from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from typing import Any, Iterable, Mapping, Sequence

from app.system_regression.common.reconciliation import JAPAN_CNY_TO_JPY


CNY_QUANTUM = Decimal("0.01")
JPY_QUANTUM = Decimal("1")
OPTION_KINDS = frozenset({"option_fixed", "option_rate"})


def _decimal(value: Any, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是数字") from exc
    if not parsed.is_finite():
        raise ValueError(f"{label}必须是有限数字")
    return parsed


def cny(value: Any) -> Decimal:
    return _decimal(value, "人民币金额").quantize(CNY_QUANTUM, rounding=ROUND_HALF_UP)


def rate_option_amount(
    *,
    rate: Any,
    option_quantity: Any,
    goods_unit_price_cny: Any,
) -> Decimal:
    amount = (
        _decimal(rate, "OPTION费率")
        / Decimal("100")
        * _decimal(option_quantity, "OPTION数量")
        * _decimal(goods_unit_price_cny, "商品单价")
    )
    return amount.quantize(CNY_QUANTUM, rounding=ROUND_HALF_UP)


def cny_components_to_jpy(components: Iterable[Decimal], exchange_rate: Decimal | None = None) -> int:
    total_cny = sum((_decimal(value, "人民币分项") for value in components), Decimal("0"))
    rate = JAPAN_CNY_TO_JPY
    if exchange_rate not in (None, ""):
        parsed = _decimal(exchange_rate, "汇率")
        if parsed > 0:
            rate = parsed
    total_jpy = total_cny * rate
    return int(total_jpy.quantize(JPY_QUANTUM, rounding=ROUND_HALF_UP))


def _detail_rows(order_detail: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("list", "order_detail", "order_details", "details", "items"):
        value = order_detail.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, Mapping)]
    data = order_detail.get("data")
    if isinstance(data, Mapping):
        return _detail_rows(data)
    return []


def _options(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def extract_order_fee_components(order_detail: Mapping[str, Any]) -> list["FeeComponent"]:
    components: list[FeeComponent] = []
    rows = _detail_rows(order_detail)
    for index, row in enumerate(rows, 1):
        detail_id = str(row.get("id") or row.get("order_detail_id") or index)
        sorting = str(row.get("sorting") or index)
        quantity = _decimal(
            row.get("offer_num") or row.get("confirm_num") or row.get("num") or 0,
            "商品数量",
        )
        unit_price = _decimal(
            row.get("offer_price") or row.get("confirm_price") or row.get("price") or 0,
            "商品单价",
        )
        components.append(
            FeeComponent(
                kind="goods",
                component_id=f"goods:sorting:{sorting}",
                amount_cny=cny(quantity * unit_price),
                sorting=sorting,
                unit_price_cny=cny(unit_price),
                quantity=quantity,
                raw=dict(row),
            )
        )
        freight = _decimal(
            row.get("offer_freight") or row.get("confirm_freight") or row.get("freight") or 0,
            "国内运费",
        )
        if freight != 0:
            components.append(
                FeeComponent(
                    kind="domestic_freight",
                    component_id=f"freight:sorting:{sorting}",
                    amount_cny=cny(freight),
                    sorting=sorting,
                    raw=dict(row),
                )
            )
        for option in _options(row.get("option") or row.get("options")):
            if option.get("checked") is False:
                continue
            option_id = str(option.get("option_id") or option.get("id") or option.get("key") or "")
            if not option_id:
                option_id = ""
            price_type = str(option.get("price_type") or "0")
            option_quantity = _decimal(option.get("num") or option.get("quantity") or 0, "OPTION数量")
            option_price = _decimal(option.get("price") or 0, "OPTION金额")
            amount = (
                rate_option_amount(
                    rate=option_price,
                    option_quantity=option_quantity,
                    goods_unit_price_cny=unit_price,
                )
                if price_type == "1"
                else cny(option_price * option_quantity)
            )
            components.append(
                FeeComponent(
                    kind="option_rate" if price_type == "1" else "option_fixed",
                    component_id=f"option:{option_id}" if option_id else f"option-name:{option.get('name') or ''}",
                    amount_cny=amount,
                    option_id=option_id,
                    sorting=sorting,
                    name=str(option.get("name") or ""),
                    price_type=price_type,
                    unit_price_cny=cny(option_price),
                    quantity=option_quantity,
                    rate=option_price if price_type == "1" else None,
                    raw=dict(option),
                )
            )

    root = order_detail.get("data") if isinstance(order_detail.get("data"), Mapping) else order_detail
    other_amount = _decimal(root.get("other_price") or root.get("other_fee_amount") or 0, "其他费用")
    if other_amount != 0:
        other_name = str(root.get("other_price_remark") or root.get("other_fee_name") or "其他费用")
        components.append(
            FeeComponent(
                kind="other_fee",
                component_id=f"other:{other_name}",
                amount_cny=cny(other_amount),
                name=other_name,
                raw={"amount": str(other_amount), "name": other_name},
            )
        )
    return components


@dataclass(frozen=True)
class FeeComponent:
    kind: str
    component_id: str
    amount_cny: Decimal
    option_id: str = ""
    sorting: str = ""
    name: str = ""
    price_type: str = ""
    unit_price_cny: Decimal | None = None
    quantity: Decimal | None = None
    rate: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", str(self.kind or ""))
        object.__setattr__(self, "component_id", str(self.component_id or ""))
        object.__setattr__(self, "amount_cny", cny(self.amount_cny))
        object.__setattr__(self, "option_id", str(self.option_id or ""))
        object.__setattr__(self, "sorting", str(self.sorting or ""))


@dataclass(frozen=True)
class FeeEvidenceContract:
    required_components: tuple[FeeComponent, ...] = ()
    required_component_kinds: tuple[str, ...] = ()
    optional_components: tuple[str, ...] = ()
    forbidden_components: tuple[str, ...] = ()
    system_generated_components: tuple[str, ...] = ()
    tolerance_jpy: int = 1


@dataclass(frozen=True)
class FeeReconciliation:
    passed: bool
    reason_code: str = ""
    reason: str = ""
    required_components: tuple[FeeComponent, ...] = ()
    actual_components: tuple[FeeComponent, ...] = ()


def _failed(
    contract: FeeEvidenceContract,
    actual: Sequence[FeeComponent],
    reason_code: str,
    reason: str,
) -> FeeReconciliation:
    return FeeReconciliation(
        passed=False,
        reason_code=reason_code,
        reason=reason,
        required_components=contract.required_components,
        actual_components=tuple(actual),
    )


def reconcile_fee_components(
    contract: FeeEvidenceContract,
    actual_components: Sequence[FeeComponent],
) -> FeeReconciliation:
    actual = tuple(actual_components)
    for component in actual:
        if component.kind in OPTION_KINDS and not component.option_id:
            return _failed(
                contract,
                actual,
                "fee_component_identity_missing",
                f"OPTION 分项缺少 option_id：{component.name or component.component_id}",
            )

    def identity(component: FeeComponent) -> tuple[str, str, str]:
        sorting = "" if component.kind in OPTION_KINDS else component.sorting
        return component.kind, component.component_id, sorting

    # 判重必须区分明细行：多条明细勾选同一个 OPTION 是合法场景，
    # 只有同一明细上重复出现同一分项才算重复计费。
    duplicate_identities = [
        (component.kind, component.component_id, component.sorting) for component in actual
    ]
    duplicates = [identity for identity, count in Counter(duplicate_identities).items() if count > 1]
    if duplicates:
        return _failed(
            contract,
            actual,
            "duplicate_fee_component",
            f"费用分项重复：{duplicates[0]}",
        )

    forbidden = set(contract.forbidden_components)
    forbidden_found = [component for component in actual if component.kind in forbidden]
    if forbidden_found:
        return _failed(
            contract,
            actual,
            "forbidden_fee_component",
            f"出现禁止费用分项：{forbidden_found[0].kind}",
        )

    actual_kinds = {component.kind for component in actual}
    for required_kind in contract.required_component_kinds:
        if required_kind not in actual_kinds:
            return _failed(
                contract,
                actual,
                "fee_component_missing",
                f"缺少必需费用类型：{required_kind}",
            )

    actual_by_identity = {
        identity(component): component
        for component in actual
    }
    for expected in contract.required_components:
        expected_identity = identity(expected)
        found = actual_by_identity.get(expected_identity)
        if found is None:
            code = "fee_component_identity_missing" if expected.kind in OPTION_KINDS else "fee_component_missing"
            return _failed(contract, actual, code, f"缺少费用分项：{expected.component_id}")
        if expected.kind in OPTION_KINDS and found.option_id != expected.option_id:
            return _failed(
                contract,
                actual,
                "fee_component_identity_missing",
                f"OPTION 标识不一致：{expected.component_id}",
            )
        if found.kind != expected.kind:
            return _failed(
                contract,
                actual,
                "fee_component_type_mismatch",
                f"费用类型不一致：{expected.component_id}",
            )
        if found.amount_cny != expected.amount_cny:
            return _failed(
                contract,
                actual,
                "fee_component_amount_mismatch",
                f"费用金额不一致：{expected.component_id}",
            )

    known_kinds = {
        component.kind for component in contract.required_components
    } | set(contract.optional_components) | set(contract.system_generated_components)
    unexpected = [component for component in actual if component.kind not in known_kinds]
    if unexpected:
        return _failed(
            contract,
            actual,
            "unexpected_fee_component",
            f"出现未声明费用分项：{unexpected[0].kind}",
        )
    return FeeReconciliation(
        passed=True,
        required_components=contract.required_components,
        actual_components=actual,
    )


__all__ = [
    "FeeComponent",
    "FeeEvidenceContract",
    "FeeReconciliation",
    "JAPAN_CNY_TO_JPY",
    "cny_components_to_jpy",
    "extract_order_fee_components",
    "rate_option_amount",
    "reconcile_fee_components",
]
