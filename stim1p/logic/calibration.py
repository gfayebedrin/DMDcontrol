"""Conversion helpers between camera, DMD and micrometre spaces."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _rotation_matrix(angle: float) -> np.ndarray:
    cos_a = float(np.cos(angle))
    sin_a = float(np.sin(angle))
    return np.array([[cos_a, -sin_a], [sin_a, cos_a]], dtype=np.float64)


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

    The calibration models a rigid in-plane rotation alongside per-axis scaling,
    allowing the camera to observe the DMD at an arbitrary angle while still
    providing direct conversions between camera pixels, normalised image
    coordinates, DMD mirrors and micrometre coordinates.
    """

    dmd_shape: tuple[int, int] = (1024, 768)
    camera_shape: tuple[int, int] = (1024, 768)
    camera_origin_pixels: tuple[float, float] = (0.0, 0.0)
    camera_pixels_per_mirror: tuple[float, float] = (1.0, 1.0)
    camera_rotation_rad: float = 0.0
    camera_pixel_size_um: float = 1.0
    micrometers_per_mirror: tuple[float, float] = (1.0, 1.0)
    invert_x: bool = False
    invert_y: bool = False

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
        origin = np.array(self.camera_origin_pixels, dtype=np.float64).reshape(2, 1)
        basis = self._camera_basis_matrix()
        return np.linalg.inv(basis) @ (coords - origin)

    def dmd_to_camera(self, coords: np.ndarray) -> np.ndarray:
        coords = _ensure_2xn(coords, "DMD")
        origin = np.array(self.camera_origin_pixels, dtype=np.float64).reshape(2, 1)
        return origin + self._camera_basis_matrix() @ coords

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

    def _camera_basis_matrix(self) -> np.ndarray:
        """Return the matrix mapping DMD mirror steps to camera pixels."""

        scale = np.array(
            [
                [self.camera_pixels_per_mirror[0], 0.0],
                [0.0, self.camera_pixels_per_mirror[1]],
            ],
            dtype=np.float64,
        )
        return _rotation_matrix(self.camera_rotation_rad) @ scale

def compute_calibration_from_square(
    diagonal_coords_camera: np.ndarray,
    mirror_dimensions: tuple[int, int] | int,
    pixel_size_um: float,
    *,
    camera_shape: tuple[int, int],
    dmd_shape: tuple[int, int] = (1024, 768),
    invert_x: bool = False,
    invert_y: bool = False,
) -> DMDCalibration:
    """Compute a calibration from the observed diagonal of a centred square.

    Parameters
    ----------
    diagonal_coords_camera:
        Points along the drawn diagonal expressed in camera pixels.
    mirror_dimensions:
        Length of the illuminated square in mirrors. May be a single integer
        if the square is isotropic or a ``(x, y)`` pair for non-square
        devices.
    pixel_size_um:
        Physical size of a camera pixel in micrometres.
    invert_x, invert_y:
        Whether the physical DMD axes should be flipped when driving the
        hardware. These flags are only considered when producing upload masks
        for the device; the camera-facing transforms remain unchanged.
    """

    coords = np.asarray(diagonal_coords_camera, dtype=np.float64)
    if coords.ndim != 2 or coords.shape[1] != 2:
        raise ValueError("Diagonal coordinates must be an array of shape (N, 2).")
    if coords.shape[0] < 2:
        raise ValueError("At least two points are required to define the diagonal.")

    p0 = coords[0]
    p1 = coords[-1]
    diagonal_vector = p1 - p0
    diagonal_length = float(np.linalg.norm(diagonal_vector))
    if diagonal_length <= 0.0:
        raise ValueError("Calibration diagonal must have a positive length.")

    if np.isscalar(mirror_dimensions):
        mirrors_x = mirrors_y = int(mirror_dimensions)
    else:
        if len(mirror_dimensions) != 2:
            raise ValueError("Mirror dimensions must contain two values for X and Y.")
        mirrors_x = int(mirror_dimensions[0])
        mirrors_y = int(mirror_dimensions[1])

    if mirrors_x <= 0 or mirrors_y <= 0:
        raise ValueError("Mirror dimensions must be positive integers.")
    if pixel_size_um <= 0:
        raise ValueError("Pixel size must be strictly positive.")

    diag_sign = 1 if diagonal_vector[0] * diagonal_vector[1] >= 0 else -1
    diag_dmd_vector = np.array(
        [diag_sign * mirrors_x, mirrors_y],
        dtype=np.float64,
    )
    diag_mirror_length = float(np.linalg.norm(diag_dmd_vector))
    if diag_mirror_length == 0.0:
        raise ValueError("Mirror diagonal must have a positive length.")

    pixels_per_mirror = diagonal_length / diag_mirror_length

    angle_cam = float(np.arctan2(diagonal_vector[1], diagonal_vector[0]))
    angle_ref = float(np.arctan2(diag_dmd_vector[1], diag_dmd_vector[0]))
    rotation = (angle_cam - angle_ref + np.pi) % (2 * np.pi) - np.pi
    if rotation > np.pi / 2:
        rotation -= np.pi
    elif rotation < -np.pi / 2:
        rotation += np.pi

    scale = np.array(
        [[pixels_per_mirror, 0.0], [0.0, pixels_per_mirror]],
        dtype=np.float64,
    )
    basis = _rotation_matrix(rotation) @ scale

    center_camera = 0.5 * (p0 + p1)
    center_dmd = np.array(
        [dmd_shape[0] / 2.0, dmd_shape[1] / 2.0],
        dtype=np.float64,
    )
    camera_origin = center_camera - basis @ center_dmd

    micrometers_per_mirror = (pixels_per_mirror * pixel_size_um,) * 2

    return DMDCalibration(
        dmd_shape=dmd_shape,
        camera_shape=camera_shape,
        camera_origin_pixels=(float(camera_origin[0]), float(camera_origin[1])),
        camera_pixels_per_mirror=(pixels_per_mirror, pixels_per_mirror),
        camera_rotation_rad=rotation,
        camera_pixel_size_um=pixel_size_um,
        micrometers_per_mirror=micrometers_per_mirror,
        invert_x=bool(invert_x),
        invert_y=bool(invert_y),
    )
