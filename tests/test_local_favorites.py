from datetime import datetime

from fastapi.testclient import TestClient

from xianyu_crawler import liveness, service
from xianyu_crawler.config import Settings
from xianyu_crawler.models import Item
from xianyu_crawler.storage import repo
from xianyu_crawler.storage.orm import ItemRow
from xianyu_crawler.web import runtime
from xianyu_crawler.web.app import app


def test_detail_price_requires_matching_item_and_success():
    detail = {"ret": ["SUCCESS::调用成功"], "data": {"itemDO": {"itemId": 42, "soldPrice": "1100.00"}}}
    assert liveness.parse_detail_price(detail, "42") == (1100, False)
    assert liveness.parse_detail_price(detail, "43") == (None, False)
    assert liveness.parse_detail_price(None, "42") == (None, False)
    assert liveness.parse_detail_price({"ret": ["FAIL_SYS_TIMEOUT"]}, "42") == (None, False)
    assert liveness.parse_detail_price({"ret": ["FAIL_BIZ_ITEM_DEL_NOT_FOUND"]}, "42") == (None, True)


def test_detail_reading_carries_original_price_and_publish_time():
    detail = {"ret": ["SUCCESS::调用成功"], "data": {"itemDO": {
        "itemId": 42, "soldPrice": "94", "originalPrice": "128", "gmtCreate": 1791594988000}}}
    reading = liveness.parse_detail(detail, "42")
    assert reading.price == 94 and reading.dead is False
    assert reading.original_price == 128
    assert reading.published_at == datetime(2026, 10, 10, 1, 16, 28)   # UTC


def test_seed_original_price_only_fills_an_earlier_gap():
    """发布价只在没有更早记录时补一条; 已有历史就绝不插队。"""
    from xianyu_crawler.storage.db import make_session

    s = make_session("sqlite:///:memory:", create=True)
    repo.upsert_item_with_price(s, Item(item_id="p1", price=900, title="t", url="u"), source="search")
    assert repo.seed_original_price(s, "p1", 1200, datetime(2026, 10, 10)) is True
    assert repo.seed_original_price(s, "p1", 1200, datetime(2026, 10, 11)) is False
    assert [point.price for point in repo.price_history(s, "p1")] == [1200, 900]


def test_local_save_and_price_refresh_only_due_items(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "DB_URL", f"sqlite:///{tmp_path / 'favorites.db'}")
    monkeypatch.setenv("XIANYU_SSO_ENABLED", "false")
    with runtime.session() as db:
        for item_id in ("123", "456"):
            item = Item(item_id=item_id, price=1000, title="票",
                        url=f"https://www.goofish.com/item?id={item_id}")
            repo.create_recommendation(db, item, "票", ok=True)
    with TestClient(app) as client:
        for item_id in ("123", "456"):
            assert client.post(f"/api/recommendations/{item_id}/approve").json() == {"ok": True}
        assert len(client.get("/api/favorites").json()) == 2
        assert client.get("/api/recommendations").json() == []

    visited = []

    def probe(_ctx, item_id):
        visited.append(item_id)
        return liveness.DetailReading(price=800) if item_id == "123" else liveness.DetailReading()

    monkeypatch.setattr(liveness, "check_detail", probe)
    with runtime.session() as db:
        settings = Settings(liveness_max_checks=1, min_drop_abs=20)
        assert service.refresh_local_favorites(None, db, settings) == 1
        assert service.refresh_local_favorites(None, db, settings) == 0
        assert service.refresh_local_favorites(None, db, settings) == 0
        assert visited == ["123", "456"]
        dropped = db.get(ItemRow, "123")
        unknown = db.get(ItemRow, "456")
        assert dropped is not None and dropped.local_saved and not dropped.favorited
        assert dropped.latest_price == 800 and dropped.reduce_price == 200
        assert unknown is not None and not unknown.dead and unknown.latest_price == 1000
        assert [event.type for event in repo.recent_events(db)] == ["price_drop"]
