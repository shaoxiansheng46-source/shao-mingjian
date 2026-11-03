# Phase 4B：波形和谐波损耗

## 输入检查

`CurrentWaveform` 要求名称、正频率、至少 4 个有限采样点、时间和电流长度一致。计算假设输入代表一个周期；非等距输入会进行显式周期线性重采样并添加 `WAVEFORM_RESAMPLED` 警告，重复端点会合并并留下诊断。

不接受时间跨度明显不是一个周期的输入，也不从直流母线电压推造高频绕组电流或电压波形。

## 谐波分析

`analyze_current_waveform()` 使用独立单边 DFT：

\[
X_k=\frac{2}{N}\sum_{n=0}^{N-1}i_n e^{-j2\pi kn/N},\qquad I_{k,rms}=|X_k|/\sqrt2
\]

DC 分量为样本平均值，AC RMS 用总 RMS 与 DC 分量分离得到。每个谱项保留阶次、频率、幅值、RMS 和相位；`truncation_rms_a` 量化谐波截断误差。

在分项定义不重叠且每个 `Rac(fn)` 可追溯时，可采用：

\[
P_{cu}=I_{dc}^2R_{dc}+\sum_k I_{k,rms}^2R_{ac}(f_k)
\]

当前 `native_dc` 不自行生成 `Rac`，因此仅输出 Rdc 基线。OpenMagnetics full 由第三方根据带谐波/processed 字段的 operating point 计算 ohmic、skin 和 proximity 分项，适配器只在分项存在时汇总。

## 独立检查

测试输入 `i(t)=2+\sqrt2\sin(2\pi ft)` 的独立预期为 DC=2 A、总 RMS=√5 A、AC RMS=1 A、基波 RMS=1 A；Phase 4B 测试直接验证这些解析值，而不是调用生产函数生成预期值。
