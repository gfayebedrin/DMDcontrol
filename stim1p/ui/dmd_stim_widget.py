import os
import glob
import numpy as np
from PIL import Image
from datetime import timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QMessageBox,
    QSpinBox,
    QTableWidgetItem,
    QTreeWidgetItem,
    QWidget,
)
import pyqtgraph as pg

from ..logic.calibration import (
    DMDCalibration,
    compute_calibration_from_square,
)
from ..logic.sequence import PatternSequence
from ..logic import saving

from .qt.DMD_stim_ui import Ui_widget_dmd_stim
from . import console, roi_manager, tree_table_manager


class _CalibrationDialog(QDialog):
    """Collect user inputs required to build a calibration."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Calibrate DMD")
        layout = QFormLayout(self)

        self._mirror_x = QSpinBox(self)
        self._mirror_x.setRange(1, 8192)
        self._mirror_x.setValue(100)
        layout.addRow("Mirrors (X)", self._mirror_x)

        self._mirror_y = QSpinBox(self)
        self._mirror_y.setRange(1, 8192)
        self._mirror_y.setValue(100)
        layout.addRow("Mirrors (Y)", self._mirror_y)

        self._pixel_size = QDoubleSpinBox(self)
        self._pixel_size.setRange(1e-6, 10_000.0)
        self._pixel_size.setDecimals(6)
        self._pixel_size.setValue(1.0)
        layout.addRow("Camera pixel size (µm)", self._pixel_size)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> tuple[int, int, float]:
        return self._mirror_x.value(), self._mirror_y.value(), self._pixel_size.value()


class StimDMDWidget(QWidget):
    def __init__(self, name="Stimulation DMD Widget", dmd=None, parent=None):
        super().__init__(parent=parent)
        self.ui = Ui_widget_dmd_stim()
        self.ui.setupUi(self)
        self.setObjectName(name)
        self.last_roi = None
        self.crosshair = pg.CrosshairROI([0, 0], [20, 20])
        self.dmd = dmd
        self.image_item = pg.ImageView(parent=self, view=pg.PlotItem())
        self.ui.stackedWidget_image.addWidget(self.image_item)
        self.roi_manager = roi_manager.RoiManager(self.image_item)
        self.tree_manager = tree_table_manager.TreeManager(self)
        self.table_manager = tree_table_manager.TableManager(self)
        self._connect()
        self._console = console.Console(self.ui.plainTextEdit_console_output)
        self._calibration: DMDCalibration | None = None
        self._current_image: np.ndarray | None = None

    @property
    def model(self) -> PatternSequence:
        if self._calibration is None:
            raise RuntimeError(
                "A DMD calibration must be available before exporting patterns."
            )
        patterns: list[list[np.ndarray]] = []
        descriptions: list[str] = []
        for i in range(self.ui.treeWidget.topLevelItemCount()):
            pattern_item = self.ui.treeWidget.topLevelItem(i)
            assert pattern_item is not None
            descriptions.append(
                tree_table_manager.extract_description(pattern_item.text(0))
            )
            pattern_polys: list[np.ndarray] = []
            for j in range(pattern_item.childCount()):
                poly_item = pattern_item.child(j)
                poly = self.roi_manager.get_polygon(poly_item)
                if poly is None:
                    continue
                points = poly.get_points()
                micrometres = self._calibration.camera_to_micrometre(points.T).T
                pattern_polys.append(micrometres)
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
        if (
            self._calibration is None
            and any(len(pattern) for pattern in model.patterns)
        ):
            raise RuntimeError(
                "Load or compute a DMD calibration before importing patterns."
            )
        descs = (
            model.descriptions
            if model.descriptions is not None
            else [""] * len(model.patterns)
        )
        for pat_idx, pattern in enumerate(model.patterns):

            root = QTreeWidgetItem([""])

            self.tree_manager.attach_pattern_id(
                root, self.tree_manager.new_pattern_id()
            )
            root.setFlags(root.flags() | Qt.ItemFlag.ItemIsEditable)
            self.ui.treeWidget.insertTopLevelItem(pat_idx, root)
            self.tree_manager.set_pattern_label(root, pat_idx, descs[pat_idx])
            for _poly_idx, poly_pts in enumerate(pattern):
                node = QTreeWidgetItem(["roi"])
                root.addChild(node)
                points = np.asarray(poly_pts, dtype=float)
                if self._calibration is not None:
                    points = self._calibration.micrometre_to_camera(points.T).T
                poly = self.roi_manager.register_polygon(node, points)
                poly.change_ref(self.crosshair.pos(), self.crosshair.angle())
        self.roi_manager.clear_visible_only()
        self.tree_manager.renumber_pattern_labels()
        self._write_table_ms(model)

    @property
    def calibration(self) -> DMDCalibration | None:
        return self._calibration

    @calibration.setter
    def calibration(self, calibration: DMDCalibration | None):
        self._calibration = calibration

    def _connect(self):
        self.ui.pushButton_load_image.clicked.connect(self._load_image)
        self.ui.pushButton_change_folder.clicked.connect(self._change_folder)
        self.ui.pushButton_refresh_image.clicked.connect(self._refresh_image)
        self.ui.pushButton_show_grid.clicked.connect(self._show_grid)
        self.ui.pushButton_define_axis.clicked.connect(self._define_axis)
        self.ui.pushButton_add_pattern.clicked.connect(
            self.tree_manager.add_pattern
        )
        self.ui.pushButton_add_roi.clicked.connect(self.tree_manager.add_roi)
        self.ui.pushButton_add_row.clicked.connect(self._add_row_table)
        self.ui.pushButton_remove_row.clicked.connect(self._remove_row_table)
        self.ui.pushButton_remove_pattern.clicked.connect(
            self.tree_manager.remove_selected_patterns
        )
        self.ui.pushButton_new_file.clicked.connect(self._new_model)
        self.ui.pushButton_load_patterns.clicked.connect(self._load_patterns_file)
        self.ui.pushButton_save_patterns.clicked.connect(self._save_file)
        self.ui.pushButton_calibrate_dmd.clicked.connect(self._calibrate_dmd)
        self.ui.treeWidget.itemClicked.connect(
            lambda item, _col: self.roi_manager.show_for_item(item)
        )
        self.ui.treeWidget.itemChanged.connect(self.tree_manager.on_item_changed)
        self.ui.tableWidget.itemChanged.connect(self.table_manager.on_item_changed)

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
        self._current_image = image

    def _load_image(self, path: str = ""):
        try:
            path = QFileDialog.getOpenFileName(self, "Select file", "", "")[0]
            if not path:
                return
            image = np.array(Image.open(path))
            self._set_image(image)
        except Exception:
            pass

    def _select_calibration_points(self) -> np.ndarray | None:
        items = self.ui.treeWidget.selectedItems()
        for item in items:
            poly = self.roi_manager.get_polygon(item)
            if poly is not None:
                return poly.get_points()
        for i in range(self.ui.treeWidget.topLevelItemCount()):
            pattern_item = self.ui.treeWidget.topLevelItem(i)
            for j in range(pattern_item.childCount()):
                child = pattern_item.child(j)
                poly = self.roi_manager.get_polygon(child)
                if poly is not None:
                    return poly.get_points()
        return None

    def _calibrate_dmd(self):
        if self._current_image is None:
            QMessageBox.warning(
                self,
                "No image loaded",
                "Load a calibration image before starting the DMD calibration.",
            )
            return

        polygon_points = self._select_calibration_points()
        if polygon_points is None:
            QMessageBox.warning(
                self,
                "Calibration ROI missing",
                "Create and select a polygon outlining the calibration square.",
            )
            return

        dialog = _CalibrationDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        mirrors_x, mirrors_y, pixel_size = dialog.values()
        camera_shape = (
            int(self._current_image.shape[1]),
            int(self._current_image.shape[0]),
        )
        if self.dmd is not None and hasattr(self.dmd, "shape"):
            try:
                dmd_shape = tuple(int(v) for v in self.dmd.shape)
            except Exception:
                dmd_shape = (1024, 768)
        else:
            dmd_shape = (1024, 768)

        try:
            calibration = compute_calibration_from_square(
                polygon_points,
                (mirrors_x, mirrors_y),
                pixel_size,
                camera_shape=camera_shape,
                dmd_shape=dmd_shape,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Calibration failed", str(exc))
            return

        self.calibration = calibration
        print(
            "Updated DMD calibration: pixels/mirror=(%.3f, %.3f), µm/mirror=(%.3f, %.3f)"
            % (
                calibration.camera_pixels_per_mirror[0],
                calibration.camera_pixels_per_mirror[1],
                calibration.micrometers_per_mirror[0],
                calibration.micrometers_per_mirror[1],
            )
        )

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
        print("Loaded empty PatternSequence")

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
        self.table_manager.ensure_desc_column()
        self.ui.tableWidget.setRowCount(len(seq))
        for r, (t, d, s) in enumerate(zip(t_ms, d_ms, seq)):
            self.ui.tableWidget.setItem(r, 0, QTableWidgetItem(str(int(t))))
            self.ui.tableWidget.setItem(r, 1, QTableWidgetItem(str(int(d))))
            self.ui.tableWidget.setItem(r, 2, QTableWidgetItem(str(int(s))))
            self.table_manager.set_sequence_row_description(r, int(s))
        self._updating_table = False

    def _load_patterns_file(self):
        file_path = QFileDialog.getOpenFileName(self, "Select file", "", "")[0]
        if not file_path:
            return
        if self._calibration is None:
            QMessageBox.warning(
                self,
                "Calibration required",
                "Load or compute a DMD calibration before loading patterns.",
            )
            return
        try:
            self.model = saving.load_pattern_sequence(file_path)
        except RuntimeError as exc:
            QMessageBox.warning(self, "Calibration required", str(exc))
            return
        self.ui.lineEdit_file_path.setText(file_path)
        print(f"Loaded PatternSequence from {file_path}")

    def _save_file(self):
        file_path = self.ui.lineEdit_file_path.text()
        if not file_path:
            file_path = QFileDialog.getSaveFileName(self, "Save file", "", "")[0]
            if not file_path:
                return
            self.ui.lineEdit_file_path.setText(file_path)
        try:
            model = self.model
        except RuntimeError as exc:
            QMessageBox.warning(self, "Calibration required", str(exc))
            return
        saving.save_pattern_sequence(file_path, model)
        print(f"Saved PatternSequence to {file_path}")

    def _add_row_table(self):
        self.ui.tableWidget.insertRow(self.ui.tableWidget.rowCount())

    def _remove_row_table(self):
        rows = sorted(
            {i.row() for i in self.ui.tableWidget.selectedIndexes()}, reverse=True
        )
        for r in rows:
            self.ui.tableWidget.removeRow(r)
