"""Conversion helpers between camera, DMD and micrometre spaces."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _ensure_2xn(coords: np.ndarray, domain: str) -> np.ndarray:
    """Validate and normalise coordinate arrays to the (2, N) convention."""

    arr = np.asarray(coords, dtype=np.float64)
    if arr.ndim == 1:
        if arr.size != 2:
            raise ValueError(f"{domain} coordinates must have size 2 along axis 0.")
        return arr.reshape(2, 1)
    if arr.shape[0] != 2:
        if arr.shape[-1] == 2:
            arr = np.moveaxis(arr, -1, 0)
        else:
            raise ValueError(
                f"{domain} coordinates must be provided as (2, N) or (N, 2) arrays."
            )
    return np.asarray(arr, dtype=np.float64)


@dataclass(frozen=True)
class DMDCalibration:
    """Bidirectional mappings between camera pixels, DMD mirrors and micrometres.

    The calibration assumes axis-aligned scaling without shear or distortion. It is
    therefore defined by the camera pixel origin of the DMD (top-left mirror), the
    number of camera pixels per DMD mirror along each axis, and the micrometre size
    of a single mirror. Helper methods provide conversions between camera pixels,
    normalised image coordinates, DMD mirrors and micrometre coordinates.
    """

    dmd_shape: tuple[int, int] = (1024, 768)
    camera_shape: tuple[int, int] = (1024, 768)
    camera_origin_pixels: tuple[float, float] = (0.0, 0.0)
    camera_pixels_per_mirror: tuple[float, float] = (1.0, 1.0)
    camera_pixel_size_um: float = 1.0
    micrometers_per_mirror: tuple[float, float] = (1.0, 1.0)
    X_min: int = 0
    X_max: int = 1023
    Y_min: int = 0
    Y_max: int = 767
    x_min: float = 0.0
    x_max: float = 1.0
    y_min: float = 0.0
    y_max: float = 1.0

    def __post_init__(self):
        object.__setattr__(self, "X_max", int(self.dmd_shape[0] - 1))
        object.__setattr__(self, "Y_max", int(self.dmd_shape[1] - 1))

    # ------------------------------------------------------------------
    # Camera ↔ image normalisation
    def camera_to_image(self, coords: np.ndarray) -> np.ndarray:
        coords = _ensure_2xn(coords, "Camera")
        width = max(self.camera_shape[0] - 1, 1)
        height = max(self.camera_shape[1] - 1, 1)
        x = coords[0] / width
        y = coords[1] / height
        return np.vstack((x, y))

    def image_to_camera(self, coords: np.ndarray) -> np.ndarray:
        coords = _ensure_2xn(coords, "Image")
        x = coords[0] * (self.camera_shape[0] - 1)
        y = coords[1] * (self.camera_shape[1] - 1)
        return np.vstack((x, y))

    # ------------------------------------------------------------------
    # Camera ↔ DMD
    def camera_to_dmd(self, coords: np.ndarray) -> np.ndarray:
        coords = _ensure_2xn(coords, "Camera")
        x = (coords[0] - self.camera_origin_pixels[0]) / self.camera_pixels_per_mirror[0]
        y = (coords[1] - self.camera_origin_pixels[1]) / self.camera_pixels_per_mirror[1]
        return np.vstack((x, y))

    def dmd_to_camera(self, coords: np.ndarray) -> np.ndarray:
        coords = _ensure_2xn(coords, "DMD")
        x = coords[0] * self.camera_pixels_per_mirror[0] + self.camera_origin_pixels[0]
        y = coords[1] * self.camera_pixels_per_mirror[1] + self.camera_origin_pixels[1]
        return np.vstack((x, y))

    # ------------------------------------------------------------------
    # DMD ↔ micrometres
    def dmd_to_micrometre(self, coords: np.ndarray) -> np.ndarray:
        coords = _ensure_2xn(coords, "DMD")
        x = coords[0] * self.micrometers_per_mirror[0]
        y = coords[1] * self.micrometers_per_mirror[1]
        return np.vstack((x, y))

    def micrometre_to_dmd(self, coords: np.ndarray) -> np.ndarray:
        coords = _ensure_2xn(coords, "Micrometre")
        x = coords[0] / self.micrometers_per_mirror[0]
        y = coords[1] / self.micrometers_per_mirror[1]
        return np.vstack((x, y))

    # ------------------------------------------------------------------
    # Composite helpers
    def camera_to_micrometre(self, coords: np.ndarray) -> np.ndarray:
        return self.dmd_to_micrometre(self.camera_to_dmd(coords))

    def micrometre_to_camera(self, coords: np.ndarray) -> np.ndarray:
        return self.dmd_to_camera(self.micrometre_to_dmd(coords))

    def image_to_dmd(self, coords: np.ndarray) -> np.ndarray:
        return self.camera_to_dmd(self.image_to_camera(coords))

    def dmd_to_image(self, coords: np.ndarray) -> np.ndarray:
        return self.camera_to_image(self.dmd_to_camera(coords))

    def image_to_micrometre(self, coords: np.ndarray) -> np.ndarray:
        return self.dmd_to_micrometre(self.image_to_dmd(coords))

    def micrometre_to_image(self, coords: np.ndarray) -> np.ndarray:
        return self.dmd_to_image(self.micrometre_to_dmd(coords))

def compute_calibration_from_square(
    square_coords_camera: np.ndarray,
    mirror_dimensions: tuple[int, int],
    pixel_size_um: float,
    *,
    camera_shape: tuple[int, int],
    dmd_shape: tuple[int, int] = (1024, 768),
) -> DMDCalibration:
    """Compute an axis-aligned calibration from a camera-observed square."""

    coords = np.asarray(square_coords_camera, dtype=np.float64)
    if coords.ndim != 2 or coords.shape[1] != 2:
        raise ValueError("Square coordinates must be an array of shape (N, 2).")

    x_min = float(coords[:, 0].min())
    x_max = float(coords[:, 0].max())
    y_min = float(coords[:, 1].min())
    y_max = float(coords[:, 1].max())

    width_pixels = x_max - x_min
    height_pixels = y_max - y_min

    if width_pixels <= 0 or height_pixels <= 0:
        raise ValueError("Calibration square must have a positive area.")

    mirrors_x, mirrors_y = mirror_dimensions
    if mirrors_x <= 0 or mirrors_y <= 0:
        raise ValueError("Mirror dimensions must be positive integers.")
    if pixel_size_um <= 0:
        raise ValueError("Pixel size must be strictly positive.")

    pixels_per_mirror_x = width_pixels / mirrors_x
    pixels_per_mirror_y = height_pixels / mirrors_y

    micrometers_per_mirror_x = pixels_per_mirror_x * pixel_size_um
    micrometers_per_mirror_y = pixels_per_mirror_y * pixel_size_um

    camera_width = camera_shape[0]
    camera_height = camera_shape[1]

    x_min_norm = x_min / max(camera_width - 1, 1)
    x_max_norm = x_max / max(camera_width - 1, 1)
    y_min_norm = y_min / max(camera_height - 1, 1)
    y_max_norm = y_max / max(camera_height - 1, 1)

    return DMDCalibration(
        dmd_shape=dmd_shape,
        camera_shape=camera_shape,
        camera_origin_pixels=(x_min, y_min),
        camera_pixels_per_mirror=(pixels_per_mirror_x, pixels_per_mirror_y),
        camera_pixel_size_um=pixel_size_um,
        micrometers_per_mirror=(micrometers_per_mirror_x, micrometers_per_mirror_y),
        X_min=0,
        X_max=dmd_shape[0] - 1,
        Y_min=0,
        Y_max=dmd_shape[1] - 1,
        x_min=x_min_norm,
        x_max=x_max_norm,
        y_min=y_min_norm,
        y_max=y_max_norm,
    )
