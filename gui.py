"""Video Subtitle Extractor — PySide6 + qfluentwidgets GUI 主窗口。

基础流程：导入视频 → 设置识别范围（预览拖拽 ROI）与帧范围 → 导出字幕 CSV。
识别链复用通用引擎（chr431/video_ocr_engine submodule），后台线程跑
FieldExtractor；CSV 两列：秒级时间戳 + 原始 OCR 文本。

入口：
    python gui.py            # 或 pip 安装后: subtitle-extract-gui
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CompactSpinBox, LineEdit, PrimaryPushButton,
    ProgressBar, PushButton, Slider, StrongBodyLabel,
)

from extract_worker import ExtractWorker
from gui_video import VideoLoadMixin
from preview_widget import PreviewWidget
from widget_utils import disable_spin_flyout, make_static_card, set_value_silent


class SubtitleExtractorApp(VideoLoadMixin, QMainWindow):
    """视频字幕提取主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Video Subtitle Extractor")
        self.resize(1240, 820)
        self.setMinimumSize(1040, 700)

        # ── 状态变量 ──
        self.video_path: Path | None = None
        self.metadata: object | None = None
        self.first_frame_qimg: QImage | None = None
        self._preview_vr = None  # decord VideoReader
        self._preview_frame_no: int = 0
        self._throttle_timer = QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.timeout.connect(self._show_throttled_frame)
        self._worker: ExtractWorker | None = None

        self._build_ui()
        self._connect_signals()
        self._add_shortcuts()

    # ═══════════════════ 构建 UI ═══════════════════

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 8, 12, 6)
        root.setSpacing(8)

        # ── 顶栏 ──
        hdr = QHBoxLayout()
        self._import_video_btn = PushButton("导入视频")
        hdr.addWidget(self._import_video_btn)
        self._file_label = BodyLabel("未导入视频")
        self._file_label.setWordWrap(True)
        hdr.addWidget(self._file_label, 1)
        self._export_btn = PrimaryPushButton("导出字幕 CSV")
        hdr.addWidget(self._export_btn)
        self._cancel_btn = PushButton("取消")
        self._cancel_btn.setEnabled(False)
        hdr.addWidget(self._cancel_btn)
        root.addLayout(hdr)

        # ── 视频信息 ──
        info = make_static_card()
        il = QHBoxLayout(info)
        self._dur_label = BodyLabel("-")
        self._res_label = BodyLabel("-")
        self._fps_label = BodyLabel("-")
        self._codec_label = BodyLabel("-")
        for t, l in [("时长", self._dur_label), ("分辨率", self._res_label),
                     ("帧率", self._fps_label), ("编码", self._codec_label)]:
            w = QWidget()
            wl = QVBoxLayout(w)
            wl.setContentsMargins(8, 4, 8, 4)
            wl.addWidget(CaptionLabel(t))
            wl.addWidget(l)
            il.addWidget(w)
        il.addStretch()
        root.addWidget(info)

        # ── 主内容：左参数 / 右预览 ──
        main_w = QHBoxLayout()
        main_w.setSpacing(12)
        left = self._build_left_panel()
        main_w.addWidget(left)
        right = QVBoxLayout()
        right.setSpacing(8)
        self._build_right_panel(right)
        main_w.addLayout(right, 1)
        root.addLayout(main_w, 1)

        # ── 底部状态 ──
        self._status_label = BodyLabel("请导入视频并设置识别范围。")
        self._progress_bar = ProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        root.addWidget(self._status_label)
        root.addWidget(self._progress_bar)

    def _build_left_panel(self) -> QWidget:
        left = QWidget()
        left.setFixedWidth(360)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(8)

        # ── 帧范围 + 采样 ──
        range_card = make_static_card()
        rgl = QGridLayout(range_card)
        rgl.addWidget(StrongBodyLabel("识别范围（帧）"), 0, 0, 1, 4)
        self.frame_start = CompactSpinBox()
        self.frame_end = CompactSpinBox()
        for s in (self.frame_start, self.frame_end):
            s.setRange(0, 1)
        self._set_start_btn = PushButton("设为首帧")
        self._set_end_btn = PushButton("设为尾帧")
        self._set_start_btn.setFixedSize(72, 30)
        self._set_end_btn.setFixedSize(72, 30)
        rgl.addWidget(CaptionLabel("开始帧"), 1, 0)
        rgl.addWidget(self.frame_start, 1, 1)
        rgl.addWidget(self._set_start_btn, 1, 2)
        rgl.addWidget(CaptionLabel("结束帧"), 2, 0)
        rgl.addWidget(self.frame_end, 2, 1)
        rgl.addWidget(self._set_end_btn, 2, 2)
        self.sample_stride = CompactSpinBox()
        self.sample_stride.setRange(1, 30)
        self.sample_stride.setValue(1)
        rgl.addWidget(CaptionLabel("采样步长"), 3, 0)
        rgl.addWidget(self.sample_stride, 3, 1)
        rgl.addWidget(CaptionLabel("(1=逐帧；>1 分频)"), 3, 2, 1, 2)
        ll.addWidget(range_card)

        # ── 输出 ──
        out_card = make_static_card()
        ol = QGridLayout(out_card)
        ol.addWidget(StrongBodyLabel("导出"), 0, 0, 1, 3)
        self.output_edit = LineEdit()
        self.output_edit.setPlaceholderText("<视频名>_subtitles.csv")
        ol.addWidget(self.output_edit, 1, 0, 1, 2)
        self._browse_btn = PushButton("浏览…")
        ol.addWidget(self._browse_btn, 1, 2)
        ll.addWidget(out_card)
        ll.addStretch()
        return left

    def _build_right_panel(self, rl: QVBoxLayout) -> None:
        # ── ROI ──
        roi_card = make_static_card()
        rgl = QGridLayout(roi_card)
        rgl.addWidget(StrongBodyLabel("识别范围（像素）"), 0, 0, 1, 4)
        self.roi_x1 = CompactSpinBox()
        self.roi_y1 = CompactSpinBox()
        self.roi_x2 = CompactSpinBox()
        self.roi_y2 = CompactSpinBox()
        for s in (self.roi_x1, self.roi_y1, self.roi_x2, self.roi_y2):
            s.setRange(0, 9999)
            s.setFixedWidth(90)
            # 默认一个居中小框（视频载入后按尺寸截断上限）
        self.roi_x1.setValue(0)
        self.roi_y1.setValue(0)
        self.roi_x2.setValue(100)
        self.roi_y2.setValue(40)
        for s in (self.roi_x1, self.roi_y1, self.roi_x2, self.roi_y2):
            s.valueChanged.connect(lambda v, spin=s: self._on_roi_spin(spin))
            disable_spin_flyout(s)
        rgl.addWidget(CaptionLabel("左上 X"), 1, 0)
        rgl.addWidget(self.roi_x1, 1, 1)
        rgl.addWidget(CaptionLabel("左上 Y"), 1, 2)
        rgl.addWidget(self.roi_y1, 1, 3)
        rgl.addWidget(CaptionLabel("右下 X"), 2, 0)
        rgl.addWidget(self.roi_x2, 2, 1)
        rgl.addWidget(CaptionLabel("右下 Y"), 2, 2)
        rgl.addWidget(self.roi_y2, 2, 3)
        rgl.addWidget(CaptionLabel("← 在预览画面上拖拽选择识别范围"), 3, 0, 1, 4)
        rl.addWidget(roi_card)

        # ── 预览 ──
        pv = make_static_card()
        pvl = QVBoxLayout(pv)
        pvl.addWidget(StrongBodyLabel("帧预览"))
        self._preview_widget = PreviewWidget()
        self._preview_widget.roi_dragged.connect(self._on_preview_roi)
        pvl.addWidget(self._preview_widget, 1)
        sr = QHBoxLayout()
        self._slider = Slider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 1)
        self._slider.setValue(0)
        self._slider.valueChanged.connect(self._on_slider)
        sr.addWidget(self._slider, 1)
        self._frame_label = CaptionLabel("#0")
        self._frame_label.setFixedWidth(70)
        sr.addWidget(self._frame_label)
        pvl.addLayout(sr)
        rl.addWidget(pv, 1)

    # ═══════════════════ 信号 + 快捷键 ═══════════════════

    def _connect_signals(self) -> None:
        self._import_video_btn.clicked.connect(self._import_video)
        self._export_btn.clicked.connect(self._export_csv)
        self._cancel_btn.clicked.connect(self._cancel_export)
        self._set_start_btn.clicked.connect(lambda: set_value_silent(self.frame_start, self._slider.value()))
        self._set_end_btn.clicked.connect(lambda: set_value_silent(self.frame_end, self._slider.value()))
        self._browse_btn.clicked.connect(self._pick_output)

    def _add_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self._step(-1))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self._step(1))
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, lambda: self._step(10))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, lambda: self._step(-10))

    def _pick_output(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "导出字幕 CSV", str(self.video_path.with_name("subtitles.csv"))
            if self.video_path else "subtitles.csv", "CSV 文件 (*.csv);;所有文件 (*.*)")
        if path:
            self.output_edit.setText(path)

    # ═══════════════════ 导出 ═══════════════════

    def _export_csv(self) -> None:
        if self.metadata is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "请先导入视频。")
            return
        if self._worker is not None and self._worker.isRunning():
            return
        x1, y1, x2, y2 = (s.value() for s in (self.roi_x1, self.roi_y1,
                                               self.roi_x2, self.roi_y2))
        if x2 <= x1 or y2 <= y1:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "识别范围无效：右下必须大于左上（像素）。")
            return
        if self.frame_end.value() <= self.frame_start.value():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "帧范围无效：结束帧必须大于开始帧。")
            return
        out_text = self.output_edit.text().strip()
        if not out_text:
            out_text = str(self.video_path.with_name("subtitles.csv"))
        out = Path(out_text)
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "输出路径无效", str(e))
            return

        self._export_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress_bar.setValue(0)
        self._status_label.setText("正在识别…（解码 + 分段 + OCR）")
        worker = ExtractWorker(
            self.video_path, (x1, y1, x2, y2),
            self.frame_start.value(), self.frame_end.value(),
            self.sample_stride.value(), out)
        worker.progress.connect(self._on_export_progress)
        worker.succeeded.connect(self._on_export_done)
        worker.failed.connect(self._on_export_failed)
        self._worker = worker
        worker.start()

    def _on_export_progress(self, msg: str, pct: float) -> None:
        self._status_label.setText(msg)
        self._progress_bar.setValue(int(round(max(0.0, min(100.0, pct)))))

    def _on_export_done(self, rows: int, out: str, fps: float) -> None:
        from PySide6.QtWidgets import QMessageBox
        self._export_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setValue(100)
        self._status_label.setText(f"完成：{rows} 条文本（fps={fps:.3f}）")
        QMessageBox.information(self, "完成", f"已导出 {rows} 条字幕到：\n{out}")

    def _on_export_failed(self, msg: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        self._export_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setValue(0)
        self._status_label.setText(f"失败：{msg}")
        if msg != "已取消":
            QMessageBox.critical(self, "导出失败", msg)

    def _cancel_export(self) -> None:
        w = self._worker
        if w is not None and w.isRunning():
            w.cancel()
            self._status_label.setText("正在取消…")

    def closeEvent(self, event) -> None:
        try:
            self._cancel_export()
        except Exception:
            pass
        w = self._worker
        if w is not None:
            try:
                w.wait(3000)
            except Exception:
                pass
        super().closeEvent(event)


def main() -> int:
    import sys
    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import Theme, setTheme
    app = QApplication(sys.argv)
    setTheme(Theme.AUTO)
    window = SubtitleExtractorApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    import sys
    sys.exit(main())
