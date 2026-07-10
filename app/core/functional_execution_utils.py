from __future__ import annotations

import sys
from functools import wraps





_COMPAT_NAMES = (
    "FUNCTIONAL_CASE_KIND_BUSINESS_AUTH",
    "FunctionalCase",
    "FunctionalExecuteRequest",
    "FunctionalRun",
    "QUALITY_AUTH_RISK",
    "QUALITY_LOCATOR_RISK",
    "QUALITY_MISSING_VARIABLES",
    "QUALITY_NEEDS_REVIEW",
    "QUALITY_NOT_RECOMMENDED",
    "QUALITY_UNCHECKED",
    "UiCase",
    "_strip_leading_login_steps",
    "can_execute_functional_case",
    "datetime",
    "execute_functional_case_for_run",
    "execute_ui_case",
    "functional_case_kind",
    "generate_ui_steps",
    "json",
    "latest_ai_config",
    "parse_json_value",
    "resolve_execution_account",
    "save_ui_record",
    "serialize",
    "to_json_text",
)


def _sync_compat_globals() -> None:
    module = sys.modules["app.core.utils"]
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(module, name)


def _compat_wrapper(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        _sync_compat_globals()
        return func(*args, **kwargs)

    return wrapped


def _impl_ui_steps_have_strong_assertion(steps: Any) -> bool:
    parsed = parse_json_value(steps, steps)
    if isinstance(parsed, str):
        parsed = parse_json_value(parsed, [])
    if not isinstance(parsed, list):
        return False
    strong_actions = {"assert_url", "assert_visible", "assert_value", "text_assert"}
    for step in parsed:
        if not isinstance(step, dict):
            continue
        if step.get("action") in strong_actions:
            return True
        if step.get("success_condition") or step.get("assertions"):
            return True
    return False


def _impl_save_generated_functional_ui_steps(
    db: Session,
    task: FunctionalTask,
    case: FunctionalCase,
    snapshot: PageSnapshot | None = None,
) -> Dict[str, Any]:
    generated = generate_ui_steps(case, task, snapshot, latest_ai_config(db))
    generated_steps = generated.items
    if functional_case_kind(case) == FUNCTIONAL_CASE_KIND_BUSINESS_AUTH:
        generated_steps, _removed_login_steps = _strip_leading_login_steps(generated_steps)
    steps_text = to_json_text(generated_steps, [])
    if case.ui_case_id:
        ui_case = db.get(UiCase, case.ui_case_id)
        if ui_case:
            ui_case.case_name = case.title
            ui_case.page_url = task.target_url
            ui_case.steps = steps_text
            ui_case.status = "draft"
        else:
            case.ui_case_id = None
    if not case.ui_case_id:
        ui_case = UiCase(
            project_id=task.project_id,
            case_name=case.title,
            page_url=task.target_url,
            steps=steps_text,
            timeout=30,
            status="draft",
            create_time=datetime.now(),
        )
        db.add(ui_case)
        db.flush()
        case.ui_case_id = ui_case.id
    case.automation_status = "draft"
    task.status = "ui_steps_generated"
    return {"source": generated.source, "warning": generated.warning, "case": serialize(case), "steps": generated_steps}


def _impl_can_execute_functional_case(
    functional_case: FunctionalCase,
    payload: FunctionalExecuteRequest | None = None,
) -> tuple[bool, str]:
    """
    执行前门禁检查。
    Returns (allowed, reason) — allowed=False 则拒绝执行。
    """
    if functional_case.automation_status != "approved":
        return False, f"用例状态为 {functional_case.automation_status}，仅 approved 可自动执行"
    if not functional_case.ui_case_id:
        return False, "尚未关联 UI 步骤，无法执行"
    quality = functional_case.quality_status or QUALITY_UNCHECKED
    trial_mode = bool(payload and (payload.force or payload.execution_mode == "trial"))
    if quality in (QUALITY_AUTH_RISK, QUALITY_MISSING_VARIABLES, QUALITY_NOT_RECOMMENDED):
        return False, f"预检未通过（{quality}），不允许自动执行"
    if quality in (QUALITY_LOCATOR_RISK, QUALITY_NEEDS_REVIEW) and not trial_mode:
        return False, f"预检未通过（{quality}），不允许自动执行"
    return True, ""


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
    return (
        {
            "functional_case_id": functional_case.id,
            "ui_case_id": ui_case.id,
            "record_id": record.id,
            "title": functional_case.title,
            "result": record.result,
            "screenshot": screenshot_path,
            "log": log_text,
        },
        1 if passed else 0,
        0 if passed else 1,
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


ui_steps_have_strong_assertion = _compat_wrapper(_impl_ui_steps_have_strong_assertion)
save_generated_functional_ui_steps = _compat_wrapper(_impl_save_generated_functional_ui_steps)
can_execute_functional_case = _compat_wrapper(_impl_can_execute_functional_case)
execute_functional_case_for_run = _compat_wrapper(_impl_execute_functional_case_for_run)
execute_functional_case_for_run_isolated = _compat_wrapper(_impl_execute_functional_case_for_run_isolated)
save_functional_run = _compat_wrapper(_impl_save_functional_run)
