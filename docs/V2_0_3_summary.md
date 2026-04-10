# V2.0.3 修改说明

## 版本目标

V2.0.3 主要收敛 V2 GUI 在预览层和界面结构上的一轮细化，重点不是改核心算法，而是让 2D / 3D 预览的显示语义、视觉风格和 UI 状态更加一致。

本次修改主要围绕以下方向展开：

- 2D 与 3D 预览显示语义统一
- 路径与母线的起点 / 终点标记统一
- 预览中的中间离散点进一步清理
- 3D 折线构造与视觉线宽优化
- 最新 Qt Designer `.ui` 结构同步收敛

## 关键改动

### 1. 2D 路径显示改为与 3D 统一

文件：
- [gui/widgets/profile_preview_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_widget.py)

调整内容：
- 2D 视图中的路径显示从 `surface_x / surface_z` 切换为 `probe_x / probe_z`
- 因此 2D 中的橙色路径现在表达的是探头真实偏移后的执行轨迹，而不是贴在母线上的表面点

效果：
- 2D 与 3D 的路径语义保持一致
- 用户可以在 2D 中直接看到探头相对母线的偏移关系

### 2. 去除母线和路径中的中间离散点

文件：
- [gui/widgets/profile_preview_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_widget.py)
- [gui/widgets/profile_preview_3d_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_3d_widget.py)

调整内容：
- 2D 视图中去掉母线和路径的中间小散点
- 3D 视图中去掉路径普通采样点显示
- 仅保留起点 / 终点标记

效果：
- 预览画面更加干净
- 视觉关注点集中到轮廓和实际路径本身

### 3. 起点 / 终点标记统一

文件：
- [gui/widgets/profile_preview_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_widget.py)
- [gui/widgets/profile_preview_3d_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_3d_widget.py)

统一后的规则：
- 起点：绿色圆形
- 终点：红色方形

调整内容：
- 3D 路径原来的紫色 / 青色端点标记改为与母线一致的绿色圆形 / 红色方形
- 2D 和 3D 中，母线与路径的起终点标记语义完全统一
- 3D 中路径文字标签语义也统一为 `Start / End`

效果：
- 用户不再需要记忆两套不同的端点颜色规则
- 2D / 3D 的阅读体验更一致

### 4. 3D 折线线宽优化

文件：
- [gui/widgets/profile_preview_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_widget.py)
- [gui/widgets/profile_preview_3d_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_3d_widget.py)

调整内容：
- 2D 路径线宽调细
- 3D 母线和路径线宽都调细到更接近 2D 母线的观感
- 终点红色方块尺寸进一步缩小

效果：
- 预览边缘区域不再因线宽过粗显得像被截断
- 画面比例更协调

### 5. 3D 折线构造方式调整

文件：
- [gui/widgets/profile_preview_3d_widget.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/widgets/profile_preview_3d_widget.py)

调整内容：
- 3D 折线从手工 `PolyData + lines` 方式改为 `pyvista.lines_from_points(...)`

目标：
- 让 3D 预览中的母线和路径更接近纯折线渲染
- 减少沿折线出现“像顶点标记”的视觉干扰

### 6. 最新 UI 结构同步

文件：
- [ui/mainwindow.ui](D:/00%20Project/pythonProject/ProfilingScanPath/ui/mainwindow.ui)
- [gui/ui/generated/ui_main_window.py](D:/00%20Project/pythonProject/ProfilingScanPath/gui/ui/generated/ui_main_window.py)

同步内容：
- 重新编译了最新版 `.ui`
- 删除不再使用的旧 UI 备份文件：
  - [ui/mainwindow1.ui](D:/00%20Project/pythonProject/ProfilingScanPath/ui/mainwindow1.ui)
  - [ui/mainwindow2.ui](D:/00%20Project/pythonProject/ProfilingScanPath/ui/mainwindow2.ui)
- 对于 3D 显示设置中已从界面删除的控件，主窗口逻辑继续使用原有默认值回退，不影响运行

当前默认回退值包括：
- `show_revolution_wireframe = True`
- `smooth_shading = True`
- `auto_fit_camera = True`

## 当前预览显示语义

### 2D 视图

- 蓝线：母线
- 橙线：探头偏移后的路径
- 绿色圆点：起点
- 红色方块：终点

### 3D 视图

- 蓝线：母线
- 橙线：探头路径
- 绿色球：起点
- 红色方块：终点
- 半透明蓝色表面：回转体显示层

## 本轮版本价值

V2.0.3 让 V2 GUI 的预览层从“功能可用”进一步变成“表达统一、阅读稳定”：

- 用户在 2D / 3D 中看到的是同一套路径语义
- 起终点标记不再混乱
- 中间离散点干扰减少
- 线宽和端点尺寸更适合实际观察
- 最新 UI 结构与代码保持同步

## 版本标记

- Git tag：`v2.0.3`

