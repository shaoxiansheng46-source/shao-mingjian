# 启动方式

推荐在仓库根目录运行：

```powershell
.\scripts\start_demo.ps1
```

默认地址：[http://127.0.0.1:8000/](http://127.0.0.1:8000/)。更换端口：

```powershell
.\scripts\start_demo.ps1 -Port 8010
```

手工启动：

```powershell
$env:PYTHONPATH=(Resolve-Path '.runtime\openmagnetics-venv\Lib\site-packages').Path
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

启动后先看“数据库状态”和“真实物理计算”中的 Provider 状态，再进入“真实结构优化”。真实工作台需要完整原副边绕组端波形；旧版“需求与寻优”仍是 synthetic Demo 路径。

可选浏览器自动化：在本地测试环境安装 `playwright` 后运行 `node scripts/phase7_browser_flow.mjs`。它会执行单候选、真实优化、候选筛选和导出按钮检查，并把截图写入 `output/playwright/`。当前 Codex Work 环境未执行该脚本，因为本地浏览器控制被禁用。
