# 01 当前软件代码审查

审查对象：仓库 `codex/v1.1-four-features`，审查依据为当前工作区源码、虚构数据包、测试和脚本，而不是 README 对功能的概括。

## 1. 结论摘要

当前项目已经是可运行的 FastAPI + 原生 HTML/CSS/JavaScript Demo。计算主链不是静态结果：参考枚举和 NSGA-II 最终都经过 `backend/app/core/engine.py:evaluate_candidate()`，输入快照在后端任务完成后写入 `.runtime/*.json`，结果页从同一任务结果渲染。

可以继续使用的核心是：

- `load_database()`、`data_snapshot()` 和 `validate_input()` 的数据/模式隔离框架；
- `winding()` 的参数化排布与 Rdc/MLT 输出结构；
- `sps_segments()` 的确定性 SPS 分段电流、功率平衡和 RMS 计算；
- V1.1 的 `evaluate_candidate_v11()`、`_gap_selection()`、`_psp_leakage_energy()`、外置电感折算及系统边界目标；
- `candidate_catalog()` 和 `evaluate_candidate()` 作为统一候选计算入口；
- `nsga2_optimization()`、任务状态 API、取消、结果快照和报告导出；
- 当前原生前端的输入、任务进度、Pareto 散点、方案详情和数据状态页面。

最重要的技术缺口是：

1. 物理模型与数据目前全部是 synthetic，`DEMO_FR_EMPIRICAL`、热阻、IGSE 参数、质量余量等不能证明工程精度。
2. V1.1 组合磁芯和 P-S-P 目前是自定义合成模型，尚未与可验证的真实磁芯/骨架/绕组数据建立映射。
3. 当前 NSGA-II 的搜索变量实际上是“候选目录索引”，并在算法前完整评估候选目录；它能完成 Demo 多目标筛选，但还不是面向连续/混合离散工程变量的独立优化内核。
4. 结果页只渲染 `pareto`，不展示全部 `feasible` 方案；这解释了“求解显示有可行方案但结果页只看到前沿”的现象，后续应明确区分可行池与 Pareto 前沿。
5. 当前服务状态保存在进程内 `TASKS` 加 `.runtime` 快照，缺少数据库、并发隔离、版本迁移和任务生命周期治理。

## 2. 实际代码结构与依赖

| 功能 | 实际位置 | 关键入口 | 输入 | 输出/下游 |
|---|---|---|---|---|
| HTTP/静态文件 | `backend/app/main.py` | `app`、`create_optimization()`、`get_optimization()` | JSON 设计输入、任务模式 | FastAPI API、`frontend/` |
| 数据加载 | `backend/app/core/engine.py` | `load_database()` | 11 个 JSON 数据文件 | 统一 `db` 字典 |
| 数据快照 | 同上 | `data_snapshot()` | `db` | 版本、文件 SHA-256、记录数 |
| 输入校验 | 同上 | `validate_input()` | 设计输入、`db` | valid 或 `InputValidationError` |
| V1.0 候选 | 同上 | `reference_enumeration()` | 输入、数据库 | 14,400 候选、可行池、Pareto |
| V1.1 候选 | 同上 | `candidate_catalog()` | 输入、数据库 | `(core,Np,Ns,wires,parallel,layout,inductor,gap)` 元组列表 |
| 单候选 | 同上 | `evaluate_candidate()` | 输入、数据库、genes | 方案指标或 `CandidateFailure` |
| 几何/绕组 | 同上 | `winding()` | 匝数、线材、并联根数、窗口几何 | 层数、每层匝数、MLT、Rdc、铜截面、质量 |
| SPS 电流 | 同上 | `sps_segments()` | 两侧电压、频率、L、功率、Lm | phase、分段波形、传输/原边 RMS |
| 频谱/AC 损耗 | 同上 | `sampled_spectrum()`、V1.0/V1.1 evaluator 内 `fr()` | SPS 分段、频率、匝比、层数 | 谐波能量、合成交流电阻倍率 |
| 磁芯损耗 | 同上 | evaluator 内 `pcore` | `ki,alpha,beta`、f、Bpk、Ve、Tc | Pcore |
| 热计算 | 同上 | evaluator 内双节点迭代 | Pcore、铜损、热阻网络、环境温度 | Tc、Tw、迭代数、温升 |
| 漏感 | 同上 | `evaluate_candidate_v10()`、`_psp_leakage_energy()` | MLT、层厚、主绝缘、窗口高度、分块几何 | `Lleak_p_H` 与分区详情 |
| 气隙 | 同上 | `_gap_selection()` | Ae、le、μe、匝数、气隙范围/步进、Lm/Im 约束 | 量化气隙、Lm、量化误差、状态 |
| 组合磁芯 | 同上 | `_core_record()` | 单体/assembly ID | 独立组合条目参数 |
| 外置电感 | 同上 | V1.1 evaluator | 离散库 ID、安装侧、L/Rdc/热阻 | 一次侧等效 L、器件损耗/温度、系统目标 |
| 多目标 | 同上 | `nsga2_optimization()`、`pareto_front()` | 候选目录、目标 `[loss,volume]` | 可行池、非支配前沿 |
| 前端输入/任务 | `frontend/index.html`, `frontend/app.js` | `formToInput()`、`start()`、`poll()` | 用户输入 | `/api/v1.4/...` |
| 前端结果 | `frontend/app.js` | `renderResult()`、`renderChart()`、`renderTable()`、`selectCandidate()` | 任务结果 `pareto` | 散点、表格、SVG 排布、导出按钮 |

依赖关系是：前端 → FastAPI → `validate_input` → 任务线程 → `reference_enumeration` 或 `nsga2_optimization` → `evaluate_candidate` → 结果快照/报告；没有独立的服务接口层或第三方适配层。

## 3. 数据库、字段和数据来源

`load_database()` 先读取原始 V1.4 数据：

- `core_material_library.json`：2 个虚构磁性材料，包含 `mu_e`、Bsat(T)、B 降额、iGSE/Steinmetz 形式参数和有效范围；
- `core_geometry_library.json`：3 个虚构单体磁芯，包含 Ae、le、Ve、窗口、骨架/工艺尺寸、质量、气隙范围与步进；
- `litz_library.json`：5 个虚构利兹线，包含股径/股数、铜面积、成品外径、Rdc、质量和 AC 模型 ID；
- `insulation_library.json`：3 个虚构绝缘材料，包含厚度、介电常数、热参数和限制说明；
- `winding_layout_templates.json`：3 个模板，其中仅 `DEMO_LAYOUT_PS` 启用，P-S-P 与 split 模板在基础数据中禁用；
- `design_rule_library.json`：1 套合成窗口、绝缘和 B 降额规则；
- `model_registry.json`：7 个合成模型，包括漏感、交流电阻和双节点热网络。

随后以 additive 方式合并 `v1_1/`：2 套独立组合磁芯、4 个离散外置电感（含零电感旁路）、1 个启用的 P-S-P 模板和 5 个 V1.1 模型。加载器检查 ID、材料、窗口面积、模板、模型、导线截面和电感非负性，并要求每条记录 `data_status=synthetic`。

这套数据关系自洽但不是真实厂家数据库；`engineering_approved=false` 和 `synthetic` 被保留到结果和报告。数据哈希由 `data_snapshot()` 计算，但当前 `data_version` 是代码中的固定版本字符串，不是从数据包 manifest 自动推导，后续应补充 manifest/迁移策略。

## 4. 计算链逐项判断

### 4.1 真实物理结构与计算骨架

- `winding()` 按实际线材外径、窗口高度、层绝缘、工艺间隙和并联根数逐层放置，计算层数、MLT、分支长度、Rdc、铜面积和质量。这是明确的参数化几何/电阻计算，但没有厂家骨架细节、端部引线、真实绕制工艺误差或端口连接网络。
- `sps_segments()` 以分段线性电感电流计算传输 RMS 和原边 RMS，检查周期性、平均电流和功率平衡。它只接受当前实现的 DAB SPS、50% 对称桥方波假设。
- `evaluate_candidate_v10()` 使用 `Lm=mu0*Np²*Ae/(le/mu_e)`，P-S 1D 漏感式，离散频谱加 `Fr`，合成磁芯损耗和两个节点热网络。
- `evaluate_candidate_v11()` 复用上述链，增加量化气隙、P-S-P 两个界面能量近似、组合条目、外置电感和系统边界目标。

### 4.2 经验常数、近似和虚构项

- 所有数据值都是虚构；`DEMO_FR_EMPIRICAL` 是明确标注的人工集成测试函数，不是 Dowell/Litz 已校准实现。
- 磁芯损耗虽然采用 iGSE 形状的方程，但参数来自虚构材料，不能作为真实材料损耗。
- `Rca/Rwa/Rcw` 对所有演示磁芯共享；热点模型为 `null`。
- V1.1 组合磁芯条目由独立 JSON 给出，模型假设是组合条目自身的合成 Ae/窗口/外包尺寸，不是由运行时把单体参数简单相乘；这些组合数据本身仍是 synthetic。
- 外置电感只计算离散器件的实际安装侧电流与 Rdc 损耗，并使用一阶虚构热阻；没有寄生、磁芯损耗和动态饱和。
- P-S-P 漏感是两个分区的线性化能量近似；不是 FEM 或经过实测标定的场解。
- 气隙未计算边缘磁通附加损耗；绝缘仅做演示规则检查，不是 IEC 协调结论。

### 4.3 未实现、界面存在但结果受限的功能

- `Thotspot_est_C` 明确返回 `null`，界面也显示“未建立 · null”。
- 基础数据中 disabled 的 P-S-P/SPLIT 模板不会进入 V1.0 搜索；V1.1 用独立启用的 `DEMO_LAYOUT_PSP_V1_1` 走另一条计算分支。
- 工程模式只做 synthetic 阻断，不提供真实数据的替代计算。
- 未见 FEM/CFD、实测校准、磁芯温度场、绝缘耐压/局放、EMI、ZVS 或 COMSOL 联机计算。
- 前端有 Pareto 图、SVG 排布和导出；没有完整的可行池浏览、误差带、引擎能力对比、版本兼容管理或后台持久化数据库。

## 5. 候选生成、约束和 NSGA-II

### V1.0 参考路径

`reference_enumeration()` 的笛卡尔积是 3 个核心 × 12 个 Np × 5×5 根线材 × 2×2 并联根数 × 4 个主绝缘层数组合 = 14,400。参考模式的 `evaluate_candidate_v10(..., reference_mode=True)` 内部固定 `Ns=Np//2`，这是仅用于默认 800/400 V 回归的旧假设；它不是可变电压模式。

每个候选经匝比、绝缘、排布、Lm、漏感、体积、质量、波形/磁芯有效范围、电流密度、热和温度约束，失败原因进入 `Counter`。当前回归真实得到 34 个可行方案和 2 个 Pareto 点。

### V1.1 可变路径

`candidate_catalog()` 根据第一工作点 `V1/V2` 和 `turns_ratio_error_max` 重新生成每个 `Np` 对应的整数 `Ns` 范围；同时枚举启用的单体/组合磁芯、线材、并联根数、模板、外置电感和搜索气隙。V1.1 的 `evaluate_candidate_v11()` 不会继续固定 `Ns=Np/2`。

### 当前优化器的实际行为

`nsga2_optimization()` 先完整遍历 `catalog`，用同一候选 evaluator 生成可行种子和失败统计，再把一个整数索引映射为“可行索引”交给 `pymoo` 的 `NSGA2`。问题定义为一变量、两个目标、一个恒定可行约束；SBX/PM 作用在索引上，最终仍对整个已缓存可行池调用 `pareto_front()`。

因此：

- 它真实调用了候选模型和 NSGA-II API，结果不是预存方案；
- 但候选目录预评估使其在当前规模上更像“离散可行池 + NSGA-II 重采样/去重”，而不是直接在多个设计变量上进化；
- 约束主要在 evaluator 中抛出 `CandidateFailure`，不是一个可解释的多约束向量；
- `pareto_front()` 是自定义二维最小化前沿筛选，只保留 `objectives` 不同且非支配的方案。

第二阶段若接入 OpenMagnetics，应先保留这个行为作为基线，再引入正式的混合离散变量、约束向量和独立预算/收敛记录，不能直接替换而丢失回归可比性。

## 6. API、结果存储和前端

### API

`backend/app/main.py` 提供：

- `GET /health`：引擎版本和 Demo 状态；
- `GET /api/v1.4/data/summary`、`GET /api/v1.4/data/{kind}`：数据库状态/原始记录；
- `GET /api/v1.4/examples/default`：默认输入；
- `POST /api/v1.4/projects/validate`：输入校验；
- `POST /api/v1.4/designs/evaluate`：单候选评估；
- `POST /api/v1.4/optimizations`：创建 reference/NSGA-II 任务；
- `GET /api/v1.4/optimizations/{id}`：任务/结果；
- `POST /api/v1.4/optimizations/{id}/cancel`：取消；
- `GET /api/v1.4/designs/{id}/report?format=md|csv|json`：报告导出。

任务在进程内 `TASKS` 维护，完成后写 `.runtime/<task_id>.json`；应用启动时会重新加载已有快照。异常被标记为 `failed`，无解是正常完成状态 `no_feasible_solution`。

### 前端

`frontend/index.html` 是中文工程工作台的三视图：需求与寻优、数据库状态、结果与报告；`app.js` 的 `formToInput()` 将表单写回输入快照，`markDirty()` 隐藏旧结果并显示失效提示，`start()` 创建任务，`poll()` 更新进度，`renderResult()` 只显示 Pareto 结果，`selectCandidate()` 使用结果中的几何字段生成 SVG。

按照 UI UX Pro Max 的审查原则，当前 UI 已有可见标签、焦点样式、viewport、错误横幅和加载/取消反馈；但仍需要在后续阶段补充键盘导航/ARIA 状态、可行池分页、失败原因就地提示、长任务重连、移动端表格交互和不依赖颜色的状态表达。当前阶段不改 UI，仅记录为目标架构约束。

## 7. 测试与演示证据

已在本阶段实际执行：

- `pytest -q`：8 passed；
- `python scripts/check_demo.py`：14,400 候选、34 可行、2 Pareto、无解诊断、工程模式和非支持波形阻断、可变电压 NSGA-II 均通过；
- `python scripts/check_v11.py`：联合气隙/P-S-P/组合磁芯/外置电感、气隙不可达、电压整数匝比、功率重算、质量无解通过；联合样例记录 `Np=10,Ns=5,gap=0.1 mm,Lseries=28.622 μH,system loss=197.429 W`；
- `node --check frontend/app.js`：通过；
- `python -m py_compile ...`：后端和测试文件通过。

测试输出有 requests 的依赖警告，但不影响上述测试退出状态。

未在本阶段执行：真实 OpenMagnetics 安装/编译、OpenMagnetics API 运行、浏览器 Playwright 流程、真实厂家数据校准、FEM/COMSOL 对比。
