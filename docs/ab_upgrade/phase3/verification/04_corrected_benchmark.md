# 修正后基准结果

## 运行环境

- 解释器：`.runtime/openmagnetics-venv/Scripts/python.exe`；
- PyOpenMagnetics：`1.7.35`；
- MKF：`39b59172268f55fbcd72037b948622f21382b5c1`；
- MAS：`0a7ba58f542049fd073041b3b5e4bac431ed6292`；
- 材料：`3C95`；磁芯：`ETD 54/28/19`；骨架：`Bobbin ETD 54`；导线：`Round 0.5 - Grade 1`；
- 工作点：100 kHz，明确端电压/端电流波形，环境温度 25 °C，中心气隙 0.1 mm。

## 实际结果

| 结构 | MAS 电气原边 | MAS 电气副边 | 励磁电感 | 峰值磁密 | 磁芯损耗 | 完整绕组损耗 |
|---|---:|---:|---:|---:|---:|---:|
| PS | 20 匝 | 5 匝 | 970.319577 μH | 0.044990746 T | 0.212934045 W | 0.044091696 W |
| PSP | 20 匝（P1+P2 串联） | 5 匝 | 970.319577 μH | 0.044990746 T | 0.212934045 W | 0.045282230 W |

专项脚本 `examples/phase3_geometry_joint.py` 与 `examples/ps_psp_consistency.py` 均返回 `status=passed`。所有核心数据、电感、铁损、绕组损耗、欧姆损耗和几何调用均为 `status=ok`。

## 解释

PSP 的完整绕组损耗略高是实体排布结果，不代表励磁或铁损输入不一致。PSP 的实体 P1/S/P2 仍可在结果结构和 MAS 的 sections/layers/turns 中追踪，且两处绝缘界面没有被合并。
