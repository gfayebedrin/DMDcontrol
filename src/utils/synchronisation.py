"""Lightweight named-pipe server for MATLAB ⇄ Python experiments (Windows only).

Requires:  pywin32  (pip install pywin32)
Usage:
    from named_pipe_bridge import NamedPipeServer, CancellableTask

    # Example cancellable task
    import time
    def blink():
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
import json, threading, traceback
from typing import Callable, Literal, Optional

import win32pipe, win32file, pywintypes


class CancellableTask:
    """Run a function in its own thread that can be started and stopped via pipe messages."""

    def __init__(self, func: Callable[[], None]):
        self._func = func
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()

    def __call__(self, message: Literal["start", "stop"]):
        match message:
            case "start":
                if self._thread and self._thread.is_alive():
                    return {"status": "already_running"}
                self._stop_evt.clear()
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()
                return {"status": "started"}
            case "stop":
                if not self._thread or not self._thread.is_alive():
                    return {"status": "not_running"}
                self._stop_evt.set()
                self._thread.join()
                return {"status": "stopped"}
            case _:
                raise ValueError(f"Unknown message: {message}")

    # ––– internal –––
    def _run(self):
        try:
            self._func()
        except Exception as ex:  # make sure a task crash doesn't kill the server thread
            print("CancellableTask crashed:", ex)
            traceback.print_exc()


class NamedPipeServer:
    """Single‑client, message‑framed named‑pipe server that survives callback errors."""

    def __init__(self, *, name: str = r"\\.\pipe\MatPy", callback=None, bufsize: int = 65536):
        self.pipe_name = name
        self.callback = callback  # Python callable (dict → dict | None)
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
        self._thread.join()

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
                self.bufsize,  # out‑buffer
                self.bufsize,  # in‑buffer
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
                        message = json.loads(raw.decode())
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

    # helper that never raises back to the listen loop
    def _safe_write(self, pipe, msg):
        try:
            win32file.WriteFile(pipe, json.dumps(msg).encode())
        except pywintypes.error:
            pass