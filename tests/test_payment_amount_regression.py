import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.data_scripts.payment_amount_regression import runner
from app.data_scripts.payment_amount_regression.reconciliation import MoneyEvidence, reconcile_amount
from app.data_scripts.payment_amount_regression.runner import (
    ScenarioBlocked,
    LivePaymentRegressionExecutor,
    _aggregate_evidence,
    _ledger_coupon_discount_jpy,
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


def test_porder_voucher_is_not_sent_during_order_flow(monkeypatch):
    calls = []
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
    monkeypatch.setattr(
        executor,
        "_variables",
        lambda *args, **kwargs: {"porder_discounts_id": "V25", "discounts_id": "V25"},
    )
    monkeypatch.setattr(executor, "_porder_expected_amount", lambda variables, porder_sn: "775")
    monkeypatch.setattr(executor, "_balance_rows", lambda variables: [])

    def run_script(runner, env, variables, name):
        calls.append((runner, dict(variables)))
        return ({"porder_sn": "PORDER-1"}, {}, "")

    monkeypatch.setattr(executor, "_run_script", run_script)
    monkeypatch.setattr(
        executor,
        "_wait_new_balance_rows",
        lambda before, variables, references: [{"id": 2, "amount": "775", "porder_sn": "PORDER-1"}],
    )

    result = executor._execute_porder(scenario, "BATCH-VOUCHER")

    assert result["status"] == "passed"
    assert calls[0][0] is scripts.run_full_flow_script
    assert "discounts_id" not in calls[0][1]
    assert calls[1][0] is scripts.run_porder_balance_payment_script
    assert calls[1][1]["discounts_id"] == "V25"


def test_run_script_retries_transient_deadlock(monkeypatch):
    calls = []
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)

    def flaky_script(_env, _variables):
        calls.append(1)
        if len(calls) == 1:
            return False, "{}", "", {"reason": "SQLSTATE[40001]: Deadlock found when trying to get lock"}
        return True, "{}", "", {"order_sn": "ORDER-RETRY"}

    summary, _log, _report = LivePaymentRegressionExecutor._run_script(
        flaky_script,
        object(),
        {},
        "订单报价",
    )

    assert calls == [1, 1]
    assert summary["order_sn"] == "ORDER-RETRY"


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


def test_japan_order_quote_keeps_one_configured_item_instead_of_forcing_two(monkeypatch):
    executor = LivePaymentRegressionExecutor(object(), {"payment_regression_item_num": 1})
    scenario = next(item for item in SCENARIO_CATALOG if item.key == "order_balance")
    captured = {}
    scripts = type("Scripts", (), {"run_full_flow_script": object()})()
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)
    monkeypatch.setattr(
        executor,
        "_run_script",
        lambda runner, env, variables, name: (captured.update(variables) or {"order_sn": "ORDER-1"}, {}, ""),
    )

    executor._quote_order(scenario, "BATCH-ONE")

    assert captured["order_item_num"] == 1


def test_japan_payment_variables_map_one_item_to_order_item_count():
    from app.system_regression.projects.japan.payment_runner import build_payment_variables

    values = build_payment_variables(
        {
            "order": {"item_count": 1, "default_quantity": 1},
            "items": [{"offer_price": {"value": "10"}, "offer_freight": {"value": "3"}}],
        }
    )

    assert values["cart_item_count"] == 1
    assert values["order_item_count"] == 1


def test_japan_amount_mismatch_285_vs_1098_cannot_pass():
    result = reconcile_amount(
        "order_balance",
        MoneyEvidence("order_quote", Decimal("285"), "JPY", "debit"),
        MoneyEvidence("customer_balance", Decimal("1098"), "JPY", "debit"),
    )

    assert result["passed"] is False
    assert result["reason_code"] == "amount_mismatch"
    assert result["difference_jpy"] == "813"


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


def test_japan_order_compares_integer_jpy_quote_to_balance_change(monkeypatch):
    executor = LivePaymentRegressionExecutor(
        object(),
        {"japan_fixed_cny_to_jpy": "21.2", "compare_actual_from_balance_change": True},
    )
    scenario = next(item for item in SCENARIO_CATALOG if item.key == "order_balance")
    scripts = type(
        "Scripts",
        (),
        {
            "run_full_flow_script": object(),
            "run_balance_payment_script": object(),
            "run_bank_payment_script": object(),
        },
    )()
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)
    monkeypatch.setattr(executor, "_quote_order", lambda scenario, batch_id: ("ORDER-1", {}))
    monkeypatch.setattr(executor, "_order_expected_amount", lambda variables, order_sn: "1055")
    monkeypatch.setattr(executor, "_balance_rows", lambda variables: [])
    monkeypatch.setattr(
        executor,
        "_run_script",
        lambda runner, env, variables, name: ({"order_sn": "ORDER-1", "pay_amount": "1055"}, {}, ""),
    )
    monkeypatch.setattr(
        executor,
        "_wait_new_balance_rows",
        lambda before, variables, references, **kwargs: [
            {"id": 1, "change_amount": "-1055", "order_sn": "ORDER-1", "bill_type_group": "出金"}
        ],
    )

    result = executor._execute_order(scenario, "BATCH-JP")

    assert result["status"] == "passed"
    assert result["checks"][0]["expected_jpy"] == "1055"
    assert result["checks"][0]["actual_jpy"] == "1055"
    assert result["checks"][0]["actual_source"] == "payment_api"
    assert result["customer_balance_jpy"] == "1055"
    assert result["checks"][1]["key"] == "customer_balance"
    assert result["checks"][1]["passed"] is True


def test_japan_bank_order_keeps_finance_bill_then_checks_balance_change(monkeypatch):
    executor = LivePaymentRegressionExecutor(
        object(),
        {"japan_fixed_cny_to_jpy": "21.2", "compare_actual_from_balance_change": True},
    )
    scenario = next(item for item in SCENARIO_CATALOG if item.key == "order_bank")
    scripts = type(
        "Scripts",
        (),
        {
            "run_full_flow_script": object(),
            "run_balance_payment_script": object(),
            "run_bank_payment_script": object(),
        },
    )()
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)
    monkeypatch.setattr(executor, "_quote_order", lambda scenario, batch_id: ("ORDER-1", {}))
    monkeypatch.setattr(executor, "_order_expected_amount", lambda variables, order_sn: "1055")
    monkeypatch.setattr(executor, "_balance_rows", lambda variables: [])
    monkeypatch.setattr(
        executor,
        "_run_script",
        lambda runner, env, variables, name: ({"order_sn": "ORDER-1", "serial_number": "BANK-1"}, {}, ""),
    )
    monkeypatch.setattr(
        executor,
        "_porder_bank_actual",
        lambda log, report, reference, expected: MoneyEvidence(
            "finance_confirmed_bill",
            Decimal("1055"),
            "JPY",
            "debit",
            reference=reference,
        ),
    )
    monkeypatch.setattr(
        executor,
        "_wait_new_balance_rows",
        lambda before, variables, references, **kwargs: [
            {"id": 1, "change_amount": "-1055", "order_sn": "ORDER-1", "bill_type_group": "出金"}
        ],
    )

    result = executor._execute_order(scenario, "BATCH-JP-BANK")

    assert result["status"] == "passed"
    assert result["checks"][0]["actual_source"] == "finance_confirmed_bill"
    assert result["customer_balance_jpy"] == "1055"
    assert result["checks"][1]["key"] == "customer_balance"


def test_japan_ledger_mismatch_fails_after_payment_api_passes(monkeypatch):
    executor = LivePaymentRegressionExecutor(
        object(),
        {"japan_fixed_cny_to_jpy": "21.2", "compare_actual_from_balance_change": True},
    )
    scenario = next(item for item in SCENARIO_CATALOG if item.key == "order_balance")
    scripts = type(
        "Scripts",
        (),
        {
            "run_full_flow_script": object(),
            "run_balance_payment_script": object(),
            "run_bank_payment_script": object(),
        },
    )()
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)
    monkeypatch.setattr(executor, "_quote_order", lambda scenario, batch_id: ("ORDER-1", {}))
    monkeypatch.setattr(executor, "_order_expected_amount", lambda variables, order_sn: "10")
    monkeypatch.setattr(executor, "_balance_rows", lambda variables: [])
    monkeypatch.setattr(
        executor,
        "_run_script",
        lambda runner, env, variables, name: ({"order_sn": "ORDER-1", "pay_amount": "10"}, {}, ""),
    )
    monkeypatch.setattr(
        executor,
        "_wait_new_balance_rows",
        lambda before, variables, references, **kwargs: [
            {"id": 1, "change_amount": "-200", "order_sn": "ORDER-1", "bill_type_group": "出金"}
        ],
    )

    result = executor._execute_order(scenario, "BATCH-JP-LEDGER")

    assert result["status"] == "failed"
    assert result["checks"][0]["passed"] is True
    assert result["checks"][1]["passed"] is False
    assert result["checks"][1]["reason_code"] == "ledger_mismatch"
    assert result["customer_balance_jpy"] == "200"


def test_japan_ledger_one_jpy_difference_is_allowed(monkeypatch):
    executor = LivePaymentRegressionExecutor(
        object(),
        {"japan_fixed_cny_to_jpy": "21.2", "compare_actual_from_balance_change": True},
    )
    scenario = next(item for item in SCENARIO_CATALOG if item.key == "order_balance")
    scripts = type(
        "Scripts",
        (),
        {
            "run_full_flow_script": object(),
            "run_balance_payment_script": object(),
            "run_bank_payment_script": object(),
        },
    )()
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)
    monkeypatch.setattr(executor, "_quote_order", lambda scenario, batch_id: ("ORDER-1", {}))
    monkeypatch.setattr(executor, "_order_expected_amount", lambda variables, order_sn: "10")
    monkeypatch.setattr(executor, "_balance_rows", lambda variables: [])
    monkeypatch.setattr(
        executor,
        "_run_script",
        lambda runner, env, variables, name: ({"order_sn": "ORDER-1", "pay_amount": "10"}, {}, ""),
    )
    monkeypatch.setattr(
        executor,
        "_wait_new_balance_rows",
        lambda before, variables, references, **kwargs: [
            {"id": 1, "change_amount": "-11", "order_sn": "ORDER-1", "bill_type_group": "出金"}
        ],
    )

    result = executor._execute_order(scenario, "BATCH-JP-LEDGER-1")

    assert result["status"] == "passed"
    assert result["checks"][1]["passed"] is True
    assert result["customer_balance_jpy"] == "11"


def test_japan_ledger_ignores_credit_inflow_on_same_order(monkeypatch):
    executor = LivePaymentRegressionExecutor(
        object(),
        {"japan_fixed_cny_to_jpy": "21.2", "compare_actual_from_balance_change": True},
    )
    scenario = next(item for item in SCENARIO_CATALOG if item.key == "order_balance")
    scripts = type(
        "Scripts",
        (),
        {
            "run_full_flow_script": object(),
            "run_balance_payment_script": object(),
            "run_bank_payment_script": object(),
        },
    )()
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)
    monkeypatch.setattr(executor, "_quote_order", lambda scenario, batch_id: ("ORDER-1", {}))
    monkeypatch.setattr(executor, "_order_expected_amount", lambda variables, order_sn: "1055")
    monkeypatch.setattr(executor, "_balance_rows", lambda variables: [])
    monkeypatch.setattr(
        executor,
        "_run_script",
        lambda runner, env, variables, name: ({"order_sn": "ORDER-1", "pay_amount": "1055"}, {}, ""),
    )
    monkeypatch.setattr(
        executor,
        "_wait_new_balance_rows",
        lambda before, variables, references, **kwargs: [
            {"id": 1, "change_amount": "-1055", "order_sn": "ORDER-1", "bill_type_group": "出金"},
            {"id": 2, "change_amount": "1055", "order_sn": "ORDER-1", "bill_type_group": "入金"},
        ],
    )

    result = executor._execute_order(scenario, "BATCH-JP-DEBIT-ONLY")

    assert result["status"] == "passed"
    assert result["customer_balance_jpy"] == "1055"


def test_japan_porder_uses_fixed_rate_not_live_rate(monkeypatch):
    payload = {
        "code": 0,
        "data": {
            "porder_amount": {
                "pay_amount": "10",
                "pay_amount_jpy": "211",
                "exchange_rate": "21.10",
            }
        },
    }

    class Client:
        def post_form(self, path, fields):
            return payload

    scripts = type(
        "Scripts",
        (),
        {
            "_api_path": staticmethod(lambda variables, key, default: default),
            "_api_success": staticmethod(lambda response: response.get("code") == 0),
        },
    )()
    executor = LivePaymentRegressionExecutor(object(), {"japan_fixed_cny_to_jpy": "21.2"})
    monkeypatch.setattr(executor, "_client", lambda variables: Client())
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)

    evidence = executor._porder_expected_amount({}, "PORDER-1")

    assert evidence.exchange_rate == Decimal("21.2")
    from app.data_scripts.payment_amount_regression.reconciliation import to_jpy

    assert to_jpy(evidence.amount, evidence.currency, evidence.exchange_rate) == Decimal("212")


def test_porder_payment_actual_uses_live_expected_rate_without_fixed_override(monkeypatch):
    expected = MoneyEvidence(
        source="porder_pay_detail",
        amount=Decimal("10"),
        currency="CNY",
        direction="debit",
        exchange_rate=Decimal("21.10"),
        reference="PORDER-1",
    )
    executor = LivePaymentRegressionExecutor(
        object(),
        {"compare_actual_from_balance_change": True, "compare_ledger_after_payment": True},
    )
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
    monkeypatch.setattr(executor, "_porder_expected_amount", lambda variables, porder_sn: expected)
    monkeypatch.setattr(executor, "_balance_rows", lambda variables: [])
    monkeypatch.setattr(
        executor,
        "_run_script",
        lambda runner, env, variables, name: (
            ({"porder_sn": "PORDER-1"}, {}, "")
            if runner is scripts.run_full_flow_script
            else ({"porder_sn": "PORDER-1", "pay_amount": "10"}, {}, "")
        ),
    )
    monkeypatch.setattr(
        executor,
        "_wait_new_balance_rows",
        lambda before, variables, references, **kwargs: [
            {"id": 2, "change_amount": "-211", "porder_sn": "PORDER-1", "bill_type_group": "出金"}
        ],
    )

    result = executor._execute_porder(scenario, "BATCH-LIVE-RATE")

    assert result["status"] == "passed"
    assert Decimal(result["checks"][0]["exchange_rate"]) == Decimal("21.10")
    assert result["checks"][0]["expected_jpy"] == "211"
    assert result["checks"][0]["actual_jpy"] == "211"
    assert result["checks"][0]["actual_source"] == "payment_api"


def test_balance_rows_query_keywords_and_normalize_sign(monkeypatch):
    captured = {}

    class Client:
        def post_form(self, path, fields):
            captured["path"] = path
            captured["fields"] = dict(fields)
            return {
                "code": 0,
                "data": [{"id": 1, "amount": 212, "bill_type_group": "出金", "order_sn": "ORDER-1"}],
            }

    scripts = type(
        "Scripts",
        (),
        {
            "_api_path": staticmethod(lambda variables, key, default: default),
            "_api_success": staticmethod(lambda response: True),
        },
    )()
    executor = LivePaymentRegressionExecutor(object(), {"japan_fixed_cny_to_jpy": "21.2"})
    monkeypatch.setattr(executor, "_client", lambda variables: Client())
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)

    rows = executor._balance_rows({"order_sn": "ORDER-1"})

    assert captured["path"] == "/client/user.balanceChange"
    assert captured["fields"]["keywords"] == "ORDER-1"
    assert rows[0]["change_amount"] == "-212"


def test_client_balance_change_catalog_points_to_japan_ledger():
    from app.core.data_script_catalog import DATA_SCRIPT_API_CASES

    item = next(row for row in DATA_SCRIPT_API_CASES if row["key"] == "client_balance_change")
    assert item["url"] == "/client/user.balanceChange"


def test_fastapi_exposes_payment_amount_regression_route():
    from app.main import app

    routes = {(route.path, method) for route in app.routes for method in getattr(route, "methods", set())}

    assert ("/api/data-scripts/payment-amount-regression", "POST") in routes


def test_ledger_coupon_discount_reads_discount_use_and_adjust_detail():
    assert _ledger_coupon_discount_jpy(
        [{"discount_use": [{"discount_amount": 38, "name_chinese": "手数料無料"}]}]
    ) == Decimal("38")
    assert _ledger_coupon_discount_jpy(
        [{"adjust_detail": [["注文の総額：1098JPY", "クーポンの割引金額 ：38JPY", "割引後の総額：1060JPY"]]}]
    ) == Decimal("38")


def test_japan_ledger_subtracts_account_coupon_when_ticket_has_no_amount(monkeypatch):
    executor = LivePaymentRegressionExecutor(
        object(),
        {"japan_fixed_cny_to_jpy": "21.2", "compare_actual_from_balance_change": True},
    )
    scenario = next(item for item in SCENARIO_CATALOG if item.key == "order_balance")
    scripts = type(
        "Scripts",
        (),
        {
            "run_full_flow_script": object(),
            "run_balance_payment_script": object(),
            "run_bank_payment_script": object(),
        },
    )()
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)
    monkeypatch.setattr(
        executor,
        "_quote_order",
        lambda scenario, batch_id: ("ORDER-1", {"discounts_id": "COUPON-1"}),
    )
    monkeypatch.setattr(executor, "_order_expected_amount", lambda variables, order_sn: "1098")
    monkeypatch.setattr(executor, "_balance_rows", lambda variables: [])
    monkeypatch.setattr(
        executor,
        "_run_script",
        lambda runner, env, variables, name: ({"order_sn": "ORDER-1", "pay_amount": "1098"}, {}, ""),
    )
    monkeypatch.setattr(
        executor,
        "_wait_new_balance_rows",
        lambda before, variables, references, **kwargs: [
            {
                "id": 1,
                "change_amount": "-1060",
                "order_sn": "ORDER-1",
                "bill_type_group": "出金",
                "discount_use": [{"discount_amount": 38, "name_chinese": "手数料無料"}],
            }
        ],
    )

    result = executor._execute_order(scenario, "BATCH-JP-COUPON")

    assert result["status"] == "passed"
    assert result["checks"][0]["passed"] is True
    assert result["checks"][1]["passed"] is True
    assert result["checks"][1]["expected_jpy"] == "1060"
    assert result["customer_balance_jpy"] == "1060"


def test_japan_ledger_fails_when_account_coupon_missing_from_balance(monkeypatch):
    executor = LivePaymentRegressionExecutor(
        object(),
        {"japan_fixed_cny_to_jpy": "21.2", "compare_actual_from_balance_change": True},
    )
    scenario = next(item for item in SCENARIO_CATALOG if item.key == "order_balance")
    scripts = type(
        "Scripts",
        (),
        {
            "run_full_flow_script": object(),
            "run_balance_payment_script": object(),
            "run_bank_payment_script": object(),
        },
    )()
    monkeypatch.setattr(executor, "_scripts", lambda: scripts)
    monkeypatch.setattr(
        executor,
        "_quote_order",
        lambda scenario, batch_id: ("ORDER-1", {"discounts_id": "COUPON-1"}),
    )
    monkeypatch.setattr(executor, "_order_expected_amount", lambda variables, order_sn: "1098")
    monkeypatch.setattr(executor, "_balance_rows", lambda variables: [])
    monkeypatch.setattr(
        executor,
        "_run_script",
        lambda runner, env, variables, name: ({"order_sn": "ORDER-1", "pay_amount": "1098"}, {}, ""),
    )
    monkeypatch.setattr(
        executor,
        "_wait_new_balance_rows",
        lambda before, variables, references, **kwargs: [
            {"id": 1, "change_amount": "-1098", "order_sn": "ORDER-1", "bill_type_group": "出金"}
        ],
    )

    result = executor._execute_order(scenario, "BATCH-JP-COUPON-MISSING")

    assert result["status"] == "failed"
    assert result["checks"][1]["reason_code"] == "coupon_not_applied"
