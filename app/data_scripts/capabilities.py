from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping

from .registry import SCRIPT_REGISTRY


ResultValidator = Callable[[Any], tuple[bool, str]]
Runner = Callable[[Any, Dict[str, Any]], Any]
ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
ALLOWED_PARAMETER_SOURCES = {
    "natural_language",
    "page_context",
    "environment",
    "default",
}


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    label: str
    value_type: str
    required: bool = False
    default: Any = None
    sources: tuple[str, ...] = (
        "natural_language",
        "page_context",
        "environment",
        "default",
    )

    def validate(self) -> "ParameterSpec":
        if not self.name.strip() or not self.label.strip() or not self.value_type.strip():
            raise ValueError("parameter name, label, and value_type are required")
        if not self.sources or set(self.sources) - ALLOWED_PARAMETER_SOURCES:
            raise ValueError("parameter contains invalid sources")
        return self


@dataclass(frozen=True)
class RiskSpec:
    level: str
    mutating: bool
    second_confirmation: bool

    def validate(self) -> "RiskSpec":
        if self.level not in ALLOWED_RISK_LEVELS:
            raise ValueError("invalid risk level")
        if not self.mutating and self.second_confirmation:
            raise ValueError("read-only capability cannot require second confirmation")
        return self


@dataclass(frozen=True)
class DataScriptCapability:
    key: str
    name: str
    module: str
    projects: tuple[str, ...]
    intents: tuple[str, ...]
    examples: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]
    risk: RiskSpec
    runner: Runner
    result_validator: ResultValidator | None
    account_role: str = ""
    preconditions: tuple[str, ...] = ()
    result_state: str = ""
    resume_key: str = ""
    idempotency_key: str = ""
    agent_enabled: bool = False

    def validate(self) -> "DataScriptCapability":
        if not self.key.strip() or not self.name.strip() or not self.module.strip():
            raise ValueError("capability key, name, and module are required")
        if not callable(self.runner):
            raise ValueError("capability runner is required")
        self.risk.validate()
        if self.risk.mutating and not callable(self.result_validator):
            raise ValueError("mutating capability requires result_validator")
        if not self.projects or not all(str(item).strip() for item in self.projects):
            raise ValueError("capability projects are required")
        if not self.intents or not self.examples:
            raise ValueError("capability intents and examples are required")
        names = [parameter.validate().name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("capability parameter names must be unique")
        return self


CAPABILITIES: Dict[str, DataScriptCapability] = {}


def register_capability(spec: DataScriptCapability) -> None:
    validated = spec.validate()
    CAPABILITIES[validated.key] = validated
    legacy = SCRIPT_REGISTRY.setdefault(validated.key, {})
    legacy.update(
        {
            "name": validated.name,
            "func": validated.runner,
            "capability": validated,
        }
    )


def capability_catalog() -> Mapping[str, DataScriptCapability]:
    return MappingProxyType(dict(CAPABILITIES))


def available_capabilities(
    project_name: str,
    modules: set[str],
    max_risk: str | None = None,
) -> list[DataScriptCapability]:
    if max_risk is not None and max_risk not in RISK_ORDER:
        raise ValueError("invalid max risk level")
    risk_limit = RISK_ORDER[max_risk] if max_risk else RISK_ORDER["critical"]
    selected = [
        spec
        for spec in CAPABILITIES.values()
        if spec.agent_enabled
        and str(project_name) in spec.projects
        and spec.module in set(modules or set())
        and RISK_ORDER[spec.risk.level] <= risk_limit
    ]
    return sorted(
        selected,
        key=lambda spec: (spec.module, RISK_ORDER[spec.risk.level], spec.key),
    )


def public_capability_catalog(
    specs: list[DataScriptCapability] | tuple[DataScriptCapability, ...],
) -> list[dict]:
    return [
        {
            "key": spec.key,
            "name": spec.name,
            "module": spec.module,
            "intents": list(spec.intents),
            "examples": list(spec.examples),
            "parameters": [
                {
                    "name": item.name,
                    "label": item.label,
                    "required": item.required,
                    "default": item.default,
                }
                for item in spec.parameters
            ],
            "preconditions": list(spec.preconditions),
            "result_state": spec.result_state,
            "risk": {
                "level": spec.risk.level,
                "second_confirmation": spec.risk.second_confirmation,
            },
        }
        for spec in specs
    ]


def validate_script_result(result: Any) -> tuple[bool, str]:
    if isinstance(result, tuple) and result:
        passed = bool(result[0])
        summary = result[3] if len(result) > 3 and isinstance(result[3], dict) else {}
        reason = str(summary.get("reason") or "脚本未返回成功证据")
        return passed, "" if passed else reason
    if not isinstance(result, dict):
        return False, "脚本未返回结构化结果"
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    passed = bool(
        result.get("passed") is True
        or result.get("result") == "passed"
        or result.get("status") in {"passed", "succeeded", "completed"}
        or summary.get("completed_all") is True
    )
    reason = str(summary.get("reason") or result.get("reason") or "脚本未返回成功证据")
    return passed, "" if passed else reason


def register_builtin_capabilities() -> None:
    """Registration hook populated incrementally by verified capability groups."""
    import app.data_scripts as data_scripts

    configs = (
        DataScriptCapability(
            key="shopping_cart",
            name="购物车准备",
            module="order",
            projects=("日本站测试",),
            intents=("加入购物车", "准备购物车商品"),
            examples=("搜索衣服，准备1个店1种商品",),
            parameters=(
                ParameterSpec("keyword", "商品关键词", "str", default="衣服"),
                ParameterSpec("shop_type", "店铺类型", "str", default="1688"),
                ParameterSpec("target_shops", "目标店铺数", "int", default=1),
                ParameterSpec("per_shop", "每店商品数", "int", default=1),
            ),
            risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
            runner=data_scripts.run_shopping_cart_script,
            result_validator=validate_script_result,
            account_role="frontend",
            result_state="shopping_cart_ready",
            idempotency_key="contract_hash",
            agent_enabled=True,
        ),
        DataScriptCapability(
            key="full_flow",
            name="日本站订单全流程",
            module="order",
            projects=("日本站测试",),
            intents=("新建订单", "造订单", "订单做到指定状态"),
            examples=("帮我造一个订单到待付款", "创建两种商品各一件做到上架"),
            parameters=(
                ParameterSpec("customer_ids", "客户ID", "list[str]"),
                ParameterSpec("order_shop_count", "店铺数", "int", default=1),
                ParameterSpec("order_per_shop", "每店商品数", "int", default=1),
                ParameterSpec("order_item_num", "每种购买数量", "int", default=1),
                ParameterSpec("offer_price", "统一单价", "decimal", default="10"),
                ParameterSpec("stop_after_node", "目标节点", "node", default="order_offered"),
            ),
            risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
            runner=data_scripts.run_full_flow_script,
            result_validator=validate_script_result,
            account_role="frontend_and_backend",
            result_state="contract_target_node",
            resume_key="order_sn",
            idempotency_key="contract_hash",
            agent_enabled=True,
        ),
        DataScriptCapability(
            key="resume_order_flow",
            name="已有订单续跑",
            module="order",
            projects=("日本站测试",),
            intents=("继续订单", "订单续跑"),
            examples=("订单2026071715475684-300001继续到待拍下",),
            parameters=(
                ParameterSpec("order_sn", "订单号", "str", required=True),
                ParameterSpec("stop_after_node", "目标节点", "node", required=True),
            ),
            risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
            runner=data_scripts.run_resume_order_flow_script,
            result_validator=validate_script_result,
            account_role="frontend_and_backend",
            preconditions=("订单号属于当前项目环境",),
            result_state="contract_target_node",
            resume_key="order_sn",
            idempotency_key="contract_hash",
            agent_enabled=True,
        ),
        DataScriptCapability(
            key="resume_porder_flow",
            name="已有配送单续跑",
            module="porder",
            projects=("日本站测试",),
            intents=("继续配送单", "配送单续跑"),
            examples=("配送单P2024-001继续到支付完成",),
            parameters=(
                ParameterSpec("porder_sn", "配送单号", "str", required=True),
                ParameterSpec("stop_after_node", "目标节点", "node", required=True),
            ),
            risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
            runner=data_scripts.run_resume_porder_flow_script,
            result_validator=validate_script_result,
            account_role="frontend_and_backend",
            preconditions=("配送单号属于当前项目环境",),
            result_state="contract_target_node",
            resume_key="porder_sn",
            idempotency_key="contract_hash",
            agent_enabled=True,
        ),
        DataScriptCapability(
            key="problem_goods",
            name="日本站问题产品处理",
            module="problem_goods",
            projects=("日本站测试",),
            intents=("提出问题产品", "处理问题产品", "问题产品退款"),
            examples=("订单2026071715475684-300001第1番单价改成0",),
            parameters=(
                ParameterSpec("order_sn", "订单号", "str", required=True),
                ParameterSpec("problem_scope", "处理范围", "scope", required=True),
            ),
            risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
            runner=data_scripts.run_problem_goods_script,
            result_validator=validate_script_result,
            account_role="frontend_and_backend",
            preconditions=("问题产品候选已查询",),
            result_state="problem_goods_completed",
            resume_key="problem_goods_id",
            idempotency_key="contract_hash",
            agent_enabled=True,
        ),
    )
    standard_configs = (
        ("order_quote", "订单报价", "order", data_scripts.run_order_quote_script, "medium", False, True, "order_sn"),
        ("balance_payment", "订单余额支付", "order", data_scripts.run_balance_payment_script, "high", True, False, "order_sn"),
        ("bank_payment", "订单银行支付", "order", data_scripts.run_bank_payment_script, "high", True, False, "order_sn"),
        ("purchase_to_shelf", "待拍下到上架", "order", data_scripts.run_purchase_to_shelf_script, "medium", False, True, "order_sn"),
        ("purchase_to_shelf_chain", "待拍下到上架组合流程", "order", data_scripts.run_purchase_to_shelf_chain, "medium", False, True, "order_sn"),
        ("porder_balance_payment", "配送单余额支付", "porder", data_scripts.run_porder_balance_payment_script, "high", True, False, "porder_sn"),
        ("porder_bank_payment", "配送单银行支付", "porder", data_scripts.run_porder_bank_payment_script, "high", True, False, "porder_sn"),
    )
    configs += tuple(
        DataScriptCapability(
            key=key,
            name=name,
            module=module,
            projects=("日本站测试",),
            intents=(name,),
            examples=(f"{name}，单号由当前任务取得",),
            parameters=(
                ParameterSpec(
                    identifier,
                    "配送单号" if identifier == "porder_sn" else "订单号",
                    "str",
                    required=True,
                ),
            ),
            risk=RiskSpec(
                level=risk_level,
                mutating=True,
                second_confirmation=second_confirmation,
            ),
            runner=runner,
            result_validator=validate_script_result,
            account_role="frontend_and_backend",
            resume_key=identifier,
            idempotency_key="contract_hash",
            agent_enabled=enabled,
        )
        for key, name, module, runner, risk_level, second_confirmation, enabled, identifier in standard_configs
    )
    configs += (
        DataScriptCapability(
            key="warehouse_delivery",
            name="仓库提出配送单",
            module="warehouse",
            projects=("日本站测试",),
            intents=("仓库提出配送单", "从仓库商品创建配送单"),
            examples=("从仓库选2番，每番提出1件并创建配送单",),
            parameters=(
                ParameterSpec("warehouse_sku_count", "仓库提出番数", "int", required=True),
                ParameterSpec("send_num", "每番提出数量", "int", required=True),
            ),
            risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
            runner=data_scripts.run_warehouse_delivery_script,
            result_validator=validate_script_result,
            account_role="frontend_and_backend",
            result_state="warehouse_delivery_created",
            resume_key="porder_sn",
            idempotency_key="contract_hash",
            agent_enabled=True,
        ),
        DataScriptCapability(
            key="direct_box_to_shelf",
            name="直接装箱上架",
            module="warehouse",
            projects=("日本站测试",),
            intents=("直接装箱上架",),
            examples=("订单号明确后直接装箱并上架",),
            parameters=(ParameterSpec("order_sn", "订单号", "str", required=True),),
            risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
            runner=data_scripts.run_direct_box_to_shelf_script,
            result_validator=validate_script_result,
            account_role="frontend_and_backend",
            result_state="shelf_stored",
            resume_key="order_sn",
            idempotency_key="contract_hash",
            agent_enabled=False,
        ),
        DataScriptCapability(
            key="material_order",
            name="辅料单",
            module="material",
            projects=("日本站测试",),
            intents=("创建辅料单",),
            examples=("为商品123创建名称为包装袋的辅料单",),
            parameters=(
                ParameterSpec("accessory_name", "辅料名称", "str", required=True),
                ParameterSpec("goods_id", "商品ID", "int", required=True),
            ),
            risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
            runner=data_scripts.run_material_order_script,
            result_validator=validate_script_result,
            account_role="frontend",
            result_state="material_order_created",
            idempotency_key="contract_hash",
            agent_enabled=False,
        ),
        DataScriptCapability(
            key="material_generation",
            name="辅料生成",
            module="material",
            projects=("日本站测试",),
            intents=("批量生成辅料",),
            examples=("以包装袋为基础名称生成3个辅料",),
            parameters=(
                ParameterSpec("name", "辅料基础名称", "str", required=True),
                ParameterSpec("count", "生成数量", "int", default=1),
            ),
            risk=RiskSpec(level="medium", mutating=True, second_confirmation=False),
            runner=data_scripts.run_material_generation_script,
            result_validator=validate_script_result,
            account_role="frontend",
            result_state="materials_created",
            idempotency_key="contract_hash",
            agent_enabled=False,
        ),
    )
    for spec in configs:
        if spec.key not in CAPABILITIES:
            register_capability(spec)


register_builtin_capabilities()
