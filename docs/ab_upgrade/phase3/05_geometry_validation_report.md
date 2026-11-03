# 第三阶段：几何验证报告

验证入口：`backend/tests/test_geometry_phase3.py`。

## 正例

- PS：生成两个绕组块、实际层和匝坐标、一处完整主绝缘；
- PSP：21 匝原边生成 P1=10、P2=11，满足 `P1+P2=Np`，生成两处完整主绝缘；
- MAS：块名/顺序、匝数、section/layer/turn 数量保持一致；
- 设计参数改变：改变总原边匝数后，生成的匝坐标发生变化；
- 独立联合服务：完整波形触发 Provider 边界，缺波形时损耗保持 null。

## 反例

- 小窗口返回 `WINDOW_RADIAL_OVERFLOW`；
- 主绝缘为零返回 `INSULATION_NON_POSITIVE`；
- 显式 P1/P2 和不等于总原边匝数返回 `PRIMARY_SPLIT_MISMATCH`；
- 未知模板返回 `UNSUPPORTED_GEOMETRY`；
- 缺少波形返回 `MISSING_WAVEFORM`，不从直流母线自动构造损耗波形。

## 实际与限制

本报告实际运行了上述正反例。当前二维模型检查的是径向块、轴向匝和层级矩形的碰撞与边界；尚未实现三维端部引出线、复杂骨架台阶、线包圆角和磁芯组合高保真碰撞。对应结构应在后续扩展前保持明确的 unsupported 状态。
