# Release Notes

## v0.2.0（2026-08-21）— 字幕提取性能大幅提升

### ⚡ 性能

- **相似段合并默认开启**：噪声把同一条字幕切成多段时，OCR 前自动合并，只识别一次。
  - 高噪声视频（新三国03）段数 6506 → 约 1165，OCR 次数减少约 82%
  - CPU+TRT 单集约 29.4s → 16.1s；CPU+CPU 约 60s → 20.5s
- **gray 输出默认开启**：字幕场景不需要彩色预览，减少解码/转换数据量
- 默认关闭代表帧/帧序列保留（`keep_crops=False` / `keep_frames=False`），降低长视频内存
- 5 集 batch 队列实测（CPU+TRT+merge）：约 **80.8s**

### 🔧 兼容

- 保留 `--no-merge-similar` 可关闭相似段合并
- 保留 `--decode-backend auto/cpu/nvdec`、`--ocr-backend auto/cpu/tensorrt`
- 默认解码后端保持 `auto`（NVDEC 优先，不可用回退 CPU）

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
