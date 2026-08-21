from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Mapping

from app.data_scripts.payment_amount_regression.runner import LivePaymentRegressionExecutor, ScenarioBlocked
from app.data_scripts.payment_amount_regression.scenarios import ScenarioSpec
from app.services.system_regression.membership_service import (
    apply_membership_to_variables,
    inspect_membership_from_env,
    public_membership,
)
from app.services.system_regression.ticket_service import list_usable_tickets

from .fee_evidence import (
    FeeComponent,
    FeeEvidenceContract,
    extract_order_fee_components,
    rate_option_amount,
    reconcile_fee_components,
)
from .panel import ACCOUNT_COUPON_ID, ACCOUNT_VOUCHER_ID, SERVICE_COUPON_ID
from .runner import CaseRunResult


def _money_value(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("value", 0)
    return str(value if value not in (None, "") else "0")


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _coupon_selected_id(parameters: Mapping[str, Any]) -> str:
    coupon = _mapping(parameters.get("coupon"))
    return str(coupon.get("selectedId") or coupon.get("selected_id") or "").strip()


def _voucher_selected_id(parameters: Mapping[str, Any]) -> str:
    porder = _mapping(parameters.get("porder"))
    voucher = _mapping(porder.get("voucher"))
    return str(voucher.get("selectedId") or voucher.get("selected_id") or "").strip()


def _ticket_amount(row: Mapping[str, Any]) -> str:
    amount = row.get("amount")
    if amount in (None, ""):
        return ""
    text = str(amount).strip()
    return "" if text in {"", "0", "0.0"} else text


def _copy_payment_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    values = dict(parameters)
    coupon = _mapping(values.get("coupon"))
    if coupon:
        values["coupon"] = dict(coupon)
    porder = _mapping(values.get("porder"))
    if porder:
        copied = dict(porder)
        voucher = _mapping(copied.get("voucher"))
        if voucher:
            copied["voucher"] = dict(voucher)
        values["porder"] = copied
    return values


def _pick_account_coupon(tickets: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = [dict(row) for row in tickets.get("coupons") or [] if isinstance(row, Mapping) and row.get("id")]
    return rows[0] if rows else None


def _pick_account_voucher(tickets: Mapping[str, Any], logistics_id: str = "") -> dict[str, Any] | None:
    rows = [dict(row) for row in tickets.get("vouchers") or [] if isinstance(row, Mapping) and row.get("id")]
    if not rows:
        return None
    wanted = str(logistics_id or "").strip()
    if wanted:
        matched = [row for row in rows if str(row.get("logistics_id") or "").strip() == wanted]
        if matched:
            with_amount = [row for row in matched if _ticket_amount(row)]
            return with_amount[0] if with_amount else matched[0]
    all_kind = [row for row in rows if str(row.get("kind") or "") == "all"]
    if all_kind:
        return all_kind[0]
    with_amount = [row for row in rows if _ticket_amount(row)]
    return with_amount[0] if with_amount else rows[0]


def bind_account_tickets(
    env: Any,
    parameters: Mapping[str, Any],
    variables: Mapping[str, Any] | None = None,
    *,
    runner_kind: str = "",
) -> dict[str, Any]:
    values = _copy_payment_parameters(parameters)
    need_coupon = _coupon_selected_id(values) == ACCOUNT_COUPON_ID
    need_voucher = runner_kind == "porder_payment" and _voucher_selected_id(values) == ACCOUNT_VOUCHER_ID
    if not need_coupon and not need_voucher:
        return values
    tickets = list_usable_tickets(env, variables)
    if need_coupon:
        coupon = _pick_account_coupon(tickets)
        if coupon is None:
            raise ScenarioBlocked(
                str(tickets.get("reason") or "账号没有可用订单优惠券，无法做用券后金额比对"),
                reason_code="missing_coupon",
                evidence={"tickets_reason": str(tickets.get("reason") or "")},
            )
        coupon_block = dict(_mapping(values.get("coupon")))
        coupon_block["selectedId"] = str(coupon["id"])
        values["coupon"] = coupon_block
        values["discounts_id"] = str(coupon["id"])
        values["service_discount"] = True
        amount = _ticket_amount(coupon)
        if amount:
            values["payment_regression_discount_jpy"] = amount
    if need_voucher:
        porder = dict(_mapping(values.get("porder")))
        voucher = _pick_account_voucher(tickets, str(porder.get("logistics") or ""))
        if voucher is None:
            raise ScenarioBlocked(
                str(tickets.get("reason") or "账号没有可用配送单代金券，无法做用券后金额比对"),
                reason_code="missing_voucher",
                evidence={"tickets_reason": str(tickets.get("reason") or "")},
            )
        voucher_block = dict(_mapping(porder.get("voucher")))
        voucher_block["selectedId"] = str(voucher["id"])
        porder["voucher"] = voucher_block
        logistics_id = str(voucher.get("logistics_id") or "").strip()
        if logistics_id:
            porder["logistics"] = logistics_id
        values["porder"] = porder
        # 代金券只能打在配送单支付上；写进 discounts_id 会在造订单时被当成优惠券提交
        values.pop("discounts_id", None)
        values["porder_discounts_id"] = str(voucher["id"])
        amount = _ticket_amount(voucher)
        if amount:
            values["payment_regression_voucher_jpy"] = amount
    return values


def build_payment_variables(parameters: Mapping[str, Any], *, runner_kind: str = "") -> dict[str, Any]:
    values = {
        key: value
        for key, value in dict(parameters).items()
        if key not in {"order", "items", "actual_amount", "actual_evidence", "actual", "part_pay", "coupon", "porder", "problem_goods"}
    }
    order = _mapping(parameters.get("order"))
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
    default_offer = order.get("default_offer_price") or (items[0].get("offer_price") if items else None)
    if default_offer is not None:
        values["payment_regression_offer_price"] = _money_value(default_offer)
        values["offer_price"] = _money_value(default_offer)

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
                    option_counts[key] = option_counts.get(key, 0) + int(option.get("num") or option.get("order_num") or 0)
        if option_counts:
            values["order_option_counts"] = option_counts

    part_pay = _mapping(parameters.get("part_pay"))
    part_enabled = bool(part_pay.get("enabled")) or str(parameters.get("payment_plan") or "") == "part"
    if part_pay.get("percent") not in (None, ""):
        percent = int(part_pay.get("percent"))
    else:
        percent = int(Decimal(str(parameters.get("first_payment_rate") or "0.5")) * Decimal("100"))
    values["first_payment_rate"] = str((Decimal(percent) / Decimal("100")).quantize(Decimal("0.01")))
    values["order_part_pay_percent"] = percent
    values["payment_regression_part_pay_percent"] = percent
    values["order_part_pay"] = 1 if part_enabled else 0
    values["_full_flow_part_pay_script"] = bool(part_enabled)
    values["payment_plan"] = "part" if part_enabled else str(parameters.get("payment_plan") or "full")
    if part_enabled:
        values["order_part_pay_tail_node"] = str(part_pay.get("tail_node") or "before_shelf")
        values["order_part_pay_tail_partial_enabled"] = 1 if part_pay.get("tail_partial") else 0
        values["order_part_pay_tail_select_by"] = "sorting"
        values["order_part_pay_tail_sortings"] = str(part_pay.get("tail_sortings") or "")
        timing = part_pay.get("fee_timing") if isinstance(part_pay.get("fee_timing"), Mapping) else {}
        values["order_part_pay_fee_timing"] = {
            key: ("tail" if str(timing.get(key) or "first") == "tail" else "first")
            for key in ("domestic_freight", "service_fee", "additional_service_fee", "other_fee")
        }

    coupon_id = _coupon_selected_id(parameters)
    values["service_discount"] = bool(parameters.get("service_discount")) or bool(coupon_id)
    porder = _mapping(parameters.get("porder"))
    apply_porder = runner_kind == "porder_payment" or (
        runner_kind == "" and isinstance(parameters.get("porder"), Mapping) and bool(porder)
    )
    if not apply_porder:
        if coupon_id and coupon_id not in {SERVICE_COUPON_ID, ACCOUNT_COUPON_ID}:
            values["discounts_id"] = coupon_id
        elif parameters.get("discounts_id"):
            values["discounts_id"] = str(parameters.get("discounts_id") or "")

    if apply_porder:
        values["warehouse_sku_count"] = int(porder.get("sku_count") or 1)
        values["send_num"] = int(porder.get("send_num") or 1)
        values["box_count"] = str(porder.get("box_count") or "1")
        values["box_length"] = str(porder.get("box_length") or "58")
        values["box_width"] = str(porder.get("box_width") or "51")
        values["box_height"] = str(porder.get("box_height") or "50")
        values["box_weight"] = str(porder.get("box_weight") or "10")
        values["delivery_quote_logistics_id"] = str(porder.get("logistics") or "25")
        voucher_id = _voucher_selected_id(parameters)
        if runner_kind == "porder_payment":
            if voucher_id and voucher_id != ACCOUNT_VOUCHER_ID:
                values["porder_discounts_id"] = voucher_id
            elif parameters.get("porder_discounts_id"):
                values["porder_discounts_id"] = str(parameters.get("porder_discounts_id") or "")
            values.pop("discounts_id", None)
        elif voucher_id and voucher_id != ACCOUNT_VOUCHER_ID:
            values["discounts_id"] = voucher_id
        if porder.get("price_manual"):
            values["logistics_price_artificial"] = _money_value(porder.get("logistics_price"))
            values["logistics_price_from_api"] = False
        else:
            values["logistics_price_from_api"] = True
            values.pop("logistics_price_artificial", None)

    wait_seconds = int(parameters.get("ledger_wait_seconds") or 30)
    values["ledger_wait_seconds"] = wait_seconds
    evidence_delay = 0.5
    values["payment_regression_evidence_delay"] = evidence_delay
    values["payment_regression_evidence_retries"] = max(1, int(wait_seconds / evidence_delay))
    values["finance_confirm"] = bool(parameters.get("finance_confirm", True))
    values["compare_actual_from_balance_change"] = True
    values["compare_ledger_after_payment"] = True
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
            # 下单流程只消费单数 offer_freight（缺省 5），逐番 offer_freights 不会入单；
            # 合同期望必须与实际提交口径一致，各番运费都按单数值计
            freight_each = _money_value(parameters.get("offer_freight") or variables.get("offer_freight") or 5)
            freights = [freight_each] * item_count
            if len(unit_prices) != item_count or len(freights) != item_count:
                raise ValueError("全费用场景的商品单价和单番国内运费数量必须与番号数一致")
            variables["cart_item_count"] = item_count
            variables["order_item_num"] = item_quantity
            variables["offer_unit_prices"] = unit_prices
            variables["offer_freights"] = freights
            variables["offer_freight"] = freight_each
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
        part_pay = _mapping(parameters.get("part_pay"))
        if runner_kind in {"order_payment", "order_part_payment"}:
            if "enabled" in part_pay:
                category = "order_part" if part_pay.get("enabled") else "order"
            elif str(parameters.get("payment_plan") or "") == "part" or runner_kind == "order_part_payment":
                category = "order_part"
            else:
                category = "order"
        else:
            category = category_by_runner[runner_kind]
        context_variables = dict(context.get("variables") or {})
        try:
            parameters = bind_account_tickets(
                self.env,
                parameters,
                {**self.base_variables, **context_variables},
                runner_kind=runner_kind,
            )
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
        variables = {
            **self.base_variables,
            **context_variables,
            **build_payment_variables(parameters, runner_kind=runner_kind),
        }
        membership = inspect_membership_from_env(self.env, variables)
        apply_membership_to_variables(variables, membership)
        fee_contract = self._apply_fee_profile(parameters, variables)
        scenario = ScenarioSpec(
            key=str(case.get("case_key") or ""),
            name=str(case.get("name") or case.get("case_key") or ""),
            category=category,
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
        payload["membership"] = public_membership(membership)
        ticket_id = str(variables.get("discounts_id") or variables.get("porder_discounts_id") or "")
        if ticket_id:
            payload["used_ticket"] = {
                "discounts_id": ticket_id,
                "discount_jpy": str(variables.get("payment_regression_discount_jpy") or ""),
                "voucher_jpy": str(variables.get("payment_regression_voucher_jpy") or ""),
            }
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


__all__ = ["PaymentRunner", "bind_account_tickets", "build_payment_variables"]
