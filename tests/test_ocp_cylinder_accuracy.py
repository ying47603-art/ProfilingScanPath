"""Accuracy-oriented tests for the normalized OCP cylinder profile."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.path_planner import compute_arc_length, generate_scan_path
from core.profile_extractor import load_and_extract_profile
from data.models import ScanParams


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
OCP_CYLINDER_FIXTURE = FIXTURE_DIR / "ocp_cylinder.step"


def test_ocp_cylinder_profile_is_close_to_expected_geometry() -> None:
    """The extracted cylinder profile should remain close to x=100 and z=0..100."""

    profile_points = load_and_extract_profile(OCP_CYLINDER_FIXTURE, num_samples=80)
    x_values = [point[0] for point in profile_points]
    z_values = [point[1] for point in profile_points]
    mean_x = sum(x_values) / len(x_values)
    x_span = max(x_values) - min(x_values)

    assert profile_points
    assert mean_x == pytest.approx(100.0, abs=1.0)
    assert x_span <= 2.0
    assert min(z_values) == pytest.approx(0.0, abs=1.0)
    assert max(z_values) == pytest.approx(100.0, abs=1.0)


def test_ocp_cylinder_path_angles_are_close_to_ninety_degrees() -> None:
    """The cylinder path should produce near-90-degree tilt angles."""

    profile_points = load_and_extract_profile(OCP_CYLINDER_FIXTURE, num_samples=80)
    total_arc_length = compute_arc_length(profile_points)[-1]
    scan_path = generate_scan_path(
        profile_points,
        ScanParams(
            s_start=0.0,
            s_end=min(total_arc_length, 100.0),
            layer_step=10.0,
            water_distance=20.0,
        ),
    )

    angle_values = [point.tilt_angle_deg for point in scan_path.points]
    mean_angle = sum(angle_values) / len(angle_values)

    assert angle_values
    assert mean_angle == pytest.approx(90.0, abs=2.0)
    assert max(abs(angle - 90.0) for angle in angle_values) <= 5.0
