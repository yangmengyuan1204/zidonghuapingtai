from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence


MONEY_DIRECTIONS = {"debit", "credit", "none"}
REFERENCE_KEYS = (
    "order_sn",
    "porder_sn",
    "p_order_sn",
    "problem_goods_id",
    "serial_number",
    "remark",
    "pay_remark",
    "description",
)
IDENTITY_KEYS = ("id", "serial_number", "bill_sn", "record_id", "uniqid")


class EvidenceMatchError(ValueError):
    pass


@dataclass(frozen=True)
class MoneyEvidence:
    source: str
    amount: Decimal
    currency: str
    direction: str
    exchange_rate: Decimal | None = None
    reference: str = ""
    record_id: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", str(self.currency or "").strip().upper())
        object.__setattr__(self, "direction", str(self.direction or "").strip().lower())
        if self.direction not in MONEY_DIRECTIONS:
            raise ValueError(f"不支持的出入账方向：{self.direction}")


def _decimal(value: Any, label: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是有效金额") from exc
    if not number.is_finite():
        raise ValueError(f"{label}必须是有限金额")
    return number


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text == "-0" else text


def to_jpy(amount: Decimal, currency: str, exchange_rate: Decimal | None = None) -> Decimal:
    number = _decimal(amount, "金额")
    normalized_currency = str(currency or "").strip().upper()
    if normalized_currency == "JPY":
        converted = number
    elif normalized_currency == "CNY":
        if exchange_rate is None or _decimal(exchange_rate, "汇率") <= 0:
            raise ValueError("人民币换算日元必须提供正数汇率")
        converted = number * _decimal(exchange_rate, "汇率")
    else:
        raise ValueError(f"不支持的币种：{normalized_currency or '空'}")
    return converted.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def reconcile_amount(
    key: str,
    expected: MoneyEvidence,
    actual: MoneyEvidence,
    *,
    tolerance_jpy: Decimal = Decimal("1"),
    discount_jpy: Decimal = Decimal("0"),
    voucher_jpy: Decimal = Decimal("0"),
) -> dict[str, Any]:
    gross_expected_jpy = abs(to_jpy(expected.amount, expected.currency, expected.exchange_rate))
    actual_jpy = abs(to_jpy(actual.amount, actual.currency, actual.exchange_rate))
    discount = abs(_decimal(discount_jpy, "优惠券金额"))
    voucher = abs(_decimal(voucher_jpy, "代金券金额"))
    expected_jpy = gross_expected_jpy - discount - voucher
    if expected_jpy < 0:
        expected_jpy = Decimal("0")
    difference = abs(actual_jpy - expected_jpy)
    direction_matches = expected.direction == actual.direction
    passed = direction_matches and difference <= abs(_decimal(tolerance_jpy, "容差"))
    reason_code = ""
    reason = ""
    if not direction_matches:
        reason_code = "direction_mismatch"
        reason = f"实际方向 {actual.direction} 与预期方向 {expected.direction} 不一致"
    elif not passed:
        reason_code = "amount_mismatch"
        reason = f"金额相差 {_decimal_text(difference)} 日元"
    return {
        "key": key,
        "passed": passed,
        "reason_code": reason_code,
        "reason": reason,
        "expected_source": expected.source,
        "actual_source": actual.source,
        "expected_currency": expected.currency,
        "actual_currency": actual.currency,
        "expected_amount": _decimal_text(expected.amount),
        "actual_amount": _decimal_text(actual.amount),
        "exchange_rate": _decimal_text(expected.exchange_rate) if expected.exchange_rate is not None else "",
        "gross_expected_jpy": _decimal_text(gross_expected_jpy),
        "expected_jpy": _decimal_text(expected_jpy),
        "actual_jpy": _decimal_text(actual_jpy),
        "difference_jpy": _decimal_text(difference),
        "tolerance_jpy": _decimal_text(abs(_decimal(tolerance_jpy, "容差"))),
        "discount_amount": _decimal_text(discount),
        "voucher_amount": _decimal_text(voucher),
        "expected_direction": expected.direction,
        "actual_direction": actual.direction,
        "expected_reference": expected.reference,
        "actual_reference": actual.reference,
        "actual_record_id": actual.record_id,
    }


def _record_identity(row: Mapping[str, Any]) -> tuple[str, str]:
    for key in IDENTITY_KEYS:
        value = row.get(key)
        if value not in (None, ""):
            return key, str(value)
    return "payload", repr(sorted((str(key), repr(value)) for key, value in row.items()))


def new_records(before: Iterable[Mapping[str, Any]], after: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    known = {_record_identity(row) for row in before}
    return [dict(row) for row in after if _record_identity(row) not in known]


def _row_contains_reference(row: Mapping[str, Any], references: Sequence[str]) -> bool:
    needles = [str(value).strip() for value in references if str(value).strip()]
    if not needles:
        return False
    for key in REFERENCE_KEYS:
        value = row.get(key)
        text = str(value or "")
        if any(needle == text or needle in text for needle in needles):
            return True
    return False


def select_unique_record(rows: Iterable[Mapping[str, Any]], *, references: Sequence[str]) -> dict[str, Any]:
    matches = [dict(row) for row in rows if _row_contains_reference(row, references)]
    reference_text = "、".join(str(value) for value in references)
    if not matches:
        raise EvidenceMatchError(f"未找到匹配流水：{reference_text}")
    if len(matches) > 1:
        raise EvidenceMatchError(f"找到多条匹配流水，无法唯一取证：{reference_text}")
    return matches[0]

