# 02 OpenMagnetics 能力与许可证评估

本评估基于 2026-10-23 对用户指定仓库及其官方源码/文档的读取。所有未实际安装和运行的 API 均标记为“待验证”；本阶段没有修改 `requirements.txt`，也没有把第三方库加入生产路径。

## 1. 仓库与证据索引

| 项目 | 关注源码/文档位置 | 已确认内容 | 许可证 |
|---|---|---|---|
| MKF | `README.md`、`CAPABILITIES.md`、`src/converter_models/`、`src/advisers/`、`src/PyMKF/PyMKFWrapper.cpp` | C++ 磁性计算内核；converter、adviser、磁场、漏感、损耗和热相关能力 | MIT，见 `LICENSE.md` |
| PyOpenMagnetics | `AGENTS.md`、`PyOpenMagnetics.pyi`、`api/validation.py`、`examples/`、`src/` | Python/pybind11 包装层；公开数据库、MAS 输入、设计 adviser、损耗、绕组和绘图 API | MIT，见 `LICENSE` |
| MVB | `README.md`、`docs/`、`OpenMagneticsVirtualBuilder.builder.Builder` | MAS → CadQuery/FreeCAD 的参数化 STEP/STL/OBJ/SVG/DXF/网格生成 | MIT，见 `LICENSE` |
| MAS | `schemas/`、`docs/`、`samples/`、`data/`、`MAS.hpp` | 磁性元件的中立 JSON Schema 数据契约，包含 inputs/magnetic/outputs | Apache-2.0，见 `LICENSE.md` |

参考链接：

- [MKF README](https://github.com/OpenMagnetics/MKF/blob/main/README.md)
- [MKF 能力清单](https://raw.githubusercontent.com/OpenMagnetics/MKF/main/CAPABILITIES.md)
- [PyOpenMagnetics README](https://github.com/OpenMagnetics/PyOpenMagnetics/blob/main/README.md)
- [PyOpenMagnetics AGENTS.md](https://raw.githubusercontent.com/OpenMagnetics/PyOpenMagnetics/main/AGENTS.md)
- [PyOpenMagnetics 类型存根](https://raw.githubusercontent.com/OpenMagnetics/PyOpenMagnetics/main/PyOpenMagnetics.pyi)
- [MVB README](https://raw.githubusercontent.com/OpenMagnetics/MVB/main/README.md)
- [MAS 仓库](https://github.com/OpenMagnetics/MAS)

## 2. MAS 数据模型

### 已确认

MAS 是 pre-1.0 的 JSON Schema draft 2020-12 数据模型。完整文档包含：

- `inputs`：`designRequirements` 和 `operatingPoints`，描述目标、拓扑、温度、尺寸和激励；
- `magnetic`：core、material、gapping、coil、bobbin、wire、绝缘和绕组描述；
- `outputs`：电感、磁密、磁芯/绕组损耗、温度、寄生电容和其他计算结果。

MAS 数值字段按照规范使用固定 SI 单位，值是裸数字而不是 `{value, unit}`；公开说明明确频率使用 Hz、长度使用 m、温度使用 °C、磁密使用 T。MAS 范围包括变压器、储能电感、扼流圈和 DAB 等拓扑，并提供材料、标准磁芯、导线和骨架数据目录。

这与现有项目的“前端工程单位、内部 SI”原则兼容，但字段名和嵌套结构不同。不能把当前 `operating_points` 直接当作 MAS `operatingPoints`，必须有版本化转换器。

### 待验证

- 当前 MAS 主分支的 schema 版本仍是 pre-1.0，minor 版本允许破坏性变化；接入时必须固定 commit/tag，不能只依赖 `main`。
- 用户指定的 `OpenMagnetics/MAS` 页面当前包含 PSMA 迁移/治理信息；实际发布包、数据库字段、第三方数据许可证和版本号必须在集成时锁定并记录。
- 当前项目的 `P-S-P`、组合磁芯、外置电感和 `demo_only` 元数据没有直接等价的 MAS 扩展约定，不能未经验证地塞入自定义字段并宣称标准兼容。

## 3. MKF 核心能力

### 3.1 磁芯、材料和导线数据库

MKF/PyOpenMagnetics 暴露材料、磁芯形状、导线、骨架等查询能力，如 `get_core_materials()`、`get_core_shapes()`、`get_wires()`、`get_bobbins()` 及按名称查找函数。MAS 仓库说明当前数据库包含数百个材料、磁芯形状、导线和骨架，具体数量会随 commit 变化。

适合用来替代当前 Demo 的“数据查询层”，但不应直接覆盖现有 synthetic JSON；建议以 `SourceRecord` 标记 `openmagnetics:<repo>@<commit>`，并保留 Demo provider 作为回归 provider。

### 3.2 初步磁芯选型和设计 adviser

MKF `src/advisers/` 具有 `CoreAdviser`、`CoilAdviser`、`WireAdviser`、`MagneticAdviser` 及多个 `MagneticFilter*`。能力清单明确列出 `get_advised_core()`、`calculate_gapping_constraints()`、`optimize_gap_and_turns_binary_search()`、`get_advised_coil()`、`get_advised_sections()` 和 `score_magnetics()`。

PyOpenMagnetics 公开的高层路径是：

```python
PyOM.load_databases({})
processed = PyOM.process_converter("dab", converter_dict, use_ngspice=False)
processed = PyOM.process_inputs(processed)
designs = PyOM.calculate_advised_magnetics(processed, 5, "standard cores")
```

也有一站式 `design_magnetics_from_converter()`，内部组合 converter 与 adviser。当前 PyOpenMagnetics 的 AI 指南特别要求使用位置参数、直接传 Python dict、先加载数据库，并使用小写带空格的 core mode（例如 `standard cores`）；这些不是本项目可自行猜测的接口约定。

适配判断：可用于 A/C 类“提供初步候选和基准”，不直接替代当前 SST 结构优化，因为当前项目需要控制整数 Np/Ns、P-S/P-S-P 分块、漏感目标、外置电感和系统边界。

### 3.3 气隙、励磁电感和磁场

PyOpenMagnetics 类型存根确认存在：

- `calculate_core_data(core, include_material_data=False)`；
- `calculate_gap_reluctance(gap, model)`，返回磁阻和边缘系数；
- `calculate_inductance_from_number_turns_and_gapping(core, coil, operating_point, models)`；
- `get_core_temperature_dependant_parameters(...)`；
- `calculate_saturation_current(...)`。

MKF README 的默认模型列表包含 Zhang 气隙磁阻、Rosh(en) 边缘磁场和可选 `IMAGED_MMF_SHEETS`。这比当前均匀等效磁阻模型更适合作为气隙/磁场基准，但需要独立验证模型输入、气隙分布和组合磁芯语义。

### 3.4 磁芯损耗、绕组 AC/DC 损耗和温升

MKF README 列出 iGSE、厂商模型、LOSS_FACTOR、Steinmetz、Roshen 等磁芯损耗模型；导线损耗按 round、litz、rectangular/planar、foil 分为 skin/proximity 模型。PyOpenMagnetics 类型存根确认：

- `calculate_core_losses(core, coil, inputs, models)`；
- `calculate_winding_losses(...)`；
- `calculate_ohmic_losses(...)`；
- `calculate_skin_effect_losses(...)`；
- `calculate_proximity_effect_losses(...)`。

MKF 列出 `MANIKTALA` core temperature 模型，但 README 同时说明温度模型“not really used”；所以不能把存在的符号等同于已经满足 SST 热点温度需求。当前项目的双节点热网络仍应作为 B/C 适配和回归基线，直到真实温升校核建立。

### 3.5 绕组自动排布和漏感

PyOpenMagnetics 的 `wind()` 支持 `repetitions`、`proportion_per_winding`、`pattern` 和 `margin_pairs`，并返回 sections/layers/turns 描述；`pattern` 可以表示交错序列。`calculate_winding_losses` 需要完整 coil/waveform 输入。

MKF 的能力清单说明漏感是通过此前计算的磁场进行积分的自有模型，而非只用一个固定系数。该能力适合 P-S/P-S-P 排布的基础场计算和验证，但当前代码的分区能量法仍应保留作为可回归的 B 模型。尚未确认 OpenMagnetics 的 P-S-P 端口等效电容、SST DAB 统一参考侧和外置串联电感系统模型，因此不能直接宣称可替换现有 V1.1 漏感链。

## 4. PyOpenMagnetics Python API 与依赖

### 已确认 API

来自当前 `PyOpenMagnetics.pyi`/`AGENTS.md` 的可用入口包括：

| 目的 | 入口 |
|---|---|
| 初始化数据库 | `load_databases({})` |
| 查询库 | `get_core_materials`, `get_core_shapes`, `get_wires`, `get_bobbins` |
| DAB/其他拓扑处理 | `process_converter("dab", converter, use_ngspice=False)` |
| MAS 输入校验/派生 | `process_inputs(inputs)` |
| 高层设计 | `design_magnetics_from_converter(...)` |
| adviser | `calculate_advised_cores(...)`, `calculate_advised_magnetics(...)` |
| core/gap | `calculate_core_data`, `calculate_gap_reluctance`, `calculate_inductance_from_number_turns_and_gapping` |
| 损耗 | `calculate_core_losses`, `calculate_winding_losses`, skin/proximity/ohmic 函数 |
| 排布 | `wind`, `wind_by_sections` |
| 可视化 | `plot_core`, `plot_sections`, `plot_layers`, `plot_turns`, `plot_field` |
| 结果导出 | `export_magnetic_as_subcircuit` |

### 调用约束

当前官方指南指出：需要先调用 `load_databases({})`；设计函数用位置参数；传 dict 而不是 `json.dumps` 字符串；`EngineError` 是引擎错误类型。构建信息可以通过 `__mkf_commit__` 和 `__mas_commit__` 记录 provenance。

### 本机状态

本机检查结果：`pymoo==0.6.2` 已安装，`npx` 可用，`PyOpenMagnetics` 的 `importlib.util.find_spec()` 返回 `None`。因此本阶段没有安装、编译或修改生产依赖。第二阶段需单独建立可选 `openmagnetics` 环境/extra，固定 Python、编译器、MKF/MAS commit 和平台 wheel。

## 5. MVB 参数化三维模型

MVB README 确认 `OpenMagneticsVirtualBuilder.builder.Builder` 支持 `CadQuery`（默认、Python 原生）和 `FreeCAD`（需要外部安装），可通过 `get_families()` 查询形状族，通过 `get_core()` 生成 STEP/STL，通过 `get_magnetic()` 从 MAS core/coil/bobbin/turns 生成完整组件。输出还包括 OBJ、SVG、DXF、FreeCAD macro 和网格等，具体能力随 CAD engine 变化。

推荐位置：作为 C/D 类后置展示和工程交付，不放在初始优化内环。优化器先输出可验证 MAS/内部结构，再异步生成 CAD；CAD 失败不应让电磁候选变成“无解”。MVB 对当前虚构组合磁芯、三块 P-S-P 和特殊引线结构的支持需要单独测试。

## 6. 许可证和商业集成条件

- MKF、PyOpenMagnetics、MVB 当前仓库许可证页面显示为 MIT，核心要求是保留版权和许可声明，并按“原样”承担免责声明。
- MAS 是 Apache-2.0，分发或修改时要保留许可证、版权/归属和 NOTICE（若有），修改文件需说明变更；Apache-2.0 还包含专利授权/终止条款。
- 这些仓库许可证不自动覆盖内置商业厂家数据、第三方论文/数据表、编译工具链、ngspice、CadQuery、FreeCAD 或 PyPI 传递依赖。产品集成必须做 SBOM、NOTICE、依赖许可证和数据授权审查。
- `MIT/Apache-2.0` 允许商业集成的判断只适用于仓库代码本身；不能据此宣布所有数据库内容、模型参数或名称均可商用。

许可证原文：

- [MKF MIT](https://raw.githubusercontent.com/OpenMagnetics/MKF/main/LICENSE.md)
- [PyOpenMagnetics MIT](https://raw.githubusercontent.com/OpenMagnetics/PyOpenMagnetics/main/LICENSE)
- [MVB MIT](https://raw.githubusercontent.com/OpenMagnetics/MVB/main/LICENSE)
- [MAS Apache-2.0](https://raw.githubusercontent.com/OpenMagnetics/MAS/main/LICENSE.md)

## 7. 适合接入与不可直接接入

### 适合优先接入

1. MAS schema 校验和内部数据适配；
2. OpenMagnetics 材料、磁芯形状、导线、骨架查询；
3. core/gap/inductance 基准计算；
4. core loss、litz skin/proximity loss 基准计算；
5. 以 `wind()` 生成标准 P-S/交错绕组结构的独立对照；
6. MVB 后置生成结构图和 STEP/STL。

### 必须先验证后再接入

1. DAB-SPS 输入字段能否完整表达现有多工况、一次侧参考、漏感目标和外置电感；
2. P-S-P 分块同向串联、两处绝缘、连接损耗和实际能量法漏感是否与验收基准一致；
3. 组合磁芯是否有可验证的 MAS 结构表达和等效磁路；
4. OpenMagnetics 的热模型能否提供当前工程规则要求的绕组/磁芯/热点边界；
5. 数据库的厂家许可、版本、字段精度、温频有效范围；
6. PyOpenMagnetics wheel 在 Windows 当前项目 Python 环境的编译/运行兼容性。

### 不应直接替换

当前没有证据支持用 OpenMagnetics adviser 直接替代 SST 系统级 NSGA-II、P-S/P-S-P 自研漏感、外置电感系统匹配、结果版本追溯或 Demo/工程模式门禁。
