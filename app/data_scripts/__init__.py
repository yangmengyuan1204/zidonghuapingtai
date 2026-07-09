import copy
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import random
import threading
import time
from typing import Any, Dict, Tuple
from urllib.parse import urljoin

import requests

from ..executors import ensure_report_dirs, write_allure_result
from ..models import Env
from ..vendor import piliangtianjiagouwuche as bulk_cart
from ..oem_scripts.material_order import run_material_order_script  # noqa: E402



SCRIPT_NAME = "\u5546\u54c1\u8d2d\u7269\u8f66"
ORDER_SCRIPT_NAME = "\u8ba2\u5355\u62a5\u4ef7"
BALANCE_PAYMENT_SCRIPT_NAME = "\u4f59\u989d\u652f\u4ed8"
BANK_PAYMENT_SCRIPT_NAME = "\u94f6\u884c\u652f\u4ed8"
PURCHASE_TO_SHELF_SCRIPT_NAME = "\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6"
WAREHOUSE_DELIVERY_SCRIPT_NAME = "\u4ed3\u5e93\u63d0\u51fa\u914d\u9001\u5355"
POORDER_BALANCE_PAYMENT_SCRIPT_NAME = "\u914d\u9001\u5355\u4f59\u989d\u4ed8\u6b3e"
POORDER_BANK_PAYMENT_SCRIPT_NAME = "\u914d\u9001\u5355\u94f6\u884c\u4ed8\u6b3e"
BALANCE_RECHARGE_SCRIPT_NAME = "\u4f59\u989d\u5145\u503c"
FULL_FLOW_SCRIPT_NAME = "\u5168\u6d41\u7a0b\u5b8c\u5168\u4f53"
FULL_FLOW_PART_PAY_SCRIPT_NAME = "全流程加入分批付款"
DIRECT_BOX_TO_SHELF_SCRIPT_NAME = "\u76f4\u63a5\u88c5\u7bb1\u4e0a\u67b6"
RESUME_ORDER_FLOW_SCRIPT_NAME = "输入订单号继续执行操作"
RESUME_PORDER_FLOW_SCRIPT_NAME = "输入配送单号继续执行操作"
FULL_FLOW_COMPLETE_NODE = "full_complete"
FULL_FLOW_NODE_LABELS = {
    "shopping_cart": "\u5546\u54c1\u52a0\u8d2d\u5b8c\u6210",
    "order_created": "\u524d\u53f0\u63d0\u4ea4\u8ba2\u5355\u5b8c\u6210",
    "order_translated": "\u540e\u53f0\u8ba2\u5355\u7ffb\u8bd1\u5b8c\u6210",
    "order_confirmed": "\u540e\u53f0\u8ba2\u5355\u786e\u8ba4\u5b8c\u6210",
    "order_offered": "\u540e\u53f0\u8ba2\u5355\u62a5\u4ef7\u5b8c\u6210",
    "order_paid": "\u8ba2\u5355\u652f\u4ed8\u5b8c\u6210",
    "pending_purchase": "\u8ba2\u5355\u8fdb\u5165\u5f85\u62cd\u4e0b",
    "purchase_no_saved": "\u4fdd\u5b58\u4ea4\u6613\u53f7\u5b8c\u6210",
    "purchase_wait_modify_price": "\u6807\u8bb0\u5f85\u6539\u4ef7\u5b8c\u6210",
    "purchase_wait_pay": "\u63d0\u4ea4\u5f85\u8d22\u52a1\u4ed8\u6b3e\u5b8c\u6210",
    "purchase_paid": "\u4ea4\u6613\u53f7\u4ed8\u6b3e\u5b8c\u6210",
    "checking_started": "\u5f00\u59cb\u6838\u67e5\u5b8c\u6210",
    "shelf_stored": "\u6838\u67e5\u4e0a\u67b6\u5165\u5e93\u5b8c\u6210",
    "warehouse_delivery_created": "\u4ed3\u5e93\u63d0\u51fa\u914d\u9001\u5355\u5b8c\u6210",
    "porder_translated": "\u914d\u9001\u5355\u5f85\u7ffb\u8bd1\u5b8c\u6210",
    "porder_confirmed": "\u914d\u9001\u5355\u786e\u8ba4\u6d41\u8f6c\u5b8c\u6210",
    "porder_wait_offer": "\u914d\u9001\u5355\u8fdb\u5165\u5f85\u62a5\u4ef7\u5b8c\u6210",
    "porder_offered": "\u914d\u9001\u5355\u62a5\u4ef7\u5b8c\u6210",
    "porder_paid": "\u914d\u9001\u5355\u652f\u4ed8\u5b8c\u6210",
    FULL_FLOW_COMPLETE_NODE: "\u5168\u6d41\u7a0b\u7ed3\u675f",
}
FULL_FLOW_NODE_SEQUENCE = [
    "shopping_cart",
    "order_created",
    "order_translated",
    "order_confirmed",
    "order_offered",
    "order_paid",
    "pending_purchase",
    "purchase_no_saved",
    "purchase_wait_modify_price",
    "purchase_wait_pay",
    "purchase_paid",
    "checking_started",
    "shelf_stored",
    "warehouse_delivery_created",
    "porder_translated",
    "porder_confirmed",
    "porder_wait_offer",
    "porder_offered",
    "porder_paid",
    FULL_FLOW_COMPLETE_NODE,
]
KEYWORDS = [
    "\u8863\u670d",
    "\u978b\u5b50",
    "\u978b",
    "usp",
    "USP",
    "\u5305",
    "\u5e3d\u5b50",
    "\u88d9\u5b50",
    "\u8033\u73af",
    "\u889c\u5b50",
    "\u624b\u673a\u58f3",
    "\u624b\u8868",
    "\u9879\u94fe",
    "\u6c34\u676f",
    "\u6587\u5177",
    "\u6536\u7eb3",
]
PREFERRED_KEYWORDS = ["衣服", "鞋子", "鞋", "包"]
SHOP_TYPES = ["1688", "taobao", "tmall", "rakumart"]
SHOP_TYPE_ALIASES = {}
MAX_LOG_BODY = 1200
REQUEST_RETRIES = 2
REQUEST_RETRY_DELAY = 0.8
ORDER_OPTION_NAME_FALLBACKS = {
    "1": "FBA贴标",
    "3": "更换OPP袋子",
    "4": "取布标",
    "5": "缝布标",
    "fba_label": "FBA贴标",
    "detail_inspection": "详细检品(单价)",
    "opp_bag": "更换OPP袋子",
    "remove_cloth_label": "取布标",
    "sew_cloth_label": "缝布标",
    "FBA贴标": "FBA贴标",
    "详细检品(单价)": "详细检品(单价)",
    "更换OPP袋子": "更换OPP袋子",
    "取布标": "取布标",
    "缝布标": "缝布标",
}


class DataScriptRuntime:
    def __init__(self) -> None:
        self._client_cache: Dict[tuple[Any, ...], tuple[Any, str]] = {}
        self._admin_token_cache: Dict[tuple[Any, ...], tuple[Dict[str, Any], str]] = {}
        self._admin_session: requests.Session | None = None

    def admin_session(self) -> requests.Session:
        """返回可复用的 admin requests.Session，在链式调用中保持 TCP 连接复用"""
        if self._admin_session is None:
            self._admin_session = requests.Session()
        return self._admin_session

    def client(
        self,
        env: Env,
        variables: Dict[str, Any],
        *,
        log: Dict[str, Any] | None = None,
        retry_login: bool = True,
    ) -> tuple[Any, str, int, str, bool]:
        account, password, client_tool = _client_login_inputs(variables)
        timeout = _as_int(variables.get("timeout"), env.timeout or 25)
        base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
        key = (base_url, timeout, account, password, client_tool)
        cached = key in self._client_cache
        if cached:
            client, token = self._client_cache[key]
            _configure_client_api_paths(client, variables)
        else:
            client = bulk_cart.RakumartClient(base_url, timeout)
            _configure_client_api_paths(client, variables)
            login = lambda: client.login(account, password, client_tool)
            token = _call_with_retry("client login", login) if retry_login else login()
            self._client_cache[key] = (client, str(token))
        if log is not None:
            log["login"] = {
                "success": True,
                "account": account,
                "client_tool": client_tool,
                "token_extracted": bool(token),
                "cached": cached,
            }
        return client, base_url, timeout, str(token), cached

    def admin_login(
        self,
        session: requests.Session,
        base_url: str,
        variables: Dict[str, Any],
        timeout: int,
    ) -> tuple[Dict[str, Any], str, bool]:
        key = (
            base_url.rstrip("/"),
            timeout,
            str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
            str(variables.get("backend_password") or "raku@123456``"),
            str(variables.get("backend_system") or "1"),
            str(variables.get("backend_compute_token") or ""),
            str(variables.get("backend_code") or "wnm666"),
        )
        cached = key in self._admin_token_cache
        if cached:
            payload, token = self._admin_token_cache[key]
        else:
            payload, token = _admin_login_without_runtime(session, base_url, variables, timeout)
            if token:
                self._admin_token_cache[key] = (payload, token)
        if token:
            session.headers.update(_admin_headers(token))
        return payload, token, cached


def _runtime_from_variables(variables: Dict[str, Any]) -> DataScriptRuntime | None:
    runtime = variables.get("_runtime")
    return runtime if isinstance(runtime, DataScriptRuntime) else None


def _admin_session_from(variables: Dict[str, Any]) -> requests.Session:
    """从 runtime 获取共享 session（如可用），否则新建一个"""
    runtime = _runtime_from_variables(variables)
    if runtime is not None:
        return runtime.admin_session()
    return requests.Session()


def _client_login_inputs(variables: Dict[str, Any]) -> tuple[str, str, str]:
    account = str(variables.get("account") or "").strip()
    password = str(variables.get("password") or "").strip()
    client_tool = str(variables.get("client_tool") or "1").strip()
    if client_tool == "2" and not _as_bool(variables.get("allow_h5_client_tool"), False):
        client_tool = "1"
    return account, password, client_tool


def _as_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or fallback
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return fallback


def _unique_list(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        text = str(item).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _as_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _clean_multipart_headers(headers: Dict[str, Any]) -> Dict[str, str]:
    request_headers = {str(key): str(value) for key, value in (headers or {}).items() if value is not None}
    for key in list(request_headers.keys()):
        if key.lower() == "content-type" and "multipart/form-data" in request_headers[key].lower():
            request_headers.pop(key, None)
    return request_headers


def _post_form(
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


def _response_json(response: requests.Response) -> Dict[str, Any]:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _response_brief(response: requests.Response, payload: Dict[str, Any] | None = None, include_body: bool = False) -> Dict[str, Any]:
    payload = payload if payload is not None else _response_json(response)
    brief: Dict[str, Any] = {"status_code": response.status_code}
    for key in ["success", "code", "msg"]:
        if key in payload:
            brief[key] = payload.get(key)
    if include_body:
        brief["body"] = response.text[:MAX_LOG_BODY]
    return brief


def _extract_token(payload: Dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ["userToken", "token", "access_token"]:
            if data.get(key):
                return str(data[key])
    for key in ["userToken", "token", "access_token"]:
        if payload.get(key):
            return str(payload[key])
    return ""


def _data_object(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _goods_items(search_payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    result = _data_object(search_payload).get("result", {}).get("result", [])
    return result if isinstance(result, list) else []


def _first_stock(detail_payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
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


def _detail_specs(detail_payload: Dict[str, Any], stock_parent: Dict[str, Any]) -> str:
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


def _cart_payload(detail_payload: Dict[str, Any]) -> Dict[str, Any]:
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


def _auth_headers(user_token: str) -> Dict[str, str]:
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


def _auth_form_fields(user_token: str, login_payload: Dict[str, Any], client_tool: str) -> Dict[str, Any]:
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


def _duration_ms(started_at: Any, finished_at: datetime) -> int | None:
    if not isinstance(started_at, datetime):
        return None
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _finish_named(script_name: str, log: Dict[str, Any], passed: bool, summary: Dict[str, Any]) -> Tuple[bool, str, str, Dict[str, Any]]:
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


def _finish(log: Dict[str, Any], passed: bool, summary: Dict[str, Any]) -> Tuple[bool, str, str, Dict[str, Any]]:
    return _finish_named(SCRIPT_NAME, log, passed, summary)


def _stop_after_node(variables: Dict[str, Any]) -> str:
    return str(variables.get("stop_after_node") or variables.get("pause_after_node") or "").strip()


def _checkpoint_requested(variables: Dict[str, Any], node: str) -> bool:
    stop_after = _stop_after_node(variables)
    return bool(stop_after and stop_after != FULL_FLOW_COMPLETE_NODE and stop_after == node)


def _paused_summary(node: str, summary: Dict[str, Any] | None = None) -> Dict[str, Any]:
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


def _is_paused(summary: Dict[str, Any] | None) -> bool:
    return bool(isinstance(summary, dict) and summary.get("paused"))


def _finish_paused(
    script_name: str,
    log: Dict[str, Any],
    node: str,
    summary: Dict[str, Any] | None = None,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    paused = _paused_summary(node, summary)
    log["paused"] = paused
    return _finish_named(script_name, log, True, paused)


def _legacy_run_shopping_cart_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = env.timeout or 30
    configured_keywords = _as_list(variables.get("keywords") or variables.get("keyword_pool"), KEYWORDS)
    keyword_pool = _unique_list(configured_keywords + KEYWORDS)
    preferred_keywords = _unique_list(_as_list(variables.get("preferred_keywords"), PREFERRED_KEYWORDS))
    configured_keyword = str(variables.get("keyword") or "").strip()
    random_keyword = variables.get("random_keyword", True) is not False
    if configured_keyword:
        keyword_pool = _unique_list([configured_keyword] + keyword_pool)
    shuffled_pool = random.sample(keyword_pool, len(keyword_pool)) if keyword_pool else []
    if configured_keyword and not random_keyword:
        keyword = configured_keyword
        keyword_candidates = _unique_list([configured_keyword] + preferred_keywords + shuffled_pool)
    else:
        keyword = configured_keyword or (shuffled_pool[0] if shuffled_pool else "")
        keyword_candidates = _unique_list([keyword] + preferred_keywords + shuffled_pool)
    shop_types = _as_list(variables.get("shop_types"), SHOP_TYPES)
    per_shop = _as_int(variables.get("per_shop"), 5)
    candidate_limit = _as_int(variables.get("candidate_limit"), max(12, per_shop * 3))
    candidate_limit = max(per_shop, candidate_limit)
    candidate_target = _as_int(variables.get("candidate_target"), max(per_shop, min(candidate_limit, per_shop * 2)))
    candidate_target = max(per_shop, min(candidate_target, candidate_limit))
    keyword_max_rounds = _as_int(variables.get("keyword_max_rounds"), min(6, len(keyword_candidates) or 1))
    keyword_max_rounds = min(max(1, keyword_max_rounds), len(keyword_candidates) or 1)
    empty_search_stop = _as_int(variables.get("empty_search_stop"), 6)
    boost_keywords = _unique_list(_as_list(variables.get("boost_keywords"), ["衣服", "鞋子", "包"]))
    strict_shop_count = bool(variables.get("strict_shop_count") or variables.get("strict"))
    account = str(variables.get("account") or "").strip()
    password = str(variables.get("password") or "").strip()
    client_tool = str(variables.get("client_tool") or "2").strip()

    log: Dict[str, Any] = {
        "script": SCRIPT_NAME,
        "keyword": keyword,
        "keyword_candidates": keyword_candidates,
        "preferred_keywords": preferred_keywords,
        "shop_types": shop_types,
        "per_shop": per_shop,
        "candidate_limit": candidate_limit,
        "candidate_target": candidate_target,
        "keyword_max_rounds": keyword_max_rounds,
        "empty_search_stop": empty_search_stop,
        "boost_keywords": boost_keywords,
        "started_at": datetime.now(),
        "shops": [],
    }

    session = _admin_session_from(variables)
    headers: Dict[str, str] = {}

    try:
        login_response = _post_form(
            session,
            env.base_url,
            "/mobile/userLogin",
            {"account": account, "password": password, "client_tool": client_tool},
            headers,
            timeout,
        )
        login_payload = _response_json(login_response)
        user_token = _extract_token(login_payload)
        if user_token:
            headers.update(_auth_headers(user_token))
        cart_auth_fields = _auth_form_fields(user_token, login_payload, client_tool)
        log["login"] = {
            **_response_brief(login_response, login_payload, include_body=True),
            "account": account,
            "token_extracted": bool(user_token),
        }

        if login_payload.get("success") is not True or not user_token:
            reason = login_payload.get("msg") or "\u767b\u5f55\u672a\u8fd4\u56de token"
            return _finish(
                log,
                False,
                {
                    "keyword": keyword,
                    "expected_total": len(shop_types) * per_shop,
                    "added_total": 0,
                    "shop_types": shop_types,
                    "reason": f"\u767b\u5f55\u5931\u8d25: {reason}",
                },
            )

        added_total = 0
        expected_total = len(shop_types) * per_shop
        for shop_type in shop_types:
            shop_log: Dict[str, Any] = {"shop_type": shop_type, "added": [], "errors": [], "searches": []}
            collected: list[Dict[str, Any]] = []
            seen_goods = set()
            aliases = SHOP_TYPE_ALIASES.get(shop_type, [shop_type])
            searched_keywords = set()
            empty_search_streak = 0
            break_reason = ""

            for current_keyword in keyword_candidates[:keyword_max_rounds]:
                searched_keywords.add(current_keyword)
                keyword_has_result = False
                for search_shop_type in aliases:
                    search_response = _post_form(
                        session,
                        env.base_url,
                        "/mobile/searchGoods",
                        {
                            "keywords": current_keyword,
                            "shop_type": search_shop_type,
                            "page": 1,
                            "pageSize": candidate_limit,
                        },
                        headers,
                        timeout,
                    )
                    search_payload = _response_json(search_response)
                    items = _goods_items(search_payload)
                    if items:
                        keyword_has_result = True
                    shop_log["searches"].append(
                        {
                            "keyword": current_keyword,
                            "shop_type": search_shop_type,
                            **_response_brief(search_response, search_payload),
                            "count": len(items),
                        }
                    )
                    for goods in items:
                        goods_id = goods.get("goodsId")
                        if goods_id and goods_id not in seen_goods:
                            seen_goods.add(goods_id)
                            collected.append(goods)
                    if len(collected) >= candidate_target:
                        break
                if keyword_has_result:
                    empty_search_streak = 0
                else:
                    empty_search_streak += 1
                if len(collected) >= candidate_target:
                    break_reason = "candidate_target_reached"
                    break
                if empty_search_streak >= empty_search_stop:
                    break_reason = "empty_search_stop"
                    break

            if 0 < len(collected) < per_shop:
                for boost_keyword in boost_keywords:
                    if boost_keyword in searched_keywords:
                        continue
                    searched_keywords.add(boost_keyword)
                    for search_shop_type in aliases:
                        search_response = _post_form(
                            session,
                            env.base_url,
                            "/mobile/searchGoods",
                            {
                                "keywords": boost_keyword,
                                "shop_type": search_shop_type,
                                "page": 1,
                                "pageSize": candidate_limit,
                            },
                            headers,
                            timeout,
                        )
                        search_payload = _response_json(search_response)
                        items = _goods_items(search_payload)
                        shop_log["searches"].append(
                            {
                                "keyword": boost_keyword,
                                "shop_type": search_shop_type,
                                "phase": "boost",
                                **_response_brief(search_response, search_payload),
                                "count": len(items),
                            }
                        )
                        for goods in items:
                            goods_id = goods.get("goodsId")
                            if goods_id and goods_id not in seen_goods:
                                seen_goods.add(goods_id)
                                collected.append(goods)
                        if len(collected) >= candidate_target:
                            break_reason = "candidate_target_reached_in_boost"
                            break
                    if len(collected) >= candidate_target or len(collected) >= per_shop:
                        if not break_reason:
                            break_reason = "enough_candidates_in_boost"
                        break

            if len(collected) > candidate_limit:
                collected = collected[:candidate_limit]
            candidate_status = "partial_candidates"
            if len(collected) == 0:
                candidate_status = "no_results"
            elif len(collected) >= per_shop:
                candidate_status = "enough_candidates"
            if not break_reason:
                if len(collected) == 0:
                    break_reason = "search_exhausted_no_results"
                elif len(collected) >= per_shop:
                    break_reason = "search_exhausted_enough_candidates"
                else:
                    break_reason = "search_exhausted_partial_candidates"

            shop_log["search"] = {
                "status_code": shop_log["searches"][-1]["status_code"] if shop_log["searches"] else None,
                "count": len(collected),
                "candidate_limit": candidate_limit,
                "candidate_target": candidate_target,
                "keyword_max_rounds": keyword_max_rounds,
                "empty_search_stop": empty_search_stop,
                "search_calls": len(shop_log["searches"]),
                "break_reason": break_reason,
                "candidate_status": candidate_status,
            }
            shop_success_count = 0
            for goods in collected:
                if shop_success_count >= per_shop:
                    break
                goods_id = goods.get("goodsId")
                goods_shop_type = goods.get("shopType") or shop_type
                if not goods_id:
                    continue
                try:
                    detail_response = _post_form(
                        session,
                        env.base_url,
                        "/mobile/goodsParticulars",
                        {"shop_type": goods_shop_type, "goods_id": goods_id},
                        headers,
                        timeout,
                    )
                    detail_payload = _response_json(detail_response)
                    if detail_payload.get("success") is not True or not isinstance(detail_payload.get("data"), dict):
                        shop_log["errors"].append(
                            {
                                "goods_id": goods_id,
                                "error": "\u5546\u54c1\u8be6\u60c5\u63a5\u53e3\u672a\u8fd4\u56de\u53ef\u52a0\u8d2d\u7684\u5546\u54c1\u6570\u636e",
                                "detail": _response_brief(detail_response, detail_payload, include_body=True),
                            }
                        )
                        continue
                    cart_data = _cart_payload(detail_payload)
                    if not cart_data.get("to_cart[0][sku_id]") or not cart_data.get("to_cart[0][goods_id]"):
                        shop_log["errors"].append({"goods_id": goods_id, "error": "\u5546\u54c1\u8be6\u60c5\u672a\u627e\u5230\u53ef\u7528\u5e93\u5b58/SKU"})
                        continue

                    cart_response = _post_form(session, env.base_url, "/mobile/cart.goodsToCart", {**cart_data, **cart_auth_fields}, headers, timeout)
                    cart_payload = _response_json(cart_response)
                    ok = cart_response.status_code == 200 and cart_payload.get("success") is True
                    if ok:
                        added_total += 1
                        shop_success_count += 1
                    shop_log["added"].append(
                        {
                            "goods_id": goods_id,
                            "shop_type": goods_shop_type,
                            "detail": _response_brief(detail_response, detail_payload),
                            "cart": _response_brief(cart_response, cart_payload, include_body=not ok),
                            "success": ok,
                        }
                    )
                except Exception as exc:
                    shop_log["errors"].append({"goods_id": goods_id, "error": str(exc)})
            log["shops"].append(shop_log)

        available_shop_count = 0
        skipped_shop_types = []
        failed_shop_types = []
        for shop in log["shops"]:
            search_count = (shop.get("search") or {}).get("count") or 0
            success_count = len([item for item in shop.get("added", []) if item.get("success")])
            if search_count <= 0:
                skipped_shop_types.append(shop.get("shop_type"))
            else:
                available_shop_count += 1
                if success_count < per_shop:
                    failed_shop_types.append(shop.get("shop_type"))

        available_expected_total = available_shop_count * per_shop
        passed = added_total >= (expected_total if strict_shop_count else available_expected_total) and added_total > 0 and not failed_shop_types
        summary = {
            "keyword": keyword,
            "expected_total": expected_total,
            "available_expected_total": available_expected_total,
            "added_total": added_total,
            "shop_types": shop_types,
            "skipped_shop_types": skipped_shop_types,
            "failed_shop_types": failed_shop_types,
            "strict_shop_count": strict_shop_count,
        }
        if not passed:
            if failed_shop_types:
                summary["reason"] = "\u6709\u5546\u54c1\u6570\u636e\u7684\u5e97\u94fa\u672a\u52a0\u8d2d\u5230\u8981\u6c42\u6570\u91cf"
            elif strict_shop_count:
                summary["reason"] = "\u4e25\u683c\u6a21\u5f0f\u4e0b\uff0c\u6709\u5e97\u94fa\u672a\u641c\u7d22\u5230\u5546\u54c1"
            else:
                summary["reason"] = "\u672a\u52a0\u8d2d\u5230\u6709\u6548\u5546\u54c1"
        return _finish(log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish(log, False, {"keyword": keyword, "added_total": 0, "error": str(exc)})


def _as_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
        return parsed if parsed >= 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: Any, fallback: bool = False) -> bool:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _quantity_cycle(value: Any) -> list[int]:
    if isinstance(value, list):
        values = value
    else:
        values = str(value or "2,3,5").split(",")
    quantities = []
    for item in values:
        try:
            parsed = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            quantities.append(parsed)
    return quantities or [1]


def _item_brief(item: Any) -> Dict[str, Any]:
    data = item.to_dict() if hasattr(item, "to_dict") else dict(item) if isinstance(item, dict) else {}
    return {
        "goods_id": data.get("goods_id"),
        "shop_id": data.get("shop_id"),
        "shop_name": data.get("shop_name"),
        "sku_id": data.get("sku_id"),
        "spec_id": data.get("spec_id"),
        "num": data.get("num"),
        "price": data.get("price"),
        "from_platform": data.get("from_platform"),
    }


def _cart_text(data: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _cart_item_matches(expected: Dict[str, Any], actual: Dict[str, Any]) -> bool:
    expected_goods = _cart_text(expected, "goods_id", "goodsId")
    actual_goods = _cart_text(actual, "goods_id", "goodsId")
    if not expected_goods or expected_goods != actual_goods:
        return False
    for key_pair in [("sku_id", "skuId"), ("spec_id", "specId")]:
        expected_value = _cart_text(expected, *key_pair)
        actual_value = _cart_text(actual, *key_pair)
        if expected_value and actual_value and expected_value != actual_value:
            return False
    return True


def _verify_cart_contains_items(cart_payload: Dict[str, Any], items: list[Any]) -> Dict[str, Any]:
    cart_goods = _flatten_cart_goods(cart_payload)
    used_indices: set[int] = set()
    missing: list[Dict[str, Any]] = []
    matched = 0
    for item in items:
        expected = item.to_dict() if hasattr(item, "to_dict") else dict(item) if isinstance(item, dict) else {}
        match_index = None
        for index, actual in enumerate(cart_goods):
            if index in used_indices:
                continue
            if _cart_item_matches(expected, actual):
                match_index = index
                break
        if match_index is None:
            missing.append(_item_brief(expected))
        else:
            used_indices.add(match_index)
            matched += 1
    return {
        "cart_goods_count": len(cart_goods),
        "expected_count": len(items),
        "matched_count": matched,
        "missing_count": len(missing),
        "missing_items": missing[:10],
    }


def run_shopping_cart_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})

    account = str(variables.get("account") or "").strip()
    password = str(variables.get("password") or "").strip()
    client_tool = str(variables.get("client_tool") or "1").strip()
    if client_tool == "2" and not _as_bool(variables.get("allow_h5_client_tool"), False):
        client_tool = "1"
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")

    keywords = _as_list(variables.get("keywords") or variables.get("keyword_pool"), KEYWORDS)
    keyword = str(variables.get("keyword") or "").strip() or random.choice(keywords)
    shop_types = _as_list(variables.get("shop_types"), ["1688"])
    shop_type = str(variables.get("shop_type") or shop_types[0] or "1688").strip()
    per_shop = _as_int(variables.get("per_shop"), 5)
    target_shops = _as_int(variables.get("target_shops") or variables.get("shop_count"), max(1, len(shop_types)))
    page_size = _as_int(variables.get("page_size") or variables.get("candidate_limit"), 50)
    max_pages = _as_int(variables.get("max_pages"), 10)
    batch_size = _as_int(variables.get("batch_size"), 30)
    sleep_seconds = _as_float(variables.get("sleep"), 0.2)
    detail_workers = _as_int(variables.get("detail_workers"), 8)
    quantities = _quantity_cycle(variables.get("quantities"))
    allow_fallback_sku = not _as_bool(variables.get("no_fallback_sku"), False)
    strict_shop_count = _as_bool(variables.get("strict_shop_count") or variables.get("strict"), False)
    verify_cart_after_add = _as_bool(variables.get("verify_cart_after_add"), True)
    cart_verify_mode = str(variables.get("cart_verify_mode") or "batch").strip().lower()
    if cart_verify_mode not in {"batch", "final"}:
        cart_verify_mode = "batch"
    cart_list_price_cut = str(variables.get("priceCut") or variables.get("price_cut") or "0")

    log: Dict[str, Any] = {
        "script": SCRIPT_NAME,
        "mode": "vendored_piliangtianjiagouwuche",
        "source": "app/vendor/piliangtianjiagouwuche.py",
        "base_url": base_url,
        "keyword": keyword,
        "shop_type": shop_type,
        "target_shops": target_shops,
        "per_shop": per_shop,
        "page_size": page_size,
        "max_pages": max_pages,
        "batch_size": batch_size,
        "detail_workers": detail_workers,
        "quantities": quantities,
        "allow_fallback_sku": allow_fallback_sku,
        "verify_cart_after_add": verify_cart_after_add,
        "cart_verify_mode": cart_verify_mode,
        "started_at": datetime.now(),
        "shops": [],
        "batches": [],
    }

    try:
        runtime = _runtime_from_variables(variables)
        if runtime:
            client, _base_url, _timeout, token, _cached = runtime.client(env, variables, log=log, retry_login=False)
        else:
            client = bulk_cart.RakumartClient(base_url, timeout)
            _configure_client_api_paths(client, variables)
            token = client.login(account, password, client_tool)
            log["login"] = {"success": True, "account": account, "client_tool": client_tool, "token_extracted": bool(token)}

        def collect_cart_items(keyword_value: str, shop_type_value: str) -> tuple[Dict[str, list[Dict[str, Any]]], list[Dict[str, Any]], int]:
            collected_shops = bulk_cart.collect_items(
                client=client,
                keyword=keyword_value,
                shop_type=shop_type_value,
                target_shops=target_shops,
                per_shop=per_shop,
                page_size=page_size,
                max_pages=max_pages,
                sleep_seconds=sleep_seconds,
                quantity_cycle=quantities,
                allow_fallback_sku=allow_fallback_sku,
                detail_workers=max(1, detail_workers),
            )
            collected_items = bulk_cart.flatten_ready_shops(collected_shops, target_shops, per_shop)
            collected_ready_shops = len(collected_items) // per_shop if per_shop else 0
            return collected_shops, collected_items, collected_ready_shops

        shops, items, ready_shops = collect_cart_items(keyword, shop_type)
        expected_total = target_shops * per_shop
        collection_attempts = [
            {
                "keyword": keyword,
                "shop_type": shop_type,
                "ready_shops": ready_shops,
                "collected_shops": len(shops),
                "selected_items": len(items),
            }
        ]
        # 兜底1：当前 shop_type 收集为空且非 1688 时，自动尝试 1688（可通过 auto_fallback_shop_type=False 关闭）
        if not items and shop_type != "1688" and _as_bool(variables.get("auto_fallback_shop_type"), True):
            fb_shops, fb_items, fb_ready = collect_cart_items(keyword, "1688")
            collection_attempts.append(
                {
                    "keyword": keyword,
                    "shop_type": "1688",
                    "ready_shops": fb_ready,
                    "collected_shops": len(fb_shops),
                    "selected_items": len(fb_items),
                    "fallback": True,
                    "fallback_reason": "shop_type_empty",
                }
            )
            if fb_items:
                log["fallback_collection"] = {
                    "from": {"keyword": keyword, "shop_type": shop_type},
                    "to": {"keyword": keyword, "shop_type": "1688"},
                }
                shop_type = "1688"
                shops = fb_shops
                items = fb_items
                ready_shops = fb_ready
                log["shop_type"] = shop_type
        if not items and _as_bool(variables.get("auto_fill_cart_on_shortage"), False):
            fallback_keywords = _unique_list(_as_list(variables.get("fallback_keywords"), PREFERRED_KEYWORDS) + PREFERRED_KEYWORDS + KEYWORDS)
            fallback_keyword_rounds = _as_int(
                variables.get("fallback_keyword_max_rounds") or variables.get("keyword_max_rounds"),
                min(6, len(fallback_keywords) or 1),
            )
            fallback_keywords = fallback_keywords[: max(1, min(fallback_keyword_rounds, len(fallback_keywords) or 1))]
            fallback_shop_types = _unique_list(_as_list(variables.get("fallback_shop_types"), ["1688"]) + ["1688"])
            fallback_used = False
            for fallback_shop_type in fallback_shop_types:
                for fallback_keyword in fallback_keywords:
                    if fallback_keyword == keyword and fallback_shop_type == shop_type:
                        continue
                    fallback_shops, fallback_items, fallback_ready_shops = collect_cart_items(fallback_keyword, fallback_shop_type)
                    collection_attempts.append(
                        {
                            "keyword": fallback_keyword,
                            "shop_type": fallback_shop_type,
                            "ready_shops": fallback_ready_shops,
                            "collected_shops": len(fallback_shops),
                            "selected_items": len(fallback_items),
                            "fallback": True,
                        }
                    )
                    if fallback_items:
                        log["fallback_collection"] = {
                            "from": {"keyword": keyword, "shop_type": shop_type},
                            "to": {"keyword": fallback_keyword, "shop_type": fallback_shop_type},
                        }
                        keyword = fallback_keyword
                        shop_type = fallback_shop_type
                        shops = fallback_shops
                        items = fallback_items
                        ready_shops = fallback_ready_shops
                        fallback_used = True
                        break
                if fallback_used:
                    break
            log["keyword"] = keyword
            log["shop_type"] = shop_type

        for index, (shop_key, shop_items) in enumerate(shops.items(), start=1):
            log["shops"].append(
                {
                    "index": index,
                    "shop_key": shop_key,
                    "collected_count": len(shop_items),
                    "selected_count": min(len(shop_items), per_shop),
                    "ready": len(shop_items) >= per_shop,
                    "sample_items": [_item_brief(item) for item in shop_items[:3]],
                }
            )

        log["collection"] = {
            "ready_shops": ready_shops,
            "collected_shops": len(shops),
            "selected_items": len(items),
            "expected_total": expected_total,
            "preview_items": [_item_brief(item) for item in items[:20]],
            "attempts": collection_attempts,
        }

        if not items:
            # 失败诊断：再调一次 searchGoods 探测接口返回，便于定位是接口报错还是返回空
            search_probe = {"keyword": keyword, "shop_type": shop_type}
            try:
                probe_payload = client.search_goods(keyword, shop_type, 1, 1)
                probe_data = probe_payload.get("data") or {}
                probe_result = probe_data.get("result") if isinstance(probe_data, dict) else None
                first_goods_count = 0
                if isinstance(probe_result, list):
                    first_goods_count = len(probe_result)
                elif isinstance(probe_result, dict):
                    inner = probe_result.get("result") or probe_result.get("list") or probe_result.get("data")
                    if isinstance(inner, list):
                        first_goods_count = len(inner)
                search_probe.update(
                    {
                        "success": probe_payload.get("success"),
                        "code": probe_payload.get("code"),
                        "msg": probe_payload.get("msg"),
                        "first_page_goods": first_goods_count,
                    }
                )
            except Exception as exc:
                search_probe["error"] = str(exc)
            return _finish(
                log,
                False,
                {
                    "keyword": keyword,
                    "shop_type": shop_type,
                    "target_shops": target_shops,
                    "per_shop": per_shop,
                    "ready_shops": ready_shops,
                    "expected_total": expected_total,
                    "added_total": 0,
                    "reason": "\u672a\u6536\u96c6\u5230\u53ef\u52a0\u8d2d\u5546\u54c1",
                    "search_probe": search_probe,
                    "collection_attempts": collection_attempts,
                },
            )

        added_total = 0
        api_added_total = 0
        verified_added_total = 0
        failed_batches = []
        verification_failed_batches = []
        verification_items: list[Any] = []
        for batch_index, batch in enumerate(bulk_cart.chunks(items, batch_size), start=1):
            payload = client.add_to_cart(batch)
            ok = bool(payload.get("success")) and payload.get("code") == 0
            batch_log = {
                "batch": batch_index,
                "size": len(batch),
                "success": ok,
                "code": payload.get("code"),
                "msg": payload.get("msg"),
            }
            if not ok:
                batch_log["body"] = payload
                failed_batches.append(batch_index)
            else:
                api_added_total += len(batch)
                if verify_cart_after_add and cart_verify_mode == "batch":
                    cart_payload = _call_with_retry(
                        "cart verify",
                        lambda: client.post_form(
                            _api_path(variables, "client_cart_list", "/client/cart.goodsCartList"),
                            {"priceCut": cart_list_price_cut},
                        ),
                    )
                    verification = _verify_cart_contains_items(cart_payload, batch)
                    verification["api_success"] = _api_success(cart_payload)
                    batch_log["verification"] = verification
                    verified_added_total += verification["matched_count"]
                    if not verification["api_success"] or verification["matched_count"] < len(batch):
                        verification_failed_batches.append(batch_index)
                elif verify_cart_after_add:
                    verification_items.extend(batch)
                else:
                    added_total += len(batch)
            log["batches"].append(batch_log)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        if verify_cart_after_add and cart_verify_mode == "final" and verification_items:
            cart_payload = _call_with_retry(
                "cart verify final",
                lambda: client.post_form(
                    _api_path(variables, "client_cart_list", "/client/cart.goodsCartList"),
                    {"priceCut": cart_list_price_cut},
                ),
            )
            verification = _verify_cart_contains_items(cart_payload, verification_items)
            verification["api_success"] = _api_success(cart_payload)
            log["final_verification"] = verification
            verified_added_total = verification["matched_count"]
            if not verification["api_success"] or verification["matched_count"] < len(verification_items):
                verification_failed_batches.append("final")

        if verify_cart_after_add:
            added_total = verified_added_total
        passed = added_total > 0 and not failed_batches and (ready_shops >= target_shops or not strict_shop_count)
        if verify_cart_after_add:
            passed = passed and not verification_failed_batches
        summary = {
            "keyword": keyword,
            "shop_type": shop_type,
            "target_shops": target_shops,
            "per_shop": per_shop,
            "ready_shops": ready_shops,
            "expected_total": expected_total,
            "available_expected_total": ready_shops * per_shop,
            "added_total": added_total,
            "api_added_total": api_added_total,
            "verified_added_total": verified_added_total if verify_cart_after_add else added_total,
            "cart_verification_enabled": verify_cart_after_add,
            "cart_verify_mode": cart_verify_mode,
            "failed_batches": failed_batches,
            "verification_failed_batches": verification_failed_batches,
            "strict_shop_count": strict_shop_count,
        }
        if not passed:
            if failed_batches:
                summary["reason"] = "\u6709\u52a0\u8d2d\u6279\u6b21\u5931\u8d25"
            elif verification_failed_batches:
                summary["reason"] = "\u52a0\u8d2d\u63a5\u53e3\u8fd4\u56de\u6210\u529f\uff0c\u4f46\u8d2d\u7269\u8f66\u672a\u9a8c\u8bc1\u5230\u5bf9\u5e94\u5546\u54c1"
            elif strict_shop_count and ready_shops < target_shops:
                summary["reason"] = "\u6536\u96c6\u5230\u7684\u5e97\u94fa\u6570\u4e0d\u8db3"
            else:
                summary["reason"] = "\u672a\u6210\u529f\u52a0\u8d2d\u5546\u54c1"
        return _finish(log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish(
            log,
            False,
            {
                "keyword": keyword,
                "shop_type": shop_type,
                "target_shops": target_shops,
                "per_shop": per_shop,
                "added_total": 0,
                "error": str(exc),
            },
        )


def _api_success(payload: Dict[str, Any]) -> bool:
    code = payload.get("code")
    success = payload.get("success")
    success_ok = success is True or str(success).strip().lower() == "true"
    return success_ok and code in (None, 0, "0")


def _api_paths(variables: Dict[str, Any]) -> Dict[str, str]:
    paths = variables.get("api_paths")
    return paths if isinstance(paths, dict) else {}


def _api_path(variables: Dict[str, Any], key: str, default: str) -> str:
    return str(_api_paths(variables).get(key) or variables.get(f"{key}_path") or default)


def _client_login_with_path(client: Any, variables: Dict[str, Any], account: str, password: str, client_tool: str) -> str:
    payload = client.post_form(
        _api_path(variables, "client_login", "/client/userLogin"),
        {"account": account, "password": password, "client_tool": client_tool},
    )
    if not payload.get("success"):
        raise RuntimeError("Login failed: code={0} msg={1}".format(payload.get("code"), payload.get("msg")))
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    token = data.get("userToken") or data.get("token") or data.get("access_token")
    if not token:
        raise RuntimeError("Login succeeded but token was missing: {0}".format(payload))
    client.session.headers.update({"clienttoken": str(token)})
    return str(token)


def _configure_client_api_paths(client: Any, variables: Dict[str, Any]) -> None:
    def login(account: str, password: str, client_tool: str) -> str:
        return _client_login_with_path(client, variables, account, password, client_tool)

    def search_goods(keyword: str, shop_type: str, page: int, page_size: int) -> Dict[str, Any]:
        return client.post_form(
            _api_path(variables, "client_search_goods", "/client/searchGoods"),
            {"keywords": keyword, "shop_type": shop_type, "page": page, "pageSize": page_size},
        )

    def get_store_shop_id(keywords: str) -> Dict[str, Any]:
        return client.post_form(_api_path(variables, "client_store_shop_id", "/client/getStoreShopId"), {"keywords": keywords})

    def add_to_cart(items: list[Any]) -> Dict[str, Any]:
        fields = OrderedDict()
        for index, item in enumerate(items):
            prefix = f"to_cart[{index}]"
            data = item.to_dict() if hasattr(item, "to_dict") else dict(item)
            for key in [
                "goods_id",
                "goods_title",
                "price",
                "num",
                "pic",
                "detail",
                "sku_id",
                "spec_id",
                "shop_id",
                "shop_name",
                "from_platform",
                "price_ranges",
                "trace",
            ]:
                fields[f"{prefix}[{key}]"] = data.get(key, "")
        return client.post_form(_api_path(variables, "client_cart_add", "/client/cart.goodsToCart"), fields)

    client.login = login
    client.search_goods = search_goods
    client.get_store_shop_id = get_store_shop_id
    client.add_to_cart = add_to_cart


def _payload_brief(payload: Dict[str, Any]) -> Dict[str, Any]:
    brief: Dict[str, Any] = {}
    for key in ["success", "code", "msg", "message"]:
        if key in payload:
            brief[key] = payload.get(key)
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ["order_sn", "message", "serial_number", "pay_amount", "total_amount"]:
            if key in data:
                brief[f"data.{key}"] = data.get(key)
        order_rows = data.get("order")
        if isinstance(order_rows, list):
            brief["data.order_count"] = len(order_rows)
    elif isinstance(data, list):
        brief["data_count"] = len(data)
    elif data not in (None, "", [], {}):
        brief["data"] = data
    return brief


def _order_text(value: Any, fallback: str = "") -> str:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list, tuple)):
        return bulk_cart.json_text(value)
    return str(value)


def _first_price(price_ranges: Any) -> str:
    if not isinstance(price_ranges, list) or not price_ranges:
        return ""
    first = price_ranges[0]
    if not isinstance(first, dict):
        return ""
    for key in ["price", "priceMin", "priceMax"]:
        if first.get(key) not in (None, ""):
            return str(first.get(key))
    return ""


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _order_option_items(value: Any) -> list[Dict[str, Any]]:
    return [item for item in _json_list(value) if isinstance(item, dict)]


def _order_option_key(option: Dict[str, Any]) -> str:
    for key in ["id", "option_id", "value", "key", "name", "name_translate"]:
        value = option.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _order_option_label(option: Dict[str, Any], key: str = "") -> str:
    option_id = str(option.get("id") or option.get("option_id") or "").strip()
    name = str(option.get("name") or "").strip()
    name_translate = str(option.get("name_translate") or "").strip()
    for candidate in [name, option_id, key]:
        if candidate and ORDER_OPTION_NAME_FALLBACKS.get(candidate):
            return ORDER_OPTION_NAME_FALLBACKS[candidate]
    return name or name_translate or key


def _normalize_order_option_counts(value: Any) -> OrderedDict[str, int]:
    if not isinstance(value, dict):
        return OrderedDict()
    counts: OrderedDict[str, int] = OrderedDict()
    for raw_key, raw_count in value.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        if count > 0:
            counts[key] = count
    return counts


def _add_order_option_to_catalog(catalog: OrderedDict[str, Dict[str, Any]], option: Dict[str, Any]) -> None:
    key = _order_option_key(option)
    if not key or key in catalog:
        return
    label = _order_option_label(option, key)
    catalog[key] = {
        "key": key,
        "id": option.get("id") or option.get("option_id") or "",
        "name": option.get("name") or label,
        "label": label,
        "name_translate": option.get("name_translate") or "",
        "price": option.get("price") if option.get("price") not in (None, "") else "",
        "price_type": option.get("price_type") if option.get("price_type") not in (None, "") else "",
        "unit": option.get("unit") or "",
        "template": copy.deepcopy(option),
    }


def _order_option_catalog_from_options(options: Any) -> OrderedDict[str, Dict[str, Any]]:
    catalog: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    for option in _order_option_items(options):
        _add_order_option_to_catalog(catalog, option)
    return catalog


def _collect_order_option_catalog(items: list[Dict[str, Any]]) -> OrderedDict[str, Dict[str, Any]]:
    catalog: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    for item in items:
        for option in _order_option_items(item.get("option")):
            _add_order_option_to_catalog(catalog, option)
    return catalog


def _public_order_options(catalog: OrderedDict[str, Dict[str, Any]]) -> list[Dict[str, Any]]:
    return [
        {key: value for key, value in option.items() if key != "template"}
        for option in catalog.values()
    ]


def _order_option_list_path(variables: Dict[str, Any]) -> str:
    return _api_path(variables, "client_order_option_list", "/client/order.optionList")


def _fetch_order_option_catalog(client: Any, variables: Dict[str, Any]) -> tuple[OrderedDict[str, Dict[str, Any]], Dict[str, Any], str]:
    path = _order_option_list_path(variables)
    payload = _call_with_retry("order option list", lambda: client.post_form(path, {}))
    if not _api_success(payload):
        raise RuntimeError(f"读取订单 option 失败：{payload.get('msg') or payload.get('data') or payload}")
    options = payload.get("data")
    catalog = _order_option_catalog_from_options(options)
    if not catalog:
        raise RuntimeError("读取订单 option 失败：接口未返回可用 option")
    return catalog, payload, path


def _apply_order_options_to_items(
    items: list[Dict[str, Any]],
    variables: Dict[str, Any],
    option_catalog: OrderedDict[str, Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    counts = _normalize_order_option_counts(variables.get("order_option_counts"))
    catalog = option_catalog if option_catalog is not None else _collect_order_option_catalog(items)
    selected_options = []
    missing = []
    for key, count in counts.items():
        option = catalog.get(key)
        if option:
            selected_options.append({**{k: v for k, v in option.items() if k != "template"}, "num": count})
        else:
            missing.append({"key": key, "num": count, "reason": "option_not_found"})

    applied_detail_count = 0
    for item in items:
        applied = []
        for key, count in counts.items():
            template = (catalog.get(key) or {}).get("template")
            if not isinstance(template, dict):
                continue
            option = copy.deepcopy(template)
            label = _order_option_label(option, key)
            option["name"] = option.get("name") or label
            option["checked"] = True
            option["num"] = str(count)
            applied.append(option)
        if applied:
            item["option"] = applied
            applied_detail_count += 1
        else:
            item.pop("option", None)

    return {
        "available_options": _public_order_options(catalog),
        "selected_options": selected_options,
        "counts": dict(counts),
        "applied_detail_count": applied_detail_count,
        "missing": missing,
    }


def _flatten_cart_goods(cart_payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = cart_payload.get("data")
    if isinstance(data, list):
        containers = data
    elif isinstance(data, dict):
        nested = data.get("list") or data.get("result") or data.get("rows") or data.get("goods") or data.get("data")
        containers = nested if isinstance(nested, list) else [data]
    else:
        containers = []

    goods: list[Dict[str, Any]] = []
    for container in containers:
        if not isinstance(container, dict):
            continue
        rows = container.get("goods") or container.get("goods_list") or container.get("list") or container.get("items")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                item = dict(row)
                for key in ["shop_id", "shop_name", "shop_type"]:
                    if item.get(key) in (None, "") and container.get(key) not in (None, ""):
                        item[key] = container.get(key)
                goods.append(item)
        elif container.get("id") not in (None, "") and container.get("goods_id") not in (None, ""):
            goods.append(dict(container))
    return goods


def _cart_item_ready(item: Dict[str, Any]) -> bool:
    return item.get("id") not in (None, "") and item.get("goods_id") not in (None, "")


def _select_cart_items(cart_payload: Dict[str, Any], item_count: int) -> list[Dict[str, Any]]:
    selected: list[Dict[str, Any]] = []
    for item in _flatten_cart_goods(cart_payload):
        if not _cart_item_ready(item):
            continue
        selected.append(item)
        if len(selected) >= item_count:
            break
    return selected


def _cart_shop_key(item: Dict[str, Any]) -> str:
    shop_id = str(item.get("shop_id") or "").strip()
    if shop_id:
        return f"shop_id:{shop_id}"
    shop_name = str(item.get("shop_name") or "").strip()
    platform = str(item.get("from_platform") or item.get("shop_type") or "").strip()
    if shop_name:
        return f"shop_name:{shop_name}|{platform}"
    if platform:
        return f"platform:{platform}"
    return f"unknown:{item.get('goods_id') or item.get('id') or ''}"


def _select_cart_items_by_shop(
    cart_payload: Dict[str, Any],
    shop_count: int,
    per_shop: int,
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    grouped: OrderedDict[str, list[Dict[str, Any]]] = OrderedDict()
    for item in _flatten_cart_goods(cart_payload):
        if not _cart_item_ready(item):
            continue
        grouped.setdefault(_cart_shop_key(item), []).append(item)

    ready_groups = [(shop_key, items) for shop_key, items in grouped.items() if len(items) >= per_shop]
    selected: list[Dict[str, Any]] = []
    selected_shop_keys: list[str] = []
    for shop_key, items in ready_groups[:shop_count]:
        selected.extend(items[:per_shop])
        selected_shop_keys.append(shop_key)

    expected_total = shop_count * per_shop
    meta = {
        "expected_shop_count": shop_count,
        "expected_per_shop": per_shop,
        "expected_total": expected_total,
        "available_shop_count": len(grouped),
        "ready_shop_count": len(ready_groups),
        "selected_shop_count": len(selected_shop_keys),
        "selected_count": len(selected),
        "shortage_count": max(0, expected_total - len(selected)),
        "selected_shop_keys": selected_shop_keys,
        "shop_counts": {shop_key: len(items) for shop_key, items in grouped.items()},
    }
    return selected, meta


def _order_item_brief(item: Dict[str, Any]) -> Dict[str, Any]:
    title = str(item.get("goods_title") or "")
    return {
        "cart_id": item.get("id"),
        "goods_id": item.get("goods_id"),
        "goods_title": title[:80],
        "num": item.get("num"),
        "price": item.get("price"),
        "sku_id": item.get("sku_id"),
        "spec_id": item.get("spec_id"),
        "shop_id": item.get("shop_id"),
        "shop_name": item.get("shop_name"),
        "from_platform": item.get("from_platform"),
    }


def _edit_cart_fields(item: Dict[str, Any], quantity: int) -> OrderedDict[str, Any]:
    detail = _order_text(item.get("detail"), "[]")
    price = item.get("price")
    if price in (None, ""):
        price = _first_price(item.get("price_ranges"))
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["id"] = item.get("id")
    fields["num"] = quantity
    fields["price"] = price
    fields["detail"] = detail
    fields["sku_id"] = item.get("sku_id") or ""
    fields["spec_id"] = item.get("spec_id") or ""
    fields["pic"] = item.get("pic") or ""
    fields["client_remark"] = item.get("client_remark") or ""
    return fields


def _cart_item_quantity(item: Dict[str, Any]) -> int | None:
    value = item.get("num")
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _authed_client_with_token(base_url: str, timeout: int, variables: Dict[str, Any], token: str) -> Any:
    client = bulk_cart.RakumartClient(base_url, timeout)
    _configure_client_api_paths(client, variables)
    if token:
        client.session.headers.update({"clienttoken": token})
    return client


def _edit_cart_items_for_order(
    client: Any,
    base_url: str,
    timeout: int,
    variables: Dict[str, Any],
    selected_items: list[Dict[str, Any]],
    item_quantity: int,
    token: str,
) -> tuple[list[Dict[str, Any]], list[Any]]:
    edit_path = _api_path(variables, "client_cart_edit", "/client/cart.goodsCartEdit")
    workers = _as_int(variables.get("cart_edit_workers"), 1)
    logs_by_index: Dict[int, Dict[str, Any]] = {}
    failed_by_index: Dict[int, tuple[Dict[str, Any], Dict[str, Any]]] = {}
    to_edit: list[tuple[int, Dict[str, Any], OrderedDict[str, Any]]] = []

    for index, item in enumerate(selected_items):
        if _cart_item_quantity(item) == item_quantity:
            item["num"] = item_quantity
            logs_by_index[index] = {
                "cart_id": item.get("id"),
                "goods_id": item.get("goods_id"),
                "num": item_quantity,
                "success": True,
                "skipped": True,
                "reason": "quantity_already_matched",
            }
            continue
        to_edit.append((index, item, _edit_cart_fields(item, item_quantity)))

    def apply_result(index: int, item: Dict[str, Any], payload: Dict[str, Any], retried: bool = False) -> None:
        edit_ok = _api_success(payload)
        if edit_ok:
            item["num"] = item_quantity
            failed_by_index.pop(index, None)
        else:
            failed_by_index[index] = (item, payload)
        log_item = {
            "cart_id": item.get("id"),
            "goods_id": item.get("goods_id"),
            "num": item_quantity,
            **_payload_brief(payload),
        }
        if retried:
            log_item["retried_serial"] = True
        logs_by_index[index] = log_item

    def edit_with(target_client: Any, fields: OrderedDict[str, Any]) -> Dict[str, Any]:
        return _call_with_retry("cart edit", lambda: target_client.post_form(edit_path, fields))

    if workers > 1 and len(to_edit) > 1 and token:
        thread_state = threading.local()

        def thread_client() -> Any:
            cached_client = getattr(thread_state, "client", None)
            if cached_client is None:
                cached_client = _authed_client_with_token(base_url, timeout, variables, token)
                thread_state.client = cached_client
            return cached_client

        def edit_in_thread(fields: OrderedDict[str, Any]) -> Dict[str, Any]:
            return edit_with(thread_client(), fields)

        with ThreadPoolExecutor(max_workers=min(workers, len(to_edit))) as executor:
            future_map = {
                executor.submit(edit_in_thread, fields): (index, item, fields)
                for index, item, fields in to_edit
            }
            for future in as_completed(future_map):
                index, item, fields = future_map[future]
                try:
                    payload = future.result()
                except Exception as exc:
                    payload = {"success": False, "message": str(exc)}
                apply_result(index, item, payload)

        retry_items = [(index, item, fields) for index, item, fields in to_edit if index in failed_by_index]
        for index, item, fields in retry_items:
            try:
                payload = edit_with(client, fields)
            except Exception as exc:
                payload = {"success": False, "message": str(exc)}
            apply_result(index, item, payload, retried=True)
    else:
        for index, item, fields in to_edit:
            try:
                payload = edit_with(client, fields)
            except Exception as exc:
                payload = {"success": False, "message": str(exc)}
            apply_result(index, item, payload)

    edit_logs = [logs_by_index[index] for index in range(len(selected_items)) if index in logs_by_index]
    failed_edits = [item.get("id") for item, _payload in failed_by_index.values()]
    return edit_logs, failed_edits


# 后端日文错误提示 → 中文映射（命中即替换，未命中保留原文+数字）
_ORDER_MSG_TRANSLATIONS = {
    "注文提出商品数が最大制限に達しました": "订单提交商品数已达最大限制",
    "操作が成功しました": "操作成功",
    "ログインに失敗しました": "登录失败",
    "パラメータエラー": "参数错误",
    "システムエラー": "系统错误",
    "注文情報が存在しません": "订单信息不存在",
    "カート情報が存在しません": "购物车信息不存在",
    "在庫が不足しています": "库存不足",
}


def _translate_order_msg(msg: Any) -> str:
    """把后端日文错误提示翻译成中文，未命中的保留原文。"""
    text = str(msg or "").strip()
    if not text:
        return ""
    for jp, cn in _ORDER_MSG_TRANSLATIONS.items():
        if jp in text:
            return text.replace(jp, cn)
    return text


def _parse_order_max_limit(msg: Any) -> int | None:
    """从"订单提交商品数已达最大限制:50"类提示中解析最大数量。"""
    text = str(msg or "")
    m = re.search(r"[:：]\s*(\d+)\s*$", text)
    return int(m.group(1)) if m else None


def _order_fields(
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


def _extract_order_sn(payload: Dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, dict) and data.get("order_sn"):
        return str(data.get("order_sn"))
    if payload.get("order_sn"):
        return str(payload.get("order_sn"))
    return ""


def _decimal_text(value: Any, fallback: str = "0") -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        number = Decimal(str(fallback))
    text = format(number.normalize(), "f")
    return "0" if text == "-0" else text


def _money_total(num: Any, price: Any, freight: Any = "0") -> str:
    try:
        total = Decimal(str(num)) * Decimal(str(price)) + Decimal(str(freight))
    except (InvalidOperation, ValueError, TypeError):
        total = Decimal("0")
    return _decimal_text(total)


def _admin_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "AdminToken": token,
        "ManageToken": token,
        "adminToken": token,
        "token": token,
        "X-Requested-With": "XMLHttpRequest",
        "Lang": "zh-CN",
    }


def _call_with_retry(label: str, operation: Any, attempts: int = 3, delay: float = 0.8) -> Any:
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


def _post_admin_form(
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


def _flatten_urlencoded_fields(value: Any, prefix: str) -> list[tuple[str, str]]:
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


def _post_admin_urlencoded(
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


def _admin_login_without_runtime(
    session: requests.Session,
    base_url: str,
    variables: Dict[str, Any],
    timeout: int,
) -> tuple[Dict[str, Any], str]:
    fields = {
        "username": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
        "password": str(variables.get("backend_password") or "raku@123456``"),
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


def _admin_login(
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


def _order_detail_data(
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


def _admin_detail_brief(order_data: Dict[str, Any]) -> Dict[str, Any]:
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


def _prepare_translate_data(order_data: Dict[str, Any], variables: Dict[str, Any]) -> Dict[str, Any]:
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


def _build_confirm_data(order_data: Dict[str, Any], variables: Dict[str, Any], item_quantity: int) -> Dict[str, Any]:
    quote_price = _decimal_text(variables.get("confirm_price") or variables.get("quote_unit_price") or "10")
    freight = _decimal_text(variables.get("confirm_freight") or variables.get("freight") or "5")
    volume = str(variables.get("confirm_volume") or "1x2x3")
    weight = _as_int(variables.get("confirm_weight") or variables.get("weight"), 200)
    remark = str(variables.get("confirm_remark") or "自动化采购调查")
    details = order_data.get("order_detail")
    confirm_details = []
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict) or detail.get("id") in (None, ""):
            continue
        quantity = _as_int(detail.get("num") or item_quantity, item_quantity)
        confirm_details.append(
            {
                "id": detail.get("id"),
                "confirm_num": str(quantity),
                "confirm_price": quote_price,
                "confirm_freight": freight,
                "confirm_dicker_price": quote_price,
                "confirm_dicker_freight": freight,
                "g_remark": remark,
                "volume": volume,
                "weight": weight,
            }
        )
    return {"order_sn": order_data.get("order_sn"), "order_detail": confirm_details}


ORDER_PART_PAY_FEE_KEYS = ["domestic_freight", "service_fee", "additional_service_fee", "other_fee"]
ORDER_PART_PAY_TAIL_NODES = {"before_shelf", "before_porder_create"}


def _order_part_pay_enabled(variables: Dict[str, Any]) -> bool:
    return _full_flow_part_pay_script_enabled(variables) and _order_part_pay_requested(variables)


def _full_flow_part_pay_script_enabled(variables: Dict[str, Any]) -> bool:
    return _as_bool(variables.get("_full_flow_part_pay_script"), False)


def _order_part_pay_requested(variables: Dict[str, Any]) -> bool:
    return _as_bool(variables.get("order_part_pay"), False) or str(variables.get("order_part_pay")).strip() == "1"


def _order_part_pay_percent(variables: Dict[str, Any]) -> int:
    percent = _as_int(variables.get("order_part_pay_percent"), 10)
    percent = max(0, min(100, percent))
    return int(round(percent / 5) * 5)


def _order_part_pay_tail_node(variables: Dict[str, Any]) -> str:
    node = str(variables.get("order_part_pay_tail_node") or "before_shelf").strip()
    return node if node in ORDER_PART_PAY_TAIL_NODES else "before_shelf"


def _order_part_pay_fee_timing(variables: Dict[str, Any]) -> Dict[str, str]:
    raw = variables.get("order_part_pay_fee_timing")
    raw = raw if isinstance(raw, dict) else {}
    timing: Dict[str, str] = {}
    for key in ORDER_PART_PAY_FEE_KEYS:
        value = str(raw.get(key) or "first").strip()
        timing[key] = "tail" if value in {"tail", "尾款支付"} else "first"
    return timing


def _apply_order_part_pay_payload(prepared: Dict[str, Any], variables: Dict[str, Any]) -> None:
    if _full_flow_part_pay_script_enabled(variables):
        prepared["order_part_pay"] = 1 if _order_part_pay_requested(variables) else 0
    else:
        prepared.pop("order_part_pay", None)


def _order_part_pay_api_node(variables: Dict[str, Any]) -> int:
    configured = variables.get("order_part_pay_must_pay_node")
    if configured not in (None, ""):
        return _as_int(configured, 1)
    return 1 if _order_part_pay_tail_node(variables) == "before_shelf" else 2


def _order_part_pay_api_fee_flag(timing: Dict[str, str], key: str) -> int:
    return 1 if timing.get(key) == "tail" else 0


def _order_part_pay_goods_total(offer_data: Dict[str, Any]) -> Decimal:
    total = Decimal("0")
    details = offer_data.get("order_detail")
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        try:
            num = Decimal(str(detail.get("offer_num") or detail.get("confirm_num") or detail.get("num") or "0"))
            price = Decimal(str(detail.get("offer_price") or detail.get("confirm_price") or "0"))
        except (InvalidOperation, TypeError, ValueError):
            continue
        total += max(Decimal("0"), num) * max(Decimal("0"), price)
    return total


def _order_part_pay_first_goods_amount(offer_data: Dict[str, Any], variables: Dict[str, Any]) -> str:
    configured = _positive_decimal(variables.get("order_part_pay_goods_amount") or variables.get("first_goods_amount"))
    if configured is not None:
        return f"{configured.quantize(Decimal('0.01')):.2f}"
    total = _order_part_pay_goods_total(offer_data)
    amount = total * Decimal(_order_part_pay_percent(variables)) / Decimal("100")
    return f"{amount.quantize(Decimal('0.01')):.2f}"


def _order_part_pay_plan_fields(order_sn: str, offer_data: Dict[str, Any], variables: Dict[str, Any]) -> OrderedDict[str, Any]:
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


def _save_order_part_pay_plan_if_needed(
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


def _prepare_offer_data(order_data: Dict[str, Any], variables: Dict[str, Any], item_quantity: int) -> Dict[str, Any]:
    prepared = copy.deepcopy(order_data)
    quote_price = _decimal_text(variables.get("offer_price") or variables.get("quote_unit_price") or "10")
    offer_freight = _decimal_text(variables.get("offer_freight") or variables.get("confirm_freight") or "5")
    prepared["other_price"] = _decimal_text(variables.get("other_price") or prepared.get("other_price") or "0")
    prepared["other_price_remark"] = str(variables.get("other_price_remark") or prepared.get("other_price_remark") or "自动化其他费用备注")
    prepared["y_reply"] = str(variables.get("y_reply") or prepared.get("y_reply") or "")
    prepared["y_remark"] = str(variables.get("offer_remark") or prepared.get("y_remark") or "自动化业务报价")
    prepared["predict_logistics_price"] = _decimal_text(variables.get("predict_logistics_price") or prepared.get("predict_logistics_price") or "0")
    _apply_order_part_pay_payload(prepared, variables)
    details = prepared.get("order_detail")
    if isinstance(details, list):
        for detail in details:
            if not isinstance(detail, dict):
                continue
            quantity = _as_int(detail.get("confirm_num") or detail.get("num") or item_quantity, item_quantity)
            offer_quantity = _as_int(variables.get("offer_num"), quantity)
            detail["confirm_num"] = str(quantity)
            detail["confirm_price"] = quote_price
            detail["confirm_dicker_price"] = quote_price
            detail["offer_num"] = offer_quantity
            detail["offer_price"] = quote_price
            detail["offer_freight"] = offer_freight
            detail["offer_total"] = _money_total(offer_quantity, quote_price, offer_freight)
    return prepared


def _run_backend_order_flow(
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
    translate_payload = _post_admin_form(
        session,
        base_url,
        _api_path(variables, "admin_order_translate", "/order.submitTranslate"),
        {"data": bulk_cart.json_text(translate_data), "is_temp": str(variables.get("translate_is_temp") or "0")},
        timeout,
    )
    backend_log["translate"] = _payload_brief(translate_payload)
    if not _api_success(translate_payload):
        return False, {"backend_passed": False, "reason": "订单翻译提交失败", "translate": _payload_brief(translate_payload)}

    # detail_after_translate：仅 order_translated 暂停点需要准确 status，非暂停路径跳过冗余查询
    #（translate 不修改 order_detail 结构，confirm_source 直接用 translate_data 即可）
    if _checkpoint_requested(variables, "order_translated"):
        _, after_translate = _order_detail_data(session, base_url, variables, order_sn, timeout, retries=2)
        backend_log["detail_after_translate"] = _admin_detail_brief(after_translate)
        return True, _paused_summary(
            "order_translated",
            {
                "order_sn": order_sn,
                "backend_passed": True,
                "backend_steps": ["login", "detail", "translate"],
                "backend_status": after_translate.get("status") if after_translate else None,
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
            },
        )
    _, after_offer = _order_detail_data(session, base_url, variables, order_sn, timeout, retries=1)
    backend_log["detail_after_offer"] = _admin_detail_brief(after_offer)
    return True, {
        "backend_passed": True,
        "backend_steps": ["login", "detail", "translate", "confirm", "part_pay_plan", "offer"],
        "quote_unit_price": _decimal_text(variables.get("offer_price") or variables.get("quote_unit_price") or "10"),
        "backend_status": after_offer.get("status") if after_offer else None,
    }


def _order_status_code(order_data: Dict[str, Any]) -> int | None:
    for key in ["status", "order_status", "orderStatus"]:
        value = order_data.get(key)
        if value in (None, ""):
            continue
        try:
            return int(Decimal(str(value)))
        except (InvalidOperation, TypeError, ValueError):
            continue
    return None


def _resume_node_for_order_status(status: int | None) -> str:
    if status == 20:
        return "order_translated"
    if status == 21:
        return "order_confirmed"
    if status == 22:
        return "order_offered"
    if status == 30:
        return "order_offered"
    return ""


def _order_detail_ids(order_data: Dict[str, Any]) -> list[str]:
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


def _order_ready_for_warehouse_delivery(status: int | None, order_data: Dict[str, Any]) -> bool:
    if status == 60:
        return True
    details = order_data.get("order_detail")
    if not isinstance(details, list):
        return False
    ready_names = ["\u5f85\u53d1\u8d27", "\u53ef\u53d1\u8d27", "\u5df2\u5165\u5e93"]
    for item in details:
        if not isinstance(item, dict):
            continue
        status_name = str(item.get("statusName") or item.get("status_name") or "")
        if any(name in status_name for name in ready_names):
            return True
    return False


def _purchase_is_pending_start(item: Dict[str, Any]) -> bool:
    return "\u5f85\u62cd\u4e0b" in _purchase_status_name(item)


def _detect_resume_order_state(
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


def _run_backend_order_flow_resume(
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
    if status <= 20:
        translate_data = _prepare_translate_data(current_data, variables)
        translate_payload = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_order_translate", "/order.submitTranslate"),
            {"data": bulk_cart.json_text(translate_data), "is_temp": str(variables.get("translate_is_temp") or "0")},
            timeout,
        )
        backend_log["translate"] = _payload_brief(translate_payload)
        if not _api_success(translate_payload):
            return False, {"backend_passed": False, "reason": "\u8ba2\u5355\u7ffb\u8bd1\u63d0\u4ea4\u5931\u8d25", "translate": _payload_brief(translate_payload)}
        backend_steps.append("translate")
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
                },
            )

    return True, {
        "order_sn": order_sn,
        "backend_passed": True,
        "backend_steps": backend_steps,
        "quote_unit_price": _decimal_text(variables.get("offer_price") or variables.get("quote_unit_price") or "10"),
        "backend_status": current_data.get("status") if current_data else None,
    }


def _positive_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number > 0 else None


def _first_positive_decimal(source: Dict[str, Any], keys: list[str]) -> Decimal | None:
    for key in keys:
        number = _positive_decimal(source.get(key))
        if number is not None:
            return number
    return None


def _order_rows_from_payload(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("data") or data.get("list") or data.get("rows") or data.get("order") or data.get("orders") or []
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def _order_payment_amount(order: Dict[str, Any]) -> str:
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


def _payment_order_list_fields(variables: Dict[str, Any]) -> OrderedDict[str, Any]:
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


def _select_payment_order(orders: list[Dict[str, Any]], variables: Dict[str, Any], status_name: str) -> Dict[str, Any] | None:
    requested_sn = str(variables.get("order_sn") or "").strip()
    if requested_sn:
        for order in orders:
            if str(order.get("order_sn") or "") == requested_sn:
                return order
    for order in orders:
        if str(order.get("status_name") or "") == status_name or str(order.get("status") or "") == "30":
            return order
    return orders[0] if orders else None


def _login_client_for_payment(env: Env, variables: Dict[str, Any], log: Dict[str, Any]) -> tuple[Any, str, int, str]:
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


def _load_payment_order(client: Any, variables: Dict[str, Any], log: Dict[str, Any]) -> tuple[Dict[str, Any] | None, str, str]:
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


def _common_payment_summary(
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


PORDER_AMOUNT_KEYS = [
    "pay_amount",
    "total_amount",
    "need_pay_amount",
    "wait_pay_amount",
    "payment_amount",
    "porder_amount",
    "porder_price",
    "delivery_amount",
    "delivery_price",
    "logistics_price",
    "logistics_amount",
    "international_freight",
    "freight_price",
    "freight_amount",
    "amount",
    "total",
]


def _first_recursive_positive_decimal(value: Any, keys: list[str]) -> Decimal | None:
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


def _porder_payload_matches(payload: Dict[str, Any], porder_sn: str) -> bool:
    if not porder_sn:
        return False
    found = _extract_porder_sn(payload, "")
    return not found or found == porder_sn or _row_contains_text(payload, porder_sn)


def _porder_payment_summary(
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


def _porder_payment_amount_from_payload(payload: Dict[str, Any]) -> str:
    number = _first_recursive_positive_decimal(payload, PORDER_AMOUNT_KEYS)
    return _decimal_text(number) if number is not None else "0"


def _load_porder_payment_amount(client: Any, variables: Dict[str, Any], log: Dict[str, Any], porder_sn: str) -> str:
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


def _apply_extra_fields(fields: OrderedDict[str, Any], extra_fields: Any) -> OrderedDict[str, Any]:
    if isinstance(extra_fields, dict):
        for key, value in extra_fields.items():
            if key and value is not None:
                fields[str(key)] = value
    return fields


def _order_tail_payment_order_sn(variables: Dict[str, Any]) -> str:
    for key in ["order_sn", "last_order_sn", "warehouse_order_sn"]:
        value = str(variables.get(key) or "").strip()
        if value:
            return value
    return ""


def _order_tail_payment_mode(variables: Dict[str, Any]) -> str:
    mode = str(
        variables.get("order_tail_payment_mode")
        or variables.get("order_payment_mode")
        or variables.get("payment_mode")
        or "balance"
    ).strip().lower()
    return "bank" if mode in {"bank", "bank_payment"} else "balance"


def _order_tail_payment_path(variables: Dict[str, Any], payment_mode: str) -> str:
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


def _order_tail_pay_amount_from_variables(variables: Dict[str, Any]) -> str:
    for key in ["order_tail_pay_amount", "tail_pay_amount", "pay_amount"]:
        value = str(variables.get(key) or "").strip()
        if value:
            return value
    return ""


def _order_tail_value_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        values: list[str] = []
        for item in value:
            values.extend(_order_tail_value_list(item))
        return _unique_list(values)
    text = str(value or "").strip()
    if not text:
        return []
    return _unique_list([item.strip() for item in re.split(r"[\s,，;；]+", text) if item.strip()])


def _order_tail_partial_enabled(variables: Dict[str, Any]) -> bool:
    return _as_bool(variables.get("order_part_pay_tail_partial_enabled"), False)


def _order_tail_partial_select_by(variables: Dict[str, Any]) -> str:
    value = str(variables.get("order_part_pay_tail_select_by") or "").strip()
    return "detail_id" if value in {"detail_id", "order_detail_id", "id"} else "sorting"


def _order_tail_partial_selected_values(variables: Dict[str, Any]) -> tuple[str, list[str]]:
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


def _order_tail_detail_id(row: Dict[str, Any]) -> str:
    for key in ["order_detail_id", "orderDetailId", "detail_id", "id"]:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _order_tail_detail_sorting(row: Dict[str, Any]) -> str:
    for key in ["sorting", "sort", "index", "no"]:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _order_tail_detail_status(row: Dict[str, Any]) -> str:
    value = row.get("tail_pay_status")
    if value not in (None, ""):
        return str(value).strip()
    return ""


def _order_tail_detail_is_paid(row: Dict[str, Any]) -> bool:
    status = _order_tail_detail_status(row).lower()
    name = str(row.get("tail_pay_status_name") or "").strip()
    return status in {"1", "true", "paid"} or "已支付" in name


def _order_tail_detail_is_unpaid(row: Dict[str, Any]) -> bool:
    status = _order_tail_detail_status(row).lower()
    name = str(row.get("tail_pay_status_name") or "").strip()
    return status in {"0", "false", "unpaid"} or "待支付" in name


def _order_tail_order_detail_rows(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
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


def _order_tail_unpaid_ids_from_detail(payload: Dict[str, Any], rows: list[Dict[str, Any]]) -> list[str]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    summary = data.get("part_pay_tail_summary") if isinstance(data.get("part_pay_tail_summary"), dict) else {}
    ids = _order_tail_value_list(summary.get("unpaid_tail_detail_ids"))
    if ids:
        return ids
    return _unique_list([_order_tail_detail_id(row) for row in rows if _order_tail_detail_is_unpaid(row)])


def _order_tail_detail_fields(order_sn: str, variables: Dict[str, Any]) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["order_sn"] = order_sn
    return fields


def _order_tail_pay_data_fields(order_sn: str, variables: Dict[str, Any], detail_ids: list[str]) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["order_sn"] = order_sn
    for index, detail_id in enumerate(detail_ids):
        fields[f"order_detail_ids[{index}]"] = detail_id
    if detail_ids:
        fields["pay_mode"] = "partial"
    fields["discounts_id"] = str(variables.get("discounts_id") or "")
    return fields


def _order_tail_apply_payment_detail_fields(fields: OrderedDict[str, Any], detail_ids: list[str]) -> None:
    for index, detail_id in enumerate(detail_ids):
        fields[f"order_detail_ids[{index}]"] = detail_id
    if detail_ids:
        fields["pay_mode"] = "partial"


def _order_tail_pay_data_brief(payload: Dict[str, Any], fields: OrderedDict[str, Any]) -> Dict[str, Any]:
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


def _order_tail_pay_amount_from_pay_data(payload: Dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    part_pay_amount = data.get("part_pay_amount") if isinstance(data.get("part_pay_amount"), dict) else {}
    jpy = part_pay_amount.get("JPY") if isinstance(part_pay_amount.get("JPY"), dict) else {}
    for value in [jpy.get("pay_amount_jpy"), jpy.get("total_amount"), data.get("pay_amount_jpy"), data.get("pay_amount")]:
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _order_tail_pay_data_unpayable_ids(payload: Dict[str, Any]) -> list[str]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    rows = data.get("tail_detail_list") if isinstance(data.get("tail_detail_list"), list) else []
    return _unique_list(
        [
            _order_tail_detail_id(row)
            for row in rows
            if isinstance(row, dict) and row.get("can_pay_tail") is False
        ]
    )


def _resolve_order_tail_partial_context(
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


def _public_order_tail_context(context: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in context.items() if not str(key).startswith("_")}


def _order_tail_bank_pay_amount(
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


def _run_order_tail_payment_if_needed(
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


def _bank_pay_reach_date(variables: Dict[str, Any], pay_date: datetime) -> str:
    configured = str(variables.get("pay_reach_date") or "").strip()
    if configured:
        return configured
    offset_days = _as_int(variables.get("pay_reach_after_days"), 0)
    return (pay_date + timedelta(days=max(0, offset_days))).strftime("%Y-%m-%d %H:%M:%S")


def _finance_rows_from_payload(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("data") or data.get("list") or data.get("rows") or []
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def _finance_bill_brief(row: Dict[str, Any] | None) -> Dict[str, Any]:
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


def _row_contains_text(row: Dict[str, Any], needle: str) -> bool:
    return bool(needle) and needle in bulk_cart.json_text(row)


def _select_finance_bill(rows: list[Dict[str, Any]], serial_number: str, order_sn: str) -> Dict[str, Any] | None:
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


def _finance_unconfirm_fields(variables: Dict[str, Any], serial_number: str, order_sn: str) -> OrderedDict[str, Any]:
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


def _admin_rows_from_payload(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("data") or data.get("list") or data.get("rows") or data.get("items") or data.get("order") or []
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def _field_text(value: Any) -> str:
    return "" if value in (None, "") else str(value)


def _purchase_timestamp_no() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def _purchase_list_fields(variables: Dict[str, Any], order_sn: str) -> OrderedDict[str, Any]:
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


def _flatten_purchase_items(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
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


def _purchase_item_id(item: Dict[str, Any]) -> Any:
    return item.get("id") or item.get("order_purchase_id") or item.get("purchase_id")


def _select_purchase_items(items: list[Dict[str, Any]], order_sn: str, variables: Dict[str, Any]) -> list[Dict[str, Any]]:
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


def _positive_text(*values: Any, fallback: str = "0") -> str:
    for value in values:
        number = _positive_decimal(value)
        if number is not None:
            return _decimal_text(number)
    return _decimal_text(fallback)


def _purchase_item_values(item: Dict[str, Any], variables: Dict[str, Any]) -> tuple[str, str, str, str]:
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


def _purchase_status_name(item: Dict[str, Any]) -> str:
    detail = item.get("order_detail") if isinstance(item.get("order_detail"), dict) else {}
    return str(item.get("statusName") or item.get("status_name") or detail.get("statusName") or detail.get("status_name") or "\u5f85\u62cd\u4e0b")


def _purchase_save_rows(
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


def _purchase_wait_pay_rows(items: list[Dict[str, Any]], variables: Dict[str, Any], purchase_no: str) -> list[Dict[str, Any]]:
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


def _purchase_item_brief(item: Dict[str, Any]) -> Dict[str, Any]:
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


def _purchase_order_detail_id(item: Dict[str, Any]) -> str:
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


def _purchase_wait_pay_fields(variables: Dict[str, Any], purchase_no: str, with_status: bool = True) -> OrderedDict[str, Any]:
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


def _select_purchase_wait_pay(rows: list[Dict[str, Any]], purchase_no: str) -> Dict[str, Any] | None:
    for row in rows:
        if purchase_no and str(row.get("purchase_no") or "") == purchase_no:
            return row
    return rows[0] if rows else None


def _finance_purchase_brief(row: Dict[str, Any] | None) -> Dict[str, Any]:
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


def _follow_list_fields(variables: Dict[str, Any], purchase_no: str, order_sn: str, status_value: str | None = None) -> OrderedDict[str, Any]:
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


def _flatten_follow_items(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
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


def _preview_rows_from_payload(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        rows = data.get("data") or data.get("list") or data.get("rows") or []
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        return [data]
    return []


def _preview_items(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
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


def _order_purchase_id(item: Dict[str, Any]) -> Any:
    return item.get("order_purchase_id") or item.get("id") or item.get("purchase_id")


def _item_up_num(item: Dict[str, Any]) -> str:
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


def _items_already_checking(items: list[Dict[str, Any]]) -> bool:
    if not items:
        return False
    statuses = []
    for item in items:
        try:
            statuses.append(int(item.get("status") or 0))
        except (TypeError, ValueError):
            statuses.append(0)
    return bool(statuses) and all(status >= 40 for status in statuses)


def _first_preview_user_id(rows: list[Dict[str, Any]], items: list[Dict[str, Any]]) -> str:
    for row in rows:
        user = row.get("user")
        if isinstance(user, dict) and user.get("id") not in (None, ""):
            return str(user.get("id"))
    for item in items:
        if item.get("_preview_user_id") not in (None, ""):
            return str(item.get("_preview_user_id"))
    return ""


def _unique_values(values: list[Any]) -> list[Any]:
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


def _purchase_status_code(item: Dict[str, Any]) -> int | None:
    for key in ["status", "_order_status"]:
        value = item.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _purchase_still_pending(item: Dict[str, Any]) -> bool:
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


def _verify_purchase_to_shelf_completed(
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


def _walk_grid_candidates(value: Any, result: list[Dict[str, Any]]) -> None:
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


def _grid_candidates(warehouse_data: Any, warehouse_index: str) -> list[Dict[str, Any]]:
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


def _select_grid_from_payload(payload: Dict[str, Any], variables: Dict[str, Any]) -> Dict[str, Any] | None:
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


def _step(log: Dict[str, Any], name: str, payload: Dict[str, Any], request: Dict[str, Any] | None = None, extra: Dict[str, Any] | None = None) -> None:
    item = {"name": name, **_payload_brief(payload)}
    if request is not None:
        item["request"] = dict(request)
    if extra:
        item.update(extra)
    log.setdefault("steps", []).append(item)


def run_purchase_to_shelf_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (variables.get("backend_base_url") or env.base_url or bulk_cart.BASE_URL).rstrip("/")
    order_sn = str(variables.get("order_sn") or variables.get("last_order_sn") or "").strip()
    purchase_no = str(variables.get("purchase_no") or "").strip() or _purchase_timestamp_no()
    log: Dict[str, Any] = {
        "script": PURCHASE_TO_SHELF_SCRIPT_NAME,
        "mode": "purchase_to_shelf",
        "base_url": base_url,
        "order_sn": order_sn,
        "purchase_no": purchase_no,
        "started_at": datetime.now(),
        "steps": [],
    }

    try:
        session = _admin_session_from(variables)
        login_payload, token = _admin_login(session, base_url, variables, timeout)
        log["login"] = {
            **_payload_brief(login_payload),
            "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
            "token_extracted": bool(token),
        }
        if not _api_success(login_payload) or not token:
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u540e\u53f0\u767b\u5f55\u5931\u8d25"},
            )

        list_fields = _purchase_list_fields(variables, order_sn)
        list_payload = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_purchase_list", "/purchase.purchaseList"),
            list_fields,
            timeout,
        )
        purchase_rows = _admin_rows_from_payload(list_payload)
        purchase_items = _select_purchase_items(_flatten_purchase_items(purchase_rows), order_sn, variables)
        _step(
            log,
            "purchase_list",
            list_payload,
            list_fields,
            {
                "row_count": len(purchase_rows),
                "selected_count": len(purchase_items),
                "selected_items": [_purchase_item_brief(item) for item in purchase_items[:20]],
            },
        )
        if not _api_success(list_payload) or not purchase_items:
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {
                    "order_sn": order_sn,
                    "purchase_no": purchase_no,
                    "selected_count": len(purchase_items),
                    "reason": "\u672a\u67e5\u8be2\u5230\u53ef\u64cd\u4f5c\u7684\u5f85\u62cd\u4e0b\u5546\u54c1",
                },
            )
        if _checkpoint_requested(variables, "pending_purchase"):
            return _finish_paused(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                "pending_purchase",
                {
                    "order_sn": order_sn,
                    "purchase_no": purchase_no,
                    "selected_count": len(purchase_items),
                    "purchase_items": [_purchase_item_brief(item) for item in purchase_items[:20]],
                },
            )

        save_rows, ids = _purchase_save_rows(purchase_items, variables, purchase_no)
        if not save_rows or not ids:
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u5f85\u62cd\u4e0b\u5546\u54c1\u7f3a\u5c11\u53ef\u63d0\u4ea4\u7684\u91c7\u8d2dID"},
            )

        save_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_purchase_save_temp", "/purchase.saveTemp"),
            {"data": save_rows},
            timeout,
        )
        _step(log, "purchase_save_temp", save_payload, {"data_count": len(save_rows), "purchase_no": purchase_no})
        if not _api_success(save_payload):
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u4fdd\u5b58\u4ea4\u6613\u53f7\u5931\u8d25"},
            )
        if _checkpoint_requested(variables, "purchase_no_saved"):
            return _finish_paused(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                "purchase_no_saved",
                {"order_sn": order_sn, "purchase_no": purchase_no, "purchase_ids": ids, "selected_count": len(purchase_items)},
            )

        modify_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_purchase_to_wait_modify_price", "/purchase.toWaitModifyPrice"),
            {"ids": ids, "purchase_no": [purchase_no for _ in ids]},
            timeout,
        )
        _step(log, "purchase_to_wait_modify_price", modify_payload, {"ids": ids, "purchase_no": purchase_no})
        if not _api_success(modify_payload):
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u6807\u8bb0\u5f85\u6539\u4ef7\u5931\u8d25"},
            )
        if _checkpoint_requested(variables, "purchase_wait_modify_price"):
            return _finish_paused(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                "purchase_wait_modify_price",
                {"order_sn": order_sn, "purchase_no": purchase_no, "purchase_ids": ids, "selected_count": len(purchase_items)},
            )

        transition_delay = _as_float(variables.get("purchase_transition_delay"), 1.0)
        if transition_delay > 0:
            time.sleep(transition_delay)

        relist_payload = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_purchase_list", "/purchase.purchaseList"),
            list_fields,
            timeout,
        )
        relist_items_all = _flatten_purchase_items(_admin_rows_from_payload(relist_payload))
        selected_id_set = {str(item_id) for item_id in ids}
        relist_items = [item for item in relist_items_all if str(_purchase_item_id(item) or "") in selected_id_set]
        if relist_items:
            purchase_items = relist_items
        _step(
            log,
            "purchase_relist_after_modify",
            relist_payload,
            list_fields,
            {"selected_count": len(relist_items), "selected_items": [_purchase_item_brief(item) for item in relist_items[:20]]},
        )

        wait_save_rows, ids = _purchase_save_rows(purchase_items, variables, purchase_no)
        wait_save_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_purchase_save_temp", "/purchase.saveTemp"),
            {"data": wait_save_rows},
            timeout,
        )
        _step(log, "purchase_save_temp_before_wait_pay", wait_save_payload, {"data_count": len(wait_save_rows), "purchase_no": purchase_no})
        if not _api_success(wait_save_payload):
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u5f85\u8d22\u52a1\u4ed8\u6b3e\u524d\u4fdd\u5b58\u5931\u8d25"},
            )

        wait_pay_rows = _purchase_wait_pay_rows(purchase_items, variables, purchase_no)
        wait_pay_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_purchase_to_wait_pay", "/purchase.toWaitPay"),
            {"data": wait_pay_rows, "ids": ids},
            timeout,
        )
        _step(log, "purchase_to_wait_pay", wait_pay_payload, {"data_count": len(wait_pay_rows), "ids": ids, "purchase_no": purchase_no})
        if not _api_success(wait_pay_payload):
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u63d0\u4ea4\u5f85\u8d22\u52a1\u4ed8\u6b3e\u5931\u8d25"},
            )
        if _checkpoint_requested(variables, "purchase_wait_pay"):
            return _finish_paused(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                "purchase_wait_pay",
                {"order_sn": order_sn, "purchase_no": purchase_no, "purchase_ids": ids, "selected_count": len(purchase_items)},
            )

        retry_delay = _as_float(variables.get("finance_confirm_delay"), 2.0)
        retries = _as_int(variables.get("finance_confirm_retries"), 8)
        finance_rows: list[Dict[str, Any]] = []
        selected_finance: Dict[str, Any] | None = None
        finance_payload: Dict[str, Any] = {}
        finance_attempts = []
        for attempt in range(retries):
            finance_fields = _purchase_wait_pay_fields(variables, purchase_no, True)
            finance_payload = _post_admin_form(
                session,
                base_url,
                _api_path(variables, "admin_bill_purchase_wait_pay_list", "/bill.purchaseWaitPayList"),
                finance_fields,
                timeout,
            )
            finance_rows = _admin_rows_from_payload(finance_payload)
            selected_finance = _select_purchase_wait_pay(finance_rows, purchase_no)
            attempt_brief = {
                **_payload_brief(finance_payload),
                "attempt": attempt + 1,
                "row_count": len(finance_rows),
                "selected": _finance_purchase_brief(selected_finance),
                "request": dict(finance_fields),
            }
            finance_attempts.append(attempt_brief)
            if _api_success(finance_payload) and selected_finance:
                break
            if attempt == 0:
                fallback_fields = _purchase_wait_pay_fields(variables, purchase_no, False)
                fallback_payload = _post_admin_form(
                    session,
                    base_url,
                    _api_path(variables, "admin_bill_purchase_wait_pay_list", "/bill.purchaseWaitPayList"),
                    fallback_fields,
                    timeout,
                )
                fallback_rows = _admin_rows_from_payload(fallback_payload)
                selected_finance = _select_purchase_wait_pay(fallback_rows, purchase_no)
                finance_attempts.append(
                    {
                        **_payload_brief(fallback_payload),
                        "attempt": "fallback-no-status",
                        "row_count": len(fallback_rows),
                        "selected": _finance_purchase_brief(selected_finance),
                        "request": dict(fallback_fields),
                    }
                )
                if _api_success(fallback_payload) and selected_finance:
                    finance_payload = fallback_payload
                    finance_rows = fallback_rows
                    break
            if attempt < retries - 1:
                time.sleep(retry_delay)
        log["finance_wait_pay_attempts"] = finance_attempts
        if not selected_finance:
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {
                    "order_sn": order_sn,
                    "purchase_no": purchase_no,
                    "reason": "\u4ea4\u6613\u53f7\u4ed8\u6b3e\u5217\u8868\u672a\u627e\u5230\u5f85\u4ed8\u6b3e\u8bb0\u5f55",
                },
            )

        pay_confirm_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_bill_purchase_wait_pay_confirm", "/bill.purchaseWaitPayConfirm"),
            {"purchaseNoSet": [purchase_no]},
            timeout,
        )
        _step(log, "bill_purchase_wait_pay_confirm", pay_confirm_payload, {"purchaseNoSet": [purchase_no]})
        if not _api_success(pay_confirm_payload):
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u4ea4\u6613\u53f7\u4ed8\u6b3e\u786e\u8ba4\u5931\u8d25"},
            )
        if _checkpoint_requested(variables, "purchase_paid"):
            return _finish_paused(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                "purchase_paid",
                {"order_sn": order_sn, "purchase_no": purchase_no, "purchase_ids": ids, "selected_count": len(purchase_items)},
            )

        follow_delay = _as_float(variables.get("follow_delay"), 2.0)
        follow_retries = _as_int(variables.get("follow_retries"), 8)
        follow_payload: Dict[str, Any] = {}
        follow_rows: list[Dict[str, Any]] = []
        follow_attempts = []
        for attempt in range(follow_retries):
            follow_fields = _follow_list_fields(variables, purchase_no, order_sn)
            follow_payload = _post_admin_form(
                session,
                base_url,
                _api_path(variables, "admin_follow_list", "/follow.followList"),
                follow_fields,
                timeout,
            )
            follow_rows = _admin_rows_from_payload(follow_payload)
            follow_items = _flatten_follow_items(follow_rows)
            follow_attempts.append(
                {
                    **_payload_brief(follow_payload),
                    "attempt": attempt + 1,
                    "row_count": len(follow_rows),
                    "item_count": len(follow_items),
                    "request": dict(follow_fields),
                }
            )
            if _api_success(follow_payload) and follow_items:
                break
            if attempt == 0:
                fallback_fields = _follow_list_fields(variables, purchase_no, order_sn, "0")
                fallback_payload = _post_admin_form(
                    session,
                    base_url,
                    _api_path(variables, "admin_follow_list", "/follow.followList"),
                    fallback_fields,
                    timeout,
                )
                fallback_rows = _admin_rows_from_payload(fallback_payload)
                fallback_items = _flatten_follow_items(fallback_rows)
                follow_attempts.append(
                    {
                        **_payload_brief(fallback_payload),
                        "attempt": "fallback-all",
                        "row_count": len(fallback_rows),
                        "item_count": len(fallback_items),
                        "request": dict(fallback_fields),
                    }
                )
                if _api_success(fallback_payload) and fallback_items:
                    follow_payload = fallback_payload
                    follow_rows = fallback_rows
                    break
            if attempt < follow_retries - 1:
                time.sleep(follow_delay)
        log["follow_list_attempts"] = follow_attempts
        if not _api_success(follow_payload) or not _flatten_follow_items(follow_rows):
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u6838\u67e5\u5546\u54c1\u5217\u8868\u672a\u627e\u5230\u5df2\u4ed8\u6b3e\u5546\u54c1"},
            )

        preview_fields = {"purchase_no": purchase_no, "express_no": str(variables.get("express_no") or "")}
        preview_payload = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_follow_up_preview", "/follow.upPreview"),
            preview_fields,
            timeout,
        )
        preview_rows = _preview_rows_from_payload(preview_payload)
        preview_items = _preview_items(preview_rows)
        _step(
            log,
            "follow_up_preview",
            preview_payload,
            preview_fields,
            {"row_count": len(preview_rows), "item_count": len(preview_items)},
        )
        if not _api_success(preview_payload) or not preview_items:
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u672a\u8fdb\u5165\u6838\u67e5\u9884\u89c8\u9875\u6216\u65e0\u53ef\u6838\u67e5\u5546\u54c1"},
            )

        purchase_ids = _unique_values([_order_purchase_id(item) for item in preview_items])
        order_detail_ids = _unique_values([_purchase_order_detail_id(item) for item in purchase_items])
        already_checking = _items_already_checking(preview_items)
        if purchase_ids and (not already_checking or _as_bool(variables.get("force_start_checking"), False)):
            start_payload = _post_admin_urlencoded(
                session,
                base_url,
                _api_path(variables, "admin_follow_start_checking", "/follow.startChecking"),
                {"purchaseIds": purchase_ids},
                timeout,
            )
            _step(log, "follow_start_checking", start_payload, {"purchaseIds": purchase_ids})
            if not _api_success(start_payload):
                return _finish_named(
                    PURCHASE_TO_SHELF_SCRIPT_NAME,
                    log,
                    False,
                    {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u5f00\u59cb\u6838\u67e5\u5931\u8d25"},
                )
        else:
            log["steps"].append({"name": "follow_start_checking", "skipped": True, "already_checking": already_checking})
        if _checkpoint_requested(variables, "checking_started"):
            return _finish_paused(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                "checking_started",
                {
                    "order_sn": order_sn,
                    "purchase_no": purchase_no,
                    "purchase_ids": purchase_ids,
                    "order_detail_ids": order_detail_ids,
                    "selected_count": len(purchase_items),
                    "already_checking": already_checking,
                },
            )

        inspection_delay = _as_float(variables.get("inspection_transition_delay"), 1.0)
        if inspection_delay > 0:
            time.sleep(inspection_delay)
        preview_payload_after = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_follow_up_preview", "/follow.upPreview"),
            preview_fields,
            timeout,
        )
        preview_rows_after = _preview_rows_from_payload(preview_payload_after)
        preview_items_after = _preview_items(preview_rows_after) or preview_items
        if preview_items_after:
            preview_rows = preview_rows_after or preview_rows
            preview_items = preview_items_after
        _step(
            log,
            "follow_up_preview_after_start",
            preview_payload_after,
            preview_fields,
            {"row_count": len(preview_rows_after), "item_count": len(preview_items_after)},
        )

        storage_preview_items = preview_items
        storage_order_detail_ids = order_detail_ids
        tail_pay_passed, tail_pay_summary = _run_order_tail_payment_if_needed(env, variables, log, "before_shelf")
        if not tail_pay_passed:
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {
                    "order_sn": order_sn,
                    "purchase_no": purchase_no,
                    "reason": str(tail_pay_summary.get("reason") or "上架前尾款支付失败"),
                    "order_tail_payment": tail_pay_summary,
                },
            )
        tail_order_detail_ids = _unique_list(
            (tail_pay_summary.get("order_detail_ids") if isinstance(tail_pay_summary.get("order_detail_ids"), list) else [])
            or (tail_pay_summary.get("downstream_order_detail_ids") if isinstance(tail_pay_summary.get("downstream_order_detail_ids"), list) else [])
        )
        if tail_order_detail_ids:
            allowed_detail_ids = set(tail_order_detail_ids)
            storage_preview_items = [item for item in preview_items if _purchase_order_detail_id(item) in allowed_detail_ids]
            storage_order_detail_ids = _unique_values([_purchase_order_detail_id(item) for item in storage_preview_items])
            if not storage_preview_items:
                return _finish_named(
                    PURCHASE_TO_SHELF_SCRIPT_NAME,
                    log,
                    False,
                    {
                        "order_sn": order_sn,
                        "purchase_no": purchase_no,
                        "order_tail_payment": tail_pay_summary,
                        "reason": "已支付尾款的番未匹配到可上架商品",
                    },
                )
        storage_purchase_ids = _unique_values([_order_purchase_id(item) for item in storage_preview_items])

        up_data = []
        for item in storage_preview_items:
            order_purchase_id = _order_purchase_id(item)
            if order_purchase_id in (None, ""):
                continue
            up_data.append(
                {
                    "num": _item_up_num(item),
                    "order_purchase_id": order_purchase_id,
                    "uncomplete_problem_num": item.get("uncomplete_problem_num") or 0,
                }
            )
        if not up_data:
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u672a\u751f\u6210\u53ef\u4e0a\u67b6\u5165\u5e93\u7684\u5546\u54c1\u6570\u636e"},
            )

        userid = str(variables.get("warehouse_user_id") or _first_preview_user_id(preview_rows, preview_items) or "")
        warehouse_fields = {
            "shelf_type_set": variables.get("shelf_type_set") or [1, 3],
            "user_id": userid,
            "order_purchase_id": storage_purchase_ids,
        }
        warehouse_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_wms_grid_preview", "/wms.wmsGridPreview"),
            warehouse_fields,
            timeout,
        )
        selected_grid = _select_grid_from_payload(warehouse_payload, variables)
        _step(
            log,
            "wms_grid_preview",
            warehouse_payload,
            warehouse_fields,
            {"selected_grid": {"id": (selected_grid or {}).get("id"), "grid_number": (selected_grid or {}).get("grid_number")}},
        )
        if not _api_success(warehouse_payload) or not selected_grid:
            return _finish_named(
                PURCHASE_TO_SHELF_SCRIPT_NAME,
                log,
                False,
                {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u672a\u627e\u5230\u53ef\u7528\u5e93\u4f4d"},
            )

        storage_fields = {"grid_id": selected_grid.get("id"), "data": up_data}
        storage_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_follow_up_storage", "/follow.upStorage"),
            storage_fields,
            timeout,
        )
        storage_retry_payload: Dict[str, Any] | None = None
        if str(storage_payload.get("code")) == "10006":
            storage_fields = {"grid_id": selected_grid.get("id"), "data": up_data, "reconfirm": 1}
            storage_retry_payload = _post_admin_urlencoded(
                session,
                base_url,
                _api_path(variables, "admin_follow_up_storage", "/follow.upStorage"),
                storage_fields,
                timeout,
            )
            storage_payload = storage_retry_payload
        _step(
            log,
            "follow_up_storage",
            storage_payload,
            {"grid_id": selected_grid.get("id"), "data_count": len(up_data), "reconfirm": 1 if storage_retry_payload else 0},
            {"grid_number": selected_grid.get("grid_number")},
        )
        passed = _api_success(storage_payload)
        summary = {
            "order_sn": order_sn,
            "purchase_no": purchase_no,
            "selected_count": len(storage_preview_items),
            "purchase_ids": storage_purchase_ids,
            "order_detail_ids": storage_order_detail_ids,
            "order_detail_id": storage_order_detail_ids[0] if storage_order_detail_ids else "",
            "order_tail_payment": tail_pay_summary,
            "grid_id": selected_grid.get("id"),
            "grid_number": selected_grid.get("grid_number"),
            "storage_count": len(up_data),
            "storage_passed": passed,
        }
        if not passed:
            summary["reason"] = str(storage_payload.get("msg") or storage_payload.get("data") or "\u4e0a\u67b6\u5165\u5e93\u5931\u8d25")
        elif _checkpoint_requested(variables, "shelf_stored"):
            return _finish_paused(PURCHASE_TO_SHELF_SCRIPT_NAME, log, "shelf_stored", summary)
        elif _as_bool(variables.get("verify_purchase_to_shelf"), True):
            verify_passed, verify_summary = _verify_purchase_to_shelf_completed(
                session,
                base_url,
                variables,
                order_sn,
                purchase_ids,
                timeout,
                log,
            )
            summary.update(verify_summary)
            passed = verify_passed
        return _finish_named(PURCHASE_TO_SHELF_SCRIPT_NAME, log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            PURCHASE_TO_SHELF_SCRIPT_NAME,
            log,
            False,
            {"order_sn": order_sn, "purchase_no": purchase_no, "error": str(exc)},
        )


def _porder_sn(variables: Dict[str, Any]) -> str:
    configured = str(variables.get("porder_sn") or "").strip()
    if configured:
        return configured
    suffix = str(variables.get("porder_suffix") or variables.get("operation_id") or "300001").strip() or "300001"
    return f"P{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(0, 99):02d}-{suffix}"


def _warehouse_list_fields(variables: Dict[str, Any]) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    for key in ["children_id", "for_sn_set", "tag_set", "client_remark", "sort_type", "hasLabel"]:
        value = variables.get(key)
        if value not in (None, ""):
            fields[key] = value
    keywords = str(variables.get("warehouse_keywords") or "").strip()
    tag = str(variables.get("warehouse_search_tag") or "").strip()
    if keywords:
        if tag in {"\u7ba1\u7406\u756a\u53f7", "for_sn", "for_sn_set"}:
            fields["for_sn_set"] = keywords
        elif tag in {"\u30e9\u30d9\u30eb\u60c5\u5831", "tag", "tag_set"}:
            fields["tag_set"] = keywords
        elif tag in {"\u5099\u8003\u6b04", "client_remark"}:
            fields["client_remark"] = keywords
    _apply_extra_fields(fields, variables.get("warehouse_list_fields"))
    return fields


def _warehouse_candidate_paths(variables: Dict[str, Any]) -> list[str]:
    configured = variables.get("client_warehouse_list") or variables.get("warehouse_list_path")
    paths = []
    if configured:
        paths.append(str(configured))
    api_path = _api_paths(variables).get("client_warehouse_list")
    if api_path:
        paths.append(str(api_path))
    paths.extend(
        [
            "/client/wms.stockAutoList",
            "/client/warehouse.warehouseList",
            "/client/warehouse.goodsList",
            "/client/warehouse.goodsWarehouseList",
            "/client/warehouse.orderDetailList",
            "/client/porder.warehouseList",
            "/client/porder.porderWarehouseList",
            "/client/porder.porderDetailList",
            "/client/order.warehouseList",
        ]
    )
    result = []
    for path in paths:
        if path and path not in result:
            result.append(path)
    return result


def _nested_rows(value: Any, depth: int = 0) -> list[Dict[str, Any]]:
    if depth > 5:
        return []
    rows: list[Dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            rows.extend(_nested_rows(item, depth + 1))
        return rows
    if not isinstance(value, dict):
        return rows
    if any(key in value for key in ["order_detail_id", "order_detailId", "detail_id", "porder_detail_id", "id"]):
        rows.append(value)
    for key in ["data", "list", "rows", "result", "items", "order_detail", "orderDetail", "detail", "details", "goods", "goods_list"]:
        child = value.get(key)
        if isinstance(child, (dict, list)):
            rows.extend(_nested_rows(child, depth + 1))
    return rows


def _field_value(row: Dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _warehouse_item_id(row: Dict[str, Any]) -> str:
    return str(_field_value(row, ["order_detail_id", "order_detailId", "detail_id", "porder_detail_id", "id"]) or "").strip()


def _warehouse_sku_id(row: Dict[str, Any]) -> str:
    return str(
        _field_value(
            row,
            [
                "sku_id",
                "skuId",
                "skuID",
                "spec_id",
                "specId",
                "specID",
                "goods_id",
                "goodsId",
                "goodsID",
            ],
        )
        or _warehouse_item_id(row)
        or ""
    ).strip()


def _warehouse_sendable_num(row: Dict[str, Any]) -> int:
    value = _field_value(
        row,
        [
            "send_num",
            "send_await_num",
            "can_send_num",
            "canSendNum",
            "sendable_num",
            "surplus_num",
            "surplus",
            "stock_num",
            "stock",
            "num",
            "available_num",
            "in_stock_num",
        ],
    )
    return _as_int(value, 0)


def _warehouse_item_brief(row: Dict[str, Any], send_num: int | None = None) -> Dict[str, Any]:
    brief = {
        "order_detail_id": _warehouse_item_id(row),
        "sku_id": _warehouse_sku_id(row),
        "goods_id": _field_value(row, ["goods_id", "goodsId", "goodsID"]),
        "goods_title": _field_value(row, ["goods_title", "goodsTitle", "title", "name"]),
        "sendable_num": _warehouse_sendable_num(row),
    }
    order_sn = _field_value(row, ["order_sn", "orderSn", "orderSN"])
    if order_sn not in (None, ""):
        brief["order_sn"] = order_sn
    if row.get("_warehouse_source"):
        brief["source"] = row.get("_warehouse_source")
    if send_num is not None:
        brief["send_num"] = send_num
    return brief


def _warehouse_requested_order_detail_ids(variables: Dict[str, Any]) -> list[str]:
    ids = _as_list(variables.get("order_detail_ids"), [])
    for key in ["order_detail_id", "porder_detail_id"]:
        value = variables.get(key)
        if value not in (None, ""):
            ids.append(str(value).strip())
    return _unique_list(ids)


def _warehouse_row_order_sn(row: Dict[str, Any]) -> str:
    direct = _field_value(row, ["order_sn", "orderSn", "orderSN"])
    if direct not in (None, ""):
        return str(direct).strip()
    return str(_first_deep_value(row, ["order_sn", "orderSn", "orderSN"]) or "").strip()


def _warehouse_row_matches_current_order(row: Dict[str, Any], order_sn: str, order_detail_ids: set[str]) -> bool:
    item_id = _warehouse_item_id(row)
    if order_detail_ids and item_id in order_detail_ids:
        return True
    return bool(order_sn and _warehouse_row_order_sn(row) == order_sn)


def _select_warehouse_items(rows: list[Dict[str, Any]], variables: Dict[str, Any], limit: int = 1) -> list[Dict[str, Any]]:
    requested_id = str(variables.get("order_detail_id") or variables.get("porder_detail_id") or "").strip()
    requested_ids = _warehouse_requested_order_detail_ids(variables)
    requested_id_set = set(requested_ids)
    order_sn = str(variables.get("warehouse_order_sn") or variables.get("order_sn") or "").strip()
    fill_scope = str(variables.get("warehouse_fill_scope") or "").strip().lower()
    require_full_count = _as_bool(variables.get("require_warehouse_sku_count"), False)
    current_first = fill_scope in {"current_order", "current_order_then_history"} or bool(requested_id_set and limit > 1) or bool(order_sn)
    allow_history = fill_scope != "current_order"
    target_count = max(1, limit)
    selected: list[Dict[str, Any]] = []
    seen_skus: set[str] = set()
    seen_item_ids: set[str] = set()

    def add(row: Dict[str, Any], *, force: bool = False, source: str = "history") -> bool:
        item_id = _warehouse_item_id(row)
        if not item_id:
            return False
        if not force and _warehouse_sendable_num(row) <= 0:
            return False
        if item_id in seen_item_ids:
            return False
        sku_id = _warehouse_sku_id(row) or item_id
        if sku_id in seen_skus:
            return False
        selected_row = dict(row)
        selected_row["_warehouse_source"] = source
        selected.append(selected_row)
        seen_skus.add(sku_id)
        seen_item_ids.add(item_id)
        return len(selected) >= target_count

    if current_first:
        for row in rows:
            if _warehouse_row_matches_current_order(row, order_sn, requested_id_set) and add(row, source="current_order"):
                return selected
        if len(selected) >= target_count or not allow_history:
            return selected

    if requested_id:
        for row in rows:
            if _warehouse_item_id(row) == requested_id:
                add(row, force=not require_full_count, source="current_order")
                break
        if not selected and not require_full_count:
            add({"order_detail_id": requested_id, "send_num": _as_int(variables.get("send_num"), 1)}, force=True, source="current_order")
        if len(selected) >= target_count:
            return selected

    if not allow_history:
        return selected
    for row in rows:
        if add(row, source="history"):
            break
    return selected


def _select_warehouse_item(rows: list[Dict[str, Any]], variables: Dict[str, Any]) -> Dict[str, Any] | None:
    selected = _select_warehouse_items(rows, variables, 1)
    return selected[0] if selected else None


def _address_fields(prefix: str, values: Dict[str, Any]) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    for key in [
        "name",
        "company",
        "address",
        "zip",
        "mobile",
        "tel",
        "name_rome",
        "address_rome",
        "corporate_name",
        "account",
        "standard_code",
        "title",
    ]:
        fields[f"{prefix}[{key}]"] = values.get(key, "")
    return fields


def _default_receiver_address() -> Dict[str, Any]:
    return {
        "name": "\u6d4b\u8bd5",
        "company": "\u6d4b\u8bd5\u516c\u53f8\u540d",
        "address": "\u4f4f\u6240",
        "zip": "12345678",
        "mobile": "1353214567",
        "tel": "0321-55786",
        "name_rome": "\u30ed\u30fc\u30de\u5b57(\u6c0f\u540d)",
        "address_rome": "\u30ed\u30fc\u30de\u5b57(\u4f4f\u6240)",
        "corporate_name": "1234567891234",
        "account": "1234567889789",
        "standard_code": "1234567891235",
        "title": "\u9648\u54e5\u6700\u7231\u5199bug",
    }


def _default_importer_address() -> Dict[str, Any]:
    return {
        "name": "13123",
        "company": "",
        "address": "123123",
        "zip": "1232132",
        "mobile": "123123",
        "tel": "",
        "name_rome": "12312313",
        "address_rome": "123123123",
        "corporate_name": "",
        "account": "\u30ea\u30a2\u30eb\u30bf\u30a4\u30e0\u53e3\u5ea7\u5c0f\u6768",
        "standard_code": "\u6a19\u6e96\u30b3\u30fc\u30c9\u5c0f\u6768",
        "title": "\u6c0f\u540d",
    }


def _merge_address(defaults: Dict[str, Any], configured: Any) -> Dict[str, Any]:
    result = dict(defaults)
    if isinstance(configured, dict):
        for key, value in configured.items():
            result[str(key)] = value
    return result


def _porder_create_fields_for_items(items: list[Dict[str, Any]], porder_sn: str, variables: Dict[str, Any]) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["create_type"] = str(variables.get("create_type") or "send")
    fields["porder_sn"] = porder_sn
    fields["logistics_id"] = str(variables.get("porder_logistics_id") or variables.get("logistics_id") or "14")
    fields["client_remark"] = str(variables.get("client_remark") or "")
    for index, item in enumerate(items):
        prefix = f"porder_detail[{index}]"
        fields[f"{prefix}[order_detail_id]"] = str(item.get("order_detail_id") or "")
        fields[f"{prefix}[send_num]"] = _as_int(item.get("send_num"), 1)
        fields[f"{prefix}[client_remark]"] = str(item.get("client_remark") or variables.get("porder_detail_remark") or "自动化配送单明细备注")
    receiver = _merge_address(_default_receiver_address(), variables.get("receiver_address"))
    importer = _merge_address(_default_importer_address(), variables.get("importer_address"))
    fields.update(_address_fields("receiver_address", receiver))
    fields.update(_address_fields("importer_address", importer))
    fields["is_amazon"] = str(variables.get("is_amazon") or "0")
    _apply_extra_fields(fields, variables.get("porder_create_fields"))
    return fields


def _porder_create_fields(order_detail_id: str, porder_sn: str, send_num: int, variables: Dict[str, Any]) -> OrderedDict[str, Any]:
    return _porder_create_fields_for_items(
        [{"order_detail_id": order_detail_id, "send_num": send_num, "client_remark": variables.get("porder_detail_remark") or "自动化配送单明细备注"}],
        porder_sn,
        variables,
    )


def _extract_porder_sn(payload: Dict[str, Any], fallback: str) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ["porder_sn", "porderSn", "sn", "order_sn"]:
            value = data.get(key)
            if value:
                return str(value)
    if isinstance(data, str) and data.strip().startswith("P"):
        return data.strip()
    for key in ["porder_sn", "porderSn", "sn"]:
        value = payload.get(key)
        if value:
            return str(value)
    return fallback


def _walk_dicts(value: Any, depth: int = 0) -> list[Dict[str, Any]]:
    if depth > 8:
        return []
    if isinstance(value, list):
        rows: list[Dict[str, Any]] = []
        for item in value:
            rows.extend(_walk_dicts(item, depth + 1))
        return rows
    if not isinstance(value, dict):
        return []
    rows = [value]
    for item in value.values():
        if isinstance(item, (dict, list)):
            rows.extend(_walk_dicts(item, depth + 1))
    return rows


def _first_deep_value(value: Any, keys: list[str]) -> Any:
    for row in _walk_dicts(value):
        for key in keys:
            item = row.get(key)
            if item not in (None, "", [], {}):
                return item
    return ""


def _porder_detail_rows(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = payload.get("data")
    roots = [data, payload]
    rows: list[Dict[str, Any]] = []
    detail_keys = [
        "porder_detail",
        "porderDetail",
        "porder_detail_list",
        "porderDetailList",
        "detail",
        "details",
        "list",
    ]
    for root in roots:
        if isinstance(root, dict):
            for key in detail_keys:
                child = root.get(key)
                if isinstance(child, (dict, list)):
                    rows.extend(_nested_rows(child))
        elif isinstance(root, list):
            rows.extend(_nested_rows(root))
    filtered: list[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _field_value(row, ["porder_detail_id", "porderDetailId", "detail_id", "id"]) in (None, ""):
            continue
        if any(key in row for key in ["porder_sn", "goods_id", "goods_name", "send_num", "wait_box_num", "received_num", "order_detail_id"]):
            filtered.append(row)
    return filtered or [row for row in rows if isinstance(row, dict)]


def _porder_detail_id(row: Dict[str, Any]) -> str:
    return str(_field_value(row, ["porder_detail_id", "porderDetailId", "detail_id", "id"]) or "").strip()


def _porder_wait_box_num(row: Dict[str, Any], fallback: int = 1) -> int:
    value = _field_value(
        row,
        [
            "wait_box_num",
            "waitBoxNum",
            "not_box_num",
            "notBoxNum",
            "packing_num",
            "received_num",
            "send_num",
            "num",
        ],
    )
    number = _as_int(value, fallback)
    return number if number > 0 else fallback


def _box_need_num(value: Any, fallback_num: int) -> int:
    fallback = max(1, _as_int(fallback_num, 1))
    number = _as_int(value, fallback)
    if number <= 0:
        return fallback
    return min(number, fallback)


def _extract_freight_id(*payloads: Dict[str, Any], variables: Dict[str, Any] | None = None) -> str:
    variables = variables or {}
    configured = str(variables.get("freight_id") or variables.get("porder_freight_id") or "").strip()
    if configured:
        return configured
    freight_shape_keys = {
        "freight_id",
        "freightId",
        "freightID",
        "logistics_id",
        "logisticsId",
        "length",
        "width",
        "height",
        "weight",
        "box_no",
        "boxNo",
        "box_num",
        "boxNum",
        "porder_sn",
    }
    for payload in payloads:
        direct = _first_deep_value(payload, ["freight_id", "freightId", "freightID"])
        if direct not in (None, ""):
            return str(direct).strip()
        freight_set = _first_deep_value(payload, ["freight_id_set", "freightIdSet", "freight_ids"])
        if isinstance(freight_set, list) and freight_set:
            return str(freight_set[0]).strip()
        for row in _walk_dicts(payload):
            row_id = row.get("id")
            if row_id in (None, ""):
                continue
            if any(key in row and row.get(key) not in (None, "") for key in freight_shape_keys):
                return str(row_id).strip()
    return ""


def _payload_structure_sample(payload: Dict[str, Any], limit: int = 8) -> list[Dict[str, Any]]:
    samples: list[Dict[str, Any]] = []
    for row in _walk_dicts(payload):
        if not row:
            continue
        keys = list(row.keys())[:20]
        interesting = {
            key: row.get(key)
            for key in [
                "id",
                "porder_detail_id",
                "porderDetailId",
                "stock_id",
                "stockId",
                "wms_stock_id",
                "num",
                "num_need",
                "need_num",
                "stock_num",
                "storage_num",
                "send_num",
                "wait_box_num",
            ]
            if key in row
        }
        samples.append({"keys": keys, "interesting": interesting})
        if len(samples) >= limit:
            break
    return samples


def _freight_box_brief(payload: Dict[str, Any], limit: int = 10) -> list[Dict[str, Any]]:
    boxes: list[Dict[str, Any]] = []
    freight_keys = {
        "number",
        "status",
        "length",
        "width",
        "height",
        "weight",
        "logistics_id",
        "box_id",
        "volume",
        "charge_weight",
        "freight_id",
    }
    for row in _walk_dicts(payload):
        if row.get("id") in (None, ""):
            continue
        if not any(key in row for key in freight_keys):
            continue
        boxes.append(
            {
                "id": row.get("id"),
                "porder_sn": row.get("porder_sn"),
                "number": row.get("number"),
                "status": row.get("status"),
                "statusName": row.get("statusName") or row.get("status_name"),
                "length": row.get("length"),
                "width": row.get("width"),
                "height": row.get("height"),
                "weight": row.get("weight"),
                "logistics_id": row.get("logistics_id"),
                "box_id": row.get("box_id"),
                "freight_id": row.get("freight_id"),
            }
        )
        if len(boxes) >= limit:
            break
    return boxes


def _has_incomplete_freight_box(payload: Dict[str, Any]) -> bool:
    boxes = _freight_box_brief(payload)
    for box in boxes:
        status = box.get("status")
        status_name = str(box.get("statusName") or "")
        if status in (None, "", 0, "0", False) or "未完成" in status_name or "空箱" in status_name:
            return True
    return False


def _porder_complete_box_paths(variables: Dict[str, Any]) -> list[str]:
    paths: list[str] = []
    api_paths = _api_paths(variables)
    configured = api_paths.get("admin_porder_complete_box") or variables.get("admin_porder_complete_box_path")
    if configured:
        paths.append(str(configured))
    paths.extend(_as_list(variables.get("porder_complete_box_paths"), []))
    paths.append("/porder.completeBox")
    normalized = []
    for path in _unique_list(paths):
        normalized.append(path if path.startswith("/") else f"/{path}")
    return normalized


def _extract_stock_item(payload: Dict[str, Any], fallback_num: int, porder_detail_id: str = "") -> Dict[str, Any]:
    configured_stock_id = str(payload.get("stock_id") or "").strip()
    if configured_stock_id:
        return {"stock_id": configured_stock_id, "num_need": _box_need_num(fallback_num, fallback_num)}
    stock_shape_keys = {
        "stock_id",
        "stockId",
        "wms_stock_id",
        "wmsStockId",
        "stock_num",
        "stockNum",
        "storage_num",
        "storageNum",
        "num_need",
        "need_num",
        "grid_id",
        "warehouse_id",
        "order_purchase_id",
        "putaway_at",
    }
    for row in _walk_dicts(payload):
        stock_id = _field_value(row, ["stock_id", "stockId", "wms_stock_id", "wmsStockId", "stockDetailId", "stock_detail_id"])
        if stock_id not in (None, ""):
            return {
                "stock_id": str(stock_id).strip(),
                "num_need": _box_need_num(
                    _field_value(row, ["num_need", "need_num", "send_num", "wait_box_num", "stock_num", "storage_num", "num"]),
                    fallback_num,
                ),
            }
    for row in _walk_dicts(payload):
        for stock_key in ["stock", "stocks", "stock_list", "stockList", "wms_stock", "wmsStock", "storage", "storage_list", "storageList"]:
            stock = row.get(stock_key)
            if not isinstance(stock, list):
                continue
            for item in stock:
                if isinstance(item, dict) and item.get("id") not in (None, ""):
                    return {
                        "stock_id": str(item.get("id")).strip(),
                        "num_need": _box_need_num(
                            _field_value(item, ["num_need", "need_num", "send_num", "wait_box_num", "stock_num", "storage_num", "num"]),
                            fallback_num,
                        ),
                    }
    candidate_ids: list[tuple[str, int]] = []
    for row in _walk_dicts(payload):
        row_id = row.get("id")
        if row_id in (None, "") or str(row_id) == str(porder_detail_id):
            continue
        if any(key in row and row.get(key) not in (None, "") for key in stock_shape_keys):
            candidate_ids.append(
                (
                    str(row_id).strip(),
                    _box_need_num(
                        _field_value(row, ["num_need", "need_num", "send_num", "wait_box_num", "stock_num", "storage_num", "num"]),
                        fallback_num,
                    ),
                )
            )
    if len(candidate_ids) == 1:
        stock_id, num_need = candidate_ids[0]
        return {"stock_id": stock_id, "num_need": num_need}
    return {"stock_id": "", "num_need": _box_need_num(fallback_num, fallback_num)}


def _stock_item_from_row(row: Dict[str, Any], fallback_num: int) -> Dict[str, Any]:
    stock_id = _field_value(row, ["stock_id", "stockId", "wms_stock_id", "wmsStockId", "stockDetailId", "stock_detail_id"])
    if stock_id not in (None, ""):
        return {
            "stock_id": str(stock_id).strip(),
            "num_need": _box_need_num(
                _field_value(row, ["num_need", "need_num", "send_num", "wait_box_num", "stock_num", "storage_num", "num"]),
                fallback_num,
            ),
        }
    for stock_key in ["stock", "stocks", "stock_list", "stockList", "wms_stock", "wmsStock", "storage", "storage_list", "storageList"]:
        stock = row.get(stock_key)
        stock_rows = stock if isinstance(stock, list) else [stock] if isinstance(stock, dict) else []
        for item in stock_rows:
            if not isinstance(item, dict):
                continue
            item_id = _field_value(item, ["stock_id", "stockId", "wms_stock_id", "wmsStockId", "stockDetailId", "stock_detail_id", "id"])
            if item_id not in (None, ""):
                return {
                    "stock_id": str(item_id).strip(),
                    "num_need": _box_need_num(
                        _field_value(item, ["num_need", "need_num", "send_num", "wait_box_num", "stock_num", "storage_num", "num"]),
                        fallback_num,
                    ),
                }
    return {"stock_id": "", "num_need": _box_need_num(fallback_num, fallback_num)}


def _extract_stock_item_for_detail(
    payload: Dict[str, Any],
    porder_detail_id: str,
    fallback_num: int,
    *,
    allow_global_fallback: bool = False,
) -> Dict[str, Any]:
    detail_id = str(porder_detail_id or "").strip()
    for row in _walk_dicts(payload):
        row_detail_id = str(_field_value(row, ["porder_detail_id", "porderDetailId", "detail_id", "detailId"]) or "").strip()
        row_id = str(row.get("id") or "").strip()
        if detail_id and detail_id not in {row_detail_id, row_id}:
            continue
        stock_item = _stock_item_from_row(row, fallback_num)
        if stock_item.get("stock_id"):
            return stock_item
    if allow_global_fallback:
        return _extract_stock_item(payload, fallback_num, detail_id)
    return {"stock_id": "", "num_need": _box_need_num(fallback_num, fallback_num)}


def _porder_flow_detail_items(rows: list[Dict[str, Any]], fallback_num: int = 1) -> list[Dict[str, Any]]:
    items: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        porder_detail_id = _porder_detail_id(row)
        if not porder_detail_id or porder_detail_id in seen:
            continue
        seen.add(porder_detail_id)
        items.append(
            {
                "porder_detail_id": porder_detail_id,
                "wait_box_num": _porder_wait_box_num(row, fallback_num),
            }
        )
    return items


def _porder_detail_payload(
    session: requests.Session,
    base_url: str,
    variables: Dict[str, Any],
    porder_sn: str,
    timeout: int,
    retries: int = 4,
) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    payload: Dict[str, Any] = {}
    rows: list[Dict[str, Any]] = []
    for attempt in range(retries + 1):
        payload = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_porder_detail", "/porder.detail"),
            {"porder_sn": porder_sn},
            timeout,
        )
        rows = _porder_detail_rows(payload)
        if _api_success(payload) and rows:
            return payload, rows
        if attempt < retries:
            time.sleep(0.8 * (attempt + 1))
    return payload, rows


def _porder_detail_brief(payload: Dict[str, Any], rows: list[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        **_payload_brief(payload),
        "detail_count": len(rows),
        "details": [
            {
                "id": _porder_detail_id(row),
                "goods_id": row.get("goods_id"),
                "num": row.get("num"),
                "send_num": row.get("send_num"),
                "wait_box_num": row.get("wait_box_num"),
                "received_num": row.get("received_num"),
                "freight_id": row.get("freight_id"),
                "status": row.get("status"),
                "statusName": row.get("statusName") or row.get("status_name"),
            }
            for row in rows[:10]
        ],
    }


def _run_backend_porder_flow(
    base_url: str,
    timeout: int,
    variables: Dict[str, Any],
    porder_sn: str,
    log: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    backend_log: Dict[str, Any] = {"porder_sn": porder_sn, "steps": []}
    log["backend_porder"] = backend_log
    session = _admin_session_from(variables)

    login_payload, token = _admin_login(session, base_url, variables, timeout)
    session.headers.update(
        {
            "AdminToken": f"Bearer {token}" if token else "",
            "adminToken": f"Bearer {token}" if token else "",
            "Fingerprint": str(variables.get("fingerprint") or "35d3d2dc553624bd3e6cc32688f4e43b"),
            "PageUrlTrace": f"https://jpmanage.rakumart.cn/#/porderDetail?porder_sn={porder_sn}",
            "Origin": "https://jpmanage.rakumart.cn",
            "Referer": "https://jpmanage.rakumart.cn/",
        }
    )
    backend_log["login"] = {
        **_payload_brief(login_payload),
        "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
        "token_extracted": bool(token),
    }
    if not _api_success(login_payload) or not token:
        return False, {"backend_passed": False, "reason": "后台登录失败"}

    detail_payload, detail_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout)
    backend_log["detail_before"] = _porder_detail_brief(detail_payload, detail_rows)
    if not _api_success(detail_payload) or not detail_rows:
        return False, {"backend_passed": False, "reason": "未获取到配送单详情"}

    default_box_num = _as_int(variables.get("backend_box_num"), 1)
    detail_items = _porder_flow_detail_items(detail_rows, default_box_num)
    if not detail_items:
        return False, {"backend_passed": False, "reason": "配送单详情缺少 porder_detail_id"}

    porder_detail_ids = [item["porder_detail_id"] for item in detail_items]
    porder_detail_id = porder_detail_ids[0]

    translate_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_submit_translate", "/porder.submitTranslate"),
        {
            "porder_sn": porder_sn,
            "client_remark_translate": str(variables.get("client_remark_translate") or "自动化配送单翻译"),
            "list": [{"id": item["porder_detail_id"], "y_remark": str(variables.get("porder_y_remark") or "自动化装箱")} for item in detail_items],
            "is_temp": str(variables.get("porder_translate_is_temp") or "0"),
        },
        timeout,
    )
    backend_log["submit_translate"] = {**_payload_brief(translate_payload), "porder_detail_ids": porder_detail_ids}
    if not _api_success(translate_payload):
        return False, {"backend_passed": False, "reason": "配送单提交配货失败", "submit_translate": _payload_brief(translate_payload)}

    _, after_translate_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout, retries=2)
    if after_translate_rows:
        translated_items = _porder_flow_detail_items(after_translate_rows, default_box_num)
        if translated_items:
            detail_items = translated_items
            porder_detail_ids = [item["porder_detail_id"] for item in detail_items]
            porder_detail_id = porder_detail_ids[0]
    backend_log["detail_after_translate"] = {"detail_count": len(after_translate_rows), "porder_detail_ids": porder_detail_ids}
    if _checkpoint_requested(variables, "porder_translated"):
        return True, _paused_summary(
            "porder_translated",
            {
                "porder_sn": porder_sn,
                "porder_detail_id": porder_detail_id,
                "porder_detail_ids": porder_detail_ids,
                "backend_passed": True,
                "backend_steps": ["login", "porder_detail", "submit_translate"],
            },
        )

    box_fields = {
        "porder_sn": porder_sn,
        "count": str(variables.get("box_count") or "1"),
        "length": str(variables.get("box_length") or "58"),
        "width": str(variables.get("box_width") or "51"),
        "height": str(variables.get("box_height") or "50"),
        "weight": str(variables.get("box_weight") or "10"),
    }
    add_box_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_add_box", "/porder.addBox"),
        box_fields,
        timeout,
    )
    backend_log["add_box"] = {**_payload_brief(add_box_payload), "request": box_fields}
    if not _api_success(add_box_payload):
        return False, {"backend_passed": False, "reason": "配送单添加箱子失败", "add_box": _payload_brief(add_box_payload)}

    freight_before_box_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
        {"porder_sn": porder_sn},
        timeout,
    )
    detail_after_box_payload, detail_after_box_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout, retries=1)
    backend_log["freight_list_before_box"] = {
        **_payload_brief(freight_before_box_payload),
        "sample": _payload_structure_sample(freight_before_box_payload, limit=4),
    }
    backend_log["detail_after_add_box"] = _porder_detail_brief(detail_after_box_payload, detail_after_box_rows)

    preview_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_into_box_preview", "/porder.intoBoxPreview"),
        {"porderDetailIdS": porder_detail_ids},
        timeout,
    )
    stock_items: list[Dict[str, Any]] = []
    for item in detail_items:
        stock_item = _extract_stock_item_for_detail(
            preview_payload,
            item["porder_detail_id"],
            _as_int(item.get("wait_box_num"), default_box_num),
            allow_global_fallback=len(detail_items) == 1,
        )
        box_num = _box_need_num(stock_item.get("num_need"), _as_int(item.get("wait_box_num"), default_box_num))
        stock_items.append(
            {
                "porder_detail_id": item["porder_detail_id"],
                "stock_id": stock_item.get("stock_id") or "",
                "num_need": stock_item.get("num_need"),
                "box_num": box_num,
            }
        )
    freight_id = _extract_freight_id(
        freight_before_box_payload,
        detail_after_box_payload,
        add_box_payload,
        preview_payload,
        detail_payload,
        variables=variables,
    )
    backend_log["into_box_preview"] = {
        **_payload_brief(preview_payload),
        "porder_detail_id": porder_detail_id,
        "porder_detail_ids": porder_detail_ids,
        "freight_id": freight_id,
        "stock_items": stock_items,
        "sample": _payload_structure_sample(preview_payload, limit=8),
    }
    if not _api_success(preview_payload):
        return False, {"backend_passed": False, "reason": "装箱预览失败", "into_box_preview": _payload_brief(preview_payload)}
    if not freight_id:
        return False, {"backend_passed": False, "reason": "未拿到箱子 freight_id，无法装箱"}
    missing_stock_items = [item for item in stock_items if not item.get("stock_id")]
    if missing_stock_items:
        return False, {
            "backend_passed": False,
            "reason": "\u672a\u6309\u914d\u9001\u5355\u8be6\u60c5\u5339\u914d\u5230\u5e93\u5b58 stock_id\uff0c\u65e0\u6cd5\u88c5\u7bb1",
            "missing_porder_detail_ids": [item["porder_detail_id"] for item in missing_stock_items],
        }
    stock_item = stock_items[0]
    if False and not stock_item.get("stock_id"):
        return False, {"backend_passed": False, "reason": "未拿到库存 stock_id，无法装箱"}

    box_num = _as_int(stock_item.get("box_num"), 1)
    into_box_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_into_box_submit", "/porder.intoBoxSubmit"),
        {
            "freight_id_set": [freight_id],
            "list": [
                {
                    "per_num": item["box_num"],
                    "porder_detail_id": item["porder_detail_id"],
                    "stock": [{"stock_id": item["stock_id"], "num_need": item["box_num"]}],
                }
                for item in stock_items
            ],
        },
        timeout,
    )
    backend_log["into_box_submit"] = {**_payload_brief(into_box_payload), "box_num": box_num, "box_nums": {item["porder_detail_id"]: item["box_num"] for item in stock_items}}
    if not _api_success(into_box_payload):
        return False, {"backend_passed": False, "reason": "装箱提交失败", "into_box_submit": _payload_brief(into_box_payload)}

    time.sleep(float(variables.get("after_box_submit_delay") or 0.8))
    detail_after_into_box_payload = _post_admin_form(
        session,
        base_url,
        _api_path(variables, "admin_porder_detail", "/porder.detail"),
        {"porder_sn": porder_sn, "filterByFreightNum": "false"},
        timeout,
    )
    detail_after_into_box_rows = _porder_detail_rows(detail_after_into_box_payload)
    freight_after_into_box_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
        {"porder_sn": porder_sn, "filterByFreightNum": "false"},
        timeout,
    )
    backend_log["detail_after_into_box"] = _porder_detail_brief(detail_after_into_box_payload, detail_after_into_box_rows)
    backend_log["freight_list_after_into_box"] = {
        **_payload_brief(freight_after_into_box_payload),
        "boxes": _freight_box_brief(freight_after_into_box_payload),
        "sample": _payload_structure_sample(freight_after_into_box_payload, limit=4),
    }
    spot_after_into_box_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_spot_porder_detail", "/spot/spot/check/getSpotPorderDetail"),
        {"porder_sn": porder_sn, "filterByFreightNum": "false"},
        timeout,
    )
    backend_log["spot_after_into_box"] = _payload_brief(spot_after_into_box_payload)

    complete_box_attempts: list[Dict[str, Any]] = []
    if _has_incomplete_freight_box(freight_after_into_box_payload):
        complete_box_fields = {**box_fields, "freight_id_set": [freight_id]}
        for complete_box_path in _porder_complete_box_paths(variables):
            try:
                complete_payload = _post_admin_urlencoded(session, base_url, complete_box_path, complete_box_fields, timeout)
                complete_brief = _payload_brief(complete_payload)
            except Exception as exc:
                complete_payload = {"success": False, "message": str(exc)}
                complete_brief = {"success": False, "message": str(exc)}
            time.sleep(float(variables.get("after_complete_box_delay") or 0.8))
            complete_check_payload = _post_admin_urlencoded(
                session,
                base_url,
                _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
                {"porder_sn": porder_sn, "filterByFreightNum": "false"},
                timeout,
            )
            attempt = {
                "path": complete_box_path,
                "request": complete_box_fields,
                "response": complete_brief,
                "boxes": _freight_box_brief(complete_check_payload),
                "box_completed": not _has_incomplete_freight_box(complete_check_payload),
            }
            complete_box_attempts.append(attempt)
            if _api_success(complete_payload) and attempt["box_completed"]:
                break
    else:
        complete_box_attempts.append({"skipped": True, "reason": "freight box already completed"})
    backend_log["complete_box_attempts"] = complete_box_attempts

    to_wait_offer_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_to_wait_offer", "/porder.toWaitOffer"),
        {"porder_sn": porder_sn},
        timeout,
    )
    backend_log["to_wait_offer"] = _payload_brief(to_wait_offer_payload)
    if not _api_success(to_wait_offer_payload):
        time.sleep(float(variables.get("to_wait_offer_retry_delay") or 1))
        retry_detail_payload = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_porder_detail", "/porder.detail"),
            {"porder_sn": porder_sn, "filterByFreightNum": "false"},
            timeout,
        )
        retry_detail_rows = _porder_detail_rows(retry_detail_payload)
        retry_freight_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
            {"porder_sn": porder_sn, "filterByFreightNum": "false"},
            timeout,
        )
        retry_spot_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_spot_porder_detail", "/spot/spot/check/getSpotPorderDetail"),
            {"porder_sn": porder_sn, "filterByFreightNum": "false"},
            timeout,
        )
        retry_to_wait_offer_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_porder_to_wait_offer", "/porder.toWaitOffer"),
            {"porder_sn": porder_sn},
            timeout,
        )
        backend_log["detail_before_to_wait_offer_retry"] = _porder_detail_brief(retry_detail_payload, retry_detail_rows)
        backend_log["freight_list_before_to_wait_offer_retry"] = {
            **_payload_brief(retry_freight_payload),
            "boxes": _freight_box_brief(retry_freight_payload),
            "sample": _payload_structure_sample(retry_freight_payload, limit=4),
        }
        backend_log["spot_before_to_wait_offer_retry"] = _payload_brief(retry_spot_payload)
        backend_log["to_wait_offer_retry"] = _payload_brief(retry_to_wait_offer_payload)
        if _api_success(retry_to_wait_offer_payload):
            to_wait_offer_payload = retry_to_wait_offer_payload
            backend_log["to_wait_offer"] = {**_payload_brief(to_wait_offer_payload), "retried": True}
    if not _api_success(to_wait_offer_payload):
        return False, {"backend_passed": False, "reason": "配送单提交业务失败", "to_wait_offer": _payload_brief(to_wait_offer_payload)}

    porder_to_wait_node = ""
    if _checkpoint_requested(variables, "porder_confirmed"):
        porder_to_wait_node = "porder_confirmed"
    elif _checkpoint_requested(variables, "porder_wait_offer"):
        porder_to_wait_node = "porder_wait_offer"
    if porder_to_wait_node:
        return True, _paused_summary(
            porder_to_wait_node,
            {
                "porder_sn": porder_sn,
                "porder_detail_id": porder_detail_id,
                "porder_detail_ids": porder_detail_ids,
                "freight_id": freight_id,
                "backend_passed": True,
                "backend_steps": [
                    "login",
                    "porder_detail",
                    "submit_translate",
                    "add_box",
                    "into_box_preview",
                    "into_box_submit",
                    "complete_box",
                    "to_wait_offer",
                ],
            },
        )

    logistics_id = str(variables.get("delivery_quote_logistics_id") or variables.get("quote_logistics_id") or "25")
    logistics_price = str(variables.get("logistics_price_artificial") or "775")
    logistics_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_batch_update_freight_logistics", "/porder.batchUpdateFreightLogistics"),
        {"logistics_id": logistics_id, "freight_id_set": [freight_id]},
        timeout,
    )
    backend_log["batch_update_freight_logistics"] = {
        **_payload_brief(logistics_payload),
        "logistics_id": logistics_id,
        "freight_id": freight_id,
    }
    if not _api_success(logistics_payload):
        return False, {
            "backend_passed": False,
            "reason": "配送单选择国际物流失败",
            "batch_update_freight_logistics": _payload_brief(logistics_payload),
        }

    freight_list_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
        {"porder_sn": porder_sn},
        timeout,
    )
    current_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_amount_current", "/porder.porderAmountCurrent"),
        {"porder_sn": porder_sn},
        timeout,
    )
    backend_log["freight_list"] = _payload_brief(freight_list_payload)
    backend_log["amount_current"] = _payload_brief(current_payload)

    offer_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_submit_offer", "/porder.submitOffer"),
        {
            "porder_sn": porder_sn,
            "y_remark": str(variables.get("porder_offer_remark") or "自动化配送单报价"),
            "list": [{"id": item["porder_detail_id"], "y_remark": str(variables.get("porder_y_remark") or "自动化装箱"), "received_num": ""} for item in detail_items],
            "logistics_price_artificial": logistics_price,
            "fba_complete_num": str(variables.get("fba_complete_num") or "0"),
            "fba_overstep_reason": str(variables.get("fba_overstep_reason") or ""),
        },
        timeout,
    )
    backend_log["submit_offer"] = {
        **_payload_brief(offer_payload),
        "porder_detail_id": porder_detail_id,
        "porder_detail_ids": porder_detail_ids,
        "logistics_price_artificial": logistics_price,
    }
    if _api_success(offer_payload) and _checkpoint_requested(variables, "porder_offered"):
        return True, _paused_summary(
            "porder_offered",
            {
                "porder_sn": porder_sn,
                "porder_detail_id": porder_detail_id,
                "porder_detail_ids": porder_detail_ids,
                "freight_id": freight_id,
                "stock_id": stock_item.get("stock_id"),
                "stock_ids": [item.get("stock_id") for item in stock_items],
                "box_num": box_num,
                "box_nums": {item["porder_detail_id"]: item["box_num"] for item in stock_items},
                "logistics_id": logistics_id,
                "logistics_price_artificial": logistics_price,
                "backend_passed": True,
                "backend_steps": [
                    "login",
                    "porder_detail",
                    "submit_translate",
                    "add_box",
                    "into_box_preview",
                    "into_box_submit",
                    "complete_box",
                    "to_wait_offer",
                    "batch_update_freight_logistics",
                    "freight_list",
                    "submit_offer",
                ],
            },
        )
    if not _api_success(offer_payload):
        return False, {"backend_passed": False, "reason": "配送单报价失败", "submit_offer": _payload_brief(offer_payload)}

    return True, {
        "backend_passed": True,
        "backend_steps": [
            "login",
            "porder_detail",
            "submit_translate",
            "add_box",
            "into_box_preview",
            "into_box_submit",
            "complete_box",
            "to_wait_offer",
            "batch_update_freight_logistics",
            "freight_list",
            "submit_offer",
        ],
        "porder_detail_id": porder_detail_id,
        "porder_detail_ids": porder_detail_ids,
        "freight_id": freight_id,
        "stock_id": stock_item.get("stock_id"),
        "stock_ids": [item.get("stock_id") for item in stock_items],
        "box_num": box_num,
        "box_nums": {item["porder_detail_id"]: item["box_num"] for item in stock_items},
        "logistics_id": logistics_id,
        "logistics_price_artificial": logistics_price,
    }


def _run_backend_porder_flow_resume(
    base_url: str,
    timeout: int,
    variables: Dict[str, Any],
    porder_sn: str,
    log: Dict[str, Any],
    detected_start_node: str,
) -> tuple[bool, Dict[str, Any]]:
    backend_log: Dict[str, Any] = {"porder_sn": porder_sn, "detected_start_node": detected_start_node, "steps": []}
    log["backend_porder_resume"] = backend_log
    session = _admin_session_from(variables)

    login_payload, token = _admin_login(session, base_url, variables, timeout)
    session.headers.update(
        {
            "AdminToken": f"Bearer {token}" if token else "",
            "adminToken": f"Bearer {token}" if token else "",
            "Fingerprint": str(variables.get("fingerprint") or "35d3d2dc553624bd3e6cc32688f4e43b"),
            "PageUrlTrace": f"https://jpmanage.rakumart.cn/#/porderDetail?porder_sn={porder_sn}",
            "Origin": "https://jpmanage.rakumart.cn",
            "Referer": "https://jpmanage.rakumart.cn/",
        }
    )
    backend_log["login"] = {
        **_payload_brief(login_payload),
        "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
        "token_extracted": bool(token),
    }
    if not _api_success(login_payload) or not token:
        return False, {"backend_passed": False, "reason": "后台登录失败"}

    detail_payload, detail_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout)
    backend_log["detail_before"] = _porder_detail_brief(detail_payload, detail_rows)
    if not _api_success(detail_payload) or not detail_rows:
        return False, {"backend_passed": False, "reason": "未获取到配送单详情"}

    default_box_num = _as_int(variables.get("backend_box_num"), 1)
    detail_items = _porder_flow_detail_items(detail_rows, default_box_num)
    if not detail_items:
        return False, {"backend_passed": False, "reason": "配送单详情缺少 porder_detail_id"}

    porder_detail_ids = [item["porder_detail_id"] for item in detail_items]
    porder_detail_id = porder_detail_ids[0]
    stock_item: Dict[str, Any] = {"stock_id": "", "box_num": 1}
    freight_id = ""
    logistics_id = str(variables.get("delivery_quote_logistics_id") or variables.get("quote_logistics_id") or "25")
    logistics_price = str(variables.get("logistics_price_artificial") or "775")
    skip_remaining = False

    # ── Step 1: submitTranslate ──
    if detected_start_node in ("warehouse_delivery_created",):
        translate_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_submit_translate", "/porder.submitTranslate"),
            {
                "porder_sn": porder_sn,
                "client_remark_translate": str(variables.get("client_remark_translate") or "自动化配送单翻译"),
                "list": [{"id": item["porder_detail_id"], "y_remark": str(variables.get("porder_y_remark") or "自动化装箱")} for item in detail_items],
                "is_temp": str(variables.get("porder_translate_is_temp") or "0"),
            },
            timeout,
        )
        backend_log["submit_translate"] = {**_payload_brief(translate_payload), "porder_detail_ids": porder_detail_ids}
        if not _api_success(translate_payload):
            return False, {"backend_passed": False, "reason": "配送单提交配货失败", "submit_translate": _payload_brief(translate_payload)}

        _, after_translate_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout, retries=2)
        if after_translate_rows:
            translated_items = _porder_flow_detail_items(after_translate_rows, default_box_num)
            if translated_items:
                detail_items = translated_items
                porder_detail_ids = [item["porder_detail_id"] for item in detail_items]
                porder_detail_id = porder_detail_ids[0]
        backend_log["detail_after_translate"] = {"detail_count": len(after_translate_rows), "porder_detail_ids": porder_detail_ids}
        if _checkpoint_requested(variables, "porder_translated"):
            return True, _paused_summary(
                "porder_translated",
                {
                    "porder_sn": porder_sn,
                    "porder_detail_id": porder_detail_id,
                    "porder_detail_ids": porder_detail_ids,
                    "backend_passed": True,
                    "backend_steps": ["login", "porder_detail", "submit_translate"],
                },
            )
    else:
        backend_log["submit_translate"] = {"skipped": True, "reason": f"起点 {detected_start_node} 已过配货步骤"}

    # ── Step 2: addBox + intoBox ──
    if detected_start_node in ("warehouse_delivery_created", "porder_translated"):
        box_fields = {
            "porder_sn": porder_sn,
            "count": str(variables.get("box_count") or "1"),
            "length": str(variables.get("box_length") or "58"),
            "width": str(variables.get("box_width") or "51"),
            "height": str(variables.get("box_height") or "50"),
            "weight": str(variables.get("box_weight") or "10"),
        }
        add_box_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_add_box", "/porder.addBox"),
            box_fields, timeout,
        )
        backend_log["add_box"] = {**_payload_brief(add_box_payload), "request": box_fields}
        if not _api_success(add_box_payload):
            return False, {"backend_passed": False, "reason": "配送单添加箱子失败", "add_box": _payload_brief(add_box_payload)}

        freight_before_box_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
            {"porder_sn": porder_sn}, timeout,
        )
        detail_after_box_payload, detail_after_box_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout, retries=1)
        backend_log["freight_list_before_box"] = {**_payload_brief(freight_before_box_payload), "sample": _payload_structure_sample(freight_before_box_payload, limit=4)}
        backend_log["detail_after_add_box"] = _porder_detail_brief(detail_after_box_payload, detail_after_box_rows)

        preview_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_into_box_preview", "/porder.intoBoxPreview"),
            {"porderDetailIdS": porder_detail_ids}, timeout,
        )
        stock_items: list[Dict[str, Any]] = []
        for item in detail_items:
            stock_item = _extract_stock_item_for_detail(
                preview_payload, item["porder_detail_id"],
                _as_int(item.get("wait_box_num"), default_box_num),
                allow_global_fallback=len(detail_items) == 1,
            )
            box_num = _box_need_num(stock_item.get("num_need"), _as_int(item.get("wait_box_num"), default_box_num))
            stock_items.append({
                "porder_detail_id": item["porder_detail_id"],
                "stock_id": stock_item.get("stock_id") or "",
                "num_need": stock_item.get("num_need"),
                "box_num": box_num,
            })
        freight_id = _extract_freight_id(
            freight_before_box_payload, detail_after_box_payload, add_box_payload, preview_payload, detail_payload, variables=variables,
        )
        backend_log["into_box_preview"] = {
            **_payload_brief(preview_payload), "porder_detail_id": porder_detail_id,
            "porder_detail_ids": porder_detail_ids, "freight_id": freight_id,
            "stock_items": stock_items, "sample": _payload_structure_sample(preview_payload, limit=8),
        }
        if not _api_success(preview_payload):
            return False, {"backend_passed": False, "reason": "装箱预览失败", "into_box_preview": _payload_brief(preview_payload)}
        if not freight_id:
            return False, {"backend_passed": False, "reason": "未拿到箱子 freight_id，无法装箱"}
        missing_stock_items = [item for item in stock_items if not item.get("stock_id")]
        if missing_stock_items:
            return False, {
                "backend_passed": False,
                "reason": "未按配送单详情匹配到库存 stock_id，无法装箱",
                "missing_porder_detail_ids": [item["porder_detail_id"] for item in missing_stock_items],
            }
        stock_item = stock_items[0]
        box_num = _as_int(stock_item.get("box_num"), 1)
        into_box_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_into_box_submit", "/porder.intoBoxSubmit"),
            {
                "freight_id_set": [freight_id],
                "list": [{
                    "per_num": item["box_num"],
                    "porder_detail_id": item["porder_detail_id"],
                    "stock": [{"stock_id": item["stock_id"], "num_need": item["box_num"]}],
                } for item in stock_items],
            }, timeout,
        )
        backend_log["into_box_submit"] = {**_payload_brief(into_box_payload), "box_num": box_num, "box_nums": {item["porder_detail_id"]: item["box_num"] for item in stock_items}}
        if not _api_success(into_box_payload):
            return False, {"backend_passed": False, "reason": "装箱提交失败", "into_box_submit": _payload_brief(into_box_payload)}

        time.sleep(float(variables.get("after_box_submit_delay") or 0.8))
        detail_after_into_box_payload = _post_admin_form(
            session, base_url,
            _api_path(variables, "admin_porder_detail", "/porder.detail"),
            {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
        )
        detail_after_into_box_rows = _porder_detail_rows(detail_after_into_box_payload)
        freight_after_into_box_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
            {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
        )
        backend_log["detail_after_into_box"] = _porder_detail_brief(detail_after_into_box_payload, detail_after_into_box_rows)
        backend_log["freight_list_after_into_box"] = {
            **_payload_brief(freight_after_into_box_payload),
            "boxes": _freight_box_brief(freight_after_into_box_payload),
            "sample": _payload_structure_sample(freight_after_into_box_payload, limit=4),
        }
        spot_after_into_box_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_spot_porder_detail", "/spot/spot/check/getSpotPorderDetail"),
            {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
        )
        backend_log["spot_after_into_box"] = _payload_brief(spot_after_into_box_payload)

        complete_box_attempts: list[Dict[str, Any]] = []
        if _has_incomplete_freight_box(freight_after_into_box_payload):
            complete_box_fields = {**box_fields, "freight_id_set": [freight_id]}
            for complete_box_path in _porder_complete_box_paths(variables):
                try:
                    complete_payload = _post_admin_urlencoded(session, base_url, complete_box_path, complete_box_fields, timeout)
                    complete_brief = _payload_brief(complete_payload)
                except Exception as exc:
                    complete_payload = {"success": False, "message": str(exc)}
                    complete_brief = {"success": False, "message": str(exc)}
                time.sleep(float(variables.get("after_complete_box_delay") or 0.8))
                complete_check_payload = _post_admin_urlencoded(
                    session, base_url,
                    _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
                    {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
                )
                attempt = {
                    "path": complete_box_path, "request": complete_box_fields,
                    "response": complete_brief,
                    "boxes": _freight_box_brief(complete_check_payload),
                    "box_completed": not _has_incomplete_freight_box(complete_check_payload),
                }
                complete_box_attempts.append(attempt)
                if _api_success(complete_payload) and attempt["box_completed"]:
                    break
        else:
            complete_box_attempts.append({"skipped": True, "reason": "freight box already completed"})
        backend_log["complete_box_attempts"] = complete_box_attempts

        if _checkpoint_requested(variables, "warehouse_delivery_created"):
            return True, _paused_summary(
                "warehouse_delivery_created",
                {
                    "porder_sn": porder_sn,
                    "porder_detail_id": porder_detail_id,
                    "porder_detail_ids": porder_detail_ids,
                    "backend_passed": True,
                    "backend_steps": ["login", "porder_detail", "submit_translate", "add_box", "into_box", "complete_box"],
                },
            )
    else:
        backend_log["add_box"] = {"skipped": True, "reason": f"起点 {detected_start_node} 已过装箱步骤"}
        backend_log["into_box_submit"] = {"skipped": True}
        backend_log["complete_box_attempts"] = [{"skipped": True, "reason": f"起点 {detected_start_node} 已过装箱步骤"}]
        # 从货运列表中获取 freight_id
        freight_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
            {"porder_sn": porder_sn}, timeout,
        )
        freight_id = _extract_freight_id(freight_payload, variables=variables)
        stock_item = {"stock_id": ""}

    # ── Step 3: toWaitOffer ──
    if detected_start_node in ("warehouse_delivery_created", "porder_translated", "porder_confirmed"):
        to_wait_offer_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_to_wait_offer", "/porder.toWaitOffer"),
            {"porder_sn": porder_sn}, timeout,
        )
        backend_log["to_wait_offer"] = _payload_brief(to_wait_offer_payload)
        if not _api_success(to_wait_offer_payload):
            time.sleep(float(variables.get("to_wait_offer_retry_delay") or 1))
            retry_detail_payload = _post_admin_form(
                session, base_url,
                _api_path(variables, "admin_porder_detail", "/porder.detail"),
                {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
            )
            retry_detail_rows = _porder_detail_rows(retry_detail_payload)
            retry_freight_payload = _post_admin_urlencoded(
                session, base_url,
                _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
                {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
            )
            retry_spot_payload = _post_admin_urlencoded(
                session, base_url,
                _api_path(variables, "admin_spot_porder_detail", "/spot/spot/check/getSpotPorderDetail"),
                {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
            )
            retry_to_wait_offer_payload = _post_admin_urlencoded(
                session, base_url,
                _api_path(variables, "admin_porder_to_wait_offer", "/porder.toWaitOffer"),
                {"porder_sn": porder_sn}, timeout,
            )
            backend_log["detail_before_to_wait_offer_retry"] = _porder_detail_brief(retry_detail_payload, retry_detail_rows)
            backend_log["freight_list_before_to_wait_offer_retry"] = {
                **_payload_brief(retry_freight_payload),
                "boxes": _freight_box_brief(retry_freight_payload),
                "sample": _payload_structure_sample(retry_freight_payload, limit=4),
            }
            backend_log["spot_before_to_wait_offer_retry"] = _payload_brief(retry_spot_payload)
            backend_log["to_wait_offer_retry"] = _payload_brief(retry_to_wait_offer_payload)
            if _api_success(retry_to_wait_offer_payload):
                to_wait_offer_payload = retry_to_wait_offer_payload
                backend_log["to_wait_offer"] = {**_payload_brief(to_wait_offer_payload), "retried": True}
        if not _api_success(to_wait_offer_payload):
            return False, {"backend_passed": False, "reason": "配送单提交业务失败", "to_wait_offer": _payload_brief(to_wait_offer_payload)}

        porder_to_wait_node = ""
        if _checkpoint_requested(variables, "porder_confirmed"):
            porder_to_wait_node = "porder_confirmed"
        elif _checkpoint_requested(variables, "porder_wait_offer"):
            porder_to_wait_node = "porder_wait_offer"
        if porder_to_wait_node:
            return True, _paused_summary(
                porder_to_wait_node,
                {
                    "porder_sn": porder_sn,
                    "porder_detail_id": porder_detail_id,
                    "porder_detail_ids": porder_detail_ids,
                    "freight_id": freight_id,
                    "backend_passed": True,
                    "backend_steps": ["login", "porder_detail", "submit_translate", "add_box", "into_box_submit", "complete_box", "to_wait_offer"],
                },
            )
    else:
        backend_log["to_wait_offer"] = {"skipped": True, "reason": f"起点 {detected_start_node} 已过提交业务步骤"}

    # ── Step 4: logistics selection + submitOffer ──
    if detected_start_node in ("warehouse_delivery_created", "porder_translated", "porder_confirmed", "porder_wait_offer"):
        logistics_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_batch_update_freight_logistics", "/porder.batchUpdateFreightLogistics"),
            {"logistics_id": logistics_id, "freight_id_set": [freight_id]}, timeout,
        )
        backend_log["batch_update_freight_logistics"] = {
            **_payload_brief(logistics_payload), "logistics_id": logistics_id, "freight_id": freight_id,
        }
        if not _api_success(logistics_payload):
            return False, {
                "backend_passed": False, "reason": "配送单选择国际物流失败",
                "batch_update_freight_logistics": _payload_brief(logistics_payload),
            }

        freight_list_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
            {"porder_sn": porder_sn}, timeout,
        )
        current_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_amount_current", "/porder.porderAmountCurrent"),
            {"porder_sn": porder_sn}, timeout,
        )
        backend_log["freight_list"] = _payload_brief(freight_list_payload)
        backend_log["amount_current"] = _payload_brief(current_payload)

        offer_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_submit_offer", "/porder.submitOffer"),
            {
                "porder_sn": porder_sn,
                "y_remark": str(variables.get("porder_offer_remark") or "自动化配送单报价"),
                "list": [{"id": item["porder_detail_id"], "y_remark": str(variables.get("porder_y_remark") or "自动化装箱"), "received_num": ""} for item in detail_items],
                "logistics_price_artificial": logistics_price,
                "fba_complete_num": str(variables.get("fba_complete_num") or "0"),
                "fba_overstep_reason": str(variables.get("fba_overstep_reason") or ""),
            }, timeout,
        )
        backend_log["submit_offer"] = {
            **_payload_brief(offer_payload), "porder_detail_id": porder_detail_id,
            "porder_detail_ids": porder_detail_ids, "logistics_price_artificial": logistics_price,
        }
        if _api_success(offer_payload) and _checkpoint_requested(variables, "porder_offered"):
            return True, _paused_summary(
                "porder_offered",
                {
                    "porder_sn": porder_sn, "porder_detail_id": porder_detail_id,
                    "porder_detail_ids": porder_detail_ids, "freight_id": freight_id,
                    "stock_id": stock_item.get("stock_id") if isinstance(stock_item, dict) else "",
                    "box_num": stock_item.get("box_num") if isinstance(stock_item, dict) else 1,
                    "logistics_id": logistics_id, "logistics_price_artificial": logistics_price,
                    "backend_passed": True,
                    "backend_steps": ["login", "porder_detail", "submit_translate", "add_box", "into_box_submit", "complete_box", "to_wait_offer", "batch_update_freight_logistics", "submit_offer"],
                },
            )
        if not _api_success(offer_payload):
            return False, {"backend_passed": False, "reason": "配送单报价失败", "submit_offer": _payload_brief(offer_payload)}
    else:
        backend_log["submit_offer"] = {"skipped": True, "reason": f"起点 {detected_start_node} 已过报价步骤"}

    return True, {
        "backend_passed": True,
        "backend_steps": ["login", "porder_detail", "submit_translate", "add_box", "into_box_submit", "complete_box", "to_wait_offer", "batch_update_freight_logistics", "submit_offer"],
        "porder_detail_id": porder_detail_id,
        "porder_detail_ids": porder_detail_ids,
        "freight_id": freight_id,
        "stock_id": stock_item.get("stock_id") if isinstance(stock_item, dict) else "",
        "logistics_id": logistics_id,
        "logistics_price_artificial": logistics_price,
    }


def _porder_detail_status_texts(rows: list[Dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    keys = [
        "status",
        "statusName",
        "status_name",
        "statusText",
        "status_text",
        "porder_status",
        "porderStatus",
        "porder_status_name",
        "porderStatusName",
    ]
    for row in rows:
        for key in keys:
            value = row.get(key)
            if value not in (None, "", [], {}):
                texts.append(str(value).strip())
    return _unique_list([text for text in texts if text])


def _porder_node_from_status_texts(texts: list[str]) -> str:
    status_text = " ".join(texts).lower()
    if not status_text:
        return ""
    node_keywords = [
        ("porder_offered", ["已报价", "报价完成", "待付款", "等待付款", "wait_pay", "wait pay", "offered", "quoted"]),
        ("porder_wait_offer", ["待报价", "等待报价", "wait_offer", "wait offer"]),
        ("porder_confirmed", ["已装箱", "装箱完成", "待提交业务", "提交业务", "confirmed"]),
        ("porder_translated", ["已配货", "配货完成", "待装箱", "已翻译", "翻译完成", "translated"]),
    ]
    for node, keywords in node_keywords:
        if any(keyword in status_text for keyword in keywords):
            return node
    return ""


def _detect_resume_porder_state(
    env: Env,
    variables: Dict[str, Any],
    porder_sn: str,
    log: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    base_url = (variables.get("backend_base_url") or env.base_url or bulk_cart.BASE_URL).rstrip("/")
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    detect_log: Dict[str, Any] = {"porder_sn": porder_sn, "base_url": base_url}
    log["resume_porder_detect"] = detect_log

    session = _admin_session_from(variables)
    login_payload, token = _admin_login(session, base_url, variables, timeout)
    detect_log["login"] = {
        **_payload_brief(login_payload),
        "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
        "token_extracted": bool(token),
    }
    if not _api_success(login_payload) or not token:
        return False, {"porder_sn": porder_sn, "detected_start_node": "", "reason": "后台登录失败"}

    # 查询配送单详情
    detail_payload, detail_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout)
    detect_log["detail"] = _porder_detail_brief(detail_payload, detail_rows)
    if not _api_success(detail_payload) or not detail_rows:
        return False, {"porder_sn": porder_sn, "detected_start_node": "", "reason": "未查到配送单详情"}

    # 查询箱子列表
    freight_payload = _post_admin_urlencoded(
        session, base_url,
        _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
        {"porder_sn": porder_sn, "filterByFreightNum": "false"},
        timeout,
    )
    freight_data = freight_payload.get("data") if isinstance(freight_payload.get("data"), dict) else {}
    freight_rows = _nested_rows(freight_data) if freight_data else []
    has_boxes = len(freight_rows) > 0
    boxes_completed = has_boxes and not _has_incomplete_freight_box(freight_payload)
    detect_log["freight_list"] = {
        **_payload_brief(freight_payload),
        "row_count": len(freight_rows),
        "has_boxes": has_boxes,
        "boxes_completed": boxes_completed,
    }

    # 判断当前节点
    detail_statuses = set()
    detail_has_freight_id = False
    for row in detail_rows:
        status = str(row.get("status", "") or "").strip()
        if status:
            detail_statuses.add(status)
        if row.get("freight_id"):
            detail_has_freight_id = True
    detail_status_texts = _porder_detail_status_texts(detail_rows)
    status_detected_node = _porder_node_from_status_texts(detail_status_texts)

    detected_start_node = ""
    order_status = detail_statuses

    # 从配送单状态反推当前节点
    # 若无箱子 → warehouse_delivery_created 或 porder_translated
    # 有箱子但未完成装箱 → porder_confirmed
    # 箱子已完成 → porder_wait_offer 或 porder_offered
    if status_detected_node == "porder_offered":
        detected_start_node = "porder_offered"
    elif not has_boxes:
        # 检查是否已提交翻译：detail 行的 status 如果有 translate 相关标记
        if status_detected_node in {"porder_translated", "porder_confirmed", "porder_wait_offer"}:
            detected_start_node = status_detected_node
        elif not detail_has_freight_id:
            detected_start_node = "warehouse_delivery_created"
        else:
            detected_start_node = "porder_translated"
    elif not boxes_completed:
        detected_start_node = "porder_confirmed"
    else:
        # 箱子已完成，检查是否已报价
        amount_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_amount_current", "/porder.porderAmountCurrent"),
            {"porder_sn": porder_sn},
            timeout,
        )
        detect_log["amount_current"] = _payload_brief(amount_payload)
        amount_data = amount_payload.get("data") if isinstance(amount_payload.get("data"), dict) else {}
        offered = bool(amount_data and (
            _positive_decimal(str(amount_data.get("pay_amount") or amount_data.get("amount") or "0"))
        ))
        if offered or status_detected_node == "porder_offered":
            detected_start_node = "porder_offered"
        elif status_detected_node in {"porder_confirmed", "porder_wait_offer"}:
            detected_start_node = status_detected_node
        else:
            detected_start_node = "porder_wait_offer"

    summary: Dict[str, Any] = {
        "porder_sn": porder_sn,
        "detail_statuses": list(detail_statuses),
        "detail_status_texts": detail_status_texts,
        "status_detected_node": status_detected_node,
        "has_boxes": has_boxes,
        "boxes_completed": boxes_completed,
        "detected_start_node": detected_start_node,
        "detail": _admin_detail_brief({"order_detail": detail_rows}),
    }
    if not detected_start_node:
        summary["reason"] = f"配送单状态无法识别"
        return False, summary
    return True, summary


def run_warehouse_delivery_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    account, password, client_tool = _client_login_inputs(variables)
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
    send_num = _as_int(variables.get("send_num") or variables.get("porder_send_num"), 1)
    warehouse_sku_count = max(1, _as_int(variables.get("warehouse_sku_count") or variables.get("porder_sku_count") or variables.get("sku_count"), 1))
    require_full_count = _as_bool(variables.get("require_warehouse_sku_count"), False)
    warehouse_fill_retries = max(1, _as_int(variables.get("warehouse_fill_retries"), 1))
    warehouse_fill_retry_delay = _as_float(variables.get("warehouse_fill_retry_delay"), 1.0)
    porder_sn = _porder_sn(variables)
    log: Dict[str, Any] = {
        "script": WAREHOUSE_DELIVERY_SCRIPT_NAME,
        "mode": "warehouse_to_delivery_offer",
        "base_url": base_url,
        "send_num": send_num,
        "warehouse_sku_count": warehouse_sku_count,
        "requested_warehouse_sku_count": warehouse_sku_count,
        "warehouse_fill_scope": str(variables.get("warehouse_fill_scope") or ""),
        "require_warehouse_sku_count": require_full_count,
        "started_at": datetime.now(),
        "warehouse_attempts": [],
    }

    try:
        runtime = _runtime_from_variables(variables)
        if runtime:
            client, _base_url, _timeout, token, _cached = runtime.client(env, variables, log=log)
        else:
            client = bulk_cart.RakumartClient(base_url, timeout)
            _configure_client_api_paths(client, variables)
            token = _call_with_retry("client login", lambda: client.login(account, password, client_tool))
            log["login"] = {"success": True, "account": account, "client_tool": client_tool, "token_extracted": bool(token)}

        tail_pay_passed, tail_pay_summary = _run_order_tail_payment_if_needed(env, variables, log, "before_porder_create")
        if not tail_pay_passed:
            return _finish_named(
                WAREHOUSE_DELIVERY_SCRIPT_NAME,
                log,
                False,
                {
                    "porder_sn": "",
                    "order_detail_id": "",
                    "order_detail_ids": [],
                    "reason": str(tail_pay_summary.get("reason") or "提出配送单前尾款支付失败"),
                    "order_tail_payment": tail_pay_summary,
                },
            )
        tail_order_detail_ids = _unique_list(
            (tail_pay_summary.get("order_detail_ids") if isinstance(tail_pay_summary.get("order_detail_ids"), list) else [])
            or (tail_pay_summary.get("downstream_order_detail_ids") if isinstance(tail_pay_summary.get("downstream_order_detail_ids"), list) else [])
        )
        if tail_order_detail_ids:
            warehouse_sku_count = len(tail_order_detail_ids)
            require_full_count = True
            log["warehouse_sku_count"] = warehouse_sku_count
            log["requested_warehouse_sku_count"] = warehouse_sku_count
            log["require_warehouse_sku_count"] = require_full_count

        selected_items: list[Dict[str, Any]] = []
        warehouse_rows: list[Dict[str, Any]] = []
        requested_id = str(variables.get("order_detail_id") or variables.get("porder_detail_id") or "").strip()
        requested_ids = _warehouse_requested_order_detail_ids(variables)
        if requested_ids and len(requested_ids) > warehouse_sku_count:
            warehouse_sku_count = len(requested_ids)
            require_full_count = True
            log["warehouse_sku_count"] = warehouse_sku_count
            log["requested_warehouse_sku_count"] = warehouse_sku_count
            log["require_warehouse_sku_count"] = require_full_count
        if requested_id and warehouse_sku_count <= 1 and not require_full_count:
            # 快速路径：仍查询仓库列表拿真实可出荷数，避免 send_num 超过后端限制
            list_fields = _warehouse_list_fields(variables)
            fast_matched: Dict[str, Any] = {}
            fast_path_used = ""
            for path in _warehouse_candidate_paths(variables):
                try:
                    payload = _call_with_retry("warehouse list", lambda path=path: client.post_form(path, list_fields), attempts=1)
                except Exception as exc:
                    log["warehouse_attempts"].append({"attempt": 1, "path": path, "request": dict(list_fields), "error": str(exc), "fast_path": True})
                    continue
                rows = _nested_rows(payload)
                log["warehouse_attempts"].append(
                    {
                        "attempt": 1,
                        "path": path,
                        "request": dict(list_fields),
                        **_payload_brief(payload),
                        "row_count": len(rows),
                        "fast_path": True,
                    }
                )
                for row in rows:
                    if _warehouse_item_id(row) == requested_id and _warehouse_sendable_num(row) > 0:
                        fast_matched = dict(row)
                        fast_matched.setdefault("_warehouse_source", "current_order")
                        fast_path_used = path
                        warehouse_rows = rows
                        break
                if fast_matched:
                    break
            if fast_matched:
                selected_items = [fast_matched]
                log["warehouse_fast_path"] = {"matched": True, "path": fast_path_used, "sendable_num": _warehouse_sendable_num(fast_matched)}
            else:
                selected_items = [{"order_detail_id": requested_id, "send_num": send_num}]
                log["warehouse_fast_path"] = {"matched": False, "fallback": "warehouse_list_no_match", "warning": "未取到真实可出荷数，沿用配置 send_num 提交"}
        else:
            list_fields = _warehouse_list_fields(variables)
            best_selected: list[Dict[str, Any]] = []
            for attempt in range(warehouse_fill_retries):
                found_usable = False
                for path in _warehouse_candidate_paths(variables):
                    try:
                        payload = _call_with_retry("warehouse list", lambda path=path: client.post_form(path, list_fields), attempts=1)
                    except Exception as exc:
                        log["warehouse_attempts"].append({"attempt": attempt + 1, "path": path, "request": dict(list_fields), "error": str(exc)})
                        continue
                    rows = _nested_rows(payload)
                    selected = _select_warehouse_items(rows, variables, warehouse_sku_count)
                    current_order_count = sum(1 for item in selected if item.get("_warehouse_source") == "current_order")
                    history_fill_count = sum(1 for item in selected if item.get("_warehouse_source") == "history")
                    log["warehouse_attempts"].append(
                        {
                            "attempt": attempt + 1,
                            "path": path,
                            "request": dict(list_fields),
                            **_payload_brief(payload),
                            "row_count": len(rows),
                            "selected_order_detail_ids": [_warehouse_item_id(item) for item in selected],
                            "selected_sku_ids": [_warehouse_sku_id(item) for item in selected],
                            "current_order_count": current_order_count,
                            "history_fill_count": history_fill_count,
                        }
                    )
                    if not _api_success(payload) or not selected:
                        continue
                    if len(selected) > len(best_selected):
                        best_selected = selected
                        warehouse_rows = rows
                    if len(selected) >= warehouse_sku_count or not require_full_count:
                        selected_items = selected
                        warehouse_rows = rows
                        found_usable = True
                        break
                if found_usable:
                    break
                if attempt < warehouse_fill_retries - 1 and warehouse_fill_retry_delay > 0:
                    time.sleep(warehouse_fill_retry_delay)
            if not selected_items and best_selected:
                selected_items = best_selected

        if not selected_items and requested_ids:
            direct_count = warehouse_sku_count if require_full_count else max(1, min(warehouse_sku_count, len(requested_ids)))
            if not require_full_count or len(requested_ids) >= direct_count:
                used_ids = requested_ids[:direct_count]
                selected_items = [
                    {
                        "order_detail_id": item_id,
                        "send_num": send_num,
                        "_warehouse_source": "current_order",
                        "_direct_requested_id": True,
                    }
                    for item_id in used_ids
                ]
                log["warehouse_direct_requested_ids"] = {
                    "used_order_detail_ids": used_ids,
                    "requested_order_detail_ids": requested_ids,
                    "reason": "warehouse list empty or delayed",
                }

        if not selected_items and requested_id and not require_full_count:
            selected_items = [{"order_detail_id": requested_id, "send_num": send_num}]

        order_detail_id = _warehouse_item_id(selected_items[0] if selected_items else {})
        if not order_detail_id:
            return _finish_named(
                WAREHOUSE_DELIVERY_SCRIPT_NAME,
                log,
                False,
                {
                    "porder_sn": "",
                    "order_detail_id": "",
                    "reason": "\u672a\u627e\u5230\u53ef\u63d0\u51fa\u914d\u9001\u5355\u7684\u4ed3\u5e93\u5546\u54c1\uff0c\u8bf7\u5728\u53d8\u91cf\u4e2d\u914d\u7f6e client_warehouse_list \u6216 order_detail_id",
                },
            )

        delivery_items: list[Dict[str, Any]] = []
        for item in selected_items:
            item_order_detail_id = _warehouse_item_id(item)
            if not item_order_detail_id:
                continue
            max_send_num = _warehouse_sendable_num(item)
            actual_send_num = min(send_num, max_send_num) if max_send_num > 0 else send_num
            delivery_items.append(
                {
                    "order_detail_id": item_order_detail_id,
                    "send_num": actual_send_num,
                    "sendable_num": max_send_num,
                    "sku_id": _warehouse_sku_id(item),
                    "source": item.get("_warehouse_source") or "history",
                    "client_remark": str(variables.get("porder_detail_remark") or "自动化配送单明细备注"),
                    "row": item,
                }
            )
        order_detail_ids = [item["order_detail_id"] for item in delivery_items]
        selected_sku_ids = [item["sku_id"] for item in delivery_items if item.get("sku_id")]
        actual_warehouse_sku_count = len(delivery_items)
        current_order_count = sum(1 for item in delivery_items if item.get("source") == "current_order")
        history_fill_count = sum(1 for item in delivery_items if item.get("source") == "history")
        total_send_num = sum(_as_int(item.get("send_num"), 0) for item in delivery_items)
        if not delivery_items:
            return _finish_named(
                WAREHOUSE_DELIVERY_SCRIPT_NAME,
                log,
                False,
                {
                    "porder_sn": "",
                    "order_detail_id": "",
                    "order_detail_ids": [],
                    "requested_warehouse_sku_count": warehouse_sku_count,
                    "warehouse_sku_count": warehouse_sku_count,
                    "actual_warehouse_sku_count": 0,
                    "current_order_count": 0,
                    "history_fill_count": 0,
                    "reason": "可用库存不足" if require_full_count else "\u672a\u627e\u5230\u53ef\u63d0\u51fa\u914d\u9001\u5355\u7684\u4ed3\u5e93\u5546\u54c1",
                },
            )
        selected_warehouse_items = [_warehouse_item_brief(item.get("row") or {}, _as_int(item.get("send_num"), send_num)) for item in delivery_items]
        if require_full_count and actual_warehouse_sku_count < warehouse_sku_count:
            return _finish_named(
                WAREHOUSE_DELIVERY_SCRIPT_NAME,
                log,
                False,
                {
                    "porder_sn": "",
                    "order_detail_id": order_detail_ids[0] if order_detail_ids else "",
                    "order_detail_ids": order_detail_ids,
                    "send_num": _as_int(delivery_items[0].get("send_num"), send_num),
                    "total_send_num": total_send_num,
                    "requested_warehouse_sku_count": warehouse_sku_count,
                    "warehouse_sku_count": warehouse_sku_count,
                    "actual_warehouse_sku_count": actual_warehouse_sku_count,
                    "current_order_count": current_order_count,
                    "history_fill_count": history_fill_count,
                    "selected_sku_ids": selected_sku_ids,
                    "selected_warehouse_items": selected_warehouse_items,
                    "warehouse_rows": len(warehouse_rows),
                    "reason": "可用库存不足",
                },
            )
        order_detail_id = order_detail_ids[0]
        actual_send_num = _as_int(delivery_items[0].get("send_num"), send_num)
        fields = _porder_create_fields_for_items(delivery_items, porder_sn, variables)
        payload = _call_with_retry(
            "porder create",
            lambda: client.post_form(_api_path(variables, "client_porder_create", "/client/porder.porderCreate"), fields),
        )
        porder_sn = _extract_porder_sn(payload, porder_sn)
        log["selected_item"] = delivery_items[0]
        log["selected_items"] = [
            {key: value for key, value in item.items() if key != "row"}
            for item in delivery_items
        ]
        log["porder_create"] = {
            **_payload_brief(payload),
            "request": {
                "create_type": fields.get("create_type"),
                "porder_sn": fields.get("porder_sn"),
                "logistics_id": fields.get("logistics_id"),
                "order_detail_id": order_detail_id,
                "order_detail_ids": order_detail_ids,
                "send_num": actual_send_num,
                "total_send_num": total_send_num,
                "details": [
                    {key: value for key, value in item.items() if key != "row"}
                    for item in delivery_items
                ],
            },
            "response": payload,
        }
        passed = _api_success(payload)
        summary = {
            "porder_sn": porder_sn,
            "order_detail_id": order_detail_id,
            "order_detail_ids": order_detail_ids,
            "send_num": actual_send_num,
            "total_send_num": total_send_num,
            "requested_warehouse_sku_count": warehouse_sku_count,
            "warehouse_sku_count": warehouse_sku_count,
            "actual_warehouse_sku_count": actual_warehouse_sku_count,
            "current_order_count": current_order_count,
            "history_fill_count": history_fill_count,
            "selected_sku_ids": selected_sku_ids,
            "selected_warehouse_items": selected_warehouse_items,
            "warehouse_rows": len(warehouse_rows),
            "order_tail_payment": tail_pay_summary,
            "create_passed": passed,
        }
        if actual_warehouse_sku_count < warehouse_sku_count:
            summary["warning"] = f"\u8bf7\u6c42 {warehouse_sku_count} \u756a\uff0c\u5b9e\u9645\u627e\u5230 {actual_warehouse_sku_count} \u756a\u53ef\u63d0\u51fa SKU"
        if not passed:
            summary["reason"] = payload.get("msg") or payload.get("message") or "\u914d\u9001\u5355\u63d0\u51fa\u5931\u8d25"
            return _finish_named(WAREHOUSE_DELIVERY_SCRIPT_NAME, log, False, summary)
        if _checkpoint_requested(variables, "warehouse_delivery_created"):
            return _finish_paused(WAREHOUSE_DELIVERY_SCRIPT_NAME, log, "warehouse_delivery_created", summary)
        if _as_bool(variables.get("run_backend_delivery_flow"), True):
            backend_passed, backend_summary = _run_backend_porder_flow(base_url, timeout, variables, porder_sn, log)
            summary.update(backend_summary)
            passed = backend_passed
            if not backend_passed and "reason" not in summary:
                summary["reason"] = backend_summary.get("reason") or "\u914d\u9001\u5355\u540e\u53f0\u6d41\u8f6c\u5931\u8d25"
        return _finish_named(WAREHOUSE_DELIVERY_SCRIPT_NAME, log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            WAREHOUSE_DELIVERY_SCRIPT_NAME,
            log,
            False,
            {"porder_sn": "", "order_detail_id": "", "send_num": send_num, "warehouse_sku_count": warehouse_sku_count, "error": str(exc)},
        )


def run_balance_payment_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    log: Dict[str, Any] = {
        "script": BALANCE_PAYMENT_SCRIPT_NAME,
        "mode": "balance_payment",
        "started_at": datetime.now(),
        "order_list": {},
        "payment": {},
    }

    try:
        client, base_url, _, _ = _login_client_for_payment(env, variables, log)
        log["base_url"] = base_url
        order, order_sn, amount = _load_payment_order(client, variables, log)
        if not order or not order_sn:
            return _finish_named(
                BALANCE_PAYMENT_SCRIPT_NAME,
                log,
                False,
                {"payment_type": "balance", "order_sn": "", "pay_amount": "0", "reason": "\u672a\u67e5\u8be2\u5230\u7b49\u5f85\u4ed8\u6b3e\u8ba2\u5355"},
            )

        fields: OrderedDict[str, Any] = OrderedDict()
        fields["order_sn"] = order_sn
        fields["discounts_id"] = str(variables.get("discounts_id") or "")
        fields["predict_logistics_price_is_pay"] = str(variables.get("predict_logistics_price_is_pay") or "0")
        if _as_bool(variables.get("include_balance_pay_amount"), False):
            fields["pay_amount"] = amount
        _apply_extra_fields(fields, variables.get("balance_pay_fields"))
        payment_payload = _call_with_retry(
            "balance payment",
            lambda: client.post_form(_api_path(variables, "client_balance_pay", "/client/order.balancePayOrder"), fields),
        )
        log["payment"] = {**_payload_brief(payment_payload), "request": dict(fields)}
        summary = _common_payment_summary("balance", order_sn, amount, payment_payload)
        return _finish_named(BALANCE_PAYMENT_SCRIPT_NAME, log, summary["payment_passed"], summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            BALANCE_PAYMENT_SCRIPT_NAME,
            log,
            False,
            {"payment_type": "balance", "order_sn": "", "pay_amount": "0", "error": str(exc)},
        )


def run_bank_payment_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    existing_serial_number = str(variables.get("serial_number") or "").strip()
    existing_order_sn = str(variables.get("order_sn") or "").strip()
    log: Dict[str, Any] = {
        "script": BANK_PAYMENT_SCRIPT_NAME,
        "mode": "finance_only" if existing_serial_number else "bank_payment",
        "started_at": datetime.now(),
        "order_list": {},
        "payment": {},
        "finance": {},
    }

    try:
        client = None
        base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
        timeout = _as_int(variables.get("timeout"), env.timeout or 25)
        if not existing_serial_number:
            client, base_url, timeout, _ = _login_client_for_payment(env, variables, log)
        log["base_url"] = base_url
        order_sn = existing_order_sn
        amount = str(variables.get("pay_amount") or "0")
        payment_payload: Dict[str, Any] = {"success": True, "code": 0, "data": {"order_sn": order_sn, "serial_number": existing_serial_number}}
        payment_data: Dict[str, Any] = {"order_sn": order_sn, "serial_number": existing_serial_number}
        payment_ok = True
        serial_number = existing_serial_number
        if existing_serial_number:
            log["payment"] = {
                "skipped": True,
                "reason": "\u5df2\u4f20\u5165\u6d41\u6c34\u53f7\uff0c\u53ea\u6267\u884c\u8d22\u52a1\u786e\u8ba4\u5165\u91d1",
                "order_sn": order_sn,
                "serial_number": serial_number,
            }
        else:
            order, order_sn, amount = _load_payment_order(client, variables, log)
            if not order or not order_sn:
                return _finish_named(
                    BANK_PAYMENT_SCRIPT_NAME,
                    log,
                    False,
                    {"payment_type": "bank", "order_sn": "", "pay_amount": "0", "reason": "\u672a\u67e5\u8be2\u5230\u7b49\u5f85\u4ed8\u6b3e\u8ba2\u5355"},
                )
            if not _positive_decimal(amount):
                return _finish_named(
                    BANK_PAYMENT_SCRIPT_NAME,
                    log,
                    False,
                    {"payment_type": "bank", "order_sn": order_sn, "pay_amount": amount, "reason": "\u672a\u83b7\u53d6\u5230\u53ef\u7528\u7684\u8ba2\u5355\u652f\u4ed8\u91d1\u989d"},
                )

            now = datetime.now()
            fields: OrderedDict[str, Any] = OrderedDict()
            fields["order_sn"] = order_sn
            fields["pay_bank_method"] = str(variables.get("pay_bank_method") or "1")
            fields["pay_date"] = str(variables.get("pay_date") or now.strftime("%Y-%m-%d %H:%M:%S"))
            fields["pay_reach_date"] = _bank_pay_reach_date(variables, now)
            fields["pay_name"] = str(variables.get("pay_name") or "\u81ea\u52a8\u5316\u6d4b\u8bd5")
            fields["pay_amount"] = amount
            fields["pay_remark"] = str(variables.get("pay_remark") or "\u81ea\u52a8\u5316\u94f6\u884c\u4ed8\u6b3e")
            fields["discounts_id"] = str(variables.get("discounts_id") or "")
            fields["predict_logistics_price_is_pay"] = str(variables.get("predict_logistics_price_is_pay") or "0")
            _apply_extra_fields(fields, variables.get("bank_pay_fields"))
            payment_payload = _call_with_retry(
                "bank payment",
                lambda: client.post_form(_api_path(variables, "client_bank_pay", "/client/order.bankPayOrder"), fields),
            )
            payment_ok = _api_success(payment_payload)
            payment_data = payment_payload.get("data") if isinstance(payment_payload.get("data"), dict) else {}
            serial_number = str(payment_data.get("serial_number") or variables.get("serial_number") or "")
            log["payment"] = {**_payload_brief(payment_payload), "request": dict(fields), "serial_number": serial_number}

        finance_confirm = _as_bool(variables.get("finance_confirm"), True)
        finance_ok = True
        if payment_ok and finance_confirm:
            if not serial_number:
                finance_ok = False
                log["finance"] = {"reason": "\u94f6\u884c\u652f\u4ed8\u672a\u8fd4\u56de\u6d41\u6c34\u53f7"}
            else:
                session = _admin_session_from(variables)
                login_payload, token = _admin_login(session, base_url, variables, timeout)
                log["finance"]["login"] = {
                    **_payload_brief(login_payload),
                    "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
                    "token_extracted": bool(token),
                }
                if not _api_success(login_payload) or not token:
                    finance_ok = False
                    log["finance"]["reason"] = "\u540e\u53f0\u767b\u5f55\u5931\u8d25"
                else:
                    initial_delay = _as_float(variables.get("finance_confirm_initial_delay"), 2.0)
                    retry_delay = _as_float(variables.get("finance_confirm_delay"), 2.0)
                    retries = _as_int(variables.get("finance_confirm_retries"), 6)
                    if initial_delay > 0:
                        time.sleep(initial_delay)
                    attempts = []
                    list_payload: Dict[str, Any] = {}
                    confirm_payload: Dict[str, Any] = {}
                    selected_bill: Dict[str, Any] | None = None
                    for attempt in range(retries):
                        list_fields = _finance_unconfirm_fields(variables, serial_number, str(payment_data.get("order_sn") or order_sn))
                        list_payload = _post_admin_form(
                            session,
                            base_url,
                            _api_path(variables, "admin_bill_unconfirm_list", "/bill.unConfirmList"),
                            list_fields,
                            timeout,
                        )
                        rows = _finance_rows_from_payload(list_payload)
                        selected_bill = _select_finance_bill(rows, serial_number, str(payment_data.get("order_sn") or order_sn))
                        attempt_brief = {
                            **_payload_brief(list_payload),
                            "request": dict(list_fields),
                            "row_count": len(rows),
                            "selected_bill": _finance_bill_brief(selected_bill),
                            "serial_number": serial_number,
                            "attempt": attempt + 1,
                        }
                        attempts.append(attempt_brief)
                        if _api_success(list_payload) and selected_bill and selected_bill.get("id") not in (None, ""):
                            break
                        if attempt < retries - 1:
                            time.sleep(retry_delay)
                    log["finance"]["unconfirm_list_attempts"] = attempts
                    log["finance"]["unconfirm_list"] = attempts[-1] if attempts else {"serial_number": serial_number}
                    if _api_success(list_payload) and selected_bill and selected_bill.get("id") not in (None, ""):
                        confirm_payload = _post_admin_form(
                            session,
                            base_url,
                            _api_path(variables, "admin_bill_confirm", "/bill.confirm"),
                            {"id": selected_bill.get("id")},
                            timeout,
                        )
                        finance_ok = _api_success(confirm_payload)
                        log["finance"]["confirm"] = {
                            **_payload_brief(confirm_payload),
                            "request": {"id": selected_bill.get("id")},
                            "selected_bill": _finance_bill_brief(selected_bill),
                        }
                    else:
                        finance_ok = False
                        log["finance"]["confirm"] = {"serial_number": serial_number, "selected_bill": _finance_bill_brief(selected_bill)}
                    if not finance_ok:
                        last_payload = confirm_payload or list_payload
                        last_msg = last_payload.get("msg") or last_payload.get("data") or "\u8d22\u52a1\u786e\u8ba4\u6c47\u6b3e\u5931\u8d25"
                        log["finance"]["reason"] = f"\u8d22\u52a1\u786e\u8ba4\u6c47\u6b3e\u5931\u8d25\uff1a{last_msg}"

        passed = payment_ok and finance_ok
        summary = _common_payment_summary(
            "bank",
            str(payment_data.get("order_sn") or order_sn),
            amount,
            payment_payload,
            {
                "serial_number": serial_number,
                "finance_confirm": finance_confirm,
                "finance_passed": finance_ok,
            },
        )
        finance_reason = log.get("finance", {}).get("reason")
        if not passed and finance_reason:
            summary["reason"] = finance_reason
        elif not passed and "reason" not in summary:
            summary["reason"] = "\u94f6\u884c\u652f\u4ed8\u6216\u8d22\u52a1\u786e\u8ba4\u5931\u8d25"
        return _finish_named(BANK_PAYMENT_SCRIPT_NAME, log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            BANK_PAYMENT_SCRIPT_NAME,
            log,
            False,
            {"payment_type": "bank", "order_sn": "", "pay_amount": "0", "error": str(exc)},
        )


def preview_order_quote_options(env: Env, variables: Dict[str, Any] | None = None) -> Dict[str, Any]:
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


def run_order_quote_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})

    account = str(variables.get("account") or "").strip()
    password = str(variables.get("password") or "").strip()
    client_tool = str(variables.get("client_tool") or "1").strip()
    if client_tool == "2" and not _as_bool(variables.get("allow_h5_client_tool"), False):
        client_tool = "1"
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
    item_quantity = _as_int(variables.get("order_item_num") or variables.get("num"), 10)
    price_cut = str(variables.get("priceCut") or variables.get("price_cut") or "0")
    logistics_id = str(variables.get("logistics_id") or "1")
    client_remark = str(variables.get("client_remark") or "\u81ea\u52a8\u5316\u63d0\u51fa\u8ba2\u5355")
    requested_type = str(variables.get("create_type") or "send").strip().lower()
    submit_order = requested_type != "save" and _as_bool(variables.get("submit_order"), True)
    seed_order_sn = str(variables.get("order_sn") or "").strip()
    run_backend_flow = submit_order and _as_bool(variables.get("run_backend_flow"), True)
    skip_create_order = _as_bool(variables.get("skip_create_order") or variables.get("backend_only"), False)
    option_counts = _normalize_order_option_counts(variables.get("order_option_counts"))

    log: Dict[str, Any] = {
        "script": ORDER_SCRIPT_NAME,
        "mode": "backend_only" if skip_create_order else "cart_to_order_and_backend_quote",
        "base_url": base_url,
        "item_count": item_count,
        "order_shop_count": order_shop_count if use_shop_grouping else None,
        "order_per_shop": order_per_shop if use_shop_grouping else None,
        "use_shop_grouping": use_shop_grouping,
        "item_quantity": item_quantity,
        "price_cut": price_cut,
        "submit_order": submit_order,
        "run_backend_flow": run_backend_flow,
        "order_option_counts": dict(option_counts),
        "started_at": datetime.now(),
        "selected_items": [],
        "edits": [],
        "create": {},
    }

    try:
        if skip_create_order:
            if not seed_order_sn:
                return _finish_named(
                    ORDER_SCRIPT_NAME,
                    log,
                    False,
                    {
                        "order_sn": "",
                        "selected_count": 0,
                        "item_quantity": item_quantity,
                        "reason": "后台单独执行时必须传入 order_sn",
                    },
                )
            summary = {
                "order_sn": seed_order_sn,
                "selected_count": 0,
                "item_quantity": item_quantity,
                "submit_order": submit_order,
                "skip_create_order": True,
            }
            if run_backend_flow:
                backend_passed, backend_summary = _run_backend_order_flow(
                    base_url, timeout, variables, seed_order_sn, item_quantity, log
                )
                summary.update(backend_summary)
                if not backend_passed and "reason" not in summary:
                    summary["reason"] = "后台订单报价流程失败"
                return _finish_named(ORDER_SCRIPT_NAME, log, backend_passed, summary)
            return _finish_named(ORDER_SCRIPT_NAME, log, True, summary)

        runtime = _runtime_from_variables(variables)
        if runtime:
            client, _base_url, _timeout, token, _cached = runtime.client(env, variables, log=log)
        else:
            client = bulk_cart.RakumartClient(base_url, timeout)
            _configure_client_api_paths(client, variables)
            token = _call_with_retry("client login", lambda: client.login(account, password, client_tool))
            log["login"] = {"success": True, "account": account, "client_tool": client_tool, "token_extracted": bool(token)}

        # 若需要 order option，提前并行拉取 option_catalog，与 cart_list 并行以节省时间
        option_prefetch_executor = None
        option_prefetch_future = None
        if option_counts:
            option_prefetch_executor = ThreadPoolExecutor(max_workers=1)
            option_prefetch_future = option_prefetch_executor.submit(_fetch_order_option_catalog, client, variables)

        cart_payload = _call_with_retry(
            "cart list",
            lambda: client.post_form(_api_path(variables, "client_cart_list", "/client/cart.goodsCartList"), {"priceCut": price_cut}),
        )
        cart_goods = _flatten_cart_goods(cart_payload)
        if not cart_goods and price_cut != "0":
            fallback_payload = _call_with_retry(
                "cart list fallback",
                lambda: client.post_form(_api_path(variables, "client_cart_list", "/client/cart.goodsCartList"), {"priceCut": "0"}),
            )
            fallback_goods = _flatten_cart_goods(fallback_payload)
            log["cart_list_retry"] = {
                "price_cut": "0",
                **_payload_brief(fallback_payload),
                "goods_count": len(fallback_goods),
            }
            if fallback_goods:
                cart_payload = fallback_payload
                cart_goods = fallback_goods
                price_cut = "0"
        selection_meta: Dict[str, Any] = {}
        if use_shop_grouping:
            selected_items, selection_meta = _select_cart_items_by_shop(cart_payload, order_shop_count, order_per_shop)
        else:
            selected_items = _select_cart_items(cart_payload, item_count)
            selection_meta = {
                "expected_total": item_count,
                "selected_count": len(selected_items),
                "shortage_count": max(0, item_count - len(selected_items)),
            }
        log["cart_list"] = {
            **_payload_brief(cart_payload),
            "goods_count": len(cart_goods),
            "selected_count": len(selected_items),
            "selection": selection_meta,
        }
        log["selected_items"] = [_order_item_brief(item) for item in selected_items]
        if len(selected_items) < item_count:
            shortage_summary = {
                "order_sn": "",
                "selected_count": len(selected_items),
                "expected_count": item_count,
                "reason_code": "cart_items_shortage",
                "shortage_count": max(0, item_count - len(selected_items)),
                "reason": "\u8d2d\u7269\u8f66\u53ef\u63d0\u5355\u5546\u54c1\u4e0d\u8db3",
            }
            if use_shop_grouping:
                shortage_summary.update(
                    {
                        "expected_shop_count": order_shop_count,
                        "expected_per_shop": order_per_shop,
                        "available_shop_count": selection_meta.get("available_shop_count", 0),
                        "ready_shop_count": selection_meta.get("ready_shop_count", 0),
                        "selected_shop_count": selection_meta.get("selected_shop_count", 0),
                        "shortage_count": selection_meta.get("shortage_count", shortage_summary["shortage_count"]),
                    }
                )
            return _finish_named(
                ORDER_SCRIPT_NAME,
                log,
                False,
                shortage_summary,
            )

        edit_logs, failed_edits = _edit_cart_items_for_order(
            client,
            base_url,
            timeout,
            variables,
            selected_items,
            item_quantity,
            token,
        )
        log["edits"].extend(edit_logs)
        if failed_edits:
            return _finish_named(
                ORDER_SCRIPT_NAME,
                log,
                False,
                {
                    "order_sn": "",
                    "selected_count": len(selected_items),
                    "item_quantity": item_quantity,
                    "failed_edit_cart_ids": failed_edits,
                    "reason": "\u6709\u8d2d\u7269\u8f66\u5546\u54c1\u6570\u91cf\u4fee\u6539\u5931\u8d25",
                },
            )

        if option_counts:
            # 复用预取结果，避免与 cart_list 串行等待；预取失败则回退串行重试
            if option_prefetch_future is not None:
                try:
                    option_catalog, option_payload, option_path = option_prefetch_future.result()
                except Exception as exc:
                    log["order_option_prefetch_error"] = str(exc)
                    option_catalog, option_payload, option_path = _fetch_order_option_catalog(client, variables)
                finally:
                    if option_prefetch_executor is not None:
                        option_prefetch_executor.shutdown(wait=False)
            else:
                option_catalog, option_payload, option_path = _fetch_order_option_catalog(client, variables)
            log["order_option_list"] = {
                "source_path": option_path,
                **_payload_brief(option_payload),
                "option_count": len(option_catalog),
            }
            option_summary = _apply_order_options_to_items(selected_items, variables, option_catalog)
            log["order_options"] = option_summary
            if option_summary.get("missing"):
                return _finish_named(
                    ORDER_SCRIPT_NAME,
                    log,
                    False,
                    {
                        "order_sn": "",
                        "selected_count": len(selected_items),
                        "item_quantity": item_quantity,
                        "missing_order_options": option_summary["missing"],
                        "reason": "已选择的订单 option 在接口返回中不存在，已停止创建订单",
                    },
                )
        else:
            option_summary = _apply_order_options_to_items(selected_items, variables, OrderedDict())
            log["order_options"] = option_summary
        save_fields = _order_fields(selected_items, "save", seed_order_sn, item_quantity, logistics_id, client_remark)
        save_payload = _call_with_retry(
            "order save",
            lambda: client.post_form(_api_path(variables, "client_order_create", "/client/order.orderCreate"), save_fields),
        )
        order_sn = _extract_order_sn(save_payload) or seed_order_sn
        log["create"]["save"] = {**_payload_brief(save_payload), "order_sn": order_sn}
        if not _api_success(save_payload) or not order_sn:
            # 解析"商品数超过最大限制"提示，按后端给的最大数量截断后重试一次
            save_msg = str(save_payload.get("msg") or save_payload.get("data") or "")
            max_limit = _parse_order_max_limit(save_msg)
            if max_limit and len(selected_items) > max_limit:
                log["create"]["save_limit_retry"] = {
                    "original_count": len(selected_items),
                    "max_limit": max_limit,
                    "raw_msg": save_msg,
                }
                selected_items = selected_items[:max_limit]
                if option_counts:
                    option_summary = _apply_order_options_to_items(selected_items, variables, option_catalog)
                else:
                    option_summary = _apply_order_options_to_items(selected_items, variables, OrderedDict())
                log["order_options"] = option_summary
                save_fields = _order_fields(selected_items, "save", seed_order_sn, item_quantity, logistics_id, client_remark)
                save_payload = _call_with_retry(
                    "order save retry",
                    lambda: client.post_form(_api_path(variables, "client_order_create", "/client/order.orderCreate"), save_fields),
                )
                order_sn = _extract_order_sn(save_payload) or seed_order_sn
                log["create"]["save_retry"] = {**_payload_brief(save_payload), "order_sn": order_sn, "truncated_to": max_limit}
            if not _api_success(save_payload) or not order_sn:
                final_msg = _translate_order_msg(save_payload.get("msg") or save_payload.get("data")) or "临时保存订单失败"
                return _finish_named(
                    ORDER_SCRIPT_NAME,
                    log,
                    False,
                    {
                        "order_sn": order_sn,
                        "selected_count": len(selected_items),
                        "item_quantity": item_quantity,
                        "reason": final_msg,
                    },
                )

        final_payload = save_payload
        if submit_order:
            send_fields = _order_fields(selected_items, "send", order_sn, item_quantity, logistics_id, client_remark)
            final_payload = _call_with_retry(
                "order send",
                lambda: client.post_form(_api_path(variables, "client_order_create", "/client/order.orderCreate"), send_fields),
            )
            log["create"]["send"] = {**_payload_brief(final_payload), "order_sn": _extract_order_sn(final_payload) or order_sn}

        passed = _api_success(final_payload)
        final_order_sn = _extract_order_sn(final_payload) or order_sn
        summary = {
            "order_sn": final_order_sn,
            "selected_count": len(selected_items),
            "item_quantity": item_quantity,
            "submit_order": submit_order,
            "run_backend_flow": run_backend_flow,
            "cart_ids": [item.get("id") for item in selected_items],
            "goods_ids": [item.get("goods_id") for item in selected_items],
            "order_options": option_summary.get("selected_options", []),
            "order_option_applied_detail_count": option_summary.get("applied_detail_count", 0),
        }
        if use_shop_grouping:
            summary.update(
                {
                    "expected_shop_count": order_shop_count,
                    "expected_per_shop": order_per_shop,
                    "selected_shop_count": selection_meta.get("selected_shop_count", 0),
                    "available_shop_count": selection_meta.get("available_shop_count", 0),
                    "ready_shop_count": selection_meta.get("ready_shop_count", 0),
                }
            )
        if not passed:
            final_msg = _translate_order_msg(final_payload.get("msg") or final_payload.get("data"))
            summary["reason"] = final_msg or ("\u6b63\u5f0f\u63d0\u51fa\u8ba2\u5355\u5931\u8d25" if submit_order else "\u8ba2\u5355\u4fdd\u5b58\u5931\u8d25")
        elif _checkpoint_requested(variables, "order_created"):
            return _finish_named(ORDER_SCRIPT_NAME, log, True, _paused_summary("order_created", summary))
        elif run_backend_flow:
            backend_passed, backend_summary = _run_backend_order_flow(
                base_url, timeout, variables, final_order_sn, item_quantity, log
            )
            summary.update(backend_summary)
            passed = backend_passed
            if not backend_passed and "reason" not in summary:
                summary["reason"] = "后台订单报价流程失败"
        return _finish_named(ORDER_SCRIPT_NAME, log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            ORDER_SCRIPT_NAME,
            log,
            False,
            {
                "order_sn": "",
                "selected_count": 0,
                "item_quantity": item_quantity,
                "error": str(exc),
            },
        )


MATERIAL_GENERATION_SCRIPT_NAME = "辅料生成"
MATERIAL_ORDER_SCRIPT_NAME = "辅料单"



def run_material_generation_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """辅料生成脚本 - 通过后端代理调用 jpapi 接口，避免 CORS 问题"""
    ensure_report_dirs()
    variables = dict(variables or {})
    started_at = datetime.now()

    account, password, client_tool = _client_login_inputs(variables)
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")

    base_name = str(variables.get("name") or "").strip()
    count = max(1, _as_int(variables.get("count"), 1))

    log: Dict[str, Any] = {
        "script": MATERIAL_GENERATION_SCRIPT_NAME,
        "base_url": base_url,
        "name": base_name,
        "count": count,
        "started_at": started_at,
    }

    if not base_name:
        return _finish_named(
            MATERIAL_GENERATION_SCRIPT_NAME, log, False,
            {"reason": "缺少必要参数：辅料名称不能为空"},
        )

    try:
        # 登录客户端
        client = bulk_cart.RakumartClient(base_url, timeout)
        _configure_client_api_paths(client, variables)
        token = _call_with_retry("client login", lambda: client.login(account, password, client_tool))
        log["login"] = {"success": True, "account": account, "token_extracted": bool(token)}

        # 查询已有辅料名称，并解析最大编号
        list_url = base_url + "/client/material/material/list"
        existing_names: set = set()
        max_existing_idx = 0
        _name_pattern = re.compile(r"^" + re.escape(base_name) + r"-(\d+)$")

        def _parse_list_items(list_data: Any) -> list:
            """从列表接口响应中提取 items，兼容多种返回格式"""
            if not isinstance(list_data, dict):
                return []
            data = list_data.get("data")
            if isinstance(data, dict):
                return data.get("data") or data.get("list") or data.get("items") or []
            if isinstance(data, list):
                return data
            return []

        # 先不带 name 过滤拉取全量列表（某些接口 name 是精确匹配，模糊搜索需空 name）
        _query_variants = [
            {"page": "1", "pageSize": "500"},
            {"name": "", "page": "1", "pageSize": "500"},
            {"name": base_name, "page": "1", "pageSize": "500"},
        ]
        for query_params in _query_variants:
            try:
                list_resp = client.session.get(list_url, params=query_params, timeout=timeout)
                log.setdefault("list_responses", []).append({
                    "params": dict(query_params),
                    "method": "GET",
                    "status": list_resp.status_code,
                    "body_preview": list_resp.text[:800] if list_resp.ok else list_resp.text[:300],
                })
                if list_resp.ok:
                    list_data = list_resp.json()
                    if list_data.get("success") or list_data.get("code") == 200 or list_data.get("code") == 0:
                        items = _parse_list_items(list_data)
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict) and item.get("name"):
                                    name_text = item["name"]
                                    existing_names.add(name_text)
                                    _m = _name_pattern.match(name_text)
                                    if _m:
                                        max_existing_idx = max(max_existing_idx, int(_m.group(1)))
            except Exception as list_err:
                log.setdefault("list_errors", []).append(f"GET {query_params}: {list_err}")

        # 如果 GET 方式没查到数据，尝试 POST form-data（部分接口只接受 POST）
        if not existing_names:
            _post_variants = [
                {"page": "1", "pageSize": "500"},
                {"name": "", "page": "1", "pageSize": "500"},
                {"name": base_name, "name_trans": "", "type_id": "", "page": "1", "pageSize": "500"},
            ]
            for post_fields in _post_variants:
                try:
                    files = [(k, (None, str(v))) for k, v in post_fields.items()]
                    list_resp = client.session.post(list_url, files=files, timeout=timeout)
                    log.setdefault("list_responses", []).append({
                        "params": dict(post_fields),
                        "method": "POST",
                        "status": list_resp.status_code,
                        "body_preview": list_resp.text[:800] if list_resp.ok else list_resp.text[:300],
                    })
                    if list_resp.ok:
                        list_data = list_resp.json()
                        if list_data.get("success") or list_data.get("code") == 200 or list_data.get("code") == 0:
                            items = _parse_list_items(list_data)
                            if isinstance(items, list):
                                for item in items:
                                    if isinstance(item, dict) and item.get("name"):
                                        name_text = item["name"]
                                        existing_names.add(name_text)
                                        _m = _name_pattern.match(name_text)
                                        if _m:
                                            max_existing_idx = max(max_existing_idx, int(_m.group(1)))
                except Exception as list_err:
                    log.setdefault("list_errors", []).append(f"POST {post_fields}: {list_err}")

        # 从已有最大编号 +1 开始创建
        start_idx = max_existing_idx + 1
        log["existing_count"] = len(existing_names)
        log["max_existing_idx"] = max_existing_idx
        log["start_idx"] = start_idx

        # 循环创建辅料
        created: list = []
        skipped: list = []
        idx = start_idx
        max_iterations = start_idx + count + 200
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 10

        while len(created) < count and idx <= max_iterations and consecutive_failures < MAX_CONSECUTIVE_FAILURES:
            candidate = f"{base_name}-{idx}"
            if candidate in existing_names:
                skipped.append(candidate)
                idx += 1
                continue

            body_obj = {
                "name": candidate,
                "name_trans": candidate,
                "type_id": 1,
                "consume": 1,
                "main_image": "https://rakumart-ps20.oss-ap-northeast-1.aliyuncs.com/dest/202606/265055113/O1CN01nklPMm2KqWS7HYtvi_!!2248919608.jpg",
                "notice": "",
            }
            try:
                create_resp = client.session.post(
                    base_url + "/client/material/material/store",
                    json=body_obj,
                    timeout=timeout,
                )
                if create_resp.ok:
                    create_data = create_resp.json()
                    if create_data.get("success"):
                        created.append({"name": candidate, "id": create_data.get("data", {}).get("id", "")})
                        consecutive_failures = 0
                    else:
                        skipped.append(f"{candidate}({create_data.get('msg', '创建失败')})")
                        consecutive_failures += 1
                else:
                    skipped.append(f"{candidate}(HTTP {create_resp.status_code})")
                    consecutive_failures += 1
            except Exception as fetch_err:
                skipped.append(f"{candidate}(网络错误: {fetch_err})")
                consecutive_failures += 1

            existing_names.add(candidate)
            idx += 1

        passed = len(created) > 0
        reason = ""
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES and len(created) < count:
            reason = f"连续 {MAX_CONSECUTIVE_FAILURES} 次创建失败，已中止。已创建 {len(created)}/{count}"
        elif len(created) < count:
            reason = f"达到最大尝试次数，已创建 {len(created)}/{count}"

        summary: Dict[str, Any] = {
            "material_generation_name": base_name,
            "material_generation_count": count,
            "created_count": len(created),
            "skipped_count": len(skipped),
            "created_list": [c["name"] for c in created],
            "skipped_list": skipped,
            "completed": passed,
        }
        if reason:
            summary["reason"] = reason

        return _finish_named(MATERIAL_GENERATION_SCRIPT_NAME, log, passed, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            MATERIAL_GENERATION_SCRIPT_NAME, log, False,
            {"reason": str(exc), "error": str(exc)},
        )


def run_balance_recharge_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """\u4f59\u989d\u5145\u503c\u811a\u672c - \u524d\u53f0\u63d0\u4ea4\u94f6\u884c\u5145\u503c\u7533\u8bf7\uff0c\u540e\u53f0\u767b\u5f55\u540e\u786e\u8ba4\u5165\u91d1\uff0c\u5145\u503c\u91d1\u989d\u5230\u8fbe\u8be5\u8d26\u53f7\u4f59\u989d\u3002

    \u63a5\u53e3\uff1a
    - \u524d\u53f0\u63d0\u4ea4 POST /client/user.bankPayBalance (ClientToken)
      \u5b57\u6bb5: pay_bank_method, pay_reach_date, pay_date, pay_name, pay_amount, pay_remark
    - \u540e\u53f0\u67e5\u8be2 POST /bill.unConfirmList (AdminToken)
    - \u540e\u53f0\u786e\u8ba4 POST /bill.confirm (AdminToken)  \u5b57\u6bb5: id

    \u53ef\u914d\u7f6e\u53d8\u91cf\uff1a
    - customer_id: \u5fc5\u586b\uff0c\u5145\u503c\u5230\u8be5\u5ba2\u6237\u4f59\u989d\uff08\u7531\u524d\u7aef/\u8def\u7531\u5c42\u6ce8\u5165\uff09
    - amount: \u5fc5\u586b\uff0c\u5145\u503c\u91d1\u989d\uff08\u6620\u5c04\u5230 pay_amount\uff09
    - pay_bank_method / pay_date / pay_reach_date / pay_name / pay_remark\uff1a\u53ef\u8986\u76d6\u9ed8\u8ba4\u503c
    - client_recharge\uff1a\u524d\u53f0\u5145\u503c\u63d0\u4ea4\u63a5\u53e3\uff08\u9ed8\u8ba4 /client/user.bankPayBalance\uff09
    - finance_confirm\uff1a\u662f\u5426\u6267\u884c\u540e\u53f0\u786e\u8ba4\uff08\u9ed8\u8ba4 True\uff09
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    customer_id = str(variables.get("customer_id") or "").strip()
    amount = str(variables.get("amount") or variables.get("recharge_amount") or "").strip()
    log: Dict[str, Any] = {
        "script": BALANCE_RECHARGE_SCRIPT_NAME,
        "mode": "balance_recharge",
        "started_at": datetime.now(),
        "customer_id": customer_id,
        "amount": amount,
        "recharge": {},
        "finance": {},
    }

    if not customer_id:
        return _finish_named(
            BALANCE_RECHARGE_SCRIPT_NAME, log, False,
            {"reason": "\u7f3a\u5c11\u5fc5\u586b\u53c2\u6570\uff1acustomer_id \u4e0d\u80fd\u4e3a\u7a7a"},
        )
    if not _positive_decimal(amount):
        return _finish_named(
            BALANCE_RECHARGE_SCRIPT_NAME, log, False,
            {"reason": "\u7f3a\u5c11\u5fc5\u586b\u53c2\u6570\uff1a\u5145\u503c\u91d1\u989d amount \u5fc5\u987b\u4e3a\u6b63\u6570"},
        )

    try:
        client, base_url, timeout, _ = _login_client_for_payment(env, variables, log)
        log["base_url"] = base_url

        # Step 1: 前台提交充值申请 POST /client/user.bankPayBalance
        now = datetime.now()
        pay_bank_method = str(variables.get("pay_bank_method") or "2")
        pay_date = str(variables.get("pay_date") or now.strftime("%Y/%m/%d %H:%M:%S"))
        pay_reach_date = str(variables.get("pay_reach_date") or now.strftime("%Y-%m-%d 00:00:00"))
        pay_name = str(variables.get("pay_name") or "\u81ea\u52a8\u5316\u5145\u503c")
        pay_remark = str(variables.get("pay_remark") or "")
        fields: OrderedDict[str, Any] = OrderedDict()
        fields["pay_bank_method"] = pay_bank_method
        fields["pay_reach_date"] = pay_reach_date
        fields["pay_date"] = pay_date
        fields["pay_name"] = pay_name
        fields["pay_amount"] = amount
        fields["pay_remark"] = pay_remark
        _apply_extra_fields(fields, variables.get("recharge_fields"))
        recharge_payload = _call_with_retry(
            "balance recharge",
            lambda: client.post_form(_api_path(variables, "client_recharge", "/client/user.bankPayBalance"), fields),
        )
        recharge_ok = _api_success(recharge_payload)
        recharge_data = recharge_payload.get("data") if isinstance(recharge_payload.get("data"), dict) else {}
        serial_number = str(recharge_data.get("serial_number") or recharge_data.get("recharge_no") or recharge_data.get("bill_no") or "")
        log["recharge"] = {**_payload_brief(recharge_payload), "request": dict(fields), "serial_number": serial_number}
        if not recharge_ok:
            reason = str(recharge_payload.get("msg") or recharge_payload.get("data") or "\u524d\u53f0\u5145\u503c\u63d0\u4ea4\u5931\u8d25")
            return _finish_named(
                BALANCE_RECHARGE_SCRIPT_NAME, log, False,
                {
                    "recharge_type": "balance",
                    "customer_id": customer_id,
                    "amount": amount,
                    "serial_number": serial_number,
                    "recharge_passed": False,
                    "confirm_passed": False,
                    "reason": reason,
                },
            )

        # Step 2: 后台确认入金
        finance_confirm = _as_bool(variables.get("finance_confirm"), True)
        confirm_ok = True
        if finance_confirm:
            session = _admin_session_from(variables)
            login_payload, token = _admin_login(session, base_url, variables, timeout)
            log["finance"]["login"] = {
                **_payload_brief(login_payload),
                "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
                "token_extracted": bool(token),
            }
            if not _api_success(login_payload) or not token:
                confirm_ok = False
                log["finance"]["reason"] = "\u540e\u53f0\u767b\u5f55\u5931\u8d25"
            else:
                initial_delay = _as_float(variables.get("finance_confirm_initial_delay"), 2.0)
                retry_delay = _as_float(variables.get("finance_confirm_delay"), 2.0)
                retries = _as_int(variables.get("finance_confirm_retries"), 6)
                if initial_delay > 0:
                    time.sleep(initial_delay)
                list_payload: Dict[str, Any] = {}
                confirm_payload: Dict[str, Any] = {}
                selected_bill: Dict[str, Any] | None = None
                for attempt in range(retries):
                    list_fields = _finance_unconfirm_fields(variables, serial_number, "")
                    list_payload = _post_admin_form(
                        session,
                        base_url,
                        _api_path(variables, "admin_bill_unconfirm_list", "/bill.unConfirmList"),
                        list_fields,
                        timeout,
                    )
                    rows = _finance_rows_from_payload(list_payload)
                    selected_bill = _select_finance_bill(rows, serial_number, "")
                    if _api_success(list_payload) and selected_bill and selected_bill.get("id") not in (None, ""):
                        break
                    if attempt < retries - 1:
                        time.sleep(retry_delay)
                log["finance"]["unconfirm_list"] = {**_payload_brief(list_payload), "serial_number": serial_number, "selected_bill": _finance_bill_brief(selected_bill)}
                if _api_success(list_payload) and selected_bill and selected_bill.get("id") not in (None, ""):
                    confirm_payload = _post_admin_form(
                        session,
                        base_url,
                        _api_path(variables, "admin_bill_confirm", "/bill.confirm"),
                        {"id": selected_bill.get("id")},
                        timeout,
                    )
                    confirm_ok = _api_success(confirm_payload)
                    log["finance"]["confirm"] = {**_payload_brief(confirm_payload), "request": {"id": selected_bill.get("id")}}
                else:
                    confirm_ok = False
                    log["finance"]["confirm"] = {"serial_number": serial_number, "selected_bill": _finance_bill_brief(selected_bill)}
                if not confirm_ok:
                    last_payload = confirm_payload or list_payload
                    last_msg = last_payload.get("msg") or last_payload.get("data") or "\u8d22\u52a1\u786e\u8ba4\u5165\u91d1\u5931\u8d25"
                    log["finance"]["reason"] = f"\u8d22\u52a1\u786e\u8ba4\u5165\u91d1\u5931\u8d25\uff1a{last_msg}"

        passed = recharge_ok and confirm_ok
        summary = {
            "recharge_type": "balance",
            "customer_id": customer_id,
            "amount": amount,
            "serial_number": serial_number,
            "recharge_passed": recharge_ok,
            "confirm_passed": confirm_ok,
        }
        if not passed and "reason" not in summary:
            summary["reason"] = log.get("finance", {}).get("reason") or "\u4f59\u989d\u5145\u503c\u5931\u8d25"
        return _finish_named(BALANCE_RECHARGE_SCRIPT_NAME, log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            BALANCE_RECHARGE_SCRIPT_NAME, log, False,
            {"recharge_type": "balance", "customer_id": customer_id, "amount": amount, "reason": str(exc)},
        )


SCRIPT_REGISTRY: Dict[str, Any] = {
    "shopping_cart": {
        "name": SCRIPT_NAME,
        "func": None,
    },
    "order_quote": {
        "name": ORDER_SCRIPT_NAME,
        "func": None,
    },
    "balance_payment": {
        "name": BALANCE_PAYMENT_SCRIPT_NAME,
        "func": None,
    },
    "bank_payment": {
        "name": BANK_PAYMENT_SCRIPT_NAME,
        "func": None,
    },
    "purchase_to_shelf": {
        "name": PURCHASE_TO_SHELF_SCRIPT_NAME,
        "func": None,
    },
    "purchase_to_shelf_chain": {
        "name": "\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6(\u7ec4\u5408\u811a\u672c)",
        "func": None,
        "chain": True,
    },
    "warehouse_delivery": {
        "name": WAREHOUSE_DELIVERY_SCRIPT_NAME,
        "func": None,
    },
    "porder_balance_payment": {
        "name": POORDER_BALANCE_PAYMENT_SCRIPT_NAME,
        "func": None,
    },
    "porder_bank_payment": {
        "name": POORDER_BANK_PAYMENT_SCRIPT_NAME,
        "func": None,
    },
    "full_flow": {
        "name": FULL_FLOW_SCRIPT_NAME,
        "func": None,
        "chain": True,
    },
    "direct_box_to_shelf": {
        "name": DIRECT_BOX_TO_SHELF_SCRIPT_NAME,
        "func": None,
        "chain": True,
    },
    "resume_order_flow": {
        "name": RESUME_ORDER_FLOW_SCRIPT_NAME,
        "func": None,
        "chain": True,
    },
    "resume_porder_flow": {
        "name": RESUME_PORDER_FLOW_SCRIPT_NAME,
        "func": None,
        "chain": True,
    },
    "material_order": {
        "name": MATERIAL_ORDER_SCRIPT_NAME,
        "func": run_material_order_script,
    },

    "material_generation": {
        "name": MATERIAL_GENERATION_SCRIPT_NAME,
        "func": run_material_generation_script,
    },
    "balance_recharge": {
        "name": BALANCE_RECHARGE_SCRIPT_NAME,
        "func": run_balance_recharge_script,
    },
}


def run_purchase_to_shelf_chain(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    chain_log: Dict[str, Any] = {
        "script": "待拍下到商品上架(组合脚本)",
        "mode": "chain_execution",
        "started_at": datetime.now(),
        "steps": [],
        "shared_data": {},
    }

    try:
        import sys

        ds = sys.modules[__name__]

        # Step 1: 订单报价
        quote_vars = dict(variables)
        quote_vars.pop("order_sn", None)
        quote_vars.pop("last_order_sn", None)
        quote_vars["skip_create_order"] = False
        quote_vars["backend_only"] = False
        quote_vars["submit_order"] = True
        quote_vars["run_backend_flow"] = True
        quote_result = run_order_quote_script(env, quote_vars)
        quote_passed, quote_log, quote_report, quote_summary = quote_result
        chain_log["steps"].append({
            "step": 1,
            "script": ORDER_SCRIPT_NAME,
            "passed": quote_passed,
            "summary": quote_summary,
        })

        if not quote_passed or not quote_summary.get("order_sn"):
            chain_log["finished_at"] = datetime.now()
            chain_log["summary"] = {
                "passed": False,
                "reason": "订单报价脚本失败，未生成订单号",
                "order_sn": "",
            }
            log_text = json.dumps(chain_log, ensure_ascii=False, indent=2, default=str)
            report_path = write_allure_result("待拍下到商品上架(组合脚本)", "data_script", False, log_text)
            return False, log_text, report_path, chain_log["summary"]

        order_sn = quote_summary["order_sn"]
        chain_log["shared_data"]["order_sn"] = order_sn

        # Step 2: 余额支付
        pay_vars = dict(variables)
        pay_vars["order_sn"] = order_sn
        balance_result = run_balance_payment_script(env, pay_vars)
        balance_passed, balance_log, balance_report, balance_summary = balance_result
        chain_log["steps"].append({
            "step": 2,
            "script": BALANCE_PAYMENT_SCRIPT_NAME,
            "passed": balance_passed,
            "summary": balance_summary,
        })

        if not balance_passed:
            chain_log["finished_at"] = datetime.now()
            chain_log["summary"] = {
                "passed": False,
                "reason": "余额支付脚本失败",
                "order_sn": order_sn,
                "failed_step": "余额支付",
            }
            log_text = json.dumps(chain_log, ensure_ascii=False, indent=2, default=str)
            report_path = write_allure_result("待拍下到商品上架(组合脚本)", "data_script", False, log_text)
            return False, log_text, report_path, chain_log["summary"]

        # Step 3: 待拍下到商品上架
        shelf_vars = dict(variables)
        shelf_vars["order_sn"] = order_sn
        shelf_vars["purchase_no"] = str(variables.get("purchase_no") or datetime.now().strftime("%Y%m%d%H%M%S"))
        shelf_vars["link_quote_balance_before_shelf"] = False
        shelf_vars["auto_quote_and_pay"] = False
        shelf_result = run_purchase_to_shelf_script(env, shelf_vars)
        shelf_passed, shelf_log, shelf_report, shelf_summary = shelf_result
        chain_log["steps"].append({
            "step": 3,
            "script": PURCHASE_TO_SHELF_SCRIPT_NAME,
            "passed": shelf_passed,
            "summary": shelf_summary,
        })

        chain_passed = shelf_passed
        chain_log["finished_at"] = datetime.now()
        chain_log["summary"] = {
            "passed": chain_passed,
            "order_sn": order_sn,
            "purchase_no": shelf_vars.get("purchase_no", ""),
            "total_steps": 3,
            "success_steps": sum(1 for s in chain_log["steps"] if s["passed"]),
        }
        for key in [
            "storage_passed",
            "verify_passed",
            "remaining_purchase_count",
            "remaining_pending_count",
            "purchase_ids",
            "grid_id",
            "grid_number",
        ]:
            if key in shelf_summary:
                chain_log["summary"][key] = shelf_summary[key]
        if not chain_passed:
            chain_log["summary"]["reason"] = "待拍下到商品上架脚本失败"
            chain_log["summary"]["failed_step"] = "待拍下到商品上架"

        log_text = json.dumps(chain_log, ensure_ascii=False, indent=2, default=str)
        report_path = write_allure_result("待拍下到商品上架(组合脚本)", "data_script", chain_passed, log_text)
        return chain_passed, log_text, report_path, chain_log["summary"]

    except Exception as exc:
        chain_log["error"] = str(exc)
        chain_log["finished_at"] = datetime.now()
        chain_log["summary"] = {"passed": False, "reason": str(exc)}
        log_text = json.dumps(chain_log, ensure_ascii=False, indent=2, default=str)
        report_path = write_allure_result("待拍下到商品上架(组合脚本)", "data_script", False, log_text)
        return False, log_text, report_path, chain_log["summary"]


# 注册脚本函数
SCRIPT_REGISTRY["shopping_cart"]["func"] = run_shopping_cart_script
SCRIPT_REGISTRY["order_quote"]["func"] = run_order_quote_script
SCRIPT_REGISTRY["balance_payment"]["func"] = run_balance_payment_script
SCRIPT_REGISTRY["bank_payment"]["func"] = run_bank_payment_script
SCRIPT_REGISTRY["purchase_to_shelf"]["func"] = run_purchase_to_shelf_script
SCRIPT_REGISTRY["purchase_to_shelf_chain"]["func"] = run_purchase_to_shelf_chain
SCRIPT_REGISTRY["warehouse_delivery"]["func"] = run_warehouse_delivery_script


def run_porder_balance_payment_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    porder_sn = _porder_sn(variables)
    if not porder_sn:
        return _finish_named(
            POORDER_BALANCE_PAYMENT_SCRIPT_NAME,
            {"script": POORDER_BALANCE_PAYMENT_SCRIPT_NAME, "started_at": datetime.now()},
            False,
            {"porder_sn": "", "order_sn": "", "reason": "请输入配送单号"},
        )

    log: Dict[str, Any] = {
        "script": POORDER_BALANCE_PAYMENT_SCRIPT_NAME,
        "mode": "porder_balance_payment",
        "started_at": datetime.now(),
        "porder_sn": porder_sn,
        "backend_porder": {},
        "order_list": {},
        "payment": {},
    }

    try:
        # Step 1: 可选执行后台配送单流程（配货、装箱、报价）
        base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
        timeout = _as_int(variables.get("timeout"), env.timeout or 25)
        if _as_bool(variables.get("run_backend_porder_flow"), False):
            log["mode"] = "porder_backend_then_balance_payment"
            backend_passed, backend_summary = _run_backend_porder_flow(base_url, timeout, variables, porder_sn, log)
            if not backend_passed:
                return _finish_named(
                    POORDER_BALANCE_PAYMENT_SCRIPT_NAME,
                    log,
                    False,
                    {"porder_sn": porder_sn, "order_sn": "", "reason": backend_summary.get("reason") or "配送单后台流程失败"},
                )
        else:
            log["backend_porder"] = {"skipped": True, "reason": "配送单已待支付，跳过后台流程"}

        # Step 2: 余额支付
        client, base_url, _, _ = _login_client_for_payment(env, variables, log)
        log["base_url"] = base_url
        amount = _load_porder_payment_amount(client, variables, log, porder_sn)

        fields: OrderedDict[str, Any] = OrderedDict()
        fields["porder_sn"] = porder_sn
        fields["discounts_id"] = str(variables.get("discounts_id") or "")
        fields["merge_pay"] = str(variables.get("merge_pay") or "0")
        _apply_extra_fields(fields, variables.get("balance_pay_fields"))
        payment_payload = _call_with_retry(
            "porder balance payment",
            lambda: client.post_form(_api_path(variables, "client_porder_balance_pay", "/client/porder.balancePayOrder"), fields),
        )
        log["payment"] = {**_payload_brief(payment_payload), "request": dict(fields)}
        summary = _porder_payment_summary("balance", porder_sn, amount, payment_payload)
        summary["backend_passed"] = True
        return _finish_named(POORDER_BALANCE_PAYMENT_SCRIPT_NAME, log, summary["payment_passed"] and summary["porder_matched"], summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            POORDER_BALANCE_PAYMENT_SCRIPT_NAME,
            log,
            False,
            {"porder_sn": porder_sn, "payment_type": "balance", "order_sn": "", "pay_amount": "0", "error": str(exc)},
        )


def run_porder_bank_payment_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    porder_sn = _porder_sn(variables)
    if not porder_sn:
        return _finish_named(
            POORDER_BANK_PAYMENT_SCRIPT_NAME,
            {"script": POORDER_BANK_PAYMENT_SCRIPT_NAME, "started_at": datetime.now()},
            False,
            {"porder_sn": "", "order_sn": "", "reason": "请输入配送单号"},
        )

    log: Dict[str, Any] = {
        "script": POORDER_BANK_PAYMENT_SCRIPT_NAME,
        "mode": "porder_bank_payment",
        "started_at": datetime.now(),
        "porder_sn": porder_sn,
        "backend_porder": {},
        "order_list": {},
        "payment": {},
        "finance": {},
    }

    try:
        # Step 1: 可选执行后台配送单流程（配货、装箱、报价）
        base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
        timeout = _as_int(variables.get("timeout"), env.timeout or 25)
        if _as_bool(variables.get("run_backend_porder_flow"), False):
            log["mode"] = "porder_backend_then_bank_payment"
            backend_passed, backend_summary = _run_backend_porder_flow(base_url, timeout, variables, porder_sn, log)
            if not backend_passed:
                return _finish_named(
                    POORDER_BANK_PAYMENT_SCRIPT_NAME,
                    log,
                    False,
                    {"porder_sn": porder_sn, "order_sn": "", "reason": backend_summary.get("reason") or "配送单后台流程失败"},
                )
        else:
            log["backend_porder"] = {"skipped": True, "reason": "配送单已待支付，跳过后台流程"}

        # Step 2: 银行支付
        client, base_url, timeout, _ = _login_client_for_payment(env, variables, log)
        log["base_url"] = base_url
        amount = _load_porder_payment_amount(client, variables, log, porder_sn)
        if not _positive_decimal(amount):
            return _finish_named(
                POORDER_BANK_PAYMENT_SCRIPT_NAME,
                log,
                False,
                {"porder_sn": porder_sn, "payment_type": "bank", "order_sn": "", "pay_amount": amount, "reason": "未获取到可用的配送单支付金额"},
            )

        now = datetime.now()
        fields: OrderedDict[str, Any] = OrderedDict()
        fields["porder_sn"] = porder_sn
        fields["pay_bank_method"] = str(variables.get("pay_bank_method") or "1")
        fields["pay_date"] = str(variables.get("pay_date") or now.strftime("%Y-%m-%d %H:%M:%S"))
        fields["pay_reach_date"] = _bank_pay_reach_date(variables, now)
        fields["pay_name"] = str(variables.get("pay_name") or "自动化测试")
        fields["pay_amount"] = amount
        fields["pay_remark"] = str(variables.get("pay_remark") or "自动化银行付款")
        fields["discounts_id"] = str(variables.get("discounts_id") or "")
        fields["merge_pay"] = str(variables.get("merge_pay") or "0")
        _apply_extra_fields(fields, variables.get("bank_pay_fields"))
        payment_payload = _call_with_retry(
            "porder bank payment",
            lambda: client.post_form(_api_path(variables, "client_porder_bank_pay", "/client/porder.bankPayOrder"), fields),
        )
        payment_ok = _api_success(payment_payload)
        payment_data = payment_payload.get("data") if isinstance(payment_payload.get("data"), dict) else {}
        serial_number = str(payment_data.get("serial_number") or variables.get("serial_number") or "")
        porder_matched = _porder_payload_matches(payment_payload, porder_sn)
        log["payment"] = {**_payload_brief(payment_payload), "request": dict(fields), "serial_number": serial_number, "porder_matched": porder_matched}

        # Step 3: 财务确认
        finance_confirm = _as_bool(variables.get("finance_confirm"), True)
        finance_ok = True
        if payment_ok and porder_matched and finance_confirm:
            if not serial_number:
                finance_ok = False
                log["finance"] = {"reason": "银行支付未返回流水号"}
            else:
                session = _admin_session_from(variables)
                login_payload, token = _admin_login(session, base_url, variables, timeout)
                log["finance"]["login"] = {
                    **_payload_brief(login_payload),
                    "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
                    "token_extracted": bool(token),
                }
                if not _api_success(login_payload) or not token:
                    finance_ok = False
                    log["finance"]["reason"] = "后台登录失败"
                else:
                    initial_delay = _as_float(variables.get("finance_confirm_initial_delay"), 2.0)
                    retry_delay = _as_float(variables.get("finance_confirm_delay"), 2.0)
                    retries = _as_int(variables.get("finance_confirm_retries"), 6)
                    if initial_delay > 0:
                        time.sleep(initial_delay)
                    attempts = []
                    list_payload: Dict[str, Any] = {}
                    confirm_payload: Dict[str, Any] = {}
                    selected_bill: Dict[str, Any] | None = None
                    for attempt in range(retries):
                        list_fields = _finance_unconfirm_fields(variables, serial_number, porder_sn)
                        list_payload = _post_admin_form(
                            session, base_url,
                            _api_path(variables, "admin_bill_unconfirm_list", "/bill.unConfirmList"),
                            list_fields, timeout,
                        )
                        rows = _finance_rows_from_payload(list_payload)
                        selected_bill = _select_finance_bill(rows, serial_number, porder_sn)
                        attempt_brief = {
                            **_payload_brief(list_payload),
                            "request": dict(list_fields),
                            "row_count": len(rows),
                            "selected_bill": _finance_bill_brief(selected_bill),
                            "serial_number": serial_number,
                            "attempt": attempt + 1,
                        }
                        attempts.append(attempt_brief)
                        if _api_success(list_payload) and selected_bill and selected_bill.get("id") not in (None, ""):
                            break
                        if attempt < retries - 1:
                            time.sleep(retry_delay)
                    log["finance"]["unconfirm_list_attempts"] = attempts
                    log["finance"]["unconfirm_list"] = attempts[-1] if attempts else {"serial_number": serial_number}
                    if _api_success(list_payload) and selected_bill and selected_bill.get("id") not in (None, ""):
                        confirm_payload = _post_admin_form(
                            session, base_url,
                            _api_path(variables, "admin_bill_confirm", "/bill.confirm"),
                            {"id": selected_bill.get("id")}, timeout,
                        )
                        finance_ok = _api_success(confirm_payload)
                        log["finance"]["confirm"] = {
                            **_payload_brief(confirm_payload),
                            "request": {"id": selected_bill.get("id")},
                            "selected_bill": _finance_bill_brief(selected_bill),
                        }
                    else:
                        finance_ok = False
                        log["finance"]["confirm"] = {"serial_number": serial_number, "selected_bill": _finance_bill_brief(selected_bill)}
                    if not finance_ok:
                        last_payload = confirm_payload or list_payload
                        last_msg = last_payload.get("msg") or last_payload.get("data") or "财务确认汇款失败"
                        log["finance"]["reason"] = f"财务确认汇款失败：{last_msg}"

        passed = payment_ok and porder_matched and finance_ok
        summary = _porder_payment_summary("bank", porder_sn, amount, payment_payload)
        summary["backend_passed"] = True
        summary["finance_passed"] = finance_ok
        if payment_ok and not porder_matched:
            summary["reason"] = "配送单银行付款接口返回单号与输入配送单号不一致"
        return _finish_named(POORDER_BANK_PAYMENT_SCRIPT_NAME, log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            POORDER_BANK_PAYMENT_SCRIPT_NAME,
            log,
            False,
            {"porder_sn": porder_sn, "payment_type": "bank", "order_sn": "", "pay_amount": "0", "error": str(exc)},
        )


BALANCE_INSUFFICIENT_MARKERS = [
    "\u4f59\u989d\u4e0d\u8db3",
    "\u8d26\u6237\u91d1\u989d",
    "\u53ef\u7528\u4f59\u989d",
    "\u4f59\u989d\u4e0d\u591f",
    "insufficient",
    "not enough",
]
FULL_FLOW_SHARED_KEYS = [
    "order_sn",
    "purchase_no",
    "purchase_ids",
    "grid_id",
    "grid_number",
    "order_detail_id",
    "order_detail_ids",
    "porder_sn",
    "porder_detail_id",
    "porder_detail_ids",
    "freight_id",
    "warehouse_sku_count",
    "actual_warehouse_sku_count",
    "selected_sku_ids",
    "total_send_num",
    "serial_number",
    "payment_type",
    "pay_amount",
]


def _summary_text(*parts: Any) -> str:
    return json.dumps(parts, ensure_ascii=False, default=str).lower()


def _looks_like_balance_insufficient(summary: Dict[str, Any], log_text: str = "") -> bool:
    text = _summary_text(summary, log_text)
    if any(marker.lower() in text for marker in BALANCE_INSUFFICIENT_MARKERS):
        return True
    return "\u4f59\u989d" in text and any(marker in text for marker in ["\u4e0d\u8db3", "\u4e0d\u591f", "\u4f4e\u4e8e"])


def _payment_with_bank_fallback(
    env: Env,
    variables: Dict[str, Any],
    *,
    porder: bool = False,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    balance_func = run_porder_balance_payment_script if porder else run_balance_payment_script
    bank_func = run_porder_bank_payment_script if porder else run_bank_payment_script
    mode_key = "porder_payment_mode" if porder else "order_payment_mode"
    payment_mode = str(variables.get(mode_key) or variables.get("payment_mode") or "balance_first").strip().lower()
    if payment_mode in {"bank", "bank_payment"}:
        bank_vars = dict(variables)
        bank_vars["finance_confirm"] = True
        bank_passed, bank_log, bank_report, bank_summary = bank_func(env, bank_vars)
        bank_summary = dict(bank_summary or {})
        bank_summary["attempted_payment_types"] = ["bank"]
        bank_summary["payment_mode"] = "bank"
        return bank_passed, bank_log, bank_report, bank_summary

    balance_passed, balance_log, balance_report, balance_summary = balance_func(env, variables)
    balance_summary = dict(balance_summary or {})
    balance_summary["attempted_payment_types"] = ["balance"]
    balance_summary["payment_mode"] = "balance_first"
    if balance_passed:
        return balance_passed, balance_log, balance_report, balance_summary
    if not _looks_like_balance_insufficient(balance_summary, balance_log):
        return balance_passed, balance_log, balance_report, balance_summary

    bank_vars = dict(variables)
    bank_vars["finance_confirm"] = True
    bank_passed, bank_log, bank_report, bank_summary = bank_func(env, bank_vars)
    bank_summary = dict(bank_summary or {})
    bank_summary.update(
        {
            "fallback_from_balance": True,
            "attempted_payment_types": ["balance", "bank"],
            "payment_mode": "balance_first",
            "balance_failure": balance_summary,
        }
    )
    return bank_passed, bank_log, bank_report, bank_summary


def _direct_box_int(value: Any, fallback: int = 1) -> int:
    try:
        number = int(Decimal(str(value)))
        return number if number > 0 else fallback
    except (InvalidOperation, TypeError, ValueError):
        return fallback


def _direct_box_text(value: Any, fallback: str) -> str:
    text = str(value if value not in (None, "") else fallback).strip()
    return text or fallback


def _direct_box_configs(variables: Dict[str, Any], total_num: int = 1) -> list[Dict[str, Any]]:
    raw_boxes = variables.get("boxes")
    if isinstance(raw_boxes, str):
        try:
            parsed = json.loads(raw_boxes)
        except (TypeError, ValueError):
            parsed = []
        raw_boxes = parsed
    requested_count = _direct_box_int(variables.get("box_count") or variables.get("direct_box_count"), 1)
    if isinstance(raw_boxes, list) and raw_boxes:
        requested_count = max(requested_count, len(raw_boxes))
    requested_count = max(1, requested_count)
    default = {
        "length": _direct_box_text(variables.get("box_length"), "10"),
        "width": _direct_box_text(variables.get("box_width"), "20"),
        "height": _direct_box_text(variables.get("box_height"), "30"),
        "weight": _direct_box_text(variables.get("box_weight"), "10"),
        "item_count": "",
    }
    result: list[Dict[str, Any]] = []
    source = raw_boxes if isinstance(raw_boxes, list) else []
    for index in range(requested_count):
        item = source[index] if index < len(source) and isinstance(source[index], dict) else {}
        result.append(
            {
                "length": _direct_box_text(item.get("length") or item.get("c") or item.get("box_length"), default["length"]),
                "width": _direct_box_text(item.get("width") or item.get("k") or item.get("box_width"), default["width"]),
                "height": _direct_box_text(item.get("height") or item.get("g") or item.get("box_height"), default["height"]),
                "weight": _direct_box_text(item.get("weight") or item.get("box_weight"), default["weight"]),
                "item_count": item.get("item_count") or item.get("num") or "",
            }
        )
    return result[: max(1, min(len(result), max(total_num, requested_count)))]


def _direct_box_rows(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    data = payload.get("data")
    candidates = data if isinstance(data, list) else data.get("data") if isinstance(data, dict) else []
    if isinstance(candidates, list):
        rows = [row for row in candidates if isinstance(row, dict)]
    if not rows:
        rows = [
            row
            for row in _nested_rows(payload)
            if isinstance(row, dict) and row.get("id") not in (None, "") and any(key in row for key in ["box_no", "order_sn", "attr", "weight"])
        ]
    return rows


def _direct_box_id(row: Dict[str, Any]) -> str:
    return str(row.get("id") or row.get("box_id") or "").strip()


def _direct_box_sort_key(row: Dict[str, Any]) -> tuple[int, int]:
    return (_direct_box_int(row.get("box_no"), 999999), _direct_box_int(row.get("id"), 999999))


def _direct_box_order_sn(rows: list[Dict[str, Any]], items: list[Dict[str, Any]], variables: Dict[str, Any]) -> str:
    for value in [variables.get("order_sn"), variables.get("last_order_sn")]:
        if value not in (None, ""):
            return str(value).strip()
    for item in items:
        for key in ["order_sn", "_order_sn"]:
            if item.get(key) not in (None, ""):
                return str(item.get(key)).strip()
    for row in rows:
        if row.get("order_sn") not in (None, ""):
            return str(row.get("order_sn")).strip()
    return ""


def _direct_box_units(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    units: list[Dict[str, Any]] = []
    for item in items:
        order_purchase_id = _order_purchase_id(item)
        if order_purchase_id in (None, ""):
            continue
        units.append({"order_purchase_id": order_purchase_id, "num": _direct_box_int(_item_up_num(item), 1)})
    return units


def _direct_box_counts(total_num: int, configs: list[Dict[str, Any]], box_count: int) -> list[int]:
    box_count = max(1, min(box_count, total_num))
    configured: list[int] = []
    has_configured = False
    for index in range(box_count):
        count_value = configs[index].get("item_count") if index < len(configs) else ""
        if count_value not in (None, ""):
            has_configured = True
        configured.append(_direct_box_int(count_value, 1))
    if has_configured:
        counts = [max(1, value) for value in configured]
        while sum(counts) > total_num:
            changed = False
            for index in range(len(counts) - 1, -1, -1):
                if counts[index] > 1 and sum(counts) > total_num:
                    counts[index] -= 1
                    changed = True
            if not changed:
                break
        if sum(counts) < total_num:
            counts[-1] += total_num - sum(counts)
        return counts
    base = total_num // box_count
    remainder = total_num % box_count
    counts = [base for _ in range(box_count)]
    counts[-1] += remainder
    return [max(1, count) for count in counts]


def _direct_box_allocations(units: list[Dict[str, Any]], counts: list[int]) -> list[list[Dict[str, Any]]]:
    remaining = [{"order_purchase_id": item["order_purchase_id"], "num": _direct_box_int(item.get("num"), 1)} for item in units]
    cursor = 0
    result: list[list[Dict[str, Any]]] = []
    for count in counts:
        need = count
        allocation: list[Dict[str, Any]] = []
        while need > 0 and cursor < len(remaining):
            current = remaining[cursor]
            take = min(need, current["num"])
            if take > 0:
                allocation.append({"num": take, "order_purchase_id": current["order_purchase_id"]})
                current["num"] -= take
                need -= take
            if current["num"] <= 0:
                cursor += 1
        result.append(allocation)
    return result


def _direct_box_prepare_to_checking(env: Env, variables: Dict[str, Any], log: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
    order_sn = str(variables.get("order_sn") or variables.get("last_order_sn") or "").strip()
    purchase_no = str(variables.get("purchase_no") or "").strip()
    if not order_sn and purchase_no:
        return True, {"order_sn": "", "purchase_no": purchase_no, "preflow": "purchase_no_only"}

    working = dict(variables)
    if not order_sn:
        quote_vars = dict(working)
        quote_vars.pop("order_sn", None)
        quote_vars.pop("last_order_sn", None)
        quote_vars["skip_create_order"] = False
        quote_vars["backend_only"] = False
        quote_vars["submit_order"] = True
        quote_vars["run_backend_flow"] = True
        quote_passed, _, quote_report, quote_summary = run_order_quote_script(env, quote_vars)
        log["steps"].append({"name": "pre_order_quote", "passed": quote_passed, "summary": quote_summary, "report_path": quote_report})
        order_sn = str((quote_summary or {}).get("order_sn") or "").strip()
        if not quote_passed or not order_sn:
            return False, {"reason": "\u8ba2\u5355\u62a5\u4ef7\u672a\u751f\u6210\u8ba2\u5355\u53f7", "order_sn": order_sn}

        pay_vars = dict(working)
        pay_vars["order_sn"] = order_sn
        pay_passed, _, pay_report, pay_summary = _payment_with_bank_fallback(env, pay_vars, porder=False)
        log["steps"].append({"name": "pre_order_payment", "passed": pay_passed, "summary": pay_summary, "report_path": pay_report})
        if not pay_passed:
            return False, {"reason": str((pay_summary or {}).get("reason") or "\u8ba2\u5355\u652f\u4ed8\u5931\u8d25"), "order_sn": order_sn}
        working["order_sn"] = order_sn

    shelf_vars = dict(working)
    shelf_vars["order_sn"] = order_sn
    shelf_vars["purchase_no"] = purchase_no or str(variables.get("purchase_no") or datetime.now().strftime("%Y%m%d%H%M%S"))
    shelf_vars["link_quote_balance_before_shelf"] = False
    shelf_vars["auto_quote_and_pay"] = False
    shelf_vars["stop_after_node"] = "checking_started"
    shelf_passed, _, shelf_report, shelf_summary = run_purchase_to_shelf_script(env, shelf_vars)
    log["steps"].append({"name": "pre_purchase_to_checking", "passed": shelf_passed, "summary": shelf_summary, "report_path": shelf_report})
    if not shelf_passed:
        return False, {
            "reason": str((shelf_summary or {}).get("reason") or (shelf_summary or {}).get("error") or "\u5f00\u59cb\u6838\u67e5\u524d\u7f6e\u6d41\u7a0b\u5931\u8d25"),
            "order_sn": order_sn,
            "purchase_no": shelf_vars["purchase_no"],
        }
    return True, dict(shelf_summary or {})


def run_direct_box_to_shelf_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (variables.get("backend_base_url") or env.base_url or bulk_cart.BASE_URL).rstrip("/")
    log: Dict[str, Any] = {
        "script": DIRECT_BOX_TO_SHELF_SCRIPT_NAME,
        "mode": "direct_box_to_shelf",
        "base_url": base_url,
        "started_at": datetime.now(),
        "steps": [],
    }

    try:
        pre_passed, pre_summary = _direct_box_prepare_to_checking(env, variables, log)
        if not pre_passed:
            return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, pre_summary)

        purchase_no = str(pre_summary.get("purchase_no") or variables.get("purchase_no") or "").strip()
        if not purchase_no:
            return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"reason": "\u672a\u83b7\u53d6\u5230\u4ea4\u6613\u53f7\uff0c\u65e0\u6cd5\u76f4\u63a5\u88c5\u7bb1"})

        session = _admin_session_from(variables)
        login_payload, token = _admin_login(session, base_url, variables, timeout)
        log["login"] = {
            **_payload_brief(login_payload),
            "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
            "token_extracted": bool(token),
        }
        if not _api_success(login_payload) or not token:
            return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"purchase_no": purchase_no, "reason": "\u540e\u53f0\u767b\u5f55\u5931\u8d25"})

        purchase_ids = _unique_values(pre_summary.get("purchase_ids") if isinstance(pre_summary.get("purchase_ids"), list) else [])
        preview_fields: Dict[str, Any] = {"purchase_no": purchase_no, "express_no": str(variables.get("express_no") or "")}
        if purchase_ids:
            preview_fields["order_purchase_id_set"] = purchase_ids
        preview_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_follow_up_preview", "/follow.upPreview"),
            preview_fields,
            timeout,
        )
        preview_rows = _preview_rows_from_payload(preview_payload)
        preview_items = _preview_items(preview_rows)
        if not purchase_ids:
            purchase_ids = _unique_values([_order_purchase_id(item) for item in preview_items])
        _step(log, "direct_follow_up_preview", preview_payload, preview_fields, {"item_count": len(preview_items), "purchase_ids": purchase_ids})
        if not _api_success(preview_payload) or not preview_items:
            return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"purchase_no": purchase_no, "reason": "\u672a\u83b7\u53d6\u5230\u53ef\u76f4\u63a5\u88c5\u7bb1\u7684\u6838\u67e5\u5546\u54c1"})

        units = _direct_box_units(preview_items)
        total_num = sum(item["num"] for item in units)
        if total_num <= 0:
            return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"purchase_no": purchase_no, "reason": "\u53ef\u88c5\u7bb1\u5546\u54c1\u6570\u91cf\u4e0d\u8db3"})

        order_sn = _direct_box_order_sn(preview_rows, preview_items, {**variables, **pre_summary})
        if not order_sn:
            return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"purchase_no": purchase_no, "reason": "\u672a\u83b7\u53d6\u5230\u8ba2\u5355\u53f7\uff0c\u65e0\u6cd5\u521b\u5efa\u7bb1\u5b50"})

        configs = _direct_box_configs(variables, total_num)
        requested_box_count = len(configs)
        before_box_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_box_list", "/box.boxList"),
            {"status": 1, "order_sn": order_sn},
            timeout,
        )
        before_boxes = _direct_box_rows(before_box_payload)
        before_ids = {_direct_box_id(row) for row in before_boxes}
        _step(log, "box_list_before_add", before_box_payload, {"status": 1, "order_sn": order_sn}, {"box_count": len(before_boxes)})

        add_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_box_add_batch", "/box.addBoxBatch"),
            {"order_sn": order_sn, "num": requested_box_count},
            timeout,
        )
        _step(log, "box_add_batch", add_payload, {"order_sn": order_sn, "num": requested_box_count})
        if not _api_success(add_payload):
            return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u6dfb\u52a0\u7bb1\u5b50\u5931\u8d25"})

        after_add_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_box_list", "/box.boxList"),
            {"status": 1, "order_sn": order_sn},
            timeout,
        )
        after_add_boxes = sorted(_direct_box_rows(after_add_payload), key=_direct_box_sort_key)
        new_boxes = [row for row in after_add_boxes if _direct_box_id(row) and _direct_box_id(row) not in before_ids]
        if len(new_boxes) < requested_box_count:
            new_boxes = after_add_boxes[-requested_box_count:]
        new_boxes = sorted(new_boxes, key=_direct_box_sort_key)
        _step(log, "box_list_after_add", after_add_payload, {"status": 1, "order_sn": order_sn}, {"new_box_ids": [_direct_box_id(row) for row in new_boxes]})
        if not new_boxes:
            return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u672a\u83b7\u53d6\u5230\u672c\u6b21\u65b0\u589e\u7bb1\u5b50ID"})

        keep_count = min(len(new_boxes), total_num)
        keep_boxes = new_boxes[:keep_count]
        delete_boxes = new_boxes[keep_count:]
        deleted_box_ids: list[str] = []
        if delete_boxes:
            delete_ids = [_direct_box_id(row) for row in delete_boxes if _direct_box_id(row)]
            delete_payload = _post_admin_urlencoded(
                session,
                base_url,
                _api_path(variables, "admin_box_delete", "/box.deleteBox"),
                {"ids": delete_ids},
                timeout,
            )
            _step(log, "box_delete_extra", delete_payload, {"ids": delete_ids})
            if not _api_success(delete_payload):
                return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u5220\u9664\u591a\u4f59\u7a7a\u7bb1\u5931\u8d25", "delete_box_ids": delete_ids})
            deleted_box_ids = delete_ids

        kept_box_ids = [_direct_box_id(row) for row in keep_boxes if _direct_box_id(row)]
        if not kept_box_ids:
            return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u65e0\u53ef\u88c5\u8d27\u7bb1\u5b50"})

        for index, box_id in enumerate(kept_box_ids):
            config = configs[index] if index < len(configs) else configs[-1]
            attr_fields = {
                "ids": [box_id],
                "attr": f"{config['length']}*{config['width']}*{config['height']}",
                "c": config["length"],
                "k": config["width"],
                "g": config["height"],
            }
            attr_payload = _post_admin_urlencoded(
                session,
                base_url,
                _api_path(variables, "admin_box_update_attr", "/box.updateBoxAttr"),
                attr_fields,
                timeout,
            )
            _step(log, "box_update_attr", attr_payload, attr_fields)
            if not _api_success(attr_payload):
                return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u4fee\u6539\u7bb1\u89c4\u5931\u8d25", "box_id": box_id})

            weight_fields = {"ids": [box_id], "weight": config["weight"]}
            weight_payload = _post_admin_urlencoded(
                session,
                base_url,
                _api_path(variables, "admin_box_update_weight", "/box.updateBoxWeight"),
                weight_fields,
                timeout,
            )
            _step(log, "box_update_weight", weight_payload, weight_fields)
            if not _api_success(weight_payload):
                return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u4fee\u6539\u91cd\u91cf\u5931\u8d25", "box_id": box_id})

        counts = _direct_box_counts(total_num, configs, len(kept_box_ids))
        allocations = _direct_box_allocations(units, counts)
        if any(not allocation for allocation in allocations):
            return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u5546\u54c1\u6570\u91cf\u4e0d\u8db3\uff0c\u65e0\u6cd5\u4fdd\u8bc1\u6bcf\u4e2a\u7bb1\u5b50\u81f3\u5c111\u4ef6\u5546\u54c1"})

        for box_id, allocation in zip(kept_box_ids, allocations):
            into_payload = _post_admin_urlencoded(
                session,
                base_url,
                _api_path(variables, "admin_box_into_box", "/box.intoBox"),
                {"ids": [box_id], "list": allocation},
                timeout,
            )
            _step(log, "box_into_box", into_payload, {"ids": [box_id], "list": allocation})
            if not _api_success(into_payload):
                return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u8d27\u7269\u88c5\u7bb1\u5931\u8d25", "box_id": box_id})

        grid_fields = {
            "shelf_type_set": variables.get("shelf_type_set") or [1, 3],
            "user_id": str(variables.get("warehouse_user_id") or ""),
            "order_purchase_id": variables.get("grid_order_purchase_id") or "",
        }
        grid_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_wms_grid_preview", "/wms.wmsGridPreview"),
            grid_fields,
            timeout,
        )
        selected_grid = _select_grid_from_payload(grid_payload, variables)
        _step(
            log,
            "wms_grid_preview_for_box",
            grid_payload,
            grid_fields,
            {"selected_grid": {"id": (selected_grid or {}).get("id"), "grid_number": (selected_grid or {}).get("grid_number")}},
        )
        if not _api_success(grid_payload) or not selected_grid:
            return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u672a\u627e\u5230\u53ef\u7528\u4e0a\u67b6\u5e93\u4f4d"})

        complete_fields = {"ids": kept_box_ids, "grid_id": selected_grid.get("id"), "grid_number": selected_grid.get("grid_number")}
        complete_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_box_to_complete", "/box.toComplete"),
            complete_fields,
            timeout,
        )
        _step(log, "box_to_complete", complete_payload, complete_fields)
        if not _api_success(complete_payload):
            fallback_results = []
            all_ok = True
            for box_id in kept_box_ids:
                single_fields = {"ids": [box_id], "grid_id": selected_grid.get("id"), "grid_number": selected_grid.get("grid_number")}
                single_payload = _post_admin_urlencoded(
                    session,
                    base_url,
                    _api_path(variables, "admin_box_to_complete", "/box.toComplete"),
                    single_fields,
                    timeout,
                )
                fallback_results.append({"box_id": box_id, **_payload_brief(single_payload)})
                if not _api_success(single_payload):
                    all_ok = False
            log["steps"].append({"name": "box_to_complete_fallback", "results": fallback_results, "passed": all_ok})
            if not all_ok:
                return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"order_sn": order_sn, "purchase_no": purchase_no, "reason": "\u76f4\u63a5\u88c5\u7bb1\u4e0a\u67b6\u5931\u8d25", "box_ids": kept_box_ids})

        final_box_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_box_list", "/box.boxList"),
            {"status": 1, "order_sn": order_sn},
            timeout,
        )
        final_boxes = _direct_box_rows(final_box_payload)
        remaining_ids = {_direct_box_id(row) for row in final_boxes}
        unfinished_ids = [box_id for box_id in kept_box_ids if box_id in remaining_ids]
        _step(log, "box_list_after_complete", final_box_payload, {"status": 1, "order_sn": order_sn}, {"unfinished_box_ids": unfinished_ids})
        passed = not unfinished_ids
        summary = {
            "order_sn": order_sn,
            "purchase_no": purchase_no,
            "purchase_ids": purchase_ids,
            "total_box_item_num": total_num,
            "requested_box_count": requested_box_count,
            "kept_box_count": len(kept_box_ids),
            "deleted_box_ids": deleted_box_ids,
            "box_ids": kept_box_ids,
            "box_item_counts": counts,
            "box_allocations": [{"box_id": box_id, "list": allocation} for box_id, allocation in zip(kept_box_ids, allocations)],
            "grid_id": selected_grid.get("id"),
            "grid_number": selected_grid.get("grid_number"),
            "direct_box_passed": passed,
        }
        if not passed:
            summary["reason"] = "\u4ecd\u6709\u7bb1\u5b50\u505c\u7559\u5728\u5f85\u88c5\u7bb1\u5217\u8868"
            summary["unfinished_box_ids"] = unfinished_ids
        return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(DIRECT_BOX_TO_SHELF_SCRIPT_NAME, log, False, {"error": str(exc), "reason": str(exc)})


SCRIPT_REGISTRY["direct_box_to_shelf"]["func"] = run_direct_box_to_shelf_script


def _full_flow_update_shared(shared: Dict[str, Any], summary: Dict[str, Any]) -> None:
    for key in FULL_FLOW_SHARED_KEYS:
        value = summary.get(key)
        if value not in (None, ""):
            shared[key] = value


def _full_flow_record_step(
    log: Dict[str, Any],
    node: str,
    script_name: str,
    passed: bool,
    summary: Dict[str, Any],
    report_path: str = "",
) -> None:
    current_node = str(summary.get("current_node") or summary.get("stopped_after_node") or node)
    log["steps"].append(
        {
            "node": current_node,
            "node_label": FULL_FLOW_NODE_LABELS.get(current_node, current_node),
            "script": script_name,
            "passed": passed,
            "paused": bool(summary.get("paused")),
            "duration_ms": summary.get("duration_ms"),
            "summary": summary,
            "report_path": report_path,
        }
    )
    _full_flow_update_shared(log["shared_data"], summary)


def _full_flow_node_results(current_node: str, passed: bool, paused: bool) -> list[Dict[str, Any]]:
    if current_node in FULL_FLOW_NODE_SEQUENCE:
        reached_index = FULL_FLOW_NODE_SEQUENCE.index(current_node)
    elif passed:
        reached_index = FULL_FLOW_NODE_SEQUENCE.index(FULL_FLOW_COMPLETE_NODE)
    else:
        reached_index = -1
    results: list[Dict[str, Any]] = []
    for index, node in enumerate(FULL_FLOW_NODE_SEQUENCE):
        if reached_index < 0 or index > reached_index:
            status_text = "pending"
            node_passed: bool | None = None
        elif index < reached_index:
            status_text = "completed"
            node_passed = True
        elif paused:
            status_text = "paused"
            node_passed = True
        elif passed:
            status_text = "completed"
            node_passed = True
        else:
            status_text = "failed"
            node_passed = False
        results.append(
            {
                "node": node,
                "node_label": FULL_FLOW_NODE_LABELS.get(node, node),
                "status": status_text,
                "passed": node_passed,
            }
        )
    return results


def _full_flow_finish(
    log: Dict[str, Any],
    passed: bool,
    current_node: str,
    *,
    reason: str = "",
    paused: bool = False,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    summary: Dict[str, Any] = {
        "passed": passed,
        "paused": paused,
        "current_node": current_node,
        "node_label": FULL_FLOW_NODE_LABELS.get(current_node, current_node),
        "stop_after_node": log.get("stop_after_node") or FULL_FLOW_COMPLETE_NODE,
        "total_steps": len(log.get("steps", [])),
        "success_steps": sum(1 for item in log.get("steps", []) if item.get("passed")),
        "node_results": _full_flow_node_results(current_node, passed, paused),
        "steps": [
            {
                "node": item.get("node"),
                "node_label": item.get("node_label"),
                "script": item.get("script"),
                "passed": item.get("passed"),
                "paused": item.get("paused"),
                "duration_ms": item.get("duration_ms"),
            }
            for item in log.get("steps", [])
        ],
        "step_timings": [
            {
                "node": item.get("node"),
                "script": item.get("script"),
                "duration_ms": item.get("duration_ms"),
            }
            for item in log.get("steps", [])
            if item.get("duration_ms") is not None
        ],
    }
    summary.update(log.get("shared_data") or {})
    if paused:
        summary["stopped_after_node"] = current_node
    if reason:
        summary["reason"] = reason
    return _finish_named(str(log.get("script") or FULL_FLOW_SCRIPT_NAME), log, passed, summary)


def _resume_record_skipped(log: Dict[str, Any], nodes: list[str], reason: str) -> None:
    skipped = log.setdefault("skipped_nodes", [])
    for node in nodes:
        skipped.append({"node": node, "node_label": FULL_FLOW_NODE_LABELS.get(node, node), "reason": reason})


def _resume_flow_finish(
    log: Dict[str, Any],
    passed: bool,
    current_node: str,
    *,
    reason: str = "",
    paused: bool = False,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    summary: Dict[str, Any] = {
        "passed": passed,
        "paused": paused,
        "current_node": current_node,
        "node_label": FULL_FLOW_NODE_LABELS.get(current_node, current_node),
        "stop_after_node": log.get("stop_after_node") or "porder_offered",
        "detected_start_node": log.get("detected_start_node") or "",
        "total_steps": len(log.get("steps", [])),
        "success_steps": sum(1 for item in log.get("steps", []) if item.get("passed")),
        "node_results": _full_flow_node_results(current_node, passed, paused),
        "steps": [
            {
                "node": item.get("node"),
                "node_label": item.get("node_label"),
                "script": item.get("script"),
                "passed": item.get("passed"),
                "paused": item.get("paused"),
                "duration_ms": item.get("duration_ms"),
            }
            for item in log.get("steps", [])
        ],
        "step_timings": [
            {
                "node": item.get("node"),
                "script": item.get("script"),
                "duration_ms": item.get("duration_ms"),
            }
            for item in log.get("steps", [])
            if item.get("duration_ms") is not None
        ],
        "skipped_nodes": log.get("skipped_nodes", []),
    }
    summary.update(log.get("shared_data") or {})
    if paused:
        summary["stopped_after_node"] = current_node
    if reason:
        summary["reason"] = reason
    script_name = str(log.get("script") or RESUME_ORDER_FLOW_SCRIPT_NAME)
    return _finish_named(script_name, log, passed, summary)


def _full_flow_stop_reached(variables: Dict[str, Any], node: str) -> bool:
    return _checkpoint_requested(variables, node)


def _full_flow_prepare_warehouse_counts(variables: Dict[str, Any]) -> Dict[str, Any]:
    before = {
        "target_shops": variables.get("target_shops"),
        "per_shop": variables.get("per_shop"),
        "order_shop_count": variables.get("order_shop_count"),
        "order_per_shop": variables.get("order_per_shop"),
        "order_item_count": variables.get("order_item_count"),
        "warehouse_sku_count": variables.get("warehouse_sku_count"),
    }
    warehouse_sku_count = max(1, _as_int(variables.get("warehouse_sku_count") or variables.get("porder_sku_count") or variables.get("sku_count"), 1))
    order_shop_count = _as_int(variables.get("order_shop_count"), 1)
    order_per_shop = _as_int(variables.get("order_per_shop") or variables.get("order_item_count"), 2)
    if order_shop_count * order_per_shop < warehouse_sku_count:
        order_per_shop = max(order_per_shop, (warehouse_sku_count + order_shop_count - 1) // order_shop_count)
    target_shops = max(_as_int(variables.get("target_shops") or variables.get("shop_count"), order_shop_count), order_shop_count)
    per_shop = max(_as_int(variables.get("per_shop"), order_per_shop), order_per_shop)

    variables["warehouse_sku_count"] = warehouse_sku_count
    variables["order_shop_count"] = order_shop_count
    variables["order_per_shop"] = order_per_shop
    variables["order_item_count"] = order_per_shop
    variables["target_shops"] = target_shops
    variables["per_shop"] = per_shop

    after = {
        "target_shops": target_shops,
        "per_shop": per_shop,
        "order_shop_count": order_shop_count,
        "order_per_shop": order_per_shop,
        "order_item_count": order_per_shop,
        "warehouse_sku_count": warehouse_sku_count,
    }
    changed = {key: {"before": before.get(key), "after": value} for key, value in after.items() if str(before.get(key)) != str(value)}
    return changed


def run_full_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    variables["_runtime"] = variables.get("_runtime") if isinstance(variables.get("_runtime"), DataScriptRuntime) else DataScriptRuntime()
    variables.setdefault("sleep", 0)
    variables.setdefault("cart_verify_mode", "final")
    variables.setdefault("cart_edit_workers", 4)
    variables.setdefault("auto_fill_cart_on_shortage", True)
    variables.setdefault("purchase_transition_delay", 0)
    variables.setdefault("inspection_transition_delay", 0)
    variables.setdefault("after_box_submit_delay", 0.2)
    variables.setdefault("after_complete_box_delay", 0.2)
    resume_porder_sn = str(variables.get("porder_sn") or "").strip()
    resume_order_sn = str(variables.get("order_sn") or variables.get("last_order_sn") or "").strip()
    if resume_porder_sn:
        variables["porder_sn"] = resume_porder_sn
        return run_resume_porder_flow_script(env, variables)
    if resume_order_sn:
        variables["order_sn"] = resume_order_sn
        return run_resume_order_flow_script(env, variables)

    input_adjustments = _full_flow_prepare_warehouse_counts(variables)
    stop_after = _stop_after_node(variables) or FULL_FLOW_COMPLETE_NODE
    variables["stop_after_node"] = stop_after
    report_name = str(variables.get("_full_flow_report_name") or FULL_FLOW_SCRIPT_NAME).strip() or FULL_FLOW_SCRIPT_NAME
    log: Dict[str, Any] = {
        "script": report_name,
        "mode": "full_flow",
        "started_at": datetime.now(),
        "stop_after_node": stop_after,
        "input_adjustments": input_adjustments,
        "steps": [],
        "shared_data": {},
    }

    try:
        if _full_flow_stop_reached(variables, "shopping_cart"):
            cart_passed, cart_log, cart_report, cart_summary = run_shopping_cart_script(env, variables)
            cart_summary = dict(cart_summary or {})
            _full_flow_record_step(log, "shopping_cart", SCRIPT_NAME, cart_passed, cart_summary, cart_report)
            if not cart_passed:
                return _full_flow_finish(log, False, "shopping_cart", reason=str(cart_summary.get("reason") or cart_summary.get("error") or "\u5546\u54c1\u52a0\u8d2d\u5931\u8d25"))
            return _full_flow_finish(log, True, "shopping_cart", paused=True)

        log["cart_autofill"] = {
            "mode": "on_shortage",
            "skipped_initial_cart": True,
            "triggered": False,
        }

        def run_quote_attempt(retry_after_autofill: bool = False) -> tuple[bool, str, str, Dict[str, Any]]:
            quote_vars = dict(variables)
            quote_vars.pop("order_sn", None)
            quote_vars.pop("last_order_sn", None)
            quote_vars["skip_create_order"] = False
            quote_vars["backend_only"] = False
            quote_vars["submit_order"] = True
            quote_vars["run_backend_flow"] = True
            if retry_after_autofill:
                quote_vars["auto_fill_cart_on_shortage"] = False
            return run_order_quote_script(env, quote_vars)

        quote_passed, quote_log, quote_report, quote_summary = run_quote_attempt()
        quote_summary = dict(quote_summary or {})
        if (
            not quote_passed
            and quote_summary.get("reason_code") == "cart_items_shortage"
            and _as_bool(variables.get("auto_fill_cart_on_shortage"), True)
        ):
            shortage_before = {
                key: quote_summary.get(key)
                for key in [
                    "selected_count",
                    "expected_count",
                    "shortage_count",
                    "expected_shop_count",
                    "expected_per_shop",
                    "available_shop_count",
                    "ready_shop_count",
                    "selected_shop_count",
                ]
                if key in quote_summary
            }
            log["cart_autofill"].update(
                {
                    "triggered": True,
                    "reason_code": "cart_items_shortage",
                    "shortage_before": shortage_before,
                    "initial_quote_report_path": quote_report,
                }
            )
            cart_vars = dict(variables)
            cart_vars.pop("order_sn", None)
            cart_vars.pop("last_order_sn", None)
            cart_passed, cart_log, cart_report, cart_summary = run_shopping_cart_script(env, cart_vars)
            cart_summary = dict(cart_summary or {})
            log["cart_autofill"]["cart_summary"] = {
                "passed": cart_passed,
                "target_shops": cart_summary.get("target_shops"),
                "per_shop": cart_summary.get("per_shop"),
                "added_total": cart_summary.get("added_total"),
                "reason": cart_summary.get("reason") or cart_summary.get("error"),
                "duration_ms": cart_summary.get("duration_ms"),
            }
            _full_flow_record_step(log, "shopping_cart", SCRIPT_NAME, cart_passed, cart_summary, cart_report)
            if not cart_passed:
                return _full_flow_finish(log, False, "shopping_cart", reason=str(cart_summary.get("reason") or cart_summary.get("error") or "\u5546\u54c1\u52a0\u8d2d\u5931\u8d25"))
            quote_passed, quote_log, quote_report, quote_summary = run_quote_attempt(retry_after_autofill=True)
            quote_summary = dict(quote_summary or {})
            log["cart_autofill"]["retry_quote_report_path"] = quote_report
        elif not quote_passed:
            log["cart_autofill"]["reason"] = str(quote_summary.get("reason") or quote_summary.get("error") or "")

        _full_flow_record_step(log, "order_offered", ORDER_SCRIPT_NAME, quote_passed, quote_summary, quote_report)
        if not quote_passed:
            return _full_flow_finish(log, False, str(quote_summary.get("current_node") or "order_offered"), reason=str(quote_summary.get("reason") or quote_summary.get("error") or "\u8ba2\u5355\u62a5\u4ef7\u5931\u8d25"))
        if _is_paused(quote_summary):
            return _full_flow_finish(log, True, str(quote_summary.get("current_node") or "order_offered"), paused=True)

        order_sn = str(quote_summary.get("order_sn") or "").strip()
        if not order_sn:
            return _full_flow_finish(log, False, "order_offered", reason="\u8ba2\u5355\u62a5\u4ef7\u672a\u8fd4\u56de\u8ba2\u5355\u53f7")
        variables["order_sn"] = order_sn

        pay_vars = dict(variables)
        pay_vars["order_sn"] = order_sn
        pay_passed, pay_log, pay_report, pay_summary = _payment_with_bank_fallback(env, pay_vars, porder=False)
        _full_flow_record_step(log, "order_paid", pay_summary.get("payment_type") == "bank" and BANK_PAYMENT_SCRIPT_NAME or BALANCE_PAYMENT_SCRIPT_NAME, pay_passed, pay_summary, pay_report)
        if not pay_passed:
            return _full_flow_finish(log, False, "order_paid", reason=str(pay_summary.get("reason") or pay_summary.get("error") or "\u8ba2\u5355\u652f\u4ed8\u5931\u8d25"))
        if _full_flow_stop_reached(variables, "order_paid"):
            return _full_flow_finish(log, True, "order_paid", paused=True)

        shelf_vars = dict(variables)
        shelf_vars["order_sn"] = order_sn
        shelf_vars["purchase_no"] = str(variables.get("purchase_no") or datetime.now().strftime("%Y%m%d%H%M%S"))
        shelf_vars["link_quote_balance_before_shelf"] = False
        shelf_vars["auto_quote_and_pay"] = False
        shelf_passed, shelf_log, shelf_report, shelf_summary = run_purchase_to_shelf_script(env, shelf_vars)
        _full_flow_record_step(log, "shelf_stored", PURCHASE_TO_SHELF_SCRIPT_NAME, shelf_passed, shelf_summary, shelf_report)
        if not shelf_passed:
            return _full_flow_finish(log, False, str(shelf_summary.get("current_node") or "shelf_stored"), reason=str(shelf_summary.get("reason") or shelf_summary.get("error") or "\u5f85\u62cd\u4e0b\u5230\u4e0a\u67b6\u5931\u8d25"))
        if _is_paused(shelf_summary):
            return _full_flow_finish(log, True, str(shelf_summary.get("current_node") or "shelf_stored"), paused=True)

        delivery_vars = dict(variables)
        delivery_vars.update(log["shared_data"])
        delivery_vars["run_backend_delivery_flow"] = True
        delivery_vars.setdefault("warehouse_fill_scope", "current_order_then_history")
        delivery_vars.setdefault("require_warehouse_sku_count", True)
        delivery_vars.setdefault("warehouse_fill_retries", 3)
        delivery_vars.setdefault("warehouse_fill_retry_delay", 1)
        delivery_vars.pop("porder_sn", None)
        delivery_passed, delivery_log, delivery_report, delivery_summary = run_warehouse_delivery_script(env, delivery_vars)
        _full_flow_record_step(log, "porder_offered", WAREHOUSE_DELIVERY_SCRIPT_NAME, delivery_passed, delivery_summary, delivery_report)
        if not delivery_passed:
            return _full_flow_finish(log, False, str(delivery_summary.get("current_node") or "porder_offered"), reason=str(delivery_summary.get("reason") or delivery_summary.get("error") or "\u914d\u9001\u5355\u6d41\u8f6c\u5931\u8d25"))
        if _is_paused(delivery_summary):
            return _full_flow_finish(log, True, str(delivery_summary.get("current_node") or "porder_offered"), paused=True)

        porder_sn = str(delivery_summary.get("porder_sn") or log["shared_data"].get("porder_sn") or "").strip()
        if not porder_sn:
            return _full_flow_finish(log, False, "porder_offered", reason="\u914d\u9001\u5355\u6d41\u8f6c\u672a\u8fd4\u56de\u914d\u9001\u5355\u53f7")
        variables["porder_sn"] = porder_sn

        porder_pay_vars = dict(variables)
        porder_pay_vars["porder_sn"] = porder_sn
        porder_pay_vars["run_backend_porder_flow"] = False
        porder_pay_passed, porder_pay_log, porder_pay_report, porder_pay_summary = _payment_with_bank_fallback(env, porder_pay_vars, porder=True)
        _full_flow_record_step(
            log,
            "porder_paid",
            porder_pay_summary.get("payment_type") == "bank" and POORDER_BANK_PAYMENT_SCRIPT_NAME or POORDER_BALANCE_PAYMENT_SCRIPT_NAME,
            porder_pay_passed,
            porder_pay_summary,
            porder_pay_report,
        )
        if not porder_pay_passed:
            return _full_flow_finish(log, False, "porder_paid", reason=str(porder_pay_summary.get("reason") or porder_pay_summary.get("error") or "\u914d\u9001\u5355\u652f\u4ed8\u5931\u8d25"))
        if _full_flow_stop_reached(variables, "porder_paid"):
            return _full_flow_finish(log, True, "porder_paid", paused=True)

        return _full_flow_finish(log, True, FULL_FLOW_COMPLETE_NODE)
    except Exception as exc:
        log["error"] = str(exc)
        return _full_flow_finish(log, False, str(log["steps"][-1]["node"] if log["steps"] else "full_flow"), reason=str(exc))


def run_resume_order_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    variables["_runtime"] = variables.get("_runtime") if isinstance(variables.get("_runtime"), DataScriptRuntime) else DataScriptRuntime()
    variables.setdefault("sleep", 0)
    variables.setdefault("purchase_transition_delay", 0)
    variables.setdefault("inspection_transition_delay", 0)
    variables.setdefault("after_box_submit_delay", 0.2)
    variables.setdefault("after_complete_box_delay", 0.2)
    input_adjustments = _full_flow_prepare_warehouse_counts(variables)
    stop_after = _stop_after_node(variables) or "porder_offered"
    variables["stop_after_node"] = stop_after
    order_sn = str(variables.get("order_sn") or variables.get("last_order_sn") or "").strip()
    log: Dict[str, Any] = {
        "script": RESUME_ORDER_FLOW_SCRIPT_NAME,
        "mode": "resume_order_flow",
        "started_at": datetime.now(),
        "order_sn": order_sn,
        "stop_after_node": stop_after,
        "input_adjustments": input_adjustments,
        "steps": [],
        "shared_data": {},
        "skipped_nodes": [],
    }
    if order_sn:
        log["shared_data"]["order_sn"] = order_sn

    try:
        if not order_sn:
            return _resume_flow_finish(log, False, "order_created", reason="\u8bf7\u8f93\u5165\u8ba2\u5355\u53f7")

        detected, detect_summary = _detect_resume_order_state(env, variables, order_sn, log)
        detect_summary = dict(detect_summary or {})
        _full_flow_update_shared(log["shared_data"], detect_summary)
        log["detected_start_node"] = str(detect_summary.get("detected_start_node") or "")
        if not detected:
            return _resume_flow_finish(
                log,
                False,
                str(log.get("detected_start_node") or "order_created"),
                reason=str(detect_summary.get("reason") or "\u672a\u8bc6\u522b\u8ba2\u5355\u53ef\u6062\u590d\u8d77\u70b9"),
            )

        detected_start_node = str(detect_summary.get("detected_start_node") or "")
        order_status = detect_summary.get("order_status")
        skip_shelf = False
        if detected_start_node == "pending_purchase":
            _resume_record_skipped(
                log,
                ["order_translated", "order_confirmed", "order_offered", "order_paid"],
                "\u8ba2\u5355\u5df2\u5728\u5f85\u62cd\u4e0b\uff0c\u8df3\u8fc7\u8ba2\u5355\u540e\u53f0\u62a5\u4ef7\u548c\u8ba2\u5355\u652f\u4ed8",
            )
        elif detected_start_node == "shelf_stored":
            skip_shelf = True
            _resume_record_skipped(
                log,
                [
                    "order_translated",
                    "order_confirmed",
                    "order_offered",
                    "order_paid",
                    "pending_purchase",
                    "purchase_no_saved",
                    "purchase_wait_modify_price",
                    "purchase_wait_pay",
                    "purchase_paid",
                    "checking_started",
                    "shelf_stored",
                ],
                "\u8ba2\u5355\u5df2\u5230\u4ed3\u5e93\u5f85\u53d1\u8d27\uff0c\u8df3\u8fc7\u8ba2\u5355\u548c\u4e0a\u67b6\u9636\u6bb5",
            )
            if _full_flow_stop_reached(variables, "shelf_stored"):
                return _resume_flow_finish(log, True, "shelf_stored", paused=True)
        else:
            if order_status == 30:
                _resume_record_skipped(
                    log,
                    ["order_translated", "order_confirmed", "order_offered"],
                    "\u8ba2\u5355\u5df2\u5b8c\u6210\u62a5\u4ef7\uff0c\u8df3\u8fc7\u8ba2\u5355\u540e\u53f0\u9636\u6bb5",
                )
            else:
                base_url = (variables.get("backend_base_url") or env.base_url or bulk_cart.BASE_URL).rstrip("/")
                timeout = _as_int(variables.get("timeout"), env.timeout or 25)
                item_quantity = _as_int(variables.get("order_item_num") or variables.get("item_quantity"), 10)
                backend_passed, backend_summary = _run_backend_order_flow_resume(
                    base_url,
                    timeout,
                    variables,
                    order_sn,
                    item_quantity,
                    log,
                    detect_summary.get("order_data") if isinstance(detect_summary.get("order_data"), dict) else {},
                )
                backend_summary = dict(backend_summary or {})
                _full_flow_record_step(
                    log,
                    str(backend_summary.get("current_node") or backend_summary.get("stopped_after_node") or detected_start_node or "order_offered"),
                    ORDER_SCRIPT_NAME,
                    backend_passed,
                    backend_summary,
                )
                if not backend_passed:
                    return _resume_flow_finish(
                        log,
                        False,
                        str(backend_summary.get("current_node") or detected_start_node or "order_offered"),
                        reason=str(backend_summary.get("reason") or backend_summary.get("error") or "\u8ba2\u5355\u540e\u53f0\u63a5\u7eed\u5931\u8d25"),
                    )
                if _is_paused(backend_summary):
                    return _resume_flow_finish(log, True, str(backend_summary.get("current_node") or "order_offered"), paused=True)

            pay_vars = dict(variables)
            pay_vars["order_sn"] = order_sn
            pay_passed, pay_log, pay_report, pay_summary = _payment_with_bank_fallback(env, pay_vars, porder=False)
            pay_summary = dict(pay_summary or {})
            _full_flow_record_step(
                log,
                "order_paid",
                pay_summary.get("payment_type") == "bank" and BANK_PAYMENT_SCRIPT_NAME or BALANCE_PAYMENT_SCRIPT_NAME,
                pay_passed,
                pay_summary,
                pay_report,
            )
            if not pay_passed:
                return _resume_flow_finish(
                    log,
                    False,
                    "order_paid",
                    reason=str(pay_summary.get("reason") or pay_summary.get("error") or "\u8ba2\u5355\u652f\u4ed8\u5931\u8d25"),
                )
            if _full_flow_stop_reached(variables, "order_paid"):
                return _resume_flow_finish(log, True, "order_paid", paused=True)

        if not skip_shelf:
            shelf_vars = dict(variables)
            shelf_vars["order_sn"] = order_sn
            shelf_vars["purchase_no"] = str(variables.get("purchase_no") or _purchase_timestamp_no())
            shelf_vars["link_quote_balance_before_shelf"] = False
            shelf_vars["auto_quote_and_pay"] = False
            shelf_passed, shelf_log, shelf_report, shelf_summary = run_purchase_to_shelf_script(env, shelf_vars)
            shelf_summary = dict(shelf_summary or {})
            _full_flow_record_step(log, str(shelf_summary.get("current_node") or "shelf_stored"), PURCHASE_TO_SHELF_SCRIPT_NAME, shelf_passed, shelf_summary, shelf_report)
            if not shelf_passed:
                return _resume_flow_finish(
                    log,
                    False,
                    str(shelf_summary.get("current_node") or "shelf_stored"),
                    reason=str(shelf_summary.get("reason") or shelf_summary.get("error") or "\u5f85\u62cd\u4e0b\u5230\u4e0a\u67b6\u5931\u8d25"),
                )
            if _is_paused(shelf_summary):
                return _resume_flow_finish(log, True, str(shelf_summary.get("current_node") or "shelf_stored"), paused=True)

        delivery_vars = dict(variables)
        delivery_vars.update(log["shared_data"])
        delivery_vars["run_backend_delivery_flow"] = True
        delivery_vars["warehouse_order_sn"] = order_sn
        delivery_vars["warehouse_fill_scope"] = "current_order_then_history"
        delivery_vars.setdefault("require_warehouse_sku_count", True)
        delivery_vars.setdefault("warehouse_fill_retries", 3)
        delivery_vars.setdefault("warehouse_fill_retry_delay", 1)
        delivery_vars.pop("porder_sn", None)
        delivery_passed, delivery_log, delivery_report, delivery_summary = run_warehouse_delivery_script(env, delivery_vars)
        delivery_summary = dict(delivery_summary or {})
        _full_flow_record_step(log, str(delivery_summary.get("current_node") or "porder_offered"), WAREHOUSE_DELIVERY_SCRIPT_NAME, delivery_passed, delivery_summary, delivery_report)
        if not delivery_passed:
            return _resume_flow_finish(
                log,
                False,
                str(delivery_summary.get("current_node") or "porder_offered"),
                reason=str(delivery_summary.get("reason") or delivery_summary.get("error") or "\u914d\u9001\u5355\u6d41\u8f6c\u5931\u8d25"),
            )
        if _is_paused(delivery_summary):
            return _resume_flow_finish(log, True, str(delivery_summary.get("current_node") or "porder_offered"), paused=True)

        return _resume_flow_finish(log, True, "porder_offered")
    except Exception as exc:
        log["error"] = str(exc)
        return _resume_flow_finish(log, False, str(log["steps"][-1]["node"] if log["steps"] else "order_created"), reason=str(exc))


def run_resume_porder_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    variables["_runtime"] = variables.get("_runtime") if isinstance(variables.get("_runtime"), DataScriptRuntime) else DataScriptRuntime()
    variables.setdefault("sleep", 0)
    variables.setdefault("after_box_submit_delay", 0.2)
    variables.setdefault("after_complete_box_delay", 0.2)
    stop_after = _stop_after_node(variables) or "porder_offered"
    variables["stop_after_node"] = stop_after
    porder_sn = str(variables.get("porder_sn") or "").strip()
    log: Dict[str, Any] = {
        "script": RESUME_PORDER_FLOW_SCRIPT_NAME,
        "mode": "resume_porder_flow",
        "started_at": datetime.now(),
        "porder_sn": porder_sn,
        "stop_after_node": stop_after,
        "steps": [],
        "shared_data": {},
        "skipped_nodes": [],
    }
    if porder_sn:
        log["shared_data"]["porder_sn"] = porder_sn

    try:
        if not porder_sn:
            return _resume_flow_finish(log, False, "warehouse_delivery_created", reason="请输入配送单号")

        # 检测配送单当前节点
        detected, detect_summary = _detect_resume_porder_state(env, variables, porder_sn, log)
        detect_summary = dict(detect_summary or {})
        log["detected_start_node"] = str(detect_summary.get("detected_start_node") or "")
        if not detected:
            return _resume_flow_finish(
                log,
                False,
                str(log.get("detected_start_node") or "warehouse_delivery_created"),
                reason=str(detect_summary.get("reason") or "未识别配送单可恢复起点"),
            )

        detected_start_node = str(detect_summary.get("detected_start_node") or "")

        # 如果已报价，跳过后台流程直接支付
        if detected_start_node == "porder_offered":
            _resume_record_skipped(
                log,
                ["porder_translated", "porder_confirmed", "porder_wait_offer", "porder_offered"],
                "配送单已完成报价，跳过后台流程",
            )
        else:
            base_url = (variables.get("backend_base_url") or env.base_url or bulk_cart.BASE_URL).rstrip("/")
            timeout = _as_int(variables.get("timeout"), env.timeout or 25)
            backend_passed, backend_summary = _run_backend_porder_flow_resume(
                base_url, timeout, variables, porder_sn, log, detected_start_node,
            )
            backend_summary = dict(backend_summary or {})
            _full_flow_record_step(
                log,
                str(backend_summary.get("current_node") or backend_summary.get("stopped_after_node") or detected_start_node or "porder_offered"),
                WAREHOUSE_DELIVERY_SCRIPT_NAME,
                backend_passed,
                backend_summary,
            )
            if not backend_passed:
                return _resume_flow_finish(
                    log,
                    False,
                    str(backend_summary.get("current_node") or detected_start_node or "porder_offered"),
                    reason=str(backend_summary.get("reason") or backend_summary.get("error") or "配送单后台流程失败"),
                )
            if _is_paused(backend_summary):
                return _resume_flow_finish(log, True, str(backend_summary.get("current_node") or "porder_offered"), paused=True)

        # 支付：余额优先，余额不足自动降级银行支付
        porder_pay_vars = dict(variables)
        porder_pay_vars["porder_sn"] = porder_sn
        porder_pay_vars["run_backend_porder_flow"] = False
        pay_passed, pay_log, pay_report, pay_summary = _payment_with_bank_fallback(env, porder_pay_vars, porder=True)
        pay_summary = dict(pay_summary or {})
        _full_flow_record_step(
            log,
            "porder_paid",
            pay_summary.get("payment_type") == "bank" and POORDER_BANK_PAYMENT_SCRIPT_NAME or POORDER_BALANCE_PAYMENT_SCRIPT_NAME,
            pay_passed,
            pay_summary,
            pay_report,
        )
        if not pay_passed:
            return _resume_flow_finish(
                log,
                False,
                "porder_paid",
                reason=str(pay_summary.get("reason") or pay_summary.get("error") or "配送单支付失败"),
            )
        return _resume_flow_finish(log, True, "porder_paid")
    except Exception as exc:
        log["error"] = str(exc)
        return _resume_flow_finish(log, False, str(log["steps"][-1]["node"] if log["steps"] else "warehouse_delivery_created"), reason=str(exc))


SCRIPT_REGISTRY["porder_balance_payment"]["func"] = run_porder_balance_payment_script
SCRIPT_REGISTRY["porder_bank_payment"]["func"] = run_porder_bank_payment_script
SCRIPT_REGISTRY["full_flow"]["func"] = run_full_flow_script
SCRIPT_REGISTRY["resume_order_flow"]["func"] = run_resume_order_flow_script
SCRIPT_REGISTRY["resume_porder_flow"]["func"] = run_resume_porder_flow_script


# ─── OEM 独立数据脚本（与日本站完全隔离，不影响日本站脚本）──────────────

OEM_SCRIPT_NAME = "OEM创建询价单"
OEM_DEFAULT_BASE_URL = "https://oemapi.rakumart.cn"
OEM_DEFAULT_FRONTEND_ORIGIN = "https://oem.rakumart.cn"
OEM_DEFAULT_ADMIN_ORIGIN = "https://oemadmin.rakumart.cn"


def _oem_post_json(
    session: requests.Session,
    base_url: str,
    path: str,
    body: Dict[str, Any],
    timeout: int,
    token: str | None = None,
    is_admin: bool = False,
    variables: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """OEM 通用 JSON POST 请求，自带 3 次重试。与日本站 multipart form 完全独立。"""
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    origin = (variables or {}).get(
        "backend_manage_origin" if is_admin else "frontend_origin",
        OEM_DEFAULT_ADMIN_ORIGIN if is_admin else OEM_DEFAULT_FRONTEND_ORIGIN,
    )
    headers["Origin"] = origin
    headers["Referer"] = (variables or {}).get(
        "frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN
    ).rstrip("/") + "/"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.post(url, json=body, headers=headers, timeout=timeout)
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"oem request {path} failed after retries: {last_error}")


def _oem_admin_login(session: requests.Session, base_url: str, variables: Dict[str, Any], timeout: int) -> str:
    """OEM 后台登录，返回 access_token。"""
    fields = {
        "username": variables.get("backend_account") or "admin",
        "password": variables.get("backend_password") or "123456",
    }
    payload = _oem_post_json(session, base_url, "/admin/login", fields, timeout, is_admin=True, variables=variables)
    if not payload.get("success") or payload.get("code") not in (0, "0", None):
        raise RuntimeError(f"OEM 后台登录失败: code={payload.get('code')} msg={payload.get('msg')}")
    token = (payload.get("data") or {}).get("access_token")
    if not token:
        raise RuntimeError(f"OEM 后台登录成功但未返回 access_token: {payload}")
    return str(token)


def _oem_client_login(session: requests.Session, base_url: str, variables: Dict[str, Any], timeout: int) -> tuple[str, str, str]:
    """OEM 前台登录，返回 (access_token, user_id, user_info_error)。

    站点接口为 POST /api/login，请求体 {"account","password"}，
    返回 {"code":0,"msg":"操作成功","data":{"access_token":"..."}}，无 success 字段。
    user_id 需调 /api/userInfo 获取（登录响应不含 id）。
    user_info_error 为获取 user_id 时的错误信息（空字符串表示无错误）。
    """
    fields = {
        "account": variables.get("account") or "12345678990",
        "password": variables.get("password") or "123456",
    }
    payload = _oem_post_json(session, base_url, "/api/login", fields, timeout, is_admin=False, variables=variables)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    token = data.get("access_token") or data.get("userToken") or data.get("token")
    if not token:
        raise RuntimeError(f"OEM 前台登录失败: code={payload.get('code')} msg={payload.get('msg')}")

    # 调 /api/userInfo 获取账号 id（样品单号需要，必须带 token）
    user_id = ""
    user_info_error = ""
    try:
        info_payload = _oem_post_json(
            session, base_url, "/api/userInfo", {}, timeout,
            token=token, is_admin=False, variables=variables,
        )
        info_data = info_payload.get("data") if isinstance(info_payload.get("data"), dict) else {}
        user_id = str(info_data.get("id") or info_data.get("user_id") or info_data.get("uid") or "")
        if not user_id:
            # 记录完整响应便于排查字段名差异
            user_info_error = f"userInfo 响应无 id 字段, payload={json.dumps(info_payload, ensure_ascii=False)[:300]}"
    except Exception as exc:
        user_info_error = f"调用 /api/userInfo 失败: {exc}"
    return str(token), user_id, user_info_error


def _oem_get_upload_token(session: requests.Session, base_url: str, client_token: str, timeout: int) -> Dict[str, Any]:
    """调 OEM /common/common/getUploadToken 获取阿里云 OSS STS 临时凭证（需 clienttoken 头）。"""
    url = urljoin(base_url.rstrip("/") + "/", "/common/common/getUploadToken")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "clienttoken": client_token,
        "Origin": OEM_DEFAULT_FRONTEND_ORIGIN,
        "Referer": OEM_DEFAULT_FRONTEND_ORIGIN.rstrip("/") + "/",
    }
    response = session.post(url, json={}, headers=headers, timeout=timeout)
    data = response.json() if response.ok else {}
    if not isinstance(data, dict) or not data.get("success"):
        raise RuntimeError(f"获取 OSS STS 失败: {data}")
    sts = data.get("data") or {}
    if not sts.get("AccessKeyId") or not sts.get("SecurityToken"):
        raise RuntimeError(f"OSS STS 数据不完整: {sts}")
    return sts


def _oss_put_object(sts: Dict[str, Any], bucket: str, endpoint: str, object_key: str, content: bytes, content_type: str) -> str:
    """用 STS 临时凭证签名 PUT 到阿里云 OSS，返回可访问 URL。"""
    import hmac, hashlib, base64
    from email.utils import formatdate
    date = formatdate(usegmt=True)
    # OSS v1 签名 StringToSign: VERB\nContent-MD5\nContent-Type\nDate\nCanonicalizedOSSHeaders\nCanonicalizedResource
    string_to_sign = f"PUT\n\n{content_type}\n{date}\nx-oss-security-token:{sts['SecurityToken']}\n/{bucket}/{object_key}"
    signature = base64.b64encode(
        hmac.new(sts["AccessKeySecret"].encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    url = f"https://{bucket}.{endpoint}/{object_key}"
    headers = {
        "Authorization": f"OSS {sts['AccessKeyId']}:{signature}",
        "Content-Type": content_type,
        "Date": date,
        "x-oss-security-token": sts["SecurityToken"],
    }
    response = requests.put(url, data=content, headers=headers, timeout=30)
    if response.status_code not in (200, 204):
        raise RuntimeError(f"OSS PUT 失败: {response.status_code} {response.text[:200]}")
    return url


OEM_OSS_BUCKET = "rakumart-oem"
OEM_OSS_ENDPOINT = "oss-ap-northeast-1.aliyuncs.com"


def upload_oem_image(file_name: str, content: bytes, content_type: str, base_url: str = OEM_DEFAULT_BASE_URL) -> str:
    """OEM 图片上传：获取 STS -> PUT 到 OSS -> 返回 OSS URL（getUploadToken 无需登录鉴权）。"""
    session = requests.Session()
    sts = _oem_get_upload_token(session, base_url, "", 30)
    # 构造 object_key: dest/202607/6位随机/文件名
    now = datetime.now()
    month_dir = now.strftime("%Y%m")
    import random, string
    rand_suffix = "".join(random.choices(string.digits, k=6))
    safe_name = (file_name or "upload.png").replace("\\", "/").split("/")[-1]
    object_key = f"dest/{month_dir}/{rand_suffix}/{safe_name}"
    return _oss_put_object(sts, OEM_OSS_BUCKET, OEM_OSS_ENDPOINT, object_key, content, content_type)


def _oem_parse_factory_urls(variables: Dict[str, Any]) -> list:
    """从前端多行文本解析工厂链接列表，兼容旧 factory_url 单值字段。"""
    raw = variables.get("factory_urls")
    if raw and isinstance(raw, list):
        return raw
    if raw and isinstance(raw, str):
        urls = [line.strip() for line in raw.splitlines() if line.strip()]
        if urls:
            return urls
    old = variables.get("factory_url")
    return [old] if old else []


def _oem_extract_factory_iid(factory_url: str) -> str:
    """从 1688 工厂链接解析 memberId 作为 factory_iid。

    支持格式：
    - https://sale.1688.com/factory/card.html?...&memberId=b2b-2216921663537497f8&...
    - https://detail.1688.com/offer/xxx.html?memberId=b2b-xxx
    - 兼容 HTML 编码 &amp; （从页面复制时可能带上）
    - 兼容小写 memberid (1688 不同页面参数写法不同)

    若 URL 不含 memberId 参数，返回空字符串。
    """
    if not factory_url:
        return ""
    # 处理 HTML 编码（&amp; → &），从页面复制可能带上
    url = factory_url.replace('&amp;', '&').replace('&AMP;', '&')
    # 不区分大小写：兼容 memberId / memberid / MEMBERID 等写法
    m = re.search(r'[?&]memberid=([^&#\s]+)', url, re.IGNORECASE)
    return m.group(1) if m else ""


def run_oem_new_inquiry_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 创建询价单脚本：前台登录 -> 创建询价单，返回 inquiry_sn。"""
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")

    log: Dict[str, Any] = {
        "script": OEM_SCRIPT_NAME,
        "mode": "oem_new_inquiry",
        "base_url": base_url,
        "started_at": datetime.now(),
        "steps": [],
    }

    try:
        session = requests.Session()
        # 前台登录
        client_token, user_id, _ = _oem_client_login(session, base_url, variables, timeout)
        _step(
            log,
            "client_login",
            {"account": variables.get("account") or "12345678990"},
            {"url": "/api/login", "method": "POST"},
            {"token": client_token[:16] + "..."},
        )

        # 构造创建询价单请求体
        sku_info = variables.get("sku_info")
        if not isinstance(sku_info, list):
            sku_info = [
                {"sku": variables.get("sku1") or "sku1", "num": variables.get("sku1_num") or "1"},
                {"sku": variables.get("sku2") or "sku2", "num": variables.get("sku2_num") or "2"},
                {"sku": variables.get("sku3") or "sku3", "num": variables.get("sku3_num") or "3"},
            ]
        body: Dict[str, Any] = {
            "goods_name": variables.get("goods_name") or "测试商品",
            "hope_min_price": variables.get("hope_min_price") or "1",
            "hope_max_price": variables.get("hope_max_price") or "100",
            "hope_futures": variables.get("hope_futures") or "10",
            "material": variables.get("material") or "",
            "sku_info": sku_info,
            "is_temporarily": False,
            "goods_type": int(variables.get("goods_type") or 1),
            "goods_detail": variables.get("goods_detail") or "",
            "num": int(variables.get("num") or sum(int(s.get("num") or 0) for s in sku_info)),
            "customize_detail": variables.get("customize_detail") or "",
            "factory_urls": _oem_parse_factory_urls(variables),
            "factory_type": int(variables.get("factory_type") or 3),
            "goods_file": variables.get("goods_file") or [],
            "goods_img": variables.get("goods_img") or "",
            "goods_other_img": variables.get("goods_other_img") or [],
            "provide_prototype": False,
            "register_forward": variables.get("register_forward") or "",
            "forward_order": variables.get("forward_order") or {"forward_sn": "", "num": "", "goods_value": ""},
        }

        # 调用创建询价单接口（前台 token 注入 Authorization: Bearer 头）
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {client_token}",
            "Origin": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN),
            "Referer": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN).rstrip("/") + "/",
        }
        url = urljoin(base_url.rstrip("/") + "/", "/api/newInquiry")
        last_error: Exception | None = None
        payload: Dict[str, Any] = {}
        for attempt in range(3):
            try:
                response = session.post(url, json=body, headers=headers, timeout=timeout)
                payload = response.json()
                break
            except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
        else:
            raise RuntimeError(f"创建询价单请求失败: {last_error}")

        if not payload.get("success") or payload.get("code") not in (0, "0", None):
            _step(log, "new_inquiry", payload, {"url": "/api/newInquiry", "method": "POST"})
            return _finish_named(
                OEM_SCRIPT_NAME,
                log,
                False,
                {"reason": f"创建询价单失败: {payload.get('msg')}", "error": payload.get("msg"), "payload": payload},
            )

        inquiry_sn = str(payload.get("data") or "")
        _step(
            log,
            "new_inquiry",
            payload,
            {"url": "/api/newInquiry", "method": "POST"},
            {"inquiry_sn": inquiry_sn, "success": True},
        )

        summary = {"inquiry_sn": inquiry_sn, "reason": "创建询价单成功"}
        return _finish_named(OEM_SCRIPT_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_SCRIPT_NAME, log, False, {"reason": str(exc), "error": str(exc)})


# ─── OEM 样品单提出脚本 ───────────────────────────────────────────────

OEM_SAMPLE_ORDER_SCRIPT_NAME = "OEM提出样品单"


# OEM 后端常见日文错误信息 → 中文翻译
_OEM_MSG_TRANSLATIONS = {
    "操作に失敗しました": "操作失败",
    "操作成功": "操作成功",
    "SKU形式が正しくありません": "SKU 格式不正确",
    "パラメータエラー": "参数错误",
    "システムエラー": "系统错误",
    "ログインに失敗しました": "登录失败",
    "権限がありません": "无权限",
    "データが存在しません": "数据不存在",
    "注文情報が存在しません": "订单信息不存在",
    "在庫が不足しています": "库存不足",
}


def _translate_oem_msg(msg: Any) -> str:
    """翻译 OEM 后端日文 msg 为中文，未命中则原样返回。"""
    text = str(msg or "").strip()
    if not text:
        return ""
    for jp, cn in _OEM_MSG_TRANSLATIONS.items():
        if jp in text:
            return text.replace(jp, cn)
    return text


# OEM 单子属性映射：body.type 值 → 单号后缀
_OEM_ORDER_TYPE_LABELS = {
    1: "OEM",
    2: "ODM",
    3: "FL",
}


def _oem_order_type_label(order_type, variables=None) -> str:
    """根据 body.type 返回单子属性标签（OEM/ODM/FL）。"""
    if variables and str(variables.get("order_type_label") or "").strip():
        return str(variables["order_type_label"]).strip()
    try:
        t = int(order_type or 1)
    except (TypeError, ValueError):
        t = 1
    label = _OEM_ORDER_TYPE_LABELS.get(t)
    if not label:
        label = "OEM"
    return label


def _oem_generate_sample_order_sn(variables=None, user_id="", order_type=1) -> str:
    """生成 OEM 样品单号：Y + 14位时间戳 + - + 账号id + - + 单子属性。

    规则：Y{YYYYMMDDHHMMSS}-{user_id}-{OEM|ODM|FL}
    - user_id: 账号 id（从 /api/userInfo 获取）
    - order_type: 1=OEM, 2=ODM, 3=FL
    允许通过 variables["sample_order_sn"] 自定义覆盖。
    """
    if variables and str(variables.get("sample_order_sn") or "").strip():
        return str(variables["sample_order_sn"]).strip()
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    uid = str(user_id or (variables.get("user_id") if variables else "") or "").strip()
    label = _oem_order_type_label(order_type, variables)
    return f"Y{ts}-{uid}-{label}"


def run_oem_sample_order_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 样品单提出脚本：前台登录 -> 创建样品单，返回 order_sn。

    接口 POST /api/newOrder，从询价单提出样品单。

    可配置变量：
        - account / password: 前台登录账号（默认 12345678990 / 123456）
        - order_sn: 询价单号（必填，如 Y20260701111904-15-OEM）
        - sku_list: SKU 列表，支持两种格式：
            a) JSON 字符串 [{"sku_id":1993,"num":1},{"sku_id":1994,"num":2}]
            b) 纯文本行，每行 "sku_id,num"（如 "1993,1"）
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")

    order_sn = str(variables.get("order_sn") or "").strip()
    if not order_sn:
        return _finish_named(
            OEM_SAMPLE_ORDER_SCRIPT_NAME, {},
            False, {"reason": "缺少必填参数：询价单号 order_sn 不能为空"},
        )

    log: Dict[str, Any] = {
        "script": OEM_SAMPLE_ORDER_SCRIPT_NAME,
        "mode": "oem_sample_order",
        "base_url": base_url,
        "inquiry_order_sn": order_sn,
        "sample_order_sn": "",
        "started_at": datetime.now(),
        "steps": [],
    }

    try:
        session = requests.Session()
        # 前台登录
        client_token, user_id, _ = _oem_client_login(session, base_url, variables, timeout)
        _step(
            log,
            "client_login",
            {"account": variables.get("account") or "12345678990"},
            {"url": "/client/userLogin", "method": "POST"},
            {"token": client_token[:16] + "..."},
        )

        # 解析 SKU 列表
        sku_list = variables.get("sku_list")
        if isinstance(sku_list, list):
            # 已是列表，确保每项含 option
            pass
        elif isinstance(sku_list, str) and sku_list.strip().startswith("["):
            # JSON 字符串解析
            try:
                sku_list = json.loads(sku_list)
            except (json.JSONDecodeError, TypeError):
                sku_list = []
        elif isinstance(sku_list, str) and sku_list.strip():
            # 纯文本行格式：每行 "sku_id,num"
            sku_list = []
            for line in sku_list.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                try:
                    sku_id = int(parts[0].strip())
                    num = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else 1
                    sku_list.append({"sku_id": sku_id, "num": num, "option": []})
                except (ValueError, IndexError):
                    continue
        else:
            sku_list = []

        # 确保每个 SKU 有 option 字段（OEM API 必须）
        if isinstance(sku_list, list):
            for item in sku_list:
                if isinstance(item, dict) and "option" not in item:
                    item["option"] = []

        sample_order_sn = _oem_generate_sample_order_sn(variables, user_id, 1)
        log["sample_order_sn"] = sample_order_sn
        body: Dict[str, Any] = {
            "order_sn": sample_order_sn,
            "inquiry_detail_id": variables.get("inquiry_detail_id") or str(variables.get("id") or ""),
            "type": 1,
            "sku_list": sku_list if sku_list else [{"sku_id": 1993, "num": 1, "option": []}],
            "remark": "",
            "warehouse_city": 2,
        }

        # 调用创建样品单接口
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {client_token}",
            "Origin": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN),
            "Referer": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN).rstrip("/") + "/",
        }
        url = urljoin(base_url.rstrip("/") + "/", "/api/newOrder")
        last_error: Exception | None = None
        payload: Dict[str, Any] = {}
        for attempt in range(3):
            try:
                response = session.post(url, json=body, headers=headers, timeout=timeout)
                payload = response.json()
                break
            except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
        else:
            raise RuntimeError(f"创建样品单请求失败: {last_error}")

        if not payload.get("success") or payload.get("code") not in (0, "0", None):
            raw_msg = payload.get("msg")
            raw_data = payload.get("data")
            translated_msg = _translate_oem_msg(raw_msg)
            # data 含 "Line:" 通常是后端业务校验失败（询价单已被转过样品单/状态已变更）
            hint = ""
            if isinstance(raw_data, str) and "Line:" in raw_data:
                hint = "（可能原因：该询价单已被转过样品单或状态已变更，请确认询价单可用性）"
            _step(
                log,
                "new_sample_order",
                payload,
                {"url": "/api/newOrder", "method": "POST", "body": body},
            )
            return _finish_named(
                OEM_SAMPLE_ORDER_SCRIPT_NAME,
                log,
                False,
                {
                    "reason": f"创建样品单失败: {translated_msg}{hint}",
                    "error": translated_msg,
                    "payload": payload,
                },
            )

        order_sn_out = str(payload.get("data") or "")
        _step(
            log,
            "new_sample_order",
            payload,
            {"url": "/api/newOrder", "method": "POST", "body": body},
            {"order_sn": order_sn_out, "success": True},
        )

        summary = {"order_sn": order_sn_out, "inquiry_order_sn": order_sn, "sample_order_sn": sample_order_sn, "reason": "创建样品单成功"}
        return _finish_named(OEM_SAMPLE_ORDER_SCRIPT_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_SAMPLE_ORDER_SCRIPT_NAME, log, False, {"reason": str(exc), "error": str(exc)})


def fetch_oem_goods_class_list(variables: Dict[str, Any] | None = None) -> list:
    """获取 OEM 商品分类列表（POST /admin/goodsClassList）。

    返回展平后的列表 [{id, class_name, parent_name}, ...]，便于前端下拉渲染。
    """
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), 30)
    base_url = (variables.get("base_url") or OEM_DEFAULT_BASE_URL).rstrip("/")
    session = requests.Session()
    admin_token = _oem_admin_login(session, base_url, variables, timeout)
    payload = _oem_post_json(session, base_url, "/admin/goodsClassList", {}, timeout,
                             token=admin_token, is_admin=True, variables=variables)
    if not payload.get("success"):
        return []
    tree = payload.get("data")
    if not isinstance(tree, list):
        return []
    flat: list = []

    def _flatten(items, parent_name=""):
        for item in items:
            name = item.get("class_name") or ""
            flat.append({"id": item.get("id"), "class_name": name, "parent_name": parent_name})
            childs = item.get("childs") or []
            if childs:
                _flatten(childs, name)

    _flatten(tree)
    return flat


def fetch_oem_option_list(variables: Dict[str, Any] | None = None) -> list:
    """获取 OEM 大货单可选 option 列表（POST /common/common/optionList，空 body）。"""
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), 30)
    base_url = (variables.get("base_url") or OEM_DEFAULT_BASE_URL).rstrip("/")
    session = requests.Session()
    client_token, user_id, _ = _oem_client_login(session, base_url, variables, timeout)
    return _oem_query_option_list(session, base_url, client_token, timeout, variables)


def fetch_oem_full_quote(order_sn: str, variables: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """根据询价单号查询 OEM 完整报价详情。

    两步调用：
      1. POST /api/inquiryDetail  → 获取 detail_id 及工厂信息
      2. POST /api/quoteDetail   → 获取完整报价明细
    返回合并后的 data 对象，查询失败时返回空 dict。
    """
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), 30)
    base_url = (variables.get("base_url") or OEM_DEFAULT_BASE_URL).rstrip("/")

    try:
        session = requests.Session()
        client_token, user_id, _ = _oem_client_login(session, base_url, variables, timeout)

        # 1. 查询询价单基本信息，获取 detail_id
        inquiry_payload = _oem_post_json(
            session, base_url, "/api/inquiryDetail",
            {"order_sn": order_sn}, timeout,
            token=client_token, is_admin=False, variables=variables,
        )
        if not inquiry_payload.get("success") or inquiry_payload.get("code") not in (0, "0", None):
            return {}
        inquiry_data = inquiry_payload.get("data")
        if not isinstance(inquiry_data, dict):
            return {}

        # 提取第一条记录的 id 作为 detail_id
        records = inquiry_data.get("list") or []
        if not isinstance(records, list) or not records:
            return {}
        first = records[0] if isinstance(records[0], dict) else {}
        detail_id = first.get("id") or ""
        inquiry_data["detail_id"] = detail_id

        # 2. 查询完整报价详情
        if detail_id:
            try:
                quote_payload = _oem_post_json(
                    session, base_url, "/api/quoteDetail",
                    {"detail_id": str(detail_id)}, timeout,
                    token=client_token, is_admin=False, variables=variables,
                )
                if quote_payload.get("success") and quote_payload.get("code") in (0, "0", None):
                    quote_data = quote_payload.get("data")
                    if isinstance(quote_data, dict):
                        inquiry_data["quote_detail"] = quote_data
            except Exception:
                pass

        return inquiry_data

    except Exception:
        return {}


# ─── OEM 询价单全流程脚本（提出→翻译→询价→报价） ──────────────────────

OEM_FULL_INQUIRY_SCRIPT_NAME = "OEM询价单全流程"


def _oem_normalize_goods_class(detail: Dict[str, Any]) -> Any:
    """详情接口返回的 goods_class 是对象 {"id":110,"class_name":"..."}，
    提交给后台的 body 需要 goods_class 为数字 id。原地修改并返回。"""
    gc = detail.get("goods_class")
    if isinstance(gc, dict):
        detail["goods_class"] = gc.get("id")
    return detail


def _oem_query_inquiry_detail(
    session: requests.Session, base_url: str, admin_token: str, order_sn: str, timeout: int, variables: Dict[str, Any]
) -> Dict[str, Any]:
    """查询询价单完整详情（POST /admin/inquiryDetail 不带 point_name）。"""
    payload = _oem_post_json(
        session, base_url, "/admin/inquiryDetail",
        {"order_sn": order_sn}, timeout,
        token=admin_token, is_admin=True, variables=variables,
    )
    if not payload.get("success") and payload.get("code") not in (0, "0", None):
        raise RuntimeError(f"查询询价单详情失败: code={payload.get('code')} msg={payload.get('msg')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"询价单详情数据异常: {payload}")
    _oem_normalize_goods_class(data)
    return data


def _oem_submit_node(
    session: requests.Session, base_url: str, admin_token: str, order_sn: str,
    point_name: str, is_quote: bool, timeout: int, variables: Dict[str, Any],
) -> Dict[str, Any]:
    """节点提交（POST /admin/inquiryDetail 带 point_name）。"""
    body = {"order_sn": order_sn, "is_quote": is_quote, "point_name": point_name}
    return _oem_post_json(session, base_url, "/admin/inquiryDetail", body, timeout,
                          token=admin_token, is_admin=True, variables=variables)


def run_oem_full_inquiry_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 询价单全流程脚本：前台提出询价单 → 后台翻译 → 询价 → 报价，直至报价成功。

    支持从指定 order_sn 开始（跳过创建），便于调试中间阶段。
    各阶段可通过开关变量跳过：skip_create / skip_translate / skip_inquiry / skip_quote。
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")

    log: Dict[str, Any] = {
        "script": OEM_FULL_INQUIRY_SCRIPT_NAME,
        "mode": "oem_full_inquiry",
        "base_url": base_url,
        "started_at": datetime.now(),
        "steps": [],
    }

    try:
        session = requests.Session()
        order_sn = str(variables.get("order_sn") or "").strip()
        admin_token = ""
        client_token = ""

        # ─── 阶段1：询价单提出（前台登录 + 创建询价单） ─────────────
        if not variables.get("skip_create") and not order_sn:
            client_token, user_id, _ = _oem_client_login(session, base_url, variables, timeout)
            _step(log, "client_login", {"account": variables.get("account") or "12345678990"},
                  {"url": "/api/login", "method": "POST"}, {"token": client_token[:16] + "..."})

            sku_info = variables.get("sku_info")
            if not isinstance(sku_info, list):
                sku_info = [
                    {"sku": variables.get("sku1") or "sku1", "num": int(variables.get("sku1_num") or 1)},
                    {"sku": variables.get("sku2") or "sku2", "num": int(variables.get("sku2_num") or 2)},
                    {"sku": variables.get("sku3") or "sku3", "num": int(variables.get("sku3_num") or 3)},
                ]
            # 创建询价单前校验工厂链接：缺 factory_urls 会导致后端不生成 detail_list，
            # 后续询价阶段无法工厂报价，inquiryComplete 会报"请报价至少一条数据后点击"
            factory_urls_for_create = _oem_parse_factory_urls(variables)
            if not factory_urls_for_create:
                _step(log, "new_inquiry", {"order_sn": ""},
                      {"url": "/api/newInquiry", "method": "POST"},
                      {"success": False, "msg": "缺少 factory_urls，无法走通询价全流程"})
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": "创建询价单失败: 缺少 factory_urls，请在前端配置工厂链接后再执行"})
            create_body: Dict[str, Any] = {
                "goods_name": variables.get("goods_name") or "测试商品",
                "hope_min_price": variables.get("hope_min_price") or "1",
                "hope_max_price": variables.get("hope_max_price") or "100",
                "hope_futures": variables.get("hope_futures") or "10",
                "material": variables.get("material") or "",
                "sku_info": sku_info,
                "is_temporarily": False,
                "goods_type": int(variables.get("goods_type") or 1),
                "goods_class": int(variables.get("goods_class") or 110),
                "goods_detail": variables.get("goods_detail") or "",
                "num": int(variables.get("num") or sum(int(s.get("num") or 0) for s in sku_info)),
                "customize_detail": variables.get("customize_detail") or "",
                "factory_urls": _oem_parse_factory_urls(variables),
                "factory_type": int(variables.get("factory_type") or 3),
                "goods_file": variables.get("goods_file") or [],
                "goods_img": variables.get("goods_img") or "",
                "goods_other_img": variables.get("goods_other_img") or [],
                "provide_prototype": False,
                "register_forward": variables.get("register_forward") or "",
                "forward_order": variables.get("forward_order") or {"forward_sn": "", "num": "", "goods_value": ""},
            }
            create_headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {client_token}",
                "Origin": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN),
                "Referer": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN).rstrip("/") + "/",
            }
            url = urljoin(base_url.rstrip("/") + "/", "/api/newInquiry")
            response = session.post(url, json=create_body, headers=create_headers, timeout=timeout)
            payload = response.json()
            if not payload.get("success") and payload.get("code") not in (0, "0", None):
                _step(log, "new_inquiry", create_body, {"url": "/api/newInquiry", "method": "POST"}, payload)
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"创建询价单失败: {payload.get('msg')}", "error": payload.get("msg")})
            order_sn = str(payload.get("data") or "")
            _step(log, "new_inquiry", create_body, {"url": "/api/newInquiry", "method": "POST"},
                  {"inquiry_sn": order_sn, "success": True})
        else:
            _step(log, "skip_create", {"order_sn": order_sn}, {"note": "跳过创建，使用传入 order_sn"}, {"skipped": True})

        if not order_sn:
            return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False, {"reason": "未获取到 order_sn"})

        # ─── 后台登录（后续阶段都需要） ─────────────────────────
        admin_token = _oem_admin_login(session, base_url, variables, timeout)
        _step(log, "admin_login", {"username": variables.get("backend_account") or "admin"},
              {"url": "/admin/login", "method": "POST"}, {"token": admin_token[:16] + "..."})

        # 查询询价单完整详情
        detail = _oem_query_inquiry_detail(session, base_url, admin_token, order_sn, timeout, variables)
        _step(log, "query_detail", {"order_sn": order_sn}, {"url": "/admin/inquiryDetail", "method": "POST"},
              {"inquiry_id": detail.get("id"), "detail_count": len(detail.get("detail_list") or []),
               "sku_count": len(detail.get("sku_info") or [])})

        # ─── 阶段2：翻译阶段（提交审核 + 审核完成提交采购） ───────────────
        if not variables.get("skip_translate"):
            translate_body: Dict[str, Any] = {
                "is_temp": False,
                "order_sn": order_sn,
                "goods_name_tr": variables.get("goods_name_tr") or (detail.get("goods_name_tr") or detail.get("goods_name") or ""),
                "material_tr": variables.get("material_tr") or (detail.get("material_tr") or detail.get("material") or ""),
                "customize_detail_tr": variables.get("customize_detail_tr") or (detail.get("customize_detail_tr") or detail.get("customize_detail") or ""),
                "goods_detail_tr": variables.get("goods_detail_tr") or (detail.get("goods_detail_tr") or detail.get("goods_detail") or ""),
                "goods_file_tr": detail.get("goods_file_tr") or [],
                "sku_info": detail.get("sku_info") or [],
                "goods_id": str(detail.get("goods_id") or ""),
                "goods_class": int(variables.get("goods_class") or 110),
                "y_remark": detail.get("y_remark") or "",
                "user_remark": detail.get("user_remark") or "",
            }
            tp = _oem_post_json(session, base_url, "/admin/inquiryTranslate", translate_body, timeout,
                                token=admin_token, is_admin=True, variables=variables)
            _step(log, "translate_save", translate_body, {"url": "/admin/inquiryTranslate", "method": "POST"},
                  {"success": tp.get("success"), "msg": tp.get("msg")})
            if not tp.get("success") and tp.get("code") not in (0, "0", None):
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"翻译保存失败: {tp.get('msg')}", "order_sn": order_sn})

            # 提交给采购（审核完成后推进状态到可询价）
            ap = _oem_post_json(session, base_url, "/admin/inquiryTranslateAudit", {"order_sn": order_sn}, timeout,
                                token=admin_token, is_admin=True, variables=variables)
            _step(log, "translate_audit", {"order_sn": order_sn}, {"url": "/admin/inquiryTranslateAudit", "method": "POST"},
                  {"success": ap.get("success"), "msg": ap.get("msg")})
            if not ap.get("success") and ap.get("code") not in (0, "0", None):
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"翻译审核失败: {ap.get('msg')}", "order_sn": order_sn})
            # 重新查询详情获取最新状态
            detail = _oem_query_inquiry_detail(session, base_url, admin_token, order_sn, timeout, variables)
        else:
            _step(log, "skip_translate", {}, {"note": "跳过翻译阶段"}, {"skipped": True})

        # ─── 阶段3：询价阶段（开始询价 + 编辑工厂 + 工厂报价 + 询价完成） ──
        if not variables.get("skip_inquiry"):
            # 开始询价：goods_class 详情返回可能是对象，需确保为有效数字 id
            gc = detail.get("goods_class")
            if isinstance(gc, dict):
                detail["goods_class"] = gc.get("id") or int(variables.get("goods_class") or 110)
            elif not isinstance(gc, int) or gc == 0:
                detail["goods_class"] = int(variables.get("goods_class") or 110)
            sip = _oem_post_json(session, base_url, "/admin/inquiryStartInquiry", detail, timeout,
                                 token=admin_token, is_admin=True, variables=variables)
            _step(log, "start_inquiry", {"order_sn": order_sn}, {"url": "/admin/inquiryStartInquiry", "method": "POST"},
                  {"success": sip.get("success"), "msg": sip.get("msg")})
            if not sip.get("success") and sip.get("code") not in (0, "0", None):
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"开始询价失败: {sip.get('msg')}", "order_sn": order_sn})

            # 重新查询详情，拿到 detail_list 的 id
            detail = _oem_query_inquiry_detail(session, base_url, admin_token, order_sn, timeout, variables)
            detail_list = detail.get("detail_list") or []
            # 兜底校验：detail_list 为空说明后端未生成工厂明细，直接报错而非空跑循环
            if not detail_list:
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"询价单 {order_sn} 无工厂明细 detail_list（可能创建时未传 factory_urls），无法进行工厂报价",
                                      "order_sn": order_sn})
            factory_img = variables.get("factory_img") or "https://img.alicdn.com/placeholder.jpg"
            salesman = variables.get("salesman") or "测试业务员"
            salesman_phone = variables.get("salesman_phone") or "13800000000"
            # 全局默认值（向后兼容：无 factory_quotes 时所有工厂共用这组）
            samples_price_default = variables.get("samples_price") or "12.00"
            large_price_default = variables.get("large_price") or "11.00"
            large_other_fee_default = variables.get("large_other_fee") or "12.00"
            large_freight_default = variables.get("large_freight") or "11.00"
            large_delivery_time_default = int(variables.get("large_delivery_time") or 15)
            large_deposit_rate_default = variables.get("large_deposit_rate") or "100"
            real_samples_price_default = variables.get("real_samples_price") or "10.00"
            real_large_price_default = variables.get("real_large_price") or "10.00"
            # 每工厂差异化报价（前端按 factory_urls 行数展开多组）
            factory_quotes = variables.get("factory_quotes") or []

            for idx, d_item in enumerate(detail_list):
                detail_id = d_item.get("id")
                factory_url = d_item.get("factory_url") or ""
                factory_submit_info = d_item.get("factory_submit_info") or factory_url
                factory_iid = d_item.get("factory_iid") or _oem_extract_factory_iid(factory_url)
                factory_name = d_item.get("factory_name") or "测试工厂"
                # 按工厂 idx 取该工厂的报价字段，缺失时用全局默认
                fq = factory_quotes[idx] if idx < len(factory_quotes) and isinstance(factory_quotes[idx], dict) else {}
                samples_price = fq.get("samples_price") or samples_price_default
                large_price = fq.get("large_price") or large_price_default
                large_other_fee = fq.get("large_other_fee") or large_other_fee_default
                large_freight = fq.get("large_freight") or large_freight_default
                large_delivery_time = int(fq.get("large_delivery_time") or large_delivery_time_default)
                large_deposit_rate = fq.get("large_deposit_rate") or large_deposit_rate_default
                real_samples_price = fq.get("real_samples_price") or real_samples_price_default
                real_large_price = fq.get("real_large_price") or real_large_price_default
                # 编辑工厂
                edit_body: Dict[str, Any] = {
                    "detail_id": detail_id,
                    "factory_iid": factory_iid,
                    "factory_name": factory_name,
                    "factory_province": d_item.get("factory_province") or "",
                    "factory_city": d_item.get("factory_city") or "",
                    "factory_img": factory_img,
                    "factory_url": factory_url,
                    "salesman": salesman,
                    "salesman_phone": salesman_phone,
                    "goods_url": d_item.get("goods_url") or "",
                }
                ep = _oem_post_json(session, base_url, "/admin/factoryEdit", edit_body, timeout,
                                    token=admin_token, is_admin=True, variables=variables)
                _step(log, f"factory_edit_{idx+1}", edit_body, {"url": "/admin/factoryEdit", "method": "POST"},
                      {"detail_id": detail_id, "factory_iid": factory_iid, "factory_url": factory_url, "success": ep.get("success"), "msg": ep.get("msg")})

                # 工厂报价（基于 detail 原有字段 + 报价参数覆盖）
                sku_detail = d_item.get("sku_detail") or []
                for sku in sku_detail:
                    sku["samples_price"] = samples_price
                    sku["large_price"] = large_price
                    sku["real_samples_price"] = real_samples_price
                    sku["real_large_price"] = real_large_price
                # 以 d_item 为基底，只覆盖报价相关字段，避免漏字段导致"参数错误"
                quote_body = dict(d_item)
                quote_body.update({
                    "status": 0, "g_cant_quote": 0, "is_read": 1,
                    "factory_type": d_item.get("factory_type") or 1,
                    "factory_submit_info": factory_submit_info,
                    "factory_iid": factory_iid, "factory_name": factory_name,
                    "factory_province": d_item.get("factory_province") or "浙江省",
                    "factory_city": d_item.get("factory_city") or "杭州市",
                    "factory_url": factory_url, "factory_img": factory_img,
                    "goods_url": d_item.get("goods_url") or "",
                    "samples_other_fee": d_item.get("samples_other_fee") or "0.00",
                    "samples_freight": d_item.get("samples_freight") or "0.00",
                    "samples_delivery_time": d_item.get("samples_delivery_time") or 0,
                    "real_samples_other_fee": d_item.get("real_samples_other_fee") or "0.00",
                    "real_samples_freight": d_item.get("real_samples_freight") or "0.00",
                    "large_other_fee": large_other_fee, "large_freight": large_freight,
                    "large_delivery_time": large_delivery_time, "large_deposit_rate": large_deposit_rate,
                    "real_large_other_fee": variables.get("real_large_other_fee") or "10.00",
                    "real_large_freight": variables.get("real_large_freight") or "10.00",
                    "factory_salesman_id": 0, "warehouse_city": 0,
                    "samples_warehouse_city": 1, "large_warehouse_city": 1,
                    "quote_admin": 0, "is_special_quote": False,
                    "sku_detail": sku_detail, "salesman": salesman, "salesman_phone": salesman_phone,
                    "is_temporarily": False, "detail_id": detail_id,
                })
                qp = _oem_post_json(session, base_url, "/admin/factoryQuote", quote_body, timeout,
                                    token=admin_token, is_admin=True, variables=variables)
                _step(log, f"factory_quote_{idx+1}", {"detail_id": detail_id}, {"url": "/admin/factoryQuote", "method": "POST"},
                      {"success": qp.get("success"), "msg": qp.get("msg")})
                if not qp.get("success") and qp.get("code") not in (0, "0", None):
                    return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                         {"reason": f"工厂{idx+1}报价失败: {qp.get('msg')}", "order_sn": order_sn})

            # 询价完成（detail_list 各 status=1）
            for d_item in detail_list:
                d_item["status"] = 1
            detail["detail_list"] = detail_list
            detail["g_admin_status"] = 2
            cp = _oem_post_json(session, base_url, "/admin/inquiryComplete", detail, timeout,
                                token=admin_token, is_admin=True, variables=variables)
            _step(log, "inquiry_complete", {"order_sn": order_sn}, {"url": "/admin/inquiryComplete", "method": "POST"},
                  {"success": cp.get("success"), "msg": cp.get("msg")})
            if not cp.get("success") and cp.get("code") not in (0, "0", None):
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"询价完成失败: {cp.get('msg')}", "order_sn": order_sn})
        else:
            _step(log, "skip_inquiry", {}, {"note": "跳过询价阶段"}, {"skipped": True})

        # ─── 阶段4：报价阶段（开始报价 → 报价给用户 → 询价单报价完成） ─────────
        if not variables.get("skip_quote"):
            detail = _oem_query_inquiry_detail(session, base_url, admin_token, order_sn, timeout, variables)
            detail_list = detail.get("detail_list") or []
            quote_admin = int(detail.get("g_id") or 19)
            factory_salesman_id = 236

            # 开始报价（必须先调用，否则后续 inquiryQuoteComplate 报"当前状态无法操作"）
            sq = _oem_post_json(session, base_url, "/admin/inquiryStartQuote",
                                {"order_sn": order_sn}, timeout,
                                token=admin_token, is_admin=True, variables=variables)
            _step(log, "start_quote", {"order_sn": order_sn},
                  {"url": "/admin/inquiryStartQuote", "method": "POST"},
                  {"success": sq.get("success"), "msg": sq.get("msg")})
            if not sq.get("success") and sq.get("code") not in (0, "0", None):
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"开始报价失败: {sq.get('msg')}", "order_sn": order_sn})

            for idx, d_item in enumerate(detail_list):
                detail_id = d_item.get("id")
                # 报价给用户：基于 d_item 覆盖报价相关字段
                quote_to_user_body = dict(d_item)
                quote_to_user_body.update({
                    "status": 1, "is_read": 0,
                    "factory_salesman_id": factory_salesman_id,
                    "quote_admin": quote_admin,
                    "is_special_quote": False,
                    "is_temporarily": False,
                    "detail_id": detail_id,
                })
                qp2 = _oem_post_json(session, base_url, "/admin/factoryQuoteToUser", quote_to_user_body, timeout,
                                     token=admin_token, is_admin=True, variables=variables)
                _step(log, f"quote_to_user_{idx+1}", {"detail_id": detail_id},
                      {"url": "/admin/factoryQuoteToUser", "method": "POST"},
                      {"success": qp2.get("success"), "msg": qp2.get("msg")})
                if not qp2.get("success") and qp2.get("code") not in (0, "0", None):
                    return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                         {"reason": f"工厂{idx+1}报价给用户失败: {qp2.get('msg')}", "order_sn": order_sn})

            # 重新查询详情，拿到最新状态后设置 status=2
            detail = _oem_query_inquiry_detail(session, base_url, admin_token, order_sn, timeout, variables)
            detail_list = detail.get("detail_list") or []
            for d_item in detail_list:
                d_item["status"] = 2
            detail["detail_list"] = detail_list

            # 询价单报价完成（发送完整 detail body）
            qcp = _oem_post_json(session, base_url, "/admin/inquiryQuoteComplate", detail, timeout,
                                 token=admin_token, is_admin=True, variables=variables)
            _step(log, "quote_complete", {"order_sn": order_sn}, {"url": "/admin/inquiryQuoteComplate", "method": "POST"},
                  {"success": qcp.get("success"), "msg": qcp.get("msg")})
            if not qcp.get("success") and qcp.get("code") not in (0, "0", None):
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"询价单报价完成失败: {qcp.get('msg')}", "order_sn": order_sn})
        else:
            _step(log, "skip_quote", {}, {"note": "跳过报价阶段"}, {"skipped": True})

        final_detail = detail_list[0] if detail_list else {}
        final_sku_list = final_detail.get("sku_detail") or []
        final_sku = final_sku_list[0] if final_sku_list else {}
        summary = {
            "order_sn": order_sn,
            "reason": "OEM 询价单全流程执行成功",
            "samples_price_return": final_sku.get("samples_price_return") or "0.00",
            "samples_other_fee": final_detail.get("samples_other_fee") or "0.00",
            "samples_freight": final_detail.get("samples_freight") or "0.00",
            "samples_delivery_time": final_detail.get("samples_delivery_time") or 0,
            "factory_img": final_detail.get("factory_img") or "",
        }
        return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False, {"reason": str(exc), "error": str(exc)})


# ─── OEM 样品单后台管理流程 ─────────────────────────────────────────

OEM_SAMPLE_ADMIN_SCRIPT_NAME = "OEM样品单后台流程"


def _oem_admin_post(
    session: requests.Session,
    base_url: str,
    path: str,
    body: Dict[str, Any],
    timeout: int,
    token: str,
    variables: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """OEM 后台 JSON POST，带 Bearer token + admin Origin。"""
    return _oem_post_json(session, base_url, path, body, timeout, token=token, is_admin=True, variables=variables)


def _call_admin_api(
    session: requests.Session,
    base_url: str,
    path: str,
    body: Dict[str, Any],
    timeout: int,
    token: str,
    variables: Dict[str, Any] | None,
    log: Dict[str, Any],
    step_name: str,
) -> Dict[str, Any]:
    """调用后台 API 并记录日志，失败时抛 RuntimeError。"""
    payload = _oem_admin_post(session, base_url, path, body, timeout, token, variables)
    if not payload.get("success") or payload.get("code") not in (0, "0", None):
        _step(log, step_name, payload, {"url": path, "method": "POST"})
        raise RuntimeError(f"{step_name} 失败: {payload.get('msg')}")
    _step(log, step_name, payload, {"url": path, "method": "POST"})
    return payload


def _oem_build_sku_info_from_quote(order_sn: str, session: requests.Session, base_url: str, timeout: int, token: str, variables: Dict[str, Any]) -> list[Dict[str, Any]]:
    """从 samplesDetail 获取当前 SKU 数据，用于 samplesConfirmed 的 quote_info.sku_info。"""
    try:
        detail_payload = _oem_admin_post(session, base_url, "/admin/samplesDetail", {"order_sn": order_sn}, timeout, token, variables)
        data = detail_payload.get("data") or {}
        if isinstance(data, dict):
            skus = data.get("sku_detail") or data.get("skuInfo") or data.get("sku_list") or []
            if not skus and isinstance(data.get("list"), list) and len(data["list"]) > 0:
                skus = data["list"][0].get("sku_detail") or []
        elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            skus = data[0].get("sku_detail") or data
        else:
            skus = []
    except Exception:
        skus = []
    # 从 variables 中读取用户提供的 sku_info 覆盖，否则用查到的数据构造
    user_sku_info = variables.get("quote_sku_info")
    if isinstance(user_sku_info, list) and user_sku_info:
        return user_sku_info
    result = []
    for sku in (skus if isinstance(skus, list) else []):
        if not isinstance(sku, dict):
            continue
        result.append({
            "id": sku.get("id") or sku.get("goods_sku_id") or 0,
            "sku": sku.get("sku") or "",
            "sku_tr": sku.get("sku_tr") or sku.get("sku") or "",
            "sku_image": sku.get("sku_image") or "",
            "num": sku.get("num") or 1,
            "inquiry_samples_price": str(sku.get("inquiry_samples_price") or variables.get("inquiry_samples_price", "0")),
            "inquiry_samples_price_return": str(sku.get("inquiry_samples_price_return") or variables.get("inquiry_samples_price_return", "0")),
            "quote_samples_price": str(sku.get("quote_samples_price") or variables.get("quote_samples_price", "1")),
            "quote_samples_price_return": str(sku.get("quote_samples_price_return") or variables.get("quote_samples_price_return", "0")),
            "real_samples_price": str(sku.get("real_samples_price") or variables.get("real_samples_price", "1")),
            "real_samples_price_return": str(sku.get("real_samples_price_return") or variables.get("real_samples_price_return", "0")),
            "keep_sample_sku_num": int(sku.get("keep_sample_sku_num") or 0),
        })
    if not result:
        # 完全构造默认数据
        num_skus = int(variables.get("sku_count") or 3)
        for i in range(1, num_skus + 1):
            sid = variables.get(f"sku_id_{i}")
            if sid:
                result.append({
                    "id": int(sid),
                    "sku": variables.get(f"sku_{i}", f"SKU{i}"),
                    "sku_tr": variables.get(f"sku_tr_{i}", f"SKU{i}"),
                    "sku_image": "",
                    "num": int(variables.get(f"sku_num_{i}", 1)),
                    "inquiry_samples_price": variables.get(f"inquiry_samples_price_{i}", "0"),
                    "inquiry_samples_price_return": variables.get(f"inquiry_samples_price_return_{i}", "0"),
                    "quote_samples_price": variables.get(f"quote_samples_price_{i}", "1"),
                    "quote_samples_price_return": variables.get(f"quote_samples_price_return_{i}", "0"),
                    "real_samples_price": variables.get(f"real_samples_price_{i}", "1"),
                    "real_samples_price_return": variables.get(f"real_samples_price_return_{i}", "0"),
                    "keep_sample_sku_num": 0,
                })
    return result


def run_oem_sample_admin_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 样品单后台管理流程：翻译提交 → 开始确认 → 采购确认→业务。

    可配置变量：
        - order_sn: 样品单号（必填）
        - warehouse_city: 仓库城市（默认 2）
        - backend_account / backend_password: 后台登录凭证
        - quote_sku_info: SKU 报价明细 JSON（可覆盖自动查询）
        - inquiry_samples_price / quote_samples_price / real_samples_price 等报价字段
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")
    order_sn = str(variables.get("order_sn") or "").strip()
    if not order_sn:
        return _finish_named(OEM_SAMPLE_ADMIN_SCRIPT_NAME, {}, False, {"reason": "缺少必填参数：order_sn"})

    log: Dict[str, Any] = {
        "script": OEM_SAMPLE_ADMIN_SCRIPT_NAME,
        "mode": "oem_sample_admin_flow",
        "base_url": base_url,
        "order_sn": order_sn,
        "started_at": datetime.now(),
        "steps": [],
    }
    try:
        session = requests.Session()
        # Admin 后台登录
        admin_token = _oem_admin_login(session, base_url, variables, timeout)
        _step(log, "admin_login", {}, {"url": "/admin/login", "method": "POST"}, {"token_prefix": admin_token[:10] + "..."})

        # 1. 样品单翻译提交
        _call_admin_api(session, base_url, "/admin/samplesSubmitPurchase",
                        {"order_sn": order_sn, "warehouse_city": int(variables.get("warehouse_city") or 2)},
                        timeout, admin_token, variables, log, "samplesSubmitPurchase")

        # 2. 样品单开始确认
        _call_admin_api(session, base_url, "/admin/samplesStartConfirm",
                        {"order_sn": order_sn},
                        timeout, admin_token, variables, log, "samplesStartConfirm")

        # 3. 采购确认→业务（含报价信息）
        sku_info = _oem_build_sku_info_from_quote(order_sn, session, base_url, timeout, admin_token, variables)
        quote_info = {
            "inquiry_other_fee": str(variables.get("inquiry_other_fee", "0.00")),
            "inquiry_freight": str(variables.get("inquiry_freight", "0.00")),
            "inquiry_delivery_time": int(variables.get("inquiry_delivery_time", 0)),
            "quote_other_fee": str(variables.get("quote_other_fee", "7")),
            "quote_freight": str(variables.get("quote_freight", "8")),
            "quote_delivery_time": str(variables.get("quote_delivery_time", "9")),
            "real_other_fee": str(variables.get("real_other_fee", "7")),
            "real_freight": str(variables.get("real_freight", "8")),
            "sku_info": sku_info,
        }
        _call_admin_api(session, base_url, "/admin/samplesConfirmed", {
            "order_sn": order_sn,
            "warehouse_city": int(variables.get("warehouse_city") or 2),
            "is_special_quote": bool(variables.get("is_special_quote", True)),
            "y_response": str(variables.get("y_response", "")),
            "quote_info": quote_info,
        }, timeout, admin_token, variables, log, "samplesConfirmed")

        # 4. 业务开始报价
        _call_admin_api(session, base_url, "/admin/samplesStartQuote",
                        {"order_sn": order_sn},
                        timeout, admin_token, variables, log, "samplesStartQuote")

        # 5. 报价给客户
        _call_admin_api(session, base_url, "/admin/samplesQuoteToUser",
                        {"order_sn": order_sn, "warehouse_city": int(variables.get("warehouse_city") or 2)},
                        timeout, admin_token, variables, log, "samplesQuoteToUser")

        summary = {"order_sn": order_sn, "reason": "样品单后台流程执行成功"}
        return _finish_named(OEM_SAMPLE_ADMIN_SCRIPT_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_SAMPLE_ADMIN_SCRIPT_NAME, log, False, {"reason": str(exc), "error": str(exc)})


# ─── OEM 样品单全流程（提出 + 后台管理）─────────────────────────────

OEM_SAMPLE_FULL_FLOW_NAME = "OEM样品单全流程"


def run_oem_sample_full_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 样品单全流程：提出样品单 → 翻译提交 → 确认 → 报价给客户。

    阶段：
      1. 提出样品单（前台登录 → 创建样品单）
      2. 翻译提交（后台登录 → samplesSubmitPurchase）
      3. 开始确认（samplesStartConfirm）
      4. 采购确认（samplesConfirmed → samplesStartQuote → samplesQuoteToUser）
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")
    warehouse_city = int(variables.get("warehouse_city") or 2)
    inquiry_order_sn = str(variables.get("order_sn") or variables.get("inquiry_order_sn") or "").strip()
    sku_list_raw = variables.get("sku_list")
    sample_order_sn = str(variables.get("sample_order_sn") or "").strip()

    log: Dict[str, Any] = {
        "script": OEM_SAMPLE_FULL_FLOW_NAME,
        "mode": "oem_sample_full_flow",
        "base_url": base_url,
        "started_at": datetime.now(),
        "steps": [],
    }

    try:
        session = requests.Session()

        # ── 阶段 1：提出样品单 ──
        if not sample_order_sn and inquiry_order_sn:
            client_token, user_id, _ = _oem_client_login(session, base_url, variables, timeout)
            _step(log, "client_login", {"account": variables.get("account") or "12345678990"},
                  {"url": "/client/userLogin", "method": "POST"},
                  {"token": client_token[:16] + "..."})

            # 解析 SKU 列表
            sku_list = sku_list_raw
            if isinstance(sku_list, str):
                try:
                    sku_list = json.loads(sku_list) if sku_list.strip().startswith("[") else []
                except (json.JSONDecodeError, TypeError):
                    sku_list = []
            if not isinstance(sku_list, list):
                sku_list = []
            for item in sku_list:
                if isinstance(item, dict) and "option" not in item:
                    item["option"] = []

            gen_sample_sn = _oem_generate_sample_order_sn(variables, user_id, 1)
            log["generated_sample_order_sn"] = gen_sample_sn
            body = {
                "order_sn": gen_sample_sn,
                "inquiry_detail_id": variables.get("inquiry_detail_id") or "",
                "type": 1,
                "sku_list": sku_list if sku_list else [{"sku_id": 1993, "num": 1, "option": []}],
                "remark": "",
                "warehouse_city": warehouse_city,
            }
            headers = {
                "Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {client_token}",
                "Origin": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN),
                "Referer": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN).rstrip("/") + "/",
            }
            url = urljoin(base_url.rstrip("/") + "/", "/api/newOrder")
            payload = {}
            for attempt in range(3):
                try:
                    resp = session.post(url, json=body, headers=headers, timeout=timeout)
                    payload = resp.json()
                    break
                except (requests.ConnectionError, requests.Timeout, ValueError):
                    if attempt < 2:
                        time.sleep(0.8 * (attempt + 1))
            else:
                raise RuntimeError("创建样品单请求失败")
            if not payload.get("success") or payload.get("code") not in (0, "0", None):
                raise RuntimeError(f"创建样品单失败: {_translate_oem_msg(payload.get('msg'))}")
            sample_order_sn = str(payload.get("data") or "")
            _step(log, "new_sample_order", payload, {"url": "/api/newOrder", "method": "POST"},
                  {"order_sn": sample_order_sn, "success": True})
            log["sample_order_sn"] = sample_order_sn
        else:
            log["sample_order_sn"] = sample_order_sn or inquiry_order_sn

        if not sample_order_sn:
            sample_order_sn = inquiry_order_sn
        log["order_sn"] = sample_order_sn

        # ── 阶段 2-5：后台管理流程 ──
        admin_token = _oem_admin_login(session, base_url, variables, timeout)
        _step(log, "admin_login", {}, {"url": "/admin/login", "method": "POST"}, {"token_prefix": admin_token[:10] + "..."})

        # 翻译提交
        _call_admin_api(session, base_url, "/admin/samplesSubmitPurchase",
                        {"order_sn": sample_order_sn, "warehouse_city": warehouse_city},
                        timeout, admin_token, variables, log, "samplesSubmitPurchase")

        # 开始确认
        _call_admin_api(session, base_url, "/admin/samplesStartConfirm",
                        {"order_sn": sample_order_sn},
                        timeout, admin_token, variables, log, "samplesStartConfirm")

        # 采购确认→业务
        sku_info = _oem_build_sku_info_from_quote(sample_order_sn, session, base_url, timeout, admin_token, variables)
        quote_info = {
            "inquiry_other_fee": str(variables.get("inquiry_other_fee", "0.00")),
            "inquiry_freight": str(variables.get("inquiry_freight", "0.00")),
            "inquiry_delivery_time": int(variables.get("inquiry_delivery_time", 0)),
            "quote_other_fee": str(variables.get("quote_other_fee", "7")),
            "quote_freight": str(variables.get("quote_freight", "8")),
            "quote_delivery_time": str(variables.get("quote_delivery_time", "9")),
            "real_other_fee": str(variables.get("real_other_fee", "7")),
            "real_freight": str(variables.get("real_freight", "8")),
            "sku_info": sku_info,
        }
        _call_admin_api(session, base_url, "/admin/samplesConfirmed", {
            "order_sn": sample_order_sn, "warehouse_city": warehouse_city,
            "is_special_quote": bool(variables.get("is_special_quote", True)),
            "y_response": str(variables.get("y_response", "")),
            "quote_info": quote_info,
        }, timeout, admin_token, variables, log, "samplesConfirmed")

        # 业务开始报价
        _call_admin_api(session, base_url, "/admin/samplesStartQuote",
                        {"order_sn": sample_order_sn},
                        timeout, admin_token, variables, log, "samplesStartQuote")

        # 报价给客户
        _call_admin_api(session, base_url, "/admin/samplesQuoteToUser",
                        {"order_sn": sample_order_sn, "warehouse_city": warehouse_city},
                        timeout, admin_token, variables, log, "samplesQuoteToUser")

        # ── 6. 客户余额支付 ──
        client_token2, _, _ = _oem_client_login(session, base_url, variables, timeout)
        pay_payload = _oem_post_json(
            session, base_url, "/api/balancePayOrder",
            {"order_sn": sample_order_sn, "coupon_id": str(variables.get("coupon_id") or "")},
            timeout, token=client_token2, is_admin=False, variables=variables,
        )
        if not pay_payload.get("success") or pay_payload.get("code") not in (0, "0", None):
            _step(log, "balancePayOrder", pay_payload, {"url": "/api/balancePayOrder", "method": "POST"})
            raise RuntimeError(f"余额支付失败: {_translate_oem_msg(pay_payload.get('msg'))}")
        serial_number = str((pay_payload.get("data") or {}).get("serial_number") or "")
        _step(log, "balancePayOrder", pay_payload, {"url": "/api/balancePayOrder", "method": "POST"},
              {"serial_number": serial_number, "success": True})

        # ── 7. 后台开始采购 ──
        _call_admin_api(session, base_url, "/admin/samplesStartPurchase",
                        {"order_sn": sample_order_sn},
                        timeout, admin_token, variables, log, "samplesStartPurchase")

        # ── 8. 采购提交物流号 ──
        _call_admin_api(session, base_url, "/admin/samplesDispatch", {
            "order_sn": sample_order_sn,
            "express_id": int(variables.get("express_id") or 1039),
            "express_no": str(variables.get("express_no") or sample_order_sn[-6:] or "000000"),
            "express_remark": str(variables.get("express_remark") or ""),
        }, timeout, admin_token, variables, log, "samplesDispatch")

        # ── 9. 核查签收 ──
        _call_admin_api(session, base_url, "/admin/orderSign",
                        {"order_sn": sample_order_sn},
                        timeout, admin_token, variables, log, "orderSign")

        # ── 10. 开始核查货物 ──
        _call_admin_api(session, base_url, "/admin/checkStart",
                        {"order_sn": sample_order_sn},
                        timeout, admin_token, variables, log, "checkStart")

        # ── 11. 提交验货报告 ──
        report_images_raw = variables.get("check_report_images", "")
        report_images = [u.strip() for u in report_images_raw.replace("\n", ",").split(",") if u.strip()]
        if report_images:
            check_body = {
                "order_sn": sample_order_sn,
                "samples_report_video": [],
                "samples_report_image": [],
                "video": [],
                "image": report_images,
                "remark": str(variables.get("check_report_remark", "")),
            }
            _call_admin_api(session, base_url, "/admin/checkReport",
                            check_body, timeout, admin_token, variables, log, "checkReport")

        # ── 12. 获取验货明细 ──
        try:
            check_detail_resp = _call_admin_api(session, base_url, "/admin/checkDetail",
                                                {"order_sn": sample_order_sn},
                                                timeout, admin_token, variables, log, "checkDetail")
        except RuntimeError:
            check_detail_resp = {"data": None}
        check_detail_data = check_detail_resp.get("data") if isinstance(check_detail_resp, dict) else None

        # ── 13. 验货完成提交 ──
        check_list = []
        if check_detail_data and isinstance(check_detail_data, list):
            for item in check_detail_data:
                check_list.append({
                    "id": item.get("id", 0),
                    "check_id": item.get("check_id", 0),
                    "sku_tr": str(item.get("sku_tr", "")),
                    "sku": str(item.get("sku", "")),
                    "sku_image": str(item.get("sku_image", "")),
                    "num": item.get("num", 1),
                    "price": str(item.get("price", "0.00")),
                    "option": item.get("option", []),
                    "check_num": str(item.get("num", 1)),
                    "weight": str(item.get("weight", "1")),
                    "size": str(item.get("size", "0")),
                    "length": item.get("length", 1),
                    "width": item.get("width", 1),
                    "height": item.get("height", 1),
                    "possible_num": item.get("num", 1),
                    "storage_num": 0,
                    "shelves_num": 0,
                    "wait_inspect_num": item.get("num", 1),
                    "inspect_num": item.get("num", 1),
                    "bad_num": 0,
                    "good_num": item.get("num", 1),
                    "keep_sample_num": int(variables.get("keep_sample_num", 0)),
                    "keep_sample_possible_num": int(variables.get("keep_sample_possible_num", 0)),
                    "keep_sample_shelves_num": 0,
                    "warehouse_shelves": [],
                    "after_sale_num": 0,
                    "shelve_num": item.get("num", 1),
                    "checked_listing": True,
                })
        if check_list:
            _call_admin_api(session, base_url, "/admin/checkComplete",
                            {"order_sn": sample_order_sn, "check_list": check_list},
                            timeout, admin_token, variables, log, "checkComplete")

        # ── 14. 业务提交验货报告给客户 ──
        _call_admin_api(session, base_url, "/admin/samplesCheckRaise",
                        {"order_sn": sample_order_sn},
                        timeout, admin_token, variables, log, "samplesCheckRaise")

        # ── 15. 核查上架 ──
        try:
            shelve_detail_resp = _call_admin_api(session, base_url, "/admin/checkDetail",
                                                 {"order_sn": sample_order_sn},
                                                 timeout, admin_token, variables, log, "checkDetail-shelve")
        except RuntimeError:
            shelve_detail_resp = {"data": None}
        shelve_data = shelve_detail_resp.get("data") if isinstance(shelve_detail_resp, dict) else None
        shelve_info = []
        if shelve_data and isinstance(shelve_data, list):
            for item in shelve_data:
                shelve_info.append({
                    "id": item.get("id", 0),
                    "check_id": item.get("check_id", 0),
                    "sku_tr": str(item.get("sku_tr", "")),
                    "sku": str(item.get("sku", "")),
                    "sku_image": str(item.get("sku_image", "")),
                    "num": item.get("num", 1),
                    "price": str(item.get("price", "0.00")),
                    "option": item.get("option", []),
                    "check_num": item.get("num", 1),
                    "weight": item.get("weight", 1),
                    "size": "1*1*1",
                    "length": 1,
                    "width": 1,
                    "height": 1,
                    "possible_num": item.get("num", 1),
                    "storage_num": 0,
                    "shelves_num": 0,
                    "wait_inspect_num": item.get("num", 1),
                    "inspect_num": item.get("num", 1),
                    "bad_num": 0,
                    "good_num": item.get("num", 1),
                    "keep_sample_num": int(variables.get("keep_sample_num", 0)),
                    "keep_sample_possible_num": int(variables.get("keep_sample_possible_num", 0)),
                    "keep_sample_shelves_num": 0,
                    "warehouse_shelves": [],
                    "after_sale_num": 0,
                    "shelve_num": item.get("num", 1),
                    "checked_listing": True,
                })
        if shelve_info:
            _call_admin_api(session, base_url, "/admin/orderShelve", {
                "order_sn": sample_order_sn,
                "shelve_info": shelve_info,
                "warehouse_city": warehouse_city,
            }, timeout, admin_token, variables, log, "orderShelve")

        summary = {"order_sn": sample_order_sn, "serial_number": serial_number, "reason": "样品单全流程执行成功"}
        return _finish_named(OEM_SAMPLE_FULL_FLOW_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_SAMPLE_FULL_FLOW_NAME, log, False, {"reason": str(exc), "error": str(exc)})


# ─── OEM 大货单下单 ────────────────────────────────────────────

OEM_BULK_ORDER_NAME = "OEM大货单下单"


def _oem_query_option_list(
    session: requests.Session, base_url: str, token: str, timeout: int, variables: Dict[str, Any]
) -> list:
    """查询 OEM 大货单可选 option 列表（POST /common/common/optionList，空 body）。"""
    payload = _oem_post_json(
        session, base_url, "/common/common/optionList", {}, timeout,
        token=token, is_admin=False, variables=variables,
    )
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # 兼容 {list: [...]} 结构
        inner = data.get("list") or data.get("option_list") or []
        if isinstance(inner, list):
            return inner
    return []


def _oem_generate_large_order_sn(order_sn: str, user_id: str) -> str:
    """按 OEM 前端规则生成大货单号：D{timestamp}-{user_id}-{type}
    其中 type 从询价单号后缀提取（如 OEM、ODM），无法提取时默认为 OEM。
    """
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    type_suffix = "OEM"
    parts = str(order_sn).strip().rsplit("-", 1)
    if len(parts) == 2 and parts[1]:
        type_suffix = parts[1].upper()
    uid = str(user_id) if user_id else "0"
    return f"D{ts}-{uid}-{type_suffix}"


def _oem_order_preview(
    session: requests.Session, base_url: str, token: str,
    detail_id: str, timeout: int, variables: Dict[str, Any], large_order_sn: str = "",
) -> Dict[str, Any]:
    """大货单订单预览（POST /api/orderPreviews，type=2）。"""
    body = {"detail_id": str(detail_id), "type": 2, "large_order_sn": large_order_sn or ""}
    payload = _oem_post_json(
        session, base_url, "/api/orderPreviews", body, timeout,
        token=token, is_admin=False, variables=variables,
    )
    return payload.get("data") if isinstance(payload.get("data"), dict) else {}


def _oem_edit_sku_image(
    session: requests.Session, base_url: str, token: str,
    goods_sku_id: int, sku_image: str, timeout: int, variables: Dict[str, Any],
) -> Dict[str, Any]:
    """编辑 SKU 图片（POST /api/editSkuImage）。"""
    body = {"goods_sku_id": int(goods_sku_id), "sku_image": sku_image}
    payload = _oem_post_json(
        session, base_url, "/api/editSkuImage", body, timeout,
        token=token, is_admin=False, variables=variables,
    )
    return payload


def _oem_create_new_order(
    session: requests.Session, base_url: str, token: str,
    body: Dict[str, Any], timeout: int, variables: Dict[str, Any],
) -> Dict[str, Any]:
    """创建大货单（POST /api/newOrder，type=2）。返回响应 data。"""
    payload = _oem_post_json(
        session, base_url, "/api/newOrder", body, timeout,
        token=token, is_admin=False, variables=variables,
    )
    if not isinstance(payload, dict):
        raise RuntimeError(f"创建大货单失败: 接口返回非 JSON 响应")
    # 兼容两种成功判定：有 success=true，或 code=0/"0"
    is_success = payload.get("success") is True or payload.get("code") in (0, "0")
    if not is_success:
        raise RuntimeError(
            f"创建大货单失败: code={payload.get('code')} msg={payload.get('msg')} "
            f"data={json.dumps(payload.get('data'), ensure_ascii=False)[:500] if payload.get('data') else 'null'}"
        )
    return payload.get("data") if isinstance(payload.get("data"), dict) else (payload or {})


def _oem_build_option_for_sku(
    option_template: list, num: int, large_price: str = "",
) -> list:
    """根据 option 模板和购买数量，生成该 SKU 的 option 数组。
    全部 option 默认 checked=true；num 跟随 SKU 数量（拍照类 price_type=0 固定 1）。
    large_price 为 SKU 级别大货单价（来自 inquiryDetail.sku_detail.large_price），
    OEM 后端要求 option.large_price 必须为该 SKU 的大货单价，而非 option 自身的 price。
    """
    result = []
    for opt in option_template:
        if not isinstance(opt, dict):
            continue
        item = dict(opt)
        # 拍照类 option（id=9 或 name 含"拍照"）固定数量为 1
        opt_id = item.get("id")
        opt_name = str(item.get("name") or "")
        opt_num = 1 if (opt_id == 9 or "拍照" in opt_name) else num
        item["num"] = opt_num
        item["checked"] = True
        # large_price 优先用传入的 SKU 级别大货单价，否则回退到 option 自身 price
        if large_price:
            item["large_price"] = large_price
        elif "large_price" not in item:
            item["large_price"] = item.get("price") or "0.00"
        # price_range 默认空数组
        if "price_range" not in item:
            item["price_range"] = []
        result.append(item)
    return result


def _oem_build_warehouse_for_sku(
    sku_index: int, variables: Dict[str, Any], bulk_images: list,
) -> list:
    """根据变量和图片列表构造 warehouse 数组。
    默认 warehouse_type=1（FBA），FNSKU/ASIN 从变量取，image 取 bulk_images 对应索引。
    """
    warehouse_city = _as_int(variables.get("warehouse_city"), 1)
    # 仓库类型默认 1=FBA，可通过 warehouse_type_N 指定每个 SKU
    warehouse_type = _as_int(variables.get(f"warehouse_type_{sku_index}"), 1)
    fnsku = str(variables.get(f"fnsku_{sku_index}") or variables.get("fnsku") or "").strip()
    asin = str(variables.get(f"asin_{sku_index}") or variables.get("asin") or "").strip()
    image = ""
    if sku_index < len(bulk_images):
        image = bulk_images[sku_index]
    return [{
        "warehouse_type": warehouse_type,
        "FNSKU": fnsku,
        "ASIN": asin,
        "image": image,
    }]


def run_oem_bulk_order_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 大货单下单脚本：输入询价单号 → 查询报价 → 获取 option → 上传图片 → 创建大货单。

    阶段：
      1. 前台登录获取 token
      2. 查询报价详情（fetch_oem_full_quote）
      3. 查询 option 列表（/common/common/optionList）
      4. 订单预览（/api/orderPreviews，type=2）
      5. 上传图片到 OSS 并调用 editSkuImage（如提供 bulk_images）
      6. 创建大货单（POST /api/newOrder，type=2）
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")
    order_sn = str(variables.get("order_sn") or "").strip()

    log: Dict[str, Any] = {
        "script": OEM_BULK_ORDER_NAME,
        "mode": "oem_bulk_order",
        "base_url": base_url,
        "order_sn": order_sn,
        "started_at": datetime.now(),
        "steps": [],
    }

    if not order_sn:
        return _finish_named(OEM_BULK_ORDER_NAME, log, False,
                             {"reason": "缺少必填参数：询价单号 order_sn 不能为空"})

    try:
        session = requests.Session()

        # ── 阶段 1：前台登录 ──
        client_token, user_id, user_info_error = _oem_client_login(session, base_url, variables, timeout)

        # 按 OEM 前端规则生成大货单号（D{timestamp}-{user_id}-{type}）
        generated_large_order_sn = _oem_generate_large_order_sn(order_sn, user_id)

        _step(log, "client_login", {"account": variables.get("account") or "12345678990"},
              {"url": "/api/login + /api/userInfo", "method": "POST"},
              {"user_id": user_id, "has_token": bool(client_token),
               "generated_large_order_sn": generated_large_order_sn,
               "user_info_error": user_info_error})

        # ── 阶段 2：查询报价详情 ──
        quote_data = fetch_oem_full_quote(order_sn, variables)
        if not quote_data:
            return _finish_named(OEM_BULK_ORDER_NAME, log, False,
                                 {"reason": f"询价单 {order_sn} 无报价数据或接口返回异常"})
        detail_id = str(quote_data.get("detail_id") or variables.get("inquiry_detail_id") or "").strip()
        if not detail_id:
            records = quote_data.get("list") or []
            if records and isinstance(records[0], dict):
                detail_id = str(records[0].get("id") or "").strip()
        if not detail_id:
            return _finish_named(OEM_BULK_ORDER_NAME, log, False,
                                 {"reason": "未能从询价单解析出 detail_id"})

        quote_detail = quote_data.get("quote_detail") or {}
        large_info = quote_detail.get("large_info") or {}
        detail_list = quote_data.get("list") or []
        goods_name = (detail_list[0] if detail_list and isinstance(detail_list[0], dict) else {}).get("goods_name") or ""

        _step(log, "query_quote", {"order_sn": order_sn},
              {"url": "/api/inquiryDetail + /api/quoteDetail", "method": "POST"},
              {"detail_id": detail_id, "factory_count": len(detail_list),
               "has_large": bool(large_info), "goods_name": goods_name})

        # 从当前 detail_id 对应的 record 中提取每个 SKU 的大货单价
        # OEM 后端要求 option.large_price 必须为该 SKU 的大货单价（来自 sku_detail.large_price），
        # 而非 option 自身的 price，否则创建大货单会返回 code=10000
        sku_large_price_map: Dict[str, str] = {}
        for rec in detail_list:
            if not isinstance(rec, dict) or str(rec.get("id")) != str(detail_id):
                continue
            for sd in (rec.get("sku_detail") or []):
                if not isinstance(sd, dict):
                    continue
                gsid = sd.get("goods_sku_id") or sd.get("sku_id")
                lp = sd.get("large_price")
                if gsid is not None and lp is not None:
                    sku_large_price_map[str(gsid)] = str(lp)
            break

        # ── 阶段 3：查询 option 列表 ──
        option_list = _oem_query_option_list(session, base_url, client_token, timeout, variables)
        _step(log, "query_option_list", {"detail_id": detail_id},
              {"url": "/common/common/optionList", "method": "POST"},
              {"option_count": len(option_list)})

        # ── 阶段 4：订单预览（type=2 大货单） ──
        preview_data = _oem_order_preview(
            session, base_url, client_token, detail_id, timeout, variables,
            large_order_sn=generated_large_order_sn,
        )
        _step(log, "order_preview", {"detail_id": detail_id, "type": 2},
              {"url": "/api/orderPreviews", "method": "POST"},
              {"has_preview": bool(preview_data)})
        if not preview_data:
            return _finish_named(
                OEM_BULK_ORDER_NAME, log, False,
                {"reason": f"询价单 {order_sn}（detail_id={detail_id}）无大货报价信息，"
                           f"可能尚未完成报价或报价已过期。large_info 为空，无法创建大货单。"}
            )

        # 使用 OEM 前端规则生成的大货单号（而非 orderPreviews 预分配的）
        large_order_sn = generated_large_order_sn

        # ── 阶段 5：解析 SKU 列表 + 上传图片 + editSkuImage ──
        sku_list_raw = variables.get("sku_list")
        if isinstance(sku_list_raw, str) and sku_list_raw.strip().startswith("["):
            try:
                sku_list_raw = json.loads(sku_list_raw)
            except (json.JSONDecodeError, TypeError):
                sku_list_raw = []
        elif not isinstance(sku_list_raw, list):
            sku_list_raw = []
        if not sku_list_raw:
            return _finish_named(OEM_BULK_ORDER_NAME, log, False,
                                 {"reason": "sku_list 为空，请先在前端勾选要下单的 SKU"})

        # bulk_images 已是 OSS URL 列表（前端通过 /api/oem/upload-image 上传完成）
        bulk_images_raw = variables.get("bulk_images") or ""
        if isinstance(bulk_images_raw, list):
            bulk_images = [u for u in bulk_images_raw if u]
        else:
            bulk_images = [line.strip() for line in str(bulk_images_raw).splitlines() if line.strip()]

        # 为每个 SKU 构造 option + warehouse，并按需调用 editSkuImage
        sku_list_body = []
        for idx, item in enumerate(sku_list_raw):
            if not isinstance(item, dict):
                continue
            sku_id = item.get("sku_id") or item.get("goods_sku_id") or item.get("id")
            if sku_id is None:
                continue
            try:
                sku_id_int = int(sku_id)
            except (TypeError, ValueError):
                sku_id_int = sku_id
            num = _as_int(item.get("num"), 1)
            # 获取该 SKU 的大货单价（来自 sku_detail.large_price）
            sku_large_price = sku_large_price_map.get(str(sku_id_int)) or ""
            # option：优先用前端传入的（允许空列表，表示用户未勾选任何 option），否则用模板生成
            opt_input = item.get("option")
            if isinstance(opt_input, list):
                options = opt_input
                # 用 SKU 级别大货单价覆盖每个 option 的 large_price
                if sku_large_price:
                    for opt in options:
                        if isinstance(opt, dict):
                            opt["large_price"] = sku_large_price
            else:
                options = _oem_build_option_for_sku(option_list, num, large_price=sku_large_price)
            # warehouse：从变量+图片列表构造
            warehouses = _oem_build_warehouse_for_sku(idx, variables, bulk_images)
            # 若该 SKU 有对应图片，调用 editSkuImage
            sku_image_url = warehouses[0].get("image") if warehouses else ""
            if sku_image_url and isinstance(sku_id_int, int):
                try:
                    _oem_edit_sku_image(session, base_url, client_token, sku_id_int, sku_image_url, timeout, variables)
                    _step(log, "edit_sku_image", {"sku_id": sku_id_int, "sku_image": sku_image_url},
                          {"url": "/api/editSkuImage", "method": "POST"},
                          {"status": "ok"})
                except Exception as e:
                    _step(log, "edit_sku_image", {"sku_id": sku_id_int, "sku_image": sku_image_url},
                          {"url": "/api/editSkuImage", "method": "POST"},
                          {"status": "failed", "error": str(e)})
            sku_list_body.append({
                "sku_id": sku_id_int,
                "num": num,
                "option": options,
                "warehouse": warehouses,
            })

        if not sku_list_body:
            return _finish_named(OEM_BULK_ORDER_NAME, log, False,
                                 {"reason": "构造 SKU 下单列表失败，sku_list_body 为空"})

        # ── 阶段 6：创建大货单 ──
        remark = str(variables.get("remark") or "").strip()
        warehouse_city = _as_int(variables.get("warehouse_city"), 1)
        new_order_body = {
            "order_sn": large_order_sn,
            "inquiry_detail_id": detail_id,
            "type": 2,
            "sku_list": sku_list_body,
            "remark": remark,
            "warehouse_city": warehouse_city,
        }
        try:
            order_result = _oem_create_new_order(session, base_url, client_token, new_order_body, timeout, variables)
        except Exception as exc:
            # 将请求体附加到错误日志，方便排查
            log["new_order_request"] = new_order_body
            raise
        new_order_sn = ""
        if isinstance(order_result, dict):
            new_order_sn = str(order_result.get("order_sn") or order_result.get("large_order_sn") or order_result.get("sn") or order_result.get("orderSn") or "")
        elif isinstance(order_result, str):
            new_order_sn = order_result

        # 记录完整响应数据，便于排查 new_order_sn 为空的情况
        resp_detail = {}
        if isinstance(order_result, dict):
            resp_detail = {k: v for k, v in order_result.items() if k not in ("sku_list",)}
        _step(log, "create_bulk_order",
              {"order_sn": large_order_sn, "inquiry_sn": order_sn, "detail_id": detail_id, "sku_count": len(sku_list_body)},
              {"url": "/api/newOrder", "method": "POST", "type": 2},
              {"new_order_sn": new_order_sn, "sku_count": len(sku_list_body),
               "resp_keys": list(order_result.keys()) if isinstance(order_result, dict) else [],
               "resp_data": resp_detail})

        summary = {
            "order_sn": order_sn,
            "new_order_sn": new_order_sn,
            "detail_id": detail_id,
            "goods_name": goods_name,
            "factory_count": len(detail_list),
            "sku_count": len(sku_list_body),
            "option_count": len(option_list),
            "has_large": bool(large_info),
            "bulk_images_count": len(bulk_images),
            "warehouse_city": warehouse_city,
            "remark": remark,
        }
        return _finish_named(OEM_BULK_ORDER_NAME, log, True, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_BULK_ORDER_NAME, log, False,
                             {"reason": str(exc), "error": str(exc)})


# ─── OEM 样品单余额支付 ────────────────────────────────────────────

OEM_BALANCE_PAY_NAME = "OEM样品单余额支付"


def run_oem_sample_balance_pay_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 样品单余额支付：前台登录 → 余额支付。

    接口 POST /api/balancePayOrder
    可配置变量：
        - order_sn: 样品单号（必填）
        - coupon_id: 优惠券ID（可选）
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")
    order_sn = str(variables.get("order_sn") or "").strip()
    if not order_sn:
        return _finish_named(OEM_BALANCE_PAY_NAME, {}, False, {"reason": "缺少必填参数：order_sn"})

    log: Dict[str, Any] = {
        "script": OEM_BALANCE_PAY_NAME, "mode": "oem_balance_pay",
        "base_url": base_url, "order_sn": order_sn, "started_at": datetime.now(), "steps": [],
    }
    try:
        session = requests.Session()
        client_token, _, _ = _oem_client_login(session, base_url, variables, timeout)
        _step(log, "client_login", {"account": variables.get("account") or "12345678990"},
              {"url": "/client/userLogin", "method": "POST"}, {"token": client_token[:16] + "..."})

        payload = _oem_post_json(session, base_url, "/api/balancePayOrder",
                                 {"order_sn": order_sn, "coupon_id": str(variables.get("coupon_id") or "")},
                                 timeout, token=client_token, is_admin=False, variables=variables)
        if not payload.get("success") or payload.get("code") not in (0, "0", None):
            _step(log, "balancePayOrder", payload, {"url": "/api/balancePayOrder", "method": "POST"})
            return _finish_named(OEM_BALANCE_PAY_NAME, log, False,
                                 {"reason": f"余额支付失败: {_translate_oem_msg(payload.get('msg'))}", "error": payload.get("msg")})

        data = payload.get("data") or {}
        serial_number = str(data.get("serial_number") or "")
        _step(log, "balancePayOrder", payload, {"url": "/api/balancePayOrder", "method": "POST"},
              {"serial_number": serial_number, "success": True})
        summary = {"order_sn": order_sn, "serial_number": serial_number, "reason": "余额支付成功"}
        return _finish_named(OEM_BALANCE_PAY_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_BALANCE_PAY_NAME, log, False, {"reason": str(exc), "error": str(exc)})

