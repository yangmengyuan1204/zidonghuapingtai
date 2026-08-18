from collections import Counter

from app.system_regression.projects.japan.catalog import japan_case_definitions


def test_japan_catalog_has_stable_unique_matrix():
    cases = japan_case_definitions()

    assert len(cases) == 87
    assert len({case.key for case in cases}) == 87
    assert Counter(case.category for case in cases) == {
        "payment": 15,
        "porder": 5,
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
        *(f"JP-PAY-{index:03d}" for index in range(1, 21)),
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

    assert [case.sort_order for case in cases] == list(range(1, 88))
    assert all(case.runner_kind for case in cases)
    assert all(case.name.strip() for case in cases)


def test_payment_panels_fill_order_rows_and_new_coverage_cases():
    cases = {case.key: case for case in japan_case_definitions()}

    assert cases["JP-PAY-001"].parameters["items"][0]["offer_price"]["value"] == "10"
    assert cases["JP-PAY-005"].category == "porder"
    assert cases["JP-PAY-005"].parameters["porder"]["box_length"] == 58
    assert cases["JP-PAY-007"].parameters["items"][1]["offer_freight"]["value"] == "4"
    assert cases["JP-PAY-008"].parameters["order"]["other_fee_name"] == "包装材料费"
    assert cases["JP-PAY-009"].name == "固定金额和百分比 OPTION 一起买"
    assert cases["JP-PAY-009"].parameters["option_profile"] == "fixed_and_rate"
    assert {int(row["price_type"]) for row in cases["JP-PAY-009"].parameters["items"][0]["options"]} == {0, 1}
    assert cases["JP-PAY-011"].parameters["coupon"]["selectedId"] == "__service_discount__"
    assert cases["JP-PAY-011"].parameters["service_discount"] is True
    assert cases["JP-PAY-012"].category == "porder"
    assert cases["JP-PAY-012"].parameters["porder"]["extra_name"] == "加固包装"
    assert cases["JP-PAY-013"].parameters["part_pay"]["fee_timing"]["domestic_freight"] == "tail"
    assert cases["JP-PAY-014"].parameters["part_pay"]["tail_node"] == "before_porder_create"
    assert cases["JP-PAY-015"].parameters["part_pay"]["tail_partial"] is True
    assert cases["JP-PAY-015"].parameters["part_pay"]["tail_sortings"] == "1"
    assert cases["JP-PAY-016"].parameters["part_pay"]["fee_timing"]["service_fee"] == "tail"
    assert cases["JP-PAY-017"].parameters["part_pay"]["fee_timing"]["additional_service_fee"] == "tail"
    assert cases["JP-PAY-018"].parameters["part_pay"]["fee_timing"]["other_fee"] == "tail"
    assert cases["JP-PAY-019"].parameters["porder"]["price_manual"] is True
    assert cases["JP-PAY-019"].parameters["porder"]["logistics_price"]["value"] == "88"
    assert cases["JP-PAY-020"].category == "porder"
    assert cases["JP-PAY-020"].parameters["porder"]["logistics"] == "20"
    assert cases["JP-PG-FLOW-008"].parameters["problem_goods"]["client_deal_other"] == "系统回归自定义回复"
    assert cases["JP-PG-AMT-004"].parameters["problem_goods"]["problem_description"] == "单价下调退款"
    assert cases["JP-PG-GUARD-001"].parameters["part_pay"]["enabled"] is True


def test_debit_and_none_problem_cases_do_not_default_to_refund_only():
    cases = {case.key: case for case in japan_case_definitions()}

    assert cases["JP-PG-AMT-001"].parameters["g_deal_type"] == "其他"
    assert cases["JP-PG-AMT-001"].parameters["service_deal_suggest"] == 1
    assert cases["JP-PG-AMT-005"].parameters["g_deal_type"] == "其他"
    assert cases["JP-PG-OPT-M-001"].parameters["g_deal_type"] == "其他"
    assert cases["JP-PG-SVC-001"].parameters["service_deal_suggest"] == 2
    assert cases["JP-PG-FLOW-007"].parameters["g_deal_type"] == "其他"


def test_problem_amount_catalog_declares_formal_completion_stage():
    case = next(case for case in japan_case_definitions() if case.key == "JP-PG-AMT-001")

    assert case.expectation.expected_stage == "problem_goods_completed"
