from decimal import Decimal

from app.system_regression.common.amount_oracle import expected_problem_amount


def _candidate():
    return {
        "possible_num": 3,
        "confirm_price": "10",
        "confirm_freight": "3",
        "service_rate": "0.1",
        "service_fee_paid": True,
        "option": [
            {"id": 79, "name": "固定", "price_type": 0, "price": "2", "num": 3, "auto_calculate": True},
        ],
    }


def test_problem_oracle_calculates_goods_freight_service_and_option_refund():
    result = expected_problem_amount(
        _candidate(),
        {
            "pre_num": 2,
            "pre_price": "9",
            "pre_freight": "2",
            "service_deal_suggest": 2,
            "option_deal_suggest": 2,
            "complete_inspect_num": 0,
        },
    )

    assert result.direction == "credit"
    assert result.goods_cny == Decimal("-12.00")
    assert result.freight_cny == Decimal("-1.00")
    assert result.service_cny == Decimal("-1.20")
    assert result.option_cny == Decimal("-2.00")
    assert result.total_cny == Decimal("-16.20")


def test_problem_oracle_returns_zero_for_unchanged_case():
    result = expected_problem_amount(
        _candidate(),
        {
            "pre_num": 3,
            "pre_price": "10",
            "pre_freight": "3",
            "service_deal_suggest": 1,
            "option_deal_suggest": 2,
        },
    )

    assert result.direction == "none"
    assert result.total_cny == Decimal("0.00")


def test_problem_oracle_reads_runtime_option_order_quantity():
    candidate = _candidate()
    candidate["option"] = [
        {"id": 79, "name": "固定", "price_type": 0, "price": "2", "num": 0, "order_num": 3},
    ]

    result = expected_problem_amount(
        candidate,
        {
            "pre_num": 3,
            "pre_price": "10",
            "pre_freight": "3",
            "service_deal_suggest": 1,
            "option_deal_suggest": 1,
            "option_new": [],
        },
    )

    assert result.option_cny == Decimal("-6.00")
    assert result.total_cny == Decimal("-6.00")


def test_problem_oracle_uses_runtime_service_rate_for_discounted_order_adjustment():
    candidate = _candidate()
    candidate["service_rate"] = "0.045"

    result = expected_problem_amount(
        candidate,
        {
            "pre_num": 3,
            "pre_price": "9",
            "pre_freight": "3",
            "service_deal_suggest": 2,
            "service_discount": True,
            "option_deal_suggest": 0,
        },
    )

    assert result.goods_cny == Decimal("-3.00")
    assert result.service_cny == Decimal("-0.14")
    assert result.total_cny == Decimal("-3.14")


def test_problem_oracle_matches_same_name_options_by_id():
    candidate = _candidate()
    candidate["option"] = [
        {"id": 78, "name": "检品", "price_type": 0, "price": "2", "num": 1},
        {"id": 79, "name": "检品", "price_type": 0, "price": "3", "num": 1},
    ]

    result = expected_problem_amount(
        candidate,
        {
            "pre_num": 3,
            "pre_price": "10",
            "pre_freight": "3",
            "service_deal_suggest": 1,
            "option_deal_suggest": 1,
            "option_new": [
                {"id": 78, "name": "检品", "price_type": 0, "price": "2", "num": 1},
            ],
        },
    )

    assert result.option_cny == Decimal("-3.00")


def test_problem_oracle_allows_new_option_without_runtime_id():
    candidate = _candidate()

    result = expected_problem_amount(
        candidate,
        {
            "pre_num": 3,
            "pre_price": "10",
            "pre_freight": "3",
            "service_deal_suggest": 1,
            "option_deal_suggest": 1,
            "option_new": [
                *candidate["option"],
                {"name": "系统回归OPTION", "price_type": 0, "price": "1", "num": 1},
            ],
        },
    )

    assert result.option_cny == Decimal("1.00")
