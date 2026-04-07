"""Core data models for ProfilingScanPath V1."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence


class CsvFormat(str, Enum):
    """Supported CSV export formats in V1."""

    STANDARD = "standard"
    COMPACT = "compact"


@dataclass(frozen=True)
class ScanPlanInput:
    """User inputs that define a layered scan task."""

    step_file: Path
    s_start: float
    s_end: float
    layer_step: float
    water_distance: float


@dataclass(frozen=True)
class PathPoint:
    """A single probe path point.

    V1 constraints are enforced here:
    - probe_y must stay at 0
    - tilt happens only in the XZ plane
    """

    layer_index: int
    surface_arc_length: float
    probe_x: float
    probe_y: float
    probe_z: float
    tilt_angle_deg: float
    surface_x: float
    surface_z: float
    water_distance: float

    def __post_init__(self) -> None:
        if self.layer_index < 0:
            raise ValueError("layer_index must be >= 0")
        if self.probe_y != 0.0:
            raise ValueError("probe_y must remain 0.0 in V1")


@dataclass(frozen=True)
class ExportBundle:
    """Paths of generated CSV files."""

    standard_csv: Path
    compact_csv: Path


@dataclass(frozen=True)
class StandardizedStepModel:
    """Placeholder model after STEP normalization.

    TODO: Replace the placeholder fields with normalized geometry data.
    """

    source_file: Path


class StepNormalizationError(RuntimeError):
    """Raised when STEP normalization fails."""

    MESSAGE: str = "STEP模型标准化失败"

    def __init__(self) -> None:
        super().__init__(self.MESSAGE)


PathPoints = Sequence[PathPoint]
