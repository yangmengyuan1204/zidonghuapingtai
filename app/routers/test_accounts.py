"""账号档案路由"""
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.cache import invalidate
from ..core.utils import (
    serialize_account_profile, get_or_404, schema_data,
    normalize_account_payload, account_target_project_id,
    account_profile_variables, save_test_account_binding,
    ensure_project_exists,
)
from ..database import get_db
from ..models import TestAccountBinding, TestAccountProfile, User
from ..schemas import TestAccountProfileCreate, TestAccountProfileUpdate, TestAccountBindingUpdate
from ..security import get_current_user, require_admin

router = APIRouter(tags=["test-accounts"])


@router.get("/api/test-accounts")
def list_test_accounts(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(TestAccountProfile)
    if project_id is not None:
        ensure_project_exists(db, project_id)
        query = query.filter(or_(TestAccountProfile.project_id == project_id, TestAccountProfile.project_id.is_(None)))
    if current_user.role != "admin":
        query = query.filter(TestAccountProfile.status == "active")
    return [serialize_account_profile(item) for item in query.order_by(TestAccountProfile.project_id.asc(), TestAccountProfile.id.desc()).all()]


@router.post("/api/test-accounts")
def create_test_account(
    payload: TestAccountProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = normalize_account_payload(db, schema_data(payload))
    profile = TestAccountProfile(
        project_id=data.get("project_id"),
        profile_name=data["profile_name"],
        variables=data.get("variables") or "{}",
        sensitive_variables=data.get("sensitive_variables") or "",
        login_url=data.get("login_url") or "",
        username_locator=data.get("username_locator") or "",
        password_locator=data.get("password_locator") or "",
        submit_locator=data.get("submit_locator") or "",
        success_url_contains=data.get("success_url_contains") or "",
        success_selector=data.get("success_selector") or "",
        status=data.get("status") or "active",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    invalidate("projects")
    return serialize_account_profile(profile)


@router.put("/api/test-accounts/{account_id}")
def update_test_account(
    account_id: int,
    payload: TestAccountProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    profile = get_or_404(db, TestAccountProfile, account_id)
    data = normalize_account_payload(db, schema_data(payload, exclude_unset=True), profile)
    for field, value in data.items():
        setattr(profile, field, value)
    profile.update_time = datetime.now()
    db.commit()
    db.refresh(profile)
    invalidate("projects")
    return serialize_account_profile(profile)


@router.delete("/api/test-accounts/{account_id}")
def delete_test_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    profile = get_or_404(db, TestAccountProfile, account_id)
    db.query(TestAccountBinding).filter(TestAccountBinding.account_profile_id == profile.id).delete(synchronize_session=False)
    db.delete(profile)
    db.commit()
    invalidate("projects")
    return {"message": "deleted"}


@router.delete("/api/test-accounts/{account_id}/browser-session")
def clear_test_account_browser_session(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    profile = get_or_404(db, TestAccountProfile, account_id)
    profile.browser_state_encrypted = ""
    profile.browser_session_status = "cleared"
    profile.browser_session_cleared_at = datetime.now()
    profile.browser_session_validated_at = None
    profile.update_time = datetime.now()
    db.commit()
    db.refresh(profile)
    return serialize_account_profile(profile)


@router.put("/api/test-account-bindings")
def update_test_account_binding(
    payload: TestAccountBindingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload)
    target_type = str(data["target_type"])
    target_id = int(data["target_id"])
    project_id = account_target_project_id(db, target_type, target_id)
    profile_id = data.get("account_profile_id")
    if profile_id is not None:
        account_profile_variables(db, int(profile_id), project_id)
    save_test_account_binding(db, target_type, target_id, profile_id)
    db.commit()
    invalidate("projects")
    profile = db.get(TestAccountProfile, profile_id) if profile_id else None
    return {"profile": serialize_account_profile(profile) if profile else None}
