"""Generate stable OCP-backed STEP fixtures for tests.

Always run this script with the profiling-ocp interpreter:
    & 'C:\\ProgramData\\Anaconda3\\envs\\profiling-ocp\\python.exe' scripts\\generate_ocp_fixtures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT_DIR / "tests" / "fixtures"


def main() -> int:
    """Generate the OCP STEP fixtures used by loader smoke tests."""

    try:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeRevol
        from OCP.GC import GC_MakeArcOfCircle
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
        from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt
    except Exception as exc:
        print(f"fixture_generation_ok=False error={exc}")
        return 1

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    cylinder_file = FIXTURE_DIR / "ocp_cylinder.step"
    fillet_file = FIXTURE_DIR / "ocp_fillet.step"

    cylinder_shape = BRepPrimAPI_MakeCylinder(100.0, 100.0).Shape()
    fillet_shape = _build_fillet_revolved_shape(
        make_edge=BRepBuilderAPI_MakeEdge,
        make_wire=BRepBuilderAPI_MakeWire,
        make_face=BRepBuilderAPI_MakeFace,
        make_revol=BRepPrimAPI_MakeRevol,
        make_arc=GC_MakeArcOfCircle,
        gp_ax1=gp_Ax1,
        gp_dir=gp_Dir,
        gp_point=gp_Pnt,
    )

    if not _write_step_shape(cylinder_shape, cylinder_file, STEPControl_Writer, STEPControl_AsIs, IFSelect_RetDone):
        print(f"fixture_generation_ok=False file={cylinder_file}")
        return 2
    if not _write_step_shape(fillet_shape, fillet_file, STEPControl_Writer, STEPControl_AsIs, IFSelect_RetDone):
        print(f"fixture_generation_ok=False file={fillet_file}")
        return 2

    print(f"fixture_generation_ok=True file={cylinder_file}")
    print(f"fixture_generation_ok=True file={fillet_file}")
    print(f"python_executable={sys.executable}")
    return 0


def _build_fillet_revolved_shape(
    make_edge,
    make_wire,
    make_face,
    make_revol,
    make_arc,
    gp_ax1,
    gp_dir,
    gp_point,
):
    """Build a cylinder-plus-fillet revolved solid for section-extraction tests."""

    p0 = gp_point(0.0, 0.0, 0.0)
    p1 = gp_point(100.0, 0.0, 0.0)
    p2 = gp_point(100.0, 0.0, 60.0)
    p3 = gp_point(80.0, 0.0, 80.0)
    p4 = gp_point(0.0, 0.0, 80.0)

    edge_bottom = make_edge(p0, p1).Edge()
    edge_cylinder = make_edge(p1, p2).Edge()
    edge_arc = make_edge(make_arc(p2, gp_point(94.1421356237, 0.0, 74.1421356237), p3).Value()).Edge()
    edge_top = make_edge(p3, p4).Edge()
    edge_axis = make_edge(p4, p0).Edge()

    wire_builder = make_wire()
    for edge in [edge_bottom, edge_cylinder, edge_arc, edge_top, edge_axis]:
        wire_builder.Add(edge)
    profile_wire = wire_builder.Wire()
    profile_face = make_face(profile_wire).Face()
    return make_revol(profile_face, gp_ax1(gp_point(0.0, 0.0, 0.0), gp_dir(0.0, 0.0, 1.0))).Shape()


def _write_step_shape(shape, file_path: Path, writer_cls, transfer_mode, success_code) -> bool:
    """Write a shape to STEP and report whether the write succeeded."""

    writer = writer_cls()
    writer.Transfer(shape, transfer_mode)
    return writer.Write(str(file_path)) == success_code


if __name__ == "__main__":
    raise SystemExit(main())
