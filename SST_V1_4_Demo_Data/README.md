# SST V1.4 虚构演示数据包

本数据包用于初步设计软件的开发、演示和流程联调。所有磁芯、材料、线材、绝缘材料和模型参数均为虚构，不对应任何厂家产品。`data_status=synthetic`、`engineering_approved=false`、`result_grade=demo_only` 必须从数据库贯穿至计算结果及报告。

## 1. 文件清单

| 文件 | 内容 | 数量 |
|---|---|---:|
| core_geometry_library.json | 虚构矩形框架磁芯、窗口、骨架、平均匝长所需尺寸、组合及气隙规则 | 3 |
| core_material_library.json | 虚构材料，Bsat(T)、磁导率、密度、带单位的 iGSE 系数及有效范围 | 2 |
| litz_library.json | 单丝/股数、铜截面、成品外径、电阻、绞合修正、质量 | 5 |
| insulation_library.json | 虚构薄膜、纸及主绝缘板，厚度、介电常数和热参数 | 3 |
| winding_layout_templates.json | P-S、P/2-S-P/2、分段排布模板 | 3 |
| design_rule_library.json | 窗口、电流密度相关规则及虚构绝缘规则 | 1 |
| model_registry.json | 虚构损耗、磁路、漏感、交流电阻、电容、几何及热模型 | 7 |
| sample_input_feasible.json | 100 kW、800/400 V、20 kHz、目标漏感 20 μH±10% 演示需求 | 1 |
| sample_input_infeasible.json | 极小体积上限，期望无解 | 1 |
| sample_input_engineering_blocked.json | 虚构库进入工程模式，期望阻断 | 1 |
| sample_input_unsupported.json | 45% 占空比，期望阻断 | 1 |
| run_demo.py | 仅依赖 Python 标准库的确定性流程校验脚本 | 1 |
| self_test_results.json | 已执行自检的结果 | 1 |
| reference_output/ | 可行算例结果 JSON、Pareto CSV、Markdown 报告 | 3 |
| reference_no_feasible/ | 无解算例结果及原因统计 | 3 |
| V1.4_演示数据需求补充.md | 对软件演示模式与正式工程模式的实施约定 | 1 |

P-S 为启用模板；其余两个模板保留结构定义，`enabled=false`。对应漏感/排布模型实现前必须过滤，不得复用 P-S 模型伪装成已支持交错/分段绕组。

## 2. 运行方法

解压后，在本目录执行（Python 3.9 或更新版本）：

```bash
python3 run_demo.py --self-test
python3 run_demo.py --input sample_input_feasible.json --output run_output
python3 run_demo.py --input sample_input_infeasible.json --output no_solution_output
```

脚本以完全枚举生成候选并进行非支配筛选，用于验证数据关系、制造排布与计算链路，作为后续 NSGA-II 的小空间参考。它不是完整产品，也没有实现 NSGA-II、前端、外置电感模式、任意匝比搜索或外部仿真。

默认枚举 14,400 个候选；固定参数下得到 34 个演示可行方案、2 个 Pareto 代表点。可行的含义仅为通过该脚本所实施的虚构规则与模型，不表示真实绝缘、热点、气隙边缘效应或硬件运行已经通过验证。

| 代表点 | 磁芯 | 匝数 P/S | 主绝缘 mm | 漏感 μH | 总损耗 W | 外包体积 L | 绕组节点 ℃ |
|---|---|---|---:|---:|---:|---:|---:|
| 低损耗 | DEMO_CORE_XXL | 12/6 | 2 | 18.19 | 145.2 | 3.92 | 48.5 |
| 小体积 | DEMO_CORE_XL | 12/6 | 2 | 19.82 | 262.7 | 2.70 | 51.3 |

具体值以 reference_output/results.json 为准。本例只输出两个前沿点，不为了凑足 3~5 个方案生成虚假数据。

## 3. 接入软件的顺序

1. 读取材料、绝缘、线材、磁芯、模板、规则和模型；建立 ID 索引，执行外键与单位校验。
2. 工程模式拒绝任何 synthetic 关键条目；演示模式保留标签，不允许导出成工程合格结论。
3. 按磁芯净窗口及标准线成品尺寸进行整数排布；从层数和实际径向厚度推导漏感、匝长、电阻。
4. 以实际漏感求移相和两侧 RMS，计算双侧铜损、磁芯损耗，执行双节点电热迭代。
5. 按演示约束过滤，输出非支配集、失败原因及数据版本。前端在图表和导出报告持续显示“虚构演示数据”。

生产软件的 JSON Schema 应纳入这些字段。V1.4 文档中的 `allowed_layouts=["P-S"]` 是排布名称；本包使用唯一 ID `DEMO_LAYOUT_PS`，UI 显示 P-S，后端统一通过模板 ID 引用，不同时混用两种标识。搜索中新增 `Np_min`、`Np_step`；本参考脚本仅枚举 Np 为偶数、Ns=Np/2，针对本算例的 2:1 匝比，不是通用整数匝比生成器。

## 4. 单位与主要字段

| 数据 | 字段 | 单位/约定 |
|---|---|---|
| 磁芯 | Ae_mm2/Amin_mm2/Aw_mm2 | mm²；Aw 指单个窗口，铜面积不因两窗口而重复计数 |
| 磁芯 | Ve_mm3/le_mm/core_outer_mm | mm³/mm/mm；核心计算入口换成 SI |
| 磁芯 | leg_width_mm/leg_depth_mm/window_height_mm/window_width_mm | 矩形绕线柱宽/深、窗口高/宽 |
| 磁芯 | bobbin_wall_mm/end_margin_each_mm/radial_margin_mm | 骨架厚度、单端裕量、径向余量 |
| 材料 | Bsat_vs_T/mu_e | 温度 ℃、磁密 T；磁导率无量纲 |
| 材料 | loss_parameters.ki | iGSE 系数，单位明确写入字段；不是正弦 Steinmetz k |
| 线材 | strand_bare_diameter_mm/copper_area_mm2/outer_diameter_mm | 裸单丝径、纯铜截面、成品外径 |
| 线材 | Rdc_ohm_per_m_20C | Ω/m，已含绞合修正；不再重复增加绞合长度 |
| 线材 | mass_kg_per_m | kg/m，演示只计导体质量；装配另加虚构 0.2 kg 余量 |
| 排布 | parallel_bundle_placement | radial：每匝并联根数沿径向排布，改变每层厚度 |
| 排布 | main_insulation_layers_choices | 主绝缘片数；乘材料厚度得到 dps |
| 模型 | Rca_K_W/Rwa_K_W/Rcw_K_W | K/W，双节点网络 |
| 输出 | Lm_p_H/Lleak_p_H/Lseries_p_H | H，均折算到一次侧 |
| 输出 | Cps_estimate_F/volume_envelope_L | F/L；电容为几何估算 |
| 输出 | Tc_est_C/Tw_est_C/Thotspot_est_C | ℃；本包无热点模型，热点返回 null |

## 5. 校验覆盖与简化

已检查：ID 唯一性、外键、铜截面与股数一致、铜面积小于成品外形面积、Ae 和柱截面一致、Aw 和窗口尺寸一致、磁芯体积小于外包体积、双侧电流及损耗、SPS 周期闭合及平均功率、实际几何排布、模型有效范围、电热收敛、无解返回、工程模式阻断和占空比阻断。

演示特意使用虚构 Fr 函数及热阻，以便在没有真实测试数据库时完成软件链路。Fr 不是 Dowell 或经验证的利兹线模型；谐波范围超出条目频域时仅在 demo 内明确外推，尾项按末阶 Fr 估算。磁芯感应电压近似 V1_dc；未建模一次侧漏感分配。绝缘仅检查虚构距离，不检查爬电、局放或耐压。气隙本算例为零，不证明非零气隙算法已验收。

生产工程模式必须按 V1.4 用真实数据、有效域和标定模型替换这些简化项。无需改变数据库接口，但模型更换必须改变版本及结果来源。
