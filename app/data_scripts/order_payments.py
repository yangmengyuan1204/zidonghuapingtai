from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'BALANCE_PAYMENT_SCRIPT_NAME',
    'BANK_PAYMENT_SCRIPT_NAME',
    'Dict',
    'Env',
    'OrderedDict',
    'POORDER_BALANCE_PAYMENT_SCRIPT_NAME',
    'POORDER_BANK_PAYMENT_SCRIPT_NAME',
    'Tuple',
    '_admin_login',
    '_admin_session_from',
    '_api_path',
    '_api_success',
    '_apply_extra_fields',
    '_as_bool',
    '_as_float',
    '_as_int',
    '_bank_pay_reach_date',
    '_call_with_retry',
    '_common_payment_summary',
    '_finance_bill_brief',
    '_finance_rows_from_payload',
    '_finance_unconfirm_fields',
    '_finish_named',
    '_load_payment_order',
    '_load_porder_payment_amount',
    '_login_client_for_payment',
    '_payload_brief',
    '_porder_payload_matches',
    '_porder_payment_summary',
    '_porder_sn',
    '_positive_decimal',
    '_post_admin_form',
    '_run_backend_porder_flow',
    '_select_finance_bill',
    'bulk_cart',
    'datetime',
    'ensure_report_dirs',
    'time',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl_run_balance_payment_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    log: Dict[str, Any] = {
        "script": BALANCE_PAYMENT_SCRIPT_NAME,
        "mode": "balance_payment",
        "started_at": datetime.now(),
        "order_list": {},
        "payment": {},
    }

    try:
        client, base_url, _, _ = _login_client_for_payment(env, variables, log)
        log["base_url"] = base_url
        order, order_sn, amount = _load_payment_order(client, variables, log)
        if not order or not order_sn:
            return _finish_named(
                BALANCE_PAYMENT_SCRIPT_NAME,
                log,
                False,
                {"payment_type": "balance", "order_sn": "", "pay_amount": "0", "reason": "\u672a\u67e5\u8be2\u5230\u7b49\u5f85\u4ed8\u6b3e\u8ba2\u5355"},
            )

        fields: OrderedDict[str, Any] = OrderedDict()
        fields["order_sn"] = order_sn
        fields["discounts_id"] = str(variables.get("discounts_id") or "")
        fields["predict_logistics_price_is_pay"] = str(variables.get("predict_logistics_price_is_pay") or "0")
        if _as_bool(variables.get("include_balance_pay_amount"), False):
            fields["pay_amount"] = amount
        _apply_extra_fields(fields, variables.get("balance_pay_fields"))
        payment_payload = _call_with_retry(
            "balance payment",
            lambda: client.post_form(_api_path(variables, "client_balance_pay", "/client/order.balancePayOrder"), fields),
        )
        log["payment"] = {**_payload_brief(payment_payload), "request": dict(fields)}
        summary = _common_payment_summary("balance", order_sn, amount, payment_payload)
        return _finish_named(BALANCE_PAYMENT_SCRIPT_NAME, log, summary["payment_passed"], summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            BALANCE_PAYMENT_SCRIPT_NAME,
            log,
            False,
            {"payment_type": "balance", "order_sn": "", "pay_amount": "0", "error": str(exc)},
        )


def _impl_run_bank_payment_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    existing_serial_number = str(variables.get("serial_number") or "").strip()
    existing_order_sn = str(variables.get("order_sn") or "").strip()
    log: Dict[str, Any] = {
        "script": BANK_PAYMENT_SCRIPT_NAME,
        "mode": "finance_only" if existing_serial_number else "bank_payment",
        "started_at": datetime.now(),
        "order_list": {},
        "payment": {},
        "finance": {},
    }

    try:
        client = None
        base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
        timeout = _as_int(variables.get("timeout"), env.timeout or 25)
        if not existing_serial_number:
            client, base_url, timeout, _ = _login_client_for_payment(env, variables, log)
        log["base_url"] = base_url
        order_sn = existing_order_sn
        amount = str(variables.get("pay_amount") or "0")
        payment_payload: Dict[str, Any] = {"success": True, "code": 0, "data": {"order_sn": order_sn, "serial_number": existing_serial_number}}
        payment_data: Dict[str, Any] = {"order_sn": order_sn, "serial_number": existing_serial_number}
        payment_ok = True
        serial_number = existing_serial_number
        if existing_serial_number:
            log["payment"] = {
                "skipped": True,
                "reason": "\u5df2\u4f20\u5165\u6d41\u6c34\u53f7\uff0c\u53ea\u6267\u884c\u8d22\u52a1\u786e\u8ba4\u5165\u91d1",
                "order_sn": order_sn,
                "serial_number": serial_number,
            }
        else:
            order, order_sn, amount = _load_payment_order(client, variables, log)
            if not order or not order_sn:
                return _finish_named(
                    BANK_PAYMENT_SCRIPT_NAME,
                    log,
                    False,
                    {"payment_type": "bank", "order_sn": "", "pay_amount": "0", "reason": "\u672a\u67e5\u8be2\u5230\u7b49\u5f85\u4ed8\u6b3e\u8ba2\u5355"},
                )
            if not _positive_decimal(amount):
                return _finish_named(
                    BANK_PAYMENT_SCRIPT_NAME,
                    log,
                    False,
                    {"payment_type": "bank", "order_sn": order_sn, "pay_amount": amount, "reason": "\u672a\u83b7\u53d6\u5230\u53ef\u7528\u7684\u8ba2\u5355\u652f\u4ed8\u91d1\u989d"},
                )

            now = datetime.now()
            fields: OrderedDict[str, Any] = OrderedDict()
            fields["order_sn"] = order_sn
            fields["pay_bank_method"] = str(variables.get("pay_bank_method") or "1")
            fields["pay_date"] = str(variables.get("pay_date") or now.strftime("%Y-%m-%d %H:%M:%S"))
            fields["pay_reach_date"] = _bank_pay_reach_date(variables, now)
            fields["pay_name"] = str(variables.get("pay_name") or "\u81ea\u52a8\u5316\u6d4b\u8bd5")
            fields["pay_amount"] = amount
            fields["pay_remark"] = str(variables.get("pay_remark") or "\u81ea\u52a8\u5316\u94f6\u884c\u4ed8\u6b3e")
            fields["discounts_id"] = str(variables.get("discounts_id") or "")
            fields["predict_logistics_price_is_pay"] = str(variables.get("predict_logistics_price_is_pay") or "0")
            _apply_extra_fields(fields, variables.get("bank_pay_fields"))
            payment_payload = _call_with_retry(
                "bank payment",
                lambda: client.post_form(_api_path(variables, "client_bank_pay", "/client/order.bankPayOrder"), fields),
            )
            payment_ok = _api_success(payment_payload)
            payment_data = payment_payload.get("data") if isinstance(payment_payload.get("data"), dict) else {}
            serial_number = str(payment_data.get("serial_number") or variables.get("serial_number") or "")
            log["payment"] = {**_payload_brief(payment_payload), "request": dict(fields), "serial_number": serial_number}

        finance_confirm = _as_bool(variables.get("finance_confirm"), True)
        finance_ok = True
        if payment_ok and finance_confirm:
            if not serial_number:
                finance_ok = False
                log["finance"] = {"reason": "\u94f6\u884c\u652f\u4ed8\u672a\u8fd4\u56de\u6d41\u6c34\u53f7"}
            else:
                session = _admin_session_from(variables)
                login_payload, token = _admin_login(session, base_url, variables, timeout)
                log["finance"]["login"] = {
                    **_payload_brief(login_payload),
                    "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
                    "token_extracted": bool(token),
                }
                if not _api_success(login_payload) or not token:
                    finance_ok = False
                    log["finance"]["reason"] = "\u540e\u53f0\u767b\u5f55\u5931\u8d25"
                else:
                    initial_delay = _as_float(variables.get("finance_confirm_initial_delay"), 2.0)
                    retry_delay = _as_float(variables.get("finance_confirm_delay"), 2.0)
                    retries = _as_int(variables.get("finance_confirm_retries"), 6)
                    if initial_delay > 0:
                        time.sleep(initial_delay)
                    attempts = []
                    list_payload: Dict[str, Any] = {}
                    confirm_payload: Dict[str, Any] = {}
                    selected_bill: Dict[str, Any] | None = None
                    for attempt in range(retries):
                        list_fields = _finance_unconfirm_fields(variables, serial_number, str(payment_data.get("order_sn") or order_sn))
                        list_payload = _post_admin_form(
                            session,
                            base_url,
                            _api_path(variables, "admin_bill_unconfirm_list", "/bill.unConfirmList"),
                            list_fields,
                            timeout,
                        )
                        rows = _finance_rows_from_payload(list_payload)
                        selected_bill = _select_finance_bill(rows, serial_number, str(payment_data.get("order_sn") or order_sn))
                        attempt_brief = {
                            **_payload_brief(list_payload),
                            "request": dict(list_fields),
                            "row_count": len(rows),
                            "selected_bill": _finance_bill_brief(selected_bill),
                            "serial_number": serial_number,
                            "attempt": attempt + 1,
                        }
                        attempts.append(attempt_brief)
                        if _api_success(list_payload) and selected_bill and selected_bill.get("id") not in (None, ""):
                            break
                        if attempt < retries - 1:
                            time.sleep(retry_delay)
                    log["finance"]["unconfirm_list_attempts"] = attempts
                    log["finance"]["unconfirm_list"] = attempts[-1] if attempts else {"serial_number": serial_number}
                    if _api_success(list_payload) and selected_bill and selected_bill.get("id") not in (None, ""):
                        confirm_payload = _post_admin_form(
                            session,
                            base_url,
                            _api_path(variables, "admin_bill_confirm", "/bill.confirm"),
                            {"id": selected_bill.get("id")},
                            timeout,
                        )
                        finance_ok = _api_success(confirm_payload)
                        log["finance"]["confirm"] = {
                            **_payload_brief(confirm_payload),
                            "request": {"id": selected_bill.get("id")},
                            "selected_bill": _finance_bill_brief(selected_bill),
                        }
                    else:
                        finance_ok = False
                        log["finance"]["confirm"] = {"serial_number": serial_number, "selected_bill": _finance_bill_brief(selected_bill)}
                    if not finance_ok:
                        last_payload = confirm_payload or list_payload
                        last_msg = last_payload.get("msg") or last_payload.get("data") or "\u8d22\u52a1\u786e\u8ba4\u6c47\u6b3e\u5931\u8d25"
                        log["finance"]["reason"] = f"\u8d22\u52a1\u786e\u8ba4\u6c47\u6b3e\u5931\u8d25\uff1a{last_msg}"

        passed = payment_ok and finance_ok
        summary = _common_payment_summary(
            "bank",
            str(payment_data.get("order_sn") or order_sn),
            amount,
            payment_payload,
            {
                "serial_number": serial_number,
                "finance_confirm": finance_confirm,
                "finance_passed": finance_ok,
            },
        )
        finance_reason = log.get("finance", {}).get("reason")
        if not passed and finance_reason:
            summary["reason"] = finance_reason
        elif not passed and "reason" not in summary:
            summary["reason"] = "\u94f6\u884c\u652f\u4ed8\u6216\u8d22\u52a1\u786e\u8ba4\u5931\u8d25"
        return _finish_named(BANK_PAYMENT_SCRIPT_NAME, log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            BANK_PAYMENT_SCRIPT_NAME,
            log,
            False,
            {"payment_type": "bank", "order_sn": "", "pay_amount": "0", "error": str(exc)},
        )


def _impl_run_porder_balance_payment_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    porder_sn = _porder_sn(variables)
    if not porder_sn:
        return _finish_named(
            POORDER_BALANCE_PAYMENT_SCRIPT_NAME,
            {"script": POORDER_BALANCE_PAYMENT_SCRIPT_NAME, "started_at": datetime.now()},
            False,
            {"porder_sn": "", "order_sn": "", "reason": "请输入配送单号"},
        )

    log: Dict[str, Any] = {
        "script": POORDER_BALANCE_PAYMENT_SCRIPT_NAME,
        "mode": "porder_balance_payment",
        "started_at": datetime.now(),
        "porder_sn": porder_sn,
        "backend_porder": {},
        "order_list": {},
        "payment": {},
    }

    try:
        # Step 1: 可选执行后台配送单流程（配货、装箱、报价）
        base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
        timeout = _as_int(variables.get("timeout"), env.timeout or 25)
        if _as_bool(variables.get("run_backend_porder_flow"), False):
            log["mode"] = "porder_backend_then_balance_payment"
            backend_passed, backend_summary = _run_backend_porder_flow(base_url, timeout, variables, porder_sn, log)
            if not backend_passed:
                return _finish_named(
                    POORDER_BALANCE_PAYMENT_SCRIPT_NAME,
                    log,
                    False,
                    {"porder_sn": porder_sn, "order_sn": "", "reason": backend_summary.get("reason") or "配送单后台流程失败"},
                )
        else:
            log["backend_porder"] = {"skipped": True, "reason": "配送单已待支付，跳过后台流程"}

        # Step 2: 余额支付
        client, base_url, _, _ = _login_client_for_payment(env, variables, log)
        log["base_url"] = base_url
        amount = _load_porder_payment_amount(client, variables, log, porder_sn)

        fields: OrderedDict[str, Any] = OrderedDict()
        fields["porder_sn"] = porder_sn
        fields["discounts_id"] = str(variables.get("discounts_id") or "")
        fields["merge_pay"] = str(variables.get("merge_pay") or "0")
        _apply_extra_fields(fields, variables.get("balance_pay_fields"))
        payment_payload = _call_with_retry(
            "porder balance payment",
            lambda: client.post_form(_api_path(variables, "client_porder_balance_pay", "/client/porder.balancePayOrder"), fields),
        )
        log["payment"] = {**_payload_brief(payment_payload), "request": dict(fields)}
        summary = _porder_payment_summary("balance", porder_sn, amount, payment_payload)
        summary["backend_passed"] = True
        return _finish_named(POORDER_BALANCE_PAYMENT_SCRIPT_NAME, log, summary["payment_passed"] and summary["porder_matched"], summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            POORDER_BALANCE_PAYMENT_SCRIPT_NAME,
            log,
            False,
            {"porder_sn": porder_sn, "payment_type": "balance", "order_sn": "", "pay_amount": "0", "error": str(exc)},
        )


def _impl_run_porder_bank_payment_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    porder_sn = _porder_sn(variables)
    if not porder_sn:
        return _finish_named(
            POORDER_BANK_PAYMENT_SCRIPT_NAME,
            {"script": POORDER_BANK_PAYMENT_SCRIPT_NAME, "started_at": datetime.now()},
            False,
            {"porder_sn": "", "order_sn": "", "reason": "请输入配送单号"},
        )

    log: Dict[str, Any] = {
        "script": POORDER_BANK_PAYMENT_SCRIPT_NAME,
        "mode": "porder_bank_payment",
        "started_at": datetime.now(),
        "porder_sn": porder_sn,
        "backend_porder": {},
        "order_list": {},
        "payment": {},
        "finance": {},
    }

    try:
        # Step 1: 可选执行后台配送单流程（配货、装箱、报价）
        base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
        timeout = _as_int(variables.get("timeout"), env.timeout or 25)
        if _as_bool(variables.get("run_backend_porder_flow"), False):
            log["mode"] = "porder_backend_then_bank_payment"
            backend_passed, backend_summary = _run_backend_porder_flow(base_url, timeout, variables, porder_sn, log)
            if not backend_passed:
                return _finish_named(
                    POORDER_BANK_PAYMENT_SCRIPT_NAME,
                    log,
                    False,
                    {"porder_sn": porder_sn, "order_sn": "", "reason": backend_summary.get("reason") or "配送单后台流程失败"},
                )
        else:
            log["backend_porder"] = {"skipped": True, "reason": "配送单已待支付，跳过后台流程"}

        # Step 2: 银行支付
        client, base_url, timeout, _ = _login_client_for_payment(env, variables, log)
        log["base_url"] = base_url
        amount = _load_porder_payment_amount(client, variables, log, porder_sn)
        if not _positive_decimal(amount):
            return _finish_named(
                POORDER_BANK_PAYMENT_SCRIPT_NAME,
                log,
                False,
                {"porder_sn": porder_sn, "payment_type": "bank", "order_sn": "", "pay_amount": amount, "reason": "未获取到可用的配送单支付金额"},
            )

        now = datetime.now()
        fields: OrderedDict[str, Any] = OrderedDict()
        fields["porder_sn"] = porder_sn
        fields["pay_bank_method"] = str(variables.get("pay_bank_method") or "1")
        fields["pay_date"] = str(variables.get("pay_date") or now.strftime("%Y-%m-%d %H:%M:%S"))
        fields["pay_reach_date"] = _bank_pay_reach_date(variables, now)
        fields["pay_name"] = str(variables.get("pay_name") or "自动化测试")
        fields["pay_amount"] = amount
        fields["pay_remark"] = str(variables.get("pay_remark") or "自动化银行付款")
        fields["discounts_id"] = str(variables.get("discounts_id") or "")
        fields["merge_pay"] = str(variables.get("merge_pay") or "0")
        _apply_extra_fields(fields, variables.get("bank_pay_fields"))
        payment_payload = _call_with_retry(
            "porder bank payment",
            lambda: client.post_form(_api_path(variables, "client_porder_bank_pay", "/client/porder.bankPayOrder"), fields),
        )
        payment_ok = _api_success(payment_payload)
        payment_data = payment_payload.get("data") if isinstance(payment_payload.get("data"), dict) else {}
        serial_number = str(payment_data.get("serial_number") or variables.get("serial_number") or "")
        porder_matched = _porder_payload_matches(payment_payload, porder_sn)
        log["payment"] = {**_payload_brief(payment_payload), "request": dict(fields), "serial_number": serial_number, "porder_matched": porder_matched}

        # Step 3: 财务确认
        finance_confirm = _as_bool(variables.get("finance_confirm"), True)
        finance_ok = True
        if payment_ok and porder_matched and finance_confirm:
            if not serial_number:
                finance_ok = False
                log["finance"] = {"reason": "银行支付未返回流水号"}
            else:
                session = _admin_session_from(variables)
                login_payload, token = _admin_login(session, base_url, variables, timeout)
                log["finance"]["login"] = {
                    **_payload_brief(login_payload),
                    "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
                    "token_extracted": bool(token),
                }
                if not _api_success(login_payload) or not token:
                    finance_ok = False
                    log["finance"]["reason"] = "后台登录失败"
                else:
                    initial_delay = _as_float(variables.get("finance_confirm_initial_delay"), 2.0)
                    retry_delay = _as_float(variables.get("finance_confirm_delay"), 2.0)
                    retries = _as_int(variables.get("finance_confirm_retries"), 6)
                    if initial_delay > 0:
                        time.sleep(initial_delay)
                    attempts = []
                    list_payload: Dict[str, Any] = {}
                    confirm_payload: Dict[str, Any] = {}
                    selected_bill: Dict[str, Any] | None = None
                    for attempt in range(retries):
                        list_fields = _finance_unconfirm_fields(variables, serial_number, porder_sn)
                        list_payload = _post_admin_form(
                            session, base_url,
                            _api_path(variables, "admin_bill_unconfirm_list", "/bill.unConfirmList"),
                            list_fields, timeout,
                        )
                        rows = _finance_rows_from_payload(list_payload)
                        selected_bill = _select_finance_bill(rows, serial_number, porder_sn)
                        attempt_brief = {
                            **_payload_brief(list_payload),
                            "request": dict(list_fields),
                            "row_count": len(rows),
                            "selected_bill": _finance_bill_brief(selected_bill),
                            "serial_number": serial_number,
                            "attempt": attempt + 1,
                        }
                        attempts.append(attempt_brief)
                        if _api_success(list_payload) and selected_bill and selected_bill.get("id") not in (None, ""):
                            break
                        if attempt < retries - 1:
                            time.sleep(retry_delay)
                    log["finance"]["unconfirm_list_attempts"] = attempts
                    log["finance"]["unconfirm_list"] = attempts[-1] if attempts else {"serial_number": serial_number}
                    if _api_success(list_payload) and selected_bill and selected_bill.get("id") not in (None, ""):
                        confirm_payload = _post_admin_form(
                            session, base_url,
                            _api_path(variables, "admin_bill_confirm", "/bill.confirm"),
                            {"id": selected_bill.get("id")}, timeout,
                        )
                        finance_ok = _api_success(confirm_payload)
                        log["finance"]["confirm"] = {
                            **_payload_brief(confirm_payload),
                            "request": {"id": selected_bill.get("id")},
                            "selected_bill": _finance_bill_brief(selected_bill),
                        }
                    else:
                        finance_ok = False
                        log["finance"]["confirm"] = {"serial_number": serial_number, "selected_bill": _finance_bill_brief(selected_bill)}
                    if not finance_ok:
                        last_payload = confirm_payload or list_payload
                        last_msg = last_payload.get("msg") or last_payload.get("data") or "财务确认汇款失败"
                        log["finance"]["reason"] = f"财务确认汇款失败：{last_msg}"

        passed = payment_ok and porder_matched and finance_ok
        summary = _porder_payment_summary("bank", porder_sn, amount, payment_payload)
        summary["backend_passed"] = True
        summary["finance_passed"] = finance_ok
        if payment_ok and not porder_matched:
            summary["reason"] = "配送单银行付款接口返回单号与输入配送单号不一致"
        return _finish_named(POORDER_BANK_PAYMENT_SCRIPT_NAME, log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            POORDER_BANK_PAYMENT_SCRIPT_NAME,
            log,
            False,
            {"porder_sn": porder_sn, "payment_type": "bank", "order_sn": "", "pay_amount": "0", "error": str(exc)},
        )


def run_balance_payment_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_balance_payment_script(env, variables)


def run_bank_payment_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_bank_payment_script(env, variables)


def run_porder_balance_payment_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_porder_balance_payment_script(env, variables)


def run_porder_bank_payment_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _impl_run_porder_bank_payment_script(env, variables)
