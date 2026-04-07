"""Tests for the OCP-first STEP loader behavior."""

from __future__ import annotations

from pathlib import Path

from core.step_loader import load_step_model


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
OCP_FIXTURE = FIXTURE_DIR / "ocp_cylinder.step"
FALLBACK_FIXTURE = FIXTURE_DIR / "sample_revolved_profile.step"


def test_ocp_fixture_can_be_loaded() -> None:
    """The real OCP-generated STEP fixture should load successfully."""

    model = load_step_model(OCP_FIXTURE)

    assert model.file_path == OCP_FIXTURE


def test_ocp_loaded_shape_is_not_null() -> None:
    """The OCP-loaded fixture should carry a non-null shape object."""

    model = load_step_model(OCP_FIXTURE)

    assert model.loader_backend == "ocp"
    assert model.ocp_shape is not None
    assert not model.ocp_shape.IsNull()


def test_step_loader_prefers_ocp_when_available() -> None:
    """The loader should prefer OCP for full BRep STEP fixtures."""

    model = load_step_model(OCP_FIXTURE)

    assert model.loader_backend == "ocp"


def test_step_loader_fallback_still_works() -> None:
    """The legacy fallback loader should still work for non-BRep sample fixtures."""

    model = load_step_model(FALLBACK_FIXTURE)

    assert model.loader_backend == "fallback"
    assert model.cartesian_points
    assert model.ocp_shape is None
