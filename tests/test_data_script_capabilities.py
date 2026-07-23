from dataclasses import FrozenInstanceError

import pytest

from app.data_scripts.capabilities import (
    CAPABILITIES,
    DataScriptCapability,
    ParameterSpec,
    RiskSpec,
    available_capabilities,
    capability_catalog,
    public_capability_catalog,
    register_capability,
)
from app.data_scripts.registry import SCRIPT_REGISTRY
from app.services.data_factory_agent_tools import TOOL_SPECS
from app.services.data_factory_agent_prompts import build_analysis_prompt


@pytest.fixture(autouse=True)
def isolated_app_database():
    """Capability metadata tests are pure unit tests and never touch shared SQLite."""
    yield


def _validator(result):
    return bool(result.get("passed")), ""


def _capability(**overrides):
    values = {
        "key": "shopping_cart",
        "name": "购物车",
        "module": "order",
        "projects": ("日本站测试",),
        "intents": ("加入购物车",),
        "examples": ("加入购物车",),
        "parameters": (),
        "risk": RiskSpec(level="low", mutating=False, second_confirmation=False),
        "runner": lambda env, variables: {"passed": True},
        "result_validator": None,
        "agent_enabled": False,
    }
    values.update(overrides)
    return DataScriptCapability(**values)


def test_register_capability_projects_runner_into_legacy_registry():
    original = dict(SCRIPT_REGISTRY["shopping_cart"])
    previous = CAPABILITIES.get("shopping_cart")
    runner = lambda env, variables: {"passed": True}
    try:
        register_capability(_capability(runner=runner))

        assert SCRIPT_REGISTRY["shopping_cart"]["func"] is runner
        assert capability_catalog()["shopping_cart"].runner is runner
        assert SCRIPT_REGISTRY["shopping_cart"]["capability"] is capability_catalog()["shopping_cart"]
    finally:
        SCRIPT_REGISTRY["shopping_cart"] = original
        if previous is None:
            CAPABILITIES.pop("shopping_cart", None)
        else:
            CAPABILITIES["shopping_cart"] = previous


def test_mutating_capability_requires_result_validator():
    with pytest.raises(ValueError, match="result_validator"):
        _capability(
            key="bad",
            risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
            result_validator=None,
            agent_enabled=True,
        ).validate()


def test_capability_and_parameter_specs_are_immutable():
    spec = _capability(parameters=(ParameterSpec("keyword", "关键词", "str"),))

    with pytest.raises(FrozenInstanceError):
        spec.name = "被修改"
    with pytest.raises(TypeError):
        capability_catalog()["new"] = spec


@pytest.mark.parametrize("level", ["", "unknown", "money"])
def test_invalid_risk_level_is_rejected(level):
    with pytest.raises(ValueError, match="risk level"):
        _capability(risk=RiskSpec(level=level, mutating=False, second_confirmation=False)).validate()


def test_duplicate_parameter_names_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        _capability(
            parameters=(
                ParameterSpec("customer_ids", "客户ID", "list[str]"),
                ParameterSpec("customer_ids", "客户ID", "list[str]"),
            )
        ).validate()


@pytest.mark.parametrize(
    "key",
    ["full_flow", "resume_order_flow", "resume_porder_flow", "problem_goods"],
)
def test_core_agent_capability_is_complete(key):
    spec = capability_catalog()[key]

    assert spec.agent_enabled is True
    assert spec.projects == ("日本站测试",)
    assert spec.intents
    assert spec.examples
    assert callable(spec.result_validator)
    assert spec.idempotency_key == "contract_hash"


@pytest.mark.parametrize(
    ("tool_name", "capability_key"),
    [
        ("run_full_flow", "full_flow"),
        ("resume_order_flow", "resume_order_flow"),
        ("resume_porder_flow", "resume_porder_flow"),
        ("process_problem_goods", "problem_goods"),
    ],
)
def test_core_tool_specs_are_projected_from_capabilities(tool_name, capability_key):
    capability = capability_catalog()[capability_key]
    tool = TOOL_SPECS[tool_name]

    assert capability.name in tool.description
    assert tool.mutating is capability.risk.mutating
    assert tool.category == "组合脚本"


def test_available_capabilities_excludes_other_projects_modules_and_disabled_specs():
    specs = available_capabilities("日本站测试", {"order"})

    assert specs
    assert all("日本站测试" in spec.projects for spec in specs)
    assert all(spec.agent_enabled for spec in specs)
    assert all(spec.module == "order" for spec in specs)
    assert "balance_payment" not in {spec.key for spec in specs}
    assert "resume_porder_flow" not in {spec.key for spec in specs}


def test_available_capabilities_applies_stable_risk_and_key_order():
    specs = available_capabilities("日本站测试", {"order"}, max_risk="medium")
    ordering = [(spec.module, spec.risk.level, spec.key) for spec in specs]

    assert ordering == sorted(ordering, key=lambda item: (item[0], {"low": 0, "medium": 1}[item[1]], item[2]))
    assert all(spec.risk.level in {"low", "medium"} for spec in specs)


def test_public_capability_catalog_excludes_runner_and_account_details():
    payload = public_capability_catalog(available_capabilities("日本站测试", {"order"}))
    serialized = str(payload).lower()

    assert "runner" not in serialized
    assert "account_role" not in serialized
    assert "password" not in serialized
    assert all(set(item) == {"key", "name", "module", "intents", "examples", "parameters", "preconditions", "result_state", "risk"} for item in payload)


def test_analysis_prompt_does_not_include_unrelated_or_disabled_capabilities():
    prompt = build_analysis_prompt(
        [{"role": "user", "content": "帮我造订单到待付款"}],
        capability_specs=available_capabilities("日本站测试", {"order"}),
    )

    assert "日本站订单全流程" in prompt
    assert "已有配送单续跑" not in prompt
    assert "订单余额支付" not in prompt


@pytest.mark.parametrize(
    "key",
    ["inspect_order_state", "inspect_porder_state", "inspect_problem_goods"],
)
def test_read_only_tools_remain_explicit_non_mutating_specs(key):
    assert TOOL_SPECS[key].mutating is False
    assert TOOL_SPECS[key].category == "查询接口"
    assert key not in SCRIPT_REGISTRY


def test_shopping_cart_capability_is_enabled_without_second_confirmation():
    spec = capability_catalog()["shopping_cart"]

    assert spec.agent_enabled is True
    assert spec.risk.mutating is True
    assert spec.risk.second_confirmation is False
    assert callable(spec.result_validator)
    assert TOOL_SPECS["fill_shopping_cart"].description.startswith(spec.name)


@pytest.mark.parametrize(
    ("key", "required"),
    [
        ("warehouse_delivery", {"warehouse_sku_count", "send_num"}),
        ("direct_box_to_shelf", {"order_sn"}),
        ("material_order", {"accessory_name", "goods_id"}),
        ("material_generation", {"name"}),
    ],
)
def test_warehouse_material_metadata_declares_actual_required_inputs(key, required):
    spec = capability_catalog()[key]
    actual = {item.name for item in spec.parameters if item.required}

    assert required <= actual
    assert callable(spec.result_validator)


def test_only_verified_warehouse_capability_is_enabled():
    catalog = capability_catalog()

    assert catalog["warehouse_delivery"].agent_enabled is True
    assert TOOL_SPECS["create_and_quote_porder"].description.startswith("仓库提出配送单")
    assert catalog["direct_box_to_shelf"].agent_enabled is False
    assert catalog["material_order"].agent_enabled is False
    assert catalog["material_generation"].agent_enabled is False


def test_standard_result_validator_accepts_legacy_script_tuple():
    validator = capability_catalog()["warehouse_delivery"].result_validator

    assert validator((True, "", "", {"porder_sn": "P-1"})) == (True, "")
    assert validator((False, "", "", {"reason": "库存不足"})) == (False, "库存不足")
