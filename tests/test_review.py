import httpx
import pytest

from xianyu_crawler import review
from xianyu_crawler.review import ReviewVerdict, _parse_verdict, _extract_json_array, _build_messages
from xianyu_crawler.models import Item
from xianyu_crawler.config import Settings


def test_extract_json_array_with_fence():
    txt = '好的:\n```json\n[{"i":0,"ok":true,"reason":"符合"}]\n```'
    arr = _extract_json_array(txt)
    assert arr[0]["ok"] is True


def test_parse_verdict_rejects_missing_or_invalid_judgment():
    verdict = _parse_verdict('[{"i":0,"ok":false,"reason":"错场"}]')
    assert verdict == ReviewVerdict(ok=False, reason="错场")
    with pytest.raises(ValueError):
        _parse_verdict("[]")
    with pytest.raises(ValueError):
        _parse_verdict('[{"i":0,"ok":"false"}]')


def test_review_items_no_requirement_passes_all():
    items = [Item(item_id="a", title="x", url="u", price=1)]
    assert review.review_items(items, None, Settings()) == [ReviewVerdict(ok=True)]


def test_review_items_failopen_on_error(monkeypatch):
    items = [Item(item_id="a", title="x", url="u", price=1)]

    def boom(*a, **k):
        raise RuntimeError("net down")

    monkeypatch.setattr(review, "_call_llm", boom)
    vs = review.review_items(items, "必须M5", Settings())
    assert vs[0].ok is True and "未运行" in vs[0].reason and vs[0].skipped is True


def test_review_items_sends_one_request_per_item_and_isolates_failure(monkeypatch):
    titles = ["第一件正例", "第二件截断", "第三件反例"]
    items = [Item(item_id=str(i), title=title, url="u", price=1)
             for i, title in enumerate(titles)]
    requests = []

    def post(url, json, headers, timeout):
        requests.append(json)
        title = titles[len(requests) - 1]
        prompt = json["messages"][1]["content"]
        assert [candidate for candidate in titles if candidate in prompt] == [title]
        if title == titles[1]:
            choice = {"finish_reason": "length", "message": {
                "content": "", "reasoning_content": '[{"i":0,"ok":true,"reason":"推理中的例子"}]'
            }}
        else:
            decision = "true" if title == titles[0] else "false"
            choice = {"finish_reason": "stop", "message": {
                "content": f'[{{"i":0,"ok":{decision},"reason":"审核理由"}}]'
            }}
        return httpx.Response(200, request=httpx.Request("POST", url), json={"choices": [choice]})

    monkeypatch.setattr(review.httpx, "post", post)
    verdicts = review.review_items(items, "审核要求", Settings())
    assert len(requests) == len(items)
    assert verdicts == [
        ReviewVerdict(ok=True, reason="审核理由"),
        ReviewVerdict(ok=True, reason=review.REVIEW_NOT_RUN, skipped=True),
        ReviewVerdict(ok=False, reason="审核理由"),
    ]


def test_build_messages_shape():
    item = Item(item_id="a", title="标题X", url="u", price=1, condition="99新", location="上海")
    msgs = _build_messages(item, "要 M5", Settings())
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert "要 M5" in msgs[1]["content"] and "标题X" in msgs[1]["content"]
    assert msgs[0]["content"] == Settings().review_system_prompt   # 系统提示词来自配置


def test_review_items_disabled_leaves_items_for_manual_review():
    items = [Item(item_id="a", title="x", url="u", price=1)]
    st = Settings(review_enabled=False)
    [verdict] = review.review_items(items, "必须M5", st)
    assert verdict.skipped is True and verdict.reason == review.REVIEW_MANUAL


def test_review_uses_configured_params(monkeypatch):
    captured = {}
    items = [Item(item_id="a", title="M5", url="u", price=1)]
    st = Settings(review_temperature=0.7, review_max_tokens=512,
                  review_system_prompt="自定义提示词")

    def fake_post(url, json, headers, timeout):
        captured.update(json)

        class R:
            status_code = 200
            def raise_for_status(self): ...
            def json(self): return {"choices": [{"message": {"content": '{"verdicts":[{"i":0,"ok":true}]}'}}]}
        return R()

    monkeypatch.setattr(review.httpx, "post", fake_post)
    review.review_items(items, "必须M5", st)
    assert captured["temperature"] == 0.7 and captured["max_tokens"] == 512
    assert captured["messages"][0]["content"] == "自定义提示词"
    assert "response_format" not in captured


def test_coerce_array_handles_shapes():
    assert review._coerce_array('{"verdicts":[{"i":0,"ok":true}]}')[0]["ok"] is True  # 结构化
    assert review._coerce_array('[{"i":0,"ok":false}]')[0]["ok"] is False             # 裸数组
    assert review._coerce_array('好的:\n```json\n[{"i":0,"ok":true}]\n```')[0]["i"] == 0  # 夹文本


def test_rejected_http_request_is_not_retried(monkeypatch):
    requests = []

    def post(url, json, headers, timeout):
        requests.append(json)
        return httpx.Response(400, request=httpx.Request("POST", url))

    monkeypatch.setattr(review.httpx, "post", post)
    verdicts = review.review_items([Item(item_id="a", title="x", url="u", price=1)], "req", Settings())
    assert verdicts[0].reason == review.REVIEW_NOT_RUN
    assert len(requests) == 1


# --- test_review(控制台「测试 LLM」按钮) ---
def test_test_review_ok(monkeypatch):
    monkeypatch.setattr(review, "_call_llm", lambda msgs, st: '[{"i":0,"ok":true,"reason":"符合"}]')
    r = review.test_review(Settings(review_model="m-x"))
    assert r["ok"] is True and r["model"] == "m-x"


def test_test_review_unparsable_reply_is_not_ok(monkeypatch):
    # 连上了但返回不是 JSON 数组 → 诚实判 ok=False(否则会「测试通过但实际全跳过」)
    monkeypatch.setattr(review, "_call_llm", lambda msgs, st: "我觉得这个还行")
    r = review.test_review(Settings())
    assert r["ok"] is False and "JSON" in r["error"]


def test_test_review_empty_content_hints_reasoning_model(monkeypatch):
    # 推理模型典型症状: content 为空 → 给出可操作提示
    monkeypatch.setattr(review, "_call_llm", lambda msgs, st: "   ")
    r = review.test_review(Settings())
    assert r["ok"] is False and "content 为空" in r["error"]


def test_test_review_uses_passed_requirement(monkeypatch):
    seen = {}
    def cap(msgs, st):
        seen["user"] = msgs[1]["content"]
        return '[{"i":0,"ok":true}]'
    monkeypatch.setattr(review, "_call_llm", cap)
    review.test_review(Settings(), requirement="必须_独特要求_XYZ")
    assert "必须_独特要求_XYZ" in seen["user"]


def test_test_review_http_401_friendly(monkeypatch):
    req = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    resp = httpx.Response(401, request=req)

    def boom(msgs, st):
        raise httpx.HTTPStatusError("Unauthorized", request=req, response=resp)

    monkeypatch.setattr(review, "_call_llm", boom)
    r = review.test_review(Settings())
    assert r["ok"] is False and "401" in r["error"]


def test_test_review_connect_error_friendly(monkeypatch):
    def boom(msgs, st):
        raise httpx.ConnectError("name resolution failed")

    monkeypatch.setattr(review, "_call_llm", boom)
    r = review.test_review(Settings())
    assert r["ok"] is False and "连不上" in r["error"]
