# Phase 6B API 合同

统一前缀：`/api/v1.6`。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/status` | Provider、版本、模式和计算预算上限 |
| POST | `/optimizations` | 创建真实结构优化任务，返回任务 ID |
| GET | `/optimizations/{id}` | 查询任务；`include_result=true` 返回完整结果 |
| GET | `/optimizations/{id}/progress` | 读取进度和计数 |
| POST | `/optimizations/{id}/cancel` | 设置取消事件 |
| GET | `/optimizations/{id}/candidates?view=all\|feasible\|pareto` | 查询候选视图 |
| GET | `/optimizations/{id}/candidates/{candidate_hash}` | 查询单候选 |
| GET | `/optimizations/{id}/report?format=json\|csv` | 导出任务结果 |

## 请求要点

请求必须包含：

```json
{
  "data_source": "external_database",
  "fixed": {"core": {"shape_name": "ETD 54/28/19", "material_name": "3C95", "bobbin_name": "Bobbin ETD 54"}, "wire": {"primary_name": "真实导线", "secondary_name": "真实导线"}},
  "operating_point": {
    "frequency_hz": 30000,
    "voltage_primary_v": 800,
    "voltage_secondary_v": 400,
    "current_waveforms": {"Primary": {"data": [1, 1, -1, -1], "time": [0, 0.00000833, 0.00001667, 0.000025], "frequency_hz": 30000}, "Secondary": {"data": [-2, -2, 2, 2], "time": [0, 0.00000833, 0.00001667, 0.000025], "frequency_hz": 30000}},
    "voltage_waveforms": {"Primary": {"data": [800, 800, -800, -800], "time": [0, 0.00000833, 0.00001667, 0.000025]}, "Secondary": {"data": [400, 400, -400, -400], "time": [0, 0.00000833, 0.00001667, 0.000025]}}
  },
  "variables": {"Np": {"optimize": true, "min": 16, "max": 24}, "Ns": {"optimize": true, "min": 4, "max": 8}, "P1": {"optimize": true, "min": 1, "max": 23}, "layout": {"optimize": true, "choices": ["PS", "PSP"]}, "interwinding_gap_m": {"min": 0.0004, "max": 0.0015, "step": 0.00005}, "core_clearance_m": {"min": 0.0003, "max": 0.0012, "step": 0.00005}},
  "optimizer": {"population_size": 4, "generations": 2, "max_evaluations": 8, "seed": 20261103}
}
```

内部单位均为 SI。页面负责把毫米、微米等工程单位转换为米；服务层再次校验范围、整数匝数、波形完整性和预算。`data_source` 不是可选的信任标记，任何非外部数据库值均返回 `SYNTHETIC_DATA_BLOCKED_IN_PHASE6B`。

## 状态语义

`pending/running/cancelling/completed/failed/cancelled` 是任务状态；候选自身还带 `geometry_feasible`、`research_feasible`、`engineering_status` 和 `pareto_rank`。研究性可行不代表工程 PASS；当前工程状态保持 UNKNOWN。
