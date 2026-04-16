"""Shared data models for the project skeleton."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class ScanParams:
    """Input parameters for layered scan-path generation."""

    s_start: float
    s_end: float
    layer_step: float
    water_distance: float


@dataclass(frozen=True)
class PathPoint:
    """A single scan-path point generated on the XZ profile."""

    layer_index: int
    arc_length: float
    surface_x: float
    surface_z: float
    probe_x: float
    probe_y: float
    probe_z: float
    tilt_angle_deg: float
    group_index: int = 0
    segment_index: int = 0


@dataclass(frozen=True)
class ScanPath:
    """A collection of ordered scan-path points."""

    points: list[PathPoint] = field(default_factory=list)


@dataclass(frozen=True)
class AppInfo:
    """Basic metadata displayed by the minimal runnable app."""

    name: str
    version: str
    description: str


@dataclass(frozen=True)
class StepAxisPlacement:
    """A parsed axis placement from a STEP file."""

    origin: tuple[float, float, float]
    direction: tuple[float, float, float]
    ref_direction: Optional[tuple[float, float, float]] = None


@dataclass(frozen=True)
class StepModel:
    """A lightweight V1 STEP model representation."""

    file_path: Path
    cartesian_points: list[tuple[float, float, float]]
    axis_placements: list[StepAxisPlacement] = field(default_factory=list)
    raw_text: str = ""
    loader_backend: str = "fallback"
    ocp_shape: Optional[Any] = None


@dataclass(frozen=True)
class NormalizedStepModel:
    """A normalized revolved model ready for profile extraction."""

    source_file: Path
    points_3d: list[tuple[float, float, float]]
    axis_origin: tuple[float, float, float]
    axis_direction: tuple[float, float, float]
    ocp_shape: Optional[Any] = None


@dataclass(frozen=True)
class ProfileSegment:
    """One extracted profile segment plus its geometry and path-side metadata."""

    segment_id: int
    name: str
    points: list[tuple[float, float]]
    point_count: int
    x_min: float
    x_max: float
    z_min: float
    z_max: float
    polyline_length: float
    segment_type: str = "mixed"
    profile_side: str = "outer"
    is_enabled: bool = True
    fit_center_x: float | None = None
    fit_center_z: float | None = None
    fit_radius: float | None = None
    fit_radius_valid: bool = False
    fit_residual: float | None = None
    arc_theta_start: float | None = None
    arc_theta_end: float | None = None
    arc_delta_theta: float | None = None
    arc_direction: int | None = None
    arc_length: float | None = None
    arc_geometry_valid: bool = False
    line_start_x: float | None = None
    line_start_z: float | None = None
    line_end_x: float | None = None
    line_end_z: float | None = None
    line_length: float | None = None
    line_valid: bool = False


@dataclass(frozen=True)
class ExtractedProfileSegments:
    """All valid selectable profile segments extracted from one revolved workpiece."""

    profile_segments: list[ProfileSegment] = field(default_factory=list)


@dataclass(frozen=True)
class ActiveProfileBuildResult:
    """Result of rebuilding working-profile groups from ordered selectable segments."""

    rebuilt_profile_points: list[tuple[float, float]] = field(default_factory=list)
    profile_groups: list[list[tuple[float, float]]] = field(default_factory=list)
    oriented_segments: list[ProfileSegment] = field(default_factory=list)
    oriented_group_segments: list[list[ProfileSegment]] = field(default_factory=list)
    is_continuous: bool = False
    warnings: list[str] = field(default_factory=list)
    transform_applied: bool = False


@dataclass(frozen=True)
class InterferenceSample:
    """One interpolated probe pose sampled during one adjacent-layer transition."""

    layer_start: int
    layer_end: int
    sample_index: int
    sample_count: int
    probe_x: float
    probe_y: float
    probe_z: float
    probe_b_angle: float
    center_x: float
    center_y: float
    center_z: float
    collided: bool
    min_distance: float | None = None


@dataclass(frozen=True)
class InterferenceLayerResult:
    """Detection result for one adjacent layer-index pair."""

    layer_start: int
    layer_end: int
    start_center: tuple[float, float, float]
    end_center: tuple[float, float, float]
    collided: bool
    collision_sample: Optional[InterferenceSample] = None


@dataclass(frozen=True)
class InterferenceCheckResult:
    """Summary of one full adjacent-layer interference checking pass."""

    pair_results: list[InterferenceLayerResult] = field(default_factory=list)
    checked_pairs: int = 0
    collided_pairs: int = 0
