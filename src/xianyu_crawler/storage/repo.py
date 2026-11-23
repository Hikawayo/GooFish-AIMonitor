"""仓储: 纯 DB 操作, 可独立测试。"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, or_, func, delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Item
from .orm import ItemRow, PriceHistory, PublishedPrice, Event, WatchRow, WatchMatch, AppConfig
from ..review import REVIEW_NOT_RUN


def _now() -> datetime:
    # naive UTC: SQLite 读回的 datetime 一律无 tzinfo, 统一成 naive 才能安全比较/排序
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_latest_price(s: Session, item_id: str) -> float | None:
    row = s.get(ItemRow, item_id)
    return row.latest_price if row else None


def get_reduce_price(s: Session, item_id: str) -> float | None:
    row = s.get(ItemRow, item_id)
    return row.reduce_price if row else None


def upsert_item_with_price(s: Session, item: Item, source: str,
                           watch_name: str | None = None) -> float | None:
    """写入/更新商品并追加一条价格观测; 返回更新前的 latest_price(无则 None)。"""
    reduce = item.reduce_price or 0.0
    attrs = json.dumps(item.attrs, ensure_ascii=False) if item.attrs else None
    row = s.get(ItemRow, item.item_id)
    prev = row.latest_price if row else None
    created = row is None
    if created:
        row = ItemRow(item_id=item.item_id, title=item.title, url=item.url,
                      seller_id=item.seller_id, seller_nick=item.seller_nick,
                      location=item.location, condition=item.condition,
                      free_shipping=item.free_shipping, pic_url=item.pic_url,
                      first_price=item.price, latest_price=item.price,
                      reduce_price=reduce, source=source, watch_name=watch_name,
                      publish_time=item.publish_time, attrs=attrs,
                      dead=item.dead, dead_reason=item.dead_reason,
                      dead_at=_now() if item.dead else None)
        s.add(row)
    else:
        if prev is not None and item.price != prev:   # 价格变了 → 记调价时间
            row.price_changed_at = _now()
        row.latest_price = item.price
        row.reduce_price = reduce
        row.location = item.location
        row.condition = item.condition
        row.free_shipping = item.free_shipping
        row.pic_url = item.pic_url or row.pic_url
        row.seller_nick = item.seller_nick or row.seller_nick
        if attrs:                                     # 抽到属性才覆盖, 没抽到保留旧的
            row.attrs = attrs
        if item.publish_time and not row.publish_time:   # 补发布时间(收藏源没有)
            row.publish_time = item.publish_time
        row.last_seen_at = _now()
        if item.dead and not row.dead:        # 死链信号是"粘性"的: 一旦死掉就不复活
            row.dead = True
            row.dead_reason = item.dead_reason
            row.dead_at = _now()
    if item.original_price and item.original_price > (row.original_price or 0) \
            and item.original_price > item.price:
        row.original_price = item.original_price      # 平台给的最初挂牌价(详情精确值优先)
    # 首次入库时若知道「卖家最初挂牌价 + 发布时间」, 先补这个起点, 走势才不会从半路开始
    s.add(PriceHistory(item_id=item.item_id, price=item.price))
    s.commit()
    if (item.original_price and item.publish_time and item.original_price > item.price):
        seed_original_price(s, item.item_id, item.original_price, item.publish_time)
    return prev


def mark_favorited(s: Session, item_id: str) -> None:
    row = s.get(ItemRow, item_id)
    if row is None:
        return
    row.favorited = True
    row.favorited_at = _now()
    s.commit()


def is_favorited(s: Session, item_id: str) -> bool:
    row = s.get(ItemRow, item_id)
    return bool(row and row.favorited)


def is_collected(s: Session, item_id: str) -> bool:
    """已在闲鱼收藏(我们点过收藏, 或出现在收藏列表)→ 不再作为推荐。"""
    row = s.get(ItemRow, item_id)
    return bool(row and (row.local_saved or row.favorited or row.source == "favorite"))


def save_local_favorite(s: Session, item_id: str, item: Item | None = None,
                        folder_key: str | None = None) -> bool:
    row = s.get(ItemRow, item_id)
    if row is None and item is not None:
        upsert_item_with_price(s, item, source="shared")
        row = s.get(ItemRow, item_id)
    if row is None:
        return False
    if not row.local_saved:
        row.local_saved = True
        row.favorited_at = row.favorited_at or _now()
        if row.rec_status == "new":
            row.rec_status = "approved"
    if folder_key and not row.shared_folder_key:
        row.shared_folder_key = folder_key
    s.commit()
    return True


def clear_local_favorite(s: Session, item_id: str) -> bool:
    """取消站内收藏: 退回收藏前的状态(回到待审队列), 价格历史保留。

    闲鱼收藏夹同步来的商品不动 —— 那是账号里真实收藏的, 本站无权取消。
    返回是否真的取消了。
    """
    row = s.get(ItemRow, item_id)
    if row is None or not row.local_saved or row.favorited or row.source == "favorite":
        return False
    row.local_saved = False
    row.shared_folder_key = None
    row.favorited_at = None
    if row.rec_status == "approved" and row.rec_ok is not False:
        row.rec_status = "new"
    s.commit()
    return True


def due_local_favorites(s: Session, interval_minutes: int, limit: int) -> list[ItemRow]:
    cutoff = _now() - timedelta(minutes=interval_minutes)
    query = (
        select(ItemRow).where(ItemRow.local_saved.is_(True), ItemRow.dead.is_(False),
                              or_(ItemRow.detail_checked_at.is_(None), ItemRow.detail_checked_at <= cutoff))
        .order_by(ItemRow.detail_checked_at.asc(), ItemRow.favorited_at.asc(), ItemRow.item_id)
        .limit(limit)
    )
    return list(s.scalars(query))


def record_local_price(s: Session, row: ItemRow, price: float) -> None:
    now = _now()
    if price != row.latest_price:
        row.price_changed_at = now
        row.reduce_price = max(row.latest_price - price, 0.0)
    row.latest_price = price
    row.last_seen_at = now
    s.add(PriceHistory(item_id=row.item_id, price=price, observed_at=now))
    s.execute(update(WatchMatch).where(WatchMatch.item_id == row.item_id)
              .values(price=price, observed_at=now))
    for match in s.scalars(select(WatchMatch).where(WatchMatch.item_id == row.item_id)):
        record_published_price(s, match)
    s.commit()


def price_history(s: Session, item_id: str):
    return list(reversed(list(s.scalars(select(PriceHistory).where(PriceHistory.item_id == item_id)
                                        .order_by(PriceHistory.observed_at.desc(), PriceHistory.id.desc())
                                        .limit(500)))))


def set_item_attrs(s: Session, item_id: str, attrs: dict) -> None:
    """只补属性, 不动价格与状态(用于给历史商品补抽席种等)。"""
    row = s.get(ItemRow, item_id)
    if row is None:
        return
    row.attrs = json.dumps(attrs, ensure_ascii=False)
    s.commit()


def set_promo_price(s: Session, item_id: str, promo: float | None,
                    list_price: float | None) -> None:
    """记下平台优惠价(有优惠时同时留挂牌价); 优惠没了就清空。"""
    row = s.get(ItemRow, item_id)
    if row is None:
        return
    row.promo_price = promo
    row.list_price = list_price if promo else None
    s.commit()


def item_attrs_of(s: Session, item_id: str) -> dict | None:
    raw = s.scalar(select(ItemRow.attrs).where(ItemRow.item_id == item_id))
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def item_attrs(s: Session, watch_ids: list[int]) -> dict[str, dict | None]:
    """这些条件下各商品抽取到的属性(没抽到 → None), 用来判断能不能进价格统计。"""
    if not watch_ids:
        return {}
    rows = s.execute(
        select(ItemRow.item_id, ItemRow.attrs)
        .join(WatchMatch, WatchMatch.item_id == ItemRow.item_id)
        .where(WatchMatch.watch_id.in_(watch_ids))
        .distinct()
    ).all()
    out: dict[str, dict | None] = {}
    for item_id, raw in rows:
        try:
            out[str(item_id)] = json.loads(raw) if raw else None
        except ValueError:
            out[str(item_id)] = None
    return out


def trend_rows(s: Session, watch_ids: list[int]):
    """这些条件下「已确认匹配」商品的价格观测(升序), 供 trend.build 聚合。

    只统计 AI 通过或还没人工裁决的匹配(ok 不是 False), 并排除自己忽略掉的商品:
    AI 判否的兑换码、特典本来就不属于目标观测, 不该出现在走势里。
    """
    item_ids = {match.item_id for match in s.scalars(
        select(WatchMatch).where(WatchMatch.watch_id.in_(watch_ids),
                                 or_(WatchMatch.ok.is_(True), WatchMatch.ok.is_(None))))}
    if not item_ids:
        return []
    return s.execute(
        select(PriceHistory.item_id, ItemRow.title, PriceHistory.observed_at, PriceHistory.price)
        .join(ItemRow, ItemRow.item_id == PriceHistory.item_id)
        .where(PriceHistory.item_id.in_(item_ids),
               or_(ItemRow.rec_status.is_(None), ItemRow.rec_status != "rejected"))
        .order_by(PriceHistory.observed_at.asc(), PriceHistory.id.asc())
    ).all()


def seed_original_price(s: Session, item_id: str, price: float, observed_at: datetime) -> bool:
    """把卖家发布时的原价补成这条商品最早的一次观测。

    只在还没有更早记录时插一次: 已有历史就不该拿平台给的原价覆盖或插队。
    """
    earliest = s.scalar(select(func.min(PriceHistory.observed_at))
                        .where(PriceHistory.item_id == item_id))
    if earliest is not None and earliest <= observed_at:
        return False
    s.add(PriceHistory(item_id=item_id, price=price, observed_at=observed_at))
    s.commit()
    return True


def record_published_price(s: Session, match: WatchMatch) -> None:
    watch = s.get(WatchRow, match.watch_id)
    if not watch or not watch.public or match.ok is not True or match.reason == REVIEW_NOT_RUN:
        return
    if watch.requirement and match.reason is None:
        return
    item = s.get(ItemRow, match.item_id)
    if not item or item.dead or item.rec_status == "rejected" or (item.muted_until and item.muted_until > _now()):
        return
    previous = s.scalar(select(PublishedPrice.price)
                        .where(PublishedPrice.watch_id == match.watch_id, PublishedPrice.item_id == match.item_id)
                        .order_by(PublishedPrice.id.desc()).limit(1))
    if previous != match.price:
        s.add(PublishedPrice(watch_id=match.watch_id, item_id=match.item_id, price=match.price))


def is_dead(s: Session, item_id: str) -> bool:
    """已售出/已删除/已下架 → 不再作为推荐。"""
    row = s.get(ItemRow, item_id)
    return bool(row and row.dead)


def mark_dead(s: Session, item_id: str, reason: str) -> None:
    row = s.get(ItemRow, item_id)
    if row is None or row.dead:
        return
    row.dead = True
    row.dead_reason = reason
    row.dead_at = _now()
    s.commit()


def mark_collected(s: Session, item_id: str) -> None:
    """收藏夹里观测到该商品 → 标 favorited(幂等), 并把仍在待审的退出(approved)。

    修复: 用户直接在闲鱼收藏(非控制台批准)的商品, 之前不会被标 favorited,
    导致反复进推荐、且不出现在收藏视图。
    """
    row = s.get(ItemRow, item_id)
    if row is None:
        return
    if not row.favorited:
        row.favorited = True
        row.favorited_at = _now()
    if row.rec_status == "new":          # 已收藏的不该再在待审队列里
        row.rec_status = "approved"
    s.commit()


def mute_item(s: Session, item_id: str, until: datetime) -> None:
    """近期不看: muted_until 之前从待审隐藏 + 不再推荐; 到期后(1天/7天)自动重现,
    永久=远未来(9999)。保留 rec_status=new, 仅靠 muted_until 过滤, 到期即回归。"""
    row = s.get(ItemRow, item_id)
    if row is None:
        return
    row.muted_until = until
    s.commit()


def is_muted(s: Session, item_id: str) -> bool:
    row = s.get(ItemRow, item_id)
    return bool(row and row.muted_until and row.muted_until > _now())


def add_event(s: Session, item_id: str, type_: str, payload: dict) -> None:
    s.add(Event(item_id=item_id, type=type_,
                payload=json.dumps(payload, ensure_ascii=False)))
    s.commit()


def has_drop_event_at_price(s: Session, item_id: str, price: float, minutes: int = 180) -> bool:
    """最近是否已经因为「跌到这个价」记过降价事件, 避免搜索和收藏复检重复记一条。"""
    cutoff = _now() - timedelta(minutes=minutes)
    rows = s.scalars(select(Event).where(Event.item_id == item_id, Event.type == "price_drop",
                                         Event.created_at >= cutoff))
    for event in rows:
        try:
            if float(json.loads(event.payload).get("curr_price")) == float(price):
                return True
        except (ValueError, TypeError):
            continue
    return False


def unnotified_events(s: Session) -> list[Event]:
    return list(s.scalars(select(Event).where(Event.notified.is_(False))))


def mark_notified(s: Session, ids: list[int]) -> None:
    for e in s.scalars(select(Event).where(Event.id.in_(ids))):
        e.notified = True
    s.commit()


# ---------- Watches (控制台管理) ----------

def list_watches(s: Session) -> list[WatchRow]:
    return list(s.scalars(select(WatchRow).order_by(WatchRow.id)))


def get_watch(s: Session, watch_id: int) -> WatchRow | None:
    return s.get(WatchRow, watch_id)


def add_watch(s: Session, **fields) -> WatchRow:
    row = WatchRow(**fields)
    s.add(row)
    s.commit()
    return row


def update_watch(s: Session, watch_id: int, **fields) -> WatchRow | None:
    row = s.get(WatchRow, watch_id)
    if row is None:
        return None
    if "name" in fields and fields["name"] != row.name:
        s.execute(update(ItemRow).where(ItemRow.watch_name == row.name).values(watch_name=fields["name"]))
    visibility_changed = fields.get("public", row.public) != row.public or fields.get("folder_id", row.folder_id) != row.folder_id
    if visibility_changed:
        s.execute(delete(PublishedPrice).where(PublishedPrice.watch_id == watch_id))
    for k, v in fields.items():
        setattr(row, k, v)
    if visibility_changed and row.public:
        for match in watch_matches(s, row.id):
            record_published_price(s, match)
    s.commit()
    return row


def delete_watch(s: Session, watch_id: int) -> None:
    row = s.get(WatchRow, watch_id)
    if row is not None:
        s.execute(delete(PublishedPrice).where(PublishedPrice.watch_id == watch_id))
        s.execute(delete(WatchMatch).where(WatchMatch.watch_id == watch_id))
        s.delete(row)
        s.commit()


def watch_last_runs(s: Session) -> dict[int, datetime]:
    """每个条件最近一次跑到的时刻(取该组匹配记录的观测时间)。"""
    rows = s.execute(select(WatchMatch.watch_id, func.max(WatchMatch.observed_at))
                     .group_by(WatchMatch.watch_id)).all()
    return {int(watch_id): stamp for watch_id, stamp in rows if stamp is not None}


def watch_matches(s: Session, watch_id: int):
    return s.scalars(select(WatchMatch).where(WatchMatch.watch_id == watch_id))


def save_watch_match(s: Session, watch_id: int, item: Item,
                     ok: bool | None, reason: str | None) -> None:
    match = s.get(WatchMatch, (watch_id, item.item_id))
    if match is None:
        match = WatchMatch(watch_id=watch_id, item_id=item.item_id)
        s.add(match)
    match.ok = ok
    match.reason = reason
    match.title = item.title
    match.url = item.url
    match.price = item.price
    match.observed_at = _now()
    record_published_price(s, match)
    s.commit()


def item_watch_ids(s: Session) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for item_id, watch_id in s.execute(select(WatchMatch.item_id, WatchMatch.watch_id)):
        result.setdefault(item_id, []).append(watch_id)
    return result


# ---------- App config (单行) ----------

def get_config(s: Session) -> AppConfig:
    cfg = s.get(AppConfig, 1)
    if cfg is None:
        s.add(AppConfig(id=1))
        try:
            s.commit()
        except IntegrityError:      # 同一新账号的首屏请求并发建配置行
            s.rollback()
        cfg = s.get(AppConfig, 1)
        if cfg is None:
            raise RuntimeError("app_config 初始化失败")
    return cfg


def update_config(s: Session, **fields) -> AppConfig:
    cfg = get_config(s)
    for k, v in fields.items():
        setattr(cfg, k, v)
    s.commit()
    return cfg


# ---------- Recommendations (审核队列) ----------

def has_been_recommended(s: Session, item_id: str) -> bool:
    row = s.get(ItemRow, item_id)
    return bool(row and row.rec_status)


def create_recommendation(s: Session, item: Item, watch_name: str | None,
                          reason: str | None = None, ok: bool | None = None) -> bool:
    """新推荐(未见过)→ 写入并标 rec_status=new; 已见过返回 False。
    ok = LLM 裁决(True 通过 / False 未过 / None 未审); 未过的也入库, 由前端筛选。"""
    if has_been_recommended(s, item.item_id):
        return False
    upsert_item_with_price(s, item, source="search", watch_name=watch_name)
    row = s.get(ItemRow, item.item_id)
    if row is None:
        return False
    row.rec_status = "new"
    row.rec_created_at = _now()
    row.rec_reason = reason
    row.rec_ok = ok
    s.commit()
    return True


def list_recommendations(s: Session, status: str = "new") -> list[ItemRow]:
    q = select(ItemRow).where(ItemRow.rec_status == status)
    if status == "new":
        # 待审里排除已收藏、当前静音中的; 死链保留(置灰提示别再开)
        q = q.where(ItemRow.favorited.is_(False), ItemRow.local_saved.is_(False)).where(
            or_(ItemRow.muted_until.is_(None), ItemRow.muted_until <= _now()))
    return list(s.scalars(
        q.order_by(ItemRow.dead.asc(), ItemRow.rec_created_at.desc())))


def set_rec_status(s: Session, item_id: str, status: str) -> None:
    row = s.get(ItemRow, item_id)
    if row is not None:
        row.rec_status = status
        s.commit()


def update_rec_verdict(s: Session, item_id: str, ok: bool | None, reason: str | None) -> None:
    """一键补审: 只更新 LLM 裁决(rec_ok/rec_reason), 不动 rec_status。"""
    row = s.get(ItemRow, item_id)
    if row is not None:
        row.rec_ok = ok
        row.rec_reason = reason
        s.commit()


def update_item_stats(s: Session, item_id: str, want_count: int | None = None,
                      browse_count: int | None = None, collect_count: int | None = None) -> None:
    """更新商品的浏览/收藏/想要次数(死链核活打开详情页时顺带取到)。None 的不覆盖。"""
    row = s.get(ItemRow, item_id)
    if row is None:
        return
    if want_count is not None:
        row.want_count = want_count
    if browse_count is not None:
        row.browse_count = browse_count
    if collect_count is not None:
        row.collect_count = collect_count
    s.commit()


def list_favorites(s: Session) -> list[ItemRow]:
    """收藏视图 = 闲鱼收藏夹(source=favorite) ∪ 我们批准收藏过的。死链排末尾。"""
    return list(s.scalars(
        select(ItemRow)
        .where(or_(ItemRow.local_saved.is_(True), ItemRow.favorited.is_(True), ItemRow.source == "favorite"))
        .order_by(ItemRow.dead.asc(), ItemRow.reduce_price.desc(),
                  ItemRow.last_seen_at.desc())))


def recent_events(s: Session, limit: int = 100) -> list[Event]:
    return list(s.scalars(select(Event).order_by(Event.created_at.desc()).limit(limit)))


def stats(s: Session) -> dict:
    """仪表盘指标。"""
    def cnt(q) -> int:
        return int(s.scalar(select(func.count()).select_from(ItemRow).where(q)) or 0)

    new = list_recommendations(s, "new")          # 已排除已收藏/静音
    return {
        "pending": len(new),
        "passed": sum(1 for r in new if r.rec_ok is not False),
        "watches": int(s.scalar(select(func.count()).select_from(WatchRow)) or 0),
        "favorites": cnt(or_(ItemRow.local_saved.is_(True), ItemRow.favorited.is_(True), ItemRow.source == "favorite")),
        "dead": cnt(ItemRow.dead.is_(True)),
        "drops_today": int(s.scalar(
            select(func.count()).select_from(Event)
            .where(Event.type == "price_drop", Event.created_at >= _now() - timedelta(days=1))) or 0),
    }
