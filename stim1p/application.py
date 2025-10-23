from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QWidget

from .ui.dmd_stim_widget import StimDMDWidget


def _resources_dir() -> Path:
    return Path(__file__).resolve().parent / "ui" / "ressources"


def _load_app_icon() -> QIcon:
    resources_dir = _resources_dir()
    icon_filename = "stim1p.ico" if sys.platform.startswith("win") else "stim1p.png"
    icon_path = resources_dir / icon_filename
    icon = QIcon(str(icon_path))
    return icon


def _apply_icon_to_widget(widget: QWidget, icon: QIcon) -> None:
    """Ensure the icon propagates to both QWidget and underlying QWindow."""
    widget.setWindowIcon(icon)

    def _apply_to_window():
        handle = widget.windowHandle()
        if handle is not None:
            handle.setIcon(icon)
        elif widget.isVisible():
            QTimer.singleShot(0, _apply_to_window)

    QTimer.singleShot(0, _apply_to_window)


def create_application(argv: Sequence[str]) -> tuple[QApplication, QIcon]:
    app = QApplication(argv)
    icon = _load_app_icon()
    app.setWindowIcon(icon)
    return app, icon


def create_main_widget(icon: QIcon) -> StimDMDWidget:
    widget = StimDMDWidget()
    _apply_icon_to_widget(widget, icon)
    return widget


def run(argv: Sequence[str] | None = None) -> int:
    """Entry point used by the CLI launcher and tests."""
    argv = argv if argv is not None else sys.argv
    app, icon = create_application(argv)
    widget = create_main_widget(icon)
    widget.showMaximized()
    return app.exec()
