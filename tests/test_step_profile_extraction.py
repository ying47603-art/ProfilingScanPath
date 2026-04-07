"""Tests for the V1 STEP-to-profile extraction chain."""

from __future__ import annotations

from pathlib import Path

from core.model_normalizer import normalize_revolved_model
from core.path_planner import compute_arc_length, generate_scan_path
from core.profile_extractor import extract_profile_points, load_and_extract_profile
from core.step_loader import load_step_model
from data.models import ScanParams


FIXTURE_STEP_FILE = Path(__file__).resolve().parent / "fixtures" / "sample_revolved_profile.step"


def test_load_step_model() -> None:
    """A valid STEP fixture should load into the lightweight STEP model."""

    model = load_step_model(FIXTURE_STEP_FILE)

    assert model.file_path == FIXTURE_STEP_FILE
    assert model.cartesian_points
    assert model.axis_placements


def test_normalize_revolved_model_success() -> None:
    """A simple revolved fixture should normalize without errors."""

    model = load_step_model(FIXTURE_STEP_FILE)
    normalized = normalize_revolved_model(model)

    assert normalized.points_3d
    assert normalized.axis_direction == (0.0, 0.0, 1.0)


def test_extract_profile_points_returns_nonempty_points() -> None:
    """The extractor should return a non-empty XZ profile."""

    model = normalize_revolved_model(load_step_model(FIXTURE_STEP_FILE))
    profile_points = extract_profile_points(model, num_samples=50)

    assert profile_points


def test_profile_points_are_2d_xz_points() -> None:
    """Extracted profile points should be 2D XZ coordinates on the positive X side."""

    profile_points = load_and_extract_profile(FIXTURE_STEP_FILE, num_samples=50)

    assert len(profile_points) >= 2
    assert all(len(point) == 2 for point in profile_points)
    assert all(point[0] >= 0.0 for point in profile_points)


def test_profile_points_are_ordered() -> None:
    """Extracted profile points should run from bottom to top."""

    profile_points = load_and_extract_profile(FIXTURE_STEP_FILE, num_samples=50)
    z_values = [point[1] for point in profile_points]

    assert z_values[0] <= z_values[-1]
    assert all(left <= right for left, right in zip(z_values, z_values[1:]))


def test_profile_points_can_be_used_by_path_planner() -> None:
    """Extracted profile points should be directly consumable by the path planner."""

    profile_points = load_and_extract_profile(FIXTURE_STEP_FILE, num_samples=50)
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
