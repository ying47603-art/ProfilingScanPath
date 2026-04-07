"""Path planner interface for ProfilingScanPath V1."""

from typing import List

from profiling_scan_path.domain.models import PathPoint, ScanPlanInput, StandardizedStepModel


class LayeredPathPlanner:
    """Placeholder planner for layered scan paths.

    TODO: Implement real layered path planning for pure rotational solids.
    """

    def plan(
        self,
        model: StandardizedStepModel,
        scan_input: ScanPlanInput,
    ) -> List[PathPoint]:
        raise NotImplementedError("TODO: implement layered scan path planning")
