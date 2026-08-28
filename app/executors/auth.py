from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'BUSINESS_VAR_ALIASES',
    'Dict',
    'Iterable',
    'LOGIN_TEXT_MARKERS',
    'LOGIN_URL_MARKERS',
    'REGISTER_TEXT_MARKERS',
    'UiAuthPreparationError',
    '_first_business_match',
    '_first_runtime_value',
    '_guess_login_url',
    '_is_generated_sample_value',
    '_is_login_related_step',
    '_login_loading_visible',
    '_looks_like_login_page',
    '_looks_like_login_url',
    '_merge_locator_values',
    '_normalize_text',
    '_replace_sample_tokens',
    '_resolve_locator',
    '_sample_replacement_for_step',
    '_split_locator_values',
    '_step_text',
    '_visible_login_error',
    '_wait_for_url_contains',
    '_wait_login_submit_settled',
    're',
    'time',
    'urlparse',
    'urlunparse',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.executors"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


LOGIN_TEXT_MARKERS = [
    "登录", "登入", "立即登录", "登陆", "login", "sign in", "signin",
    "ログイン", "サインイン", "マイページ", "mypage", "my page"
]
REGISTER_TEXT_MARKERS = [
    "注册", "立即注册", "register", "sign up", "signup", "新規登録"
]


def _impl__guess_login_url(target_url: str | None) -> str:
    raw = str(target_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return ""
    if parsed.fragment and "/" in parsed.fragment:
        hash_prefix = "!/" if parsed.fragment.startswith("!/") else "/"
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", f"{hash_prefix}login"))
    return urlunparse((parsed.scheme, parsed.netloc, "/login", "", "", ""))


def _impl__first_runtime_value(variables: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = str(variables.get(key) or "").strip()
        if value:
            return value
    return ""


def _impl__step_text(step: Dict[str, Any]) -> str:
    values = [step.get("name"), step.get("locator"), step.get("value"), " ".join(_split_locator_values(step.get("fallback_locators")))]
    return " ".join(str(item or "") for item in values).lower()


def _impl__looks_like_login_url(value: Any) -> bool:
    url = str(value or "").strip().lower()
    return any(marker in url for marker in LOGIN_URL_MARKERS)


def _impl__looks_like_login_page(page: Any, expected_url: str = "") -> bool:
    current_url = str(getattr(page, "url", "") or "").lower()
    expected = str(expected_url or "").lower()
    if current_url and current_url != expected and any(marker in current_url for marker in LOGIN_URL_MARKERS):
        return True
    try:
        password_visible = any(
            page.locator(locator).first.is_visible(timeout=300)
            for locator in ['input[type="password"]', 'input[name="password"]']
        )
    except Exception:
        password_visible = False
    if not password_visible:
        return False
    for locator in [
        'button:has-text("登录")',
        '[role="button"]:has-text("登录")',
        "text=登录",
        'input[placeholder*="账号"]',
        'input[placeholder*="邮箱"]',
        'input[placeholder*="手机号"]',
    ]:
        try:
            if page.locator(locator).first.is_visible(timeout=200):
                return True
        except Exception:
            continue
    return False


def _impl__visible_login_error(page: Any) -> str:
    for locator in [
        ".error, .ant-form-item-explain-error, .el-form-item__error, .ant-message-error",
        "text=密码错误",
        "text=账号或密码错误",
        "text=登录失败",
        "text=验证码错误",
    ]:
        try:
            target = page.locator(locator).first
            if target.is_visible(timeout=200):
                text = _normalize_text(target.inner_text(timeout=500))
                if text:
                    return text[:200]
        except Exception:
            continue
    return ""


def _impl__login_loading_visible(page: Any) -> bool:
    for locator in [
        "text=正在加载",
        "text=请稍等",
        ".el-loading-mask",
        ".ant-spin",
        ".loading",
        "[class*='loading']",
    ]:
        try:
            target = page.locator(locator).first
            if target.is_visible(timeout=200):
                return True
        except Exception:
            continue
    return False


def _impl__wait_login_submit_settled(page: Any, timeout_ms: int) -> bool:
    deadline = time.time() + max(timeout_ms, 3000) / 1000
    saw_loading = False
    while time.time() < deadline:
        if not _login_loading_visible(page):
            return True
        saw_loading = True
        page.wait_for_timeout(500)
    return not saw_loading


def _impl__is_login_related_step(step: Dict[str, Any]) -> bool:
    action = str(step.get("action") or "").strip().lower()
    text = _step_text(step)
    if action == "goto" and _looks_like_login_url(step.get("value")):
        return True
    if action == "input" and any(keyword in text.lower() for keyword in ["username", "account", "email", "mobile", "phone", "密码", "password", "账号", "邮箱", "手机", "验证码", "captcha", "code", "ユーザー名", "パスワード"]):
        return True
    if action == "click" and any(keyword in text.lower() for keyword in [*LOGIN_TEXT_MARKERS, *REGISTER_TEXT_MARKERS]):
        return True
    if action in {"wait_for_selector", "assert_visible", "text_assert"} and any(keyword in text.lower() for keyword in [*LOGIN_TEXT_MARKERS, "验证码", "captcha"]):
        return True
    return False


def _impl__strip_leading_login_steps(steps: list[Dict[str, Any]]) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    prefix_actions = {"input", "click", "check", "uncheck", "wait", "wait_for_selector", "assert_visible", "text_assert"}
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            break
        action = str(step.get("action") or "").strip().lower()
        if action == "goto" and not _looks_like_login_url(step.get("value")):
            if index > 0:
                prefix = steps[:index]
                if all(
                    isinstance(item, dict) and (
                        str(item.get("action") or "").strip().lower() in prefix_actions
                        or (str(item.get("action") or "").strip().lower() == "goto" and _looks_like_login_url(item.get("value")))
                    )
                    for item in prefix
                ):
                    return steps[index:], prefix
            break
    kept: list[Dict[str, Any]] = []
    removed: list[Dict[str, Any]] = []
    stripping = True
    for step in steps:
        if not isinstance(step, dict):
            kept.append(step)
            stripping = False
            continue
        action = str(step.get("action") or "").strip().lower()
        if action == "goto" and not _looks_like_login_url(step.get("value")):
            if not kept:
                kept.append(step)
                continue
            else:
                kept.append(step)
                stripping = False
                continue
        if stripping:
            if _is_login_related_step(step):
                removed.append(step)
                continue
            if removed and action in ("wait", "wait_for_selector") and _is_login_related_step(step):
                removed.append(step)
                continue
            if action == "goto" and _looks_like_login_url(step.get("value")):
                removed.append(step)
                continue
            # Encountered first non-login business step! Stop stripping!
            stripping = False
            kept.append(step)
            continue
        kept.append(step)
    return kept or [{"name": "等待页面加载", "action": "wait_for_selector", "locator": "body"}], removed


def _impl__first_business_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.I)
        if not match:
            continue
        value = (match.group(1) if match.groups() else match.group(0)).strip(" \t\r\n:" + "\uFF1A,\uFF0C\u3002")
        if value:
            return value[:80]
    return ""


def _impl__business_variables_from_text(text: str) -> Dict[str, Any]:
    variables: Dict[str, Any] = {}
    customer_id = _first_business_match(text, [
        "\\bID\\s*[:\\uFF1A]\\s*([A-Za-z0-9_-]{3,32})",
        "\\b(CUST[-_]?[A-Za-z0-9]{3,24})\\b",
    ])
    if customer_id:
        variables["customer_id"] = customer_id
    customer_name = _first_business_match(text, [
        "\\bID\\s*[:\\uFF1A]\\s*[A-Za-z0-9_-]{3,32}\\s+([^\\s\\d][^\\r\\n]{1,40}?)\\s+(?:20\\d{8,}|[A-Z]{2,}[-_]?\\d|\\u3010)",
    ])
    if customer_name:
        variables["customer_name"] = customer_name
    box_no = _first_business_match(text, [
        "\\b(20\\d{10,}-[A-Za-z0-9_-]{3,}-\\d+)\\b",
        "\\b(BOX[-_]?[A-Z0-9]{4,36})\\b",
    ])
    if box_no:
        variables["box_no"] = box_no
    location_code = _first_business_match(text, [
        "\\u3010([^\\u3011]{2,80})\\u3011",
    ])
    if location_code:
        variables["location_code"] = location_code
    return variables


def _impl__is_generated_sample_value(value: Any) -> bool:
    raw = str(value or "").strip()
    if not raw or raw.upper().startswith("NONEXISTENT"):
        return False
    lower = raw.lower()
    if raw in {"\u5ba2\u6237A", "\u5ba2\u6237B", "\u5ba2\u6237a", "\u5ba2\u6237b"}:
        return True
    return bool(
        re.fullmatch(r"CUST[-_]?\d{3,}", raw, flags=re.I)
        or re.fullmatch(r"CUSTOMER[-_]?\d{3,}", raw, flags=re.I)
        or re.fullmatch(r"ORDER[-_]?\d{3,}", raw, flags=re.I)
        or re.fullmatch(r"BOX[-_]?\d{3,}", raw, flags=re.I)
        or re.fullmatch(r"BX[-_]?\d{4}[-_]\d+", raw, flags=re.I)
        or lower in {"cust123456", "customer123456", "order123456", "box123456", "bx-2023-001"}
    )


def _impl__sample_replacement_for_step(step: Dict[str, Any], variables: Dict[str, Any]) -> str:
    hint_lower = _step_text(step).lower()
    customer_id = str(variables.get("customerId") or variables.get("customer_id") or "").strip()
    customer_name = str(variables.get("customerName") or variables.get("customer_name") or "").strip()
    box_no = str(variables.get("boxNo") or variables.get("box_no") or variables.get("boxCode") or "").strip()
    location_code = str(variables.get("locationCode") or variables.get("location_code") or variables.get("warehouse_location") or "").strip()
    order_no = str(variables.get("orderNumber") or variables.get("orderNo") or variables.get("order_no") or "").strip()
    if any(item in hint_lower for item in ("customer", "client", "\u5ba2\u6237")):
        if "id" in hint_lower or "\u7f16\u53f7" in hint_lower:
            return customer_id or customer_name
        return customer_name or customer_id
    if any(item in hint_lower for item in ("box", "\u7bb1\u53f7", "\u7bb1\u5b50")) and box_no:
        return box_no
    if any(item in hint_lower for item in ("order", "\u8ba2\u5355")) and order_no:
        return order_no
    if any(item in hint_lower for item in ("location", "\u5e93\u4f4d", "\u4ed3\u4f4d")) and location_code:
        return location_code
    return ""


def _impl__replace_sample_tokens(value: Any, replacement: str) -> Any:
    if not isinstance(value, str) or not replacement:
        return value
    result = value
    for token in ("\u5ba2\u6237A", "\u5ba2\u6237B", "CUST123456", "CUSTOMER123456", "ORDER123456", "BOX123456", "BX-2023-001"):
        result = result.replace(token, replacement)
    result = re.sub(r"\bCUST[-_]?\d{3,}\b", replacement, result, flags=re.I)
    result = re.sub(r"\bCUSTOMER[-_]?\d{3,}\b", replacement, result, flags=re.I)
    result = re.sub(r"\bORDER[-_]?\d{3,}\b", replacement, result, flags=re.I)
    result = re.sub(r"\bBOX[-_]?\d{3,}\b", replacement, result, flags=re.I)
    result = re.sub(r"\bBX[-_]?\d{4}[-_]\d+\b", replacement, result, flags=re.I)
    return result


def _impl__merge_inferred_business_variables(variables: Dict[str, Any], inferred: Dict[str, Any]) -> Dict[str, Any]:
    applied: Dict[str, Any] = {}
    for canonical, aliases in BUSINESS_VAR_ALIASES.items():
        value = str(inferred.get(canonical) or "").strip()
        if not value:
            continue
        for alias in aliases:
            current = variables.get(alias)
            if current in (None, "") or _is_generated_sample_value(current):
                variables[alias] = value
                applied[alias] = value
    if "keyword" not in variables or variables.get("keyword") in (None, ""):
        keyword = inferred.get("location_code") or inferred.get("customer_id") or inferred.get("customer_name") or inferred.get("box_no")
        if keyword:
            variables["keyword"] = keyword
            applied["keyword"] = keyword
    return applied


def _impl__stabilize_runtime_steps(steps: list[Dict[str, Any]], variables: Dict[str, Any]) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    normalized: list[Dict[str, Any]] = []
    replacements: list[Dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            normalized.append(step)
            continue
        next_step = dict(step)
        replacement = _sample_replacement_for_step(next_step, variables)
        if replacement and _is_generated_sample_value(next_step.get("value")):
            old_value = next_step.get("value")
            next_step["value"] = replacement
            replacements.append({"step": index, "field": "value", "from": old_value, "to": replacement})
        if replacement:
            old_locator = next_step.get("locator")
            new_locator = _replace_sample_tokens(old_locator, replacement)
            if new_locator != old_locator:
                next_step["locator"] = new_locator
                replacements.append({"step": index, "field": "locator", "from": old_locator, "to": new_locator})
            fallbacks = next_step.get("fallback_locators")
            if isinstance(fallbacks, list):
                new_fallbacks = [_replace_sample_tokens(item, replacement) for item in fallbacks]
                if new_fallbacks != fallbacks:
                    next_step["fallback_locators"] = new_fallbacks
                    replacements.append({"step": index, "field": "fallback_locators", "from": fallbacks, "to": new_fallbacks})
        normalized.append(next_step)
    return normalized, replacements


def _impl__prepare_authenticated_page(page: Any, execution_context: Dict[str, Any], variables: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
    auth = dict(execution_context.get("login_config") or {})
    target_url = str(execution_context.get("target_url") or "").strip()
    login_url = str(auth.get("login_url") or "").strip() or _guess_login_url(target_url)
    username = _first_runtime_value(variables, ["username", "account", "email", "mobile", "phone"])
    password = _first_runtime_value(variables, ["password"])
    code = _first_runtime_value(variables, ["code", "captcha", "captcha_code", "verify_code", "verification_code"])
    trace: list[str] = [f"打开登录页：{login_url}"]
    if not login_url or not username or not password:
        raise UiAuthPreparationError("登录前置失败：缺少登录页 URL、登录账号或登录密码。", trace)

    username_defaults = [
        'input[placeholder="邮箱/手机号"]',
        'input[name="username"]',
        'input[name="account"]',
        'input[name="mobile"]',
        'input[name="email"]',
        'input[type="text"]',
        'input[placeholder*="ユーザー名"]',
        'input[placeholder*="携帯番号"]',
        'input[placeholder*="Email" i]',
        'input[placeholder*="username" i]',
    ]
    password_defaults = [
        'input[placeholder="请输入密码"]',
        'input[type="password"]',
        'input[name="password"]',
        'input[placeholder*="パスワード"]',
        'input[placeholder*="password" i]',
    ]
    submit_defaults = [
        'button:has-text("立即登录")',
        '[role="button"]:has-text("立即登录")',
        '.el-button:has-text("立即登录")',
        '[class*="button"]:has-text("立即登录")',
        '[class*="btn"]:has-text("立即登录")',
        '[class*="login"]:has-text("立即登录")',
        'input[type="submit"][value*="立即登录"]',
        "text=立即登录",
        'button[type="submit"]',
        'button:has-text("登录")',
        '[role="button"]:has-text("登录")',
        '.el-button:has-text("登录")',
        '[class*="button"]:has-text("登录")',
        '[class*="btn"]:has-text("登录")',
        '[class*="login"]:has-text("登录")',
        'input[type="submit"][value*="登录"]',
        "text=登录",
        'button:has-text("ログイン")',
        '[role="button"]:has-text("ログイン")',
        '.el-button:has-text("ログイン")',
        '[class*="button"]:has-text("ログイン")',
        '[class*="btn"]:has-text("ログイン")',
        '[class*="login"]:has-text("ログイン")',
        'input[type="submit"][value*="ログイン"]',
        "text=ログイン",
        'button:has-text("サインイン")',
        "text=サインイン",
        'button:has-text("Sign in")',
        'button:has-text("Log in")',
        "text=Sign in",
        "text=Log in",
    ]
    username_candidates = _merge_locator_values(_split_locator_values(auth.get("username_locator")), username_defaults)
    password_candidates = _merge_locator_values(_split_locator_values(auth.get("password_locator")), password_defaults)
    submit_candidates = _merge_locator_values(_split_locator_values(auth.get("submit_locator")), submit_defaults)
    code_candidates = [
        'input[placeholder*="验证码"]',
        'input[name="code"]',
        'input[name="captcha"]',
        'input[placeholder*="captcha" i]',
    ]


    page.goto(login_url, wait_until="domcontentloaded", timeout=max(timeout_seconds, 10) * 1000)
    page.set_default_timeout(timeout_seconds * 1000)

    username_target, username_locator, _ = _resolve_locator(page, username_candidates, 4000)
    username_target.fill("", timeout=4000)
    username_target.fill(username, timeout=4000)
    trace.append(f"已填写登录账号：{username_locator}")

    password_target, password_locator, _ = _resolve_locator(page, password_candidates, 4000)
    password_target.fill("", timeout=4000)
    password_target.fill(password, timeout=4000)
    trace.append(f"已填写登录密码：{password_locator}")

    if code:
        try:
            code_target, code_locator, _ = _resolve_locator(page, code_candidates, 2000)
            code_target.fill("", timeout=2000)
            code_target.fill(code, timeout=2000)
            trace.append(f"已填写验证码：{code_locator}")
        except Exception:
            trace.append("未定位到验证码输入框，跳过验证码自动填写")

    submit_target, submit_locator, _ = _resolve_locator(page, submit_candidates, 5000)
    try:
        submit_target.scroll_into_view_if_needed(timeout=1000)
    except Exception:
        pass
    submit_target.click(timeout=5000)
    trace.append(f"已点击登录按钮：{submit_locator}")

    success_selector = str(auth.get("success_selector") or "").strip()
    success_url_contains = str(auth.get("success_url_contains") or "").strip()
    def wait_after_submit(label: str) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            page.wait_for_timeout(1500)
        settled = _wait_login_submit_settled(page, max(timeout_seconds, 15) * 1000)
        if not settled:
            trace.append(f"{label}后登录页仍处于加载中")
        trace.append(f"{label}后当前页面：{page.url}")

    wait_after_submit("首次提交")
    if success_selector:
        page.wait_for_selector(success_selector, timeout=max(timeout_seconds, 8) * 1000)
        trace.append(f"检测到登录成功元素：{success_selector}")
    elif success_url_contains:
        _wait_for_url_contains(page, success_url_contains, max(timeout_seconds, 8) * 1000)
        trace.append(f"检测到登录成功地址：{page.url}")
    else:
        if _looks_like_login_page(page, expected_url=login_url):
            # 二次确认：检查页面是否真的还有密码输入框（防止 URL 含 "login" 子串而误判）
            still_has_password = False
            try:
                still_has_password = any(
                    page.locator(l).first.is_visible(timeout=500)
                    for l in ['input[type="password"]', 'input[name="password"]']
                )
            except Exception:
                pass
            if not still_has_password:
                trace.append("页面已无密码输入框，认为登录成功（URL 含 login 关键词但已无登录表单）")
            else:
                try:
                    password_target.press("Enter", timeout=2000)
                    trace.append("首次点击后仍在登录页，已尝试按 Enter 再次提交")
                    wait_after_submit("Enter 提交")
                except Exception as exc:
                    trace.append(f"Enter 提交失败：{str(exc)[:200]}")
        if _looks_like_login_page(page, expected_url=login_url):
            try:
                submit_target.click(timeout=3000, force=True)
                trace.append("Enter 提交后仍在登录页，已尝试强制点击登录按钮")
                wait_after_submit("强制点击")
            except Exception as exc:
                trace.append(f"强制点击失败：{str(exc)[:200]}")
        if _looks_like_login_page(page, expected_url=login_url):
            error_text = _visible_login_error(page)
            detail = f"登录前置失败：提交后仍停留在登录页，当前页面 {page.url}"
            if _login_loading_visible(page):
                detail += "；登录请求一直处于加载中，可能是账号/密码不正确、验证码/二次认证未处理，或登录接口响应异常"
            if error_text:
                detail += f"；页面提示：{error_text}"
                trace.append(f"页面错误提示：{error_text}")
            raise UiAuthPreparationError(detail, trace)
        trace.append(f"登录后当前页面：{page.url}")
    return {"trace": trace, "login_url": login_url, "submit_locator": submit_locator}


def _guess_login_url(target_url: str | None) -> str:
    _sync_compat_globals()
    return _impl__guess_login_url(target_url)


def _first_runtime_value(variables: Dict[str, Any], keys: Iterable[str]) -> str:
    _sync_compat_globals()
    return _impl__first_runtime_value(variables, keys)


def _step_text(step: Dict[str, Any]) -> str:
    _sync_compat_globals()
    return _impl__step_text(step)


def _looks_like_login_url(value: Any) -> bool:
    _sync_compat_globals()
    return _impl__looks_like_login_url(value)


def _looks_like_login_page(page: Any, expected_url: str='') -> bool:
    _sync_compat_globals()
    return _impl__looks_like_login_page(page, expected_url)


def _visible_login_error(page: Any) -> str:
    _sync_compat_globals()
    return _impl__visible_login_error(page)


def _login_loading_visible(page: Any) -> bool:
    _sync_compat_globals()
    return _impl__login_loading_visible(page)


def _wait_login_submit_settled(page: Any, timeout_ms: int) -> bool:
    _sync_compat_globals()
    return _impl__wait_login_submit_settled(page, timeout_ms)


def _is_login_related_step(step: Dict[str, Any]) -> bool:
    _sync_compat_globals()
    return _impl__is_login_related_step(step)


def _strip_leading_login_steps(steps: list[Dict[str, Any]]) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    _sync_compat_globals()
    return _impl__strip_leading_login_steps(steps)


def _first_business_match(text: str, patterns: list[str]) -> str:
    _sync_compat_globals()
    return _impl__first_business_match(text, patterns)


def _business_variables_from_text(text: str) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__business_variables_from_text(text)


def _is_generated_sample_value(value: Any) -> bool:
    _sync_compat_globals()
    return _impl__is_generated_sample_value(value)


def _sample_replacement_for_step(step: Dict[str, Any], variables: Dict[str, Any]) -> str:
    _sync_compat_globals()
    return _impl__sample_replacement_for_step(step, variables)


def _replace_sample_tokens(value: Any, replacement: str) -> Any:
    _sync_compat_globals()
    return _impl__replace_sample_tokens(value, replacement)


def _merge_inferred_business_variables(variables: Dict[str, Any], inferred: Dict[str, Any]) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__merge_inferred_business_variables(variables, inferred)


def _stabilize_runtime_steps(steps: list[Dict[str, Any]], variables: Dict[str, Any]) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    _sync_compat_globals()
    return _impl__stabilize_runtime_steps(steps, variables)


def _prepare_authenticated_page(page: Any, execution_context: Dict[str, Any], variables: Dict[str, Any], timeout_seconds: int) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__prepare_authenticated_page(page, execution_context, variables, timeout_seconds)
