# 启动、操作与复现

## 启动

在已安装项目依赖且 OpenMagnetics 隔离环境可见时：

```powershell
$env:PYTHONPATH=(Resolve-Path '.runtime\\openmagnetics-venv\\Lib\\site-packages').Path
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/`，选择“真实结构优化”。如果 Provider 不可用，页面会禁用开始按钮并说明原因；不会改用 synthetic。

## 复现信息

任务文件保存在 `.runtime/phase6b/phase6b-{task_id}.json`。结果中包含完整请求、固定 case 数据快照、Phase 5A/6A 模型版本、Provider 版本、pymoo 兼容版本、随机种子、评估尝试和 Pareto 记录。相同输入、数据库版本、模型版本和 seed 可以重放；OpenMagnetics 依赖本身仍需固定安装环境。

## 取消

网页“取消”会设置线程事件。优化器在代际回调或评估边界检查该事件，状态会变为 `cancelling`，完成后报告 `cancelled`。取消不产生虚假 Pareto 结果。
