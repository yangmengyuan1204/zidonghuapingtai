from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import Project, UiRecordProjectConfig
from .requirement_verification import data_script_catalog, validate_data_setup_for_project


SENSITIVE_KEY_PARTS = ("password", "token", "cookie", "secret", "authorization")


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            any(part in str(key).strip().lower() for part in SENSITIVE_KEY_PARTS)
            or _contains_sensitive_key(nested)
            for key, nested in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def get_recording_config(db: Session, project_id: int) -> UiRecordProjectConfig | None:
    return db.get(UiRecordProjectConfig, project_id)


def save_recording_config(
    db: Session,
    project_id: int,
    payload: dict[str, Any],
) -> UiRecordProjectConfig:
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("项目不存在")
    reset_script_key = str(payload.get("reset_script_key") or "").strip()
    reset_env_id = int(payload.get("reset_env_id") or 0)
    reset_variables = payload.get("reset_variables") or {}
    if not isinstance(reset_variables, dict):
        raise ValueError("重置参数必须是对象")
    if _contains_sensitive_key(reset_variables):
        raise ValueError("重置参数不能保存密码、令牌或Cookie")
    validate_data_setup_for_project(db, project_id, {
        "steps": [{
            "script_type": reset_script_key,
            "env_id": reset_env_id,
            "variables": reset_variables,
            "enabled": True,
        }]
    })
    row = db.get(UiRecordProjectConfig, project_id)
    if row is None:
        row = UiRecordProjectConfig(project_id=project_id, create_time=datetime.now())
        db.add(row)
    row.reset_script_key = reset_script_key
    row.reset_env_id = reset_env_id
    row.reset_variables_json = json.dumps(reset_variables, ensure_ascii=False)
    row.verification_rounds = 2
    row.max_repair_attempts = max(1, min(5, int(payload.get("max_repair_attempts") or 3)))
    row.update_time = datetime.now()
    db.commit()
    db.refresh(row)
    return row


def serialize_recording_config(db: Session, project_id: int) -> dict[str, Any]:
    row = get_recording_config(db, project_id)
    return {
        "project_id": project_id,
        "config": None if row is None else {
            "reset_script_key": row.reset_script_key,
            "reset_env_id": row.reset_env_id,
            "reset_variables": json.loads(row.reset_variables_json or "{}"),
            "verification_rounds": 2,
            "max_repair_attempts": row.max_repair_attempts,
        },
        "available_scripts": data_script_catalog(db, project_id),
    }
