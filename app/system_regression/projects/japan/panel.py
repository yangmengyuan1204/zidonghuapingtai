from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping


SERVICE_COUPON_ID = "__service_discount__"

PACK_OPTION = {"name": "加固包装", "price_type": 0, "price": "2.5", "num": 1, "checked": True}
INSPECT_OPTION = {"name": "检品", "price_type": 1, "price": "5", "num": 1, "checked": True}


def _money(value: Any, currency: str = "CNY") -> dict[str, str]:
    return {"value": str(value), "currency": currency}


def _option(name: str, price_type: int, price: Any, num: int = 1) -> dict[str, Any]:
    return {"name": name, "price_type": price_type, "price": str(price), "num": num, "checked": True}


def _item(
    sorting: int = 1,
    *,
    quantity: int = 1,
    price: Any = "10",
    freight: Any = "3",
    options: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "sorting": sorting,
        "quantity": quantity,
        "offer_price": _money(price),
        "offer_freight": _money(freight),
        "options": list(options or []),
    }


def _part_pay(
    enabled: bool = False,
    *,
    percent: int = 50,
    tail_node: str = "before_shelf",
    tail_partial: bool = False,
    tail_sortings: str = "",
    fee_timing: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "percent": percent,
        "tail_node": tail_node,
        "tail_partial": tail_partial,
        "tail_sortings": tail_sortings,
        "fee_timing": dict(
            fee_timing
            or {
                "domestic_freight": "first",
                "service_fee": "first",
                "additional_service_fee": "first",
                "other_fee": "first",
            }
        ),
    }


def _empty_porder(**overrides: Any) -> dict[str, Any]:
    payload = {
        "sku_count": 1,
        "send_num": 1,
        "box_count": 1,
        "box_length": 58,
        "box_width": 51,
        "box_height": 50,
        "box_weight": 10,
        "logistics": "25",
        "price_manual": False,
        "logistics_price": _money("0"),
        "extra_name": "",
        "extra_fee": _money("0"),
        "payment_mode": "balance",
        "voucher": {"selectedId": ""},
    }
    payload.update(overrides)
    return payload


def _order_block(items: list[dict[str, Any]], *, other_name: str = "", other_amount: Any = "0") -> dict[str, Any]:
    first = items[0] if items else _item()
    return {
        "item_count": max(1, len(items)),
        "default_quantity": int(first.get("quantity") or 1),
        "default_offer_price": dict(first.get("offer_price") or _money("10")),
        "default_freight": dict(first.get("offer_freight") or _money("3")),
        "other_fee_name": other_name,
        "other_fee_amount": _money(other_amount),
    }


def order_panel(
    *,
    payment_mode: str = "balance",
    payment_plan: str = "full",
    items: list[dict[str, Any]] | None = None,
    other_name: str = "",
    other_amount: Any = "0",
    coupon_id: str = "",
    part: dict[str, Any] | None = None,
    finance_confirm: bool | None = None,
    **flags: Any,
) -> dict[str, Any]:
    rows = list(items or [_item()])
    selected = coupon_id or ""
    payload: dict[str, Any] = {
        "payment_mode": payment_mode,
        "payment_plan": payment_plan,
        "order": _order_block(rows, other_name=other_name, other_amount=other_amount),
        "items": rows,
        "part_pay": part or _part_pay(enabled=payment_plan == "part"),
        "coupon": {"selectedId": selected},
        "service_discount": bool(flags.get("service_discount") or selected),
        "discounts_id": "" if selected in {"", SERVICE_COUPON_ID} else selected,
        "porder": _empty_porder(),
        "ledger_wait_seconds": 30,
        "amount_step": "1",
    }
    if other_name:
        payload["other_fee_name"] = other_name
        payload["other_fee_amount"] = str(other_amount)
    if finance_confirm is not None:
        payload["finance_confirm"] = finance_confirm
    if payment_plan == "part" and "first_payment_rate" not in flags:
        percent = int((payload["part_pay"] or {}).get("percent") or 50)
        payload["first_payment_rate"] = str((Decimal(percent) / Decimal("100")).quantize(Decimal("0.01")))
    payload.update(flags)
    return payload


def porder_panel(
    *,
    payment_mode: str = "balance",
    finance_confirm: bool | None = None,
    extra_name: str = "",
    extra_fee: Any = "0",
    logistics: str = "25",
    price_manual: bool = False,
    logistics_price: Any = "0",
    **flags: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "payment_mode": payment_mode,
        "payment_plan": "full",
        "order": _order_block([_item()]),
        "items": [],
        "part_pay": _part_pay(False),
        "coupon": {"selectedId": ""},
        "porder": _empty_porder(
            payment_mode=payment_mode,
            extra_name=extra_name,
            extra_fee=_money(extra_fee),
            logistics=logistics,
            price_manual=price_manual,
            logistics_price=_money(logistics_price),
        ),
        "ledger_wait_seconds": 30,
        "amount_step": "1",
    }
    if finance_confirm is not None:
        payload["finance_confirm"] = finance_confirm
    payload.update(flags)
    return payload


def _shifted(value: str, delta: int) -> str:
    number = Decimal(str(value or "0")) + Decimal(delta)
    if number < 0:
        number = Decimal("0")
    return format(number.normalize(), "f")


def _pre_state(adjustment: str, *, quantity: int, price: str, freight: str) -> tuple[int, str, str]:
    pre_num = quantity
    pre_price = price
    pre_freight = freight
    if adjustment in {
        "quantity_partial_down",
        "quantity_down",
        "fixed_quantity_down",
        "rate_quantity_down",
        "inspection_completed",
        "non_auto_unchanged",
    }:
        pre_num = max(0, quantity - 1)
    elif adjustment == "quantity_up":
        pre_num = quantity + 1
    elif adjustment == "quantity_all_down":
        pre_num = 0
    if adjustment in {
        "price_down",
        "goods_down_refund_service",
        "goods_down_keep_service",
        "goods_down_discount_service",
        "zero_service_rate",
        "rate_goods_price_down",
        "net_refund",
    } or (adjustment == "rate_price_down"):
        pre_price = _shifted(price, -1)
    elif adjustment in {
        "price_up",
        "goods_up_charge_service",
        "goods_up_discount_service",
        "net_topup",
    }:
        pre_price = _shifted(price, 1)
    if adjustment in {"freight_down", "net_topup"}:
        pre_freight = _shifted(freight, -1)
    elif adjustment in {"freight_up", "price_down_freight_up_net_refund", "net_refund"}:
        pre_freight = _shifted(freight, 1)
    if adjustment == "price_up_freight_down_net_topup":
        pre_price = _shifted(price, 1)
        pre_freight = _shifted(freight, -1)
    if adjustment == "price_down_freight_up_net_refund":
        pre_price = _shifted(price, -1)
        pre_freight = _shifted(freight, 1)
    if adjustment == "quantity_and_price_down":
        pre_num = max(0, quantity - 1)
        pre_price = _shifted(price, -1)
    if adjustment == "quantity_down_price_up_net_refund":
        pre_num = max(0, quantity - 1)
        pre_price = _shifted(price, 1)
    return pre_num, pre_price, pre_freight


def problem_panel(
    *,
    name: str,
    problem_type: int,
    adjustment: str = "",
    option_adjustment: str = "",
    client_deal_choice: str = "accept",
    client_deal_other: str = "",
    g_deal_type: str = "仅退款",
    service_deal_suggest: int = 2,
    option_deal_suggest: int = 2,
    service_discount: bool = False,
    items: list[dict[str, Any]] | None = None,
    quantity: int = 2,
    **flags: Any,
) -> dict[str, Any]:
    change = option_adjustment or adjustment
    need_options = (
        "option" in str(change).lower()
        or "opt" in str(change).lower()
        or option_deal_suggest == 1
        or problem_type in {6, 7}
    )
    options = [dict(PACK_OPTION), dict(INSPECT_OPTION)] if need_options else []
    rows = list(items or [_item(1, quantity=quantity, options=options)])
    price = str((rows[0].get("offer_price") or {}).get("value") or "10")
    freight = str((rows[0].get("offer_freight") or {}).get("value") or "3")
    qty = int(rows[0].get("quantity") or quantity)
    pre_num, pre_price, pre_freight = _pre_state(change, quantity=qty, price=price, freight=freight)
    coupon_id = SERVICE_COUPON_ID if service_discount else ""
    if client_deal_choice == "other" and not str(client_deal_other).strip():
        client_deal_other = "系统回归自定义回复"
    payload = order_panel(
        items=rows,
        coupon_id=coupon_id,
        service_discount=service_discount,
        **{key: value for key, value in flags.items() if key not in {"validate_components"}},
    )
    payload["problem_type"] = problem_type
    payload["adjustment"] = adjustment
    payload["option_adjustment"] = option_adjustment
    payload["amount_step"] = "1"
    payload["service_deal_suggest"] = service_deal_suggest
    payload["option_deal_suggest"] = option_deal_suggest
    payload["client_deal_choice"] = client_deal_choice
    payload["client_deal_other"] = client_deal_other
    payload["g_deal_type"] = g_deal_type
    payload["service_discount"] = service_discount
    if flags.get("validate_components"):
        payload["validate_components"] = True
    payload["problem_goods"] = {
        "problem_type": problem_type,
        "problem_num": 1,
        "problem_description": name,
        "translation_content": "システム回帰テスト",
        "pre_num": pre_num,
        "pre_price": _money(pre_price),
        "pre_freight": _money(pre_freight),
        "client_deal_choice": client_deal_choice,
        "client_deal_other": client_deal_other,
        "service_deal_suggest": service_deal_suggest,
        "option_deal_suggest": option_deal_suggest,
        "option_new": [],
        "g_deal_type": g_deal_type,
        "business_decision": f"{name}：系统回归自动处理",
        "purchase_remark": "系统回归",
        "confirm_distribution": True,
        "service_discount": service_discount,
    }
    return payload


def guard_panel(name: str, *, guard_kind: str, part_pay: bool = False) -> dict[str, Any]:
    payload = problem_panel(
        name=name,
        problem_type=1,
        items=[_item(1, quantity=2, options=[dict(PACK_OPTION), dict(INSPECT_OPTION)] if any(token in guard_kind for token in ("option", "rate", "quantity")) else [])],
        part=_part_pay(True, percent=50) if part_pay else None,
        payment_plan="part" if part_pay else "full",
    )
    if part_pay:
        payload["payment_plan"] = "part"
        payload["first_payment_rate"] = "0.5"
    payload["guard_kind"] = guard_kind
    return payload


__all__ = [
    "INSPECT_OPTION",
    "PACK_OPTION",
    "SERVICE_COUPON_ID",
    "guard_panel",
    "order_panel",
    "porder_panel",
    "problem_panel",
    "_item",
    "_option",
    "_part_pay",
]
