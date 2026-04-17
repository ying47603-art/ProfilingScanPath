
"""Controller layer for the PyQt6 GUI workflow."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Sequence

from core.interference_checker import check_adjacent_layer_interference
from core.model_normalizer import normalize_revolved_model
from core.path_planner import generate_scan_path
from core.profile_extractor import extract_profile_segments
from core.step_loader import load_step_model
from data.models import (
    ActiveProfileBuildResult,
    ExtractedProfileSegments,
    InterferenceCheckResult,
    NormalizedStepModel,
    PathPoint,
    ProfileSegment,
    ScanParams,
    ScanPath,
    StepModel,
)
from exporter.csv_exporter import CsvExporter


ProfilePoint = tuple[float, float]
CONTINUITY_WARNING_RATIO = 0.08


class GuiController:
    """Coordinate GUI actions with the segment-first profile workflow."""

    def __init__(self) -> None:
        """Initialize controller state."""

        self._exporter = CsvExporter()
        self._step_model: StepModel | None = None
        self._normalized_model: NormalizedStepModel | None = None
        self._source_profile_segments: dict[int, ProfileSegment] = {}
        self._ordered_segment_ids: list[int] = []
        self._enabled_segment_ids: set[int] = set()
        self._active_profile_points: list[ProfilePoint] = []
        self._active_profile_groups: list[list[ProfilePoint]] = []
        self._active_profile_segments: list[ProfileSegment] = []
        self._active_profile_group_segments: list[list[ProfileSegment]] = []
        self._active_profile_build_result = ActiveProfileBuildResult()
        self._scan_path: ScanPath | None = None
        self._interference_result: InterferenceCheckResult | None = None
        self._flip_z_enabled = False
        self._flip_start_enabled = False
        self._reverse_offset_direction = False
        self._profile_global_z_min: float | None = None
        self._profile_global_z_max: float | None = None

    @property
    def step_model(self) -> StepModel | None:
        return self._step_model

    @property
    def normalized_model(self) -> NormalizedStepModel | None:
        return self._normalized_model

    @property
    def profile_points(self) -> list[ProfilePoint]:
        return list(self._active_profile_points)

    @property
    def active_profile_groups(self) -> list[list[ProfilePoint]]:
        return [list(group) for group in self._active_profile_groups]

    @property
    def active_profile_total_length(self) -> float:
        return sum(self._get_segment_effective_arc_length(segment) for segment in self._active_profile_segments)

    @property
    def active_profile_group_lengths(self) -> list[float]:
        """Return authoritative arc lengths for each current active working-profile group."""

        return [
            self._get_group_effective_arc_length(group)
            for group in self._active_profile_group_segments
        ]

    @property
    def active_profile_is_valid(self) -> bool:
        return bool(self._active_profile_groups)

    @property
    def active_profile_build_result(self) -> ActiveProfileBuildResult:
        return self._active_profile_build_result

    @property
    def scan_path(self) -> ScanPath | None:
        return self._scan_path

    @property
    def interference_result(self) -> InterferenceCheckResult | None:
        return self._interference_result

    @property
    def flip_z_enabled(self) -> bool:
        return self._flip_z_enabled

    @property
    def flip_start_enabled(self) -> bool:
        return self._flip_start_enabled

    @property
    def reverse_offset_direction_enabled(self) -> bool:
        return self._reverse_offset_direction

    def load_step(self, file_path: Path) -> dict[str, object]:
        self._step_model = load_step_model(file_path)
        self._normalized_model = None
        self._reset_profile_state()
        return {
            "file_path": self._step_model.file_path,
            "loader_backend": self._step_model.loader_backend,
            "has_ocp_shape": self._step_model.ocp_shape is not None,
            "cartesian_point_count": len(self._step_model.cartesian_points),
            "axis_placement_count": len(self._step_model.axis_placements),
        }

    def extract_profile(self, samples: int) -> dict[str, object]:
        if self._step_model is None:
            raise ValueError("No STEP model has been loaded")

        self._normalized_model = normalize_revolved_model(self._step_model)
        extracted_segments = extract_profile_segments(self._normalized_model, num_samples=samples)
        self._apply_extracted_profile_segments(extracted_segments)
        self.build_active_profile_from_segments()
        self._scan_path = None
        self._interference_result = None

        result = self._profile_stats()
        result.update(
            {
                "axis_origin": self._normalized_model.axis_origin,
                "axis_direction": self._normalized_model.axis_direction,
                "has_ocp_shape": self._normalized_model.ocp_shape is not None,
                "segment_count": len(self._ordered_segment_ids),
                "enabled_segment_count": len(self._enabled_segment_ids),
                "suggested_segment_order": list(self._ordered_segment_ids),
                "global_z_min": self._profile_global_z_min,
                "global_z_max": self._profile_global_z_max,
            }
        )
        return result

    def get_profile_segments(self) -> list[ProfileSegment]:
        """Return raw ordered profile segments without display-only transform options."""

        ordered_segments: list[ProfileSegment] = []
        for segment_id in self._ordered_segment_ids:
            base_segment = self._source_profile_segments.get(segment_id)
            if base_segment is None:
                continue
            ordered_segments.append(self._clone_profile_segment(base_segment, is_enabled=segment_id in self._enabled_segment_ids))
        return ordered_segments

    def get_display_profile_segments(self) -> list[ProfileSegment]:
        """Return ordered profile segments after applying display-level Z-axis flipping."""

        raw_segments = self.get_profile_segments()
        if not self._flip_z_enabled or not raw_segments:
            return raw_segments

        mirrored_segments: list[ProfileSegment] = []
        for segment in raw_segments:
            mirrored_segments.append(
                self._clone_profile_segment(
                    segment,
                    points=self._flip_points_z_with_global_bounds(segment.points),
                    is_enabled=segment.is_enabled,
                    fit_center_z=(
                        None
                        if segment.fit_center_z is None or self._profile_global_z_min is None or self._profile_global_z_max is None
                        else float(self._profile_global_z_min) + float(self._profile_global_z_max) - segment.fit_center_z
                    ),
                )
            )
        return mirrored_segments

    def set_profile_segments(self, profile_segments: Sequence[ProfileSegment]) -> None:
        """Update UI-driven order and check-state from source-backed segment rows."""

        if not self._source_profile_segments and profile_segments:
            self._source_profile_segments = {
                int(segment.segment_id): self._build_profile_segment(
                    segment_id=int(segment.segment_id),
                    points=list(segment.points),
                    profile_side=segment.profile_side,
                    is_enabled=bool(segment.is_enabled),
                    name=segment.name,
                    segment_type=segment.segment_type,
                    fit_center_x=segment.fit_center_x,
                    fit_center_z=segment.fit_center_z,
                    fit_radius=segment.fit_radius,
                    fit_radius_valid=segment.fit_radius_valid,
                    fit_residual=segment.fit_residual,
                    arc_theta_start=segment.arc_theta_start,
                    arc_theta_end=segment.arc_theta_end,
                    arc_delta_theta=segment.arc_delta_theta,
                    arc_direction=segment.arc_direction,
                    arc_length=segment.arc_length,
                    arc_geometry_valid=segment.arc_geometry_valid,
                    line_start_x=segment.line_start_x,
                    line_start_z=segment.line_start_z,
                    line_end_x=segment.line_end_x,
                    line_end_z=segment.line_end_z,
                    line_length=segment.line_length,
                    line_valid=segment.line_valid,
                )
                for segment in profile_segments
            }
            for segment in self._source_profile_segments.values():
                self._log_segment_geometry_state("[PROFILE_DEBUG] source", segment)
            self._compute_profile_global_z_bounds(self._source_profile_segments.values())

        self._ordered_segment_ids = [int(segment.segment_id) for segment in profile_segments]
        self._enabled_segment_ids = {
            int(segment.segment_id)
            for segment in profile_segments
            if bool(segment.is_enabled)
        }
        for segment in profile_segments:
            source_segment = self._source_profile_segments.get(int(segment.segment_id))
            if source_segment is None:
                print(f"[PROFILE_DEBUG] source pollution detected for segment={int(segment.segment_id)} missing_source_segment")
                continue
            if (
                source_segment.segment_type != segment.segment_type
                or source_segment.fit_radius_valid != segment.fit_radius_valid
                or source_segment.fit_radius != segment.fit_radius
                or source_segment.fit_center_x != segment.fit_center_x
                or source_segment.fit_center_z != segment.fit_center_z
            ):
                print(f"[PROFILE_DEBUG] source pollution detected for segment={int(segment.segment_id)} incoming_working_metadata_differs_from_source")
        self.build_active_profile_from_segments()
        self._scan_path = None
        self._interference_result = None

    def enable_all_profile_segments(self) -> None:
        self._enabled_segment_ids = set(self._ordered_segment_ids)
        self.build_active_profile_from_segments()
        self._scan_path = None
        self._interference_result = None

    def set_profile_transform_options(
        self,
        *,
        flip_z: bool | None = None,
        flip_start: bool | None = None,
    ) -> ActiveProfileBuildResult:
        if flip_z is not None:
            self._flip_z_enabled = bool(flip_z)
        if flip_start is not None:
            self._flip_start_enabled = bool(flip_start)
        print(f"[PROFILE_DEBUG] flip_z={self._flip_z_enabled}")

        build_result = self.build_active_profile_from_segments()
        self._scan_path = None
        self._interference_result = None
        return build_result

    def set_reverse_offset_direction(self, enabled: bool) -> None:
        """Set whether generated path points should be offset to the opposite normal side."""

        self._reverse_offset_direction = bool(enabled)
        self._scan_path = None
        self._interference_result = None

    def get_enabled_profile_segments_in_order(self) -> list[ProfileSegment]:
        return [
            self._clone_profile_segment(segment, is_enabled=True)
            for segment in self._active_profile_segments
        ]

    def get_active_profile_group_segments(self) -> list[list[ProfileSegment]]:
        """Return deep-copied active profile segments grouped by disconnected working profile."""

        return [
            [
                self._clone_profile_segment(segment, is_enabled=True)
                for segment in group
            ]
            for group in self._active_profile_group_segments
        ]

    def build_active_profile_from_segments(self) -> ActiveProfileBuildResult:
        """Build ordered working-profile groups from checked segments without cross-group connectors."""

        warnings: list[str] = []
        raw_enabled_segments = [
            self._source_profile_segments[segment_id]
            for segment_id in self._ordered_segment_ids
            if segment_id in self._enabled_segment_ids and segment_id in self._source_profile_segments
        ]
        if not raw_enabled_segments:
            self._active_profile_points = []
            self._active_profile_groups = []
            self._active_profile_segments = []
            self._active_profile_group_segments = []
            self._active_profile_build_result = ActiveProfileBuildResult(
                rebuilt_profile_points=[],
                profile_groups=[],
                oriented_segments=[],
                oriented_group_segments=[],
                is_continuous=False,
                warnings=["[PROFILE] no enabled segments"],
            )
            return self._active_profile_build_result

        continuity_threshold = self._compute_continuity_warning_threshold(raw_enabled_segments)
        oriented_group_segments: list[list[ProfileSegment]] = []
        current_group_segments: list[ProfileSegment] = []
        current_group_points: list[ProfilePoint] = []

        for raw_segment in raw_enabled_segments:
            self._log_segment_geometry_state("[PROFILE_DEBUG] rebuild input source", raw_segment)
            segment_points = list(raw_segment.points)
            if len(segment_points) < 2:
                continue

            if current_group_points:
                distance_to_start = self._point_distance(current_group_points[-1], segment_points[0])
                distance_to_end = self._point_distance(current_group_points[-1], segment_points[-1])
                if distance_to_end < distance_to_start:
                    segment_points.reverse()
                    gap_distance = distance_to_end
                else:
                    gap_distance = distance_to_start

                if gap_distance > continuity_threshold:
                    oriented_group_segments.append(current_group_segments)
                    current_group_segments = []
                    current_group_points = []

            oriented_segment = self._clone_profile_segment(raw_segment, points=segment_points, is_enabled=True)
            self._log_segment_geometry_state("[PROFILE_DEBUG] rebuild output", oriented_segment)
            current_group_segments.append(oriented_segment)

            if current_group_points and self._points_are_close(current_group_points[-1], segment_points[0]):
                current_group_points.extend(segment_points[1:])
            else:
                current_group_points.extend(segment_points)

        if current_group_segments:
            oriented_group_segments.append(current_group_segments)

        transformed_groups, transformed_group_segments = self._apply_profile_group_transform_options(oriented_group_segments)
        self._active_profile_groups = transformed_groups
        self._active_profile_group_segments = transformed_group_segments
        self._active_profile_points = [point for group in transformed_groups for point in group]
        self._active_profile_segments = [segment for group in transformed_group_segments for segment in group]
        for segment in self._active_profile_segments:
            self._log_segment_geometry_state("[PROFILE_DEBUG] rebuild output", segment)

        if len(transformed_groups) > 1:
            warnings.append(f"[PROFILE] selected segments split into {len(transformed_groups)} disconnected groups")

        self._active_profile_build_result = ActiveProfileBuildResult(
            rebuilt_profile_points=list(self._active_profile_points),
            profile_groups=[list(group) for group in self._active_profile_groups],
            oriented_segments=list(self._active_profile_segments),
            oriented_group_segments=self.get_active_profile_group_segments(),
            is_continuous=bool(transformed_groups),
            warnings=warnings,
            transform_applied=self._flip_z_enabled or self._flip_start_enabled,
        )
        return self._active_profile_build_result

    def generate_path(
        self,
        s_start: float,
        s_end: float | None,
        layer_step: float,
        water_distance: float,
    ) -> dict[str, object]:
        print("[PATH_DEBUG] generate_path uses working geometry")
        build_result = self.build_active_profile_from_segments()
        if not build_result.profile_groups or not self._active_profile_group_segments:
            raise ValueError("No enabled profile segments are available for path generation")

        total_arc_length = self.active_profile_total_length
        resolved_s_end = total_arc_length if s_end is None else s_end
        if resolved_s_end <= s_start:
            raise ValueError("s_start and s_end must satisfy 0 <= s_start < s_end <= total_arc_length")

        params = ScanParams(
            s_start=s_start,
            s_end=resolved_s_end,
            layer_step=layer_step,
            water_distance=water_distance,
        )
        try:
            self._scan_path = self._generate_scan_path_from_segments(params)
            self._interference_result = None
        except Exception:
            self._scan_path = None
            self._interference_result = None
            raise

        angle_values = [point.tilt_angle_deg for point in self._scan_path.points]
        return {
            "scan_point_count": len(self._scan_path.points),
            "min_angle": min(angle_values),
            "max_angle": max(angle_values),
            "resolved_s_end": resolved_s_end,
            "continuity_warning": bool(build_result.warnings),
            "path_group_count": len(build_result.profile_groups),
        }

    def export_csv(self, output_dir: Path) -> dict[str, Path]:
        active_profile_points = self.profile_points
        if not active_profile_points:
            raise ValueError("No profile points are available for export")
        if self._scan_path is None or not self._scan_path.points:
            raise ValueError("No scan path is available for export")

        output_dir.mkdir(parents=True, exist_ok=True)
        profile_file = self._exporter.export_rows(
            rows=[{"x": float(point_x), "z": float(point_z)} for point_x, point_z in active_profile_points],
            target_file=output_dir / "profile_points.csv",
        )
        standard_file = self._exporter.export_rows(
            rows=self._build_standard_rows(self._scan_path.points),
            target_file=output_dir / "scan_path_standard.csv",
        )
        compact_file = self._exporter.export_rows(
            rows=self._build_compact_rows(self._scan_path.points),
            target_file=output_dir / "scan_path_compact.csv",
        )
        return {
            "profile_points": profile_file,
            "scan_path_standard": standard_file,
            "scan_path_compact": compact_file,
        }

    def flip_z_axis(self) -> dict[str, object]:
        self.set_profile_transform_options(flip_z=not self._flip_z_enabled)
        return self._profile_stats()

    def flip_profile_direction(self) -> dict[str, object]:
        self.set_profile_transform_options(flip_start=not self._flip_start_enabled)
        return self._profile_stats()

    def clear_scan_path(self) -> None:
        self._scan_path = None
        self._interference_result = None

    def clear_interference_result(self) -> None:
        self._interference_result = None

    def check_adjacent_layer_interference(
        self,
        *,
        surface_meshes: Sequence[object],
        probe_diameter: float,
        probe_length: float,
        interpolation_samples: int = 20,
    ) -> InterferenceCheckResult:
        if self._scan_path is None or not self._scan_path.points:
            raise ValueError("No scan path is available for interference checking")
        if not surface_meshes:
            raise ValueError("No active surface mesh is available for interference checking")

        self._interference_result = check_adjacent_layer_interference(
            self._scan_path,
            surface_meshes=surface_meshes,
            probe_diameter=probe_diameter,
            probe_length=probe_length,
            interpolation_samples=interpolation_samples,
        )
        return self._interference_result

    def _apply_extracted_profile_segments(self, extracted_segments: ExtractedProfileSegments) -> None:
        for segment in extracted_segments.profile_segments:
            self._log_segment_geometry_state("[PROFILE_DEBUG] source", segment)
        self._source_profile_segments = {
            segment.segment_id: self._build_profile_segment(
                segment_id=segment.segment_id,
                points=list(segment.points),
                profile_side=segment.profile_side,
                is_enabled=segment.is_enabled,
                name=segment.name,
                segment_type=segment.segment_type,
                fit_center_x=segment.fit_center_x,
                fit_center_z=segment.fit_center_z,
                fit_radius=segment.fit_radius,
                fit_radius_valid=segment.fit_radius_valid,
                fit_residual=segment.fit_residual,
                arc_theta_start=segment.arc_theta_start,
                arc_theta_end=segment.arc_theta_end,
                arc_delta_theta=segment.arc_delta_theta,
                arc_direction=segment.arc_direction,
                arc_length=segment.arc_length,
                arc_geometry_valid=segment.arc_geometry_valid,
                line_start_x=segment.line_start_x,
                line_start_z=segment.line_start_z,
                line_end_x=segment.line_end_x,
                line_end_z=segment.line_end_z,
                line_length=segment.line_length,
                line_valid=segment.line_valid,
            )
            for segment in extracted_segments.profile_segments
        }
        self._compute_profile_global_z_bounds(self._source_profile_segments.values())
        self._ordered_segment_ids = self._suggest_initial_segment_order(extracted_segments.profile_segments)
        self._enabled_segment_ids = set(self._ordered_segment_ids)

    def _generate_scan_path_from_segments(self, params: ScanParams) -> ScanPath:
        points: list[PathPoint] = []
        running_offset = 0.0
        layer_index_offset = 0
        for group_index, group in enumerate(self._active_profile_group_segments):
            for segment in group:
                source_segment = self._source_profile_segments.get(int(segment.segment_id))
                source_vs_working_same = bool(source_segment is not None and source_segment == segment)
                print(f"[PATH_DEBUG] source_vs_working_same={source_vs_working_same}")
                segment_length = max(self._get_segment_effective_arc_length(segment), 0.0)
                local_start = max(params.s_start - running_offset, 0.0)
                local_end = min(params.s_end - running_offset, segment_length)

                if local_end - local_start <= 1e-9:
                    running_offset += segment_length
                    continue

                segment_path = generate_scan_path(
                    segment.points,
                    ScanParams(
                        s_start=local_start,
                        s_end=local_end,
                        layer_step=params.layer_step,
                        water_distance=params.water_distance,
                    ),
                    profile_kind=segment.profile_side,
                    reverse_offset_direction=self._reverse_offset_direction,
                    group_index=group_index,
                    segment_index=int(segment.segment_id),
                    segment_type=segment.segment_type,
                    fit_center_x=segment.fit_center_x,
                    fit_center_z=segment.fit_center_z,
                    fit_radius=segment.fit_radius,
                    fit_radius_valid=segment.fit_radius_valid,
                    arc_theta_start=segment.arc_theta_start,
                    arc_theta_end=segment.arc_theta_end,
                    arc_delta_theta=segment.arc_delta_theta,
                    arc_direction=segment.arc_direction,
                    arc_length=segment.arc_length,
                    arc_geometry_valid=segment.arc_geometry_valid,
                    line_start_x=segment.line_start_x,
                    line_start_z=segment.line_start_z,
                    line_end_x=segment.line_end_x,
                    line_end_z=segment.line_end_z,
                    line_length=segment.line_length,
                    line_valid=segment.line_valid,
                    flip_z_applied=self._flip_z_enabled,
                    flip_start_applied=self._flip_start_enabled,
                )
                for path_point in segment_path.points:
                    points.append(
                        PathPoint(
                            layer_index=layer_index_offset + int(path_point.layer_index),
                            arc_length=float(path_point.arc_length + running_offset),
                            surface_x=float(path_point.surface_x),
                            surface_z=float(path_point.surface_z),
                            probe_x=float(path_point.probe_x),
                            probe_y=float(path_point.probe_y),
                            probe_z=float(path_point.probe_z),
                            tilt_angle_deg=float(path_point.tilt_angle_deg),
                            group_index=group_index,
                            segment_index=int(segment.segment_id),
                        )
                    )

                if segment_path.points:
                    layer_index_offset = points[-1].layer_index + 1
                running_offset += segment_length

        if not points:
            raise ValueError("No enabled profile segments are available for path generation")
        return ScanPath(points=points)

    def _profile_stats(self) -> dict[str, object]:
        active_profile_points = self.profile_points
        if not active_profile_points:
            return {
                "profile_point_count": 0,
                "segment_count": len(self._ordered_segment_ids),
                "enabled_segment_count": len(self._enabled_segment_ids),
                "active_profile_group_count": 0,
                "min_x": 0.0,
                "max_x": 0.0,
                "min_z": 0.0,
                "max_z": 0.0,
            }

        x_values = [point[0] for point in active_profile_points]
        z_values = [point[1] for point in active_profile_points]
        return {
            "profile_point_count": len(active_profile_points),
            "segment_count": len(self._ordered_segment_ids),
            "enabled_segment_count": len(self._enabled_segment_ids),
            "active_profile_group_count": len(self._active_profile_groups),
            "min_x": min(x_values),
            "max_x": max(x_values),
            "min_z": min(z_values),
            "max_z": max(z_values),
        }

    def _reset_profile_state(self) -> None:
        self._source_profile_segments = {}
        self._ordered_segment_ids = []
        self._enabled_segment_ids = set()
        self._active_profile_points = []
        self._active_profile_groups = []
        self._active_profile_segments = []
        self._active_profile_group_segments = []
        self._active_profile_build_result = ActiveProfileBuildResult()
        self._scan_path = None
        self._interference_result = None
        self._profile_global_z_min = None
        self._profile_global_z_max = None

    def _build_profile_segment(
        self,
        *,
        segment_id: int,
        points: list[ProfilePoint],
        profile_side: str,
        is_enabled: bool,
        name: str | None = None,
        segment_type: str = "mixed",
        fit_center_x: float | None = None,
        fit_center_z: float | None = None,
        fit_radius: float | None = None,
        fit_radius_valid: bool = False,
        fit_residual: float | None = None,
        arc_theta_start: float | None = None,
        arc_theta_end: float | None = None,
        arc_delta_theta: float | None = None,
        arc_direction: int | None = None,
        arc_length: float | None = None,
        arc_geometry_valid: bool = False,
        line_start_x: float | None = None,
        line_start_z: float | None = None,
        line_end_x: float | None = None,
        line_end_z: float | None = None,
        line_length: float | None = None,
        line_valid: bool = False,
    ) -> ProfileSegment:
        x_values = [point[0] for point in points]
        z_values = [point[1] for point in points]
        derived_line_start_x = line_start_x
        derived_line_start_z = line_start_z
        derived_line_end_x = line_end_x
        derived_line_end_z = line_end_z
        derived_line_length = line_length
        derived_line_valid = line_valid if segment_type == "line" else False
        if segment_type == "line":
            if len(points) >= 2:
                derived_line_start_x = points[0][0]
                derived_line_start_z = points[0][1]
                derived_line_end_x = points[-1][0]
                derived_line_end_z = points[-1][1]
                derived_line_length = self._point_distance(points[0], points[-1])
                derived_line_valid = bool(derived_line_length and derived_line_length > 1e-9)
            else:
                derived_line_start_x = None
                derived_line_start_z = None
                derived_line_end_x = None
                derived_line_end_z = None
                derived_line_length = None
                derived_line_valid = False
        return ProfileSegment(
            segment_id=segment_id,
            name=name or f"segment_{segment_id}",
            points=list(points),
            point_count=len(points),
            x_min=min(x_values),
            x_max=max(x_values),
            z_min=min(z_values),
            z_max=max(z_values),
            polyline_length=self._compute_polyline_length(points),
            segment_type=segment_type,
            profile_side="inner" if str(profile_side).strip().lower() == "inner" else "outer",
            is_enabled=bool(is_enabled),
            fit_center_x=fit_center_x,
            fit_center_z=fit_center_z,
            fit_radius=fit_radius,
            fit_radius_valid=fit_radius_valid,
            fit_residual=fit_residual,
            arc_theta_start=arc_theta_start,
            arc_theta_end=arc_theta_end,
            arc_delta_theta=arc_delta_theta,
            arc_direction=arc_direction,
            arc_length=arc_length,
            arc_geometry_valid=arc_geometry_valid,
            line_start_x=derived_line_start_x,
            line_start_z=derived_line_start_z,
            line_end_x=derived_line_end_x,
            line_end_z=derived_line_end_z,
            line_length=derived_line_length,
            line_valid=derived_line_valid,
        )

    def _clone_profile_segment(
        self,
        segment: ProfileSegment,
        *,
        points: Sequence[ProfilePoint] | None = None,
        is_enabled: bool | None = None,
        profile_side: str | None = None,
        fit_center_z: float | None = None,
    ) -> ProfileSegment:
        """Clone one segment while preserving its full geometry metadata by default."""

        resolved_points = list(points) if points is not None else list(segment.points)
        resolved_fit_center_z = segment.fit_center_z if fit_center_z is None else fit_center_z
        return self._build_profile_segment(
            segment_id=segment.segment_id,
            points=resolved_points,
            profile_side=segment.profile_side if profile_side is None else profile_side,
            is_enabled=segment.is_enabled if is_enabled is None else is_enabled,
            name=segment.name,
            segment_type=segment.segment_type,
            fit_center_x=segment.fit_center_x,
            fit_center_z=resolved_fit_center_z,
            fit_radius=segment.fit_radius,
            fit_radius_valid=segment.fit_radius_valid,
            fit_residual=segment.fit_residual,
            arc_theta_start=segment.arc_theta_start,
            arc_theta_end=segment.arc_theta_end,
            arc_delta_theta=segment.arc_delta_theta,
            arc_direction=segment.arc_direction,
            arc_length=segment.arc_length,
            arc_geometry_valid=segment.arc_geometry_valid,
            line_start_x=segment.line_start_x,
            line_start_z=segment.line_start_z,
            line_end_x=segment.line_end_x,
            line_end_z=segment.line_end_z,
            line_length=segment.line_length,
            line_valid=segment.line_valid,
        )

    def _log_segment_geometry_state(self, prefix: str, segment: ProfileSegment) -> None:
        """Log one segment's retained analytic geometry fields for rebuild diagnostics."""

        fit_radius_value = segment.fit_radius if segment.fit_radius is not None else float("nan")
        fit_center_x = segment.fit_center_x if segment.fit_center_x is not None else float("nan")
        fit_center_z = segment.fit_center_z if segment.fit_center_z is not None else float("nan")
        print(
            f"{prefix} "
            f"segment={segment.segment_id} "
            f"type={segment.segment_type} "
            f"fit_valid={segment.fit_radius_valid} "
            f"fit_radius={fit_radius_value:.6f} "
            f"fit_center=({fit_center_x:.6f}, {fit_center_z:.6f})"
        )

    def _get_segment_effective_arc_length(self, segment: ProfileSegment) -> float:
        """Return the single authoritative arc-length value for one working segment."""

        if (
            segment.segment_type == "arc"
            and segment.arc_geometry_valid
            and segment.arc_length is not None
            and segment.arc_length > 0.0
        ):
            return float(segment.arc_length)
        return float(segment.polyline_length)

    def _get_group_effective_arc_length(self, group: Sequence[ProfileSegment]) -> float:
        """Return the authoritative total arc length for one active profile group."""

        return sum(self._get_segment_effective_arc_length(segment) for segment in group)

    def _compute_continuity_warning_threshold(self, profile_segments: Sequence[ProfileSegment]) -> float:
        x_values: list[float] = []
        z_values: list[float] = []
        for segment in profile_segments:
            for point_x, point_z in segment.points:
                x_values.append(point_x)
                z_values.append(point_z)

        if not x_values or not z_values:
            return 1e-6

        span = max(max(x_values) - min(x_values), max(z_values) - min(z_values), 1.0)
        return span * CONTINUITY_WARNING_RATIO

    def _compute_polyline_length(self, points: Sequence[ProfilePoint]) -> float:
        return sum(self._point_distance(points[index - 1], points[index]) for index in range(1, len(points)))

    def _point_distance(self, point_a: ProfilePoint, point_b: ProfilePoint) -> float:
        dx = float(point_a[0]) - float(point_b[0])
        dz = float(point_a[1]) - float(point_b[1])
        return (dx * dx + dz * dz) ** 0.5

    def _points_are_close(self, point_a: ProfilePoint, point_b: ProfilePoint) -> bool:
        return self._point_distance(point_a, point_b) <= 1e-6

    def _suggest_initial_segment_order(self, profile_segments: Sequence[ProfileSegment]) -> list[int]:
        if not profile_segments:
            return []
        if len(profile_segments) == 1:
            return [profile_segments[0].segment_id]

        remaining = {segment.segment_id: segment for segment in profile_segments}
        start_segment = min(profile_segments, key=lambda segment: (segment.z_min, segment.x_min, segment.segment_id))
        ordered_ids = [start_segment.segment_id]
        current_segment = start_segment
        remaining.pop(start_segment.segment_id, None)

        while remaining:
            current_endpoints = (current_segment.points[0], current_segment.points[-1])
            next_segment = min(
                remaining.values(),
                key=lambda segment: min(
                    self._point_distance(endpoint, candidate_endpoint)
                    for endpoint in current_endpoints
                    for candidate_endpoint in (segment.points[0], segment.points[-1])
                ),
            )
            ordered_ids.append(next_segment.segment_id)
            current_segment = next_segment
            remaining.pop(next_segment.segment_id, None)

        return ordered_ids

    def _apply_profile_group_transform_options(
        self,
        oriented_group_segments: Sequence[Sequence[ProfileSegment]],
    ) -> tuple[list[list[ProfilePoint]], list[list[ProfileSegment]]]:
        transformed_group_segments: list[list[ProfileSegment]] = []
        for group in oriented_group_segments:
            transformed_group_segments.append([self._clone_profile_segment(segment, is_enabled=True) for segment in group])

        if not transformed_group_segments:
            return [], []

        if self._flip_z_enabled:
            transformed_group_segments = [
                [
                    self._build_working_segment_variant(
                        segment,
                        points=self._flip_points_z_with_global_bounds(segment.points),
                        is_enabled=True,
                        flip_z_applied=True,
                    )
                    for segment in group
                ]
                for group in transformed_group_segments
            ]

        if self._flip_start_enabled:
            transformed_group_segments = [
                [
                    self._build_working_segment_variant(
                        segment,
                        points=list(reversed(segment.points)),
                        is_enabled=True,
                        reverse_applied=True,
                    )
                    for segment in reversed(group)
                ]
                for group in reversed(transformed_group_segments)
            ]

        for group in transformed_group_segments:
            for segment in group:
                points_transformed = bool(self._flip_z_enabled or self._flip_start_enabled)
                analytic_transformed = bool(
                    (segment.segment_type == "arc" and (self._flip_z_enabled or self._flip_start_enabled))
                    or (segment.segment_type == "line" and (self._flip_z_enabled or self._flip_start_enabled))
                )
                print(
                    f"[PROFILE_DEBUG] working segment={segment.segment_id} "
                    f"transformed_points_applied={points_transformed}"
                )
                print(
                    f"[PROFILE_DEBUG] working segment={segment.segment_id} "
                    f"analytic_geometry_transformed={analytic_transformed}"
                )
                print(
                    f"[PROFILE_DEBUG] working segment={segment.segment_id} "
                    f"points_vs_analytic_consistent={self._points_vs_analytic_consistent(segment)}"
                )

        transformed_groups: list[list[ProfilePoint]] = []
        for group in transformed_group_segments:
            rebuilt_group: list[ProfilePoint] = []
            for segment in group:
                if not rebuilt_group:
                    rebuilt_group.extend(segment.points)
                elif self._points_are_close(rebuilt_group[-1], segment.points[0]):
                    rebuilt_group.extend(segment.points[1:])
                else:
                    rebuilt_group.extend(segment.points)
            transformed_groups.append(rebuilt_group)

        return transformed_groups, transformed_group_segments

    def _build_working_segment_variant(
        self,
        segment: ProfileSegment,
        *,
        points: Sequence[ProfilePoint],
        is_enabled: bool,
        flip_z_applied: bool = False,
        reverse_applied: bool = False,
    ) -> ProfileSegment:
        """Build one working-segment variant whose analytic geometry matches its transformed points."""

        fit_center_z = segment.fit_center_z
        arc_theta_start = segment.arc_theta_start
        arc_theta_end = segment.arc_theta_end
        arc_delta_theta = segment.arc_delta_theta
        arc_direction = segment.arc_direction
        arc_length = segment.arc_length

        if flip_z_applied:
            fit_center_z = self._flip_z_value(fit_center_z)
            if (
                segment.segment_type == "arc"
                and arc_theta_start is not None
                and arc_theta_end is not None
                and arc_delta_theta is not None
                and arc_direction is not None
            ):
                arc_theta_start = -arc_theta_start
                arc_theta_end = -arc_theta_end
                arc_delta_theta = -arc_delta_theta
                arc_direction = -int(arc_direction)

        if reverse_applied and segment.segment_type == "arc":
            if (
                arc_theta_start is not None
                and arc_theta_end is not None
                and arc_delta_theta is not None
                and arc_direction is not None
            ):
                original_start = arc_theta_start
                arc_theta_start = arc_theta_end
                arc_theta_end = original_start
                arc_delta_theta = -arc_delta_theta
                arc_direction = -int(arc_direction)

        return self._build_profile_segment(
            segment_id=segment.segment_id,
            points=list(points),
            profile_side=segment.profile_side,
            is_enabled=is_enabled,
            name=segment.name,
            segment_type=segment.segment_type,
            fit_center_x=segment.fit_center_x,
            fit_center_z=fit_center_z,
            fit_radius=segment.fit_radius,
            fit_radius_valid=segment.fit_radius_valid,
            fit_residual=segment.fit_residual,
            arc_theta_start=arc_theta_start,
            arc_theta_end=arc_theta_end,
            arc_delta_theta=arc_delta_theta,
            arc_direction=arc_direction,
            arc_length=arc_length,
            arc_geometry_valid=segment.arc_geometry_valid,
            line_start_x=segment.line_start_x,
            line_start_z=segment.line_start_z,
            line_end_x=segment.line_end_x,
            line_end_z=segment.line_end_z,
            line_length=segment.line_length,
            line_valid=segment.line_valid,
        )

    def _flip_z_value(self, z_value: float | None) -> float | None:
        """Mirror one scalar Z value across the stable global profile bounds."""

        if z_value is None or self._profile_global_z_min is None or self._profile_global_z_max is None:
            return z_value
        return float(self._profile_global_z_min) + float(self._profile_global_z_max) - float(z_value)

    def _points_vs_analytic_consistent(self, segment: ProfileSegment) -> bool:
        """Return whether one working segment's analytic geometry matches its current points."""

        if len(segment.points) < 2:
            return True
        if segment.segment_type == "line":
            if not segment.line_valid or segment.line_start_x is None or segment.line_start_z is None:
                return True
            if segment.line_end_x is None or segment.line_end_z is None or segment.line_length is None:
                return False
            start_matches = self._points_are_close(segment.points[0], (segment.line_start_x, segment.line_start_z))
            end_matches = self._points_are_close(segment.points[-1], (segment.line_end_x, segment.line_end_z))
            length_matches = math.isclose(
                self._point_distance(segment.points[0], segment.points[-1]),
                float(segment.line_length),
                abs_tol=1e-6,
            )
            return start_matches and end_matches and length_matches

        if segment.segment_type == "arc":
            if (
                not segment.arc_geometry_valid
                or segment.fit_center_x is None
                or segment.fit_center_z is None
                or segment.fit_radius is None
                or segment.arc_theta_start is None
                or segment.arc_theta_end is None
                or segment.arc_delta_theta is None
                or segment.arc_direction is None
                or segment.arc_length is None
            ):
                return True
            start_angle = math.atan2(
                segment.points[0][1] - float(segment.fit_center_z),
                segment.points[0][0] - float(segment.fit_center_x),
            )
            end_angle = math.atan2(
                segment.points[-1][1] - float(segment.fit_center_z),
                segment.points[-1][0] - float(segment.fit_center_x),
            )
            start_matches = math.isclose(
                self._wrap_radians_difference(float(segment.arc_theta_start) - start_angle),
                0.0,
                abs_tol=1e-6,
            )
            end_matches = math.isclose(
                self._wrap_radians_difference(float(segment.arc_theta_end) - end_angle),
                0.0,
                abs_tol=1e-6,
            )
            direction_matches = int(segment.arc_direction) in {-1, 1}
            length_matches = float(segment.arc_length) > 0.0
            return start_matches and end_matches and direction_matches and length_matches

        return True

    def _wrap_radians_difference(self, delta_rad: float) -> float:
        """Wrap one radian delta into the shortest signed interval for geometry checks."""

        wrapped = (delta_rad + math.pi) % (2.0 * math.pi) - math.pi
        if math.isclose(wrapped, -math.pi, abs_tol=1e-9) and delta_rad > 0.0:
            return math.pi
        return wrapped

    def _compute_profile_global_z_bounds(self, profile_segments: Sequence[ProfileSegment]) -> None:
        """Compute stable global Z bounds once from extracted raw profile segments."""

        z_values = [point_z for segment in profile_segments for _point_x, point_z in segment.points]
        if not z_values:
            self._profile_global_z_min = None
            self._profile_global_z_max = None
            return

        self._profile_global_z_min = min(z_values)
        self._profile_global_z_max = max(z_values)

    def _flip_points_z_with_global_bounds(self, points: Sequence[ProfilePoint]) -> list[ProfilePoint]:
        """Mirror points across stable extracted-profile global Z bounds."""

        if self._profile_global_z_min is None or self._profile_global_z_max is None:
            return list(points)

        global_z_min = float(self._profile_global_z_min)
        global_z_max = float(self._profile_global_z_max)
        return [
            (point_x, global_z_min + global_z_max - point_z)
            for point_x, point_z in points
        ]

    def _build_standard_rows(self, points: list[PathPoint]) -> list[dict[str, float]]:
        return [
            {
                "group_index": float(point.group_index),
                "layer_index": float(point.layer_index),
                "segment_index": float(point.segment_index),
                "arc_length": float(point.arc_length),
                "surface_x": float(point.surface_x),
                "surface_z": float(point.surface_z),
                "probe_x": float(point.probe_x),
                "probe_y": float(point.probe_y),
                "probe_z": float(point.probe_z),
                "tilt_angle_deg": float(point.tilt_angle_deg),
            }
            for point in points
        ]

    def _build_compact_rows(self, points: list[PathPoint]) -> list[dict[str, float]]:
        return [
            {
                "Group": float(point.group_index),
                "Segment": float(point.segment_index),
                "X": float(point.probe_x),
                "Y": float(point.probe_y),
                "Z": float(point.probe_z),
                "Angle": float(point.tilt_angle_deg),
            }
            for point in points
        ]
