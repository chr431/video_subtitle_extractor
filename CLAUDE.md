# video_subtitle_extractor — 项目知识

## 开发约定（重要）

- **CLI 与 GUI 功能必须保持同步**：除了无法进行视觉预览外，GUI 提供的功能 CLI 也必须有对应入口。
- 今后新增任何功能时，必须同时添加 CLI 参数与 GUI 控件/入口，避免两端功能漂移。
- 开发过程中的结论、性能实测、设计决策记录在本文件（CLAUDE.md），不写入用户向 README。
- 需要用户阅读的功能说明才写入 README。

## 当前功能同步状态

- 单视频提取：CLI 与 GUI 均支持。
- 批量提取：GUI 与 CLI 均支持（合并输出）。
- 引擎内混合解码（hybrid）：GUI 解码后端下拉与 CLI `--decode-backend hybrid` 均支持；
  应用级 `--dual` / `--engine-dual` 与 GUI「双引擎并行处理」开关已删除（2026-08 引擎重构后
  双解码并行由引擎 HybridDecoder 承担）。
- 相似段合并、gray 输出、代表帧关闭等引擎选项：CLI 与 GUI 已同步。

## 性能记录

- 批量 5 视频队列双引擎并发：约 107.6s → 67.0s（约 1.6× 加速）。
- 双引擎需要 NVDEC 和 TensorRT 均可用；不满足时回退单实例并提示。
- 2026-08 批量 5 视频、`stride=8`、`end=12000`、宽 ROI 对比：
  - 单实例顺序：21.29s
  - **应用级双引擎（--dual）：14.14s（最快）**
  - 引擎内双流水线 2 片：17.88s
  - 引擎内双流水线 4 片：20.46s
  - 应用级双引擎 + 引擎内双流水线 2 片：20.61s（嵌套反而更慢）
  - 结论：批量场景**应用级双引擎仍优于引擎内双流水线**；引擎内双流水线更适合单视频长任务，批量下不建议嵌套。
- 2026-08 悬浮字幕分离实验（text_video_test + 人工 truth）：
  - 默认灰度+gamma：与 truth 集合 present 195/196（仅 1 缺失、2 多余）
  - binary 作 OCR 输入：present 189/196（7 缺失、13 多余），准确率下降
  - **binary 仅用于相似帧合并（RVTOL_TEXT_SEP_MERGE=binary）**：
    - truth 覆盖与默认一致（195/196）
    - 10000 帧段数 276 → 244（-12%），OCR 调用减少
    - 耗时 5.41s → 5.06s（-6%）
  - 结论：分离图适合做“相似帧合并”，不适合直接替代 OCR 输入。

## 2026-08-25 — 下游 video_ocr_engine 重构适配（hybrid 取代双流水线）

- 引擎已移除 `dual_pipeline` / `dual_backends` 构造参数与 `_dual_pipeline.py`，
  新增 `decode_backend="hybrid"`（顶层 `hybrid_decode.HybridDecoder`：CPU+NVDEC
  双解码生产者按 kfe 分片竞争，对下游仍是 VideoReader 同形替身）。
- 本项目删除应用级 `--dual`（批量双实例并行）、`--engine-dual`、GUI「双引擎并行
  处理」开关及互补后端/可用性探测逻辑；批量恢复顺序处理，并行能力交给每个视频的
  hybrid 解码（需要 NVDEC 可用、stride==1、编码非 AV1，否则引擎自动回退到纯
  GPU/CPU）。
- hybrid 只并行解码，OCR 仍走单一后端，不复现旧的“双完整流水线混配/让位”问题。
- **已知引擎缺陷与绕行（e8b2637）**：`HybridDecoder._Batch` 没有 `to_dlpack`，
  宿主校准 `with_dev=True` 时 gray 单通道 DLPack 解析会崩溃
  （`AttributeError: '_Batch' object has no attribute 'to_dlpack'`）。
  本项目对 `decode_backend="hybrid"` 且 `stride==1` 的候选路径暂用 **RGB 输出**
  （分段/OCR 内部仍转灰度，结果一致），stride>1 与其它后端保持 gray。
  待引擎修复后应删除该绕行、恢复 gray。
- **相关实测（2026-08-25，text_video_test / batch_test）**：
  - text_test.mp4（AV1，stride=1，hybrid）：引擎按设计回退纯 GPU（hybrid 不支持
    AV1），输出 201 条文本，truth 覆盖 196/196（额外 2 条）。
  - batch_test 5 集全片、stride=8、hybrid：5/5 成功，合并 CSV 3110 行
    （各集 598/641/603/641/627）。
  - 新三国01.mkv（h264，stride=1，hybrid）3000 帧探针：`meta.backend =
    decord/GPU+CPU-hybrid`，确认 HybridDecoder 真正激活（728 段）。
