"""核心计算：把本地静默窗映射为 UTC 允许区间。

思路：
- 静默状态只在两类真实瞬时发生变化：
  1. 本地钟面时间跨过窗口起点/终点（回拨时同一本地时刻会跨两次，
     跳跃时不存在的本地时刻一次也不跨）；
  2. UTC 偏移本身发生切换的瞬时（本地钟面跳跃或回拨）。
- 收集这两类分界点后，相邻分界点之间偏移恒定、本地时间随 UTC 线性
  推进，静默状态不变，取中点换算本地时间判定即可。
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import Interval, QuietHoursConfig, QuietWindow
from .resolver import resolve_window

UTC = timezone.utc
_SCAN_STEP = timedelta(hours=6)


def _utc_occurrences(tz: ZoneInfo, local_dt: datetime) -> list[datetime]:
    """本地（naive）时刻对应的真实 UTC 瞬时，可能 0、1、2 个。"""
    occurrences: list[datetime] = []
    for fold in (0, 1):
        aware = local_dt.replace(tzinfo=tz, fold=fold)
        instant = aware.astimezone(UTC)
        if instant.astimezone(tz).replace(tzinfo=None) == local_dt:
            if instant not in occurrences:
                occurrences.append(instant)
    occurrences.sort()
    return occurrences


def _offset_transitions(tz: ZoneInfo, start: datetime, end: datetime) -> list[datetime]:
    """[start, end] 内 UTC 偏移发生切换的瞬时（精确到秒）。"""
    transitions: list[datetime] = []
    cursor = start
    cursor_offset = cursor.astimezone(tz).utcoffset()
    while cursor < end:
        nxt = min(cursor + _SCAN_STEP, end)
        next_offset = nxt.astimezone(tz).utcoffset()
        if next_offset != cursor_offset:
            lo, hi = int(cursor.timestamp()), int(nxt.timestamp())
            while lo + 1 < hi:
                mid = (lo + hi) // 2
                if datetime.fromtimestamp(mid, UTC).astimezone(tz).utcoffset() == cursor_offset:
                    lo = mid
                else:
                    hi = mid
            transitions.append(datetime.fromtimestamp(hi, UTC))
        cursor = nxt
        cursor_offset = next_offset
    return transitions


def _is_quiet(window: QuietWindow, local_time: time) -> bool:
    start, end = window.start, window.end
    if start < end:
        return start <= local_time < end
    return local_time >= start or local_time < end


def allowed_intervals(
    config: QuietHoursConfig, start: datetime, end: datetime
) -> list[Interval]:
    """查询 [start, end)（UTC，左闭右开）内全部允许触发的连续区间。"""
    start = start.astimezone(UTC).replace(microsecond=0)
    end = end.astimezone(UTC).replace(microsecond=0)
    if not start < end:
        return []

    window = resolve_window(config)
    if window.start == window.end:
        return []

    tz = ZoneInfo(config.subscriber_tz)

    first_day = (start - timedelta(days=2)).astimezone(tz).date()
    last_day = (end + timedelta(days=2)).astimezone(tz).date()

    boundaries = {start, end}
    boundaries.update(_offset_transitions(tz, start, end))
    day = first_day
    one_day = timedelta(days=1)
    while day <= last_day:
        local_starts = [datetime.combine(day, window.start)]
        if window.start < window.end:
            local_ends = [datetime.combine(day, window.end)]
        else:
            local_ends = [datetime.combine(day + one_day, window.end)]
        for local_dt in local_starts + local_ends:
            for instant in _utc_occurrences(tz, local_dt):
                if start <= instant <= end:
                    boundaries.add(instant)
        day += one_day

    ordered = sorted(boundaries)
    allowed: list[Interval] = []
    for left, right in zip(ordered, ordered[1:]):
        seg_start = max(left, start)
        seg_end = min(right, end)
        if seg_start >= seg_end:
            continue
        midpoint = seg_start + (seg_end - seg_start) / 2
        local_time = midpoint.astimezone(tz).time()
        if _is_quiet(window, local_time):
            continue
        if allowed and allowed[-1].end == seg_start:
            allowed[-1] = Interval(allowed[-1].start, seg_end)
        else:
            allowed.append(Interval(seg_start, seg_end))
    return allowed
