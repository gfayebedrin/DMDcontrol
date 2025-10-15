import os
import glob
import math
from pathlib import Path
import numpy as np
from PIL import Image
from datetime import timedelta
from dataclasses import dataclass
from typing import Sequence

from PySide6.QtCore import (
    QEvent,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import QTransform
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QHeaderView,
    QSpinBox,
    QTableWidgetItem,
    QTreeWidgetItem,
    QWidget,
    QFrame,
)
import pyqtgraph as pg

from ..logic.calibration import (
    DMDCalibration,
    compute_calibration_from_square,
)
from ..logic.geometry import (
    AxisDefinition,
    axis_micrometre_scale,
    axis_micrometre_to_axis_pixels,
    axis_pixels_to_axis_micrometre,
)
from ..logic.sequence import PatternSequence
from ..logic import saving
from ..stim1p import Stim1P

from .qt.DMD_stim_ui import Ui_widget_dmd_stim
from . import console, roi_manager, tree_table_manager
from .calibration_preferences import CalibrationPreferences
from .grid_dialog import GridDialog, GridParameters
from .capture_tools import (
    AxisCapture,
    InteractiveRectangleCapture,
    PolygonDrawingCapture,
)


class _MicrometreAxisItem(pg.AxisItem):
    """Axis that renders tick labels in micrometres when calibration is available."""

    def __init__(self, orientation: str, widget):
        super().__init__(orientation=orientation)
        self._widget = widget

    def tickStrings(self, values, scale, spacing):
        if self.logMode:
            return super().tickStrings(values, scale, spacing)
        per_unit = self._widget._axis_unit_scale_for_orientation(self.orientation)
        if per_unit is None or not np.isfinite(per_unit) or per_unit == 0.0:
            return super().tickStrings(values, scale, spacing)
        spacing_um = abs(spacing * per_unit)
        effective_spacing = max(spacing_um, 1e-9)
        places = max(0, int(np.ceil(-np.log10(effective_spacing))))
        places = min(places, 6)
        strings: list[str] = []
        for value in values:
            val_um = float(value) * per_unit
            if abs(val_um) < 1e-9:
                val_um = 0.0
            if abs(val_um) < 1e-3 or abs(val_um) >= 1e4:
                label = f"{val_um:g}"
            else:
                label = f"{val_um:.{places}f}"
            strings.append(label)
        return strings


@dataclass
class _AxisRedefinitionCache:
    previous_origin: np.ndarray
    previous_angle: float
    new_origin: np.ndarray
    new_angle: float
    shapes: dict[QTreeWidgetItem, tuple[np.ndarray, str]]
    behaviour: str | None = None


class _CalibrationDialog(QDialog):
    """Collect user inputs required to build a calibration."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        default_mirrors: tuple[int, int] = (100, 100),
        default_pixel_size: float = 1.0,
        default_invert_axes: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle("Calibrate DMD")
        layout = QFormLayout(self)

        self._mirror_size = QSpinBox(self)
        self._mirror_size.setRange(1, 8192)
        default_avg = 0.5 * (float(default_mirrors[0]) + float(default_mirrors[1]))
        default_size = max(1, min(8192, int(round(default_avg))))
        self._mirror_size.setValue(default_size)
        layout.addRow("Square size (mirrors)", self._mirror_size)

        self._pixel_size = QDoubleSpinBox(self)
        self._pixel_size.setRange(1e-6, 10_000.0)
        self._pixel_size.setDecimals(6)
        clamped_size = max(self._pixel_size.minimum(), min(self._pixel_size.maximum(), float(default_pixel_size)))
        self._pixel_size.setValue(clamped_size)
        layout.addRow("Camera pixel size (µm)", self._pixel_size)

        self._invert_axes = QCheckBox(self)
        self._invert_axes.setChecked(bool(default_invert_axes))
        self._invert_axes.setText("Flip DMD axes (X→X−x, Y→Y−y)")
        layout.addRow(self._invert_axes)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> tuple[int, float, bool]:
        return self._mirror_size.value(), self._pixel_size.value(), self._invert_axes.isChecked()


class _GridPreviewOverlay:
    """Render a temporary preview of rectangles on top of the plot."""

    def __init__(self, plot_item: pg.PlotItem):
        self._plot_item = plot_item
        self._items: list[pg.PlotCurveItem] = []
        self._pen = pg.mkPen(color=(0, 200, 255, 200), width=2, style=Qt.PenStyle.DashLine)

    def set_rectangles(self, rectangles: Sequence[np.ndarray]) -> None:
        rectangles = [np.asarray(rect, dtype=float) for rect in rectangles]
        required = len(rectangles)
        while len(self._items) < required:
            item = pg.PlotCurveItem(pen=self._pen)
            item.setZValue(8_750)
            item.hide()
            self._plot_item.addItem(item)
            self._items.append(item)
        for idx, rect in enumerate(rectangles):
            item = self._items[idx]
            if rect.ndim != 2 or rect.shape[1] != 2:
                item.hide()
                continue
            closed = np.vstack([rect, rect[0]])
            item.setData(closed[:, 0], closed[:, 1])
            item.show()
        for idx in range(len(rectangles), len(self._items)):
            self._items[idx].hide()

    def hide(self) -> None:
        for item in self._items:
            item.hide()

    def clear(self) -> None:
        for item in self._items:
            self._plot_item.removeItem(item)
        self._items.clear()


class StimDMDWidget(QWidget):
    """Coordinate DMD calibration, ROI editing, and pattern sequencing UI."""

    _AXIS_MODE_MOVE = "move"
    _AXIS_MODE_KEEP = "keep"
    _AXIS_BEHAVIOUR_LABELS = {
        _AXIS_MODE_MOVE: "Move patterns with the image",
        _AXIS_MODE_KEEP: "Keep patterns in place",
    }

    def __init__(self, name="Stimulation DMD Widget", dmd=None, parent=None):
        """Build the widget layout and initialise runtime state."""
        super().__init__(parent=parent)
        self.ui = Ui_widget_dmd_stim()
        self.ui.setupUi(self)
        self.setObjectName(name)
        self.last_roi = None
        self.dmd = dmd
        self._calibration: DMDCalibration | None = None
        self._current_image: np.ndarray | None = None
        self._current_levels: tuple[float, float] | None = None
        self._axis_origin_camera = np.array([0.0, 0.0], dtype=float)
        self._axis_angle_rad = 0.0
        self._axis_defined = False
        self._axis_redefine_cache: _AxisRedefinitionCache | None = None
        # GraphicsLayoutWidget gives us fine control over plot + histogram layout.
        self._graphics_widget = pg.GraphicsLayoutWidget(parent=self)
        axis_items = {
            "bottom": _MicrometreAxisItem("bottom", self),
            "left": _MicrometreAxisItem("left", self),
        }
        self._plot_item = self._graphics_widget.addPlot(axisItems=axis_items)
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
        for orientation in ("bottom", "left"):
            axis = self._plot_item.getAxis(orientation)
            axis.enableAutoSIPrefix(False)
        self._update_axis_labels()

        # ImageItem renders the camera frame; keep it behind ROIs.
        self._image_item = pg.ImageItem()
        self._image_item.setZValue(-1)
        # Attach image directly to the view box so it follows pans/zooms.
        self._view_box.addItem(self._image_item)

        self._axis_line_item = pg.PlotDataItem(pen=pg.mkPen(color="c", width=2))
        self._axis_line_item.setZValue(8_500)
        self._axis_arrow_item = pg.ArrowItem(
            angle=0,
            headLen=25,
            pen=pg.mkPen("c"),
            brush=pg.mkBrush("c"),
        )
        self._axis_arrow_item.setZValue(8_501)
        self._axis_origin_item = pg.ScatterPlotItem(
            [0.0],
            [0.0],
            size=10,
            brush=pg.mkBrush("c"),
            pen=pg.mkPen("c"),
        )
        self._axis_origin_item.setZValue(8_502)
        self._plot_item.addItem(self._axis_line_item)
        self._plot_item.addItem(self._axis_arrow_item)
        self._plot_item.addItem(self._axis_origin_item)
        self._axis_line_item.hide()
        self._axis_arrow_item.hide()
        self._axis_origin_item.hide()
        self._grid_preview_overlay: _GridPreviewOverlay | None = None
        self._grid_dialog: GridDialog | None = None

        # HistogramLUTWidget provides the contrast controls that users expect.
        self._hist_widget = pg.HistogramLUTWidget(parent=self)
        self._hist_widget.setImageItem(self._image_item)
        self._hist_widget.setMinimumWidth(140)
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
        self._preferences = CalibrationPreferences()
        self._run_state_timer = QTimer(self)
        self._run_state_timer.setInterval(250)
        self._run_state_timer.timeout.connect(self._on_run_state_check)
        self._stim = Stim1P()
        self._grid_last_parameters = self._preferences.grid_parameters()
        if not self._grid_last_parameters.is_valid():
            self._grid_last_parameters = GridParameters()
        self._roi_properties_item: QTreeWidgetItem | None = None
        self._updating_roi_properties = False
        self._setup_roi_properties_panel()
        self.roi_manager.shapeEdited.connect(self._on_roi_shape_edited)
        self._setup_axis_behaviour_controls()
        self._setup_axis_feedback_banner()
        self._last_calibration_file_path: str = (
            self._preferences.last_calibration_file_path()
        )
        self._connect()
        self._install_context_menu()
        self._apply_saved_preferences()
        self._console = console.Console(self.ui.plainTextEdit_console_output)
        self._update_image_transform()
        self._update_axis_visuals()
        self._update_dmd_controls()
        self._update_listener_controls()
        self._update_run_controls()

    @staticmethod
    def _rect_to_polygon_points(rect: QRectF) -> np.ndarray:
        """Return the rectangle corners as a float array in clockwise order."""

        x0, x1 = rect.left(), rect.right()
        y0, y1 = rect.top(), rect.bottom()
        return np.array(
            [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
            dtype=float,
        )

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
                axis_points = shape.get_points()
                micrometre_points = self._axis_pixels_to_micrometres(axis_points)
                pattern_polys.append(micrometre_points)
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
        self._set_roi_properties_item(None)
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

        # Keep whichever axis the user already defined; if none, make sure visuals stay in sync.
        self._update_image_transform()
        self._update_axis_visuals()
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
                points_um = np.asarray(poly_pts, dtype=float)
                points_axis = self._micrometres_to_axis_pixels(points_um)
                if shape_kind == "rectangle":
                    self.roi_manager.register_rectangle(node, points_axis)
                else:
                    self.roi_manager.register_polygon(node, points_axis)
        self.roi_manager.clear_visible_only()
        self.tree_manager.renumber_pattern_labels()
        self._write_table_ms(model)
        self._fit_view_to_image()
        self._update_axis_visuals()

    @property
    def calibration(self) -> DMDCalibration | None:
        return self._calibration

    @calibration.setter
    def calibration(self, calibration: DMDCalibration | None):
        self._calibration = calibration
        self._update_axis_labels()
        self._update_listener_controls()

    def _toggle_dmd_connection(self) -> None:
        """Connect or disconnect the DMD hardware via the controller."""

        try:
            if not self._stim.is_dmd_connected:
                self._stim.connect_dmd()
            else:
                if self._stim.is_listening:
                    try:
                        self._stim.stop_listening()
                    except Exception as exc:  # noqa: BLE001
                        QMessageBox.critical(
                            self,
                            "Error stopping listener",
                            str(exc),
                        )
                        return
                if self._stim.is_running:
                    try:
                        self._stim.stop_run()
                    except Exception as exc:  # noqa: BLE001
                        QMessageBox.critical(
                            self,
                            "Error stopping run",
                            str(exc),
                        )
                        return
                self._stim.disconnect_dmd()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "DMD connection error", str(exc))
        finally:
            self._update_dmd_controls()
            self._update_listener_controls()
            self._update_run_controls()

    def _toggle_pipe_listener(self) -> None:
        """Start or stop listening for MATLAB commands through the controller."""

        if not self._stim.is_listening:
            if not self._stim.is_dmd_connected:
                QMessageBox.warning(
                    self,
                    "DMD disconnected",
                    "Connect to the DMD before starting the MATLAB listener.",
                )
                return
            if self._calibration is None:
                QMessageBox.warning(
                    self,
                    "Calibration missing",
                    "Load or compute a DMD calibration before listening for MATLAB commands.",
                )
                return
            if not self._axis_defined:
                QMessageBox.warning(
                    self,
                    "Axis definition required",
                    "Define an axis before listening for MATLAB commands.",
                )
                return
            try:
                pattern_sequence = self.model
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(
                    self,
                    "Pattern export failed",
                    str(exc),
                )
                return
            try:
                self._stim.set_calibration(self._calibration)
                self._stim.set_axis_definition(self._axis_definition())
                self._stim.set_pattern_sequence(pattern_sequence)
                self._stim.start_listening()
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Listener error", str(exc))
                return
        else:
            try:
                self._stim.stop_listening()
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Listener error", str(exc))
                return
        self._update_listener_controls()
        self._update_run_controls()

    def _toggle_run_now(self) -> None:
        """Start or stop the pattern sequence directly on the DMD."""

        if self._stim.is_running:
            try:
                self._stim.stop_run()
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Run control error", str(exc))
                return
            finally:
                self._update_run_controls()
            return

        if self._stim.is_listening:
            QMessageBox.warning(
                self,
                "Listener active",
                "Stop listening to MATLAB before starting a run manually.",
            )
            return
        if not self._stim.is_dmd_connected:
            QMessageBox.warning(
                self,
                "DMD disconnected",
                "Connect to the DMD before starting a run.",
            )
            return
        if self._calibration is None:
            QMessageBox.warning(
                self,
                "Calibration missing",
                "Load or compute a DMD calibration before starting a run.",
            )
            return
        if not self._axis_defined:
            QMessageBox.warning(
                self,
                "Axis definition required",
                "Define an axis before starting a run.",
            )
            return

        try:
            pattern_sequence = self.model
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                "Pattern export failed",
                str(exc),
            )
            return

        try:
            self._stim.set_calibration(self._calibration)
            self._stim.set_axis_definition(self._axis_definition())
            self._stim.set_pattern_sequence(pattern_sequence)
            self._stim.start_run()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Run control error", str(exc))
            return

        self._update_run_controls()

    def _update_dmd_controls(self) -> None:
        """Update the connect button caption based on controller state."""

        button = self.ui.pushButton_connect_dmd
        if self._stim.is_dmd_connected:
            button.setText("Disconnect DMD")
        else:
            button.setText("Connect to DMD")

    def _update_listener_controls(self) -> None:
        """Refresh listener button text and availability."""

        button = self.ui.pushButton_listen_to_matlab
        listening = self._stim.is_listening
        button.setText("Stop listening" if listening else "Start listening")
        if listening:
            button.setEnabled(True)
        else:
            prerequisites_met = (
                self._stim.is_dmd_connected
                and self._calibration is not None
                and self._axis_defined
            )
            button.setEnabled(prerequisites_met)
        self._update_run_controls()

    def _update_run_controls(self) -> None:
        """Update the manual run button caption and availability."""

        button = self.ui.pushButton_run_now
        running = getattr(self._stim, "is_running", False)
        button.setText("Stop run" if running else "Start run now")
        if running:
            button.setEnabled(True)
            if not self._run_state_timer.isActive():
                self._run_state_timer.start()
            return
        if self._run_state_timer.isActive():
            self._run_state_timer.stop()
        prerequisites_met = (
            self._stim.is_dmd_connected
            and self._calibration is not None
            and self._axis_defined
            and not self._stim.is_listening
        )
        button.setEnabled(prerequisites_met)

    def _on_run_state_check(self) -> None:
        """Poll for run completion to refresh the UI."""

        if not getattr(self._stim, "is_running", False):
            self._run_state_timer.stop()
            self._update_run_controls()
            return
        self._update_run_controls()

    def _connect(self):
        """Wire UI widgets to their slots and manager helpers."""
        self.ui.pushButton_load_image.clicked.connect(self._load_image)
        self.ui.pushButton_change_folder.clicked.connect(self._change_folder)
        self.ui.pushButton_refresh_image.clicked.connect(self._refresh_image)
        self.ui.pushButton_show_grid.clicked.connect(self._show_grid)
        self.ui.pushButton_define_axis.clicked.connect(self._define_axis)
        self.ui.pushButton_add_pattern.clicked.connect(
            self.tree_manager.add_pattern
        )
        self.ui.pushButton_create_grid.clicked.connect(self._open_grid_dialog)
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
        self.ui.pushButton_connect_dmd.clicked.connect(self._toggle_dmd_connection)
        self.ui.pushButton_listen_to_matlab.clicked.connect(self._toggle_pipe_listener)
        self.ui.pushButton_run_now.clicked.connect(self._toggle_run_now)
        self.ui.treeWidget.itemClicked.connect(
            lambda item, _col: self.roi_manager.show_for_item(item)
        )
        self.ui.treeWidget.itemSelectionChanged.connect(
            self._on_tree_selection_changed
        )
        self.ui.treeWidget.itemChanged.connect(self.tree_manager.on_item_changed)
        self.ui.tableWidget.itemChanged.connect(self.table_manager.on_item_changed)
        self.ui.tableWidget_polygon_points.itemChanged.connect(
            self._on_polygon_point_changed
        )
        self.ui.doubleSpinBox_rect_width.valueChanged.connect(
            self._on_rectangle_property_changed
        )
        self.ui.doubleSpinBox_rect_height.valueChanged.connect(
            self._on_rectangle_property_changed
        )
        self.ui.doubleSpinBox_rect_angle.valueChanged.connect(
            self._on_rectangle_property_changed
        )

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_axis_feedback_frame", None):
            if event.type() in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
                if self._axis_feedback_timer.isActive():
                    self._axis_feedback_timer.stop()
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
                if self._axis_feedback_frame.isVisible():
                    self._axis_feedback_timer.start(3000)
        return super().eventFilter(obj, event)

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

    def _axis_definition(self) -> AxisDefinition:
        origin = tuple(float(v) for v in self._axis_origin_camera.reshape(2))
        return AxisDefinition(origin_camera=origin, angle_rad=float(self._axis_angle_rad))

    def _rotation_matrix(self, angle: float | None = None) -> np.ndarray:
        angle = self._axis_angle_rad if angle is None else float(angle)
        cos_a = float(np.cos(angle))
        sin_a = float(np.sin(angle))
        return np.array([[cos_a, -sin_a], [sin_a, cos_a]], dtype=float)

    def _camera_to_axis(
        self,
        points: np.ndarray,
        *,
        origin: np.ndarray | None = None,
        angle: float | None = None,
    ) -> np.ndarray:
        """Convert camera pixel coordinates into the user-defined axis frame."""
        arr = np.asarray(points, dtype=float)
        was_1d = arr.ndim == 1
        pts = np.atleast_2d(arr)
        origin_vec = (
            self._axis_origin_camera
            if origin is None
            else np.asarray(origin, dtype=float)
        )
        R = self._rotation_matrix(angle)
        relative = pts - origin_vec
        # Rotate into the axis frame and keep the input dimensionality.
        result = (R.T @ relative.T).T
        return result[0] if was_1d else result

    def _axis_to_camera(
        self,
        points: np.ndarray,
        *,
        origin: np.ndarray | None = None,
        angle: float | None = None,
    ) -> np.ndarray:
        """Convert axis-aligned coordinates back to camera pixel indices."""
        arr = np.asarray(points, dtype=float)
        was_1d = arr.ndim == 1
        pts = np.atleast_2d(arr)
        origin_vec = (
            self._axis_origin_camera
            if origin is None
            else np.asarray(origin, dtype=float)
        )
        R = self._rotation_matrix(angle)
        # Rotate and translate back into camera coordinates.
        result = (R @ pts.T).T + origin_vec
        return result[0] if was_1d else result

    def _axis_origin_micrometre(
        self, origin_camera: np.ndarray | None = None
    ) -> np.ndarray:
        if self._calibration is None:
            raise RuntimeError("A calibration is required for micrometre conversion.")
        origin_vec = (
            self._axis_origin_camera
            if origin_camera is None
            else np.asarray(origin_camera, dtype=float)
        )
        mic = self._calibration.camera_to_micrometre(origin_vec.reshape(2, 1)).T[0]
        return np.asarray(mic, dtype=float)

    def _axis_pixels_to_micrometres(self, points: np.ndarray) -> np.ndarray:
        if self._calibration is None:
            raise RuntimeError("A calibration is required for micrometre conversion.")
        return axis_pixels_to_axis_micrometre(
            points, self._axis_definition(), self._calibration
        )

    def _axis_micrometre_scale(self) -> tuple[float, float] | None:
        if self._calibration is None:
            return None
        try:
            scales = axis_micrometre_scale(
                self._axis_definition(), self._calibration
            )
        except Exception:
            return None
        scale_x = float(scales[0])
        scale_y = float(scales[1])
        if (
            not np.isfinite(scale_x)
            or not np.isfinite(scale_y)
            or scale_x <= 0.0
            or scale_y <= 0.0
        ):
            return None
        return scale_x, scale_y

    def _axis_unit_scale_for_orientation(self, orientation: str) -> float | None:
        scales = self._axis_micrometre_scale()
        if scales is None:
            return None
        orient = orientation.lower()
        if orient in ("bottom", "top"):
            return scales[0]
        if orient in ("left", "right"):
            return scales[1]
        return None

    def _reproject_shapes_from_cache(self, cache: _AxisRedefinitionCache) -> None:
        prev_origin = np.asarray(cache.previous_origin, dtype=float)
        prev_angle = float(cache.previous_angle)
        new_origin = np.asarray(cache.new_origin, dtype=float)
        new_angle = float(cache.new_angle)
        for item, (axis_points, shape_type) in cache.shapes.items():
            axis_pts = np.asarray(axis_points, dtype=float)
            camera_pts = self._axis_to_camera(axis_pts, origin=prev_origin, angle=prev_angle)
            axis_pts_new = self._camera_to_axis(camera_pts, origin=new_origin, angle=new_angle)
            self.roi_manager.update_shape(item, shape_type, axis_pts_new)

    def _restore_shapes_from_cache(self, cache: _AxisRedefinitionCache) -> None:
        for item, (axis_points, shape_type) in cache.shapes.items():
            self.roi_manager.update_shape(item, shape_type, axis_points)

    def _setup_axis_behaviour_controls(self) -> None:
        combo = self.ui.comboBox_axis_behaviour
        self._axis_behaviour_by_index = {
            0: self._AXIS_MODE_MOVE,
            1: self._AXIS_MODE_KEEP,
        }
        self._axis_behaviour_to_index = {
            value: key for key, value in self._axis_behaviour_by_index.items()
        }
        for index, mode in self._axis_behaviour_by_index.items():
            combo.setItemText(index, self._AXIS_BEHAVIOUR_LABELS[mode])
        tooltip = (
            "Choose what happens to existing patterns when the axis is redefined.\n"
            "A banner appears after redefining so you can switch behaviour for that change."
        )
        combo.setToolTip(tooltip)
        self.ui.label_axis_behaviour.setToolTip(tooltip)
        stored_mode = self._preferences.axis_redefinition_mode()
        index = self._axis_behaviour_to_index.get(stored_mode, 0)
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)
        combo.currentIndexChanged.connect(self._on_axis_behaviour_combo_changed)

    def _setup_axis_feedback_banner(self) -> None:
        frame = QFrame(self.ui.verticalLayoutWidget)
        frame.setObjectName("axisBehaviourBanner")
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setVisible(False)
        frame.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        label = QLabel(frame)
        layout.addWidget(label, 1)

        layout.addStretch(1)

        move_btn = QPushButton(self._AXIS_BEHAVIOUR_LABELS[self._AXIS_MODE_MOVE], frame)
        keep_btn = QPushButton(self._AXIS_BEHAVIOUR_LABELS[self._AXIS_MODE_KEEP], frame)
        layout.addWidget(move_btn, 0)
        layout.addWidget(keep_btn, 0)

        self.ui.verticalLayout_controls.insertWidget(1, frame)

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._hide_axis_feedback_banner)

        move_btn.clicked.connect(lambda: self._handle_axis_banner_choice(self._AXIS_MODE_MOVE))
        keep_btn.clicked.connect(lambda: self._handle_axis_banner_choice(self._AXIS_MODE_KEEP))
        frame.installEventFilter(self)

        self._axis_feedback_frame = frame
        self._axis_feedback_label = label
        self._axis_feedback_move_button = move_btn
        self._axis_feedback_keep_button = keep_btn
        self._axis_feedback_timer = timer

    def _axis_behaviour_from_index(self, index: int) -> str:
        return self._axis_behaviour_by_index.get(index, self._AXIS_MODE_MOVE)

    def _axis_behaviour_label(self, behaviour: str) -> str:
        return self._AXIS_BEHAVIOUR_LABELS.get(behaviour, behaviour)

    def _default_axis_behaviour(self) -> str:
        return self._axis_behaviour_from_index(self.ui.comboBox_axis_behaviour.currentIndex())

    def _update_axis_behaviour_combo(self, behaviour: str, *, update_preferences: bool) -> None:
        index = self._axis_behaviour_to_index.get(behaviour)
        if index is None:
            return
        combo = self.ui.comboBox_axis_behaviour
        if combo.currentIndex() != index:
            combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(False)
        if update_preferences:
            self._preferences.set_axis_redefinition_mode(behaviour)

    def _show_axis_feedback_banner(self, cache: _AxisRedefinitionCache) -> None:
        if not cache.shapes:
            self._hide_axis_feedback_banner()
            return
        behaviour = cache.behaviour or self._default_axis_behaviour()
        description = self._axis_behaviour_label(behaviour)
        self._axis_feedback_label.setText(f'Axis updated; patterns set to "{description}". Change?')
        self._refresh_axis_feedback_buttons(behaviour)
        self._axis_feedback_frame.setVisible(True)
        self._axis_feedback_timer.start(6000)

    def _hide_axis_feedback_banner(self) -> None:
        self._axis_feedback_timer.stop()
        self._axis_feedback_frame.setVisible(False)

    def _refresh_axis_feedback_buttons(self, behaviour: str) -> None:
        move_active = behaviour == self._AXIS_MODE_MOVE
        keep_active = behaviour == self._AXIS_MODE_KEEP
        self._axis_feedback_move_button.setEnabled(not move_active)
        self._axis_feedback_move_button.setDefault(move_active)
        self._axis_feedback_keep_button.setEnabled(not keep_active)
        self._axis_feedback_keep_button.setDefault(keep_active)

    def _handle_axis_banner_choice(self, behaviour: str) -> None:
        cache = self._axis_redefine_cache
        if cache is None:
            return
        if cache.behaviour == behaviour:
            self._hide_axis_feedback_banner()
            return
        self._apply_axis_definition(cache, behaviour, fit_view=False)
        self._update_axis_behaviour_combo(behaviour, update_preferences=True)
        self._show_axis_feedback_banner(cache)

    def _on_axis_behaviour_combo_changed(self, index: int) -> None:
        behaviour = self._axis_behaviour_from_index(index)
        self._preferences.set_axis_redefinition_mode(behaviour)
        if self._axis_redefine_cache is not None:
            self._refresh_axis_feedback_buttons(self._axis_redefine_cache.behaviour or behaviour)

    def _update_axis_labels(self) -> None:
        unit = "µm" if self._calibration is not None else "px"
        axis_bottom = self._plot_item.getAxis("bottom")
        axis_left = self._plot_item.getAxis("left")
        axis_bottom.setLabel(f"X ({unit})")
        axis_left.setLabel(f"Y ({unit})")
        for axis in (axis_bottom, axis_left):
            axis.picture = None
            axis.update()

    def _micrometres_to_axis_pixels(self, points_um: np.ndarray) -> np.ndarray:
        if self._calibration is None:
            raise RuntimeError("A calibration is required for micrometre conversion.")
        return axis_micrometre_to_axis_pixels(
            points_um, self._axis_definition(), self._calibration
        )

    def _setup_roi_properties_panel(self) -> None:
        stack = self.ui.stackedWidget_roi_properties
        stack.setCurrentWidget(self.ui.page_roi_placeholder)
        table = self.ui.tableWidget_polygon_points
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for spin in (
            self.ui.doubleSpinBox_rect_width,
            self.ui.doubleSpinBox_rect_height,
        ):
            spin.setDecimals(6)
            spin.setMinimum(1e-6)
            spin.setMaximum(1e9)
            spin.setSingleStep(0.1)
        self.ui.doubleSpinBox_rect_angle.setDecimals(3)
        self.ui.doubleSpinBox_rect_angle.setRange(-180.0, 180.0)
        self.ui.doubleSpinBox_rect_angle.setSingleStep(1.0)

    def _show_roi_placeholder(self) -> None:
        table = self.ui.tableWidget_polygon_points
        self._updating_roi_properties = True
        try:
            table.blockSignals(True)
            table.setRowCount(0)
        finally:
            table.blockSignals(False)
            self._updating_roi_properties = False
        self.ui.stackedWidget_roi_properties.setCurrentWidget(
            self.ui.page_roi_placeholder
        )

    def _populate_polygon_properties(self, shape: roi_manager.PolygonShape) -> None:
        points = np.asarray(shape.get_points(), dtype=float)
        table = self.ui.tableWidget_polygon_points
        self._updating_roi_properties = True
        try:
            table.blockSignals(True)
            table.setRowCount(points.shape[0])
            for row in range(points.shape[0]):
                for col in range(2):
                    value = float(points[row, col]) if points.size else 0.0
                    text = f"{value:.6f}"
                    existing = table.item(row, col)
                    if existing is None:
                        table.setItem(row, col, QTableWidgetItem(text))
                    else:
                        existing.setText(text)
        finally:
            table.blockSignals(False)
            self._updating_roi_properties = False
        self.ui.stackedWidget_roi_properties.setCurrentWidget(
            self.ui.page_roi_polygon
        )

    def _populate_rectangle_properties(
        self, shape: roi_manager.RectangleShape
    ) -> None:
        state = dict(shape.roi.state)
        width, height = state.get("size", (0.0, 0.0))
        angle = float(state.get("angle", 0.0))
        width = float(width)
        height = float(height)
        spins = (
            self.ui.doubleSpinBox_rect_width,
            self.ui.doubleSpinBox_rect_height,
            self.ui.doubleSpinBox_rect_angle,
        )
        values = (width, height, angle)
        self._updating_roi_properties = True
        try:
            for spin, value in zip(spins, values):
                spin.blockSignals(True)
                spin.setValue(value)
        finally:
            for spin in spins:
                spin.blockSignals(False)
            self._updating_roi_properties = False
        self.ui.stackedWidget_roi_properties.setCurrentWidget(
            self.ui.page_roi_rectangle
        )

    def _refresh_roi_properties(self) -> None:
        item = self._roi_properties_item
        if item is None:
            self._show_roi_placeholder()
            return
        shape = self.roi_manager.get_shape(item)
        if shape is None:
            self._roi_properties_item = None
            self._show_roi_placeholder()
            return
        shape_type = str(shape.shape_type).lower()
        if shape_type == "rectangle":
            self._populate_rectangle_properties(shape)
        elif shape_type == "polygon":
            self._populate_polygon_properties(shape)
        else:
            self._show_roi_placeholder()

    def _set_roi_properties_item(self, item: QTreeWidgetItem | None) -> None:
        if item is None or not self.roi_manager.have_item(item):
            self._roi_properties_item = None
            self._show_roi_placeholder()
            return
        self._roi_properties_item = item
        self._refresh_roi_properties()

    def _on_tree_selection_changed(self) -> None:
        items = self.ui.treeWidget.selectedItems()
        if not items:
            self.roi_manager.clear_visible_only()
            self._set_roi_properties_item(None)
            return
        self.roi_manager.show_for_item(items[0])
        roi_item = next(
            (candidate for candidate in items if self.roi_manager.have_item(candidate)),
            None,
        )
        self._set_roi_properties_item(roi_item)

    def _on_roi_shape_edited(self, item: QTreeWidgetItem) -> None:
        if item is self._roi_properties_item:
            self._refresh_roi_properties()

    def _on_polygon_point_changed(self, table_item: QTableWidgetItem) -> None:
        if self._updating_roi_properties or table_item is None:
            return
        item = self._roi_properties_item
        if item is None:
            return
        shape = self.roi_manager.get_shape(item)
        if shape is None or str(shape.shape_type).lower() != "polygon":
            return
        try:
            value = float(table_item.text())
        except (TypeError, ValueError):
            self._refresh_roi_properties()
            return
        points = np.asarray(shape.get_points(), dtype=float)
        row = table_item.row()
        col = table_item.column()
        if row < 0 or col < 0:
            return
        if row >= points.shape[0] or col >= points.shape[1]:
            return
        points[row, col] = value
        shape.set_points(points)
        self.roi_manager.shapeEdited.emit(item)
        self._refresh_roi_properties()

    def _on_rectangle_property_changed(self, _value: float) -> None:
        if self._updating_roi_properties:
            return
        item = self._roi_properties_item
        if item is None:
            return
        shape = self.roi_manager.get_shape(item)
        if shape is None or str(shape.shape_type).lower() != "rectangle":
            return
        width = max(float(self.ui.doubleSpinBox_rect_width.value()), 1e-6)
        height = max(float(self.ui.doubleSpinBox_rect_height.value()), 1e-6)
        angle = float(self.ui.doubleSpinBox_rect_angle.value())
        points = np.asarray(shape.get_points(), dtype=float)
        if points.shape[0] < 4:
            return
        center = np.mean(points, axis=0)
        angle_rad = math.radians(angle)
        u = np.array([math.cos(angle_rad), math.sin(angle_rad)], dtype=float)
        v = np.array([-u[1], u[0]], dtype=float)
        half_w = 0.5 * width
        half_h = 0.5 * height
        new_points = np.array(
            [
                center - half_w * u - half_h * v,
                center + half_w * u - half_h * v,
                center + half_w * u + half_h * v,
                center - half_w * u + half_h * v,
            ],
            dtype=float,
        )
        shape.set_points(new_points)
        self.roi_manager.shapeEdited.emit(item)
        self._refresh_roi_properties()

    def _update_image_transform(self) -> None:
        if not self._axis_defined:
            self._image_item.setTransform(QTransform())
            return
        ox, oy = self._axis_origin_camera.astype(float)
        cos_a = float(np.cos(self._axis_angle_rad))
        sin_a = float(np.sin(self._axis_angle_rad))
        tx = -(cos_a * ox + sin_a * oy)
        ty = sin_a * ox - cos_a * oy
        transform = QTransform(
            cos_a,
            -sin_a,
            0.0,
            sin_a,
            cos_a,
            0.0,
            tx,
            ty,
            1.0,
        )
        self._image_item.setTransform(transform)

    def _image_axis_bounds(self) -> tuple[float, float, float, float]:
        if self._current_image is None:
            return (-50.0, 50.0, -50.0, 50.0)
        height, width = self._current_image.shape[:2]
        corners_camera = np.array(
            [[0.0, 0.0], [float(width), 0.0], [float(width), float(height)], [0.0, float(height)]],
            dtype=float,
        )
        corners_axis = self._camera_to_axis(corners_camera)
        min_x = float(np.min(corners_axis[:, 0]))
        max_x = float(np.max(corners_axis[:, 0]))
        min_y = float(np.min(corners_axis[:, 1]))
        max_y = float(np.max(corners_axis[:, 1]))
        return min_x, max_x, min_y, max_y

    def _update_axis_visuals(self) -> None:
        show = self._axis_defined
        for item in (self._axis_line_item, self._axis_arrow_item, self._axis_origin_item):
            item.setVisible(show)
        if not show:
            return
        min_x, max_x, min_y, max_y = self._image_axis_bounds()
        span = max(max_x - min_x, max_y - min_y, 1.0)
        origin_x, origin_y = 0.0, 0.0
        end_x, end_y = span * 0.25, 0.0
        self._axis_line_item.setData([origin_x, end_x], [origin_y, end_y])
        self._axis_arrow_item.setPos(end_x, end_y)
        self._axis_arrow_item.setStyle(angle=0.0)
        self._axis_origin_item.setData([origin_x], [origin_y])

    def _update_zoom_constraints(self, _width: int, _height: int) -> None:
        view_box = self._get_view_box()
        view_box.setLimits(
            minXRange=1.0,
            minYRange=1.0,
            maxXRange=None,
            maxYRange=None,
        )

    def _fit_view_to_image(self, *, use_axis: bool = True) -> None:
        if use_axis and self._axis_defined:
            min_x, max_x, min_y, max_y = self._image_axis_bounds()
        else:
            if self._current_image is None:
                min_x = max_x = min_y = max_y = 0.0
            else:
                height, width = self._current_image.shape[:2]
                min_x, max_x = 0.0, float(width)
                min_y, max_y = 0.0, float(height)
        span_x = max_x - min_x
        span_y = max_y - min_y
        span = max(span_x, span_y, 1.0)
        margin = max(span * 0.05, 1.0)
        half_span = span / 2.0 + margin
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        x_range = (center_x - half_span, center_x + half_span)
        y_range = (center_y - half_span, center_y + half_span)
        self._update_zoom_constraints(int(span), int(span))
        self._get_view_box().setRange(xRange=x_range, yRange=y_range, padding=0.0)

    def _set_axis_state(
        self, origin_camera: np.ndarray, angle_rad: float, defined: bool
    ) -> None:
        self._axis_origin_camera = np.asarray(origin_camera, dtype=float)
        self._axis_angle_rad = float(angle_rad)
        self._axis_defined = defined
        self._update_image_transform()
        self._update_axis_visuals()
        self._update_listener_controls()

    def _apply_axis_definition(
        self,
        cache: _AxisRedefinitionCache,
        behaviour: str,
        *,
        fit_view: bool,
    ) -> None:
        """Apply an axis redefinition using the supplied behaviour."""

        self._axis_origin_camera = np.asarray(cache.new_origin, dtype=float)
        self._axis_angle_rad = float(cache.new_angle)
        self._axis_defined = True
        self._update_image_transform()

        if cache.shapes:
            if (
                behaviour == self._AXIS_MODE_MOVE
                and cache.behaviour != self._AXIS_MODE_MOVE
            ):
                self._reproject_shapes_from_cache(cache)
            elif (
                behaviour == self._AXIS_MODE_KEEP
                and cache.behaviour not in (None, self._AXIS_MODE_KEEP)
            ):
                self._restore_shapes_from_cache(cache)
        cache.behaviour = behaviour

        self._update_axis_visuals()
        if fit_view:
            self._fit_view_to_image()
        self._update_listener_controls()

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
        QTimer.singleShot(0, self._ensure_calibration_available)

    def _ensure_calibration_available(self) -> None:
        stored_path = self.last_calibration_file_path()
        if stored_path:
            success, _ = self._load_calibration_from_path(stored_path)
            if success:
                return
        self._calibrate_dmd()

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
            capture = InteractiveRectangleCapture(self._get_view_box(), self)
            rect = capture.exec()
        finally:
            button.setEnabled(True)
        if rect is None or rect.width() <= 0.0 or rect.height() <= 0.0:
            return
        points = self._rect_to_polygon_points(rect)
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
            capture = PolygonDrawingCapture(self._get_view_box(), self)
            points = capture.exec()
        finally:
            button.setEnabled(True)
        if not points or len(points) < 3:
            return
        array = np.array([[pt.x(), pt.y()] for pt in points], dtype=float)
        self._create_roi_item(parent_item, array, "polygon")

    def _ensure_grid_preview_overlay(self) -> _GridPreviewOverlay:
        if self._grid_preview_overlay is None:
            self._grid_preview_overlay = _GridPreviewOverlay(self._plot_item)
        return self._grid_preview_overlay

    def _open_grid_dialog(self) -> None:
        if self._grid_dialog is not None:
            self._grid_dialog.raise_()
            self._grid_dialog.activateWindow()
            return
        dialog = GridDialog(self, defaults=self._grid_last_parameters)
        dialog.setModal(True)
        dialog.parametersChanged.connect(self._on_grid_parameters_changed)
        dialog.accepted.connect(self._on_grid_dialog_accepted)
        dialog.finished.connect(self._on_grid_dialog_finished)
        self._grid_dialog = dialog
        # Ensure the preview reflects the current parameters as soon as the dialog opens.
        self._on_grid_parameters_changed(dialog.parameters())
        dialog.open()

    def _on_grid_parameters_changed(self, params: GridParameters) -> None:
        self._grid_last_parameters = params
        if params.is_valid():
            self._preferences.set_grid_parameters(params)
        overlay = self._ensure_grid_preview_overlay()
        rectangles = params.rectangle_points()
        if rectangles:
            overlay.set_rectangles(rectangles)
        else:
            overlay.hide()

    def _on_grid_dialog_accepted(self) -> None:
        dialog = self._grid_dialog
        if dialog is None:
            return
        params = dialog.parameters()
        rectangles = params.rectangle_points()
        if not rectangles:
            return
        description_base = f"Grid {params.rows}x{params.columns}"
        total = len(rectangles)
        for idx, rect in enumerate(rectangles, start=1):
            self.tree_manager.add_pattern()
            pattern_index = self.ui.treeWidget.topLevelItemCount() - 1
            pattern_item = self.ui.treeWidget.topLevelItem(pattern_index)
            if pattern_item is None:
                continue
            suffix = "" if total == 1 else f" ({idx}/{total})"
            self.tree_manager.set_pattern_label(
                pattern_item, pattern_index, f"{description_base}{suffix}"
            )
            self._create_roi_item(pattern_item, rect, "rectangle")
        if rectangles:
            self.tree_manager.renumber_pattern_labels()

    def _on_grid_dialog_finished(self, _result: int) -> None:
        self._grid_dialog = None
        if self._grid_preview_overlay is not None:
            self._grid_preview_overlay.hide()

    def _reset_image_view(self) -> None:
        if self._current_image is None:
            return
        height, width = self._current_image.shape[:2]
        self._update_zoom_constraints(width, height)
        view_box = self._get_view_box()
        view_box.enableAutoRange(pg.ViewBox.XYAxes, enable=False)
        self._fit_view_to_image(use_axis=self._axis_defined)

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

    def _set_image(
        self,
        image: np.ndarray,
        *,
        fit_to_view: bool = False,
        apply_axis: bool = True,
        auto_contrast: bool = False,
    ) -> None:
        """Display ``image`` and optionally adapt the view/contrast settings."""
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
        use_previous_levels = previous_levels is not None and not auto_contrast
        auto_levels_flag = not use_previous_levels
        levels = previous_levels if use_previous_levels else None
        self._image_item.setImage(
            display_image,
            autoLevels=auto_levels_flag,
            autoDownsample=False,
            levels=levels,
        )
        self._image_item.setRect(QRectF(0.0, 0.0, float(width), float(height)))
        self._image_item.setPos(0.0, 0.0)
        self._current_image = image
        if auto_contrast:
            self._apply_auto_levels_clipped()
        elif use_previous_levels and levels is not None:
            self._hist_widget.region.setRegion(levels)
        else:
            self._store_histogram_levels()
        if apply_axis and self._axis_defined:
            self._update_image_transform()
            self._update_axis_visuals()
        else:
            self._image_item.setTransform(QTransform())
            for item in (
                self._axis_line_item,
                self._axis_arrow_item,
                self._axis_origin_item,
            ):
                item.hide()
        self._update_zoom_constraints(width, height)
        view_box.enableAutoRange(pg.ViewBox.XYAxes, enable=False)
        if preserve_view and previous_range is not None:
            x_range, y_range = previous_range
            view_box.setRange(xRange=x_range, yRange=y_range, padding=0.0)
        else:
            self._fit_view_to_image(use_axis=apply_axis and self._axis_defined)

    def _store_histogram_levels(self) -> None:
        try:
            low, high = self._hist_widget.region.getRegion()
            self._current_levels = (float(low), float(high))
        except Exception:
            self._current_levels = None

    def _load_image(self, path: str | None = "") -> None:
        """Load an image from *path* or prompt the user to choose one."""

        if not isinstance(path, str):
            # QPushButton.clicked passes a boolean; treat any non-str as a fresh pick.
            path = ""

        chosen_path = path.strip()
        if not chosen_path:
            initial_dir = self.ui.lineEdit_image_folder_path.text().strip()
            file_filter = "Image files (*.png *.jpg *.jpeg *.tif *.tiff *.gif);;All files (*)"
            chosen_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select image",
                initial_dir if initial_dir else "",
                file_filter,
            )
            if not chosen_path:
                return

        try:
            with Image.open(chosen_path) as pil_image:
                image = np.array(pil_image)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Image load error",
                f"Unable to open image file:\n{exc}",
            )
            return

        directory = os.path.dirname(chosen_path)
        if directory:
            self.ui.lineEdit_image_folder_path.setText(directory)

        self._set_image(image, fit_to_view=True, auto_contrast=True)

    def _calibrate_dmd(self):
        action = self._prompt_calibration_action()
        if action is None:
            return
        if action == "load":
            self._load_calibration_from_dialog()
        elif action == "define":
            self._define_new_calibration()

    def _prompt_calibration_action(self) -> str | None:
        prompt = QMessageBox(self)
        prompt.setWindowTitle("Calibrate DMD")
        prompt.setIcon(QMessageBox.Icon.Question)
        prompt.setText("Choose how to obtain a DMD calibration.")
        load_button = prompt.addButton(
            "Load calibration file", QMessageBox.ButtonRole.ActionRole
        )
        define_button = prompt.addButton(
            "Define new calibration", QMessageBox.ButtonRole.ActionRole
        )
        prompt.addButton(QMessageBox.StandardButton.Cancel)
        if self._calibration is None:
            prompt.setDefaultButton(define_button)
        else:
            prompt.setDefaultButton(load_button)
        prompt.exec()
        clicked = prompt.clickedButton()
        if clicked is None:
            return None
        standard = prompt.standardButton(clicked)
        if standard == QMessageBox.StandardButton.Cancel:
            return None
        if clicked is load_button:
            return "load"
        if clicked is define_button:
            return "define"
        return None

    def _load_calibration_from_dialog(self) -> None:
        last_path = self.last_calibration_file_path()
        initial = ""
        if last_path:
            candidate = Path(str(last_path)).expanduser()
            if candidate.exists():
                initial = str(candidate)
            else:
                parent = candidate.parent
                if parent.exists():
                    initial = str(parent)
        file_filter = "Calibration files (*.h5 *.hdf5);;All files (*)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select calibration file",
            initial,
            file_filter,
        )
        if not file_path:
            return
        success, error = self._load_calibration_from_path(file_path)
        if not success:
            QMessageBox.warning(
                self,
                "Calibration load error",
                f"Unable to load calibration file:\n{error}",
            )

    def _define_new_calibration(self) -> None:
        """Guide the user through loading a calibration image and storing it."""

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

        # Swap the display to the calibration image but remember the previous
        # session so we can restore it if the workflow is cancelled mid-way.
        self._set_image(
            calibration_image,
            fit_to_view=True,
            apply_axis=False,
            auto_contrast=True,
        )

        diagonal_points = self._prompt_calibration_diagonal()
        if diagonal_points is None:
            QMessageBox.information(
                self,
                "Calibration cancelled",
                "No calibration diagonal was drawn. Calibration has been cancelled.",
            )
            self._restore_after_calibration(previous_image, previous_view, selected_item)
            return

        invert_defaults = self._preferences.axes_inverted()
        dialog = _CalibrationDialog(
            self,
            default_mirrors=self._preferences.mirror_counts(),
            default_pixel_size=self._preferences.pixel_size(),
            default_invert_axes=bool(invert_defaults[0] or invert_defaults[1]),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._restore_after_calibration(previous_image, previous_view, selected_item)
            return

        square_mirrors, pixel_size, invert_axes = dialog.values()
        self._preferences.set_mirror_counts(square_mirrors, square_mirrors)
        self._preferences.set_pixel_size(pixel_size)
        self._preferences.set_axes_inverted(invert_axes, invert_axes)
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
                diagonal_points,
                square_mirrors,
                pixel_size,
                camera_shape=camera_shape,
                dmd_shape=dmd_shape,
                invert_x=invert_axes,
                invert_y=invert_axes,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Calibration failed", str(exc))
            self._restore_after_calibration(previous_image, previous_view, selected_item)
            return

        self.calibration = calibration
        print(
            "Updated DMD calibration: pixels/mirror=(%.3f, %.3f), µm/mirror=(%.3f, %.3f), rotation=%.2f°"
            % (
                calibration.camera_pixels_per_mirror[0],
                calibration.camera_pixels_per_mirror[1],
                calibration.micrometers_per_mirror[0],
                calibration.micrometers_per_mirror[1],
                np.degrees(calibration.camera_rotation_rad),
            )
        )
        self._prompt_save_calibration(calibration)
        self._restore_after_calibration(previous_image, previous_view, selected_item)

    def _prompt_save_calibration(self, calibration: DMDCalibration) -> None:
        response = QMessageBox.question(
            self,
            "Save calibration",
            "Do you want to save this calibration to a file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        last_path = self.last_calibration_file_path()
        initial = ""
        if last_path:
            candidate = Path(str(last_path)).expanduser()
            if candidate.exists():
                initial = str(candidate)
            else:
                parent = candidate.parent
                if parent.exists():
                    initial = str(parent / candidate.name)
        file_filter = "Calibration files (*.h5 *.hdf5);;All files (*)"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save calibration",
            initial,
            file_filter,
        )
        if not file_path:
            return
        root, ext = os.path.splitext(file_path)
        if not ext:
            file_path = f"{file_path}.h5"
        self._save_calibration_to_path(calibration, file_path)

    def _save_calibration_to_path(
        self, calibration: DMDCalibration, file_path: str
    ) -> bool:
        path = Path(str(file_path)).expanduser()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            saving.save_calibration(str(path), calibration)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Save failed",
                f"Unable to save calibration file:\n{exc}",
            )
            return False
        self.remember_calibration_file(str(path))
        print(f"Saved DMD calibration to {path}")
        return True

    def _load_calibration_from_path(self, path_str: str) -> tuple[bool, str | None]:
        """Load calibration from disk and activate it."""
        path = Path(str(path_str)).expanduser()
        try:
            calibration = saving.load_calibration(str(path))
        except Exception as exc:
            message = f"{path}: {exc}"
            print(f"Failed to load stored calibration from {message}")
            return False, message
        self.calibration = calibration
        self.remember_calibration_file(str(path))
        try:
            pixel_size = calibration.camera_pixel_size_um
        except AttributeError:
            pixel_size = None
        if pixel_size is not None:
            self._preferences.set_pixel_size(float(pixel_size))
        print(f"Active DMD calibration: {path}")
        return True, None

    def _prompt_calibration_diagonal(self) -> np.ndarray | None:
        """Capture the diagonal of the illuminated calibration square."""

        prompt = QMessageBox(self)
        prompt.setWindowTitle("Select calibration diagonal")
        prompt.setIcon(QMessageBox.Icon.Information)
        prompt.setText("Draw the diagonal of the illuminated calibration square.")
        prompt.setInformativeText(
            "Left-click and drag to draw the line. Right-click or press Esc to cancel."
        )
        prompt.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok
        )
        if prompt.exec() != QMessageBox.StandardButton.Ok:
            return None

        capture = AxisCapture(self._get_view_box(), self)
        segment = capture.exec()
        if segment is None:
            return None
        start, end = segment
        start_xy = np.array([start.x(), start.y()], dtype=float)
        end_xy = np.array([end.x(), end.y()], dtype=float)
        if not np.all(np.isfinite(start_xy)) or not np.all(np.isfinite(end_xy)):
            return None
        if np.linalg.norm(end_xy - start_xy) < 1e-9:
            return None
        return np.vstack((start_xy, end_xy))

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
            self._set_image(previous_image, auto_contrast=True)
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
        self._set_image(image, fit_to_view=True, auto_contrast=True)

    def _show_grid(self):
        show = self.ui.pushButton_show_grid.isChecked()
        self._plot_item.showGrid(show, show)

    def _define_axis(self):
        button = self.ui.pushButton_define_axis
        if not button.isEnabled():
            return
        button.setChecked(True)
        print(
            "Axis tool: click to set origin, drag to direction, release to confirm. Right-click or Esc cancels."
        )
        capture = AxisCapture(self._get_view_box(), self)
        result = capture.exec()
        button.setChecked(False)
        if result is None:
            return
        origin_view, end_view = result
        origin_axis = np.array([origin_view.x(), origin_view.y()], dtype=float)
        end_axis = np.array([end_view.x(), end_view.y()], dtype=float)
        vector_axis = end_axis - origin_axis
        if np.linalg.norm(vector_axis) < 1e-6:
            return
        origin_camera = self._axis_to_camera(origin_axis)
        direction_camera = self._rotation_matrix() @ vector_axis
        angle_camera = float(np.arctan2(direction_camera[1], direction_camera[0]))
        shapes_export = {
            item: (np.asarray(points, dtype=float), shape_type)
            for item, (points, shape_type) in self.roi_manager.export_shape_points().items()
        }
        cache = _AxisRedefinitionCache(
            previous_origin=self._axis_origin_camera.copy(),
            previous_angle=self._axis_angle_rad,
            new_origin=np.asarray(origin_camera, dtype=float),
            new_angle=angle_camera,
            shapes=shapes_export,
        )
        self._axis_redefine_cache = cache
        behaviour = self._default_axis_behaviour()
        self._apply_axis_definition(cache, behaviour, fit_view=True)
        if cache.shapes:
            self._show_axis_feedback_banner(cache)
        else:
            self._hide_axis_feedback_banner()

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
