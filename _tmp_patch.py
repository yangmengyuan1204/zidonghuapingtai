import io
p = 'app/data_scripts.py'
s = io.open(p, 'r', encoding='utf-8').read()

old = '''            # 重新查询详情获取最新状态
            detail = _oem_query_inquiry_detail(session, base_url, admin_token, order_sn, timeout, variables)
        else:
            _step(log, "skip_translate", {}, {"note": "跳过翻译阶段"}, {"skipped": True})

        # ─── 阶段3：询价阶段（开始询价 + 编辑工厂 + 工厂报价 + 询价完成） ──
        if not variables.get("skip_inquiry"):
            # 开始询价：需要把状态字段设为翻译完成后的状态(user_status=2/y_admin_status=2/g_admin_status=2)
            # goods_class 详情返回可能是空对象，需确保为有效数字 id
            detail["user_status"] = 2
            detail["y_admin_status"] = 2
            detail["g_admin_status"] = 2
            gc = detail.get("goods_class")
            if not isinstance(gc, int) or gc == 0:
                detail["goods_class"] = int(variables.get("goods_class") or 110)
            sip = _oem_post_json(session, base_url, "/admin/inquiryStartInquiry", detail, timeout,
                                 token=admin_token, is_admin=True, variables=variables)'''

new = '''            # 翻译审核（新需求：翻译提交后需审核通过，状态才会推进到可询价）
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
                                 token=admin_token, is_admin=True, variables=variables)'''

if old in s:
    s = s.replace(old, new)
    io.open(p, 'w', encoding='utf-8').write(s)
    print('OK replaced')
else:
    print('NOT FOUND')
