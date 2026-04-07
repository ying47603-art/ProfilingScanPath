"""CSV export service for ProfilingScanPath V1."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, Iterable, List

from profiling_scan_path.domain.models import CsvFormat, PathPoint


STANDARD_HEADERS: List[str] = [
    "layer_index",
    "surface_arc_length",
    "probe_x",
    "probe_y",
    "probe_z",
    "tilt_angle_deg",
    "surface_x",
    "surface_z",
    "water_distance",
]

COMPACT_HEADERS: List[str] = [
    "layer_index",
    "probe_x",
    "probe_y",
    "probe_z",
    "tilt_angle_deg",
]


class CsvExporter:
    """Exports path points to standard or compact CSV files."""

    def export(
        self,
        points: Iterable[PathPoint],
        target_file: Path,
        csv_format: CsvFormat,
    ) -> Path:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        rows = [self._to_row(point, csv_format) for point in points]
        headers = self._headers_for(csv_format)

        with target_file.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

        return target_file

    def _headers_for(self, csv_format: CsvFormat) -> List[str]:
        if csv_format == CsvFormat.STANDARD:
            return STANDARD_HEADERS
        if csv_format == CsvFormat.COMPACT:
            return COMPACT_HEADERS
        raise ValueError(f"Unsupported CSV format: {csv_format}")

    def _to_row(self, point: PathPoint, csv_format: CsvFormat) -> Dict[str, float]:
        standard_row: Dict[str, float] = {
            "layer_index": point.layer_index,
            "surface_arc_length": point.surface_arc_length,
            "probe_x": point.probe_x,
            "probe_y": point.probe_y,
            "probe_z": point.probe_z,
            "tilt_angle_deg": point.tilt_angle_deg,
            "surface_x": point.surface_x,
            "surface_z": point.surface_z,
            "water_distance": point.water_distance,
        }

        if csv_format == CsvFormat.STANDARD:
            return standard_row
        if csv_format == CsvFormat.COMPACT:
            return {key: standard_row[key] for key in COMPACT_HEADERS}
        raise ValueError(f"Unsupported CSV format: {csv_format}")
