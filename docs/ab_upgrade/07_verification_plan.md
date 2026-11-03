# 07 验证计划与验收标准

## 1. 验证原则

验证分成四层：

1. **数据/接口层**：schema、字段、单位、来源和版本；
2. **模型不变量层**：独立公式、守恒、几何和边界；
3. **引擎对照层**：Demo vs OpenMagnetics vs 后置 FEM/实测；
4. **产品流程层**：输入修改、任务生命周期、结果联动、报告和复算。

不能仅通过调用被测 evaluator 自己生成预期值；每个新模型至少有一个独立计算脚本或手工构造的解析样例。

## 2. 当前基线（本阶段实际执行）

| 检查 | 命令/范围 | 实际结果 |
|---|---|---|
| Python 单元测试 | `pytest -q` | 8 passed |
| V1.0 参考回归 | `python scripts/check_demo.py` | 14,400 候选、34 可行、2 Pareto；无解/工程阻断/非支持波形/可变电压通过 |
| V1.1 增量检查 | `python scripts/check_v11.py` | 联合例、气隙不可达、电压整数匝比、功率重算、质量无解通过 |
| Python 语法 | `python -m py_compile ...` | 通过 |
| JavaScript 语法 | `node --check frontend/app.js` | 通过 |
| pymoo 环境 | `python -c "import pymoo; print(pymoo.__version__)"` | 0.6.2 |
| PyOpenMagnetics 环境 | `importlib.util.find_spec('PyOpenMagnetics')` | 未安装；本阶段未加入生产依赖 |
| npx/Playwright 前置 | `Get-Command npx` | `C:\Program Files\nodejs\npx.ps1` 可用 |
| 本地浏览器流程 | Playwright | 未执行：本阶段不改 UI，且检查时 127.0.0.1:8000 未启动 |

已执行的 V1.1 联合结果摘要：`candidate_id=806befff4415`、`Np/Ns=10/5`、气隙 `0.1 mm`、一次侧总串联电感 `28.622 μH`、系统损耗 `197.429 W`；结果仍为 synthetic/demo_only。

## 3. 当前代码缺口的新增验证

以下用例应在第二阶段接入前补齐：

### 3.1 MAS schema 和单位

- 最小 DAB-SPS request 可转换为 MAS inputs；
- MAS response 可回到内部 DTO；
- V、A、Hz、H、T、m、m²、m³、kg、W、°C 无隐式 mm/L 转换；
- 缺少必填字段、单位错位、未知 enum 被阻断；
- MAS schema commit 变化能在 manifest 中发现。

### 3.2 OpenMagnetics provider

- 调用 `load_databases({})` 后查询材料/磁芯/导线数量和字段；
- `process_converter("dab", ..., use_ngspice=False)` 的 DAB 输入/输出；
- `process_inputs`、`calculate_advised_magnetics` 结果解析；
- 固定 core + coil + operating point 调用 core data/gap/inductance/loss/winding loss；
- `EngineError`、库缺失和超范围情况结构化返回；
- exact MKF/MAS commit 写入结果，不允许只写包版本。

### 3.3 几何和漏感

- P-S：窗口高度、层数、MLT、Rdc 与当前 baseline 一致；
- P-S-P：偶数/奇数 Np，`P1+P2=Np`，两个主绝缘完整存在；
- P-S-P 两个界面分别输出电容，不宣称端口等效电容；
- leakage energy 的 `L=2W/I²` 维度和两区求和独立复算；
- 组合磁芯使用自身窗口/Ae/le/Ve/外包尺寸，禁止运行时简单乘数量；
- MVB CAD 输出的绕组位置与 domain geometry 对齐。

### 3.4 电磁、损耗、热

- 每个工作点 SPS 功率平衡和周期性；
- Lm、Lleak、Lext、Lseries 全部采用一次侧参考；副边外置电感满足 `n²`；
- 一个实际外置电感跨所有工作点保持不变；
- core loss、DC、skin/proximity loss 的分项相加关系；
- 热网络能量平衡；热点未知为 null 而不是估算值；
- 气隙边缘损耗未建模时结果中仍有明确 capability/warning。

## 4. 优化与流程验收

### 必须保持的回归

1. V1.1 关闭时当前默认输入仍走 V1.0 路径；
2. 14,400/34/2 参考结果只作为当前基线，不扩展成新版本固定目标；
3. 工程模式拒绝 synthetic；非支持波形被阻断；disabled 模板不进入候选；
4. 报告可重建 input/data/model/seed/result，结果等级保持 demo_only。

### 必须新增的可变输入测试

- 功率修改：候选/电流/损耗实际变化，旧 result 失效；
- 电压比例修改：重新生成整数 Np/Ns，不能固定 Ns=Np/2；
- 漏感目标/公差修改：实际重新筛选，原因统计可变化；
- 体积/温度修改：候选重新约束，可能得到新 Pareto 或明确无解；
- 频率超范围：输入校验错误；
- 无解：显示 primary reason/top failure counts，不生成伪方案；
- 外部 provider 缺失：Demo 可运行，OpenMagnetics 模式明确 provider unavailable；
- 不同 seed：保存 seed，结果可复现/差异可解释。

## 5. 参考不变量（独立于被测函数）

建议在 `tests/verification/` 中以常量和独立小函数写入：

```text
turns_ratio = Np / Ns
Lm = mu0 * Np^2 * Ae / reluctance_total
Lseries_primary = Lleak_primary + Lext_primary
Lext_primary = Lext_secondary * (Np/Ns)^2  (secondary installation)
Psystem = Ptransformer + Pexternal
Ptotal >= 0, volume >= 0, mass >= 0
P1_turns + P2_turns = Np
all interface insulation >= rule minimum
```

同时写反例：负气隙、气隙超制造范围、量化后违反 Lm 下限、负外置电感补偿、质量/体积超限、未知模板和未知材料。

## 6. 性能、稳定性和可复算

- 记录候选总数、实际评估数、模型调用数、缓存命中、各阶段耗时；
- 固定输入/版本/seed 重跑，比较 canonical result hash 和容差指标；
- 取消任务后不应继续写入新结果；
- 后端重启后能恢复已完成结果，未完成任务状态明确；
- 长任务期间前端可重连，不因页面刷新丢失任务；
- OpenMagnetics 计算超时/引擎崩溃不影响 Demo provider。

## 7. 工程校核阶段的验收门槛

在接入真实厂家数据或把结果标为工程可信前，必须由工程人员确认：

- 材料频率/温度/B 范围和供应商数据许可；
- 真实气隙、漏感、AC 电阻、磁芯损耗和热阻的实测/仿真 benchmark；
- 绝缘协调、局放、爬电/电气间隙、机械与制造容差；
- COMSOL/FEM 网格、边界、材料和版本；
- 目标误差、置信区间和报告审核流程。

这些条件未满足前，所有 hybrid/reference 结果只能保留 `reference_only` 或 `hybrid_unqualified`，不能因为 OpenMagnetics 返回了数据就提升等级。
