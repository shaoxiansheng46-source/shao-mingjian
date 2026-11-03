# Phase 4B：直流电阻和温度模型

## 计算路径

代码位置：`backend/app/winding_loss/service.py`。

对每个 Phase 3 绕组段，导线长度来自 `turns_geometry[].length_m` 的实际逐匝长度之和，并加上每个并联支路的 lead allowance。并联时先得到单支路长度，再按并联数折算电阻；PSP 的 P1、P2 分别计算后在电气绕组 `Primary` 中串联相加。

在已有电阻率和铜面积时使用：

\[
R_{dc}(T)=\rho_{20}[1+\alpha(T-20^\circ C)]\frac{l_{branch}}{A_{cu}N_{parallel}}
\]

其中 `Acu` 是裸铜总截面积，不是利兹线成品占用面积。若真实材料电阻率缺失，native 模型调用 OpenMagnetics 的 `calculate_dc_resistance_per_meter()`；第三方接口不可用时返回诊断，不将电阻静默设为零。

直流损耗基线使用完整波形的 RMS 电流：

\[
P_{dc}=I_{rms}^2R_{dc}
\]

`native_dc` 只声明这是 Rdc 基线，`skin_loss_w`、`proximity_loss_w` 保持 `null`，并列出未建模机制。它不会把未计算的交流机制当作零后再宣称“完整铜损”。

## 实际 Provider 调用

Phase 4B 独立基准实际调用 `calculate_dc_resistance_per_meter()`。选定利兹线在 25°C 的实际返回值为约 `0.0544915964214477 Ω/m`。该数值来自运行时数据库和第三方函数，不写入生产模型常数。
