from __future__ import annotations

CATEGORY_KEY_PREFIX: dict[str, str] = {
    "payment": "支付",
    "porder": "配送",
    "problem_amount": "金额",
    "problem_service_fee": "手续费",
    "problem_option_manual": "手动OPTION",
    "problem_option_auto": "自动OPTION",
    "problem_mixed": "混合",
    "problem_flow": "流程",
    "problem_guard": "拦截",
}

CREATE_KIND_PREFIX: dict[str, str] = {
    "payment": "支付",
    "part": "支付",
    "problem": "流程",
    "porder": "配送",
}

LEGACY_CUSTOM_PREFIX: dict[str, str] = {
    "CUSTOM-PAY": "支付",
    "CUSTOM-PG": "流程",
    "CUSTOM-PORDER": "配送",
}

REMOVED_DEFAULT_CASE_KEYS = frozenset(
    {
        "拦截-001", "拦截-002", "拦截-003", "拦截-004", "拦截-005", "拦截-006",
        "拦截-007", "拦截-008", "拦截-009", "拦截-010", "拦截-011", "拦截-012",
        "拦截-013", "拦截-014", "拦截-015",
        "流程-001", "流程-002", "流程-003", "流程-004", "流程-005", "流程-006",
        "流程-008", "流程-009", "流程-010",
    }
)


def case_key_prefix(category: str) -> str:
    try:
        return CATEGORY_KEY_PREFIX[str(category)]
    except KeyError as exc:
        raise KeyError(f"未知用例分类：{category}") from exc


def format_case_key(prefix: str, index: int) -> str:
    return f"{prefix}-{index:03d}"


def case_key_for_category(category: str, index: int) -> str:
    return format_case_key(case_key_prefix(category), index)


__all__ = [
    "CATEGORY_KEY_PREFIX",
    "CREATE_KIND_PREFIX",
    "LEGACY_CUSTOM_PREFIX",
    "REMOVED_DEFAULT_CASE_KEYS",
    "case_key_for_category",
    "case_key_prefix",
    "format_case_key",
]
