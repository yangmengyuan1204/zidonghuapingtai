"""UI 用例路由"""
import copy
import json
from pathlib import Path
import re
import threading
from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.utils import (
    serialize, serialize_many, get_or_404, schema_data,
    normalize_json_fields, ensure_project_exists,
    account_profile_summary, resolve_execution_account, save_ui_record,
)
from ..database import SessionLocal, get_db
from ..executors import execute_ui_case, parse_json_value, to_json_text
from ..models import (
    UiCase, TestAccountBinding, TestAccountProfile, TestRecord,
    LocatorHealLog, User,
)
from ..schemas import UiCaseCreate, UiCaseUpdate, FunctionalExecuteRequest
from ..security import get_current_user, require_admin

router = APIRouter(tags=["ui-cases"])

_VISUAL_EXECUTIONS: dict[str, Dict[str, Any]] = {}
_VISUAL_EXECUTIONS_LOCK = threading.Lock()
_SENSITIVE_VISUAL_KEY_RE = re.compile(r"(password|passwd|pwd|captcha|token|secret|authorization|auth|验证码|密码)", re.I)
_REPORTS_DIR = Path(__file__).resolve().parents[2] / "reports"


def _visual_screenshot_url(path: Any) -> str:
    if not path:
        return ""
    try:
        screenshot_path = Path(str(path)).resolve()
        rel = screenshot_path.relative_to(_REPORTS_DIR.resolve())
        return "/reports/" + rel.as_posix()
    except Exception:
        return ""


def _latest_visual_screenshot(detail: Dict[str, Any] | None) -> str:
    if not isinstance(detail, dict):
        return ""
    for key in ("failure_screenshot", "after_screenshot", "screenshot", "retry_confirmation_screenshot", "before_screenshot"):
        value = detail.get(key)
        if value:
            return str(value)
    return ""


def _visual_safe(value: Any, key: str = "") -> Any:
    if _SENSITIVE_VISUAL_KEY_RE.search(str(key or "")):
        return "***"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _visual_safe(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_visual_safe(item, key) for item in value]
    if isinstance(value, tuple):
        return [_visual_safe(item, key) for item in value]
    if isinstance(value, str) and len(value) > 1200:
        return value[:1200] + "...(truncated)"
    return value


def _visual_step_summary(step: Dict[str, Any], index: int) -> Dict[str, Any]:
    return {
        "index": index,
        "name": step.get("name") or step.get("action") or f"step-{index}",
        "action": step.get("action") or "",
        "locator": step.get("locator") or "",
        "value": _visual_safe(step.get("value"), "value"),
        "status": "queued",
    }


def _update_visual_execution(run_id: str, payload: Dict[str, Any]) -> None:
    payload = _visual_safe(payload)
    with _VISUAL_EXECUTIONS_LOCK:
        run = _VISUAL_EXECUTIONS.get(run_id)
        if not run:
            return
        run["updated_at"] = datetime.now().isoformat(sep=" ", timespec="seconds")
        events = run.setdefault("events", [])
        events.append(payload)
        if len(events) > 120:
            del events[:-120]
        event = payload.get("event")
        if event == "prepared":
            steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
            run["steps"] = [
                _visual_step_summary(step if isinstance(step, dict) else {"raw": step}, index)
                for index, step in enumerate(steps, start=1)
            ]
            run["validation_issues"] = payload.get("validation_issues") or []
        elif event == "step_start":
            index = int(payload.get("index") or 0)
            run["status"] = "running"
            run["current_step_index"] = index
            for step in run.get("steps", []):
                if step.get("index") == index:
                    step["status"] = "running"
        elif event == "step_finish":
            index = int(payload.get("index") or 0)
            detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}
            for step in run.get("steps", []):
                if step.get("index") == index:
                    step.update(
                        {
                            "status": payload.get("status") or detail.get("status") or "passed",
                            "duration_ms": detail.get("duration_ms"),
                            "error": detail.get("error") or "",
                            "category": detail.get("category") or "",
                            "reason": detail.get("reason") or "",
                            "suggestion": detail.get("suggestion") or "",
                            "used_locator": detail.get("used_locator") or "",
                            "extracted": detail.get("extracted") or {},
                        }
                    )
            screenshot = _latest_visual_screenshot(detail)
            if screenshot:
                run["latest_screenshot"] = screenshot
                run["latest_screenshot_url"] = _visual_screenshot_url(screenshot)
            if isinstance(payload.get("extracted_vars"), dict):
                run["extracted_vars"] = payload["extracted_vars"]
        elif event == "finished":
            status_value = payload.get("status") or "failed"
            run["status"] = "passed" if status_value == "passed" else "failed"
            run["error"] = payload.get("error") or ""
            run["verification_issues"] = payload.get("verification_issues") or []
            if isinstance(payload.get("extracted_vars"), dict):
                run["extracted_vars"] = payload["extracted_vars"]
            screenshot = payload.get("screenshot") or ""
            if screenshot:
                run["latest_screenshot"] = screenshot
                run["latest_screenshot_url"] = _visual_screenshot_url(screenshot)


def _finish_visual_execution(run_id: str, record: TestRecord | None = None, error: str = "") -> None:
    with _VISUAL_EXECUTIONS_LOCK:
        run = _VISUAL_EXECUTIONS.get(run_id)
        if not run:
            return
        if record:
            run["record"] = serialize(record)
            run["record_id"] = record.id
            run["status"] = record.result
            if record.screenshot:
                run["latest_screenshot"] = record.screenshot
                run["latest_screenshot_url"] = _visual_screenshot_url(record.screenshot)
            try:
                log_data = json.loads(record.log or "{}")
                if isinstance(log_data, dict):
                    run["extracted_vars"] = log_data.get("extracted_vars") or run.get("extracted_vars") or {}
                    run["final_url"] = log_data.get("current_url") or log_data.get("page_url") or ""
                    run["summary"] = {
                        "verification_status": log_data.get("verification_status"),
                        "business_verification": log_data.get("business_verification"),
                        "verification_issues": log_data.get("verification_issues") or [],
                    }
            except Exception:
                pass
        elif error:
            run["status"] = "failed"
            run["error"] = error
        run["finished_at"] = datetime.now().isoformat(sep=" ", timespec="seconds")


def _visual_case_copy(case: UiCase) -> UiCase:
    return UiCase(
        id=case.id,
        project_id=case.project_id,
        case_name=case.case_name,
        page_url=case.page_url,
        steps=case.steps,
        timeout=case.timeout,
        status=case.status,
        create_time=case.create_time,
    )


def _run_visual_ui_case_background(
    run_id: str,
    case: UiCase,
    variables: Dict[str, Any],
    execution_context: Dict[str, Any],
) -> None:
    bg_db = SessionLocal()
    try:
        _update_visual_execution(run_id, {"event": "started", "status": "running", "case_name": case.case_name, "page_url": case.page_url})
        passed, log_text, screenshot_path, report_path = execute_ui_case(
            case,
            variables,
            execution_context,
            db_session=bg_db,
            progress_callback=lambda event: _update_visual_execution(run_id, event),
        )
        record = save_ui_record(bg_db, case, passed, log_text, report_path, screenshot_path)
        _finish_visual_execution(run_id, record=record)
    except Exception as exc:
        _update_visual_execution(run_id, {"event": "finished", "status": "failed", "error": str(exc)})
        _finish_visual_execution(run_id, error=str(exc))
    finally:
        bg_db.close()


@router.get("/api/ui-cases")
def list_ui_cases(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(UiCase)
    if project_id is not None:
        query = query.filter(UiCase.project_id == project_id)
    cases = query.order_by(UiCase.id.desc()).all()
    if not cases:
        return []

    case_ids = [c.id for c in cases]
    project_ids = list({c.project_id for c in cases})

    # 批量加载 ui_case 级别的绑定
    ui_bindings: dict[int, int | None] = {}
    for row in (
        db.query(TestAccountBinding.target_id, TestAccountBinding.account_profile_id)
        .filter(
            TestAccountBinding.target_type == "ui_case",
            TestAccountBinding.target_id.in_(case_ids),
        )
        .all()
    ):
        ui_bindings[row[0]] = row[1]

    # 批量加载 project 级别的绑定（用作兜底）
    proj_bindings: dict[int, int | None] = {}
    for row in (
        db.query(TestAccountBinding.target_id, TestAccountBinding.account_profile_id)
        .filter(
            TestAccountBinding.target_type == "project",
            TestAccountBinding.target_id.in_(project_ids),
        )
        .all()
    ):
        proj_bindings[row[0]] = row[1]

    # 收集所有 profile ID 一次加载
    all_profile_ids: set[int] = set()
    for pid in ui_bindings.values():
        if pid is not None:
            all_profile_ids.add(pid)
    for pid in proj_bindings.values():
        if pid is not None:
            all_profile_ids.add(pid)
    profiles: dict[int, TestAccountProfile] = {}
    if all_profile_ids:
        for p in db.query(TestAccountProfile).filter(TestAccountProfile.id.in_(list(all_profile_ids))).all():
            profiles[p.id] = p

    # 兜底：项目中仅有一条有效账号时自动使用
    fallback_profile: dict[int, TestAccountProfile] = {}
    for proj_id in project_ids:
        projs = (
            db.query(TestAccountProfile)
            .filter(TestAccountProfile.project_id == proj_id, TestAccountProfile.status == "active")
            .order_by(TestAccountProfile.id.asc())
            .all()
        )
        if len(projs) == 1:
            fallback_profile[proj_id] = projs[0]

    result = []
    for case in cases:
        item = serialize(case)
        profile: TestAccountProfile | None = None
        # 优先 ui_case 级别绑定
        pid = ui_bindings.get(case.id)
        if pid is not None and pid in profiles:
            profile = profiles[pid]
        # 其次 project 级别绑定
        if not profile:
            pid = proj_bindings.get(case.project_id)
            if pid is not None and pid in profiles:
                profile = profiles[pid]
        # 最后兜底
        if not profile and case.project_id in fallback_profile:
            profile = fallback_profile[case.project_id]
        item.update(account_profile_summary(profile))
        result.append(item)
    return result


@router.post("/api/ui-cases")
def create_ui_case(
    payload: UiCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = normalize_json_fields(schema_data(payload))
    ensure_project_exists(db, data["project_id"])
    case = UiCase(**data, create_time=datetime.now())
    db.add(case)
    db.commit()
    db.refresh(case)
    return serialize(case)


@router.put("/api/ui-cases/{case_id}")
def update_ui_case(
    case_id: int,
    payload: UiCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    case = get_or_404(db, UiCase, case_id)
    data = normalize_json_fields(schema_data(payload, exclude_unset=True))
    if "project_id" in data:
        ensure_project_exists(db, data["project_id"])
    for field, value in data.items():
        setattr(case, field, value)
    db.commit()
    db.refresh(case)
    return serialize(case)


@router.delete("/api/ui-cases/{case_id}")
def delete_ui_case(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, str]:
    case = get_or_404(db, UiCase, case_id)
    # 清理关联记录
    db.query(TestRecord).filter(TestRecord.case_type == "ui", TestRecord.case_id == case.id).delete(synchronize_session=False)
    db.query(LocatorHealLog).filter(LocatorHealLog.case_id == case.id).delete(synchronize_session=False)
    db.query(TestAccountBinding).filter(TestAccountBinding.target_type == "ui_case", TestAccountBinding.target_id == case.id).delete(synchronize_session=False)
    db.delete(case)
    db.commit()
    return {"message": "deleted"}


@router.post("/api/ui-cases/{case_id}/heal-steps")
def heal_ui_case_steps(
    case_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """接受执行日志中的 healing 建议，更新用例的 locator"""
    case = get_or_404(db, UiCase, case_id)
    heal_map = payload.get("heal_map")
    if not isinstance(heal_map, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="heal_map 必须是对象")
    current_steps = parse_json_value(case.steps, [])
    if not isinstance(current_steps, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用例步骤格式不正确")
    updated_count = 0
    for step in current_steps:
        if not isinstance(step, dict):
            continue
        step_locator = step.get("locator", "")
        for old_locator, new_locator in heal_map.items():
            if step_locator == old_locator:
                step["locator"] = new_locator
                step["healed_at"] = datetime.now().isoformat()
                updated_count += 1
    if updated_count:
        case.steps = to_json_text(current_steps, [])
        db.commit()
        db.refresh(case)
    return {"updated_count": updated_count, "case": serialize(case)}


@router.post("/api/ui-cases/{case_id}/execute")
def run_ui_case(
    case_id: int,
    payload: FunctionalExecuteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    case = get_or_404(db, UiCase, case_id)
    variables, execution_context = resolve_execution_account(db, payload, "ui_case", case.id, case.project_id, case.page_url)
    passed, log_text, screenshot_path, report_path = execute_ui_case(case, variables, execution_context, db_session=db)
    record = save_ui_record(db, case, passed, log_text, report_path, screenshot_path)
    return serialize(record)


@router.post("/api/ui-cases/{case_id}/visual-execute")
def start_visual_ui_case(
    case_id: int,
    payload: Dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    case = get_or_404(db, UiCase, case_id)
    payload_data = payload if isinstance(payload, dict) else {}
    execute_payload = FunctionalExecuteRequest(**payload_data)
    variables, execution_context = resolve_execution_account(db, execute_payload, "ui_case", case.id, case.project_id, case.page_url)
    execution_context = dict(execution_context or {})
    execution_context["headed"] = payload_data.get("headed", True) is not False
    execution_context["visual_execution"] = True

    raw_steps = parse_json_value(case.steps, [])
    steps = raw_steps if isinstance(raw_steps, list) else []
    run_id = uuid4().hex
    now_text = datetime.now().isoformat(sep=" ", timespec="seconds")
    with _VISUAL_EXECUTIONS_LOCK:
        _VISUAL_EXECUTIONS[run_id] = {
            "run_id": run_id,
            "case_id": case.id,
            "case_name": case.case_name,
            "page_url": case.page_url,
            "status": "queued",
            "current_step_index": 0,
            "steps": [
                _visual_step_summary(step if isinstance(step, dict) else {"raw": step}, index)
                for index, step in enumerate(steps, start=1)
            ],
            "events": [],
            "extracted_vars": {},
            "latest_screenshot": "",
            "latest_screenshot_url": "",
            "created_at": now_text,
            "updated_at": now_text,
            "headed": execution_context["headed"],
        }
        if len(_VISUAL_EXECUTIONS) > 50:
            oldest = sorted(_VISUAL_EXECUTIONS.items(), key=lambda item: item[1].get("created_at", ""))[:10]
            for old_id, old_run in oldest:
                if old_run.get("status") in {"passed", "failed", "error"}:
                    _VISUAL_EXECUTIONS.pop(old_id, None)

    thread = threading.Thread(
        target=_run_visual_ui_case_background,
        args=(run_id, _visual_case_copy(case), variables, execution_context),
        daemon=True,
    )
    thread.start()
    with _VISUAL_EXECUTIONS_LOCK:
        return copy.deepcopy(_VISUAL_EXECUTIONS[run_id])


@router.get("/api/ui-executions/{run_id}")
def get_visual_ui_execution(
    run_id: str,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    with _VISUAL_EXECUTIONS_LOCK:
        run = _VISUAL_EXECUTIONS.get(run_id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行任务不存在或已过期")
        return copy.deepcopy(run)
