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
    def __init__(self):
        self.dmd: DMD | None = None
        self.calibration: DMDCalibration | None = None
        self.pattern_sequence: PatternSequence | None = None
        self.pipe_server: NamedPipeServer | None = None

    def connect_dmd(self):
        if self.dmd is not None:
            raise RuntimeError("DMD is already connected.")
        self.dmd = DMD()

    def disconnect_dmd(self):
        if self.dmd is not None:
            self.dmd.disconnect()
            self.dmd = None

    def start_listening(self, pipe_name: str = r"\\.\pipe\MatPy"):
        if self.calibration is None:
            raise RuntimeError("Calibration must be set before starting the server.")
        if self.pattern_sequence is None:
            raise RuntimeError(
                "Pattern sequence must be set before starting the server."
            )
        if self.pipe_server is not None and self.pipe_server.is_alive():
            raise RuntimeError("Pipe server is already running.")

        task = CancellableTask(
            lambda event: play_pattern_sequence(
                self.dmd, self.pattern_sequence, self.calibration, stop_event=event
            )
        )
        self.pipe_server = NamedPipeServer(name=pipe_name, callback=task)
        self.pipe_server.start()

    def stop_listening(self):
        if not self.pipe_server.is_alive():
            return
        self.pipe_server.stop()
        self.pipe_server = None