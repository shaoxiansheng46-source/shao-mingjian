# Phase 4B+ 回归报告

## 实际执行并通过

| 检查 | 结果 |
|---|---|
| `pytest -q` | 42 passed |
| `pytest -q backend/tests/test_winding_loss_phase4b.py` | 8 passed |
| `python scripts/check_demo.py` | passed；14400/34/2 回归一致 |
| `python scripts/check_v11.py` | passed |
| Phase 2 `examples/openmagnetics_benchmark.py` | passed |
| Phase 3 `examples/phase3_geometry_joint.py` | passed |
| Phase 4A `examples/phase4a_leakage_benchmark.py` | passed |
| Phase 4A+ `examples/phase4a_plus_verification.py` | passed |
| PS/PSP 一致性 `examples/ps_psp_consistency.py` | passed |
| Phase 4B 原始 benchmark | passed |
| Phase 4B+ 一致性脚本 | `passed_with_unresolved_mkf_proximity_path` |

Phase 4B+ 状态不是无条件“全部物理一致”：所有输入、Rdc、ohmic、skin 和 complete 聚合检查通过，但 standalone proximity 与 complete proximity 的第三方路径差异已明确保留。

## 可复现命令

```powershell
.runtime\openmagnetics-venv\Scripts\python.exe examples\phase4b_plus_verification.py
pytest -q
```

完整 JSON：`docs/ab_upgrade/phase4b/verification/phase4b_plus_results.json`。
