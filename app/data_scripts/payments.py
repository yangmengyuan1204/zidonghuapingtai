from collections import OrderedDict
from datetime import datetime
import sys
import time
from typing import Any, Dict, Tuple

from ..executors import ensure_report_dirs
from ..models import Env


_COMPAT_NAMES = (
    "BALANCE_RECHARGE_SCRIPT_NAME",
    "_admin_login",
    "_admin_session_from",
    "_api_path",
    "_api_success",
    "_apply_extra_fields",
    "_as_bool",
    "_as_float",
    "_as_int",
    "_call_with_retry",
    "_finance_bill_brief",
    "_finance_rows_from_payload",
    "_finance_unconfirm_fields",
    "_finish_named",
    "_login_client_for_payment",
    "_payload_brief",
    "_positive_decimal",
    "_post_admin_form",
    "_select_finance_bill",
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _run_balance_recharge_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """\u4f59\u989d\u5145\u503c\u811a\u672c - \u524d\u53f0\u63d0\u4ea4\u94f6\u884c\u5145\u503c\u7533\u8bf7\uff0c\u540e\u53f0\u767b\u5f55\u540e\u786e\u8ba4\u5165\u91d1\uff0c\u5145\u503c\u91d1\u989d\u5230\u8fbe\u8be5\u8d26\u53f7\u4f59\u989d\u3002

    \u63a5\u53e3\uff1a
    - \u524d\u53f0\u63d0\u4ea4 POST /client/user.bankPayBalance (ClientToken)
      \u5b57\u6bb5: pay_bank_method, pay_reach_date, pay_date, pay_name, pay_amount, pay_remark
    - \u540e\u53f0\u67e5\u8be2 POST /bill.unConfirmList (AdminToken)
    - \u540e\u53f0\u786e\u8ba4 POST /bill.confirm (AdminToken)  \u5b57\u6bb5: id

    \u53ef\u914d\u7f6e\u53d8\u91cf\uff1a
    - customer_id: \u5fc5\u586b\uff0c\u5145\u503c\u5230\u8be5\u5ba2\u6237\u4f59\u989d\uff08\u7531\u524d\u7aef/\u8def\u7531\u5c42\u6ce8\u5165\uff09
    - amount: \u5fc5\u586b\uff0c\u5145\u503c\u91d1\u989d\uff08\u6620\u5c04\u5230 pay_amount\uff09
    - pay_bank_method / pay_date / pay_reach_date / pay_name / pay_remark\uff1a\u53ef\u8986\u76d6\u9ed8\u8ba4\u503c
    - client_recharge\uff1a\u524d\u53f0\u5145\u503c\u63d0\u4ea4\u63a5\u53e3\uff08\u9ed8\u8ba4 /client/user.bankPayBalance\uff09
    - finance_confirm\uff1a\u662f\u5426\u6267\u884c\u540e\u53f0\u786e\u8ba4\uff08\u9ed8\u8ba4 True\uff09
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    customer_id = str(variables.get("customer_id") or "").strip()
    amount = str(variables.get("amount") or variables.get("recharge_amount") or "").strip()
    log: Dict[str, Any] = {
        "script": BALANCE_RECHARGE_SCRIPT_NAME,
        "mode": "balance_recharge",
        "started_at": datetime.now(),
        "customer_id": customer_id,
        "amount": amount,
        "recharge": {},
        "finance": {},
    }

    if not customer_id:
        return _finish_named(
            BALANCE_RECHARGE_SCRIPT_NAME, log, False,
            {"reason": "\u7f3a\u5c11\u5fc5\u586b\u53c2\u6570\uff1acustomer_id \u4e0d\u80fd\u4e3a\u7a7a"},
        )
    if not _positive_decimal(amount):
        return _finish_named(
            BALANCE_RECHARGE_SCRIPT_NAME, log, False,
            {"reason": "\u7f3a\u5c11\u5fc5\u586b\u53c2\u6570\uff1a\u5145\u503c\u91d1\u989d amount \u5fc5\u987b\u4e3a\u6b63\u6570"},
        )

    try:
        client, base_url, timeout, _ = _login_client_for_payment(env, variables, log)
        log["base_url"] = base_url

        # Step 1: 前台提交充值申请 POST /client/user.bankPayBalance
        now = datetime.now()
        pay_bank_method = str(variables.get("pay_bank_method") or "2")
        pay_date = str(variables.get("pay_date") or now.strftime("%Y/%m/%d %H:%M:%S"))
        pay_reach_date = str(variables.get("pay_reach_date") or now.strftime("%Y-%m-%d 00:00:00"))
        pay_name = str(variables.get("pay_name") or "\u81ea\u52a8\u5316\u5145\u503c")
        pay_remark = str(variables.get("pay_remark") or "")
        fields: OrderedDict[str, Any] = OrderedDict()
        fields["pay_bank_method"] = pay_bank_method
        fields["pay_reach_date"] = pay_reach_date
        fields["pay_date"] = pay_date
        fields["pay_name"] = pay_name
        fields["pay_amount"] = amount
        fields["pay_remark"] = pay_remark
        _apply_extra_fields(fields, variables.get("recharge_fields"))
        recharge_payload = _call_with_retry(
            "balance recharge",
            lambda: client.post_form(_api_path(variables, "client_recharge", "/client/user.bankPayBalance"), fields),
        )
        recharge_ok = _api_success(recharge_payload)
        recharge_data = recharge_payload.get("data") if isinstance(recharge_payload.get("data"), dict) else {}
        serial_number = str(recharge_data.get("serial_number") or recharge_data.get("recharge_no") or recharge_data.get("bill_no") or "")
        log["recharge"] = {**_payload_brief(recharge_payload), "request": dict(fields), "serial_number": serial_number}
        if not recharge_ok:
            reason = str(recharge_payload.get("msg") or recharge_payload.get("data") or "\u524d\u53f0\u5145\u503c\u63d0\u4ea4\u5931\u8d25")
            return _finish_named(
                BALANCE_RECHARGE_SCRIPT_NAME, log, False,
                {
                    "recharge_type": "balance",
                    "customer_id": customer_id,
                    "amount": amount,
                    "serial_number": serial_number,
                    "recharge_passed": False,
                    "confirm_passed": False,
                    "reason": reason,
                },
            )

        # Step 2: 后台确认入金
        finance_confirm = _as_bool(variables.get("finance_confirm"), True)
        confirm_ok = True
        if finance_confirm:
            session = _admin_session_from(variables)
            login_payload, token = _admin_login(session, base_url, variables, timeout)
            log["finance"]["login"] = {
                **_payload_brief(login_payload),
                "account": str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
                "token_extracted": bool(token),
            }
            if not _api_success(login_payload) or not token:
                confirm_ok = False
                log["finance"]["reason"] = "\u540e\u53f0\u767b\u5f55\u5931\u8d25"
            else:
                initial_delay = _as_float(variables.get("finance_confirm_initial_delay"), 2.0)
                retry_delay = _as_float(variables.get("finance_confirm_delay"), 2.0)
                retries = _as_int(variables.get("finance_confirm_retries"), 6)
                if initial_delay > 0:
                    time.sleep(initial_delay)
                list_payload: Dict[str, Any] = {}
                confirm_payload: Dict[str, Any] = {}
                selected_bill: Dict[str, Any] | None = None
                for attempt in range(retries):
                    list_fields = _finance_unconfirm_fields(variables, serial_number, "")
                    list_payload = _post_admin_form(
                        session,
                        base_url,
                        _api_path(variables, "admin_bill_unconfirm_list", "/bill.unConfirmList"),
                        list_fields,
                        timeout,
                    )
                    rows = _finance_rows_from_payload(list_payload)
                    selected_bill = _select_finance_bill(rows, serial_number, "")
                    if _api_success(list_payload) and selected_bill and selected_bill.get("id") not in (None, ""):
                        break
                    if attempt < retries - 1:
                        time.sleep(retry_delay)
                log["finance"]["unconfirm_list"] = {**_payload_brief(list_payload), "serial_number": serial_number, "selected_bill": _finance_bill_brief(selected_bill)}
                if _api_success(list_payload) and selected_bill and selected_bill.get("id") not in (None, ""):
                    confirm_payload = _post_admin_form(
                        session,
                        base_url,
                        _api_path(variables, "admin_bill_confirm", "/bill.confirm"),
                        {"id": selected_bill.get("id")},
                        timeout,
                    )
                    confirm_ok = _api_success(confirm_payload)
                    log["finance"]["confirm"] = {**_payload_brief(confirm_payload), "request": {"id": selected_bill.get("id")}}
                else:
                    confirm_ok = False
                    log["finance"]["confirm"] = {"serial_number": serial_number, "selected_bill": _finance_bill_brief(selected_bill)}
                if not confirm_ok:
                    last_payload = confirm_payload or list_payload
                    last_msg = last_payload.get("msg") or last_payload.get("data") or "\u8d22\u52a1\u786e\u8ba4\u5165\u91d1\u5931\u8d25"
                    log["finance"]["reason"] = f"\u8d22\u52a1\u786e\u8ba4\u5165\u91d1\u5931\u8d25\uff1a{last_msg}"

        passed = recharge_ok and confirm_ok
        summary = {
            "recharge_type": "balance",
            "customer_id": customer_id,
            "amount": amount,
            "serial_number": serial_number,
            "recharge_passed": recharge_ok,
            "confirm_passed": confirm_ok,
        }
        if not passed and "reason" not in summary:
            summary["reason"] = log.get("finance", {}).get("reason") or "\u4f59\u989d\u5145\u503c\u5931\u8d25"
        return _finish_named(BALANCE_RECHARGE_SCRIPT_NAME, log, passed, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            BALANCE_RECHARGE_SCRIPT_NAME, log, False,
            {"recharge_type": "balance", "customer_id": customer_id, "amount": amount, "reason": str(exc)},
        )


def run_balance_recharge_script(
    env: Env,
    variables: Dict[str, Any] | None = None,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _run_balance_recharge_script(env, variables)
