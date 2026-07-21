from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..core.utils import safe_file_response
from ..functional_testing import store_functional_screenshot_file
from ..models import (
    Env,
    Project,
    RequirementVerification,
    User,
    VerificationClarification,
    VerificationDataSource,
    VerificationFormula,
    VerificationItem,
    VerificationMaterial,
    VerificationMemory,
    VerificationRun,
    VerificationRunDataset,
    VerificationRunItem,
    VerificationLearningEvent,
    VerificationLearningSession,
)
from ..security import get_current_user, require_admin
from ..services.requirement_verification import (
    ITEM_TYPES,
    RESULTS,
    analyze_requirement,
    apply_screenshot_ocr,
    confirm_clarification,
    create_and_start_run,
    data_script_catalog,
    defer_clarification,
    evaluate_formula,
    execute_verification_run,
    interpret_clarification,
    json_load,
    json_text,
    normalize_data_setup,
    normalize_target_pages,
    open_manual_takeover_browser,
    close_manual_takeover_browser,
    serialize_formula,
    serialize_item,
    serialize_run,
    target_pages_for,
    validate_data_setup_for_project,
    validate_formula_definition,
    verification_preflight,
    verification_detail,
)
from ..verification_schemas import (
    RequirementVerificationCreate,
    RequirementVerificationUpdate,
    VerificationAnalysisRequest,
    VerificationClarificationAnswer,
    VerificationConfirmation,
    VerificationDataSourceCreate,
    VerificationDataSourceUpdate,
    VerificationFormulaCreate,
    VerificationFormulaUpdate,
    VerificationItemBatchConfirm,
    VerificationItemUpdate,
    VerificationCheckpointCreate,
    VerificationInheritRequest,
    VerificationLearningEventBatch,
    VerificationLearningSave,
    VerificationLearningSessionCreate,
    VerificationMaterialCreate,
    VerificationMemoryCreate,
    VerificationMemoryUpdate,
    VerificationPreflightRequest,
    VerificationRunCreate,
    VerificationRunRetry,
    VerificationTemplateCopyRequest,
)
from ..services.verification_runtime_v2 import cancel_run, pause_run, resolve_manual_action, resume_run
from ..services.verification_learning import (
    add_checkpoint,
    append_learning_events,
    begin_checkpoint_capture,
    boundary_combinations,
    cancel_learning_session,
    copy_public_template,
    cross_project_regression_suggestions,
    create_learning_session,
    defect_draft,
    efficiency_stats,
    inherit_from_task,
    requirement_diff,
    save_learning_session,
    serialize_learning_event,
    serialize_learning_session,
    similar_tasks,
)


router = APIRouter(prefix="/api/requirement-verifications", tags=["requirement-verifications"])
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _data(payload: Any, *, exclude_unset: bool = False) -> Dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=exclude_unset)
    return payload.dict(exclude_unset=exclude_unset)


def _task(db: Session, task_id: int) -> RequirementVerification:
    item = db.get(RequirementVerification, task_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="需求验证任务不存在")
    return item


def _project(db: Session, project_id: int) -> Project:
    item = db.get(Project, project_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return item


def _validate_formula_http(expression: str, rounding_mode: str, scale: int) -> None:
    try:
        validate_formula_definition(expression, rounding_mode, scale)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _target_pages_http(value: Any, fallback_url: str = "") -> list[Dict[str, str]]:
    try:
        return normalize_target_pages(value, fallback_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _data_setup_http(db: Session, project_id: int, value: Any) -> Dict[str, Any]:
    try:
        return validate_data_setup_for_project(db, project_id, value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("")
def list_verification_tasks(
    project_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    task_status: str | None = Query(default=None, alias="status"),
    archived: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(RequirementVerification)
    if project_id is not None:
        query = query.filter(RequirementVerification.project_id == project_id)
    normalized_keyword = str(keyword or "").strip()
    if normalized_keyword:
        query = query.filter(RequirementVerification.name.contains(normalized_keyword))
    if task_status:
        query = query.filter(RequirementVerification.status == task_status)
    if archived is not None:
        query = query.filter(RequirementVerification.is_archived == (1 if archived else 0))
    rows = query.order_by(
        func.coalesce(RequirementVerification.update_time, RequirementVerification.create_time).desc(),
        RequirementVerification.id.desc(),
    ).all()
    task_ids = [row.id for row in rows]
    item_counts: Dict[int, Dict[str, int]] = {}
    run_counts: Dict[int, int] = {}
    latest_results: Dict[int, str] = {}
    if task_ids:
        item_rows = (
            db.query(VerificationItem.task_id, VerificationItem.status, func.count(VerificationItem.id))
            .join(RequirementVerification, RequirementVerification.id == VerificationItem.task_id)
            .filter(
                VerificationItem.task_id.in_(task_ids),
                VerificationItem.analysis_version == RequirementVerification.analysis_version,
            )
            .group_by(VerificationItem.task_id, VerificationItem.status)
            .all()
        )
        for task_id, result, count in item_rows:
            item_counts.setdefault(task_id, {})[str(result or "unknown")] = int(count or 0)
        run_counts = {
            task_id: int(count or 0)
            for task_id, count in (
                db.query(VerificationRun.task_id, func.count(VerificationRun.id))
                .filter(VerificationRun.task_id.in_(task_ids))
                .group_by(VerificationRun.task_id)
                .all()
            )
        }
        latest_run = (
            db.query(
                VerificationRun.task_id.label("task_id"),
                func.max(VerificationRun.id).label("run_id"),
            )
            .filter(VerificationRun.task_id.in_(task_ids))
            .group_by(VerificationRun.task_id)
            .subquery()
        )
        latest_results = {
            task_id: result
            for task_id, result in (
                db.query(VerificationRun.task_id, VerificationRun.status)
                .join(latest_run, VerificationRun.id == latest_run.c.run_id)
                .all()
            )
        }
    return [
        {
            "id": row.id,
            "project_id": row.project_id,
            "name": row.name,
            "target_url": row.target_url or "",
            "target_pages": target_pages_for(row),
            "data_setup_step_count": len(normalize_data_setup(json_load(row.data_setup_json, {}))["steps"]),
            "status": row.status,
            "is_archived": bool(row.is_archived),
            "analysis_version": row.analysis_version,
            "item_count": sum(item_counts.get(row.id, {}).values()),
            "result_counts": item_counts.get(row.id, {}),
            "run_count": run_counts.get(row.id, 0),
            "latest_result": latest_results.get(row.id, ""),
            "create_time": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else "",
            "update_time": row.update_time.strftime("%Y-%m-%d %H:%M:%S") if row.update_time else "",
        }
        for row in rows
    ]


@router.get("/data-script-catalog")
def get_data_script_catalog(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    if project_id is not None:
        _project(db, project_id)
    return data_script_catalog(db, project_id)


@router.post("")
def create_verification_task(
    payload: RequirementVerificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = _data(payload)
    _project(db, data["project_id"])
    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="需求名称不能为空")
    target_pages = _target_pages_http(data.get("target_pages"), str(data.get("target_url") or ""))
    data_setup = _data_setup_http(db, data["project_id"], data.get("data_setup") or {})
    primary_url = next((page["url"] for page in target_pages if page["url"]), "")
    now = datetime.now()
    item = RequirementVerification(
        project_id=data["project_id"],
        name=name[:200],
        target_url=primary_url[:500],
        target_pages_json=json_text(target_pages),
        data_setup_json=json_text(data_setup),
        requirement_text=str(data.get("requirement_text") or ""),
        context=str(data.get("context") or ""),
        status="draft",
        is_archived=0,
        analysis_version=0,
        analysis_json="{}",
        create_time=now,
        update_time=None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return verification_detail(db, item)


@router.get("/{task_id}")
def get_verification_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    return verification_detail(db, _task(db, task_id))


@router.put("/{task_id}")
def update_verification_task(
    task_id: int,
    payload: RequirementVerificationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    item = _task(db, task_id)
    data = _data(payload, exclude_unset=True)
    for field in ("name", "requirement_text", "context", "status"):
        if field in data and data[field] is not None:
            setattr(item, field, str(data[field]).strip() if field != "requirement_text" else str(data[field]))
    if "target_pages" in data:
        pages = _target_pages_http(data.get("target_pages"))
        item.target_pages_json = json_text(pages)
        item.target_url = next((page["url"] for page in pages if page["url"]), "")[:500]
    elif "target_url" in data and data["target_url"] is not None:
        legacy_url = str(data["target_url"] or "").strip()
        pages = target_pages_for(item)
        if pages:
            pages[0]["url"] = legacy_url
        else:
            pages = _target_pages_http([], legacy_url)
        item.target_pages_json = json_text(pages)
        item.target_url = legacy_url[:500]
    if "is_archived" in data and data["is_archived"] is not None:
        item.is_archived = 1 if data["is_archived"] else 0
    if "data_setup" in data and data["data_setup"] is not None:
        item.data_setup_json = json_text(_data_setup_http(db, item.project_id, data["data_setup"]))
    if not item.name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="需求名称不能为空")
    item.update_time = datetime.now()
    db.commit()
    db.refresh(item)
    return verification_detail(db, item)


@router.delete("/{task_id}")
def delete_verification_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    item = _task(db, task_id)
    run_ids = [row[0] for row in db.query(VerificationRun.id).filter(VerificationRun.task_id == task_id).all()]
    if run_ids:
        db.query(VerificationRunItem).filter(VerificationRunItem.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(VerificationRunDataset).filter(VerificationRunDataset.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(VerificationRun).filter(VerificationRun.id.in_(run_ids)).delete(synchronize_session=False)
    learning_ids = [row[0] for row in db.query(VerificationLearningSession.id).filter(VerificationLearningSession.task_id == task_id).all()]
    if learning_ids:
        db.query(VerificationLearningEvent).filter(VerificationLearningEvent.session_id.in_(learning_ids)).delete(synchronize_session=False)
        db.query(VerificationLearningSession).filter(VerificationLearningSession.id.in_(learning_ids)).delete(synchronize_session=False)
    db.query(VerificationClarification).filter(VerificationClarification.task_id == task_id).delete(synchronize_session=False)
    db.query(VerificationFormula).filter(VerificationFormula.task_id == task_id).delete(synchronize_session=False)
    db.query(VerificationItem).filter(VerificationItem.task_id == task_id).delete(synchronize_session=False)
    db.query(VerificationMaterial).filter(VerificationMaterial.task_id == task_id).delete(synchronize_session=False)
    db.query(VerificationMemory).filter(VerificationMemory.source_task_id == task_id).update({VerificationMemory.source_task_id: None}, synchronize_session=False)
    db.delete(item)
    db.commit()
    return {"message": "deleted"}


@router.post("/{task_id}/materials")
def add_text_material(
    task_id: int,
    payload: VerificationMaterialCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = _task(db, task_id)
    data = _data(payload)
    text_value = str(data.get("content_text") or "").strip()
    if not text_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="材料内容不能为空")
    row = VerificationMaterial(
        task_id=task.id,
        material_type=str(data.get("material_type") or "note")[:32],
        name=str(data.get("name") or "")[:200],
        content_text=text_value,
        image_path="",
        ocr_text="",
        analysis_json="{}",
        status="active",
        create_time=datetime.now(),
    )
    db.add(row)
    task.status = "materials_ready"
    task.update_time = datetime.now()
    db.commit()
    return verification_detail(db, task)


@router.post("/{task_id}/materials/upload")
async def upload_material_screenshot(
    task_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = _task(db, task_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="截图文件为空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="截图最大20MB")
    try:
        image_path = store_functional_screenshot_file(file.filename or "requirement.png", content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    row = VerificationMaterial(
        task_id=task.id,
        material_type="prototype_screenshot",
        name=(file.filename or "原型截图")[:200],
        content_text="",
        image_path=image_path,
        ocr_text="",
        analysis_json="{}",
        status="active",
        create_time=datetime.now(),
    )
    db.add(row)
    db.flush()
    try:
        apply_screenshot_ocr(row)
    except Exception as exc:
        row.analysis_json = json_text({"ocr_error": str(exc)[:500]})
    task.status = "materials_ready"
    task.update_time = datetime.now()
    db.commit()
    return verification_detail(db, task)


@router.post("/materials/{material_id}/ocr")
def rerun_material_ocr(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationMaterial, material_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="材料不存在")
    result = apply_screenshot_ocr(row)
    db.commit()
    return {"material_id": row.id, "ocr": result}


@router.get("/materials/{material_id}/file")
def get_material_file(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    row = db.get(VerificationMaterial, material_id)
    if not row or not row.image_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="截图不存在")
    return safe_file_response(row.image_path)


@router.post("/{task_id}/analyze")
def analyze_verification_task(
    task_id: int,
    payload: VerificationAnalysisRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return analyze_requirement(db, _task(db, task_id), payload.mode if payload else "standard")


@router.put("/clarifications/{clarification_id}")
def answer_clarification(
    clarification_id: int,
    payload: VerificationClarificationAnswer,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationClarification, clarification_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="澄清问题不存在")
    return interpret_clarification(db, row, payload.answer or "", payload.supplement or "")


@router.post("/clarifications/{clarification_id}/confirm")
def confirm_clarification_answer(
    clarification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationClarification, clarification_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="澄清问题不存在")
    return confirm_clarification(db, row)


@router.post("/clarifications/{clarification_id}/defer")
def defer_clarification_answer(
    clarification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationClarification, clarification_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="澄清问题不存在")
    return defer_clarification(db, row)


@router.put("/items/{item_id}")
def update_verification_item(
    item_id: int,
    payload: VerificationItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationItem, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="验证项不存在")
    data = _data(payload, exclude_unset=True)
    if "item_type" in data and data["item_type"] not in ITEM_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证类型不支持")
    for field in ("title", "priority", "role_name", "precondition", "action_goal", "expected", "automation_level", "risk_level", "status"):
        if field in data and data[field] is not None:
            setattr(row, field, str(data[field]).strip())
    if "source_refs" in data:
        row.source_refs = json_text(data["source_refs"] or [])
    if "config" in data:
        row.config_json = json_text(data["config"] or {})
    row.confirmed = 0
    row.update_time = datetime.now()
    db.commit()
    db.refresh(row)
    return serialize_item(row)


@router.post("/{task_id}/items/batch-confirm")
def confirm_verification_items(
    task_id: int,
    payload: VerificationItemBatchConfirm,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = _task(db, task_id)
    query = db.query(VerificationItem).filter(
        VerificationItem.task_id == task.id,
        VerificationItem.analysis_version == task.analysis_version,
    )
    if payload.item_ids:
        query = query.filter(VerificationItem.id.in_(payload.item_ids))
    rows = query.all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可确认的验证项")
    blocked = []
    for row in rows:
        row.confirmed = 1 if payload.confirmed else 0
        if row.status == "blocked":
            if payload.confirmed:
                blocked.append(row.title)
        else:
            row.status = "ready" if payload.confirmed else "draft"
        row.update_time = datetime.now()
    if any(row.confirmed and row.status != "blocked" for row in rows):
        task.status = "ready"
    task.update_time = datetime.now()
    db.commit()
    return {"confirmed": sum(1 for row in rows if row.confirmed), "blocked": blocked}


@router.get("/projects/{project_id}/formulas")
def list_project_formulas(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    _project(db, project_id)
    rows = db.query(VerificationFormula).filter(VerificationFormula.project_id == project_id).order_by(VerificationFormula.id.desc()).all()
    return [serialize_formula(row) for row in rows]


@router.post("/projects/{project_id}/formulas")
def create_project_formula(
    project_id: int,
    payload: VerificationFormulaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    _project(db, project_id)
    data = _data(payload)
    _validate_formula_http(data["expression"], data["rounding_mode"].upper(), data["scale"])
    if data.get("task_id"):
        task = _task(db, int(data["task_id"]))
        if task.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="公式任务不属于当前项目")
    row = VerificationFormula(
        project_id=project_id,
        task_id=data.get("task_id"),
        analysis_version=None,
        name=data["name"].strip()[:200],
        version=1,
        expression=data["expression"].strip(),
        variables_json=json_text(data.get("variables") or {}),
        conditions_json=json_text(data.get("conditions") or {}),
        currency=str(data.get("currency") or "")[:16],
        scale=data["scale"],
        rounding_mode=data["rounding_mode"].upper(),
        rounding_stage=data["rounding_stage"],
        source_refs=json_text(data.get("source_refs") or []),
        status="draft",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_formula(row)


@router.put("/formulas/{formula_id}")
def update_formula(
    formula_id: int,
    payload: VerificationFormulaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationFormula, formula_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="金额公式不存在")
    data = _data(payload, exclude_unset=True)
    expression = str(data.get("expression", row.expression))
    rounding_mode = str(data.get("rounding_mode", row.rounding_mode)).upper()
    scale = int(data.get("scale", row.scale))
    _validate_formula_http(expression, rounding_mode, scale)
    for field in ("name", "expression", "currency", "rounding_stage"):
        if field in data and data[field] is not None:
            setattr(row, field, str(data[field]).strip())
    row.rounding_mode = rounding_mode
    row.scale = scale
    if "variables" in data:
        row.variables_json = json_text(data["variables"] or {})
    if "conditions" in data:
        row.conditions_json = json_text(data["conditions"] or {})
    if "source_refs" in data:
        row.source_refs = json_text(data["source_refs"] or [])
    row.status = "draft"
    row.version += 1
    row.update_time = datetime.now()
    db.commit()
    db.refresh(row)
    return serialize_formula(row)


@router.post("/formulas/{formula_id}/confirm")
def confirm_formula(
    formula_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationFormula, formula_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="金额公式不存在")
    _validate_formula_http(row.expression, row.rounding_mode, row.scale)
    row.status = "confirmed"
    row.update_time = datetime.now()
    db.commit()
    return serialize_formula(row)


@router.post("/formulas/{formula_id}/preview")
def preview_formula(
    formula_id: int,
    values: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    row = db.get(VerificationFormula, formula_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="金额公式不存在")
    try:
        return evaluate_formula(row, values)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _serialize_source(row: VerificationDataSource) -> Dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "env_id": row.env_id,
        "name": row.name,
        "allowed_methods": ["GET", "HEAD"],
        "allowed_paths": json_load(row.allowed_paths, []),
        "status": row.status,
    }


@router.get("/projects/{project_id}/data-sources")
def list_data_sources(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    _project(db, project_id)
    rows = db.query(VerificationDataSource).filter(VerificationDataSource.project_id == project_id).order_by(VerificationDataSource.id.desc()).all()
    return [_serialize_source(row) for row in rows]


@router.post("/projects/{project_id}/data-sources")
def create_data_source(
    project_id: int,
    payload: VerificationDataSourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    _project(db, project_id)
    env = db.get(Env, payload.env_id)
    if not env or env.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="环境不属于当前项目")
    paths = [str(path).strip() for path in payload.allowed_paths if str(path).strip()]
    if not paths or any(not path.startswith("/") or ".." in path or "://" in path for path in paths):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="白名单必须是安全的绝对路径前缀")
    row = VerificationDataSource(
        project_id=project_id,
        env_id=payload.env_id,
        name=payload.name.strip()[:160],
        allowed_paths=json_text(paths),
        status=payload.status,
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_source(row)


@router.put("/data-sources/{source_id}")
def update_data_source(
    source_id: int,
    payload: VerificationDataSourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationDataSource, source_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="只读数据源不存在")
    data = _data(payload, exclude_unset=True)
    if "allowed_paths" in data:
        paths = [str(path).strip() for path in data["allowed_paths"] or [] if str(path).strip()]
        if not paths or any(not path.startswith("/") or ".." in path or "://" in path for path in paths):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="白名单路径不合法")
        row.allowed_paths = json_text(paths)
    if data.get("name") is not None:
        row.name = str(data["name"]).strip()[:160]
    if data.get("status") is not None:
        row.status = str(data["status"])
    row.update_time = datetime.now()
    db.commit()
    return _serialize_source(row)


def _serialize_memory(row: VerificationMemory) -> Dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "memory_type": row.memory_type,
        "name": row.name,
        "content": json_load(row.content_json, {}),
        "source_task_id": row.source_task_id,
        "version": row.version,
        "status": row.status,
    }


@router.get("/projects/{project_id}/memories")
def list_memories(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    _project(db, project_id)
    rows = db.query(VerificationMemory).filter(VerificationMemory.project_id == project_id).order_by(VerificationMemory.id.desc()).all()
    return [_serialize_memory(row) for row in rows]


@router.post("/projects/{project_id}/memories")
def create_memory(
    project_id: int,
    payload: VerificationMemoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    _project(db, project_id)
    if payload.source_task_id and _task(db, payload.source_task_id).project_id != project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="记忆来源任务不属于当前项目")
    row = VerificationMemory(
        project_id=project_id,
        memory_type=payload.memory_type.strip()[:40],
        name=payload.name.strip()[:200],
        content_json=json_text(payload.content),
        source_task_id=payload.source_task_id,
        version=1,
        status="draft",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_memory(row)


@router.put("/memories/{memory_id}")
def update_memory(
    memory_id: int,
    payload: VerificationMemoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationMemory, memory_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="业务记忆不存在")
    data = _data(payload, exclude_unset=True)
    if data.get("name") is not None:
        row.name = str(data["name"]).strip()[:200]
    if data.get("content") is not None:
        row.content_json = json_text(data["content"])
    if data.get("status") is not None:
        row.status = str(data["status"])
    row.version += 1
    row.update_time = datetime.now()
    db.commit()
    return _serialize_memory(row)


@router.post("/memories/{memory_id}/confirm")
def confirm_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationMemory, memory_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="业务记忆不存在")
    content = json_load(row.content_json, None)
    if not isinstance(content, dict) or not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="业务记忆内容为空或格式错误")
    row.status = "confirmed"
    row.update_time = datetime.now()
    db.commit()
    return _serialize_memory(row)


@router.post("/{task_id}/preflight")
def preflight_run(
    task_id: int,
    payload: VerificationPreflightRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return verification_preflight(
        db,
        _task(db, task_id),
        payload.item_ids,
        payload.variables,
        payload.data_setup,
        runtime_check=payload.runtime_check,
        visible_browser=payload.visible_browser,
    )


@router.post("/{task_id}/runs")
def start_run(
    task_id: int,
    payload: VerificationRunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    run = create_and_start_run(
        db,
        _task(db, task_id),
        payload.item_ids,
        payload.variables,
        payload.visible_browser,
        payload.data_setup,
        payload.risk_confirmed,
        payload.mode,
        payload.reuse_data_from_run_id,
        payload.dataset_overrides,
    )
    return serialize_run(db, run)


@router.get("/runs/{run_id}")
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    row = db.get(VerificationRun, run_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")
    return serialize_run(db, row)


@router.post("/run-items/{run_item_id}/confirm")
async def confirm_run_item(
    run_item_id: int,
    payload: VerificationConfirmation,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationRunItem, run_item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行项不存在")
    if row.result not in {"waiting_user", "waiting_confirmation"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="执行项当前不在等待确认状态")
    pending_run = db.get(VerificationRun, row.run_id)
    if pending_run:
        await close_manual_takeover_browser(db, pending_run)
    run = resolve_manual_action(db, row, payload.decision, payload.candidate_index, payload.note or "", payload.observed_value)
    threading.Thread(target=execute_verification_run, args=(run.id,), daemon=True, name=f"verification-run-{run.id}").start()
    return {"message": "confirmation_saved", "run": serialize_run(db, run)}


@router.post("/runs/{run_id}/pause")
def pause_verification_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationRun, run_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")
    return serialize_run(db, pause_run(db, row))


@router.post("/runs/{run_id}/resume")
def resume_verification_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationRun, run_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")
    return serialize_run(db, resume_run(db, row))


@router.post("/runs/{run_id}/cancel")
async def cancel_verification_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationRun, run_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")
    await close_manual_takeover_browser(db, row)
    return serialize_run(db, cancel_run(db, row))


@router.post("/runs/{run_id}/open-browser")
async def open_verification_manual_browser(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(VerificationRun, run_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")
    if row.phase != "waiting_user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前执行不需要打开人工接管浏览器")
    return await open_manual_takeover_browser(db, row, current_user.id)


@router.post("/runs/{run_id}/retry")
def retry_verification_run(
    run_id: int,
    payload: VerificationRunRetry,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    source = db.get(VerificationRun, run_id)
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")
    if source.status not in {"failed", "blocked", "needs_review", "cancelled"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前执行尚未结束，请使用继续或完成人工接管")
    rows = db.query(VerificationRunItem).filter(VerificationRunItem.run_id == source.id).all()
    retry_ids = payload.item_ids or [row.item_id for row in rows if row.result in {"failed", "blocked", "needs_review", "skipped"}]
    if not retry_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有需要复跑的验证项")
    reuse_source = source.id if payload.strategy == "current_step" else None
    if payload.strategy not in {"current_step", "new_data"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="复跑方式只能是从当前步骤继续或使用新数据重新开始")
    run = create_and_start_run(
        db,
        _task(db, source.task_id),
        retry_ids,
        json_load(source.variables_json, {}),
        bool(source.visible_browser),
        json_load(source.data_setup_json, {"steps": []}),
        payload.risk_confirmed,
        "regression",
        reuse_source,
        {},
    )
    return serialize_run(db, run)


@router.post("/{task_id}/learning-sessions")
async def start_learning_session(
    task_id: int,
    payload: VerificationLearningSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = await create_learning_session(
        db,
        task_id,
        payload.role_name or "",
        payload.page_name or "",
        payload.start_url or "",
        payload.account_profile_id,
        current_user.id,
    )
    return serialize_learning_session(db, row)


@router.get("/learning-sessions/{session_id}")
def get_learning_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    from ..models import VerificationLearningSession

    row = db.get(VerificationLearningSession, session_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学习会话不存在")
    return serialize_learning_session(db, row)


@router.post("/learning-sessions/{session_id}/events")
def save_learning_events(
    session_id: str,
    payload: VerificationLearningEventBatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return serialize_learning_session(db, append_learning_events(db, session_id, payload.events))


@router.post("/learning-sessions/{session_id}/select-checkpoint")
def select_learning_checkpoint(
    session_id: str,
    payload: VerificationCheckpointCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return serialize_learning_event(add_checkpoint(db, session_id, _data(payload)))


@router.post("/learning-sessions/{session_id}/capture-checkpoint")
async def capture_learning_checkpoint(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return serialize_learning_session(db, await begin_checkpoint_capture(db, session_id))


@router.post("/learning-sessions/{session_id}/save")
async def save_learning_rules(
    session_id: str,
    payload: VerificationLearningSave,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return await save_learning_session(db, session_id, payload.name or "", payload.replay_verified, payload.promote_to_project)


@router.post("/learning-sessions/{session_id}/cancel")
async def cancel_learning_rules(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return serialize_learning_session(db, await cancel_learning_session(db, session_id))


@router.get("/{task_id}/similar")
def get_similar_verification_tasks(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    return {"items": similar_tasks(db, task_id)}


@router.get("/{task_id}/diff")
def get_verification_diff(
    task_id: int,
    source_task_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    return requirement_diff(db, task_id, source_task_id)


@router.get("/{task_id}/boundary-combinations")
def get_boundary_combinations(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    return boundary_combinations(db, task_id)


@router.get("/{task_id}/cross-project-suggestions")
def get_cross_project_suggestions(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    return {"items": cross_project_regression_suggestions(db, task_id)}


@router.post("/{task_id}/inherit")
def inherit_verification_task(
    task_id: int,
    payload: VerificationInheritRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return inherit_from_task(db, task_id, payload.source_task_id, payload.item_ids, payload.memory_ids)


@router.post("/projects/{project_id}/templates/copy")
def copy_verification_template(
    project_id: int,
    payload: VerificationTemplateCopyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    _project(db, project_id)
    _project(db, payload.target_project_id)
    return copy_public_template(db, project_id, payload.target_project_id, payload.memory_ids)


@router.get("/run-items/{run_item_id}/defect-draft")
def get_defect_draft(
    run_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    return defect_draft(db, run_item_id)


@router.get("/stats/efficiency")
def get_verification_efficiency(
    project_id: int | None = Query(default=None),
    task_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    return efficiency_stats(db, project_id, task_id)
