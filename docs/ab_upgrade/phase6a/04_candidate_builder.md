# CandidateBuilder 实现

`backend/app/optimization/phase6a/builder.py` 负责将 pymoo 字典变量转换为 `EvaluationCandidate`：

1. 将 pymoo 的 numpy 标量转换为 Python 标量，并检查整数与类别范围；
2. 从固定数据快照选择真实 `WireGeometry` 与 `LitzWireSpecification`；
3. 创建 `WindingSpec`，将 `Np/Ns` 作为电气匝数；
4. 通过 `build_layout` 生成 PS 或 `P1-S-P2` 的实际层、匝和坐标；
5. 写入 `P1+P2=Np`、串联同向、数据来源和工程可信度标识；
6. 返回 `candidate_hash`、布局快照和明确的几何违规原因。

因此间距、绝缘、线径、匝数或排布变化均会影响窗口检查、层数、平均匝长、导线长度、漏感积分输入和 MAS 几何。未支持的变量没有暴露给优化器。
