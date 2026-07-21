from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Dict
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..core.utils import decrypt_account_payload, default_account_profile_for_target, encrypt_account_payload
from ..models import (
    RequirementVerification,
    TestAccountProfile,
    VerificationItem,
    VerificationLearningEvent,
    VerificationLearningSession,
    VerificationMemory,
    VerificationRun,
    VerificationRunItem,
)
from . import ui_recording_session
from .verification_runtime_v2 import item_conditions


MEMORY_TYPES = {"page_checkpoint", "page_readiness", "business_flow", "data_recipe", "state_mapping", "amount_rule"}
SENSITIVE_KEYS = {"password", "passwd", "pwd", "token", "cookie", "authorization", "secret", "browser_state", "storage_state"}
TEMPLATE_REMOVED_KEYS = SENSITIVE_KEYS | {"account_profile_id", "env_id", "url", "start_url", "target_url", "formula_id", "expression", "order_sn", "porder_sn", "purchase_no"}


def _json_load(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _time_text(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _redact_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "***手机号***", text)
    text = re.sub(r"(?i)(password|passwd|pwd|token|secret|authorization|cookie)\s*[:=]\s*[^\s,;]+", r"\1=***", text)
    return text[:3000]


def sanitize_learning_payload(value: Any, key: str = "") -> Any:
    if str(key).lower() in SENSITIVE_KEYS:
        return "***"
    if isinstance(value, dict):
        return {str(name): sanitize_learning_payload(nested, str(name)) for name, nested in value.items()}
    if isinstance(value, list):
        return [sanitize_learning_payload(item, key) for item in value[:100]]
    if isinstance(value, str):
        if "password" in str(key).lower() or "密码" in str(key):
            return "{{password}}"
        return _redact_text(value)
    return value


def _task(db: Session, task_id: int) -> RequirementVerification:
    task = db.get(RequirementVerification, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="功能分类不存在")
    return task


def _session(db: Session, session_id: str) -> VerificationLearningSession:
    row = db.get(VerificationLearningSession, session_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="学习会话不存在")
    return row


def serialize_learning_event(row: VerificationLearningEvent) -> Dict[str, Any]:
    return {
        "id": row.id,
        "event_type": row.event_type,
        "action": row.action or "",
        "payload": _json_load(row.payload_json, {}),
        "sensitive": bool(row.sensitive),
        "create_time": _time_text(row.create_time),
    }


def serialize_learning_session(db: Session, row: VerificationLearningSession) -> Dict[str, Any]:
    events = (
        db.query(VerificationLearningEvent)
        .filter(VerificationLearningEvent.session_id == row.id)
        .order_by(VerificationLearningEvent.id.asc())
        .all()
    )
    return {
        "id": row.id,
        "task_id": row.task_id,
        "project_id": row.project_id,
        "account_profile_id": row.account_profile_id,
        "role_name": row.role_name or "",
        "page_name": row.page_name or "",
        "start_url": row.start_url,
        "current_url": row.current_url or row.start_url,
        "status": row.status,
        "create_time": _time_text(row.create_time),
        "update_time": _time_text(row.update_time),
        "finish_time": _time_text(row.finish_time),
        "event_count": len(events),
        "events": [serialize_learning_event(event) for event in events],
        "checkpoints": [serialize_learning_event(event) for event in events if event.event_type == "checkpoint"],
    }


async def create_learning_session(
    db: Session,
    task_id: int,
    role_name: str,
    page_name: str,
    start_url: str,
    account_profile_id: int | None,
    user_id: int | None,
) -> VerificationLearningSession:
    task = _task(db, task_id)
    pages = _json_load(task.target_pages_json, [])
    target_url = str(start_url or "").strip()
    if not target_url:
        for page in pages if isinstance(pages, list) else []:
            if not page_name or str(page.get("name") or "") == page_name:
                target_url = str(page.get("url") or "").strip()
                if target_url:
                    break
    target_url = target_url or str(task.target_url or "").strip()
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="边测边教需要有效的PC页面URL")
    profile = db.get(TestAccountProfile, account_profile_id) if account_profile_id else default_account_profile_for_target(db, "requirement_verification", task.id, task.project_id)
    if not profile or profile.status != "active" or profile.project_id not in {None, task.project_id}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先绑定当前项目的有效测试账号")
    session_id = uuid4().hex
    row = VerificationLearningSession(
        id=session_id,
        task_id=task.id,
        project_id=task.project_id,
        account_profile_id=profile.id,
        role_name=str(role_name or ""),
        page_name=str(page_name or ""),
        start_url=target_url,
        current_url=target_url,
        status="starting",
        browser_state_json="{}",
        create_time=datetime.now(),
        update_time=None,
        finish_time=None,
    )
    db.add(row)
    db.commit()
    stored = decrypt_account_payload(profile.browser_state_encrypted)
    storage_state = stored.get("storage_state") if isinstance(stored, dict) else None
    try:
        await ui_recording_session.start_session(
            task.project_id,
            f"{task.name}-边测边教",
            target_url,
            user_id,
            storage_state if isinstance(storage_state, dict) else None,
            preferred_session_id=session_id,
        )
    except Exception as exc:
        row.status = "blocked"
        row.update_time = datetime.now()
        row.browser_state_json = _json_text({"error": _redact_text(exc)})
        db.commit()
        raise
    row.status = "recording"
    row.update_time = datetime.now()
    db.commit()
    db.refresh(row)
    return row


def append_learning_events(db: Session, session_id: str, events: list[Dict[str, Any]]) -> VerificationLearningSession:
    row = _session(db, session_id)
    if row.status not in {"recording", "verified"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前学习会话不能继续写入事件")
    for event in events[:200]:
        safe = sanitize_learning_payload(event)
        db.add(
            VerificationLearningEvent(
                session_id=row.id,
                event_type=str(safe.get("event_type") or "action"),
                action=str(safe.get("action") or ""),
                payload_json=_json_text(safe),
                sensitive=1 if safe.get("sensitive") else 0,
                create_time=datetime.now(),
            )
        )
        if safe.get("url"):
            row.current_url = str(safe["url"])
    row.update_time = datetime.now()
    db.commit()
    return row


def add_checkpoint(db: Session, session_id: str, payload: Dict[str, Any]) -> VerificationLearningEvent:
    row = _session(db, session_id)
    if row.status not in {"recording", "verified"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前学习会话不能添加验证点")
    field_name = str(payload.get("field_name") or "").strip()
    if not field_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="字段名称不能为空")
    value_type = str(payload.get("value_type") or "text")
    relation = str(payload.get("relation") or "") or ("table_key_value" if value_type in {"money", "amount"} else "nearby_value")
    checkpoint = sanitize_learning_payload(
        {
            **payload,
            "page_name": payload.get("page_name") or row.page_name,
            "role_name": payload.get("role_name") or row.role_name,
            "url_pattern": urlparse(row.current_url or row.start_url).path or "/",
            "relation": relation,
            "extraction": payload.get("extraction") or {
                "target": "adjacent_value" if relation == "table_key_value" else "self_text",
                "remove": ["元", "円", "¥", "￥", ",", " "],
                "decimal": value_type in {"money", "amount", "decimal"},
            },
            "lifecycle": "draft",
        }
    )
    event = VerificationLearningEvent(
        session_id=row.id,
        event_type="checkpoint",
        action="assert",
        payload_json=_json_text(checkpoint),
        sensitive=0,
        create_time=datetime.now(),
    )
    db.add(event)
    row.update_time = datetime.now()
    db.commit()
    db.refresh(event)
    return event


def _checkpoint_item_config(checkpoint: Dict[str, Any]) -> Dict[str, Any]:
    variable_name = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", str(checkpoint.get("field_name") or "actual_value")).strip("_") or "actual_value"
    expected = checkpoint.get("expected")
    if expected in (None, ""):
        expected = checkpoint.get("actual_value")
    verification_type = str(checkpoint.get("verification_type") or "equals")
    operator = {"equals": "eq", "contains": "contains", "range": "between", "amount_equals": "approx"}.get(verification_type, "eq")
    return {
        "start_page": checkpoint.get("page_name") or "",
        "actions": [],
        "observations": [
            {
                "source": "page",
                "name": variable_name,
                "field_name": checkpoint.get("field_name"),
                "goal": f"获取{checkpoint.get('field_name')}的实际值",
                "value_type": checkpoint.get("value_type") or "text",
                "locator_candidates": checkpoint.get("locator_candidates") or [],
                "extraction": checkpoint.get("extraction") or {},
            }
        ],
        "assertions": [{"left": variable_name, "operator": operator, "right_value": expected}],
        "learned_checkpoint": checkpoint,
    }


async def save_learning_session(
    db: Session,
    session_id: str,
    name: str,
    replay_verified: bool,
    promote_to_project: bool,
) -> Dict[str, Any]:
    row = _session(db, session_id)
    task = _task(db, row.task_id)
    checkpoints = (
        db.query(VerificationLearningEvent)
        .filter(VerificationLearningEvent.session_id == row.id, VerificationLearningEvent.event_type == "checkpoint")
        .order_by(VerificationLearningEvent.id.asc())
        .all()
    )
    if not checkpoints:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少添加一个验证点后再保存")
    if promote_to_project and not replay_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="规则必须先成功回放，才能确认写入项目记忆")
    storage_state = await ui_recording_session.get_session_storage_state(session_id)
    profile = db.get(TestAccountProfile, row.account_profile_id) if row.account_profile_id else None
    if profile and storage_state:
        profile.browser_state_encrypted = encrypt_account_payload({"storage_state": storage_state})
        profile.browser_session_status = "valid"
        profile.browser_session_validated_at = datetime.now()
        profile.update_time = datetime.now()
    created_items: list[int] = []
    created_memories: list[int] = []
    for event in checkpoints:
        checkpoint = _json_load(event.payload_json, {})
        checkpoint["lifecycle"] = "confirmed" if promote_to_project else ("verified" if replay_verified else "draft")
        title = f"验证{checkpoint.get('page_name') or '页面'}的{checkpoint.get('field_name')}"
        item = VerificationItem(
            task_id=task.id,
            analysis_version=task.analysis_version,
            item_type="amount" if checkpoint.get("value_type") in {"money", "amount"} and checkpoint.get("verification_type") == "formula" else "page",
            title=title,
            priority="P1",
            role_name=str(checkpoint.get("role_name") or ""),
            precondition="使用边测边教时的已确认页面和数据前置条件",
            action_goal=f"打开页面并采集{checkpoint.get('field_name')}",
            expected=str(checkpoint.get("expected") if checkpoint.get("expected") not in (None, "") else checkpoint.get("actual_value") or ""),
            source_refs=_json_text([f"learning_session:{row.id}", f"checkpoint:{event.id}"]),
            automation_level="supervised",
            risk_level="low",
            config_json=_json_text(_checkpoint_item_config(checkpoint)),
            status="confirmed",
            confirmed=1,
            result_message="",
            actual_json="{}",
            create_time=datetime.now(),
            update_time=None,
        )
        db.add(item)
        db.flush()
        created_items.append(item.id)
        memory = VerificationMemory(
            project_id=task.project_id,
            memory_type="page_checkpoint",
            name=str(name or title),
            content_json=_json_text(checkpoint),
            source_task_id=task.id,
            version=1,
            status="confirmed" if promote_to_project else ("verified" if replay_verified else "draft"),
            create_time=datetime.now(),
            update_time=None,
        )
        db.add(memory)
        db.flush()
        created_memories.append(memory.id)
    row.status = "confirmed" if promote_to_project else ("verified" if replay_verified else "saved")
    row.finish_time = datetime.now()
    row.update_time = datetime.now()
    task.update_time = datetime.now()
    db.commit()
    await ui_recording_session.close_session(session_id)
    return {"session": serialize_learning_session(db, row), "item_ids": created_items, "memory_ids": created_memories}


async def cancel_learning_session(db: Session, session_id: str) -> VerificationLearningSession:
    row = _session(db, session_id)
    await ui_recording_session.close_session(session_id)
    row.status = "cancelled"
    row.finish_time = datetime.now()
    row.update_time = datetime.now()
    db.commit()
    return row


async def begin_checkpoint_capture(db: Session, session_id: str) -> VerificationLearningSession:
    row = _session(db, session_id)
    if row.status != "recording":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前学习会话不在录制中")
    try:
        await ui_recording_session.begin_checkpoint_selection(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="测试浏览器已经关闭，请重新开始边测边教") from exc
    row.update_time = datetime.now()
    db.commit()
    return row


def _keywords(value: str) -> set[str]:
    return set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", str(value or "").lower()))


def similar_tasks(db: Session, task_id: int, limit: int = 8) -> list[Dict[str, Any]]:
    task = _task(db, task_id)
    basis = f"{task.name} {task.requirement_text or ''} {task.context or ''}"
    basis_keywords = _keywords(basis)
    candidates = db.query(RequirementVerification).filter(RequirementVerification.project_id == task.project_id, RequirementVerification.id != task.id).all()
    result: list[Dict[str, Any]] = []
    for candidate in candidates:
        text = f"{candidate.name} {candidate.requirement_text or ''} {candidate.context or ''}"
        keywords = _keywords(text)
        overlap = len(basis_keywords & keywords) / max(len(basis_keywords | keywords), 1)
        name_score = SequenceMatcher(None, task.name.lower(), candidate.name.lower()).ratio()
        score = round(max(name_score, overlap * 1.4), 4)
        if score < 0.18:
            continue
        confirmed_items = db.query(VerificationItem).filter(VerificationItem.task_id == candidate.id, VerificationItem.confirmed == 1).count()
        confirmed_memories = db.query(VerificationMemory).filter(VerificationMemory.source_task_id == candidate.id, VerificationMemory.status == "confirmed").count()
        result.append(
            {
                "task_id": candidate.id,
                "name": candidate.name,
                "score": score,
                "confirmed_items": confirmed_items,
                "confirmed_memories": confirmed_memories,
                "updated_at": _time_text(candidate.update_time or candidate.create_time),
            }
        )
    return sorted(result, key=lambda row: (row["score"], row["updated_at"]), reverse=True)[:limit]


def inherit_from_task(
    db: Session,
    task_id: int,
    source_task_id: int,
    item_ids: list[int],
    memory_ids: list[int],
) -> Dict[str, Any]:
    task = _task(db, task_id)
    source = _task(db, source_task_id)
    if source.project_id != task.project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="功能继承只能在同一个项目内进行")
    item_query = db.query(VerificationItem).filter(VerificationItem.task_id == source.id, VerificationItem.confirmed == 1)
    if item_ids:
        item_query = item_query.filter(VerificationItem.id.in_(item_ids))
    copied_item_ids: list[int] = []
    for source_item in item_query.all():
        copied = VerificationItem(
            task_id=task.id,
            analysis_version=task.analysis_version,
            item_type=source_item.item_type,
            title=source_item.title,
            priority=source_item.priority,
            role_name=source_item.role_name,
            precondition=source_item.precondition,
            action_goal=source_item.action_goal,
            expected=source_item.expected,
            source_refs=_json_text([*(_json_load(source_item.source_refs, []) or []), f"inherited_task:{source.id}", f"inherited_item:{source_item.id}"]),
            automation_level=source_item.automation_level,
            risk_level=source_item.risk_level,
            config_json=source_item.config_json,
            status="confirmed",
            confirmed=1,
            result_message="",
            actual_json="{}",
            create_time=datetime.now(),
            update_time=None,
        )
        db.add(copied)
        db.flush()
        copied_item_ids.append(copied.id)
    memory_query = db.query(VerificationMemory).filter(VerificationMemory.project_id == task.project_id, VerificationMemory.source_task_id == source.id, VerificationMemory.status == "confirmed")
    if memory_ids:
        memory_query = memory_query.filter(VerificationMemory.id.in_(memory_ids))
    linked_memory_ids = [row.id for row in memory_query.all()]
    task.update_time = datetime.now()
    db.commit()
    return {"source_task_id": source.id, "copied_item_ids": copied_item_ids, "linked_memory_ids": linked_memory_ids}


def _sanitize_template(value: Any, key: str = "") -> Any:
    if str(key).lower() in TEMPLATE_REMOVED_KEYS:
        return None
    if isinstance(value, dict):
        return {name: sanitized for name, nested in value.items() if (sanitized := _sanitize_template(nested, str(name))) is not None}
    if isinstance(value, list):
        return [sanitized for nested in value if (sanitized := _sanitize_template(nested, key)) is not None]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def copy_public_template(db: Session, source_project_id: int, target_project_id: int, memory_ids: list[int]) -> Dict[str, Any]:
    if source_project_id == target_project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标项目应与来源项目不同")
    source_rows = db.query(VerificationMemory).filter(VerificationMemory.project_id == source_project_id, VerificationMemory.status == "confirmed")
    if memory_ids:
        source_rows = source_rows.filter(VerificationMemory.id.in_(memory_ids))
    copied: list[int] = []
    for source in source_rows.all():
        if source.memory_type == "amount_rule":
            continue
        content = _sanitize_template(_json_load(source.content_json, {}))
        row = VerificationMemory(
            project_id=target_project_id,
            memory_type=source.memory_type if source.memory_type in MEMORY_TYPES else "business_flow",
            name=f"公共模板-{source.name}",
            content_json=_json_text({"template": content, "requires_mapping": ["target_page", "account", "environment", "state_mapping", "amount_rule"]}),
            source_task_id=None,
            version=1,
            status="draft",
            create_time=datetime.now(),
            update_time=None,
        )
        db.add(row)
        db.flush()
        copied.append(row.id)
    db.commit()
    return {"copied_memory_ids": copied, "requires_mapping": True}


def defect_draft(db: Session, run_item_id: int) -> Dict[str, Any]:
    row = db.get(VerificationRunItem, run_item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行项不存在")
    if row.failure_kind != "business_mismatch" or row.result != "failed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只有具备真实业务不一致证据的失败才能生成缺陷草稿")
    run = db.get(VerificationRun, row.run_id)
    item = db.get(VerificationItem, row.item_id)
    task = db.get(RequirementVerification, run.task_id) if run else None
    actual = _json_load(row.actual_json, {})
    evidence = _json_load(row.evidence_json, {})
    variables = _json_load(run.variables_json, {}) if run else {}
    business_keys = {key: value for key, value in variables.items() if key in {"order_sn", "porder_sn", "purchase_no", "goods_id", "customer_id"}}
    return {
        "title": f"【{task.name if task else '功能验证'}】{item.title if item else '业务结果不符合预期'}",
        "project_id": task.project_id if task else None,
        "task_id": task.id if task else None,
        "run_id": run.id if run else None,
        "run_item_id": row.id,
        "precondition": item.precondition if item else "",
        "business_keys": business_keys,
        "steps": evidence.get("actions") or [],
        "expected": item.expected if item else "",
        "actual": actual,
        "calculation": actual.get("calculation") if isinstance(actual, dict) else None,
        "screenshots": evidence.get("screenshots") or [],
        "message": row.message or "",
        "copy_text": f"项目/功能分类：{task.name if task else ''}\n验证点：{item.title if item else ''}\n前置条件：{item.precondition if item else ''}\n预期：{item.expected if item else ''}\n实际：{row.message or actual}",
    }


def efficiency_stats(db: Session, project_id: int | None = None, task_id: int | None = None) -> Dict[str, Any]:
    query = db.query(VerificationRun)
    if task_id:
        query = query.filter(VerificationRun.task_id == task_id)
    elif project_id:
        task_ids = [row[0] for row in db.query(RequirementVerification.id).filter(RequirementVerification.project_id == project_id).all()]
        query = query.filter(VerificationRun.task_id.in_(task_ids))
    runs = query.all()
    run_ids = [run.id for run in runs]
    items = db.query(VerificationRunItem).filter(VerificationRunItem.run_id.in_(run_ids)).all() if run_ids else []
    total_seconds = sum(max(((run.finish_time or datetime.now()) - (run.start_time or run.create_time)).total_seconds(), 0) for run in runs)
    return {
        "runs": len(runs),
        "total_seconds": round(total_seconds, 2),
        "automatic_completed": sum(1 for row in items if row.result == "passed"),
        "waiting_user": sum(1 for row in items if row.result in {"waiting_user", "waiting_confirmation"}),
        "business_failures": sum(1 for row in items if row.failure_kind == "business_mismatch"),
        "technical_blocks": sum(1 for row in items if row.failure_kind and row.failure_kind != "business_mismatch"),
        "data_invalid": sum(1 for row in items if row.failure_kind == "data_invalid"),
        "reused_rules": sum(1 for row in db.query(VerificationMemory).filter(VerificationMemory.status == "confirmed").all() if project_id is None or row.project_id == project_id),
        "result_counts": {key: sum(1 for row in items if row.result == key) for key in {"passed", "failed", "blocked", "needs_review", "waiting_user", "skipped"}},
    }


def requirement_diff(db: Session, task_id: int, source_task_id: int | None = None) -> Dict[str, Any]:
    task = _task(db, task_id)
    if source_task_id:
        source = _task(db, source_task_id)
        if source.project_id != task.project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="需求差异只能比较同项目功能分类")
    else:
        candidates = similar_tasks(db, task.id, 1)
        source = _task(db, candidates[0]["task_id"]) if candidates else None
    current_items = db.query(VerificationItem).filter(VerificationItem.task_id == task.id).all()
    source_items = db.query(VerificationItem).filter(VerificationItem.task_id == source.id, VerificationItem.confirmed == 1).all() if source else []
    normalize = lambda value: re.sub(r"[\s\W_]+", "", str(value or "").lower())
    source_by_title = {normalize(item.title): item for item in source_items}
    current_by_title = {normalize(item.title): item for item in current_items}
    added = [item.id for key, item in current_by_title.items() if key not in source_by_title]
    removed = [item.id for key, item in source_by_title.items() if key not in current_by_title]
    modified: list[int] = []
    unchanged: list[int] = []
    for key in current_by_title.keys() & source_by_title.keys():
        current, previous = current_by_title[key], source_by_title[key]
        current_signature = (current.expected or "", current.precondition or "", current.role_name or "", current.item_type, current.config_json or "")
        previous_signature = (previous.expected or "", previous.precondition or "", previous.role_name or "", previous.item_type, previous.config_json or "")
        (modified if current_signature != previous_signature else unchanged).append(current.id)
    p0_p1 = [item.id for item in source_items if item.priority in {"P0", "P1"}]
    return {
        "source_task": {"id": source.id, "name": source.name} if source else None,
        "added_item_ids": added,
        "modified_item_ids": modified,
        "removed_source_item_ids": removed,
        "unchanged_item_ids": unchanged,
        "recommended_item_ids": sorted(set(added + modified + p0_p1)),
        "summary": {"added": len(added), "modified": len(modified), "removed": len(removed), "unchanged": len(unchanged)},
    }


def boundary_combinations(db: Session, task_id: int) -> Dict[str, Any]:
    task = _task(db, task_id)
    items = db.query(VerificationItem).filter(VerificationItem.task_id == task.id, VerificationItem.confirmed == 1).all()
    numeric_boundaries: list[Dict[str, Any]] = []
    categorical: Dict[str, list[Any]] = {}
    for item in items:
        for condition in item_conditions(item):
            value = condition.get("value")
            operator = condition.get("operator")
            if operator in {"lt", "lte", "gt", "gte", "eq"}:
                try:
                    numeric = Decimal(str(value))
                except Exception:
                    continue
                numeric_boundaries.append({**condition, "value": numeric, "item_id": item.id})
            elif operator == "in" and isinstance(value, list):
                categorical.setdefault(str(condition["field"]), [])
                for nested in value:
                    if nested not in categorical[str(condition["field"])]:
                        categorical[str(condition["field"])].append(nested)
    scenarios: list[Dict[str, Any]] = []
    categories = [(field, values) for field, values in categorical.items() if values]
    for boundary_index, boundary in enumerate(numeric_boundaries):
        value: Decimal = boundary["value"]
        unit = Decimal("1") if value == value.to_integral_value() else Decimal("0.01")
        points = [("小于边界", value - unit), ("等于边界", value), ("大于边界", value + unit)]
        for point_index, (label, point) in enumerate(points):
            conditions = {str(boundary["field"]): str(point)}
            if categories:
                field, values = categories[(boundary_index + point_index) % len(categories)]
                conditions[field] = values[(boundary_index + point_index) % len(values)]
            scenarios.append(
                {
                    "name": f"{boundary['field']}{label}{point}",
                    "conditions": conditions,
                    "source_item_ids": [boundary["item_id"]],
                    "risk_reason": f"覆盖{boundary['field']}的{label}",
                }
            )
    for field, values in categories:
        outside = next((value for value in ("V5", "其他", "UNKNOWN") if value not in values), "条件外值")
        scenarios.append({"name": f"{field}条件外例外", "conditions": {field: outside}, "source_item_ids": [], "risk_reason": "覆盖条件外例外值"})
    unique: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for scenario in scenarios:
        key = _json_text(scenario["conditions"])
        if key not in seen:
            seen.add(key)
            unique.append(scenario)
    return {"task_id": task.id, "items": unique[:30], "strategy": "风险优先最小组合，不生成笛卡尔积"}


def cross_project_regression_suggestions(db: Session, task_id: int) -> list[Dict[str, Any]]:
    task = _task(db, task_id)
    source_memories = db.query(VerificationMemory).filter(VerificationMemory.project_id == task.project_id, VerificationMemory.status == "confirmed").all()
    source_tokens = _keywords(" ".join([task.name, task.requirement_text or "", *[memory.name for memory in source_memories]]))
    projects = {}
    for memory in db.query(VerificationMemory).filter(VerificationMemory.project_id != task.project_id, VerificationMemory.status == "confirmed").all():
        project = projects.setdefault(memory.project_id, {"project_id": memory.project_id, "matched_rules": [], "tokens": set()})
        project["matched_rules"].append({"id": memory.id, "name": memory.name, "type": memory.memory_type})
        project["tokens"].update(_keywords(memory.name))
    suggestions = []
    for project in projects.values():
        overlap = len(source_tokens & project["tokens"]) / max(len(source_tokens | project["tokens"]), 1)
        if overlap <= 0:
            continue
        project["score"] = round(overlap, 4)
        project["requires_mapping"] = ["目标页面", "项目账号", "数据脚本与环境", "状态映射", "金额公式"]
        project.pop("tokens", None)
        suggestions.append(project)
    return sorted(suggestions, key=lambda row: row["score"], reverse=True)
