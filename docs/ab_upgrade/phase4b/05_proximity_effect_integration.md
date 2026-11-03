# Phase 4B：邻近效应接入

## OpenMagnetics full 路径

`WindingLossService.openmagnetics_full` 将 Phase 3 `LayoutGeometry` 经 `MasGeometryAdapter` 转成磁性结构，并把 P1/P2 的电流波形映射到同一个电气 `Primary` 端口；P1、P2 不会作为两个独立变压器原边重复施加完整电流。

完整第三方调用为：

`provider.calculate_winding_losses(magnetic, processed_operating_point, temperature)`

返回的 per-winding 结果保留 `ohmic_w`、`skin_w`、`proximity_w`。只有三类分项都存在时，适配器才把总值标为 `status=ok`；缺少任一分项时是 `partial`，该分项进入 `unmodeled_mechanisms`，不补零。

## 缺少场数据的边界

当前项目没有自研逐导体局部外部磁场求解器，也没有 COMSOL 自动化。独立 `openmagnetics_skin` 入口不把 Phase 4A 一维漏磁场未经验证地当成导线局部邻近场，而是返回 `MISSING_FIELD_DATA` 警告和 `proximity_loss_w=null`。

如果未来需要使用自研场数据，必须将其明确标记为研究性模型，并记录场的空间采样、频率、参考方向和来源；不允许以零邻近损耗代替缺失计算。

## 实际结果

本阶段真实 benchmark 的 OpenMagnetics full 路径返回了非零 proximity 分项：

- PS：`1.31407545698134e-6 W`
- PSP：`1.76060547521484e-6 W`

这些是 PyOpenMagnetics/MKF 对当前 MAS/operating point 的研发原型结果，不是有限元或样机校核结论。
