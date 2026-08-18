from decimal import Decimal

import pytest

from app.system_regression.projects.japan.parameters import (
    ParameterValidationError,
    validate_case_parameters,
    validate_option_changes,
)


def fixed_option(**overrides):
    row = {
        "id": 11,
        "name": "加急服务",
        "name_translate": "特急サービス",
        "price_type": 0,
        "price": "5",
        "num": 3,
        "checked": True,
        "auto_calculate": True,
    }
    row.update(overrides)
    return row


def rate_option(**overrides):
    row = fixed_option(name="详细检品", name_translate="詳細検品", price_type=1, price="4")
    row.update(overrides)
    return row


def valid_problem_payload(**problem_overrides):
    problem = {
        "problem_type": 3,
        "problem_num": 1,
        "pre_num": 2,
        "pre_price": {"value": "20", "currency": "CNY", "source": "confirm_price"},
        "pre_freight": {"value": "3", "currency": "CNY", "source": "purchase_freight"},
        "client_deal_choice": "accept",
        "service_deal_suggest": 2,
        "option_deal_suggest": 1,
        "option_new": [fixed_option(num=2)],
        "g_deal_type": "仅退款",
        "business_decision": "系统回归自动处理",
        "problem_description": "系统回归问题产品",
        "translation_content": "システム回帰テスト",
        "purchase_remark": "系统回归",
    }
    problem.update(problem_overrides)
    return {
        "project_key": "japan",
        "order": {
            "item_count": 1,
            "default_quantity": 3,
            "other_fee_name": "包装材料费",
            "other_fee_amount": {"value": "5", "currency": "CNY", "source": "case_input"},
        },
        "items": [
            {
                "sorting": 1,
                "quantity": 3,
                "confirm_price": {"value": "20", "currency": "CNY", "source": "case_input"},
                "confirm_freight": {"value": "3", "currency": "CNY", "source": "case_input"},
                "options": [fixed_option()],
            }
        ],
        "problem_goods": problem,
        "tolerance_jpy": 1,
        "ledger_wait_seconds": 30,
    }


def test_structured_form_payload_preserves_money_items_and_options():
    result = validate_case_parameters("problem_goods", valid_problem_payload(), current_num=3)

    assert result.order.other_fee_name == "包装材料费"
    assert result.order.other_fee_amount.value == Decimal("5")
    assert result.items[0].confirm_freight.currency == "CNY"
    assert result.items[0].options[0].name == "加急服务"
    assert result.problem_goods.pre_price.source == "confirm_price"
    assert result.problem_goods.business_decision == "系统回归自动处理"
    assert result.problem_goods.problem_description == "系统回归问题产品"
    assert result.problem_goods.translation_content == "システム回帰テスト"


def test_part_pay_percent_zero_and_coupon_selected_id_are_kept():
    payload = valid_problem_payload()
    payload["part_pay"] = {"enabled": True, "percent": 0, "tail_node": "before_shelf"}
    payload["coupon"] = {"selectedId": "__service_discount__"}
    payload["porder"] = {"box_length": 58, "box_width": 51, "box_height": 50, "box_weight": 10, "logistics": "25"}

    result = validate_case_parameters("problem_goods", payload, current_num=3)

    assert result.part_pay.enabled is True
    assert result.part_pay.percent == 0
    assert result.coupon.selected_id == "__service_discount__"
    assert result.porder.box_length == Decimal("58")
    assert int(result.porder.box_length * result.porder.box_width * result.porder.box_height) == 147900


def test_quantity_increase_rejects_auto_option():
    payload = valid_problem_payload(pre_num=4, option_deal_suggest=2, option_new=[])

    with pytest.raises(ParameterValidationError, match="数量增加"):
        validate_case_parameters("problem_goods", payload, current_num=3)


def test_auto_option_rejects_option_count_over_goods_and_multiple_rate_options():
    over_count = valid_problem_payload(option_deal_suggest=2, option_new=[], pre_num=2)
    over_count["items"][0]["options"] = [fixed_option(num=4)]
    with pytest.raises(ParameterValidationError, match="OPTION数量大于商品数"):
        validate_case_parameters("problem_goods", over_count, current_num=3)

    multiple_rate = valid_problem_payload(option_deal_suggest=2, option_new=[], pre_num=2)
    multiple_rate["items"][0]["options"] = [rate_option(), rate_option(id=12, name="附加检品")]
    with pytest.raises(ParameterValidationError, match="多个百分比OPTION"):
        validate_case_parameters("problem_goods", multiple_rate, current_num=3)


def test_existing_option_cannot_change_price_type():
    original = [fixed_option()]
    updated = [fixed_option(price_type=1)]

    with pytest.raises(ParameterValidationError, match="计价类型"):
        validate_option_changes(original, updated)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"client_deal_choice": "other", "client_deal_other": ""}, "客户回复"),
        ({"g_deal_type": "其他", "purchase_remark": ""}, "采购处理备注"),
    ],
)
def test_other_choices_require_plain_text_inputs(overrides, message):
    with pytest.raises(ParameterValidationError, match=message):
        validate_case_parameters("problem_goods", valid_problem_payload(**overrides), current_num=3)


def test_negative_money_and_fractional_quantity_are_rejected():
    negative = valid_problem_payload()
    negative["order"]["other_fee_amount"]["value"] = "-1"
    with pytest.raises(ParameterValidationError, match="不能小于0"):
        validate_case_parameters("problem_goods", negative, current_num=3)

    fractional = valid_problem_payload(pre_num="1.5")
    with pytest.raises(ParameterValidationError, match="整数"):
        validate_case_parameters("problem_goods", fractional, current_num=3)
