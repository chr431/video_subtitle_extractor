"""导出 worker — 后台线程跑引擎 FieldExtractor + 写 CSV（保持 GUI 响应）。"""
from __future__ import annotations

import queue
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

# ── 引擎子模块路径引导（必须在 import 引擎模块之前）──
from engine_bootstrap import ensure_engine_path  # noqa: E402
ensure_engine_path()

from video_ocr_engine import FieldExtractor  # noqa: E402
from subtitle_extract_cli import (  # noqa: E402
    ProgressGate, build_rows, postprocess_rows, write_combined_csv, write_csv,
)


class _Cancelled(Exception):
    pass


def _opposite_decode(backend: str) -> str:
    """返回互补解码后端：CPU 软解 ↔ 自动/NVDEC（GPU 优先）。"""
    return "auto" if (backend or "").strip().lower() == "cpu" else "cpu"


def _opposite_ocr(backend: str) -> str:
    """返回互补 OCR 后端：CPU ONNX ↔ 自动/TensorRT（GPU 优先）。"""
    return "auto" if (backend or "").strip().lower() == "cpu" else "cpu"


def _opposite_backends(decode: str, ocr: str) -> tuple[str, str]:
    return _opposite_decode(decode), _opposite_ocr(ocr)


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
                 decode_backend: str = "auto", ocr_backend: str = "cpu",
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
        self.decode_backend = decode_backend
        self.ocr_backend = ocr_backend
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
                decode_backend=self.decode_backend,
                ocr_backend=self.ocr_backend,
                progress_cb=ProgressGate(
                    lambda m, p: self.progress.emit(m, p)),
                cancel_check=self._check_cancel,
                # 字幕场景不需要代表帧/帧序列预览，关闭以降低长视频内存；
                # gray 输出减少解码/转换数据量（标清宽 ROI 实测更快）
                gray_output=True,
                keep_crops=False,
                keep_frames=False,
                merge_similar=True,
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


class BatchExtractWorker(QThread):
    """批量导出 worker — 双引擎实例并发消费视频队列。

    两个消费者分别使用互补后端：
      - 主实例：用户选择的 decode_backend / ocr_backend
      - 副实例：自动取相反组合（CPU ↔ GPU/TRT）
    这样 5 视频队列可同时利用 CPU 与 GPU，缩短总墙钟。

    信号:
        progress(str, float)       — 总体进度消息 + 百分比 0-100
        video_done(int, int, int, str) — 已完成 (序号1基, 总数, 行数, 输出路径)
        finished(int, int, list)   — 全部结束 (成功数, 总数, 失败列表[str])
    """

    progress = Signal(str, float)
    video_done = Signal(int, int, int, str)
    finished = Signal(int, int, list)

    def __init__(self, videos: list, roi: tuple, start: int, end: int,
                 stride: int, postprocess: bool = True,
                 decode_backend: str = "auto", ocr_backend: str = "auto",
                 output_dir=None, combined_output=None, parent=None,
                 dual_workers: bool = True) -> None:
        super().__init__(parent)
        self.videos = list(videos)
        self.roi = roi
        self.start_frame = start
        self.end_frame = end
        self.stride = stride
        self.postprocess = postprocess
        self.decode_backend = decode_backend
        self.ocr_backend = ocr_backend
        self.output_dir = output_dir
        self.combined_output = Path(combined_output) if combined_output else None
        self.dual_workers = bool(dual_workers)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _check_cancel(self) -> None:
        if self._cancelled:
            raise _Cancelled()

    def _output_path(self, video: Path) -> Path:
        if self.output_dir:
            return Path(self.output_dir) / f"{video.stem}_subtitles.csv"
        return video.with_name(f"{video.stem}_subtitles.csv")

    def run(self) -> None:
        total = len(self.videos)
        ok = 0
        failures: list[str] = []
        combined_rows: list[tuple[str, int, str]] = []
        lock = threading.Lock()
        jq: "queue.Queue[tuple[int, Path, Path]]" = queue.Queue()
        for i, video in enumerate(self.videos, 1):
            out = self.combined_output or self._output_path(video)
            jq.put((i, video, out))

        def _progress_for(i: int, video: Path, m: str, p: float) -> None:
            overall = (i - 1) / total * 100 + p / total if total else p
            self.progress.emit(
                f"批量处理 {i}/{total}: {video.name} {m}", overall)

        def _process(job: tuple, dec: str, ocr: str) -> None:
            nonlocal ok
            i, video, out = job
            if self._cancelled:
                return
            self.progress.emit(
                f"批量处理 {i}/{total}: {video.name}（dec={dec}, ocr={ocr}）",
                (i - 1) / total * 100 if total else 0)
            try:
                # 引擎进度收敛为单调；并映射到批量总体区间
                # （第 i 个视频内 0-100 → 总体 [(i-1)/N, i/N]）
                def _progress(m: str, p: float) -> None:
                    _progress_for(i, video, m, p)

                gate = ProgressGate(_progress)
                ex = FieldExtractor(
                    str(video), self.roi,
                    frame_start=self.start_frame,
                    frame_end=None if (self.end_frame is None or self.end_frame <= 0) else self.end_frame,
                    sample_stride=self.stride,
                    decode_backend=dec,
                    ocr_backend=ocr,
                    progress_cb=gate,
                    cancel_check=self._check_cancel,
                    gray_output=True,
                    keep_crops=False,
                    keep_frames=False,
                    merge_similar=True,
                )
                result = ex.extract()
                rows = build_rows(result)
                if self.postprocess:
                    rows = postprocess_rows(rows)
                with lock:
                    if self.combined_output is not None:
                        combined_rows.extend(
                            (video.name, t, text) for t, text in rows)
                    else:
                        write_csv(out, rows)
                    ok += 1
                self.video_done.emit(i, total, len(rows), str(out))
            except _Cancelled:
                return
            except Exception as e:  # noqa: BLE001 — 单个失败继续处理下一个
                with lock:
                    failures.append(f"{video.name}: {e}")
                self.progress.emit(
                    f"批量处理 {i}/{total}: {video.name} 失败，继续下一个",
                    i / total * 100 if total else 0)

        def _consumer(dec: str, ocr: str) -> None:
            while not self._cancelled:
                try:
                    job = jq.get_nowait()
                except queue.Empty:
                    return
                try:
                    _process(job, dec, ocr)
                finally:
                    jq.task_done()

        pairs = [(self.decode_backend, self.ocr_backend)]
        if self.dual_workers:
            pairs.append(_opposite_backends(
                self.decode_backend, self.ocr_backend))
        threads = []
        for dec, ocr in pairs:
            t = threading.Thread(target=_consumer, args=(dec, ocr), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

        if self.combined_output is not None:
            try:
                write_combined_csv(self.combined_output, combined_rows)
            except Exception as e:  # noqa: BLE001
                failures.append(f"合并输出失败: {e}")
        self.finished.emit(ok, total, failures)
