from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from app.data_scripts.capabilities import (
    ContractFieldSpec,
    DataScriptCapability,
    capability_catalog,
    effective_contract_fields,
)


_INACTIVE_FIELD = object()


class ContractValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("合同字段校验失败")
        self.errors = dict(errors)


LEGACY_CAPABILITY_BY_SCOPE = {
    ("order", "create"): "full_flow",
    ("order", "resume_order"): "resume_order_flow",
    ("porder", "resume_porder"): "resume_porder_flow",
    ("problem_goods", "problem_goods"): "problem_goods",
}


def resolve_goal_capability(
    goal: dict[str, Any],
    *,
    module_key: Any = "",
    intent_key: Any = "",
) -> str:
    catalog = capability_catalog()
    safe_intent = str(intent_key or "").strip()
    explicit = str(goal.get("capability_key") or safe_intent).strip()
    if explicit in catalog:
        return explicit
    operations = [
        item for item in goal.get("operations") or [] if isinstance(item, dict)
    ]
    types = {str(item.get("type") or "") for item in operations}
    safe_module = str(module_key or "").strip()
    mode = str(goal.get("mode") or "").strip()
    legacy_key = LEGACY_CAPABILITY_BY_SCOPE.get((safe_module, safe_intent))
    if types == {"problem_goods"}:
        return "problem_goods"
    if "advance_porder" in types or mode == "resume_porder":
        return "resume_porder_flow"
    if mode == "resume_order":
        return "resume_order_flow"
    if "advance_order" in types or mode == "new":
        return "full_flow"
    return legacy_key or ""


def problem_goods_operation(goal: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in goal.get("operations") or []
            if isinstance(item, dict) and item.get("type") == "problem_goods"
        ),
        None,
    )


def project_contract_goal(
    goal: dict[str, Any],
    capability: DataScriptCapability,
    plan_version: int | None = None,
) -> dict[str, Any]:
    projected = copy.deepcopy(goal)
    operation = problem_goods_operation(projected)
    if operation is not None:
        for field in effective_contract_fields(capability):
            if (
                field.group == "problem_goods"
                and not field.readonly
                and operation.get(field.name) is not None
            ):
                _set_path(projected, field.path, operation[field.name])
    if plan_version is not None:
        projected["plan_version"] = int(plan_version)
    return projected


def _get_path(goal: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = goal
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _set_path(goal: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = goal
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[parts[-1]] = copy.deepcopy(value)


def backwrite_problem_goods_operation(
    goal: dict[str, Any],
    capability: DataScriptCapability,
    updated_names: set[str],
) -> None:
    operation = problem_goods_operation(goal)
    if operation is None:
        return
    fields = {
        field.name: field
        for field in effective_contract_fields(capability)
        if field.group == "problem_goods" and not field.readonly
    }
    for name in updated_names.intersection(fields):
        value = _get_path(goal, fields[name].path, _INACTIVE_FIELD)
        if value is not _INACTIVE_FIELD:
            operation[name] = copy.deepcopy(value)


def _delete_path(goal: dict[str, Any], path: str) -> None:
    current: Any = goal
    parts = path.split(".")
    for part in parts[:-1]:
        if not isinstance(current, dict):
            return
        current = current.get(part)
    if isinstance(current, dict):
        current.pop(parts[-1], None)


def _decimal_text(value: Any) -> str:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("必须是数字") from exc
    if not number.is_finite():
        raise ValueError("必须是数字")
    if number < 0:
        raise ValueError("不能小于0")
    return format(number.normalize(), "f")


def _int_value(value: Any) -> int:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("必须是整数") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError("必须是整数")
    return int(number)


def _string_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    raw = value if isinstance(value, (list, tuple)) else [value]
    result: list[str] = []
    for item in raw:
        result.extend(
            part.strip()
            for part in str(item).replace("，", ",").split(",")
            if part.strip()
        )
    return result


def _bool_value(value: Any) -> bool:
    if value in (None, ""):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "是"}:
        return True
    if normalized in {"0", "false", "no", "off", "否"}:
        return False
    raise ValueError("必须是布尔值")


def _normalize_value(field: ContractFieldSpec, value: Any) -> Any:
    value_type = field.value_type.strip().lower()
    if value_type == "int":
        return _int_value(value)
    if value_type == "decimal":
        return _decimal_text(value)
    if value_type == "list[str]":
        return _string_list(value)
    if value_type == "bool":
        return _bool_value(value)
    if value is None:
        return "" if value_type in {"str", "string", "node"} else None
    return str(value).strip() if value_type in {"str", "string", "node"} else copy.deepcopy(value)


def normalize_contract_field_value(
    capability: DataScriptCapability,
    field_name: str,
    value: Any,
) -> Any:
    field = next(
        (
            item
            for item in effective_contract_fields(capability)
            if item.name == str(field_name or "") and item.execution_field
        ),
        None,
    )
    if field is None:
        raise ValueError("字段不属于当前脚本执行合同")
    normalized = _normalize_value(field, value)
    if not _choice_is_valid(field, normalized):
        raise ValueError("字段值不在允许选项中")
    return normalized


def _choice_is_valid(field: ContractFieldSpec, value: Any) -> bool:
    if not field.choices:
        return True
    allowed = {choice_value for choice_value, _ in field.choices}
    return value in allowed or str(value) in allowed


def _effective_field_value(
    goal: dict[str, Any],
    field: ContractFieldSpec,
    fields: dict[str, ContractFieldSpec],
) -> Any:
    offer_price = fields.get("offer_price")
    unit_prices = fields.get("offer_unit_prices")
    if field.name not in {"offer_price", "offer_unit_prices"} or not (
        offer_price and unit_prices
    ):
        return _get_path(goal, field.path, field.default)

    unit_value = _get_path(goal, unit_prices.path)
    if _string_list(unit_value):
        return unit_value if field.name == "offer_unit_prices" else _INACTIVE_FIELD
    if field.name == "offer_unit_prices":
        return _INACTIVE_FIELD
    price_value = _get_path(goal, offer_price.path)
    return price_value if price_value not in (None, "") else offer_price.default


def build_contract_editor_schema(
    capability: DataScriptCapability, goal: dict[str, Any]
) -> list[dict[str, Any]]:
    inferred = set(goal.get("inferred_fields") or [])
    sources = goal.get("field_sources") if isinstance(goal.get("field_sources"), dict) else {}
    contract_fields = effective_contract_fields(capability)
    fields = {field.name: field for field in contract_fields}
    schema: list[dict[str, Any]] = []
    for field in contract_fields:
        value = _effective_field_value(goal, field, fields)
        schema.append({
            "name": field.name,
            "label": field.label,
            "group": field.group,
            "value_type": field.value_type,
            "editor": field.editor,
            "choices": [
                {"value": value, "label": label} for value, label in field.choices
            ],
            "required": field.required,
            "readonly": field.readonly,
            "learnable": field.learnable,
            "value": None if value is _INACTIVE_FIELD else copy.deepcopy(value),
            "source": str(sources.get(field.name) or ""),
            "inferred": field.name in inferred,
        })
    return schema


def normalize_execution_contract(
    goal: dict[str, Any], capability: DataScriptCapability
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    errors: dict[str, str] = {}
    contract_fields = effective_contract_fields(capability)
    fields = {field.name: field for field in contract_fields}
    for field in contract_fields:
        if not field.execution_field:
            continue
        value = _effective_field_value(goal, field, fields)
        if value is _INACTIVE_FIELD:
            normalized[field.name] = None
            continue
        if field.required and value in (None, "", []):
            normalized[field.name] = None
            continue
        try:
            normalized[field.name] = _normalize_value(field, value)
        except ValueError as exc:
            errors[field.name] = str(exc)
    if errors:
        raise ContractValidationError(errors)
    return normalized


def required_contract_errors(
    goal: dict[str, Any], capability: DataScriptCapability
) -> dict[str, str]:
    normalized = normalize_execution_contract(goal, capability)
    return {
        field.name: f"{field.label}为必填项"
        for field in effective_contract_fields(capability)
        if field.required
        and field.execution_field
        and normalized.get(field.name) in (None, "", [])
    }


def diff_execution_contract(
    initial: dict[str, Any],
    final: dict[str, Any],
    capability: DataScriptCapability,
    source: str,
) -> list[dict[str, Any]]:
    before = normalize_execution_contract(initial, capability)
    after = normalize_execution_contract(final, capability)
    return [
        {
            "field": name,
            "before": before.get(name),
            "after": after.get(name),
            "source": source,
        }
        for name in sorted(set(before) | set(after))
        if before.get(name) != after.get(name)
    ]


def _price_values(value: Any) -> list[str]:
    return [_decimal_text(item) for item in _string_list(value)]


def _positive_count(variables: dict[str, Any], name: str, default: int = 1) -> int:
    value = _int_value(variables.get(name, default))
    if value <= 0:
        raise ValueError("必须是正整数")
    return value


def _goods_total_prices(total: Any, item_count: int, quantity: int) -> list[str]:
    decimal_total = Decimal(_decimal_text(total))
    cents = decimal_total * Decimal("100")
    if cents != cents.to_integral_value():
        raise ValueError("商品总价最多支持两位小数")
    total_cents = int(cents)
    if total_cents % quantity:
        raise ValueError("商品总价无法按购买数量精确分摊到分")
    line_cents, remainder = divmod(total_cents // quantity, item_count)
    return [
        format(
            (Decimal(line_cents + (1 if index < remainder else 0)) / Decimal("100")).normalize(),
            "f",
        )
        for index in range(item_count)
    ]


def _recompute_price_totals(
    goal: dict[str, Any],
    updated_names: set[str],
    fields: dict[str, ContractFieldSpec],
) -> None:
    price_fields = {"offer_price", "offer_unit_prices"}
    shape_fields = {"order_shop_count", "order_per_shop", "order_item_num"}
    if not updated_names.intersection(price_fields | shape_fields):
        return
    variables = goal.get("variables")
    if not isinstance(variables, dict):
        return

    item_count = _positive_count(variables, "order_shop_count") * _positive_count(
        variables, "order_per_shop"
    )
    quantity = _positive_count(variables, "order_item_num")
    intent = goal.get("intent") if isinstance(goal.get("intent"), dict) else {}
    intent = copy.deepcopy(intent)
    pricing = intent.get("pricing") if isinstance(intent.get("pricing"), dict) else {}
    pricing = copy.deepcopy(pricing)

    price_updated = updated_names.intersection(price_fields)
    goods_total_recomputed = (
        not price_updated
        and pricing.get("mode") == "goods_total"
        and pricing.get("requested_goods_total") not in (None, "")
    )
    if "offer_unit_prices" in price_updated:
        prices = _price_values(variables.get("offer_unit_prices"))
    elif "offer_price" in price_updated:
        prices = _price_values(variables.get("offer_price"))
    elif goods_total_recomputed:
        prices = _goods_total_prices(
            pricing.get("requested_goods_total"), item_count, quantity
        )
    else:
        prices = _price_values(
            variables.get("offer_unit_prices") or variables.get("offer_price")
        )

    if not prices:
        return
    if len(prices) == 1:
        prices *= item_count
    if len(prices) != item_count:
        raise ValueError(
            f"当前共{item_count}个商品，请填写1个统一单价或{item_count}个逐商品单价"
        )
    if goods_total_recomputed:
        if len(set(prices)) == 1 and "offer_price" in fields:
            _set_path(goal, fields["offer_price"].path, prices[0])
            if "offer_unit_prices" in fields:
                _delete_path(goal, fields["offer_unit_prices"].path)
        elif "offer_unit_prices" in fields:
            _set_path(goal, fields["offer_unit_prices"].path, prices)
            if "offer_price" in fields:
                _delete_path(goal, fields["offer_price"].path)
        else:
            error_field = "offer_price" if "offer_price" in fields else "pricing"
            raise ContractValidationError(
                {error_field: "当前合同字段无法准确表达逐商品分摊价格"}
            )
    total = sum(Decimal(value) * quantity for value in prices)
    pricing.update(
        {
            "effective_unit_prices": prices,
            "effective_goods_total": format(total.normalize(), "f"),
        }
    )
    if price_updated:
        pricing.update(
            {
                "mode": "user_unit_override",
                "mode_label": "用户指定执行单价",
                "requested_goods_total": "",
                "includes_fees": False,
                "evidence": "用户直接编辑目标数据",
            }
        )
    intent["pricing"] = pricing
    goal["intent"] = intent


def _summary_value(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (dict, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value)


def _refresh_derived_contract(
    goal: dict[str, Any], capability: DataScriptCapability
) -> None:
    normalized = normalize_execution_contract(goal, capability)
    labels = {
        field.name: field.label
        for field in effective_contract_fields(capability)
        if field.execution_field
    }
    goal["summary"] = "，".join(
        f"{labels[name]}{_summary_value(value)}"
        for name, value in normalized.items()
        if value not in (None, "", [])
    )
    payload = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    goal["contract_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def apply_contract_updates(
    goal: dict[str, Any],
    updates: dict[str, Any],
    capability: DataScriptCapability,
) -> tuple[dict, list[dict]]:
    fields = {field.name: field for field in effective_contract_fields(capability)}
    errors: dict[str, str] = {}
    converted: dict[str, Any] = {}
    for name, value in updates.items():
        field = fields.get(name)
        if field is None:
            errors[name] = "字段不属于当前脚本合同"
            continue
        if field.readonly:
            errors[name] = "字段为只读"
            continue
        try:
            normalized = _normalize_value(field, value)
        except ValueError as exc:
            errors[name] = str(exc)
            continue
        if not _choice_is_valid(field, normalized):
            errors[name] = "字段值不在允许选项中"
            continue
        converted[name] = normalized
    if (
        converted.get("offer_price") not in (None, "")
        and converted.get("offer_unit_prices") not in (None, "", [])
    ):
        message = "统一单价与逐商品单价不能同时填写"
        errors["offer_price"] = message
        errors["offer_unit_prices"] = message
    if errors:
        raise ContractValidationError(errors)

    updated = copy.deepcopy(goal)
    for name, value in converted.items():
        _set_path(updated, fields[name].path, value)
    backwrite_problem_goods_operation(updated, capability, set(converted))
    if "offer_price" in converted and "offer_unit_prices" in fields:
        _delete_path(updated, fields["offer_unit_prices"].path)
    if "offer_unit_prices" in converted and "offer_price" in fields:
        _delete_path(updated, fields["offer_price"].path)
    try:
        _recompute_price_totals(updated, set(converted), fields)
    except ContractValidationError:
        raise
    except ValueError as exc:
        related = next(
            (
                name
                for name in updates
                if name
                in {
                    "offer_price",
                    "offer_unit_prices",
                    "order_shop_count",
                    "order_per_shop",
                    "order_item_num",
                }
            ),
            "pricing",
        )
        raise ContractValidationError({related: str(exc)}) from exc
    _refresh_derived_contract(updated, capability)
    return updated, diff_execution_contract(goal, updated, capability, "direct_edit")
