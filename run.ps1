$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "尚未创建运行环境，请先执行 build.ps1。" -ForegroundColor Yellow
    exit 1
}

& $Python (Join-Path $ProjectRoot "app.py")
