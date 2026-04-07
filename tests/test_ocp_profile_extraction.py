"""Tests for OCP-first profile normalization and extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.model_normalizer import normalize_revolved_model
from core.path_planner import compute_arc_length, generate_scan_path
from core.profile_extractor import extract_profile_points, load_and_extract_profile
from core.step_loader import load_step_model
from data.models import ScanParams, StepModel


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
OCP_FILLET_FIXTURE = FIXTURE_DIR / "ocp_fillet.step"
FALLBACK_FIXTURE = FIXTURE_DIR / "sample_revolved_profile.step"


def test_ocp_fillet_fixture_can_be_loaded() -> None:
    """The OCP fillet STEP fixture should load through the OCP backend."""

    model = load_step_model(OCP_FILLET_FIXTURE)

    assert model.loader_backend == "ocp"
    assert model.ocp_shape is not None
    assert not model.ocp_shape.IsNull()


def test_ocp_shape_can_be_normalized() -> None:
    """The OCP fillet STEP fixture should normalize without errors."""

    model = load_step_model(OCP_FILLET_FIXTURE)
    normalized = normalize_revolved_model(model)

    assert normalized.ocp_shape is not None
    assert normalized.axis_origin == (0.0, 0.0, 0.0)
    assert normalized.axis_direction == (0.0, 0.0, 1.0)


def test_ocp_profile_extraction_returns_nonempty_points() -> None:
    """The OCP extraction chain should return a non-empty profile."""

    normalized = normalize_revolved_model(load_step_model(OCP_FILLET_FIXTURE))
    profile_points = extract_profile_points(normalized, num_samples=80)

    assert profile_points


def test_ocp_profile_points_are_stable_xz_points() -> None:
    """Extracted points should be XZ points with positive X and overall increasing Z."""

    profile_points = load_and_extract_profile(OCP_FILLET_FIXTURE, num_samples=80)

    assert len(profile_points) >= 2
    assert all(len(point) == 2 for point in profile_points)
    assert all(point[0] >= -1e-6 for point in profile_points)
    z_values = [point[1] for point in profile_points]
    assert z_values[0] <= z_values[-1]
    assert all(left <= right for left, right in zip(z_values, z_values[1:]))


def test_ocp_profile_points_can_feed_path_planner() -> None:
    """The extracted OCP profile should be directly usable by the path planner."""

    profile_points = load_and_extract_profile(OCP_FILLET_FIXTURE, num_samples=80)
    total_arc_length = compute_arc_length(profile_points)[-1]
    scan_path = generate_scan_path(
        profile_points,
        ScanParams(
            s_start=0.0,
            s_end=min(total_arc_length, 40.0),
            layer_step=5.0,
            water_distance=20.0,
        ),
    )

    assert scan_path.points


def test_ocp_fillet_angles_change_smoothly() -> None:
    """The fillet profile should produce a smoothly varying path angle."""

    profile_points = load_and_extract_profile(OCP_FILLET_FIXTURE, num_samples=80)
    total_arc_length = compute_arc_length(profile_points)[-1]
    scan_path = generate_scan_path(
        profile_points,
        ScanParams(
            s_start=0.0,
            s_end=min(total_arc_length, 90.0),
            layer_step=5.0,
            water_distance=20.0,
        ),
    )

    angles = [point.tilt_angle_deg for point in scan_path.points]
    assert angles
    assert max(abs(right - left) for left, right in zip(angles, angles[1:])) < 20.0


def test_fallback_old_chain_still_works() -> None:
    """The legacy fallback extraction chain should remain usable."""

    profile_points = load_and_extract_profile(FALLBACK_FIXTURE, num_samples=50)

    assert profile_points


def test_normalization_failure_raises_expected_error() -> None:
    """Invalid STEP model inputs should raise the required normalization error."""

    model = StepModel(file_path=Path("invalid.step"), cartesian_points=[], axis_placements=[])

    with pytest.raises(ValueError, match="STEP模型标准化失败"):
        normalize_revolved_model(model)
