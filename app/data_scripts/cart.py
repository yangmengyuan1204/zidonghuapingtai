from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'Dict',
    'Env',
    'KEYWORDS',
    'PREFERRED_KEYWORDS',
    'SCRIPT_NAME',
    'Tuple',
    '_api_path',
    '_api_success',
    '_as_bool',
    '_as_float',
    '_as_int',
    '_as_list',
    '_call_with_retry',
    '_configure_client_api_paths',
    '_finish',
    '_item_brief',
    '_quantity_cycle',
    '_runtime_from_variables',
    '_unique_list',
    '_verify_cart_contains_items',
    'bulk_cart',
    'datetime',
    'ensure_report_dirs',
    'random',
    'time',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl_run_shopping_cart_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
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


def run_shopping_cart_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_shopping_cart_script(env, variables)
