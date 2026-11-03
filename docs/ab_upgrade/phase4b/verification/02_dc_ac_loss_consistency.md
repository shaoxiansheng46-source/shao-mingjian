# Phase 4B+ DC/AC 损耗一致性

## 重新统一后的比较

| 结构 | Native（含引线） | Native（仅逐匝） | MKF ohmic | MKF complete |
|---|---:|---:|---:|---:|
| PS | 0.031122188702 W | 0.023561479699 W | 0.023561479699 W | 0.023562997200 W |
| PSP | 0.032934862555 W | 0.024597648303 W | 0.024597648303 W | 0.024599626958 W |

“Native（仅逐匝）”是独立校核脚本根据同一 `Rdc/m`、同一 RMS 电流和 MAS 逐匝长度计算的对照值，不是把 MKF 输出作为预期值。

## 结果判断

- PS：native 含引线比 MKF ohmic 高 `0.007560709003 W`，对应额外 `0.300000 m` 导线。
- PSP：native 含引线比 MKF ohmic 高 `0.008337214252 W`，对应额外 `0.450000 m` 导线。
- native 仅逐匝结果与 MKF ohmic 的绝对差小于 `1e-14 W`。
- MKF complete 比自身 ohmic 高：PS 增量约 `1.517501398e-6 W`，PSP 增量约 `1.978655359e-6 W`。
- 在同一长度、温度、RMS 和电阻定义下，MKF complete 均不低于其 ohmic/Rdc 基线。

因此原表中“完整交流损耗低于自研 Rdc 基线”是比较口径不一致造成的，不是已证明的负交流损耗。

## 电气分段

PSP 的 P1、P2 均使用同一个 Primary 电流波形，并在 native 中分别计算后串联累加；MKF MAS `functionalDescription` 仍只有一个 20 匝 Primary，物理 P1/P2 保留在 sections/layers/turns 中。没有发现将 P1/P2 当成两个独立原边重复施加电流的问题。
