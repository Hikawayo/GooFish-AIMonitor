"""可选简短市场日报: 先用 SQL 统计客观数据, 再可选调用兼容 LLM 概括趋势与不确定性。

不让模型编造市场交易量或预测百分比; 未启用/未配置 LLM 时直接返回客观统计摘要。
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from . import review, trend
from .config import Settings
from .storage import repo

logger = logging.getLogger(__name__)

DIGEST_SYSTEM_PROMPT = (
    "你是二手挂牌行情简报助手。你只能依据用户提供的客观统计 JSON 写 3–5 句简短中文摘要。\n"
    "规则：\n"
    "1. 只描述观察到的在售挂牌价（最低价、P25、中位数、降价/涨价件数与跨组差异）。\n"
    "2. 严禁编造真实成交量、市场供需结论或预测未来涨跌百分比；挂牌消失不等于成交。\n"
    "3. 样本数少（如不足 5 件）时必须明确指出样本偏少、参考性有限。\n"
    "4. 输出纯中文段落，不要用 Markdown 标题或冗余客套话。"
)


def compute_stats(s: Session, watch_ids: list[int] | None = None) -> list[dict]:
    """按监控条件汇总客观统计(仅统计可比挂牌)。"""
    watches = repo.list_watches(s)
    if watch_ids:
        wanted = set(watch_ids)
        watches = [w for w in watches if w.id in wanted]
    out: list[dict] = []
    for w in watches:
        attrs = repo.item_attrs(s, [w.id])
        comparable = {iid for iid, meta in attrs.items() if trend.is_comparable(meta)}
        data = trend.build(repo.trend_rows(s, [w.id]), mode="day",
                           comparable_ids=comparable if attrs else None)
        summary = data["summary"]
        if summary["count"] == 0 and data["observations"] == 0:
            continue
        out.append({
            "watch_id": w.id,
            "name": w.name,
            "kind": w.kind or "general",
            "archived": bool(w.archived),
            "count": summary["count"],
            "min": summary["min"],
            "p25": summary["p25"],
            "median": summary["median"],
            "dropped": summary["dropped"],
            "raised": summary["raised"],
            "observations": data["observations"],
        })
    return out


def generate_digest(s: Session, settings: Settings, watch_ids: list[int] | None = None,
                    use_llm: bool = True) -> dict:
    """生成趋势简报: 返回 stats 列表与可选 LLM 概括文本。"""
    stats = compute_stats(s, watch_ids=watch_ids)
    if not stats:
        return {"stats": [], "summary": "暂无足够的价格观测数据。", "used_llm": False}

    lines = []
    for row in stats:
        seg = f"「{row['name']}」在售可比 {row['count']} 件"
        if row["min"] is not None:
            seg += f"，最低 ¥{round(row['min'])} / P25 ¥{round(row['p25'])} / 中位 ¥{round(row['median'])}"
        if row["dropped"] or row["raised"]:
            seg += f"（降价 {row['dropped']} / 涨价 {row['raised']}）"
        lines.append(seg)
    fallback = "；".join(lines) + "。"

    if not use_llm or not settings.review_enabled or not settings.review_api_token:
        return {"stats": stats, "summary": fallback, "used_llm": False}

    try:
        msgs = [
            {"role": "system", "content": DIGEST_SYSTEM_PROMPT},
            {"role": "user", "content": "客观统计数据：\n" + json.dumps(stats, ensure_ascii=False)},
        ]
        text = review._call_llm(msgs, settings).strip()
        return {"stats": stats, "summary": text or fallback, "used_llm": bool(text)}
    except Exception as e:  # noqa: BLE001 - LLM 失败时退回纯统计摘要
        logger.warning("生成 AI 简报失败, 回退统计摘要: %s", e)
        return {"stats": stats, "summary": fallback, "used_llm": False, "warn": f"AI 概括不可用：{e}"}
