from decimal import Decimal

import pytest

from app.system_regression.common.evidence import (
    EvidenceMatchError,
    MoneyEvidence,
    match_unique_evidence,
)
from app.system_regression.common.reconciliation import reconcile_three_way, to_jpy


def evidence(amount, *, direction="credit", currency="JPY", exchange_rate=None, source="customer_balance"):
    return MoneyEvidence(
        source=source,
        amount=Decimal(str(amount)),
        currency=currency,
        direction=direction,
        exchange_rate=Decimal(str(exchange_rate)) if exchange_rate is not None else None,
        reference="PG-901",
    )


def test_cny_to_jpy_uses_evidence_rate_then_japan_fallback():
    assert to_jpy(evidence("1.5", currency="CNY", exchange_rate="3", source="order_quote")) == Decimal("5")
    assert to_jpy(evidence("10", currency="CNY", source="order_quote")) == Decimal("212")
    assert to_jpy(evidence("212", currency="CNY", source="customer_balance", exchange_rate="15")) == Decimal("212")


@pytest.mark.parametrize(("preview", "actual", "passed"), [(100, 100, True), (101, 100, True), (102, 100, False)])
def test_three_way_tolerance_boundary(preview, actual, passed):
    result = reconcile_three_way(
        "case",
        evidence(100),
        evidence(preview),
        evidence(actual),
        tolerance_jpy=1,
    )

    assert result.passed is passed


def test_three_way_tolerance_cannot_exceed_one_jpy():
    result = reconcile_three_way(
        "case",
        evidence(100),
        evidence(102),
        evidence(100),
        tolerance_jpy=10,
    )

    assert result.passed is False
    assert result.reason_code == "amount_mismatch"


def test_three_way_rejects_wrong_direction_and_problem_bank_source():
    wrong_direction = reconcile_three_way("case", evidence(100), evidence(100), evidence(100, direction="debit"))
    wrong_source = reconcile_three_way(
        "case",
        evidence(100),
        evidence(100),
        evidence(100, source="bank_flow"),
        actual_source="problem_goods",
    )

    assert wrong_direction.passed is False
    assert wrong_direction.reason_code == "direction_mismatch"
    assert wrong_source.passed is False
    assert wrong_source.reason_code == "invalid_actual_source"


def test_zero_amount_requires_no_matching_actual_evidence():
    clean = reconcile_three_way("zero", evidence(0, direction="none"), evidence(0, direction="none"), None)
    unexpected = reconcile_three_way("zero", evidence(0, direction="none"), evidence(0, direction="none"), evidence(1))

    assert clean.passed is True
    assert unexpected.passed is False
    assert unexpected.reason_code == "unexpected_ledger"


def test_unique_evidence_matching_rejects_missing_and_ambiguous_rows():
    rows = [
        {"id": 1, "order_sn": "ORDER-1", "problem_goods_id": 901, "amount": 100, "bill_type": "change_in"},
        {"id": 2, "order_sn": "ORDER-2", "problem_goods_id": 902, "amount": 200, "bill_type": "change_out"},
    ]
    matched = match_unique_evidence(rows, references=("ORDER-1", "901"), direction="credit")
    assert matched.record_id == "1"

    with pytest.raises(EvidenceMatchError, match="缺失"):
        match_unique_evidence(rows, references=("ORDER-9",), direction="credit")
    with pytest.raises(EvidenceMatchError, match="歧义"):
        match_unique_evidence(rows + [dict(rows[0], id=3)], references=("ORDER-1",), direction="credit")
