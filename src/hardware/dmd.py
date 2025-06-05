"""
Wrapper for the ALP-4.3 API to control a DMD device.
"""

from . import ALP4
from functools import cached_property
import numpy as np
import numpy.typing as npt
import ctypes

# Directory where the ALP-4.3 API is located
LIBDIR = r"C:\Program Files\ALP-4.3\ALP-4.3 API"


class DMD:

    def __init__(self):
        self._alp4 = ALP4.ALP4(libDir=LIBDIR)
        self._alp4.Initialize()
        self._alp4.SeqControl(ALP4.ALP_FLUT_MODE, ALP4.ALP_FLUT_9BIT)
        # may need to set ALP_FLUT_ENTRIES9 to 2*len(sequence) according to C++ sample
        self._alp4.SeqControl(ALP4.ALP_BIN_MODE, ALP4.ALP_BIN_UNINTERRUPTED)
        self._alp4.SetTiming()

        self._frames = np.empty((0, 0, 0), dtype=bool)
        self._is_frame_shown = False

    # Properties

    @property
    def shape(self):
        """Size of the DMD in pixels."""
        return self._alp4.nSizeX, self._alp4.nSizeY

    @cached_property
    def max_frames(self):
        """Maximum number of frames."""
        return self._alp4.DevInquire(ALP4.ALP_AVAIL_MEMORY)

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
        self._alp4.Halt()
        self._alp4.FreeSeq()
        self._alp4.SeqAlloc(nbImg=value.shape[0])
        self._alp4.SeqPut(bitstream)

        self.show_frame(0)
        self._alp4.Run()

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

    def show_frame(self, frame_index:int):        
        flut = ALP4.tFlutWrite(
            nOffset=ctypes.c_long(0),
            nSize=ctypes.c_long(1),
            FrameNumbers=(ctypes.c_ulong * 4096)(frame_index)
        )
        self._alp4.ProjControlEx(ALP4.ALP_FLUT_WRITE_9BIT, ctypes.byref(flut))