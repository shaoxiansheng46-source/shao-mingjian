# 目标与约束

## 目标

对物理计算完整的候选，目标向量为：

```text
f1 = Pcore + Pcu_MKF_complete       [W]
f2 = layout.volume_m3               [m³]
```

`Pcu_MKF_complete` 来自 Phase 5A 的 MKF complete winding 路径；native Rdc 仅作为结果中的独立基线，不能再次叠加到 complete 损耗。第二目标是当前参数化绕组包络体积，不宣称已优化固定磁芯外包络体积。

## 研究性约束

约束遵守 pymoo 的 `g <= 0` 约定：

- 匝比：`abs(Np/Ns - target) - tolerance`；
- 峰值磁密：`Bmax - Bmax_max`；
- 励磁电感：`Lm_min - Lm`、`Lm - Lm_max`；
- 可选漏感目标上下界。

几何不可行在物理计算前淘汰。缺失指标使用正的 `unknown_constraint_sentinel`，因此不能被误判为可行。热模型尚未接入，不能成为通过条件。漏感来自 Phase 4A 研究性模型，除非另有 COMSOL/样机校核，工程状态始终为 `UNKNOWN`。

工程判定和研究性可行严格分开：本阶段没有任何候选会被标记为工程 `PASS`。
