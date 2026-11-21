import base64
import hashlib
import hmac
import json
import threading
import time

from fastapi.testclient import TestClient

from xianyu_crawler import service
from xianyu_crawler.models import Item
from xianyu_crawler.storage import repo
from xianyu_crawler.storage.orm import WatchMatch
from xianyu_crawler.web import runner, runtime
from xianyu_crawler.web.app import app


def test_public_catalog_and_private_account_resources(tmp_path, monkeypatch):
    key = b"local-test-goofish-key-more-than-32-bytes"
    owner_email = "owner@example.test"
    member_email = "member@example.test"
    owner_scope = hashlib.sha256(owner_email.encode()).hexdigest()
    member_scope = hashlib.sha256(member_email.encode()).hexdigest()
    monkeypatch.setenv("XIANYU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("XIANYU_SSO_ENABLED", "true")
    monkeypatch.setenv("XIANYU_SSO_OWNER_SCOPE", owner_scope)
    monkeypatch.setenv("XIANYU_REVIEW_API_TOKEN", "owner-fallback")
    monkeypatch.setattr(runtime, "DB_URL", f"sqlite:///{tmp_path / 'xianyu.db'}")
    (tmp_path / "sso.key").write_bytes(key)
    (tmp_path / "storage_state.json").write_text('{"cookies":[]}')

    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    def auth(email: str, aud: str = "goofish") -> dict[str, str]:
        payload = encode(json.dumps({"e": email, "aud": aud, "exp": time.time() + 60}).encode())
        signature = encode(hmac.digest(key, payload.encode(), "sha256"))
        return {"sso": f"{payload}.{signature}"}

    with TestClient(app, cookies=auth(owner_email)) as owner, TestClient(
        app, cookies=auth(member_email)
    ) as member, TestClient(app) as anonymous:
        assert anonymous.get("/api/shared").status_code == 401
        anonymous.cookies.update(auth(owner_email, aud="other-app"))
        assert anonymous.get("/api/config").status_code == 401
        assert owner.get("/api/login/status").json()["has_state"] is True
        assert member.get("/api/login/status").json()["has_state"] is False
        assert member.post("/api/run").status_code == 409
        assert member.post("/api/test-review").status_code == 409
        assert member.put("/api/config", json={
            "review_base_url": "http://127.0.0.1:8080/v1",
        }).status_code == 422
        assert member.put("/api/config", json={
            "review_api_token": "member-own-key", "review_base_url": "https://api.deepseek.com",
        }).json()["review_token_set"]
        assert "member-own-key" not in member.get("/api/config").text

        folder = owner.post("/api/watch-folders", json={"name": "对邦"}).json()
        public_body = {"name": "团名查询", "public": True, "folder_id": folder["id"]}
        public_id = owner.post("/api/watches", json=public_body).json()["id"]
        private_id = owner.post("/api/watches", json={"name": "私密商品"}).json()["id"]
        assert member.get("/api/watches").json() == []
        assert member.get("/api/watch-folders").json() == []
        assert member.put(f"/api/watches/{private_id}", json={"name": "尝试篡改"}).status_code == 404
        assert member.get("/api/recommendations").json() == []
        assert member.get("/api/favorites").json() == []

        listing = Item(item_id="same-id", title="本场门票", url="https://www.goofish.com/item?id=same-id", price=100,
                       seller_nick="卖家别名", pic_url="https://example.test/cover.jpg")
        with runtime.use_scope(runtime.OWNER), runtime.session() as db:
            repo.create_recommendation(db, listing, public_body["name"], reason="符合", ok=True)
            repo.save_watch_match(db, private_id, listing.model_copy(update={"price": 80}), True, "私密条件")
            repo.upsert_item_with_price(db, listing.model_copy(update={"price": 80}), source="search")
            repo.save_watch_match(db, public_id, listing, True, "私有审核理由")
            ignored = listing.model_copy(update={"item_id": "ignored"})
            repo.create_recommendation(db, ignored, public_body["name"], ok=True)
            repo.save_watch_match(db, public_id, ignored, True, None)
            repo.set_rec_status(db, ignored.item_id, "rejected")
            repo.mark_favorited(db, listing.item_id)
        catalog = member.get("/api/shared")
        assert catalog.headers["Cache-Control"] == "no-store"
        [published] = catalog.json()
        assert published["name"] == "对邦"
        [entry] = published["items"]
        assert entry["price"] == 100
        assert entry["seller_nick"] == listing.seller_nick
        assert entry["pic_url"] == listing.pic_url
        public_prices = f"/api/shared/{published['id']}/same-id/prices"
        assert [point["price"] for point in member.get(public_prices).json()] == [100]
        assert [point["price"] for point in owner.get("/api/items/same-id/prices").json()] == [100, 80]
        assert member.get("/api/items/same-id/prices").status_code == 404
        with runtime.use_scope(runtime.OWNER), runtime.session() as db:
            repo.save_watch_match(db, public_id, listing.model_copy(update={"price": 90}), True, "符合")
        assert [point["price"] for point in member.get(public_prices).json()] == [100, 90]
        for private in ("私密商品", "私密条件", "私有审核理由", owner_email):
            assert private not in catalog.text
        assert member.post(f"/api/shared/{published['id']}/same-id/favorite").json() == {"ok": True}
        assert member.get("/api/favorites").json()[0]["item_id"] == listing.item_id
        assert member.get("/api/login/status").json()["has_state"] is False
        assert owner.put(f"/api/watches/{public_id}", json=dict(public_body, name="改名后")).status_code == 200
        assert member.get("/api/shared").json()[0]["id"] == published["id"]
        assert owner.put(f"/api/watches/{public_id}", json=dict(public_body, public=False)).status_code == 200
        assert member.get("/api/shared").json() == []
        assert member.get(public_prices).status_code == 404
        assert member.post(f"/api/shared/{published['id']}/same-id/favorite").status_code == 404
        assert owner.put(f"/api/watches/{public_id}", json=public_body).status_code == 200
        assert [point["price"] for point in member.get(public_prices).json()] == [90]

        (tmp_path / "users" / member_scope / "storage_state.json").write_text('{"cookies":[]}')
        invoked = threading.Event()
        recorded = {}

        def crawl(_watch):
            with runtime.session() as db:
                settings = runtime.effective_settings(repo.get_config(db))
                recorded.update(scope=runtime.scope(), key=settings.review_api_token, path=settings.data_dir)
            invoked.set()

        monkeypatch.setattr(runner, "crawl", crawl)
        assert member.post("/api/run").json()["status"] == "queued"
        assert invoked.wait(5)
        assert recorded == {
            "scope": member_scope, "key": "member-own-key", "path": tmp_path / "users" / member_scope,
        }


def test_member_without_api_key_can_search_after_disabling_ai_review(tmp_path, monkeypatch):
    from xianyu_crawler.config import Settings

    monkeypatch.setenv("XIANYU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("XIANYU_SSO_ENABLED", "true")
    with runtime.use_scope("b" * 64):
        no_key = Settings(review_enabled=True, review_api_token=None)
        assert runtime.search_block_reason(no_key) == "请先扫码登录闲鱼"
        runtime.data_dir().mkdir(parents=True, exist_ok=True)
        (runtime.data_dir() / "storage_state.json").write_text('{"cookies":[]}')
        assert runtime.can_search(no_key) is False
        reason = runtime.search_block_reason(no_key)
        assert reason is not None and "AI API Key" in reason
        manual = Settings(review_enabled=False, review_api_token=None)
        assert runtime.can_search(manual) is True
        assert runtime.search_block_reason(manual) is None


def test_same_item_can_be_reviewed_in_two_folders_and_refresh_price(tmp_path, monkeypatch):
    from xianyu_crawler.config import Settings
    from xianyu_crawler.storage.db import make_session

    db = make_session(f"sqlite:///{tmp_path / 'test.db'}", create=True)
    first = repo.add_watch(db, name="对邦")
    second = repo.add_watch(db, name="棉花娃娃")
    listing = Item(item_id="common", title="商品", url="https://www.goofish.com/item?id=1", price=100)
    monkeypatch.setattr(service, "_search", lambda *args: [listing])
    watches = [service.watchrow_to_watch(first), service.watchrow_to_watch(second)]
    service.scan_recommendations(None, db, Settings(), watches)
    assert repo.item_watch_ids(db)[listing.item_id] == [first.id, second.id]
    listing.price = 80
    service.scan_recommendations(None, db, Settings(), [watches[0]])
    first_match = db.get(WatchMatch, (first.id, listing.item_id))
    second_match = db.get(WatchMatch, (second.id, listing.item_id))
    assert first_match is not None and first_match.price == 80
    assert second_match is not None and second_match.price == 100
    db.close()
