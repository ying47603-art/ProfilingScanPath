"""CSV exporter skeleton.

This module only provides a lightweight interface for future export logic.
"""

from pathlib import Path
from typing import Iterable, Mapping
import csv


class CsvExporter:
    """Small utility kept intentionally simple for the initial project skeleton."""

    def export_rows(
        self,
        rows: Iterable[Mapping[str, object]],
        target_file: Path,
    ) -> Path:
        """Export rows to CSV.

        TODO: Replace this helper with the real ultrasonic path CSV formats.
        """

        row_list = list(rows)
        target_file.parent.mkdir(parents=True, exist_ok=True)

        if not row_list:
            target_file.write_text("", encoding="utf-8")
            return target_file

        headers = list(row_list[0].keys())
        with target_file.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(row_list)
        return target_file
