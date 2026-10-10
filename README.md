# SST 中高频隔离变压器初步设计 Demo

这是基于 V1.5 需求文档和随附虚构演示数据包的可运行 Demo。所有结果都带有 `demo_only` / `synthetic` 标识，不用于工程选型。

## 启动

在仓库根目录运行：

```powershell
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

访问：[http://127.0.0.1:8000](http://127.0.0.1:8000)

## 后端检查

```powershell
python run_demo.py
pytest -q
```

检查包括：数据适配、14,400 候选参考枚举、34 个可行方案、2 个 Pareto 代表、无解诊断、工程/非支持波形阻断，以及改变电压比例后的 NSGA-II 实算。

## 工作台功能

- 加载默认 100 kW 项目，修改功率、电压、频率、漏感目标/公差、J、温度、体积/质量和匝数搜索范围；
- 运行参考枚举或 NSGA-II，查看进度、失败原因、Pareto 图、前沿方案表和单方案 P-S SVG 排布；
- 导出 Markdown 报告、CSV 和包含输入/数据快照/模型版本/种子/结果的项目 JSON；
- 数据库页查看四类库、模板和模型的 synthetic/启用状态；
- 输入变化后旧结果自动标记失效；工程模式、45% 占空比和禁用模板明确阻断。

## 主要接口

`POST /api/v1.4/projects/validate`、`POST /api/v1.4/designs/evaluate`、`POST /api/v1.4/optimizations`、`GET /api/v1.4/optimizations/{id}`、`POST /api/v1.4/optimizations/{id}/cancel`、`GET /api/v1.4/designs/{id}/report?format=md|csv|json`。
