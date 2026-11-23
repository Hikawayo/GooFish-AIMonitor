"""服务层: 桥接 DB(watches/config) ↔ 引擎(search/filter/favorite/monitor)。

控制台与调度都调这里。审核制: 搜索命中 → 写"推荐"(不自动收藏);
用户在控制台批准 → 点"收藏" → 进闲鱼收藏列表 → 自动进降价监控。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, Watch
from .models import Item
from .filter import matches
from .storage import repo
from .storage.orm import WatchRow, WatchMatch, AppConfig, ItemRow
from . import search as _search_mod
from . import favorite as _favorite_mod
from . import pipeline
from .price_monitor import detect_drop
from . import review
from . import liveness as _liveness_mod

logger = logging.getLogger(__name__)


# --- 测试可 monkeypatch 的间接层(隔离真实浏览器) ---
def _search(ctx, watch: Watch, settings: Settings):
    return _search_mod.search(ctx, watch, settings.search_max_pages, settings.search_url)


def _check_liveness(ctx, item_id: str) -> tuple[bool, str | None, dict | None]:
    return _liveness_mod.check_liveness(ctx, item_id)


def _add_favorite(ctx, item: Item, settings: Settings) -> bool:
    return _favorite_mod.add_favorite(ctx, item, settings)


# --- row ↔ domain 映射 ---
def watchrow_to_watch(w: WatchRow) -> Watch:
    return Watch(
        id=w.id,
        name=w.name,
        keywords=json.loads(w.keywords or "[]"),
        price_min=w.price_min,
        price_max=w.price_max,
        city=w.city,
        condition=json.loads(w.condition) if w.condition else None,
        free_shipping=w.free_shipping,
        seller_min_credit=w.seller_min_credit,
        requirement=w.requirement,
        kind=w.kind or "general",
        enabled=w.enabled,
    )


def effective_settings(cfg: AppConfig) -> Settings:
    """DB 配置覆盖到 Settings; SMTP 控制台填了用控制台的, 没填回退系统环境变量。"""
    base = Settings()

    def pick(db_val, env_val):
        return db_val if db_val not in (None, "") else env_val

    return base.model_copy(update={
        "min_drop_pct": cfg.min_drop_pct,
        "min_drop_abs": cfg.min_drop_abs,
        "notify_to": cfg.notify_to or base.notify_to,
        "headless": cfg.headless,
        "search_max_pages": cfg.search_max_pages,
        "favorites_max_pages": cfg.favorites_max_pages,
        "favorites_minutes": cfg.favorites_minutes,
        # LLM 二次审核(接口地址/token 控制台没填则回退本地 secret.env)
        "review_enabled": cfg.review_enabled,
        "review_base_url": pick(cfg.review_base_url, base.review_base_url),
        "review_model": cfg.review_model,
        "review_api_token": pick(cfg.review_api_token, base.review_api_token),
        "review_timeout": cfg.review_timeout,
        "review_temperature": cfg.review_temperature,
        "review_max_tokens": cfg.review_max_tokens,
        "review_system_prompt": cfg.review_system_prompt or base.review_system_prompt,
        # 高级(抓取/反爬)
        "action_delay_min": cfg.action_delay_min,
        "action_delay_max": cfg.action_delay_max,
        "liveness_max_checks": cfg.liveness_max_checks,
        "search_url": cfg.search_url,
        "favorites_url": cfg.favorites_url,
        # SMTP
        "smtp_host": pick(cfg.smtp_host, base.smtp_host),
        "smtp_port": cfg.smtp_port or base.smtp_port,
        "smtp_user": pick(cfg.smtp_user, base.smtp_user),
        "smtp_pass": pick(cfg.smtp_pass, base.smtp_pass),
        # 邮件提醒事件开关
        "notify_on_new": cfg.notify_on_new,
        "notify_on_drop": cfg.notify_on_drop,
        "notify_on_sold": cfg.notify_on_sold,
        "notify_on_favorite": cfg.notify_on_favorite,
        "notify_on_login": cfg.notify_on_login,
    })


# --- 用例 ---
@dataclass
class ScanResult:
    """一轮扫描的三个数字: 搜索返回条数、命中规则条数、真正新入队的推荐数。

    raw 与 scanned 分开, 才能回答「是没搜到东西, 还是被价格/地区规则挡掉了」。
    """
    created: int = 0
    scanned: int = 0
    raw: int = 0
    drops: int = 0           # 搜索复看时发现的降价(与收藏复检合并计数)
    warning: str | None = None  # 跑完了但结果可疑(例如某个条件一条都没搜到)
    backfilled: int = 0      # 票务模板给历史商品补抽属性成功的条数


def scan_recommendations(ctx, session: Session, settings: Settings,
                         watches: list[Watch], on_watch=None,
                         on_backfill=None) -> ScanResult:
    """搜索 → 规则过滤 → 去重 → LLM 二次审核 → 写"我没见过的"推荐。

    `created` 只数真正新入队的候选；`scanned` 是本轮搜索命中规则的条数——
    有了它才能区分「一条都没搜到」和「都搜到了但都不是新的」。
    """
    result = ScanResult()
    for watch_index, w in enumerate(watches):
        if not w.enabled:
            continue
        if on_watch is not None:
            on_watch(watch_index, len(watches), w.name)
        # 规则过滤 + 去重(本轮内 & 已推荐过的)
        fresh: list[Item] = []
        seen: set[str] = set()
        known = {m.item_id: m for m in repo.watch_matches(session, w.id)} if w.id is not None else {}
        watch_raw = watch_scanned = watch_drops = 0
        for item in _search(ctx, w, settings):
            if item.item_id in seen:
                continue
            seen.add(item.item_id)
            watch_raw += 1
            if not matches(item, w):
                continue
            watch_scanned += 1
            previous = known.get(item.item_id)
            if previous is not None:
                prev_price = repo.upsert_item_with_price(session, item, source="search")
                previous.price = item.price
                previous.observed_at = repo._now()
                repo.record_published_price(session, previous)
                session.commit()
                # 搜索再次看到时降价了, 也要进事件流(以前只有收藏复检会记, 于是
                # 「价格记录里有变化, 实时事件里什么都没有」)
                if prev_price is not None:
                    drop = detect_drop(item.item_id, prev_price, item.price,
                                       settings.min_drop_pct, settings.min_drop_abs)
                    if drop and not repo.has_drop_event_at_price(session, item.item_id, item.price):
                        repo.add_event(session, item.item_id, "price_drop", {
                            "title": item.title, "url": item.url, "pic": item.pic_url,
                            "reason": "搜索再次发现降价",
                            "prev_price": drop.prev_price, "curr_price": drop.curr_price,
                            "drop_abs": drop.drop_abs, "drop_pct": drop.drop_pct,
                        })
                        watch_drops += 1
                continue
            if (repo.is_dead(session, item.item_id) or repo.is_muted(session, item.item_id)
                    or (w.id is None and (repo.has_been_recommended(session, item.item_id)
                                         or repo.is_collected(session, item.item_id)))):
                continue
            fresh.append(item)
        watch_created = 0
        # LLM 二次审核(有 requirement 才审; 无要求/失败放行)。
        # 未通过的也入库(带 rec_ok=False + 理由), 由前端筛选展示。
        verdicts = review.review_items(fresh, w.requirement, settings, kind=w.kind or "general")
        for item, verdict in zip(fresh, verdicts):
            ok = None if verdict.skipped else verdict.ok
            if verdict.attrs:
                item.attrs = verdict.attrs
            # 人工审核没有理由可展示(页面本身就是待审队列); 只保留"没跑通"的提示
            reason = None if verdict.reason == review.REVIEW_MANUAL else (verdict.reason or None)
            if repo.is_collected(session, item.item_id):
                repo.upsert_item_with_price(session, item, source="search")
                new = False
            else:
                new = repo.create_recommendation(session, item, w.name, reason, ok=ok)
            if w.id is not None:
                repo.save_watch_match(session, w.id, item, ok, reason)
            if not new:
                continue
            # AI 通过, 或人工审核模式下进队列 → 都算"本轮新推荐"
            queued = ok is True or (ok is None and not settings.review_enabled)
            if queued:
                watch_created += 1
                repo.add_event(session, item.item_id, "new_recommendation",
                               {"title": item.title, "url": item.url, "price": item.price,
                                "pic": item.pic_url, "watch": w.name})
        if watch_raw == 0 and w.enabled:
            # 一条都没搜到而这条条件本来是有结果的 → 多半被风控或页面异常, 必须让用户看见
            result.warning = f"「{w.name}」一条都没搜到，可能被风控或列表没加载出来"
        result.raw += watch_raw
        result.drops += watch_drops
        result.scanned += watch_scanned
        result.created += watch_created
        logger.info("扫描「%s」关键词=%s: 搜索 %d 条 → 命中规则 %d 条 → 新增 %d 条",
                    w.name, " ".join(w.keywords), watch_raw, watch_scanned, watch_created)
        if (w.kind or "general") == "ticket":
            result.backfilled += _backfill_attrs(session, settings, w, on_step=on_backfill)
    return result


# 票务模板: 一轮最多给几件历史商品补抽属性(控制模型调用量)
ATTR_BACKFILL_PER_RUN = 10


def _backfill_attrs(session: Session, settings: Settings, w: Watch, on_step=None) -> int:
    """给库里还没属性的商品补抽席种等; 每轮限量, 抽到就存, 抽不到下次再说。"""
    if not settings.review_enabled or not w.requirement or w.id is None:
        return 0
    pending = []
    for match in repo.watch_matches(session, w.id):
        if match.ok is False:
            continue
        attrs = repo.item_attrs_of(session, match.item_id)
        if attrs:
            continue
        pending.append(Item(item_id=match.item_id, title=match.title or "", url=match.url or "",
                            price=match.price or 0.0))
        if len(pending) >= ATTR_BACKFILL_PER_RUN:
            break
    if not pending:
        return 0
    done = 0
    for item, verdict in zip(pending, review.review_items(pending, w.requirement, settings,
                                                          kind="ticket", on_item=on_step)):
        if verdict.attrs and not verdict.skipped:
            repo.set_item_attrs(session, item.item_id, verdict.attrs)
            done += 1
    return done


def rereview_pending(session: Session, settings: Settings) -> dict:
    """对已入库的「待审」推荐, 用当前 LLM 配置重新跑一次 AI 审核并更新裁决(不重新抓闲鱼)。

    用途: 之前接口没配好时 review fail-open 攒下的「未审核」推荐(rec_reason=(审核未运行)),
    把接口配好(可用「测试 LLM」验证)后一键补审。没跑通的保留原样并计数提示。
    """
    if not settings.review_enabled:
        return {"ok": False, "error": "AI 审核未启用, 请先在设置里打开「启用 AI 审核」"}
    rows = [r for r in repo.list_recommendations(session, "new") if not r.dead]
    watches = repo.list_watches(session)
    requirements = {w.name: w.requirement for w in watches}
    by_watch: dict[str, list[tuple[ItemRow, WatchMatch | None]]] = {}
    watch_by_id = {w.id: w.name for w in watches}
    matches_by_item: dict[str, list[WatchMatch]] = {}
    for match in session.scalars(select(WatchMatch)):
        if match.watch_id in watch_by_id:
            matches_by_item.setdefault(match.item_id, []).append(match)
    skipped = 0
    for r in rows:
        matches = matches_by_item.get(r.item_id, [])
        if matches:
            for match in matches:
                by_watch.setdefault(watch_by_id[match.watch_id], []).append((r, match))
        elif r.watch_name is not None:
            by_watch.setdefault(r.watch_name, []).append((r, None))
        else:
            skipped += 1

    reviewed = passed = rejected = not_run = 0
    for wname, recs in by_watch.items():
        requirement = requirements.get(wname)
        if not requirement:                  # 该监控条件没写「AI 审核要求」→ 无从审核
            skipped += len(recs)
            continue
        items = [Item(item_id=r.item_id, title=r.title, url=r.url, price=match.price if match else r.latest_price,
                      condition=r.condition, location=r.location) for r, match in recs]
        verdicts = review.review_items(items, requirement, settings)
        for (r, match), v in zip(recs, verdicts):
            if v.skipped:                            # 接口没跑通 → 保留原裁决, 只计数
                not_run += 1
                continue
            if match is not None:
                match.ok = v.ok
                match.reason = v.reason or None
                repo.record_published_price(session, match)
                session.commit()
            if r.watch_name == wname:
                repo.update_rec_verdict(session, r.item_id, v.ok, v.reason or None)
            reviewed += 1
            passed += int(bool(v.ok))
            rejected += int(not v.ok)
    return {"ok": True, "reviewed": reviewed, "passed": passed, "rejected": rejected,
            "not_run": not_run, "skipped_no_requirement": skipped}


def sweep_liveness(ctx, session: Session, settings: Settings, on_step=None) -> int:
    """对待审推荐逐条打开详情页核活, 已删除/下架的标死链(置灰, 不再误开)。

    收藏夹的死链由收藏 API 直接给出(run_monitor 入库); 这里专补"纯搜索来源、
    卖出后从搜索消失"的推荐。每轮限量 settings.liveness_max_checks。返回新判死数。
    """
    rows = repo.list_recommendations(session, "new")
    pending = [r for r in rows if not r.dead][: settings.liveness_max_checks]
    newly_dead = 0
    for index, r in enumerate(pending, 1):
        if on_step is not None:
            on_step(index, len(pending))
        dead, reason, stats = _check_liveness(ctx, r.item_id)
        if stats:                          # 顺带回写浏览/收藏/想要次数
            repo.update_item_stats(session, r.item_id, **stats)
        if dead:
            repo.mark_dead(session, r.item_id, reason or "已删除")
            repo.add_event(session, r.item_id, "sold",
                           {"title": r.title, "url": r.url, "pic": r.pic_url,
                            "reason": reason or "已删除"})
            newly_dead += 1
    return newly_dead


def approve_recommendation(ctx, session: Session, settings: Settings, item_id: str) -> bool:
    """批准推荐 → 在闲鱼点"收藏" → 标记 favorited/approved。"""
    row = session.get(ItemRow, item_id)
    if row is None:
        return False
    item = Item(item_id=row.item_id, title=row.title, url=row.url, price=row.latest_price)
    if _add_favorite(ctx, item, settings):
        repo.mark_favorited(session, item_id)
        repo.set_rec_status(session, item_id, "approved")
        return True
    return False


def reject_recommendation(session: Session, item_id: str) -> None:
    repo.set_rec_status(session, item_id, "rejected")


MANUAL_APPROVED = "(人工通过)"
MANUAL_REJECTED = "(人工忽略)"


def record_manual_verdict(session: Session, item_id: str, ok: bool) -> None:
    """人工审核模式下把「通过/忽略」写进所属条件的匹配记录。

    公开行情和价格观测都以 WatchMatch.ok 判定"已确认匹配"; 只改推荐状态的话,
    人工通过的组在公开页仍然是空的。
    """
    if repo.get_config(session).review_enabled:
        return
    reason = MANUAL_APPROVED if ok else MANUAL_REJECTED
    for match in session.scalars(select(WatchMatch).where(WatchMatch.item_id == item_id)):
        match.ok = ok
        match.reason = reason
        repo.record_published_price(session, match)
    repo.update_rec_verdict(session, item_id, ok, reason)
    session.commit()


_MUTE_FOREVER = datetime(9999, 12, 31)


def mute_recommendation(session: Session, item_id: str, days: int) -> None:
    """近期不看: days>0 → 隐藏到 N 天后(到期自动重现); days<=0 → 永久不看。"""
    if days <= 0:
        until = _MUTE_FOREVER
    else:
        until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=days)
    repo.mute_item(session, item_id, until)


def run_price_monitor(ctx, session: Session, settings: Settings) -> int:
    return refresh_local_favorites(ctx, session, settings) + pipeline.run_monitor(ctx, session, settings)


def refresh_local_favorites(ctx, session: Session, settings: Settings) -> int:
    """独立读取站内收藏的详情价。按上次尝试时间轮转，错误不会覆盖上次结果。"""
    drops = 0
    entries = repo.due_local_favorites(session, max(settings.favorites_minutes, 1),
                                      max(settings.liveness_max_checks, 0))
    for row in entries:
        reading = _liveness_mod.check_detail(ctx, row.item_id)
        row.detail_checked_at = repo._now()
        previous = row.latest_price
        if reading.dead:
            repo.mark_dead(session, row.item_id, reading.dead_reason or "详情已失效")
            repo.add_event(session, row.item_id, "sold", {
                "title": row.title, "url": row.url, "pic": row.pic_url,
                "reason": reading.dead_reason or "详情已失效",
            })
        elif reading.price is not None:
            # 平台优惠: 挂牌价没动但实付更低, 走势必须按实付价走, 否则这次降价永远看不到
            promo = reading.promo_price
            effective = promo if (promo is not None and promo < reading.price) else reading.price
            discounted = effective < reading.price
            repo.set_promo_price(session, row.item_id,
                                 promo if discounted else None,
                                 reading.price if discounted else None)
            repo.record_local_price(session, row, effective)
            # 平台给了「卖家原价 + 发布时间」时, 补一条最早的观测, 走势才有起点
            if (reading.original_price and reading.published_at
                    and reading.original_price > reading.price
                    and reading.published_at <= repo._now()):
                repo.seed_original_price(session, row.item_id,
                                         reading.original_price, reading.published_at)
            drop = detect_drop(row.item_id, previous, effective, settings.min_drop_pct, settings.min_drop_abs)
            if drop and not repo.has_drop_event_at_price(session, row.item_id, effective):
                repo.add_event(session, row.item_id, "price_drop", {
                    "title": row.title, "url": row.url, "pic": row.pic_url,
                    "reason": "平台优惠降价" if discounted else "站内收藏详情复检",
                    "prev_price": drop.prev_price, "curr_price": drop.curr_price,
                    "drop_abs": drop.drop_abs, "drop_pct": drop.drop_pct,
                })
                drops += 1
        else:
            session.commit()
    return drops
