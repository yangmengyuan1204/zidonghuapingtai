import os
from pathlib import Path

TEST_DB = Path(__file__).resolve().parent / "test_platform.db"
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"

from fastapi.testclient import TestClient

import app.executors as executors
from app.main import app


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_normal_user_cannot_create_project():
    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        response = client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"username": "normal_for_test", "password": "123456", "role": "normal"},
        )
        assert response.status_code in (200, 400)

        normal_token = login(client, "normal_for_test", "123456")
        blocked = client.post(
            "/api/projects",
            headers={"Authorization": f"Bearer {normal_token}"},
            json={"name": "blocked", "desc": ""},
        )
        assert blocked.status_code == 403


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = __import__("json").dumps(payload, ensure_ascii=False)
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


def test_batch_api_execution_passes_extracted_variables(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append({"method": method, "url": url, "kwargs": kwargs})
        if method == "POST":
            assert kwargs["json"]["name"] == "qa_alice"
            return FakeResponse(201, {"data": {"id": "U123"}})
        assert url.endswith("/users/U123")
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr(executors.requests, "request", fake_request)

    with TestClient(app) as client:
        admin_token = login(client, "admin", "admin123")
        headers = {"Authorization": f"Bearer {admin_token}"}

        project = client.post("/api/projects", headers=headers, json={"name": "造数项目", "desc": ""}).json()
        env = client.post(
            "/api/envs",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_name": "测试环境",
                "base_url": "https://example.test",
                "global_headers": {},
                "global_vars": {"prefix": "qa"},
                "timeout": 30,
            },
        ).json()
        case_1 = client.post(
            "/api/api-cases",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_id": env["id"],
                "case_name": "创建用户",
                "method": "POST",
                "url": "/users",
                "headers": {},
                "params": {},
                "body": {"name": "{{prefix}}_{{username}}"},
                "assert_rule": {"status_code": 201, "extract": {"user_id": "json.data.id"}},
                "status": "active",
            },
        ).json()
        case_2 = client.post(
            "/api/api-cases",
            headers=headers,
            json={
                "project_id": project["id"],
                "env_id": env["id"],
                "case_name": "查询用户",
                "method": "GET",
                "url": "/users/{{user_id}}",
                "headers": {},
                "params": {},
                "body": "",
                "assert_rule": {"status_code": 200},
                "status": "active",
            },
        ).json()

        result = client.post(
            "/api/api-cases/batch-execute",
            headers=headers,
            json={"case_ids": [case_1["id"], case_2["id"]], "variables": {"username": "alice"}},
        )

    assert result.status_code == 200
    assert result.json()["variables"]["user_id"] == "U123"
    assert [call["method"] for call in calls] == ["POST", "GET"]
