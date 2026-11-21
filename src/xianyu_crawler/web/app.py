"""FastAPI 控制台后端。"""
import json
import sys
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from . import runtime, runner, dto, login_runner, sharing
from .. import service, notifier, review
from ..models import Item
from ..storage import repo
from ..storage.orm import ItemRow, WatchFolder, WatchMatch

app = FastAPI(title="闲鱼控制台")


@app.middleware("http")
async def bind_user(request: Request, call_next):
    user_scope = runtime.authenticate(request.cookies.get("sso"))
    if user_scope is None:
        return JSONResponse({"detail": "请先通过统一登录进入控制台"}, status_code=401)
    with runtime.use_scope(user_scope):
        response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

# 打包(PyInstaller)后静态资源在 _MEIPASS 下; 开发期就在包目录旁
if getattr(sys, "frozen", False):
    _STATIC_DIR = Path(getattr(sys, "_MEIPASS", ".")) / "xianyu_crawler" / "web" / "static"
else:
    _STATIC_DIR = Path(__file__).parent / "static"


def get_db():
    s = runtime.session()
    try:
        yield s
    finally:
        s.close()


@app.get("/api/access")
def api_access():
    return {"member": runtime.scope() != runtime.OWNER,
            "shared": runtime.shared_mode(),
            "review_urls": sorted(runtime.member_review_urls()) if runtime.scope() != runtime.OWNER else []}


# ---------- watches ----------
@app.get("/api/watches", response_model=list[dto.WatchOut])
def api_list_watches(s: Session = Depends(get_db)):
    return [dto.watchrow_to_out(w) for w in repo.list_watches(s)]


@app.post("/api/watches", response_model=dto.WatchOut)
def api_create_watch(body: dto.WatchIn, s: Session = Depends(get_db)):
    validate_folder(s, body.folder_id)
    return dto.watchrow_to_out(repo.add_watch(s, **dto.watchin_to_fields(body)))


@app.put("/api/watches/{wid}", response_model=dto.WatchOut)
def api_update_watch(wid: int, body: dto.WatchIn, s: Session = Depends(get_db)):
    validate_folder(s, body.folder_id)
    fields = dto.watchin_to_fields(body)
    for field in ("public", "folder_id"):
        if field not in body.model_fields_set:
            fields.pop(field)
    row = repo.update_watch(s, wid, **fields)
    if row is None:
        raise HTTPException(404, "watch not found")
    return dto.watchrow_to_out(row)


@app.delete("/api/watches/{wid}")
def api_delete_watch(wid: int, s: Session = Depends(get_db)):
    repo.delete_watch(s, wid)
    return {"ok": True}


def validate_folder(s: Session, folder_id: int | None) -> None:
    if folder_id is not None and s.get(WatchFolder, folder_id) is None:
        raise HTTPException(404, "文件夹不存在")


@app.get("/api/watch-folders", response_model=list[dto.FolderOut])
def api_folders(s: Session = Depends(get_db)):
    return [dto.FolderOut(id=folder.id, name=folder.name)
            for folder in s.scalars(select(WatchFolder).order_by(WatchFolder.id))]


class FolderName(BaseModel):
    name: str


@app.post("/api/watch-folders", response_model=dto.FolderOut)
def api_create_folder(body: FolderName, s: Session = Depends(get_db)):
    name = body.name.strip()
    if not name or len(name) > 80:
        raise HTTPException(422, "文件夹名称须为 1–80 字")
    existing = s.scalar(select(WatchFolder).where(WatchFolder.name == name))
    if existing is None:
        existing = WatchFolder(name=name)
        s.add(existing)
        s.commit()
    return dto.FolderOut(id=existing.id, name=existing.name)


@app.get("/api/shared")
def api_shared():
    return sharing.catalog()


@app.post("/api/shared/{folder_key}/{item_id}/favorite")
def api_shared_favorite(folder_key: str, item_id: str, s: Session = Depends(get_db)):
    item = sharing.get_item(folder_key, item_id)
    if item is None:
        raise HTTPException(404, "公开商品不存在")
    return {"ok": save_favorite_and_schedule(s, item_id, item=item, folder_key=folder_key)}


@app.get("/api/shared/{folder_key}/{item_id}/prices")
def api_shared_prices(folder_key: str, item_id: str):
    points = sharing.price_history(folder_key, item_id)
    if points is None:
        raise HTTPException(404, "公开商品不存在")
    return points


@app.get("/api/items/{item_id}/prices")
def api_item_prices(item_id: str, s: Session = Depends(get_db)):
    if s.get(ItemRow, item_id) is None:
        raise HTTPException(404, "商品不存在")
    return [{"price": point.price, "observed_at": dto._iso(point.observed_at)}
            for point in repo.price_history(s, item_id)]


# ---------- config ----------
@app.get("/api/config", response_model=dto.ConfigOut)
def api_get_config(s: Session = Depends(get_db)):
    return dto.config_to_out(repo.get_config(s), member=runtime.scope() != runtime.OWNER)


@app.put("/api/config", response_model=dto.ConfigOut)
def api_put_config(body: dto.ConfigIn, s: Session = Depends(get_db)):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    member = runtime.scope() != runtime.OWNER
    if member:
        for field in ("smtp_host", "smtp_port", "smtp_user", "smtp_pass", "notify_to",
                      "search_url", "favorites_url", "headless"):
            fields.pop(field, None)
        if "review_base_url" in fields:
            url = fields["review_base_url"].strip().rstrip("/")
            if url not in runtime.member_review_urls():
                raise HTTPException(422, "请选择管理员允许的模型接口")
            fields["review_base_url"] = url
        for field, minimum, maximum in (
            ("schedule_minutes", 15, 10_080), ("favorites_minutes", 15, 10_080),
            ("search_max_pages", 1, 10), ("favorites_max_pages", 1, 20),
            ("liveness_max_checks", 0, 30), ("review_timeout", 1, 120),
            ("review_max_tokens", 1, 16_000),
        ):
            if field in fields and not minimum <= fields[field] <= maximum:
                raise HTTPException(422, f"{field} 须在 {minimum}–{maximum} 之间")
    cfg = repo.update_config(s, **fields)
    try:
        from . import scheduler
        scheduler.reschedule(cfg.schedule_minutes, cfg.favorites_minutes)
    except Exception:
        pass
    return dto.config_to_out(cfg, member=member)


@app.post("/api/test-email")
async def api_test_email(s: Session = Depends(get_db)):
    """用当前(已保存的)配置发一封测试邮件; 返回成功或错误原因。"""
    if runtime.scope() != runtime.OWNER:
        raise HTTPException(403, "成员邮箱通知暂未启用")
    settings = runtime.effective_settings(repo.get_config(s))
    try:
        await run_in_threadpool(notifier.send_test, settings)
        return {"ok": True, "to": settings.notify_to}
    except Exception as e:  # noqa: BLE001 - 把失败原因回显给控制台
        return {"ok": False, "error": str(e)}


@app.post("/api/test-review")
async def api_test_review(s: Session = Depends(get_db)):
    """用当前(已保存的)配置 + 真实「AI 审核要求」做一次真实审核; 回显成功或错误原因。"""
    settings = runtime.effective_settings(repo.get_config(s))
    if runtime.scope() != runtime.OWNER and (
        not settings.review_api_token or settings.review_base_url.rstrip("/") not in runtime.member_review_urls()
    ):
        raise HTTPException(409, "请先配置自己的 AI API Key 和模型接口")
    reqs = [w.requirement for w in repo.list_watches(s) if w.requirement]
    requirement = max(reqs, key=len) if reqs else None   # 用最长的要求, 最能压出推理模型的坑
    return await run_in_threadpool(review.test_review, settings, requirement)


# ---------- recommendations ----------
@app.get("/api/recommendations", response_model=list[dto.RecommendationOut])
def api_list_recs(status: str = "new", s: Session = Depends(get_db)):
    matches: dict[str, list[dto.WatchMatchOut]] = {}
    for match in s.scalars(select(WatchMatch)):
        matches.setdefault(match.item_id, []).append(dto.WatchMatchOut(
            watch_id=match.watch_id, price=match.price, rec_ok=match.ok, reason=match.reason))
    result = [dto.itemrow_to_rec(row) for row in repo.list_recommendations(s, status)]
    for item in result:
        item.watch_matches = matches.get(item.item_id, [])
    return result


@app.post("/api/recommendations/review")
def api_rereview(s: Session = Depends(get_db)):
    """一键 AI 审核: 用当前 LLM 配置对已入库的待审推荐重新审核(补审之前没跑通的), 不重新抓取。

    同步 def → FastAPI 在线程池里跑, LLM 调用阻塞该 worker, 与 session 同线程, 安全。
    """
    settings = runtime.effective_settings(repo.get_config(s))
    if runtime.scope() != runtime.OWNER and (
        not settings.review_api_token or settings.review_base_url.rstrip("/") not in runtime.member_review_urls()
    ):
        raise HTTPException(409, "请先配置自己的 AI API Key 和模型接口")
    return service.rereview_pending(s, settings)


@app.post("/api/recommendations/{item_id}/approve")
def api_approve(item_id: str, s: Session = Depends(get_db)):
    if not save_favorite_and_schedule(s, item_id):
        raise HTTPException(404, "商品不存在")
    service.record_manual_verdict(s, item_id, True)
    return {"ok": True}


def save_favorite_and_schedule(s: Session, item_id: str, item: Item | None = None,
                               folder_key: str | None = None) -> bool:
    from . import scheduler

    if not repo.save_local_favorite(s, item_id, item=item, folder_key=folder_key):
        return False
    cfg = repo.get_config(s)
    scheduler.ensure_scheduled(cfg.schedule_minutes, cfg.favorites_minutes)
    return True


@app.post("/api/recommendations/{item_id}/reject")
def api_reject(item_id: str, s: Session = Depends(get_db)):
    repo.set_rec_status(s, item_id, "rejected")
    service.record_manual_verdict(s, item_id, False)
    return {"ok": True}


@app.post("/api/recommendations/{item_id}/mute")
def api_mute(item_id: str, days: int = 7, s: Session = Depends(get_db)):
    """近期不看: days=1/7 暂时隐藏(到期重现), days=0 永久不看。"""
    service.mute_recommendation(s, item_id, days)
    return {"ok": True}


# ---------- favorites + drops ----------
@app.get("/api/favorites", response_model=list[dto.FavoriteOut])
def api_favorites(s: Session = Depends(get_db)):
    watch_ids = repo.item_watch_ids(s)
    result = [dto.itemrow_to_fav(r) for r in repo.list_favorites(s)]
    for item in result:
        item.watch_ids = watch_ids.get(item.item_id, [])
    return result


@app.get("/api/stats")
def api_stats(s: Session = Depends(get_db)):
    return repo.stats(s)


@app.get("/api/events")
def api_events(s: Session = Depends(get_db)):
    return [
        {"item_id": e.item_id, "type": e.type, "payload": json.loads(e.payload),
         "created_at": dto._iso(e.created_at)}   # 标 UTC, 前端才能转本地时区(与其它时间一致)
        for e in repo.recent_events(s)
    ]


# ---------- 扫码登录 ----------
@app.post("/api/login/start")
def api_login_start():
    """启动图形化扫码登录(后台开浏览器取二维码)。"""
    return login_runner.start()


@app.get("/api/login/status")
def api_login_status():
    """前端轮询: 登录状态 + 当前二维码(base64) + 是否已有登录态。"""
    return login_runner.status()


@app.post("/api/login/logout")
def api_login_logout():
    """退出登录 / 换号: 清除本地登录态。"""
    return login_runner.logout()


# ---------- run + status ----------
@app.post("/api/run")
def api_run(watch: str | None = None, s: Session = Depends(get_db)):
    """watch=None → 全量; watch=条件名 → 只跑该条件。"""
    reason = runtime.search_block_reason(runtime.effective_settings(repo.get_config(s)))
    if reason:
        raise HTTPException(409, reason)
    runtime.start_thread(runner.crawl, watch)
    return {"status": "queued", "scope": watch or "all"}


@app.get("/api/status")
def api_status(s: Session = Depends(get_db)):
    cfg = repo.get_config(s)
    return {
        "running": runtime.job_state()["running"],
        "last": runtime.job_state()["last"],
        "paused": cfg.paused,
        "schedule_minutes": cfg.schedule_minutes,
    }


# ---------- static SPA (前端构建产物, C4) ----------
if _STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        index = _STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(404)
