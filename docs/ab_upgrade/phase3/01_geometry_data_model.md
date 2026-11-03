# 第三阶段：参数化几何数据模型

## 范围

第三阶段新增 `backend/app/geometry/`，不导入现有 `backend/app/core/engine.py`，也不修改当前 NSGA-II、前端和生产依赖。它只负责生成可追溯的参数化结构、验证几何约束，并把结构交给 Phase 2 Provider。

## 核心对象

| 对象 | 代码 | 作用 |
|---|---|---|
| `CoreGeometry` | `backend/app/geometry/models.py` | 区分物理外形、窗口/绕线柱尺寸、有效 Ae/le/Ve、气隙和组合堆叠数量 |
| `WireGeometry` | 同上 | 导线外径、导体直径、并联股数和可选直流电阻率 |
| `WindingSpec` | 同上 | 待排布的原边/副边匝数、并联数和导线 |
| `WindingLayout` | 同上 | 模板、径向分块、轴向匝/径向层方向、工艺余量和绝缘规则 |
| `WindingSegmentGeometry` | 同上 | 一个绕组块的层、匝、坐标、平均匝长、支路长度和电阻 |
| `InsulationGeometry` | 同上 | 两个相邻绕组块之间的一处完整主绝缘 |
| `LayoutGeometry` | 同上 | 完整结构、连接关系、可行性、违反项、警告和可信度来源 |

## 单位和坐标

内部长度全部使用 m，面积使用 m²，体积使用 m³，电感使用 H，频率使用 Hz，损耗使用 W，质量使用 kg。显示层如果需要 mm，应在边界转换；本阶段没有把 mm 混入几何核心。

绕组坐标使用二维 `(radial, axial)`：径向从骨架/窗口内侧向外，轴向从窗口中心向两端；匝沿轴向递增，层沿径向递增。MAS 映射保留这两个坐标和每匝尺寸，不仅传递窗口填充率。

磁芯对象同时保留：

- `physical_dimensions_m`：数据库或实际结构尺寸；
- `effective_area_m2/effective_length_m/effective_volume_m3`：Provider 计算或数据库得到的有效磁参数；
- `window_width_m/window_height_m`、绕线柱和骨架壁厚：用于排布；
- `gap_m/gap_position`：气隙物理配置，不被当作漏感独立调节旋钮。

## 状态和来源

每个布局返回 `feasible`、`violations`、`status`、`model_status` 和 `provenance`。第三阶段结果保留 `data_status`、`synthetic`、`demo_only`、`engineering_approved`；真实数据库联合算例也明确 `engineering_approved=false`。

不能表达的模板返回 `UNSUPPORTED_GEOMETRY`，而不是转换为 PS。缺失波形时联合服务只做几何/可用的基础计算，损耗值保持 `null` 并返回诊断。
