from __future__ import annotations

import sys
from functools import wraps





_COMPAT_NAMES = (
    "API_ALLOWED_METHODS",
    "AiConfig",
    "BASE_DIR",
    "Env",
    "FileResponse",
    "HTTPException",
    "JSON_FIELD_DEFAULTS",
    "Path",
    "Project",
    "TABLE_FIELDS",
    "TestRecord",
    "User",
    "datetime",
    "require_non_blank_text",
    "serialize",
    "status",
    "test_record_credibility_payload",
    "to_json_text",
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


def _impl_schema_data(payload: Any, exclude_unset: bool = False) -> Dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=exclude_unset)
    return payload.dict(exclude_unset=exclude_unset)


def _impl_serialize(obj: Any, hide_password: bool = True) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for field in TABLE_FIELDS[type(obj)]:
        if hide_password and field == "password":
            continue
        value = getattr(obj, field)
        if isinstance(value, datetime):
            value = value.strftime("%Y-%m-%d %H:%M:%S")
        data[field] = value
    if isinstance(obj, TestRecord):
        data.update(test_record_credibility_payload(obj))
    return data


def _impl_serialize_many(items: Iterable[Any]) -> list[Dict[str, Any]]:
    return [serialize(item) for item in items]


def _impl_get_or_404(db: Session, model: Type[Any], item_id: int) -> Any:
    item = db.get(model, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据不存在")
    return item


def _impl_normalize_json_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    for field, fallback in JSON_FIELD_DEFAULTS.items():
        if field in data:
            data[field] = to_json_text(data[field], fallback)
    if "body" in data and data["body"] is not None and not isinstance(data["body"], str):
        data["body"] = to_json_text(data["body"], {})
    if "body" in data and data["body"] is None:
        data["body"] = ""
    if "method" in data and data["method"]:
        data["method"] = str(data["method"]).upper()
    return data


def _impl_require_non_blank_text(data: Dict[str, Any], field: str, label: str) -> None:
    value = str(data.get(field) or "").strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label}不能为空")
    data[field] = value


def _impl_normalize_project_payload(data: Dict[str, Any], require_name: bool = False) -> Dict[str, Any]:
    if require_name or "name" in data:
        require_non_blank_text(data, "name", "项目名称")
    if "desc" in data and data["desc"] is None:
        data["desc"] = ""
    return data


def _impl_normalize_env_payload(data: Dict[str, Any], require_required_fields: bool = False) -> Dict[str, Any]:
    if require_required_fields or "env_name" in data:
        require_non_blank_text(data, "env_name", "环境名称")
    if require_required_fields or "base_url" in data:
        require_non_blank_text(data, "base_url", "环境地址")
    if "timeout" in data and data["timeout"] is not None and int(data["timeout"]) <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="超时时间必须大于0")
    return data


def _impl_normalize_api_case_payload(data: Dict[str, Any], require_required_fields: bool = False) -> Dict[str, Any]:
    if require_required_fields or "method" in data:
        method = str(data.get("method") or "").upper().strip()
        if method not in API_ALLOWED_METHODS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的请求方法")
        data["method"] = method
    if require_required_fields or "url" in data:
        require_non_blank_text(data, "url", "请求地址")
    return data


def _impl_ensure_env_belongs_to_project(env: Env, project_id: int) -> None:
    if env.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="环境不属于该用例项目")


def _impl_ensure_project_exists(db: Session, project_id: int) -> None:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="项目不存在")


def _impl_ensure_env_exists(db: Session, env_id: int) -> Env:
    env = db.get(Env, env_id)
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="环境不存在")
    return env


def _impl_ensure_unique_username(db: Session, username: str, user_id: int | None = None) -> None:
    query = db.query(User).filter(User.username == username)
    if user_id is not None:
        query = query.filter(User.id != user_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")


def _impl_safe_file_response(raw_path: str | None) -> FileResponse:
    if not raw_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    file_path = Path(raw_path)
    if not file_path.is_absolute():
        file_path = BASE_DIR / file_path
    resolved = file_path.resolve()
    base = BASE_DIR.resolve()
    if base not in resolved.parents and resolved != base:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="禁止访问该文件")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    return FileResponse(resolved)


def _impl_latest_ai_config(db: Session) -> AiConfig | None:
    return db.query(AiConfig).order_by(AiConfig.id.desc()).first()


def _impl_serialize_ai_config(config: AiConfig | None) -> Dict[str, Any]:
    if not config:
        return {"provider": "openai_compatible", "base_url": "", "model": "", "api_key": "", "heal_enabled": 1, "heal_confidence_threshold": 0.7}
    data = serialize(config)
    data["api_key"] = ""
    return data


schema_data = _compat_wrapper(_impl_schema_data)
serialize = _compat_wrapper(_impl_serialize)
serialize_many = _compat_wrapper(_impl_serialize_many)
get_or_404 = _compat_wrapper(_impl_get_or_404)
normalize_json_fields = _compat_wrapper(_impl_normalize_json_fields)
require_non_blank_text = _compat_wrapper(_impl_require_non_blank_text)
normalize_project_payload = _compat_wrapper(_impl_normalize_project_payload)
normalize_env_payload = _compat_wrapper(_impl_normalize_env_payload)
normalize_api_case_payload = _compat_wrapper(_impl_normalize_api_case_payload)
ensure_env_belongs_to_project = _compat_wrapper(_impl_ensure_env_belongs_to_project)
ensure_project_exists = _compat_wrapper(_impl_ensure_project_exists)
ensure_env_exists = _compat_wrapper(_impl_ensure_env_exists)
ensure_unique_username = _compat_wrapper(_impl_ensure_unique_username)
safe_file_response = _compat_wrapper(_impl_safe_file_response)
latest_ai_config = _compat_wrapper(_impl_latest_ai_config)
serialize_ai_config = _compat_wrapper(_impl_serialize_ai_config)
