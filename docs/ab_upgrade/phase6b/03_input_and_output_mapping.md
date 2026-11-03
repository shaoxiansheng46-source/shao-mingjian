# 输入、变量和结果映射

## 输入映射

| 页面字段 | 内部字段 | 说明 |
|---|---|---|
| 原/副边绕组端电压采样 | `OperatingPointSnapshot.voltage_waveforms` | 明确的绕组端波形，不从母线电压推导 |
| 原/副边电流采样 | `current_waveforms` | 用于真实绕组损耗；RMS 由采样计算并带符号 |
| 频率、功率、环境温度 | `frequency_hz/power_w/ambient_c` | SI/摄氏度输入边界 |
| Np、Ns、P1 | `DesignVariableSpace` | 整数变量；PSP 要求 P1+P2=Np |
| PS/PSP | `layout` Choice | 通过 Phase 3 `CandidateBuilder` 生成实际块 |
| 气隙和磁芯间隙 | `*_bounds_m` | 按制造步进量化 |

首版固定磁芯、骨架和一条真实导线。请求仍保留导线选择字段，但为避免把未加载的第二条记录伪装成可选项，原副边必须选择同一条已加载真实导线。

## 结果映射

每个候选来源于一个统一 `PhysicalDesignCase`、一个统一 `OperatingPointSnapshot` 和一个结构快照。目标为：

`[Pcore + Pcu_complete, winding_envelope_volume]`

未完成物理计算的候选使用明确的失败状态和无效目标值，绝不以零或 synthetic 值进入 Pareto。结构 SVG 直接读取 `layout_snapshot.blocks` 的径向/轴向坐标、匝数和平均匝长。

## 兼容性

旧页面继续使用既有静态数据接口和 `/api/v1.4`、`/api/v1.5`。Phase 6B 脚本独立挂载，不改变旧页面的任务状态，也不读旧版任务文件。
