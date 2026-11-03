# 第三阶段：MAS 几何映射

实现文件：`backend/app/geometry/mas_geometry.py`。

## 映射内容

`MasGeometryAdapter.to_magnetic()` 生成：

- `magnetic.core.functionalDescription`：shape、material、gapping、numberStacks；
- `magnetic.coil.functionalDescription`：每个 P/S/P1/P2 块的名称、匝数、并联数、导线和绝缘侧；
- `groupsDescription`：窗口组和块顺序；
- `sectionsDescription`：每个导电块和每处主绝缘；
- `layersDescription`：每个导电层和每个绝缘层；
- `turnsDescription`：每匝的坐标、尺寸、层、section、绕组和长度。

字段形状按当前隔离环境 PyOpenMagnetics 1.7.35 的 `wind()` 实际返回值适配，包括 `functionalDescription` 中的连接/绕线窗口字段、section 的 `fillingFactor/margin/windingStyle`，以及 insulation layer 的 `turnsAlignment`。

## 校验

`validate_mas_geometry()` 不返回第三方原始对象，只校验应用侧不变量：

- block 数量、名字和顺序；
- 每块匝数、导线 ID；
- sections/layers/turns 数量；
- 每匝坐标和尺寸为正；
- P-S/PSP 结构没有在映射时丢失。

当前 PyOpenMagnetics 版本没有向 Provider 暴露独立官方 JSON Schema 校验器，因此文档明确使用“依据实际 `wind()` 输出字段的结构校验”，不是官方完整 schema 声明。

## Provider 边界

`backend/app/providers/openmagnetics/provider.py` 的 `_resolve_coil()` 保留了 Phase 2 默认行为：没有显式几何时仍调用第三方 `wind()`。当 coil 同时提供四类几何数组时，只解析数据库导线/骨架并保留 sections/layers/turns，再交给 PyOpenMagnetics。这样优化器和生产 Demo 没有被接入新路径。

若结构字段不完整或模板未实现，适配器返回 `UNSUPPORTED_GEOMETRY`/结构诊断，不自动改成 PS。
