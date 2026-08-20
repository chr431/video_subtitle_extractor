"""tensorrt → tensorrt_bindings 兼容 shim（移植自 RaceVideoToLog/tensorrt.py）。

本项目走 thin binding：只装 ``tensorrt_*_bindings``（~1MB 的纯 Python 绑定层）
而不是体积巨大的 tensorrt 元包（会拉入 ~2.2GB 的 tensorrt_libs）。引擎的
``ocr_trt.TrtEngine`` 与依赖检测代码都 ``import tensorrt``；本 shim 把它解析到
同一套 thin bindings。实际推理 DLL 由引擎 ``gpu_setup`` 从 PATH 扫描本地安装的
CUDA/TensorRT 加载：用户只需把 ``<TensorRT-xx>/bin``、CUDA ``bin`` 加入 PATH，
无则引擎自动回退 ONNX（CPU）。

可选依赖：cuda-python + tensorrt thin bindings（见 pyproject [trt] extra /
scripts/setup.ps1）。本模块在 bindings 缺失时不应被 import（引擎仅在
ocr_backend=tensorrt/auto 时才尝试，失败即回退 ONNX）。
"""
from tensorrt_bindings import *  # noqa: F401,F403
from tensorrt_bindings import __version__  # noqa: F401
