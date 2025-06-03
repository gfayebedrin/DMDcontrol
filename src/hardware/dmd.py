from . import ALP4
from functools import cached_property
import numpy as np
import numpy.typing as npt
import ctypes

# Directory where the ALP-4.3 API is located
LIBDIR = r"C:\Program Files\ALP-4.3\ALP-4.3 API"

# Maximum number of distinct values in FLUT entries
FLUT_MAX_VALUES9 = 2**9
FLUT_MAX_VALUES18 = 2**18


class DMD:

    def __init__(self):
        self._alp4 = ALP4.ALP4(libDir=LIBDIR)
        self._alp4.Initialize()
        self._frames = np.empty((0, 0, 0), dtype=bool)
        self._sequence = np.empty((0,), dtype=np.integer)

    # Properties

    @property
    def shape(self):
        """Size of the DMD in pixels."""
        return self._alp4.nSizeX, self._alp4.nSizeY

    @cached_property
    def max_frames(self):
        """Maximum number of frames."""
        max_avail_memory = self._alp4.DevInquire(ALP4.ALP_AVAIL_MEMORY)
        return min(max_avail_memory, FLUT_MAX_VALUES9)

    @property
    def frames(self) -> npt.NDArray[np.integer]:
        """Frames in the device RAM. Defines the images to be displayed.

        Three-dimensional boolean array with shape (frames, width, height)."""
        return self._frames

    @frames.setter
    def frames(self, value: npt.NDArray[np.bool_]):
        assert value.ndim == 3, "Value must be a 3D array (frames, width, height)."
        assert (
            value.shape[1:] == self.shape
        ), f"Images must match DMD shape {self.shape}."
        assert (
            value.shape[0] <= self.max_frames
        ), f"Number of frames exceeds maximum of {self.max_frames} frames."

        self._frames = value

        bitstream = np.packbits(value)
        self._alp4.FreeSeq()
        self._alp4.SeqAlloc(nbImg=value.shape[0])
        self._alp4.SeqPut(bitstream)

    @cached_property
    def max_sequence_length(self):
        """Maximum length of the sequence."""
        return self._alp4.ProjInquire(ALP4.ALP_FLUT_MAX_ENTRIES9)

    @property
    def sequence(self):
        """Sequence in the device RAM. Defines the order of frames to be displayed.

        One-dimensional integer array with shape (frames,)."""
        return self._sequence

    @sequence.setter
    def sequence(self, value: npt.NDArray[np.integer]):
        assert value.ndim == 1, "Value must be a 1D array (sequence)."
        assert (
            value.size <= self.max_frames
        ), f"Sequence length exceeds maximum of {self.max_frames} frames."
        assert np.issubdtype(
            value.dtype, np.integer
        ), "Sequence values must be integers."
        assert np.all(
            (value >= 0) & (value < FLUT_MAX_VALUES9)
        ), f"Sequence values must be between 0 and {FLUT_MAX_VALUES9}."

        flut_write_struct = ALP4.tFlutWrite(
            nOffset=ctypes.c_long(0),
            nSize=ctypes.c_long(value.size),
            FrameNumbers=(ctypes.c_ulong * self.max_sequence_length)(*value),
        )

        self._alp4.ProjControlEx(
            ALP4.ALP_FLUT_WRITE_9BIT, ctypes.byref(flut_write_struct)
        )

        self._sequence = value

    # Dunder methods

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.delete()

    # Private methods

    # Public methods

    def delete(self):
        self._alp4.Halt()
        self._alp4.Free()

    def reset(self):
        self.delete()
        self.__init__()
