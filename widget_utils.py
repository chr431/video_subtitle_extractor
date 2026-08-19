"""共享 GUI 组件与工具函数（移植自 RaceVideoToLog.widget_utils 的最小集）。"""
from __future__ import annotations

from qfluentwidgets import CardWidget, CompactSpinBox


def make_static_card(parent=None):
    """创建禁用 hover 高亮的 CardWidget。"""
    w = CardWidget(parent)
    w.enterEvent = lambda e: None
    w.leaveEvent = lambda e: None
    return w


def set_value_silent(spin, value) -> None:
    """设置 spinbox 值但不触发 valueChanged（ROI 联动赋值统一用法）。"""
    spin.blockSignals(True)
    spin.setValue(value)
    spin.blockSignals(False)


def disable_spin_flyout(spin) -> None:
    """禁用 CompactSpinBox 点击弹出的浮点输入面板。"""
    try:
        spin.compactSpinButton.clicked.disconnect()
    except Exception:
        pass
    spin._showFlyout = lambda: None


def make_int_spinbox(min_val: int, max_val: int, default: int, width: int = 90):
    """创建整数 CompactSpinBox：禁用浮点 flyout 面板。"""
    spin = CompactSpinBox()
    spin.setRange(min_val, max_val)
    spin.setValue(default)
    spin.setFixedWidth(width)
    disable_spin_flyout(spin)
    return spin
