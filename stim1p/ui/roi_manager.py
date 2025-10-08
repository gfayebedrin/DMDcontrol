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

class Polygon:
    """Adapter around a pyqtgraph PolyLineROI tied to a tree item."""
    def __init__(self, points: np.ndarray, item: QTreeWidgetItem):
        self.item = item
        self.roi = pg.PolyLineROI(points, closed=True)
        # clicking the ROI selects the corresponding tree item
        self.roi.sigClicked.connect(lambda *_: self.item.setSelected(True))

    def change_ref(self, center: QPointF, angle: float) -> None:
        self.roi.setPos(center)
        self.roi.setAngle(angle)

    def get_points(self) -> np.ndarray:
        pts = []
        for _, pos in self.roi.getSceneHandlePositions():
            pts.append([pos.x(), pos.y()])
        return np.asarray(pts, dtype=float)

class RoiManager(QObject):
    """Owns Polygon ROIs and their attachment to an ImageView."""
    # Emits when visible ROIs changed (e.g., selection in tree)
    visibilityChanged = Signal()
    polygonEdited = Signal(QTreeWidgetItem)

    def __init__(self, image_view: pg.GraphicsItem):
        super().__init__()
        self._image_view = image_view
        self._polygons: dict[QTreeWidgetItem, Polygon] = {}
        self._visible_rois: list[pg.ROI] = []

    # ---- Ownership / registration ----------------------------------------
    def register_polygon(self, item: QTreeWidgetItem, points: np.ndarray) -> Polygon:
        """Create and track a polygon for a tree item (not auto-shown)."""
        poly = Polygon(points.astype("float64"), item)
        poly.roi.sigRegionChangeFinished.connect(lambda *_: self.polygonEdited.emit(item))
        self._polygons[item] = poly
        return poly

    def unregister_item(self, item: QTreeWidgetItem) -> None:
        """Remove polygon (and from view if visible)."""
        poly = self._polygons.pop(item, None)
        if poly is None:
            return
        if poly.roi in self._visible_rois:
            self._image_view.removeItem(poly.roi)
            self._visible_rois.remove(poly.roi)
        # let Qt/pyqtgraph GC the ROI; no explicit delete required

    def clear_all(self) -> None:
        """Remove all ROIs from view and forget them."""
        for roi in self._visible_rois:
            self._image_view.removeItem(roi)
        self._visible_rois.clear()
        self._polygons.clear()
        self.visibilityChanged.emit()

    # ---- View control -----------------------------------------------------
    def show_for_item(self, item: QTreeWidgetItem) -> None:
        """
        Show the ROI(s) corresponding to a selected tree item:
        - if item is a leaf polygon: show that ROI
        - if item is a pattern (has children): show all its children ROIs
        """
        self.clear_visible_only()
        if item in self._polygons:
            self._add_visible(self._polygons[item].roi)
        else:
            for i in range(item.childCount()):
                child = item.child(i)
                poly = self._polygons.get(child)
                if poly:
                    self._add_visible(poly.roi)
        self.visibilityChanged.emit()

    def clear_visible_only(self) -> None:
        """Hide all currently shown ROIs but keep them registered."""
        for roi in self._visible_rois:
            self._image_view.removeItem(roi)
        self._visible_rois.clear()

    def _add_visible(self, roi: pg.ROI) -> None:
        self._image_view.addItem(roi)
        self._visible_rois.append(roi)

    # ---- Bulk ops ---------------------------------------------------------
    def change_reference_all(self, center: QPointF, angle: float) -> None:
        """Rebase all polygons to a new reference (crosshair pose)."""
        for poly in self._polygons.values():
            poly.change_ref(center, angle)

    def remove_items(self, items: Iterable[QTreeWidgetItem]) -> None:
        """Unregister multiple items (pattern or polygon leaves)."""
        for it in items:
            # If it's a pattern (has children), unregister all children
            for i in range(it.childCount()):
                self.unregister_item(it.child(i))
            # A leaf polygon may be passed directly
            self.unregister_item(it)
        self.visibilityChanged.emit()

    # ---- Introspection / export ------------------------------------------
    def have_item(self, item: QTreeWidgetItem) -> bool:
        return item in self._polygons

    def get_polygon(self, item: QTreeWidgetItem) -> Polygon | None:
        return self._polygons.get(item)

    def export_points(self) -> dict[QTreeWidgetItem, np.ndarray]:
        """Return a mapping item -> Nx2 array for serialization."""
        return {item: poly.get_points() for item, poly in self._polygons.items()}
