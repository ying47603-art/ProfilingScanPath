"""PyQt6 application bootstrap for ProfilingScanPath."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PyQt6.QtWidgets import QApplication

from gui.controller import GuiController
from gui.icon_resources import register_icon_resources
from gui.main_window import MainWindow


def _load_global_stylesheet(app: QApplication) -> None:
    """Load the shared light-theme stylesheet without blocking application startup on failure."""

    stylesheet_path = Path(__file__).resolve().parent / "styles" / "light_theme.qss"
    try:
        stylesheet_text = stylesheet_path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"[UI_DEBUG] failed to load stylesheet: {stylesheet_path} reason={exc}")
        return

    app.setStyleSheet(stylesheet_text)
    print(f"[UI_DEBUG] loaded stylesheet: {stylesheet_path}")


def run_app(argv: Sequence[str]) -> int:
    """Create and run the PyQt6 application."""

    app = QApplication(list(argv))
    if register_icon_resources():
        print("[UI_DEBUG] registered icon resources: gui/icon_img.rcc")
    else:
        print("[UI_DEBUG] failed to register icon resources: gui/icon_img.rcc")
    _load_global_stylesheet(app)
    controller = GuiController()
    window = MainWindow(controller)
    window.show()
    return app.exec()
