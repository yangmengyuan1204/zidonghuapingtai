from pathlib import Path


APP_JS = Path("static/app.js").read_text(encoding="utf-8")


def test_balance_adjustment_is_a_builtin_data_script() -> None:
    assert 'balance_adjustment: { id: "balance_adjustment_builtin"' in APP_JS


def test_balance_adjustment_has_runtime_parameter_fields() -> None:
    assert "balance_adjustment: [" in APP_JS
    for field_name in (
        "customer_id",
        "adjustment_type",
        "amount",
        "adjust_reason",
        "client_bill_reason",
    ):
        assert f'name: "{field_name}"' in APP_JS


def test_balance_adjustment_calls_its_data_script_endpoint() -> None:
    assert 'if (flow.scriptType === "balance_adjustment") {' in APP_JS
    assert 'api("/api/data-scripts/balance-adjustment"' in APP_JS
