from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    "ApiCase",
    "DATA_SCRIPT_API_CASES",
    "Env",
    "FRONTEND_UNIVERSAL_ACCOUNT_PASSWORD",
    "HTTPException",
    "LOGIN_CASE_NAME",
    "apply_frontend_customer_login_variables",
    "ensure_project_exists",
    "find_data_script_project",
    "get_or_404",
    "or_",
    "parse_json_value",
    "re",
    "split_customer_ids",
    "status",
    "strip_case_name_prefix",
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


def _impl_split_customer_ids(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    raw_items = value if isinstance(value, list) else [value]
    customer_ids: list[str] = []
    for raw_item in raw_items:
        if raw_item in (None, ""):
            continue
        for item in re.split(r"[\s,，;；]+", str(raw_item).strip()):
            customer_id = item.strip()
            if not customer_id:
                continue
            if not re.fullmatch(r"\d+", customer_id):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"客户ID只能是数字：{customer_id}")
            customer_ids.append(customer_id)
    return customer_ids


def _impl_apply_frontend_customer_login_variables(variables: Dict[str, Any]) -> Dict[str, Any]:
    customer_ids = split_customer_ids(variables.get("customer_id"))
    if not customer_ids:
        customer_ids = split_customer_ids(variables.get("customer_ids"))
    if not customer_ids:
        return variables
    customer_id = customer_ids[0]
    variables["customer_id"] = customer_id
    variables["customer_ids"] = customer_ids
    variables["account"] = f"userID/{customer_id}In"
    variables["password"] = FRONTEND_UNIVERSAL_ACCOUNT_PASSWORD
    return variables


def _impl_resolve_data_script_context(db: Session, payload: DataScriptExecuteRequest) -> tuple[Env, int]:
    project_id = int(payload.project_id) if payload.project_id is not None else None
    if project_id is not None:
        ensure_project_exists(db, project_id)
    if payload.env_id:
        env = get_or_404(db, Env, payload.env_id)
        if project_id is not None and env.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="环境不属于所选项目")
        return env, env.project_id
    query = db.query(Env)
    if project_id is not None:
        query = query.filter(Env.project_id == project_id)
    else:
        data_script_project = find_data_script_project(db)
        if data_script_project:
            query = query.filter(Env.project_id == data_script_project.id)
    env = query.order_by(Env.id.asc()).first()
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先配置环境")
    return env, env.project_id


def _impl_data_script_variables(db: Session, variables: Dict[str, Any] | None, project_id: int | None = None) -> Dict[str, Any]:
    merged = dict(variables or {})
    configured_paths = {}

    # 批量查询：一次性查出所有相关 ApiCase，避免 ~40 次循环 x 4 种匹配的 N+1 查询
    all_search_names = set()
    all_urls = set()
    for item in DATA_SCRIPT_API_CASES:
        all_search_names.add(item["case_name"])
        all_search_names.add(strip_case_name_prefix(item["case_name"]))
        all_urls.add(item["url"])
    batch_query = db.query(ApiCase).filter(
        or_(ApiCase.case_name.in_(all_search_names), ApiCase.url.in_(all_urls))
    )
    if project_id is not None:
        batch_query = batch_query.filter(ApiCase.project_id == project_id)
    all_cases = batch_query.order_by(ApiCase.id.asc()).all()

    # 构建内存索引，沿用原有 4 级匹配优先级
    case_by_name: Dict[str, ApiCase] = {}
    case_by_name_url: Dict[tuple[str, str], ApiCase] = {}
    case_by_url_first: Dict[str, ApiCase] = {}
    for c in all_cases:
        if c.case_name not in case_by_name:
            case_by_name[c.case_name] = c
        key_nu = (c.case_name, c.url)
        if key_nu not in case_by_name_url:
            case_by_name_url[key_nu] = c
        if c.url not in case_by_url_first:
            case_by_url_first[c.url] = c

    for item in DATA_SCRIPT_API_CASES:
        legacy_name = item["case_name"]
        case_name = strip_case_name_prefix(legacy_name)
        url = item["url"]
        case = (
            case_by_name.get(legacy_name)
            or case_by_name_url.get((case_name, url))
            or case_by_url_first.get(url)
            or case_by_name.get(case_name)
        )
        configured_paths[item["key"]] = case.url if case else item["url"]
    custom_paths = merged.get("api_paths") if isinstance(merged.get("api_paths"), dict) else {}
    merged["api_paths"] = {**configured_paths, **custom_paths}
    login_case_query = db.query(ApiCase).filter(ApiCase.case_name == LOGIN_CASE_NAME)
    if project_id is not None:
        login_case_query = login_case_query.filter(ApiCase.project_id == project_id)
    login_case = login_case_query.order_by(ApiCase.id.asc()).first()
    login_body = parse_json_value(login_case.body, {}) if login_case else {}
    if isinstance(login_body, dict):
        for key in ["account", "password", "client_tool"]:
            default_value = login_body.get(key)
            if default_value in (None, ""):
                continue
            current_value = merged.get(key)
            is_old_seed = (key == "account" and current_value == "abner") or (key == "password" and current_value == "12345")
            if current_value in (None, "") or is_old_seed:
                merged[key] = default_value
    return apply_frontend_customer_login_variables(merged)


split_customer_ids = _compat_wrapper(_impl_split_customer_ids)
apply_frontend_customer_login_variables = _compat_wrapper(_impl_apply_frontend_customer_login_variables)
resolve_data_script_context = _compat_wrapper(_impl_resolve_data_script_context)
data_script_variables = _compat_wrapper(_impl_data_script_variables)
