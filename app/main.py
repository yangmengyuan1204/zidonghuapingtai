import hashlib
import logging
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
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, text
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from .core.app_setup import configure_app, create_app
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
    run_balance_recharge_script,
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


# 鈹€鈹€鈹€ App 鍒濆鍖?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_app()
    yield


# SEC-03: 鐢熶骇鐜閫氳繃 DISABLE_OPENAPI=1 鍏抽棴 /docs /redoc /openapi.json锛岄粯璁や繚鎸佸紑鍚互鍏煎鐜版湁琛屼负
app = create_app(lifespan=lifespan)

# 保护「至少保留一个 admin」的序列化锁（SQLite 不支持 SELECT FOR UPDATE）
_admin_lock = threading.Lock()
configure_app(app)


# ─── 三大模块路由器 ──────────────────────────────────────


from .routers import register_routers

register_routers(app)


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# 浠ヤ笅璺敱淇濈暀鍦?main.py 涓紙鏈縼绉诲埌妯″潡锛?
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?


# 鈹€鈹€鈹€ 鍩虹 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


