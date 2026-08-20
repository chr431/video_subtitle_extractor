"""Video Subtitle Extractor — PySide6 + qfluentwidgets GUI 主窗口。

对标 RaceVideoToLog 的 GUI 格式：顶部主题切换 + 底部状态栏 + 单页主页
（导入视频 / ROI 预览 / 帧范围 / 采样 / 后端选择 / 导出字幕 CSV），
主题默认跟随系统（ThemeManager）。

入口：
    python gui.py            # 或 pip 安装后: subtitle-extract-gui
"""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QFileDialog, QGridLayout, QHBoxLayout, QMainWindow, QMessageBox,
    QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, CaptionLabel, CompactSpinBox, PrimaryPushButton,
    ProgressBar, PushButton, Slider, StrongBodyLabel,
    isDarkTheme, qconfig, setTheme, Theme,
)

from app_config import app_config
from extract_worker import BatchExtractWorker, ExtractWorker
from gui_settings import build_settings_panel
from gui_video import VideoLoadMixin
from preview_widget import PreviewWidget
from subtitle_extract_cli import discover_videos
from theme_manager import ThemeManager
from widget_utils import disable_spin_flyout, make_static_card, set_value_silent

# ═══════════════════ 主题颜色常量 ═══════════════════
CANVAS_BG_DARK = "#1f1f1f"
CANVAS_BG_LIGHT = "#ffffff"
CANVAS_FG_DARK = "#f0f0f0"
CANVAS_FG_LIGHT = "#000000"

# ── qfluentwidgets watcher 保护（移植自 RaceVideoToLog）──
# widget 销毁时 Paint/DynamicPropertyChange 事件会触发
# "Internal C++ object already deleted"（PySide6 已知问题）。把
# RuntimeError 捕获并忽略，避免 stderr 刷屏。
import qfluentwidgets.common.style_sheet as _qfw_ss  # noqa: E402

for _watcher_cls in (_qfw_ss.CustomStyleSheetWatcher,
                     _qfw_ss.DirtyStyleSheetWatcher):
    _orig_event_filter = _watcher_cls.eventFilter

    def _safe_event_filter(self, obj, e, _orig=_orig_event_filter):
        try:
            return _orig(self, obj, e)
        except RuntimeError:
            return False

    _watcher_cls.eventFilter = _safe_event_filter


class SubtitleExtractorApp(VideoLoadMixin, QMainWindow):
    """视频字幕提取主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Video Subtitle Extractor")
        self.resize(1500, 920)
        self.setMinimumSize(1100, 760)

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
        self._batch_videos: list = []      # 批量导入后待处理的视频列表（未开始时为空）

        self._build_ui()
        self._connect_signals()
        self._add_shortcuts()
        self._register_theme_callbacks()
        ThemeManager.refresh()

    # ═══════════════════ 构建 UI ═══════════════════

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 8, 12, 6)
        root.setSpacing(0)

        # ── 顶栏：主题按钮（主题默认跟随系统，可手动切换）──
        top_bar = QWidget()
        tbl = QHBoxLayout(top_bar)
        tbl.setContentsMargins(0, 0, 0, 4)
        tbl.addStretch()
        self._theme_btn = PushButton("☀" if not isDarkTheme() else "☾")
        self._theme_btn.setFixedSize(36, 28)
        self._theme_btn.setToolTip("切换亮色/暗色主题")
        self._theme_btn.clicked.connect(self._toggle_theme)
        tbl.addWidget(self._theme_btn)
        root.addWidget(top_bar)

        # ── 主页（所有功能都在这里）──
        self._extract_tab = QWidget()
        root.addWidget(self._extract_tab, 1)
        self._build_extract_tab()

        # ── 底部状态栏 ──
        self._footer = QWidget()
        fl = QVBoxLayout(self._footer)
        fl.setContentsMargins(0, 6, 0, 0)
        self._status_label = BodyLabel("请导入视频并设置识别范围。")
        self._progress_bar = ProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        fl.addWidget(self._status_label)
        fl.addWidget(self._progress_bar)
        root.addWidget(self._footer)

    def _build_extract_tab(self) -> None:
        layout = QVBoxLayout(self._extract_tab)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(8)

        # ── 顶栏 ──
        hdr = QHBoxLayout()
        self._import_video_btn = PushButton("导入视频")
        hdr.addWidget(self._import_video_btn)
        self._batch_btn = PushButton("批量导入…")
        hdr.addWidget(self._batch_btn)
        self._batch_start_btn = PrimaryPushButton("开始批量处理")
        self._batch_start_btn.setEnabled(False)
        hdr.addWidget(self._batch_start_btn)
        self._file_label = BodyLabel("未导入视频")
        self._file_label.setWordWrap(True)
        hdr.addWidget(self._file_label, 1)
        self._export_btn = PrimaryPushButton("导出字幕 CSV")
        hdr.addWidget(self._export_btn)
        self._cancel_btn = PushButton("取消")
        self._cancel_btn.setEnabled(False)
        hdr.addWidget(self._cancel_btn)
        layout.addLayout(hdr)

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
        layout.addWidget(info)

        # ── 主内容：左参数面板 / 右预览 ──
        main_w = QHBoxLayout()
        main_w.setSpacing(12)
        left = QWidget()
        left.setFixedWidth(420)
        self._settings = build_settings_panel(left)
        for _k, _v in self._settings.items():
            setattr(self, _k, _v)
        main_w.addWidget(left)
        right = QVBoxLayout()
        right.setSpacing(8)
        self._build_right_panel(right)
        main_w.addLayout(right, 1)
        layout.addLayout(main_w, 1)

    def _build_right_panel(self, rl: QVBoxLayout) -> None:
        # ── 识别范围（像素）—— 对标参考：紧凑两行（标签行 + spinbox 行）──
        roi_card = make_static_card()
        rgl = QGridLayout(roi_card)
        rgl.addWidget(StrongBodyLabel("识别范围（像素）"), 0, 0, 1, 4)
        self.roi_x1 = CompactSpinBox()
        self.roi_y1 = CompactSpinBox()
        self.roi_x2 = CompactSpinBox()
        self.roi_y2 = CompactSpinBox()
        for s in (self.roi_x1, self.roi_y1, self.roi_x2, self.roi_y2):
            s.setRange(0, 9999)
            s.setFixedWidth(80)
            s.valueChanged.connect(lambda v, spin=s: self._on_roi_spin(spin))
            disable_spin_flyout(s)
        self.roi_x1.setValue(0)
        self.roi_y1.setValue(0)
        self.roi_x2.setValue(100)
        self.roi_y2.setValue(40)
        # 标签一行，数值一行（同参考布局：左上一列/右上一列/左下一列/右下一列）
        rgl.addWidget(CaptionLabel("左上 X"), 1, 0)
        rgl.addWidget(CaptionLabel("左上 Y"), 1, 1)
        rgl.addWidget(CaptionLabel("右下 X"), 1, 2)
        rgl.addWidget(CaptionLabel("右下 Y"), 1, 3)
        rgl.addWidget(self.roi_x1, 2, 0)
        rgl.addWidget(self.roi_y1, 2, 1)
        rgl.addWidget(self.roi_x2, 2, 2)
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
        self._batch_btn.clicked.connect(self._batch_import_folder)
        self._batch_start_btn.clicked.connect(self._batch_start_processing)
        self._export_btn.clicked.connect(self._export_csv)
        self._cancel_btn.clicked.connect(self._cancel_export)
        self._set_start_btn.clicked.connect(
            lambda: set_value_silent(self.frame_start, self._slider.value()))
        self._set_end_btn.clicked.connect(
            lambda: set_value_silent(self.frame_end, self._slider.value()))

    def _add_shortcuts(self) -> None:
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self._step(-1))
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self._step(1))
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, lambda: self._step(10))
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, lambda: self._step(-10))

    # ═══════════════════ 导出 ═══════════════════

    def _export_csv(self) -> None:
        if self.metadata is None:
            QMessageBox.warning(self, "提示", "请先导入视频。")
            return
        if self._worker is not None and self._worker.isRunning():
            return
        x1, y1, x2, y2 = (s.value() for s in (self.roi_x1, self.roi_y1,
                                               self.roi_x2, self.roi_y2))
        if x2 <= x1 or y2 <= y1:
            QMessageBox.warning(self, "提示", "识别范围无效：右下必须大于左上（像素）。")
            return
        # 结束帧 0 表示“到视频末尾”（与 CLI 一致），因此只有 0<end<=start 才无效
        if (self.frame_end.value() != 0 and
                self.frame_end.value() <= self.frame_start.value()):
            QMessageBox.warning(self, "提示", "帧范围无效：结束帧必须大于开始帧（0 表示到视频末尾）。")
            return

        # ── 弹出保存对话框选择导出位置（对标参考：导出命名在弹出窗口完成）──
        initial = ""
        out_dir = str(app_config.outputDir.value)
        if out_dir:
            initial = str(Path(out_dir) / f"{self.video_path.stem}_subtitles.csv")
        else:
            initial = str(self.video_path.with_name(
                f"{self.video_path.stem}_subtitles.csv"))
        out_text, _ = QFileDialog.getSaveFileName(
            self, "保存字幕 CSV", initial, "CSV 文件 (*.csv);;所有文件 (*.*)")
        if not out_text:
            return
        out = Path(out_text)
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "输出路径无效", str(e))
            return

        self._import_video_btn.setEnabled(False)
        self._batch_btn.setEnabled(False)
        self._batch_start_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress_bar.setValue(0)
        self._status_label.setText(f"正在识别…（解码 + 分段 + OCR"
                                   f"{' + 后处理' if app_config.postProcess.value else ''}）")
        decode_backend = ("auto", "cpu", "nvdec")[self.backend_combo.currentIndex()]
        ocr_backend = ("auto", "cpu", "tensorrt")[self.ocr_backend_combo.currentIndex()]
        worker = ExtractWorker(
            self.video_path, (x1, y1, x2, y2),
            self.frame_start.value(), self.frame_end.value(),
            self.sample_stride.value(), out,
            postprocess=bool(app_config.postProcess.value),
            decode_backend=decode_backend,
            ocr_backend=ocr_backend)
        worker.progress.connect(self._on_export_progress)
        worker.succeeded.connect(self._on_export_done)
        worker.failed.connect(self._on_export_failed)
        self._worker = worker
        worker.start()

    def _on_export_progress(self, msg: str, pct: float) -> None:
        self._status_label.setText(msg)
        self._progress_bar.setValue(int(round(max(0.0, min(100.0, pct)))))

    def _on_export_done(self, rows: int, out: str, fps: float) -> None:
        self._import_video_btn.setEnabled(True)
        self._batch_btn.setEnabled(True)
        self._batch_start_btn.setEnabled(bool(self._batch_videos))
        self._export_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setValue(100)
        self._status_label.setText(f"完成：{rows} 条文本（fps={fps:.3f}）")
        QMessageBox.information(self, "完成", f"已导出 {rows} 条字幕到：\n{out}")

    def _on_export_failed(self, msg: str) -> None:
        self._import_video_btn.setEnabled(True)
        self._batch_btn.setEnabled(True)
        self._batch_start_btn.setEnabled(bool(self._batch_videos))
        self._export_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._progress_bar.setValue(0)
        self._status_label.setText(f"失败：{msg}")
        if msg != "已取消":
            QMessageBox.critical(self, "导出失败", msg)

    # ═══════════════════ 批量处理 ═══════════════════

    def _clear_batch(self) -> None:
        """清除当前批量待处理列表（例如用户改导入单个视频时）。"""
        self._batch_videos = []
        self._batch_start_btn.setEnabled(False)

    def _import_video(self) -> None:
        """覆盖：导入单个视频后清空批量待处理状态，避免误触发批量。"""
        super()._import_video()
        self._clear_batch()

    def _batch_import_folder(self) -> None:
        """批量导入：仅选择文件夹 + 预览第一个视频，等用户调好参数后再开始。"""
        if self._worker is not None and self._worker.isRunning():
            return
        folder = QFileDialog.getExistingDirectory(self, "选择视频文件夹", "")
        if not folder:
            return
        videos = discover_videos(Path(folder))
        if not videos:
            QMessageBox.warning(self, "没有视频", "所选文件夹内未找到视频文件。")
            return

        # 预览第一个视频（满足“预览显示第一个视频的画面”）。
        # 若之前已导入过视频且设了有效帧范围，则保留该范围；否则默认全片。
        has_custom_range = (self.metadata is not None and
                            self.frame_end.value() > self.frame_start.value())
        try:
            self._load_video(videos[0], reset_range=not has_custom_range)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "预览失败",
                                 f"无法预览第一个视频：\n{e}")
            return

        self._batch_videos = videos
        self._batch_start_btn.setEnabled(True)
        self._status_label.setText(
            f"已选择 {len(videos)} 个视频，请调整 ROI/帧范围/后端后点「开始批量处理」。")
        self._file_label.setText(
            f"批量：{len(videos)} 个视频（{Path(folder)}）")

    def _batch_start_processing(self) -> None:
        """开始批量处理：校验参数并启动顺序处理所有已导入的视频。"""
        if not self._batch_videos:
            QMessageBox.warning(self, "提示", "请先点击「批量导入…」选择视频文件夹。")
            return
        if self._worker is not None and self._worker.isRunning():
            return
        videos = self._batch_videos
        x1, y1, x2, y2 = (s.value() for s in (self.roi_x1, self.roi_y1,
                                               self.roi_x2, self.roi_y2))
        if x2 <= x1 or y2 <= y1:
            QMessageBox.warning(self, "提示", "识别范围无效：右下必须大于左上（像素）。")
            return
        # 结束帧 0 表示“到视频末尾”（与 CLI 一致），只有 0<end<=start 才无效
        if (self.frame_end.value() != 0 and
                self.frame_end.value() <= self.frame_start.value()):
            QMessageBox.warning(self, "提示", "帧范围无效：结束帧必须大于开始帧（0 表示到视频末尾）。")
            return

        self._import_video_btn.setEnabled(False)
        self._batch_btn.setEnabled(False)
        self._batch_start_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress_bar.setValue(0)
        self._status_label.setText(
            f"批量处理 {len(videos)} 个视频：{videos[0].parent}")
        worker = BatchExtractWorker(
            videos, (x1, y1, x2, y2),
            self.frame_start.value(), self.frame_end.value(),
            self.sample_stride.value(),
            postprocess=bool(app_config.postProcess.value),
            decode_backend=("auto", "cpu", "nvdec")[self.backend_combo.currentIndex()],
            ocr_backend=("auto", "cpu", "tensorrt")[self.ocr_backend_combo.currentIndex()],
        )
        worker.progress.connect(self._on_batch_progress)
        worker.video_done.connect(self._on_batch_video_done)
        worker.finished.connect(self._on_batch_done)
        self._worker = worker
        worker.start()

    def _on_batch_progress(self, msg: str, pct: float) -> None:
        self._status_label.setText(msg)
        self._progress_bar.setValue(int(round(max(0.0, min(100.0, pct)))))

    def _on_batch_video_done(self, index: int, total: int, rows: int,
                             out: str) -> None:
        self._status_label.setText(
            f"批量处理 {index}/{total}：{Path(out).name} → {rows} 条文本")
        if total:
            self._progress_bar.setValue(int(round(index / total * 100)))

    def _on_batch_done(self, ok: int, total: int, failures: list) -> None:
        self._import_video_btn.setEnabled(True)
        self._batch_btn.setEnabled(True)
        self._batch_start_btn.setEnabled(bool(self._batch_videos))
        self._export_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        if ok == total:
            self._progress_bar.setValue(100)
        else:
            self._progress_bar.setValue(0)
        msg = f"批量处理完成：成功 {ok}/{total} 个视频。"
        if failures:
            msg += f"\n失败 {len(failures)} 个：\n" + "\n".join(failures[:10])
            if len(failures) > 10:
                msg += f"\n…等 {len(failures)} 个"
            self._status_label.setText(f"批量完成：成功 {ok}/{total}（失败 {len(failures)}）")
            QMessageBox.warning(self, "批量完成", msg)
        else:
            self._status_label.setText(f"批量完成：{ok}/{total} 个视频")
            QMessageBox.information(self, "批量完成", msg)

    def _cancel_export(self) -> None:
        w = self._worker
        if w is not None and w.isRunning():
            w.cancel()
            self._status_label.setText("正在取消…")

    # ═══════════════════ 主题 ═══════════════════

    def _register_theme_callbacks(self) -> None:
        def _update_bg(dark: bool) -> None:
            bg = CANVAS_BG_DARK if dark else CANVAS_BG_LIGHT
            fg = CANVAS_FG_DARK if dark else CANVAS_FG_LIGHT
            for w in (self, self.centralWidget()):
                if w is None:
                    continue
                p = w.palette()
                p.setColor(QPalette.ColorRole.Window, QColor(bg))
                p.setColor(QPalette.ColorRole.Base, QColor(bg))
                p.setColor(QPalette.ColorRole.WindowText, QColor(fg))
                p.setColor(QPalette.ColorRole.Text, QColor(fg))
                p.setColor(QPalette.ColorRole.ButtonText, QColor(fg))
                w.setPalette(p)
        ThemeManager.register(_update_bg)

        def _update_titlebar(dark: bool) -> None:
            if sys.platform != "win32":
                return
            try:
                hwnd = int(self.winId())
                val = ctypes.c_int(1 if dark else 0)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
            except Exception:
                pass
        ThemeManager.register(_update_titlebar)

        def _update_icon(dark: bool) -> None:
            self._theme_btn.setText("☀" if not dark else "☾")
        ThemeManager.register(_update_icon)

        self._theme_callbacks = [_update_bg, _update_titlebar, _update_icon]

    def _toggle_theme(self) -> None:
        if qconfig.theme == Theme.DARK:
            setTheme(Theme.LIGHT)
        else:
            setTheme(Theme.DARK)
        ThemeManager.refresh()

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
        for cb in getattr(self, "_theme_callbacks", []):
            try:
                ThemeManager.unregister(cb)
            except Exception:
                pass
        super().closeEvent(event)


def main() -> int:
    import sys
    from PySide6.QtWidgets import QApplication
    from app_config import load_app_config
    load_app_config()
    app = QApplication(sys.argv)
    # 主题默认跟随系统（可点右上角 ☀/☾ 手动切换）
    setTheme(Theme.AUTO)
    window = SubtitleExtractorApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    import sys
    sys.exit(main())
