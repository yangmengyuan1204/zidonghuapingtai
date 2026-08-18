from __future__ import annotations

from typing import Any, Mapping

from app.data_scripts.orders import inspect_order_options
from app.services.system_regression.ticket_service import _safe_reason, _text


def _as_price_type(value: Any) -> int:
    try:
        return 1 if int(value) == 1 else 0
    except (TypeError, ValueError):
        return 0


def normalize_order_options(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    rows = []
    for row in (payload or {}).get("options") or []:
        if not isinstance(row, Mapping):
            continue
        key = _text(row.get("key") or row.get("id") or row.get("name"))
        if not key:
            continue
        name = _text(row.get("label") or row.get("name") or row.get("name_translate") or key)
        rows.append(
            {
                "key": key,
                "id": _text(row.get("id") or key),
                "name": name,
                "name_translate": _text(row.get("name_translate")),
                "price": _text(row.get("price") or "0") or "0",
                "price_type": _as_price_type(row.get("price_type")),
                "unit": _text(row.get("unit")),
            }
        )
    return {
        "options": rows,
        "path": _text((payload or {}).get("path")) or "/client/order.optionList",
        "reason": "" if rows else "这个环境没有可用 OPTION。",
    }


def list_order_options(env: Any, variables: Mapping[str, Any] | None = None) -> dict[str, Any]:
    values = dict(variables or {})
    if not _text(values.get("account")) or not _text(values.get("password")):
        return {"options": [], "path": "/client/order.optionList", "reason": "缺少前台账号，无法拉 OPTION"}
    if not _text(getattr(env, "base_url", "") or values.get("base_url")):
        return {"options": [], "path": "/client/order.optionList", "reason": "执行环境没有站点地址，无法拉 OPTION"}
    try:
        payload = inspect_order_options(env, values)
    except Exception as exc:
        return {
            "options": [],
            "path": "/client/order.optionList",
            "reason": _safe_reason(f"OPTION 列表拉取失败：{exc}"),
        }
    return normalize_order_options(payload if isinstance(payload, Mapping) else {})
