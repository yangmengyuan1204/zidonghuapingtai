from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'Dict',
    'Env',
    'OEM_BALANCE_PAY_NAME',
    'OEM_DEFAULT_BASE_URL',
    'OEM_DEFAULT_FRONTEND_ORIGIN',
    'OEM_SAMPLE_ADMIN_SCRIPT_NAME',
    'OEM_SAMPLE_FULL_FLOW_NAME',
    'OEM_SAMPLE_ORDER_SCRIPT_NAME',
    'Tuple',
    '_as_int',
    '_call_admin_api',
    '_finish_named',
    '_oem_admin_login',
    '_oem_build_sku_info_from_quote',
    '_oem_client_login',
    '_oem_generate_sample_order_sn',
    '_oem_post_json',
    '_step',
    '_translate_oem_msg',
    'datetime',
    'ensure_report_dirs',
    'json',
    'requests',
    'time',
    'urljoin',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl_run_oem_sample_order_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 样品单提出脚本：前台登录 -> 创建样品单，返回 order_sn。

    接口 POST /api/newOrder，从询价单提出样品单。

    可配置变量：
        - account / password: 前台登录账号（默认 12345678990 / 123456）
        - order_sn: 询价单号（必填，如 Y20260701111904-15-OEM）
        - sku_list: SKU 列表，支持两种格式：
            a) JSON 字符串 [{"sku_id":1993,"num":1},{"sku_id":1994,"num":2}]
            b) 纯文本行，每行 "sku_id,num"（如 "1993,1"）
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")

    order_sn = str(variables.get("order_sn") or "").strip()
    if not order_sn:
        return _finish_named(
            OEM_SAMPLE_ORDER_SCRIPT_NAME, {},
            False, {"reason": "缺少必填参数：询价单号 order_sn 不能为空"},
        )

    log: Dict[str, Any] = {
        "script": OEM_SAMPLE_ORDER_SCRIPT_NAME,
        "mode": "oem_sample_order",
        "base_url": base_url,
        "inquiry_order_sn": order_sn,
        "sample_order_sn": "",
        "started_at": datetime.now(),
        "steps": [],
    }

    try:
        session = requests.Session()
        # 前台登录
        client_token, user_id, _ = _oem_client_login(session, base_url, variables, timeout)
        _step(
            log,
            "client_login",
            {"account": variables.get("account") or "12345678990"},
            {"url": "/client/userLogin", "method": "POST"},
            {"token": client_token[:16] + "..."},
        )

        # 解析 SKU 列表
        sku_list = variables.get("sku_list")
        if isinstance(sku_list, list):
            # 已是列表，确保每项含 option
            pass
        elif isinstance(sku_list, str) and sku_list.strip().startswith("["):
            # JSON 字符串解析
            try:
                sku_list = json.loads(sku_list)
            except (json.JSONDecodeError, TypeError):
                sku_list = []
        elif isinstance(sku_list, str) and sku_list.strip():
            # 纯文本行格式：每行 "sku_id,num"
            sku_list = []
            for line in sku_list.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                try:
                    sku_id = int(parts[0].strip())
                    num = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else 1
                    sku_list.append({"sku_id": sku_id, "num": num, "option": []})
                except (ValueError, IndexError):
                    continue
        else:
            sku_list = []

        # 确保每个 SKU 有 option 字段（OEM API 必须）
        if isinstance(sku_list, list):
            for item in sku_list:
                if isinstance(item, dict) and "option" not in item:
                    item["option"] = []

        sample_order_sn = _oem_generate_sample_order_sn(variables, user_id, 1)
        log["sample_order_sn"] = sample_order_sn
        body: Dict[str, Any] = {
            "order_sn": sample_order_sn,
            "inquiry_detail_id": variables.get("inquiry_detail_id") or str(variables.get("id") or ""),
            "type": 1,
            "sku_list": sku_list if sku_list else [{"sku_id": 1993, "num": 1, "option": []}],
            "remark": "",
            "warehouse_city": 2,
        }

        # 调用创建样品单接口
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {client_token}",
            "Origin": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN),
            "Referer": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN).rstrip("/") + "/",
        }
        url = urljoin(base_url.rstrip("/") + "/", "/api/newOrder")
        last_error: Exception | None = None
        payload: Dict[str, Any] = {}
        for attempt in range(3):
            try:
                response = session.post(url, json=body, headers=headers, timeout=timeout)
                payload = response.json()
                break
            except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
        else:
            raise RuntimeError(f"创建样品单请求失败: {last_error}")

        if not payload.get("success") or payload.get("code") not in (0, "0", None):
            raw_msg = payload.get("msg")
            raw_data = payload.get("data")
            translated_msg = _translate_oem_msg(raw_msg)
            # data 含 "Line:" 通常是后端业务校验失败（询价单已被转过样品单/状态已变更）
            hint = ""
            if isinstance(raw_data, str) and "Line:" in raw_data:
                hint = "（可能原因：该询价单已被转过样品单或状态已变更，请确认询价单可用性）"
            _step(
                log,
                "new_sample_order",
                payload,
                {"url": "/api/newOrder", "method": "POST", "body": body},
            )
            return _finish_named(
                OEM_SAMPLE_ORDER_SCRIPT_NAME,
                log,
                False,
                {
                    "reason": f"创建样品单失败: {translated_msg}{hint}",
                    "error": translated_msg,
                    "payload": payload,
                },
            )

        order_sn_out = str(payload.get("data") or "")
        _step(
            log,
            "new_sample_order",
            payload,
            {"url": "/api/newOrder", "method": "POST", "body": body},
            {"order_sn": order_sn_out, "success": True},
        )

        summary = {"order_sn": order_sn_out, "inquiry_order_sn": order_sn, "sample_order_sn": sample_order_sn, "reason": "创建样品单成功"}
        return _finish_named(OEM_SAMPLE_ORDER_SCRIPT_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_SAMPLE_ORDER_SCRIPT_NAME, log, False, {"reason": str(exc), "error": str(exc)})


def _impl_run_oem_sample_admin_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 样品单后台管理流程：翻译提交 → 开始确认 → 采购确认→业务。

    可配置变量：
        - order_sn: 样品单号（必填）
        - warehouse_city: 仓库城市（默认 2）
        - backend_account / backend_password: 后台登录凭证
        - quote_sku_info: SKU 报价明细 JSON（可覆盖自动查询）
        - inquiry_samples_price / quote_samples_price / real_samples_price 等报价字段
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")
    order_sn = str(variables.get("order_sn") or "").strip()
    if not order_sn:
        return _finish_named(OEM_SAMPLE_ADMIN_SCRIPT_NAME, {}, False, {"reason": "缺少必填参数：order_sn"})

    log: Dict[str, Any] = {
        "script": OEM_SAMPLE_ADMIN_SCRIPT_NAME,
        "mode": "oem_sample_admin_flow",
        "base_url": base_url,
        "order_sn": order_sn,
        "started_at": datetime.now(),
        "steps": [],
    }
    try:
        session = requests.Session()
        # Admin 后台登录
        admin_token = _oem_admin_login(session, base_url, variables, timeout)
        _step(log, "admin_login", {}, {"url": "/admin/login", "method": "POST"}, {"token_prefix": admin_token[:10] + "..."})

        # 1. 样品单翻译提交
        _call_admin_api(session, base_url, "/admin/samplesSubmitPurchase",
                        {"order_sn": order_sn, "warehouse_city": int(variables.get("warehouse_city") or 2)},
                        timeout, admin_token, variables, log, "samplesSubmitPurchase")

        # 2. 样品单开始确认
        _call_admin_api(session, base_url, "/admin/samplesStartConfirm",
                        {"order_sn": order_sn},
                        timeout, admin_token, variables, log, "samplesStartConfirm")

        # 3. 采购确认→业务（含报价信息）
        sku_info = _oem_build_sku_info_from_quote(order_sn, session, base_url, timeout, admin_token, variables)
        quote_info = {
            "inquiry_other_fee": str(variables.get("inquiry_other_fee", "0.00")),
            "inquiry_freight": str(variables.get("inquiry_freight", "0.00")),
            "inquiry_delivery_time": int(variables.get("inquiry_delivery_time", 0)),
            "quote_other_fee": str(variables.get("quote_other_fee", "7")),
            "quote_freight": str(variables.get("quote_freight", "8")),
            "quote_delivery_time": str(variables.get("quote_delivery_time", "9")),
            "real_other_fee": str(variables.get("real_other_fee", "7")),
            "real_freight": str(variables.get("real_freight", "8")),
            "sku_info": sku_info,
        }
        _call_admin_api(session, base_url, "/admin/samplesConfirmed", {
            "order_sn": order_sn,
            "warehouse_city": int(variables.get("warehouse_city") or 2),
            "is_special_quote": bool(variables.get("is_special_quote", True)),
            "y_response": str(variables.get("y_response", "")),
            "quote_info": quote_info,
        }, timeout, admin_token, variables, log, "samplesConfirmed")

        # 4. 业务开始报价
        _call_admin_api(session, base_url, "/admin/samplesStartQuote",
                        {"order_sn": order_sn},
                        timeout, admin_token, variables, log, "samplesStartQuote")

        # 5. 报价给客户
        _call_admin_api(session, base_url, "/admin/samplesQuoteToUser",
                        {"order_sn": order_sn, "warehouse_city": int(variables.get("warehouse_city") or 2)},
                        timeout, admin_token, variables, log, "samplesQuoteToUser")

        summary = {"order_sn": order_sn, "reason": "样品单后台流程执行成功"}
        return _finish_named(OEM_SAMPLE_ADMIN_SCRIPT_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_SAMPLE_ADMIN_SCRIPT_NAME, log, False, {"reason": str(exc), "error": str(exc)})


def _impl_run_oem_sample_full_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 样品单全流程：提出样品单 → 翻译提交 → 确认 → 报价给客户。

    阶段：
      1. 提出样品单（前台登录 → 创建样品单）
      2. 翻译提交（后台登录 → samplesSubmitPurchase）
      3. 开始确认（samplesStartConfirm）
      4. 采购确认（samplesConfirmed → samplesStartQuote → samplesQuoteToUser）
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")
    warehouse_city = int(variables.get("warehouse_city") or 2)
    inquiry_order_sn = str(variables.get("order_sn") or variables.get("inquiry_order_sn") or "").strip()
    sku_list_raw = variables.get("sku_list")
    sample_order_sn = str(variables.get("sample_order_sn") or "").strip()

    log: Dict[str, Any] = {
        "script": OEM_SAMPLE_FULL_FLOW_NAME,
        "mode": "oem_sample_full_flow",
        "base_url": base_url,
        "started_at": datetime.now(),
        "steps": [],
    }

    try:
        session = requests.Session()

        # ── 阶段 1：提出样品单 ──
        if not sample_order_sn and inquiry_order_sn:
            client_token, user_id, _ = _oem_client_login(session, base_url, variables, timeout)
            _step(log, "client_login", {"account": variables.get("account") or "12345678990"},
                  {"url": "/client/userLogin", "method": "POST"},
                  {"token": client_token[:16] + "..."})

            # 解析 SKU 列表
            sku_list = sku_list_raw
            if isinstance(sku_list, str):
                try:
                    sku_list = json.loads(sku_list) if sku_list.strip().startswith("[") else []
                except (json.JSONDecodeError, TypeError):
                    sku_list = []
            if not isinstance(sku_list, list):
                sku_list = []
            for item in sku_list:
                if isinstance(item, dict) and "option" not in item:
                    item["option"] = []

            gen_sample_sn = _oem_generate_sample_order_sn(variables, user_id, 1)
            log["generated_sample_order_sn"] = gen_sample_sn
            body = {
                "order_sn": gen_sample_sn,
                "inquiry_detail_id": variables.get("inquiry_detail_id") or "",
                "type": 1,
                "sku_list": sku_list if sku_list else [{"sku_id": 1993, "num": 1, "option": []}],
                "remark": "",
                "warehouse_city": warehouse_city,
            }
            headers = {
                "Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {client_token}",
                "Origin": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN),
                "Referer": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN).rstrip("/") + "/",
            }
            url = urljoin(base_url.rstrip("/") + "/", "/api/newOrder")
            payload = {}
            for attempt in range(3):
                try:
                    resp = session.post(url, json=body, headers=headers, timeout=timeout)
                    payload = resp.json()
                    break
                except (requests.ConnectionError, requests.Timeout, ValueError):
                    if attempt < 2:
                        time.sleep(0.8 * (attempt + 1))
            else:
                raise RuntimeError("创建样品单请求失败")
            if not payload.get("success") or payload.get("code") not in (0, "0", None):
                raise RuntimeError(f"创建样品单失败: {_translate_oem_msg(payload.get('msg'))}")
            sample_order_sn = str(payload.get("data") or "")
            _step(log, "new_sample_order", payload, {"url": "/api/newOrder", "method": "POST"},
                  {"order_sn": sample_order_sn, "success": True})
            log["sample_order_sn"] = sample_order_sn
        else:
            log["sample_order_sn"] = sample_order_sn or inquiry_order_sn

        if not sample_order_sn:
            sample_order_sn = inquiry_order_sn
        log["order_sn"] = sample_order_sn

        # ── 阶段 2-5：后台管理流程 ──
        admin_token = _oem_admin_login(session, base_url, variables, timeout)
        _step(log, "admin_login", {}, {"url": "/admin/login", "method": "POST"}, {"token_prefix": admin_token[:10] + "..."})

        # 翻译提交
        _call_admin_api(session, base_url, "/admin/samplesSubmitPurchase",
                        {"order_sn": sample_order_sn, "warehouse_city": warehouse_city},
                        timeout, admin_token, variables, log, "samplesSubmitPurchase")

        # 开始确认
        _call_admin_api(session, base_url, "/admin/samplesStartConfirm",
                        {"order_sn": sample_order_sn},
                        timeout, admin_token, variables, log, "samplesStartConfirm")

        # 采购确认→业务
        sku_info = _oem_build_sku_info_from_quote(sample_order_sn, session, base_url, timeout, admin_token, variables)
        quote_info = {
            "inquiry_other_fee": str(variables.get("inquiry_other_fee", "0.00")),
            "inquiry_freight": str(variables.get("inquiry_freight", "0.00")),
            "inquiry_delivery_time": int(variables.get("inquiry_delivery_time", 0)),
            "quote_other_fee": str(variables.get("quote_other_fee", "7")),
            "quote_freight": str(variables.get("quote_freight", "8")),
            "quote_delivery_time": str(variables.get("quote_delivery_time", "9")),
            "real_other_fee": str(variables.get("real_other_fee", "7")),
            "real_freight": str(variables.get("real_freight", "8")),
            "sku_info": sku_info,
        }
        _call_admin_api(session, base_url, "/admin/samplesConfirmed", {
            "order_sn": sample_order_sn, "warehouse_city": warehouse_city,
            "is_special_quote": bool(variables.get("is_special_quote", True)),
            "y_response": str(variables.get("y_response", "")),
            "quote_info": quote_info,
        }, timeout, admin_token, variables, log, "samplesConfirmed")

        # 业务开始报价
        _call_admin_api(session, base_url, "/admin/samplesStartQuote",
                        {"order_sn": sample_order_sn},
                        timeout, admin_token, variables, log, "samplesStartQuote")

        # 报价给客户
        _call_admin_api(session, base_url, "/admin/samplesQuoteToUser",
                        {"order_sn": sample_order_sn, "warehouse_city": warehouse_city},
                        timeout, admin_token, variables, log, "samplesQuoteToUser")

        # ── 6. 客户余额支付 ──
        client_token2, _, _ = _oem_client_login(session, base_url, variables, timeout)
        pay_payload = _oem_post_json(
            session, base_url, "/api/balancePayOrder",
            {"order_sn": sample_order_sn, "coupon_id": str(variables.get("coupon_id") or "")},
            timeout, token=client_token2, is_admin=False, variables=variables,
        )
        if not pay_payload.get("success") or pay_payload.get("code") not in (0, "0", None):
            _step(log, "balancePayOrder", pay_payload, {"url": "/api/balancePayOrder", "method": "POST"})
            raise RuntimeError(f"余额支付失败: {_translate_oem_msg(pay_payload.get('msg'))}")
        serial_number = str((pay_payload.get("data") or {}).get("serial_number") or "")
        _step(log, "balancePayOrder", pay_payload, {"url": "/api/balancePayOrder", "method": "POST"},
              {"serial_number": serial_number, "success": True})

        # ── 7. 后台开始采购 ──
        _call_admin_api(session, base_url, "/admin/samplesStartPurchase",
                        {"order_sn": sample_order_sn},
                        timeout, admin_token, variables, log, "samplesStartPurchase")

        # ── 8. 采购提交物流号 ──
        _call_admin_api(session, base_url, "/admin/samplesDispatch", {
            "order_sn": sample_order_sn,
            "express_id": int(variables.get("express_id") or 1039),
            "express_no": str(variables.get("express_no") or sample_order_sn[-6:] or "000000"),
            "express_remark": str(variables.get("express_remark") or ""),
        }, timeout, admin_token, variables, log, "samplesDispatch")

        # ── 9. 核查签收 ──
        _call_admin_api(session, base_url, "/admin/orderSign",
                        {"order_sn": sample_order_sn},
                        timeout, admin_token, variables, log, "orderSign")

        # ── 10. 开始核查货物 ──
        _call_admin_api(session, base_url, "/admin/checkStart",
                        {"order_sn": sample_order_sn},
                        timeout, admin_token, variables, log, "checkStart")

        # ── 11. 提交验货报告 ──
        report_images_raw = variables.get("check_report_images", "")
        report_images = [u.strip() for u in report_images_raw.replace("\n", ",").split(",") if u.strip()]
        if report_images:
            check_body = {
                "order_sn": sample_order_sn,
                "samples_report_video": [],
                "samples_report_image": [],
                "video": [],
                "image": report_images,
                "remark": str(variables.get("check_report_remark", "")),
            }
            _call_admin_api(session, base_url, "/admin/checkReport",
                            check_body, timeout, admin_token, variables, log, "checkReport")

        # ── 12. 获取验货明细 ──
        try:
            check_detail_resp = _call_admin_api(session, base_url, "/admin/checkDetail",
                                                {"order_sn": sample_order_sn},
                                                timeout, admin_token, variables, log, "checkDetail")
        except RuntimeError:
            check_detail_resp = {"data": None}
        check_detail_data = check_detail_resp.get("data") if isinstance(check_detail_resp, dict) else None

        # ── 13. 验货完成提交 ──
        check_list = []
        if check_detail_data and isinstance(check_detail_data, list):
            for item in check_detail_data:
                check_list.append({
                    "id": item.get("id", 0),
                    "check_id": item.get("check_id", 0),
                    "sku_tr": str(item.get("sku_tr", "")),
                    "sku": str(item.get("sku", "")),
                    "sku_image": str(item.get("sku_image", "")),
                    "num": item.get("num", 1),
                    "price": str(item.get("price", "0.00")),
                    "option": item.get("option", []),
                    "check_num": str(item.get("num", 1)),
                    "weight": str(item.get("weight", "1")),
                    "size": str(item.get("size", "0")),
                    "length": item.get("length", 1),
                    "width": item.get("width", 1),
                    "height": item.get("height", 1),
                    "possible_num": item.get("num", 1),
                    "storage_num": 0,
                    "shelves_num": 0,
                    "wait_inspect_num": item.get("num", 1),
                    "inspect_num": item.get("num", 1),
                    "bad_num": 0,
                    "good_num": item.get("num", 1),
                    "keep_sample_num": int(variables.get("keep_sample_num", 0)),
                    "keep_sample_possible_num": int(variables.get("keep_sample_possible_num", 0)),
                    "keep_sample_shelves_num": 0,
                    "warehouse_shelves": [],
                    "after_sale_num": 0,
                    "shelve_num": item.get("num", 1),
                    "checked_listing": True,
                })
        if check_list:
            _call_admin_api(session, base_url, "/admin/checkComplete",
                            {"order_sn": sample_order_sn, "check_list": check_list},
                            timeout, admin_token, variables, log, "checkComplete")

        # ── 14. 业务提交验货报告给客户 ──
        _call_admin_api(session, base_url, "/admin/samplesCheckRaise",
                        {"order_sn": sample_order_sn},
                        timeout, admin_token, variables, log, "samplesCheckRaise")

        # ── 15. 核查上架 ──
        try:
            shelve_detail_resp = _call_admin_api(session, base_url, "/admin/checkDetail",
                                                 {"order_sn": sample_order_sn},
                                                 timeout, admin_token, variables, log, "checkDetail-shelve")
        except RuntimeError:
            shelve_detail_resp = {"data": None}
        shelve_data = shelve_detail_resp.get("data") if isinstance(shelve_detail_resp, dict) else None
        shelve_info = []
        if shelve_data and isinstance(shelve_data, list):
            for item in shelve_data:
                shelve_info.append({
                    "id": item.get("id", 0),
                    "check_id": item.get("check_id", 0),
                    "sku_tr": str(item.get("sku_tr", "")),
                    "sku": str(item.get("sku", "")),
                    "sku_image": str(item.get("sku_image", "")),
                    "num": item.get("num", 1),
                    "price": str(item.get("price", "0.00")),
                    "option": item.get("option", []),
                    "check_num": item.get("num", 1),
                    "weight": item.get("weight", 1),
                    "size": "1*1*1",
                    "length": 1,
                    "width": 1,
                    "height": 1,
                    "possible_num": item.get("num", 1),
                    "storage_num": 0,
                    "shelves_num": 0,
                    "wait_inspect_num": item.get("num", 1),
                    "inspect_num": item.get("num", 1),
                    "bad_num": 0,
                    "good_num": item.get("num", 1),
                    "keep_sample_num": int(variables.get("keep_sample_num", 0)),
                    "keep_sample_possible_num": int(variables.get("keep_sample_possible_num", 0)),
                    "keep_sample_shelves_num": 0,
                    "warehouse_shelves": [],
                    "after_sale_num": 0,
                    "shelve_num": item.get("num", 1),
                    "checked_listing": True,
                })
        if shelve_info:
            _call_admin_api(session, base_url, "/admin/orderShelve", {
                "order_sn": sample_order_sn,
                "shelve_info": shelve_info,
                "warehouse_city": warehouse_city,
            }, timeout, admin_token, variables, log, "orderShelve")

        summary = {"order_sn": sample_order_sn, "serial_number": serial_number, "reason": "样品单全流程执行成功"}
        return _finish_named(OEM_SAMPLE_FULL_FLOW_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_SAMPLE_FULL_FLOW_NAME, log, False, {"reason": str(exc), "error": str(exc)})


def _impl_run_oem_sample_balance_pay_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 样品单余额支付：前台登录 → 余额支付。

    接口 POST /api/balancePayOrder
    可配置变量：
        - order_sn: 样品单号（必填）
        - coupon_id: 优惠券ID（可选）
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")
    order_sn = str(variables.get("order_sn") or "").strip()
    if not order_sn:
        return _finish_named(OEM_BALANCE_PAY_NAME, {}, False, {"reason": "缺少必填参数：order_sn"})

    log: Dict[str, Any] = {
        "script": OEM_BALANCE_PAY_NAME, "mode": "oem_balance_pay",
        "base_url": base_url, "order_sn": order_sn, "started_at": datetime.now(), "steps": [],
    }
    try:
        session = requests.Session()
        client_token, _, _ = _oem_client_login(session, base_url, variables, timeout)
        _step(log, "client_login", {"account": variables.get("account") or "12345678990"},
              {"url": "/client/userLogin", "method": "POST"}, {"token": client_token[:16] + "..."})

        payload = _oem_post_json(session, base_url, "/api/balancePayOrder",
                                 {"order_sn": order_sn, "coupon_id": str(variables.get("coupon_id") or "")},
                                 timeout, token=client_token, is_admin=False, variables=variables)
        if not payload.get("success") or payload.get("code") not in (0, "0", None):
            _step(log, "balancePayOrder", payload, {"url": "/api/balancePayOrder", "method": "POST"})
            return _finish_named(OEM_BALANCE_PAY_NAME, log, False,
                                 {"reason": f"余额支付失败: {_translate_oem_msg(payload.get('msg'))}", "error": payload.get("msg")})

        data = payload.get("data") or {}
        serial_number = str(data.get("serial_number") or "")
        _step(log, "balancePayOrder", payload, {"url": "/api/balancePayOrder", "method": "POST"},
              {"serial_number": serial_number, "success": True})
        summary = {"order_sn": order_sn, "serial_number": serial_number, "reason": "余额支付成功"}
        return _finish_named(OEM_BALANCE_PAY_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_BALANCE_PAY_NAME, log, False, {"reason": str(exc), "error": str(exc)})


def run_oem_sample_order_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_oem_sample_order_script(env, variables)


def run_oem_sample_admin_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_oem_sample_admin_flow_script(env, variables)


def run_oem_sample_full_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_oem_sample_full_flow_script(env, variables)


def run_oem_sample_balance_pay_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_oem_sample_balance_pay_script(env, variables)
