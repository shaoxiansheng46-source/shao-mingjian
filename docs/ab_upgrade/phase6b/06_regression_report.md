# Phase 6B 回归报告

## 基线与结果

Phase 6B 在既有 Phase 5D/6A 工作区基础上增量实现。Phase 6B 增加请求边界和状态接口测试后，根目录 `pytest -q` 实际结果为 `66 passed`；其中原有 62 项回归仍通过。

保留的回归入口：

```powershell
pytest -q
python scripts/check_demo.py
python scripts/check_v11.py
python -m compileall -q backend examples
node --check frontend/app.js
node --check frontend/physical.js
node --check frontend/optimization.js
```

旧版 `/api/v1.4`、Phase 5D `/api/v1.5` 路由未删除；Phase 6B 仅新增 `/api/v1.6`。Phase 6A 仍通过 `Phase6AEvaluator` 和 `optimize_phase6a`，没有替换旧版 `engine.py` 或 synthetic NSGA-II。

## 需要重点观察的回归项

- Provider 不可用时不得生成真实 Pareto。
- synthetic 请求必须被 Phase 6B 阻断。
- 缺少电流或电压波形时不能把几何检查结果冒充完整损耗结果。
- 任务快照中的输入、结构、模型版本和 seed 与导出报告一致。
