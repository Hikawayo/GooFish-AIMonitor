from datetime import datetime, timedelta

from xianyu_crawler import trend


def obs(item_id, moment, price, title="t"):
    return (item_id, title, moment, price)


def test_day_buckets_follow_local_midnight():
    """东八区: UTC 15:30 是本地 23:30, UTC 16:30 是次日 00:30 → 两个桶。"""
    rows = [
        obs("a", datetime(2026, 11, 21, 15, 30), 100),
        obs("a", datetime(2026, 11, 21, 16, 30), 90),
    ]
    data = trend.build(rows, mode="day", tz_minutes=480)
    assert len(data["series"]) == 2
    assert [point["min"] for point in data["series"]] == [100, 90]


def test_same_bucket_keeps_last_price():
    rows = [
        obs("a", datetime(2026, 11, 21, 2, 0), 100),
        obs("a", datetime(2026, 11, 21, 9, 0), 80),
    ]
    data = trend.build(rows, mode="day", tz_minutes=480)
    assert len(data["series"]) == 1
    assert data["series"][0]["min"] == 80
    assert [point["price"] for point in data["items"][0]["points"]] == [80]


def test_aggregate_carries_each_item_forward():
    """b 出现前不参与最低价; 出现后 a 的旧价格仍然有效。"""
    rows = [
        obs("a", datetime(2026, 11, 21, 1, 0), 100),
        obs("b", datetime(2026, 11, 21, 3, 0), 60),
    ]
    data = trend.build(rows, mode="all", tz_minutes=480)
    assert [point["count"] for point in data["series"]] == [1, 2]
    assert [point["min"] for point in data["series"]] == [100, 60]
    assert [point["median"] for point in data["series"]] == [100, 80]


def test_week_buckets_start_on_monday():
    rows = [
        obs("a", datetime(2026, 11, 15, 4, 0), 100),   # 本地周日 12:00
        obs("a", datetime(2026, 11, 16, 4, 0), 90),    # 本地周一 12:00
    ]
    data = trend.build(rows, mode="week", tz_minutes=480)
    assert len(data["series"]) == 2
    starts = [point["t"] + timedelta(hours=8) for point in data["series"]]
    assert all(stamp.weekday() == 0 and stamp.hour == 0 for stamp in starts)   # 本地周一零点
    assert starts[0] == datetime(2026, 11, 9, 0, 0) and starts[1] == datetime(2026, 11, 16, 0, 0)


def test_all_mode_thins_long_timeline_but_keeps_ends():
    start = datetime(2026, 11, 1, 0, 0)
    rows = [obs("a", start + timedelta(minutes=i), 1000 - i) for i in range(1000)]
    data = trend.build(rows, mode="all", tz_minutes=480)
    assert len(data["series"]) <= trend.MAX_SERIES_POINTS
    assert data["series"][0]["t"] == start
    assert data["series"][-1]["t"] == start + timedelta(minutes=999)
    # 抽稀后最低价仍跟着最新观测走, 不会被丢掉
    assert data["series"][-1]["min"] == 1


def test_min_price_keeps_junk_listings_out():
    """条件里混着便宜兑换码时, 价格下限能把它们挡在统计之外。"""
    rows = [
        obs("code", datetime(2026, 11, 20, 1, 0), 3),
        obs("ticket", datetime(2026, 11, 20, 1, 0), 1500),
    ]
    data = trend.build(rows, mode="day", tz_minutes=480, min_price=500)
    assert data["items_total"] == 1 and data["items"][0]["item_id"] == "ticket"
    assert data["series"][0]["min"] == 1500 and data["observations"] == 1


def test_empty_input():
    data = trend.build([], mode="day")
    assert data["series"] == [] and data["items"] == [] and data["from"] is None
