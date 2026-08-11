from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .evidence import MoneyEvidence


@dataclass(frozen=True)
class ReconciliationResult:
    case_key: str
    passed: bool
    reason_code: str
    reason: str
    expected_jpy: Decimal
    preview_jpy: Decimal
    actual_jpy: Decimal
    expected_preview_diff: Decimal
    preview_actual_diff: Decimal


def to_jpy(evidence: MoneyEvidence) -> Decimal:
    if evidence.currency == "JPY":
        return abs(evidence.amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if evidence.exchange_rate is None or evidence.exchange_rate <= 0:
        raise ValueError("人民币证据缺少有效汇率")
    return (abs(evidence.amount) * evidence.exchange_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _result(
    case_key: str,
    *,
    passed: bool,
    reason_code: str,
    reason: str,
    expected_jpy: Decimal,
    preview_jpy: Decimal,
    actual_jpy: Decimal,
) -> ReconciliationResult:
    return ReconciliationResult(
        case_key=case_key,
        passed=passed,
        reason_code=reason_code,
        reason=reason,
        expected_jpy=expected_jpy,
        preview_jpy=preview_jpy,
        actual_jpy=actual_jpy,
        expected_preview_diff=abs(expected_jpy - preview_jpy),
        preview_actual_diff=abs(preview_jpy - actual_jpy),
    )


def reconcile_three_way(
    case_key: str,
    expected: MoneyEvidence,
    preview: MoneyEvidence,
    actual: MoneyEvidence | None,
    *,
    tolerance_jpy: int = 1,
    actual_source: str = "payment",
) -> ReconciliationResult:
    expected_jpy = to_jpy(expected)
    preview_jpy = to_jpy(preview)
    if expected.direction == "none":
        actual_jpy = Decimal("0") if actual is None else to_jpy(actual)
        if actual is not None:
            return _result(
                case_key,
                passed=False,
                reason_code="unexpected_ledger",
                reason="零金额场景出现匹配流水",
                expected_jpy=expected_jpy,
                preview_jpy=preview_jpy,
                actual_jpy=actual_jpy,
            )
        return _result(
            case_key,
            passed=expected_jpy == preview_jpy == 0,
            reason_code="ok" if expected_jpy == preview_jpy == 0 else "amount_mismatch",
            reason="金额一致" if expected_jpy == preview_jpy == 0 else "零金额预期与预览不一致",
            expected_jpy=expected_jpy,
            preview_jpy=preview_jpy,
            actual_jpy=actual_jpy,
        )
    if actual is None:
        return _result(
            case_key,
            passed=False,
            reason_code="missing_actual",
            reason="缺少实际资金流水",
            expected_jpy=expected_jpy,
            preview_jpy=preview_jpy,
            actual_jpy=Decimal("0"),
        )
    actual_jpy = to_jpy(actual)
    if actual_source == "problem_goods" and actual.source != "customer_balance":
        return _result(
            case_key,
            passed=False,
            reason_code="invalid_actual_source",
            reason="问题产品实际金额只能来自客户余额",
            expected_jpy=expected_jpy,
            preview_jpy=preview_jpy,
            actual_jpy=actual_jpy,
        )
    if preview.direction != expected.direction or actual.direction != expected.direction:
        return _result(
            case_key,
            passed=False,
            reason_code="direction_mismatch",
            reason="资金方向与预期不一致",
            expected_jpy=expected_jpy,
            preview_jpy=preview_jpy,
            actual_jpy=actual_jpy,
        )
    tolerance = Decimal(tolerance_jpy)
    expected_preview_diff = abs(expected_jpy - preview_jpy)
    preview_actual_diff = abs(preview_jpy - actual_jpy)
    passed = expected_preview_diff <= tolerance and preview_actual_diff <= tolerance
    return _result(
        case_key,
        passed=passed,
        reason_code="ok" if passed else "amount_mismatch",
        reason="金额和方向一致" if passed else "三方金额差值超过允许范围",
        expected_jpy=expected_jpy,
        preview_jpy=preview_jpy,
        actual_jpy=actual_jpy,
    )


__all__ = ["ReconciliationResult", "reconcile_three_way", "to_jpy"]
