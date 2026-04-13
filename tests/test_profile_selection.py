"""Tests for selectable outer/inner profile classification."""

from __future__ import annotations

from core.profile_extractor import _select_outer_and_inner_chains


def test_single_outer_profile_does_not_create_inner_profile() -> None:
    """A single complete contour should remain outer-only."""

    outer_chain = [(100.0, 0.0), (100.0, 50.0), (100.0, 100.0)]

    outer, inner = _select_outer_and_inner_chains([outer_chain])

    assert outer == outer_chain
    assert inner is None


def test_hollow_section_selects_outer_and_inner_profiles() -> None:
    """Two complete overlapping contours should be classified as outer/inner."""

    outer_chain = [
        (100.0, 0.0),
        (101.0, 20.0),
        (102.0, 40.0),
        (102.0, 60.0),
        (101.0, 80.0),
        (100.0, 100.0),
    ]
    inner_chain = [
        (60.0, 0.0),
        (59.0, 20.0),
        (58.0, 40.0),
        (58.0, 60.0),
        (59.0, 80.0),
        (60.0, 100.0),
    ]

    outer, inner = _select_outer_and_inner_chains([outer_chain, inner_chain])

    assert outer == outer_chain
    assert inner == inner_chain


def test_segmented_outer_profile_is_not_misclassified_as_inner_profile() -> None:
    """A short local chain must not be treated as an inner contour candidate."""

    outer_chain = [(100.0, 0.0), (100.0, 50.0), (100.0, 100.0)]
    local_step_chain = [(70.0, 55.0), (70.0, 75.0), (70.0, 95.0)]

    outer, inner = _select_outer_and_inner_chains([outer_chain, local_step_chain])

    assert outer == outer_chain
    assert inner is None
