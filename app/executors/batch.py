from __future__ import annotations

import sys

from .common import VAR_PATTERN


_COMPAT_NAMES = (
    'Any',
    'BUILTIN_VAR_NAMES',
    'Dict',
    'Iterable',
    'ThreadPoolExecutor',
    'Tuple',
    'UI_ACTION_LABELS',
    'UI_LOCATOR_REQUIRED',
    'UiAuthPreparationError',
    'UiCase',
    '_locator_candidates',
    '_looks_like_login_page',
    '_prepare_authenticated_page',
    '_validate_ui_steps_for_execution',
    'as_completed',
    'builtin_variables',
    'ensure_report_dirs',
    'execute_ui_case',
    'execute_ui_case_in_page',
    'execute_ui_case_with_deadline',
    'json',
    'launch_chromium_browser',
    'logger',
    'parse_json_value',
    'render_template',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.executors"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl_execute_ui_cases_batch(
    items: Iterable[Dict[str, Any]],
    on_case_start: Any | None = None,
    on_case_finish: Any | None = None,
    parallelism: int = 1,
    db_session: Any = None,
) -> list[Tuple[bool, str, str, str]]:
    ensure_report_dirs()
    batch_items = list(items)
    for item in batch_items:
        if item.get("functional_case_id"):
            execution_context = dict(item.get("execution_context") or {})
            execution_context["strip_login_steps"] = True
            item["execution_context"] = execution_context
    results: list[Tuple[bool, str, str, str]] = []
    worker_count = max(1, min(int(parallelism or 1), 3))
    has_scenario_chain = any(
        str((item.get("execution_context") or {}).get("execution_policy") or "").lower() == "scenario_chain"
        for item in batch_items
    )
    if worker_count == 1 and not has_scenario_chain and any(item.get("functional_case_id") for item in batch_items):
        for item in batch_items:
            if on_case_start:
                on_case_start(item)
            case = item["case"]
            execution_context = item.get("execution_context") or {}
            deadline = int(
                execution_context.get("case_timeout_seconds")
                or min(max((getattr(case, "timeout", None) or 30) + 15, 30), 60)
            )
            result = execute_ui_case_with_deadline(
                case,
                item.get("variables"),
                execution_context,
                deadline,
                db_session=db_session,
            )
            results.append(result)
            if on_case_finish:
                on_case_finish(item, result)
        return results
    if worker_count > 1:
        indexed_items = list(enumerate(batch_items))
        future_map = {}
        ordered_results: list[Tuple[bool, str, str, str] | None] = [None] * len(indexed_items)
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            for index, item in indexed_items:
                if on_case_start:
                    on_case_start(item)
                future_map[pool.submit(execute_ui_case, item["case"], item.get("variables"), item.get("execution_context"), None, db_session)] = (index, item)
            for future in as_completed(future_map):
                index, item = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    log_text = json.dumps({"error": str(exc), "error_category": "parallel_execution_failed"}, ensure_ascii=False)
                    result = (False, log_text, "", "")
                ordered_results[index] = result
                if on_case_finish:
                    on_case_finish(item, result)
        return [item for item in ordered_results if item is not None]

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        for item in batch_items:
            if on_case_start:
                on_case_start(item)
            result = execute_ui_case(item["case"], item.get("variables"), item.get("execution_context"), None, db_session)
            results.append(result)
            if on_case_finish:
                on_case_finish(item, result)
        return results

    browser = None
    pages: Dict[str, Any] = {}
    contexts: Dict[str, Any] = {}
    try:
        with sync_playwright() as p:
            browser = launch_chromium_browser(p, headless=True)
            for item in batch_items:
                if on_case_start:
                    on_case_start(item)
                execution_context = dict(item.get("execution_context") or {})
                case = item["case"]
                session_key = "guest"
                if execution_context.get("login_required"):
                    functional_case = item.get("functional_case")
                    session_key = str(execution_context.get("session_key") or f"auth:{getattr(functional_case, 'id', case.id)}")
                page = pages.get(session_key)
                if page is None:
                    context = browser.new_context()
                    page = context.new_page()
                    contexts[session_key] = context
                    pages[session_key] = page
                    if execution_context.get("login_required"):
                        execution_context["target_url"] = execution_context.get("target_url") or case.page_url or ""
                        auth_result = _prepare_authenticated_page(page, execution_context, item.get("variables") or {}, case.timeout or 30)
                        execution_context["login_trace"] = auth_result.get("trace") or []
                        execution_context["preauthenticated"] = True
                elif execution_context.get("login_required"):
                    if _looks_like_login_page(page, expected_url=(execution_context.get("login_config") or {}).get("login_url") or ""):
                        auth_result = _prepare_authenticated_page(page, execution_context, item.get("variables") or {}, case.timeout or 30)
                        execution_context["login_trace"] = auth_result.get("trace") or []
                    execution_context["preauthenticated"] = True
                if item.get("functional_case_id"):
                    execution_context["strip_login_steps"] = True
                item["execution_context"] = execution_context
                result = execute_ui_case_in_page(case, page, item.get("variables"), execution_context)
                results.append(result)
                if on_case_finish:
                    on_case_finish(item, result)
    except Exception as exc:
        if isinstance(exc, UiAuthPreparationError) or "登录前置失败" in str(exc):
            raise
        logger.warning("批量 UI 执行中途失败，已完成的 %d 个结果将保留，剩余用例逐一执行: %s", len(results), exc)
        processed_count = len(results)
        for item in batch_items[processed_count:]:
            if on_case_start:
                on_case_start(item)
            result = execute_ui_case(item["case"], item.get("variables"), item.get("execution_context"), None, db_session)
            results.append(result)
            if on_case_finish:
                on_case_finish(item, result)
    finally:
        for page in pages.values():
            try:
                page.close()
            except Exception:
                pass
        for context in contexts.values():
            try:
                context.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass
    return results


def _impl_preflight_ui_case(case: UiCase, runtime_vars: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ensure_report_dirs()
    variables = builtin_variables()
    if runtime_vars:
        variables.update(runtime_vars)
    steps = render_template(parse_json_value(case.steps, []), variables)
    page_url = render_template(case.page_url, variables)
    steps, issues = _validate_ui_steps_for_execution(steps)
    raw_text = json.dumps({"page_url": case.page_url, "steps": parse_json_value(case.steps, [])}, ensure_ascii=False)
    required_vars = sorted(set(VAR_PATTERN.findall(raw_text)) - BUILTIN_VAR_NAMES - {f"${key}" for key in BUILTIN_VAR_NAMES})
    missing_vars = [name for name in required_vars if name not in variables or str(variables.get(name, "")).startswith("{{")]
    locator_checks: list[Dict[str, Any]] = []
    auth_risk = False

    if missing_vars:
        issues.append({"severity": "error", "message": "缺少运行时变量：" + "、".join(missing_vars)})
    if any(item.get("severity") == "error" for item in issues):
        return {"status": "missing_variables" if missing_vars else "not_recommended", "issues": issues, "locator_checks": locator_checks, "missing_variables": missing_vars}

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {"status": "not_recommended", "issues": [{"severity": "error", "message": f"Playwright不可用：{exc}"}], "locator_checks": locator_checks}

    browser = None
    try:
        with sync_playwright() as p:
            browser = launch_chromium_browser(p, headless=True)
            page = browser.new_page()
            page.set_default_timeout(8000)
            first_goto = next((step.get("value") for step in steps if step.get("action") == "goto" and step.get("value")), page_url)
            if first_goto:
                page.goto(str(first_goto), wait_until="domcontentloaded", timeout=12000)
                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    page.wait_for_timeout(300)
            auth_risk = "login" in (page.url or "").lower() and "login" not in str(first_goto or "").lower()
            for index, step in enumerate(steps, start=1):
                if step.get("action") not in UI_LOCATOR_REQUIRED:
                    continue
                candidates = _locator_candidates(step)
                check = {"step": index, "name": step.get("name") or UI_ACTION_LABELS.get(step.get("action"), step.get("action")), "locator": step.get("locator"), "status": "failed", "matched_count": 0, "visible": False}
                for locator in candidates:
                    try:
                        count = page.locator(locator).count()
                        visible = count > 0 and page.locator(locator).first.is_visible(timeout=600)
                        if count:
                            check.update({"status": "ok" if visible else "not_visible", "used_locator": locator, "matched_count": count, "visible": visible})
                            break
                    except Exception as exc:
                        check["error"] = str(exc)
                if check["status"] != "ok":
                    issues.append({"severity": "warning", "step": index, "message": f"第{index}步定位器可能不可用：{step.get('locator') or '-'}"})
                locator_checks.append(check)
            browser.close()
            browser = None
    except Exception as exc:
        issues.append({"severity": "warning", "message": f"页面试跑检查未完成：{exc}"})
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass

    warning_count = sum(1 for item in issues if item.get("severity") == "warning")
    if auth_risk:
        status_value = "auth_risk"
    elif missing_vars:
        status_value = "missing_variables"
    elif warning_count:
        status_value = "locator_risk"
    else:
        status_value = "executable"
    return {
        "status": status_value,
        "issues": issues,
        "locator_checks": locator_checks,
        "missing_variables": missing_vars,
        "auth_risk": auth_risk,
        "summary": "可执行" if status_value == "executable" else "存在执行风险，请查看检查详情",
    }


def execute_ui_cases_batch(items: Iterable[Dict[str, Any]], on_case_start: Any | None=None, on_case_finish: Any | None=None, parallelism: int=1, db_session: Any=None) -> list[Tuple[bool, str, str, str]]:
    _sync_compat_globals()
    return _impl_execute_ui_cases_batch(items, on_case_start, on_case_finish, parallelism, db_session)


def preflight_ui_case(case: UiCase, runtime_vars: Dict[str, Any] | None=None) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl_preflight_ui_case(case, runtime_vars)
