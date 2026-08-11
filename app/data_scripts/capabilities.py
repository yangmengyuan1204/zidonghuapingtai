from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping

from ._legacy import FULL_FLOW_NODE_LABELS
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
ALLOWED_EDITORS = {"text", "number", "decimal", "select", "checkbox", "id_list", "readonly"}
ALLOWED_LEARNING_MODES = {"none", "value", "pattern", "strategy"}
ALLOWED_LEARNING_SCOPES = {"project", "global"}
_SENSITIVE_IDENTIFIER_PARTS = {
    "authorization",
    "ciphertext",
    "cookie",
    "credential",
    "credentials",
    "encrypted",
    "passwd",
    "password",
    "pwd",
    "secret",
    "token",
    "usertoken",
}
_NON_CREDENTIAL_METADATA_SUFFIXES = {"count", "flag", "status"}


def is_sensitive_field_identifier(identifier: Any) -> bool:
    identifier = unicodedata.normalize("NFKC", str(identifier or ""))
    tokenized = re.sub(
        r"(?<=[A-Z])(?=[A-Z][a-z])",
        "_",
        identifier,
    )
    tokenized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", tokenized)
    normalized = re.sub(
        r"[^0-9a-z\u4e00-\u9fff]+",
        "_",
        tokenized.casefold(),
    ).strip("_")
    if not normalized:
        return False
    if any(marker in normalized for marker in ("密码", "口令", "令牌", "凭据")):
        return True
    parts = tuple(part for part in normalized.split("_") if part)
    if any(
        parts[index : index + 2] in {("private", "key"), ("api", "key")}
        for index in range(len(parts) - 1)
    ):
        return True
    for index, part in enumerate(parts):
        if part not in _SENSITIVE_IDENTIFIER_PARTS:
            continue
        if (
            part in {"token", "cookie", "authorization", "encrypted"}
            and index == len(parts) - 2
            and parts[-1] in _NON_CREDENTIAL_METADATA_SUFFIXES
        ):
            continue
        return True
    return False


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
class ContractFieldSpec:
    name: str
    label: str
    path: str
    group: str
    value_type: str
    required: bool = False
    default: Any = None
    sources: tuple[str, ...] = (
        "natural_language",
        "page_context",
        "environment",
        "default",
    )
    aliases: tuple[str, ...] = ()
    editor: str = "text"
    choices: tuple[tuple[str, str], ...] = ()
    readonly: bool = False
    execution_field: bool = True
    learnable: bool = True
    learning_mode: str = "value"
    learning_scope: str = "project"

    def validate(self) -> "ContractFieldSpec":
        if not all(str(item).strip() for item in (self.name, self.label, self.path, self.group, self.value_type)):
            raise ValueError("contract field identity is required")
        if self.editor not in ALLOWED_EDITORS:
            raise ValueError("contract field editor is invalid")
        if not self.sources or set(self.sources) - ALLOWED_PARAMETER_SOURCES:
            raise ValueError("contract field contains invalid sources")
        if self.learning_mode not in ALLOWED_LEARNING_MODES:
            raise ValueError("contract field learning mode is invalid")
        if self.learning_scope not in ALLOWED_LEARNING_SCOPES:
            raise ValueError("contract field learning scope is invalid")
        if self.learnable and any(
            is_sensitive_field_identifier(identifier)
            for identifier in (self.name, self.path, *self.aliases)
        ):
            raise ValueError("sensitive contract field cannot be learnable")
        if self.readonly and self.editor != "readonly":
            raise ValueError("readonly contract field must use readonly editor")
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
    contract_fields: tuple[ContractFieldSpec, ...] = ()

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
        contract_fields = [field.validate() for field in self.contract_fields]
        contract_names = [field.name for field in contract_fields]
        contract_paths = [field.path for field in contract_fields]
        if len(contract_names) != len(set(contract_names)):
            raise ValueError("capability contract field names must be unique")
        if len(contract_paths) != len(set(contract_paths)):
            raise ValueError("capability contract field paths must be unique")
        return self


def effective_contract_fields(
    capability: DataScriptCapability,
) -> tuple[ContractFieldSpec, ...]:
    if capability.contract_fields:
        return tuple(field.validate() for field in capability.contract_fields)
    return tuple(
        ContractFieldSpec(
            name=item.name,
            label=item.label,
            path=f"variables.{item.name}",
            group="task_scope" if item.name.endswith("_sn") else "business",
            value_type=item.value_type,
            required=item.required,
            default=item.default,
            sources=item.sources,
            editor="number" if item.value_type == "int" else (
                "decimal" if item.value_type == "decimal" else "text"
            ),
            learning_mode="pattern" if item.name.endswith("_sn") else "value",
        ).validate()
        for item in capability.parameters
    )


FULL_FLOW_NODE_CHOICES = tuple(FULL_FLOW_NODE_LABELS.items())
OFFER_UNIT_PRICES_FIELD = ContractFieldSpec(
    "offer_unit_prices",
    "逐商品单价",
    "variables.offer_unit_prices",
    "goods_price",
    "list[str]",
    aliases=("逐商品单价", "各商品价格"),
    editor="text",
)
CORE_FIELDS = (
    ContractFieldSpec(
        "customer_ids", "客户ID", "customer_ids", "task_scope", "list[str]",
        aliases=("客户", "客户id"), editor="id_list", learning_mode="pattern",
    ),
    ContractFieldSpec(
        "order_sn", "订单号", "order_sn", "task_scope", "str",
        aliases=("订单", "订单编号"), editor="text", learning_mode="pattern",
    ),
    ContractFieldSpec(
        "porder_sn", "配送单号", "porder_sn", "task_scope", "str",
        aliases=("配送单", "配送单编号"), editor="text", learning_mode="pattern",
    ),
    ContractFieldSpec(
        "target_node", "目标状态", "target_node", "task_scope", "node",
        aliases=("做到", "执行到"), editor="select",
        choices=FULL_FLOW_NODE_CHOICES, learning_mode="value",
    ),
    ContractFieldSpec(
        "order_shop_count", "店铺数", "variables.order_shop_count", "goods_price", "int",
        default=1, aliases=("店铺", "店"), editor="number",
    ),
    ContractFieldSpec(
        "order_per_shop", "每店商品种类", "variables.order_per_shop", "goods_price", "int",
        default=1, aliases=("每店商品", "商品种类"), editor="number",
    ),
    ContractFieldSpec(
        "order_item_num", "每种购买数量", "variables.order_item_num", "goods_price", "int",
        default=1, aliases=("购买数量", "每种数量"), editor="number",
    ),
    ContractFieldSpec(
        "offer_price", "统一单价", "variables.offer_price", "goods_price", "decimal",
        default="10", aliases=("单价", "价格"), editor="decimal",
    ),
    OFFER_UNIT_PRICES_FIELD,
)
PAYMENT_FALLBACK_FIELD = ContractFieldSpec(
    "payment_fallback", "余额不足降级方式", "variables.payment_fallback", "payment", "str",
    default="bank", aliases=("余额不足", "降级支付"), editor="select",
    choices=(("bank", "银行支付"),), learning_mode="strategy",
)
ORDER_PAYMENT_FIELDS = (
    ContractFieldSpec(
        "order_payment_mode", "订单支付方式", "variables.order_payment_mode", "payment", "str",
        default="balance_first", aliases=("支付方式", "订单支付"), editor="select",
        choices=(("balance_first", "余额优先"), ("bank", "银行支付")),
        learning_mode="strategy",
    ),
    PAYMENT_FALLBACK_FIELD,
    ContractFieldSpec(
        "finance_confirm", "银行入金确认", "variables.finance_confirm", "payment", "bool",
        default=True, aliases=("入金", "财务确认"), editor="checkbox",
        learning_mode="strategy",
    ),
)
PORDER_PAYMENT_FIELDS = (
    ContractFieldSpec(
        "porder_payment_mode", "配送单支付方式", "variables.porder_payment_mode", "payment", "str",
        default="balance_first", aliases=("配送单支付",), editor="select",
        choices=(("balance_first", "余额优先"), ("bank", "银行支付")),
        learning_mode="strategy",
    ),
)
PROBLEM_GOODS_FIELDS = (
    ContractFieldSpec(
        "permission_account_strategy",
        "权限接管账号策略",
        "variables.permission_account_strategy",
        "problem_goods",
        "dict",
        aliases=("权限接管账号", "后台账号档案"),
        editor="readonly",
        readonly=True,
        learning_mode="strategy",
        learning_scope="project",
    ),
    ContractFieldSpec(
        "scope", "处理范围", "variables.scope", "problem_goods", "str",
        aliases=("问题产品范围", "处理范围"), editor="select",
        choices=(
            ("single_or_all_if_one", "单个候选（仅一个时）"),
            ("selected_item", "指定商品"),
            ("all_candidates", "全部商品"),
        ),
    ),
    ContractFieldSpec(
        "item_index", "商品序号", "variables.item_index", "problem_goods", "int",
        default=1, aliases=("第几番", "商品序号"), editor="number",
    ),
    ContractFieldSpec(
        "quantity_refund_mode", "退款数量", "variables.quantity_refund_mode", "problem_goods", "str",
        default="keep", aliases=("退款数量", "退数量"), editor="select",
        choices=(("keep", "保持不变"), ("all", "全部退款"), ("half", "退一半"), ("fixed", "指定数量")),
    ),
    ContractFieldSpec(
        "quantity_refund_value", "指定退款数量", "variables.quantity_refund_value", "problem_goods", "int",
        default=0, aliases=("退几件", "退款件数"), editor="number",
    ),
    ContractFieldSpec(
        "price_adjustment_mode", "商品金额处理", "variables.price_adjustment_mode", "problem_goods", "str",
        default="keep", aliases=("商品金额", "单价调整"), editor="select",
        choices=(("keep", "保持不变"), ("zero", "单价归零"), ("fixed", "指定单价")),
    ),
    ContractFieldSpec(
        "price_adjustment_value", "调整后单价", "variables.price_adjustment_value", "problem_goods", "decimal",
        default="0", aliases=("调整单价", "问题产品单价"), editor="decimal",
    ),
    ContractFieldSpec(
        "freight_refund_mode", "国内运费处理", "variables.freight_refund_mode", "problem_goods", "str",
        default="keep", aliases=("国内运费", "退运费"), editor="select",
        choices=(("keep", "保持不变"), ("all", "全部退款")),
    ),
    ContractFieldSpec(
        "option_refund_mode", "附加服务处理", "variables.option_refund_mode", "problem_goods", "str",
        default="keep", aliases=("附加服务", "option"), editor="select",
        choices=(("keep", "保持不变"), ("all", "全部退款")),
    ),
)
EXECUTION_FIELDS = (
    ContractFieldSpec(
        "inferred_items", "推断项", "assumptions", "execution", "list[str]",
        editor="readonly", readonly=True, execution_field=False, learnable=False,
        learning_mode="none",
    ),
    ContractFieldSpec(
        "operation_order", "操作顺序", "steps", "execution", "list[str]",
        editor="readonly", readonly=True, execution_field=False, learnable=False,
        learning_mode="none",
    ),
    ContractFieldSpec(
        "plan_version", "合同版本", "plan_version", "execution", "int",
        editor="readonly", readonly=True, execution_field=False, learnable=False,
        learning_mode="none",
    ),
    ContractFieldSpec(
        "contract_hash", "合同哈希", "contract_hash", "execution", "str",
        editor="readonly", readonly=True, execution_field=False, learnable=False,
        learning_mode="none",
    ),
)


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
            contract_fields=(
                CORE_FIELDS
                + ORDER_PAYMENT_FIELDS
                + PORDER_PAYMENT_FIELDS
                + PROBLEM_GOODS_FIELDS
                + EXECUTION_FIELDS
            ),
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
            contract_fields=(
                CORE_FIELDS
                + ORDER_PAYMENT_FIELDS
                + PROBLEM_GOODS_FIELDS
                + EXECUTION_FIELDS
            ),
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
            contract_fields=(
                CORE_FIELDS
                + PORDER_PAYMENT_FIELDS
                + (PAYMENT_FALLBACK_FIELD,)
                + EXECUTION_FIELDS
            ),
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
            contract_fields=(
                CORE_FIELDS + PROBLEM_GOODS_FIELDS + EXECUTION_FIELDS
            ),
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
            key="balance_recharge",
            name="客户余额充值",
            module="funds",
            projects=("日本站测试",),
            intents=("客户余额充值",),
            examples=("给客户300001充值100元",),
            parameters=(
                ParameterSpec("customer_id", "客户ID", "str", required=True),
                ParameterSpec("amount", "充值金额", "decimal", required=True),
            ),
            risk=RiskSpec(level="critical", mutating=True, second_confirmation=True),
            runner=data_scripts.run_balance_recharge_script,
            result_validator=validate_script_result,
            account_role="frontend_and_backend_finance",
            result_state="balance_recharged",
            idempotency_key="contract_hash",
            agent_enabled=False,
        ),
        DataScriptCapability(
            key="balance_adjustment",
            name="客户出入金调整",
            module="funds",
            projects=("日本站测试",),
            intents=("客户入金调整", "客户出金调整"),
            examples=("客户300001入金调整100元",),
            parameters=(
                ParameterSpec("customer_id", "客户ID", "str", required=True),
                ParameterSpec("adjustment_type", "调整方向", "enum[1,2]", required=True),
                ParameterSpec("amount", "调整金额", "decimal", required=True),
                ParameterSpec("adjust_reason", "调整原因", "str", required=True),
                ParameterSpec("client_bill_reason", "客户账单原因", "str", required=True),
            ),
            risk=RiskSpec(level="critical", mutating=True, second_confirmation=True),
            runner=data_scripts.run_balance_adjustment_script,
            result_validator=validate_script_result,
            account_role="backend_finance",
            result_state="balance_adjusted",
            idempotency_key="contract_hash",
            agent_enabled=False,
        ),
        DataScriptCapability(
            key="payment_amount_regression",
            name="支付金额自动回归",
            module="funds",
            projects=("日本站测试",),
            intents=("支付金额回归", "校验付款流水金额"),
            examples=("执行支付金额自动回归，默认选择全部场景",),
            parameters=(
                ParameterSpec("customer_id", "客户ID", "str"),
                ParameterSpec("payment_regression_batch_id", "回归批次", "str"),
            ),
            risk=RiskSpec(level="critical", mutating=True, second_confirmation=True),
            runner=data_scripts.run_payment_amount_regression_script,
            result_validator=validate_script_result,
            account_role="frontend_and_backend_finance",
            result_state="payment_amount_regression_completed",
            idempotency_key="contract_hash",
            agent_enabled=False,
        ),
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
    oem_configs = (
        (
            "oem_new_inquiry",
            "OEM创建询价单",
            data_scripts.run_oem_new_inquiry_script,
            (),
            "inquiry_sn",
            "oem_frontend",
            "inquiry_created",
        ),
        (
            "oem_sample_order",
            "OEM提出样品单",
            data_scripts.run_oem_sample_order_script,
            (ParameterSpec("order_sn", "询价单号", "str", required=True),),
            "order_sn",
            "oem_frontend",
            "sample_order_created",
        ),
        (
            "oem_sample_admin_flow",
            "OEM样品单后台流程",
            data_scripts.run_oem_sample_admin_flow_script,
            (ParameterSpec("order_sn", "样品单号", "str", required=True),),
            "order_sn",
            "oem_backend",
            "sample_admin_flow_completed",
        ),
        (
            "oem_full_inquiry_flow",
            "OEM询价单全流程",
            data_scripts.run_oem_full_inquiry_flow_script,
            (ParameterSpec("order_sn", "已有询价单号", "str"),),
            "order_sn",
            "oem_frontend_and_backend",
            "inquiry_quote_completed",
        ),
        (
            "oem_sample_full_flow",
            "OEM样品单全流程",
            data_scripts.run_oem_sample_full_flow_script,
            (ParameterSpec("order_sn", "已有询价单号", "str"),),
            "sample_order_sn",
            "oem_frontend_and_backend",
            "sample_flow_completed",
        ),
        (
            "oem_bulk_order",
            "OEM大货单下单",
            data_scripts.run_oem_bulk_order_script,
            (ParameterSpec("order_sn", "询价单号", "str", required=True),),
            "large_order_sn",
            "oem_frontend",
            "bulk_order_created",
        ),
        (
            "oem_balance_pay",
            "OEM样品单余额支付",
            data_scripts.run_oem_sample_balance_pay_script,
            (ParameterSpec("order_sn", "样品单号", "str", required=True),),
            "order_sn",
            "oem_frontend",
            "sample_order_paid",
        ),
    )
    configs += tuple(
        DataScriptCapability(
            key=key,
            name=name,
            module="oem",
            projects=("oem-测试",),
            intents=(name,),
            examples=(f"执行{name}，仅处理一个业务单据",),
            parameters=parameters,
            risk=RiskSpec(level="high", mutating=True, second_confirmation=True),
            runner=runner,
            result_validator=validate_script_result,
            account_role=account_role,
            preconditions=("当前环境属于 oem-测试 项目",),
            result_state=result_state,
            resume_key=resume_key,
            idempotency_key="contract_hash",
            agent_enabled=False,
        )
        for key, name, runner, parameters, resume_key, account_role, result_state in oem_configs
    )
    configs += (
        DataScriptCapability(
            key="rollback_flow",
            name="日本站业务状态回退",
            module="rollback",
            projects=("日本站测试",),
            intents=("回退订单状态", "回退配送单状态", "回退采购单状态"),
            examples=("将订单状态回退到指定业务节点",),
            parameters=(
                ParameterSpec("rollback_target", "回退目标", "node", required=True),
                ParameterSpec("order_sn", "订单号", "str"),
                ParameterSpec("porder_sn", "配送单号", "str"),
                ParameterSpec("purchase_no", "采购单号", "str"),
            ),
            risk=RiskSpec(level="critical", mutating=True, second_confirmation=True),
            runner=data_scripts.run_rollback_flow_script,
            result_validator=validate_script_result,
            account_role="backend_admin",
            preconditions=("业务单号与回退目标必须匹配",),
            result_state="rollback_target_reached",
            resume_key="order_sn",
            idempotency_key="contract_hash",
            agent_enabled=False,
        ),
    )
    porder_shipment_runner = getattr(data_scripts, "run_porder_shipment_script", None)
    if callable(porder_shipment_runner):
        configs += (
            DataScriptCapability(
                key="porder_shipment",
                name="配送单出货",
                module="porder",
                projects=("日本站测试",),
                intents=("配送单出货", "填写物流单号并出货"),
                examples=("配送单P2024-001自动填写物流单号并提交出货",),
                parameters=(ParameterSpec("porder_sn", "配送单号", "str", required=True),),
                risk=RiskSpec(level="high", mutating=True, second_confirmation=True),
                runner=porder_shipment_runner,
                result_validator=validate_script_result,
                account_role="backend_admin",
                preconditions=("配送单已支付且具备可出货箱子",),
                result_state="porder_shipped",
                resume_key="porder_sn",
                idempotency_key="contract_hash",
                agent_enabled=False,
            ),
        )
    for spec in configs:
        if spec.key not in CAPABILITIES:
            register_capability(spec)


register_builtin_capabilities()
