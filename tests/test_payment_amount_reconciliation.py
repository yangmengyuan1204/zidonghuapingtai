from decimal import Decimal

import pytest

from app.data_scripts.payment_amount_regression.reconciliation import (
    EvidenceMatchError,
    MoneyEvidence,
    new_records,
    reconcile_amount,
    select_unique_record,
    to_jpy,
)


def evidence(amount, currency="JPY", direction="debit", exchange_rate=None):
    return MoneyEvidence(
        source="test",
        amount=Decimal(str(amount)),
        currency=currency,
        direction=direction,
        exchange_rate=Decimal(str(exchange_rate)) if exchange_rate is not None else None,
        reference="ORDER-1",
    )


def test_cny_amount_is_rounded_to_integer_jpy():
    assert to_jpy(Decimal("10.25"), "CNY", Decimal("20.5")) == Decimal("210")


def test_cny_conversion_requires_positive_exchange_rate():
    with pytest.raises(ValueError, match="汇率"):
        to_jpy(Decimal("10"), "CNY", None)


@pytest.mark.parametrize(
    ("actual", "passed"),
    [("100", True), ("101", True), ("99", True), ("102", False), ("98", False)],
)
def test_reconciliation_allows_one_jpy_difference(actual, passed):
    result = reconcile_amount("order_balance", evidence("100"), evidence(actual))

    assert result["passed"] is passed
    assert result["difference_jpy"] == str(abs(Decimal(actual) - Decimal("100")))


def test_reconciliation_caps_tolerance_at_one_jpy():
    result = reconcile_amount("order_balance", evidence("100"), evidence("102"), tolerance_jpy=Decimal("5"))

    assert result["passed"] is False
    assert result["tolerance_jpy"] == "1"
    assert "超过允许的 1 日元" in result["reason"]


def test_reconciliation_rejects_wrong_cashflow_direction():
    result = reconcile_amount(
        "problem_refund",
        evidence("100", direction="credit"),
        evidence("100", direction="debit"),
    )

    assert result["passed"] is False
    assert result["reason_code"] == "direction_mismatch"


def test_reconciliation_reserves_discount_and_voucher_amounts():
    result = reconcile_amount(
        "discount_placeholder",
        evidence("1000"),
        evidence("850"),
        discount_jpy=Decimal("100"),
        voucher_jpy=Decimal("50"),
    )

    assert result["expected_jpy"] == "850"
    assert result["discount_amount"] == "100"
    assert result["voucher_amount"] == "50"
    assert result["passed"] is True


def test_new_records_uses_stable_business_identity():
    before = [{"id": 1, "amount": "100"}]
    after = [{"id": 1, "amount": "100"}, {"id": 2, "amount": "200"}]

    assert new_records(before, after) == [{"id": 2, "amount": "200"}]


def test_select_unique_record_matches_any_declared_reference():
    rows = [
        {"id": 1, "order_sn": "OTHER", "amount": "10"},
        {"id": 2, "order_sn": "ORDER-1", "amount": "20"},
    ]

    selected = select_unique_record(rows, references=["ORDER-1"])

    assert selected["id"] == 2


def test_select_unique_record_rejects_missing_and_ambiguous_evidence():
    with pytest.raises(EvidenceMatchError, match="未找到"):
        select_unique_record([], references=["ORDER-1"])

    rows = [
        {"id": 1, "order_sn": "ORDER-1"},
        {"id": 2, "remark": "batch ORDER-1"},
    ]
    with pytest.raises(EvidenceMatchError, match="多条"):
        select_unique_record(rows, references=["ORDER-1"])

