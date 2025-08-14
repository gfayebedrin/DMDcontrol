from .hardware import DMD

from .utils.calibration import DMDCalibration
from .utils.geometry import PatternCoordinates, polygons_to_mask
from .utils.saving import (
    save_pattern_sequence,
    load_pattern_sequence,
    save_calibration,
    load_calibration,
)
from .utils.sequence import PatternSequence, play_pattern_sequence
from .utils.synchronisation import CancellableTask, NamedPipeServer


class Stim1P:
    """Main class for managing DMD operations.
    This class provides methods to connect to the DMD, 
    load and save calibration and pattern sequences.
    It includes a named pipe server to listen for commands to start and stop DMD operations.
    """

    def __init__(self):
        self._dmd: DMD | None = None
        self._calibration: DMDCalibration | None = None
        self._pattern_sequence: PatternSequence | None = None
        self._pipe_server: NamedPipeServer | None = None

    def __enter__(self):
        """Context manager entry point to connect to the DMD."""
        self.connect_dmd()
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        """Context manager exit point to disconnect from the DMD."""
        self.stop_listening()
        self.disconnect_dmd()

    def connect_dmd(self):
        """Connect to the DMD hardware."""
        if self._dmd is not None:
            raise RuntimeError("DMD is already connected.")
        self._dmd = DMD()

    def disconnect_dmd(self):
        """Disconnect from the DMD hardware."""
        if self._dmd is not None:
            self._dmd.free()
            self._dmd = None

    def start_listening(self, pipe_name: str = r"\\.\pipe\MatPy"):
        """Start the named pipe server to listen for commands.
        Accepted commands are `{"dmd":"start"}` and `{"dmd":"stop"}`.
        Parameters:
            pipe_name (str): The name of the named pipe to listen on.
        Raises:
            RuntimeError: If the server is already running or if calibration or pattern sequence is not set.
        """
        if self._calibration is None:
            raise RuntimeError("Calibration must be set before starting the server.")
        if self._pattern_sequence is None:
            raise RuntimeError(
                "Pattern sequence must be set before starting the server."
            )
        if self._pipe_server is not None and self._pipe_server.is_alive():
            raise RuntimeError("Pipe server is already running.")

        task = CancellableTask(
            lambda event: play_pattern_sequence(
                self._dmd, self._pattern_sequence, self._calibration, stop_event=event
            ),
            command_key="dmd",
            start_cmd="start",
            stop_cmd="stop",
        )
        self._pipe_server = NamedPipeServer(name=pipe_name, callback=task)
        self._pipe_server.start()

    def stop_listening(self):
        """Stop the named pipe server."""
        if self._pipe_server is None:
            return
        self._pipe_server.stop()
        self._pipe_server = None

    def load_calibration(self, filepath: str):
        """
        Load a calibration object from an HDF5 file.
        Parameters:
            filepath (str): Path to the HDF5 file.
        """
        self._calibration = load_calibration(filepath)

    def save_calibration(self, filepath: str):
        """Save the current calibration object to an HDF5 file.
        Parameters:
            filepath (str): Path to the HDF5 file.
        Raises:
            RuntimeError: If no calibration is set.
        """
        if self._calibration is None:
            raise RuntimeError("No calibration to save.")
        save_calibration(filepath, self._calibration)

    def discard_calibration(self):
        """Discard the current calibration object."""
        self._calibration = None

    def load_pattern_sequence(self, filepath: str):
        """Load a pattern sequence from an HDF5 file.
        Parameters:
            filepath (str): Path to the HDF5 file.
        """
        self._pattern_sequence = load_pattern_sequence(filepath)

    def save_pattern_sequence(self, filepath: str):
        """Save the current pattern sequence to an HDF5 file.
        Parameters:
            filepath (str): Path to the HDF5 file.
        Raises:
            RuntimeError: If no pattern sequence is set.
        """
        if self._pattern_sequence is None:
            raise RuntimeError("No pattern sequence to save.")
        save_pattern_sequence(filepath, self._pattern_sequence)

    def discard_pattern_sequence(self):
        """Discard the current pattern sequence."""
        self._pattern_sequence = None
