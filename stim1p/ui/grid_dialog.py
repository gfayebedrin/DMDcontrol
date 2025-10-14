"""Dialog for configuring a rectangular grid of ROI patterns."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QWidget,
)


@dataclass(slots=True)
class GridParameters:
    """Container describing a grid of identical rectangular ROIs."""

    rows: int = 2
    columns: int = 2
    rect_width: float = 50.0
    rect_height: float = 50.0
    spacing_x: float = 10.0
    spacing_y: float = 10.0
    angle_deg: float = 0.0
    origin_x: float = 0.0
    origin_y: float = 0.0

    def is_valid(self) -> bool:
        return (
            self.rows > 0
            and self.columns > 0
            and self.rect_width > 0.0
            and self.rect_height > 0.0
        )

    def rectangle_points(self) -> list[np.ndarray]:
        """Return rectangle corner arrays in axis coordinates."""

        if not self.is_valid():
            return []
        rows = int(self.rows)
        cols = int(self.columns)
        width = float(self.rect_width)
        height = float(self.rect_height)
        spacing_x = float(self.spacing_x)
        spacing_y = float(self.spacing_y)
        angle_rad = math.radians(float(self.angle_deg))
        origin = np.array([float(self.origin_x), float(self.origin_y)], dtype=float)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        rot = np.array([[cos_a, -sin_a], [sin_a, cos_a]], dtype=float)
        step_x = rot @ np.array([width + spacing_x, 0.0])
        step_y = rot @ np.array([0.0, height + spacing_y])
        half_x = rot @ np.array([0.5 * width, 0.0])
        half_y = rot @ np.array([0.0, 0.5 * height])
        rectangles: list[np.ndarray] = []
        for row in range(rows):
            for col in range(cols):
                centre = origin + col * step_x + row * step_y
                corners = np.array(
                    [
                        centre - half_x - half_y,
                        centre + half_x - half_y,
                        centre + half_x + half_y,
                        centre - half_x + half_y,
                    ],
                    dtype=float,
                )
                rectangles.append(corners)
        return rectangles


class GridDialog(QDialog):
    """Collect the information necessary to generate a grid of patterns."""

    parametersChanged = Signal(GridParameters)

    def __init__(self, parent: QWidget | None = None, *, defaults: GridParameters | None = None):
        super().__init__(parent)
        self.setWindowTitle("Create grid")
        self._block_updates = False
        layout = QFormLayout(self)

        self._rows = QSpinBox(self)
        self._rows.setRange(1, 512)
        self._rows.setValue(2)
        layout.addRow("Rows", self._rows)

        self._columns = QSpinBox(self)
        self._columns.setRange(1, 512)
        self._columns.setValue(2)
        layout.addRow("Columns", self._columns)

        self._rect_width = self._build_distance_spin()
        layout.addRow("Rectangle width", self._rect_width)

        self._rect_height = self._build_distance_spin()
        layout.addRow("Rectangle height", self._rect_height)

        self._spacing_x = self._build_distance_spin(minimum=0.0)
        layout.addRow("Horizontal spacing", self._spacing_x)

        self._spacing_y = self._build_distance_spin(minimum=0.0)
        layout.addRow("Vertical spacing", self._spacing_y)

        self._angle = QDoubleSpinBox(self)
        self._angle.setDecimals(2)
        self._angle.setRange(-180.0, 180.0)
        self._angle.setSuffix(" °")
        layout.addRow("Angle", self._angle)

        origin_container = QWidget(self)
        origin_layout = QHBoxLayout(origin_container)
        origin_layout.setContentsMargins(0, 0, 0, 0)
        origin_layout.setSpacing(6)
        origin_layout.addWidget(QLabel("X", origin_container))
        self._origin_x = self._build_distance_spin(minimum=-100_000.0, maximum=100_000.0)
        origin_layout.addWidget(self._origin_x)
        origin_layout.addWidget(QLabel("Y", origin_container))
        self._origin_y = self._build_distance_spin(minimum=-100_000.0, maximum=100_000.0)
        origin_layout.addWidget(self._origin_y)
        layout.addRow("Origin", origin_container)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        layout.addRow(self._buttons)

        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)

        for widget in self._iter_controls():
            widget.valueChanged.connect(self._on_parameters_changed)

        initial = defaults if defaults is not None else GridParameters()
        self.set_parameters(initial)

    def _build_distance_spin(
        self,
        *,
        minimum: float = 1.0,
        maximum: float = 10_000.0,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(self)
        spin.setDecimals(3)
        spin.setMinimum(minimum)
        spin.setMaximum(maximum)
        spin.setSingleStep(1.0)
        return spin

    def _iter_controls(self) -> Iterable[QDoubleSpinBox | QSpinBox]:
        yield self._rows
        yield self._columns
        yield self._rect_width
        yield self._rect_height
        yield self._spacing_x
        yield self._spacing_y
        yield self._angle
        yield self._origin_x
        yield self._origin_y

    def parameters(self) -> GridParameters:
        return GridParameters(
            rows=self._rows.value(),
            columns=self._columns.value(),
            rect_width=self._rect_width.value(),
            rect_height=self._rect_height.value(),
            spacing_x=self._spacing_x.value(),
            spacing_y=self._spacing_y.value(),
            angle_deg=self._angle.value(),
            origin_x=self._origin_x.value(),
            origin_y=self._origin_y.value(),
        )

    def set_parameters(self, params: GridParameters) -> None:
        self._block_updates = True
        try:
            self._rows.setValue(max(1, int(round(params.rows))))
            self._columns.setValue(max(1, int(round(params.columns))))
            self._rect_width.setValue(max(self._rect_width.minimum(), float(params.rect_width)))
            self._rect_height.setValue(max(self._rect_height.minimum(), float(params.rect_height)))
            self._spacing_x.setValue(max(self._spacing_x.minimum(), float(params.spacing_x)))
            self._spacing_y.setValue(max(self._spacing_y.minimum(), float(params.spacing_y)))
            self._angle.setValue(float(params.angle_deg))
            self._origin_x.setValue(float(params.origin_x))
            self._origin_y.setValue(float(params.origin_y))
        finally:
            self._block_updates = False
        self._on_parameters_changed()

    def _on_parameters_changed(self) -> None:
        if self._block_updates:
            return
        params = self.parameters()
        ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(params.is_valid())
        self.parametersChanged.emit(params)

