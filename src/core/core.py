import numpy.typing as npt
from ..hardware import DMD


def get_device():
    return DMD()


def free_device(device: DMD):
    device.delete()


def set_pattern_sequence(
    device: DMD,
    patterns: list[list[npt.ArrayLike[float]]],
    sequence: npt.ArrayLike[int],
    timings: npt.ArrayLike[int],
):
    """
    Set the pattern sequence on the DMD device.

    Parameters:
    - device: DMD, the DMD device to set the pattern sequence on.
    - patterns: list of patterns. Each pattern is a list of (N,2) numpy arrays representing polygon vertices in µm.
    - sequence: (M,) array_like, sequence of pattern indices.
    - timings: (M,) array_like, timing information for each sequence entry in milliseconds.
    """
    raise NotImplementedError
