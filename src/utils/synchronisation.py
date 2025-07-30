"""Lightweight named-pipe server for MATLAB ⇄ Python experiments (Windows only).

Requires:  pywin32  (pip install pywin32)
Usage:
    from named_pipe_bridge import NamedPipeServer, CancellableTask

    # Example cancellable task
    import time
    def blink(event):
        while not event.is_set():
            print("Blink!")
            time.sleep(0.5)
            if event.is_set():
                print("Blink cancelled!")

    task = CancellableTask(blink)

    srv = NamedPipeServer(
        callback=task
    )
    srv.start()
    time.sleep(5)
    srv.stop()
"""

from __future__ import annotations
import time
import json, threading, traceback
from typing import Callable, Optional
from types import SimpleNamespace
import ctypes, ctypes.wintypes as wt
import win32pipe, win32file, pywintypes


TASK_MESSAGES = SimpleNamespace(COMMAND_KEY="cmd", START_CMD="start", STOP_CMD="stop")
SLEEP_TIME = 0.01  # seconds
TIMEOUT = 5  # seconds, for pipe connection and task stop


_CancelIoEx = ctypes.windll.kernel32.CancelIoEx
_CancelIoEx.argtypes = [wt.HANDLE, wt.LPVOID]
_CancelIoEx.restype = wt.BOOL


class CancellableTask:
    """
    Run a function in its own thread that can be started and stopped via messages.
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
        if TASK_MESSAGES.COMMAND_KEY not in message:
            return {"status": "command_missing"}
        match message[TASK_MESSAGES.COMMAND_KEY]:
            case TASK_MESSAGES.START_CMD:
                return self.start()
            case TASK_MESSAGES.STOP_CMD:
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
        self._pipe: Optional[pywintypes.HANDLE] = None

    # ––– public API –––
    def start(self):
        """Begin listening in a background thread (returns immediately)."""
        self._thread.start()

    def stop(self):
        """Request shutdown and join the thread."""

        self._stop_event.set()

        if isinstance(self.callback, CancellableTask):
            self.callback.stop()

        if self._pipe is not None:
            _CancelIoEx(int(self._pipe), None)
            self._pipe = None

        if self._thread.is_alive():
            self._thread.join(TIMEOUT)

    # ––– internal –––
    def _listen(self):
        while not self._stop_event.is_set():
            pipe = self._pipe = win32pipe.CreateNamedPipe(
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

                # Wait for messages until the stop event is set
                while not self._stop_event.is_set():

                    # Read a message from the pipe
                    try:
                        hr, raw = win32file.ReadFile(pipe, self.bufsize)
                    except pywintypes.error as e:
                        if e.winerror in (109, 232):
                            # broken pipe / no data
                            break
                        else:
                            raise

                    if not raw:
                        break

                    # Parse the message as JSON
                    try:
                        message = json.loads(raw.decode("utf-8"))
                    except json.JSONDecodeError as ex:
                        self._safe_write(pipe, {"error": str(ex)})
                        continue

                    reply = {"status": "ok"}

                    # Call the registered callback with the message
                    if self.callback is not None:
                        try:
                            cb_reply = self.callback(message)
                            if cb_reply is not None:
                                reply = cb_reply
                        except Exception as ex:
                            print("Callback exception:", ex)
                            traceback.print_exc()
                            reply = {"error": str(ex)}

                    # Send the reply back to the client
                    self._safe_write(pipe, reply)

            except pywintypes.error as e:
                if e.winerror == 995 and self._stop_event.is_set():
                    # operation aborted
                    break
                raise

            finally:
                win32file.CloseHandle(pipe)
                self._pipe = None

            time.sleep(SLEEP_TIME)  # avoid busy loop

    # helper that never raises back to the listen loop
    def _safe_write(self, pipe, msg):
        try:
            win32file.WriteFile(pipe, json.dumps(msg).encode() + b"\n")
        except pywintypes.error:
            pass
