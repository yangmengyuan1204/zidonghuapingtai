from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


@dataclass(frozen=True)
class ScenarioSpec:
    key: str
    name: str
    category: str
    payment_mode: str = ""
    expected_direction: str = "debit"
    problem_type: int | None = None
    adjustment: str = ""


class ScenarioConfigurationError(ValueError):
    pass


SCENARIO_CATALOG: tuple[ScenarioSpec, ...] = (
    ScenarioSpec("order_balance", "普通订单余额支付", "order", payment_mode="balance"),
    ScenarioSpec("order_bank", "普通订单银行支付", "order", payment_mode="bank"),
    ScenarioSpec("order_part_balance", "分批付款余额首尾款", "order_part", payment_mode="balance"),
    ScenarioSpec("order_part_bank", "分批付款银行首尾款", "order_part", payment_mode="bank"),
    ScenarioSpec("porder_balance", "配送单余额支付", "porder", payment_mode="balance"),
    ScenarioSpec("porder_bank", "配送单银行支付", "porder", payment_mode="bank"),
    ScenarioSpec(
        "problem_quantity_refund",
        "问题产品数量减少退款",
        "problem_goods",
        expected_direction="credit",
        problem_type=3,
        adjustment="quantity_down",
    ),
    ScenarioSpec(
        "problem_price_refund",
        "问题产品单价下调退款",
        "problem_goods",
        expected_direction="credit",
        problem_type=1,
        adjustment="price_down",
    ),
    ScenarioSpec(
        "problem_freight_refund",
        "问题产品运费下调退款",
        "problem_goods",
        expected_direction="credit",
        problem_type=2,
        adjustment="freight_down",
    ),
    ScenarioSpec(
        "problem_option_topup",
        "问题产品 OPTION 费用增加补款",
        "problem_goods",
        expected_direction="debit",
        problem_type=6,
        adjustment="option_up",
    ),
    ScenarioSpec(
        "problem_mixed_refund",
        "问题产品混合调整退款",
        "problem_goods",
        expected_direction="credit",
        problem_type=5,
        adjustment="mixed_down",
    ),
    ScenarioSpec(
        "problem_zero_control",
        "问题产品零金额对照",
        "problem_goods",
        expected_direction="none",
        problem_type=9,
        adjustment="unchanged",
    ),
)


def problem_goods_scenarios() -> tuple[ScenarioSpec, ...]:
    return tuple(item for item in SCENARIO_CATALOG if item.category == "problem_goods")


def _decimal(value: Any, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ScenarioConfigurationError(f"{label}不是有效金额") from exc
    if not number.is_finite() or number < 0:
        raise ScenarioConfigurationError(f"{label}必须是非负有限金额")
    return number


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text == "-0" else text


def _int_value(value: Any, label: str) -> int:
    number = _decimal(value, label)
    if number != number.to_integral_value():
        raise ScenarioConfigurationError(f"{label}必须是整数")
    return int(number)


def _candidate_number(candidate: Mapping[str, Any]) -> int:
    for key in ("possible_num", "now_num", "confirm_num", "pre_num"):
        if candidate.get(key) not in (None, ""):
            return _int_value(candidate.get(key), "问题产品数量")
    raise ScenarioConfigurationError("问题产品候选缺少可调整数量")


def _candidate_money(candidate: Mapping[str, Any], *keys: str) -> Decimal:
    for key in keys:
        if candidate.get(key) not in (None, ""):
            return _decimal(candidate.get(key), key)
    return Decimal("0")


def _fixed_option(candidate: Mapping[str, Any]) -> dict[str, Any]:
    options = candidate.get("option") if isinstance(candidate.get("option"), list) else []
    for raw in options:
        if isinstance(raw, dict) and raw.get("checked") is not False and int(raw.get("price_type") or 0) == 0:
            return dict(raw)
    raise ScenarioConfigurationError("问题产品场景需要一个可调整的固定金额 OPTION")


def _adjusted_options(candidate: Mapping[str, Any], delta: Decimal) -> list[dict[str, Any]]:
    selected = _fixed_option(candidate)
    current_price = _decimal(selected.get("price") or 0, "OPTION 金额")
    selected["price"] = _decimal_text(max(Decimal("0"), current_price + delta))
    return [selected]


def build_problem_goods_variables(
    scenario: ScenarioSpec,
    candidate: Mapping[str, Any],
    *,
    amount_step: Decimal = Decimal("1"),
) -> dict[str, Any]:
    if scenario.category != "problem_goods" or scenario.problem_type is None:
        raise ScenarioConfigurationError(f"场景 {scenario.key} 不是问题产品场景")
    quantity = _candidate_number(candidate)
    price = _candidate_money(candidate, "confirm_price", "price", "pre_price")
    freight = _candidate_money(candidate, "confirm_freight", "freight", "pre_freight")
    step = abs(_decimal(amount_step, "调整步长"))
    values: dict[str, Any] = {
        "order_purchase_id": int(candidate.get("order_purchase_id") or 0),
        "order_detail_id": int(candidate.get("order_detail_id") or 0),
        "problem_type": scenario.problem_type,
        "problem_num": 1,
        "pre_num": quantity,
        "pre_price": _decimal_text(price),
        "pre_freight": _decimal_text(freight),
        "client_deal_choice": "accept",
        "service_deal_suggest": 2,
        "option_deal_suggest": 2,
        "g_deal_type": "仅退款",
        "create_if_missing": True,
        "confirm_distribution": True,
    }
    if not values["order_purchase_id"] or not values["order_detail_id"]:
        raise ScenarioConfigurationError("问题产品候选缺少采购明细或订单明细 ID")

    if scenario.adjustment == "quantity_down":
        if quantity < 1:
            raise ScenarioConfigurationError("当前数量不足，无法执行减少数量场景")
        values["pre_num"] = quantity - 1
    elif scenario.adjustment == "price_down":
        values["pre_price"] = _decimal_text(max(Decimal("0"), price - step))
    elif scenario.adjustment == "freight_down":
        values["pre_freight"] = _decimal_text(max(Decimal("0"), freight - step))
    elif scenario.adjustment == "option_up":
        values["option_deal_suggest"] = 1
        values["option_new"] = _adjusted_options(candidate, step)
    elif scenario.adjustment == "mixed_down":
        if quantity < 1:
            raise ScenarioConfigurationError("当前数量不足，无法执行混合调整场景")
        values["pre_num"] = quantity - 1
        values["pre_price"] = _decimal_text(max(Decimal("0"), price - step))
        values["pre_freight"] = _decimal_text(max(Decimal("0"), freight - step))
        values["option_deal_suggest"] = 1
        values["option_new"] = _adjusted_options(candidate, -step)
    elif scenario.adjustment == "unchanged":
        values["service_deal_suggest"] = 1
        values["g_deal_type"] = "其他"
    else:
        raise ScenarioConfigurationError(f"不支持的问题产品调整方式：{scenario.adjustment}")
    return values

