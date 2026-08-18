from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.data_script_catalog import DATA_SCRIPT_API_CASES
from app.database import Base, get_db
from app.models import Env
from app.routers import system_regression as regression_router_module
from app.routers.system_regression import router
from app.security import require_admin
from app.services.system_regression.option_service import list_order_options, normalize_order_options


@pytest.fixture()
def api_client(monkeypatch):
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
    seed = session_factory()
    seed.add(
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
    seed.commit()
    seed.close()
    captured = {}

    def fake_list(env, variables):
        captured["env"] = env
        captured["variables"] = dict(variables or {})
        return {
            "options": [
                {"key": "79", "id": "79", "name": "詳細検品", "price": "2", "price_type": 0, "unit": "件"},
                {"key": "80", "id": "80", "name": "検品", "price": "5", "price_type": 1, "unit": ""},
            ],
            "path": "/client/order.optionList",
            "reason": "",
        }

    monkeypatch.setattr(regression_router_module, "list_order_options", fake_list)
    try:
        with TestClient(app) as client:
            yield client, captured
    finally:
        Base.metadata.drop_all(bind=engine)


def test_catalog_registers_order_option_list_path():
    item = next(row for row in DATA_SCRIPT_API_CASES if row["key"] == "client_order_option_list")
    assert item["url"] == "/client/order.optionList"


def test_normalize_order_options_keeps_public_fields():
    result = normalize_order_options(
        {
            "path": "/client/order.optionList",
            "options": [
                {"key": "79", "id": 79, "label": "詳細検品", "name": "詳細検品", "price": "2", "price_type": "0", "unit": "件"},
                {"name": ""},
            ],
        }
    )

    assert result["path"] == "/client/order.optionList"
    assert result["options"] == [
        {
            "key": "79",
            "id": "79",
            "name": "詳細検品",
            "name_translate": "",
            "price": "2",
            "price_type": 0,
            "unit": "件",
        }
    ]
    assert result["reason"] == ""


def test_list_order_options_uses_inspect_and_redacts_failure(monkeypatch):
    monkeypatch.setattr(
        "app.services.system_regression.option_service.inspect_order_options",
        lambda env, variables: (_ for _ in ()).throw(RuntimeError("token=eyJaaaaaaaaaa.bbbbbbbbbbbb.cccccccccccc")),
    )

    result = list_order_options(
        SimpleNamespace(base_url="https://jpapi.rakumart.cn", timeout=25),
        {"account": "userID/300001In", "password": "secret"},
    )

    assert result["options"] == []
    assert "eyJaaaaaaaaaa" not in result["reason"]
    assert "secret" not in result["reason"]


def test_options_endpoint_rejects_non_numeric_customer_id(api_client):
    client, _captured = api_client
    response = client.post(
        "/api/system-regression/options",
        json={"project_id": 1, "env_id": 1, "customer_id": "abc"},
    )

    assert response.status_code == 200
    assert response.json()["reason"] == "客户 ID 只能填写数字"
    assert response.json()["options"] == []


def test_options_endpoint_uses_customer_id_login_and_returns_list(api_client):
    client, captured = api_client
    response = client.post(
        "/api/system-regression/options",
        json={"project_id": 1, "env_id": 1, "customer_id": "300001"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["options"][0]["id"] == "79"
    assert body["options"][1]["price_type"] == 1
    assert captured["variables"]["account"] == "userID/300001In"
    assert captured["variables"]["customer_id"] == "300001"
    assert "token" not in captured["variables"]
