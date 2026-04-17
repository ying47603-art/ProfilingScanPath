"""Designer-based QWidget main window for the V2.0 GUI."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFileDialog, QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout, QWidget

from data.models import ProfileSegment
from gui.controller import GuiController
from gui.display_set_window import DisplaySetWindow
from gui.ui.generated.ui_main_window import Ui_MainWindow
from gui.widgets import ProfilePreview3DWidget, ProfilePreviewWidget


class MainWindow(QWidget):
    """Main widget for the Designer-driven V2.0 GUI."""

    def __init__(self, controller: GuiController) -> None:
        """Initialize the generated UI and bind application actions."""

        super().__init__()
        self._controller = controller
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self._preview_widget: ProfilePreviewWidget | None = None
        self._preview_widget_3d: ProfilePreview3DWidget | None = None
        self._display_set_window: DisplaySetWindow | None = None
        self._last_probe_log_signature: tuple[int, int] | None = None
        self._segment_list_updating = False
        self._preview_batch_updating = False
        self._display_show_profile_3d = True
        self._display_show_path_3d = True
        self._display_show_surface_3d = False
        self._display_show_axis_3d = True
        self._display_show_axis_line_3d = True
        self._display_render_mode_3d = "wireframe"
        self._display_revolve_resolution_3d = 36
        self._display_surface_opacity_3d = 0.35
        self._display_smooth_shading_3d = True
        self._display_auto_fit_camera_3d = True

        self._init_preview_widgets()

        if hasattr(self.ui, "txtLog"):
            self.ui.txtLog.setReadOnly(True)

        self._connect_signals()
        self._reset_result_labels()
        self._sync_auto_s_end_value(log=False)
        self._sync_3d_button_text()
        self._apply_3d_display_settings()
        self._apply_probe_pose_settings()
        self._update_button_states()

    def _init_preview_widgets(self) -> None:
        """Create and mount preview widgets into the UI placeholder areas."""

        if hasattr(self.ui, "wgtPreviewCanvas2D"):
            self._preview_widget = ProfilePreviewWidget(self.ui.wgtPreviewCanvas2D)
            self._mount_widget(self.ui.wgtPreviewCanvas2D, self._preview_widget)

        if hasattr(self.ui, "wgtPreviewCanvas3D"):
            self._preview_widget_3d = ProfilePreview3DWidget(self.ui.wgtPreviewCanvas3D)
            self._mount_widget(self.ui.wgtPreviewCanvas3D, self._preview_widget_3d)

    def _mount_widget(self, container: QWidget, child: QWidget) -> None:
        """Attach a child widget into a placeholder container with a fresh layout."""

        layout = container.layout()
        if layout is None:
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
        else:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
        layout.addWidget(child)

    def _connect_signals(self) -> None:
        """Connect UI signals to the corresponding handlers."""

        if hasattr(self.ui, "btnOpen"):
            self.ui.btnOpen.clicked.connect(self._on_open_and_load_step)
        if hasattr(self.ui, "btnBrowseStep"):
            self.ui.btnBrowseStep.clicked.connect(self._on_browse_step)
        if hasattr(self.ui, "btnLoadStep"):
            self.ui.btnLoadStep.clicked.connect(self._on_load_step)
        if hasattr(self.ui, "btnExtract"):
            self.ui.btnExtract.clicked.connect(self._on_extract_profile)
        if hasattr(self.ui, "btnGenerate"):
            self.ui.btnGenerate.clicked.connect(self._on_generate_path)
        if hasattr(self.ui, "btnExport"):
            self.ui.btnExport.clicked.connect(self._on_export_csv)
        if hasattr(self.ui, "chkAutoSEnd"):
            self.ui.chkAutoSEnd.toggled.connect(self._on_auto_s_end_toggled)
        if hasattr(self.ui, "edtStepFilePath"):
            self.ui.edtStepFilePath.textChanged.connect(self._on_step_path_changed)

        self._connect_profile_transform_controls()
        if hasattr(self.ui, "btnReNormalize"):
            self.ui.btnReNormalize.clicked.connect(self._on_renormalize)

        self._connect_profile_segment_controls()
        self._connect_3d_display_controls()
        self._connect_probe_pose_controls()

    def _connect_profile_segment_controls(self) -> None:
        """Connect segment-list controls to the controller-backed profile builder."""

        list_widget = self._get_profile_segment_list_widget()
        if list_widget is not None:
            list_widget.itemChanged.connect(self._on_profile_segment_item_changed)
            list_widget.itemSelectionChanged.connect(self._on_profile_segment_selection_changed)

    def _connect_profile_transform_controls(self) -> None:
        """Connect checkable profile-transform toolbuttons to controller state."""

        if hasattr(self.ui, "btnFlipZ"):
            self.ui.btnFlipZ.toggled.connect(self._on_profile_transform_toggled)
        if hasattr(self.ui, "btnFlipProfile"):
            self.ui.btnFlipProfile.toggled.connect(self._on_profile_transform_toggled)
        if hasattr(self.ui, "btnReverseOffsetDirection"):
            self.ui.btnReverseOffsetDirection.toggled.connect(self._on_reverse_offset_direction_toggled)

    def _connect_3d_display_controls(self) -> None:
        """Connect 3D display setting widgets to the preview control slot."""

        if hasattr(self.ui, "btnDisplaySurface"):
            self.ui.btnDisplaySurface.clicked.connect(self._on_toggle_surface_display)
        if hasattr(self.ui, "btnMoreSet"):
            self.ui.btnMoreSet.clicked.connect(self._on_open_display_settings)

        if hasattr(self.ui, "btnResetCamera"):
            self.ui.btnResetCamera.clicked.connect(self._on_reset_3d_camera)

    def _connect_probe_pose_controls(self) -> None:
        """Connect probe-pose widgets to the single-probe preview logic."""

        for object_name in (
            "spnProbelLayerIndex",
            "dsbProbeDiameter",
            "dsbProbeLength",
        ):
            widget = getattr(self.ui, object_name, None)
            if widget is not None:
                widget.valueChanged.connect(lambda _value=0: self._apply_probe_pose_settings())

        for object_name in (
            "chkShowProbeBody",
            "chkShowProbeLine",
        ):
            checkbox = getattr(self.ui, object_name, None)
            if checkbox is not None:
                checkbox.toggled.connect(lambda _checked=False: self._apply_probe_pose_settings())

    def _apply_3d_display_settings(self) -> None:
        """Read current GUI settings and apply them to the 3D preview widget."""

        if self._preview_widget_3d is None:
            return

        self._preview_widget_3d.set_display_options(
            show_profile=self._display_show_profile_3d,
            show_scan_path=self._display_show_path_3d,
            show_revolution_wireframe=True,
            show_surface=self._display_show_surface_3d,
            show_axes=self._display_show_axis_3d,
            show_axis_line=self._display_show_axis_line_3d,
            refresh=False,
        )
        self._preview_widget_3d.set_render_mode(self._display_render_mode_3d, refresh=False)
        self._preview_widget_3d.set_surface_options(
            revolve_resolution=self._display_revolve_resolution_3d,
            surface_opacity=self._display_surface_opacity_3d,
            smooth_shading=self._display_smooth_shading_3d,
            refresh=False,
        )
        self._preview_widget_3d.set_camera_options(
            auto_fit_camera=self._display_auto_fit_camera_3d,
            refresh=False,
        )
        self._preview_widget_3d.refresh_view()

    def _apply_probe_pose_settings(self, *, refresh: bool = True) -> None:
        """Read current probe-pose widgets and apply them to the previews."""

        if self._preview_widget is None and self._preview_widget_3d is None:
            return

        self._sync_probe_pose_control_states()
        current_index = self._get_current_probe_index()

        show_probe_body = self._get_checkbox_value("chkShowProbeBody", True)
        show_probe_line = self._get_checkbox_value("chkShowProbeLine", True)
        probe_diameter = self._get_float_value("dsbProbeDiameter", 10.0)
        probe_length = self._get_float_value("dsbProbeLength", 20.0)

        if self._preview_widget is not None:
            self._preview_widget.set_probe_pose_options(
                show_probe_body=show_probe_body,
                show_probe_line=show_probe_line,
                probe_diameter=probe_diameter,
                probe_length=probe_length,
                refresh=False,
            )
            self._preview_widget.set_current_probe_index(current_index, refresh=False)

        if self._preview_widget_3d is not None:
            self._preview_widget_3d.set_probe_pose_options(
                show_probe_body=show_probe_body,
                show_probe_line=show_probe_line,
                probe_diameter=probe_diameter,
                probe_length=probe_length,
                refresh=False,
            )
            self._preview_widget_3d.set_current_probe_index(current_index, refresh=False)
        if refresh:
            if self._preview_widget is not None:
                self._append_log("[UI_DEBUG] refresh 2D")
                self._preview_widget.refresh_view()
            if self._preview_widget_3d is not None:
                self._append_log("[UI_DEBUG] refresh 3D")
                self._preview_widget_3d.refresh_view()
        self._log_current_probe_pose(current_index)

    def _sync_probe_pose_control_states(self) -> None:
        """Enable or disable probe-pose widgets based on path availability."""

        has_path = self._controller.scan_path is not None and bool(self._controller.scan_path.points)
        spinbox = getattr(self.ui, "spnProbelLayerIndex", None)
        if spinbox is not None:
            spinbox.blockSignals(True)
            if has_path:
                spinbox.setMinimum(0)
                spinbox.setMaximum(len(self._controller.scan_path.points) - 1)
                spinbox.setEnabled(True)
                if spinbox.value() > spinbox.maximum():
                    spinbox.setValue(spinbox.maximum())
            else:
                spinbox.setMinimum(0)
                spinbox.setMaximum(0)
                spinbox.setValue(0)
                spinbox.setEnabled(False)
            spinbox.blockSignals(False)

        for object_name in (
            "chkShowProbeBody",
            "chkShowProbeLine",
            "dsbProbeDiameter",
            "dsbProbeLength",
        ):
            widget = getattr(self.ui, object_name, None)
            if widget is not None:
                widget.setEnabled(has_path)

    def _get_current_probe_index(self) -> int | None:
        """Return the selected scan-path index when path data is available."""

        if self._controller.scan_path is None or not self._controller.scan_path.points:
            return None

        spinbox = getattr(self.ui, "spnProbelLayerIndex", None)
        if spinbox is None:
            return 0

        return min(max(0, int(spinbox.value())), len(self._controller.scan_path.points) - 1)

    def _log_current_probe_pose(self, current_index: int | None) -> None:
        """Append one compact probe-pose log line when the current layer changes."""

        if self._controller.scan_path is None or not self._controller.scan_path.points or current_index is None:
            self._last_probe_log_signature = None
            return

        signature = (id(self._controller.scan_path), int(current_index))
        if signature == self._last_probe_log_signature:
            return

        point = self._controller.scan_path.points[current_index]
        self._append_log(
            "[PROBE] "
            f"layer={int(point.layer_index)} "
            f"x={float(point.probe_x):.6f} "
            f"y={float(point.probe_y):.6f} "
            f"z={float(point.probe_z):.6f} "
            f"b={float(point.tilt_angle_deg):.6f}"
        )
        self._last_probe_log_signature = signature

    def _get_profile_segment_list_widget(self) -> QListWidget | None:
        """Return the profile-segment list widget when the current UI provides it."""

        widget = getattr(self.ui, "lstProfileSegments", None)
        return widget if isinstance(widget, QListWidget) else None

    def _populate_profile_segment_list(self) -> None:
        """Fill the segment list from the current controller profile-segment state."""

        list_widget = self._get_profile_segment_list_widget()
        if list_widget is None:
            return

        self._append_log("[UI_DEBUG] populate segment list start")
        self._segment_list_updating = True
        self._append_log("[UI_DEBUG] block list signals")
        list_widget.blockSignals(True)
        list_widget.clear()
        for profile_segment in self._controller.get_profile_segments():
            item_text = self._format_segment_list_text(profile_segment)
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, int(profile_segment.segment_id))
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(
                Qt.CheckState.Checked if profile_segment.is_enabled else Qt.CheckState.Unchecked
            )
            list_widget.addItem(item)
            self._append_log(
                f"[UI_DEBUG] segment item text updated: segment={int(profile_segment.segment_id)}"
            )

        if list_widget.count() > 0:
            list_widget.setCurrentRow(0)
        list_widget.blockSignals(False)
        self._append_log("[UI_DEBUG] unblock list signals")
        self._segment_list_updating = False
        self._update_segment_button_states()
        self._append_log("[UI_DEBUG] profile segment list refreshed")

    def _format_segment_list_text(self, segment: ProfileSegment) -> str:
        """Return one compact single-line segment label including start/end XYZ coordinates."""

        default_text = f"{segment.name} [{segment.segment_type}]"
        if len(segment.points) < 2:
            return default_text

        start_point = segment.points[0]
        end_point = segment.points[-1]
        return (
            f"{segment.name} [{segment.segment_type}]  "
            f"X:({float(start_point[0]):.3f}\u2192{float(end_point[0]):.3f})  "
            f"Y:0  "
            f"Z:({float(start_point[1]):.3f}\u2192{float(end_point[1]):.3f})"
        )

    def _collect_profile_segments_from_list(self) -> list[ProfileSegment]:
        """Build an ordered segment list from the current QListWidget state."""

        list_widget = self._get_profile_segment_list_widget()
        if list_widget is None:
            return []

        segment_lookup = {
            segment.segment_id: segment
            for segment in self._controller.get_profile_segments()
        }
        ordered_segments: list[ProfileSegment] = []
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            segment_id = int(item.data(Qt.ItemDataRole.UserRole))
            base_segment = segment_lookup.get(segment_id)
            if base_segment is None:
                continue
            ordered_segments.append(
                ProfileSegment(
                    segment_id=segment_id,
                    name=base_segment.name,
                    points=list(base_segment.points),
                    point_count=base_segment.point_count,
                    x_min=base_segment.x_min,
                    x_max=base_segment.x_max,
                    z_min=base_segment.z_min,
                    z_max=base_segment.z_max,
                    polyline_length=base_segment.polyline_length,
                    segment_type=base_segment.segment_type,
                    profile_side=base_segment.profile_side,
                    is_enabled=item.checkState() == Qt.CheckState.Checked,
                    fit_center_x=base_segment.fit_center_x,
                    fit_center_z=base_segment.fit_center_z,
                    fit_radius=base_segment.fit_radius,
                    fit_radius_valid=base_segment.fit_radius_valid,
                    fit_residual=base_segment.fit_residual,
                    arc_theta_start=base_segment.arc_theta_start,
                    arc_theta_end=base_segment.arc_theta_end,
                    arc_delta_theta=base_segment.arc_delta_theta,
                    arc_direction=base_segment.arc_direction,
                    arc_length=base_segment.arc_length,
                    arc_geometry_valid=base_segment.arc_geometry_valid,
                    line_start_x=base_segment.line_start_x,
                    line_start_z=base_segment.line_start_z,
                    line_end_x=base_segment.line_end_x,
                    line_end_z=base_segment.line_end_z,
                    line_length=base_segment.line_length,
                    line_valid=base_segment.line_valid,
                )
            )
        return ordered_segments

    def _apply_profile_segment_selection(self, *, log_reordered: bool = False) -> None:
        """Persist current QListWidget state into the controller and refresh dependent views."""

        list_widget = self._get_profile_segment_list_widget()
        if list_widget is None:
            return

        ordered_segments = self._collect_profile_segments_from_list()
        self._controller.set_profile_segments(ordered_segments)
        build_result = self._controller.active_profile_build_result
        enabled_segment_count = sum(1 for segment in ordered_segments if segment.is_enabled)

        self._reset_path_labels()
        self._clear_path_dependent_views(refresh=False)
        self._refresh_profile_previews(refresh_2d=True, refresh_3d=True)
        self._apply_probe_pose_settings(refresh=False)
        self._sync_auto_s_end_value(log=True)
        self._append_log(f"[PROFILE] enabled_segments={enabled_segment_count}")
        self._append_log(f"[PROFILE] active_profile_groups={len(build_result.profile_groups)}")
        if log_reordered:
            reordered_ids = ",".join(str(segment.segment_id) for segment in ordered_segments)
            self._append_log(f"[PROFILE] reordered_segments={reordered_ids}")
        if enabled_segment_count == 0:
            self._append_log("[PROFILE] no enabled segments")
        elif build_result.profile_groups:
            self._append_log("[PROFILE] active_profile rebuilt from selected segments")
        for warning in build_result.warnings:
            self._append_log(warning)
        self._update_button_states()
        self._update_segment_button_states()

    def _apply_profile_transform_controls(self) -> None:
        """Apply checkable transform-toolbutton state to the controller and previews."""

        build_result = self._controller.set_profile_transform_options(
            flip_z=bool(getattr(self.ui, "btnFlipZ", None).isChecked()) if hasattr(self.ui, "btnFlipZ") else None,
            flip_start=bool(getattr(self.ui, "btnFlipProfile", None).isChecked()) if hasattr(self.ui, "btnFlipProfile") else None,
        )

        self._append_log(f"[PROFILE] flip_z={self._controller.flip_z_enabled}")
        self._append_log(f"[PROFILE] flip_start={self._controller.flip_start_enabled}")
        self._append_log(f"[PROFILE] active_profile_groups={len(build_result.profile_groups)}")
        if self._controller.flip_z_enabled:
            self._append_log("[PROFILE_DEBUG] apply flip_z with stable global bounds")
            self._append_log("[PROFILE_DEBUG] active segments reuse global transform context")
        if build_result.profile_groups:
            self._append_log("[PROFILE] active_profile rebuilt with transform options")
        for warning in build_result.warnings:
            self._append_log(warning)

        self._reset_path_labels()
        self._clear_path_dependent_views(refresh=False)
        self._refresh_profile_previews(refresh_2d=True, refresh_3d=True)
        self._apply_probe_pose_settings(refresh=False)
        self._sync_auto_s_end_value(log=True)
        self._append_log("[PATH] scan path cleared because transform options changed")
        self._update_button_states()

    def _on_profile_transform_toggled(self, _checked: bool) -> None:
        """Handle transform toolbutton toggles without mutating source segments."""

        if self._preview_batch_updating:
            return
        self._apply_profile_transform_controls()

    def _on_reverse_offset_direction_toggled(self, checked: bool) -> None:
        """Update scan-path offset direction without mutating the current working profile."""

        self._controller.set_reverse_offset_direction(bool(checked))
        self._reset_path_labels()
        self._clear_path_dependent_views(refresh=False)
        self._refresh_profile_previews(refresh_2d=True, refresh_3d=True)
        self._apply_probe_pose_settings(refresh=False)
        if checked:
            self._append_log("[PATH] 路径偏移方向=法向反向")
        else:
            self._append_log("[PATH] 路径偏移方向=法向同向")
        self._update_button_states()

    def _on_profile_segment_item_changed(self, _item: QListWidgetItem) -> None:
        """Apply checkbox-state edits from the profile-segment list."""

        if self._segment_list_updating:
            return
        self._apply_profile_segment_selection()

    def _on_profile_segment_selection_changed(self) -> None:
        """Refresh preview emphasis and move-button states when list selection changes."""

        self._refresh_profile_previews(refresh_2d=True, refresh_3d=False)
        self._update_segment_button_states()

    def _get_selected_profile_segment_id(self) -> int | None:
        """Return the currently selected profile-segment identifier, if any."""

        list_widget = self._get_profile_segment_list_widget()
        if list_widget is None or list_widget.currentItem() is None:
            return None
        return int(list_widget.currentItem().data(Qt.ItemDataRole.UserRole))

    def _update_segment_button_states(self) -> None:
        """Refresh list-selection dependent UI state for the current simplified segment panel."""

        list_widget = self._get_profile_segment_list_widget()
        if list_widget is None:
            return
        if list_widget.count() > 0 and list_widget.currentRow() < 0:
            list_widget.setCurrentRow(0)

    def _refresh_profile_previews(self, *, refresh_2d: bool = True, refresh_3d: bool = True) -> None:
        """Push active/inactive profile data into the 2D and 3D preview widgets."""

        active_profile_groups = self._controller.active_profile_groups
        active_profile_is_valid = self._controller.active_profile_is_valid
        active_segments = self._controller.get_display_profile_segments()
        active_group_segments = self._controller.get_active_profile_group_segments()
        active_segment_ids = {
            int(segment.segment_id)
            for group in active_group_segments
            for segment in group
        }
        enabled_segments = [
            segment
            for segment in active_segments
            if int(segment.segment_id) not in active_segment_ids
        ]
        disabled_segments = [segment for segment in active_segments if not segment.is_enabled]
        selected_segment_id = self._get_selected_profile_segment_id()
        flattened_active_segments = [segment for group in active_group_segments for segment in group]

        if self._preview_widget is not None:
            self._preview_widget.set_profile_segments(
                enabled_segments=enabled_segments,
                disabled_segments=disabled_segments,
                selected_segment_id=selected_segment_id,
                refresh=False,
            )
            self._preview_widget.set_profile_groups(active_profile_groups, refresh=False)

        if self._preview_widget_3d is not None:
            self._preview_widget_3d.set_profile_segments(
                enabled_segments=flattened_active_segments if active_profile_is_valid else [],
                disabled_segments=disabled_segments if active_profile_is_valid else active_segments,
                refresh=False,
            )
            self._preview_widget_3d.set_profile_groups(
                active_profile_groups if active_profile_is_valid else [],
                refresh=False,
            )
            self._preview_widget_3d.set_reference_profile_points([], refresh=False)

        if refresh_2d and self._preview_widget is not None:
            self._append_log("[UI_DEBUG] refresh 2D")
            self._preview_widget.refresh_view()

        if refresh_3d and self._preview_widget_3d is not None:
            self._append_log("[UI_DEBUG] refresh 3D")
            self._preview_widget_3d.refresh_view()

    def _clear_path_dependent_views(self, *, refresh: bool = True) -> None:
        """Clear all path, probe, and dependent preview state."""

        self._controller.clear_scan_path()
        self._controller.clear_interference_result()
        self._last_probe_log_signature = None
        if self._preview_widget is not None:
            self._preview_widget.set_scan_path(None, refresh=False)
            self._preview_widget.clear_probe_pose(refresh=False)

        if self._preview_widget_3d is not None:
            self._preview_widget_3d.set_scan_path(None, refresh=False)
            self._preview_widget_3d.clear_interference_visuals(refresh=False)
            self._preview_widget_3d.clear_probe_pose(refresh=False)
        if refresh:
            if self._preview_widget is not None:
                self._append_log("[UI_DEBUG] refresh 2D")
                self._preview_widget.refresh_view()
            if self._preview_widget_3d is not None:
                self._append_log("[UI_DEBUG] refresh 3D")
                self._preview_widget_3d.refresh_view()

    def _on_3d_render_mode_changed(self) -> None:
        """Reconcile resolution bounds when the 3D render mode changes."""

        self._sync_3d_revolve_resolution_range()

    def _sync_3d_surface_control_states(self, show_surface: bool) -> None:
        """Enable or disable surface-only controls based on the surface toggle state."""

        window = self._display_set_window
        if window is None:
            return

        for object_name in ("cmbRenderMode3D", "spnRevolveResolution", "dsbSurfaceOpacity"):
            widget = getattr(window.ui, object_name, None)
            if widget is not None:
                widget.setEnabled(show_surface)

    def _sync_3d_revolve_resolution_range(self) -> None:
        """Clamp the revolve-resolution input to the active render-mode range."""

        spinbox = getattr(self._display_set_window.ui, "spnRevolveResolution", None) if self._display_set_window else None
        if spinbox is None:
            return

        minimum, maximum = self._get_revolve_resolution_limits()
        spinbox.blockSignals(True)
        spinbox.setMinimum(minimum)
        spinbox.setMaximum(maximum)
        if spinbox.value() < minimum:
            spinbox.setValue(minimum)
        elif spinbox.value() > maximum:
            spinbox.setValue(maximum)
        spinbox.blockSignals(False)

    def _get_revolve_resolution_limits(self) -> tuple[int, int]:
        """Return the allowed base revolve-resolution range for the current mode."""

        render_mode = self._get_render_mode_from_ui()
        if render_mode == "surface_high":
            return (36, 90)
        return (12, 90)

    def _get_checkbox_value(self, object_name: str, default: bool) -> bool:
        """Return a checkbox value when the widget exists, otherwise a default."""

        checkbox = getattr(self.ui, object_name, None)
        if checkbox is None:
            return default
        return bool(checkbox.isChecked())

    def _get_int_value(self, object_name: str, default: int) -> int:
        """Return an integer widget value when the widget exists."""

        widget = getattr(self.ui, object_name, None)
        if widget is None:
            return default
        return int(widget.value())

    def _get_float_value(self, object_name: str, default: float) -> float:
        """Return a floating-point widget value when the widget exists."""

        widget = getattr(self.ui, object_name, None)
        if widget is None:
            return default
        return float(widget.value())

    def _get_render_mode_from_ui(self) -> str:
        """Map the current 3D render mode combo selection to an internal value."""

        combo = getattr(self._display_set_window.ui, "cmbRenderMode3D", None) if self._display_set_window else None
        if combo is None:
            return self._display_render_mode_3d

        current_index = int(combo.currentIndex())
        if current_index == 1:
            return "surface_low"
        if current_index == 2:
            return "surface_high"
        return "wireframe"

    def _ensure_display_set_window(self) -> DisplaySetWindow:
        """Create the 3D display-settings popup on first use."""

        if self._display_set_window is None:
            self._display_set_window = DisplaySetWindow(self)
            self._display_set_window.ui.btnConfirm3DSet.clicked.connect(self._on_confirm_3d_settings)
            self._display_set_window.ui.cmbRenderMode3D.currentIndexChanged.connect(self._on_3d_render_mode_changed)
            self._sync_display_set_window_from_state()
        return self._display_set_window

    def _sync_display_set_window_from_state(self) -> None:
        """Push current 3D display state into the popup controls."""

        window = self._ensure_display_set_window()
        ui = window.ui

        ui.chkShowProfile3D.setChecked(self._display_show_profile_3d)
        ui.chkShowPath3D.setChecked(self._display_show_path_3d)
        ui.chkShowAxis3D.setChecked(self._display_show_axis_3d)
        ui.chkShowAxisLine3D.setChecked(self._display_show_axis_line_3d)
        ui.spnRevolveResolution.setValue(int(self._display_revolve_resolution_3d))
        ui.dsbSurfaceOpacity.setValue(float(self._display_surface_opacity_3d))
        if self._display_render_mode_3d == "surface_low":
            ui.cmbRenderMode3D.setCurrentIndex(1)
        elif self._display_render_mode_3d == "surface_high":
            ui.cmbRenderMode3D.setCurrentIndex(2)
        else:
            ui.cmbRenderMode3D.setCurrentIndex(0)

        self._sync_3d_revolve_resolution_range()
        self._sync_3d_surface_control_states(self._display_show_surface_3d)

    def _read_display_set_window_state(self) -> None:
        """Read 3D display settings back from the popup controls."""

        window = self._ensure_display_set_window()
        ui = window.ui
        self._display_show_profile_3d = bool(ui.chkShowProfile3D.isChecked())
        self._display_show_path_3d = bool(ui.chkShowPath3D.isChecked())
        self._display_show_axis_3d = bool(ui.chkShowAxis3D.isChecked())
        self._display_show_axis_line_3d = bool(ui.chkShowAxisLine3D.isChecked())
        self._display_render_mode_3d = self._get_render_mode_from_ui()
        self._display_revolve_resolution_3d = int(ui.spnRevolveResolution.value())
        self._display_surface_opacity_3d = float(ui.dsbSurfaceOpacity.value())

    def _sync_3d_button_text(self) -> None:
        """Update the main-window surface toggle button text."""

        button = getattr(self.ui, "btnDisplaySurface", None)
        if button is None:
            return
        button.setText("隐藏表面" if self._display_show_surface_3d else "显示表面")

    def _on_toggle_surface_display(self) -> None:
        """Toggle active surface visibility from the main window."""

        self._display_show_surface_3d = not self._display_show_surface_3d
        self._sync_3d_button_text()
        self._sync_3d_surface_control_states(self._display_show_surface_3d)
        self._apply_3d_display_settings()

    def _on_open_display_settings(self) -> None:
        """Open the popup used to edit 3D display settings."""

        window = self._ensure_display_set_window()
        self._sync_display_set_window_from_state()
        window.show()
        window.raise_()
        window.activateWindow()

    def _on_confirm_3d_settings(self) -> None:
        """Apply popup 3D settings and close the popup window."""

        self._read_display_set_window_state()
        self._sync_3d_revolve_resolution_range()
        self._sync_3d_surface_control_states(self._display_show_surface_3d)
        self._apply_3d_display_settings()
        if self._display_set_window is not None:
            self._display_set_window.close()

    def _on_reset_3d_camera(self) -> None:
        """Reset the 3D preview camera to the default engineering view."""

        if self._preview_widget_3d is None:
            return

        self._preview_widget_3d.reset_camera_view()
        self._append_log("[PROFILE] 3D视角已重置")

    def _on_browse_step(self) -> None:
        """Open a file chooser and write the selected STEP path into the edit box."""

        current_path = self.ui.edtStepFilePath.text().strip() if hasattr(self.ui, "edtStepFilePath") else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 STEP 文件",
            current_path,
            "STEP Files (*.step *.stp)",
        )
        if file_path and hasattr(self.ui, "edtStepFilePath"):
            self.ui.edtStepFilePath.setText(file_path)

    def _on_open_and_load_step(self) -> None:
        """Browse for a STEP file and immediately load it into the workflow."""

        self._on_browse_step()
        if hasattr(self.ui, "edtStepFilePath") and self.ui.edtStepFilePath.text().strip():
            self._on_load_step()

    def _on_load_step(self) -> None:
        """Load the STEP file from the current file path field."""

        try:
            step_path_text = self.ui.edtStepFilePath.text().strip()
            if not step_path_text:
                raise ValueError("请选择 STEP 文件")

            result = self._controller.load_step(Path(step_path_text))
            self._set_result_text("lblLoaderBackendValue", str(result["loader_backend"]))
            self._set_result_text(
                "lblHasOcpShapeValue",
                "True" if bool(result["has_ocp_shape"]) else "False",
            )

            self._reset_profile_labels()
            self._reset_path_labels()
            self._last_probe_log_signature = None
            self._populate_profile_segment_list()
            if self._preview_widget is not None:
                self._preview_widget.clear_preview()
            if self._preview_widget_3d is not None:
                self._preview_widget_3d.clear_preview()
            self._sync_auto_s_end_value(log=False)
            self._apply_probe_pose_settings()

            self._append_log("[STEP] STEP 文件加载成功")
            self._append_log(f"[STEP] loader_backend={result['loader_backend']}")
            self._append_log(f"[STEP] has_ocp_shape={result['has_ocp_shape']}")
            self._update_button_states()
        except Exception as exc:
            self._handle_error(exc)

    def _on_extract_profile(self) -> None:
        """Normalize the current STEP model and extract selectable profiles."""

        try:
            had_path = self._controller.scan_path is not None and bool(self._controller.scan_path.points)
            result = self._controller.extract_profile(samples=int(self.ui.spnSamples.value()))
            self._refresh_after_profile_change(
                result=result,
                action_log="[PROFILE] 轮廓分段提取成功",
                detail_logs=[
                    f"[PROFILE] point_count={result['profile_point_count']}",
                    f"[PROFILE] x_range={float(result['min_x']):.6f} .. {float(result['max_x']):.6f}",
                    f"[PROFILE] z_range={float(result['min_z']):.6f} .. {float(result['max_z']):.6f}",
                ],
                had_path=had_path,
            )
        except Exception as exc:
            self._handle_error(exc)

    def _refresh_after_profile_change(
        self,
        result: dict[str, object],
        action_log: str,
        detail_logs: list[str],
        had_path: bool,
    ) -> None:
        """Refresh labels, previews, and path guidance after profile data changes."""

        self._preview_batch_updating = True
        try:
            self._apply_profile_stats(result)
            self._reset_path_labels()
            self._populate_profile_segment_list()
            self._clear_path_dependent_views(refresh=False)
            self._refresh_profile_previews(refresh_2d=True, refresh_3d=True)
            self._apply_probe_pose_settings(refresh=False)
            self._sync_auto_s_end_value(log=True)
        finally:
            self._preview_batch_updating = False

        self._append_log(action_log)
        self._append_log(f"[PROFILE] extracted_segments={len(self._controller.get_profile_segments())}")
        self._append_log("[PROFILE] segment list updated with geometric types")
        if result.get("global_z_min") is not None and result.get("global_z_max") is not None:
            self._append_log(f"[PROFILE_DEBUG] global_z_min={float(result['global_z_min']):.6f}")
            self._append_log(f"[PROFILE_DEBUG] global_z_max={float(result['global_z_max']):.6f}")
        suggested_order = ",".join(str(segment_id) for segment_id in result.get("suggested_segment_order", []))
        if suggested_order:
            self._append_log(f"[PROFILE] suggested_segment_order={suggested_order}")
        for message in detail_logs:
            self._append_log(message)
        for warning in self._controller.active_profile_build_result.warnings:
            self._append_log(warning)
        if had_path:
            self._append_log("[PATH] 旧路径已失效，请重新生成路径")
        else:
            self._append_log("[PATH] 当前母线已更新，可重新生成路径")
        self._update_button_states()

    def _on_generate_path(self) -> None:
        """Generate the scan path from the current active profile and GUI parameters."""

        try:
            auto_s_end = hasattr(self.ui, "chkAutoSEnd") and self.ui.chkAutoSEnd.isChecked()
            s_end = None if auto_s_end else float(self.ui.dsbSEnd.value())
            build_result = self._controller.build_active_profile_from_segments()
            if not build_result.profile_groups:
                for warning in build_result.warnings:
                    self._append_log(warning)
                raise ValueError("No enabled profile segments are available for path generation")
            result = self._controller.generate_path(
                s_start=float(self.ui.dsbSStart.value()),
                s_end=s_end,
                layer_step=float(self.ui.dsbLayerStep.value()),
                water_distance=float(self.ui.dsbWaterDistance.value()),
            )

            self._set_result_text("lblScanCountValue", str(result["scan_point_count"]))
            self._set_result_text(
                "lblAngleRangeValue",
                f"{float(result['min_angle']):.6f} .. {float(result['max_angle']):.6f}",
            )

            self._refresh_profile_previews(refresh_2d=False, refresh_3d=False)
            if self._preview_widget is not None:
                self._preview_widget.set_scan_path(self._controller.scan_path, refresh=False)
            if self._preview_widget_3d is not None:
                self._preview_widget_3d.set_scan_path(self._controller.scan_path, refresh=False)
                self._preview_widget_3d.clear_interference_visuals(refresh=False)
            self._last_probe_log_signature = None
            self._apply_probe_pose_settings(refresh=True)

            self._append_log("[PATH] 路径生成成功")
            self._append_log(
                "[PATH] 路径偏移方向="
                f"{'法向反向' if self._controller.reverse_offset_direction_enabled else '法向同向'}"
            )
            self._append_log(f"[PATH] scan_point_count={result['scan_point_count']}")
            self._append_log(f"[PATH] generated path groups={result['path_group_count']}")
            self._append_log(f"[PATH] resolved_s_end={float(result['resolved_s_end']):.6f}")
            self._append_log(
                f"[PATH] angle_range={float(result['min_angle']):.6f} .. {float(result['max_angle']):.6f}"
            )
            self._update_button_states()
        except Exception as exc:
            if "local offset infeasible" in str(exc):
                self._append_log("[PATH] path generation aborted because local offset is infeasible")
            self._handle_error(exc)

    def _on_interference_check(self) -> None:
        """Check adjacent layer-index transitions and visualize the result in 3D."""

        try:
            if self._controller.scan_path is None or not self._controller.scan_path.points:
                raise ValueError("No scan path is available for interference checking")
            if self._preview_widget_3d is None:
                raise ValueError("3D preview is not available for interference checking")

            surface_meshes = self._preview_widget_3d.get_active_surface_meshes_for_analysis()
            result = self._controller.check_adjacent_layer_interference(
                surface_meshes=surface_meshes,
                probe_diameter=self._get_float_value("dsbProbeDiameter", 10.0),
                probe_length=self._get_float_value("dsbProbeLength", 20.0),
                interpolation_samples=20,
            )
            self._preview_widget_3d.set_interference_results(result)

            self._append_log("[INTERFERENCE] checking adjacent layer transitions...")
            for pair_result in result.pair_results:
                self._append_log(
                    f"[INTERFERENCE] layer_pair={pair_result.layer_start}->{pair_result.layer_end} "
                    f"collided={pair_result.collided}"
                )
                if pair_result.collision_sample is None:
                    continue

                sample = pair_result.collision_sample
                self._append_log(
                    f"[INTERFERENCE] collision_sample={sample.sample_index}/{sample.sample_count}"
                )
                self._append_log(f"[INTERFERENCE] probe_x={sample.probe_x:.6f}")
                self._append_log(f"[INTERFERENCE] probe_y={sample.probe_y:.6f}")
                self._append_log(f"[INTERFERENCE] probe_z={sample.probe_z:.6f}")
                self._append_log(f"[INTERFERENCE] probe_b={sample.probe_b_angle:.6f}")

            self._append_log(f"[INTERFERENCE] checked_pairs={result.checked_pairs}")
            self._append_log(f"[INTERFERENCE] collided_pairs={result.collided_pairs}")
            self._update_button_states()
        except Exception as exc:
            self._handle_error(exc)

    def _on_export_csv(self) -> None:
        """Export active-profile and scan-path CSV files to a selected directory."""

        try:
            output_dir = QFileDialog.getExistingDirectory(self, "选择导出目录", str(Path.cwd()))
            if not output_dir:
                return

            result = self._controller.export_csv(Path(output_dir))
            self._append_log("[EXPORT] CSV 导出成功")
            for name, export_path in result.items():
                self._append_log(f"[EXPORT] {name}={export_path}")
            QMessageBox.information(self, "导出完成", "CSV 文件导出成功。")
            self._update_button_states()
        except Exception as exc:
            self._handle_error(exc)

    def _on_flip_z_axis(self) -> None:
        """Flip the current selectable profiles on the Z axis and refresh UI state."""

        try:
            had_path = self._controller.scan_path is not None and bool(self._controller.scan_path.points)
            result = self._controller.flip_z_axis()
            self._refresh_after_profile_change(
                result=result,
                action_log="[PROFILE] 已执行 Z 轴翻转",
                detail_logs=[
                    f"[PROFILE] z_range={float(result['min_z']):.6f} .. {float(result['max_z']):.6f}",
                ],
                had_path=had_path,
            )
        except Exception as exc:
            self._handle_error(exc)

    def _on_flip_profile(self) -> None:
        """Reverse the current selectable profile directions and refresh UI state."""

        try:
            had_path = self._controller.scan_path is not None and bool(self._controller.scan_path.points)
            result = self._controller.flip_profile_direction()
            self._refresh_after_profile_change(
                result=result,
                action_log="[PROFILE] 已执行母线翻转",
                detail_logs=[
                    f"[PROFILE] point_count={result['profile_point_count']}",
                ],
                had_path=had_path,
            )
        except Exception as exc:
            self._handle_error(exc)

    def _on_renormalize(self) -> None:
        """Re-run normalization and selectable-profile extraction for the loaded STEP model."""

        try:
            had_path = self._controller.scan_path is not None and bool(self._controller.scan_path.points)
            result = self._controller.extract_profile(samples=int(self.ui.spnSamples.value()))
            self._refresh_after_profile_change(
                result=result,
                action_log="[PROFILE] 已执行重新标准化",
                detail_logs=[
                    f"[PROFILE] point_count={result['profile_point_count']}",
                    f"[PROFILE] x_range={float(result['min_x']):.6f} .. {float(result['max_x']):.6f}",
                    f"[PROFILE] z_range={float(result['min_z']):.6f} .. {float(result['max_z']):.6f}",
                ],
                had_path=had_path,
            )
        except Exception as exc:
            self._handle_error(exc)

    def _on_auto_s_end_toggled(self, checked: bool) -> None:
        """Sync the manual s_end editor with the auto mode setting."""

        if hasattr(self.ui, "dsbSEnd"):
            self.ui.dsbSEnd.setDisabled(checked)
        self._sync_auto_s_end_value(log=True)

    def _on_step_path_changed(self) -> None:
        """Refresh button states when the STEP file path changes."""

        self._update_button_states()

    def _apply_profile_stats(self, result: dict[str, object]) -> None:
        """Update profile-related summary fields from a stats dictionary."""

        self._set_result_text("lblProfileCountValue", str(result["profile_point_count"]))
        self._set_result_text(
            "lblXRangeValue",
            f"{float(result['min_x']):.6f} .. {float(result['max_x']):.6f}",
        )
        self._set_result_text(
            "lblZRangeValue",
            f"{float(result['min_z']):.6f} .. {float(result['max_z']):.6f}",
        )

    def _set_result_text(self, object_name: str, text: str) -> None:
        """Set a result label when that widget exists in the current UI."""

        widget = getattr(self.ui, object_name, None)
        if widget is not None and hasattr(widget, "setText"):
            widget.setText(text)

    def _reset_result_labels(self) -> None:
        """Reset all result labels to their default placeholder values."""

        self._set_result_text("lblLoaderBackendValue", "-")
        self._set_result_text("lblHasOcpShapeValue", "-")
        self._reset_profile_labels()
        self._reset_path_labels()

    def _reset_profile_labels(self) -> None:
        """Reset profile extraction result labels."""

        self._set_result_text("lblProfileCountValue", "-")
        self._set_result_text("lblXRangeValue", "-")
        self._set_result_text("lblZRangeValue", "-")

    def _reset_path_labels(self) -> None:
        """Reset path generation result labels."""

        self._set_result_text("lblScanCountValue", "-")
        self._set_result_text("lblAngleRangeValue", "-")

    def _sync_auto_s_end_value(self, *, log: bool = False) -> None:
        """Synchronize s_start/s_end to the current active profile groups when auto mode is enabled."""

        if not hasattr(self.ui, "chkAutoSEnd") or not self.ui.chkAutoSEnd.isChecked():
            return

        if self._controller.active_profile_groups:
            group_lengths = self._controller.active_profile_group_lengths
            total_arc_length = float(self._controller.active_profile_total_length)

            if hasattr(self.ui, "dsbSStart"):
                self.ui.dsbSStart.blockSignals(True)
                self.ui.dsbSStart.setValue(0.0)
                self.ui.dsbSStart.blockSignals(False)
            if hasattr(self.ui, "dsbSEnd"):
                self.ui.dsbSEnd.blockSignals(True)
                self.ui.dsbSEnd.setValue(total_arc_length)
                self.ui.dsbSEnd.blockSignals(False)

            if log:
                self._append_log("[PROFILE] auto arc-length sync enabled")
                for group_index, group_length in enumerate(group_lengths):
                    self._append_log(f"[PROFILE] group_{group_index} arc_length={float(group_length):.6f}")
                self._append_log(f"[PROFILE] active group total_arc_length={total_arc_length:.6f}")
                self._append_log("[PROFILE] s_end synchronized to active group arc length")
            return

        if self._controller.scan_path is None and hasattr(self.ui, "dsbSStart") and hasattr(self.ui, "dsbSEnd"):
            fallback_start = float(self.ui.dsbSStart.value())
            self.ui.dsbSEnd.blockSignals(True)
            self.ui.dsbSEnd.setValue(fallback_start)
            self.ui.dsbSEnd.blockSignals(False)

    def _update_button_states(self) -> None:
        """Enable or disable primary action buttons according to current state."""

        has_step_path = hasattr(self.ui, "edtStepFilePath") and bool(self.ui.edtStepFilePath.text().strip())
        has_step = self._controller.step_model is not None
        has_segments = bool(self._controller.get_profile_segments())
        has_profile = self._controller.active_profile_is_valid
        has_path = self._controller.scan_path is not None and bool(self._controller.scan_path.points)

        if hasattr(self.ui, "btnLoadStep"):
            self.ui.btnLoadStep.setEnabled(has_step_path)
        if hasattr(self.ui, "btnExtract"):
            self.ui.btnExtract.setEnabled(has_step)
        if hasattr(self.ui, "btnGenerate"):
            self.ui.btnGenerate.setEnabled(has_profile)
        if hasattr(self.ui, "btnDisplaySurface"):
            self.ui.btnDisplaySurface.setEnabled(has_profile)
        if hasattr(self.ui, "btnMoreSet"):
            self.ui.btnMoreSet.setEnabled(has_profile)
        if hasattr(self.ui, "btnExport"):
            self.ui.btnExport.setEnabled(has_path)

        if hasattr(self.ui, "btnFlipZ"):
            self.ui.btnFlipZ.setEnabled(has_segments)
        if hasattr(self.ui, "btnFlipProfile"):
            self.ui.btnFlipProfile.setEnabled(has_segments)
        if hasattr(self.ui, "btnReverseOffsetDirection"):
            self.ui.btnReverseOffsetDirection.setEnabled(has_segments)
        if hasattr(self.ui, "btnReNormalize"):
            self.ui.btnReNormalize.setEnabled(has_step)

        self._update_segment_button_states()

        if hasattr(self.ui, "dsbSEnd") and hasattr(self.ui, "chkAutoSEnd"):
            self.ui.dsbSEnd.setDisabled(self.ui.chkAutoSEnd.isChecked())

    def _append_log(self, message: str) -> None:
        """Append a tagged log line to the log text widget."""

        if hasattr(self.ui, "txtLog"):
            self.ui.txtLog.appendPlainText(message)

    def _handle_error(self, exc: Exception) -> None:
        """Write an error to the log and show a modal message box."""

        message = str(exc)
        self._append_log(f"[ERROR] {message}")
        self._update_button_states()
        QMessageBox.critical(self, "错误", message)
