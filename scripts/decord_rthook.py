"""PyInstaller runtime hook — frozen 下让 decord fork 找到随包的 DLL。

参考 RaceVideoToLog\runtime_hook.py：decord 的 ``_ffi/libinfo.find_lib_path``
会首先检查 ``DECORD_LIBRARY_PATH``；把 <bundle>/decord 指过去，并在 Windows
上把该目录加入 DLL 搜索目录与 PATH，确保 decord.dll 的依赖（av*.dll 等）
也能解析。与源码运行行为一致（本项目不需要 CUDA，故不处理 CUDA_PATH）。
"""
import os
import sys

_decord_dir = os.path.abspath(
    os.path.join(getattr(sys, "_MEIPASS", ""), "decord"))
os.environ["DECORD_LIBRARY_PATH"] = _decord_dir

if os.name == "nt":
    _existing = os.environ.get("PATH", "")
    os.environ["PATH"] = _decord_dir + os.pathsep + _existing
    if os.path.isdir(_decord_dir):
        try:
            os.add_dll_directory(_decord_dir)
        except Exception:  # noqa: BLE001 — 非关键路径
            pass
