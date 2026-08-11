from __future__ import annotations

from typing import Any, Callable, Mapping

from .runner import CaseRunResult


class GuardRunner:
    def __init__(self, gateway: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]) -> None:
        self.gateway = gateway

    def execute(self, case: Mapping[str, Any], context: Mapping[str, Any]) -> CaseRunResult:
        payload = dict(self.gateway(case, context) or {})
        structured_status = str(payload.get("status") or "")
        reason_code = str(payload.get("reason_code") or "")
        if structured_status in {"passed", "failed", "blocked", "waiting"} and reason_code:
            run_status = "waiting_account" if structured_status == "waiting" else structured_status
            return CaseRunResult(
                status=run_status,
                order_sn=str(payload.get("order_sn") or ""),
                problem_goods_id=str(payload.get("problem_goods_id") or ""),
                result=payload,
                reason_code=reason_code,
                error_message=str(payload.get("failure_reason") or "") if run_status != "passed" else "",
                resume_stage=str(payload.get("expected_stage") or "") if run_status == "waiting_account" else "",
            )
        expectation = dict(case.get("expectation") or {})
        codes = {str(value) for value in expectation.get("error_codes") or []}
        keywords = [str(value) for value in expectation.get("error_keywords") or []]
        actual_code = str(payload.get("error_code") or "")
        message = str(payload.get("error_message") or payload.get("failure_reason") or "")
        matched = (bool(actual_code) and actual_code in codes) or any(keyword and keyword in message for keyword in keywords)
        if matched:
            return CaseRunResult(status="passed", result=payload, reason_code="guard_triggered")
        return CaseRunResult(
            status="failed",
            result=payload,
            reason_code="guard_not_triggered",
            error_message="未触发预期拦截，或实际错误与用例声明不匹配",
        )


__all__ = ["GuardRunner"]
