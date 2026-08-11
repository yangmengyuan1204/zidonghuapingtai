from __future__ import annotations

from typing import Any, Iterable

from ...common.catalog import CaseExpectation, RegressionCaseDefinition


JAPAN_REQUIRED_IDENTITIES = ("admin", "client")


def _success(
    key: str,
    name: str,
    category: str,
    direction: str,
    *,
    runner_kind: str,
    parameters: dict[str, Any] | None = None,
    tags: Iterable[str] = (),
    expected_stage: str = "",
) -> tuple[str, str, str, str, dict[str, Any], CaseExpectation, tuple[str, ...]]:
    return (
        key,
        name,
        category,
        runner_kind,
        dict(parameters or {}),
        CaseExpectation(
            outcome="success",
            direction=direction,
            required_identities=JAPAN_REQUIRED_IDENTITIES,
            expected_stage=expected_stage or (
                "problem_goods_completed" if runner_kind in {"problem_goods", "problem_flow"} else ""
            ),
        ),
        tuple(tags),
    )


def _guard(
    key: str,
    name: str,
    *,
    guard_kind: str,
    error_keywords: Iterable[str],
    error_codes: Iterable[str] = (),
    parameters: dict[str, Any] | None = None,
) -> tuple[str, str, str, str, dict[str, Any], CaseExpectation, tuple[str, ...]]:
    values = {"guard_kind": guard_kind, **dict(parameters or {})}
    return (
        key,
        name,
        "problem_guard",
        "problem_guard",
        values,
        CaseExpectation(
            outcome="guard",
            error_codes=tuple(error_codes),
            error_keywords=tuple(error_keywords),
            required_identities=JAPAN_REQUIRED_IDENTITIES,
        ),
        ("问题产品", "预期拦截"),
    )


def _raw_definitions():
    payment = (
        _success("JP-PAY-001", "单番余额全额支付", "payment", "debit", runner_kind="order_payment", parameters={"payment_mode": "balance", "payment_plan": "full"}, tags=("支付", "余额")),
        _success("JP-PAY-002", "单番银行全额支付", "payment", "debit", runner_kind="order_payment", parameters={"payment_mode": "bank", "payment_plan": "full", "finance_confirm": True}, tags=("支付", "银行")),
        _success("JP-PAY-003", "余额分批付款", "payment", "debit", runner_kind="order_part_payment", parameters={"payment_mode": "balance", "payment_plan": "part", "first_payment_rate": "0.5"}, tags=("支付", "分批")),
        _success("JP-PAY-004", "银行分批付款", "payment", "debit", runner_kind="order_part_payment", parameters={"payment_mode": "bank", "payment_plan": "part", "first_payment_rate": "0.5", "finance_confirm": True}, tags=("支付", "分批", "银行")),
        _success("JP-PAY-005", "配送单余额支付", "payment", "debit", runner_kind="porder_payment", parameters={"payment_mode": "balance"}, tags=("支付", "配送单")),
        _success("JP-PAY-006", "配送单银行支付", "payment", "debit", runner_kind="porder_payment", parameters={"payment_mode": "bank", "finance_confirm": True}, tags=("支付", "配送单", "银行")),
        _success("JP-PAY-007", "多单番独立国内运费", "payment", "debit", runner_kind="order_payment", parameters={"payment_mode": "balance", "item_count": 2, "per_item_freight": True}, tags=("支付", "多番", "国内运费")),
        _success("JP-PAY-008", "其他费用金额与名义", "payment", "debit", runner_kind="order_payment", parameters={"payment_mode": "balance", "other_fee_name": "包装材料费", "other_fee_amount": "5"}, tags=("支付", "其他费用")),
        _success("JP-PAY-009", "多 OPTION 混合", "payment", "debit", runner_kind="order_payment", parameters={"payment_mode": "balance", "option_profile": "fixed_and_rate"}, tags=("支付", "OPTION")),
        _success("JP-PAY-010", "全费用混合订单", "payment", "debit", runner_kind="order_payment", parameters={"payment_mode": "balance", "fee_profile": "all"}, tags=("支付", "综合费用")),
    )

    amount_rows = (
        ("客户原因零金额对照", 9, "unchanged", "none"),
        ("少货数量部分减少", 3, "quantity_partial_down", "credit"),
        ("少货数量全部减少至零", 3, "quantity_all_down", "credit"),
        ("单价下调退款", 1, "price_down", "credit"),
        ("单价上调补款", 1, "price_up", "debit"),
        ("单条采购运费下调退款", 2, "freight_down", "credit"),
        ("单条采购运费上调补款", 2, "freight_up", "debit"),
        ("不良且少货数量减少", 5, "quantity_down", "credit"),
        ("不良且少货数量和单价下调", 5, "quantity_and_price_down", "credit"),
        ("不良数量减少且单价上调", 4, "quantity_down_price_up_net_refund", "credit"),
        ("单价下调运费上调净退款", 8, "price_down_freight_up_net_refund", "credit"),
        ("单价上调运费下调净补款", 8, "price_up_freight_down_net_topup", "debit"),
    )
    amounts = tuple(
        _success(
            f"JP-PG-AMT-{index:03d}",
            name,
            "problem_amount",
            direction,
            runner_kind="problem_goods",
            parameters={"problem_type": problem_type, "adjustment": adjustment},
            tags=("问题产品", "基础金额"),
        )
        for index, (name, problem_type, adjustment, direction) in enumerate(amount_rows, 1)
    )

    service_rows = (
        ("商品减少手续费多退少补", "goods_down_refund_service", 2, False, "credit"),
        ("商品减少手续费已收不退", "goods_down_keep_service", 1, False, "credit"),
        ("商品增加补收手续费", "goods_up_charge_service", 2, False, "debit"),
        ("手续费减免券下商品减少", "goods_down_discount_service", 2, True, "credit"),
        ("手续费减免券下商品增加", "goods_up_discount_service", 2, True, "debit"),
        ("单番手续费率为零", "zero_service_rate", 2, False, "credit"),
    )
    services = tuple(
        _success(
            f"JP-PG-SVC-{index:03d}",
            name,
            "problem_service_fee",
            direction,
            runner_kind="problem_goods",
            parameters={"problem_type": 1, "adjustment": adjustment, "service_deal_suggest": rule, "service_discount": discount},
            tags=("问题产品", "手续费"),
        )
        for index, (name, adjustment, rule, discount, direction) in enumerate(service_rows, 1)
    )

    manual_option_rows = (
        ("新增固定金额 OPTION", "fixed_add", "debit"),
        ("删除固定金额 OPTION", "fixed_delete", "credit"),
        ("固定 OPTION 数量增加", "fixed_num_up", "debit"),
        ("固定 OPTION 数量减少", "fixed_num_down", "credit"),
        ("固定 OPTION 单价增加", "fixed_price_up", "debit"),
        ("固定 OPTION 单价减少", "fixed_price_down", "credit"),
        ("新增百分比 OPTION", "rate_add", "debit"),
        ("删除百分比 OPTION", "rate_delete", "credit"),
        ("百分比 OPTION 数量增加", "rate_num_up", "debit"),
        ("百分比 OPTION 数量减少", "rate_num_down", "credit"),
        ("OPTION 百分比提高", "rate_price_up", "debit"),
        ("OPTION 百分比降低", "rate_price_down", "credit"),
        ("商品单价下调联动百分比 OPTION", "rate_goods_price_down", "credit"),
        ("全部取消 OPTION", "all_delete", "credit"),
        ("多个 OPTION 同时增减净退款", "mixed_net_refund", "credit"),
    )
    manual_options = tuple(
        _success(
            f"JP-PG-OPT-M-{index:03d}",
            name,
            "problem_option_manual",
            direction,
            runner_kind="problem_goods",
            parameters={"problem_type": 6, "option_deal_suggest": 1, "option_adjustment": adjustment},
            tags=("问题产品", "OPTION", "业务修改"),
        )
        for index, (name, adjustment, direction) in enumerate(manual_option_rows, 1)
    )

    auto_option_rows = (
        ("数量减少固定 OPTION 自动计算", "fixed_quantity_down", "credit"),
        ("数量减少百分比 OPTION 自动计算", "rate_quantity_down", "credit"),
        ("商品单价下调百分比 OPTION 联动", "rate_price_down", "credit"),
        ("检品 OPTION 已完成数量保护", "inspection_completed", "credit"),
        ("非自动 OPTION 保持不变", "non_auto_unchanged", "credit"),
        ("商品和 OPTION 均不变", "unchanged", "none"),
    )
    auto_options = tuple(
        _success(
            f"JP-PG-OPT-A-{index:03d}",
            name,
            "problem_option_auto",
            direction,
            runner_kind="problem_goods",
            parameters={"problem_type": 6, "option_deal_suggest": 2, "option_adjustment": adjustment},
            tags=("问题产品", "OPTION", "系统自动"),
        )
        for index, (name, adjustment, direction) in enumerate(auto_option_rows, 1)
    )

    mixed_rows = (
        ("全费用综合净退款", "net_refund", "credit"),
        ("全费用综合净补款", "net_topup", "debit"),
        ("全费用正负相抵为零", "net_zero", "none"),
    )
    mixed = tuple(
        _success(
            f"JP-PG-MIX-{index:03d}",
            name,
            "problem_mixed",
            direction,
            runner_kind="problem_goods",
            parameters={"problem_type": 8, "adjustment": adjustment, "validate_components": True},
            tags=("问题产品", "综合净额"),
        )
        for index, (name, adjustment, direction) in enumerate(mixed_rows, 1)
    )

    flow_rows = (
        ("单价变动完整流程", 1, "accept", "仅退款", "credit"),
        ("运费变动完整流程", 2, "accept", "仅退款", "credit"),
        ("少货补买完整流程", 3, "accept", "少货补买", "credit"),
        ("不良换货完整流程", 4, "exchange", "换货", "credit"),
        ("不良且少货退货退款流程", 5, "cancel", "退货退款", "credit"),
        ("OPTION 变动完整流程", 6, "accept", "其他", "debit"),
        ("数量多了补款流程", 7, "accept", "其他", "debit"),
        ("其他问题自定义回复流程", 8, "other", "其他", "none"),
        ("客户原因已收不退流程", 9, "discard", "其他", "none"),
        ("不良直接上架标准流程", 10, "accept", "其他", "none"),
    )
    flows = tuple(
        _success(
            f"JP-PG-FLOW-{index:03d}",
            name,
            "problem_flow",
            direction,
            runner_kind="problem_flow",
            parameters={"problem_type": problem_type, "client_deal_choice": client_choice, "g_deal_type": purchase_type},
            tags=("问题产品", "完整流程"),
        )
        for index, (name, problem_type, client_choice, purchase_type, direction) in enumerate(flow_rows, 1)
    )

    guard_rows = (
        ("分批付款尾款未完成禁止决策", "part_tail_unpaid", ("未分批付款完成", "尾款")),
        ("转寄订单禁止提出问题产品", "resend_order", ("转寄订单",)),
        ("待财务付款采购禁止提出", "purchase_wait_pay", ("待财务付款",)),
        ("处理中问题产品禁止重复提出", "duplicate_open_problem", ("不可以重复提出", "进行中的问题产品")),
        ("问题数量超过未上架数量", "problem_num_over_unstored", ("超过未上架数",)),
        ("修改后数量小于已上架数量", "pre_num_below_storage", ("不能小于仓库已上架",)),
        ("普通账号数量超过可入库数", "quantity_over_possible", ("修改后数量应该 <=",)),
        ("数量增加禁止 OPTION 自动计算", "quantity_up_auto_option", ("商品数量增加", "业务修改OPTION")),
        ("OPTION 数量超过商品数禁止自动计算", "option_num_over_goods", ("OPTION数量大于商品数", "option数比商品数多")),
        ("多个百分比 OPTION 禁止自动计算", "multiple_rate_auto", ("多个百分比OPTION",)),
        ("已有 OPTION 禁止修改计价类型", "option_price_type_change", ("不允许修改OPTION计价类型",)),
        ("同番多采购禁止修改预处理数据", "multiple_purchase_update", ("有多条采购记录",)),
        ("大额退款切换部长账号", "large_refund_account", ("大于500人民币", "部长账号")),
        ("受限类型已有交易号禁止跳过采购", "restricted_skip_purchase", ("不允许跳过采购",)),
        ("非允许类型禁止配货直接完成", "direct_complete_invalid_type", ("只有【少货、不良、不良且少货】",)),
    )
    guards = tuple(
        _guard(
            f"JP-PG-GUARD-{index:03d}",
            name,
            guard_kind=guard_kind,
            error_keywords=keywords,
        )
        for index, (name, guard_kind, keywords) in enumerate(guard_rows, 1)
    )
    return payment + amounts + services + manual_options + auto_options + mixed + flows + guards


_RAW_DEFINITIONS = _raw_definitions()


def japan_case_definitions() -> tuple[RegressionCaseDefinition, ...]:
    return tuple(
        RegressionCaseDefinition(
            key=key,
            name=name,
            category=category,
            runner_kind=runner_kind,
            parameters=parameters,
            expectation=expectation,
            tags=tags,
            sort_order=index,
        )
        for index, (key, name, category, runner_kind, parameters, expectation, tags) in enumerate(_RAW_DEFINITIONS, 1)
    )


__all__ = ["JAPAN_REQUIRED_IDENTITIES", "japan_case_definitions"]
