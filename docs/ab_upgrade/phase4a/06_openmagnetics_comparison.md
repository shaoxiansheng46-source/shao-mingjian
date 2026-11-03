# 4A OpenMagnetics 对照

## 实际调用

当前隔离环境为 PyOpenMagnetics `1.7.35`，MKF commit `39b59172268f55fbcd72037b948622f21382b5c1`，MAS commit `0a7ba58f542049fd073041b3b5e4bac431ed6292`。

Provider 实际调用 `calculate_leakage_inductance(magnetic_json, frequency_hz, source_index)`。输入先经过 Phase 3 MAS 几何映射和磁芯处理，没有把当前结构简化为另一种模板。

| 结构 | 自研 native | OpenMagnetics Energy | 相对差异 |
|---|---:|---:|---:|
| PS | `0.818968 μH` | `19.053366 μH` | `95.7017%` |
| PSP | `0.361705 μH` | `7.824007 μH` | `95.3770%` |

两次第三方调用均为 `status=ok`，方法返回 `Energy`，并保留 per-winding 值和版本来源。

## 差异解释与处理

自研模型是等高径向一维均匀电流片，显式使用 `l(x)`、层边界和 RMS 储能；MKF 是窗口磁场/网格能量路径，使用 Binns-Lawrenson 等第三方场模型、完整逐匝几何和自身的电流/峰值归一化约定。两者的物理边界和离散方式不同，因此当前对照差异较大。

MKF 源码明确了漏感场能量积分和源电流归一化路径；其仓库的审查记录也提示过峰值/RMS 归一化需要通过 FEM/测量进一步确认。这里不通过乘固定系数强行拟合，也不把任一结果标记为真值。对照结果只用于下一阶段模型校准和问题定位。

完整输入、第三方返回和差异记录在 `.runtime/phase4a-leakage-benchmark.json`。当前未接入 NSGA-II，也未用第三方结果替换现有 Demo 漏感。
