from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
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
    cny_components_to_jpy,
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


def _configured_order_expected_jpy(
    parameters: Mapping[str, Any],
    membership: Mapping[str, Any],
) -> Decimal | None:
    items = [dict(row) for row in parameters.get("items", []) if isinstance(row, Mapping)]
    exchange_rate = Decimal(str(membership.get("preview_cny_to_jpy") or 0))
    if not items or exchange_rate <= 0:
        return None
    goods = Decimal("0")
    freight = Decimal("0")
    options = Decimal("0")
    for row in items:
        quantity = Decimal(str(row.get("quantity") or 1))
        unit_price = Decimal(_money_value(row.get("offer_price")))
        goods += unit_price * quantity
        freight += Decimal(_money_value(row.get("offer_freight")))
        for option in row.get("options") or []:
            if not isinstance(option, Mapping) or option.get("checked") is False:
                continue
            option_quantity = Decimal(str(option.get("num") or 1))
            option_price = Decimal(str(option.get("price") or 0))
            if int(option.get("price_type") or 0) == 1:
                options += unit_price * option_quantity * option_price / Decimal("100")
            else:
                options += option_price * option_quantity
    order = _mapping(parameters.get("order"))
    other = Decimal(_money_value(order.get("other_fee_amount", parameters.get("other_fee_amount", 0))))
    coupon = _mapping(parameters.get("coupon"))
    ticket_discount_jpy = Decimal(str(parameters.get("payment_regression_discount_jpy") or 0))
    coupon_enabled = bool(coupon.get("selectedId") or parameters.get("service_discount"))
    service_rate = Decimal(str(membership.get("service_rate") or 0))
    service = Decimal("0") if coupon_enabled and ticket_discount_jpy <= 0 else goods * service_rate
    gross_jpy = Decimal(cny_components_to_jpy((goods, freight, options, other, service), exchange_rate))
    if coupon_enabled and ticket_discount_jpy <= 0:
        # 日本站手续费全免券按最终日元金额截尾，13 CNY * 21.20 = 275.6 实扣 275。
        gross_jpy = (sum((goods, freight, options, other), Decimal("0")) * exchange_rate).quantize(
            Decimal("1"), rounding=ROUND_DOWN
        )
    return max(Decimal("0"), gross_jpy - ticket_discount_jpy)


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


def _coupon_is_fee_waiver(row: Mapping[str, Any]) -> bool:
    if "fee_waiver" in row:
        return bool(row.get("fee_waiver"))
    title = str(row.get("title") or "")
    return ("手数料" in title or "手续费" in title) and any(
        word in title for word in ("無料", "免费", "免費", "减免", "減免")
    )


def _pick_account_coupon(
    tickets: Mapping[str, Any],
    *,
    fee_waiver: bool,
) -> dict[str, Any] | None:
    rows = [dict(row) for row in tickets.get("coupons") or [] if isinstance(row, Mapping) and row.get("id")]
    if fee_waiver:
        return next((row for row in rows if _coupon_is_fee_waiver(row)), None)
    monetary = [row for row in rows if not _coupon_is_fee_waiver(row) and _ticket_amount(row)]
    if monetary:
        return monetary[0]
    non_waiver = next((row for row in rows if not _coupon_is_fee_waiver(row)), None)
    return non_waiver or next((row for row in rows if _coupon_is_fee_waiver(row)), None)


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
    need_coupon = _coupon_selected_id(values) in {SERVICE_COUPON_ID, ACCOUNT_COUPON_ID}
    need_voucher = runner_kind == "porder_payment" and _voucher_selected_id(values) == ACCOUNT_VOUCHER_ID
    if not need_coupon and not need_voucher:
        return values
    tickets = list_usable_tickets(env, variables)
    if need_coupon:
        selected_id = _coupon_selected_id(values)
        coupon = _pick_account_coupon(tickets, fee_waiver=selected_id == SERVICE_COUPON_ID)
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
    # orders.py consumes order_item_count; keep it aligned with the panel's item count
    # instead of falling back to its generic two-item default.
    values["order_item_count"] = item_count
    # full_flow 的仓库准备阶段优先读取 order_per_shop/per_shop；显式覆盖这些
    # 通用变量，避免运行上下文里的默认 2 番把页面配置重新改回去。
    values["order_shop_count"] = 1
    values["order_per_shop"] = item_count
    values["per_shop"] = item_count
    values["order_item_num"] = default_quantity
    # payment_amount_regression 的报价阶段读取该专用字段；不写会把页面数量回退成 1。
    values["payment_regression_item_num"] = default_quantity

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
        values["confirm_freights"] = list(values["offer_freights"])
        if not values.get("offer_freight"):
            values["offer_freight"] = values["offer_freights"][0]
        if not values.get("confirm_freight"):
            values["confirm_freight"] = values["offer_freight"]
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
        values["other_price"] = _money_value(porder.get("extra_fee"))
        values["other_price_remark"] = str(porder.get("extra_name") or "系统回归配送附加费")
        values["warehouse_sku_count"] = int(porder.get("sku_count") or 1)
        values["send_num"] = int(porder.get("send_num") or 1)
        values["box_count"] = str(porder.get("box_count") or "1")
        values["box_length"] = str(porder.get("box_length") or "58")
        values["box_width"] = str(porder.get("box_width") or "51")
        values["box_height"] = str(porder.get("box_height") or "50")
        values["box_weight"] = str(porder.get("box_weight") or "10")
        values["delivery_quote_logistics_id"] = str(porder.get("logistics") or "25")
        # 系统回归要求实走线路与页面配置完全一致，不允许通用流程静默降级到其他线路。
        values["strict_delivery_logistics"] = True
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
        order_evidence_loader: Callable[[Any, Mapping[str, Any], str], Mapping[str, Any]] | None = None,
        porder_evidence_loader: Callable[[Any, Mapping[str, Any], str], Mapping[str, Any]] | None = None,
    ) -> None:
        self.env = env
        self.base_variables = dict(base_variables or {})
        self.executor_factory = executor_factory
        if option_catalog_loader is None:
            from app.data_scripts.orders import inspect_order_options

            option_catalog_loader = inspect_order_options
        self.option_catalog_loader = option_catalog_loader
        self.fee_evidence_loader = fee_evidence_loader or self._load_fee_evidence
        self.order_evidence_loader = order_evidence_loader
        self.porder_evidence_loader = porder_evidence_loader or self._load_porder_evidence

    @staticmethod
    def _load_order_evidence(
        env: Any,
        variables: Mapping[str, Any],
        order_sn: str,
    ) -> Mapping[str, Any]:
        from app.data_scripts.problem_goods import ProblemGoodsGateway

        gateway = ProblemGoodsGateway(
            env,
            dict(variables),
            {"script": "日本站系统回归订单详情核验", "order_sn": order_sn},
        )
        return dict(gateway.order_detail(order_sn) or {})

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
    def _load_porder_evidence(
        env: Any,
        variables: Mapping[str, Any],
        porder_sn: str,
    ) -> Mapping[str, Any]:
        from app.data_scripts.problem_goods import ProblemGoodsGateway

        gateway = ProblemGoodsGateway(
            env,
            dict(variables),
            {"script": "日本站系统回归配送单详情核验", "porder_sn": porder_sn},
        )
        payload = gateway._admin_request(
            "/porder.detail",
            {"porder_sn": porder_sn},
            "查询配送单详情",
            mutation=False,
        )
        return dict(payload.get("data") or {}) if isinstance(payload, Mapping) else {}

    @staticmethod
    def _porder_config_check(parameters: Mapping[str, Any], detail: Mapping[str, Any]) -> dict[str, Any]:
        configured = _mapping(parameters.get("porder"))
        logistics = _mapping(detail.get("logistics"))
        differences: list[dict[str, str]] = []

        def compare(field: str, expected: Any, actual: Any) -> None:
            if str(expected) != str(actual):
                differences.append({"field": field, "expected": str(expected), "actual": str(actual)})

        def compare_money(field: str, expected: Any, actual: Any) -> None:
            if Decimal(str(expected or "0")) != Decimal(str(actual or "0")):
                differences.append({"field": field, "expected": str(expected), "actual": str(actual)})

        compare("logistics", str(configured.get("logistics") or "25"), str(logistics.get("id") or ""))
        if configured.get("price_manual"):
            compare_money("logistics_price", _money_value(configured.get("logistics_price")), _money_value(detail.get("logistics_price")))
        extra_fee = _money_value(configured.get("extra_fee"))
        compare_money("extra_fee", extra_fee, _money_value(detail.get("other_price")))
        status = int(detail.get("status") or 0)
        if status != 50:
            differences.append({"field": "status", "expected": "50", "actual": str(status)})
        reason = "" if not differences else "配送单详情与配置不一致：" + "、".join(
            f"{row['field']}={row['expected']}→{row['actual']}" for row in differences
        )
        return {
            "key": "porder_config",
            "passed": not differences,
            "reason_code": "" if not differences else "porder_config_mismatch",
            "reason": reason,
            "differences": differences,
            "status": status,
            "status_name": str(detail.get("statusName") or detail.get("status_name") or ""),
        }

    @staticmethod
    def _porder_quote_chain_check(
        payment_row: Mapping[str, Any] | None,
        porder_detail: Mapping[str, Any],
        ledger_jpy_text: str,
        voucher_jpy: Decimal,
        predicted_quote: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        missing: list[str] = []
        row = _mapping(payment_row)
        quote = _mapping(predicted_quote)
        captured = bool(row.get("captured_before_payment") or quote.get("captured_before_payment"))
        currency = str(row.get("expected_currency") or quote.get("currency") or "").upper()
        amount = row.get("expected_amount")
        if amount in (None, ""):
            amount = quote.get("amount")
        source = str(row.get("expected_source") or quote.get("source") or "")
        predicted_cny_text = ""
        if source != "porder_pay_detail" or currency != "CNY" or amount in (None, "") or not captured:
            missing.append("predicted_quote_cny")
        else:
            predicted_cny_text = _money_value(amount)
        logistics_cny = Decimal(_money_value(porder_detail.get("logistics_price")))
        extra_cny = Decimal(_money_value(porder_detail.get("other_price")))
        detail_cny = logistics_cny + extra_cny
        exchange_rate = Decimal(str(porder_detail.get("exchange_rate") or row.get("exchange_rate") or 0))
        payment_jpy_text = str(row.get("actual_jpy") or "")
        if not payment_jpy_text:
            missing.append("payment_jpy")
        if not ledger_jpy_text:
            missing.append("customer_balance")
        if exchange_rate <= 0:
            missing.append("exchange_rate")
        if detail_cny <= 0:
            missing.append("porder_detail_cny")
        reason_code = ""
        reason = ""
        passed = not missing
        if missing:
            reason_code = "evidence_incomplete"
            reason = "配送独立报价链证据不完整：" + "、".join(missing)
        elif abs(Decimal(predicted_cny_text) - detail_cny) > Decimal("0.05"):
            passed = False
            reason_code = "porder_quote_chain_mismatch"
            reason = f"支付前报价 {predicted_cny_text} CNY 与配送详情 {format(detail_cny, 'f')} CNY 不一致"
        else:
            predicted_jpy = (Decimal(predicted_cny_text) * exchange_rate).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
            net_jpy = max(Decimal("0"), predicted_jpy - voucher_jpy)
            payment_jpy = Decimal(payment_jpy_text)
            ledger_jpy = Decimal(ledger_jpy_text)
            if abs(net_jpy - payment_jpy) > Decimal("1") or abs(net_jpy - ledger_jpy) > Decimal("1"):
                passed = False
                reason_code = "porder_quote_chain_mismatch"
                reason = (
                    f"报价链不一致：预测 {predicted_cny_text} CNY → {format(net_jpy, 'f')} JPY，"
                    f"支付 {format(payment_jpy, 'f')} JPY，账本 {format(ledger_jpy, 'f')} JPY"
                )
        return {
            "key": "porder_quote_chain",
            "passed": passed,
            "reason_code": reason_code,
            "reason": reason,
            "missing": missing,
            "predicted_cny": predicted_cny_text,
            "detail_cny": format(detail_cny, "f") if detail_cny else "",
            "payment_jpy": payment_jpy_text,
            "ledger_jpy": ledger_jpy_text,
            "captured_before_payment": captured,
        }

    @staticmethod
    def _bank_channel_check(
        parameters: Mapping[str, Any],
        checks: list[Mapping[str, Any]],
    ) -> dict[str, Any] | None:
        if str(parameters.get("payment_mode") or "") != "bank":
            return None
        bank_row = next(
            (row for row in checks if str(row.get("actual_source") or "") == "finance_confirmed_bill"),
            None,
        )
        passed = bank_row is not None
        return {
            "key": "bank_channel",
            "passed": passed,
            "reason_code": "" if passed else "bank_channel_missing",
            "reason": "" if passed else "银行支付缺少财务确认流水，不能只凭客户余额账本通过",
            "actual_source": str((bank_row or {}).get("actual_source") or ""),
        }

    @staticmethod
    def _order_config_check(
        parameters: Mapping[str, Any],
        detail: Mapping[str, Any],
        *,
        expected_status: int,
        allowed_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        root = _mapping(detail.get("data")) or dict(detail)
        actual_rows = next(
            (
                [dict(row) for row in root.get(key) or [] if isinstance(row, Mapping)]
                for key in ("list", "order_detail", "order_details", "details", "items")
                if isinstance(root.get(key), list)
            ),
            [],
        )
        order = _mapping(parameters.get("order"))
        configured_rows = [dict(row) for row in parameters.get("items") or [] if isinstance(row, Mapping)]
        if not configured_rows:
            item_count = int(order.get("item_count") or parameters.get("item_count") or 1)
            configured_rows = [
                {
                    "sorting": index + 1,
                    "quantity": int(order.get("default_quantity") or parameters.get("item_quantity") or 1),
                    "offer_price": order.get("default_offer_price") or parameters.get("offer_price") or "10",
                    "offer_freight": order.get("default_freight") or parameters.get("offer_freight") or "3",
                    "options": [],
                }
                for index in range(item_count)
            ]
        expected_by_sorting = {
            str(row.get("sorting") or index): row for index, row in enumerate(configured_rows, 1)
        }
        actual_by_sorting = {
            str(row.get("sorting") or index): row for index, row in enumerate(actual_rows, 1)
        }
        differences: list[dict[str, str]] = []

        def add(field: str, expected: Any, actual: Any) -> None:
            differences.append({"field": field, "expected": str(expected), "actual": str(actual)})

        if set(expected_by_sorting) != set(actual_by_sorting):
            add("sortings", sorted(expected_by_sorting), sorted(actual_by_sorting))
        for sorting, expected in expected_by_sorting.items():
            actual = actual_by_sorting.get(sorting)
            if actual is None:
                continue
            expected_quantity = int(expected.get("quantity") or order.get("default_quantity") or 1)
            actual_quantity = int(actual.get("confirm_num") or actual.get("offer_num") or actual.get("num") or 0)
            if expected_quantity != actual_quantity:
                add(f"sorting:{sorting}.quantity", expected_quantity, actual_quantity)
            expected_price = Decimal(_money_value(expected.get("offer_price") or order.get("default_offer_price") or 0))
            actual_price = Decimal(_money_value(actual.get("confirm_price") or actual.get("offer_price") or actual.get("price") or 0))
            if expected_price != actual_price:
                add(f"sorting:{sorting}.price", expected_price, actual_price)
            expected_freight = Decimal(_money_value(expected.get("offer_freight") or order.get("default_freight") or 0))
            actual_freight = Decimal(_money_value(actual.get("confirm_freight") or actual.get("offer_freight") or actual.get("freight") or 0))
            if expected_freight != actual_freight:
                add(f"sorting:{sorting}.freight", expected_freight, actual_freight)
            expected_options = {
                str(row.get("id") or row.get("option_id") or row.get("key") or ""): int(
                    row.get("num") or row.get("quantity") or 0
                )
                for row in expected.get("options") or []
                if isinstance(row, Mapping) and row.get("checked") is not False
            }
            actual_options = {
                str(row.get("id") or row.get("option_id") or row.get("key") or ""): int(
                    row.get("num") or row.get("quantity") or 0
                )
                for row in actual.get("option") or actual.get("options") or []
                if isinstance(row, Mapping) and row.get("checked") is not False
            }
            if expected_options != actual_options:
                add(f"sorting:{sorting}.options", expected_options, actual_options)
        status = int(root.get("status") or 0)
        allowed = allowed_statuses or {expected_status}
        if status not in allowed:
            add("status", ",".join(str(value) for value in sorted(allowed)), status)
        reason = "" if not differences else "订单详情与配置不一致：" + "、".join(
            f"{row['field']}={row['expected']}→{row['actual']}" for row in differences
        )
        return {
            "key": "order_config",
            "passed": not differences,
            "reason_code": "" if not differences else "order_config_mismatch",
            "reason": reason,
            "differences": differences,
            "status": status,
            "status_name": str(root.get("statusName") or root.get("status_name") or ""),
            "detail_count": len(actual_rows),
        }

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
        configured_options = [
            dict(option)
            for item in parameters.get("items") or []
            if isinstance(item, Mapping)
            for option in item.get("options") or []
            if isinstance(option, Mapping) and option.get("checked") is not False
        ]

        def configured_option(price_type: int) -> dict[str, Any] | None:
            wanted = next(
                (row for row in configured_options if int(row.get("price_type") or 0) == price_type),
                None,
            )
            if wanted is None:
                return next(
                    (row for row in options if int(row.get("price_type") or 0) == price_type and row.get("id") not in (None, "")),
                    None,
                )
            wanted_id = str(wanted.get("id") or wanted.get("option_id") or wanted.get("key") or "")
            matched = next((row for row in options if str(row.get("id") or row.get("key") or "") == wanted_id), None)
            if matched is None:
                raise RuntimeError(f"配置 OPTION {wanted_id} 不在当前真实目录中")
            return {**matched, "configured_num": wanted.get("num") or wanted.get("quantity")}

        fixed = configured_option(0)
        rate = configured_option(1)
        if fixed is None or rate is None:
            raise RuntimeError("缺少可通过 option_id 识别的固定金额或百分比 OPTION")
        goods_unit_price = Decimal(str(parameters.get("offer_price") or parameters.get("payment_regression_offer_price") or "10"))
        counts: dict[str, int] = {}
        required: list[FeeComponent] = []
        for row in (fixed, rate):
            quantity = max(1, int(row.get("configured_num") or parameters.get("option_quantity") or 2))
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
            # 造单必须严格遵循页面配置；不能用通用默认值把 1 番改成 2 番。
            # 未配置时才回退到已有变量/单价列表，最终至少执行 1 番。
            configured_prices = parameters.get("offer_unit_prices") or variables.get("offer_unit_prices") or []
            item_count = max(
                1,
                int(
                    parameters.get("item_count")
                    or variables.get("order_item_count")
                    or len(configured_prices)
                    or 1
                ),
            )
            item_quantity = max(1, int(parameters.get("item_quantity") or variables.get("order_item_num") or 1))
            unit_prices = [
                str(value)
                for value in parameters.get("offer_unit_prices") or ["10"] * item_count
            ][:item_count]
            freight_each = _money_value(parameters.get("offer_freight") or variables.get("offer_freight") or 5)
            configured_freights = parameters.get("offer_freights") or variables.get("offer_freights") or []
            freights = [str(value) for value in configured_freights][:item_count] or [freight_each] * item_count
            if len(unit_prices) != item_count or len(freights) != item_count:
                raise ValueError("全费用场景的商品单价和单番国内运费数量必须与番号数一致")
            variables["cart_item_count"] = item_count
            variables["order_item_count"] = item_count
            variables["order_item_num"] = item_quantity
            variables["offer_unit_prices"] = unit_prices
            variables["offer_freights"] = freights
            variables["confirm_freights"] = list(freights)
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
        order_detail: dict[str, Any] = {}
        if category in {"order", "order_part"}:
            order_sn = str(payload.get("order_sn") or "")
            if not order_sn:
                checks.append(
                    {
                        "key": "order_config",
                        "passed": False,
                        "reason_code": "evidence_incomplete",
                        "reason": "订单支付成功但未返回 order_sn，无法核验订单详情和状态",
                    }
                )
            else:
                loader = self.order_evidence_loader
                if loader is None and getattr(self.env, "base_url", None):
                    loader = self._load_order_evidence
                if loader is not None:
                    try:
                        order_detail = dict(loader(self.env, variables, order_sn) or {})
                    except Exception as exc:
                        checks.append(
                            {
                                "key": "order_config",
                                "passed": False,
                                "reason_code": "evidence_incomplete",
                                "reason": f"订单详情反查失败：{exc}",
                            }
                        )
                    else:
                        expected_status = 70 if category == "order_part" else 50
                        allowed_statuses = {expected_status}
                        if category == "order_part" and part_pay.get("tail_partial"):
                            allowed_statuses.add(60)
                        order_check = self._order_config_check(
                            parameters,
                            order_detail,
                            expected_status=expected_status,
                            allowed_statuses=allowed_statuses,
                        )
                        checks.append(order_check)
                        payload["order_evidence"] = {
                            "order_sn": order_sn,
                            "status": order_check["status"],
                            "status_name": order_check["status_name"],
                            "detail_count": order_check["detail_count"],
                        }
            payload["checks"] = checks
        configured_expected_jpy = _configured_order_expected_jpy(parameters, membership) if category == "order" else None
        if configured_expected_jpy is not None:
            ticket_discount_jpy = Decimal(str(parameters.get("payment_regression_discount_jpy") or 0))
            gross_parameters = dict(parameters)
            gross_parameters["coupon"] = {"selectedId": ""}
            gross_parameters["service_discount"] = False
            gross_parameters["payment_regression_discount_jpy"] = "0"
            configured_gross_jpy = _configured_order_expected_jpy(gross_parameters, membership)
            if configured_gross_jpy is None:
                configured_gross_jpy = configured_expected_jpy + ticket_discount_jpy
            quote_row = next(
                (row for row in checks if str(row.get("expected_source") or "") == "order_quote"),
                None,
            )
            payment_row = next(
                (row for row in checks if str(row.get("actual_source") or "") not in {"", "customer_balance"}),
                None,
            )
            ledger_row = next(
                (row for row in checks if str(row.get("actual_source") or "") == "customer_balance"),
                None,
            )
            if quote_row is not None and payment_row is not None:
                quote_jpy = Decimal(str(quote_row.get("expected_jpy") or 0))
                payment_jpy = Decimal(str(payment_row.get("actual_jpy") or 0))
                ledger_jpy = (
                    Decimal(str(ledger_row.get("actual_jpy") or 0))
                    if ledger_row is not None
                    else None
                )
                differences = [abs(quote_jpy - configured_gross_jpy), abs(payment_jpy - configured_gross_jpy)]
                if ledger_jpy is not None:
                    differences.append(abs(ledger_jpy - configured_expected_jpy))
                configured_passed = all(value <= Decimal("1") for value in differences)
                reason = "" if configured_passed else (
                    f"页面冻结净额 {configured_expected_jpy} 日元（支付毛额 {configured_gross_jpy} 日元），订单报价 {quote_jpy} 日元，"
                    f"支付接口 {payment_jpy} 日元"
                    + (f"，客户出入金 {ledger_jpy} 日元" if ledger_jpy is not None else "")
                    + "，金额不一致"
                )
                checks.append(
                    {
                        "key": "configured_amount",
                        "passed": configured_passed,
                        "reason_code": "" if configured_passed else "configured_amount_mismatch",
                        "reason": reason,
                        "expected_jpy": str(configured_expected_jpy),
                        "expected_gross_jpy": str(configured_gross_jpy),
                        "order_quote_jpy": str(quote_jpy),
                        "payment_actual_jpy": str(payment_jpy),
                        "customer_balance_jpy": str(ledger_jpy) if ledger_jpy is not None else "",
                    }
                )
                payload["checks"] = checks
                payload["configured_expected_jpy"] = str(configured_expected_jpy)
                payload["configured_gross_jpy"] = str(configured_gross_jpy)
                payload["order_quote_jpy"] = str(quote_jpy)
                payload["payment_actual_jpy"] = str(payment_jpy)
                payload["configured_amount_difference_jpy"] = str(max(differences))
        fee_check = None
        if fee_contract is not None:
            if not isinstance(payload.get("fee_components"), list):
                payload["fee_components"] = (
                    [self._component_dict(component) for component in extract_order_fee_components(order_detail)]
                    if order_detail
                    else list(
                        self.fee_evidence_loader(
                            self.env,
                            variables,
                            str(payload.get("order_sn") or ""),
                        )
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
        if category == "porder" and not str(payload.get("porder_sn") or ""):
            checks.append(
                {
                    "key": "porder_config",
                    "passed": False,
                    "reason_code": "evidence_incomplete",
                    "reason": "配送单支付成功但未返回 porder_sn，无法核验配送详情和状态",
                }
            )
            payload["checks"] = checks
        elif category == "porder":
            porder_detail = dict(
                self.porder_evidence_loader(
                    self.env,
                    variables,
                    str(payload.get("porder_sn") or ""),
                ) or {}
            )
            porder_check = self._porder_config_check(parameters, porder_detail)
            checks.append(porder_check)
            configured_porder = _mapping(parameters.get("porder"))
            exchange_rate = Decimal(str(porder_detail.get("exchange_rate") or 0))
            ledger_check = _mapping(payload.get("ledger_check"))
            ledger_jpy_text = str(ledger_check.get("customer_balance_jpy") or "")
            if not ledger_jpy_text:
                ledger_row = next(
                    (row for row in checks if str(row.get("actual_source") or "") == "customer_balance"),
                    None,
                )
                ledger_jpy_text = str((ledger_row or {}).get("actual_jpy") or "")
            payment_row = next(
                (
                    row
                    for row in checks
                    if str(row.get("expected_source") or "")
                    and str(row.get("actual_source") or "") not in {"", "customer_balance"}
                ),
                None,
            )
            missing_evidence: list[str] = []
            if not _money_value(porder_detail.get("logistics_price")) or Decimal(
                _money_value(porder_detail.get("logistics_price"))
            ) <= 0:
                missing_evidence.append("porder_detail")
            if exchange_rate <= 0:
                missing_evidence.append("exchange_rate")
            if payment_row is None:
                missing_evidence.extend(["porder_quote", "payment_actual"])
            if not ledger_jpy_text:
                missing_evidence.append("customer_balance")
            voucher_jpy = Decimal(str(variables.get("payment_regression_voucher_jpy") or 0))
            checks.append(
                {
                    "key": "porder_amount_evidence",
                    "passed": not missing_evidence,
                    "reason_code": "" if not missing_evidence else "evidence_incomplete",
                    "reason": "" if not missing_evidence else (
                        "配送金额证据不完整：" + "、".join(missing_evidence)
                    ),
                    "missing": missing_evidence,
                }
            )
            if not missing_evidence:
                logistics_cny = Decimal(
                    _money_value(
                        configured_porder.get("logistics_price")
                        if configured_porder.get("price_manual")
                        else porder_detail.get("logistics_price")
                    )
                )
                extra_cny = Decimal(_money_value(configured_porder.get("extra_fee")))
                configured_jpy = max(
                    Decimal("0"),
                    ((logistics_cny + extra_cny) * exchange_rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                    - voucher_jpy,
                )
                ledger_jpy = Decimal(ledger_jpy_text)
                amount_passed = abs(configured_jpy - ledger_jpy) <= Decimal("1")
                checks.append(
                    {
                        "key": "configured_amount",
                        "passed": amount_passed,
                        "reason_code": "" if amount_passed else "configured_amount_mismatch",
                        "reason": "" if amount_passed else (
                            f"配送配置应扣 {configured_jpy} 日元，客户实际出入金 {ledger_jpy} 日元，金额不一致"
                        ),
                        "expected_jpy": str(configured_jpy),
                        "customer_balance_jpy": str(ledger_jpy),
                    }
                )
            payload["checks"] = checks
            payload["porder_evidence"] = {
                "porder_sn": str(porder_detail.get("porder_sn") or ""),
                "logistics_id": str(_mapping(porder_detail.get("logistics")).get("id") or ""),
                "logistics_name": str(_mapping(porder_detail.get("logistics")).get("name") or ""),
                "logistics_price": _money_value(porder_detail.get("logistics_price")),
                "other_price": _money_value(porder_detail.get("other_price")),
                "status": porder_check["status"],
                "status_name": porder_check["status_name"],
            }
            checks.append(
                self._porder_quote_chain_check(
                    payment_row,
                    porder_detail,
                    ledger_jpy_text,
                    voucher_jpy,
                    payload.get("predicted_quote") if isinstance(payload.get("predicted_quote"), Mapping) else None,
                )
            )
            payload["checks"] = checks
        bank_check = self._bank_channel_check(parameters, checks)
        if bank_check is not None:
            checks.append(bank_check)
            payload["checks"] = checks
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
