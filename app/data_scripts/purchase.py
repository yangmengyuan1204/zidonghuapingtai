from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'BALANCE_PAYMENT_SCRIPT_NAME',
    'DIRECT_BOX_TO_SHELF_SCRIPT_NAME',
    'Dict',
    'Env',
    'ORDER_SCRIPT_NAME',
    'PURCHASE_TO_SHELF_SCRIPT_NAME',
    'Tuple',
    '_admin_login',
    '_admin_rows_from_payload',
    '_admin_session_from',
    '_api_path',
    '_api_success',
    '_as_bool',
    '_as_float',
    '_as_int',
    '_checkpoint_requested',
    '_direct_box_allocations',
    '_direct_box_configs',
    '_direct_box_counts',
    '_direct_box_id',
    '_direct_box_order_sn',
    '_direct_box_prepare_to_checking',
    '_direct_box_rows',
    '_direct_box_sort_key',
    '_direct_box_units',
    '_finance_purchase_brief',
    '_finish_named',
    '_finish_paused',
    '_first_preview_user_id',
    '_flatten_follow_items',
    '_flatten_purchase_items',
    '_follow_list_fields',
    '_item_up_num',
    '_items_already_checking',
    '_order_purchase_id',
    '_payload_brief',
    '_post_admin_form',
    '_post_admin_urlencoded',
    '_preview_items',
    '_preview_rows_from_payload',
    '_purchase_item_brief',
    '_purchase_item_id',
    '_purchase_list_fields',
    '_purchase_order_detail_id',
    '_purchase_save_rows',
    '_purchase_timestamp_no',
    '_purchase_wait_pay_fields',
    '_purchase_wait_pay_rows',
    '_run_order_tail_payment_if_needed',
    '_select_grid_from_payload',
    '_select_purchase_items',
    '_select_purchase_wait_pay',
    '_step',
    '_unique_list',
    '_unique_values',
    '_verify_purchase_to_shelf_completed',
    'bulk_cart',
    'datetime',
    'ensure_report_dirs',
    'json',
    'run_balance_payment_script',
    'run_order_quote_script',
    'run_purchase_to_shelf_script',
    'time',
    'write_allure_result',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl_run_purchase_to_shelf_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
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


def _impl_run_purchase_to_shelf_chain(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
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


def _impl_run_direct_box_to_shelf_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
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


def run_purchase_to_shelf_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_purchase_to_shelf_script(env, variables)


def run_purchase_to_shelf_chain(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_purchase_to_shelf_chain(env, variables)


def run_direct_box_to_shelf_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_direct_box_to_shelf_script(env, variables)
