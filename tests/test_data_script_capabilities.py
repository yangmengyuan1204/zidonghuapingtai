from dataclasses import FrozenInstanceError

import pytest

import app.data_scripts as data_scripts
from app.data_scripts.capabilities import (
    CAPABILITIES,
    ContractFieldSpec,
    DataScriptCapability,
    ParameterSpec,
    RiskSpec,
    available_capabilities,
    capability_catalog,
    effective_contract_fields,
    public_capability_catalog,
    register_capability,
)
from app.data_scripts.registry import SCRIPT_REGISTRY
from app.services.data_factory_agent_tools import TOOL_SPECS
from app.services.data_factory_agent_prompts import build_analysis_prompt
from app.services import data_factory_agent as agent_service


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


def test_contract_field_rejects_secret_learning():
    field = ContractFieldSpec(
        name="backend_password",
        label="后台密码",
        path="variables.backend_password",
        group="execution",
        value_type="str",
        learnable=True,
    )

    with pytest.raises(ValueError, match="sensitive"):
        field.validate()


@pytest.mark.parametrize(
    ("path", "aliases"),
    [
        ("variables.headers.Authorization", ()),
        ("variables.credential", ()),
        ("variables.credentials", ()),
        ("variables.backend", ("api-token",)),
    ],
)
def test_contract_field_rejects_sensitive_learning_identifiers(path, aliases):
    field = ContractFieldSpec(
        name="backend_setting",
        label="后台设置",
        path=path,
        group="execution",
        value_type="str",
        aliases=aliases,
        learnable=True,
    )

    with pytest.raises(ValueError, match="sensitive"):
        field.validate()


@pytest.mark.parametrize(
    "identifier",
    [
        "password_hash",
        "passwordHash",
        "PasswordHash",
        "token_value",
        "tokenValue",
        "client_secret_key",
        "clientSecretKey",
        "clientAPIKey",
        "private_key",
        "privateKey",
        "backend_password",
        "compute_token",
        "usertoken",
        "authorization",
        "cookie",
        "secret",
        "中文密码",
        "加密凭据",
        "ｐａｓｓｗｏｒｄ",
        "ｔｏｋｅｎ",
    ],
)
def test_contract_field_rejects_shared_sensitive_identifiers(identifier):
    field = ContractFieldSpec(
        name=identifier,
        label="测试字段",
        path=f"variables.{identifier}",
        group="execution",
        value_type="str",
        learnable=True,
    )

    with pytest.raises(ValueError, match="sensitive"):
        field.validate()


@pytest.mark.parametrize(
    "identifier",
    [
        "secretary_name",
        "secretaryName",
        "token_count",
        "tokenCount",
        "TokenCount",
        "cookie_count",
        "cookieCount",
        "authorization_status",
        "authorizationStatus",
        "encrypted_flag",
        "encryptedFlag",
        "ｔｏｋｅｎ＿ｃｏｕｎｔ",
    ],
)
def test_contract_field_allows_noncredential_metadata_identifiers(identifier):
    field = ContractFieldSpec(
        name=identifier,
        label="测试字段",
        path=f"variables.{identifier}",
        group="execution",
        value_type="str",
        learnable=True,
    )

    assert field.validate() is field


def test_legacy_parameters_are_synthesized_as_contract_fields():
    capability = DataScriptCapability(
        key="demo",
        name="演示",
        module="order",
        projects=("日本站测试",),
        intents=("演示",),
        examples=("执行演示",),
        parameters=(ParameterSpec("order_sn", "订单号", "str", required=True),),
        risk=RiskSpec(level="low", mutating=False, second_confirmation=False),
        runner=lambda **_: {},
        result_validator=None,
    ).validate()

    field = effective_contract_fields(capability)[0]
    assert (field.name, field.path, field.editor) == (
        "order_sn", "variables.order_sn", "text"
    )


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


def test_problem_goods_declares_project_permission_account_strategy_metadata():
    fields = {
        field.name: field
        for field in effective_contract_fields(capability_catalog()["problem_goods"])
    }

    field = fields["permission_account_strategy"]
    assert field.path == "variables.permission_account_strategy"
    assert field.learnable is True
    assert (field.learning_mode, field.learning_scope) == ("strategy", "project")


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


@pytest.mark.parametrize("key", ["balance_recharge", "balance_adjustment"])
def test_money_capabilities_require_second_confirmation_but_remain_disabled(key):
    spec = capability_catalog()[key]

    assert spec.risk.level == "critical"
    assert spec.risk.second_confirmation is True
    assert spec.agent_enabled is False
    assert callable(spec.result_validator)


@pytest.mark.parametrize(
    "key",
    [
        "oem_new_inquiry",
        "oem_sample_order",
        "oem_sample_admin_flow",
        "oem_full_inquiry_flow",
        "oem_sample_full_flow",
        "oem_bulk_order",
        "oem_balance_pay",
    ],
)
def test_oem_capability_declares_scope_account_and_validator(key):
    spec = capability_catalog()[key]

    assert spec.module == "oem"
    assert spec.projects == ("oem-测试",)
    assert spec.account_role
    assert spec.idempotency_key == "contract_hash"
    assert callable(spec.result_validator)
    assert spec.risk.level == "high"
    assert spec.risk.second_confirmation is True
    assert spec.agent_enabled is False


@pytest.mark.parametrize(
    ("key", "required"),
    [
        ("oem_new_inquiry", set()),
        ("oem_sample_order", {"order_sn"}),
        ("oem_sample_admin_flow", {"order_sn"}),
        ("oem_full_inquiry_flow", set()),
        ("oem_sample_full_flow", set()),
        ("oem_bulk_order", {"order_sn"}),
        ("oem_balance_pay", {"order_sn"}),
    ],
)
def test_oem_capability_required_inputs_match_runner_contract(key, required):
    spec = capability_catalog()[key]

    assert {item.name for item in spec.parameters if item.required} == required


def test_every_registered_script_has_valid_capability_metadata():
    catalog = capability_catalog()

    assert set(SCRIPT_REGISTRY) == set(catalog)
    for key, item in SCRIPT_REGISTRY.items():
        spec = catalog[key]
        assert item["func"] is spec.runner
        spec.validate()


def test_agent_enabled_capabilities_are_fully_executable():
    for spec in capability_catalog().values():
        if not spec.agent_enabled:
            continue
        assert callable(spec.runner)
        assert callable(spec.result_validator)
        assert spec.examples
        assert spec.intents


def test_rollback_capability_requires_second_confirmation_and_stays_disabled():
    spec = capability_catalog()["rollback_flow"]

    assert spec.risk.level == "critical"
    assert spec.risk.second_confirmation is True
    assert spec.agent_enabled is False
    assert {item.name for item in spec.parameters if item.required} == {"rollback_target"}


def test_optional_porder_shipment_capability_matches_loaded_runner():
    runner = getattr(data_scripts, "run_porder_shipment_script", None)
    if not callable(runner):
        pytest.skip("porder shipment script is not installed")

    spec = capability_catalog()["porder_shipment"]
    assert spec.runner is runner
    assert spec.risk.second_confirmation is True
    assert spec.agent_enabled is False
    assert {item.name for item in spec.parameters if item.required} == {"porder_sn"}


def test_high_risk_contract_requires_matching_second_confirmation(monkeypatch):
    submitted = []
    session = agent_service.AgentSessionState(
        id="risk-session",
        user_id=7,
        project_id=1,
        env_id=2,
        status="awaiting_confirmation",
        goal={
            "contract_hash": "1234567890abcdef",
            "risk": {
                "level": "critical",
                "second_confirmation": True,
                "operation": "客户出入金调整",
            },
            "operations": [{"id": "operation_1", "type": "capability"}],
        },
    )
    monkeypatch.setattr(agent_service, "validate_agent_context", lambda *args: (object(), object()))
    monkeypatch.setattr(agent_service, "_latest_model_config", lambda *args: object())
    monkeypatch.setattr(agent_service, "_validate_confirmable_contract", lambda *args: object())
    monkeypatch.setattr(agent_service._EXECUTOR, "submit", lambda func, session_id: submitted.append(session_id))
    agent_service._SESSIONS[session.id] = session
    try:
        first = agent_service.confirm_agent_session(object(), session.id, 7, 1)
        assert first["status"] == "awaiting_risk_confirmation"
        assert submitted == []

        with pytest.raises(Exception) as mismatch:
            agent_service.confirm_agent_risk(
                object(), session.id, 7, 1, "ffffffffffffffff", True
            )
        assert mismatch.value.status_code == 409
        assert session.status == "awaiting_risk_confirmation"

        confirmed = agent_service.confirm_agent_risk(
            object(), session.id, 7, 1, "1234567890abcdef", True
        )
        assert confirmed["status"] == "running"
        assert submitted == [session.id]
    finally:
        agent_service.reset_agent_runtime_for_tests()
