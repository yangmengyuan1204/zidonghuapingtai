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
from app.services.system_regression.ticket_service import list_usable_tickets, normalize_usable_discounts


FIXED_USER_INFO_PAYLOAD = {
    "success": True,
    "code": 0,
    "msg": "success",
    "data": {
        "current_service_rate": 0,
        "level": {
            "currentLevel": {
                "id": 7,
                "level_type": 1,
                "level_name": "定額会員",
                "service_rate": "0",
            }
        },
    },
}


USABLE_DISCOUNT_PAYLOAD = {
    "success": True,
    "code": 0,
    "msg": "success",
    "data": {
        "pageSize": 1000,
        "currentPage": 1,
        "lastPage": 1,
        "total": 3,
        "data": [
            {
                "id": 180895,
                "sn": "CPN180895",
                "type": 1,
                "type_name": "优惠券",
                "status": 1,
                "status_name": "待使用",
                "name_chinese": "手数料無料",
                "name_translation": "手续费免费",
                "discounts_amount_jpy": 1,
            },
            {
                "id": "180900",
                "type": "3",
                "type_name": "折扣券",
                "status": "1",
                "name_chinese": "国际物流折扣券",
                "discounts_amount_jpy": 1500,
                "logistics_id": 25,
                "logistics_group": [{"logistics_name": "海运"}],
            },
            {
                "id": 180901,
                "type": 1,
                "type_name": "优惠券",
                "status": 2,
                "name_chinese": "已用掉的券",
            },
        ],
    },
}


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
            "coupons": [{"id": "180895", "title": "手数料無料"}],
            "vouchers": [{"id": "180900", "title": "国际物流折扣券", "kind": "logistics", "amount": "1500"}],
            "reason": "",
        }

    monkeypatch.setattr(regression_router_module, "list_usable_tickets", fake_list)
    try:
        with TestClient(app) as client:
            yield client, captured
    finally:
        Base.metadata.drop_all(bind=engine)


def test_catalog_registers_usable_discount_path():
    item = next(row for row in DATA_SCRIPT_API_CASES if row["key"] == "client_usable_discount")
    assert item["url"] == "/client/user.usableDiscount"
    assert item["body"]["page"] == "{{page}}"
    assert item["body"]["pageSize"] == "{{page_size}}"


def test_normalize_usable_discounts_splits_order_coupons_and_logistics_vouchers():
    result = normalize_usable_discounts(USABLE_DISCOUNT_PAYLOAD)

    assert result["coupons"] == [
        {
            "id": "180895",
            "title": "手数料無料",
            "type": "1",
            "discounts_amount_jpy": "1",
            "fee_waiver": True,
        }
    ]
    assert result["vouchers"] == [
        {
            "id": "180900",
            "title": "国际物流折扣券",
            "kind": "logistics",
            "amount": "1500",
            "logistics_id": "25",
            "logistics_name": "海运",
        }
    ]
    assert result["reason"] == ""


def test_normalize_usable_discounts_skips_used_and_empty_ids():
    result = normalize_usable_discounts(
        {
            "success": True,
            "code": 0,
            "data": {
                "data": [
                    {"id": "", "type": 1, "status": 1, "name_chinese": "空"},
                    {"id": 9, "type": 2, "status": 1, "name_chinese": "全部抵扣券"},
                ]
            },
        }
    )

    assert result["coupons"] == []
    assert result["vouchers"] == [{"id": "9", "title": "全部抵扣券", "kind": "all"}]


def test_catalog_registers_user_info_path():
    item = next(row for row in DATA_SCRIPT_API_CASES if row["key"] == "client_user_info")
    assert item["url"] == "/client/user.info"


def test_list_usable_tickets_uses_catalog_path_and_does_not_leak_token(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, base_url, timeout):
            self.base_url = base_url
            self.timeout = timeout
            self.session = SimpleNamespace(headers={})

        def login(self, account, password, client_tool):
            calls.append(("login", account, client_tool))
            self.session.headers["clienttoken"] = "token"
            return "token"

        def post_form(self, path, fields):
            calls.append(("post", path, dict(fields)))
            if str(path).endswith("user.info"):
                return FIXED_USER_INFO_PAYLOAD
            return USABLE_DISCOUNT_PAYLOAD

    monkeypatch.setattr("app.services.system_regression.ticket_service.RakumartClient", FakeClient)
    monkeypatch.setattr("app.services.system_regression.ticket_service._configure_client_api_paths", lambda client, variables: None)

    env = SimpleNamespace(base_url="https://jpapi.rakumart.cn/", timeout=25)
    result = list_usable_tickets(
        env,
        {"account": "userID/300001In", "password": "secret", "client_tool": "1"},
    )

    assert calls[0][0] == "login"
    assert calls[1][1] == "/client/user.usableDiscount"
    assert calls[1][2] == {"page": "1", "pageSize": "1000"}
    assert calls[2][1] == "/client/user.info"
    assert result["coupons"][0]["id"] == "180895"
    assert result["vouchers"][0]["kind"] == "logistics"
    assert result["membership"]["kind"] == "fixed"
    assert result["membership"]["service_rate"] == "0"
    assert "secret" not in str(result)


def test_list_usable_tickets_redacts_jwt_from_failure_reason(monkeypatch):
    class FakeClient:
        def __init__(self, base_url, timeout):
            self.session = SimpleNamespace(headers={})

        def login(self, account, password, client_tool):
            raise RuntimeError("clienttoken=eyJaaaaaaaaaa.bbbbbbbbbbbb.cccccccccccc")

    monkeypatch.setattr("app.services.system_regression.ticket_service.RakumartClient", FakeClient)
    monkeypatch.setattr("app.services.system_regression.ticket_service._configure_client_api_paths", lambda client, variables: None)

    result = list_usable_tickets(
        SimpleNamespace(base_url="https://jpapi.rakumart.cn", timeout=25),
        {"account": "userID/300001In", "password": "secret"},
    )

    assert result["coupons"] == []
    assert result["membership"]["kind"] == ""
    assert "[token]" in result["reason"] or "clienttoken=[hidden]" in result["reason"]
    assert "eyJaaaaaaaaaa" not in result["reason"]
    assert "secret" not in result["reason"]


def test_tickets_endpoint_rejects_non_numeric_customer_id(api_client):
    client, _captured = api_client
    response = client.post(
        "/api/system-regression/tickets",
        json={"project_id": 1, "env_id": 1, "customer_id": "abc"},
    )

    assert response.status_code == 200
    assert response.json() == {"coupons": [], "vouchers": [], "reason": "客户 ID 只能填写数字"}


def test_tickets_endpoint_uses_customer_id_login_and_returns_lists(api_client):
    client, captured = api_client
    response = client.post(
        "/api/system-regression/tickets",
        json={"project_id": 1, "env_id": 1, "customer_id": "300001"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["coupons"][0]["id"] == "180895"
    assert body["vouchers"][0]["kind"] == "logistics"
    assert captured["variables"]["account"] == "userID/300001In"
    assert captured["variables"]["customer_id"] == "300001"
    assert "token" not in captured["variables"]
    assert "eyJ" not in str(captured["variables"])
