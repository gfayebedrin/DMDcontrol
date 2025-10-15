from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from stim1p.logic.sequence import PatternSequence
from stim1p.ui import dmd_stim_widget


class _DummyStim1P:
    def __init__(self):
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.start_calls = 0
        self.stop_calls = 0
        self.start_run_calls = 0
        self.stop_run_calls = 0
        self._connected = False
        self._listening = False
        self._running = False
        self.calibration = None
        self.axis_definition = None
        self.sequence = None

    @property
    def is_dmd_connected(self) -> bool:
        return self._connected

    @property
    def is_listening(self) -> bool:
        return self._listening

    @property
    def is_running(self) -> bool:
        return self._running

    def connect_dmd(self) -> None:
        self.connect_calls += 1
        if self._connected:
            raise RuntimeError("already connected")
        self._connected = True

    def disconnect_dmd(self) -> None:
        self.disconnect_calls += 1
        self._connected = False

    def start_listening(self) -> None:
        if not self._connected:
            raise RuntimeError("not connected")
        self.start_calls += 1
        self._listening = True

    def stop_listening(self) -> None:
        self.stop_calls += 1
        self._listening = False

    def start_run(self) -> None:
        if not self._connected:
            raise RuntimeError("not connected")
        self.start_run_calls += 1
        self._running = True

    def stop_run(self) -> None:
        self.stop_run_calls += 1
        self._running = False

    def set_calibration(self, calibration) -> None:  # noqa: ANN001
        self.calibration = calibration

    def set_axis_definition(self, axis) -> None:  # noqa: ANN001
        self.axis_definition = axis

    def set_pattern_sequence(self, sequence: PatternSequence | None) -> None:
        self.sequence = sequence


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def widget(monkeypatch, qapp):  # noqa: ANN001
    instances: list[_DummyStim1P] = []

    def _factory():
        inst = _DummyStim1P()
        instances.append(inst)
        return inst

    monkeypatch.setattr(dmd_stim_widget, "Stim1P", _factory)
    widget = dmd_stim_widget.StimDMDWidget()
    yield widget, instances[0]
    widget.deleteLater()


def test_toggle_dmd_connection_updates_controller_and_ui(widget):
    stim_widget, stim = widget
    assert stim_widget.ui.pushButton_connect_dmd.text() == "Connect to DMD"
    assert not stim_widget.ui.pushButton_run_now.isEnabled()

    stim_widget._toggle_dmd_connection()

    assert stim.connect_calls == 1
    assert stim.is_dmd_connected
    assert stim_widget.ui.pushButton_connect_dmd.text() == "Disconnect DMD"
    assert not stim_widget.ui.pushButton_listen_to_matlab.isEnabled()
    assert not stim_widget.ui.pushButton_run_now.isEnabled()

    stim_widget._toggle_dmd_connection()

    assert stim.disconnect_calls == 1
    assert not stim.is_dmd_connected
    assert stim_widget.ui.pushButton_connect_dmd.text() == "Connect to DMD"


def test_toggle_pipe_listener_pushes_state(widget, monkeypatch):
    stim_widget, stim = widget
    messages: list[tuple[str, tuple]] = []

    def _record(kind):
        def _recorder(*args):
            messages.append((kind, args))
            return None

        return _recorder

    monkeypatch.setattr(dmd_stim_widget.QMessageBox, "warning", _record("warning"))
    monkeypatch.setattr(dmd_stim_widget.QMessageBox, "critical", _record("critical"))

    stim_widget.calibration = object()
    stim_widget._set_axis_state([0.0, 0.0], 0.0, True)
    stim_widget._toggle_dmd_connection()

    assert stim_widget.ui.pushButton_listen_to_matlab.isEnabled()
    assert stim_widget.ui.pushButton_run_now.isEnabled()

    stim_widget._toggle_pipe_listener()

    assert stim.start_calls == 1
    assert stim.is_listening
    assert stim.calibration is stim_widget.calibration
    assert stim.axis_definition is not None
    assert isinstance(stim.sequence, PatternSequence)
    assert stim_widget.ui.pushButton_listen_to_matlab.text() == "Stop listening"
    assert not stim_widget.ui.pushButton_run_now.isEnabled()
    assert not messages

    stim_widget._toggle_pipe_listener()

    assert stim.stop_calls == 1
    assert not stim.is_listening
    assert stim_widget.ui.pushButton_listen_to_matlab.text() == "Start listening"
    assert stim_widget.ui.pushButton_run_now.isEnabled()
    assert not messages


def test_run_now_button_starts_and_stops_sequence(widget, monkeypatch):
    stim_widget, stim = widget
    messages: list[tuple[str, tuple]] = []

    def _record(kind):
        def _recorder(*args):
            messages.append((kind, args))
            return None

        return _recorder

    monkeypatch.setattr(dmd_stim_widget.QMessageBox, "warning", _record("warning"))
    monkeypatch.setattr(dmd_stim_widget.QMessageBox, "critical", _record("critical"))

    stim_widget.calibration = object()
    stim_widget._set_axis_state([0.0, 0.0], 0.0, True)
    stim_widget._toggle_dmd_connection()

    assert stim_widget.ui.pushButton_run_now.isEnabled()

    stim_widget._toggle_run_now()

    assert stim.start_run_calls == 1
    assert stim.is_running
    assert stim_widget.ui.pushButton_run_now.text() == "Stop run"
    assert not messages

    stim_widget._toggle_run_now()

    assert stim.stop_run_calls == 1
    assert not stim.is_running
    assert stim_widget.ui.pushButton_run_now.text() == "Start run now"
    assert not messages
