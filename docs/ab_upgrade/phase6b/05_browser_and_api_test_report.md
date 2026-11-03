# Phase 6B 浏览器/API 验证报告

## 已执行

在真实 Provider 运行环境中启动 FastAPI，并通过 HTTP 调用完成一次小预算任务：

- Provider：PyOpenMagnetics 1.7.35，状态可用。
- 输入：真实 ETD 54/28/19、3C95、Bobbin ETD 54、真实利兹线；显式原副边电压和电流波形。
- 预算：population=2、generation=1、max_evaluations=2。
- 结果：`completed`，1 个唯一候选，1 次真实物理成功，1 个研究性可行候选，1 个 Pareto 候选。
- `/status`、任务查询、进度、all/feasible/pareto 候选和 JSON/CSV 导出均返回 200。

## 自动检查

- `node --check frontend/optimization.js`：通过。
- `node --check frontend/app.js`：通过。
- FastAPI 路由导入和 `/api/v1.6/status`：通过。
- Phase 6B 请求边界测试：通过。

## 未执行

当前 Codex Work 环境的本地浏览器控制被设置禁用（返回 `Local browser use is disabled in Work settings`），Playwright CLI 依赖下载也未在限定时间内可用。因此本阶段没有把“浏览器点击操作”误报为已自动化通过；已用真实 HTTP/API 联调、静态脚本检查和应用页面代码路径替代，并保留浏览器手工验证步骤供本地环境执行。

## 手工流程

1. 在项目目录启动真实 Provider 环境的 FastAPI。
2. 打开 `http://127.0.0.1:8000/`，点击“真实结构优化”。
3. 确认 Provider 可用，填写四组同长度采样序列。
4. 选择 PS/PSP、变量范围和小预算，点击“开始真实优化”。
5. 查看进度、候选表、Pareto 图和结构详情；修改任意参数后应出现结果失效提示。
6. 选择两个候选进行比较并导出 JSON/CSV。
