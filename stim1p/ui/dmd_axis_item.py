"""Axis item helpers for DMD visualisations."""

from __future__ import annotations

from typing import Protocol, Sequence

import numpy as np
import pyqtgraph as pg


class AxisScaleProvider(Protocol):
    """Provide conversion factors for axis tick labels."""

    def axis_unit_scale_for_orientation(self, orientation: str) -> float | None:
        """Return micrometre-per-unit scale for the given axis orientation."""


class MicrometreAxisItem(pg.AxisItem):
    """Axis that renders tick labels in micrometres when calibration is available."""

    def __init__(self, orientation: str, scale_provider: AxisScaleProvider):
        super().__init__(orientation=orientation)
        self._scale_provider = scale_provider

    def tickStrings(
        self, values: Sequence[float], scale: float, spacing: float
    ) -> list[str]:
        if self.logMode:
            return super().tickStrings(values, scale, spacing)

        per_unit = self._scale_provider.axis_unit_scale_for_orientation(self.orientation)
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
