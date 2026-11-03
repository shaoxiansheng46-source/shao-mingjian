# SST 高频隔离变压器结构优化 Demo V1.0

这是一个研究型工程设计 Demo，采用 OpenMagnetics Provider 与自研参数化结构、漏感、约束和 NSGA-II 编排。它支持：

- 旧版 synthetic 数据演示与参考回归；
- 真实磁芯/材料/利兹线的单候选计算；
- PS、PSP 实际几何生成；
- 显式绕组端电压/电流波形下的磁芯、绕组、励磁电感和研究性漏感计算；
- 真实整数匝数、PS/PSP、间距和制造步进的混合变量 NSGA-II；
- 全部候选、研究性可行候选、Pareto、结构图、比较和 JSON/CSV 导出。

本版本不是工程认证软件。漏感、邻近损耗及热结果仍保留研究性限制，工程状态为 UNKNOWN。

快速开始：阅读 [INSTALL.md](INSTALL.md) 和 [STARTUP.md](STARTUP.md)。
