# Phase 6A 优化架构

Phase 6A 新增 `backend/app/optimization/phase6a/`，不接管旧版 `backend/app/core/engine.py` 和旧版 NSGA-II。调用链为：

`pymoo individual → CandidateBuilder → Phase 3 build_layout → Phase 5A UnifiedEvaluationService → OptimizationLedger → Pareto`。

每个个体使用同一份 `PhysicalDesignCase`：真实磁芯、真实导线、工作点波形、数据快照和模型版本固定。`CandidateBuilder` 只生成结构，不复制物理公式；有效结构才进入 Phase 5A。OpenMagnetics 不可用时，外部物理算例直接失败，不回退到 synthetic。

`PhysicalDesignCase` 还保留 provider、数据库记录 ID、operating-point 快照和 `provider_inputs`。结果保留候选快照、激励哈希、评估键、所有唯一候选和所有评估尝试。

当前版本只把已经能够改变 Phase 3 实际坐标的变量暴露给优化器。绕组高度、绕组厚度和可变磁芯尚未被几何生成器可靠支持，因此在变量空间中明确列为 `unsupported_not_exposed`。
