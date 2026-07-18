from app.services import data_factory_agent as agent_service
from app.services.data_factory_agent_contract import compile_contract_defaults


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
        "keyword": "琛ｆ湇",
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
        [{"role": "user", "content": "甯垜閫犱竴涓鍗昤"}],
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
        "keyword": "琛ｆ湇",
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
