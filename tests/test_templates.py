"""模板与属性: 抽取清洗、统计口径、条件 kind 往返。"""
from datetime import datetime

from fastapi.testclient import TestClient

from xianyu_crawler import review, trend
from xianyu_crawler.storage import repo
from xianyu_crawler.storage.db import make_session
from xianyu_crawler.web import runtime
from xianyu_crawler.web.app import app


def test_ticket_attrs_are_extracted_and_sanitised():
    raw = ('[{"i":0,"ok":true,"reason":"内场","attrs":'
           '{"seat":"内场","qty":2,"bundle":false,"deposit":false,"unit":"合计","junk":"x"}}]')
    verdict = review._parse_verdict(raw)
    assert verdict.ok is True
    assert verdict.attrs == {"seat": "内场", "qty": 2, "bundle": False,
                             "deposit": False, "unit": "合计"}


def test_attrs_dropped_when_model_makes_them_up():
    """越界的张数、不认识的席种/单位都不收; 全不合法就没有 attrs。"""
    verdict = review._parse_verdict('[{"i":0,"ok":true,"reason":"x",'
                                    '"attrs":{"seat":"舞台","qty":99,"unit":"每人"}}]')
    assert verdict.attrs is None


def test_general_template_returns_no_attrs():
    verdict = review._parse_verdict('[{"i":0,"ok":true,"reason":"x"}]')
    assert verdict.attrs is None


def test_bundle_and_deposit_are_not_comparable():
    assert trend.is_comparable(None) is True
    assert trend.is_comparable({"seat": "内场", "qty": 1}) is True
    # 两张一起出但标的是单张价 → 仍然可比; 说不清单价才剔除
    assert trend.is_comparable({"qty": 2, "unit": "单张"}) is True
    assert trend.is_comparable({"qty": 2}) is False
    assert trend.is_comparable({"qty": 2, "unit": "合计"}) is False
    assert trend.is_comparable({"bundle": True}) is False
    assert trend.is_comparable({"deposit": True}) is False
    assert trend.is_comparable({"unit": "合计"}) is False


def test_min_and_median_skip_non_comparable_listings():
    """捆绑票照样画线, 但不进最低价/中位数。"""
    rows = [
        ("a", "单票", datetime(2026, 11, 21, 10), 1000),
        ("b", "捆绑两张", datetime(2026, 11, 21, 10), 400),
    ]
    data = trend.build(rows, mode="all", comparable_ids={"a"})
    assert data["series"][-1]["min"] == 1000
    assert data["series"][-1]["count"] == 1
    assert data["items_total"] == 2          # 线还是要画出来


def test_watch_kind_round_trips_through_api(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "DB_URL", f"sqlite:///{tmp_path / 'kind.db'}")
    monkeypatch.setenv("XIANYU_SSO_ENABLED", "false")
    with TestClient(app) as client:
        created = client.post("/api/watches", json={"name": "票", "keywords": ["x"], "kind": "ticket"})
        assert created.status_code == 200
        assert created.json()["kind"] == "ticket"
        listed = client.get("/api/watches").json()
        assert listed[0]["kind"] == "ticket"
        # 不传 kind 的老请求按通用处理
        plain = client.post("/api/watches", json={"name": "货", "keywords": ["y"]})
        assert plain.json()["kind"] == "general"


def test_ticket_watch_backfills_attrs_for_known_items(monkeypatch):
    """票务条件会给库里还没属性的商品补抽一次, 每轮限量。"""
    from xianyu_crawler import service
    from xianyu_crawler.config import Watch
    from xianyu_crawler.models import Item

    s = make_session("sqlite:///:memory:", create=True)
    repo.add_watch(s, name="票", keywords='["x"]', requirement="只多内场", kind="ticket")
    watch = repo.list_watches(s)[0]
    repo.create_recommendation(s, Item(item_id="k1", title="内场票", url="u", price=1000), "票", ok=True)
    repo.save_watch_match(s, watch.id, Item(item_id="k1", title="内场票", url="u", price=1000), True, None)

    monkeypatch.setattr(service, "_search", lambda ctx, w, st: [])
    monkeypatch.setattr(review, "review_items",
                        lambda its, req, st, **_: [review.ReviewVerdict(
                            ok=True, attrs={"seat": "内场", "qty": 1}) for _ in its])
    from xianyu_crawler.config import Settings
    settings = Settings(review_enabled=True)
    result = service.scan_recommendations(None, s, settings,
                                          [Watch(id=watch.id, name="票", keywords=["x"],
                                                 requirement="只多内场", kind="ticket")])
    assert result.backfilled == 1
    assert repo.item_attrs_of(s, "k1") == {"seat": "内场", "qty": 1}


def test_general_watch_does_not_backfill(monkeypatch):
    from xianyu_crawler import service
    from xianyu_crawler.config import Settings, Watch
    from xianyu_crawler.models import Item

    s = make_session("sqlite:///:memory:", create=True)
    repo.add_watch(s, name="货", keywords='["x"]', requirement="要全新的", kind="general")
    watch = repo.list_watches(s)[0]
    repo.create_recommendation(s, Item(item_id="k2", title="相机", url="u", price=1000), "货", ok=True)
    repo.save_watch_match(s, watch.id, Item(item_id="k2", title="相机", url="u", price=1000), True, None)
    monkeypatch.setattr(service, "_search", lambda ctx, w, st: [])
    monkeypatch.setattr(review, "review_items",
                        lambda its, req, st, **_: [review.ReviewVerdict(
                            ok=True, attrs={"seat": "内场"}) for _ in its])
    service.scan_recommendations(None, s, Settings(review_enabled=True),
                                 [Watch(id=watch.id, name="货", keywords=["x"], requirement="要全新的")])
    assert repo.item_attrs_of(s, "k2") is None      # 通用条件不抽票务字段


def test_watch_row_to_watch_keeps_kind():
    """抓取走 watchrow_to_watch 这条映射; 漏拷 kind 会让票务模板永远不生效。"""
    from xianyu_crawler import service

    s = make_session("sqlite:///:memory:", create=True)
    repo.add_watch(s, name="票", keywords='["x"]', requirement="内场", kind="ticket")
    row = repo.list_watches(s)[0]
    assert service.watchrow_to_watch(row).kind == "ticket"


def test_attrs_persist_on_item():
    from xianyu_crawler.models import Item
    from xianyu_crawler.storage.orm import ItemRow

    s = make_session("sqlite:///:memory:", create=True)
    repo.create_recommendation(s, Item(item_id="t1", title="内场票", url="u", price=1000,
                                       attrs={"seat": "内场", "qty": 1}), "票", ok=True)
    assert repo.item_attrs(s, []) == {}
    row = s.get(ItemRow, "t1")
    assert row is not None and row.attrs and "内场" in row.attrs
