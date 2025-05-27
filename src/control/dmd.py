from . import ALP4
from functools import cached_property


# Directory where the ALP-4.3 API is located
LIBDIR = r"C:\Program Files\ALP-4.3\ALP-4.3 API"


class DMD:
    """Class representing the DMD device."""

    def __init__(self):
        """Initialize the DMD device."""
        self._alp4 = ALP4.ALP4(libDir=LIBDIR)
        self._alp4.Initialize()

    # Properties

    @property
    def size(self):
        """Size of the DMD in pixels."""
        return self._alp4.nSizeX, self._alp4.nSizeY
    
    @cached_property
    def max_sequence_length(self):
        """Maximum length of a sequence."""
        return self._alp4.DevInquire(ALP4.ALP_AVAIL_MEMORY)

    # Dunder methods

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.delete()

    # Private methods

    # Public methods

    def calibrate(self):
        pass

    def delete(self):
        self._alp4.Halt()
        self._alp4.Free()

    def reset(self):
        pass

    def upload(self, image):
        pass