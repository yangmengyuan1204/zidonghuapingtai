from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..agent_schemas import (
    DataAgentGoalUpdate,
    DataAgentPermissionResume,
    DataAgentSessionConfirm,
    DataAgentSessionCreate,
    DataAgentSessionMessage,
)
from ..database import get_db
from ..models import User
from ..security import require_admin
from ..services.data_factory_agent import (
    add_agent_message,
    cancel_agent_session,
    confirm_agent_session,
    create_agent_session,
    get_agent_session,
    resume_agent_permission,
    update_agent_goal,
)

router = APIRouter(prefix="/api/data-scripts/agent", tags=["data-agent"])


@router.post("/sessions")
def create_session(
    payload: DataAgentSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return create_agent_session(
        db,
        current_user.id,
        payload.project_id,
        payload.env_id,
        payload.instruction,
        payload.topbar_customer_ids,
    )


@router.post("/sessions/{session_id}/messages")
def post_message(
    session_id: str,
    payload: DataAgentSessionMessage,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return add_agent_message(db, session_id, current_user.id, payload.message)


@router.post("/sessions/{session_id}/confirm")
def confirm_session(
    session_id: str,
    payload: DataAgentSessionConfirm,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return confirm_agent_session(db, session_id, current_user.id, payload.plan_version)


@router.get("/sessions/{session_id}")
def read_session(
    session_id: str,
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return get_agent_session(session_id, current_user.id)


@router.post("/sessions/{session_id}/permission")
async def resume_permission(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        raw_payload = await request.json()
        if not isinstance(raw_payload, dict):
            raise ValueError("invalid payload")
        payload = DataAgentPermissionResume.model_validate(raw_payload)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="权限恢复请求格式无效",
        ) from None
    return resume_agent_permission(
        db,
        session_id,
        current_user.id,
        payload.plan_version,
        payload.backend_account_profile_id,
        payload.backend_account,
        payload.backend_password,
    )


@router.post("/sessions/{session_id}/cancel")
def cancel_session(
    session_id: str,
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    return cancel_agent_session(session_id, current_user.id)


@router.patch("/sessions/{session_id}/goal")
def update_goal(
    session_id: str,
    payload: DataAgentGoalUpdate,
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """Direct edit of goal fields without re-invoking DeepSeek."""
    return update_agent_goal(
        session_id, current_user.id, payload.model_dump(exclude_none=True)
    )
