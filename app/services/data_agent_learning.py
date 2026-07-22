from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import case
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from ..models import DataAgentLearningSample, DataAgentRuleCandidate


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
    "pricing",
    "pricing_mode",
    "problem_scope",
    "problem_refund_quantity",
    "problem_refund_freight",
    "keyword",
    "shop_type",
    "order_payment_mode",
}
CANDIDATE_FIELDS = LEARNABLE_FIELDS - {"offer_price", "offer_unit_prices"}
REVISION_FIELD_MAP = {
    "item_count": "order_per_shop",
    "quantity_per_item": "order_item_num",
}
TERMINAL_STATUSES = {"succeeded", "failed", "blocked", "cancelled"}
MAX_DEPTH = 5
MAX_DICT_ITEMS = 80
MAX_LIST_ITEMS = 100
MAX_STRING_LENGTH = 4000
MAX_MATCH_PHRASES = 8
MAX_MATCH_PHRASE_LENGTH = 240
CANDIDATE_THRESHOLD = 3
CANDIDATE_RULE_KEYS = {"signature", "field", "match_phrases", "set_fields", "source_count"}
PRICING_FIELDS = {"mode", "amount", "amounts"}
PRICING_MODES = {"goods_total", "uniform_unit", "per_item_unit", "default_unit", "unspecified", "ambiguous"}
FORBIDDEN_CANDIDATE_KEYS = {
    "allow_large_refund",
    "permission",
    "amount_threshold",
    "backend",
    "account",
    "password",
    "profile",
    "system",
    "api_path",
    "url",
    "sql",
    "tool",
    "tool_name",
    "interface_order",
    "token",
    "cookie",
    "authorization",
    "secret",
    "browser_state",
    "ciphertext",
    "sensitive_variables",
    "customer",
    "identity",
}

_SENSITIVE_ASSIGNMENT_START = re.compile(
    rf"(?i)\b(password|passwd|pwd|access[_ -]?token|admin[_ -]?token|token|cookie|"
    rf"api[_ -]?key|secret|backend[_ -]?account|backend[_ -]?password|"
    rf"account[_ -]?ciphertext|browser[_ -]?state[_ -]?encrypted|sensitive[_ -]?variables)"
    rf"\s*[:=]\s*"
)
_BEARER_ASSIGNMENT = re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[^\s,;]+")


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().lower()).strip("_")
    return normalized.endswith(("_encrypted", "_ciphertext")) or normalized in SENSITIVE_KEYS or any(
        normalized.endswith(f"_{suffix}")
        for suffix in SENSITIVE_KEYS
    )


def _single_assigned_value_end(text: str, start: int) -> int:
    if start >= len(text):
        return start
    opening = text[start]
    if opening in {'"', "'"}:
        escaped = False
        for index in range(start + 1, len(text)):
            character = text[index]
            if character == opening and not escaped:
                return index + 1
            escaped = character == "\\" and not escaped
            if character != "\\":
                escaped = False
        return len(text)
    if opening in "{[":
        stack = ["}" if opening == "{" else "]"]
        quote = ""
        escaped = False
        for index in range(start + 1, len(text)):
            character = text[index]
            if quote:
                if character == quote and not escaped:
                    quote = ""
                escaped = character == "\\" and not escaped
                if character != "\\":
                    escaped = False
                continue
            if character in {'"', "'"}:
                quote = character
            elif character in "{[":
                stack.append("}" if character == "{" else "]")
            elif character == stack[-1]:
                stack.pop()
                if not stack:
                    return index + 1
        return len(text)
    index = start
    while index < len(text) and not text[index].isspace() and text[index] not in ",;":
        index += 1
    return index


def _assigned_value_end(text: str, start: int, field: str) -> int:
    end = _single_assigned_value_end(text, start)
    if field.casefold() != "cookie":
        return end
    while end < len(text):
        continuation = re.match(r"\s*;\s*[^;,\s=]+\s*=\s*", text[end:])
        if not continuation:
            break
        next_start = end + continuation.end()
        next_end = _single_assigned_value_end(text, next_start)
        if next_end <= next_start:
            break
        end = next_end
    return end


def _redact_sensitive_assignments(text: str) -> str:
    pieces: list[str] = []
    cursor = 0
    while match := _SENSITIVE_ASSIGNMENT_START.search(text, cursor):
        value_end = _assigned_value_end(text, match.end(), match.group(1))
        pieces.extend((text[cursor:match.start()], f"{match.group(1)}=***"))
        cursor = max(value_end, match.end())
    pieces.append(text[cursor:])
    return "".join(pieces)


def _sanitize_text(value: str) -> str:
    redacted = _BEARER_ASSIGNMENT.sub("Authorization: ***", value)
    return _redact_sensitive_assignments(redacted)[:MAX_STRING_LENGTH]


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


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _candidate_signature(field: str, after: Any) -> str:
    payload = _stable_json({"field": field, "after": after})
    return f"{field}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _normalized_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().lower()).strip("_")


def _normalized_candidate_value(value: Any) -> Any:
    safe_value = sanitize_learning_value(value)
    if isinstance(safe_value, dict):
        return {key: _normalized_candidate_value(item) for key, item in safe_value.items()}
    if isinstance(safe_value, list):
        return [_normalized_candidate_value(item) for item in safe_value]
    if isinstance(safe_value, str):
        return safe_value.strip()
    return safe_value


def _forbidden_candidate_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    parts = set(normalized.split("_"))
    return normalized in FORBIDDEN_CANDIDATE_KEYS or bool(
        parts & {"permission", "threshold", "backend", "account", "password", "profile", "system", "url", "sql", "tool", "token", "cookie", "authorization", "secret", "browser", "ciphertext", "customer", "identity"}
    )


def _reject_forbidden_candidate_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _forbidden_candidate_key(key):
                raise ValueError(f"候选规则包含禁止字段：{key}")
            _reject_forbidden_candidate_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_forbidden_candidate_keys(item)


def _validate_pricing_value(value: Any) -> None:
    if not isinstance(value, dict) or not value:
        raise ValueError("pricing 候选只允许安全价格语义与金额字段")
    unknown = sorted(set(value) - PRICING_FIELDS)
    if unknown:
        raise ValueError(f"pricing 候选包含不允许字段：{', '.join(unknown)}")
    mode = str(value.get("mode") or "")
    if mode not in PRICING_MODES:
        raise ValueError(f"pricing 候选包含不允许模式：{mode or 'empty'}")
    for key, item in value.items():
        if isinstance(item, dict):
            raise ValueError(f"pricing 候选字段不允许嵌套对象：{key}")
        if isinstance(item, list) and any(isinstance(entry, (dict, list, tuple)) for entry in item):
            raise ValueError(f"pricing 候选字段不允许复杂列表：{key}")


def validate_candidate_rule(rule: dict) -> dict:
    if not isinstance(rule, dict):
        raise ValueError("候选规则必须是对象")
    _reject_forbidden_candidate_keys(rule)
    unknown = sorted(set(rule) - CANDIDATE_RULE_KEYS)
    if unknown:
        raise ValueError(f"候选规则包含不允许字段：{', '.join(unknown)}")
    missing = sorted(CANDIDATE_RULE_KEYS - set(rule))
    if missing:
        raise ValueError(f"候选规则缺少字段：{', '.join(missing)}")

    source_field = _normalized_key(rule.get("field"))
    field = REVISION_FIELD_MAP.get(source_field, source_field)
    if field not in CANDIDATE_FIELDS:
        raise ValueError(f"候选规则包含禁止字段：{field or 'field'}")
    set_fields = rule.get("set_fields")
    if not isinstance(set_fields, dict) or len(set_fields) != 1:
        raise ValueError("候选规则 set_fields 只允许当前规范字段")
    raw_set_field, raw_set_value = next(iter(set_fields.items()))
    source_set_field = _normalized_key(raw_set_field)
    set_field = REVISION_FIELD_MAP.get(source_set_field, source_set_field)
    if set_field != field:
        raise ValueError("候选规则 set_fields 只允许当前规范字段")
    safe_value = _normalized_candidate_value(raw_set_value)
    if isinstance(safe_value, dict) and field != "pricing":
        raise ValueError(f"候选规则字段不允许嵌套对象：{field}")
    if field == "pricing":
        _validate_pricing_value(safe_value)

    signature = str(rule.get("signature") or "").strip()
    if signature != _candidate_signature(field, safe_value):
        raise ValueError("候选规则 signature 不是规范 field/after 摘要")
    phrases = rule.get("match_phrases")
    if not isinstance(phrases, list) or any(not isinstance(item, str) for item in phrases):
        raise ValueError("候选规则 match_phrases 必须是字符串列表")
    safe_phrases = sorted(
        {
            str(sanitize_learning_value(item)).strip()[:MAX_MATCH_PHRASE_LENGTH]
            for item in phrases
            if str(item or "").strip()
        }
    )[:MAX_MATCH_PHRASES]
    source_count = rule.get("source_count")
    if isinstance(source_count, bool) or not isinstance(source_count, int) or source_count < 1:
        raise ValueError("候选规则 source_count 必须是正整数")
    return {
        "signature": signature,
        "field": field,
        "match_phrases": safe_phrases,
        "set_fields": {field: safe_value},
        "source_count": source_count,
    }


def _normalized_correction(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    source_field = _normalized_key(item.get("field"))
    field = REVISION_FIELD_MAP.get(source_field, source_field)
    if field not in LEARNABLE_FIELDS:
        if _forbidden_candidate_key(source_field):
            raise ValueError(f"候选规则包含禁止字段：{source_field or 'field'}")
        return None
    raw_after = _normalized_candidate_value(item.get("after"))
    raw_before = _normalized_candidate_value(item.get("before"))
    if raw_after is None or raw_before == raw_after:
        return None
    if field == "offer_price":
        field = "pricing"
        after = {"mode": "uniform_unit", "amount": raw_after}
        before = {"mode": "uniform_unit", "amount": raw_before}
    elif field == "offer_unit_prices":
        field = "pricing"
        after = {"mode": "per_item_unit", "amounts": raw_after}
        before = {"mode": "per_item_unit", "amounts": raw_before}
    else:
        after = raw_after
        before = raw_before
    signature = _candidate_signature(field, after)
    validate_candidate_rule(
        {
            "signature": signature,
            "field": field,
            "match_phrases": ["candidate"],
            "set_fields": {field: after},
            "source_count": 1,
        }
    )
    return {"signature": signature, "field": field, "before": before, "after": after}


def _sample_corrections(sample: DataAgentLearningSample) -> list[dict]:
    try:
        raw = json.loads(sample.corrections_json or "[]")
    except (TypeError, ValueError):
        return []
    return [normalized for item in raw if (normalized := _normalized_correction(item)) is not None]


def refresh_rule_candidate(
    db: Session,
    project_id: int,
    module_key: str,
    intent_key: str,
    rule_key_or_signature: str,
) -> DataAgentRuleCandidate:
    signature = str(rule_key_or_signature or "").strip()
    if not signature:
        raise ValueError("候选规则 signature 不能为空")
    matching_samples: list[DataAgentLearningSample] = []
    matched_rule: dict | None = None
    samples = (
        db.query(DataAgentLearningSample)
        .filter(
            DataAgentLearningSample.project_id == int(project_id),
            DataAgentLearningSample.module_key == str(module_key),
            DataAgentLearningSample.intent_key == str(intent_key),
            DataAgentLearningSample.outcome == "success",
            DataAgentLearningSample.verified == 1,
        )
        .order_by(DataAgentLearningSample.id.asc())
        .all()
    )
    for sample in samples:
        sample_matches = {
            correction["signature"]: correction
            for correction in _sample_corrections(sample)
            if correction["signature"] == signature
        }
        if signature in sample_matches:
            matching_samples.append(sample)
            matched_rule = sample_matches[signature]
    if not matching_samples or matched_rule is None:
        raise ValueError("没有匹配的已验证纠正样本")

    source_ids = sorted({int(sample.id) for sample in matching_samples})
    phrases = sorted(
        {
            str(sanitize_learning_value(sample.instruction_text or "")).strip()[:MAX_MATCH_PHRASE_LENGTH]
            for sample in matching_samples
            if str(sample.instruction_text or "").strip()
        }
    )[:MAX_MATCH_PHRASES]
    proposal = validate_candidate_rule(
        {
            "signature": signature,
            "field": matched_rule["field"],
            "match_phrases": phrases,
            "set_fields": {matched_rule["field"]: matched_rule["after"]},
            "source_count": len(source_ids),
        }
    )
    now = datetime.now()
    identity = (
        DataAgentRuleCandidate.project_id == int(project_id),
        DataAgentRuleCandidate.module_key == str(module_key),
        DataAgentRuleCandidate.intent_key == str(intent_key),
        DataAgentRuleCandidate.rule_key == signature,
    )
    db.execute(
        sqlite_insert(DataAgentRuleCandidate)
        .values(
            project_id=int(project_id),
            module_key=str(module_key)[:80],
            intent_key=str(intent_key)[:120],
            rule_key=signature[:160],
            proposal_json=_stable_json(proposal),
            source_sample_ids_json=_stable_json(source_ids),
            occurrence_count=len(source_ids),
            regression_json="{}",
            status="pending_regression" if len(source_ids) >= CANDIDATE_THRESHOLD else "collecting",
            create_time=now,
        )
        .on_conflict_do_nothing(
            index_elements=["project_id", "module_key", "intent_key", "rule_key"]
        )
    )
    status_value = DataAgentRuleCandidate.status
    if len(source_ids) >= CANDIDATE_THRESHOLD:
        status_value = case(
            (DataAgentRuleCandidate.status == "collecting", "pending_regression"),
            else_=DataAgentRuleCandidate.status,
        )
    (
        db.query(DataAgentRuleCandidate)
        .filter(*identity, DataAgentRuleCandidate.occurrence_count <= len(source_ids))
        .update(
            {
                DataAgentRuleCandidate.proposal_json: _stable_json(proposal),
                DataAgentRuleCandidate.source_sample_ids_json: _stable_json(source_ids),
                DataAgentRuleCandidate.occurrence_count: len(source_ids),
                DataAgentRuleCandidate.status: status_value,
                DataAgentRuleCandidate.update_time: now,
            },
            synchronize_session=False,
        )
    )
    db.flush()
    return db.query(DataAgentRuleCandidate).filter(*identity).populate_existing().one()


def _refresh_candidates_with_retry(
    db: Session,
    sample: DataAgentLearningSample,
) -> list[DataAgentRuleCandidate]:
    for attempt in range(3):
        try:
            candidates = refresh_candidates_for_sample(db, sample)
            db.commit()
            return candidates
        except OperationalError as exc:
            db.rollback()
            if "locked" not in str(exc).lower() or attempt == 2:
                raise
            time.sleep(0.05 * (attempt + 1))
    return []


def refresh_candidates_for_sample(
    db: Session,
    sample: DataAgentLearningSample,
) -> list[DataAgentRuleCandidate]:
    if sample is None or sample.outcome != "success" or int(sample.verified or 0) != 1:
        return []
    signatures = sorted({item["signature"] for item in _sample_corrections(sample)})
    return [
        refresh_rule_candidate(
            db,
            int(sample.project_id),
            str(sample.module_key),
            str(sample.intent_key),
            signature,
        )
        for signature in signatures
    ]


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
    corrections = _corrections(session)
    sample = DataAgentLearningSample(
        project_id=int(session.project_id),
        session_id=str(session.id)[:64],
        module_key=module_key,
        intent_key=intent_key,
        instruction_text=str(safe_instruction),
        model_candidate_json="{}",
        initial_contract_json=json.dumps(safe_initial_contract, ensure_ascii=False, sort_keys=True, default=str),
        final_contract_json=json.dumps(safe_final_contract, ensure_ascii=False, sort_keys=True, default=str),
        corrections_json=json.dumps(corrections, ensure_ascii=False, sort_keys=True, default=str),
        outcome="success" if verified else "failure",
        verified=1 if verified else 0,
        fingerprint=fingerprint,
        create_time=datetime.now(),
    )
    db.add(sample)
    try:
        db.commit()
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
    db.refresh(sample)
    if verified and corrections:
        _refresh_candidates_with_retry(db, sample)
        db.refresh(sample)
    return sample
