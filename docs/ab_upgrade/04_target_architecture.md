# 04 A+B 目标技术架构

本架构只作为第二阶段及以后实施依据。第一阶段不改现有 `backend/`、`frontend/` 或 `requirements.txt`。

## 1. 设计目标

- 保留当前 Demo 计算路径和参考结果；
- 让优化器只依赖稳定的项目服务接口；
- 将 OpenMagnetics 作为可替换 provider，而不是散落在 evaluator 中的直接调用；
- 同一候选在需要时可同时得到 Demo、OpenMagnetics 和后置校核结果；
- 每个数字都带单位、来源、模型版本、适用范围和错误状态；
- 外部引擎不可用或不适用时明确降级/阻断，不产生伪造工程结论。

## 2. 分层结构

```text
frontend (中文工程工作台)
        |
FastAPI application / task repository / report exporter
        |
Design Orchestrator
  - request normalization
  - provider selection
  - candidate cache key
  - progress/cancel/result provenance
        |
Domain services (stable ports)
  MagneticCoreService   GeometryService      ElectromagneticService
  CoreLossService       WindingLossService   LeakageService
  ThermalService        DesignConstraintService
  OptimizationService
        |
Provider adapters
  DemoProvider (current engine; default regression)
  OpenMagneticsProvider (PyOM/MKF; optional)
  ExternalValidationProvider (COMSOL/FEM; later)
        |
Data adapters
  current demo JSON <-> internal SI <-> MAS JSON
  source/version/license/provenance registry
```

优化器依赖 domain service ports；它不导入 PyOpenMagnetics、MKF C++ 类型、MAS 生成的 C++ binding 或 MVB 类。

## 3. 运行时流程

1. 前端提交 `DesignRequest`，API 做 schema、范围、模式和数据来源校验。
2. `InputNormalizer` 把 UI 单位转成 SI，补齐兼容默认值，并生成 canonical JSON hash。
3. `DataRegistry` 根据 `provider`、数据版本、模型版本和可用性返回 core/material/wire/insulation records。
4. `GeometryService` 生成单体、组合磁芯及 PS/PSP 绕组结构；保留每个 block 的空间、绝缘、引线和质量。
5. `ElectromagneticService` 根据 DAB-SPS 工作点得到波形、B、Lm、漏感和总串联电感。
6. `CoreLossService`、`WindingLossService`、`ThermalService` 各自返回带来源的 metric；热点未知就返回 null 和 capability flag。
7. `DesignConstraintService` 返回结构化 constraint residuals，而不是只剩一个字符串原因。
8. `OptimizationService` 对离散/混合变量执行枚举或 NSGA-II；候选 evaluator 可同时调用不同 provider。
9. `ResultRepository` 保存输入快照、data/model/engine provenance、seed、候选统计、可行池、Pareto 和失败原因。
10. 报告和 UI 明确显示“可行池”和“Pareto 前沿”两个集合；CAD/COMSOL 作为异步后置任务。

## 4. Provider 选择策略

| 模式 | 默认 | 允许的 provider | 结果等级 |
|---|---|---|---|
| Demo 回归 | `demo` | `DemoProvider` | `demo_only` |
| OpenMagnetics 基准 | `openmagnetics_reference` | `OpenMagneticsProvider` | `reference_only`，未通过项目验证前不可标工程可信 |
| 混合设计 | `hybrid` | OpenMagnetics 提供基础磁芯/损耗，B 类服务保留 SST 结构/约束 | `hybrid_unqualified`，逐 metric 标 provider |
| 工程候选 | `engineering` | 仅审核真实数据 + 通过验证的 provider | 需明确 `engineering_qualified` 条件，不能自动给出 |

如果 `OpenMagneticsProvider` 不可用，只有 Demo 模式可以回退到 DemoProvider；用户明确选择 OpenMagnetics 或工程模式时应返回可解释错误。

## 5. 任务和缓存

候选缓存 key 至少包含：

```text
canonical_input_hash
data_snapshot_hash
model_registry_version
engine/provider/version
candidate_gene
operating_points_hash
seed (optimization only)
```

任何模型、排布、provider、输入、数据或约束变化都必须使旧计算失效。结果对象不可只用 candidate_id 作为 key，因为同一匝数结构在不同 provider/模型/工作点下的指标不同。

## 6. 兼容策略

- 保留 `backend.app.core.engine.evaluate_candidate()` 作为 `DemoProvider` 的实现入口，先包在 adapter 里再迁移。
- 现有 API `/api/v1.4/...` 保持兼容，增加 `/api/v2/...` 或版本化 payload；旧客户端可继续只请求 Demo。
- 现有 JSON 原字段不覆盖；MAS 适配字段写入独立 normalized snapshot。
- `v1_1` 兼容默认值继续有效；新 provider/模型显式写入结果。
- report/export 同时保留 raw input、normalized input、provider provenance 和 limitations。

## 7. 失败处理

统一错误类型：

- `InputValidationError`：用户输入/模式不合法；
- `DataUnavailableError`：数据缺失、版本或许可证不可用；
- `ModelApplicabilityError`：波形/频率/温度/结构超出模型适用范围；
- `GeometryInfeasibleError`：窗口、绝缘、层数等排布失败；
- `CalculationError`：第三方引擎计算失败；
- `ConstraintViolation`：候选已计算但不满足工程约束；
- `OptimizationCancelled` / `OptimizationNoFeasible`：任务控制状态。

每个候选可以失败，但失败 reason 必须带 service、code、message、候选基因和可选 residual；第三方异常不能被转换成“看起来可行”的默认值。

## 8. 目标架构的最大风险

OpenMagnetics 的通用磁性模型和当前 SST 的系统目标粒度不同：MAS/MKF 可以给磁性元件描述和基础性能，但不天然提供当前的 P-S-P 分区能量、外置串联电感系统边界、SPS 多工况统一器件选择或项目级结果追溯。因此 A+B 的边界必须是“基础能力复用 + SST 结构/约束自研”，不能变成“全量替换”。
