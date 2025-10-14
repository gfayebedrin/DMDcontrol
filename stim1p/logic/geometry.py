"""Geometry utilities for handling coordinate transformations and polygon masks."""

from dataclasses import dataclass
import numpy as np
from skimage.draw import polygon2mask
from .calibration import DMDCalibration


@dataclass(frozen=True)
class AxisDefinition:
    """Placement of the user-defined object axis in camera space."""

    origin_camera: tuple[float, float]
    angle_rad: float


@dataclass(frozen=True)
class PatternCoordinates:
    """
    Coordinate systems for positionning patterns in the image.
    Allows translating coordinates between image coordinates and local coordinates.
    Image coordinates are in the range [0, 1]. Origin is at the top-left corner of the image.
    The image coordinate system is indirect.
    Local coordinates are expressed in µm and are relative to the origin and orientation of the local coordinate system.
    The local coordinate system is direct.

    Attributes:
        origin (tuple[float, float]): origin of the local coordinate system in image coordinates.
        orientation (float, optional): orientation of the local coordinate system in radians.
        field_size (float, optional): size of the field in µm.
    """

    origin: tuple[float, float] = (0.0, 0.0)
    orientation: float = 0.0
    field_size: float = 594.0

    @property
    def local_to_image_matrix(self) -> np.ndarray:
        """
        Transformation matrix from local coordinates to image coordinates.
        The matrix is a 3x3 affine transformation matrix.
        """
        d = self.field_size
        cos_theta = np.cos(self.orientation)
        sin_theta = np.sin(self.orientation)
        return np.array(
            [
                [cos_theta / d, sin_theta / d, self.origin[0]],
                [sin_theta / d, -cos_theta / d, self.origin[1]],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

    @property
    def image_to_local_matrix(self) -> np.ndarray:
        """
        Transformation matrix from image coordinates to local coordinates.
        The matrix is a 3x3 affine transformation matrix.
        """
        return np.linalg.inv(self.local_to_image_matrix)

    def local_to_image(self, coords: np.ndarray) -> np.ndarray:
        """
        Convert local coordinates to image coordinates.

        Parameters:
            coords (ndarray): Local coordinates in µm. (2,...) array_like.

        Returns:
            coords (ndarray): Image coordinates in [0, 1] range. (2,...) array_like.
        """
        affine_coords = np.stack((*coords, np.ones(coords.shape[1:])), axis=0)
        transformed_coords = self.local_to_image_matrix @ affine_coords
        return transformed_coords[:2]

    def image_to_local(self, coords: np.ndarray) -> np.ndarray:
        """
        Convert image coordinates to local coordinates.

        Parameters:
            coords (ndarray): Image coordinates in [0, 1] range. (2,...) array_like.

        Returns:
            coords (ndarray): Local coordinates in µm. (2,...) array_like.
        """
        affine_coords = np.stack((*coords, np.ones(coords.shape[1:])), axis=0)
        transformed_coords = self.image_to_local_matrix @ affine_coords
        return transformed_coords[:2]


def _camera_pixel_to_micrometre_scale(calibration: DMDCalibration) -> np.ndarray:
    """Return the micrometre length of one camera pixel along each axis."""

    return np.array(
        [
            calibration.micrometers_per_mirror[0]
            / calibration.camera_pixels_per_mirror[0],
            calibration.micrometers_per_mirror[1]
            / calibration.camera_pixels_per_mirror[1],
        ],
        dtype=np.float64,
    )


def axis_definition_components(
    axis: AxisDefinition, calibration: DMDCalibration
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return origin, per-axis scales, and unit vectors in micrometres."""

    origin_camera = np.asarray(axis.origin_camera, dtype=np.float64)
    if origin_camera.shape != (2,):
        origin_camera = origin_camera.reshape(2)
    origin_um = calibration.camera_to_micrometre(origin_camera.reshape(2, 1)).T[0]

    cos_a = float(np.cos(axis.angle_rad))
    sin_a = float(np.sin(axis.angle_rad))
    rotation = np.array(
        [[cos_a, -sin_a], [sin_a, cos_a]],
        dtype=np.float64,
    )

    per_pixel_um = _camera_pixel_to_micrometre_scale(calibration)
    basis_um = per_pixel_um.reshape(2, 1) * rotation

    scales = np.linalg.norm(basis_um, axis=0)
    if (not np.all(np.isfinite(scales))) or np.any(scales <= 0.0):
        raise ValueError("Invalid axis scale computed from calibration.")

    unit_vectors = basis_um / scales
    return origin_um, scales, unit_vectors


def axis_micrometre_scale(axis: AxisDefinition, calibration: DMDCalibration) -> np.ndarray:
    """Return the micrometre-per-unit scale along each axis of ``axis``."""

    _, scales, _ = axis_definition_components(axis, calibration)
    return scales


def axis_pixels_to_axis_micrometre(
    points: np.ndarray, axis: AxisDefinition, calibration: DMDCalibration
) -> np.ndarray:
    """Convert axis-frame pixel coordinates to micrometres along the same axes."""

    scales = axis_micrometre_scale(axis, calibration)
    arr = np.asarray(points, dtype=float)
    was_1d = arr.ndim == 1
    pts = np.atleast_2d(arr)
    mic = pts * scales.reshape(1, 2)
    return mic[0] if was_1d else mic


def axis_micrometre_to_axis_pixels(
    points_um: np.ndarray, axis: AxisDefinition, calibration: DMDCalibration
) -> np.ndarray:
    """Inverse of :func:`axis_pixels_to_axis_micrometre`."""

    scales = axis_micrometre_scale(axis, calibration)
    arr = np.asarray(points_um, dtype=float)
    was_1d = arr.ndim == 1
    pts = np.atleast_2d(arr)
    axis_pts = pts / scales.reshape(1, 2)
    return axis_pts[0] if was_1d else axis_pts


def axis_micrometre_to_global(
    points_um: np.ndarray, axis: AxisDefinition, calibration: DMDCalibration
) -> np.ndarray:
    """Map axis-frame micrometre coordinates into global micrometre space."""

    origin_um, _, unit_vectors = axis_definition_components(axis, calibration)
    arr = np.asarray(points_um, dtype=float)
    was_1d = arr.ndim == 1
    pts = np.atleast_2d(arr)
    x = pts[:, 0:1]
    y = pts[:, 1:2]
    global_pts = (
        origin_um.reshape(1, 2)
        + x * unit_vectors[:, 0].reshape(1, 2)
        + y * unit_vectors[:, 1].reshape(1, 2)
    )
    return global_pts[0] if was_1d else global_pts


def axis_polygons_to_global(
    polygons: list[np.ndarray], axis: AxisDefinition, calibration: DMDCalibration
) -> list[np.ndarray]:
    """Convert a list of axis-frame polygons into global micrometre space."""

    return [axis_micrometre_to_global(poly, axis, calibration) for poly in polygons]


def axis_polygons_to_mask(
    polygons: list[np.ndarray], axis: AxisDefinition, calibration: DMDCalibration
):
    """Render axis-frame polygons into a DMD mask."""

    return polygons_to_mask(axis_polygons_to_global(polygons, axis, calibration), calibration)


def polygons_to_mask(polygons: list[np.ndarray], calibration: DMDCalibration):
    """
    Convert a list of polygons to a boolean mask.

    Parameters:
        polygons (list[ndarray]): list of polygons, where each polygon is a (N, 2)
            numpy array of vertices expressed in micrometres.
        calibration (DMDCalibration): calibration parameters for converting
            coordinates.

    Returns:
        mask (ndarray): Boolean 2D mask with `True` inside the polygons and `False` outside.
    """
    mask = np.zeros(calibration.dmd_shape, dtype=bool)

    width, height = calibration.dmd_shape

    for polygon in polygons:
        polygon_dmd = calibration.micrometre_to_dmd(polygon.T).T
        if calibration.invert_x:
            polygon_dmd[:, 0] = (width - 1) - polygon_dmd[:, 0]
        if calibration.invert_y:
            polygon_dmd[:, 1] = (height - 1) - polygon_dmd[:, 1]
        mask |= polygon2mask(calibration.dmd_shape, polygon_dmd)

    return mask
