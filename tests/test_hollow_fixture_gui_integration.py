"""GUI/core integration test for a real hollow STEP fixture."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget
import pyvista as pv

from data.models import ProfileSegment
from gui.controller import GuiController
import gui.main_window as main_window_module
from gui.main_window import MainWindow
from gui.widgets.profile_preview_3d_widget import ProfilePreview3DWidget


FIXTURE_FILE = Path(__file__).resolve().parent / "fixtures" / "ocp_hollow_shell.step"


def _ensure_app() -> QApplication:
    """Return a running QApplication for the GUI integration test."""

    app = QApplication.instance()
    if app is not None:
        return app
    return QApplication([])


class DummyPreview3DWidget(QWidget):
    """Lightweight stand-in that avoids creating a real QtInteractor in tests."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._profile_points = []
        self._profile_groups = []
        self._reference_profile_points = []
        self._scan_path = None
        self._interference_segments = []
        self._interference_points = []
        self._probe_diameter = 10.0
        self._probe_length = 20.0
        self._revolve_resolution = 36

    def set_profile_points(self, profile_points, **_kwargs) -> None:
        self._profile_points = list(profile_points)
        self._profile_groups = [list(self._profile_points)] if len(self._profile_points) >= 2 else []

    def set_profile_groups(self, profile_groups, **_kwargs) -> None:
        self._profile_groups = [list(group) for group in profile_groups]
        self._profile_points = [point for group in self._profile_groups for point in group]

    def set_reference_profile_points(self, profile_points, **_kwargs) -> None:
        self._reference_profile_points = list(profile_points)

    def set_profile_segments(self, *, enabled_segments, disabled_segments, **_kwargs) -> None:
        self._enabled_profile_segments = list(enabled_segments)
        self._disabled_profile_segments = list(disabled_segments)

    def set_scan_path(self, scan_path, **_kwargs) -> None:
        self._scan_path = scan_path

    def clear_preview(self) -> None:
        self._profile_points = []
        self._reference_profile_points = []
        self._scan_path = None
        self._interference_segments = []
        self._interference_points = []

    def set_display_options(self, **_kwargs) -> None:
        return None

    def set_render_mode(self, *_args, **_kwargs) -> None:
        return None

    def set_surface_options(self, *, revolve_resolution=None, **_kwargs) -> None:
        if revolve_resolution is not None:
            self._revolve_resolution = int(revolve_resolution)

    def set_camera_options(self, **_kwargs) -> None:
        return None

    def set_probe_pose_options(self, *, probe_diameter=None, probe_length=None, **_kwargs) -> None:
        if probe_diameter is not None:
            self._probe_diameter = float(probe_diameter)
        if probe_length is not None:
            self._probe_length = float(probe_length)

    def set_current_probe_index(self, *_args, **_kwargs) -> None:
        return None

    def clear_probe_pose(self, **_kwargs) -> None:
        return None

    def refresh_view(self) -> None:
        return None

    def reset_camera_view(self) -> None:
        return None

    def clear_interference_visuals(self, *, refresh: bool = True) -> None:
        self._interference_segments = []
        self._interference_points = []

    def set_interference_results(self, result) -> None:
        self._interference_segments = [
            (pair.start_center, pair.end_center, pair.collided)
            for pair in result.pair_results
        ]
        self._interference_points = [
            (
                pair.collision_sample.center_x,
                pair.collision_sample.center_y,
                pair.collision_sample.center_z,
            )
            for pair in result.pair_results
            if pair.collision_sample is not None
        ]

    def get_active_surface_meshes_for_analysis(self):
        return [
            pv.Cylinder(
                center=(0.0, 0.0, 50.0),
                direction=(0.0, 0.0, 1.0),
                radius=100.0,
                height=100.0,
                resolution=max(36, self._revolve_resolution),
                capping=False,
            ).triangulate()
        ]


def _patch_main_window_3d_widget(monkeypatch) -> None:
    """Replace the real 3D preview with a light test double."""

    monkeypatch.setattr(main_window_module, "ProfilePreview3DWidget", DummyPreview3DWidget)


def test_hollow_fixture_exposes_segment_first_profile_selection(monkeypatch) -> None:
    """The GUI should expose multiple selectable segments for a real hollow STEP fixture."""

    _patch_main_window_3d_widget(monkeypatch)

    app = _ensure_app()
    controller = GuiController()
    window = MainWindow(controller)

    window.ui.edtStepFilePath.setText(str(FIXTURE_FILE))
    window.ui.spnSamples.setValue(40)
    window._on_load_step()
    window._on_extract_profile()

    assert controller.get_profile_segments()
    assert len(controller.get_profile_segments()) >= 2
    assert window.ui.txtLog.toPlainText().find("[PROFILE] suggested_segment_order=") >= 0
    assert controller.active_profile_groups
    assert window._preview_widget is not None
    assert window._preview_widget_3d is not None
    assert window._preview_widget._profile_groups == controller.active_profile_groups
    assert window._preview_widget_3d._profile_groups == controller.active_profile_groups

    list_widget = window.ui.lstProfileSegments
    assert "[" in list_widget.item(0).text()
    list_widget.item(0).setCheckState(Qt.CheckState.Unchecked)

    assert any(not segment.is_enabled for segment in controller.get_profile_segments())
    assert controller.scan_path is None
    assert controller.active_profile_groups
    assert window._preview_widget._scan_path is None
    assert window._preview_widget_3d._scan_path is None
    assert window._preview_widget._profile_groups == controller.active_profile_groups
    assert window._preview_widget_3d._profile_groups == controller.active_profile_groups

    window._on_generate_path()

    assert controller.scan_path is not None
    assert controller.scan_path.points
    assert window._preview_widget._scan_path is controller.scan_path
    assert window._preview_widget_3d._scan_path is controller.scan_path


def test_surface_segments_ignore_horizontal_connectors(monkeypatch) -> None:
    """3D surface generation should only revolve active non-horizontal sidewall segments."""

    _ensure_app()
    widget = ProfilePreview3DWidget.__new__(ProfilePreview3DWidget)
    widget._enabled_profile_segments = []
    widget._profile_points = [
        (100.0, 0.0),
        (100.0, 50.0),
        (80.0, 50.0),
        (80.0, 100.0),
    ]

    assert widget._get_active_surface_segments() == [
        [(100.0, 0.0), (100.0, 50.0)],
        [(80.0, 50.0), (80.0, 100.0)],
    ]


def test_interference_check_updates_and_clears_3d_visual_state(monkeypatch) -> None:
    """Interference visuals should populate after checking and clear after profile changes."""

    _patch_main_window_3d_widget(monkeypatch)

    _ensure_app()
    controller = GuiController()
    window = MainWindow(controller)

    window.ui.edtStepFilePath.setText(str(FIXTURE_FILE))
    window.ui.spnSamples.setValue(40)
    window.ui.dsbLayerStep.setValue(25.0)
    window._on_load_step()
    window._on_extract_profile()
    window.ui.lstProfileSegments.item(1).setCheckState(Qt.CheckState.Unchecked)
    window._on_generate_path()
    window._on_interference_check()

    assert controller.interference_result is not None
    assert controller.interference_result.checked_pairs == len(controller.scan_path.points) - 1
    assert window._preview_widget_3d is not None
    assert len(window._preview_widget_3d._interference_segments) == controller.interference_result.checked_pairs

    window.ui.lstProfileSegments.item(0).setCheckState(Qt.CheckState.Unchecked)

    assert controller.interference_result is None
    assert window._preview_widget_3d._interference_segments == []
    assert window._preview_widget_3d._interference_points == []


def test_profile_segment_list_populates_and_rebuilds_active_profile(monkeypatch) -> None:
    """The segment list should drive active-profile rebuilding without auto-generating a path."""

    _patch_main_window_3d_widget(monkeypatch)

    _ensure_app()
    controller = GuiController()
    window = MainWindow(controller)

    window.ui.edtStepFilePath.setText(str(FIXTURE_FILE))
    window.ui.spnSamples.setValue(40)
    window._on_load_step()
    window._on_extract_profile()

    list_widget = window.ui.lstProfileSegments
    assert list_widget.count() >= 1
    assert all(list_widget.item(index).checkState() == Qt.CheckState.Checked for index in range(list_widget.count()))
    assert controller.active_profile_groups

    first_item = list_widget.item(0)
    first_item.setCheckState(Qt.CheckState.Unchecked)

    assert controller.scan_path is None
    assert not any(segment.is_enabled for segment in controller.get_profile_segments()[:1])
    assert controller.active_profile_groups

    window._on_segment_select_all()

    assert all(segment.is_enabled for segment in controller.get_profile_segments())


def test_auto_s_end_tracks_current_active_profile_groups(monkeypatch) -> None:
    """Auto s_end should follow the current active profile-group total arc length."""

    _patch_main_window_3d_widget(monkeypatch)

    _ensure_app()
    controller = GuiController()
    window = MainWindow(controller)

    window.ui.edtStepFilePath.setText(str(FIXTURE_FILE))
    window.ui.spnSamples.setValue(40)
    window.ui.chkAutoSEnd.setChecked(True)
    window._on_load_step()
    window._on_extract_profile()

    assert window.ui.dsbSStart.value() == 0.0
    assert window.ui.dsbSEnd.value() == controller.active_profile_total_length

    list_widget = window.ui.lstProfileSegments
    assert list_widget.count() >= 2
    list_widget.item(1).setCheckState(Qt.CheckState.Unchecked)

    assert window.ui.dsbSStart.value() == 0.0
    assert window.ui.dsbSEnd.value() == controller.active_profile_total_length
    assert "[PROFILE] auto arc-length sync enabled" in window.ui.txtLog.toPlainText()


def test_disconnected_order_splits_into_multiple_active_groups_without_hidden_connectors(monkeypatch) -> None:
    """Disconnected selected segments should remain valid as separate active profile groups."""

    _patch_main_window_3d_widget(monkeypatch)

    _ensure_app()
    controller = GuiController()
    window = MainWindow(controller)

    first_segment = ProfileSegment(0, "segment_0", [(100.0, 0.0), (100.0, 20.0)], 2, 100.0, 100.0, 0.0, 20.0, 20.0, "vertical_like", "outer", True)
    second_segment = ProfileSegment(1, "segment_1", [(140.0, 80.0), (140.0, 100.0)], 2, 140.0, 140.0, 80.0, 100.0, 20.0, "vertical_like", "inner", True)
    controller.set_profile_segments([first_segment, second_segment])
    window._populate_profile_segment_list()
    window._apply_profile_segment_selection()

    assert len(controller.active_profile_groups) == 2
    assert window._preview_widget._profile_groups == controller.active_profile_groups
    assert window._preview_widget_3d._profile_groups == controller.active_profile_groups
    assert window._preview_widget._enabled_profile_segments == []
