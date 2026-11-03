# 设计变量与边界

`DesignVariableSpace` 的默认演示范围如下，内部均为 SI 单位：

| 类型 | 变量 | 默认范围/取值 | 物理作用 |
|---|---|---:|---|
| Integer | `Np` | 16–24 匝 | 原边电气总匝数 |
| Integer | `Ns` | 4–8 匝 | 副边电气总匝数 |
| Integer | `P1` | 1–23 匝 | 仅 PSP 的第一原边串联段 |
| Derived | `P2` | `Np-P1` | 仅 PSP 的第二原边串联段 |
| Real | `interwinding_gap_m` | 0.4–1.5 mm，0.05 mm 步进 | 每个相邻绕组界面的完整主绝缘 |
| Real | `core_clearance_m` | 0.3–1.2 mm，0.05 mm 步进 | 绕组到骨架/磁芯的径向距离 |
| Choice | `layout` | `PS`, `PSP` | 实际径向块顺序 |
| Choice | `primary_wire`/`secondary_wire` | 当前真实数据库集合 | 导线记录，不生成虚构参数 |

PS 中 `P1/P2` 被规范化为 `0/Np`，避免未使用的基因制造重复结构；PSP 强制 `P1+P2=Np` 且两段串联同向。连续变量改变后会重新调用 `build_layout`，不只是修改显示字段。

用户如果希望使用不同范围，应通过新的变量空间和配置显式传入；不满足制造几何的个体会被记录为 `geometry_infeasible`，不会自动放宽约束。
