"""pytest 根配置：把引擎子模块源码根加入 sys.path（见 engine_bootstrap）。"""
from __future__ import annotations

import sys
from pathlib import Path

_ENGINE = Path(__file__).resolve().parent / "third_party" / "video_ocr_engine"
if not (_ENGINE / "video_ocr_engine").is_dir():
    raise RuntimeError(
        f"引擎子模块缺失: {_ENGINE}\n"
        "请执行 `git submodule update --init --recursive`")
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))
