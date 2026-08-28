from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'Callable',
    'Dict',
    'Env',
    'Path',
    'SCREENSHOT_DIR',
    'Tuple',
    'UiAuthPreparationError',
    'UiCase',
    'UiStepExecutionError',
    '_business_variables_from_text',
    '_expected_origin',
    '_final_business_verification',
    '_json_dump_log',
    '_mask_variables',
    '_merge_inferred_business_variables',
    '_page_text_excerpt',
    '_prepare_authenticated_page',
    '_quick_screenshot_check',
    '_run_ui_step',
    '_stabilize_runtime_steps',
    '_strip_leading_login_steps',
    '_url_looks_reasonable',
    '_validate_ui_steps_for_execution',
    '_wait_after_action',
    '_wait_page_stable',
    'builtin_variables',
    'datetime',
    'ensure_report_dirs',
    'execute_ui_case',
    'execute_ui_case_in_page',
    'json',
    'launch_chromium_browser',
    'logger',
    'merge_variables',
    'parse_json_value',
    'queue',
    'render_template',
    'threading',
    'uuid4',
    'write_allure_result',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.executors"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)
    from .auth import _strip_leading_login_steps
    globals()["_strip_leading_login_steps"] = _strip_leading_login_steps

def _active_page(page: Any) -> Any:
    try:
        pages = getattr(getattr(page, "context", None), "pages", [])
        for p in reversed(pages):
            if hasattr(p, "is_closed") and not p.is_closed():
                try:
                    if p.url == "about:blank" or not p.url:
                        p.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                return p
    except Exception:
        pass
    return page


def _impl_execute_ui_case_in_page(
    case: UiCase,
    page: Any,
    runtime_vars: Dict[str, Any] | None = None,
    execution_context: Dict[str, Any] | None = None,
    env: Env | None = None,
    db_session: Any = None,
    progress_callback: Callable[[Dict[str, Any]], None] | None = None,
) -> Tuple[bool, str, str, str]:
    ensure_report_dirs()
    timeout = case.timeout or 30
    if env:
        variables = merge_variables(env, runtime_vars)
    else:
        variables = builtin_variables()
        if runtime_vars:
            variables.update(runtime_vars)
    raw_steps = parse_json_value(case.steps, [])
    page_url = render_template(case.page_url, variables)
    steps: list[Dict[str, Any]] = []
    validation_issues: list[Dict[str, Any]] = []
    execution_context = dict(execution_context or {})
    removed_login_steps: list[Dict[str, Any]] = []
    login_trace: list[str] = list(execution_context.get("login_trace") or [])
    # 读取重试配置
    retry_count = execution_context.get("retry_count", 2)
    retry_interval_ms = execution_context.get("retry_interval_ms", 1000)

    log_parts: Dict[str, Any] = {
        "case_name": case.case_name,
        "page_url": page_url,
        "steps": steps,
        "timeout": timeout,
        "variables": _mask_variables(variables),
        "validation_issues": validation_issues,
        "step_logs": [],
        "started_at": datetime.now(),
        "retry_config": {"retry_count": retry_count, "retry_interval_ms": retry_interval_ms},
        "auth_context": {
            "login_required": bool(execution_context.get("login_required")),
            "account_profile_id": execution_context.get("account_profile_id"),
            "login_url": (execution_context.get("login_config") or {}).get("login_url") or "",
            "removed_login_step_count": len(removed_login_steps),
        },
    }
    if login_trace:
        log_parts["auth_context"]["login_trace"] = login_trace
    screenshots: list[str] = []
    extracted_vars: Dict[str, Any] = {}
    current_step_index = 0
    current_step: Dict[str, Any] | None = None
    failed_step_detail: Dict[str, Any] | None = None

    def emit_progress(event: str, **data: Any) -> None:
        if not progress_callback:
            return
        try:
            progress_callback({"event": event, **data})
        except Exception:
            logger.debug("UI progress callback failed", exc_info=True)

    emit_progress(
        "started",
        status="running",
        case_name=case.case_name,
        page_url=page_url,
        total_steps=len(raw_steps) if isinstance(raw_steps, list) else 0,
    )

    try:
        page.set_default_timeout(timeout * 1000)
        if execution_context.get("login_required") and not execution_context.get("preauthenticated"):
            try:
                auth_result = _prepare_authenticated_page(page, execution_context, variables, timeout)
            except UiAuthPreparationError as exc:
                login_trace = list(getattr(exc, 'trace', []) or [])
                log_parts["auth_context"]["login_trace"] = login_trace
                raise
            login_trace = auth_result.get("trace") or []
            log_parts["auth_context"]["login_trace"] = login_trace
            execution_context["preauthenticated"] = True
        if case.page_url:
            page.goto(page_url, wait_until="domcontentloaded")
            _wait_page_stable(page)
        inferred_variables = _business_variables_from_text(_page_text_excerpt(page, limit=12000))
        applied_variables = _merge_inferred_business_variables(variables, inferred_variables)
        steps = render_template(raw_steps, variables)
        for s in steps:
            if isinstance(s, dict) and s.get("default_value"):
                val = str(s.get("value") or "")
                if not val or val.startswith("{{"):
                    s["value"] = s["default_value"]
        if execution_context.get("login_required") or execution_context.get("strip_login_steps") or execution_context.get("preauthenticated"):
            steps, removed_login_steps = _strip_leading_login_steps(steps)
        steps, runtime_replacements = _stabilize_runtime_steps(steps, variables)
        steps, validation_issues = _validate_ui_steps_for_execution(steps)
        log_parts.update(
            {
                "steps": steps,
                "variables": _mask_variables(variables),
                "validation_issues": validation_issues,
                "runtime_seed_variables": applied_variables,
                "runtime_step_replacements": runtime_replacements,
                "extracted_vars": extracted_vars,
            }
        )
        emit_progress("prepared", status="running", steps=steps, validation_issues=validation_issues)
        log_parts["auth_context"]["removed_login_step_count"] = len(removed_login_steps)
        if any(item.get("severity") == "error" for item in validation_issues):
            log_parts.update(
                {
                    "error": "UI steps validation failed: " + "; ".join(item.get("message", "") for item in validation_issues),
                    "error_category": "step_validation_failed",
                    "finished_at": datetime.now(),
                }
            )
            emit_progress("finished", status="failed", error=log_parts["error"], extracted_vars=extracted_vars)
            log_text = _json_dump_log(log_parts)
            report_path = write_allure_result(case.case_name, "ui", False, log_text)
            return False, log_text, "", report_path
        for index, step in enumerate(steps, start=1):
            current_step_index = index
            current_step = step if isinstance(step, dict) else {"raw": step}
            curr_page = _active_page(page)
            emit_progress("step_start", status="running", index=index, step=current_step)
            # 智能等待：操作前等待页面稳定
            action = (current_step or {}).get("action", "")
            if action in ("click", "input", "select", "check", "uncheck"):
                _wait_page_stable(curr_page, timeout=1500)

            try:
                step_detail = _run_ui_step(curr_page, current_step, screenshots, timeout, case_id=getattr(case, 'id', 0) or 0, db=db_session)
                step_detail["index"] = index
                log_parts["step_logs"].append(step_detail)
                if isinstance(step_detail.get("extracted"), dict):
                    extracted_vars.update(step_detail["extracted"])
                    variables.update(step_detail["extracted"])
                    log_parts["extracted_vars"] = extracted_vars
                emit_progress("step_finish", status=step_detail.get("status", "passed"), index=index, step=current_step, detail=step_detail, extracted_vars=extracted_vars)
                # 智能等待：操作后等待页面响应
                _wait_after_action(curr_page, action)
            except UiStepExecutionError as exc:
                # 失败自动重试
                if retry_count > 0 and action not in ("text_assert", "assert_url", "assert_value", "assert_visible"):
                    retried = False
                    for attempt in range(retry_count):
                        retry_page = _active_page(page)
                        retry_page.wait_for_timeout(retry_interval_ms)
                        _wait_page_stable(retry_page)
                        try:
                            step_detail = _run_ui_step(retry_page, current_step, screenshots, timeout, case_id=getattr(case, 'id', 0) or 0, db=db_session)
                            step_detail["index"] = index
                            step_detail["retry_attempt"] = attempt + 1
                            log_parts["step_logs"].append(step_detail)
                            if isinstance(step_detail.get("extracted"), dict):
                                extracted_vars.update(step_detail["extracted"])
                                variables.update(step_detail["extracted"])
                                log_parts["extracted_vars"] = extracted_vars
                            # 重试成功后截一张确认图，作为"步骤恢复"的证据
                            confirm_shot = SCREENSHOT_DIR / f"retry-confirm-{uuid4()}.png"
                            try:
                                retry_page.screenshot(path=str(confirm_shot), full_page=True)
                                step_detail["retry_confirmation_screenshot"] = str(confirm_shot)
                                screenshots.append(str(confirm_shot))
                            except Exception:
                                pass
                            emit_progress("step_finish", status=step_detail.get("status", "passed"), index=index, step=current_step, detail=step_detail, extracted_vars=extracted_vars)
                            retried = True
                            break
                        except UiStepExecutionError:
                            continue
                    if retried:
                        continue
                failed_step_detail = exc.detail
                failed_step_detail["index"] = index
                log_parts["step_logs"].append(failed_step_detail)
                emit_progress("step_finish", status="failed", index=index, step=current_step, detail=failed_step_detail, extracted_vars=extracted_vars)
                raise
        # 最终验证：强制截图 + URL + 截图质量检查
        final_page = _active_page(page)
        final_screenshot = SCREENSHOT_DIR / f"{uuid4()}.png"
        try:
            final_page.screenshot(path=str(final_screenshot), full_page=True)
            screenshots.append(str(final_screenshot))
        except Exception as exc:
            final_screenshot = Path(screenshots[-1]) if screenshots else None

        # 三级验证
        final_url = getattr(final_page, "url", "")
        screenshot_check = _quick_screenshot_check(str(final_screenshot)) if final_screenshot else {"ok": False, "reason": "无法获取截图"}
        url_ok = _url_looks_reasonable(final_url, _expected_origin(str(case.page_url or "")))
        business_ok, business_issues, business_evidence = _final_business_verification(final_page, steps, timeout)

        verification_issues = []
        if not url_ok:
            verification_issues.append(f"最终 URL 异常：{final_url}")
        if not screenshot_check["ok"]:
            verification_issues.append(f"截图验证失败：{screenshot_check['reason']}")
        if not business_ok:
            verification_issues.extend(business_issues)

        if verification_issues:
            # 三级验证未通过 → 标记为 failed
            log_parts.update({
                "finished_at": datetime.now(),
                "verification_issues": verification_issues,
                "verification_status": "failed_verification",
                "business_verification": business_evidence,
                "verification_screenshot": str(final_screenshot) if final_screenshot else "",
                "warning": "所有步骤执行通过，但最终验证未通过：" + "; ".join(verification_issues),
            })
            log_parts["extracted_vars"] = extracted_vars
            emit_progress("finished", status="failed", screenshot=str(final_screenshot) if final_screenshot else "", verification_issues=verification_issues, extracted_vars=extracted_vars)
            log_text = _json_dump_log(log_parts)
            report_path = write_allure_result(case.case_name, "ui", False, log_text, str(final_screenshot) if final_screenshot else "")
            return False, log_text, str(final_screenshot) if final_screenshot else "", report_path

        log_parts.update({
            "finished_at": datetime.now(),
            "verification": {"screenshot_ok": True, "url_ok": True, "business_ok": True},
            "verification_status": "trusted_passed",
            "business_verification": business_evidence,
            "verification_screenshot": str(final_screenshot) if final_screenshot else "",
        })
        log_parts["extracted_vars"] = extracted_vars
        emit_progress("finished", status="passed", screenshot=str(final_screenshot) if final_screenshot else "", extracted_vars=extracted_vars)
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "ui", True, log_text, str(final_screenshot) if final_screenshot else screenshots[-1])
        return True, log_text, str(final_screenshot) if final_screenshot else screenshots[-1], report_path
    except Exception as exc:
        screenshot = ""
        try:
            screenshot_path = SCREENSHOT_DIR / f"{uuid4()}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)
            screenshot = str(screenshot_path)
        except Exception:
            screenshot = ""
        log_parts.update(
            {
                "error": str(exc),
                "error_category": failed_step_detail.get("category") if failed_step_detail else None,
                "failure_reason": failed_step_detail.get("reason") if failed_step_detail else None,
                "suggestion": failed_step_detail.get("suggestion") if failed_step_detail else None,
                "failed_step_index": current_step_index or None,
                "failed_step": current_step,
                "failed_step_detail": failed_step_detail,
                "current_url": getattr(page, "url", "") if page else "",
                "screenshot": screenshot,
                "auth_context": {**log_parts.get("auth_context", {}), "login_trace": login_trace},
                "finished_at": datetime.now(),
                "extracted_vars": extracted_vars,
            }
        )
        emit_progress("finished", status="failed", error=str(exc), screenshot=screenshot, failed_step_index=current_step_index or None, failed_step_detail=failed_step_detail, extracted_vars=extracted_vars)
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "ui", False, log_text, screenshot)
        return False, log_text, screenshot, report_path


def _impl_execute_ui_case(
    case: UiCase,
    runtime_vars: Dict[str, Any] | None = None,
    execution_context: Dict[str, Any] | None = None,
    env: Env | None = None,
    db_session: Any = None,
    progress_callback: Callable[[Dict[str, Any]], None] | None = None,
) -> Tuple[bool, str, str, str]:
    ensure_report_dirs()
    timeout = case.timeout or 30
    execution_context = dict(execution_context or {})
    if env:
        variables = merge_variables(env, runtime_vars)
    else:
        variables = builtin_variables()
        if runtime_vars:
            variables.update(runtime_vars)
    steps = render_template(parse_json_value(case.steps, []), variables)
    for s in steps:
        if isinstance(s, dict) and s.get("default_value"):
            val = str(s.get("value") or "")
            if not val or val.startswith("{{"):
                s["value"] = s["default_value"]
    if execution_context.get("login_required") or execution_context.get("strip_login_steps") or execution_context.get("preauthenticated"):
        steps, removed_login_steps = _strip_leading_login_steps(steps)
    steps, validation_issues = _validate_ui_steps_for_execution(steps)

    log_parts: Dict[str, Any] = {
        "case_name": case.case_name,
        "page_url": render_template(case.page_url, variables),
        "steps": steps,
        "timeout": timeout,
        "variables": _mask_variables(variables),
        "validation_issues": validation_issues,
        "step_logs": [],
        "started_at": datetime.now(),
    }
    def emit_progress(event: str, **data: Any) -> None:
        if not progress_callback:
            return
        try:
            progress_callback({"event": event, **data})
        except Exception:
            logger.debug("UI progress callback failed", exc_info=True)

    if any(item.get("severity") == "error" for item in validation_issues):
        log_parts.update(
            {
                "error": "UI步骤校验失败：" + "；".join(item.get("message", "") for item in validation_issues),
                "error_category": "步骤结构错误",
                "finished_at": datetime.now(),
            }
        )
        emit_progress("finished", status="failed", error=log_parts["error"])
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "ui", False, log_text)
        return False, log_text, "", report_path

    screenshots: list[str] = []
    current_step_index = 0
    current_step: Dict[str, Any] | None = None
    failed_step_detail: Dict[str, Any] | None = None

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        log_parts.update(
            {
                "error": f"Playwright 不可用：{exc}",
                "hint": "请先执行：python -m playwright install",
                "finished_at": datetime.now(),
            }
        )
        emit_progress("finished", status="failed", error=log_parts["error"])
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "ui", False, log_text)
        return False, log_text, "", report_path

    browser = None
    page = None
    try:
        with sync_playwright() as p:
            headed = bool(execution_context.get("headed") or execution_context.get("visual_browser"))
            browser = launch_chromium_browser(p, headless=not headed)
            context_options = {"ignore_https_errors": True}
            storage_state = execution_context.get("storage_state")
            if isinstance(storage_state, dict) and isinstance(storage_state.get("cookies"), list):
                context_options["storage_state"] = storage_state
            context = browser.new_context(**context_options)
            page = context.new_page()
            try:
                passed, log_text, screenshot_path, report_path = execute_ui_case_in_page(case, page, runtime_vars, execution_context, db_session=db_session, progress_callback=progress_callback)
            except Exception as inner_exc:
                # 在 with 块内捕获异常，此时 browser/page 仍存活
                screenshot = ""
                if page:
                    try:
                        screenshot_path = SCREENSHOT_DIR / f"{uuid4()}.png"
                        page.screenshot(path=str(screenshot_path), full_page=True)
                        screenshot = str(screenshot_path)
                    except Exception:
                        screenshot = ""
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass
                    browser = None
                log_parts.update(
                    {
                        "error": str(inner_exc),
                        "error_category": failed_step_detail.get("category") if failed_step_detail else None,
                        "failure_reason": failed_step_detail.get("reason") if failed_step_detail else None,
                        "suggestion": failed_step_detail.get("suggestion") if failed_step_detail else None,
                        "failed_step_index": current_step_index or None,
                        "failed_step": current_step,
                        "failed_step_detail": failed_step_detail,
                        "current_url": getattr(page, "url", "") if page else "",
                        "screenshot": screenshot,
                        "finished_at": datetime.now(),
                    }
                )
                emit_progress("finished", status="failed", error=str(inner_exc), screenshot=screenshot)
                log_text = _json_dump_log(log_parts)
                report_path = write_allure_result(case.case_name, "ui", False, log_text, screenshot)
                return False, log_text, screenshot, report_path
            try:
                browser.close()
            except Exception:
                pass
            browser = None
            # 执行成功且发生过自愈时，更新历史 success_count
            if passed and db_session:
                try:
                    from .services.locator_heal import update_heal_history_on_success
                    # 从 log_text 中解析 healed 信息
                    import json as _json
                    log_data = _json.loads(log_text) if log_text else {}
                    for step_log in (log_data.get("step_logs") or []):
                        if step_log.get("healed") and step_log.get("original_locator") and step_log.get("healed_locator"):
                            update_heal_history_on_success(db_session, step_log["original_locator"], step_log["healed_locator"])
                except Exception:
                    pass
            return passed, log_text, screenshot_path, report_path
    except Exception as exc:
        # 这里的异常只可能来自 sync_playwright() 或 launch 阶段（在 with 块外）
        screenshot = ""
        if page:
            try:
                screenshot_path = SCREENSHOT_DIR / f"{uuid4()}.png"
                page.screenshot(path=str(screenshot_path), full_page=True)
                screenshot = str(screenshot_path)
            except Exception:
                screenshot = ""
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        log_parts.update(
            {
                "error": str(exc),
                "error_category": failed_step_detail.get("category") if failed_step_detail else None,
                "failure_reason": failed_step_detail.get("reason") if failed_step_detail else None,
                "suggestion": failed_step_detail.get("suggestion") if failed_step_detail else None,
                "failed_step_index": current_step_index or None,
                "failed_step": current_step,
                "failed_step_detail": failed_step_detail,
                "current_url": getattr(page, "url", "") if page else "",
                "screenshot": screenshot,
                "finished_at": datetime.now(),
            }
        )
        emit_progress("finished", status="failed", error=str(exc), screenshot=screenshot)
        log_text = _json_dump_log(log_parts)
        report_path = write_allure_result(case.case_name, "ui", False, log_text, screenshot)
        return False, log_text, screenshot, report_path


def _impl_execute_ui_case_with_deadline(
    case: UiCase,
    runtime_vars: Dict[str, Any] | None,
    execution_context: Dict[str, Any] | None,
    deadline_seconds: int,
    db_session: Any = None,
) -> Tuple[bool, str, str, str]:
    result_queue: queue.Queue[Tuple[bool, str, str, str] | BaseException] = queue.Queue(maxsize=1)

    def _runner() -> None:
        try:
            result_queue.put(execute_ui_case(case, runtime_vars, execution_context, None, db_session))
        except BaseException as exc:
            result_queue.put(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(max(1, deadline_seconds))
    if thread.is_alive():
        log_text = json.dumps(
            {
                "case_name": case.case_name,
                "page_url": case.page_url,
                "current_url": case.page_url,
                "error": f"功能用例执行超过 {deadline_seconds} 秒仍未结束，已按超时终止本轮等待",
                "error_category": "case_timeout",
                "environment_reason": "case_execution_timeout",
                "failed_step": {"action": "case_timeout", "timeout_seconds": deadline_seconds},
                "suggestion": "缩短或拆分该用例步骤，检查页面是否有长时间加载、弹窗遮挡或定位器一直等待",
                "timeout_seconds": deadline_seconds,
                "finished_at": datetime.now(),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        report_path = write_allure_result(case.case_name, "ui", False, log_text)
        return False, log_text, "", report_path
    if result_queue.empty():
        log_text = json.dumps(
            {
                "case_name": case.case_name,
                "page_url": case.page_url,
                "current_url": case.page_url,
                "error": "功能用例执行线程结束但没有返回结果",
                "error_category": "system_error",
                "failed_step": {"action": "system_error"},
                "finished_at": datetime.now(),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        report_path = write_allure_result(case.case_name, "ui", False, log_text)
        return False, log_text, "", report_path
    result = result_queue.get()
    if isinstance(result, BaseException):
        log_text = json.dumps(
            {
                "case_name": case.case_name,
                "page_url": case.page_url,
                "error": str(result),
                "error_category": "system_error",
                "finished_at": datetime.now(),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        report_path = write_allure_result(case.case_name, "ui", False, log_text)
        return False, log_text, "", report_path
    return result


def execute_ui_case_in_page(case: UiCase, page: Any, runtime_vars: Dict[str, Any] | None=None, execution_context: Dict[str, Any] | None=None, env: Env | None=None, db_session: Any=None, progress_callback: Callable[[Dict[str, Any]], None] | None=None) -> Tuple[bool, str, str, str]:
    _sync_compat_globals()
    return _impl_execute_ui_case_in_page(case, page, runtime_vars, execution_context, env, db_session, progress_callback)


def execute_ui_case(case: UiCase, runtime_vars: Dict[str, Any] | None=None, execution_context: Dict[str, Any] | None=None, env: Env | None=None, db_session: Any=None, progress_callback: Callable[[Dict[str, Any]], None] | None=None) -> Tuple[bool, str, str, str]:
    _sync_compat_globals()
    return _impl_execute_ui_case(case, runtime_vars, execution_context, env, db_session, progress_callback)


def execute_ui_case_with_deadline(case: UiCase, runtime_vars: Dict[str, Any] | None, execution_context: Dict[str, Any] | None, deadline_seconds: int, db_session: Any=None) -> Tuple[bool, str, str, str]:
    _sync_compat_globals()
    return _impl_execute_ui_case_with_deadline(case, runtime_vars, execution_context, deadline_seconds, db_session)
