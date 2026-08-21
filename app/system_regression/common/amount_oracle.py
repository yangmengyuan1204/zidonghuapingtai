from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping


CENT = Decimal("0.01")


def _decimal(value: Any, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label}不是有效金额") from exc
    if not number.is_finite():
        raise ValueError(f"{label}必须是有限金额")
    return number


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _number(candidate: Mapping[str, Any], *keys: str) -> Decimal:
    for key in keys:
        if candidate.get(key) not in (None, ""):
            return _decimal(candidate[key], key)
    raise ValueError(f"候选缺少金额字段：{', '.join(keys)}")


def _active_options(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or [] if isinstance(row, Mapping) and row.get("checked") is not False]


def _option_amount(row: Mapping[str, Any], goods_price: Decimal) -> Decimal:
    price = _decimal(row.get("price") or 0, "OPTION价格")
    quantity = _decimal(row.get("num") or row.get("quantity") or 0, "OPTION数量")
    if int(row.get("price_type") or 0) == 1:
        return _money(price / Decimal("100") * quantity * goods_price)
    return _money(price * quantity)


def _inspection_refund_count(old_quantity: int, option_quantity: int, completed: int, decrease: int) -> int:
    remaining_items = old_quantity - decrease
    remaining_inspection = option_quantity - completed
    if decrease >= option_quantity:
        return 0 if remaining_items >= remaining_inspection else max(0, remaining_inspection - remaining_items)
    if completed < decrease < option_quantity:
        pending = option_quantity - decrease
        return 0 if remaining_items >= pending else max(0, pending - remaining_items)
    return 0


@dataclass(frozen=True)
class ProblemAmountExpectation:
    goods_cny: Decimal
    freight_cny: Decimal
    service_cny: Decimal
    option_cny: Decimal
    total_cny: Decimal
    direction: str


def expected_problem_amount(
    candidate: Mapping[str, Any],
    request: Mapping[str, Any],
) -> ProblemAmountExpectation:
    if not any(candidate.get(key) not in (None, "") for key in ("possible_num", "now_num", "confirm_num", "pre_num")):
        if not any(request.get(key) not in (None, "") for key in ("pre_num", "pre_price", "pre_freight")):
            return ProblemAmountExpectation(
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("0.00"),
                Decimal("0.00"),
                "none",
            )
        raise ValueError("候选缺少金额基线")
    old_quantity = int(_number(candidate, "possible_num", "now_num", "confirm_num", "pre_num"))
    old_price = _number(candidate, "confirm_price", "price", "pre_price")
    old_freight = _number(candidate, "confirm_freight", "freight", "pre_freight")
    new_quantity = int(_decimal(request.get("pre_num", old_quantity), "修改后数量"))
    new_price = _decimal(request.get("pre_price", old_price), "修改后单价")
    new_freight = _decimal(request.get("pre_freight", old_freight), "修改后运费")

    goods = _money(new_quantity * new_price - old_quantity * old_price)
    freight = _money(new_freight - old_freight)
    service = Decimal("0.00")
    service_rate = _decimal(request.get("service_rate") or candidate.get("service_rate") or 0, "手续费率")
    if not request.get("service_discount"):
        service_should = _money(goods * service_rate)
        if goods > 0 or (goods < 0 and int(request.get("service_deal_suggest") or 2) == 2 and candidate.get("service_fee_paid", True)):
            service = service_should

    old_options = _active_options(candidate.get("option"))
    option_rule = int(request.get("option_deal_suggest") or 0)
    option = Decimal("0.00")
    if option_rule == 1:
        new_options = _active_options(request.get("option_new") or old_options)
        old_by_name = {str(row.get("name") or ""): row for row in old_options}
        new_by_name = {str(row.get("name") or ""): row for row in new_options}
        for name in set(old_by_name) | set(new_by_name):
            option += _option_amount(new_by_name[name], new_price) if name in new_by_name else Decimal("0")
            option -= _option_amount(old_by_name[name], old_price) if name in old_by_name else Decimal("0")
    elif option_rule == 2:
        decrease = max(0, old_quantity - new_quantity)
        for row in old_options:
            if row.get("auto_calculate", True) is False:
                continue
            new_option_quantity = int(_decimal(row.get("num") or 0, "OPTION数量"))
            if decrease:
                refund_count = decrease
                if "检品" in str(row.get("name") or ""):
                    refund_count = _inspection_refund_count(
                        old_quantity,
                        new_option_quantity,
                        int(request.get("complete_inspect_num") or 0),
                        decrease,
                    )
                new_option_quantity = max(0, new_option_quantity - refund_count)
            new_row = {**row, "num": new_option_quantity}
            option += _option_amount(new_row, new_price) - _option_amount(row, old_price)

    total = _money(goods + freight + service + option)
    direction = "credit" if total < 0 else "debit" if total > 0 else "none"
    return ProblemAmountExpectation(goods, freight, service, option, total, direction)


__all__ = ["ProblemAmountExpectation", "expected_problem_amount"]
