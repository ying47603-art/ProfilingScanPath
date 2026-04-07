# 水浸自动化超声检测仿形路径规划软件 V1 需求规格书

## 1. 项目概述

开发一款基于 STEP
三维模型的离线路径规划软件，实现纯回转体工件的自动仿形扫描路径生成。

## 2. 输入

-   STEP 三维模型
-   参数：
    -   起始弧长 s_start
    -   终止弧长 s_end
    -   层间步距 layer_step
    -   水距 water_distance

## 3. 输出

### 精简版 CSV

X,Y,Z,Angle

### 标准版 CSV

layer_index,arc_length,surface_x,surface_z,probe_x,probe_y,probe_z,tilt_angle_deg

## 4. 坐标系定义

-   原点：旋转轴最底点
-   Z轴：旋转轴向上
-   X轴：水平向右
-   Y轴：垂直向内

## 5. 探头定义

-   Y = 0
-   偏转在 XZ 平面
-   法向入射
-   固定水距

## 6. 偏角定义

偏角为探头轴线在 XZ 平面相对 Z 轴夹角： θ = atan2(nx, nz)，单位：度

## 7. 路径生成

-   母线：C(s) = (x(s), z(s))
-   层：s_i = s_start + i \* layer_step
-   探头点：Q = P + dN

## 8. 校验规则

-   layer_step \> 0
-   water_distance \> 0
-   0 ≤ s_start \< s_end ≤ 总弧长

## 9. 异常

STEP模型标准化失败 -\> 弹窗提示

## 10. 模块设计

-   模型模块
-   母线模块
-   路径模块
-   导出模块
-   GUI模块
