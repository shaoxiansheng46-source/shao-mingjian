# 安装与环境

## 基础要求

- Windows PowerShell。
- Python 3.10 或更高版本。
- FastAPI、uvicorn、NumPy、pymoo 0.6.2 等仓库基础依赖。
- 已验证的 PyOpenMagnetics 1.7.35 隔离运行环境。

仓库的 `requirements.txt` 保持生产 Demo 依赖，不包含第三方隔离运行时。真实计算需要把已有 `.runtime/openmagnetics-venv/Lib/site-packages` 暴露给 `PYTHONPATH`，或在本机用等价的隔离环境配置。

## 检查

```powershell
python --version
python -c "import fastapi,uvicorn,pymoo; print('pymoo', pymoo.__version__)"
$env:PYTHONPATH=(Resolve-Path '.runtime\openmagnetics-venv\Lib\site-packages').Path
python -c "from backend.app.providers.openmagnetics import OpenMagneticsProvider; print(OpenMagneticsProvider().status())"
```

缺少第三方运行时只允许进入 synthetic Demo；真实结构优化不会静默切换到 synthetic。
