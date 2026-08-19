"""PyInstaller runtime hook — frozen 下让 decord fork 找到随包的 DLL。

decord 的 ``_ffi/libinfo.find_lib_path`` 会首先检查 ``DECORD_LIBRARY_PATH``；
spec（VideoSubtitleExtractor.spec）已把 decord.dll / FFmpeg dll 打到
<bundle>/decord，这里把它指过去，并在 Windows 上加进 DLL 搜索目录，
确保 decord.dll 的依赖（av*.dll 等）也能解析。与源码运行行为一致。
"""
import os
import sys

_decord_dir = os.path.abspath(
    os.path.join(getattr(sys, "_MEIPASS", ""), "decord"))
os.environ["DECORD_LIBRARY_PATH"] = _decord_dir

if os.name == "nt" and os.path.isdir(_decord_dir):
    try:
        os.add_dll_directory(_decord_dir)
    except Exception:  # noqa: BLE001 — 非关键路径
        pass
