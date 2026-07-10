from __future__ import annotations

import sys
from functools import wraps


CASE_GENERATION_TEST_RESULTS = {"untested", "passed", "failed", "blocked", "skipped"}

CASE_GENERATION_WORKSPACE_TASK_NAME = "用例生成草稿"

CASE_GENERATION_WORKSPACE_TARGET_NAME = "用例生成"


_COMPAT_NAMES = (
    "BASE_DIR",
    "CASE_GENERATION_TEST_RESULTS",
    "CASE_GENERATION_WORKSPACE_TARGET_NAME",
    "CASE_GENERATION_WORKSPACE_TASK_NAME",
    "CaseGenerationCase",
    "CaseGenerationRequirementNote",
    "CaseGenerationScreenshot",
    "CaseGenerationTask",
    "HTTPException",
    "Path",
    "Project",
    "SimpleNamespace",
    "case_generation_case_is_protected",
    "case_generation_detail",
    "case_generation_refs_include_screenshot",
    "case_generation_serialize_json",
    "case_generation_source_refs",
    "case_generation_stats",
    "case_generation_task_proxy",
    "datetime",
    "ensure_project_exists",
    "generate_functional_cases",
    "get_or_404",
    "json",
    "latest_ai_config",
    "parse_json_value",
    "serialize",
    "serialize_many",
    "status",
    "uuid4",
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


def _impl_case_generation_case_is_protected(item: CaseGenerationCase) -> bool:
    return bool(item.manual_edited) or (item.test_result or "untested") != "untested"


def _impl_ensure_case_generation_workspace(db: Session, project_id: int) -> CaseGenerationTask:
    ensure_project_exists(db, project_id)
    task = (
        db.query(CaseGenerationTask)
        .filter(
            CaseGenerationTask.project_id == project_id,
            CaseGenerationTask.task_name == CASE_GENERATION_WORKSPACE_TASK_NAME,
            CaseGenerationTask.target_name == CASE_GENERATION_WORKSPACE_TARGET_NAME,
        )
        .order_by(CaseGenerationTask.id.desc())
        .first()
    )
    if task:
        return task
    task = CaseGenerationTask(
        project_id=project_id,
        task_name=CASE_GENERATION_WORKSPACE_TASK_NAME,
        target_name=CASE_GENERATION_WORKSPACE_TARGET_NAME,
        target_url="",
        requirement_text="",
        context="",
        status="draft",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _impl_case_generation_serialize_json(value: Any) -> str:
    return json.dumps(value or [], ensure_ascii=False)


def _impl_apply_case_generation_ocr_material(screenshot: CaseGenerationScreenshot, analysis_result: str) -> None:
    payload = parse_json_value(analysis_result, {})
    material = payload.get("ocr_material") if isinstance(payload, dict) else {}
    if not isinstance(material, dict):
        material = {}
    screenshot.ocr_text = str(material.get("ocr_text") or "")
    try:
        screenshot.ocr_confidence = float(material.get("ocr_confidence") or 0)
    except (TypeError, ValueError):
        screenshot.ocr_confidence = 0
    screenshot.low_confidence_items = case_generation_serialize_json(material.get("low_confidence_items"))
    screenshot.regions = case_generation_serialize_json(material.get("regions"))
    screenshot.needs_manual_confirm = 1 if material.get("needs_manual_confirm", True) else 0
    screenshot.ocr_error = str(material.get("ocr_error") or "")


def _impl_case_generation_task_proxy(task: CaseGenerationTask) -> SimpleNamespace:
    target = task.target_url or task.target_name or ""
    return SimpleNamespace(
        id=task.id,
        project_id=task.project_id,
        iteration_name=task.task_name,
        target_url=target,
        requirement_text=task.requirement_text or "",
        context=task.context or "",
        status=task.status,
    )


def _impl_case_generation_source_refs(
    screenshots: Iterable[CaseGenerationScreenshot],
    notes: Iterable[CaseGenerationRequirementNote],
) -> str:
    payload = {
        "screenshots": [item.id for item in screenshots],
        "notes": [item.id for item in notes],
        "initial_requirement": True,
    }
    return json.dumps(payload, ensure_ascii=False)


def _impl_case_generation_refs_include_screenshot(item: CaseGenerationCase, screenshot_id: int) -> bool:
    refs = parse_json_value(item.source_refs, {})
    values = refs.get("screenshots") if isinstance(refs, dict) else []
    return str(screenshot_id) in {str(value) for value in (values or [])}


def _impl_case_generation_refs_include_note(item: CaseGenerationCase, note_id: int) -> bool:
    refs = parse_json_value(item.source_refs, {})
    values = refs.get("notes") if isinstance(refs, dict) else []
    return str(note_id) in {str(value) for value in (values or [])}


def _impl_case_generation_stats(cases: Iterable[CaseGenerationCase]) -> Dict[str, int]:
    stats = {key: 0 for key in ["total", "untested", "passed", "failed", "blocked", "skipped"]}
    for item in cases:
        stats["total"] += 1
        result = item.test_result or "untested"
        if result not in CASE_GENERATION_TEST_RESULTS:
            result = "untested"
        stats[result] += 1
    return stats


def _impl_case_generation_detail(db: Session, task: CaseGenerationTask) -> Dict[str, Any]:
    data = serialize(task)
    project = db.get(Project, task.project_id)
    data["project_name"] = project.name if project else task.project_id
    screenshots = (
        db.query(CaseGenerationScreenshot)
        .filter(CaseGenerationScreenshot.task_id == task.id)
        .order_by(CaseGenerationScreenshot.id.desc())
        .all()
    )
    notes = (
        db.query(CaseGenerationRequirementNote)
        .filter(CaseGenerationRequirementNote.task_id == task.id)
        .order_by(CaseGenerationRequirementNote.id.desc())
        .all()
    )
    cases = (
        db.query(CaseGenerationCase)
        .filter(CaseGenerationCase.task_id == task.id)
        .order_by(CaseGenerationCase.id.asc())
        .all()
    )
    data["screenshots"] = serialize_many(screenshots)
    data["requirement_notes"] = serialize_many(notes)
    data["cases"] = serialize_many(cases)
    data["stats"] = case_generation_stats(cases)
    return data


def _impl_remove_uploaded_case_generation_file(raw_path: str | None) -> None:
    if not raw_path:
        return
    try:
        path = Path(raw_path)
        if not path.is_absolute():
            path = BASE_DIR / path
        resolved = path.resolve()
        reports_dir = (BASE_DIR / "reports").resolve()
        if resolved.exists() and resolved.is_file() and (resolved == reports_dir or reports_dir in resolved.parents):
            resolved.unlink()
    except Exception:
        pass


def _impl_case_generation_screenshot_impact(db: Session, screenshot: CaseGenerationScreenshot) -> Dict[str, int]:
    impacted = [
        item
        for item in db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == screenshot.task_id).all()
        if case_generation_refs_include_screenshot(item, screenshot.id)
    ]
    deletable = [item for item in impacted if not case_generation_case_is_protected(item)]
    protected = [item for item in impacted if case_generation_case_is_protected(item)]
    return {
        "total": len(impacted),
        "deletable": len(deletable),
        "protected": len(protected),
    }


def _impl_generate_case_generation_cases_for_task(db: Session, task: CaseGenerationTask) -> Dict[str, Any]:
    screenshots = (
        db.query(CaseGenerationScreenshot)
        .filter(CaseGenerationScreenshot.task_id == task.id)
        .order_by(CaseGenerationScreenshot.id.asc())
        .all()
    )
    notes = (
        db.query(CaseGenerationRequirementNote)
        .filter(CaseGenerationRequirementNote.task_id == task.id)
        .order_by(CaseGenerationRequirementNote.id.asc())
        .all()
    )
    generated = generate_functional_cases(
        case_generation_task_proxy(task),
        "",
        None,
        latest_ai_config(db),
        screenshots,
        notes,
    )
    for old_case in db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == task.id).all():
        if not case_generation_case_is_protected(old_case):
            db.delete(old_case)
    db.flush()

    batch = uuid4().hex[:12]
    source_refs = case_generation_source_refs(screenshots, notes)
    created = 0
    for item in generated.items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        db.add(
            CaseGenerationCase(
                task_id=task.id,
                title=title[:200],
                precondition=item.get("precondition", ""),
                steps=item.get("steps", ""),
                expected=item.get("expected", ""),
                priority=item.get("priority", "P1"),
                source_refs=source_refs,
                generation_batch=batch,
                manual_edited=0,
                test_result="untested",
                source_missing=0,
                remark="",
                create_time=datetime.now(),
                update_time=None,
            )
        )
        created += 1
    task.status = "cases_generated"
    task.update_time = datetime.now()
    db.commit()
    db.refresh(task)
    return {"created": created, "workspace": case_generation_detail(db, task)}


def _impl_batch_update_case_generation_cases_for_task(
    db: Session,
    task_id: int,
    payload: CaseGenerationCaseBatchStatusUpdate,
) -> Dict[str, Any]:
    if payload.test_result not in CASE_GENERATION_TEST_RESULTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的测试状态")
    updated = (
        db.query(CaseGenerationCase)
        .filter(CaseGenerationCase.task_id == task_id, CaseGenerationCase.id.in_(payload.case_ids or [-1]))
        .update({"test_result": payload.test_result, "update_time": datetime.now()}, synchronize_session="fetch")
    )
    db.commit()
    return {"updated": updated, "test_result": payload.test_result}


def _impl_ensure_case_generation_task(db: Session, task_id: int) -> CaseGenerationTask:
    return get_or_404(db, CaseGenerationTask, task_id)


case_generation_case_is_protected = _compat_wrapper(_impl_case_generation_case_is_protected)
ensure_case_generation_workspace = _compat_wrapper(_impl_ensure_case_generation_workspace)
case_generation_serialize_json = _compat_wrapper(_impl_case_generation_serialize_json)
apply_case_generation_ocr_material = _compat_wrapper(_impl_apply_case_generation_ocr_material)
case_generation_task_proxy = _compat_wrapper(_impl_case_generation_task_proxy)
case_generation_source_refs = _compat_wrapper(_impl_case_generation_source_refs)
case_generation_refs_include_screenshot = _compat_wrapper(_impl_case_generation_refs_include_screenshot)
case_generation_refs_include_note = _compat_wrapper(_impl_case_generation_refs_include_note)
case_generation_stats = _compat_wrapper(_impl_case_generation_stats)
case_generation_detail = _compat_wrapper(_impl_case_generation_detail)
remove_uploaded_case_generation_file = _compat_wrapper(_impl_remove_uploaded_case_generation_file)
case_generation_screenshot_impact = _compat_wrapper(_impl_case_generation_screenshot_impact)
generate_case_generation_cases_for_task = _compat_wrapper(_impl_generate_case_generation_cases_for_task)
batch_update_case_generation_cases_for_task = _compat_wrapper(_impl_batch_update_case_generation_cases_for_task)
ensure_case_generation_task = _compat_wrapper(_impl_ensure_case_generation_task)
