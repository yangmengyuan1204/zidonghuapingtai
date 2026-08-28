from __future__ import annotations

import re
from typing import Any, Mapping

from app.data_scripts.cart_support import _api_path, _api_success, _configure_client_api_paths
from app.services.system_regression.membership_service import inspect_logged_in_membership, public_membership
from app.vendor.piliangtianjiagouwuche import RakumartClient

_TOKEN_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
_SECRET_RE = re.compile(r"(?i)(password|token|clienttoken|authorization)\s*[:=]\s*\S+")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _safe_reason(text: Any) -> str:
    cleaned = _TOKEN_RE.sub("[token]", _text(text))
    cleaned = _SECRET_RE.sub(lambda match: f"{match.group(1)}=[hidden]", cleaned)
    return cleaned[:200]


def _discount_rows(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    root = payload.get("data") if isinstance(payload, Mapping) else None
    if isinstance(root, list):
        rows = root
    elif isinstance(root, Mapping):
        rows = root.get("data") or root.get("list") or root.get("rows") or []
    else:
        rows = []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _ticket_id(row: Mapping[str, Any]) -> str:
    return _text(row.get("id") or row.get("sn"))


def _ticket_title(row: Mapping[str, Any]) -> str:
    return _text(row.get("name_chinese") or row.get("name_translation") or row.get("type_name") or _ticket_id(row))


def _usable(row: Mapping[str, Any]) -> bool:
    status = row.get("status")
    return status in (None, "", 1, "1")


def _discount_ok(payload: Mapping[str, Any] | None) -> bool:
    if not isinstance(payload, Mapping):
        return False
    if _api_success(payload):
        return True
    if payload.get("success") is False or str(payload.get("success")).strip().lower() == "false":
        return False
    code = payload.get("code")
    if code not in (None, 0, "0"):
        return False
    return isinstance(payload.get("data"), (Mapping, list))


def _is_order_coupon(row: Mapping[str, Any]) -> bool:
    type_id = _as_int(row.get("type"))
    type_name = _text(row.get("type_name"))
    return type_id == 1 or type_name == "优惠券"


def _is_fee_waiver(row: Mapping[str, Any]) -> bool:
    title = " ".join(
        _text(row.get(key))
        for key in ("name_chinese", "name_translation", "type_name")
    )
    return ("手数料" in title or "手续费" in title) and any(
        word in title for word in ("無料", "免费", "免費", "减免", "減免")
    )


def _voucher_kind(row: Mapping[str, Any]) -> str:
    logistics_id = _text(row.get("logistics_id"))
    group = row.get("logistics_group")
    if logistics_id or (isinstance(group, list) and group):
        return "logistics"
    return "all"


def normalize_usable_discounts(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    coupons: list[dict[str, Any]] = []
    vouchers: list[dict[str, Any]] = []
    for row in _discount_rows(payload):
        ticket_id = _ticket_id(row)
        if not ticket_id or not _usable(row):
            continue
        title = _ticket_title(row)
        if _is_order_coupon(row):
            fee_waiver = _is_fee_waiver(row)
            coupon: dict[str, Any] = {
                "id": ticket_id,
                "title": title,
                "type": _text(row.get("type")),
                "fee_waiver": fee_waiver,
            }
            amount = row.get("discounts_amount_jpy")
            if amount not in (None, ""):
                coupon["discounts_amount_jpy"] = _text(amount)
                if not fee_waiver:
                    coupon["amount"] = _text(amount)
            coupons.append(coupon)
            continue
        voucher: dict[str, Any] = {
            "id": ticket_id,
            "title": title,
            "kind": _voucher_kind(row),
        }
        amount = row.get("discounts_amount_jpy")
        if amount not in (None, ""):
            voucher["amount"] = _text(amount)
        logistics_id = _text(row.get("logistics_id"))
        if logistics_id:
            voucher["logistics_id"] = logistics_id
        group = row.get("logistics_group")
        if isinstance(group, list) and group and isinstance(group[0], Mapping):
            name = _text(group[0].get("logistics_name"))
            if name:
                voucher["logistics_name"] = name
        vouchers.append(voucher)
    reason = ""
    if not coupons and not vouchers:
        reason = "这个账号没有可用优惠券或代金券。订单仍可用「手续费减免券」把手续费变成 0。"
    elif not coupons:
        reason = "这个账号没有可用订单优惠券。仍可用「手续费减免券」把手续费变成 0。"
    elif not vouchers:
        reason = "这个账号没有可用配送单代金券。"
    return {"coupons": coupons, "vouchers": vouchers, "reason": reason}


def list_usable_tickets(env: Any, variables: Mapping[str, Any] | None = None) -> dict[str, Any]:
    values = dict(variables or {})
    account = _text(values.get("account"))
    password = _text(values.get("password"))
    if not account or not password:
        return {"coupons": [], "vouchers": [], "reason": "缺少前台账号，无法拉券", "membership": public_membership(None)}
    base_url = _text(getattr(env, "base_url", "") or values.get("base_url"))
    if not base_url:
        return {"coupons": [], "vouchers": [], "reason": "执行环境没有站点地址，无法拉券", "membership": public_membership(None)}
    timeout = _as_int(values.get("timeout"), _as_int(getattr(env, "timeout", None), 25)) or 25
    client = RakumartClient(base_url.rstrip("/"), timeout)
    _configure_client_api_paths(client, values)
    try:
        client.login(account, password, _text(values.get("client_tool") or "1") or "1")
        payload = client.post_form(
            _api_path(values, "client_usable_discount", "/client/user.usableDiscount"),
            {"page": "1", "pageSize": "1000"},
        )
    except Exception as exc:
        return {
            "coupons": [],
            "vouchers": [],
            "reason": _safe_reason(f"优惠券列表拉取失败：{exc}"),
            "membership": public_membership(None),
        }
    membership = inspect_logged_in_membership(client, values)
    if not _discount_ok(payload):
        return {
            "coupons": [],
            "vouchers": [],
            "reason": _safe_reason(
                (payload.get("msg") if isinstance(payload, Mapping) else "") or "优惠券列表拉取失败"
            ),
            "membership": public_membership(membership),
        }
    result = normalize_usable_discounts(payload)
    result["membership"] = public_membership(membership)
    return result
