# 06 分阶段实施计划

本计划遵循用户给定顺序。第一阶段只完成审查与计划；下面的第二阶段起才是开发任务。

## 阶段 1：OpenMagnetics 接入及基准测试

### 目标

建立可选的 PyOpenMagnetics/MKF provider、MAS schema 校验和最小独立基准；不改变默认 Demo provider。

### 修改/新增模块

- 新增 `backend/app/domain/` 内部 DTO 与 service ports；
- 新增 `backend/app/adapters/openmagnetics/`，封装数据库加载、MAS 转换、EngineError；
- 新增 `backend/tests/openmagnetics/`，使用隔离环境/固定 third-party commit；
- 仅将 `engine.py` 包装为 `DemoProvider`，不改其计算公式；
- 依赖使用可选 extra 或独立 lockfile，不改默认生产安装。

### 输入/输出

`DesignRequest` → MAS `inputs` → PyOM processed input / core/gap/loss result → internal DTO + provenance。

### 测试

- MAS schema valid/invalid；
- PyOM `load_databases`、`process_converter("dab",...)`、`process_inputs`；
- 一个固定 core/material/wire 的 inductance/core-loss/winding-loss case；
- Demo provider 回归仍为 14,400/34/2；
- PyOM 不可安装时 Demo 仍可运行。

### 验收

- 能记录 MKF/MAS/PyOM exact commits；
- 第三方异常不会变成默认零损耗；
- 仅显式选择 OpenMagnetics provider 时才调用第三方；
- 未通过独立基准前 provider 状态为 `reference_only`。

### 依赖

无；是后续所有阶段的前置。

## 阶段 2：材料、磁芯、利兹线数据库

### 目标

建立版本化 `DataRegistry`，以 MAS/OpenMagnetics 为可选来源，与现有 Demo JSON 并列。

### 修改/新增模块

- `DataRegistry`、source/license manifest、字段映射；
- 数据摘要 API 和 UI 数据页增加 provider/version/status；
- 现有 `load_database()` 迁移到 Demo provider wrapper，不删除 JSON。

### 输入/输出

搜索条件 → `MaterialRecord/CoreRecord/WireRecord/InsulationRecord`；每项含 SI、valid range、source、license、approval。

### 测试/验收

- 记录字段完整性、单位和来源；
- 数据版本变化触发输入/结果失效；
- synthetic/engineering 门禁；
- 至少一个真实公开记录的人工核对；
- 数据库查询失败可解释，不能静默混用来源。

### 依赖

阶段 1 的 MAS adapter 和许可证/SBOM 结论。

## 阶段 3：参数化磁芯与绕组结构

### 目标

将当前 `winding()` 的结构输出扩展为标准 block/section/layer/turn domain geometry，并对接 PyOM `wind()` 作为独立对照；必要时接 MVB 生成 CAD。

### 修改/新增模块

- `GeometryService`、PS/PSP layout provider；
- MAS coil/bobbin adapter；
- 后置 MVB exporter；
- 前端结构示意使用 domain geometry，而不是硬编码 SVG 尺寸。

### 测试/验收

- P-S、P-S-P 奇偶匝、绝缘、并联、层数和窗口边界；
- `P1+P2=Np`，端点和引线不重复；
- 现有 Demo 几何输出兼容；
- MVB 失败不影响优化任务，导出文件可复现。

### 依赖

阶段 2 的 core/wire/bobbin records。

## 阶段 4：电磁、损耗、漏感及热计算

### 目标

把 current evaluator 拆成 service provider；OpenMagnetics 提供基础参考，B 类 SST 模型保留并逐项比较。

### 修改/新增模块

- `ElectromagneticService`：DAB/SPS 适配、Lm、磁密；
- `CoreLossService`、`WindingLossService`；
- `LeakageService`：PS/PSP 分区能量、第三方对照；
- `ThermalService`：当前双节点 baseline、后续工程热网络；
- constraint residual DTO 和诊断。

### 测试/验收

- 功率平衡、周期性、能量/电感单位；
- core loss、DC/AC loss 与独立算例；
- 气隙范围/量化/边缘系数；
- P-S-P 漏感两界面和端口电容不相加；
- 热平衡、热点 null 语义；
- 同一 candidate 固定 provider/model 时 bitwise 或容差可复算。

### 依赖

阶段 1–3；COMSOL/FEM 不作为本阶段硬依赖。

## 阶段 5：多目标优化与工程规则

### 目标

让 NSGA-II 使用 domain evaluator，支持混合离散变量、结构化约束、可行池/Pareto 分离、预算和收敛记录。

### 修改/新增模块

- `OptimizationService`、mixed-variable adapter；
- 把当前 `candidate_catalog` 变成明确的 search space provider；
- 约束 residual/失败原因 aggregator；
- UI 增加 provider、可行池、Pareto 和模型能力状态。

### 测试/验收

- 保留 V1.0 reference baseline；
- 多 seed 重复性和预算；
- 修改功率、电压比、频率、漏感、温度、体积、质量均触发新 hash 和新计算；
- 无解原因来自实际失败统计；
- 旧结果不能混到新输入；
- Pymoo 约束语义符合 `g(x)<=0`，选择前复评 candidate。

### 依赖

阶段 4 的服务接口和完整结果 DTO。

## 阶段 6：COMSOL 数据接口与工程校核

### 目标

把候选、材料、损耗和边界导出为 COMSOL/FEM 可校核输入，并把校核结果作为外部证据返回，不混入未验证的自动工程结论。

### 修改/新增模块

- `ExternalValidationProvider`；
- COMSOL/CSV/MAS interchange；
- 校核任务、网格/版本/边界/残差记录；
- 报告增加模型对比和审核状态。

### 测试/验收

- 几何坐标与内部排布一致；
- 频率、匝数、电流、材料和气隙单位一致；
- 结果可回读并绑定 candidate/model hash；
- 校核失败、超时、缺数据均不会伪造工程可信标记；
- 至少一个实测或仿真 benchmark 达到预设误差标准（标准需在该阶段由工程人员确认）。

### 依赖

阶段 1–5、COMSOL 环境/授权、真实或审核材料数据。

## 第二阶段最小可实施任务

建议只做“OpenMagnetics provider 基准 + MAS adapter + Demo provider 保持原样”，不同时改优化器或 UI。最小交付：

1. 固定 PyOpenMagnetics/MKF/MAS 版本和可选安装说明；
2. 用当前一个 DAB 设计输入生成 MAS 输入并通过 schema；
3. 读取一个 core/material/wire，完成 core data、气隙电感、core loss、winding loss 的独立调用；
4. 将结果转回内部 DTO，带 source/commit/model/valid range；
5. 与当前 Demo evaluator 生成结构化差异报告；
6. Demo 回归全部保持通过。

第二阶段验收不要求把 OpenMagnetics 结果接入 NSGA-II；只有上述基准结果稳定且许可证/数据来源清楚后，才进入阶段 2 数据 registry。
