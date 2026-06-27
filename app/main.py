import hashlib
import logging
import os
import re
import secrets
import socket
import threading
import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Type
from urllib.parse import urljoin, urlparse
from uuid import uuid4

logger = logging.getLogger(__name__)

import requests
from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from sqlalchemy import func, or_, text
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from .database import Base, engine, get_db, safe_commit
from .executors import ensure_report_dirs, execute_api_case, execute_ui_case, execute_ui_cases_batch, parse_json_value, to_json_text
from .models import (
    ActionTemplate,
    AiConfig,
    ApiCase,
    Env,
    FunctionalCase,
    FunctionalDataCheckResult,
    FunctionalDataCheckRule,
    FunctionalImpactItem,
    FunctionalRequirementNote,
    FunctionalRun,
    FunctionalScreenshot,
    FunctionalTask,
    LocatorHealLog,
    PageSnapshot,
    Project,
    TestRecord,
    TestAccountBinding,
    TestAccountProfile,
    CaseGenerationCase,
    CaseGenerationRequirementNote,
    CaseGenerationScreenshot,
    CaseGenerationTask,
    UiCase,
    User,
)
from .schemas import (
    ActionTemplateCreate,
    ActionTemplateUpdate,
    AiConfigUpdate,
    ApiBatchExecuteRequest,
    ApiCaseCreate,
    ApiCaseUpdate,
    ApiExecuteRequest,
    DataScriptExecuteRequest,
    EnvCreate,
    EnvUpdate,
    FunctionalExecuteRequest,
    LocatorHealLogConfirm,
    LoginRequest,
    PreflightResult,
    ProjectCreate,
    ProjectUpdate,
    QuickRunRequest,
    TestAccountBindingUpdate,
    TestAccountProfileCreate,
    TestAccountProfileUpdate,
    UiCaseCreate,
    UiCaseUpdate,
    UserCreate,
    UserUpdate,
)
from .security import SECRET_KEY, create_access_token, get_current_user, hash_password, is_password_hash, require_admin, verify_password
from .services.requirement_workflow import build_workflow_status

from .core.utils import (
    BASE_DIR,
    STATIC_DIR,
    TABLE_FIELDS,
    JSON_FIELD_DEFAULTS,
    ACCOUNT_CONFIG_FIELDS,
    CASE_NAME_PREFIXES,
    API_ALLOWED_METHODS,
    ACTION_TEMPLATE_JSON_DEFAULTS,
    FUNCTIONAL_TEST_RESULTS,
    DATA_SCRIPT_PROJECT_NAME,
    LOGIN_CASE_NAME,
    CART_CASE_NAME,
    FRONTEND_UNIVERSAL_ACCOUNT_PASSWORD,
    DATA_SCRIPT_API_CASES,
    PROXY_ALLOWED_METHODS,
    PROXY_ALLOW_PRIVATE_URLS,
    PROXY_MAX_REDIRECTS,
    SENSITIVE_ACCOUNT_KEY_RE,
    SENSITIVE_ACCOUNT_KEY_NAMES,
    strip_case_name_prefix,
    normalize_api_case_names,
    migrate_legacy_plaintext_passwords,
    find_data_script_project,
    find_data_script_api_case,
    ensure_data_script_api_cases,
    init_app,
    schema_data,
    serialize,
    serialize_many,
    get_or_404,
    normalize_json_fields,
    require_non_blank_text,
    normalize_project_payload,
    normalize_env_payload,
    normalize_api_case_payload,
    ensure_env_belongs_to_project,
    ensure_project_exists,
    ensure_env_exists,
    ensure_unique_username,
    safe_file_response,
    latest_ai_config,
    serialize_ai_config,
    normalize_functional_result,
    functional_result_counts,
    latest_data_check_results_by_rule,
    functional_task_conclusion_summary,
    functional_task_detail,
    normalize_variable_name,
    quality_report_payload,
    parse_case_steps,
    functional_case_ui_payload,
    case_has_business_assertion,
    case_locator_issues,
    placeholder_names,
    seed_has_key,
    case_required_seed_keys,
    first_pattern_value,
    clean_seed_value,
    build_functional_seed_text,
    seed_functional_package_data,
    account_preflight_status,
    guess_functional_login_url,
    evaluate_functional_case_quality,
    functional_package_preflight_summary,
    preflight_functional_package,
    functional_task_keywords,
    keyword_score,
    impact_item_key,
    suggest_functional_impact_items,
    normalize_data_check_payload,
    full_data_check_url,
    lookup_nested_value,
    extract_response_value,
    normalize_compare_text,
    normalize_decimal_value,
    compare_data_check_values,
    execute_functional_data_check_rule,
    case_generation_case_is_protected,
    ensure_case_generation_workspace,
    case_generation_serialize_json,
    apply_case_generation_ocr_material,
    case_generation_task_proxy,
    case_generation_source_refs,
    case_generation_refs_include_screenshot,
    case_generation_refs_include_note,
    case_generation_stats,
    case_generation_detail,
    remove_uploaded_case_generation_file,
    case_generation_screenshot_impact,
    ensure_case_generation_task,
    save_ui_record,
    save_record,
    split_customer_ids,
    apply_frontend_customer_login_variables,
    resolve_data_script_context,
    data_script_variables,
    is_sensitive_account_key,
    mask_variables,
    account_cipher,
    encrypt_account_payload,
    decrypt_account_payload,
    normalize_account_payload,
    serialize_account_profile,
    account_profile_variables,
    account_target_project_id,
    account_binding_profile,
    account_profile_summary,
    default_account_profile_for_target,
    resolve_execution_account,
    save_test_account_binding,
    _serialize_template,
    _check_login_rate_limit,
    _record_login_attempt,
    ui_steps_have_strong_assertion,
    save_generated_functional_ui_steps,
    can_execute_functional_case,
    execute_functional_case_for_run,
    execute_functional_case_for_run_isolated,
    save_functional_run,
    proxy_ip_is_blocked,
    _resolve_and_check_hostname,
    validate_proxy_target,
    _origin,
    guarded_proxy_request,
)

from .core.cache import get as cache_get, set as cache_set, invalidate, invalidate_prefix
from .data_scripts import (
    preview_order_quote_options,
    run_balance_payment_script,
    run_bank_payment_script,
    run_direct_box_to_shelf_script,
    run_full_flow_script,
    run_order_quote_script,
    run_porder_balance_payment_script,
    run_porder_bank_payment_script,
    run_purchase_to_shelf_chain,
    run_purchase_to_shelf_script,
    run_resume_order_flow_script,
    run_resume_porder_flow_script,
    run_shopping_cart_script,
    run_warehouse_delivery_script,
)
from .functional_testing import scan_page_dom


# ─── App 初始化 ──────────────────────────────────────────


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_app()
    yield


app = FastAPI(title="接口 + UI 自动化测试平台", lifespan=lifespan)

# 保护「至少保留一个 admin」的序列化锁（SQLite 不支持 SELECT FOR UPDATE）
_admin_lock = threading.Lock()
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").strip()
allowed_origins = [origin.strip() for origin in CORS_ORIGINS.split(",") if origin.strip()] if CORS_ORIGINS else ["http://localhost:8000", "http://127.0.0.1:8000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def no_cache_frontend_assets(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/"):
        # 前端 JS/CSS 已使用版本号 query 参数做缓存破坏，可安全启用浏览器强缓存
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path == "/":
        # index.html 禁用缓存以确保新版本能被立即获取
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    ct = response.headers.get("content-type", "")
    if "application/json" in ct and "charset" not in ct.lower():
        response.headers["content-type"] = ct.replace("application/json", "application/json; charset=utf-8")
    return response


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ─── 三大模块路由器 ──────────────────────────────────────


from .routers.functional_tasks import router as functional_tasks_router
from .routers.case_generation import router as case_generation_router
from .routers.data_scripts import router as data_scripts_router

app.include_router(functional_tasks_router)
app.include_router(case_generation_router)
app.include_router(data_scripts_router)


# ═══════════════════════════════════════════════════════════
# 以下路由保留在 main.py 中（未迁移到模块）
# ═══════════════════════════════════════════════════════════


# ─── 基础 ────────────────────────────────────────────────


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> Dict[str, Any]:
    """健康检查端点。"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ─── 认证 ────────────────────────────────────────────────


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(client_ip, payload.username)
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password):
        _record_login_attempt(client_ip, payload.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_access_token(user.username)
    return {"access_token": token, "token_type": "bearer", "user": serialize(user)}


@app.get("/api/auth/me")
def me(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    cache_key = f"me:{current_user.username}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    result = serialize(current_user)
    cache_set(cache_key, result, ttl=120)
    return result


# ─── 仪表盘 ──────────────────────────────────────────────


@app.get("/api/dashboard")
def dashboard(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    # 一条组合查询获取 5 个 COUNT（代替 5~8 次独立查询）
    if project_id is not None:
        row = db.execute(
            text("""
                SELECT
                    (SELECT COUNT(*) FROM project WHERE id = :pid),
                    (SELECT COUNT(*) FROM env WHERE project_id = :pid),
                    (SELECT COUNT(*) FROM api_case WHERE project_id = :pid),
                    (SELECT COUNT(*) FROM ui_case WHERE project_id = :pid),
                    (SELECT COUNT(*) FROM test_record WHERE project_id = :pid)
            """),
            {"pid": project_id},
        ).one()
    else:
        row = db.execute(
            text("""
                SELECT
                    (SELECT COUNT(*) FROM project),
                    (SELECT COUNT(*) FROM env),
                    (SELECT COUNT(*) FROM api_case),
                    (SELECT COUNT(*) FROM ui_case),
                    (SELECT COUNT(*) FROM test_record)
            """),
        ).one()

    latest_records = db.query(TestRecord)
    if project_id is not None:
        latest_records = latest_records.filter(TestRecord.project_id == project_id)
    latest_records = latest_records.order_by(TestRecord.id.desc()).limit(10).all()

    return {
        "project_count": row[0],
        "env_count": row[1],
        "api_case_count": row[2],
        "ui_case_count": row[3],
        "record_count": row[4],
        "latest_records": serialize_many(latest_records),
        "role": current_user.role,
    }


# ─── 用户管理 ────────────────────────────────────────────


@app.get("/api/users")
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[Dict[str, Any]]:
    return serialize_many(db.query(User).order_by(User.id.desc()).all())


@app.post("/api/users")
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, Any]:
    data = schema_data(payload)
    ensure_unique_username(db, data["username"])
    user = User(
        username=data["username"],
        password=hash_password(data["password"]),
        role=data["role"],
        create_time=datetime.now(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return serialize(user)


@app.put("/api/users/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    user = get_or_404(db, User, user_id)
    data = schema_data(payload, exclude_unset=True)
    old_username = user.username
    if "username" in data:
        ensure_unique_username(db, data["username"], user_id)
        user.username = data["username"]
    if "password" in data and data["password"]:
        if not data["password"].strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码不能为纯空格")
        user.password = hash_password(data["password"])
    if "role" in data and data["role"]:
        with _admin_lock:
            if user.role == "admin" and data["role"] != "admin" and db.query(User).filter(User.role == "admin", User.id != user.id).count() < 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少保留一个 admin 账号")
            user.role = data["role"]
    db.commit()
    db.refresh(user)
    invalidate(f"me:{old_username}")
    invalidate(f"me:{user.username}")
    return serialize(user)


@app.delete("/api/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    user = get_or_404(db, User, user_id)
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前登录账号")
    with _admin_lock:
        if user.role == "admin" and db.query(User).filter(User.role == "admin", User.id != user.id).count() < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少保留一个 admin 账号")
        db.delete(user)
    db.commit()
    invalidate(f"me:{user.username}")
    return {"message": "deleted"}


# ─── 项目管理 ────────────────────────────────────────────


@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[Dict[str, Any]]:
    cached = cache_get("projects")
    if cached is not None:
        return cached
    projects = db.query(Project).order_by(Project.id.desc()).all()
    if not projects:
        return []

    project_ids = [p.id for p in projects]

    # 批量加载账号绑定关系（代替逐行查询的 N+1 模式）
    bindings: dict[int, int | None] = {}
    for row in (
        db.query(TestAccountBinding.target_id, TestAccountBinding.account_profile_id)
        .filter(
            TestAccountBinding.target_type == "project",
            TestAccountBinding.target_id.in_(project_ids),
        )
        .all()
    ):
        bindings[row[0]] = row[1]

    # 批量加载所有关联的账号配置
    bound_profile_ids = [pid for pid in bindings.values() if pid is not None]
    profiles_map: dict[int, TestAccountProfile] = {}
    if bound_profile_ids:
        for p in db.query(TestAccountProfile).filter(TestAccountProfile.id.in_(bound_profile_ids)).all():
            profiles_map[p.id] = p

    # 批量获取各项目下的「恰好一条有效账号」作为兜底
    fallback_profile: dict[int, TestAccountProfile] = {}
    for project_id in project_ids:
        projs = (
            db.query(TestAccountProfile)
            .filter(TestAccountProfile.project_id == project_id, TestAccountProfile.status == "active")
            .order_by(TestAccountProfile.id.asc())
            .all()
        )
        if len(projs) == 1:
            fallback_profile[project_id] = projs[0]

    result = []
    for project in projects:
        item = serialize(project)
        profile: TestAccountProfile | None = None
        pid = bindings.get(project.id)
        if pid and pid in profiles_map:
            profile = profiles_map[pid]
        if not profile and project.id in fallback_profile:
            profile = fallback_profile[project.id]
        item.update(account_profile_summary(profile))
        result.append(item)

    cache_set("projects", result, ttl=60)
    return result


@app.post("/api/projects")
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = normalize_project_payload(schema_data(payload), require_name=True)
    project = Project(name=data["name"], desc=data.get("desc") or "", create_time=datetime.now())
    db.add(project)
    db.commit()
    db.refresh(project)
    invalidate("projects")
    return serialize(project)


@app.put("/api/projects/{project_id}")
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    project = get_or_404(db, Project, project_id)
    data = normalize_project_payload(schema_data(payload, exclude_unset=True))
    for field in ["name", "desc"]:
        if field in data:
            setattr(project, field, data[field])
    db.commit()
    db.refresh(project)
    invalidate("projects")
    return serialize(project)


@app.delete("/api/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    project = get_or_404(db, Project, project_id)
    task_ids = [row[0] for row in db.query(FunctionalTask.id).filter(FunctionalTask.project_id == project_id).all()]
    functional_case_rows = (
        db.query(FunctionalCase.id, FunctionalCase.ui_case_id)
        .filter(FunctionalCase.task_id.in_(task_ids))
        .all()
        if task_ids
        else []
    )
    functional_case_ids = [row[0] for row in functional_case_rows]
    generated_ui_ids = [row[1] for row in functional_case_rows if row[1]]
    direct_ui_ids = [row[0] for row in db.query(UiCase.id).filter(UiCase.project_id == project_id).all()]
    ui_ids = sorted(set(direct_ui_ids + generated_ui_ids))
    api_ids = [row[0] for row in db.query(ApiCase.id).filter(ApiCase.project_id == project_id).all()]
    profile_ids = [row[0] for row in db.query(TestAccountProfile.id).filter(TestAccountProfile.project_id == project_id).all()]

    if api_ids:
        db.query(TestRecord).filter(TestRecord.case_type == "api", TestRecord.case_id.in_(api_ids)).delete(synchronize_session=False)
    if ui_ids:
        db.query(TestRecord).filter(TestRecord.case_type == "ui", TestRecord.case_id.in_(ui_ids)).delete(synchronize_session=False)
        db.query(LocatorHealLog).filter(LocatorHealLog.case_id.in_(ui_ids)).delete(synchronize_session=False)

    binding_filters = [
        (TestAccountBinding.target_type == "project") & (TestAccountBinding.target_id == project_id),
    ]
    if task_ids:
        binding_filters.append((TestAccountBinding.target_type == "functional_task") & TestAccountBinding.target_id.in_(task_ids))
    if functional_case_ids:
        binding_filters.append((TestAccountBinding.target_type == "functional_case") & TestAccountBinding.target_id.in_(functional_case_ids))
    if ui_ids:
        binding_filters.append((TestAccountBinding.target_type == "ui_case") & TestAccountBinding.target_id.in_(ui_ids))
    if profile_ids:
        db.query(TestAccountBinding).filter(TestAccountBinding.account_profile_id.in_(profile_ids)).delete(synchronize_session=False)
    db.query(TestAccountBinding).filter(or_(*binding_filters)).delete(synchronize_session=False)

    if task_ids:
        db.query(PageSnapshot).filter(PageSnapshot.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalScreenshot).filter(FunctionalScreenshot.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalRequirementNote).filter(FunctionalRequirementNote.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalRun).filter(FunctionalRun.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalImpactItem).filter(FunctionalImpactItem.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalDataCheckResult).filter(FunctionalDataCheckResult.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalDataCheckRule).filter(FunctionalDataCheckRule.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalCase).filter(FunctionalCase.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalTask).filter(FunctionalTask.id.in_(task_ids)).delete(synchronize_session=False)
    cg_task_ids = [row[0] for row in db.query(CaseGenerationTask.id).filter(CaseGenerationTask.project_id == project_id).all()]
    if cg_task_ids:
        db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id.in_(cg_task_ids)).delete(synchronize_session=False)
        db.query(CaseGenerationScreenshot).filter(CaseGenerationScreenshot.task_id.in_(cg_task_ids)).delete(synchronize_session=False)
        db.query(CaseGenerationRequirementNote).filter(CaseGenerationRequirementNote.task_id.in_(cg_task_ids)).delete(synchronize_session=False)
        db.query(CaseGenerationTask).filter(CaseGenerationTask.id.in_(cg_task_ids)).delete(synchronize_session=False)
    if ui_ids:
        db.query(UiCase).filter(UiCase.id.in_(ui_ids)).delete(synchronize_session=False)
    if api_ids:
        db.query(ApiCase).filter(ApiCase.id.in_(api_ids)).delete(synchronize_session=False)
    if profile_ids:
        db.query(TestAccountProfile).filter(TestAccountProfile.id.in_(profile_ids)).delete(synchronize_session=False)

    # 清理所有项目下的测试记录（含 case_id=0 的数据脚本记录）
    db.query(TestRecord).filter(TestRecord.project_id == project_id).delete(synchronize_session=False)

    db.query(Env).filter(Env.project_id == project_id).delete(synchronize_session=False)
    db.query(ActionTemplate).filter(ActionTemplate.project_id == project_id).delete(synchronize_session=False)
    db.delete(project)
    db.commit()
    invalidate("projects")
    return {"message": "deleted"}


# ─── 环境管理 ────────────────────────────────────────────


@app.get("/api/envs")
def list_envs(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    cache_key = f"envs:{project_id or ''}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    query = db.query(Env)
    if project_id is not None:
        query = query.filter(Env.project_id == project_id)
    result = serialize_many(query.order_by(Env.id.asc()).all())
    cache_set(cache_key, result, ttl=30)
    return result


@app.post("/api/envs")
def create_env(payload: EnvCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, Any]:
    data = normalize_env_payload(normalize_json_fields(schema_data(payload)), require_required_fields=True)
    ensure_project_exists(db, data["project_id"])
    env = Env(**data)
    db.add(env)
    db.commit()
    db.refresh(env)
    invalidate_prefix("envs:")
    return serialize(env)


@app.put("/api/envs/{env_id}")
def update_env(
    env_id: int,
    payload: EnvUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    env = get_or_404(db, Env, env_id)
    data = normalize_env_payload(normalize_json_fields(schema_data(payload, exclude_unset=True)))
    if "project_id" in data:
        if data["project_id"] != env.project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不允许修改环境所属项目，请删除后重建")
        ensure_project_exists(db, data["project_id"])
    for field, value in data.items():
        setattr(env, field, value)
    db.commit()
    db.refresh(env)
    invalidate_prefix("envs:")
    return serialize(env)


@app.delete("/api/envs/{env_id}")
def delete_env(env_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, str]:
    env = get_or_404(db, Env, env_id)
    linked_api_count = db.query(ApiCase).filter(ApiCase.env_id == env.id).count()
    if linked_api_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"环境已被 {linked_api_count} 个接口用例引用，不能删除",
        )
    db.delete(env)
    db.commit()
    invalidate_prefix("envs:")
    return {"message": "deleted"}


# ─── 接口用例 ────────────────────────────────────────────


@app.get("/api/api-cases")
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


@app.post("/api/api-cases")
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


@app.put("/api/api-cases/{case_id}")
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


@app.delete("/api/api-cases/{case_id}")
def delete_api_case(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, str]:
    case = get_or_404(db, ApiCase, case_id)
    # 清理关联记录
    db.query(TestRecord).filter(TestRecord.case_type == "api", TestRecord.case_id == case.id).delete(synchronize_session=False)
    db.query(TestAccountBinding).filter(TestAccountBinding.target_type == "api_case", TestAccountBinding.target_id == case.id).delete(synchronize_session=False)
    db.delete(case)
    db.commit()
    return {"message": "deleted"}


@app.post("/api/api-cases/{case_id}/execute")
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


@app.post("/api/api-cases/batch-execute")
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


# ─── UI 用例 ─────────────────────────────────────────────


@app.get("/api/ui-cases")
def list_ui_cases(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(UiCase)
    if project_id is not None:
        query = query.filter(UiCase.project_id == project_id)
    cases = query.order_by(UiCase.id.desc()).all()
    if not cases:
        return []

    case_ids = [c.id for c in cases]
    project_ids = list({c.project_id for c in cases})

    # 批量加载 ui_case 级别的绑定
    ui_bindings: dict[int, int | None] = {}
    for row in (
        db.query(TestAccountBinding.target_id, TestAccountBinding.account_profile_id)
        .filter(
            TestAccountBinding.target_type == "ui_case",
            TestAccountBinding.target_id.in_(case_ids),
        )
        .all()
    ):
        ui_bindings[row[0]] = row[1]

    # 批量加载 project 级别的绑定（用作兜底）
    proj_bindings: dict[int, int | None] = {}
    for row in (
        db.query(TestAccountBinding.target_id, TestAccountBinding.account_profile_id)
        .filter(
            TestAccountBinding.target_type == "project",
            TestAccountBinding.target_id.in_(project_ids),
        )
        .all()
    ):
        proj_bindings[row[0]] = row[1]

    # 收集所有 profile ID 一次加载
    all_profile_ids: set[int] = set()
    for pid in ui_bindings.values():
        if pid is not None:
            all_profile_ids.add(pid)
    for pid in proj_bindings.values():
        if pid is not None:
            all_profile_ids.add(pid)
    profiles: dict[int, TestAccountProfile] = {}
    if all_profile_ids:
        for p in db.query(TestAccountProfile).filter(TestAccountProfile.id.in_(list(all_profile_ids))).all():
            profiles[p.id] = p

    # 兜底：项目中仅有一条有效账号时自动使用
    fallback_profile: dict[int, TestAccountProfile] = {}
    for proj_id in project_ids:
        projs = (
            db.query(TestAccountProfile)
            .filter(TestAccountProfile.project_id == proj_id, TestAccountProfile.status == "active")
            .order_by(TestAccountProfile.id.asc())
            .all()
        )
        if len(projs) == 1:
            fallback_profile[proj_id] = projs[0]

    result = []
    for case in cases:
        item = serialize(case)
        profile: TestAccountProfile | None = None
        # 优先 ui_case 级别绑定
        pid = ui_bindings.get(case.id)
        if pid is not None and pid in profiles:
            profile = profiles[pid]
        # 其次 project 级别绑定
        if not profile:
            pid = proj_bindings.get(case.project_id)
            if pid is not None and pid in profiles:
                profile = profiles[pid]
        # 最后兜底
        if not profile and case.project_id in fallback_profile:
            profile = fallback_profile[case.project_id]
        item.update(account_profile_summary(profile))
        result.append(item)
    return result


@app.post("/api/ui-cases")
def create_ui_case(
    payload: UiCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = normalize_json_fields(schema_data(payload))
    ensure_project_exists(db, data["project_id"])
    case = UiCase(**data, create_time=datetime.now())
    db.add(case)
    db.commit()
    db.refresh(case)
    return serialize(case)


@app.put("/api/ui-cases/{case_id}")
def update_ui_case(
    case_id: int,
    payload: UiCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    case = get_or_404(db, UiCase, case_id)
    data = normalize_json_fields(schema_data(payload, exclude_unset=True))
    if "project_id" in data:
        ensure_project_exists(db, data["project_id"])
    for field, value in data.items():
        setattr(case, field, value)
    db.commit()
    db.refresh(case)
    return serialize(case)


@app.delete("/api/ui-cases/{case_id}")
def delete_ui_case(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, str]:
    case = get_or_404(db, UiCase, case_id)
    # 清理关联记录
    db.query(TestRecord).filter(TestRecord.case_type == "ui", TestRecord.case_id == case.id).delete(synchronize_session=False)
    db.query(LocatorHealLog).filter(LocatorHealLog.case_id == case.id).delete(synchronize_session=False)
    db.query(TestAccountBinding).filter(TestAccountBinding.target_type == "ui_case", TestAccountBinding.target_id == case.id).delete(synchronize_session=False)
    db.delete(case)
    db.commit()
    return {"message": "deleted"}


@app.post("/api/ui-cases/{case_id}/heal-steps")
def heal_ui_case_steps(
    case_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """接受执行日志中的 healing 建议，更新用例的 locator"""
    case = get_or_404(db, UiCase, case_id)
    heal_map = payload.get("heal_map")
    if not isinstance(heal_map, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="heal_map 必须是对象")
    current_steps = parse_json_value(case.steps, [])
    if not isinstance(current_steps, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用例步骤格式不正确")
    updated_count = 0
    for step in current_steps:
        if not isinstance(step, dict):
            continue
        step_locator = step.get("locator", "")
        for old_locator, new_locator in heal_map.items():
            if step_locator == old_locator:
                step["locator"] = new_locator
                step["healed_at"] = datetime.now().isoformat()
                updated_count += 1
    if updated_count:
        case.steps = to_json_text(current_steps, [])
        db.commit()
        db.refresh(case)
    return {"updated_count": updated_count, "case": serialize(case)}


@app.post("/api/ui-cases/{case_id}/execute")
def run_ui_case(
    case_id: int,
    payload: FunctionalExecuteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    case = get_or_404(db, UiCase, case_id)
    variables, execution_context = resolve_execution_account(db, payload, "ui_case", case.id, case.project_id, case.page_url)
    passed, log_text, screenshot_path, report_path = execute_ui_case(case, variables, execution_context, db_session=db)
    record = save_ui_record(db, case, passed, log_text, report_path, screenshot_path)
    return serialize(record)


# ─── 账号档案 ────────────────────────────────────────────


@app.get("/api/test-accounts")
def list_test_accounts(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(TestAccountProfile)
    if project_id is not None:
        ensure_project_exists(db, project_id)
        query = query.filter(or_(TestAccountProfile.project_id == project_id, TestAccountProfile.project_id.is_(None)))
    if current_user.role != "admin":
        query = query.filter(TestAccountProfile.status == "active")
    return [serialize_account_profile(item) for item in query.order_by(TestAccountProfile.project_id.asc(), TestAccountProfile.id.desc()).all()]


@app.post("/api/test-accounts")
def create_test_account(
    payload: TestAccountProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = normalize_account_payload(db, schema_data(payload))
    profile = TestAccountProfile(
        project_id=data.get("project_id"),
        profile_name=data["profile_name"],
        variables=data.get("variables") or "{}",
        sensitive_variables=data.get("sensitive_variables") or "",
        login_url=data.get("login_url") or "",
        username_locator=data.get("username_locator") or "",
        password_locator=data.get("password_locator") or "",
        submit_locator=data.get("submit_locator") or "",
        success_url_contains=data.get("success_url_contains") or "",
        success_selector=data.get("success_selector") or "",
        status=data.get("status") or "active",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    invalidate("projects")
    return serialize_account_profile(profile)


@app.put("/api/test-accounts/{account_id}")
def update_test_account(
    account_id: int,
    payload: TestAccountProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    profile = get_or_404(db, TestAccountProfile, account_id)
    data = normalize_account_payload(db, schema_data(payload, exclude_unset=True), profile)
    for field, value in data.items():
        setattr(profile, field, value)
    profile.update_time = datetime.now()
    db.commit()
    db.refresh(profile)
    invalidate("projects")
    return serialize_account_profile(profile)


@app.delete("/api/test-accounts/{account_id}")
def delete_test_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    profile = get_or_404(db, TestAccountProfile, account_id)
    db.query(TestAccountBinding).filter(TestAccountBinding.account_profile_id == profile.id).delete(synchronize_session=False)
    db.delete(profile)
    db.commit()
    invalidate("projects")
    return {"message": "deleted"}


@app.put("/api/test-account-bindings")
def update_test_account_binding(
    payload: TestAccountBindingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload)
    target_type = str(data["target_type"])
    target_id = int(data["target_id"])
    project_id = account_target_project_id(db, target_type, target_id)
    profile_id = data.get("account_profile_id")
    if profile_id is not None:
        account_profile_variables(db, int(profile_id), project_id)
    save_test_account_binding(db, target_type, target_id, profile_id)
    db.commit()
    invalidate("projects")
    profile = db.get(TestAccountProfile, profile_id) if profile_id else None
    return {"profile": serialize_account_profile(profile) if profile else None}


# ─── 操作模板库 ──────────────────────────────────────────


@app.get("/api/action-templates")
def list_action_templates(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(ActionTemplate)
    if project_id is not None:
        query = query.filter(ActionTemplate.project_id == project_id)
    return [_serialize_template(t) for t in query.order_by(ActionTemplate.id.desc()).all()]


@app.post("/api/action-templates")
def create_action_template(
    payload: ActionTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload)
    ensure_project_exists(db, data["project_id"])
    require_non_blank_text(data, "name", "模板名称")
    template = ActionTemplate(
        project_id=data["project_id"],
        name=data["name"],
        description=data.get("description", ""),
        trigger_keywords=to_json_text(data.get("trigger_keywords", []), []),
        steps=to_json_text(data.get("steps", []), []),
        variables=to_json_text(data.get("variables", {}), {}),
        locator_fallbacks=to_json_text(data.get("locator_fallbacks", {}), {}),
        create_time=datetime.now(),
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _serialize_template(template)


@app.put("/api/action-templates/{template_id}")
def update_action_template(
    template_id: int,
    payload: ActionTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    template = get_or_404(db, ActionTemplate, template_id)
    data = schema_data(payload, exclude_unset=True)
    if "name" in data:
        require_non_blank_text(data, "name", "模板名称")
    for field in ["name", "description"]:
        if field in data:
            setattr(template, field, data[field])
    for json_field in ["trigger_keywords", "steps", "variables", "locator_fallbacks"]:
        if json_field in data:
            setattr(template, json_field, to_json_text(data[json_field], ACTION_TEMPLATE_JSON_DEFAULTS[json_field]))
    db.commit()
    db.refresh(template)
    return _serialize_template(template)


@app.delete("/api/action-templates/{template_id}")
def delete_action_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    template = get_or_404(db, ActionTemplate, template_id)
    db.delete(template)
    db.commit()
    return {"message": "deleted"}


@app.get("/api/action-templates/{template_id}/test-run")
def test_run_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    template = get_or_404(db, ActionTemplate, template_id)
    steps = parse_json_value(template.steps, [])
    if not steps:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模板没有步骤")
    try:
        from .executors import execute_ui_case
        ui_case = UiCase(
            id=-1,  # 临时对象，不会被保存到数据库，使用 -1 避免误操作
            project_id=template.project_id,
            case_name=f"[模板测试] {template.name}",
            page_url="",
            steps=to_json_text(steps, []),
            timeout=30,
            status="active",
            create_time=datetime.now(),
        )
        passed, log_text, screenshot_path, report_path = execute_ui_case(ui_case, {})
        return {"passed": passed, "log": log_text, "screenshot": screenshot_path}
    except Exception as exc:
        return {"passed": False, "log": str(exc), "screenshot": ""}


# ─── Locator 自愈记录 ─────────────────────────────────────


@app.get("/api/locator-heal-logs")
def list_heal_logs(
    case_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    query = db.query(LocatorHealLog)
    if case_id is not None:
        query = query.filter(LocatorHealLog.case_id == case_id)
    total = query.count()
    offset = (page - 1) * page_size
    items = [
        {
            "id": log.id,
            "case_id": log.case_id,
            "old_locator": log.old_locator,
            "new_locator": log.new_locator,
            "page_url": log.page_url or "",
            "screenshot_path": log.screenshot_path or "",
            "confirmed": log.confirmed,
            "create_time": log.create_time.isoformat(),
            "step_action": log.step_action or "",
            "auto_applied": log.auto_applied or 0,
            "ai_prompt": log.ai_prompt or "",
            "ai_response": log.ai_response or "",
        }
        for log in query.order_by(LocatorHealLog.id.desc()).offset(offset).limit(page_size).all()
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.put("/api/locator-heal-logs/{log_id}")
def confirm_heal_log(
    log_id: int,
    payload: LocatorHealLogConfirm,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    log = get_or_404(db, LocatorHealLog, log_id)
    log.confirmed = payload.confirmed
    db.commit()
    return {"message": "updated"}


@app.post("/api/locator-heal-logs/{log_id}/apply")
def apply_heal_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """手动确认应用一条 heal 记录到用例。"""
    import json as _json
    log = get_or_404(db, LocatorHealLog, log_id)
    if not log.new_locator:
        return {"message": "无新 locator，无法应用"}
    case = db.get(UiCase, log.case_id)
    if not case:
        return {"message": "用例不存在"}
    try:
        steps = _json.loads(case.steps or "[]")
        if isinstance(steps, list):
            changed = False
            for s in steps:
                if isinstance(s, dict) and s.get("locator") == log.old_locator:
                    s["locator"] = log.new_locator
                    s["healed_at"] = datetime.now().isoformat()
                    changed = True
            if changed:
                case.steps = _json.dumps(steps, ensure_ascii=False)
                log.confirmed = 1
                log.auto_applied = 1
                db.commit()
                return {"message": "已应用"}
        return {"message": "未找到匹配的 locator"}
    except Exception as exc:
        return {"message": f"应用失败: {exc}"}


# ─── AI 配置 ─────────────────────────────────────────────


@app.get("/api/ai-config")
def get_ai_config(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return serialize_ai_config(latest_ai_config(db))


@app.put("/api/ai-config")
def update_ai_config(
    payload: AiConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload, exclude_unset=True)
    config = latest_ai_config(db)
    if not config:
        config = AiConfig(
            provider=data.get("provider") or "openai_compatible",
            base_url=data.get("base_url") or "",
            model=data.get("model") or "",
            api_key=data.get("api_key") or "",
            create_time=datetime.now(),
        )
        db.add(config)
    else:
        if "provider" in data:
            config.provider = data["provider"] or "openai_compatible"
        if "base_url" in data:
            config.base_url = data["base_url"] or ""
        if "model" in data:
            config.model = data["model"] or ""
        if "api_key" in data:
            config.api_key = data["api_key"] or ""
        if "heal_enabled" in data:
            config.heal_enabled = int(data["heal_enabled"] or 1)
        if "heal_confidence_threshold" in data:
            config.heal_confidence_threshold = float(data["heal_confidence_threshold"] or 0.7)
    db.commit()
    db.refresh(config)
    return serialize_ai_config(config)


# ─── 代理请求 ────────────────────────────────────────────


@app.post("/api/proxy/request")
def proxy_http_request(
    payload: QuickRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    method = payload.method.upper().strip()
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL不能为空")
    headers = dict(payload.headers or {})
    body = payload.body or ""
    client_ip = request.client.host if request.client else "unknown"
    logger.info("代理请求 [%s] %s %s (来源: %s)", method, url, current_user.username, client_ip)
    start = time.time()
    try:
        resp = guarded_proxy_request(method, url, headers, body, timeout=30)
    except HTTPException:
        raise
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="请求超时（30s）")
    except requests.exceptions.ConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"连接失败: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    elapsed = int((time.time() - start) * 1000)
    content_type = resp.headers.get("Content-Type", "")
    body_text = resp.text
    preview = body_text[:5000]
    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "body_preview": preview,
        "body_truncated": len(body_text) > 5000,
        "elapsed_ms": elapsed,
    }


# ─── 测试记录 ────────────────────────────────────────────


@app.get("/api/test-records")
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
    items = serialize_many(query.order_by(TestRecord.id.desc()).offset((page - 1) * page_size).limit(page_size).all())
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@app.get("/api/test-records/{record_id}")
def get_record(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return serialize(get_or_404(db, TestRecord, record_id))


@app.get("/api/test-records/{record_id}/report")
def get_record_report(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> FileResponse:
    record = get_or_404(db, TestRecord, record_id)
    return safe_file_response(record.report_path)


@app.get("/api/test-records/{record_id}/screenshot")
def get_record_screenshot(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> FileResponse:
    record = get_or_404(db, TestRecord, record_id)
    return safe_file_response(record.screenshot)


@app.get("/api/files/screenshot")
def get_screenshot_by_path(path: str = Query(..., description="截图文件路径"), current_user: User = Depends(get_current_user)) -> FileResponse:
    return safe_file_response(path)
