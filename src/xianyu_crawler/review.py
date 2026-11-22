"""二次审核: 调任意 OpenAI 兼容接口, 判定候选是否符合 watch.requirement。

端点: POST {review_base_url}/chat/completions (OpenAI Chat Completions 格式)。
具体接口地址/密钥由本地配置(data/secret.env 的 XIANYU_REVIEW_BASE_URL /
XIANYU_REVIEW_API_TOKEN)或控制台设置提供，不写进仓库。每件商品各发一次请求。
无要求/未启用/调用失败时**放行全部**(fail-open), 避免把推荐误黑洞掉。
"""
from __future__ import annotations

import json
import logging
import re

import httpx
from pydantic import BaseModel

from .config import Settings
from .models import Item

logger = logging.getLogger(__name__)

# 审核没跑通(接口报错/未配置)时的占位理由; 一键补审据此识别"还没真正审过"的条目。
REVIEW_NOT_RUN = "(审核未运行)"
# 关闭 AI 审核后的模式: 不调用模型, 候选留作人工审核。
REVIEW_MANUAL = "(人工审核)"

# 有些推理模型把思考内联在 content 里(<think>...</think>), 解析前先剥掉。
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think(text: str | None) -> str:
    return _THINK_RE.sub("", text or "").strip()


class ReviewVerdict(BaseModel):
    ok: bool
    reason: str = ""
    # 审核没真正跑(未启用/调用失败) → 调用方不要把 ok 当作裁决
    skipped: bool = False
    # 票务模板顺便抽取的属性; 通用模板/没抽到 → None
    attrs: dict | None = None


# 票务模板要模型额外回的结构化属性。只收这几个键, 其余一律丢掉。
_TICKET_ATTRS = (
    "\n\n本条件用「票务模板」：除 ok 与 reason 外，再从标题里抽取属性放进 attrs，"
    "抽不到就填 null，不要猜。字段："
    'seat（"内场" / "看台" / "未知"）、qty（整数张数，默认 1）、'
    "bundle（布尔，是否**多张票或多场演出打包**一起卖；只带特典、赠品、小卡不算捆绑）、"
    "deposit（布尔，标价是否**只是定金/尾款**而不是整张票价；"
    "「标价一张、需提确 50%」这种标价仍是整票价，算 false）、"
    'unit（"单张" / "合计" / "未知"，标价是单张价还是多张总价）。'
    '输出格式：[{"i":0,"ok":true,"reason":"一句话中文理由",'
    '"attrs":{"seat":"内场","qty":1,"bundle":false,"deposit":false,"unit":"单张"}}]'
)


def review_items(items: list[Item], requirement: str | None,
                 settings: Settings, kind: str = "general",
                 on_item=None) -> list[ReviewVerdict]:
    """按顺序单独审核每件商品，失败的条目保留供补审。"""
    if not settings.review_enabled:
        return [ReviewVerdict(ok=True, reason=REVIEW_MANUAL, skipped=True) for _ in items]
    if not requirement or not items:
        return [ReviewVerdict(ok=True) for _ in items]
    out: list[ReviewVerdict] = []
    for index, item in enumerate(items):
        if on_item is not None:
            on_item(index, len(items))
        try:
            content = _call_llm(_build_messages(item, requirement, settings, kind), settings)
            out.append(_parse_verdict(content))
        except Exception as e:  # noqa: BLE001 - 审核失败保留本条
            logger.warning("单条 AI 审核失败: %s", _friendly_error(e))
            out.append(ReviewVerdict(ok=True, reason=REVIEW_NOT_RUN, skipped=True))
    return out


def _build_messages(item: Item, requirement: str, settings: Settings,
                    kind: str = "general") -> list[dict]:
    meta = " | ".join(p for p in [
        f"¥{item.price:.0f}",
        f"成色:{item.condition}" if item.condition else "",
        f"地区:{item.location}" if item.location else "",
    ] if p)
    ask = ('\n' + _TICKET_ATTRS) if kind == "ticket" else ""
    user = (
        f"要求: {requirement}\n\n"
        f"判断下面这件商品是否符合要求:\n0. {item.title}  [{meta}]"
        '\n\n只输出包含一项的 JSON 数组，格式为 [{"i":0,"ok":true,"reason":"一句话中文理由"}]。'
        'ok 按实际判断填 true 或 false。'
        + ask
    )
    return [{"role": "system", "content": settings.review_system_prompt},
            {"role": "user", "content": user}]


def _call_llm(messages: list[dict], settings: Settings) -> str:
    url = settings.review_base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.review_api_token:
        headers["Authorization"] = f"Bearer {settings.review_api_token}"
    body = {
        "model": settings.review_model,
        "messages": messages,
        "stream": False,
        "max_tokens": settings.review_max_tokens,
        "temperature": settings.review_temperature,
    }

    resp = httpx.post(url, json=body, headers=headers, timeout=settings.review_timeout)
    resp.raise_for_status()
    choice = (resp.json().get("choices") or [{}])[0]
    if choice.get("finish_reason") == "length":
        return ""
    msg = choice.get("message") or {}
    content = _strip_think(msg.get("content"))
    if not content:
        # 推理模型常把正文留在 reasoning_content; content 为空时兜底取它(也剥思考标签)
        content = _strip_think(msg.get("reasoning_content"))
    return content


def _coerce_array(content: str) -> list:
    """取出裁决数组: 兼容结构化的 {"verdicts":[...]}、裸数组、或夹在文本里的 [...]。"""
    s = (content or "").strip()
    if not s:
        raise ValueError("模型没有返回正文(content 为空) — 多半是推理模型把 token 用在思考上, 或 max_tokens 太小")
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return _extract_json_array(s)        # 不是规整 JSON → 从文本里抠出 [...]
    if isinstance(obj, dict) and isinstance(obj.get("verdicts"), list):
        return obj["verdicts"]               # 结构化输出
    if isinstance(obj, list):
        return obj                           # 裸数组
    raise ValueError("JSON 里没有 verdicts 数组")


def _clean_attrs(raw: object) -> dict | None:
    """只保留认识的键和合法值; 没抽到就是 None, 不拿默认值编造。"""
    if not isinstance(raw, dict):
        return None
    out: dict = {}
    if raw.get("seat") in ("内场", "看台", "未知"):
        out["seat"] = raw["seat"]
    qty = raw.get("qty")
    if isinstance(qty, int) and not isinstance(qty, bool) and 1 <= qty <= 20:
        out["qty"] = qty
    for key in ("bundle", "deposit"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    if raw.get("unit") in ("单张", "合计", "未知"):
        out["unit"] = raw["unit"]
    return out or None


def _parse_verdict(content: str) -> ReviewVerdict:
    verdicts = _coerce_array(content)
    if len(verdicts) != 1 or not isinstance(verdicts[0], dict):
        raise ValueError("JSON 应只包含一条裁决")
    verdict = verdicts[0]
    if verdict.get("i") not in (0, "0") or not isinstance(verdict.get("ok"), bool):
        raise ValueError("JSON 裁决缺少有效的商品序号或判断")
    return ReviewVerdict(ok=verdict["ok"], reason=str(verdict.get("reason") or ""),
                         attrs=_clean_attrs(verdict.get("attrs")))


def _extract_json_array(text: str) -> list:
    s = (text or "").strip()
    if not s:
        raise ValueError("模型没有返回正文(content 为空) — 多半是推理模型把 token 用在思考上, 或 max_tokens 太小")
    start = s.find("[")
    end = s.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("响应里没有 JSON 数组")
    return json.loads(s[start:end + 1])


def _friendly_error(e: Exception) -> str:
    """把底层异常翻成控制台能看懂的一句话(尤其区分 401/404, 帮用户判断是 key 还是地址/模型)。"""
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        hint = {
            400: "请求被拒(模型名或参数可能不对)",
            401: "Key 无效或无权限(鉴权失败)",
            403: "无权限 / 被拒绝",
            404: "接口地址或模型名不对",
            429: "调用频率 / 额度超限",
            500: "服务端错误", 502: "网关错误", 503: "服务暂不可用",
        }.get(code, "")
        return f"HTTP {code} {hint}".strip()
    if isinstance(e, httpx.ConnectError):
        return f"连不上接口地址(base url 可能写错): {e}"
    if isinstance(e, httpx.TimeoutException):
        return "请求超时(可调大超时或检查网络)"
    return f"{type(e).__name__}: {e}"


def test_review(settings: Settings, requirement: str | None = None) -> dict:
    """用当前配置做一次真实审核, 回显成功或失败原因(控制台「测试 LLM」按钮用)。

    诚实判定: 只有「真的拿到可解析的裁决」才算 ok。连上了但正文为空 / 不是 JSON 都算失败
    并给出可操作的原因——否则会出现「测试通过但实际审核全跳过」的假阳性(正是推理模型的坑)。
    使用一件样品和实际「AI 审核要求」，与正常审核的请求大小一致。
    """
    sample = Item(item_id="0", title="MacBook Pro 16寸 M1 Pro 32G 1T 国行 95新",
                  url="", price=7000, condition="95新", location="北京")
    req = requirement or "只要 16 寸、M1 Pro、32G 内存、1T 硬盘、国行; 不要阉割版 / 16G / 512G"
    try:
        content = _call_llm(_build_messages(sample, req, settings), settings)
    except Exception as e:  # noqa: BLE001 - 失败原因回显给控制台, 不抛
        return {"ok": False, "error": _friendly_error(e)}
    if not content.strip():
        return {"ok": False, "model": settings.review_model,
                "error": "连上了, 但模型没返回正文(content 为空)。多半是推理模型把 token 额度用在思考上 —"
                         "调大「最大 tokens」(如 8000)、缩短「AI 审核要求」, 或换非推理模型。"}
    try:
        _parse_verdict(content)
    except Exception:  # noqa: BLE001
        return {"ok": False, "model": settings.review_model, "reply": content.strip()[:200],
                "error": "连上了, 但返回的不是可解析的 JSON 数组(见下方片段)。调大 max_tokens 或换模型。"}
    return {"ok": True, "model": settings.review_model, "reply": content.strip()[:200]}
