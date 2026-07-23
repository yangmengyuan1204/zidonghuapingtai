from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from ..agent_schemas import (
    DataAgentGoalUpdate,
    DataAgentPermissionResume,
    DataAgentRuleReviewRequest,
    DataAgentRuleRollbackRequest,
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
from ..services import data_agent_learning as learning_service

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


_LEARNING_ROUTE_ERRORS = (ValueError, IntegrityError, OperationalError)


def _raise_learning_http_error(exc: Exception) -> None:
    if isinstance(exc, learning_service.LearningNotFoundError):
        code = status.HTTP_404_NOT_FOUND
        detail = "学习规则不存在"
    elif isinstance(exc, learning_service.LearningInputError):
        code = status.HTTP_400_BAD_REQUEST
        detail = "学习规则请求参数无效"
    else:
        code = status.HTTP_409_CONFLICT
        detail = "学习规则状态冲突，请刷新后重试"
    raise HTTPException(status_code=code, detail=detail) from None


async def _read_learning_payload(request: Request, schema: type) -> Any:
    try:
        raw_payload = await request.json()
        if not isinstance(raw_payload, dict):
            raise ValueError("invalid payload")
        return schema.model_validate(raw_payload)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="学习规则请求参数无效",
        ) from None


@router.get("/learning/overview")
def learning_overview(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return learning_service.get_learning_overview(db, project_id)
    except _LEARNING_ROUTE_ERRORS as exc:
        _raise_learning_http_error(exc)


@router.get("/learning/candidates/{candidate_id}")
def learning_candidate_detail(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return learning_service.get_candidate_detail(db, candidate_id)
    except _LEARNING_ROUTE_ERRORS as exc:
        _raise_learning_http_error(exc)


@router.post("/learning/candidates/{candidate_id}/regression")
def learning_candidate_regression(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        learning_service.get_candidate_detail(db, candidate_id)
        learning_service.run_candidate_regression(db, candidate_id)
        return learning_service.get_candidate_detail(db, candidate_id)
    except _LEARNING_ROUTE_ERRORS as exc:
        _raise_learning_http_error(exc)


@router.post("/learning/candidates/{candidate_id}/approve")
async def learning_candidate_approve(
    candidate_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    payload = await _read_learning_payload(request, DataAgentRuleReviewRequest)
    try:
        return learning_service.approve_candidate(
            db, candidate_id, current_user.id, payload.reason
        )
    except _LEARNING_ROUTE_ERRORS as exc:
        _raise_learning_http_error(exc)


@router.post("/learning/candidates/{candidate_id}/reject")
async def learning_candidate_reject(
    candidate_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    payload = await _read_learning_payload(request, DataAgentRuleReviewRequest)
    try:
        return learning_service.reject_candidate(
            db, candidate_id, current_user.id, payload.reason
        )
    except _LEARNING_ROUTE_ERRORS as exc:
        _raise_learning_http_error(exc)


@router.get("/learning/rules/{rule_version_id}")
def learning_rule_detail(
    rule_version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return learning_service.get_rule_detail(db, rule_version_id)
    except _LEARNING_ROUTE_ERRORS as exc:
        _raise_learning_http_error(exc)


@router.post("/learning/rules/{rule_version_id}/promote")
async def learning_rule_promote(
    rule_version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    payload = await _read_learning_payload(request, DataAgentRuleReviewRequest)
    try:
        return learning_service.promote_rule(
            db, rule_version_id, current_user.id, payload.reason
        )
    except _LEARNING_ROUTE_ERRORS as exc:
        _raise_learning_http_error(exc)


@router.post("/learning/rules/{rule_version_id}/disable")
async def learning_rule_disable(
    rule_version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    payload = await _read_learning_payload(request, DataAgentRuleReviewRequest)
    try:
        return learning_service.disable_rule(
            db, rule_version_id, current_user.id, payload.reason
        )
    except _LEARNING_ROUTE_ERRORS as exc:
        _raise_learning_http_error(exc)


@router.post("/learning/rules/{rule_version_id}/rollback")
async def learning_rule_rollback(
    rule_version_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    payload = await _read_learning_payload(request, DataAgentRuleRollbackRequest)
    try:
        return learning_service.rollback_rule(
            db,
            rule_version_id,
            payload.target_version_id,
            current_user.id,
            payload.reason,
        )
    except _LEARNING_ROUTE_ERRORS as exc:
        _raise_learning_http_error(exc)
