from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.services.system_regression.account_service import AccountLoginRequired
from app.system_regression.projects.japan import problem_runner as problem_runner_module
from app.system_regression.projects.japan.guard_runner import GuardRunner
from app.data_scripts.payment_amount_regression.runner import ScenarioBlocked
from app.data_scripts.porder_flow_support import (
    _extract_predicted_price,
    _logistics_ids_from_freight,
    _select_porder_logistics,
)
from app.system_regression.projects.japan.payment_runner import PaymentRunner, build_payment_variables
from app.system_regression.projects.japan.problem_runner import (
    ProblemGoodsRunner,
    build_problem_goods_request,
)
from app.system_regression.projects.japan.runner import JapanRegressionRunner


def _case(
    *,
    key: str,
    runner_kind: str,
    parameters: dict,
    direction: str = "debit",
    expectation: dict | None = None,
) -> dict:
    return {
        "case_key": key,
        "name": key,
        "runner_kind": runner_kind,
        "parameters": parameters,
        "expectation": expectation or {"outcome": "success", "direction": direction},
    }


def test_build_payment_variables_maps_all_editable_fee_fields_without_actual_evidence():
    values = build_payment_variables(
        {
            "payment_mode": "balance",
            "actual_amount": "999999",
            "actual_evidence": {"source": "request"},
            "order": {
                "item_count": 2,
                "default_quantity": 3,
                "other_fee_name": "加固包装费",
                "other_fee_amount": {"value": "5.5", "currency": "CNY"},
            },
            "items": [
                {
                    "sorting": 1,
                    "quantity": 2,
                    "offer_price": {"value": "12", "currency": "CNY"},
                    "offer_freight": {"value": "3", "currency": "CNY"},
                    "options": [{"name": "验品", "price_type": 0, "price": "2", "num": 2}],
                },
                {
                    "sorting": 2,
                    "quantity": 1,
                    "offer_price": {"value": "20", "currency": "CNY"},
                    "offer_freight": {"value": "4", "currency": "CNY"},
                    "options": [{"name": "拍照", "price_type": 1, "price": "5", "num": 1}],
                },
            ],
        }
    )

    assert values["cart_item_count"] == 2
    assert values["order_item_num"] == 3
    assert values["other_price"] == "5.5"
    assert values["other_price_remark"] == "加固包装费"
    assert values["offer_unit_prices"] == ["12", "20"]
    assert values["offer_freights"] == ["3", "4"]
    assert values["order_option_counts"] == {"验品": 2, "拍照": 1}
    assert "actual_amount" not in values
    assert "actual_evidence" not in values
    assert "japan_fixed_cny_to_jpy" not in values
    assert values["compare_actual_from_balance_change"] is True
    assert values["compare_ledger_after_payment"] is True


def test_build_payment_variables_maps_part_pay_coupon_and_porder_boxes():
    values = build_payment_variables(
        {
            "part_pay": {"enabled": True, "percent": 0, "tail_node": "before_porder_create", "tail_partial": True, "tail_sortings": "1,2"},
            "coupon": {"selectedId": "__service_discount__"},
            "porder": {
                "sku_count": 2,
                "box_count": 1,
                "box_length": 58,
                "box_width": 51,
                "box_height": 50,
                "box_weight": 10,
                "logistics": "25",
                "price_manual": False,
                "voucher": {"selectedId": "VOUCHER-9"},
            },
            "ledger_wait_seconds": 12,
        }
    )

    assert values["order_part_pay"] == 1
    assert values["_full_flow_part_pay_script"] is True
    assert values["order_part_pay_percent"] == 0
    assert values["first_payment_rate"] == "0.00"
    assert values["service_discount"] is True
    assert "discounts_id" in values
    assert values["discounts_id"] == "VOUCHER-9"
    assert values["logistics_price_from_api"] is True
    assert values["box_length"] == "58"
    assert values["delivery_quote_logistics_id"] == "25"
    assert values["ledger_wait_seconds"] == 12
    assert values["payment_regression_evidence_delay"] == 0.5
    assert values["payment_regression_evidence_retries"] == 24


def test_sea_logistics_ids_are_read_from_nested_freight_groups():
    ids = _logistics_ids_from_freight(
        {
            "success": True,
            "data": [
                {
                    "group": [
                        {"logistics_id": "15", "name": "航空便"},
                        {"logistics_id": "31", "name": "船便", "list": [{"id": 10, "logistics_id": "31"}]},
                    ]
                }
            ],
        },
        "20",
    )

    assert ids[0] == "31"
    assert "20" in ids
    assert "15" not in ids


def test_select_porder_logistics_retries_sea_id_from_refreshed_freight_list(monkeypatch):
    import app.data_scripts.porder_flow_support as flow

    calls = []

    def fake_post(_session, _base_url, path, fields, _timeout):
        calls.append((path, dict(fields)))
        if path.endswith("freightList"):
            return {
                "success": True,
                "code": 0,
                "data": [{"group": [{"logistics_id": "31", "name": "船便"}, {"logistics_id": "15", "name": "航空便"}]}],
            }
        if str(fields.get("logistics_id")) == "31":
            return {"success": True, "code": 0, "msg": "操作成功"}
        return {"success": False, "code": 10000, "msg": "物流不可用"}

    monkeypatch.setattr(flow, "_sync_compat_globals", lambda: None, raising=False)
    monkeypatch.setattr(flow, "_post_admin_urlencoded", fake_post, raising=False)
    monkeypatch.setattr(flow, "_api_path", lambda _variables, _key, default: default, raising=False)
    monkeypatch.setattr(flow, "_api_success", lambda payload: bool(payload.get("success")), raising=False)
    monkeypatch.setattr(flow, "_payload_brief", lambda payload: dict(payload or {}), raising=False)
    monkeypatch.setattr(flow, "_payload_structure_sample", lambda payload, limit=4: payload, raising=False)

    log = {}
    selected, payload = _select_porder_logistics(
        object(),
        "http://example",
        {},
        "P1",
        "F1",
        "20",
        [{"success": True, "data": []}],
        10,
        log,
    )

    assert selected == "31"
    assert payload.get("success") is True
    assert [fields.get("logistics_id") for path, fields in calls if path.endswith("batchUpdateFreightLogistics")] == ["31"]


def test_select_porder_logistics_uses_user_logistics_list_when_requested_sea_id_unavailable(monkeypatch):
    import app.data_scripts.porder_flow_support as flow

    calls = []

    def fake_post(_session, _base_url, path, fields, _timeout):
        calls.append((path, dict(fields)))
        if path.endswith("logistics.list") or path.endswith("logisticsList"):
            return {
                "success": True,
                "code": 0,
                "data": [
                    {"id": 25, "name": "KS-JP電子特殊便"},
                    {"id": 29, "name": "海源電子特殊航空便"},
                    {"id": 20, "name": "RW船便"},
                    {"id": 30, "name": "Rロジ専用船便"},
                ],
            }
        if str(fields.get("logistics_id")) == "30":
            return {"success": True, "code": 0, "msg": "操作成功"}
        return {"success": False, "code": 10000, "msg": "当前发送方式不可用"}

    monkeypatch.setattr(flow, "_sync_compat_globals", lambda: None, raising=False)
    monkeypatch.setattr(flow, "_post_admin_urlencoded", fake_post, raising=False)
    monkeypatch.setattr(flow, "_api_path", lambda _variables, _key, default: default, raising=False)
    monkeypatch.setattr(flow, "_api_success", lambda payload: bool(payload.get("success")), raising=False)
    monkeypatch.setattr(flow, "_payload_brief", lambda payload: dict(payload or {}), raising=False)
    monkeypatch.setattr(flow, "_payload_structure_sample", lambda payload, limit=4: payload, raising=False)

    selected, payload = _select_porder_logistics(
        object(),
        "http://example",
        {"customer_id": "300001"},
        "P1",
        "F1",
        "20",
        [{"success": True, "data": []}],
        10,
        {},
    )

    assert selected == "30"
    assert payload.get("success") is True
    attempted = [fields.get("logistics_id") for path, fields in calls if path.endswith("batchUpdateFreightLogistics")]
    assert "30" in attempted
    assert "29" not in attempted
    assert any(path.endswith("logistics.list") or path.endswith("logisticsList") for path, _fields in calls)


def test_sea_logistics_ids_ignore_haiyuan_air_names():
    ids = _logistics_ids_from_freight(
        {
            "success": True,
            "data": [
                {"id": 29, "name": "海源電子特殊航空便"},
                {"id": 9, "name": "海源航空便"},
                {"id": 20, "name": "RW船便"},
                {"id": 30, "name": "Rロジ専用船便"},
            ],
        },
        "20",
    )

    assert ids[0] == "20"
    assert "30" in ids
    assert "29" not in ids
    assert "9" not in ids


def test_build_payment_variables_keeps_real_coupon_id_and_manual_freight():
    coupon_only = build_payment_variables({"coupon": {"selectedId": "COUPON-3"}})
    assert coupon_only["service_discount"] is True
    assert coupon_only["discounts_id"] == "COUPON-3"

    manual = build_payment_variables(
        {"porder": {"price_manual": True, "logistics_price": {"value": "88", "currency": "CNY"}}}
    )
    assert manual["logistics_price_from_api"] is False
    assert manual["logistics_price_artificial"] == "88"


def test_build_payment_variables_does_not_send_account_ticket_sentinels():
    from app.system_regression.projects.japan.panel import ACCOUNT_COUPON_ID, ACCOUNT_VOUCHER_ID

    coupon = build_payment_variables({"coupon": {"selectedId": ACCOUNT_COUPON_ID}})
    assert coupon["service_discount"] is True
    assert "discounts_id" not in coupon

    voucher = build_payment_variables(
        {"porder": {"voucher": {"selectedId": ACCOUNT_VOUCHER_ID}, "logistics": "25"}},
        runner_kind="porder_payment",
    )
    assert "discounts_id" not in voucher
    assert "porder_discounts_id" not in voucher


def test_build_payment_variables_keeps_porder_voucher_off_order_discounts_id():
    values = build_payment_variables(
        {"porder": {"voucher": {"selectedId": "V25"}, "logistics": "25"}, "discounts_id": "V25"},
        runner_kind="porder_payment",
    )
    assert "discounts_id" not in values
    assert values["porder_discounts_id"] == "V25"


def test_bind_account_tickets_replaces_coupon_sentinel(monkeypatch):
    from app.system_regression.projects.japan.panel import ACCOUNT_COUPON_ID
    from app.system_regression.projects.japan.payment_runner import bind_account_tickets

    monkeypatch.setattr(
        "app.system_regression.projects.japan.payment_runner.list_usable_tickets",
        lambda _env, _variables: {
            "coupons": [{"id": "C1", "title": "手续费免费"}],
            "vouchers": [],
            "reason": "",
        },
    )
    bound = bind_account_tickets(
        object(),
        {"coupon": {"selectedId": ACCOUNT_COUPON_ID}},
        {"account": "a", "password": "b"},
        runner_kind="order_payment",
    )
    assert bound["coupon"]["selectedId"] == "C1"
    assert bound["discounts_id"] == "C1"
    assert bound["service_discount"] is True


def test_bind_account_tickets_blocks_when_account_has_no_coupon(monkeypatch):
    from app.system_regression.projects.japan.panel import ACCOUNT_COUPON_ID
    from app.system_regression.projects.japan.payment_runner import bind_account_tickets

    monkeypatch.setattr(
        "app.system_regression.projects.japan.payment_runner.list_usable_tickets",
        lambda _env, _variables: {"coupons": [], "vouchers": [], "reason": "这个账号没有可用订单优惠券"},
    )
    with pytest.raises(ScenarioBlocked) as exc:
        bind_account_tickets(
            object(),
            {"coupon": {"selectedId": ACCOUNT_COUPON_ID}},
            {},
            runner_kind="order_payment",
        )
    assert exc.value.reason_code == "missing_coupon"


def test_bind_account_tickets_picks_matching_voucher_and_logistics(monkeypatch):
    from app.system_regression.projects.japan.panel import ACCOUNT_VOUCHER_ID
    from app.system_regression.projects.japan.payment_runner import bind_account_tickets

    monkeypatch.setattr(
        "app.system_regression.projects.japan.payment_runner.list_usable_tickets",
        lambda _env, _variables: {
            "coupons": [],
            "vouchers": [
                {"id": "V20", "title": "船便券", "kind": "logistics", "amount": "800", "logistics_id": "20"},
                {"id": "V25", "title": "空运券", "kind": "logistics", "amount": "1500", "logistics_id": "25"},
            ],
            "reason": "",
        },
    )
    bound = bind_account_tickets(
        object(),
        {"porder": {"logistics": "25", "voucher": {"selectedId": ACCOUNT_VOUCHER_ID}}},
        {},
        runner_kind="porder_payment",
    )
    assert bound["porder"]["voucher"]["selectedId"] == "V25"
    assert bound["porder"]["logistics"] == "25"
    assert bound["porder_discounts_id"] == "V25"
    assert "discounts_id" not in bound
    assert bound["payment_regression_voucher_jpy"] == "1500"


def test_payment_runner_execute_binds_account_coupon_into_discounts_id(monkeypatch):
    from app.system_regression.projects.japan.panel import ACCOUNT_COUPON_ID

    captured = {}

    class FakeExecutor:
        def __init__(self, variables):
            captured.update(variables)

        def execute(self, _scenario, _batch_no):
            return {"status": "passed", "order_sn": "O1", "checks": [{"passed": True}]}

    monkeypatch.setattr(
        "app.system_regression.projects.japan.payment_runner.list_usable_tickets",
        lambda _env, _variables: {
            "coupons": [{"id": "C9", "title": "手续费免费"}],
            "vouchers": [],
            "reason": "",
        },
    )
    runner = PaymentRunner(env=object(), executor_factory=lambda _env, variables: FakeExecutor(variables))
    result = runner.execute(
        _case(
            key="支付-016",
            runner_kind="order_payment",
            parameters={"payment_mode": "balance", "coupon": {"selectedId": ACCOUNT_COUPON_ID}},
        ),
        {"batch_no": "B1", "variables": {}},
    )
    assert result.status == "passed"
    assert captured["discounts_id"] == "C9"
    assert result.result["used_ticket"]["discounts_id"] == "C9"


def test_payment_runner_porder_voucher_does_not_put_discounts_id_on_order_pay(monkeypatch):
    from app.system_regression.projects.japan.panel import ACCOUNT_VOUCHER_ID

    captured = {}

    class FakeExecutor:
        def __init__(self, variables):
            captured.update(variables)

        def execute(self, _scenario, _batch_no):
            return {"status": "passed", "porder_sn": "P1", "checks": [{"passed": True}]}

    monkeypatch.setattr(
        "app.system_regression.projects.japan.payment_runner.list_usable_tickets",
        lambda _env, _variables: {
            "coupons": [],
            "vouchers": [{"id": "V25", "title": "空运券", "kind": "logistics", "amount": "1500", "logistics_id": "25"}],
            "reason": "",
        },
    )
    runner = PaymentRunner(env=object(), executor_factory=lambda _env, variables: FakeExecutor(variables))
    result = runner.execute(
        _case(
            key="配送-006",
            runner_kind="porder_payment",
            parameters={
                "payment_mode": "balance",
                "porder": {"logistics": "25", "voucher": {"selectedId": ACCOUNT_VOUCHER_ID}},
            },
        ),
        {"batch_no": "B1", "variables": {}},
    )
    assert result.status == "passed"
    assert "discounts_id" not in captured
    assert captured["porder_discounts_id"] == "V25"
    assert result.result["used_ticket"]["discounts_id"] == "V25"
    assert result.result["used_ticket"]["voucher_jpy"] == "1500"


def test_payment_runner_execute_blocks_when_account_coupon_missing(monkeypatch):
    from app.system_regression.projects.japan.panel import ACCOUNT_COUPON_ID

    monkeypatch.setattr(
        "app.system_regression.projects.japan.payment_runner.list_usable_tickets",
        lambda _env, _variables: {"coupons": [], "vouchers": [], "reason": "没券"},
    )
    runner = PaymentRunner(
        env=object(),
        executor_factory=lambda _env, _variables: (_ for _ in ()).throw(AssertionError("不应执行支付")),
    )
    result = runner.execute(
        _case(
            key="支付-016",
            runner_kind="order_payment",
            parameters={"payment_mode": "balance", "coupon": {"selectedId": ACCOUNT_COUPON_ID}},
        ),
        {"batch_no": "B1", "variables": {}},
    )
    assert result.status == "blocked"
    assert result.reason_code == "missing_coupon"


def test_build_payment_variables_ignores_porder_block_for_order_cases():
    values = build_payment_variables(
        {"porder": {"logistics": "25", "box_count": 1, "price_manual": False}},
        runner_kind="order_payment",
    )
    assert "logistics_price_from_api" not in values
    assert "delivery_quote_logistics_id" not in values


def test_extract_predicted_logistics_price_from_nested_list():
    assert _extract_predicted_price({"data": {"list": [{"price": "123.45"}]}}) == "123.45"
    assert _extract_predicted_price({"data": {"logistics_price": "88"}}) == "88"


def test_payment_runner_dispatches_all_payment_runner_kinds():
    calls = []

    class FakeExecutor:
        def execute(self, scenario, batch_no):
            calls.append((scenario.category, scenario.payment_mode, batch_no))
            return {"status": "passed", "order_sn": "O1", "checks": [{"passed": True}]}

    runner = PaymentRunner(env=object(), executor_factory=lambda _env, _variables: FakeExecutor())
    contexts = {"batch_no": "B1", "variables": {}}

    assert runner.execute(_case(key="P1", runner_kind="order_payment", parameters={"payment_mode": "balance"}), contexts).status == "passed"
    assert runner.execute(_case(key="P2", runner_kind="order_part_payment", parameters={"payment_mode": "bank"}), contexts).status == "passed"
    assert runner.execute(_case(key="P3", runner_kind="porder_payment", parameters={"payment_mode": "balance"}), contexts).status == "passed"
    assert calls == [("order", "balance", "B1"), ("order_part", "bank", "B1"), ("porder", "balance", "B1")]


def test_payment_runner_uses_part_pay_enabled_to_pick_order_part_category():
    calls = []

    class FakeExecutor:
        def execute(self, scenario, batch_no):
            calls.append(scenario.category)
            return {"status": "passed", "order_sn": "O1", "checks": [{"passed": True}]}

    runner = PaymentRunner(env=object(), executor_factory=lambda _env, _variables: FakeExecutor())
    contexts = {"batch_no": "B1", "variables": {}}

    enabled = runner.execute(
        _case(key="C1", runner_kind="order_payment", parameters={"payment_mode": "balance", "part_pay": {"enabled": True, "percent": 50}}),
        contexts,
    )
    disabled = runner.execute(
        _case(key="C2", runner_kind="order_part_payment", parameters={"payment_mode": "balance", "part_pay": {"enabled": False}}),
        contexts,
    )

    assert enabled.status == "passed"
    assert disabled.status == "passed"
    assert calls == ["order_part", "order"]


def test_payment_runner_fixed_and_rate_profile_selects_real_option_ids():
    captured = {}

    class FakeExecutor:
        def __init__(self, variables):
            captured.update(variables)

        def execute(self, _scenario, _batch_no):
            required = captured["system_regression_fee_contract"]["required_components"]
            return {"status": "passed", "order_sn": "O1", "fee_components": required, "checks": [{"passed": True}]}

    runner = PaymentRunner(
        env=object(),
        option_catalog_loader=lambda _env, _variables: {
            "options": [
                {"id": 7, "key": "fixed-7", "name": "检品", "price_type": 0, "price": "2"},
                {"id": 8, "key": "rate-8", "name": "保险", "price_type": 1, "price": "5"},
            ]
        },
        executor_factory=lambda _env, variables: FakeExecutor(variables),
    )

    result = runner.execute(
        _case(
            key="支付-007",
            runner_kind="order_payment",
            parameters={"payment_mode": "balance", "option_profile": "fixed_and_rate"},
        ),
        {"batch_no": "B1", "variables": {}},
    )

    assert result.status == "passed"
    assert captured["order_option_counts"] == {"fixed-7": 2, "rate-8": 2}
    required = captured["system_regression_fee_contract"]["required_components"]
    assert {(row["kind"], row["option_id"]) for row in required} == {("option_fixed", "7"), ("option_rate", "8")}


def test_payment_runner_rejects_matching_total_when_required_fee_component_is_wrong():
    class FakeExecutor:
        def execute(self, _scenario, _batch_no):
            return {
                "status": "passed",
                "order_sn": "O1",
                "fee_components": [
                    {"kind": "option_fixed", "component_id": "option:7", "option_id": "7", "sorting": "1", "amount_cny": "5.00"},
                    {"kind": "option_rate", "component_id": "option:8", "option_id": "8", "sorting": "1", "amount_cny": "0.00"},
                ],
                "checks": [{"passed": True}],
            }

    runner = PaymentRunner(
        env=object(),
        option_catalog_loader=lambda _env, _variables: {
            "options": [
                {"id": 7, "key": "fixed-7", "name": "检品", "price_type": 0, "price": "2"},
                {"id": 8, "key": "rate-8", "name": "保险", "price_type": 1, "price": "5"},
            ]
        },
        executor_factory=lambda _env, _variables: FakeExecutor(),
    )

    result = runner.execute(
        _case(
            key="支付-007",
            runner_kind="order_payment",
            parameters={"payment_mode": "balance", "option_profile": "fixed_and_rate"},
        ),
        {"batch_no": "B1", "variables": {}},
    )

    assert result.status == "failed"
    assert result.reason_code == "fee_component_amount_mismatch"


def test_payment_runner_loads_fee_evidence_from_order_detail_when_executor_has_no_components():
    calls = []

    class FakeExecutor:
        def execute(self, _scenario, _batch_no):
            return {"status": "passed", "order_sn": "O1", "checks": [{"passed": True}]}

    runner = PaymentRunner(
        env=object(),
        option_catalog_loader=lambda _env, _variables: {
            "options": [
                {"id": 7, "key": "fixed-7", "name": "检品", "price_type": 0, "price": "2"},
                {"id": 8, "key": "rate-8", "name": "保险", "price_type": 1, "price": "5"},
            ]
        },
        fee_evidence_loader=lambda _env, _variables, order_sn: calls.append(order_sn) or [
            {"kind": "option_fixed", "component_id": "option:7", "option_id": "7", "sorting": "1", "amount_cny": "4.00"},
            {"kind": "option_rate", "component_id": "option:8", "option_id": "8", "sorting": "1", "amount_cny": "1.00"},
        ],
        executor_factory=lambda _env, _variables: FakeExecutor(),
    )

    result = runner.execute(
        _case(
            key="支付-007",
            runner_kind="order_payment",
            parameters={"payment_mode": "balance", "option_profile": "fixed_and_rate"},
        ),
        {"batch_no": "B1", "variables": {}},
    )

    assert result.status == "passed"
    assert calls == ["O1"]
    assert len(result.result["fee_components"]) == 2


def test_payment_runner_all_fee_profile_requires_every_requested_component():
    captured = {}

    class FakeExecutor:
        def __init__(self, variables):
            captured.update(variables)

        def execute(self, _scenario, _batch_no):
            return {"status": "passed", "order_sn": "O-ALL", "checks": [{"passed": True}]}

    actual_components = [
        {"kind": "goods", "component_id": "goods:sorting:1", "sorting": "1", "amount_cny": "20.00"},
        {"kind": "goods", "component_id": "goods:sorting:2", "sorting": "2", "amount_cny": "20.00"},
        {"kind": "domestic_freight", "component_id": "freight:sorting:1", "sorting": "1", "amount_cny": "5.00"},
        {"kind": "domestic_freight", "component_id": "freight:sorting:2", "sorting": "2", "amount_cny": "5.00"},
        {"kind": "other_fee", "component_id": "other:系统回归包装费", "amount_cny": "5.00"},
        {"kind": "option_fixed", "component_id": "option:7", "option_id": "7", "amount_cny": "4.00"},
        {"kind": "option_rate", "component_id": "option:8", "option_id": "8", "amount_cny": "1.00"},
    ]
    runner = PaymentRunner(
        env=object(),
        option_catalog_loader=lambda _env, _variables: {
            "options": [
                {"id": 7, "key": "fixed-7", "name": "检品", "price_type": 0, "price": "2"},
                {"id": 8, "key": "rate-8", "name": "保险", "price_type": 1, "price": "5"},
            ]
        },
        fee_evidence_loader=lambda _env, _variables, _order_sn: actual_components,
        executor_factory=lambda _env, variables: FakeExecutor(variables),
    )

    result = runner.execute(
        _case(
            key="支付-008",
            runner_kind="order_payment",
            parameters={"payment_mode": "balance", "fee_profile": "all"},
        ),
        {"batch_no": "B1", "variables": {}},
    )

    assert result.status == "passed"
    assert captured["offer_unit_prices"] == ["10", "10"]
    assert captured["offer_freights"] == ["5", "5"]
    assert captured["offer_freight"] == "5"
    assert captured["other_price"] == "5"
    required = captured["system_regression_fee_contract"]["required_components"]
    assert {row["component_id"] for row in required} == {row["component_id"] for row in actual_components}


def test_problem_goods_request_maps_combination_and_uses_candidate_baseline():
    request = build_problem_goods_request(
        {
            "problem_type": 8,
            "adjustment": "quantity_down_price_up_net_refund",
            "service_deal_suggest": 2,
            "option_deal_suggest": 1,
        },
        {
            "order_purchase_id": 21,
            "order_detail_id": 31,
            "possible_num": 3,
            "confirm_price": "20",
            "confirm_freight": "6",
            "option": [{"name": "验品", "price_type": 0, "price": "2", "num": 3, "checked": True}],
        },
        expected_direction="credit",
        amount_step=Decimal("2"),
    )

    assert request["order_purchase_id"] == 21
    assert request["order_detail_id"] == 31
    assert request["problem_type"] == 8
    assert request["pre_num"] == 2
    assert Decimal(request["pre_price"]) > Decimal("20")
    assert request["service_deal_suggest"] == 2
    assert request["option_deal_suggest"] == 1
    assert request["business_decision"] == "系统回归自动处理"
    assert request["problem_description"] == "系统回归问题产品"
    assert request["translation_content"] == "システム回帰テスト"
    assert request["refund_channel"] == "customer_balance"


def test_problem_goods_request_ignores_stale_structured_pre_baseline():
    request = build_problem_goods_request(
        {
            "problem_type": 1,
            "problem_goods": {"pre_num": 2, "pre_price": {"value": "8"}, "pre_freight": {"value": "1"}},
        },
        {
            "order_purchase_id": 21,
            "order_detail_id": 31,
            "possible_num": 3,
            "confirm_price": "10",
            "confirm_freight": "3",
            "option": [],
        },
        expected_direction="debit",
    )

    assert request["pre_num"] == 3
    assert request["pre_price"] == "10"
    assert request["pre_freight"] == "3"


def test_problem_goods_request_preserves_custom_business_text():
    request = build_problem_goods_request(
        {"problem_goods": {
            "business_decision": "金额回归人工备注",
            "problem_description": "少货一件",
            "translation_content": "商品が1点不足しています",
        }},
        {
            "order_purchase_id": 21,
            "order_detail_id": 31,
            "possible_num": 3,
            "confirm_price": "20",
            "confirm_freight": "6",
        },
        expected_direction="credit",
    )

    assert request["business_decision"] == "金额回归人工备注"
    assert request["problem_description"] == "少货一件"
    assert request["translation_content"] == "商品が1点不足しています"


@pytest.mark.parametrize("adjustment", ["fixed_add", "rate_add"])
def test_problem_goods_request_new_option_includes_translated_name(adjustment):
    request = build_problem_goods_request(
        {"option_adjustment": adjustment, "option_deal_suggest": 1},
        {
            "order_purchase_id": 21,
            "order_detail_id": 31,
            "possible_num": 3,
            "confirm_price": "20",
            "confirm_freight": "6",
            "option": [],
        },
        expected_direction="debit",
    )

    assert request["option_new"][0]["name_translate"] == "システム回帰OPTION"


def test_auto_rate_price_down_changes_goods_price_for_option_linkage():
    request = build_problem_goods_request(
        {"option_adjustment": "rate_price_down", "option_deal_suggest": 2},
        {
            "order_purchase_id": 21,
            "order_detail_id": 31,
            "possible_num": 3,
            "confirm_price": "20",
            "confirm_freight": "6",
            "option": [{"name": "检品", "price_type": 1, "price": "4", "num": 3}],
        },
        expected_direction="credit",
        amount_step=Decimal("2"),
    )

    assert request["pre_price"] == "18"
    assert "option_new" not in request


def test_empty_nested_option_new_does_not_block_option_adjustment():
    request = build_problem_goods_request(
        {
            "option_adjustment": "fixed_add",
            "option_deal_suggest": 1,
            "problem_goods": {"option_new": [], "option_deal_suggest": 2},
        },
        {
            "order_purchase_id": 21,
            "order_detail_id": 31,
            "possible_num": 3,
            "confirm_price": "20",
            "confirm_freight": "6",
            "option": [],
        },
        expected_direction="debit",
    )

    assert request["option_deal_suggest"] == 1
    assert request["option_new"]
    assert request["option_new"][0]["name"]


def test_problem_runner_rejects_non_balance_actual_evidence():
    def gateway(_case, _context, _request):
        return {
            "status": "passed",
            "order_sn": "O1",
            "problem_goods_id": "PG1",
            "expected": {"amount": "10", "currency": "JPY", "direction": "credit", "source": "calculator"},
            "preview": {"amount": "10", "currency": "JPY", "direction": "credit", "source": "preview"},
            "actual": {"amount": "10", "currency": "JPY", "direction": "credit", "source": "bank"},
        }

    runner = ProblemGoodsRunner(env=object(), live_gateway=gateway)
    result = runner.execute(
        _case(key="PG", runner_kind="problem_goods", parameters={"problem_type": 1, "adjustment": "price_down"}, direction="credit"),
        {"candidate": {"order_purchase_id": 1, "order_detail_id": 2, "possible_num": 2, "confirm_price": "10", "confirm_freight": "1"}},
    )

    assert result.status == "failed"
    assert result.error_code == "invalid_actual_source"


def test_problem_gateway_records_each_write_once_without_sensitive_fields(monkeypatch):
    from app.data_scripts.problem_goods import ProblemGoodsGateway

    gateway_class = getattr(problem_runner_module, "_SystemRegressionProblemGoodsGateway", None)
    assert gateway_class is not None
    monkeypatch.setattr(
        ProblemGoodsGateway,
        "_admin_request",
        lambda _self, _path, _fields, _action, *, mutation: {"success": True, "code": 0, "token": "must-not-leak"},
    )
    log = {"steps": []}
    gateway = gateway_class(object(), {}, log)

    payload = gateway._admin_request(
        "/problem.store",
        {"password": "must-not-leak"},
        "create_problem_goods",
        mutation=True,
    )

    assert payload["success"] is True
    assert log["attempted_actions"] == [
        {
            "action": "create_problem_goods",
            "request_type": "write",
            "target": "/problem.store",
            "business_object": "problem_goods",
            "attempt_count": 1,
            "result": "success",
            "timed_out": False,
            "reconciliation_performed": False,
            "repeated": False,
            "response_summary": {"success": True, "code": 0},
        }
    ]
    assert "must-not-leak" not in json.dumps(log)


def test_problem_live_execute_builds_complete_zero_amount_evidence_and_checkpoint(monkeypatch):
    import app.data_scripts as data_scripts
    import app.data_scripts.payment_amount_regression.runner as payment_module
    from app.system_regression.common.evidence import MoneyEvidence

    gateway_class = getattr(problem_runner_module, "_SystemRegressionProblemGoodsGateway", None)
    assert gateway_class is not None
    class FakeEvidenceGateway:
        def __init__(self, _env, _variables):
            pass

        def _balance_rows(self, _variables):
            return []

        def _preview_evidence(self, _bills, _scenario, reference):
            return MoneyEvidence("problem_goods_preview", Decimal("0"), "JPY", "none", reference=reference)

        def _wait_new_balance_rows(self, _before, _variables, _references, *, allow_empty, expected_direction=None):
            assert allow_empty is True
            return []

    def fake_problem_script(_env, variables, *, gateway_factory=None):
        assert gateway_factory is gateway_class
        log = {
            "attempted_actions": [
                {
                    "action": "create_problem_goods",
                    "request_type": "write",
                    "target": "/problem.store",
                    "business_object": "problem_goods",
                    "attempt_count": 1,
                    "result": "success",
                    "timed_out": False,
                    "reconciliation_performed": False,
                    "repeated": False,
                    "response_summary": {"success": True, "code": 0},
                }
            ],
            "steps": [{"name": "problem_created", "problem_goods_id": 7001}],
        }
        return True, json.dumps(log), "", {
            "order_sn": variables["order_sn"],
            "problem_goods_id": 7001,
            "status": 6,
            "status_name": "completed",
            "preview_bills": [],
            "completed": True,
        }

    monkeypatch.setattr(data_scripts, "run_problem_goods_script", fake_problem_script)
    monkeypatch.setattr(payment_module, "LivePaymentRegressionExecutor", FakeEvidenceGateway)
    checkpoints = []
    case = _case(
        key="金额-001",
        runner_kind="problem_goods",
        parameters={"problem_type": 9, "adjustment": "unchanged"},
        direction="none",
        expectation={
            "outcome": "success",
            "direction": "none",
            "required_identities": ["admin", "client"],
            "expected_stage": "problem_goods_completed",
        },
    )
    context = {
        "order_sn": "ORDER-NEW",
        "variables": {},
        "candidate": {"status": 20},
        "resource_evidence": {"order_created": True, "order_created_count": 1},
        "execution_id": "EXEC-NEW",
        "checkpoint": checkpoints.append,
    }
    request = {"problem_type": 9, "order_purchase_id": 91}

    payload = ProblemGoodsRunner(object())._live_execute(case, context, request)

    assert payload["status"] == "passed"
    assert payload["reason_code"] == "ok"
    assert payload["expected_stage"] == "problem_goods_completed"
    assert payload["actual_stage"] == "problem_goods_completed"
    assert payload["stage_evidence"]["stage_matched"] is True
    assert payload["write_state"] == "confirmed_written"
    assert payload["parameter_snapshot"]["case_id"] == "金额-001"
    assert payload["parameter_snapshot"]["problem_goods_id"] == "7001"
    assert payload["after_evidence"]["actual_amount_jpy"] == 0
    assert payload["after_evidence"]["customer_balance_jpy"] == 0
    assert payload["after_evidence"]["preview_bills"] == []
    assert payload["side_effects"]["payment_executed"] is False
    assert payload["side_effects"]["balance_debited"] is False
    assert payload["side_effects"]["balance_bill_created"] is False
    assert payload["side_effects"]["duplicate_order_detected"] is False
    assert payload["side_effects"]["duplicate_problem_goods_detected"] is False
    assert payload["write_request_count"] == 1
    assert checkpoints[-1]["last_write"]["state"] == "confirmed_written"
    assert checkpoints[-1]["current_step"] == "problem_goods_completed"


def test_problem_live_execute_refuses_pass_when_required_evidence_is_missing(monkeypatch):
    import app.data_scripts as data_scripts
    import app.data_scripts.payment_amount_regression.runner as payment_module
    from app.system_regression.common.evidence import MoneyEvidence

    class FakeEvidenceGateway:
        def __init__(self, _env, _variables):
            pass

        def _balance_rows(self, _variables):
            return []

        def _preview_evidence(self, _bills, _scenario, reference):
            return MoneyEvidence("problem_goods_preview", Decimal("0"), "JPY", "none", reference=reference)

        def _wait_new_balance_rows(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr(
        data_scripts,
        "run_problem_goods_script",
        lambda _env, variables, *, gateway_factory=None: (
            True,
            json.dumps({"steps": []}),
            "",
            {
                "order_sn": variables["order_sn"],
                "problem_goods_id": 7002,
                "status": 6,
                "preview_bills": [],
                "completed": True,
            },
        ),
    )
    monkeypatch.setattr(payment_module, "LivePaymentRegressionExecutor", FakeEvidenceGateway)
    case = _case(
        key="金额-001",
        runner_kind="problem_goods",
        parameters={"problem_type": 9, "adjustment": "unchanged"},
        direction="none",
        expectation={"outcome": "success", "direction": "none", "expected_stage": "problem_goods_completed"},
    )

    payload = ProblemGoodsRunner(object())._live_execute(
        case,
        {"order_sn": "ORDER-NEW", "variables": {}, "candidate": {}},
        {"problem_type": 9, "order_purchase_id": 91},
    )

    assert payload["status"] == "failed"
    assert payload["reason_code"] == "evidence_incomplete"
    assert payload["error_code"] == "evidence_incomplete"
    assert payload["failure_reason"]


@pytest.mark.parametrize(
    ("problem_type", "direction", "expected"),
    [
        (1, "credit", {"pre_price": "9"}),
        (2, "credit", {"pre_freight": "2"}),
        (3, "credit", {"pre_num": 2}),
        (4, "credit", {"pre_price": "9"}),
        (5, "credit", {"pre_num": 2, "pre_price": "9"}),
        (6, "debit", {"option_deal_suggest": 1}),
        (7, "debit", {"pre_num": 4, "option_deal_suggest": 1}),
        (8, "none", {"client_deal_other": "系统回归自定义回复"}),
    ],
)
def test_problem_flow_applies_default_adjustment_for_each_problem_type(problem_type, direction, expected):
    captured = {}

    def gateway(_case, _context, request):
        captured.update(request)
        return {"status": "passed"}

    result = ProblemGoodsRunner(env=object(), live_gateway=gateway).execute(
        _case(
            key=f"FLOW-{problem_type}",
            runner_kind="problem_flow",
            parameters={"problem_type": problem_type, "client_deal_choice": "other" if problem_type == 8 else "accept"},
            direction=direction,
        ),
        {
            "candidate": {
                "order_purchase_id": 1,
                "order_detail_id": 2,
                "possible_num": 3,
                "confirm_price": "10",
                "confirm_freight": "3",
                "option": [],
            },
            "variables": {},
        },
    )

    assert result.status == "passed"
    for key, value in expected.items():
        assert captured[key] == value


def test_problem_runner_creates_precondition_candidate_when_context_has_none():
    calls = []

    def candidate_loader(_case, context):
        calls.append("prepare")
        return {
            "candidate": {
                "order_purchase_id": 8,
                "order_detail_id": 9,
                "possible_num": 2,
                "confirm_price": "10",
                "confirm_freight": "1",
            },
            "order_sn": "O-PREPARED",
            "variables": context.get("variables", {}),
        }

    def gateway(_case, context, request):
        calls.append((context["order_sn"], request["order_purchase_id"]))
        return {"status": "passed", "order_sn": context["order_sn"]}

    runner = ProblemGoodsRunner(env=object(), live_gateway=gateway, candidate_loader=candidate_loader)
    result = runner.execute(
        _case(key="PG", runner_kind="problem_goods", parameters={"problem_type": 1, "adjustment": "price_down"}, direction="credit"),
        {"variables": {}},
    )

    assert result.status == "passed"
    assert calls == ["prepare", ("O-PREPARED", 8)]


def test_problem_candidate_stops_before_storage(monkeypatch):
    import app.data_scripts as data_scripts
    import app.data_scripts.problem_goods as problem_goods

    captured = {}
    loaded_purchase_nos = []

    def run_full_flow(_env, variables):
        captured.update(variables)
        return True, "", "", {"order_sn": "O1", "purchase_no": "PURCHASE-1"}

    monkeypatch.setattr(data_scripts, "run_full_flow_script", run_full_flow)
    monkeypatch.setattr(
        problem_goods,
        "inspect_problem_goods",
        lambda _env, variables: {
            "order_candidates": [
                {
                    "order_purchase_id": 1,
                    "order_detail_id": 2,
                    "possible_num": 3,
                    "storage_num": 0,
                    "can_submit": True,
                }
            ]
        },
    )

    runner = ProblemGoodsRunner(object())
    monkeypatch.setattr(
        runner,
        "_load_h5_purchase_candidates",
        lambda variables, purchase_no: loaded_purchase_nos.append(purchase_no)
        or [
            {
                "order_purchase_id": 1,
                "order_detail_id": 2,
                "possible_num": 3,
                "storage_num": 0,
                "can_submit": True,
            }
        ],
        raising=False,
    )

    result = runner._prepare_candidate(
        _case(
            key="PG",
            runner_kind="problem_goods",
            parameters={"problem_type": 3, "adjustment": "quantity_down"},
            direction="credit",
        ),
        {"variables": {}},
    )

    assert captured["stop_after_node"] == "checking_started"
    assert captured["confirm_freight"] == "3"


def test_pre_num_below_storage_stops_before_shelf_so_problem_can_be_created(monkeypatch):
    import app.data_scripts as data_scripts
    import app.data_scripts.problem_goods as problem_goods

    captured = {}

    def run_full_flow(_env, variables):
        captured.update(variables)
        return True, "", "", {"order_sn": "O-STORE", "purchase_no": "PURCHASE-STORE"}

    monkeypatch.setattr(data_scripts, "run_full_flow_script", run_full_flow)
    monkeypatch.setattr(
        problem_goods,
        "inspect_problem_goods",
        lambda _env, _variables: {
            "order_candidates": [
                {
                    "order_purchase_id": 9,
                    "order_detail_id": 8,
                    "possible_num": 3,
                    "storage_num": 0,
                    "can_submit": True,
                }
            ]
        },
    )
    runner = ProblemGoodsRunner(object())
    monkeypatch.setattr(
        runner,
        "_load_h5_purchase_candidates",
        lambda _variables, _purchase_no: [
            {
                "order_purchase_id": 9,
                "order_detail_id": 8,
                "possible_num": 3,
                "storage_num": 0,
                "can_submit": True,
            }
        ],
        raising=False,
    )

    result = runner._prepare_candidate(
        _case(
            key="拦截-006",
            runner_kind="problem_guard",
            parameters={"guard_kind": "pre_num_below_storage"},
            direction="none",
        ),
        {"variables": {}},
    )

    assert captured["stop_after_node"] == "checking_started"
    assert result["candidate"]["can_submit"] is True
    assert result["candidate"]["storage_num"] == 0


def test_problem_candidate_splits_purchase_no_for_same_sorting(monkeypatch):
    import app.data_scripts as data_scripts
    import app.system_regression.projects.japan.problem_runner as problem_runner_mod

    captured = {}
    split_calls = []

    def run_full_flow(_env, variables):
        captured.update(variables)
        return True, "", "", {"order_sn": "O-300001", "purchase_no": "PURCHASE-1"}

    class FakeSplitGateway:
        def __init__(self, *args, **kwargs):
            pass

        def split_purchase_no(self, order_purchase_id, new_num, new_purchase_no):
            split_calls.append(
                {
                    "order_purchase_id": order_purchase_id,
                    "new_num": new_num,
                    "new_purchase_no": new_purchase_no,
                }
            )
            return {"success": True, "code": 0}

        def list_purchase_candidates(self, _order_sn):
            return [
                {
                    "order_purchase_id": 11,
                    "order_detail_id": 22,
                    "sorting": 1,
                    "possible_num": 2,
                    "storage_num": 0,
                    "can_submit": True,
                    "purchase_no": "PURCHASE-1",
                },
                {
                    "order_purchase_id": 12,
                    "order_detail_id": 22,
                    "sorting": 1,
                    "possible_num": 1,
                    "storage_num": 0,
                    "can_submit": True,
                    "purchase_no": split_calls[-1]["new_purchase_no"],
                },
            ]

        def spot_order_detail(self, _order_sn):
            return {}

    monkeypatch.setattr(data_scripts, "run_full_flow_script", run_full_flow)
    monkeypatch.setattr(problem_runner_mod, "ProblemGoodsGateway", FakeSplitGateway)

    runner = ProblemGoodsRunner(object())
    monkeypatch.setattr(
        runner,
        "_load_h5_purchase_candidates",
        lambda _variables, _purchase_no: [
            {
                "order_purchase_id": 11,
                "order_detail_id": 22,
                "sorting": 1,
                "possible_num": 3,
                "storage_num": 0,
                "can_submit": True,
                "purchase_no": "PURCHASE-1",
            }
        ],
        raising=False,
    )

    result = runner._prepare_candidate(
        _case(
            key="拦截-012",
            runner_kind="problem_guard",
            parameters={"guard_kind": "multiple_purchase_update"},
            direction="none",
        ),
        {"variables": {}},
    )

    assert captured["stop_after_node"] == "purchase_paid"
    assert captured["order_item_num"] == 3
    assert split_calls[0]["order_purchase_id"] == 11
    assert split_calls[0]["new_num"] == 1
    assert split_calls[0]["new_purchase_no"]
    assert result["candidate"]["same_purchase_count"] == 2
    assert result["candidate"]["order_purchase_count"] == 2


def test_problem_candidate_multiple_rate_uses_one_catalog_option(monkeypatch):
    import app.data_scripts as data_scripts
    import app.data_scripts.orders as orders

    captured = {}

    def run_full_flow(_env, variables):
        captured.update(variables)
        return True, "", "", {"order_sn": "O-300001", "purchase_no": "PURCHASE-1"}

    monkeypatch.setattr(data_scripts, "run_full_flow_script", run_full_flow)
    monkeypatch.setattr(
        orders,
        "inspect_order_options",
        lambda _env, _variables: {
            "options": [
                {"id": "rate-1", "key": "rate-1", "name": "检品", "price_type": 1, "price": "5"},
            ]
        },
    )

    runner = ProblemGoodsRunner(object())
    monkeypatch.setattr(
        runner,
        "_load_h5_purchase_candidates",
        lambda _variables, _purchase_no: [
            {
                "order_purchase_id": 11,
                "order_detail_id": 22,
                "possible_num": 3,
                "storage_num": 0,
                "can_submit": True,
            }
        ],
        raising=False,
    )

    runner._prepare_candidate(
        _case(
            key="拦截-010",
            runner_kind="problem_guard",
            parameters={"guard_kind": "multiple_rate_auto"},
            direction="none",
        ),
        {"variables": {}},
    )

    assert captured["order_option_counts"] == {"rate-1": 3}


def test_problem_candidate_guard_without_option_kind_skips_options(monkeypatch):
    import app.data_scripts as data_scripts
    import app.data_scripts.orders as orders

    captured = {}

    def run_full_flow(_env, variables):
        captured.update(variables)
        return True, "", "", {"order_sn": "O-300001", "purchase_no": "PURCHASE-1"}

    def forbidden_inspect(_env, _variables):
        raise AssertionError("非 OPTION 拦截场景不应加载 OPTION 目录")

    monkeypatch.setattr(data_scripts, "run_full_flow_script", run_full_flow)
    monkeypatch.setattr(orders, "inspect_order_options", forbidden_inspect)

    runner = ProblemGoodsRunner(object())
    monkeypatch.setattr(
        runner,
        "_load_h5_purchase_candidates",
        lambda _variables, _purchase_no: [
            {
                "order_purchase_id": 11,
                "order_detail_id": 22,
                "possible_num": 3,
                "storage_num": 0,
                "can_submit": True,
            }
        ],
        raising=False,
    )

    result = runner._prepare_candidate(
        _case(
            key="拦截-015",
            runner_kind="problem_guard",
            parameters={"guard_kind": "direct_complete_invalid_type", "option_deal_suggest": 2},
            direction="none",
        ),
        {"variables": {}},
    )

    assert result["candidate"]["order_purchase_id"] == 11
    assert "order_option_counts" not in captured


def test_quantity_over_possible_uses_catalog_options_not_stale_panel_names(monkeypatch):
    import app.data_scripts as data_scripts
    import app.data_scripts.orders as orders

    captured = {}

    def run_full_flow(_env, variables):
        captured.update(variables)
        return True, "", "", {"order_sn": "O-300001", "purchase_no": "PURCHASE-1"}

    monkeypatch.setattr(data_scripts, "run_full_flow_script", run_full_flow)
    monkeypatch.setattr(
        orders,
        "inspect_order_options",
        lambda *_args, **_kwargs: {
            "options": [
                {"id": "fixed-7", "key": "fixed-7", "name": "针检", "price_type": 0, "price": "2"},
            ]
        },
    )

    runner = ProblemGoodsRunner(object())
    monkeypatch.setattr(
        runner,
        "_load_h5_purchase_candidates",
        lambda _variables, _purchase_no: [
            {
                "order_purchase_id": 11,
                "order_detail_id": 22,
                "possible_num": 3,
                "storage_num": 0,
                "can_submit": True,
            }
        ],
        raising=False,
    )

    runner._prepare_candidate(
        _case(
            key="拦截-007",
            runner_kind="problem_guard",
            parameters={
                "guard_kind": "quantity_over_possible",
                "items": [
                    {
                        "sorting": 1,
                        "quantity": 2,
                        "offer_price": {"value": "10", "currency": "CNY"},
                        "offer_freight": {"value": "3", "currency": "CNY"},
                        "options": [
                            {"name": "加固包装", "price_type": 0, "price": "2.5", "num": 1, "checked": True},
                            {"name": "检品", "price_type": 1, "price": "5", "num": 1, "checked": True},
                        ],
                    }
                ],
            },
            direction="none",
        ),
        {"variables": {}},
    )

    assert captured["order_option_counts"] == {"fixed-7": 3}
    assert "加固包装" not in captured["order_option_counts"]


def test_problem_candidate_option_num_over_goods_orders_extra_option(monkeypatch):
    import app.data_scripts as data_scripts
    import app.data_scripts.orders as orders

    captured = {}

    def run_full_flow(_env, variables):
        captured.update(variables)
        return True, "", "", {"order_sn": "O-300001", "purchase_no": "PURCHASE-1"}

    monkeypatch.setattr(data_scripts, "run_full_flow_script", run_full_flow)
    monkeypatch.setattr(
        orders,
        "inspect_order_options",
        lambda _env, _variables: {
            "options": [
                {"id": "fixed-7", "key": "fixed-7", "name": "针检", "price_type": 0, "price": "2"},
            ]
        },
    )

    runner = ProblemGoodsRunner(object())
    monkeypatch.setattr(
        runner,
        "_load_h5_purchase_candidates",
        lambda _variables, _purchase_no: [
            {
                "order_purchase_id": 11,
                "order_detail_id": 22,
                "possible_num": 3,
                "storage_num": 0,
                "can_submit": True,
            }
        ],
        raising=False,
    )

    runner._prepare_candidate(
        _case(
            key="拦截-009",
            runner_kind="problem_guard",
            parameters={"guard_kind": "option_num_over_goods"},
            direction="none",
        ),
        {"variables": {}},
    )

    # 下单即让 OPTION 数(4)超过商品数(3)，采购处理才会被服务端稳定拒绝
    assert captured["order_option_counts"] == {"fixed-7": 4}


def test_problem_candidate_falls_back_to_inspect_when_h5_empty(monkeypatch):
    import app.data_scripts as data_scripts
    import app.data_scripts.problem_goods as problem_goods

    def run_full_flow(_env, _variables):
        return True, "", "", {"order_sn": "O-300001", "purchase_no": "PURCHASE-1"}

    monkeypatch.setattr(data_scripts, "run_full_flow_script", run_full_flow)
    monkeypatch.setattr(
        problem_goods,
        "inspect_problem_goods",
        lambda _env, _variables: {
            "order_candidates": [
                {
                    "order_purchase_id": 33,
                    "order_detail_id": 44,
                    "possible_num": 3,
                    "storage_num": 0,
                    "can_submit": True,
                }
            ]
        },
    )

    runner = ProblemGoodsRunner(object())
    monkeypatch.setattr(runner, "_load_h5_purchase_candidates", lambda _variables, _purchase_no: [], raising=False)

    result = runner._prepare_candidate(
        _case(
            key="拦截-003",
            runner_kind="problem_guard",
            parameters={"guard_kind": "purchase_wait_pay"},
            direction="none",
        ),
        {"variables": {}},
    )

    assert result["candidate"]["order_purchase_id"] == 33


def test_h5_purchase_candidates_are_flattened_and_normalized():
    payload = {
        "success": True,
        "code": 0,
        "data": {
            "list": [
                {
                    "order_sn": "O1",
                    "list": [
                        {
                            "order_purchase_id": 11,
                            "order_detail_id": 22,
                            "possible_num": 3,
                            "storage_num": 0,
                            "max_submit_num": 3,
                            "can_submit": 1,
                        }
                    ],
                }
            ]
        },
    }

    rows = ProblemGoodsRunner._h5_purchase_candidates_from_payload(payload)

    assert rows == [
        {
            "order_purchase_id": 11,
            "order_detail_id": 22,
            "possible_num": 3,
            "storage_num": 0,
            "max_submit_num": 3,
            "can_submit": True,
        }
    ]


def test_problem_balance_rows_use_business_in_out_direction():
    rows = ProblemGoodsRunner._normalize_balance_rows(
        [
            {"id": 1, "amount": 63, "bill_type_group": "出金"},
            {"id": 2, "amount": 21, "bill_type_name": "商品调整入金"},
        ]
    )

    assert rows[0]["change_amount"] == "-63"
    assert rows[1]["change_amount"] == "21"


def test_problem_candidate_resumes_created_order_after_state_race(monkeypatch):
    import app.data_scripts as data_scripts
    import app.data_scripts.problem_goods as problem_goods

    calls = []

    def run_full_flow(_env, variables):
        calls.append(("full", dict(variables)))
        return False, "", "", {"order_sn": "O1", "reason": "订单翻译提交失败"}

    def run_shelf(_env, variables):
        calls.append(("shelf", dict(variables)))
        return False, "", "", {"order_sn": "O1", "reason": "订单已进入采购中间状态"}

    def run_resume(_env, variables):
        calls.append(("resume", dict(variables)))
        return True, "", "", {"order_sn": "O1", "stopped_after_node": "checking_started"}

    monkeypatch.setattr(data_scripts, "run_full_flow_script", run_full_flow)
    monkeypatch.setattr(data_scripts, "run_purchase_to_shelf_script", run_shelf)
    monkeypatch.setattr(data_scripts, "run_resume_order_flow_script", run_resume)
    monkeypatch.setattr(
        problem_goods,
        "inspect_problem_goods",
        lambda _env, variables: {
            "order_candidates": [
                {
                    "order_purchase_id": 1,
                    "order_detail_id": 2,
                    "possible_num": 3,
                    "storage_num": 0,
                    "can_submit": True,
                }
            ]
        },
    )

    result = ProblemGoodsRunner(object())._prepare_candidate(
        _case(
            key="PG",
            runner_kind="problem_goods",
            parameters={"problem_type": 3, "adjustment": "quantity_down"},
            direction="credit",
        ),
        {"variables": {}},
    )

    assert [name for name, _variables in calls] == ["full", "shelf", "resume"]
    assert calls[1][1]["order_sn"] == "O1"
    assert calls[1][1]["stop_after_node"] == "checking_started"
    assert result["order_sn"] == "O1"


def test_problem_runner_switches_to_minister_context_for_refund_at_least_500():
    resolved = []

    def account_resolver(_case, _context, _request, refund_cny):
        resolved.append(refund_cny)
        return {"backend_account": "shenwenni", "backend_password": "stored-secret"}

    def gateway(_case, context, _request):
        assert context["variables"]["backend_account"] == "shenwenni"
        assert context["variables"]["backend_password"] == "stored-secret"
        return {"status": "passed"}

    runner = ProblemGoodsRunner(env=object(), live_gateway=gateway, account_resolver=account_resolver)
    result = runner.execute(
        _case(key="PG", runner_kind="problem_goods", parameters={"problem_type": 3, "adjustment": "quantity_all_down"}, direction="credit"),
        {"candidate": {"order_purchase_id": 1, "order_detail_id": 2, "possible_num": 1, "confirm_price": "600", "confirm_freight": "0"}, "variables": {}},
    )

    assert result.status == "passed"
    assert resolved == [Decimal("600.00")]


def test_guard_runner_passes_only_when_expected_error_matches():
    expected_case = _case(
        key="G1",
        runner_kind="problem_guard",
        parameters={"guard_kind": "duplicate"},
        direction="none",
        expectation={"outcome": "guard", "direction": "none", "error_codes": ["DUPLICATE"], "error_keywords": ["重复提出"]},
    )
    passed = GuardRunner(lambda _case, _context: {"error_code": "DUPLICATE", "error_message": "不可重复提出"}).execute(expected_case, {})
    missed = GuardRunner(lambda _case, _context: {"status": "passed", "writes": ["problem_goods"]}).execute(expected_case, {})

    assert passed.status == "passed"
    assert missed.status == "failed"
    assert missed.error_code == "guard_not_triggered"


def test_japan_runner_dispatches_and_turns_precondition_errors_into_blocked():
    class Stub:
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

        def execute(self, _case, _context):
            if self.error:
                raise self.error
            return self.result

    payment = Stub(error=RuntimeError("登录失败"))
    runner = JapanRegressionRunner(payment_runner=payment, problem_runner=Stub(), guard_runner=Stub())
    result = runner.execute(_case(key="P", runner_kind="order_payment", parameters={}), {})

    assert result.status == "blocked"
    assert result.error_code == "precondition_error"
    assert "登录失败" in result.error_message


def test_payment_write_reconciliation_status_is_not_reclassified_as_precondition_error():
    from app.data_scripts.payment_amount_regression.runner import ScenarioBlocked

    class StructuredExecutor:
        def execute(self, _scenario, _batch_no):
            raise ScenarioBlocked(
                "订单翻译写入状态无法确认",
                reason_code="unknown_write_state",
                evidence={
                    "order_sn": "ORDER-UNKNOWN",
                    "write_state": "indeterminate",
                    "request_attempt_count": 1,
                    "attempted_actions": [{"action": "order.submitTranslate", "attempt_count": 1}],
                    "before_evidence": {"backend_status": 20},
                    "after_evidence": {"statuses": []},
                    "business_diffs": {},
                },
            )

    payment = PaymentRunner(env=object(), executor_factory=lambda _env, _variables: StructuredExecutor())
    runner = JapanRegressionRunner(payment_runner=payment, problem_runner=object(), guard_runner=object())

    result = runner.execute(_case(key="支付-006", runner_kind="order_payment", parameters={}), {"batch_no": "B1"})

    assert result.status == "blocked"
    assert result.reason_code == "unknown_write_state"
    assert result.error_code == "unknown_write_state"
    assert result.order_sn == "ORDER-UNKNOWN"
    assert result.result["write_state"] == "indeterminate"
    assert result.result["request_attempt_count"] == 1


def test_japan_runner_turns_minister_account_request_into_waiting_account():
    class WaitingRunner:
        def execute(self, _case, _context):
            raise AccountLoginRequired("沈文妮账号自动登录失败")

    runner = JapanRegressionRunner(payment_runner=WaitingRunner(), problem_runner=WaitingRunner(), guard_runner=WaitingRunner())
    result = runner.execute(_case(key="PG", runner_kind="problem_goods", parameters={}), {})

    assert result.status == "waiting_account"
    assert result.resume_stage == "minister_account_login"
    assert result.error_code == "minister_account_required"
