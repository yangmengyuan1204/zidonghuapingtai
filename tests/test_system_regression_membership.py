from __future__ import annotations

from types import SimpleNamespace

from app.services.system_regression.membership_service import (
    apply_membership_to_variables,
    inspect_logged_in_membership,
    parse_user_info_membership,
    public_membership,
)


FIXED_USER_INFO = {
    "success": True,
    "code": 0,
    "data": {
        "current_service_rate": 0,
        "level_id": 7,
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


REGULAR_USER_INFO = {
    "success": True,
    "code": 0,
    "data": {
        "current_service_rate": 0.05,
        "level_id": 1,
        "level": {
            "currentLevel": {
                "id": 1,
                "level_type": 0,
                "level_name": "無料会員",
                "service_rate": "0.05",
            }
        },
    },
}


def test_parse_user_info_detects_fixed_membership_and_zero_service_rate():
    result = parse_user_info_membership(FIXED_USER_INFO)

    assert result["kind"] == "fixed"
    assert result["level_name"] == "定額会員"
    assert result["service_rate"] == "0"
    assert result["preview_cny_to_jpy"] == "21.10"


def test_parse_user_info_detects_regular_membership_and_service_rate():
    result = parse_user_info_membership(REGULAR_USER_INFO)

    assert result["kind"] == "regular"
    assert result["level_name"] == "無料会員"
    assert result["service_rate"] == "0.05"
    assert result["preview_cny_to_jpy"] == "21.20"


def test_vip_and_svip_names_count_as_fixed_membership():
    vip = parse_user_info_membership({"data": {"level": {"currentLevel": {"level_name": "VIP", "level_type": 0, "service_rate": "0"}}}})
    svip = parse_user_info_membership({"data": {"level": {"currentLevel": {"level_name": "SVIP", "level_type": 0, "service_rate": "0"}}}})

    assert vip["kind"] == "fixed"
    assert svip["kind"] == "fixed"


def test_apply_membership_does_not_overwrite_existing_service_rate():
    variables = {"service_rate": "0.10"}
    apply_membership_to_variables(variables, parse_user_info_membership(FIXED_USER_INFO))

    assert variables["membership_kind"] == "fixed"
    assert variables["service_rate"] == "0.10"


def test_inspect_logged_in_membership_uses_user_info_path():
    calls = []

    class FakeClient:
        def __init__(self):
            self.session = SimpleNamespace(headers={"clienttoken": "token"})

        def post_form(self, path, fields):
            calls.append((path, dict(fields)))
            return FIXED_USER_INFO

    result = inspect_logged_in_membership(FakeClient(), {})

    assert calls[0][0] == "/client/user.info"
    assert result["kind"] == "fixed"
    assert public_membership(result)["service_rate"] == "0"


def test_payment_runner_uses_membership_and_does_not_force_exchange_rate(monkeypatch):
    from app.system_regression.projects.japan.payment_runner import PaymentRunner

    monkeypatch.setattr(
        "app.system_regression.projects.japan.payment_runner.inspect_membership_from_env",
        lambda _env, _variables: {
            "kind": "fixed",
            "level_name": "定額会員",
            "level_id": "7",
            "level_type": "1",
            "service_rate": "0",
            "preview_cny_to_jpy": "21.10",
            "source": "client_user_info",
            "reason": "",
        },
    )
    captured = {}

    class FakeExecutor:
        def __init__(self, variables):
            captured.update(variables)

        def execute(self, _scenario, _batch_no):
            return {"status": "passed", "order_sn": "O1", "checks": [{"passed": True}]}

    runner = PaymentRunner(
        env=object(),
        executor_factory=lambda _env, variables: FakeExecutor(variables),
    )
    result = runner.execute(
        {
            "case_key": "配送-003",
            "name": "配送单余额支付",
            "runner_kind": "porder_payment",
            "parameters": {"payment_mode": "balance"},
            "expectation": {"direction": "debit"},
        },
        {"batch_no": "B1", "variables": {}},
    )

    assert captured["membership_kind"] == "fixed"
    assert captured["service_rate"] == "0"
    assert "japan_fixed_cny_to_jpy" not in captured
    assert result.result["membership"]["kind"] == "fixed"
    assert result.result["membership"]["preview_cny_to_jpy"] == "21.10"
