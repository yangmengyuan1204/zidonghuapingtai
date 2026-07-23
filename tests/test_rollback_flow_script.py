from types import SimpleNamespace

import pytest
import requests

from app.data_scripts import rollback_flow as rollback_module
from app.data_scripts.rollback_flow import (
    ORDER_EDGES,
    PORDER_EDGES,
    PORDER_DETECTED_STAGES,
    JapanRollbackGateway,
    RollbackFlow,
    RollbackFlowError,
    _item_is_checking,
)
from app.services.data_factory_agent import ALLOWED_VARIABLE_KEYS, _analyze_turn, _rollback_contract, _verify_goal
from app.services import data_factory_agent_tools as agent_tools
from app.services.data_factory_agent_tools import AgentToolContext


class FakeRollbackGateway:
    def __init__(self, order_stage="order_quoted", porder_stage="porder_quoted"):
        self.order_stage = order_stage
        self.porder_stage = porder_stage
        self.order_edges = []
        self.porder_edges = []
        self.shelf_mutations = []
        self.shelf_rolled_back = False

    def order_snapshot(self, _order_sn):
        return {"stage": self.order_stage, "data": {"order_sn": "ORDER", "order_detail": []}}

    def rollback_order_edge(self, source, _order_sn, _order_data):
        target = ORDER_EDGES[source][0]
        self.order_edges.append((source, target))
        self.order_stage = target
        return {"success": True, "code": 0}, "", target

    def porder_snapshot(self, _porder_sn):
        return {"stage": self.porder_stage}

    def rollback_porder_edge(self, source, _porder_sn):
        target = PORDER_EDGES[source][0]
        self.porder_edges.append((source, target))
        self.porder_stage = target
        return {"success": True, "code": 0}, "", target

    def shelf_snapshot(self, _order_sn, purchase_no, purchase_id):
        return {
            "purchase_no": purchase_no or "PURCHASE-1",
            "purchase_id": purchase_id or "11",
            "item": {"storage_num": 1 if not self.shelf_rolled_back else 0},
            "rows": [],
            "checking": self.shelf_rolled_back,
        }

    def rollback_shelf(self, _snapshot, quantity):
        self.shelf_mutations.append(quantity)
        self.shelf_rolled_back = True
        return {"success": True, "code": 0}, ""


def _flow(gateway, **variables):
    return RollbackFlow(
        gateway,
        {"rollback_verify_retries": 1, "rollback_verify_delay": 0, **variables},
        {"steps": []},
    )


def test_order_rollback_runs_every_adjacent_edge():
    gateway = FakeRollbackGateway()

    summary = _flow(
        gateway,
        rollback_target="order_translate",
        order_sn="2026072200000000-300001",
    ).run()

    assert gateway.order_edges == [
        ("order_quoted", "order_wait_offer"),
        ("order_wait_offer", "order_purchase"),
        ("order_purchase", "order_translate"),
    ]
    assert summary["current_node"] == "order_translate"
    assert summary["verified"] is True


def test_porder_rollback_runs_every_adjacent_edge():
    gateway = FakeRollbackGateway()

    summary = _flow(gateway, rollback_target="porder_wait_translate", porder_sn="PORDER-1").run()

    assert gateway.porder_edges == [
        ("porder_quoted", "porder_wait_offer"),
        ("porder_wait_offer", "porder_wait_box"),
        ("porder_wait_box", "porder_wait_translate"),
    ]
    assert summary["current_node"] == "porder_wait_translate"


def test_three_edge_chain_is_read_write_read_for_every_step():
    class SequencedGateway(FakeRollbackGateway):
        def __init__(self):
            super().__init__()
            self.events = []

        def order_snapshot(self, order_sn):
            self.events.append(("read", self.order_stage))
            return super().order_snapshot(order_sn)

        def rollback_order_edge(self, source, order_sn, order_data):
            self.events.append(("write", source))
            return super().rollback_order_edge(source, order_sn, order_data)

    gateway = SequencedGateway()

    _flow(gateway, rollback_target="order_translate", order_sn="ORDER-1").run()

    assert gateway.events == [
        ("read", "order_quoted"),
        ("write", "order_quoted"),
        ("read", "order_wait_offer"),
        ("write", "order_wait_offer"),
        ("read", "order_purchase"),
        ("write", "order_purchase"),
        ("read", "order_translate"),
    ]


def test_failed_intermediate_verification_stops_later_writes():
    class StuckGateway(FakeRollbackGateway):
        def rollback_order_edge(self, source, _order_sn, _order_data):
            target = ORDER_EDGES[source][0]
            self.order_edges.append((source, target))
            return {"success": True, "code": 0}, "", target

    gateway = StuckGateway()

    with pytest.raises(RollbackFlowError, match="状态校验失败"):
        _flow(gateway, rollback_target="order_translate", order_sn="ORDER-1").run()

    assert gateway.order_edges == [("order_quoted", "order_wait_offer")]


def test_uncertain_write_is_followed_only_by_read_verification():
    class UncertainGateway(FakeRollbackGateway):
        def __init__(self):
            super().__init__(order_stage="order_quoted")
            self.events = []

        def order_snapshot(self, order_sn):
            self.events.append("read")
            return super().order_snapshot(order_sn)

        def rollback_order_edge(self, source, order_sn, order_data):
            self.events.append("write")
            payload, _, target = super().rollback_order_edge(source, order_sn, order_data)
            return payload, "写接口结果不确定：ChunkedEncodingError", target

    gateway = UncertainGateway()

    summary = _flow(gateway, rollback_target="order_wait_offer", order_sn="ORDER-1").run()

    assert summary["verified"] is True
    assert gateway.events == ["read", "write", "read"]


def test_rollback_at_target_is_idempotent():
    gateway = FakeRollbackGateway(order_stage="order_wait_offer")

    summary = _flow(gateway, rollback_target="order_wait_offer", order_sn="ORDER-1").run()

    assert summary["already_at_target"] is True
    assert gateway.order_edges == []


def test_rollback_never_advances_forward():
    gateway = FakeRollbackGateway(order_stage="order_translate")

    with pytest.raises(RollbackFlowError, match="不会执行正向推进"):
        _flow(gateway, rollback_target="order_wait_offer", order_sn="ORDER-1").run()

    assert gateway.order_edges == []


def test_shelf_rollback_uses_negative_one_and_verifies():
    gateway = FakeRollbackGateway()

    summary = _flow(
        gateway,
        rollback_target="shelf_checking",
        order_sn="2026072200000000-300001",
    ).run()

    assert gateway.shelf_mutations == [-1]
    assert summary["current_node"] == "shelf_checking"
    assert summary["verified"] is True


@pytest.mark.parametrize(
    "item",
    [
        {"status": 40},
        {"status": "41"},
        {"statusName": "等待核查"},
    ],
)
def test_shelf_checking_accepts_numeric_and_text_status(item):
    assert _item_is_checking(item) is True


def test_shelf_selection_rejects_requested_item_that_is_not_shelved():
    with pytest.raises(RollbackFlowError, match="未上架"):
        JapanRollbackGateway._select_item(
            [{"order_purchase_id": 11, "storage_num": 0, "status": 30}],
            "11",
        )


def test_shelf_selection_does_not_fall_back_to_only_unshelved_item():
    with pytest.raises(RollbackFlowError, match="没有已上架"):
        JapanRollbackGateway._select_item(
            [{"order_purchase_id": 11, "storage_num": 0, "status": 30}],
            "",
        )


def test_shelf_storage_reduction_is_evidence_not_success():
    class StorageOnlyGateway(FakeRollbackGateway):
        def shelf_snapshot(self, _order_sn, purchase_no, purchase_id):
            storage_num = 2 if not self.shelf_rolled_back else 1
            return {
                "purchase_no": purchase_no or "PURCHASE-1",
                "purchase_id": purchase_id or "11",
                "item": {"order_purchase_id": 11, "storage_num": storage_num, "status": 30},
                "rows": [],
                "checking": False,
            }

    gateway = StorageOnlyGateway()
    flow = _flow(
        gateway,
        rollback_target="shelf_checking",
        order_sn="2026072200000000-300001",
    )

    with pytest.raises(RollbackFlowError, match="未确认商品回到核查中"):
        flow.run()

    assert gateway.shelf_mutations == [-1]
    assert flow.log["steps"][0]["storage_reduced"] is True


def test_order_wait_offer_uses_live_detail_json():
    gateway = object.__new__(JapanRollbackGateway)
    gateway.variables = {}
    captured = {}

    def mutation(path, fields):
        captured.update({"path": path, "fields": fields})
        return {"success": True, "code": 0}, ""

    gateway._mutation_once = mutation
    payload, uncertain, target = gateway.rollback_order_edge(
        "order_wait_offer",
        "ORDER-1",
        {
            "order_sn": "ORDER-1",
            "order_detail": [{"id": 7, "confirm_price": "12"}],
            "other_price": "3",
            "other_price_remark": "remark",
            "predict_logistics_price": "4",
            "y_remark": "y",
            "y_reply": "reply",
        },
    )

    assert payload["success"] is True
    assert uncertain == ""
    assert target == "order_purchase"
    assert captured["path"] == "/order.backToWaitConfirm"
    body = __import__("json").loads(captured["fields"]["data"])
    assert body["order_detail"][0]["confirm_price"] == "12"
    assert body["other_price"] == "3"


@pytest.mark.parametrize(
    ("source", "expected_path", "expected_fields"),
    [
        ("order_quoted", "/order.backToWaitOffer", {"order_sn_set": ["ORDER-1"]}),
        ("order_purchase", "/order.backToWaitTranslate", {"order_sn_set": ["ORDER-1"]}),
    ],
)
def test_order_simple_edges_use_exact_path_and_body(source, expected_path, expected_fields):
    gateway = object.__new__(JapanRollbackGateway)
    gateway.variables = {}
    captured = {}
    gateway._mutation_once = lambda path, fields: (captured.update(path=path, fields=fields) or ({"success": True, "code": 0}, ""))

    gateway.rollback_order_edge(source, "ORDER-1", {"order_detail": [{"id": 7}]})

    assert captured == {"path": expected_path, "fields": expected_fields}


def test_order_wait_offer_edge_uses_exact_path_and_nested_body():
    gateway = object.__new__(JapanRollbackGateway)
    gateway.variables = {}
    captured = {}
    gateway._mutation_once = lambda path, fields: (captured.update(path=path, fields=fields) or ({"success": True, "code": 0}, ""))
    order_data = {
        "order_sn": "ORDER-1",
        "order_detail": [{"id": 7, "confirm_price": "12"}],
        "other_price": "3",
        "other_price_remark": "remark",
        "predict_logistics_price": "4",
        "y_remark": "y",
        "y_reply": "reply",
    }

    gateway.rollback_order_edge("order_wait_offer", "ORDER-1", order_data)

    assert captured["path"] == "/order.backToWaitConfirm"
    assert __import__("json").loads(captured["fields"]["data"]) == order_data


@pytest.mark.parametrize(
    ("source", "expected_path"),
    [
        ("porder_quoted", "/porder.backToOffer"),
        ("porder_wait_offer", "/porder.backToConfirm"),
        ("porder_wait_box", "/porder.toWaitTranslate"),
    ],
)
def test_porder_edges_use_exact_path_and_body(source, expected_path):
    gateway = object.__new__(JapanRollbackGateway)
    gateway.variables = {}
    gateway.admin_token = "TOKEN"
    gateway.session = SimpleNamespace(headers={"Authorization": "Bearer TOKEN"})
    captured = {}
    gateway._mutation_once = lambda path, fields: (captured.update(path=path, fields=fields) or ({"success": True, "code": 0}, ""))

    gateway.rollback_porder_edge(source, "PORDER-1")

    assert captured == {"path": expected_path, "fields": {"porder_sn": "PORDER-1"}}


def test_shelf_write_uses_exact_path_and_nested_body(monkeypatch):
    gateway = object.__new__(JapanRollbackGateway)
    gateway.variables = {"warehouse_user_id": "99", "warehouse_index": "2"}
    gateway.session = SimpleNamespace()
    gateway.base_url = "https://example.invalid"
    gateway.timeout = 1
    monkeypatch.setattr(
        rollback_module,
        "_post_admin_urlencoded",
        lambda *_args, **_kwargs: {
            "success": True,
            "code": 0,
            "data": {
                "2": [
                    {
                        "id": 77,
                        "grid_number": "A-77",
                        "wms_stock": [{"order_purchase_id": 11}],
                    }
                ]
            },
        },
    )
    captured = {}
    gateway._mutation_once = lambda path, fields: (captured.update(path=path, fields=fields) or ({"success": True, "code": 0}, ""))

    gateway.rollback_shelf(
        {
            "purchase_id": "11",
            "item": {"order_purchase_id": 11, "uncomplete_problem_num": 2},
            "rows": [],
        },
        -1,
    )

    assert captured == {
        "path": "/follow.upStorage",
        "fields": {
            "grid_id": 77,
            "data": [{"num": -1, "order_purchase_id": "11", "uncomplete_problem_num": 2}],
        },
    }


def test_order_wait_offer_rejects_missing_live_detail_before_write():
    gateway = object.__new__(JapanRollbackGateway)
    gateway.variables = {}
    mutations = []
    gateway._mutation_once = lambda path, fields: mutations.append((path, fields))

    with pytest.raises(RollbackFlowError, match="订单商品明细"):
        gateway.rollback_order_edge("order_wait_offer", "ORDER-1", {"order_sn": "ORDER-1", "order_detail": []})

    assert mutations == []


def test_mutation_catches_chunked_encoding_error_once_as_uncertain():
    class FailingSession:
        def __init__(self):
            self.calls = 0

        def post(self, *_args, **_kwargs):
            self.calls += 1
            raise requests.exceptions.ChunkedEncodingError("broken response")

    gateway = object.__new__(JapanRollbackGateway)
    gateway.base_url = "https://example.invalid"
    gateway.timeout = 1
    gateway.session = FailingSession()

    payload, uncertain = gateway._mutation_once("/write", {"id": 1})

    assert payload == {}
    assert uncertain == "写接口结果不确定：ChunkedEncodingError"
    assert gateway.session.calls == 1


def test_porder_write_sets_existing_header_contract_and_preserves_authorization(monkeypatch):
    session = SimpleNamespace(headers={"Authorization": "Bearer TOKEN"})
    monkeypatch.setattr(rollback_module, "_admin_session_from", lambda _variables: session)
    monkeypatch.setattr(
        rollback_module,
        "_admin_login",
        lambda *_args, **_kwargs: ({"success": True, "code": 0}, "TOKEN"),
    )
    gateway = JapanRollbackGateway(
        SimpleNamespace(base_url="https://example.invalid", timeout=1),
        {"fingerprint": "FP-1"},
        {},
    )
    captured = {}

    def mutation(path, fields):
        captured.update({"path": path, "fields": fields, "headers": dict(session.headers)})
        return {"success": True, "code": 0}, ""

    gateway._mutation_once = mutation
    gateway.rollback_porder_edge("porder_wait_offer", "PORDER-1")

    assert captured["headers"] == {
        "Authorization": "Bearer TOKEN",
        "AdminToken": "Bearer TOKEN",
        "adminToken": "Bearer TOKEN",
        "Fingerprint": "FP-1",
        "PageUrlTrace": "https://jpmanage.rakumart.cn/#/porderDetail?porder_sn=PORDER-1",
        "Origin": "https://jpmanage.rakumart.cn",
        "Referer": "https://jpmanage.rakumart.cn/",
    }


def test_porder_confirmed_is_not_treated_as_wait_box(monkeypatch):
    gateway = object.__new__(JapanRollbackGateway)
    gateway.env = SimpleNamespace()
    gateway.variables = {}
    mutations = []
    gateway.rollback_porder_edge = lambda *args: mutations.append(args)
    monkeypatch.setattr(
        rollback_module,
        "_detect_resume_porder_state",
        lambda *_args, **_kwargs: (
            True,
            {"detected_start_node": "porder_confirmed", "detail_status_texts": ["装箱中"]},
        ),
    )

    assert "porder_confirmed" not in PORDER_DETECTED_STAGES
    with pytest.raises(RollbackFlowError, match="无法安全识别"):
        _flow(gateway, rollback_target="porder_wait_translate", porder_sn="PORDER-1").run()
    assert mutations == []


@pytest.mark.parametrize(
    ("instruction", "target", "mode"),
    [
        ("把2026072200000000-300001从已报价退回到待报价", "order_wait_offer", "resume_order"),
        ("配送单P2024-001从待报价退回待装箱", "porder_wait_box", "resume_porder"),
        ("把订单2026072200000000-300001的上架商品输入-1下架到核查中", "shelf_checking", "resume_order"),
    ],
)
def test_rollback_contract_from_one_sentence(instruction, target, mode):
    status, goal, question = _rollback_contract([{"role": "user", "content": instruction}])

    assert status == "awaiting_confirmation"
    assert question == ""
    assert goal["mode"] == mode
    assert goal["target_node"] == target
    assert goal["operations"][0]["type"] == "rollback"


def test_rollback_contract_requires_identifier():
    status, goal, question = _rollback_contract([{"role": "user", "content": "把配送单退回到待报价"}])

    assert status == "clarifying"
    assert goal == {}
    assert "配送单号" in question


@pytest.mark.parametrize(
    ("instruction", "key", "expected"),
    [
        (
            "订单号2026072200000000-300001，更正为2026072200000000-300099，退回订单采购",
            "order_sn",
            "2026072200000000-300099",
        ),
        (
            "配送单号PORDER-OLD001，更正配送单号PORDER-NEW009，退回待装箱",
            "porder_sn",
            "PORDER-NEW009",
        ),
    ],
)
def test_rollback_contract_uses_last_explicit_identifier(instruction, key, expected):
    status, goal, question = _rollback_contract([{"role": "user", "content": instruction}])

    assert status == "awaiting_confirmation"
    assert question == ""
    assert goal["variables"][key] == expected


@pytest.mark.parametrize("label", ["库位ID", "grid_id"])
def test_shelf_contract_accepts_explicit_grid_id(label):
    instruction = f"把订单2026072200000000-300001的商品输入-1下架到核查中，{label}=GRID-9"

    status, goal, question = _rollback_contract([{"role": "user", "content": instruction}])

    assert status == "awaiting_confirmation"
    assert question == ""
    assert goal["variables"]["grid_id"] == "GRID-9"
    assert "grid_id" in ALLOWED_VARIABLE_KEYS


def test_shelf_contract_does_not_require_purchase_id_for_unique_product():
    status, goal, question = _rollback_contract(
        [{"role": "user", "content": "把订单2026072200000000-300001的唯一商品下架到核查中"}]
    )

    assert status == "awaiting_confirmation"
    assert question == ""
    assert "order_purchase_id" not in goal["variables"]


def test_analyze_turn_uses_deterministic_rollback_contract_without_model():
    status, goal, question, trace = _analyze_turn(
        None,
        [{"role": "user", "content": "把2026072200000000-300001退回到订单采购"}],
        {},
    )

    assert status == "awaiting_confirmation"
    assert question == ""
    assert goal["target_node"] == "order_purchase"
    assert trace["model"] == "deterministic_rollback_contract"


def test_agent_tool_uses_confirmed_rollback_target(monkeypatch):
    captured = {}
    context = AgentToolContext(
        db=None,
        env=SimpleNamespace(),
        project_id=1,
        goal={
            "target_node": "order_wait_offer",
            "order_sn": "2026072200000000-300001",
            "variables": {},
            "operations": [
                {"id": "operation_1", "type": "rollback", "target_node": "order_wait_offer"}
            ],
        },
        variables={},
        public_variables={},
        state={"current_operation_id": "operation_1"},
    )

    def fake_save(_context, key, runner, variables):
        captured.update({"key": key, "runner": runner, "variables": variables})
        return {"tool": key, "passed": True, "summary": {}}

    monkeypatch.setattr(agent_tools, "_save_script_result", fake_save)
    result = agent_tools._rollback_business_state(context, {})

    assert result["passed"] is True
    assert captured["key"] == "rollback_flow"
    assert captured["variables"]["rollback_target"] == "order_wait_offer"
    assert captured["variables"]["order_sn"] == "2026072200000000-300001"


def test_agent_verification_accepts_only_verified_rollback_result():
    context = SimpleNamespace(goal={"target_node": "porder_wait_box"})

    passed, detail = _verify_goal(
        context,
        {"passed": True, "summary": {"current_node": "porder_wait_box", "verified": True}},
    )

    assert passed is True
    assert detail["actual_node"] == "porder_wait_box"

    failed, _ = _verify_goal(
        context,
        {"passed": True, "summary": {"current_node": "porder_wait_box", "verified": False}},
    )
    assert failed is False
