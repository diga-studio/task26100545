# quiet_hours — 短信静默时段计算库

纯 Python 库，无接口层、无外部服务；规则保存在进程内，时区资料使用本机 IANA 数据（`zoneinfo`）。

## 规则

- 静默窗每天按订阅者本地时分重复，左闭右开；起点晚于终点表示跨午夜，起终点相同表示全天静默。
- 默认静默窗 21:00–08:00；优先级：活动配置 > 区域配置 > 默认配置，覆盖为整窗替换。
- 是否静默取决于真实瞬时对应的本地钟面时间：回拨重复的本地时刻各自适用同一规则，向前跳跃中不存在的本地时刻不占真实时间；支持半小时偏移切换与整日跳过。

## 调用

```python
from datetime import datetime, time, timezone
from quiet_hours import QuietRules, QuietWindow, allowed_intervals

rules = QuietRules(                                   # 进程内保存，一次调用期间不变
    default=QuietWindow(time(21, 0), time(8, 0)),     # 可省略，默认即 21:00-08:00
    regions={"EU": QuietWindow(time(22, 0), time(7, 0))},
    campaigns={"summer-sale": QuietWindow(time(1, 30), time(2, 30))},
)

intervals = allowed_intervals(
    tz="America/New_York",        # 订阅者 IANA 时区
    region="EU",                  # 所属区域，无则传 None
    campaign="summer-sale",       # 活动标识，无则传 None
    rules=rules,
    start=datetime(2025, 11, 2, 5, 0, tzinfo=timezone.utc),  # 带时区，左闭
    end=datetime(2025, 11, 2, 8, 0, tzinfo=timezone.utc),    # 右开
)
# -> [(05:00, 05:30), (06:00, 06:30), (07:30, 08:00)] 均为 UTC，左闭右开、已合并
```

返回 `[(start, end), ...]`，恰好覆盖查询范围内全部允许瞬时；整段禁止时返回 `[]`。

## 测试

```sh
python3 tests/test_quiet_hours.py
```
