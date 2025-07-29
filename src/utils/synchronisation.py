"""Lightweight named-pipe server for MATLAB ⇄ Python experiments (Windows only).

Requires:  pywin32  (pip install pywin32)
Usage:
    from named_pipe_bridge import NamedPipeServer, CancellableTask

    # Example cancellable task
    import time
    def blink(event):
        print("tick")
        time.sleep(0.5)

    task = CancellableTask(blink)

    srv = NamedPipeServer()

    # Register a dict-style dispatcher so MATLAB can control the task
    def on_msg(msg):
        match msg.get("cmd"):
            case "TASK":
                return task(msg.get("action"))
            case _:
                return {"status": "unknown"}

    srv.callback = on_msg
    srv.start()
"""

from __future__ import annotations
import time
import json, threading, traceback
from typing import Callable, Literal, Optional
from types import SimpleNamespace

import win32pipe, win32file, pywintypes


MESSAGES = SimpleNamespace(COMMAND_KEY="cmd", START_CMD="start", STOP_CMD="stop")
SLEEP_TIME = 0.01  # seconds
TIMEOUT = 5  # seconds, for pipe connection


class CancellableTask:
    """
    Run a function in its own thread that can be started and stopped via pipe messages.
    The function should accept a threading.Event parameter to check for cancellation.
    """

    def __init__(self, func: Callable[[threading.Event], None]):
        """
        Initialize the task with a function that accepts a threading.Event to check for cancellation.
        The function should run in a loop, checking the event to stop gracefully.

        Parameters:
            func (Callable[[threading.Event], None]): The function to run in the task.
        """
        self._func = func
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()

    def __call__(self, message: dict) -> dict:
        """
        Handle incoming messages to control the task.
        Reacts to messages defined in constant MESSAGES.
        """
        if MESSAGES.COMMAND_KEY not in message:
            return {"status": "command_missing"}
        match message[MESSAGES.COMMAND_KEY]:
            case MESSAGES.START_CMD:
                return self.start()
            case MESSAGES.STOP_CMD:
                return self.stop()
            case _:
                return {"status": "command_unknown"}

    def is_running(self) -> bool:
        """Check if the task is currently running."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> dict:
        """Start the task if it is not already running."""
        if self.is_running():
            return {"status": "already_running"}

        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return {"status": "started"}

    def stop(self) -> dict:
        """Stop the task if it is running."""
        if not self.is_running():
            return {"status": "not_running"}

        self._stop_evt.set()
        self._thread.join(TIMEOUT)
        return {"status": "stopped"}

    # ––– internal –––
    def _run(self):
        try:
            self._func(self._stop_evt)
        except Exception as ex:  # make sure a task crash doesn't kill the server thread
            print("CancellableTask crashed:", ex)
            traceback.print_exc()
        finally:
            # Ensure restart is possible
            self._thread = None
            self._stop_evt.set()


class NamedPipeServer:
    """Single-client, message-framed named-pipe server that survives callback errors."""

    def __init__(
        self,
        *,
        name: str = r"\\.\pipe\MatPy",
        callback: Optional[Callable[[dict], dict | None]] = None,
        bufsize: int = 65536,
    ):
        self.pipe_name = name
        self.callback = callback
        self.bufsize = bufsize
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._listen, daemon=True)

    # ––– public API –––
    def start(self):
        """Begin listening in a background thread (returns immediately)."""
        self._thread.start()

    def stop(self):
        """Request shutdown and join the thread."""
        self._stop_event.set()
        if isinstance(self.callback, CancellableTask):
            self.callback.stop()
        if self._thread.is_alive():
            self._thread.join(TIMEOUT)

    # ––– internal –––
    def _listen(self):
        while not self._stop_event.is_set():
            pipe = win32pipe.CreateNamedPipe(
                self.pipe_name,
                win32pipe.PIPE_ACCESS_DUPLEX,
                win32pipe.PIPE_TYPE_MESSAGE
                | win32pipe.PIPE_READMODE_MESSAGE
                | win32pipe.PIPE_WAIT,
                1,  # max instances
                self.bufsize,  # out-buffer
                self.bufsize,  # in-buffer
                0,
                None,
            )
            try:
                win32pipe.ConnectNamedPipe(pipe, None)
                # client loop
                while not self._stop_event.is_set():
                    try:
                        hr, raw = win32file.ReadFile(pipe, self.bufsize)
                    except pywintypes.error:
                        break  # client closed or error
                    if not raw:
                        break
                    try:
                        message = json.loads(raw.decode('utf-8'))
                    except json.JSONDecodeError as ex:
                        self._safe_write(pipe, {"error": str(ex)})
                        continue

                    reply = {"status": "ok"}
                    if self.callback:
                        try:
                            cb_reply = self.callback(message)
                            if cb_reply is not None:
                                reply = cb_reply
                        except Exception as ex:
                            print("Callback exception:", ex)
                            traceback.print_exc()
                            reply = {"error": str(ex)}
                    self._safe_write(pipe, reply)
            finally:
                win32file.CloseHandle(pipe)
                time.sleep(SLEEP_TIME)  # avoid busy loop

    # helper that never raises back to the listen loop
    def _safe_write(self, pipe, msg):
        try:
            win32file.WriteFile(pipe, json.dumps(msg).encode() + b"\n")
        except pywintypes.error:
            pass
