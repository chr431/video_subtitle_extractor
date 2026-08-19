"""应用级 QConfig 配置（设置持久化）。

- 主题：由 qfluentwidgets 内置 qconfig 持久化（setTheme 写 config/config.json，
  与 RaceVideoToLog 行为一致）。
- 应用配置：输出目录、导出后处理开关等，用 QConfig 持久化到
  config/app_config.json（仓库根/可执行文件目录下）。
"""
from __future__ import annotations

from pathlib import Path

from qfluentwidgets import ConfigItem, QConfig


class _AppConfig(QConfig):
    """应用配置项（继承内置 QConfig 以复用保存/加载机制）。"""

    # 默认输出目录（空 = 视频所在目录）
    outputDir = ConfigItem("Export", "OutputDir", "")
    # 导出后处理（去重 + 剔除纯数字行，默认开启）
    postProcess = ConfigItem("Export", "PostProcess", True)


app_config = _AppConfig()
app_config.file = Path("config/app_config.json")


def load_app_config() -> None:
    """读取持久化配置（文件不存在时静默使用默认值）。"""
    try:
        if app_config.file.is_file():
            app_config.load(app_config.file)
        else:
            app_config.file.parent.mkdir(parents=True, exist_ok=True)
            app_config.save()
    except Exception:  # noqa: BLE001 — 配置损坏不应阻断启动
        pass


def save_app_config() -> None:
    try:
        app_config.save()
    except Exception:  # noqa: BLE001
        pass
