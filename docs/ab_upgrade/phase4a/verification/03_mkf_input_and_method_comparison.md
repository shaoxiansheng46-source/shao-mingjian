# MKF 输入与方法对照

## 实际第三方环境

本次运行使用隔离环境：

- PyOpenMagnetics `1.7.35`；
- MKF commit `39b59172268f55fbcd72037b948622f21382b5c1`；
- MAS commit `0a7ba58f542049fd073041b3b5e4bac431ed6292`；
- 数据库对象：Ferroxcube `3C95`、`ETD 54/28/19`、`Round 0.5 - Grade 1`；
- 频率：100 kHz；参考端口：Primary；
- 调用：`OpenMagneticsProvider.calculate_leakage_inductance()`，底层 `calculate_core_data()` 后调用 PyOpenMagnetics `calculate_leakage_inductance(magnetic, frequency_hz, source_index)`。

所有真实数据保留 `data_status=external_database`、`synthetic=false`、`demo_only=false`、`engineering_approved=false`。

## 输入结构

`MasGeometryAdapter.to_magnetic()` 生成并记录在 `verification.json` 和 `ps_psp_input_diff.json` 中：

- `core.functionalDescription`：磁芯类型、材料、`gapping`、stack 数；
- `coil.functionalDescription`：PS 为 Primary 20 匝、Secondary 5 匝；PSP 同样是 Primary 20 匝、Secondary 5 匝；
- PSP 的 P1/S/P2 保留在 `sectionsDescription`、`layersDescription`、`turnsDescription`；
- `sstElectricalWindingMap` 为 `P1 -> Primary`、`S -> Secondary`、`P2 -> Primary`；
- `sstElectricalConnections` 明确为 P1/P2 同向串联且 `P1+P2=Np`；
- 坐标、尺寸、长度和气隙均为 SI 米。

这点很重要：不能把 PSP 的两个物理分段再次写成两个独立电气绕组，否则 MKF 会把 10 匝段当成励磁主绕组。当前映射已避免该错误。

## 结果

| 结构 | 自研 1-D | MKF `Energy`（显式几何） | MKF/自研 | 相对差异 |
|---|---:|---:|---:|---:|
| PS | 0.818968 μH | 19.053366 μH | 23.26× | 95.7017% |
| PSP | 0.361705 μH | 7.824007 μH | 21.63× | 95.3770% |

PSP 还进行了控制实验：去掉显式 `groups/sections/layers/turnsDescription`，让 provider 走 PyOpenMagnetics 的 `wind()` 默认排布，返回 7.264712 μH；保留 Phase 3 显式几何时返回 7.824007 μH。PS 的单层控制值为 19.053366 μH，与显式值相同。这个实验说明显式几何至少对 PSP 的 MKF 结果有影响，但它不是把两种模型变成同一物理模型的证明。

代码证据：`backend/app/providers/openmagnetics/provider.py::_resolve_coil()` 在四类几何数组都存在时原样保留数组；缺失时才调用第三方 `wind()`。`backend/app/geometry/mas_geometry.py::_electrical_winding_view()` 将 PSP 的电气 Primary 合并为总匝数，同时保留物理分段映射。

## 方法差异

MKF 源码的漏感路径包括窗口磁场计算和场能量积分，公开源码位置：

- [MKF LeakageInductance.cpp](https://github.com/OpenMagnetics/MKF/blob/main/src/physical_models/LeakageInductance.cpp)
- [MKF magnetic-field models](https://openmagnetics.github.io/MKF/models/magnetic-field/)

自研模型是等高、径向 1-D、均匀轴向电流片，并用实际平均匝长近似端部周长。MKF 使用其自身的场模型、离散/网格积分、逐匝几何处理和 Energy 归一化路径。公开实现中源电流使用峰值/谐波相关量；自研接口使用周期平均储能和 RMS 电流。因此两者的绝对值不能直接当作同一公式的两个实现。

## 不能从当前结果推出的结论

- 不能说 MKF 一定正确，也不能说自研值应乘 22；
- 不能把 MKF 与默认 `wind()` 控制值混称为 Phase 3 几何结果；
- 不能只凭返回 `status=ok` 宣称已达到工程精度；
- 需要 COMSOL 或实测短路试验确定端部场、参考电流归一化和几何细节对绝对值的影响。
