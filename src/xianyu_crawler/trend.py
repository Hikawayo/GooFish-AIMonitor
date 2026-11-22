"""单个条件内的价格总览: 把这个条件下所有商品的观测压成一条时间轴。

后端只做分桶与聚合, 不关心怎么画。分桶按调用方给的时区偏移(默认东八区),
所以「按天」的边界就是用户本地零点, 而不是 UTC 零点。

返回两组东西:
- `series`: 每个时间桶的「当前最低价」和「中位数」, 用来画主趋势线;
- `items`: 每件商品自己的点, 用来把全部商品画进同一张图。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

MODES = ("all", "day", "week", "month")

# 「全部时间」下时间点太多时等距抽稀, 避免 SVG 里几千个点
MAX_SERIES_POINTS = 240
# 商品太多时只画观测最多的若干条, 否则线会糊成一团
MAX_ITEMS = 30


def _bucket_time(moment: datetime, mode: str, tz: timedelta) -> datetime:
    """把 UTC 时刻按本地时区归到 天 / 周(周一起) / 月 的桶。all 模式原样返回。"""
    if mode == "all":
        return moment
    local = moment + tz
    if mode == "day":
        local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    elif mode == "week":
        local = (local - timedelta(days=local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0)
    elif mode == "month":
        local = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return local - tz


def build(rows, mode: str = "all", tz_minutes: int = 480) -> dict:
    """rows: 可迭代的 (item_id, title, observed_at, price), 时间可以是乱序。"""
    if mode not in MODES:
        raise ValueError(f"mode 只能是 {MODES}")
    tz = timedelta(minutes=tz_minutes)

    points = [(str(item_id), title or "", moment, float(price))
              for item_id, title, moment, price in rows
              if item_id and moment is not None and price is not None]
    points.sort(key=lambda row: row[2])
    if not points:
        return {"mode": mode, "from": None, "to": None, "series": [], "items": [],
                "observations": 0}

    buckets: dict[datetime, dict[str, float]] = {}
    titles: dict[str, str] = {}
    for item_id, title, moment, price in points:
        titles.setdefault(item_id, title)
        # 同一桶里后到的观测覆盖先到的 → 桶价 = 该时段最后一次观测
        buckets.setdefault(_bucket_time(moment, mode, tz), {})[item_id] = price

    timeline = sorted(buckets)
    keep = set(range(len(timeline)))
    if mode == "all" and len(timeline) > MAX_SERIES_POINTS:
        keep = {round(i * (len(timeline) - 1) / (MAX_SERIES_POINTS - 1))
                for i in range(MAX_SERIES_POINTS)}

    last: dict[str, float] = {}
    pending: dict[str, float] = {}
    series: list[dict] = []
    per_item: dict[str, list[dict]] = {}
    for index, stamp in enumerate(timeline):
        pending.update(buckets[stamp])
        if index not in keep:
            continue                      # 被抽掉的桶并入下一个保留点, 状态不丢
        for item_id, price in pending.items():
            per_item.setdefault(item_id, []).append({"t": stamp, "price": price})
        last.update(pending)
        pending = {}
        values = list(last.values())
        series.append({"t": stamp, "min": min(values),
                       "median": float(median(values)), "count": len(values)})

    order = sorted(per_item, key=lambda item_id: (-len(per_item[item_id]), item_id))[:MAX_ITEMS]
    items = [{"item_id": item_id, "title": titles.get(item_id, ""),
              "points": per_item[item_id]} for item_id in order]
    return {"mode": mode, "from": timeline[0], "to": timeline[-1],
            "series": series, "items": items, "observations": len(points)}
