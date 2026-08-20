"""GUI 左侧参数面板（对标 RaceVideoToLog 的 gui_settings 结构）。

- build_settings_panel(parent)：左侧参数卡片（识别范围帧 / 采样步长 / 后端 /
  导出后处理），返回 widget dict。主窗口把关键控件赋为自身属性
  （frame_start/frame_end/sample_stride/postprocess_check/backend_combo/
  ocr_backend_combo 等）。输出命名在导出时通过保存对话框完成（对标参考）。
"""
from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QVBoxLayout
from qfluentwidgets import (
    CaptionLabel, CheckBox, ComboBox, CompactSpinBox, PushButton,
    StrongBodyLabel,
)

from app_config import app_config, save_app_config
from widget_utils import disable_spin_flyout, make_int_spinbox, make_static_card

# 绑定到 app_config.postProcess 的所有控件，任一变化时同步（当前只有左面板一个）。
_postprocess_controls: list = []


def _postprocess_changed(checked: bool, sender=None) -> None:
    """同步所有后处理开关，并写回持久化配置。"""
    app_config.postProcess.value = bool(checked)
    save_app_config()
    for w in _postprocess_controls:
        if w is not sender:
            w.blockSignals(True)
            try:
                w.setChecked(bool(checked))
            finally:
                w.blockSignals(False)


def build_settings_panel(parent) -> dict:
    """构建左侧参数面板，返回 {控件名: widget} dict（主窗口需要保留引用）。"""
    widgets: dict = {}

    card = make_static_card(parent)
    gl = QGridLayout(card)
    gl.addWidget(StrongBodyLabel("识别范围（帧）"), 0, 0, 1, 4)

    start = CompactSpinBox()
    start.setRange(0, 1)
    start.setValue(0)
    disable_spin_flyout(start)
    end = CompactSpinBox()
    end.setRange(0, 1)
    end.setValue(1)          # 默认 0-1 合法范围；0 结束帧=到末尾由导出校验支持
    disable_spin_flyout(end)
    set_start = PushButton("设为首帧")
    set_start.setFixedSize(84, 30)
    set_end = PushButton("设为尾帧")
    set_end.setFixedSize(84, 30)
    widgets["frame_start"] = start
    widgets["frame_end"] = end
    widgets["_set_start_btn"] = set_start
    widgets["_set_end_btn"] = set_end

    gl.addWidget(CaptionLabel("开始帧"), 1, 0)
    gl.addWidget(start, 1, 1)
    gl.addWidget(set_start, 1, 2)
    gl.addWidget(CaptionLabel("结束帧"), 2, 0)
    gl.addWidget(end, 2, 1)
    gl.addWidget(set_end, 2, 2)
    gl.addWidget(CaptionLabel("默认全片；可用当前预览帧设为起/终点"), 3, 0, 1, 4)

    stride = make_int_spinbox(1, 30, 1, 90)
    widgets["sample_stride"] = stride
    gl.addWidget(CaptionLabel("采样步长"), 4, 0)
    gl.addWidget(stride, 4, 1)
    gl.addWidget(CaptionLabel("(1=逐帧；>1 分频)"), 4, 2, 1, 2)
    gl.addWidget(CaptionLabel("导出 CSV：点击「导出字幕 CSV」后在弹出窗口选择保存位置"), 5, 0, 1, 4)
    gl.setColumnStretch(1, 1)

    # ── 性能/后端 卡（对标参考：解码后端 auto/CPU/NVDEC + OCR 后端 auto/CPU/TensorRT）──
    perf_card = make_static_card(parent)
    plg = QGridLayout(perf_card)
    plg.addWidget(StrongBodyLabel("性能"), 0, 0, 1, 4)
    plg.addWidget(CaptionLabel("解码后端"), 1, 0)
    backend_combo = ComboBox()
    backend_combo.addItems(["自动", "CPU", "NVDEC"])
    backend_combo.setCurrentIndex(0)          # auto
    backend_combo.setFixedWidth(96)
    widgets["backend_combo"] = backend_combo
    plg.addWidget(backend_combo, 1, 1)
    plg.addWidget(CaptionLabel("OCR 后端"), 1, 2)
    ocr_backend_combo = ComboBox()
    ocr_backend_combo.addItems(["自动", "CPU", "TensorRT"])
    ocr_backend_combo.setCurrentIndex(1)      # 默认 CPU
    ocr_backend_combo.setFixedWidth(96)
    widgets["ocr_backend_combo"] = ocr_backend_combo
    plg.addWidget(ocr_backend_combo, 1, 3)

    # ── 后处理卡 ──
    pp_card = make_static_card(parent)
    pl = QVBoxLayout(pp_card)
    pl.addWidget(StrongBodyLabel("导出后处理"))
    post = CheckBox("剔除重复行与纯数字行")
    post.setChecked(bool(app_config.postProcess.value))
    post.toggled.connect(lambda c, s=post: _postprocess_changed(c, sender=s))
    _postprocess_controls.append(post)
    widgets["postprocess_check"] = post
    pl.addWidget(post)
    pl.addWidget(CaptionLabel("CLI 与 GUI 导出同时生效。"))

    ll = QVBoxLayout(parent)
    ll.setContentsMargins(0, 0, 0, 0)
    ll.setSpacing(6)
    ll.addWidget(card)
    ll.addWidget(perf_card)
    ll.addWidget(pp_card)
    ll.addStretch()
    return widgets
