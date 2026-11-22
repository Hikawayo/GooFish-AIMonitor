import threading

from xianyu_crawler.storage.db import make_session
from xianyu_crawler.storage import repo
from xianyu_crawler.storage.orm import ItemRow
from xianyu_crawler.models import Item


def session():
    return make_session("sqlite:///:memory:", create=True)


def test_first_write_seeds_publish_price():
    """首次入库知道原价与发布时间时, 先补这个起点, 走势不从半路开始。"""
    from datetime import datetime

    s = session()
    item = Item(item_id="p1", title="t", url="u", price=1500,
                publish_time=datetime(2026, 10, 10, 1, 0), original_price=3000)
    repo.upsert_item_with_price(s, item, source="search")
    assert [point.price for point in repo.price_history(s, "p1")] == [3000, 1500]
    assert repo.get_latest_price(s, "p1") == 1500
    row = s.get(ItemRow, "p1")
    assert row is not None and row.original_price == 3000
    # 已有的商品不会被重复补
    repo.upsert_item_with_price(s, item.model_copy(update={"price": 1400}), source="search")
    assert [point.price for point in repo.price_history(s, "p1")] == [3000, 1500, 1400]


def test_concurrent_first_open_builds_database_once(tmp_path):
    """新账号首屏会并发打进来几个请求; 建表和配配置行都不能互踩(否则一片 500)。"""
    url = f"sqlite:///{(tmp_path / 'race.db').as_posix()}"
    errors = []
    start = threading.Barrier(6)

    def open_page():
        try:
            start.wait()
            s = make_session(url, create=True)
            repo.get_config(s)
            repo.list_watches(s)
            repo.stats(s)
            s.close()
        except Exception as e:  # noqa: BLE001 - 收集线程里的失败
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=open_page) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_watch_crud():
    s = session()
    w = repo.add_watch(s, name="w1", keywords='["iPhone"]', price_max=5000, enabled=True)
    assert w.id is not None
    assert len(repo.list_watches(s)) == 1
    repo.update_watch(s, w.id, price_max=4000, enabled=False)
    got = repo.get_watch(s, w.id)
    assert got is not None and got.price_max == 4000 and got.enabled is False
    repo.delete_watch(s, w.id)
    assert repo.list_watches(s) == []


def test_config_defaults_and_update():
    s = session()
    cfg = repo.get_config(s)
    assert cfg.notify_to == "" and cfg.schedule_minutes == 120   # 默认空, 走本地配置/UI
    repo.update_config(s, schedule_minutes=60, paused=True)
    cfg2 = repo.get_config(s)
    assert cfg2.schedule_minutes == 60 and cfg2.paused is True


def test_recommendation_lifecycle():
    s = session()
    it = Item(item_id="r1", title="t", url="u", price=1000)
    assert repo.create_recommendation(s, it, "w1") is True
    assert repo.create_recommendation(s, it, "w1") is False     # 已见过 → 不重复
    recs = repo.list_recommendations(s, "new")
    assert len(recs) == 1 and recs[0].item_id == "r1"
    repo.set_rec_status(s, "r1", "rejected")
    assert repo.list_recommendations(s, "new") == []
    assert len(repo.list_recommendations(s, "rejected")) == 1
