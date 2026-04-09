"""Designer-based QWidget main window for the V2.0 GUI."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QVBoxLayout, QWidget

from core.path_planner import compute_arc_length
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
        self._sync_auto_s_end_value()
        self._apply_3d_display_settings()
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

        self._connect_3d_display_controls()

    def _connect_3d_display_controls(self) -> None:
        """Connect 3D display setting widgets to the preview control slot."""

        checkbox_names = [
            "chkShowProfile3D",
            "chkShowPath3D",
            "chkShowWireframe3D",
            "chkShowSurface3D",
            "chkShowAxis3D",
            "chkShowAxisLine3D",
            "chkShowLabels3D",
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
            self.ui.cmbRenderMode3D.currentIndexChanged.connect(
                lambda _index=0: self._apply_3d_display_settings()
            )

        if hasattr(self.ui, "btnResetCamera"):
            self.ui.btnResetCamera.clicked.connect(self._on_reset_3d_camera)

    def _apply_3d_display_settings(self) -> None:
        """Read current GUI settings and apply them to the 3D preview widget."""

        if self._preview_widget_3d is None:
            return

        self._preview_widget_3d.set_display_options(
            show_profile=self._get_checkbox_value("chkShowProfile3D", True),
            show_scan_path=self._get_checkbox_value("chkShowPath3D", True),
            show_revolution_wireframe=self._get_checkbox_value("chkShowWireframe3D", True),
            show_surface=self._get_checkbox_value("chkShowSurface3D", False),
            show_axes=self._get_checkbox_value("chkShowAxis3D", True),
            show_axis_line=self._get_checkbox_value("chkShowAxisLine3D", True),
            show_text_labels=self._get_checkbox_value("chkShowLabels3D", False),
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
            self._sync_auto_s_end_value()
            if self._preview_widget is not None:
                self._preview_widget.clear_preview()
            if self._preview_widget_3d is not None:
                self._preview_widget_3d.clear_preview()

            self._append_log("[STEP] STEP 文件加载成功")
            self._append_log(f"[STEP] loader_backend={result['loader_backend']}")
            self._append_log(f"[STEP] has_ocp_shape={result['has_ocp_shape']}")
            self._update_button_states()
        except Exception as exc:
            self._handle_error(exc)

    def _on_extract_profile(self) -> None:
        """Normalize the current STEP model and extract profile points."""

        try:
            had_path = self._controller.scan_path is not None and bool(self._controller.scan_path.points)
            result = self._controller.extract_profile(samples=int(self.ui.spnSamples.value()))
            self._refresh_after_profile_change(
                result=result,
                action_log="[PROFILE] 母线提取成功",
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
        """Refresh labels, preview, and path guidance after profile data changes."""

        self._apply_profile_stats(result)
        self._reset_path_labels()
        self._sync_auto_s_end_value()

        if self._preview_widget is not None:
            self._preview_widget.set_profile_points(self._controller.profile_points)
            self._preview_widget.set_scan_path(None)
        if self._preview_widget_3d is not None:
            self._preview_widget_3d.set_profile_points(self._controller.profile_points)
            self._preview_widget_3d.set_scan_path(None)

        self._append_log(action_log)
        for message in detail_logs:
            self._append_log(message)
        if had_path:
            self._append_log("[PATH] 旧路径已失效，请重新生成路径")
        else:
            self._append_log("[PATH] 母线已更新，可重新生成路径")
        self._update_button_states()

    def _on_generate_path(self) -> None:
        """Generate the scan path from the current profile and GUI parameters."""

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

            if self._preview_widget is not None:
                self._preview_widget.set_profile_points(self._controller.profile_points)
                self._preview_widget.set_scan_path(self._controller.scan_path)
            if self._preview_widget_3d is not None:
                self._preview_widget_3d.set_profile_points(self._controller.profile_points)
                self._preview_widget_3d.set_scan_path(self._controller.scan_path)

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
        """Export profile and scan path CSV files to a selected directory."""

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
        """Flip the current profile on the Z axis and refresh dependent UI state."""

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
        """Reverse the current profile direction and refresh dependent UI state."""

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
        """Re-run normalization and profile extraction for the loaded STEP model."""

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
            total_arc_length = compute_arc_length(self._controller.profile_points)[-1]
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
