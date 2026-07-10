from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    'Decimal',
    'OrderedDict',
    '_admin_rows_from_payload',
    '_api_path',
    '_api_success',
    '_as_bool',
    '_as_float',
    '_as_int',
    '_as_list',
    '_decimal_text',
    '_field_text',
    '_flatten_purchase_items',
    '_grid_candidates',
    '_money_total',
    '_payload_brief',
    '_positive_decimal',
    '_positive_text',
    '_post_admin_form',
    '_purchase_item_brief',
    '_purchase_item_id',
    '_purchase_item_values',
    '_purchase_list_fields',
    '_purchase_order_detail_id',
    '_purchase_status_code',
    '_purchase_status_name',
    '_purchase_still_pending',
    '_walk_grid_candidates',
    'datetime',
    'time',
    'timedelta',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _compat_wrapper(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        _sync_compat_globals()
        return func(*args, **kwargs)

    return wrapped


def _impl__purchase_timestamp_no() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def _impl__purchase_list_fields(variables: Dict[str, Any], order_sn: str) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["page"] = _as_int(variables.get("purchase_page") or variables.get("page"), 1)
    fields["pageSize"] = _as_int(variables.get("purchase_page_size") or variables.get("page_size") or variables.get("pageSize"), 20)
    fields["status"] = str(variables.get("purchase_status") or "\u5168\u90e8")
    fields["dateStart"] = _field_text(variables.get("purchase_date_start") or variables.get("dateStart"))
    fields["dateEnd"] = _field_text(variables.get("purchase_date_end") or variables.get("dateEnd"))
    fields["user_id"] = _field_text(variables.get("user_id"))
    fields["order_sn"] = order_sn
    fields["g_id"] = _field_text(variables.get("g_id"))
    fields["is_urgent"] = _field_text(variables.get("is_urgent"))
    fields["overdue"] = _field_text(variables.get("overdue"))
    for key in ["realname", "p_name", "y_name", "goods_from", "keywords"]:
        value = variables.get(key)
        if value not in (None, ""):
            fields[key] = value
    return fields


def _impl__flatten_purchase_items(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    items: list[Dict[str, Any]] = []
    for row in rows:
        purchases = (
            row.get("order_purchase")
            or row.get("purchase")
            or row.get("purchase_list")
            or row.get("list")
            or row.get("items")
        )
        if isinstance(purchases, list):
            for purchase in purchases:
                if not isinstance(purchase, dict):
                    continue
                item = dict(purchase)
                item.setdefault("_order_sn", row.get("order_sn"))
                item.setdefault("_order_id", row.get("id"))
                item.setdefault("_order_status", row.get("status"))
                items.append(item)
            continue
        if row.get("id") not in (None, "") and (row.get("order_detail") or row.get("purchase_no") is not None):
            item = dict(row)
            item.setdefault("_order_sn", row.get("order_sn"))
            items.append(item)
    return items


def _impl__purchase_item_id(item: Dict[str, Any]) -> Any:
    return item.get("id") or item.get("order_purchase_id") or item.get("purchase_id")


def _impl__select_purchase_items(items: list[Dict[str, Any]], order_sn: str, variables: Dict[str, Any]) -> list[Dict[str, Any]]:
    requested_ids = _as_list(variables.get("purchase_ids"), [])
    requested_id_set = {str(item) for item in requested_ids}
    selected: list[Dict[str, Any]] = []
    for item in items:
        if order_sn and str(item.get("_order_sn") or item.get("order_sn") or "") != order_sn:
            continue
        if requested_id_set and str(_purchase_item_id(item) or "") not in requested_id_set:
            continue
        selected.append(item)
    if not selected and not order_sn and not requested_id_set:
        selected = list(items)
    try:
        item_limit = int(variables.get("purchase_item_limit") or 0)
    except (TypeError, ValueError):
        item_limit = 0
    if item_limit > 0:
        selected = selected[:item_limit]
    return selected


def _impl__positive_text(*values: Any, fallback: str = "0") -> str:
    for value in values:
        number = _positive_decimal(value)
        if number is not None:
            return _decimal_text(number)
    return _decimal_text(fallback)


def _impl__purchase_item_values(item: Dict[str, Any], variables: Dict[str, Any]) -> tuple[str, str, str, str]:
    detail = item.get("order_detail") if isinstance(item.get("order_detail"), dict) else {}
    price = _positive_text(
        item.get("final_dicker_price"),
        detail.get("confirm_dicker_price"),
        detail.get("confirm_price"),
        detail.get("price"),
        variables.get("purchase_unit_price"),
        fallback="10",
    )
    freight = _positive_text(
        item.get("final_dicker_freight"),
        detail.get("confirm_dicker_freight"),
        detail.get("confirm_freight"),
        detail.get("freight"),
        variables.get("purchase_freight"),
        fallback="0",
    )
    quantity = _positive_text(
        detail.get("confirm_num"),
        detail.get("num"),
        item.get("confirm_num"),
        item.get("num"),
        fallback="1",
    )
    return price, freight, quantity, _money_total(quantity, price, freight)


def _impl__purchase_status_name(item: Dict[str, Any]) -> str:
    detail = item.get("order_detail") if isinstance(item.get("order_detail"), dict) else {}
    return str(item.get("statusName") or item.get("status_name") or detail.get("statusName") or detail.get("status_name") or "\u5f85\u62cd\u4e0b")


def _impl__purchase_save_rows(
    items: list[Dict[str, Any]],
    variables: Dict[str, Any],
    purchase_no: str,
) -> tuple[list[Dict[str, Any]], list[Any]]:
    rows: list[Dict[str, Any]] = []
    ids: list[Any] = []
    for item in items:
        item_id = _purchase_item_id(item)
        if item_id in (None, ""):
            continue
        price, freight, _, account_payable = _purchase_item_values(item, variables)
        ids.append(item_id)
        rows.append(
            {
                "id": item_id,
                "final_dicker_price": price,
                "final_dicker_freight": freight,
                "purchase_no": purchase_no,
                "accountPayable": account_payable,
            }
        )
    return rows, ids


def _impl__purchase_wait_pay_rows(items: list[Dict[str, Any]], variables: Dict[str, Any], purchase_no: str) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for item in items:
        if _purchase_item_id(item) in (None, ""):
            continue
        price, freight, _, account_payable = _purchase_item_values(item, variables)
        rows.append(
            {
                "final_dicker_price": price,
                "final_dicker_freight": freight,
                "purchase_no": purchase_no,
                "status": _purchase_status_name(item),
                "accountPayable": account_payable,
            }
        )
    return rows


def _impl__purchase_item_brief(item: Dict[str, Any]) -> Dict[str, Any]:
    detail = item.get("order_detail") if isinstance(item.get("order_detail"), dict) else {}
    return {
        "id": _purchase_item_id(item),
        "order_detail_id": _purchase_order_detail_id(item),
        "order_sn": item.get("_order_sn") or item.get("order_sn"),
        "purchase_no": item.get("purchase_no"),
        "status": item.get("status"),
        "statusName": _purchase_status_name(item),
        "goods_id": detail.get("goods_id") or item.get("goods_id"),
        "confirm_num": detail.get("confirm_num") or detail.get("num") or item.get("num"),
    }


def _impl__purchase_order_detail_id(item: Dict[str, Any]) -> str:
    detail = item.get("order_detail") if isinstance(item.get("order_detail"), dict) else {}
    for value in [
        item.get("order_detail_id"),
        item.get("orderDetailId"),
        item.get("detail_id"),
        detail.get("id"),
        detail.get("order_detail_id"),
        detail.get("orderDetailId"),
        detail.get("detail_id"),
    ]:
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _impl__purchase_wait_pay_fields(variables: Dict[str, Any], purchase_no: str, with_status: bool = True) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["page"] = _as_int(variables.get("finance_page") or variables.get("page"), 1)
    fields["pageSize"] = _as_int(variables.get("finance_page_size") or variables.get("page_size") or variables.get("pageSize"), 20)
    if with_status:
        fields["status"] = str(variables.get("finance_wait_pay_status") or "2")
    fields["dateStart"] = str(
        variables.get("finance_date_start") or (datetime.now() - timedelta(days=_as_int(variables.get("finance_days"), 30))).strftime("%Y-%m-%d 00:00:00")
    )
    fields["dateEnd"] = str(variables.get("finance_date_end") or datetime.now().strftime("%Y-%m-%d 23:59:59"))
    fields["purchase_no"] = purchase_no
    for key in ["order_sn", "user_id", "realname", "link_type"]:
        value = variables.get(key)
        if value not in (None, ""):
            fields[key] = value
    return fields


def _impl__select_purchase_wait_pay(rows: list[Dict[str, Any]], purchase_no: str) -> Dict[str, Any] | None:
    for row in rows:
        if purchase_no and str(row.get("purchase_no") or "") == purchase_no:
            return row
    return rows[0] if rows else None


def _impl__finance_purchase_brief(row: Dict[str, Any] | None) -> Dict[str, Any]:
    if not row:
        return {}
    return {
        "id": row.get("id"),
        "purchase_no": row.get("purchase_no"),
        "order_sn": row.get("order_sn"),
        "status": row.get("status"),
        "statusName": row.get("statusName") or row.get("status_name"),
        "shouldPay": row.get("shouldPay"),
        "clientTotal": row.get("clientTotal"),
    }


def _impl__follow_list_fields(variables: Dict[str, Any], purchase_no: str, order_sn: str, status_value: str | None = None) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["page"] = _as_int(variables.get("follow_page") or variables.get("page"), 1)
    fields["pageSize"] = _as_int(variables.get("follow_page_size") or variables.get("page_size") or variables.get("pageSize"), 20)
    fields["status"] = str(status_value if status_value is not None else variables.get("follow_status") or "3")
    fields["dateStart"] = _field_text(variables.get("follow_date_start"))
    fields["dateEnd"] = _field_text(variables.get("follow_date_end"))
    fields["user_id"] = _field_text(variables.get("user_id"))
    fields["order_sn"] = order_sn
    fields["express_no"] = _field_text(variables.get("express_no"))
    fields["purchase_no"] = purchase_no
    fields["order_part"] = _field_text(variables.get("order_part"))
    fields["realname"] = _field_text(variables.get("realname"))
    return fields


def _impl__flatten_follow_items(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    items: list[Dict[str, Any]] = []
    for row in rows:
        children = row.get("list") or row.get("items") or row.get("order_purchase")
        if isinstance(children, list):
            for child in children:
                if not isinstance(child, dict):
                    continue
                item = dict(child)
                item.setdefault("_order_sn", row.get("order_sn"))
                item.setdefault("_purchase_no", row.get("purchase_no"))
                items.append(item)
            continue
        if row.get("order_purchase_id") not in (None, "") or row.get("id") not in (None, ""):
            items.append(dict(row))
    return items


def _impl__preview_rows_from_payload(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        rows = data.get("data") or data.get("list") or data.get("rows") or []
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        return [data]
    return []


def _impl__preview_items(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    items: list[Dict[str, Any]] = []
    for row in rows:
        children = row.get("list") or row.get("items") or row.get("order_purchase")
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    item = dict(child)
                    item.setdefault("_preview_user_id", ((row.get("user") if isinstance(row.get("user"), dict) else {}) or {}).get("id"))
                    items.append(item)
        elif row.get("order_purchase_id") not in (None, ""):
            items.append(dict(row))
    return items


def _impl__order_purchase_id(item: Dict[str, Any]) -> Any:
    return item.get("order_purchase_id") or item.get("id") or item.get("purchase_id")


def _impl__item_up_num(item: Dict[str, Any]) -> str:
    for key in ["maxUpNum", "max_up_num", "this_arrival_num", "arrival_num"]:
        number = _positive_decimal(item.get(key))
        if number is not None:
            return _decimal_text(number)
    possible = _positive_decimal(item.get("possible_num")) or Decimal("0")
    storage = _positive_decimal(item.get("storage_num")) or Decimal("0")
    remain = possible - storage
    if remain > 0:
        return _decimal_text(remain)
    for key in ["confirm_num", "num", "purchase_num"]:
        number = _positive_decimal(item.get(key))
        if number is not None:
            return _decimal_text(number)
    return "1"


def _impl__items_already_checking(items: list[Dict[str, Any]]) -> bool:
    if not items:
        return False
    statuses = []
    for item in items:
        try:
            statuses.append(int(item.get("status") or 0))
        except (TypeError, ValueError):
            statuses.append(0)
    return bool(statuses) and all(status >= 40 for status in statuses)


def _impl__first_preview_user_id(rows: list[Dict[str, Any]], items: list[Dict[str, Any]]) -> str:
    for row in rows:
        user = row.get("user")
        if isinstance(user, dict) and user.get("id") not in (None, ""):
            return str(user.get("id"))
    for item in items:
        if item.get("_preview_user_id") not in (None, ""):
            return str(item.get("_preview_user_id"))
    return ""


def _impl__unique_values(values: list[Any]) -> list[Any]:
    seen = set()
    result = []
    for value in values:
        if value in (None, ""):
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _impl__purchase_status_code(item: Dict[str, Any]) -> int | None:
    for key in ["status", "_order_status"]:
        value = item.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _impl__purchase_still_pending(item: Dict[str, Any]) -> bool:
    status_code = _purchase_status_code(item)
    if status_code in {0, 1, 2, 3}:
        return True
    status_name = _purchase_status_name(item)
    pending_names = [
        "\u5f85\u62cd\u4e0b",
        "\u5f85\u6539\u4ef7",
        "\u5f85\u8d22\u52a1\u4ed8\u6b3e",
        "\u5f85\u4ed8\u6b3e",
        "\u5f85\u6838\u67e5",
    ]
    return any(name in status_name for name in pending_names)


def _impl__verify_purchase_to_shelf_completed(
    session: requests.Session,
    base_url: str,
    variables: Dict[str, Any],
    order_sn: str,
    purchase_ids: list[Any],
    timeout: int,
    log: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    retries = _as_int(variables.get("purchase_verify_retries"), 4)
    delay = _as_float(variables.get("purchase_verify_delay"), 1.0)
    selected_id_set = {str(item_id) for item_id in purchase_ids}
    attempts = []
    last_payload: Dict[str, Any] = {}
    last_selected: list[Dict[str, Any]] = []
    last_pending: list[Dict[str, Any]] = []

    for attempt in range(retries):
        fields = _purchase_list_fields(variables, order_sn)
        fields["status"] = str(variables.get("purchase_verify_status") or "\u5168\u90e8")
        fields["pageSize"] = max(_as_int(fields.get("pageSize"), 20), len(selected_id_set) or 20)
        payload = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_purchase_list", "/purchase.purchaseList"),
            fields,
            timeout,
        )
        items = _flatten_purchase_items(_admin_rows_from_payload(payload))
        selected_items = [
            item
            for item in items
            if not selected_id_set or str(_purchase_item_id(item) or "") in selected_id_set
        ]
        pending_items = [item for item in selected_items if _purchase_still_pending(item)]
        attempts.append(
            {
                **_payload_brief(payload),
                "attempt": attempt + 1,
                "item_count": len(items),
                "selected_count": len(selected_items),
                "pending_count": len(pending_items),
                "request": dict(fields),
                "selected_items": [_purchase_item_brief(item) for item in selected_items[:20]],
            }
        )
        last_payload = payload
        last_selected = selected_items
        last_pending = pending_items
        if _api_success(payload) and not pending_items:
            log["post_storage_verify_attempts"] = attempts
            return True, {
                "verify_passed": True,
                "remaining_purchase_count": len(selected_items),
                "remaining_pending_count": 0,
            }
        if attempt < retries - 1:
            time.sleep(delay)

    log["post_storage_verify_attempts"] = attempts
    if not _api_success(last_payload):
        return False, {
            "verify_passed": False,
            "remaining_purchase_count": len(last_selected),
            "remaining_pending_count": len(last_pending),
            "reason": "\u4e0a\u67b6\u540e\u56de\u67e5\u91c7\u8d2d\u5217\u8868\u5931\u8d25",
        }
    return False, {
        "verify_passed": False,
        "remaining_purchase_count": len(last_selected),
        "remaining_pending_count": len(last_pending),
        "remaining_pending_items": [_purchase_item_brief(item) for item in last_pending[:20]],
        "reason": "\u4e0a\u67b6\u540e\u91c7\u8d2d\u72b6\u6001\u4ecd\u672a\u6d41\u8f6c",
    }


def _impl__walk_grid_candidates(value: Any, result: list[Dict[str, Any]]) -> None:
    if isinstance(value, dict):
        if value.get("id") not in (None, "") and value.get("grid_number") not in (None, ""):
            result.append(value)
        for key in ["wms_grid", "grids", "children", "list", "data", "items"]:
            nested = value.get(key)
            if isinstance(nested, (list, dict)):
                _walk_grid_candidates(nested, result)
    elif isinstance(value, list):
        for item in value:
            _walk_grid_candidates(item, result)


def _impl__grid_candidates(warehouse_data: Any, warehouse_index: str) -> list[Dict[str, Any]]:
    selected = warehouse_data
    if isinstance(warehouse_data, dict):
        selected = warehouse_data.get(str(warehouse_index))
        if selected is None:
            selected = warehouse_data.get(warehouse_index)
        if selected is None:
            selected = next((value for value in warehouse_data.values() if isinstance(value, list)), warehouse_data)
    result: list[Dict[str, Any]] = []
    _walk_grid_candidates(selected, result)
    return result


def _impl__select_grid_from_payload(payload: Dict[str, Any], variables: Dict[str, Any]) -> Dict[str, Any] | None:
    configured_grid_id = str(variables.get("grid_id") or "").strip()
    warehouse_data = payload.get("data")
    grids = _grid_candidates(warehouse_data, str(variables.get("warehouse_index") or "2"))
    if configured_grid_id:
        for grid in grids:
            if str(grid.get("id") or "") == configured_grid_id:
                return grid
    prefer_empty = _as_bool(variables.get("prefer_empty_grid"), True)
    if prefer_empty:
        for grid in grids:
            if not grid.get("wms_stock"):
                return grid
    return grids[0] if grids else None


def _impl__step(log: Dict[str, Any], name: str, payload: Dict[str, Any], request: Dict[str, Any] | None = None, extra: Dict[str, Any] | None = None) -> None:
    item = {"name": name, **_payload_brief(payload)}
    if request is not None:
        item["request"] = dict(request)
    if extra:
        item.update(extra)
    log.setdefault("steps", []).append(item)


_purchase_timestamp_no = _compat_wrapper(_impl__purchase_timestamp_no)
_purchase_list_fields = _compat_wrapper(_impl__purchase_list_fields)
_flatten_purchase_items = _compat_wrapper(_impl__flatten_purchase_items)
_purchase_item_id = _compat_wrapper(_impl__purchase_item_id)
_select_purchase_items = _compat_wrapper(_impl__select_purchase_items)
_positive_text = _compat_wrapper(_impl__positive_text)
_purchase_item_values = _compat_wrapper(_impl__purchase_item_values)
_purchase_status_name = _compat_wrapper(_impl__purchase_status_name)
_purchase_save_rows = _compat_wrapper(_impl__purchase_save_rows)
_purchase_wait_pay_rows = _compat_wrapper(_impl__purchase_wait_pay_rows)
_purchase_item_brief = _compat_wrapper(_impl__purchase_item_brief)
_purchase_order_detail_id = _compat_wrapper(_impl__purchase_order_detail_id)
_purchase_wait_pay_fields = _compat_wrapper(_impl__purchase_wait_pay_fields)
_select_purchase_wait_pay = _compat_wrapper(_impl__select_purchase_wait_pay)
_finance_purchase_brief = _compat_wrapper(_impl__finance_purchase_brief)
_follow_list_fields = _compat_wrapper(_impl__follow_list_fields)
_flatten_follow_items = _compat_wrapper(_impl__flatten_follow_items)
_preview_rows_from_payload = _compat_wrapper(_impl__preview_rows_from_payload)
_preview_items = _compat_wrapper(_impl__preview_items)
_order_purchase_id = _compat_wrapper(_impl__order_purchase_id)
_item_up_num = _compat_wrapper(_impl__item_up_num)
_items_already_checking = _compat_wrapper(_impl__items_already_checking)
_first_preview_user_id = _compat_wrapper(_impl__first_preview_user_id)
_unique_values = _compat_wrapper(_impl__unique_values)
_purchase_status_code = _compat_wrapper(_impl__purchase_status_code)
_purchase_still_pending = _compat_wrapper(_impl__purchase_still_pending)
_verify_purchase_to_shelf_completed = _compat_wrapper(_impl__verify_purchase_to_shelf_completed)
_walk_grid_candidates = _compat_wrapper(_impl__walk_grid_candidates)
_grid_candidates = _compat_wrapper(_impl__grid_candidates)
_select_grid_from_payload = _compat_wrapper(_impl__select_grid_from_payload)
_step = _compat_wrapper(_impl__step)
