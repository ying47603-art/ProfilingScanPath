# V2.0.4 修改说明

## 版本目标

V2.0.4 聚焦于中空回转件的“内外表面母线选择”能力收敛，并修复由此带来的路径生成和 3D 预览语义问题。

这一版的核心目标是：

- 支持在 GUI 中区分并选择外表面母线、内表面母线
- 避免把分段外轮廓误判成“外母线 + 内母线”
- 修复真实中空件在 merge 阶段把内外轮廓错误并成一条链的问题
- 让路径生成、2D/3D 预览、probe 姿态都严格跟随当前激活母线

## 关键改动

### 1. 支持内外表面母线选择

相关文件：

- [ui/mainwindow.ui](D:/00%20Project/pythonProject/ProfilingScanPath/ui/mainwindow.ui)
- [gui/ui/generated/ui_main_window.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/ui/generated/ui_main_window.py)
- [gui/main_window.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/main_window.py)
- [gui/controller.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/controller.py)
- [data/models.py](D:/00%20Project/pythonProject/ProfilingScanPath/data/models.py)

本次新增了基于 RadioButton 的母线选择链路：

- `rdoProfileOuter`
- `rdoProfileInner`

行为规则如下：

- 若只识别到外表面母线，则仅启用外母线
- 若同时识别到内外母线，则默认激活外母线
- 切换激活母线后，旧路径会被清空
- 2D / 3D 预览、probe pose 和结果标签会同步刷新

### 2. 母线提取改为“候选链归并后再判断内外”

相关文件：

- [core/profile_extractor.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/profile_extractor.py)

本次没有用“原始 edge / segment 数量”去判断是否存在 inner，而是基于归并后的候选链进行判定。

新增与强化内容包括：

- 候选链统计信息计算
- 外/内候选链完整性判断
- Z 覆盖重叠作为 inner 判定硬条件
- `mean_x` 差异约束
- 统一的 `[PROFILE_DEBUG]` 诊断日志

### 3. 修复 merge 阶段误把内外轮廓拼成一条链

相关文件：

- [core/profile_extractor.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/profile_extractor.py)

此前真实中空件的问题是：

- `raw_candidate_chains` 和 `filtered_candidate_chains` 都存在多条链
- 但在 `_merge_ordered_chains(...)` 中，仅按端点接近就把外壁、内壁和上下连接边串成了一条大链

V2.0.4 对 merge 策略做了受限归并：

- 先给 filtered chain 做几何统计
- 按相对特征区分 `vertical_like`、`horizontal_connector_like`、`mixed`
- merge 时增加拒绝规则，避免 connector 把大半径主链和小半径主链桥接到一起
- 保留真实 outer / inner 主链作为独立候选，再交给后续 outer/inner 判定

新增诊断日志包括：

- filtered chain 的类型与统计
- merge 尝试
- merge 接受原因
- merge 拒绝原因

### 4. 路径偏移方向跟随当前激活母线

相关文件：

- [gui/controller.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/controller.py)
- [core/path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/core/path_planner.py)

本次保持了 `compute_normal()` 原有语义不变，只在 `generate_scan_path()` 中根据 `profile_kind` 选择最终实际使用的有效法向：

- `outer`：沿原有效法向偏移
- `inner`：沿翻转后的有效法向偏移

同时：

- `tilt_angle_deg` 也基于最终实际使用的有效法向计算
- 因此切换到 inner 后，路径和角度语义都会一起翻转

### 5. 2D / 3D 预览区分 active / inactive 母线

相关文件：

- [gui/widgets/profile_preview_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_widget.py)
- [gui/widgets/profile_preview_3d_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_3d_widget.py)

当前语义统一为：

- active profile：正常显示
- inactive profile：弱化显示
- start / end 只强调 active profile
- 路径和 probe pose 只基于当前 active profile

### 6. 3D surface 只回转当前 active profile 的非水平侧壁段

相关文件：

- [gui/widgets/profile_preview_3d_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_3d_widget.py)

本次修复了 3D 表面误显示内外之间连接区域的问题。

新的 surface 构建规则：

- 不再直接对整条 polyline 回转
- 先用 `split_profile_segments(...)` 拆出非水平侧壁段
- 只回转当前 active profile 的有效侧壁段
- inactive profile 不参与 surface mesh 构建

因此：

- outer 激活时，只显示 outer 对应表面
- inner 激活时，只显示 inner 对应表面
- 不再自动生成 inner / outer 之间的封闭连接面

### 7. 新增 fixture 与测试

相关文件：

- [scripts/generate_ocp_fixtures.py](D:/00%20Project/pythonProject/ProfilingScanPath/scripts/generate_ocp_fixtures.py)
- [tests/fixtures/ocp_hollow_shell.step](D:/00%20Project/pythonProject/ProfilingScanPath/tests/fixtures/ocp_hollow_shell.step)
- [tests/test_profile_selection.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_profile_selection.py)
- [tests/test_hollow_fixture_gui_integration.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_hollow_fixture_gui_integration.py)
- [tests/test_path_planner.py](D:/00%20Project/pythonProject/ProfilingScanPath/tests/test_path_planner.py)

本次新增了：

- 真实中空件 STEP fixture
- outer / inner 候选选择相关测试
- GUI/core 联动测试
- inner 路径偏移方向测试
- 3D surface 仅基于非水平侧壁段的测试

## 本版验证重点

V2.0.4 重点验证以下场景：

- 普通圆柱件仅保留 outer
- 环形件 / 中空件可识别 outer + inner
- 阶梯件 / 分段外轮廓件不会被误判成 inner
- inner 激活后，路径位于内侧
- 3D 表面只跟随 active profile

## 版本标记

- Git tag：`2.0.4`
