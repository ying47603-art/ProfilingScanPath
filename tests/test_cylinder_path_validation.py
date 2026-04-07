"""Validation test for the standard cylinder scan path."""

from __future__ import annotations

import math

from core.path_planner import generate_scan_path
from data.models import ScanParams


def test_cylinder_standard_part_path_matches_theoretical_values() -> None:
    """A cylinder profile should produce the expected layered scan path."""

    profile_points = [(100.0, 0.0), (100.0, 100.0)]
    params = ScanParams(
        s_start=0.0,
        s_end=100.0,
        layer_step=10.0,
        water_distance=20.0,
    )

    scan_path = generate_scan_path(profile_points, params)

    assert len(scan_path.points) == 11
    assert [point.layer_index for point in scan_path.points] == list(range(11))

    for index, point in enumerate(scan_path.points):
        expected_z = float(index * 10)

        assert math.isclose(point.arc_length, expected_z, abs_tol=1e-9)
        assert math.isclose(point.surface_x, 100.0, abs_tol=1e-9)
        assert math.isclose(point.surface_z, expected_z, abs_tol=1e-9)
        assert math.isclose(point.probe_x, 120.0, abs_tol=1e-9)
        assert math.isclose(point.probe_y, 0.0, abs_tol=1e-9)
        assert math.isclose(point.probe_z, expected_z, abs_tol=1e-9)
        assert math.isclose(point.tilt_angle_deg, 90.0, abs_tol=1e-9)
