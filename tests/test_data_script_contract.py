import inspect

import app.data_scripts as data_scripts


EXPECTED_RUN_SCRIPT_ENTRIES = {
    "run_balance_payment_script",
    "run_balance_recharge_script",
    "run_bank_payment_script",
    "run_direct_box_to_shelf_script",
    "run_full_flow_script",
    "run_material_generation_script",
    "run_material_order_script",
    "run_oem_bulk_order_script",
    "run_oem_full_inquiry_flow_script",
    "run_oem_new_inquiry_script",
    "run_oem_sample_admin_flow_script",
    "run_oem_sample_balance_pay_script",
    "run_oem_sample_full_flow_script",
    "run_oem_sample_order_script",
    "run_order_quote_script",
    "run_porder_balance_payment_script",
    "run_porder_bank_payment_script",
    "run_problem_goods_script",
    "run_purchase_to_shelf_script",
    "run_resume_order_flow_script",
    "run_resume_porder_flow_script",
    "run_shopping_cart_script",
    "run_warehouse_delivery_script",
}

EXPECTED_REGISTRY_KEYS = {
    "shopping_cart",
    "order_quote",
    "balance_payment",
    "bank_payment",
    "purchase_to_shelf",
    "purchase_to_shelf_chain",
    "warehouse_delivery",
    "porder_balance_payment",
    "porder_bank_payment",
    "problem_goods",
    "full_flow",
    "direct_box_to_shelf",
    "resume_order_flow",
    "resume_porder_flow",
    "material_order",
    "material_generation",
    "balance_recharge",
    "oem_new_inquiry",
    "oem_sample_order",
    "oem_sample_admin_flow",
    "oem_full_inquiry_flow",
    "oem_sample_full_flow",
    "oem_bulk_order",
    "oem_balance_pay",
}


def test_data_script_public_entry_contract():
    current = {
        name
        for name, value in vars(data_scripts).items()
        if name.startswith("run_") and name.endswith("_script") and callable(value)
    }
    assert current == EXPECTED_RUN_SCRIPT_ENTRIES
    for name in sorted(current):
        parameters = list(inspect.signature(getattr(data_scripts, name)).parameters)
        assert parameters[:2] == ["env", "variables"]


def test_data_script_registry_contract():
    registry = data_scripts.SCRIPT_REGISTRY
    assert set(registry) == EXPECTED_REGISTRY_KEYS
    assert all(callable(item.get("func")) for item in registry.values())
    assert registry["purchase_to_shelf_chain"]["func"] is data_scripts.run_purchase_to_shelf_chain
    for key in EXPECTED_RUN_SCRIPT_ENTRIES:
        script_key = key.removeprefix("run_").removesuffix("_script")
        if script_key == "oem_sample_balance_pay":
            script_key = "oem_balance_pay"
        assert registry[script_key]["func"] is getattr(data_scripts, key)
