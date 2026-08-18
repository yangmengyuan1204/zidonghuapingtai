from __future__ import annotations

from dataclasses import dataclass


MATCH_PRIORITY = ("business_code", "structured_error", "http_status", "message_regex")


@dataclass(frozen=True)
class GuardScenarioSpec:
    guard_kind: str
    expected_stage: str
    precondition_builder: str
    target_action: str
    message_patterns: tuple[str, ...]
    business_codes: tuple[str, ...] = ()
    http_statuses: tuple[int, ...] = (400, 409, 422)
    match_priority: tuple[str, ...] = MATCH_PRIORITY
    success_conditions: tuple[str, ...] = ("target_rejected", "no_forbidden_effects")
    requires_target_call: bool = True
    parallel_safe: bool = False
    safe_retry: bool = False


_SCENARIOS = (
    GuardScenarioSpec(
        "part_tail_unpaid",
        "business_deal",
        "build_part_tail_unpaid",
        "business_deal",
        (r"未分批付款完成", r"尾款"),
        ("PART_TAIL_UNPAID",),
    ),
    GuardScenarioSpec(
        "resend_order",
        "problem_create",
        "build_resend_order",
        "create_problem",
        (r"转寄订单.*不允许提出问题产品",),
        ("RESEND_ORDER_PROBLEM_FORBIDDEN",),
    ),
    GuardScenarioSpec(
        "purchase_wait_pay",
        "problem_create",
        "build_purchase_wait_pay",
        "create_problem",
        (r"待财务付款", r"待付款"),
        ("PURCHASE_WAIT_PAY",),
    ),
    GuardScenarioSpec(
        "duplicate_open_problem",
        "problem_create",
        "build_duplicate_open_problem",
        "create_problem",
        (r"不可以重复提出", r"进行中的问题产品"),
        ("DUPLICATE_OPEN_PROBLEM",),
    ),
    GuardScenarioSpec(
        "problem_num_over_unstored",
        "problem_create",
        "build_unstored_quantity",
        "create_problem",
        (r"问题产品提出数超过未上架数",),
        ("PROBLEM_NUM_OVER_UNSTORED",),
    ),
    GuardScenarioSpec(
        "pre_num_below_storage",
        "purchase_deal",
        "build_stored_problem",
        "purchase_deal",
        (r"不能小于仓库已上架",),
        ("PRE_NUM_BELOW_STORAGE",),
    ),
    GuardScenarioSpec(
        "quantity_over_possible",
        "purchase_deal",
        "build_possible_quantity_problem",
        "purchase_deal",
        (r"修改后数量应该", r"可入库数", r"购买时数量"),
        ("QUANTITY_OVER_POSSIBLE",),
    ),
    GuardScenarioSpec(
        "quantity_up_auto_option",
        "purchase_deal",
        "build_quantity_up_auto_option",
        "purchase_deal",
        (r"商品数增加.*业务修改OPTION",),
        ("QUANTITY_UP_AUTO_OPTION",),
    ),
    GuardScenarioSpec(
        "option_num_over_goods",
        "purchase_deal",
        "build_option_num_over_goods",
        "purchase_deal",
        (r"option数比商品数多", r"OPTION数多于商品数"),
        ("OPTION_NUM_OVER_GOODS",),
    ),
    GuardScenarioSpec(
        "multiple_rate_auto",
        "purchase_deal",
        "build_multiple_rate_options",
        "purchase_deal",
        (r"多个百分比OPTION",),
        ("MULTIPLE_RATE_OPTION_AUTO",),
    ),
    GuardScenarioSpec(
        "option_price_type_change",
        "option_update",
        "build_existing_option",
        "update_options",
        (r"不允许修改OPTION计价类型",),
        ("OPTION_PRICE_TYPE_CHANGE",),
    ),
    GuardScenarioSpec(
        "multiple_purchase_update",
        "pre_data_update",
        "build_multiple_purchase_detail",
        "update_pre_data",
        (r"有多条采购记录",),
        ("MULTIPLE_PURCHASE_UPDATE",),
    ),
    GuardScenarioSpec(
        "large_refund_account",
        "purchase_deal",
        "build_large_refund_problem",
        "large_refund_composite",
        (r"退款金额.*大于500人民币.*部长账号",),
        ("MINISTER_ACCOUNT_REQUIRED",),
        success_conditions=(
            "normal_actor_rejected",
            "no_forbidden_effects",
            "minister_actor_completed",
            "balance_credit_verified",
        ),
    ),
    GuardScenarioSpec(
        "restricted_skip_purchase",
        "business_deal",
        "build_restricted_problem_with_trade",
        "business_deal",
        (r"已有交易号.*不允许跳过采购",),
        ("RESTRICTED_SKIP_PURCHASE",),
    ),
    GuardScenarioSpec(
        "direct_complete_invalid_type",
        "distribution_direct_complete",
        "build_invalid_direct_complete_problem",
        "distribution_direct_complete",
        (r"只有【少货、不良、不良且少货】类型",),
        ("DIRECT_COMPLETE_INVALID_TYPE",),
    ),
)

_BY_KIND = {scenario.guard_kind: scenario for scenario in _SCENARIOS}


def guard_scenarios() -> tuple[GuardScenarioSpec, ...]:
    return _SCENARIOS


def guard_scenario(guard_kind: str) -> GuardScenarioSpec:
    try:
        return _BY_KIND[str(guard_kind)]
    except KeyError as exc:
        raise ValueError(f"不支持的拦截规则：{guard_kind}") from exc


__all__ = [
    "GuardScenarioSpec",
    "MATCH_PRIORITY",
    "guard_scenario",
    "guard_scenarios",
]
