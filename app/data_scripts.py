import copy
from collections import OrderedDict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import random
import time
from typing import Any, Dict, Tuple
from urllib.parse import urljoin

import requests

from .executors import ensure_report_dirs, write_allure_result
from .models import Env
from .vendor import piliangtianjiagouwuche as bulk_cart


SCRIPT_NAME = "\u5546\u54c1\u8d2d\u7269\u8f66"
ORDER_SCRIPT_NAME = "\u8ba2\u5355\u62a5\u4ef7"
BALANCE_PAYMENT_SCRIPT_NAME = "\u4f59\u989d\u652f\u4ed8"
BANK_PAYMENT_SCRIPT_NAME = "\u94f6\u884c\u652f\u4ed8"
PURCHASE_TO_SHELF_SCRIPT_NAME = "\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6"
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


def _finish_named(script_name: str, log: Dict[str, Any], passed: bool, summary: Dict[str, Any]) -> Tuple[bool, str, str, Dict[str, Any]]:
    log["summary"] = summary
    log["finished_at"] = datetime.now()
    log_text = json.dumps(log, ensure_ascii=False, indent=2, default=str)
    report_path = write_allure_result(script_name, "data_script", passed, log_text)
    return passed, log_text, report_path, summary


def _finish(log: Dict[str, Any], passed: bool, summary: Dict[str, Any]) -> Tuple[bool, str, str, Dict[str, Any]]:
    return _finish_named(SCRIPT_NAME, log, passed, summary)


def run_shopping_cart_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
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

    session = requests.Session()
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
    data = item.to_dict() if hasattr(item, "to_dict") else {}
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
    detail_workers = _as_int(variables.get("detail_workers"), 4)
    quantities = _quantity_cycle(variables.get("quantities"))
    allow_fallback_sku = not _as_bool(variables.get("no_fallback_sku"), False)
    strict_shop_count = _as_bool(variables.get("strict_shop_count") or variables.get("strict"), False)

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
        "started_at": datetime.now(),
        "shops": [],
        "batches": [],
    }

    try:
        client = bulk_cart.RakumartClient(base_url, timeout)
        _configure_client_api_paths(client, variables)
        token = client.login(account, password, client_tool)
        log["login"] = {"success": True, "account": account, "client_tool": client_tool, "token_extracted": bool(token)}

        shops = bulk_cart.collect_items(
            client=client,
            keyword=keyword,
            shop_type=shop_type,
            target_shops=target_shops,
            per_shop=per_shop,
            page_size=page_size,
            max_pages=max_pages,
            sleep_seconds=sleep_seconds,
            quantity_cycle=quantities,
            allow_fallback_sku=allow_fallback_sku,
            detail_workers=max(1, detail_workers),
        )
        items = bulk_cart.flatten_ready_shops(shops, target_shops, per_shop)
        ready_shops = len(items) // per_shop if per_shop else 0
        expected_total = target_shops * per_shop

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
        }

        if not items:
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
                },
            )

        added_total = 0
        failed_batches = []
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
                added_total += len(batch)
            log["batches"].append(batch_log)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        passed = added_total > 0 and not failed_batches and (ready_shops >= target_shops or not strict_shop_count)
        summary = {
            "keyword": keyword,
            "shop_type": shop_type,
            "target_shops": target_shops,
            "per_shop": per_shop,
            "ready_shops": ready_shops,
            "expected_total": expected_total,
            "available_expected_total": ready_shops * per_shop,
            "added_total": added_total,
            "failed_batches": failed_batches,
            "strict_shop_count": strict_shop_count,
        }
        if not passed:
            if failed_batches:
                summary["reason"] = "\u6709\u52a0\u8d2d\u6279\u6b21\u5931\u8d25"
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
                time.sleep(delay * (attempt + 1))
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


def _admin_login(
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
    quote_price = _decimal_text(variables.get("quote_unit_price") or variables.get("confirm_price") or "10")
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


def _prepare_offer_data(order_data: Dict[str, Any], variables: Dict[str, Any], item_quantity: int) -> Dict[str, Any]:
    prepared = copy.deepcopy(order_data)
    quote_price = _decimal_text(variables.get("quote_unit_price") or variables.get("offer_price") or "10")
    offer_freight = _decimal_text(variables.get("offer_freight") or variables.get("confirm_freight") or "5")
    prepared["other_price"] = _decimal_text(variables.get("other_price") or prepared.get("other_price") or "0")
    prepared["other_price_remark"] = str(variables.get("other_price_remark") or prepared.get("other_price_remark") or "")
    prepared["y_reply"] = str(variables.get("y_reply") or prepared.get("y_reply") or "")
    prepared["y_remark"] = str(variables.get("offer_remark") or prepared.get("y_remark") or "自动化业务报价")
    prepared["predict_logistics_price"] = _decimal_text(variables.get("predict_logistics_price") or prepared.get("predict_logistics_price") or "0")
    prepared["order_part_pay"] = _as_int(variables.get("order_part_pay"), 0)
    details = prepared.get("order_detail")
    if isinstance(details, list):
        for detail in details:
            if not isinstance(detail, dict):
                continue
            quantity = _as_int(detail.get("confirm_num") or detail.get("num") or item_quantity, item_quantity)
            detail["confirm_num"] = str(quantity)
            detail["confirm_price"] = quote_price
            detail["confirm_dicker_price"] = quote_price
            detail["offer_num"] = quantity
            detail["offer_price"] = quote_price
            detail["offer_freight"] = offer_freight
            detail["offer_total"] = _money_total(quantity, quote_price, offer_freight)
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
    session = requests.Session()

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

    _, after_translate = _order_detail_data(session, base_url, variables, order_sn, timeout, retries=2)
    backend_log["detail_after_translate"] = _admin_detail_brief(after_translate)

    confirm_source = after_translate or translate_data
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

    offer_source = after_confirm or confirm_source
    offer_data = _prepare_offer_data(offer_source, variables, item_quantity)
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

    _, after_offer = _order_detail_data(session, base_url, variables, order_sn, timeout, retries=1)
    backend_log["detail_after_offer"] = _admin_detail_brief(after_offer)
    return True, {
        "backend_passed": True,
        "backend_steps": ["login", "detail", "translate", "confirm", "offer"],
        "quote_unit_price": _decimal_text(variables.get("quote_unit_price") or "10"),
        "backend_status": after_offer.get("status") if after_offer else None,
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
    account = str(variables.get("account") or "").strip()
    password = str(variables.get("password") or "").strip()
    client_tool = str(variables.get("client_tool") or "1").strip()
    if client_tool == "2" and not _as_bool(variables.get("allow_h5_client_tool"), False):
        client_tool = "1"
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


def _apply_extra_fields(fields: OrderedDict[str, Any], extra_fields: Any) -> OrderedDict[str, Any]:
    if isinstance(extra_fields, dict):
        for key, value in extra_fields.items():
            if key and value is not None:
                fields[str(key)] = value
    return fields


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
        "pay_amount": row.get("pay_amount"),
        "amount": row.get("amount"),
        "bill_method": row.get("bill_method"),
        "predict_arrival_at": row.get("predict_arrival_at"),
        "created_at": row.get("created_at"),
        "status": row.get("status"),
    }


def _select_finance_bill(rows: list[Dict[str, Any]], serial_number: str, order_sn: str) -> Dict[str, Any] | None:
    for row in rows:
        if serial_number and str(row.get("serial_number") or "") == serial_number:
            return row
    for row in rows:
        if order_sn and str(row.get("order_sn") or "") == order_sn:
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
        "order_sn": item.get("_order_sn") or item.get("order_sn"),
        "purchase_no": item.get("purchase_no"),
        "status": item.get("status"),
        "statusName": _purchase_status_name(item),
        "goods_id": detail.get("goods_id") or item.get("goods_id"),
        "confirm_num": detail.get("confirm_num") or detail.get("num") or item.get("num"),
    }


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
        session = requests.Session()
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

        up_data = []
        for item in preview_items:
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
            "order_purchase_id": purchase_ids,
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
            "selected_count": len(purchase_items),
            "purchase_ids": purchase_ids,
            "grid_id": selected_grid.get("id"),
            "grid_number": selected_grid.get("grid_number"),
            "storage_count": len(up_data),
            "storage_passed": passed,
        }
        if not passed:
            summary["reason"] = str(storage_payload.get("msg") or storage_payload.get("data") or "\u4e0a\u67b6\u5165\u5e93\u5931\u8d25")
        return _finish_named(PURCHASE_TO_SHELF_SCRIPT_NAME, log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            PURCHASE_TO_SHELF_SCRIPT_NAME,
            log,
            False,
            {"order_sn": order_sn, "purchase_no": purchase_no, "error": str(exc)},
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
                session = requests.Session()
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
    item_quantity = _as_int(variables.get("order_item_num") or variables.get("num"), 10)
    price_cut = str(variables.get("priceCut") or variables.get("price_cut") or "0")
    logistics_id = str(variables.get("logistics_id") or "1")
    client_remark = str(variables.get("client_remark") or "\u81ea\u52a8\u5316\u63d0\u51fa\u8ba2\u5355")
    requested_type = str(variables.get("create_type") or "send").strip().lower()
    submit_order = requested_type != "save" and _as_bool(variables.get("submit_order"), True)
    seed_order_sn = str(variables.get("order_sn") or "").strip()
    run_backend_flow = submit_order and _as_bool(variables.get("run_backend_flow"), True)
    skip_create_order = _as_bool(variables.get("skip_create_order") or variables.get("backend_only"), False)

    log: Dict[str, Any] = {
        "script": ORDER_SCRIPT_NAME,
        "mode": "backend_only" if skip_create_order else "cart_to_order_and_backend_quote",
        "base_url": base_url,
        "item_count": item_count,
        "item_quantity": item_quantity,
        "price_cut": price_cut,
        "submit_order": submit_order,
        "run_backend_flow": run_backend_flow,
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

        client = bulk_cart.RakumartClient(base_url, timeout)
        _configure_client_api_paths(client, variables)
        token = _call_with_retry("client login", lambda: client.login(account, password, client_tool))
        log["login"] = {"success": True, "account": account, "client_tool": client_tool, "token_extracted": bool(token)}

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
        selected_items = _select_cart_items(cart_payload, item_count)
        log["cart_list"] = {
            **_payload_brief(cart_payload),
            "goods_count": len(cart_goods),
            "selected_count": len(selected_items),
        }
        log["selected_items"] = [_order_item_brief(item) for item in selected_items]
        if len(selected_items) < item_count:
            return _finish_named(
                ORDER_SCRIPT_NAME,
                log,
                False,
                {
                    "order_sn": "",
                    "selected_count": len(selected_items),
                    "expected_count": item_count,
                    "reason": "\u8d2d\u7269\u8f66\u53ef\u63d0\u5355\u5546\u54c1\u4e0d\u8db3",
                },
            )

        failed_edits = []
        for item in selected_items:
            edit_fields = _edit_cart_fields(item, item_quantity)
            edit_payload = _call_with_retry(
                "cart edit",
                lambda edit_fields=edit_fields: client.post_form(_api_path(variables, "client_cart_edit", "/client/cart.goodsCartEdit"), edit_fields),
            )
            edit_ok = _api_success(edit_payload)
            if edit_ok:
                item["num"] = item_quantity
            else:
                failed_edits.append(item.get("id"))
            log["edits"].append(
                {
                    "cart_id": item.get("id"),
                    "goods_id": item.get("goods_id"),
                    "num": item_quantity,
                    **_payload_brief(edit_payload),
                }
            )
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

        save_fields = _order_fields(selected_items, "save", seed_order_sn, item_quantity, logistics_id, client_remark)
        save_payload = _call_with_retry(
            "order save",
            lambda: client.post_form(_api_path(variables, "client_order_create", "/client/order.orderCreate"), save_fields),
        )
        order_sn = _extract_order_sn(save_payload) or seed_order_sn
        log["create"]["save"] = {**_payload_brief(save_payload), "order_sn": order_sn}
        if not _api_success(save_payload) or not order_sn:
            return _finish_named(
                ORDER_SCRIPT_NAME,
                log,
                False,
                {
                    "order_sn": order_sn,
                    "selected_count": len(selected_items),
                    "item_quantity": item_quantity,
                    "reason": "\u4e34\u65f6\u4fdd\u5b58\u8ba2\u5355\u5931\u8d25",
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
        }
        if not passed:
            summary["reason"] = "\u6b63\u5f0f\u63d0\u51fa\u8ba2\u5355\u5931\u8d25" if submit_order else "\u8ba2\u5355\u4fdd\u5b58\u5931\u8d25"
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
