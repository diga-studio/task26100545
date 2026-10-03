import unittest
from datetime import datetime, time, timezone

from quiet_hours import (
    DEFAULT_WINDOW,
    Interval,
    QuietHoursConfig,
    QuietWindow,
    allowed_intervals,
    resolve_window,
)

UTC = timezone.utc


def utc(h, m=0, s=0, day=2, month=11, year=2025):
    return datetime(year, month, day, h, m, s, tzinfo=UTC)


def cfg(tz_name, campaign_window=None, region_window=None):
    return QuietHoursConfig(
        subscriber_tz=tz_name,
        region="r1",
        campaign="c1",
        campaign_window=campaign_window,
        region_window=region_window,
    )


def pairs(intervals):
    return [(i.start, i.end) for i in intervals]


class FallBackTest(unittest.TestCase):
    """America/New_York 2025-11-02 回拨：01:00-02:00 出现两次。"""

    def test_repeated_hour_not_swallowed(self):
        config = cfg("America/New_York", campaign_window=QuietWindow(time(1, 30), time(2, 30)))
        result = allowed_intervals(config, utc(5, 0), utc(8, 0))
        self.assertEqual(
            pairs(result),
            [(utc(5, 0), utc(5, 30)), (utc(6, 0), utc(6, 30)), (utc(7, 30), utc(8, 0))],
        )


class SpringForwardGapTest(unittest.TestCase):
    """Australia/Lord_Howe 2025-10-05 02:00 -> 02:30 向前跳 30 分钟。"""

    def test_nonexistent_window_start(self):
        config = cfg("Australia/Lord_Howe", campaign_window=QuietWindow(time(2, 10), time(2, 40)))
        result = allowed_intervals(config, utc(15, 0, day=4, month=10), utc(16, 0, day=4, month=10))
        self.assertEqual(
            pairs(result),
            [(utc(15, 0, day=4, month=10), utc(15, 30, day=4, month=10)),
             (utc(15, 40, day=4, month=10), utc(16, 0, day=4, month=10))],
        )


class PrecedenceTest(unittest.TestCase):
    def test_campaign_beats_region_beats_default(self):
        c = cfg("Asia/Shanghai",
                campaign_window=QuietWindow(time(1, 0), time(2, 0)),
                region_window=QuietWindow(time(3, 0), time(4, 0)))
        self.assertEqual(resolve_window(c), QuietWindow(time(1, 0), time(2, 0)))
        c = cfg("Asia/Shanghai", region_window=QuietWindow(time(3, 0), time(4, 0)))
        self.assertEqual(resolve_window(c), QuietWindow(time(3, 0), time(4, 0)))
        self.assertEqual(resolve_window(cfg("Asia/Shanghai")), DEFAULT_WINDOW)

    def test_override_replaces_not_stacks(self):
        # 区域窗 03:00-04:00 替换默认 21:00-08:00，默认窗时段不再静默。
        config = cfg("Asia/Shanghai", region_window=QuietWindow(time(3, 0), time(4, 0)))
        # 上海 UTC+8：03:00-04:00 本地 = 19:00-20:00 UTC，查询 18:00-21:00 UTC。
        result = allowed_intervals(config, utc(18, 0, day=1), utc(21, 0, day=1))
        self.assertEqual(
            pairs(result),
            [(utc(18, 0, day=1), utc(19, 0, day=1)), (utc(20, 0, day=1), utc(21, 0, day=1))],
        )


class WindowShapeTest(unittest.TestCase):
    def test_cross_midnight_window(self):
        # 上海 22:00-06:00 本地 = 14:00-22:00 UTC。
        config = cfg("Asia/Shanghai", campaign_window=QuietWindow(time(22, 0), time(6, 0)))
        result = allowed_intervals(config, utc(12, 0, day=1), utc(0, 0, day=3))
        self.assertEqual(
            pairs(result),
            [(utc(12, 0, day=1), utc(14, 0, day=1)),
             (utc(22, 0, day=1), utc(14, 0, day=2)),
             (utc(22, 0, day=2), utc(0, 0, day=3))],
        )

    def test_full_day_window_returns_empty(self):
        config = cfg("Asia/Shanghai", campaign_window=QuietWindow(time(0, 0), time(0, 0)))
        self.assertEqual(allowed_intervals(config, utc(0, 0, day=1), utc(0, 0, day=4)), [])

    def test_default_window_used_when_unconfigured(self):
        # 上海默认 21:00-08:00 本地 = 13:00-00:00 UTC。
        result = allowed_intervals(cfg("Asia/Shanghai"), utc(12, 0, day=1), utc(2, 0, day=2))
        self.assertEqual(
            pairs(result),
            [(utc(12, 0, day=1), utc(13, 0, day=1)), (utc(0, 0, day=2), utc(2, 0, day=2))],
        )


class MergeAndEdgeTest(unittest.TestCase):
    def test_adjacent_allowed_merged(self):
        # 窗口完全在查询范围外，整段应合并为一条。
        config = cfg("Asia/Shanghai", campaign_window=QuietWindow(time(3, 0), time(4, 0)))
        result = allowed_intervals(config, utc(0, 0, day=1), utc(10, 0, day=1))
        self.assertEqual(pairs(result), [(utc(0, 0, day=1), utc(10, 0, day=1))])

    def test_empty_range(self):
        config = cfg("Asia/Shanghai")
        self.assertEqual(allowed_intervals(config, utc(5, 0), utc(5, 0)), [])

    def test_fully_quiet_returns_empty(self):
        config = cfg("Asia/Shanghai", campaign_window=QuietWindow(time(0, 0), time(12, 0)))
        # 上海 00:00-12:00 本地 = 16:00-04:00 UTC，查询段完全落在静默内。
        self.assertEqual(allowed_intervals(config, utc(18, 0, day=1), utc(20, 0, day=1)), [])


class DateLineSkipTest(unittest.TestCase):
    def test_apia_skipped_day(self):
        # Pacific/Apia 2011-12-30 整日被跳过（-10 -> +14）。
        # 2011-12-29 23:00 本地 = 2011-12-30 09:00 UTC（+10 偏移时代）。
        config = cfg("Pacific/Apia", campaign_window=QuietWindow(time(23, 0), time(1, 0)))
        result = allowed_intervals(
            config,
            datetime(2011, 12, 30, 8, 0, tzinfo=UTC),
            datetime(2011, 12, 30, 16, 0, tzinfo=UTC),
        )
        # 08:00-09:00 UTC 本地 22:00-23:00 允许；09:00 UTC 跳到 12-31 00:00（静默）；
        # 静默到 12-31 01:00 本地 = 12-30 11:00 UTC。
        self.assertEqual(
            pairs(result),
            [(datetime(2011, 12, 30, 8, 0, tzinfo=UTC), datetime(2011, 12, 30, 9, 0, tzinfo=UTC)),
             (datetime(2011, 12, 30, 11, 0, tzinfo=UTC), datetime(2011, 12, 30, 16, 0, tzinfo=UTC))],
        )


if __name__ == "__main__":
    unittest.main()


class BruteForceConsistencyTest(unittest.TestCase):
    """与逐秒采样对拍：结果必须恰好覆盖查询范围内所有允许瞬时。"""

    def check(self, tz_name, window, start, end):
        from zoneinfo import ZoneInfo
        from datetime import timedelta

        config = cfg(tz_name, campaign_window=window)
        result = allowed_intervals(config, start, end)

        # 结果自身：升序、不重叠、左闭右开、落在范围内。
        for prev, nxt in zip(result, result[1:]):
            self.assertLess(prev.end, nxt.start)
        for iv in result:
            self.assertLess(iv.start, iv.end)
            self.assertGreaterEqual(iv.start, start)
            self.assertLessEqual(iv.end, end)

        tz = ZoneInfo(tz_name)
        from quiet_hours.calculator import _is_quiet

        cursor = start
        allowed_expected = []
        while cursor < end:
            local_t = cursor.astimezone(tz).time()
            if not _is_quiet(window, local_t):
                allowed_expected.append(cursor)
            cursor += timedelta(seconds=1)

        # 展开的允许秒集合必须一致。
        expanded = []
        for iv in result:
            t = iv.start
            while t < iv.end:
                expanded.append(t)
                t += timedelta(seconds=1)
        self.assertEqual(expanded, allowed_expected)

    def test_new_york_fall_back_day(self):
        self.check("America/New_York", QuietWindow(time(1, 30), time(2, 30)),
                   utc(0, 0, day=2), utc(12, 0, day=2))

    def test_lord_howe_half_hour_jump_day(self):
        self.check("Australia/Lord_Howe", QuietWindow(time(2, 10), time(2, 40)),
                   utc(12, 0, day=4, month=10), utc(0, 0, day=5, month=10))

    def test_apia_date_line_skip(self):
        self.check("Pacific/Apia", QuietWindow(time(23, 0), time(1, 0)),
                   datetime(2011, 12, 29, 0, 0, tzinfo=UTC),
                   datetime(2011, 12, 31, 12, 0, tzinfo=UTC))

    def test_default_window_cross_midnight(self):
        self.check("Asia/Shanghai", DEFAULT_WINDOW, utc(0, 0, day=1), utc(0, 0, day=3))
