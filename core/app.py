"""Minimal application orchestration for the project skeleton."""

from data.models import AppInfo
from exporter.csv_exporter import CsvExporter


class ProjectApp:
    """Small runnable app object used by ``main.py``.

    The real business workflow will be added in later iterations.
    """

    def __init__(self) -> None:
        self.info = AppInfo(
            name="ProfilingScanPath",
            version="0.1.0",
            description="Python project skeleton for STEP-based path planning.",
        )
        self.csv_exporter = CsvExporter()

    def run(self) -> str:
        """Return a startup message for the runnable skeleton."""

        return (
            f"{self.info.name} {self.info.version} is ready. "
            "GUI, STEP parsing, and planning logic are TODO."
        )
