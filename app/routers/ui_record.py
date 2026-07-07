from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.utils import ensure_project_exists, serialize
from ..database import get_db
from ..executors import to_json_text
from ..models import UiCase, User
from ..security import require_admin
from ..services import ui_recording_session

router = APIRouter(prefix="/api/ui-record", tags=["ui-record"])


def _required_text(payload: Dict[str, Any], field: str, label: str) -> str:
    value = str(payload.get(field) or "").strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label}不能为空")
    return value


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
    try:
        session_id = await ui_recording_session.start_session(project_id, case_name, start_url, getattr(current_user, "id", None))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"浏览器启动失败: {exc}") from exc
    return {
        "session_id": session_id,
        "status": "recording",
        "project_id": project_id,
        "case_name": case_name,
        "start_url": start_url,
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


@router.post("/sessions/{session_id}/save")
async def save_ui_record_session(
    session_id: str,
    payload: Dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    assertion_text = str(data.get("assertion_text") or "").strip()
    try:
        session_state = ui_recording_session.get_session_state(session_id, assertion_text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    ui_case = UiCase(
        project_id=int(session_state["project_id"]),
        case_name=str(session_state["case_name"]),
        page_url=str(session_state["start_url"]),
        steps=to_json_text(session_state.get("preview_steps") or [], []),
        timeout=30,
        status="draft",
        create_time=datetime.now(),
    )
    db.add(ui_case)
    db.commit()
    db.refresh(ui_case)
    await ui_recording_session.close_session(session_id)
    return {
        "case": serialize(ui_case),
        "steps": session_state.get("preview_steps") or [],
        "event_count": session_state.get("count") or 0,
    }


@router.delete("/sessions/{session_id}")
async def cancel_ui_record_session(
    session_id: str,
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    await ui_recording_session.close_session(session_id)
    return {"ok": True}
