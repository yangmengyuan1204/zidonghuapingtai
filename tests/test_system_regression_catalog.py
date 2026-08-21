from collections import Counter

from app.system_regression.projects.japan.case_keys import case_key_for_category
from app.system_regression.projects.japan.catalog import japan_case_definitions


def test_japan_catalog_has_stable_unique_matrix():
    cases = japan_case_definitions()

    assert len(cases) == 68
    assert len({case.key for case in cases}) == 68
    assert Counter(case.category for case in cases) == {
        "payment": 18,
        "porder": 7,
        "problem_amount": 12,
        "problem_service_fee": 6,
        "problem_option_manual": 15,
        "problem_option_auto": 6,
        "problem_mixed": 3,
        "problem_flow": 1,
    }


def test_japan_catalog_keys_are_contiguous_within_each_group():
    keys = {case.key for case in japan_case_definitions()}

    expected = {
        *(case_key_for_category("payment", index) for index in range(1, 19)),
        *(case_key_for_category("porder", index) for index in range(1, 8)),
        *(case_key_for_category("problem_amount", index) for index in range(1, 13)),
        *(case_key_for_category("problem_service_fee", index) for index in range(1, 7)),
        *(case_key_for_category("problem_option_manual", index) for index in range(1, 16)),
        *(case_key_for_category("problem_option_auto", index) for index in range(1, 7)),
        *(case_key_for_category("problem_mixed", index) for index in range(1, 4)),
        "流程-007",
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

    assert [case.sort_order for case in cases] == list(range(1, 69))
    assert all(case.runner_kind for case in cases)
    assert all(case.name.strip() for case in cases)


def test_payment_panels_fill_order_rows_and_new_coverage_cases():
    cases = {case.key: case for case in japan_case_definitions()}

    assert cases["支付-001"].parameters["items"][0]["offer_price"]["value"] == "10"
    assert cases["配送-001"].category == "porder"
    assert cases["配送-001"].parameters["porder"]["box_length"] == 58
    assert cases["支付-005"].parameters["items"][1]["offer_freight"]["value"] == "4"
    assert cases["支付-006"].parameters["order"]["other_fee_name"] == "包装材料费"
    assert cases["支付-007"].name == "同一商品同时收固定额和百分比 OPTION"
    assert cases["支付-007"].parameters["option_profile"] == "fixed_and_rate"
    assert {int(row["price_type"]) for row in cases["支付-007"].parameters["items"][0]["options"]} == {0, 1}
    assert cases["支付-009"].parameters["coupon"]["selectedId"] == "__service_discount__"
    assert cases["支付-009"].parameters["service_discount"] is True
    assert cases["配送-003"].category == "porder"
    assert cases["配送-003"].parameters["porder"]["extra_name"] == "加固包装"
    assert cases["支付-010"].parameters["part_pay"]["fee_timing"]["domestic_freight"] == "tail"
    assert cases["支付-011"].parameters["part_pay"]["tail_node"] == "before_shelf"
    assert cases["支付-018"].parameters["part_pay"]["tail_node"] == "before_porder_create"
    assert cases["支付-012"].parameters["part_pay"]["tail_partial"] is True
    assert cases["支付-012"].parameters["part_pay"]["tail_sortings"] == "1"
    assert cases["支付-013"].parameters["part_pay"]["fee_timing"]["service_fee"] == "tail"
    assert cases["支付-014"].parameters["part_pay"]["fee_timing"]["additional_service_fee"] == "tail"
    assert cases["支付-015"].parameters["part_pay"]["fee_timing"]["other_fee"] == "tail"
    assert cases["配送-004"].parameters["porder"]["price_manual"] is True
    assert cases["配送-004"].parameters["porder"]["logistics_price"]["value"] == "88"
    assert cases["配送-005"].category == "porder"
    assert cases["配送-005"].parameters["porder"]["logistics"] == "20"
    assert cases["支付-016"].parameters["coupon"]["selectedId"] == "__account_coupon__"
    assert cases["支付-016"].parameters["discounts_id"] == ""
    assert cases["支付-017"].parameters["payment_mode"] == "bank"
    assert cases["支付-017"].parameters["coupon"]["selectedId"] == "__account_coupon__"
    assert cases["配送-006"].category == "porder"
    assert cases["配送-006"].parameters["porder"]["voucher"]["selectedId"] == "__account_voucher__"
    assert cases["配送-007"].parameters["payment_mode"] == "bank"
    assert cases["配送-007"].parameters["porder"]["voucher"]["selectedId"] == "__account_voucher__"
    assert cases["流程-007"].name == "商品数量增加后的补款金额"
    assert cases["金额-004"].parameters["problem_goods"]["problem_description"] == "单价下调退款"


def test_catalog_contains_only_amount_cases_and_retains_bank_variants():
    cases = japan_case_definitions()
    assert not any(case.category == "problem_guard" for case in cases)
    assert {case.key for case in cases if case.category == "problem_flow"} == {"流程-007"}
    assert {case.key for case in cases if case.parameters.get("payment_mode") == "bank"} >= {
        "支付-002", "支付-004", "支付-017"
    }


def test_auto_option_cases_declare_amount_relevant_baselines():
    cases = {case.key: case for case in japan_case_definitions()}
    inspection = cases["自动OPTION-004"].parameters["problem_goods"]
    non_auto = cases["自动OPTION-005"].parameters["items"][0]["options"]
    assert inspection["complete_inspect_num"] == 1
    assert all(row.get("auto_calculate") is False for row in non_auto)


def test_part_payment_tail_node_pair_changes_only_stage_boundary():
    cases = {case.key: case for case in japan_case_definitions()}
    first = cases["支付-011"].parameters
    second = cases["支付-018"].parameters
    assert first["payment_mode"] == second["payment_mode"] == "balance"
    assert first["part_pay"]["percent"] == second["part_pay"]["percent"] == 50
    assert first["order"] == second["order"]
    assert first["items"] == second["items"]
    assert first["part_pay"]["tail_node"] == "before_shelf"
    assert second["part_pay"]["tail_node"] == "before_porder_create"


def test_mixed_zero_case_is_explicitly_unchanged():
    case = next(case for case in japan_case_definitions() if case.key == "混合-003")
    assert case.parameters["adjustment"] == "net_zero"
    assert case.name == "全部金额不变零金额对照"


def test_debit_and_none_problem_cases_do_not_default_to_refund_only():
    cases = {case.key: case for case in japan_case_definitions()}

    assert cases["金额-001"].parameters["g_deal_type"] == "其他"
    assert cases["金额-001"].parameters["service_deal_suggest"] == 1
    assert cases["金额-005"].parameters["g_deal_type"] == "其他"
    assert cases["手动OPTION-001"].parameters["g_deal_type"] == "其他"
    assert cases["手续费-001"].parameters["service_deal_suggest"] == 2
    assert cases["流程-007"].parameters["g_deal_type"] == "其他"


def test_problem_amount_catalog_declares_formal_completion_stage():
    case = next(case for case in japan_case_definitions() if case.key == "金额-001")

    assert case.expectation.expected_stage == "problem_goods_completed"
