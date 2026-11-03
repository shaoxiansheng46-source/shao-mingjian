# Phase 4B：集肤效应模型

## 已确认的第三方 API

实际安装的 PyOpenMagnetics 为 1.7.35，MKF commit 为 `39b59172268f55fbcd72037b948622f21382b5c1`。Provider 已验证并封装：

- `calculate_dc_resistance_per_meter(wire, temperature)`
- `calculate_skin_ac_resistance_per_meter(wire, current, temperature)`
- `calculate_skin_ac_factor(wire, current, temperature)`
- `calculate_skin_ac_losses_per_meter(wire, current, temperature)`
- `calculate_ohmic_losses(coil, operating_point, temperature)`
- `calculate_skin_effect_losses(coil, winding_losses, temperature)`
- `calculate_winding_losses(magnetic, operating_point, temperature)`

当前版本要求 current 描述包含 `harmonics` 和 `processed`，其中 `processed.label`、`processed.effectiveFrequency` 等字段由 `analyze_current_waveform()` 产生。Provider 不向上层暴露原始第三方对象。

## 结果定义

MKF 的独立 skin 阶段返回的是加入集肤阶段后的 `windingLosses`，而不是单独的 `skinEffectLosses` 标量。因此适配器以：

\[
P_{skin}=P_{after\ skin}-P_{ohmic}
\]

得到真实增量；缺少这两个值时返回 `SKIN_LOSSES_FAILED`，不转换为零。

`openmagnetics_skin` 的 `value` 保持 `null`，因为此入口只保证第三方集肤阶段，外部邻近效应没有同一结果中的可追溯分项。它返回实际 `ohmic_loss_w`、`skin_loss_w`，并用 `MISSING_FIELD_DATA` 警告标记“不是完整绕组总损耗”。

独立基准的利兹线实际 per-meter 结果（25°C、实际处理过的周期电流）为：

| 项目 | 实际返回 |
|---|---:|
| Rdc | 0.0544915964214477 Ω/m |
| Rac（skin API） | 0.0544923654873939 Ω/m |

不能据此推断所有利兹线或所有几何的交流损耗；绞合内部电流分布和外部邻近场的覆盖范围必须以第三方模型返回和输入适用性为准。
