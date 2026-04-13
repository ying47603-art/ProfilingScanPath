"""GUI/core integration test for a real hollow STEP fixture."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

from PyQt6.QtWidgets import QApplication

from gui.controller import GuiController
from gui.main_window import MainWindow
from gui.widgets.profile_preview_3d_widget import ProfilePreview3DWidget


FIXTURE_FILE = Path(__file__).resolve().parent / "fixtures" / "ocp_hollow_shell.step"


def _ensure_app() -> QApplication:
    """Return a running QApplication for the GUI integration test."""

    app = QApplication.instance()
    if app is not None:
        return app
    return QApplication([])


def test_hollow_fixture_supports_outer_and_inner_selection(monkeypatch) -> None:
    """The GUI should expose outer/inner selection for a real hollow STEP fixture."""

    monkeypatch.setattr(ProfilePreview3DWidget, "refresh_view", lambda self: None)
    monkeypatch.setattr(ProfilePreview3DWidget, "reset_camera_view", lambda self: None)

    app = _ensure_app()
    controller = GuiController()
    window = MainWindow(controller)

    window.ui.edtStepFilePath.setText(str(FIXTURE_FILE))
    window._on_load_step()
    window._on_extract_profile()

    assert controller.outer_profile_points
    assert controller.has_inner_profile
    assert window.ui.rdoProfileOuter.isEnabled()
    assert window.ui.rdoProfileInner.isEnabled()
    assert window.ui.rdoProfileOuter.isChecked()
    assert not window.ui.rdoProfileInner.isChecked()
    assert window._preview_widget is not None
    assert window._preview_widget_3d is not None
    assert window._preview_widget._profile_points == controller.profile_points
    assert window._preview_widget_3d._profile_points == controller.profile_points

    window.ui.rdoProfileInner.setChecked(True)

    assert controller.active_profile_kind == "inner"
    assert controller.scan_path is None
    assert window._preview_widget._scan_path is None
    assert window._preview_widget_3d._scan_path is None
    assert window._preview_widget._profile_points == controller.profile_points
    assert window._preview_widget._reference_profile_points == controller.outer_profile_points
    assert window._preview_widget_3d._profile_points == controller.profile_points
    assert window._preview_widget_3d._reference_profile_points == controller.outer_profile_points

    window._on_generate_path()

    assert controller.scan_path is not None
    assert controller.scan_path.points
    assert all(point.probe_x < point.surface_x for point in controller.scan_path.points)
    assert window._preview_widget._scan_path is controller.scan_path
    assert window._preview_widget_3d._scan_path is controller.scan_path


def test_surface_segments_ignore_horizontal_connectors(monkeypatch) -> None:
    """3D surface generation should only revolve active non-horizontal sidewall segments."""

    monkeypatch.setattr(ProfilePreview3DWidget, "refresh_view", lambda self: None)
    monkeypatch.setattr(ProfilePreview3DWidget, "reset_camera_view", lambda self: None)

    _ensure_app()
    widget = ProfilePreview3DWidget()
    widget.set_profile_points(
        [
            (100.0, 0.0),
            (100.0, 50.0),
            (80.0, 50.0),
            (80.0, 100.0),
        ]
    )

    assert widget._get_active_surface_segments() == [
        [(100.0, 0.0), (100.0, 50.0)],
        [(80.0, 50.0), (80.0, 100.0)],
    ]
