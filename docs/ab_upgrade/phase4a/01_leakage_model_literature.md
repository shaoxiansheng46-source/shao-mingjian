# 4A 漏感模型文献与第三方研究

## 可查证资料

1. [General Analytical Model and Optimization for Leakage Inductances of Medium-Frequency Transformers, DOI 10.1109/JESTPE.2021.3062019](https://ieeexplore.ieee.org/document/9363203/)。摘要明确提到叠加原理、Rogowski 系数、不同绕组高度和与 3-D FEM/实验的误差评估。
2. [Medium Frequency Transformer Leakage Inductance Modeling and Experimental Verification, DOI 10.1109/ECCE.2017.8095813](https://ieeexplore.ieee.org/document/8095813/)。摘要明确说明模型从 MFT 几何结构建立，并与 FEM 和样机测量比较。
3. [Accurate Calculation of Leakage Inductance for Balanced and Fractional-Interleaved Winding, DOI 10.1109/SPEC.2017.8333556](https://ieeexplore.ieee.org/document/8333556/)。用于识别平衡/分数交错绕组问题域。
4. [OpenMagnetics MKF LeakageInductance.cpp](https://github.com/OpenMagnetics/MKF/blob/main/src/physical_models/LeakageInductance.cpp#L2519-L3065)。公开源码显示 MKF 对非环形结构使用窗口磁场能量积分，并用源绕组/目标绕组和运行频率计算漏感；其磁场文档说明 Binns-Lawrenson、Dowell、Wang、Albach 是不同精度/适用条件的场模型。
5. [MKF Magnetic Field 文档](https://openmagnetics.github.io/MKF/models/magnetic-field/)。文档将漏感列为磁场分布的直接应用，并说明 Binns-Lawrenson 是基于窗口傅里叶展开的模型，Dowell 是快速一维均匀电流片近似。

## 本阶段的证据边界

当前可访问的是论文摘要、公开仓库源码和 MKF 文档，未取得上述论文的完整公式、符号约定和全部实验数据。因此本阶段没有声称实现 JESTPE/ECCE/SPEC 任一论文的完整算法，也没有把论文的误差结论复制成软件验收指标。

实现的是一个单独、可解释的径向一维 MMF/储能模型，并保留 Model A/Model B 的明确范围。MKF 只作为独立对照引擎，不能自动成为本模型的真值。
