from __future__ import annotations

import json
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..data_script_shared import _finish_named
from ..orders import inspect_order_options
from ..problem_goods import inspect_problem_goods
from .reconciliation import MoneyEvidence, new_records, reconcile_amount, to_jpy
from .scenarios import (
    SCENARIO_CATALOG,
    ScenarioConfigurationError,
    ScenarioSpec,
    build_problem_goods_variables,
)


PAYMENT_AMOUNT_REGRESSION_SCRIPT_NAME = "支付金额自动回归"
AMOUNT_KEYS = (
    "change_amount",
    "pay_amount",
    "amount",
    "money",
    "balance_change",
    "payment_amount",
)


class ScenarioBlocked(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "",
        evidence: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = str(reason_code or "")
        self.evidence = dict(evidence or {})


def _decimal(value: Any, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ScenarioBlocked(f"{label}不是有效金额") from exc
    if not number.is_finite():
        raise ScenarioBlocked(f"{label}不是有限金额")
    return number


def _bool_value(value: Any, default: bool = True) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {"0", "false", "no", "off", "否"}


def _amount_from_record(row: Mapping[str, Any]) -> Decimal:
    for key in AMOUNT_KEYS:
        value = row.get(key)
        if value not in (None, ""):
            return _decimal(value, f"流水字段 {key}")
    raise ScenarioBlocked("实际流水缺少金额字段")


def _record_id(row: Mapping[str, Any]) -> str:
    for key in ("id", "serial_number", "bill_sn", "record_id", "uniqid"):
        if row.get(key) not in (None, ""):
            return str(row.get(key))
    return ""


def money_evidence_from_record(
    row: Mapping[str, Any],
    *,
    source: str,
    reference: str,
    direction: str | None = None,
) -> MoneyEvidence:
    amount = _amount_from_record(row)
    actual_direction = direction or ("debit" if amount < 0 else "credit" if amount > 0 else "none")
    currency = str(row.get("currency") or row.get("currency_code") or "JPY").upper()
    rate_value = row.get("exchange_rate") or row.get("rate")
    return MoneyEvidence(
        source=source,
        amount=amount,
        currency=currency,
        direction=actual_direction,
        exchange_rate=_decimal(rate_value, "实际流水汇率") if rate_value not in (None, "") else None,
        reference=reference,
        record_id=_record_id(row),
        raw=dict(row),
    )


def _report_log(report_path: str) -> dict[str, Any]:
    result_path = Path(str(report_path or ""))
    if not result_path.is_file():
        return {}
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    attachments = result.get("attachments") if isinstance(result, dict) else []
    for attachment in attachments if isinstance(attachments, list) else []:
        if not isinstance(attachment, dict) or attachment.get("name") != "log":
            continue
        log_path = result_path.parent / str(attachment.get("source") or "")
        try:
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError):
            return {}
    return {}


def collect_selected_bills(payload: Any) -> list[dict[str, Any]]:
    bills: list[dict[str, Any]] = []
    seen_bills: set[tuple[str, str]] = set()
    visited_reports: set[str] = set()

    def add_bill(row: Mapping[str, Any]) -> None:
        key = ("id", _record_id(row)) if _record_id(row) else ("payload", repr(sorted(row.items())))
        if key not in seen_bills:
            seen_bills.add(key)
            bills.append(dict(row))

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            selected = value.get("selected_bill")
            if isinstance(selected, dict) and selected:
                add_bill(selected)
            for key, item in value.items():
                if key not in {"selected_bill", "report_path"}:
                    walk(item)
            report_path = str(value.get("report_path") or "").strip()
            if report_path and report_path not in visited_reports:
                visited_reports.add(report_path)
                walk(_report_log(report_path))
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return bills


def _payload_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = [payload.get("data")]
    while candidates:
        value = candidates.pop(0)
        if isinstance(value, list):
            rows = [dict(item) for item in value if isinstance(item, dict)]
            if rows:
                return rows
        elif isinstance(value, dict):
            for key in ("data", "list", "rows", "result", "records"):
                if value.get(key) is not None:
                    candidates.append(value.get(key))
    return []


def _row_matches(row: Mapping[str, Any], references: Iterable[str]) -> bool:
    needles = [str(value).strip() for value in references if str(value).strip()]
    if not needles:
        return False
    exact_keys = (
        "order_sn",
        "porder_sn",
        "p_order_sn",
        "problem_goods_id",
        "serial_number",
    )
    text_keys = (
        "remark",
        "pay_remark",
        "description",
    )
    return any(needle == str(row.get(key) or "").strip() for needle in needles for key in exact_keys) or any(
        needle in str(row.get(key) or "") for needle in needles for key in text_keys
    )


def _matching_rows(rows: Iterable[Mapping[str, Any]], references: Iterable[str]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if _row_matches(row, references)]


def _expected_evidence(amount: Any, source: str, reference: str, direction: str) -> MoneyEvidence:
    return MoneyEvidence(source, _decimal(amount, source), "JPY", direction, reference=reference)


def _aggregate_evidence(
    rows: list[Mapping[str, Any]],
    *,
    source: str,
    reference: str,
    direction: str | None = None,
) -> MoneyEvidence:
    if not rows:
        raise ScenarioBlocked(f"未找到 {reference} 的实际流水")
    if len(rows) != 1:
        raise ScenarioBlocked(f"{reference} 匹配到 {len(rows)} 条实际流水，无法唯一取证")
    return money_evidence_from_record(rows[0], source=source, reference=reference, direction=direction)


def _sum_evidence_jpy(evidences: Iterable[MoneyEvidence]) -> Decimal:
    return sum(
        (abs(to_jpy(item.amount, item.currency, item.exchange_rate)) for item in evidences),
        Decimal("0"),
    )


def _first_failure(checks: list[Mapping[str, Any]]) -> str:
    for check in checks:
        if check.get("passed") is False:
            return str(check.get("reason") or check.get("reason_code") or "金额校验失败")
    return ""


class LivePaymentRegressionExecutor:
    def __init__(self, env: Any, variables: Mapping[str, Any] | None = None):
        self.env = env
        self.variables = {
            key: value
            for key, value in dict(variables or {}).items()
            if key != "_scenario_executor"
        }

    @staticmethod
    def _scripts():
        import app.data_scripts as data_scripts

        return data_scripts

    def _variables(self, batch_id: str, scenario: ScenarioSpec, **overrides: Any) -> dict[str, Any]:
        values = dict(self.variables)
        for key in ("pay_amount", "order_tail_pay_amount", "tail_pay_amount", "porder_pay_amount"):
            values.pop(key, None)
        if values.get("confirm_freight") in (None, ""):
            values["confirm_freight"] = "5"
        if values.get("offer_freight") in (None, ""):
            values["offer_freight"] = "5"
        marker = f"[{batch_id}][{scenario.key}]"
        values.update(
            {
                "client_remark": marker,
                "pay_remark": marker,
                "order_tail_pay_remark": marker,
                "purchase_remark": marker,
                "problem_description": marker,
                "payment_regression_batch_id": batch_id,
            }
        )
        values.update(overrides)
        return values

    @staticmethod
    def _run_script(runner: Any, env: Any, variables: dict[str, Any], label: str) -> tuple[dict[str, Any], dict[str, Any], str]:
        passed, log_text, report_path, summary = runner(env, variables)
        try:
            log = json.loads(log_text) if log_text else {}
        except ValueError:
            log = {}
        if not passed:
            reason = str((summary or {}).get("reason") or (summary or {}).get("error") or f"{label}失败")
            structured = dict(summary or {})
            recognized_codes = {
                "unknown_write_state",
                "confirmed_written",
                "confirmed_not_written",
                "reconciliation_failed",
                "target_action_timeout",
            }
            if str(structured.get("reason_code") or "") not in recognized_codes:
                for step in reversed(log.get("steps") or []):
                    candidate = step.get("summary") if isinstance(step, Mapping) else None
                    if isinstance(candidate, Mapping) and str(candidate.get("reason_code") or "") in recognized_codes:
                        structured = dict(candidate)
                        break
            reason_code = str(structured.get("reason_code") or "")
            if reason_code in recognized_codes:
                evidence_keys = {
                    "order_sn",
                    "write_state",
                    "attempted_actions",
                    "before_evidence",
                    "after_evidence",
                    "business_diffs",
                    "request_attempt_count",
                    "reconciliation",
                }
                evidence = {key: structured.get(key) for key in evidence_keys if key in structured}
                raise ScenarioBlocked(reason, reason_code=reason_code, evidence=evidence)
            raise ScenarioBlocked(reason)
        result_summary = dict(summary or {})
        evidence_keys = {
            "write_state",
            "write_reason_code",
            "attempted_actions",
            "before_evidence",
            "after_evidence",
            "business_diffs",
            "request_attempt_count",
            "reconciliation",
        }
        for step in reversed(log.get("steps") or []):
            candidate = step.get("summary") if isinstance(step, Mapping) else None
            if isinstance(candidate, Mapping) and candidate.get("write_state"):
                for key in evidence_keys:
                    if key in candidate:
                        result_summary[key] = candidate.get(key)
                break
        return result_summary, log if isinstance(log, dict) else {}, str(report_path or "")

    def _client(self, variables: dict[str, Any]) -> Any:
        scripts = self._scripts()
        client, _base_url, _timeout, _token = scripts._login_client_for_payment(self.env, variables, {})
        return client

    def _balance_rows(self, variables: dict[str, Any]) -> list[dict[str, Any]]:
        scripts = self._scripts()
        client = self._client(variables)
        fields = {
            "start_time": "",
            "end_time": "",
            "keywords": "",
            "bill_type": "",
            "bill_method": "",
            "order_by": "desc",
            "page": 1,
            "pageSize": int(variables.get("payment_regression_ledger_page_size") or 100),
        }
        path = scripts._api_path(variables, "client_balance_change", "/client/user.balanceChange")
        payload = client.post_form(path, fields)
        if not scripts._api_success(payload):
            raise ScenarioBlocked(str(payload.get("msg") or "客户账单查询失败"))
        return _payload_rows(payload)

    def _wait_new_balance_rows(
        self,
        before: list[Mapping[str, Any]],
        variables: dict[str, Any],
        references: list[str],
        *,
        allow_empty: bool = False,
    ) -> list[dict[str, Any]]:
        retries = int(variables.get("payment_regression_evidence_retries") or 6)
        delay = float(variables.get("payment_regression_evidence_delay") or 2)
        matches: list[dict[str, Any]] = []
        for attempt in range(max(1, retries)):
            matches = _matching_rows(new_records(before, self._balance_rows(variables)), references)
            if matches:
                return matches
            if attempt < retries - 1 and delay > 0:
                time.sleep(delay)
        if allow_empty:
            return []
        raise ScenarioBlocked(f"结算等待结束后未找到实际流水：{'、'.join(references)}")

    def _quote_order(
        self,
        scenario: ScenarioSpec,
        batch_id: str,
        *,
        part_pay: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        scripts = self._scripts()
        variables = self._variables(
            batch_id,
            scenario,
            stop_after_node="order_offered",
            order_item_num=max(2, int(self.variables.get("payment_regression_item_num") or 2)),
            offer_price=str(self.variables.get("payment_regression_offer_price") or "10"),
            _full_flow_part_pay_script=part_pay,
            order_part_pay=part_pay,
            order_part_pay_percent=int(self.variables.get("payment_regression_part_pay_percent") or 50),
            order_part_pay_tail_node="before_shelf",
            order_payment_mode=scenario.payment_mode or "balance",
            order_tail_payment_mode=scenario.payment_mode or "balance",
            finance_confirm=True,
        )
        summary, _log, _report = self._run_script(scripts.run_full_flow_script, self.env, variables, "订单报价")
        order_sn = str(summary.get("order_sn") or "")
        if not order_sn:
            raise ScenarioBlocked("订单报价未返回订单号")
        evidence_keys = {
            "write_state",
            "write_reason_code",
            "attempted_actions",
            "before_evidence",
            "after_evidence",
            "business_diffs",
            "request_attempt_count",
            "reconciliation",
        }
        write_evidence = {key: summary.get(key) for key in evidence_keys if key in summary}
        self._last_order_write_evidence = write_evidence
        return order_sn, variables

    def _order_expected_amount(self, variables: dict[str, Any], order_sn: str) -> str:
        scripts = self._scripts()
        client = self._client(variables)
        lookup = dict(variables, order_sn=order_sn)
        lookup.pop("pay_amount", None)
        order, selected_sn, amount = scripts._load_payment_order(client, lookup, {})
        if not order or selected_sn != order_sn or not scripts._positive_decimal(amount):
            raise ScenarioBlocked("未获取到订单报价金额")
        return str(amount)

    def _porder_expected_amount(self, variables: dict[str, Any], porder_sn: str) -> MoneyEvidence:
        scripts = self._scripts()
        client = self._client(variables)
        path = scripts._api_path(
            variables,
            "client_porder_detail",
            "/client/porder.porderDetail",
        )
        payload = client.post_form(path, {"porder_sn": porder_sn})
        if not scripts._api_success(payload):
            raise ScenarioBlocked(str(payload.get("msg") or "配送单应付金额查询失败"))
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        amount_data = data.get("porder_amount") if isinstance(data.get("porder_amount"), dict) else {}
        amount = _decimal(amount_data.get("pay_amount"), "配送单人民币应付金额")
        exchange_rate = _decimal(amount_data.get("exchange_rate"), "配送单汇率")
        expected_jpy = _decimal(amount_data.get("pay_amount_jpy"), "配送单日元应付金额")
        if amount <= 0 or exchange_rate <= 0 or expected_jpy <= 0:
            raise ScenarioBlocked("未获取到有效的配送单应付金额或汇率")
        if to_jpy(amount, "CNY", exchange_rate) != expected_jpy:
            raise ScenarioBlocked("配送单人民币金额、汇率与日元应付金额不一致")
        return MoneyEvidence(
            source="porder_pay_detail",
            amount=amount,
            currency="CNY",
            direction="debit",
            exchange_rate=exchange_rate,
            reference=porder_sn,
            raw=dict(amount_data),
        )

    @staticmethod
    def _bank_actual(log: Mapping[str, Any], report_path: str, reference: str) -> MoneyEvidence:
        bills = collect_selected_bills({"log": dict(log), "report_path": report_path})
        matches = _matching_rows(bills, [reference])
        if len(matches) != 1:
            raise ScenarioBlocked(f"银行支付实际流水无法唯一匹配：{reference}")
        return money_evidence_from_record(matches[0], source="finance_confirmed_bill", reference=reference, direction="debit")

    @staticmethod
    def _porder_bank_actual(
        log: Mapping[str, Any],
        report_path: str,
        reference: str,
        expected: MoneyEvidence,
    ) -> MoneyEvidence:
        actual = LivePaymentRegressionExecutor._bank_actual(log, report_path, reference)
        raw = dict(actual.raw)
        explicit_currency = raw.get("currency") or raw.get("currency_code")
        if explicit_currency not in (None, ""):
            return actual
        return MoneyEvidence(
            source=actual.source,
            amount=actual.amount,
            currency="CNY",
            direction=actual.direction,
            exchange_rate=expected.exchange_rate,
            reference=actual.reference,
            record_id=actual.record_id,
            raw=raw,
        )

    def _execute_order(self, scenario: ScenarioSpec, batch_id: str) -> dict[str, Any]:
        scripts = self._scripts()
        order_sn, variables = self._quote_order(scenario, batch_id)
        write_evidence = dict(getattr(self, "_last_order_write_evidence", {}) or {})
        expected_amount = self._order_expected_amount(variables, order_sn)
        before = self._balance_rows(variables) if scenario.payment_mode == "balance" else []
        payment_vars = dict(variables, order_sn=order_sn, finance_confirm=True)
        runner = scripts.run_balance_payment_script if scenario.payment_mode == "balance" else scripts.run_bank_payment_script
        payment_summary, payment_log, payment_report = self._run_script(runner, self.env, payment_vars, scenario.name)
        if scenario.payment_mode == "balance":
            rows = self._wait_new_balance_rows(before, variables, [order_sn])
            actual = _aggregate_evidence(rows, source="customer_balance", reference=order_sn, direction="debit")
        else:
            actual = self._bank_actual(payment_log, payment_report, str(payment_summary.get("serial_number") or order_sn))
        expected = _expected_evidence(expected_amount, "order_quote", order_sn, "debit")
        check = reconcile_amount(scenario.key, expected, actual)
        return {
            "status": "passed" if check["passed"] else "failed",
            "order_sn": order_sn,
            "payment_type": scenario.payment_mode,
            "checks": [check],
            **write_evidence,
        }

    def _order_pay_data(self, variables: dict[str, Any], order_sn: str) -> dict[str, Any]:
        scripts = self._scripts()
        client = self._client(variables)
        fields = scripts._order_tail_pay_data_fields(order_sn, variables, [])
        payload = client.post_form(scripts._api_path(variables, "client_order_pay_data", "/client/order.payData"), fields)
        if not scripts._api_success(payload):
            raise ScenarioBlocked(str(payload.get("msg") or "分批付款金额查询失败"))
        return payload

    @staticmethod
    def _part_payment_expected_amounts(first_due_amount: str, pay_data: Any) -> tuple[str, str]:
        first = str(first_due_amount or "").strip()
        total = LivePaymentRegressionExecutor._recursive_amount(
            pay_data,
            ("pay_amount_jpy", "total_amount", "pay_amount"),
        )
        if not first:
            raise ScenarioBlocked("分批付款未返回首款预期金额")
        if not total:
            raise ScenarioBlocked("分批付款未返回整单报价金额")
        return first, total

    @staticmethod
    def _recursive_amount(payload: Any, keys: tuple[str, ...]) -> str:
        if isinstance(payload, dict):
            for key in keys:
                if payload.get(key) not in (None, ""):
                    return str(payload.get(key))
            for value in payload.values():
                found = LivePaymentRegressionExecutor._recursive_amount(value, keys)
                if found:
                    return found
        elif isinstance(payload, list):
            for value in payload:
                found = LivePaymentRegressionExecutor._recursive_amount(value, keys)
                if found:
                    return found
        return ""

    @staticmethod
    def _tail_summary(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            value = payload.get("order_tail_payment")
            if isinstance(value, dict):
                return value
            for item in payload.values():
                found = LivePaymentRegressionExecutor._tail_summary(item)
                if found:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                found = LivePaymentRegressionExecutor._tail_summary(item)
                if found:
                    return found
        return {}

    @staticmethod
    def _tail_expected_amount(payload: Any) -> str:
        tail = LivePaymentRegressionExecutor._tail_summary(payload)
        return str(
            tail.get("pay_amount")
            or tail.get("data.pay_amount")
            or LivePaymentRegressionExecutor._recursive_amount(
                tail.get("pay_data") or {},
                ("pay_amount_jpy", "total_amount", "pay_amount"),
            )
            or ""
        )

    @staticmethod
    def _split_stage_actuals(rows: list[Mapping[str, Any]], first_amount: str, reference: str, source: str, direction: str | None = None) -> tuple[MoneyEvidence, MoneyEvidence]:
        if len(rows) != 2:
            raise ScenarioBlocked(f"分批付款需要唯一的首款、尾款两条实际流水，当前匹配到 {len(rows)} 条")
        evidences = [money_evidence_from_record(row, source=source, reference=reference, direction=direction) for row in rows]
        target = abs(_decimal(first_amount, "首款金额"))
        evidences.sort(
            key=lambda item: abs(abs(to_jpy(item.amount, item.currency, item.exchange_rate)) - target)
        )
        return evidences[0], evidences[1]

    def _execute_part_pay(self, scenario: ScenarioSpec, batch_id: str) -> dict[str, Any]:
        scripts = self._scripts()
        order_sn, variables = self._quote_order(scenario, batch_id, part_pay=True)
        write_evidence = dict(getattr(self, "_last_order_write_evidence", {}) or {})
        first_due_amount = self._order_expected_amount(variables, order_sn)
        first_payload = self._order_pay_data(variables, order_sn)
        first_expected_amount, quote_total = self._part_payment_expected_amounts(
            first_due_amount,
            first_payload,
        )
        before = self._balance_rows(variables) if scenario.payment_mode == "balance" else []
        resume_vars = dict(variables, order_sn=order_sn, stop_after_node="shelf_stored")
        summary, log, report_path = self._run_script(scripts.run_resume_order_flow_script, self.env, resume_vars, scenario.name)
        tail_expected_amount = self._tail_expected_amount(
            {"summary": summary, "log": log, "report_path": report_path}
        )
        if not tail_expected_amount:
            raise ScenarioBlocked("分批付款未返回尾款预期金额")
        if scenario.payment_mode == "balance":
            rows = self._wait_new_balance_rows(before, variables, [order_sn])
            first_actual, tail_actual = self._split_stage_actuals(
                rows,
                first_expected_amount,
                order_sn,
                "customer_balance",
                "debit",
            )
        else:
            bills = collect_selected_bills({"log": log, "report_path": report_path})
            rows = _matching_rows(bills, [order_sn])
            first_actual, tail_actual = self._split_stage_actuals(rows, first_expected_amount, order_sn, "finance_confirmed_bill", "debit")
        first_expected = _expected_evidence(first_expected_amount, "order_part_pay_preview", order_sn, "debit")
        tail_expected = _expected_evidence(tail_expected_amount, "order_tail_pay_preview", order_sn, "debit")
        first_check = reconcile_amount(f"{scenario.key}_first", first_expected, first_actual)
        tail_check = reconcile_amount(f"{scenario.key}_tail", tail_expected, tail_actual)
        total_actual = MoneyEvidence(
            "payment_stage_sum",
            _sum_evidence_jpy((first_actual, tail_actual)),
            "JPY",
            "debit",
            reference=order_sn,
            record_id=",".join(filter(None, [first_actual.record_id, tail_actual.record_id])),
        )
        partial_tail = bool(int(variables.get("order_part_pay_tail_partial_enabled") or 0))
        total_expected = (
            MoneyEvidence(
                "payment_stage_sum",
                _sum_evidence_jpy((first_expected, tail_expected)),
                "JPY",
                "debit",
                reference=order_sn,
            )
            if partial_tail
            else _expected_evidence(quote_total, "order_quote", order_sn, "debit")
        )
        total_check = reconcile_amount(
            f"{scenario.key}_total",
            total_expected,
            total_actual,
        )
        checks = [first_check, tail_check, total_check]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "failed",
            "order_sn": order_sn,
            "payment_type": scenario.payment_mode,
            "checks": checks,
            **write_evidence,
        }

    def _execute_porder(self, scenario: ScenarioSpec, batch_id: str) -> dict[str, Any]:
        scripts = self._scripts()
        variables = self._variables(batch_id, scenario, stop_after_node="porder_offered", order_item_num=2)
        summary, _log, _report = self._run_script(scripts.run_full_flow_script, self.env, variables, "配送单报价")
        porder_sn = str(summary.get("porder_sn") or "")
        if not porder_sn:
            raise ScenarioBlocked("配送流程未返回配送单号")
        expected_value = self._porder_expected_amount(variables, porder_sn)
        expected = (
            expected_value
            if isinstance(expected_value, MoneyEvidence)
            else _expected_evidence(str(expected_value), "porder_pay_detail", porder_sn, "debit")
        )
        before = self._balance_rows(variables) if scenario.payment_mode == "balance" else []
        pay_vars = dict(variables, porder_sn=porder_sn, run_backend_porder_flow=False, finance_confirm=True)
        if scenario.payment_mode == "bank":
            pay_vars = self._bounded_porder_payment_variables(pay_vars)
        runner = scripts.run_porder_balance_payment_script if scenario.payment_mode == "balance" else scripts.run_porder_bank_payment_script
        pay_summary, pay_log, pay_report = self._run_script(runner, self.env, pay_vars, scenario.name)
        if scenario.payment_mode == "balance":
            rows = self._wait_new_balance_rows(before, variables, [porder_sn])
            actual = _aggregate_evidence(rows, source="customer_balance", reference=porder_sn, direction="debit")
        else:
            actual = self._porder_bank_actual(
                pay_log,
                pay_report,
                str(pay_summary.get("serial_number") or porder_sn),
                expected,
            )
        check = reconcile_amount(
            scenario.key,
            expected,
            actual,
        )
        return {"status": "passed" if check["passed"] else "failed", "porder_sn": porder_sn, "payment_type": scenario.payment_mode, "checks": [check]}

    @staticmethod
    def _bounded_porder_payment_variables(variables: dict[str, Any]) -> dict[str, Any]:
        values = dict(variables)
        values.setdefault("timeout", 8)
        values.setdefault("finance_confirm_retries", 2)
        values.setdefault("finance_confirm_initial_delay", 1)
        values.setdefault("finance_confirm_delay", 1)
        return values

    def _ensure_problem_option(self, variables: dict[str, Any]) -> None:
        preview = inspect_order_options(self.env, variables)
        for option in preview.get("options") if isinstance(preview.get("options"), list) else []:
            if not isinstance(option, dict):
                continue
            if int(option.get("price_type") or 0) == 0 and _decimal(option.get("price") or 0, "OPTION 金额") > 0:
                key = str(option.get("key") or option.get("id") or option.get("name") or "").strip()
                if key:
                    variables["order_option_counts"] = {key: 2}
                    return
        raise ScenarioBlocked("未找到可用于问题产品金额回归的固定金额 OPTION")

    @staticmethod
    def _preview_evidence(bills: list[Mapping[str, Any]], scenario: ScenarioSpec, reference: str) -> MoneyEvidence:
        net_amount = sum((_decimal(row.get("amount") or 0, "问题产品预览金额") for row in bills), Decimal("0"))
        preview_direction = "credit" if net_amount > 0 else "debit" if net_amount < 0 else "none"
        if preview_direction != scenario.expected_direction:
            raise ValueError(
                f"问题产品预览方向 {preview_direction} 与场景预期方向 {scenario.expected_direction} 不一致"
            )
        return MoneyEvidence(
            "problem_goods_preview",
            abs(net_amount),
            "JPY",
            scenario.expected_direction,
            reference=reference,
            raw={"bills": [dict(row) for row in bills]},
        )

    def _execute_problem_goods(self, scenario: ScenarioSpec, batch_id: str) -> dict[str, Any]:
        scripts = self._scripts()
        variables = self._variables(
            batch_id,
            scenario,
            stop_after_node="shelf_stored",
            order_item_num=3,
            purchase_freight=str(self.variables.get("payment_regression_problem_freight") or "3"),
        )
        if scenario.adjustment in {"option_up", "mixed_down"}:
            self._ensure_problem_option(variables)
        flow_summary, _flow_log, _flow_report = self._run_script(scripts.run_full_flow_script, self.env, variables, "问题产品前置订单")
        order_sn = str(flow_summary.get("order_sn") or "")
        if not order_sn:
            raise ScenarioBlocked("问题产品前置流程未返回订单号")
        inspection = inspect_problem_goods(self.env, dict(variables, order_sn=order_sn))
        candidates = inspection.get("order_candidates") if isinstance(inspection.get("order_candidates"), list) else []
        candidate = next((row for row in candidates if isinstance(row, dict) and row.get("can_submit") is not False), None)
        if not candidate:
            raise ScenarioBlocked("未找到可提交的问题产品采购明细")
        problem_vars = self._variables(batch_id, scenario, order_sn=order_sn)
        try:
            problem_vars.update(build_problem_goods_variables(scenario, candidate))
        except ScenarioConfigurationError as exc:
            raise ScenarioBlocked(str(exc)) from exc
        before = self._balance_rows(problem_vars)
        problem_summary, _problem_log, _problem_report = self._run_script(scripts.run_problem_goods_script, self.env, problem_vars, scenario.name)
        problem_id = str(problem_summary.get("problem_goods_id") or "")
        preview_bills = problem_summary.get("preview_bills") if isinstance(problem_summary.get("preview_bills"), list) else []
        expected = self._preview_evidence(preview_bills, scenario, problem_id or order_sn)
        references = [value for value in [problem_id, order_sn] if value]
        rows = self._wait_new_balance_rows(before, problem_vars, references, allow_empty=scenario.expected_direction == "none")
        if scenario.expected_direction == "none":
            if rows:
                evidences = [
                    money_evidence_from_record(
                        row,
                        source="customer_balance",
                        reference=problem_id or order_sn,
                    )
                    for row in rows
                ]
                directions = {item.direction for item in evidences}
                actual = MoneyEvidence(
                    "customer_balance",
                    sum((abs(item.amount) for item in evidences), Decimal("0")),
                    "JPY",
                    directions.pop() if len(directions) == 1 else "none",
                    reference=problem_id or order_sn,
                    record_id=",".join(item.record_id for item in evidences if item.record_id),
                    raw={"records": [dict(row) for row in rows]},
                )
            else:
                actual = MoneyEvidence("customer_balance", Decimal("0"), "JPY", "none", reference=problem_id or order_sn)
        else:
            actual = _aggregate_evidence(rows, source="customer_balance", reference=problem_id or order_sn)
        check = reconcile_amount(scenario.key, expected, actual)
        if scenario.expected_direction == "none" and rows:
            check.update(
                passed=False,
                reason_code="unexpected_ledger",
                reason=f"零金额场景出现 {len(rows)} 条匹配的客户出入金流水",
            )
        return {
            "status": "passed" if check["passed"] else "failed",
            "order_sn": order_sn,
            "problem_goods_id": problem_id,
            "checks": [check],
        }

    def execute(self, scenario: ScenarioSpec, batch_id: str) -> dict[str, Any]:
        if scenario.category == "order":
            return self._execute_order(scenario, batch_id)
        if scenario.category == "order_part":
            return self._execute_part_pay(scenario, batch_id)
        if scenario.category == "porder":
            return self._execute_porder(scenario, batch_id)
        if scenario.category == "problem_goods":
            return self._execute_problem_goods(scenario, batch_id)
        raise ScenarioBlocked(f"不支持的金额回归场景：{scenario.category}")


def _scenario_result(scenario: ScenarioSpec, payload: Mapping[str, Any]) -> dict[str, Any]:
    result = {"key": scenario.key, "name": scenario.name, **dict(payload)}
    checks = result.get("checks") if isinstance(result.get("checks"), list) else []
    failure_reason = _first_failure(checks)
    if failure_reason:
        result["status"] = "failed"
        result["failure_reason"] = failure_reason
    else:
        result.setdefault("status", "passed")
    return result


def run_payment_amount_regression_script(
    env: Any,
    variables: Mapping[str, Any] | None = None,
) -> tuple[bool, str, str, dict[str, Any]]:
    values = dict(variables or {})
    batch_id = str(values.get("payment_regression_batch_id") or f"PAYREG-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    executor = values.get("_scenario_executor") or LivePaymentRegressionExecutor(env, values)
    log: dict[str, Any] = {
        "script": PAYMENT_AMOUNT_REGRESSION_SCRIPT_NAME,
        "mode": "payment_amount_regression",
        "started_at": datetime.now(),
        "batch_id": batch_id,
        "scenarios": [],
    }
    results: list[dict[str, Any]] = []
    selected_scenarios = tuple(
        scenario
        for scenario in SCENARIO_CATALOG
        if _bool_value(values.get(f"payment_regression_scenario_{scenario.key}"), True)
    )
    for scenario in selected_scenarios:
        try:
            payload = executor.execute(scenario, batch_id)
            result = _scenario_result(scenario, payload if isinstance(payload, dict) else {})
        except ScenarioBlocked as exc:
            result = {"key": scenario.key, "name": scenario.name, "status": "blocked", "failure_reason": str(exc), "checks": []}
        except Exception as exc:
            result = {"key": scenario.key, "name": scenario.name, "status": "failed", "failure_reason": str(exc), "checks": []}
        results.append(result)
        log["scenarios"].append(result)
    passed_count = sum(item["status"] == "passed" for item in results)
    failed_count = sum(item["status"] == "failed" for item in results)
    blocked_count = sum(item["status"] == "blocked" for item in results)
    summary = {
        "batch_id": batch_id,
        "scenario_count": len(results),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "blocked_count": blocked_count,
        "coupon_supported": False,
        "voucher_supported": False,
        "discount_amount": "0",
        "voucher_amount": "0",
        "scenarios": results,
    }
    if not results:
        summary["failure_reason"] = "至少选择一个支付金额回归场景"
    passed = bool(results) and failed_count == 0 and blocked_count == 0
    return _finish_named(PAYMENT_AMOUNT_REGRESSION_SCRIPT_NAME, log, passed, summary)
