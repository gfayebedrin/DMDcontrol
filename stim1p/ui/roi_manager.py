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


class PolygonShape(_BaseShape):
    def __init__(self, points: np.ndarray, item: QTreeWidgetItem):
        roi = pg.PolyLineROI(points, closed=True)
        super().__init__(item, roi, "polygon")

    def change_ref(self, center: QPointF, angle: float) -> None:
        self.roi.setPos(center)
        self.roi.setAngle(angle)

    def get_points(self) -> np.ndarray:
        pts = []
        for _, pos in self.roi.getSceneHandlePositions():
            pts.append([pos.x(), pos.y()])
        return np.asarray(pts, dtype=float)


class RectangleShape(_BaseShape):
    def __init__(self, points: np.ndarray, item: QTreeWidgetItem):
        ordered = self._order_points(np.asarray(points, dtype=float))
        width_vector = ordered[1] - ordered[0]
        height_vector = ordered[2] - ordered[1]
        width = float(np.linalg.norm(width_vector))
        height = float(np.linalg.norm(height_vector))
        if width == 0 or height == 0:
            width = height = 1.0
        center = ordered.mean(axis=0)
        roi = pg.RectROI(
            pos=(center[0] - width / 2.0, center[1] - height / 2.0),
            size=(width, height),
            rotatable=True,
            removable=False,
        )
        super().__init__(item, roi, "rectangle")
        angle_deg = float(np.degrees(np.arctan2(width_vector[1], width_vector[0])))
        self.roi.setAngle(angle_deg)

    @staticmethod
    def _order_points(points: np.ndarray) -> np.ndarray:
        center = points.mean(axis=0)
        angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
        order = np.argsort(angles)
        return points[order]

    def _size(self) -> tuple[float, float]:
        size = self.roi.size()
        try:
            width = float(size.x())
            height = float(size.y())
        except AttributeError:
            width, height = size
        return width, height

    def _center_point(self) -> QPointF:
        pts = self.get_points()
        if pts.size == 0:
            return QPointF(0.0, 0.0)
        center = pts.mean(axis=0)
        return QPointF(float(center[0]), float(center[1]))

    def change_ref(self, center: QPointF, angle: float) -> None:
        current_center = self._center_point()
        delta = QPointF(center.x() - current_center.x(), center.y() - current_center.y())
        self.roi.setPos(self.roi.pos() + delta)
        self.roi.setAngle(angle)

    def get_points(self) -> np.ndarray:
        width, height = self._size()
        local = [
            QPointF(0.0, 0.0),
            QPointF(width, 0.0),
            QPointF(width, height),
            QPointF(0.0, height),
        ]
        pts = []
        for pt in local:
            mapped = self.roi.mapToParent(pt)
            pts.append([mapped.x(), mapped.y()])
        return np.asarray(pts, dtype=float)


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
        self._shapes[item] = polygon
        return polygon

    def register_rectangle(
        self, item: QTreeWidgetItem, points: np.ndarray
    ) -> RectangleShape:
        rectangle = RectangleShape(points.astype("float64"), item)
        rectangle.roi.sigRegionChangeFinished.connect(
            lambda *_: self.shapeEdited.emit(item)
        )
        self._shapes[item] = rectangle
        return rectangle

    def unregister_item(self, item: QTreeWidgetItem) -> None:
        shape = self._shapes.pop(item, None)
        if shape is None:
            return
        if shape.roi in self._visible_rois:
            self._image_view.removeItem(shape.roi)
            self._visible_rois.remove(shape.roi)

    def clear_all(self) -> None:
        for roi in self._visible_rois:
            self._image_view.removeItem(roi)
        self._visible_rois.clear()
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
            self._image_view.removeItem(roi)
        self._visible_rois.clear()

    def _add_visible(self, roi: pg.ROI) -> None:
        self._image_view.addItem(roi)
        self._visible_rois.append(roi)

    # ---- Bulk ops ---------------------------------------------------------
    def change_reference_all(self, center: QPointF, angle: float) -> None:
        for shape in self._shapes.values():
            shape.change_ref(center, angle)

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
