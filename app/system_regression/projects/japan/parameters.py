from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ParameterValidationError(ValueError):
    pass


def _non_negative_decimal(value: Any, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是数字") from exc
    if not number.is_finite():
        raise ValueError(f"{label}必须是有限数字")
    if number < 0:
        raise ValueError(f"{label}不能小于0")
    return number


def _non_negative_integer(value: Any, label: str) -> int:
    number = _non_negative_decimal(value, label)
    if number != number.to_integral_value():
        raise ValueError(f"{label}必须是整数")
    return int(number)


class MoneyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Decimal
    currency: Literal["CNY", "JPY"] = "CNY"
    source: str = "case_input"

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, value: Any) -> Decimal:
        return _non_negative_decimal(value, "金额")


class OptionInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | None = None
    name: str
    name_translate: str = ""
    price_type: Literal[0, 1]
    price: Decimal
    num: int
    checked: bool = True
    auto_calculate: bool = True
    completed_num: int = 0
    completed_inspect_num: int = 0

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("OPTION名称不能为空")
        return text

    @field_validator("price", mode="before")
    @classmethod
    def validate_price(cls, value: Any) -> Decimal:
        return _non_negative_decimal(value, "OPTION价格")

    @field_validator("num", "completed_num", "completed_inspect_num", mode="before")
    @classmethod
    def validate_number(cls, value: Any) -> int:
        return _non_negative_integer(value, "OPTION数量")


class OrderDefaultsInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    item_count: int = 1
    default_quantity: int = 1
    other_fee_name: str = ""
    other_fee_amount: MoneyInput = Field(default_factory=lambda: MoneyInput(value=0))

    @field_validator("item_count", "default_quantity", mode="before")
    @classmethod
    def validate_positive_integer(cls, value: Any) -> int:
        number = _non_negative_integer(value, "订单数量")
        if number <= 0:
            raise ValueError("订单数量必须大于0")
        return number


class OrderItemInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sorting: int
    quantity: int
    purchase_price: MoneyInput | None = None
    confirm_price: MoneyInput | None = None
    offer_price: MoneyInput | None = None
    purchase_freight: MoneyInput | None = None
    confirm_freight: MoneyInput | None = None
    offer_freight: MoneyInput | None = None
    options: list[OptionInput] = Field(default_factory=list)

    @field_validator("sorting", "quantity", mode="before")
    @classmethod
    def validate_integer(cls, value: Any) -> int:
        return _non_negative_integer(value, "单番数量")


class ProblemGoodsInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    problem_type: int
    problem_num: int = 1
    problem_description: str = "系统回归问题产品"
    translation_content: str = "システム回帰テスト"
    pre_num: int
    pre_price: MoneyInput
    pre_freight: MoneyInput
    client_deal_choice: Literal["accept", "exchange", "cancel", "discard", "other"] = "accept"
    client_deal_other: str = ""
    service_deal_suggest: Literal[1, 2] = 2
    option_deal_suggest: Literal[1, 2] = 2
    option_new: list[OptionInput] = Field(default_factory=list)
    g_deal_type: Literal["退货退款", "换货", "丢货重拍", "少货补买", "其他", "仅退款"] = "仅退款"
    business_decision: str = "系统回归自动处理"
    purchase_remark: str = "系统回归"

    @field_validator("problem_type", mode="before")
    @classmethod
    def validate_problem_type(cls, value: Any) -> int:
        number = _non_negative_integer(value, "问题类型")
        if number not in range(1, 11):
            raise ValueError("问题类型必须为1到10")
        return number

    @field_validator("problem_num", "pre_num", mode="before")
    @classmethod
    def validate_problem_integer(cls, value: Any) -> int:
        return _non_negative_integer(value, "问题产品数量")


class JapanCaseParameters(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_key: Literal["japan"] = "japan"
    order: OrderDefaultsInput = Field(default_factory=OrderDefaultsInput)
    items: list[OrderItemInput] = Field(default_factory=list)
    problem_goods: ProblemGoodsInput | None = None
    tolerance_jpy: int = 1
    ledger_wait_seconds: int = 30

    @field_validator("tolerance_jpy", "ledger_wait_seconds", mode="before")
    @classmethod
    def validate_runtime_integer(cls, value: Any) -> int:
        return _non_negative_integer(value, "运行参数")


def validate_option_changes(original: Any, updated: Any) -> list[OptionInput]:
    try:
        original_rows = [OptionInput.model_validate(row) for row in (original or [])]
        updated_rows = [OptionInput.model_validate(row) for row in (updated or [])]
    except ValidationError as exc:
        raise ParameterValidationError(str(exc)) from exc
    original_types = {row.name: row.price_type for row in original_rows}
    seen: set[str] = set()
    for row in updated_rows:
        if row.name in seen:
            raise ParameterValidationError(f"OPTION名称重复：{row.name}")
        seen.add(row.name)
        if row.name in original_types and original_types[row.name] != row.price_type:
            raise ParameterValidationError(f"不允许修改OPTION计价类型：{row.name}")
    return updated_rows


def validate_case_parameters(
    runner_kind: str,
    payload: dict[str, Any],
    *,
    current_num: int | None = None,
    original_options: Any = None,
) -> JapanCaseParameters:
    try:
        values = JapanCaseParameters.model_validate(payload)
    except ValidationError as exc:
        raise ParameterValidationError(str(exc)) from exc
    if runner_kind not in {"problem_goods", "problem_flow", "problem_guard"}:
        return values
    problem = values.problem_goods
    if problem is None:
        raise ParameterValidationError("问题产品参数不能为空")
    if problem.client_deal_choice == "other" and not problem.client_deal_other.strip():
        raise ParameterValidationError("客户选择其他时必须填写客户回复")
    if problem.g_deal_type == "其他" and not problem.purchase_remark.strip():
        raise ParameterValidationError("选择其他时采购处理备注不能为空")
    if original_options is not None and problem.option_deal_suggest == 1:
        validate_option_changes(original_options, [row.model_dump() for row in problem.option_new])
    if problem.option_deal_suggest == 2:
        baseline_num = current_num if current_num is not None else (values.items[0].quantity if values.items else None)
        if baseline_num is not None and problem.pre_num > baseline_num:
            raise ParameterValidationError("商品数量增加时必须选择按照业务修改值计算OPTION")
        active_options = [row for item in values.items for row in item.options if row.checked]
        if baseline_num is not None and any(row.num > baseline_num for row in active_options):
            raise ParameterValidationError("OPTION数量大于商品数，必须选择按照业务修改值计算")
        if sum(1 for row in active_options if row.price_type == 1) > 1:
            raise ParameterValidationError("存在多个百分比OPTION，必须选择按照业务修改值计算")
    return values


__all__ = [
    "JapanCaseParameters",
    "MoneyInput",
    "OptionInput",
    "OrderItemInput",
    "ParameterValidationError",
    "validate_case_parameters",
    "validate_option_changes",
]
