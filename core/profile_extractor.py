"""Profile extraction for normalized simple revolved STEP models."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Union

from core.model_normalizer import normalize_revolved_model
from core.path_planner import compute_arc_length, interpolate_point, split_profile_segments
from core.step_loader import load_step_model
from data.models import ExtractedProfileSegments, NormalizedStepModel, ProfileSegment


EXTRACTION_ERROR = "STEP model normalization failed"
Y_SECTION_TOLERANCE = 1e-3
DEDUPLICATION_TOLERANCE = 1e-6
AXIS_CHAIN_TOLERANCE = 1.0
CHAIN_MERGE_DISTANCE = 2.5
PROFILE_COMPLETENESS_RATIO = 0.6
PROFILE_Z_OVERLAP_RATIO = 0.75
INNER_PROFILE_MEAN_X_GAP_RATIO = 0.08
MIN_PROFILE_CHAIN_POINTS = 6
MIN_POINTS_PER_SUBSEGMENT = 4
MIN_SUBSEGMENT_LENGTH_RATIO = 0.05
MIN_SUBSEGMENT_LENGTH_ABS = 1.0
LINE_TURN_ANGLE_TOL_DEG = 4.0
ARC_TURN_ANGLE_MIN_DEG = 0.8
ARC_CUMULATIVE_TURN_MIN_DEG = 4.5
ARC_TURN_STABILITY_RATIO = 0.8
ARC_FIT_MIN_POINT_COUNT = 5
ARC_FIT_MAX_RELATIVE_RESIDUAL = 0.08
LINE_RECHECK_MIN_POINT_COUNT = 6
LINE_TO_ARC_MIN_RATIO = 1.003
LINE_TO_ARC_MIN_TURN_DEG = 6.0
LINE_TO_ARC_MAX_RELATIVE_RESIDUAL = 0.03
CORNER_SPLIT_MIN_ANGLE_DEG = 20.0
CORNER_SPLIT_NEIGHBOR_STEP = 2
CORNER_SPLIT_MIN_SUBSEGMENT_POINTS = 3
CORNER_SPLIT_CLUSTER_GAP = 1


@dataclass(frozen=True)
class ProfileChainStats:
    """Summary statistics for one merged profile-chain candidate."""

    x_min: float
    x_max: float
    x_span: float
    z_min: float
    z_max: float
    z_span: float
    mean_x: float
    point_count: int
    polyline_length: float


@dataclass
class ChainMergeEntry:
    """Mutable merge-time wrapper that tracks source chains kept in one candidate."""

    points: list[tuple[float, float]]
    source_indices: list[int]


def _profile_debug(message: str) -> None:
    """Emit one profile-extraction debug line without affecting normal control flow."""

    print(f"[PROFILE_DEBUG] {message}")


def _format_chain_stats(index: int, stats: ProfileChainStats) -> str:
    """Return a compact diagnostic summary for one merged profile chain."""

    return (
        f"chain[{index}] "
        f"point_count={stats.point_count} "
        f"x_min={stats.x_min:.6f} "
        f"x_max={stats.x_max:.6f} "
        f"x_span={stats.x_span:.6f} "
        f"z_min={stats.z_min:.6f} "
        f"z_max={stats.z_max:.6f} "
        f"z_span={stats.z_span:.6f} "
        f"mean_x={stats.mean_x:.6f} "
        f"polyline_length={stats.polyline_length:.6f}"
    )


def extract_profile_points(
    model: NormalizedStepModel,
    num_samples: int = 200,
) -> list[tuple[float, float]]:
    """Extract one concatenated default working profile for legacy callers."""

    extracted_segments = extract_profile_segments(model, num_samples=num_samples)
    concatenated_points: list[tuple[float, float]] = []
    for profile_segment in extracted_segments.profile_segments:
        if not concatenated_points:
            concatenated_points.extend(profile_segment.points)
            continue

        candidate_points = list(profile_segment.points)
        distance_to_start = _point_distance(concatenated_points[-1], candidate_points[0])
        distance_to_end = _point_distance(concatenated_points[-1], candidate_points[-1])
        if distance_to_end < distance_to_start:
            candidate_points.reverse()

        if _point_distance(concatenated_points[-1], candidate_points[0]) <= DEDUPLICATION_TOLERANCE:
            concatenated_points.extend(candidate_points[1:])
        else:
            concatenated_points.extend(candidate_points)

    return concatenated_points


def extract_profile_segments(
    model: NormalizedStepModel,
    num_samples: int = 200,
) -> ExtractedProfileSegments:
    """Extract all valid selectable profile segments from one normalized workpiece."""

    if num_samples < 2:
        raise ValueError("num_samples must be >= 2")

    if model.ocp_shape is not None:
        return _extract_profile_segments_from_ocp_shape(model, num_samples)
    return _extract_profile_segments_fallback(model, num_samples)


def load_and_extract_profile(
    file_path: Union[str, Path],
    num_samples: int = 200,
) -> list[tuple[float, float]]:
    """Load a STEP file, normalize it, and extract one default concatenated profile."""

    model = load_step_model(file_path)
    normalized_model = normalize_revolved_model(model)
    return extract_profile_points(normalized_model, num_samples=num_samples)


def _extract_profile_segments_from_ocp_shape(
    model: NormalizedStepModel,
    num_samples: int,
) -> ExtractedProfileSegments:
    """Extract all valid profile segments from the normalized OCP shape."""

    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt
    except Exception as exc:
        raise ValueError(EXTRACTION_ERROR) from exc

    if model.ocp_shape is None or model.ocp_shape.IsNull():
        raise ValueError(EXTRACTION_ERROR)

    section_plane = gp_Pln(gp_Ax3(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 1.0, 0.0)))
    section = BRepAlgoAPI_Section(model.ocp_shape, section_plane, False)
    section.Build()
    if not section.IsDone():
        raise ValueError(EXTRACTION_ERROR)

    explorer = TopExp_Explorer(section.Shape(), TopAbs_EDGE)
    chains: list[list[tuple[float, float]]] = []

    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        curve = BRepAdaptor_Curve(edge)
        first = curve.FirstParameter()
        last = curve.LastParameter()
        sample_count = max(12, num_samples // 10)
        chain: list[tuple[float, float]] = []

        for index in range(sample_count + 1):
            parameter = first + (last - first) * index / sample_count
            point = curve.Value(parameter)
            if abs(point.Y()) <= Y_SECTION_TOLERANCE:
                chain.append((point.X(), point.Z()))

        chain = _deduplicate_points(chain)
        if len(chain) >= 2:
            if chain[0][1] > chain[-1][1]:
                chain.reverse()
            chains.append(chain)

        explorer.Next()

    if not chains:
        raise ValueError(EXTRACTION_ERROR)
    _profile_debug(f"raw_candidate_chains={len(chains)}")

    candidate_chains = _filter_candidate_outer_chains(chains)
    if not candidate_chains:
        raise ValueError(EXTRACTION_ERROR)
    _profile_debug(f"filtered_candidate_chains={len(candidate_chains)}")

    merged_chains = _merge_ordered_chains(candidate_chains)
    _profile_debug(f"merged_candidate_chains={len(merged_chains)}")
    normalized_chains = _normalize_candidate_chains(merged_chains)
    if not normalized_chains:
        raise ValueError(EXTRACTION_ERROR)

    for index, chain in enumerate(normalized_chains):
        _profile_debug(_format_chain_stats(index, _build_profile_chain_stats(chain)))

    profile_segments = _build_profile_segments_from_chains(normalized_chains, num_samples=num_samples)
    _profile_debug(f"extracted_segments={len(profile_segments)}")
    for segment in profile_segments:
        _profile_debug(
            f"segment={segment.segment_id} "
            f"type={segment.segment_type} "
            f"fit_valid={segment.fit_radius_valid} "
            f"fit_radius={(segment.fit_radius if segment.fit_radius is not None else float('nan')):.6f} "
            f"fit_center=("
            f"{(segment.fit_center_x if segment.fit_center_x is not None else float('nan')):.6f}, "
            f"{(segment.fit_center_z if segment.fit_center_z is not None else float('nan')):.6f})"
        )
    return ExtractedProfileSegments(profile_segments=profile_segments)


def _extract_profile_segments_fallback(
    model: NormalizedStepModel,
    num_samples: int,
) -> ExtractedProfileSegments:
    """Extract valid profile segments from the fallback point-based model."""

    section_points = [
        (point_x, point_z)
        for point_x, point_y, point_z in model.points_3d
        if abs(point_y) <= Y_SECTION_TOLERANCE
    ]
    if len(section_points) < 2:
        raise ValueError(EXTRACTION_ERROR)

    ordered_points = _order_profile_points(section_points)
    deduplicated_points = _deduplicate_points(ordered_points)
    if len(deduplicated_points) < 2:
        raise ValueError(EXTRACTION_ERROR)

    profile_segments = _build_profile_segments_from_chains([deduplicated_points], num_samples=num_samples)
    return ExtractedProfileSegments(profile_segments=profile_segments)


def _build_profile_segments_from_chains(
    chains: list[list[tuple[float, float]]],
    *,
    num_samples: int,
) -> list[ProfileSegment]:
    """Convert merged chains into selectable geometrically segmented profile pieces."""

    if not chains:
        return []

    chain_sides = _determine_chain_profile_sides(chains)
    profile_segments: list[ProfileSegment] = []
    next_segment_id = 0
    for chain_index, chain in enumerate(chains):
        chain_side = chain_sides[chain_index]
        topological_segments = [segment for segment in split_profile_segments(chain) if len(segment) >= 2]
        for topological_segment in topological_segments:
            deduplicated_points = _deduplicate_points(topological_segment)
            if len(deduplicated_points) < 2:
                continue

            geometric_subsegments = _geometrically_split_segment(
                deduplicated_points,
                source_chain_index=chain_index,
            )
            _profile_debug(
                f"geometric_split source_chain={chain_index} subsegments={len(geometric_subsegments)}"
            )
            for subsegment_index, (segment_type, subsegment_points) in enumerate(geometric_subsegments):
                sampled_points = _resample_profile_points(subsegment_points, num_samples=max(12, num_samples))
                segment_stats = _build_profile_chain_stats(sampled_points)
                normalized_type = segment_type if segment_type in {"line", "arc", "mixed"} else "mixed"
                fit_center_x = None
                fit_center_z = None
                fit_radius = None
                fit_radius_valid = False
                fit_residual = None
                arc_theta_start = None
                arc_theta_end = None
                arc_delta_theta = None
                arc_direction = None
                arc_length = None
                arc_geometry_valid = False
                line_start_x = None
                line_start_z = None
                line_end_x = None
                line_end_z = None
                line_length = None
                line_valid = False
                if normalized_type == "line":
                    chord_length = _point_distance(sampled_points[0], sampled_points[-1]) if len(sampled_points) >= 2 else 0.0
                    polyline_length = segment_stats.polyline_length
                    arc_ratio = (
                        polyline_length / chord_length
                        if chord_length > DEDUPLICATION_TOLERANCE
                        else math.inf
                    )
                    total_turn_angle_deg = _compute_total_turn_angle_deg(sampled_points)
                    (
                        fit_center_x,
                        fit_center_z,
                        fit_radius,
                        fit_residual,
                        fit_radius_valid,
                    ) = _fit_arc_circle(sampled_points)
                    _profile_debug(f"line_recheck segment={next_segment_id}")
                    _profile_debug(
                        f"line_recheck chord_length={chord_length:.6f} "
                        f"polyline_length={polyline_length:.6f} ratio={arc_ratio:.6f}"
                    )
                    _profile_debug(f"line_recheck total_turn_angle={total_turn_angle_deg:.6f}")
                    _profile_debug(
                        f"line_recheck circle_fit_valid={fit_radius_valid} "
                        f"fit_radius={(fit_radius if fit_radius is not None else float('nan')):.6f} "
                        f"residual={(fit_residual if fit_residual is not None else float('nan')):.6f}"
                    )
                    if (
                        len(sampled_points) >= LINE_RECHECK_MIN_POINT_COUNT
                        and fit_radius_valid
                        and fit_residual is not None
                        and fit_residual <= LINE_TO_ARC_MAX_RELATIVE_RESIDUAL
                        and arc_ratio >= LINE_TO_ARC_MIN_RATIO
                        and abs(total_turn_angle_deg) >= LINE_TO_ARC_MIN_TURN_DEG
                    ):
                        normalized_type = "arc"
                        (
                            arc_theta_start,
                            arc_theta_end,
                            arc_delta_theta,
                            arc_direction,
                            arc_length,
                            arc_geometry_valid,
                        ) = _extract_arc_geometry_from_points(
                            sampled_points,
                            fit_center_x=fit_center_x,
                            fit_center_z=fit_center_z,
                            fit_radius=fit_radius,
                            fit_radius_valid=fit_radius_valid,
                        )
                        _profile_debug(f"segment={next_segment_id} reclassified line_to_arc")
                        _profile_debug(f"arc_geometry segment={next_segment_id}")
                        _profile_debug(
                            f"arc_theta_start={(arc_theta_start if arc_theta_start is not None else float('nan')):.6f} "
                            f"arc_theta_end={(arc_theta_end if arc_theta_end is not None else float('nan')):.6f}"
                        )
                        _profile_debug(f"arc_direction={(arc_direction if arc_direction is not None else 0)}")
                        _profile_debug(
                            f"arc_delta_theta={(arc_delta_theta if arc_delta_theta is not None else float('nan')):.6f}"
                        )
                        _profile_debug(
                            f"arc_length={(arc_length if arc_length is not None else float('nan')):.6f} "
                            f"arc_geometry_valid={arc_geometry_valid}"
                        )
                    else:
                        fit_center_x = None
                        fit_center_z = None
                        fit_radius = None
                        fit_radius_valid = False
                        fit_residual = None
                if normalized_type == "arc":
                    fit_center_x, fit_center_z, fit_radius, fit_residual, fit_radius_valid = _fit_arc_circle(sampled_points)
                    _profile_debug(
                        f"arc_fit segment={next_segment_id} point_count={len(sampled_points)}"
                    )
                    _profile_debug(
                        f"arc_fit center=({fit_center_x if fit_center_x is not None else float('nan'):.6f}, "
                        f"{fit_center_z if fit_center_z is not None else float('nan'):.6f}) "
                        f"radius={(fit_radius if fit_radius is not None else float('nan')):.6f} "
                        f"valid={fit_radius_valid}"
                    )
                    _profile_debug(
                        f"arc_fit residual={(fit_residual if fit_residual is not None else float('nan')):.6f}"
                    )
                    (
                        arc_theta_start,
                        arc_theta_end,
                        arc_delta_theta,
                        arc_direction,
                        arc_length,
                        arc_geometry_valid,
                    ) = _extract_arc_geometry_from_points(
                        sampled_points,
                        fit_center_x=fit_center_x,
                        fit_center_z=fit_center_z,
                        fit_radius=fit_radius,
                        fit_radius_valid=fit_radius_valid,
                    )
                    _profile_debug(f"arc_geometry segment={next_segment_id}")
                    _profile_debug(
                        f"arc_theta_start={(arc_theta_start if arc_theta_start is not None else float('nan')):.6f} "
                        f"arc_theta_end={(arc_theta_end if arc_theta_end is not None else float('nan')):.6f}"
                    )
                    _profile_debug(f"arc_direction={(arc_direction if arc_direction is not None else 0)}")
                    _profile_debug(
                        f"arc_delta_theta={(arc_delta_theta if arc_delta_theta is not None else float('nan')):.6f}"
                    )
                    _profile_debug(
                        f"arc_length={(arc_length if arc_length is not None else float('nan')):.6f} "
                        f"arc_geometry_valid={arc_geometry_valid}"
                    )
                if normalized_type == "line":
                    (
                        line_start_x,
                        line_start_z,
                        line_end_x,
                        line_end_z,
                        line_length,
                        line_valid,
                    ) = _extract_line_geometry(sampled_points)
                    if segment_stats.z_span <= DEDUPLICATION_TOLERANCE:
                        _profile_debug(
                            f"horizontal line kept as profile segment segment={next_segment_id}"
                        )
                    _profile_debug(
                        f"segment={next_segment_id} type=line "
                        f"x_span={segment_stats.x_span:.6f} z_span={segment_stats.z_span:.6f}"
                    )
                _profile_debug(
                    f"subsegment[{subsegment_index}] type={normalized_type} point_count={segment_stats.point_count}"
                )
                profile_segments.append(
                    ProfileSegment(
                        segment_id=next_segment_id,
                        name=f"segment_{next_segment_id}",
                        points=sampled_points,
                        point_count=segment_stats.point_count,
                        x_min=segment_stats.x_min,
                        x_max=segment_stats.x_max,
                        z_min=segment_stats.z_min,
                        z_max=segment_stats.z_max,
                        polyline_length=segment_stats.polyline_length,
                        segment_type=normalized_type,
                        profile_side=chain_side,
                        is_enabled=True,
                        fit_center_x=fit_center_x,
                        fit_center_z=fit_center_z,
                        fit_radius=fit_radius,
                        fit_radius_valid=fit_radius_valid,
                        fit_residual=fit_residual,
                        arc_theta_start=arc_theta_start,
                        arc_theta_end=arc_theta_end,
                        arc_delta_theta=arc_delta_theta,
                        arc_direction=arc_direction,
                        arc_length=arc_length,
                        arc_geometry_valid=arc_geometry_valid,
                        line_start_x=line_start_x,
                        line_start_z=line_start_z,
                        line_end_x=line_end_x,
                        line_end_z=line_end_z,
                        line_length=line_length,
                        line_valid=line_valid,
                    )
                )
                next_segment_id += 1
    return profile_segments


def _fit_arc_circle(
    points: list[tuple[float, float]],
) -> tuple[float | None, float | None, float | None, float | None, bool]:
    """Fit one circle to an arc segment using all of its points."""

    if len(points) < ARC_FIT_MIN_POINT_COUNT:
        return None, None, None, None, False

    sum_x = sum(point[0] for point in points)
    sum_z = sum(point[1] for point in points)
    sum_xx = sum(point[0] * point[0] for point in points)
    sum_zz = sum(point[1] * point[1] for point in points)
    sum_xz = sum(point[0] * point[1] for point in points)
    sum_b = sum(point[0] * point[0] + point[1] * point[1] for point in points)
    sum_xb = sum(point[0] * (point[0] * point[0] + point[1] * point[1]) for point in points)
    sum_zb = sum(point[1] * (point[0] * point[0] + point[1] * point[1]) for point in points)
    count = float(len(points))

    matrix = (
        (sum_xx, sum_xz, sum_x),
        (sum_xz, sum_zz, sum_z),
        (sum_x, sum_z, count),
    )
    rhs = (sum_xb, sum_zb, sum_b)
    determinant = _determinant3(matrix)
    if abs(determinant) <= DEDUPLICATION_TOLERANCE:
        return None, None, None, None, False

    determinant_dx = _determinant3(
        (
            (rhs[0], matrix[0][1], matrix[0][2]),
            (rhs[1], matrix[1][1], matrix[1][2]),
            (rhs[2], matrix[2][1], matrix[2][2]),
        )
    )
    determinant_dz = _determinant3(
        (
            (matrix[0][0], rhs[0], matrix[0][2]),
            (matrix[1][0], rhs[1], matrix[1][2]),
            (matrix[2][0], rhs[2], matrix[2][2]),
        )
    )
    determinant_c = _determinant3(
        (
            (matrix[0][0], matrix[0][1], rhs[0]),
            (matrix[1][0], matrix[1][1], rhs[1]),
            (matrix[2][0], matrix[2][1], rhs[2]),
        )
    )

    d_value = determinant_dx / determinant
    e_value = determinant_dz / determinant
    c_value = determinant_c / determinant
    center_x = d_value / 2.0
    center_z = e_value / 2.0
    radius_squared = center_x * center_x + center_z * center_z + c_value
    if radius_squared <= DEDUPLICATION_TOLERANCE:
        return center_x, center_z, None, None, False

    radius = math.sqrt(radius_squared)
    radial_errors = [
        abs(math.hypot(point_x - center_x, point_z - center_z) - radius)
        for point_x, point_z in points
    ]
    mean_abs_error = sum(radial_errors) / len(radial_errors)
    relative_residual = mean_abs_error / radius if radius > DEDUPLICATION_TOLERANCE else math.inf
    is_valid = relative_residual <= ARC_FIT_MAX_RELATIVE_RESIDUAL
    return center_x, center_z, radius, relative_residual, is_valid


def _extract_arc_geometry_from_points(
    points: list[tuple[float, float]],
    *,
    fit_center_x: float | None,
    fit_center_z: float | None,
    fit_radius: float | None,
    fit_radius_valid: bool,
) -> tuple[float | None, float | None, float | None, int | None, float | None, bool]:
    """Build one stable analytic arc description from all arc-segment points."""

    if not fit_radius_valid or fit_center_x is None or fit_center_z is None or fit_radius is None:
        return None, None, None, None, None, False
    if len(points) < 3 or fit_radius <= DEDUPLICATION_TOLERANCE:
        return None, None, None, None, None, False

    raw_angles = [
        math.atan2(point_z - fit_center_z, point_x - fit_center_x)
        for point_x, point_z in points
    ]
    unwrapped_angles = [raw_angles[0]]
    for raw_angle in raw_angles[1:]:
        delta = _wrap_radians(raw_angle - unwrapped_angles[-1])
        unwrapped_angles.append(unwrapped_angles[-1] + delta)

    theta_start = float(unwrapped_angles[0])
    theta_end = float(unwrapped_angles[-1])
    delta_theta = float(theta_end - theta_start)
    if math.isclose(delta_theta, 0.0, abs_tol=DEDUPLICATION_TOLERANCE):
        return None, None, None, None, None, False

    arc_direction = 1 if delta_theta > 0.0 else -1
    arc_length = abs(delta_theta) * float(fit_radius)
    if arc_length <= DEDUPLICATION_TOLERANCE:
        return None, None, None, None, None, False

    return theta_start, theta_end, delta_theta, arc_direction, arc_length, True


def _determinant3(matrix: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]) -> float:
    """Return the determinant of one 3x3 matrix."""

    return (
        matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )


def _extract_line_geometry(
    points: list[tuple[float, float]],
) -> tuple[float | None, float | None, float | None, float | None, float | None, bool]:
    """Extract one analytic line description from a line-like segment."""

    if len(points) < 2:
        return None, None, None, None, None, False

    start_x, start_z = points[0]
    end_x, end_z = points[-1]
    line_length = math.hypot(end_x - start_x, end_z - start_z)
    if line_length <= DEDUPLICATION_TOLERANCE:
        return start_x, start_z, end_x, end_z, None, False
    return start_x, start_z, end_x, end_z, line_length, True


def _compute_total_turn_angle_deg(points: list[tuple[float, float]]) -> float:
    """Return the signed cumulative tangent-turn angle, in degrees, over one point sequence."""

    turn_values = _compute_turn_values(points)
    if not turn_values:
        return 0.0
    return math.degrees(sum(turn_values))


def _geometrically_split_segment(
    points: list[tuple[float, float]],
    *,
    source_chain_index: int | None = None,
) -> list[tuple[str, list[tuple[float, float]]]]:
    """Split one merged segment into geometric subsegments without changing merge logic."""

    if len(points) < 3:
        return [("line", points)]

    subsegments: list[tuple[str, list[tuple[float, float]]]] = []
    corner_split_segments = _split_segment_at_corners(points, source_chain_index=source_chain_index)
    for corner_segment in corner_split_segments:
        point_labels = _classify_segment_points(corner_segment)
        labeled_ranges = _collect_labeled_ranges(point_labels)
        merged_ranges = _merge_short_labeled_ranges(corner_segment, labeled_ranges)
        for segment_type, start_index, end_index in merged_ranges:
            subsegment_points = corner_segment[start_index : end_index + 1]
            if len(subsegment_points) < 2:
                continue
            subsegments.append((segment_type, subsegment_points))

    return subsegments or [("mixed", points)]


def _split_segment_at_corners(
    points: list[tuple[float, float]],
    *,
    source_chain_index: int | None = None,
) -> list[list[tuple[float, float]]]:
    """Split one merged chain only at strong tangent-discontinuity corners."""

    if source_chain_index is not None:
        _profile_debug(
            f"corner_split source_chain={source_chain_index} point_count={len(points)}"
        )

    if len(points) < max(CORNER_SPLIT_NEIGHBOR_STEP * 2 + 1, CORNER_SPLIT_MIN_SUBSEGMENT_POINTS * 2 - 1):
        if source_chain_index is not None:
            _profile_debug("corner_split result subsegments=1")
        return [points]

    turn_values = _compute_turn_values(points)
    raw_candidates = _detect_corner_candidates(points, turn_values)
    accepted_indices = _select_corner_split_indices(points, raw_candidates)
    if not accepted_indices:
        if source_chain_index is not None:
            _profile_debug("corner_split result subsegments=1")
        return [points]

    split_segments: list[list[tuple[float, float]]] = []
    start_index = 0
    for split_index in accepted_indices:
        split_segments.append(points[start_index : split_index + 1])
        start_index = split_index
    split_segments.append(points[start_index:])

    normalized_segments = [
        segment
        for segment in split_segments
        if len(segment) >= 2
    ]
    if source_chain_index is not None:
        _profile_debug(f"corner_split result subsegments={len(normalized_segments)}")
    return normalized_segments or [points]


def _detect_corner_candidates(
    points: list[tuple[float, float]],
    turn_values: list[float],
) -> list[tuple[int, float]]:
    """Return strong corner candidates based on tangent discontinuity rather than smooth curvature."""

    if len(points) < CORNER_SPLIT_NEIGHBOR_STEP * 2 + 1:
        return []

    candidates: list[tuple[int, float]] = []
    for point_index in range(CORNER_SPLIT_NEIGHBOR_STEP, len(points) - CORNER_SPLIT_NEIGHBOR_STEP):
        left_point = points[point_index - CORNER_SPLIT_NEIGHBOR_STEP]
        center_point = points[point_index]
        right_point = points[point_index + CORNER_SPLIT_NEIGHBOR_STEP]
        previous_tangent = _normalize_vector(
            center_point[0] - left_point[0],
            center_point[1] - left_point[1],
        )
        next_tangent = _normalize_vector(
            right_point[0] - center_point[0],
            right_point[1] - center_point[1],
        )
        if previous_tangent is None or next_tangent is None:
            _profile_debug(f"corner_reject index={point_index} reason=degenerate_tangent")
            continue

        angle_deg = _angle_between_unit_vectors_deg(previous_tangent, next_tangent)
        _profile_debug(f"corner_candidate index={point_index} angle_deg={angle_deg:.6f}")
        if angle_deg < CORNER_SPLIT_MIN_ANGLE_DEG:
            _profile_debug(f"corner_reject index={point_index} reason=angle_below_threshold")
            continue

        local_turn_start = max(0, point_index - CORNER_SPLIT_NEIGHBOR_STEP)
        local_turn_end = min(len(turn_values), point_index + CORNER_SPLIT_NEIGHBOR_STEP)
        local_turn_window = turn_values[local_turn_start:local_turn_end]
        if len(local_turn_window) >= 2 and _is_stable_arc_window(local_turn_window):
            _profile_debug(f"corner_reject index={point_index} reason=smooth_arc_like")
            continue

        candidates.append((point_index, angle_deg))
    return candidates


def _select_corner_split_indices(
    points: list[tuple[float, float]],
    candidates: list[tuple[int, float]],
) -> list[int]:
    """Keep only the strongest candidate near each corner and enforce minimum subsegment sizes."""

    if not candidates:
        return []

    grouped_candidates: list[list[tuple[int, float]]] = []
    current_group: list[tuple[int, float]] = [candidates[0]]
    for candidate in candidates[1:]:
        if candidate[0] - current_group[-1][0] <= CORNER_SPLIT_CLUSTER_GAP:
            current_group.append(candidate)
            continue
        grouped_candidates.append(current_group)
        current_group = [candidate]
    grouped_candidates.append(current_group)

    filtered_candidates: list[tuple[int, float]] = []
    for group in grouped_candidates:
        strongest_candidate = max(group, key=lambda item: item[1])
        for candidate_index, _candidate_angle in group:
            if candidate_index == strongest_candidate[0]:
                continue
            _profile_debug(
                f"corner_reject index={candidate_index} reason=weaker_neighbor_candidate"
            )
        filtered_candidates.append(strongest_candidate)

    accepted_indices: list[int] = []
    previous_split = 0
    for point_index, angle_deg in filtered_candidates:
        left_count = point_index - previous_split + 1
        right_count = len(points) - point_index
        if left_count < CORNER_SPLIT_MIN_SUBSEGMENT_POINTS:
            _profile_debug(f"corner_reject index={point_index} reason=left_subsegment_too_short")
            continue
        if right_count < CORNER_SPLIT_MIN_SUBSEGMENT_POINTS:
            _profile_debug(f"corner_reject index={point_index} reason=right_subsegment_too_short")
            continue
        accepted_indices.append(point_index)
        previous_split = point_index
        _profile_debug(f"corner_accept index={point_index} angle_deg={angle_deg:.6f}")

    return accepted_indices


def _normalize_vector(dx: float, dz: float) -> tuple[float, float] | None:
    """Return one normalized 2D vector, or None when the vector is degenerate."""

    magnitude = math.hypot(dx, dz)
    if magnitude <= DEDUPLICATION_TOLERANCE:
        return None
    return dx / magnitude, dz / magnitude


def _angle_between_unit_vectors_deg(
    left_vector: tuple[float, float],
    right_vector: tuple[float, float],
) -> float:
    """Return the unsigned angle between two already normalized 2D vectors in degrees."""

    dot_value = max(-1.0, min(1.0, left_vector[0] * right_vector[0] + left_vector[1] * right_vector[1]))
    return math.degrees(math.acos(dot_value))


def _classify_segment_points(points: list[tuple[float, float]]) -> list[str]:
    """Classify each point along one merged segment as line, arc, or mixed."""

    if len(points) < 3:
        return ["line"] * len(points)

    turn_values = _compute_turn_values(points)
    if not turn_values:
        return ["line"] * len(points)

    point_labels = ["mixed"] * len(points)
    turn_signs = [0 for _ in turn_values]
    arc_core_indices: list[int] = []

    for turn_index, turn_value in enumerate(turn_values):
        abs_turn_deg = abs(math.degrees(turn_value))
        if abs_turn_deg <= LINE_TURN_ANGLE_TOL_DEG:
            continue

        local_window = turn_values[max(0, turn_index - 2) : min(len(turn_values), turn_index + 3)]
        if _is_stable_arc_window(local_window):
            arc_core_indices.append(turn_index)
            turn_signs[turn_index] = 1 if turn_value > 0.0 else -1

    for core_index in arc_core_indices:
        core_sign = turn_signs[core_index]
        left_index = core_index
        right_index = core_index

        while left_index - 1 >= 0 and _is_arc_transition_turn(turn_values[left_index - 1], core_sign):
            left_index -= 1
        while right_index + 1 < len(turn_values) and _is_arc_transition_turn(turn_values[right_index + 1], core_sign):
            right_index += 1

        for turn_index in range(left_index, right_index + 1):
            point_labels[turn_index + 1] = "arc"

    for index, turn_value in enumerate(turn_values, start=1):
        if point_labels[index] == "arc":
            continue
        abs_turn_deg = abs(math.degrees(turn_value))
        if abs_turn_deg <= LINE_TURN_ANGLE_TOL_DEG:
            point_labels[index] = "line"

    point_labels = _smooth_point_labels(point_labels)
    if len(point_labels) >= 2:
        point_labels[0] = point_labels[1]
        point_labels[-1] = point_labels[-2]
    return point_labels


def _compute_turn_values(points: list[tuple[float, float]]) -> list[float]:
    """Compute signed local turn angles between adjacent edges in one point sequence."""

    edge_angles: list[float] = []
    for left_point, right_point in zip(points, points[1:]):
        dx = right_point[0] - left_point[0]
        dz = right_point[1] - left_point[1]
        if math.hypot(dx, dz) <= DEDUPLICATION_TOLERANCE:
            continue
        edge_angles.append(math.atan2(dz, dx))

    turn_values: list[float] = []
    for left_angle, right_angle in zip(edge_angles, edge_angles[1:]):
        turn = right_angle - left_angle
        while turn > math.pi:
            turn -= 2.0 * math.pi
        while turn < -math.pi:
            turn += 2.0 * math.pi
        turn_values.append(turn)
    return turn_values


def _is_stable_arc_window(turn_values: list[float]) -> bool:
    """Return whether one local turn window looks like a stable arc rather than noise."""

    if len(turn_values) < 2:
        return False

    dominant_turns_deg = _extract_dominant_arc_turns_deg(turn_values)
    if len(dominant_turns_deg) < 2:
        return False
    if min(dominant_turns_deg) < ARC_TURN_ANGLE_MIN_DEG:
        return False
    if sum(dominant_turns_deg) < ARC_CUMULATIVE_TURN_MIN_DEG:
        return False

    mean_turn = sum(dominant_turns_deg) / len(dominant_turns_deg)
    if mean_turn <= 1e-9:
        return False

    variance = sum((turn_value - mean_turn) ** 2 for turn_value in dominant_turns_deg) / len(dominant_turns_deg)
    relative_std = math.sqrt(variance) / mean_turn
    return relative_std <= ARC_TURN_STABILITY_RATIO


def _extract_dominant_arc_turns_deg(turn_values: list[float]) -> list[float]:
    """Return the dominant-sign non-zero turn magnitudes from one local window."""

    positive_turns = [
        abs(math.degrees(turn_value))
        for turn_value in turn_values
        if turn_value > 0.0 and abs(math.degrees(turn_value)) >= ARC_TURN_ANGLE_MIN_DEG
    ]
    negative_turns = [
        abs(math.degrees(turn_value))
        for turn_value in turn_values
        if turn_value < 0.0 and abs(math.degrees(turn_value)) >= ARC_TURN_ANGLE_MIN_DEG
    ]

    if not positive_turns and not negative_turns:
        return []
    if len(positive_turns) > len(negative_turns):
        return positive_turns
    if len(negative_turns) > len(positive_turns):
        return negative_turns
    return positive_turns if sum(positive_turns) >= sum(negative_turns) else negative_turns


def _wrap_radians(delta_rad: float) -> float:
    """Wrap one radian delta into the shortest signed interval."""

    wrapped = (delta_rad + math.pi) % (2.0 * math.pi) - math.pi
    if math.isclose(wrapped, -math.pi, abs_tol=DEDUPLICATION_TOLERANCE) and delta_rad > 0.0:
        return math.pi
    return wrapped


def _is_arc_transition_turn(turn_value: float, expected_sign: int) -> bool:
    """Return whether one local turn is compatible with a nearby stable arc region."""

    abs_turn_deg = abs(math.degrees(turn_value))
    if abs_turn_deg < ARC_TURN_ANGLE_MIN_DEG * 0.5:
        return False
    if expected_sign == 0:
        return False
    turn_sign = 1 if turn_value > 0.0 else -1
    return turn_sign == expected_sign


def _smooth_point_labels(point_labels: list[str]) -> list[str]:
    """Reduce single-point label noise without turning uncertain regions into false arcs."""

    if len(point_labels) < 3:
        return point_labels

    smoothed = list(point_labels)
    for index in range(1, len(point_labels) - 1):
        left_label = smoothed[index - 1]
        current_label = smoothed[index]
        right_label = smoothed[index + 1]
        if current_label != "mixed":
            continue
        if left_label == right_label and left_label in {"line", "arc"}:
            smoothed[index] = left_label
    return smoothed


def _collect_labeled_ranges(point_labels: list[str]) -> list[tuple[str, int, int]]:
    """Convert point labels into continuous labeled index ranges."""

    if not point_labels:
        return []

    ranges: list[tuple[str, int, int]] = []
    current_label = point_labels[0]
    start_index = 0
    for index, label in enumerate(point_labels[1:], start=1):
        if label == current_label:
            continue
        ranges.append((current_label, start_index, index))
        current_label = label
        start_index = index
    ranges.append((current_label, start_index, len(point_labels) - 1))
    return ranges


def _merge_short_labeled_ranges(
    points: list[tuple[float, float]],
    labeled_ranges: list[tuple[str, int, int]],
) -> list[tuple[str, int, int]]:
    """Merge overly short geometric ranges back into neighbors to avoid fragmentation."""

    if not labeled_ranges:
        return []

    minimum_length = max(
        _build_profile_chain_stats(points).polyline_length * MIN_SUBSEGMENT_LENGTH_RATIO,
        MIN_SUBSEGMENT_LENGTH_ABS,
    )
    merged_ranges = list(labeled_ranges)
    while True:
        changed = False
        for index, (segment_type, start_index, end_index) in enumerate(list(merged_ranges)):
            point_count = end_index - start_index + 1
            segment_length = _compute_range_length(points, start_index, end_index)
            if point_count >= MIN_POINTS_PER_SUBSEGMENT or segment_length >= minimum_length:
                continue
            if len(merged_ranges) == 1:
                merged_ranges[0] = ("mixed", start_index, end_index)
                return merged_ranges

            if index == 0:
                right_label, _right_start, right_end = merged_ranges[1]
                merged_ranges[1] = (right_label, start_index, right_end)
                merged_ranges.pop(0)
            elif index == len(merged_ranges) - 1:
                left_label, left_start, _left_end = merged_ranges[index - 1]
                merged_ranges[index - 1] = (left_label, left_start, end_index)
                merged_ranges.pop(index)
            else:
                left_label, left_start, left_end = merged_ranges[index - 1]
                right_label, right_start, right_end = merged_ranges[index + 1]
                left_gap = _compute_range_length(points, left_start, end_index)
                right_gap = _compute_range_length(points, start_index, right_end)
                if left_gap <= right_gap:
                    merged_ranges[index - 1] = (left_label, left_start, end_index)
                    merged_ranges.pop(index)
                else:
                    merged_ranges[index + 1] = (right_label, start_index, right_end)
                    merged_ranges.pop(index)
            changed = True
            break
        if not changed:
            break

    normalized_ranges: list[tuple[str, int, int]] = []
    for segment_type, start_index, end_index in merged_ranges:
        normalized_type = segment_type if segment_type in {"line", "arc", "mixed"} else "mixed"
        if normalized_ranges and normalized_ranges[-1][0] == normalized_type:
            previous_type, previous_start, _previous_end = normalized_ranges[-1]
            normalized_ranges[-1] = (previous_type, previous_start, end_index)
        else:
            normalized_ranges.append((normalized_type, start_index, end_index))
    return _absorb_transition_mixed_ranges(normalized_ranges)


def _absorb_transition_mixed_ranges(
    labeled_ranges: list[tuple[str, int, int]],
) -> list[tuple[str, int, int]]:
    """Absorb short mixed transition buffers into neighboring stable geometric ranges."""

    if not labeled_ranges:
        return []

    merged_ranges = list(labeled_ranges)
    while True:
        changed = False
        for index, (segment_type, start_index, end_index) in enumerate(list(merged_ranges)):
            if segment_type != "mixed":
                continue

            point_count = end_index - start_index + 1
            if point_count > 3:
                continue

            left_label = merged_ranges[index - 1][0] if index > 0 else None
            right_label = merged_ranges[index + 1][0] if index + 1 < len(merged_ranges) else None
            if left_label == right_label and left_label in {"line", "arc"}:
                left_start = merged_ranges[index - 1][1]
                merged_ranges[index - 1] = (left_label, left_start, end_index)
                merged_ranges.pop(index)
                changed = True
                break

            if left_label in {"line", "arc"} and right_label in {"line", "arc"}:
                right_end = merged_ranges[index + 1][2]
                merged_ranges[index + 1] = (right_label, start_index, right_end)
                merged_ranges.pop(index)
                changed = True
                break

            if left_label in {"line", "arc"} and right_label is None:
                left_start = merged_ranges[index - 1][1]
                merged_ranges[index - 1] = (left_label, left_start, end_index)
                merged_ranges.pop(index)
                changed = True
                break

            if right_label in {"line", "arc"} and left_label is None:
                right_end = merged_ranges[index + 1][2]
                merged_ranges[index + 1] = (right_label, start_index, right_end)
                merged_ranges.pop(index)
                changed = True
                break

        if not changed:
            break

    normalized_ranges: list[tuple[str, int, int]] = []
    for segment_type, start_index, end_index in merged_ranges:
        if normalized_ranges and normalized_ranges[-1][0] == segment_type:
            previous_type, previous_start, _previous_end = normalized_ranges[-1]
            normalized_ranges[-1] = (previous_type, previous_start, end_index)
        else:
            normalized_ranges.append((segment_type, start_index, end_index))
    return normalized_ranges


def _compute_range_length(
    points: list[tuple[float, float]],
    start_index: int,
    end_index: int,
) -> float:
    """Return polyline length over one inclusive point-index range."""

    if end_index <= start_index:
        return 0.0
    return sum(
        _point_distance(points[index - 1], points[index])
        for index in range(start_index + 1, end_index + 1)
    )


def _determine_chain_profile_sides(chains: list[list[tuple[float, float]]]) -> list[str]:
    """Assign one path-offset side to each merged chain without picking a final profile."""

    chain_stats = [_build_profile_chain_stats(chain) for chain in chains]
    chain_sides = ["outer"] * len(chains)
    for index, candidate_stats in enumerate(chain_stats):
        for reference_stats in chain_stats:
            if reference_stats.mean_x <= candidate_stats.mean_x:
                continue
            if _compute_z_overlap_ratio(candidate_stats, reference_stats) < PROFILE_Z_OVERLAP_RATIO:
                continue
            min_mean_x_gap = max(1.0, reference_stats.mean_x * INNER_PROFILE_MEAN_X_GAP_RATIO)
            if reference_stats.mean_x - candidate_stats.mean_x < min_mean_x_gap:
                continue
            chain_sides[index] = "inner"
            break
    return chain_sides


def _filter_candidate_outer_chains(chains: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Filter section chains down to plausible positive-X contour candidates."""

    candidates: list[list[tuple[float, float]]] = []
    for chain in chains:
        x_values = [point[0] for point in chain]
        z_values = [point[1] for point in chain]
        z_span = max(z_values) - min(z_values)
        avg_x = sum(x_values) / len(x_values)
        max_x = max(x_values)

        if max_x <= AXIS_CHAIN_TOLERANCE:
            continue
        if avg_x <= AXIS_CHAIN_TOLERANCE:
            continue
        if z_span <= DEDUPLICATION_TOLERANCE and max_x <= AXIS_CHAIN_TOLERANCE * 2.0:
            continue

        candidates.append(chain)

    return candidates


def _merge_ordered_chains(chains: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Merge section chains conservatively to avoid bridging outer and inner walls."""

    if not chains:
        return []

    chain_stats = [_build_profile_chain_stats(chain) for chain in chains]
    reference_z_span = max(stats.z_span for stats in chain_stats)
    chain_types = [_classify_chain_type(stats, reference_z_span) for stats in chain_stats]

    for index, (stats, chain_type) in enumerate(zip(chain_stats, chain_types, strict=False)):
        _profile_debug(
            f"filtered_chain[{index}] "
            f"point_count={stats.point_count} "
            f"x_span={stats.x_span:.6f} "
            f"z_span={stats.z_span:.6f} "
            f"mean_x={stats.mean_x:.6f} "
            f"type={chain_type}"
        )

    sorted_entries = sorted(
        [ChainMergeEntry(list(chain), [index]) for index, chain in enumerate(chains)],
        key=lambda entry: (entry.points[0][1], entry.points[-1][1]),
    )
    merged: list[ChainMergeEntry] = []

    for entry in sorted_entries:
        current = ChainMergeEntry(list(entry.points), list(entry.source_indices))
        if not merged:
            merged.append(current)
            continue

        previous = merged[-1]
        merged_entry, reject_reason = _merge_chain_pair(
            previous,
            current,
            chain_stats=chain_stats,
            chain_types=chain_types,
            reference_z_span=reference_z_span,
        )
        if merged_entry is not None:
            merged[-1] = merged_entry
        else:
            if reject_reason is not None:
                _profile_debug(
                    f"merge_reject left={previous.source_indices} right={current.source_indices} "
                    f"reason={reject_reason}"
                )
            merged.append(current)

    return [entry.points for entry in merged]


def _normalize_candidate_chains(chains: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Orient and deduplicate merged chains before profile-role classification."""

    normalized_chains: list[list[tuple[float, float]]] = []
    for chain in chains:
        ordered_points = _order_profile_points(chain)
        deduplicated_points = _deduplicate_points(ordered_points)
        if len(deduplicated_points) >= 2:
            normalized_chains.append(deduplicated_points)
    return normalized_chains


def _select_outer_and_inner_chains(
    chains: list[list[tuple[float, float]]],
) -> tuple[list[tuple[float, float]], list[tuple[float, float]] | None]:
    """Select one outer chain and one optional inner chain from merged candidates."""

    if not chains:
        raise ValueError(EXTRACTION_ERROR)

    outer_chain = _select_main_outer_chain(chains)
    outer_index = chains.index(outer_chain)
    outer_stats = _build_profile_chain_stats(outer_chain)
    _profile_debug(f"outer_selected={_format_chain_stats(outer_index, outer_stats)}")
    inner_candidates: list[tuple[tuple[float, float, int, float], list[tuple[float, float]]]] = []

    for index, chain in enumerate(chains):
        if chain == outer_chain:
            continue

        candidate_stats = _build_profile_chain_stats(chain)
        min_point_count = max(MIN_PROFILE_CHAIN_POINTS, outer_stats.point_count // 5)
        min_required_z_span = outer_stats.z_span * PROFILE_COMPLETENESS_RATIO
        if not _is_complete_profile_candidate(candidate_stats, outer_stats):
            if candidate_stats.point_count < min_point_count:
                _profile_debug(
                    f"inner_candidate[{index}] rejected: point_count_too_small "
                    f"point_count={candidate_stats.point_count} min_required={min_point_count}"
                )
            else:
                _profile_debug(
                    f"inner_candidate[{index}] rejected: z_span_too_small "
                    f"z_span={candidate_stats.z_span:.6f} min_required={min_required_z_span:.6f}"
                )
            continue

        overlap_ratio = _compute_z_overlap_ratio(candidate_stats, outer_stats)
        if overlap_ratio < PROFILE_Z_OVERLAP_RATIO:
            _profile_debug(
                f"inner_candidate[{index}] rejected: overlap_too_low "
                f"overlap_ratio={overlap_ratio:.6f} min_required={PROFILE_Z_OVERLAP_RATIO:.6f}"
            )
            continue

        min_mean_x_gap = max(1.0, outer_stats.mean_x * INNER_PROFILE_MEAN_X_GAP_RATIO)
        if outer_stats.mean_x - candidate_stats.mean_x < min_mean_x_gap:
            _profile_debug(
                f"inner_candidate[{index}] rejected: mean_x_gap_too_small "
                f"mean_x_gap={(outer_stats.mean_x - candidate_stats.mean_x):.6f} "
                f"min_required={min_mean_x_gap:.6f}"
            )
            continue

        _profile_debug(
            f"inner_candidate[{index}] accepted "
            f"overlap_ratio={overlap_ratio:.6f} "
            f"mean_x_gap={(outer_stats.mean_x - candidate_stats.mean_x):.6f}"
        )
        inner_candidates.append(
            (
                (
                    overlap_ratio,
                    candidate_stats.z_span,
                    candidate_stats.point_count,
                    outer_stats.mean_x - candidate_stats.mean_x,
                ),
                chain,
            )
        )

    if not inner_candidates:
        _profile_debug("available_profiles=outer_only")
        return outer_chain, None

    inner_candidates.sort(key=lambda item: item[0], reverse=True)
    selected_inner_chain = inner_candidates[0][1]
    selected_inner_index = chains.index(selected_inner_chain)
    selected_inner_stats = _build_profile_chain_stats(selected_inner_chain)
    _profile_debug(f"inner_selected={_format_chain_stats(selected_inner_index, selected_inner_stats)}")
    _profile_debug("available_profiles=outer_and_inner")
    return outer_chain, selected_inner_chain


def _select_main_outer_chain(chains: list[list[tuple[float, float]]]) -> list[tuple[float, float]]:
    """Select the main outer contour chain from merged positive-X candidates."""

    if not chains:
        raise ValueError(EXTRACTION_ERROR)

    def score(chain: list[tuple[float, float]]) -> tuple[float, float, float]:
        z_values = [point[1] for point in chain]
        x_values = [point[0] for point in chain]
        length = sum(_point_distance(chain[index - 1], chain[index]) for index in range(1, len(chain)))
        return max(z_values) - min(z_values), length, sum(x_values) / len(x_values)

    return max(chains, key=score)


def _build_profile_chain_stats(chain: list[tuple[float, float]]) -> ProfileChainStats:
    """Build summary statistics for one merged contour chain."""

    z_values = [point[1] for point in chain]
    x_values = [point[0] for point in chain]
    return ProfileChainStats(
        x_min=min(x_values),
        x_max=max(x_values),
        x_span=max(x_values) - min(x_values),
        z_min=min(z_values),
        z_max=max(z_values),
        z_span=max(z_values) - min(z_values),
        mean_x=sum(x_values) / len(x_values),
        point_count=len(chain),
        polyline_length=sum(_point_distance(chain[index - 1], chain[index]) for index in range(1, len(chain))),
    )


def _is_complete_profile_candidate(
    candidate_stats: ProfileChainStats,
    outer_stats: ProfileChainStats,
) -> bool:
    """Return whether a merged chain is complete enough to be an inner candidate."""

    min_point_count = max(MIN_PROFILE_CHAIN_POINTS, outer_stats.point_count // 5)
    min_required_z_span = outer_stats.z_span * PROFILE_COMPLETENESS_RATIO
    if candidate_stats.point_count < min_point_count:
        return False
    if candidate_stats.z_span < min_required_z_span:
        return False
    return True


def _compute_z_overlap_ratio(
    candidate_stats: ProfileChainStats,
    outer_stats: ProfileChainStats,
) -> float:
    """Return normalized Z-range overlap between two complete profile candidates."""

    overlap = min(candidate_stats.z_max, outer_stats.z_max) - max(candidate_stats.z_min, outer_stats.z_min)
    if overlap <= 0.0:
        return 0.0

    normalization = min(candidate_stats.z_span, outer_stats.z_span)
    if normalization <= DEDUPLICATION_TOLERANCE:
        return 0.0
    return overlap / normalization


def _order_profile_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Orient an already ordered outer contour from bottom to top."""

    if not points:
        return []

    ordered = _deduplicate_points(points)
    start_z = ordered[0][1]
    end_z = ordered[-1][1]
    if start_z > end_z:
        ordered.reverse()
    elif abs(start_z - end_z) <= DEDUPLICATION_TOLERANCE and len(ordered) >= 2:
        if ordered[0][0] > ordered[-1][0]:
            ordered.reverse()
    return ordered


def _merge_chain_pair(
    first: ChainMergeEntry,
    second: ChainMergeEntry,
    chain_stats: list[ProfileChainStats],
    chain_types: list[str],
    reference_z_span: float,
) -> tuple[ChainMergeEntry | None, str | None]:
    """Merge two ordered chains if geometry and chain roles indicate low risk."""

    candidates: list[tuple[float, list[tuple[float, float]]]] = []
    orientations = (
        (first.points, second.points),
        (first.points, list(reversed(second.points))),
        (list(reversed(first.points)), second.points),
        (list(reversed(first.points)), list(reversed(second.points))),
    )
    for left_chain, right_chain in orientations:
        distance = _point_distance(left_chain[-1], right_chain[0])
        if distance <= CHAIN_MERGE_DISTANCE:
            candidates.append((distance, _deduplicate_points(left_chain + right_chain)))

    if not candidates:
        return None, "endpoint_too_far"

    candidates.sort(key=lambda item: item[0])
    best_distance, merged_points = candidates[0]
    merged_indices = first.source_indices + second.source_indices
    reject_reason = _evaluate_merge_rejection(
        first=first,
        second=second,
        merged_source_indices=merged_indices,
        chain_stats=chain_stats,
        chain_types=chain_types,
        reference_z_span=reference_z_span,
    )
    _profile_debug(
        f"merge_try left={first.source_indices} right={second.source_indices} "
        f"left_type={_describe_entry_type(first, chain_types)} "
        f"right_type={_describe_entry_type(second, chain_types)} "
        f"endpoint_distance={best_distance:.6f}"
    )
    if reject_reason is not None:
        return None, reject_reason

    _profile_debug(
        f"merge_accept left={first.source_indices} right={second.source_indices} "
        f"reason=compatible_chain_progression"
    )
    return ChainMergeEntry(merged_points, merged_indices), None


def _classify_chain_type(stats: ProfileChainStats, reference_z_span: float) -> str:
    """Classify one filtered chain by relative vertical/horizontal dominance."""

    safe_reference_z_span = max(reference_z_span, DEDUPLICATION_TOLERANCE)
    safe_x_span = max(stats.x_span, DEDUPLICATION_TOLERANCE)
    safe_z_span = max(stats.z_span, DEDUPLICATION_TOLERANCE)

    z_ratio = stats.z_span / safe_reference_z_span
    vertical_dominance = stats.z_span / safe_x_span
    horizontal_dominance = stats.x_span / safe_z_span

    if z_ratio >= 0.45 and vertical_dominance >= 1.2:
        return "vertical_like"
    if z_ratio <= 0.35 and horizontal_dominance >= 1.5:
        return "horizontal_connector_like"
    return "mixed"


def _describe_entry_type(entry: ChainMergeEntry, chain_types: list[str]) -> str:
    """Return a readable type summary for one merge entry."""

    entry_types = sorted({chain_types[index] for index in entry.source_indices})
    if not entry_types:
        return "unknown"
    if len(entry_types) == 1:
        return entry_types[0]
    return "+".join(entry_types)


def _evaluate_merge_rejection(
    first: ChainMergeEntry,
    second: ChainMergeEntry,
    merged_source_indices: list[int],
    chain_stats: list[ProfileChainStats],
    chain_types: list[str],
    reference_z_span: float,
) -> str | None:
    """Return a rejection reason when one merge would blur outer/inner boundaries."""

    if _is_type_mismatch_without_progression(first, second, chain_stats, chain_types, reference_z_span):
        return "type_mismatch"
    if _would_bridge_outer_inner_boundary(merged_source_indices, chain_stats, chain_types, reference_z_span):
        if any(chain_types[index] == "horizontal_connector_like" for index in merged_source_indices):
            return "connector_bridge"
        return "likely_outer_inner_boundary"
    return None


def _is_type_mismatch_without_progression(
    first: ChainMergeEntry,
    second: ChainMergeEntry,
    chain_stats: list[ProfileChainStats],
    chain_types: list[str],
    reference_z_span: float,
) -> bool:
    """Detect merges where a connector-like chain cannot reasonably extend a profile."""

    first_types = {chain_types[index] for index in first.source_indices}
    second_types = {chain_types[index] for index in second.source_indices}
    if "horizontal_connector_like" not in first_types.union(second_types):
        return False

    first_has_tall_vertical = _entry_has_tall_vertical(first.source_indices, chain_stats, chain_types, reference_z_span)
    second_has_tall_vertical = _entry_has_tall_vertical(second.source_indices, chain_stats, chain_types, reference_z_span)
    if first_has_tall_vertical or second_has_tall_vertical:
        return False

    return first_types != second_types


def _would_bridge_outer_inner_boundary(
    merged_source_indices: list[int],
    chain_stats: list[ProfileChainStats],
    chain_types: list[str],
    reference_z_span: float,
) -> bool:
    """Return whether one merged entry would contain two overlapping wall-like chains."""

    vertical_indices = [
        index
        for index in merged_source_indices
        if chain_types[index] == "vertical_like"
        and chain_stats[index].z_span >= max(reference_z_span * 0.55, DEDUPLICATION_TOLERANCE)
    ]
    if len(vertical_indices) < 2:
        return False

    for left_pos in range(len(vertical_indices)):
        left_index = vertical_indices[left_pos]
        left_stats = chain_stats[left_index]
        for right_index in vertical_indices[left_pos + 1 :]:
            right_stats = chain_stats[right_index]
            overlap_ratio = _compute_z_overlap_ratio(left_stats, right_stats)
            if overlap_ratio < PROFILE_Z_OVERLAP_RATIO:
                continue

            mean_x_gap = abs(left_stats.mean_x - right_stats.mean_x)
            min_required_gap = max(
                1.0,
                max(left_stats.mean_x, right_stats.mean_x) * INNER_PROFILE_MEAN_X_GAP_RATIO,
            )
            if mean_x_gap >= min_required_gap:
                return True

    return False


def _entry_has_tall_vertical(
    source_indices: list[int],
    chain_stats: list[ProfileChainStats],
    chain_types: list[str],
    reference_z_span: float,
) -> bool:
    """Return whether one merge entry already contains a wall-like chain."""

    min_vertical_span = max(reference_z_span * 0.55, DEDUPLICATION_TOLERANCE)
    return any(
        chain_types[index] == "vertical_like" and chain_stats[index].z_span >= min_vertical_span
        for index in source_indices
    )


def _deduplicate_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Remove duplicate or near-duplicate profile points."""

    deduplicated: list[tuple[float, float]] = []
    for point in points:
        if not deduplicated:
            deduplicated.append(point)
            continue

        last_x, last_z = deduplicated[-1]
        if abs(point[0] - last_x) <= DEDUPLICATION_TOLERANCE and abs(point[1] - last_z) <= DEDUPLICATION_TOLERANCE:
            continue
        deduplicated.append(point)

    return deduplicated


def _point_distance(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    """Return the Euclidean distance between two 2D points."""

    dx = point_a[0] - point_b[0]
    dz = point_a[1] - point_b[1]
    return (dx * dx + dz * dz) ** 0.5


def _resample_profile_points(
    points: list[tuple[float, float]],
    num_samples: int,
) -> list[tuple[float, float]]:
    """Resample profile points along arc length for stable path-planning input."""

    if len(points) <= num_samples:
        return points

    arc_lengths = compute_arc_length(points)
    total_arc_length = arc_lengths[-1]
    sample_positions = [total_arc_length * index / (num_samples - 1) for index in range(num_samples)]
    return [interpolate_point(points, arc_lengths, target_s) for target_s in sample_positions]
