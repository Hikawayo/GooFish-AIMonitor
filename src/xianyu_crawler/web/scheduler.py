"""进程内定时调度(APScheduler): 两个独立任务。

- crawl (schedule_minutes, 默认 120): 推荐抓取 + 死链核活 + 通知。
- favorites (favorites_minutes, 默认 30): 收藏刷新 + 降价通知。

防重入: 每个 job max_instances=1 + coalesce; runner 还有全局锁兜底(两任务共用一把锁,
不会并发开浏览器)。暂停由各 runner 函数内部检查 AppConfig.paused 实现。
"""
from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from . import runner, runtime
from ..config import Settings
from ..storage import backup, repo

_scheduler: BackgroundScheduler | None = None


def _run_for_scope(user_scope: str, favorites: bool) -> None:
    with runtime.use_scope(user_scope):
        (runner.enqueue_favorites if favorites else runner.enqueue_crawl)()


def start(crawl_minutes: int, favorites_minutes: int) -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    reschedule(crawl_minutes, favorites_minutes)
    if runtime.shared_mode():
        for user_scope in runtime.scopes():
            if user_scope != runtime.OWNER:
                with runtime.use_scope(user_scope), runtime.session() as db:
                    cfg = repo.get_config(db)
                    reschedule(cfg.schedule_minutes, cfg.favorites_minutes)
    # 每日一次 SQLite 在线备份(滚动保留最近 7 份)
    _scheduler.add_job(
        lambda: backup.backup_all_scopes(Settings().data_dir.resolve()),
        IntervalTrigger(hours=24), id="system:backup",
        max_instances=1, coalesce=True, replace_existing=True,
    )
    _scheduler.start()


def reschedule(crawl_minutes: int, favorites_minutes: int) -> None:
    if _scheduler is None:
        return
    user_scope = runtime.scope()
    for name, minutes in (("crawl", crawl_minutes), ("favorites", favorites_minutes)):
        _scheduler.add_job(_run_for_scope, IntervalTrigger(minutes=max(1, minutes)),
                           args=(user_scope, name == "favorites"), id=f"{user_scope}:{name}",
                           max_instances=1, coalesce=True, replace_existing=True)


def delay_after_manual(include_favorites: bool = True) -> None:
    """手动跑完 → 把下一次定时往后推一个周期, 避免刚跑完又定时跑一遍。"""
    if _scheduler is None:
        return
    scope = runtime.scope()
    names = ["crawl", "favorites"] if include_favorites else ["crawl"]
    for name in names:
        job = _scheduler.get_job(f"{scope}:{name}")
        if job is None:
            continue
        job.modify(next_run_time=datetime.now() + job.trigger.interval)


def ensure_scheduled(crawl_minutes: int, favorites_minutes: int) -> None:
    if _scheduler is None:
        return
    scope = runtime.scope()
    if _scheduler.get_job(f"{scope}:crawl") is None or _scheduler.get_job(f"{scope}:favorites") is None:
        reschedule(crawl_minutes, favorites_minutes)


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running
