from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'Dict',
    'Iterable',
    '_normalize_text',
    '_quote_locator_text',
    '_split_locator_values',
    '_text_locator_value',
    're',
    'time',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.executors"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl__step_timeout_ms(step: Dict[str, Any], default_seconds: int, cap_seconds: int = 15) -> int:
    raw = step.get("timeout")
    if raw in (None, ""):
        return min(default_seconds, cap_seconds) * 1000
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return min(default_seconds, cap_seconds) * 1000
    if value <= 0:
        return min(default_seconds, cap_seconds) * 1000
    # < 1000 视为秒（转换为毫秒），≥ 1000 视为毫秒直接使用
    return value * 1000 if value < 1000 else value


def _impl__split_locator_values(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[\r\n]+", str(value or ""))
    result = []
    for item in items:
        text_value = str(item or "").strip()
        if text_value and text_value not in result:
            result.append(text_value)
    return result


def _impl__merge_locator_values(*groups: Iterable[str]) -> list[str]:
    result: list[str] = []
    for group in groups:
        for item in group:
            text_value = str(item or "").strip()
            if text_value and text_value not in result:
                result.append(text_value)
    return result


def _impl__text_locator_value(locator: str) -> str:
    text_value = str(locator or "").strip()
    if text_value.startswith("text="):
        return text_value[5:].strip().strip('"').strip("'")
    match = re.match(r"^(?:button|a|\[role=['\"]?button['\"]?\]):has-text\(['\"](.+?)['\"]\)$", text_value)
    return match.group(1) if match else ""


def _impl__locator_candidates(step: Dict[str, Any]) -> list[str]:
    primary = str(step.get("locator") or "").strip()
    candidates = []
    for item in [primary, *_split_locator_values(step.get("fallback_locators"))]:
        if item and item not in candidates:
            candidates.append(item)
    if primary:
        placeholder_match = re.match(r"^placeholder\s*=\s*(.+)$", primary, flags=re.I)
        if placeholder_match:
            value = _quote_locator_text(placeholder_match.group(1).strip())
            candidates.extend([f'input[placeholder*="{value}"]', f'textarea[placeholder*="{value}"]'])
        name_match = re.match(r"^name\s*=\s*(.+)$", primary, flags=re.I)
        if name_match:
            value = _quote_locator_text(name_match.group(1).strip())
            candidates.extend([f'[name="{value}"]', f'input[name="{value}"]'])
        text_value = _text_locator_value(primary)
        if text_value:
            quoted = _quote_locator_text(text_value)
            candidates.extend(
                [
                    f'button:has-text("{quoted}")',
                    f'a:has-text("{quoted}")',
                    f'[role="button"]:has-text("{quoted}")',
                    f'input[type="button"][value*="{quoted}"]',
                    f'input[type="submit"][value*="{quoted}"]',
                ]
            )
    step_name = str(step.get("name") or "")
    if "搜索" in step_name or "search" in step_name.lower() or "search" in primary.lower():
        candidates.extend([
            "button:has(img[src*='smallss'])",
            "button[data-logger-action-type*='rakumart']",
            ".flexAndCenter button",
            "button:has(.el-icon-search)",
        ])
    if any(k in step_name.lower() or k in primary.lower() for k in ("cart", "カート", "购物车", "加购", "買い物かご")):
        candidates.extend([
            'button:has-text("ショッピングカートに入れる")',
            'button:has-text("カートに追加")',
            'button:has-text("カートに入れる")',
            'button:has-text("カート")',
            '.el-button--primary:has-text("カート")',
        ])
    result = []
    for item in candidates:
        if item and item not in result:
            result.append(item)
    return result


def _impl__classify_ui_error(error: str, step: Dict[str, Any], current_url: str = "") -> Dict[str, Any]:
    error_lower = str(error or "").lower()
    action = step.get("action") or ""
    if "unknown engine" in error_lower or "unexpected token" in error_lower:
        category = "定位器写法错误"
        reason = "locator 写法不符合 Playwright 规则。"
        suggestion = "重新扫描页面 DOM 后生成步骤，或改成 id/name/placeholder/text 这类稳定定位。"
    elif "strict mode violation" in error_lower:
        category = "定位器不唯一"
        reason = "locator 匹配到了多个元素，执行器无法确定要操作哪一个。"
        suggestion = "把 locator 改得更唯一，例如增加 id、name、placeholder 或更精确的按钮文案。"
    elif "waiting for" in error_lower and "timeout" in error_lower:
        category = "定位器找不到"
        reason = "规定时间内没有找到目标元素，可能是页面未进入预期状态、加载慢或定位器失效。"
        suggestion = "先看失败截图确认页面停留位置，再检查前一步操作和 locator。"
    elif "timeout" in error_lower:
        category = "操作超时"
        reason = "页面操作在指定时间内未完成，可能是页面加载慢或元素状态异常。"
        suggestion = "可适当增加超时设置，或检查页面是否有异常弹窗阻塞操作。"
    elif "not visible" in error_lower or "visible" in error_lower and "failed" in error_lower:
        category = "元素不可见/不可点击"
        reason = "元素存在但不可见或不可点击，可能被遮挡、折叠、未滚动到视图内或页面尚未渲染完成。"
        suggestion = "补充展开/等待步骤，或使用更准确的可见元素 locator。"
    elif "assert_url failed" in error:
        category = "页面未跳转或跳转地址不符合预期"
        reason = "执行后当前 URL 和预期不一致。"
        suggestion = "确认提交是否成功、登录态是否有效、预期跳转地址是否正确。"
    elif "text_assert failed" in error:
        category = "文案断言失败"
        reason = "页面实际文案和预期不一致，或当前页面不是预期页面。"
        suggestion = "确认产品文案是否变更，避免把弱文案作为主流程强断言。"
    elif "assert_value failed" in error:
        category = "输入值断言失败"
        reason = "输入框实际值和预期不一致，可能是输入未生效、控件自动格式化或定位到了错误输入框。"
        suggestion = "检查输入框 locator 是否唯一，并确认页面是否会自动格式化输入内容。"
    elif "login" in str(current_url or "").lower() and action != "goto":
        category = "登录态失效"
        reason = "执行时页面停留在登录页，后续业务步骤无法继续。"
        suggestion = "检查运行时账号密码、登录步骤和目标页面是否需要先登录。"
    else:
        category = "未知异常"
        reason = "执行过程中出现未分类异常。"
        suggestion = "结合失败截图、当前 URL 和失败步骤继续判断。"
    return {"category": category, "reason": reason, "suggestion": suggestion}


def _impl__resolve_locator(page: Any, candidates: list[str], timeout_ms: int, state: str = "visible") -> tuple[Any, str, int]:
    errors = []
    # 1. 第一轮：标准等待指定状态（如 visible）
    for locator in candidates:
        try:
            target = page.locator(locator).first
            req_state = "attached" if locator.strip().lower() in ("body", "html", ":root") else state
            target.wait_for(state=req_state, timeout=timeout_ms)
            count = page.locator(locator).count()
            return target, locator, count
        except Exception as exc:
            errors.append(f"{locator}: {exc}")
            continue

    # 2. 第二轮：若寻找可见元素失败，但元素在 DOM 中（如悬浮菜单、隐藏提示文案），查找其最近的可见祖先容器
    if state == "visible":
        for locator in candidates:
            try:
                target = page.locator(locator).first
                if target.count() > 0:
                    ancestor = target.locator(
                        "xpath=ancestor-or-self::*[not(contains(@style,'display: none')) and not(contains(@style,'display:none')) and not(self::html) and not(self::body)][1]"
                    )
                    if ancestor.count() > 0 and ancestor.first.is_visible():
                        return ancestor.first, f"{locator} (ancestor)", 1
            except Exception:
                continue

    # 3. 第三轮：尝试 locator heal 自愈
    for locator in candidates:
        try:
            healed = _heal_locator(page, locator, "; ".join(errors[-2:]))
            if healed:
                target = page.locator(healed).first
                target.wait_for(state=state, timeout=min(timeout_ms, 3000))
                return target, healed, page.locator(healed).count()
        except Exception:
            continue

    raise TimeoutError("未找到可用定位器：" + "；".join(errors[-4:]))


def _impl__wait_for_url_contains(page: Any, expected: str, timeout_ms: int, exact: bool = False) -> None:
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        current = page.url or ""
        if exact:
            if current.rstrip("/") == expected.rstrip("/"):
                return
        else:
            if expected in current:
                return
        page.wait_for_timeout(300)
    mode = "精确匹配" if exact else "包含"
    raise AssertionError(f"assert_url failed: expected {mode} {expected!r}, actual {page.url!r}")


def _impl__wait_text_contains(target: Any, expected: Any, timeout_ms: int) -> str:
    deadline = time.time() + max(timeout_ms, 1000) / 1000
    expected_text = _normalize_text(expected)
    last_text = ""
    last_error: Exception | None = None
    while True:
        remaining_ms = max(250, int((deadline - time.time()) * 1000))
        try:
            try:
                last_text = target.inner_text(timeout=min(1000, remaining_ms))
            except Exception:
                last_text = target.evaluate("el => el.innerText || el.textContent || ''")
            if expected_text in _normalize_text(last_text):
                return last_text
        except Exception as exc:
            last_error = exc
        if time.time() >= deadline:
            if last_error and not last_text:
                raise AssertionError(f"text_assert failed: expected {expected!r}, actual unavailable: {last_error}") from last_error
            raise AssertionError(f"text_assert failed: expected {expected!r}, actual {last_text!r}")
        try:
            target.page.wait_for_timeout(300)
        except Exception:
            time.sleep(0.3)


def _impl__heal_locator(page: Any, failed_locator: str, error_text: str) -> str | None:
    """尝试修复失败的定位器，返回新定位器或 None"""
    heal_candidates: list[str] = []

    # 策略 1: text=xxx → 跳过原始定位器，直接尝试包含匹配 / partial text
    if failed_locator.startswith("text="):
        target_text = failed_locator[5:].strip().strip("\"'")
        if target_text:
            # 转义双引号防止注入到 Playwright 选择器语法中
            safe_text = target_text.replace('"', '\\"')
            try:
                # 先试 :has-text（比 text= 更灵活）
                partial = page.locator(f':has-text("{safe_text}")')
                if partial.count() > 0:
                    heal_candidates.append(f':has-text("{safe_text}")')
                for tag in ["button", "a", "span", "div"]:
                    exact = page.locator(f'{tag}:has-text("{safe_text}")')
                    if exact.count() > 0:
                        heal_candidates.append(f'{tag}:has-text("{safe_text}")')
                # 最后试原始 text= 精确匹配（可能因为 DOM 刷新后重新可用）
                contains = page.locator(f"text={target_text}")
                if contains.count() > 0:
                    heal_candidates.append(f"text={target_text}")
            except Exception:
                pass

    # 策略 2: CSS 选择器 → 简化
    if not failed_locator.startswith("text="):
        simplified = re.sub(r"\.[a-zA-Z][\w-]*", "", failed_locator)
        if simplified != failed_locator:
            try:
                el = page.locator(simplified)
                if el.count() > 0:
                    heal_candidates.append(simplified)
            except Exception:
                pass
        ids = re.findall(r"#([a-zA-Z][\w-]*)", failed_locator)
        if ids:
            try:
                el = page.locator(f"#{ids[-1]}")
                if el.count() > 0:
                    heal_candidates.append(f"#{ids[-1]}")
            except Exception:
                pass

    if "search" in failed_locator.lower() or "搜索" in failed_locator:
        for search_cand in [
            "button:has(img[src*='smallss'])",
            "button[data-logger-action-type*='rakumart']",
            ".flexAndCenter button",
            "button:has(.el-icon-search)",
            "button[type='submit']",
        ]:
            try:
                el = page.locator(search_cand).first
                if el.count() > 0 and el.is_visible():
                    heal_candidates.append(search_cand)
            except Exception:
                pass

    if any(k in failed_locator.lower() for k in ("cart", "カート", "购物车", "加购", "買い物かご")):
        for cart_cand in [
            'button:has-text("ショッピングカートに入れる")',
            'button:has-text("カートに追加")',
            'button:has-text("カートに入れる")',
            'button:has-text("カート")',
            '.el-button--primary:has-text("カート")',
        ]:
            try:
                el = page.locator(cart_cand).first
                if el.count() > 0 and el.is_visible():
                    heal_candidates.append(cart_cand)
            except Exception:
                pass

    return heal_candidates[0] if heal_candidates else None


def _impl__wait_page_stable(page: Any, timeout: int = 1500) -> None:
    """等待页面加载稳定"""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception:
        pass
    page.wait_for_timeout(300)


def _step_timeout_ms(step: Dict[str, Any], default_seconds: int, cap_seconds: int = 15) -> int:
    _sync_compat_globals()
    return _impl__step_timeout_ms(step, default_seconds, cap_seconds)


def _split_locator_values(value: Any) -> list[str]:
    _sync_compat_globals()
    return _impl__split_locator_values(value)


def _merge_locator_values(*groups: Iterable[str]) -> list[str]:
    _sync_compat_globals()
    return _impl__merge_locator_values(*groups)


def _text_locator_value(locator: str) -> str:
    _sync_compat_globals()
    return _impl__text_locator_value(locator)


def _locator_candidates(step: Dict[str, Any]) -> list[str]:
    _sync_compat_globals()
    return _impl__locator_candidates(step)


def _classify_ui_error(error: str, step: Dict[str, Any], current_url: str='') -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__classify_ui_error(error, step, current_url)


def _resolve_locator(page: Any, candidates: list[str], timeout_ms: int, state: str='visible') -> tuple[Any, str, int]:
    _sync_compat_globals()
    return _impl__resolve_locator(page, candidates, timeout_ms, state)


def _wait_for_url_contains(page: Any, expected: str, timeout_ms: int, exact: bool=False) -> None:
    _sync_compat_globals()
    return _impl__wait_for_url_contains(page, expected, timeout_ms, exact)


def _wait_text_contains(target: Any, expected: Any, timeout_ms: int) -> str:
    _sync_compat_globals()
    return _impl__wait_text_contains(target, expected, timeout_ms)


def _heal_locator(page: Any, failed_locator: str, error_text: str) -> str | None:
    _sync_compat_globals()
    return _impl__heal_locator(page, failed_locator, error_text)


def _wait_page_stable(page: Any, timeout: int=1500) -> None:
    _sync_compat_globals()
    return _impl__wait_page_stable(page, timeout)
