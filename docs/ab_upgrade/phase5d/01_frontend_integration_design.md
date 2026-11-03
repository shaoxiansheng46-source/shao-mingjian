# Phase 5D 前端接入设计

## 范围

Phase 5D 增加独立的“真实物理计算”视图。旧的 `designView`、演示数据、参考枚举、NSGA-II、Pareto 结果和旧报告接口保持原路径不变。真实视图只提交一个候选结构和一个不可变工作点快照，不进入旧优化器。

## 交互边界

- `external_database`：必须使用 OpenMagnetics Provider 的真实数据库；Provider 不可用时返回明确错误，不能切换为 synthetic。
- `demo_fixture`：仅用于在没有第三方运行环境时验证网页编排链路，结果始终带 `synthetic=true`、`demo_only=true`、`engineering_approved=false`。
- PS/PSP、气隙、匝数、主绝缘、间距、端部余量、真实导线名称和显式绕组端波形都由表单构造请求。
- 修改任一输入会隐藏旧结果并显示“旧结果失效”，必须重新提交任务。
- 缺少波形时可以执行几何检查，损耗与第三方波形计算被阻断；不由直流母线电压自动生成波形。

## 页面实现

- `frontend/index.html`：新增 `physicalView`、数据来源和结构表单、显式波形字段、Provider 状态、指标和追溯快照。
- `frontend/physical.js`：独立于旧 `app.js` 的请求、任务轮询、失效标记、结果渲染和 JSON 导出。
- 结构 SVG 读取返回的 `LayoutGeometry` 坐标、区块、接口和窗口尺寸生成，未使用固定演示几何。
- 工程状态固定显示 `UNKNOWN`；热模型显示“未计算”，不复用 synthetic 温升。

## 视觉与可用性决策

采用 UI UX Pro Max 的 Data-Dense Dashboard 建议：状态和来源与数值并列、表单有可见标签、任务有进度和错误反馈、结果表格保持紧凑。按钮与字段保留键盘焦点和响应式布局；颜色不是唯一的状态含义，状态同时显示文字。

