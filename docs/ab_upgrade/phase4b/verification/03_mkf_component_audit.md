# Phase 4B+ MKF 分项审计

## 实际 API

本次使用同一 processed operating point 和同一 MAS 几何调用：

- `calculate_ohmic_losses`
- `calculate_skin_effect_losses`
- `calculate_proximity_effect_losses`
- `calculate_winding_losses`

PyOpenMagnetics 1.7.35 的 standalone skin/proximity 返回结构不总是在顶层提供独立标量。适配器现在保留原值，必要时从 `windingLossesPerTurn` 的 `losses` 或 `lossesPerHarmonic` 求和；缺少分项时仍报错，不补零。

## PS 分项

| 电气绕组 | ohmic | skin | proximity |
|---|---:|---:|---:|
| Primary | 0.006688712681 W | 9.440099913e-8 W | 1.014617453e-6 W |
| Secondary | 0.016872767018 W | 1.090249419e-7 W | 2.994580038e-7 W |
| 合计 | 0.023561479699 W | 2.034259410e-7 W | 1.314075457e-6 W |

合计正好为 `0.023562997200 W`，与 MKF complete 一致。

## PSP 分项

| 电气绕组 | ohmic | skin | proximity |
|---|---:|---:|---:|
| Primary=P1+P2 | 0.007724881285 W | 1.090249419e-7 W | 1.504450612e-6 W |
| Secondary | 0.016872767018 W | 1.090249419e-7 W | 2.561548630e-7 W |
| 合计 | 0.024597648303 W | 2.180498838e-7 W | 1.760605475e-6 W |

合计正好为 `0.024599626958 W`，与 MKF complete 一致。

## standalone 与 complete 的限制

- standalone skin 的结果与“skin 阶段累计值减 ohmic”一致。
- standalone proximity 实际从 per-turn 返回约 `5.200303767e-7 W`（PS）和 `4.007454165e-7 W`（PSP）。
- complete winding 的 per-winding proximity 则为上表中的 `1.314075457e-6 W`（PS）和 `1.760605475e-6 W`（PSP）。

这两条 MKF API 路径在当前版本下没有得到一致 proximity 总量。两者原始结果均已写入 JSON，未用比例系数或 complete 值覆盖 standalone 值；该差异仍标为未解决的第三方 API/模型路径问题。
