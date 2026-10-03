# quiet_hours — 短信静默时段计算库

纯进程内 Python 库（仅依赖标准库 `zoneinfo`，使用本机 IANA 时区数据），
由上层直接调用，无接口层、无外部服务。

## 调用方式

```python
from datetime import datetime, time, timezone
from quiet_hours import QuietHoursConfig, QuietWindow, allowed_intervals

config = QuietHoursConfig(
    subscriber_tz="America/New_York",   # 订阅者 IANA 时区
    region="us-east",                   # 所属区域
    campaign="spring-promo",            # 活动标识
    campaign_window=QuietWindow(time(1, 30), time(2, 30)),  # 活动级静默窗（本地时分）
    # region_window=QuietWindow(...),   # 区域级静默窗，可选
)

intervals = allowed_intervals(
    config,
    datetime(2025, 11, 2, 5, 0, tzinfo=timezone.utc),  # 查询起点（UTC，含）
    datetime(2025, 11, 2, 8, 0, tzinfo=timezone.utc),  # 查询终点（UTC，不含）
)
for iv in intervals:
    print(iv.start, "->", iv.end)
```

## 规则

- 静默窗每天按订阅者本地时分重复，左闭右开；起点晚于终点表示跨午夜；
  起终点相同表示全天静默；未配置时默认 21:00–08:00。
- 优先级：活动窗 > 区域窗 > 默认窗，整窗替换、逐级回退。
- 返回 UTC 左闭右开区间，精确到秒，已合并相接区间；整段禁止返回 `[]`。
- 正确处理回拨（重复本地时刻各自判定）、向前跳跃（不存在的本地时刻
  不占真实时间）、半小时偏移切换与整日跳过（如 Pacific/Apia）。

## 运行测试

```bash
python3 -m unittest discover -s tests -v
```
