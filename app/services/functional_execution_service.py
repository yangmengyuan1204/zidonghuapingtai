from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'BLOCKED_QUALITY_STATUSES',
    'Dict',
    'FunctionalCase',
    'FunctionalExecuteRequest',
    'FunctionalRun',
    'FunctionalTask',
    'QUALITY_AUTH_RISK',
    'QUALITY_EXECUTABLE',
    'QUALITY_LOCATOR_RISK',
    'QUALITY_MISSING_VARIABLES',
    'QUALITY_NEEDS_REVIEW',
    'QUALITY_UNCHECKED',
    'REVIEW_QUALITY_STATUSES',
    'Session',
    'UiCase',
    '_classify_functional_execution_result',
    '_execution_event',
    '_repair_issue_type',
    'can_execute_functional_case',
    'datetime',
    'execute_functional_case_for_run',
    'execute_ui_case',
    'execute_ui_cases_batch',
    'is_sensitive_account_key',
    'json',
    'parse_json_value',
    'quality_report_payload',
    'resolve_execution_account',
    'save_ui_record',
    'time',
)


def _sync_compat_globals() -> None:
    module = sys.modules["app.routers.functional_tasks"]
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(module, name)


def _impl_execute_functional_case_for_run(
    db: Session,
    functional_case: FunctionalCase,
    variables: Dict[str, Any],
    payload: FunctionalExecuteRequest | None = None,
) -> tuple[Dict[str, Any], int, int]:
    # ── 执行门禁 ──────────────────────────────────────
    allowed, reason = can_execute_functional_case(functional_case, payload)
    if not allowed:
        return (
            {
                "functional_case_id": functional_case.id,
                "title": functional_case.title,
                "result": "failed",
                "error": reason,
                "gate_blocked": True,
            },
            0,
            1,
        )
    # ──────────────────────────────────────────────────
    ui_case = db.get(UiCase, functional_case.ui_case_id) if functional_case.ui_case_id else None
    if not ui_case:
        return (
            {
                "functional_case_id": functional_case.id,
                "title": functional_case.title,
                "result": "failed",
                "error": "关联UI用例不存在",
            },
            0,
            1,
        )
    case_variables, execution_context = resolve_execution_account(
        db,
        payload,
        "functional_case",
        functional_case.id,
        ui_case.project_id,
        ui_case.page_url,
    )
    case_variables = {**variables, **case_variables}
    execution_context = dict(execution_context or {})
    execution_context["strip_login_steps"] = True
    try:
        passed, log_text, screenshot_path, report_path = execute_ui_case(ui_case, case_variables, execution_context, None, db)
    except Exception as exc:
        passed = False
        screenshot_path = ""
        report_path = ""
        log_text = json.dumps(
            {
                "case_name": ui_case.case_name,
                "page_url": ui_case.page_url,
                "error": str(exc),
                "finished_at": datetime.now(),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    record = save_ui_record(db, ui_case, passed, log_text, report_path, screenshot_path)
    result_status, result_reason = _classify_functional_execution_result(passed, log_text, functional_case.quality_status)
    if functional_case:
        functional_case.test_result = result_status
        if result_status == "needs_review":
            functional_case.quality_status = QUALITY_NEEDS_REVIEW
        elif result_status == "blocked" and functional_case.quality_status in (None, QUALITY_UNCHECKED):
            functional_case.quality_status = QUALITY_MISSING_VARIABLES
        db.commit()
    return (
        {
            "functional_case_id": functional_case.id,
            "ui_case_id": ui_case.id,
            "record_id": record.id,
            "title": functional_case.title,
            "result": result_status,
            "record_result": record.result,
            "result_reason": result_reason,
            "screenshot": screenshot_path,
            "log": log_text,
        },
        1 if result_status == "passed" else 0,
        1 if result_status == "failed" else 0,
    )


def _impl_execute_functional_case_for_run_isolated(
    functional_case_id: int,
    variables: Dict[str, Any],
    payload_data: Dict[str, Any] | None = None,
) -> tuple[Dict[str, Any], int, int]:
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        functional_case = db.get(FunctionalCase, functional_case_id)
        if not functional_case:
            return (
                {
                    "functional_case_id": functional_case_id,
                    "title": f"#{functional_case_id}",
                    "result": "failed",
                    "error": "功能用例不存在",
                },
                0,
                1,
            )
        payload = FunctionalExecuteRequest(**payload_data) if payload_data else None
        return execute_functional_case_for_run(db, functional_case, variables, payload)
    finally:
        db.close()


def _impl_save_functional_run(
    db: Session,
    task: FunctionalTask,
    variables: Dict[str, Any],
    records: list[Dict[str, Any]],
    passed_count: int,
    failed_count: int,
) -> FunctionalRun:
    result = "passed" if failed_count == 0 else "failed"
    log_payload = {
        "task_id": task.id,
        "task": task.iteration_name,
        "variables": {key: ("***" if "password" in str(key).lower() else value) for key, value in variables.items()},
        "records": records,
        "passed_count": passed_count,
        "failed_count": failed_count,
    }
    run = FunctionalRun(
        task_id=task.id,
        result=result,
        log=json.dumps(log_payload, ensure_ascii=False, indent=2, default=str),
        passed_count=passed_count,
        failed_count=failed_count,
        execute_time=datetime.now(),
    )
    task.status = result
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _impl__classify_functional_execution_result(passed: bool, log_text: str, quality_status: str | None) -> tuple[str, str]:
    if passed:
        return "passed", ""
    quality = quality_status or QUALITY_UNCHECKED
    if quality in BLOCKED_QUALITY_STATUSES:
        return "blocked", f"preflight:{quality}"
    if quality in REVIEW_QUALITY_STATUSES:
        return "needs_review", f"preflight:{quality}"

    log_data = parse_json_value(log_text, {})
    if isinstance(log_data, dict) and log_data:
        text = json.dumps(log_data, ensure_ascii=False, default=str).lower()
    else:
        text = str(log_text or "").lower()
    verification_status = log_data.get("verification_status") if isinstance(log_data, dict) else ""
    error_category = str(log_data.get("error_category") or "").lower() if isinstance(log_data, dict) else ""
    if error_category == "step_validation_failed":
        return "blocked", "step_invalid"
    if error_category == "case_timeout":
        return "blocked", "environment_timeout"
    if error_category in {"parallel_execution_failed", "system_error"}:
        return "failed", "system_error"
    business = log_data.get("business_verification") if isinstance(log_data, dict) else {}
    if isinstance(business, dict) and int(business.get("business_assertion_count") or 0) == 0:
        return "needs_review", "missing_business_assertion"
    if verification_status == "failed_verification" and "业务断言" in text:
        return "needs_review", "missing_business_assertion"

    blocked_markers = [
        "login_required",
        "#/login",
        "/login",
        "登录前置",
        "登录态",
        "缺少真实数据",
        "missing_variables",
        "缺少变量",
        "库存不足",
        "可用库存不足",
        "option_not_found",
        "数据不足",
        "前置不足",
        "not found order",
        "order_not_found",
    ]
    if any(marker.lower() in text for marker in blocked_markers):
        return "blocked", "blocked_prerequisite"
    return "failed", "assertion_or_page_failure"


def _impl__execution_event(event_type: str, **payload: Any) -> Dict[str, Any]:
    return {
        "type": event_type,
        "timestamp": datetime.now().isoformat(),
        **payload,
    }


def _impl__save_functional_runtime_variables(task: FunctionalTask, variables: Dict[str, Any] | None) -> Dict[str, Any]:
    safe_variables = {
        str(key): value
        for key, value in (variables or {}).items()
        if value not in ("", None) and not is_sensitive_account_key(key)
    }
    if not safe_variables:
        return {}
    payload = parse_json_value(task.context or "", None)
    if not isinstance(payload, dict):
        payload = {"notes": task.context or ""}
    runtime_variables = payload.get("runtime_variables") if isinstance(payload.get("runtime_variables"), dict) else {}
    runtime_variables.update(safe_variables)
    payload["runtime_variables"] = runtime_variables
    task.context = json.dumps(payload, ensure_ascii=False, default=str)
    return safe_variables


def _impl__functional_execution_payload(run: FunctionalRun) -> Dict[str, Any]:
    log_data = parse_json_value(run.log, {})
    if not isinstance(log_data, dict):
        log_data = {}
    return {
        "job_id": run.id,
        "status": run.result,
        "total": log_data.get("total", 0),
        "completed": log_data.get("completed", 0),
        "passed_count": run.passed_count,
        "failed_count": run.failed_count,
        "blocked_count": log_data.get("blocked_count", 0),
        "review_count": log_data.get("review_count", 0),
        "preflight": log_data.get("preflight", None),
        "current_case_title": log_data.get("current_case_title", ""),
        "active_case_id": log_data.get("active_case_id"),
        "active_step_index": log_data.get("active_step_index"),
        "active_step_name": log_data.get("active_step_name", ""),
        "elapsed_ms": log_data.get("elapsed_ms", 0),
        "events": log_data.get("events", []),
        "records": log_data.get("records", []),
        "task_name": log_data.get("task", ""),
        "error": log_data.get("error", None),
    }


def _impl__repair_issue_type(record: Dict[str, Any], ui_log: Dict[str, Any]) -> str:
    text = json.dumps({"record": record, "log": ui_log}, ensure_ascii=False, default=str).lower()
    if record.get("result") == "blocked" and ("auth" in text or "login" in text or "#/login" in text):
        return "auth"
    if "missing_variables" in text or "data_missing" in text or "缺" in text and "数据" in text:
        return "data"
    if any(marker in text for marker in ["healed", "locator", "strict mode violation", "timeout"]):
        return "locator"
    if "assert" in text or "断言" in text:
        return "assertion"
    if "environment" in text or "net::" in text or "5xx" in text:
        return "environment"
    return "test_design" if record.get("result") == "needs_review" else "app_bug"


def _impl__build_functional_repair_plan(run: FunctionalRun) -> Dict[str, Any]:
    run_log = parse_json_value(run.log, {})
    records = run_log.get("records") if isinstance(run_log.get("records"), list) else []
    repairs: list[Dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or record.get("result") == "passed":
            continue
        ui_log = parse_json_value(record.get("log"), {})
        if not isinstance(ui_log, dict):
            ui_log = {}
        step_logs = ui_log.get("step_logs") if isinstance(ui_log.get("step_logs"), list) else []
        issue_type = _repair_issue_type(record, ui_log)
        repair = {
            "record_id": record.get("record_id"),
            "functional_case_id": record.get("functional_case_id"),
            "ui_case_id": record.get("ui_case_id"),
            "case_title": record.get("title") or "",
            "issue_type": issue_type,
            "root_cause": ui_log.get("failure_reason") or ui_log.get("error") or record.get("result_reason") or "",
            "confidence": "high" if issue_type in {"auth", "data", "locator"} else "medium",
            "auto_fixable": False,
            "fix_type": "",
            "suggested_action": ui_log.get("suggestion") or "",
            "locator_updates": [],
        }
        locator_updates = []
        for step in step_logs:
            if isinstance(step, dict) and step.get("healed") and step.get("original_locator") and step.get("suggested_locator"):
                locator_updates.append(
                    {
                        "original_locator": step.get("original_locator"),
                        "suggested_locator": step.get("suggested_locator"),
                    }
                )
        if locator_updates:
            repair.update(
                {
                    "auto_fixable": True,
                    "fix_type": "locator",
                    "suggested_action": "应用已自愈成功的 locator，并复跑失败用例",
                    "locator_updates": locator_updates,
                }
            )
        elif issue_type == "data":
            repair["suggested_action"] = repair["suggested_action"] or "补齐缺失变量后重新预检并执行"
        elif issue_type == "auth":
            repair["suggested_action"] = repair["suggested_action"] or "绑定并验证测试账号后重新执行"
        repairs.append(repair)
    return {
        "run_id": run.id,
        "repair_items": repairs,
        "auto_fixable_count": sum(1 for item in repairs if item.get("auto_fixable")),
    }


def _impl__background_execute_functional(
    task_id: int,
    run_id: int,
    payload_data: dict,
    selected_bg_case_ids: list[int],
    variables: dict,
) -> None:
    from ..database import SessionLocal

    bg_db = None
    try:
        bg_db = SessionLocal()
        bg_task = bg_db.query(FunctionalTask).filter(FunctionalTask.id == task_id).first()
        bg_run = bg_db.query(FunctionalRun).filter(FunctionalRun.id == run_id).first()
        if not bg_task or not bg_run:
            return

        bg_cases_query = bg_db.query(FunctionalCase).filter(
            FunctionalCase.task_id == task_id,
            FunctionalCase.automation_status == "approved",
            FunctionalCase.ui_case_id.isnot(None),
        )
        if selected_bg_case_ids:
            bg_cases_query = bg_cases_query.filter(FunctionalCase.id.in_(selected_bg_case_ids))
        if payload_data.get("force"):
            bg_cases_query = bg_cases_query.filter(
                FunctionalCase.quality_status.in_(
                    [QUALITY_EXECUTABLE, QUALITY_UNCHECKED, QUALITY_NEEDS_REVIEW, QUALITY_LOCATOR_RISK]
                )
            )
        else:
            bg_cases_query = bg_cases_query.filter(FunctionalCase.quality_status == QUALITY_EXECUTABLE)
        bg_cases = bg_cases_query.order_by(FunctionalCase.id.asc()).all()

        gathered_records: list[Dict[str, Any]] = []
        total_passed = 0
        total_failed = 0
        total_blocked = 0
        total_review = 0
        _cached_vars = dict(variables)
        processed_case_ids: set[int] = set()
        batch_items: list[Dict[str, Any]] = []
        payload_obj = FunctionalExecuteRequest(**payload_data) if payload_data else None
        execution_policy = str(payload_data.get("execution_policy") or "isolated_per_case")
        parallelism = max(1, min(int(payload_data.get("parallelism") or 1), 3))
        if execution_policy == "scenario_chain":
            parallelism = 1
        started_ts = time.time()
        events: list[Dict[str, Any]] = [
            _execution_event("run_started", run_id=run_id, total=len(bg_cases), parallelism=parallelism, execution_policy=execution_policy)
        ]

        for fc in bg_cases:
            ui_case = bg_db.get(UiCase, fc.ui_case_id) if fc.ui_case_id else None
            if not ui_case:
                continue
            case_variables, execution_context = resolve_execution_account(
                bg_db,
                payload_obj,
                "functional_case",
                fc.id,
                ui_case.project_id,
                ui_case.page_url,
            )
            case_variables = {**_cached_vars, **case_variables}
            if execution_context.get("login_required"):
                profile_key = execution_context.get("account_profile_id") or "default"
                execution_context["session_key"] = f"functional-task:{task_id}:profile:{profile_key}"
                execution_context["target_url"] = execution_context.get("target_url") or bg_task.target_url or ui_case.page_url
            execution_context["execution_policy"] = execution_policy
            batch_items.append(
                {
                    "case": ui_case,
                    "functional_case": fc,
                    "functional_case_id": fc.id,
                    "variables": case_variables,
                    "execution_context": execution_context,
                }
            )

        def _write_run_progress(current_title: str, completed: int) -> None:
            bg_run.log = json.dumps({
                **json.loads(bg_run.log or "{}"),
                "records": gathered_records,
                "passed_count": total_passed,
                "failed_count": total_failed,
                "blocked_count": total_blocked,
                "review_count": total_review,
                "completed": completed,
                "current_case_title": current_title,
                "active_case_id": None,
                "active_step_index": None,
                "active_step_name": "",
                "elapsed_ms": int((time.time() - started_ts) * 1000),
                "events": events[-200:],
                "parallelism": parallelism,
                "execution_policy": execution_policy,
            }, ensure_ascii=False, default=str)
            bg_run.passed_count = total_passed
            bg_run.failed_count = total_failed
            bg_db.commit()

        def _on_case_start(item: Dict[str, Any]) -> None:
            fc = item.get("functional_case")
            title = getattr(fc, "title", "正在执行用例")
            events.append(_execution_event("case_started", functional_case_id=getattr(fc, "id", None), title=title))
            _write_run_progress(title, len(processed_case_ids))

        def _on_case_finish(item: Dict[str, Any], result_tuple: tuple[bool, str, str, str]) -> None:
            nonlocal total_passed, total_failed, total_blocked, total_review
            fc = bg_db.get(FunctionalCase, int(item.get("functional_case_id")))
            ui_case = item.get("case")
            passed, log_text, screenshot_path, report_path = result_tuple
            record = save_ui_record(bg_db, ui_case, passed, log_text, report_path, screenshot_path)
            quality_status = getattr(fc, "quality_status", QUALITY_UNCHECKED) if fc else QUALITY_UNCHECKED
            result_status, result_reason = _classify_functional_execution_result(passed, log_text, quality_status)
            log_data = parse_json_value(log_text, {})
            if not isinstance(log_data, dict):
                log_data = {}
            business_verification = log_data.get("business_verification") if isinstance(log_data.get("business_verification"), dict) else {}
            record_payload: Dict[str, Any] = {
                "functional_case_id": fc.id if fc else item.get("functional_case_id"),
                "ui_case_id": getattr(ui_case, "id", None),
                "record_id": record.id,
                "title": fc.title if fc else getattr(ui_case, "case_name", "未知用例"),
                "case_kind": (parse_json_value(getattr(fc, "quality_report", ""), {}) or {}).get("case_kind") if fc else "",
                "result": result_status,
                "record_result": record.result,
                "quality_status": quality_status,
                "result_reason": result_reason,
                "screenshot": screenshot_path,
                "log": log_text,
                "current_url": log_data.get("current_url")
                or business_verification.get("final_url", "")
                or log_data.get("page_url")
                or getattr(ui_case, "page_url", ""),
                "failed_step": log_data.get("failed_step"),
                "failed_step_detail": log_data.get("failed_step_detail"),
            }
            record_text = json.dumps(record_payload, ensure_ascii=False, default=str)
            auth_blocked = result_status == "blocked" and ("登录前置失败" in record_text or ("login_required" in record_text and "#/login" in record_text))
            if fc:
                if result_status == "passed":
                    fc.test_result = "passed"
                    total_passed += 1
                elif result_status == "blocked":
                    fc.test_result = "blocked"
                    if auth_blocked:
                        fc.quality_status = QUALITY_AUTH_RISK
                        fc.quality_report = json.dumps(
                            quality_report_payload(QUALITY_AUTH_RISK, "登录前置失败，未继续判定业务功能"),
                            ensure_ascii=False,
                            default=str,
                        )
                        record_payload["status"] = "auth_blocked"
                    total_blocked += 1
                elif result_status == "needs_review":
                    fc.test_result = "needs_review"
                    fc.quality_status = QUALITY_NEEDS_REVIEW
                    fc.quality_report = json.dumps(
                        quality_report_payload(QUALITY_NEEDS_REVIEW, "执行完成但结果可信度不足，需要人工确认", [result_reason]),
                        ensure_ascii=False,
                        default=str,
                    )
                    total_review += 1
                else:
                    fc.test_result = "failed"
                    fc.failure_count = (fc.failure_count or 0) + 1
                    total_failed += 1
                processed_case_ids.add(fc.id)
            gathered_records.append(record_payload)
            step_logs = log_data.get("step_logs") if isinstance(log_data.get("step_logs"), list) else []
            for step in step_logs[-20:]:
                if isinstance(step, dict):
                    events.append(
                        _execution_event(
                            "step_finished",
                            functional_case_id=record_payload.get("functional_case_id"),
                            step_index=step.get("index"),
                            step_name=step.get("name") or step.get("action") or "",
                            status=step.get("status") or "",
                        )
                    )
            events.append(
                _execution_event(
                    "case_finished",
                    functional_case_id=record_payload.get("functional_case_id"),
                    title=record_payload["title"],
                    result=result_status,
                )
            )
            _write_run_progress(
                "登录前置失败，后续用例已阻断" if auth_blocked else record_payload["title"],
                len(processed_case_ids),
            )

        try:
            execute_ui_cases_batch(batch_items, on_case_start=_on_case_start, on_case_finish=_on_case_finish, parallelism=parallelism, db_session=bg_db)
        except Exception as exc:
            if "登录前置失败" not in str(exc):
                raise
            for blocked_case in bg_cases:
                if blocked_case.id in processed_case_ids:
                    continue
                blocked_case.test_result = "blocked"
                blocked_case.quality_status = QUALITY_AUTH_RISK
                blocked_case.quality_report = json.dumps(
                    quality_report_payload(QUALITY_AUTH_RISK, str(exc)[:500]),
                    ensure_ascii=False,
                    default=str,
                )
                gathered_records.append(
                    {
                        "functional_case_id": blocked_case.id,
                        "title": blocked_case.title,
                        "result": "blocked",
                        "status": "auth_blocked",
                        "error": str(exc),
                    }
                )
                events.append(_execution_event("case_finished", functional_case_id=blocked_case.id, title=blocked_case.title, result="blocked"))
                processed_case_ids.add(blocked_case.id)
                total_blocked += 1
            _write_run_progress("登录前置失败，已停止后续用例", len(processed_case_ids))

        final_result = "failed" if total_failed else ("blocked" if total_blocked else ("needs_review" if total_review else "passed"))
        bg_run.result = final_result
        events.append(_execution_event("run_finished", run_id=run_id, status=final_result))
        bg_run.log = json.dumps({
            **json.loads(bg_run.log or "{}"),
            "current_case_title": "执行完毕",
            "status": final_result,
            "blocked_count": total_blocked,
            "review_count": total_review,
            "elapsed_ms": int((time.time() - started_ts) * 1000),
            "events": events[-200:],
        }, ensure_ascii=False, default=str)
        bg_task.status = final_result
        bg_db.commit()
    except Exception:
        import traceback
        if bg_db is not None:
            try:
                error_run = bg_db.query(FunctionalRun).filter(FunctionalRun.id == run_id).first()
                if error_run:
                    error_run.result = "error"
                    error_run.log = json.dumps({
                        **json.loads(error_run.log or "{}"),
                        "current_case_title": "执行异常",
                        "status": "error",
                        "error": traceback.format_exc(),
                    }, ensure_ascii=False, default=str)
                    bg_task.status = "error"
                    bg_db.commit()
            except Exception:
                pass
    finally:
        if bg_db is not None:
            bg_db.close()


def execute_functional_case_for_run(db: Session, functional_case: FunctionalCase, variables: Dict[str, Any], payload: FunctionalExecuteRequest | None=None) -> tuple[Dict[str, Any], int, int]:
    _sync_compat_globals()
    return _impl_execute_functional_case_for_run(db, functional_case, variables, payload)


def execute_functional_case_for_run_isolated(functional_case_id: int, variables: Dict[str, Any], payload_data: Dict[str, Any] | None=None) -> tuple[Dict[str, Any], int, int]:
    _sync_compat_globals()
    return _impl_execute_functional_case_for_run_isolated(functional_case_id, variables, payload_data)


def save_functional_run(db: Session, task: FunctionalTask, variables: Dict[str, Any], records: list[Dict[str, Any]], passed_count: int, failed_count: int) -> FunctionalRun:
    _sync_compat_globals()
    return _impl_save_functional_run(db, task, variables, records, passed_count, failed_count)


def _classify_functional_execution_result(passed: bool, log_text: str, quality_status: str | None) -> tuple[str, str]:
    _sync_compat_globals()
    return _impl__classify_functional_execution_result(passed, log_text, quality_status)


def _execution_event(event_type: str, **payload: Any) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__execution_event(event_type, **payload)


def _save_functional_runtime_variables(task: FunctionalTask, variables: Dict[str, Any] | None) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__save_functional_runtime_variables(task, variables)


def _functional_execution_payload(run: FunctionalRun) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__functional_execution_payload(run)


def _repair_issue_type(record: Dict[str, Any], ui_log: Dict[str, Any]) -> str:
    _sync_compat_globals()
    return _impl__repair_issue_type(record, ui_log)


def _build_functional_repair_plan(run: FunctionalRun) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__build_functional_repair_plan(run)


def _background_execute_functional(task_id: int, run_id: int, payload_data: dict, selected_bg_case_ids: list[int], variables: dict) -> None:
    _sync_compat_globals()
    return _impl__background_execute_functional(task_id, run_id, payload_data, selected_bg_case_ids, variables)
