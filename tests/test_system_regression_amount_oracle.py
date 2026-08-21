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
            {"name": "固定", "price_type": 0, "price": "2", "num": 3, "auto_calculate": True},
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
