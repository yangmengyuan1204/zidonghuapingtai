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
    assert data["total"] == 10
    assert len(data["cases"]) == 10
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


def test_reset_custom_case_returns_business_error(api_client):
    case = api_client.get("/api/system-regression/suites/japan/cases").json()["cases"][0]
    copied = api_client.post(f"/api/system-regression/cases/{case['id']}/copy").json()

    response = api_client.post(f"/api/system-regression/cases/{copied['id']}/reset")

    assert response.status_code == 400
    assert response.json()["detail"] == "自定义用例不支持重置"
