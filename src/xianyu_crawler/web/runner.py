"""浏览器 worker: 用全局锁串行化所有浏览器作业(Playwright sync 一次只跑一个)。

在线程里跑(不在 asyncio 事件循环), 由 API(run_in_threadpool / Thread)与调度器共同调用。
"""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone

from .. import service, notifier
from ..session import browser_session, is_logged_in
from ..storage import repo
from . import runtime, account

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()


def busy() -> bool:
    """是否有浏览器作业在跑(全局串行锁)。前端按钮据此给「正在搜索中」的提示。"""
    return _LOCK.locked()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _notify(session, settings) -> int:
    """发邮件: 按控制台「邮件提醒事件」开关过滤; CSV 仍记录全部, 全部标记已处理。"""
    evs = repo.unnotified_events(session)
    if not evs:
        return 0
    views = [{"type": e.type, **json.loads(e.payload)} for e in evs]
    notifier.append_csv(settings.data_dir / "events.csv", views)   # 本地 CSV 记全部
    on = {"new_recommendation": settings.notify_on_new,
          "price_drop": settings.notify_on_drop,
          "sold": settings.notify_on_sold,
          "favorited": settings.notify_on_favorite}
    mail = [v for v in views if on.get(v["type"], True)]
    if mail:
        subject, body = notifier.format_email(mail)
        html = notifier.format_email_html(mail)
        notifier.send_email(settings, subject, body, html)
    repo.mark_notified(session, [e.id for e in evs])               # 含未发邮件的也标记
    return len(mail)


def crawl(watch_name: str | None = None) -> dict:
    """一轮抓取。watch_name=None → 全量(降价监控 + 全部条件扫描 + 死链核活);
    指定条件名 → 只搜该条件(不刷收藏/不核活)。锁忙则跳过(防重入)。"""
    if not _LOCK.acquire(blocking=False):
        return {"skipped": "busy"}
    runtime.job_state()["running"] = True
    s = None
    try:
        s = runtime.session()
        cfg = repo.get_config(s)
        if cfg.paused:
            return {"skipped": "paused"}
        settings = runtime.effective_settings(cfg)
        blocked = runtime.search_block_reason(settings)
        if blocked:
            logger.warning("无法开始抓取(scope=%s): %s", runtime.scope()[:8], blocked)
            result = {"error": blocked, "at": _now_iso()}
            runtime.job_state()["last"] = result
            return result
        watches = [service.watchrow_to_watch(w) for w in repo.list_watches(s)]
        if watch_name:                           # 只跑指定条件
            watches = [w for w in watches if w.name == watch_name]
        with browser_session(settings) as ctx:
            check = ctx.new_page()
            navs: list = []          # 顺带抓「我的导航」接口里的头像(在 handler 外再读 body)
            check.on("response",
                     lambda r: navs.append(r) if "mtop.idle.web.user.page.nav" in r.url else None)
            logged_in = is_logged_in(check)
            if logged_in and not navs:
                try:
                    check.wait_for_timeout(2000)     # 导航接口偶尔晚到, 略等
                except Exception:
                    pass
            for r in navs:                           # 提取头像 URL → 缓存(默认灰头像会被存成 null)
                try:
                    m = re.search(r'"avatar"\s*:\s*"([^"]+)"', r.text())
                    if m:
                        account.save(m.group(1))
                        break
                except Exception:
                    pass
            check.close()
            if not logged_in:
                logger.warning("闲鱼登录失效(scope=%s)", runtime.scope()[:8])
                if settings.notify_on_login:
                    notifier.send_email(
                        settings, "闲鱼登录已失效",
                        "控制台检测到登录态失效，请打开控制台 → 设置 → 闲鱼登录 → 扫码登录 重新登录。")
                result = {"error": "login_expired", "at": _now_iso()}
            elif watch_name:
                # 只跑单个条件: 仅搜索该条件 + 通知(不刷收藏、不核活, 快)
                scan = service.scan_recommendations(ctx, s, settings, watches)
                notified = _notify(s, settings)
                result = {"recommendations": scan.created, "scanned": scan.scanned, "raw": scan.raw,
                          "scope": watch_name, "notified": notified, "at": _now_iso()}
            else:
                # 先跑监控(刷新收藏列表入库, 含收藏夹死链), scan 才能据此过滤
                drops = service.run_price_monitor(ctx, s, settings)
                scan = service.scan_recommendations(ctx, s, settings, watches)
                # 给待审推荐核活, 标记卖出/删除的死链(避免重复打开)
                dead = service.sweep_liveness(ctx, s, settings)
                notified = _notify(s, settings)
                result = {"recommendations": scan.created, "scanned": scan.scanned, "raw": scan.raw,
                          "drops": drops + scan.drops, "dead": dead, "notified": notified,
                          "at": _now_iso()}
    except Exception as e:  # noqa: BLE001 - 后台作业, 记录不抛
        logger.exception("抓取失败(scope=%s)", runtime.scope()[:8])
        result = {"error": str(e), "at": _now_iso()}
    finally:
        if s is not None:
            s.close()
        runtime.job_state()["running"] = False
        _LOCK.release()
    runtime.job_state()["last"] = result
    return result


def crawl_manual(watch_name: str | None = None) -> dict:
    """手动触发的抓取: 跑完把下一次定时往后推一个周期。

    只跑单个条件时不刷新收藏, 所以只推迟 crawl; 全量才连收藏任务一起推迟。
    """
    result = crawl(watch_name)
    if not result.get("skipped"):
        from . import scheduler
        scheduler.delay_after_manual(include_favorites=watch_name is None)
    return result


def refresh_favorites() -> dict:
    """收藏刷新(独立定时任务, 默认每 30 分钟): 在线读闲鱼收藏夹,
    更新价格/死链/收藏后降价, 命中降价发邮件。锁忙/已暂停则跳过。
    """
    if not _LOCK.acquire(blocking=False):
        return {"skipped": "busy"}
    runtime.job_state()["running"] = True
    s = None
    try:
        s = runtime.session()
        cfg = repo.get_config(s)
        if cfg.paused:
            return {"skipped": "paused"}
        settings = runtime.effective_settings(cfg)
        if runtime.shared_mode() and not runtime.has_login():
            return {"skipped": "login_required"}
        with browser_session(settings) as ctx:
            drops = service.run_price_monitor(ctx, s, settings)
        notified = _notify(s, settings)
        return {"drops": drops, "notified": notified, "at": _now_iso()}
    except Exception as e:  # noqa: BLE001 - 后台作业, 记录不抛
        return {"error": str(e), "at": _now_iso()}
    finally:
        if s is not None:
            s.close()
        runtime.job_state()["running"] = False
        _LOCK.release()
