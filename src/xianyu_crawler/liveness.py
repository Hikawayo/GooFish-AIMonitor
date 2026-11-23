"""商品存活性探测: 打开详情页, 拦截 mtop 详情接口的 ret 码判定死链。

权威信号(真实验证):
- 活: mtop.taobao.idle.pc.detail → ret ["SUCCESS::调用成功"]
- 死: ret ["FAIL_BIZ_ITEM_DEL_NOT_FOUND::您要看的宝贝不存在或已被删除啦!"]

保守原则: 只在拿到明确"不存在/已删除/已下架"信号时判死; 其它(含拿不到 ret、
风控、超时)一律视为"活", 绝不误杀在售商品(误杀 = 用户错过好货, 代价更高)。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

from .parsing import to_price

DETAIL_API = "mtop.taobao.idle.pc.detail"
_DEAD_MARKERS = ("ITEM_DEL", "不存在", "已被删除", "已删除", "已下架", "下架", "ITEM_NOT_FOUND")


def sold_reason(item: dict) -> str | None:
    """已售出的商品接口仍回 SUCCESS, 只有 itemStatus 变负(-2), 必须单独认。"""
    status = item.get("itemStatus")
    if isinstance(status, (int, float)) and not isinstance(status, bool) and status < 0:
        return "已售出" if int(status) == -2 else "已下架"
    return None

_ITEM_URL = "https://www.goofish.com/item?id={}"


def _ret_blob(ret: object) -> str:
    if isinstance(ret, list):
        return " ".join(str(x) for x in ret)
    return str(ret or "")


def _to_int(v: object) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _extract_stats(detail: dict | None) -> dict | None:
    """从详情接口的 data.itemDO 取浏览/收藏/想要次数。全无则返回 None。"""
    item = (((detail or {}).get("data") or {}).get("itemDO")) or {}
    stats = {
        "browse_count": _to_int(item.get("browseCnt")),
        "collect_count": _to_int(item.get("collectCnt")),
        "want_count": _to_int(item.get("wantCnt")),
    }
    return stats if any(v is not None for v in stats.values()) else None


def _read_detail(ctx, item_id: str, wait_ms: int) -> dict | None:
    if not item_id.isascii() or not item_id.isdecimal():
        return None
    page = ctx.new_page()
    captured: dict = {"json": None}

    def _on_response(resp) -> None:
        if f"{DETAIL_API}/" in resp.url and captured["json"] is None:
            try:
                captured["json"] = resp.json()
            except Exception:
                pass

    page.on("response", _on_response)
    try:
        page.goto(_ITEM_URL.format(item_id), wait_until="domcontentloaded", timeout=15_000)
        page.wait_for_timeout(wait_ms)
    except Exception:
        return None
    finally:
        page.close()

    return captured["json"]


def check_liveness(ctx, item_id: str, wait_ms: int = 2500) -> tuple[bool, str | None, dict | None]:
    """打开详情页核活并读取互动次数。拿不到明确下架信号时保持原状态。"""
    detail = _read_detail(ctx, item_id, wait_ms)
    stats = _extract_stats(detail)
    blob = _ret_blob((detail or {}).get("ret"))
    if "SUCCESS" in blob:
        item = ((detail or {}).get("data") or {}).get("itemDO") or {}
        reason = sold_reason(item)
        if reason:
            return True, reason, stats
        return False, None, stats
    if any(m in blob for m in _DEAD_MARKERS):
        return True, "已删除", stats
    return False, None, stats        # 不确定 → 保守判活


def parse_detail_price(detail: dict | None, item_id: str) -> tuple[float | None, bool]:
    """返回当前挂牌价和明确失效标记。未知结果保留原价及原状态。"""
    if not detail:
        return None, False
    blob = _ret_blob(detail.get("ret"))
    if "SUCCESS" not in blob:
        return None, any(marker in blob for marker in _DEAD_MARKERS)
    item = (detail.get("data") or {}).get("itemDO") or {}
    if str(item.get("itemId")) != item_id:
        return None, False
    if sold_reason(item):
        return None, True
    price = to_price(item.get("soldPrice"))
    return (price if price is not None and isfinite(price) and price > 0 else None), False


def check_detail_price(ctx, item_id: str) -> tuple[float | None, bool]:
    return parse_detail_price(_read_detail(ctx, item_id, 2500), item_id)


@dataclass
class DetailReading:
    """一次详情读取的结果: 现价、是否失效, 卖家最初挂的价格, 以及平台优惠价。"""
    price: float | None = None
    dead: bool = False
    original_price: float | None = None     # itemDO.originalPrice, 卖家降价前的挂牌价
    published_at: datetime | None = None    # itemDO.gmtCreate, naive UTC
    promo_price: float | None = None        # 平台优惠后的实付价(itemDO.promotionPriceDO)
    dead_reason: str | None = None          # 已售出 / 已下架 / 详情已失效


def _promo_price(item: dict, listing: float | None) -> float | None:
    """平台优惠价: 挂牌价不动, 但买家实付更低(「平台优惠 减¥1700」)。

    详情接口放在 promotionPriceDO.promotionPriceMin; 只有真的低于挂牌价才算数。
    """
    block = item.get("promotionPriceDO")
    if not isinstance(block, dict):
        return None
    for key in ("promotionPriceMin", "promotionPrice", "minPrice", "discountPrice"):
        value = to_price(block.get(key))
        if value is None or not isfinite(value) or value <= 0:
            continue
        if listing is not None and value >= listing:
            return None                     # 没便宜就不当成优惠价
        return value
    return None


def parse_detail(detail: dict | None, item_id: str) -> DetailReading:
    """在现价之外补上「发布价 + 发布时间 + 平台优惠价」, 用来给走势补一个最早的点。"""
    price, dead = parse_detail_price(detail, item_id)
    reading = DetailReading(price=price, dead=dead)
    if dead or not detail:
        if dead:
            item = ((detail or {}).get("data") or {}).get("itemDO") or {}
            reading.dead_reason = sold_reason(item) or "详情已失效"
        return reading
    item = (detail.get("data") or {}).get("itemDO") or {}
    if str(item.get("itemId")) != item_id:
        return reading
    reading.promo_price = _promo_price(item, price)
    original = to_price(item.get("originalPrice"))
    if original is not None and isfinite(original) and original > 0:
        reading.original_price = original
    created = item.get("gmtCreate")
    if isinstance(created, (int, float)) and created > 0:
        reading.published_at = datetime.fromtimestamp(created / 1000, tz=timezone.utc).replace(tzinfo=None)
    return reading


def check_detail(ctx, item_id: str) -> DetailReading:
    return parse_detail(_read_detail(ctx, item_id, 2500), item_id)
