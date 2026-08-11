from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class CaseRunResult:
    status: str
    order_sn: str = ""
    sorting: str = ""
    porder_sn: str = ""
    problem_goods_id: str = ""
    expected: dict[str, Any] = field(default_factory=dict)
    preview: dict[str, Any] = field(default_factory=dict)
    actual: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    reason_code: str = ""
    error_code: str = ""
    error_message: str = ""
    resume_stage: str = ""

    def __post_init__(self) -> None:
        if self.reason_code and not self.error_code:
            self.error_code = self.reason_code
        elif self.error_code and not self.reason_code:
            self.reason_code = self.error_code


class JapanRegressionRunner:
    def __init__(self, *, payment_runner: Any, problem_runner: Any, guard_runner: Any) -> None:
        self.payment_runner = payment_runner
        self.problem_runner = problem_runner
        self.guard_runner = guard_runner

    def execute(self, case: Mapping[str, Any], context: Mapping[str, Any]) -> CaseRunResult:
        runner_kind = str(case.get("runner_kind") or "")
        if runner_kind in {"order_payment", "order_part_payment", "porder_payment"}:
            runner = self.payment_runner
        elif runner_kind in {"problem_goods", "problem_flow"}:
            runner = self.problem_runner
        elif runner_kind == "problem_guard":
            runner = self.guard_runner
        else:
            return CaseRunResult(
                status="failed",
                error_code="unsupported_runner",
                error_message=f"不支持的执行类型：{runner_kind}",
            )
        try:
            return runner.execute(case, context)
        except Exception as exc:
            if exc.__class__.__name__ == "AccountLoginRequired":
                return CaseRunResult(
                    status="waiting_account",
                    resume_stage="minister_account_login",
                    error_code="minister_account_required",
                    error_message=str(exc),
                )
            if not isinstance(exc, (RuntimeError, ValueError, KeyError)):
                raise
            return CaseRunResult(
                status="blocked",
                error_code="precondition_error",
                error_message=str(exc),
            )


__all__ = ["CaseRunResult", "JapanRegressionRunner"]
