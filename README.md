# video-subtitle-extractor

从视频**固定区域**（字幕条/文本条）提取文本的 **CLI + GUI** 应用，基于通用引擎
[chr431/video_ocr_engine](https://github.com/chr431/video_ocr_engine)（git submodule
`third_party/video_ocr_engine`，sys.path bootstrap）。输出两列 CSV：
**秒级时间戳 + 原始 OCR 文本**（中文等，原样输出不做处理）。

## 依赖

- Python 3.11+
- 引擎子模块：`git submodule update --init --recursive`（即 `third_party/video_ocr_engine`）
- 引擎依赖：`numpy / onnxruntime / psutil`（`pip install -e third_party/video_ocr_engine` 或手动安装）
- 解码 fork **chr431/decord**（NVDEC/CPU；`--sample-stride>1` 建议 **≥v0.7.12**
  以获得等差步长快速路径，旧版退化为逐索引 seek，仍正确但更慢）——**解码必需**，
  `scripts/setup.ps1` 会一键安装 v0.7.12 发布包（PyPI 版 decord 不支持本项目特性）
- GUI：`PySide6-Essentials` + `PySide6-Fluent-Widgets`（**GPLv3**，见许可证）

## 安装

```bash
git clone --recurse-submodules https://github.com/chr431/video_subtitle_extractor.git
cd video_subtitle_extractor
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -e ".[dev]"
pip install -e third_party/video_ocr_engine        # 引擎 + 其依赖
# decord fork：运行 scripts\setup.ps1 会自动下载 chr431/decord v0.7.12 发布包
# （缓存到 _decord_build\）并装入 .venv。GUI 精简 Qt（PySide6-Addons 是可废弃的
# ~400MB，且其 RECORD 误含 Essentials 的 Qt6Core.dll——卸载后需强制重装
# Essentials 恢复，否则 QtCore 加载失败）：
pip uninstall -y PySide6-Addons
pip install --force-reinstall --no-deps PySide6-Essentials
```

## 一键脚本（Windows PowerShell）

仓库 `scripts/` 提供三个一键脚本（右键「使用 PowerShell 运行」，或
`powershell -ExecutionPolicy Bypass -File scripts\xxx.ps1`）：

| 脚本 | 作用 |
|------|------|
| `scripts/setup.ps1` | **一键配置 venv**（参考 RaceVideoToLog）：拉引擎子模块 → 建 `.venv` → 写引擎 `.pth` → 装本项目（含 dev）+ 引擎依赖 → 装 **decord 解码 fork**（`_decord_build\` 优先或下载 v0.7.12，解码必需，`-SkipDecord` 可跳过）→ 精简 Qt（移除 `PySide6-Addons` 并强制重装 `PySide6-Essentials` 修复 RECORD 缺陷；`-KeepAddons` 保留）。可选 `-NoDev` |
| `scripts/run_gui.ps1` | **一键启动 GUI**：用 `.venv` 的 python 运行 `gui.py`（未配置时提示先跑 setup） |
| `scripts/build_exe.ps1` | **一键构建 frozen exe**（参考 RaceVideoToLog）：自动补 .venv → 校验关键依赖（onnxruntime/numpy/PySide6/decord/qfluentwidgets，**不含 CUDA/TensorRT**）→ 装 PyInstaller → 按 `scripts/VideoSubtitleExtractor.spec` 冻结 GUI，产物 `dist\VideoSubtitleExtractor\`（onedir；引擎源码、OCR 模型、decord 解码后端已随包；spec 已排除未用依赖） |

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1      # 首次
powershell -ExecutionPolicy Bypass -File scripts\run_gui.ps1    # 启动 GUI
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1  # 构建 exe
```

## 用法

### CLI

```bash
# 源码方式（仓库根目录即源码根）
python subtitle_extract_cli.py episode.mkv --roi 10 850 1910 940 \
    --start-frame 0 --end-frame 3000 -o subtitles.csv

# 分频采样：字幕更新慢，只处理每个第 3 帧（大幅降低解码/处理压力）
python subtitle_extract_cli.py episode.mkv --roi 10 850 1910 940 \
    --sample-stride 3 -o subtitles.csv

# pip 安装后可用命令
subtitle-extract episode.mkv --roi 10 850 1910 940 -o subtitles.csv
```

### GUI（导入视频 → 选 ROI/帧范围 → 导出）

```bash
python gui.py                     # 或 pip 安装后: subtitle-extract-gui
# 或一键: powershell -ExecutionPolicy Bypass -File scripts\run_gui.ps1
```

- **导入视频**：打开文件并载入元信息与首帧（预览显示）
- **选 ROI**：在预览画面上**拖拽框选**字幕条区域，或用右侧「识别范围（像素）」spinbox 微调
- **帧范围**：`开始帧 / 结束帧`（默认全片；可用当前帧设为起点/终点）
- **采样步长**：`1`=逐帧；`>1`=分频采样（字幕等慢更新内容）
- **导出字幕 CSV**：后台线程跑引擎（进度条实时反馈），写 `time_sec,text` 两列 CSV；
  可随时「取消」

### 参数（CLI）

| 参数 | 默认 | 说明 |
|------|------|------|
| `video` | — | 视频输入（位置参数） |
| `--roi X1 Y1 X2 Y2` | 必填 | 字幕/文本条区域 |
| `--start-frame N` | 0 | 开始帧号 |
| `--end-frame N` | 到末尾 | 结束帧号（0 视为末尾） |
| `--sample-stride N` | 1 | 分频采样步长：只处理每个第 N 帧（字幕等慢更新内容） |
| `-o, --output` | `<视频名>_subtitles.csv` | 输出 CSV 路径 |

解码/OCR 后端用演示默认：`decode=auto`（GPU 优先回退 CPU）、`OCR=cpu`（ONNX，
免 TRT 构建），不在此暴露引擎细节。

### CSV 输出

`utf-8-sig`，两列（对中文/含逗号文本自动加引号）：

| time_sec | text |
|---|---|
| 12 | 你好，世界 |
| 15 | 我们继续 |

- `time_sec`：段代表帧（识别帧）在视频中的实际秒数（绝对帧号 ÷ 引擎自测 fps，
  四舍五入到秒）。`--sample-stride>1` 时最多偏移 `(stride-1)/fps` 秒。
- `text`：OCR 原始文本，原样输出（不解析/过滤/规整）；无文本的段跳过。

## 测试

```bash
python -m pytest tests/ -v
```

纯单元测试（行构建/时间戳/写文件/参数解析）无需视频/decord/GPU/OCR；GUI 冒烟
（导入窗口构造）在 `QT_QPA_PLATFORM=offscreen` 下跑。端到端需本机安装 decord +
测试视频后手动跑 CLI/GUI。

## 许可证

**GPL-3.0-or-later**（GUI 依赖 PySide6-Fluent-Widgets 为 GPLv3，故本应用为
GPLv3）。通用引擎 [chr431/video_ocr_engine](https://github.com/chr431/video_ocr_engine)
是独立仓库，保持 **Apache-2.0**（作为 submodule 被本应用包含）。

