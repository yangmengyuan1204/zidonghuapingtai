from dataclasses import FrozenInstanceError

import pytest

from app.data_scripts.capabilities import (
    CAPABILITIES,
    DataScriptCapability,
    ParameterSpec,
    RiskSpec,
    capability_catalog,
    register_capability,
)
from app.data_scripts.registry import SCRIPT_REGISTRY


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
