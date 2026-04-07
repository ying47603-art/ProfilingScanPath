"""Validation tests for a cylinder-to-fillet transition profile."""

from __future__ import annotations

import math
from typing import List, Tuple

import pytest

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


def _build_scan_path():
    """Create the shared scan path for the fillet validation case."""

    profile_points = build_fillet_profile_points()
    total_arc_length = compute_arc_length(profile_points)[-1]
    params = ScanParams(
        s_start=0.0,
        # The sampled fillet is a polyline approximation of the quarter arc,
        # so its discrete total arc length is slightly smaller than 60 + 10*pi.
        s_end=total_arc_length,
        layer_step=2.0,
        water_distance=20.0,
    )
    return generate_scan_path(profile_points, params)


def test_probe_y_is_zero_for_all_layers() -> None:
    """All probe points should remain on the Y=0 plane."""

    scan_path = _build_scan_path()

    assert [point.probe_y for point in scan_path.points] == pytest.approx([0.0] * len(scan_path.points))


def test_cylinder_segment_keeps_constant_x_and_ninety_degree_tilt() -> None:
    """The cylinder segment should stay at x=100 with a 90-degree tilt."""

    scan_path = _build_scan_path()
    cylinder_points = [point for point in scan_path.points if point.surface_z <= 60.0 + 1e-6]

    assert cylinder_points
    for point in cylinder_points:
        assert point.surface_x == pytest.approx(100.0, abs=1e-6)
        assert point.tilt_angle_deg == pytest.approx(90.0, abs=1.0)


def test_fillet_segment_tilt_decreases_continuously() -> None:
    """The fillet segment should smoothly reduce tilt from 90 toward 0 degrees."""

    scan_path = _build_scan_path()
    fillet_points = [point for point in scan_path.points if point.surface_z > 60.0 + 1e-6]
    fillet_angles = [point.tilt_angle_deg for point in fillet_points]

    assert fillet_points
    assert fillet_angles[0] < 90.0
    assert fillet_angles[-1] <= 5.0

    for left, right in zip(fillet_angles, fillet_angles[1:]):
        assert right <= left + 1.0
        assert abs(right - left) < 15.0


def test_fillet_end_angle_is_close_to_zero() -> None:
    """The smallest angle near the fillet end should approach 0 degrees."""

    scan_path = _build_scan_path()
    min_angle = min(point.tilt_angle_deg for point in scan_path.points)

    assert min_angle == pytest.approx(0.0, abs=5.0)


def test_fillet_surface_points_lie_on_expected_arc() -> None:
    """Fillet surface points should satisfy the quarter-circle equation."""

    scan_path = _build_scan_path()
    fillet_points = [point for point in scan_path.points if point.surface_z > 60.0 + 1e-6]

    assert fillet_points
    for point in fillet_points:
        radius_sq = (point.surface_x - 80.0) ** 2 + (point.surface_z - 60.0) ** 2
        assert radius_sq == pytest.approx(20.0 ** 2, abs=2.0)


def test_arc_length_is_monotonic_increasing() -> None:
    """Arc length should increase monotonically along the full path."""

    scan_path = _build_scan_path()
    arc_lengths = [point.arc_length for point in scan_path.points]

    for left, right in zip(arc_lengths, arc_lengths[1:]):
        assert right > left
