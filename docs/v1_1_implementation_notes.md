# V1.1 增量实现说明

本版本在 V1.0 的 `evaluate_candidate`、候选目录、NSGA-II、任务快照和报告导出链上增加四项模型。原始 `SST_V1_4_Demo_Data/*.json` 未覆盖；新增数据位于 `SST_V1_4_Demo_Data/v1_1/`，并在结果中记录组合后的数据哈希。

## 使用

默认输入不带 `v1_1.enabled` 或设置为 `false` 时，沿用 V1.0 参考路径。启用后增加如下输入段：

```json
{
  "v1_1": {
    "enabled": true,
    "layout_mode": "PSP",
    "core_mode": "combination",
    "core_assembly_ids": ["DEMO_CORE_SET2_XL"],
    "gap": {"mode": "target", "target_mode": "lm_target", "Lm_target_H": 0.003},
    "external": {
      "mode": "external_allowed",
      "external_inductor_ids": ["DEMO_EXT_L_10UH"],
      "comparison_boundary": "system"
    }
  }
}
```

`inductance.leakage_mode` 也必须同步为 `external_allowed`。`gap.mode=search` 时可通过 `candidate_values_mm` 指定制造步进候选；未指定时使用磁芯条目中的范围和步进生成离散候选。

## 模型边界

- 气隙使用等效磁阻计算并按磁芯步进量化；不计算气隙边缘磁通附加损耗。
- P-S-P 使用 P1-S 和 S-P2 两个界面的分区磁场能量近似，不使用任意交错改善系数；两个界面电容只作为界面估算输出，不合并为端口电容。
- 组合磁芯使用独立的组合记录，不把单体参数直接按数量相乘；组合记录仍是虚构演示数据。
- 外置电感为单个跨工况离散器件，二次侧器件的电感折算采用匝比平方，损耗采用器件安装侧电流；超过目标上限时不允许负电感补偿。
- 热点模型没有建立，`Thotspot_est_C` 保持 `null`；变压器和外置电感使用合成热阻模型，结果持续标记 `synthetic` / `demo_only`。
