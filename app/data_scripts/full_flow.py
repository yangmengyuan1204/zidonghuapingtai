from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'BALANCE_PAYMENT_SCRIPT_NAME',
    'BANK_PAYMENT_SCRIPT_NAME',
    'DataScriptRuntime',
    'Dict',
    'Env',
    'FULL_FLOW_COMPLETE_NODE',
    'FULL_FLOW_SCRIPT_NAME',
    'ORDER_SCRIPT_NAME',
    'POORDER_BALANCE_PAYMENT_SCRIPT_NAME',
    'POORDER_BANK_PAYMENT_SCRIPT_NAME',
    'PURCHASE_TO_SHELF_SCRIPT_NAME',
    'RESUME_ORDER_FLOW_SCRIPT_NAME',
    'RESUME_PORDER_FLOW_SCRIPT_NAME',
    'SCRIPT_NAME',
    'Tuple',
    'WAREHOUSE_DELIVERY_SCRIPT_NAME',
    '_as_bool',
    '_as_int',
    '_detect_resume_order_state',
    '_detect_resume_porder_state',
    '_full_flow_finish',
    '_full_flow_prepare_warehouse_counts',
    '_full_flow_record_step',
    '_full_flow_stop_reached',
    '_full_flow_update_shared',
    '_is_paused',
    '_order_part_pay_enabled',
    '_order_tail_partial_enabled',
    '_order_tail_partial_selected_values',
    '_payment_with_bank_fallback',
    '_purchase_timestamp_no',
    '_resume_flow_finish',
    '_resume_record_skipped',
    '_run_backend_order_flow_resume',
    '_run_backend_porder_flow_resume',
    '_stop_after_node',
    'bulk_cart',
    'datetime',
    'ensure_report_dirs',
    'run_order_quote_script',
    'run_purchase_to_shelf_script',
    'run_resume_order_flow_script',
    'run_resume_porder_flow_script',
    'run_shopping_cart_script',
    'run_warehouse_delivery_script',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _full_flow_part_pay_input_error(variables: Dict[str, Any]) -> str:
    if not _order_part_pay_enabled(variables) or not _order_tail_partial_enabled(variables):
        return ""
    _, selected_values = _order_tail_partial_selected_values(variables)
    return "" if selected_values else "按番尾款已启用，但未填写番序号"


def _emit_progress(callback: Any, node: str, status: str, next_node: str = "", **extra: Any) -> None:
    if callable(callback):
        callback(
            {
                "node": node,
                "status": status,
                "next_node": next_node,
                "updated_at": datetime.now().isoformat(),
                **extra,
            }
        )


def _call_with_progress(callback: Any, node: str, runner: Any) -> Any:
    _emit_progress(callback, node, "running")
    try:
        result = runner()
    except Exception as exc:
        _emit_progress(callback, node, "failed", reason=str(exc))
        raise
    passed = bool(result[0]) if isinstance(result, tuple) and result else False
    summary = result[3] if isinstance(result, tuple) and len(result) > 3 and isinstance(result[3], dict) else {}
    actual_node = str(summary.get("current_node") or summary.get("stopped_after_node") or node)
    _emit_progress(callback, actual_node, "completed" if passed else "failed")
    return result


def _impl_run_full_flow_script(
    env: Env,
    variables: Dict[str, Any] | None = None,
    progress_callback: Any = None,
) -> Tuple[bool, str, str, Dict[str, Any]]:
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
        return run_resume_porder_flow_script(env, variables, progress_callback=progress_callback)
    if resume_order_sn:
        variables["order_sn"] = resume_order_sn
        return run_resume_order_flow_script(env, variables, progress_callback=progress_callback)

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
    input_error = _full_flow_part_pay_input_error(variables)
    if input_error:
        log["input_validation"] = {"passed": False, "reason": input_error}
        return _full_flow_finish(log, False, "input_validation", reason=input_error)

    try:
        if _full_flow_stop_reached(variables, "shopping_cart"):
            cart_passed, cart_log, cart_report, cart_summary = _call_with_progress(
                progress_callback,
                "shopping_cart",
                lambda: run_shopping_cart_script(env, variables),
            )
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

        quote_passed, quote_log, quote_report, quote_summary = _call_with_progress(
            progress_callback,
            "order_offered",
            run_quote_attempt,
        )
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
            cart_passed, cart_log, cart_report, cart_summary = _call_with_progress(
                progress_callback,
                "shopping_cart",
                lambda: run_shopping_cart_script(env, cart_vars),
            )
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
            quote_passed, quote_log, quote_report, quote_summary = _call_with_progress(
                progress_callback,
                "order_offered",
                lambda: run_quote_attempt(retry_after_autofill=True),
            )
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
        pay_passed, pay_log, pay_report, pay_summary = _call_with_progress(
            progress_callback,
            "order_paid",
            lambda: _payment_with_bank_fallback(env, pay_vars, porder=False),
        )
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
        shelf_progress_node = stop_after if stop_after in {
            "pending_purchase",
            "purchase_no_saved",
            "purchase_wait_modify_price",
            "purchase_wait_pay",
            "purchase_paid",
            "checking_started",
            "shelf_stored",
        } else "shelf_stored"
        shelf_passed, shelf_log, shelf_report, shelf_summary = _call_with_progress(
            progress_callback,
            shelf_progress_node,
            lambda: run_purchase_to_shelf_script(env, shelf_vars),
        )
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
        delivery_progress_node = stop_after if stop_after in {
            "warehouse_delivery_created",
            "porder_translated",
            "porder_confirmed",
            "porder_wait_offer",
            "porder_offered",
        } else "porder_offered"
        delivery_passed, delivery_log, delivery_report, delivery_summary = _call_with_progress(
            progress_callback,
            delivery_progress_node,
            lambda: run_warehouse_delivery_script(env, delivery_vars),
        )
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
        porder_pay_passed, porder_pay_log, porder_pay_report, porder_pay_summary = _call_with_progress(
            progress_callback,
            "porder_paid",
            lambda: _payment_with_bank_fallback(env, porder_pay_vars, porder=True),
        )
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


def _impl_run_resume_order_flow_script(
    env: Env,
    variables: Dict[str, Any] | None = None,
    progress_callback: Any = None,
) -> Tuple[bool, str, str, Dict[str, Any]]:
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
                backend_node = stop_after if stop_after in {
                    "order_translated", "order_confirmed", "order_offered"
                } else "order_offered"
                backend_passed, backend_summary = _call_with_progress(
                    progress_callback,
                    backend_node,
                    lambda: _run_backend_order_flow_resume(
                        base_url,
                        timeout,
                        variables,
                        order_sn,
                        item_quantity,
                        log,
                        detect_summary.get("order_data") if isinstance(detect_summary.get("order_data"), dict) else {},
                    ),
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
            pay_passed, pay_log, pay_report, pay_summary = _call_with_progress(
                progress_callback,
                "order_paid",
                lambda: _payment_with_bank_fallback(env, pay_vars, porder=False),
            )
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
            shelf_progress_node = stop_after if stop_after in {
                "pending_purchase",
                "purchase_no_saved",
                "purchase_wait_modify_price",
                "purchase_wait_pay",
                "purchase_paid",
                "checking_started",
                "shelf_stored",
            } else "shelf_stored"
            shelf_passed, shelf_log, shelf_report, shelf_summary = _call_with_progress(
                progress_callback,
                shelf_progress_node,
                lambda: run_purchase_to_shelf_script(env, shelf_vars),
            )
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
        delivery_progress_node = stop_after if stop_after in {
            "warehouse_delivery_created",
            "porder_translated",
            "porder_confirmed",
            "porder_wait_offer",
            "porder_offered",
        } else "porder_offered"
        delivery_passed, delivery_log, delivery_report, delivery_summary = _call_with_progress(
            progress_callback,
            delivery_progress_node,
            lambda: run_warehouse_delivery_script(env, delivery_vars),
        )
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


def _impl_run_resume_porder_flow_script(
    env: Env,
    variables: Dict[str, Any] | None = None,
    progress_callback: Any = None,
) -> Tuple[bool, str, str, Dict[str, Any]]:
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
            backend_node = stop_after if stop_after in {
                "porder_translated", "porder_confirmed", "porder_wait_offer", "porder_offered"
            } else "porder_offered"
            backend_passed, backend_summary = _call_with_progress(
                progress_callback,
                backend_node,
                lambda: _run_backend_porder_flow_resume(
                    base_url, timeout, variables, porder_sn, log, detected_start_node,
                ),
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
        pay_passed, pay_log, pay_report, pay_summary = _call_with_progress(
            progress_callback,
            "porder_paid",
            lambda: _payment_with_bank_fallback(env, porder_pay_vars, porder=True),
        )
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


def run_full_flow_script(
    env: Env,
    variables: Dict[str, Any] | None = None,
    progress_callback: Any = None,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_full_flow_script(env, variables, progress_callback=progress_callback)


def run_resume_order_flow_script(
    env: Env,
    variables: Dict[str, Any] | None = None,
    progress_callback: Any = None,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_resume_order_flow_script(env, variables, progress_callback=progress_callback)


def run_resume_porder_flow_script(
    env: Env,
    variables: Dict[str, Any] | None = None,
    progress_callback: Any = None,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_resume_porder_flow_script(env, variables, progress_callback=progress_callback)
