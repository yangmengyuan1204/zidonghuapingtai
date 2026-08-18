from __future__ import annotations

from decimal import Decimal

from app.system_regression.projects.japan.fee_evidence import (
    FeeComponent,
    FeeEvidenceContract,
    cny_components_to_jpy,
    extract_order_fee_components,
    rate_option_amount,
    reconcile_fee_components,
)


def _component(kind, component_id, amount, *, option_id="", sorting="1"):
    return FeeComponent(
        kind=kind,
        component_id=component_id,
        amount_cny=Decimal(amount),
        option_id=option_id,
        sorting=sorting,
    )


def test_rate_option_uses_rate_times_option_quantity_times_goods_unit_price():
    assert rate_option_amount(rate="5", option_quantity=2, goods_unit_price_cny="10") == Decimal("1.00")


def test_jpy_rounding_happens_after_cny_components_are_summed():
    assert cny_components_to_jpy([Decimal("0.03"), Decimal("0.03")], Decimal("21.10")) == 1


def test_duplicate_option_id_fails_even_when_total_matches():
    contract = FeeEvidenceContract(required_components=(_component("option_fixed", "option:7", "2.00", option_id="7"),))
    actual = [
        _component("option_fixed", "option:7", "1.00", option_id="7"),
        _component("option_fixed", "option:7", "1.00", option_id="7"),
    ]

    result = reconcile_fee_components(contract, actual)

    assert result.passed is False
    assert result.reason_code == "duplicate_fee_component"


def test_same_total_with_offsetting_wrong_components_fails():
    contract = FeeEvidenceContract(
        required_components=(
            _component("goods", "goods:1", "10.00"),
            _component("domestic_freight", "freight:1", "5.00"),
        )
    )
    actual = [
        _component("goods", "goods:1", "11.00"),
        _component("domestic_freight", "freight:1", "4.00"),
    ]

    result = reconcile_fee_components(contract, actual)

    assert sum(item.amount_cny for item in contract.required_components) == sum(item.amount_cny for item in actual)
    assert result.passed is False
    assert result.reason_code == "fee_component_amount_mismatch"


def test_option_name_without_option_id_cannot_satisfy_required_option():
    contract = FeeEvidenceContract(required_components=(_component("option_fixed", "option:7", "2.00", option_id="7"),))
    actual = [FeeComponent(kind="option_fixed", component_id="option-name:检品", amount_cny=Decimal("2.00"), name="检品")]

    result = reconcile_fee_components(contract, actual)

    assert result.passed is False
    assert result.reason_code == "fee_component_identity_missing"


def test_forbidden_component_fails_before_total_reconciliation():
    contract = FeeEvidenceContract(
        required_components=(_component("goods", "goods:1", "10.00"),),
        forbidden_components=("coupon",),
    )
    actual = [_component("goods", "goods:1", "10.00"), _component("coupon", "coupon:1", "0.00")]

    result = reconcile_fee_components(contract, actual)

    assert result.passed is False
    assert result.reason_code == "forbidden_fee_component"


def test_extract_order_fee_components_uses_option_id_and_all_fee_parts():
    components = extract_order_fee_components(
        {
            "order_sn": "O-1",
            "other_price": "5",
            "other_price_remark": "包装费",
            "list": [
                {
                    "id": 101,
                    "sorting": 1,
                    "offer_num": 2,
                    "offer_price": "10",
                    "offer_freight": "3",
                    "option": [
                        {"id": 7, "name": "检品", "price_type": 0, "price": "2", "num": 2, "checked": True},
                        {"id": 8, "name": "保险", "price_type": 1, "price": "5", "num": 2, "checked": True},
                    ],
                }
            ],
        }
    )

    by_id = {component.component_id: component for component in components}
    assert by_id["goods:sorting:1"].amount_cny == Decimal("20.00")
    assert by_id["freight:sorting:1"].amount_cny == Decimal("3.00")
    assert by_id["freight:sorting:1"].sorting == "1"
    assert by_id["other:包装费"].amount_cny == Decimal("5.00")
    assert by_id["option:7"].amount_cny == Decimal("4.00")
    assert by_id["option:8"].amount_cny == Decimal("1.00")
    assert by_id["option:7"].option_id == "7"
    assert by_id["option:8"].option_id == "8"


def test_required_component_kind_cannot_be_downgraded_to_optional():
    contract = FeeEvidenceContract(
        required_components=(_component("option_fixed", "option:7", "4.00", option_id="7", sorting=""),),
        required_component_kinds=("goods", "domestic_freight", "other_fee", "option_fixed", "option_rate"),
    )
    actual = [_component("option_fixed", "option:7", "4.00", option_id="7", sorting="")]

    result = reconcile_fee_components(contract, actual)

    assert result.passed is False
    assert result.reason_code == "fee_component_missing"
    assert "goods" in result.reason


def test_extract_order_fee_components_reads_japan_order_detail_list():
    components = extract_order_fee_components(
        {
            "data": {
                "order_detail": [
                    {
                        "id": 201,
                        "sorting": 1,
                        "offer_num": 2,
                        "offer_price": "10",
                        "offer_freight": "3",
                        "option": [{"id": 7, "name": "检品", "price_type": 0, "price": "2", "num": 2, "checked": True}],
                    }
                ]
            }
        }
    )

    by_id = {component.component_id: component for component in components}
    assert by_id["goods:sorting:1"].amount_cny == Decimal("20.00")
    assert by_id["option:7"].amount_cny == Decimal("4.00")
