"""Profile extraction for normalized simple revolved STEP models."""

from __future__ import annotations

from pathlib import Path
from typing import Union

from core.model_normalizer import normalize_revolved_model
from core.path_planner import compute_arc_length, interpolate_point
from core.step_loader import load_step_model
from data.models import NormalizedStepModel


EXTRACTION_ERROR = "STEP模型标准化失败"
Y_SECTION_TOLERANCE = 1e-3
DEDUPLICATION_TOLERANCE = 1e-6
AXIS_CHAIN_TOLERANCE = 1.0
HORIZONTAL_CHAIN_RATIO = 0.25
CHAIN_MERGE_DISTANCE = 2.5


def extract_profile_points(
    model: NormalizedStepModel,
    num_samples: int = 200,
) -> list[tuple[float, float]]:
    """Extract ordered profile points on the Y=0 XZ section."""

    if num_samples < 2:
        raise ValueError("num_samples must be >= 2")

    if model.ocp_shape is not None:
        return _extract_profile_points_from_ocp_shape(model, num_samples)
    return _extract_profile_points_fallback(model, num_samples)


def load_and_extract_profile(
    file_path: Union[str, Path],
    num_samples: int = 200,
) -> list[tuple[float, float]]:
    """Load a STEP file, normalize it, and extract its profile points."""

    model = load_step_model(file_path)
    normalized_model = normalize_revolved_model(model)
    return extract_profile_points(normalized_model, num_samples=num_samples)


def _extract_profile_points_from_ocp_shape(
    model: NormalizedStepModel,
    num_samples: int,
) -> list[tuple[float, float]]:
    """Extract a stable outer profile from the normalized OCP shape."""

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

    candidate_chains = _filter_candidate_outer_chains(chains)
    if not candidate_chains:
        raise ValueError(EXTRACTION_ERROR)

    merged_chains = _merge_ordered_chains(candidate_chains)
    main_chain = _select_main_outer_chain(merged_chains)
    ordered_points = _order_profile_points(main_chain)
    deduplicated_points = _deduplicate_points(ordered_points)
    if len(deduplicated_points) < 2:
        raise ValueError(EXTRACTION_ERROR)

    return _resample_profile_points(deduplicated_points, num_samples=num_samples)


def _extract_profile_points_fallback(
    model: NormalizedStepModel,
    num_samples: int,
) -> list[tuple[float, float]]:
    """Extract ordered profile points from the fallback point-based model."""

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

    return _resample_profile_points(deduplicated_points, num_samples=num_samples)


def _filter_candidate_outer_chains(chains: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Filter section chains down to plausible outer-profile candidates.

    Rules:
    - reject chains near the axis (`x≈0`)
    - reject chains on the negative-x side
    - reject near-horizontal end-face chains
    """

    candidates: list[list[tuple[float, float]]] = []
    for chain in chains:
        x_values = [point[0] for point in chain]
        z_values = [point[1] for point in chain]
        x_span = max(x_values) - min(x_values)
        z_span = max(z_values) - min(z_values)
        avg_x = sum(x_values) / len(x_values)
        max_x = max(x_values)

        if max_x <= AXIS_CHAIN_TOLERANCE:
            continue
        if avg_x <= AXIS_CHAIN_TOLERANCE:
            continue
        if z_span <= max(DEDUPLICATION_TOLERANCE, x_span * HORIZONTAL_CHAIN_RATIO):
            continue

        candidates.append(chain)

    return candidates


def _merge_ordered_chains(chains: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Merge simple section chains by z order and endpoint proximity."""

    sorted_chains = sorted(chains, key=lambda chain: (chain[0][1], chain[-1][1]))
    merged: list[list[tuple[float, float]]] = []

    for chain in sorted_chains:
        current = list(chain)
        if not merged:
            merged.append(current)
            continue

        previous = merged[-1]
        if _point_distance(previous[-1], current[0]) <= CHAIN_MERGE_DISTANCE:
            merged[-1] = _deduplicate_points(previous + current)
        else:
            merged.append(current)

    return merged


def _select_main_outer_chain(chains: list[list[tuple[float, float]]]) -> list[tuple[float, float]]:
    """Select the main outer contour chain.

    Primary score: z coverage range.
    Secondary score: average x position, to prefer the outer contour over other
    positive-x chains.
    """

    if not chains:
        raise ValueError(EXTRACTION_ERROR)

    def score(chain: list[tuple[float, float]]) -> tuple[float, float]:
        z_values = [point[1] for point in chain]
        x_values = [point[0] for point in chain]
        return max(z_values) - min(z_values), sum(x_values) / len(x_values)

    return max(chains, key=score)


def _order_profile_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Order profile points from bottom to top and keep the outer contour."""

    points_by_z: dict[float, float] = {}
    for point_x, point_z in points:
        z_key = round(point_z, 6)
        current_x = points_by_z.get(z_key)
        if current_x is None or point_x > current_x:
            points_by_z[z_key] = point_x

    return [(point_x, z_key) for z_key, point_x in sorted(points_by_z.items(), key=lambda item: item[0])]


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
