"""FastAPI 控制台后端。"""
import json
import os
import re
import sys
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from . import runtime, runner, dto, login_runner, sharing
from .. import digest, service, notifier, review, trend
from ..models import Item
from ..storage import repo
from ..storage.orm import ItemRow, WatchFolder, WatchMatch, WatchRow

# 商品排序: 前端下拉的取值, 也是本人默认排序的合法范围
SORTS = {"published-desc", "published-asc", "price-asc", "price-desc"}

app = FastAPI(title="海鲜价格监控")


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
    last_runs = repo.watch_last_runs(s)
    return [
        dto.watchrow_to_out(w).model_copy(update={"last_run_at": dto._iso(last_runs.get(w.id))})
        for w in repo.list_watches(s)
    ]


@app.post("/api/watches", response_model=dto.WatchOut)
def api_create_watch(body: dto.WatchIn, s: Session = Depends(get_db)):
    from . import scheduler

    validate_folder(s, body.folder_id)
    row = repo.add_watch(s, **dto.watchin_to_fields(body))
    cfg = repo.get_config(s)
    scheduler.ensure_scheduled(cfg.schedule_minutes, cfg.favorites_minutes)
    sharing.invalidate()
    return dto.watchrow_to_out(row)


@app.put("/api/watches/{wid}", response_model=dto.WatchOut)
def api_update_watch(wid: int, body: dto.WatchIn, s: Session = Depends(get_db)):
    validate_folder(s, body.folder_id)
    fields = dto.watchin_to_fields(body)
    for field in ("public", "folder_id", "archived", "target_price"):
        if field not in body.model_fields_set:
            fields.pop(field)
    row = repo.update_watch(s, wid, **fields)
    if row is None:
        raise HTTPException(404, "watch not found")
    sharing.invalidate()
    return dto.watchrow_to_out(row)


@app.delete("/api/watches/{wid}")
def api_delete_watch(wid: int, s: Session = Depends(get_db)):
    repo.delete_watch(s, wid)
    sharing.invalidate()
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


@app.put("/api/watch-folders/{fid}", response_model=dto.FolderOut)
def api_rename_folder(fid: int, body: FolderName, s: Session = Depends(get_db)):
    folder = s.get(WatchFolder, fid)
    if folder is None:
        raise HTTPException(404, "文件夹不存在")
    name = body.name.strip()
    if not name or len(name) > 80:
        raise HTTPException(422, "文件夹名称须为 1–80 字")
    conflict = s.scalar(select(WatchFolder).where(WatchFolder.name == name, WatchFolder.id != fid))
    if conflict is not None:
        raise HTTPException(409, "已有同名文件夹")
    folder.name = name
    s.commit()
    sharing.invalidate()
    return dto.FolderOut(id=folder.id, name=folder.name)


@app.delete("/api/watch-folders/{fid}")
def api_delete_folder(fid: int, s: Session = Depends(get_db)):
    folder = s.get(WatchFolder, fid)
    if folder is None:
        raise HTTPException(404, "文件夹不存在")
    s.execute(update(WatchRow).where(WatchRow.folder_id == fid).values(folder_id=None))
    s.delete(folder)
    s.commit()
    sharing.invalidate()
    return {"ok": True}


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


@app.get("/api/price-trend")
def api_price_trend(watch_ids: str = "", mode: str = "all", tz: int = 480,
                    min_price: float | None = None, seat: str = "",
                    s: Session = Depends(get_db)):
    """一个或多个条件内的价格总览: 分桶后的最低/P25/中位序列 + 席种筛选 + 跨组对比。"""
    ids = sorted({int(part) for part in watch_ids.split(",") if part.strip().isdigit()})
    if not ids:
        raise HTTPException(422, "请先选择一个条件")
    if len(ids) > 50:
        raise HTTPException(422, "一次最多汇总 50 个条件")
    if mode not in trend.MODES:
        raise HTTPException(422, "mode 只能是 all / day / week / month")
    if not -720 <= tz <= 840:
        raise HTTPException(422, "时区偏移超出范围")
    if min_price is not None and min_price < 0:
        raise HTTPException(422, "价格下限不能是负数")

    attrs = repo.item_attrs(s, ids)
    seats = sorted({str(meta["seat"]) for meta in attrs.values()
                    if meta and meta.get("seat") and meta.get("seat") != "未知"})
    rows = repo.trend_rows(s, ids)
    seat_clean = seat.strip()
    if seat_clean:
        seat_ids = {iid for iid, meta in attrs.items() if meta and meta.get("seat") == seat_clean}
        rows = [row for row in rows if str(row[0]) in seat_ids]
    comparable = {item_id for item_id, meta in attrs.items() if trend.is_comparable(meta)}
    data = trend.build(rows, mode=mode, tz_minutes=tz, min_price=min_price,
                       comparable_ids=comparable if attrs else None)
    # 只统计真的画进图里的商品, 否则会把已被筛掉的兑换码也算进「另有 N 件」
    drawn = {item["item_id"] for item in data["items"]}
    stats_excluded = sum(1 for item_id in drawn if not trend.is_comparable(attrs.get(item_id)))
    groups = digest.compute_stats(s, watch_ids=ids) if len(ids) > 1 else []
    return {
        "mode": data["mode"],
        "from": dto._iso(data["from"]),
        "to": dto._iso(data["to"]),
        "observations": data["observations"],
        "items_total": data["items_total"],
        "stats_excluded": stats_excluded,
        "auto_floor": data["auto_floor"],
        "excluded": data["excluded"],
        "summary": data["summary"],
        "seats": seats,
        "groups": groups,
        "series": [{"t": dto._iso(point["t"]), "min": point["min"], "p25": point.get("p25"),
                    "median": point["median"], "count": point["count"]}
                   for point in data["series"]],
        "items": [{"item_id": item["item_id"], "title": item["title"],
                   "points": [{"t": dto._iso(point["t"]), "price": point["price"]}
                              for point in item["points"]]}
                  for item in data["items"]],
    }


class DigestIn(BaseModel):
    watch_ids: list[int] | None = None
    use_llm: bool = True


@app.post("/api/digest")
def api_digest(body: DigestIn | None = None, s: Session = Depends(get_db)):
    """生成简短行情日报(先 SQL 统计, 可选调用 LLM 概括趋势与不确定性)。"""
    settings = runtime.effective_settings(repo.get_config(s))
    ids = body.watch_ids if body else None
    use_llm = body.use_llm if body else True
    return digest.generate_digest(s, settings, watch_ids=ids, use_llm=use_llm)


# ---------- config ----------
@app.get("/api/config", response_model=dto.ConfigOut)
def api_get_config(s: Session = Depends(get_db)):
    return dto.config_to_out(repo.get_config(s), member=runtime.scope() != runtime.OWNER)


@app.put("/api/config", response_model=dto.ConfigOut)
def api_put_config(body: dto.ConfigIn, s: Session = Depends(get_db)):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    member = runtime.scope() != runtime.OWNER
    if "default_sort" in fields and fields["default_sort"] not in SORTS:
        raise HTTPException(422, "排序方式无效")
    if "notify_to" in fields and isinstance(fields["notify_to"], str):
        fields["notify_to"] = fields["notify_to"].strip()
    if member:
        for field in ("smtp_host", "smtp_port", "smtp_user", "smtp_pass",
                      "search_url", "favorites_url", "headless"):
            fields.pop(field, None)
        if "review_base_url" in fields:
            url = fields["review_base_url"].strip().rstrip("/")
            if url not in runtime.member_review_urls():
                raise HTTPException(422, "请选择管理员允许的模型接口")
            fields["review_base_url"] = url

    # 全员数值范围校验(成员部分上限更严; 错误提示统一用中文字段名)
    min_interval = 15 if member else 1
    bounds = (
        ("schedule_minutes", "推荐抓取间隔", min_interval, 10_080),
        ("favorites_minutes", "收藏刷新间隔", min_interval, 10_080),
        ("min_drop_pct", "降价阈值（%）", 0, 100),
        ("min_drop_abs", "降价阈值（¥）", 0, 1_000_000),
        ("search_max_pages", "搜索翻页上限", 1, 10),
        ("favorites_max_pages", "收藏翻页上限", 1, 20),
        ("liveness_max_checks", "死链核活上限", 0, 30 if member else 100),
        ("review_timeout", "AI 审核超时", 1, 120 if member else 300),
        ("review_temperature", "模型温度", 0, 2),
        ("review_max_tokens", "最大输出 token", 1, 16_000 if member else 32_000),
        ("action_delay_min", "操作间隔下限", 0, 120),
        ("action_delay_max", "操作间隔上限", 0, 120),
        ("smtp_port", "SMTP 端口", 1, 65_535),
    )
    for field, label, minimum, maximum in bounds:
        if field in fields and not minimum <= fields[field] <= maximum:
            raise HTTPException(422, f"{label}须在 {minimum}–{maximum} 之间")
    cur_cfg = repo.get_config(s)
    d_min = fields.get("action_delay_min", cur_cfg.action_delay_min)
    d_max = fields.get("action_delay_max", cur_cfg.action_delay_max)
    if d_min > d_max:
        raise HTTPException(422, "操作间隔下限不能大于上限")
    cfg = repo.update_config(s, **fields)
    try:
        from . import scheduler
        scheduler.reschedule(cfg.schedule_minutes, cfg.favorites_minutes)
    except Exception:
        pass
    return dto.config_to_out(cfg, member=member)


@app.post("/api/test-email")
async def api_test_email(s: Session = Depends(get_db)):
    """用当前(已保存的)配置发一封测试邮件; 成员未填收件邮箱时发往管理员默认邮箱。"""
    cfg = repo.get_config(s)
    member = runtime.scope() != runtime.OWNER
    settings = runtime.effective_settings(cfg)
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_pass):
        msg = "站点尚未配置发件邮箱，请联系管理员" if member else "请先配置并保存 SMTP 发件信息"
        return {"ok": False, "error": msg}
    try:
        await run_in_threadpool(notifier.send_test, settings)
        target = (cfg.notify_to or "").strip() if member else (settings.notify_to or settings.smtp_user)
        return {"ok": True, "to": target or "管理员默认邮箱"}
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


class ManualFavoriteIn(BaseModel):
    url_or_id: str
    title: str | None = None
    price: float | None = None


_ITEM_ID_RE = re.compile(r"(?:[?&]id=|/item/)(\d{8,20})|^\s*(\d{8,20})\s*$")


@app.post("/api/favorites/manual")
def api_manual_favorite(body: ManualFavoriteIn, s: Session = Depends(get_db)):
    """手动粘贴闲鱼商品链接或商品 ID 加入本地跟踪(后续复检自动同步真实标题与价格)。"""
    raw = body.url_or_id.strip()
    m = _ITEM_ID_RE.search(raw)
    if not m:
        raise HTTPException(422, "请输入有效的闲鱼商品链接（含 id=数字）或纯数字商品 ID")
    item_id = m.group(1) or m.group(2)
    url = f"https://www.goofish.com/item?id={item_id}"
    title = (body.title or "").strip() or f"手动添加商品 #{item_id}"
    price = float(body.price) if body.price is not None and body.price >= 0 else 0.0
    item = Item(item_id=item_id, title=title, url=url, price=price)
    save_favorite_and_schedule(s, item_id, item=item)
    return {"ok": True, "item_id": item_id, "url": url}


@app.delete("/api/favorites/{item_id}")
def api_unfavorite(item_id: str, s: Session = Depends(get_db)):
    """取消站内收藏, 商品退回待审推荐。"""
    if not repo.clear_local_favorite(s, item_id):
        raise HTTPException(404, "这件商品不在站内收藏里")
    return {"ok": True}


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
    own = [
        {"item_id": e.item_id, "type": e.type, "payload": json.loads(e.payload),
         "created_at": dto._iso(e.created_at)}   # 标 UTC, 前端才能转本地时区(与其它时间一致)
        for e in repo.recent_events(s)
    ]
    pub = sharing.public_drop_events(limit=30)
    if not pub:
        return own
    seen = {(e["item_id"], e["type"], e["created_at"]) for e in own}
    merged = own + [e for e in pub if (e["item_id"], e["type"], e["created_at"]) not in seen]
    merged.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return merged[:100]


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
    """watch=None → 全量; watch=条件名 → 只跑该条件。排入单 worker 队列, 不因他人抓取被跳过。"""
    reason = runtime.search_block_reason(runtime.effective_settings(repo.get_config(s)))
    if reason:
        raise HTTPException(409, reason)
    res = runner.enqueue_crawl(watch, manual=True)
    if res.get("status") == "busy":
        raise HTTPException(409, "你的抓取正在进行中，请稍后")
    return res


@app.get("/api/status")
def api_status(s: Session = Depends(get_db)):
    cfg = repo.get_config(s)
    pos = runner.queue_position()
    return {
        "running": runtime.job_state()["running"],
        "queued": pos > 0,
        "queue_position": pos,
        "progress": runtime.job_state().get("progress"),
        "last": runtime.job_state()["last"],
        "paused": cfg.paused,
        "schedule_minutes": cfg.schedule_minutes,
        "version": os.environ.get("XIANYU_APP_VERSION") or "dev",
        "build_time": os.environ.get("XIANYU_APP_BUILD_TIME") or None,
    }


# ---------- static SPA (前端构建产物, C4) ----------
if _STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")
    if (_STATIC_DIR / "tabler").exists():      # 自托管的图标字体(快照里要能内联)
        app.mount("/tabler", StaticFiles(directory=_STATIC_DIR / "tabler"), name="tabler")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        index = _STATIC_DIR / "index.html"
        if index.exists():
            # 入口 HTML 不许缓存: 否则手机浏览器会一直跑旧 bundle, 刷新也看不到更新
            return FileResponse(index, headers={"Cache-Control": "no-cache, must-revalidate"})
        raise HTTPException(404)
