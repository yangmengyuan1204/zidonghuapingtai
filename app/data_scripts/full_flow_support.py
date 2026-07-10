from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    'BALANCE_INSUFFICIENT_MARKERS',
    'Decimal',
    'FULL_FLOW_COMPLETE_NODE',
    'FULL_FLOW_NODE_LABELS',
    'FULL_FLOW_NODE_SEQUENCE',
    'FULL_FLOW_SCRIPT_NAME',
    'FULL_FLOW_SHARED_KEYS',
    'InvalidOperation',
    'RESUME_ORDER_FLOW_SCRIPT_NAME',
    '_as_int',
    '_checkpoint_requested',
    '_direct_box_int',
    '_direct_box_text',
    '_finish_named',
    '_full_flow_node_results',
    '_full_flow_update_shared',
    '_item_up_num',
    '_looks_like_balance_insufficient',
    '_nested_rows',
    '_order_purchase_id',
    '_payment_with_bank_fallback',
    '_summary_text',
    'datetime',
    'json',
    'run_balance_payment_script',
    'run_bank_payment_script',
    'run_order_quote_script',
    'run_porder_balance_payment_script',
    'run_porder_bank_payment_script',
    'run_purchase_to_shelf_script',
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


def _impl__summary_text(*parts: Any) -> str:
    return json.dumps(parts, ensure_ascii=False, default=str).lower()


def _impl__looks_like_balance_insufficient(summary: Dict[str, Any], log_text: str = "") -> bool:
    text = _summary_text(summary, log_text)
    if any(marker.lower() in text for marker in BALANCE_INSUFFICIENT_MARKERS):
        return True
    return "\u4f59\u989d" in text and any(marker in text for marker in ["\u4e0d\u8db3", "\u4e0d\u591f", "\u4f4e\u4e8e"])


def _impl__payment_with_bank_fallback(
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


def _impl__direct_box_int(value: Any, fallback: int = 1) -> int:
    try:
        number = int(Decimal(str(value)))
        return number if number > 0 else fallback
    except (InvalidOperation, TypeError, ValueError):
        return fallback


def _impl__direct_box_text(value: Any, fallback: str) -> str:
    text = str(value if value not in (None, "") else fallback).strip()
    return text or fallback


def _impl__direct_box_configs(variables: Dict[str, Any], total_num: int = 1) -> list[Dict[str, Any]]:
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


def _impl__direct_box_rows(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
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


def _impl__direct_box_id(row: Dict[str, Any]) -> str:
    return str(row.get("id") or row.get("box_id") or "").strip()


def _impl__direct_box_sort_key(row: Dict[str, Any]) -> tuple[int, int]:
    return (_direct_box_int(row.get("box_no"), 999999), _direct_box_int(row.get("id"), 999999))


def _impl__direct_box_order_sn(rows: list[Dict[str, Any]], items: list[Dict[str, Any]], variables: Dict[str, Any]) -> str:
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


def _impl__direct_box_units(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    units: list[Dict[str, Any]] = []
    for item in items:
        order_purchase_id = _order_purchase_id(item)
        if order_purchase_id in (None, ""):
            continue
        units.append({"order_purchase_id": order_purchase_id, "num": _direct_box_int(_item_up_num(item), 1)})
    return units


def _impl__direct_box_counts(total_num: int, configs: list[Dict[str, Any]], box_count: int) -> list[int]:
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


def _impl__direct_box_allocations(units: list[Dict[str, Any]], counts: list[int]) -> list[list[Dict[str, Any]]]:
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


def _impl__direct_box_prepare_to_checking(env: Env, variables: Dict[str, Any], log: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
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


def _impl__full_flow_update_shared(shared: Dict[str, Any], summary: Dict[str, Any]) -> None:
    for key in FULL_FLOW_SHARED_KEYS:
        value = summary.get(key)
        if value not in (None, ""):
            shared[key] = value


def _impl__full_flow_record_step(
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


def _impl__full_flow_node_results(current_node: str, passed: bool, paused: bool) -> list[Dict[str, Any]]:
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


def _impl__full_flow_finish(
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


def _impl__resume_record_skipped(log: Dict[str, Any], nodes: list[str], reason: str) -> None:
    skipped = log.setdefault("skipped_nodes", [])
    for node in nodes:
        skipped.append({"node": node, "node_label": FULL_FLOW_NODE_LABELS.get(node, node), "reason": reason})


def _impl__resume_flow_finish(
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


def _impl__full_flow_stop_reached(variables: Dict[str, Any], node: str) -> bool:
    return _checkpoint_requested(variables, node)


def _impl__full_flow_prepare_warehouse_counts(variables: Dict[str, Any]) -> Dict[str, Any]:
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


_summary_text = _compat_wrapper(_impl__summary_text)
_looks_like_balance_insufficient = _compat_wrapper(_impl__looks_like_balance_insufficient)
_payment_with_bank_fallback = _compat_wrapper(_impl__payment_with_bank_fallback)
_direct_box_int = _compat_wrapper(_impl__direct_box_int)
_direct_box_text = _compat_wrapper(_impl__direct_box_text)
_direct_box_configs = _compat_wrapper(_impl__direct_box_configs)
_direct_box_rows = _compat_wrapper(_impl__direct_box_rows)
_direct_box_id = _compat_wrapper(_impl__direct_box_id)
_direct_box_sort_key = _compat_wrapper(_impl__direct_box_sort_key)
_direct_box_order_sn = _compat_wrapper(_impl__direct_box_order_sn)
_direct_box_units = _compat_wrapper(_impl__direct_box_units)
_direct_box_counts = _compat_wrapper(_impl__direct_box_counts)
_direct_box_allocations = _compat_wrapper(_impl__direct_box_allocations)
_direct_box_prepare_to_checking = _compat_wrapper(_impl__direct_box_prepare_to_checking)
_full_flow_update_shared = _compat_wrapper(_impl__full_flow_update_shared)
_full_flow_record_step = _compat_wrapper(_impl__full_flow_record_step)
_full_flow_node_results = _compat_wrapper(_impl__full_flow_node_results)
_full_flow_finish = _compat_wrapper(_impl__full_flow_finish)
_resume_record_skipped = _compat_wrapper(_impl__resume_record_skipped)
_resume_flow_finish = _compat_wrapper(_impl__resume_flow_finish)
_full_flow_stop_reached = _compat_wrapper(_impl__full_flow_stop_reached)
_full_flow_prepare_warehouse_counts = _compat_wrapper(_impl__full_flow_prepare_warehouse_counts)
