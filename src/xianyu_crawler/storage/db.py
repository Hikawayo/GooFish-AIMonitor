"""DB session 工厂。"""
from __future__ import annotations

import threading

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .orm import Base
from .migrate import ensure_columns

_READY: set[str] = set()          # 每个 DB 文件每进程只建表/补列一次
_ENGINES: dict[str, Engine] = {}  # 复用连接池: 每请求新建 engine 会一直漏连接
_LOCK = threading.Lock()


def _engine(url: str) -> Engine:
    engine = _ENGINES.get(url)
    if engine is None:
        engine = create_engine(url, future=True)
        _ENGINES[url] = engine
    return engine


def make_session(url: str, create: bool = False) -> Session:
    if ":memory:" in url:                       # 每个会话独立内存库, 不复用
        engine = create_engine(url, future=True)
        if create:
            Base.metadata.create_all(engine)
        return Session(engine, future=True)

    engine = _engine(url)
    if create and url not in _READY:
        # 首屏会并发打进来几个请求; 不加锁时两个线程会同时 CREATE TABLE 而报
        # "table items already exists", 新账号第一次打开页面就是一片 500。
        with _LOCK:
            if url not in _READY:
                Base.metadata.create_all(engine)        # 建缺失的表
                if url.startswith("sqlite:///"):
                    ensure_columns(url[len("sqlite:///"):])   # 给旧表补缺失列
                _READY.add(url)
    return Session(engine, future=True)
