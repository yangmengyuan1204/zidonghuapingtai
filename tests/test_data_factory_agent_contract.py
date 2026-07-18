import pytest

from app.services import data_factory_agent as agent_service
from app.services.data_factory_agent_contract import compile_contract_defaults
from app.services.data_factory_agent_intent import reduce_intent_fields


def test_minimal_new_order_uses_confirmed_business_defaults():
    result = compile_contract_defaults(
        mode="new",
        target_node="",
        variables={},
        explicit_customer_ids=[],
        context={"topbar_customer_ids": [], "bound_customer_ids": ["300001"]},
    )
    assert result.target_node == "order_offered"
    assert result.customer_ids == ["300001"]
    assert result.customer_source == "bound_account"
    assert result.variables == {
        "keyword": "衣服",
        "shop_type": "1688",
        "order_shop_count": 1,
        "order_per_shop": 1,
        "order_item_num": 1,
        "offer_price": "10",
        "order_payment_mode": "balance_first",
        "payment_fallback": "bank",
    }
    assert set(result.defaults_used) == {
        "target_node", "customer_ids", "keyword", "shop_type", "order_shop_count",
        "order_per_shop", "order_item_num", "offer_price", "order_payment_mode",
        "payment_fallback",
    }


def test_resume_order_does_not_receive_new_order_defaults():
    result = compile_contract_defaults(
        mode="resume_order",
        target_node="",
        variables={"order_sn": "2026071715475684-300001"},
        explicit_customer_ids=[],
        context={"bound_customer_ids": ["300002"]},
    )
    assert result.target_node == ""
    assert result.variables == {"order_sn": "2026071715475684-300001"}


def test_normalize_goal_applies_compiled_new_order_defaults_before_clarifying():
    status, goal, question = agent_service._normalize_goal(
        {"status": "ready", "goal": {"mode": "new", "variables": {}}},
        [{"role": "user", "content": "帮我造一个订单"}],
        compile_context={"bound_customer_ids": ["300001"]},
    )

    assert (status, question) == ("awaiting_confirmation", "")
    assert goal["target_node"] == "order_offered"
    assert goal["customer_ids"] == ["300001"]
    assert goal["customer_source"] == "bound_account"
    assert {
        key: goal["variables"][key]
        for key in (
            "keyword",
            "shop_type",
            "order_shop_count",
            "order_per_shop",
            "order_item_num",
            "offer_price",
            "order_payment_mode",
            "payment_fallback",
        )
    } == {
        "keyword": "衣服",
        "shop_type": "1688",
        "order_shop_count": 1,
        "order_per_shop": 1,
        "order_item_num": 1,
        "offer_price": "10",
        "order_payment_mode": "balance_first",
        "payment_fallback": "bank",
    }
    assert set(goal["defaults_used"]) == {
        "target_node", "customer_ids", "keyword", "shop_type", "order_shop_count",
        "order_per_shop", "order_item_num", "offer_price", "order_payment_mode",
        "payment_fallback",
    }


def test_normalize_goal_preserves_explicit_model_target_clarification():
    status, goal, question = agent_service._normalize_goal(
        {"status": "clarifying", "question": "最终要到哪个状态？", "goal": {}},
        [{"role": "user", "content": "帮我造个订单"}],
    )

    assert status == "clarifying"
    assert goal == {}
    assert question == "最终要到哪个状态？"


def test_normalize_goal_does_not_default_an_invalid_model_target():
    status, goal, question = agent_service._normalize_goal(
        {"status": "ready", "goal": {"target_node": "not_a_real_node", "variables": {}}},
        [{"role": "user", "content": "帮我造个订单"}],
    )

    assert status == "clarifying"
    assert goal == {}
    assert "最终" in question


def test_two_fan_goods_is_item_count_not_problem_item_selection():
    state = reduce_intent_fields({}, "造一个2番商品的订单，每个数量1，到待拍下后处理全部问题产品")

    fields = state["resolved_fields"]
    assert fields["item_count"]["value"] == 2
    assert "item_index" not in fields
    assert fields["problem_scope"]["value"] == "all"


def test_problem_goods_all_refund_keeps_unit_price():
    state = reduce_intent_fields({}, "两番都处理问题产品，全部退")

    fields = state["resolved_fields"]
    assert fields["problem_scope"]["value"] == "all"
    assert fields["problem_refund_quantity"]["value"] == "all"
    assert fields["problem_refund_freight"]["value"] == "all"
    assert fields["problem_preserve_price"]["value"] is True


def test_existing_order_unit_price_zero_does_not_request_shape():
    payload = {
        "status": "ready",
        "goal": {
            "mode": "resume_order",
            "order_sn": "2026071715475684-300001",
            "target_node": "",
            "variables": {},
            "operations": [{"type": "problem_goods", "evidence": "第1番单价改成0"}],
            "intent": {"pricing": {"mode": "uniform_unit", "amount": "0", "evidence": "单价改成0"}},
        },
    }

    status, goal, question = agent_service._normalize_goal(
        payload,
        [{"role": "user", "content": "订单2026071715475684-300001第1番提出问题产品，单价改成0"}],
    )

    assert status == "awaiting_confirmation"
    assert "商品种类数" not in question
    assert "购买数量" not in question
    assert goal["mode"] == "resume_order"


def test_multi_product_problem_goods_without_scope_asks_exact_scope_question():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "new",
                "target_node": "pending_purchase",
                "variables": {},
            },
        },
        [{"role": "user", "content": "造一个2番商品的订单，每个数量1，到待拍下后提出问题产品，数量全部退"}],
    )

    assert status == "clarifying"
    assert goal == {}
    assert question == "订单包含多个商品，请说明处理第几番或全部商品。"


@pytest.mark.parametrize("scope_text", ["第1番", "全部商品"])
def test_selected_problem_scope_without_change_asks_exact_change_question(scope_text):
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "new",
                "target_node": "pending_purchase",
                "variables": {},
            },
        },
        [{"role": "user", "content": f"造一个2番商品的订单，每个数量1，到待拍下后处理{scope_text}问题产品"}],
    )

    assert status == "clarifying"
    assert goal == {}
    assert question == "请说明问题产品需要修改数量、单价或国内运费，以及目标值。"


def test_explicit_third_fan_resolves_problem_item_three():
    state = reduce_intent_fields({}, "第3番提出问题产品，数量全部退")

    fields = state["resolved_fields"]
    assert fields["item_index"]["value"] == 3
    assert fields["problem_scope"]["value"] == "item"


def test_explicit_problem_quantity_and_freight_zero_survive_normalization():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "resume_order",
                "order_sn": "2026071715475684-300001",
                "variables": {},
            },
        },
        [{
            "role": "user",
            "content": "订单2026071715475684-300001第1番提出问题产品，数量改成0，国内运费改成0",
        }],
    )

    assert (status, question) == ("awaiting_confirmation", "")
    problem = goal["operations"][0]
    assert problem["scope"] == "selected_item"
    assert problem["item_index"] == 1
    assert problem["quantity_refund_mode"] == "all"
    assert problem["freight_refund_mode"] == "all"
    assert problem["price_adjustment_mode"] == "keep"


def test_follow_up_all_scope_clears_only_scope_pending_and_preserves_facts():
    state = {
        "resolved_fields": {
            "order_sn": {"value": "2026071715475684-300001", "evidence": "订单2026071715475684-300001"},
            "pricing": {"value": {"mode": "uniform_unit", "amount": "0"}, "evidence": "单价改成0"},
        },
        "pending_fields": {
            "problem_scope": {"question": "订单包含多个商品，请说明处理第几番或全部商品。"},
            "permission": {"question": "确认执行？"},
        },
        "turn_count": 1,
    }

    updated = reduce_intent_fields(state, "全部处理")

    assert updated["resolved_fields"]["problem_scope"]["value"] == "all"
    assert updated["resolved_fields"]["order_sn"]["value"] == "2026071715475684-300001"
    assert updated["resolved_fields"]["pricing"]["value"]["amount"] == "0"
    assert "problem_scope" not in updated["pending_fields"]
    assert "permission" in updated["pending_fields"]


def test_follow_up_unit_price_zero_overrides_earlier_full_refund_price_preservation():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "resume_order",
                "order_sn": "2026071715475684-300001",
                "variables": {},
            },
        },
        [
            {
                "role": "user",
                "content": "订单2026071715475684-300001第1番提出问题产品，全部退",
            },
            {"role": "user", "content": "单价改成0"},
        ],
    )

    assert (status, question) == ("awaiting_confirmation", "")
    problem = goal["operations"][0]
    assert problem["quantity_refund_mode"] == "all"
    assert problem["freight_refund_mode"] == "all"
    assert problem["price_adjustment_mode"] == "zero"


def test_problem_goods_filter_keeps_unhandled_mixed_request():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "resume_order",
                "order_sn": "2026071715475684-300001",
                "variables": {},
                "unhandled_requests": ["报价后修改收货地址"],
            },
        },
        [{
            "role": "user",
            "content": "订单2026071715475684-300001第1番提出问题产品，数量改成0，报价后修改收货地址",
        }],
    )

    assert status == "clarifying"
    assert goal == {}
    assert "报价后修改收货地址" in question


def test_selected_problem_item_with_valid_index_satisfies_scope_gate():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "resume_order",
                "order_sn": "2026071715475684-300001",
                "variables": {},
            },
        },
        [{
            "role": "user",
            "content": "订单2026071715475684-300001，2番提出问题产品，单价改成0",
        }],
    )

    assert (status, question) == ("awaiting_confirmation", "")
    problem = goal["operations"][0]
    assert problem["scope"] == "selected_item"
    assert problem["item_index"] == 2


def test_problem_goods_filter_keeps_unknown_clause_after_supported_clause():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "resume_order",
                "order_sn": "2026071715475684-300001",
                "variables": {},
                "unhandled_requests": ["提出问题产品后修改收货地址"],
            },
        },
        [{
            "role": "user",
            "content": "订单2026071715475684-300001第1番提出问题产品，数量改成0，提出问题产品后修改收货地址",
        }],
    )

    assert status == "clarifying"
    assert goal == {}
    assert "修改收货地址" in question


def test_new_order_selected_second_item_passes_late_scope_gate():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "new",
                "target_node": "pending_purchase",
                "variables": {},
            },
        },
        [{
            "role": "user",
            "content": "造一个2番商品的订单，每个数量1，到待拍下后第2番提出问题产品，数量改成0",
        }],
    )

    assert (status, question) == ("awaiting_confirmation", "")
    problem = goal["operations"][1]
    assert problem["scope"] == "selected_item"
    assert problem["item_index"] == 2


@pytest.mark.parametrize(
    ("instruction", "unhandled"),
    [
        ("退一半", "退一半"),
        ("退款2件", "退款2件"),
        ("退一半，国内运费保持不变", "国内运费保持不变"),
        ("数量不退，单价改成0", "数量不退"),
        ("只退国内运费", "只退国内运费"),
        ("退款全部国内运费", "退款全部国内运费"),
        ("退一半，附加服务全退", "附加服务全退"),
        ("退一半，附加服务都退", "附加服务都退"),
        ("退一半，附加服务全部退光", "附加服务全部退光"),
        ("退一半，附加服务清零", "附加服务清零"),
    ],
)
def test_supported_problem_expression_does_not_remain_unhandled(instruction, unhandled):
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "resume_order",
                "order_sn": "2026071715475684-300001",
                "variables": {},
                "unhandled_requests": [unhandled],
            },
        },
        [{
            "role": "user",
            "content": f"订单2026071715475684-300001第1番提出问题产品，{instruction}",
        }],
    )

    assert (status, question) == ("awaiting_confirmation", "")
    assert goal["operations"][0]["type"] == "problem_goods"
