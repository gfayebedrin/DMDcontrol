"""Widget for DMD stimulation"""

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
    QTreeWidget,
)
import pyqtgraph as pg

from ..logic.sequence import PatternSequence
from ..logic import saving

from .qt.DMD_stim_ui import Ui_widget_dmd_stim
from . import console, roi_manager


class StimDMDWidget(QWidget):
    """DMD Stimulation Widget"""

    def __init__(self, name="Stimulation DMD Widget", dmd=None, parent=None):
        super().__init__(parent=parent)
        self.ui = Ui_widget_dmd_stim()
        self.ui.setupUi(self)
        self.setObjectName(name)
        self.last_roi = None
        self.crosshair = pg.CrosshairROI([0, 0], [20, 20])
        self.dmd = dmd
        self.model: PatternSequence | None = None  # TODO rename to pattern_sequence

        # self.setWindowIcon(QIcon.fromTheme(QIcon.name("accessories-calculator")))
        self.image_item = pg.ImageView(parent=self, view=pg.PlotItem())
        self.ui.stackedWidget_image.addWidget(self.image_item)

        self.roi_manager = roi_manager.RoiManager(self.image_item)
        self.roi_manager.polygonEdited.connect(
            lambda *_: setattr(self, "model", self._get_model_from_ui())
        )

        self.ui.treeWidget.setEditTriggers(
            QTreeWidget.DoubleClicked  # Double-clic pour éditer
            | QTreeWidget.EditKeyPressed  # Appui sur F2 ou Entrée pour éditer
        )

        self._connect()

        # --- Console setup + tee redirection ---
        self._console = console.Console(self.ui.plainTextEdit_console_output)

    def _connect(self):
        """Connect signals and slots"""
        self.ui.pushButton_load_image.clicked.connect(self._load_image)
        self.ui.pushButton_change_folder.clicked.connect(self._change_folder)
        self.ui.pushButton_refresh_image.clicked.connect(self._refresh_image)
        self.ui.pushButton_show_grid.clicked.connect(self._show_grid)
        self.ui.pushButton_define_axis.clicked.connect(self._define_axis)
        self.ui.pushButton_add_pattern.clicked.connect(self._add_pattern)
        self.ui.pushButton_add_roi.clicked.connect(self._add_roi)

        self.ui.pushButton_add_row.clicked.connect(self._add_row_table)
        self.ui.pushButton_remove_row.clicked.connect(self._remove_row_table)

        self.ui.pushButton_remove_pattern.clicked.connect(self._remove_pattern_or_roi)
        self.ui.pushButton_load_patterns.clicked.connect(self._load_patterns_file)
        self.ui.pushButton_save_patterns.clicked.connect(self._save_file)
        self.ui.treeWidget.itemClicked.connect(self.roi_manager.show_for_item)

    # ----------------------------------------------------------------------

    def closeEvent(self, event):
        self._console.restore_original_streams()
        super().closeEvent(event)

    def update_ui(self, data):
        """Update the UI with new data"""
        if self.dmd is not None:
            self._set_image(data)

    def set_up(self):
        """Set up the widget"""

    def _set_image(self, image):
        self.image_item.setImage(image.T)

    def _load_image(self, path: str = ""):
        try:
            path = QFileDialog.getOpenFileName(self, "Select file", "", "")[0]
            image = np.array(Image.open(path))
            self._set_image(image)
        except AttributeError:
            pass

    def _change_folder(self):
        try:
            filename = self.ui.lineEdit_image_folder_path.text()
            if filename == "":
                filename = "C:\\"
            path = QFileDialog.getExistingDirectory(
                None, "Select a folder:", filename, QFileDialog.ShowDirsOnly
            )
            self.ui.lineEdit_image_folder_path.setText(path)
        except AttributeError:
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
        # Trie les images par date de modification (la plus récente en premier)
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
        # --- Tree + ROIs ---
        self.ui.treeWidget.clear()
        self.roi_manager.clear_all()

        for pat_idx, pattern in enumerate(model.patterns):
            root = QTreeWidgetItem(None, [f"pattern_{pat_idx}"])
            root.setData(0, Qt.UserRole, ("pattern", pat_idx))
            root.setFlags(root.flags() | Qt.ItemIsEditable)
            self.ui.treeWidget.insertTopLevelItem(pat_idx, root)

            for poly_idx, poly_pts in enumerate(pattern):
                node = QTreeWidgetItem(None, [f"polygon_{poly_idx}"])
                node.setData(0, Qt.UserRole, ("polygon", pat_idx, poly_idx))
                node.setFlags(node.flags() | Qt.ItemIsEditable)
                root.addChild(node)

                poly = self.roi_manager.register_polygon(
                    node, np.asarray(poly_pts, dtype=float)
                )
                # rebase to current crosshair if present
                poly.change_ref(self.crosshair.pos(), self.crosshair.angle())

        self.roi_manager.clear_visible_only()

        # --- Timings table ---
        self._write_table_ms(model)

    def _get_model_from_ui(self) -> PatternSequence:
        # 1) Build patterns from the tree, in UI order
        patterns: list[list[np.ndarray]] = []
        for i in range(self.ui.treeWidget.topLevelItemCount()):
            pattern_item = self.ui.treeWidget.topLevelItem(i)
            pattern_polys: list[np.ndarray] = []
            for j in range(pattern_item.childCount()):
                poly_item = pattern_item.child(j)
                poly = self.roi_manager.get_polygon(poly_item)
                if poly is None:
                    continue
                pattern_polys.append(poly.get_points())
            patterns.append(pattern_polys)

        # 2) Read timings/durations/sequence from the table
        timings_ms, durations_ms, sequence = self._read_table_ms()

        return PatternSequence(
            patterns=patterns,
            sequence=sequence,
            timings=[timedelta(milliseconds=int(t)) for t in timings_ms],
            durations=[timedelta(milliseconds=int(d)) for d in durations_ms],
        )

    def _new_model(self):
        self.model = PatternSequence(patterns=[], sequence=[], timings=[], durations=[])
        self._set_ui_from_model(self.model)

    def _read_table_ms(self):
        timings, durations, sequence = [], [], []
        rows = self.ui.tableWidget.rowCount()
        for r in range(rows):
            t_item = self.ui.tableWidget.item(r, 0)
            d_item = self.ui.tableWidget.item(r, 1)
            s_item = self.ui.tableWidget.item(r, 2)
            if t_item and d_item and s_item:
                timings.append(int(t_item.text()))
                durations.append(int(d_item.text()))
                sequence.append(int(s_item.text()))
        return timings, durations, sequence

    def _write_table_ms(self, model: PatternSequence):
        t_ms = model.timings_milliseconds
        d_ms = model.durations_milliseconds
        seq = model.sequence
        self.ui.tableWidget.setRowCount(len(seq))
        for r, (t, d, s) in enumerate(zip(t_ms, d_ms, seq)):
            self.ui.tableWidget.setItem(r, 0, QTableWidgetItem(str(int(t))))
            self.ui.tableWidget.setItem(r, 1, QTableWidgetItem(str(int(d))))
            self.ui.tableWidget.setItem(r, 2, QTableWidgetItem(str(int(s))))

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

        # Build a fresh model from the current UI state
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

        node = QTreeWidgetItem(None, ["new roi"])
        node.setFlags(node.flags() | Qt.ItemIsEditable)
        root.addChild(node)

        poly = self.roi_manager.register_polygon(node, positions)
        poly.change_ref(self.crosshair.pos(), self.crosshair.angle())

    def _add_pattern(self):
        index = self.ui.treeWidget.topLevelItemCount()
        root = QTreeWidgetItem(None, ["new pattern"])
        root.setFlags(root.flags() | Qt.ItemIsEditable)
        self.ui.treeWidget.insertTopLevelItem(index, root)

    def _remove_pattern_or_roi(self):
        items = self.ui.treeWidget.selectedItems()
        if not items:
            return

        # Remove from tree first but collect items to unregister
        items_to_unregister = []
        for item in items:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
                items_to_unregister.append(item)
            else:
                idx = self.ui.treeWidget.indexOfTopLevelItem(item)
                # collect children and the pattern item
                for i in range(item.childCount()):
                    items_to_unregister.append(item.child(i))
                self.ui.treeWidget.takeTopLevelItem(idx)
                items_to_unregister.append(item)

        self.roi_manager.remove_items(items_to_unregister)

    def _add_row_table(self):
        self.ui.tableWidget.insertRow(self.ui.tableWidget.rowCount())

    def _remove_row_table(self):
        rows = sorted(
            {i.row() for i in self.ui.tableWidget.selectedIndexes()}, reverse=True
        )
        for r in rows:
            self.ui.tableWidget.removeRow(r)
