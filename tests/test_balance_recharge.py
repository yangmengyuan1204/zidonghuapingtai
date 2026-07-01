"""余额充值数据脚本测试。

基于真实接口：
- 前台提交 POST /client/user.bankPayBalance (ClientToken)
  字段: pay_bank_method, pay_reach_date, pay_date, pay_name, pay_amount, pay_remark
- 后台查询待确认 POST /bill.unConfirmList (AdminToken)
- 后台确认入金 POST /bill.confirm (AdminToken)
  字段: id
  返回: {"success":true,"code":0,"msg":"操作成功","data":true}

脚本字段（对齐其他数据脚本的客户ID机制）：
- customer_ids: 必填，多个客户ID（前端 textarea，支持换行/逗号分隔）
  前端 runMultiCustomerFlow 会遍历每个 customerId 逐个调用本脚本
- customer_id: 单客户执行时由前端 variablesForCustomerId 注入
- amount: 必填，充值金额（映射到 pay_amount，必须为正数）

多客户批量由前端 runMultiCustomerFlow 负责，后端只处理单客户。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import data_scripts
from app.data_scripts import run_balance_recharge_script


def _env():
    return SimpleNamespace(base_url="http://jpapi.test", timeout=25)


@pytest.fixture()
def patched(monkeypatch):
    """统一 mock 外部 HTTP 依赖，返回一个可现场配置的桩。"""
    client = MagicMock()
    session = MagicMock()
    stub = SimpleNamespace(
        client=client,
        session=session,
        login_payload={"success": True, "code": 0, "data": {"access_token": "adm-token"}},
        recharge_payload={"success": True, "code": 0, "msg": "操作成功", "data": {"serial_number": "RC20260629001"}},
        list_payload={"success": True, "code": 0, "data": {"data": [{"id": 88, "serial_number": "RC20260629001", "pay_amount": "100"}]}},
        confirm_payload={"success": True, "code": 0, "msg": "操作成功", "data": True},
        admin_post_calls=[],
        login_calls=[],
    )
    client.post_form = MagicMock(side_effect=lambda *a, **k: stub.recharge_payload)

    def _login_client_for_payment(env, variables, log):
        account = variables.get("account", "")
        stub.login_calls.append(account)
        log["login"] = {"success": True, "account": account}
        return client, "http://jpapi.test", 25, "cli-token"

    def _admin_session_from(variables):
        return session

    def _admin_login(sess, base_url, variables, timeout):
        return stub.login_payload, "adm-token"

    def _post_admin_form(sess, base_url, path, fields, timeout):
        stub.admin_post_calls.append({"path": path, "fields": dict(fields)})
        if "unConfirmList" in path:
            return stub.list_payload
        if path.endswith("bill.confirm") or "bill.confirm" in path:
            return stub.confirm_payload
        return {"success": True, "code": 0}

    monkeypatch.setattr(data_scripts, "_login_client_for_payment", _login_client_for_payment)
    monkeypatch.setattr(data_scripts, "_admin_session_from", _admin_session_from)
    monkeypatch.setattr(data_scripts, "_admin_login", _admin_login)
    monkeypatch.setattr(data_scripts, "_post_admin_form", _post_admin_form)
    monkeypatch.setattr(data_scripts.time, "sleep", lambda *a, **k: None)
    return stub


# ── 参数校验 ──────────────────────────────────────────────


def test_missing_customer_id_fails(patched):
    passed, _log, _report, summary = run_balance_recharge_script(_env(), {"amount": "100"})
    assert passed is False
    assert "customer_id" in summary.get("reason", "")


def test_missing_amount_fails(patched):
    passed, _log, _report, summary = run_balance_recharge_script(_env(), {"customer_id": "300001"})
    assert passed is False
    assert "金额" in summary.get("reason", "") or "amount" in summary.get("reason", "").lower()


def test_invalid_amount_fails(patched):
    passed, _log, _report, summary = run_balance_recharge_script(_env(), {"customer_id": "300001", "amount": "0"})
    assert passed is False


def test_negative_amount_fails(patched):
    passed, _log, _report, summary = run_balance_recharge_script(_env(), {"customer_id": "300001", "amount": "-50"})
    assert passed is False


# ── 正常路径 ──────────────────────────────────────────────


def test_happy_path_recharge_and_confirm(patched):
    passed, _log, _report, summary = run_balance_recharge_script(
        _env(), {"customer_id": "300001", "amount": "500.00", "account": "userID/300001In", "password": "pwd"}
    )
    assert passed is True
    assert summary["customer_id"] == "300001"
    assert summary["amount"] == "500.00"
    assert summary["serial_number"] == "RC20260629001"
    assert summary["recharge_passed"] is True
    assert summary["confirm_passed"] is True
    # 前台提交字段对齐真实接口
    assert patched.client.post_form.call_count == 1
    _path, fields = patched.client.post_form.call_args[0]
    assert fields["pay_amount"] == "500.00"
    assert "pay_bank_method" in fields
    assert "pay_date" in fields
    assert "pay_reach_date" in fields
    assert "pay_name" in fields
    assert "pay_remark" in fields
    # 后台先查未确认列表，再确认
    paths = [call["path"] for call in patched.admin_post_calls]
    assert any("unConfirmList" in p for p in paths)
    assert any(p.endswith("bill.confirm") or "bill.confirm" in p for p in paths)
    # 确认请求字段为 id
    confirm_call = next(c for c in patched.admin_post_calls if "bill.confirm" in c["path"])
    assert "id" in confirm_call["fields"]


def test_customer_id_drives_login_account(patched):
    """customer_id 决定前台登录账号（由路由层 apply_frontend_customer_login_variables 注入 account）。"""
    passed, _log, _report, _summary = run_balance_recharge_script(
        _env(), {"customer_id": "71", "amount": "100", "account": "userID/71In", "password": "pwd"}
    )
    assert passed is True
    assert patched.login_calls == ["userID/71In"]


def test_recharge_uses_configurable_client_path(patched, monkeypatch):
    captured = {}
    original_api_path = data_scripts._api_path

    def _api_path(variables, key, default):
        if key == "client_recharge":
            captured["client_path"] = str(variables["api_paths"]["client_recharge"])
            return captured["client_path"]
        return original_api_path(variables, key, default)

    monkeypatch.setattr(data_scripts, "_api_path", _api_path)
    passed, _log, _report, _summary = run_balance_recharge_script(
        _env(),
        {
            "customer_id": "300001",
            "amount": "100",
            "account": "userID/300001In",
            "password": "pwd",
            "api_paths": {"client_recharge": "/client/wallet.customRecharge"},
        },
    )
    assert passed is True
    assert captured["client_path"] == "/client/wallet.customRecharge"


def test_pay_name_defaults_to_auto_recharge(patched):
    """pay_name 默认为'自动化充值'。"""
    passed, _log, _report, _summary = run_balance_recharge_script(
        _env(), {"customer_id": "300001", "amount": "100", "account": "userID/300001In", "password": "pwd"}
    )
    assert passed is True
    _path, fields = patched.client.post_form.call_args[0]
    assert fields["pay_name"] == "\u81ea\u52a8\u5316\u5145\u503c"


# ── 失败分支 ──────────────────────────────────────────────


def test_recharge_submit_failure_fails(patched):
    patched.recharge_payload = {"success": False, "code": 500, "msg": "\u5145\u503c\u63a5\u53e3\u5f02\u5e38"}
    passed, _log, _report, summary = run_balance_recharge_script(
        _env(), {"customer_id": "300001", "amount": "100", "account": "userID/300001In", "password": "pwd"}
    )
    assert passed is False
    assert summary["recharge_passed"] is False


def test_no_bill_found_fails(patched):
    patched.list_payload = {"success": True, "code": 0, "data": {"data": []}}
    passed, _log, _report, summary = run_balance_recharge_script(
        _env(), {"customer_id": "300001", "amount": "100", "account": "userID/300001In", "password": "pwd"}
    )
    assert passed is False
    assert summary["confirm_passed"] is False


def test_confirm_failure_fails(patched):
    patched.confirm_payload = {"success": False, "code": 1, "msg": "\u786e\u8ba4\u5931\u8d25"}
    passed, _log, _report, summary = run_balance_recharge_script(
        _env(), {"customer_id": "300001", "amount": "100", "account": "userID/300001In", "password": "pwd"}
    )
    assert passed is False
    assert summary["confirm_passed"] is False


def test_admin_login_failure_fails(patched):
    stub_login = {"success": False, "code": 1, "msg": "\u540e\u53f0\u767b\u5f55\u5931\u8d25"}
    patched.login_payload = stub_login
    monkeypatch_patch = pytest.MonkeyPatch()
    monkeypatch_patch.setattr(data_scripts, "_admin_login", lambda *a, **k: (stub_login, ""))
    passed, _log, _report, _summary = run_balance_recharge_script(
        _env(), {"customer_id": "300001", "amount": "100", "account": "userID/300001In", "password": "pwd"}
    )
    assert passed is False
    monkeypatch_patch.undo()


def test_script_registry_registered():
    reg = data_scripts.SCRIPT_REGISTRY
    assert "balance_recharge" in reg
    assert reg["balance_recharge"]["name"] == data_scripts.BALANCE_RECHARGE_SCRIPT_NAME
    assert reg["balance_recharge"]["func"] is run_balance_recharge_script
