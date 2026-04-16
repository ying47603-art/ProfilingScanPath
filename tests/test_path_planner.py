"""Tests for the V1 core path planner."""

from __future__ import annotations

import math

import pytest

from core.path_planner import compute_arc_length, compute_normal, generate_scan_path
from data.models import ScanParams


def _extract_test_arc_geometry(
    profile_points: list[tuple[float, float]],
    center_x: float,
    center_z: float,
    radius: float,
) -> tuple[float, float, float, int, float]:
    """Build one unwrapped arc geometry tuple for direct planner tests."""

    raw_angles = [math.atan2(point_z - center_z, point_x - center_x) for point_x, point_z in profile_points]
    unwrapped_angles = [raw_angles[0]]
    for raw_angle in raw_angles[1:]:
        delta = (raw_angle - unwrapped_angles[-1] + math.pi) % (2.0 * math.pi) - math.pi
        if math.isclose(delta, -math.pi, abs_tol=1e-9) and raw_angle - unwrapped_angles[-1] > 0.0:
            delta = math.pi
        unwrapped_angles.append(unwrapped_angles[-1] + delta)

    theta_start = unwrapped_angles[0]
    theta_end = unwrapped_angles[-1]
    delta_theta = theta_end - theta_start
    arc_direction = 1 if delta_theta > 0.0 else -1
    arc_length = abs(delta_theta) * radius
    return theta_start, theta_end, delta_theta, arc_direction, arc_length


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


def test_generate_scan_path_for_inner_profile_flips_offset_direction() -> None:
    """Inner profiles should use the opposite effective normal for offset and tilt."""

    profile_points = [(10.0, 0.0), (10.0, 20.0)]
    params = ScanParams(
        s_start=0.0,
        s_end=20.0,
        layer_step=10.0,
        water_distance=5.0,
    )

    scan_path = generate_scan_path(profile_points, params, profile_kind="inner")

    assert len(scan_path.points) == 3
    assert all(math.isclose(point.tilt_angle_deg, -90.0, abs_tol=1e-6) for point in scan_path.points)
    assert math.isclose(scan_path.points[0].probe_x, 5.0, abs_tol=1e-6)
    assert all(point.probe_x < point.surface_x for point in scan_path.points)


def test_generate_scan_path_reverse_offset_direction_flips_offset_and_angle() -> None:
    """Reversing offset direction should invert the final offset side and tilt."""

    profile_points = [(10.0, 0.0), (10.0, 20.0)]
    params = ScanParams(
        s_start=0.0,
        s_end=20.0,
        layer_step=10.0,
        water_distance=5.0,
    )

    default_path = generate_scan_path(profile_points, params)
    reversed_path = generate_scan_path(profile_points, params, reverse_offset_direction=True)

    assert len(default_path.points) == len(reversed_path.points) == 3
    assert math.isclose(default_path.points[0].probe_x, 15.0, abs_tol=1e-6)
    assert math.isclose(reversed_path.points[0].probe_x, 5.0, abs_tol=1e-6)
    assert all(math.isclose(point.tilt_angle_deg, -90.0, abs_tol=1e-6) for point in reversed_path.points)


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


def test_generate_scan_path_keeps_constant_water_distance_on_arc_profile() -> None:
    """Arc-like profiles should keep a constant probe-to-surface distance at every layer."""

    radius = 50.0
    profile_points = [
        (radius * math.cos(angle), radius * math.sin(angle))
        for angle in [math.pi * ratio / 8.0 for ratio in range(5)]
    ]
    params = ScanParams(
        s_start=0.0,
        s_end=compute_arc_length(profile_points)[-1],
        layer_step=compute_arc_length(profile_points)[-1] / 4.0,
        water_distance=7.5,
    )

    scan_path = generate_scan_path(profile_points, params)

    assert scan_path.points
    for point in scan_path.points:
        distance = math.hypot(point.probe_x - point.surface_x, point.probe_z - point.surface_z)
        assert distance == pytest.approx(params.water_distance, abs=1e-6)


def test_generate_scan_path_keeps_arc_offset_direction_continuous() -> None:
    """Arc profiles should not randomly flip the offset side between adjacent samples."""

    radius = 60.0
    profile_points = [
        (80.0 + radius * math.cos(angle), radius * math.sin(angle))
        for angle in [math.radians(value) for value in range(-60, 61, 10)]
    ]
    total_arc_length = compute_arc_length(profile_points)[-1]
    params = ScanParams(
        s_start=0.0,
        s_end=total_arc_length,
        layer_step=total_arc_length / 10.0,
        water_distance=6.0,
    )

    scan_path = generate_scan_path(profile_points, params)

    offset_vectors = [
        (point.probe_x - point.surface_x, point.probe_z - point.surface_z)
        for point in scan_path.points
    ]
    assert offset_vectors
    for previous_vector, current_vector in zip(offset_vectors, offset_vectors[1:]):
        previous_norm = math.hypot(previous_vector[0], previous_vector[1])
        current_norm = math.hypot(current_vector[0], current_vector[1])
        dot_value = previous_vector[0] * current_vector[0] + previous_vector[1] * current_vector[1]
        assert previous_norm == pytest.approx(params.water_distance, abs=1e-6)
        assert current_norm == pytest.approx(params.water_distance, abs=1e-6)
        assert dot_value > 0.0


def test_generate_scan_path_allows_inward_arc_offset_when_radius_is_large_enough() -> None:
    """Inward offset should remain valid while water distance stays below the local radius limit."""

    radius = 40.0
    profile_points = [
        (100.0 + radius * math.cos(angle), radius * math.sin(angle))
        for angle in [math.radians(value) for value in range(-60, 61, 10)]
    ]
    total_arc_length = compute_arc_length(profile_points)[-1]
    params = ScanParams(
        s_start=0.0,
        s_end=total_arc_length,
        layer_step=total_arc_length / 8.0,
        water_distance=12.0,
    )

    scan_path = generate_scan_path(
        profile_points,
        params,
        reverse_offset_direction=True,
    )

    assert scan_path.points
    for point in scan_path.points:
        distance = math.hypot(point.probe_x - point.surface_x, point.probe_z - point.surface_z)
        assert distance == pytest.approx(params.water_distance, abs=1e-6)


def test_generate_scan_path_rejects_inward_arc_offset_when_water_distance_exceeds_radius() -> None:
    """Inward offset should abort when water distance approaches the local curvature radius."""

    radius = 20.0
    profile_points = [
        (100.0 + radius * math.cos(angle), radius * math.sin(angle))
        for angle in [math.radians(value) for value in range(-60, 61, 10)]
    ]
    total_arc_length = compute_arc_length(profile_points)[-1]
    params = ScanParams(
        s_start=0.0,
        s_end=total_arc_length,
        layer_step=total_arc_length / 8.0,
        water_distance=19.5,
    )

    with pytest.raises(ValueError, match="local offset infeasible"):
        generate_scan_path(
            profile_points,
            params,
            reverse_offset_direction=True,
            group_index=0,
        )


def test_generate_scan_path_prefers_fitted_arc_radius_for_inward_feasibility() -> None:
    """Arc segments should use the fitted whole-arc radius before noisy local rho values."""

    radius = 11.45
    profile_points = [
        (50.0 + radius * math.cos(angle), 80.0 + radius * math.sin(angle))
        for angle in [math.radians(value) for value in (-60, -40, -20, -5, 0, 5, 20, 40, 60)]
    ]
    total_arc_length = compute_arc_length(profile_points)[-1]
    params = ScanParams(
        s_start=0.0,
        s_end=total_arc_length,
        layer_step=total_arc_length / 8.0,
        water_distance=10.0,
    )

    scan_path = generate_scan_path(
        profile_points,
        params,
        reverse_offset_direction=True,
        group_index=0,
        segment_index=3,
        segment_type="arc",
        fit_center_x=50.0,
        fit_center_z=80.0,
        fit_radius=radius,
        fit_radius_valid=True,
        arc_theta_start=_extract_test_arc_geometry(profile_points, 50.0, 80.0, radius)[0],
        arc_theta_end=_extract_test_arc_geometry(profile_points, 50.0, 80.0, radius)[1],
        arc_delta_theta=_extract_test_arc_geometry(profile_points, 50.0, 80.0, radius)[2],
        arc_direction=_extract_test_arc_geometry(profile_points, 50.0, 80.0, radius)[3],
        arc_length=_extract_test_arc_geometry(profile_points, 50.0, 80.0, radius)[4],
        arc_geometry_valid=True,
    )

    assert scan_path.points
    for point in scan_path.points:
        distance = math.hypot(point.probe_x - point.surface_x, point.probe_z - point.surface_z)
        assert distance == pytest.approx(params.water_distance, abs=1e-6)


def test_generate_scan_path_prefers_fitted_arc_radius_for_infeasibility_check() -> None:
    """A valid fitted arc radius should override noisy local rho estimates for legality checks."""

    radius = 11.45
    profile_points = [
        (50.0 + radius * math.cos(angle), 80.0 + radius * math.sin(angle))
        for angle in [math.radians(value) for value in (-60, -20, -5, 0, 5, 20, 60)]
    ]
    total_arc_length = compute_arc_length(profile_points)[-1]
    params = ScanParams(
        s_start=0.0,
        s_end=total_arc_length,
        layer_step=total_arc_length / 6.0,
        water_distance=5.0,
    )

    scan_path = generate_scan_path(
        profile_points,
        params,
        reverse_offset_direction=True,
        group_index=0,
        segment_index=3,
        segment_type="arc",
        fit_center_x=50.0,
        fit_center_z=80.0,
        fit_radius=radius,
        fit_radius_valid=True,
        arc_theta_start=_extract_test_arc_geometry(profile_points, 50.0, 80.0, radius)[0],
        arc_theta_end=_extract_test_arc_geometry(profile_points, 50.0, 80.0, radius)[1],
        arc_delta_theta=_extract_test_arc_geometry(profile_points, 50.0, 80.0, radius)[2],
        arc_direction=_extract_test_arc_geometry(profile_points, 50.0, 80.0, radius)[3],
        arc_length=_extract_test_arc_geometry(profile_points, 50.0, 80.0, radius)[4],
        arc_geometry_valid=True,
    )

    assert scan_path.points
    for point in scan_path.points:
        distance = math.hypot(point.probe_x - point.surface_x, point.probe_z - point.surface_z)
        assert distance == pytest.approx(params.water_distance, abs=1e-6)


def test_generate_scan_path_falls_back_to_local_curvature_when_arc_fit_is_invalid() -> None:
    """Invalid arc-fit metadata should fall back to the local three-point curvature estimate."""

    radius = 20.0
    profile_points = [
        (100.0 + radius * math.cos(angle), radius * math.sin(angle))
        for angle in [math.radians(value) for value in range(-60, 61, 10)]
    ]
    total_arc_length = compute_arc_length(profile_points)[-1]
    params = ScanParams(
        s_start=0.0,
        s_end=total_arc_length,
        layer_step=total_arc_length / 8.0,
        water_distance=19.5,
    )

    with pytest.raises(ValueError, match="local offset infeasible"):
        generate_scan_path(
            profile_points,
            params,
            reverse_offset_direction=True,
            group_index=0,
            segment_index=2,
            segment_type="arc",
            fit_radius=radius,
            fit_radius_valid=False,
        )


def test_generate_scan_path_rejects_line_analytic_for_curved_line_candidate() -> None:
    """A curved segment mislabeled as line should fall back instead of using analytic chord length."""

    radius = 25.0
    profile_points = [
        (90.0 + radius * math.cos(angle), 40.0 + radius * math.sin(angle))
        for angle in [math.radians(value) for value in (-40, -20, 0, 20, 40)]
    ]
    polyline_length = compute_arc_length(profile_points)[-1]
    chord_length = math.hypot(
        profile_points[-1][0] - profile_points[0][0],
        profile_points[-1][1] - profile_points[0][1],
    )
    params = ScanParams(
        s_start=0.0,
        s_end=polyline_length,
        layer_step=polyline_length / 4.0,
        water_distance=4.0,
    )

    scan_path = generate_scan_path(
        profile_points,
        params,
        segment_index=7,
        segment_type="line",
        line_start_x=profile_points[0][0],
        line_start_z=profile_points[0][1],
        line_end_x=profile_points[-1][0],
        line_end_z=profile_points[-1][1],
        line_length=chord_length,
        line_valid=True,
    )

    assert scan_path.points
    assert math.isclose(scan_path.points[-1].arc_length, polyline_length, abs_tol=1e-6)


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
