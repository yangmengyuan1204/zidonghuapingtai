from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..core.account_utils import account_profile_variables, default_account_profile_for_target
from ..core.data_script_catalog import DATA_SCRIPT_PROJECT_NAME
from ..core.utils import data_script_variables, save_record
from ..database import SessionLocal
from ..functional_testing.model_client import call_local_model_json
from ..models import AiConfig, Env, Project, TestAccountProfile
from .data_factory_agent_intent import reduce_intent_fields
from .data_factory_agent_contract import (
    compile_contract_defaults,
    problem_goods_clarification,
    read_deterministic_problem_fields,
)
from .data_factory_agent_prompts import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_ACTION,
    build_analysis_prompt,
    build_action_prompt,
)
from .data_factory_agent_tools import (
    AgentToolContext,
    TOOL_SPECS,
    aggregate_log,
    execute_agent_tool,
    public_tool_catalog,
    sanitize_observation,
)


logger = logging.getLogger(__name__)


SESSION_TTL = timedelta(hours=2)
MAX_AGENT_ROUNDS = 12
MAX_IDENTICAL_ACTIONS = 2
UNSUPPORTED_CAPABILITIES = {
    "OEM": "新增受控OEM造数工具组",
    "分批付款": "新增分批付款计划、首款和尾款校验工具",
    "按番尾款": "新增按番尾款支付与状态查询工具",
    "出入金调整": "新增经二次确认的出入金调整工具",
    "删除订单": "新增受控订单删除工具",
    "取消订单": "新增受控订单取消工具",
}
IGNORED_MODEL_VARIABLE_KEYS = {
    "item_index",
    "pricing_mode",
    "pricing",
    "item_count",
    "problem_scope",
    "options",
    "problem_refund_quantity",
    "problem_refund_freight",
    "problem_preserve_price",
}
TERMINAL_STATUSES = {"succeeded", "failed", "blocked", "cancelled"}
SESSION_STATUSES = {
    "clarifying",
    "awaiting_confirmation",
    "awaiting_permission",
    "running",
    "succeeded",
    "failed",
    "blocked",
    "cancelled",
}

FULL_FLOW_NODE_LABELS: Dict[str, str] = {
    "shopping_cart": "商品加购完成",
    "order_created": "前台提交订单完成",
    "order_translated": "后台订单翻译完成",
    "order_confirmed": "后台订单确认完成",
    "order_offered": "后台订单报价完成",
    "order_paid": "订单支付完成",
    "pending_purchase": "订单进入待拍下",
    "purchase_no_saved": "保存交易号完成",
    "purchase_wait_modify_price": "标记待改价完成",
    "purchase_wait_pay": "提交待财务付款完成",
    "purchase_paid": "交易号付款完成",
    "checking_started": "开始核查完成",
    "shelf_stored": "核查上架入库完成",
    "warehouse_delivery_created": "仓库提出配送单完成",
    "porder_translated": "配送单翻译完成",
    "porder_confirmed": "配送单确认流转完成",
    "porder_wait_offer": "配送单进入待报价",
    "porder_offered": "配送单报价完成",
    "porder_paid": "配送单支付完成",
    "full_complete": "全流程结束",
}
FULL_FLOW_NODE_SEQUENCE = list(FULL_FLOW_NODE_LABELS)
NODE_ALIASES = {
    "加购": "shopping_cart",
    "购物车": "shopping_cart",
    "创建订单": "order_created",
    "提交订单": "order_created",
    "翻译": "order_translated",
    "采购确认": "order_confirmed",
    "订单报价": "order_offered",
    "报价完成": "order_offered",
    "订单支付": "order_paid",
    "付款完成": "order_paid",
    "待拍下": "pending_purchase",
    "交易号": "purchase_no_saved",
    "待改价": "purchase_wait_modify_price",
    "采购待付款": "purchase_wait_pay",
    "待付款": "purchase_wait_pay",
    "采购付款": "purchase_paid",
    "开始核查": "checking_started",
    "上架": "shelf_stored",
    "入库": "shelf_stored",
    "提出配送单": "warehouse_delivery_created",
    "配送单翻译": "porder_translated",
    "配送单确认": "porder_confirmed",
    "配送单待报价": "porder_wait_offer",
    "配送单报价": "porder_offered",
    "配送单支付": "porder_paid",
    "全流程": "full_complete",
}

ALLOWED_GOAL_KEYS = {
    "assumptions",
    "customer_ids",
    "intent",
    "mode",
    "operations",
    "options",
    "order_sn",
    "porder_sn",
    "summary",
    "target_node",
    "variables",
    "unhandled_requests",
}
ALLOWED_VARIABLE_KEYS = {
    "box_count",
    "box_height",
    "box_length",
    "box_weight",
    "box_width",
    "client_remark",
    "client_remark_translate",
    "confirm_freight",
    "confirm_price",
    "confirm_remark",
    "confirm_volume",
    "confirm_weight",
    "delivery_quote_logistics_id",
    "discounts_id",
    "express_no",
    "fba_complete_num",
    "finance_confirm",
    "grid_id",
    "keyword",
    "logistics_price_artificial",
    "merge_pay",
    "offer_freight",
    "offer_num",
    "offer_price",
    "offer_remark",
    "offer_unit_prices",
    "order_item_num",
    "order_option_counts",
    "order_payment_mode",
    "payment_fallback",
    "order_per_shop",
    "order_shop_count",
    "other_price",
    "other_price_remark",
    "pay_name",
    "pay_remark",
    "porder_detail_remark",
    "porder_offer_remark",
    "porder_payment_mode",
    "porder_y_remark",
    "purchase_freight",
    "purchase_no",
    "purchase_unit_price",
    "quantities",
    "send_num",
    "shelf_type_set",
    "shop_type",
    "stop_after_node",
    "target_shops",
    "per_shop",
    "translate_remark",
    "warehouse_index",
    "warehouse_sku_count",
    "warehouse_user_id",
}

DEFAULT_VARIABLES: Dict[str, Any] = {
    "keyword": "衣服",
    "shop_type": "1688",
    "order_shop_count": 1,
    "order_per_shop": 1,
    "order_item_num": 1,
    "client_remark": "自动化提出订单",
    "translate_remark": "自动化订单翻译",
    "confirm_price": "10",
    "confirm_freight": "5",
    "confirm_volume": "1x2x3",
    "confirm_weight": "200",
    "confirm_remark": "自动化采购调查",
    "offer_price": "10",
    "offer_freight": "5",
    "other_price": "0",
    "other_price_remark": "自动化其他费用备注",
    "offer_remark": "自动化业务报价",
    "order_payment_mode": "balance_first",
    "pay_name": "自动化测试",
    "pay_remark": "自动化银行付款",
    "finance_confirm": True,
    "purchase_unit_price": "10",
    "purchase_freight": "0",
    "warehouse_index": "2",
    "shelf_type_set": "1,3",
    "warehouse_sku_count": 1,
    "send_num": 1,
    "box_count": 1,
    "box_length": 58,
    "box_width": 51,
    "box_height": 50,
    "box_weight": 10,
    "delivery_quote_logistics_id": "25",
    "logistics_price_artificial": "775",
    "porder_payment_mode": "balance_first",
    "merge_pay": "0",
}

POSITIVE_INT_FIELDS = {
    "box_count",
    "box_height",
    "box_length",
    "box_weight",
    "box_width",
    "order_item_num",
    "order_per_shop",
    "order_shop_count",
    "send_num",
    "warehouse_sku_count",
}
DECIMAL_FIELDS = {
    "confirm_freight",
    "confirm_price",
    "confirm_weight",
    "logistics_price_artificial",
    "offer_freight",
    "offer_num",
    "offer_price",
    "other_price",
    "purchase_freight",
    "purchase_unit_price",
}


@dataclass
class AgentSessionState:
    id: str
    user_id: int
    project_id: int
    env_id: int
    status: str
    plan_version: int = 1
    messages: list[Dict[str, str]] = field(default_factory=list)
    compile_context: Dict[str, Any] = field(default_factory=dict)
    goal: Dict[str, Any] = field(default_factory=dict)
    question: str = ""
    events: list[Dict[str, Any]] = field(default_factory=list)
    result: Dict[str, Any] = field(default_factory=dict)
    runtime_state: Dict[str, Any] = field(default_factory=dict)
    intent_state: Dict[str, Any] = field(default_factory=dict)
    clarification_counts: Dict[str, int] = field(default_factory=dict)
    analysis_record_ids: list[int] = field(default_factory=list)
    cancel_requested: bool = False
    record_id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


_SESSIONS: Dict[str, AgentSessionState] = {}
_STORE_LOCK = threading.RLock()
_ENV_RUNNING: Dict[int, str] = {}
_TEMP_PERMISSION_SECRETS: Dict[str, Dict[str, str]] = {}
_CLAIMED_TEMP_PERMISSION_SECRETS: set[str] = set()
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="data-factory-agent")


def _store_temp_permission_secret(session_id: str, backend_account: str, backend_password: str) -> None:
    with _STORE_LOCK:
        key = str(session_id)
        previous = _TEMP_PERMISSION_SECRETS.pop(key, None)
        if previous:
            previous.clear()
        _CLAIMED_TEMP_PERMISSION_SECRETS.discard(key)
        _TEMP_PERMISSION_SECRETS[key] = {
            "backend_account": str(backend_account),
            "backend_password": str(backend_password),
        }


def _take_temp_permission_secret(session_id: str) -> Dict[str, str]:
    with _STORE_LOCK:
        key = str(session_id)
        if key in _CLAIMED_TEMP_PERMISSION_SECRETS:
            return {}
        secret = _TEMP_PERMISSION_SECRETS.get(key)
        if not secret:
            return {}
        _CLAIMED_TEMP_PERMISSION_SECRETS.add(key)
        return secret


def _clear_temp_permission_secret(session_id: str) -> None:
    with _STORE_LOCK:
        key = str(session_id)
        secret = _TEMP_PERMISSION_SECRETS.pop(key, None)
        _CLAIMED_TEMP_PERMISSION_SECRETS.discard(key)
        if secret:
            secret.clear()


def _safe_exception_text(exc: Exception, credentials: Dict[str, str]) -> str:
    message = str(exc)
    for value in credentials.values():
        if value:
            message = message.replace(str(value), "[REDACTED]")
    return message


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _event(kind: str, message: str, **data: Any) -> Dict[str, Any]:
    return {"time": _now_text(), "kind": kind, "message": str(message or ""), **sanitize_observation(data)}


def _cleanup_sessions() -> None:
    cutoff = datetime.now() - SESSION_TTL
    for session_id, session in list(_SESSIONS.items()):
        if session.updated_at < cutoff:
            _clear_temp_permission_secret(session_id)
            if session.status != "running":
                _SESSIONS.pop(session_id, None)


def _session_or_404(session_id: str, user_id: int) -> AgentSessionState:
    with _STORE_LOCK:
        _cleanup_sessions()
        session = _SESSIONS.get(str(session_id))
        if not session or session.user_id != int(user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="智能体任务不存在")
        return session


def _serialize_session(session: AgentSessionState) -> Dict[str, Any]:
    with _STORE_LOCK:
        payload = {
            "id": session.id,
            "project_id": session.project_id,
            "env_id": session.env_id,
            "status": session.status,
            "plan_version": session.plan_version,
            "messages": copy.deepcopy(session.messages),
            "goal": copy.deepcopy(session.goal),
            "question": session.question,
            "events": copy.deepcopy(session.events),
            "result": copy.deepcopy(session.result),
            "current_state": copy.deepcopy(session.runtime_state),
            "intent_state": copy.deepcopy(session.intent_state),
            "pending_fields": copy.deepcopy(session.intent_state.get("pending_fields") or {}),
            "record_id": session.record_id,
            "analysis_record_ids": list(session.analysis_record_ids),
            "can_confirm": session.status == "awaiting_confirmation",
            "can_message": session.status in {"clarifying", "awaiting_confirmation"},
            "can_permission": session.status == "awaiting_permission",
            "can_cancel": session.status == "running",
            "created_at": session.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": session.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
    return payload


def _save_analysis_record(
    db: Session,
    session: AgentSessionState,
    trace: Dict[str, Any],
    session_status: str,
    question: str,
) -> int | None:
    log_data = {
        "script": "DeepSeek数据智能体识别分析",
        "session_id": session.id,
        "turn_index": max(0, len(session.messages) - 1),
        "status": str(session_status or ""),
        "question": str(question or ""),
        "analysis": sanitize_observation(trace),
    }
    try:
        record = save_record(
            db,
            "api",
            0,
            session_status == "awaiting_confirmation",
            json.dumps(log_data, ensure_ascii=False, default=str),
            "",
            project_id=session.project_id,
            kind="data_agent_analysis",
            script_key="data_factory_agent_analysis",
            env_id=session.env_id,
            variables={},
        )
    except Exception as exc:
        logger.error("保存数据智能体识别记录失败 session_id=%s: %s", session.id, exc, exc_info=True)
        return None
    record_id = int(record.id)
    if record_id not in session.analysis_record_ids:
        session.analysis_record_ids.append(record_id)
    return record_id


def validate_agent_context(db: Session, project_id: int, env_id: int) -> tuple[Project, Env]:
    project = db.get(Project, int(project_id))
    if not project or project.name != DATA_SCRIPT_PROJECT_NAME:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="数据智能体仅允许日本站测试项目")
    env = db.get(Env, int(env_id))
    if not env or env.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="环境不属于日本站测试项目")
    return project, env


def _auto_large_refund_profile_id(db: Session, project_id: int) -> int | None:
    profile = (
        db.query(TestAccountProfile)
        .filter(
            TestAccountProfile.project_id == int(project_id),
            TestAccountProfile.status == "active",
            TestAccountProfile.profile_name == "后台沈文妮账号",
        )
        .order_by(TestAccountProfile.id.asc())
        .first()
    )
    if not profile:
        return None
    try:
        account_values, _ = account_profile_variables(db, int(profile.id), int(project_id))
    except HTTPException:
        return None
    backend_account = account_values.get("backend_account") or account_values.get("username") or account_values.get("account")
    backend_password = account_values.get("backend_password") or account_values.get("password")
    return int(profile.id) if backend_account and backend_password else None


def _latest_model_config(db: Session) -> AiConfig:
    config = db.query(AiConfig).order_by(AiConfig.id.desc()).first()
    if not config or not str(config.base_url or "").strip() or not str(config.model or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先在AI配置中完成DeepSeek模型配置")
    return config


def _analysis_prompt(
    messages: list[Dict[str, str]],
    intent_state: Dict[str, Any] | None = None,
) -> str:
    return build_analysis_prompt(
        messages=messages,
        intent_state=intent_state,
        node_labels=FULL_FLOW_NODE_LABELS,
        allowed_variable_keys=ALLOWED_VARIABLE_KEYS,
    )


def _unsupported_capability(messages: list[Dict[str, str]]) -> Dict[str, str]:
    text = "\n".join(str(item.get("content") or "") for item in messages if isinstance(item, dict))
    if re.search(r"(?:执行|运行|修改|删除|写入|注入).{0,12}\b(?:SQL|SELECT|UPDATE|INSERT|DELETE|DROP|ALTER)\b", text, re.IGNORECASE):
        return {
            "reason": "当前数据智能体禁止执行任意SQL，未触发任何业务调用。",
            "capability_gap": "任意SQL",
            "suggested_tool": "使用已注册且受合同校验的数据工具",
        }
    if re.search(r"(?:调用|访问|请求|打开).{0,12}(?:外部)?(?:URL|https?://)", text, re.IGNORECASE):
        return {
            "reason": "当前数据智能体禁止调用外部URL，未触发任何业务调用。",
            "capability_gap": "外部URL",
            "suggested_tool": "使用已注册且受目标校验的业务工具",
        }
    if re.search(r"(?:把)?订单(?:给我)?(?:删除|删掉|删了)|(?:删除|删掉|删了).{0,4}订单", text):
        return {
            "reason": "当前数据智能体尚未注册“删除订单”能力，未触发任何业务调用。",
            "capability_gap": "删除订单",
            "suggested_tool": UNSUPPORTED_CAPABILITIES["删除订单"],
        }
    for keyword, suggestion in UNSUPPORTED_CAPABILITIES.items():
        if keyword.lower() in text.lower():
            return {
                "reason": f"当前数据智能体尚未注册“{keyword}”能力，未触发任何业务调用。",
                "capability_gap": keyword,
                "suggested_tool": suggestion,
            }
    return {}


def _decimal_value(value: Any, field_name: str) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是数字") from exc
    if number < 0:
        raise ValueError(f"{field_name} 不能小于0")
    return format(number.normalize(), "f")


def _positive_int(value: Any, field_name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是正整数") from exc
    if number <= 0:
        raise ValueError(f"{field_name} 必须是正整数")
    return number


def _bool_value(value: Any, fallback: bool = False) -> bool:
    if value in (None, ""):
        return fallback
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {"0", "false", "no", "off", "否"}


def _keyword_value(value: Any) -> str:
    keyword = str(value or "衣服").strip()[:80]
    lowered = keyword.lower()
    if "://" in lowered or lowered.startswith(("//", "\\\\")):
        raise ValueError("keyword 只能是商品检索词，不能是URL或网络路径")
    return keyword or "衣服"


_COUNT_TOKEN = r"(?:\d+|[一二两三四五六七八九十百]+)"
_CHINESE_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _source_text(messages: list[Dict[str, str]] | None) -> str:
    if not messages:
        return ""
    return "\n".join(
        str(item.get("content") or "").strip()
        for item in messages
        if isinstance(item, dict) and str(item.get("content") or "").strip()
    )[:16000]


def _compact_semantic_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace("，", ",").replace("：", ":")


def _reduce_intent_state(state: Dict[str, Any], message: str) -> Dict[str, Any]:
    result = reduce_intent_fields(state, message)
    text = _compact_semantic_text(message)
    options = dict(result.get("options") or {})
    if re.search(r"(?:option|附加服务).{0,8}(?:不要|不添加|取消)", text, re.IGNORECASE):
        options = {"enabled": False, "mode": "none", "count": 0, "names": []}
    option_count = re.search(
        r"(?:每番|每个商品)?.{0,6}(?:随机)?.{0,4}(?:添加|加)?(\d+)个(?:option|附加服务)",
        text,
        re.IGNORECASE,
    )
    if option_count:
        options = {"enabled": True, "mode": "random", "count": int(option_count.group(1)), "names": []}
    if re.search(r"(?:还是|恢复|继续).{0,8}(?:需要|添加).{0,8}(?:option|附加服务)", text, re.IGNORECASE):
        options["enabled"] = True
    if options:
        result["options"] = options
    return result


MAX_CLARIFICATION_TOTAL_ROUNDS = 3
MAX_LIFETIME_CLARIFICATIONS = 5


def _bounded_clarification(
    session: AgentSessionState,
    field_name: str,
    message: str,
) -> Dict[str, Any]:
    count = int(session.clarification_counts.get(field_name, 0)) + 1
    session.clarification_counts[field_name] = count
    total_rounds = sum(
        int(value)
        for key, value in session.clarification_counts.items()
        if key != "_global"
    )
    lifetime = int(session.clarification_counts.get("_global", 0)) + 1
    session.clarification_counts["_global"] = lifetime
    blocked = total_rounds >= MAX_CLARIFICATION_TOTAL_ROUNDS or lifetime >= MAX_LIFETIME_CLARIFICATIONS
    return {"blocked": blocked, "message": str(message or "请补充该字段。"), "count": count, "lifetime": lifetime}


def _clarification_field(question: str) -> str:
    text = str(question or "").lower()
    if "option" in text or "附加服务" in text:
        return "options"
    if "第几番" in text or "全部商品" in text:
        return "problem_scope"
    if "问题产品" in text or "问题商品" in text:
        return "problem_goods"
    if "数量" in text or "商品数" in text:
        return "quantity"
    if "价格" in text or "总价" in text or "单价" in text:
        return "pricing"
    if "运费" in text or "退款" in text or "问题产品" in text:
        return "problem_goods"
    if "节点" in text or "状态" in text:
        return "target_node"
    return "general"


def _update_pending_fields(
    intent_state: Dict[str, Any],
    session_status: str,
    question: str,
) -> Dict[str, Any]:
    result = copy.deepcopy(intent_state) if isinstance(intent_state, dict) else {}
    if session_status != "clarifying" or not question:
        result["pending_fields"] = {}
        return result
    field_name = _clarification_field(question)
    labels = {
        "options": "附加服务",
        "problem_scope": "问题产品范围",
        "quantity": "商品数量",
        "pricing": "价格口径",
        "problem_goods": "问题产品处理方式",
        "target_node": "最终状态",
        "general": "待确认信息",
    }
    result["pending_fields"] = {
        field_name: {
            "label": labels[field_name],
            "question": str(question),
        }
    }
    return result


def _count_value(value: str) -> int:
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    if not text or any(char not in _CHINESE_DIGITS and char not in {"十", "百"} for char in text):
        raise ValueError("数量必须是正整数")
    total = 0
    current = 0
    for char in text:
        if char in _CHINESE_DIGITS:
            current = _CHINESE_DIGITS[char]
        elif char == "十":
            total += (current or 1) * 10
            current = 0
        elif char == "百":
            total += (current or 1) * 100
            current = 0
    result = total + current
    if result <= 0:
        raise ValueError("数量必须是正整数")
    return result


def _explicit_count_intent(source_text: str) -> tuple[Dict[str, Any], str]:
    text = _compact_semantic_text(source_text)
    if not text:
        return {}, ""
    result: Dict[str, Any] = {"evidence": {}}
    direct_quantity_matches = list(re.finditer(
        rf"(?:每(?:个|种|款)(?:商品|货品|sku)?|每(?:一)?番(?:商品|货品)?)(?:的)?(?:购买)?(?:数量)?"
        rf"(?:都)?(?:给我)?(?:放|买|是|为|=|:)?({_COUNT_TOKEN})(?:件|个|份)",
        text,
        re.IGNORECASE,
    ))
    direct_quantity_values = {_count_value(match.group(1)) for match in direct_quantity_matches}
    if len(direct_quantity_values) > 1:
        return {}, "同一每种商品数量出现多个冲突值，请确认最终购买数量。"
    quantity_match = direct_quantity_matches[0] if direct_quantity_matches else re.search(
        rf"(?:每(?:个|种|款|件)?(?:商品|货品|sku)|每(?:一)?番(?:商品|货品)?(?:的)?|{_COUNT_TOKEN}番(?:商品|货品)|每(?:个|种)?数量)"
        rf"(?:购买)?(?:数量|买)?(?:都)?(?:给我)?(?:放|买|是|为|=|:)?({_COUNT_TOKEN})(?:件|个|份)?(?:数量)?",
        text,
        re.IGNORECASE,
    )
    if quantity_match:
        result["quantity_per_item"] = _count_value(quantity_match.group(1))
        result["evidence"]["quantity"] = quantity_match.group(0)

    shop_match = re.search(rf"({_COUNT_TOKEN})(?:个)?(?:店铺|店)", text, re.IGNORECASE)
    if shop_match:
        result["shop_count"] = _count_value(shop_match.group(1))
        result["evidence"]["shop_count"] = shop_match.group(0)

    per_shop_match = re.search(
        rf"(?:每(?:个)?店(?:铺)?|店铺各|各店(?:铺)?)(?:有|包含|要求)?({_COUNT_TOKEN})(?:个|种|款|件)?(?:商品|货品|sku)",
        text,
        re.IGNORECASE,
    )
    if per_shop_match:
        result["items_per_shop"] = _count_value(per_shop_match.group(1))
        result["evidence"]["items_per_shop"] = per_shop_match.group(0)

    total_item_match = None
    for candidate in re.finditer(
        rf"(?:共|一共|总共|要求|包含|创建|有)?({_COUNT_TOKEN})(?:个|种|款|件|番)(?:商品|货品|sku)",
        text,
        re.IGNORECASE,
    ):
        if candidate.start() > 0 and text[candidate.start() - 1] == "第":
            continue
        if per_shop_match and candidate.start() >= per_shop_match.start() and candidate.end() <= per_shop_match.end():
            continue
        total_item_match = candidate
        break
    if total_item_match:
        result["total_items"] = _count_value(total_item_match.group(1))
        result["evidence"]["item_count"] = total_item_match.group(0)

    shops = result.get("shop_count")
    per_shop = result.get("items_per_shop")
    total_items = result.get("total_items")
    if shops and per_shop and total_items and shops * per_shop != total_items:
        return {}, f"同时识别到{shops}个店铺、每店{per_shop}个商品和总共{total_items}个商品，数量相互矛盾，请确认。"
    if shops and total_items and not per_shop:
        if total_items % shops:
            return {}, f"{total_items}个商品无法平均分配到{shops}个店铺，请补充每个店铺的商品数。"
        result["items_per_shop"] = total_items // shops
    elif total_items and not shops:
        result["shop_count"] = 1
        result["items_per_shop"] = total_items
    return result, ""


def _explicit_target_intent(source_text: str) -> tuple[str, str, str]:
    text = _compact_semantic_text(source_text)
    if not text:
        return "", "", ""
    porder_paid_match = re.search(r"配送单.{0,8}(?:支付完成|已支付|已付款|付款完成)", text)
    porder_offered_match = re.search(r"配送单.{0,8}(?:报价(?:完成)?|已报价)", text)
    delivery_created_match = re.search(r"(?:配送单(?:提出|已提出)|提出配送单)", text)
    shelf_match = re.search(r"(?:上架入库|上架|入库)", text)
    pending_match = re.search(r"(?:待拍下|待拍单)", text)
    purchase_match = re.search(r"(?:采购|交易号|财务).{0,8}(?:待付款|待支付|付款)|待财务付款", text)
    waiting_match = None if purchase_match else re.search(
        r"订单.{0,8}(?:待付款|待支付)|待付款|待支付|付款前|付钱之前|等付款|报价完(?:就行|成)?",
        text,
    )
    paid_match = None if porder_paid_match else re.search(r"已付款|已支付|支付完成|付款完成|付完(?:钱|款)", text)
    targets: list[tuple[str, str]] = []
    for match, node in (
        (porder_paid_match, "porder_paid"),
        (porder_offered_match, "porder_offered"),
        (delivery_created_match, "warehouse_delivery_created"),
        (shelf_match, "shelf_stored"),
        (pending_match, "pending_purchase"),
        (purchase_match, "purchase_wait_pay"),
        (waiting_match, "order_offered"),
        (paid_match, "order_paid"),
    ):
        if match:
            targets.append((node, match.group(0)))
    unique = {item[0] for item in targets}
    if len(unique) > 1:
        return "", "", "同时出现多个冲突目标，请确认最终要停在哪个状态。"
    if not targets:
        return "", "", ""
    return targets[0][0], targets[0][1], ""


def _model_evidenced_count(
    raw_goal: Dict[str, Any],
    source_text: str,
    variable_name: str,
    evidence_name: str,
) -> tuple[int | None, str]:
    intent = raw_goal.get("intent") if isinstance(raw_goal.get("intent"), dict) else {}
    variables = raw_goal.get("variables") if isinstance(raw_goal.get("variables"), dict) else {}
    evidence = str(intent.get(evidence_name) or "").strip()
    value = variables.get(variable_name)
    if not evidence or value in (None, ""):
        return None, ""
    if _compact_semantic_text(evidence) not in _compact_semantic_text(source_text):
        return None, ""
    return _positive_int(value, variable_name), evidence


def _quantity_value_from_evidence(evidence: str) -> int | None:
    match = re.search(
        rf"(?:购买数量|数量|买|放)(?:都|给我|是|为|=|:)*({_COUNT_TOKEN})(?:件|个|份)?",
        _compact_semantic_text(evidence),
        re.IGNORECASE,
    )
    return _count_value(match.group(1)) if match else None


def _pricing_from_model_intent(raw_goal: Dict[str, Any], source_text: str) -> Dict[str, Any]:
    intent = raw_goal.get("intent") if isinstance(raw_goal.get("intent"), dict) else {}
    pricing = intent.get("pricing") if isinstance(intent.get("pricing"), dict) else {}
    mode = str(pricing.get("mode") or "").strip().lower()
    if mode not in {"goods_total", "uniform_unit", "per_item_unit", "unspecified", "ambiguous"}:
        return {}
    evidence = str(pricing.get("evidence") or "").strip()
    if source_text:
        if not evidence or _compact_semantic_text(evidence) not in _compact_semantic_text(source_text):
            return {}
    return {
        "mode": mode,
        "amount": pricing.get("amount"),
        "amounts": pricing.get("amounts") if isinstance(pricing.get("amounts"), list) else [],
        "evidence": evidence,
        "source": "model_evidence",
    }


def _explicit_price_intent(
    source_text: str,
    raw_goal: Dict[str, Any],
    raw_variables: Dict[str, Any],
) -> tuple[Dict[str, Any], str]:
    text = _compact_semantic_text(source_text)
    number = r"(\d+(?:\.\d+)?)"
    money_boundary = r"(?=元|块|,|。|；|;|$)"
    if text:
        payable_match = re.search(r"订单(?:应付|实付|支付)总(?:价|额|金额)|应付总额|实付金额|含运费(?:的)?总价", text)
        if payable_match:
            return {}, "订单应付总额包含运费或其他费用，请补充商品金额、运费和其他费用的拆分。"

        list_match = re.search(r"(?:分别(?:报价|单价)?|(?:报价|单价)分别(?:是|为)?|依次(?:报价|单价)?)([^。；;]*)", text)
        list_values = re.findall(r"\d+(?:\.\d+)?", list_match.group(1)) if list_match else []
        total_match = re.search(rf"(?:商品总金额|商品总额|商品总价|商品金额|总金额|总价|合计|一共|总共)(?:是|为|=|:|等于|共计)?{number}{money_boundary}", text)
        if not total_match:
            total_match = re.search(rf"{number}(?:元)?(?:的)?(?:商品总金额|商品总额|商品总价|商品金额|总金额|总价|合计)", text)
        unit_match = re.search(
            rf"(?:商品单价|报价单价|单价|单番(?:的)?(?:单价|价格|报价)|每(?:个|件|番|种|款)(?:商品)?(?:的)?(?:报价|单价|价格|金额)|单件(?:的)?(?:单价|价格|报价))(?:是|为|=|:|等于)?{number}",
            text,
        )
        ambiguous_match = re.search(rf"(?:价格|金额)(?:是|为|=|:)?{number}", text)

        if total_match and unit_match:
            return {}, "同时出现商品总价与单价，请确认仅保留一种价格口径。"
        if unit_match:
            return {
                "mode": "uniform_unit",
                "amount": unit_match.group(1),
                "amounts": [],
                "evidence": unit_match.group(0),
                "source": "deterministic",
            }, ""
        if list_values:
            return {
                "mode": "per_item_unit",
                "amount": "",
                "amounts": list_values,
                "evidence": list_match.group(0),
                "source": "deterministic",
            }, ""
        if total_match:
            intent = {
                "mode": "goods_total",
                "amount": total_match.group(1),
                "amounts": [],
                "evidence": total_match.group(0),
                "source": "deterministic",
            }
            return intent, ""
        if ambiguous_match:
            return {}, "价格金额未说明是商品总价还是每件单价，请明确价格口径。"

    model_intent = _pricing_from_model_intent(raw_goal, source_text)
    if model_intent:
        if model_intent["mode"] == "ambiguous":
            return {}, "价格金额未说明是商品总价还是每件单价，请明确价格口径。"
        if model_intent["mode"] != "unspecified":
            return model_intent, ""
    if raw_variables.get("offer_unit_prices") not in (None, "", []):
        return {
            "mode": "per_item_unit",
            "amount": "",
            "amounts": raw_variables.get("offer_unit_prices"),
            "evidence": "DeepSeek结构化逐商品报价",
            "source": "legacy_model",
        }, ""
    if raw_variables.get("offer_price") not in (None, ""):
        raw_price = raw_variables.get("offer_price")
        if _decimal_value(raw_price, "offer_price") == "0" and not re.search(r"(?:单价|价格|报价).*(?:0|零)", source_text):
            return {}, "订单单价为0，请确认报价金额。如果用户已指定商品总价，请重新说明。"
        return {
            "mode": "uniform_unit",
            "amount": raw_variables.get("offer_price"),
            "amounts": [],
            "evidence": "DeepSeek结构化统一单价",
            "source": "legacy_model",
        }, ""
    return {"mode": "default_unit", "amount": DEFAULT_VARIABLES["offer_price"], "amounts": [], "evidence": "", "source": "default"}, ""


def _money_cents(value: Any, field_name: str) -> int:
    decimal_value = Decimal(_decimal_value(value, field_name))
    cents = decimal_value * Decimal("100")
    if cents != cents.to_integral_value():
        raise ValueError(f"{field_name}最多支持两位小数")
    return int(cents)


def _cents_text(value: int) -> str:
    return format((Decimal(value) / Decimal("100")).normalize(), "f")


def _compile_price_intent(
    price_intent: Dict[str, Any],
    variables: Dict[str, Any],
    item_count: int,
    quantity: int,
) -> tuple[Dict[str, Any], str]:
    mode = str(price_intent.get("mode") or "default_unit")
    effective_prices: list[str]
    requested_total = ""
    if mode == "goods_total":
        try:
            total_cents = _money_cents(price_intent.get("amount"), "商品总价")
        except ValueError as exc:
            return {}, str(exc)
        if total_cents % quantity:
            return {}, f"商品总价{_cents_text(total_cents)}元无法按每种数量{quantity}精确分摊到分，请调整总价或购买数量。"
        per_line_unit_cents, remainder = divmod(total_cents // quantity, item_count)
        effective_prices = [
            _cents_text(per_line_unit_cents + (1 if index < remainder else 0))
            for index in range(item_count)
        ]
        declared = price_intent.get("declared_unit_prices") or []
        if declared:
            try:
                declared_prices = [_decimal_value(item, "声明单价") for item in declared]
            except ValueError as exc:
                return {}, str(exc)
            if len(declared_prices) == 1:
                declared_prices *= item_count
            if declared_prices != effective_prices:
                return {}, f"声明的商品总价与单价不一致：按总价应为{effective_prices}，请确认。"
        requested_total = _cents_text(total_cents)
    elif mode in {"uniform_unit", "default_unit"}:
        try:
            unit_price = _decimal_value(price_intent.get("amount"), "商品单价")
        except ValueError as exc:
            return {}, str(exc)
        effective_prices = [unit_price] * item_count
    elif mode == "per_item_unit":
        try:
            values = _price_list(price_intent.get("amounts"))
        except ValueError as exc:
            return {}, str(exc)
        if len(values) == 1:
            effective_prices = values * item_count
        elif len(values) == item_count:
            effective_prices = values
        else:
            return {}, f"当前订单共{item_count}个商品，但识别到{len(values)}个逐商品单价，请补充为1个统一单价或{item_count}个单价。"
    else:
        return {}, "价格金额未说明是商品总价还是每件单价，请明确价格口径。"

    if len(set(effective_prices)) == 1:
        variables["offer_price"] = effective_prices[0]
        variables.pop("offer_unit_prices", None)
    else:
        variables["offer_unit_prices"] = effective_prices
        variables.pop("offer_price", None)
    actual_total = sum(Decimal(price) * quantity for price in effective_prices)
    return {
        "mode": mode,
        "mode_label": {
            "goods_total": "商品金额合计",
            "uniform_unit": "统一商品单价",
            "per_item_unit": "逐商品单价",
            "default_unit": "默认商品单价",
        }.get(mode, mode),
        "requested_goods_total": requested_total,
        "effective_unit_prices": effective_prices,
        "effective_goods_total": format(actual_total.normalize(), "f"),
        "includes_fees": False,
        "evidence": str(price_intent.get("evidence") or ""),
    }, ""


def _explicit_customer_ids(source_text: str) -> tuple[list[str], str]:
    text = _compact_semantic_text(source_text)
    if not text:
        return [], ""
    matches = re.findall(r"(?:客户|用户)(?:id)?(?:是|为|=|:)?(\d{4,})|执行id(?:是|为|=|:)?(\d{6,})", text, re.IGNORECASE)
    values: list[str] = []
    for left, right in matches:
        value = left or right
        if value and value not in values:
            values.append(value)
    evidence = "、".join(f"ID{value}" for value in values)
    return values, evidence


def _explicit_order_sn(source_text: str) -> str:
    match = re.search(r"(?<!\d)\d{14,}-\d{4,}(?!\d)", str(source_text or ""))
    return match.group(0) if match else ""


def _problem_goods_intent(source_text: str) -> tuple[Dict[str, Any], str]:
    text = _compact_semantic_text(source_text)
    marker = re.search(
        r"(?:问题产品|问题商品|(?:全部|所有|全)(?:商品)?(?:金额|数量).{0,20}(?:退|退款))",
        text,
    )
    if not marker:
        return {}, ""
    clause_start = max(0, text.rfind("然后", 0, marker.start()))
    evidence = text[clause_start :][:500]
    listed_all = bool(
        re.search(
            r"(?:商品金额|商品数量|商品|两番(?:商品)?(?:金额|数量)?|数量).{0,40}(?:国内运费|运费).{0,40}(?:option|附加服务).{0,12}(?:全退|都退|全部退(?:光)?|清零)",
            evidence,
            re.IGNORECASE,
        )
    )
    quantity_candidates: list[tuple[int, str, int | None]] = []
    if listed_all:
        quantity_candidates.append((0, "all", None))
    for match in re.finditer(
        r"(?:所有|全部|全)(?:商品)?(?:金额|数量).{0,20}(?:退|退款)|数量.{0,8}(?:全部|全|都)(?:给)?退|(?:问题产品|商品)?数量(?:(?:改|变)(?:成|为)?|成|为|=|:)?0",
        evidence,
    ):
        quantity_candidates.append((match.start(), "all", None))
    for match in re.finditer(r"(?:一半数量|数量.{0,5}一半|退一半)", evidence):
        quantity_candidates.append((match.start(), "half", None))
    for match in re.finditer(r"(?:退|退款)(?:掉)?(\d+)(?:个|件|份)?(?:数量|商品)?", evidence):
        quantity_candidates.append((match.start(), "fixed", int(match.group(1))))
    for match in re.finditer(r"(?:商品)?数量.{0,4}(?:保留|不退|不变)", evidence):
        quantity_candidates.append((match.start(), "keep", None))
    latest_quantity = max(quantity_candidates, key=lambda item: item[0]) if quantity_candidates else (-1, "", None)
    quantity_mode = latest_quantity[1]
    quantity_value = latest_quantity[2]

    freight_keep_matches = list(re.finditer(r"(?:国内运费|运费).{0,3}(?:保留|不退|不变)", evidence))
    freight_all_matches = list(
        re.finditer(
            r"(?:国内运费|运费).{0,8}(?:全部|全|都)?(?:给)?退|(?:全部|全|都)退.{0,8}(?:国内运费|运费)|(?:退|退款).{0,15}(?:全部|全)(?:国内运费|运费)|(?:只)?退.{0,5}(?:国内运费|运费)|(?:国内运费|运费)(?:(?:改|变)(?:成|为)?|成|为|=|:)?0",
            evidence,
        )
    )
    latest_keep = freight_keep_matches[-1].start() if freight_keep_matches else -1
    latest_all = freight_all_matches[-1].start() if freight_all_matches else (-1 if not listed_all else 0)
    freight_mode = "all" if latest_all > latest_keep else "keep"

    option_mode = "all" if listed_all or re.search(
        r"(?:option|附加服务).{0,12}(?:全退|都退|全部退(?:光)?|清零|(?:(?:改|变)(?:成|为)?|成|为|=|:)?0)",
        evidence,
        re.IGNORECASE,
    ) else "keep"

    # --- 价格调整检测 ---
    price_adjustment_mode = "keep"
    price_adjustment_value = None
    price_zero = re.search(
        r"(?:单价|报价|价格|offer.?price)\s*(?:改成|改为|调整为|变成|是|为|=|:)\s*0",
        evidence, re.IGNORECASE,
    )
    price_fixed = re.search(
        r"(?:单价|报价|价格|offer.?price)\s*(?:改成|改为|调整为|变成|是|为|=|:)\s*(\d+(?:\.\d+)?)",
        evidence, re.IGNORECASE,
    )
    if price_zero:
        price_adjustment_mode = "zero"
        if not quantity_mode:
            quantity_mode = "keep"  # 只改单价时数量保持不变
    elif price_fixed:
        price_adjustment_mode = "fixed"
        price_adjustment_value = price_fixed.group(1)
        if not quantity_mode:
            quantity_mode = "keep"

    return {
        "type": "problem_goods",
        "action": "create_and_process",
        "scope": "all_candidates" if re.search(r"所有商品|全部商品|全商品|这些商品|这所有|(?:提出|提)两次问题产品|(?:给)?两番(?:都)?.{0,20}(?:问题产品|全退|都退|全部退|清零)", evidence) else "single_or_all_if_one",
        "problem_type": 8,
        "problem_type_label": "其他",
        "quantity_refund_mode": quantity_mode or "keep",
        "quantity_refund_value": quantity_value,
        "freight_refund_mode": freight_mode,
        "option_refund_mode": option_mode,
        "price_adjustment_mode": price_adjustment_mode,
        "price_adjustment_value": price_adjustment_value,
        "evidence": evidence,
    }, ""


def _explicit_order_option_intent(source_text: str) -> Dict[str, Any]:
    text = _compact_semantic_text(source_text)
    cancelled = re.search(r"((?:不要|不需要|取消|别)(?:再)?(?:添加|加)?(?:option|附加服务)|(?:option|附加服务)(?:不要|不需要|取消|不添加))", text, re.IGNORECASE)
    if cancelled:
        return {
            "enabled": False,
            "mode": "none",
            "count": 0,
            "names": [],
            "evidence": cancelled.group(1),
        }
    match = re.search(
        r"((?:每番|每个商品)?(?:都)?(?:随机|随便|任意)(?:添加|加)?(\d+)个(?:option|附加服务))",
        text,
        re.IGNORECASE,
    )
    if not match:
        return {}
    return {
        "enabled": True,
        "mode": "random",
        "count": int(match.group(2)),
        "names": [],
        "evidence": match.group(1),
    }


def _raw_unhandled_requests(raw_goal: Dict[str, Any]) -> list[str]:
    raw = raw_goal.get("unhandled_requests") or []
    if not isinstance(raw, list):
        raw = [raw]
    return [str(item).strip() for item in raw if str(item).strip()]


def _problem_request_is_covered(value: str, evidence_values: list[str]) -> bool:
    remaining = _compact_semantic_text(value)
    remaining = re.sub(
        r"(?:option|附加服务).{0,12}(?:全退|都退|全部退(?:光)?|清零|(?:(?:改|变)(?:成|为)?|成|为|=|:)?0)",
        "",
        remaining,
        flags=re.IGNORECASE,
    )
    for evidence in sorted(
        {_compact_semantic_text(item) for item in evidence_values if _compact_semantic_text(item)},
        key=len,
        reverse=True,
    ):
        remaining = remaining.replace(evidence, "")
    supported_problem_patterns = (
        r"(?:一半数量|数量.{0,5}一半|退一半)",
        r"(?:退|退款)(?:掉)?\d+(?:个|件|份)?(?:数量|商品)?",
        r"(?:商品)?数量.{0,4}(?:保留|不退|不变)",
        r"(?:国内运费|运费).{0,3}(?:保留|不退|不变)",
        r"(?:所有|全部|全)(?:商品)?(?:金额|数量).{0,20}(?:退|退款)",
        r"数量.{0,8}(?:全部|全|都)(?:给)?退",
        r"(?:国内运费|运费).{0,8}(?:全部|全|都)?(?:给)?退",
        r"(?:全部|全|都)退.{0,8}(?:国内运费|运费)",
        r"(?:退|退款).{0,15}(?:全部|全)(?:国内运费|运费)",
        r"(?:只)?退.{0,5}(?:国内运费|运费)",
    )
    for pattern in supported_problem_patterns:
        remaining = re.sub(pattern, "", remaining)
    remaining = re.sub(r"问题产品|问题商品", "", remaining)
    remaining = re.sub(
        r"(?:然后|之后|后|并且|并|同时|再|把|这些|这个|和|与|、|也|都|,|。|；|;)",
        "",
        remaining,
    )
    return not remaining


def _price_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        raw = [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
    elif isinstance(value, list):
        raw = value
    else:
        raw = [value]
    return [_decimal_value(item, "逐商品报价") for item in raw]


def _target_node(value: Any) -> str:
    text = str(value or "").strip()
    if text in FULL_FLOW_NODE_LABELS:
        return text
    if text in NODE_ALIASES:
        return NODE_ALIASES[text]
    for alias, node in NODE_ALIASES.items():
        if alias in text:
            return node
    return ""


def _customer_ids(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else ([value] if value not in (None, "") else [])
    result: list[str] = []
    for item in raw:
        for part in str(item).replace("，", ",").split(","):
            customer_id = part.strip()
            if not customer_id:
                continue
            if not customer_id.isdigit():
                raise ValueError("客户ID只能是数字")
            result.append(customer_id)
    return result


def _numeric_context_customer_ids(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        for part in str(item or "").replace("，", ",").split(","):
            customer_id = part.strip()
            if customer_id.isdigit() and customer_id not in result:
                result.append(customer_id)
    return result


def build_agent_compile_context(
    db: Session,
    project_id: int,
    topbar_customer_ids: list[str] | None,
) -> Dict[str, Any]:
    page_ids: list[str] = []
    for value in topbar_customer_ids or []:
        customer_id = str(value).strip()
        if not customer_id.isdigit():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"客户ID只能是数字：{customer_id}",
            )
        if customer_id not in page_ids:
            page_ids.append(customer_id)

    bound_ids: list[str] = []
    profile = default_account_profile_for_target(db, "project", int(project_id), int(project_id))
    if profile is not None and profile.status == "active":
        variables, _ = account_profile_variables(db, int(profile.id), int(project_id))
        for key in ("customer_ids", "customer_id"):
            for customer_id in _numeric_context_customer_ids(variables.get(key)):
                if customer_id not in bound_ids:
                    bound_ids.append(customer_id)

    return {"topbar_customer_ids": page_ids, "bound_customer_ids": bound_ids}


def _normalize_goal(
    payload: Any,
    messages: list[Dict[str, str]] | None = None,
    force_ready: bool = False,
    compile_context: Dict[str, Any] | None = None,
) -> tuple[str, Dict[str, Any], str]:
    if not isinstance(payload, dict):
        raise ValueError("DeepSeek未返回合法目标JSON")
    top_allowed = {"status", "question", "goal", "reason"}
    unknown_top = sorted(set(payload) - top_allowed)
    if unknown_top:
        raise ValueError(f"DeepSeek返回了未允许字段：{', '.join(unknown_top)}")
    raw_goal = payload.get("goal")
    if not isinstance(raw_goal, dict):
        raw_goal = {}
    unknown_goal = sorted(set(raw_goal) - ALLOWED_GOAL_KEYS)
    if unknown_goal:
        raise ValueError(f"目标包含未允许字段：{', '.join(unknown_goal)}")
    raw_variables = dict(raw_goal.get("variables")) if isinstance(raw_goal.get("variables"), dict) else {}
    for key in IGNORED_MODEL_VARIABLE_KEYS:
        raw_variables.pop(key, None)
    unknown_variables = sorted(set(raw_variables) - ALLOWED_VARIABLE_KEYS)
    if unknown_variables:
        raise ValueError(f"目标包含未注册变量：{', '.join(unknown_variables)}")

    requested_status = str(payload.get("status") or "ready").strip().lower()
    question = str(payload.get("question") or "").strip()
    source_text = _source_text(messages)
    conversation_intent: Dict[str, Any] = {}
    for message in messages or []:
        if isinstance(message, dict) and str(message.get("content") or "").strip():
            conversation_intent = _reduce_intent_state(
                conversation_intent,
                str(message.get("content") or ""),
            )
    resolved_fields = conversation_intent.get("resolved_fields") or {}
    deterministic_problem_fields = read_deterministic_problem_fields(resolved_fields)
    corrections: list[Dict[str, Any]] = []
    evidence: Dict[str, str] = {}

    problem_operation, problem_question = _problem_goods_intent(source_text)
    if problem_question:
        if force_ready:
            problem_operation = {}
        else:
            return "clarifying", {}, problem_question
    if problem_operation:
        problem_scope = str(deterministic_problem_fields.get("problem_scope") or "")
        if problem_scope == "all":
            problem_operation["scope"] = "all_candidates"
        elif problem_scope == "item":
            problem_operation["scope"] = "selected_item"
            problem_operation["item_index"] = deterministic_problem_fields.get("item_index")
        if deterministic_problem_fields.get("problem_refund_quantity") == "all":
            problem_operation["quantity_refund_mode"] = "all"
            problem_operation["quantity_refund_value"] = None
        if deterministic_problem_fields.get("problem_refund_freight") == "all":
            problem_operation["freight_refund_mode"] = "all"
        if deterministic_problem_fields.get("problem_preserve_price") is True:
            problem_operation["price_adjustment_mode"] = "keep"
            problem_operation["price_adjustment_value"] = None
    order_options = _explicit_order_option_intent(source_text)

    unhandled = _raw_unhandled_requests(raw_goal)
    ignored = [
        str(item).strip()
        for item in (raw_goal.get("assumptions") or [])
        if re.search(r"忽略|未支持|无法执行", str(item))
    ]
    if problem_operation:
        problem_evidence = list((deterministic_problem_fields.get("evidence") or {}).values())
        latest_pricing_field = resolved_fields.get("pricing") if isinstance(resolved_fields, dict) else None
        if isinstance(latest_pricing_field, dict):
            problem_evidence.append(str(latest_pricing_field.get("evidence") or ""))
        unhandled = [
            item for item in unhandled
            if not _problem_request_is_covered(item, problem_evidence)
        ]
        ignored = [
            item for item in ignored
            if not _problem_request_is_covered(item, problem_evidence)
        ]
    if order_options:
        supported_option_words = re.compile(r"option|附加服务", re.IGNORECASE)
        unhandled = [item for item in unhandled if not supported_option_words.search(item)]
        ignored = [item for item in ignored if not supported_option_words.search(item)]
    stop_constraint_words = re.compile(
        r"(?:别|不要|不需要|无需|不)(?:再)?(?:支付|付)(?:采购款|采购货款|交易号款)|(?:采购款|采购货款)(?:别|不要|不需要|无需|不)(?:支付|付)",
    )
    unhandled = [item for item in unhandled if not stop_constraint_words.search(item)]
    ignored = [item for item in ignored if not stop_constraint_words.search(item)]
    deterministic_order_sn = _explicit_order_sn(source_text)
    deterministic_target, _, deterministic_target_question = _explicit_target_intent(source_text)
    if deterministic_order_sn and deterministic_target and not deterministic_target_question:
        generic_parse_failure = re.compile(r"^(?:无法|不能|未能)(?:解析|理解)(?:用户)?(?:消息|输入|需求|指令)$")
        covered_constraint = re.compile(r"^(?:确认一下(?:就行)?|(?:商品数量、)?每个购买数量和价格都保持原样|其他数据不要改|保持(?:原样|原值)|不要(?:修改|改))$")

        def is_covered_resume_note(item: str) -> bool:
            quoted = re.search(r"用户要求[“\"]([^”\"]+)[”\"]", item)
            request_text = _compact_semantic_text(quoted.group(1) if quoted else item).strip("。.")
            return bool(covered_constraint.fullmatch(request_text))

        unhandled = [
            item for item in unhandled
            if not generic_parse_failure.fullmatch(item) and not is_covered_resume_note(item)
        ]
    if (unhandled or ignored) and not force_ready:
        missing = "；".join(unhandled or ignored)
        return "clarifying", {}, f"还有要求没有进入执行合同：{missing}。请确认如何处理，当前不会执行任何业务操作。"

    explicit_sn = deterministic_order_sn
    order_sn = str(raw_goal.get("order_sn") or "").strip()
    if explicit_sn:
        if order_sn and order_sn != explicit_sn:
            corrections.append({"field": "order_sn", "before": order_sn, "after": explicit_sn, "reason": "使用用户原文订单号"})
        order_sn = explicit_sn
    elif source_text and order_sn and order_sn not in source_text:
        corrections.append({"field": "order_sn", "before": order_sn, "after": "", "reason": "模型订单号在原文中没有证据"})
        order_sn = ""
    porder_sn = str(raw_goal.get("porder_sn") or "").strip()
    raw_mode = str(raw_goal.get("mode") or "").strip().lower()
    if order_sn and porder_sn:
        return "clarifying", {}, "同时识别到订单号和配送单号，请明确本次从哪一种单号继续。"
    mode = "resume_porder" if porder_sn else "resume_order" if order_sn else "new"
    if mode not in {"new", "resume_order", "resume_porder"}:
        raise ValueError("目标执行模式不受支持")
    if mode == "resume_order" and not order_sn:
        return "clarifying", {}, "请提供需要继续执行的订单号。"
    if mode == "resume_porder" and not porder_sn:
        return "clarifying", {}, "请提供需要继续执行的配送单号。"

    raw_target_node = str(raw_goal.get("target_node") or "").strip()
    target_node = _target_node(raw_target_node)
    invalid_model_target = bool(raw_target_node) and not target_node
    explicit_target, target_evidence, target_question = _explicit_target_intent(source_text)
    latest_target = resolved_fields.get("target_node") if isinstance(resolved_fields, dict) else None
    if isinstance(latest_target, dict) and latest_target.get("value") and not target_question:
        explicit_target = str(latest_target["value"])
        target_evidence = str(latest_target.get("evidence") or "")
        target_question = ""
    if target_question:
        if force_ready:
            explicit_target = explicit_target or "order_offered"
            target_evidence = target_evidence or "智能体自动推断"
        else:
            return "clarifying", {}, target_question
    if explicit_target:
        evidence["target_node"] = target_evidence
        if target_node and target_node != explicit_target:
            corrections.append({
                "field": "target_node",
                "before": target_node,
                "after": explicit_target,
                "reason": f"根据用户原话“{target_evidence}”纠正目标状态",
            })
        target_node = explicit_target
    advance_request = re.search(
        r"(?:继续|推进|做到|走到|到达|进入|停在|一直走到).{0,12}(?:待付款|待支付|已付款|支付完成|待拍下|采购|交易号|财务付款|核查|上架|入库|配送单|全流程)",
        _compact_semantic_text(source_text),
    )
    if problem_operation and order_sn and not advance_request:
        target_node = ""
    target_was_resolved = bool(target_node)
    explicit_customer_ids, customer_evidence = _explicit_customer_ids(source_text)
    if customer_evidence:
        evidence["customer_ids"] = customer_evidence
    contract_defaults = compile_contract_defaults(
        mode=mode,
        target_node=target_node,
        variables=raw_variables,
        explicit_customer_ids=explicit_customer_ids,
        context=compile_context,
    )
    target_node = contract_defaults.target_node
    if invalid_model_target and not target_was_resolved and not force_ready:
        return "clarifying", {}, question or "希望最终把测试数据造到哪个状态？例如：待拍下、上架入库或配送单支付完成。"
    if (
        requested_status == "clarifying"
        and question
        and not problem_operation
        and not target_was_resolved
        and not force_ready
    ):
        return "clarifying", {}, question
    if not target_node and not (problem_operation and order_sn):
        if force_ready:
            target_node = "order_offered"
            target_evidence = "智能体自动推断：默认至订单待付款"
        else:
            return "clarifying", {}, question or "希望最终把测试数据造到哪个状态？例如：待拍下、上架入库或配送单支付完成。"
    if mode == "resume_order" and target_node in {"shopping_cart", "order_created", "full_complete", "porder_paid"}:
        return "clarifying", {}, "该目标节点不适用于订单号续跑，请选择订单报价至配送单报价之间的节点。"
    if mode == "resume_porder" and target_node and target_node not in {
        "warehouse_delivery_created", "porder_translated", "porder_confirmed",
        "porder_wait_offer", "porder_offered", "porder_paid",
    }:
        return "clarifying", {}, "配送单号续跑只能选择配送单阶段的目标节点。"

    variables = dict(DEFAULT_VARIABLES) if mode == "new" else dict(contract_defaults.variables)
    if mode == "new":
        variables.update(contract_defaults.variables)
    count_intent, count_question = _explicit_count_intent(source_text)
    latest_item_count = resolved_fields.get("item_count") if isinstance(resolved_fields, dict) else None
    latest_quantity = resolved_fields.get("quantity_per_item") if isinstance(resolved_fields, dict) else None
    if isinstance(latest_item_count, dict) and latest_item_count.get("value"):
        count_intent["shop_count"] = 1
        count_intent["items_per_shop"] = int(latest_item_count["value"])
        count_intent.setdefault("evidence", {})["item_count"] = str(latest_item_count.get("evidence") or "")
        if "冲突" not in count_question:
            count_question = ""
    if isinstance(latest_quantity, dict) and latest_quantity.get("value"):
        count_intent["quantity_per_item"] = int(latest_quantity["value"])
        count_intent.setdefault("evidence", {})["quantity"] = str(latest_quantity.get("evidence") or "")
    if mode == "new":
        if not count_intent.get("shop_count"):
            variables["order_shop_count"] = DEFAULT_VARIABLES["order_shop_count"]
        if not count_intent.get("items_per_shop"):
            variables["order_per_shop"] = DEFAULT_VARIABLES["order_per_shop"]
    if count_question:
        if force_ready:
            count_intent["shop_count"] = count_intent.get("shop_count") or 1
            count_intent["items_per_shop"] = count_intent.get("items_per_shop") or 1
        else:
            return "clarifying", {}, count_question
    model_quantity, model_quantity_evidence = _model_evidenced_count(
        raw_goal,
        source_text,
        "order_item_num",
        "quantity_evidence",
    )
    declared_model_quantity = _quantity_value_from_evidence(model_quantity_evidence)
    if (
        model_quantity is not None
        and declared_model_quantity is not None
        and model_quantity != declared_model_quantity
        and not count_intent.get("quantity_per_item")
    ):
        return (
            "clarifying",
            {},
            f"原文证据表示每种购买数量{declared_model_quantity}，但模型结果{model_quantity}，请确认后再执行。",
        )
    if not count_intent.get("quantity_per_item") and model_quantity is not None:
        count_intent["quantity_per_item"] = model_quantity
        count_intent.setdefault("evidence", {})["quantity"] = model_quantity_evidence
    evidence.update(count_intent.get("evidence") or {})
    if mode != "new":
        if not count_intent.get("shop_count"):
            variables.pop("order_shop_count", None)
        if not count_intent.get("items_per_shop"):
            variables.pop("order_per_shop", None)
        if not count_intent.get("quantity_per_item"):
            variables.pop("order_item_num", None)
    count_updates = {
        "order_shop_count": count_intent.get("shop_count"),
        "order_per_shop": count_intent.get("items_per_shop"),
        "order_item_num": count_intent.get("quantity_per_item") or (1 if mode == "new" else None),
    }
    for key, value in count_updates.items():
        if value is None:
            continue
        before = variables.get(key)
        variables[key] = value
        if before not in (None, "") and str(before) != str(value):
            corrections.append({
                "field": key,
                "before": before,
                "after": value,
                "reason": "根据用户原话纠正数量" if key in {"order_shop_count", "order_per_shop"} else "根据用户原话或智能体默认纠正每种购买数量",
            })
    if "keyword" in variables or mode == "new":
        variables["keyword"] = _keyword_value(variables.get("keyword"))
    for key in POSITIVE_INT_FIELDS:
        if key in variables and variables[key] not in (None, ""):
            variables[key] = _positive_int(variables[key], key)
    for key in DECIMAL_FIELDS:
        if key in variables and variables[key] not in (None, ""):
            variables[key] = _decimal_value(variables[key], key)
    for key in ("order_payment_mode", "porder_payment_mode"):
        if key not in variables and mode != "new":
            continue
        mode_value = str(variables.get(key) or "balance_first").strip().lower()
        if mode_value in {"bank_payment", "bank"}:
            variables[key] = "bank"
        elif mode_value in {"balance", "balance_first", "余额", "余额优先"}:
            variables[key] = "balance_first"
        else:
            raise ValueError(f"{key} 仅支持balance_first或bank")
    if "finance_confirm" in variables or mode == "new":
        variables["finance_confirm"] = _bool_value(variables.get("finance_confirm"), True)
    if variables.get("order_payment_mode") == "bank":
        variables["finance_confirm"] = True

    expected_items = (
        int(variables["order_shop_count"]) * int(variables["order_per_shop"])
        if variables.get("order_shop_count") and variables.get("order_per_shop")
        else 0
    )
    if problem_operation:
        problem_contract_fields = copy.deepcopy(deterministic_problem_fields)
        operation_scope = str(problem_operation.get("scope") or "")
        operation_item_index = problem_operation.get("item_index")
        if not problem_contract_fields.get("problem_scope"):
            if operation_scope == "selected_item" and isinstance(operation_item_index, int) and operation_item_index > 0:
                problem_contract_fields["problem_scope"] = "item"
                problem_contract_fields["item_index"] = operation_item_index
            elif operation_scope == "all_candidates":
                problem_contract_fields["problem_scope"] = "all"
        has_problem_change = any(
            name in problem_contract_fields
            for name in ("problem_refund_quantity", "problem_refund_freight")
        ) or any(
            str(problem_operation.get(name) or "keep") != "keep"
            for name in ("quantity_refund_mode", "freight_refund_mode", "price_adjustment_mode")
        )
        problem_contract_question = problem_goods_clarification(
            problem_requested=True,
            problem_fields=problem_contract_fields,
            item_count=expected_items or None,
            existing_order=mode != "new",
            has_explicit_change=has_problem_change,
        )
        if problem_contract_question and not force_ready:
            return "clarifying", {}, problem_contract_question
    price_source, price_question = _explicit_price_intent(source_text, raw_goal, raw_variables)
    latest_pricing = resolved_fields.get("pricing") if isinstance(resolved_fields, dict) else None
    if not price_question and isinstance(latest_pricing, dict) and isinstance(latest_pricing.get("value"), dict):
        price_source = {
            **copy.deepcopy(latest_pricing["value"]),
            "evidence": str(latest_pricing.get("evidence") or ""),
            "source": "latest_message",
        }
        price_question = (
            "价格金额未说明是商品总价还是每件单价，请明确总价还是每件单价。"
            if price_source.get("mode") == "ambiguous"
            else ""
        )
    if price_question and not force_ready:
        return "clarifying", {}, price_question
    if problem_operation and price_source.get("refund_context"):
        variables.pop("offer_price", None)
        variables.pop("offer_unit_prices", None)
        pricing = {
            "mode": "preserve_existing",
            "mode_label": "保持原订单价格",
            "requested_goods_total": "",
            "effective_unit_prices": [],
            "effective_goods_total": "",
            "includes_fees": False,
            "evidence": "",
        }
    elif mode != "new" and price_source.get("source") in {"default", "legacy_model"}:
        variables.pop("offer_price", None)
        variables.pop("offer_unit_prices", None)
        pricing = {
            "mode": "preserve_existing",
            "mode_label": "保持原订单价格",
            "requested_goods_total": "",
            "effective_unit_prices": [],
            "effective_goods_total": "",
            "includes_fees": False,
            "evidence": "",
        }
    elif mode == "resume_order" and price_source.get("mode") == "uniform_unit":
        unit_price = _decimal_value(price_source.get("amount"), "商品单价")
        variables["offer_price"] = unit_price
        variables.pop("offer_unit_prices", None)
        pricing = {
            "mode": "uniform_unit",
            "mode_label": "统一商品单价",
            "requested_goods_total": "",
            "effective_unit_prices": [unit_price],
            "effective_goods_total": "",
            "includes_fees": False,
            "evidence": str(price_source.get("evidence") or ""),
        }
    else:
        if not expected_items or not variables.get("order_item_num"):
            if force_ready:
                variables["order_item_num"] = 1
            else:
                return "clarifying", {}, "续跑订单如需修改价格，请同时明确商品种类数和每种购买数量。"
        pricing, price_question = _compile_price_intent(
            price_source, variables, expected_items, int(variables["order_item_num"])
        )
        if price_question:
            return "clarifying", {}, price_question
    if pricing.get("evidence"):
        evidence["pricing"] = str(pricing["evidence"])
    raw_price = raw_variables.get("offer_unit_prices") or raw_variables.get("offer_price")
    effective_price = variables.get("offer_unit_prices") or variables.get("offer_price")
    if raw_price not in (None, "", []) and raw_price != effective_price:
        corrections.append({"field": "pricing", "before": raw_price, "after": effective_price, "reason": f"按{pricing['mode_label']}编译执行价格"})

    model_customer_ids = _customer_ids(raw_goal.get("customer_ids"))
    customer_ids = contract_defaults.customer_ids
    if model_customer_ids and model_customer_ids != customer_ids:
        corrections.append({"field": "customer_ids", "before": model_customer_ids, "after": customer_ids, "reason": "丢弃用户原文中没有证据的客户ID"})

    defaults_used = list(contract_defaults.defaults_used)
    if mode == "new":
        variables["target_shops"] = variables["order_shop_count"]
        variables["per_shop"] = variables["order_per_shop"]
        variables["auto_fill_cart_on_shortage"] = True
    if target_node:
        variables["stop_after_node"] = target_node
    if order_sn:
        variables["order_sn"] = order_sn
    if porder_sn:
        variables["porder_sn"] = porder_sn
    if customer_ids:
        variables["customer_ids"] = customer_ids
    else:
        variables.pop("customer_ids", None)

    operations: list[Dict[str, Any]] = []
    steps: list[str] = []
    selected_problem_item = (
        problem_operation
        and problem_operation.get("scope") == "selected_item"
        and isinstance(problem_operation.get("item_index"), int)
        and problem_operation["item_index"] > 0
    )
    if (
        problem_operation
        and mode == "new"
        and expected_items > 1
        and problem_operation.get("scope") != "all_candidates"
        and not selected_problem_item
    ):
        if force_ready:
            problem_operation["scope"] = "all_candidates"
        else:
            return "clarifying", {}, f"订单将创建{expected_items}个商品，请明确问题产品处理哪一个，或说明全部商品都处理。"
    if target_node:
        porder_start = FULL_FLOW_NODE_SEQUENCE.index("warehouse_delivery_created")
        operation_type = "advance_porder" if mode == "resume_porder" or FULL_FLOW_NODE_SEQUENCE.index(target_node) >= porder_start else "advance_order"
        operations.append({"id": "operation_1", "type": operation_type, "target_node": target_node, "target_label": FULL_FLOW_NODE_LABELS[target_node], "evidence": target_evidence})
        steps.append(("继续执行至" if mode != "new" else "创建并执行至") + FULL_FLOW_NODE_LABELS[target_node])
    if problem_operation:
        problem_operation = {**problem_operation, "id": f"operation_{len(operations) + 1}", "depends_on": operations[-1]["id"] if operations else ""}
        operations.append(problem_operation)
        steps.append("提出并处理问题产品")
        evidence["problem_goods"] = problem_operation["evidence"]
    if order_options:
        evidence["options"] = str(order_options["evidence"])
    if not operations:
        if force_ready:
            target_node = target_node or "order_offered"
            operation_type = "advance_order"
            operations.append({"id": "operation_1", "type": operation_type, "target_node": target_node, "target_label": FULL_FLOW_NODE_LABELS.get(target_node, target_node), "evidence": "智能体自动推断"})
            steps.append("智能体自动推断执行至" + FULL_FLOW_NODE_LABELS.get(target_node, target_node))
        else:
            return "clarifying", {}, question or "没有识别到可执行的目标操作，请补充希望执行到的状态或业务动作。"

    if mode == "new":
        price_text = "、".join(pricing["effective_unit_prices"])
        pricing_summary = (
            f"商品金额合计{pricing['requested_goods_total']}元（执行单价{price_text}元，运费及其他费用另计）"
            if pricing["mode"] == "goods_total" else f"商品单价{price_text}元"
        )
        summary_parts = [f"{variables['order_shop_count']}个店铺，每店{variables['order_per_shop']}个商品，每种购买数量{variables['order_item_num']}，{pricing_summary}"]
    else:
        summary_parts = [f"继续处理{order_sn or porder_sn}，未明确的数据保持原值"]
    if target_node:
        summary_parts.append(f"目标{FULL_FLOW_NODE_LABELS[target_node]}")
    if problem_operation:
        quantity_label = {"all": "退全部数量", "half": "退一半数量", "fixed": f"退{problem_operation.get('quantity_refund_value')}件", "keep": "数量保持不变"}[problem_operation["quantity_refund_mode"]]
        freight_label = "退全部国内运费" if problem_operation["freight_refund_mode"] == "all" else "国内运费保持不变"
        option_label = "退全部附加服务金额" if problem_operation["option_refund_mode"] == "all" else "附加服务保持不变"
        price_mode = str(problem_operation.get("price_adjustment_mode") or "keep")
        if price_mode == "zero":
            price_label = "单价改为0"
        elif price_mode == "fixed":
            price_label = f"单价改为{problem_operation.get('price_adjustment_value', '?')}元"
        else:
            price_label = "单价保持不变"
        summary_parts.append(f"然后提出问题产品（{quantity_label}，{freight_label}，{option_label}，{price_label}，类型其他）")
    if order_options:
        summary_parts.insert(1, f"每个商品随机添加{order_options['count']}个附加服务")
    summary = "，".join(summary_parts)

    system_assumptions = []
    if not customer_ids and mode == "new":
        system_assumptions.append("未指定客户ID，使用日本站测试项目的默认测试账号")
    if "quantity" not in evidence and mode == "new":
        system_assumptions.append("未指定每种购买数量，使用智能体默认值1")
    if pricing["mode"] == "default_unit":
        system_assumptions.append(f"未指定价格，使用默认商品单价{variables['offer_price']}元")
    if pricing["mode"] == "goods_total":
        system_assumptions.append("商品总价不包含运费和其他费用")
    if problem_operation:
        system_assumptions.append("未指定问题类型，使用现有问题产品页面默认值：其他（8）")
    goal = {
        "mode": mode,
        "target_node": target_node,
        "target_label": FULL_FLOW_NODE_LABELS.get(target_node, ""),
        "customer_ids": customer_ids,
        "customer_scope_label": "、".join(customer_ids) if customer_ids else ("从订单号自动识别" if mode != "new" else "项目默认测试账号"),
        "order_sn": order_sn,
        "porder_sn": porder_sn,
        "variables": variables,
        "operations": operations,
        "options": order_options,
        "unhandled_requests": [],
        "intent": {"source_text": source_text, "evidence": evidence, "pricing": pricing, "corrections": corrections},
        "summary": summary,
        "assumptions": system_assumptions[:20],
        "defaults_used": defaults_used,
        "customer_source": contract_defaults.customer_source,
        "steps": steps,
    }
    goal["contract_hash"] = hashlib.sha256(
        json.dumps(goal, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    if force_ready:
        if not target_node:
            target_node = "order_offered"
            goal["target_node"] = target_node
            goal["target_label"] = FULL_FLOW_NODE_LABELS.get(target_node, "")
            goal["assumptions"].append("追问达上限，智能体自动推断目标为订单待付款")
        requested_status = "ready"
        question = ""
    if requested_status == "clarifying" and question and not problem_operation and not target_node:
        return "clarifying", {}, question
    return "awaiting_confirmation", goal, ""


def _analyze_turn(
    db: Session,
    messages: list[Dict[str, str]],
    intent_state: Dict[str, Any],
    force_ready: bool = False,
    compile_context: Dict[str, Any] | None = None,
) -> tuple[str, Dict[str, Any], str, Dict[str, Any]]:
    config = _latest_model_config(db)
    try:
        prompt = _analysis_prompt(messages, intent_state)
        if force_ready:
            prompt += "\n\n【强制指令】已多次追问仍未满足所有条件。本轮你必须输出 status=\"ready\"，所有不确定字段使用合理默认值，在 assumptions 中逐一标注你采用的默认值及原因。禁止输出 clarifying。"
        payload = call_local_model_json(config, prompt, timeout=120, system_prompt=SYSTEM_PROMPT)
        if force_ready and isinstance(payload, dict):
            payload["status"] = "ready"
            payload["question"] = ""
        session_status, goal, question = _normalize_goal(
            payload,
            messages,
            force_ready=force_ready,
            compile_context=compile_context,
        )
        trace = {
            "turn_index": max(0, len(messages) - 1),
            "model": str(config.model or ""),
            "message": copy.deepcopy(messages[-1]) if messages else {},
            "model_candidate": sanitize_observation(payload),
            "intent_state": sanitize_observation(intent_state),
            "normalized_intent": sanitize_observation(goal.get("intent") or {}),
            "pending_fields": {
                _clarification_field(question): question
            } if question else {},
        }
        return session_status, goal, question, trace
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"DeepSeek理解命令失败：{exc}") from exc


def _analyze_messages(
    db: Session,
    messages: list[Dict[str, str]],
    compile_context: Dict[str, Any] | None = None,
) -> tuple[str, Dict[str, Any], str]:
    session_status, goal, question, _ = _analyze_turn(
        db,
        messages,
        {},
        compile_context=compile_context,
    )
    return session_status, goal, question


def _raw_goal_from_contract(goal: Dict[str, Any]) -> Dict[str, Any]:
    raw = {
        key: copy.deepcopy(goal.get(key))
        for key in ALLOWED_GOAL_KEYS
        if key in goal
    }
    raw["variables"] = {
        key: copy.deepcopy(value)
        for key, value in dict(goal.get("variables") or {}).items()
        if key in ALLOWED_VARIABLE_KEYS
    }
    raw.pop("summary", None)
    raw.pop("operations", None)
    raw.pop("unhandled_requests", None)
    return raw


def _merge_follow_up_analysis(
    previous_goal: Dict[str, Any],
    session_status: str,
    goal: Dict[str, Any],
    question: str,
    messages: list[Dict[str, str]],
    intent_state: Dict[str, Any],
    compile_context: Dict[str, Any] | None = None,
) -> tuple[str, Dict[str, Any], str]:
    if session_status != "clarifying" or not previous_goal:
        return session_status, goal, question
    resolved = intent_state.get("resolved_fields") if isinstance(intent_state, dict) else {}
    resolved = resolved if isinstance(resolved, dict) else {}
    preserve = bool((resolved.get("preserve_unspecified") or {}).get("value"))
    option_resolved = bool(intent_state.get("options")) and _clarification_field(question) == "options"
    if not preserve and not option_resolved:
        return session_status, goal, question
    payload = {
        "status": "ready",
        "question": "",
        "goal": _raw_goal_from_contract(previous_goal),
    }
    return _normalize_goal(payload, messages, compile_context=compile_context)


def create_agent_session(
    db: Session,
    user_id: int,
    project_id: int,
    env_id: int,
    instruction: str,
    topbar_customer_ids: list[str] | None = None,
) -> Dict[str, Any]:
    validate_agent_context(db, project_id, env_id)
    compile_context = build_agent_compile_context(db, project_id, topbar_customer_ids)
    messages = [{"role": "user", "content": str(instruction or "").strip()}]
    intent_state = _reduce_intent_state({}, messages[0]["content"])
    capability_gap = _unsupported_capability(messages)
    if capability_gap:
        session_status, goal, question = "blocked", {}, ""
        analysis_trace = {
            "turn_index": 0,
            "message": messages[0],
            "capability_gap": capability_gap,
            "intent_state": sanitize_observation(intent_state),
        }
    else:
        session_status, goal, question, analysis_trace = _analyze_turn(
            db, messages, intent_state, compile_context=compile_context,
        )
    intent_state = _update_pending_fields(intent_state, session_status, question)
    session = AgentSessionState(
        id=uuid.uuid4().hex,
        user_id=int(user_id),
        project_id=int(project_id),
        env_id=int(env_id),
        status=session_status,
        messages=messages,
        compile_context=compile_context,
        intent_state=intent_state,
        goal=goal,
        question=question,
        events=[
            _event(
                "capability_gap" if capability_gap else "analysis",
                capability_gap.get("reason") if capability_gap else ("DeepSeek已完成目标理解" if goal else "DeepSeek需要补充关键信息"),
            )
        ],
        result=capability_gap,
    )
    if session_status == "clarifying" and question:
        bounded = _bounded_clarification(session, _clarification_field(question), question)
        if bounded["blocked"]:
            session_status, goal, question, analysis_trace = _analyze_turn(
                db, messages, intent_state, force_ready=True, compile_context=compile_context,
            )
            if session_status == "clarifying":
                goal = goal or {"mode": "new", "target_node": "order_offered", "target_label": "订单待付款", "customer_ids": [], "order_sn": "", "porder_sn": "", "variables": dict(DEFAULT_VARIABLES), "operations": [], "summary": "智能体自动推断：默认单店单品至订单待付款", "assumptions": ["追问次数已达上限，智能体自动推断默认参数"], "steps": ["创建并执行至订单待付款"], "contract_hash": ""}
                session_status = "awaiting_confirmation"
                question = ""
            session.intent_state = _update_pending_fields(intent_state, session_status, question)
            session.status = session_status
            session.goal = goal
            session.question = question
            session.events[0] = _event(
                "analysis",
                "追问次数已达上限，智能体已自动推断默认参数生成执行合同",
            )
        else:
            session.question = bounded["message"]
            session.events[0] = _event(
                "clarification",
                bounded["message"],
                field=_clarification_field(question),
                count=bounded["count"],
            )
    _save_analysis_record(db, session, analysis_trace, session.status, session.question)
    with _STORE_LOCK:
        _cleanup_sessions()
        _SESSIONS[session.id] = session
    return _serialize_session(session)


def add_agent_message(db: Session, session_id: str, user_id: int, message: str) -> Dict[str, Any]:
    session = _session_or_404(session_id, user_id)
    with _STORE_LOCK:
        if session.status not in {"clarifying", "awaiting_confirmation"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前任务状态不允许补充消息")
        session.messages.append({"role": "user", "content": str(message or "").strip()})
        session.intent_state = _reduce_intent_state(session.intent_state, str(message or ""))
        messages = copy.deepcopy(session.messages)
        previous_goal = copy.deepcopy(session.goal)
    capability_gap = _unsupported_capability(messages)
    if capability_gap:
        session_status, goal, question = "blocked", {}, ""
        analysis_trace = {
            "turn_index": len(messages) - 1,
            "message": messages[-1],
            "capability_gap": capability_gap,
            "intent_state": sanitize_observation(session.intent_state),
        }
    else:
        session_status, goal, question, analysis_trace = _analyze_turn(
            db, messages, session.intent_state, compile_context=session.compile_context,
        )
        session_status, goal, question = _merge_follow_up_analysis(
            previous_goal,
            session_status,
            goal,
            question,
            messages,
            session.intent_state,
            session.compile_context,
        )
        analysis_trace["final_status"] = session_status
        analysis_trace["final_intent"] = sanitize_observation(goal.get("intent") or {})
        analysis_trace["pending_fields"] = {
            _clarification_field(question): question
        } if question else {}
    next_intent_state = _update_pending_fields(session.intent_state, session_status, question)
    with _STORE_LOCK:
        if session_status == "clarifying" and question:
            field_name = _clarification_field(question)
            bounded = _bounded_clarification(session, field_name, question)
            if bounded["blocked"]:
                session_status, goal, question, retry_trace = _analyze_turn(
                    db,
                    messages,
                    session.intent_state,
                    force_ready=True,
                    compile_context=session.compile_context,
                )
                session_status, goal, question = _merge_follow_up_analysis(
                    previous_goal,
                    session_status,
                    goal,
                    question,
                    messages,
                    session.intent_state,
                    session.compile_context,
                )
                if session_status == "clarifying":
                    goal = goal or previous_goal or {"mode": "new", "target_node": "order_offered", "target_label": "订单待付款", "customer_ids": [], "order_sn": "", "porder_sn": "", "variables": dict(DEFAULT_VARIABLES), "operations": [], "summary": "智能体自动推断", "assumptions": ["追问次数已达上限"], "steps": [], "contract_hash": ""}
                    session_status = "awaiting_confirmation"
                    question = ""
                analysis_trace = retry_trace
                analysis_trace["final_status"] = session_status
                analysis_trace["force_ready"] = True
            else:
                question = bounded["message"]
        session.status = session_status
        session.intent_state = next_intent_state
        session.goal = goal
        session.question = question
        if session_status != "blocked":
            session.result = capability_gap
        session.plan_version += 1
        session.updated_at = datetime.now()
        session.events.append(
            _event(
                "capability_gap" if capability_gap or session_status == "blocked" else ("clarification" if question else "analysis"),
                capability_gap.get("reason") if capability_gap else (question or ("DeepSeek已根据补充信息更新目标" if goal else "仍需补充关键信息")),
                field=_clarification_field(question) if question else "",
                count=session.clarification_counts.get(_clarification_field(question), 0) if question else 0,
            )
        )
    _save_analysis_record(db, session, analysis_trace, session.status, session.question)
    return _serialize_session(session)


def get_agent_session(session_id: str, user_id: int) -> Dict[str, Any]:
    return _serialize_session(_session_or_404(session_id, user_id))


def _agent_action_prompt(goal: Dict[str, Any], events: list[Dict[str, Any]], state: Dict[str, Any]) -> str:
    return build_action_prompt(goal=goal, events=events, state=state)


def _next_agent_action(config: AiConfig, goal: Dict[str, Any], events: list[Dict[str, Any]], state: Dict[str, Any]) -> Dict[str, Any]:
    payload = call_local_model_json(config, _agent_action_prompt(goal, events, state), timeout=120, system_prompt=SYSTEM_PROMPT_ACTION)
    if not isinstance(payload, dict):
        raise ValueError("DeepSeek未返回合法动作JSON")
    action = str(payload.get("action") or "").strip()
    if action not in {"call_tool", "finish", "request_reconfirmation", "report_capability_gap"}:
        raise ValueError("DeepSeek返回了未知动作")
    tool = str(payload.get("tool") or "").strip()
    if action == "call_tool" and tool not in TOOL_SPECS:
        return {
            "action": "report_capability_gap",
            "tool": "",
            "arguments": {},
            "reason": f"DeepSeek选择了未注册工具“{tool[:120]}”，未触发业务调用。",
            "expected": "",
            "suggested_tool": f"评审并注册受控工具：{tool[:120]}",
        }
    return {
        "action": action,
        "tool": tool,
        "arguments": payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {},
        "reason": str(payload.get("reason") or "").strip()[:500],
        "expected": str(payload.get("expected") or "").strip()[:500],
        "suggested_tool": str(payload.get("suggested_tool") or "").strip()[:500],
    }


def _bank_payment_verified(value: Any, identifier_key: str) -> bool:
    if isinstance(value, dict):
        if value.get("payment_type") == "bank" and value.get("finance_passed") is True:
            identifier = str(value.get(identifier_key) or "").strip()
            if identifier and (identifier_key == "porder_sn" or not value.get("porder_sn")):
                return True
        return any(_bank_payment_verified(item, identifier_key) for item in value.values())
    if isinstance(value, list):
        return any(_bank_payment_verified(item, identifier_key) for item in value)
    return False


def _normalized_prices(values: Any) -> list[str]:
    result = []
    for value in values if isinstance(values, list) else []:
        try:
            result.append(format(Decimal(str(value)).normalize(), "f"))
        except (InvalidOperation, TypeError, ValueError):
            result.append(str(value))
    return result


def _order_option_key(value: Dict[str, Any]) -> str:
    for key in ("key", "id", "option_id", "value", "name", "name_translate"):
        candidate = str(value.get(key) or "").strip()
        if candidate:
            return candidate
    return ""


def _order_option_rows(value: Any) -> list[Dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _order_option_contract_check(
    items: list[Dict[str, Any]],
    selected_options: list[Dict[str, Any]],
) -> tuple[bool, list[Dict[str, Any]]]:
    expected = sorted({_order_option_key(item) for item in selected_options if _order_option_key(item)})
    detail: list[Dict[str, Any]] = []
    for index, item in enumerate(items):
        actual = sorted(
            {
                _order_option_key(option)
                for option in _order_option_rows(item.get("options"))
                if option.get("checked") is not False and _problem_quantity(option.get("num") or 1) != 0
            }
            - {""}
        )
        detail.append(
            {
                "item_index": index + 1,
                "expected": expected,
                "actual": actual,
                "missing": sorted(set(expected) - set(actual)),
                "unexpected": sorted(set(actual) - set(expected)),
            }
        )
    passed = bool(items) and bool(expected) and all(not row["missing"] and not row["unexpected"] for row in detail)
    return passed, detail


def _problem_quantity(value: Any) -> int:
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return -1


def _verify_goal(context: AgentToolContext, last_result: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
    goal = context.goal
    target = str(goal.get("target_node") or "")
    summary = last_result.get("summary") if isinstance(last_result.get("summary"), dict) else {}
    current_node = str(summary.get("current_node") or summary.get("stopped_after_node") or "")
    verification: Dict[str, Any] = {
        "target_node": target,
        "reported_node": current_node,
        "target_label": FULL_FLOW_NODE_LABELS.get(target, target),
    }
    target_index = FULL_FLOW_NODE_SEQUENCE.index(target) if target in FULL_FLOW_NODE_SEQUENCE else -1
    porder_nodes = set(FULL_FLOW_NODE_SEQUENCE[FULL_FLOW_NODE_SEQUENCE.index("warehouse_delivery_created") :])
    inspect_result: Dict[str, Any] | None = None

    if target == "shopping_cart":
        cart = summary.get("agent_cart_evidence") if isinstance(summary.get("agent_cart_evidence"), dict) else summary
        expected_shops = int(goal["variables"].get("order_shop_count", 1))
        expected_per_shop = int(goal["variables"].get("order_per_shop", 2))
        expected_items = expected_shops * expected_per_shop
        actual_items = cart.get("verified_added_total")
        if actual_items in (None, ""):
            actual_items = cart.get("added_total")
        cart_ok = (
            cart.get("target_shops") == expected_shops
            and cart.get("per_shop") == expected_per_shop
            and int(cart.get("ready_shops") or 0) >= expected_shops
            and int(actual_items or 0) >= expected_items
        )
        verification["cart"] = sanitize_observation(cart)
        if not cart_ok:
            verification["reason"] = "未从购物车查询结果确认目标店铺数和商品数"
            return False, verification

    order_sn = str(context.state.get("order_sn") or "").strip()
    requires_order = target_index >= FULL_FLOW_NODE_SEQUENCE.index("order_created")
    if requires_order and not order_sn and goal.get("mode") != "resume_porder":
        verification["reason"] = "未获得可查询的订单号"
        return False, verification
    if order_sn:
        inspect_result = execute_agent_tool("inspect_order_state", context, {})
        verification["order_inspection"] = inspect_result.get("summary")
        inspected = inspect_result.get("_verification") if isinstance(inspect_result.get("_verification"), dict) else {}
        inspected_node = str(inspected.get("detected_start_node") or "")
        current_node = inspected_node or current_node
        evidence = goal.get("intent", {}).get("evidence", {}) if isinstance(goal.get("intent"), dict) else {}
        verify_shape = goal.get("mode") == "new" or any(key in evidence for key in ("item_count", "shop_count", "items_per_shop", "quantity"))
        expected_items = 0
        if verify_shape:
            expected_items = int(goal["variables"].get("order_shop_count", 1)) * int(goal["variables"].get("order_per_shop", 1))
            if inspected.get("item_count") != expected_items:
                cart = summary.get("agent_cart_evidence") if isinstance(summary.get("agent_cart_evidence"), dict) else {}
                cart_items = cart.get("verified_added_total") if cart.get("verified_added_total") not in (None, "") else cart.get("added_total")
                cart_shape_ok = int(cart_items or 0) >= expected_items and int(cart.get("ready_shops") or 0) >= int(goal["variables"].get("order_shop_count", 1))
                if not cart_shape_ok:
                    verification["reason"] = f"实际商品数{inspected.get('item_count')}与目标{expected_items}不一致"
                    return False, verification
                verification.setdefault("warnings", []).append("订单进入采购中间状态，使用已验证购物车证据校验商品数")
            expected_shops = int(goal["variables"].get("order_shop_count", 1))
            if inspected.get("shop_count") != expected_shops:
                cart = summary.get("agent_cart_evidence") if isinstance(summary.get("agent_cart_evidence"), dict) else {}
                if int(cart.get("ready_shops") or 0) < expected_shops:
                    verification["reason"] = f"实际店铺数{inspected.get('shop_count')}与目标{expected_shops}不一致"
                    return False, verification
            expected_quantity = goal["variables"].get("order_item_num")
            if expected_quantity not in (None, ""):
                actual_quantities = [_problem_quantity(item.get("num")) for item in inspected.get("items", [])]
                if any(value != int(expected_quantity) for value in actual_quantities):
                    quote_evidence = summary.get("agent_quote_evidence") if isinstance(summary.get("agent_quote_evidence"), dict) else {}
                    if not quote_evidence.get("quote_step_passed") or _problem_quantity(quote_evidence.get("submitted_quantity")) != int(expected_quantity):
                        verification["reason"] = f"实际每种购买数量{actual_quantities}与目标{expected_quantity}不一致"
                        return False, verification
                    verification.setdefault("warnings", []).append("订单进入采购中间状态，使用已成功提交的报价数量证据")

            option_goal = goal.get("options") if isinstance(goal.get("options"), dict) else {}
            if option_goal.get("enabled"):
                selected_options = [
                    item for item in context.state.get("selected_order_options") or [] if isinstance(item, dict)
                ]
                options_ok, option_detail = _order_option_contract_check(inspected.get("items", []), selected_options)
                if not options_ok:
                    retry_result = execute_agent_tool("inspect_order_state", context, {})
                    verification["order_options_retry"] = retry_result.get("summary")
                    inspected = retry_result.get("_verification") if isinstance(retry_result.get("_verification"), dict) else inspected
                    options_ok, option_detail = _order_option_contract_check(inspected.get("items", []), selected_options)
                verification["order_options"] = option_detail
                if not options_ok:
                    verification["reason"] = "实际订单商品附加服务与已确认合同不一致"
                    return False, verification

        pricing = goal.get("intent", {}).get("pricing", {}) if isinstance(goal.get("intent"), dict) else {}
        if target_index >= FULL_FLOW_NODE_SEQUENCE.index("order_offered") and pricing.get("mode") != "preserve_existing":
            expected_prices = _normalized_prices(pricing.get("effective_unit_prices"))
            items = inspected.get("items", [])
            actual_prices = _normalized_prices([item.get("offer_price") for item in items])
            if not actual_prices or all(not price for price in actual_prices):
                retry_result = execute_agent_tool("inspect_order_state", context, {})
                verification["order_inspection_retry"] = retry_result.get("summary")
                inspected = retry_result.get("_verification") if isinstance(retry_result.get("_verification"), dict) else inspected
                items = inspected.get("items", [])
                actual_prices = _normalized_prices([item.get("offer_price") for item in items])
            if not actual_prices or all(not price for price in actual_prices):
                quote_evidence = summary.get("agent_quote_evidence") if isinstance(summary.get("agent_quote_evidence"), dict) else {}
                submitted_prices = _normalized_prices(quote_evidence.get("submitted_unit_prices"))
                if len(submitted_prices) == 1 and expected_items > 1:
                    submitted_prices *= expected_items
                if not quote_evidence.get("quote_step_passed") or submitted_prices != expected_prices:
                    verification["reason"] = "两次查询均未取得实际报价，且没有匹配的成功报价提交证据"
                    return False, verification
                actual_prices = submitted_prices
                verification.setdefault("warnings", []).append("订单进入采购中间状态，使用后台已成功接收的报价提交证据")
            if expected_prices and actual_prices != expected_prices:
                verification["reason"] = f"实际报价{actual_prices}与目标{expected_prices}不一致"
                return False, verification
            if items and all(item.get("offer_price") not in (None, "") and item.get("num") not in (None, "") for item in items):
                actual_goods_total = sum(Decimal(str(item.get("offer_price"))) * Decimal(str(item.get("num"))) for item in items)
            else:
                actual_goods_total = sum(Decimal(price) * Decimal(str(goal["variables"].get("order_item_num") or 1)) for price in actual_prices)
            actual_goods_total_text = format(actual_goods_total.normalize(), "f")
            verification["actual_goods_total"] = actual_goods_total_text
            requested_total = str(pricing.get("requested_goods_total") or "")
            if requested_total and Decimal(actual_goods_total_text) != Decimal(requested_total):
                verification["reason"] = f"实际商品金额合计{actual_goods_total_text}与目标{requested_total}不一致"
                return False, verification

    porder_sn = str(context.state.get("porder_sn") or "").strip()
    if target in porder_nodes and not porder_sn:
        verification["reason"] = "未获得可查询的配送单号"
        return False, verification
    if target in porder_nodes and porder_sn and target not in {"porder_paid", "full_complete"}:
        inspect_result = execute_agent_tool("inspect_porder_state", context, {})
        verification["porder_inspection"] = inspect_result.get("summary")
        inspected = inspect_result.get("_verification") if isinstance(inspect_result.get("_verification"), dict) else {}
        current_node = str(inspected.get("detected_start_node") or current_node)

    if goal["variables"].get("order_payment_mode") == "bank" and target in FULL_FLOW_NODE_SEQUENCE[
        FULL_FLOW_NODE_SEQUENCE.index("order_paid") :
    ]:
        bank_ok = _bank_payment_verified(summary, "order_sn")
        verification.update({"bank_payment_verified": bank_ok, "finance_confirmed": bank_ok})
        if not bank_ok:
            verification["reason"] = "未在执行结果中确认银行付款及财务入金"
            return False, verification

    if goal["variables"].get("porder_payment_mode") == "bank" and target in {"porder_paid", "full_complete"}:
        porder_bank_ok = _bank_payment_verified(summary, "porder_sn")
        verification.update({"porder_bank_payment_verified": porder_bank_ok, "porder_finance_confirmed": porder_bank_ok})
        if not porder_bank_ok:
            verification["reason"] = "未在执行结果中确认配送单银行付款及财务入金"
            return False, verification

    passed = bool(last_result.get("passed") and current_node == target)
    if not passed and not verification.get("reason"):
        verification["reason"] = f"当前节点{current_node or '未知'}，尚未到达{target}"
    verification["actual_node"] = current_node
    return passed, verification


def _is_cancel_requested(session_id: str) -> bool:
    with _STORE_LOCK:
        session = _SESSIONS.get(session_id)
        return not session or session.cancel_requested


def _append_event(session_id: str, event: Dict[str, Any]) -> None:
    with _STORE_LOCK:
        session = _SESSIONS.get(session_id)
        if not session:
            return
        session.events.append(event)
        session.updated_at = datetime.now()


def _sync_runtime_state(session_id: str, state_value: Dict[str, Any]) -> None:
    with _STORE_LOCK:
        session = _SESSIONS.get(session_id)
        if not session:
            return
        session.runtime_state = dict(sanitize_observation(state_value))
        session.updated_at = datetime.now()


def _make_progress_callback(
    session_id: str,
    goal: Dict[str, Any],
    state: Dict[str, Any],
):
    last_signature: tuple[Any, ...] | None = None

    def callback(update: Dict[str, Any]) -> None:
        nonlocal last_signature
        if not isinstance(update, dict):
            return
        previous = state.get("progress") if isinstance(state.get("progress"), dict) else {}
        progress = {
            "operation_index": _problem_quantity(state.get("operation_index", 0)) + 1,
            "operation_total": len(_goal_operations(goal)),
            "current_node": str(update.get("node") or ""),
            "next_node": str(update.get("next_node") or ""),
            "node_status": str(update.get("status") or "running"),
            "item_index": update.get("item_index"),
            "item_total": update.get("item_total"),
            "problem_goods_id": update.get("problem_goods_id"),
            "reason": str(update.get("reason") or ""),
            "started_at": previous.get("started_at") or _now_text(),
            "updated_at": _now_text(),
        }
        state["progress"] = progress
        _sync_runtime_state(session_id, state)
        signature = (
            progress["current_node"],
            progress["node_status"],
            progress["item_index"],
            progress["item_total"],
            progress["problem_goods_id"],
        )
        if signature == last_signature:
            return
        last_signature = signature
        node_label = FULL_FLOW_NODE_LABELS.get(progress["current_node"], progress["current_node"] or "当前步骤")
        status_label = {
            "running": "执行中",
            "completed": "已完成",
            "failed": "失败",
            "awaiting_permission": "等待授权",
        }.get(progress["node_status"], progress["node_status"])
        _append_event(
            session_id,
            _event("progress", f"{node_label}：{status_label}", **progress),
        )

    return callback


def _finalize_session(
    db: Session,
    session_id: str,
    final_status: str,
    result: Dict[str, Any],
    context: AgentToolContext | None,
) -> None:
    _clear_temp_permission_secret(session_id)
    if final_status not in TERMINAL_STATUSES:
        final_status = "failed"
    with _STORE_LOCK:
        session = _SESSIONS.get(session_id)
        if not session:
            return
        goal = copy.deepcopy(session.goal)
        events = copy.deepcopy(session.events)
        messages = copy.deepcopy(session.messages)
        project_id = session.project_id
        env_id = session.env_id
    child_ids: list[int] = []
    for event in events:
        if event.get("record_id"):
            child_ids.append(int(event["record_id"]))
        event_summary = event.get("summary") if isinstance(event.get("summary"), dict) else {}
        for record_id in event_summary.get("child_record_ids") or []:
            if record_id:
                child_ids.append(int(record_id))
    child_ids = list(dict.fromkeys(child_ids))
    aggregate = {
        **sanitize_observation(result),
        "status": final_status,
        "child_record_ids": child_ids,
        "input_messages": sanitize_observation(messages),
        "semantic_trace": sanitize_observation(goal.get("intent") or {}),
        "order_sn": (context.state.get("order_sn") if context else None),
        "porder_sn": (context.state.get("porder_sn") if context else None),
        "current_node": (context.state.get("current_node") or context.state.get("detected_start_node") if context else None),
    }
    record = save_record(
        db,
        "api",
        0,
        final_status == "succeeded",
        aggregate_log(goal, events, aggregate),
        str(result.get("report_path") or ""),
        project_id=project_id,
        kind="data_agent",
        script_key="data_factory_agent",
        env_id=env_id,
        variables=goal.get("variables") if isinstance(goal.get("variables"), dict) else {},
    )
    with _STORE_LOCK:
        session = _SESSIONS.get(session_id)
        if not session:
            return
        session.status = final_status
        session.result = aggregate
        session.runtime_state = dict(sanitize_observation(context.state if context else {}))
        session.record_id = record.id
        session.question = ""
        session.updated_at = datetime.now()


def _goal_operations(goal: Dict[str, Any]) -> list[Dict[str, Any]]:
    operations = goal.get("operations") if isinstance(goal.get("operations"), list) else []
    return [item for item in operations if isinstance(item, dict) and item.get("type")]


def _current_operation(goal: Dict[str, Any], state: Dict[str, Any]) -> tuple[int, Dict[str, Any] | None]:
    operations = _goal_operations(goal)
    index = _problem_quantity(state.get("operation_index", 0))
    if index < 0:
        index = 0
    return index, operations[index] if index < len(operations) else None


def _complete_operation(
    state: Dict[str, Any],
    operation: Dict[str, Any],
    verification: Dict[str, Any],
) -> None:
    results = state.get("operation_results") if isinstance(state.get("operation_results"), dict) else {}
    results[str(operation.get("id") or f"operation_{len(results) + 1}")] = {
        "type": operation.get("type"),
        "status": "completed",
        "verification": sanitize_observation(verification),
    }
    state["operation_results"] = results
    state["operation_index"] = _problem_quantity(state.get("operation_index", 0)) + 1
    state.pop("current_operation_id", None)
    state.pop("current_operation_type", None)


def _pause_agent_session(
    session_id: str,
    session_status: str,
    question: str,
    result: Dict[str, Any],
) -> None:
    _clear_temp_permission_secret(session_id)
    with _STORE_LOCK:
        session = _SESSIONS.get(session_id)
        if not session:
            return
        session.status = session_status
        session.question = question
        session.result = sanitize_observation(result)
        session.runtime_state = dict(sanitize_observation(result.get("state") or session.runtime_state))
        session.updated_at = datetime.now()
        session.events.append(_event("permission" if session_status == "awaiting_permission" else "reconfirmation", question))


def _run_agent_session(session_id: str) -> None:
    db = SessionLocal()
    context: AgentToolContext | None = None
    permission_credentials = _take_temp_permission_secret(session_id)
    final_status = "failed"
    final_result: Dict[str, Any] = {"reason": "智能体未完成执行"}
    try:
        with _STORE_LOCK:
            session = _SESSIONS.get(session_id)
            if not session:
                return
            goal = copy.deepcopy(session.goal)
            project_id = session.project_id
            env_id = session.env_id
            saved_state = copy.deepcopy(session.runtime_state)
        _, env = validate_agent_context(db, project_id, env_id)
        config = _latest_model_config(db)
        public_variables = dict(goal.get("variables") or {})
        merged_variables = data_script_variables(db, public_variables, project_id)
        state: Dict[str, Any] = {
            "order_sn": goal.get("order_sn") or public_variables.get("order_sn") or "",
            "porder_sn": goal.get("porder_sn") or public_variables.get("porder_sn") or "",
            "operation_index": 0,
            "operation_results": {},
        }
        state.update({key: value for key, value in saved_state.items() if value not in (None, "")})
        context = AgentToolContext(
            db=db,
            env=env,
            project_id=project_id,
            goal=goal,
            variables=merged_variables,
            public_variables=public_variables,
            state=state,
            progress_callback=_make_progress_callback(session_id, goal, state),
            permission_credentials_provider=lambda: dict(permission_credentials),
        )
        action_counts: Dict[str, int] = {}
        last_result: Dict[str, Any] = {}
        invalid_actions = 0
        preflight_checked_operations: set[str] = set()

        for round_index in range(1, MAX_AGENT_ROUNDS + 1):
            if _is_cancel_requested(session_id):
                final_status = "cancelled"
                final_result = {"reason": "用户已取消，已完成动作不会回滚", **sanitize_observation(state)}
                break
            operation_index, operation = _current_operation(goal, state)
            if not operation:
                final_status = "succeeded"
                final_result = {
                    "reason": "全部已确认操作均已完成并通过实际数据校验",
                    "operation_results": sanitize_observation(state.get("operation_results") or {}),
                    **sanitize_observation(state),
                }
                break
            state["current_operation_id"] = operation.get("id")
            state["current_operation_type"] = operation.get("type")
            _sync_runtime_state(session_id, state)
            operation_key = str(operation.get("id") or operation_index)
            if (
                goal.get("mode") in {"resume_order", "resume_porder"}
                and operation.get("type") in {"advance_order", "advance_porder"}
                and operation_key not in preflight_checked_operations
            ):
                preflight_checked_operations.add(operation_key)
                inspect_tool = "inspect_porder_state" if operation.get("type") == "advance_porder" else "inspect_order_state"
                preflight = execute_agent_tool(inspect_tool, context, {})
                inspected = preflight.get("_verification") if isinstance(preflight.get("_verification"), dict) else {}
                current_node = str(inspected.get("detected_start_node") or "")
                target_node = str(operation.get("target_node") or goal.get("target_node") or "")
                _sync_runtime_state(session_id, context.state)
                _append_event(
                    session_id,
                    _event(
                        "preflight",
                        "续跑前已只读核验当前状态",
                        tool=inspect_tool,
                        passed=bool(preflight.get("passed")),
                        current_node=current_node,
                        target_node=target_node,
                        summary=preflight.get("summary"),
                    ),
                )
                if not preflight.get("passed") or not current_node:
                    reason = str((preflight.get("summary") or {}).get("reason") or "无法可靠识别当前业务状态")
                    question = f"续跑前只读核验失败：{reason}。为避免改变已有订单，本次未调用任何变更工具，请确认后续处理方式。"
                    _pause_agent_session(session_id, "clarifying", question, {"reason": question, "state": context.state})
                    return
                if current_node in FULL_FLOW_NODE_SEQUENCE and target_node in FULL_FLOW_NODE_SEQUENCE:
                    current_index = FULL_FLOW_NODE_SEQUENCE.index(current_node)
                    target_index = FULL_FLOW_NODE_SEQUENCE.index(target_node)
                    if current_index > target_index:
                        question = (
                            f"当前实际状态{FULL_FLOW_NODE_LABELS.get(current_node, current_node)}已超过目标"
                            f"{FULL_FLOW_NODE_LABELS.get(target_node, target_node)}。为避免继续改变数据，本次未调用任何变更工具，请确认是否保持现状。"
                        )
                        _pause_agent_session(session_id, "clarifying", question, {"reason": question, "state": context.state})
                        return
                    if current_index == target_index:
                        verified, verification = _verify_goal(context, preflight)
                        _append_event(session_id, _event("verification", "目标已达到，续跑前直接完成实际数据校验", **verification))
                        if not verified:
                            question = str(verification.get("reason") or "当前数据未通过目标合同校验")
                            question = f"目标节点已达到，但{question}。本次未调用任何变更工具，请确认后续处理方式。"
                            _pause_agent_session(session_id, "clarifying", question, {"reason": question, "state": context.state})
                            return
                        _complete_operation(state, operation, verification)
                        _sync_runtime_state(session_id, state)
                        _append_event(
                            session_id,
                            _event(
                                "operation_completed",
                                f"操作{operation_index + 1}已完成（目标原本已达到，未重复执行）",
                                operation_id=operation.get("id"),
                                operation_type=operation.get("type"),
                            ),
                        )
                        last_result = {}
                        action_counts = {}
                        continue
            with _STORE_LOCK:
                recent_events = copy.deepcopy(_SESSIONS[session_id].events)
            if operation.get("type") == "problem_goods":
                action = {
                    "action": "call_tool",
                    "tool": "process_problem_goods",
                    "arguments": {},
                    "reason": "执行已确认的问题产品操作",
                    "expected": "问题产品全部完成或安全暂停等待权限",
                    "suggested_tool": "",
                }
            else:
                try:
                    action = _next_agent_action(config, goal, recent_events, state)
                except Exception as exc:
                    invalid_actions += 1
                    _append_event(session_id, _event("agent_error", f"DeepSeek动作无效：{exc}", round=round_index))
                    if invalid_actions >= 2:
                        final_status = "blocked"
                        final_result = {"reason": f"DeepSeek连续返回无效动作：{exc}", **sanitize_observation(state)}
                        break
                    continue
            if _is_cancel_requested(session_id):
                final_status = "cancelled"
                final_result = {"reason": "用户已取消，已完成动作不会回滚", **sanitize_observation(state)}
                break

            if action["action"] == "request_reconfirmation":
                with _STORE_LOCK:
                    session = _SESSIONS.get(session_id)
                    if session:
                        session.status = "clarifying"
                        session.question = action["reason"] or "执行需要改变已确认目标，请补充新的要求后重新确认。"
                        session.plan_version += 1
                        session.updated_at = datetime.now()
                        session.events.append(_event("reconfirmation", session.question))
                return

            if action["action"] == "report_capability_gap":
                final_status = "blocked"
                final_result = {
                    "reason": action["reason"] or "缺少完成目标所需的受控工具",
                    "capability_gap": True,
                    "suggested_tool": action.get("suggested_tool") or "请评审并新增受控工具",
                    **sanitize_observation(state),
                }
                _append_event(session_id, _event("capability_gap", final_result["reason"], suggested_tool=final_result["suggested_tool"]))
                break

            if action["action"] == "finish":
                verified, verification = _verify_goal(context, last_result)
                _append_event(session_id, _event("verification", "智能体请求结束，执行最终校验", **verification))
                if verified:
                    _complete_operation(state, operation, verification)
                    _sync_runtime_state(session_id, state)
                    _append_event(session_id, _event("operation_completed", f"操作{operation_index + 1}已完成", operation_id=operation.get("id"), operation_type=operation.get("type")))
                    continue
                last_result = {"passed": False, "summary": verification}
                continue

            signature = json.dumps(
                {"tool": action["tool"], "arguments": action["arguments"]},
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            action_counts[signature] = action_counts.get(signature, 0) + 1
            if action_counts[signature] > MAX_IDENTICAL_ACTIONS:
                _append_event(session_id, _event("guard", "相同工具动作重复过多，已阻止再次执行", tool=action["tool"]))
                final_status = "blocked"
                final_result = {"reason": "相同动作连续无进展，已停止避免重复造数", **sanitize_observation(state)}
                break

            _append_event(
                session_id,
                _event(
                    "decision",
                    action["reason"] or f"准备调用{action['tool']}",
                    round=round_index,
                    tool=action["tool"],
                    expected=action["expected"],
                ),
            )
            try:
                tool_result = execute_agent_tool(action["tool"], context, action["arguments"])
            except Exception as exc:
                tool_result = {
                    "tool": action["tool"],
                    "passed": False,
                    "record_id": None,
                    "report_path": "",
                    "summary": {"reason": _safe_exception_text(exc, permission_credentials)},
                }
            finally:
                permission_credentials.clear()
            last_result = tool_result
            _sync_runtime_state(session_id, context.state)
            _append_event(
                session_id,
                _event(
                    "tool_result",
                    f"{action['tool']}执行{'成功' if tool_result.get('passed') else '失败'}",
                    tool=action["tool"],
                    passed=bool(tool_result.get("passed")),
                    record_id=tool_result.get("record_id"),
                    summary=tool_result.get("summary"),
                ),
            )
            tool_summary = tool_result.get("summary") if isinstance(tool_result.get("summary"), dict) else {}
            tool_reason = str(tool_summary.get("reason") or "")
            if not tool_result.get("passed") and action.get("tool") == "resume_order_flow" and "采购中间状态" in tool_reason:
                final_status = "blocked"
                final_result = {
                    "reason": tool_reason,
                    "capability_gap": True,
                    "suggested_tool": "增强订单续跑脚本以支持从采购中间状态继续",
                    **sanitize_observation(state),
                }
                _append_event(session_id, _event("capability_gap", tool_reason, suggested_tool=final_result["suggested_tool"]))
                break
            if operation.get("type") == "problem_goods" and tool_summary.get("awaiting_permission"):
                retry_count = _problem_quantity(context.state.get("permission_retry_count", 0))
                if tool_summary.get("permission_required") and retry_count < 1:
                    profile_id = _auto_large_refund_profile_id(db, project_id)
                    if profile_id:
                        context.state.update(
                            {
                                "backend_account_profile_id": profile_id,
                                "allow_large_refund": True,
                                "permission_retry_count": 1,
                                "awaiting_permission": False,
                            }
                        )
                        _sync_runtime_state(session_id, context.state)
                        _append_event(
                            session_id,
                            _event(
                                "permission_auto_resumed",
                                "已自动切换当前项目后台账号并重试一次",
                                backend_account_profile_id=profile_id,
                                permission_retry_count=1,
                            ),
                        )
                        continue
                context.state["awaiting_permission"] = True
                _sync_runtime_state(session_id, context.state)
                _pause_agent_session(
                    session_id,
                    "awaiting_permission",
                    str(tool_summary.get("reason") or "问题产品退款需要部长后台账号，请选择账号后继续。"),
                    {"reason": tool_summary.get("reason"), "summary": tool_summary, "state": context.state},
                )
                return
            if operation.get("type") == "problem_goods" and tool_summary.get("needs_clarification"):
                _sync_runtime_state(session_id, context.state)
                _pause_agent_session(
                    session_id,
                    "clarifying",
                    str(tool_summary.get("reason") or "问题产品处理范围不明确，请补充。"),
                    {"reason": tool_summary.get("reason"), "summary": tool_summary, "state": context.state},
                )
                return
            if operation.get("type") == "problem_goods" and not tool_result.get("passed"):
                final_status = "blocked"
                final_result = {"reason": tool_summary.get("reason") or "问题产品处理失败，已停止避免重复提交", **sanitize_observation(state)}
                break
            if tool_result.get("passed") and TOOL_SPECS[action["tool"]].mutating:
                if operation.get("type") == "problem_goods":
                    verified = bool(tool_summary.get("completed_all"))
                    verification = {
                        "operation_type": "problem_goods",
                        "completed_all": verified,
                        "problem_goods_ids": tool_summary.get("problem_goods_ids") or context.state.get("problem_goods_ids") or [],
                        "items": tool_summary.get("items") or [],
                    }
                    if not verified:
                        verification["reason"] = "问题产品实际状态尚未全部完成"
                else:
                    verified, verification = _verify_goal(context, tool_result)
                _append_event(session_id, _event("verification", "已根据实际状态校验目标", **verification))
                if verified:
                    _complete_operation(state, operation, verification)
                    _sync_runtime_state(session_id, state)
                    _append_event(session_id, _event("operation_completed", f"操作{operation_index + 1}已完成", operation_id=operation.get("id"), operation_type=operation.get("type")))
                    last_result = {}
                    action_counts = {}
                    continue
        else:
            final_status = "blocked"
            final_result = {"reason": "已达到智能体最大决策轮数，停止避免无限执行", **sanitize_observation(state)}

        _finalize_session(db, session_id, final_status, final_result, context)
    except Exception as exc:
        final_status = "failed"
        safe_error = _safe_exception_text(exc, permission_credentials)
        final_result = {"reason": safe_error, **sanitize_observation(context.state if context else {})}
        try:
            _append_event(session_id, _event("error", f"智能体执行异常：{safe_error}"))
            _finalize_session(db, session_id, final_status, final_result, context)
        except Exception:
            with _STORE_LOCK:
                session = _SESSIONS.get(session_id)
                if session:
                    session.status = "failed"
                    session.result = final_result
                    session.updated_at = datetime.now()
    finally:
        permission_credentials.clear()
        _clear_temp_permission_secret(session_id)
        with _STORE_LOCK:
            session = _SESSIONS.get(session_id)
            if session and _ENV_RUNNING.get(session.env_id) == session_id:
                _ENV_RUNNING.pop(session.env_id, None)
        db.close()


def update_agent_goal(
    session_id: str,
    user_id: int,
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    """Directly edit goal fields without DeepSeek re-analysis."""
    session = _session_or_404(session_id, user_id)
    with _STORE_LOCK:
        if session.status not in {"awaiting_confirmation", "clarifying"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="仅允许在待确认或待补充状态下修改目标",
            )
        goal = dict(session.goal)
        variables = dict(goal.get("variables") or {})
        intent = dict(goal.get("intent") or {})
        pricing = dict(intent.get("pricing") or {})
        price_edited = False
        allowed = {"order_shop_count", "order_per_shop", "order_item_num",
                   "offer_price", "offer_unit_prices", "target_node"}
        for key, value in updates.items():
            if key not in allowed or value is None:
                continue
            if key == "target_node":
                resolved = _target_node(value)
                if not resolved:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"无法识别的目标节点：{value}",
                    )
                goal["target_node"] = resolved
                goal["target_label"] = FULL_FLOW_NODE_LABELS.get(resolved, resolved)
                variables["stop_after_node"] = resolved
                for operation in goal.get("operations") or []:
                    if isinstance(operation, dict) and operation.get("type") in {"advance_order", "advance_porder"}:
                        operation["target_node"] = resolved
                        operation["target_label"] = FULL_FLOW_NODE_LABELS.get(resolved, resolved)
                        break
            elif key in ("offer_unit_prices",):
                prices = _price_list(value)
                if not prices:
                    continue
                variables[key] = prices
                variables.pop("offer_price", None)
                price_edited = True
            elif key in ("offer_price",):
                variables[key] = _decimal_value(value, key)
                variables.pop("offer_unit_prices", None)
                price_edited = True
            elif key in POSITIVE_INT_FIELDS:
                variables[key] = _positive_int(value, key)
            else:
                variables[key] = value
        expected_items = int(variables.get("order_shop_count") or 1) * int(variables.get("order_per_shop") or 1)
        quantity = int(variables.get("order_item_num") or 1)
        if price_edited:
            values = _price_list(variables.get("offer_unit_prices") or variables.get("offer_price"))
            if len(values) == 1:
                values *= expected_items
            if len(values) != expected_items:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"当前共{expected_items}个商品，请填写1个统一单价或{expected_items}个逐商品单价")
            total = sum(Decimal(value) * quantity for value in values)
            pricing = {
                "mode": "user_unit_override",
                "mode_label": "用户指定执行单价",
                "requested_goods_total": "",
                "effective_unit_prices": values,
                "effective_goods_total": format(total.normalize(), "f"),
                "includes_fees": False,
                "evidence": "用户直接编辑目标数据",
            }
        elif pricing.get("mode") == "goods_total" and any(key in updates for key in ("order_shop_count", "order_per_shop", "order_item_num")):
            compiled, compile_question = _compile_price_intent(
                {"mode": "goods_total", "amount": pricing.get("requested_goods_total"), "evidence": pricing.get("evidence")},
                variables,
                expected_items,
                quantity,
            )
            if compile_question:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=compile_question)
            pricing = compiled
        intent["pricing"] = pricing
        goal["intent"] = intent
        # Rebuild summary
        price_text = (
            "、".join(variables.get("offer_unit_prices") or [])
            if variables.get("offer_unit_prices")
            else str(variables.get("offer_price") or "10")
        )
        variables.setdefault("target_shops", variables.get("order_shop_count", 1))
        variables.setdefault("per_shop", variables.get("order_per_shop", 2))
        goal["variables"] = variables
        goal["summary"] = (
            f"{variables.get('order_shop_count', 1)}个店铺，每店{variables.get('order_per_shop', 2)}个商品，"
            f"每种购买数量{variables.get('order_item_num', 1)}，执行单价{price_text}元，目标{goal.get('target_label', '')}"
        )
        if any(isinstance(item, dict) and item.get("type") == "problem_goods" for item in goal.get("operations") or []):
            goal["summary"] += "，然后提出并处理问题产品"
        goal["contract_hash"] = hashlib.sha256(
            json.dumps(goal, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        session.goal = goal
        session.plan_version += 1
        session.updated_at = datetime.now()
        session.events.append(_event("goal_updated", "用户直接编辑了目标数据"))
    return _serialize_session(session)

def confirm_agent_session(
    db: Session,
    session_id: str,
    user_id: int,
    plan_version: int,
) -> Dict[str, Any]:
    session = _session_or_404(session_id, user_id)
    validate_agent_context(db, session.project_id, session.env_id)
    _latest_model_config(db)
    with _STORE_LOCK:
        if session.status != "awaiting_confirmation" or not session.goal:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前任务没有可确认的目标")
        if int(plan_version) != session.plan_version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="目标已更新，请重新查看后确认")
        running_session = _ENV_RUNNING.get(session.env_id)
        if running_session and running_session != session.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前环境已有数据智能体任务正在执行")
        session.status = "running"
        session.cancel_requested = False
        session.question = ""
        session.updated_at = datetime.now()
        session.events.append(_event("confirmation", "目标合同已确认，智能体开始执行", plan_version=session.plan_version))
        _ENV_RUNNING[session.env_id] = session.id
    try:
        _EXECUTOR.submit(_run_agent_session, session.id)
    except Exception:
        with _STORE_LOCK:
            session.status = "awaiting_confirmation"
            _ENV_RUNNING.pop(session.env_id, None)
        raise
    return _serialize_session(session)


def resume_agent_permission(
    db: Session,
    session_id: str,
    user_id: int,
    plan_version: int,
    backend_account_profile_id: int | None,
    backend_account: str = "",
    backend_password: str = "",
) -> Dict[str, Any]:
    session = _session_or_404(session_id, user_id)
    validate_agent_context(db, session.project_id, session.env_id)
    if len(str(backend_account or "")) > 160 or len(str(backend_password or "")) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="临时后台账号或密码长度超过限制",
        )
    temporary_account = str(backend_account or "").strip()
    temporary_password = str(backend_password or "")
    has_profile = backend_account_profile_id is not None
    has_temporary_account = bool(temporary_account)
    has_temporary_password = bool(temporary_password.strip())
    if has_profile == (has_temporary_account or has_temporary_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请选择后台账号档案，或同时输入临时后台账号和密码",
        )
    if not has_profile and not (has_temporary_account and has_temporary_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="临时后台账号和密码必须同时填写",
        )
    if has_profile:
        account_values, _ = account_profile_variables(
            db,
            int(backend_account_profile_id),
            session.project_id,
        )
        profile_account = account_values.get("backend_account") or account_values.get("username") or account_values.get("account")
        profile_password = account_values.get("backend_password") or account_values.get("password")
        if not profile_account or not profile_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="所选后台账号档案缺少账号或密码")
    with _STORE_LOCK:
        if session.status != "awaiting_permission":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前任务不在等待权限状态")
        if int(plan_version) != session.plan_version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="目标已更新，请重新查看后继续")
        running_session = _ENV_RUNNING.get(session.env_id)
        if running_session and running_session != session.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前环境已有数据智能体任务正在执行")
        if has_profile:
            session.runtime_state["backend_account_profile_id"] = int(backend_account_profile_id)
        else:
            session.runtime_state.pop("backend_account_profile_id", None)
        session.runtime_state["allow_large_refund"] = True
        session.runtime_state["permission_retry_count"] = max(
            1,
            _problem_quantity(session.runtime_state.get("permission_retry_count", 0)),
        )
        session.runtime_state["awaiting_permission"] = False
        session.status = "running"
        session.question = ""
        session.result = {}
        session.cancel_requested = False
        session.updated_at = datetime.now()
        event_data = (
            {"backend_account_profile_id": int(backend_account_profile_id)}
            if has_profile
            else {"temporary_credentials": True}
        )
        session.events.append(
            _event("permission_resumed", "已提供后台权限，继续问题产品处理", **event_data)
        )
        if has_profile:
            _clear_temp_permission_secret(session.id)
        else:
            _store_temp_permission_secret(session.id, temporary_account, temporary_password)
        _ENV_RUNNING[session.env_id] = session.id
    try:
        _EXECUTOR.submit(_run_agent_session, session.id)
    except Exception:
        _clear_temp_permission_secret(session.id)
        with _STORE_LOCK:
            session.status = "awaiting_permission"
            session.runtime_state["awaiting_permission"] = True
            _ENV_RUNNING.pop(session.env_id, None)
        raise
    return _serialize_session(session)


def cancel_agent_session(session_id: str, user_id: int) -> Dict[str, Any]:
    session = _session_or_404(session_id, user_id)
    with _STORE_LOCK:
        if session.status != "running":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前任务不在执行中")
        session.cancel_requested = True
        session.updated_at = datetime.now()
        session.events.append(_event("cancel", "已请求取消，将在当前工具执行结束后停止"))
    _clear_temp_permission_secret(session.id)
    return _serialize_session(session)


def reset_agent_runtime_for_tests() -> None:
    with _STORE_LOCK:
        for secret in _TEMP_PERMISSION_SECRETS.values():
            secret.clear()
        _TEMP_PERMISSION_SECRETS.clear()
        _CLAIMED_TEMP_PERMISSION_SECRETS.clear()
        _SESSIONS.clear()
        _ENV_RUNNING.clear()
