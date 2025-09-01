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
)
import pyqtgraph as pg

from ..logic.sequence import PatternSequence
from ..logic import saving

from .qt.DMD_stim_ui import Ui_widget_dmd_stim
from . import console, roi_manager, tree_widget_manager


class StimDMDWidget(QWidget):
    def __init__(self, name="Stimulation DMD Widget", dmd=None, parent=None):
        super().__init__(parent=parent)
        self.ui = Ui_widget_dmd_stim()
        self.ui.setupUi(self)
        self.setObjectName(name)
        self.last_roi = None
        self.crosshair = pg.CrosshairROI([0, 0], [20, 20])
        self.dmd = dmd
        self._next_pattern_id: int = 0
        self.image_item = pg.ImageView(parent=self, view=pg.PlotItem())
        self.ui.stackedWidget_image.addWidget(self.image_item)
        self.roi_manager = roi_manager.RoiManager(self.image_item)
        self.tree_widget_manager = tree_widget_manager.TreeWidgetManager(self)
        self._connect()
        self._console = console.Console(self.ui.plainTextEdit_console_output)
        self._updating_table = False

    @property
    def model(self) -> PatternSequence:
        patterns: list[list[np.ndarray]] = []
        descriptions: list[str] = []
        for i in range(self.ui.treeWidget.topLevelItemCount()):
            pattern_item = self.ui.treeWidget.topLevelItem(i)
            assert pattern_item is not None
            descriptions.append(
                self.tree_widget_manager.extract_description(pattern_item.text(0))
            )
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

    @model.setter
    def model(self, model: PatternSequence):
        self.ui.treeWidget.clear()
        self.roi_manager.clear_all()
        self._next_pattern_id = 0
        descs = (
            model.descriptions
            if model.descriptions is not None
            else [""] * len(model.patterns)
        )
        for pat_idx, pattern in enumerate(model.patterns):
            
            root = QTreeWidgetItem([""])
            
            self.tree_widget_manager.attach_pattern_id(
                root, self.tree_widget_manager.new_pattern_id()
            )
            root.setFlags(root.flags() | Qt.ItemFlag.ItemIsEditable)
            self.ui.treeWidget.insertTopLevelItem(pat_idx, root)
            self.tree_widget_manager.set_pattern_label(root, pat_idx, descs[pat_idx])
            for _poly_idx, poly_pts in enumerate(pattern):
                node = QTreeWidgetItem(["roi"])
                root.addChild(node)
                poly = self.roi_manager.register_polygon(
                    node, np.asarray(poly_pts, dtype=float)
                )
                poly.change_ref(self.crosshair.pos(), self.crosshair.angle())
        self.roi_manager.clear_visible_only()
        self.tree_widget_manager.renumber_pattern_labels()
        self._write_table_ms(model)

    def _connect(self):
        self.ui.pushButton_load_image.clicked.connect(self._load_image)
        self.ui.pushButton_change_folder.clicked.connect(self._change_folder)
        self.ui.pushButton_refresh_image.clicked.connect(self._refresh_image)
        self.ui.pushButton_show_grid.clicked.connect(self._show_grid)
        self.ui.pushButton_define_axis.clicked.connect(self._define_axis)
        self.ui.pushButton_add_pattern.clicked.connect(
            self.tree_widget_manager.add_pattern
        )
        self.ui.pushButton_add_roi.clicked.connect(self.tree_widget_manager.add_roi)
        self.ui.pushButton_add_row.clicked.connect(self._add_row_table)
        self.ui.pushButton_remove_row.clicked.connect(self._remove_row_table)
        self.ui.pushButton_remove_pattern.clicked.connect(
            self.tree_widget_manager.remove_selected_patterns
        )
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
                desc = self.tree_widget_manager.extract_description(item.text(col))
                self.tree_widget_manager.set_pattern_label(item, idx, desc)
                self.tree_widget_manager.refresh_sequence_descriptions()

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if self._updating_table:
            return
        if item.column() == 2:
            try:
                idx = int(item.text())
            except Exception:
                return
            self.tree_widget_manager.set_sequence_row_description(item.row(), idx)

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
                None, "Select a folder:", filename, QFileDialog.Option.ShowDirsOnly
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
        self.image_item.getView().showGrid(show, show) # pyright: ignore[reportAttributeAccessIssue]

    def _define_axis(self):
        if self.ui.pushButton_define_axis.isChecked():
            self.image_item.addItem(self.crosshair) # pyright: ignore[reportAttributeAccessIssue]
        else:
            self.image_item.removeItem(self.crosshair) # pyright: ignore[reportAttributeAccessIssue]
            self.roi_manager.change_reference_all(
                self.crosshair.pos(), self.crosshair.angle()
            )

    def _new_model(self):
        self.model = PatternSequence(
            patterns=[], sequence=[], timings=[], durations=[], descriptions=[]
        )

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
        self.tree_widget_manager.ensure_desc_column()
        self.ui.tableWidget.setRowCount(len(seq))
        for r, (t, d, s) in enumerate(zip(t_ms, d_ms, seq)):
            self.ui.tableWidget.setItem(r, 0, QTableWidgetItem(str(int(t))))
            self.ui.tableWidget.setItem(r, 1, QTableWidgetItem(str(int(d))))
            self.ui.tableWidget.setItem(r, 2, QTableWidgetItem(str(int(s))))
            self.tree_widget_manager.set_sequence_row_description(r, int(s))
        self._updating_table = False

    def _load_patterns_file(self):
        file_path = QFileDialog.getOpenFileName(self, "Select file", "", "")[0]
        if not file_path:
            return
        self.model = saving.load_pattern_sequence(file_path)
        self.ui.lineEdit_file_path.setText(file_path)
        print(f"Loaded PatternSequence from {file_path}")

    def _save_file(self):
        file_path = self.ui.lineEdit_file_path.text()
        if not file_path:
            file_path = QFileDialog.getSaveFileName(self, "Save file", "", "")[0]
            if not file_path:
                return
            self.ui.lineEdit_file_path.setText(file_path)
        saving.save_pattern_sequence(file_path, self.model)
        print(f"Saved PatternSequence to {file_path}")

    def _add_row_table(self):
        self.ui.tableWidget.insertRow(self.ui.tableWidget.rowCount())

    def _remove_row_table(self):
        rows = sorted(
            {i.row() for i in self.ui.tableWidget.selectedIndexes()}, reverse=True
        )
        for r in rows:
            self.ui.tableWidget.removeRow(r)
