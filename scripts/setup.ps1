<#
.SYNOPSIS
    一键配置虚拟环境（Windows PowerShell）：创建 .venv、安装本项目 + 引擎子模块依赖、精简 Qt 体积。

.DESCRIPTION
    - 自动 `git submodule update --init --recursive`（引擎 third_party/video_ocr_engine）
    - 基于仓库根目录创建 `.venv`（要求 Python 3.11+）
    - 安装本项目 editable（默认含 dev 依赖）+ 引擎子模块（numpy/onnxruntime/psutil）
    - 默认尝试移除 `PySide6-Addons`（qfluentwidgets 经 PySide6 元包装入的全量 Qt，
      可省 ~400MB；移除后自动 `import PySide6.QtWidgets` 自检，失败则自动装回，
      保证 GUI 可用），用 -KeepAddons 保留

    一键运行（右键「使用 PowerShell 运行」，或执行）：
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

.EXAMPLE
    .\scripts\setup.ps1              # 标准开发环境
    .\scripts\setup.ps1 -NoDev       # 只装运行时依赖（跳过 dev）
    .\scripts\setup.ps1 -KeepAddons  # 不移除 PySide6-Addons
#>
[CmdletBinding()]
param(
    [switch]$NoDev,       # 跳过 dev 依赖（pytest 等）
    [switch]$KeepAddons   # 不移除 PySide6-Addons
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Write-Step([string]$msg) {
    Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] $msg" -ForegroundColor Cyan
}

# ── 0. 工具与版本检查 ──
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 git。请先安装 Git for Windows 并加入 PATH。"
    exit 1
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 python。请安装 Python 3.11+ 并加入 PATH。"
    exit 1
}
& python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "需要 Python 3.11+，当前: $(& python --version)"
    exit 1
}

# ── 1. 引擎子模块 ──
$engineMarker = Join-Path $root "third_party\video_ocr_engine\video_ocr_engine\__init__.py"
if (-not (Test-Path $engineMarker)) {
    Write-Step "拉取引擎子模块（git submodule update --init --recursive）..."
    git submodule update --init --recursive
    if ($LASTEXITCODE -ne 0) { Write-Error "引擎子模块拉取失败"; exit 1 }
} else {
    Write-Step "引擎子模块已就绪。"
}

# ── 2. 虚拟环境 ──
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Step "创建虚拟环境 .venv ..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) { Write-Error ".venv 创建失败"; exit 1 }
} else {
    Write-Step ".venv 已存在，复用。"
}

# ── 3. 本项目 editable ──
Write-Step "升级 pip ..."
& $venvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Write-Error "pip 升级失败"; exit 1 }

$spec = if ($NoDev) { "." } else { ".[dev]" }
Write-Step "安装本项目 ${spec} 依赖 ..."
& $venvPy -m pip install -e $spec
if ($LASTEXITCODE -ne 0) { Write-Error "本项目安装失败"; exit 1 }

# ── 4. 引擎子模块（含 onnxruntime/psutil）──
Write-Step "安装引擎子模块（editable，numpy/onnxruntime/psutil）..."
& $venvPy -m pip install -e "third_party\video_ocr_engine"
if ($LASTEXITCODE -ne 0) { Write-Error "引擎子模块安装失败"; exit 1 }

# ── 5. 精简 Qt（尝试移除 Addons，自检失败自动装回，保证 GUI 可用）──
if (-not $KeepAddons) {
    Write-Step "尝试移除 PySide6-Addons（qfluentwidgets 装入的全量 Qt，可省 ~400MB）..."
    & $venvPy -m pip uninstall -y PySide6-Addons *> $null

    # Qt 导入自检：预期失败会写 stderr + 非零退出，这里临时放宽 ErrorAction，
    # 避免 `2> $null` 在 EAP=Stop 下把"预期失败"升级成终止错误。
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $venvPy -c "import PySide6.QtWidgets" 2> $null
    $qtOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEap

    if ($qtOk) {
        Write-Host "    ✓ 已移除 PySide6-Addons，GUI 依赖自检通过。"
    } else {
        Write-Host "    ⚠ 移除后 Qt 导入自检失败（部分环境 Qt 需要 Addons），重新装回保留。" -ForegroundColor Yellow
        & $venvPy -m pip install --no-input PySide6-Addons *> $null
    }
}

Write-Host ""
Write-Host "✔ 配置完成" -ForegroundColor Green
Write-Host "  启动 GUI   :  .\scripts\run_gui.ps1"
Write-Host "  构建 frozen:  .\scripts\build_exe.ps1"
Write-Host "  跑测试     :  & .\.venv\Scripts\python.exe -m pytest tests/ -v"
Write-Host "  （可选）安装 decord fork（chr431/decord >=v0.7.12）以获得 GPU/快速解码，见引擎 README。"
Write-Host ""
