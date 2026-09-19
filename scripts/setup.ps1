<#
.SYNOPSIS
    一键配置虚拟环境（Windows PowerShell，参考 RaceVideoToLog\setup_venv.bat 重写）：
    创建 .venv、写引擎 .pth、安装本项目/引擎/decord fork、精简 Qt。

.DESCRIPTION
    - 引擎子模块 third_party/video_ocr_engine：写 site-packages\video_ocr_engine.pth，
      让任意 venv 进程（CLI/GUI/测试）都能 import 引擎模块（同 RaceVideoToLog）。
    - 安装本项目 editable（默认含 dev）+ 引擎依赖（numpy/openvino/psutil）。
    - decord 解码 fork（chr431/decord，视频解码必需；PyPI 官方版不支持本项目
      用到的 next_roi / ROI-first / 原生 hybrid ctx）：作为依赖由
      `pip install -e .` 按 pyproject.toml 的 wheel URL 安装，本脚本只做
      存在性与 hybrid ctx 能力校验（版本单一事实源在 pyproject.toml）。
    - TRT（可选，默认装 thin binding）：只装 cuda-python + tensorrt 纯 Python 绑定层
      （[trt] extra，~1MB），不装 tensorrt 元包；实际推理 DLL 由引擎从 PATH 扫描
      本地 CUDA/TensorRT 加载；无则 OCR 自动回退 ONNX（CPU）。-SkipTrt 可跳过。
    - 精简 Qt（PySide6-Addons 是可废弃的 ~400MB；且 Addons 的 RECORD 误含
      Essentials 的 Qt6Core.dll，同 RaceVideoToLog）：卸载 Addons 后
      `--force-reinstall --no-deps PySide6-Essentials` 恢复，再 import 自检。
    - 只装本项目/引擎真正需要的依赖（openvino/numpy/psutil/PySide6/qfluentwidgets/
      decord + 可选 TRT thin binding）。

    一键运行（右键「使用 PowerShell 运行」，或执行）：
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

.EXAMPLE
    .\scripts\setup.ps1              # 标准开发环境（含 dev + decord + TRT thin binding）
    .\scripts\setup.ps1 -NoDev       # 只装运行时依赖（跳过 dev）
    .\scripts\setup.ps1 -SkipDecord  # 不安装 decord fork（视频解码不可用）
    .\scripts\setup.ps1 -SkipTrt     # 不安装 TRT thin binding（OCR 仅 CPU/ONNX）
    .\scripts\setup.ps1 -KeepAddons  # 保留 PySide6-Addons（不精简 Qt）
#>
[CmdletBinding()]
param(
    [switch]$NoDev,       # 跳过 dev 依赖（pytest 等）
    [switch]$SkipDecord,  # 不安装 decord 解码 fork
    [switch]$SkipTrt,     # 不安装 TRT thin binding（cuda-python + tensorrt bindings）
    [switch]$KeepAddons   # 保留 PySide6-Addons（不精简 Qt）
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

# ── 1. 引擎（video_ocr_engine）：pip 依赖，不再用 git submodule ──
# 旧做法：submodule + 写 site-packages 的 .pth（绝对路径硬编码，换机即废）。
# 新做法：版本由 pyproject.toml 的 git tag 锁定（pip install -e . 时自动装）。
# 本地存在引擎源码树（与本仓库同级的 video_ocr_engine/）时改 editable 安装，
# 改引擎代码立刻生效；必须在装完本项目依赖**之后**执行，否则 pip 会用
# git 版本覆盖掉源码直连。

# ── 2. 虚拟环境 ──
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$venvRoot = Split-Path (Split-Path $venvPy)   # .venv（Scripts 的上一级）
if (-not (Test-Path $venvPy)) {
    Write-Step "创建虚拟环境 .venv ..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPy)) { Write-Error ".venv 创建失败"; exit 1 }
} else {
    Write-Step ".venv 已存在，将刷新依赖（如需完全重建: 删除 .venv 后重跑）。"
}

Write-Step "升级 pip ..."
& $venvPy -m pip install --upgrade pip -q
if ($LASTEXITCODE -ne 0) { Write-Error "pip 升级失败"; exit 1 }

# ── 3. 本项目 editable（默认含 dev；引擎作为依赖按 pyproject 的 tag 安装）──
$spec = if ($NoDev) { "." } else { ".[dev]" }
Write-Step "安装本项目 ${spec} 依赖（引擎经 git tag 锁定一并安装）..."
& $venvPy -m pip install -e $spec
if ($LASTEXITCODE -ne 0) { Write-Error "本项目安装失败"; exit 1 }

# ── 4. 本地引擎源码树（editable 覆盖，改引擎立刻生效）──
$engineSrc = Join-Path (Split-Path $root) "video_ocr_engine"
if (Test-Path (Join-Path $engineSrc "pyproject.toml")) {
    Write-Step "发现本地引擎源码树，改用 editable 安装（覆盖 git 版本）..."
    & $venvPy -m pip install -e $engineSrc --no-deps
    if ($LASTEXITCODE -ne 0) { Write-Error "引擎 editable 安装失败"; exit 1 }
} else {
    Write-Step "无本地引擎源码树，使用 pyproject 锁定的 git tag 版本。"
}

# ── 5. 清理旧 submodule 时代的残留 .pth（如有）──
$legacyPth = Join-Path $venvRoot "Lib\site-packages\video_ocr_engine.pth"
if (Test-Path $legacyPth) {
    Remove-Item $legacyPth -Force
    Write-Step "已删除旧 submodule 时代的 $legacyPth（避免与 pip 包冲突）"
}

# ── 6. decord 解码 fork ──
# 2026-09-19：改为**轮子安装**（版本与 URL 由 pyproject.toml 的 PEP 508 依赖
# 单一锁定，`pip install -e .` 已装好）。旧做法是从 release zip 解压再手工
# 拷 DLL，版本号硬编码在本脚本里——结果是 0.7.12 一直没跟上引擎的原生
# hybrid（需 ≥0.7.15），`--decode-backend hybrid` 静默回退纯 GPU。
# 本步只做**验证**与（必要时）重装，不再自行拼装包内容。
if (-not $SkipDecord) {
    Write-Step "校验 decord 解码 fork（版本由 pyproject.toml 锁定）..."
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $decordInfo = & $venvPy -c "import decord; print(decord.__version__)" 2>&1 | Out-String
    $decordOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEap
    if (-not $decordOk) {
        Write-Host "    decord 未就绪，按 pyproject 重装 ..."
        & $venvPy -m pip install --force-reinstall --no-deps "decord"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "decord 安装失败（请检查网络/杀毒软件；DLL 被拦会导致导入失败）。"
            exit 1
        }
        $ErrorActionPreference = "Continue"
        $decordInfo = & $venvPy -c "import decord; print(decord.__version__)" 2>&1 | Out-String
        $decordOk = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $prevEap
    }
    if (-not $decordOk) {
        Write-Error "decord fork 导入自检失败（请检查杀毒软件是否拦截了 .venv\Lib\site-packages\decord 下的 DLL）。"
        exit 1
    }
    # 能力自检：原生 hybrid ctx 存在性（引擎 `--decode-backend hybrid` 依赖它；
    # 缺失时引擎静默回退纯 GPU，用户无从察觉 → 这里显式报警）。
    $hybridOk = & $venvPy -c "import decord, sys; sys.exit(0 if hasattr(decord, 'hybrid') else 1)" 2>$null
    $hybridHas = ($LASTEXITCODE -eq 0)
    if ($hybridHas) {
        Write-Host "    ✓ decord $($decordInfo.Trim()) 就绪（含原生 hybrid ctx）。"
    } else {
        Write-Host "    ⚠ decord $($decordInfo.Trim()) 已装，但缺少原生 hybrid ctx" -ForegroundColor Yellow
        Write-Host "      （需 ≥0.7.15）：`--decode-backend hybrid` 会静默回退纯 GPU。" -ForegroundColor Yellow
        Write-Host "      请确认 pyproject.toml 的 decord URL 与已装版本一致后重跑本脚本。" -ForegroundColor Yellow
    }
}


# ── 7. TRT thin binding（可选，默认装；无本机 TensorRT 不影响，OCR 自动回退 ONNX）──
if (-not $SkipTrt) {
    Write-Step "安装 TRT thin binding（cuda-python + tensorrt bindings，[trt] extra）..."
    & $venvPy -m pip install -e ".[trt]"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    ⚠ TRT thin binding 安装失败某依赖（本机若无 TensorRT/CUDA13 属正常）——OCR 将继续用 ONNX(CPU)。"
    } else {
        Write-Host "    ✓ TRT thin binding 就绪；实际推理 DLL 由引擎从 PATH 扫描本地 CUDA/TensorRT，暂无则自动回退 ONNX。"
    }
}

# ── 8. 精简 Qt（参考 RaceVideoToLog：卸 Addons + 强制重装 Essentials 修复 RECORD）──
if (-not $KeepAddons) {
    Write-Step "精简 Qt：移除 PySide6-Addons（~400MB）并强制重装 Essentials ..."
    & $venvPy -m pip uninstall -y PySide6-Addons *> $null
    # PySide6 打包缺陷：Addons 的 RECORD 误含 Essentials 的 Qt6Core.dll，
    # 卸载后强制重装 Essentials 恢复，否则 QtCore 加载失败。
    & $venvPy -m pip install --force-reinstall --no-deps PySide6-Essentials -q
    if ($LASTEXITCODE -ne 0) { Write-Error "PySide6-Essentials 重装失败"; exit 1 }

    # Qt 自检（失败即报错，不再回退；符合参考实现的确定性结论）
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $venvPy -c "import PySide6.QtWidgets" 2>&1 | Out-Null
    $qtOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEap
    if (-not $qtOk) {
        Write-Error "Qt 导入自检失败。建议删除 .venv 后重跑本脚本。"
        exit 1
    }
    Write-Host "    ✓ PySide6-Addons 已移除，Qt(Essentials) 自检通过。"
}

Write-Host ""
Write-Host "✔ 配置完成" -ForegroundColor Green
Write-Host "  启动 GUI   :  .\scripts\run_gui.ps1"
Write-Host "  构建 frozen:  .\scripts\build_exe.ps1"
Write-Host "  跑测试     :  & .\.venv\Scripts\python.exe -m pytest tests/ -v"
if (-not $SkipDecord) {
    Write-Host "  解码后端:   decord $($decordInfo.Trim())（site-packages\decord）"
}
Write-Host ""
