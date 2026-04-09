"""Controller layer for the minimal PyQt6 GUI prototype."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.model_normalizer import normalize_revolved_model
from core.path_planner import compute_effective_arc_length, generate_scan_path
from core.profile_extractor import extract_profile_points
from core.step_loader import load_step_model
from data.models import NormalizedStepModel, PathPoint, ScanParams, ScanPath, StepModel
from exporter.csv_exporter import CsvExporter


class GuiController:
    """Coordinate GUI actions with the existing core pipeline."""

    def __init__(self) -> None:
        """Initialize controller state."""

        self._exporter = CsvExporter()
        self._step_model: Optional[StepModel] = None
        self._normalized_model: Optional[NormalizedStepModel] = None
        self._profile_points: list[tuple[float, float]] = []
        self._scan_path: Optional[ScanPath] = None

    @property
    def step_model(self) -> Optional[StepModel]:
        """Return the currently loaded STEP model, if any."""

        return self._step_model

    @property
    def normalized_model(self) -> Optional[NormalizedStepModel]:
        """Return the currently normalized model, if any."""

        return self._normalized_model

    @property
    def profile_points(self) -> list[tuple[float, float]]:
        """Return the current extracted profile points."""

        return list(self._profile_points)

    @property
    def scan_path(self) -> Optional[ScanPath]:
        """Return the current generated scan path, if any."""

        return self._scan_path

    def load_step(self, file_path: Path) -> dict[str, object]:
        """Load a STEP file and reset all downstream state."""

        self._step_model = load_step_model(file_path)
        self._normalized_model = None
        self._profile_points = []
        self._scan_path = None

        return {
            "file_path": self._step_model.file_path,
            "loader_backend": self._step_model.loader_backend,
            "has_ocp_shape": self._step_model.ocp_shape is not None,
            "cartesian_point_count": len(self._step_model.cartesian_points),
            "axis_placement_count": len(self._step_model.axis_placements),
        }

    def extract_profile(self, samples: int) -> dict[str, object]:
        """Normalize the loaded STEP model and extract profile points."""

        if self._step_model is None:
            raise ValueError("No STEP model has been loaded")

        self._normalized_model = normalize_revolved_model(self._step_model)
        self._profile_points = extract_profile_points(self._normalized_model, num_samples=samples)
        self._scan_path = None

        result = self._profile_stats()
        result.update(
            {
                "axis_origin": self._normalized_model.axis_origin,
                "axis_direction": self._normalized_model.axis_direction,
                "has_ocp_shape": self._normalized_model.ocp_shape is not None,
            }
        )
        return result

    def generate_path(
        self,
        s_start: float,
        s_end: Optional[float],
        layer_step: float,
        water_distance: float,
    ) -> dict[str, object]:
        """Generate a scan path from the current profile points."""

        if not self._profile_points:
            raise ValueError("No profile points have been extracted")

        total_arc_length = compute_effective_arc_length(self._profile_points)
        resolved_s_end = total_arc_length if s_end is None else s_end

        params = ScanParams(
            s_start=s_start,
            s_end=resolved_s_end,
            layer_step=layer_step,
            water_distance=water_distance,
        )
        self._scan_path = generate_scan_path(self._profile_points, params)

        angle_values = [point.tilt_angle_deg for point in self._scan_path.points]
        return {
            "scan_point_count": len(self._scan_path.points),
            "min_angle": min(angle_values),
            "max_angle": max(angle_values),
            "resolved_s_end": resolved_s_end,
        }

    def export_csv(self, output_dir: Path) -> dict[str, Path]:
        """Export the current profile and scan path data to CSV files."""

        if not self._profile_points:
            raise ValueError("No profile points are available for export")
        if self._scan_path is None or not self._scan_path.points:
            raise ValueError("No scan path is available for export")

        output_dir.mkdir(parents=True, exist_ok=True)

        profile_file = self._exporter.export_rows(
            rows=[
                {"x": float(point_x), "z": float(point_z)}
                for point_x, point_z in self._profile_points
            ],
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
        """Mirror the current profile on the Z axis and clear the stale scan path."""

        if not self._profile_points:
            raise ValueError("No profile points have been extracted")

        z_values = [point[1] for point in self._profile_points]
        min_z = min(z_values)
        max_z = max(z_values)
        mirrored_profile = [
            (point_x, min_z + max_z - point_z)
            for point_x, point_z in reversed(self._profile_points)
        ]

        self._profile_points = mirrored_profile
        self._scan_path = None
        return self._profile_stats()

    def flip_profile_direction(self) -> dict[str, object]:
        """Reverse the current profile point order and clear the stale scan path."""

        if not self._profile_points:
            raise ValueError("No profile points have been extracted")

        self._profile_points = list(reversed(self._profile_points))
        self._scan_path = None
        return self._profile_stats()

    def clear_scan_path(self) -> None:
        """Clear the currently generated scan path."""

        self._scan_path = None

    def _build_standard_rows(self, points: list[PathPoint]) -> list[dict[str, float]]:
        """Convert path points into the standard CSV row format."""

        return [
            {
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
        """Convert path points into the compact CSV row format."""

        return [
            {
                "Segment": float(point.segment_index),
                "X": float(point.probe_x),
                "Y": float(point.probe_y),
                "Z": float(point.probe_z),
                "Angle": float(point.tilt_angle_deg),
            }
            for point in points
        ]

    def _profile_stats(self) -> dict[str, object]:
        """Return summary statistics for the current profile."""

        x_values = [point[0] for point in self._profile_points]
        z_values = [point[1] for point in self._profile_points]
        return {
            "profile_point_count": len(self._profile_points),
            "min_x": min(x_values),
            "max_x": max(x_values),
            "min_z": min(z_values),
            "max_z": max(z_values),
        }
