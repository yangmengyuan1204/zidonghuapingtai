from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.routers.system_regression import router
from app.security import require_admin


@pytest.fixture()
def api_client():
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
    try:
        with TestClient(app) as client:
            yield client
    finally:
        Base.metadata.drop_all(bind=engine)


def test_list_japan_cases_seeds_catalog_and_returns_field_values(api_client):
    response = api_client.get("/api/system-regression/suites/japan/cases?category=payment")

    assert response.status_code == 200
    data = response.json()
    assert data["suite"]["suite_key"] == "japan"
    assert data["total"] == 15
    assert len(data["cases"]) == 15
    assert data["cases"][0]["case_key"] == "JP-PAY-001"
    assert isinstance(data["cases"][0]["parameters"], dict)
    assert "parameters_json" not in data["cases"][0]
    assert data["problem_types"] == [
        {"value": 1, "label": "单价变动"},
        {"value": 2, "label": "运费变动"},
        {"value": 3, "label": "少货"},
        {"value": 4, "label": "不良"},
        {"value": 5, "label": "不良且少货"},
        {"value": 6, "label": "option变动"},
        {"value": 7, "label": "数量多了"},
        {"value": 8, "label": "其他"},
        {"value": 9, "label": "客户原因"},
        {"value": 10, "label": "不良直接上架"},
    ]


def test_admin_can_update_copy_and_reset_case(api_client):
    listed = api_client.get("/api/system-regression/suites/japan/cases?category=payment").json()
    case = listed["cases"][0]

    updated_response = api_client.patch(
        f"/api/system-regression/cases/{case['id']}",
        json={
            "name": "余额全额支付（自定义）",
            "parameters": {**case["parameters"], "other_fee_amount": "12.50"},
        },
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()
    assert updated["version"] == 2
    assert updated["user_modified"] is True
    assert updated["parameters"]["other_fee_amount"] == "12.50"

    copied_response = api_client.post(f"/api/system-regression/cases/{case['id']}/copy")
    assert copied_response.status_code == 201
    copied = copied_response.json()
    assert copied["is_system"] is False
    assert copied["case_key"].startswith("CUSTOM-")

    reset_response = api_client.post(f"/api/system-regression/cases/{case['id']}/reset")
    assert reset_response.status_code == 200
    reset = reset_response.json()
    assert reset["name"] == case["name"]
    assert reset["user_modified"] is False


def test_admin_can_create_custom_cases_and_cannot_delete_system_cases(api_client):
    created = api_client.post("/api/system-regression/cases", json={"kind": "part", "name": "我的分批"})
    assert created.status_code == 201
    first = created.json()
    assert first["case_key"] == "CUSTOM-PAY-001"
    assert first["runner_kind"] == "order_part_payment"
    assert first["is_system"] is False
    assert first["parameters"]["part_pay"]["enabled"] is True

    second = api_client.post("/api/system-regression/cases", json={"kind": "part"}).json()
    assert second["case_key"] == "CUSTOM-PAY-002"

    deleted = api_client.delete(f"/api/system-regression/cases/{first['id']}")
    assert deleted.status_code == 204

    third = api_client.post("/api/system-regression/cases", json={"kind": "part"}).json()
    assert third["case_key"] == "CUSTOM-PAY-003"

    porder = api_client.post("/api/system-regression/cases", json={"kind": "porder", "name": "海运"}).json()
    assert porder["case_key"] == "CUSTOM-PORDER-001"
    assert porder["runner_kind"] == "porder_payment"
    assert porder["category"] == "porder"

    listed = api_client.get("/api/system-regression/suites/japan/cases?category=payment").json()
    system_case = next(row for row in listed["cases"] if row["case_key"] == "JP-PAY-001")
    blocked = api_client.delete(f"/api/system-regression/cases/{system_case['id']}")
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == "系统预置用例不能删除"

    invalid = api_client.post("/api/system-regression/cases", json={"kind": "unknown"})
    assert invalid.status_code == 400
    assert invalid.json()["detail"] == "不支持的用例类型"


def test_reset_custom_case_returns_business_error(api_client):
    case = api_client.get("/api/system-regression/suites/japan/cases").json()["cases"][0]
    copied = api_client.post(f"/api/system-regression/cases/{case['id']}/copy").json()

    response = api_client.post(f"/api/system-regression/cases/{copied['id']}/reset")

    assert response.status_code == 400
    assert response.json()["detail"] == "自定义用例不支持重置"
