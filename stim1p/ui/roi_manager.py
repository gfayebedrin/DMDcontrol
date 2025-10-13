# src/ui/roi_manager.py
"""
Manager for ROIs (Regions of Interest) in a DMD stimulation application.
This module provides functionality to create, manage, and visualize ROIs
associated with tree items in a Qt application.
"""

from __future__ import annotations
from typing import Iterable

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QTreeWidgetItem
from PySide6.QtCore import QObject, Signal, QPointF


class _BaseShape:
    """Base wrapper around a pyqtgraph ROI bound to a tree item."""

    def __init__(self, item: QTreeWidgetItem, roi: pg.ROI, shape_type: str):
        self.item = item
        self.roi = roi
        self.shape_type = shape_type
        self.roi.sigClicked.connect(lambda *_: self.item.setSelected(True))

    def change_ref(self, center: QPointF, angle: float) -> None:
        raise NotImplementedError

    def get_points(self) -> np.ndarray:
        raise NotImplementedError

    def set_points(self, points: np.ndarray) -> None:
        raise NotImplementedError


class PolygonShape(_BaseShape):
    def __init__(self, points: np.ndarray, item: QTreeWidgetItem):
        roi = pg.PolyLineROI(points, closed=True)
        super().__init__(item, roi, "polygon")

    def change_ref(self, center: QPointF, angle: float) -> None:
        self.roi.setPos(center)
        self.roi.setAngle(angle)

    def get_points(self) -> np.ndarray:
        points: list[list[float]] = []
        parent = self.roi.parentItem()
        for handle_info in getattr(self.roi, "handles", []):
            if handle_info.get("type") != "f":
                continue
            handle_item = handle_info.get("item")
            if handle_item is None:
                continue
            local_pos = handle_item.pos()
            if parent is not None:
                mapped = self.roi.mapToParent(local_pos)
            else:
                # ROI currently detached from a view; fall back to local coords + translation.
                mapped = QPointF(float(local_pos.x()), float(local_pos.y()))
                roi_pos = self.roi.pos()
                mapped += QPointF(float(roi_pos.x()), float(roi_pos.y()))
            points.append([float(mapped.x()), float(mapped.y())])
        if not points:
            return np.zeros((0, 2), dtype=float)
        return np.asarray(points, dtype=float)

    def set_points(self, points: np.ndarray) -> None:
        from PySide6.QtCore import QPointF

        pts = [QPointF(float(x), float(y)) for x, y in np.asarray(points, dtype=float)]
        self.roi.setPoints(pts, closed=True)
        self.roi.setAngle(0.0)
        self.roi.setPos(0.0, 0.0)


class RectangleShape(_BaseShape):
    def __init__(self, points: np.ndarray, item: QTreeWidgetItem):
        points = np.asarray(points, dtype=float)
        min_x = float(np.min(points[:, 0]))
        max_x = float(np.max(points[:, 0]))
        min_y = float(np.min(points[:, 1]))
        max_y = float(np.max(points[:, 1]))
        width = max(max_x - min_x, 1e-6)
        height = max(max_y - min_y, 1e-6)
        roi = pg.RectROI(
            pos=(min_x, min_y),
            size=(width, height),
            rotatable=False,
            removable=False,
        )
        super().__init__(item, roi, "rectangle")
        self.roi.setAngle(0.0)

    def change_ref(self, center: QPointF, angle: float) -> None:
        self.roi.setPos(center.x(), center.y())
        self.roi.setAngle(0.0)

    def get_points(self) -> np.ndarray:
        rect = self.roi.parentBounds()
        if rect is None:
            return np.zeros((0, 2), dtype=float)
        x0 = float(rect.left())
        y0 = float(rect.top())
        x1 = float(rect.right())
        y1 = float(rect.bottom())
        return np.asarray([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=float)

    def set_points(self, points: np.ndarray) -> None:
        points = np.asarray(points, dtype=float)
        min_x = float(np.min(points[:, 0]))
        max_x = float(np.max(points[:, 0]))
        min_y = float(np.min(points[:, 1]))
        max_y = float(np.max(points[:, 1]))
        width = max(max_x - min_x, 1e-6)
        height = max(max_y - min_y, 1e-6)
        self.roi.setAngle(0.0)
        self.roi.setPos(min_x, min_y)
        self.roi.setSize((width, height))


class RoiManager(QObject):
    """Owns shape ROIs and their attachment to an ImageView."""

    visibilityChanged = Signal()
    shapeEdited = Signal(QTreeWidgetItem)

    def __init__(self, image_view: pg.GraphicsItem):
        super().__init__()
        self._image_view = image_view
        self._shapes: dict[QTreeWidgetItem, _BaseShape] = {}
        self._visible_rois: list[pg.ROI] = []

    # ---- Ownership / registration ----------------------------------------
    def register_polygon(self, item: QTreeWidgetItem, points: np.ndarray) -> PolygonShape:
        polygon = PolygonShape(points.astype("float64"), item)
        polygon.roi.sigRegionChangeFinished.connect(
            lambda *_: self.shapeEdited.emit(item)
        )
        self._image_view.addItem(polygon.roi)
        polygon.roi.setVisible(False)
        self._shapes[item] = polygon
        return polygon

    def register_rectangle(
        self, item: QTreeWidgetItem, points: np.ndarray
    ) -> RectangleShape:
        rectangle = RectangleShape(points.astype("float64"), item)
        rectangle.roi.sigRegionChangeFinished.connect(
            lambda *_: self.shapeEdited.emit(item)
        )
        self._image_view.addItem(rectangle.roi)
        rectangle.roi.setVisible(False)
        self._shapes[item] = rectangle
        return rectangle

    def unregister_item(self, item: QTreeWidgetItem) -> None:
        shape = self._shapes.pop(item, None)
        if shape is None:
            return
        if shape.roi in self._visible_rois:
            self._visible_rois.remove(shape.roi)
        shape.roi.setVisible(False)
        self._image_view.removeItem(shape.roi)

    def clear_all(self) -> None:
        for roi in self._visible_rois:
            roi.setVisible(False)
        self._visible_rois.clear()
        for shape in self._shapes.values():
            self._image_view.removeItem(shape.roi)
        self._shapes.clear()
        self.visibilityChanged.emit()

    # ---- View control -----------------------------------------------------
    def show_for_item(self, item: QTreeWidgetItem) -> None:
        self.clear_visible_only()
        shape = self._shapes.get(item)
        if shape is not None:
            self._add_visible(shape.roi)
        else:
            for i in range(item.childCount()):
                child = item.child(i)
                child_shape = self._shapes.get(child)
                if child_shape is not None:
                    self._add_visible(child_shape.roi)
        self.visibilityChanged.emit()

    def clear_visible_only(self) -> None:
        for roi in self._visible_rois:
            roi.setVisible(False)
        self._visible_rois.clear()

    def _add_visible(self, roi: pg.ROI) -> None:
        if roi.scene() is None:
            self._image_view.addItem(roi)
        if roi not in self._visible_rois:
            self._visible_rois.append(roi)
        roi.setVisible(True)

    # ---- Bulk ops ---------------------------------------------------------
    def remove_items(self, items: Iterable[QTreeWidgetItem]) -> None:
        for it in items:
            for i in range(it.childCount()):
                self.unregister_item(it.child(i))
            self.unregister_item(it)
        self.visibilityChanged.emit()

    # ---- Introspection / export ------------------------------------------
    def have_item(self, item: QTreeWidgetItem) -> bool:
        return item in self._shapes

    def get_shape(self, item: QTreeWidgetItem) -> _BaseShape | None:
        return self._shapes.get(item)

    def get_shape_type(self, item: QTreeWidgetItem) -> str | None:
        shape = self._shapes.get(item)
        return shape.shape_type if shape is not None else None

    def export_shape_points(self) -> dict[QTreeWidgetItem, tuple[np.ndarray, str]]:
        return {
            item: (shape.get_points(), shape.shape_type)
            for item, shape in self._shapes.items()
        }

    def update_shape(
        self, item: QTreeWidgetItem, shape_type: str, points: np.ndarray
    ) -> None:
        shape_type = str(shape_type).lower()
        points = np.asarray(points, dtype=float)
        was_visible = False
        existing = self._shapes.get(item)
        if existing is not None:
            was_visible = existing.roi in self._visible_rois
            self.unregister_item(item)
        if shape_type == "rectangle":
            new_shape = self.register_rectangle(item, points)
        else:
            new_shape = self.register_polygon(item, points)
        if was_visible:
            self._add_visible(new_shape.roi)
