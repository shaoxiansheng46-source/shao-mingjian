# Phase 2：PyOpenMagnetics API 映射

## 已确认的官方 API

下列函数均在隔离环境中实际发现，并按安装版本的 docstring/pyi 核对参数。数据库访问和基础物理计算由 `OpenMagneticsProvider` 负责，Provider 对外只返回本项目定义的标准结果。

| OpenMagnetics API | Provider/验证入口 | 输入重点 | 输出处理 |
|---|---|---|---|
| `load_databases({})` | `OpenMagneticsProvider.initialize()` | Python dict | 记录初始化状态和版本 |
| `get_core_materials()` | `get_core_materials()` | 无 | 只输出名称、厂家、材料族、密度等摘要 |
| `get_core_shapes()` | `get_core_shapes()` | 无 | 只输出名称、族、类型、SI 尺寸摘要 |
| `get_wires()` | `get_wires()` | 无 | 只输出名称、导线类型、标准、直径摘要 |
| `find_core_material_by_name(name)` | 同名 Provider 方法 | 数据库名称 | 统一 lookup 结果 |
| `find_core_shape_by_name(name)` | 同名 Provider 方法 | 数据库名称 | 统一 lookup 结果 |
| `find_wire_by_name(name)` | Provider 扩展方法 | 数据库名称 | 统一 lookup 结果 |
| `calculate_core_data(core, False)` | `calculate_core_data()` | MAS Core functional description | 归一化 Ae、le、Ve、minimumArea |
| `calculate_inductance_from_number_turns_and_gapping()` | `calculate_inductance()` | core、coil、operating point、reluctance model | `H` |
| `calculate_core_losses()` | `calculate_core_losses()` | core、coil、Inputs、models | `W`、B 峰值、温度摘要 |
| `wind()` | `wind()` | coil、重复数、比例、pattern、margin | 绕组块、section/layer/turn 数量 |
| `calculate_ohmic_losses()` | `calculate_ohmic_losses()` | coil、operating point、温度 | `W` |
| `calculate_winding_losses()` | `calculate_winding_losses()` | 完整 magnetic、operating point、温度 | 总铜损及每绕组 DC/skin/proximity 摘要 |
| `calculate_skin_effect_losses()` | `calculate_skin_effect_losses()` | coil、含 harmonics 的累积损耗对象、温度 | 缺少 harmonics 时保留错误 |
| `calculate_magnetic_field_strength_field()` | proximity 路径内部调用 | operating point、processed magnetic | 只作为内部字段输入 |
| `calculate_proximity_effect_losses()` | `calculate_proximity_effect_losses()` | coil、温度、累积损耗、磁场 | 缺少前置数据时保留错误 |

## 重要 API 约束

1. `calculate_core_data` 要求 core functional description 中有 `type`、`shape`、`material`、`gapping` 等字段；在 Provider 内补齐兼容默认值，但不把缺失气隙自动解释成目标电感。
2. `calculate_winding_losses` 的 core 必须有 `processedDescription`。Provider 内部先调用 `calculate_core_data`，避免把第三方生命周期细节泄露给调用者。
3. `calculate_core_losses` 的模型示例为 `{"coreLosses": "IGSE", "reluctance": "ZHANG", "coreTemperature": "MANIKTALA"}`。
4. `wind` 可以传绕组名称、匝数、并绕数和数据库 wire 名称；实际验证使用了 `Bobbin ETD 54`。
5. 独立 skin/proximity API 需要 process-inputs 产生的 harmonics 和字段分布。基准程序对当前简化四点波形实际调用后保留 `MISSING_DATA: Current is missing harmonics`，没有静默置零。

## 版本与异常

所有结果带有：

- `source=OpenMagnetics/MKF via PyOpenMagnetics`；
- `data_status=external_database`；
- PyOpenMagnetics 版本、MKF commit、MAS commit；
- `model_version=sst-openmagnetics-adapter-0.1.0`；
- `status`、`errors` 和计算名称。

PyOpenMagnetics `EngineError`、查找失败、输入缺字段和第三方返回缺少数值，均被转换为结构化错误；不会改写成 0。
