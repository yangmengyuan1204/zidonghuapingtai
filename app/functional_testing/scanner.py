from __future__ import annotations

from contextlib import contextmanager
import sys


_COMPAT_NAMES = (
    'Any',
    'Dict',
    'FunctionalScanError',
    'Path',
    'SCREENSHOT_DIR',
    '_DOM_EXTRACT_JS',
    '_attach_login_network_trace',
    '_auth_storage_snapshot',
    '_check_keep_login',
    '_clean_text_locator_value',
    '_click_first_available',
    '_click_login_submit',
    '_click_text_locator',
    '_element_text',
    '_fill_auto_input',
    '_fill_first_available',
    '_has_visible_locator',
    '_input_meta',
    '_is_login_response',
    '_locator_candidates',
    '_login_before_scan',
    '_looks_like_login_page',
    '_page_available_for_screenshot',
    '_redacted_response_summary',
    '_request_failure_text',
    '_safe_page_evaluate',
    '_safe_url_label',
    '_scan_error',
    '_scan_extract_dom',
    '_scan_launch',
    '_scan_locator_quality',
    '_scan_navigate',
    '_scan_page_state',
    '_scan_screenshot',
    '_scan_trace',
    '_score_input',
    '_step_timeout',
    '_wait_after_login_submit',
    'contextmanager',
    'ensure_functional_dirs',
    'json',
    'launch_chromium_browser',
    'os',
    're',
    'time',
    'urlparse',
    'uuid4',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.functional_testing"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl__locator_candidates(value: Any, defaults: list[str]) -> list[str]:
    raw_items: list[str] = []
    if isinstance(value, list):
        raw_items = [str(item) for item in value]
    elif value:
        raw_items = re.split(r"[\r\n]+", str(value))
    candidates: list[str] = []
    for item in [*raw_items, *defaults]:
        locator = str(item or "").strip()
        if locator and locator not in candidates:
            candidates.append(locator)
    return candidates


def _impl__scan_trace(trace: list[str], message: str) -> None:
    trace.append(message)


def _impl__scan_error(message: str, trace: list[str]) -> FunctionalScanError:
    return FunctionalScanError(message, trace)


def _impl__fill_first_available(page: Any, locators: list[str], value: str, name: str, trace: list[str]) -> str:
    last_error = ""
    for locator in locators:
        try:
            target = page.locator(locator).first
            target.wait_for(state="visible", timeout=5000)
            target.fill(value)
            _scan_trace(trace, f"已填写{name}：{locator}")
            return locator
        except Exception as exc:
            last_error = str(exc)
    raise _scan_error(f"登录未成功，请检查{name}定位器。最后错误：{last_error[:300]}", trace)


def _impl__clean_text_locator_value(locator: str) -> str:
    value = locator.strip()[5:].strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    return value.strip()


def _impl__element_text(locator: Any) -> str:
    try:
        return locator.evaluate(
            """
            (el) => (el.innerText || el.textContent || el.value || el.getAttribute("aria-label") || "").trim().replace(/\\s+/g, " ")
            """
        )
    except Exception:
        return ""


def _impl__click_text_locator(page: Any, locator: str, trace: list[str]) -> bool:
    target_text = _clean_text_locator_value(locator)
    if not target_text:
        return False
    targets = page.locator(locator)
    try:
        count = min(targets.count(), 30)
    except Exception:
        return False

    visible_indexes: list[int] = []
    exact_indexes: list[int] = []
    for index in range(count):
        item = targets.nth(index)
        try:
            if not item.is_visible(timeout=500):
                continue
            visible_indexes.append(index)
            if _element_text(item) == target_text:
                exact_indexes.append(index)
        except Exception:
            continue

    for index in exact_indexes:
        try:
            targets.nth(index).click()
            _scan_trace(trace, f"已点击登录按钮：{locator}（精确文本）")
            return True
        except Exception:
            continue

    for index in reversed(visible_indexes):
        try:
            text = _element_text(targets.nth(index))
            targets.nth(index).click()
            _scan_trace(trace, f"已点击登录按钮：{locator}（可见候选：{text or index}）")
            return True
        except Exception:
            continue
    return False


def _impl__click_first_available(page: Any, locators: list[str], name: str, trace: list[str]) -> str:
    last_error = ""
    for locator in locators:
        try:
            if name == "登录按钮" and locator.strip().lower().startswith("text=") and _click_text_locator(page, locator, trace):
                return locator
            target = page.locator(locator).last if name == "登录按钮" else page.locator(locator).first
            target.wait_for(state="visible", timeout=5000)
            target.click()
            _scan_trace(trace, f"已点击{name}：{locator}")
            return locator
        except Exception as exc:
            last_error = str(exc)
    raise _scan_error(f"登录未成功，请检查{name}定位器。最后错误：{last_error[:300]}", trace)


def _impl__input_meta(locator: Any, index: int) -> Dict[str, Any]:
    return locator.evaluate(
        """
        (el, index) => {
          const textOf = (node) => (node && (node.innerText || node.textContent || "") || "").trim().replace(/\\s+/g, " ").slice(0, 160);
          const wrap = el.closest(".el-form-item,.ant-form-item,.form-item,.field,.input-item,.login-item,.login-form,.form-group,label") || el.parentElement;
          const rect = el.getBoundingClientRect();
          return {
            index,
            type: (el.getAttribute("type") || "").toLowerCase(),
            id: el.id || "",
            name: el.getAttribute("name") || "",
            placeholder: el.getAttribute("placeholder") || "",
            autocomplete: el.getAttribute("autocomplete") || "",
            ariaLabel: el.getAttribute("aria-label") || "",
            labelText: textOf(wrap),
            visible: !!(rect.width && rect.height)
          };
        }
        """,
        index,
    )


def _impl__score_input(meta: Dict[str, Any], kind: str) -> int:
    text = " ".join(
        str(meta.get(key) or "")
        for key in ["type", "id", "name", "placeholder", "autocomplete", "ariaLabel", "labelText"]
    ).lower()
    input_type = str(meta.get("type") or "").lower()
    if not meta.get("visible") or input_type in {"hidden", "checkbox", "radio", "submit", "button"}:
        return -100
    if kind == "password":
        score = 0
        if input_type == "password":
            score += 100
        for keyword in ["密码", "パスワード", "password", "pwd"]:
            if keyword.lower() in text:
                score += 30
        return score

    if input_type == "password":
        return -100
    score = 5
    for keyword in ["邮箱", "邮件", "手机号", "手机", "账号", "帐号", "用户名", "名字", "メール", "email", "mail", "phone", "mobile", "account", "user", "name"]:
        if keyword.lower() in text:
            score += 30
    if input_type in {"email", "tel", "text", ""}:
        score += 10
    return score


def _impl__fill_auto_input(page: Any, value: str, kind: str, name: str, trace: list[str]) -> str:
    inputs = page.locator("input, textarea")
    candidates: list[tuple[int, int, Dict[str, Any]]] = []
    try:
        count = min(inputs.count(), 40)
    except Exception as exc:
        raise _scan_error(f"登录未成功，无法读取登录表单输入框：{str(exc)[:300]}", trace)
    for index in range(count):
        item = inputs.nth(index)
        try:
            meta = _input_meta(item, index)
            score = _score_input(meta, kind)
            if score > 0:
                candidates.append((score, index, meta))
        except Exception:
            continue
    if not candidates:
        raise _scan_error(f"登录未成功，自动识别不到{name}", trace)
    score, index, meta = sorted(candidates, key=lambda item: item[0], reverse=True)[0]
    inputs.nth(index).fill(value)
    label = meta.get("placeholder") or meta.get("name") or meta.get("id") or meta.get("labelText") or f"input[{index}]"
    _scan_trace(trace, f"已自动填写{name}：{label}，匹配分 {score}")
    return f"input:nth({index})"


def _impl__click_login_submit(page: Any, locators: list[str], trace: list[str]) -> str:
    """点击登录按钮 + 按 Enter 双重保险（SPA 兼容）"""
    clicked = None
    # 1. 优先使用 locator 点击
    try:
        clicked = _click_first_available(page, locators, "登录按钮", trace)
        page.wait_for_timeout(500)
    except FunctionalScanError:
        pass

    # 2. 尝试 button:has-text 系列
    if not clicked:
        fallback_locators = [
            'button:has-text("登录")',
            'button:has-text("登入")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button:has-text("ログイン")',
            '[role="button"]:has-text("登录")',
            '[role="button"]:has-text("Login")',
            '.el-button--primary',
            '.ant-btn-primary',
            '.el-button:has-text("登录")',
            '.ant-btn:has-text("登录")',
            '[class*="btn-primary"]',
            '[class*="el-button--primary"]',
            'button[type="submit"]',
            'input[type="submit"]',
            'text=登录',
            'text=Login',
        ]
        for locator in fallback_locators:
            try:
                target = page.locator(locator).last
                target.wait_for(state="visible", timeout=3000)
                target.click()
                page.wait_for_timeout(500)
                clicked = locator
                _scan_trace(trace, f"已点击登录按钮(兜底)：{locator}")
                break
            except Exception:
                continue

    # 3. 在密码框按 Enter 提交 — 这是最可靠的 SPA 表单提交方式
    _scan_trace(trace, "在密码框按 Enter 提交（确保表单提交触发）...")
    try:
        password_input = page.locator('input[type="password"]').first
        if password_input.is_visible():
            password_input.focus()
            page.wait_for_timeout(200)
            password_input.press("Enter")
            page.wait_for_timeout(1500)
            _scan_trace(trace, "已在密码框按 Enter 提交")
    except Exception:
        pass

    if clicked:
        return clicked
    raise _scan_error("登录未成功，找不到登录按钮", trace)


def _impl__check_keep_login(page: Any, trace: list[str]) -> None:
    checkbox_locators = [
        'label:has-text("保持账号登录")',
        'text=保持账号登录',
        'input[type="checkbox"]',
        '.el-checkbox:has-text("保持账号登录")',
        '.ant-checkbox-wrapper:has-text("保持账号登录")',
    ]
    for locator in checkbox_locators:
        try:
            target = page.locator(locator).first
            target.wait_for(state="visible", timeout=1500)
            try:
                input_target = target if locator.startswith("input") else target.locator('input[type="checkbox"]').first
                if input_target.count() and not input_target.is_checked(timeout=500):
                    input_target.check(force=True)
                    _scan_trace(trace, f"已勾选保持账号登录：{locator}")
                    return
                if input_target.count() and input_target.is_checked(timeout=500):
                    _scan_trace(trace, "保持账号登录已是勾选状态")
                    return
            except Exception:
                pass
            target.click()
            _scan_trace(trace, f"已点击保持账号登录：{locator}")
            return
        except Exception:
            continue
    _scan_trace(trace, "未找到保持账号登录选项，继续登录")


def _impl__safe_url_label(url: str) -> str:
    try:
        parsed = urlparse(url)
        return f"{parsed.netloc}{parsed.path}"
    except Exception:
        return str(url).split("?")[0][:120]


def _impl__attach_login_network_trace(page: Any, trace: list[str]) -> list[str]:
    events: list[str] = []

    def is_interesting(url: str, method: str = "") -> bool:
        text = url.lower()
        return method.upper() == "POST" or any(keyword in text for keyword in ["login", "auth", "token", "user", "partner"])

    def on_request(request: Any) -> None:
        try:
            if is_interesting(request.url, request.method):
                events.append(f"请求 {request.method} {_safe_url_label(request.url)}")
        except Exception:
            return

    def on_response(response: Any) -> None:
        try:
            request = response.request
            if is_interesting(response.url, request.method):
                events.append(f"响应 {response.status} {request.method} {_safe_url_label(response.url)}")
        except Exception:
            return

    page.on("request", on_request)
    page.on("response", on_response)
    _scan_trace(trace, "已开启登录阶段网络请求监听")
    return events


def _impl__is_login_response(response: Any) -> bool:
    """宽松检测：所有 POST 请求都视为潜在登录请求"""
    try:
        method = response.request.method.upper()
        if method != "POST":
            return False
        url = response.url.lower()
        # 优先匹配已知登录关键词
        if any(keyword in url for keyword in ["login", "auth", "token", "partnerlogin", "signin", "sign-in", "logon", "authenticate"]):
            return True
        # 兜底：任何 POST 到同源的 JSON/XHR 请求都尝试捕获
        # 避免漏掉不包含关键词的登录 API
        return True
    except Exception:
        return False


def _impl__redacted_response_summary(response: Any) -> str:
    try:
        payload = response.json()
    except Exception:
        try:
            text = response.text()
        except Exception:
            text = ""
        return f"HTTP {response.status}，响应文本：{text[:180]}"

    if isinstance(payload, dict):
        parts = [f"HTTP {response.status}"]
        for key in ["success", "code", "msg", "message", "error"]:
            if key in payload:
                parts.append(f"{key}={payload.get(key)}")
        data = payload.get("data")
        if isinstance(data, dict):
            safe_keys = [key for key in data.keys() if not re.search(r"token|password|secret|authorization", str(key), re.I)]
            sensitive_keys = [key for key in data.keys() if key not in safe_keys]
            if safe_keys:
                parts.append(f"data字段={','.join(map(str, safe_keys[:12]))}")
            if sensitive_keys:
                parts.append(f"敏感字段已隐藏={','.join(map(str, sensitive_keys[:8]))}")
        return "，".join(parts)
    return f"HTTP {response.status}，响应类型={type(payload).__name__}"


def _impl__auth_storage_snapshot(page: Any) -> str:
    try:
        return page.evaluate(
            """
            () => JSON.stringify({
              url: location.href,
              local: Object.keys(localStorage).filter((key) => /token|auth|user|login|session/i.test(key)).map((key) => [key, localStorage.getItem(key)]),
              session: Object.keys(sessionStorage).filter((key) => /token|auth|user|login|session/i.test(key)).map((key) => [key, sessionStorage.getItem(key)]),
              cookie: document.cookie || ""
            })
            """
        )
    except Exception:
        return ""


def _impl__wait_after_login_submit(page: Any, before_url: str, before_storage: str, trace: list[str], timeout: int) -> None:
    deadline = time.time() + min(max(timeout, 8), 20)
    last_url = before_url
    while time.time() < deadline:
        page.wait_for_timeout(500)
        current_url = page.url
        if current_url != before_url:
            _scan_trace(trace, f"检测到登录后页面跳转：{current_url}")
            return
        current_storage = _auth_storage_snapshot(page)
        if current_storage and current_storage != before_storage:
            _scan_trace(trace, "检测到登录态写入 localStorage/sessionStorage/cookie")
            return
        if last_url != current_url:
            last_url = current_url
        if not _looks_like_login_page(page):
            _scan_trace(trace, "登录表单已消失")
            return
    _scan_trace(trace, "登录后未检测到明显跳转或登录态变化，继续尝试进入目标页面")


def _impl__has_visible_locator(page: Any, locator: str, timeout: int = 300) -> bool:
    try:
        targets = page.locator(locator)
        count = min(targets.count(), 5)
        return any(targets.nth(index).is_visible(timeout=timeout) for index in range(count))
    except Exception:
        return False


def _impl__looks_like_login_page(page: Any, expected_url: str = "") -> bool:
    try:
        current_url = (page.url or "").lower()
        expected = (expected_url or "").lower()
        if ("login" in current_url or "signin" in current_url) and current_url != expected:
            return True
        has_password = _has_visible_locator(page, 'input[type="password"]')
        if not has_password:
            return False
        has_account = any(
            _has_visible_locator(page, locator)
            for locator in [
                'input[name="username"]',
                'input[name="account"]',
                'input[name="mobile"]',
                'input[name="email"]',
                'input[placeholder*="账号"]',
                'input[placeholder*="用户名"]',
                'input[placeholder*="手机号"]',
                'input[placeholder*="邮箱"]',
            ]
        )
        has_login_button = any(
            _has_visible_locator(page, locator)
            for locator in ["text=登录", "text=登入", "text=登陆", "text=Login", "text=Sign in", "text=ログイン"]
        )
        return has_account or has_login_button
    except Exception:
        return False


def _impl__login_before_scan(page: Any, page_url: str, auth: Dict[str, Any], timeout: int, trace: list[str]) -> None:
    login_url = str(auth.get("login_url") or "").strip()
    username = str(auth.get("username") or "")
    password = str(auth.get("password") or "")
    if not login_url or not username or not password:
        raise _scan_error("登录未成功，请填写登录页URL、登录账号和登录密码", trace)

    username_locators = _locator_candidates(
        auth.get("username_locator"),
        [
            'input[name="username"]',
            'input[name="account"]',
            'input[name="mobile"]',
            'input[name="email"]',
            'input[placeholder*="账号"]',
            'input[placeholder*="用户名"]',
            'input[placeholder*="手机号"]',
            'input[placeholder*="邮箱"]',
            'input[placeholder*="メール"]',
            'input[placeholder*="email" i]',
            'input[type="text"]',
            'input:not([type])',
        ],
    )
    password_locators = _locator_candidates(
        auth.get("password_locator"),
        [
            'input[type="password"]',
            'input[name="password"]',
            'input[placeholder*="密码"]',
            'input[placeholder*="パスワード"]',
            'input[placeholder*="password" i]',
        ],
    )
    submit_locators = _locator_candidates(
        auth.get("submit_locator"),
        [
            'button[type="submit"]',
            'button:has-text("登录")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button:has-text("ログイン")',
            'input[type="submit"]',
            'a:has-text("登录")',
            'a:has-text("Login")',
            "text=登录",
            "text=登入",
            "text=登陆",
            "text=Login",
            "text=Sign in",
            "text=ログイン",
        ],
    )

    # 如果当前页面已经是登录页，跳过重复导航（支持 SPA hash 路由）
    if not _looks_like_login_page(page):
      _scan_trace(trace, f"打开登录页：{login_url}")
      page.goto(login_url, wait_until="domcontentloaded")
      page.wait_for_timeout(500)
    else:
      _scan_trace(trace, f"当前页面已是登录页，跳过导航：{page.url}")
    try:
        _fill_first_available(page, username_locators, username, "账号输入框", trace)
    except FunctionalScanError:
        _fill_auto_input(page, username, "username", "账号输入框", trace)
    try:
        _fill_first_available(page, password_locators, password, "密码输入框", trace)
    except FunctionalScanError:
        _fill_auto_input(page, password, "password", "密码输入框", trace)
    _check_keep_login(page, trace)
    network_events = _attach_login_network_trace(page, trace)
    before_url = page.url
    before_storage = _auth_storage_snapshot(page)
    login_response = None
    try:
        with page.expect_response(_is_login_response, timeout=15000) as response_info:
            _click_login_submit(page, submit_locators, trace)
        login_response = response_info.value
    except FunctionalScanError:
        raise
    except Exception:
        _scan_trace(trace, "点击登录后 15 秒内未捕获登录接口响应")
    if login_response is not None:
        _scan_trace(trace, f"登录接口返回摘要：{_redacted_response_summary(login_response)}")

    success_selector = str(auth.get("success_selector") or "").strip()
    success_url_contains = str(auth.get("success_url_contains") or "").strip()
    if success_selector:
        _scan_trace(trace, f"等待登录成功元素：{success_selector}")
        page.wait_for_selector(success_selector, timeout=timeout * 1000)
    elif success_url_contains:
        _scan_trace(trace, f"等待登录成功 URL 包含：{success_url_contains}")
        page.wait_for_url(f"**{success_url_contains}**", timeout=timeout * 1000)
    else:
        _scan_trace(trace, "等待登录请求和页面跳转完成")
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            page.wait_for_timeout(2000)
        _wait_after_login_submit(page, before_url, before_storage, trace, timeout)
    if network_events:
        _scan_trace(trace, "登录阶段网络请求：")
        for item in network_events[-12:]:
            _scan_trace(trace, f"  {item}")
    else:
        _scan_trace(trace, "登录阶段没有捕获到登录/认证相关请求")

    _scan_trace(trace, f"进入目标页面：{page_url}")
    page.goto(page_url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        page.wait_for_timeout(1200)
    if _looks_like_login_page(page, expected_url=page_url):
        # 检查页面是否有错误提示信息
        try:
            error_texts = ["密码错误", "账号错误", "用户名错误", "验证码错误", "登录失败", "account", "password", "invalid", "error"]
            for err_text in error_texts:
                err_el = page.locator(f'text={err_text}').first
                if err_el.is_visible(timeout=500):
                    _scan_trace(trace, f"页面检测到错误提示(含「{err_text}」)：{err_el.inner_text()[:100]}")
                    break
        except Exception:
            pass
        raise _scan_error(f"登录未成功，请检查账号密码或登录定位器。当前页面：{page.url}", trace)
    _scan_trace(trace, f"目标页面已打开：{page.url}")


def _impl__safe_page_evaluate(page: Any, js: str, default: Any = None) -> Any:
    """安全执行 page.evaluate，失败时返回 default 而非抛异常。"""
    try:
        return page.evaluate(js)
    except Exception as exc:
        return default


@contextmanager
def _impl__step_timeout(page: Any, seconds: int, step_name: str, trace: list[str]):
    """为扫描子步骤设置独立超时。超时或异常时自动记录到 trace。"""
    old_timeout = None
    try:
        old_timeout = getattr(page, '_default_timeout', 30000)
        page.set_default_timeout(seconds * 1000)
        yield
    except Exception as exc:
        msg = str(exc)[:200]
        _scan_trace(trace, f"步骤「{step_name}」超时或失败 ({seconds}s): {msg}")
        raise
    finally:
        if old_timeout is not None:
            page.set_default_timeout(old_timeout)


def _impl__scan_launch(playwright: Any, headless: bool = True, proxy: str | None = None) -> Any:
    """启动浏览器，返回 browser 实例。"""
    browser = launch_chromium_browser(playwright, headless=headless, proxy=proxy)
    return browser


def _impl__scan_navigate(page: Any, url: str, timeout_sec: int, trace: list[str]) -> None:
    """导航到目标页面，含等待加载完成。"""
    _scan_trace(trace, f"导航到：{url}")
    page.goto(url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_sec * 1000, 8000))
    except Exception:
        page.wait_for_timeout(500)
    _scan_trace(trace, f"页面已加载：{page.url}")


def _impl__scan_extract_dom(page: Any, trace: list[str]) -> dict:
    """提取页面 DOM 摘要，含降级处理。"""
    _scan_trace(trace, "开始提取页面 DOM 摘要")
    result = _safe_page_evaluate(page, _DOM_EXTRACT_JS, default={})
    elements = result.get("elements") or []
    if result.get("error"):
        _scan_trace(trace, f"DOM 提取部分失败：{result['error']}")
    _scan_trace(trace, f"DOM 提取完成：{len(elements)} 个可操作元素")
    return result


def _impl__scan_screenshot(page: Any, trace: list[str]) -> Path:
    """截取页面截图。"""
    screenshot = SCREENSHOT_DIR / f"functional-{uuid4()}.png"
    try:
        page.screenshot(path=str(screenshot), full_page=True)
        _scan_trace(trace, f"截图已保存：{screenshot.name}")
    except Exception as exc:
        _scan_trace(trace, f"截图失败：{str(exc)[:200]}")
    return screenshot


def _impl__request_failure_text(request: Any) -> str:
    try:
        failure = getattr(request, "failure", None)
        if callable(failure):
            failure = failure()
        if isinstance(failure, dict):
            return str(failure.get("errorText") or failure.get("error") or "request failed")
        if failure:
            return str(failure)
    except Exception as exc:
        return str(exc)
    return "request failed"


def _impl__page_available_for_screenshot(page: Any) -> bool:
    if not page:
        return False
    try:
        is_closed = getattr(page, "is_closed", None)
        if callable(is_closed):
            return not bool(is_closed())
    except Exception:
        return False
    return True


def _impl__scan_locator_quality(elements: list[dict]) -> dict:
    """评估定位器质量。"""
    total = len(elements)
    if total == 0:
        return {"total_elements": 0, "score": "unknown", "recommendation": "未能提取到页面元素"}
    with_data_testid = sum(1 for el in elements if el.get("data_testid"))
    with_id = sum(1 for el in elements if el.get("id"))
    with_name = sum(1 for el in elements if el.get("name"))
    weak_locators = sum(1 for el in elements if str(el.get("locator","")).startswith("text=") and not el.get("id") and not el.get("name"))
    quality = {}
    quality["total_elements"] = total
    quality["with_data_testid"] = with_data_testid
    quality["with_id"] = with_id
    quality["with_name"] = with_name
    quality["weak_locators"] = weak_locators
    if with_data_testid >= total * 0.3:
        quality["score"] = "good"
    elif with_id >= total * 0.3:
        quality["score"] = "fair"
    else:
        quality["score"] = "poor"
    quality["recommendation"] = ""
    if quality["score"] == "poor" and weak_locators > 5:
        quality["recommendation"] = f"建议给 {weak_locators} 个无 id/name/data-testid 的交互元素添加 data-testid 属性"
    elif weak_locators > 5:
        quality["recommendation"] = f"有 {weak_locators} 个元素只用 text= 定位，容易因文案变更失效"
    return quality


def _impl__scan_page_state(partial: dict, console_errors: list[str], network_errors: list[str]) -> dict[str, Any]:
    text = " ".join(
        [
            str(partial.get("title") or ""),
            " ".join(str(item or "") for item in partial.get("headings") or []),
            " ".join(str((item or {}).get("text") or "") for item in partial.get("elements") or []),
        ]
    ).lower()
    current_url = str(partial.get("url") or "").lower()
    login_markers = ("login", "signin", "登录", "登陆", "用户名", "密码", "验证码")
    error_markers = ("404", "500", "502", "503", "504", "error", "exception", "not found", "错误", "异常", "无法访问")
    is_login_page = any(marker in current_url or marker in text for marker in login_markers)
    is_error_page = any(marker in current_url or marker in text for marker in error_markers)
    elements = partial.get("elements") or []
    if partial.get("error_step"):
        scan_status = "partial"
    elif is_error_page:
        scan_status = "error_page"
    elif not elements:
        scan_status = "no_interactive_elements"
    else:
        scan_status = "ok"
    return {
        "scan_status": scan_status,
        "is_login_page": is_login_page,
        "is_error_page": is_error_page,
        "interactive_count": len(elements),
        "console_error_count": len(console_errors),
        "network_error_count": len(network_errors),
        "needs_auth": is_login_page,
    }


def _impl_scan_page_dom(page_url: str, timeout: int = 30, auth: Dict[str, Any] | None = None, proxy: str | None = None) -> Dict[str, str]:
    """Scan a page and return DOM, screenshot, quality, page state, and trace."""
    ensure_functional_dirs()
    started = time.time()
    trace: list[str] = []
    partial: dict = {"title": "", "url": "", "headings": [], "elements": [], "error_step": None, "error": None}
    console_errors: list[str] = []
    network_errors: list[str] = []

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _scan_error(f"Playwright 不可用：{exc}", trace) from exc

    browser = None
    context = None
    page = None
    screenshot_path = SCREENSHOT_DIR / f"functional-{uuid4()}.png"
    if proxy is None:
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")

    try:
        with sync_playwright() as p:
            _scan_trace(trace, "启动浏览器..." + (f" (代理: {proxy})" if proxy else ""))
            browser = _scan_launch(p, headless=True, proxy=proxy)
            context = browser.new_context()
            page = context.new_page()
            page.on("console", lambda msg: console_errors.append(f"{msg.type}: {msg.text}") if msg.type in {"error", "warning"} else None)
            page.on("requestfailed", lambda request: network_errors.append(f"{request.method} {request.url}: {_request_failure_text(request)}"))

            with _step_timeout(page, min(timeout, 20), "导航到目标页面", trace):
                _scan_navigate(page, page_url, timeout, trace)

            auth_config = auth or {}
            if auth_config.get("enabled"):
                with _step_timeout(page, min(timeout, 25), "登录流程", trace):
                    _login_before_scan(page, page_url, auth_config, timeout, trace)

            with _step_timeout(page, 10, "DOM 提取", trace):
                partial = _scan_extract_dom(page, trace)

            with _step_timeout(page, 5, "截图", trace):
                screenshot_path = _scan_screenshot(page, trace)
    except FunctionalScanError:
        raise
    except Exception as exc:
        error_msg = str(exc)[:300]
        _scan_trace(trace, f"扫描过程中断：{error_msg}")
        partial["error_step"] = "unknown"
        partial["error"] = error_msg
        if _page_available_for_screenshot(page):
            try:
                screenshot_path = _scan_screenshot(page, trace)
            except Exception:
                pass
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass
        if context:
            try:
                context.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass

    elements = partial.get("elements") or []
    locator_quality = _scan_locator_quality(elements)
    page_state = _scan_page_state(partial, console_errors, network_errors)
    scan_result = {
        "scan_seconds": round(time.time() - started, 2),
        "scan_trace": trace,
        **page_state,
        "title": partial.get("title", ""),
        "url": partial.get("url", ""),
        "headings": partial.get("headings", []),
        "elements": elements,
        "locator_quality": locator_quality,
        "page_state": page_state,
        "console_errors": console_errors[:50],
        "network_errors": network_errors[:50],
    }
    if partial.get("error_step"):
        scan_result["error_step"] = partial["error_step"]
        scan_result["error"] = partial["error"]
    return {
        "dom_summary": json.dumps(scan_result, ensure_ascii=False, indent=2),
        "screenshot_path": str(screenshot_path),
        "scan_trace": trace,
    }


def _locator_candidates(value: Any, defaults: list[str]) -> list[str]:
    _sync_compat_globals()
    return _impl__locator_candidates(value, defaults)

def _scan_trace(trace: list[str], message: str) -> None:
    _sync_compat_globals()
    return _impl__scan_trace(trace, message)

def _scan_error(message: str, trace: list[str]) -> FunctionalScanError:
    _sync_compat_globals()
    return _impl__scan_error(message, trace)

def _fill_first_available(page: Any, locators: list[str], value: str, name: str, trace: list[str]) -> str:
    _sync_compat_globals()
    return _impl__fill_first_available(page, locators, value, name, trace)

def _clean_text_locator_value(locator: str) -> str:
    _sync_compat_globals()
    return _impl__clean_text_locator_value(locator)

def _element_text(locator: Any) -> str:
    _sync_compat_globals()
    return _impl__element_text(locator)

def _click_text_locator(page: Any, locator: str, trace: list[str]) -> bool:
    _sync_compat_globals()
    return _impl__click_text_locator(page, locator, trace)

def _click_first_available(page: Any, locators: list[str], name: str, trace: list[str]) -> str:
    _sync_compat_globals()
    return _impl__click_first_available(page, locators, name, trace)

def _input_meta(locator: Any, index: int) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__input_meta(locator, index)

def _score_input(meta: Dict[str, Any], kind: str) -> int:
    _sync_compat_globals()
    return _impl__score_input(meta, kind)

def _fill_auto_input(page: Any, value: str, kind: str, name: str, trace: list[str]) -> str:
    _sync_compat_globals()
    return _impl__fill_auto_input(page, value, kind, name, trace)

def _click_login_submit(page: Any, locators: list[str], trace: list[str]) -> str:
    _sync_compat_globals()
    return _impl__click_login_submit(page, locators, trace)

def _check_keep_login(page: Any, trace: list[str]) -> None:
    _sync_compat_globals()
    return _impl__check_keep_login(page, trace)

def _safe_url_label(url: str) -> str:
    _sync_compat_globals()
    return _impl__safe_url_label(url)

def _attach_login_network_trace(page: Any, trace: list[str]) -> list[str]:
    _sync_compat_globals()
    return _impl__attach_login_network_trace(page, trace)

def _is_login_response(response: Any) -> bool:
    _sync_compat_globals()
    return _impl__is_login_response(response)

def _redacted_response_summary(response: Any) -> str:
    _sync_compat_globals()
    return _impl__redacted_response_summary(response)

def _auth_storage_snapshot(page: Any) -> str:
    _sync_compat_globals()
    return _impl__auth_storage_snapshot(page)

def _wait_after_login_submit(page: Any, before_url: str, before_storage: str, trace: list[str], timeout: int) -> None:
    _sync_compat_globals()
    return _impl__wait_after_login_submit(page, before_url, before_storage, trace, timeout)

def _has_visible_locator(page: Any, locator: str, timeout: int=300) -> bool:
    _sync_compat_globals()
    return _impl__has_visible_locator(page, locator, timeout)

def _looks_like_login_page(page: Any, expected_url: str='') -> bool:
    _sync_compat_globals()
    return _impl__looks_like_login_page(page, expected_url)

def _login_before_scan(page: Any, page_url: str, auth: Dict[str, Any], timeout: int, trace: list[str]) -> None:
    _sync_compat_globals()
    return _impl__login_before_scan(page, page_url, auth, timeout, trace)

def _safe_page_evaluate(page: Any, js: str, default: Any=None) -> Any:
    _sync_compat_globals()
    return _impl__safe_page_evaluate(page, js, default)

def _step_timeout(page: Any, seconds: int, step_name: str, trace: list[str]):
    _sync_compat_globals()
    return _impl__step_timeout(page, seconds, step_name, trace)

def _scan_launch(playwright: Any, headless: bool=True, proxy: str | None=None) -> Any:
    _sync_compat_globals()
    return _impl__scan_launch(playwright, headless, proxy)

def _scan_navigate(page: Any, url: str, timeout_sec: int, trace: list[str]) -> None:
    _sync_compat_globals()
    return _impl__scan_navigate(page, url, timeout_sec, trace)

def _scan_extract_dom(page: Any, trace: list[str]) -> dict:
    _sync_compat_globals()
    return _impl__scan_extract_dom(page, trace)

def _scan_screenshot(page: Any, trace: list[str]) -> Path:
    _sync_compat_globals()
    return _impl__scan_screenshot(page, trace)

def _request_failure_text(request: Any) -> str:
    _sync_compat_globals()
    return _impl__request_failure_text(request)

def _page_available_for_screenshot(page: Any) -> bool:
    _sync_compat_globals()
    return _impl__page_available_for_screenshot(page)

def _scan_locator_quality(elements: list[dict]) -> dict:
    _sync_compat_globals()
    return _impl__scan_locator_quality(elements)

def _scan_page_state(partial: dict, console_errors: list[str], network_errors: list[str]) -> dict[str, Any]:
    _sync_compat_globals()
    return _impl__scan_page_state(partial, console_errors, network_errors)

def scan_page_dom(page_url: str, timeout: int=30, auth: Dict[str, Any] | None=None, proxy: str | None=None) -> Dict[str, str]:
    _sync_compat_globals()
    return _impl_scan_page_dom(page_url, timeout, auth, proxy)
