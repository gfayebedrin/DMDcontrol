"""Tests for geometry helpers."""

import numpy as np

from .calibration import DMDCalibration
from .geometry import polygons_to_mask


def test_polygons_to_mask_covers_full_width():
    """Regression test ensuring wide polygons are not clipped along X."""

    calibration = DMDCalibration(dmd_shape=(10, 6))
    width, height = calibration.dmd_shape

    rectangle_um = np.array(
        [
            [0.0, 0.0],
            [float(width), 0.0],
            [float(width), float(height)],
            [0.0, float(height)],
        ]
    )

    mask = polygons_to_mask([rectangle_um], calibration)

    assert mask.shape == calibration.dmd_shape

    # No clipping near the previous boundary at calibration.dmd_shape[1]
    assert mask[calibration.dmd_shape[1], height - 1]

    on_pixels_x = np.where(mask)[0]
    assert on_pixels_x.min() == 0
    assert on_pixels_x.max() == width - 1
