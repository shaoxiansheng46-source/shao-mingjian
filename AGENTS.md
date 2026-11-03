# SST 设计软件仓库协作规范

本文件是本仓库根目录的新增项目规范。提交前已检查仓库，没有发现更高优先级的现有 `AGENTS.md`；若未来在子目录增加更具体的指令，子目录指令只对其目录生效并优先于本文件。

## 当前版本边界

- 当前基线为 `codex/v1.1-four-features`，包含可运行的 V1.0/V1.1 虚构数据 Demo。
- 第一阶段 A+B 升级只做源码审查、OpenMagnetics 评估、架构和验证方案，不重构生产代码、不替换现有算法、不修改生产依赖、不删除演示数据。
- 当前第二阶段经用户明确授权：可以新增独立的 `backend/app/providers/openmagnetics/` Provider、MAS 适配器、`examples/` 基准程序、适配器测试和 `docs/ab_upgrade/phase2/` 文档；这些代码不得接入现有 NSGA-II、合成计算引擎或前端业务流程。
- 任何后续接入必须保留当前 Demo 路径和已有回归结果；新引擎必须通过适配器和独立基准测试后才能进入优化流程。
- 本阶段不自行提交、推送或修改生产分支。

## 数据与结果可信度

- `SST_V1_4_Demo_Data/` 及 `v1_1/` 中的条目是虚构数据。必须保留 `data_status=synthetic`、`demo_only`、`engineering_approved=false` 等来源标识。
- 不得把演示结果、经验常数、未验证模型或自动生成的代理结果标记为工程可信。
- 所有计算结果应能追溯到输入快照、数据版本/哈希、模型版本、引擎版本和随机种子。
- 工程模式必须拒绝未审核的 synthetic 数据；不可为了得到方案而自动放宽用户约束。

## 单位和接口

- 内部计算统一使用 SI：V、A、Hz、H、T、m、m²、m³、kg、W、°C/K；只在 UI 和报告边界做单位转换。
- 优化器只依赖项目定义的服务接口，不直接依赖第三方库内部数据结构。
- MAS/OpenMagnetics 的数据必须经版本化适配器转换；不得凭空创造第三方 API，无法确认的行为先记录为待验证并加测试。

## 质量门槛

- 修改代码前先阅读本文件及相关目录指令；修改后至少执行相关单元测试、语法检查和数据校验。
- 新物理模型必须有独立计算的不变量/基准用例，不能只调用被测函数生成期望值。
- 结果页、报告和导出必须与同一个任务快照一致；输入改变时旧结果应失效。
- 不提交密钥、真实厂家受限数据、运行时缓存或临时浏览器产物。

## 常用检查

```powershell
pytest -q
python scripts/check_demo.py
python scripts/check_v11.py
node --check frontend/app.js
```

除第二阶段明确授权的独立 Provider、MAS 适配器、示例、测试和文档外，不修改 `backend/app/core/engine.py`、`frontend/`、`requirements.txt` 或生产依赖；本阶段不自行提交、推送或修改生产分支。

## 第三阶段授权范围

- 第三阶段可以新增独立的 `backend/app/geometry/` 参数化几何包，扩展第二阶段 OpenMagnetics Provider 的几何保留入口，并新增 `examples/`、`backend/tests/` 与 `docs/ab_upgrade/phase3/` 内容。
- 几何包必须与 `backend/app/core/engine.py`、现有 NSGA-II、`frontend/` 和生产依赖文件解耦；不得替换当前 synthetic Demo 计算路径。
- 几何模型内部统一使用 SI 单位，保留 `synthetic`、`demo_only`、`engineering_approved` 等可信度标识；无法表达的结构必须返回 `UNSUPPORTED_GEOMETRY`，不得静默简化成另一种排布。
- OpenMagnetics 成功调用仍属于研发原型结果，不得标记为工程认证结果或改变现有 Demo 的结果基线。

## 第四阶段 4A 授权范围

- 4A 仅新增与 Phase 3 `LayoutGeometry` 解耦的 PS/PSP `LeakageInductanceService`、独立解析基准、OpenMagnetics 漏感对照和 `docs/ab_upgrade/phase4a/` 文档。
- 漏感服务必须使用真实分段、层、坐标、匝数和有符号 RMS 电流；明确副边短路、参考端口、安匝平衡和 `L=2W/I_rms^2` 的能量约定。
- 不修改旧版 `backend/app/core/engine.py`、NSGA-II、`frontend/`、生产依赖或现有 Demo 计算路径；不把 OpenMagnetics 对照值自动当作真值。
- 不同绕组高度、端部三维漏磁、组合磁芯高保真漏感和未验证经验修正必须返回模型范围诊断，不得静默给值。
