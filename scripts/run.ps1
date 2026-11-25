# 在已安装依赖的 Windows 虚拟环境里启动。不需要管理员。
# 这个脚本没有在 Windows 上运行过。请使用 64 位 Python 3.12。
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "还没有 .venv。请先按 README 安装依赖。"
}
$env:PYTHONPATH = "src"
& $python -m screenmatch
