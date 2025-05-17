from PyQt6 import QtWidgets, QtGui, QtCore
from typing import List, Dict
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
        self.max_x = 4000  # Можно увеличить при необходимости
        self.max_y = 4000

        self.setWindowTitle("Графический редактор")
        self.setGeometry(100, 100, 1200, 800)

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

        # Панель инструментов
        self.tool_panel = QtWidgets.QFrame()
        self.tool_panel.setFixedWidth(200)
        self.tool_layout = QtWidgets.QVBoxLayout(self.tool_panel)

        self.toolbar = ToolBarWidget(self)
        self.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, self.create_toolbar())

        # self.current_tool = "select"

        layout.addWidget(self.view)
        layout.addWidget(self.tool_panel)

        self.create_tools()
        self.setup_scene_events()

        self.active_layer = 1

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
            "Material1": {"color": "#ff0000", "style": QtCore.Qt.PenStyle.SolidLine, "z": 3},
            "Material2": {"color": "#00aa00", "style": QtCore.Qt.PenStyle.SolidLine, "z": 2},
            "Material3": {"color": "#0000ff", "style": QtCore.Qt.PenStyle.SolidLine, "z": 1},
            "Material4": {"color": "#ffaa00", "style": QtCore.Qt.PenStyle.SolidLine, "z": 0},
            "VCC": {"color": "#ff00ff", "style": QtCore.Qt.PenStyle.DashLine, "z": 1},
            "GND": {"color": "#00ffff", "style": QtCore.Qt.PenStyle.DashLine, "z": 1},
        }

        self.cell_comment_manager = CellCommentManager(self.scene)

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
        save_action = QtGui.QAction("Сохранение всей информации об элементах", self)
        save_action.triggered.connect(self.save_cells_to_files)
        file_menu.addAction(save_action)

        # Новое действие для CIF
        save_cif_action = QtGui.QAction("Сохранение ячеек (CIF)", self)
        save_cif_action.triggered.connect(self.export_to_cif)
        file_menu.addAction(save_cif_action)

        export_comment_cif_action = QtGui.QAction("Экспорт комментариев (CIF)", self)
        export_comment_cif_action.triggered.connect(self.export_comment_fragments_to_cif)
        file_menu.addAction(export_comment_cif_action)

    def table_creation(self):
        # Диалог для выбора размера ячеек по X (в логических шагах)
        size_x_dialog = QtWidgets.QInputDialog(self)
        size_x_dialog.setWindowTitle("Размер ячеек по X")
        size_x_dialog.setLabelText("Введите ширину ячеек (в шагах):")
        size_x_dialog.setInputMode(QtWidgets.QInputDialog.InputMode.IntInput)
        size_x_dialog.setIntRange(1, 50)
        size_x_dialog.setIntValue(4)

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
        size_y_dialog.setIntValue(3)

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
        count_x_dialog.setIntValue(5)

        if not count_x_dialog.exec():
            return

        cell_count_x = count_x_dialog.intValue()

        # Диалог для выбора количества ячеек по Y
        count_y_dialog = QtWidgets.QInputDialog(self)
        count_y_dialog.setWindowTitle("Количество ячеек по Y")
        count_y_dialog.setLabelText("Введите количество ячеек по вертикали (Y):")
        count_y_dialog.setInputMode(QtWidgets.QInputDialog.InputMode.IntInput)
        count_y_dialog.setIntRange(1, 100)
        count_y_dialog.setIntValue(5)

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
            ("Линия", "line"),
            ("Комментарий", "comment"),
            ("Контакт", "contact"),
            ("Удаление", "delete"),
            ("Шаблоны", "template"),
            ("Просмотр", "view"),
            ("Столбец", "column"),
            ("Строка", "row"),
            ("Комментарий ячеек", "cell_comment")
        ]

        label = QtWidgets.QLabel("Инструменты")
        label.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Weight.Bold))
        label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        self.tool_layout.addWidget(label)
        self.tool_layout.setSpacing(1)
        self.tool_layout.setContentsMargins(1, 1, 1, 1)

        self.tool_button_group = QtWidgets.QButtonGroup(self)
        self.tool_button_group.setExclusive(True)

        for tool_name, tool_id in tools:
            btn = QtWidgets.QRadioButton(tool_name)
            btn.setFixedWidth(180)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda checked, tid=tool_id: self.set_tool(tid) if checked else None)
            self.tool_button_group.addButton(btn)
            self.tool_layout.addWidget(btn)

        self.properties_label = QtWidgets.QLabel("Свойства")
        self.properties_label.hide()
        self.properties_label.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Weight.Bold))
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
        selected_items = self.scene.selectedItems()
        if not selected_items:
            self.clear_properties_panel()
            return
        item = selected_items[0]

        if isinstance(item, QtWidgets.QGraphicsLineItem):
            self.show_line_properties(item)
        elif item.data(0) == "contact":
            self.show_contact_properties(item)
        elif item.data(0) == "cell":
            cell = item.data(1)  # Получаем объект Cell
            self.show_cell_properties(cell)
        elif item.data(0) in ["column_comment", "row_comment"]:
            comment = item.data(1)
            if isinstance(comment, CellComment):
                self.show_comment_properties(comment)

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

    def show_cell_properties(self, cell):
        self.clear_properties_panel()
        self.properties_label.show()

        label = QtWidgets.QLabel(f"Ячейка: ({cell.x1}, {cell.y1}) — ({cell.x2}, {cell.y2})")
        self.properties_layout.addWidget(label)

        line_count = 0
        contact_count = 0
        for element in cell.elements:
            if isinstance(element, QtWidgets.QGraphicsLineItem) and hasattr(element, 'data') and element.data(
                    0) == "wire":
                line_count += 1
            elif isinstance(element, QtWidgets.QGraphicsEllipseItem) and hasattr(element, 'data') and element.data(
                    0) == "contact":
                contact_count += 1

        count_label = QtWidgets.QLabel(f"Элементов внутри: {len(cell.elements)}")
        self.properties_layout.addWidget(count_label)

        # Подсчитываем количество линий и контактов
        line_count = 0
        contact_count = 0
        for element in cell.elements:
            if isinstance(element, QtWidgets.QGraphicsLineItem):
                line_count += 1
            elif isinstance(element, QtWidgets.QGraphicsEllipseItem) and hasattr(element, 'data') and element.data(
                    0) == "contact":
                contact_count += 1

        # Отображаем количество линий и контактов
        line_label = QtWidgets.QLabel(f"Линий: {line_count}")
        self.properties_layout.addWidget(line_label)

        contact_label = QtWidgets.QLabel(f"Контактов: {contact_count}")
        self.properties_layout.addWidget(contact_label)

        # Отображаем слои CIF
        if cell.cif_layers:
            for layer, elems in cell.cif_layers.items():
                layer_label = QtWidgets.QLabel(f"Слой: {layer}, элементов: {len(elems)}")
                self.properties_layout.addWidget(layer_label)

        copy_x_button = QtWidgets.QPushButton("Копировать по X")
        copy_x_button.clicked.connect(lambda: self.copy_cell(cell, direction="x"))
        self.properties_layout.addWidget(copy_x_button)

        copy_y_button = QtWidgets.QPushButton("Копировать по Y")
        copy_y_button.clicked.connect(lambda: self.copy_cell(cell, direction="y"))
        self.properties_layout.addWidget(copy_y_button)

        copy_offset_button = QtWidgets.QPushButton("Копировать со смещением")
        copy_offset_button.clicked.connect(lambda: self.copy_cell(cell, direction="offset"))
        self.properties_layout.addWidget(copy_offset_button)
        self.properties_layout.addStretch()

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
        # Координаты новой ячейки
        new_x1 = original_cell.x1 + offset.x()
        new_y1 = original_cell.y1 + offset.y()
        new_x2 = original_cell.x2 + offset.x()
        new_y2 = original_cell.y2 + offset.y()

        new_cell = Cell(new_x1, new_y1, new_x2, new_y2)

        # Копируем элементы
        for item in original_cell.elements:
            new_item = None

            if isinstance(item, QtWidgets.QGraphicsLineItem):
                line = item.line()
                new_line = GridSnapLineItem(
                    line.x1() + offset.x(), line.y1() + offset.y(),
                    line.x2() + offset.x(), line.y2() + offset.y()
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
                new_contact = GridSnapEllipseItem(
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
        material_combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        material_combo.addItems(list(self.LINE_MATERIALS.keys()))
        current_material = line_item.data(1) or "Material1"
        material_combo.setCurrentText(current_material)
        self.properties_layout.addWidget(material_combo)

        # --- Функция обновления стиля ---
        def update_line():
            material = material_combo.currentText()
            logic_width = width_spin.value()

            # Обновляем внутренние данные
            line_item.setData(1, material)
            line_item.setData(2, logic_width)

            # Обновляем стиль линии
            self.set_line_style(line_item, material, logic_width)

        material_combo.currentIndexChanged.connect(update_line)
        width_spin.valueChanged.connect(update_line)

        self.property_widgets["material"] = material_combo
        self.property_widgets["width"] = width_spin

        self.properties_layout.addStretch()

    def set_tool(self, tool_id):
        self.current_tool = tool_id
        print(f"Выбран инструмент: {tool_id}")
        self.clear_properties_panel()

    def draw_grid(self):
        light_pen = QtGui.QPen(QtGui.QColor("#e8eaed"))
        light_pen.setWidth(0)

        dark_pen = QtGui.QPen(QtGui.QColor("lightgray"))
        dark_pen.setWidth(0)

        for x in range(-4000, 8000, self.cell_size):
            pen = dark_pen if x % self.step == 0 else light_pen
            line = self.scene.addLine(x, -4000, x, 4000, pen)
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
        if self.handle_middle_mouse_pan(event):
            return True

        if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.RightButton:
            scene_pos = self.view.mapToScene(event.pos())
            item = self.scene.itemAt(scene_pos, self.view.transform())
            if item:
                self.moving_item = item
                self.move_start_pos = scene_pos
                self.view.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                return True

        elif event.type() == QtCore.QEvent.Type.MouseMove and self.moving_item and event.buttons() & QtCore.Qt.MouseButton.RightButton:
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

        if event.type() == QtCore.QEvent.Type.MouseButtonPress and event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self.current_tool == "delete":
                self.handle_delete_click(event)
            elif self.current_tool == "line":
                self.line_creation(event)
            elif self.current_tool == "view":
                self.properties_label.show()
            elif self.current_tool == "comment":
                scene_pos = self.view.mapToScene(event.pos())
                self.create_comment(scene_pos)
            elif self.current_tool == "contact":
                scene_pos = self.snap_to_grid(self.view.mapToScene(event.pos()))
                self.create_contact(scene_pos)
            elif self.current_tool == "column":
                scene_pos = self.view.mapToScene(event.pos())
                self.create_column(scene_pos)
            elif self.current_tool == "row":
                scene_pos = self.view.mapToScene(event.pos())
                self.create_row(scene_pos)

            else:
                self.last_pos = event.pos()

        elif event.type() == QtCore.QEvent.Type.MouseMove:
            if self.current_tool == "line" and self.line_start and self.temp_line:
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

        elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self.current_tool == "line" and self.temp_line:
                self.temp_line = None
                self.line_start = None

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

        if self.current_tool == "move":
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self.view.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                    self.last_pos = event.pos()
                    return True

            elif event.type() == QtCore.QEvent.Type.MouseMove and self.last_pos:
                delta = event.pos() - self.last_pos
                self.view.horizontalScrollBar().setValue(
                    self.view.horizontalScrollBar().value() - delta.x())
                self.view.verticalScrollBar().setValue(
                    self.view.verticalScrollBar().value() - delta.y())
                self.last_pos = event.pos()
                return True

            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                self.view.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
                self.last_pos = None
                return True

        return super().eventFilter(source, event)

    def set_line_style(self, line_item, material_name, logic_width):
        material = self.LINE_MATERIALS.get(material_name, self.LINE_MATERIALS["Material1"])
        color = QtGui.QColor(material["color"])
        style = material["style"]
        z = material["z"]

        # Линейное преобразование: логическая -3...10 → визуальная 3...16
        visual_width = logic_width + 6

        pen = QtGui.QPen(color)
        pen.setWidth(max(1, visual_width))  # минимальная ширина = 1 px
        pen.setStyle(style)

        line_item.setPen(pen)
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

        default_material = "Material1"
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

    def create_contact(self, position):
        if self.active_layer not in [0, 1]:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Выбран не тот слой!")
            return
        self.save_state_for_undo()
        contact_size = 10
        contact = GridSnapEllipseItem(
            -contact_size / 2, -contact_size / 2,
            contact_size, contact_size, cell_size=self.cell_size
        )
        contact.setPos(position)

        # Данные для CIF
        contact.setData(0, "contact")
        contact.setData(1, "VIA1")  # Слой
        contact.setData(2, contact_size)  # Диаметр

        pen = QtGui.QPen(QtGui.QColor("black"))
        pen.setWidth(1)
        contact.setPen(pen)
        contact.setBrush(QtGui.QBrush(QtGui.QColor("red")))

        contact.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        contact.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

        self.scene.addItem(contact)



        if hasattr(self, 'cell_manager'):
            self.cell_manager.assign_elements_to_cells()

        return contact

    def show_contact_properties(self, contact_item):
        self.clear_properties_panel()
        self.properties_label.show()

        size_label = QtWidgets.QLabel("Размер:")
        self.properties_layout.addWidget(size_label)

        size_spin = QtWidgets.QSpinBox()
        size_spin.setRange(5, 30)
        size_spin.setValue(contact_item.data(2))
        self.properties_layout.addWidget(size_spin)

        def change_size():
            new_size = size_spin.value()
            contact_item.setRect(-new_size / 2, -new_size / 2, new_size, new_size)
            contact_item.setData(2, new_size)

        size_spin.valueChanged.connect(change_size)
        self.property_widgets["size"] = size_spin

        color_label = QtWidgets.QLabel("Цвет:")
        self.properties_layout.addWidget(color_label)

        color_combo = QtWidgets.QComboBox()
        colors = ["Красный", "Синий", "Зеленый", "Желтый", "Черный"]
        color_combo.addItems(colors)

        current_color = contact_item.brush().color().name()
        color_map = {
            "#ff0000": "Красный",
            "#0000ff": "Синий",
            "#00ff00": "Зеленый",
            "#ffff00": "Желтый",
            "#000000": "Черный"
        }
        color_combo.setCurrentText(color_map.get(current_color, "Красный"))
        self.properties_layout.addWidget(color_combo)

        def change_color(index):
            color_name = color_combo.currentText()
            color_dict = {
                "Красный": QtGui.QColor("red"),
                "Синий": QtGui.QColor("blue"),
                "Зеленый": QtGui.QColor("green"),
                "Желтый": QtGui.QColor("yellow"),
                "Черный": QtGui.QColor("black")
            }
            contact_item.setBrush(QtGui.QBrush(color_dict[color_name]))

        color_combo.currentIndexChanged.connect(change_color)
        self.property_widgets["color"] = color_combo

        material_label = QtWidgets.QLabel("Материал:")
        self.properties_layout.addWidget(material_label)

        material_combo = QtWidgets.QComboBox()
        material_combo.addItems(["Material1", "Material2", "Material3"])
        material_combo.setCurrentText(contact_item.data(1))
        self.properties_layout.addWidget(material_combo)

        def change_material(index):
            contact_item.setData(1, material_combo.currentText())

        material_combo.currentIndexChanged.connect(change_material)
        self.property_widgets["material"] = material_combo

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

      #  self.cell_comment_manager.draw_comments

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


class CommentTextItem(QtWidgets.QGraphicsTextItem):
    def __init__(self, placeholder="Комментарий"):
        super().__init__()
        self.placeholder = placeholder
        self.is_placeholder_visible = True
        self.setPlainText(self.placeholder)
        self.setDefaultTextColor(QtGui.QColor("gray"))
        self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditorInteraction)
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
            ("Перемещение", "move"),
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

        undo_btn = QtWidgets.QPushButton("Отменить (Ctrl+Z)")
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
                is_active = True  # пока не фильтруем
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

        # Нужно минимум 2 столбца и 2 строки для образования ячеек
        if len(self.columns) < 2 or len(self.rows) < 2:
            return

        # Создаем ячейки между линиями
        for i in range(len(self.columns) - 1):
            for j in range(len(self.rows) - 1):
                cell = Cell(
                    self.columns[i], self.rows[j],
                    self.columns[i + 1], self.rows[j + 1]
                )
                self.cells.append(cell)

    def get_cell_at(self, pos: QtCore.QPointF) -> 'Cell':
        """Находит ячейку, содержащую указанную точку"""
        for cell in self.cells:
            if cell.contains(pos):
                return cell
        return None

    def draw_cell_borders(self):
        # Удаляем предыдущие графические элементы ячеек
        for item in self.cell_graphics_items:
            self.scene.removeItem(item)
        self.cell_graphics_items.clear()

        # Получаем доступ к шагу
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

            rect.setZValue(1)  # 🚨 Поверх сетки (grid ZValue = 0 по умолчанию)
            rect.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            rect.setData(0, "cell")
            rect.setData(1, cell)

            self.scene.addItem(rect)
            self.cell_graphics_items.append(rect)

            # Подпись координат в логических шагах (step)
            label_text = f"{round(cell.x1 / step)},{round(cell.y1 / step)}"
            label = QtWidgets.QGraphicsSimpleTextItem(label_text)
            label.setPos(cell.x1 + 15, cell.y1 + 20)
            label.setBrush(QtGui.QBrush(QtGui.QColor("gray")))
            label.setTransform(QtGui.QTransform().scale(1, -1))
            label.setZValue(2)  # Текст тоже поверх
            self.scene.addItem(label)
            self.cell_graphics_items.append(label)

    def assign_elements_to_cells(self):
        print("Перераспределение элементов по ячейкам...")
        for cell in self.cells:
            cell.clear_elements()
            cell.cif_layers.clear()  # Очищаем CIF-данные

        for item in self.scene.items():
            if hasattr(item, 'data'):
                item_type = item.data(0)
                if hasattr(item, 'data') and item.data(0) in ["grid", "axis", "axis_mark", "axis_label", "column",
                                                              "row", "cell"]:
                    continue

            bounds = item.mapToScene(item.boundingRect()).boundingRect()
            center = bounds.center()

            pos = item.scenePos()
            cell = self.get_cell_at(pos)
            if cell:
                cell.add_element(item)

                # Добавляем данные в CIF-формате
                if hasattr(item, 'data'):
                    elem_data = {
                        'type': item.data(0),
                        'layer': item.data(1),
                        'x': pos.x(),
                        'y': pos.y()
                    }

                    if item.data(0) == "wire":
                        elem_data.update({
                            'x1': item.line().x1(),
                            'y1': item.line().y1(),
                            'x2': item.line().x2(),
                            'y2': item.line().y2(),
                            'width': item.pen().width()
                        })
                    elif item.data(0) == "contact":
                        elem_data['diameter'] = item.data(2)

                    # Группируем по слоям
                    if elem_data['layer'] not in cell.cif_layers:
                        cell.cif_layers[elem_data['layer']] = []
                    cell.cif_layers[elem_data['layer']].append(elem_data)


class Cell:
    def __init__(self, x1: float, y1: float, x2: float, y2: float):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.elements = []
        self.cif_layers = {}

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
        rect.setZValue(-1)  # Чтобы границы были под элементами
        scene.addItem(rect)


class CellCommentManager:
    def __init__(self, scene: QtWidgets.QGraphicsScene):
        self.scene = scene
        self.comment_items = []

    def clear_comments(self):
        """Безопасное удаление всех комментариев"""
        for item in self.comment_items[:]:  # Используем копию списка для безопасного удаления
            try:
                self.scene.removeItem(item)
                self.comment_items.remove(item)
            except:
                continue

    def update_comments(self, columns, rows):
        """Обновление комментариев"""
        self.clear_comments()

        if not self.scene:
            return

        try:
            # Комментарии для столбцов (левая отрицательная область)
            if len(columns) >= 2:
                columns_sorted = sorted(columns)
                for i in range(len(columns_sorted) - 1):
                    self._create_comment(
                        columns_sorted[i], -200,
                        columns_sorted[i + 1], 0,
                        f"Ячейка столбцов {i + 1}", "column_comment"
                    )

            # Комментарии для строк (верхняя отрицательная область)
            if len(rows) >= 2:
                rows_sorted = sorted(rows)
                for j in range(len(rows_sorted) - 1):
                    self._create_comment(
                        -200, rows_sorted[j],
                        0, rows_sorted[j + 1],
                        f"Ячейка строк {j + 1}", "row_comment"
                    )
        except Exception as e:
            print(f"Error updating comments: {str(e)}")

    def _create_comment(self, x1, y1, x2, y2, text, comment_type):
        """Создает один комментарий"""
        rect = QtWidgets.QGraphicsRectItem(x1, y1, x2 - x1, y2 - y1)
        rect.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        # Правильное указание стиля линии
        pen = QtGui.QPen(QtGui.QColor(150, 150, 200))
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)  # Правильный способ задания стиля
        pen.setWidth(1)

        rect.setPen(pen)
        rect.setBrush(QtGui.QBrush(QtGui.QColor(230, 230, 250, 120)))
        rect.setZValue(-5)
        rect.setData(0, comment_type)


        text_item = QtWidgets.QGraphicsSimpleTextItem(text, rect)
        text_item.setPos(x1 + 15, y1 + 20)
        text_item.setBrush(QtGui.QBrush(QtGui.QColor(80, 80, 120)))
        text_item.setTransform(QtGui.QTransform().scale(1, -1))

        comment = CellComment(x1, y1, x2, y2, text)

        if hasattr(self.scene.parent(), 'cell_manager'):
            for cell in self.scene.parent().cell_manager.cells:
                # Пересекаются ли границы cell и комментария
                if (cell.x1 >= min(x1, x2) and cell.x2 <= max(x1, x2) and
                        cell.y1 >= min(y1, y2) and cell.y2 <= max(y1, y2)):
                    comment.linked_cells.append(cell)
        rect.setData(1, comment)
        self.scene.addItem(rect)
        self.comment_items.append(rect)

class CellComment:
    def __init__(self, x1: float, y1: float, x2: float, y2: float, text: str = ""):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.text = text
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