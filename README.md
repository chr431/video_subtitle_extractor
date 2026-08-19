# video-subtitle-extractor

从视频**固定区域**（字幕条/文本条）提取文本的 CLI 应用，基于通用引擎
[chr431/video_ocr_engine](https://github.com/chr431/video_ocr_engine)（git submodule
`third_party/video_ocr_engine`，sys.path bootstrap 调用）。输出两列 CSV：
**秒级时间戳 + 原始 OCR 文本**（中文等，原样输出不做处理）。

## 依赖

- Python 3.11+
- 引擎子模块：`git submodule update --init --recursive`（即 `third_party/video_ocr_engine`）
- 引擎依赖：`numpy / onnxruntime / psutil`（`pip install -e third_party/video_ocr_engine` 或手动安装）
- 解码 fork **chr431/decord**（NVDEC/CPU；`--sample-stride>1` 建议 **≥v0.7.12**
  以获得等差步长快速路径，旧版退化为逐索引 seek，仍正确但更慢）

## 安装

```bash
git clone --recurse-submodules https://github.com/chr431/video_subtitle_extractor.git
cd video_subtitle_extractor
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -e ".[dev]"
pip install -e third_party/video_ocr_engine        # 引擎 + 其依赖
# decord fork：从 chr431/decord v0.7.12 release 安装（见引擎 README）
```

## 用法

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

### 参数

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

纯单元测试（行构建/时间戳/写文件/参数解析）无需视频/decord/GPU/OCR。
端到端需本机安装 decord + 测试视频后手动跑 CLI。

## 许可证

Apache-2.0（应用代码为原作者原创作品；通用引擎 chr431/video_ocr_engine 亦为
Apache-2.0）。
