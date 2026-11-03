# 03 A/B/C/D 模块清单与推荐路线

分类含义：A=优先直接复用 OpenMagnetics；B=保留并完善自研；C=复用基础能力后改造；D=当前 MVP 暂不实施。

## 1. 总体边界

当前优化器不应知道 MKF、PyOpenMagnetics 或 MVB 的内部 dict。统一入口先接收项目内部 SI 数据，再通过 provider/adapter 调用第三方，返回版本化内部结果。Demo provider 继续存在，保证 V1.0/V1.1 回归可比。

## 2. 模块分类表

| 模块 | 类别 | 现有代码位置 | OpenMagnetics 对应 | 推荐输入/输出 | 依赖 | 复杂度 | 验证 |
|---|---|---|---|---|---|---:|---|
| MAS 数据契约/校验 | C | `engine.py:validate_input`, `data_snapshot` | MAS `schemas/`, `api/validation.py` | 内部 `DesignRequest` ↔ MAS `inputs/magnetic/outputs` | schema 固定 commit、jsonschema/适配器 | 中 | schema round-trip、单位、必填字段 |
| 材料/磁芯/导线/骨架查询 | A | `load_database`, `/api/v1.4/data/*` | PyOM `get_*`/`find_*`、MAS `data/` | 查询条件 → `SourceRecord` | PyOM 数据库 | 中 | count、字段映射、版本/许可、人工 spot check |
| 磁芯有效参数/温度参数 | A/C | evaluator 中 Ae/le/Ve/Bsat 使用 | `calculate_core_data`, `get_core_temperature_dependant_parameters` | core + material + T → processed core | MKF core models | 中 | 参考磁芯、温度插值、单位 |
| 气隙磁阻/励磁电感 | C | `_gap_selection`、V1.1 gap 数据 | `calculate_gap_reluctance`, `calculate_inductance_from_number_turns_and_gapping` | core/gap/coil/op → Lm、fringing | MKF gap model；当前制造离散规则 | 高 | 解析磁阻、步进/范围、负气隙、边缘场对照 |
| DAB/SPS 波形与系统工况 | B | `sps_segments`、`validate_input` | MKF converter models `dab`/`process_converter` 可作 C 基准 | DAB 多工况 → waveform/current requirements | 项目系统定义、第三方 schema | 高 | 功率平衡、周期性、独立数值积分 |
| P-S 参数化排布 | B/C | `winding`、V1.0 evaluator | PyOM `wind`、MVB coil | core/window/wire/turns → sections/layers/MLT/Rdc | 现有 V1.0 回归、MAS coil | 高 | 逐层装配、边界、引线、Rdc、旧结果一致 |
| P-S-P/分区漏感 | B | `_psp_leakage_energy`, V1.1 evaluator | MKF field/leakage、PyOM `wind` | block layout → zone energy/Lleak/cap interfaces | 结构定义、一次侧参考 | 高 | P1+P2=Np、绝缘、能量积分、独立解析/FEM样例 |
| 磁芯损耗 | C | evaluator `pcore` | MKF/PyOM `calculate_core_losses`、iGSE/Steinmetz | waveform/core/material/models → Pcore | 材料损耗数据许可 | 高 | 正弦/三角/实测曲线、温频范围、单位 |
| 利兹线 DC/AC 损耗 | C | `winding`, `sampled_spectrum`, `fr` | PyOM `calculate_winding_losses` 与 skin/proximity/ohmic | coil + current waveform → Pcu | wire geometry、波形、模型版本 | 高 | DC closed form、skin/proximity benchmark、实测 |
| 热网络/工程温度约束 | B/C | evaluator 双节点迭代、`diagnostic_payload` | MKF core-temperature 可作为基础参考 | loss + thermal boundary → T nodes/hotspot status | 冷却方案、结构热阻、工程校核 | 高 | 热平衡、COMSOL/实验、热点误差 |
| 组合磁芯 | B/C | `_core_record`, V1.1 assembly JSON | MAS core assembly 可作数据契约；MKF 组合语义待验证 | assembly record → 等效/逐件参数 | 组合几何、磁路和窗口定义 | 高 | 不变量、质量/体积、磁路/FEM |
| 外置电感/系统边界 | B | V1.1 evaluator 外置电感分支 | MKF 可计算独立磁性元件，但无证据支持当前系统策略 | discrete inductor + side + n → Lseries/Pext/Text | 现有接口与约束 | 中-高 | n² 折算、安装侧电流、跨工况固定器件 |
| 候选生成和工程约束 | B | `candidate_catalog`, `validate_input`, failure counter | adviser filters 可作为 C 输入 | request → discrete candidate set + constraints | 所有 providers | 高 | 电压整数匝比、禁用模板、无解原因 |
| NSGA-II/多目标 | B | `nsga2_optimization`, `pareto_front` | OpenMagnetics adviser scoring 可用于候选预筛/辅助目标 | candidate vector + services → Pareto | pymoo 0.6.2、seed | 高 | ZDT/离散 benchmark、预算、收敛和重复性 |
| 参数化 3D/CAD | D（后置 C） | 当前仅 SVG 结构示意 | MVB `Builder.get_core/get_magnetic` | MAS candidate → STEP/STL/SVG | CadQuery/FreeCAD、文件生命周期 | 中-高 | shape family、P-S-P、组合、导出失败隔离 |
| SPICE/电路联机 | D | 当前无 | PyOM/MKF ngspice generators | converter/magnetic → netlist/波形 | ngspice、拓扑覆盖 | 高 | 独立 netlist 仿真，暂不进入优化环 |
| FEM/COMSOL/热点/局放 | D | 当前无 | OpenMagnetics 不等同于 FEM/COMSOL | candidate → external validation | COMSOL、网格/材料实测 | 很高 | 后置工程校核，不影响 Demo |

## 3. 推荐的复用优先级

### A 类：先复用

先接入 MAS 兼容的查询/数据结构和 OpenMagnetics 的 core/material/wire catalog；再把 core data、气隙磁阻、磁芯损耗、绕组损耗做成“可选基准引擎”。此阶段不改默认 provider。

### B 类：必须保留

DAB-SPS 的系统工况、用户约束、P-S/P-S-P 的工程排布、分区漏感、外置电感一次侧统一、组合磁芯、双边界目标、Demo/工程门禁、任务快照和 Pareto 展示是当前项目的产品核心，不应被通用 adviser 取代。

### C 类：适配后复用

把第三方的波形、core/gap、loss、wind 输出转换为内部结构，并在同一候选上同时运行 Demo provider 和 OpenMagnetics provider，比较偏差后才选择默认。适配器还要补充 SST 所需的多工况、分块、来源、适用范围和错误语义。

### D 类：本阶段不实施

完整 3D CAD、SPICE/NGspice 全拓扑、FEM/CFD、局放、热点、EMI、AI 代理模型和大规模真实厂家数据库许可治理不应与第一批接入混在一起。

## 4. 主要验证要求

每个 A/C 模块都要有：

1. 解析或独立数据计算的 reference case；
2. 同一输入在 Demo provider 与 OpenMagnetics provider 的结构化 diff；
3. 模型有效范围、单位、来源和版本校验；
4. 引擎异常不吞掉、不伪造结果；
5. 当第三方不可用时，V1.0/V1.1 Demo 仍可运行。
