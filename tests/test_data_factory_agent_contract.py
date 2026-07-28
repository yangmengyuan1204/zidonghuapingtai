import hashlib
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import AiConfig, Env, Project
from app.data_scripts.capabilities import capability_catalog, effective_contract_fields
from app.services import data_agent_learning as learning_service
from app.services import data_factory_agent as agent_service
from app.services.data_agent_contract_compiler import compile_metadata_contract
from app.services.data_agent_contracts import (
    apply_contract_updates,
    build_contract_editor_schema,
    normalize_execution_contract,
    project_contract_goal,
    resolve_goal_capability,
)
from app.services.data_factory_agent_contract import compile_contract_defaults
from app.services.data_factory_agent_intent import reduce_intent_fields


def _login(client: TestClient) -> dict:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _agent_context() -> tuple[Project, Env]:
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.name == "日本站测试").one()
        env = db.query(Env).filter(Env.project_id == project.id).order_by(Env.id.asc()).first()
        db.add(
            AiConfig(
                provider="openai_compatible",
                base_url="https://deepseek.example.test",
                model="deepseek-chat",
                api_key="test-key",
                create_time=datetime.now(),
            )
        )
        db.commit()
        db.refresh(project)
        db.refresh(env)
        return project, env
    finally:
        db.close()


def _ready_goal() -> dict:
    return {
        "status": "ready",
        "question": "",
        "goal": {
            "mode": "new",
            "target_node": "pending_purchase",
            "variables": {},
        },
    }


def test_metadata_compiler_rejects_undeclared_model_fields():
    order_quote = capability_catalog()["order_quote"]
    goal, rejected = compile_metadata_contract(
        order_quote,
        {"order_sn": "20260701-1", "backend_password": "secret"},
        {"project_id": 1},
    )
    assert "backend_password" in rejected
    assert "backend_password" not in json.dumps(goal, ensure_ascii=False)


def test_metadata_compiler_emits_registered_operation_for_non_core_capability():
    capability = capability_catalog()["order_quote"]

    goal, rejected = compile_metadata_contract(
        capability,
        {"order_sn": "20260701-1"},
        {"project_id": 1},
    )

    assert rejected == []
    assert goal["operations"] == [
        {
            "id": "operation_order_quote_1",
            "type": "registered_capability",
            "capability_key": "order_quote",
        }
    ]


@pytest.mark.parametrize(
    "capability_key",
    [
        key
        for key, capability in capability_catalog().items()
        if capability.agent_enabled
    ],
)
def test_every_agent_enabled_capability_can_compile_a_typed_seed(capability_key):
    capability = capability_catalog()[capability_key]
    candidates = {
        "customer_ids": ["300001"],
        "order_sn": "20260701-1",
        "porder_sn": "P20260701-1",
        "target_node": "order_offered",
        "warehouse_sku_count": 2,
        "send_num": 1,
    }
    fields = {
        field.name: candidates[field.name]
        for field in effective_contract_fields(capability)
        if field.required and field.name in candidates
    }

    goal, rejected = compile_metadata_contract(capability, fields, {})

    assert rejected == []
    assert normalize_execution_contract(goal, capability)


def test_restoring_initial_inference_restores_value_source_and_inferred_state():
    capability = capability_catalog()["shopping_cart"]
    initial_goal, _ = compile_metadata_contract(capability, {}, {})
    session = agent_service.AgentSessionState(
        id="restore-inferred-contract",
        user_id=1,
        project_id=1,
        env_id=1,
        status="awaiting_confirmation",
        capability_key=capability.key,
        goal=initial_goal,
    )
    agent_service._SESSIONS[session.id] = session
    try:
        edited = agent_service.update_agent_goal(
            session.id,
            session.user_id,
            {"keyword": "鞋"},
            session.plan_version,
        )
        edited_field = next(
            field
            for field in edited["contract_editor"]["fields"]
            if field["name"] == "keyword"
        )
        assert edited_field["value"] == "鞋"
        assert edited_field["inferred"] is False
        assert edited_field["restore_value"] == "衣服"
        assert edited_field["restore_source"] == "default"
        assert edited_field["restore_inferred"] is True

        restored = agent_service.update_agent_goal(
            session.id,
            session.user_id,
            {"keyword": edited_field["restore_value"]},
            edited["plan_version"],
        )
        restored_field = next(
            field
            for field in restored["contract_editor"]["fields"]
            if field["name"] == "keyword"
        )
        assert restored_field["value"] == "衣服"
        assert restored_field["source"] == "default"
        assert restored_field["inferred"] is True
    finally:
        agent_service._SESSIONS.pop(session.id, None)


def test_warehouse_required_integer_context_is_applied_before_full_validation():
    capability = capability_catalog()["warehouse_delivery"]

    goal, rejected = compile_metadata_contract(
        capability,
        {},
        {"warehouse_sku_count": 2, "send_num": 1},
    )

    assert rejected == []
    assert goal["variables"] == {"warehouse_sku_count": 2, "send_num": 1}


def test_core_full_flow_still_uses_specialized_compiler(monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "compile_metadata_contract",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    monkeypatch.setattr(
        agent_service, "call_local_model_json", lambda *args, **kwargs: _ready_goal()
    )
    project, env = _agent_context()
    with TestClient(app) as client:
        headers = _login(client)
        created = client.post(
            "/api/data-scripts/agent/sessions",
            headers=headers,
            json={"project_id": project.id, "env_id": env.id, "instruction": "订单待付款"},
        ).json()
    assert created["status"] == "awaiting_confirmation"
    assert created["goal"]["target_node"] == "order_offered"


@pytest.mark.parametrize(
    ("instruction", "expected_capability"),
    [
        ("订单待付款", "full_flow"),
        ("帮我造一个订单", "full_flow"),
        ("订单2026071715475684-300001继续到待拍下", "resume_order_flow"),
        ("配送单P2024-001做到配送单支付", "resume_porder_flow"),
        (
            "订单2026071715475684-300001第1番提出问题产品，单价改成0",
            "problem_goods",
        ),
    ],
)
def test_deterministic_core_intent_overrides_wrong_model_capability(
    monkeypatch, instruction, expected_capability
):
    monkeypatch.setattr(
        agent_service,
        "compile_metadata_contract",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    monkeypatch.setattr(
        agent_service,
        "call_local_model_json",
        lambda *args, **kwargs: {
            "status": "ready",
            "capability_key": "order_quote",
            "fields": {},
            "evidence": {},
            "question": "",
        },
    )
    project, _ = _agent_context()
    db = SessionLocal()
    try:
        status_value, goal, question, trace = agent_service._analyze_turn(
            db,
            [{"role": "user", "content": instruction}],
            {},
            compile_context={"project_id": project.id},
        )
    finally:
        db.close()

    assert (status_value, question) == ("awaiting_confirmation", "")
    assert resolve_goal_capability(goal) == expected_capability
    assert trace["capability_key"] == expected_capability


@pytest.mark.parametrize(
    ("capability_key", "fields", "forbidden_defaults"),
    [
        (
            "resume_order_flow",
            {
                "order_sn": "2026071715475684-300001",
                "target_node": "pending_purchase",
            },
            {"order_payment_mode", "payment_fallback", "finance_confirm"},
        ),
        (
            "resume_porder_flow",
            {"porder_sn": "P2024-001", "target_node": "porder_paid"},
            {"porder_payment_mode", "payment_fallback"},
        ),
    ],
)
def test_core_candidate_seed_does_not_materialize_metadata_defaults(
    capability_key, fields, forbidden_defaults
):
    capability = capability_catalog()[capability_key]
    payload = {
        "status": "ready",
        "capability_key": capability_key,
        "fields": fields,
        "evidence": {},
        "question": "",
    }

    projected = agent_service._core_candidate_payload(
        payload,
        capability,
        fields,
        {},
    )["goal"]

    assert forbidden_defaults.isdisjoint(projected["variables"])


@pytest.mark.parametrize(
    "order_sn",
    ["20260701-1", "2026071715475684-300001"],
)
def test_order_quote_with_processing_word_is_not_forced_to_core(
    monkeypatch, order_sn
):
    monkeypatch.setattr(
        agent_service,
        "call_local_model_json",
        lambda *args, **kwargs: {
            "status": "ready",
            "capability_key": "order_quote",
            "fields": {"order_sn": order_sn},
            "evidence": {"order_sn": f"订单{order_sn}"},
            "question": "",
        },
    )
    project, _ = _agent_context()
    db = SessionLocal()
    try:
        status_value, goal, question, trace = agent_service._analyze_turn(
            db,
            [{"role": "user", "content": f"处理一下订单{order_sn}的报价"}],
            {},
            compile_context={"project_id": project.id},
        )
    finally:
        db.close()

    assert (status_value, question) == ("awaiting_confirmation", "")
    assert goal["capability_key"] == "order_quote"
    assert goal["variables"]["order_sn"] == order_sn
    assert trace["capability_key"] == "order_quote"


def test_non_core_capability_compiles_from_declared_metadata(monkeypatch):
    candidate = {
        "status": "ready",
        "capability_key": "order_quote",
        "fields": {"order_sn": "20260701-1"},
        "evidence": {"order_sn": "订单20260701-1"},
        "question": "",
    }
    monkeypatch.setattr(
        agent_service, "call_local_model_json", lambda *args, **kwargs: candidate
    )
    project, env = _agent_context()
    with TestClient(app) as client:
        headers = _login(client)
        created = client.post(
            "/api/data-scripts/agent/sessions",
            headers=headers,
            json={"project_id": project.id, "env_id": env.id, "instruction": "给订单20260701-1报价"},
        ).json()
    assert created["status"] == "awaiting_confirmation"
    assert created["goal"]["capability_key"] == "order_quote"
    assert created["goal"]["variables"]["order_sn"] == "20260701-1"


def test_warehouse_capability_is_reachable_from_real_turn_analysis(monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "call_local_model_json",
        lambda *args, **kwargs: {
            "status": "ready",
            "capability_key": "warehouse_delivery",
            "fields": {"warehouse_sku_count": 2, "send_num": 1},
            "evidence": {
                "warehouse_sku_count": "选2番",
                "send_num": "每番1件",
            },
            "question": "",
        },
    )
    project, _ = _agent_context()
    db = SessionLocal()
    try:
        status_value, goal, question, trace = agent_service._analyze_turn(
            db,
            [{"role": "user", "content": "从仓库选2番，每番提出1件并创建配送单"}],
            {},
            compile_context={"project_id": project.id},
        )
    finally:
        db.close()

    assert (status_value, question) == ("awaiting_confirmation", "")
    assert goal["capability_key"] == "warehouse_delivery"
    assert goal["variables"] == {"warehouse_sku_count": 2, "send_num": 1}
    assert "warehouse_delivery" in trace["capability_keys"]


def test_non_core_direct_edit_preserves_variable_path_and_updates_provenance():
    goal, _ = compile_metadata_contract(
        capability_catalog()["order_quote"],
        {"order_sn": "OLD-ORDER"},
        {},
    )

    updated, _ = agent_service._apply_session_contract_updates(
        goal,
        {"order_sn": "NEW-ORDER"},
        "order_quote",
    )

    assert updated["variables"]["order_sn"] == "NEW-ORDER"
    assert updated["field_sources"]["order_sn"] == "direct_edit"
    assert "order_sn" not in updated.get("inferred_fields", [])


def test_dynamic_business_group_is_exposed_for_metadata_editor():
    goal, _ = compile_metadata_contract(
        capability_catalog()["shopping_cart"],
        {},
        {},
    )
    session = agent_service.AgentSessionState(
        id="metadata-business-group",
        user_id=1,
        project_id=1,
        env_id=1,
        status="awaiting_confirmation",
        capability_key="shopping_cart",
        goal=goal,
    )

    payload = agent_service._serialize_session(session)

    assert {item["key"] for item in payload["contract_editor"]["groups"]} >= {
        "business"
    }
    assert {
        item["name"]
        for item in payload["contract_editor"]["fields"]
        if item["group"] == "business"
    } == {"keyword", "shop_type", "target_shops", "per_shop"}


def test_confirm_rejects_forged_metadata_contract_with_blank_required_field(
    monkeypatch,
):
    class DeferredExecutor:
        def __init__(self):
            self.calls = []

        def submit(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    executor = DeferredExecutor()
    monkeypatch.setattr(agent_service, "_EXECUTOR", executor)
    monkeypatch.setattr(
        agent_service,
        "call_local_model_json",
        lambda *args, **kwargs: {
            "status": "ready",
            "capability_key": "order_quote",
            "fields": {"order_sn": "20260701-1"},
            "evidence": {"order_sn": "订单20260701-1"},
            "question": "",
        },
    )
    project, env = _agent_context()
    with TestClient(app) as client:
        headers = _login(client)
        created = client.post(
            "/api/data-scripts/agent/sessions",
            headers=headers,
            json={
                "project_id": project.id,
                "env_id": env.id,
                "instruction": "给订单20260701-1报价",
            },
        ).json()
        agent_service._SESSIONS[created["id"]].goal["variables"]["order_sn"] = ""
        response = client.post(
            f"/api/data-scripts/agent/sessions/{created['id']}/confirm",
            headers=headers,
            json={"plan_version": created["plan_version"]},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["fields"] == {"order_sn": "订单号为必填项"}
    assert executor.calls == []


def test_confirm_rejects_contract_without_registered_operations(monkeypatch):
    class DeferredExecutor:
        def __init__(self):
            self.calls = []

        def submit(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    executor = DeferredExecutor()
    monkeypatch.setattr(agent_service, "_EXECUTOR", executor)
    monkeypatch.setattr(
        agent_service,
        "call_local_model_json",
        lambda *args, **kwargs: {
            "status": "ready",
            "capability_key": "order_quote",
            "fields": {"order_sn": "20260701-1"},
            "evidence": {"order_sn": "订单20260701-1"},
            "question": "",
        },
    )
    project, env = _agent_context()
    with TestClient(app) as client:
        headers = _login(client)
        created = client.post(
            "/api/data-scripts/agent/sessions",
            headers=headers,
            json={
                "project_id": project.id,
                "env_id": env.id,
                "instruction": "给订单20260701-1报价",
            },
        ).json()
        agent_service._SESSIONS[created["id"]].goal["operations"] = []
        response = client.post(
            f"/api/data-scripts/agent/sessions/{created['id']}/confirm",
            headers=headers,
            json={"plan_version": created["plan_version"]},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "目标合同没有可验证的注册操作"
    assert executor.calls == []


def test_metadata_missing_required_uses_server_question(monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "call_local_model_json",
        lambda *args, **kwargs: {
            "status": "clarifying",
            "capability_key": "order_quote",
            "fields": {},
            "evidence": {},
            "question": "请补充更多任务信息。",
        },
    )
    project, _ = _agent_context()
    db = SessionLocal()
    try:
        status_value, goal, question, trace = agent_service._analyze_turn(
            db,
            [{"role": "user", "content": "给订单报价"}],
            {},
            compile_context={"project_id": project.id},
        )
    finally:
        db.close()

    assert status_value == "clarifying"
    assert goal == {}
    assert question == "请提供订单号。"
    assert trace["capability_key"] == "order_quote"


def test_metadata_model_question_is_used_without_server_missing(monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "call_local_model_json",
        lambda *args, **kwargs: {
            "status": "clarifying",
            "capability_key": "order_quote",
            "fields": {"order_sn": "20260701-1"},
            "evidence": {"order_sn": "订单20260701-1"},
            "question": "请确认是否只做订单报价。",
        },
    )
    project, _ = _agent_context()
    db = SessionLocal()
    try:
        status_value, goal, question, _ = agent_service._analyze_turn(
            db,
            [{"role": "user", "content": "给订单20260701-1报价"}],
            {},
            compile_context={"project_id": project.id},
        )
    finally:
        db.close()

    assert status_value == "clarifying"
    assert goal == {}
    assert question == "请确认是否只做订单报价。"


def test_metadata_missing_required_never_falls_back_to_full_flow(monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "call_local_model_json",
        lambda *args, **kwargs: {
            "status": "clarifying",
            "capability_key": "order_quote",
            "fields": {},
            "evidence": {},
            "question": "",
        },
    )
    project, env = _agent_context()
    with TestClient(app) as client:
        headers = _login(client)
        created = client.post(
            "/api/data-scripts/agent/sessions",
            headers=headers,
            json={
                "project_id": project.id,
                "env_id": env.id,
                "instruction": "给订单报价",
            },
        ).json()
        latest = created
        for message in ("暂时没有单号", "还是没有单号"):
            latest = client.post(
                f"/api/data-scripts/agent/sessions/{created['id']}/messages",
                headers=headers,
                json={"message": message},
            ).json()

    assert latest["status"] == "clarifying"
    assert latest["capability_key"] == "order_quote"
    assert latest["goal"] == {}
    assert latest["question"] == "请提供订单号。"


def test_metadata_learning_is_limited_to_selected_capability(monkeypatch):
    proposal = {
        "signature": learning_service._candidate_signature(
            "target_node", "pending_purchase"
        ),
        "field": "target_node",
        "match_phrases": ["订单报价"],
        "set_fields": {"target_node": "pending_purchase"},
        "source_count": 3,
    }
    monkeypatch.setattr(
        agent_service,
        "call_local_model_json",
        lambda *args, **kwargs: {
            "status": "ready",
            "capability_key": "order_quote",
            "fields": {"order_sn": "20260701-1"},
            "evidence": {"order_sn": "订单20260701-1"},
            "question": "",
        },
    )
    monkeypatch.setattr(
        agent_service,
        "learning_context",
        lambda *args, **kwargs: {
            "module_key": "order",
            "rules": [
                {
                    "id": 92,
                    "scope": "project",
                    "rule": proposal,
                }
            ],
            "examples": [],
        },
    )
    project, _ = _agent_context()
    db = SessionLocal()
    try:
        status_value, goal, question, _ = agent_service._analyze_turn(
            db,
            [{"role": "user", "content": "给订单20260701-1报价"}],
            {},
            compile_context={"project_id": project.id},
        )
    finally:
        db.close()

    assert (status_value, question) == ("awaiting_confirmation", "")
    assert "target_node" not in goal
    assert "stop_after_node" not in goal["variables"]
    assert "learning_applied" not in goal


def test_allowed_metadata_learning_refreshes_contract_derivatives(monkeypatch):
    proposal = {
        "signature": learning_service._candidate_signature("keyword", "鞋子"),
        "field": "keyword",
        "match_phrases": ["加入购物车"],
        "set_fields": {"keyword": "鞋子"},
        "source_count": 3,
    }
    monkeypatch.setattr(
        agent_service,
        "call_local_model_json",
        lambda *args, **kwargs: {
            "status": "ready",
            "capability_key": "shopping_cart",
            "fields": {},
            "evidence": {},
            "question": "",
        },
    )
    monkeypatch.setattr(
        agent_service,
        "learning_context",
        lambda *args, **kwargs: {
            "module_key": "order",
            "rules": [{"id": 93, "scope": "project", "rule": proposal}],
            "examples": [],
        },
    )
    project, _ = _agent_context()
    db = SessionLocal()
    try:
        status_value, goal, question, _ = agent_service._analyze_turn(
            db,
            [{"role": "user", "content": "加入购物车"}],
            {},
            compile_context={"project_id": project.id},
        )
    finally:
        db.close()

    capability = capability_catalog()["shopping_cart"]
    normalized = normalize_execution_contract(goal, capability)
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    assert (status_value, question) == ("awaiting_confirmation", "")
    assert goal["variables"]["keyword"] == "鞋子"
    assert "鞋子" in goal["summary"]
    assert goal["contract_hash"] == hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:16]


def test_declared_metadata_learning_uses_contract_updates(monkeypatch):
    rules = []
    for index, (field, value) in enumerate(
        (("target_shops", 2), ("per_shop", 3)),
        start=94,
    ):
        rules.append(
            {
                "id": index,
                "scope": "project",
                "rule": {
                    "signature": learning_service._candidate_signature(field, value),
                    "field": field,
                    "match_phrases": ["加入购物车"],
                    "set_fields": {field: value},
                    "source_count": 3,
                },
            }
        )
    monkeypatch.setattr(
        agent_service,
        "call_local_model_json",
        lambda *args, **kwargs: {
            "status": "ready",
            "capability_key": "shopping_cart",
            "fields": {},
            "evidence": {},
            "question": "",
        },
    )
    monkeypatch.setattr(
        agent_service,
        "learning_context",
        lambda *args, **kwargs: {
            "module_key": "order",
            "rules": rules,
            "examples": [],
        },
    )
    project, _ = _agent_context()
    db = SessionLocal()
    try:
        status_value, goal, question, _ = agent_service._analyze_turn(
            db,
            [{"role": "user", "content": "加入购物车"}],
            {},
            compile_context={"project_id": project.id},
        )
    finally:
        db.close()

    assert (status_value, question) == ("awaiting_confirmation", "")
    assert goal["variables"]["target_shops"] == 2
    assert goal["variables"]["per_shop"] == 3
    assert {item["field"] for item in goal["learning_applied"]} == {
        "target_shops",
        "per_shop",
    }
    assert "目标店铺数2" in goal["summary"]
    assert "每店商品数3" in goal["summary"]


def test_problem_goods_metadata_learning_backwrites_all_declared_value_fields():
    capability = capability_catalog()["problem_goods"]
    updates = {
        "scope": "all_candidates",
        "item_index": 2,
        "quantity_refund_mode": "fixed",
        "quantity_refund_value": 2,
        "price_adjustment_mode": "fixed",
        "price_adjustment_value": "12.5",
        "freight_refund_mode": "all",
        "option_refund_mode": "all",
    }
    declared_value_fields = {
        field.name
        for field in effective_contract_fields(capability)
        if field.group == "problem_goods"
        and not field.readonly
        and field.learnable
        and field.learning_mode == "value"
    }
    assert set(updates) == declared_value_fields
    operation = {
        "id": "operation_problem_goods_1",
        "type": "problem_goods",
        "scope": "selected_item",
        "item_index": 1,
        "quantity_refund_mode": "keep",
        "quantity_refund_value": 0,
        "price_adjustment_mode": "keep",
        "price_adjustment_value": "0",
        "freight_refund_mode": "keep",
        "option_refund_mode": "keep",
    }
    goal = {
        "capability_key": "problem_goods",
        "mode": "resume_order",
        "order_sn": "2026071715475684-300001",
        "variables": {},
        "operations": [
            {"id": "operation_before", "type": "advance_order"},
            operation,
            {"id": "operation_after", "type": "audit_marker"},
        ],
    }
    rules = [
        {
            "id": index,
            "scope": "project",
            "rule": {
                "signature": learning_service._candidate_signature(field, value),
                "field": field,
                "match_phrases": ["处理问题产品"],
                "set_fields": {field: value},
                "source_count": 3,
            },
        }
        for index, (field, value) in enumerate(updates.items(), start=120)
    ]

    learned = agent_service._apply_approved_learning(
        goal,
        {"rules": rules, "examples": []},
        set(),
        capability,
    )

    learned_operation = learned["operations"][1]
    assert [item["id"] for item in learned["operations"]] == [
        "operation_before",
        "operation_problem_goods_1",
        "operation_after",
    ]
    assert len(learned["operations"]) == 3
    assert {
        name: learned_operation[name]
        for name in declared_value_fields
    } == updates
    projected = project_contract_goal(learned, capability)
    normalized = normalize_execution_contract(projected, capability)
    assert {name: normalized[name] for name in declared_value_fields} == updates
    assert all(
        f"{field.label}{updates[field.name]}" in learned["summary"]
        for field in effective_contract_fields(capability)
        if field.name in declared_value_fields
    )
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    assert learned["contract_hash"] == hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:16]


def test_legacy_problem_scope_learning_stays_projection_compatible():
    capability = capability_catalog()["problem_goods"]
    goal = {
        "capability_key": "problem_goods",
        "mode": "resume_order",
        "order_sn": "2026071715475684-300001",
        "variables": {"problem_scope": "item"},
        "operations": [{
            "id": "operation_problem_goods_1",
            "type": "problem_goods",
            "scope": "selected_item",
        }],
    }
    rule = {
        "signature": learning_service._candidate_signature("problem_scope", "all"),
        "field": "problem_scope",
        "match_phrases": ["处理问题产品"],
        "set_fields": {"problem_scope": "all"},
        "source_count": 3,
    }

    learned = agent_service._apply_approved_learning(
        goal,
        {"rules": [{"id": 130, "scope": "project", "rule": rule}]},
        set(),
        capability,
    )

    assert len(learned["operations"]) == 1
    assert learned["operations"][0]["id"] == "operation_problem_goods_1"
    assert learned["operations"][0]["scope"] == "all_candidates"
    projected = project_contract_goal(learned, capability)
    normalized = normalize_execution_contract(projected, capability)
    assert normalized["scope"] == "all_candidates"
    assert "处理范围all_candidates" in learned["summary"]
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    assert learned["contract_hash"] == hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:16]


def test_metadata_compiler_materializes_declared_defaults():
    capability = capability_catalog()["shopping_cart"]
    goal, rejected = compile_metadata_contract(capability, {}, {})
    normalized = normalize_execution_contract(goal, capability)
    defaults = {
        field.name: normalized[field.name]
        for field in effective_contract_fields(capability)
        if field.default is not None
    }

    assert rejected == []
    assert {
        name: goal["variables"][name]
        for name in defaults
    } == defaults
    assert goal["field_sources"] == {name: "default" for name in defaults}
    assert set(goal["inferred_fields"]) == set(defaults)
    assert goal["summary"]
    assert goal["contract_hash"]
    assert {
        field["name"]: field["value"]
        for field in build_contract_editor_schema(capability, goal)
        if field["name"] in defaults
    } == defaults


def test_core_capabilities_declare_contract_editor_fields():
    catalog = capability_catalog()
    declared = {
        key: {field.name: field for field in effective_contract_fields(catalog[key])}
        for key in (
            "full_flow",
            "resume_order_flow",
            "resume_porder_flow",
            "problem_goods",
        )
    }
    declared_legacy_fields = {
        "order_shop_count",
        "order_per_shop",
        "order_item_num",
        "offer_price",
        "target_node",
    }
    assert all(declared_legacy_fields <= fields.keys() for fields in declared.values())

    assert {
        "customer_ids",
        "target_node",
        "order_shop_count",
        "order_per_shop",
        "order_item_num",
        "offer_price",
        "order_payment_mode",
    } <= declared["full_flow"].keys()
    assert "order_sn" in declared["resume_order_flow"]
    assert {
        "porder_sn",
        "porder_payment_mode",
        "payment_fallback",
    } <= declared["resume_porder_flow"].keys()
    assert {
        "scope",
        "quantity_refund_mode",
        "quantity_refund_value",
        "price_adjustment_mode",
        "price_adjustment_value",
        "freight_refund_mode",
        "option_refund_mode",
    } <= declared["problem_goods"].keys()
    for fields in declared.values():
        for name in (
            "inferred_items",
            "operation_order",
            "plan_version",
            "contract_hash",
        ):
            assert fields[name].readonly is True
            assert fields[name].execution_field is False
            assert fields[name].learnable is False


def test_resume_porder_fallback_is_editable_and_part_of_contract_hash():
    capability = capability_catalog()["resume_porder_flow"]
    goal = {
        "mode": "resume_porder",
        "porder_sn": "PORDER-1001",
        "target_node": "porder_paid",
        "variables": {"porder_payment_mode": "balance_first"},
    }

    fallback = next(
        field
        for field in build_contract_editor_schema(capability, goal)
        if field["name"] == "payment_fallback"
    )
    assert fallback["value"] == "bank"
    assert fallback["readonly"] is False

    updated, _ = apply_contract_updates(
        goal, {"payment_fallback": "bank"}, capability
    )
    normalized = normalize_execution_contract(updated, capability)
    assert normalized["payment_fallback"] == "bank"
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    assert updated["contract_hash"] == hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:16]


def test_resolve_goal_capability_preserves_core_routing():
    assert resolve_goal_capability({"mode": "new"}) == "full_flow"
    assert resolve_goal_capability({"mode": "resume_order"}) == "resume_order_flow"
    assert resolve_goal_capability({"mode": "resume_porder"}) == "resume_porder_flow"
    assert resolve_goal_capability({
        "operations": [{"type": "problem_goods"}],
    }) == "problem_goods"
    assert resolve_goal_capability({
        "capability_key": "resume_porder_flow",
        "mode": "new",
    }) == "resume_porder_flow"
    assert resolve_goal_capability({
        "mode": "resume_order",
        "operations": [{"type": "problem_goods"}],
    }) == "problem_goods"


def test_resolve_goal_capability_requires_matching_legacy_scope():
    assert resolve_goal_capability(
        {},
        module_key="unknown_module",
        intent_key="resume_order",
    ) == ""


def test_project_contract_goal_backfills_problem_operation_without_mutating_source():
    capability = capability_catalog()["problem_goods"]
    goal = {
        "mode": "resume_order",
        "variables": {"order_item_num": 1},
        "operations": [{
            "type": "problem_goods",
            "scope": "selected_item",
            "quantity_refund_mode": "all",
            "price_adjustment_mode": "fixed",
            "price_adjustment_value": "12.5",
            "freight_refund_mode": "all",
        }],
    }

    projected = project_contract_goal(goal, capability, plan_version=3)

    assert projected["variables"] == {
        "order_item_num": 1,
        "scope": "selected_item",
        "quantity_refund_mode": "all",
        "price_adjustment_mode": "fixed",
        "price_adjustment_value": "12.5",
        "freight_refund_mode": "all",
    }
    assert projected["plan_version"] == 3
    assert goal["variables"] == {"order_item_num": 1}


def test_minimal_new_order_uses_confirmed_business_defaults():
    result = compile_contract_defaults(
        mode="new",
        target_node="",
        variables={},
        explicit_customer_ids=[],
        context={"topbar_customer_ids": [], "bound_customer_ids": ["300001"]},
    )
    assert result.target_node == "order_offered"
    assert result.customer_ids == ["300001"]
    assert result.customer_source == "bound_account"
    assert result.variables == {
        "keyword": "衣服",
        "shop_type": "1688",
        "order_shop_count": 1,
        "order_per_shop": 1,
        "order_item_num": 1,
        "offer_price": "10",
        "order_payment_mode": "balance_first",
        "payment_fallback": "bank",
    }
    assert set(result.defaults_used) == {
        "target_node", "customer_ids", "keyword", "shop_type", "order_shop_count",
        "order_per_shop", "order_item_num", "offer_price", "order_payment_mode",
        "payment_fallback",
    }


def test_resume_order_does_not_receive_new_order_defaults():
    result = compile_contract_defaults(
        mode="resume_order",
        target_node="",
        variables={"order_sn": "2026071715475684-300001"},
        explicit_customer_ids=[],
        context={"bound_customer_ids": ["300002"]},
    )
    assert result.target_node == ""
    assert result.variables == {"order_sn": "2026071715475684-300001"}


def test_normalize_goal_applies_compiled_new_order_defaults_before_clarifying():
    status, goal, question = agent_service._normalize_goal(
        {"status": "ready", "goal": {"mode": "new", "variables": {}}},
        [{"role": "user", "content": "帮我造一个订单"}],
        compile_context={"bound_customer_ids": ["300001"]},
    )

    assert (status, question) == ("awaiting_confirmation", "")
    assert goal["target_node"] == "order_offered"
    assert goal["customer_ids"] == ["300001"]
    assert goal["customer_source"] == "bound_account"
    assert {
        key: goal["variables"][key]
        for key in (
            "keyword",
            "shop_type",
            "order_shop_count",
            "order_per_shop",
            "order_item_num",
            "offer_price",
            "order_payment_mode",
            "payment_fallback",
        )
    } == {
        "keyword": "衣服",
        "shop_type": "1688",
        "order_shop_count": 1,
        "order_per_shop": 1,
        "order_item_num": 1,
        "offer_price": "10",
        "order_payment_mode": "balance_first",
        "payment_fallback": "bank",
    }
    assert set(goal["defaults_used"]) == {
        "target_node", "customer_ids", "keyword", "shop_type", "order_shop_count",
        "order_per_shop", "order_item_num", "offer_price", "order_payment_mode",
        "payment_fallback",
    }


def test_normalize_goal_preserves_explicit_model_target_clarification():
    status, goal, question = agent_service._normalize_goal(
        {"status": "clarifying", "question": "最终要到哪个状态？", "goal": {}},
        [{"role": "user", "content": "帮我造个订单"}],
    )

    assert status == "clarifying"
    assert goal == {}
    assert question == "最终要到哪个状态？"


def test_normalize_goal_does_not_default_an_invalid_model_target():
    status, goal, question = agent_service._normalize_goal(
        {"status": "ready", "goal": {"target_node": "not_a_real_node", "variables": {}}},
        [{"role": "user", "content": "帮我造个订单"}],
    )

    assert status == "clarifying"
    assert goal == {}
    assert "最终" in question


def test_two_fan_goods_is_item_count_not_problem_item_selection():
    state = reduce_intent_fields({}, "造一个2番商品的订单，每个数量1，到待拍下后处理全部问题产品")

    fields = state["resolved_fields"]
    assert fields["item_count"]["value"] == 2
    assert "item_index" not in fields
    assert fields["problem_scope"]["value"] == "all"


def test_problem_goods_all_refund_keeps_unit_price():
    state = reduce_intent_fields({}, "两番都处理问题产品，全部退")

    fields = state["resolved_fields"]
    assert fields["problem_scope"]["value"] == "all"
    assert fields["problem_refund_quantity"]["value"] == "all"
    assert fields["problem_refund_freight"]["value"] == "all"
    assert fields["problem_preserve_price"]["value"] is True


def test_existing_order_unit_price_zero_does_not_request_shape():
    payload = {
        "status": "ready",
        "goal": {
            "mode": "resume_order",
            "order_sn": "2026071715475684-300001",
            "target_node": "",
            "variables": {},
            "operations": [{"type": "problem_goods", "evidence": "第1番单价改成0"}],
            "intent": {"pricing": {"mode": "uniform_unit", "amount": "0", "evidence": "单价改成0"}},
        },
    }

    status, goal, question = agent_service._normalize_goal(
        payload,
        [{"role": "user", "content": "订单2026071715475684-300001第1番提出问题产品，单价改成0"}],
    )

    assert status == "awaiting_confirmation"
    assert "商品种类数" not in question
    assert "购买数量" not in question
    assert goal["mode"] == "resume_order"


def test_multi_product_problem_goods_without_scope_asks_exact_scope_question():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "new",
                "target_node": "pending_purchase",
                "variables": {},
            },
        },
        [{"role": "user", "content": "造一个2番商品的订单，每个数量1，到待拍下后提出问题产品，数量全部退"}],
    )

    assert status == "clarifying"
    assert goal == {}
    assert question == "订单包含多个商品，请说明处理第几番或全部商品。"


@pytest.mark.parametrize("scope_text", ["第1番", "全部商品"])
def test_selected_problem_scope_without_change_asks_exact_change_question(scope_text):
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "new",
                "target_node": "pending_purchase",
                "variables": {},
            },
        },
        [{"role": "user", "content": f"造一个2番商品的订单，每个数量1，到待拍下后处理{scope_text}问题产品"}],
    )

    assert status == "clarifying"
    assert goal == {}
    assert question == "请说明问题产品需要修改数量、单价或国内运费，以及目标值。"


def test_explicit_third_fan_resolves_problem_item_three():
    state = reduce_intent_fields({}, "第3番提出问题产品，数量全部退")

    fields = state["resolved_fields"]
    assert fields["item_index"]["value"] == 3
    assert fields["problem_scope"]["value"] == "item"


def test_explicit_problem_quantity_and_freight_zero_survive_normalization():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "resume_order",
                "order_sn": "2026071715475684-300001",
                "variables": {},
            },
        },
        [{
            "role": "user",
            "content": "订单2026071715475684-300001第1番提出问题产品，数量改成0，国内运费改成0",
        }],
    )

    assert (status, question) == ("awaiting_confirmation", "")
    problem = goal["operations"][0]
    assert problem["scope"] == "selected_item"
    assert problem["item_index"] == 1
    assert problem["quantity_refund_mode"] == "all"
    assert problem["freight_refund_mode"] == "all"
    assert problem["price_adjustment_mode"] == "keep"


def test_follow_up_all_scope_clears_only_scope_pending_and_preserves_facts():
    state = {
        "resolved_fields": {
            "order_sn": {"value": "2026071715475684-300001", "evidence": "订单2026071715475684-300001"},
            "pricing": {"value": {"mode": "uniform_unit", "amount": "0"}, "evidence": "单价改成0"},
        },
        "pending_fields": {
            "problem_scope": {"question": "订单包含多个商品，请说明处理第几番或全部商品。"},
            "permission": {"question": "确认执行？"},
        },
        "turn_count": 1,
    }

    updated = reduce_intent_fields(state, "全部处理")

    assert updated["resolved_fields"]["problem_scope"]["value"] == "all"
    assert updated["resolved_fields"]["order_sn"]["value"] == "2026071715475684-300001"
    assert updated["resolved_fields"]["pricing"]["value"]["amount"] == "0"
    assert "problem_scope" not in updated["pending_fields"]
    assert "permission" in updated["pending_fields"]


def test_follow_up_unit_price_zero_overrides_earlier_full_refund_price_preservation():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "resume_order",
                "order_sn": "2026071715475684-300001",
                "variables": {},
            },
        },
        [
            {
                "role": "user",
                "content": "订单2026071715475684-300001第1番提出问题产品，全部退",
            },
            {"role": "user", "content": "单价改成0"},
        ],
    )

    assert (status, question) == ("awaiting_confirmation", "")
    problem = goal["operations"][0]
    assert problem["quantity_refund_mode"] == "all"
    assert problem["freight_refund_mode"] == "all"
    assert problem["price_adjustment_mode"] == "zero"


def test_problem_goods_filter_keeps_unhandled_mixed_request():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "resume_order",
                "order_sn": "2026071715475684-300001",
                "variables": {},
                "unhandled_requests": ["报价后修改收货地址"],
            },
        },
        [{
            "role": "user",
            "content": "订单2026071715475684-300001第1番提出问题产品，数量改成0，报价后修改收货地址",
        }],
    )

    assert status == "clarifying"
    assert goal == {}
    assert "报价后修改收货地址" in question


def test_selected_problem_item_with_valid_index_satisfies_scope_gate():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "resume_order",
                "order_sn": "2026071715475684-300001",
                "variables": {},
            },
        },
        [{
            "role": "user",
            "content": "订单2026071715475684-300001，2番提出问题产品，单价改成0",
        }],
    )

    assert (status, question) == ("awaiting_confirmation", "")
    problem = goal["operations"][0]
    assert problem["scope"] == "selected_item"
    assert problem["item_index"] == 2


def test_problem_goods_filter_keeps_unknown_clause_after_supported_clause():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "resume_order",
                "order_sn": "2026071715475684-300001",
                "variables": {},
                "unhandled_requests": ["提出问题产品后修改收货地址"],
            },
        },
        [{
            "role": "user",
            "content": "订单2026071715475684-300001第1番提出问题产品，数量改成0，提出问题产品后修改收货地址",
        }],
    )

    assert status == "clarifying"
    assert goal == {}
    assert "修改收货地址" in question


def test_new_order_selected_second_item_passes_late_scope_gate():
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "new",
                "target_node": "pending_purchase",
                "variables": {},
            },
        },
        [{
            "role": "user",
            "content": "造一个2番商品的订单，每个数量1，到待拍下后第2番提出问题产品，数量改成0",
        }],
    )

    assert (status, question) == ("awaiting_confirmation", "")
    problem = goal["operations"][1]
    assert problem["scope"] == "selected_item"
    assert problem["item_index"] == 2


@pytest.mark.parametrize(
    ("instruction", "unhandled"),
    [
        ("退一半", "退一半"),
        ("退款2件", "退款2件"),
        ("退一半，国内运费保持不变", "国内运费保持不变"),
        ("数量不退，单价改成0", "数量不退"),
        ("只退国内运费", "只退国内运费"),
        ("退款全部国内运费", "退款全部国内运费"),
        ("退一半，附加服务全退", "附加服务全退"),
        ("退一半，附加服务都退", "附加服务都退"),
        ("退一半，附加服务全部退光", "附加服务全部退光"),
        ("退一半，附加服务清零", "附加服务清零"),
    ],
)
def test_supported_problem_expression_does_not_remain_unhandled(instruction, unhandled):
    status, goal, question = agent_service._normalize_goal(
        {
            "status": "ready",
            "goal": {
                "mode": "resume_order",
                "order_sn": "2026071715475684-300001",
                "variables": {},
                "unhandled_requests": [unhandled],
            },
        },
        [{
            "role": "user",
            "content": f"订单2026071715475684-300001第1番提出问题产品，{instruction}",
        }],
    )

    assert (status, question) == ("awaiting_confirmation", "")
    assert goal["operations"][0]["type"] == "problem_goods"
