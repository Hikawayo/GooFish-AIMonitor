import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from xianyu_crawler.web import runtime, app as app_mod
    runtime.set_db_url(f"sqlite:///{tmp_path}/t.db")
    return TestClient(app_mod.app)


def test_watch_crud_api(client):
    r = client.post("/api/watches", json={"name": "w1", "keywords": ["iPhone"], "price_max": 5000})
    assert r.status_code == 200
    wid = r.json()["id"]
    assert client.get("/api/watches").json()[0]["name"] == "w1"
    r2 = client.put(f"/api/watches/{wid}",
                    json={"name": "w1", "keywords": ["iPhone", "苹果"], "price_max": 4000, "enabled": False})
    assert r2.json()["price_max"] == 4000 and r2.json()["enabled"] is False
    assert client.delete(f"/api/watches/{wid}").json()["ok"] is True
    assert client.get("/api/watches").json() == []


def test_config_api(client):
    assert "notify_to" in client.get("/api/config").json()   # 默认空, 走本地配置
    r = client.put("/api/config", json={"schedule_minutes": 60, "paused": True})
    assert r.json()["schedule_minutes"] == 60 and r.json()["paused"] is True


def test_recommendations_api(client):
    from xianyu_crawler.web import runtime
    from xianyu_crawler.storage import repo
    from xianyu_crawler.models import Item
    s = runtime.session()
    repo.create_recommendation(
        s, Item(item_id="x1", title="t", url="u", price=1000, location="上海",
                free_shipping=True), "w1")
    repo.update_item_stats(s, "x1", browse_count=134, collect_count=3, want_count=4)
    recs = client.get("/api/recommendations").json()
    assert len(recs) == 1 and recs[0]["item_id"] == "x1"
    assert recs[0]["location"] == "上海" and recs[0]["free_shipping"] is True
    # 浏览/收藏/想要次数透传到前端
    assert recs[0]["browse_count"] == 134 and recs[0]["collect_count"] == 3 and recs[0]["want_count"] == 4
    assert client.post("/api/recommendations/x1/reject").json()["ok"] is True
    assert client.get("/api/recommendations").json() == []


def test_run_rejected_while_busy(client, monkeypatch):
    """浏览器作业串行: 正在抓取时再点运行要明确回 409, 而不是静默跳过。"""
    from xianyu_crawler.web import runner

    monkeypatch.setattr(runner, "busy", lambda: True)
    response = client.post("/api/run")
    assert response.status_code == 409
    assert "抓取中" in response.json()["detail"]


def test_price_trend_api(client):
    """条件内价格总览: 分桶、最低价、空条件、非法粒度。"""
    from datetime import datetime

    from sqlalchemy import delete

    from xianyu_crawler.models import Item
    from xianyu_crawler.storage import repo
    from xianyu_crawler.storage.orm import PriceHistory
    from xianyu_crawler.web import runtime

    s = runtime.session()
    watch = repo.add_watch(s, name="w", keywords='["x"]')
    item = Item(item_id="i1", title="t", url="u", price=100)
    repo.create_recommendation(s, item, "w")
    repo.save_watch_match(s, watch.id, item, None, None)
    junk = Item(item_id="i2", title="兑换码", url="u", price=3)
    repo.create_recommendation(s, junk, "w")
    repo.save_watch_match(s, watch.id, junk, False, "不符")   # AI 判否 → 不进走势
    s.add_all([PriceHistory(item_id="i1", price=price, observed_at=datetime(2026, 11, 20, hour))
               for hour, price in ((1, 100), (5, 90))])
    s.add(PriceHistory(item_id="i2", price=3, observed_at=datetime(2026, 11, 20, 2)))
    # 建推荐时补的「现在」这一条会多出一个桶, 删掉只留上面几条
    s.execute(delete(PriceHistory).where(PriceHistory.observed_at > datetime(2026, 11, 21)))
    s.commit()

    body = client.get(f"/api/price-trend?watch_ids={watch.id}&mode=day&tz=480").json()
    assert body["mode"] == "day" and len(body["series"]) == 1
    assert body["series"][0]["min"] == 90 and body["series"][0]["count"] == 1
    assert [entry["item_id"] for entry in body["items"]] == ["i1"]
    assert body["from"] and body["from"].endswith("+00:00")

    assert client.get("/api/price-trend?watch_ids=999").json()["series"] == []
    assert client.get(f"/api/price-trend?watch_ids={watch.id}&mode=year").status_code == 422
    assert client.get("/api/price-trend").status_code == 422


def test_status_and_favorites_empty(client):
    assert client.get("/api/status").json()["running"] is False
    assert client.get("/api/favorites").json() == []
    assert client.get("/api/events").json() == []


def test_test_review_endpoint_ok(client, monkeypatch):
    from xianyu_crawler import review
    monkeypatch.setattr(review, "_call_llm", lambda msgs, st: '[{"i":0,"ok":true,"reason":"符合"}]')
    body = client.post("/api/test-review").json()
    assert body["ok"] is True


def test_test_review_endpoint_reports_error(client, monkeypatch):
    import httpx
    from xianyu_crawler import review
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp = httpx.Response(401, request=req)

    def boom(msgs, st):
        raise httpx.HTTPStatusError("Unauthorized", request=req, response=resp)

    monkeypatch.setattr(review, "_call_llm", boom)
    body = client.post("/api/test-review").json()
    assert body["ok"] is False and "401" in body["error"]


def test_rereview_endpoint(client, monkeypatch):
    from xianyu_crawler import review
    from xianyu_crawler.web import runtime
    from xianyu_crawler.storage import repo
    from xianyu_crawler.models import Item
    s = runtime.session()
    repo.add_watch(s, name="w", keywords='["x"]', requirement="必须 M1 Pro")
    repo.create_recommendation(s, Item(item_id="a", title="M1 Pro 机", url="u", price=7000),
                               "w", reason=review.REVIEW_NOT_RUN, ok=True)
    monkeypatch.setattr(review, "review_items",
                        lambda items, req, st: [review.ReviewVerdict(ok=False, reason="不符") for _ in items])
    body = client.post("/api/recommendations/review").json()
    assert body["ok"] is True and body["reviewed"] == 1 and body["rejected"] == 1
    assert client.get("/api/recommendations?status=new").json()[0]["rec_ok"] is False
