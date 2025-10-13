"""Reusable interactive tools for drawing shapes within the stimulus view.

The stimulation widget previously bundled several small QObject helpers for
capturing rectangles, axes, and free-form polygons directly from the view box
used to render the camera feed.  Moving those helpers into this module keeps
``dmd_stim_widget.py`` focused on the main widget implementation while still
exposing the tools to other UIs that may need identical interactions.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QEvent, QEventLoop, QObject, QPointF, QRectF, Qt
from PySide6.QtWidgets import QGraphicsRectItem, QWidget


class InteractiveRectangleCapture(QObject):
    """Let the user drag out a rectangle within the provided view box."""

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
        """Block until the user finishes drawing and return the rectangle."""

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


class AxisCapture(QObject):
    """Interactive helper to capture an axis vector with live preview."""

    def __init__(self, view_box: pg.ViewBox, parent: QWidget | None = None):
        super().__init__(parent)
        self._view_box = view_box
        self._scene = view_box.scene()
        self._loop: QEventLoop | None = None
        self._origin_view: QPointF | None = None
        self._current_view: QPointF | None = None
        self._line_item: pg.PlotDataItem | None = None
        self._arrow_item: pg.ArrowItem | None = None
        self._origin_item: pg.ScatterPlotItem | None = None
        self._original_mouse_enabled: tuple[bool, bool] = (True, True)

    def exec(self) -> tuple[QPointF, QPointF] | None:
        """Block until an axis has been defined and return the endpoints."""

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
        if self._origin_view is not None and self._current_view is not None:
            result = (QPointF(self._origin_view), QPointF(self._current_view))
        else:
            result = None
        self._origin_view = None
        self._current_view = None
        self._loop = None
        return result

    def eventFilter(self, _obj, event):  # noqa: D401
        if self._loop is None:
            return False
        etype = event.type()
        if etype == QEvent.GraphicsSceneMousePress:
            if not self._view_box.sceneBoundingRect().contains(event.scenePos()):
                return False
            if event.button() == Qt.MouseButton.LeftButton:
                self._origin_view = self._view_box.mapSceneToView(event.scenePos())
                self._current_view = QPointF(self._origin_view)
                self._ensure_preview_items()
                self._update_preview(self._current_view)
                event.accept()
                return True
            if event.button() == Qt.MouseButton.RightButton:
                self._finish(cancel=True)
                event.accept()
                return True
        elif etype == QEvent.GraphicsSceneMouseMove:
            if self._origin_view is None:
                return False
            current = self._view_box.mapSceneToView(event.scenePos())
            self._current_view = current
            self._update_preview(current)
            event.accept()
            return True
        elif etype == QEvent.GraphicsSceneMouseRelease:
            if (
                self._origin_view is not None
                and event.button() == Qt.MouseButton.LeftButton
            ):
                current = self._view_box.mapSceneToView(event.scenePos())
                self._current_view = current
                self._update_preview(current)
                self._finish(cancel=False)
                event.accept()
                return True
        elif etype == QEvent.GraphicsSceneMouseDoubleClick:
            if (
                self._origin_view is not None
                and event.button() == Qt.MouseButton.LeftButton
            ):
                current = self._view_box.mapSceneToView(event.scenePos())
                self._current_view = current
                self._update_preview(current)
                self._finish(cancel=False)
                event.accept()
                return True
        elif etype == QEvent.KeyPress and event.key() == Qt.Key.Key_Escape:
            self._finish(cancel=True)
            event.accept()
            return True
        return False

    def _ensure_preview_items(self) -> None:
        if self._line_item is None:
            self._line_item = pg.PlotDataItem(
                pen=pg.mkPen(color="yellow", width=2),
                name="axis_preview_line",
            )
            self._line_item.setZValue(9_000)
            self._view_box.addItem(self._line_item)
        if self._arrow_item is None:
            self._arrow_item = pg.ArrowItem(
                angle=0,
                headLen=15,
                pen=pg.mkPen("yellow"),
                brush=pg.mkBrush("yellow"),
            )
            self._arrow_item.setZValue(9_001)
            self._view_box.addItem(self._arrow_item)
        if self._origin_item is None:
            self._origin_item = pg.ScatterPlotItem(
                [0.0],
                [0.0],
                size=8,
                brush=pg.mkBrush("yellow"),
                pen=pg.mkPen("yellow"),
            )
            self._origin_item.setZValue(9_001)
            self._view_box.addItem(self._origin_item)

    def _update_preview(self, current: QPointF) -> None:
        if self._origin_view is None:
            return
        self._ensure_preview_items()
        ox, oy = self._origin_view.x(), self._origin_view.y()
        cx, cy = current.x(), current.y()
        self._line_item.setData([ox, cx], [oy, cy])
        if self._arrow_item is not None:
            angle_deg = float(np.degrees(np.arctan2(cy - oy, cx - ox)))
            self._arrow_item.setPos(cx, cy)
            self._arrow_item.setStyle(angle=angle_deg)
        if self._origin_item is not None:
            self._origin_item.setData([ox], [oy])

    def _finish(self, cancel: bool) -> None:
        if cancel or self._origin_view is None or self._current_view is None:
            self._origin_view = None
            self._current_view = None
        if self._loop is not None and self._loop.isRunning():
            self._loop.quit()

    def _cleanup_preview(self) -> None:
        if self._line_item is not None:
            self._view_box.removeItem(self._line_item)
            self._line_item = None
        if self._arrow_item is not None:
            self._view_box.removeItem(self._arrow_item)
            self._arrow_item = None
        if self._origin_item is not None:
            self._view_box.removeItem(self._origin_item)
            self._origin_item = None


class PolygonDrawingCapture(QObject):
    """Capture a polygon drawn via successive clicks within the view box."""

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
        """Return the polygon vertices when the user completes the drawing."""

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

