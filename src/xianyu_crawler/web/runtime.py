"""请求和后台任务使用相同的用户数据范围。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from pathlib import Path

from ..config import Settings
from ..storage.db import make_session
from ..storage.orm import AppConfig
from .. import service

DB_URL = f"sqlite:///{(Settings().data_dir.resolve() / 'xianyu.db')}"
OWNER = "owner"
SCOPE_ID = re.compile(r"[0-9a-f]{64}")
_scope: ContextVar[str] = ContextVar("user_scope", default=OWNER)
_jobs: dict[str, dict] = {}
_logins: dict[str, dict] = {}


def set_db_url(url: str) -> None:
    global DB_URL
    DB_URL = url


def scope() -> str:
    return _scope.get()


def shared_mode() -> bool:
    return Settings().sso_enabled


def has_login() -> bool:
    return (data_dir() / "storage_state.json").is_file()


def member_review_urls() -> set[str]:
    return {url.strip().rstrip("/") for url in Settings().member_review_urls.split(",")
            if url.strip().startswith("https://")}


def effective_settings(cfg: AppConfig) -> Settings:
    settings = service.effective_settings(cfg)
    if scope() == OWNER:
        return settings
    default = Settings.model_fields["review_base_url"].default
    return settings.model_copy(update={
        "data_dir": data_dir(),
        "review_base_url": cfg.review_base_url or default,
        "review_api_token": cfg.review_api_token,
        "review_enabled": cfg.review_enabled,
        "smtp_host": None, "smtp_user": None, "smtp_pass": None, "notify_to": None,
    })


def can_search(settings: Settings) -> bool:
    return not shared_mode() or bool(has_login() and _review_ready(settings))


def _review_ready(settings: Settings) -> bool:
    """AI 审核没开(人工审核)就不需要 Key, 只认登录态。"""
    if not settings.review_enabled:
        return True
    return bool(settings.review_api_token and
                (scope() == OWNER or settings.review_base_url.rstrip("/") in member_review_urls()))


def search_block_reason(settings: Settings) -> str | None:
    """跑不了搜索时给用户一句能动手的原因; 能跑返回 None。"""
    if can_search(settings):
        return None
    if not has_login():
        return "请先扫码登录闲鱼"
    return "请先配置 AI API Key，或在设置里关掉 AI 审核改由自己审核"


@contextmanager
def use_scope(user_scope: str) -> Iterator[None]:
    if user_scope != OWNER and not SCOPE_ID.fullmatch(user_scope):
        raise ValueError("Invalid data scope")
    token = _scope.set(user_scope)
    try:
        yield
    finally:
        _scope.reset(token)


def data_dir() -> Path:
    root = Settings().data_dir.resolve()
    return root if scope() == OWNER else root / "users" / scope()


def session():
    if scope() == OWNER:
        return make_session(DB_URL, create=True)
    path = data_dir()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return make_session(f"sqlite:///{path / 'xianyu.db'}", create=True)


def scopes() -> list[str]:
    root = Settings().data_dir.resolve() / "users"
    members = [p.name for p in root.iterdir() if SCOPE_ID.fullmatch(p.name)
               and not p.is_symlink() and (p / "xianyu.db").is_file()] if root.exists() else []
    return [OWNER, *sorted(members)]


def job_state() -> dict:
    return _jobs.setdefault(scope(), {"running": False, "last": None})


def login_state() -> dict:
    return _logins.setdefault(scope(), {"status": "idle", "qr": None, "message": "", "at": None})


def start_thread(target, *args) -> None:
    context = copy_context()
    threading.Thread(target=context.run, args=(target, *args), daemon=True).start()


def authenticate(ticket: str | None) -> str | None:
    settings = Settings()
    if not settings.sso_enabled:
        return OWNER
    if not ticket or len(ticket) > 4096 or not SCOPE_ID.fullmatch(settings.sso_owner_scope):
        return None
    try:
        payload, signature = ticket.split(".")
        key = (settings.data_dir / "sso.key").read_bytes().strip()
        expected = base64.urlsafe_b64encode(hmac.digest(key, payload.encode("ascii"), "sha256"))
        if len(key) < 32 or not hmac.compare_digest(signature.encode("ascii"), expected.rstrip(b"=")):
            return None
        identity = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        email = identity["e"].strip().casefold()
        if identity.get("aud") != "goofish" or not email or identity["exp"] <= time.time():
            return None
        user_scope = hashlib.sha256(email.encode("utf-8")).hexdigest()
        return OWNER if hmac.compare_digest(user_scope, settings.sso_owner_scope) else user_scope
    except (OSError, AttributeError, ValueError, KeyError, TypeError):
        return None
