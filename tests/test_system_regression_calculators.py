from decimal import Decimal

from app.system_regression.projects.japan.calculators import calculate_problem_amount


def base_payload(**overrides):
    payload = {
        "old_total_num": 3,
        "old_possible_num": 3,
        "old_price": "20",
        "new_num": 2,
        "new_price": "20",
        "old_freight": "5",
        "new_freight": "2",
        "service_rate": "0.10",
        "service_deal_suggest": 2,
        "service_fee_paid": True,
        "service_discount": False,
        "goods_fee_free": False,
        "option_deal_suggest": 1,
        "option_old": [{"name": "加急", "price_type": 0, "price": "5", "num": 3, "checked": True}],
        "option_new": [{"name": "加急", "price_type": 0, "price": "5", "num": 2, "checked": True}],
        "complete_inspect_num": 0,
    }
    payload.update(overrides)
    return payload


def test_problem_total_uses_goods_freight_service_and_option():
    result = calculate_problem_amount(base_payload())

    assert result.goods_delta == Decimal("-20.00")
    assert result.freight_delta == Decimal("-3.00")
    assert result.service_delta == Decimal("-2.00")
    assert result.option_delta == Decimal("-5.00")
    assert result.total_cny == Decimal("-30.00")


def test_service_fee_respects_keep_rule_discount_and_zero_rate():
    keep = calculate_problem_amount(base_payload(service_deal_suggest=1))
    discounted = calculate_problem_amount(base_payload(service_discount=True))
    zero_rate = calculate_problem_amount(base_payload(service_rate="0"))

    assert keep.service_delta == 0
    assert discounted.service_delta == 0
    assert zero_rate.service_delta == 0


def test_goods_increase_charges_service_unless_discounted():
    charged = calculate_problem_amount(
        base_payload(new_num=4, new_price="20", new_freight="5", option_old=[], option_new=[])
    )
    discounted = calculate_problem_amount(
        base_payload(new_num=4, new_price="20", new_freight="5", option_old=[], option_new=[], service_discount=True)
    )

    assert charged.goods_delta == Decimal("20.00")
    assert charged.service_delta == Decimal("2.00")
    assert discounted.service_delta == 0


def test_manual_percentage_option_uses_new_goods_price_and_option_quantity():
    result = calculate_problem_amount(
        base_payload(
            new_num=3,
            new_price="30",
            new_freight="5",
            service_rate="0",
            option_old=[{"name": "检品", "price_type": 1, "price": "10", "num": 3, "checked": True}],
            option_new=[{"name": "检品", "price_type": 1, "price": "10", "num": 2, "checked": True}],
        )
    )

    assert result.option_delta == Decimal("0.00")


def test_auto_inspection_option_keeps_completed_quantity_paid():
    result = calculate_problem_amount(
        base_payload(
            old_total_num=5,
            old_possible_num=5,
            new_num=2,
            old_price="10",
            new_price="10",
            old_freight="0",
            new_freight="0",
            service_rate="0",
            option_deal_suggest=2,
            option_old=[{"name": "检品", "price_type": 0, "price": "2", "num": 5, "checked": True, "auto_calculate": True}],
            option_new=[],
            complete_inspect_num=3,
        )
    )

    assert result.option_delta == Decimal("0.00")


def test_free_goods_rule_zeroes_goods_and_service_delta():
    result = calculate_problem_amount(base_payload(goods_fee_free=True))

    assert result.goods_delta == 0
    assert result.service_delta == 0
