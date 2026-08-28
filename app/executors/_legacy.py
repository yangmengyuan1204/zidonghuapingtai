import logging
from datetime import datetime
import json
import queue
from pathlib import Path
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable, Tuple
from urllib.parse import urlparse, urlunparse
from uuid import uuid4


logger = logging.getLogger(__name__)

import requests

from ..models import ActionTemplate, ApiCase, Env, LocatorHealLog, UiCase
from .api import _pick_path, build_request_kwargs, execute_api_case, extract_response_vars
from .browser import _browser_executable_candidates, _get_proxy_from_env, launch_chromium_browser
from .common import (
    BASE_DIR,
    REPORT_DIR,
    SCREENSHOT_DIR,
    builtin_variables,
    ensure_report_dirs,
    json_dump_log as _json_dump_log,
    merge_variables,
    parse_json_value,
    render_template,
    to_json_text,
    write_allure_result,
)


# ─── 截图验证工具 ──────────────────────────────────────

ERROR_PAGE_PATTERNS = [
    "404 Not Found",
    "500 Internal Server Error",
    "502 Bad Gateway",
    "503 Service Unavailable",
    "504 Gateway Timeout",
    "Whitelabel Error Page",
    "Internal Server Error",
    "An error occurred",
    "Page not found",
    "无法访问此网站",
    "无法访问",
    "页面不存在",
    "系统错误",
    "服务器内部错误",
]






UI_ACTION_LABELS = {
    "goto": "打开页面",
    "input": "输入",
    "click": "点击",
    "select": "选择",
    "check": "勾选",
    "uncheck": "取消勾选",
    "wait": "等待",
    "wait_for_selector": "等待元素",
    "assert_visible": "检查元素可见",
    "assert_url": "检查页面地址",
    "assert_value": "检查输入值",
    "text_assert": "检查页面文案",
    "extract_text": "提取文本",
    "extract_value": "提取输入值",
    "screenshot": "截图",
    "resume_order_flow": "执行全流程履约至发货",
}

UI_LOCATOR_REQUIRED = {"input", "click", "wait_for_selector", "text_assert", "select", "check", "uncheck", "assert_visible", "assert_value", "extract_text", "extract_value"}
UI_VALUE_REQUIRED = {"goto", "input", "wait", "text_assert", "select", "assert_url", "assert_value"}
BUILTIN_VAR_NAMES = {"timestamp", "datetime", "date", "uuid", "random_int", "random_str", "random_phone", "random_email"}
LOGIN_URL_MARKERS = ("login", "signin")
LOGIN_TEXT_MARKERS = ("登录", "登入", "登陆", "login", "sign in", "signin", "ログイン", "サインイン", "マイページ", "mypage", "my page")
REGISTER_TEXT_MARKERS = ("立即注册", "马上注册", "去注册", "register", "sign up", "新規登録")


class UiStepExecutionError(RuntimeError):
    def __init__(self, message: str, detail: Dict[str, Any]):
        super().__init__(message)
        self.detail = detail


class UiAuthPreparationError(RuntimeError):
    def __init__(self, message: str, trace: list[str]):
        suffix = f"\n登录过程：\n- " + "\n- ".join(trace) if trace else ""
        super().__init__(message + suffix)
        self.message = message
        self.trace = trace












































BUSINESS_VAR_ALIASES = {
    "customer_id": ("customer_id", "customerId", "customerID"),
    "customer_name": ("customer_name", "customerName"),
    "box_no": ("box_no", "boxNo", "boxCode", "box_number"),
    "location_code": ("location_code", "locationCode", "warehouse_location"),
    "order_no": ("orderNumber", "order_no", "orderNo", "order_sn"),
}




































# ═══════════════════════════════════════════════════════════
# 操作模板匹配
# ═══════════════════════════════════════════════════════════






# ═══════════════════════════════════════════════════════════
# 执行前预检
# ═══════════════════════════════════════════════════════════






# ═══════════════════════════════════════════════════════════
# Locator 自愈
# ═══════════════════════════════════════════════════════════




# ═══════════════════════════════════════════════════════════
# 智能等待
# ═══════════════════════════════════════════════════════════
