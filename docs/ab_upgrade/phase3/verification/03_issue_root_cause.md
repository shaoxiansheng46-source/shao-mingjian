# 问题根因与最小修复

## 复现证据

专项前的真实 OpenMagnetics 调用返回：

- PS：`L=970.319577 μH`、磁芯损耗 `0.212934045 W`；
- PSP：`L=242.579894 μH`、磁芯损耗 `1.544904454 W`。

PSP 电感正好为四分之一，说明接口使用的是 10 匝分段而不是 20 匝串联原边。铁损约为 PS 的 7.26 倍，与“完整原边电压施加在半数匝数几何上”的输入错误相符。

## 根因

1. `MasGeometryAdapter` 将 P1、S、P2 作为三个 `functionalDescription` 电气绕组导出。P1/P2 虽然是实体分段，但在本结构中不是三个独立端口。
2. `calculate_inductance_from_number_turns_and_gapping` 没有应用应用层的串联关系元数据，只能按 MAS 电气绕组选择 P1，因此使用 10 匝。
3. PSP 的原有示例把激励拆成 P1/S/P2，并试图把原边电压减半；这仍然与“一个 20 匝串联 Primary 端口”的 MAS 表达不一致。
4. 磁芯损耗调用使用完整 `Primary` 工作点，但实体几何仍被映射为 P1 半匝数，导致 `V/N` 不一致。

## 修复

- 电气视图合并为 `Primary=20` 与 `Secondary=5`；
- P1/S/P2 只保留在 sections/layers/turns 和 `sstElectricalConnections` 中；
- PS 与 PSP 共同使用同一套完整端口工况，不再拆分端口电压；
- 联合服务增加激励名称绑定检查，错误映射直接返回明确输入错误；
- 增加独立 `Np²/Rm` 校核、输入快照和 PS/PSP 一致性测试。

没有写入相等结果、固定修正系数或预存电感/铁损值。修复后的数值均由当前安装的 PyOpenMagnetics 1.7.35 实际调用返回。
