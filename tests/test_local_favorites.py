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
        return (800, False) if item_id == "123" else (None, False)

    monkeypatch.setattr(liveness, "check_detail_price", probe)
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
