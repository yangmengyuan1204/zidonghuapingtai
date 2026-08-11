from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence


RESULT_STATUSES = frozenset({"passed", "failed", "blocked", "waiting"})


@dataclass
class ExecutionResultPayload:
    execution_id: str = ""
    batch_id: str = ""
    case_id: str = ""
    status: str = "blocked"
    reason_code: str = ""
    guard_kind: str = ""
    expected_stage: str = ""
    actual_stage: str = ""
    actor: dict[str, Any] = field(default_factory=dict)
    order_sn: str = ""
    problem_goods_id: str = ""
    purchase_record_ids: list[str] = field(default_factory=list)
    parameter_snapshot: dict[str, Any] = field(default_factory=dict)
    precondition_evidence: dict[str, Any] = field(default_factory=dict)
    attempted_actions: list[dict[str, Any]] = field(default_factory=list)
    response_evidence: list[dict[str, Any]] = field(default_factory=list)
    before_evidence: dict[str, Any] = field(default_factory=dict)
    after_evidence: dict[str, Any] = field(default_factory=dict)
    required_effects: list[dict[str, Any]] = field(default_factory=list)
    forbidden_effects: list[dict[str, Any]] = field(default_factory=list)
    allowed_effects: list[dict[str, Any]] = field(default_factory=list)
    unclassified_effects: list[dict[str, Any]] = field(default_factory=list)
    business_diffs: list[dict[str, Any]] = field(default_factory=list)
    failure_reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in RESULT_STATUSES:
            raise ValueError(f"无效结果状态：{self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _matches_rule(effect: Mapping[str, Any], rule: Mapping[str, Any]) -> bool:
    return all(effect.get(key) == value for key, value in rule.items())


def _matches_any(effect: Mapping[str, Any], rules: Sequence[Mapping[str, Any]]) -> bool:
    return any(_matches_rule(effect, rule) for rule in rules)


def classify_business_diffs(
    payload: ExecutionResultPayload,
    *,
    required_rules: Sequence[Mapping[str, Any]],
    forbidden_rules: Sequence[Mapping[str, Any]],
    allowed_rules: Sequence[Mapping[str, Any]],
) -> ExecutionResultPayload:
    payload.required_effects = [
        dict(effect) for effect in payload.business_diffs if _matches_any(effect, required_rules)
    ]
    payload.forbidden_effects = [
        dict(effect) for effect in payload.business_diffs if _matches_any(effect, forbidden_rules)
    ]
    payload.allowed_effects = [
        dict(effect) for effect in payload.business_diffs if _matches_any(effect, allowed_rules)
    ]
    classified = {
        id(effect)
        for effect in payload.business_diffs
        if _matches_any(effect, required_rules)
        or _matches_any(effect, forbidden_rules)
        or _matches_any(effect, allowed_rules)
    }
    payload.unclassified_effects = [
        dict(effect) for effect in payload.business_diffs if id(effect) not in classified
    ]
    missing_required = [
        dict(rule)
        for rule in required_rules
        if not any(_matches_rule(effect, rule) for effect in payload.business_diffs)
    ]
    if payload.forbidden_effects:
        payload.status = "failed"
        payload.reason_code = "forbidden_business_effect"
        payload.failure_reason = "拦截动作产生了禁止的业务变化"
    elif payload.unclassified_effects:
        payload.status = "failed"
        payload.reason_code = "unclassified_business_effect"
        payload.failure_reason = "动作产生了未分类的业务变化"
    elif missing_required:
        payload.status = "failed"
        payload.reason_code = "required_business_effect_missing"
        payload.failure_reason = "缺少场景要求的业务变化"
    return payload


__all__ = [
    "ExecutionResultPayload",
    "RESULT_STATUSES",
    "classify_business_diffs",
]
