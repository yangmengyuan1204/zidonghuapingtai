import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import data_scripts
from app.core.data_script_catalog import DATA_SCRIPT_API_CASES
from app.data_scripts import balance_adjustment
from app.data_scripts.balance_adjustment import (
    BalanceAdjustmentRequestUncertain,
    run_balance_adjustment_script,
)
from app.database import SessionLocal
from app.main import app
from app.models import ApiCase, Project


def _env():
    return SimpleNamespace(base_url="https://jpapi.test", timeout=25)


def _payload(data):
    return {"success": True, "code": 0, "msg": "操作成功", "data": data}


def _application_row(
    application_id=21,
    *,
    customer_id="300001",
    adjustment_type=1,
    amount="10",
    adjust_reason="测试申请原因",
    client_bill_reason="测试出入金名义",
    status=0,
):
    return {
        "id": application_id,
        "user_id": int(customer_id),
        "amount": amount,
        "adjust_reason": adjust_reason,
        "client_bill_reason": client_bill_reason,
        "type": adjustment_type,
        "status": status,
        "status_name": "审核通过" if status == 1 else "待审核",
    }


class ApiStub:
    def __init__(self, *, adjustment_type=1, balance_before="100", amount="10"):
        self.adjustment_type = adjustment_type
        self.balance_before = balance_before
        self.amount = amount
        self.customer_id = "300001"
        self.adjust_reason = "测试申请原因"
        self.client_bill_reason = "测试出入金名义"
        expected = float(balance_before) + float(amount) if adjustment_type == 1 else float(balance_before) - float(amount)
        self.balance_after = str(int(expected) if expected.is_integer() else expected)
        self.info_id = self.customer_id
        self.info_success = True
        self.pending_before = []
        self.pending_after = [self.row(status=0)]
        self.approved_rows = [self.row(status=1)]
        self.create_payload = _payload("")
        self.confirm_payload = _payload("")
        self.create_uncertain = False
        self.confirm_uncertain = False
        self.info_calls = 0
        self.pending_calls = 0
        self.calls = []

    def row(self, application_id=21, status=0):
        return _application_row(
            application_id,
            customer_id=self.customer_id,
            adjustment_type=self.adjustment_type,
            amount=self.amount,
            adjust_reason=self.adjust_reason,
            client_bill_reason=self.client_bill_reason,
            status=status,
        )

    def request(self, _session, _base_url, path, fields, _timeout, *, read_only, attempts=3):
        self.calls.append({"path": path, "fields": dict(fields), "read_only": read_only, "attempts": attempts})
        if path.endswith("jpanfirm.clientInfo"):
            self.info_calls += 1
            balance = self.balance_before if self.info_calls == 1 else self.balance_after
            data = {
                "id": int(self.info_id),
                "username": "测试客户账号",
                "realname": "测试客户",
                "account_status": "正常",
                "balance": balance,
            }
            return _payload(data) if self.info_success else {"success": False, "code": 1, "msg": "客户不存在", "data": ""}
        if path.endswith("bill.adjustApplication.create"):
            if self.create_uncertain:
                raise BalanceAdjustmentRequestUncertain("创建请求结果不确定")
            return self.create_payload
        if path.endswith("bill.adjustApplication.confirm"):
            if self.confirm_uncertain:
                raise BalanceAdjustmentRequestUncertain("审核请求结果不确定")
            return self.confirm_payload
        if path.endswith("bill.adjustApplication.list"):
            status = int(fields["status"])
            if status == 0:
                self.pending_calls += 1
                rows = self.pending_before if self.pending_calls == 1 else self.pending_after
            else:
                rows = self.approved_rows
            return _payload({"data": rows, "pageSize": "100", "currentPage": 1, "total": len(rows)})
        raise AssertionError(f"unexpected path: {path}")

    def variables(self, **extra):
        values = {
            "customer_id": self.customer_id,
            "customer_ids": [self.customer_id],
            "adjust_reason": self.adjust_reason,
            "adjustment_type": str(self.adjustment_type),
            "amount": self.amount,
            "client_bill_reason": self.client_bill_reason,
            "balance_adjustment_poll_retries": 1,
            "balance_adjustment_poll_delay": 0,
        }
        values.update(extra)
        return values


@pytest.fixture()
def patched(monkeypatch):
    session = MagicMock()
    session.headers = {}
    monkeypatch.setattr(balance_adjustment, "ensure_report_dirs", lambda: None)
    monkeypatch.setattr(balance_adjustment, "_admin_session_from", lambda _variables: session)
    monkeypatch.setattr(
        balance_adjustment,
        "_admin_login",
        lambda *_args, **_kwargs: (_payload({"access_token": "admin-token"}), "admin-token"),
    )
    monkeypatch.setattr(balance_adjustment.time, "sleep", lambda *_args, **_kwargs: None)

    def finish(_name, log, passed, summary):
        return passed, json.dumps(log, ensure_ascii=False, default=str), "", summary

    monkeypatch.setattr(balance_adjustment, "_finish_named", finish)

    def install(stub):
        monkeypatch.setattr(balance_adjustment, "_request_urlencoded", stub.request)
        return stub

    return install


@pytest.mark.parametrize(
    ("adjustment_type", "balance_before", "amount", "balance_after", "type_name"),
    [
        (1, "100", "10", "110", "入金调整"),
        (2, "100", "10", "90", "出金调整"),
    ],
)
def test_happy_path_adjusts_and_verifies_balance(
    patched,
    adjustment_type,
    balance_before,
    amount,
    balance_after,
    type_name,
):
    stub = patched(ApiStub(adjustment_type=adjustment_type, balance_before=balance_before, amount=amount))

    passed, _log, _report, summary = run_balance_adjustment_script(_env(), stub.variables())

    assert passed is True
    assert summary["application_id"] == 21
    assert summary["adjustment_type_name"] == type_name
    assert summary["balance_before"] == balance_before
    assert summary["balance_after"] == balance_after
    assert summary["review_passed"] is True
    assert summary["balance_verified"] is True
    create_calls = [call for call in stub.calls if call["path"].endswith("bill.adjustApplication.create")]
    confirm_calls = [call for call in stub.calls if call["path"].endswith("bill.adjustApplication.confirm")]
    assert len(create_calls) == 1
    assert len(confirm_calls) == 1
    assert create_calls[0]["read_only"] is False
    assert confirm_calls[0]["read_only"] is False
    assert confirm_calls[0]["fields"] == {"id": 21, "confirm_remark": ""}


@pytest.mark.parametrize(
    ("variables", "reason_marker"),
    [
        ({"adjustment_type": "1", "amount": "1", "adjust_reason": "原因", "client_bill_reason": "名义"}, "customer_id"),
        ({"customer_id": "abc", "adjustment_type": "1", "amount": "1", "adjust_reason": "原因", "client_bill_reason": "名义"}, "数字"),
        ({"customer_id": "1", "adjustment_type": "3", "amount": "1", "adjust_reason": "原因", "client_bill_reason": "名义"}, "adjustment_type"),
        ({"customer_id": "1", "adjustment_type": "1", "amount": "0", "adjust_reason": "原因", "client_bill_reason": "名义"}, "正数"),
        ({"customer_id": "1", "adjustment_type": "1", "amount": "1", "adjust_reason": "", "client_bill_reason": "名义"}, "adjust_reason"),
        ({"customer_id": "1", "adjustment_type": "1", "amount": "1", "adjust_reason": "原因", "client_bill_reason": ""}, "client_bill_reason"),
        ({"customer_ids": ["1", "2"], "adjustment_type": "1", "amount": "1", "adjust_reason": "原因", "client_bill_reason": "名义"}, "单客户"),
    ],
)
def test_parameter_validation_stops_before_http(patched, variables, reason_marker):
    stub = patched(ApiStub())
    passed, _log, _report, summary = run_balance_adjustment_script(_env(), variables)
    assert passed is False
    assert reason_marker in summary["reason"]
    assert stub.calls == []


def test_customer_lookup_failure_stops_before_create(patched):
    stub = patched(ApiStub())
    stub.info_success = False
    passed, _log, _report, summary = run_balance_adjustment_script(_env(), stub.variables())
    assert passed is False
    assert "客户不存在" in summary["reason"]
    assert not any(call["path"].endswith("bill.adjustApplication.create") for call in stub.calls)


def test_customer_id_mismatch_stops_before_create(patched):
    stub = patched(ApiStub())
    stub.info_id = "71"
    passed, _log, _report, summary = run_balance_adjustment_script(_env(), stub.variables())
    assert passed is False
    assert "客户ID与输入不一致" in summary["reason"]
    assert not any(call["path"].endswith("bill.adjustApplication.create") for call in stub.calls)


def test_withdrawal_larger_than_balance_stops_before_create(patched):
    stub = patched(ApiStub(adjustment_type=2, balance_before="50", amount="100"))
    passed, _log, _report, summary = run_balance_adjustment_script(_env(), stub.variables())
    assert passed is False
    assert "超过客户当前余额" in summary["reason"]
    assert not any(call["path"].endswith("bill.adjustApplication.create") for call in stub.calls)


def test_existing_matching_pending_application_blocks_duplicate(patched):
    stub = ApiStub()
    stub.pending_before = [stub.row(application_id=11, status=0)]
    stub = patched(stub)
    passed, _log, _report, summary = run_balance_adjustment_script(_env(), stub.variables())
    assert passed is False
    assert summary["existing_application_ids"] == [11]
    assert summary["manual_review_required"] is True
    assert summary["retry_forbidden"] is True
    assert not any(call["path"].endswith("bill.adjustApplication.create") for call in stub.calls)


@pytest.mark.parametrize("candidate_count", [0, 2])
def test_new_application_must_be_unique(patched, candidate_count):
    stub = ApiStub()
    stub.pending_after = [stub.row(application_id=21 + index, status=0) for index in range(candidate_count)]
    stub = patched(stub)
    passed, _log, _report, summary = run_balance_adjustment_script(_env(), stub.variables())
    assert passed is False
    assert summary["application_created"] is True
    assert summary["manual_review_required"] is True
    assert summary["retry_forbidden"] is True
    assert not any(call["path"].endswith("bill.adjustApplication.confirm") for call in stub.calls)


def test_create_transport_uncertainty_forbids_retry(patched):
    stub = ApiStub()
    stub.create_uncertain = True
    stub = patched(stub)
    passed, _log, _report, summary = run_balance_adjustment_script(_env(), stub.variables())
    assert passed is False
    assert summary["application_created"] is None
    assert summary["manual_review_required"] is True
    assert summary["retry_forbidden"] is True


def test_confirm_failure_requires_manual_review(patched):
    stub = ApiStub()
    stub.confirm_payload = {"success": False, "code": 1, "msg": "审核失败", "data": ""}
    stub.approved_rows = []
    stub.balance_after = stub.balance_before
    stub = patched(stub)
    passed, _log, _report, summary = run_balance_adjustment_script(_env(), stub.variables())
    assert passed is False
    assert "审核失败" in summary["reason"]
    assert summary["manual_review_required"] is True
    assert summary["retry_forbidden"] is True


def test_balance_mismatch_after_approval_requires_manual_review(patched):
    stub = ApiStub()
    stub.balance_after = "109"
    stub = patched(stub)
    passed, _log, _report, summary = run_balance_adjustment_script(_env(), stub.variables())
    assert passed is False
    assert summary["review_passed"] is True
    assert summary["balance_verified"] is False
    assert summary["retry_forbidden"] is True


def test_confirm_uncertain_can_be_proven_by_read_only_verification(patched):
    stub = ApiStub()
    stub.confirm_uncertain = True
    stub = patched(stub)
    passed, _log, _report, summary = run_balance_adjustment_script(_env(), stub.variables())
    assert passed is True
    assert "返回不确定" in summary["warning"]


def test_script_registry_registered():
    assert data_scripts.SCRIPT_REGISTRY["balance_adjustment"]["func"] is run_balance_adjustment_script
    assert data_scripts.SCRIPT_REGISTRY["balance_adjustment"]["name"] == "出入金调整"


def test_api_cases_are_seeded_into_japan_project():
    keys = {item["key"] for item in DATA_SCRIPT_API_CASES if item["key"].startswith("admin_balance_adjustment_")}
    assert keys == {
        "admin_balance_adjustment_client_info",
        "admin_balance_adjustment_create",
        "admin_balance_adjustment_list",
        "admin_balance_adjustment_confirm",
    }
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.name == "日本站测试").one()
        urls = {
            row.url
            for row in db.query(ApiCase).filter(ApiCase.project_id == project.id).all()
            if "adjustApplication" in row.url or row.url == "/jpanfirm.clientInfo"
        }
        assert urls == {
            "/jpanfirm.clientInfo",
            "/bill.adjustApplication.create",
            "/bill.adjustApplication.list",
            "/bill.adjustApplication.confirm",
        }
    finally:
        db.close()


def _login(client, username, password):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_route_requires_platform_admin(monkeypatch):
    with TestClient(app) as client:
        admin_headers = _login(client, "admin", "admin123")
        created = client.post(
            "/api/users",
            headers=admin_headers,
            json={"username": "balance_adjust_reader", "password": "reader123", "role": "normal"},
        )
        assert created.status_code == 200, created.text
        normal_headers = _login(client, "balance_adjust_reader", "reader123")
        payload = {
            "variables": {
                "customer_id": "300001",
                "adjust_reason": "权限测试",
                "adjustment_type": "1",
                "amount": "1",
                "client_bill_reason": "权限测试",
            }
        }
        denied = client.post("/api/data-scripts/balance-adjustment", headers=normal_headers, json=payload)
        assert denied.status_code == 403

        monkeypatch.setattr(
            "app.routers.data_scripts.run_balance_adjustment_script",
            lambda _env, _variables: (True, "{}", "", {"application_id": 21}),
        )
        allowed = client.post("/api/data-scripts/balance-adjustment", headers=admin_headers, json=payload)
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["result"] == "passed"
