import sys as _sys
import types as _types

from . import _legacy as _legacy_module


_LEGACY_EXPORT_NAMES = tuple(
    name for name in vars(_legacy_module) if not name.startswith("__")
)
_DOMAIN_ENTRY_NAMES = (
    "run_balance_adjustment_script",
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
    "inspect_order_options",
    "run_problem_goods_script",
    "run_porder_balance_payment_script",
    "run_porder_bank_payment_script",
    "run_purchase_to_shelf_chain",
    "run_purchase_to_shelf_script",
    "run_resume_order_flow_script",
    "run_resume_porder_flow_script",
    "run_shopping_cart_script",
    "run_warehouse_delivery_script",
)
for _name in _LEGACY_EXPORT_NAMES:
    globals()[_name] = getattr(_legacy_module, _name)


def _sync_legacy_overrides() -> None:
    for name in _LEGACY_EXPORT_NAMES:
        if name in globals():
            setattr(_legacy_module, name, globals()[name])


class _DataScriptsModule(_types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name in _LEGACY_EXPORT_NAMES or name in _DOMAIN_ENTRY_NAMES:
            setattr(_legacy_module, name, value)


_sys.modules[__name__].__class__ = _DataScriptsModule


from .cart import run_shopping_cart_script
from .balance_adjustment import BALANCE_ADJUSTMENT_SCRIPT_NAME, run_balance_adjustment_script
from .full_flow import run_full_flow_script, run_resume_order_flow_script, run_resume_porder_flow_script
from .materials import run_material_generation_script, run_material_order_script
from .oem import (
    run_oem_bulk_order_script,
    run_oem_full_inquiry_flow_script,
    run_oem_new_inquiry_script,
    run_oem_sample_admin_flow_script,
    run_oem_sample_balance_pay_script,
    run_oem_sample_full_flow_script,
    run_oem_sample_order_script,
)
from .order_payments import (
    run_balance_payment_script,
    run_bank_payment_script,
    run_porder_balance_payment_script,
    run_porder_bank_payment_script,
)
from .orders import inspect_order_options, run_order_quote_script
from .payments import run_balance_recharge_script
from .problem_goods import run_problem_goods_script
from .purchase import run_direct_box_to_shelf_script, run_purchase_to_shelf_chain, run_purchase_to_shelf_script
from .warehouse import run_warehouse_delivery_script


for _name in _DOMAIN_ENTRY_NAMES:
    setattr(_legacy_module, _name, globals()[_name])


register_script("shopping_cart", run_shopping_cart_script)
register_script("order_quote", run_order_quote_script)
register_script("balance_payment", run_balance_payment_script)
register_script("bank_payment", run_bank_payment_script)
register_script("purchase_to_shelf", run_purchase_to_shelf_script)
register_script("purchase_to_shelf_chain", run_purchase_to_shelf_chain)
register_script("warehouse_delivery", run_warehouse_delivery_script)
register_script("porder_balance_payment", run_porder_balance_payment_script)
register_script("porder_bank_payment", run_porder_bank_payment_script)
register_script("full_flow", run_full_flow_script)
register_script("direct_box_to_shelf", run_direct_box_to_shelf_script)
register_script("resume_order_flow", run_resume_order_flow_script)
register_script("resume_porder_flow", run_resume_porder_flow_script)
register_script("material_order", run_material_order_script)
register_script("material_generation", run_material_generation_script)
register_script("balance_recharge", run_balance_recharge_script)
register_script("balance_adjustment", run_balance_adjustment_script)
register_script("problem_goods", run_problem_goods_script)
register_script("oem_new_inquiry", run_oem_new_inquiry_script)
register_script("oem_sample_order", run_oem_sample_order_script)
register_script("oem_sample_admin_flow", run_oem_sample_admin_flow_script)
register_script("oem_full_inquiry_flow", run_oem_full_inquiry_flow_script)
register_script("oem_sample_full_flow", run_oem_sample_full_flow_script)
register_script("oem_bulk_order", run_oem_bulk_order_script)
register_script("oem_balance_pay", run_oem_sample_balance_pay_script)


del _name
