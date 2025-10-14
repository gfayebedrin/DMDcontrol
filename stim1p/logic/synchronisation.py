"""Lightweight named-pipe server for MATLAB ⇄ Python experiments.

The helpers in this module are only available on Windows hosts with the
``pywin32`` package installed. On other platforms the module still imports so
clients can access the rest of the :mod:`stim1p` package without optional
dependencies, but attempting to construct :class:`NamedPipeServer` will raise a
clear error explaining the requirements.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from typing import Callable, Optional

SLEEP_TIME = 0.01  # seconds
TIMEOUT = 5  # seconds, for pipe connection and task stop

NAMED_PIPE_SUPPORTED = False
NAMED_PIPE_UNAVAILABLE_REASON: str | None = None

if sys.platform.startswith("win"):
    try:
        import ctypes
        import ctypes.wintypes as wt
        import win32file  # type: ignore
        import win32pipe  # type: ignore
        import pywintypes  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised on systems w/o deps
        NAMED_PIPE_UNAVAILABLE_REASON = (
            "Windows named pipes require the 'pywin32' package (pip install pywin32): "
            f"{exc}"
        )
    else:
        NAMED_PIPE_SUPPORTED = True
        NAMED_PIPE_UNAVAILABLE_REASON = None

        _CancelIoEx = ctypes.windll.kernel32.CancelIoEx
        _CancelIoEx.argtypes = [wt.HANDLE, wt.LPVOID]
        _CancelIoEx.restype = wt.BOOL
else:  # pragma: no cover - depends on runtime platform
    NAMED_PIPE_UNAVAILABLE_REASON = "Named pipes are only supported on Windows."


class CancellableTask:
    """Run a function in its own thread that can be started and stopped."""

    def __init__(
        self,
        func: Callable[[threading.Event], None],
        *,
        command_key: str = "cmd",
        start_cmd: str = "start",
        stop_cmd: str = "stop",
    ):
        """Initialise the task with a function that accepts a ``threading.Event``."""

        self._func = func
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._command_key = command_key
        self._start_cmd = start_cmd
        self._stop_cmd = stop_cmd

    def __call__(self, message: dict) -> dict:
        """Handle incoming messages to control the task."""

        if self._command_key not in message:
            return {"status": "command_missing"}
        match message[self._command_key]:
            case self._start_cmd:
                return self.start()
            case self._stop_cmd:
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
        self._thread.join(TIMEOUT)  # pyright: ignore[reportOptionalMemberAccess]
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


if NAMED_PIPE_SUPPORTED:

    class NamedPipeServer:
        """Single-client, message-framed named-pipe server resilient to errors."""

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
            self._thread: Optional[threading.Thread] = None
            self._pipe: Optional[int] = None

        # ––– public API –––
        def is_alive(self) -> bool:
            """Check if the server thread is running."""

            return self._thread is not None and self._thread.is_alive()

        def start(self):
            """Begin listening in a background thread (returns immediately)."""

            if self.is_alive():
                raise RuntimeError("Server is already running.")

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._listen, daemon=True)
            self._thread.start()

        def stop(self):
            """Request shutdown and join the thread."""

            self._stop_event.set()

            if isinstance(self.callback, CancellableTask):
                self.callback.stop()

            if self._pipe is not None:
                _CancelIoEx(self._pipe, None)
                self._pipe = None

            if self.is_alive():
                self._thread.join(TIMEOUT)  # pyright: ignore[reportOptionalMemberAccess]

            self._thread = None

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
                    None,  # pyright: ignore[reportArgumentType]
                )

                try:
                    win32pipe.ConnectNamedPipe(pipe, None)

                    # Wait for messages until the stop event is set
                    while not self._stop_event.is_set():
                        _, raw = win32file.ReadFile(pipe, self.bufsize)

                        if not raw:
                            break

                        # Parse the message as JSON
                        try:
                            message = json.loads(raw)
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
                    if e.winerror in (109, 232):
                        # broken pipe / no data
                        continue
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


else:

    class NamedPipeServer:
        """Placeholder used when Windows named-pipe support is unavailable."""

        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            reason = NAMED_PIPE_UNAVAILABLE_REASON or "Named pipes are unavailable."
            raise RuntimeError(reason)

        def is_alive(self) -> bool:  # pragma: no cover - simple stub
            return False

        def start(self):  # pragma: no cover - simple stub
            reason = NAMED_PIPE_UNAVAILABLE_REASON or "Named pipes are unavailable."
            raise RuntimeError(reason)

        def stop(self):  # pragma: no cover - simple stub
            return None
