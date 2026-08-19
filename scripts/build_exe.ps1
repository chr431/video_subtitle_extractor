<#
.SYNOPSIS
    一键构建 frozen exe（Windows）：用 PyInstaller 冻结 GUI 应用。

.DESCRIPTION
    - 复用 .venv（缺失时提示先跑 scripts\setup.ps1；可用 -SystemPython 改用系统 python）
    - 安装构建依赖（pyinstaller，走本仓库 [build] extra）
    - 运行 scripts\VideoSubtitleExtractor.spec，
      产物为 onedir 目录 dist\VideoSubtitleExtractor\（内含 VideoSubtitleExtractor.exe）
      —— 引擎子模块源码与 OCR 模型（assets\ocr_models）已随包打进

    一键运行（右键「使用 PowerShell 运行」，或执行）：
        powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1

.EXAMPLE
    .\scripts\build_exe.ps1
    .\scripts\build_exe.ps1 -SystemPython
#>
[CmdletBinding()]
param(
    [switch]$SystemPython  # 用系统 python 而不是 .venv
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if ($SystemPython) {
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $py) { Write-Error "未找到系统 python。"; exit 1 }
} elseif (-not (Test-Path $py)) {
    Write-Error "未找到 .venv，请先运行:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1"
    exit 1
}

Write-Host "[build] 安装构建依赖（pyinstaller）..." -ForegroundColor Cyan
& $py -m pip install -e ".[build]"
if ($LASTEXITCODE -ne 0) { Write-Error "构建依赖安装失败"; exit 1 }

# decord 是视频解码后端；构建机缺它会做进一个无法解码视频的 exe，这里先拦下。
Write-Host "[build] 检查 decord 解码依赖 ..."
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $py -c "import decord" 2>&1 | Out-Null
$decordOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prevEap
if (-not $decordOk) {
    Write-Error "未检测到 decord 解码 fork。请先运行:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 （一键会安装 chr431/decord 解码后端）"
    exit 1
}

Write-Host "[build] 运行 PyInstaller（spec: scripts\VideoSubtitleExtractor.spec）..." -ForegroundColor Cyan
& $py -m PyInstaller "scripts\VideoSubtitleExtractor.spec" --noconfirm --clean
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller 构建失败"; exit 1 }

$exe = Join-Path $root "dist\VideoSubtitleExtractor\VideoSubtitleExtractor.exe"
Write-Host ""
Write-Host "✔ 构建完成" -ForegroundColor Green
Write-Host "  可执行文件: $exe"
Write-Host "  整个 dist\VideoSubtitleExtractor\ 目录（onedir）即可分发，需整体拷贝。"
Write-Host ""
