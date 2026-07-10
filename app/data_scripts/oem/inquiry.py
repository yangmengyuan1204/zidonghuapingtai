from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'Dict',
    'Env',
    'OEM_DEFAULT_BASE_URL',
    'OEM_DEFAULT_FRONTEND_ORIGIN',
    'OEM_FULL_INQUIRY_SCRIPT_NAME',
    'OEM_SCRIPT_NAME',
    'Tuple',
    '_as_int',
    '_finish_named',
    '_oem_admin_login',
    '_oem_client_login',
    '_oem_extract_factory_iid',
    '_oem_parse_factory_urls',
    '_oem_post_json',
    '_oem_query_inquiry_detail',
    '_step',
    'datetime',
    'ensure_report_dirs',
    'requests',
    'time',
    'urljoin',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl_run_oem_new_inquiry_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 创建询价单脚本：前台登录 -> 创建询价单，返回 inquiry_sn。"""
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")

    log: Dict[str, Any] = {
        "script": OEM_SCRIPT_NAME,
        "mode": "oem_new_inquiry",
        "base_url": base_url,
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
            {"url": "/api/login", "method": "POST"},
            {"token": client_token[:16] + "..."},
        )

        # 构造创建询价单请求体
        sku_info = variables.get("sku_info")
        if not isinstance(sku_info, list):
            sku_info = [
                {"sku": variables.get("sku1") or "sku1", "num": variables.get("sku1_num") or "1"},
                {"sku": variables.get("sku2") or "sku2", "num": variables.get("sku2_num") or "2"},
                {"sku": variables.get("sku3") or "sku3", "num": variables.get("sku3_num") or "3"},
            ]
        body: Dict[str, Any] = {
            "goods_name": variables.get("goods_name") or "测试商品",
            "hope_min_price": variables.get("hope_min_price") or "1",
            "hope_max_price": variables.get("hope_max_price") or "100",
            "hope_futures": variables.get("hope_futures") or "10",
            "material": variables.get("material") or "",
            "sku_info": sku_info,
            "is_temporarily": False,
            "goods_type": int(variables.get("goods_type") or 1),
            "goods_detail": variables.get("goods_detail") or "",
            "num": int(variables.get("num") or sum(int(s.get("num") or 0) for s in sku_info)),
            "customize_detail": variables.get("customize_detail") or "",
            "factory_urls": _oem_parse_factory_urls(variables),
            "factory_type": int(variables.get("factory_type") or 3),
            "goods_file": variables.get("goods_file") or [],
            "goods_img": variables.get("goods_img") or "",
            "goods_other_img": variables.get("goods_other_img") or [],
            "provide_prototype": False,
            "register_forward": variables.get("register_forward") or "",
            "forward_order": variables.get("forward_order") or {"forward_sn": "", "num": "", "goods_value": ""},
        }

        # 调用创建询价单接口（前台 token 注入 Authorization: Bearer 头）
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {client_token}",
            "Origin": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN),
            "Referer": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN).rstrip("/") + "/",
        }
        url = urljoin(base_url.rstrip("/") + "/", "/api/newInquiry")
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
            raise RuntimeError(f"创建询价单请求失败: {last_error}")

        if not payload.get("success") or payload.get("code") not in (0, "0", None):
            _step(log, "new_inquiry", payload, {"url": "/api/newInquiry", "method": "POST"})
            return _finish_named(
                OEM_SCRIPT_NAME,
                log,
                False,
                {"reason": f"创建询价单失败: {payload.get('msg')}", "error": payload.get("msg"), "payload": payload},
            )

        inquiry_sn = str(payload.get("data") or "")
        _step(
            log,
            "new_inquiry",
            payload,
            {"url": "/api/newInquiry", "method": "POST"},
            {"inquiry_sn": inquiry_sn, "success": True},
        )

        summary = {"inquiry_sn": inquiry_sn, "reason": "创建询价单成功"}
        return _finish_named(OEM_SCRIPT_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_SCRIPT_NAME, log, False, {"reason": str(exc), "error": str(exc)})


def _impl_run_oem_full_inquiry_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 询价单全流程脚本：前台提出询价单 → 后台翻译 → 询价 → 报价，直至报价成功。

    支持从指定 order_sn 开始（跳过创建），便于调试中间阶段。
    各阶段可通过开关变量跳过：skip_create / skip_translate / skip_inquiry / skip_quote。
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")

    log: Dict[str, Any] = {
        "script": OEM_FULL_INQUIRY_SCRIPT_NAME,
        "mode": "oem_full_inquiry",
        "base_url": base_url,
        "started_at": datetime.now(),
        "steps": [],
    }

    try:
        session = requests.Session()
        order_sn = str(variables.get("order_sn") or "").strip()
        admin_token = ""
        client_token = ""

        # ─── 阶段1：询价单提出（前台登录 + 创建询价单） ─────────────
        if not variables.get("skip_create") and not order_sn:
            client_token, user_id, _ = _oem_client_login(session, base_url, variables, timeout)
            _step(log, "client_login", {"account": variables.get("account") or "12345678990"},
                  {"url": "/api/login", "method": "POST"}, {"token": client_token[:16] + "..."})

            sku_info = variables.get("sku_info")
            if not isinstance(sku_info, list):
                sku_info = [
                    {"sku": variables.get("sku1") or "sku1", "num": int(variables.get("sku1_num") or 1)},
                    {"sku": variables.get("sku2") or "sku2", "num": int(variables.get("sku2_num") or 2)},
                    {"sku": variables.get("sku3") or "sku3", "num": int(variables.get("sku3_num") or 3)},
                ]
            # 创建询价单前校验工厂链接：缺 factory_urls 会导致后端不生成 detail_list，
            # 后续询价阶段无法工厂报价，inquiryComplete 会报"请报价至少一条数据后点击"
            factory_urls_for_create = _oem_parse_factory_urls(variables)
            if not factory_urls_for_create:
                _step(log, "new_inquiry", {"order_sn": ""},
                      {"url": "/api/newInquiry", "method": "POST"},
                      {"success": False, "msg": "缺少 factory_urls，无法走通询价全流程"})
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": "创建询价单失败: 缺少 factory_urls，请在前端配置工厂链接后再执行"})
            create_body: Dict[str, Any] = {
                "goods_name": variables.get("goods_name") or "测试商品",
                "hope_min_price": variables.get("hope_min_price") or "1",
                "hope_max_price": variables.get("hope_max_price") or "100",
                "hope_futures": variables.get("hope_futures") or "10",
                "material": variables.get("material") or "",
                "sku_info": sku_info,
                "is_temporarily": False,
                "goods_type": int(variables.get("goods_type") or 1),
                "goods_class": int(variables.get("goods_class") or 110),
                "goods_detail": variables.get("goods_detail") or "",
                "num": int(variables.get("num") or sum(int(s.get("num") or 0) for s in sku_info)),
                "customize_detail": variables.get("customize_detail") or "",
                "factory_urls": _oem_parse_factory_urls(variables),
                "factory_type": int(variables.get("factory_type") or 3),
                "goods_file": variables.get("goods_file") or [],
                "goods_img": variables.get("goods_img") or "",
                "goods_other_img": variables.get("goods_other_img") or [],
                "provide_prototype": False,
                "register_forward": variables.get("register_forward") or "",
                "forward_order": variables.get("forward_order") or {"forward_sn": "", "num": "", "goods_value": ""},
            }
            create_headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {client_token}",
                "Origin": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN),
                "Referer": variables.get("frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN).rstrip("/") + "/",
            }
            url = urljoin(base_url.rstrip("/") + "/", "/api/newInquiry")
            response = session.post(url, json=create_body, headers=create_headers, timeout=timeout)
            payload = response.json()
            if not payload.get("success") and payload.get("code") not in (0, "0", None):
                _step(log, "new_inquiry", create_body, {"url": "/api/newInquiry", "method": "POST"}, payload)
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"创建询价单失败: {payload.get('msg')}", "error": payload.get("msg")})
            order_sn = str(payload.get("data") or "")
            _step(log, "new_inquiry", create_body, {"url": "/api/newInquiry", "method": "POST"},
                  {"inquiry_sn": order_sn, "success": True})
        else:
            _step(log, "skip_create", {"order_sn": order_sn}, {"note": "跳过创建，使用传入 order_sn"}, {"skipped": True})

        if not order_sn:
            return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False, {"reason": "未获取到 order_sn"})

        # ─── 后台登录（后续阶段都需要） ─────────────────────────
        admin_token = _oem_admin_login(session, base_url, variables, timeout)
        _step(log, "admin_login", {"username": variables.get("backend_account") or "admin"},
              {"url": "/admin/login", "method": "POST"}, {"token": admin_token[:16] + "..."})

        # 查询询价单完整详情
        detail = _oem_query_inquiry_detail(session, base_url, admin_token, order_sn, timeout, variables)
        _step(log, "query_detail", {"order_sn": order_sn}, {"url": "/admin/inquiryDetail", "method": "POST"},
              {"inquiry_id": detail.get("id"), "detail_count": len(detail.get("detail_list") or []),
               "sku_count": len(detail.get("sku_info") or [])})

        # ─── 阶段2：翻译阶段（提交审核 + 审核完成提交采购） ───────────────
        if not variables.get("skip_translate"):
            translate_body: Dict[str, Any] = {
                "is_temp": False,
                "order_sn": order_sn,
                "goods_name_tr": variables.get("goods_name_tr") or (detail.get("goods_name_tr") or detail.get("goods_name") or ""),
                "material_tr": variables.get("material_tr") or (detail.get("material_tr") or detail.get("material") or ""),
                "customize_detail_tr": variables.get("customize_detail_tr") or (detail.get("customize_detail_tr") or detail.get("customize_detail") or ""),
                "goods_detail_tr": variables.get("goods_detail_tr") or (detail.get("goods_detail_tr") or detail.get("goods_detail") or ""),
                "goods_file_tr": detail.get("goods_file_tr") or [],
                "sku_info": detail.get("sku_info") or [],
                "goods_id": str(detail.get("goods_id") or ""),
                "goods_class": int(variables.get("goods_class") or 110),
                "y_remark": detail.get("y_remark") or "",
                "user_remark": detail.get("user_remark") or "",
            }
            tp = _oem_post_json(session, base_url, "/admin/inquiryTranslate", translate_body, timeout,
                                token=admin_token, is_admin=True, variables=variables)
            _step(log, "translate_save", translate_body, {"url": "/admin/inquiryTranslate", "method": "POST"},
                  {"success": tp.get("success"), "msg": tp.get("msg")})
            if not tp.get("success") and tp.get("code") not in (0, "0", None):
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"翻译保存失败: {tp.get('msg')}", "order_sn": order_sn})

            # 提交给采购（审核完成后推进状态到可询价）
            ap = _oem_post_json(session, base_url, "/admin/inquiryTranslateAudit", {"order_sn": order_sn}, timeout,
                                token=admin_token, is_admin=True, variables=variables)
            _step(log, "translate_audit", {"order_sn": order_sn}, {"url": "/admin/inquiryTranslateAudit", "method": "POST"},
                  {"success": ap.get("success"), "msg": ap.get("msg")})
            if not ap.get("success") and ap.get("code") not in (0, "0", None):
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"翻译审核失败: {ap.get('msg')}", "order_sn": order_sn})
            # 重新查询详情获取最新状态
            detail = _oem_query_inquiry_detail(session, base_url, admin_token, order_sn, timeout, variables)
        else:
            _step(log, "skip_translate", {}, {"note": "跳过翻译阶段"}, {"skipped": True})

        # ─── 阶段3：询价阶段（开始询价 + 编辑工厂 + 工厂报价 + 询价完成） ──
        if not variables.get("skip_inquiry"):
            # 开始询价：goods_class 详情返回可能是对象，需确保为有效数字 id
            gc = detail.get("goods_class")
            if isinstance(gc, dict):
                detail["goods_class"] = gc.get("id") or int(variables.get("goods_class") or 110)
            elif not isinstance(gc, int) or gc == 0:
                detail["goods_class"] = int(variables.get("goods_class") or 110)
            sip = _oem_post_json(session, base_url, "/admin/inquiryStartInquiry", detail, timeout,
                                 token=admin_token, is_admin=True, variables=variables)
            _step(log, "start_inquiry", {"order_sn": order_sn}, {"url": "/admin/inquiryStartInquiry", "method": "POST"},
                  {"success": sip.get("success"), "msg": sip.get("msg")})
            if not sip.get("success") and sip.get("code") not in (0, "0", None):
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"开始询价失败: {sip.get('msg')}", "order_sn": order_sn})

            # 重新查询详情，拿到 detail_list 的 id
            detail = _oem_query_inquiry_detail(session, base_url, admin_token, order_sn, timeout, variables)
            detail_list = detail.get("detail_list") or []
            # 兜底校验：detail_list 为空说明后端未生成工厂明细，直接报错而非空跑循环
            if not detail_list:
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"询价单 {order_sn} 无工厂明细 detail_list（可能创建时未传 factory_urls），无法进行工厂报价",
                                      "order_sn": order_sn})
            factory_img = variables.get("factory_img") or "https://img.alicdn.com/placeholder.jpg"
            salesman = variables.get("salesman") or "测试业务员"
            salesman_phone = variables.get("salesman_phone") or "13800000000"
            # 全局默认值（向后兼容：无 factory_quotes 时所有工厂共用这组）
            samples_price_default = variables.get("samples_price") or "12.00"
            large_price_default = variables.get("large_price") or "11.00"
            large_other_fee_default = variables.get("large_other_fee") or "12.00"
            large_freight_default = variables.get("large_freight") or "11.00"
            large_delivery_time_default = int(variables.get("large_delivery_time") or 15)
            large_deposit_rate_default = variables.get("large_deposit_rate") or "100"
            real_samples_price_default = variables.get("real_samples_price") or "10.00"
            real_large_price_default = variables.get("real_large_price") or "10.00"
            # 每工厂差异化报价（前端按 factory_urls 行数展开多组）
            factory_quotes = variables.get("factory_quotes") or []

            for idx, d_item in enumerate(detail_list):
                detail_id = d_item.get("id")
                factory_url = d_item.get("factory_url") or ""
                factory_submit_info = d_item.get("factory_submit_info") or factory_url
                factory_iid = d_item.get("factory_iid") or _oem_extract_factory_iid(factory_url)
                factory_name = d_item.get("factory_name") or "测试工厂"
                # 按工厂 idx 取该工厂的报价字段，缺失时用全局默认
                fq = factory_quotes[idx] if idx < len(factory_quotes) and isinstance(factory_quotes[idx], dict) else {}
                samples_price = fq.get("samples_price") or samples_price_default
                large_price = fq.get("large_price") or large_price_default
                large_other_fee = fq.get("large_other_fee") or large_other_fee_default
                large_freight = fq.get("large_freight") or large_freight_default
                large_delivery_time = int(fq.get("large_delivery_time") or large_delivery_time_default)
                large_deposit_rate = fq.get("large_deposit_rate") or large_deposit_rate_default
                real_samples_price = fq.get("real_samples_price") or real_samples_price_default
                real_large_price = fq.get("real_large_price") or real_large_price_default
                # 编辑工厂
                edit_body: Dict[str, Any] = {
                    "detail_id": detail_id,
                    "factory_iid": factory_iid,
                    "factory_name": factory_name,
                    "factory_province": d_item.get("factory_province") or "",
                    "factory_city": d_item.get("factory_city") or "",
                    "factory_img": factory_img,
                    "factory_url": factory_url,
                    "salesman": salesman,
                    "salesman_phone": salesman_phone,
                    "goods_url": d_item.get("goods_url") or "",
                }
                ep = _oem_post_json(session, base_url, "/admin/factoryEdit", edit_body, timeout,
                                    token=admin_token, is_admin=True, variables=variables)
                _step(log, f"factory_edit_{idx+1}", edit_body, {"url": "/admin/factoryEdit", "method": "POST"},
                      {"detail_id": detail_id, "factory_iid": factory_iid, "factory_url": factory_url, "success": ep.get("success"), "msg": ep.get("msg")})

                # 工厂报价（基于 detail 原有字段 + 报价参数覆盖）
                sku_detail = d_item.get("sku_detail") or []
                for sku in sku_detail:
                    sku["samples_price"] = samples_price
                    sku["large_price"] = large_price
                    sku["real_samples_price"] = real_samples_price
                    sku["real_large_price"] = real_large_price
                # 以 d_item 为基底，只覆盖报价相关字段，避免漏字段导致"参数错误"
                quote_body = dict(d_item)
                quote_body.update({
                    "status": 0, "g_cant_quote": 0, "is_read": 1,
                    "factory_type": d_item.get("factory_type") or 1,
                    "factory_submit_info": factory_submit_info,
                    "factory_iid": factory_iid, "factory_name": factory_name,
                    "factory_province": d_item.get("factory_province") or "浙江省",
                    "factory_city": d_item.get("factory_city") or "杭州市",
                    "factory_url": factory_url, "factory_img": factory_img,
                    "goods_url": d_item.get("goods_url") or "",
                    "samples_other_fee": d_item.get("samples_other_fee") or "0.00",
                    "samples_freight": d_item.get("samples_freight") or "0.00",
                    "samples_delivery_time": d_item.get("samples_delivery_time") or 0,
                    "real_samples_other_fee": d_item.get("real_samples_other_fee") or "0.00",
                    "real_samples_freight": d_item.get("real_samples_freight") or "0.00",
                    "large_other_fee": large_other_fee, "large_freight": large_freight,
                    "large_delivery_time": large_delivery_time, "large_deposit_rate": large_deposit_rate,
                    "real_large_other_fee": variables.get("real_large_other_fee") or "10.00",
                    "real_large_freight": variables.get("real_large_freight") or "10.00",
                    "factory_salesman_id": 0, "warehouse_city": 0,
                    "samples_warehouse_city": 1, "large_warehouse_city": 1,
                    "quote_admin": 0, "is_special_quote": False,
                    "sku_detail": sku_detail, "salesman": salesman, "salesman_phone": salesman_phone,
                    "is_temporarily": False, "detail_id": detail_id,
                })
                qp = _oem_post_json(session, base_url, "/admin/factoryQuote", quote_body, timeout,
                                    token=admin_token, is_admin=True, variables=variables)
                _step(log, f"factory_quote_{idx+1}", {"detail_id": detail_id}, {"url": "/admin/factoryQuote", "method": "POST"},
                      {"success": qp.get("success"), "msg": qp.get("msg")})
                if not qp.get("success") and qp.get("code") not in (0, "0", None):
                    return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                         {"reason": f"工厂{idx+1}报价失败: {qp.get('msg')}", "order_sn": order_sn})

            # 询价完成（detail_list 各 status=1）
            for d_item in detail_list:
                d_item["status"] = 1
            detail["detail_list"] = detail_list
            detail["g_admin_status"] = 2
            cp = _oem_post_json(session, base_url, "/admin/inquiryComplete", detail, timeout,
                                token=admin_token, is_admin=True, variables=variables)
            _step(log, "inquiry_complete", {"order_sn": order_sn}, {"url": "/admin/inquiryComplete", "method": "POST"},
                  {"success": cp.get("success"), "msg": cp.get("msg")})
            if not cp.get("success") and cp.get("code") not in (0, "0", None):
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"询价完成失败: {cp.get('msg')}", "order_sn": order_sn})
        else:
            _step(log, "skip_inquiry", {}, {"note": "跳过询价阶段"}, {"skipped": True})

        # ─── 阶段4：报价阶段（开始报价 → 报价给用户 → 询价单报价完成） ─────────
        if not variables.get("skip_quote"):
            detail = _oem_query_inquiry_detail(session, base_url, admin_token, order_sn, timeout, variables)
            detail_list = detail.get("detail_list") or []
            quote_admin = int(detail.get("g_id") or 19)
            factory_salesman_id = 236

            # 开始报价（必须先调用，否则后续 inquiryQuoteComplate 报"当前状态无法操作"）
            sq = _oem_post_json(session, base_url, "/admin/inquiryStartQuote",
                                {"order_sn": order_sn}, timeout,
                                token=admin_token, is_admin=True, variables=variables)
            _step(log, "start_quote", {"order_sn": order_sn},
                  {"url": "/admin/inquiryStartQuote", "method": "POST"},
                  {"success": sq.get("success"), "msg": sq.get("msg")})
            if not sq.get("success") and sq.get("code") not in (0, "0", None):
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"开始报价失败: {sq.get('msg')}", "order_sn": order_sn})

            for idx, d_item in enumerate(detail_list):
                detail_id = d_item.get("id")
                # 报价给用户：基于 d_item 覆盖报价相关字段
                quote_to_user_body = dict(d_item)
                quote_to_user_body.update({
                    "status": 1, "is_read": 0,
                    "factory_salesman_id": factory_salesman_id,
                    "quote_admin": quote_admin,
                    "is_special_quote": False,
                    "is_temporarily": False,
                    "detail_id": detail_id,
                })
                qp2 = _oem_post_json(session, base_url, "/admin/factoryQuoteToUser", quote_to_user_body, timeout,
                                     token=admin_token, is_admin=True, variables=variables)
                _step(log, f"quote_to_user_{idx+1}", {"detail_id": detail_id},
                      {"url": "/admin/factoryQuoteToUser", "method": "POST"},
                      {"success": qp2.get("success"), "msg": qp2.get("msg")})
                if not qp2.get("success") and qp2.get("code") not in (0, "0", None):
                    return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                         {"reason": f"工厂{idx+1}报价给用户失败: {qp2.get('msg')}", "order_sn": order_sn})

            # 重新查询详情，拿到最新状态后设置 status=2
            detail = _oem_query_inquiry_detail(session, base_url, admin_token, order_sn, timeout, variables)
            detail_list = detail.get("detail_list") or []
            for d_item in detail_list:
                d_item["status"] = 2
            detail["detail_list"] = detail_list

            # 询价单报价完成（发送完整 detail body）
            qcp = _oem_post_json(session, base_url, "/admin/inquiryQuoteComplate", detail, timeout,
                                 token=admin_token, is_admin=True, variables=variables)
            _step(log, "quote_complete", {"order_sn": order_sn}, {"url": "/admin/inquiryQuoteComplate", "method": "POST"},
                  {"success": qcp.get("success"), "msg": qcp.get("msg")})
            if not qcp.get("success") and qcp.get("code") not in (0, "0", None):
                return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False,
                                     {"reason": f"询价单报价完成失败: {qcp.get('msg')}", "order_sn": order_sn})
        else:
            _step(log, "skip_quote", {}, {"note": "跳过报价阶段"}, {"skipped": True})

        final_detail = detail_list[0] if detail_list else {}
        final_sku_list = final_detail.get("sku_detail") or []
        final_sku = final_sku_list[0] if final_sku_list else {}
        summary = {
            "order_sn": order_sn,
            "reason": "OEM 询价单全流程执行成功",
            "samples_price_return": final_sku.get("samples_price_return") or "0.00",
            "samples_other_fee": final_detail.get("samples_other_fee") or "0.00",
            "samples_freight": final_detail.get("samples_freight") or "0.00",
            "samples_delivery_time": final_detail.get("samples_delivery_time") or 0,
            "factory_img": final_detail.get("factory_img") or "",
        }
        return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_FULL_INQUIRY_SCRIPT_NAME, log, False, {"reason": str(exc), "error": str(exc)})


def run_oem_new_inquiry_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_oem_new_inquiry_script(env, variables)


def run_oem_full_inquiry_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_oem_full_inquiry_flow_script(env, variables)
