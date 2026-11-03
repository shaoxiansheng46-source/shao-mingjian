# Phase 2：MAS 数据适配设计

## 代码位置

- `backend/app/providers/openmagnetics/mas_adapter.py`
- `backend/app/providers/openmagnetics/models.py`
- `backend/app/providers/openmagnetics/provider.py`

## 输入边界

应用侧请求使用明确的字段名，适配器输出 MAS 风格的：

```text
{
  "inputs": {"designRequirements": ..., "operatingPoints": [...]},
  "magnetic": {"core": ..., "coil": ...}
}
```

适配器覆盖：磁芯类型/形状/材料、气隙、磁芯叠数、绕组名称、匝数、并绕数、导线名称、频率、端电压波形、绕组电流波形和环境温度。

## 单位关系

| 应用侧字段 | MAS/Provider 内部单位 | 转换 |
|---|---|---|
| `gap_mm` / `length_mm` | `length`，m | `mm × 1e-3` |
| `area_mm2` | m² | `mm² × 1e-6` |
| `frequency_khz` | `frequency`，Hz | `kHz × 1e3` |
| `magnetizing_inductance_uh` | `magnetizingInductance.nominal`，H | `µH × 1e-6` |
| waveform `time_s` | waveform `time`，s | 原样保留 SI |
| 温度 `ambient_temperature_c` | `conditions.ambientTemperature`，°C | 数值保留 |

适配器拒绝没有明确单位的负值、非数值和不等长波形。Provider 内部的第三方原始 dict 不向上层返回。

## DAB 与波形规则

- 直流母线电压不是绕组端电压；只有 `dc_bus_voltage` 时，适配器返回缺少端电压/电流波形诊断。
- `topology` 为 DAB 时还要求显式 `phase_shift_deg`、`phase_shift_rad` 或 `phaseShift` 之一。
- 不从电压比例、占空比或移相角自行构造“看似真实”的波形。
- 每个绕组必须提供 `voltage_waveform` 和 `current_waveform`，且 data/time 长度相等、至少两个采样点、时间非负且单调不减。

典型诊断包括：`MISSING_WAVEFORMS`、`MISSING_DAB_PHASE_SHIFT`、`MISSING_FREQUENCY`、`INVALID_WAVEFORM`、`MISSING_MAGNETIZING_INDUCTANCE`。

## 反向摘要

`MasAdapter.from_mas()` 只提取磁芯名称、材料、气隙长度、绕组名称/匝数/导线名称和工作点数量，作为结果追溯摘要，不把第三方 MAS 完整对象当作本项目公共数据模型。
