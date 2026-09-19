# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 一键冻结 **GUI + CLI 双入口**（由 scripts/build_exe.ps1 调用）。

产物（dist/VideoSubtitleExtractor/，两个 exe **共享同一份 `_internal/`**）：
  - `VideoSubtitleExtractor.exe`  GUI（console=False：无控制台窗口）
  - `subtitle-extract.exe`        CLI（console=True：进度/错误可见、可重定向；
                                  名字与 pip entry point 一致，README 的命令照抄即用）
双入口是本项目的既定形态（CLAUDE.md：「CLI 与 GUI 功能必须保持同步」；README
把 CLI 与 GUI 并列为首要用法），因此**冻结产物必须同时含两端**——0.2.1 及更早
的产物只有 GUI exe，CLI 仅存在于源码/pip 安装形态。

CLI 侧单独 Analysis 且**不收集 Qt/qfluentwidgets**（CLI 不 import 它们）：
一是语义正确（命令行不该拖一个 GUI 依赖），二是避免 Qt 的纯 Python 模块在
两个 exe 的 PYZ 里各存一份。共享二进制/data 由 COLLECT 按 (dest, src) 去重。

参考 RaceVideoToLog.spec：按需精简约依赖，只带本项目/引擎真正需要的部件：
  - 构建时临时从 PATH 屏蔽 CUDA/TensorRT（本项目 OCR 走 OpenVINO CPU）
  - OpenVINO：收集后按冻结瘦身配方剪枝（NPU/GPU 插件、非 ONNX 前端、
    C 头文件全删；只留 CPU 推理闭包）
  - 排除 scipy / Pillow / tkinter / paddle / yaml / numpy.random / numpy.fft 等未用依赖
  - 精简未用的 Qt 模块与旧版 FFmpeg DLL
  - 保留：OCR 模型（assets/ocr_models → _internal/ocr_models），decord 运行时
    DLL（decord_rthook.py 负责定位），qfluentwidgets 资源。

注：**不**采用 RaceVideoToLog 的 FFmpeg 极简集替换——那套构建只含
h264/hevc/vp9 解码器与 mov/matroska/avi 解封装，而本项目 README 明确支持
`.wmv/.flv/.ts/.m2ts/.mpg/.mpeg/.webm`，替换会让这些格式静默失效。
"""
import os
from pathlib import Path

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
# venv 中已安装的 video-ocr-engine 包解析（config.models_dir 覆盖
# 源码树 / site-packages / frozen 三种布局）。

# ── 两个入口共用的依赖集合 ──
datas = []
binaries = []
hiddenimports_common = [
    'queue', 'threading',
    # numpy 2.x 与 PyInstaller 兼容性修复（参考 RaceVideoToLog）
    'numpy._core._multiarray_umath', 'numpy._core.multiarray',
    'numpy._core.umath', 'numpy._core._methods',
    'decord',
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
    # TRT thin binding shim（引擎按名动态 import；未装则运行时自动回退）
    'tensorrt',
]
# GUI 专属：本项目 GUI 模块（CLI 侧不导入，避免把 Qt 图拖进 CLI exe 的 PYZ）
hiddenimports_gui = [
    'gui', 'gui_video', 'gui_settings', 'app_config', 'theme_manager',
    'extract_worker', 'preview_widget', 'widget_utils',
    'subtitle_extract_cli',
]
hiddenimports = hiddenimports_common + hiddenimports_gui

# ── 基础依赖收集 ──
# openvino（2026-09-19：引擎 C-48 起 CPU OCR 唯一后端 = OpenVINO，
# onnxruntime 已从引擎依赖移除、本项目也不使用它 → 换掉并省 ~45MB）。
# 发行 wheel 是全家桶（NPU 编译器 82MB / Intel GPU 插件 34MB / 各家前端），
# 本项目只用 CPU 设备 → 收集后在构建末剪枝（见文件末尾 _prune_openvino）。
_ov = collect_all('openvino')
datas += _ov[0]; binaries += _ov[1]; hiddenimports_common += _ov[2]
# decord（纯 Python + 运行时 ctypes 定位的 decord.dll/FFmpeg dll）
_dec = collect_all('decord')
datas += _dec[0]; binaries += _dec[1]; hiddenimports_common += _dec[2]
# qfluentwidgets（Fluent 组件库资源/模块）—— 仅 GUI 需要
_qfw = collect_all('qfluentwidgets')
datas += _qfw[0]; binaries += _qfw[1]; hiddenimports_gui += _qfw[2]
# PySide6 核心模块（只收集本项目用到的 Qt 模块）—— 仅 GUI 需要
for _qt_mod in ['PySide6.QtWidgets', 'PySide6.QtCore', 'PySide6.QtGui',
                'PySide6.QtXml', 'PySide6.QtSvg']:
    _qt = collect_all(_qt_mod)
    datas += _qt[0]; binaries += _qt[1]; hiddenimports_gui += _qt[2]

hiddenimports = hiddenimports_common + hiddenimports_gui

# ── TRT（可选，thin binding）—— 装了才收集；没装则跳过，引擎运行时回退 CPU ──
# 注意：构建期不把系统 CUDA / TensorRT DLL 打包（本项目从 PATH 动态定位）。
try:
    _trt = collect_all('tensorrt_bindings')
    datas += _trt[0]; binaries += _trt[1]; hiddenimports += _trt[2]
except Exception:  # 未装 TRT thin binding：OCR 走 OpenVINO CPU，属正常配置
    pass
try:
    import importlib.util
    if importlib.util.find_spec('cuda.bindings'):
        hiddenimports += [
            'cuda', 'cuda.bindings',
            'cuda.bindings.runtime', 'cuda.bindings.driver',
            'cuda.bindings.utils',
        ]
except Exception:  # 无 cuda.bindings 时引擎不做 GPU 路径，属正常配置
    pass
# CLI 侧 hiddenimports：共用部分 + TRT/cuda（上面 += 的都落在 hiddenimports 里，
# 这里去掉 GUI 专属项即可）
_CLI_DROP = set(hiddenimports_gui)
hiddenimports_cli = [m for m in hiddenimports if m not in _CLI_DROP]

# ── OCR 模型随包（video-ocr-engine pip 包的 data-files）──
# 位置由引擎自己解析（config.models_dir 覆盖 源码树 / site-packages /
# frozen 三种布局）；spec 构建期未 frozen，拿到的是已安装引擎的资产目录。
# 打包到 _internal/ocr_models，frozen 下 models_dir() 命中 _MEIPASS 同名目录。
#
# ⚠️ 用逐个**文件**的 datas 条目（同 RaceVideoToLog），不要用 Tree() 的
# 返回值解包——Tree 的 TOC 形如 (dest, src, typecode)，原写法
# `for dest, src, _ in Tree(...)` 把 dest 当源路径传回 datas，于是
# PyInstaller 把**目录**当成数据文件拷过去：产物里 ocr_models/ppocrv6_dict.txt
# 是个目录，frozen CLI 打开时报 `PermissionError: [Errno 13] ... Is a directory`
# （本轮实测复现）。
from video_ocr_engine.config import constants as _voe_constants
_OCR_MODELS_ROOT = str(_voe_constants.models_dir())
for _root, _dirs, _files in os.walk(_OCR_MODELS_ROOT):
    for _f in _files:
        if _f.endswith('.pyc'):
            continue
        datas.append((
            os.path.join(_root, _f),
            os.path.join('ocr_models',
                         os.path.relpath(_root, _OCR_MODELS_ROOT)),
        ))

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
#  ② 首版修复从 models_dir() 上溯——但 CI 用 `pip install -e .` 装引擎，
#     models_dir() 指向**引擎源码树**的 assets，而 editable 安装的包实际
#     经 .pth 挂在 site-packages → 上溯得到错误路径，PyInstaller 找不到包
#     → 产物**完全不含引擎代码**（实测 _internal 无 video_ocr_engine、
#     PYZ 无 extractor.py，frozen 启动即 ImportError）。
# 正解：直接取 `video_ocr_engine` 包的 __file__（import 已成功，两种安装
# 方式都给出真实位置），其父目录即 pathex 搜索根。REPO 一并加入，让本仓库
# 根目录的模块（gui / subtitle_extract_cli 及各 gui_* 辅助）不依赖
# PyInstaller 隐式加入的入口脚本目录。
import video_ocr_engine as _voe
_ENGINE_SEARCH_ROOT = str(Path(_voe.__file__).resolve().parent.parent)
# site-packages 本就在解释器的模块搜索路径里，再塞进 pathex 只会触发
# PyInstaller 的 "Foreign Python environment" 弃用告警（7.0 起升级为错误）。
# 只有非 site-packages 的根（如本地引擎源码树 editable 安装）才需要显式加入。
_PATHEX = [str(REPO)]
if Path(_ENGINE_SEARCH_ROOT).name != 'site-packages':
    _PATHEX.append(_ENGINE_SEARCH_ROOT)

_EXCLUDES = [
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
]
# CLI 侧额外排除 GUI 栈：CLI 不 import 它们，排除后 CLI exe 的 PYZ 不含 Qt。
_EXCLUDES_CLI = _EXCLUDES + [
    'PySide6', 'PySide6.*', 'qfluentwidgets', 'qfluentwidgets.*',
    'gui', 'gui_video', 'gui_settings', 'app_config', 'theme_manager',
    'extract_worker', 'preview_widget', 'widget_utils',
]

a = Analysis(
    [str(REPO / "gui.py")],
    pathex=_PATHEX,
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(SPEC_DIR / "decord_rthook.py")],
    excludes=_EXCLUDES,
    noarchive=False,
    optimize=2,   # 最高字节码优化：移除 docstring 和 assert
)
a_cli = Analysis(
    [str(REPO / "subtitle_extract_cli.py")],
    pathex=_PATHEX,
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports_cli,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(SPEC_DIR / "decord_rthook.py")],
    excludes=_EXCLUDES_CLI,
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)
pyz_cli = PYZ(a_cli.pure)

# ── EXE 版本资源（Windows 属性 → 属性/详细信息；失败不阻断构建）──
# 版本号取自 pyproject.toml（单一事实源，与 tag / release_notes 一致）——
# 原先硬编码 '0.1.0'，发到 0.2.x 后 exe 属性仍显示 0.1.0（本轮修正）。
_VSE_VERSION = '0.0.0'
try:
    import tomllib as _tomllib
    with open(REPO / "pyproject.toml", "rb") as _f:
        _VSE_VERSION = _tomllib.load(_f)["project"]["version"]
except Exception:  # 版本资源是附加信息，任何失败都不该阻断构建
    # ASCII only: CI console is cp1252 and cannot encode non-ASCII (cda00e6).
    print('[version] failed to read version from pyproject.toml; '
          'falling back to 0.0.0 for version resource')


def _make_version_info(description: str):
    """构造 EXE 版本资源；任何失败返回 None（不阻断构建）。"""
    try:
        import re
        from PyInstaller.utils.win32.versioninfo import (
            VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
            StringStruct, VarFileInfo, VarStruct,
        )
        parts = [int(x) for x in re.findall(r'\d+', _VSE_VERSION)[:3]]
        while len(parts) < 3:
            parts.append(0)
        ver_tuple = tuple(parts + [0])
        return VSVersionInfo(
            ffi=FixedFileInfo(
                filevers=ver_tuple, prodvers=ver_tuple,
                mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                date=(0, 0),
            ),
            kids=[
                StringFileInfo([
                    StringTable('040904B0', [
                        StringStruct('CompanyName', 'video-subtitle-extractor'),
                        StringStruct('FileDescription', description),
                        StringStruct('FileVersion', _VSE_VERSION),
                        StringStruct('ProductName', 'Video Subtitle Extractor'),
                        StringStruct('ProductVersion', _VSE_VERSION),
                    ]),
                ]),
                VarFileInfo([VarStruct('Translation', [1033, 1200])]),
            ],
        )
    except Exception:  # 版本资源是附加信息，任何失败都不该阻断构建
        return None


_NAME_GUI = "VideoSubtitleExtractor"
# CLI exe 名与 pip entry point 一致（README 里写的命令就是 `subtitle-extract`），
# 用户拿到发布包后文档里的命令可直接照抄。
_NAME_CLI = "subtitle-extract"

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=_NAME_GUI,
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
    version=_make_version_info(
        'Video Subtitle Extractor - 视频字幕提取 (GUI)'),
)

exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name=_NAME_CLI,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # 命令行入口必须挂控制台：windowed 子系统下 sys.stdout/stderr 为 None，
    # 进度与错误信息全部丢失。
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_make_version_info(
        'Video Subtitle Extractor - 视频字幕提取 (CLI)'),
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
    # PySide6 自带的旧版 FFmpeg（decord wheel 提供 FFmpeg 63：avcodec-63 等）
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
    # FFmpeg 62（decord 0.7.x zip 产物遗留，现役 wheel 用 63）
    'avcodec-62.dll', 'avformat-62.dll', 'avutil-60.dll',
    'swresample-6.dll', 'swscale-9.dll', 'avfilter-11.dll',
    # decord wheel 自 0.8.2 起已不含 avdevice / ffprobe
    'avdevice-62.dll', 'avdevice-63.dll', 'ffprobe.exe',
    'qdirect2d.dll', 'libcrypto-3-x64.dll', 'libssl-3-x64.dll',
}
_PIL_BINARY_PREFIXES = ('_avif', '_imaging', '_webp', '_imagingft',
                        '_imagingmath', '_imagingcms', '_imagingtk')


def _prune_binaries(toc):
    return [(n, p, t) for n, p, t in toc
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


def _prune_datas(toc):
    """移除 tk/tcl 数据 + 非中英文 Qt 翻译 + PIL 数据。"""
    return [(n, p, t) for n, p, t in toc
            if '_tcl_data' not in p and '_tk_data' not in p and 'tcl8' not in p
            and _keep_translation(p)
            and 'PIL' not in p.replace('/', '\\')]


# 两个入口的依赖集合相同，剪枝必须同时作用于两份 TOC，否则 CLI 侧会把已
# 排除的 DLL 又带回来。
a.binaries = _prune_binaries(a.binaries)
a_cli.binaries = _prune_binaries(a_cli.binaries)
a.datas = _prune_datas(a.datas)
a_cli.datas = _prune_datas(a_cli.datas)

coll = COLLECT(
    exe,
    exe_cli,
    a.binaries,
    a.datas,
    a_cli.binaries,
    a_cli.datas,
    strip=False,
    upx=False,
    upx_exclude=[
        'onnxruntime.dll', 'onnxruntime_providers_shared.dll',
        # decord FFmpeg 63 DLLs（UPX 可能损坏）
        'avcodec-63.dll', 'avformat-63.dll', 'avutil-61.dll',
        'swresample-7.dll', 'swscale-10.dll', 'avfilter-12.dll',
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
    # 完整性门禁：CPU 闭包必须在（ASCII 消息：CI 控制台 cp1252）
    for must in ('openvino.dll', 'openvino_intel_cpu_plugin.dll',
                 'openvino_onnx_frontend.dll'):
        if not os.path.isfile(os.path.join(ov, 'libs', must)):
            raise SystemExit('[prune] removed required CPU-closure file: %s' % must)
    print('[prune] openvino %.0fMB -> %.0fMB' % (before / 1e6, after / 1e6))


# spec 由 PyInstaller exec 执行：COLLECT 在 spec 求值期间已完成拷贝，因此
# 文件末尾可以直接对 dist 目录做剪枝。dist 布局 = <name>/_internal。
_prune_openvino(os.path.join(
    str(SPEC_DIR.parent), 'dist', 'VideoSubtitleExtractor', '_internal'))

# ── 双入口布局门禁 ──
# 构建即自检：CLI exe 悄悄消失（spec 回归）会让"发布产物含 CLI"这一既有承诺
# 失效，与 CI 的冻结冒烟重复一次但更早失败（构建期，几秒钟）。
_DIST = os.path.join(str(SPEC_DIR.parent), 'dist', 'VideoSubtitleExtractor')
for _must_exe in (_NAME_GUI + '.exe', _NAME_CLI + '.exe'):
    if not os.path.isfile(os.path.join(_DIST, _must_exe)):
        raise SystemExit('[layout] missing entry point: %s' % _must_exe)
# ASCII only: CI console is cp1252 and cannot encode non-ASCII (see cda00e6).
print('[layout] both entries ready: %s.exe (GUI) + %s.exe (CLI), '
      'sharing _internal/' % (_NAME_GUI, _NAME_CLI))
