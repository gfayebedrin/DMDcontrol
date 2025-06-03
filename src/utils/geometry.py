from dataclasses import dataclass
import numpy as np
from skimage.draw import polygon2mask


@dataclass(frozen=True)
class DeviceCalibration:
    """
    Calibration parameters for converting pixel coordinates to [0, 1] range.
    Attributes:
    - image_shape: tuple of ints, shape of the image (default: (768, 1024)).
    - xrange: tuple of floats, range for x-coordinates (default: (0.0, 1.0)). Used for cropping.
    - yrange: tuple of floats, range for y-coordinates (default: (0.0, 1.0)). Used for cropping.
    """

    device_shape: tuple[int, int] = (768, 1024)
    xrange: tuple[float, float] = (0.0, 1.0)
    yrange: tuple[float, float] = (0.0, 1.0)
    pixel_size: tuple[float, float] = (1.0, 1.0)  # Size of a pixel in µm

    def um_to_px(self, coords: np.ndarray) -> np.ndarray:
        """
        Convert normalized coordinates to pixel coordinates based on the calibration ranges.

        Parameters:
        - coords: (N, 2) array_like, normalized coordinates in µm.

        Returns:
        - px_coords: (N, 2) array_like, pixel coordinates.
        """
        raise NotImplementedError

    def um_from_px(self, px_coords: np.ndarray) -> np.ndarray:
        """
        Convert pixel coordinates to normalized coordinates based on the calibration ranges.

        Parameters:
        - px_coords: (N, 2) array_like, pixel coordinates.

        Returns:
        - coords: (N, 2) array_like, normalized coordinates in [0, 1] range.
        """
        raise NotImplementedError


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


def polygons_to_mask(polygons, calibration: DeviceCalibration):
    """
    Convert a list of polygons to a binary mask.

    Parameters:
    - image_shape: tuple, shape of the image (height, width).
    - polygons: list of (N, 2) array_like. The coordinates are (row, column).
    - calibration: tuple

    Returns:
    - mask: 2D numpy array, binary mask with `True` inside the polygons and `False` outside.
    """
    mask = np.zeros(calibration.device_shape, dtype=bool)

    for polygon in polygons:
        # Scale the polygon coordinates according to the calibration ranges
        mask |= polygon2mask(calibration.device_shape, calibration.to_px(polygon))

    return mask
