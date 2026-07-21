from __future__ import annotations

import hashlib
import json
import threading
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, Iterable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import (
    RequirementVerification,
    VerificationItem,
    VerificationRun,
    VerificationRunDataset,
    VerificationRunItem,
)


ACTIVE_RUN_STATUSES = {
    "queued",
    "preflighting",
    "data_preparing",
    "data_validating",
    "browser_preparing",
    "running",
    "waiting_user",
    "paused",
    "cancelling",
}
FINAL_RUN_STATUSES = {"passed", "failed", "blocked", "needs_review", "cancelled"}
RUN_PHASES = ACTIVE_RUN_STATUSES | FINAL_RUN_STATUSES
FAILURE_KINDS = {
    "business_mismatch",
    "auth_error",
    "data_invalid",
    "page_not_ready",
    "locator_error",
    "ai_error",
    "user_deferred",
    "system_interrupted",
    "cancelled",
}
TECHNICAL_REUSE_KINDS = {"auth_error", "page_not_ready", "locator_error", "ai_error", "system_interrupted"}
MANUAL_DECISIONS = {
    "continue",
    "user_completed",
    "select",
    "provide_value",
    "retry",
    "skip",
    "pass",
    "fail",
    "defer",
    "wait",
    "reopen",
}


class VerificationAwaitingUser(RuntimeError):
    """执行链已安全持久化，可以释放线程和浏览器。"""


class VerificationCancelled(RuntimeError):
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


def time_text(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _decimal(value: Any) -> Decimal | None:
    try:
        text = str(value).strip().replace(",", "")
        return Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _condition_operator(value: Any) -> str:
    aliases = {
        "=": "eq",
        "==": "eq",
        "等于": "eq",
        "!=": "ne",
        "不等于": "ne",
        "<": "lt",
        "小于": "lt",
        "<=": "lte",
        "≤": "lte",
        "小于等于": "lte",
        ">": "gt",
        "大于": "gt",
        ">=": "gte",
        "≥": "gte",
        "大于等于": "gte",
        "属于": "in",
        "包含": "contains",
        "范围": "between",
    }
    text = str(value or "eq").strip().lower()
    return aliases.get(text, text if text in {"eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in", "contains", "between", "exists"} else "eq")


def normalize_conditions(value: Any) -> list[Dict[str, Any]]:
    if isinstance(value, dict) and isinstance(value.get("conditions"), list):
        value = value["conditions"]
    elif isinstance(value, dict):
        rows = []
        for field, definition in value.items():
            if isinstance(definition, dict):
                rows.append({"field": field, **definition})
            else:
                rows.append({"field": field, "operator": "in" if isinstance(definition, list) else "eq", "value": definition})
        value = rows
    if not isinstance(value, list):
        return []
    result: list[Dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        field = str(row.get("field") or row.get("name") or "").strip()
        if not field:
            continue
        normalized = {
            "field": field,
            "operator": _condition_operator(row.get("operator")),
            "value": row.get("value"),
        }
        unit = str(row.get("unit") or "").strip()
        if unit:
            normalized["unit"] = unit
        result.append(normalized)
    return result[:50]


def item_conditions(item: VerificationItem) -> list[Dict[str, Any]]:
    config = json_load(item.config_json, {})
    if not isinstance(config, dict):
        return []
    return normalize_conditions(config.get("conditions") or config.get("preconditions") or [])


def _condition_key(condition: Dict[str, Any]) -> str:
    return json.dumps(condition, ensure_ascii=False, sort_keys=True, default=str)


def _field_constraints(conditions: list[Dict[str, Any]]) -> Dict[str, list[Dict[str, Any]]]:
    result: Dict[str, list[Dict[str, Any]]] = {}
    for condition in conditions:
        result.setdefault(str(condition["field"]), []).append(condition)
    return result


def conditions_compatible(left: list[Dict[str, Any]], right: list[Dict[str, Any]]) -> bool:
    for rows in _field_constraints([*left, *right]).values():
        equal_values = {str(row.get("value")) for row in rows if row.get("operator") == "eq"}
        if len(equal_values) > 1:
            return False
        allowed_sets = [set(str(item) for item in row.get("value") or []) for row in rows if row.get("operator") == "in" and isinstance(row.get("value"), list)]
        if allowed_sets and not set.intersection(*allowed_sets):
            return False
        if equal_values and allowed_sets and not all(next(iter(equal_values)) in allowed for allowed in allowed_sets):
            return False
        lower: Decimal | None = None
        lower_exclusive = False
        upper: Decimal | None = None
        upper_exclusive = False
        for row in rows:
            number = _decimal(row.get("value"))
            operator = row.get("operator")
            if number is None:
                continue
            if operator in {"gt", "gte"} and (lower is None or number > lower or (number == lower and operator == "gt")):
                lower, lower_exclusive = number, operator == "gt"
            elif operator in {"lt", "lte"} and (upper is None or number < upper or (number == upper and operator == "lt")):
                upper, upper_exclusive = number, operator == "lt"
        if lower is not None and upper is not None:
            if lower > upper or (lower == upper and (lower_exclusive or upper_exclusive)):
                return False
    return True


def merge_conditions(left: list[Dict[str, Any]], right: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    merged: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for condition in [*left, *right]:
        key = _condition_key(condition)
        if key not in seen:
            seen.add(key)
            merged.append(condition)
    return merged


def group_items_by_conditions(items: Iterable[VerificationItem]) -> list[Dict[str, Any]]:
    groups: list[Dict[str, Any]] = []
    for item in items:
        conditions = item_conditions(item)
        selected = None
        for group in groups:
            if conditions_compatible(group["conditions"], conditions):
                selected = group
                break
        if selected is None:
            selected = {"conditions": [], "item_ids": []}
            groups.append(selected)
        selected["conditions"] = merge_conditions(selected["conditions"], conditions)
        selected["item_ids"].append(item.id)
    for index, group in enumerate(groups, start=1):
        canonical = json.dumps(group["conditions"], ensure_ascii=False, sort_keys=True, default=str)
        group["group_key"] = f"dataset-{hashlib.sha1(canonical.encode('utf-8')).hexdigest()[:12]}"
        group["name"] = "通用数据" if not group["conditions"] else f"业务条件组{index}"
    return groups


def conditions_to_variables(conditions: list[Dict[str, Any]]) -> Dict[str, Any]:
    variables: Dict[str, Any] = {"business_conditions": conditions}
    for condition in conditions:
        field = str(condition["field"])
        operator = str(condition["operator"])
        value = condition.get("value")
        if operator == "eq" or (operator == "in" and isinstance(value, list) and len(value) == 1):
            variables[field] = value[0] if isinstance(value, list) else value
        elif operator in {"lt", "lte"}:
            variables[f"{field}_max"] = value
        elif operator in {"gt", "gte"}:
            variables[f"{field}_min"] = value
        elif operator == "between" and isinstance(value, list) and len(value) >= 2:
            variables[f"{field}_min"], variables[f"{field}_max"] = value[0], value[1]
    return variables


def evaluate_conditions(conditions: list[Dict[str, Any]], facts: Dict[str, Any]) -> Dict[str, Any]:
    facts = normalize_business_facts(facts)
    checks: list[Dict[str, Any]] = []
    for condition in conditions:
        field = str(condition["field"])
        operator = str(condition["operator"])
        expected = condition.get("value")
        present = field in facts and facts.get(field) not in (None, "")
        actual = facts.get(field)
        passed = False
        if operator == "exists":
            passed = present if expected is not False else not present
        elif present:
            actual_number, expected_number = _decimal(actual), _decimal(expected)
            if operator == "eq":
                passed = actual_number == expected_number if actual_number is not None and expected_number is not None else str(actual) == str(expected)
            elif operator == "ne":
                passed = actual_number != expected_number if actual_number is not None and expected_number is not None else str(actual) != str(expected)
            elif operator in {"lt", "lte", "gt", "gte"} and actual_number is not None and expected_number is not None:
                passed = {"lt": actual_number < expected_number, "lte": actual_number <= expected_number, "gt": actual_number > expected_number, "gte": actual_number >= expected_number}[operator]
            elif operator in {"in", "not_in"} and isinstance(expected, list):
                included = str(actual) in {str(item) for item in expected}
                passed = included if operator == "in" else not included
            elif operator == "contains":
                passed = str(expected) in str(actual)
            elif operator == "between" and isinstance(expected, list) and len(expected) >= 2 and actual_number is not None:
                low, high = _decimal(expected[0]), _decimal(expected[1])
                passed = low is not None and high is not None and low <= actual_number <= high
        checks.append({"field": field, "operator": operator, "expected": expected, "actual": actual, "present": present, "passed": passed})
    return {
        "passed": all(row["passed"] for row in checks),
        "checks": checks,
        "missing_fields": [row["field"] for row in checks if not row["present"] and row["operator"] != "exists"],
    }


def normalize_business_facts(value: Dict[str, Any]) -> Dict[str, Any]:
    facts = dict(value or {})
    aliases = {
        "quantity": ("quantity", "item_quantity", "num", "total_num"),
        "item_count": ("item_count", "selected_count", "goods_count", "detail_count"),
        "order_amount": ("order_amount", "total_amount", "pay_amount", "amount"),
        "currency": ("currency", "currency_code", "money_type"),
        "order_status": ("order_status", "status", "current_node", "node_label"),
        "customer_level": ("customer_level", "level", "member_level", "client_level"),
    }
    for canonical, keys in aliases.items():
        if facts.get(canonical) not in (None, ""):
            continue
        for key in keys:
            if facts.get(key) not in (None, ""):
                facts[canonical] = facts[key]
                break
    return facts


def create_run_datasets(
    db: Session,
    run: VerificationRun,
    items: list[VerificationItem],
    setup: Dict[str, Any],
    overrides: Dict[str, Any] | None = None,
) -> list[VerificationRunDataset]:
    groups = group_items_by_conditions(items)
    item_rows = {row.item_id: row for row in db.query(VerificationRunItem).filter(VerificationRunItem.run_id == run.id).all()}
    datasets: list[VerificationRunDataset] = []
    for group in groups:
        override = (overrides or {}).get(group["group_key"], {})
        dataset_setup = override.get("data_setup") if isinstance(override, dict) else None
        dataset = VerificationRunDataset(
            run_id=run.id,
            group_key=group["group_key"],
            name=str((override or {}).get("name") or group["name"]),
            conditions_json=json_text(group["conditions"]),
            setup_json=json_text(dataset_setup if isinstance(dataset_setup, dict) else setup),
            variables_json="{}",
            result_json="{}",
            status="pending",
            reuse_allowed=1,
            attempt=0,
            create_time=datetime.now(),
            update_time=None,
        )
        db.add(dataset)
        db.flush()
        datasets.append(dataset)
        for item_id in group["item_ids"]:
            row = item_rows.get(item_id)
            if row:
                row.dataset_id = dataset.id
                row.flow_group = dataset.group_key
    return datasets


def serialize_dataset(row: VerificationRunDataset) -> Dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "group_key": row.group_key,
        "name": row.name or "",
        "conditions": json_load(row.conditions_json, []),
        "data_setup": json_load(row.setup_json, {"steps": []}),
        "variables": json_load(row.variables_json, {}),
        "result": json_load(row.result_json, {}),
        "status": row.status,
        "reuse_allowed": bool(row.reuse_allowed),
        "attempt": row.attempt or 0,
        "create_time": time_text(row.create_time),
        "update_time": time_text(row.update_time),
    }


def update_run_phase(
    db: Session,
    run: VerificationRun,
    phase: str,
    *,
    message: str = "",
    current: int | None = None,
    total: int | None = None,
    extra: Dict[str, Any] | None = None,
    commit: bool = True,
) -> None:
    if phase not in RUN_PHASES:
        raise ValueError(f"不支持的运行阶段：{phase}")
    progress = json_load(run.progress_json, {})
    progress.update({"phase": phase, "message": message, "updated_at": time_text(datetime.now())})
    if current is not None:
        progress["current"] = current
    if total is not None:
        progress["total"] = total
    if extra:
        progress.update(extra)
    run.phase = phase
    if phase == "queued":
        run.status = "queued"
    elif phase in {"preflighting", "data_preparing", "data_validating", "browser_preparing", "running"}:
        run.status = "running"
    run.progress_json = json_text(progress)
    run.heartbeat_time = datetime.now()
    if commit:
        db.commit()


def check_run_control(db: Session, run: VerificationRun) -> None:
    db.refresh(run)
    if run.cancel_requested or run.phase in {"cancelling", "cancelled"}:
        _finish_cancelled_run(db, run)
        raise VerificationCancelled("用户已取消执行")
    if run.phase == "paused":
        raise VerificationAwaitingUser(run.pause_reason or "执行已暂停")


def classify_failure(error: Any, fallback: str = "system_interrupted") -> str:
    text = str(error or "").lower()
    rules = (
        ("auth_error", ("登录", "账号", "权限", "验证码", "login", "captcha", "unauthorized", "forbidden")),
        ("data_invalid", ("前置条件", "数据不符合", "数据异常", "异常警告", "币种", "客户等级", "data invalid")),
        ("page_not_ready", ("页面未准备", "加载超时", "加载遮罩", "站点错误", "page not ready", "timeout")),
        ("locator_error", ("无法定位", "无法可靠定位", "字段值不存在", "候选元素", "locator", "selector")),
        ("ai_error", ("deepseek", "模型", "ai", "置信度")),
        ("user_deferred", ("暂不确定", "已跳过", "人工检查", "defer")),
        ("cancelled", ("取消执行", "cancelled")),
    )
    for kind, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return kind
    return fallback if fallback in FAILURE_KINDS else "system_interrupted"


def should_reuse_data(failure_kind: str, *, state_changed: bool = False, readonly: bool = False) -> bool:
    if readonly or failure_kind in TECHNICAL_REUSE_KINDS:
        return True
    if failure_kind == "data_invalid":
        return False
    return not state_changed and failure_kind != "business_mismatch"


def consume_manual_decision(run_item: VerificationRunItem, request_type: str) -> Dict[str, Any] | None:
    state = json_load(run_item.resume_json, {})
    pending = state.get("pending") if isinstance(state, dict) else None
    decision = state.get("decision") if isinstance(state, dict) else None
    if not isinstance(pending, dict) or pending.get("type") != request_type or not isinstance(decision, dict):
        return None
    state["consumed"] = decision
    state["decision"] = None
    state["consumed_at"] = time_text(datetime.now())
    run_item.resume_json = json_text(state)
    return decision


def request_manual_action(
    db: Session,
    run: VerificationRun,
    run_item: VerificationRunItem,
    detail: Dict[str, Any],
) -> None:
    request_type = str(detail.get("type") or "manual_check")
    existing = consume_manual_decision(run_item, request_type)
    if existing is not None:
        return
    state = json_load(run_item.resume_json, {})
    state.update({"pending": detail, "decision": None, "requested_at": time_text(datetime.now())})
    run_item.resume_json = json_text(state)
    run_item.result = "waiting_user"
    run_item.message = str(detail.get("message") or "等待人工处理")
    evidence = json_load(run_item.evidence_json, {})
    evidence.update(detail)
    evidence["manual_takeover"] = detail
    run_item.evidence_json = json_text(evidence)
    run.phase = "waiting_user"
    run.status = "waiting_user"
    run.pause_reason = run_item.message
    update_run_phase(db, run, "waiting_user", message=run_item.message, extra={"run_item_id": run_item.id})
    raise VerificationAwaitingUser(run_item.message)


def resolve_manual_action(
    db: Session,
    run_item: VerificationRunItem,
    decision: str,
    candidate_index: int | None = None,
    note: str = "",
    observed_value: Any = None,
) -> VerificationRun:
    if decision not in MANUAL_DECISIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的人工处理决定")
    if run_item.result not in {"waiting_user", "waiting_confirmation"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前执行项不在等待人工处理状态")
    run = db.get(VerificationRun, run_item.run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")
    state = json_load(run_item.resume_json, {})
    state["decision"] = {
        "decision": decision,
        "candidate_index": candidate_index,
        "note": note,
        "observed_value": observed_value,
        "decided_at": time_text(datetime.now()),
    }
    run_item.resume_json = json_text(state)
    run_item.result = "pending"
    run_item.message = "已收到人工处理结果，等待继续"
    run.phase = "queued"
    run.status = "queued"
    run.pause_reason = None
    run.finish_time = None
    run.heartbeat_time = datetime.now()
    db.commit()
    return run


def recompute_run_summary(db: Session, run: VerificationRun) -> Dict[str, Any]:
    rows = db.query(VerificationRunItem).filter(VerificationRunItem.run_id == run.id).all()
    counts = Counter(row.result for row in rows)
    waiting = counts.get("waiting_user", 0) + counts.get("waiting_confirmation", 0)
    if waiting:
        decision = "waiting_user"
    elif counts.get("failed"):
        decision = "failed"
    elif counts.get("blocked"):
        decision = "blocked"
    elif counts.get("needs_review") or counts.get("skipped"):
        decision = "needs_review"
    elif rows and counts.get("passed") == len(rows):
        decision = "passed"
    else:
        decision = "running"
    summary = {
        "total": len(rows),
        "counts": dict(counts),
        "decision": decision,
        "business_failures": sum(1 for row in rows if row.failure_kind == "business_mismatch"),
        "technical_blocks": sum(1 for row in rows if row.failure_kind and row.failure_kind != "business_mismatch"),
    }
    run.summary_json = json_text(summary)
    return summary


def _spawn_worker(run_id: int, target: Callable[[int], None] | None = None) -> None:
    if target is None:
        from .requirement_verification import execute_verification_run

        target = execute_verification_run
    threading.Thread(target=target, args=(run_id,), daemon=True, name=f"verification-run-{run_id}").start()


def pause_run(db: Session, run: VerificationRun, reason: str = "用户主动暂停") -> VerificationRun:
    if run.status in FINAL_RUN_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已结束的执行不能暂停")
    run.phase = "paused"
    run.status = "paused"
    run.pause_reason = reason
    run.heartbeat_time = datetime.now()
    db.commit()
    return run


def resume_run(db: Session, run: VerificationRun) -> VerificationRun:
    if run.phase not in {"paused", "waiting_user"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前执行不需要恢复")
    if run.phase == "waiting_user":
        waiting = db.query(VerificationRunItem).filter(VerificationRunItem.run_id == run.id, VerificationRunItem.result.in_(["waiting_user", "waiting_confirmation"])).count()
        if waiting:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先完成“需要我处理”中的唯一操作")
    run.phase = "queued"
    run.status = "queued"
    run.pause_reason = None
    run.finish_time = None
    run.heartbeat_time = datetime.now()
    db.commit()
    _spawn_worker(run.id)
    return run


def cancel_run(db: Session, run: VerificationRun) -> VerificationRun:
    if run.status in FINAL_RUN_STATUSES:
        return run
    run.cancel_requested = 1
    if run.phase in {"queued", "paused", "waiting_user"}:
        _finish_cancelled_run(db, run)
        return run
    run.phase = "cancelling"
    run.status = "cancelling"
    run.heartbeat_time = datetime.now()
    db.commit()
    return run


def _finish_cancelled_run(db: Session, run: VerificationRun) -> None:
    now = datetime.now()
    unfinished = (
        db.query(VerificationRunItem)
        .filter(
            VerificationRunItem.run_id == run.id,
            VerificationRunItem.result.in_(["pending", "running", "waiting_user", "waiting_confirmation"]),
        )
        .all()
    )
    item_ids: list[int] = []
    for row in unfinished:
        row.result = "cancelled"
        row.failure_kind = "cancelled"
        row.message = "用户已取消执行"
        row.finish_time = now
        item_ids.append(row.item_id)
    if item_ids:
        for item in db.query(VerificationItem).filter(VerificationItem.id.in_(item_ids)).all():
            item.status = "cancelled"
            item.result_message = "用户已取消执行"
            item.update_time = now
    run.phase = "cancelled"
    run.status = "cancelled"
    run.progress_json = json_text({
        **json_load(run.progress_json, {}),
        "phase": "cancelled",
        "message": "执行已取消",
        "updated_at": time_text(now),
    })
    run.finish_time = now
    run.heartbeat_time = now
    db.commit()


def active_run_for_other_task(db: Session, task_id: int) -> VerificationRun | None:
    del task_id
    return (
        db.query(VerificationRun)
        .filter(VerificationRun.status.in_(ACTIVE_RUN_STATUSES))
        .order_by(VerificationRun.id.asc())
        .first()
    )


def recover_unfinished_runs() -> Dict[str, int]:
    db = SessionLocal()
    recovered = 0
    paused = 0
    try:
        runs = db.query(VerificationRun).filter(VerificationRun.status.in_(ACTIVE_RUN_STATUSES)).order_by(VerificationRun.id.asc()).all()
        for run in runs:
            if run.phase in {"waiting_user", "paused"}:
                continue
            if run.phase in {"data_preparing", "cancelling"}:
                if run.phase == "cancelling":
                    _finish_cancelled_run(db, run)
                else:
                    run.phase = "paused"
                    run.status = "paused"
                    run.pause_reason = "服务重启时数据脚本正在执行，为防止重复造数，请确认后继续"
                    paused += 1
                continue
            run.phase = "queued"
            run.status = "queued"
            run.pause_reason = "服务重启后已从安全检查点恢复"
            run.heartbeat_time = datetime.now()
            recovered += 1
        db.commit()
        for run in runs:
            if run.phase == "queued":
                _spawn_worker(run.id)
        return {"recovered": recovered, "paused": paused}
    finally:
        db.close()
