import copy
import itertools
import json
import math
from pathlib import Path

import pytest

from app.data_scripts.capabilities import capability_catalog
from app.services import data_factory_agent as agent_service
from app.services.data_agent_contract_compiler import select_capability
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


def build_hit_rate_report(samples: list[dict], baseline: dict[str, float]) -> dict:
    baseline_by_key = {}
    for raw_key, value in baseline.items():
        key = str(raw_key)
        if key in baseline_by_key:
            raise ValueError(f"duplicate baseline category: {key}")
        baseline_by_key[key] = value

    categories = {}
    for sample in samples:
        if not sample.get("verified"):
            continue
        key = str(sample["script_key"])
        core = bool(sample.get("core"))
        item = categories.get(key)
        if item is None:
            item = {"core": core, "sample_count": 0, "hit_count": 0}
            categories[key] = item
        elif item["core"] is not core:
            raise ValueError(f"conflicting core classification: {key}")
        item["sample_count"] += 1
        item["hit_count"] += int(bool(sample.get("first_hit")))

    for key in baseline_by_key:
        categories.setdefault(
            key,
            {"core": None, "sample_count": 0, "hit_count": 0},
        )

    for key, item in categories.items():
        item["rate"] = (
            item["hit_count"] / item["sample_count"]
            if item["sample_count"]
            else None
        )
        threshold = (
            0.95 if item["core"] is True
            else 0.90 if item["core"] is False
            else None
        )
        item["threshold"] = threshold
        item["baseline"] = baseline_by_key.get(key)
        baseline_valid = (
            key in baseline_by_key
            and isinstance(item["baseline"], (int, float))
            and math.isfinite(float(item["baseline"]))
            and 0 <= item["baseline"] <= 1
        )
        rate_valid = (
            isinstance(item["rate"], (int, float))
            and math.isfinite(float(item["rate"]))
            and 0 <= item["rate"] <= 1
        )
        item["passed"] = bool(
            rate_valid
            and baseline_valid
            and threshold is not None
            and item["rate"] >= threshold
            and item["rate"] >= item["baseline"]
        )
    return {
        "passed": bool(categories) and all(item["passed"] for item in categories.values()),
        "categories": categories,
    }


def test_metadata_compiler_does_not_choose_first_ambiguous_capability():
    catalog = capability_catalog()
    selected = select_capability(
        "",
        "订单报价后继续订单续跑",
        [catalog["order_quote"], catalog["resume_order_flow"]],
    )
    assert selected is None


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


def test_hit_rate_gate_requires_threshold_denominator_and_no_regression():
    report = build_hit_rate_report(
        [
            {"script_key": "full_flow", "core": True, "first_hit": True, "verified": True}
            for _ in range(19)
        ]
        + [
            {"script_key": "full_flow", "core": True, "first_hit": False, "verified": True},
            {"script_key": "full_flow", "core": True, "first_hit": False, "verified": False},
        ],
        baseline={"full_flow": 0.94},
    )

    assert report["categories"]["full_flow"] == {
        "core": True,
        "sample_count": 20,
        "hit_count": 19,
        "rate": 0.95,
        "threshold": 0.95,
        "baseline": 0.94,
        "passed": True,
    }
    assert report["passed"] is True


def test_hit_rate_gate_fails_when_metadata_script_is_below_ninety_percent():
    samples = [
        {"script_key": "order_quote", "core": False, "first_hit": index < 8, "verified": True}
        for index in range(10)
    ]

    assert build_hit_rate_report(samples, baseline={"order_quote": 0.75})["passed"] is False


def test_hit_rate_gate_requires_every_category_to_meet_its_baseline():
    samples = [
        {"script_key": "full_flow", "core": True, "first_hit": True, "verified": True}
        for _ in range(20)
    ] + [
        {"script_key": "order_quote", "core": False, "first_hit": True, "verified": True}
        for _ in range(9)
    ] + [
        {"script_key": "order_quote", "core": False, "first_hit": False, "verified": True}
    ]

    report = build_hit_rate_report(samples, baseline={"full_flow": 0.95, "order_quote": 0.95})

    assert report["categories"]["full_flow"]["passed"] is True
    assert report["categories"]["order_quote"]["rate"] == 0.9
    assert report["categories"]["order_quote"]["passed"] is False
    assert report["passed"] is False


def test_hit_rate_gate_fails_when_no_verified_category_exists():
    samples = [
        {"script_key": "full_flow", "core": True, "first_hit": True, "verified": False}
    ]

    assert build_hit_rate_report(samples, baseline={"full_flow": 0.95}) == {
        "passed": False,
        "categories": {
            "full_flow": {
                "core": None,
                "sample_count": 0,
                "hit_count": 0,
                "rate": None,
                "threshold": None,
                "baseline": 0.95,
                "passed": False,
            }
        },
    }


def test_hit_rate_gate_rejects_conflicting_core_classification():
    samples = [
        {"script_key": "full_flow", "core": True, "first_hit": True, "verified": True},
        {"script_key": "full_flow", "core": False, "first_hit": True, "verified": True},
    ]

    with pytest.raises(ValueError, match="conflicting core classification"):
        build_hit_rate_report(samples, baseline={"full_flow": 0.95})


def test_hit_rate_gate_requires_baseline_for_every_verified_category():
    report = build_hit_rate_report(
        [{"script_key": "order_quote", "core": False, "first_hit": True, "verified": True}],
        baseline={},
    )

    assert report["categories"]["order_quote"] == {
        "core": False,
        "sample_count": 1,
        "hit_count": 1,
        "rate": 1.0,
        "threshold": 0.9,
        "baseline": None,
        "passed": False,
    }
    assert report["passed"] is False


def test_hit_rate_gate_reports_baseline_category_without_verified_samples():
    report = build_hit_rate_report([], baseline={"order_quote": 0.8})

    assert report["categories"]["order_quote"] == {
        "core": None,
        "sample_count": 0,
        "hit_count": 0,
        "rate": None,
        "threshold": None,
        "baseline": 0.8,
        "passed": False,
    }
    assert report["passed"] is False


@pytest.mark.parametrize("invalid_baseline", [None, "", float("nan"), float("inf"), -0.01, 1.01])
def test_hit_rate_gate_fails_closed_for_invalid_baseline(invalid_baseline):
    report = build_hit_rate_report(
        [{"script_key": "full_flow", "core": True, "first_hit": True, "verified": True}],
        baseline={"full_flow": invalid_baseline},
    )

    category = report["categories"]["full_flow"]
    assert category["sample_count"] == 1
    assert category["rate"] == 1.0
    assert category["threshold"] == 0.95
    assert category["baseline"] is invalid_baseline
    assert category["passed"] is False
    assert report["passed"] is False
