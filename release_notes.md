# Release Notes

## v0.1.0（2026-08-20）— 首个正式发布

### 🎉 功能

- 视频字幕提取 **CLI + GUI**（PySide6 + qfluentwidgets），单视频 / 批量两个页签
- ROI 拖拽预览、帧范围、采样步长、导出后处理（剔除重复行与纯数字行）
- 解码后端：自动 / CPU / NVDEC；OCR 后端：自动 / CPU / TensorRT（thin binding）
- 批量可合并为单个 CSV：`video,time_hms,text`
- 时间列统一 `hh:mm:ss`，兼容 >1h 视频
- 主题默认跟随系统，可手动切换浅/深色
- 一键脚本：`scripts/setup.ps1` / `scripts/run_gui.ps1` / `scripts/build_exe.ps1`

### 🔧 工程

- PyInstaller onedir 冻结 exe（含引擎源码、OCR 模型、decord/TRT 运行时）
- 发布包使用 7-Zip LZMA2 `-mx=9` 最大压缩
