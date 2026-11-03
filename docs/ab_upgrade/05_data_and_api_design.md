# 05 统一数据模型与计算接口

以下是目标接口设计，不是本阶段已经写入代码的 Python 抽象类。接口使用 SI 和项目内部类型，避免优化器绑定 MAS/MKF 内部结构。

## 1. 通用元数据

每个 request、candidate、metric 和 result 都应能回溯：

```json
{
  "data_mode": "demo | reference | engineering",
  "data_status": "synthetic | manufacturer | measured | derived",
  "result_grade": "demo_only | reference_only | hybrid_unqualified | engineering_qualified",
  "source": {"provider": "demo | openmagnetics | comsol", "repository": "...", "commit": "...", "record_id": "..."},
  "model": {"id": "...", "version": "...", "valid_range": {}, "assumptions": []},
  "units": "SI",
  "warnings": []
}
```

其中 `engineering_qualified` 不能由代码自动因为第三方返回数值就设置；必须由验证登记表和审核状态驱动。

## 2. 设计输入

```json
{
  "schema_version": "2.0",
  "project_id": "string",
  "data_mode": "demo",
  "topology": "DAB_SPS",
  "waveform": {"bridge_duty": 0.5, "modulation": "SPS", "current_mode": "system_sps"},
  "operating_points": [
    {
      "id": "rated",
      "V1_V": 800.0,
      "V2_V": 400.0,
      "P_W": 100000.0,
      "frequency_Hz": 20000.0,
      "ambient_C": 40.0
    }
  ],
  "requirements": {
    "reference_side": "primary",
    "series_inductance_H": {"target": 2e-5, "relative_tolerance": 0.1},
    "magnetizing_inductance_H": {"minimum": 5e-4, "target": null, "current_max_A": null},
    "current_density_A_per_mm2": {"primary_max": 3.0, "secondary_max": 3.0},
    "temperature_C": {"winding_max": 110.0, "core_max": 110.0, "winding_rise_max_K": 60.0},
    "envelope": {"volume_max_m3": 0.01, "mass_max_kg": 20.0},
    "insulation": {"rule_set_id": "DEMO_RULES_001"}
  },
  "structure": {
    "layout": "PS | PSP",
    "core_mode": "single | combination | both",
    "core_ids": [],
    "external_inductor": {"mode": "integrated | allowed", "ids": [], "boundary": "transformer_only | system"}
  },
  "search": {"Np_min": 10, "Np_max": 32, "Np_step": 1, "parallel_max": 2, "population": 100, "generations": 200, "seed": 20261009},
  "provenance": {"input_hash": "..."}
}
```

对外 API 可继续接受现有 V1.4/V1.1 字段，通过 `InputNormalizer` 转换；内部不再混用 `Vdc_V`、`fs_Hz`、`P_req_W` 和 MAS 命名。

## 3. 关键结果对象

```json
{
  "candidate_id": "stable-hash-of-canonical-gene-and-model",
  "gene": {"core_id": "...", "Np": 10, "Ns": 5, "wire_primary_id": "...", "wire_secondary_id": "...", "parallel_primary": 1, "parallel_secondary": 1, "layout_id": "...", "gap_m": 0.0001, "external_inductor_id": "..."},
  "geometry": {
    "core": {},
    "blocks": [{"name": "P1", "turns": 5, "layers": 1, "mean_turn_length_m": 0.1, "radial_start_m": 0.0, "radial_width_m": 0.01}],
    "interfaces": [{"left": "P1", "right": "S", "insulation_m": 0.002}],
    "volume_m3": 0.008,
    "mass_kg": 16.0
  },
  "electromagnetic": {"Lm_H": 0.003, "Lleak_H": 1.86e-5, "Lext_H_primary_ref": 1e-5, "Lseries_H": 2.86e-5, "Bpk_T": 0.1},
  "losses": {"core_W": 10.0, "winding_W": 30.0, "external_W": 2.0, "total_W": 42.0, "system_total_W": 44.0},
  "thermal": {"core_C": 70.0, "winding_C": 80.0, "external_C": 60.0, "hotspot_C": null, "hotspot_status": "not_available"},
  "constraints": [{"id": "temperature.winding", "value": 80.0, "limit": 110.0, "residual": -30.0, "status": "pass"}],
  "capabilities": {"fringing_loss": "not_modelled", "hotspot": "not_available", "dielectric_qualification": "not_available"},
  "provenance": {}
}
```

所有长度、面积和体积在内部都为 m、m²、m³；UI 可显示 mm、L、mm²，但不能把显示值直接送入 service。

## 4. 服务接口

接口下述为 Python-like contract，方法返回 domain DTO 或结构化错误：

```text
MagneticCoreService
  list_materials(query, context) -> list[MaterialRecord]
  list_cores(query, context) -> list[CoreRecord]
  get_processed_core(core_id, temperature_C, context) -> ProcessedCore
  calculate_gap(core, gap_spec, context) -> GapResult

GeometryService
  build_core(core_record, assembly_spec, context) -> CoreGeometry
  build_winding(core_geometry, winding_spec, context) -> WindingGeometry
  build_layout(core_geometry, winding_specs, layout_spec, context) -> LayoutGeometry

ElectromagneticService
  calculate_waveforms(request, layout, context) -> list[OperatingPointWaveform]
  calculate_magnetizing_inductance(core, coil, gap, context) -> InductanceResult

CoreLossService
  calculate(core, waveform_points, material, model, context) -> LossResult

WindingLossService
  calculate(winding_geometry, waveform_points, wire, model, context) -> LossResult

LeakageService
  calculate(layout_geometry, waveforms, context) -> LeakageResult

ThermalService
  calculate(losses, geometry, cooling, context) -> ThermalResult

DesignConstraintService
  evaluate(request, candidate_result, context) -> ConstraintReport

OptimizationService
  enumerate(request, evaluator, callbacks) -> OptimizationResult
  nsga2(request, evaluator, callbacks) -> OptimizationResult
```

各 service 的 `context` 必须包含 provider、data snapshot、model registry、适用范围、随机种子和取消信号；不能由 service 隐式读取全局数据库或环境变量。

## 5. MAS 适配边界

`MasAdapter` 只负责：

1. 现有输入 → MAS `inputs.designRequirements/operatingPoints`；
2. internal core/winding/layout → MAS `magnetic`；
3. MAS `outputs` → internal metric；
4. 字段、单位、schema、版本、来源和 unsupported field 的记录。

不允许 `OptimizationService` 直接读取 `mas["magnetic"]["core"]`。如果 MAS 无法表达某个 SST 结构，adapter 要返回 `unsupported_capability`，并由 B 类服务继续计算或明确阻断。

## 6. 错误与适用条件

所有模型输出带：`status=ok|out_of_range|unsupported|engine_error`、`valid_range`、`assumptions`、`warnings`。例如：

- 非 DAB-SPS 或非 50% 方波：Demo provider 继续 `unsupported_waveform`；
- 频率/温度/B 超出材料范围：`out_of_range`，不外推为工程结果；
- 气隙量化后不能满足 Lm/Im：`constraint_violation`；
- OpenMagnetics 依赖缺失：`provider_unavailable`，Demo 模式可选回退，OpenMagnetics 模式不静默回退；
- P-S-P 端口等效电容未定义：返回两个 interface estimates 和 `port_equivalent=null`。

## 7. 结果版本和可复算

结果必须至少保存：canonical input、normalized input、raw source record IDs、data file hashes/third-party commit、model IDs/versions、provider name/version、optimizer name/config、seed、candidate catalog hash、failure counts、feasible IDs、Pareto IDs 和 UI/report build version。这样第三方数据库更新也不会悄悄改变旧报告。
