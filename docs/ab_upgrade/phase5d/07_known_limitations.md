# Phase 5D 已知限制

1. 当前真实工作台是单候选评估，不是混合离散/连续变量 NSGA-II；旧优化器未修改。
2. OpenMagnetics 运行环境不属于生产依赖。系统 Python 未安装 PyOpenMagnetics 时，真实数据库模式会明确失败；不会偷偷使用演示数据。
3. 真实利兹线数据库部分记录没有名义成品外径、绞距或导体材料字段；适配器保留缺失状态，缺关键几何时拒绝计算。
4. 漏感为 Phase 4A 研究性解析/半解析结果，未经过 COMSOL 或实物校准；前端工程状态保持 UNKNOWN。
5. MKF complete 结果与 native Rdc 的定义、长度和聚合范围应继续做 Phase 4B+ 校核；页面不把 standalone proximity 叠加到 complete。
6. 热网络、热点温度、温升和工程合格判定尚未接入；结果为 null/not_implemented。
7. 当前页面没有三维 CAD，也没有 DAB 全工况波形求解器；所有第三方损耗计算都要求用户提供显式端电压/电流时序。
8. Playwright CLI 在本 Windows 环境的 npx 调用未完成可用输出，因此本交付报告区分了 API/语法验证和未完成的浏览器自动化验证。
