"""导出 worker — 后台线程跑引擎 FieldExtractor + 写 CSV（保持 GUI 响应）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

# 引擎（video_ocr_engine）已 pip 化，直接从已安装包 import。

from video_ocr_engine import FieldExtractor  # noqa: E402
from subtitle_extract_cli import (  # noqa: E402
    ProgressGate, build_rows, postprocess_rows, write_combined_csv, write_csv,
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
                # 引擎 0.9 起：内部链恒为单通道（gray 收益已内置），
                # gray_output 参数已删除；rep_crop_format 只影响代表帧格式，
                # 本应用 keep_crops=False 用不到。hybrid+stride==1 的
                # DLPack 规避也不再需要（引擎 hybrid 内部已不依赖 DLPack）。
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
    """批量导出 worker — 顺序处理视频队列。

    应用级双引擎并行（--dual / GUI「双引擎并行」开关）已删除：双解码并行
    改由引擎内 hybrid 解码承担（decode_backend="hybrid"，单一实例内
    CPU+NVDEC 双解码生产者竞争；条件不满足时引擎自动回退）。

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
                 output_dir=None, combined_output=None, parent=None) -> None:
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

        def _progress_for(i: int, video: Path, m: str, p: float) -> None:
            overall = (i - 1) / total * 100 + p / total if total else p
            self.progress.emit(
                f"批量处理 {i}/{total}: {video.name} {m}", overall)

        for i, video in enumerate(self.videos, 1):
            out = self.combined_output or self._output_path(video)
            if self._cancelled:
                break
            self.progress.emit(
                f"批量处理 {i}/{total}: {video.name}（dec={self.decode_backend}, "
                f"ocr={self.ocr_backend}）",
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
                    decode_backend=self.decode_backend,
                    ocr_backend=self.ocr_backend,
                    progress_cb=gate,
                    cancel_check=self._check_cancel,
                    # 引擎 0.9 起 gray_output 已删（内部链恒单通道），
                    # hybrid 的 DLPack 规避也不再需要
                    keep_crops=False,
                    keep_frames=False,
                    merge_similar=True,
                )
                result = ex.extract()
                rows = build_rows(result)
                if self.postprocess:
                    rows = postprocess_rows(rows)
                if self.combined_output is not None:
                    combined_rows.extend(
                        (video.name, t, text) for t, text in rows)
                else:
                    write_csv(out, rows)
                ok += 1
                self.video_done.emit(i, total, len(rows), str(out))
            except _Cancelled:
                break
            except Exception as e:  # noqa: BLE001 — 单个失败继续处理下一个
                failures.append(f"{video.name}: {e}")
                self.progress.emit(
                    f"批量处理 {i}/{total}: {video.name} 失败，继续下一个",
                    i / total * 100 if total else 0)

        if self.combined_output is not None:
            try:
                write_combined_csv(self.combined_output, combined_rows)
            except Exception as e:  # noqa: BLE001
                failures.append(f"合并输出失败: {e}")
        self.finished.emit(ok, total, failures)
