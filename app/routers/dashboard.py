"""仪表盘路由：聚合统计"""
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..core.cache import get as cache_get
from ..core.utils import serialize_many
from ..database import get_db
from ..models import TestRecord, User
from ..security import get_current_user

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard")
def dashboard(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    # 一条组合查询获取 5 个 COUNT（代替 5~8 次独立查询）
    if project_id is not None:
        row = db.execute(
            text("""
                SELECT
                    (SELECT COUNT(*) FROM project WHERE id = :pid),
                    (SELECT COUNT(*) FROM env WHERE project_id = :pid),
                    (SELECT COUNT(*) FROM api_case WHERE project_id = :pid),
                    (SELECT COUNT(*) FROM ui_case WHERE project_id = :pid),
                    (SELECT COUNT(*) FROM test_record WHERE project_id = :pid)
            """),
            {"pid": project_id},
        ).one()
    else:
        row = db.execute(
            text("""
                SELECT
                    (SELECT COUNT(*) FROM project),
                    (SELECT COUNT(*) FROM env),
                    (SELECT COUNT(*) FROM api_case),
                    (SELECT COUNT(*) FROM ui_case),
                    (SELECT COUNT(*) FROM test_record)
            """),
        ).one()

    latest_records = db.query(TestRecord)
    if project_id is not None:
        latest_records = latest_records.filter(TestRecord.project_id == project_id)
    latest_records = latest_records.order_by(TestRecord.id.desc()).limit(10).all()

    return {
        "project_count": row[0],
        "env_count": row[1],
        "api_case_count": row[2],
        "ui_case_count": row[3],
        "record_count": row[4],
        "latest_records": serialize_many(latest_records),
        "role": current_user.role,
    }
