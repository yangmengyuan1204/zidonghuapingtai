from types import SimpleNamespace

import pytest
import requests

import app.data_scripts as data_scripts
from app.data_scripts import order_support
from app.data_scripts.payment_amount_regression.runner import LivePaymentRegressionExecutor
from app.data_scripts.payment_amount_regression.scenarios import ScenarioSpec


class TimeoutSession:
    def __init__(self):
        self.post_count = 0

    def post(self, *args, **kwargs):
        self.post_count += 1
        raise requests.Timeout("response timed out")


class SuccessSession:
    def __init__(self, payload=None):
        self.post_count = 0
        self.payload = payload or {"success": True, "code": 0}

    def post(self, *args, **kwargs):
        self.post_count += 1
        return SimpleNamespace(json=lambda: self.payload)


def test_translate_success_writes_once_and_returns_structured_evidence():
    order_support._sync_compat_globals()
    session = SuccessSession()

    payload, order_data, reconciliation = order_support._impl__submit_order_translate_with_reconciliation(
        session,
        "https://example.test",
        {},
        "ORDER-OK",
        {"data": "{}", "is_temp": "0"},
        30,
    )

    assert payload["success"] is True
    assert order_data == {}
    assert reconciliation["write_state"] == "confirmed_written"
    assert reconciliation["reason_code"] == "confirmed_written"
    assert reconciliation["request_attempt_count"] == 1
    assert reconciliation["attempted_action"] == "order.submitTranslate"
    assert session.post_count == 1


def test_translate_timeout_reconciles_completed_order_without_resubmit(monkeypatch):
    order_support._sync_compat_globals()
    session = TimeoutSession()
    states = iter((20, 21))
    monkeypatch.setattr(order_support.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        order_support,
        "_impl__order_detail_data",
        lambda *args, **kwargs: (
            {"success": True, "code": 0},
            {"order_sn": "ORDER-1", "status": next(states), "order_detail": [{"id": 1}]},
        ),
    )

    payload, order_data, reconciliation = order_support._impl__submit_order_translate_with_reconciliation(
        session,
        "https://example.test",
        {"translate_reconcile_attempts": 2, "translate_reconcile_delay": 0},
        "ORDER-1",
        {"data": "{}", "is_temp": "0"},
        30,
    )

    assert payload["success"] is True
    assert order_data["status"] == 21
    assert reconciliation["reconciled_after_timeout"] is True
    assert reconciliation["write_state"] == "confirmed_written"
    assert reconciliation["reason_code"] == "confirmed_written"
    assert reconciliation["request_attempt_count"] == 1
    assert session.post_count == 1


def test_translate_timeout_confirms_not_written_without_blind_retry(monkeypatch):
    order_support._sync_compat_globals()
    session = TimeoutSession()
    monkeypatch.setattr(order_support.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        order_support,
        "_impl__order_detail_data",
        lambda *args, **kwargs: (
            {"success": True, "code": 0},
            {"order_sn": "ORDER-2", "status": 20, "order_detail": [{"id": 2}]},
        ),
    )

    payload, order_data, reconciliation = order_support._impl__submit_order_translate_with_reconciliation(
        session,
        "https://example.test",
        {"translate_reconcile_attempts": 2, "translate_reconcile_delay": 0},
        "ORDER-2",
        {"data": "{}", "is_temp": "0"},
        30,
    )

    assert payload["success"] is False
    assert order_data["status"] == 20
    assert reconciliation["write_state"] == "confirmed_not_written"
    assert reconciliation["reason_code"] == "confirmed_not_written"
    assert reconciliation["request_attempt_count"] == 1
    assert session.post_count == 1


def test_translate_timeout_detail_query_timeout_is_indeterminate(monkeypatch):
    order_support._sync_compat_globals()
    session = TimeoutSession()
    monkeypatch.setattr(order_support.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        order_support,
        "_impl__order_detail_data",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout("detail timed out")),
    )

    payload, order_data, reconciliation = order_support._impl__submit_order_translate_with_reconciliation(
        session,
        "https://example.test",
        {"translate_reconcile_attempts": 2, "translate_reconcile_delay": 0},
        "ORDER-QUERY-TIMEOUT",
        {"data": "{}", "is_temp": "0"},
        30,
    )

    assert payload["success"] is False
    assert order_data == {}
    assert reconciliation["write_state"] == "indeterminate"
    assert reconciliation["reason_code"] == "unknown_write_state"
    assert reconciliation["request_attempt_count"] == 1
    assert reconciliation["query_evidence"]["errors"]
    assert session.post_count == 1


def test_translate_timeout_mismatched_order_evidence_is_indeterminate(monkeypatch):
    order_support._sync_compat_globals()
    session = TimeoutSession()
    monkeypatch.setattr(order_support.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        order_support,
        "_impl__order_detail_data",
        lambda *args, **kwargs: (
            {"success": True, "code": 0},
            {"order_sn": "HISTORICAL-ORDER", "status": 21, "order_detail": [{"id": 9}]},
        ),
    )

    payload, _, reconciliation = order_support._impl__submit_order_translate_with_reconciliation(
        session,
        "https://example.test",
        {"translate_reconcile_attempts": 1, "translate_reconcile_delay": 0},
        "ORDER-CURRENT",
        {"data": "{}", "is_temp": "0"},
        30,
    )

    assert payload["success"] is False
    assert reconciliation["write_state"] == "indeterminate"
    assert reconciliation["reason_code"] == "unknown_write_state"
    assert reconciliation["query_evidence"]["conflicts"]
    assert session.post_count == 1


def test_translate_timeout_tolerates_transient_detail_lookup_failure(monkeypatch):
    order_support._sync_compat_globals()
    session = TimeoutSession()
    detail_calls = []
    monkeypatch.setattr(order_support.time, "sleep", lambda seconds: None)

    def detail_lookup(*args, **kwargs):
        detail_calls.append(1)
        if len(detail_calls) == 1:
            raise RuntimeError("detail temporarily unavailable")
        return (
            {"success": True, "code": 0},
            {"order_sn": "ORDER-RETRY", "status": 21, "order_detail": [{"id": 3}]},
        )

    monkeypatch.setattr(order_support, "_impl__order_detail_data", detail_lookup)

    payload, order_data, reconciliation = order_support._impl__submit_order_translate_with_reconciliation(
        session,
        "https://example.test",
        {"translate_reconcile_attempts": 2, "translate_reconcile_delay": 0},
        "ORDER-RETRY",
        {"data": "{}", "is_temp": "0"},
        30,
    )

    assert payload["success"] is True
    assert order_data["status"] == 21
    assert reconciliation["detail_checks"] == 2
    assert len(detail_calls) == 2
    assert session.post_count == 1


def test_initial_backend_flow_reuses_translate_reconciliation(monkeypatch):
    calls = []
    monkeypatch.setattr(order_support, "_admin_session_from", lambda variables: object())
    monkeypatch.setattr(order_support, "_admin_login", lambda *args, **kwargs: ({"success": True}, "token"))
    monkeypatch.setattr(
        order_support,
        "_order_detail_data",
        lambda *args, **kwargs: (
            {"success": True},
            {"order_sn": "ORDER-FIRST", "status": 20, "order_detail": [{"id": 1}]},
        ),
    )
    monkeypatch.setattr(order_support, "_prepare_translate_data", lambda *args, **kwargs: {"detail": []})
    monkeypatch.setattr(
        order_support,
        "_submit_order_translate_with_reconciliation",
        lambda *args, **kwargs: calls.append(1) or (
            {"success": True, "code": 0},
            {"order_sn": "ORDER-FIRST", "status": 21, "order_detail": [{"id": 1}]},
            {"write_state": "confirmed_written", "reason_code": "confirmed_written", "request_attempt_count": 1},
        ),
    )

    passed, summary = order_support._impl__run_backend_order_flow(
        "https://example.test",
        30,
        {"stop_after_node": "order_translated"},
        "ORDER-FIRST",
        1,
        {},
    )

    assert passed is True
    assert calls == [1]
    assert summary["stopped_after_node"] == "order_translated"


def test_payment_quote_returns_confirmed_written_evidence():
    reconciliation = {
        "write_state": "confirmed_written",
        "reason_code": "confirmed_written",
        "request_attempt_count": 1,
        "attempted_actions": [{"action": "order.submitTranslate", "attempt_count": 1}],
        "before_evidence": {"backend_status": 20},
        "after_evidence": {"response": {"success": True}},
        "business_diffs": {},
    }

    def run_full_flow(_env, _variables):
        log = {
            "steps": [
                {
                    "summary": {
                        "order_sn": "ORDER-EVIDENCE",
                        **reconciliation,
                        "reconciliation": reconciliation,
                    }
                }
            ]
        }
        return True, __import__("json").dumps(log), "report.json", {"order_sn": "ORDER-EVIDENCE"}

    executor = LivePaymentRegressionExecutor(object(), {})
    executor._scripts = lambda: SimpleNamespace(run_full_flow_script=run_full_flow)

    order_sn, _variables = executor._quote_order(
        ScenarioSpec("支付-006", "其他费用金额与名义", "order", "balance", "debit"),
        "BATCH-1",
    )
    evidence = executor._last_order_write_evidence

    assert order_sn == "ORDER-EVIDENCE"
    assert evidence["write_state"] == "confirmed_written"
    assert evidence["request_attempt_count"] == 1
    assert evidence["attempted_actions"][0]["action"] == "order.submitTranslate"


def test_resume_exception_uses_detected_order_node(monkeypatch):
    monkeypatch.setattr(data_scripts, "ensure_report_dirs", lambda: None)
    monkeypatch.setattr(data_scripts, "write_allure_result", lambda *args, **kwargs: "report.json")
    monkeypatch.setattr(
        data_scripts,
        "_detect_resume_order_state",
        lambda env, variables, order_sn, log: (
            True,
            {
                "order_sn": order_sn,
                "order_status": 20,
                "detected_start_node": "order_translated",
                "order_data": {"status": 20, "order_detail": [{"id": 1}]},
            },
        ),
    )
    monkeypatch.setattr(
        data_scripts,
        "_run_backend_order_flow_resume",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("translate timeout")),
    )
    env = SimpleNamespace(base_url="https://example.test", timeout=30)

    passed, _, _, summary = data_scripts.run_resume_order_flow_script(
        env,
        {"order_sn": "ORDER-3", "stop_after_node": "order_offered"},
    )

    assert passed is False
    assert summary["current_node"] == "order_translated"
    assert summary["reason"] == "translate timeout"
