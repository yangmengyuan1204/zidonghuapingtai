from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_payment_amount_regression_frontend_is_loaded_after_full_flow():
    index_text = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

    full_flow_index = index_text.index('/static/full-flow.js')
    regression_index = index_text.index('/static/payment-amount-regression.js')

    assert regression_index > full_flow_index


def test_payment_amount_regression_frontend_registers_card_and_endpoint():
    source = (ROOT / "static" / "payment-amount-regression.js").read_text(encoding="utf-8")

    assert 'backend_account: "Y001"' not in source
    assert 'backend_password: "raku@123456``"' not in source
    assert 'BUILTIN_FLOW_DEFINITIONS.payment_amount_regression' in source
    assert 'SCRIPT_PARAM_SCHEMAS.payment_amount_regression' in source
    assert '/api/data-scripts/payment-amount-regression' in source
    assert '创建并保留 12 张业务订单' in source
    assert source.count('payment_regression_scenario_') >= 12
    assert 'summary.failed_count' in source
    assert 'summary.blocked_count' in source
    assert 'purchase_freight: "3"' in source
