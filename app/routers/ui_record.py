import json

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.utils import (
    decrypt_account_payload,
    encrypt_account_payload,
    ensure_project_exists,
    save_test_account_binding,
    serialize,
)
from ..database import get_db
from ..executors import to_json_text
from ..models import TestAccountProfile, UiCase, UiRecordPreflight, User
from ..security import require_admin
from ..services import ui_recording_session
from ..services.ui_recording_config import get_recording_config, save_recording_config, serialize_recording_config
from ..services.ui_recording_verification import launch_verification, request_repick, restart_verification
from ..services.ui_recording_preflight import (
    create_preflight,
    initialize_preflight_report,
    determine_recorded_case_status,
    launch_legacy_preflight,
    preflight_matches_steps,
    serialize_preflight,
)

router = APIRouter(prefix="/api/ui-record", tags=["ui-record"])


def _required_text(payload: Dict[str, Any], field: str, label: str) -> str:
    value = str(payload.get(field) or "").strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label}不能为空")
    return value


def _recording_account_profile(db: Session, raw_profile_id: Any, project_id: int) -> TestAccountProfile | None:
    if raw_profile_id in (None, ""):
        return None
    try:
        profile_id = int(raw_profile_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="测试账号无效")
    profile = db.get(TestAccountProfile, profile_id)
    if not profile or profile.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择有效的测试账号")
    if profile.project_id not in {None, project_id}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="测试账号不属于当前项目")
    return profile


@router.get("/projects/{project_id}/config")
def get_ui_record_project_config(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    ensure_project_exists(db, project_id)
    return serialize_recording_config(db, project_id)


@router.put("/projects/{project_id}/config")
def put_ui_record_project_config(
    project_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        save_recording_config(db, project_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return serialize_recording_config(db, project_id)


@router.post("/sessions")
async def create_ui_record_session(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        project_id = int(payload.get("project_id") or 0)
    except (TypeError, ValueError):
        project_id = 0
    if project_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="项目不能为空")
    case_name = _required_text(payload, "case_name", "用例名称")
    start_url = _required_text(payload, "start_url", "起始URL")
    ensure_project_exists(db, project_id)
    profile = _recording_account_profile(db, payload.get("account_profile_id"), project_id)
    stored = decrypt_account_payload(profile.browser_state_encrypted) if profile else {}
    storage_state = stored.get("storage_state") if isinstance(stored, dict) else None
    try:
        session_id = await ui_recording_session.start_session(
            project_id,
            case_name,
            start_url,
            user_id=getattr(current_user, "id", None),
            storage_state=storage_state if isinstance(storage_state, dict) else None,
            account_profile_id=profile.id if profile else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"浏览器启动失败: {exc}") from exc
    return {
        "session_id": session_id,
        "status": "recording",
        "project_id": project_id,
        "case_name": case_name,
        "start_url": start_url,
        "account_profile_id": profile.id if profile else None,
    }


@router.get("/sessions/{session_id}/events")
def list_ui_record_events(
    session_id: str,
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return ui_recording_session.get_session_state(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/preflight")
async def start_ui_record_preflight(
    session_id: str,
    payload: Dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    assertion_text = str(data.get("assertion_text") or "").strip()
    try:
        session_state = ui_recording_session.get_session_state(session_id, assertion_text)
        storage_state = await ui_recording_session.get_session_storage_state(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    steps = session_state.get("preview_steps") or []
    row = create_preflight(
        db,
        session_id=session_id,
        project_id=int(session_state["project_id"]),
        steps=steps,
        assertion_text=assertion_text,
    )
    project_config = get_recording_config(db, int(session_state["project_id"]))
    if project_config is not None:
        config_snapshot = serialize_recording_config(db, int(session_state["project_id"])).get("config")
        initialize_preflight_report(row, "verified", 2, config_snapshot if isinstance(config_snapshot, dict) else None)
        db.commit()
        launch_verification(
            row,
            case_data={
                "case_name": session_state["case_name"],
                "page_url": session_state["start_url"],
                "steps": steps,
                "timeout": 30,
            },
            storage_state=storage_state,
        )
    else:
        initialize_preflight_report(row, "legacy", 1)
        db.commit()
        launch_legacy_preflight(
            row,
            case_data={
                "case_name": session_state["case_name"],
                "page_url": session_state["start_url"],
                "steps": steps,
                "timeout": 30,
            },
            storage_state=storage_state,
        )
    return serialize_preflight(row)


@router.get("/preflights/{run_id}")
def get_ui_record_preflight(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(UiRecordPreflight, run_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="录制预检不存在")
    return serialize_preflight(row)




@router.post("/preflights/{run_id}/steps/{step_index}/repick/start")
def start_ui_record_repick(
    run_id: str,
    step_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(UiRecordPreflight, run_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="录制预检不存在")
    if row.status != "repair_required":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前状态不允许重新选点")
    try:
        report = json.loads(row.report_json or "{}")
    except (TypeError, ValueError):
        report = {}
    repair = report.get("repair") if isinstance(report.get("repair"), dict) else {}
    failed_index = repair.get("failed_step_index")
    if failed_index is None or int(failed_index) != int(step_index):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能重新选择当前失败步骤")
    try:
        repick_result = request_repick(run_id, int(step_index))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {**serialize_preflight(row), "repick": repick_result}


@router.post("/preflights/{run_id}/restart")
async def restart_ui_record_preflight(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    row = db.get(UiRecordPreflight, run_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="录制预检不存在")
    if row.status not in {"repair_ready", "failed"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前状态不允许重新检查")
    try:
        session_state = ui_recording_session.get_session_state(row.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    steps = session_state.get("preview_steps") or []
    storage_state = await ui_recording_session.get_session_storage_state(row.session_id)
    restart_verification(
        db,
        row,
        case_data={
            "case_name": session_state["case_name"],
            "page_url": session_state["start_url"],
            "steps": steps,
            "timeout": 30,
        },
        storage_state=storage_state,
    )
    try:
        report = json.loads(row.report_json or "{}")
    except (TypeError, ValueError):
        report = {}
    new_run_id = report.get("restarted_run_id") if isinstance(report, dict) else None
    new_row = db.get(UiRecordPreflight, new_run_id) if new_run_id else None
    return serialize_preflight(new_row) if new_row else serialize_preflight(row)
@router.post("/sessions/{session_id}/steps/{step_index}/locator")
def override_ui_record_step_locator(
    session_id: str,
    step_index: int,
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return ui_recording_session.override_session_step_locator(
            session_id,
            step_index,
            str(payload.get("locator") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/save")
async def save_ui_record_session(
    session_id: str,
    payload: Dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    assertion_text = str(data.get("assertion_text") or "").strip()
    preflight_run_id = str(data.get("preflight_run_id") or "").strip()
    try:
        session_state = ui_recording_session.get_session_state(session_id, assertion_text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    account_profile_id = session_state.get("account_profile_id")
    profile = _recording_account_profile(db, account_profile_id, int(session_state["project_id"]))
    storage_state = await ui_recording_session.get_session_storage_state(session_id)
    if profile and storage_state:
        profile.browser_state_encrypted = encrypt_account_payload({"storage_state": storage_state})
        profile.browser_session_status = "valid"
        profile.browser_session_validated_at = datetime.now()
        profile.update_time = datetime.now()

    steps = session_state.get("preview_steps") or []
    preflight = db.get(UiRecordPreflight, preflight_run_id) if preflight_run_id else None
    if preflight_run_id and (
        not preflight
        or preflight.session_id != session_id
        or int(preflight.project_id) != int(session_state["project_id"])
        or not preflight_matches_steps(preflight, steps)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="预检结果与当前录制会话不匹配")
    preflight_report: dict[str, Any] | None = None
    if preflight:
        try:
            preflight_report = json.loads(preflight.report_json or "{}")
        except (TypeError, ValueError):
            preflight_report = {}
    case_status = determine_recorded_case_status(preflight.status if preflight else "", steps, preflight_report)

    ui_case = UiCase(
        project_id=int(session_state["project_id"]),
        case_name=str(session_state["case_name"]),
        page_url=str(session_state["start_url"]),
        steps=to_json_text(steps, []),
        timeout=30,
        status=case_status,
        create_time=datetime.now(),
    )
    db.add(ui_case)
    db.flush()
    if preflight:
        preflight.case_id = ui_case.id
        preflight.update_time = datetime.now()
    if profile:
        save_test_account_binding(db, "ui_case", ui_case.id, profile.id)
    db.commit()
    db.refresh(ui_case)
    await ui_recording_session.close_session(session_id)
    return {
        "case": serialize(ui_case),
        "steps": session_state.get("preview_steps") or [],
        "event_count": session_state.get("count") or 0,
        "quality_status": "executable" if case_status == "active" else "needs_review",
        "preflight": serialize_preflight(preflight) if preflight else None,
    }


@router.delete("/sessions/{session_id}")
async def cancel_ui_record_session(
    session_id: str,
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    await ui_recording_session.close_session(session_id)
    return {"ok": True}
