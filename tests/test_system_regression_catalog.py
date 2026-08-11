from collections import Counter

from app.system_regression.projects.japan.catalog import japan_case_definitions


def test_japan_catalog_has_stable_unique_matrix():
    cases = japan_case_definitions()

    assert len(cases) == 77
    assert len({case.key for case in cases}) == 77
    assert Counter(case.category for case in cases) == {
        "payment": 10,
        "problem_amount": 12,
        "problem_service_fee": 6,
        "problem_option_manual": 15,
        "problem_option_auto": 6,
        "problem_mixed": 3,
        "problem_flow": 10,
        "problem_guard": 15,
    }


def test_japan_catalog_keys_are_contiguous_within_each_group():
    keys = {case.key for case in japan_case_definitions()}

    expected = {
        *(f"JP-PAY-{index:03d}" for index in range(1, 11)),
        *(f"JP-PG-AMT-{index:03d}" for index in range(1, 13)),
        *(f"JP-PG-SVC-{index:03d}" for index in range(1, 7)),
        *(f"JP-PG-OPT-M-{index:03d}" for index in range(1, 16)),
        *(f"JP-PG-OPT-A-{index:03d}" for index in range(1, 7)),
        *(f"JP-PG-MIX-{index:03d}" for index in range(1, 4)),
        *(f"JP-PG-FLOW-{index:03d}" for index in range(1, 11)),
        *(f"JP-PG-GUARD-{index:03d}" for index in range(1, 16)),
    }

    assert keys == expected


def test_guard_cases_declare_expected_errors_and_success_cases_declare_direction():
    cases = japan_case_definitions()

    guards = [case for case in cases if case.category == "problem_guard"]
    successes = [case for case in cases if case.category != "problem_guard"]

    assert all(case.expectation.outcome == "guard" for case in guards)
    assert all(case.expectation.error_codes or case.expectation.error_keywords for case in guards)
    assert all(case.expectation.outcome == "success" for case in successes)
    assert all(case.expectation.direction in {"credit", "debit", "none"} for case in successes)


def test_japan_catalog_sort_order_is_unique_and_stable():
    cases = japan_case_definitions()

    assert [case.sort_order for case in cases] == list(range(1, 78))
    assert all(case.runner_kind for case in cases)
    assert all(case.name.strip() for case in cases)


def test_problem_amount_catalog_declares_formal_completion_stage():
    case = next(case for case in japan_case_definitions() if case.key == "JP-PG-AMT-001")

    assert case.expectation.expected_stage == "problem_goods_completed"
