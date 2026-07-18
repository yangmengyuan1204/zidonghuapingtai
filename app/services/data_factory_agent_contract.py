from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict


NEW_ORDER_DEFAULTS: tuple[tuple[str, Any], ...] = (
    ("keyword", "衣服"),
    ("shop_type", "1688"),
    ("order_shop_count", 1),
    ("order_per_shop", 1),
    ("order_item_num", 1),
    ("offer_price", "10"),
    ("order_payment_mode", "balance_first"),
    ("payment_fallback", "bank"),
)

PROBLEM_SCOPE_CLARIFICATION = "订单包含多个商品，请说明处理第几番或全部商品。"
PROBLEM_CHANGE_CLARIFICATION = "请说明问题产品需要修改数量、单价或国内运费，以及目标值。"
_DETERMINISTIC_PROBLEM_FIELDS = (
    "problem_goods_op",
    "problem_scope",
    "item_index",
    "problem_refund_quantity",
    "problem_refund_freight",
    "problem_preserve_price",
)


@dataclass(frozen=True)
class ContractDefaultsResult:
    target_node: str
    variables: Dict[str, Any]
    customer_ids: list[str]
    customer_source: str
    defaults_used: list[str]


def _numeric_customer_ids(values: Any) -> list[str]:
    raw_values = values if isinstance(values, list) else []
    result: list[str] = []
    for value in raw_values:
        customer_id = str(value).strip()
        if customer_id.isdigit() and customer_id not in result:
            result.append(customer_id)
    return result


def read_deterministic_problem_fields(resolved_fields: Any) -> Dict[str, Any]:
    source = resolved_fields if isinstance(resolved_fields, dict) else {}
    result: Dict[str, Any] = {}
    evidence: Dict[str, str] = {}
    for name in _DETERMINISTIC_PROBLEM_FIELDS:
        item = source.get(name)
        if not isinstance(item, dict) or "value" not in item:
            continue
        result[name] = copy.deepcopy(item["value"])
        evidence[name] = str(item.get("evidence") or "")
    if evidence:
        result["evidence"] = evidence
    return result


def problem_goods_clarification(
    *,
    problem_requested: bool,
    problem_fields: Dict[str, Any],
    item_count: int | None,
    existing_order: bool,
    has_explicit_change: bool,
) -> str:
    if not problem_requested:
        return ""
    scope = str(problem_fields.get("problem_scope") or "")
    if not scope and (existing_order or item_count is None or item_count > 1):
        return PROBLEM_SCOPE_CLARIFICATION
    if not has_explicit_change:
        return PROBLEM_CHANGE_CLARIFICATION
    return ""


def compile_contract_defaults(
    *,
    mode: str,
    target_node: str,
    variables: Dict[str, Any],
    explicit_customer_ids: list[str],
    context: Dict[str, Any] | None = None,
) -> ContractDefaultsResult:
    compiled_target = str(target_node or "").strip()
    compiled_variables = copy.deepcopy(dict(variables or {}))
    compile_context = copy.deepcopy(dict(context or {}))
    defaults_used: list[str] = []

    explicit_ids = _numeric_customer_ids(explicit_customer_ids)
    topbar_ids = _numeric_customer_ids(compile_context.get("topbar_customer_ids"))
    bound_ids = _numeric_customer_ids(compile_context.get("bound_customer_ids"))
    if explicit_ids:
        customer_ids = explicit_ids
        customer_source = "natural_language"
    elif topbar_ids:
        customer_ids = topbar_ids
        customer_source = "topbar"
        defaults_used.append("customer_ids")
    elif bound_ids:
        customer_ids = bound_ids
        customer_source = "bound_account"
        defaults_used.append("customer_ids")
    else:
        customer_ids = []
        customer_source = ""

    if mode == "new":
        if not compiled_target:
            compiled_target = "order_offered"
            defaults_used.append("target_node")
        for key, value in NEW_ORDER_DEFAULTS:
            if key not in compiled_variables or compiled_variables[key] in (None, ""):
                compiled_variables[key] = copy.deepcopy(value)
                defaults_used.append(key)

    return ContractDefaultsResult(
        target_node=compiled_target,
        variables=copy.deepcopy(compiled_variables),
        customer_ids=list(customer_ids),
        customer_source=customer_source,
        defaults_used=list(dict.fromkeys(defaults_used)),
    )
