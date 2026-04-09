"""Matplotlib-based 2D preview widget for profile and scan-path data."""

from __future__ import annotations

from typing import Iterable, Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from core.path_planner import split_profile_segments, split_scan_path_segments
from data.models import ScanPath


class ProfilePreviewWidget(QWidget):
    """Render XZ profile lines and scan-path points inside the GUI."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Create the preview canvas and initialize empty-state rendering."""

        super().__init__(parent)
        self._profile_points: list[tuple[float, float]] = []
        self._scan_path: Optional[ScanPath] = None

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
        """Store and display the latest extracted profile points."""

        self._profile_points = list(profile_points)
        self.refresh_view()

    def set_scan_path(self, scan_path: Optional[ScanPath]) -> None:
        """Store and display the latest generated scan path."""

        self._scan_path = scan_path
        self.refresh_view()

    def clear_preview(self) -> None:
        """Clear both the rendered content and the internal preview state."""

        self._profile_points = []
        self._scan_path = None
        self.refresh_view()

    def refresh_view(self) -> None:
        """Redraw the preview with profile data, path data, or the empty state."""

        self._axes.clear()
        self._apply_axes_style()

        if self._profile_points:
            self._draw_profile()

        if self._scan_path is not None and self._scan_path.points:
            self._draw_scan_path()

        if not self._profile_points and (self._scan_path is None or not self._scan_path.points):
            self._draw_empty_hint()
            self._axes.set_xlim(-10.0, 110.0)
            self._axes.set_ylim(-10.0, 110.0)
        else:
            self._autoscale_view()

        self._canvas.draw_idle()

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

    def _draw_profile(self) -> None:
        """Draw the extracted profile polyline and its start/end markers."""

        profile_segments = split_profile_segments(self._profile_points)
        if not profile_segments:
            return

        for index, segment in enumerate(profile_segments):
            segment_x = [point[0] for point in segment]
            segment_z = [point[1] for point in segment]
            self._axes.plot(
                segment_x,
                segment_z,
                color="#1f77b4",
                linewidth=2.0,
                label="Profile" if index == 0 else None,
            )
        self._axes.scatter(
            [profile_segments[0][0][0]],
            [profile_segments[0][0][1]],
            color="#2ca02c",
            s=42,
            marker="o",
            zorder=3,
            label="Start",
        )
        self._axes.scatter(
            [profile_segments[-1][-1][0]],
            [profile_segments[-1][-1][1]],
            color="#d62728",
            s=42,
            marker="s",
            zorder=3,
            label="End",
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

    def _draw_empty_hint(self) -> None:
        """Keep the empty-state view clean while preserving axes and grid."""

    def _autoscale_view(self) -> None:
        """Fit the current data with balanced square bounds for easier reading."""

        x_values: list[float] = []
        z_values: list[float] = []

        if self._profile_points:
            x_values.extend(point[0] for point in self._profile_points)
            z_values.extend(point[1] for point in self._profile_points)

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
