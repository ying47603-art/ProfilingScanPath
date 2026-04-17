"""Runtime registration helpers for Qt icon resources used by the GUI."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QResource


def register_icon_resources() -> bool:
    """Register the compiled icon resource bundle for QSS and widget icons."""

    resource_path = Path(__file__).resolve().with_name("icon_img.rcc")
    if not resource_path.exists():
        return False
    return QResource.registerResource(str(resource_path))
