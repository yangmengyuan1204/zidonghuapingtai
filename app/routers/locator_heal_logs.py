"""Locator 自愈记录路由"""
import json
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.utils import get_or_404
from ..database import get_db
from ..models import LocatorHealLog, UiCase, User
from ..schemas import LocatorHealLogConfirm
from ..security import get_current_user, require_admin

router = APIRouter(tags=["locator-heal-logs"])


@router.get("/api/locator-heal-logs")
def list_heal_logs(
    case_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    query = db.query(LocatorHealLog)
    if case_id is not None:
        query = query.filter(LocatorHealLog.case_id == case_id)
    total = query.count()
    offset = (page - 1) * page_size
    items = [
        {
            "id": log.id,
            "case_id": log.case_id,
            "old_locator": log.old_locator,
            "new_locator": log.new_locator,
            "page_url": log.page_url or "",
            "screenshot_path": log.screenshot_path or "",
            "confirmed": log.confirmed,
            "create_time": log.create_time.isoformat(),
            "step_action": log.step_action or "",
            "auto_applied": log.auto_applied or 0,
            "ai_prompt": log.ai_prompt or "",
            "ai_response": log.ai_response or "",
        }
        for log in query.order_by(LocatorHealLog.id.desc()).offset(offset).limit(page_size).all()
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.put("/api/locator-heal-logs/{log_id}")
def confirm_heal_log(
    log_id: int,
    payload: LocatorHealLogConfirm,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    log = get_or_404(db, LocatorHealLog, log_id)
    log.confirmed = payload.confirmed
    db.commit()
    return {"message": "updated"}


@router.post("/api/locator-heal-logs/{log_id}/apply")
def apply_heal_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """手动确认应用一条 heal 记录到用例。"""
    log = get_or_404(db, LocatorHealLog, log_id)
    if not log.new_locator:
        return {"message": "无新 locator，无法应用"}
    case = db.get(UiCase, log.case_id)
    if not case:
        return {"message": "用例不存在"}
    try:
        steps = json.loads(case.steps or "[]")
        if isinstance(steps, list):
            changed = False
            for s in steps:
                if isinstance(s, dict) and s.get("locator") == log.old_locator:
                    s["locator"] = log.new_locator
                    s["healed_at"] = datetime.now().isoformat()
                    changed = True
            if changed:
                case.steps = json.dumps(steps, ensure_ascii=False)
                log.confirmed = 1
                log.auto_applied = 1
                db.commit()
                return {"message": "已应用"}
        return {"message": "未找到匹配的 locator"}
    except Exception as exc:
        return {"message": f"应用失败: {exc}"}
