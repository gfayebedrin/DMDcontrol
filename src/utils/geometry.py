"""
Geometry utilities for handling coordinate transformations and polygon masks.
"""

from dataclasses import dataclass
import numpy as np
from skimage.draw import polygon2mask
from .calibration import DMDCalibration


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
    - origin: tuple[float, float], origin of the local coordinate system in image coordinates.
    - orientation: float, orientation of the local coordinate system in radians.
    - field_size: float, size of the field in µm.
    """

    origin: tuple[float, float] = (0.0, 0.0)
    orientation: float = 0.0
    field_size: float = 594.0

    @property
    def local_to_image_matrix(self) -> np.ndarray:
        """
        Get the transformation matrix from local coordinates to image coordinates.
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
        Get the transformation matrix from image coordinates to local coordinates.
        The matrix is a 3x3 affine transformation matrix.
        """
        return np.linalg.inv(self.local_to_image_matrix)

    def local_to_image(self, coords: np.ndarray) -> np.ndarray:
        """
        Convert local coordinates to image coordinates.

        Parameters:
        - coords: (2,...) array_like, local coordinates in µm.

        Returns:
        - (2,...) array_like, image coordinates in [0, 1] range.
        """
        affine_coords = np.stack((*coords, np.ones(coords.shape[1:])), axis=0)
        transformed_coords = self.local_to_image_matrix @ affine_coords
        return transformed_coords[:2]

    def image_to_local(self, coords: np.ndarray) -> np.ndarray:
        """
        Convert image coordinates to local coordinates.

        Parameters:
        - coords: (2,...) array_like, image coordinates in [0, 1] range.

        Returns:
        - (2,...) array_like, local coordinates in µm.
        """
        affine_coords = np.stack((*coords, np.ones(coords.shape[1:])), axis=0)
        transformed_coords = self.image_to_local_matrix @ affine_coords
        return transformed_coords[:2]


def polygons_to_mask(polygons, calibration: DMDCalibration):
    """
    Convert a list of polygons to a binary mask.

    Parameters:
    - polygons: list of polygons, where each polygon is a (N, 2) numpy array of vertices in image coordinates.
    - calibration: DMDCalibration, calibration parameters for converting coordinates.

    Returns:
    - mask: 2D numpy array, binary mask with `True` inside the polygons and `False` outside.
    """
    mask = np.zeros(calibration.dmd_shape, dtype=bool)

    for polygon in polygons:
        polygon_dmd = calibration.image_to_dmd(polygon.T).T
        mask |= polygon2mask(calibration.dmd_shape, polygon_dmd)

    return mask
