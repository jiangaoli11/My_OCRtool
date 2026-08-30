$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot

if (-not (Test-Path $Python)) {
    Write-Host "[1/4] 创建隔离环境..." -ForegroundColor Cyan
    python -m venv .venv
}

Write-Host "[2/4] 安装/更新构建依赖..." -ForegroundColor Cyan
& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    throw "依赖安装失败（退出码 $LASTEXITCODE）"
}

Write-Host "[3/4] 生成应用图标..." -ForegroundColor Cyan
& $Python tools\make_icon.py
if ($LASTEXITCODE -ne 0) {
    throw "图标生成失败（退出码 $LASTEXITCODE）"
}

Write-Host "[4/4] 打包单文件 EXE..." -ForegroundColor Cyan
& $Python -m PyInstaller --noconfirm --clean ScreenshotOCR.spec
if ($LASTEXITCODE -ne 0) {
    throw "EXE 打包失败（退出码 $LASTEXITCODE）。如果 ScreenshotOCR 正在运行，请先退出程序后重试。"
}

$ExePath = Join-Path $ProjectRoot "dist\ScreenshotOCR.exe"
if (-not (Test-Path $ExePath)) {
    throw "打包完成但未找到 $ExePath"
}

$SizeMb = [Math]::Round((Get-Item $ExePath).Length / 1MB, 1)
Write-Host ""
Write-Host "构建成功：$ExePath ($SizeMb MB)" -ForegroundColor Green
