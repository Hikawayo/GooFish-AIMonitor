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


def test_config_validation_and_folder_crud(client):
    # 全员数值校验 + 中文字段名 + min<=max
    r_bad = client.put("/api/config", json={"schedule_minutes": 0})
    assert r_bad.status_code == 422 and "推荐抓取间隔" in r_bad.json()["detail"]
    r_delay = client.put("/api/config", json={"action_delay_min": 10, "action_delay_max": 3})
    assert r_delay.status_code == 422 and "下限不能大于上限" in r_delay.json()["detail"]

    # 文件夹改名与删除(删除时把关联条件的 folder_id 置空)
    f = client.post("/api/watch-folders", json={"name": "旧组名"}).json()
    w = client.post("/api/watches", json={"name": "测试条件", "folder_id": f["id"]}).json()
    assert w["folder_id"] == f["id"]
    renamed = client.put(f"/api/watch-folders/{f['id']}", json={"name": "新组名"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "新组名"
    assert client.delete(f"/api/watch-folders/{f['id']}").status_code == 200
    assert client.get("/api/watch-folders").json() == []
    assert client.get("/api/watches").json()[0]["folder_id"] is None


def test_price_history_dedup_drop_dedup_and_notify_safety(tmp_path, monkeypatch):
    from xianyu_crawler import notifier
    from xianyu_crawler.config import Settings
    from xianyu_crawler.models import Item
    from xianyu_crawler.storage import repo
    from xianyu_crawler.storage.db import make_session
    from xianyu_crawler.web import runner

    s = make_session(f"sqlite:///{tmp_path / 'p1.db'}", create=True)
    # 价格不变不重复写 PriceHistory
    it = Item(item_id="same", title="测试", url="u", price=100.0)
    repo.upsert_item_with_price(s, it, source="search")
    repo.upsert_item_with_price(s, it, source="search")
    assert [p.price for p in repo.price_history(s, "same")] == [100.0]
    repo.upsert_item_with_price(s, it.model_copy(update={"price": 90.0}), source="search")
    assert [p.price for p in repo.price_history(s, "same")] == [100.0, 90.0]

    # 降价去重: 低于上次通知价才再发
    repo.add_event(s, "same", "price_drop", {"curr_price": 90.0, "drop_abs": 10.0})
    assert repo.has_drop_event_at_price(s, "same", 90.0) is True
    assert repo.has_drop_event_at_price(s, "same", 95.0) is True
    assert repo.has_drop_event_at_price(s, "same", 80.0) is False

    # 邮件发送失败时不提前写 CSV, 避免下轮重试重复追加
    st = Settings(data_dir=tmp_path)
    monkeypatch.setattr(notifier, "send_email", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("smtp down")))
    try:
        runner._notify(s, st)  # noqa: SLF001
    except RuntimeError:
        pass
    assert not (tmp_path / "events.csv").exists()

    # 登录失效邮件去重: 只发一次
    sent: list[str] = []
    monkeypatch.setattr(notifier, "send_email", lambda _st, subj, _body, *_a: sent.append(subj))
    runner._send_login_expired_mail(s, st, "expired")  # noqa: SLF001
    runner._send_login_expired_mail(s, st, "expired")  # noqa: SLF001
    assert len(sent) == 1
    s.close()


def test_target_price_revive_manual_favorite_digest_and_backup(client, tmp_path, monkeypatch):
    from xianyu_crawler import service
    from xianyu_crawler.config import Settings
    from xianyu_crawler.models import Item
    from xianyu_crawler.storage import backup, repo
    from xianyu_crawler.web import runtime

    # 手动粘贴链接 / 纯数字 ID 加入监控
    assert client.post("/api/favorites/manual", json={"url_or_id": "invalid"}).status_code == 422
    r_man = client.post("/api/favorites/manual",
                        json={"url_or_id": "https://www.goofish.com/item?id=9876543210"})
    assert r_man.status_code == 200 and r_man.json()["item_id"] == "9876543210"
    assert any(f["item_id"] == "9876543210" for f in client.get("/api/favorites").json())

    # 目标价提醒 + 归档跳过 + 已下架商品重新出现恢复在售
    w = client.post("/api/watches", json={
        "name": "对邦票", "keywords": ["对邦"], "kind": "ticket", "target_price": 1000,
    }).json()
    w_arch = client.post("/api/watches", json={
        "name": "旧演出", "keywords": ["旧"], "archived": True,
    }).json()
    assert w["target_price"] == 1000 and w_arch["archived"] is True

    listing = Item(item_id="tp1", title="对邦内场", url="https://www.goofish.com/item?id=tp1", price=900)
    monkeypatch.setattr(service, "_search", lambda *a: [listing])
    with runtime.session() as db:
        watches = [service.watchrow_to_watch(row) for row in repo.list_watches(db)]
        res = service.scan_recommendations(None, db, Settings(review_enabled=False), watches)
        assert res.created == 1
        # 目标价事件触发且只记一条(归档条件未扫描)
        tp_events = [e for e in repo.recent_events(db) if e.type == "target_price"]
        assert len(tp_events) == 1
        # 标记死链后再次在搜索中出现 → 恢复在售
        repo.mark_dead(db, "tp1", "已下架")
        assert repo.is_dead(db, "tp1") is True
        service.scan_recommendations(None, db, Settings(review_enabled=False), watches)
        assert repo.is_dead(db, "tp1") is False

    # 趋势简报(无 LLM Key 时返回客观统计摘要)
    dg = client.post("/api/digest", json={"watch_ids": [w["id"]], "use_llm": False}).json()
    assert dg["used_llm"] is False and "对邦票" in dg["summary"]

    # SQLite 在线备份
    db_file = tmp_path / "sample.db"
    from xianyu_crawler.storage.db import make_session
    s2 = make_session(f"sqlite:///{db_file}", create=True)
    s2.close()
    dest = backup.backup_sqlite(db_file)
    assert dest is not None and dest.is_file()
