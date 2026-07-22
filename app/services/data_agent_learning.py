from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict

from sqlalchemy import case, or_
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
MAX_REGRESSION_IDS = 100
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
VARIABLE_OVERLAY_FIELDS = {
    "order_shop_count",
    "order_per_shop",
    "order_item_num",
    "keyword",
    "shop_type",
    "order_payment_mode",
}
PROBLEM_OVERLAY_FIELDS = {
    "problem_scope",
    "problem_refund_quantity",
    "problem_refund_freight",
}
SAFE_TARGET_OPERATION_TYPES = {"advance_order", "advance_porder"}

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


def _validate_overlay_value(field: str, value: Any) -> None:
    strings: list[str] = []

    def collect(item: Any) -> None:
        if isinstance(item, dict):
            for nested in item.values():
                collect(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                collect(nested)
        elif isinstance(item, str):
            strings.append(item.strip())

    collect(value)
    unsafe = re.compile(
        r"(?i)(?:https?://|(?:^|[\\/])api[\\/]|\b(?:select|insert|update|delete|drop|alter)\b.{0,40}\b(?:from|into|set|table)\b)"
    )
    if any(unsafe.search(text) for text in strings):
        raise ValueError(f"候选规则字段包含禁止值：{field}")
    if field == "target_node":
        from . import data_factory_agent as agent_service

        if not isinstance(value, str) or value not in agent_service.FULL_FLOW_NODE_LABELS:
            raise ValueError("target_node 候选值不合法")
    if field == "order_payment_mode" and value not in {"balance_first", "bank"}:
        raise ValueError("order_payment_mode 候选值不合法")


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
    _validate_overlay_value(field, safe_value)

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
    if not safe_phrases or not any(
        re.sub(
            r"[\W_]+",
            "",
            unicodedata.normalize("NFKC", phrase),
            flags=re.UNICODE,
        )
        for phrase in safe_phrases
    ):
        raise ValueError("候选规则 match_phrases 不能为空")
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


def _normalized_match_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def candidate_matches_instruction(proposal: dict, instruction: str) -> bool:
    validated = validate_candidate_rule(proposal)
    normalized_instruction = _normalized_match_text(instruction)
    if not normalized_instruction:
        return False
    return any(
        normalized_phrase and normalized_phrase in normalized_instruction
        for phrase in validated["match_phrases"]
        if (normalized_phrase := _normalized_match_text(phrase))
    )


def _decimal_text(value: Any, field: str) -> str:
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} 必须是合法金额") from None
    if not number.is_finite() or number < 0:
        raise ValueError(f"{field} 必须是非负有限金额")
    cents = number * Decimal("100")
    if cents != cents.to_integral_value():
        raise ValueError(f"{field} 最多支持两位小数")
    return format(number.normalize(), "f")


def _compile_overlay_pricing(goal: dict, value: dict) -> tuple[dict, dict]:
    variables = copy.deepcopy(goal.get("variables") or {})
    try:
        item_count = int(variables.get("order_shop_count") or 0) * int(
            variables.get("order_per_shop") or 0
        )
        quantity = int(variables.get("order_item_num") or 0)
    except (TypeError, ValueError):
        raise ValueError("pricing overlay 缺少合法数量合同") from None
    if item_count < 1 or quantity < 1:
        raise ValueError("pricing overlay 缺少合法数量合同")

    mode = str(value.get("mode") or "")
    requested_total = ""
    if mode == "goods_total":
        amount = _decimal_text(value.get("amount"), "商品总价")
        total_cents = int(Decimal(amount) * 100)
        if total_cents % quantity:
            raise ValueError("商品总价无法按购买数量精确分摊")
        unit_base, remainder = divmod(total_cents // quantity, item_count)
        effective = [
            format((Decimal(unit_base + (1 if index < remainder else 0)) / 100).normalize(), "f")
            for index in range(item_count)
        ]
        requested_total = amount
    elif mode in {"uniform_unit", "default_unit"}:
        amount = _decimal_text(value.get("amount"), "商品单价")
        effective = [amount] * item_count
    elif mode == "per_item_unit":
        raw_amounts = value.get("amounts")
        if not isinstance(raw_amounts, list) or not raw_amounts:
            raise ValueError("逐商品单价必须是非空列表")
        amounts = [_decimal_text(item, "逐商品单价") for item in raw_amounts]
        if len(amounts) == 1:
            effective = amounts * item_count
        elif len(amounts) == item_count:
            effective = amounts
        else:
            raise ValueError("逐商品单价数量与商品合同不一致")
    else:
        raise ValueError("pricing overlay 不允许不确定价格模式")

    if len(set(effective)) == 1:
        variables["offer_price"] = effective[0]
        variables.pop("offer_unit_prices", None)
    else:
        variables["offer_unit_prices"] = effective
        variables.pop("offer_price", None)
    pricing = copy.deepcopy(((goal.get("intent") or {}).get("pricing") or {}))
    pricing.update(
        {
            "mode": mode,
            "requested_goods_total": requested_total,
            "effective_unit_prices": effective,
            "effective_goods_total": format(
                sum(Decimal(item) * quantity for item in effective).normalize(),
                "f",
            ),
            "includes_fees": False,
        }
    )
    return pricing, variables


def _problem_operation(goal: dict) -> dict | None:
    for operation in goal.get("operations") or []:
        if isinstance(operation, dict) and operation.get("type") == "problem_goods":
            return operation
    return None


def apply_candidate_overlay(goal: dict, proposal: dict) -> dict:
    if not isinstance(goal, dict):
        raise ValueError("候选 overlay 目标合同必须是对象")
    validated = validate_candidate_rule(copy.deepcopy(proposal))
    overlaid = copy.deepcopy(goal)
    field = validated["field"]
    value = copy.deepcopy(validated["set_fields"][field])

    if field == "target_node":
        overlaid["target_node"] = value
        variables = overlaid.get("variables")
        if isinstance(variables, dict):
            variables["stop_after_node"] = value
        for operation in overlaid.get("operations") or []:
            if isinstance(operation, dict) and operation.get("type") in SAFE_TARGET_OPERATION_TYPES:
                operation["target_node"] = value
        return overlaid

    if field in VARIABLE_OVERLAY_FIELDS:
        variables = overlaid.setdefault("variables", {})
        if not isinstance(variables, dict):
            raise ValueError("候选 overlay variables 必须是对象")
        variables[field] = value
        return overlaid

    if field == "pricing":
        pricing, variables = _compile_overlay_pricing(overlaid, value)
        intent = overlaid.setdefault("intent", {})
        if not isinstance(intent, dict):
            raise ValueError("候选 overlay intent 必须是对象")
        intent["pricing"] = pricing
        overlaid["variables"] = variables
        return overlaid

    if field in PROBLEM_OVERLAY_FIELDS:
        variables = overlaid.get("variables")
        operation = _problem_operation(overlaid)
        if not isinstance(variables, dict) or operation is None:
            raise ValueError("问题产品候选只能应用到已有问题产品合同")
        variables[field] = value
        if field == "problem_scope":
            if value not in {"all", "item"}:
                raise ValueError("problem_scope 候选只允许 all 或 item")
            operation["scope"] = "all_candidates" if value == "all" else "selected_item"
        elif field == "problem_refund_quantity":
            if value in {"all", "half", "keep"}:
                operation["quantity_refund_mode"] = value
                operation["quantity_refund_value"] = None
            elif isinstance(value, int) and not isinstance(value, bool) and value > 0:
                operation["quantity_refund_mode"] = "fixed"
                operation["quantity_refund_value"] = value
            else:
                raise ValueError("problem_refund_quantity 候选值不合法")
        else:
            if value not in {"all", "keep"}:
                raise ValueError("problem_refund_freight 候选只允许 all 或 keep")
            operation["freight_refund_mode"] = value
        return overlaid

    raise ValueError("候选 overlay 字段不受支持")


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
    proposal_json = _stable_json(proposal)
    source_ids_json = _stable_json(source_ids)
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
            proposal_json=proposal_json,
            source_sample_ids_json=source_ids_json,
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
    regression_json_value = DataAgentRuleCandidate.regression_json
    if len(source_ids) >= CANDIDATE_THRESHOLD:
        evidence_changed = or_(
            DataAgentRuleCandidate.occurrence_count < len(source_ids),
            DataAgentRuleCandidate.proposal_json != proposal_json,
            DataAgentRuleCandidate.source_sample_ids_json != source_ids_json,
        )
        requires_regression = or_(
            DataAgentRuleCandidate.status == "collecting",
            evidence_changed,
        )
        status_value = case(
            (requires_regression, "pending_regression"),
            else_=DataAgentRuleCandidate.status,
        )
        regression_json_value = case(
            (requires_regression, "{}"),
            else_=DataAgentRuleCandidate.regression_json,
        )
    (
        db.query(DataAgentRuleCandidate)
        .filter(*identity, DataAgentRuleCandidate.occurrence_count <= len(source_ids))
        .update(
            {
                DataAgentRuleCandidate.proposal_json: proposal_json,
                DataAgentRuleCandidate.source_sample_ids_json: source_ids_json,
                DataAgentRuleCandidate.occurrence_count: len(source_ids),
                DataAgentRuleCandidate.regression_json: regression_json_value,
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


def _bounded_ids(values: Any) -> list[int]:
    if not isinstance(values, (list, tuple, set)):
        return []
    result = {
        int(value)
        for value in values
        if not isinstance(value, bool) and isinstance(value, int) and int(value) > 0
    }
    return sorted(result)[:MAX_REGRESSION_IDS]


def _regression_summary(*, fixture_total: int, historical_total: int) -> dict:
    return {
        "fixture_total": int(fixture_total),
        "historical_total": int(historical_total),
        "passed": 0,
        "failed": 0,
        "conflicts": 0,
        "failed_case_ids": [],
        "failed_sample_ids": [],
        "conflict_sample_ids": [],
        "source_sample_ids_checked": [],
        "error_codes": [],
    }


def _add_error_code(summary: dict, code: str) -> None:
    codes = summary.setdefault("error_codes", [])
    if code not in codes:
        codes.append(code)
        codes.sort()


def _finish_summary(summary: dict) -> dict:
    raw_failed_case_ids = {str(value) for value in summary.get("failed_case_ids") or [] if str(value)}
    raw_failed_sample_ids = {
        int(value)
        for value in summary.get("failed_sample_ids") or []
        if not isinstance(value, bool) and isinstance(value, int) and value > 0
    }
    raw_conflict_sample_ids = {
        int(value)
        for value in summary.get("conflict_sample_ids") or []
        if not isinstance(value, bool) and isinstance(value, int) and value > 0
    }
    for key in (
        "failed_case_ids",
        "failed_sample_ids",
        "conflict_sample_ids",
        "source_sample_ids_checked",
    ):
        values = summary.get(key) or []
        if key == "failed_case_ids":
            summary[key] = sorted({str(value)[:160] for value in values if str(value)})[
                :MAX_REGRESSION_IDS
            ]
        else:
            summary[key] = _bounded_ids(values)
    summary["error_codes"] = sorted(
        {str(code)[:80] for code in summary.get("error_codes") or [] if str(code)}
    )[:20]
    summary["failed"] = len(raw_failed_case_ids) + len(raw_failed_sample_ids)
    summary["conflicts"] = len(raw_conflict_sample_ids)
    total = int(summary.get("fixture_total") or 0) + int(summary.get("historical_total") or 0)
    summary["passed"] = max(0, total - summary["failed"] - summary["conflicts"])
    if summary["error_codes"] and summary["failed"] == 0:
        summary["failed"] = 1
        summary["passed"] = max(0, total - 1 - summary["conflicts"])
    return summary


def regression_passed(summary: dict) -> bool:
    if not isinstance(summary, dict):
        return False
    try:
        fixture_total = int(summary.get("fixture_total"))
        historical_total = int(summary.get("historical_total"))
        passed = int(summary.get("passed"))
        failed = int(summary.get("failed"))
        conflicts = int(summary.get("conflicts"))
    except (TypeError, ValueError):
        return False
    return (
        fixture_total == 80
        and historical_total >= 0
        and passed == fixture_total + historical_total
        and failed == 0
        and conflicts == 0
        and not summary.get("error_codes")
    )


def _load_json_object(value: Any) -> dict:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("JSON object is empty")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("JSON contract must be an object")
    return parsed


def _load_json_list(value: Any) -> list:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("JSON list is empty")
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("JSON value must be a list")
    return parsed


def _contract_field_value(goal: dict, field: str) -> Any:
    if field == "target_node":
        return _normalized_candidate_value(goal.get("target_node"))
    if field in VARIABLE_OVERLAY_FIELDS or field in PROBLEM_OVERLAY_FIELDS:
        variables = goal.get("variables") if isinstance(goal.get("variables"), dict) else {}
        if field in variables:
            return _normalized_candidate_value(variables.get(field))
        operation = _problem_operation(goal) if field in PROBLEM_OVERLAY_FIELDS else None
        if operation is None:
            return None
        if field == "problem_scope":
            return {"all_candidates": "all", "selected_item": "item"}.get(operation.get("scope"))
        if field == "problem_refund_quantity":
            mode = operation.get("quantity_refund_mode")
            return operation.get("quantity_refund_value") if mode == "fixed" else mode
        return operation.get("freight_refund_mode")
    if field == "pricing":
        intent = goal.get("intent") if isinstance(goal.get("intent"), dict) else {}
        pricing = intent.get("pricing") if isinstance(intent.get("pricing"), dict) else {}
        mode = str(pricing.get("mode") or "")
        if mode == "goods_total":
            return {"mode": mode, "amount": _normalized_candidate_value(pricing.get("requested_goods_total"))}
        if mode in {"uniform_unit", "default_unit"}:
            prices = pricing.get("effective_unit_prices") or []
            amount = prices[0] if isinstance(prices, list) and prices else None
            return {"mode": mode, "amount": _normalized_candidate_value(amount)}
        if mode == "per_item_unit":
            return {
                "mode": mode,
                "amounts": _normalized_candidate_value(pricing.get("effective_unit_prices") or []),
            }
        return {"mode": mode} if mode else None
    return None


_MISSING_CONTRACT_VALUE = object()


def _changed_contract_paths(before: Any, after: Any, path: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    if isinstance(before, dict) and isinstance(after, dict):
        paths: list[tuple[Any, ...]] = []
        for key in sorted(set(before) | set(after), key=str):
            if key not in before or key not in after:
                paths.append((*path, key))
            else:
                paths.extend(_changed_contract_paths(before[key], after[key], (*path, key)))
        return paths
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return [path]
        paths = []
        for index, (before_item, after_item) in enumerate(zip(before, after)):
            paths.extend(_changed_contract_paths(before_item, after_item, (*path, index)))
        return paths
    return [path] if before != after else []


def _contract_path_value(value: Any, path: tuple[Any, ...]) -> Any:
    current = value
    for part in path:
        if isinstance(part, int):
            if not isinstance(current, list) or part >= len(current):
                return _MISSING_CONTRACT_VALUE
            current = current[part]
        else:
            if not isinstance(current, dict) or part not in current:
                return _MISSING_CONTRACT_VALUE
            current = current[part]
    return current


def _candidate_contract_structure_valid(goal: dict, field: str) -> bool:
    if not isinstance(goal, dict) or not goal:
        return False
    variables = goal.get("variables")
    if not isinstance(variables, dict):
        return False
    if field == "target_node":
        operations = goal.get("operations")
        return (
            "target_node" in goal
            and isinstance(operations, list)
            and any(
                isinstance(operation, dict)
                and operation.get("type") in SAFE_TARGET_OPERATION_TYPES
                for operation in operations
            )
        )
    if field in VARIABLE_OVERLAY_FIELDS:
        return field in variables
    if field == "pricing":
        intent = goal.get("intent")
        return (
            isinstance(intent, dict)
            and isinstance(intent.get("pricing"), dict)
            and bool(intent["pricing"])
        )
    if field in PROBLEM_OVERLAY_FIELDS:
        return field in variables and _problem_operation(goal) is not None
    return False


def _safe_source_ids(candidate: DataAgentRuleCandidate) -> list[int]:
    parsed = json.loads(candidate.source_sample_ids_json or "[]")
    if (
        not isinstance(parsed, list)
        or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in parsed)
    ):
        raise ValueError("source sample ids must be positive integers")
    return sorted(set(parsed))


def evaluate_candidate(db: Session, candidate: DataAgentRuleCandidate) -> dict:
    from scripts import evaluate_data_agent_hit_rate as fixture_evaluator

    samples = (
        db.query(DataAgentLearningSample)
        .filter(
            DataAgentLearningSample.project_id == int(candidate.project_id),
            DataAgentLearningSample.outcome == "success",
            DataAgentLearningSample.verified == 1,
        )
        .order_by(DataAgentLearningSample.id.asc())
        .all()
    )
    try:
        fixture_cases = fixture_evaluator.expand_fixture_cases()
    except Exception:
        summary = _regression_summary(fixture_total=0, historical_total=len(samples))
        _add_error_code(summary, "fixture_load_failed")
        return _finish_summary(summary)
    summary = _regression_summary(fixture_total=len(fixture_cases), historical_total=len(samples))
    if len(fixture_cases) != 80:
        _add_error_code(summary, "fixture_count_invalid")
        return _finish_summary(summary)

    try:
        raw_proposal = json.loads(candidate.proposal_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        _add_error_code(summary, "invalid_candidate_json")
        return _finish_summary(summary)
    try:
        proposal = validate_candidate_rule(raw_proposal)
        source_ids = _safe_source_ids(candidate)
    except (TypeError, ValueError):
        _add_error_code(summary, "invalid_candidate")
        return _finish_summary(summary)
    summary["source_sample_ids_checked"] = source_ids
    if (
        int(proposal["source_count"]) != len(source_ids)
        or int(candidate.occurrence_count or 0) != len(source_ids)
    ):
        _add_error_code(summary, "source_coverage_invalid")
        return _finish_summary(summary)
    source_id_set = set(source_ids)
    proposal_after = _normalized_candidate_value(proposal["set_fields"][proposal["field"]])

    parsed_samples: list[tuple[DataAgentLearningSample, dict, dict]] = []
    for sample in samples:
        if (
            not isinstance(sample.initial_contract_json, str)
            or not sample.initial_contract_json.strip()
            or not isinstance(sample.final_contract_json, str)
            or not sample.final_contract_json.strip()
        ):
            summary["failed_sample_ids"].append(int(sample.id))
            _add_error_code(summary, "invalid_sample_contract")
            continue
        try:
            _load_json_object(sample.model_candidate_json)
            initial_contract = _load_json_object(sample.initial_contract_json)
            final_contract = _load_json_object(sample.final_contract_json)
            _load_json_list(sample.corrections_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            summary["failed_sample_ids"].append(int(sample.id))
            _add_error_code(summary, "invalid_sample_json")
            continue
        if not initial_contract or not final_contract:
            summary["failed_sample_ids"].append(int(sample.id))
            _add_error_code(summary, "invalid_sample_contract")
            continue
        parsed_samples.append((sample, initial_contract, final_contract))
    if summary["failed_sample_ids"]:
        return _finish_summary(summary)

    for case in fixture_cases:
        case_id = str(case.get("id") or "")
        try:
            baseline = fixture_evaluator.analyze_without_execution(
                str(case.get("instruction") or ""),
                case.get("candidate"),
            )
            result = copy.deepcopy(baseline)
            if candidate_matches_instruction(proposal, str(case.get("instruction") or "")):
                result["goal"] = apply_candidate_overlay(baseline.get("goal") or {}, proposal)
                if result["goal"] != (baseline.get("goal") or {}):
                    summary["failed_case_ids"].append(case_id)
                    continue
            if not fixture_evaluator.fixture_case_matches(result, case):
                summary["failed_case_ids"].append(case_id)
        except Exception:
            summary["failed_case_ids"].append(case_id)
            _add_error_code(summary, "fixture_evaluation_failed")

    found_sample_ids = {int(sample.id) for sample, _, _ in parsed_samples}
    summary["conflict_sample_ids"].extend(source_id_set - found_sample_ids)
    for sample, initial_contract, final_contract in parsed_samples:
        sample_id = int(sample.id)
        try:
            matched = candidate_matches_instruction(proposal, sample.instruction_text)
            if sample_id in source_id_set and not matched:
                summary["conflict_sample_ids"].append(sample_id)
                continue
            if not matched:
                continue
            if not _candidate_contract_structure_valid(
                initial_contract,
                proposal["field"],
            ) or not _candidate_contract_structure_valid(final_contract, proposal["field"]):
                summary["failed_sample_ids"].append(sample_id)
                _add_error_code(summary, "invalid_sample_contract")
                continue
            overlaid = apply_candidate_overlay(initial_contract, proposal)
            touched_paths = _changed_contract_paths(initial_contract, overlaid)
            overlaid_value = _contract_field_value(overlaid, proposal["field"])
            final_value = _contract_field_value(final_contract, proposal["field"])
            touched_paths_match = bool(touched_paths) and all(
                _contract_path_value(final_contract, path)
                == _contract_path_value(overlaid, path)
                for path in touched_paths
            )
            if (
                overlaid_value != proposal_after
                or final_value != proposal_after
                or not touched_paths_match
            ):
                summary["conflict_sample_ids"].append(sample_id)
        except Exception:
            summary["conflict_sample_ids"].append(sample_id)
            _add_error_code(summary, "historical_evaluation_failed")
    return _finish_summary(summary)


def _transaction_failure_summary(summary: dict | None) -> dict:
    current = summary if isinstance(summary, dict) else {}
    failed = _regression_summary(
        fixture_total=int(current.get("fixture_total") or 0),
        historical_total=int(current.get("historical_total") or 0),
    )
    failed["source_sample_ids_checked"] = _bounded_ids(
        current.get("source_sample_ids_checked") or []
    )
    _add_error_code(failed, "transaction_failed")
    return _finish_summary(failed)


def run_candidate_regression(db: Session, candidate_id: int) -> DataAgentRuleCandidate:
    candidate = db.get(DataAgentRuleCandidate, int(candidate_id))
    if candidate is None:
        raise ValueError("候选规则不存在")
    if candidate.status != "pending_regression":
        raise ValueError("仅 pending_regression 候选可运行回归")

    try:
        summary = evaluate_candidate(db, candidate)
    except Exception:
        summary = _regression_summary(fixture_total=0, historical_total=0)
        _add_error_code(summary, "regression_exception")
        summary = _finish_summary(summary)
    candidate.regression_json = _stable_json(summary)
    candidate.status = "pending_review" if regression_passed(summary) else "regression_failed"
    candidate.update_time = datetime.now()
    try:
        db.commit()
    except Exception:
        db.rollback()
        fallback = _transaction_failure_summary(summary)
        candidate = db.get(DataAgentRuleCandidate, int(candidate_id))
        if candidate is None:
            raise RuntimeError("候选回归事务失败") from None
        candidate.regression_json = _stable_json(fallback)
        candidate.status = "regression_failed"
        candidate.update_time = datetime.now()
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise RuntimeError("候选回归事务失败") from None
    db.refresh(candidate)
    return candidate
