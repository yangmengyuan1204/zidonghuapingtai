import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.data_scripts.payment_amount_regression import runner
from app.data_scripts.payment_amount_regression.reconciliation import MoneyEvidence
from app.data_scripts.payment_amount_regression.runner import (
    ScenarioBlocked,
    LivePaymentRegressionExecutor,
    _aggregate_evidence,
    _sum_evidence_jpy,
    collect_selected_bills,
    money_evidence_from_record,
    run_payment_amount_regression_script,
)
from app.data_scripts.payment_amount_regression.scenarios import SCENARIO_CATALOG


class FakeExecutor:
    def __init__(self, outcomes=None):
        self.outcomes = outcomes or {}
        self.calls = []

    def execute(self, scenario, batch_id):
        self.calls.append((scenario.key, batch_id))
        outcome = self.outcomes.get(scenario.key)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome or {"status": "passed", "checks": [{"passed": True}]}


def patch_finish(monkeypatch):
    monkeypatch.setattr(
        runner,
        "_finish_named",
        lambda name, log, passed, summary: (passed, json.dumps(log, ensure_ascii=False, default=str), "report.json", summary),
    )


def test_runner_executes_all_twelve_scenarios(monkeypatch):
    patch_finish(monkeypatch)
    executor = FakeExecutor()

    passed, _, _, summary = run_payment_amount_regression_script(object(), {"_scenario_executor": executor})

    assert passed is True
    assert len(executor.calls) == 12
    assert summary["scenario_count"] == 12
    assert summary["passed_count"] == 12
    assert summary["failed_count"] == 0
    assert summary["blocked_count"] == 0
    assert summary["batch_id"].startswith("PAYREG-")
    assert len({batch_id for _, batch_id in executor.calls}) == 1


def test_runner_continues_after_blocked_and_failed_scenarios(monkeypatch):
    patch_finish(monkeypatch)
    executor = FakeExecutor(
        {
            "order_balance": ScenarioBlocked("没有可用商品"),
            "order_bank": RuntimeError("财务接口异常"),
        }
    )

    passed, _, _, summary = run_payment_amount_regression_script(object(), {"_scenario_executor": executor})

    assert passed is False
    assert len(executor.calls) == 12
    assert summary["blocked_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["passed_count"] == 10
    statuses = {item["key"]: item["status"] for item in summary["scenarios"]}
    assert statuses["order_balance"] == "blocked"
    assert statuses["order_bank"] == "failed"


def test_runner_marks_returned_failed_check_as_failed(monkeypatch):
    patch_finish(monkeypatch)
    executor = FakeExecutor(
        {
            "problem_price_refund": {
                "status": "passed",
                "checks": [{"passed": False, "reason": "相差2日元"}],
            }
        }
    )

    passed, _, _, summary = run_payment_amount_regression_script(object(), {"_scenario_executor": executor})

    assert passed is False
    row = next(item for item in summary["scenarios"] if item["key"] == "problem_price_refund")
    assert row["status"] == "failed"
    assert row["failure_reason"] == "相差2日元"


def test_runner_honors_explicit_scenario_checkboxes(monkeypatch):
    patch_finish(monkeypatch)
    executor = FakeExecutor()
    variables = {f"payment_regression_scenario_{item.key}": False for item in SCENARIO_CATALOG}
    variables.update(
        {
            "payment_regression_scenario_order_balance": True,
            "payment_regression_scenario_problem_zero_control": "1",
            "_scenario_executor": executor,
        }
    )

    passed, _, _, summary = run_payment_amount_regression_script(object(), variables)

    assert passed is True
    assert [key for key, _batch_id in executor.calls] == ["order_balance", "problem_zero_control"]
    assert summary["scenario_count"] == 2


def test_live_variables_remove_all_payment_amount_overrides():
    executor = LivePaymentRegressionExecutor(
        object(),
        {
            "pay_amount": "1",
            "order_tail_pay_amount": "2",
            "tail_pay_amount": "3",
            "porder_pay_amount": "4",
        },
    )

    variables = executor._variables("BATCH-1", SCENARIO_CATALOG[0])

    assert "pay_amount" not in variables
    assert "order_tail_pay_amount" not in variables
    assert "tail_pay_amount" not in variables
    assert "porder_pay_amount" not in variables


def test_live_variables_include_required_backend_freight_fields():
    executor = LivePaymentRegressionExecutor(object(), {})

    variables = executor._variables("BATCH-1", SCENARIO_CATALOG[0])

    assert variables["confirm_freight"] == "5"
    assert variables["offer_freight"] == "5"


def test_money_evidence_uses_signed_customer_ledger_amount():
    debit = money_evidence_from_record(
        {"id": 8, "amount": "-200", "order_sn": "ORDER-1"},
        source="customer_balance",
        reference="ORDER-1",
    )
    credit = money_evidence_from_record(
        {"id": 9, "change_amount": "150", "order_sn": "ORDER-1"},
        source="customer_balance",
        reference="ORDER-1",
    )

    assert debit.amount == -200
    assert debit.direction == "debit"
    assert credit.amount == 150
    assert credit.direction == "credit"


def test_order_balance_payment_uses_business_debit_direction(monkeypatch):
    executor = LivePaymentRegressionExecutor(object(), {})
    scenario = next(item for item in SCENARIO_CATALOG if item.key == "order_balance")
    scripts = type(
        "Scripts",
        (),
        {"run_balance_payment_script": object(), "run_bank_payment_script": object()},
    )()
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)
    monkeypatch.setattr(executor, "_quote_order", lambda scenario, batch_id: ("ORDER-1", {}))
    monkeypatch.setattr(executor, "_order_expected_amount", lambda variables, order_sn: "1477")
    monkeypatch.setattr(executor, "_balance_rows", lambda variables: [])
    monkeypatch.setattr(
        executor,
        "_run_script",
        lambda runner, env, variables, name: ({"order_sn": "ORDER-1"}, {}, ""),
    )
    monkeypatch.setattr(
        executor,
        "_wait_new_balance_rows",
        lambda before, variables, references: [
            {"id": 1, "amount": "1477", "order_sn": "ORDER-1"}
        ],
    )

    result = executor._execute_order(scenario, "BATCH-1")

    assert result["status"] == "passed"
    assert result["checks"][0]["actual_direction"] == "debit"


def test_porder_balance_payment_uses_business_debit_direction(monkeypatch):
    executor = LivePaymentRegressionExecutor(object(), {})
    scenario = next(item for item in SCENARIO_CATALOG if item.key == "porder_balance")
    scripts = type(
        "Scripts",
        (),
        {
            "run_full_flow_script": object(),
            "run_porder_balance_payment_script": object(),
            "run_porder_bank_payment_script": object(),
        },
    )()
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)
    monkeypatch.setattr(executor, "_variables", lambda *args, **kwargs: {})
    monkeypatch.setattr(executor, "_porder_expected_amount", lambda variables, porder_sn: "775")
    monkeypatch.setattr(executor, "_balance_rows", lambda variables: [])
    monkeypatch.setattr(
        executor,
        "_run_script",
        lambda runner, env, variables, name: (
            ({"porder_sn": "PORDER-1"}, {}, "")
            if runner is scripts.run_full_flow_script
            else ({"porder_sn": "PORDER-1"}, {}, "")
        ),
    )
    monkeypatch.setattr(
        executor,
        "_wait_new_balance_rows",
        lambda before, variables, references: [
            {"id": 2, "amount": "775", "porder_sn": "PORDER-1"}
        ],
    )

    result = executor._execute_porder(scenario, "BATCH-2")

    assert result["status"] == "passed"
    assert result["checks"][0]["actual_direction"] == "debit"


def test_collect_selected_bills_follows_nested_report_attachments(tmp_path: Path):
    log_path = tmp_path / "child-log.txt"
    log_path.write_text(
        json.dumps({"finance": {"confirm": {"selected_bill": {"id": 2, "pay_amount": "300"}}}}),
        encoding="utf-8",
    )
    result_path = tmp_path / "child-result.json"
    result_path.write_text(
        json.dumps({"attachments": [{"name": "log", "source": log_path.name}]}),
        encoding="utf-8",
    )
    payload = {
        "finance": {"unconfirm_list": {"selected_bill": {"id": 1, "pay_amount": "200"}}},
        "report_path": str(result_path),
    }

    bills = collect_selected_bills(payload)

    assert [bill["id"] for bill in bills] == [1, 2]


def test_duplicate_actual_ledger_rows_are_ambiguous():
    rows = [
        {"id": 1, "amount": "-100", "order_sn": "ORDER-1"},
        {"id": 2, "amount": "-100", "order_sn": "ORDER-1"},
    ]

    try:
        _aggregate_evidence(rows, source="customer_balance", reference="ORDER-1")
    except ScenarioBlocked as exc:
        assert "无法唯一取证" in str(exc)
    else:
        raise AssertionError("重复实际流水必须判定为歧义")


def test_problem_goods_preview_uses_net_amount_and_validates_direction():
    scenario = next(item for item in SCENARIO_CATALOG if item.key == "problem_mixed_refund")

    evidence = LivePaymentRegressionExecutor._preview_evidence(
        [{"amount": "300"}, {"amount": "-100"}],
        scenario,
        "PG-1",
    )

    assert evidence.amount == 200
    assert evidence.direction == "credit"


def test_bank_bill_must_match_requested_reference():
    log = {
        "finance": {
            "confirm": {
                "selected_bill": {
                    "id": 1,
                    "serial_number": "BANK-OTHER",
                    "pay_amount": "300",
                }
            }
        }
    }

    with pytest.raises(ScenarioBlocked, match="无法唯一匹配"):
        LivePaymentRegressionExecutor._bank_actual(log, "", "BANK-EXPECTED")


def test_part_payment_stage_matching_converts_cny_before_pairing():
    rows = [
        {"id": 1, "amount": "-20", "currency": "CNY", "exchange_rate": "15", "order_sn": "ORDER-1"},
        {"id": 2, "amount": "-10", "currency": "CNY", "exchange_rate": "15", "order_sn": "ORDER-1"},
    ]

    first, tail = LivePaymentRegressionExecutor._split_stage_actuals(
        rows,
        "150",
        "ORDER-1",
        "customer_balance",
    )

    assert first.record_id == "2"
    assert tail.record_id == "1"
    assert _sum_evidence_jpy((first, tail)) == 450


def test_tail_expected_amount_reads_flattened_response_amount_not_request():
    payload = {
        "summary": {
            "order_tail_payment": {
                "data.pay_amount": 422,
                "request": {"pay_amount": "999"},
            }
        }
    }

    assert LivePaymentRegressionExecutor._tail_expected_amount(payload) == "422"


def test_part_payment_expected_amounts_keep_first_due_and_full_quote_separate():
    pay_data = {
        "data": {
            "part_pay_amount": {
                "JPY": {
                    "pay_amount_jpy": "1055",
                    "bank_pay_amount_min": "633",
                }
            }
        }
    }

    first, total = LivePaymentRegressionExecutor._part_payment_expected_amounts(
        "633",
        pay_data,
    )

    assert first == "633"
    assert total == "1055"


def test_porder_expected_amount_preserves_cny_and_exchange_rate(monkeypatch):
    payload = {
        "code": 0,
        "data": {
            "porder_amount": {
                "pay_amount": "775.02",
                "pay_amount_jpy": "16353",
                "exchange_rate": "21.10",
            }
        },
    }

    class Client:
        def post_form(self, path, fields):
            assert path == "/client/porder.porderDetail"
            assert fields == {"porder_sn": "PORDER-1"}
            return payload

    scripts = type(
        "Scripts",
        (),
        {
            "_api_path": staticmethod(lambda variables, key, default: default),
            "_api_success": staticmethod(lambda response: response.get("code") == 0),
        },
    )()
    executor = LivePaymentRegressionExecutor(object(), {})
    monkeypatch.setattr(executor, "_client", lambda variables: Client())
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)

    evidence = executor._porder_expected_amount({}, "PORDER-1")

    assert evidence.amount == Decimal("775.02")
    assert evidence.currency == "CNY"
    assert evidence.exchange_rate == Decimal("21.10")
    assert evidence.raw["pay_amount_jpy"] == "16353"


def test_porder_bank_payment_defaults_are_bounded_but_explicit_values_win():
    executor = LivePaymentRegressionExecutor(type("Env", (), {"timeout": 25})(), {})

    defaults = executor._bounded_porder_payment_variables({})
    configured = executor._bounded_porder_payment_variables(
        {"timeout": 12, "finance_confirm_retries": 4}
    )

    assert defaults["timeout"] == 8
    assert defaults["finance_confirm_retries"] == 2
    assert defaults["finance_confirm_initial_delay"] == 1
    assert defaults["finance_confirm_delay"] == 1
    assert configured["timeout"] == 12
    assert configured["finance_confirm_retries"] == 4


def test_porder_bank_actual_infers_cny_from_porder_evidence_when_bill_omits_currency():
    log = {
        "finance": {
            "confirm": {
                "selected_bill": {
                    "id": 3232483,
                    "serial_number": "BANK-1",
                    "order_sn": "PORDER-1",
                    "pay_amount": 775,
                }
            }
        }
    }
    expected = MoneyEvidence(
        source="porder_pay_detail",
        amount=Decimal("775.02"),
        currency="CNY",
        direction="debit",
        exchange_rate=Decimal("21.10"),
        reference="PORDER-1",
    )

    actual = LivePaymentRegressionExecutor._porder_bank_actual(
        log,
        "",
        "BANK-1",
        expected,
    )

    assert actual.amount == Decimal("775")
    assert actual.currency == "CNY"
    assert actual.exchange_rate == Decimal("21.10")


def test_fastapi_exposes_payment_amount_regression_route():
    from app.main import app

    routes = {(route.path, method) for route in app.routes for method in getattr(route, "methods", set())}

    assert ("/api/data-scripts/payment-amount-regression", "POST") in routes
