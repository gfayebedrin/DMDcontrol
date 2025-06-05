"""
Utilities for handling pattern sequences and timing information.
"""

import numpy as np
from dataclasses import dataclass
import asyncio

from ..hardware import DMD
from ..utils.calibration import DMDCalibration
from ..utils.geometry import polygons_to_mask


@dataclass(frozen=True)
class PatternSequence:
    """
    Represents a sequence of patterns with associated timings.

    Attributes:
        patterns (list[list[ndarray]]): List of patterns, where each pattern is a list of (N, 2) numpy arrays representing polygon vertices in µm.
        sequence (ndarray): (M,) array_like, sequence of pattern indices.
        timings (ndarray): (M,) array_like, timing information for each sequence entry in milliseconds.
        durations (ndarray): (M,) array_like, duration for each pattern in milliseconds.
    """

    patterns: list[list[np.ndarray]]
    sequence: np.ndarray[int]
    timings: np.ndarray[int]
    durations: np.ndarray[int]


def upload_pattern_sequence(
    dmd: DMD, calibration: DMDCalibration, pattern_sequence: PatternSequence
):
    """
    Upload the pattern sequence to the DMD device.

    Parameters:
        dmd (DMD): The DMD device to upload the pattern sequence to.
        calibration (DMDCalibration): The calibration to use for the upload.
        pattern_sequence (PatternSequence): The pattern sequence to upload.
    """
    dmd.frames = [
        polygons_to_mask(pattern, calibration) for pattern in pattern_sequence.patterns
    ]
    dmd.sequence = pattern_sequence.sequence


async def play_pattern_sequence(
    dmd: DMD, pattern_sequence: PatternSequence, delay: int = -500
):
    """
    Play the pattern sequence on the DMD device.

    Parameters:
        dmd (DMD): The DMD device to start the pattern sequence on.
        pattern_sequence (PatternSequence): The pattern sequence to play.
        delay (int): The delay before starting the sequence in milliseconds. Should be negative to anticipate.
    """
    timings = pattern_sequence.timings

    assert (
        timings[0] + delay >= 0
    ), "Anticipation cannot be longer than the first timing."

    dmd.show_first_frame()

    await asyncio.sleep((timings[0] + delay) / 1000)

    if len(timings) == 1:
        return

    for timing in pattern_sequence.timings[1:]:
        await asyncio.sleep(timing / 1000)
        dmd.show_next_frame()