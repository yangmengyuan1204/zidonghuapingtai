from __future__ import annotations

from typing import Any, Iterable

from ...common.catalog import CaseExpectation, RegressionCaseDefinition
from .panel import (
    ACCOUNT_COUPON_ID,
    ACCOUNT_VOUCHER_ID,
    INSPECT_OPTION,
    PACK_OPTION,
    SERVICE_COUPON_ID,
    _item,
    _part_pay,
    guard_panel,
    order_panel,
    porder_panel,
    problem_panel,
)

JAPAN_REQUIRED_IDENTITIES = ("admin", "client")


def _case_key(category: str, index: int) -> str:
    from .case_keys import case_key_for_category

    return case_key_for_category(category, index)


def _direction_deals(direction: str) -> dict[str, Any]:
    if direction == "debit":
        return {"g_deal_type": "其他", "service_deal_suggest": 1}
    if direction == "none":
        return {"g_deal_type": "其他", "service_deal_suggest": 1}
    return {}


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
    values = dict(parameters or {})
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
    mixed_options = [dict(PACK_OPTION), dict(INSPECT_OPTION)]
    pay_index = 0
    porder_index = 0

    def _pay_key() -> str:
        nonlocal pay_index
        pay_index += 1
        return _case_key("payment", pay_index)

    def _porder_key() -> str:
        nonlocal porder_index
        porder_index += 1
        return _case_key("porder", porder_index)

    payment = (
        _success(
            _pay_key(),
            "单个订单余额一次付清",
            "payment",
            "debit",
            runner_kind="order_payment",
            parameters=order_panel(payment_mode="balance", payment_plan="full"),
            tags=("支付", "余额"),
        ),
        _success(
            _pay_key(),
            "单个订单银行一次付清",
            "payment",
            "debit",
            runner_kind="order_payment",
            parameters=order_panel(payment_mode="bank", payment_plan="full", finance_confirm=True),
            tags=("支付", "银行"),
        ),
        _success(
            _pay_key(),
            "余额分批付款",
            "payment",
            "debit",
            runner_kind="order_part_payment",
            parameters=order_panel(
                payment_mode="balance",
                payment_plan="part",
                part=_part_pay(True, percent=50),
                first_payment_rate="0.5",
            ),
            tags=("支付", "分批"),
        ),
        _success(
            _pay_key(),
            "银行分批付款",
            "payment",
            "debit",
            runner_kind="order_part_payment",
            parameters=order_panel(
                payment_mode="bank",
                payment_plan="part",
                part=_part_pay(True, percent=50),
                first_payment_rate="0.5",
                finance_confirm=True,
            ),
            tags=("支付", "分批", "银行"),
        ),
        _success(
            _porder_key(),
            "配送单余额支付",
            "porder",
            "debit",
            runner_kind="porder_payment",
            parameters=porder_panel(payment_mode="balance"),
            tags=("支付", "配送单"),
        ),
        _success(
            _porder_key(),
            "配送单银行支付",
            "porder",
            "debit",
            runner_kind="porder_payment",
            parameters=porder_panel(payment_mode="bank", finance_confirm=True),
            tags=("支付", "配送单", "银行"),
        ),
        _success(
            _pay_key(),
            "多个商品分别计算国内运费",
            "payment",
            "debit",
            runner_kind="order_payment",
            parameters=order_panel(
                payment_mode="balance",
                items=[_item(1, freight="3"), _item(2, freight="4")],
                item_count=2,
                per_item_freight=True,
            ),
            tags=("支付", "多番", "国内运费"),
        ),
        _success(
            _pay_key(),
            "订单增加5元包装材料费",
            "payment",
            "debit",
            runner_kind="order_payment",
            parameters=order_panel(
                payment_mode="balance",
                other_name="包装材料费",
                other_amount="5",
            ),
            tags=("支付", "其他费用"),
        ),
        _success(
            _pay_key(),
            "同一商品同时收固定额和百分比 OPTION",
            "payment",
            "debit",
            runner_kind="order_payment",
            parameters=order_panel(
                payment_mode="balance",
                items=[_item(1, quantity=2, options=mixed_options)],
                option_profile="fixed_and_rate",
                option_quantity=2,
            ),
            tags=("支付", "OPTION"),
        ),
        _success(
            _pay_key(),
            "商品、运费、OPTION、其他费和手续费综合订单",
            "payment",
            "debit",
            runner_kind="order_payment",
            parameters=order_panel(
                payment_mode="balance",
                items=[
                    _item(1, quantity=2, price="10", freight="3", options=mixed_options),
                    _item(2, quantity=2, price="10", freight="4", options=mixed_options),
                ],
                other_name="系统回归包装费",
                other_amount="5",
                fee_profile="all",
                option_profile="fixed_and_rate",
                item_count=2,
                item_quantity=2,
            ),
            tags=("支付", "综合费用"),
        ),
        _success(
            _pay_key(),
            "手续费减免后应付金额",
            "payment",
            "debit",
            runner_kind="order_payment",
            parameters=order_panel(
                payment_mode="balance",
                coupon_id=SERVICE_COUPON_ID,
                service_discount=True,
            ),
            tags=("支付", "优惠券"),
        ),
        _success(
            _porder_key(),
            "配送单增加8元加固包装费",
            "porder",
            "debit",
            runner_kind="porder_payment",
            parameters=porder_panel(payment_mode="balance", extra_name="加固包装", extra_fee="8"),
            tags=("支付", "配送单", "其他费用"),
        ),
        _success(
            _pay_key(),
            "国内运费在尾款收取",
            "payment",
            "debit",
            runner_kind="order_part_payment",
            parameters=order_panel(
                payment_mode="balance",
                payment_plan="part",
                part=_part_pay(True, percent=50, fee_timing={
                    "domestic_freight": "tail",
                    "service_fee": "first",
                    "additional_service_fee": "first",
                    "other_fee": "first",
                }),
                first_payment_rate="0.5",
            ),
            tags=("支付", "分批", "国内运费"),
        ),
        _success(
            _pay_key(),
            "尾款在上架前收取",
            "payment",
            "debit",
            runner_kind="order_part_payment",
            parameters=order_panel(
                payment_mode="balance",
                payment_plan="part",
                part=_part_pay(True, percent=50, tail_node="before_shelf"),
                first_payment_rate="0.5",
            ),
            tags=("支付", "分批", "尾款节点"),
        ),
        _success(
            _pay_key(),
            "指定番号单独结算尾款",
            "payment",
            "debit",
            runner_kind="order_part_payment",
            parameters=order_panel(
                payment_mode="balance",
                payment_plan="part",
                items=[_item(1, freight="3"), _item(2, freight="4")],
                item_count=2,
                part=_part_pay(True, percent=50, tail_partial=True, tail_sortings="1"),
                first_payment_rate="0.5",
            ),
            tags=("支付", "分批", "按番尾款"),
        ),
        _success(
            _pay_key(),
            "手续费在尾款收取",
            "payment",
            "debit",
            runner_kind="order_part_payment",
            parameters=order_panel(
                payment_mode="balance",
                payment_plan="part",
                part=_part_pay(True, percent=50, fee_timing={
                    "domestic_freight": "first",
                    "service_fee": "tail",
                    "additional_service_fee": "first",
                    "other_fee": "first",
                }),
                first_payment_rate="0.5",
            ),
            tags=("支付", "分批", "手续费"),
        ),
        _success(
            _pay_key(),
            "OPTION费用在尾款收取",
            "payment",
            "debit",
            runner_kind="order_part_payment",
            parameters=order_panel(
                payment_mode="balance",
                payment_plan="part",
                items=[_item(1, quantity=2, options=mixed_options)],
                part=_part_pay(True, percent=50, fee_timing={
                    "domestic_freight": "first",
                    "service_fee": "first",
                    "additional_service_fee": "tail",
                    "other_fee": "first",
                }),
                first_payment_rate="0.5",
                option_profile="fixed_and_rate",
                option_quantity=2,
            ),
            tags=("支付", "分批", "OPTION"),
        ),
        _success(
            _pay_key(),
            "其他费用在尾款收取",
            "payment",
            "debit",
            runner_kind="order_part_payment",
            parameters=order_panel(
                payment_mode="balance",
                payment_plan="part",
                other_name="包装材料费",
                other_amount="5",
                part=_part_pay(True, percent=50, fee_timing={
                    "domestic_freight": "first",
                    "service_fee": "first",
                    "additional_service_fee": "first",
                    "other_fee": "tail",
                }),
                first_payment_rate="0.5",
            ),
            tags=("支付", "分批", "其他费用"),
        ),
        _success(
            _porder_key(),
            "配送单国际运费固定为88",
            "porder",
            "debit",
            runner_kind="porder_payment",
            parameters=porder_panel(payment_mode="balance", price_manual=True, logistics_price="88"),
            tags=("支付", "配送单", "人工运费"),
        ),
        _success(
            _porder_key(),
            "配送单按RW船便计算国际运费",
            "porder",
            "debit",
            runner_kind="porder_payment",
            parameters=porder_panel(payment_mode="balance", logistics="20"),
            tags=("支付", "配送单", "船便"),
        ),
        _success(
            _pay_key(),
            "订单余额支付使用账号优惠券后金额比对",
            "payment",
            "debit",
            runner_kind="order_payment",
            parameters=order_panel(payment_mode="balance", coupon_id=ACCOUNT_COUPON_ID),
            tags=("支付", "优惠券", "金额比对"),
        ),
        _success(
            _pay_key(),
            "订单银行支付使用账号优惠券后金额比对",
            "payment",
            "debit",
            runner_kind="order_payment",
            parameters=order_panel(
                payment_mode="bank",
                coupon_id=ACCOUNT_COUPON_ID,
                finance_confirm=True,
            ),
            tags=("支付", "优惠券", "银行", "金额比对"),
        ),
        _success(
            _pay_key(),
            "尾款在创建配送单前收取",
            "payment",
            "debit",
            runner_kind="order_part_payment",
            parameters=order_panel(
                payment_mode="balance",
                payment_plan="part",
                part=_part_pay(True, percent=50, tail_node="before_porder_create"),
                first_payment_rate="0.5",
            ),
            tags=("支付", "分批", "尾款节点", "金额对照"),
        ),
        _success(
            _porder_key(),
            "配送单余额支付使用账号代金券后金额比对",
            "porder",
            "debit",
            runner_kind="porder_payment",
            parameters=porder_panel(payment_mode="balance", voucher_id=ACCOUNT_VOUCHER_ID),
            tags=("支付", "配送单", "代金券", "金额比对"),
        ),
        _success(
            _porder_key(),
            "配送单银行支付使用账号代金券后金额比对",
            "porder",
            "debit",
            runner_kind="porder_payment",
            parameters=porder_panel(
                payment_mode="bank",
                voucher_id=ACCOUNT_VOUCHER_ID,
                finance_confirm=True,
            ),
            tags=("支付", "配送单", "代金券", "银行", "金额比对"),
        ),
    )

    amount_rows = (
        ("客户原因：金额不变、不退款", 9, "unchanged", "none"),
        ("商品数量减少1件并退款", 3, "quantity_partial_down", "credit"),
        ("少货数量全部减少至零", 3, "quantity_all_down", "credit"),
        ("单价下调退款", 1, "price_down", "credit"),
        ("单价上调补款", 1, "price_up", "debit"),
        ("单个商品国内运费下调退款", 2, "freight_down", "credit"),
        ("单条采购运费上调补款", 2, "freight_up", "debit"),
        ("不良且少货数量减少", 5, "quantity_down", "credit"),
        ("不良且少货数量和单价下调", 5, "quantity_and_price_down", "credit"),
        ("不良数量减少且单价上调", 4, "quantity_down_price_up_net_refund", "credit"),
        ("单价下调运费上调净退款", 8, "price_down_freight_up_net_refund", "credit"),
        ("单价上调运费下调净补款", 8, "price_up_freight_down_net_topup", "debit"),
    )
    amounts = tuple(
        _success(
            _case_key("problem_amount", index),
            name,
            "problem_amount",
            direction,
            runner_kind="problem_goods",
            parameters=problem_panel(name=name, problem_type=problem_type, adjustment=adjustment, **_direction_deals(direction)),
            tags=("问题产品", "基础金额"),
        )
        for index, (name, problem_type, adjustment, direction) in enumerate(amount_rows, 1)
    )

    service_rows = (
        ("商品金额减少，手续费按差额退回", "goods_down_refund_service", 2, False, "credit"),
        ("商品金额减少，但已收手续费不退", "goods_down_keep_service", 1, False, "credit"),
        ("商品增加补收手续费", "goods_up_charge_service", 2, False, "debit"),
        ("手续费减免券下商品减少", "goods_down_discount_service", 2, True, "credit"),
        ("手续费减免券下商品增加", "goods_up_discount_service", 2, True, "debit"),
        ("手续费率变为0后退款", "zero_service_rate", 2, False, "credit"),
    )
    services = tuple(
        _success(
            _case_key("problem_service_fee", index),
            name,
            "problem_service_fee",
            direction,
            runner_kind="problem_goods",
            parameters=problem_panel(
                name=name,
                problem_type=1,
                adjustment=adjustment,
                service_deal_suggest=rule,
                service_discount=discount,
                **{key: value for key, value in _direction_deals(direction).items() if key != "service_deal_suggest"},
            ),
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
        ("商品单价下调后百分比 OPTION金额联动", "rate_goods_price_down", "credit"),
        ("全部取消 OPTION", "all_delete", "credit"),
        ("多个 OPTION 同时增减净退款", "mixed_net_refund", "credit"),
    )
    manual_options = tuple(
        _success(
            _case_key("problem_option_manual", index),
            name,
            "problem_option_manual",
            direction,
            runner_kind="problem_goods",
            parameters=problem_panel(
                name=name,
                problem_type=6,
                option_adjustment=adjustment,
                option_deal_suggest=1,
                **_direction_deals(direction),
            ),
            tags=("问题产品", "OPTION", "业务修改"),
        )
        for index, (name, adjustment, direction) in enumerate(manual_option_rows, 1)
    )

    auto_option_rows = (
        ("数量减少固定 OPTION 自动计算", "fixed_quantity_down", "credit"),
        ("数量减少百分比 OPTION 自动计算", "rate_quantity_down", "credit"),
        ("商品单价下调后百分比 OPTION金额联动", "rate_price_down", "credit"),
        ("已完成检品数量不重复退款", "inspection_completed", "credit"),
        ("非自动 OPTION不参与自动金额调整", "non_auto_unchanged", "credit"),
        ("商品和OPTION均不变零金额对照", "unchanged", "none"),
    )
    auto_options = tuple(
        _success(
            _case_key("problem_option_auto", index),
            name,
            "problem_option_auto",
            direction,
            runner_kind="problem_goods",
            parameters=problem_panel(
                name=name,
                problem_type=6,
                option_adjustment=adjustment,
                option_deal_suggest=2,
                completed_inspect_num=1 if adjustment == "inspection_completed" else None,
                non_auto_option=adjustment == "non_auto_unchanged",
                **_direction_deals(direction),
            ),
            tags=("问题产品", "OPTION", "系统自动"),
        )
        for index, (name, adjustment, direction) in enumerate(auto_option_rows, 1)
    )

    mixed_rows = (
        ("商品数量、单价、运费及手续费综合退款", "net_refund", "credit"),
        ("商品单价上涨、运费下降后的综合补款", "net_topup", "debit"),
        ("全部金额不变零金额对照", "net_zero", "none"),
    )
    mixed = tuple(
        _success(
            _case_key("problem_mixed", index),
            name,
            "problem_mixed",
            direction,
            runner_kind="problem_goods",
            parameters=problem_panel(
                name=name,
                problem_type=8,
                adjustment=adjustment,
                validate_components=True,
                items=[
                    _item(1, quantity=2, freight="3", options=mixed_options),
                    _item(2, quantity=2, freight="4", options=mixed_options),
                ],
                other_name="系统回归包装费",
                other_amount="5",
                **_direction_deals(direction),
            ),
            tags=("问题产品", "综合净额"),
        )
        for index, (name, adjustment, direction) in enumerate(mixed_rows, 1)
    )

    flow_rows = (
        (7, "商品数量增加后的补款金额", 7, "accept", "其他", "debit"),
    )
    flows = tuple(
        _success(
            _case_key("problem_flow", flow_index),
            name,
            "problem_flow",
            direction,
            runner_kind="problem_flow",
            parameters=problem_panel(
                name=name,
                problem_type=problem_type,
                client_deal_choice=client_choice,
                g_deal_type=purchase_type,
                **{key: value for key, value in _direction_deals(direction).items() if key != "g_deal_type"},
            ),
            tags=("问题产品", "完整流程"),
        )
        for flow_index, name, problem_type, client_choice, purchase_type, direction in flow_rows
    )
    return payment + amounts + services + manual_options + auto_options + mixed + flows


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
