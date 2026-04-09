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
