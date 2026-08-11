from __future__ import annotations

import pytest

from app.system_regression.projects.japan.execution_contract import (
    ExecutionResultPayload,
    classify_business_diffs,
)
from app.system_regression.projects.japan.runner import CaseRunResult


def test_execution_payload_rejects_non_contract_status():
    with pytest.raises(ValueError, match="无效结果状态"):
        ExecutionResultPayload(status="waiting_account", reason_code="account_required")


def test_execution_payload_contains_the_unified_result_fields():
    payload = ExecutionResultPayload(
        execution_id="exec-1",
        batch_id="batch-1",
        case_id="case-1",
        status="blocked",
        reason_code="target_action_unavailable",
    ).to_dict()

    assert set(payload) == {
        "execution_id",
        "batch_id",
        "case_id",
        "status",
        "reason_code",
        "guard_kind",
        "expected_stage",
        "actual_stage",
        "actor",
        "order_sn",
        "problem_goods_id",
        "purchase_record_ids",
        "parameter_snapshot",
        "precondition_evidence",
        "attempted_actions",
        "response_evidence",
        "before_evidence",
        "after_evidence",
        "required_effects",
        "forbidden_effects",
        "allowed_effects",
        "unclassified_effects",
        "business_diffs",
        "failure_reason",
    }


def test_unclassified_business_diff_prevents_pass():
    checked = classify_business_diffs(
        ExecutionResultPayload(
            status="passed",
            business_diffs=[
                {
                    "entity": "problem_goods",
                    "field": "amount",
                    "before": "0",
                    "after": "1",
                }
            ],
        ),
        required_rules=[],
        forbidden_rules=[],
        allowed_rules=[],
    )

    assert checked.status == "failed"
    assert checked.reason_code == "unclassified_business_effect"
    assert checked.unclassified_effects == checked.business_diffs


def test_case_run_result_uses_reason_code_and_keeps_error_code_compatibility():
    result = CaseRunResult(status="failed", reason_code="backend_guard_missing")

    assert result.reason_code == "backend_guard_missing"
    assert result.error_code == "backend_guard_missing"
