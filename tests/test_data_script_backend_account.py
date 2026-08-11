import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import data_scripts as routes


def test_oem_data_script_variables_use_environment_with_request_precedence(monkeypatch):
    monkeypatch.setattr(
        routes,
        "data_script_variables",
        lambda db, variables, project_id: dict(variables),
    )
    env = SimpleNamespace(
        global_vars=json.dumps(
            {
                "backend_account": "admin",
                "backend_password": "environment-password",
                "factory_type": "environment-factory",
            }
        )
    )

    variables = routes._oem_data_script_variables(
        object(),
        env,
        {"factory_type": "request-factory"},
        2,
    )

    assert variables["backend_account"] == "admin"
    assert variables["backend_password"] == "environment-password"
    assert variables["factory_type"] == "request-factory"


def test_backend_account_profile_overrides_legacy_runtime_values(monkeypatch):
    monkeypatch.setattr(
        routes,
        "account_profile_variables",
        lambda db, profile_id, project_id: (
            {"username": "VISIBLE-ACCOUNT", "password": "visible-password", "code": "123456"},
            {"profile_name": "订单后台账号"},
        ),
    )

    variables = routes._resolve_backend_account_variables(
        object(),
        {
            "backend_account_profile_id": 7,
            "backend_account": "Y001",
            "backend_password": "legacy-password",
        },
        3,
    )

    assert variables["backend_account"] == "VISIBLE-ACCOUNT"
    assert variables["backend_password"] == "visible-password"
    assert variables["backend_code"] == "123456"
    assert variables["backend_account_profile_name"] == "订单后台账号"


def test_backend_account_uses_y001_profile_by_default(monkeypatch):
    monkeypatch.setattr(
        routes,
        "_backend_profile_id_for_account",
        lambda db, project_id, account: 11 if account == "Y001" else None,
    )
    monkeypatch.setattr(
        routes,
        "account_profile_variables",
        lambda db, profile_id, project_id: (
            {"backend_account": "PROJECT-ACCOUNT", "backend_password": "project-password"},
            {"profile_name": "项目默认后台"},
        ),
    )

    variables = routes._resolve_backend_account_variables(object(), {}, 5)

    assert variables["backend_account_profile_id"] == 11
    assert variables["backend_account"] == "PROJECT-ACCOUNT"


def test_backend_account_rejects_missing_profile_and_credentials(monkeypatch):
    monkeypatch.setattr(
        routes,
        "_backend_profile_id_for_account",
        lambda db, project_id, account: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        routes._resolve_backend_account_variables(object(), {}, 9)

    assert exc_info.value.status_code == 400
    assert "后台账号档案" in str(exc_info.value.detail)


@pytest.mark.parametrize("legacy_password", ["raku@123456``", "xiaolin666@@"])
def test_backend_account_rejects_legacy_builtin_credentials(monkeypatch, legacy_password):
    monkeypatch.setattr(
        routes,
        "_backend_profile_id_for_account",
        lambda db, project_id, account: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        routes._resolve_backend_account_variables(
            object(),
            {"backend_account": "Y001", "backend_password": legacy_password},
            9,
        )

    assert exc_info.value.status_code == 400


def test_builtin_order_flows_do_not_hardcode_backend_account():
    source = Path(__file__).resolve().parents[1] / "static" / "full-flow.js"
    with source.open("r", encoding="utf-8-sig") as handle:
        text = handle.read()

    for function_name in ("ensureFullFlowScript", "ensureResumeOrderFlowScript"):
        start = text.index(f"function {function_name}")
        end = text.find("\n  function ", start + 1)
        block = text[start:] if end < 0 else text[start:end]
        assert 'backend_account: "Y001"' not in block
