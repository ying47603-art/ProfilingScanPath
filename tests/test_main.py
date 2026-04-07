"""Tests for the minimal project skeleton."""

from pathlib import Path

from core.app import ProjectApp
from exporter.csv_exporter import CsvExporter
from main import main


def test_main_returns_success_code() -> None:
    assert main() == 0


def test_project_app_returns_readable_message() -> None:
    message = ProjectApp().run()
    assert "ProfilingScanPath" in message
    assert "TODO" in message


def test_csv_exporter_can_write_simple_file(tmp_path: Path) -> None:
    target = tmp_path / "sample.csv"
    result = CsvExporter().export_rows(
        rows=[{"name": "demo", "value": 1}],
        target_file=target,
    )

    assert result.exists()
    assert result.read_text(encoding="utf-8-sig").splitlines()[0] == "name,value"
