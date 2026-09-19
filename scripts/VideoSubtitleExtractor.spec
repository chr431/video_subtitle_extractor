# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 一键冻结 GUI（由 scripts/build_exe.ps1 调用）。

参考 RaceVideoToLog.spec：按需精简约依赖，只带本项目/引擎真正需要的部件：
  - 构建时临时从 PATH 屏蔽 CUDA/TensorRT（本项目 OCR 走 OpenVINO CPU）
  - OpenVINO：收集后按冻结瘦身配方剪枝（NPU/GPU 插件、非 ONNX 前端、
    C 头文件全删；只留 CPU 推理闭包）
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
# 引擎已 pip 化：不再依赖 third_party 子模块源码树，模块与模型资产都从
# venv 中已安装的 video-ocr-engine 包解析（ocr_native._models_dir 覆盖
# 源码树 / site-packages / frozen 三种布局）。

datas = []
binaries = []
hiddenimports = [
    'queue', 'threading',
    # numpy 2.x 与 PyInstaller 兼容性修复（参考 RaceVideoToLog）
    'numpy._core._multiarray_umath', 'numpy._core.multiarray',
    'numpy._core.umath', 'numpy._core._methods',
    'decord',
    # 本项目模块（显式列出更稳）
    'gui', 'gui_video', 'gui_settings', 'app_config', 'theme_manager',
    'extract_worker', 'preview_widget', 'widget_utils',
    'subtitle_extract_cli', 'tensorrt',
    # 引擎模块与包（已随 venv 安装，显式列出防漏收动态 import）
    # 2026-09-19：引擎 0.14.1 删除六个根模块 shim（engine_config /
    # gpu_setup / ocr_native / ocr_trt / segmentation / video_utils）→
    # 本表改用包内路径；旧名会让 PyInstaller 报 ModuleNotFoundError。
    'video_ocr_engine', 'video_ocr_engine.config.constants',
    'video_ocr_engine.ocr.native', 'video_ocr_engine.ocr.trt',
    'video_ocr_engine.domain.segmentation',
    'video_ocr_engine.domain.video_utils',
    'video_ocr_engine.gpu.context', 'video_ocr_engine.pipeline.engine',
    'video_ocr_engine.extractor',
]

# ── 基础依赖收集 ──
# openvino（2026-09-19：引擎 C-48 起 CPU OCR 唯一后端 = OpenVINO，
# onnxruntime 已从引擎依赖移除、本项目也不使用它 → 换掉并省 ~45MB）。
# 发行 wheel 是全家桶（NPU 编译器 82MB / Intel GPU 插件 34MB / 各家前端），
# 本项目只用 CPU 设备 → 收集后在构建末剪枝（见文件末尾 _prune_openvino）。
_ov = collect_all('openvino')
datas += _ov[0]; binaries += _ov[1]; hiddenimports += _ov[2]
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

# ── TRT（可选，thin binding）—— 装了才收集；没装则跳过，引擎运行时回退 ONNX ──
# 注意：构建期不把系统 CUDA / TensorRT DLL 打包（本项目从 PATH 动态定位）。
try:
    _trt = collect_all('tensorrt_bindings')
    datas += _trt[0]; binaries += _trt[1]; hiddenimports += _trt[2]
except Exception:
    pass
try:
    import importlib.util
    if importlib.util.find_spec('cuda.bindings'):
        hiddenimports += [
            'cuda', 'cuda.bindings', 'cuda.bindings.runtime',
            'cuda.bindings.driver', 'cuda.bindings.utils',
        ]
except Exception:
    pass

# ── OCR 模型随包（video-ocr-engine pip 包的 data-files）──
# 位置由引擎自己解析（_models_dir 覆盖 源码树 / site-packages /
# frozen 三种布局）；spec 构建期未 frozen，拿到的是已安装引擎的资产目录。
# 打包到 _internal/ocr_models，frozen 下 _models_dir() 命中 _MEIPASS 同名目录。
# 2026-09-19：ocr_native → 包内路径（引擎 shim 已删）。
from video_ocr_engine.ocr.native import _models_dir as _ov_models_dir
_OCR_MODELS_ROOT = str(_ov_models_dir())
datas += [(src, dest) for dest, src, _ in Tree(
    _OCR_MODELS_ROOT,
    prefix="ocr_models",
    excludes=[".git", "__pycache__", "*.pyc"],
)]

# ═══════════════════ 精简 ═══════════════════
# onnxruntime 未用 provider + 非推理子目录（历史遗留：本应用已不用 ORT，
# 这些排除项对不存在的包无害，保留以防某依赖间接带入）
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

# 引擎包搜索路径（2026-09-19 修复两处既有缺陷）：
#  ① 原写 pathex=[str(ENGINE)]，ENGINE **从未定义**（submodule → pip 依赖
#     重构时漏改，被更早的构建失败掩盖）；
#  ② 首版修复从 _models_dir() 上溯——但 CI 用 `pip install -e .` 装引擎，
#     _models_dir() 指向**引擎源码树**的 assets，而 editable 安装的包实际
#     经 .pth 挂在 site-packages → 上溯得到错误路径，PyInstaller 找不到包
#     → 产物**完全不含引擎代码**（实测 _internal 无 video_ocr_engine、
#     PYZ 无 extractor.py，frozen 启动即 ImportError）。
# 正解：直接取 `video_ocr_engine` 包的 __file__（import 已成功，两种安装
# 方式都给出真实位置），其父目录即 pathex 搜索根。
import video_ocr_engine as _voe
_ENGINE_SEARCH_ROOT = str(Path(_voe.__file__).resolve().parent.parent)

a = Analysis(
    [str(REPO / "gui.py")],
    pathex=[_ENGINE_SEARCH_ROOT],
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

# ── OpenVINO 剪枝（CPU-only 部署；2026-09-19）──────────────────────────
# 发行 wheel 含 NPU 编译器/Intel GPU 插件/多前端/C 头文件，本项目只用 CPU
# → 按引擎仓冻结瘦身配方删（docs/log/2026-09-14-OpenVINO冻结瘦身.md）。
# 实证（本机 2026.3.1）：234MB → 74MB（−68%），剩余为 CPU 推理闭包。
def _prune_openvino(build_root: str) -> None:
    import glob
    import os
    import shutil
    ov = os.path.join(build_root, 'openvino')
    if not os.path.isdir(ov):
        print('[prune] NOT FOUND %s, skipping (layout changed?)' % ov)
        return
    before = sum(os.path.getsize(f) for f in glob.glob(ov + '/**/*', recursive=True)
                 if os.path.isfile(f))
    pats = [
        'openvino_intel_npu_compiler.dll', 'openvino_intel_npu_compiler_loader.dll',
        'openvino_intel_npu_plugin.dll', 'openvino_intel_npu_vm_runtime.dll',
        'openvino_intel_gpu_plugin.dll', 'openvino_auto_plugin.dll',
        'openvino_auto_batch_plugin.dll', 'openvino_hetero_plugin.dll',
        'openvino_tensorflow_frontend.dll', 'openvino_tensorflow_lite_frontend.dll',
        'openvino_pytorch_frontend.dll', 'openvino_paddle_frontend.dll',
        'openvino_jax_frontend.dll', 'openvino_ir_frontend.dll',
        '*.lib', 'cache.json', '*_debug*',
    ]
    for pat in pats:
        for f in glob.glob(os.path.join(ov, 'libs', pat)):
            os.remove(f)
    for d in ('include', 'tools', 'frontend'):
        shutil.rmtree(os.path.join(ov, d), ignore_errors=True)
    after = sum(os.path.getsize(f) for f in glob.glob(ov + '/**/*', recursive=True)
                if os.path.isfile(f))
    # 完整性门禁：CPU 闭包必须在
    for must in ('openvino.dll', 'openvino_intel_cpu_plugin.dll',
                 'openvino_onnx_frontend.dll'):
        if not os.path.isfile(os.path.join(ov, 'libs', must)):
            raise SystemExit('[prune] 误删 CPU 闭包文件: %s' % must)
    print('[prune] openvino %.0fMB -> %.0fMB' % (before / 1e6, after / 1e6))


# spec 由 PyInstaller exec 执行：用 __file__ 推导 dist 路径（spec 在
# scripts/ 下）；构建完成的 dist 目录布局 = <name>/_internal
import os as _os
_prune_openvino(_os.path.join(_os.path.dirname(_os.path.dirname(
    _os.path.abspath(__file__))) if '__file__' in dir() else '.',
    'dist', 'VideoSubtitleExtractor', '_internal'))
