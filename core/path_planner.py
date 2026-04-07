"""Core path-planning helpers for ProfilingScanPath V1."""

from __future__ import annotations

from bisect import bisect_right
import math
from typing import Sequence

from data.models import PathPoint, ScanParams, ScanPath


ProfilePoint = tuple[float, float]
FLOAT_TOLERANCE = 1e-9


def compute_arc_length(profile_points: Sequence[ProfilePoint]) -> list[float]:
    """Compute cumulative arc lengths for an ordered XZ profile."""

    if len(profile_points) < 2:
        raise ValueError("profile_points must contain at least two points")

    arc_lengths: list[float] = [0.0]
    for index in range(1, len(profile_points)):
        prev_x, prev_z = profile_points[index - 1]
        curr_x, curr_z = profile_points[index]
        segment_length = math.hypot(curr_x - prev_x, curr_z - prev_z)
        arc_lengths.append(arc_lengths[-1] + segment_length)

    return arc_lengths


def interpolate_point(
    profile_points: Sequence[ProfilePoint],
    arc_lengths: Sequence[float],
    target_s: float,
) -> ProfilePoint:
    """Linearly interpolate a profile point at a target arc length."""

    if len(profile_points) != len(arc_lengths):
        raise ValueError("profile_points and arc_lengths must have the same length")
    if not arc_lengths:
        raise ValueError("arc_lengths must not be empty")
    if not 0.0 <= target_s <= arc_lengths[-1]:
        raise ValueError("target_s is out of range")

    if math.isclose(target_s, arc_lengths[0]):
        return profile_points[0]
    if math.isclose(target_s, arc_lengths[-1]):
        return profile_points[-1]

    right_index = bisect_right(arc_lengths, target_s)
    left_index = right_index - 1

    left_s = arc_lengths[left_index]
    right_s = arc_lengths[right_index]
    left_x, left_z = profile_points[left_index]
    right_x, right_z = profile_points[right_index]

    if math.isclose(left_s, right_s):
        return left_x, left_z

    ratio = (target_s - left_s) / (right_s - left_s)
    x = left_x + ratio * (right_x - left_x)
    z = left_z + ratio * (right_z - left_z)
    return x, z


def compute_normal(
    profile_points: Sequence[ProfilePoint],
    arc_lengths: Sequence[float],
    target_s: float,
) -> ProfilePoint:
    """Compute the unit outward normal at a target arc length.

    Near both profile ends, this function uses one-sided differences.
    For interior locations, it uses a central-difference neighborhood.
    """

    if len(profile_points) != len(arc_lengths):
        raise ValueError("profile_points and arc_lengths must have the same length")
    if len(profile_points) < 2:
        raise ValueError("profile_points must contain at least two points")
    if target_s < -FLOAT_TOLERANCE or target_s > arc_lengths[-1] + FLOAT_TOLERANCE:
        raise ValueError("target_s is out of range")

    clamped_s = min(max(target_s, 0.0), arc_lengths[-1])
    segment_index = min(max(0, bisect_right(arc_lengths, clamped_s) - 1), len(profile_points) - 2)

    if segment_index == 0 or math.isclose(clamped_s, arc_lengths[0], abs_tol=FLOAT_TOLERANCE):
        left_index = 0
        right_index = 1
    elif segment_index >= len(profile_points) - 2 or math.isclose(
        clamped_s,
        arc_lengths[-1],
        abs_tol=FLOAT_TOLERANCE,
    ):
        left_index = len(profile_points) - 2
        right_index = len(profile_points) - 1
    else:
        left_index = segment_index - 1
        right_index = segment_index + 1

    left_x, left_z = profile_points[left_index]
    right_x, right_z = profile_points[right_index]
    dx = right_x - left_x
    dz = right_z - left_z

    # Canonicalize the local tangent so normal selection does not depend on
    # how the source profile happened to be ordered around the same geometry.
    if dz < -FLOAT_TOLERANCE or (
        math.isclose(dz, 0.0, abs_tol=FLOAT_TOLERANCE) and dx < -FLOAT_TOLERANCE
    ):
        dx = -dx
        dz = -dz

    tangent_norm = math.hypot(dx, dz)
    if math.isclose(tangent_norm, 0.0, abs_tol=FLOAT_TOLERANCE):
        raise ValueError("profile_points contain a zero-length segment")

    # For an XZ profile x = r(z), the outward normal is proportional to
    # (1, -dr/dz), which corresponds to (dz, -dx) for the local tangent.
    nx = dz / tangent_norm
    nz = -dx / tangent_norm

    # V1 assumes the workpiece is a rotational body with x >= 0 on the outer contour.
    # If the normal points inward, flip it so that the x component becomes non-negative.
    if nx < 0.0:
        nx = -nx
        nz = -nz

    return nx, nz


def generate_scan_path(
    profile_points: Sequence[ProfilePoint],
    params: ScanParams,
) -> ScanPath:
    """Generate a layered scan path from an extracted XZ profile."""

    arc_lengths = compute_arc_length(profile_points)
    total_arc_length = arc_lengths[-1]

    if params.layer_step <= FLOAT_TOLERANCE:
        raise ValueError("layer_step must be > 0")
    if params.water_distance <= FLOAT_TOLERANCE:
        raise ValueError("water_distance must be > 0")
    if params.s_start < -FLOAT_TOLERANCE:
        raise ValueError("s_start and s_end must satisfy 0 <= s_start < s_end <= total_arc_length")
    if params.s_end > total_arc_length + FLOAT_TOLERANCE:
        raise ValueError("s_start and s_end must satisfy 0 <= s_start < s_end <= total_arc_length")
    if params.s_end - params.s_start <= FLOAT_TOLERANCE:
        raise ValueError("s_start and s_end must satisfy 0 <= s_start < s_end <= total_arc_length")

    points: list[PathPoint] = []
    layer_index = 0
    current_s = params.s_start

    while current_s <= params.s_end + FLOAT_TOLERANCE:
        clamped_s = min(current_s, params.s_end)
        surface_x, surface_z = interpolate_point(profile_points, arc_lengths, clamped_s)
        nx, nz = compute_normal(profile_points, arc_lengths, clamped_s)

        probe_x = surface_x + params.water_distance * nx
        probe_z = surface_z + params.water_distance * nz
        tilt_angle_deg = math.degrees(math.atan2(nx, nz))

        points.append(
            PathPoint(
                layer_index=layer_index,
                arc_length=float(clamped_s),
                surface_x=float(surface_x),
                surface_z=float(surface_z),
                probe_x=float(probe_x),
                probe_y=0.0,
                probe_z=float(probe_z),
                tilt_angle_deg=float(tilt_angle_deg),
            )
        )

        layer_index += 1
        current_s = params.s_start + layer_index * params.layer_step

        if current_s > params.s_end + FLOAT_TOLERANCE:
            break

    return ScanPath(points=points)
