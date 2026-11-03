# 第三阶段：绕组排布规则

实现文件：`backend/app/geometry/layout.py`。

## PS

PS 的物理径向顺序为原边块、完整主绝缘、副边块。每个块的线径节距为：

`wire.outer_diameter_m + diameter_tolerance_m + process_clearance_m`

有效轴向高度为窗口高度减去两端端部余量；每层匝数为有效高度除以节距后向下取整。每层、每匝和每个并联股都有明确的 radial/axial 坐标与尺寸。

## PSP

PSP 的物理顺序为 `P1 – 主绝缘 – S – 主绝缘 – P2`。对于总原边匝数 `Np`，默认：

- `Np1 = floor(Np/2)`；
- `Np2 = Np - Np1`；
- 因而奇数匝不会丢失，始终满足 `Np1 + Np2 = Np`。

也支持显式 `primary_segments=(Np1, Np2)`，不满足正数或和约束时返回 `PRIMARY_SPLIT_MISMATCH`。P1/P2 连接记录为串联、同向，不能被当成两个独立原边。

两处主绝缘各自使用完整 `main_insulation_m`。代码没有把一处绝缘距离拆成两半。每个接口同时生成 `InsulationGeometry`、MAS section 和 insulation layer。

## 约束

当前检查包括：

- 窗口径向边界和轴向端部余量；
- 每层至少一匝；
- 绕组到骨架/磁芯的最小距离；
- 块间径向碰撞；
- 主绝缘正值；
- P1/P2 总匝数和块顺序；
- 层、匝、导线有效截面积和可选电阻。

失败原因以结构化 violation 返回，例如 `WINDOW_RADIAL_OVERFLOW`、`GEOMETRY_NO_TURN_PER_LAYER`、`INSULATION_NON_POSITIVE`、`RADIAL_COLLISION`。

## 绝缘规则说明

默认模板使用 1 mm 主绝缘，这是与现有演示规则的兼容默认值。真实 ETD 54 联合验证中，真实骨架数据库没有给出 SST 安全规则批准值，因此示例显式选择 0.25 mm 作为研发排布参数，仅用于验证几何是否能映射和计算，不代表任何安全标准符合性。
