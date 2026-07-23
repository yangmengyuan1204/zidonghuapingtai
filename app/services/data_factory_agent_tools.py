from __future__ import annotations

import json
import random
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict

from sqlalchemy.orm import Session

from .. import data_scripts
from ..core.account_utils import account_profile_variables
from ..core.utils import save_record
from ..data_scripts.problem_goods import inspect_problem_goods
from ..data_scripts.capabilities import capability_catalog
from ..models import Env


SENSITIVE_KEYS = {
    "access_token",
    "admin_token",
    "api_key",
    "authorization",
    "backend_password",
    "compute_token",
    "password",
    "token",
    "usertoken",
}


@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    description: str
    mutating: bool
    category: str


@dataclass
class AgentToolContext:
    db: Session
    env: Env
    project_id: int
    goal: Dict[str, Any]
    variables: Dict[str, Any]
    public_variables: Dict[str, Any]
    state: Dict[str, Any]
    progress_callback: Callable[[Dict[str, Any]], None] | None = None


TOOL_SPECS: Dict[str, AgentToolSpec] = {
    "run_full_flow": AgentToolSpec(
        "run_full_flow",
        "从新建订单开始执行日本站标准全流程，并在目标节点停止；内部包含购物车不足自动补货。",
        True,
        "组合脚本",
    ),
    "resume_order_flow": AgentToolSpec(
        "resume_order_flow",
        "查询已有订单状态并从当前节点继续，适合失败恢复或输入订单号续跑。",
        True,
        "组合脚本",
    ),
    "resume_porder_flow": AgentToolSpec(
        "resume_porder_flow",
        "查询已有配送单状态并从当前节点继续。",
        True,
        "组合脚本",
    ),
    "rollback_business_state": AgentToolSpec(
        "rollback_business_state",
        "按已确认目标逐级回退订单、配送单，或将已上架商品负数下架到核查中；每一步都先查状态并回查结果。",
        True,
        "组合脚本",
    ),
    "fill_shopping_cart": AgentToolSpec(
        "fill_shopping_cart",
        "按目标店铺数和每店商品数搜索并补充购物车；允许在目标范围内调整搜索关键词。",
        True,
        "原子动作",
    ),
    "quote_order": AgentToolSpec(
        "quote_order",
        "执行前台提单、后台翻译、采购确认和业务报价。",
        True,
        "组合脚本",
    ),
    "pay_order": AgentToolSpec(
        "pay_order",
        "按已确认的订单支付方式付款；银行方式同时执行财务确认入金。",
        True,
        "原子动作",
    ),
    "confirm_order_bank_deposit": AgentToolSpec(
        "confirm_order_bank_deposit",
        "使用已有银行流水号仅执行后台财务确认入金。",
        True,
        "原子动作",
    ),
    "advance_purchase_to_shelf": AgentToolSpec(
        "advance_purchase_to_shelf",
        "将待拍下订单推进至指定采购、核查或上架节点。",
        True,
        "组合脚本",
    ),
    "create_and_quote_porder": AgentToolSpec(
        "create_and_quote_porder",
        "从仓库商品提出配送单并完成后台装箱和业务报价。",
        True,
        "组合脚本",
    ),
    "pay_porder": AgentToolSpec(
        "pay_porder",
        "按已确认的配送单支付方式付款；银行方式同时执行财务确认。",
        True,
        "原子动作",
    ),
    "inspect_order_state": AgentToolSpec(
        "inspect_order_state",
        "只读查询订单详情、采购状态、商品行、店铺数和报价。",
        False,
        "查询接口",
    ),
    "inspect_porder_state": AgentToolSpec(
        "inspect_porder_state",
        "只读查询配送单详情、装箱和报价状态。",
        False,
        "查询接口",
    ),
    "inspect_problem_goods": AgentToolSpec(
        "inspect_problem_goods",
        "只读查询当前订单的问题产品和可提出采购记录。",
        False,
        "查询接口",
    ),
    "inspect_order_options": AgentToolSpec(
        "inspect_order_options",
        "只读查询当前环境可用于订单商品的附加选项。",
        False,
        "查询接口",
    ),
    "process_problem_goods": AgentToolSpec(
        "process_problem_goods",
        "按已确认合同提出并处理问题产品；高额退款缺少部长权限时安全暂停。",
        True,
        "组合脚本",
    ),
}

for _tool_name, _capability_key in {
    "create_and_quote_porder": "warehouse_delivery",
    "fill_shopping_cart": "shopping_cart",
    "run_full_flow": "full_flow",
    "resume_order_flow": "resume_order_flow",
    "resume_porder_flow": "resume_porder_flow",
    "process_problem_goods": "problem_goods",
}.items():
    _capability = capability_catalog()[_capability_key]
    TOOL_SPECS[_tool_name] = AgentToolSpec(
        _tool_name,
        f"{_capability.name}：{'；'.join(_capability.intents)}",
        _capability.risk.mutating,
        "组合脚本",
    )


def public_tool_catalog() -> list[Dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "mutating": spec.mutating,
            "category": spec.category,
        }
        for spec in TOOL_SPECS.values()
    ]


def _masked_key(key: Any) -> bool:
    text = str(key or "").strip().lower()
    return text in SENSITIVE_KEYS or text.endswith("_password") or text.endswith("_token")


def sanitize_observation(value: Any, *, depth: int = 0) -> Any:
    if depth >= 5:
        return "..."
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for key, item in list(value.items())[:80]:
            if _masked_key(key):
                continue
            result[str(key)] = sanitize_observation(item, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [sanitize_observation(item, depth=depth + 1) for item in list(value)[:30]]
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:1000]


def _decimal_text(value: Any) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    return format(number.normalize(), "f")


def _resolve_option_counts(
    operation: Dict[str, Any],
    catalog: list[Dict[str, Any]],
    contract_hash: str,
) -> Dict[str, int]:
    rows = sorted(
        (row for row in catalog if isinstance(row, dict) and str(row.get("key") or "").strip()),
        key=lambda row: str(row.get("key")),
    )
    mode = str(operation.get("mode") or "none").strip().lower()
    if mode == "random":
        count = int(operation.get("count") or 0)
        if count <= 0 or count > len(rows):
            raise ValueError(f"可用option数量{len(rows)}，无法选择{count}个")
        selected = random.Random(str(contract_hash)).sample(rows, count)
        return {str(row["key"]): 1 for row in selected}
    if mode == "named":
        result: Dict[str, int] = {}
        for requested in operation.get("names") or []:
            requested_text = str(requested or "").strip()
            matches = [
                row
                for row in rows
                if requested_text
                in {
                    str(row.get("key") or "").strip(),
                    str(row.get("name") or "").strip(),
                    str(row.get("label") or "").strip(),
                    str(row.get("name_translate") or "").strip(),
                }
            ]
            if len(matches) != 1:
                raise ValueError(f"option“{requested_text}”匹配到{len(matches)}项")
            result[str(matches[0]["key"])] = 1
        return result
    return {}


def _order_detail_rows(order_data: Dict[str, Any]) -> list[Dict[str, Any]]:
    rows = order_data.get("order_detail")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _order_inspection(summary: Dict[str, Any]) -> Dict[str, Any]:
    order_data = summary.get("order_data") if isinstance(summary.get("order_data"), dict) else {}
    details = _order_detail_rows(order_data)
    detail_rows = []
    shop_ids = set()
    for index, row in enumerate(details):
        shop_id = str(row.get("shop_id") or row.get("shopId") or row.get("shop_name") or "").strip()
        if shop_id:
            shop_ids.add(shop_id)
        detail_rows.append(
            {
                "index": index + 1,
                "id": row.get("id"),
                "goods_id": row.get("goods_id"),
                "shop_id": shop_id,
                "confirm_price": _decimal_text(row.get("confirm_price")),
                "offer_price": _decimal_text(
                    row.get("offer_price")
                    or row.get("offer_price_bak")
                    or row.get("confirm_price")
                ),
                "num": row.get("num") or row.get("confirm_num") or row.get("offer_num"),
                "options": sanitize_observation(row.get("option") or []),
            }
        )
    return {
        "order_sn": summary.get("order_sn"),
        "detected_start_node": summary.get("detected_start_node"),
        "order_status": summary.get("order_status"),
        "purchase_selected_count": summary.get("purchase_selected_count"),
        "purchase_pending_start_count": summary.get("purchase_pending_start_count"),
        "item_count": len(detail_rows),
        "shop_count": len(shop_ids),
        "items": detail_rows,
        "reason": summary.get("reason"),
    }


def _update_state(context: AgentToolContext, summary: Dict[str, Any]) -> None:
    for key in ("order_sn", "porder_sn", "purchase_no", "serial_number", "current_node", "detected_start_node"):
        value = summary.get(key)
        if value not in (None, ""):
            context.state[key] = value


def _find_cart_evidence(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        required = {"target_shops", "per_shop", "ready_shops", "added_total"}
        if required.issubset(value):
            return {key: value.get(key) for key in required | {"verified_added_total"}}
        for item in value.values():
            found = _find_cart_evidence(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_cart_evidence(item)
            if found:
                return found
    return {}


def _find_quote_evidence(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        if value.get("node") == "order_offered" and value.get("passed") is True:
            summary = value.get("summary") if isinstance(value.get("summary"), dict) else {}
            return {
                "quote_step_passed": True,
                "reported_unit_price": _decimal_text(summary.get("quote_unit_price")),
            }
        for item in value.values():
            found = _find_quote_evidence(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_quote_evidence(item)
            if found:
                return found
    return {}


def _collect_payment_evidence(value: Any, result: list[Dict[str, Any]] | None = None) -> list[Dict[str, Any]]:
    result = result if result is not None else []
    if len(result) >= 20:
        return result
    if isinstance(value, dict):
        if value.get("payment_type") in {"bank", "balance"}:
            evidence = {
                "payment_type": value.get("payment_type"),
                "finance_passed": value.get("finance_passed"),
                "order_sn": value.get("order_sn"),
                "porder_sn": value.get("porder_sn"),
                "serial_number": value.get("serial_number"),
            }
            if evidence not in result:
                result.append(evidence)
        for item in value.values():
            _collect_payment_evidence(item, result)
    elif isinstance(value, list):
        for item in value:
            _collect_payment_evidence(item, result)
    return result


def _save_script_result(
    context: AgentToolContext,
    tool_name: str,
    runner: Callable[..., Any],
    variables: Dict[str, Any],
) -> Dict[str, Any]:
    progress_runners = {
        data_scripts.run_full_flow_script,
        data_scripts.run_resume_order_flow_script,
        data_scripts.run_resume_porder_flow_script,
    }
    if context.progress_callback and runner in progress_runners:
        passed, log_text, report_path, raw_summary = runner(
            context.env,
            variables,
            progress_callback=context.progress_callback,
        )
    else:
        passed, log_text, report_path, raw_summary = runner(context.env, variables)
    summary = dict(raw_summary or {})
    try:
        execution_log = json.loads(log_text) if log_text else {}
    except (json.JSONDecodeError, TypeError):
        execution_log = {}
    cart_evidence = _find_cart_evidence(execution_log)
    if cart_evidence:
        summary["agent_cart_evidence"] = cart_evidence
    quote_evidence = _find_quote_evidence(execution_log)
    if quote_evidence:
        raw_prices = variables.get("offer_unit_prices")
        if isinstance(raw_prices, list):
            submitted_prices = [_decimal_text(value) for value in raw_prices if _decimal_text(value)]
        else:
            submitted_price = _decimal_text(variables.get("offer_price"))
            submitted_prices = [submitted_price] if submitted_price else []
        quote_evidence.update(
            {
                "submitted_unit_prices": submitted_prices,
                "submitted_quantity": variables.get("order_item_num"),
                "submitted_item_count": _problem_int(variables.get("order_shop_count"), 1)
                * _problem_int(variables.get("order_per_shop"), 1),
            }
        )
        summary["agent_quote_evidence"] = quote_evidence
    payment_evidence = _collect_payment_evidence(execution_log)
    if payment_evidence:
        summary["agent_payment_evidence"] = payment_evidence
    _update_state(context, summary)
    record = save_record(
        context.db,
        "api",
        0,
        bool(passed),
        log_text,
        report_path,
        project_id=context.project_id,
        kind="data_agent_tool",
        script_key=tool_name,
        env_id=context.env.id,
        variables=context.public_variables,
    )
    return {
        "tool": tool_name,
        "passed": bool(passed),
        "record_id": record.id,
        "report_path": report_path or "",
        "summary": sanitize_observation(summary),
    }


def _tool_variables(context: AgentToolContext, overrides: Dict[str, Any] | None = None) -> Dict[str, Any]:
    variables = dict(context.variables)
    variables.update(overrides or {})
    return variables


def _prepare_order_options(context: AgentToolContext) -> Dict[str, int]:
    operation = context.goal.get("options") if isinstance(context.goal.get("options"), dict) else {}
    if not operation.get("enabled"):
        return {}
    cached = context.state.get("selected_order_options")
    if isinstance(cached, list) and cached:
        counts = {
            str(row.get("key")): int(row.get("count") or 1)
            for row in cached
            if isinstance(row, dict) and str(row.get("key") or "").strip()
        }
    else:
        inspection = data_scripts.inspect_order_options(context.env, _tool_variables(context))
        catalog = [row for row in inspection.get("options") or [] if isinstance(row, dict)]
        counts = _resolve_option_counts(operation, catalog, str(context.goal.get("contract_hash") or ""))
        context.state["selected_order_options"] = [
            {**row, "count": counts[str(row.get("key"))]}
            for row in catalog
            if str(row.get("key")) in counts
        ]
    context.variables["order_option_counts"] = counts
    context.public_variables["order_option_counts"] = counts
    return counts


def _inspect_order_options(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    summary = data_scripts.inspect_order_options(context.env, _tool_variables(context))
    return {
        "tool": "inspect_order_options",
        "passed": True,
        "record_id": None,
        "report_path": "",
        "summary": sanitize_observation(summary),
        "_verification": summary,
    }


def _state_identifier(context: AgentToolContext, key: str, arguments: Dict[str, Any]) -> str:
    requested = str(arguments.get(key) or "").strip()
    known = str(context.state.get(key) or context.goal.get(key) or context.goal.get("variables", {}).get(key) or "").strip()
    if requested and not known:
        raise ValueError(f"{key} 未由已确认目标或前序工具生成")
    if requested and known and requested != known:
        raise ValueError(f"{key} 不属于已确认目标")
    return requested or known


def _safe_keyword(value: Any) -> str:
    keyword = str(value or "").strip()[:80]
    lowered = keyword.lower()
    if "://" in lowered or lowered.startswith(("//", "\\\\")):
        raise ValueError("商品关键词不能是URL或网络路径")
    return keyword


def _run_full_flow(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if context.goal.get("mode") != "new":
        raise ValueError("续跑任务不能重新创建全流程")
    if context.state.get("order_sn") or context.state.get("porder_sn"):
        raise ValueError("当前任务已有单号，必须查询状态并续跑，不能重复创建全流程")
    overrides: Dict[str, Any] = {"stop_after_node": context.goal["target_node"]}
    option_counts = _prepare_order_options(context)
    if option_counts:
        overrides["order_option_counts"] = option_counts
    keyword = _safe_keyword(arguments.get("keyword"))
    if keyword:
        overrides["keyword"] = keyword[:80]
    return _save_script_result(context, "full_flow", data_scripts.run_full_flow_script, _tool_variables(context, overrides))



# 全流程节点顺序（与 data_factory_agent.py 中 FULL_FLOW_NODE_SEQUENCE 保持一致）
_RESUME_NODE_ORDER = [
    "shopping_cart", "order_created", "order_translated", "order_confirmed",
    "order_offered", "order_paid", "pending_purchase", "purchase_no_saved",
    "purchase_wait_modify_price", "purchase_wait_pay", "purchase_paid",
    "checking_started", "shelf_stored", "warehouse_delivery_created",
    "porder_translated", "porder_confirmed", "porder_wait_offer",
    "porder_offered", "porder_paid", "full_complete",
]


def _check_resume_overshoot(result, target_node, flow_type="order"):
    """Detect when resume tools run beyond the stop_after_node."""
    if not target_node:
        return
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    actual_node = str(summary.get("current_node") or summary.get("stopped_after_node") or "")
    if not actual_node or actual_node == target_node:
        return
    try:
        target_idx = _RESUME_NODE_ORDER.index(target_node)
        actual_idx = _RESUME_NODE_ORDER.index(actual_node)
    except ValueError:
        return
    if actual_idx > target_idx:
        result["passed"] = False
        result.setdefault("summary", {})
        result["summary"]["overshoot_detected"] = True
        result["summary"]["reason"] = (
            f"续跑越过了stop_after_node={target_node}，"
            f"实际到达{actual_node}（已超{actual_idx - target_idx}个节点）；"
            f"请用inspect_order_state确认真实位置后决定finish或report_capability_gap"
        )

def _resume_order(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    order_sn = _state_identifier(context, "order_sn", arguments)
    if not order_sn:
        raise ValueError("续跑订单缺少订单号")
    result = _save_script_result(
        context,
        "resume_order_flow",
        data_scripts.run_resume_order_flow_script,
        _tool_variables(context, {"order_sn": order_sn, "stop_after_node": context.goal["target_node"]}),
    )
    # 检测续跑是否越过 stop_after_node
    _check_resume_overshoot(result, context.goal.get("target_node", ""), "order")
    return result


def _resume_porder(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    porder_sn = _state_identifier(context, "porder_sn", arguments)
    if not porder_sn:
        raise ValueError("续跑配送单缺少配送单号")
    result = _save_script_result(
        context,
        "resume_porder_flow",
        data_scripts.run_resume_porder_flow_script,
        _tool_variables(context, {"porder_sn": porder_sn, "stop_after_node": context.goal["target_node"]}),
    )
    _check_resume_overshoot(result, context.goal.get("target_node", ""), "porder")
    return result


def _rollback_business_state(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    operations = context.goal.get("operations") if isinstance(context.goal.get("operations"), list) else []
    operation_id = str(context.state.get("current_operation_id") or "")
    operation = next(
        (
            item
            for item in operations
            if isinstance(item, dict)
            and item.get("type") == "rollback"
            and (not operation_id or str(item.get("id") or "") == operation_id)
        ),
        None,
    )
    target = str((operation or {}).get("target_node") or context.goal.get("target_node") or "").strip()
    if target not in data_scripts.ROLLBACK_TARGET_LABELS:
        raise ValueError("回退目标未进入已确认合同")

    overrides: Dict[str, Any] = {"rollback_target": target, "target_node": target}
    if target.startswith("order_") or target == "shelf_checking":
        order_sn = _state_identifier(context, "order_sn", arguments)
        if order_sn:
            overrides["order_sn"] = order_sn
    if target.startswith("porder_"):
        porder_sn = _state_identifier(context, "porder_sn", arguments)
        if porder_sn:
            overrides["porder_sn"] = porder_sn
    return _save_script_result(
        context,
        "rollback_flow",
        data_scripts.run_rollback_flow_script,
        _tool_variables(context, overrides),
    )


def _fill_cart(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if context.state.get("order_sn") or context.state.get("porder_sn"):
        raise ValueError("当前任务已有单号，不能再修改共享购物车")
    keyword = _safe_keyword(arguments.get("keyword") or context.goal.get("variables", {}).get("keyword") or "衣服")
    variables = _tool_variables(
        context,
        {
            "keyword": keyword,
            "target_shops": context.goal["variables"].get("order_shop_count", 1),
            "per_shop": context.goal["variables"].get("order_per_shop", 2),
            "strict_shop_count": True,
        },
    )
    return _save_script_result(context, "shopping_cart", data_scripts.run_shopping_cart_script, variables)


def _quote_order(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if context.state.get("order_sn"):
        raise ValueError("当前任务已有订单号，不能重复提单，请使用订单续跑工具")
    option_counts = _prepare_order_options(context)
    return _save_script_result(
        context,
        "order_quote",
        data_scripts.run_order_quote_script,
        _tool_variables(
            context,
            {
                "stop_after_node": "order_offered",
                "run_backend_flow": True,
                "submit_order": True,
                **({"order_option_counts": option_counts} if option_counts else {}),
            },
        ),
    )


def _pay_order(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    order_sn = _state_identifier(context, "order_sn", arguments)
    if not order_sn:
        raise ValueError("订单支付缺少订单号")
    mode = str(context.goal["variables"].get("order_payment_mode") or "balance_first")
    runner = data_scripts.run_bank_payment_script if mode == "bank" else data_scripts.run_balance_payment_script
    key = "bank_payment" if mode == "bank" else "balance_payment"
    return _save_script_result(
        context,
        key,
        runner,
        _tool_variables(context, {"order_sn": order_sn, "finance_confirm": mode == "bank"}),
    )


def _confirm_bank_deposit(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if str(context.goal["variables"].get("order_payment_mode")) != "bank":
        raise ValueError("已确认目标不是银行支付")
    serial_number = _state_identifier(context, "serial_number", arguments)
    order_sn = _state_identifier(context, "order_sn", arguments)
    if not serial_number:
        raise ValueError("财务确认缺少银行流水号")
    return _save_script_result(
        context,
        "bank_payment",
        data_scripts.run_bank_payment_script,
        _tool_variables(context, {"order_sn": order_sn, "serial_number": serial_number, "finance_confirm": True}),
    )


def _advance_purchase(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    return _resume_order(context, arguments)


def _create_porder(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if context.state.get("porder_sn"):
        raise ValueError("当前任务已有配送单号，不能重复提出配送单")
    order_sn = _state_identifier(context, "order_sn", arguments)
    if not order_sn:
        raise ValueError("提出配送单缺少当前任务生成或确认的订单号")
    overrides = {"run_backend_delivery_flow": True}
    overrides["order_sn"] = order_sn
    return _save_script_result(
        context,
        "warehouse_delivery",
        data_scripts.run_warehouse_delivery_script,
        _tool_variables(context, overrides),
    )


def _pay_porder(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    porder_sn = _state_identifier(context, "porder_sn", arguments)
    if not porder_sn:
        raise ValueError("配送单支付缺少配送单号")
    mode = str(context.goal["variables"].get("porder_payment_mode") or "balance_first")
    runner = data_scripts.run_porder_bank_payment_script if mode == "bank" else data_scripts.run_porder_balance_payment_script
    key = "porder_bank_payment" if mode == "bank" else "porder_balance_payment"
    return _save_script_result(
        context,
        key,
        runner,
        _tool_variables(
            context,
            {"porder_sn": porder_sn, "run_backend_porder_flow": False, "finance_confirm": mode == "bank"},
        ),
    )


def _inspect_order(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    order_sn = _state_identifier(context, "order_sn", arguments)
    if not order_sn:
        raise ValueError("查询订单状态缺少订单号")
    detect_log: Dict[str, Any] = {}
    passed, summary = data_scripts._detect_resume_order_state(context.env, context.variables, order_sn, detect_log)
    _update_state(context, summary)
    return {
        "tool": "inspect_order_state",
        "passed": bool(passed),
        "record_id": None,
        "report_path": "",
        "summary": sanitize_observation(_order_inspection(summary)),
        "_verification": _order_inspection(summary),
    }


def _inspect_porder(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    porder_sn = _state_identifier(context, "porder_sn", arguments)
    if not porder_sn:
        raise ValueError("查询配送单状态缺少配送单号")
    detect_log: Dict[str, Any] = {}
    passed, summary = data_scripts._detect_resume_porder_state(context.env, context.variables, porder_sn, detect_log)
    _update_state(context, summary)
    compact = sanitize_observation(summary)
    return {
        "tool": "inspect_porder_state",
        "passed": bool(passed),
        "record_id": None,
        "report_path": "",
        "summary": compact,
        "_verification": compact,
    }


def _problem_goal_operation(context: AgentToolContext) -> Dict[str, Any]:
    operations = context.goal.get("operations") if isinstance(context.goal.get("operations"), list) else []
    operation_id = str(context.state.get("current_operation_id") or "")
    for item in operations:
        if not isinstance(item, dict) or item.get("type") != "problem_goods":
            continue
        if not operation_id or str(item.get("id") or "") == operation_id:
            return item
    raise ValueError("已确认目标中没有问题产品操作")


def _problem_runtime_variables(context: AgentToolContext, values: Dict[str, Any]) -> Dict[str, Any]:
    variables = _tool_variables(context, values)
    profile_id = context.state.get("backend_account_profile_id")
    if profile_id:
        account_values, _ = account_profile_variables(context.db, int(profile_id), context.project_id)
        backend_account = account_values.get("backend_account") or account_values.get("username") or account_values.get("account")
        backend_password = account_values.get("backend_password") or account_values.get("password")
        if not backend_account or not backend_password:
            raise ValueError("所选后台账号档案缺少账号或密码")
        variables.update(account_values)
        variables.update(
            {
                "backend_account": str(backend_account),
                "backend_password": str(backend_password),
                "backend_code": str(account_values.get("backend_code") or account_values.get("code") or ""),
                "backend_system": str(account_values.get("backend_system") or "1"),
                "backend_account_profile_id": int(profile_id),
            }
        )
    return variables


def _inspect_problem(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    order_sn = _state_identifier(context, "order_sn", arguments)
    if not order_sn:
        raise ValueError("查询问题产品缺少订单号")
    summary = inspect_problem_goods(
        context.env,
        _problem_runtime_variables(context, {"order_sn": order_sn}),
    )
    compact = sanitize_observation(summary)
    return {
        "tool": "inspect_problem_goods",
        "passed": True,
        "record_id": None,
        "report_path": "",
        "summary": compact,
        "_verification": summary,
    }


def _problem_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return fallback


def _problem_option_rows(value: Any) -> list[Dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _zero_problem_options(value: Any) -> list[Dict[str, Any]]:
    return [{**item, "num": "0", "price": "0"} for item in _problem_option_rows(value)]


def _problem_options_signature(value: Any) -> list[Dict[str, str]]:
    return sorted(
        [
            {
                "key": str(item.get("id") or item.get("option_id") or item.get("name") or "").strip(),
                "name": str(item.get("name") or "").strip(),
                "price_type": str(item.get("price_type") or "0").strip(),
                "num": _decimal_text(item.get("num")),
                "price": _decimal_text(item.get("price")),
            }
            for item in _problem_option_rows(value)
        ],
        key=lambda item: (item["key"], item["name"]),
    )


def _problem_contract_mismatches(
    items: list[Dict[str, Any]],
    expected_map: Dict[str, Any],
) -> list[Dict[str, Any]]:
    mismatches: list[Dict[str, Any]] = []
    for item in items:
        problem_goods_id = item.get("problem_goods_id")
        expected = expected_map.get(str(_problem_int(problem_goods_id))) or {}
        for key in ("pre_num", "pre_price", "pre_freight"):
            if key not in expected:
                continue
            actual_value = _decimal_text(item.get(key))
            expected_value = _decimal_text(expected.get(key))
            if actual_value != expected_value:
                mismatches.append(
                    {
                        "problem_goods_id": problem_goods_id,
                        "field": key,
                        "expected": expected_value,
                        "actual": actual_value,
                    }
                )
        if "option_new" in expected:
            actual_options = _problem_options_signature(item.get("option_new"))
            expected_options = _problem_options_signature(expected.get("option_new"))
            if actual_options != expected_options:
                mismatches.append(
                    {
                        "problem_goods_id": problem_goods_id,
                        "field": "option_new",
                        "expected": expected_options,
                        "actual": actual_options,
                    }
                )
    return mismatches


def _problem_values(
    context: AgentToolContext,
    operation: Dict[str, Any],
    order_sn: str,
    row: Dict[str, Any],
) -> tuple[Dict[str, Any], str]:
    problem_goods_id = _problem_int(row.get("problem_goods_id"))
    saved_pre_num = _problem_int(row.get("pre_num"))
    saved_problem_num = _problem_int(row.get("problem_num"))
    original_num = _problem_int(
        row.get("confirm_num")
        or ((saved_pre_num + saved_problem_num) if problem_goods_id else 0)
        or row.get("possible_num")
        or row.get("pre_num")
        or row.get("problem_num")
    )
    max_submit_num = _problem_int(row.get("max_submit_num"), original_num)
    if original_num <= 0 or max_submit_num <= 0:
        return {}, "当前商品没有可提出的问题产品数量"
    quantity_mode = str(operation.get("quantity_refund_mode") or "keep")
    if problem_goods_id and saved_problem_num > 0:
        refund_num = saved_problem_num
    elif quantity_mode == "all":
        if max_submit_num < original_num:
            return {}, f"商品原数量{original_num}，但仅有{max_submit_num}件可提出，无法按“全部数量”执行"
        refund_num = original_num
    elif quantity_mode == "half":
        if original_num % 2:
            return {}, f"商品数量{original_num}无法精确退一半，请明确退款数量"
        refund_num = original_num // 2
    elif quantity_mode == "fixed":
        refund_num = _problem_int(operation.get("quantity_refund_value"))
    elif quantity_mode == "keep":
        refund_num = 1
    else:
        return {}, "提出问题产品时必须明确需要退款的商品数量"
    if refund_num <= 0 or refund_num > max_submit_num:
        return {}, f"退款数量{refund_num}超过可提出数量{max_submit_num}"

    original_price = _decimal_text(row.get("confirm_price") or row.get("price") or row.get("pre_price"))
    original_freight = _decimal_text(row.get("confirm_freight") or row.get("freight") or row.get("pre_freight"))
    price_adjustment_mode = str(operation.get("price_adjustment_mode") or "keep")
    if price_adjustment_mode == "zero":
        original_price = "0"
    elif price_adjustment_mode == "fixed":
        adjust_value = operation.get("price_adjustment_value")
        if adjust_value is not None:
            original_price = _decimal_text(adjust_value)
    if original_price == "":
        return {}, "无法读取商品原单价，已停止避免错误退款"
    if original_freight == "":
        original_freight = "0"
    customer_id = str(row.get("customer_id") or order_sn.rsplit("-", 1)[-1] or "").strip()
    option_refund_all = operation.get("option_refund_mode") == "all"
    values = {
        "order_sn": order_sn,
        "customer_id": customer_id,
        "problem_goods_id": problem_goods_id or "",
        "create_if_missing": not bool(problem_goods_id),
        "order_purchase_id": row.get("order_purchase_id"),
        "order_detail_id": row.get("order_detail_id"),
        "problem_type": int(operation.get("problem_type") or 8),
        "problem_num": refund_num,
        "problem_description": "数据智能体自动提出问题产品",
        "translation_content": "データエージェント問題商品",
        "client_deal_choice": "accept",
        "business_decision": "数据智能体按已确认目标处理",
        "service_deal_suggest": 2,
        "option_deal_suggest": 1 if option_refund_all else 2,
        "pre_num": saved_pre_num if problem_goods_id else (original_num if quantity_mode == "keep" else original_num - refund_num),
        "pre_price": original_price,
        "pre_freight": "0" if operation.get("freight_refund_mode") == "all" else original_freight,
        "g_deal_type": "其他",
        "purchase_remark": "数据智能体自动处理",
        "confirm_distribution": True,
    }
    if option_refund_all:
        values["option_new"] = _zero_problem_options(row.get("option") or row.get("option_new") or [])
    return _problem_runtime_variables(context, values), ""


def _emit_tool_progress(context: AgentToolContext, node: str, status: str, **extra: Any) -> None:
    if context.progress_callback:
        context.progress_callback({"node": node, "status": status, **extra})


def _process_problem(context: AgentToolContext, arguments: Dict[str, Any]) -> Dict[str, Any]:
    operation = _problem_goal_operation(context)
    order_sn = _state_identifier(context, "order_sn", arguments)
    if not order_sn:
        raise ValueError("处理问题产品缺少订单号")
    inspection = inspect_problem_goods(
        context.env,
        _problem_runtime_variables(context, {"order_sn": order_sn}),
    )
    existing = [item for item in inspection.get("items") or [] if isinstance(item, dict)]
    candidates = [item for item in inspection.get("order_candidates") or [] if isinstance(item, dict)]
    known_ids = {_problem_int(value) for value in context.state.get("problem_goods_ids") or []}
    expected_map = context.state.get("problem_goods_expected") if isinstance(context.state.get("problem_goods_expected"), dict) else {}
    active_known = [item for item in existing if _problem_int(item.get("problem_goods_id")) in known_ids and _problem_int(item.get("status")) < 6]
    completed_known = [item for item in existing if _problem_int(item.get("problem_goods_id")) in known_ids and _problem_int(item.get("status")) == 6]
    rows = [*active_known, *candidates] if operation.get("scope") == "all_candidates" else (active_known or candidates)
    if not rows and known_ids and len(completed_known) == len(known_ids):
        mismatches = _problem_contract_mismatches(completed_known, expected_map)
        completed_all = bool(expected_map) and not mismatches
        return {
            "tool": "process_problem_goods",
            "passed": completed_all,
            "record_id": None,
            "report_path": "",
            "summary": {
                "order_sn": order_sn,
                "completed_all": completed_all,
                "items": sanitize_observation(completed_known),
                "mismatches": mismatches,
                **({} if completed_all else {"reason": "已完成的问题产品无法通过退款合同复核"}),
            },
        }
    if not rows:
        return {
            "tool": "process_problem_goods",
            "passed": False,
            "record_id": None,
            "report_path": "",
            "summary": {"order_sn": order_sn, "reason": "没有可提出或可继续的问题产品记录", "needs_clarification": True},
        }
    if operation.get("scope") != "all_candidates" and len(rows) != 1:
        return {
            "tool": "process_problem_goods",
            "passed": False,
            "record_id": None,
            "report_path": "",
            "summary": {"order_sn": order_sn, "reason": f"订单有{len(rows)}个可处理商品，请明确处理哪一个或说明全部处理", "needs_clarification": True},
        }

    rows.sort(key=lambda item: (_problem_int(item.get("sorting"), 10**9), _problem_int(item.get("order_detail_id"))))
    completed_ids = list(known_ids)
    child_record_ids: list[int] = []
    last_report = ""
    item_total = len(rows)
    for item_index, row in enumerate(rows, start=1):
        _emit_tool_progress(
            context,
            "problem_goods",
            "running",
            item_index=item_index,
            item_total=item_total,
            problem_goods_id=_problem_int(row.get("problem_goods_id")) or None,
        )
        variables, reason = _problem_values(context, operation, order_sn, row)
        if reason:
            _emit_tool_progress(
                context,
                "problem_goods",
                "failed",
                item_index=item_index,
                item_total=item_total,
                reason=reason,
            )
            return {
                "tool": "process_problem_goods",
                "passed": False,
                "record_id": None,
                "report_path": "",
                "summary": {"order_sn": order_sn, "reason": reason, "needs_clarification": True},
            }
        result = _save_script_result(
            context,
            "problem_goods",
            data_scripts.run_problem_goods_script,
            variables,
        )
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        if result.get("record_id"):
            child_record_ids.append(int(result["record_id"]))
        last_report = str(result.get("report_path") or last_report)
        problem_goods_id = _problem_int(summary.get("problem_goods_id"))
        if problem_goods_id and problem_goods_id not in completed_ids:
            completed_ids.append(problem_goods_id)
        if problem_goods_id:
            expected_map = context.state.get("problem_goods_expected") if isinstance(context.state.get("problem_goods_expected"), dict) else {}
            expected_map[str(problem_goods_id)] = {
                "pre_num": variables.get("pre_num"),
                "pre_price": variables.get("pre_price"),
                "pre_freight": variables.get("pre_freight"),
                **({"option_new": variables.get("option_new")} if "option_new" in variables else {}),
            }
            context.state["problem_goods_expected"] = expected_map
        context.state["problem_goods_ids"] = completed_ids
        if summary.get("paused") and summary.get("permission_required"):
            context.state.update(
                {
                    "problem_goods_id": problem_goods_id,
                    "awaiting_permission": True,
                    "required_account_role": summary.get("required_account_role") or "department_leader",
                }
            )
            _emit_tool_progress(
                context,
                "problem_goods",
                "awaiting_permission",
                item_index=item_index,
                item_total=item_total,
                problem_goods_id=problem_goods_id or None,
            )
            return {
                "tool": "process_problem_goods",
                "passed": False,
                "record_id": result.get("record_id"),
                "report_path": last_report,
                "summary": {
                    **summary,
                    "awaiting_permission": True,
                    "child_record_ids": child_record_ids,
                },
            }
        if not result.get("passed") or not (summary.get("completed") or summary.get("already_completed")):
            _emit_tool_progress(
                context,
                "problem_goods",
                "failed",
                item_index=item_index,
                item_total=item_total,
                problem_goods_id=problem_goods_id or None,
                reason=str(summary.get("reason") or summary.get("error") or "问题产品未完成"),
            )
            return {
                **result,
                "tool": "process_problem_goods",
                "passed": False,
                "summary": {**summary, "child_record_ids": child_record_ids},
            }
        _emit_tool_progress(
            context,
            "problem_goods",
            "completed",
            item_index=item_index,
            item_total=item_total,
            problem_goods_id=problem_goods_id or None,
        )

    final_inspection = inspect_problem_goods(
        context.env,
        _problem_runtime_variables(context, {"order_sn": order_sn}),
    )
    final_items = [item for item in final_inspection.get("items") or [] if _problem_int(item.get("problem_goods_id")) in set(completed_ids)]
    mismatches = _problem_contract_mismatches(final_items, expected_map)
    completed_all = bool(final_items) and all(_problem_int(item.get("status")) == 6 for item in final_items) and not mismatches
    context.state["awaiting_permission"] = False
    return {
        "tool": "process_problem_goods",
        "passed": completed_all,
        "record_id": child_record_ids[-1] if child_record_ids else None,
        "report_path": last_report,
        "summary": {
            "order_sn": order_sn,
            "completed_all": completed_all,
            "problem_goods_ids": completed_ids,
            "items": sanitize_observation(final_items),
            "mismatches": mismatches,
            "child_record_ids": child_record_ids,
            **({} if completed_all else {"reason": "问题产品实际状态尚未全部完成"}),
        },
    }


TOOL_RUNNERS: Dict[str, Callable[[AgentToolContext, Dict[str, Any]], Dict[str, Any]]] = {
    "run_full_flow": _run_full_flow,
    "resume_order_flow": _resume_order,
    "resume_porder_flow": _resume_porder,
    "rollback_business_state": _rollback_business_state,
    "fill_shopping_cart": _fill_cart,
    "quote_order": _quote_order,
    "pay_order": _pay_order,
    "confirm_order_bank_deposit": _confirm_bank_deposit,
    "advance_purchase_to_shelf": _advance_purchase,
    "create_and_quote_porder": _create_porder,
    "pay_porder": _pay_porder,
    "inspect_order_state": _inspect_order,
    "inspect_porder_state": _inspect_porder,
    "inspect_problem_goods": _inspect_problem,
    "inspect_order_options": _inspect_order_options,
    "process_problem_goods": _process_problem,
}


def execute_agent_tool(name: str, context: AgentToolContext, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
    runner = TOOL_RUNNERS.get(str(name or "").strip())
    if not runner:
        raise ValueError(f"未注册的数据工具：{name}")
    safe_arguments = arguments if isinstance(arguments, dict) else {}
    result = runner(context, safe_arguments)
    result.pop("_raw", None)
    return result


def aggregate_log(goal: Dict[str, Any], events: list[Dict[str, Any]], result: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "script": "DeepSeek数据智能体",
            "goal": sanitize_observation(goal),
            "events": sanitize_observation(events),
            "summary": sanitize_observation(result),
        },
        ensure_ascii=False,
        default=str,
    )
