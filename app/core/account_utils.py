from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    "ACCOUNT_CONFIG_FIELDS",
    "Fernet",
    "FunctionalCase",
    "FunctionalTask",
    "HTTPException",
    "InvalidToken",
    "SECRET_KEY",
    "SENSITIVE_ACCOUNT_KEY_NAMES",
    "SENSITIVE_ACCOUNT_KEY_RE",
    "TestAccountBinding",
    "TestAccountProfile",
    "UiCase",
    "account_binding_profile",
    "account_cipher",
    "account_profile_variables",
    "base64",
    "datetime",
    "decrypt_account_payload",
    "default_account_profile_for_target",
    "encrypt_account_payload",
    "ensure_project_exists",
    "get_or_404",
    "hashlib",
    "is_sensitive_account_key",
    "json",
    "parse_json_value",
    "status",
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


def _impl_is_sensitive_account_key(key: Any) -> bool:
    text = str(key or "").strip()
    return text.lower() in SENSITIVE_ACCOUNT_KEY_NAMES or bool(SENSITIVE_ACCOUNT_KEY_RE.search(text))


def _impl_mask_variables(variables: Dict[str, Any]) -> Dict[str, Any]:
    return {key: ("***" if is_sensitive_account_key(key) else value) for key, value in (variables or {}).items()}


def _impl_account_cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(str(SECRET_KEY).encode("utf-8")).digest())
    return Fernet(key)


def _impl_encrypt_account_payload(values: Dict[str, Any]) -> str:
    if not values:
        return ""
    raw = json.dumps(values, ensure_ascii=False, default=str).encode("utf-8")
    return account_cipher().encrypt(raw).decode("utf-8")


def _impl_decrypt_account_payload(value: str | None) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        decrypted = account_cipher().decrypt(str(value).encode("utf-8")).decode("utf-8")
        return parse_json_value(decrypted, {})
    except (InvalidToken, ValueError, TypeError):
        legacy = parse_json_value(str(value), {})
        return legacy if isinstance(legacy, dict) else {}


def _impl_normalize_account_payload(db: Session, data: Dict[str, Any], existing: TestAccountProfile | None = None) -> Dict[str, Any]:
    if "profile_name" in data and data["profile_name"] is not None:
        data["profile_name"] = str(data["profile_name"]).strip()
        if not data["profile_name"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号档案名称不能为空")
    if "project_id" in data and data["project_id"] is not None:
        ensure_project_exists(db, int(data["project_id"]))
        data["project_id"] = int(data["project_id"])
    for field in ACCOUNT_CONFIG_FIELDS:
        if field in data and data[field] is not None:
            data[field] = str(data[field]).strip()
    public_source = data.pop("variables", None)
    sensitive_source = data.pop("sensitive_variables", None)
    if public_source is not None or sensitive_source is not None:
        public_values: Dict[str, Any] = (
            parse_json_value(existing.variables or "", {}) if existing is not None and public_source is None else {}
        )
        if not isinstance(public_values, dict):
            public_values = {}
        sensitive_values: Dict[str, Any] = (
            decrypt_account_payload(existing.sensitive_variables) if existing is not None and sensitive_source is None else {}
        )
        sensitive_changed = sensitive_source is not None
        if public_source is not None:
            for key, value in dict(public_source or {}).items():
                if value is None:
                    continue
                if is_sensitive_account_key(key):
                    sensitive_values[str(key)] = value
                    sensitive_changed = True
                else:
                    public_values[str(key)] = value
        for key, value in dict(sensitive_source or {}).items():
            if value is not None:
                sensitive_values[str(key)] = value
        data["variables"] = to_json_text(public_values, {})
        if sensitive_changed:
            data["sensitive_variables"] = encrypt_account_payload(sensitive_values)
    elif existing is not None:
        data.pop("variables", None)
        data.pop("sensitive_variables", None)
    if "status" in data and data["status"]:
        data["status"] = str(data["status"])
    return data


def _impl_serialize_account_profile(profile: TestAccountProfile) -> Dict[str, Any]:
    public_values = parse_json_value(profile.variables or "", {})
    if not isinstance(public_values, dict):
        public_values = {}
    sensitive_values = decrypt_account_payload(profile.sensitive_variables)
    masked = {**public_values, **{key: "***" for key in sensitive_values.keys()}}
    return {
        "id": profile.id,
        "project_id": profile.project_id,
        "profile_name": profile.profile_name,
        "variables": public_values,
        "masked_variables": masked,
        "sensitive_keys": sorted(sensitive_values.keys()),
        "login_url": profile.login_url or "",
        "username_locator": profile.username_locator or "",
        "password_locator": profile.password_locator or "",
        "submit_locator": profile.submit_locator or "",
        "success_url_contains": profile.success_url_contains or "",
        "success_selector": profile.success_selector or "",
        "browser_session_status": profile.browser_session_status or "empty",
        "browser_session_validated_at": profile.browser_session_validated_at.strftime("%Y-%m-%d %H:%M:%S") if profile.browser_session_validated_at else "",
        "browser_session_cleared_at": profile.browser_session_cleared_at.strftime("%Y-%m-%d %H:%M:%S") if profile.browser_session_cleared_at else "",
        "status": profile.status,
        "create_time": profile.create_time.strftime("%Y-%m-%d %H:%M:%S") if profile.create_time else "",
        "update_time": profile.update_time.strftime("%Y-%m-%d %H:%M:%S") if profile.update_time else "",
    }


def _impl_account_profile_variables(db: Session, profile_id: int, project_id: int | None) -> tuple[Dict[str, Any], Dict[str, Any]]:
    profile = get_or_404(db, TestAccountProfile, profile_id)
    if profile.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号档案未启用")
    if profile.project_id is not None and project_id is not None and profile.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号档案不属于当前项目")
    public_values = parse_json_value(profile.variables or "", {})
    if not isinstance(public_values, dict):
        public_values = {}
    variables = {**public_values, **decrypt_account_payload(profile.sensitive_variables)}
    login_config = {field: getattr(profile, field) or "" for field in ACCOUNT_CONFIG_FIELDS}
    return variables, {"id": profile.id, "profile_name": profile.profile_name, "login_config": login_config}


def _impl_account_target_project_id(db: Session, target_type: str, target_id: int) -> int:
    if target_type == "project":
        ensure_project_exists(db, target_id)
        return target_id
    elif target_type == "functional_task":
        item = get_or_404(db, FunctionalTask, target_id)
        return item.project_id
    elif target_type == "functional_case":
        item = get_or_404(db, FunctionalCase, target_id)
        task = get_or_404(db, FunctionalTask, item.task_id)
        return task.project_id
    elif target_type == "ui_case":
        item = get_or_404(db, UiCase, target_id)
        return item.project_id
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的账号绑定目标")


def _impl_account_binding_profile(db: Session, target_type: str, target_id: int) -> TestAccountProfile | None:
    binding = db.query(TestAccountBinding).filter(
        TestAccountBinding.target_type == target_type,
        TestAccountBinding.target_id == target_id,
    ).first()
    if not binding or not binding.account_profile_id:
        return None
    return db.get(TestAccountProfile, binding.account_profile_id)


def _impl_account_profile_summary(profile: TestAccountProfile | None) -> Dict[str, Any]:
    if not profile:
        return {"account_profile_id": None, "account_profile_name": ""}
    return {"account_profile_id": profile.id, "account_profile_name": profile.profile_name}


def _impl_default_account_profile_for_target(
    db: Session,
    target_type: str,
    target_id: int,
    project_id: int | None,
) -> TestAccountProfile | None:
    if target_type == "functional_case":
        case_profile = account_binding_profile(db, "functional_case", target_id)
        if case_profile:
            return case_profile
        functional_case = db.get(FunctionalCase, target_id)
        if functional_case:
            task_profile = account_binding_profile(db, "functional_task", functional_case.task_id)
            if task_profile:
                return task_profile
    elif target_type in {"functional_task", "ui_case"}:
        direct_profile = account_binding_profile(db, target_type, target_id)
        if direct_profile:
            return direct_profile
    if project_id is not None:
        project_profile = account_binding_profile(db, "project", project_id)
        if project_profile:
            return project_profile
        project_profiles = (
            db.query(TestAccountProfile)
            .filter(TestAccountProfile.project_id == project_id, TestAccountProfile.status == "active")
            .order_by(TestAccountProfile.id.asc())
            .all()
        )
        if len(project_profiles) == 1:
            return project_profiles[0]
    return None


def _impl_resolve_execution_account(
    db: Session,
    payload: FunctionalExecuteRequest | None,
    target_type: str,
    target_id: int,
    project_id: int | None,
    target_url: str,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    runtime_vars = dict(payload.variables if payload else {})
    account_mode = (payload.account_mode if payload else "default") or "default"
    if account_mode == "none":
        return runtime_vars, {}
    profile: TestAccountProfile | None = None
    if account_mode == "override":
        if payload and payload.account_profile_id:
            profile = get_or_404(db, TestAccountProfile, payload.account_profile_id)
        else:
            return runtime_vars, {}
    else:
        profile = default_account_profile_for_target(db, target_type, target_id, project_id)
    if not profile:
        return runtime_vars, {}
    account_vars, meta = account_profile_variables(db, profile.id, project_id)
    variables = {**account_vars, **runtime_vars}
    login_config = meta.get("login_config") or {}
    stored = decrypt_account_payload(profile.browser_state_encrypted) if profile.browser_state_encrypted else {}
    storage_state = stored.get("storage_state") if isinstance(stored, dict) else None
    has_valid_session = bool(isinstance(storage_state, dict) and profile.browser_session_status == "valid")
    has_explicit_login = bool(login_config.get("login_url"))

    execution_context = {
        "account_profile_id": profile.id,
        "login_config": login_config,
        "target_url": target_url,
    }
    if isinstance(storage_state, dict):
        execution_context["storage_state"] = storage_state
    if has_valid_session:
        execution_context["preauthenticated"] = True
        execution_context["login_required"] = False
    else:
        execution_context["login_required"] = has_explicit_login
    return variables, execution_context


def _impl_save_test_account_binding(db: Session, target_type: str, target_id: int, account_profile_id: int | None) -> None:
    existing = db.query(TestAccountBinding).filter(
        TestAccountBinding.target_type == target_type,
        TestAccountBinding.target_id == target_id,
    ).first()
    if existing and account_profile_id is not None:
        existing.account_profile_id = account_profile_id
        existing.update_time = datetime.now()
    elif existing and account_profile_id is None:
        db.delete(existing)
    elif not existing and account_profile_id is not None:
        db.add(TestAccountBinding(
            target_type=target_type,
            target_id=target_id,
            account_profile_id=account_profile_id,
            create_time=datetime.now(),
            update_time=None,
        ))
    else:
        return
    db.flush()


is_sensitive_account_key = _compat_wrapper(_impl_is_sensitive_account_key)
mask_variables = _compat_wrapper(_impl_mask_variables)
account_cipher = _compat_wrapper(_impl_account_cipher)
encrypt_account_payload = _compat_wrapper(_impl_encrypt_account_payload)
decrypt_account_payload = _compat_wrapper(_impl_decrypt_account_payload)
normalize_account_payload = _compat_wrapper(_impl_normalize_account_payload)
serialize_account_profile = _compat_wrapper(_impl_serialize_account_profile)
account_profile_variables = _compat_wrapper(_impl_account_profile_variables)
account_target_project_id = _compat_wrapper(_impl_account_target_project_id)
account_binding_profile = _compat_wrapper(_impl_account_binding_profile)
account_profile_summary = _compat_wrapper(_impl_account_profile_summary)
default_account_profile_for_target = _compat_wrapper(_impl_default_account_profile_for_target)
resolve_execution_account = _compat_wrapper(_impl_resolve_execution_account)
save_test_account_binding = _compat_wrapper(_impl_save_test_account_binding)
