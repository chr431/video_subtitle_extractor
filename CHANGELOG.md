# Changelog

## [0.2.0] - 2026-08-21

### 性能

- 相似段合并默认开启，高噪声字幕视频 OCR 次数减少约 82%
- gray 输出默认开启，减少解码/转换数据量
- 默认关闭代表帧/帧序列保留，降低长视频内存
- 新增 `--no-merge-similar` 可关闭相似段合并

## [0.1.0] - 2026-08-20

### 新增

- 首个正式发布：视频字幕提取 CLI + GUI
- 单视频 / 批量两个页签；ROI 拖拽预览、帧范围、采样步长
- 解码后端（自动/CPU/NVDEC）与 OCR 后端（自动/CPU/TensorRT）
- 导出后处理（剔重复/纯数字行）、批量合并单文件（video/time_hms/text）
- 一键脚本（setup/run_gui/build_exe）与 GitHub Actions 发布工作流
