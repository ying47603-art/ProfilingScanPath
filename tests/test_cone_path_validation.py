"""Validation tests for the standard cone scan path."""

from __future__ import annotations

import math

import pytest

from core.path_planner import generate_scan_path
from data.models import ScanParams


TOTAL_ARC_LENGTH = 111.80339887498948
EXPECTED_TILT_ANGLE_DEG = 63.43494882


def _build_cone_scan_path():
    """Create the shared cone scan path used by all validation tests."""

    profile_points = [
        (100.0, 0.0),
        (50.0, 100.0),
    ]
    params = ScanParams(
        s_start=0.0,
        s_end=TOTAL_ARC_LENGTH,
        layer_step=10.0,
        water_distance=20.0,
    )
    return generate_scan_path(profile_points, params)


def test_cone_layer_count() -> None:
    """The cone path should contain the expected number of layers."""

    scan_path = _build_cone_scan_path()

    assert len(scan_path.points) == 12
    assert [point.layer_index for point in scan_path.points] == list(range(12))


def test_cone_probe_y_is_zero() -> None:
    """All probe points should stay on the Y=0 plane."""

    scan_path = _build_cone_scan_path()

    assert [point.probe_y for point in scan_path.points] == pytest.approx([0.0] * len(scan_path.points))


def test_cone_tilt_angle_constant() -> None:
    """The straight cone profile should keep a constant tilt angle."""

    scan_path = _build_cone_scan_path()

    angles = [point.tilt_angle_deg for point in scan_path.points]
    assert angles == pytest.approx([EXPECTED_TILT_ANGLE_DEG] * len(angles), abs=1e-6)


def test_cone_probe_x_monotonic_decrease() -> None:
    """Probe X should decrease monotonically from bottom to top."""

    scan_path = _build_cone_scan_path()
    probe_x_values = [point.probe_x for point in scan_path.points]

    assert all(left > right or math.isclose(left, right, abs_tol=1e-9) for left, right in zip(probe_x_values, probe_x_values[1:]))


def test_cone_probe_z_monotonic_increase() -> None:
    """Probe Z should increase monotonically along the scan path."""

    scan_path = _build_cone_scan_path()
    probe_z_values = [point.probe_z for point in scan_path.points]

    assert all(left < right or math.isclose(left, right, abs_tol=1e-9) for left, right in zip(probe_z_values, probe_z_values[1:]))


def test_cone_surface_points_on_profile() -> None:
    """Surface points should lie on the line x = 100 - 0.5 * z."""

    scan_path = _build_cone_scan_path()

    for point in scan_path.points:
        expected_x = 100.0 - 0.5 * point.surface_z
        assert point.surface_x == pytest.approx(expected_x, abs=1e-6)


def test_cone_full_path_consistency() -> None:
    """Arc length, layer order, and surface positions should stay geometrically consistent."""

    scan_path = _build_cone_scan_path()
    arc_lengths = [point.arc_length for point in scan_path.points]
    surface_z_values = [point.surface_z for point in scan_path.points]

    expected_arc_lengths = [float(index * 10) for index in range(12)]

    assert arc_lengths == pytest.approx(expected_arc_lengths, abs=1e-6)
    assert all(left < right or math.isclose(left, right, abs_tol=1e-9) for left, right in zip(arc_lengths, arc_lengths[1:]))
    assert all(left < right or math.isclose(left, right, abs_tol=1e-9) for left, right in zip(surface_z_values, surface_z_values[1:]))
    assert scan_path.points[0].surface_x == pytest.approx(100.0, abs=1e-6)
    assert scan_path.points[-1].arc_length < TOTAL_ARC_LENGTH
    assert scan_path.points[-1].surface_x == pytest.approx(50.80650449500464, abs=1e-6)
    assert scan_path.points[-1].surface_z == pytest.approx(98.38699100999073, abs=1e-6)
