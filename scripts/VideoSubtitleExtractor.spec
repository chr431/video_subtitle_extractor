# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 一键冻结 GUI（由 scripts/build_exe.ps1 调用）。

打包策略（引擎子模块 third_party/video_ocr_engine 整体随包）：
  - 引擎源码树作为 data 落在 <bundle>/third_party/video_ocr_engine：
    engine_bootstrap.ensure_engine_path() 在 frozen 下仍能通过子模块存在性检查
    并把该目录插入 sys.path，行为与源码运行一致（OCR 模型也在该目录内，
    ocr_native._models_dir() 用 __file__ 相对解析即命中）。
  - Analysis pathex 指向引擎根，让静态分析解析到 video_ocr_engine 包及
    engine_config/segmentation/... 等顶层模块（PYZ 内编译副本；运行时由上述
    data 目录中的源码优先加载，二者不冲突）。
"""
from pathlib import Path

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# PyInstaller 在 spec 命名空间注入 SPECPATH（spec 所在目录）；__file__ 不可用，
# 这里用同名变量当前工作目录兜底。
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

block_cipher = None


def _optional(pkg: str) -> list:
    """可选/运行时延迟导入的依赖：未安装时跳过，避免 hidden-import 告警干扰构建。"""
    try:
        __import__(pkg)
        return [pkg]
    except ImportError:
        return []


# ── 引擎源码 + 模型完整随包（排除 .git/测试/缓存）──
# Tree 产出 (dest, src, typecode)；Analysis(datas=) 需要 (src, dest) 二元组，先翻转。
engine_tree = Tree(
    str(ENGINE),
    prefix="third_party/video_ocr_engine",
    excludes=[".git", "__pycache__", ".github", ".pytest_cache", "tests", "*.pyc"],
)
datas = [(src, dest) for dest, src, _ in engine_tree]
# qfluentwidgets 的 qss/图标等资源
datas += collect_data_files("qfluentwidgets")

hiddenimports = [
    # 引擎顶层模块（引擎根在 pathex 可静态解；显式列出兜底）
    "engine_config", "gpu_setup", "hybrid_decode", "ocr_native", "ocr_trt",
    "segmentation", "video_utils",
]
# 引擎内方法体内延迟导入的解码/推理依赖（decord fork 未必安装，缺失时跳过）
hiddenimports += _optional("decord") + _optional("onnxruntime") + _optional("psutil")
hiddenimports += collect_submodules("qfluentwidgets")

a = Analysis(
    [str(REPO / "gui.py")],
    pathex=[str(ENGINE)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VideoSubtitleExtractor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # GUI 应用：无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VideoSubtitleExtractor",
)
