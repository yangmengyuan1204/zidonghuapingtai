from __future__ import annotations

from decimal import Decimal

from app.services.system_regression.account_service import AccountLoginRequired
from app.system_regression.projects.japan.guard_executor import GuardExecutor, LiveGuardDriver
from app.system_regression.projects.japan.guard_scenarios import guard_scenario
from app.system_regression.projects.japan.guard_runner import GuardRunner


def _case():
    return {
        "id": 13,
        "case_key": "拦截-013",
        "name": "大额退款切换部长账号",
        "runner_kind": "problem_guard",
        "parameters": {"guard_kind": "large_refund_account"},
        "expectation": {"outcome": "guard", "direction": "credit"},
    }


def _prepared():
    return {
        "order_sn": "O-500",
        "problem_goods_id": "P-500",
        "purchase_record_ids": ["R-500"],
        "precondition_evidence": {"preview_refund_cny": "500.00"},
        "before_evidence": {"problem_status": 4, "balance_row_ids": [1]},
        "action_fields": {"problem_goods_id": "P-500"},
        "actor": {"role": "normal", "username": "admin"},
    }


def test_large_refund_waits_only_after_normal_actor_is_rejected_without_effects():
    response = {
        "actual_stage": "purchase_deal",
        "composite_state": "waiting_account",
        "normal_step": {
            "business_code": "MINISTER_ACCOUNT_REQUIRED",
            "error_message": "退款金额大于500人民币需要部长账号",
            "business_diffs": [],
        },
        "business_diffs": [],
        "after_evidence": {"problem_status": 4, "balance_row_ids": [1]},
    }
    executor = GuardExecutor(lambda *_args: _prepared(), lambda *_args: response)

    result = GuardRunner(executor.execute).execute(_case(), {"execution_id": "E-500"})

    assert result.status == "waiting_account"
    assert result.reason_code == "account_required"
    assert result.result["status"] == "waiting"
    assert result.result["execution_id"] == "E-500"
    assert result.result["problem_goods_id"] == "P-500"


def test_large_refund_fails_if_normal_actor_causes_balance_change():
    response = {
        "actual_stage": "purchase_deal",
        "composite_state": "waiting_account",
        "normal_step": {
            "business_code": "MINISTER_ACCOUNT_REQUIRED",
            "error_message": "需要部长账号",
            "business_diffs": [{"entity": "customer_balance", "field": "credit", "before": "0", "after": "500"}],
        },
        "business_diffs": [{"entity": "customer_balance", "field": "credit", "before": "0", "after": "500"}],
    }
    prepared = {
        **_prepared(),
        "forbidden_effect_rules": [{"entity": "customer_balance", "field": "credit"}],
    }
    result = GuardRunner(GuardExecutor(lambda *_args: prepared, lambda *_args: response).execute).execute(_case(), {})

    assert result.status == "failed"
    assert result.reason_code == "normal_guard_side_effect"


def test_large_refund_passes_only_after_minister_credit_is_verified():
    response = {
        "actual_stage": "purchase_deal",
        "composite_state": "completed",
        "normal_step": {
            "business_code": "MINISTER_ACCOUNT_REQUIRED",
            "error_message": "需要部长账号",
            "business_diffs": [],
        },
        "minister_step": {
            "actor": {"role": "department_leader", "username": "shenwenni"},
            "problem_goods_id": "P-500",
            "balance_credit": {"record_id": "B-1", "amount_cny": "500.00", "direction": "credit"},
        },
        "business_diffs": [{"entity": "customer_balance", "field": "credit", "before": "0", "after": "500.00"}],
    }
    prepared = {
        **_prepared(),
        "required_effect_rules": [{"entity": "customer_balance", "field": "credit"}],
    }
    result = GuardRunner(GuardExecutor(lambda *_args: prepared, lambda *_args: response).execute).execute(_case(), {})

    assert result.status == "passed"
    assert result.reason_code == "large_refund_composite_completed"
    assert result.result["required_effects"][0]["after"] == "500.00"


class _LargeRefundGateway:
    def __init__(self, _env, variables, _log):
        self.variables = dict(variables)
        self.role = "department_leader" if variables.get("backend_account") == "minister" else "normal"
        self.rows = []
        self.written = False

    def balance_changes(self, _order_sn):
        if self.role == "department_leader" and self.written:
            return [{"id": "B-500", "change_amount": "600", "order_sn": "O-500"}]
        return []

    def find_problem(self, _order_sn, problem_goods_id=0, order_purchase_id=0):
        return {
            "problem_goods_id": problem_goods_id or 500,
            "order_purchase_id": order_purchase_id or 700,
            "status": 4 if self.role == "normal" else 5,
        }


class _LargeRefundFlow:
    def __init__(self, gateway, variables, _log):
        self.gateway = gateway
        self.variables = variables

    def run(self):
        if self.gateway.role == "normal":
            return {
                "problem_goods_id": 500,
                "permission_required": True,
                "resume_stage": "purchase_deal",
                "reason": "退款金额大于500人民币需要部长账号",
                "status": 4,
            }
        self.gateway.written = True
        return {"problem_goods_id": 500, "status": 5}


class _LargeRefundRunner:
    def __init__(self, account_resolver):
        self.account_resolver = account_resolver

    @staticmethod
    def candidate_loader(_case, _context):
        return {
            "order_sn": "O-500",
            "variables": {"backend_account": "admin", "customer_id": 300001},
            "candidate": {
                "order_purchase_id": 700,
                "order_detail_id": 800,
                "possible_num": 6,
                "confirm_price": "100",
                "confirm_freight": "0",
            },
        }


def _large_live_case():
    case = _case()
    case["parameters"] = {
        "guard_kind": "large_refund_account",
        "adjustment": "quantity_all_down",
        "problem_order_quantity": 6,
        "items": [{"sorting": 1, "quantity": 6, "offer_price": {"value": "100"}}],
    }
    return case


def test_live_large_refund_checkpoint_can_resume_same_problem_after_account_wait():
    runner = _LargeRefundRunner(
        lambda *_args: (_ for _ in ()).throw(AccountLoginRequired("manual account required"))
    )
    driver = LiveGuardDriver(
        object(),
        runner,
        gateway_factory=_LargeRefundGateway,
        flow_factory=_LargeRefundFlow,
    )
    checkpoints = []
    executor = GuardExecutor(driver.prepare, driver.perform)

    first = executor.execute(
        _large_live_case(),
        {"execution_id": "E-500", "checkpoint": checkpoints.append},
    )

    assert first["status"] == "waiting"
    assert first["reason_code"] == "account_required"
    resume_payload = checkpoints[-1]["resume_payload"]
    assert resume_payload["problem_goods_id"] == "500"
    assert resume_payload["order_sn"] == "O-500"

    resumed = executor.execute(
        _large_live_case(),
        {
            "execution_id": "E-500",
            "temporary_account_override": True,
            "variables": {"backend_account": "minister", "backend_password": "secret"},
            "execution_state": {"resume_payload": resume_payload},
        },
    )

    assert resumed["status"] == "passed"
    assert resumed["problem_goods_id"] == "500"
    assert resumed["reason_code"] == "large_refund_composite_completed"
    assert resumed["required_effects"][0]["entity"] == "customer_balance"


def test_large_refund_live_driver_rejects_below_threshold_precondition():
    runner = _LargeRefundRunner(lambda *_args: {})
    driver = LiveGuardDriver(
        object(), runner, gateway_factory=_LargeRefundGateway, flow_factory=_LargeRefundFlow
    )
    case = _large_live_case()
    case["parameters"]["adjustment"] = "quantity_partial_down"

    try:
        driver.prepare(guard_scenario("large_refund_account"), case, {})
    except Exception as exc:
        assert exc.__class__.__name__ == "GuardPreconditionMissing"
        assert "500" in str(exc)
    else:
        raise AssertionError("below-threshold large refund must be blocked")


def test_large_refund_normal_prepare_does_not_skip_500_gate():
    runner = _LargeRefundRunner(lambda *_args: {"backend_account": "minister", "backend_password": "secret"})
    driver = LiveGuardDriver(
        object(), runner, gateway_factory=_LargeRefundGateway, flow_factory=_LargeRefundFlow
    )
    prepared = driver.prepare(guard_scenario("large_refund_account"), _large_live_case(), {})

    assert prepared["variables"]["allow_large_refund"] is False
    assert Decimal(str(prepared["precondition_evidence"]["estimated_refund_cny"])) >= Decimal("500")


def test_large_refund_accepts_pause_at_business_preview():
    response = {
        "actual_stage": "purchase_deal",
        "composite_state": "completed",
        "normal_step": {
            "actual_stage": "business_deal",
            "business_code": "MINISTER_ACCOUNT_REQUIRED",
            "error_message": "预计退款超过500元，请切换部长后台账号后继续",
            "business_diffs": [],
        },
        "minister_step": {
            "actor": {"role": "department_leader", "username": "shenwenni"},
            "problem_goods_id": "P-500",
            "balance_credit": {"record_id": "B-1", "amount_cny": "500.00", "direction": "credit"},
        },
        "business_diffs": [{"entity": "customer_balance", "field": "credit", "before": "0", "after": "500.00"}],
    }
    prepared = {
        **_prepared(),
        "required_effect_rules": [{"entity": "customer_balance", "field": "credit"}],
    }
    result = GuardRunner(GuardExecutor(lambda *_args: prepared, lambda *_args: response).execute).execute(_case(), {})

    assert result.status == "passed"
    assert result.reason_code == "large_refund_composite_completed"


class _FlagAwareLargeRefundFlow:
    def __init__(self, gateway, variables, _log):
        self.gateway = gateway
        self.variables = dict(variables)

    def run(self):
        if not self.variables.get("allow_large_refund"):
            return {
                "problem_goods_id": 500,
                "permission_required": True,
                "resume_stage": "business_deal",
                "reason": "预计退款超过500元，请切换部长后台账号后继续",
                "status": 3,
            }
        self.gateway.written = True
        return {"problem_goods_id": 500, "status": 5}


def test_live_large_refund_switches_to_minister_after_500_gate():
    runner = _LargeRefundRunner(lambda *_args: {"backend_account": "minister", "backend_password": "secret"})
    driver = LiveGuardDriver(
        object(),
        runner,
        gateway_factory=_LargeRefundGateway,
        flow_factory=_FlagAwareLargeRefundFlow,
    )
    result = GuardRunner(GuardExecutor(driver.prepare, driver.perform).execute).execute(
        _large_live_case(),
        {"execution_id": "E-500", "variables": {}},
    )

    assert result.status == "passed"
    assert result.reason_code == "large_refund_composite_completed"
