from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import TestAccountProfile as AccountProfileModel
from app.services.system_regression.account_service import (
    AccountLoginRequired,
    MINISTER_PROFILE_NAME,
    minister_account_context,
    requires_minister_account,
    use_temporary_credentials,
)
from app.services.system_regression.batch_service import create_batch, resume_run_with_account
from app.services.system_regression.case_service import ensure_japan_suite, list_cases
from app.system_regression.models import SystemRegressionCaseRun
from app.system_regression.projects.japan.runner import CaseRunResult


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_refund_threshold_is_inclusive():
    assert requires_minister_account("499.99") is False
    assert requires_minister_account("500") is True
    assert requires_minister_account("500.01") is True


def test_project_minister_profile_is_selected_by_fixed_name(db_session):
    profile = AccountProfileModel(
        project_id=7,
        profile_name=MINISTER_PROFILE_NAME,
        variables=json.dumps({"backend_account": "shenwenni"}),
        sensitive_variables=None,
        status="active",
        create_time=datetime.now(),
    )
    db_session.add(profile)
    db_session.commit()

    context = minister_account_context(db_session, project_id=7, refund_cny="500")

    assert context["backend_account_profile_id"] == profile.id
    assert context["backend_account_profile_name"] == "沈文妮"
    assert context["backend_account"] == "shenwenni"


def test_missing_or_failed_profile_requests_manual_credentials(db_session):
    with pytest.raises(AccountLoginRequired) as missing:
        minister_account_context(db_session, project_id=7, refund_cny="700")
    assert missing.value.profile_name == "沈文妮"

    profile = AccountProfileModel(
        project_id=7,
        profile_name=MINISTER_PROFILE_NAME,
        variables=json.dumps({"backend_account": "shenwenni"}),
        sensitive_variables=None,
        status="active",
        create_time=datetime.now(),
    )
    db_session.add(profile)
    db_session.commit()
    with pytest.raises(AccountLoginRequired, match="自动登录失败"):
        minister_account_context(db_session, project_id=7, refund_cny="700", login_probe=lambda _values: False)


def test_temporary_password_is_only_passed_to_callback_and_never_returned():
    captured = []

    result = use_temporary_credentials(
        username="manual-user",
        password="secret-pass",
        continuation=lambda values: captured.append(dict(values)) or {"status": "resumed", "password": "should-be-removed"},
    )

    assert captured == [{"backend_account": "manual-user", "backend_password": "secret-pass"}]
    assert result == {"status": "resumed"}
    assert "secret-pass" not in json.dumps(result, ensure_ascii=False)


def test_resume_waiting_run_uses_password_in_memory_only(db_session):
    ensure_japan_suite(db_session)
    case = list_cases(db_session, suite_key="japan")[0]
    batch = create_batch(
        db_session,
        suite_key="japan",
        case_ids=[case.id],
        project_id=7,
        env_id=8,
        actor_id=1,
        context={"variables": {}},
    )
    run = db_session.query(SystemRegressionCaseRun).filter_by(batch_id=batch.id).one()
    run.status = "waiting_account"
    run.resume_stage = "purchase_process"
    run.order_sn = "O-1"
    run.problem_goods_id = "P-1"
    run.result_json = json.dumps(
        {
            "execution_state": {
                "resume_payload": {
                    "order_sn": "O-1",
                    "problem_goods_id": "P-1",
                    "purchase_record_ids": ["R-1"],
                }
            }
        }
    )
    db_session.commit()
    captured = []

    resumed = resume_run_with_account(
        db_session,
        run.id,
        username="manual-user",
        password="secret-pass",
        runner=lambda _case, context: captured.append(dict(context)) or CaseRunResult(status="passed", result={"password": "secret-pass"}),
    )

    assert resumed.status == "passed"
    assert captured[0]["variables"] == {"backend_account": "manual-user", "backend_password": "secret-pass"}
    assert captured[0]["execution_state"]["resume_payload"]["problem_goods_id"] == "P-1"
    assert captured[0]["execution_id"]
    assert callable(captured[0]["checkpoint"])
    persisted = " ".join([resumed.result_json, resumed.error_message or "", batch.context_json])
    assert "secret-pass" not in persisted
    assert "password" not in resumed.result_json.lower()
