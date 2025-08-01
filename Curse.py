from PyQt6 import QtWidgets, QtGui, QtCore
from typing import List, Dict, Optional
from collections import defaultdict
import traceback
import re
import os
import sys


class InfiniteCanvas(QtWidgets.QMainWindow):
    def __init__(self, start_x=0, start_y=0, cell_size=20):
        super().__init__()
        self.cell_size = cell_size
        self.step = 40  # логический шаг (базовое деление осей)
        self.semi_step = 20
        self.current_tool = None
        self.undo_stack = []

        # Границы рабочей области
        self.min_x = -200
        self.min_y = -200
        self.max_x = 6000  # Можно увеличить при необходимости
        self.max_y = 6000

        self.setWindowTitle("Графический редактор")
        self.setGeometry(100, 100, 1300, 900)

        # Центральный виджет
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QHBoxLayout(central_widget)

        # Сцена и вид
        scene_width = self.max_x - self.min_x + 200
        scene_height = self.max_y - self.min_y + 200

        self.scene = QtWidgets.QGraphicsScene(
            self.min_x, self.min_y,
            scene_width, scene_height
        )

        self.view = QtWidgets.QGraphicsView(self.scene)
        self.view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        self.view.scale(1, -1)
        self.scene.selectionChanged.connect(self.update_properties_panel)

        self.cell_manager = CellManager(self.scene)

        # 2) Создаём CellCommentManager, передавая ссылку на текущий объект (self)
        self.cell_comment_manager = CellCommentManager(self.scene, self)

        # Панель инструментов
        self.tool_panel = QtWidgets.QFrame()
        self.tool_panel.setMinimumWidth(300)
        self.tool_layout = QtWidgets.QVBoxLayout(self.tool_panel)

        self.toolbar = ToolBarWidget(self)
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, self.create_toolbar())

        # self.current_tool = "select"

        layout.addWidget(self.view)
        layout.addWidget(self.tool_panel)

        self.create_tools()
        self.setup_scene_events()

        self.scene.selectionChanged.connect(self.update_properties_panel)

        self.active_layer = 1

        self.drawing_temp = False
        self.temp_line = None
        self.line_start = None
        self._vline_counter = 0

        # Инициализация
        self.draw_grid()
        self.draw_axes()
        self.moving_item = None
        self.move_start_pos = None
        # Перемещение и рисование
        self.last_pos = None
        self.line_start = None
        self.temp_line = None

        self.LINE_MATERIALS = {
            "M2": {"color": "#00ffff", "style": QtCore.Qt.PenStyle.SolidLine, "z": 4},
            "M1": {"color": "black", "style": QtCore.Qt.PenStyle.SolidLine, "z": 3},
            "SI": {"color": "#77f28d", "style": QtCore.Qt.PenStyle.SolidLine, "z": 2},
            "PA": {"color": "#123cda", "style": QtCore.Qt.PenStyle.SolidLine, "z": 1},
            "NA": {"color": "#d51903", "style": QtCore.Qt.PenStyle.SolidLine, "z": 1},
            "PK": {"color": "#7236e3", "style": QtCore.Qt.PenStyle.SolidLine, "z": 1},
            "NK": {"color": "#f97be6", "style": QtCore.Qt.PenStyle.SolidLine, "z": 1},
            "VCC": {"color": "#ff00ff", "style": QtCore.Qt.PenStyle.DashLine, "z": 1},
            "GND": {"color": "#00ffff", "style": QtCore.Qt.PenStyle.DashLine, "z": 1},
        }

        self.CONTACT_MATERIALS = {
            "CPA": {"color": "#ff0000", "z": 5},  # Контакты поверх линий
            "CPK": {"color": "#00ff00", "z": 5},
            "CPE": {"color": "#00ff00", "z": 5},
            "CNA": {"color": "#00ff00", "z": 5},
            "CNK": {"color": "#00ff00", "z": 5},
            "CNE": {"color": "#00ff00", "z": 5},
            "CSI": {"color": "#00ff00", "z": 5},
            "CM1": {"color": "#00ff00", "z": 5},
            "CW": {"color": "#0000ff", "z": 5}
        }

        self.TWO_POINT_CONTACT_TYPES = {
            "CENAPE": {"colors": ("#ff8800", "#00aa88")},  # Пример: левый — оранжевый, правый — зелёно-синий
            "CEPENA": {"colors": ("#88aaff", "#ffaa88")},
            "CEPANE": {"colors": ("#aa00ff", "#888800")},
            "CENEPA": {"colors": ("#00ccff", "#ff00aa")}
        }

        self.vlines_visible = True

        self.view.viewport().installEventFilter(self)

        # Центрирование
        self.view.centerOn(start_x, start_y)
        self.create_menu()


    def create_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("Файл")

        create_menu = menu_bar.addMenu("Создать")

        create_tabel = QtGui.QAction("Создать таблицу ячеек", self)
        create_tabel.triggered.connect(self.table_creation)
        create_menu.addAction(create_tabel)

        # Существующее действие
        save_action = QtGui.QAction("Сохранение спецификаци о всех элементах", self)
        save_action.triggered.connect(self.save_cells_to_files)
        file_menu.addAction(save_action)

        # Новое действие для CIF
      #  save_cif_action = QtGui.QAction("Сохранение яч", self)
    # save_cif_action.triggered.connect(self.export_to_cif)
     #   file_menu.addAction(save_cif_action)

        export_comment_cif_action = QtGui.QAction("Загрузка спецификации", self)
        export_comment_cif_action.triggered.connect(self.export_comment_fragments_to_cif)
        file_menu.addAction(export_comment_cif_action)
    # создание таблицы с ячейками
    def table_creation(self):
        # Диалог для выбора размера ячеек по X (в логических шагах)
        size_x_dialog = QtWidgets.QInputDialog(self)
        size_x_dialog.setWindowTitle("Размер ячеек по X")
        size_x_dialog.setLabelText("Введите ширину ячеек (в шагах):")
        size_x_dialog.setInputMode(QtWidgets.QInputDialog.InputMode.IntInput)
        size_x_dialog.setIntRange(1, 50)
        size_x_dialog.setIntValue(15)

        if not size_x_dialog.exec():
            return

        steps_x = size_x_dialog.intValue()
        cell_size_x = steps_x * self.step

        # Диалог для выбора размера ячеек по Y (в шагах)
        size_y_dialog = QtWidgets.QInputDialog(self)
        size_y_dialog.setWindowTitle("Размер ячеек по Y")
        size_y_dialog.setLabelText("Введите высоту ячеек (в шагах):")
        size_y_dialog.setInputMode(QtWidgets.QInputDialog.InputMode.IntInput)
        size_y_dialog.setIntRange(1, 50)
        size_y_dialog.setIntValue(12)

        if not size_y_dialog.exec():
            return

        steps_y = size_y_dialog.intValue()
        cell_size_y = steps_y * self.step

        # Диалог для выбора количества ячеек по X
        count_x_dialog = QtWidgets.QInputDialog(self)
        count_x_dialog.setWindowTitle("Количество ячеек по X")
        count_x_dialog.setLabelText("Введите количество ячеек по горизонтали (X):")
        count_x_dialog.setInputMode(QtWidgets.QInputDialog.InputMode.IntInput)
        count_x_dialog.setIntRange(1, 100)
        count_x_dialog.setIntValue(3)

        if not count_x_dialog.exec():
            return

        cell_count_x = count_x_dialog.intValue()

        # Диалог для выбора количества ячеек по Y
        count_y_dialog = QtWidgets.QInputDialog(self)
        count_y_dialog.setWindowTitle("Количество ячеек по Y")
        count_y_dialog.setLabelText("Введите количество ячеек по вертикали (Y):")
        count_y_dialog.setInputMode(QtWidgets.QInputDialog.InputMode.IntInput)
        count_y_dialog.setIntRange(1, 100)
        count_y_dialog.setIntValue(2)

        if not count_y_dialog.exec():
            return

        cell_count_y = count_y_dialog.intValue()

        # Очищаем существующие ячейки
        if hasattr(self, 'cell_manager'):
            self.cell_manager.columns.clear()
            self.cell_manager.rows.clear()
            self.cell_manager.cells.clear()
            self.cell_manager.draw_cell_borders()

        # Создаем столбцы (X)
        for i in range(cell_count_x + 1):
            x_pos = i * cell_size_x
            self.create_column(QtCore.QPointF(x_pos, 0))

        # Создаем строки (Y)
        for j in range(cell_count_y + 1):
            y_pos = j * cell_size_y
            self.create_row(QtCore.QPointF(0, y_pos))

        # Обновляем отображение
        self.cell_manager.draw_cell_borders()
        self.cell_comment_manager.update_comments(
            self.cell_manager.columns,
            self.cell_manager.rows
        )

        print(f"Создана таблица {cell_count_x}x{cell_count_y} ячеек размером {steps_x}x{steps_y} шагов")

    def export_comment_fragments_to_cif(self):
        if not hasattr(self, 'cell_comment_manager') or not self.cell_comment_manager.comment_items:
            QtWidgets.QMessageBox.information(self, "Экспорт", "Нет комментариев для экспорта.")
            return

        try:
            with open("comments_fragments.cif", "w", encoding="utf-8") as f:
                f.write("CIF 2.0;\n")
                f.write("(Generated by Comment Fragment Export);\n\n")

                count = 1
                for item in self.cell_comment_manager.comment_items:
                    if item.data(0) in ["column_comment", "row_comment"]:
                        comment_obj = item.data(1)
                        if isinstance(comment_obj, CellComment):
                            f.write(f"\n### Фрагмент {count}: {comment_obj.text} ###\n")
                            f.write(comment_obj.to_cif(100 + count))
                            f.write("\n\n")
                            count += 1

            QtWidgets.QMessageBox.information(self, "Успех",
                                              "Комментарий-фрагменты экспортированы в comments_fragments.cif")
            print("Экспорт комментариев в CIF завершён.")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать: {str(e)}")
            print(f"Ошибка при экспорте комментариев: {e}")

    def export_to_cif(self):
        """Экспорт всех ячеек в CIF-формате"""
        if not hasattr(self, 'cell_manager') or not self.cell_manager.cells:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Нет ячеек для экспорта")
            return

        try:
            with open("cells_info.txt", "w", encoding="utf-8") as f:
                # Заголовок CIF-файла
                f.write("CIF 2.0;\n")
                f.write("(Generated by Circuit Editor);\n\n")

                # Экспорт каждой ячейки
                for i, cell in enumerate(self.cell_manager.cells, 1):
                    f.write(f"\n\n### Ячейка {i} ###\n")
                    f.write(f"# Координаты: ({cell.x1}, {cell.y1}) - ({cell.x2}, {cell.y2})\n")

                    # Получаем CIF-описание ячейки
                    cif_data = self._get_cell_cif(cell)
                    f.write(cif_data)

            # Вывод в терминал
            print("Успешный экспорт в cells_info.txt")
            print("Содержимое файла:")
            with open("cells_info.txt", "r", encoding="utf-8") as f:
                print(f.read())

            QtWidgets.QMessageBox.information(self, "Успех", "Ячейки экспортированы в cells_info.txt")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать: {str(e)}")
            print(f"Ошибка экспорта: {str(e)}")

        if hasattr(self, 'cell_comment_manager'):
            for i, comment in enumerate(self.cell_comment_manager.comment_items, 1):
                if hasattr(comment, 'data') and comment.data(0) in ["column_comment", "row_comment"]:
                    comment_obj = comment.data(1)
                    if isinstance(comment_obj, CellComment):
                        f.write(f"\n\n### Комментарий {i}: {comment_obj.text} ###\n")
                        f.write(comment_obj.to_cif(100 + i))  # fragment_id = 100+i

    def _get_cell_cif(self, cell) -> str:
        """Генерирует CIF-описание для одной ячейки"""
        cif_lines = [
            f"DS {int(cell.x1)} {int(cell.y1)} {int(cell.x2)} {int(cell.y1)};",
            f"DF 1;  # Уровень масштабирования"
        ]

        # Группируем элементы по слоям
        layers = {}
        for item in cell.elements:
            if not hasattr(item, 'data'):
                continue

            layer = item.data(1) if item.data(1) else "UNKNOWN_LAYER"
            if layer not in layers:
                layers[layer] = []

            if item.data(0) == "wire":
                line = item.line()
                layers[layer].append(
                    f"W {item.data(2)} "  # Ширина
                    f"({int(line.x1())} {int(line.y1())}) "
                    f"({int(line.x2())} {int(line.y2())});"
                )
            elif item.data(0) == "contact":
                pos = item.scenePos()
                layers[layer].append(
                    f"C {item.data(2)} "  # Диаметр
                    f"({int(pos.x())} {int(pos.y())});"
                )

        # Добавляем элементы по слоям
        for layer, elements in layers.items():
            cif_lines.append(f"\nL {layer};  # Слой {layer}")
            cif_lines.extend(elements)

        return "\n".join(cif_lines)

    def save_cells_to_files(self):
        """Сохраняет все пользовательские элементы холста в файл grid_specification.txt"""
        filename = "grid_specification.txt"

        try:
            with open(filename, 'w', encoding='utf-8') as file:
                for item in self.scene.items():
                    # Пропускаем системные элементы
                    if hasattr(item, 'data') and item.data(0) in ["grid", "axis", "axis_mark", "axis_label"]:
                        continue

                    # Линии
                    if isinstance(item, QtWidgets.QGraphicsLineItem):
                        try:
                            line = item.line()
                            x1, y1, x2, y2 = line.x1(), line.y1(), line.x2(), line.y2()
                            width = item.pen().width() if item.pen() else 1

                            if x1 == x2:  # вертикальная
                                length = abs(y2 - y1)
                                file.write(f'Wire("line"); W_WIRE({width}) M1({x1}, {min(y1, y2)}) X({length});\n')
                            else:  # горизонтальная
                                length = abs(x2 - x1)
                                file.write(f'Wire("line"); W_WIRE({width}) M1({min(x1, x2)}, {y1}) X({length});\n')
                        except AttributeError:
                            continue

                    # Контакты
                    elif isinstance(item, QtWidgets.QGraphicsEllipseItem) and hasattr(item, 'data') and item.data(
                            0) == "contact":
                        try:
                            pos = item.pos()
                            size = item.data(2) if hasattr(item, 'data') and item.data(2) else 10
                            file.write(f'OR({"NORTH"}) CSI({pos.x()}, {pos.y()});\n')
                        except AttributeError:
                            continue

                    # Комментарии
                    elif isinstance(item, CommentTextItem):
                        try:
                            pos = item.pos()
                            text = item.toPlainText()
                            if text == getattr(item, 'placeholder', 'Комментарий'):
                                continue
                            text = text.replace('"', '\\"')
                            file.write(f'TB({pos.x()}, {pos.y()}, "{text}");\n')
                        except AttributeError:
                            continue

            print(f"Спецификация сохранена в файл {filename}")
            QtWidgets.QMessageBox.information(self, "Сохранение", f"Файл {filename} успешно сохранен")

        except Exception as e:
            print(f"Ошибка при сохранении: {str(e)}")
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл: {str(e)}")

    def create_tools(self):
        tools = [
            ("Просмотр", "view"),
            ("Линия", "line"),
            ("Транзистор", "transistor"),
            ("Контакт", "contact"),
            ("Удаление", "delete"),
            ("Граница столбца", "column"),
            ("Граница строки", "row"),
            ("Виртуальные линии", "vline"),
            ("Комментарий", "comment")
        ]

        label = QtWidgets.QLabel("Инструменты")
        label.setFont(QtGui.QFont("Arial", 18, QtGui.QFont.Weight.Bold))
        label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        self.tool_layout.addWidget(label)
        self.tool_layout.setSpacing(1)
        self.tool_layout.setContentsMargins(1, 1, 1, 1)

        self.tool_button_group = QtWidgets.QButtonGroup(self)
        self.tool_button_group.setExclusive(True)

        for tool_name, tool_id in tools:
            btn = QtWidgets.QRadioButton(tool_name)
            btn.setFixedWidth(200)
            btn.setFont(QtGui.QFont("Arial", 12))
            btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda checked, tid=tool_id: self.set_tool(tid) if checked else None)
            self.tool_button_group.addButton(btn)
            self.tool_layout.addWidget(btn)

        self.properties_label = QtWidgets.QLabel("Свойства")
        self.properties_label.hide()
        self.properties_label.setFont(QtGui.QFont("Arial", 18, QtGui.QFont.Weight.Bold))
        self.properties_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        self.tool_layout.addWidget(self.properties_label)

        self.properties_panel = QtWidgets.QFrame()
        self.properties_layout = QtWidgets.QVBoxLayout(self.properties_panel)
        self.properties_layout.setSpacing(1)
        self.properties_layout.setContentsMargins(1, 1, 1, 1)

        self.tool_layout.addWidget(self.properties_panel)
        self.property_widgets = {}

    def setup_scene_events(self):
        self.scene.selectionChanged.connect(self.update_properties_panel)

    def update_properties_panel(self):
        """
        Вызывается при изменении выделения на сцене.
        ИСПРАВЛЕНО: сначала проверяем специфичные типы, потом общие.
        """
        selected_items = self.scene.selectedItems()
        if not selected_items:
            self.clear_properties_panel()
            return

        item = selected_items[0]
        kind = item.data(0) if hasattr(item, "data") else None

        # ИСПРАВЛЕНО: сначала проверяем виртуальные линии
        if isinstance(item, QtWidgets.QGraphicsLineItem) and kind == "vline":
            self.show_vline_properties(item)
            return

        # Потом обычные линии
        if isinstance(item, QtWidgets.QGraphicsLineItem):
            self.show_line_properties(item)
            return

        if kind == "contact":
            self.show_contact_properties(item)
            return

        if isinstance(item, TransistorItem) and kind == "transistor":
            self.show_transistor_properties(item)
            return

        if kind == "cell":
            cell = item.data(1)
            if isinstance(cell, Cell):
                self.show_cell_properties(cell)
            else:
                self.clear_properties_panel()
            return

        if kind in ("column_comment", "row_comment"):
            comment = item.data(1)
            if isinstance(comment, CellComment):
                self.show_buffer_properties(comment)
            else:
                self.clear_properties_panel()
            return

        # Если никакой из известных типов не подошёл:
        self.clear_properties_panel()

    def show_buffer_properties(self, comment):
        """
        Показывает данные для выбранного буфера (столбцов или строк):
        1) Поле для редактирования имени буфера.
        2) Список связанных ячеек: имя — (координаты).
        3) Внутри каждой ячейки перечисляются элементы в формате:
           Wire("<материал>"); W_WIRE(<толщина>); K(<x1>,<y1>)-(<x2>,<y2>)
           Contact("<материал>"); W_Contact(<размер>); K(<x>,<y>)
        4) Кнопка «Коэффициент матрирования».
        5) Кнопка «Спецификация элементов» — открывает отдельное окно с текстом.
        """
        self.clear_properties_panel()
        self.properties_label.show()

        step = self.step       # обычно 40
        semi = self.semi_step  # обычно 20

        # 1) Поле для изменения имени буфера
        name_label = QtWidgets.QLabel("Имя буфера:")
        self.properties_layout.addWidget(name_label)

        name_edit = QtWidgets.QLineEdit(comment.text)
        self.properties_layout.addWidget(name_edit)

        def rename_buffer():
            new_name = name_edit.text().strip()
            if not new_name:
                return
            comment.text = new_name
            # Снова перерисовываем буферы на сцене, чтобы у QGraphicsSimpleTextItem обновился текст
            try:
                self.scene.selectionChanged.disconnect(self.update_properties_panel)
            except (TypeError, RuntimeError):
                pass

            self.cell_comment_manager.update_comments(self.cell_manager.columns, self.cell_manager.rows)

            self.scene.selectionChanged.connect(self.update_properties_panel)
            # После перерисовки снова открываем свойства этого буфера (поиск нужного comment в новом списке)
            # Чтобы окно не закрывалось сразу, можно оставить focus на этом QLineEdit, либо просто обновить панель.
            self.show_buffer_properties(comment)

        name_edit.editingFinished.connect(rename_buffer)

        # 2) Заголовок и список ячеек с их элементами
        title = QtWidgets.QLabel(f"{comment.text} — Список ячеек:")
        title.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Weight.Bold))
        self.properties_layout.addWidget(title)

        if not comment.linked_cells:
            notice = QtWidgets.QLabel("Нет связанных ячеек")
            self.properties_layout.addWidget(notice)
        else:
            # Для каждой ячейки в буфере:
            for cell in comment.linked_cells:
                # --- 2.1. Показать имя и координаты ячейки (в шагах) ---
                raw_x = cell.x1 / step
                raw_y = cell.y1 / step
                sx = round(raw_x * 2) / 2
                sy = round(raw_y * 2) / 2

                header = QtWidgets.QLabel(f"{cell.name} — ({sx:.1f}, {sy:.1f})")
                header.setFont(QtGui.QFont("Arial", 9, QtGui.QFont.Weight.Bold))
                self.properties_layout.addWidget(header)

                # --- 2.2. Показать все элементы внутри этой ячейки ---
                rect = QtCore.QRectF(cell.x1, cell.y1, cell.x2 - cell.x1, cell.y2 - cell.y1)

                for item in self.scene.items():
                    if not hasattr(item, "data"):
                        continue
                    kind = item.data(0)

                    # Линии: если хотя бы один конец внутри ячейки
                    if kind == "wire" and isinstance(item, QtWidgets.QGraphicsLineItem):
                        ln = item.line()
                        p1 = QtCore.QPointF(ln.x1(), ln.y1())
                        p2 = QtCore.QPointF(ln.x2(), ln.y2())

                        if rect.contains(p1) or rect.contains(p2):
                            material = item.data(1)      # например "M2", "M1", "SI"...
                            logic_width = item.data(2)   # логическая толщина

                            # координаты концов в шагах
                            sx1 = round((p1.x() / step) * 2) / 2
                            sy1 = round((p1.y() / step) * 2) / 2
                            sx2 = round((p2.x() / step) * 2) / 2
                            sy2 = round((p2.y() / step) * 2) / 2

                            text = (
                                f'Wire({material}); '
                                f'W_WIRE({logic_width}); '
                                f'K({sx1:.1f},{sy1:.1f})-({sx2:.1f},{sy2:.1f})'
                            )
                            label = QtWidgets.QLabel(text)
                            label.setFont(QtGui.QFont("Arial", 9))
                            self.properties_layout.addWidget(label)

                    # Контакты: проверяем центр
                    elif kind == "contact" and isinstance(item, QtWidgets.QGraphicsEllipseItem):
                        pos = item.scenePos()
                        if rect.contains(pos):
                            material = item.data(1)  # например "VIA1", "POLY"...
                            size = item.data(2)      # размер контакта

                            sx = round((pos.x() / step) * 2) / 2
                            sy = round((pos.y() / step) * 2) / 2

                            text = (
                                f'Contact({material}); '
                                f'W_Contact({size}); '
                                f'K({sx:.1f},{sy:.1f})'
                            )
                            label = QtWidgets.QLabel(text)
                            label.setFont(QtGui.QFont("Arial", 9))
                            self.properties_layout.addWidget(label)

                # Разделитель между ячейками
                separator = QtWidgets.QLabel("—" * 40)
                separator.setStyleSheet("color: gray;")
                self.properties_layout.addWidget(separator)

        # 3) Кнопка «Коэффициент матрирования»
        coef_button = QtWidgets.QPushButton("Коэффициент матрирования")
        coef_button.clicked.connect(lambda: self.ask_matrix_factor(comment))
        self.properties_layout.addWidget(coef_button)

        # 4) Кнопка «Спецификация элементов»
        spec_button = QtWidgets.QPushButton("Спецификация всех элементов")
        spec_button.clicked.connect(lambda: self.show_buffer_specification(comment))
        self.properties_layout.addWidget(spec_button)

        create_buff = QtWidgets.QPushButton("Создание группы ячеек")
        create_buff.clicked.connect(lambda: self.cells_creation_buff(comment))
        self.properties_layout.addWidget(create_buff)


        self.properties_layout.addStretch()

    def cells_creation_buff(self, comment):
        pass

    def show_buffer_specification(self, comment):
        """
        Собирает текстовую спецификацию для всех элементов во всех ячейках буфера
        и показывает его в модальном окне (QDialog с QTextEdit).
        """
        step = self.step
        result_lines = []

        # Для каждой ячейки в буфере формируем блок спецификации
        for cell in comment.linked_cells:
            # Заголовок-номер ячейки
            result_lines.append(f"({cell.name}) – ({round(cell.x1/step,1):.1f},{round(cell.y1/step,1):.1f})\n")

            rect = QtCore.QRectF(cell.x1, cell.y1, cell.x2 - cell.x1, cell.y2 - cell.y1)

            # Перебираем все элементы сцены и собираем те, что попадают в rect
            for item in self.scene.items():
                if not hasattr(item, "data"):
                    continue
                kind = item.data(0)

                # Линии
                if kind == "wire" and isinstance(item, QtWidgets.QGraphicsLineItem):
                    ln = item.line()
                    p1 = QtCore.QPointF(ln.x1(), ln.y1())
                    p2 = QtCore.QPointF(ln.x2(), ln.y2())
                    if rect.contains(p1) or rect.contains(p2):
                        material = item.data(1)
                        logic_width = item.data(2)

                        sx1 = round((p1.x()/step)*2)/2
                        sy1 = round((p1.y()/step)*2)/2
                        sx2 = round((p2.x()/step)*2)/2
                        sy2 = round((p2.y()/step)*2)/2

                        line_text = (
                            f'Wire("{material}"); '
                            f'W_WIRE({logic_width}); '
                            f'K({sx1:.1f},{sy1:.1f})-({sx2:.1f},{sy2:.1f})'
                        )
                        result_lines.append(line_text)

                # Контакты
                elif kind == "contact" and isinstance(item, QtWidgets.QGraphicsEllipseItem):
                    pos = item.scenePos()
                    if rect.contains(pos):
                        material = item.data(1)
                        size = item.data(2)
                        sx = round((pos.x()/step)*2)/2
                        sy = round((pos.y()/step)*2)/2

                        contact_text = (
                            f'Contact("{material}"); '
                            f'W_Contact({size}); '
                            f'K({sx:.1f},{sy:.1f})'
                        )
                        result_lines.append(contact_text)

            result_lines.append("")  # пустая строка между ячейками

        # Если вообще нет элементов, укажем об этом
        if not any(result_lines):
            result_lines = ["Нет элементов для спецификации."]

        full_text = "\n".join(result_lines)

        # Создаём модальный QDialog с QTextEdit
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Спецификация элементов буфера")
        dlg.resize(500, 400)

        vbox = QtWidgets.QVBoxLayout(dlg)
        text_edit = QtWidgets.QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(full_text)
        vbox.addWidget(text_edit)

        close_btn = QtWidgets.QPushButton("Закрыть")
        close_btn.clicked.connect(dlg.accept)
        vbox.addWidget(close_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        dlg.exec()

    def ask_matrix_factor(self, comment):
        factor, ok = QtWidgets.QInputDialog.getInt(
            self, "Коэффициент матрирования",
            "Введите, во сколько раз дублировать буфер:",
            value=2, min=1
        )
        if not ok or factor <= 1:
            return

        cm = self.cell_manager
        is_column_buffer = (comment.kind == "column")
        is_row_buffer = (comment.kind == "row")
        if not (is_column_buffer or is_row_buffer):
            return

        buf_index = comment.index
        if buf_index < 0:
            return

        # 1) Список исходных ячеек (Cell) в этом буфере
        original_cells = list(comment.linked_cells)
        if not original_cells:
            return

        ### ==  Матрицирование по столбцам  (vertical buffer)  == ###
        if is_column_buffer:
            orig_cols = cm.columns[:]  # копия списка X‐координат
            if buf_index >= len(orig_cols) - 1:
                return

            left = orig_cols[buf_index]
            right = orig_cols[buf_index + 1]
            width = right - left

            # 2) Строим новый список столбцов:
            #    – сначала все старые до left (включая left),
            #    – затем вставляем factor раз: left + k*width,
            #    – затем все старые после right, сдвинутые вправо на width*(factor−1).
            new_cols = orig_cols[: buf_index + 1]  # всё до и включая left
            for k in range(1, factor + 1):
                new_cols.append(left + width * k)
            for old_x in orig_cols[buf_index + 2:]:
                new_cols.append(old_x + width * (factor - 1))
            new_cols.sort()
            cm.columns = new_cols

            # 3) Пересобираем ячейки и рисуем границы
            cm.update_cells()
            cm.draw_cell_borders()

            # 4) Словарь для быстрой проверки: (x1,y1)→Cell
            step = self.cell_size
            eps = 1e-6
            cell_by_origin = {}
            for c in cm.cells:
                key = (round(c.x1, 6), round(c.y1, 6))
                cell_by_origin[key] = c

            # 5) Копируем содержимое: для каждой из original_cells
            for orig_cell in original_cells:
                x1_o, y1_o = orig_cell.x1, orig_cell.y1
                x2_o, y2_o = orig_cell.x2, orig_cell.y2

                for k in range(1, factor + 1):
                    dx_own = width * k

                    key = (round(x1_o + dx_own, 6), round(y1_o, 6))
                    if key not in cell_by_origin:
                        continue
                    target_cell = cell_by_origin[key]

                    # Перебираем все провода и контакты в сцене
                    for item in self.scene.items():
                        if not hasattr(item, "data"):
                            continue
                        kind0 = item.data(0)

                        # — Провода (wire)
                        if kind0 == "wire" and isinstance(item, QtWidgets.QGraphicsLineItem):
                            ln = item.line()
                            p1 = QtCore.QPointF(ln.x1(), ln.y1())
                            p2 = QtCore.QPointF(ln.x2(), ln.y2())
                            if ((x1_o - eps <= p1.x() <= x2_o + eps and y1_o - eps <= p1.y() <= y2_o + eps) or
                                    (x1_o - eps <= p2.x() <= x2_o + eps and y1_o - eps <= p2.y() <= y2_o + eps)):
                                ln_copy = GridSnapLineItem(
                                    ln.x1() + dx_own, ln.y1(),
                                    ln.x2() + dx_own, ln.y2(),
                                    cell_size=step
                                )
                                ln_copy.setPen(item.pen())
                                ln_copy.setData(0, item.data(0))
                                ln_copy.setData(1, item.data(1))
                                ln_copy.setData(2, item.data(2))
                                ln_copy.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                                ln_copy.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                                self.scene.addItem(ln_copy)
                                target_cell.add_element(ln_copy)

                        # — Контакты (contact)
                        elif kind0 == "contact" and isinstance(item, QtWidgets.QGraphicsEllipseItem):
                            pos = item.scenePos()
                            if (x1_o - eps <= pos.x() <= x2_o + eps and y1_o - eps <= pos.y() <= y2_o + eps):
                                size = item.data(2)
                                contact_copy = GridSnapEllipseItem(
                                    -size / 2, -size / 2, size, size, cell_size=step
                                )
                                contact_copy.setPos(pos.x() + dx_own, pos.y())
                                contact_copy.setData(0, item.data(0))
                                contact_copy.setData(1, item.data(1))
                                contact_copy.setData(2, size)
                                pen = QtGui.QPen(item.pen().color())
                                pen.setWidth(item.pen().width())
                                contact_copy.setPen(pen)
                                contact_copy.setBrush(item.brush())
                                contact_copy.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                                contact_copy.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                                self.scene.addItem(contact_copy)
                                target_cell.add_element(contact_copy)

                    target_cell.draw_border(self.scene)

            # 6) Обновляем распределение элементов по ячейкам
            cm.assign_elements_to_cells()

            # 7) Перерисовываем «буферы» (CellComment)
            self.cell_comment_manager.update_comments(cm.columns, cm.rows)
            return

        ### ==  Матрицирование по строкам  (horizontal buffer)  == ###
        if is_row_buffer:
            orig_rows = cm.rows[:]
            if buf_index >= len(orig_rows) - 1:
                return

            bottom = orig_rows[buf_index]
            top = orig_rows[buf_index + 1]
            height = top - bottom

            # 2) Строим новый список строк:
            #    – сначала все старые до bottom (включая bottom),
            #    – затем вставляем factor раз: bottom + k*height,
            #    – затем все старые после top, сдвинутые вверх (+=) на height*(factor−1).
            new_rows = orig_rows[: buf_index + 1]
            for k in range(1, factor + 1):
                new_rows.append(bottom + height * k)
            for old_y in orig_rows[buf_index + 2:]:
                # ВНИМАНИЕ: здесь прибавляем, а не вычитаем!
                new_rows.append(old_y + height * (factor - 1))
            new_rows.sort()
            cm.rows = new_rows

            # 3) Пересобираем ячейки и рисуем границы
            cm.update_cells()
            cm.draw_cell_borders()

            # 4) Словарь для быстрого поиска ячейки по координате (x1,y1)
            step = self.cell_size
            eps = 1e-6
            cell_by_origin = {}
            for c in cm.cells:
                key = (round(c.x1, 6), round(c.y1, 6))
                cell_by_origin[key] = c

            # 5) Для каждой исходной ячейки копируем содержимое «вниз»
            for orig_cell in original_cells:
                x1_o, y1_o = orig_cell.x1, orig_cell.y1
                x2_o, y2_o = orig_cell.x2, orig_cell.y2

                for k in range(1, factor + 1):
                    dx_own = 0
                    dy_own = height * k  # ПОМНИМ: растёт Y вверх, поэтому «перенос вниз» → прибавляем

                    key = (round(x1_o, 6), round(y1_o + dy_own, 6))
                    if key not in cell_by_origin:
                        continue
                    target_cell = cell_by_origin[key]

                    for item in self.scene.items():
                        if not hasattr(item, "data"):
                            continue
                        kind0 = item.data(0)

                        # — Провода
                        if kind0 == "wire" and isinstance(item, QtWidgets.QGraphicsLineItem):
                            ln = item.line()
                            p1 = QtCore.QPointF(ln.x1(), ln.y1())
                            p2 = QtCore.QPointF(ln.x2(), ln.y2())
                            if ((x1_o - eps <= p1.x() <= x2_o + eps and y1_o - eps <= p1.y() <= y2_o + eps) or
                                    (x1_o - eps <= p2.x() <= x2_o + eps and y1_o - eps <= p2.y() <= y2_o + eps)):
                                ln_copy = GridSnapLineItem(
                                    ln.x1() + dx_own, ln.y1() + dy_own,
                                    ln.x2() + dx_own, ln.y2() + dy_own,
                                    cell_size=step
                                )
                                ln_copy.setPen(item.pen())
                                ln_copy.setData(0, item.data(0))
                                ln_copy.setData(1, item.data(1))
                                ln_copy.setData(2, item.data(2))
                                ln_copy.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                                ln_copy.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                                self.scene.addItem(ln_copy)
                                target_cell.add_element(ln_copy)

                        # — Контакты
                        elif kind0 == "contact" and isinstance(item, QtWidgets.QGraphicsEllipseItem):
                            pos = item.scenePos()
                            if (x1_o - eps <= pos.x() <= x2_o + eps and y1_o - eps <= pos.y() <= y2_o + eps):
                                size = item.data(2)
                                contact_copy = GridSnapEllipseItem(
                                    -size / 2, -size / 2, size, size, cell_size=step
                                )
                                contact_copy.setPos(pos.x() + dx_own, pos.y() + dy_own)
                                contact_copy.setData(0, item.data(0))
                                contact_copy.setData(1, item.data(1))
                                contact_copy.setData(2, size)
                                pen = QtGui.QPen(item.pen().color())
                                pen.setWidth(item.pen().width())
                                contact_copy.setPen(pen)
                                contact_copy.setBrush(item.brush())
                                contact_copy.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                                contact_copy.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                                self.scene.addItem(contact_copy)
                                target_cell.add_element(contact_copy)

                    target_cell.draw_border(self.scene)

            # 6) Обновляем распределение элементов
            cm.assign_elements_to_cells()

            # 7) Перерисовываем «буферы»
            self.cell_comment_manager.update_comments(cm.columns, cm.rows)
            return

    def show_comment_properties(self, comment):
        self.clear_properties_panel()
        self.properties_label.show()

        # Заголовок
        title = QtWidgets.QLabel(f"{comment.text}")
        title.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Weight.Bold))
        self.properties_layout.addWidget(title)

        # Координаты
        coords = QtWidgets.QLabel(f"Координаты: ({comment.x1}, {comment.y1}) — ({comment.x2}, {comment.y2})")
        self.properties_layout.addWidget(coords)

        # Кол-во привязанных ячеек
        total = QtWidgets.QLabel(f"Привязано ячеек: {len(comment.linked_cells)}")
        self.properties_layout.addWidget(total)

        # Список координат привязанных ячеек
        for i, cell in enumerate(comment.linked_cells, 1):
            desc = QtWidgets.QLabel(
                f"Ячейка {i}: ({cell.x1}, {cell.y1}) — ({cell.x2}, {cell.y2}), элементов: {len(cell.elements)}")
            desc.setStyleSheet("font-size: 11px; color: gray;")
            self.properties_layout.addWidget(desc)

        self.properties_layout.addStretch()
# Сохранение всех элементов ячейки
    def show_cell_elements_properties(self, cell):
        """
        Отображает спецификацию всех элементов ячейки с координатами относительно ячейки
        в формате, похожем на C++.
        Координаты отсчитываются от левого нижнего угла ячейки (cell.x1, cell.y1).
        """
        # Определяем прямоугольник ячейки
        rect = QtCore.QRectF(cell.x1, cell.y1, cell.x2 - cell.x1, cell.y2 - cell.y1)

        # Получаем левый нижний угол ячейки как точку отсчета
        cell_origin = QtCore.QPointF(cell.x1, cell.y1)

        # Списки для хранения разных типов элементов
        transistor_specs = []
        contact_specs = []
        wire_specs = []

        # Перебираем все элементы на сцене
        for item in self.scene.items():
            # Проверяем, есть ли у элемента данные и какого он типа
            if not hasattr(item, "data"):
                continue
            kind = item.data(0)

            # Обрабатываем только провода, контакты и транзисторы
            if kind not in ["wire", "contact", "transistor"]:
                continue

            # Проверяем, принадлежит ли элемент данной ячейке
            element_in_cell = False

            if kind == "wire" and isinstance(item, QtWidgets.QGraphicsLineItem):
                ln = item.line()
                p1 = item.mapToScene(QtCore.QPointF(ln.x1(), ln.y1()))
                p2 = item.mapToScene(QtCore.QPointF(ln.x2(), ln.y2()))
                element_in_cell = rect.contains(p1) or rect.contains(p2)

            elif kind == "contact" and isinstance(item, QtWidgets.QGraphicsEllipseItem):
                pos = item.scenePos()
                element_in_cell = rect.contains(pos)

            elif kind == "transistor" and isinstance(item, TransistorItem):
                # Для транзистора проверяем центр его основного квадрата
                bounds = item.mapToScene(item.boundingRect()).boundingRect()
                center = bounds.center()
                element_in_cell = rect.contains(center)

            # Если элемент не в ячейке, пропускаем
            if not element_in_cell:
                continue

            # Формируем спецификацию элемента с координатами относительно ячейки
            if kind == "wire":
                # Координаты концов линии относительно левого нижнего угла ячейки
                p1_rel = p1 - cell_origin
                p2_rel = p2 - cell_origin

                # Преобразуем координаты в единицы сетки (делим на self.step = 40)
                p1_x_units = p1_rel.x() / 40.0
                p1_y_units = p1_rel.y() / 40.0
                p2_x_units = p2_rel.x() / 40.0
                p2_y_units = p2_rel.y() / 40.0

                material = item.data(1) or "M2"  # Материал (по умолчанию M2)
                logic_width = item.data(2) or -3  # Логическая толщина (по умолчанию -3)

                spec = f'WIRE({material}, {logic_width}, {p1_x_units:.2f}, {p1_y_units:.2f}, {p2_x_units:.2f}, {p2_y_units:.2f});'
                wire_specs.append(spec)


            elif kind == "contact":

                # Координаты контакта относительно левого нижнего угла ячейки

                pos_rel = item.scenePos() - cell_origin

                # Преобразуем координаты в единицы сетки (делим на self.step = 40)

                pos_x_units = pos_rel.x() / 40.0

                pos_y_units = pos_rel.y() / 40.0

                # Получаем реальный материал контакта

                contact_material = item.data(1) or "CPA"

                # Проверяем, является ли контакт двухточечным

                is_two_point = isinstance(item, TwoPointContactGroup)

                if is_two_point:

                    # Для двухточечного контакта вычисляем координаты обеих точек

                    # В TwoPointContactGroup эллипсы смещены на half_step влево и вправо от центра

                    half_step_units = (item.cell_size / 2) / 40.0  # half_step в единицах сетки

                    # Координаты левой и правой точек

                    left_x = pos_x_units - half_step_units

                    right_x = pos_x_units + half_step_units

                    # Материал хранится как "mat1,mat2", берем первый материал для спецификации

                    if "," in contact_material:

                        primary_material = contact_material.split(",", 1)[0]

                    else:

                        primary_material = contact_material

                    # Формируем спецификацию для двухточечного контакта с двумя координатами

                    spec = f'OR(NORTH) {primary_material}({left_x:.2f}, {pos_y_units:.2f}, {right_x:.2f}, {pos_y_units:.2f});'

                else:

                    # Одиночный контакт

                    spec = f'OR(NORTH) {contact_material}({pos_x_units:.2f}, {pos_y_units:.2f});'

                contact_specs.append(spec)

            elif kind == "transistor":
                # Получаем данные транзистора
                ttype = getattr(item, 'ttype', 'TP')  # "TP" или "TN"
                direction = getattr(item, 'direction', 'NORTH')  # "NORTH", "SOUTH", "EAST", "WEST"
                line_length = getattr(item, 'line_length', 0)  # Длина линии транзистора в пикселях

                # Вычисляем точку привязки (нижний центр квадрата транзистора)
                transistor_scene_pos = item.scenePos()
                local_bottom_center = QtCore.QPointF(0, -item.step)
                scene_bottom_center = item.mapToScene(local_bottom_center)
                rel_bottom_center = scene_bottom_center - cell_origin

                # Преобразуем координаты в единицы сетки (делим на self.step = 40)
                transistor_x_units = rel_bottom_center.x() / 40.0
                transistor_y_units = rel_bottom_center.y() / 40.0

                # Преобразуем длину линии в единицы (делим на self.semi_step = 20)
                line_length_units = line_length / 20.0

                # Формируем спецификацию транзистора в C++ стиле
                spec = f'W(1.00) L({line_length_units:.2f}) OR({direction}) {ttype}({transistor_x_units:.2f}, {transistor_y_units:.2f});'
                transistor_specs.append(spec)

        # Формируем итоговый текст в C++ стиле
        cell_width = (cell.x2 - cell.x1) / 40.0  # Преобразуем в единицы сетки
        cell_height = (cell.y2 - cell.y1) / 40.0  # Преобразуем в единицы сетки

        cpp_lines = []
        cpp_lines.append('#include "stdafx.h"')
        cpp_lines.append(f'#include <D:\\{cell.name}.h>')
        cpp_lines.append('')
        cpp_lines.append(f'layout& {cell.name}_::LAYOUT()')
        cpp_lines.append('{')
        cpp_lines.append(f'FRAG({cell.name})')

        # Добавляем виртуальные линии
        cpp_lines.append('// Объявление виртуальных линий')
        cpp_lines.append(f'VLIN_Y("{cell.name}top", 0.00);')
        cpp_lines.append(f'VLIN_Y("{cell.name}top", {cell_height:.2f});')
        cpp_lines.append(f'VLIN_Y("{cell.name}bot", 0.00);')
        cpp_lines.append(f'VLIN_Y("{cell.name}bot", {cell_height:.2f});')
        cpp_lines.append(f'VLIN_X("{cell.name}left", 0.00);')
        cpp_lines.append(f'VLIN_X("{cell.name}left", {cell_width:.2f});')
        cpp_lines.append(f'VLIN_X("{cell.name}right", 0.00);')
        cpp_lines.append(f'VLIN_X("{cell.name}right", {cell_width:.2f});')

        # Добавляем транзисторы
        if transistor_specs:
            cpp_lines.append('// Транзисторы')
            cpp_lines.extend(transistor_specs)

        # Добавляем контакты
        if contact_specs:
            cpp_lines.append('// Контакты')
            cpp_lines.extend(contact_specs)

        # Добавляем провода
        if wire_specs:
            cpp_lines.append('// Линии')
            cpp_lines.extend(wire_specs)

        cpp_lines.append('ENDF')
        cpp_lines.append(f'return {cell.name};')
        cpp_lines.append('}')

        spec_text = '\n'.join(cpp_lines)

        # Создаем диалоговое окно с возможностью копирования текста
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"Шаблон ячейки {cell.name}")
        dialog.setModal(True)
        dialog.resize(800, 600)

        layout = QtWidgets.QVBoxLayout(dialog)

        # Информация о ячейке
        total_elements = len(transistor_specs) + len(contact_specs) + len(wire_specs)
        # Размеры в единицах сетки
        cell_width_units = (cell.x2 - cell.x1) / 40.0
        cell_height_units = (cell.y2 - cell.y1) / 40.0

        info_label = QtWidgets.QLabel(
            f"Ячейка: {cell.name}\n"
            f"Границы: ({cell.x1:.2f}, {cell.y1:.2f}) - ({cell.x2:.2f}, {cell.y2:.2f}) [пиксели]\n"
            f"Размер: {cell_width_units:.2f} x {cell_height_units:.2f} [единицы сетки]\n"
            f"Элементов: {total_elements} (T: {len(transistor_specs)}, C: {len(contact_specs)}, W: {len(wire_specs)})"
        )
        info_label.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 10px; border: 1px solid #ccc; }")
        layout.addWidget(info_label)

        # Текстовое поле для отображения спецификации
        text_edit = QtWidgets.QTextEdit()
        text_edit.setPlainText(spec_text)
        text_edit.setReadOnly(True)
        text_edit.setFont(QtGui.QFont("Courier", 9))  # Моноширинный шрифт для лучшего отображения
        layout.addWidget(text_edit)

        # Кнопки
        button_layout = QtWidgets.QHBoxLayout()

        copy_button = QtWidgets.QPushButton("Копировать в буфер")
        copy_button.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(spec_text))
        button_layout.addWidget(copy_button)

        save_button = QtWidgets.QPushButton("Сохранить в файл")

        def save_to_file():
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                dialog,
                "Сохранить layout спецификацию",
                f"{cell.name}_layout.cpp",
                "C++ files (*.cpp *.h);;Text files (*.txt);;All files (*.*)"
            )
            if file_path:
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(spec_text)
                    QtWidgets.QMessageBox.information(dialog, "Успех", f"Layout спецификация сохранена в {file_path}")
                except Exception as e:
                    QtWidgets.QMessageBox.critical(dialog, "Ошибка", f"Не удалось сохранить файл:\n{str(e)}")

        save_button.clicked.connect(save_to_file)
        button_layout.addWidget(save_button)

        close_button = QtWidgets.QPushButton("Закрыть")
        close_button.clicked.connect(dialog.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

        dialog.exec()

    def save_as(self, text, cell_name=None):
        """
        Сохраняет текст спецификации в файл .cpp, выбранный пользователем.
        """
        default_name = f"{cell_name}_layout.cpp" if cell_name else ""
        file_name, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Сохранить спецификацию",
            default_name,
            "C++ файлы (*.cpp);;Все файлы (*)"
        )
        if file_name:
            try:
                with open(file_name, 'w', encoding='utf-8') as f:
                    f.write(text)
                print(f"Спецификация сохранена в {file_name}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл: {e}")

    def show_cell_properties(self, cell):
        self.clear_properties_panel()
        self.properties_label.show()

        name_label = QtWidgets.QLabel("Имя ячейки:")
        self.properties_layout.addWidget(name_label)

        name_edit = QtWidgets.QLineEdit(cell.name)
        self.properties_layout.addWidget(name_edit)

        def rename_cell():
            new_name = name_edit.text().strip()
            if not new_name:
                return
            cell.name = new_name
            try:
                self.scene.selectionChanged.disconnect(self.update_properties_panel)
            except (TypeError, RuntimeError):
                pass
            if hasattr(self, "cell_manager") and self.cell_manager is not None:
                self.cell_manager.draw_cell_borders()
            self.scene.selectionChanged.connect(self.update_properties_panel)

        name_edit.editingFinished.connect(rename_cell)

        # Определяем прямоугольник ячейки
        rect = QtCore.QRectF(cell.x1, cell.y1, cell.x2 - cell.x1, cell.y2 - cell.y1)
        line_count = 0
        contact_count = 0
        transistor_count = 0  # Добавляем счетчик транзисторов

        # Перебираем элементы сцены
        for item in self.scene.items():
            if not hasattr(item, "data"):
                continue
            kind = item.data(0)
            if kind == "wire" and isinstance(item, QtWidgets.QGraphicsLineItem):
                ln = item.line()
                p1 = item.mapToScene(QtCore.QPointF(ln.x1(), ln.y1()))
                p2 = item.mapToScene(QtCore.QPointF(ln.x2(), ln.y2()))
                if rect.contains(p1) or rect.contains(p2):
                    line_count += 1
            elif kind == "contact" and isinstance(item, QtWidgets.QGraphicsEllipseItem):
                pos = item.scenePos()
                if rect.contains(pos):
                    contact_count += 1
            elif kind == "transistor" and isinstance(item, TransistorItem):
                # Получаем центр транзистора
                bounds = item.mapToScene(item.boundingRect()).boundingRect()
                center = bounds.center()
                if rect.contains(center):
                    transistor_count += 1

        # Обновляем общее количество элементов
        total_elems = line_count + contact_count + transistor_count
        count_label = QtWidgets.QLabel(f"Элементов внутри: {total_elems}")
        self.properties_layout.addWidget(count_label)
        line_label = QtWidgets.QLabel(f"Линий: {line_count}")
        self.properties_layout.addWidget(line_label)
        contact_label = QtWidgets.QLabel(f"Контактов: {contact_count}")
        self.properties_layout.addWidget(contact_label)
        # Исправляем название переменной и добавляем метку
        transistor_label = QtWidgets.QLabel(f"Транзисторов: {transistor_count}")
        self.properties_layout.addWidget(transistor_label)

        # Остальные кнопки остаются без изменений
        copy_x_button = QtWidgets.QPushButton("Копировать по X")
        copy_x_button.clicked.connect(lambda: self.copy_cell(cell, direction="x"))
        self.properties_layout.addWidget(copy_x_button)

        copy_y_button = QtWidgets.QPushButton("Копировать по Y")
        copy_y_button.clicked.connect(lambda: self.copy_cell(cell, direction="y"))
        self.properties_layout.addWidget(copy_y_button)

        vl_button = QtWidgets.QPushButton("Спецификация виртуальных линий")
        vl_button.clicked.connect(lambda: self.show_vline_specification(cell))
        self.properties_layout.addWidget(vl_button)

        cell_props_button = QtWidgets.QPushButton("Спецификация элементов ячейки")
        cell_props_button.clicked.connect(lambda: self.show_cell_properties_dialog(cell))
        self.properties_layout.addWidget(cell_props_button)

        btn_elems_props = QtWidgets.QPushButton("Спецификация всей ячейки")
        btn_elems_props.clicked.connect(lambda: self.show_cell_elements_properties(cell))
        self.properties_layout.addWidget(btn_elems_props)

        btn_create_cell_byspec = QtWidgets.QPushButton("Создание ячейки")
        btn_create_cell_byspec.clicked.connect(lambda: self.cell_creation(cell))
        self.properties_layout.addWidget(btn_create_cell_byspec)

        self.properties_layout.addStretch()

    def show_cell_properties_dialog(self, cell):
        rect = QtCore.QRectF(cell.x1, cell.y1, cell.x2 - cell.x1, cell.y2 - cell.y1)
        step = self.step  # обычно 40

        # Формируем текст для всех элементов ячейки
        lines = []
        for item in self.scene.items():
            if not hasattr(item, "data"):
                continue

            kind = item.data(0)

            # Линии
            if kind == "wire" and isinstance(item, QtWidgets.QGraphicsLineItem):
                ln = item.line()
                p1 = QtCore.QPointF(ln.x1(), ln.y1())
                p2 = QtCore.QPointF(ln.x2(), ln.y2())

                if rect.contains(p1) or rect.contains(p2):
                    material = item.data(1)
                    logic_width = item.data(2)

                    # Координаты в шагах
                    sx1 = p1.x() / step
                    sy1 = p1.y() / step
                    sx2 = p2.x() / step
                    sy2 = p2.y() / step

                    # Округляем до .0 или .5
                    sx1 = round(sx1 * 2) / 2
                    sy1 = round(sy1 * 2) / 2
                    sx2 = round(sx2 * 2) / 2
                    sy2 = round(sy2 * 2) / 2

                    text = (
                        f'Wire({material}) W_WIRE({logic_width}) '
                        f'({sx1:.1f},{sy1:.1f})-({sx2:.1f},{sy2:.1f});\n'
                    )
                    lines.append(text)

            # Контакты
            elif kind == "contact" and isinstance(item, QtWidgets.QGraphicsEllipseItem):
                pos = item.scenePos()
                if rect.contains(pos):
                    material = item.data(1)
                    size = item.data(2)

                    # Координаты центра в шагах
                    sx = pos.x() / step
                    sy = pos.y() / step
                    sx = round(sx * 2) / 2
                    sy = round(sy * 2) / 2

                    text = (
                        f'OR(NORTH) '
                        f'{material} '
                        f'({sx:.1f},{sy:.1f}) '
                        f'W_Contact({size});\n'
                    )
                    lines.append(text)

        # Объединяем строки в полный текст
        full_text = "".join(lines) if lines else "Нет элементов в ячейке"

        # Создаем диалоговое окно
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Свойства элементов ячейки {cell.name}")
        dlg.resize(400, 300)

        # Создаем меню "Файл"
        menubar = QtWidgets.QMenuBar(dlg)
        file_menu = menubar.addMenu("Файл")
        save_as_action = file_menu.addAction("Сохранить как...")
        save_as_action.triggered.connect(lambda: self.save_as(full_text, cell.name))

        # Устанавливаем меню в диалог
        layout = QtWidgets.QVBoxLayout(dlg)
        layout.setMenuBar(menubar)

        # Текстовое поле
        text_edit = QtWidgets.QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(full_text)
        layout.addWidget(text_edit)

        # Кнопка "Закрыть"
        close_btn = QtWidgets.QPushButton("Закрыть")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        dlg.exec()

    def show_vline_specification(self, cell):
        """
        Перебираем все QGraphicsLineItem с data(0) == "vline" на сцене,
        и отбираем лишь те, у которых имя data(1) содержит "_<cell.name>_".
        Из этого имени мы извлекаем:
          - source      = часть до первого "_"
          - cell_name   = часть между первыми двумя "_"
          - edge_type   = часть между вторыми и третьими "_"
          - count_index = (необязательный суффикс в скобках), если есть

        Далее строим строку "Имя -- Отношение -- Значение", где:
          • Имя — это полное data(1) для vline (например, "SI_cell22_lft(1)") или
              cell.name + имя границы для границ ячейки
          • Отношение — это сокращённое edge_type: "lft", "rht", "btm" или "top"
          • Значение — координата (x или y) относительно левого нижнего угла ячейки (cell.x1, cell.y1), разделенная на self.step:
            - Для "btm" и "top": x-координата относительно cell.x1
            - Для "lft" и "rht": y-координата относительно cell.y1

        Кроме того, в конец списка добавляются 8 «заглушек» для собственных границ ячейки:
          cell22top--lft--0
          cell22top--rht--<x2-x1>
          cell22bot--lft--0
          cell22bot--rht--<x2-x1>
          cell22left--btm--0
          cell22left--top--<y2-y1>
          cell22right--btm--0
          cell22right--top--<y2-y1>
        """
        print(f"\n=== Отладка show_vline_specification для ячейки {cell.name} ===")

        # 1) Сначала ищем реальные vline-элементы, привязанные к этой ячейке
        found = []
        for item in self.scene.items():
            if not (isinstance(item, QtWidgets.QGraphicsLineItem) and item.data(0) == "vline"):
                continue

            full_name = item.data(1) or ""
            parts = full_name.split("_")
            # Ожидаем минимум 3 части: [source, cell.name, edge_and_rest...]
            if len(parts) < 3:
                continue

            source, cell_name, edge_and_rest = parts[0], parts[1], parts[2]
            if cell_name != cell.name:
                continue

            # Из «edge_and_rest» (например "lft", "lft(1)", "btm(2)" и т.п.) берём только буквы до "("
            if "(" in edge_and_rest:
                edge_type = edge_and_rest.split("(")[0]
            else:
                edge_type = edge_and_rest

            # Получаем «сценные» координаты концов линии
            ln: QtCore.QLineF = item.line()
            try:
                p1_scene = item.mapToScene(ln.p1())
                p2_scene = item.mapToScene(ln.p2())
                x1, y1 = p1_scene.x(), p1_scene.y()
                x2, y2 = p2_scene.x(), p2_scene.y()
            except Exception as e:
                print(f"Ошибка при получении координат vline {full_name}: {e}")
                continue

            # Вычисляем локальную координату относительно (cell.x1, cell.y1)
            if edge_type in ("lft", "rht"):
                # Вертикальная линия: берем среднюю y-координату относительно cell.y1
                val = (y1 + y2) / 2 - cell.y1
            elif edge_type in ("btm", "top"):
                # Горизонтальная линия: берем среднюю x-координату относительно cell.x1
                val = (x1 + x2) / 2 - cell.x1
            else:
                # По умолчанию (для безопасности)
                print(f"Неизвестный edge_type {edge_type} для {full_name}, используем x")
                val = (x1 + x2) / 2 - cell.x1

            found.append((full_name, edge_type, val))

        print(f"  Всего найдено подходящих vline: {len(found)}")

        # 2) Добавляем «собственные» границы ячейки (8 строк).
        # Координаты относительно (cell.x1, cell.y1):
        # - top: x = 0 (lft) или cell.x2 - cell.x1 (rht)
        # - bot: x = 0 (lft) или cell.x2 - cell.x1 (rht)
        # - left: y = 0 (btm) или cell.y2 - cell.y1 (top)
        # - right: y = 0 (btm) или cell.y2 - cell.y1 (top)
        x_right = cell.x2 - cell.x1  # Локальная x для правой границы
        y_top = cell.y2 - cell.y1  # Локальная y для верхней границы

        # Для верхнего края (top): отношение lft и rht определяет x
        found.append((f"{cell.name}top", "lft", 0))  # x=0
        found.append((f"{cell.name}top", "rht", x_right))  # x=x_right
        # Для нижнего края (bot): отношение lft и rht определяет x
        found.append((f"{cell.name}bot", "lft", 0))  # x=0
        found.append((f"{cell.name}bot", "rht", x_right))  # x=x_right
        # Для левого края (left): отношение btm и top определяет y
        found.append((f"{cell.name}left", "btm", 0))  # y=0
        found.append((f"{cell.name}left", "top", y_top))  # y=y_top
        # Для правого края (right): отношение btm и top определяет y
        found.append((f"{cell.name}right", "btm", 0))  # y=0
        found.append((f"{cell.name}right", "top", y_top))  # y=y_top

        # 3) Формируем финальный текст
        lines = []
        for name, rel, value in found:
            # Делим value на self.step и выводим с двумя знаками после запятой
            coord_type = "x" if rel in ("btm", "top") else "y"
            lines.append(f"{name} -- {rel} -- {value / self.step:.2f}")
        full_text = "\n".join(lines)

        # 4) Показываем в диалоге
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Спецификация виртуальных линий")
        dlg.resize(400, 300)

        # Создаем меню "Файл"
        menubar = QtWidgets.QMenuBar(dlg)
        file_menu = menubar.addMenu("Файл")
        save_as_action = file_menu.addAction("Сохранить как...")
        save_as_action.triggered.connect(lambda: self.save_as(full_text))

        # Устанавливаем меню в диалог
        layout = QtWidgets.QVBoxLayout(dlg)
        layout.setMenuBar(menubar)

        # Текстовое поле
        text_edit = QtWidgets.QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(full_text)
        layout.addWidget(text_edit)

        # Кнопка "Закрыть"
        close_btn = QtWidgets.QPushButton("Закрыть")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        dlg.exec()

    def cell_creation(self, cell):
        """
        Удаляет текущую ячейку, открывает диалог для выбора .cpp-файла со спецификацией,
        парсит его и создаёт новую ячейку с границами, виртуальными линиями, проводами,
        контактами и транзисторами из этой спецификации.
        """
        print(f"\n=== Отладка cell_creation для ячейки {cell.name} ===")

        # 1) Удаляем текущую ячейку (границы и все её элементы)
        if hasattr(self, "cell_manager") and self.cell_manager is not None:
            self.cell_manager.remove_cell(cell)
        else:
            QtWidgets.QMessageBox.critical(self, "Ошибка", "CellManager не найден")
            return

        # 2) Открываем диалог выбора файла
        file_name, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Выбрать спецификацию ячейки",
            "",
            "C++ файлы (*.cpp);;Все файлы (*)"
        )
        if not file_name:
            print("Файл не выбран")
            return

        # 3) Читаем содержимое файла
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось открыть файл: {e}")
            return

        # 4) Парсим имя ячейки
        # Ищем либо FRAG(<cellname>), либо layout& <cellname>_::LAYOUT
        cell_name_match = re.search(r'FRAG\(\s*([^\)]+)\s*\)|layout&\s*([A-Za-z0-9_]+)_::LAYOUT', content)
        if cell_name_match:
            cell_name = cell_name_match.group(1) or cell_name_match.group(2)
        else:
            QtWidgets.QMessageBox.critical(self, "Ошибка", "Не удалось определить имя ячейки")
            return

        # 5) Паттерны для поиска элементов
        # 5.1) Виртуальные линии по X и Y
        vlin_x_pattern = re.compile(r'VLIN_X\(\s*"([^"]+)"\s*,\s*([\d\.]+)\s*\);')
        vlin_y_pattern = re.compile(r'VLIN_Y\(\s*"([^"]+)"\s*,\s*([\d\.]+)\s*\);')

        # 5.2) Транзисторы: W(<w>) L(<l>) OR(<dir>) (TP|TN)(<x>, <y>);
        transistor_pattern = re.compile(
            r'W\(\s*([\d\.]+)\s*\)\s*'  # W(width)
            r'L\(\s*([\d\.]+)\s*\)\s*'  # L(length)
            r'OR\(\s*(NORTH|SOUTH|EAST|WEST)\s*\)\s*'  # OR(direction)
            r'(TP|TN)\(\s*([\d\.]+)\s*,\s*([\d\.]+)\s*\)\s*;'  # TP or TN(x, y)
        )

        # 5.3) Контакты: OR(NORTH) <MAT>(<x>, <y>);
        #      В спецификации show_cell_elements_properties мы формируем так:
        #        OR(NORTH) CPA(8.00, 4.00);
        contact_pattern = re.compile(
            r'OR\(\s*NORTH\s*\)\s*([A-Za-z0-9]+)\(\s*([\d\.]+)\s*,\s*([\d\.]+)\s*\)\s*;'
        )

        # 5.4) Провода (WIRE): WIRE(<MAT>, <width>, <x1>, <y1>, <x2>, <y2>);
        #      Заметим: спецификация пишется без кавычек вокруг <MAT>, поэтому паттерн без кавычек:
        wire_pattern = re.compile(
            r'WIRE\(\s*([A-Za-z0-9]+)\s*,\s*([-]?\d+)\s*,\s*'  # MAT, width (целое число, может быть отрицательным)
            r'([\d\.]+)\s*,\s*([\d\.]+)\s*,\s*'  # x1, y1
            r'([\d\.]+)\s*,\s*([\d\.]+)\s*\)\s*;'  # x2, y2
        )

        # 6) Собираем списки
        x_min = x_max = y_min = y_max = None
        vlines = []  # [(name, axis, значение_пиксели)]
        transistors = []  # [(width, length, direction, ttype, x, y)]
        contacts = []  # [(material, x, y)]
        wires = []  # [(material, width, x1, y1, x2, y2)]

        # 6.1) Парсим виртуальные линии по X
        for m in vlin_x_pattern.finditer(content):
            name, x_str = m.groups()
            x_val = float(x_str) * self.step  # в пикселях
            vlines.append((name, 'x', x_val))
            # если имя совпадает с "<cell_name>left" либо "<cell_name>right", обновляем границы
            if name == f"{cell_name}left":
                x_min = x_val if x_min is None else min(x_min, x_val)
            elif name == f"{cell_name}right":
                x_max = x_val if x_max is None else max(x_max, x_val)

        # 6.2) Парсим виртуальные линии по Y
        for m in vlin_y_pattern.finditer(content):
            name, y_str = m.groups()
            y_val = float(y_str) * self.step
            vlines.append((name, 'y', y_val))
            if name == f"{cell_name}bot":
                y_min = y_val if y_min is None else min(y_min, y_val)
            elif name == f"{cell_name}top":
                y_max = y_val if y_max is None else max(y_max, y_val)

        # 6.3) Парсим транзисторы
        for m in transistor_pattern.finditer(content):
            w_str, l_str, direction, ttype, x_str, y_str = m.groups()
            w_val = float(w_str)  # логическая ширина (мы пока не используем, но можно сохранить)
            l_val = float(l_str)  # логическая длина линии (в единицах grid)
            x_val = float(x_str) * self.step
            y_val = float(y_str) * self.step
            transistors.append((w_val, l_val, direction, ttype, x_val, y_val))

        # 6.4) Парсим контакты
        for m in contact_pattern.finditer(content):
            mat, x_str, y_str = m.groups()
            x_val = float(x_str) * self.step
            y_val = float(y_str) * self.step
            contacts.append((mat, x_val, y_val))

        # 6.5) Парсим провода
        for m in wire_pattern.finditer(content):
            mat, width_str, x1_str, y1_str, x2_str, y2_str = m.groups()
            width_val = int(width_str)  # логическая толщина
            x1 = float(x1_str) * self.step
            y1 = float(y1_str) * self.step
            x2 = float(x2_str) * self.step
            y2 = float(y2_str) * self.step
            wires.append((mat, width_val, x1, y1, x2, y2))

        # 7) Проверка, что границы определены
        if None in (x_min, x_max, y_min, y_max):
            QtWidgets.QMessageBox.critical(self, "Ошибка", "Не удалось определить границы ячейки")
            return

        # 8) Создаем новый объект Cell с распарсенными границами
        try:
            new_cell = Cell(x1=x_min, y1=y_min, x2=x_max, y2=y_max, name=cell_name)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось создать Cell: {e}")
            return

        # 9) Добавляем в CellManager
        if hasattr(self, "cell_manager") and self.cell_manager is not None:
            self.cell_manager.add_cell(new_cell)
        else:
            QtWidgets.QMessageBox.critical(self, "Ошибка", "CellManager не найден")
            return

        # 10) Рисуем в сцене виртуальные линии, провода, контакты, транзисторы

        # 10.1) Виртуальные линии
        for name, axis, val in vlines:
            if axis == 'x':
                # Горизонтальная: (x=val, y=y_min) → (x=val, y=y_max)
                line_item = QtWidgets.QGraphicsLineItem(val, y_min, val, y_max)
            else:
                # Вертикальная: (x=x_min, y=val) → (x=x_max, y=val)
                line_item = QtWidgets.QGraphicsLineItem(x_min, val, x_max, val)

            line_item.setData(0, "vline")
            line_item.setData(1, name)
            pen = QtGui.QPen(QtGui.QColor("red"))
            pen.setWidth(1)
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            line_item.setPen(pen)
            self.scene.addItem(line_item)
            # Регистрируем пересечения
            self.cell_manager.register_vline_intersections(line_item)

        # 10.2) Провода
        for mat, width_val, x1, y1, x2, y2 in wires:
            wire_item = GridSnapLineItem(x1, y1, x2, y2, cell_size=self.cell_size)
            wire_item.setData(0, "wire")
            wire_item.setData(1, mat)
            wire_item.setData(2, width_val)
            # Применяем стиль провода (аналогично show_line_properties)
            if mat in self.LINE_MATERIALS:
                self.set_line_style(wire_item, mat, width_val)
            else:
                pen = QtGui.QPen(QtGui.QColor("black"))
                pen.setWidth(max(1, abs(width_val)))
                pen.setStyle(QtCore.Qt.PenStyle.SolidLine)
                wire_item.setPen(pen)

            self.scene.addItem(wire_item)

        # 10.3) Контакты
        contact_size = 10  # фиксированный пиксельный размер (можно вынести в параметр)
        for mat, x, y in contacts:
            ellipse = GridSnapEllipseItem(-contact_size / 2, -contact_size / 2, contact_size, contact_size,
                                          cell_size=self.cell_size)
            ellipse.setPos(QtCore.QPointF(x, y))
            if mat in self.CONTACT_MATERIALS:
                params = self.CONTACT_MATERIALS[mat]
                ellipse.setBrush(QtGui.QBrush(QtGui.QColor(params["color"])))
                ellipse.setZValue(params["z"])
            else:
                ellipse.setBrush(QtGui.QBrush(QtGui.QColor("black")))
                ellipse.setZValue(5)

            ellipse.setData(0, "contact")
            ellipse.setData(1, mat)
            ellipse.setData(2, contact_size)
            pen = QtGui.QPen(QtGui.QColor("black"))
            pen.setWidth(1)
            ellipse.setPen(pen)
            self.scene.addItem(ellipse)

        # 10.4) Транзисторы
        for w_val, l_val, direction, ttype, x, y in transistors:
            # Преобразуем длину L из «логических единиц» в пиксели:
            # В спецификации L(<l_val>) задаётся в «grid-единицах» (то есть 1.00 = 40 пикселей),
            # поэтому:
            line_length_pixels = l_val * self.step
            t_item = TransistorItem(
                cell_size=self.cell_size,
                line_length=line_length_pixels,
                ttype=ttype,
                direction=direction
            )
            # Точка привязки TransistorItem — это центр нижней грани квадрата →
            # поэтому при создании нам нужно поставить его так, чтобы точка (0,0) внутри
            # TransistorItem («центр низа») оказалась в (x, y) в сценных координатах.
            # У TransistorItem локально квадрат рисуется от (-20,0) до (+20,40) (step=40),
            # а точка привязки — (0,0), так что достаточно:
            t_item.setPos(QtCore.QPointF(x, y))
            t_item.setData(0, "transistor")
            self.scene.addItem(t_item)

        # 11) Перераспределяем элементы по ячейкам и рисуем их границы
        if hasattr(self, "cell_manager") and self.cell_manager is not None:
            self.cell_manager.assign_elements_to_cells()
            self.cell_manager.draw_cell_borders()

        # 12) Обновляем панель свойств (чтобы ничего не осталось выделенным старого)
        self.update_properties_panel()

        QtWidgets.QMessageBox.information(self, "Успех", f"Ячейка «{cell_name}» создана успешно")
        print(f"Ячейка «{cell_name}» создана")

    def copy_cell(self, original_cell, direction="offset"):
        # Вычисляем координаты новой ячейки в зависимости от направления
        if direction == "x":
            dx = original_cell.x2 - original_cell.x1
            dy = 0
        elif direction == "y":
            dx = 0
            dy = original_cell.y2 - original_cell.y1
        else:  # "offset"
            dx = 40
            dy = 40

        new_x1 = original_cell.x1 + dx
        new_y1 = original_cell.y1 + dy
        new_x2 = original_cell.x2 + dx
        new_y2 = original_cell.y2 + dy
        offset = QtCore.QPointF(dx, dy)

        new_cell = Cell(new_x1, new_y1, new_x2, new_y2)

        # Копируем элементы
        for item in original_cell.elements:
            new_item = None

            if isinstance(item, QtWidgets.QGraphicsLineItem):
                line = item.line()
                new_line = self.GridSnapLineItem(  # Добавлен self.
                    line.x1() + offset.x(), line.y1() + offset.y(),
                    line.x2() + offset.x(), line.y2() + offset.y(),
                    cell_size=self.cell_size
                )
                new_line.setPen(item.pen())
                new_line.setData(0, item.data(0))
                new_line.setData(1, item.data(1))
                new_line.setData(2, item.data(2))
                new_line.setFlags(item.flags())
                self.scene.addItem(new_line)
                new_item = new_line

            elif isinstance(item, QtWidgets.QGraphicsEllipseItem) and item.data(0) == "contact":
                size = item.data(2)
                new_contact = self.GridSnapEllipseItem(  # Добавлен self.
                    -size / 2, -size / 2,
                    size, size, cell_size=self.cell_size
                )
                new_contact.setPos(item.pos() + offset)
                new_contact.setBrush(item.brush())
                new_contact.setPen(item.pen())
                new_contact.setData(0, "contact")
                new_contact.setData(1, item.data(1))
                new_contact.setData(2, size)
                new_contact.setFlags(item.flags())
                self.scene.addItem(new_contact)
                new_item = new_contact

            elif isinstance(item, CommentTextItem):
                new_comment = CommentTextItem()
                new_comment.setPlainText(item.toPlainText())
                new_comment.setPos(item.pos() + offset)
                self.scene.addItem(new_comment)
                new_item = new_comment

            if new_item:
                new_cell.add_element(new_item)

        # Отобразим границу скопированной ячейки
        new_cell.draw_border(self.scene)

        print(f"Ячейка скопирована: ({new_cell.x1}, {new_cell.y1}) – ({new_cell.x2}, {new_cell.y2})")

        if hasattr(self, 'cell_manager'):
            self.cell_manager.cells.append(new_cell)
            self.cell_manager.draw_cell_borders()
            self.cell_manager.assign_elements_to_cells()
            self.cell_comment_manager.update_comments(
                self.cell_manager.columns,
                self.cell_manager.rows
            )

    def show_transistor_properties(self, transistor):
        """
        Отображает панель свойств для TransistorItem.
        Здесь можно редактировать длину центральной линии, тип (TP/TN) и направление.
        Длина настраивается по шагам в 20 пикселей (semi_step).
        """
        self.clear_properties_panel()
        self.properties_label.show()

        # Константа для шага (полушаг)
        SEMI_STEP = 20

        # --- Длина линии ---
        length_label = QtWidgets.QLabel("Длина линии:")
        self.properties_layout.addWidget(length_label)

        length_spin = QtWidgets.QSpinBox()
        length_spin.setRange(0, 500)  # 0-500 шагов = 0-10000 пикселей

        # Преобразуем текущую длину в пикселях в количество шагов
        current_steps = transistor.line_length // SEMI_STEP
        length_spin.setValue(current_steps)

        self.properties_layout.addWidget(length_spin)

        def on_length_changed():
            # Сохраняем старую область для очистки - используем максимально возможную область
            max_line_length = 500 * SEMI_STEP  # Максимально возможная длина
            half = transistor.step / 2
            margin = 10

            # Создаем максимально возможную область для очистки
            if transistor.direction in ["NORTH", "SOUTH"]:
                # Вертикальная ориентация
                max_rect = QtCore.QRectF(
                    -half - margin,
                    -max_line_length - margin,
                    transistor.step + 2 * margin,
                    transistor.step + max_line_length + 2 * margin
                )
            else:  # EAST, WEST
                # Горизонтальная ориентация
                max_rect = QtCore.QRectF(
                    -max_line_length - margin,
                    -half - margin,
                    transistor.step + max_line_length + 2 * margin,
                    transistor.step + 2 * margin
                )

            old_scene_rect = transistor.mapRectToScene(max_rect)

            # Обновляем длину линии
            steps = length_spin.value()
            new_len = steps * SEMI_STEP

            # Уведомляем о предстоящем изменении геометрии
            transistor.prepareGeometryChange()

            # Изменяем длину
            transistor.line_length = new_len

            # Принудительно обновляем большую область сцены для очистки старого изображения
            if hasattr(transistor, 'scene') and transistor.scene():
                transistor.scene().update(old_scene_rect)

            # Получаем новую область и тоже её обновляем
            new_bounding_rect = transistor.boundingRect()
            new_scene_rect = transistor.mapRectToScene(new_bounding_rect)

            if hasattr(transistor, 'scene') and transistor.scene():
                transistor.scene().update(new_scene_rect)

            # Принудительно обновляем элемент
            transistor.update()

        length_spin.valueChanged.connect(on_length_changed)
        self.property_widgets["trans_length"] = length_spin

        # --- Тип транзистора ---
        type_label = QtWidgets.QLabel("Тип транзистора:")
        self.properties_layout.addWidget(type_label)

        type_combo = QtWidgets.QComboBox()
        type_combo.addItems(["TP", "TN"])
        idx = 0 if transistor.ttype == "TP" else 1
        type_combo.setCurrentIndex(idx)
        self.properties_layout.addWidget(type_combo)

        def on_type_changed():
            transistor.ttype = type_combo.currentText()
            transistor.update()

        type_combo.currentIndexChanged.connect(on_type_changed)
        self.property_widgets["trans_type"] = type_combo

        # --- НОВОЕ: Направление транзистора ---
        direction_label = QtWidgets.QLabel("Направление:")
        self.properties_layout.addWidget(direction_label)

        direction_combo = QtWidgets.QComboBox()
        direction_combo.addItems(["NORTH", "SOUTH", "EAST", "WEST"])

        # Устанавливаем текущее направление
        current_direction = getattr(transistor, 'direction', 'NORTH')
        direction_index = ["NORTH", "SOUTH", "EAST", "WEST"].index(current_direction)
        direction_combo.setCurrentIndex(direction_index)

        self.properties_layout.addWidget(direction_combo)

        def on_direction_changed():
            # Создаем максимально возможную область для очистки в обеих ориентациях
            max_line_length = 500 * SEMI_STEP
            half = transistor.step / 2
            margin = 10

            # Создаем область, которая покрывает все возможные направления
            max_rect = QtCore.QRectF(
                -max_line_length - margin,
                -max_line_length - margin,
                transistor.step + 2 * max_line_length + 2 * margin,
                transistor.step + 2 * max_line_length + 2 * margin
            )

            old_scene_rect = transistor.mapRectToScene(max_rect)

            # Уведомляем о предстоящем изменении геометрии
            transistor.prepareGeometryChange()

            # Устанавливаем новое направление
            transistor.direction = direction_combo.currentText()

            # Принудительно обновляем большую область для очистки
            if hasattr(transistor, 'scene') and transistor.scene():
                transistor.scene().update(old_scene_rect)

            # Получаем новую область и обновляем её
            new_bounding_rect = transistor.boundingRect()
            new_scene_rect = transistor.mapRectToScene(new_bounding_rect)

            if hasattr(transistor, 'scene') and transistor.scene():
                transistor.scene().update(new_scene_rect)

            # Принудительно обновляем элемент
            transistor.update()

        direction_combo.currentIndexChanged.connect(on_direction_changed)
        self.property_widgets["trans_direction"] = direction_combo

        self.properties_layout.addStretch()

    def show_line_properties(self, line_item):
        self.clear_properties_panel()
        self.properties_label.show()

        # Заголовок
        title = QtWidgets.QLabel("Свойства линии")
        title.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Weight.Bold))
        self.properties_layout.addWidget(title)

        # --- Логическая Толщина ---
        width_label = QtWidgets.QLabel("Толщина (логическая):")
        width_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        self.properties_layout.addWidget(width_label)

        width_spin = QtWidgets.QSpinBox()
        width_spin.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        width_spin.setRange(-3, 10)
        width_spin.setValue(line_item.data(2))  # логическая толщина
        self.properties_layout.addWidget(width_spin)

        # --- Материал ---
        material_label = QtWidgets.QLabel("Материал:")
        material_label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        self.properties_layout.addWidget(material_label)

        material_combo = QtWidgets.QComboBox()
        # Делаем ComboBox редактируемым
        material_combo.setEditable(True)
        material_combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        material_combo.addItems(list(self.LINE_MATERIALS.keys()))
        current_material = line_item.data(1) or "M2"
        material_combo.setCurrentText(current_material)
        self.properties_layout.addWidget(material_combo)

        # --- Функция обновления стиля ---
        def update_line():
            material = material_combo.currentText()
            logic_width = width_spin.value()

            # Обновляем внутренние данные
            line_item.setData(1, material)
            line_item.setData(2, logic_width)

            # Если материал есть в предустановленных, используем его параметры
            if material in self.LINE_MATERIALS:
                self.set_line_style(line_item, material, logic_width)
            else:
                # Для пользовательских материалов можно задать стандартный стиль
                # Например, сплошная линия с базовой толщиной
                pen = QtGui.QPen()
                pen.setColor(QtGui.QColor("black"))
                pen.setWidth(max(1, logic_width))
                pen.setStyle(QtCore.Qt.PenStyle.SolidLine)
                line_item.setPen(pen)

        # Обрабатываем как изменение индекса, так и редактирование текста
        material_combo.currentIndexChanged.connect(update_line)
        material_combo.editTextChanged.connect(update_line)
        width_spin.valueChanged.connect(update_line)

        self.property_widgets["material"] = material_combo
        self.property_widgets["width"] = width_spin

        self.properties_layout.addStretch()

    def show_vline_properties(self, line_item):
        """
        ИСПРАВЛЕНО: добавлена защита от None и улучшена обработка ошибок
        """
        try:
            self.clear_properties_panel()
            self.properties_label.show()

            # Заголовок
            title = QtWidgets.QLabel("Свойства виртуальной линии")
            title.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Weight.Bold))
            self.properties_layout.addWidget(title)

            # Текущее имя с защитой от None
            name_label = QtWidgets.QLabel("Имя линии:")
            self.properties_layout.addWidget(name_label)

            current_name = line_item.data(1) if line_item.data(1) is not None else ""
            name_edit = QtWidgets.QLineEdit(str(current_name))
            self.properties_layout.addWidget(name_edit)

            def rename_vline():
                try:
                    new_name = name_edit.text().strip()
                    if new_name:  # Разрешаем пустые имена, если нужно
                        line_item.setData(1, new_name)
                except Exception as e:
                    print(f"Ошибка при переименовании виртуальной линии: {e}")

            name_edit.editingFinished.connect(rename_vline)

            self.visibility_btn = QtWidgets.QPushButton()
            self.update_button_text()
            self.visibility_btn.clicked.connect(self.toggle_vlines)
            self.properties_layout.addWidget(self.visibility_btn)

            self.properties_layout.addStretch()

        except Exception as e:
            print(f"Ошибка в show_vline_properties: {e}")
            self.clear_properties_panel()

    def show_vline_controls(self):
        """
        Показывает простую панель с кнопкой переключения видимости
        """
        self.clear_properties_panel()
        self.properties_label.show()

        # Простая кнопка переключения
        self.visibility_btn = QtWidgets.QPushButton()
        self.update_button_text()
        self.visibility_btn.clicked.connect(self.toggle_vlines)
        self.properties_layout.addWidget(self.visibility_btn)

        self.properties_layout.addStretch()

    def update_button_text(self):
        """
        Обновляет текст кнопки
        """
        if hasattr(self, 'visibility_btn'):
            if self.vlines_visible:
                self.visibility_btn.setText("Скрыть виртуальные линии")
            else:
                self.visibility_btn.setText("Показать виртуальные линии")

    def toggle_vlines(self):
        """
        Переключает видимость всех виртуальных линий одной строчкой
        """
        self.vlines_visible = not self.vlines_visible

        # Простой перебор и установка видимости
        for item in self.scene.items():
            if (isinstance(item, QtWidgets.QGraphicsLineItem) and
                    item.data(0) == "vline"):
                item.setVisible(self.vlines_visible)

        self.update_button_text()

    def set_tool(self, tool_id):
        self.clear_properties_panel()
        self.current_tool = tool_id
        if tool_id == "vline":
            self.show_vline_controls()
        elif tool_id == "view":
            self.properties_label.show()
        else:
            self.properties_label.hide()
        print(f"Выбран инструмент: {tool_id}")

    def draw_grid(self):
        light_pen = QtGui.QPen(QtGui.QColor("#e8eaed"))
        light_pen.setWidth(0)

        dark_pen = QtGui.QPen(QtGui.QColor("lightgray"))
        dark_pen.setWidth(0)

        for x in range(-4000, 8000, self.cell_size):
            pen = dark_pen if x % self.step == 0 else light_pen
            line = self.scene.addLine(x, -4000, x, 8000, pen)
            line.setData(0, "grid")

        for y in range(-4000, 8000, self.cell_size):
            pen = dark_pen if y % self.step == 0 else light_pen
            line = self.scene.addLine(-4000, y, 8000, y, pen)
            line.setData(0, "grid")

    def draw_axes(self):
        axis_pen = QtGui.QPen(QtGui.QColor('#697c85'))
        axis_pen.setWidth(2)

        x_axis = self.scene.addLine(self.min_x, 0, self.max_x, 0, axis_pen)
        y_axis = self.scene.addLine(0, self.min_y, 0, self.max_y, axis_pen)

        for axis in [x_axis, y_axis]:
            axis.setData(0, "axis")
            axis.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            axis.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        font = QtGui.QFont("Arial", 8)
        step = self.step


        # Отметки по X с шагом self.step
        for x in range(self.min_x, self.max_x + 1, (self.step*5)):
            tick = self.scene.addLine(x, -5, x, 5, axis_pen)
            tick.setData(0, "axis_mark")
            tick.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            tick.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

            if x != 0 and (x // self.step) % 5 == 0:  # Только для 5, 10, 15, ...
                text = self.scene.addText(str(x // self.step), font)
                text.setDefaultTextColor(QtGui.QColor('#2d3538'))
                text.setPos(x - 10, -10)
                text.setData(0, "axis_label")
                text.setScale(1)
                text.setTransform(QtGui.QTransform().scale(1, -1))
                text.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                text.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        # Отметки по Y с шагом self.step
        for y in range(self.min_y, self.max_y + 1, self.step*5):
            tick = self.scene.addLine(-5, y, 5, y, axis_pen)
            tick.setData(0, "axis_mark")
            tick.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            tick.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

            if y != 0 and (y // self.step) % 5 == 0:
                text = self.scene.addText(str(y // self.step), font)
                text.setDefaultTextColor(QtGui.QColor('#2d3538'))
                text.setPos(-30, y - 8)
                text.setData(0, "axis_label")
                text.setScale(1)
                text.setTransform(QtGui.QTransform().scale(1, -1))
                text.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                text.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

    def snap_to_grid(self, pos):
        """Привязка к сетке с учетом границ"""
        x = max(self.min_x, min(self.max_x,
                                round(pos.x() / self.cell_size) * self.cell_size))
        y = max(self.min_y, min(self.max_y,
                                round(pos.y() / self.cell_size) * self.cell_size))
        return QtCore.QPointF(x, y)

    def save_state_for_undo(self):
        snapshot = []
        for item in self.scene.items():
            if hasattr(item, 'data'):
                item_type = item.data(0)
                if item_type in ["grid", "axis", "axis_mark", "axis_label"]:
                    continue

            snapshot.append(item)
        self.undo_stack.append(snapshot)

    def undo_last_action(self):
        if not self.undo_stack:
            QtWidgets.QMessageBox.information(self, "Undo", "Нет действий для отмены.")
            return

        last_snapshot = self.undo_stack.pop()

        # Удалить всё, кроме сетки и осей
        self.toolbar.clear_all_elements()

        # Восстановить элементы из снимка
        for item in last_snapshot:
            self.scene.addItem(item)

        if hasattr(self, 'cell_manager'):
            self.cell_manager.assign_elements_to_cells()
            self.cell_manager.draw_cell_borders()

    def eventFilter(self, source, event):
        # 1) Средняя кнопка — панорамирование
        if self.handle_middle_mouse_pan(event):
            return True

        # 2) Правая кнопка — перемещение существующих элементов (контактов, проводов, ячеек и пр.)
        if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.RightButton:
            scene_pos = self.view.mapToScene(event.pos())
            item = self.scene.itemAt(scene_pos, self.view.transform())
            if item:
                self.moving_item = item
                self.move_start_pos = scene_pos
                self.view.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                return True

        elif event.type() == QtCore.QEvent.Type.MouseMove and self.moving_item and (
                event.buttons() & QtCore.Qt.MouseButton.RightButton):
            scene_pos = self.view.mapToScene(event.pos())
            delta = scene_pos - self.move_start_pos
            grid_snap_x = round(delta.x() / self.cell_size) * self.cell_size
            grid_snap_y = round(delta.y() / self.cell_size) * self.cell_size
            self.moving_item.moveBy(grid_snap_x, grid_snap_y)
            self.move_start_pos = scene_pos
            return True

        elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.RightButton:
            self.moving_item = None
            self.move_start_pos = None
            self.view.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            return True

        # 3) Левая кнопка — разные инструменты
        if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self.current_tool == "delete":
                self.handle_delete_click(event)
                return True

            elif self.current_tool == "line":
                # заменили старый вызов line_creation → новый
                self.line_creation_with_auto_vlines(event)
                return True

            elif self.current_tool == "view":
                self.properties_label.show()
                return True

            elif self.current_tool == "comment":
                scene_pos = self.view.mapToScene(event.pos())
                self.create_comment(scene_pos)
                return True

            elif self.current_tool == "contact":
                # заменили старый create_contact → новый
                scene_pos = self.snap_to_grid(self.view.mapToScene(event.pos()))
                self.create_contact_with_auto_vlines(scene_pos)
                return True

            elif self.current_tool == "column":
                scene_pos = self.view.mapToScene(event.pos())
                self.create_column(scene_pos)
                # после создания столбца сразу пересчитываем всё:
                self.cell_manager.assign_elements_to_cells()
                self.update_virtual_lines_on_element_change()
                return True

            elif self.current_tool == "row":
                scene_pos = self.view.mapToScene(event.pos())
                self.create_row(scene_pos)
                self.cell_manager.assign_elements_to_cells()
                self.update_virtual_lines_on_element_change()
                return True

            elif self.current_tool == "vline":
                self.vline_creation(event)
                return True


            elif self.current_tool == "transistor":
                return self.handle_transistor_creation(event)

            else:
                self.last_pos = event.pos()

        # 4) MouseMove — обновление временных линий / панорамирование
        elif event.type() == QtCore.QEvent.Type.MouseMove:
            # 4.1) Обычная линия
            if self.current_tool == "line" and getattr(self, "line_start", None) and getattr(self, "temp_line", None):
                scene_pos = self.snap_to_grid(self.view.mapToScene(event.pos()))
                dx = abs(scene_pos.x() - self.line_start.x())
                dy = abs(scene_pos.y() - self.line_start.y())
                if dx > dy:
                    scene_pos.setY(self.line_start.y())
                else:
                    scene_pos.setX(self.line_start.x())
                self.temp_line.setLine(
                    self.line_start.x(), self.line_start.y(),
                    scene_pos.x(), scene_pos.y()
                )
                return True

            # 4.2) Виртуальная линия
            elif self.current_tool == "vline" and getattr(self, "drawing_temp", False):
                if getattr(self, "line_start", None) and getattr(self, "temp_line", None):
                    scene_pos = self.snap_to_grid(self.view.mapToScene(event.pos()))
                    x0, y0 = self.line_start.x(), self.line_start.y()
                    dx = abs(scene_pos.x() - x0)
                    dy = abs(scene_pos.y() - y0)
                    if dx >= dy:
                        new_line = QtCore.QLineF(x0, y0, scene_pos.x(), y0)
                    else:
                        new_line = QtCore.QLineF(x0, y0, x0, scene_pos.y())
                    self.temp_line.setLine(new_line)
                return True

            # 4.3) Панорамирование ладонью (move tool)


        # 5) Отпускание левой кнопки
        elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
            # 5.1) Завершили обычную линию
            if self.current_tool == "line" and getattr(self, "temp_line", None):
                ln = self.temp_line.line()
                scene_pos = self.snap_to_grid(self.view.mapToScene(event.pos()))
                x0, y0 = self.line_start.x(), self.line_start.y()
                dx = abs(scene_pos.x() - x0)
                dy = abs(scene_pos.y() - y0)
                if dx > dy:
                    end_point = QtCore.QPointF(scene_pos.x(), y0)
                else:
                    end_point = QtCore.QPointF(x0, scene_pos.y())
                self.temp_line.setLine(QtCore.QLineF(x0, y0, end_point.x(), end_point.y()))

                # **Главное: обновляем ячейки и создаем виртуальные линии**
                self.cell_manager.assign_elements_to_cells()
                self.update_virtual_lines_on_element_change()

                self.temp_line = None
                self.line_start = None
                return True

            # 5.2) Завершили виртуальную линию
            elif self.current_tool == "vline" and getattr(self, "drawing_temp", False):
                self.drawing_temp = False
                if getattr(self, "temp_line", None):
                    ln = self.temp_line.line()
                    if ln.x1() == ln.x2() and ln.y1() == ln.y2():
                        self.scene.removeItem(self.temp_line)
                    else:
                        scene_pos = self.snap_to_grid(self.view.mapToScene(event.pos()))
                        x0, y0 = self.line_start.x(), self.line_start.y()
                        dx = abs(scene_pos.x() - x0)
                        dy = abs(scene_pos.y() - y0)
                        if dx > dy:
                            end_point = QtCore.QPointF(scene_pos.x(), y0)
                        else:
                            end_point = QtCore.QPointF(x0, scene_pos.y())
                        self.temp_line.setLine(QtCore.QLineF(x0, y0, end_point.x(), end_point.y()))

                        # Регистрируем пересечение для ручной vline
                        self.cell_manager.register_vline_intersections(self.temp_line)

                    self.temp_line = None
                    self.line_start = None
                return True

        # 6) Колесо мыши — масштабирование View
        elif event.type() == QtCore.QEvent.Type.Wheel and source is self.view.viewport():
            zoom_in_factor = 1.15
            zoom_out_factor = 1 / zoom_in_factor

            if event.angleDelta().y() > 0:
                zoom_factor = zoom_in_factor
            else:
                zoom_factor = zoom_out_factor

            current_scale = self.view.transform().m11()
            if event.angleDelta().y() > 0:
                if current_scale < 5:
                    self.view.scale(zoom_factor, zoom_factor)
            else:
                if current_scale > 0.25:
                    self.view.scale(zoom_factor, zoom_factor)
            return super().eventFilter(source, event)

        return super().eventFilter(source, event)

    def set_line_style(self, line_item, material_name, logic_width):
        """Устанавливает стиль линии и точек"""
        material = self.LINE_MATERIALS.get(material_name, self.LINE_MATERIALS["M2"])
        color = QtGui.QColor(material["color"])
        style = material["style"]
        z = material["z"]

        # Линейное преобразование: логическая -3...10 → визуальная 3...16
        visual_width = logic_width + 6

        pen = QtGui.QPen(color)
        pen.setWidth(max(1, visual_width))  # минимальная ширина = 1 px
        pen.setStyle(style)

        line_item.setPen(pen)  # Теперь setPen также установит цвет точек
        line_item.setZValue(z)

    def line_creation(self, event):
        if self.active_layer not in [0, 1]:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Выбран не тот слой!")
            return
        self.save_state_for_undo()
        scene_pos = self.snap_to_grid(self.view.mapToScene(event.pos()))
        self.line_start = scene_pos

        self.temp_line = GridSnapLineItem(
            scene_pos.x(), scene_pos.y(),
            scene_pos.x(), scene_pos.y()
        )

        default_material = "M2"
        default_width = -3

        self.set_line_style(self.temp_line, default_material, default_width)

        self.temp_line.setData(0, "wire")
        self.temp_line.setData(1, default_material)
        self.temp_line.setData(2, default_width)

        flags = QtWidgets.QGraphicsItem.GraphicsItemFlag
        self.temp_line.setFlag(flags.ItemIsSelectable, True)
        self.temp_line.setFlag(flags.ItemIsMovable, True)

        self.scene.addItem(self.temp_line)
        if hasattr(self, 'cell_manager'):
            self.cell_manager.assign_elements_to_cells()

    def auto_create_virtual_lines(self):
        """
        Автоматически создаёт виртуальные линии:
         1) Удаляет все старые vline из сцены
         2) Проходит по всем «wire» и «contact» и собирает список vline_data
         3) Для каждого vline_data формирует имя по схеме <source>_<cell.name>_<edge_type>(N)
         4) Рисует GridSnapLineItem и сразу же регистрирует его пересечения в ячейках
        """
        print("Создание виртуальных линий...")
        self.clear_virtual_lines()

        line_counters = defaultdict(int)
        created_vlines = []

        all_vlines_data = []

        # 1) Собираем vline_data из всех проводов
        for item in self.scene.items():
            if isinstance(item, QtWidgets.QGraphicsLineItem) and hasattr(item, 'data') and item.data(0) == "wire":
                all_vlines_data.extend(self.analyze_element_for_virtual_lines(item, None))

        # 2) Собираем vline_data из всех контактов
        for item in self.scene.items():
            if isinstance(item, QtWidgets.QGraphicsEllipseItem) and hasattr(item, 'data') and item.data(0) == "contact":
                all_vlines_data.extend(self.analyze_element_for_virtual_lines(item, None))

        # 3) Формируем имена и создаём сами QGraphicsLineItem
        for vline_data in all_vlines_data:
            cell = vline_data.get('cell')
            if cell is None:
                continue
            source = vline_data.get('source', 'unknown')
            edge_type = vline_data.get('edge_type', 'unknown')

            key = f"{source}_{cell.name}_{edge_type}"
            line_counters[key] += 1
            suffix = "" if line_counters[key] == 1 else f"({line_counters[key] - 1})"
            vline_data['name'] = f"{key}{suffix}"

            vline = self.create_virtual_line_from_data(vline_data)
            if vline:
                created_vlines.append(vline)

        print(f"Создано {len(created_vlines)} виртуальных линий")
        return created_vlines

    def clear_virtual_lines(self):
        """Удаляет все существующие виртуальные линии"""
        items_to_remove = []
        for item in self.scene.items():
            if (isinstance(item, QtWidgets.QGraphicsLineItem) and
                    hasattr(item, 'data') and item.data(0) == "vline"):
                items_to_remove.append(item)

        for item in items_to_remove:
            self.scene.removeItem(item)

    def analyze_element_for_virtual_lines(self, element, cell=None):
        """
        Возвращает список vline_data для данного element (wire или contact).
        Если cell=None, означает «проверяем все ячейки сразу» (для контактов оптимальнее так).
        """
        virtual_lines_data = []
        eps = 2.0

        if not hasattr(element, 'data'):
            return virtual_lines_data

        element_type = element.data(0)
        source_name = element.data(1) or "unknown"

        # 1) Провода (wire)
        if element_type == "wire" and isinstance(element, QtWidgets.QGraphicsLineItem):
            ln = element.line()
            pos = element.scenePos()
            p1 = QtCore.QPointF(ln.x1() + pos.x(), ln.y1() + pos.y())
            p2 = QtCore.QPointF(ln.x2() + pos.x(), ln.y2() + pos.y())

            # Если cell передан, проверяем только его; иначе — все ячейки
            cells_to_check = [cell] if cell else self.cell_manager.cells

            for point in (p1, p2):
                for c in cells_to_check:
                    if c is None:
                        continue
                    vline_data = self.check_point_on_cell_edge(point, c, eps)
                    if vline_data:
                        vline_data["source"] = source_name
                        if not self.virtual_line_exists_at_position(vline_data, virtual_lines_data):
                            virtual_lines_data.append(vline_data)

        # 2) Контакты (contact)
        elif element_type == "contact" and isinstance(element, QtWidgets.QGraphicsEllipseItem):
            center = element.scenePos()
            cx, cy = center.x(), center.y()

            # Если cell передан, проверяем только его грань; иначе — все ячейки
            cells_to_check = [cell] if cell else self.cell_manager.cells

            for c in cells_to_check:
                if c is None:
                    continue
                # проверяем по четырём возможным граням
                # если центр лежит ровно на левой/правой/нижней/верхней грани, создаём один
                # vline_data с горизонталью (для левой/правой) или вертикалью (для нижней/верхней).
                # edge='left' и 'right' → горизонтальная линия; edge='bottom' и 'top' → вертикальная.

                # левая грань
                if abs(cx - c.x1) < eps and (c.y1 <= cy <= c.y2):
                    vline_data = {
                        'start_point': QtCore.QPointF(c.x1, cy),
                        'end_point':   QtCore.QPointF(c.x2, cy),
                        'edge_type':   'lft',
                        'cell':        c,
                        'source':      source_name
                    }
                    if not self.virtual_line_exists_at_position(vline_data, virtual_lines_data):
                        virtual_lines_data.append(vline_data)

                # правая грань
                if abs(cx - c.x2) < eps and (c.y1 <= cy <= c.y2):
                    vline_data = {
                        'start_point': QtCore.QPointF(c.x1, cy),
                        'end_point':   QtCore.QPointF(c.x2, cy),
                        'edge_type':   'rht',
                        'cell':        c,
                        'source':      source_name
                    }
                    if not self.virtual_line_exists_at_position(vline_data, virtual_lines_data):
                        virtual_lines_data.append(vline_data)

                # нижняя грань
                if abs(cy - c.y1) < eps and (c.x1 <= cx <= c.x2):
                    vline_data = {
                        'start_point': QtCore.QPointF(cx, c.y1),
                        'end_point':   QtCore.QPointF(cx, c.y2),
                        'edge_type':   'btm',
                        'cell':        c,
                        'source':      source_name
                    }
                    if not self.virtual_line_exists_at_position(vline_data, virtual_lines_data):
                        virtual_lines_data.append(vline_data)

                # верхняя грань
                if abs(cy - c.y2) < eps and (c.x1 <= cx <= c.x2):
                    vline_data = {
                        'start_point': QtCore.QPointF(cx, c.y1),
                        'end_point':   QtCore.QPointF(cx, c.y2),
                        'edge_type':   'top',
                        'cell':        c,
                        'source':      source_name
                    }
                    if not self.virtual_line_exists_at_position(vline_data, virtual_lines_data):
                        virtual_lines_data.append(vline_data)

        return virtual_lines_data

    def virtual_line_exists_at_position(self, new_vline_data, existing_data_list):
        """Проверяет, существует ли уже виртуальная линия в данной позиции"""
        eps = 1.0
        new_start = new_vline_data['start_point']
        new_end = new_vline_data['end_point']

        for existing in existing_data_list:
            existing_start = existing['start_point']
            existing_end = existing['end_point']

            # Проверяем совпадение координат (с учетом направления)
            if ((abs(new_start.x() - existing_start.x()) < eps and
                 abs(new_start.y() - existing_start.y()) < eps and
                 abs(new_end.x() - existing_end.x()) < eps and
                 abs(new_end.y() - existing_end.y()) < eps) or
                    (abs(new_start.x() - existing_end.x()) < eps and
                     abs(new_start.y() - existing_end.y()) < eps and
                     abs(new_end.x() - existing_start.x()) < eps and
                     abs(new_end.y() - existing_start.y()) < eps)):
                return True

        return False

    def check_point_on_cell_edge(self, point, cell, eps=2.0):
        """
        Проверяет, находится ли точка на краю ячейки
        Возвращает данные для создания виртуальной линии или None
        """
        x, y = point.x(), point.y()

        # Проверяем левый край (x = cell.x1)
        if abs(x - cell.x1) < eps and cell.y1 <= y <= cell.y2:
            return {
                'start_point': QtCore.QPointF(cell.x1, y),
                'end_point': QtCore.QPointF(cell.x2, y),
                'edge_type': 'lft',
                'cell': cell,
                'original_point': point
            }

        # Проверяем правый край (x = cell.x2)
        if abs(x - cell.x2) < eps and cell.y1 <= y <= cell.y2:
            return {
                'start_point': QtCore.QPointF(cell.x2, y),
                'end_point': QtCore.QPointF(cell.x1, y),
                'edge_type': 'rht',
                'cell': cell,
                'original_point': point
            }

        # Проверяем нижний край (y = cell.y1)
        if abs(y - cell.y1) < eps and cell.x1 <= x <= cell.x2:
            return {
                'start_point': QtCore.QPointF(x, cell.y1),
                'end_point': QtCore.QPointF(x, cell.y2),
                'edge_type': 'btm',
                'cell': cell,
                'original_point': point
            }

        # Проверяем верхний край (y = cell.y2)
        if abs(y - cell.y2) < eps and cell.x1 <= x <= cell.x2:
            return {
                'start_point': QtCore.QPointF(x, cell.y2),
                'end_point': QtCore.QPointF(x, cell.y1),
                'edge_type': 'top',
                'cell': cell,
                'original_point': point
            }

        return None

    def create_virtual_line_from_data(self, vline_data):
        """
        Создаёт виртуальную линию из vline_data, который уже содержит ключ 'name'.
        """
        try:
            start = vline_data['start_point']
            end = vline_data['end_point']
            vline_name = vline_data['name']

            vline = GridSnapLineItem(
                start.x(), start.y(),
                end.x(), end.y(),
                cell_size=self.cell_size
            )

            pen = QtGui.QPen(QtGui.QColor("red"))
            pen.setWidth(2)
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            vline.setPen(pen)

            vline.setData(0, "vline")
            vline.setData(1, vline_name)

            flags = QtWidgets.QGraphicsItem.GraphicsItemFlag
            vline.setFlag(flags.ItemIsSelectable, True)
            vline.setFlag(flags.ItemIsMovable, True)
            vline.setZValue(10)
            vline.setVisible(self.vlines_visible)

            self.scene.addItem(vline)

            # Зарегистрируем в ячейках
            if hasattr(self, 'cell_manager'):
                self.cell_manager.register_vline_intersections(vline)

            print(f"Создана виртуальная линия: {vline_name}")
            return vline

        except Exception as e:
            print(f"Ошибка при создании виртуальной линии: {e}")
            import traceback; traceback.print_exc()
            return None

    def update_virtual_lines_on_element_change(self):
        """
        Обновляет виртуальные линии при любом изменении «обычных» элементов:
        сначала расставляем провода/контакты по ячейкам, затем рисуем vline.
        """
        if hasattr(self, 'cell_manager'):
            self.cell_manager.assign_elements_to_cells()
            self.auto_create_virtual_lines()

    def vline_creation(self, event):
        """
        Автоматическое создание виртуальных линий вместо ручного рисования
        """
        # Сохраняем состояние для undo
        self.save_state_for_undo()

        # Запускаем автоматическое создание
        created_lines = self.auto_create_virtual_lines()

        if created_lines:
            print(f"Виртуальные линии созданы автоматически: {len(created_lines)} шт.")
        else:
            print("Не найдено элементов для создания виртуальных линий")

    def line_creation_with_auto_vlines(self, event):
        """Создание линии с автоматическим обновлением виртуальных линий и точками на концах"""
        if self.active_layer not in [0, 1]:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Выбран не тот слой!")
            return

        # Сохраняем Undo
        self.save_state_for_undo()

        # Получаем точку, привязанную к сетке
        scene_pos = self.snap_to_grid(self.view.mapToScene(event.pos()))
        self.line_start = scene_pos

        # Создаем временную линию С ТОЧКАМИ (используем GridSnapLineItemWithDots)
        self.temp_line = GridSnapLineItemWithDots(
            scene_pos.x(), scene_pos.y(),
            scene_pos.x(), scene_pos.y(),
            cell_size=self.cell_size
        )

        default_material = "M2"
        default_width = -3

        self.set_line_style(self.temp_line, default_material, default_width)
        self.temp_line.setData(0, "wire")
        self.temp_line.setData(1, default_material)
        self.temp_line.setData(2, default_width)

        flags = QtWidgets.QGraphicsItem.GraphicsItemFlag
        self.temp_line.setFlag(flags.ItemIsSelectable, True)
        self.temp_line.setFlag(flags.ItemIsMovable, True)

        self.scene.addItem(self.temp_line)
        self.drawing_temp = True

    def create_contact_with_auto_vlines(self, position):
        """
        ВСЕГДА создаёт только одиночный GridSnapEllipseItem.
        Двухточечный режим доступен только через свойства.
        """
        self.save_state_for_undo()

        default_material = "CPA"
        contact_size = 10  # базовый диаметр, можно потом менять в свойствах

        # ————— ВСЕГДА СОЗДАЁМ ОДИНОЧНЫЙ КОНТАКТ —————
        contact = GridSnapEllipseItem(
            -contact_size / 2, -contact_size / 2,
            contact_size, contact_size,
            cell_size=self.cell_size
        )
        contact.setPos(position)

        params = self.CONTACT_MATERIALS[default_material]
        contact.setBrush(QtGui.QBrush(QtGui.QColor(params["color"])))
        contact.setZValue(params["z"])

        contact.setData(0, "contact")
        contact.setData(1, default_material)
        contact.setData(2, contact_size)

        pen = QtGui.QPen(QtGui.QColor("black"))
        pen.setWidth(1)
        contact.setPen(pen)

        contact.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        contact.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

        self.scene.addItem(contact)

        # После добавления контакта:
        self.cell_manager.assign_elements_to_cells()
        self.update_virtual_lines_on_element_change()

        return contact

    def create_transistor(self, position):
        """Создает TransistorItem с поддержкой направления, привязывает к сетке и помечает data(0)="transistor"."""
        try:
            print("Начинаем создание транзистора...")

            # Проверяем входные параметры
            if not hasattr(self, 'cell_size'):
                print("Ошибка: отсутствует cell_size")
                return None

            if not hasattr(self, 'scene'):
                print("Ошибка: отсутствует scene")
                return None

            # Создаем транзистор с длиной линии по умолчанию в 2 шага (40 пикселей)
            default_line_length = self.cell_size * 2  # 40 пикселей = 2 шага по 20

            t = TransistorItem(
                cell_size=self.cell_size,
                line_length=default_line_length,
                ttype="TP",
                direction="NORTH"  # Направление по умолчанию
            )

            print("TransistorItem создан")

            # Устанавливаем позицию
            snapped_pos = self.snap_to_grid(position)
            t.setPos(snapped_pos)
            print(f"Позиция установлена: {snapped_pos}")

            # Устанавливаем высокий zValue для транзистора
            t.setZValue(10)

            # Устанавливаем данные
            t.setData(0, "transistor")
            print("Данные установлены")

            # Добавляем на сцену
            self.scene.addItem(t)
            print("Элемент добавлен на сцену")

            # Обновляем ячейки и виртуальные линии
            if hasattr(self, 'cell_manager'):
                self.cell_manager.assign_elements_to_cells()
                print("Элементы распределены по ячейкам")

            if hasattr(self, 'update_virtual_lines_on_element_change'):
                self.update_virtual_lines_on_element_change()
                print("Виртуальные линии обновлены")

            print("Транзистор успешно создан")
            return t

        except Exception as e:
            print(f"Ошибка при создании транзистора: {e}")
            import traceback
            traceback.print_exc()
            return None

    def handle_transistor_creation(self, event):
        """Безопасное создание транзистора с обработкой ошибок"""
        try:
            scene_pos = self.snap_to_grid(self.view.mapToScene(event.pos()))
            transistor = self.create_transistor(scene_pos)
            if transistor is None:
                print("Не удалось создать транзистор")
            return True
        except Exception as e:
            print(f"Ошибка в обработчике создания транзистора: {e}")
            traceback.print_exc()
            return True

    def create_comment(self, position):
        self.save_state_for_undo()
        text_item = CommentTextItem()
        text_item.setPos(position)
        self.scene.addItem(text_item)

    def snap_to_grid(self, pos):
        """Модифицированный метод с учетом границ"""
        x = max(self.min_x, min(self.max_x,
                                round(pos.x() / self.cell_size) * self.cell_size))
        y = max(self.min_y, min(self.max_y,
                                round(pos.y() / self.cell_size) * self.cell_size))
        return QtCore.QPointF(x, y)

    def handle_middle_mouse_pan(self, event):
        if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self.view.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            self.last_pos = event.pos()
            return True

        elif event.type() == QtCore.QEvent.Type.MouseMove and self.last_pos and event.buttons() & QtCore.Qt.MouseButton.MiddleButton:
            delta = event.pos() - self.last_pos
            self.view.horizontalScrollBar().setValue(self.view.horizontalScrollBar().value() - delta.x())
            self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().value() - delta.y())
            self.last_pos = event.pos()
            return True

        elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.MiddleButton:
            self.last_pos = None
            self.view.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            return True

        return False

    def clear_properties_panel(self):
        while self.properties_layout.count():
            item = self.properties_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.property_widgets.clear()
        self.properties_label.hide()

        if hasattr(self, 'visibility_btn'):
            delattr(self, 'visibility_btn')

    def create_contact(self, position):
     #   if self.active_layer not in [0, 1]:
      #      QtWidgets.QMessageBox.warning(self, "Ошибка", "Выбран не тот слой!")
       #     return

        self.save_state_for_undo()

        # Используем материал по умолчанию
        default_material = "VIA1"
        contact_size = 10

        contact = GridSnapEllipseItem(
            -contact_size / 2, -contact_size / 2,
            contact_size, contact_size,
            cell_size=self.cell_size
        )
        contact.setPos(position)

        # Устанавливаем свойства из материала
        material = self.CONTACT_MATERIALS[default_material]
        contact.setBrush(QtGui.QBrush(QtGui.QColor(material["color"])))
        contact.setZValue(material["z"])  # Z-значение выше чем у линий

        # Сохраняем параметры в данных
        contact.setData(0, "contact")
        contact.setData(1, default_material)  # Тип материала
        contact.setData(2, contact_size)  # Размер

        pen = QtGui.QPen(QtGui.QColor("black"))
        pen.setWidth(1)
        contact.setPen(pen)

        contact.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        contact.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)


        self.scene.addItem(contact)

        if hasattr(self, 'cell_manager'):
            self.cell_manager.assign_elements_to_cells()

        return contact

    def show_contact_properties(self, contact_item):
        """
        Отображаем панель свойств для выбранного contact_item.
        Добавляем чекбокс «Двухточечный». Если пользователь переключит чекбокс,
        мы пересоздаём контакт в нужном формате.
        """
        self.clear_properties_panel()
        self.properties_label.show()

        # Заголовок
        title = QtWidgets.QLabel("Свойства контакта")
        title.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Weight.Bold))
        self.properties_layout.addWidget(title)

        # --- Двухточечный? (checkbox) ---
        two_label = QtWidgets.QLabel("Двухточечный:")
        self.properties_layout.addWidget(two_label)
        two_checkbox = QtWidgets.QCheckBox()
        # Определим начальное состояние:
        is_two = isinstance(contact_item, TwoPointContactGroup)
        two_checkbox.setChecked(is_two)
        self.properties_layout.addWidget(two_checkbox)

        # --- Размер ---
        size_label = QtWidgets.QLabel("Размер (диаметр):")
        self.properties_layout.addWidget(size_label)

        # Определяем текущий размер
        if not is_two:
            current_size = contact_item.data(2) or 10
        else:
            current_size = contact_item.data(2) or 10

        size_spin = QtWidgets.QSpinBox()
        size_spin.setRange(5, 30)
        size_spin.setValue(current_size)
        self.properties_layout.addWidget(size_spin)

        # --- Материал(ы) ---
        material_label = QtWidgets.QLabel("Материал(ы):")
        self.properties_layout.addWidget(material_label)

        material_combo1 = QtWidgets.QComboBox()
        material_combo2 = QtWidgets.QComboBox()
        if is_two:
            material_combo1.addItems(self.TWO_POINT_CONTACT_TYPES.keys())
            material_combo2.hide()
        else:
            material_combo1.addItems(self.CONTACT_MATERIALS.keys())
            material_combo2.addItems(self.CONTACT_MATERIALS.keys())

        self.properties_layout.addWidget(material_combo1)
        self.properties_layout.addWidget(material_combo2)

        # Заполняем комбобоксы в зависимости от типа контакта
        if not is_two:
            # Одиночный: заполняем первый, скрываем второй
            mat = contact_item.data(1) or "CPA"
            material_combo1.setCurrentText(mat)
            material_combo2.hide()
        else:
            # Двухточечный: оба ключа, data(1) = "mat1,mat2"
            mat_pair = contact_item.data(1) or "CPA,CPA"
            if "," in mat_pair:
                m1, m2 = mat_pair.split(",", 1)
            else:
                m1, m2 = mat_pair, mat_pair
            material_combo1.setCurrentText(m1)
            material_combo2.setCurrentText(m2)

        # Функция для пересоздания контакта
        def recreate_contact(new_contact_item):
            """Обновляем ссылку на контакт и пересчитываем всё"""
            # Обновляем ссылку (если у вас есть такие поля)
            if hasattr(self, 'current_contact_item'):
                self.current_contact_item = new_contact_item
            if hasattr(self, 'selected_item'):
                self.selected_item = new_contact_item

            # Обновить ячейки и виртуальные линии
            self.cell_manager.assign_elements_to_cells()
            self.update_virtual_lines_on_element_change()

            # Обновляем отображение свойств для нового элемента
            self.show_contact_properties(new_contact_item)

        # Функции-обработчики
        def change_two_mode(checked):
            """
            Если переключили чекбокс, пересоздаём контакт:
            — удаляем старый contact_item из сцены,
            — создаём новый (одиночный или двухточечный)
            """
            try:
                print(f"DEBUG: change_two_mode вызван, checked={checked}, is_two={is_two}")

                # Сохраняем параметры:
                old_pos = contact_item.scenePos()
                old_size = size_spin.value()

                print(f"DEBUG: old_pos={old_pos}, old_size={old_size}")

                if not is_two:
                    # Был одиночный
                    old_mat1 = contact_item.data(1) or "CPA"
                    old_mat2 = old_mat1  # По умолчанию оба материала одинаковые
                else:
                    # Был двухточечный
                    pair = contact_item.data(1) or "CPA,CPA"
                    if "," in pair:
                        old_mat1, old_mat2 = pair.split(",", 1)
                    else:
                        old_mat1, old_mat2 = pair, pair

                print(f"DEBUG: materials: {old_mat1}, {old_mat2}")

                # Удаляем старый из сцены
                self.scene.removeItem(contact_item)
                print("DEBUG: Старый контакт удален")

                # Создаём новый:
                if not checked:
                    # Нужен одиночный
                    new_contact = GridSnapEllipseItem(
                        -old_size / 2, -old_size / 2, old_size, old_size,
                        cell_size=self.cell_size
                    )
                    new_contact.setPos(old_pos)
                    params = self.CONTACT_MATERIALS.get(old_mat1, {"color": "#ff0000", "z": 5})
                    new_contact.setBrush(QtGui.QBrush(QtGui.QColor(params["color"])))
                    new_contact.setZValue(params["z"])
                    new_contact.setData(0, "contact")
                    new_contact.setData(1, old_mat1)
                    new_contact.setData(2, old_size)

                    pen = QtGui.QPen(QtGui.QColor("black"))
                    pen.setWidth(1)
                    new_contact.setPen(pen)
                    new_contact.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                    new_contact.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

                    self.scene.addItem(new_contact)
                    print("DEBUG: Создан одиночный контакт")

                else:
                    # Нужен двухточечный
                    print("DEBUG: Создаем двухточечный контакт...")
                    new_contact = TwoPointContactGroup(
                        center_pos=old_pos,
                        size=old_size,
                        material1=old_mat1,
                        material2=old_mat2,
                        cell_size=self.cell_size,
                        contact_materials=self.CONTACT_MATERIALS
                    )
                    new_contact.setData(0, "contact")
                    new_contact.setData(1, f"{old_mat1},{old_mat2}")
                    new_contact.setData(2, old_size)
                    self.scene.addItem(new_contact)
                    print("DEBUG: Двухточечный контакт создан и добавлен в сцену")

                # Обновляем всё
                recreate_contact(new_contact)
                print("DEBUG: recreate_contact выполнен")

            except Exception as e:
                print(f"DEBUG: Ошибка в change_two_mode: {e}")
                import traceback
                traceback.print_exc()

        # Исправляем подключение сигнала
        two_checkbox.stateChanged.connect(lambda state: change_two_mode(state == 2))  # 2 = Checked

        def change_size():
            new_size = size_spin.value()
            current_pos = contact_item.scenePos()

            if not is_two:
                # Одиночный эллипс - просто меняем размер
                contact_item.setRect(-new_size / 2, -new_size / 2, new_size, new_size)
                contact_item.setData(2, new_size)
            else:
                # Двухточечный: надо перестроить всю группу
                old_mat_pair = contact_item.data(1) or "CPA,CPA"
                if "," in old_mat_pair:
                    m1, m2 = old_mat_pair.split(",", 1)
                else:
                    m1, m2 = old_mat_pair, old_mat_pair

                # Удаляем старую группу
                self.scene.removeItem(contact_item)

                # Создаём новую с обновлённым size:
                new_tp = TwoPointContactGroup(
                    center_pos=current_pos,
                    size=new_size,
                    material1=m1,
                    material2=m2,
                    cell_size=self.cell_size,
                    contact_materials=self.CONTACT_MATERIALS
                )
                new_tp.setData(0, "contact")
                new_tp.setData(1, f"{m1},{m2}")
                new_tp.setData(2, new_size)
                self.scene.addItem(new_tp)

                recreate_contact(new_tp)

        size_spin.valueChanged.connect(change_size)

        def change_materials():
            m1 = material_combo1.currentText()
            m2 = material_combo2.currentText()
            current_pos = contact_item.scenePos()
            current_size = size_spin.value()

            if not is_two:
                # Просто перекрашиваем одиночный
                params = self.CONTACT_MATERIALS.get(m1, {"color": "#ff0000", "z": 5})
                contact_item.setBrush(QtGui.QBrush(QtGui.QColor(params["color"])))
                contact_item.setZValue(params["z"])
                contact_item.setData(1, m1)
            else:
                # Для двухточечного: нужно заменить оба эллипса
                # Удаляем старую группу
                self.scene.removeItem(contact_item)

                # Создаём новую группу с новыми материалами
                if m1 in self.TWO_POINT_CONTACT_TYPES:
                    colors = self.TWO_POINT_CONTACT_TYPES[m1]["colors"]
                    new_tp = TwoPointContactGroup(
                        center_pos=current_pos,
                        size=current_size,
                        material1=m1,  # используем ключ, но внутри зададим цвета напрямую
                        material2=m1,
                        cell_size=self.cell_size,
                        contact_materials={
                            m1: {"color": colors[0], "z": 5},
                            f"{m1}_r": {"color": colors[1], "z": 5}
                        }
                    )
                    new_tp.setData(1, f"{m1},{m1}_r")
                else:
                    return  # или fallback поведение
                new_tp.setData(0, "contact")
                new_tp.setData(1, f"{m1},{m2}")
                new_tp.setData(2, current_size)
                self.scene.addItem(new_tp)

                recreate_contact(new_tp)

        material_combo1.currentIndexChanged.connect(lambda _: change_materials())
        material_combo2.currentIndexChanged.connect(lambda _: change_materials())

        # Сохраняем ссылки на виджеты (если нужно)
        if hasattr(self, 'property_widgets'):
            self.property_widgets["two_point"] = two_checkbox
            self.property_widgets["size"] = size_spin
            self.property_widgets["material1"] = material_combo1
            self.property_widgets["material2"] = material_combo2

        # Ставим отступ внизу
        self.properties_layout.addStretch()

    def create_column(self, scene_pos):
        start_point = self.snap_to_grid(scene_pos)

        # Добавляем в менеджер ячеек
        if not hasattr(self, 'cell_manager'):
            self.cell_manager = CellManager(self.scene)
        self.cell_manager.add_column(start_point.x())

        # Оригинальный код отрисовки
        bottom_y = self.scene.sceneRect().top()
        line = QtWidgets.QGraphicsLineItem(
            start_point.x(), start_point.y(), start_point.x(), bottom_y
        )
        pen = QtGui.QPen(QtGui.QColor("blue"))
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        pen.setWidth(2)
        line.setPen(pen)

        dot = QtWidgets.QGraphicsEllipseItem(
            start_point.x() - 3, start_point.y() - 3, 6, 6
        )
        dot.setBrush(QtGui.QBrush(QtGui.QColor("blue")))
        dot.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))

        self.scene.addItem(line)
        self.scene.addItem(dot)

        column_group = self.scene.createItemGroup([line, dot])
        column_group.setData(0, "column")

        # Обновляем визуализацию ячеек
        self.cell_manager.draw_cell_borders()

        self.cell_comment_manager.update_comments(
            self.cell_manager.columns,
            self.cell_manager.rows
        )

    def create_row(self, scene_pos):
        start_point = self.snap_to_grid(scene_pos)

        if not hasattr(self, 'cell_manager'):
            self.cell_manager = CellManager(self.scene)
        self.cell_manager.add_row(start_point.y())

        left_x = self.scene.sceneRect().left()

        # Создаем элементы
        line = QtWidgets.QGraphicsLineItem(
            start_point.x(), start_point.y(), left_x, start_point.y()
        )
        pen = QtGui.QPen(QtGui.QColor("red"))
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        pen.setWidth(2)
        line.setPen(pen)

        dot = QtWidgets.QGraphicsEllipseItem(
            start_point.x() - 3, start_point.y() - 3, 6, 6
        )
        dot.setBrush(QtGui.QBrush(QtGui.QColor("red")))
        dot.setPen(QtGui.QPen(QtCore.Qt.PenStyle.NoPen))

        # Добавляем элементы на сцену
        self.scene.addItem(line)
        self.scene.addItem(dot)

        # Группируем их через сцену
        row_group = self.scene.createItemGroup([line, dot])
        row_group.setData(0, "row")  # для дальнейшей идентификации

        self.cell_manager.draw_cell_borders()

        self.cell_comment_manager.update_comments(
            self.cell_manager.columns,
            self.cell_manager.rows
        )

    def handle_delete(self):
        self.save_state_for_undo()
        for item in self.scene.selectedItems():
            if item.data(0) not in ["grid", "axis", "axis_mark", "axis_label"]:
                self.scene.removeItem(item)

    def create_toolbar(self):
        """Создает QToolBar и добавляет в него наш виджет"""
        toolbar = QtWidgets.QToolBar("Инструменты")
        toolbar.addWidget(self.toolbar)
        toolbar.setMovable(False)
        return toolbar

    def set_current_tool(self, tool_id):
        """Обработчик изменения инструмента"""
        self.current_tool = tool_id
        print(f"Активирован инструмент: {tool_id}")

        # Настройка поведения View в зависимости от инструмента
        if tool_id == "select":
            self.view.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        elif tool_id == "move":
            self.view.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        elif tool_id == "view":
            self.view.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)

    def print_cell_info(self):
        """Выводит информацию о созданных ячейках в консоль"""
        if hasattr(self, 'cell_manager'):
            print("\n--- Информация о ячейках ---")
            print(f"Столбцы (X): {self.cell_manager.columns}")
            print(f"Строки (Y): {self.cell_manager.rows}")
            print(f"Всего ячеек: {len(self.cell_manager.cells)}")

            for i, cell in enumerate(self.cell_manager.cells, 1):
                print(f"Ячейка {i}: ({cell.x1}, {cell.y1}) - ({cell.x2}, {cell.y2})")
                print(f"  Содержит элементов: {len(cell.elements)}")
        else:
            print("Менеджер ячеек не инициализирован")

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Delete:
            self.handle_delete()
        elif event.matches(QtGui.QKeySequence.StandardKey.Undo):
            self.undo_last_action()
        else:
            super().keyPressEvent(event)

    def handle_delete_click(self, event):
        self.save_state_for_undo()
        scene_pos = self.view.mapToScene(event.pos())

        # Поиск элементов в маленьком прямоугольнике вокруг клика
        items = self.scene.items(QtCore.QRectF(scene_pos.x() - 5, scene_pos.y() - 5, 10, 10))

        for item in items:
            if item.data(0) in ["grid", "axis", "axis_mark", "axis_label"]:
                continue

            # Если элемент входит в группу — удаляем всю группу
            group = item.group()
            if group:
                self.scene.removeItem(group)
            else:
                self.scene.removeItem(item)

            # После первого найденного и удалённого элемента — выход
            break


class GridSnapEllipseItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, x, y, w, h, cell_size=20):
        super().__init__(x, y, w, h)
        self.cell_size = cell_size
        # Критически важные флаги:
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def itemChange(self, change, value):
        #   print(f"Ellipse change: {change}, value: {value}")  # Отладочный вывод
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            grid_size = self.cell_size
            x = round(value.x() / self.cell_size) * self.cell_size
            y = round(value.y() / self.cell_size) * self.cell_size
            #   print(f"Snapping to: {x}, {y}")  # Отладочный вывод
            return QtCore.QPointF(x, y)
        return super().itemChange(change, value)

class GridSnapLineItem(QtWidgets.QGraphicsLineItem):
    def __init__(self, x1=0, y1=0, x2=0, y2=0, cell_size=20):
        super().__init__(x1, y1, x2, y2)
        self.cell_size = cell_size
        # Критически важные флаги:
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def itemChange(self, change, value):
        #   print(f"Line change: {change}, value: {value}")  # Отладочный вывод
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            x = round(value.x() / self.cell_size) * self.cell_size
            y = round(value.y() / self.cell_size) * self.cell_size
            #   print(f"Snapping to: {x}, {y}")  # Отладочный вывод
            return QtCore.QPointF(x, y)
        return super().itemChange(change, value)

class LineWithDotsItem(QtWidgets.QGraphicsLineItem):
    """Линия с точками на концах"""

    def __init__(self, x1, y1, x2, y2, cell_size=20, parent=None):
        super().__init__(x1, y1, x2, y2, parent)
        self.cell_size = cell_size

        # Создаем точки как дочерние элементы
        dot_radius = 10
        self.start_dot = QtWidgets.QGraphicsEllipseItem(-dot_radius, -dot_radius,
                                                        dot_radius * 2, dot_radius * 2, self)
        self.end_dot = QtWidgets.QGraphicsEllipseItem(-dot_radius, -dot_radius,
                                                      dot_radius * 2, dot_radius * 2, self)

        # Обновляем позиции точек
        self._update_dots_position()

    def setLine(self, *args):
        """Переопределяем setLine для обновления позиций точек"""
        super().setLine(*args)
        self._update_dots_position()

    def _update_dots_position(self):
        """Обновляет позиции точек согласно концам линии"""
        line = self.line()
        self.start_dot.setPos(line.x1(), line.y1())
        self.end_dot.setPos(line.x2(), line.y2())

    def setPen(self, pen):
        """Устанавливает перо для линии и цвет для точек"""
        super().setPen(pen)
        # Создаем кисть того же цвета для точек
        brush = QtGui.QBrush(pen.color())
        self.start_dot.setBrush(brush)
        self.end_dot.setBrush(brush)
        # Устанавливаем обводку для точек
        dot_pen = QtGui.QPen(pen.color())
        dot_pen.setWidth(1)
        self.start_dot.setPen(dot_pen)
        self.end_dot.setPen(dot_pen)

    def setZValue(self, z):
        """Устанавливает Z-порядок"""
        super().setZValue(z)
        # Точки должны быть немного выше линии
        self.start_dot.setZValue(z + 0.1)
        self.end_dot.setZValue(z + 0.1)

class GridSnapLineItemWithDots(GridSnapLineItem):
    """GridSnapLineItem с точками на концах"""

    def __init__(self, x1, y1, x2, y2, cell_size=20):
        super().__init__(x1, y1, x2, y2, cell_size)

        # Создаем точки как дочерние элементы
        dot_radius = 3
        self.start_dot = QtWidgets.QGraphicsEllipseItem(-dot_radius, -dot_radius,
                                                        dot_radius * 2, dot_radius * 2, self)
        self.end_dot = QtWidgets.QGraphicsEllipseItem(-dot_radius, -dot_radius,
                                                      dot_radius * 2, dot_radius * 2, self)

        # Обновляем позиции точек
        self._update_dots_position()

    def setLine(self, *args):
        """Переопределяем setLine для обновления позиций точек"""
        super().setLine(*args)
        self._update_dots_position()

    def _update_dots_position(self):
        """Обновляет позиции точек согласно концам линии"""
        line = self.line()
        self.start_dot.setPos(line.x1(), line.y1())
        self.end_dot.setPos(line.x2(), line.y2())

    def setPen(self, pen):
        """Устанавливает перо для линии и цвет для точек"""
        super().setPen(pen)
        # Создаем кисть того же цвета для точек
        brush = QtGui.QBrush(pen.color())
        self.start_dot.setBrush(brush)
        self.end_dot.setBrush(brush)
        # Устанавливаем обводку для точек
        dot_pen = QtGui.QPen(pen.color())
        dot_pen.setWidth(1)
        self.start_dot.setPen(dot_pen)
        self.end_dot.setPen(dot_pen)

    def setZValue(self, z):
        """Устанавливает Z-порядок"""
        super().setZValue(z)
        # Точки должны быть немного выше линии
        self.start_dot.setZValue(z + 0.1)
        self.end_dot.setZValue(z + 0.1)

class TwoPointContactGroup(QtWidgets.QGraphicsItemGroup):
    """
    Группа, состоящая из двух эллипсов и промежуточной линии,
    где «середина» этой линии является точкой привязки к сетке.
    """
    def __init__(self, center_pos: QtCore.QPointF, size: float, material1: str, material2: str, cell_size: float, contact_materials: dict):
        """
        center_pos: координата (QPointF) центра двухточечного контакта (середина линии)
        size: диаметр каждого из двух эллипсов
        material1/2: ключи вида "CSI", "CM1" и т. п. – используются для цвета и Z-уровня
        cell_size: шаг сетки (обычно 20)
        contact_materials: словарь self.CONTACT_MATERIALS, чтобы брать цвет и Z.
        """
        super().__init__()
        self.cell_size = cell_size

        # 1) Эллипсы: смещаем влево и вправо на half_step = cell_size/2
        half_step = cell_size / 2
        r = size  # диаметр

        # Первый эллипс (левый)
        ellipse1 = GridSnapEllipseItem(-r/2 - half_step, -r/2, r, r, cell_size=cell_size)
        params1 = contact_materials.get(material1, {"color":"black","z":5})
        ellipse1.setBrush(QtGui.QBrush(QtGui.QColor(params1["color"])))
        ellipse1.setZValue(params1["z"])
        pen1 = QtGui.QPen(QtGui.QColor("black"))
        pen1.setWidth(1)
        ellipse1.setPen(pen1)
        ellipse1.setData(0, "contact")            # чтобы всё ещё считалось «контактом»
        ellipse1.setData(1, material1)            # материал
        ellipse1.setData(2, size)                 # размер

        # Второй эллипс (правый)
        ellipse2 = GridSnapEllipseItem(-r/2 + half_step, -r/2, r, r, cell_size=cell_size)
        params2 = contact_materials.get(material2, {"color":"black","z":5})
        ellipse2.setBrush(QtGui.QBrush(QtGui.QColor(params2["color"])))
        ellipse2.setZValue(params2["z"])
        pen2 = QtGui.QPen(QtGui.QColor("black"))
        pen2.setWidth(1)
        ellipse2.setPen(pen2)
        ellipse2.setData(0, "contact")
        ellipse2.setData(1, material2)
        ellipse2.setData(2, size)

        # 2) Линия, соединяющая центры двух эллипсов:
        #    Левая точка: (-half_step, 0), правая: (+half_step, 0)
        line = GridSnapLineItem(-half_step, 0, +half_step, 0, cell_size=cell_size)
        pen_line = QtGui.QPen(QtGui.QColor("black"))
        pen_line.setWidth(1)
        line.setPen(pen_line)
        line.setData(0, "contact_line")  # просто «служебный» тип, чтобы не путать с vline
        line.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        line.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        # 3) Добавляем всё в группу:
        self.addToGroup(ellipse1)
        self.addToGroup(ellipse2)
        self.addToGroup(line)

        # 4) Устанавливаем «обязательные флаги» на группу:
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # Позиция группы: центр линии (0,0) → это двоичный контакт. Переносим группу в точку center_pos:
        self.setPos(center_pos)

        # Храним текущее «основное свойство» (материалы и размер), чтобы можно было восстановить в свойствах:
        self.data_pair = (size, material1, material2)

    def itemChange(self, change, value):
        """
        Переопределяем, чтобы группа «прилипала» к сетке именно своим центром (0,0 внутри группы).
        Qt будет вызывать этот метод, когда мы пытаемся передвинуть группу.
        """
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            x = round(value.x() / self.cell_size) * self.cell_size
            y = round(value.y() / self.cell_size) * self.cell_size
            return QtCore.QPointF(x, y)
        return super().itemChange(change, value)

    def boundingRect(self) -> QtCore.QRectF:
        """
        Возвращаем общую boundingRect, который покрывает три примитива:
        линия от (-half_step,0) до(+half_step,0) и два эллипса (диаметра r) сверху/снизу.
        """
        r, m1, m2 = self.data_pair[0], None, None
        half_step = self.cell_size / 2
        return QtCore.QRectF(-half_step - r/2, -r/2, 2 * half_step + r, r)

    def paint(self, painter, option, widget=None):
        """
        Мы не рисуем ничего самим: все дети (ellipse и line) уже нарисованы.
        """
        pass

class CommentTextItem(QtWidgets.QGraphicsTextItem):
    def __init__(self, placeholder="Комментарий"):
        super().__init__()
        self.placeholder = placeholder
        self.is_placeholder_visible = True
        self.setPlainText(self.placeholder)
        self.setDefaultTextColor(QtGui.QColor("gray"))
        self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditorInteraction)
        self.setTransform(QtGui.QTransform().scale(1, -1))
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.document().contentsChanged.connect(self.check_content)

    def focusInEvent(self, event):
        if self.is_placeholder_visible:
            self.setPlainText("")
            self.setDefaultTextColor(QtGui.QColor("black"))
            self.is_placeholder_visible = False
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        if not self.toPlainText().strip():
            self.setPlainText(self.placeholder)
            self.setDefaultTextColor(QtGui.QColor("gray"))
            self.is_placeholder_visible = True
        super().focusOutEvent(event)

    def check_content(self):
        if self.is_placeholder_visible and self.toPlainText() != self.placeholder:
            self.setDefaultTextColor(QtGui.QColor("black"))
            self.is_placeholder_visible = False

class TransistorItem(QtWidgets.QGraphicsItem):
    def __init__(self, cell_size=20, line_length=40, ttype="TP", direction="NORTH"):
        super().__init__()
        self.cell_size = cell_size
        self.step = self.cell_size * 2  # 40
        self.line_length = line_length
        self.ttype = ttype  # "TP" или "TN"
        self.direction = direction  # "NORTH", "SOUTH", "EAST", "WEST"

        self.setData(0, "transistor")

        # Флаги для интерактивности
        flags = QtWidgets.QGraphicsItem.GraphicsItemFlag
        self.setFlag(flags.ItemIsMovable, True)
        self.setFlag(flags.ItemIsSelectable, True)
        self.setFlag(flags.ItemSendsGeometryChanges, True)

        # Устанавливаем высокий zValue по умолчанию
        self.setZValue(10)

        # Применяем scale(1, -1) для исправления отображения
        self.setTransform(QtGui.QTransform().scale(1, -1))

    def boundingRect(self) -> QtCore.QRectF:
        """Bounding rect учитывает квадрат и линию в зависимости от направления"""
        half = self.step / 2
        margin = 5

        # Линия может выходить за пределы квадрата
        line_extension = max(0, self.line_length - self.step)

        if self.direction in ["NORTH", "SOUTH"]:
            # Вертикальная линия
            return QtCore.QRectF(
                -half - margin,
                -line_extension - margin,
                self.step + 2 * margin,
                self.step + line_extension + 2 * margin
            )
        else:  # EAST, WEST
            # Горизонтальная линия
            return QtCore.QRectF(
                -line_extension - margin,
                -half - margin,
                self.step + line_extension + 2 * margin,
                self.step + 2 * margin
            )

    def paint(
            self,
            painter: QtGui.QPainter,
            option: QtWidgets.QStyleOptionGraphicsItem,
            widget: Optional[QtWidgets.QWidget] = None
    ) -> None:
        """Отрисовка транзистора с линией в зависимости от направления"""
        try:
            painter.save()

            # Определяем цвета
            if self.ttype == "TN":
                border_color = QtGui.QColor("red")
            else:  # TP
                border_color = QtGui.QColor("blue")

            line_color = QtGui.QColor("green")

            # 1) Рисуем квадрат 40×40 с цветными границами
            pen = QtGui.QPen(border_color)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(QtGui.QBrush(QtGui.QColor("white")))

            half = self.step / 2
            rect = QtCore.QRectF(-half, 0, self.step, self.step)
            painter.drawRect(rect)

            # 2) Рисуем линию в зависимости от направления (только если длина > 0)
            if self.line_length > 0:
                line_pen = QtGui.QPen(line_color, 3)
                painter.setPen(line_pen)

                if self.direction == "NORTH":
                    # Линия вверх от центра верхней границы квадрата
                    y_start = 0  # Верхняя граница квадрата
                    y_end = y_start - self.line_length  # Линия идет вверх
                    line = QtCore.QLineF(0, y_start, 0, y_end)

                elif self.direction == "SOUTH":
                    # Линия вниз от центра нижней границы квадрата
                    y_start = self.step  # Нижняя граница квадрата
                    y_end = y_start + self.line_length  # Линия идет вниз
                    line = QtCore.QLineF(0, y_start, 0, y_end)

                elif self.direction == "EAST":
                    # Линия вправо от центра правой границы квадрата
                    x_start = half  # Правая граница квадрата
                    x_end = x_start + self.line_length  # Линия идет вправо
                    y_center = self.step / 2  # Центр квадрата по Y
                    line = QtCore.QLineF(x_start, y_center, x_end, y_center)

                elif self.direction == "WEST":
                    # Линия влево от центра левой границы квадрата
                    x_start = -half  # Левая граница квадрата
                    x_end = x_start - self.line_length  # Линия идет влево
                    y_center = self.step / 2  # Центр квадрата по Y
                    line = QtCore.QLineF(x_start, y_center, x_end, y_center)

                painter.drawLine(line)

            # 3) Текст TP/TN внутри квадрата
            text_pen = QtGui.QPen(QtGui.QColor("black"))
            painter.setPen(text_pen)

            font = QtGui.QFont()
            font.setPointSize(8)
            painter.setFont(font)

            # Текст в центре квадрата
            text_rect = QtCore.QRectF(-half, 0, self.step, self.step)
            painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignCenter, str(self.ttype))

        except Exception as e:
            print(f"Ошибка в paint() TransistorItem: {e}")
        finally:
            painter.restore()

    def itemChange(self, change, value):
        """Безопасное изменение позиции"""
        try:
            if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionChange:
                new_pos = value
                if isinstance(new_pos, QtCore.QPointF):
                    x = round(new_pos.x() / self.cell_size) * self.cell_size
                    y = round(new_pos.y() / self.cell_size) * self.cell_size
                    return QtCore.QPointF(x, y)
        except Exception as e:
            print(f"Ошибка в itemChange() TransistorItem: {e}")

        return super().itemChange(change, value)

    def shape(self):
        """Область для выделения включает квадрат и линию"""
        path = QtGui.QPainterPath()

        # Добавляем квадрат
        half = self.step / 2
        path.addRect(-half, 0, self.step, self.step)

        # Добавляем область вокруг линии для удобства выделения (только если линия есть)
        if self.line_length > 0:
            line_width = 6

            if self.direction == "NORTH":
                line_rect = QtCore.QRectF(-line_width / 2, self.step, line_width, self.line_length)
                path.addRect(line_rect)
            elif self.direction == "SOUTH":
                line_rect = QtCore.QRectF(-line_width / 2, -self.line_length, line_width, self.line_length)
                path.addRect(line_rect)
            elif self.direction == "EAST":
                line_rect = QtCore.QRectF(half, self.step / 2 - line_width / 2, self.line_length, line_width)
                path.addRect(line_rect)
            elif self.direction == "WEST":
                line_rect = QtCore.QRectF(-half - self.line_length, self.step / 2 - line_width / 2, self.line_length,
                                          line_width)
                path.addRect(line_rect)

        return path

class ToolBarWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent  # Ссылка на главное окно
        self.setup_ui()

    def setup_ui(self):
        # Основной layout
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Группа кнопок инструментов
        self.tool_group = QtWidgets.QButtonGroup(self)

        # Создаем инструменты
        tools = [
            ("Выделение", "select"),
         #   ("Перемещение", "move"),
            ("Просмотр", "view")
        ]

        for text, tool_id in tools:
            btn = QtWidgets.QRadioButton(text)
            btn.setToolTip(f"Режим {text.lower()}")
            btn.setChecked(tool_id == "view")  # По умолчанию
            btn.toggled.connect(lambda checked, tid=tool_id: self.on_tool_changed(checked, tid))
            self.tool_group.addButton(btn)
            layout.addWidget(btn)

        # Добавляем кнопку "Очистить всё"
        clear_btn = QtWidgets.QPushButton("Очистить всё")
        clear_btn.setToolTip("Удалить все элементы кроме сетки и осей")
        clear_btn.clicked.connect(self.clear_all_elements)
        layout.addWidget(clear_btn)

        undo_btn = QtWidgets.QPushButton("Отменить")
        undo_btn.setToolTip("Откат последнего действия")
        undo_btn.clicked.connect(self.parent.undo_last_action)
        layout.addWidget(undo_btn)

        # Добавляем растяжку между основными кнопками и кнопками слоев
        layout.addStretch()

        # Создаем кнопки для слоев
        self.layer_buttons = []
        self.active_layer_button = None
        for i in range(1, 4):
            btn = QtWidgets.QPushButton(f"{i} Слой")
            btn.setToolTip(f"Активировать {i} слой")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, layer=i, b=btn: self.on_layer_selected(layer, b))
            btn.setStyleSheet("""
                QPushButton {
                    padding: 5px 10px;
                    font-size: 12px;
                    background: #d7e3f8;
                    border: 1px solid #c6d5f5;
                }
                QPushButton:hover {
                    background: #c6d5f5;
                }
                QPushButton:checked {
                    background: #a6c8ff;
                    border: 2px solid #4a90e2;
                    font-weight: bold;
                }
            """)
            self.layer_buttons.append(btn)
            layout.addWidget(btn)

        # Настройки стиля
        self.setStyleSheet("""
            QRadioButton {
                padding: 5px 10px;
                font-size: 12px;
            }
            QPushButton {
                padding: 5px 10px;
                font-size: 12px;
                background: #f8d7da;
                border: 1px solid #f5c6cb;
            }
            QPushButton:hover {
                background: #f5c6cb;
            }
            QWidget {
                background: #f0f0f0;
            }
        """)

    def clear_all_elements(self):
        if hasattr(self.parent, 'save_state_for_undo'):
            self.parent.save_state_for_undo()
        """Удаляет все элементы сцены кроме grid и axis"""
        scene = self.parent.scene

        items = scene.items()
        items_to_remove = []

        for item in items:
            if hasattr(item, 'data'):
                item_type = item.data(0)
                if item_type not in ["grid", "axis", "axis_mark", "axis_label"]:
                    items_to_remove.append(item)
            elif not isinstance(item, (QtWidgets.QGraphicsLineItem, QtWidgets.QGraphicsTextItem)):
                items_to_remove.append(item)

        for item in items_to_remove:
            scene.removeItem(item)

        if hasattr(self.parent, 'cell_manager'):
            self.parent.cell_manager.columns.clear()
            self.parent.cell_manager.rows.clear()
            self.parent.cell_manager.cells.clear()

        print("Все элементы удалены, кроме сетки и осей")

    def on_tool_changed(self, checked, tool_id):
        if checked:
            self.parent.set_current_tool(tool_id)

    def on_layer_selected(self, layer_number, button):
        if self.active_layer_button == button:
            #  Повторное нажатие — отключить фильтр
            print("Слой отключен. Переход в общий режим.")
            self.active_layer_button = None
            button.setChecked(False)
            self.parent.active_layer = 0  # 0 — общий слой
            self.update_layer_locking(0)
        else:
            #  Новый слой выбран
            print(f"Активирован слой {layer_number}")
            if self.active_layer_button:
                self.active_layer_button.setChecked(False)
            button.setChecked(True)
            self.active_layer_button = button
            self.parent.active_layer = layer_number
            self.update_layer_locking(layer_number)


    def layer_1_selected(self):
        """Функция для работы с 1 слоем"""
        pass

    def layer_2_selected(self):
        """Функция для работы со 2 слоем"""
        pass

    def layer_3_selected(self):
        """Функция для работы с 3 слоем"""
        pass

    def update_layer_locking(self, layer_number):
        scene = self.parent.scene

        for item in scene.items():
            if not hasattr(item, 'data'):
                continue

            item_type = item.data(0)

            if layer_number == 1:
                is_active = item_type in ["wire", "contact"]
            elif layer_number == 2:
                is_active = True
                # self.layer_2_selected()  # пока не фильтруем
            elif layer_number == 3:
                is_active = True
            else:
                is_active = True  # общий слой — всё доступно

            item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, is_active)
            item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, is_active)

class CellManager:
    def __init__(self, scene: QtWidgets.QGraphicsScene):
        self.scene = scene
        self.columns: List[float] = []
        self.rows: List[float] = []
        self.cells: List['Cell'] = []
        self.cell_graphics_items: List[QtWidgets.QGraphicsItem] = []
        self.virtual_lines: List[Dict[str, object]] = []

    def add_column(self, x_pos: float):
        """Добавляет вертикальный столбец по x-координате"""
        if x_pos not in self.columns:
            self.columns.append(x_pos)
            self.columns.sort()
            self.update_cells()

    def add_row(self, y_pos: float):
        """Добавляет горизонтальную строку по y-координате"""
        if y_pos not in self.rows:
            self.rows.append(y_pos)
            self.rows.sort()
            self.update_cells()

    def update_cells(self):
        """Пересчитывает ячейки на основе текущих строк и столбцов"""
        self.cells.clear()

        if len(self.columns) < 2 or len(self.rows) < 2:
            return

        for i in range(len(self.columns) - 1):
            for j in range(len(self.rows) - 1):
                name = f"cell{i + 1}{j + 1}"
                cell = Cell(
                    self.columns[i], self.rows[j],
                    self.columns[i + 1], self.rows[j + 1],
                    name=name
                )
                self.cells.append(cell)

    def get_cell_at(self, pos: QtCore.QPointF) -> 'Cell':
        """Находит ячейку, содержащую указанную точку"""
        for cell in self.cells:
            if cell.contains(pos):
                return cell
        return None

    def draw_cell_borders(self):
        """Рисует границы и подписи ячеек"""
        for item in self.cell_graphics_items:
            self.scene.removeItem(item)
        self.cell_graphics_items.clear()

        step = getattr(self.scene.parent(), "step", 40)

        for cell in self.cells:
            rect = QtWidgets.QGraphicsRectItem(cell.x1, cell.y1,
                                               cell.x2 - cell.x1, cell.y2 - cell.y1)

            color_index = self.cells.index(cell) % 3
            colors = [
                QtGui.QColor(200, 200, 255, 50),
                QtGui.QColor(255, 200, 200, 50),
                QtGui.QColor(200, 255, 200, 50)
            ]

            rect.setBrush(QtGui.QBrush(colors[color_index]))
            pen = QtGui.QPen(QtGui.QColor("black"), 1)
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            rect.setPen(pen)

            rect.setZValue(1)
            rect.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            rect.setData(0, "cell")
            rect.setData(1, cell)

            self.scene.addItem(rect)
            self.cell_graphics_items.append(rect)

            label = QtWidgets.QGraphicsSimpleTextItem(cell.name)
            label.setPos(cell.x1 + 15, cell.y1 + 20)
            label.setBrush(QtGui.QBrush(QtGui.QColor("gray")))
            label.setTransform(QtGui.QTransform().scale(1, -1))
            label.setZValue(2)
            self.scene.addItem(label)
            self.cell_graphics_items.append(label)

    def remove_cell(self, cell: 'Cell'):
        """Удаляет ячейку и связанные с ней элементы"""
        print(f"Удаление ячейки {cell.name}")
        try:
            # Удаляем графические элементы ячейки
            items_to_remove = []
            for item in self.cell_graphics_items:
                if item.data(0) == "cell" and item.data(1) == cell:
                    items_to_remove.append(item)
                elif isinstance(item, QtWidgets.QGraphicsSimpleTextItem) and item.text() == cell.name:
                    items_to_remove.append(item)

            for item in items_to_remove:
                self.scene.removeItem(item)
                self.cell_graphics_items.remove(item)

            # Удаляем элементы ячейки (провода, контакты, виртуальные линии)
            rect = QtCore.QRectF(cell.x1, cell.y1, cell.x2 - cell.x1, cell.y2 - cell.y1)
            for item in self.scene.items():
                if not hasattr(item, "data"):
                    continue
                kind = item.data(0)
                if kind == "wire" and isinstance(item, QtWidgets.QGraphicsLineItem):
                    ln = item.line()
                    p1 = item.mapToScene(QtCore.QPointF(ln.x1(), ln.y1()))
                    p2 = item.mapToScene(QtCore.QPointF(ln.x2(), ln.y2()))
                    if rect.contains(p1) or rect.contains(p2):
                        self.scene.removeItem(item)
                elif kind == "contact" and isinstance(item, QtWidgets.QGraphicsEllipseItem):
                    pos = item.scenePos()
                    if rect.contains(pos):
                        self.scene.removeItem(item)
                elif kind == "vline" and isinstance(item, QtWidgets.QGraphicsLineItem):
                    vline_name = item.data(1) or ""
                    if vline_name.startswith(f"{cell.name}") or f"_{cell.name}_" in vline_name:
                        self.scene.removeItem(item)

            # Удаляем ячейку из списка
            if cell in self.cells:
                self.cells.remove(cell)
                print(f"Ячейка {cell.name} удалена из CellManager.cells")

        except Exception as e:
            print(f"Ошибка при удалении ячейки {cell.name}: {e}")
            traceback.print_exc()

    def add_cell(self, cell: 'Cell'):
        """Добавляет ячейку в список"""
        if cell not in self.cells:
            self.cells.append(cell)
            print(f"Ячейка {cell.name} добавлена в CellManager.cells")

    def register_vline_intersections(self, line_item: QtWidgets.QGraphicsLineItem):
        """Регистрирует виртуальную линию в ячейках"""
        try:
            line_name = line_item.data(1)
            print(f"\n=== Регистрация vline: {line_name} ===")

            for cell in self.cells:
                old_count = len(cell.virtual_lines)
                cell.virtual_lines = [
                    vl for vl in cell.virtual_lines if vl.get("name") != line_name
                ]
                if old_count != len(cell.virtual_lines):
                    print(f"  У ячейки {cell.name} убрано {old_count - len(cell.virtual_lines)} старых записей")

            ln: QtCore.QLineF = line_item.line()
            p1_scene = line_item.mapToScene(ln.p1())
            p2_scene = line_item.mapToScene(ln.p2())
            x1, y1 = p1_scene.x(), p1_scene.y()
            x2, y2 = p2_scene.x(), p2_scene.y()

            print(f"  Сценные координаты линии: ({x1:.1f}, {y1:.1f}) – ({x2:.1f}, {y2:.1f})")
            eps = 0.1
            registrations = 0

            if abs(x1 - x2) < eps:
                x_const = x1
                y_min, y_max = min(y1, y2), max(y1, y2)
                print(f"  Это вертикальная линия x={x_const:.1f}, y∈[{y_min:.1f}, {y_max:.1f}]")

                for cell in self.cells:
                    if abs(x_const - cell.x1) < eps and not (y_max < cell.y1 or y_min > cell.y2):
                        cell.virtual_lines.append({
                            "name": line_name,
                            "relation": "lft",
                            "value": x_const
                        })
                        print(f"      ✓ Совпало с левой гранью (lft) ячейки {cell.name}")
                        registrations += 1
                    if abs(x_const - cell.x2) < eps and not (y_max < cell.y1 or y_min > cell.y2):
                        cell.virtual_lines.append({
                            "name": line_name,
                            "relation": "rht",
                            "value": x_const
                        })
                        print(f"      ✓ Совпало с правой гранью (rht) ячейки {cell.name}")
                        registrations += 1

            elif abs(y1 - y2) < eps:
                y_const = y1
                x_min, x_max = min(x1, x2), max(x1, x2)
                print(f"  Это горизонтальная линия y={y_const:.1f}, x∈[{x_min:.1f}, {x_max:.1f}]")

                for cell in self.cells:
                    if abs(y_const - cell.y1) < eps and not (x_max < cell.x1 or x_min > cell.x2):
                        cell.virtual_lines.append({
                            "name": line_name,
                            "relation": "btm",
                            "value": y_const
                        })
                        print(f"      ✓ Совпало с нижней гранью (btm) ячейки {cell.name}")
                        registrations += 1
                    if abs(y_const - cell.y2) < eps and not (x_max < cell.x1 or x_min > cell.x2):
                        cell.virtual_lines.append({
                            "name": line_name,
                            "relation": "top",
                            "value": y_const
                        })
                        print(f"      ✓ Совпало с верхней гранью (top) ячейки {cell.name}")
                        registrations += 1

            print(f"  Всего регистраций для {line_name}: {registrations}")

        except Exception as e:
            print(f"Ошибка в register_vline_intersections: {e}")
            traceback.print_exc()

    def assign_elements_to_cells(self):
        """Перераспределяет элементы по ячейкам"""
        print("Перераспределение элементов по ячейкам...")
        for cell in self.cells:
            cell.clear_elements()
            cell.cif_layers.clear()
            cell.virtual_lines.clear()

        for item in self.scene.items():
            if not hasattr(item, 'data'):
                bounds = item.mapToScene(item.boundingRect()).boundingRect()
                center = bounds.center()
                cell = self.get_cell_at(center)
                if cell:
                    cell.add_element(item)
                continue

            item_type = item.data(0)
            if item_type in ["grid", "axis", "axis_mark", "axis_label", "column", "row", "cell", "vline"]:
                continue

            if item_type == "wire" and isinstance(item, QtWidgets.QGraphicsLineItem):
                line = item.line()
                pos = item.scenePos()
                p1 = QtCore.QPointF(line.x1() + pos.x(), line.y1() + pos.y())
                p2 = QtCore.QPointF(line.x2() + pos.x(), line.y2() + pos.y())

                cells_for_line = set()
                cell1 = self.get_cell_at(p1)
                if cell1:
                    cells_for_line.add(cell1)
                cell2 = self.get_cell_at(p2)
                if cell2:
                    cells_for_line.add(cell2)

                for cell in cells_for_line:
                    cell.add_element(item)
                    elem_data = {
                        'type': 'wire',
                        'layer': item.data(1),
                        'x1': p1.x(),
                        'y1': p1.y(),
                        'x2': p2.x(),
                        'y2': p2.y(),
                        'width': item.pen().width()
                    }
                    if elem_data['layer'] not in cell.cif_layers:
                        cell.cif_layers[elem_data['layer']] = []
                    cell.cif_layers[elem_data['layer']].append(elem_data)

            elif item_type == "contact" and isinstance(item, QtWidgets.QGraphicsEllipseItem):
                pos = item.scenePos()
                cell = self.get_cell_at(pos)
                if cell:
                    cell.add_element(item)
                    elem_data = {
                        'type': 'contact',
                        'layer': item.data(1),
                        'x': pos.x(),
                        'y': pos.y(),
                        'diameter': item.data(2)
                    }
                    if elem_data['layer'] not in cell.cif_layers:
                        cell.cif_layers[elem_data['layer']] = []
                    cell.cif_layers[elem_data['layer']].append(elem_data)

class Cell:
    def __init__(self, x1: float, y1: float, x2: float, y2: float, name: str = ""):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.name = name
        self.elements = []
        self.cif_layers: Dict[str, List[dict]] = {}
        self.labelItem = None
        self.virtual_lines: List[Dict[str, object]] = []

    def to_cif(self) -> str:
        """Генерация CIF-описания ячейки"""
        cif_lines = [f"DS {int(self.x1)} {int(self.y1)} {int(self.x2)} {int(self.y2)};"]
        for layer_name, elements in self.cif_layers.items():
            cif_lines.append(f"L {layer_name};")
            for elem in elements:
                if elem['type'] == 'wire':
                    cif_lines.append(
                        f"W {elem['layer']} {elem['width']} "
                        f"({elem['x1']} {elem['y1']}) "
                        f"({elem['x2']} {elem['y2']});"
                    )
                elif elem['type'] == 'contact':
                    cif_lines.append(
                        f"C {elem['layer']} {elem['diameter']} "
                        f"({elem['x']} {elem['y']});"
                    )
        return "\n".join(cif_lines)

    def contains(self, point: QtCore.QPointF) -> bool:
        return (self.x1 <= point.x() <= self.x2 and
                self.y1 <= point.y() <= self.y2)

    def add_element(self, element):
        self.elements.append(element)

    def clear_elements(self):
        self.elements.clear()

    def draw_border(self, scene: QtWidgets.QGraphicsScene):
        rect = QtWidgets.QGraphicsRectItem(self.x1, self.y1,
                                           self.x2 - self.x1, self.y2 - self.y1)
        pen = QtGui.QPen(QtGui.QColor("black"), 1, QtCore.Qt.PenStyle.DashLine)
        rect.setPen(pen)
        rect.setZValue(-1)
        scene.addItem(rect)

class CellCommentManager:
    def __init__(self, scene: QtWidgets.QGraphicsScene, canvas: InfiniteCanvas):
        self.scene = scene
        self.canvas = canvas
        self.comment_items = []

    def clear_comments(self):
        for item in self.comment_items[:]:
            try:
                self.scene.removeItem(item)
                self.comment_items.remove(item)
            except:
                pass

    def update_comments(self, columns, rows):
        self.clear_comments()
        if not self.scene:
            return

        cell_manager = self.canvas.cell_manager

        # Буферы столбцов
        if len(columns) >= 2:
            cols_sorted = sorted(columns)
            for i in range(len(cols_sorted) - 1):
                x1 = cols_sorted[i]
                x2 = cols_sorted[i + 1]
                text = f"Буфер столбцов {i + 1}"
                # Прямоугольник-оболочка (чтобы можно было выбирать буфер мышью),
                # но сам отбор ячеек будет сугубо по точному совпадению границ.
                self._create_comment(x1, -200, x2, 0,
                                     text,
                                     comment_type="column_comment",
                                     cell_manager=cell_manager,
                                     buf_index=i)

        # Буферы строк
        if len(rows) >= 2:
            rows_sorted = sorted(rows)
            for j in range(len(rows_sorted) - 1):
                y1 = rows_sorted[j]
                y2 = rows_sorted[j + 1]
                text = f"Буфер строк {j + 1}"
                self._create_comment(-200, y1, 0, y2,
                                     text,
                                     comment_type="row_comment",
                                     cell_manager=cell_manager,
                                     buf_index=j)

    def _create_comment(self, x1, y1, x2, y2, text, comment_type, cell_manager, buf_index):
        """
        comment_type: "column_comment" или "row_comment".
        kind = "column" если comment_type=="column_comment", иначе "row".
        buf_index — индекс буфера (нулевой базовый).
        """

        # 1) Создаем «фон» — сам прямоугольник-буфер
        rect = QtWidgets.QGraphicsRectItem(min(x1, x2), min(y1, y2),
                                           abs(x2 - x1), abs(y2 - y1))
        rect.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        pen = QtGui.QPen(QtGui.QColor(150, 150, 200))
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        pen.setWidth(1)
        rect.setPen(pen)

        rect.setBrush(QtGui.QBrush(QtGui.QColor(230, 230, 250, 120)))
        rect.setZValue(-5)
        rect.setData(0, comment_type)  # "column_comment" или "row_comment"

        # 2) Создаем и позиционируем текст внутри этого прямоугольника
        text_item = QtWidgets.QGraphicsSimpleTextItem(text, rect)
        # Визуально «переворачиваем» по Y, чтобы текст в итоге отображался нормально:
        text_item.setTransform(QtGui.QTransform().scale(1, -1))

        # Получаем ширину и высоту текста
        br = text_item.boundingRect()
        text_width  = br.width()
        text_height = br.height()

        # Центр самого прямоугольника-буфера
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2

        # Пытаемся центрировать по горизонтали:
        desired_x = mid_x - text_width / 2
        # «Защёлкиваем» результат в [x1 + margin, x2 - text_width - margin]
        margin = 5
        min_allowed_x = min(x1, x2) + margin
        max_allowed_x = max(x1, x2) - text_width - margin
        text_x = max(min_allowed_x, min(desired_x, max_allowed_x))

        # По вертикали тоже центр:
        # Поскольку мы масштабировали по Y на −1, к mid_y нужно прибавить половину высоты текста:
        text_y = mid_y + text_height / 2

        text_item.setPos(text_x, text_y)

        # 3) Находим связанные ячейки (по границам) и сохраняем в comment.linked_cells
        kind = "column" if comment_type == "column_comment" else "row"
        comment = CellComment(x1, y1, x2, y2, text, kind=kind, index=buf_index)

        eps = 1e-6
        for cell in cell_manager.cells:
            if kind == "column":
                # Левая граница → x1, правая → x2
                if abs(cell.x1 - x1) < eps and abs(cell.x2 - x2) < eps:
                    comment.linked_cells.append(cell)
            else:  # kind == "row"
                # Нижняя граница → y1, верхняя → y2
                if abs(cell.y1 - y1) < eps and abs(cell.y2 - y2) < eps:
                    comment.linked_cells.append(cell)

        rect.setData(1, comment)
        self.scene.addItem(rect)
        self.comment_items.append(rect)

class CellComment:
    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 text: str = "", kind: str = "", index: int = -1):
        """
        kind:   либо "column" (буфер по X), либо "row" (буфер по Y)
        index:  номер буфера, т.е. если это «Буфер столбцов 2», то index=1 (нулевая база)
        """
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.text = text
        self.kind = kind
        self.index = index
        self.item = None
        self.linked_cells = []

    def draw(self, scene: QtWidgets.QGraphicsScene):
        """Отрисовывает комментарий на сцене"""
        # Создаем прямоугольник комментария
        rect = QtWidgets.QGraphicsRectItem(
            min(self.x1, self.x2),
            min(self.y1, self.y2),
            abs(self.x2 - self.x1),
            abs(self.y2 - self.y1)
        )

        # Настраиваем стиль
        rect.setBrush(QtGui.QBrush(QtGui.QColor(240, 240, 240, 150)))  # Светло-серый с прозрачностью
        pen = QtGui.QPen(QtGui.QColor(200, 200, 200), 1)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        rect.setPen(pen)
        rect.setZValue(-2)  # Чтобы был под основными элементами

        # Добавляем текст
        text_item = QtWidgets.QGraphicsTextItem(self.text)
        text_item.setDefaultTextColor(QtGui.QColor(100, 100, 100))
        text_item.setPos(min(self.x1, self.x2) + 5, min(self.y1, self.y2) + 5)
        text_item.setZValue(-1)

        # Группируем элементы
        group = scene.createItemGroup([rect, text_item])
        group.setData(0, "cell_comment")

        self.item = group

    def to_cif(self, fragment_id: int) -> str:
        lines = []
        lines.append(f"DS {fragment_id} 1 1;")
        lines.append(f"9 {self.text.replace(' ', '_')};")

        for i, cell in enumerate(self.linked_cells, 1):
            lines.append(f"L Cell_{i};")

            for layer, elements in cell.cif_layers.items():
                for elem in elements:
                    if elem['type'] == 'wire':
                        lines.append(
                            f"W {elem['width']} "
                            f"{int(elem['x1'])} {int(elem['y1'])} {int(elem['x2'])} {int(elem['y2'])};"
                        )
                    elif elem['type'] == 'contact':
                        lines.append(
                            f"C {layer} T {int(elem['x'])} {int(elem['y'])};"
                        )

        lines.append("DF;")
        return "\n".join(lines)



if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = InfiniteCanvas(start_x=290, start_y=-375)
    window.show()
    sys.exit(app.exec())