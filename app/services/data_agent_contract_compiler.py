from __future__ import annotations

import re
from typing import Any, Sequence

from ..data_scripts.capabilities import (
    DataScriptCapability,
    effective_contract_fields,
    is_sensitive_field_identifier,
)
from .data_agent_contracts import apply_contract_updates
from .data_factory_agent_tools import redact_sensitive_value


CORE_SPECIALIZED_CAPABILITIES = {
    "full_flow",
    "resume_order_flow",
    "resume_porder_flow",
    "problem_goods",
}


def normalize_match_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").casefold())


def select_capability(
    candidate_key: str,
    instruction: str,
    capabilities: Sequence[DataScriptCapability],
) -> DataScriptCapability | None:
    by_key = {item.key: item for item in capabilities if item.agent_enabled}
    if candidate_key in by_key:
        return by_key[candidate_key]
    normalized = normalize_match_text(instruction)
    matches = [
        item
        for item in by_key.values()
        if any(
            normalize_match_text(term) in normalized
            for term in (*item.intents, *item.examples)
        )
    ]
    return matches[0] if len(matches) == 1 else None


def new_contract_seed(
    capability: DataScriptCapability,
    compile_context: dict[str, Any],
    *,
    materialize_defaults: bool = False,
) -> dict[str, Any]:
    fields = {
        field.name: field
        for field in effective_contract_fields(capability)
        if not field.readonly and not is_sensitive_field_identifier(field.name)
    }
    seed: dict[str, Any] = {"variables": {}}
    default_updates: dict[str, Any] = {}
    if materialize_defaults:
        default_updates = {
            name: field.default
            for name, field in fields.items()
            if field.default not in (None, "", [])
        }
        if default_updates:
            seed, _ = apply_contract_updates(seed, default_updates, capability)
    sources = {name: "default" for name in default_updates}
    inferred = set(default_updates)

    context_updates = {
        name: value
        for name, value in dict(compile_context or {}).items()
        if name in fields and value not in (None, "", [])
    }
    if context_updates:
        seed, _ = apply_contract_updates(seed, context_updates, capability)
        sources.update({name: "page_context" for name in context_updates})
        inferred.update(context_updates)
    if sources:
        seed["field_sources"] = sources
        seed["inferred_fields"] = sorted(inferred)
    return seed


def capability_risk_payload(capability: DataScriptCapability) -> dict[str, Any]:
    return {
        "level": capability.risk.level,
        "mutating": capability.risk.mutating,
        "second_confirmation": capability.risk.second_confirmation,
    }


def compile_metadata_contract(
    capability: DataScriptCapability,
    candidate_fields: dict[str, Any],
    compile_context: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    candidate_fields = dict(candidate_fields or {})
    declared = {
        field.name
        for field in effective_contract_fields(capability)
        if not field.readonly and not is_sensitive_field_identifier(field.name)
    }
    rejected = sorted(set(candidate_fields) - declared)
    seed = new_contract_seed(
        capability,
        compile_context,
        materialize_defaults=True,
    )
    safe_fields = redact_sensitive_value(
        {key: value for key, value in candidate_fields.items() if key in declared}
    )
    goal, _ = apply_contract_updates(seed, safe_fields, capability)
    if safe_fields:
        sources = dict(goal.get("field_sources") or {})
        sources.update({key: "natural_language" for key in safe_fields})
        goal["field_sources"] = sources
        goal["inferred_fields"] = sorted(
            set(goal.get("inferred_fields") or []) - set(safe_fields)
        )
    goal["capability_key"] = capability.key
    goal["risk"] = capability_risk_payload(capability)
    if capability.key not in CORE_SPECIALIZED_CAPABILITIES:
        goal["operations"] = [
            {
                "id": f"operation_{capability.key}_1",
                "type": "registered_capability",
                "capability_key": capability.key,
            }
        ]
        goal["steps"] = [f"执行{capability.name}并校验注册结果"]
    return goal, rejected
