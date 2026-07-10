from __future__ import annotations

import sys
from functools import wraps





_COMPAT_NAMES = (
    "TestRecord",
    "datetime",
    "encrypt_account_payload",
    "enrich_log_with_exec_params",
    "json",
    "safe_commit",
)


def _sync_compat_globals() -> None:
    module = sys.modules["app.core.utils"]
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(module, name)


def _compat_wrapper(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        _sync_compat_globals()
        return func(*args, **kwargs)

    return wrapped


def _impl_enrich_log_with_exec_params(log_text: str, **exec_params: Any) -> str:
    """将加密后的执行上下文嵌入日志，供安全的再次执行使用。"""
    if not exec_params:
        return log_text
    params = dict(exec_params)
    variables = params.pop("variables", {})
    if not isinstance(variables, dict):
        variables = {}
    script_key = str(params.pop("script_key", None) or params.pop("script", None) or "").strip()
    kind = str(params.pop("kind", "") or "").strip()
    if not kind:
        kind = "api_case" if script_key == "api_case" else "ui_case" if script_key == "ui_case" else "data_script"
    metadata: Dict[str, Any] = {
        "version": 1,
        "kind": kind,
        "variables_encrypted": encrypt_account_payload(variables),
    }
    if script_key:
        metadata["script_key"] = script_key
    for key in ("target_id", "project_id", "env_id", "account_mode", "account_profile_id"):
        value = params.get(key)
        if value not in (None, ""):
            metadata[key] = value
    try:
        log_data = json.loads(log_text) if log_text else {}
    except (json.JSONDecodeError, TypeError):
        return log_text
    if isinstance(log_data, dict):
        log_data.pop("_exec_params", None)
        log_data["_exec_meta"] = metadata
        return json.dumps(log_data, ensure_ascii=False, default=str)
    return log_text


def _impl_save_ui_record(db: Session, case: UiCase, passed: bool, log_text: str, report_path: str, screenshot_path: str = "", **exec_params: Any) -> TestRecord:
    if exec_params:
        exec_params.setdefault("target_id", case.id)
        exec_params.setdefault("project_id", case.project_id)
    log_text = enrich_log_with_exec_params(log_text, **exec_params)
    record = TestRecord(
        case_type="ui",
        case_id=case.id,
        project_id=case.project_id,
        result="passed" if passed else "failed",
        log=log_text,
        screenshot=screenshot_path,
        report_path=report_path,
        execute_time=datetime.now(),
    )
    db.add(record)
    safe_commit(db)
    db.refresh(record)
    return record


def _impl_save_record(
    db: Session,
    case_type: str,
    case_id: int,
    passed: bool,
    log_text: str,
    report_path: str,
    screenshot: str = "",
    project_id: int | None = None,
    **exec_params: Any,
) -> TestRecord:
    if exec_params:
        exec_params.setdefault("target_id", case_id)
        exec_params.setdefault("project_id", project_id)
    log_text = enrich_log_with_exec_params(log_text, **exec_params)
    record = TestRecord(
        case_type=case_type,
        case_id=case_id,
        project_id=project_id,
        result="passed" if passed else "failed",
        log=log_text,
        screenshot=screenshot,
        report_path=report_path,
        execute_time=datetime.now(),
    )
    db.add(record)
    safe_commit(db)
    db.refresh(record)
    return record


enrich_log_with_exec_params = _compat_wrapper(_impl_enrich_log_with_exec_params)
save_ui_record = _compat_wrapper(_impl_save_ui_record)
save_record = _compat_wrapper(_impl_save_record)
