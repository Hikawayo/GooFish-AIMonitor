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
MAX_ITEMS = 60
# 判断「主要价位」时, 两档价格差多少倍才算两个市场(¥20 的兑换码 vs ¥1300 的门票)
AUTO_SPLIT_RATIO = 6.0


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


def _auto_floor(rows) -> tuple[float | None, int]:
    """价格分两簇时给出一个分界: 取最大的「相邻价倍数跳变」。

    一个条件里常同时挂着 ¥2 的兑换码和 ¥1500 的门票。不区分的话纵轴会被
    ¥1 撑到 ¥3400, 门票怎么降都挤在底部一条线里。没有明显跳变就不过滤。
    """
    latest: dict[str, float] = {}
    peak: dict[str, float] = {}
    for item_id, _, _, price in rows:
        if item_id is None or price is None:
            continue
        latest[str(item_id)] = float(price)
        peak[str(item_id)] = max(peak.get(str(item_id), 0.0), float(price))
    prices = sorted(value for value in latest.values() if value > 0)
    if len(prices) < 4:
        return None, 0
    best_ratio, best_index = 1.0, -1
    for index in range(len(prices) - 1):
        ratio = prices[index + 1] / max(prices[index], 0.01)
        if ratio > best_ratio:
            best_ratio, best_index = ratio, index
    if best_index < 0 or best_ratio < AUTO_SPLIT_RATIO:
        return None, 0
    floor = (prices[best_index] * prices[best_index + 1]) ** 0.5
    excluded = sum(1 for value in peak.values() if value < floor)
    return floor, excluded


def build(rows, mode: str = "all", tz_minutes: int = 480,
          min_price: float | None = None) -> dict:
    """rows: 可迭代的 (item_id, title, observed_at, price), 时间可以是乱序。

    商品按「历史最高价 ≥ 下限」筛选, 而不是按单次观测: 一件 ¥1500 的门票
    降到 ¥400 时仍然留在图里(能看到这次跳水), 只有从来没进过这个价位的
    兑换码才会被挡掉。min_price 不传时按 _auto_floor 自动判断。
    """
    if mode not in MODES:
        raise ValueError(f"mode 只能是 {MODES}")
    tz = timedelta(minutes=tz_minutes)

    rows = list(rows)
    auto_floor, excluded = (None, 0)
    floor = min_price
    if floor is None:
        auto_floor, excluded = _auto_floor(rows)
        floor = auto_floor

    if floor:
        peak: dict[str, float] = {}
        for item_id, _, _, price in rows:
            if item_id is not None and price is not None:
                peak[str(item_id)] = max(peak.get(str(item_id), 0.0), float(price))
        keep_ids = {item_id for item_id, top in peak.items() if top >= floor}
        rows = [row for row in rows if str(row[0]) in keep_ids]
        excluded = sum(1 for item_id in peak if item_id not in keep_ids)

    points = [(str(item_id), title or "", moment, float(price))
              for item_id, title, moment, price in rows
              if item_id and moment is not None and price is not None]
    points.sort(key=lambda row: row[2])
    if not points:
        return {"mode": mode, "from": None, "to": None, "series": [], "items": [],
                "observations": 0, "items_total": 0,
                "auto_floor": auto_floor, "excluded": excluded}

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
            "series": series, "items": items, "observations": len(points),
            "items_total": len(per_item),
            "auto_floor": auto_floor, "excluded": excluded}
