# Phase 5D 输入参数映射

| 页面输入 | 内部对象 | 单位/规则 |
|---|---|---|
| 磁芯规格、材料、骨架 | `CoreGeometry` + MAS core | 外部名称查库；长度 m |
| 气隙 | `CoreGeometry.gap_m` | mm → m；不是漏感旋钮 |
| PS/PSP、Np/Ns、P1/P2 | `WindingSpec` + `WindingLayout` | P1+P2=Np；串联同向由既有 `build_layout` 建立 |
| 主绝缘、层绝缘、绕组间距 | `WindingLayout` / `InsulationGeometry` | mm → m；每个 PSP 界面独立 |
| 导线名称 | `WireGeometry` + `LitzWireSpecification` | 外部库必须真实存在；成品外径缺失则拒绝 |
| 绕组端电压波形 | `OperatingPointSnapshot.voltage_waveforms` | 不由 Vdc 自动推导 |
| 绕组电流波形/RMS | `current_waveforms` / `currents_rms_a` | 同一快照；RMS 不一致时返回诊断 |
| 磁化电感要求 | MAS `designRequirements.magnetizingInductance` | μH → H；用于第三方 core-loss 输入，不覆盖实际 Lm |

Phase 5D 的 Provider 适配采用 Phase 2/3 已验证的 ETD 54/28/19、3C95、Bobbin ETD 54 和 Elektrisola 利兹线作为外部演示选择。Provider 不可用时这些字段不会降级成同名虚构条目。

