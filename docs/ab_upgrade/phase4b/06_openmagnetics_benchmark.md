# Phase 4B：OpenMagnetics 联合基准

## 运行方式

使用隔离环境执行：

```powershell
.runtime\openmagnetics-venv\Scripts\python.exe examples\phase4b_litz_benchmark.py --output .runtime\phase4b-litz\benchmark.json
```

脚本在运行时查询数据库、建立实际 PS/PSP 几何、生成 64 点周期波形，并调用 Provider；没有读取预存物理结果。研究性排布余量写在脚本的 `WindingLayout` 中，保持窗口可行性检查可追溯。

## 运行时环境和调用

| 项目 | 实际值 |
|---|---|
| PyOpenMagnetics | 1.7.35 |
| MKF commit | `39b59172268f55fbcd72037b948622f21382b5c1` |
| MAS commit | `0a7ba58f542049fd073041b3b5e4bac431ed6292` |
| 数据库 | 1073 材料、2107 磁芯、4340 导线 |
| 真实利兹线 | Elektrisola `Litz 1000x0.02 - Grade 1 - Double Served` |
| 实际调用 | 数据库查询、`calculate_dc_resistance_per_meter`、`calculate_skin_ac_resistance_per_meter`、`calculate_ohmic_losses`、`calculate_skin_effect_losses`、`calculate_winding_losses` |

## 结果（25°C，100 kHz，研究性波形）

| 结构 | native_dc | OpenMagnetics full | ohmic | skin | proximity |
|---|---:|---:|---:|---:|---:|
| PS | 0.0311221887019918 W | 0.0235629971999140 W | 0.0235614796985160 W | 2.03425941039377e-7 W | 1.31407545698134e-6 W |
| PSP | 0.0329348625552697 W | 0.0245996269581473 W | 0.0245976483027882 W | 2.18049883818373e-7 W | 1.76060547521484e-6 W |

PSP 的 native 原边电气对象包含 `blocks=["P1", "P2"]`，并以串联电阻和损耗聚合；完整第三方调用使用同一 `Primary` 电气激励，不重复计入 P1/P2。

机器可读摘要位于 `docs/ab_upgrade/phase4b/benchmark_results.json`；完整运行输出仍由脚本写入指定的 `.runtime` 路径。
