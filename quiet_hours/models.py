"""数据类型定义：静默窗、配置与查询结果。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time


@dataclass(frozen=True)
class QuietWindow:
    """每日重复的本地静默窗，起点包含、终点不包含。

    start 晚于 end 表示跨午夜；start == end 表示全天静默。
    """

    start: time
    end: time


DEFAULT_WINDOW = QuietWindow(start=time(21, 0), end=time(8, 0))


@dataclass(frozen=True)
class QuietHoursConfig:
    """一次查询期间不变的静默配置。

    campaign_window 优先于 region_window，region_window 优先于默认窗；
    覆盖为整窗替换，缺省时逐级回退。
    """

    subscriber_tz: str
    region: str
    campaign: str
    campaign_window: QuietWindow | None = None
    region_window: QuietWindow | None = None


@dataclass(frozen=True)
class Interval:
    """UTC 左闭右开区间，精度到秒。"""

    start: datetime
    end: datetime
