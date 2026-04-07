"""Minimal application flow for ProfilingScanPath V1."""

from __future__ import annotations

from pathlib import Path
from typing import List

from profiling_scan_path.domain.models import CsvFormat, ExportBundle, PathPoint, ScanPlanInput
from profiling_scan_path.services.csv_exporter import CsvExporter


def build_demo_scan_input(step_file: Path) -> ScanPlanInput:
    """Create a deterministic demo input for the runnable V1 skeleton."""

    return ScanPlanInput(
        step_file=step_file,
        s_start=0.0,
        s_end=20.0,
        layer_step=2.0,
        water_distance=15.0,
    )


def build_demo_points(scan_input: ScanPlanInput) -> List[PathPoint]:
    """Create sample points to validate the export pipeline end to end.

    TODO: Replace with output from StepModelService + LayeredPathPlanner.
    """

    return [
        PathPoint(
            layer_index=0,
            surface_arc_length=scan_input.s_start,
            probe_x=10.0,
            probe_y=0.0,
            probe_z=100.0,
            tilt_angle_deg=5.0,
            surface_x=8.7,
            surface_z=86.5,
            water_distance=scan_input.water_distance,
        ),
        PathPoint(
            layer_index=1,
            surface_arc_length=scan_input.s_start + scan_input.layer_step,
            probe_x=12.5,
            probe_y=0.0,
            probe_z=102.0,
            tilt_angle_deg=6.5,
            surface_x=11.1,
            surface_z=87.0,
            water_distance=scan_input.water_distance,
        ),
    ]


def export_demo_bundle(output_dir: Path) -> ExportBundle:
    """Export both CSV formats for the demo data."""

    output_dir.mkdir(parents=True, exist_ok=True)
    scan_input = build_demo_scan_input(step_file=Path("demo.step"))
    points = build_demo_points(scan_input)
    exporter = CsvExporter()

    standard_csv = exporter.export(
        points=points,
        target_file=output_dir / "scan_path_standard.csv",
        csv_format=CsvFormat.STANDARD,
    )
    compact_csv = exporter.export(
        points=points,
        target_file=output_dir / "scan_path_compact.csv",
        csv_format=CsvFormat.COMPACT,
    )
    return ExportBundle(standard_csv=standard_csv, compact_csv=compact_csv)
