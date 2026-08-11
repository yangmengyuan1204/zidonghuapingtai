from __future__ import annotations

import json
from datetime import datetime

import app.core.utils  # ensure compat globals are loaded for account_utils wrappers
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.account_utils import encrypt_account_payload
from app.database import Base
from app.models import Env, TestAccountProfile
from app.services.system_regression.case_service import ensure_japan_suite
from app.services.system_regression.login_context import (
    SYSTEM_REGRESSION_CUSTOMER_PROFILE_NAME,
    SYSTEM_REGRESSION_LOGIN_KIND_BACKEND,
    SYSTEM_REGRESSION_LOGIN_KIND_CUSTOMER,
    SystemRegressionLoginContextError,
    resolve_system_regression_login_context,
)


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


def _add_env(db_session):
    env = Env(
        id=1,
        project_id=1,
        env_name="JP",
        base_url="https://jpapi.rakumart.cn",
        global_headers="{}",
        global_vars="{}",
        timeout=30,
    )
    db_session.add(env)
    db_session.commit()
    return env


def _add_customer_profile(db_session, *, username="Y002", password="secret-pass", profile_name=SYSTEM_REGRESSION_CUSTOMER_PROFILE_NAME, project_id=None):
    profile = TestAccountProfile(
        project_id=project_id,
        profile_name=profile_name,
        variables=json.dumps({"username": username}, ensure_ascii=False),
        sensitive_variables=encrypt_account_payload({"password": password}),
        status="active",
        create_time=datetime.now(),
    )
    db_session.add(profile)
    db_session.commit()
    return profile


def test_profile_username_maps_to_admin_username_without_leaking_password(db_session):
    ensure_japan_suite(db_session)
    _add_env(db_session)
    profile = _add_customer_profile(db_session)

    resolution = resolve_system_regression_login_context(
        db_session,
        project_id=1,
        env_id=1,
        context={"variables": {}, "system_regression_login": {"kind": SYSTEM_REGRESSION_LOGIN_KIND_BACKEND}},
        required_identities=("admin",),
    )

    assert resolution.variables["backend_account"] == "Y002"
    assert resolution.variables["backend_password"] == "secret-pass"
    assert "account" not in resolution.variables
    assert resolution.precondition_evidence["admin_credential_source"] == "admin_profile.username"
    assert resolution.precondition_evidence["profile_id"] == profile.id
    assert resolution.login_context["kind"] == SYSTEM_REGRESSION_LOGIN_KIND_BACKEND
    assert "secret-pass" not in json.dumps(resolution.precondition_evidence, ensure_ascii=False)
    assert "secret-pass" not in json.dumps(resolution.login_context, ensure_ascii=False)


def test_explicit_account_and_password_override_customer_login_profile(db_session):
    ensure_japan_suite(db_session)
    _add_env(db_session)
    _add_customer_profile(db_session)

    resolution = resolve_system_regression_login_context(
        db_session,
        project_id=1,
        env_id=1,
        context={
            "variables": {
                "account": "explicit-account",
                "password": "explicit-pass",
                "customer_id": "300001",
            }
        },
    )

    assert resolution.variables["account"] == "explicit-account"
    assert resolution.variables["password"] == "explicit-pass"
    assert resolution.precondition_evidence["credential_source"] == "explicit_account"


def test_customer_id_path_remains_supported(db_session):
    ensure_japan_suite(db_session)
    _add_env(db_session)
    _add_customer_profile(db_session)

    resolution = resolve_system_regression_login_context(
        db_session,
        project_id=1,
        env_id=1,
        context={"variables": {"customer_id": "300001"}},
    )

    assert resolution.variables["account"] == "userID/300001In"
    assert resolution.precondition_evidence["credential_source"] == "customer_id"
    assert resolution.precondition_evidence["customer_id_present"] is True


def test_backend_context_does_not_auto_map_username_to_account(db_session):
    ensure_japan_suite(db_session)
    _add_env(db_session)
    _add_customer_profile(db_session, username="backend-user", password="backend-pass", profile_name="后台测试账号")

    resolution = resolve_system_regression_login_context(
        db_session,
        project_id=1,
        env_id=1,
        context={
            "variables": {"username": "backend-user", "password": "backend-pass"},
            "system_regression_login": {"kind": SYSTEM_REGRESSION_LOGIN_KIND_BACKEND},
        },
        required_identities=("admin",),
    )

    assert resolution.variables["backend_account"] == "backend-user"
    assert resolution.variables["backend_password"] == "backend-pass"
    assert "account" not in resolution.variables


def test_missing_password_blocks_even_if_username_exists(db_session):
    ensure_japan_suite(db_session)
    _add_env(db_session)
    profile = _add_customer_profile(db_session, password="")

    with pytest.raises(SystemRegressionLoginContextError) as exc:
        resolve_system_regression_login_context(
            db_session,
            project_id=1,
            env_id=1,
            context={"variables": {}, "system_regression_login": {"profile_id": profile.id}},
            required_identities=("admin",),
        )

    assert exc.value.reason_code == "admin_credentials_missing"
    assert exc.value.precondition_evidence["profile_id"] == profile.id
