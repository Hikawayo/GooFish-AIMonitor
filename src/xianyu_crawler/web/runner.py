"""浏览器 worker: 单 worker 队列串行化所有抓取与收藏作业(Playwright sync 一次只跑一个)。

排队机制:
- 定时任务与手动触发统一入队, 按 (scope, kind, watch_name) 去重, 不再因为别人在抓就跳过。
- busy() / queue_position() 按当前用户 scope 判断, 互不干扰。
- 单轮抓取有总时长上限(settings.crawl_timeout_seconds), 超时提前结束, 防止占死队列。
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from .. import service, notifier
from ..search import SessionExpired
from ..session import browser_session, is_logged_in
from ..storage import repo
from . import runtime, account

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()


@dataclass(frozen=True)
class _Job:
    scope: str
    kind: Literal["crawl", "favorites"]
    watch_name: str | None = None
    manual: bool = False

    def key(self) -> tuple[str, str, str | None]:
        return (self.scope, self.kind, self.watch_name)


class CrawlTimeout(TimeoutError):
    """单轮抓取超过总时长上限。"""


_QUEUE_COND = threading.Condition()
_QUEUE: deque[_Job] = deque()
_ACTIVE_JOB: _Job | None = None
_WORKER_THREAD: threading.Thread | None = None


def _ensure_worker_locked() -> None:
    global _WORKER_THREAD
    if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
        return
    _WORKER_THREAD = threading.Thread(target=_worker_loop, name="xy-browser-worker", daemon=True)
    _WORKER_THREAD.start()


def _worker_loop() -> None:
    global _ACTIVE_JOB
    while True:
        with _QUEUE_COND:
            while not _QUEUE:
                _QUEUE_COND.wait()
            job = _QUEUE.popleft()
            _ACTIVE_JOB = job
        try:
            with runtime.use_scope(job.scope):
                if job.kind == "favorites":
                    refresh_favorites()
                elif job.manual:
                    crawl_manual(job.watch_name)
                else:
                    crawl(job.watch_name)
        except Exception:  # noqa: BLE001 - worker 线程永不退出
            logger.exception("worker 执行异常(scope=%s, kind=%s)", job.scope[:8], job.kind)
        finally:
            with _QUEUE_COND:
                _ACTIVE_JOB = None


def queue_position(user_scope: str | None = None) -> int:
    """当前用户在队列中的 1-based 排队位次; 未排队返回 0。"""
    target = user_scope or runtime.scope()
    with _QUEUE_COND:
        for idx, job in enumerate(_QUEUE, start=1):
            if job.scope == target:
                return idx
    return 0


def busy(user_scope: str | None = None) -> bool:
    """指定用户(默认当前 scope)是否正在执行或排队等待浏览器作业。"""
    target = user_scope or runtime.scope()
    with _QUEUE_COND:
        if _ACTIVE_JOB is not None and _ACTIVE_JOB.scope == target:
            return True
        if any(job.scope == target for job in _QUEUE):
            return True
    return bool(runtime._jobs.get(target, {}).get("running"))


def enqueue_crawl(watch_name: str | None = None, *, manual: bool = False) -> dict:
    """把当前用户的抓取任务加入单 worker 队列(按 scope+kind+watch 去重)。"""
    user_scope = runtime.scope()
    job = _Job(scope=user_scope, kind="crawl", watch_name=watch_name, manual=manual)
    with _QUEUE_COND:
        if _ACTIVE_JOB is not None and _ACTIVE_JOB.scope == user_scope:
            return {"status": "busy", "scope": watch_name or "all"}
        for idx, existing in enumerate(_QUEUE, start=1):
            if existing.key() == job.key():
                return {"status": "queued", "scope": watch_name or "all", "position": idx, "deduped": True}
        _QUEUE.append(job)
        pos = len(_QUEUE)
        _ensure_worker_locked()
        _QUEUE_COND.notify()
    return {"status": "queued", "scope": watch_name or "all", "position": pos}


def enqueue_favorites() -> dict:
    """把当前用户的收藏刷新任务加入单 worker 队列(按 scope+favorites 去重)。"""
    user_scope = runtime.scope()
    job = _Job(scope=user_scope, kind="favorites")
    with _QUEUE_COND:
        if _ACTIVE_JOB is not None and _ACTIVE_JOB.scope == user_scope and _ACTIVE_JOB.kind == "favorites":
            return {"status": "busy"}
        for idx, existing in enumerate(_QUEUE, start=1):
            if existing.key() == job.key():
                return {"status": "queued", "position": idx, "deduped": True}
        _QUEUE.append(job)
        pos = len(_QUEUE)
        _ensure_worker_locked()
        _QUEUE_COND.notify()
    return {"status": "queued", "position": pos}


def _friendly_job_error(e: Exception) -> str:
    """把底层异常翻成用户能看懂的一句话(原始信息留在容器日志里)。"""
    text = str(e)
    if isinstance(e, CrawlTimeout):
        return text or "本轮抓取超过时长上限，已提前结束"
    if "超时" in text:
        return text
    if "Timeout" in text or "timeout" in text:
        return "打开闲鱼超时（网络慢或触发风控），稍后重试"
    if "net::" in text or "Connection" in text:
        return "连不上闲鱼（网络异常），稍后重试"
    if "Executable doesn't exist" in text or "BrowserType.launch" in text:
        return "浏览器启动失败，请检查服务端 Chromium 是否正常"
    return text[:200] or "未知错误"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _notify(session, settings) -> int:
    """发邮件: 按控制台「邮件提醒事件」开关过滤; 邮件成功后再写 CSV 并标记已处理, 避免失败重复写 CSV。"""
    evs = repo.unnotified_events(session)
    if not evs:
        return 0
    views = [{"type": e.type, **json.loads(e.payload)} for e in evs]
    on = {"new_recommendation": settings.notify_on_new,
          "target_price": settings.notify_on_drop,
          "price_drop": settings.notify_on_drop,
          "sold": settings.notify_on_sold,
          "favorited": settings.notify_on_favorite}
    mail = [v for v in views if on.get(v["type"], True)]
    if mail:
        subject, body = notifier.format_email(mail)
        html = notifier.format_email_html(mail)
        notifier.send_email(settings, subject, body, html)
    notifier.append_csv(settings.data_dir / "events.csv", views)
    repo.mark_notified(session, [e.id for e in evs])
    repo.prune_old_events(session)
    return len(mail)


def _send_login_expired_mail(session, settings, body: str) -> None:
    """登录失效邮件去重: 同一轮失效只发一次, 重新登录后才重置。"""
    if settings is None or not settings.notify_on_login:
        return
    if session is not None:
        cfg = repo.get_config(session)
        if cfg.login_alert_sent_at is not None:
            return
    try:
        notifier.send_email(settings, "闲鱼登录已失效", body)
        if session is not None:
            repo.update_config(session, login_alert_sent_at=repo._now())
    except Exception:
        logger.warning("发送登录失效邮件失败(scope=%s)", runtime.scope()[:8], exc_info=True)


def _clear_login_alert(session) -> None:
    if session is not None:
        cfg = repo.get_config(session)
        if cfg.login_alert_sent_at is not None:
            repo.update_config(session, login_alert_sent_at=None)


def crawl(watch_name: str | None = None) -> dict:
    """一轮抓取。watch_name=None → 全量(降价监控 + 全部条件扫描 + 死链核活);
    指定条件名 → 只搜该条件(不刷收藏/不核活)。"""
    if not _LOCK.acquire(blocking=False):
        return {"skipped": "busy"}
    runtime.job_state()["running"] = True
    s = None
    settings = None
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
        deadline = time.monotonic() + max(30, int(settings.crawl_timeout_seconds))

        def check_deadline() -> None:
            if time.monotonic() > deadline:
                raise CrawlTimeout("本轮抓取超过时长上限，已提前结束，可减少条件数或翻页上限")

        watches = [service.watchrow_to_watch(w) for w in repo.list_watches(s)]
        if watch_name:                           # 只跑指定条件
            watches = [w for w in watches if w.name == watch_name]
        total = 2 + len(watches)
        runtime.set_progress("打开闲鱼", 0, total)
        with browser_session(settings) as ctx:
            check = ctx.new_page()
            navs: list = []          # 顺带抓「我的导航」接口里的头像(在 handler 外再读 body)
            check.on("response",
                     lambda r: navs.append(r) if "mtop.idle.web.user.page.nav" in r.url else None)
            runtime.set_progress("检查登录状态", 1, total)
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
                runtime.mark_login_expired("闲鱼登录已失效，请重新扫码")
                _send_login_expired_mail(
                    s, settings,
                    "控制台检测到登录态失效，请打开控制台 → 设置 → 闲鱼登录 → 扫码登录 重新登录。")
                result = {"error": "login_expired", "at": _now_iso()}
            elif watch_name:
                runtime.clear_login_expired()
                _clear_login_alert(s)
                check_deadline()
                # 只跑单个条件: 仅搜索该条件 + 通知(不刷收藏、不核活, 快)
                runtime.set_progress("搜索条件", 2, total)

                def _on_watch_single(i: int, n: int, name: str) -> None:
                    check_deadline()
                    runtime.set_progress(f"搜索「{name}」", min(total - 1, 2 + i), total)

                scan = service.scan_recommendations(ctx, s, settings, watches, on_watch=_on_watch_single)
                notified = _notify(s, settings)
                result = {"recommendations": scan.created, "scanned": scan.scanned, "raw": scan.raw,
                          "scope": watch_name, "notified": notified, "at": _now_iso()}
                if scan.warning:
                    result["warn"] = scan.warning
            else:
                runtime.clear_login_expired()
                _clear_login_alert(s)
                check_deadline()
                # 先跑监控(刷新收藏列表入库, 含收藏夹死链), scan 才能据此过滤
                runtime.set_progress("刷新闲鱼收藏", 2, total)
                drops = service.run_price_monitor(ctx, s, settings)
                check_deadline()
                base = 2 + len(watches)
                runtime.set_progress("搜索条件", 2, base)

                def _on_watch(i: int, n: int, name: str) -> None:
                    check_deadline()
                    runtime.set_progress(f"搜索「{name}」", min(base, 2 + i), base)

                def _on_backfill(i: int, n: int) -> None:
                    check_deadline()
                    runtime.set_progress(f"补抽属性 {i}/{n}", base + i, base + n)

                scan = service.scan_recommendations(
                    ctx, s, settings, watches, on_watch=_on_watch, on_backfill=_on_backfill)
                check_deadline()
                # 给待审推荐核活, 标记卖出/删除的死链(避免重复打开)
                runtime.set_progress("核活待审商品", base, base)

                def _on_step(i: int, n: int) -> None:
                    check_deadline()
                    runtime.set_progress(f"核活 {i}/{n}", base + i, base + n)

                dead = service.sweep_liveness(ctx, s, settings, on_step=_on_step)
                notified = _notify(s, settings)
                result = {"recommendations": scan.created, "scanned": scan.scanned, "raw": scan.raw,
                          "drops": drops + scan.drops, "dead": dead, "notified": notified,
                          "at": _now_iso()}
                if scan.warning:
                    result["warn"] = scan.warning
    except SessionExpired as e:  # 登录过期: 搜索接口只回空壳, 必须当成"没登录"处理
        logger.warning("闲鱼登录已过期(scope=%s): %s", runtime.scope()[:8], e)
        runtime.mark_login_expired("闲鱼登录已过期，请重新扫码")
        _send_login_expired_mail(
            s, settings,
            "控制台检测到登录态过期（搜索接口返回 SESSION_EXPIRED，列表为空），"
            "请打开控制台 → 设置 → 闲鱼登录 → 扫码登录。")
        result = {"error": "login_expired", "at": _now_iso()}
    except Exception as e:  # noqa: BLE001 - 后台作业, 记录不抛
        logger.exception("抓取失败(scope=%s)", runtime.scope()[:8])
        result = {"error": _friendly_job_error(e), "at": _now_iso()}
    finally:
        if s is not None:
            s.close()
        runtime.job_state()["running"] = False
        runtime.clear_progress()
        _LOCK.release()
    from . import sharing
    sharing.invalidate()
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
    更新价格/死链/收藏后降价, 命中降价发邮件。"""
    if not _LOCK.acquire(blocking=False):
        return {"skipped": "busy"}
    runtime.job_state()["running"] = True
    s = None
    settings = None
    result: dict | None = None
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
        result = {"drops": drops, "notified": notified, "at": _now_iso()}
        return result
    except SessionExpired as e:
        logger.warning("收藏刷新检测到登录过期(scope=%s): %s", runtime.scope()[:8], e)
        runtime.mark_login_expired("闲鱼登录已过期，请重新扫码")
        _send_login_expired_mail(
            s, settings,
            "控制台在刷新收藏时检测到闲鱼登录态已过期，请打开控制台 → 设置 → 闲鱼登录 → 扫码登录。")
        result = {"error": "login_expired", "at": _now_iso()}
        return result
    except Exception as e:  # noqa: BLE001 - 后台作业, 记录不抛
        logger.exception("收藏刷新失败(scope=%s)", runtime.scope()[:8])
        result = {"error": _friendly_job_error(e), "at": _now_iso()}
        return result
    finally:
        if s is not None:
            s.close()
        runtime.job_state()["running"] = False
        if result is not None and "error" in result:
            runtime.job_state()["last"] = result
        _LOCK.release()
