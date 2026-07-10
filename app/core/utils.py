import base64
import hashlib
import ipaddress
import logging
import os
import queue
import re
import secrets
import socket
import sys
import threading
import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Type
from urllib.parse import urljoin, urlparse
from uuid import uuid4


logger = logging.getLogger(__name__)

import requests
from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, text
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from ..database import Base, engine, get_db, safe_commit
from ..data_scripts import (
    preview_order_quote_options,
    run_balance_payment_script,
    run_bank_payment_script,
    run_direct_box_to_shelf_script,
    run_full_flow_script,
    run_order_quote_script,
    run_purchase_to_shelf_script,
    run_purchase_to_shelf_chain,
    run_porder_balance_payment_script,
    run_porder_bank_payment_script,
    run_shopping_cart_script,
    run_warehouse_delivery_script,
)
from ..executors import ensure_report_dirs, execute_api_case, execute_ui_case, execute_ui_cases_batch, parse_json_value, to_json_text, _strip_leading_login_steps
from ..functional_testing import (
    FunctionalScanError,
    analyze_functional_screenshot,
    diagnose_failure,
    generate_functional_cases,
    generate_ui_steps,
    read_axure_text,
    scan_page_dom,
    store_axure_file,
    store_functional_screenshot_file,
)
from ..services.requirement_workflow import build_workflow_status
from ..models import (
    AiConfig,
    ApiCase,
    CaseGenerationCase,
    CaseGenerationRequirementNote,
    CaseGenerationScreenshot,
    CaseGenerationTask,
    ActionTemplate,
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
    UiCase,
    User,
    TestAccountBinding,
    TestAccountProfile,
)
from ..schemas import (
    ActionTemplateCreate,
    ActionTemplateUpdate,
    AiConfigUpdate,
    ApiCaseCreate,
    ApiBatchExecuteRequest,
    ApiCaseUpdate,
    ApiExecuteRequest,
    CaseGenerationCaseBatchStatusUpdate,
    CaseGenerationCaseStatusUpdate,
    CaseGenerationCaseUpdate,
    CaseGenerationRequirementNoteCreate,
    CaseGenerationRequirementNoteUpdate,
    CaseGenerationScreenshotOcrUpdate,
    CaseGenerationTaskCreate,
    CaseGenerationTaskUpdate,
    DataScriptExecuteRequest,
    EnvCreate,
    EnvUpdate,
    FunctionalCaseBatchAutomationUpdate,
    FunctionalCaseBatchIds,
    FunctionalCaseBatchStatusUpdate,
    FunctionalCaseStats,
    FunctionalCaseStatusUpdate,
    FunctionalCaseUpdate,
    FunctionalDataCheckRuleCreate,
    FunctionalDataCheckRuleUpdate,
    FunctionalExecuteRequest,
    FunctionalImpactItemCreate,
    FunctionalImpactItemUpdate,
    FunctionalRequirementNoteCreate,
    FunctionalRequirementNoteUpdate,
    FunctionalScanRequest,
    FunctionalTaskContextUpdate,
    FunctionalTaskCreate,
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
from ..security import SECRET_KEY, create_access_token, get_current_user, hash_password, is_password_hash, require_admin, verify_password
from .constants import (
    ACCOUNT_RUNTIME_VARS,
    ACTION_TEMPLATE_JSON_DEFAULTS,
    API_ALLOWED_METHODS,
    ASSERTION_ACTIONS,
    BUILTIN_RUNTIME_VARS,
    FUNCTIONAL_CASE_KIND_AUTH_NEGATIVE,
    FUNCTIONAL_CASE_KIND_BUSINESS_AUTH,
    FUNCTIONAL_CASE_KIND_MANUAL_ONLY,
    LOCATOR_REQUIRED_ACTIONS,
    PROXY_ALLOWED_METHODS,
    PROXY_ALLOW_PRIVATE_URLS,
    PROXY_MAX_REDIRECTS,
    QUALITY_AUTH_RISK,
    QUALITY_EXECUTABLE,
    QUALITY_LOCATOR_RISK,
    QUALITY_MISSING_VARIABLES,
    QUALITY_NEEDS_REVIEW,
    QUALITY_NOT_RECOMMENDED,
    QUALITY_UNCHECKED,
    SEARCH_SEED_KEYS,
    VALUE_REQUIRED_ACTIONS,
)


# __file__ is app/core/utils.py → project root is parent.parent.parent
def runtime_main_attr(name: str, fallback: Any) -> Any:
    main_module = sys.modules.get("app.main")
    return getattr(main_module, name, fallback) if main_module else fallback


BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"

TABLE_FIELDS = {
    User: ["id", "username", "password", "role", "create_time"],
    Project: ["id", "name", "desc", "create_time"],
    Env: ["id", "project_id", "env_name", "base_url", "global_headers", "global_vars", "timeout"],
    ApiCase: [
        "id",
        "project_id",
        "env_id",
        "case_name",
        "method",
        "url",
        "headers",
        "params",
        "body",
        "assert_rule",
        "status",
        "create_time",
    ],
    UiCase: ["id", "project_id", "case_name", "page_url", "steps", "timeout", "status", "create_time"],
    TestRecord: ["id", "case_type", "case_id", "project_id", "result", "log", "screenshot", "report_path", "execute_time"],
    FunctionalTask: ["id", "project_id", "iteration_name", "requirement_text", "axure_path", "target_url", "context", "status", "create_time"],
    FunctionalCase: [
        "id",
        "task_id",
        "title",
        "precondition",
        "steps",
        "expected",
        "category",
        "priority",
        "automation_status",
        "test_result",
        "ui_case_id",
        "quality_status",
        "quality_report",
        "failure_count",
        "create_time",
    ],
    PageSnapshot: ["id", "task_id", "page_url", "dom_summary", "screenshot_path", "scan_time"],
    FunctionalScreenshot: ["id", "task_id", "image_path", "analysis_result", "create_time"],
    FunctionalRequirementNote: ["id", "task_id", "note_text", "create_time", "update_time"],
    FunctionalRun: ["id", "task_id", "result", "log", "passed_count", "failed_count", "execute_time"],
    FunctionalImpactItem: ["id", "task_id", "item_type", "ref_id", "title", "target", "risk_level", "test_result", "source", "reason", "remark", "create_time", "update_time"],
    FunctionalDataCheckRule: ["id", "task_id", "rule_name", "check_type", "page_value", "api_method", "api_url", "api_headers", "api_body", "api_value_path", "compare_rule", "expected_value", "status", "create_time", "update_time"],
    FunctionalDataCheckResult: ["id", "task_id", "rule_id", "result", "page_value", "api_value", "message", "detail", "execute_time"],
    CaseGenerationTask: [
        "id",
        "project_id",
        "task_name",
        "target_name",
        "target_url",
        "requirement_text",
        "context",
        "status",
        "create_time",
        "update_time",
    ],
    CaseGenerationScreenshot: [
        "id",
        "task_id",
        "image_path",
        "analysis_result",
        "ocr_text",
        "corrected_text",
        "ocr_confidence",
        "low_confidence_items",
        "regions",
        "needs_manual_confirm",
        "ocr_error",
        "create_time",
    ],
    CaseGenerationRequirementNote: ["id", "task_id", "note_text", "create_time", "update_time"],
    CaseGenerationCase: [
        "id",
        "task_id",
        "title",
        "precondition",
        "steps",
        "expected",
        "priority",
        "source_refs",
        "generation_batch",
        "manual_edited",
        "test_result",
        "source_missing",
        "remark",
        "create_time",
        "update_time",
    ],
    AiConfig: ["id", "provider", "base_url", "model", "create_time", "heal_enabled", "heal_confidence_threshold"],  # api_key 不从此泄露
    TestAccountProfile: [
        "id", "project_id", "profile_name", "variables",
        "sensitive_variables", "login_url", "username_locator", "password_locator",
        "submit_locator", "success_url_contains", "success_selector",
        "status", "create_time", "update_time",
    ],
    TestAccountBinding: [
        "id", "target_type", "target_id", "account_profile_id",
        "create_time", "update_time",
    ],
}

JSON_FIELD_DEFAULTS = {
    "global_headers": {},
    "global_vars": {},
    "headers": {},
    "params": {},
    "assert_rule": {},
    "steps": [],
    "api_headers": {},
    "api_body": {},
    "compare_rule": {},
}

ACCOUNT_CONFIG_FIELDS = (
    "login_url",
    "username_locator",
    "password_locator",
    "submit_locator",
    "success_url_contains",
    "success_selector",
)















# 前端客户登录的通用密码，可通过环境变量 FRONTEND_ACCOUNT_PASSWORD 覆盖





# ─── OEM 独立数据脚本初始化（与日本站完全隔离，不影响日本站脚本）──────────







# OEM 接口用例库：前台/后台登录 + 创建询价单及辅助接口
# 请求体均为 JSON（与日本站 multipart form 不同）






































FUNCTIONAL_TEST_RESULTS = {"untested", "passed", "failed", "blocked", "skipped", "needs_review"}












FUNCTIONAL_TRUSTED_CATEGORIES = {"主流程", "查询筛选", "表单交互", "页面展示", "输入校验"}
SEARCH_KEYWORDS = {
    "customer_id": ["客户ID", "客户id", "客户编号", "客户号", "customer id", "customer_id"],
    "customer_name": ["客户名称", "客户名", "客户姓名", "customer name", "customer_name"],
    "orderNumber": ["订单号", "订单编号", "订单SN", "order number", "order_no", "order_sn"],
    "box_no": ["箱号", "箱子编号", "box no", "box_no", "box number"],
    "location_code": ["库位", "仓位", "location", "location_code"],
    "startDate": ["开始日期", "开始时间", "start date", "startDate"],
    "endDate": ["结束日期", "结束时间", "end date", "endDate"],
}
















GENERIC_EXPECTED_TEXTS = {"", "页面正常显示", "操作成功", "成功", "椤甸潰姝ｅ父鏄剧ず", "鎿嶄綔鎴愬姛", "鎴愬姛"}




TRUST_LEVEL_LABELS = {
    "trusted": "可信",
    "weak": "弱可信",
    "untrusted": "不建议采信",
}

RESULT_CREDIBILITY_LABELS = {
    "trusted_passed": "可信通过",
    "weak_passed": "弱通过",
    "failed_with_reason": "失败已归因",
    "failed_unclassified": "失败未归因",
    "blocked": "阻塞",
    "unknown": "未知",
}

FAILURE_CATEGORY_LABELS = {
    "product_or_assertion": "产品缺陷/断言失败",
    "script_issue": "脚本问题",
    "locator_issue": "定位器问题",
    "test_data_issue": "测试数据问题",
    "account_permission_issue": "账号/权限问题",
    "environment_issue": "环境问题",
    "requirement_unclear": "需求不明确",
    "unknown": "未知失败",
}
































































































































SENSITIVE_ACCOUNT_KEY_RE = re.compile(r"(password|passwd|pwd|captcha|token|secret|authorization|auth|密码|验证码)", re.I)
SENSITIVE_ACCOUNT_KEY_NAMES = {"code", "verify_code", "verification_code", "captcha_code"}






























def _serialize_template(template: ActionTemplate) -> Dict[str, Any]:
    return {
        "id": template.id,
        "project_id": template.project_id,
        "name": template.name,
        "description": template.description or "",
        "trigger_keywords": parse_json_value(template.trigger_keywords, []),
        "steps": parse_json_value(template.steps, []),
        "variables": parse_json_value(template.variables, {}),
        "locator_fallbacks": parse_json_value(template.locator_fallbacks, {}),
        "create_time": template.create_time.isoformat(),
    }


_LOGIN_RATE_LIMIT: dict[str, list[float]] = {}  # "ip:user" → [timestamp, ...]
_LOGIN_RATE_LOCK = threading.Lock()
_LOGIN_RATE_WINDOW = 60  # 秒
_LOGIN_RATE_MAX_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT", "200"))  # 每窗口最多尝试次数，可通过环境变量覆盖


def _check_login_rate_limit(client_ip: str, username: str = "") -> None:
    """检查登录频率，超过阈值则拒绝。key = IP:username 避免不同用户相互干扰。"""
    now = time.time()
    key = f"{client_ip}:{username}"
    with _LOGIN_RATE_LOCK:
        records = _LOGIN_RATE_LIMIT.get(key, [])
        records = [t for t in records if now - t < _LOGIN_RATE_WINDOW]
        if len(records) >= _LOGIN_RATE_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"登录尝试过于频繁，请稍后再试（{_LOGIN_RATE_WINDOW}秒内最多{_LOGIN_RATE_MAX_ATTEMPTS}次）",
            )
        _LOGIN_RATE_LIMIT[key] = records


def _record_login_attempt(client_ip: str, username: str = "") -> None:
    """记录一次登录失败（不记录成功登录）。"""
    now = time.time()
    key = f"{client_ip}:{username}"
    with _LOGIN_RATE_LOCK:
        records = _LOGIN_RATE_LIMIT.get(key, [])
        records = [t for t in records if now - t < _LOGIN_RATE_WINDOW]
        records.append(now)
        _LOGIN_RATE_LIMIT[key] = records
        # 定期清理过期 key（每 128 次写入触发一次）
        if len(_LOGIN_RATE_LIMIT) > 1000 and hash(now) % 128 == 0:
            cutoff = now - _LOGIN_RATE_WINDOW
            stale = [k for k, v in _LOGIN_RATE_LIMIT.items() if all(t < cutoff for t in v)]
            for k in stale:
                del _LOGIN_RATE_LIMIT[k]














from .data_script_context import (
    split_customer_ids,
    apply_frontend_customer_login_variables,
    resolve_data_script_context,
    data_script_variables,
)
from .account_utils import (
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
)
from .proxy_utils import (
    proxy_ip_is_blocked,
    _resolve_and_check_hostname,
    validate_proxy_target,
    _origin,
    guarded_proxy_request,
)


from .bootstrap import (
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
    strip_case_name_prefix,
    normalize_api_case_names,
    migrate_legacy_plaintext_passwords,
    find_data_script_project,
    find_data_script_api_case,
    ensure_data_script_api_cases,
    find_oem_data_script_project,
    find_oem_data_script_api_case,
    ensure_oem_data_script_api_cases,
    init_app,
)
from .serialization import (
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
)


from .functional_results import (
    normalize_functional_result,
    functional_result_counts,
    latest_data_check_results_by_rule,
    functional_task_conclusion_summary,
    functional_task_detail,
)
from .functional_quality import (
    normalize_variable_name,
    quality_report_payload,
    parse_case_steps,
    functional_case_ui_payload,
    functional_case_kind,
    functional_case_auto_trusted,
    case_has_business_assertion,
    meaningful_expected_text,
    _json_log_payload,
    _business_assertion_count_from_log,
    _api_assertion_count_from_log,
    classify_failure_category,
    test_record_credibility_payload,
    _check_item,
    functional_case_credibility_payload,
    functional_case_credibility_summary,
    ensure_weak_business_assertion,
    case_locator_issues,
    case_step_structure_issues,
)
from .functional_preflight import (
    placeholder_names,
    seed_has_key,
    case_required_seed_keys,
    first_pattern_value,
    clean_seed_value,
    build_functional_seed_text,
    seed_functional_package_data,
    functional_task_runtime_variables,
    account_preflight_status,
    guess_functional_login_url,
    evaluate_functional_case_quality,
    functional_package_preflight_summary,
    _case_group_key,
    functional_preflight_case_groups,
    functional_missing_variables_detail,
    functional_preflight_primary_action,
    preflight_functional_package,
    functional_task_keywords,
    keyword_score,
    impact_item_key,
    suggest_functional_impact_items,
)
from .functional_data_checks import (
    normalize_data_check_payload,
    full_data_check_url,
    lookup_nested_value,
    extract_response_value,
    normalize_compare_text,
    normalize_decimal_value,
    compare_data_check_values,
    execute_functional_data_check_rule,
)


from .case_generation_utils import (
    CASE_GENERATION_TEST_RESULTS,
    CASE_GENERATION_WORKSPACE_TASK_NAME,
    CASE_GENERATION_WORKSPACE_TARGET_NAME,
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
    generate_case_generation_cases_for_task,
    batch_update_case_generation_cases_for_task,
    ensure_case_generation_task,
)
from .record_utils import (
    enrich_log_with_exec_params,
    save_ui_record,
    save_record,
)
from .functional_execution_utils import (
    ui_steps_have_strong_assertion,
    save_generated_functional_ui_steps,
    can_execute_functional_case,
    execute_functional_case_for_run,
    execute_functional_case_for_run_isolated,
    save_functional_run,
)
