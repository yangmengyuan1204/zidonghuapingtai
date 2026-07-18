from __future__ import annotations

import copy
import re
from typing import Any, Dict


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace("，", ",").replace("：", ":")


_COUNT_TOKEN = r"(?:\d+|[一二两三四五六七八九十百]+)"
_CHINESE_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _count(value: str) -> int:
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    total = 0
    current = 0
    for char in text:
        if char in _CHINESE_DIGITS:
            current = _CHINESE_DIGITS[char]
        elif char == "十":
            total += (current or 1) * 10
            current = 0
        elif char == "百":
            total += (current or 1) * 100
            current = 0
    return total + current


def reduce_intent_fields(state: Dict[str, Any], message: str) -> Dict[str, Any]:
    """Merge fields explicitly stated in the latest user message."""
    result = copy.deepcopy(state) if isinstance(state, dict) else {}
    fields = result.setdefault("resolved_fields", {})
    revisions = result.setdefault("revisions", [])
    message_index = int(result.get("turn_count") or 0)
    text = _compact(message)

    def resolve(name: str, value: Any, evidence: str) -> None:
        item = {
            "value": value,
            "evidence": evidence,
            "message_index": message_index,
            "source": "deterministic",
        }
        previous = copy.deepcopy(fields.get(name))
        fields[name] = item
        if previous != item:
            revisions.append(
                {
                    "field": name,
                    "before": previous,
                    "after": copy.deepcopy(item),
                    "message_index": message_index,
                }
            )

    target_patterns = (
        (r"(?:到|进入|停在)?待拍下", "pending_purchase"),
        (r"(?:到|进入|停在)?(?:待付款|待支付|付款前)", "order_offered"),
        (r"(?:已付款|支付完成|付完钱)", "order_paid"),
        (r"(?:采购|交易号|财务).{0,8}(?:待付款|待支付)", "purchase_wait_pay"),
    )
    for pattern, value in target_patterns:
        match = re.search(pattern, text)
        if match:
            resolve("target_node", value, match.group(0))

    # --- 订单号提取 ---
    order_sn_long = re.search(r"(\d{16}-\d+)", text)  # 2026071715475684-300001 格式
    order_sn_general = re.search(
        r"(?:订单|订单号|order[. _-]*sn|SN)[. _-]*[：:]*\s*([A-Za-z0-9_-]{6,})",
        text, re.IGNORECASE,
    )
    order_sn_match = order_sn_long or order_sn_general
    if order_sn_match:
        resolve("order_sn", order_sn_match.group(1), order_sn_match.group(0))

    # --- 问题商品番号提取（仅显式选择，不把“2番商品”误判成第2番）---
    item_index_match = re.search(
        r"第\s*(\d+)\s*番|(\d+)\s*番(?=.{0,8}(?:提出|处理|提|退)(?:问题产品|问题商品))",
        text,
    )
    if item_index_match:
        item_index = item_index_match.group(1) or item_index_match.group(2)
        resolve("item_index", int(item_index), item_index_match.group(0))

    # --- 问题产品操作识别 ---
    problem_goods_patterns = (
        (r"提出.*?问题产品", "提出问题产品"),
        (r"处理.*?问题产品", "处理问题产品"),
        (r"退.*?问题产品", "退问题产品"),
    )
    for pattern, label in problem_goods_patterns:
        pg_match = re.search(pattern, text, re.IGNORECASE)
        if pg_match:
            resolve("problem_goods_op", label, pg_match.group(0))
            break

    if item_index_match:
        resolve("problem_scope", "item", item_index_match.group(0))
    else:
        all_scope = re.search(
            r"(?:全部|所有)(?:商品|问题产品|问题商品)|(?:每|各)番|分别(?:处理|提出|退)|"
            r"(?:两|2)番(?:商品)?都(?:处理|提出|提|退)|(?:全部|所有|都)处理",
            text,
        )
        if all_scope:
            resolve("problem_scope", "all", all_scope.group(0))

    per_shop_phrase = re.search(
        rf"(?:每(?:个)?店(?:铺)?|店铺各|各店(?:铺)?)(?:有|包含|要求)?({_COUNT_TOKEN})(?:个|种|款|件)?(?:商品|货品|sku)",
        text,
        re.IGNORECASE,
    )
    item_count = None
    for candidate in re.finditer(
        rf"(?:改成|改为|调整为|变成)?({_COUNT_TOKEN})(?:个|种|款|番)(?:商品|货品|sku)",
        text,
        re.IGNORECASE,
    ):
        if candidate.start() > 0 and text[candidate.start() - 1] == "第":
            continue
        if per_shop_phrase and candidate.start() >= per_shop_phrase.start() and candidate.end() <= per_shop_phrase.end():
            continue
        item_count = candidate
        break
    if item_count:
        resolve("item_count", _count(item_count.group(1)), item_count.group(0))

    per_item_quantity = re.search(
        rf"(?:每(?:个|种|款)?(?:商品|货品|sku)?|每(?:一)?番(?:商品|货品)?)(?:的)?(?:购买)?(?:数量|买)(?:都)?(?:改成|改为|调整为|变成|是|为|=|:)?({_COUNT_TOKEN})(?:件|个|份)?",
        text,
        re.IGNORECASE,
    )
    if per_item_quantity:
        resolve("quantity_per_item", _count(per_item_quantity.group(1)), per_item_quantity.group(0))

    # --- 问题产品退款：单价改成0 ---
    refund_unit_price = re.search(
        r"(?:单价|报价|价格|offer.?price)\s*(?:改成|改为|调整为|变成|是|为|=|:)\s*0",
        text, re.IGNORECASE,
    )

    total_price = re.search(
        r"(?:商品总价|总价|合计|一共|总共)(?:改成|改为|调整为|变成|是|为|=|:|共计)?(\d+(?:\.\d+)?)(?=元|块|,|。|；|;|$)",
        text,
    )
    unit_price = re.search(
        r"(?:商品单价|单价|每(?:个|件|种|款)(?:商品)?(?:的)?(?:报价|单价)?)(?:改成|改为|调整为|变成|是|为|=|:)?(\d+(?:\.\d+)?)",
        text,
    )
    price_list = re.search(r"(?:分别|依次)(?:报价|单价)?([^。；;]*)", text)
    price_values = re.findall(r"\d+(?:\.\d+)?", price_list.group(1)) if price_list else []
    ambiguous_price = re.search(
        r"(?:价格|金额)(?:改成|改为|调整为|变成|是|为|=|:)?(\d+(?:\.\d+)?)",
        text,
    )
    if refund_unit_price:
        resolve(
            "pricing",
            {"mode": "uniform_unit", "amount": "0", "amounts": [], "refund_context": True},
            refund_unit_price.group(0),
        )
    elif total_price:
        resolve(
            "pricing",
            {"mode": "goods_total", "amount": total_price.group(1), "amounts": []},
            total_price.group(0),
        )
    elif price_values:
        resolve(
            "pricing",
            {"mode": "per_item_unit", "amount": "", "amounts": price_values},
            price_list.group(0),
        )
    elif unit_price:
        resolve(
            "pricing",
            {"mode": "uniform_unit", "amount": unit_price.group(1), "amounts": []},
            unit_price.group(0),
        )
    elif ambiguous_price:
        resolve(
            "pricing",
            {"mode": "ambiguous", "amount": ambiguous_price.group(1), "amounts": []},
            ambiguous_price.group(0),
        )
    else:
        previous_pricing = fields.get("pricing") if isinstance(fields.get("pricing"), dict) else {}
        previous_value = previous_pricing.get("value") if isinstance(previous_pricing.get("value"), dict) else {}
        if previous_value.get("mode") == "ambiguous" and re.search(r"(?:是|按|表示)?(?:商品)?总价", text):
            resolve(
                "pricing",
                {**previous_value, "mode": "goods_total"},
                text[:200],
            )
        elif previous_value.get("mode") == "ambiguous" and re.search(r"(?:是|按|表示)?(?:每件|每个|商品)?单价", text):
            resolve(
                "pricing",
                {**previous_value, "mode": "uniform_unit"},
                text[:200],
            )

    quantity_all = re.search(
        r"(?:全部|所有|全)(?:商品)?(?:金额|数量).{0,12}(?:退|退款)|"
        r"(?:问题产品|问题商品|商品)?数量.{0,8}(?:全部|全|都)(?:给)?退|"
        r"(?:问题产品|问题商品|商品)?数量(?:(?:改|变)(?:成|为)?|成|为|=|:)?0",
        text,
    )
    if quantity_all:
        resolve("problem_refund_quantity", "all", quantity_all.group(0))

    freight_all = re.search(
        r"(?:国内运费|运费).{0,10}(?:全部|全|都)?(?:给)?退|"
        r"(?:全部|全|都)退.{0,8}(?:国内运费|运费)|"
        r"(?:国内运费|运费)(?:(?:改|变)(?:成|为)?|成|为|=|:)?0",
        text,
    )
    if freight_all:
        resolve("problem_refund_freight", "all", freight_all.group(0))

    full_refund = re.search(r"(?<!数量)(?<!运费)(?:全部退|全退)(?:了)?", text)
    if full_refund:
        resolve("problem_refund_quantity", "all", full_refund.group(0))
        resolve("problem_refund_freight", "all", full_refund.group(0))
        resolve("problem_preserve_price", True, full_refund.group(0))
    explicit_unit_price = refund_unit_price or unit_price
    if (
        explicit_unit_price
        and "problem_goods_op" in fields
        and (not full_refund or explicit_unit_price.start() > full_refund.start())
    ):
        resolve("problem_preserve_price", False, explicit_unit_price.group(0))

    # --- 支付方式提取 ---
    payment_mode_match = re.search(
        r"(?:支付方式|付款方式)(?:改成|改为|是|为|=|:)?\s*(银行|余额|合并)",
        text, re.IGNORECASE,
    )
    if not payment_mode_match:
        payment_mode_match = re.search(
            r"(银行)(?:汇款|支付|入金|转账)",
            text, re.IGNORECASE,
        )
    if not payment_mode_match:
        payment_mode_match = re.search(
            r"(?:用|使用)?(余额)(?:支付|付款)",
            text, re.IGNORECASE,
        )
    if payment_mode_match:
        mode_map = {"银行": "bank", "余额": "balance_first", "合并": "merge"}
        resolved = mode_map.get(payment_mode_match.group(1), payment_mode_match.group(1))
        resolve("order_payment_mode", resolved, payment_mode_match.group(0))

    # --- 客户ID提取 ---
    customer_match = re.search(
        r"(?:客户|customer)[. _-]*[：:]*\s*(\d+)",
        text, re.IGNORECASE,
    )
    if customer_match:
        existing = fields.get("customer_ids")
        existing_list = existing.get("value", []) if isinstance(existing, dict) else []
        new_id = customer_match.group(1)
        if new_id not in existing_list:
            resolve("customer_ids", existing_list + [new_id], customer_match.group(0))

    unchanged = re.search(r"(?:其他|其它|剩下|其余).{0,4}(?:不变|别改|不要改)", text)
    if unchanged:
        resolve("preserve_unspecified", True, unchanged.group(0))

    pending_fields = result.get("pending_fields")
    latest_scope = fields.get("problem_scope")
    if (
        isinstance(pending_fields, dict)
        and isinstance(latest_scope, dict)
        and latest_scope.get("message_index") == message_index
    ):
        pending_fields.pop("problem_scope", None)

    result["turn_count"] = message_index + 1
    return result


# ---------------------------------------------------------------------------
# Pattern combination library - systematic natural language coverage
# Each pattern table drives deterministic matching; add new synonyms here
# without changing logic.
# ---------------------------------------------------------------------------

PRICE_KEYWORDS = {
    'total': [
        '商品总金额', '商品总额', '商品总价', '商品金额', '总金额',
        '总价', '合计', '一共', '总共', '商品一共', '商品合计',
    ],
    'per_item': [
        '商品单价', '报价单价', '单价', '每件', '每个', '每种', '每款',
        '单番单价', '单番价格', '单件价格', '单番的单价', '每番单价',
        '每个商品', '每个的报价', '每件商品的单价',
    ],
    'connector': [
        '是', '为', '=', ':', '等于', '共计', '共', '总共', '为',
    ],
    'money_suffix': [
        '元', '块', '块钱',
    ],
}

QUANTITY_PHRASES = [
    '单番数量', '每个数量', '每种数量', '每番数量', '单品数量',
    '每件数量', '各买', '每种买', '每番买', '每件买',
]

TOTAL_PRICE_PATTERNS = [
    '{keyword}{connector}{amount}{suffix}',
    '{amount}{suffix}的{keyword}',
    '{amount}元{keyword}',
    '{keyword}{amount}{suffix}',
]

UNIT_PRICE_PATTERNS = [
    '{keyword}{connector}{amount}{suffix}',
    '{amount}{suffix}{keyword}',
    '{amount}元{keyword}',
    '{keyword}{amount}{suffix}',
]


def build_price_regex_group(keywords: list[str]) -> str:
    sorted_kw = sorted(keywords, key=len, reverse=True)
    return '(?:' + '|'.join(sorted_kw) + ')'


def build_connector_group() -> str:
    return '(?:' + '|'.join(PRICE_KEYWORDS['connector']) + ')'


def coverage_report() -> dict:
    return {
        'total_price_keywords': len(PRICE_KEYWORDS['total']),
        'per_item_keywords': len(PRICE_KEYWORDS['per_item']),
        'connectors': len(PRICE_KEYWORDS['connector']),
        'quantity_phrases': len(QUANTITY_PHRASES),
        'total_patterns': len(TOTAL_PRICE_PATTERNS),
        'unit_patterns': len(UNIT_PRICE_PATTERNS),
        'combinatorial_total': len(PRICE_KEYWORDS['total']) * len(PRICE_KEYWORDS['connector']),
    }
