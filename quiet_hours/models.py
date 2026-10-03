"""数据类型定义：静默窗与规则配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class QuietWindow:
    """每日重复的本地静默窗，起点包含、终点不包含。

    start 晚于 end 表示跨午夜；start == end 表示全天静默。
    """

    start: time
    end: time


DEFAULT_WINDOW = QuietWindow(time(21, 0), time(8, 0))


@dataclass(frozen=True)
class QuietRules:
    """进程内保存的静默规则。

    优先级：活动配置 > 区域配置 > 默认配置；覆盖为整窗替换。
    """

    default: QuietWindow = DEFAULT_WINDOW
    regions: Mapping[str, QuietWindow] = field(
        default_factory=lambda: MappingProxyType({})
    )
    campaigns: Mapping[str, QuietWindow] = field(
        default_factory=lambda: MappingProxyType({})
    )
