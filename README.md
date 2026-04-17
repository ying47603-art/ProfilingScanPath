# ProfilingScanPath V3.0

ProfilingScanPath 是一套面向**旋转体工件仿形扫描路径规划**的桌面软件。  
软件以 STEP 模型为输入，完成轮廓提取、几何分段、二维/三维可视化、扫描路径生成与 CSV 导出，适用于超声检测、水浸检测以及其它需要沿回转体表面进行离线路径规划的工程场景。

## 1. 主要能力

- STEP 模型加载与标准化
- XZ 平面母线轮廓提取
- 轮廓按明显拐点自动细分
- line / arc / mixed 几何段识别
- 基于解析几何的路径生成
  - `line_analytic`
  - `arc_analytic`
  - `fallback_points`
- 2D 轮廓与路径预览
- 3D 旋转体、路径与探头姿态预览
- 路径 CSV 导出
- 浅色主题 GUI 与分区卡片式界面

## 2. 典型应用场景

- 旋转体工件的超声检测路径规划
- 水浸检测路径准备
- 回转类零件的表面扫描轨迹离线生成
- 工件轮廓检查与局部扫描范围验证

## 3. 当前版本亮点（V3.0）

V3.0 基于前续版本的轮廓与路径能力，进一步收敛为一套可交付、可培训、可工程使用的桌面工具，当前重点包括：

- `arc` 段使用整段圆拟合和解析弧长
- `line` 段支持解析几何路径生成
- 误判为 `line` 的圆弧支持二次识别
- 水平线作为正式 `line` 段参与主链路
- `flip_z / flip_start / reverse_offset_direction` 与 working geometry 保持一致
- segment 列表显示段类型与起终点坐标
- GUI 统一浅色主题、面板卡片化、资源图标与自定义箭头样式

详细技术说明见：

- [V3.0 技术总结](D:/00%20Project/pythonProject/ProfilingScanPath/docs/V3_0_technical_summary.md)
- [V2 GUI 使用说明](D:/00%20Project/pythonProject/ProfilingScanPath/docs/V2_GUI_UserGuide.md)

## 4. 运行环境

推荐使用当前项目约定的 Conda 环境：

```powershell
C:\ProgramData\Anaconda3\envs\profiling-ocp\python.exe
```

### 依赖说明

项目当前依赖以本地环境为准，常见依赖包括：

- PyQt6
- pytest
- 与 STEP / OCP 相关的本地几何处理依赖
- matplotlib / 3D 预览相关依赖

如需重建环境，请先确认当前交付环境中的完整依赖清单，再进行补装。

## 5. 启动方式

### 5.1 启动 GUI

```powershell
cd "D:\00 Project\pythonProject\ProfilingScanPath"
& 'C:\ProgramData\Anaconda3\envs\profiling-ocp\python.exe' scripts\run_gui.py
```

### 5.2 重新编译 UI（如修改了 `.ui` 文件）

```powershell
& 'C:\ProgramData\Anaconda3\envs\profiling-ocp\python.exe' -m PyQt6.uic.pyuic "D:\00 Project\pythonProject\ProfilingScanPath\ui\mainwindow.ui" -o "D:\00 Project\pythonProject\ProfilingScanPath\gui\ui\generated\ui_main_window.py"
```

## 6. 标准使用流程

1. 加载 STEP 模型
2. 提取轮廓
3. 在左侧 segment 列表中勾选目标轮廓段
4. 设置 `samples / s_start / s_end / layer_step / water_distance`
5. 必要时执行：
   - 翻转 Z 轴
   - 翻转起始
   - 路径反向偏移
   - 重新标准化
6. 生成路径
7. 通过 2D / 3D 视图检查结果
8. 导出 CSV

## 7. 主要界面区域

### 7.1 左侧控制区

包含：

- STEP 文件加载
- 参数设置
- 修正区
- 轮廓段列表
- 3D 显示设置
- 探头设置

### 7.2 中间 2D 视图

用于查看：

- 当前 active profiles
- 生成路径
- 起点与终点
- 局部法向与偏移关系

### 7.3 右侧 3D 视图

用于查看：

- 旋转体空间形态
- 路径空间分布
- 探头姿态
- 坐标轴与旋转轴

### 7.4 底部日志区

用于输出：

- `STEP`
- `PROFILE`
- `PATH`
- `EXPORT`
- `ERROR`
- `UI_DEBUG`

## 8. 核心参数说明

| 参数 | 含义 | 建议 |
|------|------|------|
| `samples` | 轮廓离散采样数 | 一般从 `100~300` 起步 |
| `s_start` | 起始弧长 | 默认常用 `0` |
| `s_end` | 终止弧长 | 常配合“自动使用总弧长” |
| `layer_step` | 层间步距 | 越小路径越密 |
| `water_distance` | 探头法向偏移距离 | 需结合检测工艺设定 |

## 9. 路径生成机制概览

### 9.1 `line_analytic`

适用于几何一致性良好的直线段，使用解析直线生成表面点、法向和路径。

### 9.2 `arc_analytic`

适用于拟合有效的圆弧段，使用整段圆拟合参数、连续角度与解析弧长生成路径。

### 9.3 `fallback_points`

当解析几何不可稳定使用时，退回基于离散点的插值与法向计算。

## 10. CSV 导出结果

当前导出结果通常包括：

- `profile_points.csv`
- `scan_path_standard.csv`
- `scan_path_compact.csv`

常见字段：

- `x / y / z`
- `angle`

## 11. 容错与保护机制

当前版本包含多项保护逻辑：

- STEP 标准化失败保护
- `arc` 拟合失败自动 fallback
- `line` 几何异常自动 fallback
- `s_start / s_end` 合法性校验
- inward offset 不可行保护
- source / working geometry 分层保护

## 12. 常见问题

### 12.1 为什么没有生成路径？

常见原因：

- 没有成功提取轮廓
- 未勾选任何有效 segment
- `s_start / s_end` 不在有效弧长范围内
- 水距设置导致局部偏移不可行

### 12.2 为什么路径方向不对？

可优先检查：

- 是否需要“翻转起始”
- 是否需要“路径反向偏移”
- `flip_z` 后是否重新生成路径

### 12.3 为什么某段没有按 arc 生成？

可优先检查：

- 当前 segment 是否已识别为 `arc`
- arc 拟合是否有效
- 是否退回了 `fallback_points`

### 12.4 为什么翻转后图和路径不一致？

当前版本设计上：

- 预览
- 路径生成
- 探头姿态

都应基于同一套 working geometry。  
若结果异常，请优先查看日志中的 `PROFILE_DEBUG / PATH_DEBUG`。

## 13. 项目目录简述

```text
ProfilingScanPath/
|-- core/                 核心几何、路径与模型处理
|-- data/                 数据模型定义
|-- exporter/             CSV 导出
|-- gui/                  GUI、样式、预览、资源
|-- scripts/              启动与调试脚本
|-- src/                  图标、辅助资源等源文件
|-- tests/                自动化测试
|-- ui/                   Qt Designer 界面文件
|-- docs/                 版本说明、用户说明、技术文档
`-- README.md
```

## 14. 测试建议

### 14.1 运行 GUI 相关回归

```powershell
& 'C:\ProgramData\Anaconda3\envs\profiling-ocp\python.exe' -m pytest "D:\00 Project\pythonProject\ProfilingScanPath\tests\test_hollow_fixture_gui_integration.py" -q
```

### 14.2 运行几何与路径相关回归

```powershell
& 'C:\ProgramData\Anaconda3\envs\profiling-ocp\python.exe' -m pytest "D:\00 Project\pythonProject\ProfilingScanPath\tests\test_profile_geometric_segmentation.py" "D:\00 Project\pythonProject\ProfilingScanPath\tests\test_profile_segment_management.py" "D:\00 Project\pythonProject\ProfilingScanPath\tests\test_path_planner.py" -q
```

## 15. 版本标识

当前文档对应版本：

- **V3.0**

如需交付说明、培训材料或版本记录，建议同时附带：

- [V3.0 技术总结](D:/00%20Project/pythonProject/ProfilingScanPath/docs/V3_0_technical_summary.md)
- 用户操作说明
- 主界面截图
- 典型路径示例截图
