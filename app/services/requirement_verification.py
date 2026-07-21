from __future__ import annotations

import ast
import hashlib
import json
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    ROUND_HALF_UP,
    ROUND_UP,
    Decimal,
    InvalidOperation,
)
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.utils import (
    account_profile_variables,
    data_script_variables,
    decrypt_account_payload,
    default_account_profile_for_target,
    encrypt_account_payload,
    guarded_proxy_request,
    parse_json_value,
)
from ..data_scripts.registry import SCRIPT_REGISTRY
from ..database import SessionLocal
from ..executors import _prepare_authenticated_page, launch_chromium_browser
from ..functional_testing import extract_screenshot_material
from ..functional_testing.model_client import call_local_model_json
from ..models import (
    AiConfig,
    Env,
    Project,
    RequirementVerification,
    TestAccountProfile,
    VerificationClarification,
    VerificationDataSource,
    VerificationFormula,
    VerificationItem,
    VerificationMaterial,
    VerificationMemory,
    VerificationRun,
    VerificationRunDataset,
    VerificationRunItem,
)
from .verification_runtime_v2 import (
    VerificationAwaitingUser,
    VerificationCancelled,
    active_run_for_other_task,
    check_run_control,
    classify_failure,
    conditions_to_variables,
    consume_manual_decision,
    create_run_datasets,
    evaluate_conditions,
    group_items_by_conditions,
    item_conditions,
    normalize_business_facts,
    recompute_run_summary,
    request_manual_action,
    resolve_manual_action,
    serialize_dataset,
    should_reuse_data,
    update_run_phase,
)


ITEM_TYPES = {"page", "data", "state", "amount", "permission", "exception", "manual"}
AUTOMATION_LEVELS = {"auto", "supervised", "manual"}
RESULTS = {"pending", "running", "waiting_confirmation", "passed", "failed", "blocked", "needs_review", "skipped"}
RISK_WORDS = ("支付", "付款", "删除", "退款", "批量", "取消订单", "确认收货", "提交审核", "打款")
MAX_DATA_SETUP_STEPS = 10
MAX_ACTIVE_CLARIFICATIONS = 3
CLARIFICATION_CONFIRM_CONFIDENCE = 0.7
HIGH_RISK_DATA_SCRIPT_KEYS = {
    "balance_payment",
    "bank_payment",
    "porder_balance_payment",
    "porder_bank_payment",
    "balance_recharge",
    "balance_adjustment",
    "oem_balance_pay",
    "full_flow",
    "purchase_to_shelf",
    "purchase_to_shelf_chain",
    "resume_order_flow",
    "resume_porder_flow",
}
SENSITIVE_KEY_PARTS = ("password", "passwd", "pwd", "token", "secret", "authorization", "cookie")
SENSITIVE_REPLACEMENTS = (
    (re.compile(r"(?i)(authorization|token|secret|password|passwd|pwd)\s*[:=]\s*[^\s,;]+"), r"\1=***"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "***手机号***"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "***邮箱***"),
)
ROUNDING_MODES = {
    "HALF_UP": ROUND_HALF_UP,
    "HALF_EVEN": ROUND_HALF_EVEN,
    "DOWN": ROUND_DOWN,
    "UP": ROUND_UP,
    "FLOOR": ROUND_FLOOR,
    "CEILING": ROUND_CEILING,
}
EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "reports" / "verification-evidence"
UNRESOLVED_MARKERS = ("{需澄清}", "[object Object]", "待补充", "待确认", "TBD", "TODO")
BUSINESS_URL_VARIABLES = {"order_sn", "porder_sn", "purchase_no", "goods_id", "goods_sn", "customer_id"}
DATA_SCRIPT_OUTPUT_KEYS: Dict[str, list[str]] = {
    "shopping_cart": ["cart_ids", "goods_ids"],
    "order_quote": ["order_sn", "goods_ids", "cart_ids", "item_quantity", "quantity", "selected_count", "item_count"],
    "balance_payment": ["order_sn", "serial_number", "pay_amount"],
    "bank_payment": ["order_sn", "serial_number", "pay_amount"],
    "purchase_to_shelf": ["order_sn", "purchase_no"],
    "purchase_to_shelf_chain": ["order_sn", "purchase_no"],
    "warehouse_delivery": ["order_sn", "porder_sn", "porder_detail_ids"],
    "porder_balance_payment": ["porder_sn", "serial_number"],
    "porder_bank_payment": ["porder_sn", "serial_number"],
    "full_flow": ["order_sn", "porder_sn", "purchase_no", "current_node", "goods_ids", "cart_ids"],
    "direct_box_to_shelf": ["order_sn", "purchase_no", "box_ids"],
    "resume_order_flow": ["order_sn", "porder_sn", "purchase_no", "current_node"],
    "resume_porder_flow": ["porder_sn", "current_node"],
    "problem_goods": ["order_sn", "problem_goods_id", "status"],
    "balance_adjustment": ["order_sn", "serial_number", "balance", "amount"],
}
DATA_SCRIPT_ACCEPTED_CONDITIONS: Dict[str, list[str]] = {
    "shopping_cart": ["goods_keyword", "shop_type", "quantity", "item_count"],
    "order_quote": ["quantity", "item_count", "order_status"],
    "purchase_to_shelf_chain": ["quantity", "item_count", "order_status"],
    "full_flow": ["quantity", "item_count", "order_status", "stop_after_node"],
    "resume_order_flow": ["order_sn", "order_status", "stop_after_node"],
    "resume_porder_flow": ["porder_sn", "order_status", "stop_after_node"],
    "problem_goods": ["order_sn", "quantity", "is_fee", "status"],
    "balance_adjustment": ["customer_id", "amount", "adjustment_type", "status"],
}


class VerificationBlocked(RuntimeError):
    pass


class VerificationNeedsReview(RuntimeError):
    pass


def json_load(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _string_list(value: Any, limit: int = 20) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


def _normalized_question_text(value: Any) -> str:
    text = re.sub(r"[\s\W_]+", "", str(value or "").lower())
    for prefix in ("请确认", "请问", "需要确认", "是否", "具体"):
        text = text.replace(prefix, "")
    return text


def clarification_topic_key(value: Any, question: str, source_ref: str = "") -> str:
    normalized = re.sub(r"[^0-9a-zA-Z_.\-\u4e00-\u9fff]+", "_", str(value or "").strip().lower()).strip("_")
    if normalized:
        return normalized[:200]
    basis = f"{source_ref}|{_normalized_question_text(question)}"
    return f"clarification.{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:16]}"


def clarification_questions_similar(left: str, right: str) -> bool:
    normalized_left = _normalized_question_text(left)
    normalized_right = _normalized_question_text(right)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left in normalized_right or normalized_right in normalized_left:
        return min(len(normalized_left), len(normalized_right)) >= 8
    return SequenceMatcher(None, normalized_left, normalized_right).ratio() >= 0.78


def clarification_review(row: VerificationClarification) -> Dict[str, Any]:
    value = json_load(row.review_json, {})
    return value if isinstance(value, dict) else {}


def serialize_clarification(row: VerificationClarification) -> Dict[str, Any]:
    return {
        "id": row.id,
        "analysis_version": row.analysis_version,
        "question": row.question,
        "answer": row.answer or "",
        "source_ref": row.source_ref or "",
        "topic_key": row.topic_key or "",
        "review": clarification_review(row),
        "status": row.status,
        "create_time": _time_text(row.create_time),
        "update_time": _time_text(row.update_time),
    }


def normalize_target_pages(value: Any, fallback_url: str = "") -> list[Dict[str, str]]:
    if value is None:
        value = []
    if not isinstance(value, list):
        raise ValueError("目标页面必须是页面清单")
    if len(value) > 30:
        raise ValueError("一个功能分类最多配置30个目标页面")
    pages: list[Dict[str, str]] = []
    for index, raw in enumerate(value, start=1):
        if isinstance(raw, str):
            raw = {"name": raw}
        if not isinstance(raw, dict):
            raise ValueError(f"第{index}个目标页面格式错误")
        name = str(raw.get("name") or "").strip()[:160]
        url = str(raw.get("url") or "").strip()[:1000]
        role = str(raw.get("role") or "").strip()[:120]
        if not name and not url:
            continue
        pages.append({"name": name or f"页面{index}", "url": url, "role": role})
    fallback = str(fallback_url or "").strip()
    if not pages and fallback:
        pages.append({"name": "主要页面", "url": fallback[:1000], "role": ""})
    return pages


def target_pages_for(task: RequirementVerification) -> list[Dict[str, str]]:
    return normalize_target_pages(json_load(task.target_pages_json, []), task.target_url or "")


def target_page_url(task: RequirementVerification, page_name: str = "") -> str:
    pages = target_pages_for(task)
    normalized_name = str(page_name or "").strip()
    if normalized_name:
        for page in pages:
            if page["name"] == normalized_name:
                return page["url"]
    return next((page["url"] for page in pages if page["url"]), task.target_url or "")


def data_script_risk_level(script_type: str, definition: Dict[str, Any] | None = None) -> str:
    name = str((definition or {}).get("name") or "")
    if script_type in HIGH_RISK_DATA_SCRIPT_KEYS:
        return "high"
    if any(word in name for word in ("支付", "付款", "充值", "退款", "出入金")):
        return "high"
    return "normal"


def data_script_allowed_for_project(db: Session, project_id: int, script_type: str) -> bool:
    project = db.get(Project, project_id)
    if not project:
        return False
    project_is_oem = "oem" in str(project.name or "").strip().lower()
    script_is_oem = str(script_type or "").strip().lower().startswith("oem_")
    return project_is_oem == script_is_oem


def data_script_catalog(db: Session | None = None, project_id: int | None = None) -> list[Dict[str, Any]]:
    return [
        {
            "script_type": script_type,
            "name": str(definition.get("name") or script_type),
            "chain": bool(definition.get("chain")),
            "risk_level": data_script_risk_level(script_type, definition),
            "output_keys": DATA_SCRIPT_OUTPUT_KEYS.get(script_type, []),
            "accepted_business_conditions": DATA_SCRIPT_ACCEPTED_CONDITIONS.get(script_type, []),
            "changes_business_state": data_script_risk_level(script_type, definition) == "high" or bool(definition.get("chain")),
        }
        for script_type, definition in SCRIPT_REGISTRY.items()
        if isinstance(definition, dict)
        and callable(definition.get("func"))
        and (db is None or project_id is None or data_script_allowed_for_project(db, project_id, script_type))
    ]


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized_key = str(key).strip().lower()
            if any(part in normalized_key for part in SENSITIVE_KEY_PARTS):
                return True
            if _contains_sensitive_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def mask_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        masked: Dict[str, Any] = {}
        for key, nested in value.items():
            normalized_key = str(key).strip().lower()
            masked[str(key)] = "***" if any(part in normalized_key for part in SENSITIVE_KEY_PARTS) else mask_sensitive_data(nested)
        return masked
    if isinstance(value, list):
        return [mask_sensitive_data(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def normalize_data_setup(value: Any) -> Dict[str, Any]:
    if value in (None, ""):
        value = {}
    if isinstance(value, list):
        value = {"steps": value}
    if not isinstance(value, dict):
        raise ValueError("数据准备配置必须是对象")
    raw_steps = value.get("steps") or []
    if not isinstance(raw_steps, list):
        raise ValueError("数据准备步骤必须是数组")
    if len(raw_steps) > MAX_DATA_SETUP_STEPS:
        raise ValueError(f"数据准备最多配置{MAX_DATA_SETUP_STEPS}个步骤")
    steps: list[Dict[str, Any]] = []
    for index, raw in enumerate(raw_steps, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"第{index}个数据准备步骤格式错误")
        script_type = str(raw.get("script_type") or "").strip()
        if not script_type:
            raise ValueError(f"第{index}个数据准备步骤未选择脚本")
        try:
            env_id = int(raw.get("env_id") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第{index}个数据准备步骤环境格式错误") from exc
        variables = raw.get("variables") or {}
        if not isinstance(variables, dict):
            raise ValueError(f"第{index}个数据准备步骤参数必须是对象")
        if _contains_sensitive_key(variables):
            raise ValueError(f"第{index}个数据准备步骤不能保存密码、令牌或Cookie，请使用项目账号配置")
        enabled_value = raw.get("enabled", True)
        enabled = enabled_value if isinstance(enabled_value, bool) else str(enabled_value).strip().lower() not in {"0", "false", "no", "off", "否"}
        steps.append({"script_type": script_type, "env_id": env_id, "variables": variables, "enabled": enabled})
    return {"steps": steps}


def validate_data_setup_for_project(db: Session, project_id: int, value: Any) -> Dict[str, Any]:
    setup = normalize_data_setup(value)
    for index, step in enumerate(setup["steps"], start=1):
        definition = SCRIPT_REGISTRY.get(step["script_type"])
        if not isinstance(definition, dict) or not callable(definition.get("func")):
            raise ValueError(f"第{index}个数据准备脚本不存在或未注册：{step['script_type']}")
        if not data_script_allowed_for_project(db, project_id, step["script_type"]):
            raise ValueError(f"第{index}个数据准备脚本不属于当前项目：{definition.get('name') or step['script_type']}")
        if not step["enabled"]:
            continue
        env = db.get(Env, step["env_id"]) if step["env_id"] else None
        if not env or env.project_id != project_id:
            raise ValueError(f"第{index}个数据准备环境不存在或不属于当前项目")
    return setup


def data_setup_has_high_risk(value: Any) -> bool:
    setup = normalize_data_setup(value)
    return any(
        step["enabled"] and data_script_risk_level(step["script_type"], SCRIPT_REGISTRY.get(step["script_type"])) == "high"
        for step in setup["steps"]
    )


def redact_sensitive_text(value: Any, limit: int = 50000) -> str:
    text = str(value or "")[:limit]
    for pattern, replacement in SENSITIVE_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def _time_text(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def serialize_formula(row: VerificationFormula) -> Dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "task_id": row.task_id,
        "analysis_version": row.analysis_version,
        "name": row.name,
        "version": row.version,
        "expression": row.expression,
        "variables": json_load(row.variables_json, {}),
        "conditions": json_load(row.conditions_json, {}),
        "currency": row.currency or "",
        "scale": row.scale,
        "rounding_mode": row.rounding_mode,
        "rounding_stage": row.rounding_stage,
        "source_refs": json_load(row.source_refs, []),
        "status": row.status,
        "create_time": _time_text(row.create_time),
        "update_time": _time_text(row.update_time),
    }


def serialize_item(row: VerificationItem) -> Dict[str, Any]:
    return {
        "id": row.id,
        "task_id": row.task_id,
        "analysis_version": row.analysis_version,
        "item_type": row.item_type,
        "title": row.title,
        "priority": row.priority,
        "role_name": row.role_name or "",
        "precondition": row.precondition or "",
        "action_goal": row.action_goal or "",
        "expected": row.expected or "",
        "source_refs": json_load(row.source_refs, []),
        "automation_level": row.automation_level,
        "risk_level": row.risk_level,
        "config": json_load(row.config_json, {}),
        "status": row.status,
        "confirmed": bool(row.confirmed),
        "result_message": row.result_message or "",
        "actual": json_load(row.actual_json, {}),
        "create_time": _time_text(row.create_time),
        "update_time": _time_text(row.update_time),
    }


def serialize_run_item(row: VerificationRunItem) -> Dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "item_id": row.item_id,
        "dataset_id": row.dataset_id,
        "flow_group": row.flow_group or "",
        "dependencies": json_load(row.dependency_json, []),
        "attempt": row.attempt or 0,
        "failure_kind": row.failure_kind or "",
        "resume": json_load(row.resume_json, {}),
        "result": row.result,
        "message": row.message or "",
        "actual": json_load(row.actual_json, {}),
        "evidence": json_load(row.evidence_json, {}),
        "start_time": _time_text(row.start_time),
        "finish_time": _time_text(row.finish_time),
    }


def serialize_run(db: Session, row: VerificationRun) -> Dict[str, Any]:
    items = (
        db.query(VerificationRunItem)
        .filter(VerificationRunItem.run_id == row.id)
        .order_by(VerificationRunItem.id.asc())
        .all()
    )
    datasets = (
        db.query(VerificationRunDataset)
        .filter(VerificationRunDataset.run_id == row.id)
        .order_by(VerificationRunDataset.id.asc())
        .all()
    )
    return {
        "id": row.id,
        "task_id": row.task_id,
        "status": row.status,
        "phase": row.phase or row.status,
        "progress": json_load(row.progress_json, {}),
        "heartbeat_time": _time_text(row.heartbeat_time),
        "pause_reason": row.pause_reason or "",
        "cancel_requested": bool(row.cancel_requested),
        "parent_run_id": row.parent_run_id,
        "execution_version": row.execution_version or "v2",
        "variables": json_load(row.variables_json, {}),
        "data_setup": json_load(row.data_setup_json, {"steps": []}),
        "setup_result": json_load(row.setup_result_json, {}),
        "summary": json_load(row.summary_json, {}),
        "visible_browser": bool(row.visible_browser),
        "create_time": _time_text(row.create_time),
        "start_time": _time_text(row.start_time),
        "finish_time": _time_text(row.finish_time),
        "datasets": [serialize_dataset(dataset) for dataset in datasets],
        "waiting_user_items": [serialize_run_item(item) for item in items if item.result in {"waiting_user", "waiting_confirmation"}],
        "available_actions": {
            "pause": row.status not in {"passed", "failed", "blocked", "needs_review", "cancelled", "paused", "waiting_user"},
            "resume": row.phase == "paused",
            "cancel": row.status not in {"passed", "failed", "blocked", "needs_review", "cancelled"},
            "retry": row.status in {"failed", "blocked", "needs_review", "cancelled"},
        },
        "items": [serialize_run_item(item) for item in items],
    }


def verification_detail(db: Session, task: RequirementVerification) -> Dict[str, Any]:
    version = task.analysis_version or 0
    materials = (
        db.query(VerificationMaterial)
        .filter(VerificationMaterial.task_id == task.id, VerificationMaterial.status == "active")
        .order_by(VerificationMaterial.id.asc())
        .all()
    )
    questions = (
        db.query(VerificationClarification)
        .filter(VerificationClarification.task_id == task.id, VerificationClarification.analysis_version == version)
        .order_by(VerificationClarification.id.asc())
        .all()
    )
    confirmed_questions = (
        db.query(VerificationClarification)
        .filter(VerificationClarification.task_id == task.id, VerificationClarification.status == "answered")
        .order_by(VerificationClarification.id.asc())
        .all()
    )
    items = (
        db.query(VerificationItem)
        .filter(VerificationItem.task_id == task.id, VerificationItem.analysis_version == version)
        .order_by(VerificationItem.id.asc())
        .all()
    )
    formulas = (
        db.query(VerificationFormula)
        .filter(
            VerificationFormula.task_id == task.id,
            or_(VerificationFormula.analysis_version == version, VerificationFormula.analysis_version.is_(None)),
        )
        .order_by(VerificationFormula.id.asc())
        .all()
    )
    runs = (
        db.query(VerificationRun)
        .filter(VerificationRun.task_id == task.id)
        .order_by(VerificationRun.id.desc())
        .limit(10)
        .all()
    )
    memories = (
        db.query(VerificationMemory)
        .filter(
            VerificationMemory.project_id == task.project_id,
            or_(VerificationMemory.source_task_id == task.id, VerificationMemory.status == "confirmed"),
        )
        .order_by(VerificationMemory.id.desc())
        .all()
    )
    counts = Counter(item.status for item in items)
    type_counts = Counter(item.item_type for item in items)
    return {
        "id": task.id,
        "project_id": task.project_id,
        "name": task.name,
        "target_url": task.target_url or "",
        "target_pages": target_pages_for(task),
        "data_setup": json_load(task.data_setup_json, {"steps": []}),
        "requirement_text": task.requirement_text or "",
        "context": task.context or "",
        "status": task.status,
        "is_archived": bool(task.is_archived),
        "analysis_version": version,
        "analysis": json_load(task.analysis_json, {}),
        "create_time": _time_text(task.create_time),
        "update_time": _time_text(task.update_time),
        "materials": [
            {
                "id": row.id,
                "material_type": row.material_type,
                "name": row.name or "",
                "content_text": row.content_text or "",
                "has_image": bool(row.image_path),
                "ocr_text": row.ocr_text or "",
                "analysis": json_load(row.analysis_json, {}),
                "create_time": _time_text(row.create_time),
            }
            for row in materials
        ],
        "clarifications": [serialize_clarification(row) for row in questions],
        "confirmed_clarifications": [serialize_clarification(row) for row in confirmed_questions],
        "has_unapplied_confirmed_answers": any(row.analysis_version >= version for row in confirmed_questions),
        "items": [serialize_item(row) for row in items],
        "formulas": [serialize_formula(row) for row in formulas],
        "runs": [serialize_run(db, row) for row in runs],
        "memories": [
            {
                "id": row.id,
                "project_id": row.project_id,
                "memory_type": row.memory_type,
                "name": row.name,
                "content": json_load(row.content_json, {}),
                "source_task_id": row.source_task_id,
                "version": row.version,
                "status": row.status,
                "create_time": _time_text(row.create_time),
                "update_time": _time_text(row.update_time),
            }
            for row in memories
        ],
        "stats": {"total": len(items), "by_status": dict(counts), "by_type": dict(type_counts)},
    }


def _analysis_material_text(db: Session, task: RequirementVerification) -> str:
    target_pages = target_pages_for(task)
    target_page_text = "\n".join(
        f"目标页面项：{page['name']} | 角色：{page['role'] or '未指定'} | URL：{page['url'] or '未提供'}"
        for page in target_pages
    )
    parts = [
        f"需求名称：{task.name}",
        f"目标页面清单：\n{target_page_text or '未提供'}",
        f"需求正文：\n{task.requirement_text or ''}",
        f"业务上下文：\n{task.context or ''}",
    ]
    rows = (
        db.query(VerificationMaterial)
        .filter(VerificationMaterial.task_id == task.id, VerificationMaterial.status == "active")
        .order_by(VerificationMaterial.id.asc())
        .all()
    )
    for row in rows:
        text = row.content_text or row.ocr_text or ""
        if text.strip():
            parts.append(f"材料#{row.id} {row.name or row.material_type}：\n{text}")
    answers = (
        db.query(VerificationClarification)
        .filter(VerificationClarification.task_id == task.id, VerificationClarification.status == "answered")
        .order_by(VerificationClarification.id.asc())
        .all()
    )
    for row in answers:
        review = clarification_review(row)
        interpretation = review.get("interpretation") if isinstance(review.get("interpretation"), dict) else {}
        rules = _string_list(interpretation.get("understood_rules"))
        summary = str(interpretation.get("summary") or "").strip()
        confirmed_text = "；".join(rules) or summary or str(row.answer or "").strip()
        parts.append(f"已确认业务规则（{row.topic_key or '历史问答'}）：{row.question}\n确认理解：{confirmed_text}")
    return redact_sensitive_text("\n\n".join(parts), 80000)


def _clarification_history_for_prompt(db: Session, task: RequirementVerification) -> list[Dict[str, Any]]:
    rows = (
        db.query(VerificationClarification)
        .filter(VerificationClarification.task_id == task.id)
        .order_by(VerificationClarification.id.asc())
        .all()
    )
    return [
        {
            "topic_key": row.topic_key or clarification_topic_key("", row.question, row.source_ref or ""),
            "question": row.question,
            "status": row.status,
        }
        for row in rows
    ]


def _confirmed_memories(db: Session, project_id: int) -> list[Dict[str, Any]]:
    rows = (
        db.query(VerificationMemory)
        .filter(VerificationMemory.project_id == project_id, VerificationMemory.status == "confirmed")
        .order_by(VerificationMemory.id.desc())
        .limit(80)
        .all()
    )
    return [
        {"type": row.memory_type, "name": row.name, "content": json_load(row.content_json, {})}
        for row in rows
    ]


def _analysis_prompt(
    material_text: str,
    memories: list[Dict[str, Any]],
    clarification_history: list[Dict[str, Any]],
    allow_new_questions: bool,
) -> str:
    memory_text = redact_sensitive_text(json.dumps(memories, ensure_ascii=False), 30000)
    clarification_text = redact_sensitive_text(json.dumps(clarification_history, ensure_ascii=False), 20000)
    question_rule = (
        "最多返回3个真正阻塞金额、状态、权限或关键操作路径的新问题。"
        if allow_new_questions
        else "clarifications 必须返回空数组，不得产生任何新问题；不明确范围只标记关联验证项为人工或阻塞。"
    )
    return f"""
你是跨境电商高级功能测试工程师。只根据提供的需求材料和已确认项目规则生成验证计划，不得猜测。

必须遵守：
1. 不限制验证项数量，按实际需求拆分；不要为了数量制造重复项。
2. 每个验证项必须有 source_refs，指向需求原句、材料编号或已确认规则。
3. 分类只能是 page、data、state、amount、permission、exception、manual。
4. automation_level 只能是 auto、supervised、manual。缺少操作路径、数据源、状态前后值、公式或断言时必须 manual/blocked，并生成 clarification。
5. 页面动作只写业务语义，不写 CSS/XPath。config.actions 格式为 action/goal/value/risk；action 仅 goto、click、input、select、check、observe。涉及多个页面时，config.start_page 必须填写目标页面清单中的页面名称。
6. 页面采集值写入 config.observations，source=page 时填写 name/goal；只读接口 source=api 时仅在材料明确给出数据源和路径时填写。
   数据准备统一由功能分类配置，验证项 config 中禁止生成 data_setup、env_id 或“需澄清/TBD”等技术占位值。
   能机器检查的业务前置条件必须写入 config.conditions 数组，每项格式为 field/operator/value/unit；例如订单金额小于等于1000写成 {{"field":"order_amount","operator":"lte","value":"1000","unit":"CNY"}}。文字版 precondition 仍需保留。
7. config.assertions 使用 left/operator/right 或 right_value；operator 仅 eq、ne、contains、gt、gte、lt、lte、approx、exists。
8. 金额公式变量必须是合法变量名，expression 只允许四则运算、括号和 min/max/abs/round。金额规则不完整时不要补公式。
   金额验证项的 config.formula_name 必须与 formulas 中的名称完全一致。
9. {question_rule} 已存在澄清主题不得换个说法重复提问；每个问题必须提供稳定 topic_key、提问原因、2-3个候选答案和受影响验证项名称。
   验证项通过 config.blocking_topic_keys 只关联真正影响自己的问题，不能因为存在其他问题就全部阻塞。
10. 输出合法 JSON，不输出解释文字。

输出格式：
{{
  "summary":"需求摘要",
  "roles":["角色"],
  "flows":["业务流程"],
  "field_rules":["字段规则"],
  "state_rules":[{{"name":"","before":"","action":"","after":"","source_refs":[]}}],
  "formulas":[{{"name":"","expression":"","variables":{{"变量":"含义"}},"conditions":{{}},"currency":"","scale":2,"rounding_mode":"HALF_UP","rounding_stage":"final","source_refs":[]}}],
  "impacted_pages":["页面"],
  "prerequisites":["前置数据"],
  "clarifications":[{{"topic_key":"amount.exchange_rate_source","question":"","why_needed":"","suggested_answers":[],"affected_item_titles":[],"source_ref":""}}],
  "verification_items":[{{
    "item_type":"page/data/state/amount/permission/exception/manual",
    "title":"",
    "priority":"P0/P1/P2/P3",
    "role_name":"",
    "precondition":"",
    "action_goal":"",
    "expected":"",
    "source_refs":[],
    "automation_level":"auto/supervised/manual",
    "risk_level":"low/medium/high",
    "status":"draft/blocked",
    "config":{{"conditions":[],"actions":[],"observations":[],"assertions":[],"blocking_topic_keys":[]}}
  }}]
}}

已确认项目规则：
{memory_text}

历史澄清主题（只用于去重，不包含未确认答复）：
{clarification_text}

需求材料：
{material_text}
"""


def _detect_item_type(text: str) -> str:
    if any(word in text for word in ("金额", "费用", "运费", "汇率", "税费", "优惠", "单价", "总价")):
        return "amount"
    if any(word in text for word in ("状态", "审核", "流转", "已支付", "待付款", "完成")):
        return "state"
    if any(word in text for word in ("权限", "角色", "可见", "不可见")):
        return "permission"
    if any(word in text for word in ("数据", "数量", "一致", "前台", "后台")):
        return "data"
    if any(word in text for word in ("异常", "错误", "失败", "为空", "必填", "边界")):
        return "exception"
    return "page"


def _rule_analysis(task: RequirementVerification, material_text: str) -> Dict[str, Any]:
    raw_lines = [line.strip(" -\t") for line in material_text.splitlines() if line.strip()]
    ignored_prefixes = ("需求名称：", "目标页面清单：", "目标页面项：", "需求正文：", "业务上下文：")
    lines = [line for line in raw_lines if not line.startswith(ignored_prefixes)]
    items: list[Dict[str, Any]] = []
    questions: list[Dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        if len(line) < 4:
            continue
        item_type = _detect_item_type(line)
        blocked_reason = ""
        blocking_topic_keys: list[str] = []
        if item_type == "amount" and not any(mark in line for mark in ("+", "-", "*", "×", "/", "÷", "等于", "=")):
            blocked_reason = "金额公式、币种或舍入规则不完整"
            topic_key = clarification_topic_key(f"amount.requirement_line_{index}", line, f"requirement:line:{index}")
            if len(questions) < MAX_ACTIVE_CLARIFICATIONS:
                blocking_topic_keys.append(topic_key)
                questions.append({
                    "topic_key": topic_key,
                    "question": f"请确认“{line[:60]}”的计算公式、币种、精度和舍入阶段。",
                    "why_needed": "不同计算与舍入规则会直接改变预期金额。",
                    "suggested_answers": ["按需求或原型标注的规则", "沿用项目已确认金额规则", "暂时无法确认"],
                    "affected_item_titles": [line[:200]],
                    "source_ref": f"requirement:line:{index}",
                })
        if item_type == "state" and not any(mark in line for mark in ("->", "→", "变为", "更新为", "从")):
            blocked_reason = "状态变化前后值不完整"
            topic_key = clarification_topic_key(f"state.requirement_line_{index}", line, f"requirement:line:{index}")
            if len(questions) < MAX_ACTIVE_CLARIFICATIONS:
                blocking_topic_keys.append(topic_key)
                questions.append({
                    "topic_key": topic_key,
                    "question": f"请确认“{line[:60]}”操作前后的准确状态。",
                    "why_needed": "缺少前后状态时无法判断状态流转是否正确。",
                    "suggested_answers": ["按需求或原型标注状态", "沿用项目已确认状态映射", "暂时无法确认"],
                    "affected_item_titles": [line[:200]],
                    "source_ref": f"requirement:line:{index}",
                })
        items.append(
            {
                "item_type": item_type,
                "title": line[:200],
                "priority": "P1",
                "role_name": "",
                "precondition": "",
                "action_goal": line,
                "expected": line,
                "source_refs": [f"requirement:line:{index}"],
                "automation_level": "manual" if blocked_reason else "supervised",
                "risk_level": "high" if any(word in line for word in RISK_WORDS) else "low",
                "status": "blocked" if blocking_topic_keys else "draft",
                "config": {"actions": [], "observations": [], "assertions": [], "blocked_reason": blocked_reason, "blocking_topic_keys": blocking_topic_keys},
            }
        )
    if not items:
        questions.append({
            "topic_key": "requirement.minimum_testable_scope",
            "question": "当前材料不足以形成验证项，请补充具体操作、预期页面结果、状态或金额规则。",
            "why_needed": "当前没有能够形成测试结论的需求依据。",
            "suggested_answers": ["补充主要操作和预期结果", "上传原型或群聊材料", "暂时无法确认"],
            "affected_item_titles": [],
            "source_ref": "requirement",
        })
    return {
        "source": "rule",
        "summary": task.name,
        "roles": [],
        "flows": [],
        "field_rules": [],
        "state_rules": [],
        "formulas": [],
        "impacted_pages": [page["name"] for page in target_pages_for(task)],
        "prerequisites": [],
        "clarifications": questions,
        "verification_items": items,
        "warning": "未配置DeepSeek，已按需求原文生成保守草稿；系统没有补写缺失业务规则。",
    }


def _normalize_clarification_candidate(raw: Any) -> Dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"question": raw}
    if not isinstance(raw, dict):
        return None
    question = str(raw.get("question") or "").strip()
    if not question:
        return None
    source_ref = str(raw.get("source_ref") or "").strip()[:500]
    return {
        "topic_key": clarification_topic_key(raw.get("topic_key"), question, source_ref),
        "question": question[:1000],
        "why_needed": str(raw.get("why_needed") or raw.get("reason") or "该信息会影响相关验证项的预期结论。")[:1000],
        "suggested_answers": _string_list(raw.get("suggested_answers") or raw.get("options"), 3),
        "affected_item_titles": _string_list(raw.get("affected_item_titles") or raw.get("affected_items"), 20),
        "source_ref": source_ref,
    }


def _normalize_analysis(payload: Any, task: RequirementVerification, material_text: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return _rule_analysis(task, material_text)
    result = dict(payload)
    result["source"] = "ai"
    raw_clarifications = result.get("clarifications") if isinstance(result.get("clarifications"), list) else []
    normalized_clarifications = []
    seen_topic_keys: set[str] = set()
    for raw in raw_clarifications:
        clarification = _normalize_clarification_candidate(raw)
        if not clarification or clarification["topic_key"] in seen_topic_keys:
            continue
        seen_topic_keys.add(clarification["topic_key"])
        normalized_clarifications.append(clarification)
        if len(normalized_clarifications) >= MAX_ACTIVE_CLARIFICATIONS:
            break
    result["clarifications"] = normalized_clarifications
    result["formulas"] = result.get("formulas") if isinstance(result.get("formulas"), list) else []
    raw_items = result.get("verification_items") or result.get("items") or []
    normalized_items = []
    for raw in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw, dict) or not str(raw.get("title") or "").strip():
            continue
        item_type = str(raw.get("item_type") or raw.get("type") or "manual").strip().lower()
        if item_type not in ITEM_TYPES:
            item_type = "manual"
        level = str(raw.get("automation_level") or "manual").strip().lower()
        if level not in AUTOMATION_LEVELS:
            level = "manual"
        refs = raw.get("source_refs") or []
        if isinstance(refs, str):
            refs = [refs]
        refs = [str(ref).strip() for ref in refs if str(ref).strip()]
        status_value = str(raw.get("status") or "draft").strip().lower()
        config = dict(raw.get("config")) if isinstance(raw.get("config"), dict) else {}
        raw_blocking_keys = _string_list(config.get("blocking_topic_keys"), 20)
        config["blocking_topic_keys"] = [key for key in raw_blocking_keys if key in seen_topic_keys]
        if not refs:
            status_value = "draft"
            level = "manual"
            config["blocked_reason"] = "AI未提供需求依据"
            config["assumption_notice"] = "缺少需求依据，本轮只保留人工检查，不追加澄清问题。"
        normalized_items.append(
            {
                "item_type": item_type,
                "title": str(raw.get("title") or "").strip()[:220],
                "priority": str(raw.get("priority") or "P1").upper()[:20],
                "role_name": str(raw.get("role_name") or raw.get("role") or "").strip()[:120],
                "precondition": str(raw.get("precondition") or "").strip(),
                "action_goal": str(raw.get("action_goal") or raw.get("goal") or "").strip(),
                "expected": str(raw.get("expected") or "").strip(),
                "source_refs": refs,
                "automation_level": level,
                "risk_level": str(raw.get("risk_level") or "low").strip().lower()[:20],
                "status": status_value if status_value in {"draft", "blocked"} else "draft",
                "config": config,
            }
        )
    for clarification in normalized_clarifications:
        affected_titles = clarification["affected_item_titles"]
        if not affected_titles:
            continue
        for item in normalized_items:
            title = item["title"]
            if not any(title == affected or title in affected or affected in title for affected in affected_titles):
                continue
            keys = item["config"].setdefault("blocking_topic_keys", [])
            if clarification["topic_key"] not in keys:
                keys.append(clarification["topic_key"])
            item["status"] = "blocked"
    for item in normalized_items:
        if item["config"].get("blocking_topic_keys"):
            item["status"] = "blocked"
        elif item["status"] == "blocked":
            item["automation_level"] = "manual"
            item["status"] = "draft"
            item["config"]["assumption_notice"] = "本轮未作为关键问题追问，仅保留人工验证。"
    result["verification_items"] = normalized_items
    return result


def _clarification_metadata(candidate: Dict[str, Any], existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
    value = dict(existing or {})
    value["why_needed"] = candidate.get("why_needed") or value.get("why_needed") or "该信息会影响相关验证项的预期结论。"
    value["suggested_answers"] = candidate.get("suggested_answers") or value.get("suggested_answers") or []
    value["affected_item_titles"] = candidate.get("affected_item_titles") or value.get("affected_item_titles") or []
    value.setdefault("interpretation", {})
    return value


def _matching_clarification(rows: list[VerificationClarification], candidate: Dict[str, Any]) -> VerificationClarification | None:
    topic_key = candidate["topic_key"]
    for row in rows:
        row_key = row.topic_key or clarification_topic_key("", row.question, row.source_ref or "")
        if row_key == topic_key or clarification_questions_similar(row.question, candidate["question"]):
            return row
    return None


def _prepare_analysis_clarifications(
    db: Session,
    task: RequirementVerification,
    analysis: Dict[str, Any],
    version: int,
    allow_new_questions: bool,
    now: datetime,
) -> list[VerificationClarification]:
    historical = (
        db.query(VerificationClarification)
        .filter(VerificationClarification.task_id == task.id)
        .order_by(VerificationClarification.id.asc())
        .all()
    )
    for row in historical:
        if not row.topic_key:
            row.topic_key = clarification_topic_key("", row.question, row.source_ref or "")

    current_active: list[VerificationClarification] = []
    for row in historical:
        if row.status not in {"open", "pending_confirmation"}:
            continue
        if len(current_active) >= MAX_ACTIVE_CLARIFICATIONS:
            row.status = "deferred"
            row.analysis_version = version
            row.update_time = now
            continue
        row.analysis_version = version
        current_active.append(row)

    candidates = []
    if allow_new_questions:
        for raw in analysis.get("clarifications") or []:
            candidate = _normalize_clarification_candidate(raw)
            if candidate:
                candidates.append(candidate)
    for candidate in candidates:
        matched = _matching_clarification(historical, candidate)
        if matched:
            if matched.status in {"open", "pending_confirmation"} and matched not in current_active and len(current_active) < MAX_ACTIVE_CLARIFICATIONS:
                matched.analysis_version = version
                matched.review_json = json_text(_clarification_metadata(candidate, clarification_review(matched)))
                current_active.append(matched)
            continue
        if len(current_active) >= MAX_ACTIVE_CLARIFICATIONS:
            break
        row = VerificationClarification(
            task_id=task.id,
            analysis_version=version,
            question=candidate["question"],
            answer="",
            source_ref=candidate["source_ref"],
            topic_key=candidate["topic_key"],
            review_json=json_text(_clarification_metadata(candidate)),
            status="open",
            create_time=now,
            update_time=None,
        )
        db.add(row)
        db.flush()
        historical.append(row)
        current_active.append(row)

    for row in historical:
        if row.status == "deferred":
            row.analysis_version = version
    return [row for row in historical if row.status in {"open", "pending_confirmation", "deferred"}]


def _apply_clarification_blocking(analysis: Dict[str, Any], unresolved: list[VerificationClarification]) -> None:
    unresolved_by_key = {row.topic_key or "": row for row in unresolved if row.topic_key}
    for raw in analysis.get("verification_items") or []:
        if not isinstance(raw, dict):
            continue
        config = dict(raw.get("config") or {})
        title = str(raw.get("title") or "")
        linked_keys = [key for key in _string_list(config.get("blocking_topic_keys"), 20) if key in unresolved_by_key]
        for key, row in unresolved_by_key.items():
            metadata = clarification_review(row)
            affected_titles = _string_list(metadata.get("affected_item_titles"), 20)
            if affected_titles and any(title == affected or title in affected or affected in title for affected in affected_titles):
                if key not in linked_keys:
                    linked_keys.append(key)
        config["blocking_topic_keys"] = linked_keys
        raw["config"] = config
        if linked_keys:
            raw["status"] = "blocked"
        elif str(raw.get("status") or "draft") == "blocked":
            raw["status"] = "draft"
            raw["automation_level"] = "manual"
            config["assumption_notice"] = "未关联待确认关键问题，本轮只保留人工验证。"


def analyze_requirement(db: Session, task: RequirementVerification, mode: str = "standard") -> Dict[str, Any]:
    normalized_mode = str(mode or "standard").strip().lower()
    if normalized_mode not in {"standard", "continue_without_questions"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分析模式不支持")
    allow_new_questions = normalized_mode == "standard"
    material_text = _analysis_material_text(db, task)
    if not material_text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先填写需求说明或上传材料")
    config = db.query(AiConfig).order_by(AiConfig.id.desc()).first()
    if config and config.base_url and config.model:
        try:
            payload = call_local_model_json(
                config,
                _analysis_prompt(
                    material_text,
                    _confirmed_memories(db, task.project_id),
                    _clarification_history_for_prompt(db, task),
                    allow_new_questions,
                ),
                timeout=150,
            )
            analysis = _normalize_analysis(payload, task, material_text)
        except Exception as exc:
            analysis = _rule_analysis(task, material_text)
            analysis["warning"] = f"DeepSeek分析失败，已生成保守草稿：{redact_sensitive_text(exc, 300)}"
    else:
        analysis = _rule_analysis(task, material_text)

    if not allow_new_questions:
        analysis["clarifications"] = []

    version = (task.analysis_version or 0) + 1
    now = datetime.now()
    unresolved_clarifications = _prepare_analysis_clarifications(db, task, analysis, version, allow_new_questions, now)
    _apply_clarification_blocking(analysis, unresolved_clarifications)
    formulas_by_name: dict[str, VerificationFormula] = {}
    for raw in analysis.get("formulas") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        expression = str(raw.get("expression") or "").strip()
        if not name or not expression:
            continue
        formula = VerificationFormula(
            project_id=task.project_id,
            task_id=task.id,
            analysis_version=version,
            name=name[:200],
            version=1,
            expression=expression,
            variables_json=json_text(raw.get("variables") if isinstance(raw.get("variables"), dict) else {}),
            conditions_json=json_text(raw.get("conditions") if isinstance(raw.get("conditions"), dict) else {}),
            currency=str(raw.get("currency") or "")[:16],
            scale=max(0, min(int(raw.get("scale") if str(raw.get("scale", "")).isdigit() else 2), 6)),
            rounding_mode=str(raw.get("rounding_mode") or "HALF_UP").upper(),
            rounding_stage=str(raw.get("rounding_stage") or "final")[:32],
            source_refs=json_text(raw.get("source_refs") or []),
            status="draft",
            create_time=now,
            update_time=None,
        )
        try:
            validate_formula_definition(formula.expression, formula.rounding_mode, formula.scale)
        except ValueError as exc:
            analysis.setdefault("warnings", []).append(f"金额公式“{name}”无法安全执行，已转为人工确认：{exc}")
            continue
        db.add(formula)
        db.flush()
        formulas_by_name[name] = formula

    for raw in analysis.get("verification_items") or []:
        item_config = dict(raw.get("config") or {})
        formula_name = str(item_config.get("formula_name") or "").strip()
        if formula_name and formula_name in formulas_by_name:
            item_config["formula_id"] = formulas_by_name[formula_name].id
        db.add(
            VerificationItem(
                task_id=task.id,
                analysis_version=version,
                item_type=raw["item_type"],
                title=raw["title"],
                priority=raw["priority"],
                role_name=raw["role_name"],
                precondition=raw["precondition"],
                action_goal=raw["action_goal"],
                expected=raw["expected"],
                source_refs=json_text(raw["source_refs"]),
                automation_level=raw["automation_level"],
                risk_level=raw["risk_level"],
                config_json=json_text(item_config),
                status=raw["status"],
                confirmed=0,
                result_message="",
                actual_json="{}",
                create_time=now,
                update_time=None,
            )
        )
    task.analysis_version = version
    task.analysis_json = json_text({key: value for key, value in analysis.items() if key not in {"verification_items", "formulas", "clarifications"}})
    task.status = "plan_generated"
    task.update_time = now
    db.commit()
    db.refresh(task)
    return verification_detail(db, task)


def _clarification_review_prompt(
    task: RequirementVerification,
    row: VerificationClarification,
    answer: str,
    material_text: str,
    memories: list[Dict[str, Any]],
) -> str:
    metadata = clarification_review(row)
    return f"""
你是跨境电商功能测试需求分析助手。用户刚用自然语言回答了一个澄清问题。
你的任务只是复述用户的业务含义，不能补写用户没有表达的规则，也不能把猜测当事实。

请只输出以下JSON对象：
{{
  "summary":"用一句中文复述核心业务规则",
  "understood_rules":["逐条列出你明确理解到的规则"],
  "conditions":["适用条件；没有则空数组"],
  "exceptions":["例外情况；没有则空数组"],
  "affected_item_titles":["受影响的验证项标题"],
  "ambiguities":["仍有歧义的内容；没有则空数组"],
  "conflicts":["与已确认历史规则的冲突；没有则空数组"],
  "confidence":0到1之间的数字
}}

要求：
1. 只能依据用户回答、需求材料和已确认规则复述，不得自行选择金额、状态、权限或操作路径。
2. 用户回答中出现“不确定、可能、大概、应该”等表述时，必须写入 ambiguities。
3. affected_item_titles 优先使用问题元数据中的验证项标题，不得虚构不存在的标题。
4. 输出必须是合法JSON，不要输出解释文字。

功能分类：{redact_sensitive_text(task.name, 300)}
澄清问题：{redact_sensitive_text(row.question, 1500)}
提问原因：{redact_sensitive_text(metadata.get("why_needed"), 1200)}
已知受影响验证项：{redact_sensitive_text(json.dumps(metadata.get("affected_item_titles") or [], ensure_ascii=False), 5000)}
用户原始回答草稿：{redact_sensitive_text(answer, 8000)}
需求材料与已确认业务规则：
{redact_sensitive_text(material_text, 50000)}
项目已确认记忆：
{redact_sensitive_text(json.dumps(memories, ensure_ascii=False), 20000)}
"""


def _normalize_clarification_interpretation(payload: Any, row: VerificationClarification) -> Dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    summary = str(payload.get("summary") or "").strip()[:2000]
    rules = _string_list(payload.get("understood_rules") or payload.get("rules"), 30)
    if not summary or not rules:
        return None
    try:
        confidence = max(0.0, min(float(payload.get("confidence") or 0), 1.0))
    except (TypeError, ValueError):
        confidence = 0.0
    metadata = clarification_review(row)
    affected_titles = _string_list(payload.get("affected_item_titles"), 30)
    if not affected_titles:
        affected_titles = _string_list(metadata.get("affected_item_titles"), 30)
    ambiguities = _string_list(payload.get("ambiguities"), 30)
    conflicts = _string_list(payload.get("conflicts"), 30)
    return {
        "status": "ready" if confidence >= CLARIFICATION_CONFIRM_CONFIDENCE and not ambiguities and not conflicts else "needs_more_info",
        "summary": summary,
        "understood_rules": rules,
        "conditions": _string_list(payload.get("conditions"), 30),
        "exceptions": _string_list(payload.get("exceptions"), 30),
        "affected_item_titles": affected_titles,
        "ambiguities": ambiguities,
        "conflicts": conflicts,
        "confidence": confidence,
        "can_confirm": confidence >= CLARIFICATION_CONFIRM_CONFIDENCE and not ambiguities and not conflicts,
        "model_warning": "",
        "generated_at": _time_text(datetime.now()),
    }


def interpret_clarification(
    db: Session,
    row: VerificationClarification,
    answer: str = "",
    supplement: str = "",
) -> Dict[str, Any]:
    if row.status not in {"open", "pending_confirmation"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该澄清问题已处理")
    answer_text = str(answer or "").strip()
    supplement_text = str(supplement or "").strip()
    if supplement_text:
        if not str(row.answer or "").strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先填写原始回答")
        answer_text = f"{str(row.answer).strip()}\n补充说明：{supplement_text}"
    if not answer_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请填写你的回答")

    task = db.get(RequirementVerification, row.task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="功能分类不存在")
    row.answer = answer_text[:12000]
    row.status = "pending_confirmation"
    row.update_time = datetime.now()
    metadata = clarification_review(row)
    metadata["interpretation"] = {
        "status": "error",
        "summary": "",
        "understood_rules": [],
        "conditions": [],
        "exceptions": [],
        "affected_item_titles": _string_list(metadata.get("affected_item_titles"), 30),
        "ambiguities": [],
        "conflicts": [],
        "confidence": 0,
        "can_confirm": False,
        "model_warning": "AI暂时不可用，请稍后重试复述，当前回答仍是未确认草稿。",
        "generated_at": _time_text(datetime.now()),
    }

    config = db.query(AiConfig).order_by(AiConfig.id.desc()).first()
    if config and config.base_url and config.model:
        try:
            payload = call_local_model_json(
                config,
                _clarification_review_prompt(
                    task,
                    row,
                    row.answer,
                    _analysis_material_text(db, task),
                    _confirmed_memories(db, task.project_id),
                ),
                timeout=90,
            )
            interpretation = _normalize_clarification_interpretation(payload, row)
            if interpretation:
                metadata["interpretation"] = interpretation
            else:
                metadata["interpretation"]["model_warning"] = "AI复述结果格式不完整，当前回答未确认。"
        except Exception as exc:
            metadata["interpretation"]["model_warning"] = f"AI复述失败，当前回答未确认：{redact_sensitive_text(exc, 240)}"
    row.review_json = json_text(metadata)
    db.commit()
    db.refresh(row)
    return serialize_clarification(row)


def confirm_clarification(db: Session, row: VerificationClarification) -> Dict[str, Any]:
    if row.status != "pending_confirmation":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该回答不在待确认状态")
    metadata = clarification_review(row)
    interpretation = metadata.get("interpretation") if isinstance(metadata.get("interpretation"), dict) else {}
    if not interpretation.get("can_confirm"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI复述仍有歧义或置信度不足，请补充一句后重新理解")
    interpretation["confirmed_at"] = _time_text(datetime.now())
    metadata["interpretation"] = interpretation
    row.review_json = json_text(metadata)
    row.status = "answered"
    row.update_time = datetime.now()
    db.commit()
    db.refresh(row)
    return serialize_clarification(row)


def defer_clarification(db: Session, row: VerificationClarification) -> Dict[str, Any]:
    if row.status not in {"open", "pending_confirmation"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该澄清问题已处理")
    metadata = clarification_review(row)
    metadata["deferred_at"] = _time_text(datetime.now())
    row.review_json = json_text(metadata)
    row.status = "deferred"
    row.update_time = datetime.now()
    db.commit()
    db.refresh(row)
    return serialize_clarification(row)


def apply_screenshot_ocr(material: VerificationMaterial) -> Dict[str, Any]:
    if not material.image_path:
        raise ValueError("材料没有截图文件")
    result = extract_screenshot_material(material.image_path)
    material.ocr_text = str(result.get("ocr_text") or "")
    material.analysis_json = json_text(result)
    return result


def validate_formula_definition(expression: str, rounding_mode: str, scale: int) -> None:
    if rounding_mode not in ROUNDING_MODES:
        raise ValueError("不支持的舍入方式")
    if scale < 0 or scale > 6:
        raise ValueError("金额精度必须在0到6之间")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("公式语法错误") from exc
    allowed = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.USub,
        ast.UAdd,
        ast.Name,
        ast.Constant,
        ast.Call,
        ast.Load,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError(f"公式包含不允许的语法：{type(node).__name__}")
        if isinstance(node, ast.Call) and (not isinstance(node.func, ast.Name) or node.func.id not in {"min", "max", "abs", "round"}):
            raise ValueError("公式只允许min/max/abs/round函数")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, str)):
            raise ValueError("公式常量类型不受支持")


def _decimal(value: Any, name: str = "value") -> Decimal:
    if isinstance(value, Decimal):
        return value
    text = re.sub(r"[^0-9.\-]", "", str(value if value is not None else "").replace(",", ""))
    if not text:
        raise ValueError(f"{name}无法转换为数字")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{name}无法转换为数字") from exc


def _eval_formula_node(node: ast.AST, values: Dict[str, Decimal]) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval_formula_node(node.body, values)
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise ValueError(f"缺少公式变量：{node.id}")
        return values[node.id]
    if isinstance(node, ast.Constant):
        return _decimal(node.value)
    if isinstance(node, ast.UnaryOp):
        value = _eval_formula_node(node.operand, values)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        left = _eval_formula_node(node.left, values)
        right = _eval_formula_node(node.right, values)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ValueError("公式除数不能为0")
            return left / right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        args = [_eval_formula_node(arg, values) for arg in node.args]
        if node.func.id == "min":
            return min(args)
        if node.func.id == "max":
            return max(args)
        if node.func.id == "abs":
            if len(args) != 1:
                raise ValueError("abs函数需要1个参数")
            return abs(args[0])
        if node.func.id == "round":
            if not 1 <= len(args) <= 2:
                raise ValueError("round函数需要1到2个参数")
            digits = int(args[1]) if len(args) == 2 else 0
            return args[0].quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    raise ValueError("公式包含无法执行的语法")


def evaluate_formula(formula: VerificationFormula, raw_values: Dict[str, Any]) -> Dict[str, Any]:
    validate_formula_definition(formula.expression, formula.rounding_mode, formula.scale)
    declared = json_load(formula.variables_json, {})
    required = set(declared) if isinstance(declared, dict) and declared else {
        node.id for node in ast.walk(ast.parse(formula.expression, mode="eval")) if isinstance(node, ast.Name) and node.id not in {"min", "max", "abs", "round"}
    }
    values = {name: _decimal(raw_values.get(name), name) for name in required}
    conditions = json_load(formula.conditions_json, {})
    if isinstance(conditions, dict):
        for name, expected in conditions.items():
            if name not in raw_values or str(raw_values[name]) != str(expected):
                raise VerificationBlocked(f"金额公式适用条件不满足：{name}={expected}")
    raw_result = _eval_formula_node(ast.parse(formula.expression, mode="eval"), values)
    quantum = Decimal(1).scaleb(-formula.scale)
    rounded = raw_result.quantize(quantum, rounding=ROUNDING_MODES[formula.rounding_mode])
    return {
        "formula_id": formula.id,
        "formula_name": formula.name,
        "formula_version": formula.version,
        "expression": formula.expression,
        "inputs": {key: str(value) for key, value in values.items()},
        "raw_result": str(raw_result),
        "rounding_mode": formula.rounding_mode,
        "rounding_stage": formula.rounding_stage,
        "scale": formula.scale,
        "currency": formula.currency or "",
        "expected_amount": str(rounded),
    }


def _template(value: Any, variables: Dict[str, Any]) -> Any:
    if not isinstance(value, str):
        return value
    return re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", lambda match: str(variables.get(match.group(1), match.group(0))), value)


def _template_value(value: Any, variables: Dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _template_value(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_template_value(item, variables) for item in value]
    return _template(value, variables)


def _runtime_url(value: Any, variables: Dict[str, Any]) -> str:
    rendered = str(_template(value or "", variables)).strip()
    if not rendered:
        return ""
    try:
        parts = urlsplit(rendered)
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        replaced = []
        for key, current in pairs:
            variable_value = variables.get(key)
            if key in BUSINESS_URL_VARIABLES and variable_value not in (None, ""):
                replaced.append((key, str(variable_value)))
            else:
                replaced.append((key, current))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(replaced, doseq=True), parts.fragment))
    except (TypeError, ValueError):
        return rendered


def _nested(payload: Any, path: str) -> Any:
    current = payload
    for part in [item for item in str(path or "").replace("[", ".").replace("]", "").split(".") if item]:
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise KeyError(path)
    return current


def _allowed_api_path(path: str, allowed: Iterable[str]) -> bool:
    parsed_path = urlparse(path).path or "/"
    for prefix in allowed:
        normalized = "/" + str(prefix or "").strip().lstrip("/")
        normalized = normalized.rstrip("/") or "/"
        if parsed_path == normalized or parsed_path.startswith(normalized + "/"):
            return True
    return False


def _api_observation(db: Session, project_id: int, spec: Dict[str, Any], variables: Dict[str, Any]) -> Any:
    source_id = int(spec.get("data_source_id") or 0)
    source = db.get(VerificationDataSource, source_id)
    if not source or source.project_id != project_id or source.status != "active":
        raise VerificationBlocked("只读数据源不存在、未启用或不属于当前项目")
    env = db.get(Env, source.env_id)
    if not env or env.project_id != project_id:
        raise VerificationBlocked("只读数据源环境不属于当前项目")
    method = str(spec.get("method") or "GET").upper()
    if method not in {"GET", "HEAD"}:
        raise VerificationBlocked("首版只读数据源仅允许GET/HEAD")
    path = str(_template(spec.get("path") or "", variables)).strip()
    if not path or not _allowed_api_path(path, json_load(source.allowed_paths, [])):
        raise VerificationBlocked("接口路径不在项目只读白名单")
    params = spec.get("params") if isinstance(spec.get("params"), dict) else {}
    rendered_params = {key: _template(value, variables) for key, value in params.items()}
    query = urlencode(rendered_params, doseq=True)
    url = urljoin(env.base_url.rstrip("/") + "/", path.lstrip("/"))
    if query:
        url += ("&" if "?" in url else "?") + query
    headers = parse_json_value(env.global_headers or "", {})
    response = guarded_proxy_request(method, url, headers if isinstance(headers, dict) else {}, "", int(env.timeout or 20))
    if response.status_code >= 400:
        raise VerificationBlocked(f"只读接口返回HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise VerificationBlocked("只读接口未返回JSON") from exc
    value_path = str(spec.get("value_path") or "").strip()
    return _nested(payload, value_path) if value_path else payload


def _compare(left: Any, operator: str, right: Any, tolerance: Any = None) -> tuple[bool, str]:
    operator = str(operator or "eq").lower()
    if operator == "exists":
        passed = left not in (None, "", [], {})
        return passed, f"实际值={'存在' if passed else '不存在'}"
    if operator == "contains":
        passed = str(right) in str(left)
        return passed, f"实际={left}，应包含={right}"
    if operator in {"gt", "gte", "lt", "lte", "approx"}:
        left_num = _decimal(left, "left")
        right_num = _decimal(right, "right")
        if operator == "gt":
            passed = left_num > right_num
        elif operator == "gte":
            passed = left_num >= right_num
        elif operator == "lt":
            passed = left_num < right_num
        elif operator == "lte":
            passed = left_num <= right_num
        else:
            passed = abs(left_num - right_num) <= _decimal(tolerance if tolerance is not None else "0.01", "tolerance")
        return passed, f"实际={left_num}，预期={right_num}"
    left_text = " ".join(str(left if left is not None else "").split())
    right_text = " ".join(str(right if right is not None else "").split())
    passed = left_text != right_text if operator == "ne" else left_text == right_text
    return passed, f"实际={left_text}，预期={right_text}"


def resolve_confirmation(
    run_item_id: int,
    decision: str,
    candidate_index: int | None = None,
    note: str = "",
    observed_value: Any = None,
) -> bool:
    db = SessionLocal()
    try:
        run_item = db.get(VerificationRunItem, run_item_id)
        if not run_item:
            return False
        run = resolve_manual_action(db, run_item, decision, candidate_index, note, observed_value)
        threading.Thread(target=execute_verification_run, args=(run.id,), daemon=True, name=f"verification-run-{run.id}").start()
        return True
    except HTTPException:
        return False
    finally:
        db.close()


def _manual_browser_session_id(run_id: int) -> str:
    return f"verification-run-{run_id}-manual"


def _manual_browser_target(
    db: Session,
    run: VerificationRun,
) -> tuple[RequirementVerification, VerificationRunItem, VerificationItem, TestAccountProfile, Dict[str, Any], str]:
    run_item = (
        db.query(VerificationRunItem)
        .filter(
            VerificationRunItem.run_id == run.id,
            VerificationRunItem.result.in_(["waiting_user", "waiting_confirmation"]),
        )
        .order_by(VerificationRunItem.id.asc())
        .first()
    )
    if not run_item:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前执行没有等待人工处理的页面")
    task = db.get(RequirementVerification, run.task_id)
    item = db.get(VerificationItem, run_item.item_id)
    if not task or not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="功能分类或验证项不存在")
    config = json_load(item.config_json, {})
    profile_id = _safe_positive_int(config.get("account_profile_id"))
    profile = db.get(TestAccountProfile, profile_id) if profile_id else default_account_profile_for_target(db, "requirement_verification", task.id, task.project_id)
    if not profile or profile.status != "active" or profile.project_id not in {None, task.project_id}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先绑定当前项目的有效测试账号")
    variables = json_load(run.variables_json, {})
    if run_item.dataset_id:
        dataset = db.get(VerificationRunDataset, run_item.dataset_id)
        if dataset:
            variables.update(json_load(dataset.variables_json, {}))
    resume = json_load(run_item.resume_json, {})
    evidence = json_load(run_item.evidence_json, {})
    pending = resume.get("pending") if isinstance(resume.get("pending"), dict) else {}
    url = str(pending.get("url") or evidence.get("current_url") or evidence.get("final_url") or "").strip()
    if not url:
        url = target_page_url(task, str(config.get("start_page") or ""))
    url = _runtime_url(url, variables)
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前人工处理项没有可打开的页面地址")
    return task, run_item, item, profile, variables, url


async def open_manual_takeover_browser(db: Session, run: VerificationRun, user_id: int | None = None) -> Dict[str, Any]:
    from . import ui_recording_session

    session_id = _manual_browser_session_id(run.id)
    try:
        existing = ui_recording_session.get_session_state(session_id)
        return {"status": "already_open", "session_id": session_id, "current_url": existing.get("current_url") or ""}
    except ValueError:
        pass
    task, _run_item, _item, profile, _variables, url = _manual_browser_target(db, run)
    stored = decrypt_account_payload(profile.browser_state_encrypted)
    storage_state = stored.get("storage_state") if isinstance(stored, dict) else None
    await ui_recording_session.start_session(
        task.project_id,
        f"{task.name}-人工接管",
        url,
        user_id,
        storage_state if isinstance(storage_state, dict) else None,
        preferred_session_id=session_id,
        persistent=True,
        persist_learning_events=False,
    )
    return {"status": "opened", "session_id": session_id, "current_url": url}


async def close_manual_takeover_browser(db: Session, run: VerificationRun) -> None:
    from . import ui_recording_session

    session_id = _manual_browser_session_id(run.id)
    storage_state = await ui_recording_session.get_session_storage_state(session_id)
    if storage_state:
        try:
            _task, _run_item, _item, profile, _variables, _url = _manual_browser_target(db, run)
            profile.browser_state_encrypted = encrypt_account_payload({"storage_state": storage_state})
            profile.browser_session_status = "valid"
            profile.browser_session_validated_at = datetime.now()
            profile.update_time = datetime.now()
            db.commit()
        except HTTPException:
            pass
    await ui_recording_session.close_session(session_id)


def _wait_confirmation(db: Session, run_item: VerificationRunItem, detail: Dict[str, Any], timeout_seconds: int = 300) -> Dict[str, Any]:
    del timeout_seconds  # V2 人工接管永久保留，不再使用超时。
    request_type = str(detail.get("type") or "manual_check")
    response = consume_manual_decision(run_item, request_type)
    if response is not None:
        db.commit()
        if response.get("decision") not in {"continue", "user_completed", "select", "provide_value", "retry", "skip", "pass", "fail", "defer", "wait", "reopen"}:
            raise VerificationNeedsReview(response.get("note") or "人工暂不处理")
        return response
    run = db.get(VerificationRun, run_item.run_id)
    if not run:
        raise VerificationBlocked("执行记录不存在")
    request_manual_action(db, run, run_item, detail)
    raise VerificationAwaitingUser(str(detail.get("message") or "等待人工处理"))


def _semantic_snapshot(page: Any) -> list[Dict[str, Any]]:
    candidates: list[Dict[str, Any]] = []
    for frame_index, frame in enumerate(page.frames):
        if len(candidates) >= 1500:
            break
        try:
            rows = frame.evaluate(
                r"""
                (limit) => {
                  const selectors = 'button,a,input,textarea,select,[role],label,th,td,[data-testid],.status,.amount,[class*="amount"],[class*="status"]';
                  const visible = (el) => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
                  };
                  const clean = (value, max = 260) => String(value || '').trim().replace(/\s+/g, ' ').slice(0, max);
                  const found = [];
                  const visit = (root) => {
                    if (!root || found.length >= limit) return;
                    for (const el of root.querySelectorAll('*')) {
                      if (found.length >= limit) break;
                      if (el.shadowRoot) visit(el.shadowRoot);
                      if (!el.matches || !el.matches(selectors) || !visible(el)) continue;
                      found.push(el);
                    }
                  };
                  visit(document);
                  return found.slice(0, limit).map((el, index) => {
                    el.setAttribute('data-verification-candidate', String(index));
                    const text = clean(el.innerText || el.textContent || el.value, 220);
                    const row = el.closest('tr');
                    const cell = el.closest('td,th');
                    const sibling = cell ? cell.nextElementSibling : el.nextElementSibling;
                    const previous = cell ? cell.previousElementSibling : el.previousElementSibling;
                    const parent = el.closest('label,.form-item,.el-form-item,.ant-form-item,td,tr,dl') || el.parentElement;
                    return {
                      selector_id: index,
                      tag: el.tagName.toLowerCase(),
                      type: el.getAttribute('type') || '',
                      role: el.getAttribute('role') || '',
                      text,
                      label: clean(el.getAttribute('aria-label'), 160),
                      placeholder: clean(el.getAttribute('placeholder'), 160),
                      name: clean(el.getAttribute('name'), 120),
                      context: clean((parent && (parent.innerText || parent.textContent)) || '', 500),
                      next_text: clean((sibling && (sibling.innerText || sibling.textContent || sibling.value)) || '', 220),
                      previous_text: clean((previous && (previous.innerText || previous.textContent || previous.value)) || '', 220),
                      row_cells: row ? Array.from(row.querySelectorAll(':scope > th,:scope > td')).map((node) => clean(node.innerText || node.textContent || node.value, 220)).slice(0, 20) : [],
                      frame_url: location.href
                    };
                  });
                }
                """,
                1500 - len(candidates),
            )
        except Exception:
            continue
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            row["id"] = len(candidates)
            row["frame_index"] = frame_index
            candidates.append(row)
    return candidates


def _candidate_score(candidate: Dict[str, Any], goal: str, field_name: str = "") -> int:
    haystack = " ".join(str(candidate.get(key) or "") for key in ("text", "label", "placeholder", "name", "context")).lower()
    compact_goal = re.sub(r"\s+", "", goal.lower())
    score = 0
    exact_name = str(field_name or "").strip().lower()
    candidate_text = str(candidate.get("text") or "").strip().lower().rstrip("：:")
    if exact_name and candidate_text == exact_name.rstrip("：:"):
        score += 240
        if candidate.get("next_text") or candidate.get("row_cells"):
            score += 40
    elif exact_name and exact_name in haystack:
        score += 120
    if compact_goal and compact_goal in re.sub(r"\s+", "", haystack):
        score += 100
    tokens = set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", goal.lower()))
    for token in tokens:
        if token in haystack:
            score += 10 + min(len(token), 8)
    return score


def _choose_candidate(db: Session, item: VerificationItem, action: Dict[str, Any], candidates: list[Dict[str, Any]]) -> tuple[int | None, float, str]:
    goal = str(action.get("goal") or item.action_goal or item.title)
    field_name = str(action.get("field_name") or action.get("name") or "").strip()
    config = db.query(AiConfig).order_by(AiConfig.id.desc()).first()
    if config and config.base_url and config.model:
        prompt = f"""
你在执行PC网页功能测试。请根据业务目标，从候选元素中选择唯一目标。
只输出JSON：{{"candidate_id":数字或null,"confidence":0到1,"reason":"简短原因"}}。
不能确定时必须返回null，不要猜测。
动作：{action.get('action')}
真实字段名称：{redact_sensitive_text(field_name, 300)}
目标：{redact_sensitive_text(goal, 1000)}
候选：{redact_sensitive_text(json.dumps(candidates, ensure_ascii=False), 28000)}
"""
        try:
            result = call_local_model_json(config, prompt, timeout=60)
            if isinstance(result, dict):
                candidate_id = result.get("candidate_id")
                if candidate_id is not None and any(int(row["id"]) == int(candidate_id) for row in candidates):
                    return int(candidate_id), float(result.get("confidence") or 0), str(result.get("reason") or "")
        except Exception:
            pass
    ranked = sorted(((_candidate_score(row, goal, field_name), int(row["id"])) for row in candidates), reverse=True)
    if ranked and ranked[0][0] >= 40 and (len(ranked) == 1 or ranked[0][0] > ranked[1][0]):
        return ranked[0][1], 0.75, "本地语义唯一匹配"
    return None, 0, "没有可靠的唯一候选"


def _candidate_locator(page: Any, candidates: list[Dict[str, Any]], candidate_id: int) -> Any:
    candidate = next((row for row in candidates if int(row.get("id", -1)) == int(candidate_id)), None)
    if not candidate:
        raise VerificationBlocked("页面候选元素已经失效")
    frame_index = int(candidate.get("frame_index") or 0)
    if frame_index >= len(page.frames):
        raise VerificationNeedsReview("iframe页面结构已变化，请人工选择目标字段")
    selector_id = int(candidate.get("selector_id") or 0)
    return page.frames[frame_index].locator(f'[data-verification-candidate="{selector_id}"]').first


def _clean_observed_value(value: Any, value_type: str = "") -> Any:
    if not isinstance(value, str):
        return value
    cleaned = " ".join(value.split()).strip()
    if value_type in {"money", "amount", "decimal"}:
        match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", cleaned)
        if match:
            return match.group(0).replace(",", "")
    return cleaned


def _extract_candidate_value(candidate: Dict[str, Any], field_name: str, value_type: str = "") -> Any:
    label = str(field_name or "").strip().rstrip("：:")
    text = str(candidate.get("text") or "").strip()
    if label and text.rstrip("：:") == label:
        next_text = str(candidate.get("next_text") or "").strip()
        if next_text:
            return _clean_observed_value(next_text, value_type)
        cells = [str(value or "").strip() for value in candidate.get("row_cells") or []]
        for index, cell in enumerate(cells):
            if cell.rstrip("：:") == label and index + 1 < len(cells) and cells[index + 1]:
                return _clean_observed_value(cells[index + 1], value_type)
        return None
    return _clean_observed_value(text, value_type)


def _capture(page: Any, task_id: int, run_id: int, item_id: int, label: str) -> str:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"task-{task_id}-run-{run_id}-item-{item_id}-{label}-{uuid4().hex[:8]}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def _page_readiness_state(page: Any) -> Dict[str, Any]:
    try:
        return page.evaluate(
            r"""
            () => {
              const visible = (el) => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
              };
              const text = String(document.body?.innerText || '').replace(/\s+/g, ' ').trim();
              const masks = Array.from(document.querySelectorAll('.el-loading-mask,.ant-spin-spinning,[class*="loading-mask"],[aria-busy="true"]')).filter(visible).length;
              const dialogs = Array.from(document.querySelectorAll('[role="dialog"],.el-message-box,.ant-modal,.el-dialog')).filter(visible).map((el) => String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 500));
              const businessNodes = Array.from(document.querySelectorAll('main,table,.el-table,.ant-table,[class*="detail"],[class*="summary"],[class*="result"],[class*="order"]')).filter(visible).length;
              return {
                ready_state: document.readyState,
                masks,
                dialogs,
                business_nodes: businessNodes,
                text_length: text.length,
                signature: `${location.href}|${text.length}|${text.slice(-300)}`,
                body_excerpt: text.slice(0, 1600)
              };
            }
            """
        )
    except Exception as exc:
        return {"ready_state": "error", "masks": 0, "dialogs": [], "business_nodes": 0, "signature": "", "body_excerpt": str(exc)}


def _wait_page_business_ready(page: Any, timeout_seconds: int = 35) -> Dict[str, Any]:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=min(timeout_seconds * 1000, 30000))
    except Exception:
        pass
    deadline = time.monotonic() + timeout_seconds
    previous_signature = ""
    stable_count = 0
    last_state: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_state = _page_readiness_state(page)
        text = str(last_state.get("body_excerpt") or "")
        lowered = text.lower()
        if any(word in lowered for word in ("验证码", "captcha", "滑块验证", "安全验证")):
            return {**last_state, "ready": False, "problem": "captcha", "message": "页面需要验证码，请在测试浏览器中完成验证"}
        if any(word in lowered for word in ("登录已失效", "请重新登录", "login expired", "session expired")):
            return {**last_state, "ready": False, "problem": "auth", "message": "当前登录已失效，需要重新登录"}
        if any(word in lowered for word in ("权限不足", "无权访问", "forbidden", "access denied")):
            return {**last_state, "ready": False, "problem": "permission", "message": "当前账号没有访问该页面的权限"}
        signature = str(last_state.get("signature") or "")
        stable_count = stable_count + 1 if signature and signature == previous_signature else 0
        previous_signature = signature
        if last_state.get("ready_state") == "complete" and int(last_state.get("masks") or 0) == 0 and int(last_state.get("business_nodes") or 0) > 0 and stable_count >= 2:
            warnings = [
                dialog
                for dialog in last_state.get("dialogs") or []
                if any(keyword in str(dialog) for keyword in ("数据异常", "数量和单价", "金额不一致", "商品数量", "报价异常"))
            ]
            return {**last_state, "ready": True, "problem": "", "data_warnings": warnings}
        page.wait_for_timeout(500)
    return {**last_state, "ready": False, "problem": "timeout", "message": "页面业务区域在等待时间内没有准备完成"}


class BrowserSessions:
    def __init__(self, db: Session, project_id: int, visible: bool):
        self.db = db
        self.project_id = project_id
        self.visible = visible
        self.playwright = None
        self.browser = None
        self.pages: dict[str, Any] = {}
        self.logged_in: set[str] = set()
        self.profile_by_session: dict[str, TestAccountProfile] = {}

    def __enter__(self) -> "BrowserSessions":
        from playwright.sync_api import sync_playwright

        self.playwright = sync_playwright().start()
        self.browser = launch_chromium_browser(self.playwright, headless=not self.visible)
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        for page in self.pages.values():
            try:
                page.context.close()
            except Exception:
                pass
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def page_for(self, task: RequirementVerification, item: VerificationItem, variables: Dict[str, Any]) -> Any:
        config = json_load(item.config_json, {})
        session_key = str(config.get("session_key") or item.role_name or "default")
        explicit_profile_id = _safe_positive_int(config.get("account_profile_id"))
        default_profile = default_account_profile_for_target(self.db, "requirement_verification", task.id, task.project_id)
        account_profile_id = explicit_profile_id or (default_profile.id if default_profile else 0)
        profile = self.db.get(TestAccountProfile, account_profile_id) if account_profile_id else None
        if session_key not in self.pages:
            context_options: Dict[str, Any] = {"ignore_https_errors": True}
            if profile and profile.browser_state_encrypted:
                stored = decrypt_account_payload(profile.browser_state_encrypted)
                storage_state = stored.get("storage_state") if isinstance(stored, dict) else None
                if isinstance(storage_state, dict) and isinstance(storage_state.get("cookies"), list):
                    context_options["storage_state"] = storage_state
            context = self.browser.new_context(**context_options)
            self.pages[session_key] = context.new_page()
            if profile:
                self.profile_by_session[session_key] = profile
        page = self.pages[session_key]
        start_url = _runtime_url(config.get("start_url") or target_page_url(task, config.get("start_page") or ""), variables)
        if account_profile_id and session_key not in self.logged_in:
            account_vars, meta = account_profile_variables(self.db, account_profile_id, self.project_id)
            variables.update({key: value for key, value in account_vars.items() if key not in variables})
            restored = False
            if profile and profile.browser_state_encrypted and start_url:
                try:
                    page.goto(start_url, wait_until="domcontentloaded", timeout=30000)
                    password_visible = page.locator('input[type="password"],input[name="password"]').first.is_visible(timeout=800)
                    restored = not password_visible and not any(marker in page.url.lower() for marker in ("/login", "#/login", "signin"))
                except Exception:
                    restored = False
            if not restored:
                _prepare_authenticated_page(
                    page,
                    {"login_required": True, "login_config": meta.get("login_config") or {}, "target_url": start_url},
                    variables,
                    45,
                )
            self.logged_in.add(session_key)
            if profile:
                profile.browser_state_encrypted = encrypt_account_payload({"storage_state": page.context.storage_state()})
                profile.browser_session_status = "valid"
                profile.browser_session_validated_at = datetime.now()
                profile.update_time = datetime.now()
                self.db.commit()
        return page


def _browser_part(
    db: Session,
    sessions: BrowserSessions,
    task: RequirementVerification,
    item: VerificationItem,
    run: VerificationRun,
    run_item: VerificationRunItem,
    variables: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    config = json_load(item.config_json, {})
    page = sessions.page_for(task, item, variables)
    start_url = _runtime_url(config.get("start_url") or target_page_url(task, config.get("start_page") or ""), variables)
    evidence: Dict[str, Any] = json_load(run_item.evidence_json, {})
    evidence.setdefault("actions", [])
    evidence.setdefault("screenshots", [])
    resume_state = json_load(run_item.resume_json, {})
    resume_url = str(evidence.get("current_url") or evidence.get("final_url") or "") if resume_state.get("pending") else ""
    open_url = _runtime_url(resume_url or start_url, variables)
    if open_url and (page.url in {"", "about:blank"} or resume_url):
        page.goto(open_url, wait_until="domcontentloaded", timeout=30000)
    readiness = _wait_page_business_ready(page)
    if not readiness.get("ready"):
        problem = str(readiness.get("problem") or "timeout")
        if problem == "permission":
            raise VerificationBlocked(str(readiness.get("message") or "当前账号权限不足"))
        response = _wait_confirmation(
            db,
            run_item,
            {
                "type": "login" if problem in {"auth", "captcha"} else "page_not_ready",
                "message": str(readiness.get("message") or "页面业务区域没有准备完成"),
                "url": page.url,
                "available_actions": ["continue", "reopen", "skip"],
            },
        )
        if response.get("decision") == "skip":
            raise VerificationNeedsReview("用户跳过页面准备异常")
        if response.get("decision") == "reopen" and open_url:
            page.goto(open_url, wait_until="domcontentloaded", timeout=30000)
        readiness = _wait_page_business_ready(page)
        if not readiness.get("ready"):
            raise VerificationNeedsReview(str(readiness.get("message") or "页面未准备完成"))
    if readiness.get("data_warnings"):
        evidence["data_warnings"] = readiness["data_warnings"]
        run_item.evidence_json = json_text(evidence)
        db.commit()
        raise VerificationBlocked(f"测试数据页面出现异常警告：{readiness['data_warnings'][0]}")
    evidence["screenshots"].append(_capture(page, task.id, run.id, item.id, "before"))
    completed_steps = {int(row.get("step") or 0) for row in evidence.get("actions") or [] if isinstance(row, dict)}
    for index, raw_action in enumerate(config.get("actions") or [], start=1):
        if not isinstance(raw_action, dict):
            continue
        action = str(raw_action.get("action") or "observe").lower()
        goal = str(raw_action.get("goal") or item.action_goal or item.title)
        if index in completed_steps and resume_url:
            continue
        if action == "goto":
            url = _runtime_url(raw_action.get("value") or start_url, variables)
            if not url:
                raise VerificationBlocked("goto动作缺少地址")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            evidence["actions"].append({"step": index, "action": action, "goal": goal, "url": page.url})
            evidence["current_url"] = page.url
            run_item.evidence_json = json_text(evidence)
            db.commit()
            continue
        is_risk = bool(raw_action.get("risk")) or any(word in goal for word in RISK_WORDS)
        if is_risk:
            evidence["current_url"] = page.url
            run_item.evidence_json = json_text(evidence)
            db.commit()
            response = _wait_confirmation(db, run_item, {"type": "risk", "message": f"高风险动作等待确认：{goal}", "action": raw_action, "url": page.url})
            if response.get("decision") == "skip":
                raise VerificationNeedsReview(f"已跳过高风险动作：{goal}")
            if response.get("decision") == "user_completed":
                evidence["actions"].append({"step": index, "action": action, "goal": goal, "handled_by": "user"})
                continue
        if action == "observe":
            evidence["actions"].append({"step": index, "action": action, "goal": goal, "handled_by": "observation"})
            evidence["current_url"] = page.url
            run_item.evidence_json = json_text(evidence)
            db.commit()
            continue
        candidates = _semantic_snapshot(page)
        candidate_id, confidence, reason = _choose_candidate(db, item, raw_action, candidates)
        if candidate_id is None or confidence < 0.72:
            evidence["current_url"] = page.url
            run_item.evidence_json = json_text(evidence)
            db.commit()
            response = _wait_confirmation(
                db,
                run_item,
                {"type": "ambiguous_locator", "message": f"无法可靠定位：{goal}", "action": raw_action, "url": page.url, "candidates": candidates[:80]},
            )
            if response.get("decision") == "skip":
                raise VerificationNeedsReview(f"已跳过无法可靠定位的页面动作：{goal}")
            if response.get("decision") == "user_completed":
                evidence["actions"].append({"step": index, "action": action, "goal": goal, "handled_by": "user"})
                continue
            candidate_id = response.get("candidate_index")
            if candidate_id is None:
                raise VerificationBlocked("人工确认未指定页面元素")
        target = _candidate_locator(page, candidates, int(candidate_id))
        value = _template(raw_action.get("value") or "", variables)
        if action == "click":
            target.click(timeout=10000)
        elif action == "input":
            target.fill(str(value), timeout=10000)
        elif action == "select":
            try:
                target.select_option(label=str(value), timeout=10000)
            except Exception:
                target.select_option(value=str(value), timeout=10000)
        elif action == "check":
            target.check(timeout=10000)
        elif action != "observe":
            raise VerificationBlocked(f"不支持的页面动作：{action}")
        page.wait_for_timeout(int(raw_action.get("wait_ms") or 500))
        evidence["actions"].append({"step": index, "action": action, "goal": goal, "candidate_id": candidate_id, "confidence": confidence, "reason": reason})
        evidence["current_url"] = page.url
        run_item.evidence_json = json_text(evidence)
        db.commit()

    observations: Dict[str, Any] = {}
    for spec in config.get("observations") or []:
        if not isinstance(spec, dict) or spec.get("source") != "page":
            continue
        name = str(spec.get("name") or "").strip()
        if not name:
            continue
        candidates = _semantic_snapshot(page)
        lookup = {"action": "observe", "field_name": spec.get("field_name") or name, "goal": spec.get("goal") or name}
        candidate_id, confidence, reason = _choose_candidate(db, item, lookup, candidates)
        while candidate_id is None or confidence < 0.72:
            evidence["current_url"] = page.url
            run_item.evidence_json = json_text(evidence)
            db.commit()
            response = _wait_confirmation(
                db,
                run_item,
                {
                    "type": "observation_value",
                    "message": f"请查看页面中的“{spec.get('goal') or name}”，填写实际值后继续",
                    "observation_name": name,
                    "observation_goal": str(spec.get("goal") or name),
                    "url": page.url,
                    "candidates": candidates[:40],
                },
                timeout_seconds=180,
            )
            if response.get("decision") == "provide_value":
                observations[name] = response.get("observed_value")
                evidence.setdefault("observations", []).append({"name": name, "value": observations[name], "handled_by": "user"})
                break
            if response.get("decision") == "skip":
                raise VerificationNeedsReview(f"已跳过页面字段“{spec.get('goal') or name}”的人工采集")
            if response.get("decision") != "retry":
                raise VerificationNeedsReview(f"页面字段“{spec.get('goal') or name}”等待人工处理")
            candidates = _semantic_snapshot(page)
            candidate_id, confidence, reason = _choose_candidate(db, item, lookup, candidates)
        if name in observations:
            continue
        candidate = next((row for row in candidates if int(row.get("id", -1)) == int(candidate_id)), {})
        target = _candidate_locator(page, candidates, int(candidate_id))
        if str(candidate.get("tag")) in {"input", "textarea", "select"}:
            value = target.input_value(timeout=3000)
        else:
            value = _extract_candidate_value(candidate, str(spec.get("field_name") or name), str(spec.get("value_type") or ""))
        if value in (None, ""):
            evidence["current_url"] = page.url
            run_item.evidence_json = json_text(evidence)
            db.commit()
            response = _wait_confirmation(
                db,
                run_item,
                {
                    "type": "observation_value",
                    "message": f"已找到字段“{spec.get('field_name') or name}”，但没有找到相邻实际值，请点击或填写实际值",
                    "observation_name": name,
                    "url": page.url,
                },
            )
            if response.get("decision") == "provide_value":
                value = response.get("observed_value")
            else:
                raise VerificationNeedsReview(f"字段“{spec.get('field_name') or name}”缺少实际值")
        observations[name] = _clean_observed_value(value, str(spec.get("value_type") or ""))
        evidence.setdefault("observations", []).append({"name": name, "value": observations[name], "candidate_id": candidate_id, "confidence": confidence, "reason": reason})
    evidence["screenshots"].append(_capture(page, task.id, run.id, item.id, "after"))
    evidence["final_url"] = page.url
    run_item.evidence_json = json_text(evidence)
    db.commit()
    return observations, evidence


def _needs_browser(item: VerificationItem) -> bool:
    config = json_load(item.config_json, {})
    if config.get("actions"):
        return True
    return any(isinstance(spec, dict) and spec.get("source") == "page" for spec in config.get("observations") or [])


def _execute_item(
    db: Session,
    sessions: BrowserSessions | None,
    task: RequirementVerification,
    item: VerificationItem,
    run: VerificationRun,
    run_item: VerificationRunItem,
    variables: Dict[str, Any],
    setup_cache: Dict[str, Dict[str, Any]],
) -> tuple[str, str, Dict[str, Any], Dict[str, Any]]:
    config = json_load(item.config_json, {})
    if config.get("blocked_reason"):
        raise VerificationBlocked(str(config["blocked_reason"]))
    observations: Dict[str, Any] = {}
    evidence: Dict[str, Any] = json_load(run_item.evidence_json, {})
    setup = config.get("data_setup") if isinstance(config.get("data_setup"), dict) else None
    category_setup = json_load(run.data_setup_json, {"steps": []})
    if any(step.get("enabled", True) for step in category_setup.get("steps") or [] if isinstance(step, dict)):
        setup = None
        if isinstance(config.get("data_setup"), dict):
            evidence["legacy_data_setup_ignored"] = True
    if setup:
        script_type = str(setup.get("script_type") or "").strip()
        env_id = _safe_positive_int(setup.get("env_id"))
        if env_id is None:
            raise VerificationBlocked("旧验证项的数据环境未配置完成，请改用功能分类统一数据准备")
        setup_vars = _template_value(setup.get("variables") if isinstance(setup.get("variables"), dict) else {}, variables)
        cache_key = json_text({"script_type": script_type, "env_id": env_id, "variables": setup_vars})
        if cache_key in setup_cache:
            variables.update(setup_cache[cache_key])
            evidence["data_setup"] = {"script_type": script_type, "reused": True, "outputs": setup_cache[cache_key]}
        else:
            definition = SCRIPT_REGISTRY.get(script_type)
            runner = definition.get("func") if isinstance(definition, dict) else None
            if not callable(runner):
                raise VerificationBlocked(f"数据工厂脚本不存在或未注册：{script_type}")
            env = db.get(Env, env_id) if env_id else db.query(Env).filter(Env.project_id == task.project_id).order_by(Env.id.asc()).first()
            if not env or env.project_id != task.project_id:
                raise VerificationBlocked("数据工厂环境不存在或不属于当前项目")
            if any(word in script_type.lower() for word in ("payment", "pay", "recharge", "refund")) or any(word in str(definition.get("name") or "") for word in ("支付", "付款", "充值", "退款")):
                response = _wait_confirmation(db, run_item, {"type": "risk", "message": f"数据工厂高风险脚本等待确认：{definition.get('name') or script_type}", "script_type": script_type})
                if response.get("decision") == "skip":
                    raise VerificationNeedsReview("已跳过高风险数据准备")
            prepared = data_script_variables(db, {**variables, **setup_vars}, env.project_id)
            passed, log_text, screenshot_path, outputs = runner(env, prepared)
            if not passed:
                raise VerificationBlocked(f"数据准备失败：{redact_sensitive_text(log_text, 800)}")
            output_values = outputs if isinstance(outputs, dict) else {}
            setup_cache[cache_key] = output_values
            variables.update(output_values)
            evidence["data_setup"] = {
                "script_type": script_type,
                "name": definition.get("name") or script_type,
                "reused": False,
                "outputs": output_values,
                "screenshot": screenshot_path or "",
            }
    if _needs_browser(item):
        if sessions is None:
            raise VerificationBlocked("页面执行器未启动")
        browser_observations, browser_evidence = _browser_part(db, sessions, task, item, run, run_item, variables)
        observations.update(browser_observations)
        evidence.update(browser_evidence)
    for spec in config.get("observations") or []:
        if not isinstance(spec, dict):
            continue
        source = str(spec.get("source") or "")
        name = str(spec.get("name") or "").strip()
        if not name or source == "page":
            continue
        if source == "literal":
            observations[name] = _template(spec.get("value"), variables)
        elif source == "variable":
            key = str(spec.get("key") or name)
            if key not in variables:
                raise VerificationBlocked(f"缺少运行变量：{key}")
            observations[name] = variables[key]
        elif source == "api":
            observations[name] = _api_observation(db, task.project_id, spec, {**variables, **observations})
        else:
            raise VerificationBlocked(f"不支持的数据来源：{source or '空'}")
        variables[name] = observations[name]

    if item.automation_level == "manual":
        response = _wait_confirmation(
            db,
            run_item,
            {"type": "manual_check", "message": f"请人工检查：{item.title}", "expected": item.expected, "observations": observations},
            timeout_seconds=180,
        )
        if response.get("decision") == "pass":
            return "passed", "人工确认通过", {"observations": observations, "note": response.get("note") or ""}, evidence
        if response.get("decision") == "fail":
            return "failed", "人工确认业务结果不符合预期", {"observations": observations, "note": response.get("note") or ""}, evidence
        raise VerificationNeedsReview("人工检查已跳过")

    if item.item_type == "amount":
        formula_id = int(config.get("formula_id") or 0)
        formula = db.get(VerificationFormula, formula_id)
        if not formula or formula.project_id != task.project_id or formula.status != "confirmed":
            raise VerificationBlocked("金额公式尚未确认或不属于当前项目")
        input_map = config.get("formula_inputs") if isinstance(config.get("formula_inputs"), dict) else {}
        raw_values = {name: observations.get(source, variables.get(source)) for name, source in input_map.items()}
        if not input_map:
            raw_values = {**variables, **observations}
        calculation = evaluate_formula(formula, raw_values)
        actual_key = str(config.get("actual_key") or "actual_amount")
        if actual_key not in observations and actual_key not in variables:
            raise VerificationNeedsReview(f"缺少实际金额采集值：{actual_key}")
        actual_value = observations.get(actual_key, variables.get(actual_key))
        actual_decimal = _decimal(actual_value, actual_key).quantize(Decimal(1).scaleb(-formula.scale), rounding=ROUNDING_MODES[formula.rounding_mode])
        expected_decimal = Decimal(calculation["expected_amount"])
        calculation["actual_amount"] = str(actual_decimal)
        calculation["difference"] = str(actual_decimal - expected_decimal)
        passed = actual_decimal == expected_decimal
        return ("passed" if passed else "failed", "金额计算一致" if passed else "金额计算不一致", {"observations": observations, "calculation": calculation}, evidence)

    assertions = config.get("assertions") if isinstance(config.get("assertions"), list) else []
    if not assertions:
        response = _wait_confirmation(
            db,
            run_item,
            {"type": "manual_check", "message": f"系统已准备页面和数据，请人工判断：{item.title}", "expected": item.expected, "observations": observations},
            timeout_seconds=180,
        )
        if response.get("decision") == "pass":
            return "passed", "人工确认通过", {"observations": observations, "note": response.get("note") or ""}, evidence
        if response.get("decision") == "fail":
            return "failed", "人工确认业务结果不符合预期", {"observations": observations, "note": response.get("note") or ""}, evidence
        raise VerificationNeedsReview("人工检查已跳过")
    assertion_results = []
    all_passed = True
    for assertion in assertions:
        if not isinstance(assertion, dict):
            continue
        left_key = str(assertion.get("left") or "")
        reference_match = re.fullmatch(r"\$\{\s*([^}]+)\s*\}", left_key)
        if reference_match:
            left_key = reference_match.group(1).strip()
        left = observations.get(left_key, variables.get(left_key))
        right_key = assertion.get("right")
        right = observations.get(str(right_key), variables.get(str(right_key))) if right_key not in (None, "") else _template(assertion.get("right_value"), {**variables, **observations})
        passed, message = _compare(left, assertion.get("operator") or "eq", right, assertion.get("tolerance"))
        assertion_results.append({"left": left_key, "operator": assertion.get("operator") or "eq", "right": right_key or right, "passed": passed, "message": message})
        all_passed = all_passed and passed
    if not assertion_results:
        raise VerificationNeedsReview("断言配置为空")
    return ("passed" if all_passed else "failed", "全部断言通过" if all_passed else "存在断言失败", {"observations": observations, "assertions": assertion_results}, evidence)


def _execute_run_data_setup(
    db: Session,
    task: RequirementVerification,
    setup: Dict[str, Any],
    variables: Dict[str, Any],
    run: VerificationRun | None = None,
) -> tuple[bool, str, Dict[str, Any], Dict[str, Any]]:
    enabled_steps = [step for step in setup.get("steps") or [] if step.get("enabled", True)]
    total_steps = len(enabled_steps)
    step_results: list[Dict[str, Any]] = []
    merged_outputs: Dict[str, Any] = {}

    def progress_snapshot(progress_status: str, current_step: int | None = None) -> Dict[str, Any]:
        snapshot = {
            "status": progress_status,
            "total_steps": total_steps,
            "completed_steps": sum(1 for item in step_results if item.get("status") in {"passed", "failed"}),
            "current_step": current_step,
            "steps": step_results,
            "outputs": mask_sensitive_data(merged_outputs),
        }
        if run is not None:
            run.setup_result_json = json_text(snapshot)
            db.commit()
        return snapshot

    if not enabled_steps:
        return True, "", variables, progress_snapshot("skipped")
    for index, step in enumerate(enabled_steps, start=1):
        script_type = str(step.get("script_type") or "")
        definition = SCRIPT_REGISTRY.get(script_type)
        env = db.get(Env, int(step.get("env_id") or 0))
        started_at = datetime.now()
        result: Dict[str, Any] = {
            "index": index,
            "script_type": script_type,
            "name": str((definition or {}).get("name") or script_type),
            "risk_level": data_script_risk_level(script_type, definition),
            "env_id": int(step.get("env_id") or 0),
            "status": "running",
            "started_at": _time_text(started_at),
        }
        step_results.append(result)
        progress_snapshot("running", index)
        if not isinstance(definition, dict) or not callable(definition.get("func")):
            result.update({"status": "failed", "message": "脚本不存在或未注册", "finish_time": _time_text(datetime.now())})
            return False, f"数据准备第{index}步脚本不存在或未注册：{script_type}", variables, progress_snapshot("failed", index)
        if not env or env.project_id != task.project_id:
            result.update({"status": "failed", "message": "环境不存在或不属于当前项目", "finish_time": _time_text(datetime.now())})
            return False, f"数据准备第{index}步环境不存在或不属于当前项目", variables, progress_snapshot("failed", index)
        step_variables = _template_value(step.get("variables") if isinstance(step.get("variables"), dict) else {}, variables)
        result["variables"] = mask_sensitive_data(step_variables)
        try:
            prepared = data_script_variables(db, {**variables, **step_variables}, env.project_id)
            passed, log_text, evidence_path, outputs = definition["func"](env, prepared)
            output_values = outputs if isinstance(outputs, dict) else {}
            result.update(
                {
                    "status": "passed" if passed else "failed",
                    "message": "数据准备完成" if passed else "数据准备脚本执行失败",
                    "log": redact_sensitive_text(log_text, 3000),
                    "evidence_path": str(evidence_path or ""),
                    "outputs": mask_sensitive_data(output_values),
                    "finish_time": _time_text(datetime.now()),
                }
            )
        except Exception as exc:
            passed = False
            output_values = {}
            result.update(
                {
                    "status": "failed",
                    "message": redact_sensitive_text(exc, 1000),
                    "log": "",
                    "evidence_path": "",
                    "outputs": {},
                    "finish_time": _time_text(datetime.now()),
                }
            )
        if not passed:
            return False, f"数据准备第{index}步失败：{result['name']}，{result['message']}", variables, progress_snapshot("failed", index)
        variables.update(output_values)
        merged_outputs.update(output_values)
        progress_snapshot("passed" if index == total_steps else "running", None if index == total_steps else index + 1)
    return True, "", variables, progress_snapshot("passed")


_RUN_EXECUTION_LOCKS: dict[int, threading.Lock] = {}
_RUN_EXECUTION_LOCKS_GUARD = threading.Lock()


def _run_lock(run_id: int) -> threading.Lock:
    with _RUN_EXECUTION_LOCKS_GUARD:
        return _RUN_EXECUTION_LOCKS.setdefault(run_id, threading.Lock())


def _dataset_rows(db: Session, run_id: int, dataset_id: int | None) -> list[VerificationRunItem]:
    query = db.query(VerificationRunItem).filter(VerificationRunItem.run_id == run_id)
    query = query.filter(VerificationRunItem.dataset_id == dataset_id) if dataset_id else query.filter(VerificationRunItem.dataset_id.is_(None))
    return query.order_by(VerificationRunItem.id.asc()).all()


def _prepare_dataset(
    db: Session,
    run: VerificationRun,
    task: RequirementVerification,
    dataset: VerificationRunDataset,
    base_variables: Dict[str, Any],
) -> tuple[bool, str, Dict[str, Any]]:
    if dataset.status == "passed" and dataset.reuse_allowed:
        return True, "复用本次运行已经准备的数据", {**base_variables, **json_load(dataset.variables_json, {})}
    conditions = json_load(dataset.conditions_json, [])
    setup = json_load(dataset.setup_json, {"steps": []})
    high_risk = data_setup_has_high_risk(setup)
    max_attempts = 1 if high_risk else 3
    condition_variables = conditions_to_variables(conditions)
    last_message = ""
    for attempt in range(int(dataset.attempt or 0) + 1, max_attempts + 1):
        check_run_control(db, run)
        dataset.attempt = attempt
        dataset.status = "running"
        dataset.update_time = datetime.now()
        update_run_phase(
            db,
            run,
            "data_preparing",
            message=f"正在准备{dataset.name or '测试数据'}（第{attempt}次）",
            extra={"dataset_id": dataset.id, "dataset_attempt": attempt},
        )
        passed, message, merged, setup_result = _execute_run_data_setup(
            db,
            task,
            setup,
            {**base_variables, **condition_variables},
            run,
        )
        dataset.result_json = json_text({"setup": setup_result})
        if not passed:
            last_message = message
            dataset.status = "blocked"
            dataset.update_time = datetime.now()
            db.commit()
            return False, message, base_variables
        update_run_phase(db, run, "data_validating", message=f"正在检查{dataset.name or '测试数据'}是否满足业务前置条件", extra={"dataset_id": dataset.id})
        actual_outputs = setup_result.get("outputs") if isinstance(setup_result, dict) else {}
        facts = actual_outputs if isinstance(actual_outputs, dict) and actual_outputs else ({key: merged.get(key) for key in base_variables if key in merged} if not setup.get("steps") else {})
        facts = normalize_business_facts(facts)
        validity = evaluate_conditions(conditions, facts)
        dataset.result_json = json_text({"setup": setup_result, "facts": mask_sensitive_data(facts), "validity": validity})
        dataset.variables_json = json_text({key: value for key, value in merged.items() if key not in SENSITIVE_KEY_PARTS and not any(part in key.lower() for part in SENSITIVE_KEY_PARTS)})
        dataset.update_time = datetime.now()
        if validity["passed"]:
            dataset.status = "passed"
            db.commit()
            return True, "测试数据满足业务前置条件", merged
        missing = validity.get("missing_fields") or []
        last_message = f"数据脚本没有返回可验证的业务事实：{'、'.join(missing)}" if missing else "数据工厂生成的数据不符合验证项前置条件"
        if attempt < max_attempts:
            dataset.status = "retrying"
            db.commit()
            continue
        dataset.status = "invalid"
        dataset.reuse_allowed = 0
        db.commit()
    return False, last_message or "测试数据不符合前置条件", base_variables


def execute_verification_run(run_id: int) -> None:
    lock = _run_lock(run_id)
    if not lock.acquire(blocking=False):
        return
    db = SessionLocal()
    sessions: BrowserSessions | None = None
    try:
        run = db.get(VerificationRun, run_id)
        if not run or run.status in {"passed", "failed", "blocked", "needs_review", "cancelled"}:
            return
        task = db.get(RequirementVerification, run.task_id)
        if not task:
            run.phase = "blocked"
            run.status = "blocked"
            run.summary_json = json_text({"error": "功能分类不存在"})
            run.finish_time = datetime.now()
            db.commit()
            return
        check_run_control(db, run)
        if not run.start_time:
            run.start_time = datetime.now()
        run.finish_time = None
        update_run_phase(db, run, "preflighting", message="正在复核项目、账号、页面和数据条件")
        run_items = db.query(VerificationRunItem).filter(VerificationRunItem.run_id == run.id).order_by(VerificationRunItem.id.asc()).all()
        items = {item.id: item for item in db.query(VerificationItem).filter(VerificationItem.id.in_([row.item_id for row in run_items])).all()}
        datasets = db.query(VerificationRunDataset).filter(VerificationRunDataset.run_id == run.id).order_by(VerificationRunDataset.id.asc()).all()
        if not datasets:
            setup = json_load(run.data_setup_json, {"steps": []})
            create_run_datasets(db, run, [items[row.item_id] for row in run_items if row.item_id in items], setup)
            db.commit()
            datasets = db.query(VerificationRunDataset).filter(VerificationRunDataset.run_id == run.id).order_by(VerificationRunDataset.id.asc()).all()
        base_variables = json_load(run.variables_json, {})
        runnable_dataset_ids: set[int] = set()
        dataset_variables: Dict[int, Dict[str, Any]] = {}
        for dataset in datasets:
            related_rows = _dataset_rows(db, run.id, dataset.id)
            if not any(row.result in {"pending", "running", "waiting_user", "waiting_confirmation"} for row in related_rows):
                continue
            passed, message, variables = _prepare_dataset(db, run, task, dataset, base_variables)
            if passed:
                runnable_dataset_ids.add(dataset.id)
                dataset_variables[dataset.id] = variables
                continue
            now = datetime.now()
            for row in related_rows:
                if row.result in {"passed", "failed", "needs_review"}:
                    continue
                row.result = "blocked"
                row.failure_kind = "data_invalid" if dataset.status == "invalid" else "system_interrupted"
                row.message = message
                row.finish_time = now
            db.commit()

        pending_rows = [row for row in run_items if row.dataset_id in runnable_dataset_ids and row.result in {"pending", "running", "waiting_user", "waiting_confirmation"}]
        needs_browser = any(_needs_browser(items[row.item_id]) for row in pending_rows if row.item_id in items)
        if needs_browser:
            update_run_phase(db, run, "browser_preparing", message="正在恢复测试浏览器和项目登录状态")
            sessions = BrowserSessions(db, task.project_id, bool(run.visible_browser))
            sessions.__enter__()
        setup_cache: Dict[str, Dict[str, Any]] = {}
        total = len(pending_rows)
        for index, row in enumerate(pending_rows, start=1):
            check_run_control(db, run)
            item = items.get(row.item_id)
            if not item:
                row.result = "blocked"
                row.failure_kind = "system_interrupted"
                row.message = "验证项不存在"
                row.finish_time = datetime.now()
                db.commit()
                continue
            dependencies = json_load(row.dependency_json, [])
            if dependencies:
                dependency_rows = db.query(VerificationRunItem).filter(VerificationRunItem.run_id == run.id, VerificationRunItem.item_id.in_(dependencies)).all()
                if any(dependency.result in {"waiting_user", "waiting_confirmation", "pending", "running"} for dependency in dependency_rows):
                    row.result = "pending"
                    row.message = "等待前置验证项处理完成"
                    db.commit()
                    continue
            row.result = "running"
            row.attempt = int(row.attempt or 0) + 1
            row.start_time = row.start_time or datetime.now()
            row.finish_time = None
            update_run_phase(
                db,
                run,
                "running",
                message=f"正在验证：{item.title}",
                current=index,
                total=total,
                extra={"run_item_id": row.id, "item_id": item.id},
            )
            variables = dict(dataset_variables.get(int(row.dataset_id or 0), base_variables))
            try:
                result, message, actual, evidence = _execute_item(db, sessions, task, item, run, row, variables, setup_cache)
                failure_kind = "business_mismatch" if result == "failed" else ""
            except VerificationAwaitingUser:
                continue
            except VerificationCancelled:
                raise
            except VerificationNeedsReview as exc:
                result, message, actual, evidence = "needs_review", str(exc), {}, json_load(row.evidence_json, {})
                failure_kind = classify_failure(exc, "user_deferred")
            except VerificationBlocked as exc:
                result, message, actual, evidence = "blocked", str(exc), {}, json_load(row.evidence_json, {})
                failure_kind = classify_failure(exc)
            except Exception as exc:
                result = "needs_review"
                message = f"技术处理未完成：{redact_sensitive_text(exc, 500)}"
                actual, evidence = {}, json_load(row.evidence_json, {})
                failure_kind = classify_failure(exc)
            row.result = result
            row.failure_kind = failure_kind
            row.message = message
            row.actual_json = json_text(actual)
            row.evidence_json = json_text(evidence)
            row.finish_time = datetime.now()
            item.status = result
            item.result_message = message
            item.actual_json = json_text(actual)
            item.update_time = datetime.now()
            if row.dataset_id:
                dataset = next((value for value in datasets if value.id == row.dataset_id), None)
                if dataset and failure_kind:
                    config = json_load(item.config_json, {})
                    state_changed = any(bool(action.get("risk")) for action in config.get("actions") or [] if isinstance(action, dict))
                    dataset.reuse_allowed = 1 if should_reuse_data(failure_kind, state_changed=state_changed, readonly=not state_changed) else 0
            db.commit()

        summary = recompute_run_summary(db, run)
        decision = summary["decision"]
        if decision == "waiting_user" or any(row.result in {"waiting_user", "waiting_confirmation"} for row in run_items):
            run.phase = "waiting_user"
            run.status = "waiting_user"
            run.finish_time = None
            task.status = "waiting_user"
        elif decision == "running":
            run.phase = "paused"
            run.status = "paused"
            run.pause_reason = "等待依赖链中的人工处理项完成"
            run.finish_time = None
            task.status = "paused"
        else:
            run.phase = decision
            run.status = decision
            run.finish_time = datetime.now()
            task.status = decision
        run.heartbeat_time = datetime.now()
        task.update_time = datetime.now()
        db.commit()
    except VerificationAwaitingUser:
        pass
    except VerificationCancelled:
        pass
    finally:
        if sessions is not None:
            sessions.__exit__(None, None, None)
        db.close()
        lock.release()


def _effective_run_data_setup(
    db: Session,
    task: RequirementVerification,
    requested: Dict[str, Any] | None = None,
) -> tuple[Dict[str, Any], str]:
    category_value = json_load(task.data_setup_json, {"steps": []})
    category_steps = category_value.get("steps") if isinstance(category_value, dict) else []
    raw_value = category_value if category_steps else (requested if requested is not None else {"steps": []})
    try:
        return validate_data_setup_for_project(db, task.project_id, raw_value), ""
    except ValueError as exc:
        return {"steps": []}, str(exc)


def _unresolved_config_paths(value: Any, path: str = "配置") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            paths.extend(_unresolved_config_paths(nested, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value, start=1):
            paths.extend(_unresolved_config_paths(nested, f"{path}[{index}]"))
    elif isinstance(value, str):
        text = value.strip()
        if any(marker.lower() in text.lower() for marker in UNRESOLVED_MARKERS):
            paths.append(path)
    return paths


def _template_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(_template_keys(nested) for nested in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_template_keys(nested) for nested in value)) if value else set()
    if not isinstance(value, str):
        return set()
    return set(re.findall(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", value))


def _safe_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else 0


def _setup_output_keys(setup: Dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for step in setup.get("steps") or []:
        if not step.get("enabled", True):
            continue
        keys.update(DATA_SCRIPT_OUTPUT_KEYS.get(str(step.get("script_type") or ""), []))
        variables = step.get("variables") if isinstance(step.get("variables"), dict) else {}
        keys.update(str(key) for key in variables)
    return keys


def _setup_declared_output_keys(setup: Dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for step in setup.get("steps") or []:
        if isinstance(step, dict) and step.get("enabled", True):
            keys.update(DATA_SCRIPT_OUTPUT_KEYS.get(str(step.get("script_type") or ""), []))
    return keys


def _preflight_issue(code: str, message: str, suggestion: str, severity: str) -> Dict[str, str]:
    return {"code": code, "message": message, "suggestion": suggestion, "severity": severity}


def _runtime_preflight_probe(
    db: Session,
    task: RequirementVerification,
    profile: TestAccountProfile,
    variables: Dict[str, Any],
    visible_browser: bool,
) -> Dict[str, Any]:
    probe_url = ""
    for page_config in target_pages_for(task):
        candidate = str(page_config.get("url") or "").strip()
        if candidate and "{{" not in candidate:
            probe_url = candidate
            break
    probe_url = probe_url or str(task.target_url or "").strip()
    if not probe_url or "{{" in probe_url:
        return {"status": "assisted", "login": "unknown", "page": "unknown", "message": "目标页面依赖造数后的业务编号，登录检查将在执行时继续"}
    from playwright.sync_api import sync_playwright

    playwright = None
    browser = None
    context = None
    try:
        playwright = sync_playwright().start()
        browser = launch_chromium_browser(playwright, headless=not visible_browser)
        options: Dict[str, Any] = {"ignore_https_errors": True}
        stored = decrypt_account_payload(profile.browser_state_encrypted)
        storage_state = stored.get("storage_state") if isinstance(stored, dict) else None
        if isinstance(storage_state, dict) and isinstance(storage_state.get("cookies"), list):
            options["storage_state"] = storage_state
        context = browser.new_context(**options)
        page = context.new_page()
        account_values, meta = account_profile_variables(db, profile.id, task.project_id)
        runtime_variables = {**account_values, **(variables or {})}
        restored = False
        if storage_state:
            try:
                page.goto(probe_url, wait_until="domcontentloaded", timeout=30000)
                password_visible = page.locator('input[type="password"],input[name="password"]').first.is_visible(timeout=800)
                restored = not password_visible and not any(marker in page.url.lower() for marker in ("/login", "#/login", "signin"))
            except Exception:
                restored = False
        if not restored:
            _prepare_authenticated_page(
                page,
                {"login_required": True, "login_config": meta.get("login_config") or {}, "target_url": probe_url},
                runtime_variables,
                45,
            )
            page.goto(probe_url, wait_until="domcontentloaded", timeout=30000)
        readiness = _wait_page_business_ready(page, 35)
        if readiness.get("problem") in {"captcha", "auth"}:
            profile.browser_session_status = "needs_user"
            db.commit()
            return {"status": "assisted", "login": "needs_user", "page": "blocked", "message": str(readiness.get("message") or "登录需要人工处理")}
        if readiness.get("problem") == "permission":
            profile.browser_session_status = "invalid"
            db.commit()
            return {"status": "blocked", "login": "valid", "page": "permission_denied", "message": str(readiness.get("message") or "账号权限不足")}
        if not readiness.get("ready"):
            return {"status": "assisted", "login": "valid", "page": "not_ready", "message": str(readiness.get("message") or "页面业务区没有准备完成")}
        profile.browser_state_encrypted = encrypt_account_payload({"storage_state": context.storage_state()})
        profile.browser_session_status = "valid"
        profile.browser_session_validated_at = datetime.now()
        profile.update_time = datetime.now()
        db.commit()
        return {"status": "passed", "login": "valid", "page": "ready", "message": "登录状态和轻量目标页面检查通过"}
    except Exception as exc:
        message = redact_sensitive_text(exc, 500)
        lowered = message.lower()
        assisted = any(keyword in lowered for keyword in ("验证码", "captcha", "二次认证"))
        profile.browser_session_status = "needs_user" if assisted else "invalid"
        db.commit()
        return {"status": "assisted" if assisted else "blocked", "login": "needs_user" if assisted else "invalid", "page": "not_checked", "message": message}
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass


def verification_preflight(
    db: Session,
    task: RequirementVerification,
    item_ids: list[int] | None = None,
    variables: Dict[str, Any] | None = None,
    data_setup: Dict[str, Any] | None = None,
    runtime_check: bool = False,
    visible_browser: bool = True,
) -> Dict[str, Any]:
    query = db.query(VerificationItem).filter(
        VerificationItem.task_id == task.id,
        VerificationItem.analysis_version == task.analysis_version,
        VerificationItem.confirmed == 1,
        VerificationItem.status != "blocked",
    )
    if item_ids:
        query = query.filter(VerificationItem.id.in_(item_ids))
    items = query.order_by(VerificationItem.id.asc()).all()
    run_setup, setup_error = _effective_run_data_setup(db, task, data_setup)
    enabled_setup = [step for step in run_setup.get("steps") or [] if step.get("enabled", True)]
    category_value = json_load(task.data_setup_json, {"steps": []})
    category_setup_enabled = bool(
        isinstance(category_value, dict)
        and any(step.get("enabled", True) for step in category_value.get("steps") or [] if isinstance(step, dict))
    )
    available_keys = set(str(key) for key in (variables or {})) | _setup_output_keys(run_setup)
    default_profile = default_account_profile_for_target(db, "requirement_verification", task.id, task.project_id)
    if default_profile:
        try:
            account_values, _ = account_profile_variables(db, default_profile.id, task.project_id)
            available_keys.update(str(key) for key in account_values)
        except Exception:
            pass

    global_issues: list[Dict[str, str]] = []
    if setup_error:
        global_issues.append(_preflight_issue("data_setup_invalid", f"数据准备还不能执行：{setup_error}", "请在功能分类的数据准备中重新选择脚本和环境", "blocked"))
    setup_summary = []
    for step in enabled_setup:
        definition = SCRIPT_REGISTRY.get(str(step.get("script_type") or "")) or {}
        env = db.get(Env, int(step.get("env_id") or 0))
        setup_summary.append(
            {
                "script_type": step.get("script_type"),
                "name": str(definition.get("name") or step.get("script_type") or ""),
                "environment": str(env.env_name if env else "未选择环境"),
                "risk_level": data_script_risk_level(str(step.get("script_type") or ""), definition),
                "output_keys": DATA_SCRIPT_OUTPUT_KEYS.get(str(step.get("script_type") or ""), []),
                "accepted_business_conditions": DATA_SCRIPT_ACCEPTED_CONDITIONS.get(str(step.get("script_type") or ""), []),
            }
        )

    preflight_items: list[Dict[str, Any]] = []
    pages = target_pages_for(task)
    page_names = {page["name"] for page in pages}
    for item in items:
        config = json_load(item.config_json, {})
        if not isinstance(config, dict):
            config = {}
        effective_config = dict(config)
        issues = list(global_issues)
        if category_setup_enabled and effective_config.pop("data_setup", None) is not None:
            issues.append(_preflight_issue("legacy_setup_ignored", "已使用功能分类的数据准备，验证项中的旧造数配置会自动忽略", "无需处理", "info"))
        elif isinstance(effective_config.get("data_setup"), dict):
            legacy = effective_config["data_setup"]
            legacy_script = str(legacy.get("script_type") or "").strip()
            legacy_env_id = _safe_positive_int(legacy.get("env_id"))
            if not legacy_script or legacy_script not in SCRIPT_REGISTRY or not callable((SCRIPT_REGISTRY.get(legacy_script) or {}).get("func")):
                issues.append(_preflight_issue("legacy_script_invalid", "旧验证项的数据脚本无法识别", "请改用功能分类统一数据准备", "blocked"))
            if legacy_env_id is None:
                issues.append(_preflight_issue("legacy_env_invalid", "旧验证项的数据环境仍是未完成占位值", "请改用功能分类统一数据准备", "blocked"))
            elif legacy_env_id:
                legacy_env = db.get(Env, legacy_env_id)
                if not legacy_env or legacy_env.project_id != task.project_id:
                    issues.append(_preflight_issue("legacy_env_cross_project", "旧验证项的数据环境不属于当前项目", "请改用当前功能分类的数据准备", "blocked"))

        unresolved_paths = _unresolved_config_paths(effective_config)
        if unresolved_paths:
            issues.append(_preflight_issue("unresolved_placeholder", f"仍有未确认配置：{'、'.join(unresolved_paths[:3])}", "完善业务信息后再执行，系统不会先造数", "blocked"))
        missing_keys = sorted(_template_keys(effective_config) - available_keys)
        if missing_keys:
            issues.append(_preflight_issue("unresolved_variables", f"缺少运行数据：{'、'.join(missing_keys)}", "请确认数据脚本能够输出这些业务编号", "blocked"))
        conditions = item_conditions(item)
        if conditions:
            required_fact_keys = {str(condition.get("field") or "") for condition in conditions if condition.get("field")}
            declared_outputs = _setup_declared_output_keys(run_setup)
            provided_facts = set(str(key) for key in (variables or {}))
            missing_facts = sorted(required_fact_keys - declared_outputs - provided_facts)
            if missing_facts:
                issues.append(
                    _preflight_issue(
                        "data_facts_not_declared",
                        f"当前数据场景不能返回前置条件所需事实：{'、'.join(missing_facts)}",
                        "请选择能返回客户等级、订单金额、币种和状态等实际业务事实的数据场景",
                        "blocked",
                    )
                )

        if _needs_browser(item):
            start_page = str(effective_config.get("start_page") or "").strip()
            if start_page and start_page not in page_names:
                issues.append(_preflight_issue("page_not_found", f"目标页面“{start_page}”不在功能分类页面清单中", "补充页面名称和URL", "blocked"))
            if not target_page_url(task, start_page):
                issues.append(_preflight_issue("page_url_missing", "页面验证缺少目标地址", "在功能分类中补充页面URL", "blocked"))
            explicit_profile = effective_config.get("account_profile_id")
            profile_id = _safe_positive_int(explicit_profile) if explicit_profile not in (None, "") else (default_profile.id if default_profile else 0)
            if explicit_profile not in (None, "") and profile_id is None:
                issues.append(_preflight_issue("account_invalid", "页面账号配置不是有效账号", "从当前项目账号中重新选择", "blocked"))
            elif profile_id:
                profile = db.get(TestAccountProfile, profile_id)
                if not profile or profile.status != "active" or profile.project_id not in (None, task.project_id):
                    issues.append(_preflight_issue("account_cross_project", "页面账号不可用或不属于当前项目", "绑定当前项目的有效测试账号", "blocked"))
            else:
                issues.append(_preflight_issue("account_missing", "当前项目没有绑定可用测试账号，系统不会先造数再等待登录", "请先在项目中绑定默认测试账号", "blocked"))

        if item.item_type == "amount":
            formula_id = _safe_positive_int(effective_config.get("formula_id"))
            formula = db.get(VerificationFormula, formula_id) if formula_id else None
            if not formula or formula.project_id != task.project_id or formula.status != "confirmed":
                issues.append(_preflight_issue("formula_unconfirmed", "金额公式尚未确认，系统不能自动判定金额", "确认中文金额公式后再执行", "blocked"))
        elif not isinstance(effective_config.get("assertions"), list) or not effective_config.get("assertions"):
            issues.append(_preflight_issue("manual_judgement", "该测试点没有可靠的机器判断规则", "运行时由你直接确认通过、失败或跳过", "assisted"))

        if item.automation_level == "manual":
            issues.append(_preflight_issue("manual_item", "该测试点需要人工判断", "系统会打开相关页面并等待你确认", "assisted"))
        execution_mode = "blocked" if any(issue["severity"] == "blocked" for issue in issues) else "assisted" if any(issue["severity"] == "assisted" for issue in issues) else "auto"
        preflight_items.append(
            {
                "item_id": item.id,
                "title": item.title,
                "item_type": item.item_type,
                "execution_mode": execution_mode,
                "issues": issues,
            }
        )

    runtime_probe: Dict[str, Any] = {"status": "skipped", "message": "本次没有页面验证项"}
    browser_rows = [row for row in preflight_items if _needs_browser(next((item for item in items if item.id == row["item_id"]), items[0] if items else None))] if items else []
    if runtime_check and browser_rows and default_profile:
        runtime_probe = _runtime_preflight_probe(db, task, default_profile, variables or {}, visible_browser)
        if runtime_probe.get("status") != "passed":
            severity = "blocked" if runtime_probe.get("status") == "blocked" else "assisted"
            issue = _preflight_issue(
                "runtime_preflight_failed",
                f"真实登录/页面预检未完成：{runtime_probe.get('message') or '未知原因'}",
                "在系统测试浏览器中完成唯一提示动作后继续",
                severity,
            )
            browser_ids = {row["item_id"] for row in browser_rows}
            for row in preflight_items:
                if row["item_id"] in browser_ids:
                    row["issues"].append(issue)
                    row["execution_mode"] = "blocked" if severity == "blocked" else ("assisted" if row["execution_mode"] != "blocked" else "blocked")

    counts = Counter(row["execution_mode"] for row in preflight_items)
    data_groups = group_items_by_conditions(items)
    return {
        "task_id": task.id,
        "status": "blocked" if not preflight_items or not any(row["execution_mode"] != "blocked" for row in preflight_items) else "ready",
        "summary": {"auto": counts.get("auto", 0), "assisted": counts.get("assisted", 0), "blocked": counts.get("blocked", 0)},
        "items": preflight_items,
        "runnable_item_ids": [row["item_id"] for row in preflight_items if row["execution_mode"] != "blocked"],
        "blocked_item_ids": [row["item_id"] for row in preflight_items if row["execution_mode"] == "blocked"],
        "data_setup": {"steps": setup_summary, "high_risk": any(step["risk_level"] == "high" for step in setup_summary)},
        "runtime_probe": runtime_probe,
        "data_groups": data_groups,
    }


def create_and_start_run(
    db: Session,
    task: RequirementVerification,
    item_ids: list[int],
    variables: Dict[str, Any],
    visible_browser: bool,
    data_setup: Dict[str, Any] | None = None,
    risk_confirmed: bool = False,
    mode: str = "quick",
    reuse_data_from_run_id: int | None = None,
    dataset_overrides: Dict[str, Any] | None = None,
    runtime_check: bool = True,
) -> VerificationRun:
    if mode not in {"quick", "teach", "regression"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的验证执行模式")
    active = active_run_for_other_task(db, task.id)
    if active:
        active_task = db.get(RequirementVerification, active.task_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"当前正在处理功能分类“{active_task.name if active_task else active.task_id}”，请先完成、暂停后取消，或等待其结束",
        )
    preflight = verification_preflight(db, task, item_ids, variables, data_setup, runtime_check=runtime_check, visible_browser=visible_browser)
    runnable_ids = preflight["runnable_item_ids"]
    if not runnable_ids:
        messages = [issue["message"] for row in preflight["items"] for issue in row["issues"] if issue["severity"] == "blocked"]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=messages[0] if messages else "没有已确认的可执行验证项")
    selected_ids = [row["item_id"] for row in preflight["items"]]
    items = (
        db.query(VerificationItem)
        .filter(
            VerificationItem.task_id == task.id,
            VerificationItem.analysis_version == task.analysis_version,
            VerificationItem.id.in_(selected_ids),
        )
        .order_by(VerificationItem.id.asc())
        .all()
    )
    run_setup, setup_error = _effective_run_data_setup(db, task, data_setup)
    if setup_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=setup_error)
    if data_setup_has_high_risk(run_setup) and not risk_confirmed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="数据准备包含支付、充值或资金类高风险脚本，请确认风险后再执行")
    run = VerificationRun(
        task_id=task.id,
        status="queued",
        variables_json=json_text(variables or {}),
        data_setup_json=json_text(run_setup),
        setup_result_json="{}",
        summary_json="{}",
        phase="queued",
        progress_json=json_text({"phase": "queued", "message": "等待执行", "mode": mode, "preflight": preflight["summary"]}),
        heartbeat_time=datetime.now(),
        pause_reason=None,
        cancel_requested=0,
        parent_run_id=reuse_data_from_run_id,
        execution_version="v2",
        visible_browser=1 if visible_browser else 0,
        create_time=datetime.now(),
        start_time=None,
        finish_time=None,
    )
    db.add(run)
    db.flush()
    preflight_by_id = {row["item_id"]: row for row in preflight["items"]}
    for item in items:
        item_preflight = preflight_by_id.get(item.id, {})
        blocked = item_preflight.get("execution_mode") == "blocked"
        config = json_load(item.config_json, {})
        db.add(
            VerificationRunItem(
                run_id=run.id,
                item_id=item.id,
                dependency_json=json_text(config.get("dependencies") if isinstance(config.get("dependencies"), list) else []),
                attempt=0,
                failure_kind=classify_failure(" ".join(issue.get("message", "") for issue in item_preflight.get("issues") or [])) if blocked else None,
                resume_json="{}",
                result="blocked" if blocked else "pending",
                message="；".join(issue.get("message", "") for issue in item_preflight.get("issues") or [] if issue.get("severity") == "blocked") if blocked else "",
                actual_json="{}",
                evidence_json=json_text({"preflight": item_preflight}),
                start_time=None,
                finish_time=None,
            )
        )
    db.flush()
    runnable_items = [item for item in items if item.id in runnable_ids]
    datasets = create_run_datasets(db, run, runnable_items, run_setup, dataset_overrides)
    if reuse_data_from_run_id:
        source_run = db.get(VerificationRun, reuse_data_from_run_id)
        if not source_run or source_run.task_id != task.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="复用数据的执行记录不属于当前功能分类")
        source_datasets = {
            row.group_key: row
            for row in db.query(VerificationRunDataset).filter(VerificationRunDataset.run_id == source_run.id).all()
        }
        for dataset in datasets:
            source = source_datasets.get(dataset.group_key)
            if source and source.status == "passed" and source.reuse_allowed:
                dataset.variables_json = source.variables_json
                dataset.result_json = json_text({"reused_from_run_id": source_run.id, "source_result": json_load(source.result_json, {})})
                dataset.status = "passed"
                dataset.attempt = source.attempt
    task.status = "queued"
    task.update_time = datetime.now()
    db.commit()
    db.refresh(run)
    threading.Thread(target=execute_verification_run, args=(run.id,), daemon=True, name=f"verification-run-{run.id}").start()
    return run
