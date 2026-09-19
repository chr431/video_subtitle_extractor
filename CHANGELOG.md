# Changelog

## [0.2.2] - 2026-09-19

### 修复

- **发布包补上 CLI 入口**：冻结产物此前只有 GUI exe（`console=False`、入口写死
  `gui.py`），CLI 仅存在于源码/pip 安装形态。spec 改双入口（GUI + CLI，
  共享 `_internal/`），CLI 名为 `subtitle-extract.exe`（与 pip entry point 一致）。
- **OCR 模型随包缺陷**：spec 把 `Tree()` 的 TOC 元组当 `(src, dest)` 解包
  （实际为 `(dest, src, typecode)`），模型文件被当目录拷入产物，frozen CLI
  报 `PermissionError: [Errno 13] ... Is a directory`。改为逐文件 `os.walk`。
- **`--decode-backend hybrid` 静默降级**：venv 装的 decord 0.7.12 无原生
  hybrid ctx（需 ≥0.7.15），引擎静默回退纯 GPU。对齐 decord **0.8.4**，
  并在 `setup.ps1` 增加 hybrid ctx 能力自检（缺失显式告警）。
- EXE 版本资源从 `pyproject.toml` 读取（原硬编码 `0.1.0`）。

### 变更

- decord 依赖改为 `pyproject.toml` 的 PEP 508 wheel URL（与 RaceVideoToLog
  同一做法）；`setup.ps1` 不再下载 zip / 手工拷 DLL，只做导入与能力校验。
- CI 新增发布前**冻结 CLI 冒烟门禁**（合成视频 + CPU 后端；失败不出 tag/release）。
- spec 打印改 ASCII（CI 控制台 cp1252）；pathex 不再重复塞 site-packages
  （PyInstaller 7.0 起为错误）。

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
