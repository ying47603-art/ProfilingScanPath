"""PyVista-based 3D preview widget for profile and scan-path data."""

from __future__ import annotations

import math
from typing import Iterable, Optional

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.path_planner import split_profile_segments, split_scan_path_segments
from data.models import ScanPath


class ProfilePreview3DWidget(QWidget):
    """Render a readable 3D view of the revolved profile and generated path."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Create the embedded PyVista view and initialize the empty scene."""

        super().__init__(parent)
        self._profile_points: list[tuple[float, float]] = []
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

        self._profile_polyline: Optional[pv.PolyData] = None
        self._profile_segment_polylines: list[pv.PolyData] = []
        self._profile_points_3d: list[tuple[float, float, float]] = []
        self._wireframe_cache_key: tuple[tuple[tuple[float, float], ...], int] | None = None
        self._wireframe_meshes: list[pv.PolyData] = []
        self._surface_cache_key: tuple[tuple[tuple[float, float], ...], int] | None = None
        self._surface_mesh: Optional[pv.PolyData] = None
        self._scan_path_polyline: Optional[pv.PolyData] = None
        self._scan_path_segment_polylines: list[pv.PolyData] = []
        self._scan_path_points_3d: list[tuple[float, float, float]] = []
        self._camera_initialized = False

        self._plotter = QtInteractor(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plotter)

        self.refresh_view()

    def set_profile_points(self, profile_points: Iterable[tuple[float, float]]) -> None:
        """Store and display the latest extracted profile points."""

        self._profile_points = list(profile_points)
        self._invalidate_profile_geometry()
        self.refresh_view()

    def set_scan_path(self, scan_path: Optional[ScanPath]) -> None:
        """Store and display the latest generated scan path."""

        self._scan_path = scan_path
        self._invalidate_scan_path_geometry()
        self.refresh_view()

    def clear_preview(self) -> None:
        """Clear both the rendered content and the internal preview state."""

        self._profile_points = []
        self._scan_path = None
        self._invalidate_profile_geometry()
        self._invalidate_scan_path_geometry()
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
        if surface_mode_active and self._show_surface and self._profile_points:
            surface_mesh = self._get_surface_mesh()
            if surface_mesh is not None:
                self._plotter.add_mesh(
                    surface_mesh,
                    color="#9ecae1",
                    opacity=self._surface_opacity,
                    smooth_shading=self._smooth_shading,
                    show_edges=False,
                )

        if self._show_profile and self._profile_points:
            self._draw_profile_polyline()

        if self._show_revolution_wireframe and self._profile_points and not surface_mode_active:
            self._draw_revolution_wireframe(surface_mode=surface_mode_active)

        if self._show_scan_path and self._scan_path is not None and self._scan_path.points:
            self._draw_scan_path()

        if self._auto_fit_camera or saved_camera is None:
            self._set_default_camera(axis_length=axis_length, scene_bounds=scene_bounds)
        else:
            self._plotter.camera_position = saved_camera

        self._camera_initialized = True

    def _is_surface_mode(self) -> bool:
        """Return whether the current render mode is a true surface mode."""

        return self._render_mode in {"surface_low", "surface_high"}

    def _invalidate_profile_geometry(self) -> None:
        """Clear cached geometry derived from the current profile points."""

        self._profile_polyline = None
        self._profile_segment_polylines = []
        self._profile_points_3d = []
        self._invalidate_wireframe_geometry()
        self._invalidate_surface_geometry()

    def _invalidate_wireframe_geometry(self) -> None:
        """Clear cached revolution wireframe geometry."""

        self._wireframe_cache_key = None
        self._wireframe_meshes = []

    def _invalidate_surface_geometry(self) -> None:
        """Clear cached revolution surface geometry."""

        self._surface_cache_key = None
        self._surface_mesh = None

    def _invalidate_scan_path_geometry(self) -> None:
        """Clear cached geometry derived from the current scan path."""

        self._scan_path_polyline = None
        self._scan_path_segment_polylines = []
        self._scan_path_points_3d = []

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

    def _draw_profile_polyline(self) -> None:
        """Draw the extracted profile in the XZ plane."""

        profile_points = self._get_profile_points_3d()
        profile_lines = self._get_profile_segment_polylines()
        if not profile_lines or not profile_points:
            return

        for index, profile_line in enumerate(profile_lines):
            self._plotter.add_mesh(
                profile_line,
                color="#1f77b4",
                line_width=2.0,
                label="Profile" if index == 0 else None,
            )
        self._draw_profile_endpoint_markers(profile_points[0], profile_points[-1])

        if self._show_text_labels:
            self._plotter.add_point_labels(
                np.asarray([profile_points[0], profile_points[-1]], dtype=float),
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

        for index, path_line in enumerate(path_lines):
            self._plotter.add_mesh(
                path_line,
                color="#f28e2b",
                line_width=2.0,
                opacity=0.92,
                label="Scan Path" if index == 0 else None,
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

    def _get_profile_points_3d(self) -> list[tuple[float, float, float]]:
        """Return cached 3D profile points in the Y=0 plane."""

        if not self._profile_points_3d and self._profile_points:
            self._profile_points_3d = [(x_value, 0.0, z_value) for x_value, z_value in self._profile_points]
        return self._profile_points_3d

    def _get_profile_polyline(self) -> Optional[pv.PolyData]:
        """Return a cached polyline for the current profile."""

        if self._profile_polyline is None and len(self._profile_points) >= 2:
            self._profile_polyline = self._polyline_from_points(self._get_profile_points_3d())
        return self._profile_polyline

    def _get_profile_segment_polylines(self) -> list[pv.PolyData]:
        """Return cached polylines for each non-horizontal profile segment."""

        if self._profile_segment_polylines or len(self._profile_points) < 2:
            return self._profile_segment_polylines

        segment_polylines: list[pv.PolyData] = []
        for segment in split_profile_segments(self._profile_points):
            segment_points_3d = [(x_value, 0.0, z_value) for x_value, z_value in segment]
            segment_polylines.append(self._polyline_from_points(segment_points_3d))

        self._profile_segment_polylines = segment_polylines
        return self._profile_segment_polylines

    def _get_wireframe_meshes(self) -> list[pv.PolyData]:
        """Return cached sparse revolution wireframe meshes."""

        if len(self._profile_points) < 2:
            return []

        profile_key = tuple(self._profile_points)
        wireframe_resolution = self._get_wireframe_copy_count()
        cache_key = (profile_key, wireframe_resolution)
        if self._wireframe_cache_key == cache_key and self._wireframe_meshes:
            return self._wireframe_meshes

        self._wireframe_cache_key = cache_key
        self._wireframe_meshes = []
        for angle_deg in np.linspace(0.0, 360.0, wireframe_resolution, endpoint=False):
            angle_rad = math.radians(float(angle_deg))
            cos_angle = math.cos(angle_rad)
            sin_angle = math.sin(angle_rad)
            rotated_points = [
                (x_value * cos_angle, x_value * sin_angle, z_value)
                for x_value, z_value in self._profile_points
            ]
            self._wireframe_meshes.append(self._polyline_from_points(rotated_points))
        return self._wireframe_meshes

    def _get_surface_mesh(self) -> Optional[pv.PolyData]:
        """Return a cached revolved surface mesh built only for display purposes."""

        if len(self._profile_points) < 2 or not self._is_surface_mode():
            return None

        effective_resolution = self._get_effective_surface_resolution()
        profile_key = tuple(self._profile_points)
        cache_key = (profile_key, effective_resolution)
        if self._surface_cache_key == cache_key and self._surface_mesh is not None:
            return self._surface_mesh

        radii = np.asarray([point[0] for point in self._profile_points], dtype=float)
        z_values = np.asarray([point[1] for point in self._profile_points], dtype=float)
        angles = np.linspace(0.0, 2.0 * math.pi, effective_resolution + 1)

        x_grid = np.outer(np.cos(angles), radii)
        y_grid = np.outer(np.sin(angles), radii)
        z_grid = np.outer(np.ones_like(angles), z_values)

        surface_grid = pv.StructuredGrid(x_grid, y_grid, z_grid)
        self._surface_mesh = surface_grid.extract_surface(algorithm="dataset_surface").triangulate()
        self._surface_cache_key = cache_key
        return self._surface_mesh

    def _get_scan_path_points_3d(self) -> list[tuple[float, float, float]]:
        """Return cached 3D probe points for the current scan path."""

        if not self._scan_path_points_3d and self._scan_path is not None and self._scan_path.points:
            self._scan_path_points_3d = [
                (point.probe_x, point.probe_y, point.probe_z)
                for point in self._scan_path.points
            ]
        return self._scan_path_points_3d

    def _get_scan_path_polyline(self) -> Optional[pv.PolyData]:
        """Return a cached polyline for the current scan path."""

        if self._scan_path_polyline is None and self._scan_path is not None and len(self._scan_path.points) >= 2:
            self._scan_path_polyline = self._polyline_from_points(self._get_scan_path_points_3d())
        return self._scan_path_polyline

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
        """Return stable scene bounds using profile, path, and virtual revolve extents."""

        x_values: list[float] = []
        y_values: list[float] = []
        z_values: list[float] = []

        if self._profile_points:
            for x_value, z_value in self._profile_points:
                x_values.extend((-abs(x_value), abs(x_value)))
                y_values.extend((-abs(x_value), abs(x_value)))
                z_values.append(z_value)

        if self._scan_path is not None and self._scan_path.points:
            for point in self._scan_path.points:
                x_values.append(point.probe_x)
                y_values.append(point.probe_y)
                z_values.append(point.probe_z)

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
