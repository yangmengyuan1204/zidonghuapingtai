"""测试记录 + 文件路由"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.utils import get_or_404, safe_file_response, serialize
from ..database import get_db
from ..models import ApiCase, Project, TestRecord, UiCase, User
from ..schemas import ReExecuteConfirmRequest
from ..security import get_current_user, require_admin
from ..services.test_record_recovery import recover_orphan_test_records
from ..services.test_record_reporting import build_test_record_report_fields
from ..services.test_record_reexecution import build_reexecute_context, reexecute_record


router = APIRouter(tags=["test-records"])


@router.get("/api/test-records")
def list_records(
    case_type: str | None = Query(default=None),
    project_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    query = db.query(TestRecord)
    if case_type is not None:
        query = query.filter(TestRecord.case_type == case_type)
    if project_id is not None:
        api_ids = [item.id for item in db.query(ApiCase.id).filter(ApiCase.project_id == project_id).all()]
        ui_ids = [item.id for item in db.query(UiCase.id).filter(UiCase.project_id == project_id).all()]
        query = query.filter(
            or_(
                TestRecord.project_id == project_id,
                (TestRecord.case_type == "api") & TestRecord.case_id.in_(api_ids or [-1]),
                (TestRecord.case_type == "ui") & TestRecord.case_id.in_(ui_ids or [-1]),
            )
        )
    total = query.count()
    records = query.order_by(TestRecord.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for record in records:
        item = serialize(record)
        item.update(build_test_record_report_fields(db, record))
        items.append(item)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/api/test-records/recover-orphan-reports")
def recover_orphan_reports(
    project_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, int]:
    if project_id is not None:
        get_or_404(db, Project, project_id)
    return recover_orphan_test_records(db, project_id=project_id)


@router.get("/api/test-records/{record_id}")
def get_record(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    record = get_or_404(db, TestRecord, record_id)
    data = serialize(record)
    data.update(build_test_record_report_fields(db, record))
    return data


@router.get("/api/test-records/{record_id}/report")
def get_record_report(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> FileResponse:
    record = get_or_404(db, TestRecord, record_id)
    return safe_file_response(record.report_path)


@router.get("/api/test-records/{record_id}/screenshot")
def get_record_screenshot(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> FileResponse:
    record = get_or_404(db, TestRecord, record_id)
    return safe_file_response(record.screenshot)


@router.get("/api/files/screenshot")
def get_screenshot_by_path(path: str = Query(..., description="截图文件路径"), current_user: User = Depends(get_current_user)) -> FileResponse:
    return safe_file_response(path)


@router.get("/api/test-records/{record_id}/re-execute")
def get_reexecute_context(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    record = get_or_404(db, TestRecord, record_id)
    return build_reexecute_context(db, record)


@router.post("/api/test-records/{record_id}/re-execute")
def confirm_reexecute_record(
    record_id: int,
    payload: ReExecuteConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    record = get_or_404(db, TestRecord, record_id)
    return reexecute_record(db, record, payload.confirmed)
