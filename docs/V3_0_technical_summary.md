# ProfilingScanPath V3.0 技术总结

## 1. 文档定位

本文档用于对 ProfilingScanPath 当前版本的软件结构、关键能力、核心修复点与工程边界做一份可交付的技术总结，适用于：

- 内部技术交底
- 项目交付说明
- 二次开发接手
- 版本归档

本文档对应版本：

- **V3.0**

## 2. 系统目标

ProfilingScanPath 的核心目标是：

1. 从 STEP 模型中提取可用于旋转体扫描的二维母线
2. 对母线进行合理几何分段
3. 基于 line / arc / fallback 几何策略生成扫描路径
4. 通过 2D / 3D 预览验证路径结果
5. 导出可用于后续设备对接或离线分析的 CSV 数据

## 3. 当前系统整体结构

### 3.1 主要模块

- `core/`
  - STEP 处理
  - 模型标准化
  - 轮廓提取
  - 路径规划
  - 干涉检查
- `data/`
  - 数据模型定义
- `gui/`
  - 主窗口
  - 控制器
  - 2D/3D 预览
  - 样式与图标资源
- `exporter/`
  - CSV 导出
- `tests/`
  - 几何、GUI、路径和交互回归测试

### 3.2 GUI 运行入口

当前 GUI 启动链为：

- [scripts/run_gui.py](D:/00%20Project/pythonProject/ProfilingScanPath/scripts/run_gui.py)
- [gui/app.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/app.py)

其中 `gui/app.py` 负责：

- 创建 `QApplication`
- 注册图标资源
- 加载全局浅色主题 QSS
- 创建 `GuiController`
- 启动 `MainWindow`

## 4. 数据与状态管理设计

### 4.1 source / working 分层

当前控制器中已明确区分：

- `source_segments`
  - 来自 extractor 的原始几何语义
  - 保持只读
- `working / active segments`
  - 由 source + 当前 UI 状态派生
  - 支持：
    - 勾选
    - 顺序
    - `flip_z`
    - `flip_start`

这解决了早期版本中“working 副本污染 source”的问题。

### 4.2 当前关键 working 状态

控制器当前重点维护：

- `_source_profile_segments`
- `_active_profile_groups`
- `_active_profile_segments`
- `_active_profile_group_segments`
- `_flip_z_enabled`
- `_flip_start_enabled`
- `_reverse_offset_direction`

路径生成、预览与探头姿态统一消费 working geometry。

## 5. 轮廓提取与分段能力

### 5.1 轮廓提取主链

当前轮廓提取流程大致为：

1. STEP 模型加载
2. 标准化
3. merged chain 构建
4. 明显拐点预切分
5. 几何子段识别
6. 输出 `ProfileSegment` 列表

### 5.2 拐点预切分

V3.0 当前已支持在明显切向突变处对 merged chain 进一步细分：

- 使用双侧邻域切线估计局部方向变化
- 只对明显锐角、非相切连接进行切分
- 平滑圆弧和普通曲率不会被误当作拐点
- 同一拐角附近多个 candidate 仅保留一个代表切分点

这显著改善了：

- segment 列表可读性
- 用户勾选与排序体验
- 后续 `line_analytic / arc_analytic` 稳定性

### 5.3 line / arc / mixed 分类

切分后，各子段继续复用现有分类链路：

- `line`
- `arc`
- `mixed`

corner split 本身不直接给类型，只优化进入分类器的输入质量。

## 6. arc 识别与解析几何

### 6.1 arc 整段圆拟合

当前 `arc` 段不再依赖局部三点曲率作为主依据，而是优先使用整段圆拟合，输出：

- `fit_center_x`
- `fit_center_z`
- `fit_radius`
- `fit_radius_valid`
- `fit_residual`

### 6.2 连续角度与解析弧长

当前 arc 段还会进一步输出：

- `arc_theta_start`
- `arc_theta_end`
- `arc_delta_theta`
- `arc_direction`
- `arc_length`
- `arc_geometry_valid`

其中角度是基于 **unwrap 后连续角度** 保存，而不是原始 `[-pi, pi]` 角度。

这样可以保证：

- `arc_analytic` 中的 `theta = theta_start + direction * s / R`
  稳定成立
- 不再受 wrap-around 影响
- controller / planner / UI 使用统一弧长定义

### 6.3 line 误判为 arc 的二次识别

当前版本支持对初判为 `line` 的候选段进行二次 arc 识别，综合依据包括：

- 整段 circle fit
- `polyline_length / chord_length`
- 总转角

若整体几何更像圆弧，则自动改判为 `arc` 并补齐 arc 几何字段。

## 7. line 解析几何与保护

### 7.1 line_analytic

对稳定直线段，系统使用解析直线几何生成路径：

- 使用端点和切向构造 surface point
- 由切向旋转得到法向
- 曲率半径视为无穷大

### 7.2 水平线支持

V3.0 明确支持：

- 完全水平线
- 近似水平线

它们会继续作为正式 `line` segment 参与：

- segment 列表
- active profile 重建
- 路径生成
- 2D / 3D 预览

### 7.3 line 几何一致性保护

为了防止“看起来像 line、实际上明显弯曲”的段错误进入 `line_analytic`，当前版本加入了 line 几何一致性检查。

若检测到：

- `polyline_length / line_length` 偏差过大
- 总转角明显不接近 0

则退回：

- `fallback_points`

避免解析直线长度与真实几何长度不一致带来的路径错误。

## 8. 路径规划架构

### 8.1 三种几何来源

当前 `core/path_planner.py` 的路径生成几何来源为：

- `line_analytic`
- `arc_analytic`
- `fallback_points`

### 8.2 统一分流逻辑

当前分流规则为：

- 若 `segment_type == line` 且 line geometry 有效
  - 用 `line_analytic`
- 若 `segment_type == arc` 且 arc fit / arc geometry 有效
  - 用 `arc_analytic`
- 其余情况
  - 用 `fallback_points`

### 8.3 弧长一致性

当前系统对弧长定义已统一：

- `arc` 段优先使用 `segment.arc_length`
- `line / mixed / fallback` 使用 `polyline_length`

controller、UI 自动同步与 planner 使用同一套有效弧长来源。

## 9. flip_z / flip_start / reverse_offset_direction

### 9.1 working transform 统一处理

当前所有这些操作都发生在 working geometry 层，而不是 source 层：

- `flip_z`
- `flip_start`
- `reverse_offset_direction`

### 9.2 解析几何同步

V3.0 已确保：

- `points`
- `arc` 解析参数
- `line` 解析参数

在 working transform 后保持一致，不会再出现：

- 预览看起来翻了
- 路径仍按旧几何生成

## 10. GUI 与样式体系

### 10.1 当前 GUI 形态

界面由以下区域构成：

- 顶部工具按钮区
- 左侧控制区
- 轮廓段列表区
- 2D 视图区
- 3D 视图区
- 日志区

### 10.2 浅色主题

当前 GUI 已切换为全局浅色主题，样式集中在：

- [gui/styles/light_theme.qss](D:/00%20Project/pythonProject/ProfilingScanPath/gui/styles/light_theme.qss)

特点：

- 浅色工程软件风格
- panel / card 分区
- 统一按钮、列表、输入框、日志区风格
- `SpinBox / DoubleSpinBox` 自定义箭头图标
- 局部按钮支持 objectName 局部覆盖

### 10.3 资源注册

当前样式和局部 icon 相关资源通过：

- [gui/icon_img.rcc](D:/00%20Project/pythonProject/ProfilingScanPath/gui/icon_img.rcc)
- [gui/icon_resources.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/icon_resources.py)

在 GUI 启动时注册。

### 10.4 列表信息增强

segment 列表当前会显示：

- segment 名称
- 类型
- 起终点 `X / Z`
- `Y:0`

这提升了用户对局部几何范围的快速识别能力。

## 11. 3D 预览与设置

### 11.1 3D 视图职责

3D 视图主要用于：

- 展示旋转体形态
- 展示路径空间位置
- 展示探头姿态
- 辅助验证翻转、偏移和法向效果

### 11.2 3D 设置按钮

3D 设置区中的：

- `btnMoreSet`

当前作为小型 icon-toolbutton 使用，并单独保留局部样式，不跟随普通按钮尺寸。

## 12. 导出能力

当前导出器支持：

- `profile_points.csv`
- `scan_path_standard.csv`
- `scan_path_compact.csv`

输出由控制器统一组织，再由 exporter 写盘。

## 13. 主要测试覆盖

当前版本已建立以下测试覆盖：

- `tests/test_profile_geometric_segmentation.py`
- `tests/test_path_planner.py`
- `tests/test_profile_segment_management.py`
- `tests/test_hollow_fixture_gui_integration.py`
- `tests/test_interference_checker.py`

这些测试覆盖了：

- 轮廓细分
- line / arc 几何逻辑
- working/source 状态管理
- GUI 关键交互
- 干涉检查主链路

## 14. 当前已知边界

### 14.1 3D 表面是工程可视化近似

当前 3D 视图中的旋转表面主要用于：

- 视觉验证
- 路径关系检查

它不是完整 CAD 查看器，也不等同于 STEP 原始实体的完整渲染。

### 14.2 路径质量仍依赖输入几何质量

虽然系统已有：

- 标准化
- 拐点切分
- line/arc 识别
- fallback 保护

但输入 STEP 的质量仍然直接影响最终轮廓和路径稳定性。

### 14.3 GUI 主题仍以工程可用性优先

当前界面样式已经具备：

- 统一浅色主题
- 分区层次
- 可读性增强

但仍以工程实用为主，而非面向商业化精修 UI 设计。

## 15. 建议后续演进方向

后续若继续推进，可重点考虑：

1. 更细的局部路径质量分析工具
2. 更多轮廓分段人工修正能力
3. 更完整的 3D 工艺设置与探头仿真
4. 更完善的 CSV / 设备接口适配
5. 更强的 GUI 自动化检查

## 16. 结论

V3.0 的 ProfilingScanPath 已经从早期的项目骨架，收敛为一套具备以下特征的工程化桌面软件：

- 可导入真实 STEP 模型
- 可提取与细分轮廓
- 可识别 line / arc 并优先使用解析几何
- 可在 2D / 3D 中验证路径
- 可导出标准化 CSV 数据
- 具备较完整的容错与 GUI 交互基础

对于当前的工程交付、内部培训和后续扩展，已经具备较好的可维护性和可说明性。
