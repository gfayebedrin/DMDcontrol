import h5py
import numpy.typing as npt
from .geometry import DeviceCalibration


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
    raise NotImplementedError


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
    raise NotImplementedError


def save_calibration(filepath: str, calibration: DeviceCalibration):
    """
    Save a calibration object to an HDF5 file.

    Parameters:
    - filepath: str, path to the HDF5 file.
    - calibration: Calibration, the calibration object to save.
    """
    raise NotImplementedError


def load_calibration(filepath: str) -> DeviceCalibration:
    """
    Load a calibration object from an HDF5 file.

    Parameters:
    - filepath: str, path to the HDF5 file.

    Returns:
    - calibration: Calibration, the loaded calibration object.
    """
    raise NotImplementedError
