"""V1 STEP file loader.

The loader now prefers OCP-based STEP shape loading when available and falls
back to the conservative text parser used by the V1 bootstrap implementation.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Optional, Union

from data.models import StepAxisPlacement, StepModel


ENTITY_PATTERN = re.compile(r"#(?P<id>\d+)\s*=\s*(?P<body>.*?);", re.DOTALL)
FLOAT_PATTERN = r"[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?"


def load_step_model(file_path: Union[str, Path]) -> StepModel:
    """Load a STEP file, preferring OCP shape loading when available."""

    step_path = Path(file_path)
    if step_path.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("Only STEP files are supported")
    if not step_path.exists():
        raise FileNotFoundError(f"STEP file not found: {step_path}")

    raw_text = _read_step_text(step_path)
    if "ISO-10303-21" not in raw_text or "DATA;" not in raw_text:
        raise ValueError(f"Failed to read STEP file: {step_path}")

    ocp_shape = _try_load_ocp_shape(step_path)
    if ocp_shape is not None:
        cartesian_points = _extract_cartesian_points_from_text(raw_text)
        axis_placements = _extract_axis_placements(_parse_entity_map(raw_text))
        return StepModel(
            file_path=step_path,
            cartesian_points=cartesian_points,
            axis_placements=axis_placements,
            raw_text=raw_text,
            loader_backend="ocp",
            ocp_shape=ocp_shape,
        )

    return _load_step_model_fallback(step_path, raw_text)


def _load_step_model_fallback(step_path: Path, raw_text: str) -> StepModel:
    """Load a STEP file through the lightweight text-based fallback parser."""

    entity_map = _parse_entity_map(raw_text)
    cartesian_points = _extract_cartesian_points(entity_map)
    axis_placements = _extract_axis_placements(entity_map)

    if not cartesian_points:
        raise ValueError(f"Failed to read STEP file: {step_path}")

    return StepModel(
        file_path=step_path,
        cartesian_points=cartesian_points,
        axis_placements=axis_placements,
        raw_text=raw_text,
        loader_backend="fallback",
        ocp_shape=None,
    )


def _read_step_text(step_path: Path) -> str:
    """Read STEP text using a tolerant codec fallback chain.

    Many STEP files are ASCII-compatible but may contain non-UTF-8 bytes in
    header metadata. V1 prefers a practical decoding chain that keeps the
    loader robust on Windows-generated files.
    """

    raw_bytes = step_path.read_bytes()
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Failed to read STEP file: {step_path}")


def _try_load_ocp_shape(step_path: Path) -> Optional[Any]:
    """Try loading a STEP shape through OCP and return it when successful."""

    try:
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_Reader
    except Exception:
        return None

    reader = STEPControl_Reader()
    read_status = reader.ReadFile(str(step_path))
    if read_status != IFSelect_RetDone:
        return None

    transfer_count = reader.TransferRoots()
    if transfer_count <= 0:
        return None

    shape = reader.OneShape()
    if shape.IsNull():
        return None

    return shape


def _extract_cartesian_points_from_text(raw_text: str) -> list[tuple[float, float, float]]:
    """Extract cartesian points from raw STEP text without changing backend choice."""

    return _extract_cartesian_points(_parse_entity_map(raw_text))


def _parse_entity_map(raw_text: str) -> dict[int, str]:
    """Parse top-level STEP entities into an ID-to-body map."""

    return {int(match.group("id")): match.group("body").strip() for match in ENTITY_PATTERN.finditer(raw_text)}


def _extract_cartesian_points(entity_map: dict[int, str]) -> list[tuple[float, float, float]]:
    """Extract all CARTESIAN_POINT coordinates from the STEP entity map."""

    points: list[tuple[float, float, float]] = []
    point_pattern = re.compile(rf"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*({FLOAT_PATTERN})\s*,\s*({FLOAT_PATTERN})\s*,\s*({FLOAT_PATTERN})\s*\)\s*\)")

    for body in entity_map.values():
        match = point_pattern.search(body)
        if match:
            points.append(tuple(float(group) for group in match.groups()))

    return points


def _extract_axis_placements(entity_map: dict[int, str]) -> list[StepAxisPlacement]:
    """Extract all AXIS2_PLACEMENT_3D definitions from the STEP entity map."""

    placements: list[StepAxisPlacement] = []
    axis_pattern = re.compile(
        r"AXIS2_PLACEMENT_3D\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*,\s*#(\d+)\s*,\s*#(\d+)\s*\)"
    )
    direction_pattern = re.compile(rf"DIRECTION\s*\(\s*'[^']*'\s*,\s*\(\s*({FLOAT_PATTERN})\s*,\s*({FLOAT_PATTERN})\s*,\s*({FLOAT_PATTERN})\s*\)\s*\)")
    point_pattern = re.compile(rf"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*({FLOAT_PATTERN})\s*,\s*({FLOAT_PATTERN})\s*,\s*({FLOAT_PATTERN})\s*\)\s*\)")

    for body in entity_map.values():
        axis_match = axis_pattern.search(body)
        if not axis_match:
            continue

        origin_id, direction_id, ref_direction_id = (int(value) for value in axis_match.groups())
        origin_body = entity_map.get(origin_id, "")
        direction_body = entity_map.get(direction_id, "")
        ref_direction_body = entity_map.get(ref_direction_id, "")

        origin_match = point_pattern.search(origin_body)
        direction_match = direction_pattern.search(direction_body)
        ref_direction_match = direction_pattern.search(ref_direction_body)

        if not origin_match or not direction_match:
            continue

        placements.append(
            StepAxisPlacement(
                origin=tuple(float(group) for group in origin_match.groups()),
                direction=tuple(float(group) for group in direction_match.groups()),
                ref_direction=tuple(float(group) for group in ref_direction_match.groups()) if ref_direction_match else None,
            )
        )

    return placements
