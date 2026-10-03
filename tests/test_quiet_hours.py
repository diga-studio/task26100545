"""quiet_hours 自动化测试，可直接运行：python3 tests/test_quiet_hours.py"""

import os
import sys
import unittest
from datetime import datetime, time, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quiet_hours import (  # noqa: E402
    DEFAULT_WINDOW,
    QuietRules,
    QuietWindow,
    allowed_intervals,
    resolve_window,
)

UTC = timezone.utc


def utc(y, mo, d, h=0, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def fmt(intervals):
    return [(a.strftime("%m-%d %H:%M:%S"), b.strftime("%m-%d %H:%M:%S")) for a, b in intervals]


class ResolveTests(unittest.TestCase):
    def test_priority_and_fallback(self):
        rules = QuietRules(
            default=QuietWindow(time(21), time(8)),
            regions={"EU": QuietWindow(time(22), time(7))},
            campaigns={"c1": QuietWindow(time(0), time(1))},
        )
        self.assertEqual(resolve_window(rules, "EU", "c1"), rules.campaigns["c1"])
        self.assertEqual(resolve_window(rules, "EU", "unknown"), rules.regions["EU"])
        self.assertEqual(resolve_window(rules, "US", None), rules.default)
        self.assertEqual(resolve_window(QuietRules(), None, None), DEFAULT_WINDOW)


class AllowedIntervalsTests(unittest.TestCase):
    def test_fall_back_repeated_local_time(self):
        # 2025-11-02 America/New_York 回拨：01:00-02:00 出现两次
        rules = QuietRules(campaigns={"c": QuietWindow(time(1, 30), time(2, 30))})
        res = allowed_intervals(
            "America/New_York", None, "c", rules, utc(2025, 11, 2, 5), utc(2025, 11, 2, 8)
        )
        self.assertEqual(
            fmt(res),
            [("11-02 05:00:00", "11-02 05:30:00"),
             ("11-02 06:00:00", "11-02 06:30:00"),
             ("11-02 07:30:00", "11-02 08:00:00")],
        )

    def test_spring_forward_half_hour_gap(self):
        # 2025-10-05 Lord Howe 02:00 -> 02:30 跳半小时，02:10-02:30 不存在
        rules = QuietRules(campaigns={"c": QuietWindow(time(2, 10), time(2, 40))})
        res = allowed_intervals(
            "Australia/Lord_Howe", None, "c", rules, utc(2025, 10, 4, 15), utc(2025, 10, 4, 16)
        )
        self.assertEqual(
            fmt(res),
            [("10-04 15:00:00", "10-04 15:30:00"),
             ("10-04 15:40:00", "10-04 16:00:00")],
        )

    def test_cross_midnight_window(self):
        # 默认 21:00-08:00 跨午夜；UTC 时区下直观验证
        res = allowed_intervals("UTC", None, None, QuietRules(), utc(2025, 3, 1, 12), utc(2025, 3, 2, 12))
        self.assertEqual(fmt(res), [("03-01 12:00:00", "03-01 21:00:00"),
                                    ("03-02 08:00:00", "03-02 12:00:00")])

    def test_all_day_quiet_returns_empty(self):
        rules = QuietRules(default=QuietWindow(time(0), time(0)))
        res = allowed_intervals("UTC", None, None, rules, utc(2025, 1, 1), utc(2025, 1, 3))
        self.assertEqual(res, [])

    def test_adjacent_allowed_intervals_merged(self):
        # 静默窗恰好落在查询范围外，整段允许应合并为一段
        rules = QuietRules(default=QuietWindow(time(12), time(13)))
        res = allowed_intervals("UTC", None, None, rules, utc(2025, 6, 1, 13), utc(2025, 6, 2, 12))
        self.assertEqual(fmt(res), [("06-01 13:00:00", "06-02 12:00:00")])

    def test_empty_range(self):
        res = allowed_intervals("UTC", None, None, QuietRules(), utc(2025, 1, 1), utc(2025, 1, 1))
        self.assertEqual(res, [])

    def test_naive_datetime_rejected(self):
        with self.assertRaises(ValueError):
            allowed_intervals("UTC", None, None, QuietRules(),
                              datetime(2025, 1, 1), datetime(2025, 1, 2))

    def test_full_day_skip_dateline(self):
        # Apia 2011-12-30 整日被跳过（UTC+14 变更），全天静默不影响相邻日
        rules = QuietRules(default=QuietWindow(time(0), time(0)))
        res = allowed_intervals(
            "Pacific/Apia", None, None, rules, utc(2011, 12, 29, 10), utc(2011, 12, 31, 10)
        )
        self.assertEqual(res, [])
        # 非全天静默时，被跳过日的窗口无原像，不应误禁
        rules2 = QuietRules(default=QuietWindow(time(12), time(13)))
        res2 = allowed_intervals(
            "Pacific/Apia", None, None, rules2, utc(2011, 12, 29, 0), utc(2011, 12, 31, 0)
        )
        # 12-29 12:00(+14? 当日为 -10) -> UTC 22:00-23:00 静默；
        # 12-30 不存在；12-31 12:00(+14) -> 12-30 22:00-23:00 UTC 静默
        self.assertEqual(
            fmt(res2),
            [("12-29 00:00:00", "12-29 22:00:00"),
             ("12-29 23:00:00", "12-30 22:00:00"),
             ("12-30 23:00:00", "12-31 00:00:00")],
        )

    def test_half_hour_offset_zone(self):
        # 常驻半小时偏移（无 DST）：St John's 冬令时 UTC-3:30
        rules = QuietRules(default=QuietWindow(time(0, 0), time(1, 0)))
        res = allowed_intervals(
            "America/St_Johns", None, None, rules, utc(2025, 1, 10, 0), utc(2025, 1, 10, 6)
        )
        # 本地 00:00-01:00 = UTC 03:30-04:30
        self.assertEqual(
            fmt(res),
            [("01-10 00:00:00", "01-10 03:30:00"),
             ("01-10 04:30:00", "01-10 06:00:00")],
        )

    def test_result_exactly_covers_range(self):
        # 不变量：结果落在查询范围内、升序、互不相接（相接已合并）
        rules = QuietRules(regions={"R": QuietWindow(time(21, 15), time(6, 45))})
        start, end = utc(2025, 3, 1), utc(2025, 4, 15)
        res = allowed_intervals("Europe/Berlin", "R", None, rules, start, end)
        self.assertGreaterEqual(res[0][0], start)
        self.assertLessEqual(res[-1][1], end)
        for (_, prev_end), (next_start, _) in zip(res, res[1:]):
            self.assertLess(prev_end, next_start)

    def test_second_precision(self):
        rules = QuietRules(default=QuietWindow(time(0, 0, 1), time(0, 0, 3)))
        res = allowed_intervals("UTC", None, None, rules, utc(2025, 5, 1), utc(2025, 5, 1, 0, 0, 5))
        self.assertEqual(
            fmt(res),
            [("05-01 00:00:00", "05-01 00:00:01"),
             ("05-01 00:00:03", "05-01 00:00:05")],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
