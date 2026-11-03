# Phase 4B+ 根因与修复

## 已确认根因

### A：导线长度范围不同

代码证据：`WindingLossService._block_length()` 将逐匝长度和每个物理块的 `lead_allowance_m` 相加；默认值为 0.15 m。`MasGeometryAdapter` 的 `turnsDescription` 只发送每匝 `length`，未表达引线段。Provider 的 MKF ohmic 结果反推得到的有效长度恰好是逐匝长度：

- PS Primary：`0.006688712681 / (0.3082207001² × 0.0544915964) = 1.29208 m`
- PS Secondary：对应 `0.37306 m`
- PSP Primary：P1+P2 对应 `1.49224 m`

该证据解释了 native 基线高于 MKF ohmic 的全部差异。

### F：standalone proximity 与 complete 聚合范围不同

MKF standalone proximity 的 `windingLossesPerWinding` 为 `None`，但 per-turn 有 `lossesPerHarmonic`；适配器已修复为显式求和并标记 `aggregation_scope=windingLossesPerTurn`。complete winding 直接返回 per-winding proximity。两条实际 API 路径数值仍不同，暂不能证明是同一物理定义。

## 本次最小修改

只修改了 `backend/app/providers/openmagnetics/provider.py`：

1. 增加 per-turn 损耗分项的显式聚合。
2. standalone skin/proximity 缺少顶层标量时，不再误报缺失或转零。
3. 保留聚合范围和计数，便于追溯。

没有修改 `engine.py`、NSGA-II、前端或生产依赖，也没有用 MKF 值覆盖 native 值。

## 未解决项

standalone proximity 与 complete proximity 的差异仍需进一步阅读 MKF 版本源码或使用有限元/实验对标。当前软件只能把 complete 结果作为该完整 API 路径的结果，不能把 standalone proximity 当成 complete 的等价替代。
