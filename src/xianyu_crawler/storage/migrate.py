"""轻量列迁移: 给已存在的 SQLite 表补齐 ORM 新增列。

`create_all` 只建新表、不会给旧表加列。每次 ORM 加字段, 把 (表, 列, DDL) 追加到
下表即可; ensure_columns 幂等(列已存在则跳过), 容器每次启动自动跑 → 不用手动迁移。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

# (table, column, "DDL 类型 + 默认值") — 仅在列缺失时 ALTER ADD COLUMN
COLUMNS: list[tuple[str, str, str]] = [    ("items", "first_price", "REAL"),
    ("items", "original_price", "REAL"),
    ("items", "rec_reason", "TEXT"),
    ("items", "rec_ok", "BOOLEAN"),
    ("items", "dead", "BOOLEAN NOT NULL DEFAULT 0"),
    ("items", "dead_reason", "TEXT"),
    ("items", "dead_at", "DATETIME"),
    ("items", "price_changed_at", "DATETIME"),
    ("items", "publish_time", "DATETIME"),
    ("items", "muted_until", "DATETIME"),
    ("items", "want_count", "INTEGER"),
    ("items", "browse_count", "INTEGER"),
    ("items", "collect_count", "INTEGER"),
    ("items", "shared_folder_key", "TEXT"),
    ("items", "local_saved", "BOOLEAN NOT NULL DEFAULT 0"),
    ("items", "detail_checked_at", "DATETIME"),
    ("watches", "requirement", "TEXT"),
    ("watches", "public", "BOOLEAN NOT NULL DEFAULT 0"),
    ("watches", "folder_id", "INTEGER REFERENCES watch_folders(id)"),
    ("watch_matches", "title", "TEXT"),
    ("watch_matches", "url", "TEXT"),
    ("app_config", "review_model", "TEXT NOT NULL DEFAULT 'doubao-seed-2.0-pro'"),
    ("app_config", "favorites_minutes", "INTEGER NOT NULL DEFAULT 30"),
    ("app_config", "review_enabled", "BOOLEAN NOT NULL DEFAULT 1"),
    ("app_config", "review_base_url", "TEXT"),   # 空=回退本地 secret.env, 不写仓库
    ("app_config", "review_api_token", "TEXT"),
    ("app_config", "review_timeout", "REAL NOT NULL DEFAULT 30"),
    ("app_config", "review_temperature", "REAL NOT NULL DEFAULT 0"),
    ("app_config", "review_max_tokens", "INTEGER NOT NULL DEFAULT 2000"),
    ("app_config", "review_system_prompt", "TEXT"),
    ("app_config", "action_delay_min", "REAL NOT NULL DEFAULT 3"),
    ("app_config", "action_delay_max", "REAL NOT NULL DEFAULT 8"),
    ("app_config", "liveness_max_checks", "INTEGER NOT NULL DEFAULT 30"),
    ("app_config", "search_url", "TEXT NOT NULL DEFAULT 'https://www.goofish.com/search'"),
    ("app_config", "favorites_url", "TEXT NOT NULL DEFAULT 'https://www.goofish.com/collection'"),
    ("app_config", "smtp_host", "TEXT"),
    ("app_config", "smtp_port", "INTEGER"),
    ("app_config", "smtp_user", "TEXT"),
    ("app_config", "smtp_pass", "TEXT"),
    ("app_config", "notify_on_drop", "BOOLEAN NOT NULL DEFAULT 1"),
    ("app_config", "notify_on_favorite", "BOOLEAN NOT NULL DEFAULT 1"),
    ("app_config", "notify_on_login", "BOOLEAN NOT NULL DEFAULT 1"),
    ("app_config", "notify_on_new", "BOOLEAN NOT NULL DEFAULT 1"),
    ("app_config", "notify_on_sold", "BOOLEAN NOT NULL DEFAULT 1"),
]


def _cols(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


# 旧版默认提示词。存着这段的库说明用户从没自己改过, 清空让它回落到新的默认值;
# 用户自己写过的提示词原样保留。
LEGACY_DEFAULT_PROMPT = (
    "你是二手商品相关性筛选助手。判断每个商品是否符合用户的「要求」"
    "(型号/规格/成色/价格/正品等综合判断)。"
    "严格判断: 不确定或明显不符、或疑似钓鱼/配件 就 ok=false。"
)


def ensure_columns(db_path: str | Path) -> int:
    """给 db_path 补齐缺失列, 返回新增列数。表不存在则跳过(留给 create_all)。"""
    path = Path(db_path)
    if not path.exists():
        return 0
    con = sqlite3.connect(path)
    added = 0
    try:
        for table, col, ddl in COLUMNS:
            existing = _cols(con, table)
            if not existing or col in existing:
                continue
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
            added += 1
        if _cols(con, "app_config"):
            con.execute("UPDATE app_config SET review_system_prompt = NULL "
                        "WHERE review_system_prompt = ?", (LEGACY_DEFAULT_PROMPT,))
        if _cols(con, "watch_matches"):
            con.execute("""
                INSERT OR IGNORE INTO watch_matches
                    (watch_id, item_id, ok, reason, title, url, price, observed_at)
                SELECT w.id, i.item_id, i.rec_ok, i.rec_reason, i.title, i.url, i.latest_price, i.last_seen_at
                FROM watches w JOIN items i ON i.watch_name = w.name
                WHERE i.rec_reason IS NOT NULL OR i.rec_ok IS NOT NULL
            """)
            if _cols(con, "published_prices"):
                con.execute("""
                    INSERT INTO published_prices (watch_id, item_id, price, observed_at)
                    SELECT w.id, m.item_id, m.price, CURRENT_TIMESTAMP
                    FROM watches w JOIN watch_matches m ON m.watch_id = w.id
                    JOIN items i ON i.item_id = m.item_id
                    WHERE w.public = 1 AND m.ok = 1
                      AND (m.reason IS NULL OR m.reason != '(审核未运行)')
                      AND (w.requirement IS NULL OR w.requirement = '' OR m.reason IS NOT NULL)
                      AND (i.rec_status IS NULL OR i.rec_status != 'rejected')
                      AND i.dead = 0 AND (i.muted_until IS NULL OR i.muted_until <= CURRENT_TIMESTAMP)
                      AND NOT EXISTS (SELECT 1 FROM published_prices p
                          WHERE p.watch_id = w.id AND p.item_id = m.item_id)
                """)
        con.commit()
    finally:
        con.close()
    return added
