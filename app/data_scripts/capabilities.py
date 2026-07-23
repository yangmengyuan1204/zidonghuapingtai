from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping

from .registry import SCRIPT_REGISTRY


ResultValidator = Callable[[Dict[str, Any]], tuple[bool, str]]
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


def validate_script_result(result: Dict[str, Any]) -> tuple[bool, str]:
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
    for spec in configs:
        if spec.key not in CAPABILITIES:
            register_capability(spec)


register_builtin_capabilities()
