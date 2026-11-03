# Phase 2：独立基准结果

## 执行方式

基准入口：`examples/openmagnetics_benchmark.py`。

```powershell
.runtime/openmagnetics-venv/Scripts/python.exe examples/openmagnetics_benchmark.py --output .runtime/openmagnetics-benchmark.json
```

本次实际退出状态为 0，JSON `status=passed`。脚本不导入 SST 优化器，不使用预存方案。

## 实际选择的数据库对象

- 材料：Ferroxcube `3C95`，密度 `4800 kg/m³`，Curie 温度 `215 °C`；
- 磁芯：`ETD 54/28/19`；
- 线材：Elektrisola `Round 0.5 - Grade 1`，IEC 60317，导体直径 `0.0005 m`，外径约 `0.000524 m`；
- 骨架：`Bobbin ETD 54`。

## 实际计算结果

固定输入包括：20 匝原边、5 匝副边、0.1 mm subtractive gap、100 kHz、100/25 V 端电压波形和明确电流波形。

| 项目 | 实际结果 |
|---|---:|
| Ae | `2.799884090461257e-4 m²` |
| le | `0.12937894574793482 m` |
| Ve | `3.622460518402928e-5 m³` |
| 励磁电感 | `0.0009703195771705127 H` |
| 磁芯损耗，IGSE | `0.21293404491359452 W` |
| B 峰值 | `0.044990745674312514 T` |
| 估算最高磁芯温度 | `28.812407657063808 °C` |
| 完整绕组损耗 | `0.04785233148346702 W` |
| 纯欧姆绕组损耗 | `0.04453555479945645 W` |

## 变化趋势检查

- 原边匝数 20 → 40：电感 `0.0009703196 H → 0.0038812783 H`，比值 `4.0`；
- 气隙 0.1 → 0.2 mm：电感 `0.0009703196 H → 0.0005978729 H`；
- 电流整体加倍：欧姆损耗 `0.04453555 W → 0.17814222 W`，比值 `4.0`；
- 频率 100 → 200 kHz：IGSE 结果 `0.21293404 W → 0.14800022 W`，计算值发生变化；该项只验证调用对频率敏感，不强行断言单调性。
- 相同输入重复计算：两次磁芯损耗完全一致到脚本容差内。

气隙反求 API `calculate_gapping_from_number_turns_and_inductance` 也被实际调用。当前版本以本基准的精简 MAS 输入调用时返回 `Bad optional access`，Provider 将其保存为 `GAP_SOLVER_FAILED` 且 `value=null`；这被基准中的“no silent fallback”检查判定为通过。已成功验证的是带实际气隙输入的 `calculate_inductance_from_number_turns_and_gapping` 及其气隙变化趋势，反求接口所需的额外完整字段将在后续适配中补齐。

## 负例

非法材料名 `__not_a_real_material__` 和非法磁芯名 `__not_a_real_core__` 实际返回 lookup 错误；缺匝数的绕组和不支持的 `NOT_A_MODEL` 实际返回结构化错误。仅有 DAB 直流母线电压或缺少端电压/电流波形时，适配器返回输入诊断，结果为 `null`，没有伪造计算。

完整 JSON 由命令生成在 `.runtime/openmagnetics-benchmark.json`；该目录被 git 忽略，文档中的数值来自该次实际运行。
