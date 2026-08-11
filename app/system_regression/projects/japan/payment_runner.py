from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Mapping

from app.data_scripts.payment_amount_regression.runner import LivePaymentRegressionExecutor, ScenarioBlocked
from app.data_scripts.payment_amount_regression.scenarios import ScenarioSpec

from .fee_evidence import (
    FeeComponent,
    FeeEvidenceContract,
    extract_order_fee_components,
    rate_option_amount,
    reconcile_fee_components,
)
from .runner import CaseRunResult


def _money_value(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("value", 0)
    return str(value if value not in (None, "") else "0")


def build_payment_variables(parameters: Mapping[str, Any]) -> dict[str, Any]:
    values = {
        key: value
        for key, value in dict(parameters).items()
        if key not in {"order", "items", "actual_amount", "actual_evidence", "actual"}
    }
    order = parameters.get("order") if isinstance(parameters.get("order"), Mapping) else {}
    items = [dict(row) for row in parameters.get("items", []) if isinstance(row, Mapping)]
    item_count = int(order.get("item_count") or parameters.get("item_count") or len(items) or 1)
    default_quantity = int(order.get("default_quantity") or 1)
    values["cart_item_count"] = item_count
    values["order_item_num"] = default_quantity

    other_fee = order.get("other_fee_amount", parameters.get("other_fee_amount", "0"))
    values["other_price"] = _money_value(other_fee)
    values["other_price_remark"] = str(
        order.get("other_fee_name") or parameters.get("other_fee_name") or "系统回归其他费用"
    )

    if items:
        values["system_regression_items"] = items
        values["offer_unit_prices"] = [
            _money_value(row.get("offer_price") or row.get("confirm_price") or row.get("purchase_price"))
            for row in items
        ]
        values["offer_freights"] = [
            _money_value(row.get("offer_freight") or row.get("confirm_freight") or row.get("purchase_freight"))
            for row in items
        ]
        option_counts: dict[str, int] = {}
        for row in items:
            for option in row.get("options") or []:
                if not isinstance(option, Mapping) or option.get("checked") is False:
                    continue
                key = str(option.get("key") or option.get("id") or option.get("name") or "").strip()
                if key:
                    option_counts[key] = option_counts.get(key, 0) + int(option.get("num") or 0)
        if option_counts:
            values["order_option_counts"] = option_counts

    first_payment_rate = Decimal(str(parameters.get("first_payment_rate") or "0.5"))
    values["order_part_pay_percent"] = int(first_payment_rate * Decimal("100"))
    values["finance_confirm"] = bool(parameters.get("finance_confirm", True))
    return values


class PaymentRunner:
    def __init__(
        self,
        env: Any,
        *,
        base_variables: Mapping[str, Any] | None = None,
        executor_factory: Callable[[Any, Mapping[str, Any]], Any] = LivePaymentRegressionExecutor,
        option_catalog_loader: Callable[[Any, Mapping[str, Any]], Mapping[str, Any]] | None = None,
        fee_evidence_loader: Callable[[Any, Mapping[str, Any], str], list[Mapping[str, Any]]] | None = None,
    ) -> None:
        self.env = env
        self.base_variables = dict(base_variables or {})
        self.executor_factory = executor_factory
        if option_catalog_loader is None:
            from app.data_scripts.orders import inspect_order_options

            option_catalog_loader = inspect_order_options
        self.option_catalog_loader = option_catalog_loader
        self.fee_evidence_loader = fee_evidence_loader or self._load_fee_evidence

    @staticmethod
    def _load_fee_evidence(
        env: Any,
        variables: Mapping[str, Any],
        order_sn: str,
    ) -> list[Mapping[str, Any]]:
        from app.data_scripts.problem_goods import ProblemGoodsGateway

        gateway = ProblemGoodsGateway(
            env,
            dict(variables),
            {"script": "日本站系统回归费用证据", "order_sn": order_sn},
        )
        detail = gateway.order_detail(order_sn)
        return [PaymentRunner._component_dict(component) for component in extract_order_fee_components(detail)]

    @staticmethod
    def _component_dict(component: FeeComponent) -> dict[str, Any]:
        return {
            "kind": component.kind,
            "component_id": component.component_id,
            "amount_cny": str(component.amount_cny),
            "option_id": component.option_id,
            "sorting": component.sorting,
            "name": component.name,
            "price_type": component.price_type,
        }

    def _apply_fee_profile(
        self,
        parameters: Mapping[str, Any],
        variables: dict[str, Any],
    ) -> FeeEvidenceContract | None:
        option_profile = str(parameters.get("option_profile") or "")
        fee_profile = str(parameters.get("fee_profile") or "")
        if option_profile != "fixed_and_rate" and fee_profile != "all":
            return None
        catalog = dict(self.option_catalog_loader(self.env, variables) or {})
        options = [dict(row) for row in catalog.get("options") or [] if isinstance(row, Mapping)]
        fixed = next((row for row in options if int(row.get("price_type") or 0) == 0 and row.get("id") not in (None, "")), None)
        rate = next((row for row in options if int(row.get("price_type") or 0) == 1 and row.get("id") not in (None, "")), None)
        if fixed is None or rate is None:
            raise RuntimeError("缺少可通过 option_id 识别的固定金额或百分比 OPTION")
        quantity = max(1, int(parameters.get("option_quantity") or 2))
        goods_unit_price = Decimal(str(parameters.get("offer_price") or parameters.get("payment_regression_offer_price") or "10"))
        counts: dict[str, int] = {}
        required: list[FeeComponent] = []
        for row in (fixed, rate):
            option_id = str(row["id"])
            key = str(row.get("key") or option_id)
            counts[key] = quantity
            price_type = int(row.get("price_type") or 0)
            price = Decimal(str(row.get("price") or 0))
            amount = (
                rate_option_amount(
                    rate=price,
                    option_quantity=quantity,
                    goods_unit_price_cny=goods_unit_price,
                )
                if price_type == 1
                else price * quantity
            )
            required.append(
                FeeComponent(
                    kind="option_rate" if price_type == 1 else "option_fixed",
                    component_id=f"option:{option_id}",
                    amount_cny=amount,
                    option_id=option_id,
                    sorting="1",
                    name=str(row.get("name") or ""),
                    price_type=str(price_type),
                )
            )
        variables["order_option_counts"] = counts
        if fee_profile == "all":
            item_count = max(2, int(parameters.get("item_count") or 2))
            item_quantity = max(1, int(parameters.get("item_quantity") or 2))
            unit_prices = [
                str(value)
                for value in parameters.get("offer_unit_prices") or ["10"] * item_count
            ][:item_count]
            freights = [
                str(value)
                for value in parameters.get("offer_freights") or [str(index + 3) for index in range(item_count)]
            ][:item_count]
            if len(unit_prices) != item_count or len(freights) != item_count:
                raise ValueError("全费用场景的商品单价和单番国内运费数量必须与番号数一致")
            variables["cart_item_count"] = item_count
            variables["order_item_num"] = item_quantity
            variables["offer_unit_prices"] = unit_prices
            variables["offer_freights"] = freights
            variables["other_price"] = str(parameters.get("other_fee_amount") or "5")
            variables["other_price_remark"] = str(parameters.get("other_fee_name") or "系统回归包装费")
            for index in range(item_count):
                sorting = str(index + 1)
                required.extend(
                    [
                        FeeComponent(
                            kind="goods",
                            component_id=f"goods:sorting:{sorting}",
                            amount_cny=Decimal(unit_prices[index]) * item_quantity,
                            sorting=sorting,
                        ),
                        FeeComponent(
                            kind="domestic_freight",
                            component_id=f"freight:sorting:{sorting}",
                            amount_cny=Decimal(freights[index]),
                            sorting=sorting,
                        ),
                    ]
                )
            required.append(
                FeeComponent(
                    kind="other_fee",
                    component_id=f"other:{variables['other_price_remark']}",
                    amount_cny=Decimal(variables["other_price"]),
                    name=variables["other_price_remark"],
                )
            )
        contract = FeeEvidenceContract(
            required_components=tuple(required),
            required_component_kinds=(
                ("goods", "domestic_freight", "other_fee", "option_fixed", "option_rate")
                if fee_profile == "all"
                else ("option_fixed", "option_rate")
            ),
            optional_components=() if fee_profile == "all" else ("goods", "domestic_freight", "other_fee"),
            system_generated_components=("service_fee",),
        )
        variables["system_regression_fee_contract"] = {
            "required_components": [self._component_dict(component) for component in required],
            "required_component_kinds": list(contract.required_component_kinds),
            "optional_components": list(contract.optional_components),
            "forbidden_components": list(contract.forbidden_components),
            "system_generated_components": list(contract.system_generated_components),
        }
        return contract

    def execute(self, case: Mapping[str, Any], context: Mapping[str, Any]) -> CaseRunResult:
        runner_kind = str(case.get("runner_kind") or "")
        category_by_runner = {
            "order_payment": "order",
            "order_part_payment": "order_part",
            "porder_payment": "porder",
        }
        if runner_kind not in category_by_runner:
            raise ValueError(f"不支持的支付执行类型：{runner_kind}")
        parameters = dict(case.get("parameters") or {})
        variables = {
            **self.base_variables,
            **dict(context.get("variables") or {}),
            **build_payment_variables(parameters),
        }
        fee_contract = self._apply_fee_profile(parameters, variables)
        scenario = ScenarioSpec(
            key=str(case.get("case_key") or ""),
            name=str(case.get("name") or case.get("case_key") or ""),
            category=category_by_runner[runner_kind],
            payment_mode=str(parameters.get("payment_mode") or "balance"),
            expected_direction=str((case.get("expectation") or {}).get("direction") or "debit"),
        )
        executor = self.executor_factory(self.env, variables)
        try:
            payload = dict(executor.execute(scenario, str(context.get("batch_no") or "SYSTEM-REGRESSION")) or {})
        except ScenarioBlocked as exc:
            if not exc.reason_code:
                raise
            evidence = dict(exc.evidence)
            return CaseRunResult(
                status="blocked",
                order_sn=str(evidence.get("order_sn") or ""),
                result=evidence,
                reason_code=exc.reason_code,
                error_message=str(exc),
            )
        checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
        fee_check = None
        if fee_contract is not None:
            if not isinstance(payload.get("fee_components"), list):
                payload["fee_components"] = list(
                    self.fee_evidence_loader(
                        self.env,
                        variables,
                        str(payload.get("order_sn") or ""),
                    )
                )
            actual_components = [
                FeeComponent(
                    kind=str(row.get("kind") or ""),
                    component_id=str(row.get("component_id") or ""),
                    amount_cny=Decimal(str(row.get("amount_cny") or 0)),
                    option_id=str(row.get("option_id") or ""),
                    sorting=str(row.get("sorting") or ""),
                    name=str(row.get("name") or ""),
                    price_type=str(row.get("price_type") or ""),
                    raw=dict(row),
                )
                for row in payload.get("fee_components") or []
                if isinstance(row, Mapping)
            ]
            fee_check = reconcile_fee_components(fee_contract, actual_components)
            checks.append(
                {
                    "passed": fee_check.passed,
                    "reason_code": fee_check.reason_code,
                    "reason": fee_check.reason,
                }
            )
            payload["checks"] = checks
            payload["fee_contract"] = variables["system_regression_fee_contract"]
        passed = payload.get("status") == "passed" and all(row.get("passed") is not False for row in checks)
        reason = next((str(row.get("reason") or "") for row in checks if row.get("passed") is False), "")
        reason_code = next((str(row.get("reason_code") or "") for row in checks if row.get("passed") is False), "")
        return CaseRunResult(
            status="passed" if passed else "failed",
            order_sn=str(payload.get("order_sn") or ""),
            porder_sn=str(payload.get("porder_sn") or ""),
            result=payload,
            reason_code="" if passed else (reason_code or "amount_mismatch"),
            error_message=reason,
        )


__all__ = ["PaymentRunner", "build_payment_variables"]
