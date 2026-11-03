# 回归测试与执行记录

## 本次实际执行

| 检查 | 结果 |
|---|---|
| `pytest -q` | `24 passed` |
| PS/PSP MAS 映射和奇数匝测试 | 通过；包含总匝数守恒、P1/P2 串联元数据、21 匝分配、双绝缘接口 |
| 错误 P1/S/P2 激励绑定测试 | 通过；返回 `WINDING_EXCITATION_BINDING_MISMATCH` |
| `examples/phase3_geometry_joint.py` | `status=passed`；真实 OpenMagnetics 计算全通过 |
| `examples/ps_psp_consistency.py` | `status=passed`；输入差异、独立磁阻、B/铁损一致性全通过 |
| 独立磁阻与 OpenMagnetics | `0.62345%` 差异，低于 1% |
| `python scripts/check_demo.py` | 已执行；默认 Demo 回归通过 |
| `python scripts/check_v11.py` | 已执行；V1.1 回归通过 |
| `node --check frontend/app.js` | 已执行；前端未修改且通过 |

## 输出证据

- 完整输入、递归差异、独立公式和实际 Provider 结果：`ps_psp_input_diff.json`；
- 联合计算完整报告：`.runtime/phase3-geometry-joint.json`；
- 修复代码：`backend/app/geometry/mas_geometry.py`、`backend/app/geometry/joint.py`；
- 测试：`backend/tests/test_geometry_phase3.py`、`backend/tests/test_joint_phase3.py`。

## 未执行/不在本专项范围

- 未修改和未重新实现旧版 `engine.py`、NSGA-II 或前端业务；
- 未进行 COMSOL、3D 有限元、生产工程认证或安全标准合规校核；
- 未把 PyOpenMagnetics 结果接入现有 NSGA-II；
- 未声称热点或气隙边缘附加损耗达到工程验证精度。
