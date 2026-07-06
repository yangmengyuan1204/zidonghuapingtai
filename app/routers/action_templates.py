"""操作模板库路由"""
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.utils import (
    get_or_404, schema_data, _serialize_template,
    ensure_project_exists, require_non_blank_text,
)
from ..database import get_db
from ..executors import parse_json_value, to_json_text
from ..models import ActionTemplate, UiCase, User
from ..schemas import ActionTemplateCreate, ActionTemplateUpdate
from ..security import get_current_user, require_admin
from ..core.utils import ACTION_TEMPLATE_JSON_DEFAULTS

router = APIRouter(tags=["action-templates"])


@router.get("/api/action-templates")
def list_action_templates(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(ActionTemplate)
    if project_id is not None:
        query = query.filter(ActionTemplate.project_id == project_id)
    return [_serialize_template(t) for t in query.order_by(ActionTemplate.id.desc()).all()]


@router.post("/api/action-templates")
def create_action_template(
    payload: ActionTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload)
    ensure_project_exists(db, data["project_id"])
    require_non_blank_text(data, "name", "模板名称")
    template = ActionTemplate(
        project_id=data["project_id"],
        name=data["name"],
        description=data.get("description", ""),
        trigger_keywords=to_json_text(data.get("trigger_keywords", []), []),
        steps=to_json_text(data.get("steps", []), []),
        variables=to_json_text(data.get("variables", {}), {}),
        locator_fallbacks=to_json_text(data.get("locator_fallbacks", {}), {}),
        create_time=datetime.now(),
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _serialize_template(template)


@router.put("/api/action-templates/{template_id}")
def update_action_template(
    template_id: int,
    payload: ActionTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    template = get_or_404(db, ActionTemplate, template_id)
    data = schema_data(payload, exclude_unset=True)
    if "name" in data:
        require_non_blank_text(data, "name", "模板名称")
    for field in ["name", "description"]:
        if field in data:
            setattr(template, field, data[field])
    for json_field in ["trigger_keywords", "steps", "variables", "locator_fallbacks"]:
        if json_field in data:
            setattr(template, json_field, to_json_text(data[json_field], ACTION_TEMPLATE_JSON_DEFAULTS[json_field]))
    db.commit()
    db.refresh(template)
    return _serialize_template(template)


@router.delete("/api/action-templates/{template_id}")
def delete_action_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    template = get_or_404(db, ActionTemplate, template_id)
    db.delete(template)
    db.commit()
    return {"message": "deleted"}


@router.get("/api/action-templates/{template_id}/test-run")
def test_run_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    template = get_or_404(db, ActionTemplate, template_id)
    steps = parse_json_value(template.steps, [])
    if not steps:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模板没有步骤")
    try:
        from ..executors import execute_ui_case
        ui_case = UiCase(
            id=-1,  # 临时对象，不会被保存到数据库，使用 -1 避免误操作
            project_id=template.project_id,
            case_name=f"[模板测试] {template.name}",
            page_url="",
            steps=to_json_text(steps, []),
            timeout=30,
            status="active",
            create_time=datetime.now(),
        )
        passed, log_text, screenshot_path, report_path = execute_ui_case(ui_case, {})
        return {"passed": passed, "log": log_text, "screenshot": screenshot_path}
    except Exception as exc:
        return {"passed": False, "log": str(exc), "screenshot": ""}
