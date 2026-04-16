"""Core path-planning helpers for ProfilingScanPath V1."""

from __future__ import annotations

from bisect import bisect_right
import math
from typing import Sequence

from data.models import PathPoint, ScanParams, ScanPath


ProfilePoint = tuple[float, float]
FLOAT_TOLERANCE = 1e-9
WATER_DISTANCE_WARNING_TOLERANCE = 1e-6
MAX_DELTA_ANGLE_DEG = 8.0
OFFSET_SAFETY_RATIO = 0.95
CURVATURE_EPSILON = 1e-9
LINE_ANALYTIC_MAX_LENGTH_RATIO = 1.003
LINE_ANALYTIC_MAX_TURN_DEG = 6.0


def split_profile_segments(profile_points: Sequence[ProfilePoint]) -> list[list[ProfilePoint]]:
    """Split a profile into usable non-horizontal segments.

    Horizontal spans are treated as discontinuities so side-wall segments can be
    processed independently for path generation and preview.
    """

    if len(profile_points) < 2:
        return []

    segments: list[list[ProfilePoint]] = []
    current_segment: list[ProfilePoint] = [profile_points[0]]

    for point in profile_points[1:]:
        prev_x, prev_z = current_segment[-1]
        curr_x, curr_z = point
        dx = curr_x - prev_x
        dz = curr_z - prev_z

        if math.isclose(dz, 0.0, abs_tol=FLOAT_TOLERANCE) and not math.isclose(dx, 0.0, abs_tol=FLOAT_TOLERANCE):
            if len(current_segment) >= 2:
                segments.append(current_segment)
            current_segment = [point]
            continue

        current_segment.append(point)

    if len(current_segment) >= 2:
        segments.append(current_segment)

    return segments


def compute_effective_arc_length(profile_points: Sequence[ProfilePoint]) -> float:
    """Return the total arc length over non-horizontal usable profile segments."""

    total_length = 0.0
    for segment in split_profile_segments(profile_points):
        total_length += compute_arc_length(segment)[-1]
    return total_length


def split_scan_path_segments(path_points: Sequence[PathPoint]) -> list[list[PathPoint]]:
    """Split generated scan-path points into independent profile-side segments."""

    if not path_points:
        return []

    segments: list[list[PathPoint]] = [[path_points[0]]]
    for point in path_points[1:]:
        previous_point = segments[-1][-1]
        if (
            point.group_index != previous_point.group_index
            or point.segment_index != previous_point.segment_index
        ):
            segments.append([point])
        else:
            segments[-1].append(point)

    return [segment for segment in segments if segment]


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
    *,
    profile_kind: str = "outer",
    reverse_offset_direction: bool = False,
    group_index: int = 0,
    segment_index: int = 0,
    segment_type: str = "mixed",
    fit_center_x: float | None = None,
    fit_center_z: float | None = None,
    fit_radius: float | None = None,
    fit_radius_valid: bool = False,
    arc_theta_start: float | None = None,
    arc_theta_end: float | None = None,
    arc_delta_theta: float | None = None,
    arc_direction: int | None = None,
    arc_length: float | None = None,
    arc_geometry_valid: bool = False,
    line_start_x: float | None = None,
    line_start_z: float | None = None,
    line_end_x: float | None = None,
    line_end_z: float | None = None,
    line_length: float | None = None,
    line_valid: bool = False,
) -> ScanPath:
    """Generate a layered scan path from an extracted XZ profile."""

    if len(profile_points) < 2:
        raise ValueError("profile_points must contain at least two points")

    normalized_profile_kind = "inner" if str(profile_kind).strip().lower() == "inner" else "outer"
    profile_side_sign = -1.0 if normalized_profile_kind == "inner" else 1.0
    reverse_offset_sign = -1.0 if reverse_offset_direction else 1.0
    offset_sign = profile_side_sign * reverse_offset_sign

    line_geometry = _resolve_line_geometry(
        profile_points,
        line_start_x=line_start_x,
        line_start_z=line_start_z,
        line_end_x=line_end_x,
        line_end_z=line_end_z,
        line_length=line_length,
        line_valid=line_valid,
    )
    arc_geometry = _resolve_arc_geometry(
        fit_center_x=fit_center_x,
        fit_center_z=fit_center_z,
        fit_radius=fit_radius,
        fit_radius_valid=fit_radius_valid,
        arc_theta_start=arc_theta_start,
        arc_theta_end=arc_theta_end,
        arc_delta_theta=arc_delta_theta,
        arc_direction=arc_direction,
        arc_length=arc_length,
        arc_geometry_valid=arc_geometry_valid,
    )

    print(f"[PATH_DEBUG] segment={segment_index} segment_type={segment_type}")
    print(
        "[PATH_DEBUG] "
        f"fit_radius_valid={fit_radius_valid} "
        f"fit_radius={(float(fit_radius) if fit_radius is not None and math.isfinite(float(fit_radius)) else float('nan')):.6f}"
    )
    print(
        "[PATH_DEBUG] "
        f"fit_center=("
        f"{(float(fit_center_x) if fit_center_x is not None and math.isfinite(float(fit_center_x)) else float('nan')):.6f}, "
        f"{(float(fit_center_z) if fit_center_z is not None and math.isfinite(float(fit_center_z)) else float('nan')):.6f})"
    )

    fallback_reason = ""
    line_consistency_ratio = math.nan
    line_total_turn_angle_deg = math.nan
    line_geometry_matches = False
    if segment_type == "line" and line_geometry is not None:
        (
            line_geometry_matches,
            line_consistency_ratio,
            line_total_turn_angle_deg,
        ) = _check_line_geometry_consistency(profile_points, line_geometry)
        print(f"[PATH_DEBUG] line_consistency_check segment={segment_index}")
        print(
            "[PATH_DEBUG] "
            f"line_length={line_geometry['length']:.6f} "
            f"polyline_length={compute_arc_length(profile_points)[-1]:.6f} "
            f"ratio={line_consistency_ratio:.6f}"
        )
        print(f"[PATH_DEBUG] total_turn_angle={line_total_turn_angle_deg:.6f}")

    if segment_type == "line" and line_geometry is not None and line_geometry_matches:
        geometry_source = "line_analytic"
    elif segment_type == "line" and line_geometry is not None:
        geometry_source = "fallback_points"
        fallback_reason = "line_geometry_mismatch"
    elif segment_type == "line":
        geometry_source = "fallback_points"
        fallback_reason = "line_geometry_invalid"
    elif segment_type == "arc" and arc_geometry is not None:
        geometry_source = "arc_analytic"
    elif segment_type == "arc":
        geometry_source = "fallback_points"
        if not fit_radius_valid:
            fallback_reason = "fit_radius_invalid"
        elif fit_center_x is None or fit_center_z is None:
            fallback_reason = "missing_fit_center"
        elif fit_radius is None or not math.isfinite(float(fit_radius)):
            fallback_reason = "missing_fit_radius"
        elif not arc_geometry_valid:
            fallback_reason = "arc_geometry_invalid"
        else:
            fallback_reason = "missing_segment_geometry"
    else:
        geometry_source = "fallback_points"
        fallback_reason = "segment_type_not_arc"

    if geometry_source == "line_analytic" and line_geometry is not None:
        total_arc_length = float(line_geometry["length"])
    elif geometry_source == "arc_analytic" and arc_geometry is not None:
        total_arc_length = float(arc_geometry["arc_length"])
    else:
        total_arc_length = compute_arc_length(profile_points)[-1]

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

    sample_positions = _build_sample_positions(params.s_start, params.s_end, params.layer_step)
    sample_records: list[dict[str, float | int | tuple[float, float] | None]] = []
    previous_unit_normal: tuple[float, float] | None = None
    previous_theta_deg: float | None = None

    if fallback_reason:
        print(f"[PATH_DEBUG] segment={segment_index} geometry_source={geometry_source} fallback_reason={fallback_reason}")
    else:
        print(f"[PATH_DEBUG] segment={segment_index} geometry_source={geometry_source}")
    if geometry_source == "line_analytic" and line_geometry is not None:
        print(
            "[PATH_DEBUG] "
            f"line_length={line_geometry['length']:.6f} "
            f"tangent=({line_geometry['tangent'][0]:.6f}, {line_geometry['tangent'][1]:.6f}) "
            f"normal=({line_geometry['normal'][0]:.6f}, {line_geometry['normal'][1]:.6f})"
        )
        print(
            "[PATH_DEBUG] "
            f"line_start=({line_geometry['start_point'][0]:.6f}, {line_geometry['start_point'][1]:.6f}) "
            f"line_end=({line_geometry['end_point'][0]:.6f}, {line_geometry['end_point'][1]:.6f})"
        )
    elif geometry_source == "arc_analytic" and arc_geometry is not None:
        print(
            "[PATH_DEBUG] "
            f"arc center=({arc_geometry['center_x']:.6f}, {arc_geometry['center_z']:.6f}) "
            f"fit_radius={arc_geometry['radius']:.6f}"
        )
        print(
            "[PATH_DEBUG] "
            f"arc_theta_start={arc_geometry['theta_start']:.6f} "
            f"arc_theta_end={arc_geometry['theta_end']:.6f} "
            f"arc_direction={int(arc_geometry['direction_sign'])} "
            f"fit_radius={arc_geometry['radius']:.6f} "
            f"arc_length={arc_geometry['arc_length']:.6f}"
        )
        print(f"[PATH_DEBUG] total_arc_length={arc_geometry['arc_length']:.6f}")

    fallback_surface_points: list[ProfilePoint] = []
    if geometry_source == "fallback_points":
        fallback_arc_lengths = compute_arc_length(profile_points)
        fallback_surface_points = _build_fallback_surface_points(profile_points, fallback_arc_lengths, sample_positions)

    for sample_index, clamped_s in enumerate(sample_positions):
        continuity_dot = None
        if geometry_source == "line_analytic" and line_geometry is not None:
            surface_x, surface_z = _sample_line_surface(line_geometry, clamped_s)
            raw_nx, raw_nz = line_geometry["normal"]
            normal_norm = 1.0
            kappa = 0.0
            local_rho = math.inf
            rho = math.inf
            curvature_source = "analytic_line"
        elif geometry_source == "arc_analytic" and arc_geometry is not None:
            surface_x, surface_z, raw_nx, raw_nz = _sample_arc_surface_and_normal(arc_geometry, clamped_s)
            normal_norm = 1.0
            kappa = arc_geometry["direction_sign"] / arc_geometry["radius"]
            local_rho = _estimate_local_curvature_from_arc_geometry(arc_geometry, clamped_s)
            rho = arc_geometry["radius"]
            curvature_source = "fitted_arc_radius"
        else:
            surface_x, surface_z = interpolate_point(profile_points, fallback_arc_lengths, clamped_s)
            raw_nx, raw_nz = compute_normal(profile_points, fallback_arc_lengths, clamped_s)
            raw_nx, raw_nz, normal_norm = _normalize_normal(raw_nx, raw_nz)
            kappa, local_rho = _estimate_local_curvature(
                fallback_surface_points,
                sample_index,
            )
            rho = local_rho
            curvature_source = "local_three_point"

        nx, nz, normal_norm = _normalize_normal(raw_nx, raw_nz)
        if previous_unit_normal is not None:
            continuity_dot = nx * previous_unit_normal[0] + nz * previous_unit_normal[1]
            if continuity_dot < 0.0:
                nx = -nx
                nz = -nz
                continuity_dot = -continuity_dot
        previous_unit_normal = (nx, nz)

        inward_offset = _is_inward_offset(kappa, offset_sign)
        print(
            "[PATH_DEBUG] "
            f"rho={(rho if math.isfinite(rho) else float('inf')):.6f} "
            f"kappa={kappa:.6f} "
            f"s={float(clamped_s):.6f}"
        )
        print(
            "[PATH_DEBUG] "
            f"curvature_source={curvature_source} "
            f"fit_radius={(float(fit_radius) if fit_radius is not None else float('nan')):.6f} "
            f"segment={segment_index} "
            f"local_three_point_rho={(local_rho if math.isfinite(local_rho) else float('inf')):.6f}"
        )
        print(
            "[PATH_DEBUG] "
            f"inward_offset={inward_offset} "
            f"offset_sign={offset_sign:.1f} "
            f"water={float(params.water_distance):.6f}"
        )
        if inward_offset and math.isfinite(rho) and params.water_distance >= rho * OFFSET_SAFETY_RATIO:
            print(
                "[PATH_WARNING] "
                f"local offset infeasible at group={group_index} s={float(clamped_s):.6f} "
                f"rho={rho:.6f} water={float(params.water_distance):.6f}"
            )
            raise ValueError(
                f"group={group_index} s={float(clamped_s):.6f} "
                f"local offset infeasible rho={rho:.6f} water={float(params.water_distance):.6f}"
            )

        offset_nx = offset_sign * nx
        offset_nz = offset_sign * nz
        raw_theta_deg = math.degrees(math.atan2(offset_nx, offset_nz))
        tilt_angle_deg, theta_clamped = _clamp_theta_delta(raw_theta_deg, previous_theta_deg, MAX_DELTA_ANGLE_DEG)
        print(
            "[PATH_DEBUG] "
            f"nx={nx:.6f} "
            f"nz={nz:.6f} "
            f"normal_norm={normal_norm:.6f} "
            f"dot_prev={continuity_dot if continuity_dot is not None else 'None'}"
        )
        print(
            "[PATH_DEBUG] "
            f"theta_deg={tilt_angle_deg:.6f} "
            f"prev_theta_deg={previous_theta_deg if previous_theta_deg is not None else 'None'} "
            f"theta_clamped={theta_clamped}"
        )
        previous_theta_deg = tilt_angle_deg

        probe_x = surface_x + params.water_distance * offset_nx
        probe_z = surface_z + params.water_distance * offset_nz
        actual_distance = math.hypot(probe_x - surface_x, probe_z - surface_z)
        print(
            "[PATH_DEBUG] "
            f"s={float(clamped_s):.6f} "
            f"dist={actual_distance:.6f} "
            f"water={float(params.water_distance):.6f}"
        )
        print(
            "[PATH_DEBUG] "
            f"surface=({float(surface_x):.6f}, {float(surface_z):.6f}) "
            f"probe=({float(probe_x):.6f}, {float(probe_z):.6f}) "
            f"offset_distance={actual_distance:.6f}"
        )
        if abs(actual_distance - params.water_distance) > max(
            WATER_DISTANCE_WARNING_TOLERANCE,
            abs(params.water_distance) * 1e-6,
        ):
            print(
                "[PATH_WARNING] "
                f"water distance mismatch at s={float(clamped_s):.6f} "
                f"dist={actual_distance:.6f} "
                f"expected={float(params.water_distance):.6f}"
            )

        sample_records.append(
            {
                "surface_x": float(surface_x),
                "surface_z": float(surface_z),
                "probe_x": float(probe_x),
                "probe_z": float(probe_z),
                "tilt_angle_deg": float(tilt_angle_deg),
                "arc_length": float(clamped_s),
            }
        )

    return ScanPath(
        points=[
            PathPoint(
                layer_index=index,
                arc_length=float(record["arc_length"]),
                surface_x=float(record["surface_x"]),
                surface_z=float(record["surface_z"]),
                probe_x=float(record["probe_x"]),
                probe_y=0.0,
                probe_z=float(record["probe_z"]),
                tilt_angle_deg=float(record["tilt_angle_deg"]),
                group_index=0,
                segment_index=segment_index,
            )
            for index, record in enumerate(sample_records)
        ]
    )


def _locate_segment_index(
    segment_offsets: Sequence[float],
    segment_lengths: Sequence[float],
    target_s: float,
) -> int:
    """Locate which usable profile segment contains a target arc length."""

    for index, offset in enumerate(segment_offsets):
        segment_end = offset + segment_lengths[index]
        if target_s <= segment_end + FLOAT_TOLERANCE:
            return index
    return len(segment_offsets) - 1


def _normalize_normal(nx: float, nz: float) -> tuple[float, float, float]:
    """Return a guaranteed unit normal plus the original vector norm."""

    normal_norm = math.hypot(nx, nz)
    if math.isclose(normal_norm, 0.0, abs_tol=FLOAT_TOLERANCE):
        raise ValueError("computed normal has zero length")
    return nx / normal_norm, nz / normal_norm, normal_norm


def _build_sample_positions(s_start: float, s_end: float, layer_step: float) -> list[float]:
    """Return the exact surface sample positions used by one path-generation pass."""

    sample_positions: list[float] = []
    layer_index = 0
    current_s = s_start
    while current_s <= s_end + FLOAT_TOLERANCE:
        sample_positions.append(float(min(current_s, s_end)))
        layer_index += 1
        current_s = s_start + layer_index * layer_step
        if current_s > s_end + FLOAT_TOLERANCE:
            break
    return sample_positions


def _resolve_line_geometry(
    profile_points: Sequence[ProfilePoint],
    *,
    line_start_x: float | None,
    line_start_z: float | None,
    line_end_x: float | None,
    line_end_z: float | None,
    line_length: float | None,
    line_valid: bool,
) -> dict[str, object] | None:
    """Resolve one analytic line model for a line-like segment."""

    if line_valid and None not in (line_start_x, line_start_z, line_end_x, line_end_z, line_length):
        start_point = (float(line_start_x), float(line_start_z))
        end_point = (float(line_end_x), float(line_end_z))
        resolved_length = float(line_length)
    elif len(profile_points) >= 2:
        start_point = profile_points[0]
        end_point = profile_points[-1]
        resolved_length = _point_distance(start_point, end_point)
    else:
        return None

    if resolved_length <= FLOAT_TOLERANCE:
        return None

    tangent = (
        (end_point[0] - start_point[0]) / resolved_length,
        (end_point[1] - start_point[1]) / resolved_length,
    )
    normal = _normalize_normal(tangent[1], -tangent[0])[:2]
    return {
        "start_point": start_point,
        "end_point": end_point,
        "length": resolved_length,
        "tangent": tangent,
        "normal": normal,
    }


def _check_line_geometry_consistency(
    profile_points: Sequence[ProfilePoint],
    line_geometry: dict[str, object],
) -> tuple[bool, float, float]:
    """Return whether a line candidate is straight enough for analytic line dispatch."""

    polyline_length = compute_arc_length(profile_points)[-1]
    line_length = float(line_geometry["length"])
    if line_length <= FLOAT_TOLERANCE:
        return False, math.inf, math.inf

    ratio = polyline_length / line_length
    total_turn_angle_deg = _compute_total_turn_angle_deg(profile_points)
    is_consistent = (
        ratio <= LINE_ANALYTIC_MAX_LENGTH_RATIO
        and abs(total_turn_angle_deg) <= LINE_ANALYTIC_MAX_TURN_DEG
    )
    return is_consistent, ratio, total_turn_angle_deg


def _sample_line_surface(line_geometry: dict[str, object], target_s: float) -> ProfilePoint:
    """Sample one analytic line segment at arc-length position s."""

    start_x, start_z = line_geometry["start_point"]  # type: ignore[misc]
    tangent_x, tangent_z = line_geometry["tangent"]  # type: ignore[misc]
    return start_x + target_s * tangent_x, start_z + target_s * tangent_z


def _resolve_arc_geometry(
    *,
    fit_center_x: float | None,
    fit_center_z: float | None,
    fit_radius: float | None,
    fit_radius_valid: bool,
    arc_theta_start: float | None,
    arc_theta_end: float | None,
    arc_delta_theta: float | None,
    arc_direction: int | None,
    arc_length: float | None,
    arc_geometry_valid: bool,
) -> dict[str, float] | None:
    """Resolve one analytic circular-arc model from extractor-produced arc parameters."""

    if not fit_radius_valid or not arc_geometry_valid:
        return None
    if None in (
        fit_center_x,
        fit_center_z,
        fit_radius,
        arc_theta_start,
        arc_theta_end,
        arc_delta_theta,
        arc_direction,
        arc_length,
    ):
        return None

    radius = float(fit_radius)
    resolved_arc_length = float(arc_length)
    if radius <= FLOAT_TOLERANCE or resolved_arc_length <= FLOAT_TOLERANCE:
        return None
    if int(arc_direction) not in {-1, 1}:
        return None

    return {
        "center_x": float(fit_center_x),
        "center_z": float(fit_center_z),
        "radius": radius,
        "theta_start": float(arc_theta_start),
        "theta_end": float(arc_theta_end),
        "delta_theta": float(arc_delta_theta),
        "direction_sign": float(int(arc_direction)),
        "arc_length": resolved_arc_length,
    }


def _sample_arc_surface_and_normal(
    arc_geometry: dict[str, float],
    target_s: float,
) -> tuple[float, float, float, float]:
    """Sample one analytic circular arc and its radial unit normal at arc-length position s."""

    radius = float(arc_geometry["radius"])
    theta = float(arc_geometry["theta_start"]) + float(arc_geometry["direction_sign"]) * target_s / radius
    center_x = float(arc_geometry["center_x"])
    center_z = float(arc_geometry["center_z"])
    surface_x = center_x + radius * math.cos(theta)
    surface_z = center_z + radius * math.sin(theta)
    nx = (surface_x - center_x) / radius
    nz = (surface_z - center_z) / radius
    return surface_x, surface_z, nx, nz


def _estimate_local_curvature_from_arc_geometry(
    arc_geometry: dict[str, float],
    _target_s: float,
) -> float:
    """Return a comparable local-three-point radius proxy for an analytic arc."""

    return float(arc_geometry["radius"])


def _build_fallback_surface_points(
    profile_points: Sequence[ProfilePoint],
    arc_lengths: Sequence[float],
    sample_positions: Sequence[float],
) -> list[ProfilePoint]:
    """Build fallback sampled surface points once for local curvature estimation."""

    return [interpolate_point(profile_points, arc_lengths, sample_s) for sample_s in sample_positions]


def _estimate_local_curvature(
    sampled_points: Sequence[ProfilePoint],
    index: int,
) -> tuple[float, float]:
    """Estimate signed curvature and radius from the actual sampled surface sequence."""

    if len(sampled_points) < 3:
        return 0.0, math.inf

    if index <= 0:
        point_a, point_b, point_c = sampled_points[0], sampled_points[1], sampled_points[2]
    elif index >= len(sampled_points) - 1:
        point_a, point_b, point_c = sampled_points[-3], sampled_points[-2], sampled_points[-1]
    else:
        point_a, point_b, point_c = sampled_points[index - 1], sampled_points[index], sampled_points[index + 1]

    ab = _point_distance(point_a, point_b)
    bc = _point_distance(point_b, point_c)
    ac = _point_distance(point_a, point_c)
    denominator = ab * bc * ac
    if denominator <= CURVATURE_EPSILON:
        return 0.0, math.inf

    cross_value = (
        (point_b[0] - point_a[0]) * (point_c[1] - point_a[1])
        - (point_b[1] - point_a[1]) * (point_c[0] - point_a[0])
    )
    if math.isclose(cross_value, 0.0, abs_tol=CURVATURE_EPSILON):
        return 0.0, math.inf

    kappa = (2.0 * cross_value) / denominator
    if math.isclose(kappa, 0.0, abs_tol=CURVATURE_EPSILON):
        return 0.0, math.inf
    return kappa, 1.0 / abs(kappa)


def _is_inward_offset(kappa: float, offset_sign: float) -> bool:
    """Return whether the current offset direction points toward the local curvature center."""

    if math.isclose(kappa, 0.0, abs_tol=CURVATURE_EPSILON):
        return False
    return kappa * offset_sign < 0.0


def _clamp_theta_delta(
    theta_deg: float,
    previous_theta_deg: float | None,
    max_delta_angle_deg: float,
) -> tuple[float, bool]:
    """Clamp one pose-angle update without altering the geometric offset direction."""

    if previous_theta_deg is None:
        return theta_deg, False

    delta = _wrap_angle_delta(theta_deg - previous_theta_deg)
    if abs(delta) <= max_delta_angle_deg:
        return theta_deg, False

    return previous_theta_deg + math.copysign(max_delta_angle_deg, delta), True


def _wrap_angle_delta(delta_deg: float) -> float:
    """Wrap one degree delta into the shortest signed interval."""

    wrapped = (delta_deg + 180.0) % 360.0 - 180.0
    if wrapped == -180.0 and delta_deg > 0.0:
        return 180.0
    return wrapped


def _wrap_radians(delta_rad: float) -> float:
    """Wrap one radian delta into the shortest signed interval."""

    wrapped = (delta_rad + math.pi) % (2.0 * math.pi) - math.pi
    if math.isclose(wrapped, -math.pi, abs_tol=FLOAT_TOLERANCE) and delta_rad > 0.0:
        return math.pi
    return wrapped


def _compute_total_turn_angle_deg(profile_points: Sequence[ProfilePoint]) -> float:
    """Return the signed cumulative tangent-turn angle, in degrees, over one profile sequence."""

    if len(profile_points) < 3:
        return 0.0

    edge_angles: list[float] = []
    for left_point, right_point in zip(profile_points, profile_points[1:]):
        dx = right_point[0] - left_point[0]
        dz = right_point[1] - left_point[1]
        if math.hypot(dx, dz) <= FLOAT_TOLERANCE:
            continue
        edge_angles.append(math.atan2(dz, dx))

    if len(edge_angles) < 2:
        return 0.0

    total_turn = 0.0
    for left_angle, right_angle in zip(edge_angles, edge_angles[1:]):
        total_turn += _wrap_radians(right_angle - left_angle)
    return math.degrees(total_turn)


def _point_distance(point_a: ProfilePoint, point_b: ProfilePoint) -> float:
    """Return Euclidean distance between two XZ points."""

    return math.hypot(point_b[0] - point_a[0], point_b[1] - point_a[1])
