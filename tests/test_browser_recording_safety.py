import asyncio
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.routers import browser_record
from app.services import browser_session


class FakeRequest:
    method = "POST"
    resource_type = "xhr"
    url = "https://example.test/order.rollback?order_sn=ORDER-1&token=query-secret"
    headers = {
        "content-type": "application/json",
        "accept": "application/json",
        "authorization": "Bearer header-secret",
        "cookie": "session=cookie-secret",
    }
    post_data = json.dumps({
        "order_sn": "ORDER-1",
        "password": "body-secret",
        "nested": {"access_token": "nested-secret", "target_status": "wait_offer"},
    })


class FakeResponse:
    status = 200
    headers = {"content-type": "application/json"}

    def __init__(self, request):
        self.request = request

    async def text(self):
        return json.dumps({
            "success": True,
            "token": "response-secret",
            "data": {"status": "wait_offer"},
        })


def make_session(state="login_ready"):
    session = browser_session._Session(None, None, None, None)
    session.state = state
    return session


def test_login_ready_does_not_capture_requests():
    session = make_session("login_ready")
    browser_session._on_request_sync(session, FakeRequest())
    assert session.events == []


def test_checkpoint_clears_old_events_and_captures_only_sanitized_data():
    session_id = "safe-checkpoint"
    session = make_session()
    session.events.append({"path": "/old"})
    browser_session._SESSIONS[session_id] = session
    try:
        state = browser_session.start_checkpoint(session_id)
        assert state == {"session_id": session_id, "status": "capturing", "event_count": 0}

        request = FakeRequest()
        browser_session._on_request_sync(session, request)
        asyncio.run(browser_session._on_response_async(session, FakeResponse(request)))
        frozen = browser_session.stop_checkpoint(session_id)

        assert frozen == {"session_id": session_id, "status": "frozen", "event_count": 1}
        event = browser_session.get_events(session_id)[0]
        serialized = json.dumps(event, ensure_ascii=False)
        for secret in ("query-secret", "header-secret", "cookie-secret", "body-secret", "nested-secret", "response-secret"):
            assert secret not in serialized
        assert event["headers"] == {"content-type": "application/json", "accept": "application/json"}
        assert event["query"] == {"order_sn": "ORDER-1", "token": "[REDACTED]"}
        assert json.loads(event["body"])["password"] == "[REDACTED]"
        assert event["response_body"]["token"] == "[REDACTED]"
        assert event["response_body"]["data"]["status"] == "wait_offer"
    finally:
        browser_session._SESSIONS.pop(session_id, None)


def test_start_and_stop_checkpoint_reject_missing_session():
    with pytest.raises(ValueError, match="会话不存在"):
        browser_session.start_checkpoint("missing")
    with pytest.raises(ValueError, match="会话不存在"):
        browser_session.stop_checkpoint("missing")


def test_non_json_response_body_is_omitted():
    assert browser_session.sanitize_response_body("plain token=secret", "text/plain") == "[NON_JSON_RESPONSE_OMITTED]"


def test_form_body_is_sanitized_without_losing_business_fields():
    body = browser_session.sanitize_body(
        "order_sn=ORDER-1&password=secret&target_status=wait_offer",
        "application/x-www-form-urlencoded",
    )
    assert "order_sn=ORDER-1" in body
    assert "target_status=wait_offer" in body
    assert "secret" not in body
    assert "password=%5BREDACTED%5D" in body


def test_camel_case_and_alias_sensitive_fields_are_redacted_from_events():
    session = make_session("capturing")
    request = FakeRequest()
    request.url = (
        "https://example.test/order.rollback?order_sn=ORDER-1&accessToken=access-secret"
        "&refreshToken=refresh-secret&smsCode=sms-secret&phoneNumber=phone-secret"
    )
    request.post_data = json.dumps({
        "order_sn": "ORDER-1",
        "accessToken": "access-secret",
        "refreshToken": "refresh-secret",
        "smsCode": "sms-secret",
        "phoneNumber": "phone-secret",
    })

    browser_session._on_request_sync(session, request)

    event = session.events[0]
    serialized = json.dumps(event, ensure_ascii=False)
    for secret in ("access-secret", "refresh-secret", "sms-secret", "phone-secret"):
        assert secret not in serialized
    assert event["query"]["order_sn"] == "ORDER-1"
    assert all(event["query"][field] == "[REDACTED]" for field in (
        "accessToken", "refreshToken", "smsCode", "phoneNumber",
    ))
    assert json.loads(event["body"])["phoneNumber"] == "[REDACTED]"


def test_sanitize_url_removes_userinfo_and_preserves_ipv6_port():
    safe_url, query = browser_session.sanitize_url(
        "https://record-user:record-password@[2001:db8::1]:8443/orders?token=query-secret&order_sn=ORDER-1"
    )

    assert "record-user" not in safe_url
    assert "record-password" not in safe_url
    assert safe_url.startswith("https://[2001:db8::1]:8443/orders?")
    assert "query-secret" not in safe_url
    assert query == {"token": "[REDACTED]", "order_sn": "ORDER-1"}


def test_all_normalized_code_suffixes_are_redacted_in_query_and_nested_json():
    session = make_session("capturing")
    request = FakeRequest()
    request.url = (
        "https://example.test/verify?otpCode=otp-secret&mfaCode=mfa-secret"
        "&totpCode=totp-secret&order_sn=ORDER-1"
    )
    request.post_data = json.dumps({
        "order_sn": "ORDER-1",
        "verification": {
            "otpCode": "otp-secret",
            "mfaCode": "mfa-secret",
            "totpCode": "totp-secret",
        },
    })

    browser_session._on_request_sync(session, request)

    event = session.events[0]
    serialized = json.dumps(event, ensure_ascii=False)
    for secret in ("otp-secret", "mfa-secret", "totp-secret"):
        assert secret not in serialized
    assert all(event["query"][field] == "[REDACTED]" for field in ("otpCode", "mfaCode", "totpCode"))
    body = json.loads(event["body"])
    assert all(body["verification"][field] == "[REDACTED]" for field in ("otpCode", "mfaCode", "totpCode"))


class FakeDb:
    def add(self, value):
        raise AssertionError("save guard must stop before database writes")

    def flush(self):
        raise AssertionError("save guard must stop before database writes")

    def commit(self):
        raise AssertionError("save guard must stop before database writes")


def route_client():
    app = FastAPI()
    app.include_router(browser_record.router)
    app.dependency_overrides[get_db] = lambda: FakeDb()
    return TestClient(app)


def test_checkpoint_routes_expose_safe_state(monkeypatch):
    monkeypatch.setattr(browser_session, "get_session_state", lambda session_id: {
        "session_id": session_id, "status": "login_ready", "event_count": 0,
    })
    monkeypatch.setattr(browser_session, "start_checkpoint", lambda session_id: {
        "session_id": session_id, "status": "capturing", "event_count": 0,
    })
    monkeypatch.setattr(browser_session, "stop_checkpoint", lambda session_id: {
        "session_id": session_id, "status": "frozen", "event_count": 2,
    })
    client = route_client()

    assert client.get("/api/browser-record/sessions/S1").json()["status"] == "login_ready"
    assert client.post("/api/browser-record/sessions/S1/checkpoint/start").json()["status"] == "capturing"
    stopped = client.post("/api/browser-record/sessions/S1/checkpoint/stop").json()
    assert stopped == {"session_id": "S1", "status": "frozen", "event_count": 2}


def test_checkpoint_route_returns_404_for_missing_session(monkeypatch):
    def missing(_session_id):
        raise ValueError("会话不存在: missing")

    monkeypatch.setattr(browser_session, "start_checkpoint", missing)
    response = route_client().post("/api/browser-record/sessions/missing/checkpoint/start")
    assert response.status_code == 404
    assert response.json()["detail"] == "会话不存在: missing"


def test_save_rejects_non_frozen_session_before_database_write(monkeypatch):
    monkeypatch.setattr(browser_session, "get_session_state", lambda session_id: {
        "session_id": session_id, "status": "capturing", "event_count": 1,
    })
    response = route_client().post(
        "/api/browser-record/sessions/S1/save",
        json={"name": "不得保存"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "请先停止并冻结当前检查点"


def test_events_to_har_preserves_only_sanitized_values():
    har = browser_record._events_to_har([{
        "method": "POST",
        "url": "https://example.test/order.rollback?token=%5BREDACTED%5D",
        "query": {"token": "[REDACTED]"},
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"password": "[REDACTED]", "order_sn": "ORDER-1"}),
        "response_status": 200,
        "response_body": {"token": "[REDACTED]", "status": "wait_offer"},
        "started_at": "2026-07-18T12:00:00",
    }])
    serialized = json.dumps(har, ensure_ascii=False)
    assert "ORDER-1" in serialized
    assert "wait_offer" in serialized
    assert "secret" not in serialized
    assert "authorization" not in serialized.lower()
    assert "cookie" not in serialized.lower()


def test_checkpoint_routes_are_in_route_contract_baseline():
    expected = json.loads(
        Path(__file__).with_name("route_contract_expected.json").read_text(encoding="utf-8-sig")
    )
    contracts = {(item["method"], item["path"], item["name"]) for item in expected}

    assert ("GET", "/api/browser-record/sessions/{session_id}", "session_state") in contracts
    assert (
        "POST",
        "/api/browser-record/sessions/{session_id}/checkpoint/start",
        "start_checkpoint",
    ) in contracts
    assert (
        "POST",
        "/api/browser-record/sessions/{session_id}/checkpoint/stop",
        "stop_checkpoint",
    ) in contracts
