"""liveness._extract_stats: 从详情接口 data.itemDO 取浏览/收藏/想要次数。"""
from xianyu_crawler.liveness import _extract_stats


def test_extract_stats_from_item_do():
    detail = {"data": {"itemDO": {"browseCnt": 134, "collectCnt": 3, "wantCnt": 5, "soldCnt": 0}}}
    assert _extract_stats(detail) == {"browse_count": 134, "collect_count": 3, "want_count": 5}


def test_extract_stats_handles_string_numbers():
    detail = {"data": {"itemDO": {"browseCnt": "200", "wantCnt": "7"}}}
    s = _extract_stats(detail)
    assert s is not None
    assert s["browse_count"] == 200 and s["want_count"] == 7 and s["collect_count"] is None


def test_extract_stats_none_when_absent():
    assert _extract_stats({"data": {"itemDO": {}}}) is None
    assert _extract_stats(None) is None


def test_sold_item_is_dead_even_though_ret_says_success():
    """已售出的商品, ret 仍是 SUCCESS, 只有 itemStatus=-2 —— 以前会一直当在售。"""
    from xianyu_crawler.liveness import parse_detail, parse_detail_price, sold_reason

    item = {"itemId": "s1", "itemStatus": -2, "soldPrice": "1000"}
    detail = {"ret": ["SUCCESS::调用成功"], "data": {"itemDO": item}}

    assert sold_reason(item) == "已售出"
    assert sold_reason({"itemStatus": 0}) is None
    assert parse_detail_price(detail, "s1") == (None, True)
    reading = parse_detail(detail, "s1")
    assert reading.dead is True and reading.dead_reason == "已售出"