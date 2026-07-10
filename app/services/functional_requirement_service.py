from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'Dict',
    'FunctionalCase',
    'FunctionalExecuteRequest',
    'FunctionalRequirementNote',
    'FunctionalScanRequest',
    'FunctionalScreenshot',
    'FunctionalTask',
    'PageSnapshot',
    'QUALITY_AUTH_RISK',
    'QUALITY_LOCATOR_RISK',
    'QUALITY_MISSING_VARIABLES',
    'QUALITY_NEEDS_REVIEW',
    'QUALITY_NOT_RECOMMENDED',
    'QUALITY_UNCHECKED',
    'Session',
    'UiCase',
    '_assert_forward_status',
    '_runtime_func',
    '_strip_leading_login_steps',
    'datetime',
    'functional_case_auto_trusted',
    'functional_case_kind',
    'functional_task_detail',
    'generate_functional_cases',
    'generate_ui_steps',
    'get_or_404',
    'latest_ai_config',
    'parse_json_value',
    'preflight_functional_package',
    'read_axure_text',
    'safe_commit',
    'scan_page_dom',
    'schema_data',
    'serialize',
    'threading',
    'to_json_text',
    'ui_steps_have_strong_assertion',
)


def _sync_compat_globals() -> None:
    module = sys.modules["app.routers.functional_tasks"]
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(module, name)


def _impl__prepare_requirement_package(
    db: Session,
    task_id: int,
    payload: FunctionalScanRequest | None,
    demo_mode: bool = False,
) -> Dict[str, Any]:
    """
    核心准备逻辑。
    demo_mode=True: 原 quick-start 行为，含自动确认
    demo_mode=False: 生成到 UI 步骤后自动执行预检，不确认，返回需要人工处理的问题
    """
    task = get_or_404(db, FunctionalTask, task_id)
    steps_status = {}

    # ─── 步骤 1：扫描页面（带超时保护）─────────────────
    try:
        auth_config = schema_data(payload.auth, exclude_unset=True) if payload and payload.auth else None
        from urllib.parse import urlparse
        target_host = urlparse(task.target_url.lower()).hostname or ""
        skip_scan = any(target_host == domain or target_host.endswith("." + domain) for domain in ["example.com", "test.com", "localhost", "127.0.0.1"])
        if skip_scan:
            steps_status["scan"] = {"ok": False, "error": "目标URL不可达，跳过扫描", "skipped": True}
        else:
            scanned_holder = {}
            def do_scan():
                scanned_holder["result"] = _runtime_func("scan_page_dom", scan_page_dom)(task.target_url, timeout=15, auth=auth_config)
            t = threading.Thread(target=do_scan, daemon=True)
            t.start()
            t.join(timeout=25)
            if t.is_alive():
                steps_status["scan"] = {"ok": False, "error": "扫描超时（25s），已跳过"}
            else:
                scanned = scanned_holder.get("result")
                if scanned:
                    snapshot = PageSnapshot(
                        task_id=task.id,
                        page_url=task.target_url,
                        dom_summary=scanned["dom_summary"],
                        screenshot_path=scanned["screenshot_path"],
                        scan_time=datetime.now(),
                    )
                    # 状态检查放在 flush 之前，避免回滚丢失数据
                    _assert_forward_status(task, "scanned")
                    task.status = "scanned"
                    db.add(snapshot)
                    db.flush()
                    steps_status["scan"] = {"ok": True, "snapshot_id": snapshot.id}
                    safe_commit(db)
    except Exception as exc:
        db.rollback()
        db.expire_all()
        steps_status["scan"] = {"ok": False, "error": str(exc)[:300]}

    # ─── 步骤 2：生成测试用例 ─────────────────────────
    try:
        task = get_or_404(db, FunctionalTask, task_id)
        axure_text = read_axure_text(task.axure_path)
        latest_snapshot = db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).first()
        screenshots = db.query(FunctionalScreenshot).filter(FunctionalScreenshot.task_id == task.id).order_by(FunctionalScreenshot.id.asc()).all()
        notes = db.query(FunctionalRequirementNote).filter(FunctionalRequirementNote.task_id == task.id).order_by(FunctionalRequirementNote.id.asc()).all()
        generated = generate_functional_cases(task, axure_text, latest_snapshot, latest_ai_config(db), screenshots, notes)

        # 状态检查必须在 DB 修改之前，确保回滚不会丢失数据
        _assert_forward_status(task, "cases_generated")
        task.status = "cases_generated"

        for old_case in db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id, FunctionalCase.automation_status != "approved").all():
            db.delete(old_case)
        db.flush()

        for item in generated.items:
            db.add(FunctionalCase(
                task_id=task.id,
                title=item["title"],
                precondition=item.get("precondition", ""),
                steps=item.get("steps", ""),
                expected=item.get("expected", ""),
                category=item.get("category", "主流程"),
                priority=item.get("priority", "P1"),
                automation_status="draft",
                ui_case_id=None,
                create_time=datetime.now(),
            ))
        db.flush()
        steps_status["generate_cases"] = {"ok": True, "count": len(generated.items), "source": generated.source}
        db.commit()
    except Exception as exc:
        db.rollback()
        db.expire_all()
        steps_status["generate_cases"] = {"ok": False, "error": str(exc)[:300]}

    # ─── 步骤 3：生成 UI 步骤 ─────────────────────────
    task = get_or_404(db, FunctionalTask, task_id)
    cases = db.query(FunctionalCase).filter(
        FunctionalCase.task_id == task.id,
        FunctionalCase.automation_status.in_(["draft", "ui_steps_generated"]),
    ).order_by(FunctionalCase.id.asc()).all()

    ui_generated_count = 0
    ui_failed_count = 0
    trusted_auto_count = 0
    latest_snapshot = db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).first()

    # 状态检查必须在 DB 修改之前
    if demo_mode:
        _assert_forward_status(task, "approved")
    elif cases:
        _assert_forward_status(task, "ui_steps_generated")

    for fc in cases:
        try:
            generated_ui = generate_ui_steps(fc, task, latest_snapshot, latest_ai_config(db))
            generated_steps = generated_ui.items
            if functional_case_kind(fc) == "business_authenticated":
                generated_steps, _removed_login_steps = _strip_leading_login_steps(generated_steps)
            steps_text = to_json_text(generated_steps, [])
            if fc.ui_case_id:
                ui_case = db.get(UiCase, fc.ui_case_id)
                if ui_case:
                    ui_case.case_name = fc.title
                    ui_case.page_url = task.target_url
                    ui_case.steps = steps_text
                else:
                    fc.ui_case_id = None
            if not fc.ui_case_id:
                ui_case = UiCase(
                    project_id=task.project_id,
                    case_name=fc.title,
                    page_url=task.target_url,
                    steps=steps_text,
                    timeout=30,
                    status="active",
                    create_time=datetime.now(),
                )
                db.add(ui_case)
                db.flush()
                fc.ui_case_id = ui_case.id
            # demo_mode=True 时才自动确认；否则保持 ui_steps_generated 等待人工确认
            auto_trusted = (
                ui_steps_have_strong_assertion(generated_steps)
                and functional_case_auto_trusted(fc)
                and trusted_auto_count < 12
            )
            if (demo_mode and ui_steps_have_strong_assertion(generated_steps)) or (not demo_mode and auto_trusted):
                fc.automation_status = "approved"
                trusted_auto_count += 1
            else:
                fc.automation_status = "ui_steps_generated"
            ui_generated_count += 1
        except Exception as exc:
            fc.automation_status = "draft"
            ui_failed_count += 1

    approved_count = sum(1 for item in cases if item.automation_status == "approved")
    if demo_mode and approved_count > 0:
        task.status = "approved"
    elif ui_generated_count > 0:
        task.status = "ui_steps_generated"
    db.commit()

    steps_status["generate_ui"] = {
        "ok": ui_failed_count == 0,
        "total": len(cases),
        "generated": ui_generated_count,
        "approved": approved_count,
        "needs_review": max(ui_generated_count - approved_count, 0),
        "failed": ui_failed_count,
        "demo_mode": demo_mode,
    }

    # ─── 步骤 4（非 demo 模式）：执行预检 ──────────────
    preflight_result = None
    if not demo_mode:
        try:
            task = get_or_404(db, FunctionalTask, task_id)
            preflight_result = preflight_functional_package(db, task, persist=True)
            steps_status["preflight"] = {
                "ok": True,
                "executable_count": preflight_result.get("executable_count", 0),
                "total": preflight_result.get("total", 0),
                "counts": preflight_result.get("counts", {}),
            }
        except Exception as exc:
            steps_status["preflight"] = {"ok": False, "error": str(exc)[:300]}

    return {
        "task": functional_task_detail(db, task),
        "steps": steps_status,
        "preflight": preflight_result,
        "summary": f"扫描{'✅' if steps_status.get('scan',{}).get('ok') else '❌'} → "
                   f"生成用例{'✅' if steps_status.get('generate_cases',{}).get('ok') else '❌'} → "
                   f"生成步骤{'✅' if steps_status.get('generate_ui',{}).get('ok') else '❌'}"
                   + (f" → 预检{'✅' if steps_status.get('preflight',{}).get('ok') else '❌'}" if not demo_mode else ""),
    }


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
    if functional_case_kind(case) == "business_authenticated":
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
    _assert_forward_status(task, "ui_steps_generated")

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


def _prepare_requirement_package(db: Session, task_id: int, payload: FunctionalScanRequest | None, demo_mode: bool=False) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__prepare_requirement_package(db, task_id, payload, demo_mode)


def ui_steps_have_strong_assertion(steps: Any) -> bool:
    _sync_compat_globals()
    return _impl_ui_steps_have_strong_assertion(steps)


def save_generated_functional_ui_steps(db: Session, task: FunctionalTask, case: FunctionalCase, snapshot: PageSnapshot | None=None) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl_save_generated_functional_ui_steps(db, task, case, snapshot)


def can_execute_functional_case(functional_case: FunctionalCase, payload: FunctionalExecuteRequest | None=None) -> tuple[bool, str]:
    _sync_compat_globals()
    return _impl_can_execute_functional_case(functional_case, payload)
