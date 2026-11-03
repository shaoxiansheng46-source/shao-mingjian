# 4A+ 最终验证报告

## 最终回答

1. **自研模型是否通过独立解析基准？** 通过。PS 闭式、PS/PSP 分段能量 oracle、区间能量重构均通过；这证明了实现与已声明的 1-D 解析模型一致，不等同于工程精度认证。
2. **native_basic 与 native_sectional 是否吻合？** 在单层、等高 PS 退化条件下吻合，差异小于 `1e-12` 相对容差。PSP 不属于 `native_basic` 适用范围。
3. **OpenMagnetics 几何是否一致？** 电气匝数和 PSP 串联映射已一致；显式 sections/layers/turns 数据实际传入 provider，并且去除显式几何的 PSP 控制实验返回不同漏感，说明几何数据会被第三方路径感知。不能说两种模型的场假设完全一致。
4. **为什么约 22 倍？** 已确认是组合差异：自研是等高径向 1-D 当前片和 RMS 周期平均能量；MKF 使用自身场模型、几何离散和 Energy 归一化路径，且存在峰值/谐波电流约定差异。没有证据支持一个固定 22 倍修正因子。
5. **哪些已定位，哪些未解释？** 单位、核心参数、总 Primary 匝数、PSP 电气映射、几何敏感性和自研能量积分已定位并通过；绝对差异中端部/三维场与 MKF 归一化各自占比尚未由 FEM/实测分离。
6. **哪些模型可继续用？** 自研可用于明确范围内的快速相对比较；MKF 可用于真实数据库和第三方 Energy 对照；二者均不能单独标记为工程认证结果。
7. **是否可以开始利兹线交流损耗？** 可以在独立模块和独立基准中开始研发，但暂不把其结果与当前漏感绝对值混成工程可信结论。工程集成前优先完成 PS/PSP 的 COMSOL 或实测短路验证。
8. **COMSOL 优先算例？** 先算同一 ETD/3C95/20:5/0.1 mm 气隙的 PS、PSP 10/10、PSP 8/12，再做不同绕组高度越界案例。

## 实际执行结果

### 独立脚本

`examples/phase4a_plus_verification.py` 返回 `status=passed`，12 项检查全部通过，包括：

- native_basic 独立闭式；
- PS/PSP sectional 独立能量；
- 区间能量重构；
- 副边参考换算；
- 电流整体缩放不改变漏感；
- 非负能量；
- MKF PS/PSP 实际调用；
- 间距和分段对第三方结果的敏感性。

输出：`.runtime/phase4a-plus/verification.json` 和 `.runtime/phase4a-plus/ps_psp_mmf_energy.svg`。

### 既有专项脚本

`examples/ps_psp_consistency.py` 实际返回 `status=passed`：

- OpenMagnetics 励磁电感 PS/PSP：`970.319577 μH`，一致；
- 独立磁阻计算：`964.270112 μH`，与 MKF 相对差异 `0.62345%`；
- PS/PSP 峰值磁密：`0.044990746 T`，一致；
- PS/PSP 磁芯损耗：`0.212934045 W`，一致；
- PSP Primary 电气匝数：20 匝，不是 10 匝。

### 漏感结果

| 结构 | 自研 | MKF Energy（显式几何） |
|---|---:|---:|
| PS | 0.818968 μH | 19.053366 μH |
| PSP 10/10 | 0.361705 μH | 7.824007 μH |

### 回归

本次实际执行结果：`pytest -q` 为 **34 passed**；`examples/phase4a_plus_verification.py` 为 **passed / 12 checks**；`examples/ps_psp_consistency.py` 为 **passed**；Phase 2 OpenMagnetics benchmark、Phase 3 geometry/joint benchmark、Phase 4A leakage benchmark、Demo `check_demo.py`、V1.1 `check_v11.py` 和 `node --check frontend/app.js` 均为 **passed**。测试过程有 `requests` 依赖版本提示，但没有测试失败。COMSOL 本次未执行，已明确标记为待执行。

## 改动边界

本专项未修改旧版 `backend/app/core/engine.py`、NSGA-II、前端、生产依赖或 Demo 业务流程；未提交、未推送远程仓库。新增/修改文件均属于 Phase 4A 漏感服务、独立验证脚本、测试和本目录文档。
