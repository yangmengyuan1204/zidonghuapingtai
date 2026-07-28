from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any, Dict

from sqlalchemy import case, func, or_, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from ..data_scripts.capabilities import (
    DataScriptCapability,
    capability_catalog,
    effective_contract_fields,
    is_sensitive_field_identifier,
)
from ..models import (
    DataAgentLearningSample,
    DataAgentRuleCandidate,
    DataAgentRuleReview,
    DataAgentRuleVersion,
)
from .data_agent_contracts import (
    apply_contract_updates,
    normalize_contract_field_value,
    normalize_execution_contract,
    problem_goods_operation,
    project_contract_goal,
    resolve_goal_capability,
)


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
MAX_SANITIZED_KEY_LENGTH = 240
MAX_SANITIZED_NODES = 500
MAX_SANITIZED_BYTES = 64_000
MAX_MATCH_PHRASES = 8
MAX_MATCH_PHRASE_LENGTH = 240
MAX_REGRESSION_IDS = 100
CANDIDATE_THRESHOLD = 3
CANDIDATE_RULE_REQUIRED_KEYS = {"signature", "field", "match_phrases", "source_count"}
CANDIDATE_RULE_KEYS = CANDIDATE_RULE_REQUIRED_KEYS | {
    "learning_mode",
    "learning_scope",
    "set_fields",
    "extract_pattern",
    "set_strategy",
}
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
LEARNING_MODES = {"value", "pattern", "strategy"}
LEARNING_METADATA_FIELD_MAP = {
    "problem_scope": "scope",
    "problem_refund_quantity": "quantity_refund_mode",
    "problem_refund_freight": "freight_refund_mode",
}
SAFE_CANDIDATE_KEY_EXCEPTIONS = {
    "account_role",
    "customer_ids",
    "profile_name",
}

_SENSITIVE_ASSIGNMENT_START = re.compile(
    rf"(?i)(?<![a-z0-9_])(后台密码|后台账号|密码|口令|令牌|凭据|"
    rf"password|passwd|pwd|access[_ -]?token|admin[_ -]?token|token|cookie|"
    rf"api[_ -]?key|secret|authorization|backend[_ -]?account|backend[_ -]?password|"
    rf"account[_ -]?ciphertext|browser[_ -]?state[_ -]?encrypted|sensitive[_ -]?variables)"
    rf"\s*(?::|=|是|为)\s*"
)
_BEARER_ASSIGNMENT = re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[^\s,;]+")


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(
        r"[^a-z0-9]+",
        "_",
        unicodedata.normalize("NFKC", str(key or "")).strip().casefold(),
    ).strip("_")
    return is_sensitive_field_identifier(key) or normalized.endswith(("_encrypted", "_ciphertext")) or normalized in SENSITIVE_KEYS or any(
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
    normalized = unicodedata.normalize("NFKC", value)
    redacted = _BEARER_ASSIGNMENT.sub("Authorization: ***", normalized)
    return _redact_sensitive_assignments(redacted)[:MAX_STRING_LENGTH]


def _budgeted_sanitized_text(value: Any, budget: dict, *, max_length: int) -> str:
    text_value = _sanitize_text(str(value))[:max_length]
    remaining = max(0, MAX_SANITIZED_BYTES - int(budget["bytes"]))
    encoded = text_value.encode("utf-8")
    if len(encoded) > remaining:
        text_value = encoded[:remaining].decode("utf-8", errors="ignore")
        encoded = text_value.encode("utf-8")
    budget["bytes"] += len(encoded)
    return text_value


def _claim_sanitized_node(budget: dict) -> bool:
    if int(budget["nodes"]) >= MAX_SANITIZED_NODES:
        return False
    budget["nodes"] += 1
    return True


def sanitize_learning_value(
    value: Any,
    key: str = "",
    *,
    _depth: int = 0,
    _budget: dict | None = None,
) -> Any:
    budget = _budget if _budget is not None else {"nodes": 0, "bytes": 0}
    if not _claim_sanitized_node(budget):
        return "..."
    if _sensitive_key(key):
        return _budgeted_sanitized_text("***", budget, max_length=MAX_STRING_LENGTH)
    if _depth >= MAX_DEPTH:
        return _budgeted_sanitized_text("...", budget, max_length=MAX_STRING_LENGTH)
    if isinstance(value, dict):
        result = {}
        for item_key, item in sorted(value.items(), key=lambda pair: str(pair[0]))[
            :MAX_DICT_ITEMS
        ]:
            if not _claim_sanitized_node(budget):
                break
            safe_key = _budgeted_sanitized_text(
                item_key, budget, max_length=MAX_SANITIZED_KEY_LENGTH
            )
            if not safe_key or int(budget["nodes"]) >= MAX_SANITIZED_NODES:
                break
            unique_key = safe_key
            collision = 2
            while unique_key in result:
                suffix = f"#{collision}"
                unique_key = f"{safe_key[:MAX_SANITIZED_KEY_LENGTH - len(suffix)]}{suffix}"
                collision += 1
            result[unique_key] = sanitize_learning_value(
                item,
                str(item_key),
                _depth=_depth + 1,
                _budget=budget,
            )
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for item in list(value)[:MAX_LIST_ITEMS]:
            if int(budget["nodes"]) >= MAX_SANITIZED_NODES:
                break
            result.append(
                sanitize_learning_value(item, key, _depth=_depth + 1, _budget=budget)
            )
        return result
    if isinstance(value, str):
        return _budgeted_sanitized_text(value, budget, max_length=MAX_STRING_LENGTH)
    if isinstance(value, (int, float, bool)) or value is None:
        encoded = str(value).encode("utf-8")
        remaining = max(0, MAX_SANITIZED_BYTES - int(budget["bytes"]))
        if len(encoded) > remaining:
            return _budgeted_sanitized_text(
                "...", budget, max_length=MAX_STRING_LENGTH
            )
        budget["bytes"] += len(encoded)
        return value
    return _budgeted_sanitized_text(value, budget, max_length=MAX_STRING_LENGTH)


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
    normalized = unicodedata.normalize("NFKC", str(key or "")).strip().casefold()
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


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
    if is_sensitive_field_identifier(key):
        return True
    normalized = _normalized_key(key)
    if (
        normalized in SAFE_CANDIDATE_KEY_EXCEPTIONS
        or normalized in _declared_learning_modes()
    ):
        return False
    parts = set(normalized.split("_"))
    return _sensitive_key(normalized) or normalized in FORBIDDEN_CANDIDATE_KEYS or bool(
        parts & {
            "permission",
            "threshold",
            "backend",
            "account",
            "password",
            "profile",
            "system",
            "url",
            "sql",
            "tool",
            "token",
            "cookie",
            "authorization",
            "secret",
            "browser",
            "ciphertext",
            "credential",
            "identity",
        }
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
    amounts = []
    if "amount" in value:
        amounts.append(value.get("amount"))
    if "amounts" in value:
        if not isinstance(value.get("amounts"), list):
            raise ValueError("pricing 候选逐项金额必须是列表")
        amounts.extend(value.get("amounts") or [])
    for amount in amounts:
        try:
            number = Decimal(str(amount).strip())
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("pricing 候选金额必须是非负数字") from exc
        if not number.is_finite() or number < 0:
            raise ValueError("pricing 候选金额必须是非负数字")


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


def _validate_identifier_pattern(field: str, pattern: Any) -> None:
    if not isinstance(pattern, dict) or set(pattern) != {"field", "kind", "aliases", "shapes"}:
        raise ValueError("标识符模式结构无效")
    if _normalized_key(pattern.get("field")) != field:
        raise ValueError("标识符模式字段不匹配")
    if pattern.get("kind") not in {"identifier", "list"}:
        raise ValueError("标识符模式类型无效")
    aliases = pattern.get("aliases")
    if not isinstance(aliases, list) or any(not isinstance(item, str) for item in aliases):
        raise ValueError("标识符模式别名无效")
    shapes = pattern.get("shapes")
    if not isinstance(shapes, list) or not shapes or len(shapes) > 8:
        raise ValueError("标识符模式形状无效")
    for shape in shapes:
        if not isinstance(shape, dict) or set(shape) != {"length", "pattern"}:
            raise ValueError("标识符模式形状无效")
        length = shape.get("length")
        shape_pattern = shape.get("pattern")
        if (
            isinstance(length, bool)
            or not isinstance(length, int)
            or length < 1
            or length > 240
            or not isinstance(shape_pattern, str)
            or not re.fullmatch(
                r"(?:D[1-9]\d{0,2}|A[1-9]\d{0,2}|P[0-9a-f]{2,32})(?:\|(?:D[1-9]\d{0,2}|A[1-9]\d{0,2}|P[0-9a-f]{2,32}))*",
                shape_pattern,
            )
        ):
            raise ValueError("标识符模式形状无效")


def _declared_learning_modes() -> dict[str, set[str]]:
    declared: dict[str, set[str]] = {}
    for capability in capability_catalog().values():
        for field in effective_contract_fields(capability):
            if field.learnable and field.learning_mode != "none":
                declared.setdefault(field.name, set()).add(field.learning_mode)
    declared.setdefault("pricing", set()).add("value")
    for public_name, metadata_name in LEARNING_METADATA_FIELD_MAP.items():
        modes = declared.get(metadata_name)
        if modes:
            declared.setdefault(public_name, set()).update(modes)
    return declared


def candidate_signature(rule: dict) -> str:
    field = _normalized_key(rule.get("field"))
    if isinstance(rule.get("set_fields"), dict):
        payload = rule["set_fields"].get(field)
    else:
        payload = next(
            (
                rule[key]
                for key in ("extract_pattern", "set_strategy")
                if key in rule
            ),
            None,
        )
    return _candidate_signature(field, _normalized_candidate_value(payload))


def validate_candidate_rule(rule: dict) -> dict:
    if not isinstance(rule, dict):
        raise ValueError("候选规则必须是对象")
    _reject_forbidden_candidate_keys(rule)
    unknown = sorted(set(rule) - CANDIDATE_RULE_KEYS)
    if unknown:
        raise ValueError(f"候选规则包含不允许字段：{', '.join(unknown)}")
    missing = sorted(CANDIDATE_RULE_REQUIRED_KEYS - set(rule))
    if missing:
        raise ValueError(f"候选规则缺少字段：{', '.join(missing)}")

    source_field = _normalized_key(rule.get("field"))
    field = REVISION_FIELD_MAP.get(source_field, source_field)
    declared_modes = _declared_learning_modes()
    if field not in declared_modes:
        raise ValueError(f"候选规则包含禁止字段：{field or 'field'}")
    if field in {"offer_price", "offer_unit_prices"}:
        raise ValueError("价格候选不允许绕过规范 pricing 字段")
    learning_mode = str(rule.get("learning_mode") or "").strip() or (
        next(iter(declared_modes[field])) if len(declared_modes[field]) == 1 else "value"
    )
    if learning_mode not in LEARNING_MODES or learning_mode not in declared_modes[field]:
        raise ValueError("候选规则 learning_mode 与字段元数据不一致")
    learning_scope = str(rule.get("learning_scope") or "project").strip()
    if learning_scope not in {"project", "global"}:
        raise ValueError("候选规则 learning_scope 不合法")
    if learning_mode in {"pattern", "strategy"} and learning_scope != "project":
        raise ValueError("该候选规则只允许项目范围")

    payload_keys = set(rule).intersection({"set_fields", "extract_pattern", "set_strategy"})
    expected_payload_key = {
        "value": "set_fields",
        "pattern": "extract_pattern",
        "strategy": "set_strategy",
    }[learning_mode]
    if payload_keys != {expected_payload_key}:
        raise ValueError(f"候选规则 {learning_mode} 模式负载不合法")
    safe_payload = _normalized_candidate_value(rule[expected_payload_key])
    if learning_mode == "value":
        if not isinstance(safe_payload, dict) or len(safe_payload) != 1:
            raise ValueError("候选规则 set_fields 只允许当前规范字段")
        raw_set_field, safe_value = next(iter(safe_payload.items()))
        source_set_field = _normalized_key(raw_set_field)
        set_field = REVISION_FIELD_MAP.get(source_set_field, source_set_field)
        if set_field != field:
            raise ValueError("候选规则 set_fields 只允许当前规范字段")
        if isinstance(safe_value, dict) and field != "pricing":
            raise ValueError(f"候选规则字段不允许嵌套对象：{field}")
        if field == "pricing":
            _validate_pricing_value(safe_value)
        _validate_overlay_value(field, safe_value)
        safe_payload = {field: safe_value}
    elif learning_mode == "pattern":
        if not isinstance(safe_payload, dict) or not safe_payload:
            raise ValueError("候选规则 extract_pattern 必须是对象")
        _validate_identifier_pattern(field, safe_payload)
    elif learning_mode == "strategy":
        declared_specs = [
            declared_field
            for capability in capability_catalog().values()
            for declared_field in effective_contract_fields(capability)
            if declared_field.name == field
            and declared_field.learnable
            and declared_field.learning_mode == learning_mode
        ]
        if any(spec.value_type == "dict" for spec in declared_specs) and (
            not isinstance(safe_payload, dict) or not safe_payload
        ):
            raise ValueError("账号策略候选必须包含安全档案策略")
        if field == "permission_account_strategy":
            if not isinstance(safe_payload, dict) or set(safe_payload) != {
                "profile_name",
                "role",
            }:
                raise ValueError("账号策略只允许 profile_name 和 role")
            safe_payload = {
                "profile_name": str(safe_payload.get("profile_name") or "").strip(),
                "role": str(safe_payload.get("role") or "").strip(),
            }
            if not all(safe_payload.values()):
                raise ValueError("账号策略 profile_name 和 role 不能为空")

    signature = str(rule.get("signature") or "").strip()
    if learning_mode == "value":
        safe_value = safe_payload[field]
        if signature != _candidate_signature(field, safe_value):
            raise ValueError("候选规则 signature 不是规范 field/after 摘要")
    elif not re.fullmatch(rf"{re.escape(field)}:[0-9a-f]{{16}}", signature):
        raise ValueError("候选规则 signature 格式无效")
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
    validated = {
        "signature": signature,
        "field": field,
        "learning_mode": learning_mode,
        "learning_scope": learning_scope,
        "match_phrases": safe_phrases,
        "source_count": source_count,
    }
    validated[expected_payload_key] = safe_payload
    return validated


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


def _bigrams(value: Any) -> set[str]:
    text_value = re.sub(
        r"[\s，。；：、,.!?！？]+",
        "",
        unicodedata.normalize("NFKC", str(value or "")).casefold(),
    )
    if len(text_value) < 2:
        return {text_value} if text_value else set()
    return {
        text_value[index : index + 2]
        for index in range(len(text_value) - 1)
    }


def _similarity(left: Any, right: Any) -> float:
    left_tokens = _bigrams(left)
    right_tokens = _bigrams(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _rule_similarity(rule: dict, instruction: str) -> float:
    return max(
        (_similarity(instruction, phrase) for phrase in rule.get("match_phrases") or []),
        default=0.0,
    )


def learning_context(
    db: Session,
    project_id: int,
    module_key: str,
    instruction: str,
    limit: int = 5,
) -> dict:
    """Return bounded, sanitized, approved learning knowledge for one instruction."""
    bounded_limit = max(1, min(int(limit or 5), 5))
    safe_module = str(module_key or "")[:80]
    safe_instruction = str(sanitize_learning_value(instruction or ""))
    rows = (
        db.query(DataAgentRuleVersion, DataAgentRuleCandidate)
        .join(
            DataAgentRuleCandidate,
            DataAgentRuleCandidate.id == DataAgentRuleVersion.candidate_id,
        )
        .filter(
            DataAgentRuleVersion.status == "active",
            DataAgentRuleCandidate.module_key == safe_module,
            or_(
                (
                    (DataAgentRuleVersion.scope == "project")
                    & (DataAgentRuleVersion.project_id == int(project_id))
                ),
                (
                    (DataAgentRuleVersion.scope == "global")
                    & (DataAgentRuleVersion.project_id == 0)
                ),
            ),
        )
        .all()
    )
    ranked_rules: list[tuple[int, float, int, dict]] = []
    for version, candidate in rows:
        try:
            rule = validate_candidate_rule(_load_json_object(version.rule_json))
        except (TypeError, ValueError):
            continue
        similarity = _rule_similarity(rule, safe_instruction)
        if not candidate_matches_instruction(rule, safe_instruction) and similarity < 0.6:
            continue
        ranked_rules.append(
            (
                0 if version.scope == "project" else 1,
                -similarity,
                int(version.id),
                {
                    "id": int(version.id),
                    "scope": str(version.scope),
                    "module_key": str(candidate.module_key),
                    "rule_key": str(version.rule_key),
                    "version": int(version.version),
                    "similarity": round(similarity, 6),
                    "rule": sanitize_learning_value(rule),
                },
            )
        )
    ranked_rules.sort(key=lambda item: item[:3])

    samples = (
        db.query(DataAgentLearningSample)
        .filter(
            DataAgentLearningSample.project_id == int(project_id),
            DataAgentLearningSample.module_key == safe_module,
            DataAgentLearningSample.outcome.in_({"verified", "success"}),
            DataAgentLearningSample.verified == 1,
        )
        .order_by(DataAgentLearningSample.id.desc())
        .limit(100)
        .all()
    )
    ranked_examples: list[tuple[float, int, dict]] = []
    for sample in samples:
        similarity = _similarity(safe_instruction, sample.instruction_text)
        if similarity <= 0:
            continue
        try:
            final_contract = _load_json_object(sample.final_contract_json)
        except (TypeError, ValueError):
            continue
        ranked_examples.append(
            (
                -similarity,
                -int(sample.id),
                {
                    "id": int(sample.id),
                    "instruction": sanitize_learning_value(sample.instruction_text or ""),
                    "final_contract": sanitize_learning_value(final_contract),
                    "similarity": round(similarity, 6),
                },
            )
        )
    ranked_examples.sort(key=lambda item: item[:2])
    return {
        "module_key": safe_module,
        "rules": [item[3] for item in ranked_rules[:bounded_limit]],
        "examples": [item[2] for item in ranked_examples[:bounded_limit]],
    }


def apply_learning_context(
    goal: dict,
    context: dict,
    hard_fields: set[str] | None = None,
    capability: DataScriptCapability | None = None,
) -> dict:
    """Apply approved overlays while preserving explicit and deterministic fields."""
    result = copy.deepcopy(goal)
    protected = set(hard_fields or set())
    allowed_fields: set[str] | None = None
    contract_value_fields: set[str] = set()
    contract_strategy_fields: set[str] = set()
    if capability is not None:
        contract_value_fields = {
            field.name
            for field in effective_contract_fields(capability)
            if not field.readonly
            and field.learnable
            and field.learning_mode == "value"
        }
        contract_strategy_fields = {
            field.name
            for field in effective_contract_fields(capability)
            if field.readonly
            and field.learnable
            and field.learning_mode == "strategy"
        }
        allowed_fields = set(contract_value_fields).union(contract_strategy_fields)
        if contract_value_fields.intersection({"offer_price", "offer_unit_prices"}):
            allowed_fields.add("pricing")
        allowed_fields.update(
            public_name
            for public_name, metadata_name in LEARNING_METADATA_FIELD_MAP.items()
            if metadata_name in contract_value_fields
        )
    applied: list[dict] = []
    for item in context.get("rules") or []:
        if not isinstance(item, dict) or not isinstance(item.get("rule"), dict):
            continue
        try:
            rule = validate_candidate_rule(copy.deepcopy(item["rule"]))
        except (TypeError, ValueError):
            continue
        field = str(rule["field"])
        if field in protected or (
            allowed_fields is not None and field not in allowed_fields
        ):
            continue
        try:
            if capability is not None and field in contract_value_fields:
                result, _ = apply_contract_updates(
                    result,
                    {field: copy.deepcopy(rule["set_fields"][field])},
                    capability,
                )
            elif capability is not None and field in contract_strategy_fields:
                variables = result.get("variables")
                if not isinstance(variables, dict):
                    variables = {}
                    result["variables"] = variables
                variables[field] = copy.deepcopy(rule["set_strategy"])
            else:
                result = apply_candidate_overlay(result, rule)
        except (TypeError, ValueError):
            continue
        protected.add(field)
        applied.append(
            {
                "field": field,
                "scope": str(item.get("scope") or ""),
                "rule_version_id": int(item.get("id") or 0),
            }
        )
    if applied:
        result["learning_applied"] = sanitize_learning_value(applied)
    return result


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


def apply_candidate_overlay(goal: dict, proposal: dict) -> dict:
    if not isinstance(goal, dict):
        raise ValueError("候选 overlay 目标合同必须是对象")
    validated = validate_candidate_rule(copy.deepcopy(proposal))
    if validated["learning_mode"] != "value":
        raise ValueError("pattern/strategy 候选不直接覆盖合同")
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
        operation = problem_goods_operation(overlaid)
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


def identifier_shape(value: Any, field: str) -> dict:
    def shape_one(item: Any) -> dict:
        text_value = unicodedata.normalize("NFKC", str(item or "").strip())
        segments: list[str] = []
        for token in re.findall(r"\d+|[A-Za-z]+|[^\dA-Za-z]+", text_value):
            if token.isdigit():
                segments.append(f"D{len(token)}")
            elif token.isalpha() and token.isascii():
                segments.append(f"A{len(token)}")
            else:
                safe_literal = re.sub(r"[\w\u4e00-\u9fff]+", "", token)
                if safe_literal:
                    segments.append(f"P{safe_literal[:16].encode('utf-8').hex()}")
        return {"pattern": "|".join(segments), "length": len(text_value)}

    values = value if isinstance(value, (list, tuple)) else [value]
    shapes = [shape_one(item) for item in values if str(item or "").strip()]
    if not shapes:
        raise ValueError("标识符模式缺少有效样本")
    return {
        "field": _normalized_key(field),
        "kind": "list" if isinstance(value, (list, tuple)) else "identifier",
        "shapes": shapes[:8],
    }


def _instruction_phrases(
    instruction: Any,
    aliases: Any,
    redacted_values: Any = None,
) -> list[str]:
    safe_instruction = str(sanitize_learning_value(instruction or "")).strip()
    values = redacted_values if isinstance(redacted_values, (list, tuple)) else [redacted_values]
    for value in values:
        text_value = str(value or "").strip()
        if text_value:
            safe_instruction = safe_instruction.replace(text_value, "[标识符]")
    phrases = [
        str(sanitize_learning_value(alias)).strip()
        for alias in list(aliases or [])
        if str(alias or "").strip()
    ]
    if safe_instruction:
        phrases.append(safe_instruction)
    return sorted(set(phrases))[:MAX_MATCH_PHRASES]


def _metadata_path_value(contract: Any, path: str) -> Any:
    current = contract
    for part in str(path or "").split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _identifier_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [item for nested in value for item in _identifier_values(nested)]
    text_value = str(value or "").strip()
    return [text_value] if text_value else []


def _sample_pattern_identifier_values(
    sample: DataAgentLearningSample,
    contract_fields: Any,
) -> list[str]:
    pattern_fields = {
        field.name: field
        for field in contract_fields
        if field.learnable and field.learning_mode == "pattern"
    }
    values: set[str] = set()
    for raw_contract in (sample.initial_contract_json, sample.final_contract_json):
        try:
            contract = json.loads(raw_contract or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        for field in pattern_fields.values():
            values.update(_identifier_values(_metadata_path_value(contract, field.path)))
    try:
        corrections = json.loads(sample.corrections_json or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        corrections = []
    for correction in corrections if isinstance(corrections, list) else []:
        if not isinstance(correction, dict):
            continue
        field_name = REVISION_FIELD_MAP.get(
            _normalized_key(correction.get("field")),
            _normalized_key(correction.get("field")),
        )
        if field_name not in pattern_fields:
            continue
        values.update(_identifier_values(correction.get("before")))
        values.update(_identifier_values(correction.get("after")))
    return sorted(values, key=lambda item: (-len(item), item))


def _sample_capability(sample: DataAgentLearningSample):
    capability_key = resolve_goal_capability(
        {},
        module_key=sample.module_key,
        intent_key=sample.intent_key,
    )
    return capability_catalog().get(capability_key)


def _resolve_correction_field(
    contract_fields: Any,
    source_field: str,
    raw_after: Any,
) -> tuple[Any, str, Any]:
    metadata_field = LEARNING_METADATA_FIELD_MAP.get(source_field, source_field)
    field = next((item for item in contract_fields if item.name == metadata_field), None)
    proposal_field = source_field
    proposal_after = raw_after
    if source_field == "pricing":
        mode = str((raw_after if isinstance(raw_after, dict) else {}).get("mode") or "")
        metadata_name = "offer_unit_prices" if mode == "per_item_unit" else "offer_price"
        field = next((item for item in contract_fields if item.name == metadata_name), None)
        if field is None and metadata_name == "offer_unit_prices":
            field = next((item for item in contract_fields if item.name == "offer_price"), None)
    elif source_field == "offer_price":
        proposal_field = "pricing"
        proposal_after = {"mode": "uniform_unit", "amount": raw_after}
    elif source_field == "offer_unit_prices":
        if field is None:
            field = next((item for item in contract_fields if item.name == "offer_price"), None)
        proposal_field = "pricing"
        proposal_after = {"mode": "per_item_unit", "amounts": raw_after}
    return field, proposal_field, proposal_after


def correction_rule_proposal(
    sample: DataAgentLearningSample,
    correction: dict,
) -> dict:
    if not isinstance(correction, dict):
        raise ValueError("纠正样本必须是对象")
    capability = _sample_capability(sample)
    source_field = REVISION_FIELD_MAP.get(
        _normalized_key(correction.get("field")),
        _normalized_key(correction.get("field")),
    )
    contract_fields = effective_contract_fields(capability) if capability else ()
    raw_after = _normalized_candidate_value(correction.get("after"))
    field, proposal_field, proposal_after = _resolve_correction_field(
        contract_fields,
        source_field,
        raw_after,
    )
    if field is None or not field.learnable or field.learning_mode == "none":
        raise ValueError("字段未声明为可学习")

    learning_mode = "value" if proposal_field == "pricing" else field.learning_mode
    redacted_values = _sample_pattern_identifier_values(sample, contract_fields)
    if learning_mode == "pattern":
        redacted_values.extend(_identifier_values(raw_after))
    base = {
        "field": proposal_field,
        "learning_mode": learning_mode,
        "learning_scope": field.learning_scope,
        "match_phrases": _instruction_phrases(
            sample.instruction_text,
            field.aliases,
            redacted_values,
        ),
        "source_count": 1,
    }
    if learning_mode == "pattern":
        base["extract_pattern"] = {
            **identifier_shape(raw_after, field.name),
            "aliases": sorted(set(field.aliases)),
        }
    elif learning_mode == "strategy":
        base["set_strategy"] = sanitize_learning_value(raw_after)
    else:
        base["set_fields"] = {proposal_field: sanitize_learning_value(proposal_after)}
    base["signature"] = candidate_signature(base)
    return validate_candidate_rule(base)


def _normalized_correction(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    source_field = _normalized_key(item.get("field"))
    field = REVISION_FIELD_MAP.get(source_field, source_field)
    if not field:
        return None
    if _forbidden_candidate_key(source_field):
        raise ValueError(f"候选规则包含禁止字段：{source_field or 'field'}")
    raw_after = _normalized_candidate_value(item.get("after"))
    raw_before = _normalized_candidate_value(item.get("before"))
    if raw_after is None or raw_before == raw_after:
        return None
    return {"field": field, "before": raw_before, "after": raw_after}


def _sample_corrections(sample: DataAgentLearningSample) -> list[dict]:
    try:
        raw = json.loads(sample.corrections_json or "[]")
    except (TypeError, ValueError):
        return []
    proposals: list[dict] = []
    for item in raw:
        normalized = _normalized_correction(item)
        if normalized is None:
            continue
        try:
            proposals.append(correction_rule_proposal(sample, normalized))
        except ValueError:
            capability = _sample_capability(sample)
            contract_fields = effective_contract_fields(capability) if capability else ()
            declared_field, _, _ = _resolve_correction_field(
                contract_fields,
                normalized.get("field"),
                normalized.get("after"),
            )
            if (
                _forbidden_candidate_key(normalized.get("field"))
                or (
                    declared_field is not None
                    and declared_field.learnable
                    and declared_field.learning_mode != "none"
                )
            ):
                raise
    return proposals


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
    matching_rules: list[dict] = []
    matched_rule: dict | None = None
    samples = (
        db.query(DataAgentLearningSample)
        .filter(
            DataAgentLearningSample.project_id == int(project_id),
            DataAgentLearningSample.module_key == str(module_key),
            DataAgentLearningSample.intent_key == str(intent_key),
            DataAgentLearningSample.outcome.in_({"verified", "success"}),
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
            matching_rules.append(matched_rule)
    if not matching_samples or matched_rule is None:
        raise ValueError("没有匹配的已验证纠正样本")

    source_ids = sorted({int(sample.id) for sample in matching_samples})
    phrases = sorted(
        {
            str(sanitize_learning_value(phrase)).strip()[:MAX_MATCH_PHRASE_LENGTH]
            for rule in matching_rules
            for phrase in rule.get("match_phrases") or []
            if str(phrase or "").strip()
        }
    )[:MAX_MATCH_PHRASES]
    proposal_input = copy.deepcopy(matched_rule)
    proposal_input["match_phrases"] = phrases
    proposal_input["source_count"] = len(source_ids)
    proposal = validate_candidate_rule(proposal_input)
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
    if (
        sample is None
        or sample.outcome not in {"verified", "success"}
        or int(sample.verified or 0) != 1
    ):
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
        if not isinstance(event, dict):
            continue
        if event.get("kind") == "permission_profile_selected":
            strategy = event.get("strategy")
            if isinstance(strategy, dict) and set(strategy) == {"profile_name", "role"}:
                safe_strategy = {
                    "profile_name": str(strategy.get("profile_name") or "").strip(),
                    "role": str(strategy.get("role") or "").strip(),
                }
                if all(safe_strategy.values()):
                    corrections.append(
                        {
                            "field": "permission_account_strategy",
                            "before": {},
                            "after": safe_strategy,
                            "source": "manual_profile_selection",
                        }
                    )
            continue
        if event.get("kind") != "goal_updated":
            continue
        for item in event.get("corrections") or []:
            if not isinstance(item, dict):
                continue
            field = _normalized_key(item.get("field"))
            if not field or _sensitive_key(field):
                continue
            corrections.append(
                {
                    "field": field,
                    "before": item.get("before"),
                    "after": item.get("after"),
                    "source": str(item.get("source") or "direct_edit"),
                }
            )
    intent_state = getattr(session, "intent_state", None)
    intent_state = intent_state if isinstance(intent_state, dict) else {}
    for item in intent_state.get("revisions") or []:
        if not isinstance(item, dict):
            continue
        source_field = str(item.get("field") or "")
        field = REVISION_FIELD_MAP.get(source_field, source_field)
        if not field or _sensitive_key(field):
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
        isinstance(event, dict)
        and event.get("kind") in {"confirmation", "risk_confirmed"}
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
    capability_key = resolve_goal_capability(goal)
    capability = capability_catalog().get(capability_key)
    if capability is None:
        raise LearningInputError("合同能力未声明，无法生成规范学习指纹")
    mode = str(goal.get("mode") or "").strip()
    intent_key = str(goal.get("capability_key") or "").strip()
    if not intent_key:
        if capability_key == "problem_goods":
            intent_key = capability_key
        else:
            intent_key = "create" if mode == "new" else mode or capability_key
    return capability.module[:80], intent_key[:120]


def _learning_sample_values(session: Any) -> dict:
    goal = getattr(session, "goal", None)
    if not isinstance(goal, dict) or not goal:
        raise LearningInputError("合同缺少可学习目标")
    messages = list(getattr(session, "messages", None) or [])
    instruction = next(
        (
            str(message.get("content") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "user"
        ),
        "",
    )
    safe_instruction = sanitize_learning_value(instruction)
    safe_final_contract = sanitize_learning_value(goal)
    initial_contract = getattr(session, "initial_contract", None)
    safe_initial_contract = sanitize_learning_value(
        initial_contract if isinstance(initial_contract, dict) else {}
    )
    module_key, intent_key = _sample_scope(goal)
    capability = capability_catalog().get(resolve_goal_capability(goal))
    if capability is None:
        raise LearningInputError("合同能力未声明，无法生成规范学习指纹")
    try:
        execution_contract = normalize_execution_contract(
            project_contract_goal(goal, capability),
            capability,
        )
    except ValueError as exc:
        raise LearningInputError("合同无法生成规范学习指纹") from exc
    canonical_contract = {
        "capability_key": capability.key,
        "execution_contract": execution_contract,
    }
    return {
        "project_id": int(session.project_id),
        "session_id": str(session.id)[:64],
        "module_key": module_key,
        "intent_key": intent_key,
        "instruction_text": str(safe_instruction),
        "model_candidate_json": "{}",
        "initial_contract_json": json.dumps(
            safe_initial_contract, ensure_ascii=False, sort_keys=True, default=str
        ),
        "final_contract_json": json.dumps(
            safe_final_contract, ensure_ascii=False, sort_keys=True, default=str
        ),
        "corrections_json": json.dumps(
            _corrections(session), ensure_ascii=False, sort_keys=True, default=str
        ),
        "fingerprint": sample_fingerprint(
            int(session.project_id), "", canonical_contract
        ),
    }


def _upsert_session_sample(
    db: Session,
    session: Any,
) -> tuple[DataAgentLearningSample, bool]:
    values = _learning_sample_values(session)
    session_sample = (
        db.query(DataAgentLearningSample)
        .filter(
            DataAgentLearningSample.project_id == values["project_id"],
            DataAgentLearningSample.session_id == values["session_id"],
        )
        .first()
    )
    if session_sample is not None:
        previous_fingerprint = str(session_sample.fingerprint or "")
        fingerprint_owner = (
            db.query(DataAgentLearningSample)
            .filter(DataAgentLearningSample.fingerprint == values["fingerprint"])
            .first()
        )
        if fingerprint_owner not in {None, session_sample}:
            values["fingerprint"] = hashlib.sha256(
                (
                    f'{values["fingerprint"]}:{values["project_id"]}:'
                    f'{values["session_id"]}'
                ).encode("utf-8")
            ).hexdigest()
        for key, value in values.items():
            if key in {"project_id", "session_id"}:
                continue
            setattr(session_sample, key, value)
        return session_sample, previous_fingerprint != values["fingerprint"]
    sample = (
        db.query(DataAgentLearningSample)
        .filter(DataAgentLearningSample.fingerprint == values["fingerprint"])
        .first()
    )
    if sample is not None:
        values["fingerprint"] = hashlib.sha256(
            (
                f'{values["fingerprint"]}:{values["project_id"]}:'
                f'{values["session_id"]}'
            ).encode("utf-8")
        ).hexdigest()
    sample = DataAgentLearningSample(
        **values,
        outcome="pending",
        verified=0,
        create_time=datetime.now(),
    )
    db.add(sample)
    return sample, True


def _transition_sample_outcome(
    sample: DataAgentLearningSample,
    requested_outcome: str,
    contract_changed: bool,
) -> None:
    if requested_outcome not in {"pending", "verified", "invalid"}:
        raise LearningInputError("学习样本状态无效")
    if requested_outcome == "invalid":
        sample.outcome = "invalid"
        sample.verified = 0
        return
    if not contract_changed and sample.outcome == "invalid":
        sample.verified = 0
        return
    if (
        not contract_changed
        and sample.outcome in {"verified", "success"}
        and int(sample.verified or 0) == 1
    ):
        return
    sample.outcome = requested_outcome
    sample.verified = 1 if requested_outcome == "verified" else 0


def record_contract_feedback(
    db: Session,
    session: Any,
    verdict: str,
) -> DataAgentLearningSample:
    if verdict not in {"correct", "invalid"}:
        raise LearningInputError("合同反馈无效")
    sample, contract_changed = _upsert_session_sample(db, session)
    _transition_sample_outcome(
        sample,
        "pending" if verdict == "correct" else "invalid",
        contract_changed,
    )
    db.commit()
    db.refresh(sample)
    return sample


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
    sample, contract_changed = _upsert_session_sample(db, session)
    verified = bool(
        final_status == "succeeded"
        and _confirmed(session)
        and _operations_verified(session, result if isinstance(result, dict) else {})
    )
    _transition_sample_outcome(
        sample,
        "verified" if verified else "pending",
        contract_changed,
    )
    db.commit()
    db.refresh(sample)
    if sample.outcome in {"verified", "success"} and int(sample.verified or 0) == 1 and _load_json_list(sample.corrections_json):
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
        operation = problem_goods_operation(goal) if field in PROBLEM_OVERLAY_FIELDS else None
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
        return field in variables and problem_goods_operation(goal) is not None
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
            DataAgentLearningSample.outcome.in_({"verified", "success"}),
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
    learning_mode = proposal["learning_mode"]
    proposal_after = (
        _normalized_candidate_value(proposal["set_fields"][proposal["field"]])
        if learning_mode == "value"
        else None
    )

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
            if (
                learning_mode == "value"
                and candidate_matches_instruction(proposal, str(case.get("instruction") or ""))
            ):
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
            if learning_mode != "value":
                if sample_id in source_id_set:
                    sample_signatures = {
                        item["signature"] for item in _sample_corrections(sample)
                    }
                    if proposal["signature"] not in sample_signatures:
                        summary["conflict_sample_ids"].append(sample_id)
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

    snapshot = {
        "id": int(candidate.id),
        "project_id": int(candidate.project_id),
        "proposal_json": str(candidate.proposal_json),
        "source_sample_ids_json": str(candidate.source_sample_ids_json),
        "occurrence_count": int(candidate.occurrence_count or 0),
    }
    evaluation_candidate = SimpleNamespace(**snapshot)
    db.rollback()

    try:
        summary = evaluate_candidate(db, evaluation_candidate)
    except Exception:
        summary = _regression_summary(fixture_total=0, historical_total=0)
        _add_error_code(summary, "regression_exception")
        summary = _finish_summary(summary)
    result_status = "pending_review" if regression_passed(summary) else "regression_failed"
    result_json = _stable_json(summary)
    db.rollback()

    def persist_if_snapshot_matches(status: str, regression_json: str) -> int:
        return (
            db.query(DataAgentRuleCandidate)
            .filter(
                DataAgentRuleCandidate.id == snapshot["id"],
                DataAgentRuleCandidate.status == "pending_regression",
                DataAgentRuleCandidate.proposal_json == snapshot["proposal_json"],
                DataAgentRuleCandidate.source_sample_ids_json
                == snapshot["source_sample_ids_json"],
                DataAgentRuleCandidate.occurrence_count == snapshot["occurrence_count"],
            )
            .update(
                {
                    DataAgentRuleCandidate.regression_json: regression_json,
                    DataAgentRuleCandidate.status: status,
                    DataAgentRuleCandidate.update_time: datetime.now(),
                },
                synchronize_session=False,
            )
        )

    try:
        if persist_if_snapshot_matches(result_status, result_json) != 1:
            db.rollback()
            current = db.get(DataAgentRuleCandidate, snapshot["id"])
            if current is None:
                raise RuntimeError("候选回归事务失败") from None
            return current
        db.commit()
    except Exception:
        db.rollback()
        fallback = _transaction_failure_summary(summary)
        try:
            if persist_if_snapshot_matches("regression_failed", _stable_json(fallback)) != 1:
                db.rollback()
                current = db.get(DataAgentRuleCandidate, snapshot["id"])
                if current is None:
                    raise RuntimeError("候选回归事务失败") from None
                return current
            db.commit()
        except Exception:
            db.rollback()
            raise RuntimeError("候选回归事务失败") from None
    candidate = db.get(DataAgentRuleCandidate, snapshot["id"])
    if candidate is None:
        raise RuntimeError("候选回归事务失败") from None
    db.refresh(candidate)
    return candidate


class LearningNotFoundError(ValueError):
    pass


class LearningConflictError(ValueError):
    pass


class LearningInputError(ValueError):
    pass


def _safe_json_value(value: str, default: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        parsed = default
    return sanitize_learning_value(parsed)


def _safe_reason(reason: str) -> str:
    raw = str(reason or "").strip()
    if not raw or len(raw) > 1000:
        raise LearningInputError("审核原因不能为空且不能超过 1000 字符")
    return str(sanitize_learning_value(raw)).strip()


def _safe_metadata(value: Any) -> str:
    return str(sanitize_learning_value(str(value or "")))


def _serialize_candidate(candidate: DataAgentRuleCandidate) -> dict:
    source_ids = _safe_json_value(candidate.source_sample_ids_json, [])
    return {
        "id": int(candidate.id),
        "project_id": int(candidate.project_id),
        "module_key": _safe_metadata(candidate.module_key),
        "intent_key": _safe_metadata(candidate.intent_key),
        "rule_key": _safe_metadata(candidate.rule_key),
        "proposal": _safe_json_value(candidate.proposal_json, {}),
        "source_sample_ids": source_ids if isinstance(source_ids, list) else [],
        "occurrence_count": int(candidate.occurrence_count or 0),
        "regression": _safe_json_value(candidate.regression_json, {}),
        "status": _safe_metadata(candidate.status),
        "create_time": candidate.create_time.isoformat() if candidate.create_time else None,
        "update_time": candidate.update_time.isoformat() if candidate.update_time else None,
    }


def _serialize_rule(rule: DataAgentRuleVersion) -> dict:
    return {
        "id": int(rule.id),
        "candidate_id": int(rule.candidate_id),
        "project_id": int(rule.project_id),
        "scope": _safe_metadata(rule.scope),
        "rule_key": _safe_metadata(rule.rule_key),
        "version": int(rule.version),
        "rule": _safe_json_value(rule.rule_json, {}),
        "status": _safe_metadata(rule.status),
        "create_time": rule.create_time.isoformat() if rule.create_time else None,
        "activated_at": rule.activated_at.isoformat() if rule.activated_at else None,
    }


def _serialize_review(review: DataAgentRuleReview) -> dict:
    return {
        "id": int(review.id),
        "candidate_id": int(review.candidate_id),
        "rule_version_id": int(review.rule_version_id) if review.rule_version_id else None,
        "user_id": int(review.user_id),
        "action": _safe_metadata(review.action),
        "reason": sanitize_learning_value(review.reason or ""),
        "create_time": review.create_time.isoformat() if review.create_time else None,
    }


def _normalized_sample_status(sample: DataAgentLearningSample) -> str:
    outcome = str(sample.outcome or "").strip().lower()
    return {"success": "verified", "failure": "pending"}.get(outcome, outcome)


def _sample_contracts(
    sample: DataAgentLearningSample,
) -> tuple[dict, dict, str, str, DataScriptCapability | None, list[str]]:
    issues = []
    try:
        initial = _load_json_object(sample.initial_contract_json)
    except (TypeError, ValueError):
        initial = {}
        issues.append("invalid_initial_contract")
    try:
        final = _load_json_object(sample.final_contract_json)
    except (TypeError, ValueError):
        final = {}
        issues.append("invalid_final_contract")
    catalog = capability_catalog()
    initial_key = resolve_goal_capability(
        initial,
        module_key=sample.module_key,
        intent_key=sample.intent_key,
    )
    final_key = resolve_goal_capability(
        final,
        module_key=sample.module_key,
        intent_key=sample.intent_key,
    )
    capability = catalog.get(final_key) if initial_key == final_key else None
    return initial, final, initial_key, final_key, capability, issues


_DISPLAY_ONLY_CONTRACT_KEYS = {
    "assumptions",
    "contract_editor",
    "evidence",
    "field_sources",
    "inferred_fields",
    "plan_version",
    "source_text",
    "summary",
}


def _generic_execution_contract(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized_key = _normalized_key(key)
            if (
                _sensitive_key(normalized_key)
                or normalized_key in {"credential", "credentials"}
                or normalized_key in _DISPLAY_ONLY_CONTRACT_KEYS
                or normalized_key.endswith("_label")
            ):
                continue
            result[str(key)] = _generic_execution_contract(item)
        return result
    if isinstance(value, list):
        return [_generic_execution_contract(item) for item in value]
    return sanitize_learning_value(value)


def _normalized_execution_correction_value(
    field: str,
    value: Any,
    capability: DataScriptCapability | None,
) -> Any:
    revision_value = _revision_value(value)
    if field == "pricing":
        normalized = _normalized_candidate_value(revision_value)
        _validate_pricing_value(normalized)
        return normalized
    if capability is None:
        return _normalized_candidate_value(revision_value)
    metadata_field = LEARNING_METADATA_FIELD_MAP.get(field, field)
    return normalize_contract_field_value(capability, metadata_field, revision_value)


def _execution_corrections(
    value: Any,
    capability: DataScriptCapability | None,
) -> tuple[list[dict], list[str]]:
    corrections = value if isinstance(value, list) else []
    allowed_fields = set(LEARNABLE_FIELDS)
    if capability is not None:
        allowed_fields.update(
            field.name
            for field in effective_contract_fields(capability)
            if field.execution_field
        )
    result = []
    issues = []
    for item in corrections:
        if not isinstance(item, dict):
            issues.append("invalid_corrections")
            continue
        source_field = _normalized_key(item.get("field"))
        field = REVISION_FIELD_MAP.get(source_field, source_field)
        if (
            not field
            or _sensitive_key(source_field)
            or field not in allowed_fields
        ):
            continue
        try:
            before = _normalized_execution_correction_value(
                field, item.get("before"), capability
            )
            after = _normalized_execution_correction_value(
                field, item.get("after"), capability
            )
        except (TypeError, ValueError):
            issues.append("invalid_correction_value")
            continue
        if before == after:
            continue
        result.append(
            sanitize_learning_value(
                {
                    "field": field,
                    "before": before,
                    "after": after,
                    "source": str(item.get("source") or "direct_edit"),
                }
            )
        )
    return result, issues


def _analyze_learning_sample(sample: DataAgentLearningSample) -> dict:
    initial, final, initial_key, final_key, capability, issues = _sample_contracts(sample)
    try:
        raw_corrections = _load_json_list(sample.corrections_json)
    except (TypeError, ValueError):
        raw_corrections = []
        issues.append("invalid_corrections")
    corrections, correction_issues = _execution_corrections(
        raw_corrections, capability
    )
    issues.extend(correction_issues)
    contracts_match = False
    if initial_key != final_key:
        contracts_match = False
    elif capability is not None:
        try:
            normalized_initial = normalize_execution_contract(
                project_contract_goal(initial, capability), capability
            )
            normalized_final = normalize_execution_contract(
                project_contract_goal(final, capability), capability
            )
            contracts_match = normalized_initial == normalized_final
        except (TypeError, ValueError):
            issues.append("invalid_execution_contract")
    else:
        contracts_match = _generic_execution_contract(
            initial
        ) == _generic_execution_contract(final)
    status_value = _normalized_sample_status(sample)
    data_quality_issues = sorted(set(issues))
    return {
        "initial": initial,
        "final": final,
        "corrections": corrections,
        "status": status_value,
        "first_hit": bool(
            not data_quality_issues and contracts_match and not corrections
        ),
        "data_quality": "invalid" if data_quality_issues else "valid",
        "data_quality_issues": data_quality_issues,
    }


def _learning_metric_sample(sample: DataAgentLearningSample) -> dict:
    analysis = _analyze_learning_sample(sample)
    return {
        "script_key": _safe_metadata(sample.intent_key),
        "corrections": analysis["corrections"],
        "status": _safe_metadata(analysis["status"]),
        "first_hit": analysis["first_hit"],
        "data_quality": analysis["data_quality"],
    }


def serialize_learning_sample(sample: DataAgentLearningSample) -> dict:
    analysis = _analyze_learning_sample(sample)
    return {
        "id": int(sample.id),
        "project_id": int(sample.project_id),
        "session_id": _safe_metadata(sample.session_id),
        "module_key": _safe_metadata(sample.module_key),
        "script_key": _safe_metadata(sample.intent_key),
        "instruction": sanitize_learning_value(sample.instruction_text or ""),
        "initial_contract": sanitize_learning_value(analysis["initial"]),
        "final_contract": sanitize_learning_value(analysis["final"]),
        "corrections": analysis["corrections"],
        "status": _safe_metadata(analysis["status"]),
        "first_hit": analysis["first_hit"],
        "verified": analysis["status"] == "verified",
        "data_quality": analysis["data_quality"],
        "data_quality_issues": analysis["data_quality_issues"],
        "create_time": (
            sample.create_time.strftime("%Y-%m-%d %H:%M:%S")
            if sample.create_time
            else None
        ),
    }


def _learning_metrics_from_samples(samples: list[dict], days: int) -> dict:
    pending_count = 0
    invalid_count = 0
    verified_samples = []
    for sample in samples:
        if sample.get("data_quality") != "valid" or sample["status"] == "invalid":
            invalid_count += 1
        elif sample["status"] == "verified":
            verified_samples.append(sample)
        else:
            pending_count += 1

    by_script: dict[str, dict] = {}
    correction_counts: dict[str, int] = {}
    first_hit_count = 0
    for sample in verified_samples:
        script_key = str(sample["script_key"])
        item = by_script.setdefault(
            script_key,
            {"verified_count": 0, "first_hit_count": 0},
        )
        item["verified_count"] += 1
        if sample["first_hit"]:
            first_hit_count += 1
            item["first_hit_count"] += 1
        for correction in sample["corrections"]:
            field = str(correction["field"])
            correction_counts[field] = correction_counts.get(field, 0) + 1

    script_metrics = []
    for script_key in sorted(by_script):
        item = by_script[script_key]
        rate = item["first_hit_count"] / item["verified_count"]
        script_metrics.append(
            {
                "script_key": script_key,
                **item,
                "first_hit_rate": min(1.0, max(0.0, rate)),
            }
        )
    verified_count = len(verified_samples)
    overall_rate = first_hit_count / verified_count if verified_count else None
    return {
        "days": days,
        "sample_count": len(samples),
        "verified_count": verified_count,
        "pending_count": pending_count,
        "invalid_count": invalid_count,
        "first_hit_count": first_hit_count,
        "first_hit_rate": (
            min(1.0, max(0.0, overall_rate)) if overall_rate is not None else None
        ),
        "by_script": script_metrics,
        "by_correction_field": [
            {"field": field, "count": correction_counts[field]}
            for field in sorted(correction_counts)
        ],
    }


def learning_metrics(db: Session, project_id: int, days: int) -> dict:
    if isinstance(days, bool) or days not in {7, 30}:
        raise LearningInputError("命中率统计仅支持 7 天或 30 天")
    cutoff = datetime.now() - timedelta(days=days)
    rows = (
        db.query(DataAgentLearningSample)
        .filter(
            DataAgentLearningSample.project_id == int(project_id),
            DataAgentLearningSample.create_time >= cutoff,
        )
        .order_by(DataAgentLearningSample.id.desc())
        .all()
    )
    return _learning_metrics_from_samples(
        [_learning_metric_sample(row) for row in rows],
        days,
    )


def _create_review(
    db: Session,
    *,
    candidate_id: int,
    rule_version_id: int | None,
    user_id: int,
    action: str,
    reason: str,
) -> DataAgentRuleReview:
    review = DataAgentRuleReview(
        candidate_id=int(candidate_id),
        rule_version_id=int(rule_version_id) if rule_version_id is not None else None,
        user_id=int(user_id),
        action=str(action),
        reason=_safe_reason(reason),
        create_time=datetime.now(),
    )
    db.add(review)
    return review


def _begin_learning_write(db: Session) -> None:
    if db.in_transaction():
        db.rollback()
    bind = db.get_bind()
    if bind.dialect.name == "sqlite":
        try:
            db.execute(text("BEGIN IMMEDIATE"))
        except OperationalError:
            db.rollback()
            raise LearningConflictError(
                "学习规则已被其他管理员更新，请刷新后重试"
            ) from None


def _commit_learning_write(db: Session) -> None:
    try:
        db.commit()
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        raise LearningConflictError("学习规则已被其他管理员更新，请刷新后重试") from None


def _rollback_and_raise(db: Session, exc: Exception) -> None:
    db.rollback()
    if isinstance(exc, (LearningNotFoundError, LearningConflictError, LearningInputError)):
        raise exc
    if isinstance(exc, (IntegrityError, OperationalError)):
        raise LearningConflictError("学习规则已被其他管理员更新，请刷新后重试") from None
    raise exc


def _next_rule_version(db: Session, project_id: int, scope: str, rule_key: str) -> int:
    highest = (
        db.query(func.max(DataAgentRuleVersion.version))
        .filter(
            DataAgentRuleVersion.project_id == int(project_id),
            DataAgentRuleVersion.scope == str(scope),
            DataAgentRuleVersion.rule_key == str(rule_key),
        )
        .scalar()
    )
    return int(highest or 0) + 1


def _supersede_active(db: Session, project_id: int, scope: str, rule_key: str) -> None:
    db.query(DataAgentRuleVersion).filter(
        DataAgentRuleVersion.project_id == int(project_id),
        DataAgentRuleVersion.scope == str(scope),
        DataAgentRuleVersion.rule_key == str(rule_key),
        DataAgentRuleVersion.status == "active",
    ).update(
        {DataAgentRuleVersion.status: "superseded"},
        synchronize_session=False,
    )


def _strict_candidate_rule(candidate: DataAgentRuleCandidate) -> dict:
    try:
        proposal = _load_json_object(candidate.proposal_json)
        validated = validate_candidate_rule(proposal)
    except (TypeError, ValueError):
        raise LearningConflictError("候选规则未通过安全校验") from None
    if validated["signature"] != str(candidate.rule_key):
        raise LearningConflictError("候选规则标识与规范内容不一致")
    return validated


def _strict_version_rule(rule: DataAgentRuleVersion) -> dict:
    try:
        return validate_candidate_rule(_load_json_object(rule.rule_json))
    except (TypeError, ValueError):
        raise LearningConflictError("规则版本未通过安全校验") from None


def get_learning_overview(db: Session, project_id: int) -> dict:
    now = datetime.now()
    samples = (
        db.query(DataAgentLearningSample)
        .filter(
            DataAgentLearningSample.project_id == int(project_id),
            DataAgentLearningSample.create_time >= now - timedelta(days=30),
        )
        .order_by(DataAgentLearningSample.id.desc())
        .all()
    )
    serialized_samples = [
        serialize_learning_sample(item) for item in samples[:100]
    ]
    metric_samples = serialized_samples + [
        _learning_metric_sample(item) for item in samples[100:]
    ]
    serialized_days_7 = [
        payload
        for sample, payload in zip(samples, metric_samples)
        if sample.create_time >= now - timedelta(days=7)
    ]
    candidates = (
        db.query(DataAgentRuleCandidate)
        .filter(DataAgentRuleCandidate.project_id == int(project_id))
        .order_by(DataAgentRuleCandidate.id.desc())
        .limit(100)
        .all()
    )
    visible_rules_filter = or_(
        (
            (DataAgentRuleVersion.project_id == int(project_id))
            & (DataAgentRuleVersion.scope == "project")
        ),
        (
            (DataAgentRuleVersion.project_id == 0)
            & (DataAgentRuleVersion.scope == "global")
        ),
    )
    active_rules = (
        db.query(DataAgentRuleVersion)
        .filter(visible_rules_filter, DataAgentRuleVersion.status == "active")
        .order_by(DataAgentRuleVersion.scope.asc(), DataAgentRuleVersion.rule_key.asc())
        .limit(100)
        .all()
    )
    recent_versions = (
        db.query(DataAgentRuleVersion)
        .filter(visible_rules_filter)
        .order_by(DataAgentRuleVersion.id.desc())
        .limit(100)
        .all()
    )
    visible_candidate_ids = {int(item.id) for item in candidates}
    visible_version_ids = {int(item.id) for item in recent_versions}
    reviews = []
    if visible_candidate_ids or visible_version_ids:
        reviews = (
            db.query(DataAgentRuleReview)
            .filter(
                or_(
                    DataAgentRuleReview.candidate_id.in_(visible_candidate_ids or {-1}),
                    DataAgentRuleReview.rule_version_id.in_(visible_version_ids or {-1}),
                )
            )
            .order_by(DataAgentRuleReview.id.desc())
            .limit(100)
            .all()
        )
    return {
        "project_id": int(project_id),
        "candidates": [_serialize_candidate(item) for item in candidates],
        "active_rules": [_serialize_rule(item) for item in active_rules],
        "recent_versions": [_serialize_rule(item) for item in recent_versions],
        "recent_reviews": [_serialize_review(item) for item in reviews],
        "samples": serialized_samples,
        "metrics": {
            "days_7": _learning_metrics_from_samples(serialized_days_7, 7),
            "days_30": _learning_metrics_from_samples(metric_samples, 30),
        },
    }


def get_learning_sample(db: Session, sample_id: int, project_id: int) -> dict:
    sample = (
        db.query(DataAgentLearningSample)
        .filter(
            DataAgentLearningSample.id == int(sample_id),
            DataAgentLearningSample.project_id == int(project_id),
        )
        .first()
    )
    if sample is None:
        raise LearningNotFoundError("学习样本不存在")
    return serialize_learning_sample(sample)


def get_candidate_detail(db: Session, candidate_id: int) -> dict:
    candidate = db.get(DataAgentRuleCandidate, int(candidate_id))
    if candidate is None:
        raise LearningNotFoundError("候选规则不存在")
    try:
        source_ids = _safe_source_ids(candidate)[:MAX_REGRESSION_IDS]
    except (TypeError, ValueError):
        source_ids = []
    samples = []
    if source_ids:
        rows = (
            db.query(DataAgentLearningSample)
            .filter(
                DataAgentLearningSample.id.in_(source_ids),
                DataAgentLearningSample.project_id == int(candidate.project_id),
            )
            .order_by(DataAgentLearningSample.id.asc())
            .all()
        )
        samples = [
            {
                "id": int(row.id),
                "module_key": _safe_metadata(row.module_key),
                "intent_key": _safe_metadata(row.intent_key),
                "instruction": sanitize_learning_value(row.instruction_text or ""),
                "corrections": _safe_json_value(row.corrections_json, []),
                "verified": bool(row.verified),
                "outcome": _safe_metadata(row.outcome),
            }
            for row in rows
        ]
    reviews = (
        db.query(DataAgentRuleReview)
        .filter(DataAgentRuleReview.candidate_id == int(candidate.id))
        .order_by(DataAgentRuleReview.id.asc())
        .limit(100)
        .all()
    )
    return {
        "candidate": _serialize_candidate(candidate),
        "source_samples": samples,
        "reviews": [_serialize_review(item) for item in reviews],
    }


def get_rule_detail(db: Session, rule_version_id: int) -> dict:
    rule = db.get(DataAgentRuleVersion, int(rule_version_id))
    if rule is None:
        raise LearningNotFoundError("规则版本不存在")
    history = (
        db.query(DataAgentRuleVersion)
        .filter(
            DataAgentRuleVersion.project_id == int(rule.project_id),
            DataAgentRuleVersion.scope == str(rule.scope),
            DataAgentRuleVersion.rule_key == str(rule.rule_key),
        )
        .order_by(DataAgentRuleVersion.version.desc())
        .limit(100)
        .all()
    )
    history_ids = [int(item.id) for item in history]
    reviews = (
        db.query(DataAgentRuleReview)
        .filter(DataAgentRuleReview.rule_version_id.in_(history_ids))
        .order_by(DataAgentRuleReview.id.asc())
        .limit(100)
        .all()
    )
    return {
        "rule": _serialize_rule(rule),
        "history": [_serialize_rule(item) for item in history],
        "reviews": [_serialize_review(item) for item in reviews],
    }


def approve_candidate(db: Session, candidate_id: int, user_id: int, reason: str) -> dict:
    safe_reason = _safe_reason(reason)
    _begin_learning_write(db)
    try:
        candidate = db.get(DataAgentRuleCandidate, int(candidate_id))
        if candidate is None:
            raise LearningNotFoundError("候选规则不存在")
        if candidate.status != "pending_review":
            raise LearningConflictError("仅 pending_review 候选可批准")
        try:
            regression = _load_json_object(candidate.regression_json)
        except (TypeError, ValueError):
            raise LearningConflictError("候选回归结果无效") from None
        if not regression_passed(regression):
            raise LearningConflictError("候选回归未通过")
        rule = _strict_candidate_rule(candidate)
        _supersede_active(db, candidate.project_id, "project", candidate.rule_key)
        version = DataAgentRuleVersion(
            candidate_id=int(candidate.id),
            project_id=int(candidate.project_id),
            scope="project",
            rule_key=str(candidate.rule_key),
            version=_next_rule_version(db, candidate.project_id, "project", candidate.rule_key),
            rule_json=_stable_json(rule),
            status="active",
            create_time=datetime.now(),
            activated_at=datetime.now(),
        )
        db.add(version)
        db.flush()
        candidate.status = "approved"
        candidate.update_time = datetime.now()
        _create_review(
            db,
            candidate_id=candidate.id,
            rule_version_id=version.id,
            user_id=user_id,
            action="approve",
            reason=safe_reason,
        )
        _commit_learning_write(db)
        db.refresh(version)
        return {"candidate": _serialize_candidate(candidate), "rule": _serialize_rule(version)}
    except Exception as exc:
        _rollback_and_raise(db, exc)


def reject_candidate(db: Session, candidate_id: int, user_id: int, reason: str) -> dict:
    safe_reason = _safe_reason(reason)
    _begin_learning_write(db)
    try:
        candidate = db.get(DataAgentRuleCandidate, int(candidate_id))
        if candidate is None:
            raise LearningNotFoundError("候选规则不存在")
        if candidate.status != "pending_review":
            raise LearningConflictError("仅 pending_review 候选可拒绝")
        candidate.status = "rejected"
        candidate.update_time = datetime.now()
        _create_review(
            db,
            candidate_id=candidate.id,
            rule_version_id=None,
            user_id=user_id,
            action="reject",
            reason=safe_reason,
        )
        _commit_learning_write(db)
        return {"candidate": _serialize_candidate(candidate)}
    except Exception as exc:
        _rollback_and_raise(db, exc)


def promote_rule(db: Session, rule_version_id: int, user_id: int, reason: str) -> dict:
    safe_reason = _safe_reason(reason)
    _begin_learning_write(db)
    try:
        source = db.get(DataAgentRuleVersion, int(rule_version_id))
        if source is None:
            raise LearningNotFoundError("规则版本不存在")
        if (
            source.scope != "project"
            or int(source.project_id) <= 0
            or source.status != "active"
        ):
            raise LearningConflictError("仅 active 项目规则可提升")
        rule = _strict_version_rule(source)
        if rule["learning_mode"] in {"pattern", "strategy"}:
            raise LearningConflictError("该学习规则仅允许项目范围")
        _supersede_active(db, 0, "global", source.rule_key)
        version = DataAgentRuleVersion(
            candidate_id=int(source.candidate_id),
            project_id=0,
            scope="global",
            rule_key=str(source.rule_key),
            version=_next_rule_version(db, 0, "global", source.rule_key),
            rule_json=_stable_json(rule),
            status="active",
            create_time=datetime.now(),
            activated_at=datetime.now(),
        )
        db.add(version)
        db.flush()
        _create_review(
            db,
            candidate_id=source.candidate_id,
            rule_version_id=version.id,
            user_id=user_id,
            action="promote",
            reason=safe_reason,
        )
        _commit_learning_write(db)
        db.refresh(version)
        return {"source_rule": _serialize_rule(source), "rule": _serialize_rule(version)}
    except Exception as exc:
        _rollback_and_raise(db, exc)


def disable_rule(db: Session, rule_version_id: int, user_id: int, reason: str) -> dict:
    safe_reason = _safe_reason(reason)
    _begin_learning_write(db)
    try:
        rule = db.get(DataAgentRuleVersion, int(rule_version_id))
        if rule is None:
            raise LearningNotFoundError("规则版本不存在")
        if rule.status != "active":
            raise LearningConflictError("仅 active 规则可停用")
        rule.status = "disabled"
        _create_review(
            db,
            candidate_id=rule.candidate_id,
            rule_version_id=rule.id,
            user_id=user_id,
            action="disable",
            reason=safe_reason,
        )
        _commit_learning_write(db)
        return {"rule": _serialize_rule(rule)}
    except Exception as exc:
        _rollback_and_raise(db, exc)


def rollback_rule(
    db: Session,
    rule_version_id: int,
    target_version_id: int,
    user_id: int,
    reason: str,
) -> dict:
    safe_reason = _safe_reason(reason)
    _begin_learning_write(db)
    try:
        current = db.get(DataAgentRuleVersion, int(rule_version_id))
        target = db.get(DataAgentRuleVersion, int(target_version_id))
        if current is None or target is None:
            raise LearningNotFoundError("规则版本不存在")
        identity = (int(current.project_id), str(current.scope), str(current.rule_key))
        target_identity = (int(target.project_id), str(target.scope), str(target.rule_key))
        if identity != target_identity:
            raise LearningConflictError("回滚目标不属于同一规则历史")
        if target.status not in {"active", "superseded", "disabled"}:
            raise LearningConflictError("回滚目标状态无效")
        rule = _strict_version_rule(target)
        _supersede_active(db, current.project_id, current.scope, current.rule_key)
        version = DataAgentRuleVersion(
            candidate_id=int(target.candidate_id),
            project_id=int(current.project_id),
            scope=str(current.scope),
            rule_key=str(current.rule_key),
            version=_next_rule_version(db, current.project_id, current.scope, current.rule_key),
            rule_json=_stable_json(rule),
            status="active",
            create_time=datetime.now(),
            activated_at=datetime.now(),
        )
        db.add(version)
        db.flush()
        _create_review(
            db,
            candidate_id=target.candidate_id,
            rule_version_id=version.id,
            user_id=user_id,
            action="rollback",
            reason=safe_reason,
        )
        _commit_learning_write(db)
        db.refresh(version)
        return {"target_rule": _serialize_rule(target), "rule": _serialize_rule(version)}
    except Exception as exc:
        _rollback_and_raise(db, exc)
