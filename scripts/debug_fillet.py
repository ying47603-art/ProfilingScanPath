"""Debug script that prints the full scan path for the fillet transition case."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.path_planner import compute_arc_length, generate_scan_path
from data.models import ScanParams


ProfilePoint = Tuple[float, float]


def build_fillet_profile_points(sample_count: int = 21) -> List[ProfilePoint]:
    """Build a cylinder plus quarter-fillet profile in the XZ plane."""

    if sample_count < 20:
        raise ValueError("sample_count must be >= 20")

    points: List[ProfilePoint] = [
        (100.0, 0.0),
        (100.0, 60.0),
    ]

    for index in range(1, sample_count):
        phi = (math.pi / 2.0) * index / (sample_count - 1)
        x = 80.0 + 20.0 * math.cos(phi)
        z = 60.0 + 20.0 * math.sin(phi)
        points.append((x, z))

    return points


def main() -> None:
    """Generate and print the fillet validation path."""

    profile_points = build_fillet_profile_points()
    total_arc_length = compute_arc_length(profile_points)[-1]
    params = ScanParams(
        s_start=0.0,
        s_end=total_arc_length,
        layer_step=2.0,
        water_distance=20.0,
    )

    scan_path = generate_scan_path(profile_points, params)
    angles = [point.tilt_angle_deg for point in scan_path.points]

    print(
        "layer_index,arc_length,surface_x,surface_z,"
        "probe_x,probe_y,probe_z,tilt_angle_deg"
    )
    for point in scan_path.points:
        print(
            f"{point.layer_index},"
            f"{point.arc_length:.6f},"
            f"{point.surface_x:.6f},"
            f"{point.surface_z:.6f},"
            f"{point.probe_x:.6f},"
            f"{point.probe_y:.6f},"
            f"{point.probe_z:.6f},"
            f"{point.tilt_angle_deg:.6f}"
        )

    print(f"max_angle_deg={max(angles):.6f}")
    print(f"min_angle_deg={min(angles):.6f}")
    print(f"total_layers={len(scan_path.points)}")


if __name__ == "__main__":
    main()
