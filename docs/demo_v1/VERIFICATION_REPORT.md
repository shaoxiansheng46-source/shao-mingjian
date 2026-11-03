# V1.0 联调与验证报告

## 自动回归

- `pytest -q`：67 passed。
- `python scripts/check_demo.py`：14400 候选、34 可行、2 Pareto，通过。
- `python scripts/check_v11.py`：通过。
- Python compileall：通过。
- `node --check`：app.js、physical.js、optimization.js、Phase 7 浏览器流程脚本均通过。

环境中的 PyOpenMagnetics 版本为 1.7.35，pymoo 版本为 0.6.2；真实 Provider 状态为可用，真实优化路径明确关闭 synthetic fallback。

## 真实变量优化基准

使用 ETD 54/28/19、3C95、真实利兹线、100 V/25 V、100 kHz、1000 W、显式波形、seed=20261104、严格匝比容差 ±5%，Np=20–24、Ns=5–6：

- 64 次评估，61 个唯一候选；
- 26 次真实物理成功，31 个几何淘汰，0 个物理失败，3 次缓存命中；
- 7 个研究性可行，3 个 Pareto；
- 运行时间约 14.9 s，平均候选计算约 0.254 s；
- 所有候选工程状态均为 UNKNOWN。

PS/PSP 覆盖基准固定 Np/Ns=20/5、P1/P2=10/10，48 次评估、39 个唯一候选、21 个研究性可行，PS 和 PSP 均实际生成并计算；PSP 示例漏感约 0.642–0.678 μH。该结果为研究性结果，不是实物真值。

## 真实 HTTP 联调证据

当前运行中的 8000 端口使用 `examples/phase7_demo_request.json` 完成了任务 `e694e26673d1`：

- 48 次评估、32 个唯一候选、16 次缓存命中、22 次真实物理成功、10 个几何淘汰、0 个物理失败；
- 22 个研究性可行方案、1 个 Pareto 方案；
- 全部候选中包含 17 个 PS 和 15 个 PSP；
- `/api/v1.6/optimizations/{id}/all`、`/feasible`、`/pareto` 返回数量分别为 32、22、1；
- Provider 可用、`synthetic_fallback=false`，JSON/CSV 导出返回 200。

浏览器自动点击未在 Codex Work 环境执行，因为本地浏览器控制被禁用；不能将 HTTP/API 检查冒充浏览器 E2E 通过。已提供可在本机安装 Playwright 后执行的 `scripts/phase7_browser_flow.mjs`。
