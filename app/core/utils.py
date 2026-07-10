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


















































































CASE_GENERATION_TEST_RESULTS = {"untested", "passed", "failed", "blocked", "skipped"}
CASE_GENERATION_WORKSPACE_TASK_NAME = "用例生成草稿"
CASE_GENERATION_WORKSPACE_TARGET_NAME = "用例生成"


def case_generation_case_is_protected(item: CaseGenerationCase) -> bool:
    return bool(item.manual_edited) or (item.test_result or "untested") != "untested"


def ensure_case_generation_workspace(db: Session, project_id: int) -> CaseGenerationTask:
    ensure_project_exists(db, project_id)
    task = (
        db.query(CaseGenerationTask)
        .filter(
            CaseGenerationTask.project_id == project_id,
            CaseGenerationTask.task_name == CASE_GENERATION_WORKSPACE_TASK_NAME,
            CaseGenerationTask.target_name == CASE_GENERATION_WORKSPACE_TARGET_NAME,
        )
        .order_by(CaseGenerationTask.id.desc())
        .first()
    )
    if task:
        return task
    task = CaseGenerationTask(
        project_id=project_id,
        task_name=CASE_GENERATION_WORKSPACE_TASK_NAME,
        target_name=CASE_GENERATION_WORKSPACE_TARGET_NAME,
        target_url="",
        requirement_text="",
        context="",
        status="draft",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def case_generation_serialize_json(value: Any) -> str:
    return json.dumps(value or [], ensure_ascii=False)


def apply_case_generation_ocr_material(screenshot: CaseGenerationScreenshot, analysis_result: str) -> None:
    payload = parse_json_value(analysis_result, {})
    material = payload.get("ocr_material") if isinstance(payload, dict) else {}
    if not isinstance(material, dict):
        material = {}
    screenshot.ocr_text = str(material.get("ocr_text") or "")
    try:
        screenshot.ocr_confidence = float(material.get("ocr_confidence") or 0)
    except (TypeError, ValueError):
        screenshot.ocr_confidence = 0
    screenshot.low_confidence_items = case_generation_serialize_json(material.get("low_confidence_items"))
    screenshot.regions = case_generation_serialize_json(material.get("regions"))
    screenshot.needs_manual_confirm = 1 if material.get("needs_manual_confirm", True) else 0
    screenshot.ocr_error = str(material.get("ocr_error") or "")


def case_generation_task_proxy(task: CaseGenerationTask) -> SimpleNamespace:
    target = task.target_url or task.target_name or ""
    return SimpleNamespace(
        id=task.id,
        project_id=task.project_id,
        iteration_name=task.task_name,
        target_url=target,
        requirement_text=task.requirement_text or "",
        context=task.context or "",
        status=task.status,
    )


def case_generation_source_refs(
    screenshots: Iterable[CaseGenerationScreenshot],
    notes: Iterable[CaseGenerationRequirementNote],
) -> str:
    payload = {
        "screenshots": [item.id for item in screenshots],
        "notes": [item.id for item in notes],
        "initial_requirement": True,
    }
    return json.dumps(payload, ensure_ascii=False)


def case_generation_refs_include_screenshot(item: CaseGenerationCase, screenshot_id: int) -> bool:
    refs = parse_json_value(item.source_refs, {})
    values = refs.get("screenshots") if isinstance(refs, dict) else []
    return str(screenshot_id) in {str(value) for value in (values or [])}


def case_generation_refs_include_note(item: CaseGenerationCase, note_id: int) -> bool:
    refs = parse_json_value(item.source_refs, {})
    values = refs.get("notes") if isinstance(refs, dict) else []
    return str(note_id) in {str(value) for value in (values or [])}


def case_generation_stats(cases: Iterable[CaseGenerationCase]) -> Dict[str, int]:
    stats = {key: 0 for key in ["total", "untested", "passed", "failed", "blocked", "skipped"]}
    for item in cases:
        stats["total"] += 1
        result = item.test_result or "untested"
        if result not in CASE_GENERATION_TEST_RESULTS:
            result = "untested"
        stats[result] += 1
    return stats


def case_generation_detail(db: Session, task: CaseGenerationTask) -> Dict[str, Any]:
    data = serialize(task)
    project = db.get(Project, task.project_id)
    data["project_name"] = project.name if project else task.project_id
    screenshots = (
        db.query(CaseGenerationScreenshot)
        .filter(CaseGenerationScreenshot.task_id == task.id)
        .order_by(CaseGenerationScreenshot.id.desc())
        .all()
    )
    notes = (
        db.query(CaseGenerationRequirementNote)
        .filter(CaseGenerationRequirementNote.task_id == task.id)
        .order_by(CaseGenerationRequirementNote.id.desc())
        .all()
    )
    cases = (
        db.query(CaseGenerationCase)
        .filter(CaseGenerationCase.task_id == task.id)
        .order_by(CaseGenerationCase.id.asc())
        .all()
    )
    data["screenshots"] = serialize_many(screenshots)
    data["requirement_notes"] = serialize_many(notes)
    data["cases"] = serialize_many(cases)
    data["stats"] = case_generation_stats(cases)
    return data


def remove_uploaded_case_generation_file(raw_path: str | None) -> None:
    if not raw_path:
        return
    try:
        path = Path(raw_path)
        if not path.is_absolute():
            path = BASE_DIR / path
        resolved = path.resolve()
        reports_dir = (BASE_DIR / "reports").resolve()
        if resolved.exists() and resolved.is_file() and (resolved == reports_dir or reports_dir in resolved.parents):
            resolved.unlink()
    except Exception:
        pass


def case_generation_screenshot_impact(db: Session, screenshot: CaseGenerationScreenshot) -> Dict[str, int]:
    impacted = [
        item
        for item in db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == screenshot.task_id).all()
        if case_generation_refs_include_screenshot(item, screenshot.id)
    ]
    deletable = [item for item in impacted if not case_generation_case_is_protected(item)]
    protected = [item for item in impacted if case_generation_case_is_protected(item)]
    return {
        "total": len(impacted),
        "deletable": len(deletable),
        "protected": len(protected),
    }


def generate_case_generation_cases_for_task(db: Session, task: CaseGenerationTask) -> Dict[str, Any]:
    screenshots = (
        db.query(CaseGenerationScreenshot)
        .filter(CaseGenerationScreenshot.task_id == task.id)
        .order_by(CaseGenerationScreenshot.id.asc())
        .all()
    )
    notes = (
        db.query(CaseGenerationRequirementNote)
        .filter(CaseGenerationRequirementNote.task_id == task.id)
        .order_by(CaseGenerationRequirementNote.id.asc())
        .all()
    )
    generated = generate_functional_cases(
        case_generation_task_proxy(task),
        "",
        None,
        latest_ai_config(db),
        screenshots,
        notes,
    )
    for old_case in db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == task.id).all():
        if not case_generation_case_is_protected(old_case):
            db.delete(old_case)
    db.flush()

    batch = uuid4().hex[:12]
    source_refs = case_generation_source_refs(screenshots, notes)
    created = 0
    for item in generated.items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        db.add(
            CaseGenerationCase(
                task_id=task.id,
                title=title[:200],
                precondition=item.get("precondition", ""),
                steps=item.get("steps", ""),
                expected=item.get("expected", ""),
                priority=item.get("priority", "P1"),
                source_refs=source_refs,
                generation_batch=batch,
                manual_edited=0,
                test_result="untested",
                source_missing=0,
                remark="",
                create_time=datetime.now(),
                update_time=None,
            )
        )
        created += 1
    task.status = "cases_generated"
    task.update_time = datetime.now()
    db.commit()
    db.refresh(task)
    return {"created": created, "workspace": case_generation_detail(db, task)}


def batch_update_case_generation_cases_for_task(
    db: Session,
    task_id: int,
    payload: CaseGenerationCaseBatchStatusUpdate,
) -> Dict[str, Any]:
    if payload.test_result not in CASE_GENERATION_TEST_RESULTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的测试状态")
    updated = (
        db.query(CaseGenerationCase)
        .filter(CaseGenerationCase.task_id == task_id, CaseGenerationCase.id.in_(payload.case_ids or [-1]))
        .update({"test_result": payload.test_result, "update_time": datetime.now()}, synchronize_session="fetch")
    )
    db.commit()
    return {"updated": updated, "test_result": payload.test_result}


def ensure_case_generation_task(db: Session, task_id: int) -> CaseGenerationTask:
    return get_or_404(db, CaseGenerationTask, task_id)


def enrich_log_with_exec_params(log_text: str, **exec_params: Any) -> str:
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


def save_ui_record(db: Session, case: UiCase, passed: bool, log_text: str, report_path: str, screenshot_path: str = "", **exec_params: Any) -> TestRecord:
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


def save_record(
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


def ui_steps_have_strong_assertion(steps: Any) -> bool:
    parsed = parse_json_value(steps, steps)
    if isinstance(parsed, str):
        parsed = parse_json_value(parsed, [])
    if not isinstance(parsed, list):
        return False
    strong_actions = {"assert_url", "assert_visible", "assert_value", "text_assert"}
    for step in parsed:
        if not isinstance(step, dict):
            continue
        if step.get("action") in strong_actions:
            return True
        if step.get("success_condition") or step.get("assertions"):
            return True
    return False


def save_generated_functional_ui_steps(
    db: Session,
    task: FunctionalTask,
    case: FunctionalCase,
    snapshot: PageSnapshot | None = None,
) -> Dict[str, Any]:
    generated = generate_ui_steps(case, task, snapshot, latest_ai_config(db))
    generated_steps = generated.items
    if functional_case_kind(case) == FUNCTIONAL_CASE_KIND_BUSINESS_AUTH:
        generated_steps, _removed_login_steps = _strip_leading_login_steps(generated_steps)
    steps_text = to_json_text(generated_steps, [])
    if case.ui_case_id:
        ui_case = db.get(UiCase, case.ui_case_id)
        if ui_case:
            ui_case.case_name = case.title
            ui_case.page_url = task.target_url
            ui_case.steps = steps_text
            ui_case.status = "draft"
        else:
            case.ui_case_id = None
    if not case.ui_case_id:
        ui_case = UiCase(
            project_id=task.project_id,
            case_name=case.title,
            page_url=task.target_url,
            steps=steps_text,
            timeout=30,
            status="draft",
            create_time=datetime.now(),
        )
        db.add(ui_case)
        db.flush()
        case.ui_case_id = ui_case.id
    case.automation_status = "draft"
    task.status = "ui_steps_generated"
    return {"source": generated.source, "warning": generated.warning, "case": serialize(case), "steps": generated_steps}


def can_execute_functional_case(
    functional_case: FunctionalCase,
    payload: FunctionalExecuteRequest | None = None,
) -> tuple[bool, str]:
    """
    执行前门禁检查。
    Returns (allowed, reason) — allowed=False 则拒绝执行。
    """
    if functional_case.automation_status != "approved":
        return False, f"用例状态为 {functional_case.automation_status}，仅 approved 可自动执行"
    if not functional_case.ui_case_id:
        return False, "尚未关联 UI 步骤，无法执行"
    quality = functional_case.quality_status or QUALITY_UNCHECKED
    trial_mode = bool(payload and (payload.force or payload.execution_mode == "trial"))
    if quality in (QUALITY_AUTH_RISK, QUALITY_MISSING_VARIABLES, QUALITY_NOT_RECOMMENDED):
        return False, f"预检未通过（{quality}），不允许自动执行"
    if quality in (QUALITY_LOCATOR_RISK, QUALITY_NEEDS_REVIEW) and not trial_mode:
        return False, f"预检未通过（{quality}），不允许自动执行"
    return True, ""


def execute_functional_case_for_run(
    db: Session,
    functional_case: FunctionalCase,
    variables: Dict[str, Any],
    payload: FunctionalExecuteRequest | None = None,
) -> tuple[Dict[str, Any], int, int]:
    # ── 执行门禁 ──────────────────────────────────────
    allowed, reason = can_execute_functional_case(functional_case, payload)
    if not allowed:
        return (
            {
                "functional_case_id": functional_case.id,
                "title": functional_case.title,
                "result": "failed",
                "error": reason,
                "gate_blocked": True,
            },
            0,
            1,
        )
    # ──────────────────────────────────────────────────
    ui_case = db.get(UiCase, functional_case.ui_case_id) if functional_case.ui_case_id else None
    if not ui_case:
        return (
            {
                "functional_case_id": functional_case.id,
                "title": functional_case.title,
                "result": "failed",
                "error": "关联UI用例不存在",
            },
            0,
            1,
        )
    case_variables, execution_context = resolve_execution_account(
        db,
        payload,
        "functional_case",
        functional_case.id,
        ui_case.project_id,
        ui_case.page_url,
    )
    case_variables = {**variables, **case_variables}
    execution_context = dict(execution_context or {})
    execution_context["strip_login_steps"] = True
    try:
        passed, log_text, screenshot_path, report_path = execute_ui_case(ui_case, case_variables, execution_context, None, db)
    except Exception as exc:
        passed = False
        screenshot_path = ""
        report_path = ""
        log_text = json.dumps(
            {
                "case_name": ui_case.case_name,
                "page_url": ui_case.page_url,
                "error": str(exc),
                "finished_at": datetime.now(),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    record = save_ui_record(db, ui_case, passed, log_text, report_path, screenshot_path)
    return (
        {
            "functional_case_id": functional_case.id,
            "ui_case_id": ui_case.id,
            "record_id": record.id,
            "title": functional_case.title,
            "result": record.result,
            "screenshot": screenshot_path,
            "log": log_text,
        },
        1 if passed else 0,
        0 if passed else 1,
    )


def execute_functional_case_for_run_isolated(
    functional_case_id: int,
    variables: Dict[str, Any],
    payload_data: Dict[str, Any] | None = None,
) -> tuple[Dict[str, Any], int, int]:
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        functional_case = db.get(FunctionalCase, functional_case_id)
        if not functional_case:
            return (
                {
                    "functional_case_id": functional_case_id,
                    "title": f"#{functional_case_id}",
                    "result": "failed",
                    "error": "功能用例不存在",
                },
                0,
                1,
            )
        payload = FunctionalExecuteRequest(**payload_data) if payload_data else None
        return execute_functional_case_for_run(db, functional_case, variables, payload)
    finally:
        db.close()


def save_functional_run(
    db: Session,
    task: FunctionalTask,
    variables: Dict[str, Any],
    records: list[Dict[str, Any]],
    passed_count: int,
    failed_count: int,
) -> FunctionalRun:
    result = "passed" if failed_count == 0 else "failed"
    log_payload = {
        "task_id": task.id,
        "task": task.iteration_name,
        "variables": {key: ("***" if "password" in str(key).lower() else value) for key, value in variables.items()},
        "records": records,
        "passed_count": passed_count,
        "failed_count": failed_count,
    }
    run = FunctionalRun(
        task_id=task.id,
        result=result,
        log=json.dumps(log_payload, ensure_ascii=False, indent=2, default=str),
        passed_count=passed_count,
        failed_count=failed_count,
        execute_time=datetime.now(),
    )
    task.status = result
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


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
