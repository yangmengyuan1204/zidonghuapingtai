from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'Dict',
    'Env',
    'OEM_BULK_ORDER_NAME',
    'OEM_DEFAULT_BASE_URL',
    'Tuple',
    '_as_int',
    '_finish_named',
    '_oem_build_option_for_sku',
    '_oem_build_warehouse_for_sku',
    '_oem_client_login',
    '_oem_create_new_order',
    '_oem_edit_sku_image',
    '_oem_generate_large_order_sn',
    '_oem_order_preview',
    '_oem_query_option_list',
    '_step',
    'datetime',
    'ensure_report_dirs',
    'fetch_oem_full_quote',
    'json',
    'requests',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl_run_oem_bulk_order_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 大货单下单脚本：输入询价单号 → 查询报价 → 获取 option → 上传图片 → 创建大货单。

    阶段：
      1. 前台登录获取 token
      2. 查询报价详情（fetch_oem_full_quote）
      3. 查询 option 列表（/common/common/optionList）
      4. 订单预览（/api/orderPreviews，type=2）
      5. 上传图片到 OSS 并调用 editSkuImage（如提供 bulk_images）
      6. 创建大货单（POST /api/newOrder，type=2）
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or OEM_DEFAULT_BASE_URL).rstrip("/")
    order_sn = str(variables.get("order_sn") or "").strip()

    log: Dict[str, Any] = {
        "script": OEM_BULK_ORDER_NAME,
        "mode": "oem_bulk_order",
        "base_url": base_url,
        "order_sn": order_sn,
        "started_at": datetime.now(),
        "steps": [],
    }

    if not order_sn:
        return _finish_named(OEM_BULK_ORDER_NAME, log, False,
                             {"reason": "缺少必填参数：询价单号 order_sn 不能为空"})

    try:
        session = requests.Session()

        # ── 阶段 1：前台登录 ──
        client_token, user_id, user_info_error = _oem_client_login(session, base_url, variables, timeout)

        # 按 OEM 前端规则生成大货单号（D{timestamp}-{user_id}-{type}）
        generated_large_order_sn = _oem_generate_large_order_sn(order_sn, user_id)

        _step(log, "client_login", {"account": variables.get("account") or "12345678990"},
              {"url": "/api/login + /api/userInfo", "method": "POST"},
              {"user_id": user_id, "has_token": bool(client_token),
               "generated_large_order_sn": generated_large_order_sn,
               "user_info_error": user_info_error})

        # ── 阶段 2：查询报价详情 ──
        quote_data = fetch_oem_full_quote(order_sn, variables)
        if not quote_data:
            return _finish_named(OEM_BULK_ORDER_NAME, log, False,
                                 {"reason": f"询价单 {order_sn} 无报价数据或接口返回异常"})
        detail_id = str(quote_data.get("detail_id") or variables.get("inquiry_detail_id") or "").strip()
        if not detail_id:
            records = quote_data.get("list") or []
            if records and isinstance(records[0], dict):
                detail_id = str(records[0].get("id") or "").strip()
        if not detail_id:
            return _finish_named(OEM_BULK_ORDER_NAME, log, False,
                                 {"reason": "未能从询价单解析出 detail_id"})

        quote_detail = quote_data.get("quote_detail") or {}
        large_info = quote_detail.get("large_info") or {}
        detail_list = quote_data.get("list") or []
        goods_name = (detail_list[0] if detail_list and isinstance(detail_list[0], dict) else {}).get("goods_name") or ""

        _step(log, "query_quote", {"order_sn": order_sn},
              {"url": "/api/inquiryDetail + /api/quoteDetail", "method": "POST"},
              {"detail_id": detail_id, "factory_count": len(detail_list),
               "has_large": bool(large_info), "goods_name": goods_name})

        # 从当前 detail_id 对应的 record 中提取每个 SKU 的大货单价
        # OEM 后端要求 option.large_price 必须为该 SKU 的大货单价（来自 sku_detail.large_price），
        # 而非 option 自身的 price，否则创建大货单会返回 code=10000
        sku_large_price_map: Dict[str, str] = {}
        for rec in detail_list:
            if not isinstance(rec, dict) or str(rec.get("id")) != str(detail_id):
                continue
            for sd in (rec.get("sku_detail") or []):
                if not isinstance(sd, dict):
                    continue
                gsid = sd.get("goods_sku_id") or sd.get("sku_id")
                lp = sd.get("large_price")
                if gsid is not None and lp is not None:
                    sku_large_price_map[str(gsid)] = str(lp)
            break

        # ── 阶段 3：查询 option 列表 ──
        option_list = _oem_query_option_list(session, base_url, client_token, timeout, variables)
        _step(log, "query_option_list", {"detail_id": detail_id},
              {"url": "/common/common/optionList", "method": "POST"},
              {"option_count": len(option_list)})

        # ── 阶段 4：订单预览（type=2 大货单） ──
        preview_data = _oem_order_preview(
            session, base_url, client_token, detail_id, timeout, variables,
            large_order_sn=generated_large_order_sn,
        )
        _step(log, "order_preview", {"detail_id": detail_id, "type": 2},
              {"url": "/api/orderPreviews", "method": "POST"},
              {"has_preview": bool(preview_data)})
        if not preview_data:
            return _finish_named(
                OEM_BULK_ORDER_NAME, log, False,
                {"reason": f"询价单 {order_sn}（detail_id={detail_id}）无大货报价信息，"
                           f"可能尚未完成报价或报价已过期。large_info 为空，无法创建大货单。"}
            )

        # 使用 OEM 前端规则生成的大货单号（而非 orderPreviews 预分配的）
        large_order_sn = generated_large_order_sn

        # ── 阶段 5：解析 SKU 列表 + 上传图片 + editSkuImage ──
        sku_list_raw = variables.get("sku_list")
        if isinstance(sku_list_raw, str) and sku_list_raw.strip().startswith("["):
            try:
                sku_list_raw = json.loads(sku_list_raw)
            except (json.JSONDecodeError, TypeError):
                sku_list_raw = []
        elif not isinstance(sku_list_raw, list):
            sku_list_raw = []
        if not sku_list_raw:
            return _finish_named(OEM_BULK_ORDER_NAME, log, False,
                                 {"reason": "sku_list 为空，请先在前端勾选要下单的 SKU"})

        # bulk_images 已是 OSS URL 列表（前端通过 /api/oem/upload-image 上传完成）
        bulk_images_raw = variables.get("bulk_images") or ""
        if isinstance(bulk_images_raw, list):
            bulk_images = [u for u in bulk_images_raw if u]
        else:
            bulk_images = [line.strip() for line in str(bulk_images_raw).splitlines() if line.strip()]

        # 为每个 SKU 构造 option + warehouse，并按需调用 editSkuImage
        sku_list_body = []
        for idx, item in enumerate(sku_list_raw):
            if not isinstance(item, dict):
                continue
            sku_id = item.get("sku_id") or item.get("goods_sku_id") or item.get("id")
            if sku_id is None:
                continue
            try:
                sku_id_int = int(sku_id)
            except (TypeError, ValueError):
                sku_id_int = sku_id
            num = _as_int(item.get("num"), 1)
            # 获取该 SKU 的大货单价（来自 sku_detail.large_price）
            sku_large_price = sku_large_price_map.get(str(sku_id_int)) or ""
            # option：优先用前端传入的（允许空列表，表示用户未勾选任何 option），否则用模板生成
            opt_input = item.get("option")
            if isinstance(opt_input, list):
                options = opt_input
                # 用 SKU 级别大货单价覆盖每个 option 的 large_price
                if sku_large_price:
                    for opt in options:
                        if isinstance(opt, dict):
                            opt["large_price"] = sku_large_price
            else:
                options = _oem_build_option_for_sku(option_list, num, large_price=sku_large_price)
            # warehouse：从变量+图片列表构造
            warehouses = _oem_build_warehouse_for_sku(idx, variables, bulk_images)
            # 若该 SKU 有对应图片，调用 editSkuImage
            sku_image_url = warehouses[0].get("image") if warehouses else ""
            if sku_image_url and isinstance(sku_id_int, int):
                try:
                    _oem_edit_sku_image(session, base_url, client_token, sku_id_int, sku_image_url, timeout, variables)
                    _step(log, "edit_sku_image", {"sku_id": sku_id_int, "sku_image": sku_image_url},
                          {"url": "/api/editSkuImage", "method": "POST"},
                          {"status": "ok"})
                except Exception as e:
                    _step(log, "edit_sku_image", {"sku_id": sku_id_int, "sku_image": sku_image_url},
                          {"url": "/api/editSkuImage", "method": "POST"},
                          {"status": "failed", "error": str(e)})
            sku_list_body.append({
                "sku_id": sku_id_int,
                "num": num,
                "option": options,
                "warehouse": warehouses,
            })

        if not sku_list_body:
            return _finish_named(OEM_BULK_ORDER_NAME, log, False,
                                 {"reason": "构造 SKU 下单列表失败，sku_list_body 为空"})

        # ── 阶段 6：创建大货单 ──
        remark = str(variables.get("remark") or "").strip()
        warehouse_city = _as_int(variables.get("warehouse_city"), 1)
        new_order_body = {
            "order_sn": large_order_sn,
            "inquiry_detail_id": detail_id,
            "type": 2,
            "sku_list": sku_list_body,
            "remark": remark,
            "warehouse_city": warehouse_city,
        }
        try:
            order_result = _oem_create_new_order(session, base_url, client_token, new_order_body, timeout, variables)
        except Exception as exc:
            # 将请求体附加到错误日志，方便排查
            log["new_order_request"] = new_order_body
            raise
        new_order_sn = ""
        if isinstance(order_result, dict):
            new_order_sn = str(order_result.get("order_sn") or order_result.get("large_order_sn") or order_result.get("sn") or order_result.get("orderSn") or "")
        elif isinstance(order_result, str):
            new_order_sn = order_result

        # 记录完整响应数据，便于排查 new_order_sn 为空的情况
        resp_detail = {}
        if isinstance(order_result, dict):
            resp_detail = {k: v for k, v in order_result.items() if k not in ("sku_list",)}
        _step(log, "create_bulk_order",
              {"order_sn": large_order_sn, "inquiry_sn": order_sn, "detail_id": detail_id, "sku_count": len(sku_list_body)},
              {"url": "/api/newOrder", "method": "POST", "type": 2},
              {"new_order_sn": new_order_sn, "sku_count": len(sku_list_body),
               "resp_keys": list(order_result.keys()) if isinstance(order_result, dict) else [],
               "resp_data": resp_detail})

        summary = {
            "order_sn": order_sn,
            "new_order_sn": new_order_sn,
            "detail_id": detail_id,
            "goods_name": goods_name,
            "factory_count": len(detail_list),
            "sku_count": len(sku_list_body),
            "option_count": len(option_list),
            "has_large": bool(large_info),
            "bulk_images_count": len(bulk_images),
            "warehouse_city": warehouse_city,
            "remark": remark,
        }
        return _finish_named(OEM_BULK_ORDER_NAME, log, True, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(OEM_BULK_ORDER_NAME, log, False,
                             {"reason": str(exc), "error": str(exc)})


def run_oem_bulk_order_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_oem_bulk_order_script(env, variables)
