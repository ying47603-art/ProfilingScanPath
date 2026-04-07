"""Debug script that prints the full scan path for the cylinder reference case."""

from __future__ import annotations

from core.path_planner import generate_scan_path
from data.models import ScanParams


def main() -> None:
    """Generate and print the cylinder validation path."""

    profile_points = [(100.0, 0.0), (100.0, 100.0)]
    params = ScanParams(
        s_start=0.0,
        s_end=100.0,
        layer_step=10.0,
        water_distance=20.0,
    )

    scan_path = generate_scan_path(profile_points, params)

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


if __name__ == "__main__":
    main()
