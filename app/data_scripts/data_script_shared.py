from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    'DataScriptRuntime',
    'FULL_FLOW_COMPLETE_NODE',
    'FULL_FLOW_NODE_LABELS',
    'MAX_LOG_BODY',
    'REQUEST_RETRIES',
    'REQUEST_RETRY_DELAY',
    'SCRIPT_NAME',
    '_as_bool',
    '_clean_multipart_headers',
    '_data_object',
    '_detail_specs',
    '_duration_ms',
    '_finish_named',
    '_first_stock',
    '_response_json',
    '_runtime_from_variables',
    '_stop_after_node',
    'datetime',
    'json',
    'requests',
    'time',
    'urljoin',
    'write_allure_result',
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


def _impl__runtime_from_variables(variables: Dict[str, Any]) -> DataScriptRuntime | None:
    runtime = variables.get("_runtime")
    return runtime if isinstance(runtime, DataScriptRuntime) else None


def _impl__admin_session_from(variables: Dict[str, Any]) -> requests.Session:
    """从 runtime 获取共享 session（如可用），否则新建一个"""
    runtime = _runtime_from_variables(variables)
    if runtime is not None:
        return runtime.admin_session()
    return requests.Session()


def _impl__client_login_inputs(variables: Dict[str, Any]) -> tuple[str, str, str]:
    account = str(variables.get("account") or "").strip()
    password = str(variables.get("password") or "").strip()
    client_tool = str(variables.get("client_tool") or "1").strip()
    if client_tool == "2" and not _as_bool(variables.get("allow_h5_client_tool"), False):
        client_tool = "1"
    return account, password, client_tool


def _impl__as_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or fallback
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return fallback


def _impl__unique_list(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        text = str(item).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _impl__as_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _impl__clean_multipart_headers(headers: Dict[str, Any]) -> Dict[str, str]:
    request_headers = {str(key): str(value) for key, value in (headers or {}).items() if value is not None}
    for key in list(request_headers.keys()):
        if key.lower() == "content-type" and "multipart/form-data" in request_headers[key].lower():
            request_headers.pop(key, None)
    return request_headers


def _impl__post_form(
    session: requests.Session,
    base_url: str,
    path: str,
    data: Dict[str, Any],
    headers: Dict[str, Any],
    timeout: int,
) -> requests.Response:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    files = {}
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        files[str(key)] = (None, "" if value is None else str(value))
    request_headers = _clean_multipart_headers(headers)
    for attempt in range(REQUEST_RETRIES + 1):
        try:
            return session.post(url, files=files, headers=request_headers, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout):
            if attempt >= REQUEST_RETRIES:
                raise
            time.sleep(REQUEST_RETRY_DELAY * (attempt + 1))
    raise RuntimeError("request retry exhausted")


def _impl__response_json(response: requests.Response) -> Dict[str, Any]:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _impl__response_brief(response: requests.Response, payload: Dict[str, Any] | None = None, include_body: bool = False) -> Dict[str, Any]:
    payload = payload if payload is not None else _response_json(response)
    brief: Dict[str, Any] = {"status_code": response.status_code}
    for key in ["success", "code", "msg"]:
        if key in payload:
            brief[key] = payload.get(key)
    if include_body:
        brief["body"] = response.text[:MAX_LOG_BODY]
    return brief


def _impl__extract_token(payload: Dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ["userToken", "token", "access_token"]:
            if data.get(key):
                return str(data[key])
    for key in ["userToken", "token", "access_token"]:
        if payload.get(key):
            return str(payload[key])
    return ""


def _impl__data_object(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _impl__goods_items(search_payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    result = _data_object(search_payload).get("result", {}).get("result", [])
    return result if isinstance(result, list) else []


def _impl__first_stock(detail_payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    inventory = _data_object(detail_payload).get("goodsInfo", {}).get("goodsInventory", [])
    for item in inventory if isinstance(inventory, list) else []:
        values = item.get("valueC") or item.get("valueT") or []
        for value in values if isinstance(values, list) else []:
            try:
                amount = int(value.get("amountOnSale") or 0)
            except (TypeError, ValueError):
                amount = 0
            if amount > 0:
                return value, item
    return {}, {}


def _impl__detail_specs(detail_payload: Dict[str, Any], stock_parent: Dict[str, Any]) -> str:
    specs = _data_object(detail_payload).get("goodsInfo", {}).get("specification", [])
    stock_text = f"{stock_parent.get('keyC') or ''} {stock_parent.get('keyT') or ''}"
    picked = []
    for item in specs[:2] if isinstance(specs, list) else []:
        values = item.get("valueC") or item.get("valueT") or []
        candidates = values if isinstance(values, list) else []
        selected = candidates[0] if candidates else {}
        for candidate in candidates:
            name = str(candidate.get("name") or "") if isinstance(candidate, dict) else ""
            if name and name in stock_text:
                selected = candidate
                break
        picked.append(
            {
                "key": item.get("keyC") or item.get("keyT") or "",
                "value": selected.get("name") if isinstance(selected, dict) else "",
            }
        )
    return json.dumps(picked, ensure_ascii=False)


def _impl__cart_payload(detail_payload: Dict[str, Any]) -> Dict[str, Any]:
    data = _data_object(detail_payload)
    goods_info = data.get("goodsInfo", {})
    stock, stock_parent = _first_stock(detail_payload)
    price_ranges = goods_info.get("priceRanges") or []
    first_price = price_ranges[0] if isinstance(price_ranges, list) and price_ranges else {}
    images = data.get("images") or []
    price = stock.get("price") or first_price.get("priceMin") or first_price.get("priceMax") or "0"
    return {
        "to_cart[0][goods_id]": data.get("goodsId") or "",
        "to_cart[0][goods_title]": data.get("titleC") or data.get("titleT") or "",
        "to_cart[0][price]": price,
        "to_cart[0][num]": 1,
        "to_cart[0][pic]": images[0] if isinstance(images, list) and images else "",
        "to_cart[0][detail]": _detail_specs(detail_payload, stock_parent),
        "to_cart[0][sku_id]": stock.get("skuId") or "",
        "to_cart[0][spec_id]": stock.get("specId") or "",
        "to_cart[0][shop_id]": data.get("shopId") or "",
        "to_cart[0][shop_name]": data.get("shopName") or "",
        "to_cart[0][from_platform]": data.get("fromPlatform") or "",
        "to_cart[0][price_ranges]": json.dumps(price_ranges, ensure_ascii=False),
    }


def _impl__auth_headers(user_token: str) -> Dict[str, str]:
    if not user_token:
        return {}
    return {
        "Authorization": f"Bearer {user_token}",
        "userToken": user_token,
        "UserToken": user_token,
        "User-Token": user_token,
        "ClientToken": user_token,
        "gkToken": user_token,
        "token": user_token,
        "X-Requested-With": "XMLHttpRequest",
        "Lang": "zh-CN",
    }


def _impl__auth_form_fields(user_token: str, login_payload: Dict[str, Any], client_tool: str) -> Dict[str, Any]:
    if not user_token:
        return {}
    user_info = _data_object(login_payload).get("userInfo")
    user_info = user_info if isinstance(user_info, dict) else {}
    fields: Dict[str, Any] = {
        "userToken": user_token,
        "token": user_token,
        "ClientToken": user_token,
        "client_tool": client_tool,
    }
    for key in ["token_id", "operation_id", "y_id"]:
        if user_info.get(key) not in (None, ""):
            fields[key] = user_info.get(key)
    return fields


def _impl__duration_ms(started_at: Any, finished_at: datetime) -> int | None:
    if not isinstance(started_at, datetime):
        return None
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _impl__finish_named(script_name: str, log: Dict[str, Any], passed: bool, summary: Dict[str, Any]) -> Tuple[bool, str, str, Dict[str, Any]]:
    finished_at = datetime.now()
    duration_ms = _duration_ms(log.get("started_at"), finished_at)
    if duration_ms is not None:
        summary.setdefault("duration_ms", duration_ms)
        log["duration_ms"] = duration_ms
    log["summary"] = summary
    log["finished_at"] = finished_at
    log_text = json.dumps(log, ensure_ascii=False, indent=2, default=str)
    report_path = write_allure_result(script_name, "data_script", passed, log_text, started_at=log.get("started_at"), finished_at=finished_at)
    return passed, log_text, report_path, summary


def _impl__finish(log: Dict[str, Any], passed: bool, summary: Dict[str, Any]) -> Tuple[bool, str, str, Dict[str, Any]]:
    return _finish_named(SCRIPT_NAME, log, passed, summary)


def _impl__stop_after_node(variables: Dict[str, Any]) -> str:
    return str(variables.get("stop_after_node") or variables.get("pause_after_node") or "").strip()


def _impl__checkpoint_requested(variables: Dict[str, Any], node: str) -> bool:
    stop_after = _stop_after_node(variables)
    return bool(stop_after and stop_after != FULL_FLOW_COMPLETE_NODE and stop_after == node)


def _impl__paused_summary(node: str, summary: Dict[str, Any] | None = None) -> Dict[str, Any]:
    paused = dict(summary or {})
    paused.update(
        {
            "paused": True,
            "stopped_after_node": node,
            "current_node": node,
            "node_label": FULL_FLOW_NODE_LABELS.get(node, node),
        }
    )
    return paused


def _impl__is_paused(summary: Dict[str, Any] | None) -> bool:
    return bool(isinstance(summary, dict) and summary.get("paused"))


_runtime_from_variables = _compat_wrapper(_impl__runtime_from_variables)
_admin_session_from = _compat_wrapper(_impl__admin_session_from)
_client_login_inputs = _compat_wrapper(_impl__client_login_inputs)
_as_list = _compat_wrapper(_impl__as_list)
_unique_list = _compat_wrapper(_impl__unique_list)
_as_int = _compat_wrapper(_impl__as_int)
_clean_multipart_headers = _compat_wrapper(_impl__clean_multipart_headers)
_post_form = _compat_wrapper(_impl__post_form)
_response_json = _compat_wrapper(_impl__response_json)
_response_brief = _compat_wrapper(_impl__response_brief)
_extract_token = _compat_wrapper(_impl__extract_token)
_data_object = _compat_wrapper(_impl__data_object)
_goods_items = _compat_wrapper(_impl__goods_items)
_first_stock = _compat_wrapper(_impl__first_stock)
_detail_specs = _compat_wrapper(_impl__detail_specs)
_cart_payload = _compat_wrapper(_impl__cart_payload)
_auth_headers = _compat_wrapper(_impl__auth_headers)
_auth_form_fields = _compat_wrapper(_impl__auth_form_fields)
_duration_ms = _compat_wrapper(_impl__duration_ms)
_finish_named = _compat_wrapper(_impl__finish_named)
_finish = _compat_wrapper(_impl__finish)
_stop_after_node = _compat_wrapper(_impl__stop_after_node)
_checkpoint_requested = _compat_wrapper(_impl__checkpoint_requested)
_paused_summary = _compat_wrapper(_impl__paused_summary)
_is_paused = _compat_wrapper(_impl__is_paused)
