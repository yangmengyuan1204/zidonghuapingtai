from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    'Decimal',
    'InvalidOperation',
    'OrderedDict',
    'PORDER_AMOUNT_KEYS',
    '_api_path',
    '_api_paths',
    '_api_success',
    '_apply_extra_fields',
    '_as_bool',
    '_as_int',
    '_bank_pay_reach_date',
    '_call_with_retry',
    '_client_login_inputs',
    '_configure_client_api_paths',
    '_decimal_text',
    '_extract_porder_sn',
    '_first_positive_decimal',
    '_first_recursive_positive_decimal',
    '_full_flow_part_pay_script_enabled',
    '_load_payment_order',
    '_login_client_for_payment',
    '_nested_rows',
    '_order_part_pay_enabled',
    '_order_part_pay_tail_node',
    '_order_payment_amount',
    '_order_rows_from_payload',
    '_order_tail_apply_payment_detail_fields',
    '_order_tail_bank_pay_amount',
    '_order_tail_detail_fields',
    '_order_tail_detail_id',
    '_order_tail_detail_is_paid',
    '_order_tail_detail_is_unpaid',
    '_order_tail_detail_sorting',
    '_order_tail_detail_status',
    '_order_tail_order_detail_rows',
    '_order_tail_partial_enabled',
    '_order_tail_partial_select_by',
    '_order_tail_partial_selected_values',
    '_order_tail_pay_amount_from_pay_data',
    '_order_tail_pay_amount_from_variables',
    '_order_tail_pay_data_brief',
    '_order_tail_pay_data_fields',
    '_order_tail_pay_data_unpayable_ids',
    '_order_tail_payment_mode',
    '_order_tail_payment_order_sn',
    '_order_tail_payment_path',
    '_order_tail_unpaid_ids_from_detail',
    '_order_tail_value_list',
    '_payload_brief',
    '_payment_order_list_fields',
    '_porder_payload_matches',
    '_porder_payment_amount_from_payload',
    '_positive_decimal',
    '_public_order_tail_context',
    '_resolve_order_tail_partial_context',
    '_row_contains_text',
    '_runtime_from_variables',
    '_select_payment_order',
    '_unique_list',
    'bulk_cart',
    'datetime',
    're',
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


def _impl__positive_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number > 0 else None


def _impl__first_positive_decimal(source: Dict[str, Any], keys: list[str]) -> Decimal | None:
    for key in keys:
        number = _positive_decimal(source.get(key))
        if number is not None:
            return number
    return None


def _impl__order_rows_from_payload(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("data") or data.get("list") or data.get("rows") or data.get("order") or data.get("orders") or []
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def _impl__order_payment_amount(order: Dict[str, Any]) -> str:
    direct_amount = _first_positive_decimal(
        order,
        [
            "order_amount",
            "total_amount",
            "need_pay_amount",
            "wait_pay_amount",
            "payment_amount",
            "amount",
            "total_price",
            "order_price",
            "pay_amount",
        ],
    )
    if direct_amount is not None:
        return _decimal_text(direct_amount)

    total = Decimal("0")
    details = order.get("order_detail")
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        num = _positive_decimal(detail.get("num")) or Decimal("0")
        price = _first_positive_decimal(detail, ["offer_price", "confirm_price", "price", "userTotal"]) or Decimal("0")
        freight = _first_positive_decimal(detail, ["offer_freight", "confirm_freight", "freight"]) or Decimal("0")
        total += num * price + freight
        options = detail.get("option")
        for option in options if isinstance(options, list) else []:
            if not isinstance(option, dict) or option.get("checked") is False:
                continue
            option_price = _positive_decimal(option.get("price")) or Decimal("0")
            option_num = _positive_decimal(option.get("num")) or num or Decimal("1")
            total += option_price * option_num
    return _decimal_text(total)


def _impl__payment_order_list_fields(variables: Dict[str, Any]) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["status_name"] = str(variables.get("order_status_name") or variables.get("payment_status_name") or "\u7b49\u5f85\u4ed8\u6b3e")
    fields["page"] = _as_int(variables.get("page"), 1)
    fields["pageSize"] = _as_int(variables.get("page_size") or variables.get("pageSize"), 10)
    fields["order_by"] = str(variables.get("order_by") or "desc")
    order_sn = str(variables.get("order_sn") or "").strip()
    if order_sn:
        fields["keywords"] = order_sn
    for key in [
        "keywords",
        "goods_title_search",
        "goods_title_search_language",
        "start_time",
        "end_time",
        "for_sn",
        "created_by_type",
        "children_user_id",
        "follow_remark",
        "part_pay_status",
    ]:
        value = variables.get(key)
        if value not in (None, "") and key not in fields:
            fields[key] = value
    return fields


def _impl__select_payment_order(orders: list[Dict[str, Any]], variables: Dict[str, Any], status_name: str) -> Dict[str, Any] | None:
    requested_sn = str(variables.get("order_sn") or "").strip()
    if requested_sn:
        for order in orders:
            if str(order.get("order_sn") or "") == requested_sn:
                return order
    for order in orders:
        if str(order.get("status_name") or "") == status_name or str(order.get("status") or "") == "30":
            return order
    return orders[0] if orders else None


def _impl__login_client_for_payment(env: Env, variables: Dict[str, Any], log: Dict[str, Any]) -> tuple[Any, str, int, str]:
    runtime = _runtime_from_variables(variables)
    if runtime:
        client, base_url, timeout, token, _cached = runtime.client(env, variables, log=log)
        return client, base_url, timeout, token
    account, password, client_tool = _client_login_inputs(variables)
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
    client = bulk_cart.RakumartClient(base_url, timeout)
    _configure_client_api_paths(client, variables)
    token = _call_with_retry("client login", lambda: client.login(account, password, client_tool))
    log["login"] = {"success": True, "account": account, "client_tool": client_tool, "token_extracted": bool(token)}
    return client, base_url, timeout, str(token)


def _impl__load_payment_order(client: Any, variables: Dict[str, Any], log: Dict[str, Any]) -> tuple[Dict[str, Any] | None, str, str]:
    fields = _payment_order_list_fields(variables)
    payload = _call_with_retry(
        "order list",
        lambda: client.post_form(_api_path(variables, "client_order_list", "/client/order.orderList"), fields),
    )
    rows = _order_rows_from_payload(payload)
    status_name = str(fields.get("status_name") or "\u7b49\u5f85\u4ed8\u6b3e")
    order = _select_payment_order(rows, variables, status_name)
    order_sn = str((order or {}).get("order_sn") or "")
    amount = str(variables.get("pay_amount") or "").strip() or (_order_payment_amount(order) if order else "0")
    log["order_list"] = {
        **_payload_brief(payload),
        "request": dict(fields),
        "count": len(rows),
        "selected_order_sn": order_sn,
        "selected_status_name": (order or {}).get("status_name"),
        "selected_amount": amount,
    }
    return order, order_sn, amount


def _impl__common_payment_summary(
    payment_type: str,
    order_sn: str,
    amount: str,
    payment_payload: Dict[str, Any],
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    summary = {
        "payment_type": payment_type,
        "order_sn": order_sn,
        "pay_amount": amount,
        "payment_passed": _api_success(payment_payload),
    }
    data = payment_payload.get("data") if isinstance(payment_payload.get("data"), dict) else {}
    if data.get("serial_number"):
        summary["serial_number"] = str(data.get("serial_number"))
    if data.get("order_sn") and not summary["order_sn"]:
        summary["order_sn"] = str(data.get("order_sn"))
    if extra:
        summary.update(extra)
    if not summary["payment_passed"] and "reason" not in summary:
        summary["reason"] = str(payment_payload.get("msg") or payment_payload.get("data") or "\u652f\u4ed8\u63a5\u53e3\u6267\u884c\u5931\u8d25")
    return summary


def _impl__first_recursive_positive_decimal(value: Any, keys: list[str]) -> Decimal | None:
    if isinstance(value, dict):
        direct = _first_positive_decimal(value, keys)
        if direct is not None:
            return direct
        for child in value.values():
            found = _first_recursive_positive_decimal(child, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _first_recursive_positive_decimal(child, keys)
            if found is not None:
                return found
    return None


def _impl__porder_payload_matches(payload: Dict[str, Any], porder_sn: str) -> bool:
    if not porder_sn:
        return False
    found = _extract_porder_sn(payload, "")
    return not found or found == porder_sn or _row_contains_text(payload, porder_sn)


def _impl__porder_payment_summary(
    payment_type: str,
    porder_sn: str,
    amount: str,
    payment_payload: Dict[str, Any],
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    data = payment_payload.get("data") if isinstance(payment_payload.get("data"), dict) else {}
    summary = {
        "payment_type": payment_type,
        "porder_sn": porder_sn,
        "pay_amount": amount,
        "payment_passed": _api_success(payment_payload),
        "porder_matched": _porder_payload_matches(payment_payload, porder_sn),
    }
    if data.get("order_sn"):
        summary["order_sn"] = str(data.get("order_sn"))
    if data.get("serial_number"):
        summary["serial_number"] = str(data.get("serial_number"))
    if extra:
        summary.update(extra)
    if not summary["payment_passed"] and "reason" not in summary:
        summary["reason"] = str(payment_payload.get("msg") or payment_payload.get("data") or "配送单支付接口执行失败")
    if summary["payment_passed"] and not summary["porder_matched"] and "reason" not in summary:
        summary["reason"] = "配送单支付接口返回单号与输入配送单号不一致"
    return summary


def _impl__porder_payment_amount_from_payload(payload: Dict[str, Any]) -> str:
    number = _first_recursive_positive_decimal(payload, PORDER_AMOUNT_KEYS)
    return _decimal_text(number) if number is not None else "0"


def _impl__load_porder_payment_amount(client: Any, variables: Dict[str, Any], log: Dict[str, Any], porder_sn: str) -> str:
    configured = str(variables.get("pay_amount") or "").strip()
    if _positive_decimal(configured):
        log["porder_amount"] = {"source": "variables", "pay_amount": configured}
        return _decimal_text(configured)

    paths = []
    for key in ["client_porder_pay_detail", "client_porder_detail", "client_porder_list"]:
        path = _api_paths(variables).get(key)
        if path:
            paths.append(str(path))
    paths.extend(
        [
            "/client/porder.porderPayDetail",
            "/client/porder.payDetail",
            "/client/porder.paymentDetail",
            "/client/porder.porderDetail",
            "/client/porder.detail",
            "/client/porder.porderList",
        ]
    )
    attempts = []
    for path in dict.fromkeys(paths):
        fields = OrderedDict([("porder_sn", porder_sn)])
        if path.endswith("porderList"):
            fields["keywords"] = porder_sn
            fields["page"] = 1
            fields["pageSize"] = 10
        try:
            payload = _call_with_retry("porder payment amount", lambda path=path, fields=fields: client.post_form(path, fields))
            amount = _porder_payment_amount_from_payload(payload)
            attempts.append({**_payload_brief(payload), "path": path, "request": dict(fields), "pay_amount": amount})
            if _api_success(payload) and _positive_decimal(amount):
                log["porder_amount"] = {"attempts": attempts, "pay_amount": amount}
                return amount
        except Exception as exc:
            attempts.append({"path": path, "request": dict(fields), "error": str(exc)})
    log["porder_amount"] = {"attempts": attempts, "pay_amount": "0"}
    return "0"


def _impl__apply_extra_fields(fields: OrderedDict[str, Any], extra_fields: Any) -> OrderedDict[str, Any]:
    if isinstance(extra_fields, dict):
        for key, value in extra_fields.items():
            if key and value is not None:
                fields[str(key)] = value
    return fields


def _impl__order_tail_payment_order_sn(variables: Dict[str, Any]) -> str:
    for key in ["order_sn", "last_order_sn", "warehouse_order_sn"]:
        value = str(variables.get(key) or "").strip()
        if value:
            return value
    return ""


def _impl__order_tail_payment_mode(variables: Dict[str, Any]) -> str:
    mode = str(
        variables.get("order_tail_payment_mode")
        or variables.get("order_payment_mode")
        or variables.get("payment_mode")
        or "balance"
    ).strip().lower()
    return "bank" if mode in {"bank", "bank_payment"} else "balance"


def _impl__order_tail_payment_path(variables: Dict[str, Any], payment_mode: str) -> str:
    api_paths = _api_paths(variables)
    mode_key = "client_order_tail_bank_pay" if payment_mode == "bank" else "client_order_tail_balance_pay"
    configured = str(
        api_paths.get(mode_key)
        or variables.get(f"{mode_key}_path")
        or api_paths.get("client_order_tail_pay")
        or variables.get("client_order_tail_pay_path")
        or variables.get("order_tail_pay_path")
        or ""
    ).strip()
    if configured:
        return configured
    if payment_mode == "bank":
        return _api_path(variables, "client_bank_pay", "/client/order.bankPayOrder")
    return _api_path(variables, "client_balance_pay", "/client/order.balancePayOrder")


def _impl__order_tail_pay_amount_from_variables(variables: Dict[str, Any]) -> str:
    for key in ["order_tail_pay_amount", "tail_pay_amount", "pay_amount"]:
        value = str(variables.get(key) or "").strip()
        if value:
            return value
    return ""


def _impl__order_tail_value_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        values: list[str] = []
        for item in value:
            values.extend(_order_tail_value_list(item))
        return _unique_list(values)
    text = str(value or "").strip()
    if not text:
        return []
    return _unique_list([item.strip() for item in re.split(r"[\s,，;；]+", text) if item.strip()])


def _impl__order_tail_partial_enabled(variables: Dict[str, Any]) -> bool:
    return _as_bool(variables.get("order_part_pay_tail_partial_enabled"), False)


def _impl__order_tail_partial_select_by(variables: Dict[str, Any]) -> str:
    value = str(variables.get("order_part_pay_tail_select_by") or "").strip()
    return "detail_id" if value in {"detail_id", "order_detail_id", "id"} else "sorting"


def _impl__order_tail_partial_selected_values(variables: Dict[str, Any]) -> tuple[str, list[str]]:
    select_by = _order_tail_partial_select_by(variables)
    primary_key = "order_part_pay_tail_detail_ids" if select_by == "detail_id" else "order_part_pay_tail_sortings"
    fallback_key = "order_part_pay_tail_sortings" if select_by == "detail_id" else "order_part_pay_tail_detail_ids"
    values = _order_tail_value_list(variables.get(primary_key))
    if values:
        return select_by, values
    fallback_values = _order_tail_value_list(variables.get(fallback_key))
    if fallback_values:
        return ("sorting" if select_by == "detail_id" else "detail_id"), fallback_values
    return select_by, []


def _impl__order_tail_detail_id(row: Dict[str, Any]) -> str:
    for key in ["order_detail_id", "orderDetailId", "detail_id", "id"]:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _impl__order_tail_detail_sorting(row: Dict[str, Any]) -> str:
    for key in ["sorting", "sort", "index", "no"]:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _impl__order_tail_detail_status(row: Dict[str, Any]) -> str:
    value = row.get("tail_pay_status")
    if value not in (None, ""):
        return str(value).strip()
    return ""


def _impl__order_tail_detail_is_paid(row: Dict[str, Any]) -> bool:
    status = _order_tail_detail_status(row).lower()
    name = str(row.get("tail_pay_status_name") or "").strip()
    return status in {"1", "true", "paid"} or "已支付" in name


def _impl__order_tail_detail_is_unpaid(row: Dict[str, Any]) -> bool:
    status = _order_tail_detail_status(row).lower()
    name = str(row.get("tail_pay_status_name") or "").strip()
    return status in {"0", "false", "unpaid"} or "待支付" in name


def _impl__order_tail_order_detail_rows(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    groups = data.get("order_detail")
    rows: list[Dict[str, Any]] = []
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, dict):
                continue
            goods = group.get("goods")
            if isinstance(goods, list):
                rows.extend([dict(item) for item in goods if isinstance(item, dict)])
            elif _order_tail_detail_id(group):
                rows.append(dict(group))
    if not rows:
        rows = _nested_rows(groups)
    result: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        detail_id = _order_tail_detail_id(row)
        if not detail_id or detail_id in seen:
            continue
        seen.add(detail_id)
        result.append(row)
    return result


def _impl__order_tail_unpaid_ids_from_detail(payload: Dict[str, Any], rows: list[Dict[str, Any]]) -> list[str]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    summary = data.get("part_pay_tail_summary") if isinstance(data.get("part_pay_tail_summary"), dict) else {}
    ids = _order_tail_value_list(summary.get("unpaid_tail_detail_ids"))
    if ids:
        return ids
    return _unique_list([_order_tail_detail_id(row) for row in rows if _order_tail_detail_is_unpaid(row)])


def _impl__order_tail_detail_fields(order_sn: str, variables: Dict[str, Any]) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["order_sn"] = order_sn
    return fields


def _impl__order_tail_pay_data_fields(order_sn: str, variables: Dict[str, Any], detail_ids: list[str]) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["order_sn"] = order_sn
    for index, detail_id in enumerate(detail_ids):
        fields[f"order_detail_ids[{index}]"] = detail_id
    if detail_ids:
        fields["pay_mode"] = "partial"
    fields["discounts_id"] = str(variables.get("discounts_id") or "")
    return fields


def _impl__order_tail_apply_payment_detail_fields(fields: OrderedDict[str, Any], detail_ids: list[str]) -> None:
    for index, detail_id in enumerate(detail_ids):
        fields[f"order_detail_ids[{index}]"] = detail_id
    if detail_ids:
        fields["pay_mode"] = "partial"


def _impl__order_tail_pay_data_brief(payload: Dict[str, Any], fields: OrderedDict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    part_pay_amount = data.get("part_pay_amount") if isinstance(data.get("part_pay_amount"), dict) else {}
    rmb = part_pay_amount.get("RMB") if isinstance(part_pay_amount.get("RMB"), dict) else {}
    jpy = part_pay_amount.get("JPY") if isinstance(part_pay_amount.get("JPY"), dict) else {}
    tail_rows = data.get("tail_detail_list") if isinstance(data.get("tail_detail_list"), list) else []
    return {
        **_payload_brief(payload),
        "request": dict(fields),
        "pay_mode": rmb.get("pay_mode") or jpy.get("pay_mode") or fields.get("pay_mode") or "full_remaining",
        "rmb_total_amount": rmb.get("total_amount"),
        "jpy_total_amount": jpy.get("total_amount"),
        "pay_amount_jpy": jpy.get("pay_amount_jpy") or data.get("pay_amount_jpy"),
        "tail_detail_ids": _order_tail_value_list(jpy.get("tail_detail_ids") or rmb.get("tail_detail_ids")),
        "tail_detail_count": len(tail_rows),
    }


def _impl__order_tail_pay_amount_from_pay_data(payload: Dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    part_pay_amount = data.get("part_pay_amount") if isinstance(data.get("part_pay_amount"), dict) else {}
    jpy = part_pay_amount.get("JPY") if isinstance(part_pay_amount.get("JPY"), dict) else {}
    for value in [jpy.get("pay_amount_jpy"), jpy.get("total_amount"), data.get("pay_amount_jpy"), data.get("pay_amount")]:
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _impl__order_tail_pay_data_unpayable_ids(payload: Dict[str, Any]) -> list[str]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    rows = data.get("tail_detail_list") if isinstance(data.get("tail_detail_list"), list) else []
    return _unique_list(
        [
            _order_tail_detail_id(row)
            for row in rows
            if isinstance(row, dict) and row.get("can_pay_tail") is False
        ]
    )


def _impl__resolve_order_tail_partial_context(
    client: Any,
    variables: Dict[str, Any],
    order_sn: str,
    payment_log: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    context: Dict[str, Any] = {"partial_enabled": False}
    if not _order_tail_partial_enabled(variables):
        return True, context

    select_by, selected_values = _order_tail_partial_selected_values(variables)
    context.update({"partial_enabled": True, "select_by": select_by, "selected_values": selected_values})
    if not selected_values:
        context["reason"] = "按番尾款已启用，但未填写番序号"
        return False, context

    detail_fields = _order_tail_detail_fields(order_sn, variables)
    detail_payload = _call_with_retry(
        "order tail detail",
        lambda: client.post_form(_api_path(variables, "client_order_detail", "/client/order.orderDetail"), detail_fields),
    )
    rows = _order_tail_order_detail_rows(detail_payload)
    payment_log["order_tail_detail"] = {**_payload_brief(detail_payload), "request": dict(detail_fields), "detail_count": len(rows)}
    context["detail_count"] = len(rows)
    if not _api_success(detail_payload) or not rows:
        context["reason"] = str(detail_payload.get("msg") or "未获取到订单商品明细，无法执行按番尾款")
        return False, context

    by_id = {_order_tail_detail_id(row): row for row in rows if _order_tail_detail_id(row)}
    by_sorting = {_order_tail_detail_sorting(row): row for row in rows if _order_tail_detail_sorting(row)}
    selected_ids: list[str] = []
    missing_values: list[str] = []
    for value in selected_values:
        row = by_id.get(value) if select_by == "detail_id" else by_sorting.get(value)
        detail_id = _order_tail_detail_id(row or {})
        if detail_id:
            selected_ids.append(detail_id)
        else:
            missing_values.append(value)
    selected_ids = _unique_list(selected_ids)
    context["selected_order_detail_ids"] = selected_ids
    if missing_values:
        context["missing_values"] = missing_values
        context["reason"] = "所选明细 ID 不存在或未匹配到订单明细" if select_by == "detail_id" else "所选番序号不存在或未匹配到订单明细"
        return False, context

    unpaid_ids = _order_tail_unpaid_ids_from_detail(detail_payload, rows)
    unpaid_set = set(unpaid_ids)
    already_paid_ids: list[str] = []
    unpaid_selected_ids: list[str] = []
    invalid_status_ids: list[str] = []
    for detail_id in selected_ids:
        row = by_id.get(detail_id) or {}
        if _order_tail_detail_is_paid(row):
            already_paid_ids.append(detail_id)
        elif _order_tail_detail_is_unpaid(row) or detail_id in unpaid_set:
            unpaid_selected_ids.append(detail_id)
        else:
            invalid_status_ids.append(detail_id)
    context.update(
        {
            "unpaid_tail_detail_ids": unpaid_ids,
            "already_paid_order_detail_ids": already_paid_ids,
            "unpaid_selected_order_detail_ids": unpaid_selected_ids,
            "downstream_order_detail_ids": selected_ids,
        }
    )
    if invalid_status_ids:
        context["invalid_status_order_detail_ids"] = invalid_status_ids
        context["reason"] = "所选番尾款状态异常，不能自动支付"
        return False, context

    if not unpaid_selected_ids:
        context.update({"payment_scope": "already_paid", "payment_skipped": True, "payment_detail_ids": []})
        return True, context

    payment_detail_ids = [] if unpaid_ids and set(unpaid_selected_ids) == set(unpaid_ids) else unpaid_selected_ids
    context["payment_scope"] = "full_remaining" if not payment_detail_ids else "partial"
    context["payment_detail_ids"] = payment_detail_ids
    pay_data_fields = _order_tail_pay_data_fields(order_sn, variables, payment_detail_ids)
    pay_data_payload = _call_with_retry(
        "order tail pay data",
        lambda: client.post_form(_api_path(variables, "client_order_pay_data", "/client/order.payData"), pay_data_fields),
    )
    pay_data_summary = _order_tail_pay_data_brief(pay_data_payload, pay_data_fields)
    payment_log["order_tail_pay_data"] = pay_data_summary
    context["pay_data"] = pay_data_summary
    if not _api_success(pay_data_payload):
        context["reason"] = str(pay_data_payload.get("msg") or "尾款金额查询失败")
        return False, context
    returned_tail_ids = set(_order_tail_value_list(pay_data_summary.get("tail_detail_ids")))
    if payment_detail_ids and not set(payment_detail_ids).issubset(returned_tail_ids):
        context["missing_pay_data_order_detail_ids"] = [detail_id for detail_id in payment_detail_ids if detail_id not in returned_tail_ids]
        context["reason"] = "尾款金额查询未返回所选番，不能自动支付"
        return False, context
    unpayable_ids = _order_tail_pay_data_unpayable_ids(pay_data_payload)
    if unpayable_ids:
        context["unpayable_order_detail_ids"] = unpayable_ids
        context["reason"] = "所选番当前不可支付尾款"
        return False, context
    context["_pay_data_payload"] = pay_data_payload
    return True, context


def _impl__public_order_tail_context(context: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in context.items() if not str(key).startswith("_")}


def _impl__order_tail_bank_pay_amount(
    client: Any,
    variables: Dict[str, Any],
    order_sn: str,
    payment_log: Dict[str, Any],
) -> tuple[str, Dict[str, Any]]:
    configured = _order_tail_pay_amount_from_variables(variables)
    if configured:
        return configured, {"source": "variables"}
    lookup_variables = dict(variables)
    lookup_variables["order_sn"] = order_sn
    order, selected_order_sn, amount = _load_payment_order(client, lookup_variables, payment_log)
    return amount, {
        "source": "order_list",
        "found": bool(order),
        "selected_order_sn": selected_order_sn,
    }


def _impl__run_order_tail_payment_if_needed(
    env: Env,
    variables: Dict[str, Any],
    log: Dict[str, Any],
    node: str,
) -> tuple[bool, Dict[str, Any]]:
    if not _full_flow_part_pay_script_enabled(variables):
        return True, {"skipped": True, "reason": "分批付款尾款仅全流程加入分批付款脚本启用", "node": node}
    if not _order_part_pay_enabled(variables):
        return True, {"skipped": True, "reason": "未启用分批付款", "node": node}
    configured_node = _order_part_pay_tail_node(variables)
    if configured_node != node:
        return True, {"skipped": True, "reason": "未到尾款支付节点", "node": node, "configured_node": configured_node}

    order_sn = _order_tail_payment_order_sn(variables)
    summary: Dict[str, Any] = {
        "node": node,
        "configured_node": configured_node,
        "order_sn": order_sn,
        "payment_stage": "tail",
    }
    payment_mode = _order_tail_payment_mode(variables)
    path = _order_tail_payment_path(variables, payment_mode)
    if not path:
        reason = "银行尾款支付接口未配置，等待后续接入" if payment_mode == "bank" else "尾款支付接口未配置，等待后续接入"
        summary.update(
            {
                "interface_configured": False,
                "payment_mode": payment_mode,
                "reason": reason,
            }
        )
        log.setdefault("order_tail_payments", []).append(summary)
        return False, summary
    if not order_sn:
        summary["reason"] = "执行尾款支付缺少订单号"
        log.setdefault("order_tail_payments", []).append(summary)
        return False, summary

    payment_log: Dict[str, Any] = {}
    try:
        client, base_url, _, _ = _login_client_for_payment(env, variables, payment_log)
        partial_passed, partial_context = _resolve_order_tail_partial_context(client, variables, order_sn, payment_log)
        summary.update(_public_order_tail_context(partial_context))
        if not partial_passed:
            log.setdefault("order_tail_payments", []).append(summary)
            return False, summary

        downstream_ids = _unique_list(partial_context.get("downstream_order_detail_ids") or [])
        if downstream_ids:
            variables["order_detail_ids"] = downstream_ids
            variables["order_detail_id"] = downstream_ids[0]
            summary["order_detail_ids"] = downstream_ids
            summary["order_detail_id"] = downstream_ids[0]

        if partial_context.get("payment_skipped"):
            summary.update(
                {
                    "base_url": base_url,
                    "path": path,
                    "payment_mode": payment_mode,
                    "payment_passed": True,
                    "payment_skipped": True,
                    "reason": "所选番尾款均已支付，跳过尾款支付接口",
                }
            )
            log.setdefault("order_tail_payments", []).append(summary)
            return True, summary

        payment_detail_ids = _unique_list(partial_context.get("payment_detail_ids") or [])
        pay_data_payload = partial_context.get("_pay_data_payload") if isinstance(partial_context.get("_pay_data_payload"), dict) else {}
        fields: OrderedDict[str, Any] = OrderedDict()
        if payment_mode == "bank":
            amount = _order_tail_pay_amount_from_pay_data(pay_data_payload) if pay_data_payload else ""
            if amount:
                amount_summary = {"source": "order_pay_data", "payment_scope": partial_context.get("payment_scope") or "full_remaining"}
            else:
                amount, amount_summary = _order_tail_bank_pay_amount(client, variables, order_sn, payment_log)
            summary["amount_lookup"] = amount_summary
            if not _positive_decimal(amount):
                summary.update({"reason": "未获取到尾款银行支付金额", "payment_mode": payment_mode, "pay_amount": amount})
                log.setdefault("order_tail_payments", []).append(summary)
                return False, summary
            fields["pay_bank_method"] = str(variables.get("order_tail_pay_bank_method") or variables.get("pay_bank_method") or "2")
            fields["pay_reach_date"] = _bank_pay_reach_date(variables, datetime.now())
            fields["pay_name"] = str(variables.get("pay_name") or "自动化测试")
            fields["pay_amount"] = amount
            fields["pay_remark"] = str(variables.get("order_tail_pay_remark") or variables.get("pay_remark") or "")
            fields["discounts_id"] = str(variables.get("discounts_id") or "")
            fields["order_sn"] = order_sn
            fields["merge_pay"] = str(variables.get("order_tail_merge_pay") or variables.get("merge_pay") or "0")
            fields["predict_logistics_price_is_pay"] = str(variables.get("predict_logistics_price_is_pay") or "0")
            _order_tail_apply_payment_detail_fields(fields, payment_detail_ids)
        else:
            fields["order_sn"] = order_sn
            fields["discounts_id"] = str(variables.get("discounts_id") or "")
            fields["merge_pay"] = str(variables.get("order_tail_merge_pay") or variables.get("merge_pay") or "0")
            _order_tail_apply_payment_detail_fields(fields, payment_detail_ids)
            if _as_bool(variables.get("include_order_tail_pay_amount") or variables.get("include_tail_pay_amount"), False):
                amount = str(variables.get("order_tail_pay_amount") or variables.get("tail_pay_amount") or "").strip()
                if amount:
                    fields["pay_amount"] = amount
        _apply_extra_fields(fields, variables.get("order_tail_pay_fields") or variables.get("tail_pay_fields"))
        payment_payload = _call_with_retry("order tail payment", lambda: client.post_form(path, fields))
        data = payment_payload.get("data") if isinstance(payment_payload.get("data"), dict) else {}
        passed = _api_success(payment_payload)
        summary.update(
            {
                "base_url": base_url,
                "path": path,
                "request": dict(fields),
                "payment_mode": payment_mode,
                "payment_passed": passed,
                **_payload_brief(payment_payload),
            }
        )
        if data.get("serial_number"):
            summary["serial_number"] = str(data.get("serial_number"))
        if not passed:
            summary["reason"] = str(payment_payload.get("msg") or payment_payload.get("data") or "尾款支付接口执行失败")
        log.setdefault("order_tail_payments", []).append(summary)
        return passed, summary
    except Exception as exc:
        summary["reason"] = str(exc)
        if payment_log:
            summary["payment_log"] = payment_log
        log.setdefault("order_tail_payments", []).append(summary)
        return False, summary


def _impl__bank_pay_reach_date(variables: Dict[str, Any], pay_date: datetime) -> str:
    configured = str(variables.get("pay_reach_date") or "").strip()
    if configured:
        return configured
    offset_days = _as_int(variables.get("pay_reach_after_days"), 0)
    return (pay_date + timedelta(days=max(0, offset_days))).strftime("%Y-%m-%d %H:%M:%S")


def _impl__finance_rows_from_payload(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("data") or data.get("list") or data.get("rows") or []
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def _impl__finance_bill_brief(row: Dict[str, Any] | None) -> Dict[str, Any]:
    if not row:
        return {}
    return {
        "id": row.get("id"),
        "serial_number": row.get("serial_number"),
        "order_sn": row.get("order_sn"),
        "porder_sn": row.get("porder_sn"),
        "p_order_sn": row.get("p_order_sn"),
        "pay_amount": row.get("pay_amount"),
        "amount": row.get("amount"),
        "bill_method": row.get("bill_method"),
        "predict_arrival_at": row.get("predict_arrival_at"),
        "created_at": row.get("created_at"),
        "status": row.get("status"),
    }


def _impl__row_contains_text(row: Dict[str, Any], needle: str) -> bool:
    return bool(needle) and needle in bulk_cart.json_text(row)


def _impl__select_finance_bill(rows: list[Dict[str, Any]], serial_number: str, order_sn: str) -> Dict[str, Any] | None:
    for row in rows:
        if serial_number and str(row.get("serial_number") or "") == serial_number:
            return row
    for row in rows:
        if order_sn and str(row.get("order_sn") or "") == order_sn:
            return row
        if order_sn and str(row.get("porder_sn") or row.get("p_order_sn") or row.get("pOrderSn") or "") == order_sn:
            return row
    for row in rows:
        if _row_contains_text(row, order_sn):
            return row
    return rows[0] if rows else None


def _impl__finance_unconfirm_fields(variables: Dict[str, Any], serial_number: str, order_sn: str) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["page"] = _as_int(variables.get("finance_page") or variables.get("page"), 1)
    fields["pageSize"] = _as_int(variables.get("finance_page_size") or variables.get("page_size") or variables.get("pageSize"), 20)
    if serial_number:
        fields["serial_number"] = serial_number
    if order_sn:
        fields["order_sn"] = order_sn
    for key in ["user_id", "pay_realname", "bill_method", "start_time", "end_time", "is_urgent"]:
        value = variables.get(key)
        if value not in (None, ""):
            fields[key] = value
    return fields


def _impl__admin_rows_from_payload(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("data") or data.get("list") or data.get("rows") or data.get("items") or data.get("order") or []
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def _impl__field_text(value: Any) -> str:
    return "" if value in (None, "") else str(value)


_positive_decimal = _compat_wrapper(_impl__positive_decimal)
_first_positive_decimal = _compat_wrapper(_impl__first_positive_decimal)
_order_rows_from_payload = _compat_wrapper(_impl__order_rows_from_payload)
_order_payment_amount = _compat_wrapper(_impl__order_payment_amount)
_payment_order_list_fields = _compat_wrapper(_impl__payment_order_list_fields)
_select_payment_order = _compat_wrapper(_impl__select_payment_order)
_login_client_for_payment = _compat_wrapper(_impl__login_client_for_payment)
_load_payment_order = _compat_wrapper(_impl__load_payment_order)
_common_payment_summary = _compat_wrapper(_impl__common_payment_summary)
_first_recursive_positive_decimal = _compat_wrapper(_impl__first_recursive_positive_decimal)
_porder_payload_matches = _compat_wrapper(_impl__porder_payload_matches)
_porder_payment_summary = _compat_wrapper(_impl__porder_payment_summary)
_porder_payment_amount_from_payload = _compat_wrapper(_impl__porder_payment_amount_from_payload)
_load_porder_payment_amount = _compat_wrapper(_impl__load_porder_payment_amount)
_apply_extra_fields = _compat_wrapper(_impl__apply_extra_fields)
_order_tail_payment_order_sn = _compat_wrapper(_impl__order_tail_payment_order_sn)
_order_tail_payment_mode = _compat_wrapper(_impl__order_tail_payment_mode)
_order_tail_payment_path = _compat_wrapper(_impl__order_tail_payment_path)
_order_tail_pay_amount_from_variables = _compat_wrapper(_impl__order_tail_pay_amount_from_variables)
_order_tail_value_list = _compat_wrapper(_impl__order_tail_value_list)
_order_tail_partial_enabled = _compat_wrapper(_impl__order_tail_partial_enabled)
_order_tail_partial_select_by = _compat_wrapper(_impl__order_tail_partial_select_by)
_order_tail_partial_selected_values = _compat_wrapper(_impl__order_tail_partial_selected_values)
_order_tail_detail_id = _compat_wrapper(_impl__order_tail_detail_id)
_order_tail_detail_sorting = _compat_wrapper(_impl__order_tail_detail_sorting)
_order_tail_detail_status = _compat_wrapper(_impl__order_tail_detail_status)
_order_tail_detail_is_paid = _compat_wrapper(_impl__order_tail_detail_is_paid)
_order_tail_detail_is_unpaid = _compat_wrapper(_impl__order_tail_detail_is_unpaid)
_order_tail_order_detail_rows = _compat_wrapper(_impl__order_tail_order_detail_rows)
_order_tail_unpaid_ids_from_detail = _compat_wrapper(_impl__order_tail_unpaid_ids_from_detail)
_order_tail_detail_fields = _compat_wrapper(_impl__order_tail_detail_fields)
_order_tail_pay_data_fields = _compat_wrapper(_impl__order_tail_pay_data_fields)
_order_tail_apply_payment_detail_fields = _compat_wrapper(_impl__order_tail_apply_payment_detail_fields)
_order_tail_pay_data_brief = _compat_wrapper(_impl__order_tail_pay_data_brief)
_order_tail_pay_amount_from_pay_data = _compat_wrapper(_impl__order_tail_pay_amount_from_pay_data)
_order_tail_pay_data_unpayable_ids = _compat_wrapper(_impl__order_tail_pay_data_unpayable_ids)
_resolve_order_tail_partial_context = _compat_wrapper(_impl__resolve_order_tail_partial_context)
_public_order_tail_context = _compat_wrapper(_impl__public_order_tail_context)
_order_tail_bank_pay_amount = _compat_wrapper(_impl__order_tail_bank_pay_amount)
_run_order_tail_payment_if_needed = _compat_wrapper(_impl__run_order_tail_payment_if_needed)
_bank_pay_reach_date = _compat_wrapper(_impl__bank_pay_reach_date)
_finance_rows_from_payload = _compat_wrapper(_impl__finance_rows_from_payload)
_finance_bill_brief = _compat_wrapper(_impl__finance_bill_brief)
_row_contains_text = _compat_wrapper(_impl__row_contains_text)
_select_finance_bill = _compat_wrapper(_impl__select_finance_bill)
_finance_unconfirm_fields = _compat_wrapper(_impl__finance_unconfirm_fields)
_admin_rows_from_payload = _compat_wrapper(_impl__admin_rows_from_payload)
_field_text = _compat_wrapper(_impl__field_text)
