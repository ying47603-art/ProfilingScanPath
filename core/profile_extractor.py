"""Profile extraction for normalized simple revolved STEP models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

from core.model_normalizer import normalize_revolved_model
from core.path_planner import compute_arc_length, interpolate_point
from core.step_loader import load_step_model
from data.models import ExtractedProfiles, NormalizedStepModel


EXTRACTION_ERROR = "STEP model normalization failed"
Y_SECTION_TOLERANCE = 1e-3
DEDUPLICATION_TOLERANCE = 1e-6
AXIS_CHAIN_TOLERANCE = 1.0
CHAIN_MERGE_DISTANCE = 2.5
PROFILE_COMPLETENESS_RATIO = 0.6
PROFILE_Z_OVERLAP_RATIO = 0.75
INNER_PROFILE_MEAN_X_GAP_RATIO = 0.08
MIN_PROFILE_CHAIN_POINTS = 6


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
    """Extract ordered outer profile points on the Y=0 XZ section."""

    return extract_selectable_profiles(model, num_samples=num_samples).outer_profile_points


def extract_selectable_profiles(
    model: NormalizedStepModel,
    num_samples: int = 200,
) -> ExtractedProfiles:
    """Extract selectable outer/inner profiles from one normalized workpiece."""

    if num_samples < 2:
        raise ValueError("num_samples must be >= 2")

    if model.ocp_shape is not None:
        return _extract_selectable_profiles_from_ocp_shape(model, num_samples)
    return _extract_selectable_profiles_fallback(model, num_samples)


def load_and_extract_profile(
    file_path: Union[str, Path],
    num_samples: int = 200,
) -> list[tuple[float, float]]:
    """Load a STEP file, normalize it, and extract its outer profile points."""

    model = load_step_model(file_path)
    normalized_model = normalize_revolved_model(model)
    return extract_profile_points(normalized_model, num_samples=num_samples)


def _extract_selectable_profiles_from_ocp_shape(
    model: NormalizedStepModel,
    num_samples: int,
) -> ExtractedProfiles:
    """Extract selectable outer/inner profiles from the normalized OCP shape."""

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

    outer_chain, inner_chain = _select_outer_and_inner_chains(normalized_chains)
    return ExtractedProfiles(
        outer_profile_points=_resample_profile_points(outer_chain, num_samples=num_samples),
        inner_profile_points=(
            _resample_profile_points(inner_chain, num_samples=num_samples)
            if inner_chain is not None
            else None
        ),
    )


def _extract_selectable_profiles_fallback(
    model: NormalizedStepModel,
    num_samples: int,
) -> ExtractedProfiles:
    """Extract selectable profiles from the fallback point-based model."""

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

    return ExtractedProfiles(
        outer_profile_points=_resample_profile_points(deduplicated_points, num_samples=num_samples),
        inner_profile_points=None,
    )


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
