"""Popup window for 3D display settings."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget

from gui.ui.generated.ui_displaysetwindow import Ui_DisplaySetWindow


class DisplaySetWindow(QWidget):
    """Lightweight popup used to edit 3D display settings."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the generated display-settings window."""

        super().__init__(parent)
        self.ui = Ui_DisplaySetWindow()
        self.ui.setupUi(self)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
