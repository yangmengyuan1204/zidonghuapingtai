from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

import json
import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict, Iterable, Type

from sqlalchemy import func
from sqlalchemy.orm import Session

# SEC-05: 上传文件大小上限（20MB），防止内存 DoS
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

from ..core.utils import (
    QUALITY_AUTH_RISK,
    QUALITY_EXECUTABLE,
    QUALITY_LOCATOR_RISK,
    QUALITY_MISSING_VARIABLES,
    QUALITY_NEEDS_REVIEW,
    QUALITY_NOT_RECOMMENDED,
    QUALITY_UNCHECKED,
    compare_data_check_values,
    ensure_project_exists,
    execute_functional_data_check_rule,
    extract_response_value,
    full_data_check_url,
    functional_task_conclusion_summary,
    functional_task_detail,
    functional_case_auto_trusted,
    functional_case_kind,
    get_or_404,
    impact_item_key,
    is_sensitive_account_key,
    latest_ai_config,
    lookup_nested_value,
    normalize_data_check_payload,
    normalize_functional_result,
    normalize_json_fields,
    preflight_functional_package,
    quality_report_payload,
    require_non_blank_text,
    resolve_execution_account,
    safe_file_response,
    save_ui_record,
    schema_data,
    seed_functional_package_data,
    serialize,
    serialize_many,
    suggest_functional_impact_items,
)
from ..models import (
    FunctionalCase,
    FunctionalDataCheckResult,
    FunctionalDataCheckRule,
    FunctionalImpactItem,
    FunctionalRequirementNote,
    FunctionalRun,
    FunctionalScreenshot,
    FunctionalTask,
    PageSnapshot,
    TestAccountBinding,
    TestRecord,
    UiCase,
    User,
)
from ..schemas import (
    FunctionalCaseBatchAutomationUpdate,
    FunctionalCaseBatchIds,
    FunctionalCaseBatchStatusUpdate,
    FunctionalCaseStats,
    FunctionalCaseStatusUpdate,
    FunctionalCaseUpdate,
    FunctionalDataCheckRuleCreate,
    FunctionalDataCheckRuleUpdate,
    FunctionalExecuteRequest,
    FunctionalImpactItemCreate,
    FunctionalImpactItemUpdate,
    FunctionalRequirementNoteCreate,
    FunctionalRequirementNoteUpdate,
    FunctionalScanRequest,
    FunctionalTaskContextUpdate,
    FunctionalTaskCreate,
    PreflightResult,
)
from ..executors import (
    ensure_report_dirs,
    execute_api_case,
    execute_ui_case,
    execute_ui_cases_batch,
    parse_json_value,
    _strip_leading_login_steps,
    to_json_text,
)
from ..functional_testing import (
    FunctionalScanError,
    analyze_functional_screenshot,
    diagnose_failure,
    generate_functional_cases,
    generate_ui_steps,
    read_axure_text,
    scan_page_dom,
    store_axure_file,
    store_functional_screenshot_file,
)
from ..database import get_db, safe_commit
from ..security import get_current_user, require_admin
from ..services.requirement_workflow import build_workflow_status

router = APIRouter(prefix="/api", tags=["functional-tasks"])


def _runtime_func(name: str, fallback: Any) -> Any:
    fallback_module = getattr(fallback, "__module__", "")
    if fallback_module and not fallback_module.startswith("app."):
        return fallback
    main_module = sys.modules.get("app.main")
    return getattr(main_module, name, fallback) if main_module else fallback

# 功能测试任务状态流转顺序：禁止向更早的阶段回退
_FORWARD_STATUS = [
    "draft", "uploaded", "screenshot_uploaded", "screenshot_analyzed",
    "requirements_updated", "scanned", "cases_generated", "ui_steps_generated",
    "approved", "failed", "blocked", "needs_review", "passed", "error",
]


def _assert_forward_status(task: Any, new_status: str) -> None:
    """确保任务状态不会向更早的阶段回退。"""
    if task.status and task.status not in _FORWARD_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务当前状态 '{task.status}' 不在已知状态列表中，无法流转",
        )
    if new_status not in _FORWARD_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"目标状态 '{new_status}' 不在已知状态列表中",
        )
    old_idx = _FORWARD_STATUS.index(task.status) if task.status in _FORWARD_STATUS else -1
    new_idx = _FORWARD_STATUS.index(new_status)
    if new_idx < old_idx and task.status not in ("draft", "error"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"任务状态不能从 '{task.status}' 回退到 '{new_status}'",
        )


# ─── Functional tasks CRUD ─────────────────────────────────────────────


@router.get("/functional-tasks")
def list_functional_tasks(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(FunctionalTask)
    if project_id is not None:
        query = query.filter(FunctionalTask.project_id == project_id)
    return [functional_task_detail(db, item) for item in query.order_by(FunctionalTask.id.desc()).all()]


@router.post("/functional-tasks")
def create_functional_task(
    payload: FunctionalTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload)
    ensure_project_exists(db, data["project_id"])
    task = FunctionalTask(
        project_id=data["project_id"],
        iteration_name=data["iteration_name"].strip(),
        requirement_text=data.get("requirement_text") or "",
        context=data.get("context") or "",
        axure_path="",
        target_url=data["target_url"].strip(),
        status=data.get("status") or "draft",
        create_time=datetime.now(),
    )
    if not task.iteration_name or not task.target_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="迭代名称和目标页面不能为空")
    db.add(task)
    db.commit()
    db.refresh(task)
    return functional_task_detail(db, task)


@router.get("/functional-tasks/{task_id}")
def get_functional_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return functional_task_detail(db, get_or_404(db, FunctionalTask, task_id))


@router.put("/functional-tasks/{task_id}/context")
def update_functional_task_context(
    task_id: int,
    payload: FunctionalTaskContextUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    data = schema_data(payload)
    task.context = (data.get("context") or "").strip()
    db.commit()
    db.refresh(task)
    return functional_task_detail(db, task)


@router.delete("/functional-tasks/{task_id}")
def delete_functional_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    task = get_or_404(db, FunctionalTask, task_id)
    for case in db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id).all():
        if case.ui_case_id:
            db.query(TestRecord).filter(TestRecord.case_type == "ui", TestRecord.case_id == case.ui_case_id).delete(synchronize_session=False)
            db.query(TestAccountBinding).filter(
                TestAccountBinding.target_type == "ui_case",
                TestAccountBinding.target_id == case.ui_case_id,
            ).delete(synchronize_session=False)
            db.query(UiCase).filter(UiCase.id == case.ui_case_id).delete(synchronize_session=False)
        db.query(TestAccountBinding).filter(
            TestAccountBinding.target_type == "functional_case",
            TestAccountBinding.target_id == case.id,
        ).delete(synchronize_session=False)
    db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id).delete(synchronize_session=False)
    db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).delete(synchronize_session=False)
    db.query(FunctionalScreenshot).filter(FunctionalScreenshot.task_id == task.id).delete(synchronize_session=False)
    db.query(FunctionalRequirementNote).filter(FunctionalRequirementNote.task_id == task.id).delete(synchronize_session=False)
    db.query(FunctionalRun).filter(FunctionalRun.task_id == task.id).delete(synchronize_session=False)
    db.query(FunctionalImpactItem).filter(FunctionalImpactItem.task_id == task.id).delete(synchronize_session=False)
    db.query(FunctionalDataCheckResult).filter(FunctionalDataCheckResult.task_id == task.id).delete(synchronize_session=False)
    db.query(FunctionalDataCheckRule).filter(FunctionalDataCheckRule.task_id == task.id).delete(synchronize_session=False)
    db.query(TestAccountBinding).filter(
        TestAccountBinding.target_type == "functional_task",
        TestAccountBinding.target_id == task.id,
    ).delete(synchronize_session=False)
    db.delete(task)
    db.commit()
    return {"message": "deleted"}


# ─── Impact items ──────────────────────────────────────────────────────


@router.post("/functional-tasks/{task_id}/impact-items/analyze")
def analyze_functional_impact_items(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    existing_keys = {
        impact_item_key(item.item_type, item.ref_id, item.title, item.target)
        for item in db.query(FunctionalImpactItem).filter(FunctionalImpactItem.task_id == task.id).all()
    }
    created = []
    for item in suggest_functional_impact_items(db, task):
        key = impact_item_key(item.get("item_type") or "", item.get("ref_id"), item.get("title") or "", item.get("target") or "")
        if key in existing_keys:
            continue
        impact = FunctionalImpactItem(
            task_id=task.id,
            item_type=item.get("item_type") or "manual",
            ref_id=item.get("ref_id"),
            title=(item.get("title") or "关联影响项")[:200],
            target=item.get("target") or "",
            risk_level=item.get("risk_level") or "P1",
            test_result="untested",
            source=item.get("source") or "rule",
            reason=item.get("reason") or "",
            remark="",
            create_time=datetime.now(),
            update_time=None,
        )
        db.add(impact)
        db.flush()
        created.append(impact)
        existing_keys.add(key)
    db.commit()
    return {"created": len(created), "items": serialize_many(created), "task": functional_task_detail(db, task)}


@router.post("/functional-tasks/{task_id}/impact-items")
def create_functional_impact_item(
    task_id: int,
    payload: FunctionalImpactItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    data = schema_data(payload)
    require_non_blank_text(data, "title", "影响项标题")
    item = FunctionalImpactItem(
        task_id=task.id,
        item_type=data.get("item_type") or "manual",
        ref_id=data.get("ref_id"),
        title=data["title"][:200],
        target=data.get("target") or "",
        risk_level=data.get("risk_level") or "P1",
        test_result=normalize_functional_result(data.get("test_result")),
        source=data.get("source") or "manual",
        reason=data.get("reason") or "",
        remark=data.get("remark") or "",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"item": serialize(item), "task": functional_task_detail(db, task)}


@router.put("/functional-impact-items/{item_id}")
def update_functional_impact_item(
    item_id: int,
    payload: FunctionalImpactItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    item = get_or_404(db, FunctionalImpactItem, item_id)
    data = schema_data(payload, exclude_unset=True)
    if "title" in data and data["title"] is not None:
        require_non_blank_text(data, "title", "影响项标题")
    if "test_result" in data and data["test_result"] is not None:
        data["test_result"] = normalize_functional_result(data["test_result"])
    for field in ["item_type", "ref_id", "title", "target", "risk_level", "test_result", "source", "reason", "remark"]:
        if field in data and data[field] is not None:
            setattr(item, field, data[field])
    item.update_time = datetime.now()
    db.commit()
    db.refresh(item)
    return {"item": serialize(item), "task": functional_task_detail(db, get_or_404(db, FunctionalTask, item.task_id))}


@router.delete("/functional-impact-items/{item_id}")
def delete_functional_impact_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    item = get_or_404(db, FunctionalImpactItem, item_id)
    task = get_or_404(db, FunctionalTask, item.task_id)
    db.delete(item)
    db.commit()
    return {"message": "deleted", "task": functional_task_detail(db, task)}


# ─── Data check rules ──────────────────────────────────────────────────


@router.post("/functional-tasks/{task_id}/data-check-rules")
def create_functional_data_check_rule(
    task_id: int,
    payload: FunctionalDataCheckRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    data = normalize_data_check_payload(schema_data(payload), require_name=True)
    rule = FunctionalDataCheckRule(
        task_id=task.id,
        rule_name=data["rule_name"],
        check_type=data.get("check_type") or "page_api_consistency",
        page_value=data.get("page_value") or "",
        api_method=data.get("api_method") or "GET",
        api_url=data.get("api_url") or "",
        api_headers=data.get("api_headers") or "{}",
        api_body=data.get("api_body") or "{}",
        api_value_path=data.get("api_value_path") or "json",
        compare_rule=data.get("compare_rule") or "{}",
        expected_value=data.get("expected_value") or "",
        status=data.get("status") or "active",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"rule": serialize(rule), "task": functional_task_detail(db, task)}


@router.put("/functional-data-check-rules/{rule_id}")
def update_functional_data_check_rule(
    rule_id: int,
    payload: FunctionalDataCheckRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    rule = get_or_404(db, FunctionalDataCheckRule, rule_id)
    data = normalize_data_check_payload(schema_data(payload, exclude_unset=True))
    for field in [
        "rule_name",
        "check_type",
        "page_value",
        "api_method",
        "api_url",
        "api_headers",
        "api_body",
        "api_value_path",
        "compare_rule",
        "expected_value",
        "status",
    ]:
        if field in data and data[field] is not None:
            setattr(rule, field, data[field])
    rule.update_time = datetime.now()
    db.commit()
    db.refresh(rule)
    return {"rule": serialize(rule), "task": functional_task_detail(db, get_or_404(db, FunctionalTask, rule.task_id))}


@router.delete("/functional-data-check-rules/{rule_id}")
def delete_functional_data_check_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    rule = get_or_404(db, FunctionalDataCheckRule, rule_id)
    task = get_or_404(db, FunctionalTask, rule.task_id)
    db.query(FunctionalDataCheckResult).filter(FunctionalDataCheckResult.rule_id == rule.id).delete(synchronize_session=False)
    db.delete(rule)
    db.commit()
    return {"message": "deleted", "task": functional_task_detail(db, task)}


@router.post("/functional-data-check-rules/{rule_id}/execute")
def execute_functional_data_check(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    rule = get_or_404(db, FunctionalDataCheckRule, rule_id)
    task = get_or_404(db, FunctionalTask, rule.task_id)
    record = execute_functional_data_check_rule(db, task, rule)
    return {"result": serialize(record), "task": functional_task_detail(db, task)}


@router.post("/functional-tasks/{task_id}/data-check-runs")
def execute_functional_data_checks(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    rules = (
        db.query(FunctionalDataCheckRule)
        .filter(FunctionalDataCheckRule.task_id == task.id, FunctionalDataCheckRule.status != "inactive")
        .order_by(FunctionalDataCheckRule.id.asc())
        .all()
    )
    results = [execute_functional_data_check_rule(db, task, rule) for rule in rules]
    return {"results": serialize_many(results), "task": functional_task_detail(db, task)}


# ─── Task actions ──────────────────────────────────────────────────────


@router.post("/functional-tasks/{task_id}/seed-test-data")
def seed_functional_task_test_data(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    result = seed_functional_package_data(db, task)
    return {
        "task_id": task.id,
        "variables": result.get("variables") or {},
        "sources": result.get("sources") or [],
        "source_text_available": bool(result.get("source_text_available")),
        "message": "已抽取真实测试数据样本" if result.get("variables") else "未从页面快照或历史记录中抽到可用业务数据",
    }


@router.post("/functional-tasks/{task_id}/preflight-package")
def preflight_functional_task_package(
    task_id: int,
    payload: FunctionalExecuteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    selected_case_ids: list[int] = []
    if payload:
        if payload.case_id:
            selected_case_ids = [payload.case_id]
        elif payload.case_ids:
            selected_case_ids = list(dict.fromkeys(int(item) for item in payload.case_ids if int(item) > 0))
        if payload.save_variables:
            _save_functional_runtime_variables(task, payload.variables or {})
    return preflight_functional_package(db, task, payload, selected_case_ids or None, persist=True)


@router.get("/functional-tasks/{task_id}/workflow")
def get_functional_task_workflow(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """返回测试包工作流状态：当前阶段、各步骤状态、下一步建议、就绪度评分。"""
    task = get_or_404(db, FunctionalTask, task_id)
    return build_workflow_status(db, task)


@router.get("/functional-tasks/{task_id}/conclusion")
def get_functional_task_conclusion(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    return {"task_id": task.id, "conclusion": functional_task_conclusion_summary(db, task)}


@router.post("/functional-tasks/{task_id}/upload-axure")
async def upload_functional_axure(
    task_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件不能为空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件过大，最大 20MB")
    task.axure_path = store_axure_file(file.filename or "prototype.rp", content)
    _assert_forward_status(task, "uploaded")

    task.status = "uploaded"
    db.commit()
    db.refresh(task)
    axure_text = read_axure_text(task.axure_path)
    data = functional_task_detail(db, task)
    data["axure_text_preview"] = axure_text[:2000]
    return data


@router.post("/functional-tasks/{task_id}/upload-screenshot")
async def upload_functional_screenshot(
    task_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传截图不能为空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件过大，最大 20MB")
    try:
        image_path = store_functional_screenshot_file(file.filename or "screenshot.png", content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    screenshot = FunctionalScreenshot(
        task_id=task.id,
        image_path=image_path,
        analysis_result="",
        create_time=datetime.now(),
    )
    _assert_forward_status(task, "screenshot_uploaded")

    task.status = "screenshot_uploaded"
    db.add(screenshot)
    db.commit()
    db.refresh(screenshot)
    return {"screenshot": serialize(screenshot), "task": functional_task_detail(db, task)}


@router.post("/functional-tasks/{task_id}/upload-screenshots")
async def upload_functional_screenshots_batch(
    task_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
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
        screenshot = FunctionalScreenshot(
            task_id=task.id,
            image_path=image_path,
            analysis_result="",
            create_time=datetime.now(),
        )
        _assert_forward_status(task, "screenshot_uploaded")

        task.status = "screenshot_uploaded"
        db.add(screenshot)
        uploaded.append(serialize(screenshot))
    if not uploaded and errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="；".join(errors[:5]))
    db.commit()
    for item in uploaded:
        pass
    return {"uploaded": uploaded, "errors": errors, "task": functional_task_detail(db, task)}


@router.post("/functional-tasks/{task_id}/scan-page")
def scan_functional_page(
    task_id: int,
    payload: FunctionalScanRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    scanned: Dict[str, Any] = {}
    try:
        auth_config = schema_data(payload.auth, exclude_unset=True) if payload and payload.auth else None
        scanned = _runtime_func("scan_page_dom", scan_page_dom)(task.target_url, auth=auth_config)
    except FunctionalScanError as exc:
        trace = getattr(exc, "trace", None) or scanned.get("scan_trace", [])
        detail = str(exc)
        if trace:
            detail = f"{detail}\n\n扫描过程：\n" + "\n".join(f"- {item}" for item in trace)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
    except Exception as exc:
        trace = scanned.get("scan_trace", [])
        detail = f"扫描异常中断：{exc}"
        if trace:
            detail += "\n\n扫描过程：\n" + "\n".join(f"- {item}" for item in trace)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

    snapshot = PageSnapshot(
        task_id=task.id,
        page_url=task.target_url,
        dom_summary=scanned["dom_summary"],
        screenshot_path=scanned["screenshot_path"],
        scan_time=datetime.now(),
    )
    # 即使部分失败也保存已获取的数据
    _assert_forward_status(task, "scanned")

    task.status = "scanned"
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    data = serialize(snapshot)
    data["scan_trace"] = scanned.get("scan_trace", [])
    # 传递错误步骤信息以便前端展示
    dom_data = json.loads(scanned.get("dom_summary", "{}"))
    if dom_data.get("error_step"):
        data["scan_error_step"] = dom_data["error_step"]
        data["scan_error"] = dom_data.get("error", "")
    return data


@router.post("/functional-tasks/{task_id}/quick-start")
def quick_start_functional_task(
    task_id: int,
    payload: FunctionalScanRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """
    一键快速开始（演示模式，默认自动确认）。
    新流程请使用 POST /api/functional-tasks/{task_id}/ai-prepare。
    当 demo_mode=true 时保持原自动确认行为；demo_mode=false 时不自动确认且附加预检。
    """
    demo_mode = bool(payload.demo_mode) if payload else True
    return _prepare_requirement_package(db, task_id, payload, demo_mode=demo_mode)


@router.post("/functional-tasks/{task_id}/ai-prepare")
def ai_prepare_requirement_package(
    task_id: int,
    payload: FunctionalScanRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """
    AI 准备测试包：扫描页面 → 生成测试用例 → 生成UI步骤 → 预检。
    不自动确认，不自动执行。
    返回各步骤状态 + 预检结果 + 需人工处理的问题列表。
    """
    return _prepare_requirement_package(db, task_id, payload, demo_mode=False)


def _prepare_requirement_package(
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


def ui_steps_have_strong_assertion(steps: Any) -> bool:
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


@router.post("/functional-tasks/{task_id}/generate-cases")
def generate_functional_task_cases(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    axure_text = read_axure_text(task.axure_path)
    snapshot = db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).first()
    screenshots = db.query(FunctionalScreenshot).filter(FunctionalScreenshot.task_id == task.id).order_by(FunctionalScreenshot.id.asc()).all()
    notes = (
        db.query(FunctionalRequirementNote)
        .filter(FunctionalRequirementNote.task_id == task.id)
        .order_by(FunctionalRequirementNote.id.asc())
        .all()
    )
    generated = generate_functional_cases(task, axure_text, snapshot, latest_ai_config(db), screenshots, notes)

    for old_case in db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id, FunctionalCase.automation_status != "approved").all():
        db.delete(old_case)
    db.flush()

    for item in generated.items:
        db.add(
            FunctionalCase(
                task_id=task.id,
                title=item["title"],
                precondition=item.get("precondition", ""),
                steps=item.get("steps", ""),
                expected=item.get("expected", ""),
                category=item.get("category", "主流程"),
                priority=item.get("priority", "P1"),
                automation_status=item.get("automation_status", "draft"),
                ui_case_id=None,
                create_time=datetime.now(),
            )
        )
    _assert_forward_status(task, "cases_generated")

    task.status = "cases_generated"
    db.commit()
    result = {"source": generated.source, "warning": generated.warning, "task": functional_task_detail(db, task)}
    return result


# ─── Functional cases ──────────────────────────────────────────────────


@router.post("/functional-cases/{case_id}/preflight")
def preflight_check_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PreflightResult:
    functional_case = get_or_404(db, FunctionalCase, case_id)
    if not functional_case.ui_case_id:
        return PreflightResult(passed=False, errors=["该用例未关联 UI 步骤，无法执行"])
    ui_case = db.get(UiCase, functional_case.ui_case_id)
    if not ui_case:
        return PreflightResult(passed=False, errors=["关联的 UI 用例不存在"])
    try:
        from ..executors import preflight_check
        errors, warnings = preflight_check(ui_case)
        return PreflightResult(passed=len(errors) == 0, errors=errors, warnings=warnings)
    except Exception as exc:
        return PreflightResult(passed=False, errors=[str(exc)])


@router.put("/functional-cases/{case_id}")
def update_functional_case(
    case_id: int,
    payload: FunctionalCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    case = get_or_404(db, FunctionalCase, case_id)
    data = schema_data(payload, exclude_unset=True)
    for field in ["title", "precondition", "steps", "expected", "category", "priority", "automation_status"]:
        if field in data and data[field] is not None:
            setattr(case, field, data[field])
    db.commit()
    db.refresh(case)
    return serialize(case)


@router.put("/functional-cases/{case_id}/status")
def update_functional_case_status(
    case_id: int,
    payload: FunctionalCaseStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """更新单个用例的测试执行状态"""
    case = get_or_404(db, FunctionalCase, case_id)
    valid_statuses = {"untested", "passed", "failed", "blocked", "skipped", "needs_review"}
    if payload.test_result not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"无效的状态值，可选: {', '.join(sorted(valid_statuses))}")
    case.test_result = payload.test_result
    db.commit()
    db.refresh(case)
    return serialize(case)


@router.post("/functional-cases/{case_id}/generate-ui-steps")
def generate_functional_case_ui_steps(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    case = get_or_404(db, FunctionalCase, case_id)
    task = get_or_404(db, FunctionalTask, case.task_id)
    snapshot = db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).first()
    result = save_generated_functional_ui_steps(db, task, case, snapshot)
    db.commit()
    db.refresh(case)
    result["case"] = serialize(case)
    return result


# ─── Batch operations ──────────────────────────────────────────────────


@router.post("/functional-tasks/{task_id}/cases/batch-status")
def batch_update_functional_case_status(
    task_id: int,
    payload: FunctionalCaseBatchStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """批量更新用例的测试执行状态"""
    get_or_404(db, FunctionalTask, task_id)
    valid_statuses = {"untested", "passed", "failed", "blocked", "skipped", "needs_review"}
    if payload.test_result not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"无效的状态值，可选: {', '.join(sorted(valid_statuses))}")
    updated = (
        db.query(FunctionalCase)
        .filter(FunctionalCase.task_id == task_id, FunctionalCase.id.in_(payload.case_ids))
        .update({"test_result": payload.test_result}, synchronize_session="fetch")
    )
    db.commit()
    return {"updated": updated, "test_result": payload.test_result}


@router.get("/functional-tasks/{task_id}/cases/stats")
def get_functional_case_stats(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FunctionalCaseStats:
    """获取任务的用例状态统计"""
    get_or_404(db, FunctionalTask, task_id)
    total = db.query(FunctionalCase).filter(FunctionalCase.task_id == task_id).count()
    counts = {row[0]: row[1] for row in
              db.query(FunctionalCase.test_result, func.count(FunctionalCase.id))
              .filter(FunctionalCase.task_id == task_id)
              .group_by(FunctionalCase.test_result)
              .all()}
    return FunctionalCaseStats(
        total=total,
        untested=counts.get("untested", 0),
        passed=counts.get("passed", 0),
        failed=counts.get("failed", 0),
        blocked=counts.get("blocked", 0),
        skipped=counts.get("skipped", 0),
    )


@router.post("/functional-tasks/{task_id}/cases/batch-generate-ui-steps")
def batch_generate_functional_case_ui_steps(
    task_id: int,
    payload: FunctionalCaseBatchIds,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    query = db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id)
    requested_ids = list(dict.fromkeys(int(item) for item in (payload.case_ids or []) if int(item) > 0))
    if requested_ids:
        query = query.filter(FunctionalCase.id.in_(requested_ids))
    cases = query.order_by(FunctionalCase.id.asc()).all()
    if not cases:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可生成步骤的用例")
    snapshot = db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).first()
    results: list[Dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    for case in cases:
        try:
            result = save_generated_functional_ui_steps(db, task, case, snapshot)
            results.append(
                {
                    "case_id": case.id,
                    "title": case.title,
                    "status": "success",
                    "source": result.get("source"),
                    "warning": result.get("warning"),
                }
            )
            success_count += 1
        except Exception as exc:
            results.append({"case_id": case.id, "title": case.title, "status": "failed", "error": str(exc)})
            failed_count += 1
    db.commit()
    return {"total": len(cases), "success_count": success_count, "failed_count": failed_count, "results": results}


@router.post("/functional-tasks/{task_id}/cases/batch-automation-status")
def batch_update_functional_case_automation_status(
    task_id: int,
    payload: FunctionalCaseBatchAutomationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    get_or_404(db, FunctionalTask, task_id)
    valid_statuses = {"draft", "ui_steps_generated", "approved", "needs_review"}
    if payload.automation_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"无效的自动化状态，可选: {', '.join(sorted(valid_statuses))}")
    requested_ids = list(dict.fromkeys(int(item) for item in (payload.case_ids or []) if int(item) > 0))
    query = db.query(FunctionalCase).filter(FunctionalCase.task_id == task_id)
    if requested_ids:
        query = query.filter(FunctionalCase.id.in_(requested_ids))
    if payload.automation_status == "approved":
        query = query.filter(FunctionalCase.ui_case_id.isnot(None))
        query = query.filter(FunctionalCase.quality_status.in_([QUALITY_EXECUTABLE, QUALITY_UNCHECKED]))
    updated = query.update({"automation_status": payload.automation_status}, synchronize_session="fetch")
    db.commit()
    return {"updated": updated, "automation_status": payload.automation_status}


# ─── Screenshots ───────────────────────────────────────────────────────


@router.get("/functional-screenshots/{screenshot_id}/file")
def get_functional_screenshot_file(
    screenshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    screenshot = get_or_404(db, FunctionalScreenshot, screenshot_id)
    return safe_file_response(screenshot.image_path)


@router.post("/functional-screenshots/{screenshot_id}/analyze")
def analyze_uploaded_functional_screenshot(
    screenshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    screenshot = get_or_404(db, FunctionalScreenshot, screenshot_id)
    task = get_or_404(db, FunctionalTask, screenshot.task_id)
    try:
        screenshot.analysis_result = analyze_functional_screenshot(task, screenshot, latest_ai_config(db))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _assert_forward_status(task, "screenshot_analyzed")

    task.status = "screenshot_analyzed"
    db.commit()
    db.refresh(screenshot)
    return {"screenshot": serialize(screenshot), "task": functional_task_detail(db, task)}


# ─── Requirement notes ─────────────────────────────────────────────────


@router.post("/functional-tasks/{task_id}/requirement-notes")
def create_functional_requirement_note(
    task_id: int,
    payload: FunctionalRequirementNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    data = schema_data(payload)
    note_text = (data.get("note_text") or "").strip()
    if not note_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="补充需求不能为空")
    note = FunctionalRequirementNote(
        task_id=task.id,
        note_text=note_text,
        create_time=datetime.now(),
        update_time=None,
    )
    _assert_forward_status(task, "requirements_updated")

    task.status = "requirements_updated"
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"note": serialize(note), "task": functional_task_detail(db, task)}


@router.put("/functional-requirement-notes/{note_id}")
def update_functional_requirement_note(
    note_id: int,
    payload: FunctionalRequirementNoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    note = get_or_404(db, FunctionalRequirementNote, note_id)
    data = schema_data(payload)
    note_text = (data.get("note_text") or "").strip()
    if not note_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="补充需求不能为空")
    note.note_text = note_text
    note.update_time = datetime.now()
    db.commit()
    db.refresh(note)
    return serialize(note)


@router.delete("/functional-requirement-notes/{note_id}")
def delete_functional_requirement_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    note = get_or_404(db, FunctionalRequirementNote, note_id)
    db.delete(note)
    db.commit()
    return {"message": "deleted"}


# ─── Execution-related helpers ─────────────────────────────────────────


def save_generated_functional_ui_steps(
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


def can_execute_functional_case(
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


def execute_functional_case_for_run(
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


def execute_functional_case_for_run_isolated(
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


def save_functional_run(
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


# ─── Execution-related routes ──────────────────────────────────────────


BLOCKED_QUALITY_STATUSES = {QUALITY_AUTH_RISK, QUALITY_MISSING_VARIABLES, QUALITY_NOT_RECOMMENDED}
REVIEW_QUALITY_STATUSES = {QUALITY_NEEDS_REVIEW}


def _classify_functional_execution_result(passed: bool, log_text: str, quality_status: str | None) -> tuple[str, str]:
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


def _execution_event(event_type: str, **payload: Any) -> Dict[str, Any]:
    return {
        "type": event_type,
        "timestamp": datetime.now().isoformat(),
        **payload,
    }


def _save_functional_runtime_variables(task: FunctionalTask, variables: Dict[str, Any] | None) -> Dict[str, Any]:
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


def _functional_execution_payload(run: FunctionalRun) -> Dict[str, Any]:
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


def _repair_issue_type(record: Dict[str, Any], ui_log: Dict[str, Any]) -> str:
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


def _build_functional_repair_plan(run: FunctionalRun) -> Dict[str, Any]:
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


def _background_execute_functional(
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


@router.post("/functional-tasks/{task_id}/execute-async")
def execute_functional_task_async(
    task_id: int,
    payload: FunctionalExecuteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    execution_mode = (payload.execution_mode if payload else "trusted") or "trusted"
    force_execute = bool(payload.force) if payload else False
    if execution_mode == "trial":
        force_execute = True
    execution_policy = (payload.execution_policy if payload else "isolated_per_case") or "isolated_per_case"
    parallelism = max(1, min(int((payload.parallelism if payload else 1) or 1), 3))
    if execution_policy == "scenario_chain":
        parallelism = 1
    selected_case_ids: list[int] = []
    if payload:
        if payload.case_id:
            selected_case_ids = [payload.case_id]
        elif payload.case_ids:
            selected_case_ids = list(dict.fromkeys(int(item) for item in payload.case_ids if int(item) > 0))
    preflight_result = preflight_functional_package(db, task, payload, selected_case_ids or None, persist=True)
    seed_variables = dict((preflight_result.get("seed") or {}).get("variables") or {})
    variables = {**seed_variables, **(payload.variables if payload else {})}
    saved_runtime_variables = _save_functional_runtime_variables(task, payload.variables if payload and payload.save_variables else {})
    trusted_case_ids = [int(item) for item in preflight_result.get("trusted_case_ids") or preflight_result.get("executable_case_ids") or []]
    cases_query = db.query(FunctionalCase).filter(
        FunctionalCase.task_id == task.id,
        FunctionalCase.automation_status == "approved",
        FunctionalCase.ui_case_id.isnot(None),
    )
    if selected_case_ids:
        cases_query = cases_query.filter(FunctionalCase.id.in_(selected_case_ids))
    if force_execute:
        cases_query = cases_query.filter(
            FunctionalCase.quality_status.in_(
                [QUALITY_EXECUTABLE, QUALITY_UNCHECKED, QUALITY_NEEDS_REVIEW, QUALITY_LOCATOR_RISK]
            )
        )
    else:
        cases_query = cases_query.filter(FunctionalCase.quality_status == QUALITY_EXECUTABLE)
        if trusted_case_ids:
            cases_query = cases_query.filter(FunctionalCase.id.in_(trusted_case_ids))
    cases = cases_query.order_by(FunctionalCase.id.asc()).all()
    if not cases:
        counts = preflight_result.get("counts") or {}
        manual_count = counts.get("manual_check", 0)
        trial_count = preflight_result.get("trial_count", counts.get("trial_runnable", 0))
        detail = f"预检后没有高可信自动执行用例；可信可执行 {preflight_result.get('executable_count', 0)} 条，可试跑 {trial_count} 条"
        if manual_count:
            detail += f"，有 {manual_count} 条需要补数据、修定位或人工确认"
        if not force_execute and trial_count:
            detail += "；可切换到试跑风险用例模式继续执行"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    # 1) 先创建 run 记录，标记为 running
    initial_log = {
        "task_id": task.id,
        "task": task.iteration_name,
        "variables": {key: ("***" if "password" in str(key).lower() else value) for key, value in variables.items()},
        "records": [],
        "passed_count": 0,
        "failed_count": 0,
        "blocked_count": 0,
        "review_count": 0,
        "total": len(cases),
        "preflight": preflight_result,
        "saved_runtime_variables": saved_runtime_variables,
        "completed": 0,
        "active_case_id": None,
        "active_step_index": None,
        "active_step_name": "",
        "elapsed_ms": 0,
        "parallelism": parallelism,
        "execution_mode": execution_mode,
        "execution_policy": execution_policy,
        "events": [_execution_event("run_started", total=len(cases), parallelism=parallelism, execution_policy=execution_policy)],
        "current_case_title": "初始化执行器...",
    }
    run = FunctionalRun(
        task_id=task.id,
        result="running",
        log=json.dumps(initial_log, ensure_ascii=False, indent=2, default=str),
        passed_count=0,
        failed_count=0,
        execute_time=datetime.now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # 2) 后台线程执行
    run_id = run.id
    payload_data = schema_data(payload) if payload else {}
    payload_data["variables"] = variables
    payload_data["force"] = force_execute
    payload_data["parallelism"] = parallelism
    payload_data["execution_mode"] = execution_mode
    payload_data["execution_policy"] = execution_policy
    payload_case_id = payload_data.get("case_id") if payload_data else None
    payload_case_ids = payload_data.get("case_ids") if payload_data else []
    selected_bg_case_ids: list[int] = [case.id for case in cases]
    if payload_case_id:
        selected_bg_case_ids = [int(payload_case_id)]
    elif payload_case_ids:
        selected_bg_case_ids = list(dict.fromkeys(int(item) for item in payload_case_ids if int(item) > 0))

    thread = threading.Thread(
        target=_background_execute_functional,
        args=(task_id, run_id, payload_data, selected_bg_case_ids, variables),
        daemon=True,
    )
    thread.start()

    return {
        "job_id": run.id,
        "status": "running",
        "total": len(cases),
        "completed": 0,
        "active_case_id": None,
        "active_step_index": None,
        "active_step_name": "",
        "elapsed_ms": 0,
        "parallelism": parallelism,
        "execution_mode": execution_mode,
        "execution_policy": execution_policy,
        "events": [_execution_event("run_started", total=len(cases), parallelism=parallelism, execution_policy=execution_policy)],
        "passed_count": 0,
        "failed_count": 0,
        "blocked_count": 0,
        "review_count": 0,
        "current_case_title": "启动中...",
        "records": [],
        "task_name": task.iteration_name,
    }


@router.get("/functional-executions/{job_id}")
def get_functional_execution(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    run = get_or_404(db, FunctionalRun, job_id)
    return _functional_execution_payload(run)


@router.get("/functional-executions/{job_id}/events")
def stream_functional_execution_events(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    get_or_404(db, FunctionalRun, job_id)

    def event_stream():
        from ..database import SessionLocal

        sent_count = 0
        while True:
            stream_db = SessionLocal()
            try:
                run = stream_db.get(FunctionalRun, job_id)
                if not run:
                    yield "event: error\ndata: {\"error\":\"run_not_found\"}\n\n"
                    break
                payload = _functional_execution_payload(run)
                events = payload.get("events") or []
                for event in events[sent_count:]:
                    yield "event: execution\ndata: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"
                sent_count = len(events)
                yield "event: snapshot\ndata: " + json.dumps(payload, ensure_ascii=False, default=str) + "\n\n"
                if run.result in {"passed", "failed", "blocked", "needs_review", "error"}:
                    break
            finally:
                stream_db.close()
            time.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/functional-runs/{run_id}/diagnose")
def diagnose_functional_run(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    run = get_or_404(db, FunctionalRun, run_id)
    diagnosis = diagnose_failure(run, latest_ai_config(db))
    try:
        payload = json.loads(run.log or "{}")
    except json.JSONDecodeError:
        payload = {"log": run.log or ""}
    payload["diagnosis"] = diagnosis
    run.log = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    db.commit()
    db.refresh(run)
    return {"run": serialize(run), "diagnosis": diagnosis}


@router.post("/functional-runs/{run_id}/repair-plan")
def functional_run_repair_plan(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    run = get_or_404(db, FunctionalRun, run_id)
    plan = _build_functional_repair_plan(run)
    try:
        payload = json.loads(run.log or "{}")
    except json.JSONDecodeError:
        payload = {"log": run.log or ""}
    payload["repair_plan"] = plan
    run.log = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    db.commit()
    return plan


@router.post("/functional-runs/{run_id}/apply-repair")
def apply_functional_run_repair(
    run_id: int,
    payload: Dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    run = get_or_404(db, FunctionalRun, run_id)
    plan = _build_functional_repair_plan(run)
    selected_ids = {int(item) for item in (payload or {}).get("functional_case_ids", []) if str(item).isdigit()}
    applied: list[Dict[str, Any]] = []
    skipped: list[Dict[str, Any]] = []
    for item in plan.get("repair_items", []):
        if selected_ids and int(item.get("functional_case_id") or 0) not in selected_ids:
            continue
        if not item.get("auto_fixable") or item.get("fix_type") != "locator":
            skipped.append({"functional_case_id": item.get("functional_case_id"), "reason": "not_auto_fixable"})
            continue
        ui_case = db.get(UiCase, int(item.get("ui_case_id") or 0))
        if not ui_case:
            skipped.append({"functional_case_id": item.get("functional_case_id"), "reason": "ui_case_not_found"})
            continue
        steps = parse_json_value(ui_case.steps, [])
        if not isinstance(steps, list):
            steps = []
        changed = 0
        for step in steps:
            if not isinstance(step, dict):
                continue
            for update in item.get("locator_updates") or []:
                if step.get("locator") == update.get("original_locator"):
                    step["locator"] = update.get("suggested_locator")
                    step["healed_at"] = datetime.now().isoformat()
                    step["healed_from_run_id"] = run_id
                    changed += 1
        if changed:
            ui_case.steps = to_json_text(steps, [])
            applied.append({"functional_case_id": item.get("functional_case_id"), "ui_case_id": ui_case.id, "updated_count": changed})
    if applied:
        db.commit()
    return {
        "run_id": run_id,
        "applied": applied,
        "skipped": skipped,
        "applied_count": sum(item.get("updated_count", 0) for item in applied),
        "rerun_case_ids": [item["functional_case_id"] for item in applied if item.get("functional_case_id")],
    }


@router.post("/functional-runs/{run_id}/heal")
def heal_functional_run_steps(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """从执行日志提取 healed locator，批量更新关联 UI 用例"""
    run = get_or_404(db, FunctionalRun, run_id)
    run_log = parse_json_value(run.log, {})
    records = run_log.get("records") if isinstance(run_log.get("records"), list) else []
    heal_map: Dict[str, str] = {}
    updated_cases: list[int] = []

    for record in records:
        if not isinstance(record, dict):
            continue
        ui_log = parse_json_value(record.get("log"), {})
        step_logs = ui_log.get("step_logs") if isinstance(ui_log.get("step_logs"), list) else []
        for step in step_logs:
            if isinstance(step, dict) and step.get("healed") and step.get("original_locator") and step.get("suggested_locator"):
                old_loc = step.get("original_locator")
                new_loc = step.get("suggested_locator")
                if old_loc and new_loc and old_loc != new_loc:
                    heal_map[old_loc] = new_loc
        case_id = record.get("ui_case_id") or ui_log.get("ui_case_id") or ui_log.get("case_id")
        if case_id and heal_map:
            try:
                case = db.get(UiCase, case_id)
                if case:
                    current_steps = parse_json_value(case.steps, [])
                    updated = 0
                    for step in current_steps:
                        if isinstance(step, dict):
                            step_locator = step.get("locator", "")
                            for old_loc, new_loc in heal_map.items():
                                if step_locator == old_loc:
                                    step["locator"] = new_loc
                                    step["healed_at"] = datetime.now().isoformat()
                                    updated += 1
                    if updated:
                        case.steps = to_json_text(current_steps, [])
                        updated_cases.append(case.id)
            except Exception:
                continue

    if updated_cases:
        db.commit()

    return {
        "heal_map": heal_map,
        "updated_cases": updated_cases,
        "updated_count": len(heal_map),
    }


@router.get("/functional-runs/{run_id}/timeline")
def get_functional_run_timeline(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    聚合一次执行记录的结构化时间线数据。
    返回值结构：
    {
      "run_id": int,
      "status": "passed"|"failed"|"running",
      "passed_count": int,
      "failed_count": int,
      "summary": str,
      "diagnosis": { ... } | None,   # 已诊断时存在
      "cases": [
        {
          "case_id": int,
          "title": str,
          "result": "passed"|"failed",
          "screenshot": str,          # 最终截图
          "steps": [
            {
              "index": 1,
              "name": str,
              "action": str,
              "locator": str,
              "value": str,
              "status": "passed"|"failed"|"skipped",
              "url_before": str,
              "url_after": str,
              "screenshot_before": str | None,
              "screenshot_after": str | None,
              "screenshot_failure": str | None,
              "error": str | None,
              "category": str | None,
              "reason": str | None,
              "suggestion": str | None,
              "healed": bool,
              "original_locator": str,
              "suggested_locator": str,
              "duration_ms": int,
            },
            ...
          ]
        },
        ...
      ]
    }
    """
    run = get_or_404(db, FunctionalRun, run_id)
    run_log = parse_json_value(run.log, {})
    records = run_log.get("records") if isinstance(run_log.get("records"), list) else []
    diagnosis = parse_json_value(run_log.get("diagnosis", ""), None)
    passed_count = run_log.get("passed_count", run.passed_count or 0)
    failed_count = run_log.get("failed_count", run.failed_count or 0)

    cases_timeline = []
    for record in records:
        if not isinstance(record, dict):
            continue
        title = record.get("title") or "未知用例"
        case_id = record.get("functional_case_id")
        result = record.get("result", "unknown")
        screenshot = record.get("screenshot") or ""

        ui_log = parse_json_value(record.get("log"), {})
        step_logs = ui_log.get("step_logs") if isinstance(ui_log.get("step_logs"), list) else []

        steps = []
        for step in step_logs:
            if not isinstance(step, dict):
                continue
            steps.append({
                "index": step.get("index", 0),
                "name": step.get("name", ""),
                "action": step.get("action", ""),
                "locator": step.get("locator", ""),
                "value": step.get("value", ""),
                "status": step.get("status", "unknown"),
                "url_before": step.get("current_url_before", ""),
                "url_after": step.get("current_url_after", ""),
                "screenshot_before": step.get("before_screenshot") or "",
                "screenshot_after": step.get("after_screenshot") or "",
                "screenshot_failure": step.get("failure_screenshot") or "",
                "error": step.get("error") or "",
                "category": step.get("category") or "",
                "reason": step.get("reason") or "",
                "suggestion": step.get("suggestion") or "",
                "healed": bool(step.get("healed")),
                "original_locator": step.get("original_locator") or "",
                "suggested_locator": step.get("suggested_locator") or "",
                "duration_ms": step.get("duration_ms", 0),
            })

        cases_timeline.append({
            "case_id": case_id,
            "title": title,
            "result": result,
            "screenshot": screenshot,
            "steps": steps,
        })

    passed = run_log.get("passed_count", run.passed_count or 0)
    failed = run_log.get("failed_count", run.failed_count or 0)
    blocked = run_log.get("blocked_count", 0)
    review = run_log.get("review_count", 0)
    summary = f"本次执行通过 {passed} 条，失败 {failed} 条，阻断 {blocked} 条，需确认 {review} 条。"

    return {
        "run_id": run.id,
        "status": run.result,
        "passed_count": passed,
        "failed_count": failed,
        "blocked_count": blocked,
        "review_count": review,
        "summary": summary,
        "diagnosis": diagnosis,
        "cases": cases_timeline,
    }
