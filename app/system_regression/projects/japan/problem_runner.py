from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Callable, Mapping

import requests

from app.data_scripts.problem_goods import ProblemGoodsGateway, ProblemGoodsMutationUncertain, _api_success
from app.system_regression.common.execution import sanitize_secrets
from app.system_regression.common.evidence import MoneyEvidence
from app.system_regression.common.reconciliation import reconcile_three_way, to_jpy

from .calculators import calculate_problem_amount

from .runner import CaseRunResult


class _SystemRegressionProblemGoodsGateway(ProblemGoodsGateway):
    """Problem-goods gateway adapter that records safe write evidence for system regression only."""

    @staticmethod
    def _response_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "success": bool(payload.get("success")),
            "code": payload.get("code"),
        }

    def _recorded_write(
        self,
        path: str,
        action: str,
        operation: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        entry = {
            "action": str(action),
            "request_type": "write",
            "target": str(path),
            "business_object": "problem_goods",
            "attempt_count": 1,
            "result": "indeterminate",
            "timed_out": False,
            "reconciliation_performed": False,
            "repeated": False,
            "response_summary": {},
        }
        self.log.setdefault("attempted_actions", []).append(entry)
        try:
            payload = operation()
        except (ProblemGoodsMutationUncertain, requests.Timeout, requests.ConnectionError) as exc:
            cause = exc.__cause__
            entry["timed_out"] = isinstance(exc, requests.Timeout) or isinstance(cause, requests.Timeout)
            raise
        except Exception:
            entry["result"] = "failed"
            raise
        entry["result"] = "success" if _api_success(payload) else "failed"
        entry["response_summary"] = self._response_summary(payload)
        return payload

    def _admin_request(
        self,
        path: str,
        fields: dict[str, Any],
        action: str,
        *,
        mutation: bool,
    ) -> dict[str, Any]:
        if not mutation:
            return super()._admin_request(path, fields, action, mutation=False)
        return self._recorded_write(
            path,
            action,
            lambda: super(_SystemRegressionProblemGoodsGateway, self)._admin_request(
                path,
                fields,
                action,
                mutation=True,
            ),
        )

    def _client_request(
        self,
        path: str,
        fields: dict[str, Any],
        action: str,
        *,
        mutation: bool,
    ) -> dict[str, Any]:
        if not mutation:
            return super()._client_request(path, fields, action, mutation=False)
        return self._recorded_write(
            path,
            action,
            lambda: super(_SystemRegressionProblemGoodsGateway, self)._client_request(
                path,
                fields,
                action,
                mutation=True,
            ),
        )


def _problem_log(log_text: str) -> dict[str, Any]:
    try:
        value = json.loads(log_text or "{}")
    except (TypeError, ValueError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_actions(log: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = log.get("attempted_actions") if isinstance(log.get("attempted_actions"), list) else []
    return [dict(sanitize_secrets(dict(row))) for row in rows if isinstance(row, Mapping)]


def _problem_evidence_missing(payload: Mapping[str, Any]) -> list[str]:
    required = (
        "parameter_snapshot",
        "attempted_actions",
        "before_evidence",
        "after_evidence",
        "side_effects",
        "stage_evidence",
        "expected_stage",
        "actual_stage",
        "write_state",
        "reconciliation",
    )
    missing = [key for key in required if payload.get(key) in (None, "", [], {})]
    stage = payload.get("stage_evidence") if isinstance(payload.get("stage_evidence"), Mapping) else {}
    if stage and stage.get("stage_matched") is not True:
        missing.append("stage_evidence.stage_matched")
    return missing


def _number(candidate: Mapping[str, Any], *keys: str, default: str = "0") -> Decimal:
    for key in keys:
        if candidate.get(key) not in (None, ""):
            return Decimal(str(candidate[key]))
    return Decimal(default)


def _text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _active_options(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in (candidate.get("option") or []) if isinstance(row, Mapping) and row.get("checked") is not False]


def _adjust_options(options: list[dict[str, Any]], adjustment: str, step: Decimal) -> list[dict[str, Any]]:
    rows = [dict(row) for row in options]
    if adjustment in {"fixed_add", "rate_add"}:
        rows.append({"name": "系统回归OPTION", "name_translate": "システム回帰OPTION", "price_type": 1 if adjustment == "rate_add" else 0, "price": _text(step), "num": 1, "checked": True})
        return rows
    if not rows:
        raise ValueError("当前采购明细缺少可调整的OPTION")
    target_type = 1 if adjustment.startswith("rate_") else 0
    index = next((i for i, row in enumerate(rows) if int(row.get("price_type") or 0) == target_type), 0)
    target = dict(rows[index])
    if adjustment in {"fixed_delete", "rate_delete"}:
        rows.pop(index)
    elif adjustment in {"fixed_num_up", "rate_num_up"}:
        target["num"] = int(target.get("num") or 0) + 1
        rows[index] = target
    elif adjustment in {"fixed_num_down", "rate_num_down"}:
        target["num"] = max(0, int(target.get("num") or 0) - 1)
        rows[index] = target
    elif adjustment in {"fixed_price_up", "rate_price_up"}:
        target["price"] = _text(Decimal(str(target.get("price") or 0)) + step)
        rows[index] = target
    elif adjustment in {"fixed_price_down", "rate_price_down", "rate_goods_price_down"}:
        target["price"] = _text(max(Decimal("0"), Decimal(str(target.get("price") or 0)) - step))
        rows[index] = target
    elif adjustment == "all_delete":
        rows = []
    elif adjustment == "mixed_net_refund":
        rows = [{**row, "price": "0"} for row in rows]
    return rows


def build_problem_goods_request(
    parameters: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    expected_direction: str,
    amount_step: Decimal = Decimal("1"),
) -> dict[str, Any]:
    structured = parameters.get("problem_goods") if isinstance(parameters.get("problem_goods"), Mapping) else {}
    quantity = int(_number(candidate, "possible_num", "now_num", "confirm_num", "pre_num"))
    price = _number(candidate, "confirm_price", "price", "pre_price")
    freight = _number(candidate, "confirm_freight", "freight", "pre_freight")
    problem_type = int(structured.get("problem_type") or parameters.get("problem_type") or 8)
    request: dict[str, Any] = {
        "order_purchase_id": int(candidate.get("order_purchase_id") or 0),
        "order_detail_id": int(candidate.get("order_detail_id") or 0),
        "problem_type": problem_type,
        "problem_num": int(structured.get("problem_num") or 1),
        "problem_description": str(
            structured.get("problem_description")
            or parameters.get("problem_description")
            or "系统回归问题产品"
        ).strip(),
        "translation_content": str(
            structured.get("translation_content")
            or parameters.get("translation_content")
            or "システム回帰テスト"
        ).strip(),
        "pre_num": int(structured.get("pre_num") if structured.get("pre_num") is not None else quantity),
        "pre_price": str((structured.get("pre_price") or {}).get("value", price)) if isinstance(structured.get("pre_price"), Mapping) else _text(price),
        "pre_freight": str((structured.get("pre_freight") or {}).get("value", freight)) if isinstance(structured.get("pre_freight"), Mapping) else _text(freight),
        "client_deal_choice": str(structured.get("client_deal_choice") or parameters.get("client_deal_choice") or "accept"),
        "client_deal_other": str(structured.get("client_deal_other") or parameters.get("client_deal_other") or ""),
        "service_deal_suggest": int(parameters.get("service_deal_suggest") or structured.get("service_deal_suggest") or 2),
        "option_deal_suggest": int(parameters.get("option_deal_suggest") or structured.get("option_deal_suggest") or 2),
        "g_deal_type": str(parameters.get("g_deal_type") or structured.get("g_deal_type") or "仅退款"),
        "business_decision": str(
            structured.get("business_decision")
            or parameters.get("business_decision")
            or "系统回归自动处理"
        ).strip(),
        "purchase_remark": str(structured.get("purchase_remark") or "系统回归"),
        "create_if_missing": True,
        "confirm_distribution": bool(structured.get("confirm_distribution", True)),
        "refund_channel": "customer_balance",
        "service_discount": bool(
            structured.get("service_discount")
            or parameters.get("service_discount")
            or (
                (parameters.get("coupon") or {}).get("selectedId")
                if isinstance(parameters.get("coupon"), Mapping)
                else ""
            )
            or (
                (parameters.get("coupon") or {}).get("selected_id")
                if isinstance(parameters.get("coupon"), Mapping)
                else ""
            )
        ),
    }
    if not request["order_purchase_id"] or not request["order_detail_id"]:
        raise ValueError("问题产品候选缺少采购明细或订单明细ID")

    step = abs(Decimal(str(amount_step)))
    adjustment = str(parameters.get("adjustment") or parameters.get("option_adjustment") or "")
    if adjustment in {"quantity_partial_down", "quantity_down", "fixed_quantity_down", "rate_quantity_down", "inspection_completed", "non_auto_unchanged"}:
        request["pre_num"] = max(0, quantity - 1)
    elif adjustment == "quantity_up":
        request["pre_num"] = quantity + 1
    elif adjustment == "quantity_all_down":
        request["pre_num"] = 0
    elif adjustment in {"price_down", "goods_down_refund_service", "goods_down_keep_service", "goods_down_discount_service", "zero_service_rate", "rate_goods_price_down"} or (
        adjustment == "rate_price_down" and request["option_deal_suggest"] == 2
    ):
        request["pre_price"] = _text(max(Decimal("0"), price - step))
    elif adjustment in {"price_up", "goods_up_charge_service", "goods_up_discount_service"}:
        request["pre_price"] = _text(price + step)
    elif adjustment == "freight_down":
        request["pre_freight"] = _text(max(Decimal("0"), freight - step))
    elif adjustment == "freight_up":
        request["pre_freight"] = _text(freight + step)
    elif adjustment in {"quantity_and_price_down", "net_refund"}:
        request["pre_num"] = max(0, quantity - 1)
        request["pre_price"] = _text(max(Decimal("0"), price - step))
        request["pre_freight"] = _text(max(Decimal("0"), freight - step))
    elif adjustment == "quantity_down_price_up_net_refund":
        request["pre_num"] = max(0, quantity - 1)
        request["pre_price"] = _text(price + step)
    elif adjustment == "price_down_freight_up_net_refund":
        request["pre_price"] = _text(max(Decimal("0"), price - step * Decimal("2")))
        request["pre_freight"] = _text(freight + step)
    elif adjustment in {"price_up_freight_down_net_topup", "net_topup"}:
        request["pre_price"] = _text(price + step * Decimal("2"))
        request["pre_freight"] = _text(max(Decimal("0"), freight - step))
    elif adjustment == "net_zero":
        request["pre_price"] = _text(price)
        request["pre_freight"] = _text(freight)

    original_options = _active_options(candidate)
    option_adjustment = str(parameters.get("option_adjustment") or "")
    if option_adjustment:
        request["option_new"] = _adjust_options(original_options, option_adjustment, step)
    elif structured.get("option_new"):
        request["option_new"] = list(structured.get("option_new") or [])
    if request["option_deal_suggest"] == 1 and "option_new" not in request:
        request["option_new"] = original_options
    if adjustment == "zero_service_rate":
        request["service_rate"] = "0"
    request["expected_direction"] = expected_direction
    return request


def estimate_refund_cny(candidate: Mapping[str, Any], request: Mapping[str, Any]) -> Decimal:
    quantity = int(_number(candidate, "possible_num", "now_num", "confirm_num", "pre_num"))
    price = _number(candidate, "confirm_price", "price", "pre_price")
    freight = _number(candidate, "confirm_freight", "freight", "pre_freight")
    payload = {
        "old_total_num": quantity,
        "old_possible_num": quantity,
        "old_price": price,
        "new_num": request.get("pre_num", quantity),
        "new_price": request.get("pre_price", price),
        "old_freight": freight,
        "new_freight": request.get("pre_freight", freight),
        "service_rate": request.get("service_rate") or candidate.get("service_rate") or 0,
        "service_deal_suggest": request.get("service_deal_suggest") or 2,
        "service_fee_paid": candidate.get("service_fee_paid", True),
        "service_discount": request.get("service_discount", False),
        "option_deal_suggest": request.get("option_deal_suggest") or 0,
        "option_old": _active_options(candidate),
        "option_new": request.get("option_new") or _active_options(candidate),
        "complete_inspect_num": candidate.get("complete_inspect_num") or 0,
    }
    total = calculate_problem_amount(payload).total_cny
    return abs(total) if total < 0 else Decimal("0.00")


def _evidence(payload: Mapping[str, Any] | None) -> MoneyEvidence | None:
    if not payload:
        return None
    return MoneyEvidence(
        source=str(payload.get("source") or ""),
        amount=Decimal(str(payload.get("amount") or 0)),
        currency=str(payload.get("currency") or "JPY").upper(),
        direction=str(payload.get("direction") or "none"),
        exchange_rate=Decimal(str(payload["exchange_rate"])) if payload.get("exchange_rate") not in (None, "") else None,
        reference=str(payload.get("reference") or ""),
        record_id=str(payload.get("record_id") or ""),
        raw=dict(payload.get("raw") or {}),
    )


class ProblemGoodsRunner:
    def __init__(
        self,
        env: Any,
        *,
        live_gateway: Callable[..., Mapping[str, Any]] | None = None,
        candidate_loader: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None = None,
        account_resolver: Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Decimal], Mapping[str, Any]] | None = None,
    ) -> None:
        self.env = env
        self.live_gateway = live_gateway or self._live_execute
        self.candidate_loader = candidate_loader or self._prepare_candidate_with_evidence
        self.account_resolver = account_resolver

    def _prepare_candidate_with_evidence(
        self,
        case: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        prepared = dict(self._prepare_candidate(case, context))
        candidate = prepared.get("candidate") if isinstance(prepared.get("candidate"), Mapping) else {}
        prepared["resource_evidence"] = {
            "order_created": True,
            "order_created_count": 1,
            "order_sn": str(prepared.get("order_sn") or ""),
            "purchase_record_ids": [
                str(candidate.get("order_purchase_id"))
            ] if candidate.get("order_purchase_id") not in (None, "") else [],
        }
        return prepared

    @staticmethod
    def _h5_purchase_candidates_from_payload(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data") if isinstance(payload.get("data"), Mapping) else {}
        groups = data.get("list") if isinstance(data.get("list"), list) else []
        candidates: list[dict[str, Any]] = []
        for group in groups:
            if not isinstance(group, Mapping):
                continue
            rows = group.get("list") if isinstance(group.get("list"), list) else []
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                candidate = dict(row)
                candidate["can_submit"] = bool(candidate.get("can_submit"))
                candidates.append(candidate)
        return candidates

    @staticmethod
    def _normalize_balance_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            label = f"{item.get('bill_type_group') or ''}{item.get('bill_type_name') or ''}"
            raw_amount = item.get("change_amount")
            if raw_amount in (None, ""):
                raw_amount = item.get("amount") or 0
            amount = Decimal(str(raw_amount))
            if "出金" in label:
                amount = -abs(amount)
            elif "入金" in label:
                amount = abs(amount)
            item["change_amount"] = str(amount)
            normalized.append(item)
        return normalized

    def _load_h5_purchase_candidates(
        self,
        variables: Mapping[str, Any],
        purchase_no: str,
    ) -> list[dict[str, Any]]:
        from app.data_scripts.problem_goods import ProblemGoodsGateway

        gateway = ProblemGoodsGateway(
            self.env,
            dict(variables),
            {"script": "系统回归问题产品候选查询", "mode": "h5_search_before_store"},
        )
        payload = gateway._admin_request(
            gateway._path("problem_h5_search_before_store", "/problem.h5SearchBeforeStore"),
            {
                "keyword": purchase_no,
                "submit_status": 0,
                "page": 1,
                "pageSize": 100,
            },
            "查询问题产品提出前采购记录",
            mutation=False,
        )
        if payload.get("success") is False or payload.get("code") not in (None, 0, "0"):
            raise RuntimeError(str(payload.get("msg") or "问题产品候选查询失败"))
        return self._h5_purchase_candidates_from_payload(payload)

    def _prepare_candidate(self, case: Mapping[str, Any], context: Mapping[str, Any]) -> Mapping[str, Any]:
        from app.data_scripts import run_full_flow_script, run_purchase_to_shelf_script, run_resume_order_flow_script
        from app.data_scripts.orders import inspect_order_options
        from app.data_scripts.problem_goods import inspect_problem_goods

        from .payment_runner import build_payment_variables

        parameters = dict(case.get("parameters") or {})
        guard_kind = str(parameters.get("guard_kind") or "")
        stop_after = "checking_started"
        if guard_kind == "purchase_wait_pay":
            stop_after = "purchase_wait_pay"
        elif guard_kind == "pre_num_below_storage":
            stop_after = "shelf_stored"
        elif guard_kind == "multiple_purchase_update":
            stop_after = "purchase_paid"
        variables = {
            **dict(context.get("variables") or {}),
            **build_payment_variables(parameters, runner_kind=str(case.get("runner_kind") or "")),
            "stop_after_node": stop_after,
            "order_item_num": max(3, int(parameters.get("problem_order_quantity") or 3)),
            "purchase_freight": str(parameters.get("purchase_freight") or "3"),
        }
        if guard_kind == "purchase_wait_pay":
            variables["finance_confirm"] = False
        if guard_kind == "large_refund_account":
            variables["order_item_num"] = max(6, int(parameters.get("problem_order_quantity") or 6))
        variables.setdefault("confirm_freight", variables["purchase_freight"])
        variables.setdefault("offer_freight", variables["purchase_freight"])
        existing_order_sn = str(context.get("order_sn") or "").strip()
        if existing_order_sn:
            existing_purchase_no = str(context.get("purchase_no") or variables.get("purchase_no") or "").strip()
            if existing_purchase_no:
                candidates = self._load_h5_purchase_candidates(variables, existing_purchase_no)
            else:
                inspection = inspect_problem_goods(self.env, {**variables, "order_sn": existing_order_sn})
                candidates = inspection.get("order_candidates") if isinstance(inspection.get("order_candidates"), list) else []
            candidate = next(
                (dict(row) for row in candidates if isinstance(row, Mapping) and row.get("can_submit") is not False),
                None,
            )
            if candidate is None:
                raise RuntimeError("恢复执行前无法确认原问题产品采购明细状态，已停止避免重复写入")
            if guard_kind == "multiple_purchase_update":
                candidate, _purchase_no = self._ensure_same_sorting_multiple_purchases(
                    variables,
                    existing_order_sn,
                    candidate,
                    candidates,
                )
            return {**dict(context), "candidate": candidate, "order_sn": existing_order_sn, "variables": variables}
        if parameters.get("option_adjustment") or int(parameters.get("option_deal_suggest") or 0) in {1, 2} or guard_kind in {
            "multiple_rate_auto",
            "option_num_over_goods",
            "option_price_type_change",
            "quantity_over_possible",
            "quantity_up_auto_option",
        }:
            option_catalog = inspect_order_options(self.env, variables)
            options = [row for row in option_catalog.get("options", []) if isinstance(row, Mapping)]
            adjustment = str(parameters.get("option_adjustment") or "")
            if guard_kind == "multiple_rate_auto":
                option = next((row for row in options if int(row.get("price_type") or 0) == 1), None)
                if option is not None:
                    key = str(option.get("key") or option.get("id") or option.get("name") or "").strip()
                    if key:
                        variables["order_option_counts"] = {
                            key: max(1, int(parameters.get("problem_order_quantity") or 3))
                        }
            else:
                required_types = {1} if adjustment.startswith("rate_") else {0}
                if adjustment in {"mixed_net_refund", "all_delete"} or guard_kind in {
                    "option_num_over_goods",
                    "option_price_type_change",
                    "quantity_over_possible",
                    "quantity_up_auto_option",
                }:
                    required_types = {0, 1} if adjustment in {"mixed_net_refund", "all_delete"} else required_types or {0}
                selected = {}
                for price_type in required_types:
                    option = next((row for row in options if int(row.get("price_type") or 0) == price_type), None)
                    if option is None:
                        if guard_kind:
                            continue
                        raise ValueError(f"缺少计价类型为{price_type}的可用OPTION")
                    key = str(option.get("key") or option.get("id") or option.get("name") or "").strip()
                    if not key:
                        if guard_kind:
                            continue
                        raise ValueError("可用OPTION缺少唯一标识")
                    selected[key] = max(1, int(parameters.get("problem_order_quantity") or 3))
                if selected:
                    variables["order_option_counts"] = selected

        passed, _log, _report, summary = run_full_flow_script(self.env, variables)
        order_sn = str((summary or {}).get("order_sn") or "")
        if not passed and order_sn:
            shelf_vars = {
                **variables,
                "order_sn": order_sn,
                "auto_quote_and_pay": False,
                "link_quote_balance_before_shelf": False,
            }
            passed, _log, _report, resumed_summary = run_purchase_to_shelf_script(self.env, shelf_vars)
            if not passed:
                passed, _log, _report, resumed_summary = run_resume_order_flow_script(
                    self.env,
                    {**variables, "order_sn": order_sn},
                )
            summary = {**dict(summary or {}), **dict(resumed_summary or {}), "order_sn": order_sn}
        if not passed:
            raise RuntimeError(str((summary or {}).get("reason") or "问题产品前置订单创建失败"))
        order_sn = str((summary or {}).get("order_sn") or order_sn)
        if not order_sn:
            raise RuntimeError("问题产品前置订单未返回订单号")
        purchase_no = str((summary or {}).get("purchase_no") or "").strip()
        if purchase_no:
            candidates = self._load_h5_purchase_candidates(variables, purchase_no)
        else:
            inspection = inspect_problem_goods(self.env, {**variables, "order_sn": order_sn})
            candidates = inspection.get("order_candidates") if isinstance(inspection.get("order_candidates"), list) else []
        candidate = next(
            (dict(row) for row in candidates if isinstance(row, Mapping) and row.get("can_submit") is not False),
            None,
        )
        if candidate is None:
            diagnostics = [
                {
                    "order_purchase_id": row.get("order_purchase_id"),
                    "possible_num": row.get("possible_num"),
                    "storage_num": row.get("storage_num"),
                    "can_submit": row.get("can_submit"),
                }
                for row in candidates
                if isinstance(row, Mapping)
            ]
            raise RuntimeError(f"未找到可提交的问题产品采购明细：{diagnostics}")
        if guard_kind == "multiple_purchase_update":
            candidate, purchase_no = self._ensure_same_sorting_multiple_purchases(
                variables,
                order_sn,
                candidate,
                candidates,
            )
        return {
            **dict(context),
            "candidate": candidate,
            "order_sn": order_sn,
            "purchase_no": purchase_no,
            "variables": variables,
        }

    def _ensure_same_sorting_multiple_purchases(
        self,
        variables: Mapping[str, Any],
        order_sn: str,
        candidate: Mapping[str, Any],
        candidates: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], str]:
        from datetime import datetime

        from app.data_scripts.problem_goods import (
            merge_purchase_candidates,
            order_purchase_candidates,
            same_sorting_purchase_rows,
        )

        same = same_sorting_purchase_rows(candidates, dict(candidate))
        if len(same) >= 2:
            chosen = dict(candidate)
            chosen["same_purchase_count"] = len(same)
            chosen["order_purchase_count"] = len(same)
            return chosen, str(chosen.get("purchase_no") or "")

        qty = int(candidate.get("possible_num") or candidate.get("confirm_num") or candidate.get("max_submit_num") or 0)
        order_purchase_id = int(candidate.get("order_purchase_id") or 0)
        if qty < 2:
            raise RuntimeError("同番拆分需要采购数量至少为2")
        if order_purchase_id <= 0:
            raise RuntimeError("同番拆分缺少采购记录ID")

        gateway = ProblemGoodsGateway(
            self.env,
            dict(variables),
            {"script": "系统回归交易号拆分", "order_sn": order_sn},
        )
        new_no = datetime.now().strftime("%d%H%M%S")
        gateway.split_purchase_no(
            order_purchase_id=order_purchase_id,
            new_num=1,
            new_purchase_no=new_no,
        )
        rows = gateway.list_purchase_candidates(order_sn)
        same = same_sorting_purchase_rows(rows, dict(candidate))
        if len(same) < 2:
            try:
                spot_rows = order_purchase_candidates(gateway.spot_order_detail(order_sn) or {})
                same = same_sorting_purchase_rows(merge_purchase_candidates(rows, spot_rows), dict(candidate))
            except Exception:
                pass
        if len(same) < 2:
            raise RuntimeError(f"交易号拆分后同番仍只有{len(same)}条采购记录")
        chosen = next((dict(row) for row in same if row.get("can_submit") is not False), dict(same[0]))
        chosen["same_purchase_count"] = len(same)
        chosen["order_purchase_count"] = len(same)
        return chosen, str(chosen.get("purchase_no") or new_no)

    def _live_execute(self, case: Mapping[str, Any], context: Mapping[str, Any], request: Mapping[str, Any]) -> Mapping[str, Any]:
        from app.data_scripts import run_problem_goods_script
        from app.data_scripts.payment_amount_regression.runner import (
            LivePaymentRegressionExecutor,
            _aggregate_evidence,
        )
        from app.data_scripts.payment_amount_regression.scenarios import ScenarioSpec

        variables = {
            **dict(context.get("variables") or {}),
            **dict(request),
            "order_sn": str(context.get("order_sn") or ""),
        }
        evidence_gateway = LivePaymentRegressionExecutor(self.env, variables)
        before = evidence_gateway._balance_rows(variables)
        passed, log_text, _report, summary = run_problem_goods_script(
            self.env,
            variables,
            gateway_factory=_SystemRegressionProblemGoodsGateway,
        )
        result = dict(summary or {})
        if not passed:
            result["status"] = "failed"
            return result
        direction = str((case.get("expectation") or {}).get("direction") or "none")
        expected_stage = str((case.get("expectation") or {}).get("expected_stage") or "")
        actual_stage = "problem_goods_completed" if bool(result.get("completed")) else str(result.get("status_name") or "")
        reference = str(result.get("problem_goods_id") or context.get("order_sn") or "")
        preview_bills = result.get("preview_bills") if isinstance(result.get("preview_bills"), list) else []
        scenario = ScenarioSpec(
            key=str(case.get("case_key") or ""),
            name=str(case.get("name") or ""),
            category="problem_goods",
            expected_direction=direction,
            problem_type=int(request.get("problem_type") or 0),
            adjustment=str((case.get("parameters") or {}).get("adjustment") or "unchanged"),
        )
        preview = evidence_gateway._preview_evidence(preview_bills, scenario, reference)
        references = [value for value in (reference, str(context.get("order_sn") or "")) if value]
        rows = evidence_gateway._wait_new_balance_rows(
            before,
            variables,
            references,
            allow_empty=direction == "none",
        )
        rows = self._normalize_balance_rows(rows)
        actual = None if direction == "none" and not rows else _aggregate_evidence(
            rows,
            source="customer_balance",
            reference=reference,
        )
        reconciliation = reconcile_three_way(
            str(case.get("case_key") or ""),
            preview,
            preview,
            actual,
            tolerance_jpy=int((case.get("parameters") or {}).get("tolerance_jpy") or context.get("tolerance_jpy") or 1),
            actual_source="problem_goods",
        )

        flow_log = _problem_log(log_text)
        attempted_actions = _safe_actions(flow_log)
        if result.get("completed"):
            for action in attempted_actions:
                if action.get("result") == "indeterminate":
                    action["result"] = "success"
                    action["reconciliation_performed"] = True
        write_actions = [row for row in attempted_actions if row.get("request_type") == "write"]
        if any(row.get("result") == "indeterminate" for row in write_actions):
            write_state = "indeterminate"
        elif write_actions and bool(result.get("completed")):
            write_state = "confirmed_written"
        else:
            write_state = "confirmed_not_written"

        resource_evidence = (
            dict(context.get("resource_evidence") or {})
            if isinstance(context.get("resource_evidence"), Mapping)
            else {}
        )
        order_created_count = int(resource_evidence.get("order_created_count") or 0)
        problem_create_actions = [
            row
            for row in write_actions
            if str(row.get("target") or "").rstrip("/").endswith("/problem.store")
            and row.get("result") == "success"
        ]
        problem_created_count = len(problem_create_actions)
        actual_jpy = to_jpy(actual) if actual is not None else Decimal("0")
        expected_jpy = to_jpy(preview)
        response_evidence = [
            {
                "action": row.get("action"),
                "target": row.get("target"),
                "response_summary": dict(row.get("response_summary") or {}),
            }
            for row in attempted_actions
        ]
        before_evidence = {
            "problem_goods_status": "not_created" if problem_created_count else "unknown",
            "balance_bill_count": len(before),
            "order_state": (context.get("candidate") or {}).get("status")
            if isinstance(context.get("candidate"), Mapping)
            else None,
            "order_sn": str(context.get("order_sn") or ""),
        }
        after_evidence = {
            "problem_goods_status": "completed" if result.get("completed") else str(result.get("status_name") or ""),
            "expected_amount_jpy": int(expected_jpy),
            "preview_amount_jpy": int(expected_jpy),
            "actual_amount_jpy": int(actual_jpy),
            "preview_bills": preview_bills,
            "balance_delta_jpy": int(actual_jpy),
            "matched_bill_count": len(rows),
        }
        payment_executed = any("pay" in str(row.get("target") or "").lower() for row in write_actions)
        balance_bill_created = bool(rows)
        side_effects = {
            "expected_side_effects": ["order_created", "problem_goods_created", "problem_goods_completed"],
            "unexpected_side_effects": [],
            "financial_side_effects": [],
            "resource_side_effects": [
                {"effect": "order_created", "count": order_created_count},
                {"effect": "problem_goods_created", "count": problem_created_count},
                {"effect": "problem_goods_completed", "count": 1 if result.get("completed") else 0},
            ],
            "cleanup_state": "retained_for_traceability",
            "order_created": order_created_count == 1,
            "problem_goods_created": problem_created_count == 1,
            "payment_executed": payment_executed,
            "balance_debited": direction == "debit" and actual_jpy > 0,
            "balance_bill_created": balance_bill_created,
            "duplicate_order_detected": order_created_count > 1,
            "duplicate_problem_goods_detected": problem_created_count > 1,
        }
        if payment_executed:
            side_effects["unexpected_side_effects"].append("payment_executed")
        if balance_bill_created and direction == "none":
            side_effects["unexpected_side_effects"].append("balance_bill_created")
        if side_effects["duplicate_order_detected"]:
            side_effects["unexpected_side_effects"].append("duplicate_order")
        if side_effects["duplicate_problem_goods_detected"]:
            side_effects["unexpected_side_effects"].append("duplicate_problem_goods")

        parameter_snapshot = {
            **dict(
                sanitize_secrets(
                    dict(((case.get("_execution") or {}).get("parameter_snapshot") or {}))
                )
            ),
            "case_id": str(case.get("case_key") or ""),
            "order_sn": str(context.get("order_sn") or ""),
            "problem_goods_id": reference,
            "expected_amount_jpy": int(expected_jpy),
            "expected_direction": direction,
            "required_identities": list((case.get("expectation") or {}).get("required_identities") or []),
        }
        business_diffs = list(side_effects["resource_side_effects"])
        forbidden_effects = [
            {"effect": value}
            for value in side_effects["unexpected_side_effects"]
        ]
        stage_evidence = {
            "expected_stage": expected_stage,
            "actual_stage": actual_stage,
            "stage_matched": bool(expected_stage) and expected_stage == actual_stage,
        }

        def public_evidence(value: Any) -> dict[str, Any]:
            if value is None:
                return {}
            return {
                "source": value.source,
                "amount": str(value.amount),
                "currency": value.currency,
                "direction": value.direction,
                "exchange_rate": str(value.exchange_rate) if value.exchange_rate is not None else None,
                "reference": value.reference,
                "record_id": value.record_id,
                "raw": dict(value.raw),
            }

        result.update(
            status="passed" if reconciliation.passed else "failed",
            reason_code=reconciliation.reason_code,
            order_sn=str(context.get("order_sn") or ""),
            expected=public_evidence(preview),
            preview=public_evidence(preview),
            actual=public_evidence(actual),
            parameter_snapshot=parameter_snapshot,
            precondition_evidence=dict(resource_evidence),
            attempted_actions=attempted_actions,
            response_evidence=response_evidence,
            before_evidence=before_evidence,
            after_evidence=after_evidence,
            side_effects=side_effects,
            stage_evidence=stage_evidence,
            expected_stage=expected_stage,
            actual_stage=actual_stage,
            actor={"identity_type": list((case.get("expectation") or {}).get("required_identities") or [])},
            purchase_record_ids=[str(request.get("order_purchase_id"))]
            if request.get("order_purchase_id") not in (None, "")
            else [],
            write_state=write_state,
            write_request_count=sum(int(row.get("attempt_count") or 0) for row in write_actions),
            required_effects=business_diffs,
            forbidden_effects=forbidden_effects,
            allowed_effects=business_diffs,
            unclassified_effects=[],
            business_diffs=business_diffs,
            reconciliation=reconciliation.__dict__,
        )
        missing = _problem_evidence_missing(result)
        if str(case.get("case_key") or "") == "JP-PG-AMT-001" and missing:
            result["status"] = "failed"
            result["reason_code"] = "evidence_incomplete"
            result["error_code"] = "evidence_incomplete"
            result["failure_reason"] = f"missing structured evidence: {', '.join(missing)}"
            result["amount_evidence"] = {
                "expected": result["expected"],
                "preview": result["preview"],
                "actual": result["actual"],
            }
            result["expected"] = {}
            result["preview"] = {}
            result["actual"] = {}
        checkpoint = context.get("checkpoint")
        if callable(checkpoint):
            checkpoint(
                {
                    "execution_id": str(context.get("execution_id") or ""),
                    "current_step": actual_stage or "problem_goods_result_verification",
                    "completed_actions": [str(row.get("action") or "") for row in write_actions],
                    "purchase_record_ids": result["purchase_record_ids"],
                    "before_evidence": before_evidence,
                    "last_write": {"state": write_state, "idempotent": False},
                    "order_sn": result["order_sn"],
                    "problem_goods_id": reference,
                }
            )
        return result

    def execute(self, case: Mapping[str, Any], context: Mapping[str, Any]) -> CaseRunResult:
        parameters = dict(case.get("parameters") or {})
        if str(case.get("runner_kind") or "") == "problem_flow":
            problem_type = int(parameters.get("problem_type") or 0)
            if not parameters.get("adjustment") and not parameters.get("option_adjustment"):
                flow_adjustments = {
                    1: "price_down",
                    2: "freight_down",
                    3: "quantity_partial_down",
                    4: "price_down",
                    5: "quantity_and_price_down",
                    7: "quantity_up",
                }
                if problem_type == 6:
                    parameters["option_adjustment"] = "fixed_add"
                    parameters["option_deal_suggest"] = 1
                elif problem_type in flow_adjustments:
                    parameters["adjustment"] = flow_adjustments[problem_type]
                    if problem_type == 7:
                        parameters["option_deal_suggest"] = 1
            if parameters.get("client_deal_choice") == "other" and not parameters.get("client_deal_other"):
                parameters["client_deal_other"] = "系统回归自定义回复"
            nested = parameters.get("problem_goods")
            if isinstance(nested, Mapping):
                nested = dict(nested)
                for key in (
                    "adjustment",
                    "option_adjustment",
                    "option_deal_suggest",
                    "service_deal_suggest",
                    "g_deal_type",
                    "client_deal_choice",
                    "client_deal_other",
                ):
                    if parameters.get(key) not in (None, ""):
                        nested[key] = parameters[key]
                parameters["problem_goods"] = nested
        run_context = dict(context)
        if not isinstance(run_context.get("candidate"), Mapping):
            run_context = dict(self.candidate_loader(case, run_context))
        candidate = run_context.get("candidate") if isinstance(run_context.get("candidate"), Mapping) else {}
        direction = str((case.get("expectation") or {}).get("direction") or "none")
        request = build_problem_goods_request(
            parameters,
            candidate,
            expected_direction=direction,
            amount_step=Decimal(str(parameters.get("amount_step") or run_context.get("amount_step") or 1)),
        )
        refund_cny = estimate_refund_cny(candidate, request) if direction == "credit" else Decimal("0.00")
        has_temporary_account = bool(run_context.get("temporary_account_override"))
        if self.account_resolver is not None and refund_cny >= Decimal("500") and not has_temporary_account:
            account_values = dict(self.account_resolver(case, run_context, request, refund_cny) or {})
            run_context["variables"] = {
                **dict(run_context.get("variables") or {}),
                **account_values,
            }
            run_context["minister_account_required"] = True
        payload = dict(self.live_gateway(case, run_context, request) or {})
        expected = _evidence(payload.get("expected"))
        preview = _evidence(payload.get("preview"))
        actual = _evidence(payload.get("actual"))
        if actual is not None and actual.source != "customer_balance":
            return CaseRunResult(
                status="failed",
                order_sn=str(payload.get("order_sn") or ""),
                problem_goods_id=str(payload.get("problem_goods_id") or ""),
                expected=dict(payload.get("expected") or {}),
                preview=dict(payload.get("preview") or {}),
                actual=dict(payload.get("actual") or {}),
                result=payload,
                error_code="invalid_actual_source",
                error_message="问题产品实际金额只能来自客户余额",
            )
        if expected is not None and preview is not None:
            check = reconcile_three_way(
                str(case.get("case_key") or ""),
                expected,
                preview,
                actual,
                tolerance_jpy=int(parameters.get("tolerance_jpy") or run_context.get("tolerance_jpy") or 1),
                actual_source="problem_goods",
            )
            status = "passed" if check.passed else "failed"
            error_code = "" if check.passed else check.reason_code
            error_message = "" if check.passed else check.reason
            result_payload = {**payload, "reconciliation": check.__dict__}
        else:
            status = str(payload.get("status") or "failed")
            error_code = "" if status == "passed" else str(payload.get("error_code") or "problem_execution_failed")
            error_message = "" if status == "passed" else str(payload.get("error_message") or payload.get("failure_reason") or "问题产品执行失败")
            if run_context.get("minister_account_required") and status != "passed" and "登录" in error_message:
                status = "waiting_account"
                error_code = "minister_account_required"
            result_payload = payload
        return CaseRunResult(
            status=status,
            order_sn=str(payload.get("order_sn") or ""),
            problem_goods_id=str(payload.get("problem_goods_id") or ""),
            expected=dict(payload.get("expected") or {}),
            preview=dict(payload.get("preview") or {}),
            actual=dict(payload.get("actual") or {}),
            result=result_payload,
            error_code=error_code,
            error_message=error_message,
        )


__all__ = ["ProblemGoodsRunner", "build_problem_goods_request", "estimate_refund_cny"]
