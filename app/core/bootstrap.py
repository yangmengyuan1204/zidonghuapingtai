from __future__ import annotations

import sys
from functools import wraps
from .data_script_catalog import (
    CASE_NAME_PREFIXES,
    DATA_SCRIPT_PROJECT_NAME,
    LOGIN_CASE_NAME,
    CART_CASE_NAME,
    FRONTEND_UNIVERSAL_ACCOUNT_PASSWORD,
    DATA_SCRIPT_API_CASES,
    OEM_DATA_SCRIPT_PROJECT_NAME,
    OEM_BASE_URL,
    OEM_ADMIN_ORIGIN,
    OEM_FRONTEND_ORIGIN,
    OEM_DATA_SCRIPT_API_CASES,
)
import os














_COMPAT_NAMES = (
    "ApiCase",
    "Base",
    "CASE_NAME_PREFIXES",
    "DATA_SCRIPT_API_CASES",
    "DATA_SCRIPT_PROJECT_NAME",
    "Env",
    "OEM_ADMIN_ORIGIN",
    "OEM_BASE_URL",
    "OEM_DATA_SCRIPT_API_CASES",
    "OEM_DATA_SCRIPT_PROJECT_NAME",
    "OEM_FRONTEND_ORIGIN",
    "Project",
    "User",
    "datetime",
    "engine",
    "ensure_data_script_api_cases",
    "ensure_oem_data_script_api_cases",
    "ensure_report_dirs",
    "find_data_script_api_case",
    "find_data_script_project",
    "find_oem_data_script_api_case",
    "find_oem_data_script_project",
    "get_db",
    "hash_password",
    "is_password_hash",
    "logger",
    "migrate_legacy_plaintext_passwords",
    "normalize_api_case_names",
    "os",
    "secrets",
    "strip_case_name_prefix",
    "text",
    "to_json_text",
    "verify_password",
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


def _impl_strip_case_name_prefix(value: Any) -> str:
    text = str(value or "").strip()
    changed = True
    while changed:
        changed = False
        for prefix in CASE_NAME_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
                changed = True
    return text


def _impl_normalize_api_case_names(db: Session) -> None:
    changed = False
    for case in db.query(ApiCase).all():
        normalized = strip_case_name_prefix(case.case_name)
        if normalized and normalized != case.case_name:
            case.case_name = normalized
            changed = True
    if changed:
        db.commit()


def _impl_migrate_legacy_plaintext_passwords(db: Session) -> None:
    changed = 0
    for user in db.query(User).all():
        stored = str(user.password or "")
        if stored and not is_password_hash(stored):
            user.password = hash_password(stored)
            changed += 1
    if changed:
        db.commit()
        print(f"Migrated {changed} legacy plaintext user password(s) to bcrypt.", flush=True)


def _impl_find_data_script_project(db: Session) -> Project | None:
    return db.query(Project).filter(Project.name == DATA_SCRIPT_PROJECT_NAME).order_by(Project.id.asc()).first()


def _impl_find_data_script_api_case(db: Session, item: Dict[str, Any], project_id: int | None = None) -> ApiCase | None:
    case_name = strip_case_name_prefix(item["case_name"])
    legacy_name = item["case_name"]
    url = item["url"]
    queries = [
        db.query(ApiCase).filter(ApiCase.case_name == legacy_name),
        db.query(ApiCase).filter(ApiCase.case_name == case_name, ApiCase.url == url),
        db.query(ApiCase).filter(ApiCase.url == url),
        db.query(ApiCase).filter(ApiCase.case_name == case_name),
    ]
    for query in queries:
        if project_id is not None:
            query = query.filter(ApiCase.project_id == project_id)
        case = query.order_by(ApiCase.id.asc()).first()
        if case:
            return case
    return None


def _impl_ensure_data_script_api_cases(db: Session) -> None:
    project = find_data_script_project(db)
    if not project:
        project = Project(name=DATA_SCRIPT_PROJECT_NAME, desc="系统自动创建", create_time=datetime.now())
        db.add(project)
        db.commit()
        db.refresh(project)

    env = db.query(Env).filter(Env.project_id == project.id).order_by(Env.id.asc()).first()
    if not env:
        env = Env(
            project_id=project.id,
            env_name=project.name or "test-\u6570\u636e\u811a\u672c",
            base_url="https://jpapi.rakumart.cn",
            global_headers=to_json_text({}, {}),
            global_vars=to_json_text({"api": "https://jpapi.rakumart.cn"}, {}),
            timeout=30,
        )
        db.add(env)
        db.commit()
        db.refresh(env)

    for item in DATA_SCRIPT_API_CASES:
        case_name = strip_case_name_prefix(item["case_name"])
        exists = find_data_script_api_case(db, item, env.project_id) or find_data_script_api_case(db, item)
        if exists:
            exists.case_name = case_name
            exists.project_id = env.project_id
            exists.env_id = env.id
            key = str(item.get("key", ""))
            if item.get("key") in {"client_warehouse_list", "client_porder_create"} or key.startswith(("admin_porder_", "admin_spot_")):
                assert_rule = {"status_code": 200}
                if item.get("extract"):
                    assert_rule["extract"] = item["extract"]
                exists.url = item["url"]
                exists.body = to_json_text(item["body"], {})
                exists.assert_rule = to_json_text(assert_rule, {})
                exists.headers = to_json_text({"Content-Type": "multipart/form-data"}, {})
            continue
        assert_rule = {"status_code": 200}
        if item.get("extract"):
            assert_rule["extract"] = item["extract"]
        db.add(
            ApiCase(
                project_id=env.project_id,
                env_id=env.id,
                case_name=case_name,
                method="POST",
                url=item["url"],
                headers=to_json_text({"Content-Type": "multipart/form-data"}, {}),
                params=to_json_text({}, {}),
                body=to_json_text(item["body"], {}),
                assert_rule=to_json_text(assert_rule, {}),
                status="active",
                create_time=datetime.now(),
            )
        )
    db.commit()


def _impl_find_oem_data_script_project(db: Session) -> Project | None:
    return db.query(Project).filter(Project.name == OEM_DATA_SCRIPT_PROJECT_NAME).order_by(Project.id.asc()).first()


def _impl_find_oem_data_script_api_case(db: Session, item: Dict[str, Any], project_id: int | None = None) -> ApiCase | None:
    case_name = strip_case_name_prefix(item["case_name"])
    url = item["url"]
    query = db.query(ApiCase).filter(ApiCase.url == url)
    if project_id is not None:
        query = query.filter(ApiCase.project_id == project_id)
    return query.order_by(ApiCase.id.asc()).first()


def _impl_ensure_oem_data_script_api_cases(db: Session) -> None:
    """初始化 OEM 独立项目/环境变量/接口用例库，与日本站完全隔离。"""
    project = find_oem_data_script_project(db)
    if not project:
        project = Project(name=OEM_DATA_SCRIPT_PROJECT_NAME, desc="系统自动创建", create_time=datetime.now())
        db.add(project)
        db.commit()
        db.refresh(project)

    env = db.query(Env).filter(Env.project_id == project.id).order_by(Env.id.asc()).first()
    if not env:
        env = Env(
            project_id=project.id,
            env_name=project.name or "OEM-数据脚本",
            base_url=OEM_BASE_URL,
            global_headers=to_json_text({}, {}),
            global_vars=to_json_text(
                {
                    "api": OEM_BASE_URL,
                    "backend_manage_origin": OEM_ADMIN_ORIGIN,
                    "frontend_origin": OEM_FRONTEND_ORIGIN,
                },
                {},
            ),
            timeout=30,
        )
        db.add(env)
        db.commit()
        db.refresh(env)

    for item in OEM_DATA_SCRIPT_API_CASES:
        case_name = strip_case_name_prefix(item["case_name"])
        exists = find_oem_data_script_api_case(db, item, env.project_id)
        if exists:
            exists.case_name = case_name
            exists.project_id = env.project_id
            exists.env_id = env.id
            exists.url = item["url"]
            exists.body = to_json_text(item["body"], {})
            assert_rule = {"status_code": 200}
            if item.get("extract"):
                assert_rule["extract"] = item["extract"]
            exists.assert_rule = to_json_text(assert_rule, {})
            exists.headers = to_json_text({"Content-Type": "application/json"}, {})
            continue
        assert_rule = {"status_code": 200}
        if item.get("extract"):
            assert_rule["extract"] = item["extract"]
        db.add(
            ApiCase(
                project_id=env.project_id,
                env_id=env.id,
                case_name=case_name,
                method="POST",
                url=item["url"],
                headers=to_json_text({"Content-Type": "application/json"}, {}),
                params=to_json_text({}, {}),
                body=to_json_text(item["body"], {}),
                assert_rule=to_json_text(assert_rule, {}),
                status="active",
                create_time=datetime.now(),
            )
        )
    db.commit()


def _impl_init_app() -> None:
    Base.metadata.create_all(bind=engine)
    # 轻量迁移：补齐历史 SQLite 数据库缺失列。
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        migrations = {
            "functional_case": {
                "test_result": "ALTER TABLE functional_case ADD COLUMN test_result VARCHAR(20) DEFAULT 'untested'",
                "category": "ALTER TABLE functional_case ADD COLUMN category VARCHAR(40)",
                "quality_status": "ALTER TABLE functional_case ADD COLUMN quality_status VARCHAR(32) DEFAULT 'unchecked'",
                "quality_report": "ALTER TABLE functional_case ADD COLUMN quality_report TEXT",
                "failure_count": "ALTER TABLE functional_case ADD COLUMN failure_count INTEGER DEFAULT 0",
            },
            "test_record": {
                "project_id": "ALTER TABLE test_record ADD COLUMN project_id INTEGER",
            },
            "test_account_profile": {
                "login_url": "ALTER TABLE test_account_profile ADD COLUMN login_url VARCHAR(500)",
                "username_locator": "ALTER TABLE test_account_profile ADD COLUMN username_locator TEXT",
                "password_locator": "ALTER TABLE test_account_profile ADD COLUMN password_locator TEXT",
                "submit_locator": "ALTER TABLE test_account_profile ADD COLUMN submit_locator TEXT",
                "success_url_contains": "ALTER TABLE test_account_profile ADD COLUMN success_url_contains VARCHAR(500)",
                "success_selector": "ALTER TABLE test_account_profile ADD COLUMN success_selector VARCHAR(500)",
            },
            "case_generation_screenshot": {
                "ocr_text": "ALTER TABLE case_generation_screenshot ADD COLUMN ocr_text TEXT",
                "corrected_text": "ALTER TABLE case_generation_screenshot ADD COLUMN corrected_text TEXT",
                "ocr_confidence": "ALTER TABLE case_generation_screenshot ADD COLUMN ocr_confidence FLOAT",
                "low_confidence_items": "ALTER TABLE case_generation_screenshot ADD COLUMN low_confidence_items TEXT",
                "regions": "ALTER TABLE case_generation_screenshot ADD COLUMN regions TEXT",
                "needs_manual_confirm": "ALTER TABLE case_generation_screenshot ADD COLUMN needs_manual_confirm INTEGER DEFAULT 1",
                "ocr_error": "ALTER TABLE case_generation_screenshot ADD COLUMN ocr_error TEXT",
            },
            "locator_heal_log": {
                "step_action": "ALTER TABLE locator_heal_log ADD COLUMN step_action VARCHAR(32)",
                "ai_prompt": "ALTER TABLE locator_heal_log ADD COLUMN ai_prompt TEXT",
                "ai_response": "ALTER TABLE locator_heal_log ADD COLUMN ai_response TEXT",
                "auto_applied": "ALTER TABLE locator_heal_log ADD COLUMN auto_applied INTEGER DEFAULT 0",
            },
            "ai_config": {
                "heal_enabled": "ALTER TABLE ai_config ADD COLUMN heal_enabled INTEGER DEFAULT 1",
                "heal_confidence_threshold": "ALTER TABLE ai_config ADD COLUMN heal_confidence_threshold FLOAT DEFAULT 0.7",
            },
            "recorded_flow": {
                "base_url": "ALTER TABLE recorded_flow ADD COLUMN base_url VARCHAR(255)",
            },
            "recorded_flow_step": {
                "full_url": "ALTER TABLE recorded_flow_step ADD COLUMN full_url VARCHAR(1000)",
            },
        }
        with engine.begin() as conn:
            for table_name, table_migrations in migrations.items():
                existing_columns = {c["name"] for c in inspector.get_columns(table_name)}
                for column_name, sql in table_migrations.items():
                    if column_name not in existing_columns:
                        conn.execute(text(sql))
    except Exception as exc:
        logger.warning("数据库迁移失败（不影响启动）: %s", exc)
    ensure_report_dirs()
    db = next(get_db())
    try:
        migrate_legacy_plaintext_passwords(db)
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
            db.add(
                User(
                    username="admin",
                    password=hash_password(admin_password),
                    role="admin",
                    create_time=datetime.now(),
                )
            )
            db.commit()
            if not os.getenv("DEFAULT_ADMIN_PASSWORD"):
                print(
                    "Created default admin user. Password: "
                    f"{admin_password}. Set DEFAULT_ADMIN_PASSWORD to control this value.",
                    flush=True,
                )
        elif verify_password("admin123", admin.password) and os.getenv("ALLOW_DEFAULT_ADMIN_PASSWORD", "").strip() != "1":
            replacement_password = os.getenv("DEFAULT_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
            if replacement_password != "admin123":
                admin.password = hash_password(replacement_password)
                db.commit()
                print(
                    "Rotated insecure default admin password. New password: "
                    f"{replacement_password}. Set DEFAULT_ADMIN_PASSWORD to control this value.",
                    flush=True,
                )
        normalize_api_case_names(db)
        ensure_data_script_api_cases(db)
        ensure_oem_data_script_api_cases(db)
    finally:
        db.close()


strip_case_name_prefix = _compat_wrapper(_impl_strip_case_name_prefix)
normalize_api_case_names = _compat_wrapper(_impl_normalize_api_case_names)
migrate_legacy_plaintext_passwords = _compat_wrapper(_impl_migrate_legacy_plaintext_passwords)
find_data_script_project = _compat_wrapper(_impl_find_data_script_project)
find_data_script_api_case = _compat_wrapper(_impl_find_data_script_api_case)
ensure_data_script_api_cases = _compat_wrapper(_impl_ensure_data_script_api_cases)
find_oem_data_script_project = _compat_wrapper(_impl_find_oem_data_script_project)
find_oem_data_script_api_case = _compat_wrapper(_impl_find_oem_data_script_api_case)
ensure_oem_data_script_api_cases = _compat_wrapper(_impl_ensure_oem_data_script_api_cases)
init_app = _compat_wrapper(_impl_init_app)
