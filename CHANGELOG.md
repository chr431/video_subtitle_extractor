# Changelog

## [Unreleased]

### 变更

- 适配 `video_ocr_engine` 重构：解码后端新增 **混合 (CPU+NVDEC)** /
  `--decode-backend hybrid`，由引擎内 `HybridDecoder`（CPU+NVDEC 双解码生产者竞争）
  承担双解码并行。
- 删除应用级 `--dual`（批量双实例并行）、`--engine-dual` 与 GUI「双引擎并行处理」
  开关；批量恢复顺序处理，并行能力交给引擎 hybrid（NVDEC 不可用/条件不满足自动回退）。

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
