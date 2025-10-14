"""
Utilities for handling pattern sequences and timing information.
"""

import numpy as np
from dataclasses import dataclass
import sched, threading
from datetime import timedelta, datetime

# from ..hardware import DMD # TODO put that again in the future
from ..logic.calibration import DMDCalibration
from ..logic.geometry import AxisDefinition, axis_polygons_to_global, polygons_to_mask


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
    descriptions: list[str] | None = None
    shape_types: list[list[str]] | None = None

    def __post_init__(self):
        if not (len(self.sequence) == len(self.timings) == len(self.durations)):
            raise ValueError(
                "sequence, timings, and durations must all have the same length."
            )

        if self.descriptions is not None and len(self.descriptions) != len(self.patterns):
            raise ValueError(
                "descriptions must have the same length as patterns if provided."
            )

        if self.shape_types is not None:
            if len(self.shape_types) != len(self.patterns):
                raise ValueError(
                    "shape_types must have the same length as patterns if provided."
                )
            for idx, (shapes, polys) in enumerate(zip(self.shape_types, self.patterns)):
                if len(shapes) != len(polys):
                    raise ValueError(
                        f"shape_types[{idx}] must have the same length as the corresponding pattern."
                    )

    def __len__(self) -> int:
        """Return the length of the sequence."""
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
    dmd,# TODO put type hint "DMD",
    pattern_sequence: PatternSequence,
    calibration: DMDCalibration,
    delay: timedelta = timedelta(milliseconds=-500),
    *,
    stop_event: threading.Event | None = None,
    axis_definition: AxisDefinition | None = None,
):
    """
    Play the pattern sequence on the DMD device.

    Parameters:
        dmd (DMD): The DMD device to start the pattern sequence on.
        pattern_sequence (PatternSequence): The pattern sequence to play.
        calibration (DMDCalibration): The calibration to use for the upload.
        delay (timedelta): The delay before starting the sequence. Should be negative to anticipate.
        axis_definition (AxisDefinition | None): Axis placement used to interpret
            pattern vertices in the object frame. If ``None`` the polygons are
            assumed to already be expressed in the calibration frame.
    """
    t0 = datetime.now() + delay

    timings = pattern_sequence.timings

    assert (
        timings[0] + delay >= timedelta()
    ), "Anticipation cannot be longer than the first timing."

    if axis_definition is not None:
        transformed_patterns = [
            axis_polygons_to_global(pattern, axis_definition, calibration)
            for pattern in pattern_sequence.patterns
        ]
    else:
        transformed_patterns = pattern_sequence.patterns

    # Upload the patterns to the DMD
    dmd.frames = np.array([
        polygons_to_mask(pattern, calibration) for pattern in transformed_patterns
    ])

    # Schedule the frames to be shown
    scheduler = sched.scheduler()

    for frame_index, timing in zip(pattern_sequence.sequence, pattern_sequence.timings):
        scheduler.enterabs(
            (t0 + timing).timestamp(),
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
