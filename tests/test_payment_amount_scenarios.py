from decimal import Decimal

import pytest

from app.data_scripts.payment_amount_regression.scenarios import (
    SCENARIO_CATALOG,
    ScenarioConfigurationError,
    build_problem_goods_variables,
    problem_goods_scenarios,
)


def candidate(**overrides):
    row = {
        "order_purchase_id": 101,
        "order_detail_id": 201,
        "possible_num": 3,
        "confirm_num": 3,
        "confirm_price": "10",
        "confirm_freight": "4",
        "option": [
            {
                "id": 9,
                "name": "检品费",
                "price_type": 0,
                "price": "2",
                "num": 3,
                "checked": True,
            }
        ],
    }
    row.update(overrides)
    return row


def test_catalog_contains_twelve_unique_scenarios():
    assert len(SCENARIO_CATALOG) == 12
    assert len({scenario.key for scenario in SCENARIO_CATALOG}) == 12
    assert [scenario.category for scenario in SCENARIO_CATALOG].count("problem_goods") == 6


def test_payment_matrix_has_separate_balance_and_bank_scenarios():
    keys = {scenario.key for scenario in SCENARIO_CATALOG}

    assert {
        "order_balance",
        "order_bank",
        "order_part_balance",
        "order_part_bank",
        "porder_balance",
        "porder_bank",
    } <= keys


def test_problem_goods_matrix_declares_expected_types_and_directions():
    specs = {scenario.key: scenario for scenario in problem_goods_scenarios()}

    assert specs["problem_quantity_refund"].problem_type == 3
    assert specs["problem_price_refund"].problem_type == 1
    assert specs["problem_freight_refund"].problem_type == 2
    assert specs["problem_option_topup"].problem_type == 6
    assert specs["problem_mixed_refund"].problem_type == 5
    assert specs["problem_zero_control"].problem_type == 9
    assert specs["problem_option_topup"].expected_direction == "debit"
    assert specs["problem_zero_control"].expected_direction == "none"


def test_quantity_refund_reduces_only_quantity():
    spec = next(item for item in SCENARIO_CATALOG if item.key == "problem_quantity_refund")

    values = build_problem_goods_variables(spec, candidate())

    assert values["pre_num"] == 2
    assert values["pre_price"] == "10"
    assert values["pre_freight"] == "4"
    assert values["g_deal_type"] == "仅退款"


def test_option_topup_increases_fixed_option_price():
    spec = next(item for item in SCENARIO_CATALOG if item.key == "problem_option_topup")

    values = build_problem_goods_variables(spec, candidate())

    assert values["pre_num"] == 3
    assert values["option_deal_suggest"] == 1
    assert values["option_new"][0]["price"] == "3"


def test_mixed_refund_changes_all_money_dimensions():
    spec = next(item for item in SCENARIO_CATALOG if item.key == "problem_mixed_refund")

    values = build_problem_goods_variables(spec, candidate())

    assert values["pre_num"] == 2
    assert Decimal(values["pre_price"]) < Decimal("10")
    assert Decimal(values["pre_freight"]) < Decimal("4")
    assert Decimal(values["option_new"][0]["price"]) < Decimal("2")


def test_zero_control_keeps_values_and_uses_no_refund_policy():
    spec = next(item for item in SCENARIO_CATALOG if item.key == "problem_zero_control")

    values = build_problem_goods_variables(spec, candidate())

    assert values["pre_num"] == 3
    assert values["pre_price"] == "10"
    assert values["pre_freight"] == "4"
    assert values["service_deal_suggest"] == 1
    assert values["g_deal_type"] == "其他"


def test_option_scenario_blocks_when_no_fixed_amount_option_exists():
    spec = next(item for item in SCENARIO_CATALOG if item.key == "problem_option_topup")
    row = candidate(option=[{"name": "百分比服务", "price_type": 1, "price": "2", "checked": True}])

    with pytest.raises(ScenarioConfigurationError, match="固定金额 OPTION"):
        build_problem_goods_variables(spec, row)

