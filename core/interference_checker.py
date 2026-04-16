"""Adjacent-layer probe-transition interference checking helpers."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np
import pyvista as pv

from data.models import InterferenceCheckResult, InterferenceLayerResult, InterferenceSample, PathPoint, ScanPath


DEFAULT_INTERPOLATION_SAMPLES = 20
DEFAULT_DISTANCE_TOLERANCE = 0.5


@dataclass(frozen=True)
class InterpolatedProbePose:
    """One interpolated probe pose used for transition interference sampling."""

    probe_x: float
    probe_y: float
    probe_z: float
    probe_b_angle: float
    center_x: float
    center_y: float
    center_z: float
    direction: tuple[float, float, float]


def check_adjacent_layer_interference(
    scan_path: ScanPath,
    *,
    surface_meshes: Sequence[pv.PolyData],
    probe_diameter: float,
    probe_length: float,
    interpolation_samples: int = DEFAULT_INTERPOLATION_SAMPLES,
    distance_tolerance: float = DEFAULT_DISTANCE_TOLERANCE,
) -> InterferenceCheckResult:
    """Check every adjacent layer-index pair using interpolated probe poses."""

    if interpolation_samples < 2:
        raise ValueError("interpolation_samples must be >= 2")
    if probe_diameter <= 0.0:
        raise ValueError("probe_diameter must be > 0")
    if probe_length <= 0.0:
        raise ValueError("probe_length must be > 0")
    if not scan_path.points:
        raise ValueError("No scan path is available for interference checking")
    if not surface_meshes:
        raise ValueError("No active surface mesh is available for interference checking")

    ordered_points = sorted(scan_path.points, key=lambda point: point.layer_index)
    pair_results: list[InterferenceLayerResult] = []

    for current_point, next_point in zip(ordered_points, ordered_points[1:]):
        pair_results.append(
            _check_one_adjacent_pair(
                current_point,
                next_point,
                surface_meshes=surface_meshes,
                probe_diameter=probe_diameter,
                probe_length=probe_length,
                interpolation_samples=interpolation_samples,
                distance_tolerance=distance_tolerance,
            )
        )

    collided_pairs = sum(1 for result in pair_results if result.collided)
    return InterferenceCheckResult(
        pair_results=pair_results,
        checked_pairs=len(pair_results),
        collided_pairs=collided_pairs,
    )


def _check_one_adjacent_pair(
    start_point: PathPoint,
    end_point: PathPoint,
    *,
    surface_meshes: Sequence[pv.PolyData],
    probe_diameter: float,
    probe_length: float,
    interpolation_samples: int,
    distance_tolerance: float,
) -> InterferenceLayerResult:
    """Check one adjacent-layer transition by sampling interpolated probe poses."""

    start_pose = _build_pose_from_path_point(start_point, probe_length=probe_length)
    end_pose = _build_pose_from_path_point(end_point, probe_length=probe_length)
    collision_sample: InterferenceSample | None = None

    for sample_index in range(interpolation_samples):
        ratio = sample_index / (interpolation_samples - 1)
        pose = _interpolate_probe_pose(start_point, end_point, ratio=ratio, probe_length=probe_length)
        probe_mesh = _build_probe_cylinder_mesh(
            pose,
            probe_diameter=probe_diameter,
            probe_length=probe_length,
        )
        collided, min_distance = _detect_probe_surface_interference(
            probe_mesh,
            surface_meshes=surface_meshes,
            distance_tolerance=distance_tolerance,
        )
        if collided:
            collision_sample = InterferenceSample(
                layer_start=start_point.layer_index,
                layer_end=end_point.layer_index,
                sample_index=sample_index + 1,
                sample_count=interpolation_samples,
                probe_x=pose.probe_x,
                probe_y=pose.probe_y,
                probe_z=pose.probe_z,
                probe_b_angle=pose.probe_b_angle,
                center_x=pose.center_x,
                center_y=pose.center_y,
                center_z=pose.center_z,
                collided=True,
                min_distance=min_distance,
            )
            break

    return InterferenceLayerResult(
        layer_start=start_point.layer_index,
        layer_end=end_point.layer_index,
        start_center=(start_pose.center_x, start_pose.center_y, start_pose.center_z),
        end_center=(end_pose.center_x, end_pose.center_y, end_pose.center_z),
        collided=collision_sample is not None,
        collision_sample=collision_sample,
    )


def _build_pose_from_path_point(path_point: PathPoint, *, probe_length: float) -> InterpolatedProbePose:
    """Build one probe pose from one generated scan-path point."""

    return _build_pose(
        probe_x=float(path_point.probe_x),
        probe_y=float(path_point.probe_y),
        probe_z=float(path_point.probe_z),
        probe_b_angle=float(path_point.tilt_angle_deg),
        probe_length=probe_length,
    )


def _interpolate_probe_pose(
    start_point: PathPoint,
    end_point: PathPoint,
    *,
    ratio: float,
    probe_length: float,
) -> InterpolatedProbePose:
    """Linearly interpolate one probe pose between two adjacent layers."""

    return _build_pose(
        probe_x=_lerp(float(start_point.probe_x), float(end_point.probe_x), ratio),
        probe_y=_lerp(float(start_point.probe_y), float(end_point.probe_y), ratio),
        probe_z=_lerp(float(start_point.probe_z), float(end_point.probe_z), ratio),
        probe_b_angle=_lerp(float(start_point.tilt_angle_deg), float(end_point.tilt_angle_deg), ratio),
        probe_length=probe_length,
    )


def _build_pose(
    *,
    probe_x: float,
    probe_y: float,
    probe_z: float,
    probe_b_angle: float,
    probe_length: float,
) -> InterpolatedProbePose:
    """Build one probe pose and its cylinder center from X/Y/Z/B values."""

    direction = _probe_direction_from_b_angle(probe_b_angle)
    center_x = probe_x - direction[0] * (probe_length * 0.5)
    center_y = probe_y - direction[1] * (probe_length * 0.5)
    center_z = probe_z - direction[2] * (probe_length * 0.5)
    return InterpolatedProbePose(
        probe_x=probe_x,
        probe_y=probe_y,
        probe_z=probe_z,
        probe_b_angle=probe_b_angle,
        center_x=center_x,
        center_y=center_y,
        center_z=center_z,
        direction=direction,
    )


def _probe_direction_from_b_angle(probe_b_angle: float) -> tuple[float, float, float]:
    """Convert the current B-angle convention into the probe axis direction."""

    angle_rad = math.radians(probe_b_angle)
    normal_x = math.sin(angle_rad)
    normal_z = math.cos(angle_rad)
    return (-normal_x, 0.0, -normal_z)


def _build_probe_cylinder_mesh(
    pose: InterpolatedProbePose,
    *,
    probe_diameter: float,
    probe_length: float,
) -> pv.PolyData:
    """Build one simplified probe cylinder for one interpolated pose."""

    return pv.Cylinder(
        center=(pose.center_x, pose.center_y, pose.center_z),
        direction=pose.direction,
        radius=probe_diameter * 0.5,
        height=probe_length,
        resolution=24,
    ).triangulate()


def _detect_probe_surface_interference(
    probe_mesh: pv.PolyData,
    *,
    surface_meshes: Sequence[pv.PolyData],
    distance_tolerance: float,
) -> tuple[bool, float | None]:
    """Detect probe-vs-surface interference using collision, with distance fallback."""

    minimum_distance = math.inf
    for surface_mesh in surface_meshes:
        collided, min_distance = _detect_against_one_surface(
            probe_mesh,
            surface_mesh=surface_mesh,
            distance_tolerance=distance_tolerance,
        )
        if min_distance is not None:
            minimum_distance = min(minimum_distance, min_distance)
        if collided:
            return True, 0.0 if not math.isfinite(minimum_distance) else minimum_distance

    if math.isfinite(minimum_distance):
        return minimum_distance <= distance_tolerance, minimum_distance
    return False, None


def _detect_against_one_surface(
    probe_mesh: pv.PolyData,
    *,
    surface_mesh: pv.PolyData,
    distance_tolerance: float,
) -> tuple[bool, float | None]:
    """Detect interference against one active surface mesh."""

    try:
        _, contact_count = probe_mesh.collision(surface_mesh)
        if int(contact_count) > 0:
            return True, 0.0
    except Exception:
        pass

    try:
        probe_with_distance = probe_mesh.compute_implicit_distance(surface_mesh, inplace=False)
        distances = np.abs(np.asarray(probe_with_distance["implicit_distance"], dtype=float))
        if distances.size == 0:
            return False, None
        minimum_distance = float(np.min(distances))
        return minimum_distance <= distance_tolerance, minimum_distance
    except Exception:
        return False, None


def _lerp(start_value: float, end_value: float, ratio: float) -> float:
    """Linearly interpolate one scalar value."""

    return start_value + (end_value - start_value) * ratio
