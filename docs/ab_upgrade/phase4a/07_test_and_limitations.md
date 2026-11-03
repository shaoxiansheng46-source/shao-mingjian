# 4A 测试与限制

## 已执行

| 检查 | 结果 |
|---|---|
| `pytest -q backend/tests/test_leakage_phase4a.py` | 6 passed |
| `pytest -q backend/tests/test_phase4a_plus_verification.py` | 4 passed |
| 4A+ 独立验证 `examples/phase4a_plus_verification.py` | passed；12 checks |
| PS/PSP 输入一致性 `examples/ps_psp_consistency.py` | passed；励磁电感、磁密、磁芯损耗一致性通过 |
| Model A 手工闭式基准 | 通过，独立公式与服务一致 |
| PS 分段能量 | 通过；native_basic 与 sectional 一致 |
| PSP 分段能量 | 通过；P1/S/P2、双界面、分区贡献输出 |
| 间距/厚度/分段敏感性 | 通过；实际值发生变化 |
| 参考端口换算 | 通过；副边值按实际 RMS 电流归一化 |
| 不平衡安匝、零尺寸、不同高度 | 通过；明确拒绝或返回范围状态 |
| PyOpenMagnetics 漏感对照 | 通过真实调用；PS/PSP 均 `status=ok` |
| `pytest -q` 全量回归 | 34 passed |
| Phase 2 OpenMagnetics benchmark | passed |
| Phase 3 PS/PSP 联合计算 | passed |
| Demo 回归 `python scripts/check_demo.py` | passed；14400 candidates / 34 feasible / 2 Pareto |
| V1.1 回归 `python scripts/check_v11.py` | passed |
| 前端语法 `node --check frontend/app.js` | passed；前端未修改 |

## 尚未实现

- 三维端部漏磁、不同绕组高度、非平行绕组；
- 气隙边缘漏磁对绕组窗口场的耦合；
- 组合磁芯和多窗口/分柱结构；
- 基于论文完整 Rogowski 系数/叠加公式的复现；
- FEM、实物短路测试和参数标定；
- 通过一致性校准后接入 NSGA-II 或前端。

测试通过只证明实现与本阶段选定的一维解析模型一致。OpenMagnetics 对照调用成功只证明接口可运行，不能单独证明工程精度。
