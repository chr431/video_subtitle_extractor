"""视频预览控件 — 帧显示 + ROI 拖拽选择 + 缩放重绘。

移植自 RaceVideoToLog 的 gui_preview.py PreviewWidget（qfluentwidgets 风格），
坐标换算/拖拽状态/节流重绘/ROI 框绘制全部内聚于此；主窗口只负责提供帧数据
与接收 ROI 变化。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QVBoxLayout, QWidget

from qfluentwidgets import BodyLabel

# 预览配色（原 config.PREVIEW_BG / ROI_BOX_COLOR / CANVAS_FILL，内联于此避免引入应用 config）
PREVIEW_BG = "#111111"
ROI_BOX_COLOR = "#ff5050"
CANVAS_FILL = "#151515"


class PreviewWidget(QWidget):
    """视频预览：显示帧图像，支持鼠标拖拽框选 ROI。

    信号:
        roi_dragged(int, int, int, int) — 拖拽更新 ROI（x1, y1, x2, y2），
            由主窗口同步到 spinbox。
    """

    roi_dragged = Signal(int, int, int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = BodyLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(400, 300)
        self._label.setStyleSheet(f"background-color: {PREVIEW_BG}; border-radius: 6px;")
        self._label.setMouseTracking(True)
        self._label.setCursor(Qt.CursorShape.CrossCursor)
        self._label.mousePressEvent = self._on_press     # type: ignore[method-assign]
        self._label.mouseMoveEvent = self._on_move       # type: ignore[method-assign]
        self._label.mouseReleaseEvent = self._on_release  # type: ignore[method-assign]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label, 1)

        self._pm: QPixmap | None = None          # 当前帧
        self._roi: tuple | None = None           # (x1, y1, x2, y2) 视频坐标
        self._video_w: int = 0
        self._video_h: int = 0
        self._drag_active: bool = False
        self._drag_start: tuple = (0, 0)
        self._scale: float = 0.0                 # 显示缩放
        self._ox: float = 0.0                    # 图像偏移（居中）
        self._oy: float = 0.0
        self._redraw_timer: QTimer | None = None

    # ═══════════════════ 外部接口 ═══════════════════

    def set_frame(self, pm: QPixmap | None) -> None:
        """设置当前显示帧（None 时保留旧帧）。"""
        if pm is not None:
            self._pm = pm
            self._redraw()

    def set_video_size(self, width: int, height: int) -> None:
        """记录视频尺寸（坐标换算与 ROI 越界裁剪用）。"""
        self._video_w, self._video_h = width, height

    def set_roi(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """外部（spinbox）更新 ROI 并重绘。"""
        self._roi = (x1, y1, x2, y2)
        self._redraw()

    # ═══════════════════ 鼠标交互 ═══════════════════

    def _on_press(self, event) -> None:
        if self._video_w <= 0 or self._pm is None:
            return
        x, y = self._to_video(event.position().x(), event.position().y())
        self._drag_active = True
        self._drag_start = (x, y)
        self._emit_roi(x, y, x, y)

    def _on_move(self, event) -> None:
        if not self._drag_active or self._video_w <= 0:
            return
        x, y = self._to_video(event.position().x(), event.position().y())
        x1, y1 = self._drag_start
        self._emit_roi(min(x1, x), min(y1, y), max(x1, x), max(y1, y))

    def _on_release(self, event) -> None:
        self._drag_active = False

    def _emit_roi(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self._roi = (x1, y1, x2, y2)
        self._schedule_redraw()
        self.roi_dragged.emit(x1, y1, x2, y2)

    # ═══════════════════ 绘制 ═══════════════════

    def _to_video(self, wx: float, wy: float) -> tuple[int, int]:
        if self._scale <= 0:
            return 0, 0
        x = (wx - self._ox) / self._scale
        y = (wy - self._oy) / self._scale
        return (max(0, min(self._video_w - 1, int(x))),
                max(0, min(self._video_h - 1, int(y))))

    def _schedule_redraw(self) -> None:
        """节流重绘：16ms 单次定时器，避免拖拽时过度绘制。"""
        if self._redraw_timer is not None:
            return
        self._redraw_timer = QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.timeout.connect(self._do_throttled_redraw)
        self._redraw_timer.start(16)

    def _do_throttled_redraw(self) -> None:
        self._redraw_timer = None
        self._redraw()

    def _redraw(self) -> None:
        if self._pm is None:
            return
        ls = self._label.size()
        pw, ph = ls.width(), ls.height()
        if pw <= 0 or ph <= 0:
            return

        pm = self._pm
        scale = min(pw / pm.width(), ph / pm.height())
        dw = max(1, int(pm.width() * scale))
        dh = max(1, int(pm.height() * scale))
        scaled = pm.scaled(dw, dh, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        self._scale = scale
        self._ox = (pw - dw) / 2.0
        self._oy = (ph - dh) / 2.0

        if self._roi is not None:
            painter = QPainter(scaled)
            x1, y1, x2, y2 = self._roi
            l, t = int(x1 * scale), int(y1 * scale)
            r, b = int(x2 * scale), int(y2 * scale)
            painter.setPen(QPen(QColor(ROI_BOX_COLOR), max(2, int(scale * 2))))
            painter.drawRect(l, t, r - l, b - t)
            painter.end()

        result = QPixmap(pw, ph)
        result.fill(QColor(CANVAS_FILL))
        rp = QPainter(result)
        rp.drawPixmap(int(self._ox), int(self._oy), scaled)
        rp.end()
        self._label.setPixmap(result)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._redraw()
