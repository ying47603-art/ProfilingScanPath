"""STEP service interface for ProfilingScanPath V1."""

from pathlib import Path

from profiling_scan_path.domain.models import StandardizedStepModel, StepNormalizationError


class StepModelService:
    """Placeholder service for STEP parsing and normalization.

    TODO: Integrate a real STEP parser and rotational-body normalization flow.
    """

    def normalize(self, step_file: Path) -> StandardizedStepModel:
        raise StepNormalizationError()
