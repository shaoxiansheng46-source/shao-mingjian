# SST 中高频隔离变压器初步设计软件 MVP 需求文档

**版本：V1.5（虚构演示数据集成版）**  
**日期：2026-10-09**  
**面向：Codex、产品负责人、设计工程师及开发工程师**  
**交付目标：默认虚构数据下可运行的完整软件闭环**

本文是独立开发需求，完整规定产品边界、数据格式、计算链、优化、UI、接口及验收。开发所需输入为本文与随附 `SST_V1.4_虚构演示数据包.zip`，无需其他需求文档或历史对话。

默认先交付 demo 模式：使用虚构但关系自洽的数据，完成需求输入、候选生成、实际几何排布、性能估算、约束、多目标优化和报告。工程模式作为有门槛的后续开放能力；真实数据库与模型标定不阻塞演示交付。

软件输出初步方案，物理计算结果的来源和适用范围必须可追溯。演示数值不代表真实厂家产品性能。

## 1. 产品目标与应用边界

### 1.1 产品目标

输入额定功率、两侧实际直流电压、频率、冷却条件、绝缘规则和漏感要求，利用磁芯、材料、利兹线、绝缘及结构规则库，自动生成可排布的整数匝数候选方案，计算磁密、励磁电感、实际漏感、双侧铜损、磁芯损耗及温升估算，输出可行域内的损耗—体积 Pareto 前沿。

初步应用的交付闭环为：需求输入→数据检查→磁芯预筛→整数匝数与导体选择→实际窗口排布→参数计算→约束判定→多目标优化→方案对比与可追溯报告。

### 1.2 支持范围与交付阶段

下表定义模型与接口的总体边界；交付优先级以第16章P0/P1为准。P0默认实现数据包中的单磁芯、零气隙、P-S、集成漏感及系统闭环模式。其他预留能力不得显示为已实现。

| 项目 | 本版本要求 |
|---|---|
| 电路 | 单相 DAB，全桥，SPS 单移相；两侧桥输出均为对称双极性 50% 占空比方波 |
| 变压器 | 铁氧体磁芯、利兹线绕组、稳态周期运行 |
| 排布 | 首先实现同心非交错 P-S；P/2-S-P/2 仅在对应漏感及排布模型通过验收后启用 |
| 磁芯组合 | 仅允许库中明确建模的单套或叠加组合；不自动推断任意并联磁路 |
| 工况 | 必填额定工况；允许输入多个电压/功率/环境温度工况，按最不利工况判定 |
| 计算 | 解析式、分段线性电流计算和必要的轻量数值处理；不接入 FEM/CFD，不引入代理模型 |
| 优化 | NSGA-II；小空间同时支持完全枚举作为基准 |
| 热模型 | 校准的双节点集总热网络；缺乏标定数据时输出温升区间及待验证标识 |
| 寄生电容 | 几何估算与风险提示；不宣称完成共模 EMI 或高频谐振设计 |

非 50% 占空比、EPS/DPS/TPS、LLC/CLLC、磁偏置、纳米晶、铜箔/CTC、复杂分段绕组、局部放电计算、瞬态热场及 ZVS 精确校验均不纳入本版本。遇到不支持的输入应明确阻断，不得静默改成支持工况。

### 1.3 数据模式与结果等级

- **演示模式 demo**：允许合成数据，只验证软件链路。所有结果标记“演示数据，不用于工程选型”；不得生成工程推荐结论。
- **工程模式 engineering**：关键数据具有来源、单位、适用范围、版本及审核状态。未校准的模型结果显示“估算/待验证”，不得显示“已验证”。
- 结果分为 `demo_only`、`preliminary_estimate`、`calibrated_estimate`、`externally_validated`。最后一级仅能由实际外部验证记录赋予，不能由软件自动模拟。

## 2. 数据包集成与演示项目

### 交付输入

开发输入为本文和 `SST_V1.4_虚构演示数据包.zip`。解压后的根目录为 `SST_V1_4_Demo_Data/`。该包名称与内含 `schema_version="1.4"` 是数据格式标识，不要求开发者了解任何历史需求文档。本文是完整开发依据。

默认数据模式为 demo。软件必须先使用该数据包实现可运行的设计流程；真实厂家库和工程标定属于后续工程模式开放条件，不阻塞演示 MVP 的开发与验收。

### 文件与条目

| 文件 | 条目及用途 |
|---|---|
| core_geometry_library.json | 3 个磁芯：DEMO_CORE_L、DEMO_CORE_XL、DEMO_CORE_XXL |
| core_material_library.json | 2 个材料：DEMO_FERRITE_A、DEMO_FERRITE_B |
| litz_library.json | 5 种线材：DEMO_LITZ_2000x0p1、4000x0p1、6000x0p1、8000x0p1、12000x0p1（均使用 DEMO_LITZ_ 前缀） |
| insulation_library.json | DEMO_FILM_0p2、DEMO_PAPER_0p5、DEMO_BARRIER_1p0 |
| winding_layout_templates.json | DEMO_LAYOUT_PS 启用；DEMO_LAYOUT_PSP、DEMO_LAYOUT_SPLIT 禁用 |
| design_rule_library.json | DEMO_RULES_001，关联 DEMO_INS_001 绝缘规则标识 |
| model_registry.json | 7 个虚构模型，统一按 ID 解析 |
| sample_input_feasible.json | 默认 100 kW 正例 |
| sample_input_infeasible.json | 0.001 L 体积上限，无解反例 |
| sample_input_engineering_blocked.json | 工程模式读取虚构数据，应阻断 |
| sample_input_unsupported.json | 45% 占空比，应阻断 |
| run_demo.py | 完全枚举计算链参考，不实现 NSGA-II、前端或服务 |
| self_test_results.json | 已生成的参考脚本自检记录 |
| reference_output/ | 正例 results.json、pareto.csv、report.md |
| reference_no_feasible/ | 无解结果和原因统计 |

`DEMO_INS_001` 是 `DEMO_RULES_001.insulation_rule_id` 所携带的规则子标识，不是独立材料条目。不得在 insulation_library.json 中查找它。材料使用 DEMO_FILM_0p2 等独立 ID。

### 已有数据的代表参数

| 磁芯 | 材料 | Ae mm² | Aw mm² | 窗口高×宽 mm | 磁芯体积 mm³ | 外包尺寸 mm |
|---|---|---:|---:|---|---:|---|
| DEMO_CORE_L | DEMO_FERRITE_A | 3000 | 5200 | 80×65 | 1050000 | 210×70×120 |
| DEMO_CORE_XL | DEMO_FERRITE_A | 4200 | 7600 | 95×80 | 1700000 | 250×80×135 |
| DEMO_CORE_XXL | DEMO_FERRITE_B | 5600 | 10450 | 110×95 | 2400000 | 290×90×150 |

每个条目均为虚构显式组件，不推断磁芯型号。Aw 为一个窗口面积，Np/Ns 已对应每匝在该窗口的一次占位。绕线柱为矩形。数据中的外包尺寸用于演示体积定义；真实项目需要重新建立装配外包尺寸。

### 字段映射与导入要求

数据包保留原文件和字段名，使用适配层转换至 SI 内部对象。不得要求用户手动重命名 JSON 字段。

| 数据字段 | 内部含义/处理 |
|---|---|
| id、revision | 所有条目唯一标识及数据版本；不要强制要求 core_id/material_code 等别名 |
| material_id | 磁芯外键，关联材料 id |
| Ae_mm2/Amin_mm2/Aw_mm2 | 乘 1e-6 转为 m² |
| Ve_mm3 | 乘 1e-9 转为 m³ |
| le_mm、各尺寸 _mm | 乘 1e-3 转为 m |
| core_outer_mm | 三轴尺寸；演示外包体积=乘积×1e-6 L |
| Bsat_vs_T | 按温度线性插值；超温域按模式策略处理 |
| loss_parameters | ki、alpha、beta、明确单位、参考温度及虚构温度系数 |
| copper_area_mm2 | 有效裸铜截面，包含一根标准利兹线全部股数 |
| Rdc_ohm_per_m_20C | 已含绞合因子，不重复乘 twist_length_factor |
| outer_diameter_mm、outer_dimension_tolerance_mm | 成品排布尺寸及公差 |
| allowed_layout_ids / search.allowed_layouts | 均为模板 ID，UI 显示名称与内部 ID 分开 |
| layer_insulation_id / main_insulation_id | 关联绝缘材料条目 |
| main_insulation_layers_choices | 主绝缘片数候选，不是绕组层数 |
| enabled / disabled_reason | 模板和模型可选状态；禁用项只用于查看，不参与优化 |
| engineering_approved、data_status | 演示/工程数据访问校验依据 |
| uncertainty=null | 未提供，不代表零误差或已验证 |

演示元数据必填：id、revision、data_status、source、created_date、engineering_approved。来源页码、审核人、拟合误差等真实工程字段在 demo 可空缺；工程模式必须补全其所需证据，不能因这些真实来源字段为空而拒绝演示库启动。

默认输入原样接受 `schema_version="1.4"`；内部归一化为 `schema_version="1.5"`。导出保存 `input_schema_version` 与 `normalized_schema_version`。没有适配器时不得直接拒绝已有数据包。

### 演示模型行为

- DEMO_IGSE_TRIANGLE：使用材料 ki 的三角磁通 iGSE 特例及参考温度线性修正。
- DEMO_UNIFORM_RELUCTANCE：均匀磁路；默认正例气隙为零，按 Lm 下限检查。
- DEMO_PS_1D：P-S 一维漏感模型；几何因子为 1，没有工程标定依据。
- DEMO_FR_EMPIRICAL：Fr=max(1,1.25·(f/20000)^0.25+0.08·(layers−1))。仅用于软件联调，不能标为 Dowell 或真实利兹线模型。
- DEMO_RECTANGULAR_PERIMETER：每层 MLT=2·(leg_width+leg_depth)+8·radial_center，尺寸单位一致。
- DEMO_PARALLEL_PLATE：从实际重叠面积估算 Cps。
- DEMO_THERMAL_001：Rca=0.18、Rwa=0.08、Rcw=0.30 K/W；对三磁芯共用虚构热网络，热点修正为空。

demo 为匹配参考脚本允许显式的 Fr 谐波外推；结果必须携带外推警告。工程模式不得采用此路径。

### 固定参考计算配置

设置 `reference_mode=true` 时，采用数据包参考脚本的精确策略，用于数据和后端移植回归：

1. 枚举 3 个磁芯，Np=10,12,…,32，Ns=Np/2；两侧分别 5 种线材、1~2 根并联；主绝缘片数为 2、3、4、5，故总候选数为 3×12×5×5×2×2×4=14400。
2. 模板 P-S，气隙为零，不启用组合磁芯或外置电感。每层匝数由可绕高度及外径确定，并联根数沿径向排列。
3. 单侧引线长度增加 0.15 m；单侧端接等效电阻 0.00005 Ω/并联根数；这些是脚本中的合成常数，软件应将其提取为 `demo_reference_config`，不能当通用工程默认。
4. 装配质量加 0.2 kg 合成余量；线材每米 Rdc 已包含绞合修正；不重复加长。
5. 512 个周期中点采样，求 1~128 阶谐波；未覆盖电流平方能量按第 129 阶 Fr 估算尾项，保留 `spectrum_tail_current_energy_fraction_p`。
6. 电热阻尼系数 0.5，最多 50 次；温度变化<0.005 K、损耗相对变化<0.0001。此处是匹配参考脚本的较严软件收敛阈值，不代表温度准确度。
7. 最终两目标按总损耗、体积非支配筛选，目标值一致的重复点只保留一个代表。

一般设计模式支持更广的整数匝比和工况；不能沿用 `Ns=Np/2` 作为所有项目的通用规则。参考模式不使用乐观预筛而改变 14400 个原始候选计数。

### 参考结果与比较口径

固定参考模式预期：14400 个候选、34 个演示可行方案、2 个前沿代表点。数字用于枚举参考模式，不能要求随机 NSGA-II 返回完全相同的中间可行方案数。

| 代表点 | 磁芯 | Np/Ns | dps mm | 实际漏感 μH | 损耗 W | 体积 L | 绕组节点 ℃ |
|---|---|---|---:|---:|---:|---:|---:|
| 低损耗 | DEMO_CORE_XXL | 12/6 | 2 | 18.19 | 145.2 | 3.915 | 48.5 |
| 小体积 | DEMO_CORE_XL | 12/6 | 2 | 19.82 | 262.7 | 2.700 | 51.3 |

单候选的精确值和线材/并联根数以 reference_output/results.json 为准。移植相同算法时，与 JSON 比较电感/损耗相对偏差≤0.1%，节点温度绝对偏差≤0.1 K；更换模型/数值策略必须先更新模型版本及参考结果，不能一边修改计算口径一边沿用旧基准。

## 3. 架构、单位与符号

模块包括：输入与工况管理、版本化数据库、候选结构生成、性能计算、约束评估、NSGA-II、报告导出、外部验证适配器。

计算核心统一使用 SI 单位。UI 和库导入可使用 mm、mm²、mm³、A/mm²、μH、pF、L；每个字段必须携带明确单位并仅在边界转换一次。禁止使用无单位字段 `volume_max`、`total_area`。

| 符号 | 定义 | 核心单位 |
|---|---|---|
| P_req | 指定方向的理想传输功率需求，损耗另算 | W |
| V1_dc、V2_dc | 两侧实际直流母线电压 | V |
| Np、Ns、n | 两侧整数匝数及 Np/Ns | 1 |
| V2_ref | 副边电压折算至一次侧：n·V2_dc | V |
| phi、D | 两桥移相角；D=abs(phi)/pi | rad、1 |
| L_series_p | 功率传输回路总串联电感，折算至一次侧 | H |
| L_leak_p | 变压器短路漏感，折算至一次侧 | H |
| L_ext_p | 外置串联电感折算值 | H |
| Lm_p | 一次侧励磁电感 | H |
| Ip_rms、Is_rms | 物理绕组总 RMS 电流 | A |
| Ae、Aw、le、Ve | 有效截面、定义明确的窗口面积、磁路长度、磁芯体积 | m²、m²、m、m³ |
| Bpk、DeltaB | 零偏置峰值磁密、峰峰值磁密 | T |
| Jp、Js | 实际铜电流密度 | A/m² |

必须统一漏感测试定义：测量侧、另一侧短接方式、测试频率、信号幅值、引线是否包含。空载测试电感不直接等同于纯励磁电感，必要时扣除模型中对应的漏感。

## 4. 输入需求与校验

### 4.1 系统与运行工况

必填：项目名、拓扑、V1_dc、V2_dc、P_req、fs、额定工况、T_amb、冷却方式。电压范围、频率范围、负载点以 `operating_points` 显式输入；软件不得假定额定点必然为最差点。

系统闭环模式为 P0；给定电流模式为 P1 接口扩展。输入模式定义如下：

1. **系统闭环模式 system_sps**：由总串联电感与功率求移相角，再计算电流。推荐默认。
2. **给定电流模式 supplied_current**：输入两侧 RMS、峰值及已知谐波/实测 Rac 数据；用于外部系统设计已有波形结果的场景。仅有一个 RMS 标量且无交流电阻依据时不能给出可信的高频铜损。

### 4.2 电感配置

- `leakage_mode=integrated`：要求 L_leak_p 在目标总串联电感公差内，外置电感为 0。
- `leakage_mode=external_allowed`：明确变压器自身漏感目标/上限；在指定工况设计值处确定固定的 L_ext_p，后续所有工况使用同一个外置电感。不得为每个候选运行点任意变化外置电感。
- 允许输入 `L_series_target_H`，或由指定设计移相角推导目标；两者同时输入则校验一致性，不一致即报错。
- 外置电感的损耗、体积和温升不计入“变压器”指标，报告须明确系统指标未完整覆盖。不得据此把变压器损耗当成系统效率。

### 4.3 设计规则输入

必填：两侧最大允许电流密度、绕组温升上限、磁芯/绕组温度上限、库规则 ID、绝缘规则子标识、匝比偏差上限、励磁电感下限或励磁电流限制。默认演示采用 Lm 下限。

可选：材料偏好、磁芯系列、组合上限、体积/质量上限、Np/Ns 搜索上限、绕组并联根数范围、B 搜索上限。

J 是搜索边界或偏好，实际 J 由标准导体铜截面决定。自动增加 J 必须在用户已指定范围内；超界候选直接淘汰。

绝缘规则应包含主绝缘最小厚度、绕组到磁芯距离、层间绝缘、端部裕量、所需爬电/电气间隙及来源。绝缘规则由设计工程师确定；材料击穿强度不能直接转成整机耐压合格结论。7 mm 等数值仅在特定项目规则中使用，不设为所有设备通用值。

### 4.4 输入 JSON 示例

以下为字段完整性示例，数值不代表已通过工程验证的设计。

```json
{
  "schema_version": "1.4",
  "data_mode": "demo",
  "project_name": "synthetic_100kW_DAB",
  "topology": "DAB_SPS",
  "current_mode": "system_sps",
  "bridge_duty": 0.5,
  "operating_points": [
    {
      "id": "rated",
      "V1_dc_V": 800,
      "V2_dc_V": 400,
      "P_req_W": 100000,
      "fs_Hz": 20000,
      "T_amb_C": 40
    }
  ],
  "inductance": {
    "reference_side": "primary",
    "leakage_mode": "integrated",
    "L_series_target_H": 2e-05,
    "relative_tolerance": 0.1,
    "Lm_min_H": 0.0005
  },
  "design_rules": {
    "rule_set_id": "DEMO_RULES_001",
    "insulation_rule_id": "DEMO_INS_001",
    "Jp_max_A_per_mm2": 3,
    "Js_max_A_per_mm2": 3,
    "turns_ratio_error_max": 0.02,
    "deltaT_w_max_K": 60,
    "Tw_max_C": 110,
    "Tc_max_C": 110,
    "volume_max_L": 10,
    "mass_max_kg": 20
  },
  "cooling": {
    "mode": "forced_air",
    "thermal_model_id": "DEMO_THERMAL_001"
  },
  "search": {
    "allowed_layouts": [
      "DEMO_LAYOUT_PS"
    ],
    "Np_min": 10,
    "Np_max": 32,
    "Np_step": 2,
    "parallel_bundles_max": 2,
    "core_assembly_max": 1,
    "population": 100,
    "generations": 200,
    "seed": 20261009
  }
}
```

所有数值检查有限、非 NaN、单位和范围正确。工程模式不得引用 `DEMO_` 条目；缺少核心数据不自动补入 Mock 值。

## 5. 五类数据库与结构模板

### 5.1 通用元数据

所有条目包含唯一 ID、revision 和 data_status（synthetic/manufacturer/measured/calibrated）。演示字段按数据包映射；工程条目补充来源 URL 或文件、来源页码/图表、采集日期、审核人、字段单位、适用范围与已知不确定度。未经核验不得声称 manufacturer。工程计算保留使用的完整快照及哈希。

### 5.2 设计规则库

包含：适用电压/频率/温度范围、J 上限、B 降额规则、窗口预筛铜利用率、绝缘规则、工艺间隙、可制造气隙范围及步进、匝比误差、冷却模型、温度限制、漏感公差和模型启用状态。预筛铜利用率与实际几何占用率必须分别命名。

### 5.3 磁芯规格库

必填：厂家/系列/型号、匹配材料、Ae、Amin（可得时）、Aw 的单双窗口定义、le、Ve、质量、外形尺寸、窗口净高净宽、绕线柱截面、骨架尺寸和可用绕线空间、支持排布、允许气隙、组合规则、尺寸公差。

组合磁芯必须有独立 assembly 条目或经审核的生成规则，明确 Ae、Ve、窗口及外包尺寸如何变化。不得把磁芯数量同时乘到 Ae、Aw 而无结构依据。缺少窗口净宽、平均匝长推导尺寸的磁芯不能进入工程模式。

### 5.4 磁性材料库

包含：Bsat(T)、有效磁导率或 AL 数据及测试条件、密度、损耗模型类型、频率/磁密/温度有效范围、拟合误差、参数单位。

损耗优先使用已验证的方波/三角磁通模型数据；若采用 iGSE，必须明确 ki 定义及其与正弦 Steinmetz k 的转换。不能直接把厂家正弦 k 填入 ki。不得使用无单位、无适用范围或无来源的系数作为工程数据。

### 5.5 利兹线库

必填：单丝裸径、绝缘外径、股数、实际铜截面、成品外形（圆/矩形及尺寸）、尺寸公差、结构/绞合信息、Rdc 每米与参考温度、绞合长度修正、密度/单位质量、频率范围、交流电阻模型或测试曲线 ID。

铜截面校核：Acu=q·pi·ds²/4，仅代表裸铜；成品外形用于排布。并联根数由候选选择；均流假设与端接条件应报告。`max_current_3A` 不是通用额定电流，应由实际 J 与温升约束重新计算。

### 5.6 绝缘材料库及排布模板

材料包含：型号、厚度及公差、介电常数与频率条件、耐温等级、热导率（热模型使用时）、密度、来源、层叠规则。介电强度可记录，但不代替绝缘配合。

模板定义：绕组块顺序、每块匝数分配、轴向/径向方向、每匝并联导体占位、层间绝缘、主绝缘、骨架和端部裕量、平均匝长算法、漏感模型 ID、模型有效范围。

Excel/CSV 导入须提供模板、预校验、错误行提示、版本审核与原子提交；导入失败不得部分污染生产库。

## 6. 电气计算链

### 6.1 匝比与整数匝数

设计中心匝比 n0=V1_dc_design/V2_dc_design。对每个磁芯，从磁密约束推导 Np_min，枚举整数 Np，并在 Np/n0 附近选择整数 Ns；按实际 n=Np/Ns 重新计算全部工况。不得先算浮点匝数，再将两侧分别向上取整后不检查匝比。

### 6.2 功率—移相—串联电感

理想 SPS、无直流偏置、所有电感折算到一次侧时：

\[
P=\frac{V_1 V_{2,ref}}{2\pi f_s L_{series,p}}\phi\left(1-\frac{|\phi|}{\pi}\right)
\]

正向传输时 P=V1·V2_ref·D(1-D)/(2fs·L_series_p)。默认求取 D∈[0,0.5] 的低移相分支。由实际 L_series_p 求可实现移相，不用目标电感替代实际值。Pmax=V1·V2_ref/(8fs·L_series_p)；若需求超出或超出项目移相上限，判为不可行。

功率输入作为理想传输功率；若用户指定负载端净输出功率，须通过显式损耗迭代接口另行定义，不能暗含等价。

### 6.3 周期电流与 RMS

根据两桥开关时刻生成电压分段，使用 di/dt=(v1-v2_ref)/L_series_p；积分得到每段线性电流。以周期性和零均值确定初始值；对每段端点电流 ia、ib：

\[
\int_{t_a}^{t_b}i^2dt=\frac{\Delta t}{3}(i_a^2+i_ai_b+i_b^2).
\]

校验周期闭合、平均电流及平均功率。系统模型须声明励磁支路位置，区分传输电流与物理绕组电流。可采用一次侧并联励磁支路近似：ip=i_transfer+im，is=n·i_transfer；逐时相加后求 RMS，不能直接把两个 RMS 标量相加。

对称双极性方波感应电压下，三角磁化电流：Im_pk=Vmag/(4fs·Lm)，Im_rms=Im_pk/sqrt(3)。Lm_min 由励磁电流限值推导时，使用明确的电流参考，不能令参考电流包含待求励磁电流而形成循环。

MVP 中 Vmag≈V1_dc 是忽略一次侧串联电压降的近似。该近似仅可在模型验证覆盖的结构内使用；当集成漏感较大或误差超限时须升级为包含漏感分配和励磁支路的周期等效电路，或将候选标记为不支持。不得把外部端子电压无条件认作磁芯感应电压。

## 7. 磁芯筛选、排布与制造约束

### 7.1 两层磁芯筛选

第一层是保守预筛，使用项目实际 P、fs、电压及预估两侧 RMS，B_lim 为材料损耗与饱和约束共同确定的上限，J 为已授权范围上限、Ku 为经验证的铜窗口利用率。

\[
N_{p,min}=\left\lceil\frac{V_{mag,max}}{4f_s A_e B_{lim}}\right\rceil,
\qquad A_{cu,req}=N_p I_p/J_p+N_s I_s/J_s.
\]

预筛要求 A_cu_req≤Ku·Aw；窗口定义须与匝数穿窗计数一致。电流尚未精确计算时，预筛不得用过于乐观的估计排除潜在可行磁芯，可用保守上下界或直接保留。

第二层以标准线成品尺寸、骨架、层间绝缘、主绝缘和端部裕量进行几何排布。铜面积合格不能代替几何合格。

### 7.2 排布算法

同心 P-S 的默认排布：先扣除骨架、端部裕量得到可绕高度；按单匝导体占位求每层可容匝数，向下取整；按匝数求层数，向上取整；累加两侧绕组径向厚度、层间绝缘及主绝缘，与净窗口宽度比较。

每匝并联根数须指定轴向或径向排列；成品直径、公差及工艺间隙均参与占位。输出每层匝数、层数、实际铜占用、实际几何占用和尺寸裕量。两窗口结构不重复计算同一匝铜面积。

排布失败：尝试更大窗口、经许可的磁芯组合、不同线型/并联排列、更多 Ae 以减少匝数，或在许可范围增加 J 后重新校验热性能。不得自动降低 J 来解决面积不足；不得越过绝缘规则缩短距离。

### 7.3 磁密与励磁电感

匝数确定后逐工况计算实际 Bpk=Vmag/(4fs·Np·Ae)，DeltaB=2Bpk，并检查局部截面可得时的磁密。B_lim(T)同时满足饱和降额和损耗模型范围；不能只按固定 100℃ Bsat 计算所有工况。

简单磁路初值：

\[
L_m\approx\frac{\mu_0N_p^2A_e}{l_e/\mu_e+g_{eq}},
\qquad g_{eq,req}=\frac{\mu_0N_p^2A_e}{L_{m,target}}-\frac{l_e}{\mu_e}.
\]

优先使用厂家 AL—气隙数据及适用磁通范围。mu_e 应与组合磁路和工作条件一致，不能无条件使用初始磁导率。

若负气隙：精确 Lm 目标模式判该结构不可实现；仅 Lm 下限模式可使用无气隙结构并重新校验实际 Lm。等效气隙须映射到实际各气隙位置与总量，按工艺步进量化后重算。大气隙/显著边缘磁通/附近导体附加损耗超出模型有效范围时排除，不允许仅凭代数式输出厘米级气隙。

## 8. 实际漏感与寄生电容

### 8.1 漏感模型

初版仅启用经过验证的 P-S 同心结构。一维均匀漏磁场近似：

\[
L_{leak,p}\approx\mu_0N_p^2\frac{MLT_{leak}}{h_{eff}}
\left(\frac{b_p}{3}+d_{ps}+\frac{b_s}{3}\right)k_{geom}.
\]

bp、bs 为实际绕组径向厚度，dps 为两绕组间隔，heff 为有效重叠高度，MLT_leak 为模型定义的漏磁路径平均周长；kgeom 必须有适用结构和标定依据。未标定默认 1 仅代表理想一维估算，不得宣称达到漏感误差目标。

使用前提：同心、近似均匀有效高度、负载安匝基本平衡、无强端部/气隙边缘效应。部分交错不能直接复用本式并任意乘“改善系数”；需分绕组块能量法及独立验证。

集成模式以 L_leak_actual 对比目标及公差；外置模式 L_series=L_leak+L_ext。除标称值外，输出绝缘厚度、绕组厚度及模型误差导致的区间。项目选择 nominal 或 conservative 约束模式，后者要求区间仍落在目标范围内。

### 8.2 寄生电容

Cps≈epsilon0·epsilon_r·Aoverlap/dps 仅用于单界面近似。多层绝缘使用单位面积串联介质公式：C/A=epsilon0/(Σdj/epsilon_rj)。面积必须来自实际相邻绕组面，不得由磁芯面积替代。

P-S-P 有多个耦合界面，未经验证不允许简单相加当作两端等效电容。输出 `Cps_estimate_F`、模型 ID、参考连接和适用范围。

f_proxy=1/(2pi·sqrt(L_leak·Cps)) 仅为参数组合风险指标，不命名为整机自谐振频率。整机谐振硬约束须有绕组自电容、端口连接及等效网络依据；默认只显示提示，不用“10倍开关频率”一票淘汰所有设计。

## 9. 损耗计算

### 9.1 磁芯损耗

对均匀磁通、零偏置、对称双极性方波感应电压所形成的三角磁通，iGSE 特例：

\[
p_v=k_i(4f_sB_{pk})^{\alpha}(2B_{pk})^{\beta-\alpha},\qquad P_{core}=p_vV_e.
\]

ki 的单位须使 pv 为 W/m³；频率 Hz、磁密 T。正弦损耗系数必须按其文献定义转换或重新拟合，并用基准点确认。损耗随温度的变化通过数据表/分段拟合处理；不得用一个常数覆盖所有温度。

超出频率、B、温度有效范围时工程模式判模型不可用；演示模式可显示外推，但须明显标记。标定覆盖前不保证磁芯损耗误差。

### 9.2 两侧直流电阻

各层平均匝长由绕线柱/骨架和层半径推导，线长包括引线、绞合修正及端接。每侧分别计算：

\[
R_{dc}(T)=\rho_{20}[1+\alpha_{Cu}(T-20)]\frac{l_{conductor}}{A_{cu,effective}}+R_{termination}.
\]

并联绕组在均流假设下可按总等效截面或分支电阻并联计算，不能同时重复除以并联根数。优先使用实测/厂家每米 Rdc 并做温度换算，避免已包含绞合系数时重复增加线长。

### 9.3 高频铜损

两侧损耗独立计算并求和：

\[
P_{cu,p}=I_{p,dc}^2R_{dc,p}+\sum_{h\ge1}I_{p,h,rms}^2R_{ac,p}(hf_s,T_w),
\]

副边同理。可通过分段线性周期电流解析或确定性采样得到谐波，增加阶数直到损耗增量满足配置阈值；若 Rac 数据频域覆盖不足则报告未覆盖尾项，不能静默截断。

交流电阻模型按优先级使用：相同结构/频率/温度下的测试或标定模型；经审核的利兹线解析模型；最后是工程师给定的 Fr 区间用于敏感性估算。Fr 必须对应实际层数、并联结构及邻近磁场。单丝径小于两倍趋肤深度只是选线参考，不是 Fr≈1 的充分条件。

不得使用 `1+Delta^4/3` 再乘无来源层数系数作为工程铜损模型；缺少可靠 Rac 模型时可计算 Rdc 铜损下界及 Fr 区间，但不能输出确定的高效型最优方案。

Ptotal=Pcore+Pcu_p+Pcu_s+Pother。附加损耗仅有依据时计入；未知支架/屏蔽/端接损耗要列为未覆盖项。变压器效率估算采用明确功率口径，例如 eta_est=Pout/(Pout+Ptotal)，不得解释为 DAB 系统效率。

## 10. 热模型与电热迭代

默认双节点：磁芯 Tc、绕组 Tw，环境 Ta。热阻 Rca、Rwa、Rcw 来自同结构标定或受控估算：

\[
P_c=(T_c-T_a)/R_{ca}+(T_c-T_w)/R_{cw},
\]
\[
P_w=(T_w-T_a)/R_{wa}+(T_w-T_c)/R_{cw}.
\]

Pc 为磁芯热源，Pw 为绕组热源。附加损耗须按位置分配。热阻为正、网络矩阵可解；阻断 NaN、负热阻和奇异网络。

计算流程：以初始温度求损耗→求节点温度→更新铜电阻/磁芯损耗→阻尼迭代，直到温度最大变化<0.5 K 且损耗相对变化<1%，最多 50 次。阈值为软件收敛要求，不代表实际温度精度。迭代不收敛须返回明确状态并淘汰候选。

输出 Tc_est、Tw_est、DeltaT_w_est。只有拥有标定的热点修正（例如分侧热点热阻）时输出 Thotspot_est；否则不生成伪热点值，显示“节点温度估算，热点待验证”。如项目只规定热点限值且无热点模型，该候选状态为待验证，不能判为完全可行。

强迫风冷应绑定风速、风向、安装与结构有效范围，不能只用 20~50 W/(m²·K) 常数判断最终温升。简单 1/(hA) 模型仅作降级估算；面积不得将内部遮挡表面当作有效散热面。输出热阻/Fr/损耗不确定性下的温升区间，并支持保守约束模式。

## 11. 优化与不可行诊断

### 11.1 决策变量与推导量

决策变量：磁芯 assembly ID、Np、Ns、两侧利兹线 ID、并联根数、排布模板、离散主绝缘层数/厚度；若项目允许，在可制造集合内搜索气隙。

推导量：n、Bpk、实际 J、层数、线长、Lm、Lleak、Cps、电流、损耗、温升、外包体积、质量。B 不作为与 Np 独立的自由基因；目标 Lm 和独立气隙搜索不得同时强制互相矛盾的等式。

### 11.2 目标与约束

默认目标向量为 [Ptotal_rated_W, V_envelope_m3]，多个工况的损耗聚合方式显式配置（额定、最大或带权平均）。体积定义为变压器含骨架/绝缘/工艺裕量的外包尺寸乘积；磁芯材料体积单独输出。风机/外置电感仅在明确系统边界下另行统计。

硬约束：支持范围、数据有效性、整数匝比、磁密、几何排布、绝缘规则、实际 J、励磁电感/电流、漏感公差、功率可实现性、温度、体积、质量及模型收敛。所有运行工况均须满足。

约束采用可行性优先支配：可行解优于不可行解；可行解用非支配排序；不可行解按归一化违反量比较。不使用固定 5000/10000 惩罚掩盖单位或约束差异。不把 W 与 L 直接加权当作物理目标。

### 11.3 执行要求

初始种群优先从预筛后候选生成，保留制造离散性。支持去重、缓存、固定种子、保存中间状态及取消。默认 100 个体×200 代，可配置；最终前沿以统一高精度配置重新评估。

停止条件包括评估预算、代数和归一化 hypervolume/前沿变化指标；单一“最佳个体不变”不代表多目标收敛。

生成前沿后推荐 3~5 个代表方案：最低损耗、最小体积、拐点或用户偏好。实际可行解不足 3 个时如实输出；0 个时返回不可行诊断，绝不填入虚构方案。

### 11.4 不可行诊断

返回原因分类、失败候选数量、最接近可行候选、各约束裕量及可执行建议。建议基于当前结果，例如“窗口径向缺少 3 mm，建议扩大窗口或调整线型”。不得泛化建议更换开关管或随意放宽绝缘。建议不自动修改客户约束。

## 12. UI、结果与报告

最小界面包含：项目/工况输入、数据库选择与状态、优化进度、Pareto 散点图、3~5 个代表方案对比、单方案排布尺寸示意、约束裕量和导出。

结果必须包含：

- 每个工况的电压、功率、频率、移相、两侧 RMS/峰值、磁密和温度；
- 磁芯真实 ID、组合方式、材料、Np/Ns、实际变比、实际气隙及等效气隙；
- 两侧线型/并联根数/铜截面/J、每层匝数、层数、平均匝长、Rdc、Rac 模型及铜损；
- 目标和实际 Lseries、Lleak、Lext、Lm、参考侧、容差区间；
- Pcore、Pcu_p、Pcu_s、Pother、Ptotal、效率口径、外包体积、质量；
- Cps 估算、风险指标及限制；
- 所有约束的 threshold、actual、margin、status；
- 数据版本、模型版本、种子、求解预算、计算时间、结果等级、待验证项。

输出 JSON 的缺失物理量使用 null 与原因，不能填 0；不适用与计算失败应区分。导出 Markdown 报告、方案 CSV、完整项目 JSON。候选排序解释必须与实际目标一致。

## 13. API 与外部验证

| API | 功能 |
|---|---|
| POST /api/v1.4/projects/validate | 输入、单位、数据库与工况校验 |
| POST /api/v1.4/designs/evaluate | 单候选计算与约束评估 |
| POST /api/v1.4/optimizations | 创建异步寻优任务 |
| GET /api/v1.4/optimizations/{id} | 状态、进度与结果 |
| POST /api/v1.4/optimizations/{id}/cancel | 取消任务 |
| GET /api/v1.4/designs/{id}/report | 导出报告 |
| POST /api/v1.4/validation-jobs | 预留外部验证任务，MVP 不执行仿真 |

外部请求须包含 schema_version、candidate_id、数据/模型哈希、真实几何、绕组连接与方向、整数匝数、导体、绝缘、气隙、逐工况波形、材料及热边界。

未接入外部验证时返回 `not_configured`，验证字段为 null，保留解析结果原字段及来源。超时返回 `failed/timeout`；Mock 验证只允许测试环境，必须 `is_mock=true`，不得存入真实验证记录。

外部结果携带软件/模型版本、网格/求解条件、测试定义、单位、时间戳和证据文件。解析值与验证值并列保留，禁止覆盖来源。

## 14. 技术实现与项目结构

### 默认技术方案

本项目是有计算后端的多文件工程软件，不采用单页静态 Mock UI 代替完整实现。

| 层 | 默认选择 | 用途 |
|---|---|---|
| 前端 | React + TypeScript + Vite | 工程工作台及可维护组件 |
| 组件 | Ant Design | 参数表单、数据表、抽屉、状态与反馈 |
| 图表 | Apache ECharts | Pareto 散点图、损耗分项、电流曲线 |
| 几何示意 | SVG | P-S 剖面、尺寸和层数，来自真实候选几何 |
| 后端 | Python + FastAPI + Pydantic | 输入/数据校验、计算服务、任务 API |
| 数值与优化 | NumPy + pymoo | 波形/损耗计算、NSGA-II |
| 持久化 | SQLite + JSON 版本快照 | 项目、任务、方案索引及可复算输入 |
| 任务 | 独立进程执行器 | 计算不阻塞 API；P0 单任务执行队列即可 |
| 验证 | pytest、前端组件检查、浏览器流程检查 | 物理规则与端到端闭环 |

这是本项目默认选型，不意味着已经安装依赖或实现代码。开发时核实安装版本与 API，生成前后端锁文件，禁止依赖未固定的 latest 才能复算。

模块目录应包括：frontend、backend/app/api、backend/app/schemas、backend/app/data_adapter、backend/app/geometry、backend/app/electrical、backend/app/losses、backend/app/thermal、backend/app/constraints、backend/app/optimization、backend/app/reports、backend/tests、data/demo、examples、docs。

数据包 JSON 原样放入 data/demo；参考脚本与其输出放 examples/reference，产品计算核心自行提取和测试，不把参考脚本整段嵌入 API 当成完成工程化。

### NSGA-II 与枚举的共用契约

优化器与枚举器调用同一个 `evaluate_candidate(candidate, operating_points, data_snapshot, model_config)`。其返回值包含结构、逐工况性能、约束清单、归一化违反量、目标向量和警告。

整数/类别变量使用可制造集合的索引或混合变量算子，分类 ID 不用浮点连续编码直接四舍五入。修复后重新计算几何和所有约束。NSGA-II 结果须复评并去除不可行及支配点。

默认双目标 [额定总损耗 W，外包体积 m³]，保留原始单位；算法内用于距离/指标的归一化与报告物理量分开。

固定数据下先实现枚举作为正确性参考，再实现 NSGA-II。固定种子和预算不保证天然命中所有最优点；验收记录至少 5 个固定种子的前沿质量和可行性。默认小空间下建议 NSGA-II 归一化 hypervolume 达枚举前沿的≥95%，每个返回点均满足同一物理约束。归一化上下界和参考点来自固定枚举集并保存，不能每次自选坐标掩盖质量差异。

### 任务状态与响应

状态：queued、running、completed、no_feasible_solution、cancelled、failed。没有可行解不是服务异常；HTTP 状态与业务状态分开。任务响应包含 progress、generation、evaluated_count、feasible_count、pareto_count、diagnostics、result_grade。

取消在安全检查点生效；新输入变化后旧结果显示“输入已变更，需重新计算”，不能将旧结果当作新需求的结果。

## 15. UI 工作台与交互验收

### 页面与主要任务

| 页面 | 必须实现的内容 |
|---|---|
| 项目与需求 | 新建/保存/打开项目；一键加载默认演示；系统、工况、电感、绝缘和冷却表单 |
| 数据库 | 四类库与模板/模型/规则的页签；筛选、查看字段和来源；显示 synthetic 与启用状态 |
| 寻优工作台 | 算法切换（参考枚举/NSGA-II）、预算/种子、开始/取消、进度及失败分类 |
| 方案对比 | Pareto 图、代表方案、可筛选对比表、约束裕量、逐工况性能 |
| 方案详情 | 磁芯/线材、排布 SVG、匝数层数、漏感、电流与损耗、热节点、模型与警告 |
| 报告 | 导出 Markdown、CSV、项目 JSON；保存数据和模型版本 |

桌面布局以左侧导航、顶部项目栏、中央主要工作区为主。需求表单按任务分组，默认收起高级参数；寻优结果先展示可行性与损耗/体积权衡，再展示详情。不能用大幅宣传图片或营销首页占据工作区。

### 视觉规范

中文界面；白色/浅灰背景、深蓝主色，适度信息密度。数值右对齐，单位放入列标题或输入后缀；同一指标各页面采用同一精度与单位。普通正文使用系统中文字体，数值使用等宽数字特性；不依赖外网字体才能显示。

按钮和状态用文字与图标共同表达；可行/失败不只靠红绿颜色区分。所有参数有标签、单位、范围和必要提示，错误贴近字段并提供汇总。键盘可访问、焦点可见，图表同时有可读数据表。

主布局在 1440×900 和 1920×1080 下可用；1280 px 下可折叠导航。表格可在自身容器横向滚动，整页不出现无意义横向滚动。P0 不要求完整手机工作台。

### 图表与结构示意

- Pareto 横轴为体积 L、纵轴为总损耗 W；散点点击与方案表行选择双向联动。悬浮信息含磁芯、匝数、实际漏感、损耗和温升。
- 约束表展示 actual、limit、margin 和通过/失败/待验证状态；无解时显示失败原因统计及最近候选。
- 损耗图至少分 Pcore、Pcu_p、Pcu_s；不存在的 Pother 显示未覆盖或 0 的明确模型定义，不能假装已算过。
- SVG 显示磁芯、窗口、骨架、P/S 导体块、主绝缘和净空间。尺寸来自所选方案；标注“剖面示意”，非制造图，不用 AI 生成图片替代候选结构。
- 磁芯/绕组节点温度分别展示。热点为空时显示“未建立热点模型”，不拿 Tw 当热点。

### 演示入口与关键状态

首次启动可选择“加载100 kW演示项目”，自动填入数据包默认输入并关联全部库。顶部持续显示“虚构数据演示”。演示下可运行求解与导出；若切换工程模式，明确列出当前 synthetic 条目，阻断求解并提示需要工程库。

至少检查：加载样例→运行枚举→查看两个权衡点→点击方案→查看排布和损耗→导出；运行 NSGA-II→进度与取消；修改体积上限→无解诊断；修改占空比→字段阻断；查看禁用模板→不能选用；切换工程模式→虚构数据阻断。

## 16. 非功能需求与实施优先级

- 性能基准：固定数据库、工况、种子、CPU/内存及软件版本。建议目标为 100×200、3 工况在参考 8 核/16 GB 环境下 P95≤60 s；此为待实测确认的产品目标，不作解析式必然达到的承诺。单候选与全流程分别计时。
- 可复现：同数据库/模型版本和种子在相同运行环境得到一致结果；报告可从项目 JSON 复算。
- 可维护：模型插件具有 input/output schema、单位、有效范围和版本；数据库更新不要求改计算代码。
- 容错：单候选失败不终止全局任务；配置/数据系统错误立即终止并给出错误字段；不得将异常写成零损耗。
- 日志：每代可行比例、前沿规模、目标范围、主要失败原因及模型警告；无需保存所有重复个体全文。

P0：默认 demo 库导入、单位与输入、P-S 排布、零气隙及 Lm 下限、集成漏感模式、SPS 电流闭环、双侧损耗、虚构双节点热模型、参考枚举、可行性 NSGA-II、中文工作台、报告和演示验收。P0 必须能完整运行默认 100 kW 样例。

工程模式 P0 仅实现数据阻断与状态提示；没有真实库时，不承诺工程选型可用。数据包禁用的排布不能因页面存在而开放。

P1：非零气隙制造量化、给定电流、外置电感、磁芯组合、P-S-P 经验证模型、多工况敏感性、批量导入、数据审核、完整不确定性与工程模式开放。P0 保留字段与明确的 unsupported 状态，不以虚构功能冒充已实现。

P2：FEM/CFD 对接、更多拓扑/材料/导体、系统效率与 ZVS、瞬态热、代理模型。P0 必须形成可运行闭环，P1 模型未验收不得提前开放。

## 17. 验收要求

### 演示 MVP 验收入口

演示交付至少提供一条后端检查命令和一条前端启动命令。在空项目安装依赖后能加载数据包，逐项执行以下验收：

- 七个数据文件导入成功，ID唯一、外键与单位有效；原始JSON保持不变。
- 参考枚举返回14400候选、34个可行方案、2个前沿点，并与参考JSON在本文容差内一致。
- NSGA-II走同计算引擎，输出全部可行、非支配方案并记录种子及质量；无解时不返回伪推荐。
- 工程模式与45%占空比反例均阻断；0.001 L体积反例返回no_feasible_solution。
- UI能加载样例、运行、取消、对比、查看真实候选排布及导出；禁用模板不可选。
- 导出项目可复算，报告持续保留demo_only及synthetic来源；热点为空。

以下公式用例按启用能力执行；非零气隙、外置电感等P1能力在相应阶段验收，不阻塞P0演示交付。

### 17.1 软件与公式验收

| 编号 | 用例 | 合格条件 |
|---|---|---|
| A01 | 单位换算 | mm²/mm³/L/μH/A·mm⁻² 与 SI 对照结果一致，不重复转换 |
| A02 | 变比 | V1=800、V2=400、Np=20、Ns=10 得 n=2、V2_ref=800；不把 V2_ref 当实际副边电压 |
| A03 | SPS 功率 | V1=V2_ref=800、fs=20 kHz、Lseries=10 μH、D=0.05 得 P=76 kW；D=0.5 得 400 kW |
| A04 | 不可实现功率 | 需求超过 Pmax 或项目 phi 上限时明确淘汰 |
| A05 | 磁密 | Vmag=800、fs=20 kHz、Np=20、Ae=1000 mm² 得 Bpk=0.5 T，并按库限值判断 |
| A06 | RMS 与波形 | 分段积分与独立高精度参考一致；周期闭合、零均值、平均功率误差≤0.1% |
| A07 | 窗口 | J 降低后所需铜截面增加；铜面积通过但成品外形超窗必须判失败 |
| A08 | 并联导体 | 铜面积、电阻和几何按一致规则处理，不能重复降低电阻 |
| A09 | 气隙 | 负气隙/超工艺上限处理正确；工艺量化后重算 Lm |
| A10 | 漏感 | 几何尺寸和参考侧正确；简单有效域内增大主绝缘间隔时漏感增大 |
| A11 | 损耗 | 两侧铜损均计入；电流扩大两倍且 Rac 固定时铜损扩大四倍 |
| A12 | 数据范围 | ki 单位缺失、超模型范围、demo 数据进入工程模式均阻断 |
| A13 | 热 | 零热源等于环境温度；正热源能量平衡；无热点模型不输出伪热点 |
| A14 | 优化 | 人工小空间与枚举非支配集一致；报告只含可行前沿，种子可复算 |
| A15 | 无解与接口 | 0 个可行解正确诊断；未接入验证保持 null 与 not_configured |

### 17.2 工程模型验收

后续工程模式开放前，对每个启用结构至少准备 5 个独立参考设计，覆盖匝数/排布、主绝缘、气隙、频率和负载边界；参考可来自样机实测或经过审核的高保真模型。拟合数据与验证数据分开。

建议初步目标：Lm/Lleak 相对误差≤15%，磁芯/绕组损耗分别≤20%，节点温升误差≤max(5 K，参考温升的20%)。这些是本版本拟定的验收目标，必须由实测确认；不沿用高精度仿真的≤5%目标作为解析 MVP 的默认承诺。

误差分母接近零时使用预先定义的绝对误差阈值；不得以百分比掩盖小量异常。无法满足目标的模型缩小有效域或保持待验证，不得以固定安全系数宣称通过。

验证集须至少包含一个真实工程功率等级的可排布设计及一个无解需求。仅使用几百瓦磁芯的合成算例不能证明满足 100 kW 级应用需求。

### 17.3 开发交付清单

可运行程序、输入 JSON Schema、数据库 Schema 与导入模板、独立 demo 数据、工程数据来源登记表、计算模型说明、公式与约束测试、参考设计验证报告、性能基准、示例项目、报告模板、部署及使用说明。

## 18. 实现流程伪代码

```python
validate_request_and_data_versions()
assemblies = conservative_core_prefilter()
for genes in candidate_generator_or_nsga2(assemblies):
    design = build_integer_turns_and_standard_conductors(genes)
    layout = pack_actual_windings_and_insulation(design)
    if not layout.feasible:
        record_failure("geometry")
        continue
    inductances = compute_lm_and_geometry_leakage(layout)
    # 气隙量化及固定外置电感确定均发生在逐工况计算之前
    design = finalize_manufacturable_design(layout, inductances)
    results = []
    for op in operating_points:
        phase = solve_sps_phase(op, design.actual_series_inductance)
        currents = solve_periodic_winding_currents(op, phase, design)
        results.append(iterate_electrical_losses_and_thermal(design, op, currents))
    constraints = assess_all_points_and_model_validity(design, results)
    objectives = aggregate_objectives(design, results)
    submit_feasibility_and_objectives(genes, constraints, objectives)
front = reevaluate_and_filter_feasible_nondominated_candidates()
export_real_results_or_infeasibility_diagnosis(front)
```

## 19. GitHub Skill 调研与使用方案

检索日期：2026-10-09。以下已核实存在仓库及 SKILL.md，仅推荐与本项目相关的部分。Skill 是开发指导与工具流程，不是现成 UI 产品、模型数据库或已验证的变压器计算程序；本次未安装这些仓库。

### 推荐组合

| Skill | 官方/作者仓库与入口 | 项目用途 | 优先级 |
|---|---|---|---|
| UI UX Pro Max | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)；[SKILL.md](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/.claude/skills/ui-ux-pro-max/SKILL.md) | 工程工作台、表单、颜色/间距/图表与 UX 审查 | 首选 UI |
| pymoo | [K-Dense-AI/scientific-agent-skills/skills/pymoo](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/pymoo)；[SKILL.md](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/pymoo/SKILL.md) | NSGA-II、混合变量、可行性、Pareto 与优化验证 | 首选算法 |
| playwright | [openai/skills/skills/.curated/playwright](https://github.com/openai/skills/tree/main/skills/.curated/playwright)；[SKILL.md](https://github.com/openai/skills/blob/main/skills/.curated/playwright/SKILL.md) | 参数填写、运行、对比、导出及页面截图检查 | 首选 UI 检查 |
| frontend-design | [anthropics/skills/skills/frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design)；[SKILL.md](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) | 视觉方向与界面细节审查 | 可选辅助 |

推荐判断：UI UX Pro Max 的检索式设计指南适合本项目的表单、数据表和分析图；pymoo 与双目标优化直接相关。frontend-design 偏视觉表达，可辅助打磨，但其首页/视觉风格建议需服从本文工程工作台约束，不应导向宣传站。Playwright 用于实际 UI 行为检查，不负责保证物理公式准确。

没有把普通磁性设计仓库或 NSGA-II 算法仓库误列为 Skill；未核实到可直接覆盖本项目全套中高频隔离变压器解析设计链的现成 Skill。物理计算仍以本文公式、数据与验收为依据。

### 接入方法

UI UX Pro Max 的作者 README 提供 Codex CLI 安装入口。开发环境需要安装时，可按该仓库当前 README 使用：

```bash
npm install -g ui-ux-pro-max-cli
uipro init --ai codex
```

命令在目标项目根目录运行；它是后续开发环境接入说明，本次未执行。记录安装包版本及使用的 Skill 文件快照。不要只下载 SKILL.md 而遗漏搜索脚本、参考文件和数据。

pymoo、playwright、frontend-design 可向目标 Codex 环境的 Skill 安装器提供上述完整目录 URL，或按该环境的 Skill 目录规范接入整个目录；实际读取后确认依赖和平台能力。不同 Skill 自带脚本依赖不同，不能认为贴一条 GitHub 链接就已安装或能执行。

UI 设计检索可使用关键词：`engineering dashboard dense`、`parameter form validation`、`pareto scatter chart`。这是本项目建议的查询，不声称仓库自带变压器专业主题。

### Codex 开发任务说明

```text
按本需求文档开发 SST 中高频隔离变压器初步设计软件。
导入随附虚构演示数据包；先完成数据适配和参考枚举回归，再实现同计算引擎的 NSGA-II。
默认 demo 模式，真实工程数据不作为演示 MVP 启动前提。
UI 采用 React/TypeScript、Ant Design、ECharts，使用工程工作台布局。
若环境已安装 UI UX Pro Max，则用于表单、布局和图表；若已安装 pymoo Skill，
则用于约束多目标优化；若已安装 Playwright Skill，则用于本地 UI 流程检查。
缺少 Skill 不阻断核心开发，按本文规范实现并报告缺失项。
必须保留 synthetic/demo_only 标签，禁用未实现模板，不输出伪热点或伪验证结果。
完成代码、运行说明、自动检查、四类样例结果和可复算报告。
```

### 来源与边界

仓库链接同时是推荐依据和后续读取入口。具体适用性是针对本项目的判断，并非仓库作者对变压器设计精度的承诺。Skill 版本会变化；实施前固定使用版本，运行测试，不照搬无关的 UI 风格或模型建议。

## 20. 技术参考与使用说明

以下用于拓扑定义和数据核查，不表示本文所有简化公式均被这些资料直接验证。

1. Texas Instruments，TIDA-010054，DAB 参考设计与 Design Guide：<https://www.ti.com/tool/TIDA-010054>；设计指南入口：<https://www.ti.com/lit/ug/tidues0f/tidues0f.pdf>。用于核对电压折算、移相、串联电感和电流之间的关系。
2. Ferroxcube，Design Tool / Steinmetz coefficients：<https://www.ferroxcube.com/en-global/design_tool/index>。用于确认材料损耗参数来源；导入前必须阅读实际系数文件的单位及条件。
3. Ferroxcube，Power Conversion Materials：<https://www.ferroxcube.com/en-global/ak_material/index/power_conversion>。用于材料选择条件核查，不能代替具体型号的数据表。

结构漏感、交流电阻和热模型须分别登记来源、有效范围及版本。演示阶段允许本文定义的 synthetic 模型完成联调；工程阶段必须建立独立验证记录。

---

**V1.5 完成标准：** 默认演示项目可完成全流程，候选在虚构几何内可排布、满足已实施的演示约束，数据和模型版本可追溯；能在数据不足、模型超域或无可行解时明确说明原因。演示数据和算法的可复算性优先于凑齐方案数量。工程模式须通过真实数据和模型验收后开放。
