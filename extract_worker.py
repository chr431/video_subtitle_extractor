"""导出 worker — 后台线程跑引擎 FieldExtractor + 写 CSV（保持 GUI 响应）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

# ── 引擎子模块路径引导（必须在 import 引擎模块之前）──
from engine_bootstrap import ensure_engine_path  # noqa: E402
ensure_engine_path()

from video_ocr_engine import FieldExtractor  # noqa: E402
from subtitle_extract_cli import (  # noqa: E402
    build_rows, postprocess_rows, write_csv,
)


class _Cancelled(Exception):
    pass


class ExtractWorker(QThread):
    """在子线程跑 解码+分段+OCR → 写 CSV。

    信号:
        progress(str, float)  — 进度消息 + 百分比 0-100
        succeeded(int, str, float) — 成功：(文本条数, 输出路径, fps)
        failed(str)           — 失败/取消：错误信息
    """

    progress = Signal(str, float)
    succeeded = Signal(int, str, float)
    failed = Signal(str)

    def __init__(self, video: Path, roi: tuple, start: int, end: int,
                 stride: int, out: Path, postprocess: bool = True,
                 parent=None) -> None:
        super().__init__(parent)
        # 注意：不能用 self.start/self.end 命名，会遮蔽 QThread.start() 方法
        self.video = video
        self.roi = roi
        self.start_frame = start
        self.end_frame = end
        self.stride = stride
        self.out = out
        self.postprocess = postprocess
        self._cancelled = False

    def cancel(self) -> None:
        """设置取消标志（引擎在下个检查点抛错退出的 cancel_check）。"""
        self._cancelled = True

    def run(self) -> None:
        try:
            ex = FieldExtractor(
                str(self.video), self.roi,
                frame_start=self.start_frame,
                frame_end=None if (self.end_frame is None or self.end_frame <= 0) else self.end_frame,
                sample_stride=self.stride,
                decode_backend="auto", ocr_backend="cpu",
                progress_cb=lambda m, p: self.progress.emit(m, p),
                cancel_check=self._check_cancel,
            )
            result = ex.extract()
            rows = build_rows(result)
            if self.postprocess:
                rows = postprocess_rows(rows)
            write_csv(self.out, rows)
            self.succeeded.emit(len(rows), str(self.out), result.fps or 0.0)
        except _Cancelled:
            self.failed.emit("已取消")
        except Exception as e:  # noqa: BLE001 — 子线程错误经信号回传
            self.failed.emit(str(e))

    def _check_cancel(self) -> None:
        if self._cancelled:
            raise _Cancelled()
