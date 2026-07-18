from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict


NEW_ORDER_DEFAULTS: tuple[tuple[str, Any], ...] = (
    ("keyword", "琛ｆ湇"),
    ("shop_type", "1688"),
    ("order_shop_count", 1),
    ("order_per_shop", 1),
    ("order_item_num", 1),
    ("offer_price", "10"),
    ("order_payment_mode", "balance_first"),
    ("payment_fallback", "bank"),
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
