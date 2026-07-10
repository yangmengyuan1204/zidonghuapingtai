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
from .registry import SCRIPT_REGISTRY, register_script



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




















































def _finish_paused(
    script_name: str,
    log: Dict[str, Any],
    node: str,
    summary: Dict[str, Any] | None = None,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    paused = _paused_summary(node, summary)
    log["paused"] = paused
    return _finish_named(script_name, log, True, paused)
















































































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




































ORDER_PART_PAY_FEE_KEYS = ["domestic_freight", "service_fee", "additional_service_fee", "other_fee"]
ORDER_PART_PAY_TAIL_NODES = {"before_shelf", "before_porder_create"}
































































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
















































































































































































































































MATERIAL_GENERATION_SCRIPT_NAME = "辅料生成"
MATERIAL_ORDER_SCRIPT_NAME = "辅料单"










# 注册脚本函数






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




# ─── OEM 样品单全流程（提出 + 后台管理）─────────────────────────────

OEM_SAMPLE_FULL_FLOW_NAME = "OEM样品单全流程"




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




# ─── OEM 样品单余额支付 ────────────────────────────────────────────

OEM_BALANCE_PAY_NAME = "OEM样品单余额支付"


from .data_script_shared import (
    _runtime_from_variables,
    _admin_session_from,
    _client_login_inputs,
    _as_list,
    _unique_list,
    _as_int,
    _clean_multipart_headers,
    _post_form,
    _response_json,
    _response_brief,
    _extract_token,
    _data_object,
    _goods_items,
    _first_stock,
    _detail_specs,
    _cart_payload,
    _auth_headers,
    _auth_form_fields,
    _duration_ms,
    _finish_named,
    _finish,
    _stop_after_node,
    _checkpoint_requested,
    _paused_summary,
    _is_paused,
)
from .cart_support import (
    _legacy_run_shopping_cart_script,
    _as_float,
    _as_bool,
    _quantity_cycle,
    _item_brief,
    _cart_text,
    _cart_item_matches,
    _verify_cart_contains_items,
    _api_success,
    _api_paths,
    _api_path,
    _client_login_with_path,
    _configure_client_api_paths,
    _payload_brief,
    _order_text,
    _first_price,
    _json_list,
    _order_option_items,
    _order_option_key,
    _order_option_label,
    _normalize_order_option_counts,
    _add_order_option_to_catalog,
    _order_option_catalog_from_options,
    _collect_order_option_catalog,
    _public_order_options,
    _order_option_list_path,
    _fetch_order_option_catalog,
    _apply_order_options_to_items,
    _flatten_cart_goods,
    _cart_item_ready,
    _select_cart_items,
    _cart_shop_key,
    _select_cart_items_by_shop,
    _order_item_brief,
    _edit_cart_fields,
    _cart_item_quantity,
    _authed_client_with_token,
    _edit_cart_items_for_order,
)
from .order_support import (
    _translate_order_msg,
    _parse_order_max_limit,
    _order_fields,
    _extract_order_sn,
    _decimal_text,
    _money_total,
    _admin_headers,
    _call_with_retry,
    _post_admin_form,
    _flatten_urlencoded_fields,
    _post_admin_urlencoded,
    _admin_login_without_runtime,
    _admin_login,
    _order_detail_data,
    _admin_detail_brief,
    _prepare_translate_data,
    _build_confirm_data,
    _order_part_pay_enabled,
    _full_flow_part_pay_script_enabled,
    _order_part_pay_requested,
    _order_part_pay_percent,
    _order_part_pay_tail_node,
    _order_part_pay_fee_timing,
    _apply_order_part_pay_payload,
    _order_part_pay_api_node,
    _order_part_pay_api_fee_flag,
    _order_part_pay_goods_total,
    _order_part_pay_first_goods_amount,
    _order_part_pay_plan_fields,
    _save_order_part_pay_plan_if_needed,
    _prepare_offer_data,
    _run_backend_order_flow,
    _order_status_code,
    _resume_node_for_order_status,
    _order_detail_ids,
    _order_ready_for_warehouse_delivery,
    _purchase_is_pending_start,
    _detect_resume_order_state,
    _run_backend_order_flow_resume,
    preview_order_quote_options,
)


from .payment_support import (
    _positive_decimal,
    _first_positive_decimal,
    _order_rows_from_payload,
    _order_payment_amount,
    _payment_order_list_fields,
    _select_payment_order,
    _login_client_for_payment,
    _load_payment_order,
    _common_payment_summary,
    _first_recursive_positive_decimal,
    _porder_payload_matches,
    _porder_payment_summary,
    _porder_payment_amount_from_payload,
    _load_porder_payment_amount,
    _apply_extra_fields,
    _order_tail_payment_order_sn,
    _order_tail_payment_mode,
    _order_tail_payment_path,
    _order_tail_pay_amount_from_variables,
    _order_tail_value_list,
    _order_tail_partial_enabled,
    _order_tail_partial_select_by,
    _order_tail_partial_selected_values,
    _order_tail_detail_id,
    _order_tail_detail_sorting,
    _order_tail_detail_status,
    _order_tail_detail_is_paid,
    _order_tail_detail_is_unpaid,
    _order_tail_order_detail_rows,
    _order_tail_unpaid_ids_from_detail,
    _order_tail_detail_fields,
    _order_tail_pay_data_fields,
    _order_tail_apply_payment_detail_fields,
    _order_tail_pay_data_brief,
    _order_tail_pay_amount_from_pay_data,
    _order_tail_pay_data_unpayable_ids,
    _resolve_order_tail_partial_context,
    _public_order_tail_context,
    _order_tail_bank_pay_amount,
    _run_order_tail_payment_if_needed,
    _bank_pay_reach_date,
    _finance_rows_from_payload,
    _finance_bill_brief,
    _row_contains_text,
    _select_finance_bill,
    _finance_unconfirm_fields,
    _admin_rows_from_payload,
    _field_text,
)
from .purchase_support import (
    _purchase_timestamp_no,
    _purchase_list_fields,
    _flatten_purchase_items,
    _purchase_item_id,
    _select_purchase_items,
    _positive_text,
    _purchase_item_values,
    _purchase_status_name,
    _purchase_save_rows,
    _purchase_wait_pay_rows,
    _purchase_item_brief,
    _purchase_order_detail_id,
    _purchase_wait_pay_fields,
    _select_purchase_wait_pay,
    _finance_purchase_brief,
    _follow_list_fields,
    _flatten_follow_items,
    _preview_rows_from_payload,
    _preview_items,
    _order_purchase_id,
    _item_up_num,
    _items_already_checking,
    _first_preview_user_id,
    _unique_values,
    _purchase_status_code,
    _purchase_still_pending,
    _verify_purchase_to_shelf_completed,
    _walk_grid_candidates,
    _grid_candidates,
    _select_grid_from_payload,
    _step,
)


from .warehouse_support import (
    _porder_sn,
    _warehouse_list_fields,
    _warehouse_candidate_paths,
    _nested_rows,
    _field_value,
    _warehouse_item_id,
    _warehouse_sku_id,
    _warehouse_sendable_num,
    _warehouse_item_brief,
    _warehouse_requested_order_detail_ids,
    _warehouse_row_order_sn,
    _warehouse_row_matches_current_order,
    _select_warehouse_items,
    _select_warehouse_item,
    _address_fields,
    _default_receiver_address,
    _default_importer_address,
    _merge_address,
    _porder_create_fields_for_items,
    _porder_create_fields,
    _extract_porder_sn,
    _walk_dicts,
    _first_deep_value,
    _porder_detail_rows,
    _porder_detail_id,
    _porder_wait_box_num,
    _box_need_num,
    _extract_freight_id,
    _payload_structure_sample,
    _freight_box_brief,
    _has_incomplete_freight_box,
    _porder_complete_box_paths,
    _extract_stock_item,
    _stock_item_from_row,
    _extract_stock_item_for_detail,
    _porder_flow_detail_items,
    _porder_detail_payload,
    _porder_detail_brief,
)
from .porder_flow_support import (
    _run_backend_porder_flow,
)
from .porder_resume_support import (
    _run_backend_porder_flow_resume,
    _porder_detail_status_texts,
    _porder_node_from_status_texts,
    _detect_resume_porder_state,
)
