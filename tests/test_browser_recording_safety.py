import asyncio
import json

import pytest

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
