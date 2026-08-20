"""引擎子模块路径引导：把 third_party/video_ocr_engine 加入 sys.path。

本仓库通过 git submodule 使用通用引擎 chr431/video_ocr_engine；引擎仓库根目录
（engine_config.py / segmentation.py / video_ocr_engine/ ...）即 Python 源码
根，必须加入 sys.path 才能 import 引擎顶层模块与 video_ocr_engine 包。

必须在任何 import 引擎模块之前调用。覆盖入口：
  - subtitle_extract_cli.py 顶部（CLI）
  - pytest 根 conftest.py（本地/CI）
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

_ENGINE_DIRNAME = "video_ocr_engine"
_AV_LOG_QUIET = -8
_AV_LOG_ERROR = 16
_AV_LOG_WARNING = 24
_FFMPEG_LEVELS = {
    "quiet": _AV_LOG_QUIET,
    "error": _AV_LOG_ERROR,
    "warning": _AV_LOG_WARNING,
    "info": 32,
    "verbose": 40,
}


def _silence_ffmpeg() -> bool:
    """设置 FFmpeg/decord 全局日志级别，压制 MKV 容器不规范的良性噪音。

    部分 MKV（如部分压制/损坏片源）会让 FFmpeg Matroska demuxer 输出大量
    "Element ... exceeds containing master element" 日志，但 FFmpeg 能跳过
    并继续解码，不影响输出。默认 QUIET 静音；用环境变量 RVTOL_FFMPEG_LOG_LEVEL
    覆盖（quiet/error/warning/info/verbose）。
    """
    try:
        import importlib.util
        level = _FFMPEG_LEVELS.get(
            os.environ.get("RVTOL_FFMPEG_LOG_LEVEL", "quiet").lower(),
            _AV_LOG_QUIET)
        spec = importlib.util.find_spec("decord")
        if spec is None or not spec.origin:
            return False
        avutil = Path(spec.origin).parent / "avutil-60.dll"
        if not avutil.is_file():
            return False
        lib = ctypes.CDLL(str(avutil))
        lib.av_log_set_level.argtypes = [ctypes.c_int]
        lib.av_log_set_level(level)
        return True
    except Exception:
        return False


def engine_path() -> Path:
    """引擎子模块源码根目录（third_party/video_ocr_engine）。"""
    return Path(__file__).resolve().parent / "third_party" / _ENGINE_DIRNAME


def ensure_engine_path() -> Path:
    """把引擎源码根目录加入 sys.path（幂等），返回该路径。

    子模块缺失（未 clone / 未 init）时抛 RuntimeError，给出修复指引。
    """
    p = engine_path()
    if not (p / "video_ocr_engine").is_dir():
        raise RuntimeError(
            f"引擎子模块缺失: {p}\n"
            "请执行 `git submodule update --init --recursive` 获取 "
            "chr431/video_ocr_engine")
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)
    # 统一静音 FFmpeg demuxer 噪音（不影响解码/输出；可用 env 恢复）
    _silence_ffmpeg()
    return p


if __name__ == "__main__":
    print("engine path:", ensure_engine_path())
