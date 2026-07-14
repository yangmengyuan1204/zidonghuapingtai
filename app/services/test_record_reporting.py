"""测试执行记录的展示字段解析。"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from ..core.utils import decrypt_account_payload
from ..models import ApiCase, TestRecord, UiCase


EXECUTION_METADATA_KEY = "_exec_meta"


def _parse_log(record: TestRecord) -> Dict[str, Any]:
    try:
        value = json.loads(record.log or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _metadata(log_data: Dict[str, Any]) -> Dict[str, Any]:
    value = log_data.get(EXECUTION_METADATA_KEY)
    return value if isinstance(value, dict) else {}


def _metadata_variables(metadata: Dict[str, Any]) -> Dict[str, Any]:
    value = decrypt_account_payload(str(metadata.get("variables_encrypted") or ""))
    return value if isinstance(value, dict) else {}


def _script_identity(
    record: TestRecord,
    log_data: Dict[str, Any],
    metadata: Dict[str, Any],
    variables: Dict[str, Any],
    target: ApiCase | UiCase | None,
) -> tuple[str, str]:
    if record.case_type == "api" and record.case_id and target is not None and metadata.get("kind") != "data_script":
        return str(target.case_name or ""), "case"
    script_name = str(
        variables.get("_data_script_name")
        or metadata.get("script_name")
        or log_data.get("script")
        or metadata.get("script_key")
        or ""
    ).strip()
    source = "flow_metadata" if variables.get("_data_script_name") or metadata.get("script_name") else "legacy_log"
    return script_name, source


def _normalize_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        text = urlsplit(text).path or "/"
    if not text.startswith("/") or text.startswith("//"):
        return ""
    return text.split("?", 1)[0].split("#", 1)[0]


def _walk_endpoint_paths(value: Any, output: list[tuple[str, str]]) -> None:
    if isinstance(value, dict):
        method = str(value.get("method") or value.get("request_method") or "").upper().strip()
        for key in ("path", "url", "endpoint", "api_path"):
            path = _normalize_path(value.get(key))
            if path:
                output.append((path, method))
        for child in value.values():
            _walk_endpoint_paths(child, output)
    elif isinstance(value, list):
        for child in value:
            _walk_endpoint_paths(child, output)


def _step_names(log_data: Dict[str, Any]) -> list[str]:
    names: list[str] = []
    sources: Iterable[Any] = [log_data.get("steps")]
    summary = log_data.get("summary")
    if isinstance(summary, dict):
        sources = [log_data.get("steps"), summary.get("steps")]
    for source in sources:
        if not isinstance(source, list):
            continue
        for item in source:
            if not isinstance(item, dict):
                continue
            name = str(item.get("script") or "").strip()
            if name and name not in names:
                names.append(name)
    return names


def _interface_display(name: Any, method: Any, url: Any) -> str:
    path = _normalize_path(url) or str(url or "").strip()
    method_text = str(method or "POST").upper().strip()
    return f"{str(name or '接口').strip()}（{method_text} {path}）"


def _interface_names(
    db: Session,
    record: TestRecord,
    log_data: Dict[str, Any],
    target: ApiCase | UiCase | None,
) -> list[str]:
    if isinstance(target, ApiCase):
        return [_interface_display(target.case_name, target.method, target.url)]
    if record.case_type != "api":
        return []

    project_id = record.project_id
    cases = db.query(ApiCase).filter(ApiCase.project_id == project_id).all() if project_id else []
    by_path: Dict[str, ApiCase] = {}
    for case in cases:
        path = _normalize_path(case.url)
        if path and path not in by_path:
            by_path[path] = case

    paths: list[tuple[str, str]] = []
    _walk_endpoint_paths(log_data, paths)
    names: list[str] = []
    for path, method in paths:
        case = by_path.get(path)
        if case:
            display = _interface_display(case.case_name, case.method, case.url)
        else:
            display = _interface_display("接口", method, path)
        if display not in names:
            names.append(display)
    return names or _step_names(log_data)


def build_test_record_report_fields(db: Session, record: TestRecord) -> Dict[str, Any]:
    log_data = _parse_log(record)
    metadata = _metadata(log_data)
    variables = _metadata_variables(metadata)
    target: ApiCase | UiCase | None = None
    if record.case_type == "api" and record.case_id:
        target = db.get(ApiCase, record.case_id)
    elif record.case_type == "ui" and record.case_id:
        target = db.get(UiCase, record.case_id)
    script_name, source = _script_identity(record, log_data, metadata, variables, target)
    return {
        "script_name": script_name,
        "script_name_source": source,
        "interface_names": _interface_names(db, record, log_data, target),
    }
