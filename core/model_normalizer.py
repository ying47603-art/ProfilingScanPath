"""Model normalization for simple revolved STEP models in V1."""

from __future__ import annotations

import math
from typing import Optional

from data.models import NormalizedStepModel, StepAxisPlacement, StepModel


STANDARDIZATION_ERROR = "STEP模型标准化失败"
AXIS_ALIGNMENT_TOLERANCE_DEG = 15.0
Y_ALIGNMENT_TOLERANCE = 1e-3


def normalize_revolved_model(model: StepModel) -> NormalizedStepModel:
    """Normalize a simple revolved model into the V1 workpiece coordinate system."""

    if model.ocp_shape is not None:
        return _normalize_ocp_model(model)
    return _normalize_fallback_model(model)


def _normalize_ocp_model(model: StepModel) -> NormalizedStepModel:
    """Normalize an OCP shape by detecting and aligning its main revolution axis."""

    try:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Trsf, gp_Vec
    except Exception as exc:
        raise ValueError(STANDARDIZATION_ERROR) from exc

    shape = model.ocp_shape
    if shape is None or shape.IsNull():
        raise ValueError(STANDARDIZATION_ERROR)

    axis_origin, axis_direction = _detect_primary_ocp_axis(shape)
    rotated_shape = _rotate_shape_axis_to_z(shape, axis_direction)

    rotated_axis_origin = _rotate_point_to_z(axis_origin, axis_direction)
    bounds = _get_shape_bounds(rotated_shape)
    min_z = bounds[2]
    axis_center = _estimate_axis_center_from_main_section(rotated_shape, min_z=min_z, max_z=bounds[5])
    center_x, center_y = axis_center

    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(-center_x, -center_y, -min_z))
    transformed_shape = BRepBuilderAPI_Transform(rotated_shape, transform, True).Shape()

    transformed_bounds = _get_shape_bounds(transformed_shape)
    if transformed_bounds[2] < -1e-6:
        raise ValueError(STANDARDIZATION_ERROR)

    return NormalizedStepModel(
        source_file=model.file_path,
        points_3d=[],
        axis_origin=(0.0, 0.0, 0.0),
        axis_direction=(0.0, 0.0, 1.0),
        ocp_shape=transformed_shape,
    )


def _detect_primary_ocp_axis(shape: object) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Detect the main revolution axis from cylinder/cone faces."""

    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
    except Exception as exc:
        raise ValueError(STANDARDIZATION_ERROR) from exc

    axis_candidates: list[tuple[tuple[float, float, float], tuple[float, float, float], float]] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        surface = BRepAdaptor_Surface(face)
        surface_type = surface.GetType()

        if surface_type == GeomAbs_Cylinder:
            cylinder = surface.Cylinder()
            direction = cylinder.Axis().Direction()
            location = cylinder.Location()
            axis_candidates.append(
                (
                    (location.X(), location.Y(), location.Z()),
                    _normalize_vector((direction.X(), direction.Y(), direction.Z())),
                    1.0,
                )
            )
        elif surface_type == GeomAbs_Cone:
            cone = surface.Cone()
            direction = cone.Axis().Direction()
            location = cone.Location()
            axis_candidates.append(
                (
                    (location.X(), location.Y(), location.Z()),
                    _normalize_vector((direction.X(), direction.Y(), direction.Z())),
                    0.8,
                )
            )

        explorer.Next()

    if not axis_candidates:
        raise ValueError(STANDARDIZATION_ERROR)

    cardinal_axes = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )

    best_origin: Optional[tuple[float, float, float]] = None
    best_direction: Optional[tuple[float, float, float]] = None
    best_score = -1.0

    for origin, direction, weight in axis_candidates:
        alignment = max(abs(_dot(direction, axis)) for axis in cardinal_axes)
        score = alignment * weight
        if score > best_score:
            best_score = score
            best_origin = origin
            best_direction = direction

    if best_origin is None or best_direction is None:
        raise ValueError(STANDARDIZATION_ERROR)

    closest_alignment = max(abs(_dot(best_direction, axis)) for axis in cardinal_axes)
    if closest_alignment < math.cos(math.radians(AXIS_ALIGNMENT_TOLERANCE_DEG)):
        raise ValueError(STANDARDIZATION_ERROR)

    return best_origin, best_direction


def _rotate_shape_axis_to_z(shape: object, axis_direction: tuple[float, float, float]) -> object:
    """Rotate the detected main axis so it aligns with global +Z."""

    try:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf
    except Exception as exc:
        raise ValueError(STANDARDIZATION_ERROR) from exc

    rotation_axis, rotation_angle = _compute_rotation_to_z(axis_direction)
    if math.isclose(rotation_angle, 0.0, abs_tol=1e-12):
        return shape

    transform = gp_Trsf()
    transform.SetRotation(
        gp_Ax1(
            gp_Pnt(0.0, 0.0, 0.0),
            gp_Dir(rotation_axis[0], rotation_axis[1], rotation_axis[2]),
        ),
        rotation_angle,
    )
    return BRepBuilderAPI_Transform(shape, transform, True).Shape()


def _rotate_point_to_z(
    point: tuple[float, float, float],
    axis_direction: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Rotate a point with the same transform used to align the axis to +Z."""

    rotation_axis, rotation_angle = _compute_rotation_to_z(axis_direction)
    if math.isclose(rotation_angle, 0.0, abs_tol=1e-12):
        return point

    return _rotate_vector(point, rotation_axis, rotation_angle)


def _compute_rotation_to_z(axis_direction: tuple[float, float, float]) -> tuple[tuple[float, float, float], float]:
    """Compute the axis-angle rotation that maps the direction to global +Z."""

    target = (0.0, 0.0, 1.0)
    direction = _normalize_vector(axis_direction)
    dot_value = max(-1.0, min(1.0, _dot(direction, target)))

    if math.isclose(dot_value, 1.0, abs_tol=1e-12):
        return (1.0, 0.0, 0.0), 0.0

    if math.isclose(dot_value, -1.0, abs_tol=1e-12):
        # Pick a stable perpendicular axis.
        if abs(direction[0]) < 0.9:
            return _normalize_vector(_cross(direction, (1.0, 0.0, 0.0))), math.pi
        return _normalize_vector(_cross(direction, (0.0, 1.0, 0.0))), math.pi

    rotation_axis = _normalize_vector(_cross(direction, target))
    rotation_angle = math.acos(dot_value)
    return rotation_axis, rotation_angle


def _rotate_vector(
    vector: tuple[float, float, float],
    axis: tuple[float, float, float],
    angle: float,
) -> tuple[float, float, float]:
    """Rotate a 3D vector around an axis using Rodrigues' formula."""

    kx, ky, kz = _normalize_vector(axis)
    vx, vy, vz = vector
    cos_theta = math.cos(angle)
    sin_theta = math.sin(angle)

    cross_x = ky * vz - kz * vy
    cross_y = kz * vx - kx * vz
    cross_z = kx * vy - ky * vx
    dot_value = kx * vx + ky * vy + kz * vz

    return (
        vx * cos_theta + cross_x * sin_theta + kx * dot_value * (1.0 - cos_theta),
        vy * cos_theta + cross_y * sin_theta + ky * dot_value * (1.0 - cos_theta),
        vz * cos_theta + cross_z * sin_theta + kz * dot_value * (1.0 - cos_theta),
    )


def _estimate_axis_center_from_main_section(
    shape: object,
    min_z: float,
    max_z: float,
) -> tuple[float, float]:
    """Estimate the revolution axis center from one horizontal section."""

    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt
    except Exception as exc:
        raise ValueError(STANDARDIZATION_ERROR) from exc

    target_z = min_z + 0.5 * (max_z - min_z)
    section_plane = gp_Pln(gp_Ax3(gp_Pnt(0.0, 0.0, target_z), gp_Dir(0.0, 0.0, 1.0)))
    section = BRepAlgoAPI_Section(shape, section_plane, False)
    section.Build()
    if not section.IsDone():
        raise ValueError(STANDARDIZATION_ERROR)

    explorer = TopExp_Explorer(section.Shape(), TopAbs_EDGE)
    sampled_points: list[tuple[float, float]] = []
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        curve = BRepAdaptor_Curve(edge)
        first = curve.FirstParameter()
        last = curve.LastParameter()
        for index in range(25):
            parameter = first + (last - first) * index / 24.0
            point = curve.Value(parameter)
            sampled_points.append((point.X(), point.Y()))
        explorer.Next()

    if len(sampled_points) < 4:
        raise ValueError(STANDARDIZATION_ERROR)

    x_values = [point[0] for point in sampled_points]
    y_values = [point[1] for point in sampled_points]
    center_x = 0.5 * (min(x_values) + max(x_values))
    center_y = 0.5 * (min(y_values) + max(y_values))
    return center_x, center_y


def _normalize_fallback_model(model: StepModel) -> NormalizedStepModel:
    """Normalize the fallback text-parsed model representation."""

    axis = _select_primary_axis(model)
    direction = _normalize_vector(axis.direction)

    if abs(direction[0]) > math.sin(math.radians(AXIS_ALIGNMENT_TOLERANCE_DEG)):
        raise ValueError(STANDARDIZATION_ERROR)
    if abs(direction[1]) > math.sin(math.radians(AXIS_ALIGNMENT_TOLERANCE_DEG)):
        raise ValueError(STANDARDIZATION_ERROR)

    normalized_points: list[tuple[float, float, float]] = []
    origin_x, origin_y, _ = axis.origin

    for point_x, point_y, point_z in model.cartesian_points:
        x = point_x - origin_x
        y = point_y - origin_y
        z = point_z

        if direction[2] < 0.0:
            z = -z

        normalized_points.append((x, y, z))

    min_z = min(point[2] for point in normalized_points)
    shifted_points = [(point_x, point_y, point_z - min_z) for point_x, point_y, point_z in normalized_points]

    if _mean_x(shifted_points) < 0.0:
        shifted_points = [(-point_x, point_y, point_z) for point_x, point_y, point_z in shifted_points]

    if not any(abs(point_y) <= Y_ALIGNMENT_TOLERANCE for _, point_y, _ in shifted_points):
        raise ValueError(STANDARDIZATION_ERROR)

    return NormalizedStepModel(
        source_file=model.file_path,
        points_3d=shifted_points,
        axis_origin=(0.0, 0.0, 0.0),
        axis_direction=(0.0, 0.0, 1.0),
        ocp_shape=None,
    )


def _get_shape_bounds(shape: object) -> tuple[float, float, float, float, float, float]:
    """Return the bounding-box extrema for an OCP shape."""

    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box

    bbox = Bnd_Box()
    BRepBndLib.Add_s(shape, bbox)
    return bbox.Get()


def _select_primary_axis(model: StepModel) -> StepAxisPlacement:
    """Select the primary revolution axis for a simple V1 STEP model."""

    if not model.axis_placements:
        raise ValueError(STANDARDIZATION_ERROR)

    best_axis: Optional[StepAxisPlacement] = None
    best_score: Optional[float] = None
    for axis in model.axis_placements:
        direction = _normalize_vector(axis.direction)
        score = abs(direction[2])
        if best_score is None or score > best_score:
            best_axis = axis
            best_score = score

    if best_axis is None:
        raise ValueError(STANDARDIZATION_ERROR)

    return best_axis


def _normalize_vector(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    """Return a unit-length copy of a 3D vector."""

    x, y, z = vector
    length = math.sqrt(x * x + y * y + z * z)
    if math.isclose(length, 0.0):
        raise ValueError(STANDARDIZATION_ERROR)
    return x / length, y / length, z / length


def _dot(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    """Return the dot product of two 3D vectors."""

    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _cross(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Return the cross product of two 3D vectors."""

    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _mean_x(points: list[tuple[float, float, float]]) -> float:
    """Estimate whether the dominant outer profile lies on the positive X side."""

    if not points:
        raise ValueError(STANDARDIZATION_ERROR)
    return sum(point_x for point_x, _, _ in points) / len(points)
