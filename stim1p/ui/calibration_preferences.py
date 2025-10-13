"""Lightweight wrapper around :class:`~PySide6.QtCore.QSettings`.

Persisting calibration selections keeps the widget stateful between launches,
but the original implementation embedded the persistence logic inside the
already-large widget module.  This helper exposes a focused API for reading and
writing the values we care about without tying it to the widget directly.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings


class CalibrationPreferences:
    """Store calibration paths and defaults in the platform settings backend."""

    _ORG = "Stim1P"
    _APP = "DMDStim"
    _KEY_LAST_FILE = "calibration/last_file_path"
    _KEY_LAST_IMAGE = "calibration/last_image_path"
    _KEY_MIRRORS_X = "calibration/mirrors_x"
    _KEY_MIRRORS_Y = "calibration/mirrors_y"
    _KEY_PIXEL_SIZE = "calibration/pixel_size"

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

