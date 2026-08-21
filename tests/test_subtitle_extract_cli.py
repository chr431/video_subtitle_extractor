"""subtitle_extract_cli 单元测试（无需视频/decord/GPU/OCR）：CSV 行构建、时间戳、写文件、参数解析。"""
from __future__ import annotations

import csv
from pathlib import Path

import subtitle_extract_cli as m
from video_ocr_engine import ExtractedSegment, ExtractionResult


def _result(fps: float) -> ExtractionResult:
    r = ExtractionResult(fps=fps)
    r.segments = [
        ExtractedSegment(start=0, end=0, rep_frame=0, text="你好"),
        ExtractedSegment(start=30, end=30, rep_frame=30, text=None),    # 无文本 → 跳过
        ExtractedSegment(start=45, end=45, rep_frame=45, text=""),       # 空串  → 跳过
        ExtractedSegment(start=60, end=60, rep_frame=60, text="世界"),
    ]
    return r


def test_build_rows_maps_timestamp_and_skips_empty():
    rows = m.build_rows(_result(fps=30.0))
    # 0/30=0 → 0s；30/30=1 → 1s（但 None 跳过）；45 跳过；60/30=2 → 2s
    assert rows == [(0, "你好"), (2, "世界")]


def test_build_rows_text_kept_verbatim():
    r = ExtractionResult(fps=10.0)
    r.segments = [
        ExtractedSegment(start=10, end=10, rep_frame=10, text=" 带 空格 "),
        ExtractedSegment(start=20, end=20, rep_frame=20, text="含,逗号"),
    ]
    rows = m.build_rows(r)
    assert rows[0] == (1, " 带 空格 ")          # 原样，不 strip
    assert rows[1][1] == "含,逗号"              # 逗号交给 csv 引号处理


def test_timestamp_rounding():
    r = ExtractionResult(fps=30.0)
    r.segments = [
        ExtractedSegment(start=0, end=0, rep_frame=44, text="a"),  # 44/30≈1.47 → 1
        ExtractedSegment(start=0, end=0, rep_frame=45, text="b"),  # 45/30=1.5  → 2
    ]
    assert [t for t, _ in m.build_rows(r)] == [1, 2]


def test_timestamp_zero_when_fps_unknown():
    r = ExtractionResult(fps=0.0)
    r.segments = [ExtractedSegment(start=0, end=0, rep_frame=100, text="x")]
    assert m.build_rows(r) == [(0, "x")]


def test_write_csv_header_and_quoting(tmp_path):
    out = tmp_path / "sub" / "out.csv"   # 目录不存在也应创建
    m.write_csv(out, [(1, "你好，世界"), (2, "a,b")])
    with open(out, encoding="utf-8-sig", newline="") as f:
        data = list(csv.reader(f))
    assert data[0] == ["time_hms", "text"]
    assert data[1] == ["00:00:01", "你好，世界"]
    assert data[2] == ["00:00:02", "a,b"]       # 含逗号文本被 csv 引号包裹，读回仍为单值


def test_format_timestamp_hms():
    assert m.format_timestamp(0) == "00:00:00"
    assert m.format_timestamp(1) == "00:00:01"
    assert m.format_timestamp(65) == "00:01:05"
    assert m.format_timestamp(379) == "00:06:19"
    assert m.format_timestamp(3600) == "01:00:00"
    assert m.format_timestamp(3661) == "01:01:01"
    assert m.format_timestamp(-3) == "00:00:00"


def test_write_combined_csv(tmp_path):
    """批量合并 CSV：三列 video / time_hms / text。"""
    out = tmp_path / "combined.csv"
    m.write_combined_csv(out, [("a.mp4", 1, "你好"), ("b.MKV", 65, "世界")])
    with open(out, encoding="utf-8-sig", newline="") as f:
        data = list(csv.reader(f))
    assert data[0] == ["video", "time_hms", "text"]
    assert data[1] == ["a.mp4", "00:00:01", "你好"]
    assert data[2] == ["b.MKV", "00:01:05", "世界"]


def test_progress_gate_is_monotonic():
    """ProgressGate：百分比只进不退，允许同百分比切到更靠后阶段，丢弃重复。"""
    out: list = []
    gate = m.ProgressGate(lambda msg, pct: out.append((msg, pct)))
    gate("解码 1", 3)
    gate("解码 2", 58)
    gate("[OCR] 1", 20)      # 20 < 58 → 丢弃
    gate("[OCR] 2", 58)      # 同 pct 但 phase 1 > 0 → 允许
    gate("[OCR] 3", 58)      # 同 pct 同 phase → 丢弃
    gate("[OCR] 4", 86)
    gate("解码 3", 40)       # 40 < 86 → 丢弃
    gate("完成", 100)
    assert out == [("解码 1", 3), ("解码 2", 58), ("[OCR] 2", 58),
                   ("[OCR] 4", 86), ("完成", 100)]


def test_default_output_path():
    assert m.default_output_path(Path("D:/x/abc.mp4")) == Path("D:/x/abc_subtitles.csv")


def test_parse_args_defaults_and_override():
    a = m.parse_args(["v.mp4", "--roi", "1", "2", "3", "4"])
    assert a.roi == [1, 2, 3, 4]
    assert a.start_frame == 0
    assert a.end_frame is None
    assert a.output is None
    assert a.sample_stride == 1

    b = m.parse_args(["v.mp4", "--roi", "1", "2", "3", "4",
                      "--start-frame", "100", "--end-frame", "200",
                      "--sample-stride", "3", "-o", "x.csv"])
    assert (b.start_frame, b.end_frame, b.sample_stride, b.output) == (100, 200, 3, "x.csv")


def test_main_missing_video_returns_2(capsys):
    code = m.main(["does_not_exist.mp4", "--roi", "1", "2", "3", "4"])
    assert code == 2


def test_postprocess_removes_duplicates_and_numeric():
    """后处理：剔纯数字行（含全角）+ 合并连续相同文本，保留首次时间戳。"""
    rows = [
        (1, "你好"),
        (1, "你好"),        # 与上一条相同 → 合并（同一句在相邻秒的重复）
        (2, "1"),           # 纯 ASCII 数字 → 剔除
        (3, "１２３"),       # 全角数字 → isdigit 为真 → 剔除
        (4, " "),           # 纯空白 → 剔除
        (5, "你好"),        # 上一条保留文本仍为“你好” → 合并剔除
        (6, "a123"),        # 非纯数字 → 保留
        (6, "a123"),        # 连续相同 → 合并
        (7, ""),            # 空串 → 剔除
    ]
    assert m.postprocess_rows(rows) == [(1, "你好"), (6, "a123")]


def test_postprocess_merges_consecutive_but_keeps_repeat_after_gap():
    """连续相同文本合并成一条（保留首次时间戳）；隔开再出现视为正常重复，保留。"""
    rows = [
        (10, "我们继续"),
        (11, "我们继续"),   # 连续相同 → 合并
        (11, "我们继续"),   # 连续相同 → 合并
        (12, "换了一句话"),
        (13, "我们继续"),   # 中间隔了别的文本 → 保留
    ]
    assert m.postprocess_rows(rows) == [
        (10, "我们继续"), (12, "换了一句话"), (13, "我们继续")]


def test_parse_args_default_postprocess_on():
    """默认开启后处理；--no-postprocess 可关闭。"""
    a = m.parse_args(["v.mp4", "--roi", "1", "2", "3", "4"])
    assert a.postprocess is True
    b = m.parse_args(["v.mp4", "--roi", "1", "2", "3", "4", "--no-postprocess"])
    assert b.postprocess is False


def test_parse_args_backend_defaults_and_override():
    """默认 decode=cpu / ocr=auto；可分别覆盖为 nvdec / tensorrt。"""
    a = m.parse_args(["v.mp4", "--roi", "1", "2", "3", "4"])
    assert a.decode_backend == "cpu"
    assert a.ocr_backend == "auto"
    b = m.parse_args(["v.mp4", "--roi", "1", "2", "3", "4",
                      "--decode-backend", "nvdec", "--ocr-backend", "tensorrt"])
    assert (b.decode_backend, b.ocr_backend) == ("nvdec", "tensorrt")


def test_discover_videos_sorted_and_extension_case_insensitive(tmp_path):
    """批量处理：只收集视频文件，按文件名排序，扩展名大小写不敏感。"""
    (tmp_path / "b.MKV").write_bytes(b"x")
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "c.mov").write_bytes(b"x")
    (tmp_path / "d.txt").write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "e.mp4").write_bytes(b"x")  # 子目录不扫描（顶层）
    found = m.discover_videos(tmp_path)
    assert [p.name for p in found] == ["a.mp4", "b.MKV", "c.mov"]
    assert m.discover_videos(tmp_path / "missing") == []
