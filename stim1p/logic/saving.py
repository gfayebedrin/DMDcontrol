"""
Saving and loading utilities for pattern sequences and dmd calibrations.
"""

from dataclasses import asdict, fields
from datetime import timedelta
import dataclasses
import h5py
import numpy as np
import numpy.typing as npt

from .calibration import DMDCalibration
from .sequence import PatternSequence


# Constants for HDF5 dataset names
SEQUENCE = "sequence"
TIMINGS = "timings_ms"
DURATIONS = "durations_ms"
PATTERNS = "patterns"
PATTERN = "pattern_{}"
POLYGON = "polygon_{}"


def save_pattern_sequence(filepath: str, pattern_sequence: PatternSequence):
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
        shape_types = pattern_sequence.shape_types
        for i, pattern in enumerate(pattern_sequence.patterns):
            pattern_group = f[PATTERNS].create_group(
                PATTERN.format(i), track_order=True
            )
            pattern_shape_types: list[str]
            if shape_types is not None and i < len(shape_types):
                pattern_shape_types = list(shape_types[i])
            else:
                pattern_shape_types = []
            if len(pattern_shape_types) < len(pattern):
                pattern_shape_types.extend(
                    ["polygon"] * (len(pattern) - len(pattern_shape_types))
                )
            for j, (polygon, shape_kind) in enumerate(zip(pattern, pattern_shape_types)):
                shape_kind = str(shape_kind)
                dataset = pattern_group.create_dataset(POLYGON.format(j), data=polygon)
                dataset.attrs["shape_type"] = shape_kind
            if pattern_sequence.descriptions is not None:
                if i < len(pattern_sequence.descriptions):
                    pattern_group.attrs["description"] = pattern_sequence.descriptions[i]


def load_pattern_sequence(
    filepath: str,
) -> PatternSequence:
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
        patterns: list[list[np.ndarray]] = []
        shape_types: list[list[str]] = []
        descriptions: list[str] = []
        any_description = False
        any_non_polygon = False

        for pattern_name in f[PATTERNS]:
            pattern_group = f[PATTERNS][pattern_name]
            entries: list[tuple[int, np.ndarray, str]] = []
            for dataset_name, dataset in pattern_group.items():
                try:
                    index = int(dataset_name.split("_")[1])
                except (IndexError, ValueError):
                    index = len(entries)
                data = dataset[()]
                shape_kind_attr = dataset.attrs.get("shape_type", "polygon")
                if isinstance(shape_kind_attr, bytes):
                    shape_kind = shape_kind_attr.decode("utf-8")
                else:
                    shape_kind = str(shape_kind_attr)
                if shape_kind != "polygon":
                    any_non_polygon = True
                entries.append((index, data, shape_kind))
            # Sort by index to ensure deterministic ordering
            entries.sort(key=lambda item: item[0])
            pattern_points = [entry[1] for entry in entries]
            pattern_shapes = [entry[2] for entry in entries]
            patterns.append(pattern_points)
            shape_types.append(pattern_shapes)

            desc_attr = pattern_group.attrs.get("description")
            if isinstance(desc_attr, bytes):
                desc_attr = desc_attr.decode("utf-8")
            desc = desc_attr
            if desc is not None:
                any_description = True
                descriptions.append(str(desc))
            else:
                descriptions.append("")

        descriptions_value = descriptions if any_description else None
        shape_types_value = shape_types if any_non_polygon else None

    return PatternSequence(
        patterns=patterns,
        sequence=sequence,
        timings=[timedelta(milliseconds=float(t)) for t in timings_ms],
        durations=[timedelta(milliseconds=float(d)) for d in durations_ms],
        descriptions=descriptions_value,
        shape_types=shape_types_value,
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
        stored = {key: f[key][()] for key in f.keys()}

    calibration_fields = {field.name: field for field in fields(DMDCalibration)}
    data: dict[str, object] = {}

    for key, value in stored.items():
        if key not in calibration_fields:
            continue
        array_value = np.asarray(value)
        if array_value.shape == ():
            data[key] = array_value.item()
        elif array_value.ndim == 1:
            if np.issubdtype(array_value.dtype, np.integer):
                data[key] = tuple(int(v) for v in array_value.tolist())
            else:
                data[key] = tuple(float(v) for v in array_value.tolist())
        else:
            data[key] = array_value

    for field in calibration_fields.values():
        if field.name in data:
            continue
        if field.default is not dataclasses.MISSING:
            data[field.name] = field.default
        elif field.default_factory is not dataclasses.MISSING:  # type: ignore[attr-defined]
            data[field.name] = field.default_factory()  # type: ignore[misc]
        else:
            raise KeyError(f"Missing calibration parameter '{field.name}' in file {filepath}.")

    return DMDCalibration(**data)
