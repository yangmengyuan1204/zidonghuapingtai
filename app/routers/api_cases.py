"""接口用例路由"""
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.utils import (
    serialize, serialize_many, get_or_404, schema_data,
    normalize_api_case_payload, normalize_json_fields,
    ensure_project_exists, ensure_env_exists, ensure_env_belongs_to_project,
    strip_case_name_prefix, apply_frontend_customer_login_variables,
    save_record,
)
from ..database import get_db
from ..executors import execute_api_case
from ..models import ApiCase, Env, TestAccountBinding, TestRecord, User
from ..schemas import ApiCaseCreate, ApiCaseUpdate, ApiExecuteRequest, ApiBatchExecuteRequest
from ..security import get_current_user, require_admin

router = APIRouter(tags=["api-cases"])


@router.get("/api/api-cases")
def list_api_cases(
    project_id: int | None = Query(default=None),
    env_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(ApiCase)
    if project_id is not None:
        query = query.filter(ApiCase.project_id == project_id)
    if env_id is not None:
        query = query.filter(ApiCase.env_id == env_id)
    return serialize_many(query.order_by(ApiCase.id.desc()).all())


@router.post("/api/api-cases")
def create_api_case(
    payload: ApiCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = normalize_api_case_payload(normalize_json_fields(schema_data(payload)), require_required_fields=True)
    data["case_name"] = strip_case_name_prefix(data["case_name"])
    if not data["case_name"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用例名称不能为空")
    ensure_project_exists(db, data["project_id"])
    env = ensure_env_exists(db, data["env_id"])
    ensure_env_belongs_to_project(env, data["project_id"])
    case = ApiCase(**data, create_time=datetime.now())
    db.add(case)
    db.commit()
    db.refresh(case)
    return serialize(case)


@router.put("/api/api-cases/{case_id}")
def update_api_case(
    case_id: int,
    payload: ApiCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    case = get_or_404(db, ApiCase, case_id)
    data = normalize_api_case_payload(normalize_json_fields(schema_data(payload, exclude_unset=True)))
    if "case_name" in data:
        data["case_name"] = strip_case_name_prefix(data["case_name"])
        if not data["case_name"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用例名称不能为空")
    if "project_id" in data:
        ensure_project_exists(db, data["project_id"])
    final_project_id = data.get("project_id", case.project_id)
    final_env_id = data.get("env_id", case.env_id)
    env = ensure_env_exists(db, final_env_id)
    ensure_env_belongs_to_project(env, final_project_id)
    for field, value in data.items():
        setattr(case, field, value)
    db.commit()
    db.refresh(case)
    return serialize(case)


@router.delete("/api/api-cases/{case_id}")
def delete_api_case(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, str]:
    case = get_or_404(db, ApiCase, case_id)
    # 清理关联记录
    db.query(TestRecord).filter(TestRecord.case_type == "api", TestRecord.case_id == case.id).delete(synchronize_session=False)
    db.query(TestAccountBinding).filter(TestAccountBinding.target_type == "api_case", TestAccountBinding.target_id == case.id).delete(synchronize_session=False)
    db.delete(case)
    db.commit()
    return {"message": "deleted"}


@router.post("/api/api-cases/{case_id}/execute")
def run_api_case(
    case_id: int,
    payload: ApiExecuteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    case = get_or_404(db, ApiCase, case_id)
    env_id = payload.env_id if payload and payload.env_id else case.env_id
    env = get_or_404(db, Env, env_id)
    if env.project_id != case.project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="环境不属于该用例项目")
    runtime_vars = payload.variables if payload else {}
    passed, log_text, report_path, extracted_vars = execute_api_case(case, env, runtime_vars)
    record = TestRecord(
        case_type="api",
        case_id=case.id,
        project_id=case.project_id,
        result="passed" if passed else "failed",
        log=log_text,
        screenshot="",
        report_path=report_path,
        execute_time=datetime.now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    data = serialize(record)
    data["extracted_vars"] = extracted_vars
    return data


@router.post("/api/api-cases/batch-execute")
def batch_run_api_cases(
    payload: ApiBatchExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    if not payload.case_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要执行的接口用例")
    runtime_vars = apply_frontend_customer_login_variables(dict(payload.variables or {}))
    records = []
    for case_id in payload.case_ids:
        case = get_or_404(db, ApiCase, case_id)
        env_id = payload.env_id or case.env_id
        env = get_or_404(db, Env, env_id)
        if env.project_id != case.project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"用例 {case.id} 与所选环境不属于同一项目")
        passed, log_text, report_path, extracted_vars = execute_api_case(case, env, runtime_vars)
        runtime_vars.update(extracted_vars)
        record = save_record(db, "api", case.id, passed, log_text, report_path, project_id=case.project_id)
        record_data = serialize(record)
        record_data["case_name"] = case.case_name
        record_data["extracted_vars"] = extracted_vars
        records.append(record_data)
    return {
        "passed": all(item["result"] == "passed" for item in records),
        "records": records,
        "variables": runtime_vars,
    }
