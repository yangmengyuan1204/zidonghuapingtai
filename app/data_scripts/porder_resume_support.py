from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    '_admin_detail_brief',
    '_admin_login',
    '_admin_session_from',
    '_api_path',
    '_api_success',
    '_as_int',
    '_box_need_num',
    '_checkpoint_requested',
    '_extract_freight_id',
    '_extract_stock_item_for_detail',
    '_freight_box_brief',
    '_has_incomplete_freight_box',
    '_nested_rows',
    '_paused_summary',
    '_payload_brief',
    '_payload_structure_sample',
    '_porder_complete_box_paths',
    '_porder_detail_brief',
    '_porder_detail_payload',
    '_porder_detail_rows',
    '_porder_detail_status_texts',
    '_porder_flow_detail_items',
    '_porder_node_from_status_texts',
    '_positive_decimal',
    '_post_admin_form',
    '_post_admin_urlencoded',
    '_unique_list',
    'bulk_cart',
    'time',
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


def _impl__run_backend_porder_flow_resume(
    base_url: str,
    timeout: int,
    variables: Dict[str, Any],
    porder_sn: str,
    log: Dict[str, Any],
    detected_start_node: str,
) -> tuple[bool, Dict[str, Any]]:
    backend_log: Dict[str, Any] = {"porder_sn": porder_sn, "detected_start_node": detected_start_node, "steps": []}
    log["backend_porder_resume"] = backend_log
    session = _admin_session_from(variables)

    login_payload, token = _admin_login(session, base_url, variables, timeout)
    session.headers.update(
        {
            "AdminToken": f"Bearer {token}" if token else "",
            "adminToken": f"Bearer {token}" if token else "",
            "Fingerprint": str(variables.get("fingerprint") or "35d3d2dc553624bd3e6cc32688f4e43b"),
            "PageUrlTrace": f"https://jpmanage.rakumart.cn/#/porderDetail?porder_sn={porder_sn}",
            "Origin": "https://jpmanage.rakumart.cn",
            "Referer": "https://jpmanage.rakumart.cn/",
        }
    )
    backend_log["login"] = {
        **_payload_brief(login_payload),
        "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
        "token_extracted": bool(token),
    }
    if not _api_success(login_payload) or not token:
        return False, {"backend_passed": False, "reason": "后台登录失败"}

    detail_payload, detail_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout)
    backend_log["detail_before"] = _porder_detail_brief(detail_payload, detail_rows)
    if not _api_success(detail_payload) or not detail_rows:
        return False, {"backend_passed": False, "reason": "未获取到配送单详情"}

    default_box_num = _as_int(variables.get("backend_box_num"), 1)
    detail_items = _porder_flow_detail_items(detail_rows, default_box_num)
    if not detail_items:
        return False, {"backend_passed": False, "reason": "配送单详情缺少 porder_detail_id"}

    porder_detail_ids = [item["porder_detail_id"] for item in detail_items]
    porder_detail_id = porder_detail_ids[0]
    stock_item: Dict[str, Any] = {"stock_id": "", "box_num": 1}
    freight_id = ""
    logistics_id = str(variables.get("delivery_quote_logistics_id") or variables.get("quote_logistics_id") or "25")
    logistics_price = str(variables.get("logistics_price_artificial") or "775")
    skip_remaining = False

    # ── Step 1: submitTranslate ──
    if detected_start_node in ("warehouse_delivery_created",):
        translate_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_submit_translate", "/porder.submitTranslate"),
            {
                "porder_sn": porder_sn,
                "client_remark_translate": str(variables.get("client_remark_translate") or "自动化配送单翻译"),
                "list": [{"id": item["porder_detail_id"], "y_remark": str(variables.get("porder_y_remark") or "自动化装箱")} for item in detail_items],
                "is_temp": str(variables.get("porder_translate_is_temp") or "0"),
            },
            timeout,
        )
        backend_log["submit_translate"] = {**_payload_brief(translate_payload), "porder_detail_ids": porder_detail_ids}
        if not _api_success(translate_payload):
            return False, {"backend_passed": False, "reason": "配送单提交配货失败", "submit_translate": _payload_brief(translate_payload)}

        _, after_translate_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout, retries=2)
        if after_translate_rows:
            translated_items = _porder_flow_detail_items(after_translate_rows, default_box_num)
            if translated_items:
                detail_items = translated_items
                porder_detail_ids = [item["porder_detail_id"] for item in detail_items]
                porder_detail_id = porder_detail_ids[0]
        backend_log["detail_after_translate"] = {"detail_count": len(after_translate_rows), "porder_detail_ids": porder_detail_ids}
        if _checkpoint_requested(variables, "porder_translated"):
            return True, _paused_summary(
                "porder_translated",
                {
                    "porder_sn": porder_sn,
                    "porder_detail_id": porder_detail_id,
                    "porder_detail_ids": porder_detail_ids,
                    "backend_passed": True,
                    "backend_steps": ["login", "porder_detail", "submit_translate"],
                },
            )
    else:
        backend_log["submit_translate"] = {"skipped": True, "reason": f"起点 {detected_start_node} 已过配货步骤"}

    # ── Step 2: addBox + intoBox ──
    if detected_start_node in ("warehouse_delivery_created", "porder_translated"):
        box_fields = {
            "porder_sn": porder_sn,
            "count": str(variables.get("box_count") or "1"),
            "length": str(variables.get("box_length") or "58"),
            "width": str(variables.get("box_width") or "51"),
            "height": str(variables.get("box_height") or "50"),
            "weight": str(variables.get("box_weight") or "10"),
        }
        add_box_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_add_box", "/porder.addBox"),
            box_fields, timeout,
        )
        backend_log["add_box"] = {**_payload_brief(add_box_payload), "request": box_fields}
        if not _api_success(add_box_payload):
            return False, {"backend_passed": False, "reason": "配送单添加箱子失败", "add_box": _payload_brief(add_box_payload)}

        freight_before_box_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
            {"porder_sn": porder_sn}, timeout,
        )
        detail_after_box_payload, detail_after_box_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout, retries=1)
        backend_log["freight_list_before_box"] = {**_payload_brief(freight_before_box_payload), "sample": _payload_structure_sample(freight_before_box_payload, limit=4)}
        backend_log["detail_after_add_box"] = _porder_detail_brief(detail_after_box_payload, detail_after_box_rows)

        preview_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_into_box_preview", "/porder.intoBoxPreview"),
            {"porderDetailIdS": porder_detail_ids}, timeout,
        )
        stock_items: list[Dict[str, Any]] = []
        for item in detail_items:
            stock_item = _extract_stock_item_for_detail(
                preview_payload, item["porder_detail_id"],
                _as_int(item.get("wait_box_num"), default_box_num),
                allow_global_fallback=len(detail_items) == 1,
            )
            box_num = _box_need_num(stock_item.get("num_need"), _as_int(item.get("wait_box_num"), default_box_num))
            stock_items.append({
                "porder_detail_id": item["porder_detail_id"],
                "stock_id": stock_item.get("stock_id") or "",
                "num_need": stock_item.get("num_need"),
                "box_num": box_num,
            })
        freight_id = _extract_freight_id(
            freight_before_box_payload, detail_after_box_payload, add_box_payload, preview_payload, detail_payload, variables=variables,
        )
        backend_log["into_box_preview"] = {
            **_payload_brief(preview_payload), "porder_detail_id": porder_detail_id,
            "porder_detail_ids": porder_detail_ids, "freight_id": freight_id,
            "stock_items": stock_items, "sample": _payload_structure_sample(preview_payload, limit=8),
        }
        if not _api_success(preview_payload):
            return False, {"backend_passed": False, "reason": "装箱预览失败", "into_box_preview": _payload_brief(preview_payload)}
        if not freight_id:
            return False, {"backend_passed": False, "reason": "未拿到箱子 freight_id，无法装箱"}
        missing_stock_items = [item for item in stock_items if not item.get("stock_id")]
        if missing_stock_items:
            return False, {
                "backend_passed": False,
                "reason": "未按配送单详情匹配到库存 stock_id，无法装箱",
                "missing_porder_detail_ids": [item["porder_detail_id"] for item in missing_stock_items],
            }
        stock_item = stock_items[0]
        box_num = _as_int(stock_item.get("box_num"), 1)
        into_box_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_into_box_submit", "/porder.intoBoxSubmit"),
            {
                "freight_id_set": [freight_id],
                "list": [{
                    "per_num": item["box_num"],
                    "porder_detail_id": item["porder_detail_id"],
                    "stock": [{"stock_id": item["stock_id"], "num_need": item["box_num"]}],
                } for item in stock_items],
            }, timeout,
        )
        backend_log["into_box_submit"] = {**_payload_brief(into_box_payload), "box_num": box_num, "box_nums": {item["porder_detail_id"]: item["box_num"] for item in stock_items}}
        if not _api_success(into_box_payload):
            return False, {"backend_passed": False, "reason": "装箱提交失败", "into_box_submit": _payload_brief(into_box_payload)}

        time.sleep(float(variables.get("after_box_submit_delay") or 0.8))
        detail_after_into_box_payload = _post_admin_form(
            session, base_url,
            _api_path(variables, "admin_porder_detail", "/porder.detail"),
            {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
        )
        detail_after_into_box_rows = _porder_detail_rows(detail_after_into_box_payload)
        freight_after_into_box_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
            {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
        )
        backend_log["detail_after_into_box"] = _porder_detail_brief(detail_after_into_box_payload, detail_after_into_box_rows)
        backend_log["freight_list_after_into_box"] = {
            **_payload_brief(freight_after_into_box_payload),
            "boxes": _freight_box_brief(freight_after_into_box_payload),
            "sample": _payload_structure_sample(freight_after_into_box_payload, limit=4),
        }
        spot_after_into_box_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_spot_porder_detail", "/spot/spot/check/getSpotPorderDetail"),
            {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
        )
        backend_log["spot_after_into_box"] = _payload_brief(spot_after_into_box_payload)

        complete_box_attempts: list[Dict[str, Any]] = []
        if _has_incomplete_freight_box(freight_after_into_box_payload):
            complete_box_fields = {**box_fields, "freight_id_set": [freight_id]}
            for complete_box_path in _porder_complete_box_paths(variables):
                try:
                    complete_payload = _post_admin_urlencoded(session, base_url, complete_box_path, complete_box_fields, timeout)
                    complete_brief = _payload_brief(complete_payload)
                except Exception as exc:
                    complete_payload = {"success": False, "message": str(exc)}
                    complete_brief = {"success": False, "message": str(exc)}
                time.sleep(float(variables.get("after_complete_box_delay") or 0.8))
                complete_check_payload = _post_admin_urlencoded(
                    session, base_url,
                    _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
                    {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
                )
                attempt = {
                    "path": complete_box_path, "request": complete_box_fields,
                    "response": complete_brief,
                    "boxes": _freight_box_brief(complete_check_payload),
                    "box_completed": not _has_incomplete_freight_box(complete_check_payload),
                }
                complete_box_attempts.append(attempt)
                if _api_success(complete_payload) and attempt["box_completed"]:
                    break
        else:
            complete_box_attempts.append({"skipped": True, "reason": "freight box already completed"})
        backend_log["complete_box_attempts"] = complete_box_attempts

        if _checkpoint_requested(variables, "warehouse_delivery_created"):
            return True, _paused_summary(
                "warehouse_delivery_created",
                {
                    "porder_sn": porder_sn,
                    "porder_detail_id": porder_detail_id,
                    "porder_detail_ids": porder_detail_ids,
                    "backend_passed": True,
                    "backend_steps": ["login", "porder_detail", "submit_translate", "add_box", "into_box", "complete_box"],
                },
            )
    else:
        backend_log["add_box"] = {"skipped": True, "reason": f"起点 {detected_start_node} 已过装箱步骤"}
        backend_log["into_box_submit"] = {"skipped": True}
        backend_log["complete_box_attempts"] = [{"skipped": True, "reason": f"起点 {detected_start_node} 已过装箱步骤"}]
        # 从货运列表中获取 freight_id
        freight_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
            {"porder_sn": porder_sn}, timeout,
        )
        freight_id = _extract_freight_id(freight_payload, variables=variables)
        stock_item = {"stock_id": ""}

    # ── Step 3: toWaitOffer ──
    if detected_start_node in ("warehouse_delivery_created", "porder_translated", "porder_confirmed"):
        to_wait_offer_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_to_wait_offer", "/porder.toWaitOffer"),
            {"porder_sn": porder_sn}, timeout,
        )
        backend_log["to_wait_offer"] = _payload_brief(to_wait_offer_payload)
        if not _api_success(to_wait_offer_payload):
            time.sleep(float(variables.get("to_wait_offer_retry_delay") or 1))
            retry_detail_payload = _post_admin_form(
                session, base_url,
                _api_path(variables, "admin_porder_detail", "/porder.detail"),
                {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
            )
            retry_detail_rows = _porder_detail_rows(retry_detail_payload)
            retry_freight_payload = _post_admin_urlencoded(
                session, base_url,
                _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
                {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
            )
            retry_spot_payload = _post_admin_urlencoded(
                session, base_url,
                _api_path(variables, "admin_spot_porder_detail", "/spot/spot/check/getSpotPorderDetail"),
                {"porder_sn": porder_sn, "filterByFreightNum": "false"}, timeout,
            )
            retry_to_wait_offer_payload = _post_admin_urlencoded(
                session, base_url,
                _api_path(variables, "admin_porder_to_wait_offer", "/porder.toWaitOffer"),
                {"porder_sn": porder_sn}, timeout,
            )
            backend_log["detail_before_to_wait_offer_retry"] = _porder_detail_brief(retry_detail_payload, retry_detail_rows)
            backend_log["freight_list_before_to_wait_offer_retry"] = {
                **_payload_brief(retry_freight_payload),
                "boxes": _freight_box_brief(retry_freight_payload),
                "sample": _payload_structure_sample(retry_freight_payload, limit=4),
            }
            backend_log["spot_before_to_wait_offer_retry"] = _payload_brief(retry_spot_payload)
            backend_log["to_wait_offer_retry"] = _payload_brief(retry_to_wait_offer_payload)
            if _api_success(retry_to_wait_offer_payload):
                to_wait_offer_payload = retry_to_wait_offer_payload
                backend_log["to_wait_offer"] = {**_payload_brief(to_wait_offer_payload), "retried": True}
        if not _api_success(to_wait_offer_payload):
            return False, {"backend_passed": False, "reason": "配送单提交业务失败", "to_wait_offer": _payload_brief(to_wait_offer_payload)}

        porder_to_wait_node = ""
        if _checkpoint_requested(variables, "porder_confirmed"):
            porder_to_wait_node = "porder_confirmed"
        elif _checkpoint_requested(variables, "porder_wait_offer"):
            porder_to_wait_node = "porder_wait_offer"
        if porder_to_wait_node:
            return True, _paused_summary(
                porder_to_wait_node,
                {
                    "porder_sn": porder_sn,
                    "porder_detail_id": porder_detail_id,
                    "porder_detail_ids": porder_detail_ids,
                    "freight_id": freight_id,
                    "backend_passed": True,
                    "backend_steps": ["login", "porder_detail", "submit_translate", "add_box", "into_box_submit", "complete_box", "to_wait_offer"],
                },
            )
    else:
        backend_log["to_wait_offer"] = {"skipped": True, "reason": f"起点 {detected_start_node} 已过提交业务步骤"}

    # ── Step 4: logistics selection + submitOffer ──
    if detected_start_node in ("warehouse_delivery_created", "porder_translated", "porder_confirmed", "porder_wait_offer"):
        logistics_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_batch_update_freight_logistics", "/porder.batchUpdateFreightLogistics"),
            {"logistics_id": logistics_id, "freight_id_set": [freight_id]}, timeout,
        )
        backend_log["batch_update_freight_logistics"] = {
            **_payload_brief(logistics_payload), "logistics_id": logistics_id, "freight_id": freight_id,
        }
        if not _api_success(logistics_payload):
            return False, {
                "backend_passed": False, "reason": "配送单选择国际物流失败",
                "batch_update_freight_logistics": _payload_brief(logistics_payload),
            }

        freight_list_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
            {"porder_sn": porder_sn}, timeout,
        )
        current_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_amount_current", "/porder.porderAmountCurrent"),
            {"porder_sn": porder_sn}, timeout,
        )
        backend_log["freight_list"] = _payload_brief(freight_list_payload)
        backend_log["amount_current"] = _payload_brief(current_payload)

        offer_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_submit_offer", "/porder.submitOffer"),
            {
                "porder_sn": porder_sn,
                "y_remark": str(variables.get("porder_offer_remark") or "自动化配送单报价"),
                "list": [{"id": item["porder_detail_id"], "y_remark": str(variables.get("porder_y_remark") or "自动化装箱"), "received_num": ""} for item in detail_items],
                "logistics_price_artificial": logistics_price,
                "fba_complete_num": str(variables.get("fba_complete_num") or "0"),
                "fba_overstep_reason": str(variables.get("fba_overstep_reason") or ""),
            }, timeout,
        )
        backend_log["submit_offer"] = {
            **_payload_brief(offer_payload), "porder_detail_id": porder_detail_id,
            "porder_detail_ids": porder_detail_ids, "logistics_price_artificial": logistics_price,
        }
        if _api_success(offer_payload) and _checkpoint_requested(variables, "porder_offered"):
            return True, _paused_summary(
                "porder_offered",
                {
                    "porder_sn": porder_sn, "porder_detail_id": porder_detail_id,
                    "porder_detail_ids": porder_detail_ids, "freight_id": freight_id,
                    "stock_id": stock_item.get("stock_id") if isinstance(stock_item, dict) else "",
                    "box_num": stock_item.get("box_num") if isinstance(stock_item, dict) else 1,
                    "logistics_id": logistics_id, "logistics_price_artificial": logistics_price,
                    "backend_passed": True,
                    "backend_steps": ["login", "porder_detail", "submit_translate", "add_box", "into_box_submit", "complete_box", "to_wait_offer", "batch_update_freight_logistics", "submit_offer"],
                },
            )
        if not _api_success(offer_payload):
            return False, {"backend_passed": False, "reason": "配送单报价失败", "submit_offer": _payload_brief(offer_payload)}
    else:
        backend_log["submit_offer"] = {"skipped": True, "reason": f"起点 {detected_start_node} 已过报价步骤"}

    return True, {
        "backend_passed": True,
        "backend_steps": ["login", "porder_detail", "submit_translate", "add_box", "into_box_submit", "complete_box", "to_wait_offer", "batch_update_freight_logistics", "submit_offer"],
        "porder_detail_id": porder_detail_id,
        "porder_detail_ids": porder_detail_ids,
        "freight_id": freight_id,
        "stock_id": stock_item.get("stock_id") if isinstance(stock_item, dict) else "",
        "logistics_id": logistics_id,
        "logistics_price_artificial": logistics_price,
    }


def _impl__porder_detail_status_texts(rows: list[Dict[str, Any]]) -> list[str]:
    texts: list[str] = []
    keys = [
        "status",
        "statusName",
        "status_name",
        "statusText",
        "status_text",
        "porder_status",
        "porderStatus",
        "porder_status_name",
        "porderStatusName",
    ]
    for row in rows:
        for key in keys:
            value = row.get(key)
            if value not in (None, "", [], {}):
                texts.append(str(value).strip())
    return _unique_list([text for text in texts if text])


def _impl__porder_node_from_status_texts(texts: list[str]) -> str:
    status_text = " ".join(texts).lower()
    if not status_text:
        return ""
    node_keywords = [
        ("porder_offered", ["已报价", "报价完成", "待付款", "等待付款", "wait_pay", "wait pay", "offered", "quoted"]),
        ("porder_wait_offer", ["待报价", "等待报价", "wait_offer", "wait offer"]),
        ("porder_confirmed", ["已装箱", "装箱完成", "待提交业务", "提交业务", "confirmed"]),
        ("porder_translated", ["已配货", "配货完成", "待装箱", "已翻译", "翻译完成", "translated"]),
    ]
    for node, keywords in node_keywords:
        if any(keyword in status_text for keyword in keywords):
            return node
    return ""


def _impl__detect_resume_porder_state(
    env: Env,
    variables: Dict[str, Any],
    porder_sn: str,
    log: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    base_url = (variables.get("backend_base_url") or env.base_url or bulk_cart.BASE_URL).rstrip("/")
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    detect_log: Dict[str, Any] = {"porder_sn": porder_sn, "base_url": base_url}
    log["resume_porder_detect"] = detect_log

    session = _admin_session_from(variables)
    login_payload, token = _admin_login(session, base_url, variables, timeout)
    detect_log["login"] = {
        **_payload_brief(login_payload),
        "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
        "token_extracted": bool(token),
    }
    if not _api_success(login_payload) or not token:
        return False, {"porder_sn": porder_sn, "detected_start_node": "", "reason": "后台登录失败"}

    # 查询配送单详情
    detail_payload, detail_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout)
    detect_log["detail"] = _porder_detail_brief(detail_payload, detail_rows)
    if not _api_success(detail_payload) or not detail_rows:
        return False, {"porder_sn": porder_sn, "detected_start_node": "", "reason": "未查到配送单详情"}

    # 查询箱子列表
    freight_payload = _post_admin_urlencoded(
        session, base_url,
        _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
        {"porder_sn": porder_sn, "filterByFreightNum": "false"},
        timeout,
    )
    freight_data = freight_payload.get("data") if isinstance(freight_payload.get("data"), dict) else {}
    freight_rows = _nested_rows(freight_data) if freight_data else []
    has_boxes = len(freight_rows) > 0
    boxes_completed = has_boxes and not _has_incomplete_freight_box(freight_payload)
    detect_log["freight_list"] = {
        **_payload_brief(freight_payload),
        "row_count": len(freight_rows),
        "has_boxes": has_boxes,
        "boxes_completed": boxes_completed,
    }

    # 判断当前节点
    detail_statuses = set()
    detail_has_freight_id = False
    for row in detail_rows:
        status = str(row.get("status", "") or "").strip()
        if status:
            detail_statuses.add(status)
        if row.get("freight_id"):
            detail_has_freight_id = True
    detail_status_texts = _porder_detail_status_texts(detail_rows)
    status_detected_node = _porder_node_from_status_texts(detail_status_texts)

    detected_start_node = ""
    order_status = detail_statuses

    # 从配送单状态反推当前节点
    # 若无箱子 → warehouse_delivery_created 或 porder_translated
    # 有箱子但未完成装箱 → porder_confirmed
    # 箱子已完成 → porder_wait_offer 或 porder_offered
    if status_detected_node == "porder_offered":
        detected_start_node = "porder_offered"
    elif not has_boxes:
        # 检查是否已提交翻译：detail 行的 status 如果有 translate 相关标记
        if status_detected_node in {"porder_translated", "porder_confirmed", "porder_wait_offer"}:
            detected_start_node = status_detected_node
        elif not detail_has_freight_id:
            detected_start_node = "warehouse_delivery_created"
        else:
            detected_start_node = "porder_translated"
    elif not boxes_completed:
        detected_start_node = "porder_confirmed"
    else:
        # 箱子已完成，检查是否已报价
        amount_payload = _post_admin_urlencoded(
            session, base_url,
            _api_path(variables, "admin_porder_amount_current", "/porder.porderAmountCurrent"),
            {"porder_sn": porder_sn},
            timeout,
        )
        detect_log["amount_current"] = _payload_brief(amount_payload)
        amount_data = amount_payload.get("data") if isinstance(amount_payload.get("data"), dict) else {}
        offered = bool(amount_data and (
            _positive_decimal(str(amount_data.get("pay_amount") or amount_data.get("amount") or "0"))
        ))
        if offered or status_detected_node == "porder_offered":
            detected_start_node = "porder_offered"
        elif status_detected_node in {"porder_confirmed", "porder_wait_offer"}:
            detected_start_node = status_detected_node
        else:
            detected_start_node = "porder_wait_offer"

    summary: Dict[str, Any] = {
        "porder_sn": porder_sn,
        "detail_statuses": list(detail_statuses),
        "detail_status_texts": detail_status_texts,
        "status_detected_node": status_detected_node,
        "has_boxes": has_boxes,
        "boxes_completed": boxes_completed,
        "detected_start_node": detected_start_node,
        "detail": _admin_detail_brief({"order_detail": detail_rows}),
    }
    if not detected_start_node:
        summary["reason"] = f"配送单状态无法识别"
        return False, summary
    return True, summary


_run_backend_porder_flow_resume = _compat_wrapper(_impl__run_backend_porder_flow_resume)
_porder_detail_status_texts = _compat_wrapper(_impl__porder_detail_status_texts)
_porder_node_from_status_texts = _compat_wrapper(_impl__porder_node_from_status_texts)
_detect_resume_porder_state = _compat_wrapper(_impl__detect_resume_porder_state)
