"""High-level debug script for the OCP-first STEP to scan-path chain.

Always run this script with the profiling-ocp interpreter, for example:
    & 'C:\\ProgramData\\Anaconda3\\envs\\profiling-ocp\\python.exe' scripts\\debug_ocp_profile.py tests\\fixtures\\ocp_fillet.step
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.model_normalizer import normalize_revolved_model
from core.path_planner import compute_arc_length, generate_scan_path
from core.profile_extractor import extract_profile_points
from core.step_loader import load_step_model
from data.models import PathPoint, ScanParams
from exporter.csv_exporter import CsvExporter


def main() -> int:
    """Run the STEP -> profile -> scan-path debug pipeline."""

    args = _parse_args()
    step_file = args.step_file.resolve()

    model = load_step_model(step_file)
    normalized_model = normalize_revolved_model(model)
    profile_points = extract_profile_points(normalized_model, num_samples=args.samples)

    total_arc_length = compute_arc_length(profile_points)[-1]
    s_end = args.s_end if args.s_end is not None else total_arc_length

    scan_params = ScanParams(
        s_start=args.s_start,
        s_end=s_end,
        layer_step=args.layer_step,
        water_distance=args.water_distance,
    )
    scan_path = generate_scan_path(profile_points, scan_params)

    _print_loader_summary(model)
    _print_normalized_summary(normalized_model)
    _print_profile_summary(profile_points)
    _print_scan_path_summary(scan_path.points)

    if args.export_csv:
        exported_files = _export_debug_csvs(
            output_dir=args.output_dir.resolve(),
            profile_points=profile_points,
            scan_points=scan_path.points,
        )
        print("csv_exports=")
        for exported_file in exported_files:
            print(f"  {exported_file}")

    return 0


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the debug script."""

    parser = argparse.ArgumentParser(
        description="Run the OCP-first STEP -> profile -> scan-path debug pipeline.",
    )
    parser.add_argument("step_file", type=Path, help="Path to the STEP file.")
    parser.add_argument("--samples", type=int, default=200, help="Number of profile samples to extract.")
    parser.add_argument("--s-start", type=float, default=0.0, help="Scan start arc length.")
    parser.add_argument(
        "--s-end",
        type=float,
        default=None,
        help="Scan end arc length. Defaults to the extracted discrete profile arc length.",
    )
    parser.add_argument("--layer-step", type=float, default=2.0, help="Layer step for path planning.")
    parser.add_argument("--water-distance", type=float, default=20.0, help="Water distance for path planning.")
    parser.add_argument("--export-csv", action="store_true", help="Export profile points and scan path CSV files.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT_DIR / "output",
        help="Directory used when --export-csv is enabled.",
    )
    return parser.parse_args()


def _print_loader_summary(model) -> None:
    """Print summary information about STEP loading."""

    print("loader_summary=")
    print(f"  step_file={model.file_path}")
    print(f"  loader_backend={model.loader_backend}")
    print(f"  has_ocp_shape={model.ocp_shape is not None}")
    print(f"  cartesian_point_count={len(model.cartesian_points)}")
    print(f"  axis_placement_count={len(model.axis_placements)}")


def _print_normalized_summary(normalized_model) -> None:
    """Print summary information about normalization."""

    print("normalized_summary=")
    print(f"  axis_origin={normalized_model.axis_origin}")
    print(f"  axis_direction={normalized_model.axis_direction}")
    print(f"  has_ocp_shape={normalized_model.ocp_shape is not None}")
    print(f"  fallback_point_count={len(normalized_model.points_3d)}")


def _print_profile_summary(profile_points: Sequence[tuple[float, float]]) -> None:
    """Print summary information about extracted profile points."""

    x_values = [point[0] for point in profile_points]
    z_values = [point[1] for point in profile_points]

    print("profile_summary=")
    print(f"  point_count={len(profile_points)}")
    print(f"  min_x={min(x_values):.6f}")
    print(f"  max_x={max(x_values):.6f}")
    print(f"  min_z={min(z_values):.6f}")
    print(f"  max_z={max(z_values):.6f}")
    print("  first_10_points=")
    for point in profile_points[:10]:
        print(f"    ({point[0]:.6f}, {point[1]:.6f})")
    print("  last_10_points=")
    for point in profile_points[-10:]:
        print(f"    ({point[0]:.6f}, {point[1]:.6f})")


def _print_scan_path_summary(scan_points: Sequence[PathPoint]) -> None:
    """Print summary information about the generated scan path."""

    angle_values = [point.tilt_angle_deg for point in scan_points]

    print("scan_path_summary=")
    print(f"  point_count={len(scan_points)}")
    print(f"  min_angle={min(angle_values):.6f}")
    print(f"  max_angle={max(angle_values):.6f}")
    print("  first_10_points=")
    for point in scan_points[:10]:
        print(f"    {_format_path_point(point)}")
    print("  last_10_points=")
    for point in scan_points[-10:]:
        print(f"    {_format_path_point(point)}")


def _format_path_point(point: PathPoint) -> str:
    """Format a path point for human-readable debug output."""

    return (
        f"layer_index={point.layer_index}, arc_length={point.arc_length:.6f}, "
        f"surface_x={point.surface_x:.6f}, surface_z={point.surface_z:.6f}, "
        f"probe_x={point.probe_x:.6f}, probe_y={point.probe_y:.6f}, "
        f"probe_z={point.probe_z:.6f}, tilt_angle_deg={point.tilt_angle_deg:.6f}"
    )


def _export_debug_csvs(
    output_dir: Path,
    profile_points: Sequence[tuple[float, float]],
    scan_points: Sequence[PathPoint],
) -> list[Path]:
    """Export the extracted profile points and generated scan path to CSV files."""

    output_dir.mkdir(parents=True, exist_ok=True)
    exporter = CsvExporter()

    profile_file = exporter.export_rows(
        rows=_profile_rows(profile_points),
        target_file=output_dir / "profile_points.csv",
    )
    standard_file = exporter.export_rows(
        rows=_standard_scan_rows(scan_points),
        target_file=output_dir / "scan_path_standard.csv",
    )
    compact_file = exporter.export_rows(
        rows=_compact_scan_rows(scan_points),
        target_file=output_dir / "scan_path_compact.csv",
    )

    return [profile_file, standard_file, compact_file]


def _profile_rows(profile_points: Sequence[tuple[float, float]]) -> list[dict[str, float]]:
    """Convert profile points into CSV-exportable rows."""

    return [{"x": float(point_x), "z": float(point_z)} for point_x, point_z in profile_points]


def _standard_scan_rows(scan_points: Sequence[PathPoint]) -> list[dict[str, float]]:
    """Convert scan points into the standard CSV row format."""

    return [
        {
            "layer_index": float(point.layer_index),
            "arc_length": float(point.arc_length),
            "surface_x": float(point.surface_x),
            "surface_z": float(point.surface_z),
            "probe_x": float(point.probe_x),
            "probe_y": float(point.probe_y),
            "probe_z": float(point.probe_z),
            "tilt_angle_deg": float(point.tilt_angle_deg),
        }
        for point in scan_points
    ]


def _compact_scan_rows(scan_points: Sequence[PathPoint]) -> list[dict[str, float]]:
    """Convert scan points into the compact CSV row format."""

    return [
        {
            "X": float(point.probe_x),
            "Y": float(point.probe_y),
            "Z": float(point.probe_z),
            "Angle": float(point.tilt_angle_deg),
        }
        for point in scan_points
    ]


if __name__ == "__main__":
    raise SystemExit(main())
