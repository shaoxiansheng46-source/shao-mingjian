# 测试报告

Phase 6A 新增测试：

```text
pytest -q backend/tests/test_phase6a_mixed_optimization.py
8 passed
```

覆盖整数/类别变量、非整数拒绝、PSP 分段守恒、串联同向、间距驱动坐标变化、PS/PSP 实际布局差异、窗口溢出、缓存命中、真实 Provider 不可用时不回退、pymoo 0.6.2 混合变量 NSGA-II 和无假 Pareto。

完整回归在 Phase 6A 完成后实际执行：`pytest -q` 为 **62 passed**（仅有既有 Windows `.pytest_cache` 权限警告）；`python scripts/check_demo.py` 通过（14400/34/2，含可变电压检查）；`python scripts/check_v11.py` 通过。真实 Provider 集成基准使用上文独立示例，不依赖测试夹具冒充第三方计算。
