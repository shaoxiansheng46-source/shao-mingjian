# 第三阶段：联合计算结果

## 实际运行环境

- 入口：`examples/phase3_geometry_joint.py`；
- 解释器：`.runtime/openmagnetics-venv/Scripts/python.exe`；
- PyOpenMagnetics：1.7.35；
- MKF commit：`39b59172268f55fbcd72037b948622f21382b5c1`；
- MAS commit：`0a7ba58f542049fd073041b3b5e4bac431ed6292`；
- 真实对象：材料 `3C95`、磁芯 `ETD 54/28/19`、骨架 `Bobbin ETD 54`、导线 `Round 0.5 - Grade 1`。

对象全部运行时从数据库查询，不读取固定结果。真实骨架窗口为约 8.7 mm × 36.3 mm；气隙输入为 0.1 mm；工作点为 100 kHz、明确的原副边电压/电流波形。

## 实际结果

| 模板 | 励磁电感 | 磁芯损耗 | 完整绕组损耗 | 欧姆绕组损耗 |
|---|---:|---:|---:|---:|
| PS | 0.0009703195771705127 H | 0.21293404491359452 W | 0.044091696142713376 W | 0.0437039746356185 W |
| PSP | 0.0009703195771705127 H | 0.21293404491359452 W | 0.04528223031627745 W | 0.04490703056538055 W |

PSP 的实体结构为 P1/S/P2，但电气 MAS 视图是一个 `Primary=20 匝` 与一个 `Secondary=5 匝`；P1 和 P2 通过应用层元数据表示串联同向关系。PS 与 PSP 使用同一套完整端口波形，不能把 P1/P2 当成独立端口。

此前版本曾将 P1、S、P2 作为三个电气绕组送入第三方接口，得到 242.579894 μH 和 1.544904454 W。该结果已在第三阶段专项校核中定位为错误映射，不再作为基准。

每个模板的 `core_data`、`calculate_inductance_from_number_turns_and_gapping`、`calculate_core_losses`、`calculate_winding_losses`、`calculate_ohmic_losses` 和 `wind` 均返回 `status=ok`。PSP 的电感与磁芯损耗变化是第三方计算对三块显式几何/激励输入的实际返回，不是写入的演示数值。

## 结果分层

- `native`：仅放参数化几何的体积、质量、块电阻和平均匝长；没有把自研估算冒充第三方损耗。
- `openmagnetics`：Provider 实际返回的磁芯数据、电感和损耗。
- `comparison`：为后续与自研模型对比预留；本阶段没有伪造对比值。

所有联合结果仍为研发原型，`engineering_approved=false`。气隙边缘磁通附加损耗、复杂磁芯组合高保真计算、温度热点模型和工程认证均未在本阶段声明实现。
