"""
Conversion between image coordinates and dmd coordinates.
"""

import numpy as np
from dataclasses import dataclass


@dataclass(frozen=True)
class DMDCalibration:
    """
    Calibration parameters for converting between image coordinates and dmd coordinates.
    Image coordinates are in the range [0, 1] and represent the normalized position in the image.
    Device coordinates are in pixels, with the origin at the top-left corner of the dmd.

    Attributes:
    - dmd_shape: tuple of ints, shape of the image (default: (1024, 768)).
    - x_min: float, minimum x coordinate of the stimulation area in image coordinates.
    - x_max: float, maximum x coordinate of the stimulation area in image coordinates.
    - y_min: float, minimum y coordinate of the stimulation area in image coordinates.
    - y_max: float, maximum y coordinate of the stimulation area in image coordinates.
    - X_min: int, minimum x coordinate of the stimulation area in dmd coordinates.
    - X_max: int, maximum x coordinate of the stimulation area in dmd coordinates.
    - Y_min: int, minimum y coordinate of the stimulation area in dmd coordinates.
    - Y_max: int, maximum y coordinate of the stimulation area in dmd coordinates.
    """

    dmd_shape: tuple[int, int] = (1024, 768)
    X_min: int = 0
    X_max: int = dmd_shape[0] - 1
    Y_min: int = 0
    Y_max: int = dmd_shape[1] - 1
    x_min: float = 0.0
    x_max: float = 1.0
    y_min: float = 0.0
    y_max: float = 1.0

    def dmd_to_image(self, coords: np.ndarray) -> np.ndarray:
        """
        Convert dmd coordinates to image coordinates.

        Parameters:
        - coords: (2,...) array_like, dmd coordinates in pixels.

        Returns:
        - (2,...) array_like, image coordinates in the range [0, 1].
        """
        x = (coords[0] - self.X_min) / (self.X_max - self.X_min)
        y = (coords[1] - self.Y_min) / (self.Y_max - self.Y_min)
        return np.array([x, y], dtype=np.float64)

    def image_to_dmd(self, coords: np.ndarray) -> np.ndarray:
        """
        Convert image coordinates to dmd coordinates.

        Parameters:
        - coords: (2,...) array_like, image coordinates in the range [0, 1].

        Returns:
        - (2,...) array_like, dmd coordinates in pixels.
        """
        x = coords[0] * (self.X_max - self.X_min) + self.X_min
        y = coords[1] * (self.Y_max - self.Y_min) + self.Y_min
        return np.array([x, y], dtype=np.float64)