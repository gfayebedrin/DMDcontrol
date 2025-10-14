# src/ui/roi_manager.py
"""
Manager for ROIs (Regions of Interest) in a DMD stimulation application.
This module provides functionality to create, manage, and visualize ROIs
associated with tree items in a Qt application.
"""

from __future__ import annotations
from typing import Iterable

import math

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
    _MIN_EXTENT = 1e-6

    def __init__(self, points: np.ndarray, item: QTreeWidgetItem):
        roi = pg.RectROI(
            pos=(0.0, 0.0),
            size=(1.0, 1.0),
            rotatable=True,
            removable=False,
        )
        super().__init__(item, roi, "rectangle")
        self.set_points(points)

    def change_ref(self, center: QPointF, angle: float) -> None:
        # Maintain current rotation but translate so the rectangle follows the
        # new reference point.
        state = dict(self.roi.state)
        width = float(state.get("size", (0.0, 0.0))[0])
        height = float(state.get("size", (0.0, 0.0))[1])
        angle_deg = float(state.get("angle", 0.0))
        center_vec = np.array([float(center.x()), float(center.y())], dtype=float)
        half_size = np.array([width / 2.0, height / 2.0], dtype=float)
        angle_rad = math.radians(angle_deg)
        rot = np.array(
            [[math.cos(angle_rad), -math.sin(angle_rad)],
             [math.sin(angle_rad), math.cos(angle_rad)]],
            dtype=float,
        )
        pos = center_vec - rot @ half_size
        self.roi.setAngle(angle_deg)
        self.roi.setPos(float(pos[0]), float(pos[1]))

    def get_points(self) -> np.ndarray:
        state = dict(self.roi.state)
        pos = np.asarray(state.get("pos", (0.0, 0.0)), dtype=float)
        width, height = state.get("size", (0.0, 0.0))
        width = float(width)
        height = float(height)
        angle_deg = float(state.get("angle", 0.0))
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        u = np.array([cos_a, sin_a], dtype=float)
        v = np.array([-sin_a, cos_a], dtype=float)
        p0 = pos
        p1 = pos + width * u
        p2 = p1 + height * v
        p3 = pos + height * v
        return np.asarray([p0, p1, p2, p3], dtype=float)

    def set_points(self, points: np.ndarray) -> None:
        pts = np.asarray(points, dtype=float)
        if pts.shape[0] < 4:
            raise ValueError("Rectangle points must contain at least four vertices.")
        sums = np.sum(pts[:, :2], axis=1)
        start_idx = int(np.argmin(sums))
        origin = pts[start_idx]
        remaining = np.delete(pts, start_idx, axis=0)
        if remaining.shape[0] < 3:
            raise ValueError("Rectangle definition requires four distinct vertices.")
        vectors = remaining - origin
        distances = np.linalg.norm(vectors, axis=1)
        order = np.argsort(distances)
        adj_a = remaining[order[0]]
        adj_b = remaining[order[1]]
        diag = remaining[order[2]]
        vec_a = adj_a - origin
        vec_b = adj_b - origin
        cross = vec_a[0] * vec_b[1] - vec_a[1] * vec_b[0]
        if cross < 0:
            adj_a, adj_b = adj_b, adj_a
            vec_a, vec_b = vec_b, vec_a
        ordered = np.vstack((origin, adj_a, diag, adj_b))
        width_vec = ordered[1] - ordered[0]
        height_vec = ordered[3] - ordered[0]
        width = float(np.linalg.norm(width_vec))
        if width < self._MIN_EXTENT:
            width = self._MIN_EXTENT
            width_vec = np.array([width, 0.0], dtype=float)
        u = width_vec / width
        v = np.array([-u[1], u[0]], dtype=float)
        height = float(np.dot(height_vec, v))
        if abs(height) < self._MIN_EXTENT:
            height = self._MIN_EXTENT
        if height < 0:
            height = -height
            v = -v
        angle_deg = math.degrees(math.atan2(u[1], u[0]))
        center = ordered[0] + 0.5 * width * u + 0.5 * height * v
        pos = center - 0.5 * width * u - 0.5 * height * v
        self.roi.setAngle(0.0)
        self.roi.setSize((width, height))
        self.roi.setPos(float(pos[0]), float(pos[1]))
        self.roi.setAngle(angle_deg)


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
        self.shapeEdited.emit(item)
