# V2.0.5 修改说明

## 版本目标

V2.0.5 继续围绕“仿形母线的几何语义一致性”和“GUI/路径/预览统一消费 working geometry”展开，重点修复以下问题：

- merged chain 分段过粗，明显拐点没有切开
- 圆弧段误判为直线后，`line_analytic` 误参与弧长校验
- 水平线在路径链路中被当作不可用段或被错误切断
- `flip_z` 后预览与路径生成的几何来源不一致
- segment 列表信息不足，不方便判断当前段的几何范围
- UI 删除按钮后，主窗口仍保留旧接线和旧控件依赖

## 核心修改

### 1. 轮廓拐点预切分

相关文件：

- [core/profile_extractor.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/profile_extractor.py)
- [tests/test_profile_geometric_segmentation.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_profile_geometric_segmentation.py)

在 `merged chain -> geometric sub-segmentation` 之间新增了一层“明显拐点预切分”：

- 通过双侧邻域切线检测切向明显突变
- 在折线锐角、非相切 line-arc、非相切 arc-line 连接处优先切开
- 对一个拐角附近的多个 candidate，只保留角度最强的代表点
- 平滑圆弧和连续光顺段不会因为普通曲率存在而被切碎

新增调试日志：

- `[PROFILE_DEBUG] corner_split source_chain=... point_count=...`
- `[PROFILE_DEBUG] corner_candidate index=... angle_deg=...`
- `[PROFILE_DEBUG] corner_accept index=... angle_deg=...`
- `[PROFILE_DEBUG] corner_reject index=... reason=...`
- `[PROFILE_DEBUG] corner_split result subsegments=...`

### 2. line / arc / mixed 几何分段增强

相关文件：

- [core/profile_extractor.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/profile_extractor.py)
- [tests/test_profile_geometric_segmentation.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_profile_geometric_segmentation.py)

在原有几何分段基础上继续增强：

- `line` 候选支持整段 `circle fit + arc ratio + total turn angle` 的二次 arc 识别
- 被误判为 `line` 的圆弧段可在 extractor 阶段直接改判为 `arc`
- 改判成功后立即补齐 arc 拟合和 arc 解析几何字段

新增日志：

- `[PROFILE_DEBUG] line_recheck segment=...`
- `[PROFILE_DEBUG] line_recheck chord_length=... polyline_length=... ratio=...`
- `[PROFILE_DEBUG] line_recheck total_turn_angle=...`
- `[PROFILE_DEBUG] line_recheck circle_fit_valid=... fit_radius=... residual=...`
- `[PROFILE_DEBUG] segment=... reclassified line_to_arc`

### 3. arc 解析几何与统一弧长

相关文件：

- [data/models.py](D:/00%20Project/pythonProject/ProfilingScanPath/data/models.py)
- [core/profile_extractor.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/profile_extractor.py)
- [gui/controller.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/controller.py)
- [core/path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/path_planner.py)

对有效 arc 段统一保存并消费：

- `fit_center_x`
- `fit_center_z`
- `fit_radius`
- `arc_theta_start`
- `arc_theta_end`
- `arc_delta_theta`
- `arc_direction`
- `arc_length`
- `arc_geometry_valid`

其中 `arc_theta_start / arc_theta_end / arc_delta_theta` 统一保存为 unwrap 后的连续角度，避免 planner 再次遇到 wrap-around 问题。

同时，controller 和 planner 中所有“弧长”相关逻辑已经统一：

- 对有效 arc 段优先使用 `segment.arc_length`
- 对 line / mixed / fallback 继续使用 `polyline_length`
- auto `s_end`、group total length、planner 的 `total_arc_length` 均共享同一套定义

新增日志：

- `[PROFILE_DEBUG] arc_geometry segment=...`
- `[PROFILE_DEBUG] arc_theta_start=... arc_theta_end=...`
- `[PROFILE_DEBUG] arc_direction=...`
- `[PROFILE_DEBUG] arc_delta_theta=...`
- `[PROFILE_DEBUG] arc_length=... arc_geometry_valid=True/False`
- `[PROFILE] group_0 arc_length=...`
- `[PROFILE] active group total_arc_length=...`
- `[PROFILE] s_end synchronized to active group arc length`

### 4. line_analytic / arc_analytic 路径生成稳定性

相关文件：

- [core/path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/path_planner.py)
- [tests/test_path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_path_planner.py)

路径生成保持统一公式不变：

- `probe = surface + offset_sign * water_distance * unit_normal`

在此基础上增强了几何分流与保护：

- `line_analytic`
- `arc_analytic`
- `fallback_points`

并增加了：

- `line_analytic` 的几何一致性检查
- 对“不像直线”的错误 line 段自动退回 fallback
- `arc_analytic` 优先使用 extractor 产出的 arc 解析参数，不再临时重算第二套 arc length

新增日志：

- `[PATH_DEBUG] segment=... geometry_source=line_analytic`
- `[PATH_DEBUG] segment=... geometry_source=arc_analytic`
- `[PATH_DEBUG] segment=... geometry_source=fallback_points fallback_reason=...`

### 5. 圆弧偏移合法性与角度平滑

相关文件：

- [core/path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/path_planner.py)
- [gui/controller.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/controller.py)
- [gui/main_window.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/main_window.py)

保留固定水距模型不变的前提下，增加了：

- 法向单位化
- 法向连续性修正
- inward offset 合法性判断
- 邻接姿态角度变化限制

对于有效 arc 段，偏移合法性判断优先使用整段 `fit_radius` 或 `arc_length` 对应的解析几何，而不再依赖易抖动的局部三点 `rho`。

新增日志：

- `[PATH_DEBUG] curvature_source=fitted_arc_radius`
- `[PATH_DEBUG] fit_radius=... local_three_point_rho=...`
- `[PATH_WARNING] local offset infeasible at group=... s=... rho=... water=...`
- `[PATH] path generation aborted because local offset is infeasible`

### 6. source / working 几何分层

相关文件：

- [gui/controller.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/controller.py)
- [tests/test_profile_segment_management.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_profile_segment_management.py)

controller 现已显式区分：

- `_source_profile_segments`
- `_active_profile_segments`
- `_active_profile_group_segments`
- `_active_profile_groups`

规则统一为：

- extractor 结果只进入 source
- working / transformed / rebuilt / display 全部从 source 派生
- working 结果不得回写 source

这修复了“坏副本变成下一轮 original”的 source pollution 问题。

新增日志：

- `[PROFILE_DEBUG] source segment=...`
- `[PROFILE_DEBUG] rebuild input source segment=...`
- `[PROFILE_DEBUG] rebuild output segment=...`
- `[PROFILE_DEBUG] source pollution detected for segment=...`

### 7. flip_z 后 working geometry 全链路一致

相关文件：

- [gui/controller.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/controller.py)
- [core/path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/path_planner.py)
- [tests/test_profile_segment_management.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_profile_segment_management.py)

修复后：

- `flip_z` 只改变 working geometry，不改 source
- 2D preview、3D preview、path generation、probe pose 共用同一套 transformed working geometry
- working segment 的 `points` 和 analytic geometry fields 始终同步

对 arc 段会同步：

- `fit_center_z`
- `arc_theta_start`
- `arc_theta_end`
- `arc_delta_theta`
- `arc_direction`
- `arc_length`

对 line 段会同步：

- `line_start_z`
- `line_end_z`
- `line_length`

新增日志：

- `[PROFILE_DEBUG] flip_z=True/False`
- `[PROFILE_DEBUG] working segment=... transformed_points_applied=True/False`
- `[PROFILE_DEBUG] working segment=... analytic_geometry_transformed=True/False`
- `[PROFILE_DEBUG] working segment=... points_vs_analytic_consistent=True/False`
- `[PATH_DEBUG] generate_path uses working geometry`
- `[PATH_DEBUG] source_vs_working_same=False/True`

### 8. 水平线保留为正式轮廓段

相关文件：

- [core/profile_extractor.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/profile_extractor.py)
- [core/path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/path_planner.py)
- [gui/widgets/profile_preview_3d_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_3d_widget.py)
- [tests/test_path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_path_planner.py)

本版明确支持：

- 完全水平线
- 近似水平线

它们继续作为正式 `line` segment：

- 正常进入 segment 列表
- 正常参与 active profile build
- 正常参与 path generation
- `line_analytic` 可稳定工作

同时修复了之前将 horizontal spans 当作 discontinuity 的路径侧逻辑。  
3D revolve surface 仍只在自身用途上忽略水平连接边，不再与主路径链路耦合。

新增日志：

- `[PROFILE_DEBUG] horizontal line kept as profile segment segment=...`
- `[PROFILE_DEBUG] segment=... type=line x_span=... z_span=...`
- `[PATH_DEBUG] line_start=(..., ...) line_end=(..., ...)`
- `[PATH_DEBUG] tangent=(..., ...)`
- `[PATH_DEBUG] normal=(..., ...)`
- `[PATH_DEBUG] flip_z=... flip_start=... reverse_offset_direction=...`

### 9. segment 列表显示增强与 UI 同步

相关文件：

- [gui/main_window.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/main_window.py)
- [ui/mainwindow.ui](D:/00%20Project/pythonProject/ProfilingScanPath/ui/mainwindow.ui)
- [gui/ui/generated/ui_main_window.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/ui/generated/ui_main_window.py)
- [tests/test_hollow_fixture_gui_integration.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_hollow_fixture_gui_integration.py)

segment 列表条目现在会显示：

- segment 名称
- segment 类型
- 起点/终点 `X / Y / Z`

格式示例：

- `segment_0 [line]  X:(100.000→100.000)  Y:0  Z:(0.000→100.000)`

同时，已经从主窗口初始化和生成代码层清理掉这些已删除控件依赖：

- 上移
- 下移
- 全选
- 干涉检测

并重新编译 `.ui`，让生成代码与真实 UI 同步。

新增日志：

- `[UI_DEBUG] profile segment list refreshed`
- `[UI_DEBUG] segment item text updated: segment=...`

## 本版验证

本地使用以下解释器完成验证：

- `C:\ProgramData\Anaconda3\envs\profiling-ocp\python.exe`

本轮已通过的关键测试包括：

- `tests/test_profile_geometric_segmentation.py`
- `tests/test_path_planner.py`
- `tests/test_profile_segment_management.py`
- `tests/test_hollow_fixture_gui_integration.py`
- `tests/test_interference_checker.py`

## 版本说明

- 当前修改说明对应版本：`v2.0.5`
- 仓库中已存在历史 `v2.0.5` tag；本次主要更新版本说明文档并提交当前代码状态
