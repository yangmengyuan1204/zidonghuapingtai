import json
from typing import Any, Dict

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..core.utils import (
    decrypt_account_payload,
    ensure_env_belongs_to_project,
    get_or_404,
    is_sensitive_account_key,
    resolve_execution_account,
    save_record,
    save_ui_record,
    serialize,
)
from ..executors import execute_api_case, execute_ui_case
from ..models import ApiCase, Env, TestRecord, UiCase
from ..schemas import FunctionalExecuteRequest


EXECUTION_METADATA_KEY = "_exec_meta"
EXECUTION_METADATA_VERSION = 1


def _execution_metadata(record: TestRecord) -> Dict[str, Any] | None:
    try:
        log_data = json.loads(record.log or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(log_data, dict):
        return None
    metadata = log_data.get(EXECUTION_METADATA_KEY)
    if not isinstance(metadata, dict) or metadata.get("version") != EXECUTION_METADATA_VERSION:
        return None
    return metadata


def _metadata_variables(metadata: Dict[str, Any]) -> Dict[str, Any]:
    variables = decrypt_account_payload(str(metadata.get("variables_encrypted") or ""))
    return variables if isinstance(variables, dict) else {}


def _safe_context_variables(variables: Dict[str, Any]) -> tuple[Dict[str, Any], list[str]]:
    sensitive_keys = sorted(str(key) for key in variables if is_sensitive_account_key(key))
    visible = {key: value for key, value in variables.items() if str(key) not in sensitive_keys}
    return visible, sensitive_keys


def build_reexecute_context(db: Session, record: TestRecord) -> Dict[str, Any]:
    metadata = _execution_metadata(record)
    if not metadata:
        return {
            "record_id": record.id,
            "available": False,
            "direct_execute": False,
            "requires_form": True,
            "message": "历史记录缺少完整执行参数，请从原入口补充参数后执行",
        }

    kind = str(metadata.get("kind") or "").strip()
    target_id = int(metadata.get("target_id") or record.case_id or 0)
    variables, sensitive_keys = _safe_context_variables(_metadata_variables(metadata))
    context: Dict[str, Any] = {
        "record_id": record.id,
        "available": True,
        "kind": kind,
        "target_id": target_id,
        "project_id": metadata.get("project_id", record.project_id),
        "env_id": metadata.get("env_id"),
        "script_key": metadata.get("script_key", ""),
        "account_mode": metadata.get("account_mode", "default"),
        "account_profile_id": metadata.get("account_profile_id"),
        "variables": variables,
        "sensitive_keys": sensitive_keys,
    }
    if kind == "data_script":
        context.update(
            {
                "direct_execute": False,
                "requires_form": True,
                "message": "数据脚本会修改业务数据，请核对原参数后从脚本表单执行",
            }
        )
        return context
    if kind == "api_case":
        target = db.get(ApiCase, target_id)
    elif kind == "ui_case":
        target = db.get(UiCase, target_id)
    else:
        target = None
    if target is None:
        context.update(
            {
                "available": False,
                "direct_execute": False,
                "requires_form": True,
                "message": "原用例不存在或执行类型无法识别，请从原入口执行",
            }
        )
        return context
    context.update(
        {
            "direct_execute": True,
            "requires_form": False,
            "message": "请核对执行上下文并确认再次执行",
        }
    )
    return context


def reexecute_record(db: Session, record: TestRecord, confirmed: bool) -> Dict[str, Any]:
    if not confirmed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="必须确认后才能再次执行")
    metadata = _execution_metadata(record)
    if not metadata:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="历史记录缺少完整执行参数，请从原入口执行")
    kind = str(metadata.get("kind") or "").strip()
    if kind == "data_script":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="数据脚本必须回到原参数表单确认后执行")

    target_id = int(metadata.get("target_id") or record.case_id or 0)
    runtime_variables = _metadata_variables(metadata)
    if kind == "api_case":
        case = get_or_404(db, ApiCase, target_id)
        env_id = int(metadata.get("env_id") or case.env_id or 0)
        env = get_or_404(db, Env, env_id)
        ensure_env_belongs_to_project(env, case.project_id)
        passed, log_text, report_path, extracted_vars = execute_api_case(case, env, runtime_variables)
        new_record = save_record(
            db,
            "api",
            case.id,
            passed,
            log_text,
            report_path,
            project_id=case.project_id,
            kind="api_case",
            script_key="api_case",
            env_id=env.id,
            variables=runtime_variables,
        )
        data = serialize(new_record)
        data["extracted_vars"] = extracted_vars
        return data

    if kind == "ui_case":
        case = get_or_404(db, UiCase, target_id)
        stored_mode = str(metadata.get("account_mode") or "default")
        profile_id = metadata.get("account_profile_id")
        effective_mode = "none" if stored_mode == "none" else "override" if profile_id else "default"
        payload = FunctionalExecuteRequest(
            variables=runtime_variables,
            account_mode=effective_mode,
            account_profile_id=int(profile_id) if profile_id else None,
        )
        variables, execution_context = resolve_execution_account(
            db,
            payload,
            "ui_case",
            case.id,
            case.project_id,
            case.page_url,
        )
        passed, log_text, screenshot_path, report_path = execute_ui_case(
            case,
            variables,
            execution_context,
            db_session=db,
        )
        new_record = save_ui_record(
            db,
            case,
            passed,
            log_text,
            report_path,
            screenshot_path,
            kind="ui_case",
            script_key="ui_case",
            variables=runtime_variables,
            account_mode=stored_mode,
            account_profile_id=execution_context.get("account_profile_id") or profile_id,
        )
        return serialize(new_record)

    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="执行类型无法识别，请从原入口执行")
