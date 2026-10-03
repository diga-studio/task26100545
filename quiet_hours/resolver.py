"""配置解析：活动 > 区域 > 默认，整窗替换、逐级回退。"""

from __future__ import annotations

from .models import DEFAULT_WINDOW, QuietHoursConfig, QuietWindow


def resolve_window(config: QuietHoursConfig) -> QuietWindow:
    """返回本次查询实际生效的静默窗。"""
    if config.campaign_window is not None:
        return config.campaign_window
    if config.region_window is not None:
        return config.region_window
    return DEFAULT_WINDOW
