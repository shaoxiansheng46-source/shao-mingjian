# Phase 5D 回归报告

## 实际结果

- `pytest -q`：**54 passed**。
- 原有 Phase 2–4B+ 测试：包含在上述全量结果中，未新增失败。
- `backend/tests/test_phase5d_physical_api.py`：4 passed，覆盖 Provider 状态、无波形几何检查、PS 完整波形和 PSP 区块/串联关系。
- `.runtime/openmagnetics-venv/Scripts/python.exe examples/phase3_geometry_joint.py`：仍为 `passed`，PS/PSP 外部数据库联合基准可用。
- 使用隔离 Provider 实际调用 Phase 5D 适配器的外部 PS 算例：`status=ok`，第三方 `core_data`、`magnetizing_inductance`、`core_losses`、`winding_losses`、`ohmic_losses`、`geometry_call` 均为 `ok`；得到 Lm=970.3196 μH、Bmax=33.8616 mT、Pcore=0.103497 W、native 漏感=1.30389 μH、MKF complete 绕组损耗=0.038487 W。
- `python scripts/check_demo.py`：通过，默认回归 14400/34/2、无解与变量电压整数匝检查均通过。
- `python scripts/check_v11.py`：通过，联合气隙、整数匝、功率重算和质量无解检查均通过。

## 测试文件

`backend/tests/test_phase5d_physical_api.py` 使用明确标记的 `demo_fixture`，不把虚构数据当作第三方真实性证明；第三方真实性证据来自隔离环境实际调用日志。

