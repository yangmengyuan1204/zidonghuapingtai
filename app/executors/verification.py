from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'Dict',
    'SCREENSHOT_DIR',
    '_check_success_condition',
    '_normalize_text',
    '_page_text_excerpt',
    '_step_has_business_assertion',
    'ensure_report_dirs',
    'urlparse',
    'uuid4',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.executors"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl__wait_after_action(page: Any, action: str) -> None:
    """根据操作类型等待页面响应"""
    if action in ("click", "select", "check", "uncheck"):
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            page.wait_for_timeout(500)
    elif action == "input":
        page.wait_for_timeout(100)
    elif action == "goto":
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            page.wait_for_timeout(500)


def _impl__capture_evidence_screenshot(page: Any, prefix: str, screenshots: list[str]) -> str:
    ensure_report_dirs()
    target = SCREENSHOT_DIR / f"{prefix}-{uuid4()}.png"
    try:
        page.screenshot(path=str(target), full_page=True)
        screenshots.append(str(target))
        return str(target)
    except Exception:
        return ""


def _impl__page_text_excerpt(page: Any, limit: int = 1200) -> str:
    try:
        text = page.evaluate("() => document.body ? (document.body.innerText || document.body.textContent || '') : ''")
    except Exception:
        try:
            text = page.locator("body").inner_text(timeout=1200)
        except Exception:
            return ""
    text = _normalize_text(text)
    return text[:limit]


def _impl__expected_origin(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _impl__step_has_business_assertion(step: Dict[str, Any]) -> bool:
    if not isinstance(step, dict):
        return False
    if step.get("action") in {"assert_url", "assert_visible", "assert_value", "text_assert"}:
        return True
    return bool(step.get("assertions") or step.get("success_condition"))


def _impl__case_has_business_assertion(steps: list[Dict[str, Any]]) -> bool:
    return any(_step_has_business_assertion(step) for step in steps if isinstance(step, dict))


def _impl__check_success_condition(page: Any, condition: Any, timeout_ms: int) -> list[str]:
    if not condition:
        return []
    conditions = condition if isinstance(condition, list) else [condition]
    failures: list[str] = []
    for item in conditions:
        if isinstance(item, str):
            item = {"text_contains": item}
        if not isinstance(item, dict):
            continue
        if item.get("url_contains"):
            expected = str(item.get("url_contains") or "")
            if expected not in str(getattr(page, "url", "")):
                failures.append(f"URL 未包含预期片段：{expected}")
        if item.get("url_exact"):
            expected = str(item.get("url_exact") or "").rstrip("/")
            if str(getattr(page, "url", "")).rstrip("/") != expected:
                failures.append(f"URL 未精确匹配：{expected}")
        if item.get("text_contains"):
            expected = str(item.get("text_contains") or "")
            if expected not in _page_text_excerpt(page, limit=8000):
                failures.append(f"页面文本未包含：{expected}")
        selector = item.get("selector_visible") or item.get("locator_visible")
        if selector:
            try:
                page.locator(str(selector)).first.wait_for(state="visible", timeout=timeout_ms)
            except Exception:
                failures.append(f"未看到成功元素：{selector}")
    return failures


def _impl__final_business_verification(page: Any, steps: list[Dict[str, Any]], timeout_seconds: int) -> tuple[bool, list[str], dict[str, Any]]:
    issues: list[str] = []
    assertion_count = sum(1 for step in steps if _step_has_business_assertion(step))
    if assertion_count == 0:
        issues.append("用例缺少业务断言：没有 assert_url/assert_visible/assert_value/text_assert/success_condition，不能判定为可信成功")
    timeout_ms = max(1000, min(timeout_seconds, 12) * 1000)
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        failures = _check_success_condition(page, step.get("success_condition") or step.get("assertions"), timeout_ms)
        issues.extend(f"第{index}步成功条件失败：{item}" for item in failures)
    evidence = {
        "business_assertion_count": assertion_count,
        "final_url": getattr(page, "url", ""),
        "final_text_excerpt": _page_text_excerpt(page),
    }
    return not issues, issues, evidence


def _wait_after_action(page: Any, action: str) -> None:
    _sync_compat_globals()
    return _impl__wait_after_action(page, action)


def _capture_evidence_screenshot(page: Any, prefix: str, screenshots: list[str]) -> str:
    _sync_compat_globals()
    return _impl__capture_evidence_screenshot(page, prefix, screenshots)


def _page_text_excerpt(page: Any, limit: int=1200) -> str:
    _sync_compat_globals()
    return _impl__page_text_excerpt(page, limit)


def _expected_origin(url: str) -> str:
    _sync_compat_globals()
    return _impl__expected_origin(url)


def _step_has_business_assertion(step: Dict[str, Any]) -> bool:
    _sync_compat_globals()
    return _impl__step_has_business_assertion(step)


def _case_has_business_assertion(steps: list[Dict[str, Any]]) -> bool:
    _sync_compat_globals()
    return _impl__case_has_business_assertion(steps)


def _check_success_condition(page: Any, condition: Any, timeout_ms: int) -> list[str]:
    _sync_compat_globals()
    return _impl__check_success_condition(page, condition, timeout_ms)


def _final_business_verification(page: Any, steps: list[Dict[str, Any]], timeout_seconds: int) -> tuple[bool, list[str], dict[str, Any]]:
    _sync_compat_globals()
    return _impl__final_business_verification(page, steps, timeout_seconds)
