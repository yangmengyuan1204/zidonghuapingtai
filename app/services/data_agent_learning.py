from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import DataAgentLearningSample


SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pwd",
    "token",
    "cookie",
    "authorization",
    "secret",
    "api_key",
    "access_token",
    "admin_token",
    "backend_account",
    "backend_password",
    "browser_state_encrypted",
    "account_ciphertext",
    "sensitive_variables",
}
LEARNABLE_FIELDS = {
    "target_node",
    "order_shop_count",
    "order_per_shop",
    "order_item_num",
    "offer_price",
    "offer_unit_prices",
    "pricing_mode",
    "problem_scope",
    "problem_refund_quantity",
    "problem_refund_freight",
    "keyword",
    "shop_type",
    "order_payment_mode",
}
REVISION_FIELD_MAP = {
    "item_count": "order_per_shop",
    "quantity_per_item": "order_item_num",
    "pricing": "pricing_mode",
}
TERMINAL_STATUSES = {"succeeded", "failed", "blocked", "cancelled"}
MAX_DEPTH = 5
MAX_DICT_ITEMS = 80
MAX_LIST_ITEMS = 100
MAX_STRING_LENGTH = 4000

_ASSIGNED_VALUE = r'(?:"[^"\r\n]*"|\'[^\'\r\n]*\'|[^\s,;]+)'
_SENSITIVE_ASSIGNMENT = re.compile(
    rf"(?i)\b(password|passwd|pwd|access[_ -]?token|admin[_ -]?token|token|"
    rf"api[_ -]?key|secret|backend[_ -]?account|backend[_ -]?password|"
    rf"account[_ -]?ciphertext|browser[_ -]?state[_ -]?encrypted|sensitive[_ -]?variables)"
    rf"\s*[:=]\s*{_ASSIGNED_VALUE}"
)
_BEARER_ASSIGNMENT = re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[^\s,;]+")
_COOKIE_ASSIGNMENT = re.compile(
    rf"(?i)\bcookie\s*[:=]\s*{_ASSIGNED_VALUE}(?:\s*;\s*[^;\s,]+)*"
)


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().lower()).strip("_")
    return normalized.endswith(("_encrypted", "_ciphertext")) or normalized in SENSITIVE_KEYS or any(
        normalized.endswith(f"_{suffix}")
        for suffix in SENSITIVE_KEYS
    )


def _sanitize_text(value: str) -> str:
    redacted = _BEARER_ASSIGNMENT.sub("Authorization: ***", value)
    redacted = _COOKIE_ASSIGNMENT.sub("Cookie=***", redacted)
    return _SENSITIVE_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=***", redacted)[:MAX_STRING_LENGTH]


def sanitize_learning_value(value: Any, key: str = "", *, _depth: int = 0) -> Any:
    if _sensitive_key(key):
        return "***"
    if _depth >= MAX_DEPTH:
        return "..."
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_learning_value(item, str(item_key), _depth=_depth + 1)
            for item_key, item in sorted(value.items(), key=lambda pair: str(pair[0]))[:MAX_DICT_ITEMS]
        }
    if isinstance(value, (list, tuple)):
        return [
            sanitize_learning_value(item, key, _depth=_depth + 1)
            for item in list(value)[:MAX_LIST_ITEMS]
        ]
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _sanitize_text(str(value))


def sample_fingerprint(project_id: int, instruction: str, final_contract: dict) -> str:
    payload = sanitize_learning_value(
        [int(project_id), str(instruction or ""), final_contract if isinstance(final_contract, dict) else {}]
    )
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _revision_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _corrections(session: Any) -> list[Dict[str, Any]]:
    corrections: list[Dict[str, Any]] = []
    for event in list(getattr(session, "events", None) or []):
        if not isinstance(event, dict) or event.get("kind") != "goal_updated":
            continue
        for item in event.get("corrections") or []:
            if isinstance(item, dict) and item.get("field") in LEARNABLE_FIELDS:
                corrections.append(
                    {
                        "field": item["field"],
                        "before": item.get("before"),
                        "after": item.get("after"),
                        "source": "direct_edit",
                    }
                )
    intent_state = getattr(session, "intent_state", None)
    intent_state = intent_state if isinstance(intent_state, dict) else {}
    for item in intent_state.get("revisions") or []:
        if not isinstance(item, dict):
            continue
        source_field = str(item.get("field") or "")
        field = REVISION_FIELD_MAP.get(source_field, source_field)
        if field not in LEARNABLE_FIELDS:
            continue
        before = _revision_value(item.get("before"))
        after = _revision_value(item.get("after"))
        if source_field == "pricing":
            before = before.get("mode") if isinstance(before, dict) else None
            after = after.get("mode") if isinstance(after, dict) else None
        if before is None or after is None or before == after:
            continue
        corrections.append(
            {
                "field": field,
                "before": before,
                "after": after,
                "source": "clarification",
            }
        )
    return sanitize_learning_value(corrections)


def _confirmed(session: Any) -> bool:
    return any(
        isinstance(event, dict) and event.get("kind") == "confirmation"
        for event in list(getattr(session, "events", None) or [])
    )


def _operations_verified(session: Any, result: Dict[str, Any]) -> bool:
    seam = result.get("verification") if isinstance(result.get("verification"), dict) else {}
    if seam.get("passed") is True:
        return True
    goal = getattr(session, "goal", None)
    goal = goal if isinstance(goal, dict) else {}
    operations = [item for item in goal.get("operations") or [] if isinstance(item, dict)]
    operation_results = result.get("operation_results")
    operation_results = operation_results if isinstance(operation_results, dict) else {}
    if not operations or not operation_results:
        return False
    for index, operation in enumerate(operations, start=1):
        operation_id = str(operation.get("id") or f"operation_{index}")
        actual = operation_results.get(operation_id)
        if not isinstance(actual, dict) or actual.get("status") != "completed":
            return False
        verification = actual.get("verification")
        if (
            not isinstance(verification, dict)
            or not verification
            or verification.get("passed") is False
            or verification.get("reason")
        ):
            return False
    return True


def _sample_scope(goal: Dict[str, Any]) -> tuple[str, str]:
    operations = [item for item in goal.get("operations") or [] if isinstance(item, dict)]
    operation_type = str((operations[0] if operations else {}).get("type") or "data_agent")
    module_key = {
        "advance_order": "order",
        "advance_porder": "porder",
        "problem_goods": "problem_goods",
    }.get(operation_type, operation_type)
    mode = str(goal.get("mode") or "").strip()
    intent_key = "create" if mode == "new" else mode or operation_type
    return module_key[:80], intent_key[:120]


def capture_learning_sample(
    db: Session,
    session: Any,
    final_status: str,
    result: dict,
) -> DataAgentLearningSample | None:
    if session is None or final_status not in TERMINAL_STATUSES:
        return None
    goal = getattr(session, "goal", None)
    if not isinstance(goal, dict) or not goal:
        return None
    messages = list(getattr(session, "messages", None) or [])
    instruction = ""
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "user":
            instruction = str(message.get("content") or "")
            break
    safe_instruction = sanitize_learning_value(instruction)
    safe_final_contract = sanitize_learning_value(goal)
    initial_contract = getattr(session, "initial_contract", None)
    safe_initial_contract = sanitize_learning_value(
        initial_contract if isinstance(initial_contract, dict) else {}
    )
    fingerprint = sample_fingerprint(int(session.project_id), safe_instruction, safe_final_contract)
    existing = (
        db.query(DataAgentLearningSample)
        .filter(DataAgentLearningSample.fingerprint == fingerprint)
        .first()
    )
    if existing:
        return existing
    verified = bool(
        final_status == "succeeded"
        and _confirmed(session)
        and _operations_verified(session, result if isinstance(result, dict) else {})
    )
    module_key, intent_key = _sample_scope(goal)
    sample = DataAgentLearningSample(
        project_id=int(session.project_id),
        session_id=str(session.id)[:64],
        module_key=module_key,
        intent_key=intent_key,
        instruction_text=str(safe_instruction),
        model_candidate_json="{}",
        initial_contract_json=json.dumps(safe_initial_contract, ensure_ascii=False, sort_keys=True, default=str),
        final_contract_json=json.dumps(safe_final_contract, ensure_ascii=False, sort_keys=True, default=str),
        corrections_json=json.dumps(_corrections(session), ensure_ascii=False, sort_keys=True, default=str),
        outcome="success" if verified else "failure",
        verified=1 if verified else 0,
        fingerprint=fingerprint,
        create_time=datetime.now(),
    )
    db.add(sample)
    try:
        db.commit()
        db.refresh(sample)
        return sample
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(DataAgentLearningSample)
            .filter(DataAgentLearningSample.fingerprint == fingerprint)
            .first()
        )
        if existing:
            return existing
        raise
