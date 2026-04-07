"""Debug helper for the V1 STEP profile-extraction chain."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.profile_extractor import load_and_extract_profile


def main() -> int:
    """Load a STEP file, extract profile points, and print summary information."""

    if len(sys.argv) < 2:
        print("Usage: py -3.9 scripts\\debug_step_profile.py <step-file> [output-csv]")
        return 1

    step_file = Path(sys.argv[1])
    output_csv = Path(sys.argv[2]) if len(sys.argv) >= 3 else None

    profile_points = load_and_extract_profile(step_file, num_samples=200)
    x_values = [point[0] for point in profile_points]
    z_values = [point[1] for point in profile_points]

    print(f"point_count={len(profile_points)}")
    print(f"x_range=({min(x_values):.6f}, {max(x_values):.6f})")
    print(f"z_range=({min(z_values):.6f}, {max(z_values):.6f})")
    print("first_10_points=")
    for point in profile_points[:10]:
        print(f"  ({point[0]:.6f}, {point[1]:.6f})")
    print("last_10_points=")
    for point in profile_points[-10:]:
        print(f"  ({point[0]:.6f}, {point[1]:.6f})")

    if output_csv is not None:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["x", "z"])
            writer.writerows(profile_points)
        print(f"csv_written={output_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
