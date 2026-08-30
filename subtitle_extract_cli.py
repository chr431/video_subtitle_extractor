"""subtitle_extract_cli — 视频字幕提取 CLI（基于 video_ocr_engine 的独立场景应用）。

输入视频 + ROI + 可选帧范围 → 输出两列 CSV：
  time_sec — 识别帧（段代表帧）在视频中的实际时间戳，精确到秒（四舍五入）
  text     — OCR 原始文本（中文字符等，直接输出，不做任何处理）

本仓库是针对"视频字幕"场景的独立应用；通用引擎在 git submodule
third_party/video_ocr_engine（sys.path bootstrap 提供）。

用法:
    python subtitle_extract_cli.py <video> --roi X1 Y1 X2 Y2 \
        [--start-frame N] [--end-frame N] [--sample-stride N] [-o out.csv]
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import threading
from pathlib import Path

# 引擎（video_ocr_engine）已 pip 化，直接从已安装包 import。

from video_ocr_engine import ExtractionResult, FieldExtractor  # noqa: E402

PROG = "subtitle_extract_cli"

# 批量处理支持的视频扩展名（大小写不敏感）
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".m4v", ".wmv", ".flv",
    ".webm", ".ts", ".m2ts", ".mpg", ".mpeg",
}


def discover_videos(folder: Path) -> list[Path]:
    """扫描文件夹内的视频文件（顶层，按文件名排序，用于批量顺序处理）。"""
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)


class ProgressGate:
    """把并行阶段（解码∥OCR）的进度回调收敛成单调、不回退的进度。

    移植自 RaceVideoToLog/segment_flow.py。decode 与 OCR 真正并行：OCR
    可能已报到 58-86，而解码线程还在报 3-58。若直接透传，进度条会来回跳。
    本类只允许：
      - 百分比严格前进；或
      - 进入更靠后的阶段（decode→OCR）时即使百分比相同也切换。
    同一阶段内百分比相同的重复消息会被丢弃。
    """

    def __init__(self, emit) -> None:
        self._emit = emit
        self._lock = threading.Lock()
        self._last_pct = -1.0
        self._last_phase = -1

    @staticmethod
    def _phase(msg: str, pct: float) -> int:
        # 按消息内容判断阶段，避免 58.0 这种边界值被 pct 误判：
        # 解码最后一条也是 58.0，而 OCR 第一条也是 58.0。
        if msg == "检测纠正..." or msg == "完成":
            return 2
        if msg.startswith("[OCR]"):
            return 1
        return 0

    def __call__(self, msg: str, pct: float) -> None:
        phase = self._phase(msg, pct)
        with self._lock:
            if pct < self._last_pct:
                return
            if pct == self._last_pct and phase <= self._last_phase:
                return
            self._last_pct = pct
            self._last_phase = phase
        self._emit(msg, pct)


def _force_utf8_stdio() -> None:
    """Windows 控制台默认 GBK：把 stdout/stderr 改 UTF-8，防中文字符乱码。"""
    for _name in ("stdout", "stderr"):
        _s = getattr(sys, _name, None)
        if _s is not None and getattr(_s, "encoding", "utf-8") != "utf-8":
            try:
                setattr(sys, _name,
                        io.TextIOWrapper(_s.buffer, encoding="utf-8", errors="replace"))
            except (AttributeError, ValueError):
                pass


# ═══════════════════ CSV 转换（可单测） ═══════════════════

def _timestamp_sec(frame: int, fps: float) -> int:
    """绝对帧号 → 视频内实际秒数（精确到秒，四舍五入）。fps<=0 时兜底 0。"""
    if not fps or fps <= 0:
        return 0
    return int(round(frame / fps))


def build_rows(result: ExtractionResult) -> list[tuple[int, str]]:
    """ExtractionResult → [(time_sec, text), ...]。

    只保留 OCR 有文本的段；text 原样输出（不做 strip/过滤/解析）。
    时间戳取段代表帧（识别帧）的实际视频秒数。
    """
    fps = float(result.fps or 0.0)
    rows: list[tuple[int, str]] = []
    for seg in result.segments:
        if not seg.text:
            continue  # 未识别出文本的段不产出
        frame = seg.rep_frame if (seg.rep_frame is not None and seg.rep_frame >= 0) else seg.start
        rows.append((_timestamp_sec(frame, fps), seg.text))
    return rows


def postprocess_rows(rows: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """简单后处理：剔纯数字行 + 合并完全相同（连续相同文本）的结果。

    - 纯数字行：text 去掉首尾空白后仅由数字组成（含全角数字，如 OCR 把
      画面中的小数字误当成字幕提出来）。空文本/纯空白行也一并丢弃。
    - 相同结果合并：若某行 text 与前一条已保留行完全相同，则丢弃该行
      （保留首次出现的时间戳）。这会把同一句字幕在相邻多秒的重复输出
      合并为一条；若中途插入其他内容后再次出现相同字幕，则视为正常
      重复，予以保留。
    """
    out: list[tuple[int, str]] = []
    prev: str | None = None
    for time_sec, text in rows:
        if not text:
            continue
        stripped = text.strip()
        if not stripped:
            continue          # 纯空白
        if stripped.isdigit():
            continue          # 纯数字（含全角）
        if text == prev:
            continue          # 与前一条相同 → 合并（保留首次时间戳）
        out.append((time_sec, text))
        prev = text
    return out


def default_output_path(video: Path) -> Path:
    """默认输出：<视频目录>/<视频名>_subtitles.csv。"""
    return video.with_name(video.stem + "_subtitles.csv")


def format_timestamp(sec: int) -> str:
    """秒 → hh:mm:ss（如 0→'00:00'、65→'00:01:05'、3661→'01:01:01'）。

    统一三部分，Excel 不会再把 M:SS 误识别成时间（避免显示成 mm:ss:00），
    且兼容 >1 小时视频。
    """
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def write_csv(path: Path, rows: list[tuple[int, str]]) -> None:
    """写两列 CSV（utf-8-sig，Excel 友好；含逗号文本自动加引号）。

    第一列 time_hms 为 hh:mm:ss 格式（如 00:00:01 / 00:01:05）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(("time_hms", "text"))
        w.writerows((format_timestamp(t), text) for t, text in rows)


def write_combined_csv(path: Path, rows: list[tuple[str, int, str]]) -> None:
    """写批量合并 CSV（三列：视频文件名 / hh:mm:ss 时间 / 字幕文本）。

    rows: [(video_name, time_sec, text), ...]
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(("video", "time_hms", "text"))
        w.writerows((video, format_timestamp(t), text)
                    for video, t, text in rows)


def _extract_rows(video: Path, roi: tuple, start: int, end: int | None,
                  stride: int, decode_backend: str, ocr_backend: str,
                  postprocess: bool, merge_similar: bool,
                  progress_cb) -> list[tuple[int, str]]:
    """跑单个视频：解码+分段+OCR → 后处理后的 rows（不写文件）。

    decode_backend 支持 auto / cpu / nvdec / hybrid：hybrid 由引擎内
    HybridDecoder（CPU+NVDEC 双解码生产者竞争）承担，NVDEC 不可用或
    条件不满足时引擎自动回退纯 GPU/CPU。

    引擎 HybridDecoder 目前对 gray 单通道的 DLPack 设备指针路径有缺陷
    （_Batch 无 to_dlpack，校准 with_dev=True 时崩溃），因此 hybrid 候选
    （stride==1）暂用 RGB 输出；分段/OCR 内部仍转灰度，结果与 gray 一致。
    """
    ex = FieldExtractor(
        str(video), roi,
        frame_start=start,
        frame_end=end,
        sample_stride=stride,
        decode_backend=decode_backend,
        ocr_backend=ocr_backend,
        progress_cb=progress_cb,
        # 引擎 0.9 起：内部链恒为单通道，gray_output 参数已删除；
        # hybrid 的 DLPack 规避也不再需要（引擎内部不依赖 DLPack）
        keep_crops=False,
        keep_frames=False,
        merge_similar=merge_similar,
    )
    result = ex.extract()
    rows = build_rows(result)
    if postprocess:
        rows = postprocess_rows(rows)
    return rows


# ═══════════════════ CLI ═══════════════════

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog=PROG,
        description="视频字幕提取：基于 video_ocr_engine，视频 ROI → 时间戳+OCR 文本 CSV。")
    p.add_argument("video", nargs="?", help="视频输入文件（单视频模式）")
    p.add_argument("--batch-dir", dest="batch_dir", default=None,
                   help="批量处理文件夹（与 video 二选一）")
    p.add_argument("--combined", action="store_true", default=False,
                   help="批量模式输出为单个合并 CSV（需配合 -o/--output 指定路径，否则输出到批量目录）")
    p.add_argument("--output-dir", dest="output_dir", default=None,
                   help="批量模式单个 CSV 的输出目录（默认输出到各视频所在目录）")
    p.add_argument("--roi", nargs=4, type=int, required=True,
                   metavar=("X1", "Y1", "X2", "Y2"),
                   help="识别区域（字幕/文本条） (x1 y1 x2 y2)")
    p.add_argument("--start-frame", dest="start_frame", type=int, default=0,
                   help="开始帧号（默认 0）")
    p.add_argument("--end-frame", dest="end_frame", type=int, default=None,
                   help="结束帧号（默认到视频末尾；0 视为末尾）")
    p.add_argument("--sample-stride", dest="sample_stride", type=int, default=1,
                   help="分频采样步长（默认 1=逐帧；>1 时只处理每个第 N 帧，"
                        "适合字幕等慢更新内容降低解码/处理压力；需 decord ≥0.7.12）")
    p.add_argument("--decode-backend", dest="decode_backend", default="auto",
                   choices=["auto", "cpu", "nvdec", "hybrid"],
                   help="视频解码后端（默认 auto=NVDEC 优先，不可用回退 CPU；"
                        "cpu=强制 CPU 软解，nvdec=强制 NVDEC，"
                        "hybrid=CPU+NVDEC 混合解码（引擎内 HybridDecoder，"
                        "NVDEC 不可用/条件不满足时自动回退）")
    p.add_argument("--ocr-backend", dest="ocr_backend", default="auto",
                   choices=["auto", "cpu", "tensorrt"],
                   help="OCR 后端（默认 auto=有 TRT 用 TRT，无则回退 ONNX）")
    p.add_argument("--no-postprocess", dest="postprocess", action="store_false", default=True,
                   help="关闭后处理（默认开启：剔除重复行与纯数字行）")
    p.add_argument("--no-merge-similar", dest="merge_similar", action="store_false", default=True,
                   help="关闭相似段合并（默认开启：噪声把同一条字幕切成多段时只 OCR 一次）")
    p.add_argument("-o", "--output", default=None,
                   help="输出 CSV 路径（默认 <视频名>_subtitles.csv）")
    return p.parse_args(argv)


_progress_lock = threading.Lock()


def _progress(msg: str, pct: float) -> None:
    with _progress_lock:
        sys.stderr.write(f"\r[{pct:5.1f}%] {msg}")
        sys.stderr.flush()
        if pct >= 100.0:
            sys.stderr.write("\n")


def _run_batch(args, end: int | None) -> int:
    """CLI 批量模式：与 GUI 批量功能对齐（除视觉预览外）。"""
    folder = Path(args.batch_dir)
    if not folder.is_dir():
        print(f"错误: 找不到批量目录 {folder}", file=sys.stderr)
        return 2
    videos = discover_videos(folder)
    if not videos:
        print(f"错误: 批量目录中没有找到视频: {folder}", file=sys.stderr)
        return 2
    total = len(videos)
    if args.combined and args.output_dir:
        print("错误: --combined 与 --output-dir 不能同时使用", file=sys.stderr)
        return 2
    if not args.combined and args.output:
        print("错误: 非 --combined 模式请使用 --output-dir（或省略以输出到视频目录）",
              file=sys.stderr)
        return 2

    combined_path = None
    if args.combined:
        combined_path = Path(args.output) if args.output else folder / "合并字幕.csv"

    combined_rows: list[tuple[str, int, str]] = []
    failures: list[str] = []
    ok = 0

    def _make_progress(i: int, video: Path):
        def cb(m: str, p: float) -> None:
            overall = (i - 1) / total * 100 + p / total if total else p
            _progress(f"[{i}/{total}] {video.name} {m}", overall)
        return ProgressGate(cb)

    # 应用级双引擎并行（--dual）已删除：双解码并行改由引擎内 hybrid
    # 解码（decode_backend="hybrid"，CPU+NVDEC 双生产者竞争）承担。
    for i, video in enumerate(videos, 1):
        try:
            rows = _extract_rows(
                video, tuple(args.roi), args.start_frame, end,
                args.sample_stride, args.decode_backend, args.ocr_backend,
                args.postprocess, args.merge_similar,
                _make_progress(i, video))
            if combined_path is not None:
                combined_rows.extend(
                    (video.name, t, text) for t, text in rows)
            else:
                if args.output_dir:
                    out = Path(args.output_dir) / f"{video.stem}_subtitles.csv"
                else:
                    out = video.with_name(f"{video.stem}_subtitles.csv")
                write_csv(out, rows)
            ok += 1
            print(f"完成 {i}/{total}: {video.name} -> {len(rows)} 条", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{video.name}: {e}")
            print(f"失败 {i}/{total}: {video.name}: {e}", file=sys.stderr)

    if combined_path is not None:
        try:
            write_combined_csv(combined_path, combined_rows)
            print(f"完成: 合并输出 -> {combined_path}（{len(combined_rows)} 行）",
                  file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            failures.append(f"合并输出失败: {e}")

    print(f"批量完成: 成功 {ok}/{total}，失败 {len(failures)}", file=sys.stderr)
    for f in failures:
        print(f"  - {f}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    args = parse_args(argv)

    if (args.video is None) == (args.batch_dir is None):
        print("错误: 必须且只能提供 video 或 --batch-dir 之一", file=sys.stderr)
        return 2

    if args.start_frame < 0:
        print("错误: --start-frame 不能为负数", file=sys.stderr)
        return 2
    if args.sample_stride < 1:
        print("错误: --sample-stride 必须 >= 1", file=sys.stderr)
        return 2
    end = None if (args.end_frame is None or args.end_frame <= 0) else args.end_frame
    if end is not None and end <= args.start_frame:
        print("错误: --end-frame 必须大于 --start-frame", file=sys.stderr)
        return 2

    if args.batch_dir:
        return _run_batch(args, end)

    # ── 单视频模式 ──
    video = Path(args.video)
    if not video.is_file():
        print(f"错误: 找不到视频文件 {video}", file=sys.stderr)
        return 2
    if args.combined or args.output_dir:
        print("错误: --combined / --output-dir 仅批量模式有效", file=sys.stderr)
        return 2

    out = Path(args.output) if args.output else default_output_path(video)
    rows = _extract_rows(
        video, tuple(args.roi), args.start_frame, end,
        args.sample_stride, args.decode_backend, args.ocr_backend,
        args.postprocess, args.merge_similar,
        ProgressGate(_progress))
    print(f"完成: {video.name} -> {len(rows)} 条文本", file=sys.stderr)
    print(f"输出: {out}")
    write_csv(out, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
