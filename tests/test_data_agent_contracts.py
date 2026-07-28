import copy
import hashlib
import json
from decimal import Decimal

import pytest

from app.data_scripts.capabilities import (
    ContractFieldSpec,
    DataScriptCapability,
    RiskSpec,
    capability_catalog,
    effective_contract_fields,
)
from app.services.data_agent_contracts import (
    ContractValidationError,
    apply_contract_updates,
    build_contract_editor_schema,
    diff_execution_contract,
    normalize_execution_contract,
)


FULL_FLOW = capability_catalog()["full_flow"]


def _full_flow_without_per_item_prices() -> DataScriptCapability:
    return DataScriptCapability(
        **{
            **FULL_FLOW.__dict__,
            "contract_fields": tuple(
                field
                for field in effective_contract_fields(FULL_FLOW)
                if field.name != "offer_unit_prices"
            ),
        }
    ).validate()


def _metadata_capability() -> DataScriptCapability:
    return DataScriptCapability(
        key="metadata_demo",
        name="元数据演示",
        module="order",
        projects=("日本站测试",),
        intents=("演示",),
        examples=("执行演示",),
        parameters=(),
        risk=RiskSpec(level="low", mutating=False, second_confirmation=False),
        runner=lambda *_: {},
        result_validator=None,
        contract_fields=(
            ContractFieldSpec(
                "count", "数量", "variables.count", "business", "int", default=1,
                editor="number",
            ),
            ContractFieldSpec(
                "price", "单价", "variables.price", "business", "decimal", default="10",
                editor="decimal",
            ),
            ContractFieldSpec(
                "customer_ids", "客户", "customer_ids", "scope", "list[str]", default=[],
                editor="id_list",
            ),
            ContractFieldSpec(
                "enabled", "启用", "variables.enabled", "business", "bool", default=False,
                editor="checkbox",
            ),
            ContractFieldSpec(
                "mode", "模式", "variables.mode", "business", "str", default="single",
                editor="select", choices=(("single", "单个"), ("batch", "批量")),
            ),
            ContractFieldSpec(
                "note", "说明", "note", "display", "str", execution_field=False,
                learnable=False,
            ),
            ContractFieldSpec(
                "readonly_id", "只读ID", "readonly_id", "display", "str", readonly=True,
                editor="readonly", execution_field=False, learnable=False,
            ),
        ),
    ).validate()


def test_display_only_change_does_not_reduce_first_hit():
    initial = {
        "target_node": "order_offered",
        "target_label": "订单待付款",
        "variables": {"order_item_num": 1},
    }
    final = {
        "target_node": "order_offered",
        "target_label": "待付款",
        "variables": {"order_item_num": 1},
    }
    assert normalize_execution_contract(initial, FULL_FLOW) == normalize_execution_contract(
        final, FULL_FLOW
    )
    assert diff_execution_contract(initial, final, FULL_FLOW, "direct_edit") == []


def test_apply_updates_rejects_unknown_field():
    with pytest.raises(ContractValidationError) as exc_info:
        apply_contract_updates(
            {"variables": {}}, {"backend_password": "secret"}, FULL_FLOW
        )
    assert exc_info.value.errors == {"backend_password": "字段不属于当前脚本合同"}


def test_editor_schema_marks_inferred_customer_source():
    goal = {
        "customer_ids": ["300001"],
        "field_sources": {"customer_ids": "environment"},
        "inferred_fields": ["customer_ids"],
        "variables": {},
    }
    customer = next(
        item
        for item in build_contract_editor_schema(FULL_FLOW, goal)
        if item["name"] == "customer_ids"
    )
    assert customer["inferred"] is True
    assert customer["source"] == "environment"


def test_normalize_execution_contract_coerces_declared_value_types():
    capability = _metadata_capability()
    goal = {
        "customer_ids": "300001， 300002",
        "variables": {
            "count": "2",
            "price": Decimal("2.500"),
            "enabled": "否",
            "mode": "single",
        },
    }

    assert normalize_execution_contract(goal, capability) == {
        "count": 2,
        "price": "2.5",
        "customer_ids": ["300001", "300002"],
        "enabled": False,
        "mode": "single",
    }


def test_apply_updates_coerces_values_and_returns_only_execution_diffs():
    capability = _metadata_capability()
    goal = {
        "customer_ids": ["300001"],
        "variables": {"count": 1, "price": "10", "enabled": False, "mode": "single"},
        "note": "旧说明",
        "untouched": {"keep": True},
    }

    updated, diffs = apply_contract_updates(
        goal,
        {
            "count": "3",
            "price": "4.00",
            "customer_ids": "300003, 300004",
            "enabled": "yes",
            "mode": "batch",
            "note": "新说明",
        },
        capability,
    )

    assert updated["variables"] == {
        "count": 3,
        "price": "4",
        "enabled": True,
        "mode": "batch",
    }
    assert updated["customer_ids"] == ["300003", "300004"]
    assert updated["note"] == "新说明"
    assert updated["untouched"] == {"keep": True}
    assert {item["field"] for item in diffs} == {
        "count", "price", "customer_ids", "enabled", "mode"
    }
    assert {item["source"] for item in diffs} == {"direct_edit"}


def test_apply_updates_rejects_negative_offer_price_without_mutating_goal():
    goal = {
        "variables": {
            "order_shop_count": 1,
            "order_per_shop": 1,
            "order_item_num": 1,
            "offer_price": "10",
        }
    }
    original = copy.deepcopy(goal)

    with pytest.raises(ContractValidationError) as exc_info:
        apply_contract_updates(goal, {"offer_price": "-0.01"}, FULL_FLOW)

    assert exc_info.value.errors == {"offer_price": "不能小于0"}
    assert goal == original


def test_apply_updates_collects_readonly_and_choice_errors_without_mutating_goal():
    capability = _metadata_capability()
    goal = {"variables": {"mode": "single"}, "readonly_id": "R-1"}

    with pytest.raises(ContractValidationError) as exc_info:
        apply_contract_updates(
            goal, {"mode": "unsupported", "readonly_id": "R-2"}, capability
        )

    assert exc_info.value.errors == {
        "mode": "字段值不在允许选项中",
        "readonly_id": "字段为只读",
    }
    assert goal == {"variables": {"mode": "single"}, "readonly_id": "R-1"}


def test_apply_updates_rejects_invalid_bool_and_invalid_existing_contract():
    capability = _metadata_capability()
    with pytest.raises(ContractValidationError) as bool_error:
        apply_contract_updates({"variables": {}}, {"enabled": "maybe"}, capability)
    assert bool_error.value.errors == {"enabled": "必须是布尔值"}

    with pytest.raises(ContractValidationError) as existing_error:
        apply_contract_updates(
            {"variables": {"count": "invalid"}}, {"note": "新说明"}, capability
        )
    assert existing_error.value.errors == {"count": "必须是整数"}


def test_apply_updates_clears_declared_conflicting_price_field():
    base = _metadata_capability()
    capability = DataScriptCapability(
        **{
            **base.__dict__,
            "contract_fields": base.contract_fields
            + (
                ContractFieldSpec(
                    "offer_price", "统一单价", "variables.offer_price", "business",
                    "decimal", editor="decimal",
                ),
                ContractFieldSpec(
                    "offer_unit_prices", "逐商品单价", "variables.offer_unit_prices",
                    "business", "list[str]", editor="text",
                ),
            ),
        }
    ).validate()
    goal = {
        "variables": {
            "count": 1,
            "price": "10",
            "enabled": False,
            "mode": "single",
            "offer_price": "10",
            "offer_unit_prices": ["1", "2"],
        }
    }

    updated, _ = apply_contract_updates(goal, {"offer_price": "3"}, capability)

    assert updated["variables"]["offer_price"] == "3"
    assert "offer_unit_prices" not in updated["variables"]


def test_apply_updates_recomputes_price_summary_and_stable_contract_hash():
    goal = {
        "variables": {
            "order_shop_count": 2,
            "order_per_shop": 2,
            "order_item_num": 3,
            "offer_price": "10",
        },
        "intent": {"pricing": {"mode": "default_unit"}},
        "summary": "旧摘要",
        "contract_hash": "old",
    }

    updated, diffs = apply_contract_updates(goal, {"offer_price": "2.50"}, FULL_FLOW)
    repeated, repeated_diffs = apply_contract_updates(
        updated, {"offer_price": "2.5"}, FULL_FLOW
    )

    assert updated["intent"]["pricing"]["effective_unit_prices"] == ["2.5"] * 4
    assert updated["intent"]["pricing"]["effective_goods_total"] == "30"
    assert updated["summary"] != "旧摘要"
    assert len(updated["contract_hash"]) == 16
    assert repeated["contract_hash"] == updated["contract_hash"]
    assert repeated_diffs == []
    assert diffs == [
        {"field": "offer_price", "before": "10", "after": "2.5", "source": "direct_edit"}
    ]


def test_goods_total_shape_update_syncs_uniform_price_to_declared_runner_variable():
    goal = {
        "variables": {
            "order_shop_count": 1,
            "order_per_shop": 1,
            "order_item_num": 1,
            "offer_price": "100",
        },
        "intent": {
            "pricing": {
                "mode": "goods_total",
                "requested_goods_total": "100",
                "effective_unit_prices": ["100"],
                "effective_goods_total": "100",
            }
        },
    }

    updated, _ = apply_contract_updates(goal, {"order_per_shop": 2}, FULL_FLOW)

    assert updated["variables"]["offer_price"] == "50"
    assert "offer_unit_prices" not in updated["variables"]
    assert updated["intent"]["pricing"]["effective_unit_prices"] == ["50", "50"]
    assert updated["intent"]["pricing"]["effective_goods_total"] == "100"
    normalized = normalize_execution_contract(updated, FULL_FLOW)
    assert normalized["offer_price"] == "50"
    assert "统一单价50" in updated["summary"]
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    assert updated["contract_hash"] == hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:16]


def test_goods_total_shape_update_rejects_unrepresentable_price_split():
    goal = {
        "variables": {
            "order_shop_count": 1,
            "order_per_shop": 1,
            "order_item_num": 1,
            "offer_price": "100",
        },
        "intent": {
            "pricing": {
                "mode": "goods_total",
                "requested_goods_total": "100",
            }
        },
    }

    with pytest.raises(ContractValidationError) as exc_info:
        apply_contract_updates(
            goal,
            {"order_per_shop": 3},
            _full_flow_without_per_item_prices(),
        )

    assert set(exc_info.value.errors) == {"offer_price"}


def test_goods_total_shape_update_uses_declared_per_item_price_field():
    capability = FULL_FLOW
    goal = {
        "variables": {
            "order_shop_count": 1,
            "order_per_shop": 1,
            "order_item_num": 1,
            "offer_price": "100",
        },
        "intent": {
            "pricing": {
                "mode": "goods_total",
                "requested_goods_total": "100",
            }
        },
    }

    updated, _ = apply_contract_updates(goal, {"order_per_shop": 3}, capability)

    assert updated["variables"]["offer_unit_prices"] == ["33.34", "33.33", "33.33"]
    assert "offer_price" not in updated["variables"]
    normalized = normalize_execution_contract(updated, capability)
    assert normalized["offer_price"] is None
    assert normalized["offer_unit_prices"] == ["33.34", "33.33", "33.33"]
    schema = build_contract_editor_schema(capability, updated)
    assert next(item for item in schema if item["name"] == "offer_price")["value"] is None
    assert "统一单价10" not in updated["summary"]
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    assert updated["contract_hash"] == hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:16]


def test_mutually_exclusive_prices_use_uniform_value_then_default():
    capability = FULL_FLOW
    uniform_goal = {
        "variables": {
            "order_shop_count": 1,
            "order_per_shop": 1,
            "order_item_num": 1,
            "offer_price": "25",
        }
    }

    normalized = normalize_execution_contract(uniform_goal, capability)
    schema = build_contract_editor_schema(capability, uniform_goal)

    assert normalized["offer_price"] == "25"
    assert normalized["offer_unit_prices"] is None
    assert next(
        item for item in schema if item["name"] == "offer_unit_prices"
    )["value"] is None

    empty_goal = {"variables": {}}
    empty_normalized = normalize_execution_contract(empty_goal, capability)
    empty_schema = build_contract_editor_schema(capability, empty_goal)
    assert empty_normalized["offer_price"] == "10"
    assert empty_normalized["offer_unit_prices"] is None
    assert next(item for item in empty_schema if item["name"] == "offer_price")[
        "value"
    ] == "10"


def test_apply_updates_rejects_two_active_price_fields_without_mutating_goal():
    capability = FULL_FLOW
    goal = {
        "variables": {
            "order_shop_count": 1,
            "order_per_shop": 2,
            "order_item_num": 1,
            "offer_price": "10",
        }
    }
    original = copy.deepcopy(goal)

    with pytest.raises(ContractValidationError) as exc_info:
        apply_contract_updates(
            goal,
            {"offer_price": "20", "offer_unit_prices": ["30", "40"]},
            capability,
        )

    message = "统一单价与逐商品单价不能同时填写"
    assert exc_info.value.errors == {
        "offer_price": message,
        "offer_unit_prices": message,
    }
    assert goal == original
