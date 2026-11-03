# PS/PSP 输入一致性比较

## 结论

专项校核前，PSP 的 MAS `functionalDescription` 是 `P1=10 匝、S=5 匝、P2=10 匝`，第三方励磁电感接口会把第一个电气绕组 P1 当作励磁绕组。因此结果准确出现了 PS 的四分之一电感。PSP 的铁损输入仍按 PS 的 `Primary` 全端电压组织，且几何端仍是半匝数 P1，造成磁通密度和铁损被放大。

修复后：

- 实体几何仍明确为 `P1 / S / P2`，保留分段位置、层和逐匝数据；
- MAS 电气视图导出为 `Primary=20 匝、Secondary=5 匝`；
- `sstElectricalWindingMap` 为 `P1→Primary、S→Secondary、P2→Primary`；
- `sstElectricalConnections` 保留 P1、P2 串联同向关系；
- PS、PSP 使用完全相同的 Primary/Secondary 端口电压、电流、频率、温度、气隙和损耗输入；
- P1/S/P2 形式的错误工况现在返回 `WINDING_EXCITATION_BINDING_MISMATCH`，不会继续调用第三方计算。

## 输入快照

实际运行命令：

```powershell
.runtime\openmagnetics-venv\Scripts\python.exe examples\ps_psp_consistency.py --output ps_psp_input_diff.json
```

输出文件位于仓库根目录的 [ps_psp_input_diff.json](../../../../ps_psp_input_diff.json)，包含 PS 和 PSP 的完整 `magnetic`、`inputs`、`operating_point`、温度、模型和几何快照，以及递归差异路径。

本次运行结果：

- 电气/磁芯/工况共享输入差异数：`0`；
- 原始完整快照差异数：`237`；
- 这些差异全部来自预期的实体 P-S 与 P-S-P 排布、分段名称、坐标、层/匝归属和连接元数据，不是端口激励差异；
- `voltage_time_integral_v_s` 和绝对电压时间积分按每个端口分别记录，PS 与 PSP 相同。

## 代码位置

- MAS 映射：`backend/app/geometry/mas_geometry.py`；
- 联合计算输入绑定校验：`backend/app/geometry/joint.py`；
- 可复算专项入口：`examples/ps_psp_consistency.py`；
- 联合基准入口：`examples/phase3_geometry_joint.py`。
