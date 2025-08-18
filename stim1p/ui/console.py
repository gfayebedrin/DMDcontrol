import sys

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtGui import QTextCharFormat, QTextCursor, QFont

import re

# Strip common ANSI escape sequences: CSI (e.g. \x1b[31m), OSC (e.g. hyperlinks), and ST/BEL terminators
ANSI_RE = re.compile(
    r"""
    (?:\x1b\[[0-9;?]*[ -/]*[@-~])      # CSI ... cmd
  | (?:\x1b\][^\x07\x1b]*(?:\x07|\x1b\\))  # OSC ... BEL or ST
  | (?:\x1b[@-Z\\-_])                  # 2-byte escapes
    """,
    re.VERBOSE,
)


class QtTee(QObject):
    """A stream that forwards writes to the original stream and also emits a signal for the UI."""

    textWritten = Signal(str, bool)  # (text, is_err)

    def __init__(self, orig_stream, is_err=False):
        super().__init__()
        self._orig = orig_stream
        self._is_err = is_err
        # mirror common attributes for compatibility
        self.encoding = getattr(orig_stream, "encoding", "utf-8")

    def write(self, text: str):
        # pass-through to original stream
        self._orig.write(text)
        self._orig.flush()
        # also emit to UI
        if text:
            self.textWritten.emit(text, self._is_err)

    def flush(self):
        self._orig.flush()

    # optional niceties
    def isatty(self):
        return getattr(self._orig, "isatty", lambda: False)()

    def writable(self):
        return True

    def fileno(self):
        return getattr(self._orig, "fileno", lambda: -1)()


class Console:
    """
    Console class to manage DMD console output.
    It redirects standard output and error streams to a QPlainTextEdit widget.
    """

    def __init__(self, plain_text_edit: QPlainTextEdit):
        self.ui = plain_text_edit
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr

        # graphical
        self.ui.setReadOnly(True)
        self.ui.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Courier New")
        font.setStyleHint(QFont.Monospace)
        self.ui.setFont(font)

        # create tees (they forward to originals AND emit to the UI)
        self._tee_out = QtTee(self._orig_stdout, is_err=False)
        self._tee_err = QtTee(self._orig_stderr, is_err=True)

        # connect signals so UI updates happen in the GUI thread
        self._tee_out.textWritten.connect(self.append_console_text)
        self._tee_err.textWritten.connect(self.append_console_text)

        # replace sys streams with tees (console still works via forward)
        sys.stdout = self._tee_out
        sys.stderr = self._tee_err

    def __del__(self):
        """Restore original streams on deletion."""
        self.restore_original_streams()

    def restore_original_streams(self):
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr

    def append_console_text(self, text: str, is_err: bool):

        # 1) remove ANSI escapes
        cleaned = ANSI_RE.sub("", text)

        # 2) normalize CR-only progress lines (e.g. "xxx\ryyy")
        #    keep only the last carriage-return segment
        if "\r" in cleaned and "\n" not in cleaned:
            cleaned = cleaned.split("\r")[-1]

        if is_err:
            cursor = self.ui.textCursor()
            cursor.movePosition(QTextCursor.End)
            fmt = QTextCharFormat()
            fmt.setForeground(Qt.red)
            cursor.mergeCharFormat(fmt)
            cursor.insertText(cleaned)
            cursor.mergeCharFormat(QTextCharFormat())  # reset
            self.ui.setTextCursor(cursor)
        else:
            if cleaned.endswith("\n"):
                self.ui.appendPlainText(cleaned[:-1])
            else:
                self.ui.appendPlainText(cleaned)
