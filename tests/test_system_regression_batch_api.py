from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Env, TestAccountProfile
from app.routers import system_regression as regression_router_module
from app.routers.system_regression import router
from app.security import require_admin
from app.system_regression.models import SystemRegressionBatch, SystemRegressionCaseRun
from app.core.account_utils import encrypt_account_payload


LEGACY_RUN_FIELDS = {
    "id",
    "batch_id",
    "case_id",
    "case_key",
    "case_version",
    "source_run_id",
    "status",
    "resume_stage",
    "order_sn",
    "sorting",
    "porder_sn",
    "problem_goods_id",
    "expected",
    "preview",
    "actual",
    "result",
    "error_code",
    "error_message",
}


@pytest.fixture()
def api_context(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=99, role="admin")
    queued_batches = []
    queued_resumes = []
    monkeypatch.setattr(regression_router_module, "queue_batch_execution", lambda batch_id: queued_batches.append(batch_id))
    monkeypatch.setattr(
        regression_router_module,
        "queue_account_resume",
        lambda run_id, username, password: queued_resumes.append((run_id, username, password)),
    )
    seed_session = session_factory()
    seed_session.add(
        Env(
            id=1,
            project_id=1,
            env_name="JP",
            base_url="https://jpapi.rakumart.cn",
            global_headers="{}",
            global_vars="{}",
            timeout=30,
        )
    )
    seed_session.add(
        TestAccountProfile(
            project_id=None,
            profile_name="沈文妮账号",
            variables=json.dumps({"username": "Y002"}, ensure_ascii=False),
            sensitive_variables=encrypt_account_payload({"password": "secret-pass"}),
            status="active",
            create_time=datetime.now(),
        )
    )
    seed_session.commit()
    seed_session.close()
    try:
        with TestClient(app) as client:
            yield client, session_factory, queued_batches, queued_resumes
    finally:
        Base.metadata.drop_all(bind=engine)


def test_create_and_get_batch_returns_immediately_with_runs(api_context):
    client, _session_factory, queued, _resumes = api_context
    cases = client.get("/api/system-regression/suites/japan/cases?category=payment").json()["cases"][:2]

    response = client.post(
        "/api/system-regression/batches",
        json={
            "suite_key": "japan",
            "case_ids": [row["id"] for row in cases],
            "project_id": 1,
            "env_id": 1,
            "context": {"variables": {"customer_id": 3}},
        },
    )

    assert response.status_code == 202
    batch = response.json()
    assert batch["status"] == "pending"
    assert batch["total_count"] == 2
    assert queued == [batch["id"]]

    detail = client.get(f"/api/system-regression/batches/{batch['id']}")
    assert detail.status_code == 200
    assert [row["case_key"] for row in detail.json()["runs"]] == [row["case_key"] for row in cases]
    for run in detail.json()["runs"]:
        assert LEGACY_RUN_FIELDS <= set(run)
        assert run["execution_id"]
        assert run["reason_code"] == ""


@pytest.mark.parametrize("run_status", ["pending", "waiting_account", "blocked", "failed", "passed"])
def test_historical_empty_run_serializes_without_changing_legacy_fields(api_context, run_status):
    client, session_factory, _queued, _resumes = api_context
    case = client.get("/api/system-regression/suites/japan/cases").json()["cases"][0]
    batch = client.post(
        "/api/system-regression/batches",
        json={"suite_key": "japan", "case_ids": [case["id"]], "project_id": 1, "env_id": 1, "context": {"variables": {"customer_id": "300001"}}},
    ).json()
    session = session_factory()
    run = session.query(SystemRegressionCaseRun).filter_by(batch_id=batch["id"]).one()
    run.status = run_status
    run.snapshot_json = "{}"
    run.result_json = "{}"
    run.expected_json = "{}"
    run.preview_json = "{}"
    run.actual_json = "{}"
    run.error_code = None
    run.error_message = None
    session.commit()
    run_id = run.id
    session.close()

    payload = client.get(f"/api/system-regression/batches/{batch['id']}").json()["runs"][0]

    assert payload["id"] == run_id
    assert payload["status"] == run_status
    assert payload["expected"] == {}
    assert payload["preview"] == {}
    assert payload["actual"] == {}
    assert payload["result"] == {}
    assert payload["error_code"] == ""
    assert payload["error_message"] == ""
    assert payload["execution_id"] == ""
    assert payload["reason_code"] == ""
    assert payload["structured_evidence"] == {}


def test_structured_guard_fields_are_additive_and_legacy_values_are_unchanged(api_context):
    import json

    client, session_factory, _queued, _resumes = api_context
    case = client.get("/api/system-regression/suites/japan/cases").json()["cases"][0]
    batch = client.post(
        "/api/system-regression/batches",
        json={"suite_key": "japan", "case_ids": [case["id"]], "project_id": 1, "env_id": 1, "context": {"variables": {"customer_id": "300001"}}},
    ).json()
    session = session_factory()
    run = session.query(SystemRegressionCaseRun).filter_by(batch_id=batch["id"]).one()
    run.status = "failed"
    run.error_code = "legacy-code"
    run.result_json = json.dumps(
        {
            "reason_code": "backend_guard_missing",
            "guard_kind": "option_price_type_change",
            "expected_stage": "option_update",
            "actual_stage": "option_update",
            "actor": {"role": "normal"},
            "purchase_record_ids": ["701"],
            "failure_reason": "guard missing",
            "before_evidence": {},
            "after_evidence": {},
        }
    )
    session.commit()
    session.close()

    payload = client.get(f"/api/system-regression/batches/{batch['id']}").json()["runs"][0]

    assert LEGACY_RUN_FIELDS <= set(payload)
    assert payload["status"] == "failed"
    assert payload["error_code"] == "legacy-code"
    assert payload["reason_code"] == "backend_guard_missing"
    assert payload["structured_evidence"]["expected_stage"] == "option_update"
    assert payload["structured_evidence"]["actor"] == {"role": "normal"}


def test_problem_structured_evidence_fields_are_serialized_additively(api_context):
    client, session_factory, _queued, _resumes = api_context
    case = client.get("/api/system-regression/suites/japan/cases").json()["cases"][0]
    batch = client.post(
        "/api/system-regression/batches",
        json={"suite_key": "japan", "case_ids": [case["id"]], "project_id": 1, "env_id": 1, "context": {"variables": {"customer_id": "300001"}}},
    ).json()
    session = session_factory()
    run = session.query(SystemRegressionCaseRun).filter_by(batch_id=batch["id"]).one()
    run.status = "passed"
    run.result_json = json.dumps(
        {
            "write_state": "confirmed_written",
            "side_effects": {"payment_executed": False},
            "stage_evidence": {
                "expected_stage": "problem_goods_completed",
                "actual_stage": "problem_goods_completed",
                "stage_matched": True,
            },
            "reconciliation": {"passed": True, "reason_code": "ok"},
        }
    )
    session.commit()
    session.close()

    payload = client.get(f"/api/system-regression/batches/{batch['id']}").json()["runs"][0]

    assert LEGACY_RUN_FIELDS <= set(payload)
    assert payload["structured_evidence"]["write_state"] == "confirmed_written"
    assert payload["structured_evidence"]["side_effects"] == {"payment_executed": False}
    assert payload["structured_evidence"]["stage_evidence"]["stage_matched"] is True
    assert payload["structured_evidence"]["reconciliation"] == {"passed": True, "reason_code": "ok"}


def test_stop_and_rerun_endpoints(api_context):
    client, _session_factory, queued, _resumes = api_context
    case = client.get("/api/system-regression/suites/japan/cases").json()["cases"][0]
    batch = client.post(
        "/api/system-regression/batches",
        json={"suite_key": "japan", "case_ids": [case["id"]], "project_id": 1, "env_id": 1, "context": {"variables": {"customer_id": "300001"}}},
    ).json()
    detail = client.get(f"/api/system-regression/batches/{batch['id']}").json()
    source_run = detail["runs"][0]

    stopped = client.post(f"/api/system-regression/batches/{batch['id']}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"

    rerun = client.post(f"/api/system-regression/runs/{source_run['id']}/rerun")
    assert rerun.status_code == 202
    assert rerun.json()["source_run_id"] == source_run["id"]
    assert queued[-1] == batch["id"]


def test_resume_account_accepts_password_but_never_returns_or_persists_it(api_context):
    client, session_factory, _queued, resumes = api_context
    case = client.get("/api/system-regression/suites/japan/cases").json()["cases"][0]
    batch = client.post(
        "/api/system-regression/batches",
        json={"suite_key": "japan", "case_ids": [case["id"]], "project_id": 1, "env_id": 1, "context": {"variables": {"customer_id": "300001"}}},
    ).json()
    session = session_factory()
    run = session.query(SystemRegressionCaseRun).filter_by(batch_id=batch["id"]).one()
    run.status = "waiting_account"
    run.resume_stage = "purchase_process"
    session.commit()
    run_id = run.id
    session.close()

    response = client.post(
        f"/api/system-regression/runs/{run_id}/resume-account",
        json={"username": "manual-user", "password": "secret-pass"},
    )

    assert response.status_code == 202
    assert "secret-pass" not in response.text
    assert "password" not in response.text.lower()
    assert resumes == [(run_id, "manual-user", "secret-pass")]
    session = session_factory()
    persisted = session.get(SystemRegressionCaseRun, run_id)
    assert "secret-pass" not in " ".join([persisted.snapshot_json, persisted.result_json, persisted.error_message or ""])
    session.close()


def test_contextual_runner_resolves_customer_login_in_memory(monkeypatch):
    resolved_calls = []
    executed_contexts = []

    def resolve_variables(_db, *, project_id, env_id, context, suite_key="japan"):
        resolved_calls.append((dict(context.get("variables") or {}), project_id, env_id, suite_key))
        return SimpleNamespace(
            variables={
                **dict(context.get("variables") or {}),
                "account": "userID/300001In",
                "password": "runtime-only-password",
                "api_paths": {"client_login": "/client/login"},
            },
            precondition_evidence={"credential_source": "customer_id"},
            login_context={"kind": "customer_frontend", "credential_source": "customer_id"},
        )

    class FakeRunner:
        def execute(self, _case, context):
            executed_contexts.append(context)
            return "executed"

    monkeypatch.setattr(regression_router_module, "resolve_system_regression_login_context", resolve_variables)
    monkeypatch.setattr(regression_router_module, "_build_japan_runner", lambda _env, _db, _project_id: FakeRunner())
    stored_context = {"variables": {"customer_id": "300001"}}

    runner = regression_router_module._build_contextual_japan_runner(
        SimpleNamespace(id=1),
        object(),
        1,
        stored_context,
    )
    result = runner({}, {"variables": {"customer_id": "300001", "backend_account": "temporary"}})
    second = runner({}, {"variables": {"customer_id": "300001"}})

    assert result == "executed"
    assert second == "executed"
    assert resolved_calls == [({"customer_id": "300001"}, 1, 1, "japan")]
    first_vars = executed_contexts[0]["variables"]
    assert first_vars["customer_id"] == "300001"
    assert first_vars["account"] == "userID/300001In"
    assert first_vars["password"] == "runtime-only-password"
    assert first_vars["api_paths"] == {"client_login": "/client/login"}
    assert first_vars["backend_account"] == "temporary"
    assert first_vars["follow_delay"] == 0.8
    assert first_vars["_runtime"] is executed_contexts[1]["variables"]["_runtime"]
    assert stored_context == {"variables": {"customer_id": "300001"}}


def test_batch_creation_blocks_before_enqueue_when_login_credentials_are_missing(api_context):
    client, session_factory, queued, _resumes = api_context
    case = client.get("/api/system-regression/suites/japan/cases").json()["cases"][0]
    response = client.post(
        "/api/system-regression/batches",
        json={
            "suite_key": "japan",
            "case_ids": [case["id"]],
            "project_id": 1,
            "env_id": 1,
            "context": {"variables": {}, "system_regression_login": {"kind": "backend"}},
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "client_credentials_missing"
    assert payload["precondition_evidence"]["account_present"] is False
    assert payload["precondition_evidence"]["admin_identity_present"] is True
    assert payload["precondition_evidence"]["password_present"] is False
    assert queued == []
    session = session_factory()
    assert session.query(SystemRegressionBatch).count() == 0
    session.close()


def test_batch_creation_persists_safe_login_hint_without_plain_password(api_context):
    client, session_factory, queued, _resumes = api_context
    case = client.get("/api/system-regression/suites/japan/cases").json()["cases"][0]
    response = client.post(
        "/api/system-regression/batches",
        json={"suite_key": "japan", "case_ids": [case["id"]], "project_id": 1, "env_id": 1, "context": {"variables": {"customer_id": "300001"}}},
    )

    assert response.status_code == 202
    batch = response.json()
    assert queued == [batch["id"]]
    session = session_factory()
    stored = session.get(SystemRegressionBatch, batch["id"])
    assert stored is not None
    assert "secret-pass" not in stored.context_json
    assert "password" not in stored.context_json.lower()
    assert "system_regression_login" in stored.context_json
    session.close()


def test_list_batches_returns_newest_first_without_runs(api_context):
    client, _session_factory, queued, _resumes = api_context
    case = client.get("/api/system-regression/suites/japan/cases").json()["cases"][0]
    payload = {
        "suite_key": "japan",
        "case_ids": [case["id"]],
        "project_id": 1,
        "env_id": 1,
        "context": {"variables": {"customer_id": "300001"}},
    }
    first = client.post("/api/system-regression/batches", json=payload).json()
    second = client.post("/api/system-regression/batches", json=payload).json()

    response = client.get("/api/system-regression/batches?suite_key=japan&limit=20")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [row["id"] for row in items[:2]] == [second["id"], first["id"]]
    assert "runs" not in items[0]
    assert items[0]["batch_no"] == second["batch_no"]
    assert items[0]["create_time"]
    assert queued == [first["id"], second["id"]]
