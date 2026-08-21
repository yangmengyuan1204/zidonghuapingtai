from __future__ import annotations

from app.system_regression.projects.japan.catalog import japan_case_definitions
from app.system_regression.projects.japan.guard_scenarios import (
    guard_scenario,
    guard_scenarios,
)


def test_retired_catalog_guards_keep_executable_specs():
    guards = [case for case in japan_case_definitions() if case.runner_kind == "problem_guard"]

    assert guards == []
    scenarios = guard_scenarios()
    assert len(scenarios) == 15
    for scenario in scenarios:
        spec = guard_scenario(scenario.guard_kind)
        assert spec.expected_stage
        assert spec.precondition_builder
        assert spec.target_action
        assert spec.requires_target_call is True
        assert spec.parallel_safe is False


def test_each_guard_stage_and_action_match_the_real_backend_phase():
    expected = {
        "part_tail_unpaid": ("business_deal", "business_deal"),
        "resend_order": ("problem_create", "create_problem"),
        "purchase_wait_pay": ("problem_create", "create_problem"),
        "duplicate_open_problem": ("problem_create", "create_problem"),
        "problem_num_over_unstored": ("problem_create", "create_problem"),
        "pre_num_below_storage": ("purchase_deal", "purchase_deal"),
        "quantity_over_possible": ("purchase_deal", "purchase_deal"),
        "quantity_up_auto_option": ("purchase_deal", "purchase_deal"),
        "option_num_over_goods": ("purchase_deal", "purchase_deal"),
        "multiple_rate_auto": ("purchase_deal", "purchase_deal"),
        "option_price_type_change": ("option_update", "update_options"),
        "multiple_purchase_update": ("pre_data_update", "update_pre_data"),
        "large_refund_account": ("purchase_deal", "large_refund_composite"),
        "restricted_skip_purchase": ("business_deal", "business_deal"),
        "direct_complete_invalid_type": ("distribution_direct_complete", "distribution_direct_complete"),
    }

    assert {
        spec.guard_kind: (spec.expected_stage, spec.target_action)
        for spec in guard_scenarios()
    } == expected


def test_guard_error_matching_priority_is_declared():
    for spec in guard_scenarios():
        assert spec.match_priority == ("business_code", "structured_error", "http_status", "message_regex")


def test_candidate_visibility_is_auxiliary_not_a_pass_condition():
    for spec in guard_scenarios():
        assert "candidate_hidden" not in spec.success_conditions
        assert {"target_rejected", "normal_actor_rejected"} & set(spec.success_conditions)
