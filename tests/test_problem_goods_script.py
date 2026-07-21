import json
from decimal import Decimal

import pytest

import app.data_scripts.problem_goods as problem_goods
from app.data_scripts.problem_goods import (
    ProblemGoodsApiError,
    ProblemGoodsError,
    ProblemGoodsFlow,
    ProblemGoodsGateway,
    available_option_catalog,
    client_deal_text,
    merge_purchase_candidates,
    normalize_customer_id,
    order_purchase_candidates,
    parse_preview_bills,
    refund_cny_from_preview,
    validate_auto_option_eligibility,
    validate_manual_options,
)


def _variables(**overrides):
    values = {
        "order_sn": "2026071311333811-300001",
        "customer_id": "300001",
        "problem_goods_id": 895183,
        "translation_content": "自動化テスト",
        "client_deal_choice": "accept",
        "business_decision": "自动化业务决策",
        "service_deal_suggest": 2,
        "option_deal_suggest": 1,
        "option_new": [],
        "problem_type": 8,
        "pre_num": 9,
        "pre_price": "10",
        "pre_freight": "5",
        "g_deal_type": "其他",
        "purchase_remark": "自动化采购处理",
        "confirm_distribution": True,
    }
    values.update(overrides)
    return values


class FakeGateway:
    def __init__(self, status=1, preview_amount=318, purchase_error=None):
        self.status = status
        self.preview_amount = preview_amount
        self.purchase_error = purchase_error
        self.calls = []
        self.row = {
            "problem_goods_id": 895183,
            "order_sn": "2026071311333811-300001",
            "order_purchase_id": 15328018,
            "order_detail_id": 14052229,
            "status": status,
            "type": 8,
            "possible_num": 10,
            "pre_num": 9,
            "pre_price": "10",
            "pre_freight": "5",
            "option": [],
        }

    def _current(self):
        return {**self.row, "status": self.status}

    def find_problem(self, order_sn, problem_goods_id=0, order_purchase_id=0):
        self.calls.append(("find", self.status))
        return self._current()

    def wait_for_status(self, order_sn, problem_goods_id, minimum_status, attempts=6):
        self.calls.append(("wait", minimum_status))
        return self._current()

    def translate(self, problem_goods_id, content):
        self.calls.append(("translate", content))
        self.status = 2
        return {"success": True, "code": 0}

    def client_reply(self, problem_goods_id, content):
        self.calls.append(("client_reply", content))
        self.status = 3
        return {"success": True, "code": 0}

    def update_pre_data(self, problem_goods_id, pre_num, pre_price, pre_freight):
        self.calls.append(("update_pre", pre_num, pre_price, pre_freight))
        return {"success": True, "code": 0}

    def update_options(self, problem_goods_id, options):
        self.calls.append(("update_options", options))
        return {"success": True, "code": 0}

    def business_deal(self, fields, preview):
        self.calls.append(("business_preview" if preview else "business_deal", fields))
        if preview:
            bill = {"amount": self.preview_amount, "exchange_rate": 20, "order_sn": self.row["order_sn"]}
            return {"success": False, "code": 11000, "msg": json.dumps([bill], ensure_ascii=False)}
        self.status = 4
        return {"success": True, "code": 0}

    def balance_changes(self, order_sn):
        self.calls.append(("balance_changes", self.status))
        return [] if self.status < 5 else [{"amount": self.preview_amount, "order_sn": order_sn}]

    def purchase_deal(self, fields):
        self.calls.append(("purchase_deal", fields))
        if self.purchase_error:
            raise self.purchase_error
        self.status = 5
        return {"success": True, "code": 0}

    def distribution_deal(self, problem_goods_id):
        self.calls.append(("distribution_deal", problem_goods_id))
        self.status = 6
        return {"success": True, "code": 0}

    def order_detail(self, order_sn):
        self.calls.append(("order_detail", order_sn))
        return {"order_sn": order_sn, "confirm_num": 9}


def _call_names(gateway):
    return [item[0] for item in gateway.calls]


def test_customer_id_must_match_order_suffix():
    assert normalize_customer_id("2026071311333811-300001", "") == "300001"
    with pytest.raises(ProblemGoodsError, match="不一致"):
        normalize_customer_id("2026071311333811-300001", "300002")


def test_client_other_requires_manual_content():
    assert client_deal_text("accept") == "クイック処理受け入れ"
    assert client_deal_text("other", "手動返信") == "手動返信"
    with pytest.raises(ProblemGoodsError, match="必须填写"):
        client_deal_text("other", "")


def test_manual_options_reject_negative_and_price_type_change():
    original = [{"name": "详细检品", "price_type": 1, "price": 4, "num": 10, "checked": True}]
    with pytest.raises(ProblemGoodsError, match="不能小于0"):
        validate_manual_options(
            [{"name": "详细检品", "price_type": 1, "price": 4, "num": -1, "checked": True}],
            original,
        )
    with pytest.raises(ProblemGoodsError, match="不允许修改"):
        validate_manual_options(
            [{"name": "详细检品", "price_type": 0, "price": 4, "num": 9, "checked": True}],
            original,
        )


def test_manual_options_allow_catalog_option_not_in_original_order():
    original = [{"name": "详细检品", "price_type": 1, "price": 4, "num": 10, "checked": True}]

    options = validate_manual_options(
        [
            {"name": "详细检品", "price_type": 1, "price": 4, "num": 8, "checked": True},
            {"id": 99, "name": "加急服务", "name_translate": "特急サービス", "price_type": 0, "price": 2.5, "num": 8, "checked": True},
        ],
        original,
    )

    assert [item["name"] for item in options] == ["详细检品", "加急服务"]


def test_auto_option_rejects_increase_and_option_count_over_goods_count():
    with pytest.raises(ProblemGoodsError, match="商品数量增加"):
        validate_auto_option_eligibility([], 10, 11)
    with pytest.raises(ProblemGoodsError, match="OPTION数量大于商品数"):
        validate_auto_option_eligibility(
            [{"name": "针检", "num": 20, "price": 0.8, "price_type": 0, "checked": True}],
            10,
            9,
        )
    with pytest.raises(ProblemGoodsError, match="多个百分比OPTION"):
        validate_auto_option_eligibility(
            [
                {"name": "详细检品", "num": 10, "price": 4, "price_type": 1, "checked": True},
                {"name": "附加检品", "num": 10, "price": 2, "price_type": 1, "checked": True},
            ],
            10,
            9,
        )


def test_preview_bill_parsing_and_refund_conversion():
    payload = {
        "success": False,
        "code": 11000,
        "msg": json.dumps([{"amount": 318, "exchange_rate": 20.5}], ensure_ascii=False),
    }
    bills = parse_preview_bills(payload)
    assert bills[0]["amount"] == 318
    assert refund_cny_from_preview(bills) == Decimal("318") / Decimal("20.5")


def test_purchase_list_candidates_use_unstored_quantity_and_confirmed_values():
    payload = {
        "data": {
            "data": [
                {
                    "order_purchase": [
                        {
                            "id": 15326123,
                            "order_detail_id": 14048163,
                            "possible_num": 5,
                            "storage_num": 2,
                            "price": "60.00",
                            "freight": "10.00",
                            "purchase_no": "P-1",
                            "order_detail": {
                                "id": 14048163,
                                "sorting": 2,
                                "confirm_num": 8,
                                "confirm_price": "58.00",
                                "confirm_freight": "12.00",
                                "option": [],
                            },
                        }
                    ]
                }
            ]
        }
    }

    rows = order_purchase_candidates(payload)

    assert len(rows) == 1
    assert rows[0]["max_submit_num"] == 3
    assert rows[0]["can_submit"] is True
    assert rows[0]["pre_num"] == 8
    assert rows[0]["pre_price"] == "58.00"


def test_order_detail_candidates_include_nested_purchases_across_nodes():
    payload = {
        "success": True,
        "data": {
            "order_sn": "2026071816165891-300001",
            "order_detail": [{
                "id": 14052981, "sorting": 1, "confirm_num": 1,
                "confirm_price": "10.00", "confirm_freight": "2.00",
                "order_purchase": [{
                    "id": 15328208, "order_detail_id": 14052981,
                    "purchase_no": "20260718161716", "possible_num": 1,
                    "storage_num": 0, "status": 40,
                }],
            }],
        },
    }

    rows = order_purchase_candidates(payload)

    assert rows == [{
        "order_purchase_id": 15328208, "order_detail_id": 14052981,
        "sorting": 1, "purchase_no": "20260718161716", "goods_name": None,
        "sku_id": None, "purchase_status": 40, "possible_num": 1,
        "storage_num": 0, "max_submit_num": 1, "can_submit": True,
        "price": "10.00", "freight": "2.00", "confirm_num": 1,
        "confirm_price": "10.00", "confirm_freight": "2.00", "pre_num": 1,
        "pre_price": "10.00", "pre_freight": "2.00", "option": [],
    }]


def test_follow_list_candidates_accept_flat_child_fields():
    payload = {
        "success": True,
        "data": {"data": [{
            "order_sn": "2026071816165891-300001", "purchase_no": "20260718161716",
            "list": [{
                "order_purchase_id": 15328209, "order_detail_id": 14052982,
                "sorting": 2, "possible_num": 1, "storage_num": 0,
                "confirm_num": 1, "confirm_price": "11.00", "confirm_freight": "3.00",
            }],
        }]},
    }

    rows = order_purchase_candidates(payload)

    assert len(rows) == 1
    assert rows[0]["order_purchase_id"] == 15328209
    assert rows[0]["order_detail_id"] == 14052982
    assert rows[0]["sorting"] == 2
    assert rows[0]["purchase_no"] == "20260718161716"
    assert rows[0]["max_submit_num"] == 1
    assert rows[0]["confirm_num"] == 1
    assert rows[0]["confirm_price"] == "11.00"
    assert rows[0]["confirm_freight"] == "3.00"
    assert rows[0]["price"] == "11.00"
    assert rows[0]["freight"] == "3.00"


def test_candidates_mark_fully_stored_purchase_unavailable():
    payload = {"data": {"order_detail": [{
        "id": 14052983, "sorting": 3,
        "order_purchase": [{
            "id": 15328210, "order_detail_id": 14052983,
            "possible_num": 1, "storage_num": 1,
        }],
    }]}}

    rows = order_purchase_candidates(payload)

    assert rows[0]["max_submit_num"] == 0
    assert rows[0]["can_submit"] is False


def test_order_purchase_candidates_skip_malformed_id_and_quantity_records():
    payload = {"data": {"order_detail": [
        {"id": -1, "order_purchase": [{"id": 15328210, "possible_num": 1, "storage_num": 0}]},
        {"id": 14052983, "order_purchase": [
            {"id": -1, "possible_num": 1, "storage_num": 0},
            {"id": True, "possible_num": 1, "storage_num": 0},
            {"id": 15328211, "possible_num": -1, "storage_num": 0},
            {"id": 15328212, "possible_num": 1.5, "storage_num": 0},
            {"id": 15328213, "possible_num": 1, "storage_num": float("inf")},
            {"id": 15328214, "possible_num": True, "storage_num": 0},
            {"id": 15328215, "possible_num": "1.0", "storage_num": "0.0"},
        ]},
    ]}}

    rows = order_purchase_candidates(payload)

    assert [row["order_purchase_id"] for row in rows] == [15328215]
    assert rows[0]["possible_num"] == 1


def test_merge_purchase_candidates_skips_malformed_id_and_fills_empty_fields():
    rows = merge_purchase_candidates(
        [
            {"order_purchase_id": "bad-id"}, {"order_purchase_id": -1},
            {"order_purchase_id": True}, {"order_purchase_id": 1.5},
            {"order_purchase_id": float("inf")},
            {"order_purchase_id": 15328213, "purchase_no": "", "sorting": None},
        ],
        [{"order_purchase_id": "15328213.0", "purchase_no": "P-13", "sorting": 3}],
    )

    assert rows == [{"order_purchase_id": 15328213, "purchase_no": "P-13", "sorting": 3}]


def _candidate_gateway(monkeypatch, responses):
    gateway = object.__new__(ProblemGoodsGateway)
    gateway.variables = {"customer_id": "300001"}
    gateway.log = {}
    gateway._path = lambda key, default: default
    calls = []

    def request(path, fields, action, mutation):
        calls.append(path)
        response = responses[path]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(gateway, "_admin_request", request)
    gateway.candidate_request_paths = calls
    return gateway


def _order_detail_payload(purchase_id=15328208, sorting=1):
    return {
        "success": True,
        "data": {
            "order_detail": [
                {
                    "id": 14052980 + sorting,
                    "sorting": sorting,
                    "confirm_num": 1,
                    "order_purchase": [
                        {
                            "id": purchase_id,
                            "order_detail_id": 14052980 + sorting,
                            "possible_num": 1,
                            "storage_num": 0,
                        }
                    ],
                }
            ]
        },
    }


def test_gateway_prefers_order_detail_candidates(monkeypatch):
    gateway = _candidate_gateway(monkeypatch, {"/order.detail": _order_detail_payload()})

    rows = gateway.list_purchase_candidates("2026071816165891-300001")

    assert [row["order_purchase_id"] for row in rows] == [15328208]
    assert gateway.log["candidate_sources"]["order_detail"]["count"] == 1
    assert gateway.candidate_request_paths == ["/order.detail"]


def test_gateway_uses_successful_fallback_when_primary_candidates_are_malformed(monkeypatch):
    malformed_primary = {"success": True, "data": {"order_detail": [{
        "id": 14052981,
        "order_purchase": [{"id": 15328216, "possible_num": 1.5, "storage_num": 0}],
    }]}}
    gateway = _candidate_gateway(
        monkeypatch,
        {
            "/order.detail": malformed_primary,
            "/purchase.purchaseList": _order_detail_payload(15328214),
            "/follow.followList": ProblemGoodsError("temporary failure"),
        },
    )

    rows = gateway.list_purchase_candidates("2026071816165891-300001")

    assert [row["order_purchase_id"] for row in rows] == [15328214]
    assert gateway.candidate_request_paths == ["/order.detail", "/purchase.purchaseList", "/follow.followList"]


def test_gateway_merges_and_deduplicates_fallback_sources(monkeypatch):
    duplicate = _order_detail_payload()["data"]["order_detail"][0]["order_purchase"][0]
    gateway = _candidate_gateway(
        monkeypatch,
        {
            "/order.detail": {"success": True, "data": {"order_detail": []}},
            "/purchase.purchaseList": {"success": True, "data": {"data": [{"order_purchase": [duplicate]}]}},
            "/follow.followList": {
                "success": True,
                "data": {"data": [{
                    "order_sn": "2026071816165891-300001",
                    "list": [
                        {**duplicate, "order_purchase_id": duplicate["id"]},
                        {"order_purchase_id": 15328209, "order_detail_id": 14052982, "sorting": 2, "possible_num": 1, "storage_num": 0},
                    ],
                }]},
            },
        },
    )

    rows = gateway.list_purchase_candidates("2026071816165891-300001")

    assert [row["order_purchase_id"] for row in rows] == [15328208, 15328209]


def test_gateway_returns_empty_when_one_source_succeeds_empty(monkeypatch):
    error = ProblemGoodsError("temporary failure")
    gateway = _candidate_gateway(
        monkeypatch,
        {
            "/order.detail": {"success": True, "data": {"order_detail": []}},
            "/purchase.purchaseList": error,
            "/follow.followList": error,
        },
    )

    assert gateway.list_purchase_candidates("2026071816165891-300001") == []


def test_gateway_raises_when_all_candidate_sources_fail(monkeypatch):
    error = ProblemGoodsError("temporary failure")
    gateway = _candidate_gateway(
        monkeypatch,
        {"/order.detail": error, "/purchase.purchaseList": error, "/follow.followList": error},
    )

    with pytest.raises(ProblemGoodsError, match="候选采购记录查询失败"):
        gateway.list_purchase_candidates("2026071816165891-300001")


def test_available_option_catalog_keeps_unique_option_templates():
    rows = available_option_catalog(
        {
            "data": [
                {"id": 1, "name": "检品", "name_translate": "検品", "price_type": 0, "price": 2},
                {"id": 1, "name": "重复检品", "price_type": 0, "price": 3},
                {"id": 2, "name": "加急", "name_translate": "特急", "price_type": 1, "price": 5},
            ]
        }
    )

    assert [item["id"] for item in rows] == [1, 2]
    assert rows[1]["name_translate"] == "特急"


def test_available_option_catalog_gateway_uses_client_option_list(monkeypatch):
    gateway = ProblemGoodsGateway(type("Env", (), {"base_url": "https://example.test"})(), {}, {})
    captured = {}

    def fake_client_request(path, fields, action, mutation):
        captured.update({"path": path, "fields": fields, "action": action, "mutation": mutation})
        return {"success": True, "code": 0, "data": [{"id": 1, "name": "检品", "price_type": 0, "price": 2}]}

    monkeypatch.setattr(gateway, "_client_request", fake_client_request)

    options = gateway.list_available_options()

    assert options[0]["name"] == "检品"
    assert captured == {"path": "/client/order.optionList", "fields": {}, "action": "查询全量OPTION", "mutation": False}


def test_problem_goods_account_profile_maps_generic_credentials(monkeypatch):
    from app.routers import data_scripts as router
    from app.schemas import DataScriptExecuteRequest

    monkeypatch.setattr(router, "data_script_variables", lambda db, variables, project_id: dict(variables))
    monkeypatch.setattr(
        router,
        "account_profile_variables",
        lambda db, profile_id, project_id: (
            {"username": "leader", "password": "secret", "code": "123456"},
            {"profile_name": "部长账号"},
        ),
    )
    payload = DataScriptExecuteRequest(variables={"backend_account_profile_id": 7})

    values = router._problem_goods_variables(object(), payload, 1)

    assert values["backend_account"] == "leader"
    assert values["backend_password"] == "secret"
    assert values["backend_code"] == "123456"
    assert values["backend_account_profile_name"] == "部长账号"


def test_admin_requests_use_form_urlencoded_data():
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"success": True, "code": 0, "data": True}

    class Session:
        @staticmethod
        def post(url, **kwargs):
            captured.update(kwargs)
            return Response()

    gateway = ProblemGoodsGateway(type("Env", (), {"base_url": "https://example.test"})(), {}, {})
    gateway.admin_session = Session()
    gateway._admin_ready = True

    gateway._admin_request("/problem.test", {"data[0][id]": 1}, "测试", mutation=True)

    assert captured["data"] == {"data[0][id]": "1"}
    assert "files" not in captured


def test_full_flow_runs_each_mutation_once_and_completes():
    gateway = FakeGateway(status=1)
    log = {"steps": []}

    summary = ProblemGoodsFlow(gateway, _variables(pre_num=8), log).run()

    assert summary["completed"] is True
    assert summary["status"] == 6
    names = _call_names(gateway)
    assert names.count("translate") == 1
    assert names.count("client_reply") == 1
    assert names.count("update_pre") == 1
    assert names.count("business_preview") == 1
    assert names.count("business_deal") == 1
    assert names.count("purchase_deal") == 1
    assert names.count("distribution_deal") == 1


def test_unchanged_pre_data_does_not_call_update_endpoint():
    gateway = FakeGateway(status=3)

    summary = ProblemGoodsFlow(gateway, _variables(), {"steps": []}).run()

    assert summary["completed"] is True
    assert "update_pre" not in _call_names(gateway)


def test_preview_at_500_pauses_before_business_commit():
    gateway = FakeGateway(status=3, preview_amount=10000)

    summary = ProblemGoodsFlow(gateway, _variables(), {"steps": []}).run()

    assert summary["paused"] is True
    assert summary["permission_required"] is True
    assert summary["resume_stage"] == "business_deal"
    names = _call_names(gateway)
    assert "business_preview" in names
    assert "business_deal" not in names
    assert "purchase_deal" not in names


def test_backend_permission_failure_returns_leader_resume_prompt():
    error = ProblemGoodsApiError(
        "采购处理",
        {"success": False, "code": 1, "msg": "退款金额大于500人民币需要部长账号进行退款操作，请联系部长进行操作!"},
    )
    gateway = FakeGateway(status=4, purchase_error=error)

    summary = ProblemGoodsFlow(gateway, _variables(), {"steps": []}).run()

    assert summary["paused"] is True
    assert summary["resume_stage"] == "purchase_deal"
    assert _call_names(gateway).count("purchase_deal") == 1
    assert "distribution_deal" not in _call_names(gateway)


def test_leader_resume_starts_at_purchase_and_does_not_repeat_business():
    gateway = FakeGateway(status=4)

    summary = ProblemGoodsFlow(
        gateway,
        _variables(allow_large_refund=True),
        {"steps": []},
    ).run()

    assert summary["completed"] is True
    names = _call_names(gateway)
    assert "translate" not in names
    assert "client_reply" not in names
    assert "business_preview" not in names
    assert "business_deal" not in names
    assert names.count("purchase_deal") == 1
    assert names.count("distribution_deal") == 1


def test_completed_problem_is_idempotent():
    gateway = FakeGateway(status=6)

    summary = ProblemGoodsFlow(gateway, _variables(), {"steps": []}).run()

    assert summary["already_completed"] is True
    assert _call_names(gateway) == ["find"]


def test_distribution_resume_only_needs_order_and_problem_id():
    gateway = FakeGateway(status=5)
    variables = {
        "order_sn": "2026071311333811-300001",
        "customer_id": "300001",
        "problem_goods_id": 895183,
    }

    summary = ProblemGoodsFlow(gateway, variables, {"steps": []}).run()

    assert summary["completed"] is True
    names = _call_names(gateway)
    assert names.count("distribution_deal") == 1
    assert "purchase_deal" not in names


def test_script_entry_returns_standard_four_tuple(monkeypatch):
    gateway = FakeGateway(status=6)
    monkeypatch.setattr(problem_goods, "ProblemGoodsGateway", lambda env, variables, log: gateway)
    monkeypatch.setattr(
        problem_goods,
        "_finish_named",
        lambda script_name, log, passed, summary: (passed, json.dumps(log, default=str), "", summary),
    )

    result = problem_goods.run_problem_goods_script(
        object(),
        {
            "order_sn": "2026071311333811-300001",
            "customer_id": "300001",
            "problem_goods_id": 895183,
        },
    )

    assert len(result) == 4
    assert result[0] is True
    assert result[3]["already_completed"] is True
