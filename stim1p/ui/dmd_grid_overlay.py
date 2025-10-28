"""Temporary overlay helpers for DMD previews."""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt


class GridPreviewOverlay:
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
