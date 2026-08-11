from __future__ import annotations

import re
import time
from decimal import Decimal
from typing import Any, Callable, Mapping, Sequence

from .execution_contract import ExecutionResultPayload, classify_business_diffs
from .guard_scenarios import GuardScenarioSpec, guard_scenario


class GuardPreconditionMissing(RuntimeError):
    pass


class GuardActionUnavailable(RuntimeError):
    pass


class GuardWriteTimeout(TimeoutError):
    def __init__(self, message: str, *, probe: Callable[[], Mapping[str, Any]]) -> None:
        super().__init__(message)
        self.probe = probe


def _structured_error_code(response: Mapping[str, Any]) -> str:
    structured = response.get("error") if isinstance(response.get("error"), Mapping) else {}
    return str(
        response.get("structured_error")
        or structured.get("code")
        or structured.get("type")
        or ""
    )


def _response_message(response: Mapping[str, Any]) -> str:
    direct = response.get("error_message") or response.get("message") or response.get("failure_reason")
    if direct not in (None, ""):
        return str(direct)
    data = response.get("data") if isinstance(response.get("data"), Mapping) else {}
    return str(data.get("msg") or data.get("message") or "")


def match_guard_error(
    response: Mapping[str, Any],
    *,
    business_codes: Sequence[str],
    http_statuses: Sequence[int],
    message_patterns: Sequence[str],
) -> str:
    business_code = str(response.get("business_code") or response.get("error_code") or "")
    if business_code and business_code in {str(value) for value in business_codes}:
        return "business_code"
    structured_code = _structured_error_code(response)
    if structured_code and structured_code in {str(value) for value in business_codes}:
        return "structured_error"
    try:
        http_status = int(response.get("http_status") or 0)
    except (TypeError, ValueError):
        http_status = 0
    if http_status and http_status in {int(value) for value in http_statuses}:
        return "http_status"
    message = _response_message(response)
    if any(re.search(pattern, message, flags=re.IGNORECASE) for pattern in message_patterns):
        return "message_regex"
    return ""


def select_execution_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    batch_no: str,
    problem_goods_id: str,
) -> list[Mapping[str, Any]]:
    return [
        row
        for row in rows
        if str(row.get("batch_no") or "") == str(batch_no)
        and str(row.get("problem_goods_id") or "") == str(problem_goods_id)
    ]


class GuardExecutor:
    def __init__(
        self,
        precondition_provider: Callable[
            [GuardScenarioSpec, Mapping[str, Any], Mapping[str, Any]],
            Mapping[str, Any],
        ],
        action_gateway: Callable[
            [str, Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]],
            Mapping[str, Any],
        ],
    ) -> None:
        self.precondition_provider = precondition_provider
        self.action_gateway = action_gateway

    @staticmethod
    def _payload(
        spec: GuardScenarioSpec,
        case: Mapping[str, Any],
        context: Mapping[str, Any],
        prepared: Mapping[str, Any] | None = None,
    ) -> ExecutionResultPayload:
        prepared = dict(prepared or {})
        return ExecutionResultPayload(
            execution_id=str(context.get("execution_id") or ""),
            batch_id=str(context.get("batch_id") or ""),
            case_id=str(case.get("id") or case.get("case_id") or ""),
            status="blocked",
            guard_kind=spec.guard_kind,
            expected_stage=spec.expected_stage,
            actor=dict(prepared.get("actor") or {}),
            order_sn=str(prepared.get("order_sn") or context.get("order_sn") or ""),
            problem_goods_id=str(prepared.get("problem_goods_id") or context.get("problem_goods_id") or ""),
            purchase_record_ids=[str(value) for value in prepared.get("purchase_record_ids") or []],
            parameter_snapshot=dict((case.get("_execution") or {}).get("parameter_snapshot") or {}),
            precondition_evidence=dict(prepared.get("precondition_evidence") or {}),
            before_evidence=dict(prepared.get("before_evidence") or {}),
        )

    @staticmethod
    def _evaluate_large_refund(
        payload: ExecutionResultPayload,
        spec: GuardScenarioSpec,
        prepared: Mapping[str, Any],
        response: Mapping[str, Any],
    ) -> ExecutionResultPayload:
        normal_step = response.get("normal_step") if isinstance(response.get("normal_step"), Mapping) else {}
        normal_stage = str(normal_step.get("actual_stage") or response.get("actual_stage") or "")
        if normal_stage != spec.expected_stage:
            payload.status = "failed"
            payload.reason_code = "unexpected_guard_stage"
            payload.failure_reason = f"普通账号拦截发生在 {normal_stage or '未知阶段'}"
            return payload
        matched_by = match_guard_error(
            normal_step,
            business_codes=spec.business_codes,
            http_statuses=spec.http_statuses,
            message_patterns=spec.message_patterns,
        )
        if not matched_by:
            payload.status = "failed"
            payload.reason_code = "guard_not_triggered"
            payload.failure_reason = "普通账号没有命中大额退款权限拦截"
            return payload
        normal_diff_rows = normal_step.get("business_diffs")
        if normal_diff_rows is None:
            normal_diff_rows = response.get("business_diffs") or []
        normal_diffs = [
            dict(row)
            for row in normal_diff_rows
            if isinstance(row, Mapping)
        ]
        if normal_diffs:
            payload.status = "failed"
            payload.reason_code = "normal_guard_side_effect"
            payload.business_diffs = normal_diffs
            payload.forbidden_effects = normal_diffs
            payload.failure_reason = "普通账号权限拦截步骤产生了业务变化"
            return payload

        composite_state = str(response.get("composite_state") or "")
        if composite_state == "waiting_account":
            payload.status = "waiting"
            payload.reason_code = "account_required"
            payload.failure_reason = "普通账号已被拦截，等待部长账号从同一问题产品继续"
            return payload
        if composite_state != "completed":
            payload.status = "failed"
            payload.reason_code = "large_refund_composite_incomplete"
            payload.failure_reason = "大额退款复合场景没有完成部长账号步骤"
            return payload

        minister_step = response.get("minister_step") if isinstance(response.get("minister_step"), Mapping) else {}
        actor = minister_step.get("actor") if isinstance(minister_step.get("actor"), Mapping) else {}
        credit = minister_step.get("balance_credit") if isinstance(minister_step.get("balance_credit"), Mapping) else {}
        same_problem = str(minister_step.get("problem_goods_id") or "") == payload.problem_goods_id
        credit_verified = bool(credit.get("record_id")) and str(credit.get("direction") or "") == "credit"
        if str(actor.get("role") or "") != "department_leader" or not same_problem or not credit_verified:
            payload.status = "failed"
            payload.reason_code = "minister_completion_evidence_missing"
            payload.failure_reason = "部长账号、同一问题产品或余额入账证据不完整"
            return payload

        payload.actor = dict(actor)
        payload.business_diffs = [
            dict(row) for row in response.get("business_diffs") or [] if isinstance(row, Mapping)
        ]
        payload.status = "passed"
        payload.reason_code = "large_refund_composite_completed"
        return classify_business_diffs(
            payload,
            required_rules=list(prepared.get("required_effect_rules") or []),
            forbidden_rules=list(prepared.get("forbidden_effect_rules") or []),
            allowed_rules=list(prepared.get("allowed_effect_rules") or []),
        )

    @staticmethod
    def _checkpoint(
        context: Mapping[str, Any],
        payload: ExecutionResultPayload,
        step: str,
        write_state: str,
        *,
        resume_payload: Mapping[str, Any] | None = None,
    ) -> None:
        callback = context.get("checkpoint")
        if not callable(callback):
            return
        checkpoint = {
                "execution_id": payload.execution_id,
                "current_step": step,
                "order_sn": payload.order_sn,
                "problem_goods_id": payload.problem_goods_id,
                "purchase_record_ids": payload.purchase_record_ids,
                "completed_actions": [row.get("action") for row in payload.attempted_actions],
                "before_evidence": payload.before_evidence,
                "last_write": {"state": write_state, "idempotent": False},
            }
        if isinstance(resume_payload, Mapping):
            checkpoint["resume_payload"] = dict(resume_payload)
        callback(checkpoint)

    def execute(self, case: Mapping[str, Any], context: Mapping[str, Any]) -> Mapping[str, Any]:
        spec = guard_scenario(str((case.get("parameters") or {}).get("guard_kind") or ""))
        execution_state = context.get("execution_state") if isinstance(context.get("execution_state"), Mapping) else {}
        resume_payload = execution_state.get("resume_payload") if isinstance(execution_state.get("resume_payload"), Mapping) else {}
        recovered_response = (
            resume_payload.get("confirmed_response")
            if str(context.get("resume_stage") or "") == "result_verification"
            and isinstance(resume_payload.get("confirmed_response"), Mapping)
            else None
        )
        if recovered_response is not None:
            prepared = dict(resume_payload.get("prepared") or {})
        else:
            try:
                prepared = dict(self.precondition_provider(spec, case, context) or {})
            except GuardPreconditionMissing as exc:
                payload = self._payload(spec, case, context)
                payload.reason_code = "precondition_capability_missing"
                payload.failure_reason = str(exc)
                return payload.to_dict()

        payload = self._payload(spec, case, context, prepared)
        payload.attempted_actions.append(
            {
                "action": spec.target_action,
                "stage": spec.expected_stage,
                "actor": payload.actor,
                "fields": dict(prepared.get("action_fields") or {}),
            }
        )
        if recovered_response is not None:
            response = dict(recovered_response)
            payload.attempted_actions[-1]["replayed"] = False
            payload.attempted_actions[-1]["result_verification_only"] = True
        else:
            self._checkpoint(context, payload, f"guard.{spec.expected_stage}.before", "indeterminate")
            try:
                response = dict(self.action_gateway(spec.target_action, prepared, case, context) or {})
            except GuardActionUnavailable as exc:
                payload.reason_code = "target_action_unavailable"
                payload.failure_reason = str(exc)
                self._checkpoint(context, payload, f"guard.{spec.expected_stage}.unavailable", "confirmed_not_written")
                return payload.to_dict()
            except GuardWriteTimeout as exc:
                response = dict(exc.probe() or {})
                write_state = str(response.get("write_state") or "indeterminate")
                if write_state == "indeterminate":
                    payload.reason_code = "unknown_write_state"
                    payload.failure_reason = str(exc)
                    payload.response_evidence.append(response)
                    self._checkpoint(context, payload, f"guard.{spec.expected_stage}.indeterminate", write_state)
                    return payload.to_dict()
        payload.response_evidence.append(response)
        payload.order_sn = str(response.get("order_sn") or payload.order_sn)
        payload.problem_goods_id = str(response.get("problem_goods_id") or payload.problem_goods_id)
        if response.get("purchase_record_ids"):
            payload.purchase_record_ids = [str(value) for value in response.get("purchase_record_ids") or []]
        payload.actual_stage = str(response.get("actual_stage") or spec.expected_stage)
        payload.after_evidence = dict(response.get("after_evidence") or {})
        payload.business_diffs = [dict(row) for row in response.get("business_diffs") or [] if isinstance(row, Mapping)]
        if recovered_response is None:
            public_prepared = {
                key: prepared.get(key)
                for key in (
                    "order_sn",
                    "problem_goods_id",
                    "purchase_record_ids",
                    "precondition_evidence",
                    "before_evidence",
                    "action_fields",
                    "actor",
                    "forbidden_effect_rules",
                    "required_effect_rules",
                    "allowed_effect_rules",
                )
                if prepared.get(key) is not None
            }
            next_resume = (
                dict(response.get("resume_payload"))
                if isinstance(response.get("resume_payload"), Mapping)
                else {}
            )
            next_resume.setdefault("confirmed_response", response)
            next_resume.setdefault("prepared", public_prepared)
            self._checkpoint(
                context,
                payload,
                f"guard.{spec.expected_stage}.after",
                str(response.get("write_state") or "confirmed_not_written"),
                resume_payload=next_resume,
            )

        if payload.actual_stage != payload.expected_stage:
            payload.status = "failed"
            payload.reason_code = "unexpected_guard_stage"
            payload.failure_reason = f"预期阶段 {payload.expected_stage}，实际阶段 {payload.actual_stage}"
            return payload.to_dict()

        if spec.guard_kind == "large_refund_account":
            payload.response_evidence = [
                dict(value)
                for value in (response.get("normal_step"), response.get("minister_step"))
                if isinstance(value, Mapping)
            ]
            return self._evaluate_large_refund(payload, spec, prepared, response).to_dict()

        matched_by = match_guard_error(
            response,
            business_codes=spec.business_codes,
            http_statuses=spec.http_statuses,
            message_patterns=spec.message_patterns,
        )
        if matched_by:
            payload.status = "passed"
            payload.reason_code = "guard_triggered"
            payload.response_evidence[-1]["matched_by"] = matched_by
        elif response.get("success") is True or int(response.get("http_status") or 0) < 400:
            payload.status = "failed"
            payload.reason_code = "backend_guard_missing"
            payload.failure_reason = "目标接口已执行，但服务端没有触发声明的拦截规则"
        else:
            payload.status = "failed"
            payload.reason_code = "unexpected_guard_error"
            payload.failure_reason = str(
                response.get("error_message")
                or response.get("message")
                or "实际错误与规则声明不匹配"
            )

        payload = classify_business_diffs(
            payload,
            required_rules=[],
            forbidden_rules=list(prepared.get("forbidden_effect_rules") or []),
            allowed_rules=list(prepared.get("allowed_effect_rules") or []),
        )
        return payload.to_dict()


class LiveGuardDriver:
    def __init__(
        self,
        env: Any,
        problem_runner: Any,
        *,
        gateway_factory: Callable[..., Any] | None = None,
        flow_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.env = env
        self.problem_runner = problem_runner
        if gateway_factory is None:
            from app.data_scripts.problem_goods import ProblemGoodsGateway

            gateway_factory = ProblemGoodsGateway
        self.gateway_factory = gateway_factory
        if flow_factory is None:
            from app.data_scripts.problem_goods import ProblemGoodsFlow

            flow_factory = ProblemGoodsFlow
        self.flow_factory = flow_factory

    @staticmethod
    def _balance_row_id(row: Mapping[str, Any]) -> str:
        return str(
            row.get("id")
            or row.get("record_id")
            or row.get("bill_id")
            or row.get("流水号")
            or ""
        )

    @classmethod
    def _new_balance_rows(
        cls,
        before: Sequence[Mapping[str, Any]],
        after: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        before_ids = {cls._balance_row_id(row) for row in before if cls._balance_row_id(row)}
        return [
            dict(row)
            for row in after
            if not cls._balance_row_id(row) or cls._balance_row_id(row) not in before_ids
        ]

    @staticmethod
    def _credit_amount(row: Mapping[str, Any]) -> Decimal:
        raw = row.get("change_amount")
        if raw in (None, ""):
            raw = row.get("amount") or 0
        return Decimal(str(raw))

    def _wait_balance_rows(
        self,
        gateway: Any,
        order_sn: str,
        before: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for attempt in range(6):
            rows = self._new_balance_rows(before, gateway.balance_changes(order_sn))
            if rows:
                return rows
            if attempt < 5:
                time.sleep(0.5 * (attempt + 1))
        return rows

    def _large_refund_case(self, case: Mapping[str, Any]) -> dict[str, Any]:
        copied = {**dict(case), "parameters": dict(case.get("parameters") or {})}
        parameters = copied["parameters"]
        parameters.setdefault("adjustment", "quantity_all_down")
        parameters.setdefault("problem_order_quantity", 6)
        parameters.setdefault(
            "items",
            [{"sorting": 1, "quantity": 6, "offer_price": {"value": "100", "currency": "CNY"}}],
        )
        return copied

    def _prepare_large_refund(
        self,
        case: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        from app.data_scripts.problem_goods import _purchase_fields

        from .problem_runner import build_problem_goods_request, estimate_refund_cny

        execution_state = context.get("execution_state") if isinstance(context.get("execution_state"), Mapping) else {}
        resume = execution_state.get("resume_payload") if isinstance(execution_state.get("resume_payload"), Mapping) else None
        if resume:
            variables = {
                **dict(resume.get("variables") or {}),
                **dict(context.get("variables") or {}),
                "order_sn": str(resume.get("order_sn") or context.get("order_sn") or ""),
                "problem_goods_id": str(resume.get("problem_goods_id") or context.get("problem_goods_id") or ""),
                "allow_large_refund": True,
                "confirm_distribution": False,
            }
            gateway = self.gateway_factory(
                self.env,
                variables,
                {"script": "日本站系统回归大额退款恢复", "guard_kind": "large_refund_account"},
            )
            return {
                **dict(resume),
                "gateway": gateway,
                "variables": variables,
                "actor": {"role": "department_leader"},
                "before_evidence": {"balance_rows": gateway.balance_changes(variables["order_sn"])},
                "resuming_minister": True,
                "required_effect_rules": [{"entity": "customer_balance", "field": "credit"}],
            }

        large_case = self._large_refund_case(case)
        run_context = dict(self.problem_runner.candidate_loader(large_case, context))
        candidate = run_context.get("candidate") if isinstance(run_context.get("candidate"), Mapping) else {}
        if not candidate:
            raise GuardPreconditionMissing("大额退款场景缺少可处理的真实采购记录")
        request = build_problem_goods_request(
            large_case["parameters"],
            candidate,
            expected_direction="credit",
        )
        refund_cny = estimate_refund_cny(candidate, request)
        if refund_cny < Decimal("500"):
            raise GuardPreconditionMissing(f"大额退款前置金额不足500元：{refund_cny}")
        variables = {
            **dict(run_context.get("variables") or context.get("variables") or {}),
            **request,
            "order_sn": str(run_context.get("order_sn") or ""),
            "allow_large_refund": True,
            "confirm_distribution": False,
        }
        gateway = self.gateway_factory(
            self.env,
            variables,
            {"script": "日本站系统回归大额退款普通账号", "guard_kind": "large_refund_account"},
        )
        return {
            "order_sn": variables["order_sn"],
            "problem_goods_id": "",
            "purchase_record_ids": [str(candidate.get("order_purchase_id") or "")],
            "precondition_evidence": {"candidate": dict(candidate), "estimated_refund_cny": str(refund_cny)},
            "before_evidence": {"balance_rows": gateway.balance_changes(variables["order_sn"])},
            "action_fields": _purchase_fields(0, variables),
            "actor": {"role": "normal"},
            "gateway": gateway,
            "variables": variables,
            "forbidden_effect_rules": [{"entity": "customer_balance", "field": "credit"}],
            "required_effect_rules": [{"entity": "customer_balance", "field": "credit"}],
        }

    @staticmethod
    def _problem_rows(gateway: Any, order_sn: str) -> list[dict[str, Any]]:
        try:
            return [dict(row) for row in gateway.list_problems(order_sn, 0)]
        except Exception:
            return []

    def _prepare_problem_create(
        self,
        spec: GuardScenarioSpec,
        case: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        from app.data_scripts.problem_goods import _create_fields

        from .problem_runner import build_problem_goods_request

        run_context = dict(self.problem_runner.candidate_loader(case, context))
        candidate = run_context.get("candidate") if isinstance(run_context.get("candidate"), Mapping) else {}
        if not candidate:
            raise GuardPreconditionMissing("问题产品目标接口缺少可用采购记录")
        parameters = dict(case.get("parameters") or {})
        request = build_problem_goods_request(
            parameters,
            candidate,
            expected_direction="none",
        )
        if spec.guard_kind == "problem_num_over_unstored":
            available = max(
                0,
                int(candidate.get("possible_num") or 0) - int(candidate.get("storage_num") or 0),
            )
            request["problem_num"] = available + 1
        elif spec.guard_kind == "duplicate_open_problem":
            request["problem_num"] = 1
        variables = {
            **dict(run_context.get("variables") or context.get("variables") or {}),
            **request,
            "order_sn": str(run_context.get("order_sn") or context.get("order_sn") or ""),
        }
        gateway = self.gateway_factory(
            self.env,
            variables,
            {"script": "日本站系统回归拦截", "guard_kind": spec.guard_kind},
        )
        order_sn = variables["order_sn"]
        action_fields = _create_fields(variables)
        if spec.guard_kind == "duplicate_open_problem":
            try:
                gateway.create_problem(action_fields)
            except Exception as exc:
                raise GuardPreconditionMissing(f"无法创建用于重复提出的首条问题产品：{exc}") from exc
            if not self._problem_rows(gateway, order_sn):
                raise GuardPreconditionMissing("首条问题产品创建后无法查询，禁止继续重复提交")
        return {
            "order_sn": order_sn,
            "problem_goods_id": "",
            "purchase_record_ids": [str(candidate.get("order_purchase_id") or "")],
            "precondition_evidence": {
                "candidate": dict(candidate),
                "target_interface": "/problem.store",
            },
            "before_evidence": {"problem_rows": self._problem_rows(gateway, order_sn)},
            "action_fields": action_fields,
            "actor": {"role": "normal"},
            "gateway": gateway,
            "variables": variables,
            "forbidden_effect_rules": [{"entity": "problem_goods", "field": "count"}],
        }

    def _prepare_staged_problem(
        self,
        spec: GuardScenarioSpec,
        case: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        from app.data_scripts.problem_goods import (
            STATUS_BUSINESS_PENDING,
            STATUS_CLIENT_PENDING,
            STATUS_PURCHASE_PENDING,
            _business_fields,
            _create_fields,
            _problem_id,
            _purchase_fields,
            normalize_flow_variables,
        )

        from .problem_runner import build_problem_goods_request

        run_context = dict(self.problem_runner.candidate_loader(case, context))
        candidate = run_context.get("candidate") if isinstance(run_context.get("candidate"), Mapping) else {}
        if not candidate:
            raise GuardPreconditionMissing(f"{spec.guard_kind} 缺少可处理的真实采购记录")
        parameters = dict(case.get("parameters") or {})
        request = build_problem_goods_request(parameters, candidate, expected_direction="none")
        possible_num = int(candidate.get("possible_num") or request.get("pre_num") or 0)
        storage_num = int(candidate.get("storage_num") or 0)
        if spec.guard_kind == "pre_num_below_storage":
            if storage_num <= 0:
                raise GuardPreconditionMissing("当前真实采购记录没有已上架数量，无法构造小于已上架数")
            request["pre_num"] = storage_num - 1
        elif spec.guard_kind in {"quantity_over_possible", "quantity_up_auto_option"}:
            request["pre_num"] = possible_num + 1
            request["option_deal_suggest"] = 2
        elif spec.guard_kind == "option_num_over_goods":
            options = [dict(row) for row in candidate.get("option") or [] if isinstance(row, Mapping)]
            if not options:
                raise GuardPreconditionMissing("真实订单缺少 OPTION，无法构造 OPTION 数量超过商品数")
            options[0]["num"] = possible_num + 1
            request["option_new"] = options
            request["option_deal_suggest"] = 2
        elif spec.guard_kind == "multiple_rate_auto":
            options = [
                dict(row)
                for row in candidate.get("option") or []
                if isinstance(row, Mapping) and int(row.get("price_type") or 0) == 1
            ]
            if len(options) < 2:
                raise GuardPreconditionMissing("真实订单没有两个百分比 OPTION，无法构造自动计算场景")
            request["option_new"] = options
            request["option_deal_suggest"] = 2
        elif spec.guard_kind == "option_price_type_change":
            options = [dict(row) for row in candidate.get("option") or [] if isinstance(row, Mapping)]
            if not options or options[0].get("id") in (None, ""):
                raise GuardPreconditionMissing("真实订单缺少带 option_id 的 OPTION")
            options[0]["price_type"] = 0 if int(options[0].get("price_type") or 0) == 1 else 1
            request["option_new"] = options
            request["option_deal_suggest"] = 1
        elif spec.guard_kind == "multiple_purchase_update":
            purchase_count = int(candidate.get("order_purchase_count") or candidate.get("same_purchase_count") or 1)
            if purchase_count <= 1:
                raise GuardPreconditionMissing("当前番号只有一条采购记录，无法构造同番多采购")
        elif spec.guard_kind == "restricted_skip_purchase":
            if not str(candidate.get("purchase_no") or run_context.get("purchase_no") or "").strip():
                raise GuardPreconditionMissing("真实采购记录缺少交易号，无法构造禁止跳过采购")
            request["problem_type"] = int(parameters.get("restricted_problem_type") or 3)
        elif spec.guard_kind == "direct_complete_invalid_type":
            request["problem_type"] = int(parameters.get("invalid_problem_type") or 8)

        variables = {
            **dict(run_context.get("variables") or context.get("variables") or {}),
            **request,
            "order_sn": str(run_context.get("order_sn") or ""),
        }
        variables = normalize_flow_variables(variables)
        gateway = self.gateway_factory(
            self.env,
            variables,
            {"script": "日本站系统回归分阶段拦截", "guard_kind": spec.guard_kind},
        )
        gateway.create_problem(_create_fields(variables))
        row = gateway.find_problem(variables["order_sn"], 0, int(candidate.get("order_purchase_id") or 0))
        if not row:
            raise GuardPreconditionMissing("问题产品创建后无法按本批采购记录唯一查询")
        problem_goods_id = _problem_id(row)
        gateway.translate(problem_goods_id, variables["translation_content"])
        row = gateway.wait_for_status(variables["order_sn"], problem_goods_id, STATUS_CLIENT_PENDING)
        if not row:
            raise GuardPreconditionMissing("问题产品未进入客户处理阶段")
        gateway.client_reply(problem_goods_id, variables["client_deal_text"])
        row = gateway.wait_for_status(variables["order_sn"], problem_goods_id, STATUS_BUSINESS_PENDING)
        if not row:
            raise GuardPreconditionMissing("问题产品未进入业务处理阶段")

        if spec.expected_stage == "purchase_deal":
            gateway.business_deal(_business_fields(problem_goods_id, variables, preview=False), preview=False)
            row = gateway.wait_for_status(variables["order_sn"], problem_goods_id, STATUS_PURCHASE_PENDING)
            if not row:
                raise GuardPreconditionMissing("问题产品未进入采购处理阶段")

        if spec.target_action == "purchase_deal":
            action_fields: Mapping[str, Any] = _purchase_fields(problem_goods_id, variables)
        elif spec.target_action == "business_deal":
            action_fields = _business_fields(problem_goods_id, variables, preview=False)
            if spec.guard_kind == "restricted_skip_purchase":
                action_fields = {**dict(action_fields), "jump_g": 1, "preview_bill": 0}
        elif spec.target_action == "update_pre_data":
            action_fields = {
                "problem_goods_id": problem_goods_id,
                "pre_num": variables["pre_num"],
                "pre_price": variables["pre_price"],
                "pre_freight": variables["pre_freight"],
            }
        elif spec.target_action == "update_options":
            action_fields = {"problem_goods_id": problem_goods_id, "options": list(variables.get("option_new") or [])}
        else:
            action_fields = {"problem_goods_id": problem_goods_id}
        return {
            "order_sn": variables["order_sn"],
            "problem_goods_id": str(problem_goods_id),
            "purchase_record_ids": [str(candidate.get("order_purchase_id") or "")],
            "precondition_evidence": {"candidate": dict(candidate), "problem_row": dict(row)},
            "before_evidence": {"problem_row": dict(row)},
            "action_fields": dict(action_fields),
            "actor": {"role": "normal"},
            "gateway": gateway,
            "variables": variables,
            "forbidden_effect_rules": [
                {"entity": "problem_goods", "field": "status"},
                {"entity": "customer_balance", "field": "credit"},
            ],
        }

    def prepare(
        self,
        spec: GuardScenarioSpec,
        case: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        supplied = context.get("guard_precondition")
        if isinstance(supplied, Mapping):
            return dict(supplied)
        if spec.guard_kind in {"duplicate_open_problem", "problem_num_over_unstored"}:
            return self._prepare_problem_create(spec, case, context)
        if spec.guard_kind == "large_refund_account":
            return self._prepare_large_refund(case, context)
        if spec.guard_kind in {
            "pre_num_below_storage",
            "quantity_over_possible",
            "quantity_up_auto_option",
            "option_num_over_goods",
            "multiple_rate_auto",
            "option_price_type_change",
            "multiple_purchase_update",
            "restricted_skip_purchase",
            "direct_complete_invalid_type",
        }:
            return self._prepare_staged_problem(spec, case, context)
        raise GuardPreconditionMissing(f"当前环境未提供 {spec.precondition_builder} 所需的真实前置状态构造能力")

    def perform(
        self,
        action: str,
        prepared: Mapping[str, Any],
        case: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        callback = prepared.get("target_callback")
        if callable(callback):
            return dict(callback(action, prepared, case, context) or {})
        gateway = prepared.get("gateway")
        if gateway is None:
            raise GuardActionUnavailable(f"目标动作 {action} 没有可调用的真实后端接口")
        if action == "large_refund_composite":
            return self._perform_large_refund(prepared, case, context)
        try:
            if action == "create_problem":
                response = dict(gateway.create_problem(dict(prepared.get("action_fields") or {})) or {})
            elif action == "purchase_deal":
                response = dict(gateway.purchase_deal(dict(prepared.get("action_fields") or {})) or {})
            elif action == "business_deal":
                response = dict(gateway.business_deal(dict(prepared.get("action_fields") or {}), preview=False) or {})
            elif action == "update_pre_data":
                fields = dict(prepared.get("action_fields") or {})
                response = dict(gateway.update_pre_data(fields["problem_goods_id"], fields["pre_num"], fields["pre_price"], fields["pre_freight"]) or {})
            elif action == "update_options":
                fields = dict(prepared.get("action_fields") or {})
                response = dict(gateway.update_options(fields["problem_goods_id"], list(fields.get("options") or [])) or {})
            elif action == "distribution_direct_complete":
                fields = dict(prepared.get("action_fields") or {})
                response = dict(
                    gateway._admin_request(
                        gateway._path("problem_distribution_direct_complete", "/problem.distributionDirectComplete"),
                        {"ids[0]": fields["problem_goods_id"], "preview_bill": 0},
                        "配货直接完成",
                        mutation=True,
                    )
                    or {}
                )
            else:
                raise GuardActionUnavailable(f"目标动作 {action} 尚未接入真实后端接口")
        except GuardActionUnavailable:
            raise
        except Exception as exc:
            raw = dict(getattr(exc, "payload", {}) or {})
            return {
                "actual_stage": guard_scenario(str((case.get("parameters") or {}).get("guard_kind") or "")).expected_stage,
                "success": False,
                "business_code": str(raw.get("code") or raw.get("error_code") or ""),
                "structured_error": str(raw.get("error") or ""),
                "error_message": str(raw.get("msg") or raw.get("message") or exc),
                "raw": raw,
                "business_diffs": [],
                "after_evidence": {"problem_rows": self._problem_rows(gateway, str(prepared.get("order_sn") or ""))},
                "write_state": "confirmed_not_written",
            }
        return {
            "actual_stage": guard_scenario(str((case.get("parameters") or {}).get("guard_kind") or "")).expected_stage,
            "success": True,
            "business_code": str(response.get("code") or ""),
            "error_message": str(response.get("msg") or response.get("message") or ""),
            "raw": response,
            "business_diffs": [],
            "after_evidence": {"problem_rows": self._problem_rows(gateway, str(prepared.get("order_sn") or ""))},
            "write_state": "confirmed_written",
        }

    def _perform_large_refund(
        self,
        prepared: Mapping[str, Any],
        case: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        gateway = prepared["gateway"]
        variables = dict(prepared.get("variables") or {})
        order_sn = str(prepared.get("order_sn") or variables.get("order_sn") or "")
        before_rows = list((prepared.get("before_evidence") or {}).get("balance_rows") or [])
        normal_step = dict(prepared.get("normal_step") or {})
        problem_goods_id = str(prepared.get("problem_goods_id") or variables.get("problem_goods_id") or "")

        if not prepared.get("resuming_minister"):
            normal_result = dict(self.flow_factory(gateway, variables, {}).run() or {})
            problem_goods_id = str(normal_result.get("problem_goods_id") or problem_goods_id)
            normal_after = gateway.balance_changes(order_sn)
            normal_new = self._new_balance_rows(before_rows, normal_after)
            normal_diffs = [
                {"entity": "customer_balance", "field": "credit", "before": "0", "after": str(self._credit_amount(row)), "record_id": self._balance_row_id(row)}
                for row in normal_new
            ]
            normal_step = {
                "actual_stage": str(normal_result.get("resume_stage") or "purchase_deal"),
                "business_code": "MINISTER_ACCOUNT_REQUIRED" if normal_result.get("permission_required") else "",
                "error_message": str(normal_result.get("reason") or ""),
                "business_diffs": normal_diffs,
                "raw": normal_result,
            }
            if normal_diffs or not normal_result.get("permission_required"):
                return {
                    "actual_stage": "purchase_deal",
                    "order_sn": order_sn,
                    "problem_goods_id": problem_goods_id,
                    "purchase_record_ids": list(prepared.get("purchase_record_ids") or []),
                    "composite_state": "completed" if not normal_result.get("permission_required") else "waiting_account",
                    "normal_step": normal_step,
                    "business_diffs": normal_diffs,
                    "write_state": "confirmed_written" if normal_diffs else "confirmed_not_written",
                }

            try:
                account_values = dict(
                    self.problem_runner.account_resolver(
                        case,
                        {**dict(context), "order_sn": order_sn, "problem_goods_id": problem_goods_id},
                        variables,
                        Decimal(str((prepared.get("precondition_evidence") or {}).get("estimated_refund_cny") or 500)),
                    )
                    or {}
                )
            except Exception as exc:
                if exc.__class__.__name__ != "AccountLoginRequired":
                    raise
                resume_payload = {
                    "order_sn": order_sn,
                    "problem_goods_id": problem_goods_id,
                    "purchase_record_ids": list(prepared.get("purchase_record_ids") or []),
                    "variables": variables,
                    "normal_step": normal_step,
                    "precondition_evidence": dict(prepared.get("precondition_evidence") or {}),
                }
                return {
                    "actual_stage": "purchase_deal",
                    "order_sn": order_sn,
                    "problem_goods_id": problem_goods_id,
                    "purchase_record_ids": list(prepared.get("purchase_record_ids") or []),
                    "composite_state": "waiting_account",
                    "normal_step": normal_step,
                    "business_diffs": [],
                    "resume_payload": resume_payload,
                    "write_state": "confirmed_not_written",
                }
            minister_variables = {**variables, **account_values, "problem_goods_id": problem_goods_id}
            gateway = self.gateway_factory(
                self.env,
                minister_variables,
                {"script": "日本站系统回归大额退款部长账号", "guard_kind": "large_refund_account"},
            )
            variables = minister_variables

        minister_before = gateway.balance_changes(order_sn)
        minister_result = dict(self.flow_factory(gateway, variables, {}).run() or {})
        credit_rows = self._wait_balance_rows(gateway, order_sn, minister_before)
        credits = [row for row in credit_rows if self._credit_amount(row) > 0]
        credit = credits[0] if len(credits) == 1 else {}
        business_diffs = [
            {
                "entity": "customer_balance",
                "field": "credit",
                "before": "0",
                "after": str(self._credit_amount(row)),
                "record_id": self._balance_row_id(row),
            }
            for row in credits
        ]
        return {
            "actual_stage": "purchase_deal",
            "order_sn": order_sn,
            "problem_goods_id": str(minister_result.get("problem_goods_id") or problem_goods_id),
            "purchase_record_ids": list(prepared.get("purchase_record_ids") or []),
            "composite_state": "completed",
            "normal_step": normal_step,
            "minister_step": {
                "actor": {"role": "department_leader"},
                "problem_goods_id": str(minister_result.get("problem_goods_id") or problem_goods_id),
                "balance_credit": {
                    "record_id": self._balance_row_id(credit),
                    "amount": str(self._credit_amount(credit)) if credit else "0",
                    "direction": "credit" if credit else "",
                    "raw": dict(credit),
                },
                "raw": minister_result,
            },
            "business_diffs": business_diffs,
            "write_state": "confirmed_written" if business_diffs else "confirmed_not_written",
        }


__all__ = [
    "GuardActionUnavailable",
    "GuardExecutor",
    "GuardPreconditionMissing",
    "GuardWriteTimeout",
    "LiveGuardDriver",
    "match_guard_error",
    "select_execution_rows",
]
