from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from .hardware import DMD as _DMD_CLASS
except ImportError as exc:  # pragma: no cover - exercised when drivers are absent
    _DMD_CLASS = None
    _DMD_IMPORT_ERROR = exc
else:
    _DMD_IMPORT_ERROR = None

if TYPE_CHECKING:  # pragma: no cover - import only for static typing
    from .hardware import DMD

from .logic.calibration import DMDCalibration
from .logic.geometry import AxisDefinition, PatternCoordinates, polygons_to_mask
from .logic.saving import (
    load_calibration,
    load_pattern_sequence,
    save_calibration,
    save_pattern_sequence,
)
from .logic.sequence import PatternSequence, play_pattern_sequence
from .logic.synchronisation import (
    CancellableTask,
    NAMED_PIPE_SUPPORTED,
    NAMED_PIPE_UNAVAILABLE_REASON,
    NamedPipeServer,
)


class Stim1P:
    """Main class for managing DMD operations.

    The class can be instantiated on machines that do not have the DMD hardware
    stack installed, which allows preparing calibration and pattern sequence
    files offline. Hardware-specific calls such as :meth:`connect_dmd` and
    :meth:`start_listening` raise :class:`RuntimeError` when the underlying
    drivers or Windows-only dependencies are unavailable.

    Example:
        >>> stim = Stim1P()  # doctest: +SKIP
        >>> stim.load_pattern_sequence("patterns.h5")  # doctest: +SKIP
    """

    def __init__(self):
        self._dmd: DMD | None = None
        self._calibration: DMDCalibration | None = None
        self._pattern_sequence: PatternSequence | None = None
        self._pipe_server: NamedPipeServer | None = None
        self._axis_definition: AxisDefinition | None = None

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
        if _DMD_CLASS is None:
            reason = (
                "DMD hardware support is not available on this machine."
                if _DMD_IMPORT_ERROR is None
                else f"DMD hardware support could not be loaded: {_DMD_IMPORT_ERROR}"
            )
            raise RuntimeError(reason)
        self._dmd = _DMD_CLASS()

    def disconnect_dmd(self):
        """Disconnect from the DMD hardware."""
        if self._dmd is None:
            return
        self._dmd.free()
        self._dmd = None

    def start_listening(self, pipe_name: str = r"\\.\pipe\MatPy"):
        """Start the named pipe server to listen for commands.

        Accepted commands are `{"dmd":"start"}` and `{"dmd":"stop"}`.

        Parameters:
            pipe_name (str): The name of the named pipe to listen on.

        Raises:
            RuntimeError: If the server is already running or if calibration or
                pattern sequence is not set.
        """
        if not NAMED_PIPE_SUPPORTED:
            reason = (
                NAMED_PIPE_UNAVAILABLE_REASON
                or "Named pipe synchronisation is unavailable on this platform."
            )
            raise RuntimeError(reason)
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
                self._dmd,
                self._pattern_sequence,
                self._calibration,
                stop_event=event,
                axis_definition=self._axis_definition,
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

    @property
    def is_dmd_connected(self) -> bool:
        """Return ``True`` when a DMD instance is currently active."""

        return self._dmd is not None

    @property
    def is_listening(self) -> bool:
        """Return ``True`` when the named pipe server is running."""

        return bool(self._pipe_server and self._pipe_server.is_alive())

    def load_calibration(self, filepath: str):
        """Load a calibration object from an HDF5 file."""
        self._calibration = load_calibration(filepath)

    def set_calibration(self, calibration: DMDCalibration | None) -> None:
        """Assign the calibration to use for subsequent playback."""

        self._calibration = calibration

    def save_calibration(self, filepath: str):
        """Save the current calibration object to an HDF5 file."""
        if self._calibration is None:
            raise RuntimeError("No calibration to save.")
        save_calibration(filepath, self._calibration)

    def discard_calibration(self):
        """Discard the current calibration object."""
        self._calibration = None

    def load_pattern_sequence(self, filepath: str):
        """Load a pattern sequence from an HDF5 file."""
        self._pattern_sequence = load_pattern_sequence(filepath)

    def set_pattern_sequence(self, sequence: PatternSequence | None) -> None:
        """Assign the in-memory pattern sequence to play back."""

        self._pattern_sequence = sequence

    def save_pattern_sequence(self, filepath: str):
        """Save the current pattern sequence to an HDF5 file."""
        if self._pattern_sequence is None:
            raise RuntimeError("No pattern sequence to save.")
        save_pattern_sequence(filepath, self._pattern_sequence)

    def discard_pattern_sequence(self):
        """Discard the current pattern sequence."""
        self._pattern_sequence = None

    def set_axis_definition(self, axis: AxisDefinition | None):
        """Store the axis definition used to interpret pattern coordinates."""

        self._axis_definition = axis
