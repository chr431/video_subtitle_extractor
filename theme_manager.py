"""主题管理器 — 集中管理所有需要手动更新的主题回调（移植自 RaceVideoToLog）。

Fluent 控件会自动响应 qconfig.themeChanged；这里仅注册原生 Qt 等需要手动
更新的 widget（背景色/标题栏/主题图标等）。
"""
from __future__ import annotations

from collections.abc import Callable


class ThemeManager:
    """单例式主题回调管理器。"""

    _callbacks: list[Callable[[bool], None]] = []

    @classmethod
    def register(cls, fn: Callable[[bool], None]) -> Callable[[bool], None]:
        cls._callbacks.append(fn)
        return fn

    @classmethod
    def unregister(cls, fn: Callable[[bool], None]) -> None:
        if fn in cls._callbacks:
            cls._callbacks.remove(fn)

    @classmethod
    def refresh(cls) -> None:
        from qfluentwidgets import isDarkTheme
        dark = isDarkTheme()
        for fn in cls._callbacks:
            try:
                fn(dark)
            except Exception:
                pass
