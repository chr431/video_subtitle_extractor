<#
.SYNOPSIS
    一键配置虚拟环境（Windows PowerShell，参考 RaceVideoToLog\setup_venv.bat 重写）：
    创建 .venv、写引擎 .pth、安装本项目/引擎/decord fork、精简 Qt。

.DESCRIPTION
    - 引擎子模块 third_party/video_ocr_engine：写 site-packages\video_ocr_engine.pth，
      让任意 venv 进程（CLI/GUI/测试）都能 import 引擎模块（同 RaceVideoToLog）。
    - 安装本项目 editable（默认含 dev）+ 引擎子模块（numpy/onnxruntime/psutil）。
    - decord 解码 fork（chr431/decord v0.7.12，视频解码必需；PyPI 版不支持）：
        ① 本地 `_decord_build\`（发布产物，布局同 RaceVideoToLog）优先；
        ② 否则下载 v0.7.12 发布包解压为 `_decord_build\`，再装入 site-packages\decord。
    - TRT（可选，默认装 thin binding）：只装 cuda-python + tensorrt 纯 Python 绑定层
      （[trt] extra，~1MB），不装 tensorrt 元包；实际推理 DLL 由引擎从 PATH 扫描
      本地 CUDA/TensorRT 加载；无则 OCR 自动回退 ONNX（CPU）。-SkipTrt 可跳过。
    - 精简 Qt（PySide6-Addons 是可废弃的 ~400MB；且 Addons 的 RECORD 误含
      Essentials 的 Qt6Core.dll，同 RaceVideoToLog）：卸载 Addons 后
      `--force-reinstall --no-deps PySide6-Essentials` 恢复，再 import 自检。
    - 只装本项目/引擎真正需要的依赖（onnxruntime/numpy/psutil/PySide6/qfluentwidgets/
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

# ── 3. 引擎子模块 .pth（参考 RaceVideoToLog setup_venv.bat）──
# 引擎根是 Python 源码根（顶层 engine_config/segmentation/... + video_ocr_engine 包），
# 写 site-packages 的 .pth 让任何 venv 进程无需 bootstrap 即可 import。
$sitePkgs = Join-Path $venvRoot "Lib\site-packages"
if (-not (Test-Path $sitePkgs)) { New-Item -ItemType Directory -Path $sitePkgs -Force | Out-Null }
$engineAbs = Join-Path $root "third_party\video_ocr_engine"
$pth = Join-Path $sitePkgs "video_ocr_engine.pth"
Set-Content -Path $pth -Value $engineAbs -Encoding Ascii
Write-Step "写入引擎 .pth -> $pth"

# ── 4. 本项目 editable（默认含 dev）──
$spec = if ($NoDev) { "." } else { ".[dev]" }
Write-Step "安装本项目 ${spec} 依赖 ..."
& $venvPy -m pip install -e $spec
if ($LASTEXITCODE -ne 0) { Write-Error "本项目安装失败"; exit 1 }

# ── 5. 引擎子模块（editable，含 onnxruntime/psutil；与 CI 一致）──
Write-Step "安装引擎子模块（editable，numpy/onnxruntime/psutil）..."
& $venvPy -m pip install -e "third_party\video_ocr_engine"
if ($LASTEXITCODE -ne 0) { Write-Error "引擎子模块安装失败"; exit 1 }

# ── 6. decord 解码 fork（参考 RaceVideoToLog：_decord_build 优先，否则下载发布包）──
if (-not $SkipDecord) {
    Write-Step "安装 decord 解码 fork（chr431/decord v0.7.12，解码必需）..."
    $decordVer = "0.7.12"
    $decordExtract = Join-Path $root "_decord_build"

    if (-not (Test-Path (Join-Path $decordExtract "decord.dll"))) {
        # 下载发布包并解压为 _decord_build\（后续复用，布局与 RaceVideoToLog 一致）
        $zip = Join-Path $env:TEMP "decord-$decordVer-win64-gpu.zip"
        $url = "https://github.com/chr431/decord/releases/download/v${decordVer}/decord-${decordVer}-win64-gpu.zip"
        if (-not (Test-Path $zip)) {
            Write-Host "    下载 $url ..."
            $progressSave = $ProgressPreference
            $ProgressPreference = "SilentlyContinue"   # 大文件下载提速
            try {
                Invoke-WebRequest -Uri $url -OutFile $zip
            } catch {
                $ProgressPreference = $progressSave
                Write-Error "decord 发布包下载失败：$url`n$($_.Exception.Message)"
                exit 1
            }
            $ProgressPreference = $progressSave
            if (-not (Test-Path $zip)) { Write-Error "decord 发布包下载失败"; exit 1 }
        }
        Write-Host "    解压发布包 -> _decord_build\ ..."
        Remove-Item -Recurse -Force $decordExtract -ErrorAction SilentlyContinue
        Expand-Archive -Path $zip -DestinationPath $decordExtract
        # zip 内容根是 _decord_build\...，上移一级使其布局与 RaceVideoToLog 一致
        $inner = Join-Path $decordExtract "_decord_build"
        if (Test-Path (Join-Path $inner "decord.dll")) {
            Get-ChildItem $inner | Move-Item -Destination $decordExtract -Force
            Remove-Item -Recurse -Force $inner -ErrorAction SilentlyContinue
        }
    } else {
        Write-Step "使用已有 _decord_build\（发布产物）。"
    }

    # 装入 site-packages\decord（纯 Python 层 + decord.dll + FFmpeg dll + ffprobe）
    $decordSite = Join-Path $venvRoot "Lib\site-packages\decord"
    if (Test-Path $decordSite) { Remove-Item -Recurse -Force $decordSite }
    New-Item -ItemType Directory -Path $decordSite -Force | Out-Null
    Get-ChildItem (Join-Path $decordExtract "*.dll") -ErrorAction SilentlyContinue |
        Copy-Item -Destination $decordSite -Force
    Copy-Item -Force (Join-Path $decordExtract "ffprobe.exe") $decordSite -ErrorAction SilentlyContinue
    if (Test-Path (Join-Path $decordExtract "python\decord\__init__.py")) {
        Copy-Item -Recurse -Force (Join-Path $decordExtract "python\decord\*") $decordSite
    }

    # 自检：decord 通过 ctypes 加载 decord.dll；失败多为杀毒/安全策略拦 DLL
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $venvPy -c "from decord import VideoReader, cpu" 2>&1 | Out-Null
    $decordOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEap
    if (-not $decordOk) {
        Write-Error "decord fork 安装后导入自检失败（请检查杀毒软件是否拦截了 .venv\Lib\site-packages\decord 下的 DLL）。"
        exit 1
    }
    Write-Host "    ✓ decord v$decordVer 就绪（site-packages\decord）。"
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
    Write-Host "  解码后端:   decord v$decordVer（site-packages\decord；发布包缓存于 _decord_build\）"
}
Write-Host ""
