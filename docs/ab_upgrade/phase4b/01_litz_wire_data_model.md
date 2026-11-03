# Phase 4B：利兹线数据模型

## 范围

新增 `backend/app/winding_loss/models.py` 中的 `LitzWireSpecification`。该对象只包含项目定义的数据，不暴露 PyOpenMagnetics 的内部字典。

内部长度、面积、电阻率和频率分别使用 m、m²、Ω·m、Hz。UI/报告边界才做 mm、mm²、kHz 等显示换算。

## 字段和来源

模型保留以下信息：制造商、型号、数据源、单股裸径、单股绝缘外径、股数、绞合层级/股数组、绞距、成品外径范围、成品截面、导体材料、电阻率及温度系数、标称直流电阻、裸铜面积、外部绝缘、推荐频率、缺失字段和可信度标识。

`from_provider_record()` 从 Phase 2 Provider 的归一化记录建立对象：

- 单股裸径和股数存在、但数据库没有 `conductingArea` 时，裸铜面积可由“股数 × 单股圆截面积”透明计算，并在元数据中保留原记录。
- 成品外径不从铜面积反推。数据库只有范围而没有 nominal 时，`finished_outer_diameter_m` 保持 `None`；调用方必须显式选择 `database_maximum` 等几何策略，否则返回 `MISSING_LITZ_PARAMETER`。
- 绞距、电阻率、成品标称外径缺失时保留缺失状态，不能用虚构值填充。
- `data_status=external_database`、`synthetic=false`、`demo_only=false`、`engineering_approved=false` 沿计算结果传播。

## 实际数据库记录

独立基准实际读取：

| 字段 | 值 |
|---|---|
| 型号 | `Litz 1000x0.02 - Grade 1 - Double Served` |
| 制造商 | Elektrisola |
| 股数 | 1000 |
| 单股裸径 | 20 μm |
| 成品外径范围 | 0.940–1.051 mm |
| nominal 外径 | 缺失 |
| 绞距 | 缺失 |
| 裸铜面积 | 3.14159265358979e-7 m²，由单股数据计算 |

基准为可复现的研发算例，选择 `database_maximum`（1.051 mm）作为排布外径；这不是对制造公差或绝缘标准的工程批准。
