# Phase 5A 统一候选结构性能评估

## 目标

Phase 5A 新增一个独立的 `UnifiedEvaluationService`，把一个明确的
`EvaluationCandidate` 与一个明确的 `OperatingPointSnapshot` 交给现有的
Phase 3 几何、Phase 4A 漏感和 Phase 4B 绕组损耗服务。它不是新的优化器，
也不替换 `backend/app/core/engine.py`。

代码位置：

- `backend/app/evaluation/models.py`
- `backend/app/evaluation/service.py`
- `backend/tests/test_phase5a_unified_evaluation.py`
- `examples/phase5a_unified_evaluation.py`

## 编排顺序

1. 校验并冻结候选结构和运行点快照。
2. 计算参数化结构状态；不可排布时停止后续物理调用。
3. 使用同一份电流波形调用 `WindingLossService`。
4. 使用同一份有符号 RMS 电流调用 `LeakageInductanceService`。
5. 可选调用 `JointCalculationService`；第三方不可用或输入不足时返回结构化状态。
6. 汇总显式体积、质量、电流密度和漏感约束；不调用热模型。

每个结果保存候选哈希、激励哈希和编排键。任何候选、波形、模型或数据快照变化都会得到不同的键。

## 结果等级

`synthetic`、`demo_only` 或未审核的候选统一返回 `result_grade=demo_only`。
非 synthetic 的混合计算返回 `hybrid_unqualified` 或 `reference_only`，不会自动变成
`engineering_qualified`。所有结果都保留 `engineering_approved=false`。
