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
        assert hasattr(w, "output_edit")
        assert hasattr(w, "_export_btn") and hasattr(w, "_progress_bar")
    finally:
        w.close()


def test_gui_export_worker_imports(app):
    """导出 worker 可导入（引擎路径经 conftest/engine_bootstrap 提供）。"""
    from extract_worker import ExtractWorker
    assert ExtractWorker is not None
