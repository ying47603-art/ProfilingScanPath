"""PyVista-based 3D preview widget for profile and scan-path data."""

from __future__ import annotations

import math
from typing import Iterable, Optional

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.path_planner import split_profile_segments, split_scan_path_segments
from data.models import InterferenceCheckResult, ProfileSegment, ScanPath


class ProfilePreview3DWidget(QWidget):
    """Render active/inactive revolved profiles and the generated scan path."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Create the embedded PyVista view and initialize the empty scene."""

        super().__init__(parent)
        self._profile_points: list[tuple[float, float]] = []
        self._profile_groups: list[list[tuple[float, float]]] = []
        self._reference_profile_points: list[tuple[float, float]] = []
        self._enabled_profile_segments: list[ProfileSegment] = []
        self._disabled_profile_segments: list[ProfileSegment] = []
        self._scan_path: Optional[ScanPath] = None

        self._show_profile = True
        self._show_scan_path = True
        self._show_revolution_wireframe = True
        self._show_surface = False
        self._show_axes = True
        self._show_axis_line = True
        self._show_text_labels = False

        self._render_mode = "wireframe"
        self._revolve_resolution = 36
        self._surface_opacity = 0.35
        self._smooth_shading = True
        self._auto_fit_camera = True
        self._show_probe_body = True
        self._show_probe_line = True
        self._probe_diameter = 10.0
        self._probe_length = 20.0
        self._current_probe_index: Optional[int] = None

        self._wireframe_cache_key: tuple[tuple[tuple[float, float], ...], int] | None = None
        self._wireframe_meshes: list[pv.PolyData] = []
        self._surface_cache_key: tuple[tuple[tuple[float, float], ...], int] | None = None
        self._surface_meshes: list[pv.PolyData] = []
        self._scan_path_segment_polylines: list[pv.PolyData] = []
        self._scan_path_points_3d: list[tuple[float, float, float]] = []
        self._interference_segments: list[tuple[tuple[float, float, float], tuple[float, float, float], bool]] = []
        self._interference_points: list[tuple[float, float, float]] = []
        self._camera_initialized = False

        self._plotter = QtInteractor(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plotter)

        self.refresh_view()

    def set_profile_points(
        self,
        profile_points: Iterable[tuple[float, float]],
        *,
        refresh: bool = True,
    ) -> None:
        """Store and display the currently active profile points."""

        self._profile_points = list(profile_points)
        self._profile_groups = [list(self._profile_points)] if len(self._profile_points) >= 2 else []
        self._invalidate_profile_geometry()
        if refresh:
            self.refresh_view()

    def set_profile_groups(
        self,
        profile_groups: Iterable[Iterable[tuple[float, float]]],
        *,
        refresh: bool = True,
    ) -> None:
        """Store active working-profile groups without introducing cross-group connectors."""

        normalized_groups = [list(group) for group in profile_groups]
        self._profile_groups = [group for group in normalized_groups if len(group) >= 2]
        self._profile_points = [point for group in self._profile_groups for point in group]
        self._invalidate_profile_geometry()
        if refresh:
            self.refresh_view()

    def set_reference_profile_points(
        self,
        profile_points: Iterable[tuple[float, float]],
        *,
        refresh: bool = True,
    ) -> None:
        """Store and display the inactive profile points as weak reference geometry."""

        self._reference_profile_points = list(profile_points)
        if refresh:
            self.refresh_view()

    def set_profile_segments(
        self,
        *,
        enabled_segments: Iterable[ProfileSegment],
        disabled_segments: Iterable[ProfileSegment],
        refresh: bool = True,
    ) -> None:
        """Store explicit enabled/disabled segments for segment-first 3D rendering."""

        self._enabled_profile_segments = [
            ProfileSegment(
                segment_id=segment.segment_id,
                name=segment.name,
                points=list(segment.points),
                point_count=segment.point_count,
                x_min=segment.x_min,
                x_max=segment.x_max,
                z_min=segment.z_min,
                z_max=segment.z_max,
                polyline_length=segment.polyline_length,
                segment_type=segment.segment_type,
                profile_side=segment.profile_side,
                is_enabled=True,
            )
            for segment in enabled_segments
        ]
        self._disabled_profile_segments = [
            ProfileSegment(
                segment_id=segment.segment_id,
                name=segment.name,
                points=list(segment.points),
                point_count=segment.point_count,
                x_min=segment.x_min,
                x_max=segment.x_max,
                z_min=segment.z_min,
                z_max=segment.z_max,
                polyline_length=segment.polyline_length,
                segment_type=segment.segment_type,
                profile_side=segment.profile_side,
                is_enabled=False,
            )
            for segment in disabled_segments
        ]
        self._invalidate_profile_geometry()
        if refresh:
            self.refresh_view()

    def set_scan_path(self, scan_path: Optional[ScanPath], *, refresh: bool = True) -> None:
        """Store and display the latest generated scan path."""

        self._scan_path = scan_path
        self._invalidate_scan_path_geometry()
        if refresh:
            self.refresh_view()

    def set_interference_results(self, result: Optional[InterferenceCheckResult]) -> None:
        """Store adjacent-layer interference visuals and refresh immediately."""

        if result is None:
            self.clear_interference_visuals(refresh=False)
        else:
            self._interference_segments = [
                (pair_result.start_center, pair_result.end_center, pair_result.collided)
                for pair_result in result.pair_results
            ]
            self._interference_points = [
                (
                    pair_result.collision_sample.center_x,
                    pair_result.collision_sample.center_y,
                    pair_result.collision_sample.center_z,
                )
                for pair_result in result.pair_results
                if pair_result.collision_sample is not None
            ]
        self.refresh_view()

    def clear_interference_visuals(self, *, refresh: bool = True) -> None:
        """Clear all adjacent-layer interference summary visuals."""

        self._interference_segments = []
        self._interference_points = []
        if refresh:
            self.refresh_view()

    def get_active_surface_meshes_for_analysis(self) -> list[pv.PolyData]:
        """Return active-profile surface meshes for analysis regardless of display mode."""

        analysis_resolution = max(self._revolve_resolution, 36)
        return [
            surface_mesh.copy(deep=True)
            for surface_mesh in self._build_surface_meshes(
                self._get_active_surface_segments(),
                analysis_resolution,
            )
        ]

    def clear_preview(self) -> None:
        """Clear rendered profiles, path data, and cached active geometry."""

        self._profile_points = []
        self._profile_groups = []
        self._reference_profile_points = []
        self._enabled_profile_segments = []
        self._disabled_profile_segments = []
        self._scan_path = None
        self._invalidate_profile_geometry()
        self._invalidate_scan_path_geometry()
        self.clear_interference_visuals(refresh=False)
        self.refresh_view()

    def set_display_options(
        self,
        *,
        show_profile: bool = True,
        show_scan_path: bool = True,
        show_revolution_wireframe: bool = True,
        show_surface: bool = False,
        show_axes: bool = True,
        show_axis_line: bool = True,
        show_text_labels: bool = False,
        refresh: bool = True,
    ) -> None:
        """Update display-layer visibility and optionally refresh immediately."""

        self._show_profile = show_profile
        self._show_scan_path = show_scan_path
        self._show_revolution_wireframe = show_revolution_wireframe
        self._show_surface = show_surface
        self._show_axes = show_axes
        self._show_axis_line = show_axis_line
        self._show_text_labels = show_text_labels
        if refresh:
            self.refresh_view()

    def set_render_mode(self, render_mode: str, *, refresh: bool = True) -> None:
        """Set the current 3D render mode and optionally refresh immediately."""

        normalized_mode = render_mode if render_mode in {"wireframe", "surface_low", "surface_high"} else "wireframe"
        if normalized_mode != self._render_mode:
            self._render_mode = normalized_mode
            self._invalidate_surface_geometry()
        if refresh:
            self.refresh_view()

    def set_surface_options(
        self,
        *,
        revolve_resolution: Optional[int] = None,
        surface_opacity: Optional[float] = None,
        smooth_shading: Optional[bool] = None,
        refresh: bool = True,
    ) -> None:
        """Update surface-related options and optionally refresh immediately."""

        if revolve_resolution is not None:
            clamped_resolution = max(12, int(revolve_resolution))
            if clamped_resolution != self._revolve_resolution:
                self._revolve_resolution = clamped_resolution
                self._invalidate_surface_geometry()
                self._invalidate_wireframe_geometry()

        if surface_opacity is not None:
            self._surface_opacity = max(0.05, min(1.0, float(surface_opacity)))

        if smooth_shading is not None:
            self._smooth_shading = bool(smooth_shading)

        if refresh:
            self.refresh_view()

    def set_camera_options(self, *, auto_fit_camera: Optional[bool] = None, refresh: bool = True) -> None:
        """Update camera behavior and optionally refresh immediately."""

        if auto_fit_camera is not None:
            self._auto_fit_camera = bool(auto_fit_camera)

        if refresh:
            self.refresh_view()

    def set_probe_pose_options(
        self,
        *,
        show_probe_body: Optional[bool] = None,
        show_probe_line: Optional[bool] = None,
        probe_diameter: Optional[float] = None,
        probe_length: Optional[float] = None,
        refresh: bool = True,
    ) -> None:
        """Update current-probe visualization options and refresh when requested."""

        if show_probe_body is not None:
            self._show_probe_body = bool(show_probe_body)
        if show_probe_line is not None:
            self._show_probe_line = bool(show_probe_line)
        if probe_diameter is not None:
            self._probe_diameter = max(0.1, float(probe_diameter))
        if probe_length is not None:
            self._probe_length = max(0.1, float(probe_length))

        if refresh:
            self.refresh_view()

    def set_current_probe_index(self, index: Optional[int], *, refresh: bool = True) -> None:
        """Set which scan-path point should drive the single-probe preview."""

        self._current_probe_index = index
        if refresh:
            self.refresh_view()

    def clear_probe_pose(self, *, refresh: bool = True) -> None:
        """Clear the current single-probe preview selection."""

        self._current_probe_index = None
        if refresh:
            self.refresh_view()

    def reset_camera_view(self) -> None:
        """Reset the scene camera to the default engineering view."""

        self._set_default_camera(axis_length=self._compute_axis_length())
        self._plotter.render()

    def refresh_view(self) -> None:
        """Redraw the 3D scene from the current profile and scan-path state."""

        saved_camera = None
        if not self._auto_fit_camera and self._camera_initialized:
            saved_camera = self._capture_camera_position()

        self._plotter.clear()
        self._plotter.set_background("#fbfbfb")
        scene_bounds = self._get_scene_bounds()

        if self._show_axes:
            self._plotter.add_axes(line_width=2, labels_off=False)
            self._plotter.show_grid(
                color="#e0e0e0",
                bounds=scene_bounds,
                location="outer",
                xtitle="X",
                ytitle="Y",
                ztitle="Z",
            )

        axis_length = self._compute_axis_length()
        axis_line_bounds = scene_bounds or (-100.0, 100.0, -100.0, 100.0, 0.0, 100.0)

        if self._show_axis_line:
            self._draw_rotation_axis(axis_line_bounds)

        surface_mode_active = self._is_surface_mode()
        active_profile_segments = self._get_active_profile_segments()

        if surface_mode_active and self._show_surface and active_profile_segments:
            for surface_mesh in self._get_surface_meshes():
                self._plotter.add_mesh(
                    surface_mesh,
                    color="#9ecae1",
                    opacity=self._surface_opacity,
                    smooth_shading=self._smooth_shading,
                    show_edges=False,
                )

        if self._show_profile and self._disabled_profile_segments:
            self._draw_profile_segments(
                [segment.points for segment in self._disabled_profile_segments if len(segment.points) >= 2],
                color="#93b3cb",
                line_width=1.3,
                opacity=0.28,
                show_endpoints=False,
            )

        if self._show_profile and active_profile_segments:
            self._draw_profile_segments(
                active_profile_segments,
                color="#1f77b4",
                line_width=2.0,
                opacity=1.0,
                show_endpoints=True,
            )

        if self._show_revolution_wireframe and active_profile_segments and not surface_mode_active:
            self._draw_revolution_wireframe(surface_mode=surface_mode_active)

        if self._show_scan_path and self._scan_path is not None and self._scan_path.points:
            self._draw_scan_path()

        self._draw_interference_segments()
        self._draw_current_probe_pose()

        if self._auto_fit_camera or saved_camera is None:
            self._set_default_camera(axis_length=axis_length, scene_bounds=scene_bounds)
        else:
            self._plotter.camera_position = saved_camera

        self._camera_initialized = True

    def _draw_current_probe_pose(self) -> None:
        """Draw the currently selected single-probe pose, if available."""

        pose = self._build_current_probe_pose()
        if pose is None:
            return

        probe_tip, surface_point, direction = pose

        if self._show_probe_body:
            probe_body_center = probe_tip - direction * (self._probe_length * 0.5)
            probe_body = pv.Cylinder(
                center=probe_body_center,
                direction=direction,
                radius=self._probe_diameter * 0.5,
                height=self._probe_length,
                resolution=24,
            )
            self._plotter.add_mesh(
                probe_body,
                color="#9aa7b4",
                opacity=0.55,
                smooth_shading=True,
            )

        if self._show_probe_line:
            for beam_segment in self._build_dashed_probe_line(probe_tip, surface_point):
                self._plotter.add_mesh(
                    beam_segment,
                    color="#d62728",
                    line_width=2.2,
                    opacity=0.95,
                )

    def _build_current_probe_pose(
        self,
    ) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """Build tip point, surface point, and axis direction for the current probe."""

        if self._scan_path is None or not self._scan_path.points:
            return None
        if self._current_probe_index is None:
            return None
        if not 0 <= self._current_probe_index < len(self._scan_path.points):
            return None

        point = self._scan_path.points[self._current_probe_index]
        probe_tip = np.asarray(
            [point.probe_x, point.probe_y, point.probe_z],
            dtype=float,
        )
        surface_point = np.asarray(
            [point.surface_x, 0.0, point.surface_z],
            dtype=float,
        )
        direction = surface_point - probe_tip
        norm = np.linalg.norm(direction)
        if math.isclose(float(norm), 0.0):
            return None
        direction /= norm
        return probe_tip, surface_point, direction

    def _build_dashed_probe_line(
        self,
        start_point: np.ndarray,
        end_point: np.ndarray,
    ) -> list[pv.PolyData]:
        """Build short line segments that visually approximate a dashed beam line."""

        vector = end_point - start_point
        total_length = float(np.linalg.norm(vector))
        if math.isclose(total_length, 0.0):
            return []

        direction = vector / total_length
        dash_length = max(total_length * 0.12, 1.2)
        gap_length = dash_length * 0.7

        dashed_segments: list[pv.PolyData] = []
        current_length = 0.0
        while current_length < total_length:
            segment_start = start_point + direction * current_length
            segment_end_length = min(current_length + dash_length, total_length)
            segment_end = start_point + direction * segment_end_length
            dashed_segments.append(
                pv.Line(tuple(segment_start), tuple(segment_end), resolution=1)
            )
            current_length += dash_length + gap_length

        return dashed_segments

    def _is_surface_mode(self) -> bool:
        """Return whether the current render mode is a true surface mode."""

        return self._render_mode in {"surface_low", "surface_high"}

    def _invalidate_profile_geometry(self) -> None:
        """Clear cached geometry derived from the current active profile points."""

        self._invalidate_wireframe_geometry()
        self._invalidate_surface_geometry()

    def _invalidate_wireframe_geometry(self) -> None:
        """Clear cached revolution wireframe geometry."""

        self._wireframe_cache_key = None
        self._wireframe_meshes = []

    def _invalidate_surface_geometry(self) -> None:
        """Clear cached revolution surface geometry."""

        self._surface_cache_key = None
        self._surface_meshes = []

    def _invalidate_scan_path_geometry(self) -> None:
        """Clear cached geometry derived from the current scan path."""

        self._scan_path_segment_polylines = []
        self._scan_path_points_3d = []

    def _draw_interference_segments(self) -> None:
        """Draw adjacent-layer transition summaries and collision points."""

        for start_point, end_point, collided in self._interference_segments:
            self._plotter.add_mesh(
                pv.Line(start_point, end_point, resolution=1),
                color="#d62728" if collided else "#9d93d6",
                line_width=3.2 if collided else 1.8,
                opacity=0.95 if collided else 0.62,
            )

        if not self._interference_points:
            return

        marker_scale = self._compute_marker_scale() * 0.32
        for collision_point in self._interference_points:
            collision_marker = pv.Sphere(radius=marker_scale, center=collision_point)
            self._plotter.add_mesh(
                collision_marker,
                color="#d62728",
                smooth_shading=True,
                opacity=0.96,
            )

    def _compute_axis_length(self) -> float:
        """Return a scene scale suitable for the axis helper."""

        scene_bounds = self._get_scene_bounds()
        if scene_bounds is None:
            return 120.0

        x_span = scene_bounds[1] - scene_bounds[0]
        y_span = scene_bounds[3] - scene_bounds[2]
        z_span = scene_bounds[5] - scene_bounds[4]
        return max(x_span, y_span, z_span, 20.0) * 1.2

    def _compute_marker_scale(self) -> float:
        """Return a readable scale for profile endpoint markers."""

        return max(self._compute_axis_length() * 0.024, 1.1)

    def _draw_rotation_axis(
        self,
        scene_bounds: tuple[float, float, float, float, float, float],
    ) -> None:
        """Draw the global Z-axis used as the current rotation axis."""

        z_min = min(0.0, float(scene_bounds[4]))
        z_max = max(1.0, float(scene_bounds[5]))
        z_span = max(z_max - z_min, 1.0)
        axis_top = z_max + z_span * 0.03
        axis = pv.Line((0.0, 0.0, z_min), (0.0, 0.0, axis_top), resolution=1)
        self._plotter.add_mesh(axis, color="#8c8c8c", line_width=2.2, opacity=0.82)

    def _draw_profile_segments(
        self,
        profile_segments: list[list[tuple[float, float]]],
        *,
        color: str,
        line_width: float,
        opacity: float,
        show_endpoints: bool,
    ) -> None:
        """Draw one ordered profile segment collection in the XZ plane."""

        profile_lines = self._build_profile_segment_polylines(profile_segments)
        if not profile_lines or not profile_segments:
            return

        for profile_line in profile_lines:
            self._plotter.add_mesh(
                profile_line,
                color=color,
                line_width=line_width,
                opacity=opacity,
            )

        if show_endpoints:
            start_point = (
                profile_segments[0][0][0],
                0.0,
                profile_segments[0][0][1],
            )
            end_point = (
                profile_segments[-1][-1][0],
                0.0,
                profile_segments[-1][-1][1],
            )
            self._draw_profile_endpoint_markers(start_point, end_point)

            if self._show_text_labels:
                self._plotter.add_point_labels(
                    np.asarray([start_point, end_point], dtype=float),
                    ["Start", "End"],
                    font_size=11,
                    text_color="#333333",
                    shape_opacity=0.15,
                    fill_shape=True,
                    show_points=False,
                    always_visible=True,
                )

    def _draw_profile_endpoint_markers(
        self,
        start_point: tuple[float, float, float],
        end_point: tuple[float, float, float],
    ) -> None:
        """Draw profile start/end markers matching the 2D preview semantics."""

        marker_scale = self._compute_marker_scale()
        start_marker = pv.Sphere(radius=marker_scale * 0.4, center=start_point)
        end_marker = pv.Cube(
            center=end_point,
            x_length=marker_scale * 0.5,
            y_length=marker_scale * 0.5,
            z_length=marker_scale * 0.5,
        )
        self._plotter.add_mesh(start_marker, color="#2ca02c", smooth_shading=True)
        self._plotter.add_mesh(end_marker, color="#d62728", smooth_shading=False)

    def _draw_revolution_wireframe(self, *, surface_mode: bool) -> None:
        """Draw sparse rotated profile copies to suggest the revolved shape."""

        color = "#d2d2d2" if surface_mode else "#bfbfbf"
        line_width = 0.55 if surface_mode else 0.95
        opacity = 0.14 if surface_mode else 0.34
        if not self._show_surface:
            opacity = 0.0
        for wire_mesh in self._get_wireframe_meshes():
            self._plotter.add_mesh(wire_mesh, color=color, line_width=line_width, opacity=opacity)

    def _draw_scan_path(self) -> None:
        """Draw the generated 3D scan path using probe coordinates."""

        path_points = self._get_scan_path_points_3d()
        path_lines = self._get_scan_path_segment_polylines()
        if not path_lines or not path_points:
            return

        for path_line in path_lines:
            self._plotter.add_mesh(
                path_line,
                color="#f28e2b",
                line_width=2.0,
                opacity=0.92,
            )
        self._draw_path_endpoint_markers(path_points[0], path_points[-1])

        if self._show_text_labels:
            self._plotter.add_point_labels(
                np.asarray([path_points[0], path_points[-1]], dtype=float),
                ["Start", "End"],
                font_size=10,
                text_color="#444444",
                shape_opacity=0.12,
                fill_shape=True,
                show_points=False,
                always_visible=True,
            )

    def _draw_path_endpoint_markers(
        self,
        start_point: tuple[float, float, float],
        end_point: tuple[float, float, float],
    ) -> None:
        """Draw scan-path start/end markers using the same semantics as the profile."""

        marker_scale = self._compute_marker_scale()
        start_marker = pv.Sphere(radius=marker_scale * 0.4, center=start_point)
        end_marker = pv.Cube(
            center=end_point,
            x_length=marker_scale * 0.5,
            y_length=marker_scale * 0.5,
            z_length=marker_scale * 0.5,
        )
        self._plotter.add_mesh(start_marker, color="#2ca02c", smooth_shading=True)
        self._plotter.add_mesh(end_marker, color="#d62728", smooth_shading=False)

    def _build_profile_segment_polylines(self, profile_points: list[tuple[float, float]]) -> list[pv.PolyData]:
        """Return segment polylines for one profile-segment collection."""

        segment_polylines: list[pv.PolyData] = []
        for segment in profile_points:
            if len(segment) < 2:
                continue
            segment_points_3d = [(x_value, 0.0, z_value) for x_value, z_value in segment]
            segment_polylines.append(self._polyline_from_points(segment_points_3d))
        return segment_polylines

    def _get_wireframe_meshes(self) -> list[pv.PolyData]:
        """Return cached sparse revolution wireframe meshes for the active profile."""

        active_profile_segments = self._get_active_profile_segments()
        if not active_profile_segments:
            return []

        profile_key = tuple(tuple(segment) for segment in active_profile_segments)
        wireframe_resolution = self._get_wireframe_copy_count()
        cache_key = (profile_key, wireframe_resolution)
        if self._wireframe_cache_key == cache_key and self._wireframe_meshes:
            return self._wireframe_meshes

        self._wireframe_cache_key = cache_key
        self._wireframe_meshes = []
        for profile_segment in active_profile_segments:
            for angle_deg in np.linspace(0.0, 360.0, wireframe_resolution, endpoint=False):
                angle_rad = math.radians(float(angle_deg))
                cos_angle = math.cos(angle_rad)
                sin_angle = math.sin(angle_rad)
                rotated_points = [
                    (x_value * cos_angle, x_value * sin_angle, z_value)
                    for x_value, z_value in profile_segment
                ]
                self._wireframe_meshes.append(self._polyline_from_points(rotated_points))
        return self._wireframe_meshes

    def _get_surface_meshes(self) -> list[pv.PolyData]:
        """Return cached revolved surface meshes built from active sidewall segments."""

        active_profile_segments = self._get_active_surface_segments()
        if not active_profile_segments or not self._is_surface_mode():
            return []

        effective_resolution = self._get_effective_surface_resolution()
        profile_key = tuple(tuple(segment) for segment in active_profile_segments)
        cache_key = (profile_key, effective_resolution)
        if self._surface_cache_key == cache_key and self._surface_meshes:
            return self._surface_meshes

        self._surface_cache_key = cache_key
        self._surface_meshes = self._build_surface_meshes(
            active_profile_segments,
            effective_resolution,
        )
        return self._surface_meshes

    def _get_active_surface_segments(self) -> list[list[tuple[float, float]]]:
        """Return active non-horizontal sidewall segments eligible for revolution."""

        sidewall_segments: list[list[tuple[float, float]]] = []
        for segment in self._get_active_profile_segments():
            sidewall_segments.extend(self._split_non_horizontal_sidewalls(segment))
        return [segment for segment in sidewall_segments if len(segment) >= 2]

    def _get_active_profile_segments(self) -> list[list[tuple[float, float]]]:
        """Return enabled ordered segments, falling back to the active polyline when needed."""

        enabled_segments = self.__dict__.get("_enabled_profile_segments", [])
        profile_groups = self.__dict__.get("_profile_groups", [])
        profile_points = self.__dict__.get("_profile_points", [])
        if enabled_segments:
            return [list(segment.points) for segment in enabled_segments if len(segment.points) >= 2]
        if profile_groups:
            return [list(group) for group in profile_groups if len(group) >= 2]
        if len(profile_points) < 2:
            return []
        return [segment for segment in split_profile_segments(profile_points) if len(segment) >= 2]

    def _split_non_horizontal_sidewalls(
        self,
        profile_segment: list[tuple[float, float]],
    ) -> list[list[tuple[float, float]]]:
        """Split one profile segment into non-horizontal sidewall runs for revolution only."""

        if len(profile_segment) < 2:
            return []

        sidewall_segments: list[list[tuple[float, float]]] = []
        current_segment: list[tuple[float, float]] = [profile_segment[0]]
        for next_point in profile_segment[1:]:
            current_point = current_segment[-1]
            if math.isclose(current_point[1], next_point[1], abs_tol=1e-9):
                if len(current_segment) >= 2:
                    sidewall_segments.append(current_segment)
                current_segment = [next_point]
                continue
            current_segment.append(next_point)

        if len(current_segment) >= 2:
            sidewall_segments.append(current_segment)
        return sidewall_segments

    def _build_surface_meshes(
        self,
        segments: list[list[tuple[float, float]]],
        resolution: int,
    ) -> list[pv.PolyData]:
        """Build revolved surface meshes from active non-horizontal sidewall segments."""

        if resolution < 3:
            return []

        surface_meshes: list[pv.PolyData] = []
        angles = np.linspace(0.0, 2.0 * math.pi, resolution + 1)
        for segment in segments:
            radii = np.asarray([point[0] for point in segment], dtype=float)
            z_values = np.asarray([point[1] for point in segment], dtype=float)
            x_grid = np.outer(np.cos(angles), radii)
            y_grid = np.outer(np.sin(angles), radii)
            z_grid = np.outer(np.ones_like(angles), z_values)
            surface_grid = pv.StructuredGrid(x_grid, y_grid, z_grid)
            surface_meshes.append(
                surface_grid.extract_surface(algorithm="dataset_surface").triangulate()
            )
        return surface_meshes

    def _get_scan_path_points_3d(self) -> list[tuple[float, float, float]]:
        """Return cached 3D probe points for the current scan path."""

        if not self._scan_path_points_3d and self._scan_path is not None and self._scan_path.points:
            self._scan_path_points_3d = [
                (point.probe_x, point.probe_y, point.probe_z)
                for point in self._scan_path.points
            ]
        return self._scan_path_points_3d

    def _get_scan_path_segment_polylines(self) -> list[pv.PolyData]:
        """Return cached polylines for each independent scan-path segment."""

        if self._scan_path_segment_polylines or self._scan_path is None or len(self._scan_path.points) < 2:
            return self._scan_path_segment_polylines

        segment_polylines: list[pv.PolyData] = []
        for segment in split_scan_path_segments(self._scan_path.points):
            if len(segment) < 2:
                continue
            segment_points = [
                (point.probe_x, point.probe_y, point.probe_z)
                for point in segment
            ]
            segment_polylines.append(self._polyline_from_points(segment_points))

        self._scan_path_segment_polylines = segment_polylines
        return self._scan_path_segment_polylines

    def _get_wireframe_copy_count(self) -> int:
        """Return a sparse wireframe count derived from the current revolve resolution."""

        return max(8, min(36, self._revolve_resolution // 2))

    def _get_effective_surface_resolution(self) -> int:
        """Return the effective surface resolution for the active render mode."""

        if self._render_mode == "surface_low":
            return self._revolve_resolution
        if self._render_mode == "surface_high":
            return self._revolve_resolution * 2
        return 0

    def _polyline_from_points(self, points: list[tuple[float, float, float]]) -> pv.PolyData:
        """Build a PyVista polyline from an ordered point list."""

        point_array = np.asarray(points, dtype=float)
        return pv.lines_from_points(point_array, close=False)

    def _get_scene_bounds(self) -> Optional[tuple[float, float, float, float, float, float]]:
        """Return stable scene bounds using active/reference profiles and the scan path."""

        x_values: list[float] = []
        y_values: list[float] = []
        z_values: list[float] = []

        if self._enabled_profile_segments or self._disabled_profile_segments:
            segment_groups = self._enabled_profile_segments + self._disabled_profile_segments
            for profile_segment in segment_groups:
                for x_value, z_value in profile_segment.points:
                    x_values.extend((-abs(x_value), abs(x_value)))
                    y_values.extend((-abs(x_value), abs(x_value)))
                    z_values.append(z_value)
        else:
            for profile_group in self._profile_groups:
                for x_value, z_value in profile_group:
                    x_values.extend((-abs(x_value), abs(x_value)))
                    y_values.extend((-abs(x_value), abs(x_value)))
                    z_values.append(z_value)
            for profile_points in (self._reference_profile_points,):
                if profile_points:
                    for x_value, z_value in profile_points:
                        x_values.extend((-abs(x_value), abs(x_value)))
                        y_values.extend((-abs(x_value), abs(x_value)))
                        z_values.append(z_value)

        if self._scan_path is not None and self._scan_path.points:
            for point in self._scan_path.points:
                x_values.append(point.probe_x)
                y_values.append(point.probe_y)
                z_values.append(point.probe_z)

        for start_point, end_point, _collided in self._interference_segments:
            for point in (start_point, end_point):
                x_values.append(point[0])
                y_values.append(point[1])
                z_values.append(point[2])

        for collision_point in self._interference_points:
            x_values.append(collision_point[0])
            y_values.append(collision_point[1])
            z_values.append(collision_point[2])

        if not x_values or not z_values:
            return None

        return (
            min(x_values),
            max(x_values),
            min(y_values),
            max(y_values),
            min(z_values),
            max(z_values),
        )

    def _capture_camera_position(self) -> Optional[list[tuple[float, float, float]]]:
        """Return the current camera position tuple when available."""

        camera_position = self._plotter.camera_position
        if not camera_position or len(camera_position) != 3:
            return None
        return [
            tuple(camera_position[0]),
            tuple(camera_position[1]),
            tuple(camera_position[2]),
        ]

    def _set_default_camera(
        self,
        axis_length: float,
        scene_bounds: Optional[tuple[float, float, float, float, float, float]] = None,
    ) -> None:
        """Apply a stable engineering-style camera from the right-front-top side."""

        bounds = scene_bounds or self._get_scene_bounds()
        if bounds is None:
            center = np.array([0.0, 0.0, axis_length * 0.35], dtype=float)
            span = axis_length
        else:
            center = np.array(
                [
                    (bounds[0] + bounds[1]) / 2.0,
                    (bounds[2] + bounds[3]) / 2.0,
                    (bounds[4] + bounds[5]) / 2.0,
                ],
                dtype=float,
            )
            span = max(
                bounds[1] - bounds[0],
                bounds[3] - bounds[2],
                bounds[5] - bounds[4],
                axis_length * 0.55,
            )

        distance = max(span * 3.8, axis_length * 2.3)
        direction = np.array([1.0, -0.82, 0.72], dtype=float)
        direction /= np.linalg.norm(direction)
        camera_position = center + direction * distance
        self._plotter.camera_position = [
            tuple(camera_position),
            tuple(center),
            (0.0, 0.0, 1.0),
        ]
