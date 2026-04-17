"""Unit tests for controller-backed segment-first profile management."""

from __future__ import annotations

import math

import pytest

from data.models import ExtractedProfileSegments, ProfileSegment
from gui.controller import GuiController


def test_controller_creates_checked_segments_after_extraction() -> None:
    """Extracted profile points should be split into enabled selectable segments."""

    controller = GuiController()
    controller._apply_extracted_profile_segments(
        ExtractedProfileSegments(
            profile_segments=[
                ProfileSegment(
                    segment_id=0,
                    name="segment_0",
                    points=[(10.0, 0.0), (10.0, 5.0)],
                    point_count=2,
                    x_min=10.0,
                    x_max=10.0,
                    z_min=0.0,
                    z_max=5.0,
                    polyline_length=5.0,
                    segment_type="vertical_like",
                    profile_side="outer",
                    is_enabled=True,
                ),
                ProfileSegment(
                    segment_id=1,
                    name="segment_1",
                    points=[(12.0, 5.0), (12.0, 10.0)],
                    point_count=2,
                    x_min=12.0,
                    x_max=12.0,
                    z_min=5.0,
                    z_max=10.0,
                    polyline_length=5.0,
                    segment_type="vertical_like",
                    profile_side="outer",
                    is_enabled=True,
                ),
            ]
        )
    )

    segments = controller.get_profile_segments()
    assert len(segments) == 2
    assert all(segment.is_enabled for segment in segments)
    assert [segment.segment_id for segment in segments] == [0, 1]


def test_controller_rebuilds_profile_from_enabled_segments_in_current_order() -> None:
    """Enabled ordered segments should define the active profile used for path generation."""

    controller = GuiController()
    controller.set_profile_segments(
        [
            ProfileSegment(1, "segment_1", [(20.0, 5.0), (20.0, 10.0)], 2, 20.0, 20.0, 5.0, 10.0, 5.0, "vertical_like", "outer", True),
            ProfileSegment(0, "segment_0", [(20.0, 10.0), (20.0, 15.0)], 2, 20.0, 20.0, 10.0, 15.0, 5.0, "vertical_like", "outer", True),
        ]
    )

    build_result = controller.build_active_profile_from_segments()

    assert build_result.rebuilt_profile_points == [
        (20.0, 5.0),
        (20.0, 10.0),
        (20.0, 15.0),
    ]
    assert build_result.is_continuous
    assert len(build_result.profile_groups) == 1


def test_controller_splits_disconnected_segments_into_multiple_groups() -> None:
    """A large gap between selected segments should produce multiple valid profile groups."""

    controller = GuiController()
    controller.set_profile_segments(
        [
            ProfileSegment(0, "segment_0", [(100.0, 0.0), (100.0, 20.0)], 2, 100.0, 100.0, 0.0, 20.0, 20.0, "vertical_like", "outer", True),
            ProfileSegment(1, "segment_1", [(130.0, 80.0), (130.0, 100.0)], 2, 130.0, 130.0, 80.0, 100.0, 20.0, "vertical_like", "inner", True),
        ]
    )

    build_result = controller.build_active_profile_from_segments()

    assert build_result.is_continuous
    assert len(build_result.profile_groups) == 2
    assert build_result.profile_groups[0] == [(100.0, 0.0), (100.0, 20.0)]
    assert build_result.profile_groups[1] == [(130.0, 80.0), (130.0, 100.0)]
    assert controller.active_profile_groups == build_result.profile_groups
    assert any("disconnected groups" in warning for warning in build_result.warnings)


def test_controller_accepts_one_enabled_segment_as_valid_profile() -> None:
    """A single enabled segment should remain a valid working profile."""

    controller = GuiController()
    controller.set_profile_segments(
        [
            ProfileSegment(0, "segment_0", [(10.0, 0.0), (10.0, 20.0)], 2, 10.0, 10.0, 0.0, 20.0, 20.0, "vertical_like", "outer", True),
            ProfileSegment(1, "segment_1", [(20.0, 0.0), (20.0, 20.0)], 2, 20.0, 20.0, 0.0, 20.0, 20.0, "vertical_like", "inner", False),
        ]
    )

    build_result = controller.build_active_profile_from_segments()

    assert build_result.is_continuous
    assert build_result.rebuilt_profile_points == [(10.0, 0.0), (10.0, 20.0)]
    assert len(build_result.profile_groups) == 1


def test_flip_z_uses_stable_global_bounds_across_selection_changes() -> None:
    """Flip-Z should reuse extracted global Z bounds even after enabled segment changes."""

    controller = GuiController()
    controller._apply_extracted_profile_segments(
        ExtractedProfileSegments(
            profile_segments=[
                ProfileSegment(
                    segment_id=0,
                    name="segment_0",
                    points=[(10.0, 0.0), (10.0, 20.0)],
                    point_count=2,
                    x_min=10.0,
                    x_max=10.0,
                    z_min=0.0,
                    z_max=20.0,
                    polyline_length=20.0,
                    segment_type="line",
                    profile_side="outer",
                    is_enabled=True,
                ),
                ProfileSegment(
                    segment_id=1,
                    name="segment_1",
                    points=[(20.0, 80.0), (20.0, 100.0)],
                    point_count=2,
                    x_min=20.0,
                    x_max=20.0,
                    z_min=80.0,
                    z_max=100.0,
                    polyline_length=20.0,
                    segment_type="line",
                    profile_side="outer",
                    is_enabled=True,
                ),
            ]
        )
    )

    controller.set_profile_transform_options(flip_z=True)
    displayed_before = controller.get_display_profile_segments()
    assert displayed_before[0].points == [(10.0, 100.0), (10.0, 80.0)]

    raw_segments = controller.get_profile_segments()
    controller.set_profile_segments(
        [
            ProfileSegment(
                segment_id=raw_segments[0].segment_id,
                name=raw_segments[0].name,
                points=list(raw_segments[0].points),
                point_count=raw_segments[0].point_count,
                x_min=raw_segments[0].x_min,
                x_max=raw_segments[0].x_max,
                z_min=raw_segments[0].z_min,
                z_max=raw_segments[0].z_max,
                polyline_length=raw_segments[0].polyline_length,
                segment_type=raw_segments[0].segment_type,
                profile_side=raw_segments[0].profile_side,
                is_enabled=True,
            ),
            ProfileSegment(
                segment_id=raw_segments[1].segment_id,
                name=raw_segments[1].name,
                points=list(raw_segments[1].points),
                point_count=raw_segments[1].point_count,
                x_min=raw_segments[1].x_min,
                x_max=raw_segments[1].x_max,
                z_min=raw_segments[1].z_min,
                z_max=raw_segments[1].z_max,
                polyline_length=raw_segments[1].polyline_length,
                segment_type=raw_segments[1].segment_type,
                profile_side=raw_segments[1].profile_side,
                is_enabled=False,
            ),
        ]
    )

    displayed_after = controller.get_display_profile_segments()
    assert displayed_after[0].points == [(10.0, 100.0), (10.0, 80.0)]
    assert controller.active_profile_groups == [[(10.0, 100.0), (10.0, 80.0)]]


def test_controller_preserves_arc_fit_metadata_through_active_group_rebuild() -> None:
    """Active group rebuild should retain fitted arc metadata for planner dispatch."""

    controller = GuiController()
    controller.set_profile_segments(
        [
            ProfileSegment(
                segment_id=2,
                name="segment_2",
                points=[(100.0, 0.0), (99.0, 5.0), (97.0, 10.0)],
                point_count=3,
                x_min=97.0,
                x_max=100.0,
                z_min=0.0,
                z_max=10.0,
                polyline_length=10.5,
                segment_type="arc",
                profile_side="outer",
                is_enabled=True,
                fit_center_x=94.758362,
                fit_center_z=14.836635,
                fit_radius=11.532647,
                fit_radius_valid=True,
                fit_residual=0.001862,
            )
        ]
    )

    build_result = controller.build_active_profile_from_segments()

    assert build_result.profile_groups
    active_segment = build_result.oriented_group_segments[0][0]
    assert active_segment.segment_type == "arc"
    assert active_segment.fit_radius_valid is True
    assert active_segment.fit_radius == 11.532647
    assert active_segment.fit_center_x == 94.758362
    assert active_segment.fit_center_z == 14.836635


def test_controller_preserves_arc_fit_metadata_through_flip_transforms() -> None:
    """Flip transforms should not erase fitted arc metadata on rebuilt active segments."""

    controller = GuiController()
    arc_points = [
        (94.0 + 12.0 * 0.0, 20.0 + 12.0 * -1.0),
        (94.0 + 12.0 * 0.5, 20.0 + 12.0 * -0.8660254037844386),
        (94.0 + 12.0 * 0.9428090415820634, 20.0 + 12.0 * -0.3333333333333333),
    ]
    controller.set_profile_segments(
        [
            ProfileSegment(
                segment_id=2,
                name="segment_2",
                points=arc_points,
                point_count=3,
                x_min=min(point[0] for point in arc_points),
                x_max=max(point[0] for point in arc_points),
                z_min=min(point[1] for point in arc_points),
                z_max=max(point[1] for point in arc_points),
                polyline_length=14.771513008089297,
                segment_type="arc",
                profile_side="outer",
                is_enabled=True,
                fit_center_x=94.0,
                fit_center_z=20.0,
                fit_radius=12.0,
                fit_radius_valid=True,
                fit_residual=0.001,
                arc_theta_start=-1.5707963267948966,
                arc_theta_end=-0.3398369094541219,
                arc_delta_theta=1.2309594173407747,
                arc_direction=1,
                arc_length=14.771513008089297,
                arc_geometry_valid=True,
            )
        ]
    )

    controller.set_profile_transform_options(flip_z=True, flip_start=True)
    active_segment = controller.active_profile_build_result.oriented_group_segments[0][0]

    assert active_segment.segment_type == "arc"
    assert active_segment.fit_radius_valid is True
    assert active_segment.fit_radius == 12.0
    assert active_segment.fit_center_x == 94.0
    assert active_segment.fit_center_z == pytest.approx(4.0, abs=1e-6)
    assert active_segment.arc_theta_start == pytest.approx(0.3398369094541219, abs=1e-6)
    assert active_segment.arc_theta_end == pytest.approx(1.5707963267948966, abs=1e-6)
    assert active_segment.arc_delta_theta == pytest.approx(1.2309594173407747, abs=1e-6)
    assert active_segment.arc_direction == 1
    assert active_segment.arc_length == pytest.approx(14.771513008089297, abs=1e-6)
    assert controller._points_vs_analytic_consistent(active_segment) is True


def test_set_profile_segments_updates_state_without_polluting_source_geometry() -> None:
    """UI reorder/enable updates should not overwrite extractor-backed source geometry."""

    controller = GuiController()
    controller._apply_extracted_profile_segments(
        ExtractedProfileSegments(
            profile_segments=[
                ProfileSegment(
                    segment_id=2,
                    name="segment_2",
                    points=[(100.0, 0.0), (99.0, 5.0), (97.0, 10.0)],
                    point_count=3,
                    x_min=97.0,
                    x_max=100.0,
                    z_min=0.0,
                    z_max=10.0,
                    polyline_length=10.5,
                    segment_type="arc",
                    profile_side="outer",
                    is_enabled=True,
                    fit_center_x=94.758362,
                    fit_center_z=14.836635,
                    fit_radius=11.532647,
                    fit_radius_valid=True,
                    fit_residual=0.001862,
                )
            ]
        )
    )

    controller.set_profile_segments(
        [
            ProfileSegment(
                segment_id=2,
                name="segment_2",
                points=[(100.0, 0.0), (99.0, 5.0), (97.0, 10.0)],
                point_count=3,
                x_min=97.0,
                x_max=100.0,
                z_min=0.0,
                z_max=10.0,
                polyline_length=10.5,
                segment_type="arc",
                profile_side="outer",
                is_enabled=False,
                fit_center_x=None,
                fit_center_z=None,
                fit_radius=None,
                fit_radius_valid=False,
                fit_residual=None,
            )
        ]
    )

    source_segment = controller.get_profile_segments()[0]
    assert source_segment.fit_radius_valid is True
    assert source_segment.fit_radius == 11.532647
    assert controller.build_active_profile_from_segments().warnings == ["[PROFILE] no enabled segments"]

    controller.enable_all_profile_segments()
    restored_segment = controller.get_profile_segments()[0]
    assert restored_segment.fit_radius_valid is True
    assert restored_segment.fit_radius == 11.532647
    assert restored_segment.fit_center_x == 94.758362
    assert restored_segment.fit_center_z == 14.836635


def test_controller_uses_arc_geometry_length_for_active_totals() -> None:
    """Active totals should prefer analytic arc length over sampled polyline length."""

    controller = GuiController()
    controller.set_profile_segments(
        [
            ProfileSegment(
                segment_id=2,
                name="segment_2",
                points=[(100.0, 0.0), (99.0, 5.0), (97.0, 10.0)],
                point_count=3,
                x_min=97.0,
                x_max=100.0,
                z_min=0.0,
                z_max=10.0,
                polyline_length=10.5,
                segment_type="arc",
                profile_side="outer",
                is_enabled=True,
                fit_center_x=94.758362,
                fit_center_z=14.836635,
                fit_radius=11.532647,
                fit_radius_valid=True,
                fit_residual=0.001862,
                arc_theta_start=0.1,
                arc_theta_end=0.1 + 1.5,
                arc_delta_theta=1.5,
                arc_direction=1,
                arc_length=17.2989705,
                arc_geometry_valid=True,
            )
        ]
    )

    assert controller.active_profile_total_length == pytest.approx(17.2989705, abs=1e-6)
    assert len(controller.active_profile_group_lengths) == 1
    assert controller.active_profile_group_lengths[0] == pytest.approx(17.2989705, abs=1e-6)


def test_generate_path_uses_flip_z_working_arc_geometry() -> None:
    """Path generation should consume the flipped working arc geometry, not the original source."""

    controller = GuiController()
    arc_points = [
        (94.0 + 12.0 * 0.0, 20.0 + 12.0 * -1.0),
        (94.0 + 12.0 * 0.5, 20.0 + 12.0 * -0.8660254037844386),
        (94.0 + 12.0 * 0.9428090415820634, 20.0 + 12.0 * -0.3333333333333333),
    ]
    controller.set_profile_segments(
        [
            ProfileSegment(
                segment_id=2,
                name="segment_2",
                points=arc_points,
                point_count=3,
                x_min=min(point[0] for point in arc_points),
                x_max=max(point[0] for point in arc_points),
                z_min=min(point[1] for point in arc_points),
                z_max=max(point[1] for point in arc_points),
                polyline_length=14.771513008089297,
                segment_type="arc",
                profile_side="outer",
                is_enabled=True,
                fit_center_x=94.0,
                fit_center_z=20.0,
                fit_radius=12.0,
                fit_radius_valid=True,
                fit_residual=0.001,
                arc_theta_start=-1.5707963267948966,
                arc_theta_end=-0.3398369094541219,
                arc_delta_theta=1.2309594173407747,
                arc_direction=1,
                arc_length=14.771513008089297,
                arc_geometry_valid=True,
            )
        ]
    )

    baseline = controller.generate_path(
        s_start=0.0,
        s_end=None,
        layer_step=7.3857565040446485,
        water_distance=2.0,
    )
    baseline_path = controller.scan_path
    assert baseline["scan_point_count"] == 3
    assert baseline_path is not None

    controller.set_profile_transform_options(flip_z=True)
    flipped = controller.generate_path(
        s_start=0.0,
        s_end=None,
        layer_step=7.3857565040446485,
        water_distance=2.0,
    )
    flipped_path = controller.scan_path
    assert flipped["scan_point_count"] == 3
    assert flipped_path is not None

    mirror_axis_sum = min(point[1] for point in arc_points) + max(point[1] for point in arc_points)
    for baseline_point, flipped_point in zip(baseline_path.points, flipped_path.points):
        assert flipped_point.surface_x == pytest.approx(baseline_point.surface_x, abs=1e-6)
        assert flipped_point.surface_z == pytest.approx(mirror_axis_sum - baseline_point.surface_z, abs=1e-6)
        assert flipped_point.probe_x == pytest.approx(baseline_point.probe_x, abs=1e-6)
        assert flipped_point.probe_z == pytest.approx(mirror_axis_sum - baseline_point.probe_z, abs=1e-6)


def test_generate_path_uses_flip_z_working_horizontal_line_geometry() -> None:
    """A horizontal line should stay in sync with flip_z working geometry during path generation."""

    controller = GuiController()
    controller.set_profile_segments(
        [
            ProfileSegment(
                segment_id=5,
                name="segment_5",
                points=[(10.0, 5.0), (30.0, 5.0)],
                point_count=2,
                x_min=10.0,
                x_max=30.0,
                z_min=5.0,
                z_max=5.0,
                polyline_length=20.0,
                segment_type="line",
                profile_side="outer",
                is_enabled=True,
                line_start_x=10.0,
                line_start_z=5.0,
                line_end_x=30.0,
                line_end_z=5.0,
                line_length=20.0,
                line_valid=True,
            )
            ,
            ProfileSegment(
                segment_id=9,
                name="segment_9",
                points=[(10.0, 15.0), (30.0, 15.0)],
                point_count=2,
                x_min=10.0,
                x_max=30.0,
                z_min=15.0,
                z_max=15.0,
                polyline_length=20.0,
                segment_type="line",
                profile_side="outer",
                is_enabled=False,
                line_start_x=10.0,
                line_start_z=15.0,
                line_end_x=30.0,
                line_end_z=15.0,
                line_length=20.0,
                line_valid=True,
            ),
        ]
    )

    baseline = controller.generate_path(
        s_start=0.0,
        s_end=None,
        layer_step=10.0,
        water_distance=2.0,
    )
    baseline_path = controller.scan_path
    assert baseline["scan_point_count"] == 3
    assert baseline_path is not None
    assert all(math.isclose(point.surface_z, 5.0, abs_tol=1e-6) for point in baseline_path.points)

    controller.set_profile_transform_options(flip_z=True)
    flipped = controller.generate_path(
        s_start=0.0,
        s_end=None,
        layer_step=10.0,
        water_distance=2.0,
    )
    flipped_path = controller.scan_path
    assert flipped["scan_point_count"] == 3
    assert flipped_path is not None

    mirror_axis_sum = 20.0
    for baseline_point, flipped_point in zip(baseline_path.points, flipped_path.points):
        assert flipped_point.surface_x == pytest.approx(baseline_point.surface_x, abs=1e-6)
        assert flipped_point.surface_z == pytest.approx(mirror_axis_sum - baseline_point.surface_z, abs=1e-6)
        assert flipped_point.probe_z == pytest.approx(mirror_axis_sum - baseline_point.probe_z, abs=1e-6)


def test_generate_path_uses_flip_start_working_horizontal_line_geometry() -> None:
    """A horizontal line should regenerate correctly after flip_start reverses its working direction."""

    controller = GuiController()
    controller.set_profile_segments(
        [
            ProfileSegment(
                segment_id=6,
                name="segment_6",
                points=[(10.0, 5.0), (30.0, 5.0)],
                point_count=2,
                x_min=10.0,
                x_max=30.0,
                z_min=5.0,
                z_max=5.0,
                polyline_length=20.0,
                segment_type="line",
                profile_side="outer",
                is_enabled=True,
                line_start_x=10.0,
                line_start_z=5.0,
                line_end_x=30.0,
                line_end_z=5.0,
                line_length=20.0,
                line_valid=True,
            )
        ]
    )

    controller.set_profile_transform_options(flip_start=True)
    active_segment = controller.active_profile_build_result.oriented_group_segments[0][0]

    assert active_segment.points == [(30.0, 5.0), (10.0, 5.0)]
    assert active_segment.line_start_x == pytest.approx(30.0, abs=1e-6)
    assert active_segment.line_end_x == pytest.approx(10.0, abs=1e-6)
    assert active_segment.line_start_z == pytest.approx(5.0, abs=1e-6)
    assert active_segment.line_end_z == pytest.approx(5.0, abs=1e-6)
    assert controller._points_vs_analytic_consistent(active_segment) is True
