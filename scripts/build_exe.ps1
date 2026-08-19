<#
.SYNOPSIS
    一键构建 frozen exe（Windows PowerShell，参考 RaceVideoToLog\build_exe.bat 重写）：
    确保 .venv 与关键依赖 → 装 PyInstaller → 按 scripts\VideoSubtitleExtractor.spec 冻结 GUI。

.DESCRIPTION
    - .venv 缺失时自动先跑 scripts\setup.ps1（同参考实现）；可用 -SystemPython 改用系统 python。
    - 关键依赖校验：onnxruntime / numpy / PySide6 / decord / qfluentwidgets。
      不校验 CUDA/TensorRT（本项目 OCR 走 CPU 后端，无需 GPU 加速依赖）。
    - 构建前清理 build\ dist\；产物为 onedir 目录 dist\VideoSubtitleExtractor\
      （引擎子模块源码、OCR 模型、decord 运行时 dll 均已随包；见 spec）。

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

$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$py = $venvPy

# ── [1/4] 确保 .venv ──
if ($SystemPython) {
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $py) { Write-Error "未找到系统 python。"; exit 1 }
} elseif (-not (Test-Path $venvPy)) {
    Write-Host "[1/4] 未找到 .venv，先运行 scripts/setup.ps1 ..." -ForegroundColor Cyan
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "scripts\setup.ps1")
    if ($LASTEXITCODE -ne 0) { Write-Error "venv setup 失败"; exit 1 }
    if (-not (Test-Path $venvPy)) { Write-Error ".venv 仍未就绪"; exit 1 }
    $py = $venvPy
} else {
    Write-Host "[1/4] 使用已有 .venv" -ForegroundColor Cyan
}

# ── [2/4] 关键依赖校验（排除不需要的 cuda/tensorrt）──
Write-Host "[2/4] 校验关键依赖（onnxruntime/numpy/PySide6/decord/qfluentwidgets）..." -ForegroundColor Cyan
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $py -c "import onnxruntime, numpy, PySide6, decord, qfluentwidgets" 2>&1 | Out-Null
$depsOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prevEap
if (-not $depsOk) {
    Write-Host "  部分依赖缺失，重新安装 ..."
    & $py -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { Write-Error "依赖安装失败"; exit 1 }
    $ErrorActionPreference = "Continue"
    & $py -c "import onnxruntime, numpy, PySide6, decord, qfluentwidgets" 2>&1 | Out-Null
    $depsOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEap
    if (-not $depsOk) { Write-Error "依赖仍缺失（请先运行 scripts\setup.ps1）"; exit 1 }
    Write-Host "  ✓ 依赖已补齐。"
} else {
    Write-Host "  ✓ 关键依赖就绪。"
}

# ── PyInstaller ──
$ErrorActionPreference = "Continue"
& $py -c "import PyInstaller" 2>&1 | Out-Null
$piOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prevEap
if (-not $piOk) {
    # 直接装 pyinstaller（同参考 build_exe.bat：不走 -e .[build]，
    # 避免重装项目时把 setup.ps1 已精简掉的 PySide6-Addons 又装回来）
    Write-Host "  安装 PyInstaller ..."
    & $py -m pip install pyinstaller
    if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller 安装失败"; exit 1 }
    Write-Host "  ✓ PyInstaller 就绪。"
}

# ── [3/4] 清理旧产物 ──
Write-Host "[3/4] 清理 build\ dist\ ..." -ForegroundColor Cyan
Remove-Item -Recurse -Force (Join-Path $root "build") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $root "dist") -ErrorAction SilentlyContinue

# ── [4/4] 构建 ──
Write-Host "[4/4] 运行 PyInstaller（spec: scripts\VideoSubtitleExtractor.spec）..." -ForegroundColor Cyan
& $py -m PyInstaller (Join-Path $root "scripts\VideoSubtitleExtractor.spec") --noconfirm --clean
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller 构建失败"; exit 1 }

$exe = Join-Path $root "dist\VideoSubtitleExtractor\VideoSubtitleExtractor.exe"
Write-Host ""
Write-Host "✔ 构建完成" -ForegroundColor Green
Write-Host "  可执行文件: $exe"
Write-Host "  整个 dist\VideoSubtitleExtractor\ 目录（onedir）即可分发，需整体拷贝。"
Write-Host ""
