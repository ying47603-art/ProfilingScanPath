"""Debug script that prints the full scan path for the cone reference case."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.path_planner import generate_scan_path
from data.models import ScanParams


def main() -> None:
    """Generate and print the cone validation path."""

    profile_points = [
        (100.0, 0.0),
        (50.0, 100.0),
    ]
    params = ScanParams(
        s_start=0.0,
        s_end=111.80339887498948,
        layer_step=10.0,
        water_distance=20.0,
    )

    scan_path = generate_scan_path(profile_points, params)

    header = (
        "layer_index, arc_length, surface_x, surface_z, "
        "probe_x, probe_y, probe_z, tilt_angle_deg"
    )
    print(header)
    for point in scan_path.points:
        print(
            f"{point.layer_index:02d}, "
            f"{point.arc_length:10.6f}, "
            f"{point.surface_x:10.6f}, "
            f"{point.surface_z:10.6f}, "
            f"{point.probe_x:10.6f}, "
            f"{point.probe_y:10.6f}, "
            f"{point.probe_z:10.6f}, "
            f"{point.tilt_angle_deg:10.6f}"
        )


if __name__ == "__main__":
    main()
