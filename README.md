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

### GUI（Pivot 导航：提取 + 设置 两页）

```bash
python gui.py                     # 或 pip 安装后: subtitle-extract-gui
# 或一键: powershell -ExecutionPolicy Bypass -File scripts\run_gui.ps1
```

GUI 框架对齐 RaceVideoToLog：**两个页签（单视频 / 批量）+ 底部状态栏 + 主题切换**
（右上角 ☀/☾，默认**跟随系统**，可手动切换浅/深色）。两个页签共用中间的
视频信息/参数/ROI/预览区，各自显示对应的操作按钮。

- **单视频页签**：**导入视频** → 载入元信息与首帧（预览显示）→ 调整参数 →
  **导出字幕 CSV**（弹出保存对话框选择输出位置与文件名，默认 `<视频名>_subtitles.csv`）
- **批量页签**：点「批量导入…」选择文件夹，只**预览第一个视频**并列出待处理数量，
  此时可调整 ROI/帧范围/后端；确认后点「开始批量处理」**顺序处理所有视频**（按文件名
  排序；输出 `<视频名>_subtitles.csv` 到各视频所在目录），单个失败会继续处理并在结束
  时汇总
- **批量输出为单个文件**（仅批量页签显示，左下方“批量输出”卡）：开启后在开始批量处理
  时选择合并 CSV 路径，所有视频合并为一份 **三列 `video,time_hms,text`**
  （视频文件名 / hh:mm:ss / 字幕），不再生成单个视频 CSV
- **共用**：左面板可选择 **解码后端**（自动/CPU/NVDEC）与 **OCR 后端**
  （自动/CPU/TensorRT）；后台线程跑引擎（进度条实时反馈），可随时「取消」；
  **导出后处理**（默认开启）剔除重复行与纯数字行（左侧面板开关）
- **默认值对齐参考**：解码后端=自动、OCR 后端=自动、ROI 初始 0、帧范围 0-0（=全片）；
  引擎内部以 gray 输出运行（字幕场景不需要彩色预览，减少解码/转换数据量）；
  自动解码逻辑：优先 NVDEC，不可用回退 CPU；强多核 CPU + h264 时可手动选 CPU 获得更好性能；
  导入视频后不自动改写帧范围值（用户已设值保留）

### TRT（可选，thin binding）

- 只装 `cuda-python` + `tensorrt` 纯 Python 绑定层（`[trt]` extra，~几 MB），
  **不装**体积巨大的 tensorrt 元包（~2.2GB）。`scripts/setup.ps1` 默认安装；
  `-SkipTrt` 跳过 / `pip install -e ".[trt]"` 手动装。
- 运行时由引擎 `gpu_setup` 从 **PATH 扫描本地 CUDA/TensorRT** 定位实际推理 DLL
  （先 add_dll_directory 注册）；**无本机 TensorRT 时 OCR 自动回退 ONNX（CPU）**。
- 选 OCR 后端 = TensorRT / 自动 即用 TRT（GUI `ocr_backend_combo` 或 CLI
  `--ocr-backend tensorrt`）。引擎缓存构建在 `third_party/video_ocr_engine/ocr_engines/`
  （子模块已忽略，不入库）。

### FFmpeg/decord 日志

部分 MKV 片源会让 FFmpeg Matroska demuxer 输出大量“Element ... exceeds containing
master element”的良性日志（容器不规范，但可跳过继续解码，不影响 CSV）。默认已静音；
如需查看请设置环境变量 `RVTOL_FFMPEG_LOG_LEVEL=error|warning|info|verbose`。

### 参数（CLI）

| 参数 | 默认 | 说明 |
|------|------|------|
| `video` | — | 视频输入（位置参数） |
| `--roi X1 Y1 X2 Y2` | 必填 | 字幕/文本条区域 |
| `--start-frame N` | 0 | 开始帧号 |
| `--end-frame N` | 到末尾 | 结束帧号（0 视为末尾） |
| `--sample-stride N` | 1 | 分频采样步长：只处理每个第 N 帧（字幕等慢更新内容） |
| `--decode-backend` | auto | 解码后端：auto / cpu / nvdec（auto=NVDEC 优先，不可用回退 CPU） |
| `--ocr-backend` | auto | OCR 后端：auto / cpu / tensorrt（无 TRT 自动回退 ONNX） |
| `--no-postprocess` | 关 | 关闭后处理（默认开启：剔除重复行与纯数字行） |
| `-o, --output` | `<视频名>_subtitles.csv` | 输出 CSV 路径 |

### CSV 输出

`utf-8-sig`，两列（对中文/含逗号文本自动加引号）；第一列为 **hh:mm:ss**：

| time_hms | text |
|---|---|
| 00:00:12 | 你好，世界 |
| 00:00:15 | 我们继续 |

- `time_hms`：段代表帧（识别帧）在视频中的实际秒数（绝对帧号 ÷ 引擎自测 fps，
  四舍五入到秒）转换为 `hh:mm:ss`（如 65 秒 → `00:01:05`，>1 小时视频自动 `01:00:00`）。
  统一三部分可避免 Excel 把 `M:SS` 误识别成时间显示成 `mm:ss:00`。
  `--sample-stride>1` 时最多偏移 `(stride-1)/fps` 秒。
- `text`：OCR 原始文本，原样输出（不解析/过滤/规整）；无文本的段跳过。
- **后处理**（默认开启，`--no-postprocess` 关闭 / 左侧面板开关）：剔除
  「纯数字行」（`isdigit`，含全角数字）与「(time_hms, text) 重复行」；
  不同秒数的相同文本（字幕持续多行）不算重复，予以保留。

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

