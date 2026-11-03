# Phase 5D API 合同

所有内部数值使用 SI。数据库和计算结果只返回项目定义的 JSON 摘要，不暴露 PyOpenMagnetics 原始对象。

| 接口 | 用途 |
|---|---|
| `GET /api/v1.5/physical/status` | Provider 版本、数据库数量、数据源和热模型状态 |
| `GET /api/v1.5/physical/materials?q=&limit=` | 外部材料检索 |
| `GET /api/v1.5/physical/cores?q=&limit=` | 外部磁芯规格检索 |
| `GET /api/v1.5/physical/wires?q=&limit=` | 外部导线检索 |
| `POST /api/v1.5/physical/evaluations` | 提交一个候选结构和工作点快照 |
| `GET /api/v1.5/physical/evaluations/{id}` | 读取任务和结果 |
| `GET /api/v1.5/physical/evaluations/{id}/report?format=json` | 下载同一快照的 JSON 报告 |

## 请求主要字段

`data_source` 为 `external_database` 或明确的 `demo_fixture`；`layout` 为 `PS` 或 `PSP`；PSP 使用 `primary_segments=[P1,P2]` 且服务检查其和等于原边总匝数。`core`、`wire`、`geometry` 使用显示单位字段，适配层转换为米。`operating_point` 必须包含绕组端电压、电流、频率、RMS 电流和波形；波形缺失只允许几何检查。

## 结果合同

结果包含 `candidate_snapshot`、`operating_point_snapshot`、`context`、`candidate_hash`、`excitation_hash`、`evaluation_key`、`physical_model_version`、`source_selection` 和 `engineering_approved=false`。指标缺失时为 `null`，不会将异常、未适用或未计算转换为零。

`summary` 提供 `Lm_H`、`Bmax_T`、`Pcore_W`、`Lleak_p_H`、Rdc、native Rdc 铜损、MKF complete 铜损和热状态。`openmagnetics` 子树保留第三方每项调用的 status、model、provenance 和 diagnostics。

