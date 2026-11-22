"""search 显式解析回归 (合成 sample, 结构同真实 mtop 响应)。"""
import json
from pathlib import Path

import pytest

from xianyu_crawler.search import parse_search_json

FIXTURE = Path(__file__).parent / "fixtures" / "search.sample.json"


@pytest.mark.skipif(not FIXTURE.exists(), reason="缺 search.sample.json")
def test_parse_search_sample():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    items = parse_search_json(raw)
    assert len(items) == 1
    it = items[0]
    assert it.item_id == "111"
    assert it.title.startswith("测试")
    assert it.price == 1234.0            # 用 soldPrice, 非样式串
    assert it.location == "上海"
    assert it.free_shipping is True
    assert it.condition == "99新"
    assert it.url == "https://www.goofish.com/item?id=111"


def test_original_price_from_cumulative_drop_tag():
    """列表标签「累计降价50%」+ 现价 → 反推卖家最初挂牌价。"""
    raw = {"data": {"resultList": [{"data": {"item": {"main": {
        "exContent": {
            "itemId": "999", "title": "对邦 门票", "area": "上海",
            "detailParams": {"soldPrice": "1500"},
            "fishTags": {"r3": {"tagList": [{"data": {"content": "累计降价50%"}}]}},
        },
        "clickParam": {"args": {"publishTime": 1791594988000}},
    }}}}]}}
    [item] = parse_search_json(raw)
    assert item.price == 1500.0
    assert item.original_price == 3000.0
    assert item.publish_time is not None
