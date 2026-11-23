"""SQLite 在线备份: 用 sqlite3.Connection.backup() 安全复制库文件, 滚动保留最近 N 份。"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def backup_sqlite(db_path: Path, backup_dir: Path | None = None, keep: int = 7) -> Path | None:
    """备份单个 SQLite 数据库到 backups/xianyu-YYYYMMDD.db, 保留最近 keep 份。"""
    if not db_path.is_file():
        return None
    target_dir = backup_dir or (db_path.parent / "backups")
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    dest = target_dir / f"{db_path.stem}-{stamp}.db"
    tmp = target_dir / f".{db_path.stem}-{stamp}.tmp"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    tmp.replace(dest)
    old = sorted(target_dir.glob(f"{db_path.stem}-*.db"), reverse=True)
    for extra in old[keep:]:
        try:
            extra.unlink()
        except OSError:
            pass
    return dest


def backup_all_scopes(data_dir: Path, keep: int = 7) -> int:
    """备份管理员主库及所有成员库(位于 data/users/<scope>/xianyu.db)。"""
    done = 0
    for db_file in [data_dir / "xianyu.db", *(data_dir / "users").glob("*/xianyu.db")]:
        if not db_file.is_file():
            continue
        try:
            if backup_sqlite(db_file, keep=keep) is not None:
                done += 1
        except Exception:
            logger.warning("备份数据库失败: %s", db_file, exc_info=True)
    return done
