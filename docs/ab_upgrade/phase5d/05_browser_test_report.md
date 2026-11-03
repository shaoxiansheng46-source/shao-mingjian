# Phase 5D 浏览器与接口验证

## 已执行

- `node --check frontend/app.js`：通过。
- `node --check frontend/physical.js`：通过。
- `GET /` 与新增 API 在本地 FastAPI 进程下可访问。
- FastAPI TestClient 验证真实工作台任务提交、轮询、几何检查、PS/PSP 结构和 JSON 报告。
- 使用 Playwright Node API 驱动本机 Chrome 完成真实页面流程：打开页面、进入“真实物理计算”、切换 `demo_fixture`、提交计算、看到 `completed`、生成实际 SVG；随后修改原边匝数，页面隐藏旧结果并显示失效提示。再切回 `external_database`，Provider 不可用时页面显示 `input_invalid` 和明确的 PyOpenMagnetics 缺失诊断。
- 浏览器截图证据：`output/playwright/phase5d-physical-workbench.png`（演示链路）和 `output/playwright/phase5d-physical-openmagnetics.png`（真实 Provider 链路；均已加入 `.gitignore`，不纳入版本提交）。

## 可复现手工流程

1. 启动后端：`python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`。
2. 浏览器打开 `http://127.0.0.1:8000/`，点击侧栏“真实物理计算”。
3. 选择“本地虚构数据·仅链路验证”可在生产 Python 环境验证页面链路；选择 `PS`、20/5 匝，保持显式波形，点击“运行真实物理计算”。
4. 如安装了 `.runtime/openmagnetics-venv`，应使用包含 FastAPI 的独立运行环境启动后端，选择 OpenMagnetics 真实数据库，查看 Provider 版本和第三方指标。
5. 修改匝数、排布或任一波形字段，确认旧结果失效；点击“只生成几何”可验证缺波形诊断；点击 JSON 导出检查快照。

## 工具限制

Windows 环境下 `npx --package @playwright/cli` 没有返回可用 CLI 输出；因此本次浏览器证据使用同一 Playwright 运行库的 Node API 和已安装 Chrome 完成，未将 CLI 命令本身标记为通过。

