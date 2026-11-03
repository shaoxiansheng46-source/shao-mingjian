# 演示案例

## PS/PSP 网页优化案例

输入文件：[phase7_demo_request.json](../../examples/phase7_demo_request.json)。

固定真实数据：ETD 54/28/19、3C95、Bobbin ETD 54、Elektrisola Litz 1000x0.02。工作点为 100 V/25 V、100 kHz、1000 W，波形显式输入，Np/Ns=20/5，严格匝比容差 ±5%。

该案例允许 PS/PSP 选择、P1=10/P2=10、气隙和磁芯余量步进搜索。它用于网页 API `/api/v1.6/optimizations`，不包含预存结果。

## 命令行真实变量基准

```powershell
$env:PYTHONPATH=(Resolve-Path '.runtime\openmagnetics-venv\Lib\site-packages').Path
python examples/phase6a_mixed_optimization.py --population 16 --generations 4 --max-evaluations 64 --seed 20261104 --turns-ratio-tolerance 0.05 --np-min 20 --np-max 24 --ns-min 5 --ns-max 6
```

该命令直接调用真实 Provider 和 Phase 5A 统一评估，不使用 synthetic 查表。需要 PS/PSP 覆盖时使用输入文件的固定 20:5、P1=10 配置。
