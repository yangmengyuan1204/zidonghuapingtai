from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    'Decimal',
    'InvalidOperation',
    'ORDER_PART_PAY_FEE_KEYS',
    'ORDER_PART_PAY_TAIL_NODES',
    'OrderedDict',
    '_ORDER_MSG_TRANSLATIONS',
    '_admin_detail_brief',
    '_admin_headers',
    '_admin_login',
    '_admin_login_without_runtime',
    '_admin_rows_from_payload',
    '_admin_session_from',
    '_api_path',
    '_api_success',
    '_apply_order_part_pay_payload',
    '_as_bool',
    '_as_int',
    '_build_confirm_data',
    '_call_with_retry',
    '_checkpoint_requested',
    '_client_login_inputs',
    '_configure_client_api_paths',
    '_decimal_text',
    '_fetch_order_option_catalog',
    '_first_price',
    '_flatten_purchase_items',
    '_flatten_urlencoded_fields',
    '_full_flow_part_pay_script_enabled',
    '_money_total',
    '_order_detail_data',
    '_order_detail_ids',
    '_order_part_pay_api_fee_flag',
    '_order_part_pay_api_node',
    '_order_part_pay_enabled',
    '_order_part_pay_fee_timing',
    '_order_part_pay_first_goods_amount',
    '_order_part_pay_goods_total',
    '_order_part_pay_percent',
    '_order_part_pay_plan_fields',
    '_order_part_pay_requested',
    '_order_part_pay_tail_node',
    '_order_ready_for_warehouse_delivery',
    '_order_status_code',
    '_order_text',
    '_paused_summary',
    '_payload_brief',
    '_post_admin_form',
    '_post_admin_urlencoded',
    '_prepare_offer_data',
    '_prepare_translate_data',
    '_public_order_options',
    '_purchase_is_pending_start',
    '_purchase_item_brief',
    '_purchase_list_fields',
    '_purchase_status_name',
    '_resume_node_for_order_status',
    '_runtime_from_variables',
    '_save_order_part_pay_plan_if_needed',
    '_select_purchase_items',
    '_unique_list',
    'bulk_cart',
    'copy',
    'random',
    're',
    'requests',
    'time',
    'urljoin',
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


def _impl__translate_order_msg(msg: Any) -> str:
    """把后端日文错误提示翻译成中文，未命中的保留原文。"""
    text = str(msg or "").strip()
    if not text:
        return ""
    for jp, cn in _ORDER_MSG_TRANSLATIONS.items():
        if jp in text:
            return text.replace(jp, cn)
    return text


def _impl__parse_order_max_limit(msg: Any) -> int | None:
    """从"订单提交商品数已达最大限制:50"类提示中解析最大数量。"""
    text = str(msg or "")
    m = re.search(r"[:：]\s*(\d+)\s*$", text)
    return int(m.group(1)) if m else None


def _impl__order_fields(
    items: list[Dict[str, Any]],
    create_type: str,
    order_sn: str,
    quantity: int,
    logistics_id: str,
    client_remark: str,
) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["create_type"] = create_type
    fields["order_sn"] = order_sn
    fields["client_remark"] = client_remark
    fields["logistics_id"] = logistics_id
    for index, item in enumerate(items):
        prefix = f"order_detail[{index}]"
        detail = _order_text(item.get("detail"), "[]")
        price = item.get("price")
        if price in (None, ""):
            price = _first_price(item.get("price_ranges"))
        fields[f"{prefix}['cart_id']"] = item.get("id") or ""
        fields[f"{prefix}[goods_id]"] = item.get("goods_id") or ""
        fields[f"{prefix}[goods_title]"] = item.get("goods_title") or ""
        fields[f"{prefix}[price]"] = price or "0"
        fields[f"{prefix}[num]"] = quantity
        fields[f"{prefix}[pic]"] = item.get("pic") or ""
        fields[f"{prefix}[detail]"] = detail
        fields[f"{prefix}[sku_id]"] = item.get("sku_id") or ""
        fields[f"{prefix}[spec_id]"] = item.get("spec_id") or ""
        fields[f"{prefix}[shop_id]"] = item.get("shop_id") or ""
        fields[f"{prefix}[shop_name]"] = item.get("shop_name") or ""
        fields[f"{prefix}[from_platform]"] = item.get("from_platform") or item.get("shop_type") or ""
        fields[f"{prefix}[client_remark]"] = item.get("client_remark") or ""
        if item.get("option") not in (None, ""):
            fields[f"{prefix}[option]"] = _order_text(item.get("option"))
    return fields


def _impl__extract_order_sn(payload: Dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, dict) and data.get("order_sn"):
        return str(data.get("order_sn"))
    if payload.get("order_sn"):
        return str(payload.get("order_sn"))
    return ""


def _impl__decimal_text(value: Any, fallback: str = "0") -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        number = Decimal(str(fallback))
    text = format(number.normalize(), "f")
    return "0" if text == "-0" else text


def _impl__optional_decimal_text(*values: Any) -> str | None:
    for value in values:
        if value not in (None, ""):
            return _decimal_text(value)
    return None


def _impl__money_total(num: Any, price: Any, freight: Any = "0") -> str:
    try:
        total = Decimal(str(num)) * Decimal(str(price)) + Decimal(str(freight))
    except (InvalidOperation, ValueError, TypeError):
        total = Decimal("0")
    return _decimal_text(total)


def _impl__offer_unit_price_values(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        values = [item.strip().strip("\"'") for item in re.split(r"[,，]", text) if item.strip()]
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        values = [value]
    prices: list[str] = []
    for item in values:
        try:
            number = Decimal(str(item))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"逐商品报价包含非法金额：{item}") from exc
        if number < 0:
            raise ValueError("逐商品报价不能小于0")
        prices.append(_decimal_text(number))
    return prices


def _impl__admin_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "AdminToken": token,
        "ManageToken": token,
        "adminToken": token,
        "token": token,
        "X-Requested-With": "XMLHttpRequest",
        "Lang": "zh-CN",
    }


def _impl__call_with_retry(label: str, operation: Any, attempts: int = 3, delay: float = 0.8) -> Any:
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                # 抖动指数退避：delay * 2^attempt + 随机 0~0.1s，避免惊群效应
                sleep_sec = delay * (2 ** attempt) + random.uniform(0, 0.1)
                time.sleep(sleep_sec)
    raise RuntimeError(f"{label} failed after {attempts} attempts: {last_error}")


def _impl__post_admin_form(
    session: requests.Session,
    base_url: str,
    path: str,
    fields: Dict[str, Any],
    timeout: int,
) -> Dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    files = {str(key): (None, _order_text(value)) for key, value in fields.items()}
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.post(url, files=files, timeout=timeout)
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"admin request {path} failed after retries: {last_error}")


def _impl__submit_order_translate_with_reconciliation(
    session: requests.Session,
    base_url: str,
    variables: Dict[str, Any],
    order_sn: str,
    fields: Dict[str, Any],
    timeout: int,
    before_state: Any = 20,
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    path = _api_path(variables, "admin_order_translate", "/order.submitTranslate")
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    files = {str(key): (None, _order_text(value)) for key, value in fields.items()}
    base_evidence: Dict[str, Any] = {
        "attempted_action": "order.submitTranslate",
        "attempted_actions": [{"action": "order.submitTranslate", "attempt_count": 1}],
        "request_attempt_count": 1,
        "before_state": before_state,
        "before_evidence": {"order_sn": order_sn, "backend_status": before_state},
    }
    try:
        response = session.post(url, files=files, timeout=timeout)
        payload = response.json()
        payload = payload if isinstance(payload, dict) else {}
        written = _api_success(payload)
        return (
            payload,
            {},
            {
                **base_evidence,
                "write_state": "confirmed_written" if written else "confirmed_not_written",
                "reason_code": "confirmed_written" if written else "confirmed_not_written",
                "reconciled_after_timeout": False,
                "detail_checks": 0,
                "after_state": None,
                "query_evidence": {"statuses": [], "errors": [], "conflicts": []},
                "after_evidence": {"response": _payload_brief(payload)},
                "business_diffs": {},
            },
        )
    except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
        attempts = max(1, min(30, _as_int(variables.get("translate_reconcile_attempts"), 12)))
        try:
            delay = max(0.0, float(variables.get("translate_reconcile_delay", 10)))
        except (TypeError, ValueError):
            delay = 10.0
        last_status: int | None = None
        last_order_data: Dict[str, Any] = {}
        statuses: list[int] = []
        detail_errors: list[str] = []
        conflicts: list[Dict[str, Any]] = []
        for attempt in range(attempts):
            try:
                _detail_payload, order_data = _impl__order_detail_data(
                    session,
                    base_url,
                    variables,
                    order_sn,
                    timeout,
                    retries=0,
                )
                last_status = _order_status_code(order_data)
                returned_order_sn = str(order_data.get("order_sn") or "").strip()
                if returned_order_sn and returned_order_sn != order_sn:
                    conflicts.append(
                        {
                            "check": attempt + 1,
                            "kind": "order_sn_mismatch",
                            "expected_order_sn": order_sn,
                            "actual_order_sn": returned_order_sn,
                        }
                    )
                elif last_status is not None:
                    statuses.append(last_status)
                    last_order_data = order_data
                if last_status is not None and last_status > 20:
                    if conflicts:
                        continue
                    query_evidence = {
                        "statuses": statuses,
                        "errors": detail_errors,
                        "conflicts": conflicts,
                    }
                    return (
                        {"success": True, "code": 0, "msg": "翻译请求超时后已通过订单状态确认成功"},
                        order_data,
                        {
                            **base_evidence,
                            "write_state": "confirmed_written",
                            "reason_code": "confirmed_written",
                            "reconciled_after_timeout": True,
                            "detail_checks": attempt + 1,
                            "backend_status": last_status,
                            "request_error": str(exc),
                            "after_state": last_status,
                            "query_evidence": query_evidence,
                            "after_evidence": query_evidence,
                            "business_diffs": {
                                "backend_status": {"before": before_state, "after": last_status}
                            },
                        },
                    )
            except (requests.RequestException, RuntimeError, ValueError) as detail_exc:
                detail_errors.append(str(detail_exc))
            if attempt < attempts - 1 and delay:
                time.sleep(delay)
        query_evidence = {
            "statuses": statuses,
            "errors": detail_errors,
            "conflicts": conflicts,
        }
        confirmed_not_written = bool(statuses) and all(status == 20 for status in statuses) and not detail_errors and not conflicts
        write_state = "confirmed_not_written" if confirmed_not_written else "indeterminate"
        reason_code = "confirmed_not_written" if confirmed_not_written else "unknown_write_state"
        message = (
            "订单翻译提交响应超时，回查确认仍处于写入前状态，未重复提交"
            if confirmed_not_written
            else "订单翻译提交响应超时，回查后仍无法确认写入状态，未重复提交"
        )
        return (
            {"success": False, "code": reason_code, "msg": message},
            last_order_data,
            {
                **base_evidence,
                "write_state": write_state,
                "reason_code": reason_code,
                "reconciled_after_timeout": True,
                "detail_checks": attempts,
                "backend_status": last_status,
                "request_error": str(exc),
                "after_state": last_status,
                "query_evidence": query_evidence,
                "after_evidence": query_evidence,
                "business_diffs": (
                    {"backend_status": {"before": before_state, "after": last_status}}
                    if last_status is not None
                    else {}
                ),
            },
        )


def _impl__flatten_urlencoded_fields(value: Any, prefix: str) -> list[tuple[str, str]]:
    if isinstance(value, dict):
        pairs: list[tuple[str, str]] = []
        for key, item in value.items():
            pairs.extend(_flatten_urlencoded_fields(item, f"{prefix}[{key}]"))
        return pairs
    if isinstance(value, (list, tuple)):
        pairs = []
        for index, item in enumerate(value):
            pairs.extend(_flatten_urlencoded_fields(item, f"{prefix}[{index}]"))
        return pairs
    return [(prefix, "" if value is None else str(value))]


def _impl__post_admin_urlencoded(
    session: requests.Session,
    base_url: str,
    path: str,
    fields: Dict[str, Any],
    timeout: int,
) -> Dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    data: list[tuple[str, str]] = []
    for key, value in fields.items():
        data.extend(_flatten_urlencoded_fields(value, str(key)))
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.post(url, data=data, headers=headers, timeout=timeout)
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"admin request {path} failed after retries: {last_error}")


def _impl__admin_login_without_runtime(
    session: requests.Session,
    base_url: str,
    variables: Dict[str, Any],
    timeout: int,
) -> tuple[Dict[str, Any], str]:
    fields = {
        "username": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
        "password": str(variables.get("backend_password") or "xiaolin666@@"),
        "system": str(variables.get("backend_system") or "1"),
        "compute_token": str(variables.get("backend_compute_token") or ""),
        "code": str(variables.get("backend_code") or "wnm666"),
    }
    payload = _post_admin_form(session, base_url, _api_path(variables, "admin_login", "/admin.login"), fields, timeout)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    token = str(data.get("access_token") or "")
    if token:
        session.headers.update(_admin_headers(token))
    return payload, token


def _impl__admin_login(
    session: requests.Session,
    base_url: str,
    variables: Dict[str, Any],
    timeout: int,
) -> tuple[Dict[str, Any], str]:
    runtime = _runtime_from_variables(variables)
    if runtime:
        payload, token, _cached = runtime.admin_login(session, base_url, variables, timeout)
        return payload, token
    return _admin_login_without_runtime(session, base_url, variables, timeout)


def _impl__order_detail_data(
    session: requests.Session,
    base_url: str,
    variables: Dict[str, Any],
    order_sn: str,
    timeout: int,
    retries: int = 4,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    payload: Dict[str, Any] = {}
    data: Dict[str, Any] = {}
    for attempt in range(retries + 1):
        payload = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_order_detail", "/order.detail"),
            {"order_sn": order_sn},
            timeout,
        )
        raw_data = payload.get("data")
        data = raw_data if isinstance(raw_data, dict) else {}
        if _api_success(payload) and data.get("order_detail"):
            return payload, data
        if attempt < retries:
            time.sleep(0.8 * (attempt + 1))
    return payload, data


def _impl__admin_detail_brief(order_data: Dict[str, Any]) -> Dict[str, Any]:
    details = order_data.get("order_detail")
    details = details if isinstance(details, list) else []
    return {
        "order_id": order_data.get("id"),
        "order_sn": order_data.get("order_sn"),
        "status": order_data.get("status"),
        "statusName": order_data.get("statusName"),
        "detail_count": len(details),
        "details": [
            {
                "id": item.get("id"),
                "goods_id": item.get("goods_id"),
                "num": item.get("num"),
                "confirm_num": item.get("confirm_num"),
                "confirm_price": item.get("confirm_price"),
                "offer_num": item.get("offer_num"),
                "offer_price": item.get("offer_price"),
                "status": item.get("status"),
                "statusName": item.get("statusName"),
            }
            for item in details[:10]
            if isinstance(item, dict)
        ],
    }


def _impl__prepare_translate_data(order_data: Dict[str, Any], variables: Dict[str, Any]) -> Dict[str, Any]:
    prepared = copy.deepcopy(order_data)
    prepared["y_remark"] = str(variables.get("translate_remark") or prepared.get("y_remark") or "自动化订单翻译")
    details = prepared.get("order_detail")
    if isinstance(details, list):
        for detail in details:
            if not isinstance(detail, dict):
                continue
            detail["detail_y"] = detail.get("detail_y") or detail.get("detail") or []
            detail["sku_id_y"] = detail.get("sku_id_y") or detail.get("sku_id") or ""
            detail["spec_id_y"] = detail.get("spec_id_y") or detail.get("spec_id") or ""
    return prepared


def _impl__build_confirm_data(order_data: Dict[str, Any], variables: Dict[str, Any], item_quantity: int) -> Dict[str, Any]:
    quote_price = _decimal_text(variables.get("confirm_price") or variables.get("quote_unit_price") or "10")
    freight = _impl__optional_decimal_text(variables.get("confirm_freight"), variables.get("freight")) or "0"
    volume = str(variables.get("confirm_volume") or "1x2x3")
    weight = _as_int(variables.get("confirm_weight") or variables.get("weight"), 200)
    remark = str(variables.get("confirm_remark") or "自动化采购调查")
    details = order_data.get("order_detail")
    confirm_details = []
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict) or detail.get("id") in (None, ""):
            continue
        quantity = _as_int(detail.get("num") or item_quantity, item_quantity)
        confirm_detail = {
            "id": detail.get("id"),
            "confirm_num": str(quantity),
            "confirm_price": quote_price,
            "confirm_dicker_price": quote_price,
            "g_remark": remark,
            "volume": volume,
            "weight": weight,
        }
        confirm_detail["confirm_freight"] = freight
        confirm_detail["confirm_dicker_freight"] = freight
        confirm_details.append(confirm_detail)
    return {"order_sn": order_data.get("order_sn"), "order_detail": confirm_details}


def _impl__order_part_pay_enabled(variables: Dict[str, Any]) -> bool:
    return _full_flow_part_pay_script_enabled(variables) and _order_part_pay_requested(variables)


def _impl__full_flow_part_pay_script_enabled(variables: Dict[str, Any]) -> bool:
    return _as_bool(variables.get("_full_flow_part_pay_script"), False)


def _impl__order_part_pay_requested(variables: Dict[str, Any]) -> bool:
    return _as_bool(variables.get("order_part_pay"), False) or str(variables.get("order_part_pay")).strip() == "1"


def _impl__order_part_pay_percent(variables: Dict[str, Any]) -> int:
    percent = _as_int(variables.get("order_part_pay_percent"), 10)
    percent = max(0, min(100, percent))
    return int(round(percent / 5) * 5)


def _impl__order_part_pay_tail_node(variables: Dict[str, Any]) -> str:
    node = str(variables.get("order_part_pay_tail_node") or "before_shelf").strip()
    return node if node in ORDER_PART_PAY_TAIL_NODES else "before_shelf"


def _impl__order_part_pay_fee_timing(variables: Dict[str, Any]) -> Dict[str, str]:
    raw = variables.get("order_part_pay_fee_timing")
    raw = raw if isinstance(raw, dict) else {}
    timing: Dict[str, str] = {}
    for key in ORDER_PART_PAY_FEE_KEYS:
        value = str(raw.get(key) or "first").strip()
        timing[key] = "tail" if value in {"tail", "尾款支付"} else "first"
    return timing


def _impl__apply_order_part_pay_payload(prepared: Dict[str, Any], variables: Dict[str, Any]) -> None:
    if _full_flow_part_pay_script_enabled(variables):
        prepared["order_part_pay"] = 1 if _order_part_pay_requested(variables) else 0
    else:
        prepared.pop("order_part_pay", None)


def _impl__order_part_pay_api_node(variables: Dict[str, Any]) -> int:
    configured = variables.get("order_part_pay_must_pay_node")
    if configured not in (None, ""):
        return _as_int(configured, 1)
    return 1 if _order_part_pay_tail_node(variables) == "before_shelf" else 2


def _impl__order_part_pay_api_fee_flag(timing: Dict[str, str], key: str) -> int:
    return 0 if timing.get(key) == "tail" else 1


def _impl__order_part_pay_goods_total(offer_data: Dict[str, Any]) -> Decimal:
    total = Decimal("0")
    details = offer_data.get("order_detail")
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        try:
            num = Decimal(str(detail.get("confirm_num") or detail.get("num") or detail.get("offer_num") or "0"))
            price = Decimal(str(detail.get("offer_price") or detail.get("confirm_price") or "0"))
        except (InvalidOperation, TypeError, ValueError):
            continue
        total += max(Decimal("0"), num) * max(Decimal("0"), price)
    return total


def _impl__order_part_pay_first_goods_amount(offer_data: Dict[str, Any], variables: Dict[str, Any]) -> str:
    total = _order_part_pay_goods_total(offer_data)
    amount = total * Decimal(_order_part_pay_percent(variables)) / Decimal("100")
    return f"{amount.quantize(Decimal('0.01')):.2f}"


def _impl__order_part_pay_plan_fields(order_sn: str, offer_data: Dict[str, Any], variables: Dict[str, Any]) -> OrderedDict[str, Any]:
    timing = _order_part_pay_fee_timing(variables)
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["preview"] = str(variables.get("order_part_pay_preview") or "0")
    fields["order_sn"] = order_sn
    fields["goods_amount"] = _order_part_pay_first_goods_amount(offer_data, variables)
    fields["is_pay_freight_amount"] = _order_part_pay_api_fee_flag(timing, "domestic_freight")
    fields["is_pay_option_amount"] = _order_part_pay_api_fee_flag(timing, "additional_service_fee")
    fields["is_pay_service_amount"] = _order_part_pay_api_fee_flag(timing, "service_fee")
    fields["is_pay_other_amount"] = _order_part_pay_api_fee_flag(timing, "other_fee")
    fields["must_pay_node"] = _order_part_pay_api_node(variables)
    fields["first_payment_ratio"] = _order_part_pay_percent(variables)
    return fields


def _impl__save_order_part_pay_plan_if_needed(
    session: requests.Session,
    base_url: str,
    variables: Dict[str, Any],
    order_sn: str,
    offer_data: Dict[str, Any],
    timeout: int,
) -> tuple[bool, Dict[str, Any]]:
    if not _full_flow_part_pay_script_enabled(variables):
        return True, {"skipped": True, "reason": "分批付款仅全流程加入分批付款脚本启用"}
    if not _order_part_pay_enabled(variables):
        return True, {"skipped": True, "reason": "未启用分批付款"}
    fields = _order_part_pay_plan_fields(order_sn, offer_data, variables)
    payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_order_part_pay_plan", "/order.updateOrderPartPayPlan"),
        fields,
        timeout,
    )
    summary = {**_payload_brief(payload), "request": dict(fields)}
    if not _api_success(payload):
        summary["reason"] = str(payload.get("msg") or payload.get("data") or "分批付款方案保存失败")
    return _api_success(payload), summary


def _impl__prepare_offer_data(order_data: Dict[str, Any], variables: Dict[str, Any], item_quantity: int) -> Dict[str, Any]:
    prepared = copy.deepcopy(order_data)
    quote_price = _decimal_text(variables.get("offer_price") or variables.get("quote_unit_price") or "10")
    unit_prices = _impl__offer_unit_price_values(variables.get("offer_unit_prices"))
    offer_freight = _impl__optional_decimal_text(variables.get("offer_freight"))
    prepared["other_price"] = _decimal_text(variables.get("other_price") or prepared.get("other_price") or "0")
    prepared["other_price_remark"] = str(variables.get("other_price_remark") or prepared.get("other_price_remark") or "自动化其他费用备注")
    prepared["y_reply"] = str(variables.get("y_reply") or prepared.get("y_reply") or "")
    prepared["y_remark"] = str(variables.get("offer_remark") or prepared.get("y_remark") or "自动化业务报价")
    prepared["predict_logistics_price"] = _decimal_text(variables.get("predict_logistics_price") or prepared.get("predict_logistics_price") or "0")
    _apply_order_part_pay_payload(prepared, variables)
    details = prepared.get("order_detail")
    if isinstance(details, list):
        valid_details = [detail for detail in details if isinstance(detail, dict)]
        if len(unit_prices) > 1 and len(unit_prices) != len(valid_details):
            raise ValueError(
                f"逐商品报价数量不匹配：订单有{len(valid_details)}个商品，收到{len(unit_prices)}个报价"
            )
        for index, detail in enumerate(valid_details):
            if not isinstance(detail, dict):
                continue
            item_offer_price = unit_prices[0] if len(unit_prices) == 1 else (
                unit_prices[index] if unit_prices else quote_price
            )
            quantity = _as_int(detail.get("confirm_num") or detail.get("num") or item_quantity, item_quantity)
            offer_quantity = _as_int(variables.get("offer_num"), quantity)
            detail["confirm_num"] = str(quantity)
            detail["confirm_price"] = quote_price
            detail["confirm_dicker_price"] = quote_price
            detail["offer_num"] = offer_quantity
            detail["offer_price"] = item_offer_price
            detail.pop("offer_freight", None)
            if offer_freight is not None:
                detail["offer_freight"] = offer_freight
            detail["offer_total"] = _money_total(
                offer_quantity, item_offer_price, offer_freight or "0"
            )
    return prepared


def _impl__run_backend_order_flow(
    base_url: str,
    timeout: int,
    variables: Dict[str, Any],
    order_sn: str,
    item_quantity: int,
    log: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    backend_log: Dict[str, Any] = {"order_sn": order_sn, "steps": []}
    log["backend"] = backend_log
    session = _admin_session_from(variables)

    login_payload, token = _admin_login(session, base_url, variables, timeout)
    backend_log["login"] = {
        **_payload_brief(login_payload),
        "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
        "token_extracted": bool(token),
    }
    if not _api_success(login_payload) or not token:
        return False, {"backend_passed": False, "reason": "后台登录失败"}

    detail_payload, order_data = _order_detail_data(session, base_url, variables, order_sn, timeout)
    backend_log["detail_before"] = {**_payload_brief(detail_payload), **_admin_detail_brief(order_data)}
    if not _api_success(detail_payload) or not order_data.get("order_detail"):
        return False, {"backend_passed": False, "reason": "未获取到后台订单详情"}

    translate_data = _prepare_translate_data(order_data, variables)
    before_translate_status = _order_status_code(order_data)
    if before_translate_status is not None and before_translate_status > 20:
        translate_payload = {"success": True, "code": 0, "msg": "订单状态已确认翻译写入，无需重复提交"}
        reconciled_data = order_data
        translate_reconciliation = {
            "write_state": "confirmed_written",
            "reason_code": "confirmed_written",
            "attempted_action": "order.submitTranslate",
            "attempted_actions": [],
            "request_attempt_count": 0,
            "before_state": before_translate_status,
            "after_state": before_translate_status,
            "before_evidence": {"order_sn": order_sn, "backend_status": before_translate_status},
            "after_evidence": {"statuses": [before_translate_status], "errors": [], "conflicts": []},
            "query_evidence": {"statuses": [before_translate_status], "errors": [], "conflicts": []},
            "business_diffs": {},
            "reconciled_after_timeout": False,
            "detail_checks": 0,
        }
    else:
        translate_payload, reconciled_data, translate_reconciliation = _submit_order_translate_with_reconciliation(
            session,
            base_url,
            variables,
            order_sn,
            {"data": bulk_cart.json_text(translate_data), "is_temp": str(variables.get("translate_is_temp") or "0")},
            timeout,
            before_state=before_translate_status,
        )
    backend_log["translate"] = _payload_brief(translate_payload)
    backend_log["translate_reconciliation"] = translate_reconciliation
    translate_result_evidence = {
        "write_state": translate_reconciliation.get("write_state"),
        "write_reason_code": translate_reconciliation.get("reason_code"),
        "attempted_actions": translate_reconciliation.get("attempted_actions") or [],
        "before_evidence": translate_reconciliation.get("before_evidence") or {},
        "after_evidence": translate_reconciliation.get("after_evidence") or {},
        "business_diffs": translate_reconciliation.get("business_diffs") or {},
        "request_attempt_count": translate_reconciliation.get("request_attempt_count", 1),
        "reconciliation": translate_reconciliation,
    }
    if not _api_success(translate_payload):
        return False, {
            "order_sn": order_sn,
            "backend_passed": False,
            "reason": str(translate_payload.get("msg") or "订单翻译提交失败"),
            "reason_code": str(translate_reconciliation.get("reason_code") or "reconciliation_failed"),
            "write_state": str(translate_reconciliation.get("write_state") or "indeterminate"),
            "translate": _payload_brief(translate_payload),
            "attempted_actions": translate_reconciliation.get("attempted_actions") or [],
            "before_evidence": translate_reconciliation.get("before_evidence") or {},
            "after_evidence": translate_reconciliation.get("after_evidence") or {},
            "business_diffs": translate_reconciliation.get("business_diffs") or {},
            "request_attempt_count": translate_reconciliation.get("request_attempt_count", 1),
            "reconciliation": translate_reconciliation,
        }

    # detail_after_translate：仅 order_translated 暂停点需要准确 status，非暂停路径跳过冗余查询
    #（translate 不修改 order_detail 结构，confirm_source 直接用 translate_data 即可）
    if _checkpoint_requested(variables, "order_translated"):
        after_translate = reconciled_data
        if not after_translate:
            _, after_translate = _order_detail_data(session, base_url, variables, order_sn, timeout, retries=2)
        backend_log["detail_after_translate"] = _admin_detail_brief(after_translate)
        return True, _paused_summary(
            "order_translated",
            {
                "order_sn": order_sn,
                "backend_passed": True,
                "backend_steps": ["login", "detail", "translate"],
                "backend_status": after_translate.get("status") if after_translate else None,
                **translate_result_evidence,
            },
        )
    backend_log["detail_after_translate"] = {**_admin_detail_brief(order_data), "cached_from": "detail_before"}
    confirm_source = translate_data
    confirm_data = _build_confirm_data(confirm_source, variables, item_quantity)
    confirm_payload = _post_admin_form(
        session,
        base_url,
        _api_path(variables, "admin_order_confirm", "/order.submitConfirm"),
        {
            "order_sn": order_sn,
            "data": bulk_cart.json_text(confirm_data),
            "is_temp": str(variables.get("confirm_is_temp") or "0"),
        },
        timeout,
    )
    backend_log["confirm"] = {
        **_payload_brief(confirm_payload),
        "detail_count": len(confirm_data.get("order_detail") or []),
    }
    if not _api_success(confirm_payload):
        return False, {"backend_passed": False, "reason": "订单采购调查提交失败", "confirm": _payload_brief(confirm_payload)}

    _, after_confirm = _order_detail_data(session, base_url, variables, order_sn, timeout, retries=2)
    backend_log["detail_after_confirm"] = _admin_detail_brief(after_confirm)
    if _checkpoint_requested(variables, "order_confirmed"):
        return True, _paused_summary(
            "order_confirmed",
            {
                "order_sn": order_sn,
                "backend_passed": True,
                "backend_steps": ["login", "detail", "translate", "confirm"],
                "backend_status": after_confirm.get("status") if after_confirm else None,
                **translate_result_evidence,
            },
        )

    offer_source = after_confirm or confirm_source
    offer_data = _prepare_offer_data(offer_source, variables, item_quantity)
    part_pay_passed, part_pay_summary = _save_order_part_pay_plan_if_needed(session, base_url, variables, order_sn, offer_data, timeout)
    backend_log["part_pay_plan"] = part_pay_summary
    if not part_pay_passed:
        return False, {"backend_passed": False, "reason": str(part_pay_summary.get("reason") or "分批付款方案保存失败"), "part_pay_plan": part_pay_summary}

    offer_payload = _post_admin_form(
        session,
        base_url,
        _api_path(variables, "admin_order_offer", "/order.submitOffer"),
        {"data": bulk_cart.json_text(offer_data), "is_temp": str(variables.get("offer_is_temp") or "0")},
        timeout,
    )
    backend_log["offer"] = {
        **_payload_brief(offer_payload),
        "detail_count": len(offer_data.get("order_detail") or []),
    }
    if not _api_success(offer_payload):
        return False, {"backend_passed": False, "reason": "业务报价提交失败", "offer": _payload_brief(offer_payload)}

    # detail_after_offer：order_offered 暂停点不需要最新 status，跳过冗余查询；
    # 非暂停路径（继续到 order_paid）仍需查询以获取真实 status
    if _checkpoint_requested(variables, "order_offered"):
        backend_log["detail_after_offer"] = {
            **_admin_detail_brief(after_confirm),
            "skipped": True,
            "reason": "paused_at_order_offered",
            "cached_from": "after_confirm",
        }
        return True, _paused_summary(
            "order_offered",
            {
                "order_sn": order_sn,
                "backend_passed": True,
                "backend_steps": ["login", "detail", "translate", "confirm", "part_pay_plan", "offer"],
                "quote_unit_price": _decimal_text(variables.get("offer_price") or variables.get("quote_unit_price") or "10"),
                "backend_status": after_confirm.get("status") if after_confirm else None,
                **translate_result_evidence,
            },
        )
    _, after_offer = _order_detail_data(session, base_url, variables, order_sn, timeout, retries=1)
    backend_log["detail_after_offer"] = _admin_detail_brief(after_offer)
    return True, {
        "backend_passed": True,
        "backend_steps": ["login", "detail", "translate", "confirm", "part_pay_plan", "offer"],
        "quote_unit_price": _decimal_text(variables.get("offer_price") or variables.get("quote_unit_price") or "10"),
        "backend_status": after_offer.get("status") if after_offer else None,
        **translate_result_evidence,
    }


def _impl__order_status_code(order_data: Dict[str, Any]) -> int | None:
    for key in ["status", "order_status", "orderStatus"]:
        value = order_data.get(key)
        if value in (None, ""):
            continue
        try:
            return int(Decimal(str(value)))
        except (InvalidOperation, TypeError, ValueError):
            continue
    return None


def _impl__resume_node_for_order_status(status: int | None) -> str:
    if status == 20:
        return "order_translated"
    if status == 21:
        return "order_confirmed"
    if status == 22:
        return "order_offered"
    if status == 30:
        return "order_offered"
    if status == 80:
        return "porder_shipped"
    return ""


def _impl__order_detail_ids(order_data: Dict[str, Any]) -> list[str]:
    details = order_data.get("order_detail")
    if not isinstance(details, list):
        return []
    ids: list[str] = []
    for item in details:
        if not isinstance(item, dict):
            continue
        for key in ["order_detail_id", "orderDetailId", "detail_id", "id"]:
            value = item.get(key)
            if value not in (None, ""):
                ids.append(str(value).strip())
                break
    return _unique_list(ids)


def _impl__order_ready_for_warehouse_delivery(status: int | None, order_data: Dict[str, Any]) -> bool:
    details = order_data.get("order_detail")
    if not isinstance(details, list):
        return False
    ready_names = ["\u5f85\u53d1\u8d27", "\u53ef\u53d1\u8d27", "\u5df2\u5165\u5e93", "\u5df2\u4e0a\u67b6", "\u4e0a\u67b6\u5b8c\u4e86"]
    valid_details = [item for item in details if isinstance(item, dict)]
    if not valid_details:
        return False
    for item in valid_details:
        status_name = str(item.get("statusName") or item.get("status_name") or "")
        if not any(name in status_name for name in ready_names):
            return False
    return True


def _impl__purchase_is_pending_start(item: Dict[str, Any]) -> bool:
    return "\u5f85\u62cd\u4e0b" in _purchase_status_name(item)


def _impl__detect_resume_order_state(
    env: Env,
    variables: Dict[str, Any],
    order_sn: str,
    log: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    base_url = (variables.get("backend_base_url") or env.base_url or bulk_cart.BASE_URL).rstrip("/")
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    detect_log: Dict[str, Any] = {"order_sn": order_sn, "base_url": base_url}
    log["resume_detect"] = detect_log

    session = _admin_session_from(variables)
    login_payload, token = _admin_login(session, base_url, variables, timeout)
    detect_log["login"] = {
        **_payload_brief(login_payload),
        "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
        "token_extracted": bool(token),
    }
    if not _api_success(login_payload) or not token:
        return False, {"order_sn": order_sn, "detected_start_node": "", "reason": "\u540e\u53f0\u767b\u5f55\u5931\u8d25"}

    detail_payload, order_data = _order_detail_data(session, base_url, variables, order_sn, timeout)
    detect_log["detail"] = {**_payload_brief(detail_payload), **_admin_detail_brief(order_data)}
    if not _api_success(detail_payload) or not order_data.get("order_detail"):
        return False, {"order_sn": order_sn, "detected_start_node": "", "reason": "\u672a\u67e5\u5230\u540e\u53f0\u8ba2\u5355\u8be6\u60c5"}

    purchase_items: list[Dict[str, Any]] = []
    pending_purchase_items: list[Dict[str, Any]] = []
    purchase_fields = _purchase_list_fields(variables, order_sn)
    purchase_payload = _post_admin_form(
        session,
        base_url,
        _api_path(variables, "admin_purchase_list", "/purchase.purchaseList"),
        purchase_fields,
        timeout,
    )
    purchase_rows = _admin_rows_from_payload(purchase_payload)
    if _api_success(purchase_payload):
        purchase_items = _select_purchase_items(_flatten_purchase_items(purchase_rows), order_sn, variables)
        pending_purchase_items = [item for item in purchase_items if _purchase_is_pending_start(item)]
    detect_log["purchase_list"] = {
        **_payload_brief(purchase_payload),
        "request": dict(purchase_fields),
        "row_count": len(purchase_rows),
        "selected_count": len(purchase_items),
        "pending_start_count": len(pending_purchase_items),
        "selected_items": [_purchase_item_brief(item) for item in purchase_items[:20]],
    }

    order_status = _order_status_code(order_data)
    order_detail_ids = _order_detail_ids(order_data)
    if pending_purchase_items:
        detected_start_node = "pending_purchase"
    elif _order_ready_for_warehouse_delivery(order_status, order_data):
        detected_start_node = "shelf_stored"
    elif order_status == 60:
        detected_start_node = "checking_started"
    else:
        detected_start_node = _resume_node_for_order_status(order_status)
    summary: Dict[str, Any] = {
        "order_sn": order_sn,
        "order_status": order_status,
        "detected_start_node": detected_start_node,
        "purchase_selected_count": len(purchase_items),
        "purchase_pending_start_count": len(pending_purchase_items),
        "purchase_items": [_purchase_item_brief(item) for item in (pending_purchase_items or purchase_items)[:20]],
        "order_detail": _admin_detail_brief(order_data),
        "order_data": order_data,
    }
    if order_detail_ids:
        summary["order_detail_id"] = order_detail_ids[0]
        summary["order_detail_ids"] = order_detail_ids
    if pending_purchase_items:
        summary["purchase_items"] = [_purchase_item_brief(item) for item in pending_purchase_items[:20]]
        return True, summary
    if detected_start_node == "shelf_stored":
        return True, summary
    if purchase_items:
        summary["reason"] = "\u8ba2\u5355\u5df2\u8fdb\u5165\u91c7\u8d2d\u4e2d\u95f4\u72b6\u6001\uff0c\u672c\u811a\u672c\u672c\u8f6e\u4ec5\u652f\u6301\u5f85\u62cd\u4e0b\u4f5c\u4e3a\u91c7\u8d2d\u8d77\u70b9"
        return False, summary
    if not detected_start_node:
        summary["reason"] = f"\u8ba2\u5355\u72b6\u6001 {order_status} \u4e0d\u5728\u672c\u811a\u672c\u6062\u590d\u8303\u56f4"
        return False, summary
    return True, summary


def _impl__run_backend_order_flow_resume(
    base_url: str,
    timeout: int,
    variables: Dict[str, Any],
    order_sn: str,
    item_quantity: int,
    log: Dict[str, Any],
    order_data: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    backend_log: Dict[str, Any] = {"order_sn": order_sn, "mode": "resume_order_flow", "steps": []}
    log["backend"] = backend_log
    session = _admin_session_from(variables)

    login_payload, token = _admin_login(session, base_url, variables, timeout)
    backend_log["login"] = {
        **_payload_brief(login_payload),
        "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
        "token_extracted": bool(token),
    }
    if not _api_success(login_payload) or not token:
        return False, {"backend_passed": False, "reason": "\u540e\u53f0\u767b\u5f55\u5931\u8d25"}

    current_data = order_data if isinstance(order_data, dict) else {}
    if not current_data.get("order_detail"):
        detail_payload, current_data = _order_detail_data(session, base_url, variables, order_sn, timeout)
        backend_log["detail_before"] = {**_payload_brief(detail_payload), **_admin_detail_brief(current_data)}
        if not _api_success(detail_payload) or not current_data.get("order_detail"):
            return False, {"backend_passed": False, "reason": "\u672a\u83b7\u53d6\u5230\u540e\u53f0\u8ba2\u5355\u8be6\u60c5"}
    else:
        backend_log["detail_before"] = _admin_detail_brief(current_data)

    status = _order_status_code(current_data)
    if status is None:
        return False, {"backend_passed": False, "reason": "\u672a\u8bc6\u522b\u8ba2\u5355\u72b6\u6001"}
    if status == 30:
        return True, {
            "order_sn": order_sn,
            "backend_passed": True,
            "backend_steps": ["login", "detail", "skip_completed_order_backend"],
            "backend_status": status,
            "already_order_offered": True,
        }
    if status not in (20, 21, 22):
        return False, {"backend_passed": False, "backend_status": status, "reason": f"\u8ba2\u5355\u72b6\u6001 {status} \u4e0d\u652f\u6301\u4ece\u8ba2\u5355\u9636\u6bb5\u6062\u590d"}

    backend_steps = ["login", "detail"]
    translate_result_evidence: Dict[str, Any] = {}
    if status <= 20:
        translate_data = _prepare_translate_data(current_data, variables)
        translate_payload, reconciled_data, translate_reconciliation = _submit_order_translate_with_reconciliation(
            session,
            base_url,
            variables,
            order_sn,
            {"data": bulk_cart.json_text(translate_data), "is_temp": str(variables.get("translate_is_temp") or "0")},
            timeout,
            before_state=status,
        )
        backend_log["translate"] = _payload_brief(translate_payload)
        backend_log["translate_reconciliation"] = translate_reconciliation
        translate_result_evidence = {
            "write_state": translate_reconciliation.get("write_state"),
            "write_reason_code": translate_reconciliation.get("reason_code"),
            "attempted_actions": translate_reconciliation.get("attempted_actions") or [],
            "before_evidence": translate_reconciliation.get("before_evidence") or {},
            "after_evidence": translate_reconciliation.get("after_evidence") or {},
            "business_diffs": translate_reconciliation.get("business_diffs") or {},
            "request_attempt_count": translate_reconciliation.get("request_attempt_count", 1),
            "reconciliation": translate_reconciliation,
        }
        if not _api_success(translate_payload):
            return False, {
                "order_sn": order_sn,
                "backend_passed": False,
                "reason": str(translate_payload.get("msg") or "\u8ba2\u5355\u7ffb\u8bd1\u63d0\u4ea4\u5931\u8d25"),
                "reason_code": str(translate_reconciliation.get("reason_code") or "reconciliation_failed"),
                "write_state": str(translate_reconciliation.get("write_state") or "indeterminate"),
                "translate": _payload_brief(translate_payload),
                "attempted_actions": translate_reconciliation.get("attempted_actions") or [],
                "before_evidence": translate_reconciliation.get("before_evidence") or {},
                "after_evidence": translate_reconciliation.get("after_evidence") or {},
                "business_diffs": translate_reconciliation.get("business_diffs") or {},
                "request_attempt_count": translate_reconciliation.get("request_attempt_count", 1),
                "reconciliation": translate_reconciliation,
            }
        backend_steps.append("translate")
        after_translate = reconciled_data
        if not after_translate:
            _, after_translate = _order_detail_data(session, base_url, variables, order_sn, timeout, retries=2)
        backend_log["detail_after_translate"] = _admin_detail_brief(after_translate)
        current_data = after_translate or translate_data
        if _checkpoint_requested(variables, "order_translated"):
            return True, _paused_summary(
                "order_translated",
                {
                    "order_sn": order_sn,
                    "backend_passed": True,
                    "backend_steps": backend_steps,
                    "backend_status": current_data.get("status") if current_data else None,
                    **translate_result_evidence,
                },
            )

    if status <= 21:
        confirm_data = _build_confirm_data(current_data, variables, item_quantity)
        confirm_payload = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_order_confirm", "/order.submitConfirm"),
            {
                "order_sn": order_sn,
                "data": bulk_cart.json_text(confirm_data),
                "is_temp": str(variables.get("confirm_is_temp") or "0"),
            },
            timeout,
        )
        backend_log["confirm"] = {
            **_payload_brief(confirm_payload),
            "detail_count": len(confirm_data.get("order_detail") or []),
        }
        if not _api_success(confirm_payload):
            return False, {"backend_passed": False, "reason": "\u8ba2\u5355\u91c7\u8d2d\u8c03\u67e5\u63d0\u4ea4\u5931\u8d25", "confirm": _payload_brief(confirm_payload)}
        backend_steps.append("confirm")
        _, after_confirm = _order_detail_data(session, base_url, variables, order_sn, timeout, retries=2)
        backend_log["detail_after_confirm"] = _admin_detail_brief(after_confirm)
        current_data = after_confirm or current_data
        if _checkpoint_requested(variables, "order_confirmed"):
            return True, _paused_summary(
                "order_confirmed",
                {
                    "order_sn": order_sn,
                    "backend_passed": True,
                    "backend_steps": backend_steps,
                    "backend_status": current_data.get("status") if current_data else None,
                    **translate_result_evidence,
                },
            )

    if status <= 22:
        offer_data = _prepare_offer_data(current_data, variables, item_quantity)
        part_pay_passed, part_pay_summary = _save_order_part_pay_plan_if_needed(session, base_url, variables, order_sn, offer_data, timeout)
        backend_log["part_pay_plan"] = part_pay_summary
        if not part_pay_passed:
            return False, {"backend_passed": False, "reason": str(part_pay_summary.get("reason") or "分批付款方案保存失败"), "part_pay_plan": part_pay_summary}
        backend_steps.append("part_pay_plan")
        offer_payload = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_order_offer", "/order.submitOffer"),
            {"data": bulk_cart.json_text(offer_data), "is_temp": str(variables.get("offer_is_temp") or "0")},
            timeout,
        )
        backend_log["offer"] = {
            **_payload_brief(offer_payload),
            "detail_count": len(offer_data.get("order_detail") or []),
        }
        if not _api_success(offer_payload):
            return False, {"backend_passed": False, "reason": "\u4e1a\u52a1\u62a5\u4ef7\u63d0\u4ea4\u5931\u8d25", "offer": _payload_brief(offer_payload)}
        backend_steps.append("offer")
        _, after_offer = _order_detail_data(session, base_url, variables, order_sn, timeout, retries=1)
        backend_log["detail_after_offer"] = _admin_detail_brief(after_offer)
        current_data = after_offer or current_data
        if _checkpoint_requested(variables, "order_offered"):
            return True, _paused_summary(
                "order_offered",
                {
                    "order_sn": order_sn,
                    "backend_passed": True,
                    "backend_steps": backend_steps,
                    "quote_unit_price": _decimal_text(variables.get("offer_price") or variables.get("quote_unit_price") or "10"),
                    "backend_status": current_data.get("status") if current_data else None,
                    **translate_result_evidence,
                },
            )

    return True, {
        "order_sn": order_sn,
        "backend_passed": True,
        "backend_steps": backend_steps,
        "quote_unit_price": _decimal_text(variables.get("offer_price") or variables.get("quote_unit_price") or "10"),
        "backend_status": current_data.get("status") if current_data else None,
        **translate_result_evidence,
    }


def _impl_preview_order_quote_options(env: Env, variables: Dict[str, Any] | None = None) -> Dict[str, Any]:
    variables = dict(variables or {})

    account, password, client_tool = _client_login_inputs(variables)
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
    item_count = _as_int(variables.get("order_item_count") or variables.get("item_count"), 2)
    order_shop_count_raw = variables.get("order_shop_count")
    order_per_shop_raw = variables.get("order_per_shop")
    use_shop_grouping = order_shop_count_raw not in (None, "") or order_per_shop_raw not in (None, "")
    order_shop_count = _as_int(order_shop_count_raw, 0)
    order_per_shop = _as_int(order_per_shop_raw, 0)
    if use_shop_grouping:
        if order_shop_count <= 0:
            order_shop_count = _as_int(variables.get("target_shops") or variables.get("shop_count"), 1)
        if order_per_shop <= 0:
            order_per_shop = _as_int(variables.get("per_shop"), item_count)
        item_count = order_shop_count * order_per_shop

    client = bulk_cart.RakumartClient(base_url, timeout)
    _configure_client_api_paths(client, variables)
    token = _call_with_retry("client login", lambda: client.login(account, password, client_tool))
    catalog, option_payload, source_path = _fetch_order_option_catalog(client, variables)

    return {
        "options": _public_order_options(catalog),
        "option_count": len(catalog),
        "source_path": source_path,
        "selected_count": 0,
        "item_count": item_count,
        "selection": {"mode": "option_preview", "expected_total": item_count, "selected_count": 0, "shortage_count": 0},
        "preview_mode": "option_list",
        "login": {"success": bool(token), "account": account, "client_tool": client_tool},
        "option_list": {**_payload_brief(option_payload), "option_count": len(catalog)},
    }


_translate_order_msg = _compat_wrapper(_impl__translate_order_msg)
_parse_order_max_limit = _compat_wrapper(_impl__parse_order_max_limit)
_order_fields = _compat_wrapper(_impl__order_fields)
_extract_order_sn = _compat_wrapper(_impl__extract_order_sn)
_decimal_text = _compat_wrapper(_impl__decimal_text)
_money_total = _compat_wrapper(_impl__money_total)
_admin_headers = _compat_wrapper(_impl__admin_headers)
_call_with_retry = _compat_wrapper(_impl__call_with_retry)
_post_admin_form = _compat_wrapper(_impl__post_admin_form)
_submit_order_translate_with_reconciliation = _compat_wrapper(_impl__submit_order_translate_with_reconciliation)
_flatten_urlencoded_fields = _compat_wrapper(_impl__flatten_urlencoded_fields)
_post_admin_urlencoded = _compat_wrapper(_impl__post_admin_urlencoded)
_admin_login_without_runtime = _compat_wrapper(_impl__admin_login_without_runtime)
_admin_login = _compat_wrapper(_impl__admin_login)
_order_detail_data = _compat_wrapper(_impl__order_detail_data)
_admin_detail_brief = _compat_wrapper(_impl__admin_detail_brief)
_prepare_translate_data = _compat_wrapper(_impl__prepare_translate_data)
_build_confirm_data = _compat_wrapper(_impl__build_confirm_data)
_order_part_pay_enabled = _compat_wrapper(_impl__order_part_pay_enabled)
_full_flow_part_pay_script_enabled = _compat_wrapper(_impl__full_flow_part_pay_script_enabled)
_order_part_pay_requested = _compat_wrapper(_impl__order_part_pay_requested)
_order_part_pay_percent = _compat_wrapper(_impl__order_part_pay_percent)
_order_part_pay_tail_node = _compat_wrapper(_impl__order_part_pay_tail_node)
_order_part_pay_fee_timing = _compat_wrapper(_impl__order_part_pay_fee_timing)
_apply_order_part_pay_payload = _compat_wrapper(_impl__apply_order_part_pay_payload)
_order_part_pay_api_node = _compat_wrapper(_impl__order_part_pay_api_node)
_order_part_pay_api_fee_flag = _compat_wrapper(_impl__order_part_pay_api_fee_flag)
_order_part_pay_goods_total = _compat_wrapper(_impl__order_part_pay_goods_total)
_order_part_pay_first_goods_amount = _compat_wrapper(_impl__order_part_pay_first_goods_amount)
_order_part_pay_plan_fields = _compat_wrapper(_impl__order_part_pay_plan_fields)
_save_order_part_pay_plan_if_needed = _compat_wrapper(_impl__save_order_part_pay_plan_if_needed)
_prepare_offer_data = _compat_wrapper(_impl__prepare_offer_data)
_run_backend_order_flow = _compat_wrapper(_impl__run_backend_order_flow)
_order_status_code = _compat_wrapper(_impl__order_status_code)
_resume_node_for_order_status = _compat_wrapper(_impl__resume_node_for_order_status)
_order_detail_ids = _compat_wrapper(_impl__order_detail_ids)
_order_ready_for_warehouse_delivery = _compat_wrapper(_impl__order_ready_for_warehouse_delivery)
_purchase_is_pending_start = _compat_wrapper(_impl__purchase_is_pending_start)
_detect_resume_order_state = _compat_wrapper(_impl__detect_resume_order_state)
_run_backend_order_flow_resume = _compat_wrapper(_impl__run_backend_order_flow_resume)
preview_order_quote_options = _compat_wrapper(_impl_preview_order_quote_options)
