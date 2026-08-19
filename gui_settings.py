"""GUI 左侧参数面板 + 设置页（对标 RaceVideoToLog 的 gui_settings 结构）。

- build_settings_panel(parent)：左侧参数卡片（识别范围帧 / 采样步长 / 输出 /
  后处理），返回 widget dict。主窗口把关键控件赋为自身属性
  （frame_start/frame_end/sample_stride/output_edit 等），兼容 gui_video 的既有引用。
- build_settings_page(parent)：设置页（主题 / 默认输出目录 / 导出后处理），
  改动即时写回 QConfig 持久化。
"""
from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QFileDialog
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CheckBox, ComboBox, CompactSpinBox, LineEdit,
    PushButton, StrongBodyLabel, setTheme, Theme, qconfig,
)

from app_config import app_config, save_app_config
from theme_manager import ThemeManager
from widget_utils import disable_spin_flyout, make_int_spinbox, make_static_card

# 绑定到 app_config.postProcess 的所有控件（左面板 + 设置页），任一变化时同步。
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


def _apply_theme(theme: Theme) -> None:
    setTheme(theme)          # 经 qfluentwidgets 内置 qconfig 持久化
    ThemeManager.refresh()   # 手动刷新需要回调的控件


def _save_out_dir(edit: LineEdit) -> None:
    app_config.outputDir.value = edit.text().strip()
    save_app_config()


def build_settings_panel(parent) -> dict:
    """构建左侧参数面板，返回 {控件名: widget} dict（主窗口需要保留引用）。"""
    widgets: dict = {}

    card = make_static_card(parent)
    gl = QGridLayout(card)
    gl.addWidget(StrongBodyLabel("识别范围（帧）"), 0, 0, 1, 4)

    start = CompactSpinBox()
    start.setRange(0, 1)
    disable_spin_flyout(start)
    end = CompactSpinBox()
    end.setRange(0, 1)
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

    out = LineEdit()
    out.setPlaceholderText("<视频名>_subtitles.csv")
    widgets["output_edit"] = out
    browse = PushButton("浏览…")
    widgets["_browse_btn"] = browse
    gl.addWidget(CaptionLabel("输出 CSV"), 5, 0)
    gl.addWidget(out, 5, 1, 1, 2)
    gl.addWidget(browse, 5, 3)
    gl.setColumnStretch(1, 1)

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
    pl.addWidget(CaptionLabel("CLI 与 GUI 导出同时生效；可在 设置 页关闭。"))

    ll = QVBoxLayout(parent)
    ll.setContentsMargins(0, 0, 0, 0)
    ll.setSpacing(6)
    ll.addWidget(card)
    ll.addWidget(pp_card)
    ll.addStretch()
    return widgets


def build_settings_page(parent) -> object:
    """设置页：主题 / 默认输出目录 / 导出后处理（QConfig 持久化）。"""
    from PySide6.QtWidgets import QWidget

    page = QWidget(parent)
    vl = QVBoxLayout(page)
    vl.setContentsMargins(0, 6, 0, 0)
    vl.setSpacing(8)

    # ── 界面 / 主题 ──
    ui_card = make_static_card(page)
    ul = QVBoxLayout(ui_card)
    ul.addWidget(StrongBodyLabel("界面"))
    row = QHBoxLayout()
    row.addWidget(BodyLabel("主题"))
    theme_combo = ComboBox()
    theme_combo.addItems(["浅色", "深色", "跟随系统"])
    _idx = {Theme.LIGHT: 0, Theme.DARK: 1, Theme.AUTO: 2}.get(
        qconfig.themeMode.value, 0)
    theme_combo.setCurrentIndex(_idx)
    theme_combo.currentIndexChanged.connect(
        lambda i: _apply_theme([Theme.LIGHT, Theme.DARK, Theme.AUTO][i]))
    row.addWidget(theme_combo, 1)
    ul.addLayout(row)
    ul.addWidget(CaptionLabel("跟随系统 = 自动跟随 Windows 深浅色。"))
    vl.addWidget(ui_card)

    # ── 导出 ──
    ex_card = make_static_card(page)
    el = QGridLayout(ex_card)
    el.addWidget(StrongBodyLabel("导出"), 0, 0, 1, 3)
    el.addWidget(BodyLabel("默认输出目录"), 1, 0)
    out_dir = LineEdit()
    out_dir.setText(str(app_config.outputDir.value))
    out_dir.setPlaceholderText("留空 = 视频所在目录")
    el.addWidget(out_dir, 1, 1)

    def _pick_dir() -> None:
        d = QFileDialog.getExistingDirectory(page, "选择默认输出目录",
                                             out_dir.text().strip())
        if d:
            out_dir.setText(d)

    pick = PushButton("选择…")
    pick.clicked.connect(_pick_dir)
    el.addWidget(pick, 1, 2)
    out_dir.editingFinished.connect(lambda: _save_out_dir(out_dir))

    el.addWidget(BodyLabel("导出后处理"), 2, 0)
    post = CheckBox("剔除重复行与纯数字行")
    post.setChecked(bool(app_config.postProcess.value))
    post.toggled.connect(lambda c, s=post: _postprocess_changed(c, sender=s))
    _postprocess_controls.append(post)
    el.addWidget(post, 2, 1, 1, 2)
    el.addWidget(CaptionLabel("默认开启；CLI 与 GUI 导出同时生效。"), 3, 1, 1, 2)
    vl.addWidget(ex_card)

    vl.addStretch()
    return page
