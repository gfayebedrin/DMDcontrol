import os
import glob
import numpy as np
from PIL import Image
from datetime import timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QTreeWidgetItem,
    QWidget,
    QFileDialog,
    QTableWidgetItem,
    QMessageBox,
    QInputDialog,
)
import pyqtgraph as pg

from ..logic.sequence import PatternSequence
from ..logic import saving

from .qt.DMD_stim_ui import Ui_widget_dmd_stim
from . import console, roi_manager


class StimDMDWidget(QWidget):
    def __init__(self, name="Stimulation DMD Widget", dmd=None, parent=None):
        super().__init__(parent=parent)
        self.ui = Ui_widget_dmd_stim()
        self.ui.setupUi(self)
        self.setObjectName(name)
        self.last_roi = None
        self.crosshair = pg.CrosshairROI([0, 0], [20, 20])
        self.dmd = dmd
        self.model: PatternSequence | None = None
        self._next_pattern_id: int = 0
        self.image_item = pg.ImageView(parent=self, view=pg.PlotItem())
        self.ui.stackedWidget_image.addWidget(self.image_item)
        self.roi_manager = roi_manager.RoiManager(self.image_item)
        self.roi_manager.polygonEdited.connect(
            lambda *_: setattr(self, "model", self._get_model_from_ui())
        )
        self._connect()
        self._console = console.Console(self.ui.plainTextEdit_console_output)
        self._updating_table = False

    def _new_pattern_id(self) -> int:
        pid = self._next_pattern_id
        self._next_pattern_id += 1
        return pid

    def _attach_pattern_id(self, item: QTreeWidgetItem, pid: int) -> None:
        item.setData(0, Qt.UserRole, int(pid))

    def _pattern_id(self, item: QTreeWidgetItem) -> int:
        data = item.data(0, Qt.UserRole)
        return int(data) if data is not None else -1

    def _pattern_id_order(self) -> list[int]:
        ids = []
        for i in range(self.ui.treeWidget.topLevelItemCount()):
            ids.append(self._pattern_id(self.ui.treeWidget.topLevelItem(i)))
        return ids

    def _extract_description(self, text: str) -> str:
        s = text.strip()
        if s.startswith("#"):
            s = s[1:]
            while s and s[0].isdigit():
                s = s[1:]
            s = s.lstrip(" -:\t")
        return s

    def _set_pattern_label(self, item: QTreeWidgetItem, index: int, desc: str) -> None:
        item.setText(0, f"#{index} {desc}".rstrip())

    def _renumber_pattern_labels(self) -> None:
        for i in range(self.ui.treeWidget.topLevelItemCount()):
            item = self.ui.treeWidget.topLevelItem(i)
            desc = self._extract_description(item.text(0))
            self._set_pattern_label(item, i, desc)
        self._refresh_sequence_descriptions()

    def _remap_sequence_by_ids(
        self,
        old_ids: list[int],
        new_ids: list[int],
        *,
        on_deleted: str = "drop",
        replace_with: int | None = None,
    ) -> None:
        id_to_new_idx = {pid: i for i, pid in enumerate(new_ids)}
        rows_to_drop = []
        for r in range(self.ui.tableWidget.rowCount()):
            idx_item = self.ui.tableWidget.item(r, 2)
            if not idx_item:
                continue
            try:
                old_idx = int(idx_item.text())
            except Exception:
                continue
            if not (0 <= old_idx < len(old_ids)):
                continue
            pid = old_ids[old_idx]
            if pid in id_to_new_idx:
                idx_item.setText(str(id_to_new_idx[pid]))
            else:
                if on_deleted == "drop":
                    rows_to_drop.append(r)
                elif on_deleted == "replace" and replace_with is not None:
                    idx_item.setText(str(replace_with))
        for r in sorted(rows_to_drop, reverse=True):
            self.ui.tableWidget.removeRow(r)
        self._refresh_sequence_descriptions()

    def _ensure_desc_column(self):
        tbl = self.ui.tableWidget
        if tbl.columnCount() < 4:
            tbl.setColumnCount(4)
        if not tbl.horizontalHeaderItem(3):
            tbl.setHorizontalHeaderItem(3, QTableWidgetItem("Description"))

    def _pattern_description_by_index(self, idx: int) -> str:
        if 0 <= idx < self.ui.treeWidget.topLevelItemCount():
            item = self.ui.treeWidget.topLevelItem(idx)
            return self._extract_description(item.text(0))
        return ""

    def _set_sequence_row_description(self, row: int, pattern_idx: int) -> None:
        self._ensure_desc_column()
        desc = self._pattern_description_by_index(pattern_idx)
        it = self.ui.tableWidget.item(row, 3)
        if it is None:
            it = QTableWidgetItem("")
            self.ui.tableWidget.setItem(row, 3, it)
        it.setText(desc)
        it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

    def _refresh_sequence_descriptions(self):
        self._updating_table = True
        rows = self.ui.tableWidget.rowCount()
        for r in range(rows):
            idx_item = self.ui.tableWidget.item(r, 2)
            if not idx_item:
                continue
            try:
                idx = int(idx_item.text())
            except Exception:
                continue
            self._set_sequence_row_description(r, idx)
        self._updating_table = False

    def _connect(self):
        self.ui.pushButton_load_image.clicked.connect(self._load_image)
        self.ui.pushButton_change_folder.clicked.connect(self._change_folder)
        self.ui.pushButton_refresh_image.clicked.connect(self._refresh_image)
        self.ui.pushButton_show_grid.clicked.connect(self._show_grid)
        self.ui.pushButton_define_axis.clicked.connect(self._define_axis)
        self.ui.pushButton_add_pattern.clicked.connect(self._add_pattern)
        self.ui.pushButton_add_roi.clicked.connect(self._add_roi)
        self.ui.pushButton_add_row.clicked.connect(self._add_row_table)
        self.ui.pushButton_remove_row.clicked.connect(self._remove_row_table)
        self.ui.pushButton_remove_pattern.clicked.connect(self._remove_selected_patterns)
        self.ui.pushButton_load_patterns.clicked.connect(self._load_patterns_file)
        self.ui.pushButton_save_patterns.clicked.connect(self._save_file)
        self.ui.treeWidget.itemClicked.connect(
            lambda item, _col: self.roi_manager.show_for_item(item)
        )
        self.ui.treeWidget.itemChanged.connect(self._on_item_changed)
        self.ui.tableWidget.itemChanged.connect(self._on_table_item_changed)

    def _on_item_changed(self, item: QTreeWidgetItem, col: int):
        if item.parent() is None:
            idx = self.ui.treeWidget.indexOfTopLevelItem(item)
            if idx >= 0:
                desc = self._extract_description(item.text(col))
                self._set_pattern_label(item, idx, desc)
                self.model = self._get_model_from_ui()
                self._refresh_sequence_descriptions()

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if self._updating_table:
            return
        if item.column() == 2:
            try:
                idx = int(item.text())
            except Exception:
                return
            self._set_sequence_row_description(item.row(), idx)

    def closeEvent(self, event):
        self._console.restore_original_streams()
        super().closeEvent(event)

    def update_ui(self, data):
        if self.dmd is not None:
            self._set_image(data)

    def set_up(self):
        pass

    def _set_image(self, image):
        self.image_item.setImage(image.T)

    def _load_image(self, path: str = ""):
        try:
            path = QFileDialog.getOpenFileName(self, "Select file", "", "")[0]
            if not path:
                return
            image = np.array(Image.open(path))
            self._set_image(image)
        except Exception:
            pass

    def _change_folder(self):
        try:
            filename = self.ui.lineEdit_image_folder_path.text()
            if filename == "":
                filename = "C:\\"
            path = QFileDialog.getExistingDirectory(
                None, "Select a folder:", filename, QFileDialog.ShowDirsOnly
            )
            if path:
                self.ui.lineEdit_image_folder_path.setText(path)
        except Exception:
            pass

    def _refresh_image(self):
        folder_path = self.ui.lineEdit_image_folder_path.text()
        if not os.path.exists(folder_path):
            print(f"Le dossier '{folder_path}' n'existe pas.")
            return
        images = (
            glob.glob(os.path.join(folder_path, "*.[pP][nN][gG]"))
            + glob.glob(os.path.join(folder_path, "*.[jJ][pP][eE]?[gG]"))
            + glob.glob(os.path.join(folder_path, "*.[gG][iI][fF]"))
            + glob.glob(os.path.join(folder_path, "*.[tT][iI][iI]?[fF]"))
        )
        if not images:
            return
        last_image = max(images, key=os.path.getmtime)
        image = np.array(Image.open(last_image))
        self._set_image(image)

    def _show_grid(self):
        show = self.ui.pushButton_show_grid.isChecked()
        self.image_item.getView().showGrid(show, show)

    def _define_axis(self):
        if self.ui.pushButton_define_axis.isChecked():
            self.image_item.addItem(self.crosshair)
        else:
            self.image_item.removeItem(self.crosshair)
            self.roi_manager.change_reference_all(
                self.crosshair.pos(), self.crosshair.angle()
            )

    def _set_ui_from_model(self, model: PatternSequence):
        self.ui.treeWidget.clear()
        self.roi_manager.clear_all()
        self._next_pattern_id = 0
        descs = model.descriptions if model.descriptions is not None else [""] * len(model.patterns)
        for pat_idx, pattern in enumerate(model.patterns):
            root = QTreeWidgetItem(None, [""])
            self._attach_pattern_id(root, self._new_pattern_id())
            root.setFlags(root.flags() | Qt.ItemIsEditable)
            self.ui.treeWidget.insertTopLevelItem(pat_idx, root)
            self._set_pattern_label(root, pat_idx, descs[pat_idx])
            for _poly_idx, poly_pts in enumerate(pattern):
                node = QTreeWidgetItem(None, ["roi"])
                root.addChild(node)
                poly = self.roi_manager.register_polygon(
                    node, np.asarray(poly_pts, dtype=float)
                )
                poly.change_ref(self.crosshair.pos(), self.crosshair.angle())
        self.roi_manager.clear_visible_only()
        self._renumber_pattern_labels()
        self._write_table_ms(model)

    def _get_model_from_ui(self) -> PatternSequence:
        patterns: list[list[np.ndarray]] = []
        descriptions: list[str] = []
        for i in range(self.ui.treeWidget.topLevelItemCount()):
            pattern_item = self.ui.treeWidget.topLevelItem(i)
            descriptions.append(self._extract_description(pattern_item.text(0)))
            pattern_polys: list[np.ndarray] = []
            for j in range(pattern_item.childCount()):
                poly_item = pattern_item.child(j)
                poly = self.roi_manager.get_polygon(poly_item)
                if poly is None:
                    continue
                pattern_polys.append(poly.get_points())
            patterns.append(pattern_polys)
        timings_ms, durations_ms, sequence = self._read_table_ms()
        return PatternSequence(
            patterns=patterns,
            sequence=sequence,
            timings=[timedelta(milliseconds=int(t)) for t in timings_ms],
            durations=[timedelta(milliseconds=int(d)) for d in durations_ms],
            descriptions=descriptions,
        )

    def _new_model(self):
        self.model = PatternSequence(patterns=[], sequence=[], timings=[], durations=[], descriptions=[])
        self._set_ui_from_model(self.model)

    def _read_table_ms(self):
        timings, durations, sequence = [], [], []
        rows = self.ui.tableWidget.rowCount()
        for r in range(rows):
            t_item = self.ui.tableWidget.item(r, 0)
            d_item = self.ui.tableWidget.item(r, 1)
            s_item = self.ui.tableWidget.item(r, 2)
            try:
                if t_item and d_item and s_item:
                    t = int(t_item.text())
                    d = int(d_item.text())
                    s = int(s_item.text())
                    timings.append(t)
                    durations.append(d)
                    sequence.append(s)
            except Exception:
                continue
        return timings, durations, sequence

    def _write_table_ms(self, model: PatternSequence):
        t_ms = model.timings_milliseconds
        d_ms = model.durations_milliseconds
        seq = model.sequence
        self._updating_table = True
        self._ensure_desc_column()
        self.ui.tableWidget.setRowCount(len(seq))
        for r, (t, d, s) in enumerate(zip(t_ms, d_ms, seq)):
            self.ui.tableWidget.setItem(r, 0, QTableWidgetItem(str(int(t))))
            self.ui.tableWidget.setItem(r, 1, QTableWidgetItem(str(int(d))))
            self.ui.tableWidget.setItem(r, 2, QTableWidgetItem(str(int(s))))
            self._set_sequence_row_description(r, int(s))
        self._updating_table = False

    def _load_patterns_file(self):
        file_path = QFileDialog.getOpenFileName(self, "Select file", "", "")[0]
        if not file_path:
            return
        self.model = saving.load_pattern_sequence(file_path)
        self._set_ui_from_model(self.model)
        self.ui.lineEdit_file_path.setText(file_path)
        print(f"Loaded PatternSequence from {file_path}")

    def _save_file(self):
        file_path = self.ui.lineEdit_file_path.text()
        if not file_path:
            file_path = QFileDialog.getSaveFileName(self, "Save file", "", "")[0]
            if not file_path:
                return
            self.ui.lineEdit_file_path.setText(file_path)
        self.model = self._get_model_from_ui()
        saving.save_pattern_sequence(file_path, self.model)
        print(f"Saved PatternSequence to {file_path}")

    def _add_roi(self):
        if not self.ui.treeWidget.selectedItems():
            return
        selected = self.ui.treeWidget.selectedItems()[0]
        root = selected.parent() or selected
        a = 10
        positions = np.asarray([[a, a], [-a, a], [-a, -a], [a, -a]], dtype=float)
        node = QTreeWidgetItem(None, ["roi"])
        root.addChild(node)
        poly = self.roi_manager.register_polygon(node, positions)
        poly.change_ref(self.crosshair.pos(), self.crosshair.angle())
        self.model = self._get_model_from_ui()

    def _add_pattern(self):
        index = self.ui.treeWidget.topLevelItemCount()
        root = QTreeWidgetItem(None, [""])
        self._attach_pattern_id(root, self._new_pattern_id())
        root.setFlags(root.flags() | Qt.ItemIsEditable)
        self.ui.treeWidget.insertTopLevelItem(index, root)
        self._set_pattern_label(root, index, "")
        self._renumber_pattern_labels()
        self.model = self._get_model_from_ui()

    def _remove_selected_patterns(self):
        items = self.ui.treeWidget.selectedItems()
        if not items:
            return
        patterns = [it for it in items if it.parent() is None]
        leaves = [it for it in items if it.parent() is not None]
        for leaf in leaves:
            parent = leaf.parent()
            if parent is not None:
                parent.removeChild(leaf)
        if leaves:
            self.roi_manager.remove_items(leaves)
        if not patterns:
            self.model = self._get_model_from_ui()
            return
        old_ids = self._pattern_id_order()
        for item in patterns:
            del_idx = self.ui.treeWidget.indexOfTopLevelItem(item)
            if del_idx < 0:
                continue
            desc_cur = self._extract_description(item.text(0))
            use_count = 0
            for r in range(self.ui.tableWidget.rowCount()):
                it = self.ui.tableWidget.item(r, 2)
                if it and it.text().isdigit() and int(it.text()) == del_idx:
                    use_count += 1
            if use_count:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Warning)
                msg.setWindowTitle("Pattern is used")
                msg.setText(f"Pattern #{del_idx} ({desc_cur or 'no description'}) is used {use_count} times in the sequence.")
                remove_btn = msg.addButton("Remove rows", QMessageBox.DestructiveRole)
                replace_btn = msg.addButton("Replace uses…", QMessageBox.ActionRole)
                cancel_btn = msg.addButton(QMessageBox.Cancel)
                msg.exec()
                if msg.clickedButton() is cancel_btn:
                    continue
                if msg.clickedButton() is replace_btn:
                    remaining_old = [i for i in range(len(old_ids)) if i != del_idx]
                    if remaining_old:
                        chosen_old_idx, ok = QInputDialog.getInt(
                            self,
                            "Replace uses",
                            f"Replace all uses of #{del_idx} with OLD index:",
                            value=min(remaining_old),
                            minValue=min(remaining_old),
                            maxValue=max(remaining_old),
                        )
                        if not ok or chosen_old_idx not in remaining_old:
                            continue
                        self.ui.treeWidget.takeTopLevelItem(del_idx)
                        self.roi_manager.remove_items([item] + [item.child(i) for i in range(item.childCount())])
                        new_ids = self._pattern_id_order()
                        if 0 <= chosen_old_idx < len(old_ids):
                            target_pid = old_ids[chosen_old_idx]
                            if target_pid in new_ids:
                                target_new_idx = new_ids.index(target_pid)
                                self._remap_sequence_by_ids(
                                    old_ids, new_ids, on_deleted="replace", replace_with=target_new_idx
                                )
                                self._renumber_pattern_labels()
                                old_ids = new_ids
                                continue
                    rows_to_drop = []
                    for r in range(self.ui.tableWidget.rowCount()):
                        it = self.ui.tableWidget.item(r, 2)
                        if it and it.text().isdigit() and int(it.text()) == del_idx:
                            rows_to_drop.append(r)
                    for r in sorted(rows_to_drop, reverse=True):
                        self.ui.tableWidget.removeRow(r)
                    self._refresh_sequence_descriptions()
                else:
                    self.ui.treeWidget.takeTopLevelItem(del_idx)
                    self.roi_manager.remove_items([item] + [item.child(i) for i in range(item.childCount())])
                    new_ids = self._pattern_id_order()
                    self._remap_sequence_by_ids(old_ids, new_ids, on_deleted="drop")
                    self._renumber_pattern_labels()
                    old_ids = new_ids
            else:
                self.ui.treeWidget.takeTopLevelItem(del_idx)
                self.roi_manager.remove_items([item] + [item.child(i) for i in range(item.childCount())])
                new_ids = self._pattern_id_order()
                self._remap_sequence_by_ids(old_ids, new_ids, on_deleted="drop")
                self._renumber_pattern_labels()
                old_ids = new_ids
        self.model = self._get_model_from_ui()

    def _add_row_table(self):
        self.ui.tableWidget.insertRow(self.ui.tableWidget.rowCount())

    def _remove_row_table(self):
        rows = sorted({i.row() for i in self.ui.tableWidget.selectedIndexes()}, reverse=True)
        for r in rows:
            self.ui.tableWidget.removeRow(r)
