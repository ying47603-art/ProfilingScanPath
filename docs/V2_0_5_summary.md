# V2.0.5 修改说明

## 版本目标

V2.0.5 聚焦于仿形扫描路径在真实几何语义下的一致性与稳定性，重点修复以下问题：

- 圆弧段被误判成直线后导致的路径长度体系冲突
- arc/line 解析几何与 working points 脱节
- `flip_z` 后预览与路径生成不一致
- 多 group、active profile、auto `s_end` 同步之间的弧长定义不统一
- 圆弧 inward offset 合法性判断受局部噪声影响过大

## 关键改动

### 1. 几何分段增强

相关文件：
- [core/profile_extractor.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/profile_extractor.py)
- [tests/test_profile_geometric_segmentation.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_profile_geometric_segmentation.py)

本版增强了 merged chain 后的几何子分段能力：

- 提升 `line / arc / mixed` 的整段判定稳定性
- 增加 `line` 候选的二次圆弧识别
- 对误判为 `line` 的圆弧段做整段 circle fit + 总转角 + 长度比复核
- 改判成功后直接补齐 arc 解析几何字段

新增日志：

- `[PROFILE_DEBUG] line_recheck segment=...`
- `[PROFILE_DEBUG] line_recheck chord_length=... polyline_length=... ratio=...`
- `[PROFILE_DEBUG] line_recheck total_turn_angle=...`
- `[PROFILE_DEBUG] line_recheck circle_fit_valid=... fit_radius=... residual=...`
- `[PROFILE_DEBUG] segment=... reclassified line_to_arc`

### 2. arc 解析几何与统一弧长

相关文件：
- [data/models.py](D:/00%20Project/pythonProject/ProfilingScanPath/data/models.py)
- [core/profile_extractor.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/profile_extractor.py)
- [gui/controller.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/controller.py)
- [core/path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/path_planner.py)

对 `segment_type == "arc"` 且拟合有效的分段，提取阶段现在会一次性保存：

- `arc_theta_start`
- `arc_theta_end`
- `arc_delta_theta`
- `arc_direction`
- `arc_length`
- `arc_geometry_valid`

其中角度统一保存为 unwrap 后的连续角度，避免再次遇到 wrap-around 问题。

同时，系统中与弧长相关的判断已经统一：

- controller 的 active total length
- active group length
- auto `s_end` sync
- planner 的 `total_arc_length`

对有效 arc 一律优先使用 `segment.arc_length`，不再让 UI、controller、planner 各自维护不同的长度定义。

新增日志：

- `[PROFILE_DEBUG] arc_geometry segment=...`
- `[PROFILE_DEBUG] arc_theta_start=... arc_theta_end=...`
- `[PROFILE_DEBUG] arc_direction=...`
- `[PROFILE_DEBUG] arc_delta_theta=...`
- `[PROFILE_DEBUG] arc_length=... arc_geometry_valid=True/False`
- `[PROFILE] group_0 arc_length=...`
- `[PROFILE] active group total_arc_length=...`
- `[PROFILE] s_end synchronized to active group arc length`

### 3. line / arc 解析几何驱动路径生成

相关文件：
- [core/path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/path_planner.py)
- [tests/test_path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_path_planner.py)

路径生成内部现在按 segment geometry 分流：

- `line_analytic`
- `arc_analytic`
- `fallback_points`

行为规则：

- line 段：按解析直线生成 surface point / normal / `rho = inf`
- arc 段：按拟合圆心、半径、连续角度参数生成 surface point / normal / `rho = fit_radius`
- mixed 或无效段：退回原有点驱动逻辑

并且：

- `probe = surface + offset_sign * water_distance * unit_normal`
- `tilt_angle_deg` 只作为姿态输出，不反向决定偏移方向

新增日志：

- `[PATH_DEBUG] segment=... geometry_source=line_analytic`
- `[PATH_DEBUG] segment=... geometry_source=arc_analytic`
- `[PATH_DEBUG] segment=... geometry_source=fallback_points fallback_reason=...`

### 4. 圆弧偏移合法性与平滑约束

相关文件：
- [core/path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/path_planner.py)
- [gui/controller.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/controller.py)
- [gui/main_window.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/main_window.py)

本版保留固定水距公式不变，并增加工程约束：

- 法向单位化
- 法向连续性修正
- inward offset 合法性判断
- 邻接姿态角度变化限制

对有效 arc 段，合法性判断优先用整段 `fit_radius`，不再主要依赖局部三点 `rho`。
当局部 offset 不可行时，直接中止路径生成，并通过 controller / GUI 日志清晰反馈。

新增日志：

- `[PATH_DEBUG] curvature_source=fitted_arc_radius`
- `[PATH_DEBUG] fit_radius=... local_three_point_rho=...`
- `[PATH_WARNING] local offset infeasible at group=... s=... rho=... water=...`
- `[PATH] path generation aborted because local offset is infeasible`

### 5. source / working 状态分层

相关文件：
- [gui/controller.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/controller.py)
- [tests/test_profile_segment_management.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_profile_segment_management.py)

controller 现在显式区分：

- `_source_profile_segments`
- `_active_profile_segments`
- `_active_profile_group_segments`
- `_active_profile_groups`

规则统一为：

- source 只由 extractor 输出更新
- working/rebuilt/transformed 只从 source 派生
- working/display/path 结果不得反向回写 source

这解决了此前“坏副本变成下一轮 original source”的污染问题。

新增日志：

- `[PROFILE_DEBUG] source segment=...`
- `[PROFILE_DEBUG] rebuild input source segment=...`
- `[PROFILE_DEBUG] rebuild output segment=...`
- `[PROFILE_DEBUG] source pollution detected for segment=...`

### 6. flip_z 后 working geometry 全链路一致

相关文件：
- [gui/controller.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/controller.py)
- [core/path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/path_planner.py)
- [tests/test_profile_segment_management.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_profile_segment_management.py)

本版重点修复了：

- 2D/3D preview 已翻转
- 但 Scan Path 仍按翻转前几何生成

修复后规则为：

- `flip_z` 只改 working，不改 source
- working segment 的 `points` 与解析几何字段必须一起镜像
- `generate_path()` 永远只消费当前 transformed working geometry

对 `arc` 段，`flip_z` 后会同步：

- `fit_center_z`
- `arc_theta_start`
- `arc_theta_end`
- `arc_delta_theta`
- `arc_direction`
- `arc_length` 保持不变

对 `line` 段，working transform 后会保证：

- `line_start_z`
- `line_end_z`
- `line_length`

与翻转后的 `points` 对齐。

新增日志：

- `[PROFILE_DEBUG] flip_z=True/False`
- `[PROFILE_DEBUG] working segment=... transformed_points_applied=True/False`
- `[PROFILE_DEBUG] working segment=... analytic_geometry_transformed=True/False`
- `[PROFILE_DEBUG] working segment=... points_vs_analytic_consistent=True/False`
- `[PATH_DEBUG] generate_path uses working geometry`
- `[PATH_DEBUG] source_vs_working_same=False/True`

### 7. 2D/3D 预览语义整理

相关文件：
- [gui/widgets/profile_preview_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_widget.py)
- [gui/widgets/profile_preview_3d_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_3d_widget.py)
- [gui/main_window.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/main_window.py)

2D 图层与图例已经统一成：

- `Enabled Segments`
- `Active Profiles`
- `Scan Path`

并取消了旧的 `Disabled Segments` 独立层。

3D 预览继续跟随当前 active profile / active working geometry，不再跨 group 错误连线。

### 8. 干涉检查与附属窗口

相关文件：
- [core/interference_checker.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/interference_checker.py)
- [gui/display_set_window.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/display_set_window.py)
- [ui/displaysetwindow.ui](D:/00%20Project/pythonProject/ProfilingScanPath/ui/displaysetwindow.ui)
- [gui/ui/generated/ui_displaysetwindow.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/ui/generated/ui_displaysetwindow.py)
- [tests/test_interference_checker.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_interference_checker.py)

增加了相邻层 probe 干涉检测链路与配套 GUI/测试支撑，保证路径生成后的下游消费模块也能读取统一的 working geometry。

## 本版验证

本地使用以下解释器完成验证：

- `C:\ProgramData\Anaconda3\envs\profiling-ocp\python.exe`

已通过的回归包括：

- `tests/test_path_planner.py`
- `tests/test_profile_geometric_segmentation.py`
- `tests/test_profile_segment_management.py`
- `tests/test_hollow_fixture_gui_integration.py`
- `tests/test_interference_checker.py`

## 版本标记

- Git tag：`v2.0.5`
