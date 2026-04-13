"""Matplotlib-based 2D preview widget for profile and scan-path data."""

from __future__ import annotations

from typing import Iterable, Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import Polygon
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from core.path_planner import split_profile_segments, split_scan_path_segments
from data.models import ScanPath


class ProfilePreviewWidget(QWidget):
    """Render active/inactive XZ profiles and scan-path data inside the GUI."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Create the preview canvas and initialize empty-state rendering."""

        super().__init__(parent)
        self._profile_points: list[tuple[float, float]] = []
        self._reference_profile_points: list[tuple[float, float]] = []
        self._scan_path: Optional[ScanPath] = None
        self._show_probe_body = True
        self._show_probe_line = True
        self._probe_diameter = 10.0
        self._probe_length = 20.0
        self._current_probe_index: Optional[int] = None

        self._figure = Figure(figsize=(5, 4), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._axes = self._figure.add_subplot(111)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)

        self.refresh_view()

    def set_profile_points(self, profile_points: Iterable[tuple[float, float]]) -> None:
        """Store and display the currently active profile points."""

        self._profile_points = list(profile_points)
        self.refresh_view()

    def set_reference_profile_points(self, profile_points: Iterable[tuple[float, float]]) -> None:
        """Store and display the inactive profile points as a weak reference."""

        self._reference_profile_points = list(profile_points)
        self.refresh_view()

    def set_scan_path(self, scan_path: Optional[ScanPath]) -> None:
        """Store and display the latest generated scan path."""

        self._scan_path = scan_path
        self.refresh_view()

    def clear_preview(self) -> None:
        """Clear rendered profiles, path content, and current probe selection."""

        self._profile_points = []
        self._reference_profile_points = []
        self._scan_path = None
        self._current_probe_index = None
        self.refresh_view()

    def set_probe_pose_options(
        self,
        *,
        show_probe_body: Optional[bool] = None,
        show_probe_line: Optional[bool] = None,
        probe_diameter: Optional[float] = None,
        probe_length: Optional[float] = None,
    ) -> None:
        """Update the current 2D probe overlay options and refresh immediately."""

        if show_probe_body is not None:
            self._show_probe_body = bool(show_probe_body)
        if show_probe_line is not None:
            self._show_probe_line = bool(show_probe_line)
        if probe_diameter is not None:
            self._probe_diameter = max(0.1, float(probe_diameter))
        if probe_length is not None:
            self._probe_length = max(0.1, float(probe_length))
        self.refresh_view()

    def set_current_probe_index(self, index: Optional[int]) -> None:
        """Select which scan-path point should drive the 2D probe overlay."""

        self._current_probe_index = index
        self.refresh_view()

    def clear_probe_pose(self) -> None:
        """Clear the 2D single-probe overlay selection and redraw."""

        self._current_probe_index = None
        self.refresh_view()

    def refresh_view(self) -> None:
        """Redraw profiles, path data, and the current probe overlay."""

        self._axes.clear()
        self._apply_axes_style()

        if self._reference_profile_points:
            self._draw_profile(
                self._reference_profile_points,
                color="#9fbad0",
                alpha=0.32,
                linewidth=1.4,
                include_legend=False,
                emphasize_endpoints=False,
            )

        if self._profile_points:
            self._draw_profile(
                self._profile_points,
                color="#1f77b4",
                alpha=1.0,
                linewidth=2.0,
                include_legend=True,
                emphasize_endpoints=True,
            )

        if self._scan_path is not None and self._scan_path.points:
            self._draw_scan_path()
            self._draw_current_probe_pose()

        if not self._profile_points and not self._reference_profile_points and (
            self._scan_path is None or not self._scan_path.points
        ):
            self._axes.set_xlim(-10.0, 110.0)
            self._axes.set_ylim(-10.0, 110.0)
        else:
            self._autoscale_view()

        self._canvas.draw_idle()

    def _draw_current_probe_pose(self) -> None:
        """Draw the selected single probe and beam axis in the XZ preview."""

        pose = self._build_current_probe_pose()
        if pose is None:
            return

        probe_tip, surface_point, direction = pose
        probe_back = (
            probe_tip[0] - direction[0] * self._probe_length,
            probe_tip[1] - direction[1] * self._probe_length,
        )

        if self._show_probe_body:
            self._draw_probe_body(probe_tip, probe_back, direction)

        if self._show_probe_line:
            self._axes.plot(
                [probe_tip[0], surface_point[0]],
                [probe_tip[1], surface_point[1]],
                color="#d62728",
                linewidth=1.4,
                linestyle=(0, (4, 3)),
                alpha=0.95,
                zorder=2,
            )

    def _draw_probe_body(
        self,
        probe_tip: tuple[float, float],
        probe_back: tuple[float, float],
        direction: tuple[float, float],
    ) -> None:
        """Draw the probe body as a width-aware 2D projection instead of a thick line."""

        half_width = self._probe_diameter * 0.5
        normal = (-direction[1], direction[0])
        corners = [
            (probe_tip[0] + normal[0] * half_width, probe_tip[1] + normal[1] * half_width),
            (probe_tip[0] - normal[0] * half_width, probe_tip[1] - normal[1] * half_width),
            (probe_back[0] - normal[0] * half_width, probe_back[1] - normal[1] * half_width),
            (probe_back[0] + normal[0] * half_width, probe_back[1] + normal[1] * half_width),
        ]
        probe_patch = Polygon(
            corners,
            closed=True,
            facecolor="#9aa7b4",
            edgecolor="none",
            alpha=0.55,
            zorder=2,
        )
        self._axes.add_patch(probe_patch)

    def _apply_axes_style(self) -> None:
        """Apply the common axis, grid, and border styling."""

        self._axes.set_facecolor("#fbfbfb")
        self._axes.grid(True, color="#d8d8d8", linewidth=0.6, linestyle="--", alpha=0.8)
        self._axes.axhline(0.0, color="#808080", linewidth=0.9)
        self._axes.axvline(0.0, color="#808080", linewidth=0.9)
        self._axes.set_xlabel("X")
        self._axes.set_ylabel("Z")
        self._axes.set_aspect("equal", adjustable="box")
        self._axes.ticklabel_format(axis="both", style="plain", useOffset=False)

        for spine in self._axes.spines.values():
            spine.set_color("#b8b8b8")
            spine.set_linewidth(0.8)

    def _draw_profile(
        self,
        profile_points: list[tuple[float, float]],
        *,
        color: str,
        alpha: float,
        linewidth: float,
        include_legend: bool,
        emphasize_endpoints: bool,
    ) -> None:
        """Draw one profile with configurable styling."""

        profile_segments = split_profile_segments(profile_points)
        if not profile_segments:
            return

        for index, segment in enumerate(profile_segments):
            segment_x = [point[0] for point in segment]
            segment_z = [point[1] for point in segment]
            self._axes.plot(
                segment_x,
                segment_z,
                color=color,
                linewidth=linewidth,
                alpha=alpha,
                label="Profile" if include_legend and index == 0 else None,
            )

        if emphasize_endpoints:
            self._draw_endpoint_markers(
                start_point=profile_segments[0][0],
                end_point=profile_segments[-1][-1],
                include_legend=include_legend,
            )

    def _draw_scan_path(self) -> None:
        """Draw probe-path points from the generated scan path."""

        if self._scan_path is None:
            return

        scan_segments = split_scan_path_segments(self._scan_path.points)
        if not scan_segments:
            return

        for index, segment in enumerate(scan_segments):
            segment_x = [point.probe_x for point in segment]
            segment_z = [point.probe_z for point in segment]
            self._axes.plot(
                segment_x,
                segment_z,
                color="#ff7f0e",
                linewidth=1.2,
                alpha=0.95,
                label="Scan Path" if index == 0 else None,
            )

        self._draw_endpoint_markers(
            start_point=(scan_segments[0][0].probe_x, scan_segments[0][0].probe_z),
            end_point=(scan_segments[-1][-1].probe_x, scan_segments[-1][-1].probe_z),
            include_legend=False,
        )

    def _draw_endpoint_markers(
        self,
        *,
        start_point: tuple[float, float],
        end_point: tuple[float, float],
        include_legend: bool,
    ) -> None:
        """Draw unified start/end markers for profile and path data."""

        self._axes.scatter(
            [start_point[0]],
            [start_point[1]],
            color="#2ca02c",
            s=42,
            marker="o",
            zorder=3,
            label="Start" if include_legend else None,
        )
        self._axes.scatter(
            [end_point[0]],
            [end_point[1]],
            color="#d62728",
            s=42,
            marker="s",
            zorder=3,
            label="End" if include_legend else None,
        )

    def _build_current_probe_pose(
        self,
    ) -> Optional[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]]:
        """Build the current 2D probe tip, surface point, and axis direction."""

        if self._scan_path is None or not self._scan_path.points:
            return None
        if self._current_probe_index is None:
            return None
        if not 0 <= self._current_probe_index < len(self._scan_path.points):
            return None

        point = self._scan_path.points[self._current_probe_index]
        probe_tip = (float(point.probe_x), float(point.probe_z))
        surface_point = (float(point.surface_x), float(point.surface_z))
        dx = surface_point[0] - probe_tip[0]
        dz = surface_point[1] - probe_tip[1]
        norm = (dx * dx + dz * dz) ** 0.5
        if norm <= 1e-9:
            return None
        return probe_tip, surface_point, (dx / norm, dz / norm)

    def _autoscale_view(self) -> None:
        """Fit the current data with balanced square bounds for easier reading."""

        x_values: list[float] = []
        z_values: list[float] = []

        for profile_points in (self._profile_points, self._reference_profile_points):
            if profile_points:
                x_values.extend(point[0] for point in profile_points)
                z_values.extend(point[1] for point in profile_points)

        if self._scan_path is not None and self._scan_path.points:
            for segment in split_scan_path_segments(self._scan_path.points):
                x_values.extend(point.probe_x for point in segment)
                z_values.extend(point.probe_z for point in segment)

        if not x_values or not z_values:
            self._axes.set_xlim(-10.0, 110.0)
            self._axes.set_ylim(-10.0, 110.0)
            return

        min_x = min(x_values)
        max_x = max(x_values)
        min_z = min(z_values)
        max_z = max(z_values)

        x_span = max_x - min_x
        z_span = max_z - min_z
        view_span = max(x_span, z_span, 20.0)
        half_span = view_span * 0.62
        center_x = (min_x + max_x) / 2.0
        center_z = (min_z + max_z) / 2.0

        self._axes.set_xlim(center_x - half_span, center_x + half_span)
        self._axes.set_ylim(center_z - half_span, center_z + half_span)
        self._axes.legend(loc="best", fontsize=8)
