"""UI 用例路由"""
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.utils import (
    serialize, serialize_many, get_or_404, schema_data,
    normalize_json_fields, ensure_project_exists,
    account_profile_summary, resolve_execution_account, save_ui_record,
)
from ..database import get_db
from ..executors import execute_ui_case, parse_json_value, to_json_text
from ..models import (
    UiCase, TestAccountBinding, TestAccountProfile, TestRecord,
    LocatorHealLog, User,
)
from ..schemas import UiCaseCreate, UiCaseUpdate, FunctionalExecuteRequest
from ..security import get_current_user, require_admin

router = APIRouter(tags=["ui-cases"])


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
