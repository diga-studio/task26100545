"""规则解析：按优先级选出生效的静默窗。"""

from __future__ import annotations

from .models import QuietRules, QuietWindow


def resolve_window(
    rules: QuietRules,
    region: str | None = None,
    campaign: str | None = None,
) -> QuietWindow:
    """活动 > 区域 > 默认，逐级回退。"""
    if campaign is not None and campaign in rules.campaigns:
        return rules.campaigns[campaign]
    if region is not None and region in rules.regions:
        return rules.regions[region]
    return rules.default
