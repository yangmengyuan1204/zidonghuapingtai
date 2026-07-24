"""配送单出货脚本 — 已支付配送单 → 校验/填写物流单号 → 提交出货 → 回查已出货状态。

默认接口路径（可通过 variables.api_paths 覆盖）:
  admin_porder_detail  → /porder.detail
  admin_porder_freight_list → /porder.freightList
  admin_porder_get_express_no → /porder.getExpressNo
  admin_porder_update_express_no_check_address_diff → /porder.updateExpressNoCheckAddressDiff
  admin_porder_update_express_no → /porder.updateExpressNo
  admin_porder_submit_delivery → /porder.submitDelivery

已出货配送单直接视为成功并跳过。
"""
from __future__ import annotations

import sys
import time as _time
from datetime import datetime
from typing import Any, Dict, Tuple


_COMPAT_NAMES = (
    "_admin_login",
    "_admin_session_from",
    "_api_path",
    "_api_success",
    "_as_int",
    "_checkpoint_requested",
    "_nested_rows",
    "_paused_summary",
    "_finish_named",
    "_payload_brief",
    "_porder_detail_brief",
    "_porder_detail_payload",
    "_porder_detail_rows",
    "_porder_detail_status_texts",
    "_post_admin_urlencoded",
    "time",
)

POORDER_SHIPMENT_SCRIPT_NAME = "配送单出货"

_SHIPPED_KEYWORDS = ("已出货", "已出貨", "已发出", "已發出", "delivery_complete", "delivery complete", "shipped")
_STATUS_KEYS = (
    "status",
    "statusName",
    "status_name",
    "statusText",
    "status_text",
    "porder_status",
    "porderStatus",
    "porder_status_name",
    "porderStatusName",
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _status_texts_contain(one_or_many: str | list[str], keywords: tuple[str, ...]) -> bool:
    texts = [one_or_many] if isinstance(one_or_many, str) else one_or_many
    lower = " ".join(t for t in texts if t).lower()
    return any(kw in lower for kw in keywords)


def _porder_status_texts(payload: Dict[str, Any], rows: list[Dict[str, Any]]) -> list[str]:
    texts = list(_porder_detail_status_texts(rows))
    data = payload.get("data")
    roots = [payload, data] if isinstance(data, dict) else [payload]
    for root in roots:
        for key in _STATUS_KEYS:
            value = root.get(key)
            if value not in (None, "", [], {}):
                texts.append(str(value).strip())
    return list(dict.fromkeys(text for text in texts if text))


def _co_shipment_main_sn(payload: Dict[str, Any]) -> tuple[bool, str]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return False, ""
    merge_type = str(data.get("merge_type") or "").strip()
    is_child = "集运出货" in merge_type and "副" in merge_type
    main_sn = str(data.get("co_porder_sn") or data.get("coPorderSn") or "").strip()
    return is_child, main_sn


def _parse_freight_box_list(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    boxes: list[Dict[str, Any]] = []

    def collect(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                collect(item)
            return
        if not isinstance(value, dict):
            return
        if value.get("id") not in (None, "") and "express_no" in value:
            boxes.append(value)
            return
        for key in ("data", "group", "list", "rows", "result", "items"):
            child = value.get(key)
            if isinstance(child, (dict, list)):
                collect(child)

    collect(payload.get("data"))
    return boxes


def _missing_express_boxes(boxes: list[Dict[str, Any]]) -> list[int]:
    return [b.get("id") or b.get("freight_id") or 0 for b in boxes if not (b.get("express_no") or "").strip()]


def _extract_express_no(payload: Dict[str, Any]) -> str:
    keys = ("express_no", "expressNo", "logistics_no", "logisticsNo", "tracking_no", "trackingNo")

    def find(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            for item in value:
                result = find(item)
                if result:
                    return result
            return ""
        if not isinstance(value, dict):
            return ""
        for key in keys:
            result = value.get(key)
            if result not in (None, ""):
                return str(result).strip()
        for key in ("data", "result", "rows", "items", "list"):
            result = find(value.get(key))
            if result:
                return result
        return ""

    return find(payload.get("data"))


def _porder_sn(variables: Dict[str, Any]) -> str:
    candidates = str(variables.get("porder_sn") or "").strip()
    if candidates:
        return candidates.split(",")[0].strip()
    sns = str(variables.get("porder_sns") or "").strip()
    if sns:
        return sns.split(",")[0].strip()
    return ""


def run_porder_shipment_script(
    env, variables: Dict[str, Any] | None = None
) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    from app.executors import ensure_report_dirs
    ensure_report_dirs()
    variables = dict(variables or {})
    porder_sn = _porder_sn(variables)
    requested_porder_sn = porder_sn
    summary_context = {"porder_sn": porder_sn}
    timeout = _as_int(variables.get("timeout"), getattr(env, "timeout", 25) or 25)
    base_url = (variables.get("backend_base_url") or getattr(env, "base_url", "") or "https://jpmanage.rakumart.cn").rstrip("/")
    log: Dict[str, Any] = {
        "script": POORDER_SHIPMENT_SCRIPT_NAME,
        "porder_sn": porder_sn,

        "started_at": datetime.now(),
    }
    if not porder_sn:
        return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {"reason": "缺少必填参数：porder_sn 不能为空"})
    try:
        session = _admin_session_from(variables)
        # 1. 登录
        login_payload, token = _admin_login(session, base_url, variables, timeout)
        session.headers.update({
            "AdminToken": f"Bearer {token}" if token else "",
            "Fingerprint": str(variables.get("fingerprint") or "35d3d2dc553624bd3e6cc32688f4e43b"),
            "PageUrlTrace": f"https://jpmanage.rakumart.cn/#/porderDetail?porder_sn={porder_sn}",
        })
        log["login"] = {
            **_payload_brief(login_payload),
            "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
            "token_extracted": bool(token),
        }
        if not _api_success(login_payload) or not token:
            return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {"porder_sn": porder_sn, "reason": "后台登录失败"})
        # 2. 查配送单详情
        detail_payload, detail_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout)
        log["detail"] = _porder_detail_brief(detail_payload, detail_rows)
        if not _api_success(detail_payload) or not detail_rows:
            return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {"porder_sn": porder_sn, "reason": "未获取到配送单详情"})
        is_co_child, main_porder_sn = _co_shipment_main_sn(detail_payload)
        if is_co_child:
            if not main_porder_sn:
                return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {
                    "porder_sn": porder_sn,
                    "reason": "集运副单缺少主配送单号",
                })
            porder_sn = main_porder_sn
            summary_context = {
                "requested_porder_sn": requested_porder_sn,
                "porder_sn": porder_sn,
            }
            log["requested_porder_sn"] = requested_porder_sn
            log["porder_sn"] = porder_sn
            log["co_shipment"] = {
                "merge_type": "集运出货·副",
                "requested_porder_sn": requested_porder_sn,
                "main_porder_sn": porder_sn,
            }
            session.headers["PageUrlTrace"] = f"https://jpmanage.rakumart.cn/#/porderDetail?porder_sn={porder_sn}"
            detail_payload, detail_rows = _porder_detail_payload(
                session, base_url, variables, porder_sn, timeout
            )
            log["main_detail"] = _porder_detail_brief(detail_payload, detail_rows)
            if not _api_success(detail_payload) or not detail_rows:
                return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {
                    **summary_context,
                    "reason": "未获取到集运主配送单详情",
                })
        status_texts = _porder_status_texts(detail_payload, detail_rows)
        log["status_texts"] = status_texts
        if _status_texts_contain(status_texts, _SHIPPED_KEYWORDS):
            return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, True, {
                **summary_context,
                "already_shipped": True,
                "status_texts": status_texts,
                "completed": True,
            })
        # 3. 查箱子列表
        freight_list_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
            {"porder_sn": porder_sn},
            timeout,
        )
        boxes = _parse_freight_box_list(freight_list_payload)
        log["freight_list"] = {
            **_payload_brief(freight_list_payload),
            "box_count": len(boxes),
        }
        if not boxes:
            return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {**summary_context, "reason": "配送单无箱子"})
        # 4. 填写物流单号
        freight_groups: Dict[str, Dict[str, Any]] = {}
        for box in boxes:
            freight_id = box.get("id") or box.get("freight_id")
            if not freight_id:
                continue
            logistics_id = box.get("logistics_id")
            group_key = str(logistics_id) if logistics_id not in (None, "") else f"freight:{freight_id}"
            group = freight_groups.setdefault(
                group_key,
                {"logistics_id": logistics_id, "freight_ids": [], "express_nos": []},
            )
            group["freight_ids"].append(freight_id)
            current_express_no = str(box.get("express_no") or "").strip()
            if current_express_no:
                group["express_nos"].append(current_express_no)
        if not freight_groups:
            return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {
                **summary_context,
                "reason": "配送单箱子缺少 freight_id",
            })
        address_checks = []
        express_no_requests = []
        express_updates = []
        assigned_express_nos = []
        for group in freight_groups.values():
            freight_ids = group["freight_ids"]
            existing_express_nos = list(dict.fromkeys(group["express_nos"]))
            if len(group["express_nos"]) == len(freight_ids):
                assigned_express_nos.extend(existing_express_nos)
                continue
            express_no_payload = _post_admin_urlencoded(
                session, base_url,
                _api_path(variables, "admin_porder_get_express_no", "/porder.getExpressNo"),
                {"porder_sn": porder_sn, "freight_id_set": freight_ids},
                timeout,
            )
            express_no = _extract_express_no(express_no_payload)
            express_no_request = {
                **_payload_brief(express_no_payload),
                "express_no": express_no,
                "logistics_id": group["logistics_id"],
                "freight_ids": freight_ids,
            }
            express_no_requests.append(express_no_request)
            if not _api_success(express_no_payload) or not express_no:
                log["get_express_no"] = express_no_requests
                return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {
                    **summary_context,
                    "reason": "自动获取物流单号失败",
                    "get_express_no": express_no_request,
                })
            assigned_express_nos.append(express_no)
            addr_check_payload = _post_admin_urlencoded(
                session, base_url,
                _api_path(variables, "admin_porder_update_express_no_check_address_diff", "/porder.updateExpressNoCheckAddressDiff"),
                {"freight_id_set": freight_ids, "express_no": express_no},
                timeout,
            )
            address_check = {
                **_payload_brief(addr_check_payload),
                "logistics_id": group["logistics_id"],
                "freight_ids": freight_ids,
            }
            address_checks.append(address_check)
            if not _api_success(addr_check_payload):
                log["address_checks"] = address_checks
                return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {
                    **summary_context,
                    "reason": "物流号地址校验未通过",
                    "address_check": address_check,
                })
            express_payload = _post_admin_urlencoded(
                session, base_url,
                _api_path(variables, "admin_porder_update_express_no", "/porder.updateExpressNo"),
                {"freight_id_set": freight_ids, "express_no": express_no},
                timeout,
            )
            express_update = {
                **_payload_brief(express_payload),
                "express_no": express_no,
                "logistics_id": group["logistics_id"],
                "freight_ids": freight_ids,
            }
            express_updates.append(express_update)
            if not _api_success(express_payload):
                log["address_checks"] = address_checks
                log["update_express_no"] = express_updates
                return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {
                    **summary_context,
                    "reason": "填写物流单号失败",
                    "update_express_no": express_update,
                })
        log["get_express_no"] = express_no_requests
        log["address_checks"] = address_checks
        log["update_express_no"] = express_updates
        # 5. 出货前校验
        refreshed_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
            {"porder_sn": porder_sn},
            timeout,
        )
        refreshed_boxes = _parse_freight_box_list(refreshed_payload)
        log["freight_refresh"] = {
            **_payload_brief(refreshed_payload),
            "box_count": len(refreshed_boxes),
        }
        if not _api_success(refreshed_payload) or not refreshed_boxes:
            return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {
                **summary_context,
                "reason": "出货前未获取到配送单箱子",
                "freight_refresh": log["freight_refresh"],
            })
        missing = _missing_express_boxes(refreshed_boxes)
        if missing:
            return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {**summary_context, "reason": "有箱子缺少物流号", "missing_freight_ids": missing})
        # 6. 提交出货
        delivery_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_submit_delivery", "/porder.submitDelivery"),
            {"porder_sn": porder_sn},
            timeout,
        )
        log["submit_delivery"] = _payload_brief(delivery_payload)
        if not _api_success(delivery_payload):
            return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {**summary_context, "reason": "提交出货失败", "submit_delivery": _payload_brief(delivery_payload)})
        # 7. 回查已出货。后台状态异步更新，默认最多等待约 60 秒。
        verify_attempts = max(1, _as_int(variables.get("shipment_verify_attempts"), 30))
        try:
            verify_interval = max(0.2, float(variables.get("shipment_verify_interval") or 2))
        except (TypeError, ValueError):
            verify_interval = 2.0
        last_verify: Dict[str, Any] = {}
        for attempt in range(verify_attempts):
            if attempt:
                _time.sleep(verify_interval)
            verify_payload, verify_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout, retries=1)
            verify_texts = _porder_status_texts(verify_payload, verify_rows)
            last_verify = {
                **_payload_brief(verify_payload),
                "attempt": attempt + 1,
                "status_texts": verify_texts,
            }
            if _status_texts_contain(verify_texts, _SHIPPED_KEYWORDS):
                log["verify_shipped"] = last_verify
                return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, True, {
                    **summary_context, "express_nos": assigned_express_nos,
                    "shipped": True, "status_texts": verify_texts, "completed": True,
                })
        log["verify_shipped"] = last_verify
        return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {
            **summary_context,
            "reason": "出货后状态未在限定时间内更新为已出货",
            "shipped": False,
            "last_verify": last_verify,
        })
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(POORDER_SHIPMENT_SCRIPT_NAME, log, False, {"porder_sn": porder_sn, "reason": str(exc)})
