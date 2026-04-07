"""PyQt6 main window for the minimal ProfilingScanPath GUI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.controller import GuiController


class MainWindow(QMainWindow):
    """Main window for the V1 PyQt6 desktop prototype."""

    def __init__(self, controller: GuiController) -> None:
        """Initialize the main window and all widgets."""

        super().__init__()
        self._controller = controller

        self.setWindowTitle("ProfilingScanPath V1")
        self.resize(980, 760)

        self._step_path_edit = QLineEdit()
        self._browse_button = QPushButton("浏览")
        self._load_button = QPushButton("加载")

        self._samples_edit = QLineEdit("200")
        self._s_start_edit = QLineEdit("0")
        self._s_end_edit = QLineEdit("")
        self._layer_step_edit = QLineEdit("2")
        self._water_distance_edit = QLineEdit("20")

        self._extract_button = QPushButton("提取母线")
        self._generate_button = QPushButton("生成路径")
        self._export_button = QPushButton("导出 CSV")

        self._loader_backend_value = QLabel("-")
        self._has_ocp_shape_value = QLabel("-")
        self._profile_count_value = QLabel("-")
        self._x_range_value = QLabel("-")
        self._z_range_value = QLabel("-")
        self._scan_count_value = QLabel("-")
        self._angle_range_value = QLabel("-")

        self._log_text = QPlainTextEdit()
        self._log_text.setReadOnly(True)

        self._build_ui()
        self._connect_signals()
        self._update_button_states()

    def _build_ui(self) -> None:
        """Build the main window layout."""

        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)

        main_layout.addWidget(self._build_step_group())
        main_layout.addWidget(self._build_parameter_group())
        main_layout.addWidget(self._build_action_group())
        main_layout.addWidget(self._build_result_group())
        main_layout.addWidget(self._build_log_group())

        self.setCentralWidget(central_widget)

    def _build_step_group(self) -> QGroupBox:
        """Build the STEP file selection group."""

        group = QGroupBox("STEP 文件区")
        layout = QHBoxLayout(group)
        layout.addWidget(self._step_path_edit, stretch=1)
        layout.addWidget(self._browse_button)
        layout.addWidget(self._load_button)
        return group

    def _build_parameter_group(self) -> QGroupBox:
        """Build the parameter input group."""

        group = QGroupBox("参数输入区")
        layout = QFormLayout(group)
        layout.addRow("samples", self._samples_edit)
        layout.addRow("s_start", self._s_start_edit)
        layout.addRow("s_end", self._s_end_edit)
        layout.addRow("layer_step", self._layer_step_edit)
        layout.addRow("water_distance", self._water_distance_edit)
        return group

    def _build_action_group(self) -> QGroupBox:
        """Build the action button group."""

        group = QGroupBox("执行区")
        layout = QHBoxLayout(group)
        layout.addWidget(self._extract_button)
        layout.addWidget(self._generate_button)
        layout.addWidget(self._export_button)
        return group

    def _build_result_group(self) -> QGroupBox:
        """Build the result summary group."""

        group = QGroupBox("结果显示区")
        layout = QGridLayout(group)
        layout.addWidget(QLabel("loader_backend"), 0, 0)
        layout.addWidget(self._loader_backend_value, 0, 1)
        layout.addWidget(QLabel("has_ocp_shape"), 0, 2)
        layout.addWidget(self._has_ocp_shape_value, 0, 3)
        layout.addWidget(QLabel("profile_points 数量"), 1, 0)
        layout.addWidget(self._profile_count_value, 1, 1)
        layout.addWidget(QLabel("x_range"), 1, 2)
        layout.addWidget(self._x_range_value, 1, 3)
        layout.addWidget(QLabel("z_range"), 2, 0)
        layout.addWidget(self._z_range_value, 2, 1)
        layout.addWidget(QLabel("scan_path 数量"), 2, 2)
        layout.addWidget(self._scan_count_value, 2, 3)
        layout.addWidget(QLabel("angle 范围"), 3, 0)
        layout.addWidget(self._angle_range_value, 3, 1)
        return group

    def _build_log_group(self) -> QGroupBox:
        """Build the log output group."""

        group = QGroupBox("日志区")
        layout = QVBoxLayout(group)
        layout.addWidget(self._log_text)
        return group

    def _connect_signals(self) -> None:
        """Connect widget signals to their handlers."""

        self._browse_button.clicked.connect(self._on_browse_clicked)
        self._load_button.clicked.connect(self._on_load_clicked)
        self._extract_button.clicked.connect(self._on_extract_clicked)
        self._generate_button.clicked.connect(self._on_generate_clicked)
        self._export_button.clicked.connect(self._on_export_clicked)

    def _on_browse_clicked(self) -> None:
        """Handle STEP file browsing."""

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 STEP 文件",
            "",
            "STEP Files (*.step *.stp)",
        )
        if file_path:
            self._step_path_edit.setText(file_path)

    def _on_load_clicked(self) -> None:
        """Handle STEP loading."""

        try:
            step_path = Path(self._step_path_edit.text().strip())
            if not step_path:
                raise ValueError("请选择 STEP 文件")

            result = self._controller.load_step(step_path)
            self._loader_backend_value.setText(str(result["loader_backend"]))
            self._has_ocp_shape_value.setText(str(result["has_ocp_shape"]))
            self._profile_count_value.setText("-")
            self._x_range_value.setText("-")
            self._z_range_value.setText("-")
            self._scan_count_value.setText("-")
            self._angle_range_value.setText("-")
            self._append_log("[STEP] STEP 文件加载成功")
            self._append_log(f"[STEP] loader_backend={result['loader_backend']}")
            self._append_log(f"[STEP] has_ocp_shape={result['has_ocp_shape']}")
            self._update_button_states()
        except Exception as exc:
            self._handle_error(exc)

    def _on_extract_clicked(self) -> None:
        """Handle profile extraction."""

        try:
            samples = int(self._samples_edit.text().strip())
            result = self._controller.extract_profile(samples=samples)
            self._profile_count_value.setText(str(result["profile_point_count"]))
            self._x_range_value.setText(
                f"{float(result['min_x']):.6f} .. {float(result['max_x']):.6f}"
            )
            self._z_range_value.setText(
                f"{float(result['min_z']):.6f} .. {float(result['max_z']):.6f}"
            )
            self._scan_count_value.setText("-")
            self._angle_range_value.setText("-")
            self._append_log("[PROFILE] 母线提取成功")
            self._append_log(f"[PROFILE] point_count={result['profile_point_count']}")
            self._append_log(
                f"[PROFILE] x_range={float(result['min_x']):.6f} .. {float(result['max_x']):.6f}"
            )
            self._append_log(
                f"[PROFILE] z_range={float(result['min_z']):.6f} .. {float(result['max_z']):.6f}"
            )
            self._update_button_states()
        except Exception as exc:
            self._handle_error(exc)

    def _on_generate_clicked(self) -> None:
        """Handle scan-path generation."""

        try:
            s_start = float(self._s_start_edit.text().strip())
            s_end = self._parse_optional_float(self._s_end_edit.text())
            layer_step = float(self._layer_step_edit.text().strip())
            water_distance = float(self._water_distance_edit.text().strip())

            result = self._controller.generate_path(
                s_start=s_start,
                s_end=s_end,
                layer_step=layer_step,
                water_distance=water_distance,
            )
            self._scan_count_value.setText(str(result["scan_point_count"]))
            self._angle_range_value.setText(
                f"{float(result['min_angle']):.6f} .. {float(result['max_angle']):.6f}"
            )
            self._append_log("[PATH] 路径生成成功")
            self._append_log(f"[PATH] scan_point_count={result['scan_point_count']}")
            self._append_log(f"[PATH] resolved_s_end={float(result['resolved_s_end']):.6f}")
            self._append_log(
                f"[PATH] angle_range={float(result['min_angle']):.6f} .. {float(result['max_angle']):.6f}"
            )
            self._update_button_states()
        except Exception as exc:
            self._handle_error(exc)

    def _on_export_clicked(self) -> None:
        """Handle CSV export."""

        try:
            output_dir = QFileDialog.getExistingDirectory(self, "选择导出目录", str(Path.cwd()))
            if not output_dir:
                return

            result = self._controller.export_csv(Path(output_dir))
            self._append_log("[EXPORT] CSV 导出成功")
            for name, export_path in result.items():
                self._append_log(f"[EXPORT] {name}={export_path}")
            self._update_button_states()
        except Exception as exc:
            self._handle_error(exc)

    def _parse_optional_float(self, text: str) -> Optional[float]:
        """Parse an optional floating-point value from a text input."""

        stripped_text = text.strip()
        if not stripped_text:
            return None
        return float(stripped_text)

    def _update_button_states(self) -> None:
        """Update button enabled states based on controller progress."""

        has_step = self._controller.step_model is not None
        has_profile = bool(self._controller.profile_points)
        has_path = self._controller.scan_path is not None and bool(self._controller.scan_path.points)

        self._extract_button.setEnabled(has_step)
        self._generate_button.setEnabled(has_profile)
        self._export_button.setEnabled(has_path)

    def _append_log(self, message: str) -> None:
        """Append a tagged message to the log area."""

        self._log_text.appendPlainText(message)

    def _handle_error(self, exc: Exception) -> None:
        """Show and log an error message."""

        message = str(exc)
        self._append_log(f"[ERROR] {message}")
        self._update_button_states()
        QMessageBox.critical(self, "错误", message)
