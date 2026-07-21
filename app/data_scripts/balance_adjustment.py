from __future__ import annotations

import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Tuple
from urllib.parse import urljoin

import requests

from ..executors import ensure_report_dirs
from ..models import Env
from .cart_support import _api_success
from .data_script_shared import _admin_session_from, _finish_named
from .order_support import _admin_login


BALANCE_ADJUSTMENT_SCRIPT_NAME = "出入金调整"
BALANCE_ADJUSTMENT_TYPE_NAMES = {1: "入金调整", 2: "出金调整"}


class BalanceAdjustmentRequestUncertain(RuntimeError):
    """资金写请求已发出，但无法确认服务端是否完成处理。"""


def _api_path(variables: Dict[str, Any], key: str, default: str) -> str:
    paths = variables.get("api_paths")
    configured = paths.get(key) if isinstance(paths, dict) else None
    return str(configured or variables.get(f"{key}_path") or default)


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _as_positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _as_non_negative_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _customer_ids(variables: Dict[str, Any]) -> list[str]:
    raw = variables.get("customer_ids")
    raw_items = raw if isinstance(raw, list) else [raw]
    ids: list[str] = []
    for item in raw_items:
        if item in (None, ""):
            continue
        ids.extend(part for part in re.split(r"[\s,，;；]+", str(item).strip()) if part)
    customer_id = str(variables.get("customer_id") or "").strip()
    if customer_id:
        ids.append(customer_id)
    return list(dict.fromkeys(ids))


def _brief(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {key: payload.get(key) for key in ("success", "code", "msg", "message") if key in payload}


def _request_urlencoded(
    session: requests.Session,
    base_url: str,
    path: str,
    fields: Dict[str, Any],
    timeout: int,
    *,
    read_only: bool,
    attempts: int = 3,
) -> Dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request_attempts = max(1, attempts if read_only else 1)
    last_error: Exception | None = None
    for attempt in range(request_attempts):
        try:
            response = session.post(
                url,
                data={str(key): "" if value is None else str(value) for key, value in fields.items()},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("接口返回不是 JSON 对象")
            return payload
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < request_attempts - 1:
                time.sleep(0.8 * (attempt + 1))
    if read_only:
        raise RuntimeError(f"读取接口 {path} 失败：{last_error}")
    raise BalanceAdjustmentRequestUncertain(f"资金接口 {path} 返回结果不确定：{last_error}")


def _rows_from_list(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = payload.get("data")
    rows = data.get("data") if isinstance(data, dict) else None
    return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []


def _row_matches(
    row: Dict[str, Any],
    *,
    customer_id: str,
    adjustment_type: int,
    amount: Decimal,
    adjust_reason: str,
    client_bill_reason: str,
) -> bool:
    row_amount = _decimal(row.get("amount"))
    return (
        str(row.get("user_id") or "") == customer_id
        and str(row.get("type") or "") == str(adjustment_type)
        and row_amount == amount
        and str(row.get("adjust_reason") or "") == adjust_reason
        and str(row.get("client_bill_reason") or "") == client_bill_reason
    )


def _list_applications(
    session: requests.Session,
    base_url: str,
    variables: Dict[str, Any],
    timeout: int,
    status: int,
) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    payload = _request_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_balance_adjustment_list", "/bill.adjustApplication.list"),
        {"keywords": "", "status": str(status), "page": "1", "pageSize": "100"},
        timeout,
        read_only=True,
        attempts=_as_positive_int(variables.get("balance_adjustment_read_retries"), 3),
    )
    return payload, _rows_from_list(payload)


def _client_info(
    session: requests.Session,
    base_url: str,
    variables: Dict[str, Any],
    timeout: int,
    customer_id: str,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    payload = _request_urlencoded(
        session,
        base_url,
        _api_path(variables, "admin_balance_adjustment_client_info", "/jpanfirm.clientInfo"),
        {"user_id": customer_id},
        timeout,
        read_only=True,
        attempts=_as_positive_int(variables.get("balance_adjustment_read_retries"), 3),
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return payload, data


def _base_summary(
    customer_id: str,
    adjustment_type: int | None,
    amount: Decimal | None,
    **extra: Any,
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "customer_id": customer_id,
        "adjustment_type": adjustment_type,
        "adjustment_type_name": BALANCE_ADJUSTMENT_TYPE_NAMES.get(adjustment_type or 0, ""),
        "amount": _decimal_text(amount),
        "application_created": False,
        "review_passed": False,
        "balance_verified": False,
        "manual_review_required": False,
        "retry_forbidden": False,
    }
    summary.update(extra)
    return summary


def run_balance_adjustment_script(
    env: Env,
    variables: Dict[str, Any] | None = None,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    ensure_report_dirs()
    variables = dict(variables or {})
    ids = _customer_ids(variables)
    customer_id = str(variables.get("customer_id") or (ids[0] if ids else "")).strip()
    adjust_reason = str(variables.get("adjust_reason") or "").strip()
    client_bill_reason = str(variables.get("client_bill_reason") or "").strip()
    adjustment_type_raw = variables.get("adjustment_type")
    amount = _decimal(variables.get("amount"))
    try:
        adjustment_type = int(adjustment_type_raw)
    except (TypeError, ValueError):
        adjustment_type = None

    log: Dict[str, Any] = {
        "script": BALANCE_ADJUSTMENT_SCRIPT_NAME,
        "mode": "balance_adjustment",
        "started_at": datetime.now(),
        "customer_id": customer_id,
        "adjustment_type": adjustment_type,
        "amount": _decimal_text(amount),
        "steps": {},
    }

    def finish_failed(reason: str, **extra: Any) -> Tuple[bool, str, str, Dict[str, Any]]:
        summary = _base_summary(customer_id, adjustment_type, amount, reason=reason, **extra)
        return _finish_named(BALANCE_ADJUSTMENT_SCRIPT_NAME, log, False, summary)

    if not ids or not customer_id:
        return finish_failed("缺少必填参数：customer_id")
    if len(ids) != 1:
        return finish_failed("出入金调整仅支持单客户执行")
    if not re.fullmatch(r"\d+", customer_id):
        return finish_failed("客户ID只能是数字")
    if adjustment_type not in BALANCE_ADJUSTMENT_TYPE_NAMES:
        return finish_failed("出入金类型 adjustment_type 只能为 1（入金）或 2（出金）")
    if amount is None or amount <= 0:
        return finish_failed("出入金金额 amount 必须为正数")
    if not adjust_reason:
        return finish_failed("缺少必填参数：申请原因 adjust_reason")
    if not client_bill_reason:
        return finish_failed("缺少必填参数：出入金名义 client_bill_reason")

    base_url = str(getattr(env, "base_url", "") or "").rstrip("/")
    if not base_url:
        return finish_failed("执行环境缺少 base_url")
    try:
        timeout = max(1, int(getattr(env, "timeout", 30) or 30))
    except (TypeError, ValueError):
        timeout = 30

    application_created = False
    application_id: int | str | None = None
    balance_before: Decimal | None = None
    expected_balance: Decimal | None = None
    try:
        session = _admin_session_from(variables)
        login_payload, token = _admin_login(session, base_url, variables, timeout)
        log["steps"]["admin_login"] = {**_brief(login_payload), "token_extracted": bool(token)}
        if not _api_success(login_payload) or not token:
            return finish_failed("后台登录失败")

        bearer_token = str(token)
        if not bearer_token.lower().startswith("bearer "):
            bearer_token = f"Bearer {bearer_token}"
        session.headers.update(
            {
                "AdminToken": bearer_token,
                "Accept": "application/json, text/plain, */*",
                "Fingerprint": str(variables.get("fingerprint") or "a9b22a33449f254c4f1e486a45822c7f"),
                "Origin": str(variables.get("admin_origin") or "https://jpmanage.rakumart.cn"),
                "PageUrlTrace": str(
                    variables.get("admin_page_url_trace")
                    or "https://jpmanage.rakumart.cn/#/bill_adjust_apply"
                ),
            }
        )

        info_payload, customer = _client_info(session, base_url, variables, timeout, customer_id)
        balance_before = _decimal(customer.get("balance"))
        log["steps"]["client_info_before"] = {
            **_brief(info_payload),
            "customer_id": customer.get("id"),
            "customer_name": customer.get("realname") or customer.get("username"),
            "account_status": customer.get("account_status"),
            "balance": _decimal_text(balance_before),
        }
        if not _api_success(info_payload) or not customer:
            return finish_failed(str(info_payload.get("msg") or "未查询到客户信息"))
        if str(customer.get("id") or "") != customer_id:
            return finish_failed("客户信息返回的客户ID与输入不一致")
        if balance_before is None:
            return finish_failed("客户余额格式无效，无法执行安全校验")
        expected_balance = balance_before + amount if adjustment_type == 1 else balance_before - amount
        if adjustment_type == 2 and amount > balance_before:
            return finish_failed(
                "出金金额超过客户当前余额，已停止创建申请",
                customer_name=customer.get("realname") or customer.get("username") or "",
                balance_before=_decimal_text(balance_before),
                expected_balance=_decimal_text(expected_balance),
            )

        pending_payload, pending_rows = _list_applications(session, base_url, variables, timeout, 0)
        log["steps"]["pending_before"] = {**_brief(pending_payload), "row_count": len(pending_rows)}
        if not _api_success(pending_payload):
            return finish_failed(str(pending_payload.get("msg") or "读取待审核申请失败"))
        existing_matches = [
            row
            for row in pending_rows
            if _row_matches(
                row,
                customer_id=customer_id,
                adjustment_type=adjustment_type,
                amount=amount,
                adjust_reason=adjust_reason,
                client_bill_reason=client_bill_reason,
            )
        ]
        if existing_matches:
            existing_ids = [row.get("id") for row in existing_matches]
            return finish_failed(
                f"存在相同待审核申请，已停止重复创建：{existing_ids}",
                existing_application_ids=existing_ids,
                manual_review_required=True,
                retry_forbidden=True,
                balance_before=_decimal_text(balance_before),
            )
        pending_ids = {str(row.get("id")) for row in pending_rows if row.get("id") not in (None, "")}

        create_fields = {
            "user_id": customer_id,
            "adjust_reason": adjust_reason,
            "type": str(adjustment_type),
            "amount": _decimal_text(amount),
            "client_bill_reason": client_bill_reason,
        }
        try:
            create_payload = _request_urlencoded(
                session,
                base_url,
                _api_path(variables, "admin_balance_adjustment_create", "/bill.adjustApplication.create"),
                create_fields,
                timeout,
                read_only=False,
            )
        except BalanceAdjustmentRequestUncertain as exc:
            log["steps"]["create"] = {"request": create_fields, "uncertain": True, "error": str(exc)}
            return finish_failed(
                str(exc),
                application_created=None,
                manual_review_required=True,
                retry_forbidden=True,
                balance_before=_decimal_text(balance_before),
                expected_balance=_decimal_text(expected_balance),
            )
        log["steps"]["create"] = {**_brief(create_payload), "request": create_fields}
        if not _api_success(create_payload):
            return finish_failed(
                str(create_payload.get("msg") or create_payload.get("data") or "创建出入金申请失败"),
                balance_before=_decimal_text(balance_before),
                expected_balance=_decimal_text(expected_balance),
            )
        application_created = True

        poll_attempts = _as_positive_int(variables.get("balance_adjustment_poll_retries"), 6)
        poll_delay = _as_non_negative_float(variables.get("balance_adjustment_poll_delay"), 1.0)
        candidate_rows: list[Dict[str, Any]] = []
        last_pending_payload: Dict[str, Any] = {}
        for attempt in range(poll_attempts):
            last_pending_payload, current_pending_rows = _list_applications(session, base_url, variables, timeout, 0)
            if _api_success(last_pending_payload):
                candidate_rows = [
                    row
                    for row in current_pending_rows
                    if str(row.get("id")) not in pending_ids
                    and _row_matches(
                        row,
                        customer_id=customer_id,
                        adjustment_type=adjustment_type,
                        amount=amount,
                        adjust_reason=adjust_reason,
                        client_bill_reason=client_bill_reason,
                    )
                ]
                if candidate_rows:
                    break
            if attempt < poll_attempts - 1:
                time.sleep(poll_delay)
        candidate_ids = [row.get("id") for row in candidate_rows]
        log["steps"]["locate_application"] = {
            **_brief(last_pending_payload),
            "candidate_ids": candidate_ids,
        }
        if len(candidate_rows) != 1 or candidate_rows[0].get("id") in (None, ""):
            reason = "未找到刚创建的唯一待审核申请" if not candidate_rows else "刚创建的待审核申请匹配出多条记录"
            return finish_failed(
                reason,
                application_created=True,
                candidate_application_ids=candidate_ids,
                manual_review_required=True,
                retry_forbidden=True,
                balance_before=_decimal_text(balance_before),
                expected_balance=_decimal_text(expected_balance),
            )
        application_id = candidate_rows[0].get("id")

        confirm_fields = {
            "id": application_id,
            "confirm_remark": str(variables.get("confirm_remark") or ""),
        }
        confirm_uncertain = False
        try:
            confirm_payload = _request_urlencoded(
                session,
                base_url,
                _api_path(variables, "admin_balance_adjustment_confirm", "/bill.adjustApplication.confirm"),
                confirm_fields,
                timeout,
                read_only=False,
            )
            log["steps"]["confirm"] = {**_brief(confirm_payload), "request": confirm_fields}
        except BalanceAdjustmentRequestUncertain as exc:
            confirm_uncertain = True
            confirm_payload = {}
            log["steps"]["confirm"] = {"request": confirm_fields, "uncertain": True, "error": str(exc)}

        approved_row: Dict[str, Any] | None = None
        balance_after: Decimal | None = None
        after_customer: Dict[str, Any] = {}
        verify_error = ""
        for attempt in range(poll_attempts):
            try:
                approved_payload, approved_rows = _list_applications(session, base_url, variables, timeout, 1)
                approved_row = next(
                    (row for row in approved_rows if str(row.get("id") or "") == str(application_id)),
                    None,
                )
                after_payload, after_customer = _client_info(session, base_url, variables, timeout, customer_id)
                balance_after = _decimal(after_customer.get("balance"))
                log["steps"]["verify"] = {
                    "approved_list": _brief(approved_payload),
                    "application_status": approved_row.get("status_name") if approved_row else "",
                    "client_info": _brief(after_payload),
                    "balance_after": _decimal_text(balance_after),
                }
                if (
                    _api_success(approved_payload)
                    and approved_row is not None
                    and _api_success(after_payload)
                    and balance_after == expected_balance
                ):
                    break
            except Exception as exc:
                verify_error = str(exc)
                log["steps"]["verify"] = {"error": verify_error}
            if attempt < poll_attempts - 1:
                time.sleep(poll_delay)

        status_verified = approved_row is not None and str(approved_row.get("status") or "") == "1"
        balance_verified = balance_after == expected_balance
        passed = status_verified and balance_verified
        summary = _base_summary(
            customer_id,
            adjustment_type,
            amount,
            customer_name=customer.get("realname") or customer.get("username") or "",
            application_id=application_id,
            application_created=True,
            application_status=approved_row.get("status_name") if approved_row else "",
            balance_before=_decimal_text(balance_before),
            expected_balance=_decimal_text(expected_balance),
            balance_after=_decimal_text(balance_after),
            review_passed=status_verified,
            balance_verified=balance_verified,
            manual_review_required=not passed,
            retry_forbidden=not passed,
        )
        if passed:
            if confirm_uncertain:
                summary["warning"] = "审核接口返回不确定，但已通过申请状态和余额变化确认调整成功"
            return _finish_named(BALANCE_ADJUSTMENT_SCRIPT_NAME, log, True, summary)

        if not _api_success(confirm_payload) and not confirm_uncertain:
            confirm_reason = str(confirm_payload.get("msg") or confirm_payload.get("data") or "审核接口返回失败")
        else:
            confirm_reason = verify_error or "审核后的申请状态或客户余额未通过严格核验"
        summary["reason"] = f"{confirm_reason}；申请可能已生效，禁止重跑，请人工核对"
        return _finish_named(BALANCE_ADJUSTMENT_SCRIPT_NAME, log, False, summary)
    except Exception as exc:
        log["error"] = str(exc)
        return finish_failed(
            str(exc),
            application_id=application_id,
            application_created=application_created,
            balance_before=_decimal_text(balance_before),
            expected_balance=_decimal_text(expected_balance),
            manual_review_required=application_created,
            retry_forbidden=application_created,
        )


__all__ = [
    "BALANCE_ADJUSTMENT_SCRIPT_NAME",
    "BALANCE_ADJUSTMENT_TYPE_NAMES",
    "BalanceAdjustmentRequestUncertain",
    "run_balance_adjustment_script",
]
