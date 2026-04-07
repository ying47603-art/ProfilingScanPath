"""PyQt6 application bootstrap for ProfilingScanPath."""

from __future__ import annotations

from typing import Sequence

from PyQt6.QtWidgets import QApplication

from gui.controller import GuiController
from gui.main_window import MainWindow


def run_app(argv: Sequence[str]) -> int:
    """Create and run the PyQt6 application."""

    app = QApplication(list(argv))
    controller = GuiController()
    window = MainWindow(controller)
    window.show()
    return app.exec()
