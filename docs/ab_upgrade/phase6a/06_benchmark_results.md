# 小规模真实基准

执行命令（在仓库根目录）：

```powershell
$env:PYTHONPATH=(Resolve-Path '.runtime\openmagnetics-venv\Lib\site-packages').Path
python examples/phase6a_mixed_optimization.py --population 4 --generations 2 --max-evaluations 12 --output .runtime/phase6a_smoke4.json --csv .runtime/phase6a_smoke4.csv
```

实际执行结果：状态 `completed`，8 次实际评估，8 个唯一候选，5 个物理计算成功，3 个窗口/排布淘汰，2 个研究性可行，1 个 Pareto 点，缓存命中 0。Provider 为 PyOpenMagnetics 1.7.35，磁芯为 `ETD 54/28/19`、材料 `3C95`，导线为 `Litz 1000x0.02 - Grade 1 - Double Served`。

唯一 Pareto 点为 `Np=18, Ns=5` 的 PS，PS 中 `P1/P2` 被规范化为 `0/18`；量化后的间距为 `1.4 mm`、磁芯余量为 `0.6 mm`，`Pcore=0.139878 W`、`Pcu_complete=0.039869 W`，总损耗为 `0.179747 W`，绕组包络体积为 `1.52504e-6 m³`。另一个研究性可行候选被非支配排序淘汰；所有候选的真实几何快照均被保存。

另外对真实 Provider 单独执行了 PSP 候选 `Np=20, Ns=5, P1=10, P2=10`：状态 `research_feasible`，`Lm=970.3196 µH`、`Bmax=33.8616 mT`、`Pcore=0.103497 W`、`Pcu_complete=0.038690 W`、Phase 4A 漏感 `0.717590 µH`；MAS/Phase 5A 实际块为 `P1:10, S:5, P2:10`。该结果不是固定表值，而是一次真实评估台账记录。

该示例为了让小随机种群能够展示可行前沿，显式使用研究性匝比容差 `0.5`；工程任务应按实际电气设计重新设置更严格容差。上述结果不是工程认证结论，`engineering_status` 仍为 `UNKNOWN`。
