from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
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
    '_paused_summary',
    '_payload_brief',
    '_payload_structure_sample',
    '_porder_complete_box_paths',
    '_porder_detail_brief',
    '_porder_detail_payload',
    '_porder_detail_rows',
    '_porder_flow_detail_items',
    '_post_admin_form',
    '_post_admin_urlencoded',
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


def _impl__run_backend_porder_flow(
    base_url: str,
    timeout: int,
    variables: Dict[str, Any],
    porder_sn: str,
    log: Dict[str, Any],
) -> tuple[bool, Dict[str, Any]]:
    backend_log: Dict[str, Any] = {"porder_sn": porder_sn, "steps": []}
    log["backend_porder"] = backend_log
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

    translate_payload = _post_admin_urlencoded(
        session,
        base_url,
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

    box_fields = {
        "porder_sn": porder_sn,
        "count": str(variables.get("box_count") or "1"),
        "length": str(variables.get("box_length") or "58"),
        "width": str(variables.get("box_width") or "51"),
        "height": str(variables.get("box_height") or "50"),
        "weight": str(variables.get("box_weight") or "10"),
    }
    add_box_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_add_box", "/porder.addBox"),
        box_fields,
        timeout,
    )
    backend_log["add_box"] = {**_payload_brief(add_box_payload), "request": box_fields}
    if not _api_success(add_box_payload):
        return False, {"backend_passed": False, "reason": "配送单添加箱子失败", "add_box": _payload_brief(add_box_payload)}

    freight_before_box_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
        {"porder_sn": porder_sn},
        timeout,
    )
    detail_after_box_payload, detail_after_box_rows = _porder_detail_payload(session, base_url, variables, porder_sn, timeout, retries=1)
    backend_log["freight_list_before_box"] = {
        **_payload_brief(freight_before_box_payload),
        "sample": _payload_structure_sample(freight_before_box_payload, limit=4),
    }
    backend_log["detail_after_add_box"] = _porder_detail_brief(detail_after_box_payload, detail_after_box_rows)

    preview_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_into_box_preview", "/porder.intoBoxPreview"),
        {"porderDetailIdS": porder_detail_ids},
        timeout,
    )
    stock_items: list[Dict[str, Any]] = []
    for item in detail_items:
        stock_item = _extract_stock_item_for_detail(
            preview_payload,
            item["porder_detail_id"],
            _as_int(item.get("wait_box_num"), default_box_num),
            allow_global_fallback=len(detail_items) == 1,
        )
        box_num = _box_need_num(stock_item.get("num_need"), _as_int(item.get("wait_box_num"), default_box_num))
        stock_items.append(
            {
                "porder_detail_id": item["porder_detail_id"],
                "stock_id": stock_item.get("stock_id") or "",
                "num_need": stock_item.get("num_need"),
                "box_num": box_num,
            }
        )
    freight_id = _extract_freight_id(
        freight_before_box_payload,
        detail_after_box_payload,
        add_box_payload,
        preview_payload,
        detail_payload,
        variables=variables,
    )
    backend_log["into_box_preview"] = {
        **_payload_brief(preview_payload),
        "porder_detail_id": porder_detail_id,
        "porder_detail_ids": porder_detail_ids,
        "freight_id": freight_id,
        "stock_items": stock_items,
        "sample": _payload_structure_sample(preview_payload, limit=8),
    }
    if not _api_success(preview_payload):
        return False, {"backend_passed": False, "reason": "装箱预览失败", "into_box_preview": _payload_brief(preview_payload)}
    if not freight_id:
        return False, {"backend_passed": False, "reason": "未拿到箱子 freight_id，无法装箱"}
    missing_stock_items = [item for item in stock_items if not item.get("stock_id")]
    if missing_stock_items:
        return False, {
            "backend_passed": False,
            "reason": "\u672a\u6309\u914d\u9001\u5355\u8be6\u60c5\u5339\u914d\u5230\u5e93\u5b58 stock_id\uff0c\u65e0\u6cd5\u88c5\u7bb1",
            "missing_porder_detail_ids": [item["porder_detail_id"] for item in missing_stock_items],
        }
    stock_item = stock_items[0]
    if False and not stock_item.get("stock_id"):
        return False, {"backend_passed": False, "reason": "未拿到库存 stock_id，无法装箱"}

    box_num = _as_int(stock_item.get("box_num"), 1)
    into_box_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_into_box_submit", "/porder.intoBoxSubmit"),
        {
            "freight_id_set": [freight_id],
            "list": [
                {
                    "per_num": item["box_num"],
                    "porder_detail_id": item["porder_detail_id"],
                    "stock": [{"stock_id": item["stock_id"], "num_need": item["box_num"]}],
                }
                for item in stock_items
            ],
        },
        timeout,
    )
    backend_log["into_box_submit"] = {**_payload_brief(into_box_payload), "box_num": box_num, "box_nums": {item["porder_detail_id"]: item["box_num"] for item in stock_items}}
    if not _api_success(into_box_payload):
        return False, {"backend_passed": False, "reason": "装箱提交失败", "into_box_submit": _payload_brief(into_box_payload)}

    time.sleep(float(variables.get("after_box_submit_delay") or 0.8))
    detail_after_into_box_payload = _post_admin_form(
        session,
        base_url,
        _api_path(variables, "admin_porder_detail", "/porder.detail"),
        {"porder_sn": porder_sn, "filterByFreightNum": "false"},
        timeout,
    )
    detail_after_into_box_rows = _porder_detail_rows(detail_after_into_box_payload)
    freight_after_into_box_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
        {"porder_sn": porder_sn, "filterByFreightNum": "false"},
        timeout,
    )
    backend_log["detail_after_into_box"] = _porder_detail_brief(detail_after_into_box_payload, detail_after_into_box_rows)
    backend_log["freight_list_after_into_box"] = {
        **_payload_brief(freight_after_into_box_payload),
        "boxes": _freight_box_brief(freight_after_into_box_payload),
        "sample": _payload_structure_sample(freight_after_into_box_payload, limit=4),
    }
    spot_after_into_box_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_spot_porder_detail", "/spot/spot/check/getSpotPorderDetail"),
        {"porder_sn": porder_sn, "filterByFreightNum": "false"},
        timeout,
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
                session,
                base_url,
                _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
                {"porder_sn": porder_sn, "filterByFreightNum": "false"},
                timeout,
            )
            attempt = {
                "path": complete_box_path,
                "request": complete_box_fields,
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

    to_wait_offer_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_to_wait_offer", "/porder.toWaitOffer"),
        {"porder_sn": porder_sn},
        timeout,
    )
    backend_log["to_wait_offer"] = _payload_brief(to_wait_offer_payload)
    if not _api_success(to_wait_offer_payload):
        time.sleep(float(variables.get("to_wait_offer_retry_delay") or 1))
        retry_detail_payload = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_porder_detail", "/porder.detail"),
            {"porder_sn": porder_sn, "filterByFreightNum": "false"},
            timeout,
        )
        retry_detail_rows = _porder_detail_rows(retry_detail_payload)
        retry_freight_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
            {"porder_sn": porder_sn, "filterByFreightNum": "false"},
            timeout,
        )
        retry_spot_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_spot_porder_detail", "/spot/spot/check/getSpotPorderDetail"),
            {"porder_sn": porder_sn, "filterByFreightNum": "false"},
            timeout,
        )
        retry_to_wait_offer_payload = _post_admin_urlencoded(
            session,
            base_url,
            _api_path(variables, "admin_porder_to_wait_offer", "/porder.toWaitOffer"),
            {"porder_sn": porder_sn},
            timeout,
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
                "backend_steps": [
                    "login",
                    "porder_detail",
                    "submit_translate",
                    "add_box",
                    "into_box_preview",
                    "into_box_submit",
                    "complete_box",
                    "to_wait_offer",
                ],
            },
        )

    logistics_id = str(variables.get("delivery_quote_logistics_id") or variables.get("quote_logistics_id") or "25")
    logistics_price = str(variables.get("logistics_price_artificial") or "775")
    logistics_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_batch_update_freight_logistics", "/porder.batchUpdateFreightLogistics"),
        {"logistics_id": logistics_id, "freight_id_set": [freight_id]},
        timeout,
    )
    backend_log["batch_update_freight_logistics"] = {
        **_payload_brief(logistics_payload),
        "logistics_id": logistics_id,
        "freight_id": freight_id,
    }
    if not _api_success(logistics_payload):
        return False, {
            "backend_passed": False,
            "reason": "配送单选择国际物流失败",
            "batch_update_freight_logistics": _payload_brief(logistics_payload),
        }

    freight_list_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_freight_list", "/porder.freightList"),
        {"porder_sn": porder_sn},
        timeout,
    )
    current_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_amount_current", "/porder.porderAmountCurrent"),
        {"porder_sn": porder_sn},
        timeout,
    )
    backend_log["freight_list"] = _payload_brief(freight_list_payload)
    backend_log["amount_current"] = _payload_brief(current_payload)

    offer_payload = _post_admin_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_porder_submit_offer", "/porder.submitOffer"),
        {
            "porder_sn": porder_sn,
            "y_remark": str(variables.get("porder_offer_remark") or "自动化配送单报价"),
            "list": [{"id": item["porder_detail_id"], "y_remark": str(variables.get("porder_y_remark") or "自动化装箱"), "received_num": ""} for item in detail_items],
            "logistics_price_artificial": logistics_price,
            "fba_complete_num": str(variables.get("fba_complete_num") or "0"),
            "fba_overstep_reason": str(variables.get("fba_overstep_reason") or ""),
        },
        timeout,
    )
    backend_log["submit_offer"] = {
        **_payload_brief(offer_payload),
        "porder_detail_id": porder_detail_id,
        "porder_detail_ids": porder_detail_ids,
        "logistics_price_artificial": logistics_price,
    }
    if _api_success(offer_payload) and _checkpoint_requested(variables, "porder_offered"):
        return True, _paused_summary(
            "porder_offered",
            {
                "porder_sn": porder_sn,
                "porder_detail_id": porder_detail_id,
                "porder_detail_ids": porder_detail_ids,
                "freight_id": freight_id,
                "stock_id": stock_item.get("stock_id"),
                "stock_ids": [item.get("stock_id") for item in stock_items],
                "box_num": box_num,
                "box_nums": {item["porder_detail_id"]: item["box_num"] for item in stock_items},
                "logistics_id": logistics_id,
                "logistics_price_artificial": logistics_price,
                "backend_passed": True,
                "backend_steps": [
                    "login",
                    "porder_detail",
                    "submit_translate",
                    "add_box",
                    "into_box_preview",
                    "into_box_submit",
                    "complete_box",
                    "to_wait_offer",
                    "batch_update_freight_logistics",
                    "freight_list",
                    "submit_offer",
                ],
            },
        )
    if not _api_success(offer_payload):
        return False, {"backend_passed": False, "reason": "配送单报价失败", "submit_offer": _payload_brief(offer_payload)}

    return True, {
        "backend_passed": True,
        "backend_steps": [
            "login",
            "porder_detail",
            "submit_translate",
            "add_box",
            "into_box_preview",
            "into_box_submit",
            "complete_box",
            "to_wait_offer",
            "batch_update_freight_logistics",
            "freight_list",
            "submit_offer",
        ],
        "porder_detail_id": porder_detail_id,
        "porder_detail_ids": porder_detail_ids,
        "freight_id": freight_id,
        "stock_id": stock_item.get("stock_id"),
        "stock_ids": [item.get("stock_id") for item in stock_items],
        "box_num": box_num,
        "box_nums": {item["porder_detail_id"]: item["box_num"] for item in stock_items},
        "logistics_id": logistics_id,
        "logistics_price_artificial": logistics_price,
    }


_run_backend_porder_flow = _compat_wrapper(_impl__run_backend_porder_flow)
