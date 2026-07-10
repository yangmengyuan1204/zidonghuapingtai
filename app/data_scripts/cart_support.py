from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    'KEYWORDS',
    'ORDER_OPTION_NAME_FALLBACKS',
    'OrderedDict',
    'PREFERRED_KEYWORDS',
    'SCRIPT_NAME',
    'SHOP_TYPES',
    'SHOP_TYPE_ALIASES',
    'ThreadPoolExecutor',
    '_add_order_option_to_catalog',
    '_admin_session_from',
    '_api_path',
    '_api_paths',
    '_api_success',
    '_as_int',
    '_as_list',
    '_auth_form_fields',
    '_auth_headers',
    '_authed_client_with_token',
    '_call_with_retry',
    '_cart_item_matches',
    '_cart_item_quantity',
    '_cart_item_ready',
    '_cart_payload',
    '_cart_shop_key',
    '_cart_text',
    '_client_login_with_path',
    '_collect_order_option_catalog',
    '_configure_client_api_paths',
    '_edit_cart_fields',
    '_extract_token',
    '_finish',
    '_first_price',
    '_flatten_cart_goods',
    '_goods_items',
    '_item_brief',
    '_json_list',
    '_normalize_order_option_counts',
    '_order_option_catalog_from_options',
    '_order_option_items',
    '_order_option_key',
    '_order_option_label',
    '_order_option_list_path',
    '_order_text',
    '_payload_brief',
    '_post_form',
    '_public_order_options',
    '_response_brief',
    '_response_json',
    '_unique_list',
    'as_completed',
    'bulk_cart',
    'copy',
    'datetime',
    'ensure_report_dirs',
    'json',
    'random',
    'threading',
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


def _impl__legacy_run_shopping_cart_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
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


def _impl__as_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
        return parsed if parsed >= 0 else fallback
    except (TypeError, ValueError):
        return fallback


def _impl__as_bool(value: Any, fallback: bool = False) -> bool:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _impl__quantity_cycle(value: Any) -> list[int]:
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


def _impl__item_brief(item: Any) -> Dict[str, Any]:
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


def _impl__cart_text(data: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _impl__cart_item_matches(expected: Dict[str, Any], actual: Dict[str, Any]) -> bool:
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


def _impl__verify_cart_contains_items(cart_payload: Dict[str, Any], items: list[Any]) -> Dict[str, Any]:
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


def _impl__api_success(payload: Dict[str, Any]) -> bool:
    code = payload.get("code")
    success = payload.get("success")
    success_ok = success is True or str(success).strip().lower() == "true"
    return success_ok and code in (None, 0, "0")


def _impl__api_paths(variables: Dict[str, Any]) -> Dict[str, str]:
    paths = variables.get("api_paths")
    return paths if isinstance(paths, dict) else {}


def _impl__api_path(variables: Dict[str, Any], key: str, default: str) -> str:
    return str(_api_paths(variables).get(key) or variables.get(f"{key}_path") or default)


def _impl__client_login_with_path(client: Any, variables: Dict[str, Any], account: str, password: str, client_tool: str) -> str:
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


def _impl__configure_client_api_paths(client: Any, variables: Dict[str, Any]) -> None:
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


def _impl__payload_brief(payload: Dict[str, Any]) -> Dict[str, Any]:
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


def _impl__order_text(value: Any, fallback: str = "") -> str:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list, tuple)):
        return bulk_cart.json_text(value)
    return str(value)


def _impl__first_price(price_ranges: Any) -> str:
    if not isinstance(price_ranges, list) or not price_ranges:
        return ""
    first = price_ranges[0]
    if not isinstance(first, dict):
        return ""
    for key in ["price", "priceMin", "priceMax"]:
        if first.get(key) not in (None, ""):
            return str(first.get(key))
    return ""


def _impl__json_list(value: Any) -> list[Any]:
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


def _impl__order_option_items(value: Any) -> list[Dict[str, Any]]:
    return [item for item in _json_list(value) if isinstance(item, dict)]


def _impl__order_option_key(option: Dict[str, Any]) -> str:
    for key in ["id", "option_id", "value", "key", "name", "name_translate"]:
        value = option.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _impl__order_option_label(option: Dict[str, Any], key: str = "") -> str:
    option_id = str(option.get("id") or option.get("option_id") or "").strip()
    name = str(option.get("name") or "").strip()
    name_translate = str(option.get("name_translate") or "").strip()
    for candidate in [name, option_id, key]:
        if candidate and ORDER_OPTION_NAME_FALLBACKS.get(candidate):
            return ORDER_OPTION_NAME_FALLBACKS[candidate]
    return name or name_translate or key


def _impl__normalize_order_option_counts(value: Any) -> OrderedDict[str, int]:
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


def _impl__add_order_option_to_catalog(catalog: OrderedDict[str, Dict[str, Any]], option: Dict[str, Any]) -> None:
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


def _impl__order_option_catalog_from_options(options: Any) -> OrderedDict[str, Dict[str, Any]]:
    catalog: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    for option in _order_option_items(options):
        _add_order_option_to_catalog(catalog, option)
    return catalog


def _impl__collect_order_option_catalog(items: list[Dict[str, Any]]) -> OrderedDict[str, Dict[str, Any]]:
    catalog: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    for item in items:
        for option in _order_option_items(item.get("option")):
            _add_order_option_to_catalog(catalog, option)
    return catalog


def _impl__public_order_options(catalog: OrderedDict[str, Dict[str, Any]]) -> list[Dict[str, Any]]:
    return [
        {key: value for key, value in option.items() if key != "template"}
        for option in catalog.values()
    ]


def _impl__order_option_list_path(variables: Dict[str, Any]) -> str:
    return _api_path(variables, "client_order_option_list", "/client/order.optionList")


def _impl__fetch_order_option_catalog(client: Any, variables: Dict[str, Any]) -> tuple[OrderedDict[str, Dict[str, Any]], Dict[str, Any], str]:
    path = _order_option_list_path(variables)
    payload = _call_with_retry("order option list", lambda: client.post_form(path, {}))
    if not _api_success(payload):
        raise RuntimeError(f"读取订单 option 失败：{payload.get('msg') or payload.get('data') or payload}")
    options = payload.get("data")
    catalog = _order_option_catalog_from_options(options)
    if not catalog:
        raise RuntimeError("读取订单 option 失败：接口未返回可用 option")
    return catalog, payload, path


def _impl__apply_order_options_to_items(
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


def _impl__flatten_cart_goods(cart_payload: Dict[str, Any]) -> list[Dict[str, Any]]:
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


def _impl__cart_item_ready(item: Dict[str, Any]) -> bool:
    return item.get("id") not in (None, "") and item.get("goods_id") not in (None, "")


def _impl__select_cart_items(cart_payload: Dict[str, Any], item_count: int) -> list[Dict[str, Any]]:
    selected: list[Dict[str, Any]] = []
    for item in _flatten_cart_goods(cart_payload):
        if not _cart_item_ready(item):
            continue
        selected.append(item)
        if len(selected) >= item_count:
            break
    return selected


def _impl__cart_shop_key(item: Dict[str, Any]) -> str:
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


def _impl__select_cart_items_by_shop(
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


def _impl__order_item_brief(item: Dict[str, Any]) -> Dict[str, Any]:
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


def _impl__edit_cart_fields(item: Dict[str, Any], quantity: int) -> OrderedDict[str, Any]:
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


def _impl__cart_item_quantity(item: Dict[str, Any]) -> int | None:
    value = item.get("num")
    if value in (None, ""):
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _impl__authed_client_with_token(base_url: str, timeout: int, variables: Dict[str, Any], token: str) -> Any:
    client = bulk_cart.RakumartClient(base_url, timeout)
    _configure_client_api_paths(client, variables)
    if token:
        client.session.headers.update({"clienttoken": token})
    return client


def _impl__edit_cart_items_for_order(
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


_legacy_run_shopping_cart_script = _compat_wrapper(_impl__legacy_run_shopping_cart_script)
_as_float = _compat_wrapper(_impl__as_float)
_as_bool = _compat_wrapper(_impl__as_bool)
_quantity_cycle = _compat_wrapper(_impl__quantity_cycle)
_item_brief = _compat_wrapper(_impl__item_brief)
_cart_text = _compat_wrapper(_impl__cart_text)
_cart_item_matches = _compat_wrapper(_impl__cart_item_matches)
_verify_cart_contains_items = _compat_wrapper(_impl__verify_cart_contains_items)
_api_success = _compat_wrapper(_impl__api_success)
_api_paths = _compat_wrapper(_impl__api_paths)
_api_path = _compat_wrapper(_impl__api_path)
_client_login_with_path = _compat_wrapper(_impl__client_login_with_path)
_configure_client_api_paths = _compat_wrapper(_impl__configure_client_api_paths)
_payload_brief = _compat_wrapper(_impl__payload_brief)
_order_text = _compat_wrapper(_impl__order_text)
_first_price = _compat_wrapper(_impl__first_price)
_json_list = _compat_wrapper(_impl__json_list)
_order_option_items = _compat_wrapper(_impl__order_option_items)
_order_option_key = _compat_wrapper(_impl__order_option_key)
_order_option_label = _compat_wrapper(_impl__order_option_label)
_normalize_order_option_counts = _compat_wrapper(_impl__normalize_order_option_counts)
_add_order_option_to_catalog = _compat_wrapper(_impl__add_order_option_to_catalog)
_order_option_catalog_from_options = _compat_wrapper(_impl__order_option_catalog_from_options)
_collect_order_option_catalog = _compat_wrapper(_impl__collect_order_option_catalog)
_public_order_options = _compat_wrapper(_impl__public_order_options)
_order_option_list_path = _compat_wrapper(_impl__order_option_list_path)
_fetch_order_option_catalog = _compat_wrapper(_impl__fetch_order_option_catalog)
_apply_order_options_to_items = _compat_wrapper(_impl__apply_order_options_to_items)
_flatten_cart_goods = _compat_wrapper(_impl__flatten_cart_goods)
_cart_item_ready = _compat_wrapper(_impl__cart_item_ready)
_select_cart_items = _compat_wrapper(_impl__select_cart_items)
_cart_shop_key = _compat_wrapper(_impl__cart_shop_key)
_select_cart_items_by_shop = _compat_wrapper(_impl__select_cart_items_by_shop)
_order_item_brief = _compat_wrapper(_impl__order_item_brief)
_edit_cart_fields = _compat_wrapper(_impl__edit_cart_fields)
_cart_item_quantity = _compat_wrapper(_impl__cart_item_quantity)
_authed_client_with_token = _compat_wrapper(_impl__authed_client_with_token)
_edit_cart_items_for_order = _compat_wrapper(_impl__edit_cart_items_for_order)
