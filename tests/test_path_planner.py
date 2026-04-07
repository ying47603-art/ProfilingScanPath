"""Tests for the V1 core path planner."""

from __future__ import annotations

import math

import pytest

from core.path_planner import compute_arc_length, compute_normal, generate_scan_path
from data.models import ScanParams


def test_generate_scan_path_for_vertical_profile() -> None:
    """A cylinder-like vertical profile should yield +X outward normals."""

    profile_points = [(10.0, 0.0), (10.0, 20.0)]
    params = ScanParams(
        s_start=0.0,
        s_end=20.0,
        layer_step=10.0,
        water_distance=5.0,
    )

    scan_path = generate_scan_path(profile_points, params)

    assert len(scan_path.points) == 3
    assert [point.layer_index for point in scan_path.points] == [0, 1, 2]
    assert all(point.probe_y == 0.0 for point in scan_path.points)
    assert all(math.isclose(point.tilt_angle_deg, 90.0, abs_tol=1e-6) for point in scan_path.points)
    assert math.isclose(scan_path.points[0].probe_x, 15.0, abs_tol=1e-6)


def test_generate_scan_path_for_sloped_profile_has_expected_angle() -> None:
    """A cone-like sloped profile should follow the atan2(nx, nz) definition."""

    profile_points = [(5.0, 0.0), (10.0, 10.0)]
    params = ScanParams(
        s_start=0.0,
        s_end=math.hypot(5.0, 10.0),
        layer_step=math.hypot(5.0, 10.0) / 2.0,
        water_distance=2.0,
    )

    scan_path = generate_scan_path(profile_points, params)
    expected_angle = math.degrees(math.atan2(10.0 / math.hypot(5.0, 10.0), -5.0 / math.hypot(5.0, 10.0)))

    assert len(scan_path.points) == 3
    assert all(math.isclose(point.tilt_angle_deg, expected_angle, abs_tol=1e-6) for point in scan_path.points)
    assert scan_path.points[0].probe_x > scan_path.points[0].surface_x


def test_generate_scan_path_supports_full_arc_range() -> None:
    """The planner should include both start and end layers on the full arc range."""

    profile_points = [(10.0, 0.0), (10.0, 20.0)]
    total_arc_length = compute_arc_length(profile_points)[-1]
    params = ScanParams(
        s_start=0.0,
        s_end=total_arc_length,
        layer_step=5.0,
        water_distance=3.0,
    )

    scan_path = generate_scan_path(profile_points, params)

    assert len(scan_path.points) == 5
    assert math.isclose(scan_path.points[0].arc_length, 0.0, abs_tol=1e-6)
    assert math.isclose(scan_path.points[-1].arc_length, total_arc_length, abs_tol=1e-6)


def test_generate_scan_path_rejects_invalid_params() -> None:
    """The planner should raise ValueError for invalid scan parameters."""

    profile_points = [(10.0, 0.0), (10.0, 20.0)]
    params = ScanParams(
        s_start=0.0,
        s_end=10.0,
        layer_step=0.0,
        water_distance=3.0,
    )

    with pytest.raises(ValueError):
        generate_scan_path(profile_points, params)


def test_compute_normal_uses_one_sided_difference_near_endpoints() -> None:
    """Endpoint-adjacent normals should remain stable with one-sided differences."""

    profile_points = [(5.0, 0.0), (7.0, 4.0), (10.0, 10.0)]
    arc_lengths = compute_arc_length(profile_points)

    start_normal = compute_normal(profile_points, arc_lengths, 0.0)
    end_normal = compute_normal(profile_points, arc_lengths, arc_lengths[-1])

    expected_start = (4.0 / math.hypot(2.0, 4.0), -2.0 / math.hypot(2.0, 4.0))
    expected_end = (6.0 / math.hypot(3.0, 6.0), -3.0 / math.hypot(3.0, 6.0))

    assert math.isclose(start_normal[0], expected_start[0], abs_tol=1e-6)
    assert math.isclose(start_normal[1], expected_start[1], abs_tol=1e-6)
    assert math.isclose(end_normal[0], expected_end[0], abs_tol=1e-6)
    assert math.isclose(end_normal[1], expected_end[1], abs_tol=1e-6)


def test_generate_scan_path_handles_floating_point_step_tolerance() -> None:
    """A tiny floating-point drift in the final layer should not drop the end point."""

    profile_points = [(10.0, 0.0), (10.0, 1.0)]
    params = ScanParams(
        s_start=0.0,
        s_end=0.3,
        layer_step=0.1,
        water_distance=1.0,
    )

    scan_path = generate_scan_path(profile_points, params)

    assert len(scan_path.points) == 4
    assert math.isclose(scan_path.points[-1].arc_length, 0.3, abs_tol=1e-9)


def test_compute_normal_keeps_same_outer_direction_for_reversed_cone_profile() -> None:
    """The outward normal should stay consistent even if the same cone line is reversed."""

    forward_profile = [(100.0, 0.0), (50.0, 100.0)]
    reversed_profile = [(50.0, 100.0), (100.0, 0.0)]

    forward_arc_lengths = compute_arc_length(forward_profile)
    reversed_arc_lengths = compute_arc_length(reversed_profile)

    forward_normal = compute_normal(forward_profile, forward_arc_lengths, forward_arc_lengths[-1] / 2.0)
    reversed_normal = compute_normal(reversed_profile, reversed_arc_lengths, reversed_arc_lengths[-1] / 2.0)
    expected_angle = 63.43494882

    assert math.degrees(math.atan2(forward_normal[0], forward_normal[1])) == pytest.approx(expected_angle, abs=1e-6)
    assert math.degrees(math.atan2(reversed_normal[0], reversed_normal[1])) == pytest.approx(expected_angle, abs=1e-6)
