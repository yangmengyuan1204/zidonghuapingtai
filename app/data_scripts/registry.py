from typing import Any, Callable, Dict


SCRIPT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "payment_amount_regression": {"name": "支付金额自动回归", "func": None, "chain": True},
    "shopping_cart": {"name": "商品购物车", "func": None},
    "order_quote": {"name": "订单报价", "func": None},
    "balance_payment": {"name": "余额支付", "func": None},
    "balance_adjustment": {"name": "余额调整", "func": None},
    "bank_payment": {"name": "银行支付", "func": None},
    "purchase_to_shelf": {"name": "待拍下到商品上架", "func": None},
    "purchase_to_shelf_chain": {"name": "待拍下到商品上架(组合脚本)", "func": None, "chain": True},
    "warehouse_delivery": {"name": "仓库提出配送单", "func": None},
    "porder_balance_payment": {"name": "配送单余额付款", "func": None},
    "porder_bank_payment": {"name": "配送单银行付款", "func": None},
    "full_flow": {"name": "全流程完全体", "func": None, "chain": True},
    "direct_box_to_shelf": {"name": "直接装箱上架", "func": None, "chain": True},
    "resume_order_flow": {"name": "输入订单号继续执行操作", "func": None, "chain": True},
    "resume_porder_flow": {"name": "输入配送单号继续执行操作", "func": None, "chain": True},
    "rollback_flow": {"name": "日本站业务状态回退", "func": None, "chain": True},
    "material_order": {"name": "辅料单", "func": None},
    "material_generation": {"name": "辅料生成", "func": None},
    "balance_recharge": {"name": "余额充值", "func": None},
    "problem_goods": {"name": "日本站问题产品处理", "func": None},
        "porder_shipment": {"name": "配送单出货", "func": None},
"oem_new_inquiry": {"name": "OEM创建询价单", "func": None},
    "oem_sample_order": {"name": "OEM提出样品单", "func": None},
    "oem_sample_admin_flow": {"name": "OEM样品单后台流程", "func": None},
    "oem_full_inquiry_flow": {"name": "OEM询价单全流程", "func": None},
    "oem_sample_full_flow": {"name": "OEM样品单全流程", "func": None, "chain": True},
    "oem_bulk_order": {"name": "OEM大货单下单", "func": None},
    "oem_balance_pay": {"name": "OEM样品单余额支付", "func": None},
}


def register_script(key: str, runner: Callable[..., Any]) -> None:
    if key not in SCRIPT_REGISTRY:
        raise KeyError(f"Unknown data script key: {key}")
    SCRIPT_REGISTRY[key]["func"] = runner


def registered_script_keys() -> list[str]:
    return [key for key, item in SCRIPT_REGISTRY.items() if callable(item.get("func"))]
