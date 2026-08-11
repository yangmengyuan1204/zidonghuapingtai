from __future__ import annotations

import json
from datetime import datetime

import app.core.utils  # noqa: F401
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.account_utils import encrypt_account_payload
from app.database import Base, get_db
from app.models import Env, TestAccountProfile as AccountProfileModel
from app.routers import system_regression as regression_router
from app.security import require_admin
from app.services.system_regression.case_service import ensure_japan_suite
from app.services.system_regression.account_service import minister_account_context
from app.services.system_regression.batch_service import create_batch, execute_batch
from app.system_regression.projects.japan.runner import CaseRunResult
from app.services.system_regression.login_context import (
    SystemRegressionLoginContextError,
    resolve_system_regression_login_context,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


ADMIN_IDENTITY = "admin"
CLIENT_IDENTITY = "client"


@pytest.fixture()
def dual_identity_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    db.add(
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
    admin = AccountProfileModel(
        id=10,
        profile_name="后台 Y002",
        variables=json.dumps({"username": "Y002"}, ensure_ascii=False),
        sensitive_variables=encrypt_account_payload({"password": "admin-secret"}),
        status="active",
        create_time=datetime.now(),
    )
    client = AccountProfileModel(
        id=11,
        profile_name="前台客户",
        variables=json.dumps({"account": "client-account"}, ensure_ascii=False),
        sensitive_variables=encrypt_account_payload({"password": "client-secret"}),
        status="active",
        create_time=datetime.now(),
    )
    db.add_all([admin, client])
    db.commit()
    ensure_japan_suite(db)
    try:
        yield db, factory, admin, client
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_admin_and_client_profiles_are_separate_namespaces(dual_identity_db):
    db, _factory, admin, client = dual_identity_db
    resolution = resolve_system_regression_login_context(
        db,
        project_id=1,
        env_id=1,
        context={
            "variables": {},
            "system_regression_login": {
                "admin_profile_id": admin.id,
                "client_profile_id": client.id,
            },
        },
        required_identities=(ADMIN_IDENTITY, CLIENT_IDENTITY),
    )

    assert resolution.identity_context.admin.present is True
    assert resolution.identity_context.client.present is True
    assert resolution.variables["backend_account"] == "Y002"
    assert resolution.variables["account"] == "client-account"
    assert resolution.variables["backend_password"] == "admin-secret"
    assert resolution.variables["password"] == "client-secret"
    assert resolution.variables["backend_account"] != resolution.variables["account"]
    assert resolution.login_context["admin"]["route"] == "/admin.login"
    assert resolution.login_context["client"]["route"] == "/client/userLogin"


def test_admin_username_is_never_inferred_as_client_account(dual_identity_db):
    db, _factory, admin, _client = dual_identity_db
    with pytest.raises(SystemRegressionLoginContextError) as exc:
        resolve_system_regression_login_context(
            db,
            project_id=1,
            env_id=1,
            context={"variables": {}, "system_regression_login": {"admin_profile_id": admin.id}},
            required_identities=(CLIENT_IDENTITY,),
        )

    assert exc.value.reason_code == "client_credentials_missing"
    assert exc.value.precondition_evidence["admin_identity_present"] is True
    assert exc.value.precondition_evidence["client_identity_present"] is False


def test_minister_profile_username_is_bound_to_admin_namespace(dual_identity_db):
    db, _factory, admin, _client = dual_identity_db
    admin.profile_name = "沈文妮"
    db.commit()
    values = minister_account_context(db, project_id=1, refund_cny="500")
    assert values["backend_account"] == "Y002"
    assert values["backend_password"] == "admin-secret"
    assert "account" not in values


def test_frontend_profile_must_contain_explicit_account(dual_identity_db):
    db, _factory, admin, client = dual_identity_db
    client.variables = json.dumps({"username": "frontend-username"}, ensure_ascii=False)
    db.commit()
    with pytest.raises(SystemRegressionLoginContextError) as exc:
        resolve_system_regression_login_context(
            db,
            project_id=1,
            env_id=1,
            context={
                "variables": {},
                "system_regression_login": {"admin_profile_id": admin.id, "client_profile_id": client.id},
            },
            required_identities=(CLIENT_IDENTITY,),
        )
    assert exc.value.reason_code == "client_credentials_missing"


def test_explicit_credentials_override_selected_profiles(dual_identity_db):
    db, _factory, admin, client = dual_identity_db
    resolution = resolve_system_regression_login_context(
        db,
        project_id=1,
        env_id=1,
        context={
            "variables": {
                "backend_account": "explicit-admin",
                "backend_password": "explicit-admin-pass",
                "account": "explicit-client",
                "password": "explicit-client-pass",
                "client_tool": "2",
            },
            "system_regression_login": {"admin_profile_id": admin.id, "client_profile_id": client.id},
        },
        required_identities=(ADMIN_IDENTITY, CLIENT_IDENTITY),
    )
    assert resolution.variables["backend_account"] == "explicit-admin"
    assert resolution.variables["account"] == "explicit-client"
    assert resolution.variables["client_tool"] == "2"
    assert resolution.precondition_evidence["admin_credential_source"] == "explicit_admin"
    assert resolution.precondition_evidence["client_credential_source"] == "explicit_account"


def test_customer_id_is_an_explicit_client_identity_source(dual_identity_db):
    db, _factory, admin, _client = dual_identity_db
    resolution = resolve_system_regression_login_context(
        db,
        project_id=1,
        env_id=1,
        context={
            "variables": {"customer_id": "300001"},
            "system_regression_login": {"admin_profile_id": admin.id},
        },
        required_identities=(ADMIN_IDENTITY, CLIENT_IDENTITY),
    )
    assert resolution.variables["account"] == "userID/300001In"
    assert resolution.precondition_evidence["client_credential_source"] == "customer_id"


@pytest.mark.parametrize(
    ("required", "available", "status", "reason"),
    [
        ((ADMIN_IDENTITY,), {ADMIN_IDENTITY}, "passed", ""),
        ((CLIENT_IDENTITY,), {CLIENT_IDENTITY}, "passed", ""),
        ((), set(), "passed", ""),
        ((ADMIN_IDENTITY, CLIENT_IDENTITY), {ADMIN_IDENTITY}, "blocked", "client_credentials_missing"),
        ((ADMIN_IDENTITY, CLIENT_IDENTITY), {CLIENT_IDENTITY}, "blocked", "admin_credentials_missing"),
        ((ADMIN_IDENTITY, CLIENT_IDENTITY), set(), "blocked", "admin_and_client_credentials_missing"),
    ],
)
def test_identity_requirement_preflight_matrix(required, available, status, reason):
    from app.services.system_regression.login_context import validate_identity_requirements

    result = validate_identity_requirements(
        [{"case_key": "CASE", "expectation": {"required_identities": list(required)}}],
        available_identities=available,
    )
    assert result.status == status
    assert result.reason_code == reason


def test_identity_tokens_never_cross_or_persist_in_execution_variables(dual_identity_db):
    db, _factory, admin, client = dual_identity_db
    resolution = resolve_system_regression_login_context(
        db,
        project_id=1,
        env_id=1,
        context={
            "variables": {
                "admin_token": "admin-token",
                "client_token": "client-token",
            },
            "system_regression_login": {"admin_profile_id": admin.id, "client_profile_id": client.id},
        },
        required_identities=(ADMIN_IDENTITY, CLIENT_IDENTITY),
    )
    assert "admin_token" not in resolution.variables
    assert "client_token" not in resolution.variables
    assert resolution.identity_context.admin.token == ""
    assert resolution.identity_context.client.token == ""


def test_identity_context_has_safe_metadata_only(dual_identity_db):
    db, _factory, admin, client = dual_identity_db
    resolution = resolve_system_regression_login_context(
        db,
        project_id=1,
        env_id=1,
        context={
            "variables": {},
            "system_regression_login": {"admin_profile_id": admin.id, "client_profile_id": client.id},
        },
        required_identities=(ADMIN_IDENTITY, CLIENT_IDENTITY),
    )
    serialized = json.dumps(resolution.login_context, ensure_ascii=False)
    assert "admin-secret" not in serialized
    assert "client-secret" not in serialized
    assert resolution.login_context["admin"]["present"] is True
    assert resolution.login_context["client"]["present"] is True


def test_system_regression_routes_are_identity_specific():
    from app.services.system_regression.login_context import ADMIN_LOGIN_PATH, CLIENT_LOGIN_PATH

    assert ADMIN_LOGIN_PATH == "/admin.login"
    assert CLIENT_LOGIN_PATH == "/client/userLogin"
    assert ADMIN_LOGIN_PATH != CLIENT_LOGIN_PATH


def test_batch_result_persists_identity_type_from_case_snapshot(dual_identity_db):
    db, _factory, _admin, _client = dual_identity_db
    case = db.query(regression_router.SystemRegressionCase).filter_by(case_key="JP-PAY-001").one()
    batch = create_batch(
        db,
        suite_key="japan",
        case_ids=[case.id],
        project_id=1,
        env_id=1,
        actor_id=1,
        context={},
    )
    execute_batch(db, batch.id, runner=lambda _case, _context: CaseRunResult(status="failed"))
    run = db.query(regression_router.SystemRegressionCaseRun).filter_by(batch_id=batch.id).one()
    assert json.loads(run.result_json)["identity_type"] == [ADMIN_IDENTITY, CLIENT_IDENTITY]


def test_case_catalog_declares_all_japan_cases_as_both(dual_identity_db):
    db, _factory, _admin, _client = dual_identity_db
    cases = regression_router.list_cases(db, suite_key="japan")
    assert len(cases) == 77
    assert {tuple(case.expectation.get("required_identities") or []) for case in cases} == {
        (ADMIN_IDENTITY, CLIENT_IDENTITY)
    }


def test_unknown_identity_requirement_is_blocked():
    from app.services.system_regression.login_context import validate_identity_requirements

    result = validate_identity_requirements(
        [{"case_key": "CUSTOM-UNKNOWN", "expectation": asdict_expectation_without_identity()}],
        available_identities={ADMIN_IDENTITY, CLIENT_IDENTITY},
    )
    assert result.reason_code == "identity_requirement_unknown"
    assert result.status == "blocked"


def asdict_expectation_without_identity() -> dict[str, object]:
    return {"outcome": "success", "direction": "none"}


def test_batch_preflight_rejects_missing_client_without_creating_runs(dual_identity_db, monkeypatch):
    db, factory, admin, _client = dual_identity_db
    app = FastAPI()
    app.include_router(regression_router.router)

    def override_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_admin] = lambda: type("User", (), {"id": 99})()
    queued: list[int] = []
    monkeypatch.setattr(regression_router, "queue_batch_execution", queued.append)
    case = db.query(regression_router.SystemRegressionCase).filter_by(case_key="JP-PAY-001").one()

    with TestClient(app) as client:
        response = client.post(
            "/api/system-regression/batches",
            json={
                "suite_key": "japan",
                "case_ids": [case.id],
                "project_id": 1,
                "env_id": 1,
                "admin_profile_id": admin.id,
                "context": {"variables": {}},
            },
        )

    assert response.status_code == 400
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "client_credentials_missing"
    assert payload["required_identities"] == [ADMIN_IDENTITY, CLIENT_IDENTITY]
    assert payload["available_identities"] == [ADMIN_IDENTITY]
    assert queued == []
    assert factory().query(regression_router.SystemRegressionBatch).count() == 0


__all__ = []
