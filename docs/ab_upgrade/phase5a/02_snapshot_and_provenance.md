# 输入快照、单位和追溯

## `EvaluationCandidate`

候选包含完整 `LayoutGeometry`、按电气绕组标识的
`LitzWireSpecification`、数据快照和源记录 ID。几何内部字段继续使用 SI 单位；
MAS/OpenMagnetics 原始对象不穿透统一编排层。

## `OperatingPointSnapshot`

快照至少包含：

- 原副边端电压、功率、频率、环境温度；
- 有符号原副边 RMS 电流；
- 原副边周期电流时序；
- 可选的原副边端电压时序；
- 拓扑、SPS 占空比和参考侧。

波形 RMS 会由 Phase 4B 波形分析实际计算，并与显式 RMS 对照。差异超过 2% 时返回
`CURRENT_WAVEFORM_RMS_MISMATCH`，不覆盖输入，也不继续伪造一致结果。

OpenMagnetics 入口只接受显式电压和电流波形。缺少电压波形时返回
`MISSING_VOLTAGE_WAVEFORM`，不会把直流母线电压当作高频绕组激励。

## 追溯字段

统一结果至少保存：

- `candidate_hash`、`excitation_hash`、`evaluation_key`；
- `data_snapshot`、`record_ids`、模型版本和 provider provenance；
- 每个子模型的 status、model、model_version、diagnostics；
- `result_grade`、`engineering_approved` 和未建模能力。
