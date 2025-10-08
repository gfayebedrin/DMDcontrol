import os
import glob
from pathlib import Path
import numpy as np
from PIL import Image
from datetime import timedelta

from PySide6.QtCore import (
    QEvent,
    QEventLoop,
    QObject,
    QPointF,
    QRectF,
    Qt,
    QSettings,
    QStandardPaths,
    QTimer,
)
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

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        default_mirrors: tuple[int, int] = (100, 100),
        default_pixel_size: float = 1.0,
    ):
        super().__init__(parent)
        self.setWindowTitle("Calibrate DMD")
        layout = QFormLayout(self)

        self._mirror_x = QSpinBox(self)
        self._mirror_x.setRange(1, 8192)
        default_mirror_x = max(1, min(8192, int(default_mirrors[0])))
        self._mirror_x.setValue(default_mirror_x)
        layout.addRow("Mirrors (X)", self._mirror_x)

        self._mirror_y = QSpinBox(self)
        self._mirror_y.setRange(1, 8192)
        default_mirror_y = max(1, min(8192, int(default_mirrors[1])))
        self._mirror_y.setValue(default_mirror_y)
        layout.addRow("Mirrors (Y)", self._mirror_y)

        self._pixel_size = QDoubleSpinBox(self)
        self._pixel_size.setRange(1e-6, 10_000.0)
        self._pixel_size.setDecimals(6)
        clamped_size = max(self._pixel_size.minimum(), min(self._pixel_size.maximum(), float(default_pixel_size)))
        self._pixel_size.setValue(clamped_size)
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


class _PolygonDrawingCapture(QObject):
    """Interactive tool to capture a polygon drawn via successive clicks."""

    def __init__(self, view_box: pg.ViewBox, parent: QWidget | None = None):
        super().__init__(parent)
        self._view_box = view_box
        self._scene = view_box.scene()
        self._loop: QEventLoop | None = None
        self._points: list[QPointF] = []
        self._preview: pg.PlotDataItem | None = None
        self._result: list[QPointF] | None = None
        self._original_mouse_enabled: tuple[bool, bool] = (True, True)

    def exec(self) -> list[QPointF] | None:
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
        self._cleanup_preview()
        points = self._result
        self._points.clear()
        self._result = None
        self._loop = None
        return points

    def eventFilter(self, _obj, event):  # noqa: D401
        if self._loop is None:
            return False
        etype = event.type()
        if etype == QEvent.GraphicsSceneMousePress:
            if not self._view_box.sceneBoundingRect().contains(event.scenePos()):
                return False
            if event.button() == Qt.MouseButton.LeftButton:
                self._append_point(event.scenePos())
                event.accept()
                return True
            if event.button() == Qt.MouseButton.RightButton:
                self._finish(commit=True)
                event.accept()
                return True
        elif etype == QEvent.GraphicsSceneMouseDoubleClick:
            if event.button() == Qt.MouseButton.LeftButton:
                self._finish(commit=True)
                event.accept()
                return True
        elif etype == QEvent.GraphicsSceneMouseMove:
            if not self._points:
                return False
            current_view = self._view_box.mapSceneToView(event.scenePos())
            self._update_preview(current_view)
            event.accept()
            return True
        elif etype == QEvent.KeyPress and event.key() == Qt.Key.Key_Escape:
            self._finish(commit=False)
            event.accept()
            return True
        return False

    def _append_point(self, scene_pos: QPointF) -> None:
        view_point = self._view_box.mapSceneToView(scene_pos)
        self._points.append(view_point)
        self._update_preview(current=None)

    def _update_preview(self, current: QPointF | None) -> None:
        if self._preview is None:
            pen = pg.mkPen(color="yellow", width=2)
            self._preview = pg.PlotDataItem(
                pen=pen,
                symbol="o",
                symbolBrush="yellow",
                symbolPen="yellow",
                symbolSize=6,
            )
            self._preview.setZValue(10_000)
            self._view_box.addItem(self._preview)
        xs = [pt.x() for pt in self._points]
        ys = [pt.y() for pt in self._points]
        if current is not None:
            xs.append(current.x())
            ys.append(current.y())
        elif len(self._points) >= 2:
            xs.append(self._points[0].x())
            ys.append(self._points[0].y())
        self._preview.setData(xs, ys)

    def _finish(self, commit: bool) -> None:
        if commit and len(self._points) >= 3:
            self._result = [QPointF(pt) for pt in self._points]
        else:
            self._result = None
        if self._loop is not None and self._loop.isRunning():
            self._loop.quit()

    def _cleanup_preview(self) -> None:
        if self._preview is not None:
            try:
                self._view_box.removeItem(self._preview)
            except Exception:
                pass
            self._preview = None


class _CalibrationPreferences:
    """Small helper around QSettings for persisting calibration parameters."""

    _ORG = "Stim1P"
    _APP = "DMDStim"
    _KEY_LAST_FILE = "calibration/last_file_path"
    _KEY_LAST_IMAGE = "calibration/last_image_path"
    _KEY_MIRRORS_X = "calibration/mirrors_x"
    _KEY_MIRRORS_Y = "calibration/mirrors_y"
    _KEY_PIXEL_SIZE = "calibration/pixel_size"

    def __init__(self):
        self._settings = QSettings(self._ORG, self._APP)

    @staticmethod
    def _to_str(value) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)

    @staticmethod
    def _to_int(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_float(value, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def last_calibration_file_path(self) -> str:
        return self._to_str(self._settings.value(self._KEY_LAST_FILE, ""))

    def set_last_calibration_file_path(self, path: str) -> None:
        self._settings.setValue(self._KEY_LAST_FILE, path)
        self._settings.sync()

    def last_calibration_image_path(self) -> str:
        return self._to_str(self._settings.value(self._KEY_LAST_IMAGE, ""))

    def set_last_calibration_image_path(self, path: str) -> None:
        self._settings.setValue(self._KEY_LAST_IMAGE, path)
        self._settings.sync()

    def mirror_counts(self) -> tuple[int, int]:
        x = self._to_int(self._settings.value(self._KEY_MIRRORS_X), 100)
        y = self._to_int(self._settings.value(self._KEY_MIRRORS_Y), 100)
        return x, y

    def set_mirror_counts(self, mirrors_x: int, mirrors_y: int) -> None:
        self._settings.setValue(self._KEY_MIRRORS_X, int(mirrors_x))
        self._settings.setValue(self._KEY_MIRRORS_Y, int(mirrors_y))
        self._settings.sync()

    def pixel_size(self) -> float:
        return self._to_float(self._settings.value(self._KEY_PIXEL_SIZE), 1.0)

    def set_pixel_size(self, pixel_size: float) -> None:
        self._settings.setValue(self._KEY_PIXEL_SIZE, float(pixel_size))
        self._settings.sync()

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
        self._view_box.setAspectLocked(True, 1.0)
        self._view_box.invertY(True)
        self._view_box.setMouseEnabled(True, True)
        self._view_box.enableAutoRange(pg.ViewBox.XYAxes, enable=True)
        self._view_box.setLimits(minXRange=1.0, minYRange=1.0)
        self._view_box.setMenuEnabled(True)

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
        self._preferences = _CalibrationPreferences()
        self._last_calibration_file_path: str = (
            self._preferences.last_calibration_file_path()
        )
        self._connect()
        self._install_context_menu()
        self._apply_saved_preferences()
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
        shape_types: list[list[str]] = []
        for i in range(self.ui.treeWidget.topLevelItemCount()):
            pattern_item = self.ui.treeWidget.topLevelItem(i)
            assert pattern_item is not None
            descriptions.append(
                tree_table_manager.extract_description(pattern_item.text(0))
            )
            pattern_polys: list[np.ndarray] = []
            pattern_shapes: list[str] = []
            for j in range(pattern_item.childCount()):
                poly_item = pattern_item.child(j)
                shape = self.roi_manager.get_shape(poly_item)
                if shape is None:
                    continue
                points = shape.get_points()
                micrometres = self._calibration.camera_to_micrometre(points.T).T
                pattern_polys.append(micrometres)
                pattern_shapes.append(shape.shape_type)
            patterns.append(pattern_polys)
            shape_types.append(pattern_shapes)
        timings_ms, durations_ms, sequence = self._read_table_ms()
        return PatternSequence(
            patterns=patterns,
            sequence=sequence,
            timings=[timedelta(milliseconds=int(t)) for t in timings_ms],
            durations=[timedelta(milliseconds=int(d)) for d in durations_ms],
            descriptions=descriptions,
            shape_types=shape_types,
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
        shape_types = (
            model.shape_types
            if model.shape_types is not None
            else [["polygon"] * len(pattern) for pattern in model.patterns]
        )
        for pat_idx, pattern in enumerate(model.patterns):

            root = QTreeWidgetItem([""])

            self.tree_manager.attach_pattern_id(
                root, self.tree_manager.new_pattern_id()
            )
            root.setFlags(root.flags() | Qt.ItemFlag.ItemIsEditable)
            self.ui.treeWidget.insertTopLevelItem(pat_idx, root)
            self.tree_manager.set_pattern_label(root, pat_idx, descs[pat_idx])
            shape_type_row = (
                shape_types[pat_idx]
                if pat_idx < len(shape_types)
                else ["polygon"] * len(pattern)
            )
            for _poly_idx, poly_pts in enumerate(pattern):
                shape_kind = (
                    shape_type_row[_poly_idx]
                    if _poly_idx < len(shape_type_row)
                    else "polygon"
                )
                shape_kind = str(shape_kind).lower()
                node = QTreeWidgetItem([shape_kind])
                root.addChild(node)
                points = np.asarray(poly_pts, dtype=float)
                if self._calibration is not None:
                    points = self._calibration.micrometre_to_camera(points.T).T
                if shape_kind == "rectangle":
                    shape = self.roi_manager.register_rectangle(node, points)
                else:
                    shape = self.roi_manager.register_polygon(node, points)
                shape.change_ref(self.crosshair.pos(), self.crosshair.angle())
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
        self.ui.pushButton_draw_rectangle.clicked.connect(self._draw_rectangle_roi)
        self.ui.pushButton_draw_polygon.clicked.connect(self._draw_polygon_roi)
        self.ui.pushButton_add_row.clicked.connect(self._add_row_table)
        self.ui.pushButton_remove_row.clicked.connect(self._remove_row_table)
        self.ui.pushButton_remove_pattern.clicked.connect(
            self.tree_manager.remove_selected_patterns
        )
        self.ui.pushButton_new_file.clicked.connect(self._new_model)
        self.ui.pushButton_load_patterns.clicked.connect(self._load_patterns_file)
        self.ui.pushButton_save_patterns.clicked.connect(self._save_file)
        self.ui.pushButton_calibrate_dmd.clicked.connect(self._calibrate_dmd)
        self.ui.pushButton_reset_image_view.clicked.connect(self._reset_image_view)
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

    def _install_context_menu(self) -> None:
        try:
            menu = self._view_box.getMenu()
        except Exception:
            menu = None
        self._view_box_menu = menu
        if menu is None:
            return
        if menu.property("_stim_context_menu_setup"):
            return
        menu.setProperty("_stim_context_menu_setup", True)
        menu.addSeparator()
        auto_levels_action = menu.addAction("Auto levels (full range)")
        auto_levels_action.triggered.connect(self._apply_auto_levels_full)
        clipped_levels_action = menu.addAction("Auto levels (1-99% percentile)")
        clipped_levels_action.triggered.connect(self._apply_auto_levels_clipped)
        menu.addSeparator()
        reset_levels_action = menu.addAction("Reset histogram region")
        reset_levels_action.triggered.connect(self._reset_histogram_region)

    def _apply_saved_preferences(self) -> None:
        last_image_path = self._preferences.last_calibration_image_path()
        if last_image_path:
            folder = os.path.dirname(last_image_path)
            if folder:
                self.ui.lineEdit_image_folder_path.setText(folder)
        self._load_saved_calibration_if_available()

    def _default_calibration_file_path(self) -> Path:
        location = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        if not location:
            location = os.path.join(Path.home(), ".stim1p")
        base_path = Path(location).expanduser()
        try:
            base_path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return base_path / "last_calibration.h5"

    def _load_saved_calibration_if_available(self) -> None:
        candidates: list[Path] = []
        stored_path = self._preferences.last_calibration_file_path()
        if stored_path:
            candidates.append(Path(stored_path).expanduser())
        default_path = self._default_calibration_file_path()
        if not candidates or candidates[0] != default_path:
            candidates.append(default_path)
        for path in candidates:
            if not path or not path.exists():
                continue
            try:
                calibration = saving.load_calibration(str(path))
            except Exception as exc:
                print(f"Failed to load stored calibration from {path}: {exc}")
                continue
            self.calibration = calibration
            self.remember_calibration_file(str(path))
            self._preferences.set_pixel_size(calibration.camera_pixel_size_um)
            return

    def _persist_calibration(self, calibration: DMDCalibration) -> None:
        target_path = self._preferences.last_calibration_file_path()
        if target_path:
            path = Path(target_path).expanduser()
        else:
            path = self._default_calibration_file_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            saving.save_calibration(str(path), calibration)
        except Exception as exc:
            print(f"Failed to persist calibration to {path}: {exc}")
            return
        self.remember_calibration_file(str(path))

    def _compute_fit_rect(self, width: int, height: int) -> QRectF:
        span = float(max(width, height))
        if span <= 0.0:
            span = 1.0
        margin = max(span * 0.05, 1.0)
        half_extent = span / 2.0 + margin
        center_x = float(width) / 2.0
        center_y = float(height) / 2.0
        return QRectF(
            center_x - half_extent,
            center_y - half_extent,
            2.0 * half_extent,
            2.0 * half_extent,
        )

    def _update_zoom_constraints(self, _width: int, _height: int) -> None:
        view_box = self._get_view_box()
        view_box.setLimits(
            minXRange=1.0,
            minYRange=1.0,
            maxXRange=None,
            maxYRange=None,
        )

    def _fit_image_in_view(self, width: int, height: int) -> None:
        fit_rect = self._compute_fit_rect(width, height)
        view_box = self._get_view_box()
        view_box.setRange(rect=fit_rect, padding=0.0)
        QTimer.singleShot(
            0, lambda: view_box.setRange(rect=QRectF(fit_rect), padding=0.0)
        )

    def _resolve_pattern_parent(self) -> QTreeWidgetItem | None:
        tree = self.ui.treeWidget
        selected_items = tree.selectedItems()
        target = selected_items[0] if selected_items else None
        if target is None:
            if tree.topLevelItemCount() == 0:
                QMessageBox.information(
                    self,
                    "No pattern selected",
                    "Create or select a pattern before drawing a shape.",
                )
                return None
            target = tree.topLevelItem(0)
            if target is not None:
                tree.setCurrentItem(target)
        if target is None:
            return None
        if target.parent() is not None:
            target = target.parent()
        return target

    def _create_roi_item(
        self,
        parent_item: QTreeWidgetItem,
        points: np.ndarray,
        shape_type: str,
    ) -> QTreeWidgetItem:
        points = np.asarray(points, dtype=float)
        if points.ndim != 2 or points.shape[1] != 2:
            raise ValueError("ROI points must be an array of shape (N, 2).")
        shape_type = str(shape_type).lower()
        label = "rectangle" if shape_type == "rectangle" else "polygon"
        node = QTreeWidgetItem([label])
        parent_item.addChild(node)
        if shape_type == "rectangle":
            shape = self.roi_manager.register_rectangle(node, points)
        else:
            shape = self.roi_manager.register_polygon(node, points)
        shape.change_ref(self.crosshair.pos(), self.crosshair.angle())
        parent_item.setExpanded(True)
        self.ui.treeWidget.setCurrentItem(node)
        self.roi_manager.show_for_item(node)
        return node

    def _draw_rectangle_roi(self) -> None:
        parent_item = self._resolve_pattern_parent()
        if parent_item is None:
            return
        print("Rectangle tool: drag to draw. Right-click or Esc cancels.")
        button = self.ui.pushButton_draw_rectangle
        button.setEnabled(False)
        try:
            capture = _InteractiveRectangleCapture(self._get_view_box(), self)
            rect = capture.exec()
        finally:
            button.setEnabled(True)
        if rect is None or rect.width() <= 0.0 or rect.height() <= 0.0:
            return
        x0, x1 = rect.left(), rect.right()
        y0, y1 = rect.top(), rect.bottom()
        points = np.array(
            [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
            dtype=float,
        )
        self._create_roi_item(parent_item, points, "rectangle")

    def _draw_polygon_roi(self) -> None:
        parent_item = self._resolve_pattern_parent()
        if parent_item is None:
            return
        print(
            "Polygon tool: left-click to add vertices, right-click or double-click to finish (Esc cancels)."
        )
        button = self.ui.pushButton_draw_polygon
        button.setEnabled(False)
        try:
            capture = _PolygonDrawingCapture(self._get_view_box(), self)
            points = capture.exec()
        finally:
            button.setEnabled(True)
        if not points or len(points) < 3:
            return
        array = np.array([[pt.x(), pt.y()] for pt in points], dtype=float)
        self._create_roi_item(parent_item, array, "polygon")

    def _reset_image_view(self) -> None:
        if self._current_image is None:
            return
        height, width = self._current_image.shape[:2]
        self._update_zoom_constraints(width, height)
        view_box = self._get_view_box()
        view_box.enableAutoRange(pg.ViewBox.XYAxes, enable=False)
        self._fit_image_in_view(width, height)

    def remember_calibration_file(self, path: str) -> None:
        """Store the path to the most recently used calibration file."""
        self._last_calibration_file_path = path
        self._preferences.set_last_calibration_file_path(path)

    def last_calibration_file_path(self) -> str:
        """Return the last calibration file recorded for this session."""
        return self._last_calibration_file_path

    def _apply_auto_levels_full(self) -> None:
        self._apply_histogram_levels(percentile=None)

    def _apply_auto_levels_clipped(self) -> None:
        self._apply_histogram_levels(percentile=(1.0, 99.0))

    def _apply_histogram_levels(
        self, percentile: tuple[float, float] | None
    ) -> None:
        if self._current_image is None:
            return
        data = self._current_image
        if data.ndim == 3:
            # Collapse colour channels to pick global min/max.
            data = data.reshape(-1, data.shape[2])
        try:
            if percentile is None:
                lower = float(np.nanmin(data))
                upper = float(np.nanmax(data))
            else:
                low_p, high_p = percentile
                finite = data[np.isfinite(data)]
                if finite.size == 0:
                    return
                lower = float(np.nanpercentile(finite, low_p))
                upper = float(np.nanpercentile(finite, high_p))
        except Exception:
            return
        if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
            return
        levels = (lower, upper)
        try:
            self._image_item.setLevels(levels)
        except Exception:
            pass
        self._hist_widget.region.setRegion(levels)
        self._current_levels = levels

    def _reset_histogram_region(self) -> None:
        levels = self._current_levels
        if levels is None:
            self._apply_auto_levels_full()
            return
        self._hist_widget.region.setRegion(levels)

    def _set_image(self, image: np.ndarray, *, fit_to_view: bool = False) -> None:
        image = np.asarray(image)
        if image.ndim not in (2, 3):
            raise ValueError("Images must be 2D grayscale or 3-channel colour arrays.")
        height, width = image.shape[:2]
        previous_levels = self._current_levels

        view_box = self._get_view_box()
        preserve_view = (
            not fit_to_view
            and self._current_image is not None
            and self._current_image.shape[:2] == image.shape[:2]
        )
        if preserve_view:
            try:
                previous_range = view_box.viewRange()
            except Exception:
                previous_range = None
        else:
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

        self._update_zoom_constraints(width, height)
        view_box.enableAutoRange(pg.ViewBox.XYAxes, enable=False)
        if preserve_view and previous_range is not None:
            x_range, y_range = previous_range
            view_box.setRange(xRange=x_range, yRange=y_range, padding=0.0)
        else:
            self._fit_image_in_view(width, height)
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
            self._set_image(image, fit_to_view=True)
        except Exception:
            pass

    def _calibrate_dmd(self):
        initial_dir = self.ui.lineEdit_image_folder_path.text().strip()
        stored_image_path = self._preferences.last_calibration_image_path()
        if stored_image_path:
            stored_dir = os.path.dirname(stored_image_path)
            if stored_dir:
                initial_dir = stored_dir
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
        self._preferences.set_last_calibration_image_path(file_path)
        selected_dir = os.path.dirname(file_path)
        if selected_dir:
            self.ui.lineEdit_image_folder_path.setText(selected_dir)

        previous_image = self._current_image
        previous_view = self._capture_view_state()
        selected_items = self.ui.treeWidget.selectedItems()
        selected_item = selected_items[0] if selected_items else None
        self.roi_manager.clear_visible_only()

        self._set_image(calibration_image, fit_to_view=True)

        polygon_points = self._prompt_calibration_rectangle()
        if polygon_points is None:
            QMessageBox.information(
                self,
                "Calibration cancelled",
                "No calibration rectangle was drawn. Calibration has been cancelled.",
            )
            self._restore_after_calibration(previous_image, previous_view, selected_item)
            return

        dialog = _CalibrationDialog(
            self,
            default_mirrors=self._preferences.mirror_counts(),
            default_pixel_size=self._preferences.pixel_size(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._restore_after_calibration(previous_image, previous_view, selected_item)
            return

        mirrors_x, mirrors_y, pixel_size = dialog.values()
        self._preferences.set_mirror_counts(mirrors_x, mirrors_y)
        self._preferences.set_pixel_size(pixel_size)
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
        self._persist_calibration(calibration)
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
        self._set_image(image, fit_to_view=True)

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
