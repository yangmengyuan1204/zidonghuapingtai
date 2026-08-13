import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import RecordedFlow
from app.routers.browser_record import _events_to_har
from app.services import browser_session, har_recorder
from app.services.flow_player import play_flow


def _login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_flow_recorder_routes_require_admin():
    with TestClient(app) as client:
        anonymous = client.get("/api/flow-recorder/list")
        assert anonymous.status_code == 401

        admin_headers = _login(client, "admin", "admin123")
        created = client.post(
            "/api/users",
            headers=admin_headers,
            json={"username": "flow_normal", "password": "123456", "role": "normal"},
        )
        assert created.status_code == 200
        normal_headers = _login(client, "flow_normal", "123456")

        blocked = client.get("/api/flow-recorder/list", headers=normal_headers)
        assert blocked.status_code == 403


def test_browser_record_routes_require_admin():
    with TestClient(app) as client:
        response = client.get("/api/browser-record/sessions/missing/events")
        assert response.status_code == 401


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_sensitive_headers_are_parameterized_and_request_bodies_support_mutating_methods(method):
    events = [
        {
            "method": method,
            "url": "https://api.example.test/orders/1",
            "query": {},
            "headers": {
                "Authorization": "Bearer secret-token",
                "Cookie": "session=secret-cookie",
                "Proxy-Authorization": "Basic secret-proxy",
                "Content-Type": "application/json",
            },
            "body": '{"amount": 10}',
            "response_status": 200,
            "response_body": {"ok": True},
            "started_at": "2026-08-13T10:00:00",
        }
    ]

    parsed = har_recorder.parse_har(_events_to_har(events))
    dynamic = har_recorder.identify_dynamic_fields(parsed)
    definition = har_recorder.build_flow_definition(parsed, dynamic)
    step = definition["steps"][0]
    headers = json.loads(step["headers_json"])

    assert json.loads(step["body_template"]) == {"amount": "{{amount}}"}
    assert headers["Authorization"] == "{{authorization}}"
    assert headers["Cookie"] == "{{cookie}}"
    assert headers["Proxy-Authorization"] == "{{proxy_authorization}}"
    assert headers["Content-Type"] == "application/json"
    assert {field["name"] for field in dynamic["fields"]} >= {
        "authorization",
        "cookie",
        "proxy_authorization",
    }
    serialized = json.dumps(definition, ensure_ascii=False)
    assert "secret-token" not in serialized
    assert "secret-cookie" not in serialized
    assert "secret-proxy" not in serialized


def test_get_events_parameterizes_sensitive_headers_without_mutating_session():
    session = SimpleNamespace(
        events=[
            {
                "headers": {
                    "Authorization": "Bearer live-secret",
                    "Cookie": "session=live-cookie",
                    "Content-Type": "application/json",
                }
            }
        ]
    )
    browser_session._SESSIONS["live-session"] = session
    try:
        events = browser_session.get_events("live-session")
        assert events[0]["headers"] == {
            "Authorization": "{{authorization}}",
            "Cookie": "{{cookie}}",
            "Content-Type": "application/json",
        }
        assert session.events[0]["headers"]["Authorization"] == "Bearer live-secret"
    finally:
        browser_session._SESSIONS.pop("live-session", None)


def test_browser_session_save_persists_urls_and_parameterizes_headers(monkeypatch):
    events = [
        {
            "method": "GET",
            "url": "https://recorded.example.test/health",
            "query": {},
            "headers": {"Authorization": "Bearer browser-secret"},
            "body": "",
            "response_status": 200,
            "response_body": {"ok": True},
            "started_at": "2026-08-13T10:00:00",
        }
    ]
    monkeypatch.setattr(browser_session, "get_events", lambda _session_id: events)

    async def fake_close(_session_id):
        return None

    monkeypatch.setattr(browser_session, "close_session", fake_close)

    with TestClient(app) as client:
        headers = _login(client, "admin", "admin123")
        response = client.post(
            "/api/browser-record/sessions/live/save",
            headers=headers,
            json={"name": "browser-flow"},
        )
        assert response.status_code == 200

        db = SessionLocal()
        try:
            flow = db.get(RecordedFlow, response.json()["flow_id"])
            assert flow.base_url == "https://recorded.example.test"
            assert flow.steps[0].full_url == "https://recorded.example.test/health"
            assert json.loads(flow.steps[0].headers_json) == {
                "Authorization": "{{authorization}}"
            }
        finally:
            db.close()


def test_save_flow_persists_base_url_and_full_url():
    with TestClient(app) as client:
        headers = _login(client, "admin", "admin123")
        response = client.post(
            "/api/flow-recorder/save",
            headers=headers,
            json={
                "name": "multi-host-flow",
                "flow_definition": {
                    "base_url": "https://api.example.test",
                    "steps": [
                        {
                            "step_index": 1,
                            "method": "GET",
                            "path": "/health",
                            "full_url": "https://other.example.test/health",
                            "headers_json": json.dumps(
                                {
                                    "Authorization": "Bearer direct-secret",
                                    "Content-Type": "application/json",
                                }
                            ),
                        }
                    ],
                },
            },
        )
        assert response.status_code == 200

        detail = client.get(
            f"/api/flow-recorder/{response.json()['flow_id']}",
            headers=headers,
        )
        assert detail.status_code == 200
        assert {field["name"] for field in detail.json()["fields"]} >= {"authorization"}
        assert "direct-secret" not in detail.text

        db = SessionLocal()
        try:
            flow = db.get(RecordedFlow, response.json()["flow_id"])
            assert flow.base_url == "https://api.example.test"
            assert flow.steps[0].full_url == "https://other.example.test/health"
            assert json.loads(flow.steps[0].headers_json) == {
                "Authorization": "{{authorization}}",
                "Content-Type": "application/json",
            }
        finally:
            db.close()


def test_missing_browser_session_returns_404_for_events_and_save():
    with TestClient(app) as client:
        headers = _login(client, "admin", "admin123")
        events = client.get("/api/browser-record/sessions/missing/events", headers=headers)
        saved = client.post(
            "/api/browser-record/sessions/missing/save",
            headers=headers,
            json={"name": "missing"},
        )
        assert events.status_code == 404
        assert saved.status_code == 404


def test_start_session_closes_resources_when_initial_navigation_fails(monkeypatch):
    closed: list[str] = []

    class FakePage:
        def on(self, *_args):
            return None

        async def goto(self, *_args, **_kwargs):
            raise RuntimeError("navigation failed")

        async def close(self):
            closed.append("page")

    class FakeContext:
        async def new_page(self):
            return FakePage()

        async def close(self):
            closed.append("context")

    class FakeBrowser:
        async def new_context(self):
            return FakeContext()

        async def close(self):
            closed.append("browser")

    class FakePlaywright:
        async def stop(self):
            closed.append("playwright")

    class FakeStarter:
        async def start(self):
            return FakePlaywright()

    monkeypatch.setattr(browser_session, "async_playwright", lambda: FakeStarter())
    monkeypatch.setattr(browser_session, "_launch_chromium", lambda _pw: _async_value(FakeBrowser()))

    with pytest.raises(RuntimeError, match="navigation failed"):
        asyncio.run(browser_session.start_session("https://bad.example.test"))

    assert closed == ["page", "context", "browser", "playwright"]
    assert browser_session._SESSIONS == {}


async def _async_value(value):
    return value


def test_play_flow_replaces_sensitive_header_placeholders(monkeypatch):
    db = SessionLocal()
    try:
        flow = RecordedFlow(name="parameterized", base_url="https://api.example.test")
        flow.steps.append(
            __import__("app.models", fromlist=["RecordedFlowStep"]).RecordedFlowStep(
                step_index=1,
                method="GET",
                path="/secure",
                full_url="https://api.example.test/secure",
                headers_json=json.dumps({"Authorization": "{{authorization}}", "Cookie": "{{cookie}}"}),
            )
        )
        db.add(flow)
        db.commit()
        db.refresh(flow)

        captured = {}

        def fake_send(_session, _method, _url, headers, _body):
            captured.update(headers)
            return SimpleNamespace(status_code=200, text='{"success": true}')

        monkeypatch.setattr("app.services.flow_player._send_request", fake_send)
        result = play_flow(
            flow.id,
            {"authorization": "Bearer runtime-token", "cookie": "session=runtime-cookie"},
            db,
        )

        assert result["success"] is True
        assert captured == {
            "Authorization": "Bearer runtime-token",
            "Cookie": "session=runtime-cookie",
        }
    finally:
        db.close()
