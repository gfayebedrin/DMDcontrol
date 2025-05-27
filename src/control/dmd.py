from . import ALP4


# Directory where the ALP-4.3 API is located
LIBDIR = r"C:\Program Files\ALP-4.3\ALP-4.3 API"


class DMD:
    """Class representing the DMD device."""

    def __init__(self):
        """Initialize the DMD device."""
        self.alp4 = ALP4.ALP4(libDir=LIBDIR)

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.delete()

    def calibrate(self):
        pass

    def delete(self):
        pass

    def reset(self):
        pass

    def upload(self, image):
        pass