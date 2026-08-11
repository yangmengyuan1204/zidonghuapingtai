from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Mapping


CENT = Decimal("0.01")


def _decimal(value: Any, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是数字") from exc
    if not number.is_finite():
        raise ValueError(f"{label}必须是有限数字")
    return number


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _active_options(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in (value or []) if isinstance(row, Mapping) and row.get("checked") is not False]


def _option_amount(row: Mapping[str, Any], goods_price: Decimal) -> Decimal:
    price = _decimal(row.get("price") or 0, "OPTION价格")
    num = _decimal(row.get("num") or 0, "OPTION数量")
    if int(row.get("price_type") or 0) == 1:
        return _money((price / Decimal("100")) * goods_price * num)
    return _money(price * num)


def _manual_option_delta(payload: Mapping[str, Any], old_price: Decimal, new_price: Decimal) -> Decimal:
    old_rows = {str(row.get("name") or ""): row for row in _active_options(payload.get("option_old"))}
    new_rows = {str(row.get("name") or ""): row for row in _active_options(payload.get("option_new"))}
    names = set(old_rows) | set(new_rows)
    total = Decimal("0")
    for name in names:
        old_row = old_rows.get(name)
        new_row = new_rows.get(name)
        old_amount = _option_amount(old_row, old_price) if old_row else Decimal("0")
        new_amount = _option_amount(new_row, new_price) if new_row else Decimal("0")
        total += new_amount - old_amount
    return _money(total)


def _inspection_refund_count(old_possible_num: int, option_num: int, completed: int, decrease: int) -> int:
    remaining_items = old_possible_num - decrease
    remaining_inspection = option_num - completed
    if decrease >= option_num:
        return 0 if remaining_items >= remaining_inspection else max(0, remaining_inspection - remaining_items)
    if completed < decrease < option_num:
        pending = option_num - decrease
        return 0 if remaining_items >= pending else max(0, pending - remaining_items)
    return 0


def _automatic_option_delta(payload: Mapping[str, Any], old_price: Decimal, new_price: Decimal) -> Decimal:
    old_possible_num = int(_decimal(payload.get("old_possible_num") or 0, "原可入库数量"))
    new_num = int(_decimal(payload.get("new_num") or 0, "修改后数量"))
    diff_num = new_num - old_possible_num
    completed_inspect_num = int(_decimal(payload.get("complete_inspect_num") or 0, "已检品数量"))
    total = Decimal("0")
    for row in _active_options(payload.get("option_old")):
        if not row.get("auto_calculate", True):
            continue
        old_num = int(_decimal(row.get("num") or 0, "OPTION数量"))
        new_option_num = old_num
        if diff_num > 0:
            raise ValueError("商品数量增加时必须设置业务修改OPTION")
        if diff_num < 0:
            refund_count = abs(diff_num)
            if "检品" in str(row.get("name") or ""):
                refund_count = _inspection_refund_count(
                    old_possible_num,
                    old_num,
                    completed_inspect_num,
                    abs(diff_num),
                )
            new_option_num = max(0, old_num - refund_count)
        new_row = {**row, "num": new_option_num}
        total += _option_amount(new_row, new_price) - _option_amount(row, old_price)
    return _money(total)


@dataclass(frozen=True)
class ProblemAmountBreakdown:
    goods_delta: Decimal
    freight_delta: Decimal
    service_delta: Decimal
    option_delta: Decimal
    total_cny: Decimal


def calculate_problem_amount(payload: Mapping[str, Any]) -> ProblemAmountBreakdown:
    old_total_num = _decimal(payload.get("old_total_num") or 0, "原整番数量")
    old_price = _decimal(payload.get("old_price") or 0, "原单价")
    new_num = _decimal(payload.get("new_num") or 0, "修改后数量")
    new_price = _decimal(payload.get("new_price") or 0, "修改后单价")
    old_freight = _decimal(payload.get("old_freight") or 0, "原运费")
    new_freight = _decimal(payload.get("new_freight") or 0, "修改后运费")

    goods_delta = _money(new_num * new_price - old_total_num * old_price)
    if bool(payload.get("goods_fee_free")):
        goods_delta = Decimal("0.00")
    freight_delta = _money(new_freight - old_freight)

    service_delta = Decimal("0.00")
    service_rate = _decimal(payload.get("service_rate") or 0, "手续费率")
    service_should = _money(goods_delta * service_rate)
    has_discount = bool(payload.get("service_discount"))
    if not has_discount:
        if goods_delta > 0:
            service_delta = service_should
        elif (
            goods_delta < 0
            and int(payload.get("service_deal_suggest") or 0) == 2
            and bool(payload.get("service_fee_paid"))
        ):
            service_delta = service_should

    option_rule = int(payload.get("option_deal_suggest") or 0)
    if option_rule == 1:
        option_delta = _manual_option_delta(payload, old_price, new_price)
    elif option_rule == 2:
        option_delta = _automatic_option_delta(payload, old_price, new_price)
    else:
        option_delta = Decimal("0.00")

    total = _money(goods_delta + freight_delta + service_delta + option_delta)
    return ProblemAmountBreakdown(goods_delta, freight_delta, service_delta, option_delta, total)


__all__ = ["ProblemAmountBreakdown", "calculate_problem_amount"]
