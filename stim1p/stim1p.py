from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

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
        self._run_task: CancellableTask | None = None
        self._listener_task: CancellableTask | None = None

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

    def dmd_shape(self) -> tuple[int, int] | None:
        """Return the shape of the connected DMD in mirrors (width, height)."""

        if self._dmd is None:
            return None
        try:
            width, height = self._dmd.shape
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Unable to query DMD shape.") from exc
        return int(width), int(height)

    def display_calibration_frame(self, square_size: int) -> None:
        """Show a single calibration frame with a centred bright square."""

        if self._dmd is None:
            raise RuntimeError("Connect to the DMD before sending a calibration frame.")
        if self.is_running:
            raise RuntimeError("Stop the running pattern sequence before sending a calibration frame.")
        if self.is_listening:
            raise RuntimeError("Stop the MATLAB listener before sending a calibration frame.")
        if square_size <= 0:
            raise ValueError("Square size must be a positive integer.")

        shape = self.dmd_shape()
        if shape is None:
            raise RuntimeError("Unable to determine the DMD shape.")
        width, height = shape
        size = int(square_size)
        size = max(1, min(size, width, height))

        frame = np.zeros((width, height), dtype=bool)
        x_start = (width - size) // 2
        y_start = (height - size) // 2
        frame[x_start : x_start + size, y_start : y_start + size] = True

        self._dmd.frames = frame[np.newaxis, ...]

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
        if self.is_running:
            raise RuntimeError("Pattern sequence is already running.")
        if self._pipe_server is not None and self._pipe_server.is_alive():
            raise RuntimeError("Pipe server is already running.")

        self._listener_task = CancellableTask(
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
        self._pipe_server = NamedPipeServer(name=pipe_name, callback=self._listener_task)
        self._pipe_server.start()

    def stop_listening(self):
        """Stop the named pipe server."""
        if self._pipe_server is None:
            return
        self._pipe_server.stop()
        self._pipe_server = None
        self._listener_task = None

    @property
    def is_running(self) -> bool:
        """Return ``True`` when the pattern sequence is currently executing."""

        return any(
            task is not None and task.is_running()
            for task in (self._run_task, self._listener_task)
        )

    def start_run(self):
        """Start playing the pattern sequence immediately on the connected DMD."""

        if self._dmd is None:
            raise RuntimeError("Connect to the DMD before starting a run.")
        if self._calibration is None:
            raise RuntimeError("Calibration must be set before starting a run.")
        if self._pattern_sequence is None:
            raise RuntimeError("Pattern sequence must be set before starting a run.")
        if self.is_running:
            raise RuntimeError("Pattern sequence is already running.")

        if self._run_task is None:
            self._run_task = CancellableTask(
                lambda event: play_pattern_sequence(
                    self._dmd,
                    self._pattern_sequence,
                    self._calibration,
                    stop_event=event,
                    axis_definition=self._axis_definition,
                )
            )

        reply = self._run_task.start()

        status = reply.get("status")
        if status == "started":
            return
        if status == "already_running":
            raise RuntimeError("Pattern sequence is already running.")
        raise RuntimeError(f"Unable to start run (status: {status}).")

    def stop_run(self):
        """Stop the currently running pattern sequence, if any."""

        if not self.is_running:
            return

        errors: list[str] = []
        for task in (self._run_task, self._listener_task):
            if task is None or not task.is_running():
                continue
            reply = task.stop()
            status = reply.get("status")
            if status not in {"stopped", "not_running"}:
                errors.append(status or "unknown")
        if errors:
            raise RuntimeError(f"Unable to stop run (status: {', '.join(errors)}).")

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
