# Phase 5D 结果展示

## 指标

- Lm、Bmax、Pcore、原边参考漏感：来自统一结构/工作点；第三方计算保留 MKF 模型名和版本。
- Rdc、native 铜损：Phase 4B 绕组损耗服务的总 RMS × 温度修正电阻。
- MKF complete：仅在显式端电压/端电流波形和 MAS 输入完整时显示；不把 standalone skin/proximity 再次叠加。
- 热点、温升：`not_implemented`，前端显示未计算。
- 工程状态：当前固定 `UNKNOWN`，因为漏感/邻近损耗尚未经 COMSOL 或样机校准，且全部结果 `engineering_approved=false`。

## 诊断

几何溢出、PSP 匝数不守恒、波形缺失、Provider 不可用和第三方字段缺失均显示为诊断文本。几何检查仍可返回实际结构；损耗阻断时相应值为 `null`。

## 报告

JSON 报告直接读取 `.runtime/physical-{id}.json`，包含同一输入、结果和哈希。页面导出按钮只对当前任务 ID 发起下载，避免报告和页面结果错配。

