import h5py
import numpy.typing as npt
from .calibration import DeviceCalibration
from dataclasses import asdict


# Constants for HDF5 dataset names
SEQUENCE = "sequence"
TIMINGS = "timings"
PATTERNS = "patterns"
PATTERN = "pattern_{}"
POLYGON = "polygon_{}"


def save_pattern_sequence(
    filepath: str,
    patterns: list[list[npt.ArrayLike[float]]],
    sequence: npt.ArrayLike[int],
    timings: npt.ArrayLike[int],
):
    """
    Save a sequence of patterns to an HDF5 file.

    Parameters:
    - filepath: str, path to the HDF5 file.
    - patterns: list of patterns. Each pattern is a list of (N,2) numpy arrays representing polygon vertices in µm.
    - sequence: (M,) array_like, sequence of pattern indices.
    - timings: (M,) array_like, timing information for each sequence entry in milliseconds.
    """
    with h5py.File(filepath, "w") as f:
        f.create_dataset(SEQUENCE, data=sequence)
        f.create_dataset(TIMINGS, data=timings)
        f.create_group(PATTERNS, track_order=True)
        for i, pattern in enumerate(patterns):
            pattern_group = f[PATTERNS].create_group(
                PATTERN.format(i), track_order=True
            )
            for j, polygon in enumerate(pattern):
                pattern_group.create_dataset(POLYGON.format(j), data=polygon)


def load_pattern_sequence(
    filepath: str,
) -> tuple[list[list[npt.ArrayLike[float]]], npt.ArrayLike[int], npt.ArrayLike[int]]:
    """
    Load a sequence of patterns from an HDF5 file.

    Parameters:
    - filepath: str, path to the HDF5 file.

    Returns:
    - patterns: list of patterns. Each pattern is a list of (N,2) numpy arrays representing polygon vertices in µm.
    - sequence: (M,) array_like, sequence of pattern indices.
    - timings: (M,) array_like, timing information for each sequence entry in milliseconds.
    """
    with h5py.File(filepath, "r") as f:
        sequence = f[SEQUENCE][()]
        timings = f[TIMINGS][()]
        patterns = []
        for pattern_name in f[PATTERNS]:
            pattern_group = f[PATTERNS][pattern_name]
            pattern = []
            for polygon_name in pattern_group:
                polygon = pattern_group[polygon_name][()]
                pattern.append(polygon)
            patterns.append(pattern)
    return patterns, sequence, timings


def save_calibration(filepath: str, calibration: DeviceCalibration):
    """
    Save a calibration object to an HDF5 file.

    Parameters:
    - filepath: str, path to the HDF5 file.
    - calibration: Calibration, the calibration object to save.
    """
    with h5py.File(filepath, "w") as f:
        for key, value in asdict(calibration).items():
            f.create_dataset(key, data=value)


def load_calibration(filepath: str) -> DeviceCalibration:
    """
    Load a calibration object from an HDF5 file.

    Parameters:
    - filepath: str, path to the HDF5 file.

    Returns:
    - calibration: Calibration, the loaded calibration object.
    """
    with h5py.File(filepath, "r") as f:
        data = {key: f[key][()] for key in f.keys()}
    return DeviceCalibration(**data)
