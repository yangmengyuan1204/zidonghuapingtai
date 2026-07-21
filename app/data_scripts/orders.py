from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'Dict',
    'Env',
    'ORDER_SCRIPT_NAME',
    'OrderedDict',
    'ThreadPoolExecutor',
    'Tuple',
    '_api_path',
    '_api_success',
    '_apply_order_options_to_items',
    '_as_bool',
    '_as_int',
    '_call_with_retry',
    '_checkpoint_requested',
    '_configure_client_api_paths',
    '_edit_cart_items_for_order',
    '_extract_order_sn',
    '_fetch_order_option_catalog',
    '_finish_named',
    '_flatten_cart_goods',
    '_normalize_order_option_counts',
    '_order_fields',
    '_order_item_brief',
    '_parse_order_max_limit',
    '_paused_summary',
    '_payload_brief',
    '_public_order_options',
    '_run_backend_order_flow',
    '_runtime_from_variables',
    '_select_cart_items',
    '_select_cart_items_by_shop',
    '_translate_order_msg',
    'bulk_cart',
    'datetime',
    'ensure_report_dirs',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl_run_order_quote_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
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


def run_order_quote_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_order_quote_script(env, variables)


def inspect_order_options(env: Env, variables: Dict[str, Any] | None = None) -> Dict[str, Any]:
    _sync_compat_globals()
    values = dict(variables or {})
    runtime = _runtime_from_variables(values)
    log: Dict[str, Any] = {"script": "查询订单附加服务", "read_only": True}
    if runtime:
        client, _base_url, _timeout, _token, _cached = runtime.client(env, values, log=log)
    else:
        base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
        timeout = _as_int(values.get("timeout"), env.timeout or 25)
        client = bulk_cart.RakumartClient(base_url, timeout)
        _configure_client_api_paths(client, values)
        _call_with_retry(
            "client login",
            lambda: client.login(
                str(values.get("account") or ""),
                str(values.get("password") or ""),
                str(values.get("client_tool") or "1"),
            ),
        )
    catalog, _payload, path = _fetch_order_option_catalog(client, values)
    return {"path": path, "options": _public_order_options(catalog), "count": len(catalog)}
