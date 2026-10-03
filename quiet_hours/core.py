"""核心计算：查询 UTC 范围内允许触发的连续区间。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import QuietRules, QuietWindow
from .rules import resolve_window

_UTC = timezone.utc
_SCAN_STEP = timedelta(hours=1)
_ONE_SECOND = timedelta(seconds=1)


def _offset_at(zone: ZoneInfo, instant: datetime) -> timedelta:
    return instant.astimezone(zone).utcoffset()  # type: ignore[return-value]


def _find_transitions(
    zone: ZoneInfo, start: datetime, end: datetime
) -> list[datetime]:
    """找出 (start, end) 内全部偏移切换瞬间（UTC，精确到秒）。"""
    transitions: list[datetime] = []
    cursor = start
    current_off = _offset_at(zone, cursor)
    while cursor < end:
        nxt = min(cursor + _SCAN_STEP, end)
        if _offset_at(zone, nxt) != current_off:
            lo, hi = cursor, nxt
            while hi - lo > _ONE_SECOND:
                mid = (lo + (hi - lo) / 2).replace(microsecond=0)
                if mid <= lo:
                    mid = lo + _ONE_SECOND
                if _offset_at(zone, mid) == current_off:
                    lo = mid
                else:
                    hi = mid
            transitions.append(hi)
            cursor = hi
            current_off = _offset_at(zone, cursor)
        else:
            cursor = nxt
    return transitions


def _quiet_local_intervals(
    window: QuietWindow, day: date
) -> list[tuple[datetime, datetime]]:
    """静默窗在本地日期 day 上覆盖的本地时间区间（naive，左闭右开）。"""
    midnight = datetime.combine(day, time.min)
    next_midnight = midnight + timedelta(days=1)
    if window.start == window.end:
        return [(midnight, next_midnight)]
    if window.start < window.end:
        return [
            (
                datetime.combine(day, window.start),
                datetime.combine(day, window.end),
            )
        ]
    return [
        (datetime.combine(day, window.start), next_midnight),
        (midnight, datetime.combine(day, window.end)),
    ]


def _quiet_utc_intervals(
    zone: ZoneInfo,
    window: QuietWindow,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, datetime]]:
    """把每日本地静默窗映射为 [start, end) 内的 UTC 静默区间。

    按恒定偏移分段：每段内 local = utc + offset 是平移，本地静默窗的
    原像是单个区间；回拨产生的重复本地时刻自然落在两段偏移中各自
    命中，向前跳跃中不存在的本地时刻没有任何原像。
    """
    bounds = [start, *_find_transitions(zone, start, end), end]
    quiet: list[tuple[datetime, datetime]] = []
    for seg_start, seg_end in zip(bounds, bounds[1:]):
        if seg_start >= seg_end:
            continue
        off = _offset_at(zone, seg_start)
        first_day = (seg_start + off).date() - timedelta(days=1)
        last_day = (seg_end + off).date()
        day = first_day
        while day <= last_day:
            for local_start, local_end in _quiet_local_intervals(window, day):
                quiet_start = (local_start - off).replace(tzinfo=_UTC)
                quiet_end = (local_end - off).replace(tzinfo=_UTC)
                lo = max(quiet_start, seg_start)
                hi = min(quiet_end, seg_end)
                if lo < hi:
                    quiet.append((lo, hi))
            day += timedelta(days=1)
    return quiet


def _merge(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def allowed_intervals(
    tz: str,
    region: str | None,
    campaign: str | None,
    rules: QuietRules,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, datetime]]:
    """返回 [start, end) 内所有允许触发的连续 UTC 区间（左闭右开、已合并）。"""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end 必须是带时区的 datetime")
    start = start.astimezone(_UTC)
    end = end.astimezone(_UTC)
    if start >= end:
        return []
    window = resolve_window(rules, region, campaign)
    zone = ZoneInfo(tz)
    quiet = _merge(_quiet_utc_intervals(zone, window, start, end))
    allowed: list[tuple[datetime, datetime]] = []
    cursor = start
    for quiet_start, quiet_end in quiet:
        if cursor < quiet_start:
            allowed.append((cursor, quiet_start))
        cursor = max(cursor, quiet_end)
    if cursor < end:
        allowed.append((cursor, end))
    return allowed
