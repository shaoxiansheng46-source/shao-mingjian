# Phase 5A 基准与回归

独立入口：

```powershell
python examples/phase5a_unified_evaluation.py
```

该入口使用当前演示数据库的 `DEMO_CORE_L` 与 `DEMO_LITZ_2000x0p1`，并明确保留
`synthetic/demo_only/engineering_approved=false` 标识。它实际生成 PS 结构，使用
20/5 匝和 1/-4 A 的有符号 RMS 激励，调用现有漏感和绕组损耗服务；OpenMagnetics
只在运行时可用且显式提供完整波形时调用。

新增测试：

```powershell
pytest -q backend/tests/test_phase5a_unified_evaluation.py
```

覆盖内容：

- 同一候选/同一激励的确定性键；
- 修改激励后的快照失效；
- PS/PSP 原边串联分段只聚合一次；
- 显式 RMS 与波形 RMS 不一致时阻断；
- OpenMagnetics 不可用时不回退到零值；
- 不可排布结构停止子模型调用；
- 结构化约束和热模型未实现状态。

本阶段不把新编排层接入 NSGA-II 或前端任务流。
