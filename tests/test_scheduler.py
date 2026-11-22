def test_scheduler_lifecycle(monkeypatch):
    from xianyu_crawler.web import scheduler, runner
    monkeypatch.setattr(runner, "crawl", lambda: {"ok": True})            # 防止真跑浏览器
    monkeypatch.setattr(runner, "refresh_favorites", lambda: {"ok": True})
    assert scheduler.is_running() is False
    scheduler.start(60, 30)        # 推荐 60 分钟 / 收藏 30 分钟, 测试窗口内不触发
    try:
        assert scheduler.is_running() is True
        scheduler.reschedule(120, 15)   # 两个间隔都改, 不应报错
    finally:
        scheduler.shutdown()
    assert scheduler.is_running() is False


def test_manual_run_pushes_next_scheduled_time(monkeypatch):
    """手动跑完把下一次定时往后推一个周期, 不跟随原定时间。"""
    from datetime import datetime, timedelta

    from xianyu_crawler.web import scheduler, runner
    monkeypatch.setattr(runner, "crawl", lambda: {"ok": True})
    monkeypatch.setattr(runner, "refresh_favorites", lambda: {"ok": True})
    scheduler.start(120, 30)
    try:
        job_id = f"{__import__('xianyu_crawler.web.runtime', fromlist=['*']).scope()}:crawl"
        sched = scheduler._scheduler                              # noqa: SLF001 - 测试要看真实调度状态
        assert sched is not None
        job = sched.get_job(job_id)
        assert job is not None
        # 把下一次拖到 1 分钟后, 模拟"马上要到点"
        job.modify(next_run_time=datetime.now() + timedelta(minutes=1))
        scheduler.delay_after_manual(include_favorites=True)
        moved_job = sched.get_job(job_id)
        assert moved_job is not None and moved_job.next_run_time is not None
        gap = moved_job.next_run_time.replace(tzinfo=None) - datetime.now()
        assert gap > timedelta(minutes=100)          # 被推回 120 分钟
    finally:
        scheduler.shutdown()
