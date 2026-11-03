param(
  [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$demoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $demoRoot

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
  Write-Error '未找到 Python。请先安装 Python 3.10+，本脚本不会自动下载依赖。'
  exit 1
}

$openMagneticsPackages = Join-Path $demoRoot '.runtime\openmagnetics-venv\Lib\site-packages'
if (Test-Path $openMagneticsPackages) {
  $env:PYTHONPATH = $openMagneticsPackages
}

python -c "import fastapi,uvicorn,pymoo; print('FastAPI/uvicorn/pymoo dependencies: OK'); print('pymoo', pymoo.__version__)"
if ($LASTEXITCODE -ne 0) {
  Write-Error '基础 Python 依赖缺失；请按 docs/demo_v1/INSTALL.md 配置，不会自动修改生产环境。'
  exit 1
}

python -c "from backend.app.providers.openmagnetics import OpenMagneticsProvider; p=OpenMagneticsProvider(); s=p.status(); print('OpenMagnetics available:', s['available']); print('version:', s.get('third_party_version')); raise SystemExit(0 if s['available'] else 2)"
if ($LASTEXITCODE -ne 0) {
  Write-Error 'OpenMagnetics Provider 不可用。请确认隔离环境 .runtime/openmagnetics-venv 已按文档配置。'
  exit 1
}

Write-Host "SST Demo V1.0 启动中: http://127.0.0.1:$Port/"
Write-Host '关闭服务请按 Ctrl+C。'
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port $Port
