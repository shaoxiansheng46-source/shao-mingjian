# 4A 实现映射

## 新增代码

| 功能 | 代码位置 | 说明 |
|---|---|---|
| 统一服务 | `backend/app/leakage/service.py` | `LeakageInductanceService.calculate()` |
| 导出 | `backend/app/leakage/__init__.py` | 暴露服务接口 |
| OpenMagnetics Provider 对照 | `backend/app/providers/openmagnetics/provider.py` | 新增 `calculate_leakage_inductance()`，先解析并处理磁芯，再调用 PyOpenMagnetics |
| 独立真实基准 | `examples/phase4a_leakage_benchmark.py` | 从真实数据库构造 Phase 3 PS/PSP，运行自研和第三方调用 |
| 单元测试 | `backend/tests/test_leakage_phase4a.py` | 闭式解、分段、参考侧、敏感性、异常和范围测试 |

## 服务输入

```python
LeakageInductanceService(provider=None).calculate(
    layout,
    model="native_basic" | "native_sectional" | "openmagnetics_comparison",
    currents_rms={"Primary": 1.0, "Secondary": -4.0},
    reference_port="primary",
    frequency_hz=100_000,
)
```

输入电流可以使用 PSP 的电气名称 `Primary/Secondary`，也可以使用物理分段名称 `P1/S/P2`。服务将 P1/P2 绑定到同一串联电流，并检查两段电流一致。

## 服务输出

输出包括 `value/unit`、参考端口、模型和版本、能量、输入电流、匝数、分区能量/漏感贡献、假设、不确定性说明和诊断。所有内部长度、面积、能量和电感使用 SI 单位。

`openmagnetics_comparison` 同时返回 `native_sectional` 数值和 Provider 的第三方返回。第三方失败时保留明确状态，不把失败改成零，也不覆盖自研值。

## 与旧系统的边界

没有修改 `backend/app/core/engine.py`、现有 NSGA-II、前端或生产依赖。旧版 Demo 仍使用自己的 `DEMO_PS_1D`/PSP 漏感路径；4A 通过独立服务和脚本验证，尚未接入优化器。
