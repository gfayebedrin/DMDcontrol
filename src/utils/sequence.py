"""
Utilities for handling pattern sequences and timing information.
"""

import numpy as np
from dataclasses import dataclass
import time, sched, threading
from datetime import timedelta, datetime

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

    # Upload the patterns to the DMD
    dmd.frames = [
        polygons_to_mask(pattern, calibration) for pattern in pattern_sequence.patterns
    ]

    # Schedule the frames to be shown
    scheduler = sched.scheduler()

    for frame_index, timing in zip(pattern_sequence.sequence, pattern_sequence.timings):
        scheduler.enter(
            timing.total_seconds(),
            1,
            dmd.show_frame,
            argument=(frame_index,),
        )

    # Allow cancellation of scheduled tasks
    if stop_event is not None:
        threading.Thread(
            target=_cancel_all, args=(stop_event, scheduler), daemon=True
        ).start()

    scheduler.run()


def _cancel_all(event: threading.Event, scheduler: sched.scheduler):
    """
    Cancel all scheduled tasks when the event is set.

    Parameters:
        event (threading.Event): The event to monitor for cancellation.
        scheduler (sched.scheduler): The scheduler to cancel tasks from.
    """
    event.wait()
    for task in list(scheduler.queue):
        try:
            scheduler.cancel(task)
        except ValueError:
            pass
