"""GUI 冒烟测试：offscreen 平台下构造主窗口，验证基本控件存在。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

import gui  # noqa: E402


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def test_gui_constructs_smoke(app):
    w = gui.SubtitleExtractorApp()
    try:
        assert "Subtitle" in w.windowTitle()
        # 核心控件
        assert hasattr(w, "_preview_widget")          # ROI 预览
        assert hasattr(w, "roi_x1") and hasattr(w, "roi_y2")
        assert hasattr(w, "frame_start") and hasattr(w, "frame_end")
        assert hasattr(w, "sample_stride")
        assert hasattr(w, "postprocess_check")        # 左参数面板后处理开关
        assert hasattr(w, "backend_combo")            # 解码后端（auto/CPU/NVDEC）
        assert hasattr(w, "ocr_backend_combo")        # OCR 后端（auto/CPU/TensorRT）
        assert w.backend_combo.count() == 3
        assert w.ocr_backend_combo.count() == 3
        assert not hasattr(w, "output_edit")          # 输出改为保存对话框，不再有输出框
        assert not hasattr(w, "_settings_tab")        # 设置 tab 已删除
        assert hasattr(w, "_tab_pivot")               # 两个 tab：单视频 / 批量
        assert hasattr(w, "_single_header") and hasattr(w, "_batch_header")
        assert hasattr(w, "_export_btn") and hasattr(w, "_progress_bar")
        assert hasattr(w, "_batch_btn")                # 批量导入按钮
        assert hasattr(w, "_batch_start_btn")          # 开始批量处理按钮
        assert not w._batch_start_btn.isEnabled()      # 初始禁用，导入文件夹后才启用
        assert hasattr(w, "merge_check")               # 批量“输出为单个文件”选项
        assert w._merge_card.isHidden()                # 初始在单视频 tab 隐藏
        w._tab_pivot.setCurrentItem("batch")
        app.processEvents()
        assert not w._merge_card.isHidden()            # 批量 tab 显示
        w._tab_pivot.setCurrentItem("single")
        app.processEvents()
        assert w._merge_card.isHidden()                # 切回单视频隐藏
    finally:
        w.close()


def test_gui_export_worker_imports(app):
    """导出 worker 可导入（引擎路径经 conftest/engine_bootstrap 提供）。"""
    from extract_worker import ExtractWorker
    assert ExtractWorker is not None


def test_export_worker_start_not_shadowed():
    """回归：ExtractWorker.__init__ 不能把 self.start 存成 int（会遮蔽
    QThread.start()，导致 GUI 导出报 'int' object is not callable）。"""
    from pathlib import Path
    from extract_worker import ExtractWorker
    w = ExtractWorker(Path("x.mp4"), (0, 0, 10, 10), 1, 100, 1,
                      Path("out.csv"), postprocess=True)
    assert callable(w.start)                 # 必须是 QThread.start 方法
    assert w.start_frame == 1 and w.end_frame == 100


def test_batch_worker_start_and_cancel_callable():
    """批量 worker：start/cancel 可调用，且不遮蔽 QThread.start。"""
    from pathlib import Path
    from extract_worker import BatchExtractWorker
    w = BatchExtractWorker([Path("a.mp4"), Path("b.mp4")], (0, 0, 10, 10),
                           0, 100, 1, postprocess=True,
                           combined_output=Path("merged.csv"))
    assert callable(w.start)
    assert callable(w.cancel)
    assert len(w.videos) == 2
    assert str(w.combined_output) == "merged.csv"
