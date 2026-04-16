"""Tests for geometric sub-segmentation of merged profile chains."""

from __future__ import annotations

import math

import pytest

from core.profile_extractor import _build_profile_segments_from_chains, _fit_arc_circle, _geometrically_split_segment


def test_pure_line_segment_is_classified_as_line() -> None:
    """A pure straight segment should remain one line subsegment."""

    points = [(10.0, float(index) * 5.0) for index in range(8)]

    subsegments = _geometrically_split_segment(points)

    assert len(subsegments) == 1
    assert subsegments[0][0] == "line"


def test_pure_arc_segment_is_classified_as_arc() -> None:
    """A smooth circular arc should remain one arc subsegment."""

    radius = 50.0
    points = [
        (100.0 + radius * math.cos(angle), radius * math.sin(angle))
        for angle in [math.radians(value) for value in range(-45, 46, 15)]
    ]

    subsegments = _geometrically_split_segment(points)

    assert len(subsegments) == 1
    assert subsegments[0][0] == "arc"


def test_shallow_sampled_arc_segment_is_still_classified_as_arc() -> None:
    """A densely sampled shallow arc should still be recognized as one arc segment."""

    radius = 80.0
    points = [
        (radius * math.cos(angle), 100.0 + radius * math.sin(angle))
        for angle in [math.radians(value) for value in range(-18, 19, 6)]
    ]

    subsegments = _geometrically_split_segment(points)

    assert len(subsegments) == 1
    assert subsegments[0][0] == "arc"


def test_line_arc_line_chain_splits_into_three_subsegments() -> None:
    """A line-arc-line chain should split into line, arc, line subsegments."""

    line_bottom = [(100.0, value) for value in (0.0, 10.0, 20.0, 30.0, 40.0)]
    arc_middle = [
        (100.0 + 20.0 * math.cos(angle), 60.0 + 20.0 * math.sin(angle))
        for angle in [math.radians(value) for value in (-90, -60, -30, 0, 30)]
    ]
    line_top = [(120.0, value) for value in (80.0, 90.0, 100.0, 110.0, 120.0)]
    points = line_bottom + arc_middle[1:] + line_top[1:]

    subsegments = _geometrically_split_segment(points)

    assert [segment_type for segment_type, _segment_points in subsegments] == ["line", "arc", "line"]


def test_arc_circle_fit_recovers_stable_radius() -> None:
    """A fitted arc segment should recover the drawing radius with low residual."""

    radius = 11.45
    points = [
        (50.0 + radius * math.cos(angle), 80.0 + radius * math.sin(angle))
        for angle in [math.radians(value) for value in range(-60, 61, 10)]
    ]

    center_x, center_z, fit_radius, fit_residual, fit_valid = _fit_arc_circle(points)

    assert fit_valid
    assert center_x == pytest.approx(50.0, abs=1e-2)
    assert center_z == pytest.approx(80.0, abs=1e-2)
    assert fit_radius == pytest.approx(radius, abs=1e-2)
    assert fit_residual is not None
    assert fit_residual < 0.01


def test_line_recheck_reclassifies_curved_line_candidate_as_arc() -> None:
    """A curved segment that initially looks line-like should be reclassified to arc."""

    radius = 120.0
    points = [
        (50.0 + radius * math.cos(angle), 200.0 + radius * math.sin(angle))
        for angle in [math.radians(value) for value in (-12, -8, -4, 0, 4, 8, 12)]
    ]

    profile_segments = _build_profile_segments_from_chains([points], num_samples=24)

    assert len(profile_segments) == 1
    assert profile_segments[0].segment_type == "arc"
    assert profile_segments[0].fit_radius_valid is True
    assert profile_segments[0].arc_geometry_valid is True
