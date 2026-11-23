"""仅从公开条件读取已确认匹配的行情，不序列化账号或条件配置。"""
from __future__ import annotations

import hashlib
import json
import threading
import time

from datetime import datetime

from sqlalchemy import or_, select

from . import dto, runtime
from ..models import Item
from ..review import REVIEW_NOT_RUN
from ..storage import repo
from ..storage.orm import Event, ItemRow, PublishedPrice, WatchFolder, WatchMatch, WatchRow

_CACHE_TTL_S = 10.0
_CACHE_LOCK = threading.Lock()
_CATALOG_CACHE: dict[str, tuple[float, list[dict]]] = {}


def invalidate() -> None:
    """公开条件/文件夹变更或抓取结束后清缓存。"""
    with _CACHE_LOCK:
        _CATALOG_CACHE.clear()


def folder_key(user_scope: str, watch: WatchRow) -> str:
    identifier = f"folder:{watch.folder_id}" if watch.folder_id is not None else f"watch:{watch.id}"
    return hashlib.sha256(f"{user_scope}:{identifier}".encode()).hexdigest()


def _visible_matches(watch_ids):
    return (
        select(WatchMatch, ItemRow).join(ItemRow, WatchMatch.item_id == ItemRow.item_id)
        .join(WatchRow, WatchMatch.watch_id == WatchRow.id)
        .where(WatchMatch.watch_id.in_(watch_ids), WatchRow.public.is_(True), WatchMatch.ok.is_(True),
               or_(WatchMatch.reason.is_(None), WatchMatch.reason != REVIEW_NOT_RUN),
               or_(WatchRow.requirement.is_(None), WatchRow.requirement == "", WatchMatch.reason.is_not(None)),
               or_(ItemRow.rec_status.is_(None), ItemRow.rec_status != "rejected"),
               or_(ItemRow.muted_until.is_(None), ItemRow.muted_until <= repo._now()),
               WatchMatch.title.is_not(None), WatchMatch.url.is_not(None), ItemRow.dead.is_(False))
    )


def catalog() -> list[dict]:
    caller = runtime.scope()
    now = time.monotonic()
    with _CACHE_LOCK:
        hit = _CATALOG_CACHE.get(caller)
        if hit is not None and now - hit[0] < _CACHE_TTL_S:
            return hit[1]
    folders: dict[str, dict] = {}
    scopes = runtime.scopes() if runtime.shared_mode() else [caller]
    for user_scope in scopes:
        with runtime.use_scope(user_scope), runtime.session() as db:
            published = db.execute(
                select(WatchRow, WatchFolder.name).outerjoin(WatchFolder, WatchRow.folder_id == WatchFolder.id)
                .where(WatchRow.public.is_(True)).order_by(WatchRow.id)
            ).all()
            published_ids = {}
            for watch, folder_name in published:
                key = folder_key(user_scope, watch)
                published_ids[watch.id] = key
                folders.setdefault(key, {
                    "id": key, "name": folder_name or watch.name, "items": {}, "watches": [],
                })
                if caller == user_scope:
                    folders[key]["watches"].append(watch.id)
            if not published_ids:
                continue
            matches = db.execute(
                _visible_matches(published_ids).order_by(WatchMatch.observed_at.desc())
            )
            for match, item in matches:
                results = folders[published_ids[match.watch_id]]["items"]
                results.setdefault(item.item_id, {
                    "item_id": item.item_id, "title": match.title, "url": match.url,
                    "price": match.price, "observed_at": dto._iso(match.observed_at),
                    "pic_url": item.pic_url, "seller_nick": item.seller_nick,
                    "publish_time": dto._iso(item.publish_time),
                    # 席种等属性由挂牌文字推出, 公开行情一并展示
                    "attrs": json.loads(item.attrs) if item.attrs else None,
                })
    result = [dict(folder, items=list(folder["items"].values())) for folder in folders.values()]
    with _CACHE_LOCK:
        _CATALOG_CACHE[caller] = (time.monotonic(), result)
    return result


def public_drop_events(limit: int = 30) -> list[dict]:
    """收集公开组内已可见商品的降价事件(排除当前用户自己的库, 避免与本人事件重复)。"""
    if not runtime.shared_mode():
        return []
    caller = runtime.scope()
    out: list[dict] = []
    for user_scope in runtime.scopes():
        if user_scope == caller:
            continue
        with runtime.use_scope(user_scope), runtime.session() as db:
            pub_ids = list(db.scalars(select(WatchRow.id).where(WatchRow.public.is_(True))))
            if not pub_ids:
                continue
            visible_item_ids = {row[1].item_id for row in db.execute(_visible_matches(pub_ids))}
            if not visible_item_ids:
                continue
            evs = db.scalars(
                select(Event)
                .where(Event.type == "price_drop", Event.item_id.in_(visible_item_ids))
                .order_by(Event.created_at.desc())
                .limit(limit)
            )
            for e in evs:
                payload = json.loads(e.payload)
                out.append({
                    "item_id": e.item_id,
                    "type": e.type,
                    "payload": {
                        "title": payload.get("title"),
                        "url": payload.get("url"),
                        "prev_price": payload.get("prev_price"),
                        "curr_price": payload.get("curr_price"),
                        "drop_abs": payload.get("drop_abs"),
                        "public": True,
                    },
                    "created_at": dto._iso(e.created_at),
                })
    out.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return out[:limit]


def price_history(key: str, item_id: str) -> list[dict] | None:
    scopes = runtime.scopes() if runtime.shared_mode() else [runtime.scope()]
    for user_scope in scopes:
        with runtime.use_scope(user_scope), runtime.session() as db:
            ids = [watch.id for watch in db.scalars(select(WatchRow).where(WatchRow.public.is_(True)))
                   if folder_key(user_scope, watch) == key]
            if not ids:
                continue
            matches = list(db.scalars(_visible_matches(ids).where(WatchMatch.item_id == item_id)))
            if not matches:
                return None
            points = db.scalars(
                select(PublishedPrice).where(PublishedPrice.watch_id.in_(m.watch_id for m in matches),
                                             PublishedPrice.item_id == item_id)
                .order_by(PublishedPrice.observed_at.desc(), PublishedPrice.id.desc()).limit(500)
            )
            unique = {}
            for point in points:
                unique.setdefault((point.observed_at, point.price), {
                    "price": point.price, "observed_at": dto._iso(point.observed_at),
                })
            if unique:
                return list(reversed(unique.values()))
            active = max(matches, key=lambda match: match.observed_at)
            return [{"price": active.price, "observed_at": dto._iso(active.observed_at)}]
    return None


def get_item(folder_key: str, item_id: str) -> Item | None:
    for folder in catalog():
        if folder["id"] == folder_key:
            for item in folder["items"]:
                if item["item_id"] == item_id:
                    published = item["publish_time"]
                    return Item(item_id=item_id, title=item["title"], url=item["url"], price=item["price"],
                                pic_url=item["pic_url"], seller_nick=item["seller_nick"],
                                publish_time=datetime.fromisoformat(published).replace(tzinfo=None) if published else None)
    return None
