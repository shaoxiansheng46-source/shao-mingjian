# 4A 解析基准与结果

运行命令：

```powershell
.runtime\openmagnetics-venv\Scripts\python.exe examples\phase4a_leakage_benchmark.py --output .runtime\phase4a-leakage-benchmark.json
```

## 手工闭式基准

单层 PS 使用独立计算的

`μ0 Np² l_mlt/h · (tp/3 + gps + ts/3)`

与 `native_basic` 返回值逐项比较，误差小于 `1e-12` 相对容差。该基准没有调用被测服务生成预期值。

## 实际 Phase 3 几何算例

真实数据库对象：`3C95`、`ETD 54/28/19`、`Bobbin ETD 54`、`Round 0.5 - Grade 1`；工作点 100 kHz；原边 RMS 电流 1 A，副边 RMS 电流 -4 A；主绝缘 0.25 mm。

| 结构 | 模型 | 原边参考漏感 | 分区贡献 |
|---|---|---:|---|
| PS | native_basic / sectional | `0.818968 μH` | 原边 `0.263100 μH`；界面 `0.292767 μH`；副边 `0.263100 μH` |
| PSP | native_sectional | `0.361705 μH` | P1 `0.062331 μH`；两界面合计 `0.154048 μH`；S `0.069219 μH`；P2 `0.076106 μH` |

PSP 的值来自 P1/S/P2 实际层和位置积分，未使用“PSP 固定降低系数”。P1/P2 为 10/10 匝；服务也通过测试验证了 8/12 等不等分输入会改变实际计算结果。

## 几何敏感性

- 主绝缘从 0.25 mm 增至 0.5 mm，PS 漏感增大；
- PSP 分段从 10/10 改为 8/12，漏感数值改变；
- 零尺寸、负/零实体间距、不同绕组高度分别返回输入错误或 `OUT_OF_MODEL_SCOPE`。
