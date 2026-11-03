# Phase 4B+ 输入逐字段对比

## 统一测试条件

脚本 `examples/phase4b_plus_verification.py` 重新生成同一份 PS/PSP 参数化结构、同一 operating point 和同一 MAS 输入，并实际调用 MKF 四条损耗路径。机器可读完整快照位于：

`docs/ab_upgrade/phase4b/verification/phase4b_plus_results.json`

| 字段 | Native Rdc | MKF ohmic/skin/proximity/full | 结论 |
|---|---|---|---|
| 温度 | 25°C | 25°C | 相同 |
| 基波频率 | 100 kHz | operating point 100 kHz | 相同 |
| Primary DC/RMS | 0.300000 / 0.3082207001 A | 同一 current waveform，processed RMS 0.3082207001 A | 相同 |
| Secondary DC/RMS | 0.900000 / 0.9110433579 A | 同一 current waveform，processed RMS 0.9110433579 A | 相同 |
| Primary AC RMS | 0.0707106781 A | 同一 harmonics | 相同 |
| Secondary AC RMS | 0.1414213562 A | 同一 harmonics | 相同 |
| 导线型号 | `Litz 1000x0.02 - Grade 1 - Double Served` | MAS wire 名称相同，Provider 运行时解析同一 DB 记录 | 相同 |
| 裸铜面积 | 3.14159265358979e-7 m² | MKF 从实际 Litz 数据库对象计算电阻 | 已由 ohmic 对照验证 |
| Rdc/m | 0.0544915964214477 Ω/m | 0.0544915964214477 Ω/m | 相同 |
| 温度系数/电阻率 | Provider per-meter API | MKF 同一温度输入 | 结果一致 |
| 并联数 | 1 | `numberParallels=1` | 相同 |

## 长度范围差异

Phase 4B native 路径包含 `WindingSpec.lead_allowance_m=0.15 m`。当前 MAS `turnsDescription` 只携带逐匝 `length`，没有把这段引线作为匝长或独立导体段传给 MKF。

| 结构/电气绕组 | 逐匝长度（MAS scope） | Native 长度 | Native 额外引线 |
|---|---:|---:|---:|
| PS Primary | 1.29208000 m | 1.44208000 m | 0.15000000 m |
| PS Secondary | 0.37306000 m | 0.52306000 m | 0.15000000 m |
| PSP Primary=P1+P2 | 1.49224000 m | 1.79224000 m | 0.30000000 m |
| PSP Secondary | 0.37306000 m | 0.52306000 m | 0.15000000 m |

因此 PS/PSP 不是在原始结果中使用完全相同的导线长度定义；这正是 native Rdc 高于 MKF ohmic 的主要原因。

## 利兹线制造字段

实际数据库记录为 Elektrisola `Litz 1000x0.02 - Grade 1 - Double Served`：成品外径范围为 0.940–1.051 mm，但 nominal 外径和绞距缺失。排布基准显式使用最大范围值 1.051 mm；这只影响参数化窗口排布，不被伪装成制造商标称值。
