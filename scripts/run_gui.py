"""Launch the PyQt6 GUI prototype.

Run with the profiling-ocp interpreter:
    & 'C:\\ProgramData\\Anaconda3\\envs\\profiling-ocp\\python.exe' scripts\\run_gui.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from gui.app import run_app


def main() -> int:
    """Start the GUI application."""

    return run_app(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
