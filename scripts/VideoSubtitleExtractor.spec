# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 一键冻结 GUI（由 scripts/build_exe.ps1 调用）。

参考 RaceVideoToLog.spec：按需精简约依赖，只带本项目/引擎真正需要的部件：
  - 构建时临时从 PATH 屏蔽 CUDA/TensorRT（本项目 OCR 走 onnxruntime CPU）
  - onnxruntime：只留 CPU 推理（排除 DirectML / TRT / CUDA provider 与非推理子目录）
  - 排除 scipy / Pillow / tkinter / paddle / yaml / numpy.random / numpy.fft 等未用依赖
  - 精简未用的 Qt 模块与旧版 FFmpeg DLL、decord 发布产物中不需要的 avdevice/ffprobe
  - 保留：引擎子模块源码树（engine_bootstrap 存在性检查 + OCR 模型随包），
    decord 运行时 DLL（decord_rthook.py 负责定位），qfluentwidgets 资源。
"""
import os
from pathlib import Path

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_all

# ═══════════════════ 构建时屏蔽 CUDA / TensorRT 路径 ═══════════════════
# 本项目不依赖 GPU 加速（OCR=cpu），避免 PyInstaller 把系统 CUDA/TRT DLL 抓进包。
_SAVED_PATH = os.environ.get("PATH", "")
_PATH_BLOCKLIST = {"cuda", "cudnn", "tensorrt"}
os.environ["PATH"] = ";".join([
    p for p in _SAVED_PATH.split(";")
    if not any(b in p.lower() for b in _PATH_BLOCKLIST)
])

# ═══════════════════ 路径常量 ═══════════════════
try:
    SPEC_DIR = Path(SPECPATH)
except NameError:
    SPEC_DIR = Path.cwd()
REPO = SPEC_DIR.parent
ENGINE = REPO / "third_party" / "video_ocr_engine"
if not (ENGINE / "video_ocr_engine" / "__init__.py").is_file():
    raise SystemExit(
        f"引擎子模块缺失: {ENGINE}\n"
        "请先运行 scripts/setup.ps1 或 `git submodule update --init --recursive`。")

datas = []
binaries = []
hiddenimports = [
    'queue', 'threading',
    # numpy 2.x 与 PyInstaller 兼容性修复（参考 RaceVideoToLog）
    'numpy._core._multiarray_umath', 'numpy._core.multiarray',
    'numpy._core.umath', 'numpy._core._methods',
    'decord',
    # 本项目模块（显式列出更稳）
    'gui', 'gui_video', 'extract_worker', 'preview_widget', 'widget_utils',
    'subtitle_extract_cli', 'engine_bootstrap',
    # 引擎顶层模块与包（pathex 提供；引擎源码树亦随包）
    'engine_config', 'gpu_setup', 'hybrid_decode', 'ocr_native', 'ocr_trt',
    'segmentation', 'video_utils', 'video_ocr_engine',
]

# ── 基础依赖收集 ──
# onnxruntime（CPU 推理）
_ort = collect_all('onnxruntime')
datas += _ort[0]; binaries += _ort[1]; hiddenimports += _ort[2]
# qfluentwidgets（Fluent 组件库资源/模块）
_qfw = collect_all('qfluentwidgets')
datas += _qfw[0]; binaries += _qfw[1]; hiddenimports += _qfw[2]
# decord（纯 Python + 运行时 ctypes 定位的 decord.dll/FFmpeg dll）
_dec = collect_all('decord')
datas += _dec[0]; binaries += _dec[1]; hiddenimports += _dec[2]
# PySide6 核心模块（只收集本项目用到的 Qt 模块）
for _qt_mod in ['PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui',
                'PySide6.QtXml', 'PySide6.QtSvg']:
    _qt = collect_all(_qt_mod)
    datas += _qt[0]; binaries += _qt[1]; hiddenimports += _qt[2]

# ── 引擎源码树 + OCR 模型完整随包（排除 .git/测试/缓存）──
# 引擎根随包能让 engine_bootstrap.ensure_engine_path() 在 frozen 下照常工作，
# OCR 模型（assets/ocr_models）也在树内，_models_dir() 按 __file__ 相对解析即命中。
datas += [(src, dest) for dest, src, _ in Tree(
    str(ENGINE),
    prefix="third_party/video_ocr_engine",
    excludes=[".git", "__pycache__", ".github", ".pytest_cache", "tests", "*.pyc"],
)]

# ═══════════════════ 精简 ═══════════════════
# onnxruntime 未用 provider + 非推理子目录
_EXCLUDE_FILES = {
    'DirectML.dll', 'onnxruntime_providers_tensorrt.dll',
    'onnxruntime_providers_cuda.dll',
}
datas = [(s, d) for s, d in datas
         if os.path.basename(s) not in _EXCLUDE_FILES
         and not os.path.basename(s).endswith('.engine')]
binaries = [(s, d) for s, d in binaries
            if os.path.basename(s) not in _EXCLUDE_FILES
            and not os.path.basename(s).endswith('.engine')]

_EXCLUDE_DATAS_SUBDIRS = {
    'onnxruntime\\transformers', 'onnxruntime\\tools',
    'onnxruntime\\quantization', 'onnxruntime\\datasets',
    'onnxruntime\\backend',
}
datas = [(s, d) for s, d in datas
         if not any(e in d.replace('/', '\\') for e in _EXCLUDE_DATAS_SUBDIRS)]

a = Analysis(
    [str(REPO / "gui.py")],
    pathex=[str(ENGINE)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(SPEC_DIR / "decord_rthook.py")],
    excludes=[
        'onnxruntime.transformers', 'onnxruntime.transformers.*',
        'onnxruntime.tools', 'onnxruntime.tools.*',
        'onnxruntime.quantization', 'onnxruntime.quantization.*',
        'onnxruntime.datasets', 'onnxruntime.datasets.*',
        'onnxruntime.backend',
        # scipy / tkinter：本项目零引用
        'scipy', 'tkinter', '_tkinter',
        # PaddlePaddle（rapidocr 时代遗留，~1.1GB）
        'paddle', 'paddlepaddle', 'paddlepaddle_gpu',
        'safetensors', 'opt_einsum', 'networkx',
        # Pillow：仅 qfluentwidgets 可选 acrylic fallback import，本项目零引用
        'PIL', 'PIL.*', 'Pillow',
        # yaml：仅 numpy.__config__ 可选 import
        'yaml',
        # numpy.random / numpy.fft：本项目零引用（PyInstaller 惰性 __getattr__ 误收）
        'numpy.random', 'numpy.fft',
    ],
    noarchive=False,
    optimize=2,   # 最高字节码优化：移除 docstring 和 assert
)
pyz = PYZ(a.pure)

# ── EXE 版本资源（Windows 属性 → 属性/详细信息；失败不阻断构建）──
_VERSION_INFO = None
try:
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
        StringStruct, VarFileInfo, VarStruct,
    )
    _VER_PARTS = [0, 1, 0]
    _VER_TUPLE = tuple(_VER_PARTS + [0])
    _VERSION_INFO = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=_VER_TUPLE, prodvers=_VER_TUPLE,
            mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo([
                StringTable('040904B0', [
                    StringStruct('CompanyName', 'video-subtitle-extractor'),
                    StringStruct('FileDescription', 'Video Subtitle Extractor - 视频字幕提取'),
                    StringStruct('FileVersion', '0.1.0'),
                    StringStruct('ProductName', 'Video Subtitle Extractor'),
                    StringStruct('ProductVersion', '0.1.0'),
                ]),
            ]),
            VarFileInfo([VarStruct('Translation', [1033, 1200])]),
        ],
    )
except Exception:  # 版本资源是附加信息，任何失败都不该阻断构建
    _VERSION_INFO = None

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VideoSubtitleExtractor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_VERSION_INFO,
)

# ── 之后再精简：移除 Analysis 重新发现的未用 DLL（参考 RaceVideoToLog）──
_EXCLUDE_BINARIES = {
    'DirectML.dll', 'onnxruntime_providers_tensorrt.dll',
    'onnxruntime_providers_cuda.dll',
    'tcl86t.dll', 'tk86t.dll', '_tkinter.pyd',
    # Qt6 未用模块（本项目只用 qfluentwidgets + Widgets/Core/Gui/Svg/Xml）
    'opengl32sw.dll',
    'Qt6Quick.dll', 'Qt6Qml.dll', 'Qt6Pdf.dll',
    'Qt6Network.dll', 'Qt6Multimedia.dll',
    'Qt6Sql.dll', 'Qt6Test.dll',
    'Qt6QuickWidgets.dll', 'Qt6QmlModels.dll', 'Qt6QmlWorkerScript.dll',
    'Qt6PrintSupport.dll', 'Qt6WebChannel.dll',
    'Qt6WebEngine.dll', 'Qt6WebEngineCore.dll', 'Qt6WebEngineQuick.dll',
    'Qt6Designer.dll', 'Qt6Help.dll', 'Qt6UiTools.dll',
    # PySide6 自带的旧版 FFmpeg（decord 提供 FFmpeg 8.x avcodec-62 等）
    'swresample-5.dll', 'swscale-8.dll', 'avformat-61.dll',
    'avutil-59.dll', 'avcodec-61.dll', 'avdevice-61.dll', 'avfilter-10.dll',
    'postproc-58.dll',
    'avformat-60.dll', 'avutil-58.dll', 'avcodec-60.dll',
    'avdevice-60.dll', 'avfilter-9.dll', 'postproc-57.dll',
    'avcodec-58.dll', 'avformat-58.dll', 'avutil-56.dll',
    'avfilter-7.dll', 'avdevice-58.dll', 'swresample-3.dll',
    'swscale-5.dll', 'postproc-55.dll',
    'avcodec-59.dll', 'avformat-59.dll', 'avutil-57.dll',
    'avfilter-8.dll', 'avdevice-59.dll', 'swresample-4.dll',
    'swscale-6.dll', 'postproc-56.dll',
    # decord 发布产物中运行时不需要的二进制（decord.dll 不导入 avdevice；不调用 ffprobe）
    'avdevice-62.dll', 'ffprobe.exe',
    'qdirect2d.dll', 'libcrypto-3-x64.dll', 'libssl-3-x64.dll',
}
_PIL_BINARY_PREFIXES = ('_avif', '_imaging', '_webp', '_imagingft',
                        '_imagingmath', '_imagingcms', '_imagingtk')
a.binaries = [(n, p, t) for n, p, t in a.binaries
              if os.path.basename(p) not in _EXCLUDE_BINARIES
              and not os.path.basename(p).startswith(_PIL_BINARY_PREFIXES)]


def _keep_translation(p: str) -> bool:
    """只保留 Qt 的英文/中文翻译，其余 ~6MB 与目标用户无关。"""
    name = os.path.basename(p).lower()
    if 'translations' not in p.replace('\\', '/').lower():
        return True
    return (name.startswith(('qt_en', 'qt_zh_cn', 'qt_zh_tw'))
            or name.startswith(('qtbase_en', 'qtbase_zh_cn', 'qtbase_zh_tw'))
            or name.startswith(('qt_help_en', 'qt_help_zh_cn', 'qt_help_zh_tw')))


# 移除 tk/tcl 数据 + 非中英文 Qt 翻译 + PIL 数据
a.datas = [(n, p, t) for n, p, t in a.datas
           if '_tcl_data' not in p and '_tk_data' not in p and 'tcl8' not in p
           and _keep_translation(p)
           and 'PIL' not in p.replace('/', '\\')]

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[
        'onnxruntime.dll', 'onnxruntime_providers_shared.dll',
        # decord FFmpeg 8.x DLLs (UPX may corrupt)
        'avcodec-62.dll', 'avformat-62.dll', 'avutil-60.dll',
        'swresample-6.dll', 'swscale-9.dll',
    ],
    name="VideoSubtitleExtractor",
)
