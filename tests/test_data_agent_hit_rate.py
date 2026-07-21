import copy
import itertools
import json
from pathlib import Path

import pytest

from app.services import data_factory_agent as agent_service
from app.services.data_factory_agent_intent import reduce_intent_fields


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "data_agent_intent_cases.json"


def load_cases():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def expand_explicit_cases(fixture=None):
    fixture = fixture or load_cases()
    matrix = fixture["explicit_matrix"]
    cases = []
    for target, shape, price in itertools.product(
        matrix["targets"], matrix["shapes"], matrix["prices"]
    ):
        cases.append(
            {
                "id": f"{target['id']}__{shape['id']}__{price['id']}",
                "instruction": matrix["instruction_template"].format(
                    target=target["text"], shape=shape["text"], price=price["text"]
                ),
                "expected": {
                    "target_node": target["target_node"],
                    **copy.deepcopy(shape["expected"]),
                    "pricing": copy.deepcopy(price["expected"]),
                },
            }
        )
    return cases


def analyze_without_execution(instruction, candidate=None):
    messages = [{"role": "user", "content": instruction}]
    intent_state = reduce_intent_fields({}, instruction)
    capability_gap = agent_service._unsupported_capability(messages)
    if capability_gap:
        return {
            "status": "blocked",
            "goal": {},
            "question": "",
            "reason": capability_gap["reason"],
            "intent_state": intent_state,
        }
    payload = copy.deepcopy(candidate) if candidate is not None else {
        "status": "ready",
        "goal": {"mode": "new", "target_node": "", "variables": {}},
    }
    status, goal, question = agent_service._normalize_goal(payload, messages)
    return {
        "status": status,
        "goal": goal,
        "question": question,
        "reason": "",
        "intent_state": intent_state,
    }


def explicit_case_matches(result, case):
    expected = case["expected"]
    goal = result.get("goal") or {}
    variables = goal.get("variables") or {}
    pricing = (goal.get("intent") or {}).get("pricing") or {}
    if result.get("status") != "awaiting_confirmation":
        return False
    if goal.get("target_node") != expected["target_node"]:
        return False
    if variables.get("order_shop_count") != expected["shop_count"]:
        return False
    if variables.get("order_per_shop") != expected["per_shop"]:
        return False
    if variables.get("order_item_num") != expected["quantity"]:
        return False
    expected_pricing = expected["pricing"]
    if pricing.get("mode") != expected_pricing["mode"]:
        return False
    if expected_pricing["mode"] == "goods_total":
        return pricing.get("requested_goods_total") == expected_pricing["amount"]
    effective = pricing.get("effective_unit_prices") or []
    return bool(effective) and set(effective) == {expected_pricing["amount"]}


EXPLICIT_CASES = expand_explicit_cases()
FIXED_CASES = load_cases()["fixed_cases"]


def test_fixture_expands_to_exact_required_case_counts():
    assert len(EXPLICIT_CASES) == 60
    assert len(FIXED_CASES) == 20
    assert len({case["id"] for case in EXPLICIT_CASES + FIXED_CASES}) == 80


@pytest.mark.parametrize("case", EXPLICIT_CASES, ids=lambda case: case["id"])
def test_explicit_instruction_compiles_every_contract_field(case):
    result = analyze_without_execution(case["instruction"])

    assert result["status"] == "awaiting_confirmation"
    assert result["goal"]["target_node"] == case["expected"]["target_node"]
    variables = result["goal"]["variables"]
    assert variables["order_shop_count"] == case["expected"]["shop_count"]
    assert variables["order_per_shop"] == case["expected"]["per_shop"]
    assert variables["order_item_num"] == case["expected"]["quantity"]
    pricing = result["goal"]["intent"]["pricing"]
    assert pricing["mode"] == case["expected"]["pricing"]["mode"]
    if pricing["mode"] == "goods_total":
        assert pricing["requested_goods_total"] == case["expected"]["pricing"]["amount"]
    else:
        assert set(pricing["effective_unit_prices"]) == {case["expected"]["pricing"]["amount"]}


def test_explicit_first_turn_hit_rate_is_at_least_95_percent():
    correct = sum(
        explicit_case_matches(analyze_without_execution(case["instruction"]), case)
        for case in EXPLICIT_CASES
    )
    assert correct >= 57, f"首次命中 {correct}/60，低于 95% 门禁"


@pytest.mark.parametrize("case", FIXED_CASES, ids=lambda case: case["id"])
def test_ambiguous_conflicting_and_dangerous_cases_are_gated(case):
    result = analyze_without_execution(case["instruction"], case.get("candidate"))

    assert result["status"] == case["expected_status"]
    explanation = f"{result.get('question', '')} {result.get('reason', '')}"
    assert case["question_contains"] in explanation


def test_evaluation_path_never_calls_business_tools(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("首次命中率评测不得调用 execute_agent_tool")

    monkeypatch.setattr(agent_service, "execute_agent_tool", fail_if_called)
    for case in EXPLICIT_CASES:
        analyze_without_execution(case["instruction"])
    for case in FIXED_CASES:
        analyze_without_execution(case["instruction"], case.get("candidate"))


def test_real_evaluator_reuses_the_same_fixture_expansion_and_scoring():
    from scripts import evaluate_data_agent_hit_rate as evaluator

    evaluator_cases = evaluator.expand_explicit_cases(load_cases())
    assert evaluator_cases == EXPLICIT_CASES
    assert all(
        evaluator.explicit_case_matches(analyze_without_execution(case["instruction"]), case)
        for case in evaluator_cases
    )


def test_tool_record_snapshot_counts_only_data_agent_tool_metadata():
    from scripts import evaluate_data_agent_hit_rate as evaluator

    rows = [
        (1, json.dumps({"_exec_meta": {"kind": "data_agent_tool"}})),
        (2, json.dumps({"_exec_meta": {"kind": "data_agent_analysis"}})),
        (3, "not-json"),
        (4, json.dumps({"_exec_meta": {"kind": "data_agent_tool"}})),
    ]
    assert evaluator.tool_record_snapshot_from_rows(rows) == {"count": 2, "max_id": 4}
