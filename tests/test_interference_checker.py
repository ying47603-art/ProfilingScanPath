"""Tests for the adjacent-layer transition interference checker."""

from __future__ import annotations

import pyvista as pv

from core.interference_checker import check_adjacent_layer_interference
from data.models import PathPoint, ScanPath


def test_adjacent_layer_interference_reports_non_colliding_pair() -> None:
    """A far-away transition should report one checked pair and no collision."""

    scan_path = ScanPath(
        points=[
            PathPoint(0, 0.0, 10.0, 0.0, 25.0, 0.0, 0.0, 90.0),
            PathPoint(1, 10.0, 10.0, 10.0, 25.0, 0.0, 10.0, 90.0),
        ]
    )
    surface_mesh = pv.Cylinder(
        center=(0.0, 0.0, 10.0),
        direction=(0.0, 0.0, 1.0),
        radius=20.0,
        height=20.0,
        resolution=48,
        capping=False,
    ).triangulate()

    result = check_adjacent_layer_interference(
        scan_path,
        surface_meshes=[surface_mesh],
        probe_diameter=4.0,
        probe_length=12.0,
        interpolation_samples=8,
    )

    assert result.checked_pairs == 1
    assert result.collided_pairs == 0
    assert not result.pair_results[0].collided


def test_adjacent_layer_interference_reports_colliding_pair() -> None:
    """A transition that intersects the active cylindrical surface should be flagged."""

    scan_path = ScanPath(
        points=[
            PathPoint(0, 0.0, 10.0, 0.0, 12.0, 0.0, 0.0, 90.0),
            PathPoint(1, 10.0, 10.0, 10.0, 12.0, 0.0, 10.0, 90.0),
        ]
    )
    surface_mesh = pv.Cylinder(
        center=(0.0, 0.0, 10.0),
        direction=(0.0, 0.0, 1.0),
        radius=20.0,
        height=20.0,
        resolution=48,
        capping=False,
    ).triangulate()

    result = check_adjacent_layer_interference(
        scan_path,
        surface_meshes=[surface_mesh],
        probe_diameter=6.0,
        probe_length=12.0,
        interpolation_samples=8,
    )

    assert result.checked_pairs == 1
    assert result.collided_pairs == 1
    assert result.pair_results[0].collided
    assert result.pair_results[0].collision_sample is not None
