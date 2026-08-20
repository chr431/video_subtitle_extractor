"""视频加载与预览逻辑（SubtitleExtractorApp 的 mixin，移植自 RaceVideoToLog.gui_video）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QFileDialog, QMessageBox

# ── 引擎子模块路径引导（必须在 import 引擎模块之前）──
from engine_bootstrap import ensure_engine_path  # noqa: E402
ensure_engine_path()

from video_utils import VideoMetadata, format_duration, open_decord_vr  # noqa: E402
from widget_utils import set_value_silent  # noqa: E402


class VideoLoadMixin:
    """依赖宿主：video_path/_preview_vr/_preview_frame_no/metadata/roi_*/标签/滑块等状态。"""

    def _import_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择需要处理的视频", "",
            "视频文件 (*.mp4 *.mkv *.avi *.mov *.m4v *.wmv *.flv *.webm);;所有文件 (*.*)")
        if not path:
            return
        try:
            self._load_video(Path(path))
        except ModuleNotFoundError as e:
            # 解码后端缺失（decord 需自建 fork，PyPI 版不支持）→ 给出可执行提示
            if "decord" in str(e):
                QMessageBox.critical(self, "导入失败",
                    "缺少视频解码依赖 decord（需自建 fork chr431/decord，PyPI 版不支持）。\n\n"
                    "请运行一键脚本安装：\n"
                    "    powershell -ExecutionPolicy Bypass -File scripts\\setup.ps1\n\n"
                    "或手动从 https://github.com/chr431/decord/releases 获取发布产物后重试。")
            else:
                QMessageBox.critical(self, "导入失败", str(e))
            self._status_label.setText("导入失败。")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))
            self._status_label.setText("导入失败。")

    def _load_video(self, path: Path) -> None:
        vr, _label = open_decord_vr(str(path))
        try:
            codec = vr.get_codec() or "?"
        except Exception:
            codec = "?"
        try:
            fc = len(vr)
            fps = vr.get_avg_fps()
            first = vr[0].asnumpy()  # decord 返回 RGB
            h, w = first.shape[:2]
            dur = fc / fps if fps > 0 else 0.0
        except Exception:
            # 读首帧失败：直接抛出（无需 del vr，异常路径不会继续使用）
            raise RuntimeError("无法读取视频第一帧。")

        if self._preview_vr is not None:
            del self._preview_vr
        self._preview_vr = vr
        self._preview_frame_no = 0

        self.video_path = path
        self.metadata = VideoMetadata(path=path, duration_sec=dur, width=w, height=h,
                                      fps=fps, codec=codec, frame_count=fc)
        hh, ww, ch = first.shape
        self.first_frame_qimg = QImage(first.data, ww, hh, ch * ww,
                                       QImage.Format.Format_RGB888).copy()

        self._file_label.setText(str(path))
        self._dur_label.setText(format_duration(dur))
        self._res_label.setText(f"{w} x {h}")
        self._fps_label.setText(f"{fps:.3f}" if fps > 0 else "Unknown")
        self._codec_label.setText(codec)
        self._status_label.setText("视频已载入，请输入识别范围并预览。")
        self._slider.setRange(0, fc - 1)
        self._slider.setValue(0)
        self._frame_label.setText(f"#{0}/{fc}")
        self._preview_widget.set_video_size(w, h)
        self._preview_widget.set_roi(self.roi_x1.value(), self.roi_y1.value(),
                                     self.roi_x2.value(), self.roi_y2.value())
        self._show_frame(0)
        for s, m in [(self.roi_x1, w), (self.roi_y1, h),
                     (self.roi_x2, w), (self.roi_y2, h)]:
            s.setMaximum(m - 1)
        # 帧范围：只扩展 spin 范围，不自动改值（保持用户已设值/默认 0-0=全片，同参考）
        for s in (self.frame_start, self.frame_end):
            s.setRange(0, fc - 1)
        # 输出命名在导出时通过保存对话框完成（对标参考），无需在此预填

    def _on_preview_roi(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """预览拖拽 ROI → 同步 spinbox（静默赋值，不触发联动校验）。"""
        for s, v in [(self.roi_x1, x1), (self.roi_y1, y1),
                     (self.roi_x2, x2), (self.roi_y2, y2)]:
            set_value_silent(s, v)

    def _show_frame(self, frame_no: int) -> None:
        pm = None
        vr = self._preview_vr
        if frame_no > 0 and vr is not None and frame_no < len(vr):
            try:
                frame = vr[frame_no].asnumpy()  # decord 返回 RGB
                h, w, ch = frame.shape
                qimg = QImage(frame.data, w, h, ch * w,
                              QImage.Format.Format_RGB888).copy()
                pm = QPixmap.fromImage(qimg)
            except Exception:
                pass
        if pm is None and self.first_frame_qimg is not None:
            pm = QPixmap.fromImage(self.first_frame_qimg)
        if pm is not None:
            self._preview_widget.set_frame(pm)

    def _on_slider(self, value: int) -> None:
        if self.metadata:
            self._frame_label.setText(f"#{value}/{self.metadata.frame_count}")
        self._throttle_timer.stop()
        self._throttle_timer.start(30)

    def _show_throttled_frame(self) -> None:
        self._show_frame(self._slider.value())

    def _step(self, delta: int) -> None:
        if not self.metadata:
            return
        v = max(0, min(self.metadata.frame_count - 1, self._slider.value() + delta))
        self._slider.setValue(v)

    def _on_roi_spin(self, spin) -> None:
        if spin is self.roi_x1 and self.roi_x1.value() > self.roi_x2.value() - 1:
            set_value_silent(spin, self.roi_x2.value() - 1)
        elif spin is self.roi_x2 and self.roi_x2.value() < self.roi_x1.value() + 1:
            set_value_silent(spin, self.roi_x1.value() + 1)
        elif spin is self.roi_y1 and self.roi_y1.value() > self.roi_y2.value() - 1:
            set_value_silent(spin, self.roi_y2.value() - 1)
        elif spin is self.roi_y2 and self.roi_y2.value() < self.roi_y1.value() + 1:
            set_value_silent(spin, self.roi_y1.value() + 1)
        # 预览控件在 ROI 面板之后构建；构造期 spinbox 的 valueChanged 触发时
        # 可能还未创建，此时只需同步数值、跳过预览更新。
        pv = getattr(self, "_preview_widget", None)
        if pv is None:
            return
        pv.set_roi(
            self.roi_x1.value(), self.roi_y1.value(),
            self.roi_x2.value(), self.roi_y2.value())
