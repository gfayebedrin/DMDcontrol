"""
Saving and loading utilities for pattern sequences and dmd calibrations.
"""

import h5py
from datetime import timedelta
import numpy.typing as npt
from .calibration import DMDCalibration
from .sequence import PatternSequence
from dataclasses import asdict


# Constants for HDF5 dataset names
SEQUENCE = "sequence"
TIMINGS = "timings_ms"
DURATIONS = "durations_ms"
PATTERNS = "patterns"
PATTERN = "pattern_{}"
POLYGON = "polygon_{}"


def save_pattern_sequence(
    filepath: str,
    pattern_sequence: PatternSequence
):
    """
    Save a sequence of patterns to an HDF5 file.

    Parameters:
        filepath (str): Path to the HDF5 file.
        pattern_sequence (PatternSequence): The pattern sequence to save.
    """
    with h5py.File(filepath, "w") as f:
        f.create_dataset(SEQUENCE, data=pattern_sequence.sequence)
        f.create_dataset(TIMINGS, data=pattern_sequence.timings_milliseconds)
        f.create_dataset(DURATIONS, data=pattern_sequence.durations_milliseconds)
        f.create_group(PATTERNS, track_order=True)
        for i, pattern in enumerate(pattern_sequence.patterns):
            pattern_group = f[PATTERNS].create_group(
                PATTERN.format(i), track_order=True
            )
            for j, polygon in enumerate(pattern):
                pattern_group.create_dataset(POLYGON.format(j), data=polygon)


def load_pattern_sequence(
    filepath: str,
) -> tuple[list[list], list[int], list[int]]:
    """
    Load a sequence of patterns from an HDF5 file.

    Parameters:
        filepath (str): Path to the HDF5 file.

    Returns:
        pattern_sequence (PatternSequence): Sequence of patterns, timings, and sequence indices.
    """
    with h5py.File(filepath, "r") as f:
        sequence = f[SEQUENCE][()]
        timings_ms = f[TIMINGS][()]
        durations_ms = f[DURATIONS][()]
        patterns = []
        for pattern_name in f[PATTERNS]:
            pattern_group = f[PATTERNS][pattern_name]
            pattern = []
            for polygon_name in pattern_group:
                polygon = pattern_group[polygon_name][()]
                pattern.append(polygon)
            patterns.append(pattern)
    return PatternSequence(
        patterns=patterns,
        sequence=sequence,
        timings=[timedelta(milliseconds=t) for t in timings_ms],
        durations=[timedelta(milliseconds=d) for d in durations_ms]
    )


def save_calibration(filepath: str, calibration: DMDCalibration):
    """
    Save a calibration object to an HDF5 file.

    Parameters:
        filepath (str): Path to the HDF5 file.
        calibration (DMDCalibration): The calibration object to save.
    """
    with h5py.File(filepath, "w") as f:
        for key, value in asdict(calibration).items():
            f.create_dataset(key, data=value)


def load_calibration(filepath: str) -> DMDCalibration:
    """
    Load a calibration object from an HDF5 file.

    Parameters:
        filepath (str): Path to the HDF5 file.

    Returns:
        calibration (DMDCalibration): The loaded calibration object.
    """
    with h5py.File(filepath, "r") as f:
        data = {key: f[key][()] for key in f.keys()}
    return DMDCalibration(**data)
