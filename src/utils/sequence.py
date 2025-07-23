"""
Utilities for handling pattern sequences and timing information.
"""

import numpy as np
from dataclasses import dataclass
import time
from datetime import timedelta
import threading

from ..hardware import DMD
from ..utils.calibration import DMDCalibration
from ..utils.geometry import polygons_to_mask


@dataclass(frozen=True)
class PatternSequence:
    """
    Represents a sequence of patterns with associated timings.

    Attributes:
        patterns (list[list[ndarray]]): List of patterns, where each pattern is a list of (N, 2) numpy arrays representing polygon vertices in µm.
        sequence (list[int]): (M,) array_like, sequence of pattern indices.
        timings (list[timedelta]): (M,) array_like, timing information for each sequence entry in milliseconds.
        durations (list[timedelta]): (M,) array_like, duration for each pattern in milliseconds.
    """

    patterns: list[list[np.ndarray]]
    sequence: list[int]
    timings: list[timedelta]
    durations: list[timedelta]

    def __post_init__(self):
        if not (len(self.sequence) == len(self.timings) == len(self.durations)):
            raise ValueError(
                "sequence, timings, and durations must all have the same length."
            )

    def __len__(self) -> int:
        """Return the number of patterns in the sequence."""
        return len(self.sequence)

    @property
    def timings_milliseconds(self) -> np.ndarray:
        """Return the timings in milliseconds."""
        return np.array([int(t / timedelta(milliseconds=1)) for t in self.timings])

    @property
    def durations_milliseconds(self) -> np.ndarray:
        """Return the durations in milliseconds."""
        return np.array([int(d / timedelta(milliseconds=1)) for d in self.durations])


def play_pattern_sequence(
    dmd: DMD,
    pattern_sequence: PatternSequence,
    calibration: DMDCalibration,
    delay: timedelta = timedelta(milliseconds=-500),
    *,
    stop_event: threading.Event | None = None
):
    """
    Play the pattern sequence on the DMD device.

    Parameters:
        dmd (DMD): The DMD device to start the pattern sequence on.
        pattern_sequence (PatternSequence): The pattern sequence to play.
        calibration (DMDCalibration): The calibration to use for the upload.
        delay (timedelta): The delay before starting the sequence. Should be negative to anticipate.
    """
    timings = pattern_sequence.timings

    assert (
        timings[0] + delay >= timedelta()
    ), "Anticipation cannot be longer than the first timing."

    dmd.frames = [
        polygons_to_mask(pattern, calibration) for pattern in pattern_sequence.patterns
    ]

    if stop_event is not None and stop_event.is_set():
        return

    time.sleep(seconds=(timings[0] + delay).total_seconds())

    dmd.show_frame(pattern_sequence.sequence[0])

    if len(timings) == 1:
        return

    for frame_index, timing in zip(
        pattern_sequence.sequence[1:], pattern_sequence.timings[1:]
    ):
        if stop_event is not None and stop_event.is_set():
            return
        
        time.sleep(seconds=timing.total_seconds())
        dmd.show_frame(frame_index)
