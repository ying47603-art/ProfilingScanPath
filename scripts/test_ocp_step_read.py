"""Minimal OCP STEP read smoke test.

Usage:
    & 'C:\\ProgramData\\Anaconda3\\envs\\profiling-ocp\\python.exe' scripts\\test_ocp_step_read.py
    & 'C:\\ProgramData\\Anaconda3\\envs\\profiling-ocp\\python.exe' scripts\\test_ocp_step_read.py path\\to\\file.step
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Optional


def main() -> int:
    """Create or read a STEP file and verify OCP can turn it into a shape."""

    try:
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
    except Exception as exc:  # pragma: no cover - smoke path
        print(f"ocp_available=False error={exc}")
        return 1

    step_file = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else _write_temp_cylinder_step()

    reader = STEPControl_Reader()
    read_status = reader.ReadFile(str(step_file))
    print(f"step_file={step_file}")
    print(f"read_status={int(read_status)}")
    print(f"read_ok={read_status == IFSelect_RetDone}")

    if read_status != IFSelect_RetDone:
        return 2

    root_count = reader.NbRootsForTransfer()
    transfer_count = reader.TransferRoots()
    shape = reader.OneShape()

    print(f"root_count={root_count}")
    print(f"transfer_count={transfer_count}")
    print(f"shape_is_null={shape.IsNull()}")

    if shape.IsNull():
        return 3

    print("step_read_ok=True")
    return 0


def _write_temp_cylinder_step() -> Path:
    """Create a temporary valid STEP cylinder fixture for OCP smoke testing."""

    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    temp_dir = Path(tempfile.gettempdir()) / "profiling_scan_path_ocp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    step_file = temp_dir / "ocp_temp_cylinder.step"

    shape = BRepPrimAPI_MakeCylinder(100.0, 100.0).Shape()
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    write_status = writer.Write(str(step_file))
    if write_status != IFSelect_RetDone:
        raise RuntimeError(f"Failed to write temporary STEP fixture: {step_file}")

    return step_file


if __name__ == "__main__":
    raise SystemExit(main())
