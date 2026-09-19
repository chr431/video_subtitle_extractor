# Release Notes

## v0.2.2（2026-09-19）— 发布包补上 CLI 入口 + 解码器对齐

### 🎯 对你意味着什么

- **发布包现在同时含 GUI 与 CLI 两个可执行文件**（此前只有 GUI）：
  - `VideoSubtitleExtractor.exe` — GUI（双击即用，无控制台窗口）
  - `subtitle-extract.exe` — CLI（带控制台，进度/错误可见、可重定向）
  
  两者共享同一份 `_internal\`，整体体积几乎不变（只多一个 ~5.6MB 的引导器）。
  CLI 用法与源码方式完全一致，只把命令换成 exe：
  `.\subtitle-extract.exe episode.mkv --roi 10 850 1910 940 -o subs.csv`
- **`--decode-backend hybrid` 现在真正生效**：此前 venv 里装的是 decord 0.7.12，
  而原生 hybrid 需要 ≥0.7.15——引擎会**静默回退纯 GPU**（实测同一命令 0.7.12 打
  `[decord/GPU]`，0.8.4 打 `[decord/hybrid]`）。现已对齐 **decord 0.8.4**。
- 若你只跑 GUI、不用 hybrid，本次升级同样无需任何操作。

### 🔧 技术细节

- **spec 改双入口**：两个 `Analysis`（GUI 收集 Qt/qfluentwidgets，CLI 不收集）
  + 两个 `EXE`（`console=False` / `console=True`）汇入同一个 `COLLECT`，依赖按
  (dest, src) 去重 → 只落一份。
- **修 OCR 模型随包缺陷**：原写法把 `Tree(...)` 的 TOC 当 `(src, dest)` 解包，
  实际上元组是 `(dest, src, typecode)`，于是 PyInstaller 把模型**目录**当数据文件
  拷过去——产物里 `ocr_models/ppocrv6_dict.txt` 是个目录，frozen CLI 一开就报
  `PermissionError: [Errno 13] ... Is a directory`。改为逐文件 `os.walk`
  （同 RaceVideoToLog）。
- **版本资源修正**：EXE 属性里的 FileVersion/ProductVersion 原硬编码 `0.1.0`，
  现从 `pyproject.toml` 读取（单一事实源）。
- **decord 依赖改为 pyproject 的 wheel URL**（与 RaceVideoToLog 同一做法）：
  `setup.ps1` 不再手写版本号、下载 zip、手工拷 DLL；只做导入与 hybrid ctx 能力
  校验（缺 ctx 时显式告警而非静默降级）。
- **清理**：移除 `_decord_build\` 缓存流程与相关过时提示；spec 打印改 ASCII
  （CI 控制台 cp1252）；pathex 不再重复塞 site-packages（PyInstaller 7.0 起会报错）。

### 验证

- 本机全量单元测试 **26 passed**（含 GUI offscreen 冒烟）
- frozen CLI 真机冒烟：`subtitle-extract.exe test.mp4 --roi ... --end-frame 150
  --decode-backend cpu --ocr-backend cpu` → 退出码 0、CSV `time_hms,text` 表头
  与 4 条识别结果
- frozen CLI `--help` 正常输出；frozen GUI 启动后常驻运行（进程存活、无崩溃）
- decord 0.8.4 下 `--decode-backend hybrid` 实测打 `[decord/hybrid]`
- CI 新增**发布前冻结 CLI 冒烟门禁**（合成视频 + CPU 后端，失败不产生 tag/release）

## v0.2.1（2026-09-19）— 引擎 0.14.1 对齐

### 🎯 对你意味着什么

- **引擎升级到 0.14.1**：引擎删除了六个历史遗留的兼容模块（`engine_config` /
  `ocr_native` / `video_utils` 等），本应用已同步。**你无需任何操作**；
  若你有自己的脚本 `import engine_config` 之类，请改为
  `from video_ocr_engine.config import constants`（其余五个同理，
  映射表见引擎仓 `docs/MIGRATION.md` §1）
- **解码器与 OCR 引擎无变化**（仍为 decord fork + OpenVINO CPU / TensorRT GPU），
  本次仅依赖版本对齐

### 🔧 技术细节

- `pyproject.toml`：`video-ocr-engine` pin `v0.14.0` → `v0.14.1`
- `tensorrt.py` docstring 更新（提及的引擎模块名改包内路径；
  顺带修正"无则回退 ONNX"为实际的 OpenVINO——引擎 C-48 已换 CPU 引擎）
- 本应用对旧兼容模块**零代码依赖**（仅 2 处 docstring 提及）

### 验证

本机全量测试 **26 passed**；CLI 端到端实测（hybrid 解码 + 3000 帧 ROI）
提取字幕成功。

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
