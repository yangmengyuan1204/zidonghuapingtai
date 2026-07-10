from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'Dict',
    'Env',
    'Tuple',
    'WAREHOUSE_DELIVERY_SCRIPT_NAME',
    '_api_path',
    '_api_success',
    '_as_bool',
    '_as_float',
    '_as_int',
    '_call_with_retry',
    '_checkpoint_requested',
    '_client_login_inputs',
    '_configure_client_api_paths',
    '_extract_porder_sn',
    '_finish_named',
    '_finish_paused',
    '_nested_rows',
    '_payload_brief',
    '_porder_create_fields_for_items',
    '_porder_sn',
    '_run_backend_porder_flow',
    '_run_order_tail_payment_if_needed',
    '_runtime_from_variables',
    '_select_warehouse_items',
    '_unique_list',
    '_warehouse_candidate_paths',
    '_warehouse_item_brief',
    '_warehouse_item_id',
    '_warehouse_list_fields',
    '_warehouse_requested_order_detail_ids',
    '_warehouse_sendable_num',
    '_warehouse_sku_id',
    'bulk_cart',
    'datetime',
    'ensure_report_dirs',
    'time',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl_run_warehouse_delivery_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
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
        explicit_warehouse_sku_count = any(
            variables.get(key) not in (None, "")
            for key in ("warehouse_sku_count", "porder_sku_count", "sku_count")
        )
        if requested_ids and len(requested_ids) > warehouse_sku_count and not explicit_warehouse_sku_count:
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


def run_warehouse_delivery_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_warehouse_delivery_script(env, variables)
