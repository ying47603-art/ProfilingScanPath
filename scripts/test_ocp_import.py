"""Minimal OCP import smoke test.

Always run this script with the profiling-ocp interpreter:
    & 'C:\\ProgramData\\Anaconda3\\envs\\profiling-ocp\\python.exe' scripts\\test_ocp_import.py
"""

from __future__ import annotations

import sys


def main() -> int:
    """Import the core OCP modules required for STEP work."""

    print(f"python_executable={sys.executable}")
    print(f"python_version={sys.version}")

    try:
        import OCP  # noqa: F401
        from OCP.IFSelect import IFSelect_RetDone  # noqa: F401
        from OCP.STEPControl import STEPControl_Reader, STEPControl_Writer  # noqa: F401
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder  # noqa: F401
    except Exception as exc:  # pragma: no cover - smoke path
        print(f"ocp_import_ok=False error={exc}")
        return 1

    print("ocp_import_ok=True")
    print("imported_modules=OCP,STEPControl,IFSelect,BRepPrimAPI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
