"""Designer-based QWidget main window for the V2.0 GUI."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QVBoxLayout, QWidget

from core.path_planner import compute_effective_arc_length
from gui.controller import GuiController
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

        self._init_preview_widgets()

        if hasattr(self.ui, "txtLog"):
            self.ui.txtLog.setReadOnly(True)

        self._connect_signals()
        self._reset_result_labels()
        self._sync_profile_selection_ui()
        self._sync_auto_s_end_value()
        self._apply_3d_display_settings()
        self._apply_probe_pose_settings()
        self._update_probe_pose_ui()
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

        if hasattr(self.ui, "btnFlipZ"):
            self.ui.btnFlipZ.clicked.connect(self._on_flip_z_axis)
        if hasattr(self.ui, "btnFlipProfile"):
            self.ui.btnFlipProfile.clicked.connect(self._on_flip_profile)
        if hasattr(self.ui, "btnReNormalize"):
            self.ui.btnReNormalize.clicked.connect(self._on_renormalize)

        self._connect_profile_selection_controls()
        self._connect_3d_display_controls()
        self._connect_probe_pose_controls()

    def _connect_profile_selection_controls(self) -> None:
        """Connect outer/inner profile selection radio buttons."""

        outer_radio = getattr(self.ui, "rdoProfileOuter", None)
        if outer_radio is not None:
            outer_radio.toggled.connect(lambda checked: self._on_profile_selection_toggled("outer", checked))

        inner_radio = getattr(self.ui, "rdoProfileInner", None)
        if inner_radio is not None:
            inner_radio.toggled.connect(lambda checked: self._on_profile_selection_toggled("inner", checked))

    def _connect_3d_display_controls(self) -> None:
        """Connect 3D display setting widgets to the preview control slot."""

        checkbox_names = [
            "chkShowProfile3D",
            "chkShowPath3D",
            "chkShowWireframe3D",
            "chkShowSurface3D",
            "chkShowAxis3D",
            "chkShowAxisLine3D",
            "chkSmoothShading",
            "chkAutoFitCamera",
        ]
        for object_name in checkbox_names:
            checkbox = getattr(self.ui, object_name, None)
            if checkbox is not None:
                checkbox.toggled.connect(lambda _checked=False: self._apply_3d_display_settings())

        for object_name in ("spnRevolveResolution", "dsbSurfaceOpacity"):
            widget = getattr(self.ui, object_name, None)
            if widget is not None:
                widget.valueChanged.connect(lambda _value=0: self._apply_3d_display_settings())

        if hasattr(self.ui, "cmbRenderMode3D"):
            self.ui.cmbRenderMode3D.currentIndexChanged.connect(self._on_3d_render_mode_changed)

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

        self._sync_3d_revolve_resolution_range()
        show_surface = self._get_checkbox_value("chkShowSurface3D", False)
        self._sync_3d_surface_control_states(show_surface)

        self._preview_widget_3d.set_display_options(
            show_profile=self._get_checkbox_value("chkShowProfile3D", True),
            show_scan_path=self._get_checkbox_value("chkShowPath3D", True),
            show_revolution_wireframe=self._get_checkbox_value("chkShowWireframe3D", True),
            show_surface=show_surface,
            show_axes=self._get_checkbox_value("chkShowAxis3D", True),
            show_axis_line=self._get_checkbox_value("chkShowAxisLine3D", True),
            refresh=False,
        )
        self._preview_widget_3d.set_render_mode(self._get_render_mode_from_ui(), refresh=False)
        self._preview_widget_3d.set_surface_options(
            revolve_resolution=self._get_int_value("spnRevolveResolution", 36),
            surface_opacity=self._get_float_value("dsbSurfaceOpacity", 0.35),
            smooth_shading=self._get_checkbox_value("chkSmoothShading", True),
            refresh=False,
        )
        self._preview_widget_3d.set_camera_options(
            auto_fit_camera=self._get_checkbox_value("chkAutoFitCamera", True),
            refresh=False,
        )
        self._preview_widget_3d.refresh_view()

    def _apply_probe_pose_settings(self) -> None:
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
            )
            self._preview_widget.set_current_probe_index(current_index)

        if self._preview_widget_3d is not None:
            self._preview_widget_3d.set_probe_pose_options(
                show_probe_body=show_probe_body,
                show_probe_line=show_probe_line,
                probe_diameter=probe_diameter,
                probe_length=probe_length,
                refresh=False,
            )
            self._preview_widget_3d.set_current_probe_index(current_index, refresh=False)
            self._preview_widget_3d.refresh_view()
        self._update_probe_pose_ui()

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

    def _update_probe_pose_ui(self) -> None:
        """Update the current probe X/Y/Z/B readout labels."""

        current_index = self._get_current_probe_index()
        point = None
        if current_index is not None and self._controller.scan_path is not None:
            point = self._controller.scan_path.points[current_index]

        if point is None:
            for object_name in (
                "lblProbeXValue",
                "lblProbeYValue",
                "lblProbeZValue",
                "lblProbeBValue",
            ):
                self._set_result_text(object_name, "-")
            return

        self._set_result_text("lblProbeXValue", f"{float(point.probe_x):.6f}")
        self._set_result_text("lblProbeYValue", f"{float(point.probe_y):.6f}")
        self._set_result_text("lblProbeZValue", f"{float(point.probe_z):.6f}")
        self._set_result_text("lblProbeBValue", f"{float(point.tilt_angle_deg):.6f}")

    def _sync_profile_selection_ui(self) -> None:
        """Update radio-button states to match the current selectable profiles."""

        outer_radio = getattr(self.ui, "rdoProfileOuter", None)
        inner_radio = getattr(self.ui, "rdoProfileInner", None)
        has_outer = bool(self._controller.outer_profile_points)
        has_inner = self._controller.has_inner_profile

        if outer_radio is not None:
            outer_radio.blockSignals(True)
            outer_radio.setEnabled(has_outer)
            outer_radio.setChecked(has_outer and self._controller.active_profile_kind == "outer")
            outer_radio.blockSignals(False)

        if inner_radio is not None:
            inner_radio.blockSignals(True)
            inner_radio.setEnabled(has_inner)
            inner_radio.setChecked(has_inner and self._controller.active_profile_kind == "inner")
            inner_radio.blockSignals(False)

    def _refresh_profile_previews(self) -> None:
        """Push active/inactive profile data into the 2D and 3D preview widgets."""

        active_profile_points = self._controller.profile_points
        inactive_profile_points = self._controller.inactive_profile_points

        if self._preview_widget is not None:
            self._preview_widget.set_profile_points(active_profile_points)
            self._preview_widget.set_reference_profile_points(inactive_profile_points)

        if self._preview_widget_3d is not None:
            self._preview_widget_3d.set_profile_points(active_profile_points)
            self._preview_widget_3d.set_reference_profile_points(inactive_profile_points)

    def _clear_path_dependent_views(self) -> None:
        """Clear all path, probe, and dependent preview state."""

        if self._preview_widget is not None:
            self._preview_widget.set_scan_path(None)
            self._preview_widget.clear_probe_pose()

        if self._preview_widget_3d is not None:
            self._preview_widget_3d.set_scan_path(None)
            self._preview_widget_3d.clear_probe_pose(refresh=False)
            self._preview_widget_3d.refresh_view()

        self._apply_probe_pose_settings()

    def _on_profile_selection_toggled(self, profile_kind: str, checked: bool) -> None:
        """Switch the active profile when the outer/inner radio state changes."""

        if not checked or not self._controller.outer_profile_points:
            return

        if profile_kind == self._controller.active_profile_kind:
            return

        try:
            result = self._controller.set_active_profile(profile_kind)
            self._apply_profile_stats(result)
            self._reset_path_labels()
            self._sync_profile_selection_ui()
            self._refresh_profile_previews()
            self._clear_path_dependent_views()
            self._sync_auto_s_end_value()

            profile_label = "内表面母线" if profile_kind == "inner" else "外表面母线"
            self._append_log(f"[PROFILE] 当前母线切换为：{profile_label}")
            self._update_button_states()
        except Exception as exc:
            self._handle_error(exc)

    def _on_3d_render_mode_changed(self) -> None:
        """Reconcile resolution bounds when the 3D render mode changes."""

        self._sync_3d_revolve_resolution_range()
        self._apply_3d_display_settings()

    def _sync_3d_surface_control_states(self, show_surface: bool) -> None:
        """Enable or disable surface-only controls based on the surface toggle state."""

        for object_name in (
            "cmbRenderMode3D",
            "spnRevolveResolution",
            "dsbSurfaceOpacity",
            "chkSmoothShading",
        ):
            widget = getattr(self.ui, object_name, None)
            if widget is not None:
                widget.setEnabled(show_surface)

    def _sync_3d_revolve_resolution_range(self) -> None:
        """Clamp the revolve-resolution input to the active render-mode range."""

        spinbox = getattr(self.ui, "spnRevolveResolution", None)
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

        combo = getattr(self.ui, "cmbRenderMode3D", None)
        if combo is None:
            return "wireframe"

        current_index = int(combo.currentIndex())
        if current_index == 1:
            return "surface_low"
        if current_index == 2:
            return "surface_high"
        return "wireframe"

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
            self._sync_profile_selection_ui()
            if self._preview_widget is not None:
                self._preview_widget.clear_preview()
            if self._preview_widget_3d is not None:
                self._preview_widget_3d.clear_preview()
            self._sync_auto_s_end_value()
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
            available_profiles = "outer+inner" if bool(result.get("has_inner_profile")) else "outer_only"
            self._refresh_after_profile_change(
                result=result,
                action_log="[PROFILE] 母线提取成功",
                detail_logs=[
                    f"[PROFILE] point_count={result['profile_point_count']}",
                    f"[PROFILE] x_range={float(result['min_x']):.6f} .. {float(result['max_x']):.6f}",
                    f"[PROFILE] z_range={float(result['min_z']):.6f} .. {float(result['max_z']):.6f}",
                    f"[PROFILE] available_profiles={available_profiles}",
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

        self._apply_profile_stats(result)
        self._reset_path_labels()
        self._sync_profile_selection_ui()
        self._refresh_profile_previews()
        self._clear_path_dependent_views()
        self._sync_auto_s_end_value()

        self._append_log(action_log)
        for message in detail_logs:
            self._append_log(message)
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

            self._refresh_profile_previews()
            if self._preview_widget is not None:
                self._preview_widget.set_scan_path(self._controller.scan_path)
            if self._preview_widget_3d is not None:
                self._preview_widget_3d.set_scan_path(self._controller.scan_path)
            self._apply_probe_pose_settings()

            self._append_log("[PATH] 路径生成成功")
            self._append_log(f"[PATH] scan_point_count={result['scan_point_count']}")
            self._append_log(f"[PATH] resolved_s_end={float(result['resolved_s_end']):.6f}")
            self._append_log(
                f"[PATH] angle_range={float(result['min_angle']):.6f} .. {float(result['max_angle']):.6f}"
            )
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
            available_profiles = "outer+inner" if bool(result.get("has_inner_profile")) else "outer_only"
            self._refresh_after_profile_change(
                result=result,
                action_log="[PROFILE] 已执行重新标准化",
                detail_logs=[
                    f"[PROFILE] point_count={result['profile_point_count']}",
                    f"[PROFILE] x_range={float(result['min_x']):.6f} .. {float(result['max_x']):.6f}",
                    f"[PROFILE] z_range={float(result['min_z']):.6f} .. {float(result['max_z']):.6f}",
                    f"[PROFILE] available_profiles={available_profiles}",
                ],
                had_path=had_path,
            )
        except Exception as exc:
            self._handle_error(exc)

    def _on_auto_s_end_toggled(self, checked: bool) -> None:
        """Sync the manual s_end editor with the auto mode setting."""

        if hasattr(self.ui, "dsbSEnd"):
            self.ui.dsbSEnd.setDisabled(checked)
        self._sync_auto_s_end_value()

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

    def _sync_auto_s_end_value(self) -> None:
        """Update the displayed s_end value when auto mode is enabled."""

        if not hasattr(self.ui, "chkAutoSEnd") or not self.ui.chkAutoSEnd.isChecked():
            return

        if self._controller.profile_points:
            total_arc_length = compute_effective_arc_length(self._controller.profile_points)
            self.ui.dsbSEnd.setValue(float(total_arc_length))
        elif self._controller.scan_path is None and hasattr(self.ui, "dsbSStart"):
            self.ui.dsbSEnd.setValue(float(self.ui.dsbSStart.value()))

    def _update_button_states(self) -> None:
        """Enable or disable primary action buttons according to current state."""

        has_step_path = hasattr(self.ui, "edtStepFilePath") and bool(self.ui.edtStepFilePath.text().strip())
        has_step = self._controller.step_model is not None
        has_profile = bool(self._controller.profile_points)
        has_path = self._controller.scan_path is not None and bool(self._controller.scan_path.points)

        if hasattr(self.ui, "btnLoadStep"):
            self.ui.btnLoadStep.setEnabled(has_step_path)
        if hasattr(self.ui, "btnExtract"):
            self.ui.btnExtract.setEnabled(has_step)
        if hasattr(self.ui, "btnGenerate"):
            self.ui.btnGenerate.setEnabled(has_profile)
        if hasattr(self.ui, "btnExport"):
            self.ui.btnExport.setEnabled(has_path)

        if hasattr(self.ui, "btnFlipZ"):
            self.ui.btnFlipZ.setEnabled(has_profile)
        if hasattr(self.ui, "btnFlipProfile"):
            self.ui.btnFlipProfile.setEnabled(has_profile)
        if hasattr(self.ui, "btnReNormalize"):
            self.ui.btnReNormalize.setEnabled(has_step)

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
