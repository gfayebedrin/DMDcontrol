"""Axis utilities shared by :class:`stim1p.ui.dmd_stim_widget.StimDMDWidget`.

This module gathers all axis-related helpers that were previously embedded in the
main widget.  The helpers are grouped as a mixin so the widget can opt-in to
axis behaviour without inheriting an unwieldy monolithic implementation.  The
functions are intentionally verbose and document the underlying geometry
transformations so contributors can reason about the math without having to
reverse-engineer the matrix operations each time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from ...logic.calibration import DMDCalibration
from ...logic.geometry import (
    AxisDefinition,
    axis_micrometre_scale,
    axis_micrometre_to_axis_pixels,
    axis_pixels_to_axis_micrometre,
)
from ..capture_tools import AxisCapture

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from PySide6.QtWidgets import QTreeWidgetItem


@dataclass
class AxisRedefinitionCache:
    """Cache state from an axis redefinition interaction.

    The cache stores the previous and pending axis definitions alongside the
    projected shape coordinates.  After the user chooses how to treat existing
    ROIs the cache allows us to either restore the original points or reproject
    them into the new axis frame without recalculating the capture.
    """

    previous_origin: np.ndarray
    previous_angle: float
    new_origin: np.ndarray
    new_angle: float
    shapes: dict["QTreeWidgetItem", tuple[np.ndarray, str]]
    behaviour: str | None = None


class AxisControlsMixin:
    """Mixin implementing axis definition and behaviour helpers.

    The mixin assumes the host widget exposes several attributes used
    throughout the original implementation (for example ``self.ui`` or
    ``self.roi_manager``).  Centralising the logic here makes it possible to
    document the coordinate conversions and UI state transitions in one place
    instead of scattering them through the widget class.
    """

    _calibration: DMDCalibration | None
    _axis_origin_camera: np.ndarray
    _axis_angle_rad: float
    _axis_defined: bool
    _axis_redefine_cache: AxisRedefinitionCache | None

    def _axis_definition(self) -> AxisDefinition:
        """Build an :class:`AxisDefinition` describing the current axis."""

        origin = tuple(float(v) for v in self._axis_origin_camera.reshape(2))
        return AxisDefinition(origin_camera=origin, angle_rad=float(self._axis_angle_rad))

    def _rotation_matrix(self, angle: float | None = None) -> np.ndarray:
        """Return the 2D rotation matrix for ``angle`` radians.

        If no ``angle`` is supplied we reuse the current axis angle.  The helper
        is intentionally explicit so the accompanying unit tests and future
        contributors can audit the trigonometric operations without digging into
        NumPy internals.
        """

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
        """Convert camera pixel coordinates into the user-defined axis frame.

        ``points`` can be a single 2D coordinate or an array of coordinates.  We
        normalise the input to a two-dimensional array, subtract the chosen
        origin, rotate into axis space and return the result with the original
        dimensionality preserved.
        """

        arr = np.asarray(points, dtype=float)
        was_1d = arr.ndim == 1
        pts = np.atleast_2d(arr)
        origin_vec = (
            self._axis_origin_camera if origin is None else np.asarray(origin, dtype=float)
        )
        R = self._rotation_matrix(angle)
        relative = pts - origin_vec
        result = (R.T @ relative.T).T
        return result[0] if was_1d else result

    def _axis_to_camera(
        self,
        points: np.ndarray,
        *,
        origin: np.ndarray | None = None,
        angle: float | None = None,
    ) -> np.ndarray:
        """Convert axis-aligned coordinates back to camera pixel indices.

        This performs the inverse transform to :meth:`_camera_to_axis` and is
        documented separately so it is obvious that the rotation matrix is used
        in the forward direction.  Maintaining symmetry between the two helpers
        is important for ROI reprojection.
        """

        arr = np.asarray(points, dtype=float)
        was_1d = arr.ndim == 1
        pts = np.atleast_2d(arr)
        origin_vec = (
            self._axis_origin_camera if origin is None else np.asarray(origin, dtype=float)
        )
        R = self._rotation_matrix(angle)
        result = (R @ pts.T).T + origin_vec
        return result[0] if was_1d else result

    def _axis_origin_micrometre(
        self, origin_camera: np.ndarray | None = None
    ) -> np.ndarray:
        """Return the axis origin in micrometres using the active calibration."""

        if self._calibration is None:
            raise RuntimeError("A calibration is required for micrometre conversion.")
        origin_vec = (
            self._axis_origin_camera if origin_camera is None else np.asarray(origin_camera, dtype=float)
        )
        mic = self._calibration.camera_to_micrometre(origin_vec.reshape(2, 1)).T[0]
        return np.asarray(mic, dtype=float)

    def _axis_pixels_to_micrometres(self, points: np.ndarray) -> np.ndarray:
        """Convert axis-space pixels to micrometres, validating calibration."""

        if self._calibration is None:
            raise RuntimeError("A calibration is required for micrometre conversion.")
        return axis_pixels_to_axis_micrometre(points, self._axis_definition(), self._calibration)

    def _micrometres_to_axis_pixels(self, points_um: np.ndarray) -> np.ndarray:
        """Convert micrometre coordinates into axis pixels using calibration."""

        if self._calibration is None:
            raise RuntimeError("A calibration is required for micrometre conversion.")
        return axis_micrometre_to_axis_pixels(points_um, self._axis_definition(), self._calibration)

    def _axis_micrometre_scale(self) -> tuple[float, float] | None:
        """Compute micrometre-per-pixel scale factors for both axis directions."""

        if self._calibration is None:
            return None
        try:
            scales = axis_micrometre_scale(self._axis_definition(), self._calibration)
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

    def axis_unit_scale_for_orientation(self, orientation: str) -> float | None:
        """Return the micrometre scale factor corresponding to an axis label."""

        scales = self._axis_micrometre_scale()
        if scales is None:
            return None
        orient = orientation.lower()
        if orient in ("bottom", "top"):
            return scales[0]
        if orient in ("left", "right"):
            return scales[1]
        return None

    def _reproject_shapes_from_cache(self, cache: AxisRedefinitionCache) -> None:
        """Reproject cached ROI points into the new axis definition."""

        prev_origin = np.asarray(cache.previous_origin, dtype=float)
        prev_angle = float(cache.previous_angle)
        new_origin = np.asarray(cache.new_origin, dtype=float)
        new_angle = float(cache.new_angle)
        for item, (axis_points, shape_type) in cache.shapes.items():
            axis_pts = np.asarray(axis_points, dtype=float)
            camera_pts = self._axis_to_camera(axis_pts, origin=prev_origin, angle=prev_angle)
            axis_pts_new = self._camera_to_axis(camera_pts, origin=new_origin, angle=new_angle)
            self.roi_manager.update_shape(item, shape_type, axis_pts_new)

    def _restore_shapes_from_cache(self, cache: AxisRedefinitionCache) -> None:
        """Restore ROI geometry captured before redefining the axis."""

        for item, (axis_points, shape_type) in cache.shapes.items():
            self.roi_manager.update_shape(item, shape_type, axis_points)

    def _setup_axis_behaviour_controls(self) -> None:
        """Initialise the "axis behaviour" combo box and supporting mappings."""

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
        """Create a transient banner that appears after redefining the axis."""

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
        """Translate a combo box index into a behaviour identifier."""

        return self._axis_behaviour_by_index.get(index, self._AXIS_MODE_MOVE)

    def _axis_behaviour_label(self, behaviour: str) -> str:
        """Return a human readable label for an axis redefinition mode."""

        return self._AXIS_BEHAVIOUR_LABELS.get(behaviour, behaviour)

    def _default_axis_behaviour(self) -> str:
        """Resolve the default behaviour taking stored preferences into account."""

        return self._axis_behaviour_from_index(self.ui.comboBox_axis_behaviour.currentIndex())

    def _update_axis_behaviour_combo(self, behaviour: str, *, update_preferences: bool) -> None:
        """Synchronise the behaviour combo box and, optionally, saved preference."""

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

    def _show_axis_feedback_banner(self, cache: AxisRedefinitionCache) -> None:
        """Display the axis feedback banner summarising the applied behaviour."""

        if not cache.shapes:
            self._hide_axis_feedback_banner()
            return
        behaviour = cache.behaviour or self._default_axis_behaviour()
        description = self._axis_behaviour_label(behaviour)
        self._axis_feedback_label.setText(
            f'Axis updated; patterns set to "{description}". Change?'
        )
        self._refresh_axis_feedback_buttons(behaviour)
        self._axis_feedback_frame.setVisible(True)
        self._axis_feedback_timer.start(6000)

    def _hide_axis_feedback_banner(self) -> None:
        """Hide and reset the feedback banner timer."""

        self._axis_feedback_timer.stop()
        self._axis_feedback_frame.setVisible(False)

    def _refresh_axis_feedback_buttons(self, behaviour: str) -> None:
        """Enable/disable the axis feedback buttons based on ``behaviour``."""

        move_active = behaviour == self._AXIS_MODE_MOVE
        keep_active = behaviour == self._AXIS_MODE_KEEP
        self._axis_feedback_move_button.setEnabled(not move_active)
        self._axis_feedback_move_button.setDefault(move_active)
        self._axis_feedback_keep_button.setEnabled(not keep_active)
        self._axis_feedback_keep_button.setDefault(keep_active)

    def _handle_axis_banner_choice(self, behaviour: str) -> None:
        """Respond to the user clicking a behaviour button in the banner."""

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
        """Persist a manual change in the behaviour combo box."""

        behaviour = self._axis_behaviour_from_index(index)
        self._preferences.set_axis_redefinition_mode(behaviour)
        if self._axis_redefine_cache is not None:
            self._refresh_axis_feedback_buttons(
                self._axis_redefine_cache.behaviour or behaviour
            )

    def _update_axis_labels(self) -> None:
        """Refresh the axis labels to reflect whether calibration is active."""

        unit = "µm" if self._calibration is not None else "px"
        axis_bottom = self._plot_item.getAxis("bottom")
        axis_left = self._plot_item.getAxis("left")
        axis_bottom.setLabel(f"X ({unit})")
        axis_left.setLabel(f"Y ({unit})")
        for axis in (axis_bottom, axis_left):
            axis.picture = None
            axis.update()

    def _image_axis_bounds(self) -> tuple[float, float, float, float]:
        """Return the bounding box of the current image expressed in axis space."""

        if self._current_image is None:
            return (-50.0, 50.0, -50.0, 50.0)
        height, width = self._current_image.shape[:2]
        corners_camera = np.array(
            [
                [0.0, 0.0],
                [float(width), 0.0],
                [float(width), float(height)],
                [0.0, float(height)],
            ],
            dtype=float,
        )
        corners_axis = self._camera_to_axis(corners_camera)
        min_x = float(np.min(corners_axis[:, 0]))
        max_x = float(np.max(corners_axis[:, 0]))
        min_y = float(np.min(corners_axis[:, 1]))
        max_y = float(np.max(corners_axis[:, 1]))
        return min_x, max_x, min_y, max_y

    def _update_axis_visuals(self) -> None:
        """Synchronise the origin/arrow items with the current axis definition."""

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

    def _set_axis_state(self, origin_camera: np.ndarray, angle_rad: float, defined: bool) -> None:
        """Update axis properties and refresh associated visuals/listeners."""

        self._axis_origin_camera = np.asarray(origin_camera, dtype=float)
        self._axis_angle_rad = float(angle_rad)
        self._axis_defined = defined
        self._update_image_transform()
        self._update_axis_visuals()
        self._update_listener_controls()

    def _apply_axis_definition(
        self,
        cache: AxisRedefinitionCache,
        behaviour: str,
        *,
        fit_view: bool,
    ) -> None:
        """Apply an axis redefinition using the supplied behaviour.

        ``cache`` contains both the new axis parameters and a snapshot of the
        ROI geometry prior to the change.  Depending on ``behaviour`` the method
        either reprojects the shapes into the new axis or keeps them untouched.
        ``fit_view`` allows callers to control whether the image view is
        realigned after the update (useful after drawing a brand-new axis).
        """

        self._axis_origin_camera = np.asarray(cache.new_origin, dtype=float)
        self._axis_angle_rad = float(cache.new_angle)
        self._axis_defined = True
        self._update_image_transform()

        if cache.shapes:
            if behaviour == self._AXIS_MODE_MOVE and cache.behaviour != self._AXIS_MODE_MOVE:
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

    def _define_axis(self) -> None:
        """Enter the interactive axis capture tool and update state accordingly."""

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
        cache = AxisRedefinitionCache(
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
