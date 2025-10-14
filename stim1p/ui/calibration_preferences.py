"""Lightweight wrapper around :class:`~PySide6.QtCore.QSettings`.

Persisting calibration selections keeps the widget stateful between launches,
but the original implementation embedded the persistence logic inside the
already-large widget module.  This helper exposes a focused API for reading and
writing the values we care about without tying it to the widget directly.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

from .grid_dialog import GridParameters


class CalibrationPreferences:
    """Store calibration paths and defaults in the platform settings backend."""

    _ORG = "Stim1P"
    _APP = "DMDStim"
    _KEY_LAST_FILE = "calibration/last_file_path"
    _KEY_LAST_IMAGE = "calibration/last_image_path"
    _KEY_MIRRORS_X = "calibration/mirrors_x"
    _KEY_MIRRORS_Y = "calibration/mirrors_y"
    _KEY_PIXEL_SIZE = "calibration/pixel_size"
    _KEY_AXIS_BEHAVIOUR = "axis/redefinition_mode"
    _AXIS_BEHAVIOUR_DEFAULT = "move"
    _KEY_INVERT_X = "calibration/invert_x"
    _KEY_INVERT_Y = "calibration/invert_y"
    _KEY_GRID_ROWS = "grid/rows"
    _KEY_GRID_COLUMNS = "grid/columns"
    _KEY_GRID_WIDTH = "grid/rect_width"
    _KEY_GRID_HEIGHT = "grid/rect_height"
    _KEY_GRID_SPACING_X = "grid/spacing_x"
    _KEY_GRID_SPACING_Y = "grid/spacing_y"
    _KEY_GRID_ANGLE = "grid/angle"
    _KEY_GRID_ORIGIN_X = "grid/origin_x"
    _KEY_GRID_ORIGIN_Y = "grid/origin_y"

    def __init__(self) -> None:
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

    @staticmethod
    def _to_bool(value, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "t", "yes", "y"}:
                return True
            if lowered in {"0", "false", "f", "no", "n"}:
                return False
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

    def axes_inverted(self) -> tuple[bool, bool]:
        inv_x = self._to_bool(self._settings.value(self._KEY_INVERT_X), False)
        inv_y = self._to_bool(self._settings.value(self._KEY_INVERT_Y), False)
        return inv_x, inv_y

    def set_axes_inverted(self, invert_x: bool, invert_y: bool) -> None:
        self._settings.setValue(self._KEY_INVERT_X, bool(invert_x))
        self._settings.setValue(self._KEY_INVERT_Y, bool(invert_y))
        self._settings.sync()

    def axis_redefinition_mode(self) -> str:
        value = self._to_str(self._settings.value(self._KEY_AXIS_BEHAVIOUR, self._AXIS_BEHAVIOUR_DEFAULT))
        if value in ("move", "keep"):
            return value
        return self._AXIS_BEHAVIOUR_DEFAULT

    def set_axis_redefinition_mode(self, mode: str) -> None:
        if mode not in ("move", "keep"):
            mode = self._AXIS_BEHAVIOUR_DEFAULT
        self._settings.setValue(self._KEY_AXIS_BEHAVIOUR, mode)
        self._settings.sync()

    def grid_parameters(self) -> GridParameters:
        return GridParameters(
            rows=self._to_int(self._settings.value(self._KEY_GRID_ROWS), 2),
            columns=self._to_int(self._settings.value(self._KEY_GRID_COLUMNS), 2),
            rect_width=self._to_float(self._settings.value(self._KEY_GRID_WIDTH), 50.0),
            rect_height=self._to_float(self._settings.value(self._KEY_GRID_HEIGHT), 50.0),
            spacing_x=self._to_float(self._settings.value(self._KEY_GRID_SPACING_X), 10.0),
            spacing_y=self._to_float(self._settings.value(self._KEY_GRID_SPACING_Y), 10.0),
            angle_deg=self._to_float(self._settings.value(self._KEY_GRID_ANGLE), 0.0),
            origin_x=self._to_float(self._settings.value(self._KEY_GRID_ORIGIN_X), 0.0),
            origin_y=self._to_float(self._settings.value(self._KEY_GRID_ORIGIN_Y), 0.0),
        )

    def set_grid_parameters(self, params: GridParameters) -> None:
        self._settings.setValue(self._KEY_GRID_ROWS, int(params.rows))
        self._settings.setValue(self._KEY_GRID_COLUMNS, int(params.columns))
        self._settings.setValue(self._KEY_GRID_WIDTH, float(params.rect_width))
        self._settings.setValue(self._KEY_GRID_HEIGHT, float(params.rect_height))
        self._settings.setValue(self._KEY_GRID_SPACING_X, float(params.spacing_x))
        self._settings.setValue(self._KEY_GRID_SPACING_Y, float(params.spacing_y))
        self._settings.setValue(self._KEY_GRID_ANGLE, float(params.angle_deg))
        self._settings.setValue(self._KEY_GRID_ORIGIN_X, float(params.origin_x))
        self._settings.setValue(self._KEY_GRID_ORIGIN_Y, float(params.origin_y))
        self._settings.sync()
