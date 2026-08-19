"""引擎子模块路径引导：把 third_party/video_ocr_engine 加入 sys.path。

本仓库通过 git submodule 使用通用引擎 chr431/video_ocr_engine；引擎仓库根目录
（engine_config.py / segmentation.py / video_ocr_engine/ ...）即 Python 源码
根，必须加入 sys.path 才能 import 引擎顶层模块与 video_ocr_engine 包。

必须在任何 import 引擎模块之前调用。覆盖入口：
  - subtitle_extract_cli.py 顶部（CLI）
  - pytest 根 conftest.py（本地/CI）
"""
from __future__ import annotations

import sys
from pathlib import Path

_ENGINE_DIRNAME = "video_ocr_engine"


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
    return p


if __name__ == "__main__":
    print("engine path:", ensure_engine_path())
