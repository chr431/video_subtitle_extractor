"""应用侧视频工具（自 0.2.1 起从引擎拆回）。

这三个名字（VideoMetadata / format_duration / open_decord_vr）原本一直
"蹭"引擎仓库的 video_utils —— 本项目 py-modules 里没有 video_utils，
`from video_utils import ...` 命中的是引擎源码树里的同名模块。引擎 0.9.0
清理轮把这些应用侧辅助函数从引擎里移除了，只能搬回应用侧。

模块名刻意用 video_utils_app 而非 video_utils，避免与引擎 pip 包的
video_utils 模块冲突（RaceVideoToLog 同款处理）。

open_decord_vr 的 DECORD_FORCE_CPU env 为应用侧自有开关：引擎 0.9 起解码
设备由 FieldExtractor(decode_backend=...) 参数控制，不再读该 env；此函数
只服务于 GUI 的"预览打开视频"场景。
"""
from __future__ import annotations

import os as _os
from dataclasses import dataclass
from functools import lru_cache  # noqa: F401  （保持与旧版兼容的导入面）
from pathlib import Path

_FORCE_CPU_ENV = "DECORD_FORCE_CPU"


@dataclass
class VideoMetadata:
    path: Path
    duration_sec: float
    width: int
    height: int
    fps: float
    codec: str
    frame_count: int


def format_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def open_decord_vr(video_path, force_cpu: bool = False):
    """Open video with decord — GPU (NVDEC) preferred, CPU fallback.

    Returns (VideoReader, label) where label is ``'GPU'`` or ``'CPU'``.
    Set ``DECORD_FORCE_CPU=1`` in the environment or pass *force_cpu=True*
    to skip GPU even when available.
    """
    from decord import VideoReader as _VR

    _vr = None
    _label = "CPU"
    _force = force_cpu or _os.environ.get(_FORCE_CPU_ENV, "").strip() == "1"

    if not _force:
        try:
            from decord import gpu as _decord_gpu
            _vr = _VR(str(video_path), ctx=_decord_gpu(0))
            _label = "GPU"
        except Exception:
            pass

    if _vr is None:
        try:
            from decord import cpu as _decord_cpu
            _vr = _VR(str(video_path), ctx=_decord_cpu(0))
        except ModuleNotFoundError:
            raise RuntimeError(
                "decord 未安装（需要 chr431/decord fork，PyPI 官方版不支持本项目特性）。"
                "请运行 scripts/setup.ps1，或 pip install -e . 按 pyproject.toml 安装")
        except Exception as _e:
            raise RuntimeError(f"decord 无法打开视频: {_e}")

    return _vr, _label
