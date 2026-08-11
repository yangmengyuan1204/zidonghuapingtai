from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Literal, Mapping


Direction = Literal["credit", "debit", "none"]


class EvidenceMatchError(ValueError):
    pass


@dataclass(frozen=True)
class MoneyEvidence:
    source: str
    amount: Decimal
    currency: Literal["CNY", "JPY"]
    direction: Direction
    exchange_rate: Decimal | None = None
    reference: str = ""
    record_id: str = ""
    raw: Mapping[str, Any] = field(default_factory=dict)


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise EvidenceMatchError("流水金额不是有效数字") from exc


def _direction(row: Mapping[str, Any]) -> Direction:
    value = str(row.get("direction") or row.get("bill_type") or "").lower()
    if value in {"credit", "change_in", "in", "1"}:
        return "credit"
    if value in {"debit", "change_out", "out", "-1"}:
        return "debit"
    return "none"


def _matches_reference(row: Mapping[str, Any], references: tuple[str, ...]) -> bool:
    values = {
        str(row.get(key) or "")
        for key in ("order_sn", "porder_sn", "problem_goods_id", "serial_number", "reference")
    }
    return any(reference and reference in values for reference in references)


def match_unique_evidence(
    records: Iterable[Mapping[str, Any]],
    *,
    references: Iterable[str],
    direction: Direction,
    source: str = "customer_balance",
) -> MoneyEvidence:
    refs = tuple(str(value) for value in references if str(value))
    matches = [dict(row) for row in records if _matches_reference(row, refs) and _direction(row) == direction]
    if not matches:
        raise EvidenceMatchError("匹配流水缺失")
    if len(matches) != 1:
        raise EvidenceMatchError(f"匹配流水存在歧义：{len(matches)}条")
    row = matches[0]
    return MoneyEvidence(
        source=source,
        amount=abs(_decimal(row.get("amount") or 0)),
        currency=str(row.get("currency") or "JPY").upper(),
        direction=direction,
        exchange_rate=_decimal(row["exchange_rate"]) if row.get("exchange_rate") not in (None, "") else None,
        reference=next((ref for ref in refs if ref in {str(value) for value in row.values()}), refs[0] if refs else ""),
        record_id=str(row.get("id") or row.get("serial_number") or ""),
        raw=row,
    )


__all__ = ["EvidenceMatchError", "MoneyEvidence", "match_unique_evidence"]
