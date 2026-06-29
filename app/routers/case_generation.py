from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

# SEC-05: 上传文件大小上限（20MB），防止内存 DoS
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

from ..core.utils import (
    CASE_GENERATION_TEST_RESULTS,
    apply_case_generation_ocr_material,
    batch_update_case_generation_cases_for_task,
    case_generation_detail,
    case_generation_case_is_protected,
    case_generation_refs_include_note,
    case_generation_refs_include_screenshot,
    case_generation_screenshot_impact,
    case_generation_stats,
    case_generation_task_proxy,
    ensure_case_generation_task,
    ensure_case_generation_workspace,
    ensure_project_exists,
    generate_case_generation_cases_for_task,
    get_or_404,
    latest_ai_config,
    remove_uploaded_case_generation_file,
    safe_file_response,
    schema_data,
    serialize,
)
from ..database import get_db
from ..functional_testing import (
    analyze_functional_screenshot,
    store_functional_screenshot_file,
)
from ..models import (
    CaseGenerationCase,
    CaseGenerationRequirementNote,
    CaseGenerationScreenshot,
    CaseGenerationTask,
    User,
)
from ..schemas import (
    CaseGenerationCaseBatchStatusUpdate,
    CaseGenerationCaseStatusUpdate,
    CaseGenerationCaseUpdate,
    CaseGenerationRequirementNoteCreate,
    CaseGenerationRequirementNoteUpdate,
    CaseGenerationScreenshotOcrUpdate,
    CaseGenerationTaskCreate,
    CaseGenerationTaskUpdate,
)
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api", tags=["case-generation"])

# 用例生成任务状态流转顺序
_CG_FORWARD_STATUS = [
    "draft", "screenshot_uploaded", "screenshot_analyzed",
    "requirements_updated", "cases_generated",
]


def _cg_allow_status(task: Any, new_status: str) -> bool:
    """检查新状态是否比当前状态更靠前（允许向前流转）。"""
    if not task.status or task.status not in _CG_FORWARD_STATUS or new_status not in _CG_FORWARD_STATUS:
        return True
    return _CG_FORWARD_STATUS.index(new_status) >= _CG_FORWARD_STATUS.index(task.status)


# ---------------------------------------------------------------------------
# Workspace routes
# ---------------------------------------------------------------------------


@router.get("/case-generation/workspace")
def get_case_generation_workspace(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = ensure_case_generation_workspace(db, project_id)
    return case_generation_detail(db, task)


@router.post("/case-generation/workspace/upload-screenshots")
async def upload_case_generation_workspace_screenshots(
    project_id: int = Query(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_workspace(db, project_id)
    uploaded: list[Dict[str, Any]] = []
    errors: list[str] = []
    for file in files:
        content = await file.read()
        if not content:
            errors.append(f"{file.filename}: 文件为空")
            continue
        if len(content) > MAX_UPLOAD_BYTES:
            errors.append(f"{file.filename}: 文件过大，最大 20MB")
            continue
        try:
            image_path = store_functional_screenshot_file(file.filename or "screenshot.png", content)
        except ValueError as exc:
            errors.append(f"{file.filename}: {exc}")
            continue
        screenshot = CaseGenerationScreenshot(
            task_id=task.id,
            image_path=image_path,
            analysis_result="",
            ocr_text="",
            corrected_text="",
            ocr_confidence=0,
            low_confidence_items="[]",
            regions="[]",
            needs_manual_confirm=1,
            ocr_error="",
            create_time=datetime.now(),
        )
        db.add(screenshot)
        db.flush()
        uploaded.append(serialize(screenshot))
    if not uploaded and errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="；".join(errors[:5]))
    if uploaded and _cg_allow_status(task, "screenshot_uploaded"):
        task.status = "screenshot_uploaded"
        task.update_time = datetime.now()
    db.commit()
    db.refresh(task)
    return {"uploaded": uploaded, "errors": errors, "workspace": case_generation_detail(db, task)}


@router.post("/case-generation/workspace/requirement-notes")
def create_case_generation_workspace_requirement_note(
    project_id: int = Query(...),
    payload: CaseGenerationRequirementNoteCreate = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_workspace(db, project_id)
    data = schema_data(payload)
    note_text = (data.get("note_text") or "").strip()
    if not note_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="补充需求不能为空")
    note = CaseGenerationRequirementNote(
        task_id=task.id,
        note_text=note_text,
        create_time=datetime.now(),
        update_time=None,
    )
    task.status = "requirements_updated"
    task.update_time = datetime.now()
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"note": serialize(note), "workspace": case_generation_detail(db, task)}


@router.post("/case-generation/workspace/generate-cases")
def generate_case_generation_workspace_cases(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_workspace(db, project_id)
    return generate_case_generation_cases_for_task(db, task)


@router.post("/case-generation/workspace/cases/batch-status")
def batch_update_case_generation_workspace_case_status(
    project_id: int = Query(...),
    payload: CaseGenerationCaseBatchStatusUpdate = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = ensure_case_generation_workspace(db, project_id)
    return batch_update_case_generation_cases_for_task(db, task.id, payload)


# ---------------------------------------------------------------------------
# Task routes
# ---------------------------------------------------------------------------


@router.get("/case-generation/tasks")
def list_case_generation_tasks(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(CaseGenerationTask)
    if project_id is not None:
        query = query.filter(CaseGenerationTask.project_id == project_id)
    return [case_generation_detail(db, item) for item in query.order_by(CaseGenerationTask.id.desc()).all()]


@router.post("/case-generation/tasks")
def create_case_generation_task(
    payload: CaseGenerationTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload)
    ensure_project_exists(db, data["project_id"])
    task = CaseGenerationTask(
        project_id=data["project_id"],
        task_name=(data.get("task_name") or "").strip(),
        target_name=(data.get("target_name") or "").strip(),
        target_url=(data.get("target_url") or "").strip(),
        requirement_text=data.get("requirement_text") or "",
        context=data.get("context") or "",
        status=data.get("status") or "draft",
        create_time=datetime.now(),
        update_time=None,
    )
    if not task.task_name or not task.target_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务名称和目标页面/功能不能为空")
    db.add(task)
    db.commit()
    db.refresh(task)
    return case_generation_detail(db, task)


@router.get("/case-generation/tasks/{task_id}")
def get_case_generation_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    return case_generation_detail(db, ensure_case_generation_task(db, task_id))


@router.put("/case-generation/tasks/{task_id}")
def update_case_generation_task(
    task_id: int,
    payload: CaseGenerationTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_task(db, task_id)
    data = schema_data(payload, exclude_unset=True)
    if "project_id" in data and data["project_id"] is not None:
        ensure_project_exists(db, data["project_id"])
    for field in ["project_id", "task_name", "target_name", "target_url", "requirement_text", "context", "status"]:
        if field in data and data[field] is not None:
            value = data[field]
            if field in {"task_name", "target_name", "target_url"}:
                value = str(value or "").strip()
            setattr(task, field, value)
    if not task.task_name or not task.target_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务名称和目标页面/功能不能为空")
    task.update_time = datetime.now()
    db.commit()
    db.refresh(task)
    return case_generation_detail(db, task)


@router.delete("/case-generation/tasks/{task_id}")
def delete_case_generation_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    task = ensure_case_generation_task(db, task_id)
    screenshots = db.query(CaseGenerationScreenshot).filter(CaseGenerationScreenshot.task_id == task.id).all()
    for screenshot in screenshots:
        remove_uploaded_case_generation_file(screenshot.image_path)
    db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == task.id).delete(synchronize_session=False)
    db.query(CaseGenerationScreenshot).filter(CaseGenerationScreenshot.task_id == task.id).delete(synchronize_session=False)
    db.query(CaseGenerationRequirementNote).filter(CaseGenerationRequirementNote.task_id == task.id).delete(synchronize_session=False)
    db.delete(task)
    db.commit()
    return {"message": "deleted"}


# ---------------------------------------------------------------------------
# Screenshot routes
# ---------------------------------------------------------------------------


@router.post("/case-generation/tasks/{task_id}/upload-screenshots")
async def upload_case_generation_screenshots(
    task_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_task(db, task_id)
    uploaded: list[Dict[str, Any]] = []
    errors: list[str] = []
    for file in files:
        content = await file.read()
        if not content:
            errors.append(f"{file.filename}: 文件为空")
            continue
        if len(content) > MAX_UPLOAD_BYTES:
            errors.append(f"{file.filename}: 文件过大，最大 20MB")
            continue
        try:
            image_path = store_functional_screenshot_file(file.filename or "screenshot.png", content)
        except ValueError as exc:
            errors.append(f"{file.filename}: {exc}")
            continue
        screenshot = CaseGenerationScreenshot(
            task_id=task.id,
            image_path=image_path,
            analysis_result="",
            ocr_text="",
            corrected_text="",
            ocr_confidence=0,
            low_confidence_items="[]",
            regions="[]",
            needs_manual_confirm=1,
            ocr_error="",
            create_time=datetime.now(),
        )
        db.add(screenshot)
        db.flush()
        uploaded.append(serialize(screenshot))
    if not uploaded and errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="；".join(errors[:5]))
    if uploaded and _cg_allow_status(task, "screenshot_uploaded"):
        task.status = "screenshot_uploaded"
        task.update_time = datetime.now()
    db.commit()
    db.refresh(task)
    return {"uploaded": uploaded, "errors": errors, "task": case_generation_detail(db, task)}


@router.get("/case-generation/screenshots/{screenshot_id}/file")
def get_case_generation_screenshot_file(
    screenshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    screenshot = get_or_404(db, CaseGenerationScreenshot, screenshot_id)
    return safe_file_response(screenshot.image_path)


@router.get("/case-generation/screenshots/{screenshot_id}/impact")
def get_case_generation_screenshot_impact(
    screenshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, int]:
    screenshot = get_or_404(db, CaseGenerationScreenshot, screenshot_id)
    return case_generation_screenshot_impact(db, screenshot)


@router.post("/case-generation/screenshots/{screenshot_id}/analyze")
def analyze_case_generation_screenshot(
    screenshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    screenshot = get_or_404(db, CaseGenerationScreenshot, screenshot_id)
    task = ensure_case_generation_task(db, screenshot.task_id)
    try:
        screenshot.analysis_result = analyze_functional_screenshot(
            case_generation_task_proxy(task),
            screenshot,
            latest_ai_config(db),
        )
        apply_case_generation_ocr_material(screenshot, screenshot.analysis_result or "")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    task.status = "screenshot_analyzed"
    task.update_time = datetime.now()
    db.commit()
    db.refresh(screenshot)
    return {"screenshot": serialize(screenshot), "task": case_generation_detail(db, task)}


@router.put("/case-generation/screenshots/{screenshot_id}/ocr-text")
def update_case_generation_screenshot_ocr_text(
    screenshot_id: int,
    payload: CaseGenerationScreenshotOcrUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    screenshot = get_or_404(db, CaseGenerationScreenshot, screenshot_id)
    task = ensure_case_generation_task(db, screenshot.task_id)
    screenshot.corrected_text = (payload.corrected_text or "").strip()
    if screenshot.corrected_text:
        screenshot.needs_manual_confirm = 0
    else:
        screenshot.needs_manual_confirm = 1
    task.update_time = datetime.now()
    db.commit()
    db.refresh(screenshot)
    return {"screenshot": serialize(screenshot), "task": case_generation_detail(db, task)}


@router.delete("/case-generation/screenshots/{screenshot_id}")
def delete_case_generation_screenshot(
    screenshot_id: int,
    delete_cases: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    screenshot = get_or_404(db, CaseGenerationScreenshot, screenshot_id)
    task = ensure_case_generation_task(db, screenshot.task_id)
    impacted = [
        item
        for item in db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == task.id).all()
        if case_generation_refs_include_screenshot(item, screenshot.id)
    ]
    deleted_case_ids: list[int] = []
    preserved_case_ids: list[int] = []
    for item in impacted:
        if delete_cases and not case_generation_case_is_protected(item):
            deleted_case_ids.append(item.id)
            db.delete(item)
        else:
            item.source_missing = 1
            item.update_time = datetime.now()
            preserved_case_ids.append(item.id)
    remove_uploaded_case_generation_file(screenshot.image_path)
    db.delete(screenshot)
    task.status = "screenshot_deleted"
    task.update_time = datetime.now()
    db.commit()
    return {
        "message": "deleted",
        "deleted_case_ids": deleted_case_ids,
        "preserved_case_ids": preserved_case_ids,
        "task": case_generation_detail(db, task),
    }


# ---------------------------------------------------------------------------
# Requirement note routes
# ---------------------------------------------------------------------------


@router.post("/case-generation/tasks/{task_id}/requirement-notes")
def create_case_generation_requirement_note(
    task_id: int,
    payload: CaseGenerationRequirementNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_task(db, task_id)
    data = schema_data(payload)
    note_text = (data.get("note_text") or "").strip()
    if not note_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="补充需求不能为空")
    note = CaseGenerationRequirementNote(
        task_id=task.id,
        note_text=note_text,
        create_time=datetime.now(),
        update_time=None,
    )
    task.status = "requirements_updated"
    task.update_time = datetime.now()
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"note": serialize(note), "task": case_generation_detail(db, task)}


@router.put("/case-generation/requirement-notes/{note_id}")
def update_case_generation_requirement_note(
    note_id: int,
    payload: CaseGenerationRequirementNoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    note = get_or_404(db, CaseGenerationRequirementNote, note_id)
    task = ensure_case_generation_task(db, note.task_id)
    data = schema_data(payload)
    note_text = (data.get("note_text") or "").strip()
    if not note_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="补充需求不能为空")
    note.note_text = note_text
    note.update_time = datetime.now()
    task.status = "requirements_updated"
    task.update_time = datetime.now()
    db.commit()
    db.refresh(note)
    return {"note": serialize(note), "task": case_generation_detail(db, task)}


@router.delete("/case-generation/requirement-notes/{note_id}")
def delete_case_generation_requirement_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    note = get_or_404(db, CaseGenerationRequirementNote, note_id)
    task = ensure_case_generation_task(db, note.task_id)
    for item in db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == task.id).all():
        if case_generation_refs_include_note(item, note.id):
            item.source_missing = 1
            item.update_time = datetime.now()
    db.delete(note)
    task.status = "requirements_updated"
    task.update_time = datetime.now()
    db.commit()
    return {"message": "deleted", "task": case_generation_detail(db, task)}


# ---------------------------------------------------------------------------
# Case routes
# ---------------------------------------------------------------------------


@router.post("/case-generation/tasks/{task_id}/generate-cases")
def generate_case_generation_cases(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_task(db, task_id)
    return generate_case_generation_cases_for_task(db, task)


@router.put("/case-generation/cases/{case_id}")
def update_case_generation_case(
    case_id: int,
    payload: CaseGenerationCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    item = get_or_404(db, CaseGenerationCase, case_id)
    data = schema_data(payload, exclude_unset=True)
    for field in ["title", "precondition", "steps", "expected", "priority", "remark"]:
        if field in data and data[field] is not None:
            setattr(item, field, data[field])
    if not item.title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用例标题不能为空")
    item.manual_edited = 1
    item.update_time = datetime.now()
    db.commit()
    db.refresh(item)
    return serialize(item)


@router.delete("/case-generation/cases/{case_id}")
def delete_case_generation_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    item = get_or_404(db, CaseGenerationCase, case_id)
    task = ensure_case_generation_task(db, item.task_id)
    db.delete(item)
    task.update_time = datetime.now()
    db.commit()
    return {"message": "deleted"}


@router.put("/case-generation/cases/{case_id}/status")
def update_case_generation_case_status(
    case_id: int,
    payload: CaseGenerationCaseStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    item = get_or_404(db, CaseGenerationCase, case_id)
    if payload.test_result not in CASE_GENERATION_TEST_RESULTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的测试状态")
    item.test_result = payload.test_result
    item.update_time = datetime.now()
    db.commit()
    db.refresh(item)
    return serialize(item)


@router.post("/case-generation/tasks/{task_id}/cases/batch-status")
def batch_update_case_generation_case_status(
    task_id: int,
    payload: CaseGenerationCaseBatchStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    ensure_case_generation_task(db, task_id)
    return batch_update_case_generation_cases_for_task(db, task_id, payload)


@router.get("/case-generation/tasks/{task_id}/cases/stats")
def get_case_generation_case_stats(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, int]:
    ensure_case_generation_task(db, task_id)
    cases = db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == task_id).all()
    return case_generation_stats(cases)
