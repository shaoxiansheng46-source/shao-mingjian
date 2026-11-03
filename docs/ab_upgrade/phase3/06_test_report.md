# 第三阶段：测试报告

## 已执行

| 检查 | 结果 |
|---|---|
| `pytest -q` | 24 passed |
| Phase 3 几何/联合单测 | 通过（包含 PS/PSP 总匝数、串联映射、奇数匝、窗口/绝缘反例、错误激励绑定、MAS 一致性） |
| Phase 3 联合入口 | `status=passed`；PS/PSP 几何、MAS 映射和六类真实 Provider 调用均通过 |
| Phase 2 OpenMagnetics benchmark | 已执行并保持通过（真实数据库、损耗、电感、异常和复现检查） |
| `python scripts/check_demo.py` | 已执行，原有候选/可行/Pareto 回归保持通过 |
| `python scripts/check_v11.py` | 已执行，V1.1 气隙/PSP/组合/外置电感回归保持通过 |
| `node --check frontend/app.js` | 已执行，通过；前端业务没有修改 |
| PS/PSP 专项一致性脚本 | `status=passed`；实际 OpenMagnetics 电感、磁密和铁损一致 |

Phase 3 实际联合命令：

```powershell
.runtime\\openmagnetics-venv\\Scripts\\python.exe examples\\phase3_geometry_joint.py --output .runtime\\phase3-geometry-joint.json
```

它在运行时查询材料、磁芯、骨架和导线，并把完整 JSON 结果写入被忽略的 `.runtime` 目录。没有把该运行缓存纳入版本控制。

## 尚未执行

本阶段没有进行浏览器流程验证，因为没有修改前端业务流程或页面；没有进行 COMSOL、三维有限元或生产工程校核；没有把 Phase 3 Provider 接入 NSGA-II。
