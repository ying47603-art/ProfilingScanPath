# OCP Integration Plan

## Current Environment

- Project root: `D:\00 Project\pythonProject\ProfilingScanPath`
- Required interpreter: `C:\ProgramData\Anaconda3\envs\profiling-ocp\python.exe`
- Do not use the `base` conda environment for OCP-related commands.

## Preferred Package

V1 prefers `cadquery-ocp-novtk` because it provides the `OCP` modules without pulling in the VTK GUI stack.

Recommended install/check command in the target environment:

```powershell
& 'C:\ProgramData\Anaconda3\envs\profiling-ocp\python.exe' -m pip install cadquery-ocp-novtk
```

Note:
- On Windows, the interpreter path contains spaces, so PowerShell should use `& '...'`.
- In the current environment check, `import OCP` already succeeds.

## What We Verified First

1. `import OCP` works in `profiling-ocp`
2. Minimal STEP read works through OCP

Scripts for this stage:

- `scripts/test_ocp_import.py`
- `scripts/test_ocp_step_read.py`

## Why We Are Not Replacing Core Modules Yet

The repository currently has a fallback STEP/profile chain that parses a very small STEP subset and feeds the path planner.

That fallback remains useful because:

- it keeps the existing tests green
- it provides a non-OCP fallback path
- the current sample fallback STEP fixture is not a full OCP BRep solid

## Replacement Plan

### Step 1

Keep the existing fallback implementation unchanged and add OCP smoke tests.

### Step 2

Update `core/step_loader.py` to:

- try OCP-based STEP loading first
- fall back to the lightweight parser if OCP is unavailable or the file is not a full BRep shape

### Step 3

Update `core/model_normalizer.py` to:

- use OCP shape locations/transforms when a real shape is available
- keep the current fallback normalization for lightweight parsed models

### Step 4

Update `core/profile_extractor.py` to:

- use OCP for `Y=0` plane sectioning on real shapes
- keep the existing point-based fallback extractor

### Step 5

Add a real OCP-generated STEP fixture and tests for:

- OCP STEP load
- section extraction
- `profile_points -> generate_scan_path`

## Known Risks

- The current fallback fixture `tests/fixtures/sample_revolved_profile.step` is readable by the lightweight parser, but it does not transfer into a non-null OCP shape.
- OCP APIs on Windows are usually stable, but PowerShell path quoting must be handled carefully because the interpreter path includes spaces.
- Full axis recognition and robust section cleanup should be deferred until after the smoke stage is stable.
