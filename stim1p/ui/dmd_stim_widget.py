import os
import glob
import numpy as np
from PIL import Image
from datetime import timedelta

from PySide6.QtCore import QEvent, QEventLoop, QObject, QPointF, QRectF, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QMessageBox,
    QSpinBox,
    QTableWidgetItem,
    QTreeWidgetItem,
    QWidget,
    QGraphicsRectItem,
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


class _InteractiveRectangleCapture(QObject):
    """Helper to let the user draw a temporary rectangle on the image view."""

    def __init__(self, view_box: pg.ViewBox, parent: QWidget | None = None):
        super().__init__(parent)
        self._view_box = view_box
        self._scene = view_box.scene()
        self._rect_item: QGraphicsRectItem | None = None
        self._loop: QEventLoop | None = None
        self._dragging = False
        self._start_view: QPointF | None = None
        self._result: QRectF | None = None
        self._original_mouse_enabled: tuple[bool, bool] = (
            True,
            True,
        )

    def exec(self) -> QRectF | None:
        if self._scene is None:
            return None
        self._loop = QEventLoop()
        self._scene.installEventFilter(self)
        mouse_enabled = self._view_box.state.get("mouseEnabled", (True, True))
        self._original_mouse_enabled = (
            bool(mouse_enabled[0]),
            bool(mouse_enabled[1]),
        )
        self._view_box.setMouseEnabled(False, False)
        self._loop.exec()
        self._scene.removeEventFilter(self)
        self._view_box.setMouseEnabled(*self._original_mouse_enabled)
        self._cleanup_rect()
        result = self._result
        self._result = None
        self._loop = None
        return result

    def eventFilter(self, _obj, event):  # noqa: D401 - Qt signature
        if self._loop is None:
            return False
        etype = event.type()
        if etype == QEvent.GraphicsSceneMousePress:
            if not self._view_box.sceneBoundingRect().contains(event.scenePos()):
                return False
            if event.button() == Qt.MouseButton.LeftButton:
                self._dragging = True
                self._start_view = self._view_box.mapSceneToView(event.scenePos())
                if self._rect_item is None:
                    self._rect_item = QGraphicsRectItem()
                    self._rect_item.setPen(
                        pg.mkPen(color="yellow", width=2, style=Qt.PenStyle.DashLine)
                    )
                    self._rect_item.setZValue(10_000)
                    self._view_box.addItem(self._rect_item)
                self._rect_item.setRect(
                    QRectF(self._start_view, self._start_view).normalized()
                )
                event.accept()
                return True
            if event.button() == Qt.MouseButton.RightButton:
                self._finish(None)
                event.accept()
                return True
        elif etype == QEvent.GraphicsSceneMouseMove:
            if not self._dragging or self._start_view is None:
                return False
            current_view = self._view_box.mapSceneToView(event.scenePos())
            rect = QRectF(self._start_view, current_view).normalized()
            if self._rect_item is not None:
                self._rect_item.setRect(rect)
            event.accept()
            return True
        elif etype == QEvent.GraphicsSceneMouseRelease:
            if not self._dragging or event.button() != Qt.MouseButton.LeftButton:
                return False
            self._dragging = False
            if self._start_view is None:
                self._finish(None)
                event.accept()
                return True
            current_view = self._view_box.mapSceneToView(event.scenePos())
            rect = QRectF(self._start_view, current_view).normalized()
            if rect.width() <= 0.0 or rect.height() <= 0.0:
                self._finish(None)
            else:
                self._finish(rect)
            event.accept()
            return True
        elif etype == QEvent.KeyPress and event.key() == Qt.Key.Key_Escape:
            self._finish(None)
            event.accept()
            return True
        return False

    def _finish(self, rect: QRectF | None) -> None:
        self._result = rect
        self._dragging = False
        self._start_view = None
        if self._loop is not None and self._loop.isRunning():
            self._loop.quit()

    def _cleanup_rect(self) -> None:
        if self._rect_item is not None:
            self._view_box.removeItem(self._rect_item)
            self._rect_item = None

class StimDMDWidget(QWidget):
    def __init__(self, name="Stimulation DMD Widget", dmd=None, parent=None):
        super().__init__(parent=parent)
        self.ui = Ui_widget_dmd_stim()
        self.ui.setupUi(self)
        self.setObjectName(name)
        self.last_roi = None
        self.crosshair = pg.CrosshairROI([0, 0], [20, 20])
        self.dmd = dmd
        # GraphicsLayoutWidget gives us fine control over plot + histogram layout.
        self._graphics_widget = pg.GraphicsLayoutWidget(parent=self)
        self._plot_item = self._graphics_widget.addPlot()
        self._view_box = self._plot_item.getViewBox()
        # Normalise the plot behaviour: no padding, camera-style orientation.
        if hasattr(self._view_box, "setPadding"):
            self._view_box.setPadding(0.0)
        elif hasattr(self._view_box, "setDefaultPadding"):
            self._view_box.setDefaultPadding(0.0)
        self._view_box.setAspectLocked(False)
        self._view_box.invertY(True)
        self._view_box.setMouseEnabled(True, True)
        self._view_box.enableAutoRange(pg.ViewBox.XYAxes, enable=True)
        self._view_box.setLimits(xMin=0.0, yMin=0.0)

        # ImageItem renders the camera frame; keep it behind ROIs.
        self._image_item = pg.ImageItem()
        self._image_item.setZValue(-1)
        # Attach image directly to the view box so it follows pans/zooms.
        self._view_box.addItem(self._image_item)

        # HistogramLUTWidget provides the contrast controls that users expect.
        self._hist_widget = pg.HistogramLUTWidget(parent=self)
        self._hist_widget.setImageItem(self._image_item)
        self._hist_widget.setMinimumWidth(140)
        self._current_levels: tuple[float, float] | None = None
        self._hist_widget.region.sigRegionChanged.connect(self._store_histogram_levels)

        self._image_container = QWidget(parent=self)
        container_layout = QHBoxLayout(self._image_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(6)
        container_layout.addWidget(self._graphics_widget, 1)
        container_layout.addWidget(self._hist_widget, 0)

        self.ui.stackedWidget_image.addWidget(self._image_container)
        self.roi_manager = roi_manager.RoiManager(self._plot_item)
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

    def _get_view_box(self) -> pg.ViewBox:
        return self._view_box

    def _set_image(self, image: np.ndarray) -> None:
        image = np.asarray(image)
        if image.ndim not in (2, 3):
            raise ValueError("Images must be 2D grayscale or 3-channel colour arrays.")
        height, width = image.shape[:2]
        previous_levels = self._current_levels

        view_box = self._get_view_box()
        try:
            previous_range = view_box.viewRange()
        except Exception:
            previous_range = None

        # ImageView expects column-major data; transpose so axes remain aligned.
        display_image = (
            image.T if image.ndim == 2 else np.transpose(image, axes=(1, 0, 2))
        )
        auto_levels = self._image_item.image is None or previous_levels is None
        levels = None if auto_levels else previous_levels
        self._image_item.setImage(
            display_image,
            autoLevels=auto_levels,
            autoDownsample=False,
            levels=levels,
        )
        self._image_item.setRect(QRectF(0.0, 0.0, float(width), float(height)))
        self._image_item.setPos(0.0, 0.0)
        if levels is None:
            self._store_histogram_levels()
        else:
            self._hist_widget.region.setRegion(levels)

        self._view_box.enableAutoRange(pg.ViewBox.XYAxes, enable=False)
        self._view_box.setLimits(
            xMin=0.0,
            yMin=0.0,
            xMax=float(width),
            yMax=float(height),
        )
        if previous_range is not None:
            x_range, y_range = previous_range
            self._view_box.setRange(xRange=x_range, yRange=y_range, padding=0.0)
        else:
            self._view_box.setRange(
                xRange=(0.0, float(width)),
                yRange=(0.0, float(height)),
                padding=0.0,
            )
        self._current_image = image

    def _store_histogram_levels(self) -> None:
        try:
            low, high = self._hist_widget.region.getRegion()
            self._current_levels = (float(low), float(high))
        except Exception:
            self._current_levels = None

    def _load_image(self, path: str = ""):
        try:
            path = QFileDialog.getOpenFileName(self, "Select file", "", "")[0]
            if not path:
                return
            image = np.array(Image.open(path))
            self._set_image(image)
        except Exception:
            pass

    def _calibrate_dmd(self):
        initial_dir = self.ui.lineEdit_image_folder_path.text().strip()
        file_filter = (
            "Image files (*.png *.jpg *.jpeg *.tif *.tiff *.gif);;All files (*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select calibration image",
            initial_dir if initial_dir else "",
            file_filter,
        )
        if not file_path:
            return
        try:
            with Image.open(file_path) as pil_image:
                calibration_image = np.array(pil_image)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Calibration image error",
                f"Unable to load calibration image:\n{exc}",
            )
            return

        previous_image = self._current_image
        previous_view = self._capture_view_state()
        selected_items = self.ui.treeWidget.selectedItems()
        selected_item = selected_items[0] if selected_items else None
        self.roi_manager.clear_visible_only()

        self._set_image(calibration_image)

        polygon_points = self._prompt_calibration_rectangle()
        if polygon_points is None:
            QMessageBox.information(
                self,
                "Calibration cancelled",
                "No calibration rectangle was drawn. Calibration has been cancelled.",
            )
            self._restore_after_calibration(previous_image, previous_view, selected_item)
            return

        dialog = _CalibrationDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._restore_after_calibration(previous_image, previous_view, selected_item)
            return

        mirrors_x, mirrors_y, pixel_size = dialog.values()
        camera_shape = (
            int(calibration_image.shape[1]),
            int(calibration_image.shape[0]),
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
            self._restore_after_calibration(previous_image, previous_view, selected_item)
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
        self._restore_after_calibration(previous_image, previous_view, selected_item)

    def _prompt_calibration_rectangle(self) -> np.ndarray | None:
        prompt = QMessageBox(self)
        prompt.setWindowTitle("Select calibration square")
        prompt.setIcon(QMessageBox.Icon.Information)
        prompt.setText("Draw a rectangle around the calibration square.")
        prompt.setInformativeText(
            "Left-click and drag to draw. Right-click or press Esc to cancel."
        )
        prompt.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok
        )
        if prompt.exec() != QMessageBox.StandardButton.Ok:
            return None

        capture = _InteractiveRectangleCapture(self._get_view_box(), self)
        rect = capture.exec()
        if rect is None or rect.width() <= 0.0 or rect.height() <= 0.0:
            return None
        x0, x1 = rect.left(), rect.right()
        y0, y1 = rect.top(), rect.bottom()
        return np.array(
            [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
            dtype=float,
        )

    def _capture_view_state(
        self,
    ) -> tuple[tuple[float, float], tuple[float, float]] | None:
        view = self._get_view_box()
        try:
            x_range, y_range = view.viewRange()
        except Exception:
            return None
        return (tuple(x_range), tuple(y_range))

    def _restore_after_calibration(
        self,
        previous_image: np.ndarray | None,
        previous_view_range: tuple[tuple[float, float], tuple[float, float]] | None,
        selected_item: QTreeWidgetItem | None,
    ) -> None:
        if previous_image is not None:
            self._set_image(previous_image)
            if previous_view_range is not None:
                x_range, y_range = previous_view_range
                self._get_view_box().setRange(
                    xRange=x_range,
                    yRange=y_range,
                    padding=0.0,
                )
        else:
            self._image_item.clear()
            self._current_levels = None
            self._current_image = None

        if selected_item is not None:
            self.roi_manager.show_for_item(selected_item)
        else:
            self.roi_manager.clear_visible_only()

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
        self._plot_item.showGrid(show, show)

    def _define_axis(self):
        if self.ui.pushButton_define_axis.isChecked():
            self._plot_item.addItem(self.crosshair)
        else:
            self._plot_item.removeItem(self.crosshair)
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
