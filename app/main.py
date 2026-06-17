import base64
import hashlib
import ipaddress
import logging
import os
import queue
import re
import secrets
import socket
import threading
import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Type
from urllib.parse import urljoin, urlparse
from uuid import uuid4


logger = logging.getLogger(__name__)

import requests
from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, text
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from .database import Base, engine, get_db, safe_commit
from .data_scripts import (
    preview_order_quote_options,
    run_balance_payment_script,
    run_bank_payment_script,
    run_direct_box_to_shelf_script,
    run_full_flow_script,
    run_order_quote_script,
    run_purchase_to_shelf_script,
    run_purchase_to_shelf_chain,
    run_porder_balance_payment_script,
    run_porder_bank_payment_script,
    run_shopping_cart_script,
    run_warehouse_delivery_script,
)
from .executors import ensure_report_dirs, execute_api_case, execute_ui_case, execute_ui_cases_batch, parse_json_value, to_json_text
from .functional_testing import (
    FunctionalScanError,
    analyze_functional_screenshot,
    diagnose_failure,
    generate_functional_cases,
    generate_ui_steps,
    read_axure_text,
    scan_page_dom,
    store_axure_file,
    store_functional_screenshot_file,
)
from .models import (
    AiConfig,
    ApiCase,
    CaseGenerationCase,
    CaseGenerationRequirementNote,
    CaseGenerationScreenshot,
    CaseGenerationTask,
    ActionTemplate,
    Env,
    FunctionalCase,
    FunctionalDataCheckResult,
    FunctionalDataCheckRule,
    FunctionalImpactItem,
    FunctionalRequirementNote,
    FunctionalRun,
    FunctionalScreenshot,
    FunctionalTask,
    LocatorHealLog,
    PageSnapshot,
    Project,
    TestRecord,
    UiCase,
    User,
    TestAccountBinding,
    TestAccountProfile,
)
from .schemas import (
    ActionTemplateCreate,
    ActionTemplateUpdate,
    AiConfigUpdate,
    ApiCaseCreate,
    ApiBatchExecuteRequest,
    ApiCaseUpdate,
    ApiExecuteRequest,
    CaseGenerationCaseBatchStatusUpdate,
    CaseGenerationCaseStatusUpdate,
    CaseGenerationCaseUpdate,
    CaseGenerationRequirementNoteCreate,
    CaseGenerationRequirementNoteUpdate,
    CaseGenerationScreenshotOcrUpdate,
    CaseGenerationTaskCreate,
    CaseGenerationTaskUpdate,
    DataScriptExecuteRequest,
    EnvCreate,
    EnvUpdate,
    FunctionalCaseBatchAutomationUpdate,
    FunctionalCaseBatchIds,
    FunctionalCaseBatchStatusUpdate,
    FunctionalCaseStats,
    FunctionalCaseStatusUpdate,
    FunctionalCaseUpdate,
    FunctionalDataCheckRuleCreate,
    FunctionalDataCheckRuleUpdate,
    FunctionalExecuteRequest,
    FunctionalImpactItemCreate,
    FunctionalImpactItemUpdate,
    FunctionalRequirementNoteCreate,
    FunctionalRequirementNoteUpdate,
    FunctionalScanRequest,
    FunctionalTaskContextUpdate,
    FunctionalTaskCreate,
    LocatorHealLogConfirm,
    LoginRequest,
    PreflightResult,
    ProjectCreate,
    ProjectUpdate,
    QuickRunRequest,
    TestAccountBindingUpdate,
    TestAccountProfileCreate,
    TestAccountProfileUpdate,
    UiCaseCreate,
    UiCaseUpdate,
    UserCreate,
    UserUpdate,
)
from .security import SECRET_KEY, create_access_token, get_current_user, hash_password, is_password_hash, require_admin, verify_password


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

TABLE_FIELDS = {
    User: ["id", "username", "password", "role", "create_time"],
    Project: ["id", "name", "desc", "create_time"],
    Env: ["id", "project_id", "env_name", "base_url", "global_headers", "global_vars", "timeout"],
    ApiCase: [
        "id",
        "project_id",
        "env_id",
        "case_name",
        "method",
        "url",
        "headers",
        "params",
        "body",
        "assert_rule",
        "status",
        "create_time",
    ],
    UiCase: ["id", "project_id", "case_name", "page_url", "steps", "timeout", "status", "create_time"],
    TestRecord: ["id", "case_type", "case_id", "project_id", "result", "log", "screenshot", "report_path", "execute_time"],
    FunctionalTask: ["id", "project_id", "iteration_name", "requirement_text", "axure_path", "target_url", "context", "status", "create_time"],
    FunctionalCase: [
        "id",
        "task_id",
        "title",
        "precondition",
        "steps",
        "expected",
        "category",
        "priority",
        "automation_status",
        "test_result",
        "ui_case_id",
        "quality_status",
        "quality_report",
        "failure_count",
        "create_time",
    ],
    PageSnapshot: ["id", "task_id", "page_url", "dom_summary", "screenshot_path", "scan_time"],
    FunctionalScreenshot: ["id", "task_id", "image_path", "analysis_result", "create_time"],
    FunctionalRequirementNote: ["id", "task_id", "note_text", "create_time", "update_time"],
    FunctionalRun: ["id", "task_id", "result", "log", "passed_count", "failed_count", "execute_time"],
    FunctionalImpactItem: ["id", "task_id", "item_type", "ref_id", "title", "target", "risk_level", "test_result", "source", "reason", "remark", "create_time", "update_time"],
    FunctionalDataCheckRule: ["id", "task_id", "rule_name", "check_type", "page_value", "api_method", "api_url", "api_headers", "api_body", "api_value_path", "compare_rule", "expected_value", "status", "create_time", "update_time"],
    FunctionalDataCheckResult: ["id", "task_id", "rule_id", "result", "page_value", "api_value", "message", "detail", "execute_time"],
    CaseGenerationTask: [
        "id",
        "project_id",
        "task_name",
        "target_name",
        "target_url",
        "requirement_text",
        "context",
        "status",
        "create_time",
        "update_time",
    ],
    CaseGenerationScreenshot: [
        "id",
        "task_id",
        "image_path",
        "analysis_result",
        "ocr_text",
        "corrected_text",
        "ocr_confidence",
        "low_confidence_items",
        "regions",
        "needs_manual_confirm",
        "ocr_error",
        "create_time",
    ],
    CaseGenerationRequirementNote: ["id", "task_id", "note_text", "create_time", "update_time"],
    CaseGenerationCase: [
        "id",
        "task_id",
        "title",
        "precondition",
        "steps",
        "expected",
        "priority",
        "source_refs",
        "generation_batch",
        "manual_edited",
        "test_result",
        "source_missing",
        "remark",
        "create_time",
        "update_time",
    ],
    AiConfig: ["id", "provider", "base_url", "model", "create_time"],  # api_key 不从此泄露
    TestAccountProfile: [
        "id", "project_id", "profile_name", "variables",
        "sensitive_variables", "login_url", "username_locator", "password_locator",
        "submit_locator", "success_url_contains", "success_selector",
        "status", "create_time", "update_time",
    ],
    TestAccountBinding: [
        "id", "target_type", "target_id", "account_profile_id",
        "create_time", "update_time",
    ],
}

JSON_FIELD_DEFAULTS = {
    "global_headers": {},
    "global_vars": {},
    "headers": {},
    "params": {},
    "assert_rule": {},
    "steps": [],
    "api_headers": {},
    "api_body": {},
    "compare_rule": {},
}

ACCOUNT_CONFIG_FIELDS = (
    "login_url",
    "username_locator",
    "password_locator",
    "submit_locator",
    "success_url_contains",
    "success_selector",
)

CASE_NAME_PREFIXES = ("\u6570\u636e\u811a\u672c-", "test-")
API_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
ACTION_TEMPLATE_JSON_DEFAULTS = {
    "trigger_keywords": [],
    "steps": [],
    "variables": {},
    "locator_fallbacks": {},
}


def strip_case_name_prefix(value: Any) -> str:
    text = str(value or "").strip()
    changed = True
    while changed:
        changed = False
        for prefix in CASE_NAME_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
                changed = True
    return text


def normalize_api_case_names(db: Session) -> None:
    changed = False
    for case in db.query(ApiCase).all():
        normalized = strip_case_name_prefix(case.case_name)
        if normalized and normalized != case.case_name:
            case.case_name = normalized
            changed = True
    if changed:
        db.commit()


def migrate_legacy_plaintext_passwords(db: Session) -> None:
    changed = 0
    for user in db.query(User).all():
        stored = str(user.password or "")
        if stored and not is_password_hash(stored):
            user.password = hash_password(stored)
            changed += 1
    if changed:
        db.commit()
        print(f"Migrated {changed} legacy plaintext user password(s) to bcrypt.", flush=True)


DATA_SCRIPT_PROJECT_NAME = "日本站测试"


def find_data_script_project(db: Session) -> Project | None:
    return db.query(Project).filter(Project.name == DATA_SCRIPT_PROJECT_NAME).order_by(Project.id.asc()).first()


def find_data_script_api_case(db: Session, item: Dict[str, Any], project_id: int | None = None) -> ApiCase | None:
    case_name = strip_case_name_prefix(item["case_name"])
    legacy_name = item["case_name"]
    url = item["url"]
    queries = [
        db.query(ApiCase).filter(ApiCase.case_name == legacy_name),
        db.query(ApiCase).filter(ApiCase.case_name == case_name, ApiCase.url == url),
        db.query(ApiCase).filter(ApiCase.url == url),
        db.query(ApiCase).filter(ApiCase.case_name == case_name),
    ]
    for query in queries:
        if project_id is not None:
            query = query.filter(ApiCase.project_id == project_id)
        case = query.order_by(ApiCase.id.asc()).first()
        if case:
            return case
    return None


LOGIN_CASE_NAME = "\u767b\u5f55"
CART_CASE_NAME = "\u52a0\u5165\u8d2d\u7269\u8f66"
# 前端客户登录的通用密码，可通过环境变量 FRONTEND_ACCOUNT_PASSWORD 覆盖
FRONTEND_UNIVERSAL_ACCOUNT_PASSWORD = os.getenv("FRONTEND_ACCOUNT_PASSWORD", "raku@123456``")

DATA_SCRIPT_API_CASES = [
    {
        "key": "client_login",
        "case_name": "\u6570\u636e\u811a\u672c-\u524d\u53f0\u767b\u5f55",
        "url": "/client/userLogin",
        "body": {"account": "{{account}}", "password": "{{password}}", "client_tool": "{{client_tool}}"},
        "extract": {"userToken": "json.data.userToken"},
    },
    {
        "key": "client_search_goods",
        "case_name": "\u6570\u636e\u811a\u672c-\u641c\u7d22\u5546\u54c1",
        "url": "/client/searchGoods",
        "body": {"keywords": "{{keyword}}", "shop_type": "{{shop_type}}", "page": "{{page}}", "pageSize": "{{page_size}}"},
    },
    {
        "key": "client_store_shop_id",
        "case_name": "\u6570\u636e\u811a\u672c-\u83b7\u53d6\u5e97\u94fa\u4fe1\u606f",
        "url": "/client/getStoreShopId",
        "body": {"keywords": "{{shop_keywords}}"},
    },
    {
        "key": "client_cart_add",
        "case_name": "\u6570\u636e\u811a\u672c-\u52a0\u5165\u8d2d\u7269\u8f66",
        "url": "/client/cart.goodsToCart",
        "body": {"to_cart[0][goods_id]": "{{goods_id}}", "to_cart[0][num]": "{{num}}"},
    },
    {
        "key": "client_cart_list",
        "case_name": "\u6570\u636e\u811a\u672c-\u8d2d\u7269\u8f66\u5217\u8868",
        "url": "/client/cart.goodsCartList",
        "body": {"priceCut": "{{price_cut}}"},
    },
    {
        "key": "client_cart_edit",
        "case_name": "\u6570\u636e\u811a\u672c-\u7f16\u8f91\u8d2d\u7269\u8f66\u5546\u54c1",
        "url": "/client/cart.goodsCartEdit",
        "body": {"id": "{{cart_id}}", "num": "{{num}}", "price": "{{price}}", "detail": "{{detail}}", "sku_id": "{{sku_id}}", "spec_id": "{{spec_id}}", "pic": "{{pic}}", "client_remark": "{{client_remark}}"},
    },
    {
        "key": "client_order_create",
        "case_name": "\u6570\u636e\u811a\u672c-\u521b\u5efa\u65b0\u8ba2\u5355",
        "url": "/client/order.orderCreate",
        "body": {"create_type": "{{create_type}}", "order_sn": "{{order_sn}}", "client_remark": "{{client_remark}}", "logistics_id": "{{logistics_id}}"},
        "extract": {"order_sn": "json.data.order_sn"},
    },
    {
        "key": "client_order_list",
        "case_name": "\u6570\u636e\u811a\u672c-\u524d\u53f0\u8ba2\u5355\u5217\u8868",
        "url": "/client/order.orderList",
        "body": {"status_name": "{{order_status_name}}", "page": "{{page}}", "pageSize": "{{page_size}}"},
    },
    {
        "key": "client_warehouse_list",
        "case_name": "\u6570\u636e\u811a\u672c-\u4ed3\u5e93\u5546\u54c1\u5217\u8868",
        "url": "/client/wms.stockAutoList",
        "body": {"children_id": "{{children_id}}", "for_sn_set": "{{for_sn_set}}", "tag_set": "{{tag_set}}", "client_remark": "{{client_remark}}", "sort_type": "{{sort_type}}", "hasLabel": "{{hasLabel}}"},
    },
    {
        "key": "client_porder_create",
        "case_name": "\u6570\u636e\u811a\u672c-\u63d0\u51fa\u914d\u9001\u5355",
        "url": "/client/porder.porderCreate",
        "body": {"create_type": "{{create_type}}", "porder_sn": "{{porder_sn}}", "logistics_id": "{{logistics_id}}", "porder_detail[0][order_detail_id]": "{{order_detail_id}}", "porder_detail[0][send_num]": "{{send_num}}"},
        "extract": {"porder_sn": "json.data.porder_sn"},
    },
    {
        "key": "admin_porder_detail",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u8be6\u60c5",
        "url": "/porder.detail",
        "body": {"porder_sn": "{{porder_sn}}"},
    },
    {
        "key": "admin_porder_submit_translate",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u63d0\u4ea4\u914d\u8d27",
        "url": "/porder.submitTranslate",
        "body": {"porder_sn": "{{porder_sn}}", "client_remark_translate": "{{client_remark_translate}}", "list[0][id]": "{{porder_detail_id}}", "list[0][y_remark]": "{{y_remark}}", "is_temp": "{{is_temp}}"},
    },
    {
        "key": "admin_porder_add_box",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u6dfb\u52a0\u7bb1\u5b50",
        "url": "/porder.addBox",
        "body": {"porder_sn": "{{porder_sn}}", "count": "{{box_count}}", "length": "{{box_length}}", "width": "{{box_width}}", "height": "{{box_height}}", "weight": "{{box_weight}}"},
    },
    {
        "key": "admin_porder_complete_box",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u6807\u8bb0\u88c5\u7bb1\u5b8c\u6210",
        "url": "/porder.completeBox",
        "body": {"porder_sn": "{{porder_sn}}", "freight_id_set[0]": "{{freight_id}}", "count": "{{box_count}}", "length": "{{box_length}}", "width": "{{box_width}}", "height": "{{box_height}}", "weight": "{{box_weight}}"},
    },
    {
        "key": "admin_porder_into_box_preview",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u88c5\u7bb1\u9884\u89c8",
        "url": "/porder.intoBoxPreview",
        "body": {"porderDetailIdS[0]": "{{porder_detail_id}}"},
    },
    {
        "key": "admin_porder_into_box_submit",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u88c5\u7bb1\u63d0\u4ea4",
        "url": "/porder.intoBoxSubmit",
        "body": {"freight_id_set[0]": "{{freight_id}}", "list[0][per_num]": "{{box_num}}", "list[0][porder_detail_id]": "{{porder_detail_id}}", "list[0][stock][0][stock_id]": "{{stock_id}}", "list[0][stock][0][num_need]": "{{box_num}}"},
    },
    {
        "key": "admin_porder_to_wait_offer",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u63d0\u4ea4\u4e1a\u52a1",
        "url": "/porder.toWaitOffer",
        "body": {"porder_sn": "{{porder_sn}}"},
    },
    {
        "key": "admin_porder_batch_update_freight_logistics",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u9009\u62e9\u56fd\u9645\u7269\u6d41",
        "url": "/porder.batchUpdateFreightLogistics",
        "body": {"logistics_id": "{{delivery_quote_logistics_id}}", "freight_id_set[0]": "{{freight_id}}"},
    },
    {
        "key": "admin_porder_freight_list",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u56fd\u9645\u8fd0\u8d39\u5217\u8868",
        "url": "/porder.freightList",
        "body": {"porder_sn": "{{porder_sn}}"},
    },
    {
        "key": "admin_spot_porder_detail",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u88c5\u7bb1\u540e\u62bd\u68c0\u8be6\u60c5",
        "url": "/spot/spot/check/getSpotPorderDetail",
        "body": {"porder_sn": "{{porder_sn}}", "filterByFreightNum": "false"},
    },
    {
        "key": "admin_porder_amount_current",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u91d1\u989d\u8ba1\u7b97",
        "url": "/porder.porderAmountCurrent",
        "body": {"porder_sn": "{{porder_sn}}"},
    },
    {
        "key": "admin_porder_submit_offer",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u62a5\u4ef7",
        "url": "/porder.submitOffer",
        "body": {"porder_sn": "{{porder_sn}}", "list[0][id]": "{{porder_detail_id}}", "logistics_price_artificial": "{{logistics_price_artificial}}"},
    },
    {
        "key": "client_balance_pay",
        "case_name": "\u6570\u636e\u811a\u672c-\u4f59\u989d\u652f\u4ed8\u8ba2\u5355",
        "url": "/client/order.balancePayOrder",
        "body": {"order_sn": "{{order_sn}}", "discounts_id": "{{discounts_id}}", "predict_logistics_price_is_pay": "{{predict_logistics_price_is_pay}}"},
        "extract": {"order_sn": "json.data.order_sn"},
    },
    {
        "key": "client_bank_pay",
        "case_name": "\u6570\u636e\u811a\u672c-\u94f6\u884c\u652f\u4ed8\u8ba2\u5355",
        "url": "/client/order.bankPayOrder",
        "body": {"order_sn": "{{order_sn}}", "pay_bank_method": "{{pay_bank_method}}", "pay_date": "{{pay_date}}", "pay_reach_date": "{{pay_reach_date}}", "pay_name": "{{pay_name}}", "pay_amount": "{{pay_amount}}", "pay_remark": "{{pay_remark}}", "discounts_id": "{{discounts_id}}", "predict_logistics_price_is_pay": "{{predict_logistics_price_is_pay}}"},
        "extract": {"order_sn": "json.data.order_sn", "serial_number": "json.data.serial_number"},
    },
    {
        "key": "client_porder_balance_pay",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u4f59\u989d\u4ed8\u6b3e",
        "url": "/client/porder.balancePayOrder",
        "body": {"porder_sn": "{{porder_sn}}", "discounts_id": "{{discounts_id}}", "merge_pay": "{{merge_pay}}"},
        "extract": {"porder_sn": "json.data.porder_sn"},
    },
    {
        "key": "client_porder_bank_pay",
        "case_name": "\u6570\u636e\u811a\u672c-\u914d\u9001\u5355\u94f6\u884c\u4ed8\u6b3e",
        "url": "/client/porder.bankPayOrder",
        "body": {"porder_sn": "{{porder_sn}}", "pay_bank_method": "{{pay_bank_method}}", "pay_date": "{{pay_date}}", "pay_reach_date": "{{pay_reach_date}}", "pay_name": "{{pay_name}}", "pay_amount": "{{pay_amount}}", "pay_remark": "{{pay_remark}}", "discounts_id": "{{discounts_id}}", "merge_pay": "{{merge_pay}}"},
        "extract": {"porder_sn": "json.data.porder_sn", "serial_number": "json.data.serial_number"},
    },
    {
        "key": "admin_login",
        "case_name": "\u6570\u636e\u811a\u672c-\u540e\u53f0\u767b\u5f55",
        "url": "/admin.login",
        "body": {"username": "{{backend_account}}", "password": "{{backend_password}}", "system": "{{backend_system}}", "compute_token": "{{backend_compute_token}}", "code": "{{backend_code}}"},
        "extract": {"adminToken": "json.data.access_token", "compute_token": "json.data.compute_token"},
    },
    {
        "key": "admin_order_detail",
        "case_name": "\u6570\u636e\u811a\u672c-\u540e\u53f0\u8ba2\u5355\u8be6\u60c5",
        "url": "/order.detail",
        "body": {"order_sn": "{{order_sn}}"},
    },
    {
        "key": "admin_order_translate",
        "case_name": "\u6570\u636e\u811a\u672c-\u8ba2\u5355\u7ffb\u8bd1\u63d0\u4ea4",
        "url": "/order.submitTranslate",
        "body": {"data": "{{data}}", "is_temp": "{{translate_is_temp}}"},
    },
    {
        "key": "admin_order_confirm",
        "case_name": "\u6570\u636e\u811a\u672c-\u91c7\u8d2d\u8c03\u67e5\u63d0\u4ea4",
        "url": "/order.submitConfirm",
        "body": {"order_sn": "{{order_sn}}", "data": "{{data}}", "is_temp": "{{confirm_is_temp}}"},
    },
    {
        "key": "admin_order_offer",
        "case_name": "\u6570\u636e\u811a\u672c-\u4e1a\u52a1\u62a5\u4ef7\u63d0\u4ea4",
        "url": "/order.submitOffer",
        "body": {"data": "{{data}}", "is_temp": "{{offer_is_temp}}"},
    },
    {
        "key": "admin_bill_merge_pay_detail",
        "case_name": "\u6570\u636e\u811a\u672c-\u8d22\u52a1\u786e\u8ba4\u5165\u91d1",
        "url": "/bill.mergePayDetail",
        "body": {"serial_number": "{{serial_number}}"},
    },
    {
        "key": "admin_bill_unconfirm_list",
        "case_name": "\u6570\u636e\u811a\u672c-\u8d22\u52a1\u5f85\u786e\u8ba4\u6c47\u6b3e\u5217\u8868",
        "url": "/bill.unConfirmList",
        "body": {"page": "{{page}}", "pageSize": "{{page_size}}", "serial_number": "{{serial_number}}", "order_sn": "{{order_sn}}"},
    },
    {
        "key": "admin_bill_confirm",
        "case_name": "\u6570\u636e\u811a\u672c-\u8d22\u52a1\u786e\u8ba4\u6c47\u6b3e",
        "url": "/bill.confirm",
        "body": {"id": "{{bill_id}}"},
    },
    {
        "key": "admin_purchase_list",
        "case_name": "\u6570\u636e\u811a\u672c-\u5f85\u62cd\u4e0b\u5546\u54c1\u5217\u8868",
        "url": "/purchase.purchaseList",
        "body": {"page": "{{page}}", "pageSize": "{{page_size}}", "status": "{{purchase_status}}", "order_sn": "{{order_sn}}"},
    },
    {
        "key": "admin_purchase_save_temp",
        "case_name": "\u6570\u636e\u811a\u672c-\u4fdd\u5b58\u91c7\u8d2d\u4ea4\u6613\u53f7",
        "url": "/purchase.saveTemp",
        "body": {"data": "{{data}}"},
    },
    {
        "key": "admin_purchase_to_wait_modify_price",
        "case_name": "\u6570\u636e\u811a\u672c-\u6807\u8bb0\u5f85\u6539\u4ef7",
        "url": "/purchase.toWaitModifyPrice",
        "body": {"ids": "{{ids}}", "purchase_no": "{{purchase_no}}"},
    },
    {
        "key": "admin_purchase_to_wait_pay",
        "case_name": "\u6570\u636e\u811a\u672c-\u63d0\u4ea4\u5f85\u8d22\u52a1\u4ed8\u6b3e",
        "url": "/purchase.toWaitPay",
        "body": {"data": "{{data}}", "ids": "{{ids}}"},
    },
    {
        "key": "admin_bill_purchase_wait_pay_list",
        "case_name": "\u6570\u636e\u811a\u672c-\u4ea4\u6613\u53f7\u5f85\u4ed8\u6b3e\u5217\u8868",
        "url": "/bill.purchaseWaitPayList",
        "body": {"page": "{{page}}", "pageSize": "{{page_size}}", "status": "{{finance_wait_pay_status}}", "purchase_no": "{{purchase_no}}"},
    },
    {
        "key": "admin_bill_purchase_wait_pay_confirm",
        "case_name": "\u6570\u636e\u811a\u672c-\u4ea4\u6613\u53f7\u4ed8\u6b3e\u786e\u8ba4",
        "url": "/bill.purchaseWaitPayConfirm",
        "body": {"purchaseNoSet": "{{purchaseNoSet}}"},
    },
    {
        "key": "admin_follow_list",
        "case_name": "\u6570\u636e\u811a\u672c-\u6838\u67e5\u5546\u54c1\u5217\u8868",
        "url": "/follow.followList",
        "body": {"page": "{{page}}", "pageSize": "{{page_size}}", "status": "{{follow_status}}", "purchase_no": "{{purchase_no}}", "order_sn": "{{order_sn}}"},
    },
    {
        "key": "admin_follow_up_preview",
        "case_name": "\u6570\u636e\u811a\u672c-\u6838\u67e5\u5546\u54c1\u9884\u89c8",
        "url": "/follow.upPreview",
        "body": {"purchase_no": "{{purchase_no}}", "express_no": "{{express_no}}"},
    },
    {
        "key": "admin_follow_start_checking",
        "case_name": "\u6570\u636e\u811a\u672c-\u5f00\u59cb\u6838\u67e5",
        "url": "/follow.startChecking",
        "body": {"purchaseIds": "{{purchaseIds}}"},
    },
    {
        "key": "admin_wms_grid_preview",
        "case_name": "\u6570\u636e\u811a\u672c-\u5e93\u4f4d\u9884\u89c8",
        "url": "/wms.wmsGridPreview",
        "body": {"shelf_type_set": "{{shelf_type_set}}", "user_id": "{{user_id}}", "order_purchase_id": "{{order_purchase_id}}"},
    },
    {
        "key": "admin_follow_up_storage",
        "case_name": "\u6570\u636e\u811a\u672c-\u4e0a\u67b6\u5165\u5e93",
        "url": "/follow.upStorage",
        "body": {"grid_id": "{{grid_id}}", "data": "{{data}}", "reconfirm": "{{reconfirm}}"},
    },
    {
        "key": "admin_box_list",
        "case_name": "\u6570\u636e\u811a\u672c-\u76f4\u63a5\u88c5\u7bb1\u7bb1\u5b50\u5217\u8868",
        "url": "/box.boxList",
        "body": {"status": "{{status}}", "order_sn": "{{order_sn}}"},
    },
    {
        "key": "admin_box_add_batch",
        "case_name": "\u6570\u636e\u811a\u672c-\u76f4\u63a5\u88c5\u7bb1\u6dfb\u52a0\u7bb1\u5b50",
        "url": "/box.addBoxBatch",
        "body": {"order_sn": "{{order_sn}}", "num": "{{num}}"},
    },
    {
        "key": "admin_box_update_attr",
        "case_name": "\u6570\u636e\u811a\u672c-\u76f4\u63a5\u88c5\u7bb1\u4fee\u6539\u7bb1\u89c4",
        "url": "/box.updateBoxAttr",
        "body": {"ids": "{{ids}}", "attr": "{{attr}}", "c": "{{c}}", "k": "{{k}}", "g": "{{g}}"},
    },
    {
        "key": "admin_box_update_weight",
        "case_name": "\u6570\u636e\u811a\u672c-\u76f4\u63a5\u88c5\u7bb1\u4fee\u6539\u91cd\u91cf",
        "url": "/box.updateBoxWeight",
        "body": {"ids": "{{ids}}", "weight": "{{weight}}"},
    },
    {
        "key": "admin_box_into_box",
        "case_name": "\u6570\u636e\u811a\u672c-\u76f4\u63a5\u88c5\u7bb1\u8d27\u7269\u88c5\u7bb1",
        "url": "/box.intoBox",
        "body": {"ids": "{{ids}}", "list": "{{list}}"},
    },
    {
        "key": "admin_box_delete",
        "case_name": "\u6570\u636e\u811a\u672c-\u76f4\u63a5\u88c5\u7bb1\u5220\u9664\u7bb1\u5b50",
        "url": "/box.deleteBox",
        "body": {"ids": "{{ids}}"},
    },
    {
        "key": "admin_box_to_complete",
        "case_name": "\u6570\u636e\u811a\u672c-\u76f4\u63a5\u88c5\u7bb1\u4e0a\u67b6\u5b8c\u6210",
        "url": "/box.toComplete",
        "body": {"ids": "{{ids}}", "grid_id": "{{grid_id}}", "grid_number": "{{grid_number}}"},
    },
]


def ensure_data_script_api_cases(db: Session) -> None:
    project = find_data_script_project(db)
    if not project:
        project = Project(name=DATA_SCRIPT_PROJECT_NAME, desc="系统自动创建", create_time=datetime.now())
        db.add(project)
        db.commit()
        db.refresh(project)

    env = db.query(Env).filter(Env.project_id == project.id).order_by(Env.id.asc()).first()
    if not env:
        env = Env(
            project_id=project.id,
            env_name=project.name or "test-\u6570\u636e\u811a\u672c",
            base_url="https://jpapi.rakumart.cn",
            global_headers=to_json_text({}, {}),
            global_vars=to_json_text({"api": "https://jpapi.rakumart.cn"}, {}),
            timeout=30,
        )
        db.add(env)
        db.commit()
        db.refresh(env)

    for item in DATA_SCRIPT_API_CASES:
        case_name = strip_case_name_prefix(item["case_name"])
        exists = find_data_script_api_case(db, item, env.project_id) or find_data_script_api_case(db, item)
        if exists:
            exists.case_name = case_name
            exists.project_id = env.project_id
            exists.env_id = env.id
            key = str(item.get("key", ""))
            if item.get("key") in {"client_warehouse_list", "client_porder_create"} or key.startswith(("admin_porder_", "admin_spot_")):
                assert_rule = {"status_code": 200}
                if item.get("extract"):
                    assert_rule["extract"] = item["extract"]
                exists.url = item["url"]
                exists.body = to_json_text(item["body"], {})
                exists.assert_rule = to_json_text(assert_rule, {})
                exists.headers = to_json_text({"Content-Type": "multipart/form-data"}, {})
            continue
        assert_rule = {"status_code": 200}
        if item.get("extract"):
            assert_rule["extract"] = item["extract"]
        db.add(
            ApiCase(
                project_id=env.project_id,
                env_id=env.id,
                case_name=case_name,
                method="POST",
                url=item["url"],
                headers=to_json_text({"Content-Type": "multipart/form-data"}, {}),
                params=to_json_text({}, {}),
                body=to_json_text(item["body"], {}),
                assert_rule=to_json_text(assert_rule, {}),
                status="active",
                create_time=datetime.now(),
            )
        )
    db.commit()


def init_app() -> None:
    Base.metadata.create_all(bind=engine)
    # 轻量迁移：补齐历史 SQLite 数据库缺失列。
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        migrations = {
            "functional_case": {
                "test_result": "ALTER TABLE functional_case ADD COLUMN test_result VARCHAR(20) DEFAULT 'untested'",
                "category": "ALTER TABLE functional_case ADD COLUMN category VARCHAR(40)",
                "quality_status": "ALTER TABLE functional_case ADD COLUMN quality_status VARCHAR(32) DEFAULT 'unchecked'",
                "quality_report": "ALTER TABLE functional_case ADD COLUMN quality_report TEXT",
                "failure_count": "ALTER TABLE functional_case ADD COLUMN failure_count INTEGER DEFAULT 0",
            },
            "test_record": {
                "project_id": "ALTER TABLE test_record ADD COLUMN project_id INTEGER",
            },
            "test_account_profile": {
                "login_url": "ALTER TABLE test_account_profile ADD COLUMN login_url VARCHAR(500)",
                "username_locator": "ALTER TABLE test_account_profile ADD COLUMN username_locator TEXT",
                "password_locator": "ALTER TABLE test_account_profile ADD COLUMN password_locator TEXT",
                "submit_locator": "ALTER TABLE test_account_profile ADD COLUMN submit_locator TEXT",
                "success_url_contains": "ALTER TABLE test_account_profile ADD COLUMN success_url_contains VARCHAR(500)",
                "success_selector": "ALTER TABLE test_account_profile ADD COLUMN success_selector VARCHAR(500)",
            },
            "case_generation_screenshot": {
                "ocr_text": "ALTER TABLE case_generation_screenshot ADD COLUMN ocr_text TEXT",
                "corrected_text": "ALTER TABLE case_generation_screenshot ADD COLUMN corrected_text TEXT",
                "ocr_confidence": "ALTER TABLE case_generation_screenshot ADD COLUMN ocr_confidence FLOAT",
                "low_confidence_items": "ALTER TABLE case_generation_screenshot ADD COLUMN low_confidence_items TEXT",
                "regions": "ALTER TABLE case_generation_screenshot ADD COLUMN regions TEXT",
                "needs_manual_confirm": "ALTER TABLE case_generation_screenshot ADD COLUMN needs_manual_confirm INTEGER DEFAULT 1",
                "ocr_error": "ALTER TABLE case_generation_screenshot ADD COLUMN ocr_error TEXT",
            },
        }
        with engine.begin() as conn:
            for table_name, table_migrations in migrations.items():
                existing_columns = {c["name"] for c in inspector.get_columns(table_name)}
                for column_name, sql in table_migrations.items():
                    if column_name not in existing_columns:
                        conn.execute(text(sql))
    except Exception:
        pass  # 迁移失败不影响启动
    ensure_report_dirs()
    db = next(get_db())
    try:
        migrate_legacy_plaintext_passwords(db)
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
            db.add(
                User(
                    username="admin",
                    password=hash_password(admin_password),
                    role="admin",
                    create_time=datetime.now(),
                )
            )
            db.commit()
            if not os.getenv("DEFAULT_ADMIN_PASSWORD"):
                print(
                    "Created default admin user. Password: "
                    f"{admin_password}. Set DEFAULT_ADMIN_PASSWORD to control this value.",
                    flush=True,
                )
        elif verify_password("admin123", admin.password) and os.getenv("ALLOW_DEFAULT_ADMIN_PASSWORD", "").strip() != "1":
            replacement_password = os.getenv("DEFAULT_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
            if replacement_password != "admin123":
                admin.password = hash_password(replacement_password)
                db.commit()
                print(
                    "Rotated insecure default admin password. New password: "
                    f"{replacement_password}. Set DEFAULT_ADMIN_PASSWORD to control this value.",
                    flush=True,
                )
        normalize_api_case_names(db)
        ensure_data_script_api_cases(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_app()
    yield


app = FastAPI(title="接口 + UI 自动化测试平台", lifespan=lifespan)
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").strip()
allowed_origins = [origin.strip() for origin in CORS_ORIGINS.split(",") if origin.strip()] if CORS_ORIGINS else ["http://localhost:8000", "http://127.0.0.1:8000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_frontend_assets(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    ct = response.headers.get("content-type", "")
    if "application/json" in ct and "charset" not in ct.lower():
        response.headers["content-type"] = ct.replace("application/json", "application/json; charset=utf-8")
    return response


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> Dict[str, Any]:
    """健康检查端点。"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


def schema_data(payload: Any, exclude_unset: bool = False) -> Dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_unset=exclude_unset)
    return payload.dict(exclude_unset=exclude_unset)


def serialize(obj: Any, hide_password: bool = True) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    for field in TABLE_FIELDS[type(obj)]:
        if hide_password and field == "password":
            continue
        value = getattr(obj, field)
        if isinstance(value, datetime):
            value = value.strftime("%Y-%m-%d %H:%M:%S")
        data[field] = value
    return data


def serialize_many(items: Iterable[Any]) -> list[Dict[str, Any]]:
    return [serialize(item) for item in items]


def get_or_404(db: Session, model: Type[Any], item_id: int) -> Any:
    item = db.get(model, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据不存在")
    return item


def normalize_json_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    for field, fallback in JSON_FIELD_DEFAULTS.items():
        if field in data:
            data[field] = to_json_text(data[field], fallback)
    if "body" in data and data["body"] is not None and not isinstance(data["body"], str):
        data["body"] = to_json_text(data["body"], {})
    if "body" in data and data["body"] is None:
        data["body"] = ""
    if "method" in data and data["method"]:
        data["method"] = str(data["method"]).upper()
    return data


def require_non_blank_text(data: Dict[str, Any], field: str, label: str) -> None:
    value = str(data.get(field) or "").strip()
    if not value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label}不能为空")
    data[field] = value


def normalize_project_payload(data: Dict[str, Any], require_name: bool = False) -> Dict[str, Any]:
    if require_name or "name" in data:
        require_non_blank_text(data, "name", "项目名称")
    if "desc" in data and data["desc"] is None:
        data["desc"] = ""
    return data


def normalize_env_payload(data: Dict[str, Any], require_required_fields: bool = False) -> Dict[str, Any]:
    if require_required_fields or "env_name" in data:
        require_non_blank_text(data, "env_name", "环境名称")
    if require_required_fields or "base_url" in data:
        require_non_blank_text(data, "base_url", "环境地址")
    if "timeout" in data and data["timeout"] is not None and int(data["timeout"]) <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="超时时间必须大于0")
    return data


def normalize_api_case_payload(data: Dict[str, Any], require_required_fields: bool = False) -> Dict[str, Any]:
    if require_required_fields or "method" in data:
        method = str(data.get("method") or "").upper().strip()
        if method not in API_ALLOWED_METHODS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的请求方法")
        data["method"] = method
    if require_required_fields or "url" in data:
        require_non_blank_text(data, "url", "请求地址")
    return data


def ensure_env_belongs_to_project(env: Env, project_id: int) -> None:
    if env.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="环境不属于该用例项目")


def ensure_project_exists(db: Session, project_id: int) -> None:
    if not db.get(Project, project_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="项目不存在")


def ensure_env_exists(db: Session, env_id: int) -> Env:
    env = db.get(Env, env_id)
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="环境不存在")
    return env


def ensure_unique_username(db: Session, username: str, user_id: int | None = None) -> None:
    query = db.query(User).filter(User.username == username)
    if user_id is not None:
        query = query.filter(User.id != user_id)
    if query.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")


def safe_file_response(raw_path: str | None) -> FileResponse:
    if not raw_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    file_path = Path(raw_path)
    if not file_path.is_absolute():
        file_path = BASE_DIR / file_path
    resolved = file_path.resolve()
    base = BASE_DIR.resolve()
    if base not in resolved.parents and resolved != base:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="禁止访问该文件")
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    return FileResponse(resolved)


def latest_ai_config(db: Session) -> AiConfig | None:
    return db.query(AiConfig).order_by(AiConfig.id.desc()).first()


def serialize_ai_config(config: AiConfig | None) -> Dict[str, Any]:
    if not config:
        return {"provider": "openai_compatible", "base_url": "", "model": "", "api_key": ""}
    data = serialize(config)
    data["api_key"] = ""
    return data


FUNCTIONAL_TEST_RESULTS = {"untested", "passed", "failed", "blocked", "skipped"}


def normalize_functional_result(value: Any) -> str:
    text_value = str(value or "untested").strip().lower()
    return text_value if text_value in FUNCTIONAL_TEST_RESULTS else "untested"


def functional_result_counts(items: Iterable[Any], attr_name: str = "test_result") -> Dict[str, int]:
    counts = {key: 0 for key in FUNCTIONAL_TEST_RESULTS}
    total = 0
    for item in items:
        total += 1
        counts[normalize_functional_result(getattr(item, attr_name, None))] += 1
    counts["total"] = total
    return counts


def latest_data_check_results_by_rule(db: Session, task_id: int) -> Dict[int, FunctionalDataCheckResult]:
    latest: Dict[int, FunctionalDataCheckResult] = {}
    rows = (
        db.query(FunctionalDataCheckResult)
        .filter(FunctionalDataCheckResult.task_id == task_id)
        .order_by(FunctionalDataCheckResult.id.desc())
        .all()
    )
    for row in rows:
        if row.rule_id not in latest:
            latest[row.rule_id] = row
    return latest


def functional_task_conclusion_summary(db: Session, task: FunctionalTask) -> Dict[str, Any]:
    cases = db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id).all()
    impact_items = db.query(FunctionalImpactItem).filter(FunctionalImpactItem.task_id == task.id).all()
    rules = (
        db.query(FunctionalDataCheckRule)
        .filter(FunctionalDataCheckRule.task_id == task.id, FunctionalDataCheckRule.status != "inactive")
        .all()
    )
    latest_results = latest_data_check_results_by_rule(db, task.id)

    p0_blockers = []
    p1_failures = []
    for case in cases:
        priority = str(case.priority or "P1").upper()
        result = normalize_functional_result(case.test_result)
        if priority == "P0" and result in {"untested", "failed", "blocked"}:
            p0_blockers.append(case.title)
        elif priority == "P1" and result in {"failed", "blocked"}:
            p1_failures.append(case.title)

    impact_failures = [
        item.title
        for item in impact_items
        if normalize_functional_result(item.test_result) in {"failed", "blocked"}
    ]
    data_failures = []
    data_pending = []
    for rule in rules:
        latest = latest_results.get(rule.id)
        if not latest:
            data_pending.append(rule.rule_name)
        elif latest.result != "passed":
            data_failures.append(rule.rule_name)

    reasons = []
    if p0_blockers:
        reasons.append(f"P0 新功能用例未通过或未测试 {len(p0_blockers)} 条")
    if data_failures:
        reasons.append(f"数据核对失败 {len(data_failures)} 条")
    if p1_failures:
        reasons.append(f"P1 新功能用例失败/阻塞 {len(p1_failures)} 条")
    if impact_failures:
        reasons.append(f"关联影响回归失败/阻塞 {len(impact_failures)} 条")
    if data_pending:
        reasons.append(f"还有 {len(data_pending)} 条数据核对未执行")

    if p0_blockers or data_failures:
        decision = "not_recommended"
        decision_text = "不建议上线"
    elif p1_failures or impact_failures:
        decision = "risky"
        decision_text = "有风险上线"
    else:
        decision = "ready"
        decision_text = "可上线"

    return {
        "decision": decision,
        "decision_text": decision_text,
        "summary": "；".join(reasons) if reasons else "新功能、关联影响和数据核对暂无阻断风险",
        "new_feature": {
            "counts": functional_result_counts(cases),
            "p0_blockers": p0_blockers[:10],
            "p1_failures": p1_failures[:10],
        },
        "impact": {
            "counts": functional_result_counts(impact_items),
            "failures": impact_failures[:10],
        },
        "data": {
            "total": len(rules),
            "passed": sum(1 for rule in rules if latest_results.get(rule.id) and latest_results[rule.id].result == "passed"),
            "failed": len(data_failures),
            "pending": len(data_pending),
            "failures": data_failures[:10],
            "pending_rules": data_pending[:10],
        },
    }


def functional_task_detail(db: Session, task: FunctionalTask) -> Dict[str, Any]:
    data = serialize(task)
    project = db.get(Project, task.project_id)
    data["project_name"] = project.name if project else task.project_id
    data.update(account_profile_summary(default_account_profile_for_target(db, "functional_task", task.id, task.project_id)))
    cases = []
    for case in db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id).order_by(FunctionalCase.id.asc()).all():
        item = serialize(case)
        item.update(account_profile_summary(default_account_profile_for_target(db, "functional_case", case.id, task.project_id)))
        cases.append(item)
    data["cases"] = cases
    data["snapshots"] = serialize_many(db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).all())
    data["screenshots"] = serialize_many(
        db.query(FunctionalScreenshot).filter(FunctionalScreenshot.task_id == task.id).order_by(FunctionalScreenshot.id.desc()).all()
    )
    data["requirement_notes"] = serialize_many(
        db.query(FunctionalRequirementNote)
        .filter(FunctionalRequirementNote.task_id == task.id)
        .order_by(FunctionalRequirementNote.id.desc())
        .all()
    )
    data["runs"] = serialize_many(db.query(FunctionalRun).filter(FunctionalRun.task_id == task.id).order_by(FunctionalRun.id.desc()).limit(20).all())
    data["impact_items"] = serialize_many(
        db.query(FunctionalImpactItem)
        .filter(FunctionalImpactItem.task_id == task.id)
        .order_by(FunctionalImpactItem.id.asc())
        .all()
    )
    rules = (
        db.query(FunctionalDataCheckRule)
        .filter(FunctionalDataCheckRule.task_id == task.id)
        .order_by(FunctionalDataCheckRule.id.asc())
        .all()
    )
    data_rules = []
    for rule in rules:
        item = serialize(rule)
        latest = (
            db.query(FunctionalDataCheckResult)
            .filter(FunctionalDataCheckResult.rule_id == rule.id)
            .order_by(FunctionalDataCheckResult.id.desc())
            .first()
        )
        item["latest_result"] = serialize(latest) if latest else None
        data_rules.append(item)
    data["data_check_rules"] = data_rules
    data["data_check_results"] = serialize_many(
        db.query(FunctionalDataCheckResult)
        .filter(FunctionalDataCheckResult.task_id == task.id)
        .order_by(FunctionalDataCheckResult.id.desc())
        .limit(20)
        .all()
    )
    data["conclusion"] = functional_task_conclusion_summary(db, task)
    data["preflight_summary"] = functional_package_preflight_summary(cases)
    return data


QUALITY_EXECUTABLE = "executable"
QUALITY_UNCHECKED = "unchecked"
QUALITY_AUTH_RISK = "auth_risk"
QUALITY_MISSING_VARIABLES = "missing_variables"
QUALITY_LOCATOR_RISK = "locator_risk"
QUALITY_NEEDS_REVIEW = "needs_review"
QUALITY_NOT_RECOMMENDED = "not_recommended"

ASSERTION_ACTIONS = {"assert_url", "assert_visible", "assert_value", "text_assert"}
LOCATOR_REQUIRED_ACTIONS = {"input", "click", "wait_for_selector", "text_assert", "select", "check", "uncheck", "assert_visible", "assert_value"}
BUILTIN_RUNTIME_VARS = {
    "timestamp",
    "datetime",
    "date",
    "uuid",
    "random_int",
    "random_str",
    "random_phone",
    "random_email",
}
ACCOUNT_RUNTIME_VARS = {
    "username",
    "account",
    "email",
    "mobile",
    "phone",
    "password",
    "code",
    "captcha",
    "captcha_code",
    "verify_code",
    "verification_code",
}
SEARCH_SEED_KEYS = {
    "customer_id": ["customer_id", "customerId", "client_id", "clientId"],
    "customer_name": ["customer_name", "customerName", "client_name", "clientName"],
    "orderNumber": ["orderNumber", "order_no", "orderNo", "order_sn", "orderSn"],
    "box_no": ["box_no", "boxNo", "box_number", "boxNumber"],
    "location_code": ["location_code", "locationCode", "warehouse_location", "storage_location"],
    "startDate": ["startDate", "start_date"],
    "endDate": ["endDate", "end_date"],
}
SEARCH_KEYWORDS = {
    "customer_id": ["客户ID", "客户id", "客户编号", "客户号", "customer id", "customer_id"],
    "customer_name": ["客户名称", "客户名", "客户姓名", "customer name", "customer_name"],
    "orderNumber": ["订单号", "订单编号", "订单SN", "order number", "order_no", "order_sn"],
    "box_no": ["箱号", "箱子编号", "box no", "box_no", "box number"],
    "location_code": ["库位", "仓位", "location", "location_code"],
    "startDate": ["开始日期", "开始时间", "start date", "startDate"],
    "endDate": ["结束日期", "结束时间", "end date", "endDate"],
}


def normalize_variable_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def quality_report_payload(status_value: str, reason: str, issues: list[str] | None = None, **extra: Any) -> Dict[str, Any]:
    payload = {
        "status": status_value,
        "reason": reason,
        "issues": issues or [],
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    payload.update(extra)
    return payload


def parse_case_steps(raw: Any) -> list[Dict[str, Any]]:
    parsed = parse_json_value(raw or "", [])
    if isinstance(parsed, dict):
        parsed = parsed.get("steps") or parsed.get("actions") or []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def functional_case_ui_payload(db: Session, case: FunctionalCase) -> tuple[UiCase | None, list[Dict[str, Any]]]:
    ui_case = db.get(UiCase, case.ui_case_id) if case.ui_case_id else None
    if not ui_case:
        return None, []
    return ui_case, parse_case_steps(ui_case.steps)


def case_has_business_assertion(case: FunctionalCase, steps: list[Dict[str, Any]]) -> bool:
    for step in steps:
        action = str(step.get("action") or "").strip().lower()
        if action in ASSERTION_ACTIONS:
            locator = str(step.get("locator") or "").strip().lower()
            value = str(step.get("value") or "").strip()
            if action == "text_assert" and locator in {"", "body", "html"} and len(value) < 2:
                continue
            return True
        condition = step.get("success_condition") or step.get("expected") or step.get("assert")
        if isinstance(condition, (dict, list)) and condition:
            return True
        if isinstance(condition, str) and condition.strip():
            return True
    expected = str(case.expected or "").strip()
    return bool(expected and expected not in {"页面正常显示", "操作成功", "成功"})


def case_locator_issues(steps: list[Dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for index, step in enumerate(steps, start=1):
        action = str(step.get("action") or "").strip().lower()
        locator = str(step.get("locator") or "").strip()
        if action in LOCATOR_REQUIRED_ACTIONS and not locator:
            issues.append(f"第{index}步 {action} 缺少 locator")
    return issues


def placeholder_names(text: str) -> list[str]:
    names = re.findall(r"\{\{\s*([A-Za-z_][A-Za-z0-9_$]*)\s*\}\}", text or "")
    result: list[str] = []
    seen: set[str] = set()
    for name in names:
        clean = name.replace("$", "")
        norm = normalize_variable_name(clean)
        if not norm or norm in seen or clean in BUILTIN_RUNTIME_VARS or clean in ACCOUNT_RUNTIME_VARS:
            continue
        seen.add(norm)
        result.append(clean)
    return result


def seed_has_key(seed_variables: Dict[str, Any], name: str) -> bool:
    target = normalize_variable_name(name)
    if not target:
        return True
    for key, value in (seed_variables or {}).items():
        if value in ("", None):
            continue
        if normalize_variable_name(key) == target:
            return True
    for canonical, aliases in SEARCH_SEED_KEYS.items():
        alias_norms = {normalize_variable_name(item) for item in [canonical, *aliases]}
        if target in alias_norms:
            return any(seed_variables.get(alias) not in ("", None) for alias in [canonical, *aliases])
    return False


def case_required_seed_keys(case: FunctionalCase, steps: list[Dict[str, Any]]) -> list[str]:
    raw_text = " ".join(
        [
            case.title or "",
            case.precondition or "",
            case.steps or "",
            case.expected or "",
            json.dumps(steps, ensure_ascii=False, default=str),
        ]
    )
    lower_text = raw_text.lower()
    needed: list[str] = placeholder_names(raw_text)
    if any(keyword in raw_text for keyword in ["搜索", "查询", "筛选"]) or "search" in lower_text:
        for seed_key, keywords in SEARCH_KEYWORDS.items():
            if any(keyword.lower() in lower_text for keyword in keywords):
                needed.append(seed_key)
    if re.search(r"\b(CUST|ORDER|BOX)[-_]?\d{3,}\b", raw_text, flags=re.IGNORECASE):
        if "customer_id" not in needed and re.search(r"\bCUST[-_]?\d{3,}\b", raw_text, flags=re.IGNORECASE):
            needed.append("customer_id")
        if "orderNumber" not in needed and re.search(r"\bORDER[-_]?\d{3,}\b", raw_text, flags=re.IGNORECASE):
            needed.append("orderNumber")
        if "box_no" not in needed and re.search(r"\bBOX[-_]?\d{3,}\b", raw_text, flags=re.IGNORECASE):
            needed.append("box_no")
    unique: list[str] = []
    seen: set[str] = set()
    for item in needed:
        norm = normalize_variable_name(item)
        if norm and norm not in seen:
            seen.add(norm)
            unique.append(item)
    return unique


def first_pattern_value(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if match:
            value = match.group(1) if match.groups() else match.group(0)
            value = str(value or "").strip(" ：:，,。;；\n\r\t")
            if value:
                return value[:80]
    return ""


def clean_seed_value(value: str, value_type: str) -> str:
    text = str(value or "").strip(" ：:，,。;；\n\r\t")
    if not text:
        return ""
    lower = text.lower()
    fake_values = {
        "cust123456",
        "customer123456",
        "order123456",
        "ord123456",
        "box123456",
        "test123456",
        "boxkeyword",
        "orderstatusmap",
    }
    if lower in fake_values or lower.endswith(("keyword", "map", "placeholder")):
        return ""
    if "{{" in text or "}}" in text:
        return ""
    if value_type in {"customer_id", "order_no", "box_no", "location_code"} and not re.search(r"\d", text):
        return ""
    if value_type == "customer_name" and any(keyword in text for keyword in ["搜索", "筛选", "查询", "页面", "功能", "测试"]):
        return ""
    return text[:80]


def build_functional_seed_text(db: Session, task: FunctionalTask) -> tuple[str, list[str]]:
    chunks: list[str] = []
    sources: list[str] = []
    snapshot = (
        db.query(PageSnapshot)
        .filter(PageSnapshot.task_id == task.id)
        .order_by(PageSnapshot.id.desc())
        .first()
    )
    if snapshot and snapshot.dom_summary:
        chunks.append(snapshot.dom_summary)
        sources.append("page_snapshot")
    ui_ids = [
        row[0]
        for row in db.query(FunctionalCase.ui_case_id)
        .filter(FunctionalCase.task_id == task.id, FunctionalCase.ui_case_id.isnot(None))
        .all()
        if row[0]
    ]
    if ui_ids:
        records = (
            db.query(TestRecord)
            .filter(TestRecord.case_type == "ui", TestRecord.case_id.in_(ui_ids))
            .order_by(TestRecord.id.desc())
            .limit(20)
            .all()
        )
        for record in records:
            if record.log:
                chunks.append(record.log)
        if records:
            sources.append("recent_ui_records")
    return "\n".join(chunks), sources


def seed_functional_package_data(db: Session, task: FunctionalTask) -> Dict[str, Any]:
    text, sources = build_functional_seed_text(db, task)
    variables: Dict[str, Any] = {}
    customer_id = first_pattern_value(
        text,
        [
            r"(?:客户ID|客户Id|客户id|客户编号|客户号)\s*[:：]?\s*([A-Za-z0-9_-]{3,32})",
            r"\b(CUST[-_]?[A-Za-z0-9]{3,24})\b",
        ],
    )
    if customer_id:
        customer_id = clean_seed_value(customer_id, "customer_id")
    if customer_id:
        variables.update({"customer_id": customer_id, "customerId": customer_id})
    customer_name = first_pattern_value(
        text,
        [
            r"(?:客户名称|客户名|客户姓名)\s*[:：]?\s*([\u4e00-\u9fffA-Za-z0-9_\- ]{2,40})",
        ],
    )
    if customer_name:
        customer_name = clean_seed_value(customer_name, "customer_name")
    if customer_name:
        variables.update({"customer_name": customer_name, "customerName": customer_name})
    order_no = first_pattern_value(
        text,
        [
            r"(?:订单号|订单编号|订单SN|order[_ -]?(?:no|number|sn))\s*[:：]?\s*([A-Z0-9][A-Z0-9_-]{5,40})",
            r"\b(ORDER[-_]?[A-Z0-9]{5,36})\b",
        ],
    )
    if order_no:
        order_no = clean_seed_value(order_no, "order_no")
    if order_no:
        variables.update({"orderNumber": order_no, "order_no": order_no, "orderNo": order_no, "order_sn": order_no})
    box_no = first_pattern_value(
        text,
        [
            r"(?:箱号|箱子编号|box[_ -]?(?:no|number))\s*[:：]?\s*([A-Z0-9][A-Z0-9_-]{4,40})",
            r"\b(BOX[-_]?[A-Z0-9]{4,36})\b",
        ],
    )
    if box_no:
        box_no = clean_seed_value(box_no, "box_no")
    if box_no:
        variables.update({"box_no": box_no, "boxNo": box_no, "box_number": box_no})
    location_code = first_pattern_value(
        text,
        [
            r"(?:库位|仓位|location(?:_code)?)\s*[:：]?\s*([A-Z0-9][A-Z0-9_-]{2,32})",
        ],
    )
    if location_code:
        location_code = clean_seed_value(location_code, "location_code")
    if location_code:
        variables.update({"location_code": location_code, "locationCode": location_code, "warehouse_location": location_code})
    dates = re.findall(r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2})", text or "")
    if dates:
        variables.update({"startDate": dates[0], "start_date": dates[0]})
        variables.update({"endDate": dates[-1], "end_date": dates[-1]})
    return {"variables": variables, "sources": sources, "source_text_available": bool(text)}


def account_preflight_status(
    db: Session,
    task: FunctionalTask,
    payload: FunctionalExecuteRequest | None,
) -> Dict[str, Any]:
    account_mode = (payload.account_mode if payload else "default") or "default"
    if account_mode == "none":
        return {"status": "skipped", "message": "本次选择不使用测试账号"}
    try:
        variables, execution_context = resolve_execution_account(
            db,
            payload,
            "functional_task",
            task.id,
            task.project_id,
            task.target_url,
        )
    except Exception as exc:
        return {"status": "blocked", "message": f"账号解析失败：{exc}"}
    if not execution_context.get("login_required"):
        return {"status": "warning", "message": "未绑定测试账号，预检按公开页面处理"}
    login_config = execution_context.get("login_config") or {}
    login_url = str(login_config.get("login_url") or "").strip() or guess_functional_login_url(task.target_url)
    has_username = any(str(variables.get(key) or "").strip() for key in ["username", "account", "email", "mobile", "phone"])
    has_password = any(str(variables.get(key) or "").strip() for key in ["password", "pwd"])
    missing = []
    if not login_url:
        missing.append("登录页URL")
    if not has_username:
        missing.append("登录账号")
    if not has_password:
        missing.append("登录密码")
    if missing:
        return {
            "status": "blocked",
            "message": "登录前置缺失：" + "、".join(missing),
            "account_profile_id": execution_context.get("account_profile_id"),
            "login_url": login_url,
        }
    return {
        "status": "ready",
        "message": "测试账号信息完整，正式执行时会先登录并复用登录态",
        "account_profile_id": execution_context.get("account_profile_id"),
        "login_url": login_url,
    }


def guess_functional_login_url(target_url: str | None) -> str:
    raw = str(target_url or "").strip()
    try:
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return ""
        if parsed.fragment and "/" in parsed.fragment:
            hash_prefix = "#!/" if parsed.fragment.startswith("!/") else "#/"
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}{hash_prefix}login"
        return f"{parsed.scheme}://{parsed.netloc}/login"
    except Exception:
        return ""


def evaluate_functional_case_quality(
    db: Session,
    task: FunctionalTask,
    case: FunctionalCase,
    seed_variables: Dict[str, Any],
    account_status: Dict[str, Any],
) -> Dict[str, Any]:
    if case.automation_status != "approved":
        return quality_report_payload(QUALITY_NOT_RECOMMENDED, "用例未确认，不进入自动执行")
    if not case.ui_case_id:
        return quality_report_payload(QUALITY_NOT_RECOMMENDED, "尚未生成 UI 步骤")
    ui_case, steps = functional_case_ui_payload(db, case)
    if not ui_case:
        return quality_report_payload(QUALITY_NOT_RECOMMENDED, "关联 UI 用例不存在")
    if account_status.get("status") == "blocked":
        return quality_report_payload(QUALITY_AUTH_RISK, account_status.get("message") or "登录前置未通过")
    if not steps:
        return quality_report_payload(QUALITY_NOT_RECOMMENDED, "UI 步骤为空，无法自动执行")
    locator_issues = case_locator_issues(steps)
    if locator_issues:
        return quality_report_payload(QUALITY_LOCATOR_RISK, "存在缺失 locator 的步骤", locator_issues)
    required_seed_keys = case_required_seed_keys(case, steps)
    missing_seed = [item for item in required_seed_keys if not seed_has_key(seed_variables, item)]
    if missing_seed:
        return quality_report_payload(
            QUALITY_MISSING_VARIABLES,
            "搜索/筛选类用例缺少真实业务数据样本",
            [f"缺少真实数据：{item}" for item in missing_seed],
            required_seed_keys=required_seed_keys,
        )
    if not case_has_business_assertion(case, steps):
        return quality_report_payload(
            QUALITY_NEEDS_REVIEW,
            "缺少明确业务断言，不能自动标记为可信通过",
            ["请补充 assert_url/assert_visible/assert_value/text_assert 或成功条件"],
        )
    return quality_report_payload(
        QUALITY_EXECUTABLE,
        "账号、步骤、测试数据和业务断言预检通过",
        required_seed_keys=required_seed_keys,
    )


def functional_package_preflight_summary(cases: list[Dict[str, Any]]) -> Dict[str, Any]:
    counts = Counter((item.get("quality_status") or QUALITY_UNCHECKED) for item in cases)
    total = len(cases)
    manual_statuses = {QUALITY_NEEDS_REVIEW, QUALITY_MISSING_VARIABLES, QUALITY_LOCATOR_RISK, QUALITY_AUTH_RISK, QUALITY_NOT_RECOMMENDED}
    return {
        "total": total,
        "executable": counts.get(QUALITY_EXECUTABLE, 0),
        "manual_check": sum(counts.get(item, 0) for item in manual_statuses),
        "unchecked": counts.get(QUALITY_UNCHECKED, 0),
        "auth_blocked": counts.get(QUALITY_AUTH_RISK, 0),
        "data_missing": counts.get(QUALITY_MISSING_VARIABLES, 0),
        "locator_risk": counts.get(QUALITY_LOCATOR_RISK, 0),
        "missing_assertion": counts.get(QUALITY_NEEDS_REVIEW, 0),
        "not_automatable": counts.get(QUALITY_NOT_RECOMMENDED, 0),
    }


def preflight_functional_package(
    db: Session,
    task: FunctionalTask,
    payload: FunctionalExecuteRequest | None = None,
    selected_case_ids: list[int] | None = None,
    persist: bool = True,
) -> Dict[str, Any]:
    requested_ids = set(selected_case_ids or [])
    seed_result = seed_functional_package_data(db, task)
    seed_variables = dict(seed_result.get("variables") or {})
    if payload and payload.variables:
        seed_variables.update({key: value for key, value in payload.variables.items() if value not in ("", None)})
    account_status = account_preflight_status(db, task, payload)
    query = db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id)
    if requested_ids:
        query = query.filter(FunctionalCase.id.in_(requested_ids))
    cases = query.order_by(FunctionalCase.id.asc()).all()
    case_items: list[Dict[str, Any]] = []
    for case in cases:
        report = evaluate_functional_case_quality(db, task, case, seed_variables, account_status)
        status_value = str(report.get("status") or QUALITY_UNCHECKED)
        if persist:
            case.quality_status = status_value
            case.quality_report = json.dumps(report, ensure_ascii=False, default=str)
        case_items.append(
            {
                "case_id": case.id,
                "title": case.title,
                "priority": case.priority,
                "automation_status": case.automation_status,
                "quality_status": status_value,
                "reason": report.get("reason") or "",
                "issues": report.get("issues") or [],
            }
        )
    summary = functional_package_preflight_summary(case_items)
    executable_case_ids = [item["case_id"] for item in case_items if item["quality_status"] == QUALITY_EXECUTABLE]
    manual_items = [item for item in case_items if item["quality_status"] != QUALITY_EXECUTABLE]
    page_status = "ready" if db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).first() else "unchecked"
    result = {
        "task_id": task.id,
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "login": account_status,
        "page": {
            "status": page_status,
            "target_url": task.target_url,
            "message": "已有页面快照" if page_status == "ready" else "暂无页面快照，建议先扫描目标页面",
        },
        "seed": seed_result,
        "counts": summary,
        "total": len(case_items),
        "executable_count": len(executable_case_ids),
        "executable_case_ids": executable_case_ids,
        "manual_check_items": manual_items[:80],
    }
    if persist:
        db.commit()
    return result


def functional_task_keywords(task: FunctionalTask) -> list[str]:
    raw = " ".join([task.iteration_name or "", task.requirement_text or "", task.context or "", task.target_url or ""])
    try:
        parsed = urlparse(task.target_url or "")
        raw += " " + parsed.path.replace("/", " ")
    except Exception:
        pass
    tokens = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", raw)
    seen: set[str] = set()
    result = []
    for token in tokens:
        text = token.strip().lower()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result[:30]


def keyword_score(text: str, keywords: Iterable[str]) -> int:
    source = (text or "").lower()
    return sum(1 for keyword in keywords if keyword and keyword in source)


def impact_item_key(item_type: str, ref_id: int | None, title: str, target: str | None = "") -> str:
    return f"{item_type}:{ref_id or ''}:{(title or '').strip().lower()}:{(target or '').strip().lower()}"


def suggest_functional_impact_items(db: Session, task: FunctionalTask) -> list[Dict[str, Any]]:
    keywords = functional_task_keywords(task)
    candidates: list[Dict[str, Any]] = []
    seen: set[str] = set()

    def add_candidate(item: Dict[str, Any]) -> None:
        key = impact_item_key(item.get("item_type") or "", item.get("ref_id"), item.get("title") or "", item.get("target") or "")
        if key in seen:
            return
        seen.add(key)
        candidates.append(item)

    existing_task_ids = [
        row[0]
        for row in db.query(FunctionalTask.id)
        .filter(FunctionalTask.project_id == task.project_id, FunctionalTask.id != task.id)
        .all()
    ]
    if existing_task_ids:
        case_rows = (
            db.query(FunctionalCase, FunctionalTask)
            .join(FunctionalTask, FunctionalCase.task_id == FunctionalTask.id)
            .filter(FunctionalCase.task_id.in_(existing_task_ids))
            .all()
        )
        for case, source_task in case_rows:
            text = " ".join([case.title or "", case.precondition or "", case.steps or "", case.expected or "", source_task.iteration_name or ""])
            score = keyword_score(text, keywords)
            is_history_risk = normalize_functional_result(case.test_result) in {"failed", "blocked"}
            if score <= 0 and not is_history_risk:
                continue
            add_candidate(
                {
                    "item_type": "functional_case",
                    "ref_id": case.id,
                    "title": case.title,
                    "target": f"{source_task.iteration_name} / 用例#{case.id}",
                    "risk_level": "P0" if is_history_risk else (case.priority or "P1"),
                    "source": "history_failed" if is_history_risk else "keyword",
                    "reason": "历史失败/阻塞用例" if is_history_risk else f"命中需求关键词 {score} 个",
                }
            )

    try:
        target_path = urlparse(task.target_url or "").path.strip("/").lower()
    except Exception:
        target_path = ""
    for ui_case in db.query(UiCase).filter(UiCase.project_id == task.project_id).all():
        text = f"{ui_case.case_name or ''} {ui_case.page_url or ''}"
        score = keyword_score(text, keywords)
        same_path = bool(target_path and target_path in (ui_case.page_url or "").lower())
        if score <= 0 and not same_path:
            continue
        add_candidate(
            {
                "item_type": "ui_case",
                "ref_id": ui_case.id,
                "title": ui_case.case_name,
                "target": ui_case.page_url,
                "risk_level": "P1" if same_path else "P2",
                "source": "same_url" if same_path else "keyword",
                "reason": "同页面或同路径相关" if same_path else f"命中需求关键词 {score} 个",
            }
        )

    for api_case in db.query(ApiCase).filter(ApiCase.project_id == task.project_id).all():
        text = f"{api_case.case_name or ''} {api_case.url or ''}"
        score = keyword_score(text, keywords)
        if score <= 0:
            continue
        add_candidate(
            {
                "item_type": "api_case",
                "ref_id": api_case.id,
                "title": api_case.case_name,
                "target": f"{api_case.method} {api_case.url}",
                "risk_level": "P1",
                "source": "keyword",
                "reason": f"接口名称/路径命中需求关键词 {score} 个",
            }
        )

    return candidates[:30]


def normalize_data_check_payload(data: Dict[str, Any], require_name: bool = False) -> Dict[str, Any]:
    if require_name or "rule_name" in data:
        require_non_blank_text(data, "rule_name", "核对规则名称")
    if "check_type" in data and data["check_type"]:
        data["check_type"] = str(data["check_type"]).strip()
    data = normalize_json_fields(data)
    if "api_method" in data and data["api_method"]:
        data["api_method"] = str(data["api_method"]).upper()
    return data


def full_data_check_url(task: FunctionalTask, api_url: str) -> str:
    raw = (api_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return raw
    base = urlparse(task.target_url or "")
    origin = f"{base.scheme}://{base.netloc}" if base.scheme and base.netloc else ""
    return urljoin(origin.rstrip("/") + "/", raw.lstrip("/")) if origin else raw


def lookup_nested_value(payload: Any, path: str) -> Any:
    if not path or path in {"json", "$"}:
        return payload
    current = payload
    parts = [part for part in path.replace("[", ".").replace("]", "").split(".") if part and part != "json"]
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return None
    return current


def extract_response_value(response: requests.Response, value_path: str | None) -> Any:
    path = (value_path or "json").strip()
    if path == "status_code":
        return response.status_code
    if path.lower().startswith("header."):
        return response.headers.get(path.split(".", 1)[1], "")
    if path == "text":
        return response.text
    try:
        payload = response.json()
    except Exception:
        payload = response.text
    return lookup_nested_value(payload, path)


def normalize_compare_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value if value is not None else "")).strip()


def normalize_decimal_value(value: Any) -> Decimal | None:
    text_value = str(value if value is not None else "").strip()
    text_value = re.sub(r"[^\d.\-]", "", text_value.replace(",", ""))
    if not text_value:
        return None
    try:
        return Decimal(text_value).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def compare_data_check_values(rule: FunctionalDataCheckRule, page_value: Any, api_value: Any) -> tuple[bool, str]:
    compare_rule = parse_json_value(rule.compare_rule, {})
    expected_value = rule.expected_value if rule.expected_value not in (None, "") else None
    check_type = rule.check_type or "page_api_consistency"

    left = page_value
    right = api_value
    if check_type == "amount_quantity":
        left_amount = normalize_decimal_value(left)
        right_amount = normalize_decimal_value(right)
        expected_amount = normalize_decimal_value(expected_value) if expected_value is not None else None
        if left_amount is None or right_amount is None:
            return False, "金额/数量无法转换为数字"
        if expected_amount is not None:
            passed = left_amount == expected_amount and right_amount == expected_amount
            return passed, f"页面={left_amount}，接口={right_amount}，预期={expected_amount}"
        return left_amount == right_amount, f"页面={left_amount}，接口={right_amount}"

    if check_type == "status_flow":
        mapping = {}
        if isinstance(compare_rule, dict):
            mapping = compare_rule.get("status_mapping") or compare_rule.get("mapping") or {}
        if isinstance(mapping, dict):
            left = mapping.get(str(left), left)
            right = mapping.get(str(right), right)

    left_text = normalize_compare_text(left)
    right_text = normalize_compare_text(right)
    if expected_value is not None:
        expected_text = normalize_compare_text(expected_value)
        passed = left_text == expected_text and right_text == expected_text
        return passed, f"页面={left_text}，接口={right_text}，预期={expected_text}"
    return left_text == right_text, f"页面={left_text}，接口={right_text}"


def execute_functional_data_check_rule(db: Session, task: FunctionalTask, rule: FunctionalDataCheckRule) -> FunctionalDataCheckResult:
    page_value = rule.page_value or ""
    api_value: Any = ""
    result = "blocked"
    message = ""
    detail: Dict[str, Any] = {}
    try:
        url = full_data_check_url(task, rule.api_url or "")
        if not url:
            raise RuntimeError("接口 URL 不能为空")
        headers = parse_json_value(rule.api_headers, {})
        body_value = parse_json_value(rule.api_body, {})
        body_text = "" if (rule.api_method or "GET").upper() == "GET" else json.dumps(body_value, ensure_ascii=False)
        response = guarded_proxy_request(rule.api_method or "GET", url, headers if isinstance(headers, dict) else {}, body_text, 20)
        api_value = extract_response_value(response, rule.api_value_path)
        passed, message = compare_data_check_values(rule, page_value, api_value)
        result = "passed" if passed else "failed"
        detail = {
            "status_code": response.status_code,
            "api_url": url,
            "api_value_path": rule.api_value_path,
            "compare_type": rule.check_type,
        }
    except Exception as exc:
        message = str(exc)
        detail = {"error": str(exc)}

    record = FunctionalDataCheckResult(
        task_id=task.id,
        rule_id=rule.id,
        result=result,
        page_value=str(page_value),
        api_value=json.dumps(api_value, ensure_ascii=False, default=str) if isinstance(api_value, (dict, list)) else str(api_value),
        message=message,
        detail=json.dumps(detail, ensure_ascii=False, default=str),
        execute_time=datetime.now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


CASE_GENERATION_TEST_RESULTS = {"untested", "passed", "failed", "blocked", "skipped"}
CASE_GENERATION_WORKSPACE_TASK_NAME = "用例生成草稿"
CASE_GENERATION_WORKSPACE_TARGET_NAME = "用例生成"


def case_generation_case_is_protected(item: CaseGenerationCase) -> bool:
    return bool(item.manual_edited) or (item.test_result or "untested") != "untested"


def ensure_case_generation_workspace(db: Session, project_id: int) -> CaseGenerationTask:
    ensure_project_exists(db, project_id)
    task = (
        db.query(CaseGenerationTask)
        .filter(
            CaseGenerationTask.project_id == project_id,
            CaseGenerationTask.task_name == CASE_GENERATION_WORKSPACE_TASK_NAME,
            CaseGenerationTask.target_name == CASE_GENERATION_WORKSPACE_TARGET_NAME,
        )
        .order_by(CaseGenerationTask.id.desc())
        .first()
    )
    if task:
        return task
    task = CaseGenerationTask(
        project_id=project_id,
        task_name=CASE_GENERATION_WORKSPACE_TASK_NAME,
        target_name=CASE_GENERATION_WORKSPACE_TARGET_NAME,
        target_url="",
        requirement_text="",
        context="",
        status="draft",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def case_generation_serialize_json(value: Any) -> str:
    return json.dumps(value or [], ensure_ascii=False)


def apply_case_generation_ocr_material(screenshot: CaseGenerationScreenshot, analysis_result: str) -> None:
    payload = parse_json_value(analysis_result, {})
    material = payload.get("ocr_material") if isinstance(payload, dict) else {}
    if not isinstance(material, dict):
        material = {}
    screenshot.ocr_text = str(material.get("ocr_text") or "")
    try:
        screenshot.ocr_confidence = float(material.get("ocr_confidence") or 0)
    except (TypeError, ValueError):
        screenshot.ocr_confidence = 0
    screenshot.low_confidence_items = case_generation_serialize_json(material.get("low_confidence_items"))
    screenshot.regions = case_generation_serialize_json(material.get("regions"))
    screenshot.needs_manual_confirm = 1 if material.get("needs_manual_confirm", True) else 0
    screenshot.ocr_error = str(material.get("ocr_error") or "")


def case_generation_task_proxy(task: CaseGenerationTask) -> SimpleNamespace:
    target = task.target_url or task.target_name or ""
    return SimpleNamespace(
        id=task.id,
        project_id=task.project_id,
        iteration_name=task.task_name,
        target_url=target,
        requirement_text=task.requirement_text or "",
        context=task.context or "",
        status=task.status,
    )


def case_generation_source_refs(
    screenshots: Iterable[CaseGenerationScreenshot],
    notes: Iterable[CaseGenerationRequirementNote],
) -> str:
    payload = {
        "screenshots": [item.id for item in screenshots],
        "notes": [item.id for item in notes],
        "initial_requirement": True,
    }
    return json.dumps(payload, ensure_ascii=False)


def case_generation_refs_include_screenshot(item: CaseGenerationCase, screenshot_id: int) -> bool:
    refs = parse_json_value(item.source_refs, {})
    values = refs.get("screenshots") if isinstance(refs, dict) else []
    return str(screenshot_id) in {str(value) for value in (values or [])}


def case_generation_refs_include_note(item: CaseGenerationCase, note_id: int) -> bool:
    refs = parse_json_value(item.source_refs, {})
    values = refs.get("notes") if isinstance(refs, dict) else []
    return str(note_id) in {str(value) for value in (values or [])}


def case_generation_stats(cases: Iterable[CaseGenerationCase]) -> Dict[str, int]:
    stats = {key: 0 for key in ["total", "untested", "passed", "failed", "blocked", "skipped"]}
    for item in cases:
        stats["total"] += 1
        result = item.test_result or "untested"
        if result not in CASE_GENERATION_TEST_RESULTS:
            result = "untested"
        stats[result] += 1
    return stats


def case_generation_detail(db: Session, task: CaseGenerationTask) -> Dict[str, Any]:
    data = serialize(task)
    project = db.get(Project, task.project_id)
    data["project_name"] = project.name if project else task.project_id
    screenshots = (
        db.query(CaseGenerationScreenshot)
        .filter(CaseGenerationScreenshot.task_id == task.id)
        .order_by(CaseGenerationScreenshot.id.desc())
        .all()
    )
    notes = (
        db.query(CaseGenerationRequirementNote)
        .filter(CaseGenerationRequirementNote.task_id == task.id)
        .order_by(CaseGenerationRequirementNote.id.desc())
        .all()
    )
    cases = (
        db.query(CaseGenerationCase)
        .filter(CaseGenerationCase.task_id == task.id)
        .order_by(CaseGenerationCase.id.asc())
        .all()
    )
    data["screenshots"] = serialize_many(screenshots)
    data["requirement_notes"] = serialize_many(notes)
    data["cases"] = serialize_many(cases)
    data["stats"] = case_generation_stats(cases)
    return data


def remove_uploaded_case_generation_file(raw_path: str | None) -> None:
    if not raw_path:
        return
    try:
        path = Path(raw_path)
        if not path.is_absolute():
            path = BASE_DIR / path
        resolved = path.resolve()
        reports_dir = (BASE_DIR / "reports").resolve()
        if resolved.exists() and resolved.is_file() and (resolved == reports_dir or reports_dir in resolved.parents):
            resolved.unlink()
    except Exception:
        pass


def case_generation_screenshot_impact(db: Session, screenshot: CaseGenerationScreenshot) -> Dict[str, int]:
    impacted = [
        item
        for item in db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == screenshot.task_id).all()
        if case_generation_refs_include_screenshot(item, screenshot.id)
    ]
    deletable = [item for item in impacted if not case_generation_case_is_protected(item)]
    protected = [item for item in impacted if case_generation_case_is_protected(item)]
    return {
        "total": len(impacted),
        "deletable": len(deletable),
        "protected": len(protected),
    }


def ensure_case_generation_task(db: Session, task_id: int) -> CaseGenerationTask:
    return get_or_404(db, CaseGenerationTask, task_id)


@app.get("/api/case-generation/workspace")
def get_case_generation_workspace(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = ensure_case_generation_workspace(db, project_id)
    return case_generation_detail(db, task)


@app.post("/api/case-generation/workspace/upload-screenshots")
async def upload_case_generation_workspace_screenshots(
    project_id: int = Query(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_workspace(db, project_id)
    uploaded: list[Dict[str, Any]] = []
    errors: list[str] = []
    for file in files:
        content = await file.read()
        if not content:
            errors.append(f"{file.filename}: 文件为空")
            continue
        try:
            image_path = store_functional_screenshot_file(file.filename or "screenshot.png", content)
        except ValueError as exc:
            errors.append(f"{file.filename}: {exc}")
            continue
        screenshot = CaseGenerationScreenshot(
            task_id=task.id,
            image_path=image_path,
            analysis_result="",
            ocr_text="",
            corrected_text="",
            ocr_confidence=0,
            low_confidence_items="[]",
            regions="[]",
            needs_manual_confirm=1,
            ocr_error="",
            create_time=datetime.now(),
        )
        db.add(screenshot)
        db.flush()
        uploaded.append(serialize(screenshot))
    if not uploaded and errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="；".join(errors[:5]))
    if uploaded:
        task.status = "screenshot_uploaded"
        task.update_time = datetime.now()
    db.commit()
    db.refresh(task)
    return {"uploaded": uploaded, "errors": errors, "workspace": case_generation_detail(db, task)}


@app.post("/api/case-generation/workspace/requirement-notes")
def create_case_generation_workspace_requirement_note(
    project_id: int = Query(...),
    payload: CaseGenerationRequirementNoteCreate = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_workspace(db, project_id)
    data = schema_data(payload)
    note_text = (data.get("note_text") or "").strip()
    if not note_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="补充需求不能为空")
    note = CaseGenerationRequirementNote(
        task_id=task.id,
        note_text=note_text,
        create_time=datetime.now(),
        update_time=None,
    )
    task.status = "requirements_updated"
    task.update_time = datetime.now()
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"note": serialize(note), "workspace": case_generation_detail(db, task)}


@app.post("/api/case-generation/workspace/generate-cases")
def generate_case_generation_workspace_cases(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_workspace(db, project_id)
    return generate_case_generation_cases_for_task(db, task)


@app.post("/api/case-generation/workspace/cases/batch-status")
def batch_update_case_generation_workspace_case_status(
    project_id: int = Query(...),
    payload: CaseGenerationCaseBatchStatusUpdate = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = ensure_case_generation_workspace(db, project_id)
    return batch_update_case_generation_cases_for_task(db, task.id, payload)


@app.get("/api/case-generation/tasks")
def list_case_generation_tasks(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(CaseGenerationTask)
    if project_id is not None:
        query = query.filter(CaseGenerationTask.project_id == project_id)
    return [case_generation_detail(db, item) for item in query.order_by(CaseGenerationTask.id.desc()).all()]


@app.post("/api/case-generation/tasks")
def create_case_generation_task(
    payload: CaseGenerationTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload)
    ensure_project_exists(db, data["project_id"])
    task = CaseGenerationTask(
        project_id=data["project_id"],
        task_name=(data.get("task_name") or "").strip(),
        target_name=(data.get("target_name") or "").strip(),
        target_url=(data.get("target_url") or "").strip(),
        requirement_text=data.get("requirement_text") or "",
        context=data.get("context") or "",
        status=data.get("status") or "draft",
        create_time=datetime.now(),
        update_time=None,
    )
    if not task.task_name or not task.target_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务名称和目标页面/功能不能为空")
    db.add(task)
    db.commit()
    db.refresh(task)
    return case_generation_detail(db, task)


@app.get("/api/case-generation/tasks/{task_id}")
def get_case_generation_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    return case_generation_detail(db, ensure_case_generation_task(db, task_id))


@app.put("/api/case-generation/tasks/{task_id}")
def update_case_generation_task(
    task_id: int,
    payload: CaseGenerationTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_task(db, task_id)
    data = schema_data(payload, exclude_unset=True)
    if "project_id" in data and data["project_id"] is not None:
        ensure_project_exists(db, data["project_id"])
    for field in ["project_id", "task_name", "target_name", "target_url", "requirement_text", "context", "status"]:
        if field in data and data[field] is not None:
            value = data[field]
            if field in {"task_name", "target_name", "target_url"}:
                value = str(value or "").strip()
            setattr(task, field, value)
    if not task.task_name or not task.target_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="任务名称和目标页面/功能不能为空")
    task.update_time = datetime.now()
    db.commit()
    db.refresh(task)
    return case_generation_detail(db, task)


@app.delete("/api/case-generation/tasks/{task_id}")
def delete_case_generation_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    task = ensure_case_generation_task(db, task_id)
    screenshots = db.query(CaseGenerationScreenshot).filter(CaseGenerationScreenshot.task_id == task.id).all()
    for screenshot in screenshots:
        remove_uploaded_case_generation_file(screenshot.image_path)
    db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == task.id).delete(synchronize_session=False)
    db.query(CaseGenerationScreenshot).filter(CaseGenerationScreenshot.task_id == task.id).delete(synchronize_session=False)
    db.query(CaseGenerationRequirementNote).filter(CaseGenerationRequirementNote.task_id == task.id).delete(synchronize_session=False)
    db.delete(task)
    db.commit()
    return {"message": "deleted"}


@app.post("/api/case-generation/tasks/{task_id}/upload-screenshots")
async def upload_case_generation_screenshots(
    task_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_task(db, task_id)
    uploaded: list[Dict[str, Any]] = []
    errors: list[str] = []
    for file in files:
        content = await file.read()
        if not content:
            errors.append(f"{file.filename}: 文件为空")
            continue
        try:
            image_path = store_functional_screenshot_file(file.filename or "screenshot.png", content)
        except ValueError as exc:
            errors.append(f"{file.filename}: {exc}")
            continue
        screenshot = CaseGenerationScreenshot(
            task_id=task.id,
            image_path=image_path,
            analysis_result="",
            ocr_text="",
            corrected_text="",
            ocr_confidence=0,
            low_confidence_items="[]",
            regions="[]",
            needs_manual_confirm=1,
            ocr_error="",
            create_time=datetime.now(),
        )
        db.add(screenshot)
        db.flush()
        uploaded.append(serialize(screenshot))
    if not uploaded and errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="；".join(errors[:5]))
    if uploaded:
        task.status = "screenshot_uploaded"
        task.update_time = datetime.now()
    db.commit()
    db.refresh(task)
    return {"uploaded": uploaded, "errors": errors, "task": case_generation_detail(db, task)}


@app.get("/api/case-generation/screenshots/{screenshot_id}/file")
def get_case_generation_screenshot_file(
    screenshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    screenshot = get_or_404(db, CaseGenerationScreenshot, screenshot_id)
    return safe_file_response(screenshot.image_path)


@app.get("/api/case-generation/screenshots/{screenshot_id}/impact")
def get_case_generation_screenshot_impact(
    screenshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, int]:
    screenshot = get_or_404(db, CaseGenerationScreenshot, screenshot_id)
    return case_generation_screenshot_impact(db, screenshot)


@app.post("/api/case-generation/screenshots/{screenshot_id}/analyze")
def analyze_case_generation_screenshot(
    screenshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    screenshot = get_or_404(db, CaseGenerationScreenshot, screenshot_id)
    task = ensure_case_generation_task(db, screenshot.task_id)
    try:
        screenshot.analysis_result = analyze_functional_screenshot(
            case_generation_task_proxy(task),
            screenshot,
            latest_ai_config(db),
        )
        apply_case_generation_ocr_material(screenshot, screenshot.analysis_result or "")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    task.status = "screenshot_analyzed"
    task.update_time = datetime.now()
    db.commit()
    db.refresh(screenshot)
    return {"screenshot": serialize(screenshot), "task": case_generation_detail(db, task)}


@app.put("/api/case-generation/screenshots/{screenshot_id}/ocr-text")
def update_case_generation_screenshot_ocr_text(
    screenshot_id: int,
    payload: CaseGenerationScreenshotOcrUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    screenshot = get_or_404(db, CaseGenerationScreenshot, screenshot_id)
    task = ensure_case_generation_task(db, screenshot.task_id)
    screenshot.corrected_text = (payload.corrected_text or "").strip()
    screenshot.needs_manual_confirm = 0 if screenshot.corrected_text else screenshot.needs_manual_confirm
    task.update_time = datetime.now()
    db.commit()
    db.refresh(screenshot)
    return {"screenshot": serialize(screenshot), "task": case_generation_detail(db, task)}


@app.delete("/api/case-generation/screenshots/{screenshot_id}")
def delete_case_generation_screenshot(
    screenshot_id: int,
    delete_cases: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    screenshot = get_or_404(db, CaseGenerationScreenshot, screenshot_id)
    task = ensure_case_generation_task(db, screenshot.task_id)
    impacted = [
        item
        for item in db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == task.id).all()
        if case_generation_refs_include_screenshot(item, screenshot.id)
    ]
    deleted_case_ids: list[int] = []
    preserved_case_ids: list[int] = []
    for item in impacted:
        if delete_cases and not case_generation_case_is_protected(item):
            deleted_case_ids.append(item.id)
            db.delete(item)
        else:
            item.source_missing = 1
            item.update_time = datetime.now()
            preserved_case_ids.append(item.id)
    remove_uploaded_case_generation_file(screenshot.image_path)
    db.delete(screenshot)
    task.status = "screenshot_deleted"
    task.update_time = datetime.now()
    db.commit()
    return {
        "message": "deleted",
        "deleted_case_ids": deleted_case_ids,
        "preserved_case_ids": preserved_case_ids,
        "task": case_generation_detail(db, task),
    }


@app.post("/api/case-generation/tasks/{task_id}/requirement-notes")
def create_case_generation_requirement_note(
    task_id: int,
    payload: CaseGenerationRequirementNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_task(db, task_id)
    data = schema_data(payload)
    note_text = (data.get("note_text") or "").strip()
    if not note_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="补充需求不能为空")
    note = CaseGenerationRequirementNote(
        task_id=task.id,
        note_text=note_text,
        create_time=datetime.now(),
        update_time=None,
    )
    task.status = "requirements_updated"
    task.update_time = datetime.now()
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"note": serialize(note), "task": case_generation_detail(db, task)}


@app.put("/api/case-generation/requirement-notes/{note_id}")
def update_case_generation_requirement_note(
    note_id: int,
    payload: CaseGenerationRequirementNoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    note = get_or_404(db, CaseGenerationRequirementNote, note_id)
    task = ensure_case_generation_task(db, note.task_id)
    data = schema_data(payload)
    note_text = (data.get("note_text") or "").strip()
    if not note_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="补充需求不能为空")
    note.note_text = note_text
    note.update_time = datetime.now()
    task.status = "requirements_updated"
    task.update_time = datetime.now()
    db.commit()
    db.refresh(note)
    return {"note": serialize(note), "task": case_generation_detail(db, task)}


@app.delete("/api/case-generation/requirement-notes/{note_id}")
def delete_case_generation_requirement_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    note = get_or_404(db, CaseGenerationRequirementNote, note_id)
    task = ensure_case_generation_task(db, note.task_id)
    for item in db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == task.id).all():
        if case_generation_refs_include_note(item, note.id):
            item.source_missing = 1
            item.update_time = datetime.now()
    db.delete(note)
    task.status = "requirements_updated"
    task.update_time = datetime.now()
    db.commit()
    return {"message": "deleted", "task": case_generation_detail(db, task)}


def generate_case_generation_cases_for_task(db: Session, task: CaseGenerationTask) -> Dict[str, Any]:
    screenshots = (
        db.query(CaseGenerationScreenshot)
        .filter(CaseGenerationScreenshot.task_id == task.id)
        .order_by(CaseGenerationScreenshot.id.asc())
        .all()
    )
    notes = (
        db.query(CaseGenerationRequirementNote)
        .filter(CaseGenerationRequirementNote.task_id == task.id)
        .order_by(CaseGenerationRequirementNote.id.asc())
        .all()
    )
    generated = generate_functional_cases(
        case_generation_task_proxy(task),
        "",
        None,
        latest_ai_config(db),
        screenshots,
        notes,
    )
    for old_case in db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == task.id).all():
        if not case_generation_case_is_protected(old_case):
            db.delete(old_case)
    db.flush()

    batch = uuid4().hex[:12]
    source_refs = case_generation_source_refs(screenshots, notes)
    created = 0
    for item in generated.items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        db.add(
            CaseGenerationCase(
                task_id=task.id,
                title=title[:200],
                precondition=item.get("precondition", ""),
                steps=item.get("steps", ""),
                expected=item.get("expected", ""),
                priority=item.get("priority", "P1"),
                source_refs=source_refs,
                generation_batch=batch,
                manual_edited=0,
                test_result="untested",
                source_missing=0,
                remark="",
                create_time=datetime.now(),
                update_time=None,
            )
        )
        created += 1
    task.status = "cases_generated"
    task.update_time = datetime.now()
    db.commit()
    db.refresh(task)
    return {
        "source": generated.source,
        "warning": generated.warning,
        "created": created,
        "generation_batch": batch,
        "task": case_generation_detail(db, task),
        "workspace": case_generation_detail(db, task),
    }


@app.post("/api/case-generation/tasks/{task_id}/generate-cases")
def generate_case_generation_cases(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = ensure_case_generation_task(db, task_id)
    return generate_case_generation_cases_for_task(db, task)


@app.put("/api/case-generation/cases/{case_id}")
def update_case_generation_case(
    case_id: int,
    payload: CaseGenerationCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    item = get_or_404(db, CaseGenerationCase, case_id)
    data = schema_data(payload, exclude_unset=True)
    for field in ["title", "precondition", "steps", "expected", "priority", "remark"]:
        if field in data and data[field] is not None:
            setattr(item, field, data[field])
    if not item.title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用例标题不能为空")
    item.manual_edited = 1
    item.update_time = datetime.now()
    db.commit()
    db.refresh(item)
    return serialize(item)


@app.delete("/api/case-generation/cases/{case_id}")
def delete_case_generation_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    item = get_or_404(db, CaseGenerationCase, case_id)
    db.delete(item)
    db.commit()
    return {"message": "deleted"}


@app.put("/api/case-generation/cases/{case_id}/status")
def update_case_generation_case_status(
    case_id: int,
    payload: CaseGenerationCaseStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    item = get_or_404(db, CaseGenerationCase, case_id)
    if payload.test_result not in CASE_GENERATION_TEST_RESULTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的测试状态")
    item.test_result = payload.test_result
    item.update_time = datetime.now()
    db.commit()
    db.refresh(item)
    return serialize(item)


def batch_update_case_generation_cases_for_task(
    db: Session,
    task_id: int,
    payload: CaseGenerationCaseBatchStatusUpdate,
) -> Dict[str, Any]:
    if payload.test_result not in CASE_GENERATION_TEST_RESULTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的测试状态")
    updated = (
        db.query(CaseGenerationCase)
        .filter(CaseGenerationCase.task_id == task_id, CaseGenerationCase.id.in_(payload.case_ids or [-1]))
        .update({"test_result": payload.test_result, "update_time": datetime.now()}, synchronize_session="fetch")
    )
    db.commit()
    return {"updated": updated, "test_result": payload.test_result}


@app.post("/api/case-generation/tasks/{task_id}/cases/batch-status")
def batch_update_case_generation_case_status(
    task_id: int,
    payload: CaseGenerationCaseBatchStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    ensure_case_generation_task(db, task_id)
    return batch_update_case_generation_cases_for_task(db, task_id, payload)


@app.get("/api/case-generation/tasks/{task_id}/cases/stats")
def get_case_generation_case_stats(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, int]:
    ensure_case_generation_task(db, task_id)
    cases = db.query(CaseGenerationCase).filter(CaseGenerationCase.task_id == task_id).all()
    return case_generation_stats(cases)


def save_ui_record(db: Session, case: UiCase, passed: bool, log_text: str, report_path: str, screenshot_path: str = "") -> TestRecord:
    record = TestRecord(
        case_type="ui",
        case_id=case.id,
        project_id=case.project_id,
        result="passed" if passed else "failed",
        log=log_text,
        screenshot=screenshot_path,
        report_path=report_path,
        execute_time=datetime.now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    _check_login_rate_limit(request.client.host if request.client else "unknown", payload.username)
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_access_token(user.username)
    return {"access_token": token, "token_type": "bearer", "user": serialize(user)}


@app.get("/api/auth/me")
def me(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return serialize(current_user)


@app.get("/api/dashboard")
def dashboard(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    project_filter = Project.id == project_id if project_id is not None else True
    api_filter = ApiCase.project_id == project_id if project_id is not None else True
    ui_filter = UiCase.project_id == project_id if project_id is not None else True
    latest_records_query = db.query(TestRecord)
    record_count_query = db.query(TestRecord)
    if project_id is not None:
        api_ids = [item.id for item in db.query(ApiCase.id).filter(ApiCase.project_id == project_id).all()]
        ui_ids = [item.id for item in db.query(UiCase.id).filter(UiCase.project_id == project_id).all()]
        record_filter = or_(
            TestRecord.project_id == project_id,
            (TestRecord.case_type == "api") & TestRecord.case_id.in_(api_ids or [-1]),
            (TestRecord.case_type == "ui") & TestRecord.case_id.in_(ui_ids or [-1]),
        )
        latest_records_query = latest_records_query.filter(record_filter)
        record_count_query = record_count_query.filter(record_filter)
    latest_records = latest_records_query.order_by(TestRecord.id.desc()).limit(10).all()
    return {
        "project_count": db.query(Project).filter(project_filter).count(),
        "env_count": db.query(Env).filter(Env.project_id == project_id if project_id is not None else True).count(),
        "api_case_count": db.query(ApiCase).filter(api_filter).count(),
        "ui_case_count": db.query(UiCase).filter(ui_filter).count(),
        "record_count": record_count_query.count(),
        "latest_records": serialize_many(latest_records),
        "role": current_user.role,
    }


@app.get("/api/users")
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> list[Dict[str, Any]]:
    return serialize_many(db.query(User).order_by(User.id.desc()).all())


@app.post("/api/users")
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, Any]:
    data = schema_data(payload)
    ensure_unique_username(db, data["username"])
    user = User(
        username=data["username"],
        password=hash_password(data["password"]),
        role=data["role"],
        create_time=datetime.now(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return serialize(user)


@app.put("/api/users/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    user = get_or_404(db, User, user_id)
    data = schema_data(payload, exclude_unset=True)
    if "username" in data:
        ensure_unique_username(db, data["username"], user_id)
        user.username = data["username"]
    if "password" in data and data["password"]:
        user.password = hash_password(data["password"])
    if "role" in data and data["role"]:
        if user.role == "admin" and data["role"] != "admin" and db.query(User).filter(User.role == "admin").count() <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少保留一个 admin 账号")
        user.role = data["role"]
    db.commit()
    db.refresh(user)
    return serialize(user)


@app.delete("/api/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    user = get_or_404(db, User, user_id)
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除当前登录账号")
    if user.role == "admin" and db.query(User).filter(User.role == "admin").count() <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少保留一个 admin 账号")
    db.delete(user)
    db.commit()
    return {"message": "deleted"}


@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[Dict[str, Any]]:
    projects = []
    for project in db.query(Project).order_by(Project.id.desc()).all():
        item = serialize(project)
        item.update(account_profile_summary(default_account_profile_for_target(db, "project", project.id, project.id)))
        projects.append(item)
    return projects


@app.post("/api/projects")
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = normalize_project_payload(schema_data(payload), require_name=True)
    project = Project(name=data["name"], desc=data.get("desc") or "", create_time=datetime.now())
    db.add(project)
    db.commit()
    db.refresh(project)
    return serialize(project)


@app.put("/api/projects/{project_id}")
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    project = get_or_404(db, Project, project_id)
    data = normalize_project_payload(schema_data(payload, exclude_unset=True))
    for field in ["name", "desc"]:
        if field in data:
            setattr(project, field, data[field])
    db.commit()
    db.refresh(project)
    return serialize(project)


@app.delete("/api/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    project = get_or_404(db, Project, project_id)
    task_ids = [row[0] for row in db.query(FunctionalTask.id).filter(FunctionalTask.project_id == project_id).all()]
    functional_case_rows = (
        db.query(FunctionalCase.id, FunctionalCase.ui_case_id)
        .filter(FunctionalCase.task_id.in_(task_ids))
        .all()
        if task_ids
        else []
    )
    functional_case_ids = [row[0] for row in functional_case_rows]
    generated_ui_ids = [row[1] for row in functional_case_rows if row[1]]
    direct_ui_ids = [row[0] for row in db.query(UiCase.id).filter(UiCase.project_id == project_id).all()]
    ui_ids = sorted(set(direct_ui_ids + generated_ui_ids))
    api_ids = [row[0] for row in db.query(ApiCase.id).filter(ApiCase.project_id == project_id).all()]
    profile_ids = [row[0] for row in db.query(TestAccountProfile.id).filter(TestAccountProfile.project_id == project_id).all()]

    if api_ids:
        db.query(TestRecord).filter(TestRecord.case_type == "api", TestRecord.case_id.in_(api_ids)).delete(synchronize_session=False)
    if ui_ids:
        db.query(TestRecord).filter(TestRecord.case_type == "ui", TestRecord.case_id.in_(ui_ids)).delete(synchronize_session=False)
        db.query(LocatorHealLog).filter(LocatorHealLog.case_id.in_(ui_ids)).delete(synchronize_session=False)

    binding_filters = [
        (TestAccountBinding.target_type == "project") & (TestAccountBinding.target_id == project_id),
    ]
    if task_ids:
        binding_filters.append((TestAccountBinding.target_type == "functional_task") & TestAccountBinding.target_id.in_(task_ids))
    if functional_case_ids:
        binding_filters.append((TestAccountBinding.target_type == "functional_case") & TestAccountBinding.target_id.in_(functional_case_ids))
    if ui_ids:
        binding_filters.append((TestAccountBinding.target_type == "ui_case") & TestAccountBinding.target_id.in_(ui_ids))
    if profile_ids:
        db.query(TestAccountBinding).filter(TestAccountBinding.account_profile_id.in_(profile_ids)).delete(synchronize_session=False)
    db.query(TestAccountBinding).filter(or_(*binding_filters)).delete(synchronize_session=False)

    if task_ids:
        db.query(PageSnapshot).filter(PageSnapshot.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalScreenshot).filter(FunctionalScreenshot.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalRequirementNote).filter(FunctionalRequirementNote.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalRun).filter(FunctionalRun.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalImpactItem).filter(FunctionalImpactItem.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalDataCheckResult).filter(FunctionalDataCheckResult.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalDataCheckRule).filter(FunctionalDataCheckRule.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalCase).filter(FunctionalCase.task_id.in_(task_ids)).delete(synchronize_session=False)
        db.query(FunctionalTask).filter(FunctionalTask.id.in_(task_ids)).delete(synchronize_session=False)
    if ui_ids:
        db.query(UiCase).filter(UiCase.id.in_(ui_ids)).delete(synchronize_session=False)
    if api_ids:
        db.query(ApiCase).filter(ApiCase.id.in_(api_ids)).delete(synchronize_session=False)
    if profile_ids:
        db.query(TestAccountProfile).filter(TestAccountProfile.id.in_(profile_ids)).delete(synchronize_session=False)

    db.query(Env).filter(Env.project_id == project_id).delete(synchronize_session=False)
    db.query(ActionTemplate).filter(ActionTemplate.project_id == project_id).delete(synchronize_session=False)
    db.delete(project)
    db.commit()
    return {"message": "deleted"}

SENSITIVE_ACCOUNT_KEY_RE = re.compile(r"(password|passwd|pwd|captcha|token|secret|authorization|auth|密码|验证码)", re.I)
SENSITIVE_ACCOUNT_KEY_NAMES = {"code", "verify_code", "verification_code", "captcha_code"}


def is_sensitive_account_key(key: Any) -> bool:
    text = str(key or "").strip()
    return text.lower() in SENSITIVE_ACCOUNT_KEY_NAMES or bool(SENSITIVE_ACCOUNT_KEY_RE.search(text))


def mask_variables(variables: Dict[str, Any]) -> Dict[str, Any]:
    return {key: ("***" if is_sensitive_account_key(key) else value) for key, value in (variables or {}).items()}


def account_cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(str(SECRET_KEY).encode("utf-8")).digest())
    return Fernet(key)


def encrypt_account_payload(values: Dict[str, Any]) -> str:
    if not values:
        return ""
    raw = json.dumps(values, ensure_ascii=False, default=str).encode("utf-8")
    return account_cipher().encrypt(raw).decode("utf-8")


def decrypt_account_payload(value: str | None) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        decrypted = account_cipher().decrypt(str(value).encode("utf-8")).decode("utf-8")
        return parse_json_value(decrypted, {})
    except (InvalidToken, ValueError, TypeError):
        legacy = parse_json_value(str(value), {})
        return legacy if isinstance(legacy, dict) else {}


def normalize_account_payload(db: Session, data: Dict[str, Any], existing: TestAccountProfile | None = None) -> Dict[str, Any]:
    if "profile_name" in data and data["profile_name"] is not None:
        data["profile_name"] = str(data["profile_name"]).strip()
        if not data["profile_name"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号档案名称不能为空")
    if "project_id" in data and data["project_id"] is not None:
        ensure_project_exists(db, int(data["project_id"]))
        data["project_id"] = int(data["project_id"])
    for field in ACCOUNT_CONFIG_FIELDS:
        if field in data and data[field] is not None:
            data[field] = str(data[field]).strip()
    public_source = data.pop("variables", None)
    sensitive_source = data.pop("sensitive_variables", None)
    if public_source is not None or sensitive_source is not None:
        public_values: Dict[str, Any] = (
            parse_json_value(existing.variables or "", {}) if existing is not None and public_source is None else {}
        )
        if not isinstance(public_values, dict):
            public_values = {}
        sensitive_values: Dict[str, Any] = (
            decrypt_account_payload(existing.sensitive_variables) if existing is not None and sensitive_source is None else {}
        )
        sensitive_changed = sensitive_source is not None
        if public_source is not None:
            for key, value in dict(public_source or {}).items():
                if value is None:
                    continue
                if is_sensitive_account_key(key):
                    sensitive_values[str(key)] = value
                    sensitive_changed = True
                else:
                    public_values[str(key)] = value
        for key, value in dict(sensitive_source or {}).items():
            if value is not None:
                sensitive_values[str(key)] = value
        data["variables"] = to_json_text(public_values, {})
        if sensitive_changed:
            data["sensitive_variables"] = encrypt_account_payload(sensitive_values)
    elif existing is not None:
        data.pop("variables", None)
        data.pop("sensitive_variables", None)
    if "status" in data and data["status"]:
        data["status"] = str(data["status"])
    return data


def serialize_account_profile(profile: TestAccountProfile) -> Dict[str, Any]:
    public_values = parse_json_value(profile.variables or "", {})
    if not isinstance(public_values, dict):
        public_values = {}
    sensitive_values = decrypt_account_payload(profile.sensitive_variables)
    masked = {**public_values, **{key: "***" for key in sensitive_values.keys()}}
    return {
        "id": profile.id,
        "project_id": profile.project_id,
        "profile_name": profile.profile_name,
        "variables": public_values,
        "masked_variables": masked,
        "sensitive_keys": sorted(sensitive_values.keys()),
        "login_url": profile.login_url or "",
        "username_locator": profile.username_locator or "",
        "password_locator": profile.password_locator or "",
        "submit_locator": profile.submit_locator or "",
        "success_url_contains": profile.success_url_contains or "",
        "success_selector": profile.success_selector or "",
        "status": profile.status,
        "create_time": profile.create_time.strftime("%Y-%m-%d %H:%M:%S") if profile.create_time else "",
        "update_time": profile.update_time.strftime("%Y-%m-%d %H:%M:%S") if profile.update_time else "",
    }


def account_profile_variables(db: Session, profile_id: int, project_id: int | None) -> tuple[Dict[str, Any], Dict[str, Any]]:
    profile = get_or_404(db, TestAccountProfile, profile_id)
    if profile.status != "active":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号档案未启用")
    if profile.project_id is not None and project_id is not None and profile.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="账号档案不属于当前项目")
    public_values = parse_json_value(profile.variables or "", {})
    if not isinstance(public_values, dict):
        public_values = {}
    variables = {**public_values, **decrypt_account_payload(profile.sensitive_variables)}
    login_config = {field: getattr(profile, field) or "" for field in ACCOUNT_CONFIG_FIELDS}
    return variables, {"id": profile.id, "profile_name": profile.profile_name, "login_config": login_config}


def account_target_project_id(db: Session, target_type: str, target_id: int) -> int:
    if target_type == "project":
        ensure_project_exists(db, target_id)
        return target_id
    elif target_type == "functional_task":
        item = get_or_404(db, FunctionalTask, target_id)
        return item.project_id
    elif target_type == "functional_case":
        item = get_or_404(db, FunctionalCase, target_id)
        task = get_or_404(db, FunctionalTask, item.task_id)
        return task.project_id
    elif target_type == "ui_case":
        item = get_or_404(db, UiCase, target_id)
        return item.project_id
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的账号绑定目标")


def account_binding_profile(db: Session, target_type: str, target_id: int) -> TestAccountProfile | None:
    binding = db.query(TestAccountBinding).filter(
        TestAccountBinding.target_type == target_type,
        TestAccountBinding.target_id == target_id,
    ).first()
    if not binding or not binding.account_profile_id:
        return None
    return db.get(TestAccountProfile, binding.account_profile_id)


def account_profile_summary(profile: TestAccountProfile | None) -> Dict[str, Any]:
    if not profile:
        return {"account_profile_id": None, "account_profile_name": ""}
    return {"account_profile_id": profile.id, "account_profile_name": profile.profile_name}


def default_account_profile_for_target(
    db: Session,
    target_type: str,
    target_id: int,
    project_id: int | None,
) -> TestAccountProfile | None:
    if target_type == "functional_case":
        case_profile = account_binding_profile(db, "functional_case", target_id)
        if case_profile:
            return case_profile
        functional_case = db.get(FunctionalCase, target_id)
        if functional_case:
            task_profile = account_binding_profile(db, "functional_task", functional_case.task_id)
            if task_profile:
                return task_profile
    elif target_type in {"functional_task", "ui_case"}:
        direct_profile = account_binding_profile(db, target_type, target_id)
        if direct_profile:
            return direct_profile
    if project_id is not None:
        project_profile = account_binding_profile(db, "project", project_id)
        if project_profile:
            return project_profile
        project_profiles = (
            db.query(TestAccountProfile)
            .filter(TestAccountProfile.project_id == project_id, TestAccountProfile.status == "active")
            .order_by(TestAccountProfile.id.asc())
            .all()
        )
        if len(project_profiles) == 1:
            return project_profiles[0]
    return None


def resolve_execution_account(
    db: Session,
    payload: FunctionalExecuteRequest | None,
    target_type: str,
    target_id: int,
    project_id: int | None,
    target_url: str,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    runtime_vars = dict(payload.variables if payload else {})
    account_mode = (payload.account_mode if payload else "default") or "default"
    if account_mode == "none":
        return runtime_vars, {}
    profile: TestAccountProfile | None = None
    if account_mode == "override":
        if payload and payload.account_profile_id:
            profile = get_or_404(db, TestAccountProfile, payload.account_profile_id)
        else:
            return runtime_vars, {}
    else:
        profile = default_account_profile_for_target(db, target_type, target_id, project_id)
    if not profile:
        return runtime_vars, {}
    account_vars, meta = account_profile_variables(db, profile.id, project_id)
    variables = {**account_vars, **runtime_vars}
    execution_context = {
        "login_required": True,
        "account_profile_id": profile.id,
        "login_config": meta.get("login_config") or {},
        "target_url": target_url,
    }
    return variables, execution_context


def save_test_account_binding(db: Session, target_type: str, target_id: int, account_profile_id: int | None) -> None:
    existing = db.query(TestAccountBinding).filter(
        TestAccountBinding.target_type == target_type,
        TestAccountBinding.target_id == target_id,
    ).first()
    if existing and account_profile_id is not None:
        existing.account_profile_id = account_profile_id
        existing.update_time = datetime.now()
    elif existing and account_profile_id is None:
        db.delete(existing)
    elif not existing and account_profile_id is not None:
        db.add(TestAccountBinding(
            target_type=target_type,
            target_id=target_id,
            account_profile_id=account_profile_id,
            create_time=datetime.now(),
            update_time=None,
        ))
    else:
        return
    db.flush()


@app.get("/api/test-accounts")
def list_test_accounts(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(TestAccountProfile)
    if project_id is not None:
        ensure_project_exists(db, project_id)
        query = query.filter(or_(TestAccountProfile.project_id == project_id, TestAccountProfile.project_id.is_(None)))
    if current_user.role != "admin":
        query = query.filter(TestAccountProfile.status == "active")
    return [serialize_account_profile(item) for item in query.order_by(TestAccountProfile.project_id.asc(), TestAccountProfile.id.desc()).all()]


@app.post("/api/test-accounts")
def create_test_account(
    payload: TestAccountProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = normalize_account_payload(db, schema_data(payload))
    profile = TestAccountProfile(
        project_id=data.get("project_id"),
        profile_name=data["profile_name"],
        variables=data.get("variables") or "{}",
        sensitive_variables=data.get("sensitive_variables") or "",
        login_url=data.get("login_url") or "",
        username_locator=data.get("username_locator") or "",
        password_locator=data.get("password_locator") or "",
        submit_locator=data.get("submit_locator") or "",
        success_url_contains=data.get("success_url_contains") or "",
        success_selector=data.get("success_selector") or "",
        status=data.get("status") or "active",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return serialize_account_profile(profile)


@app.put("/api/test-accounts/{account_id}")
def update_test_account(
    account_id: int,
    payload: TestAccountProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    profile = get_or_404(db, TestAccountProfile, account_id)
    data = normalize_account_payload(db, schema_data(payload, exclude_unset=True), profile)
    for field, value in data.items():
        setattr(profile, field, value)
    profile.update_time = datetime.now()
    db.commit()
    db.refresh(profile)
    return serialize_account_profile(profile)


@app.delete("/api/test-accounts/{account_id}")
def delete_test_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    profile = get_or_404(db, TestAccountProfile, account_id)
    db.query(TestAccountBinding).filter(TestAccountBinding.account_profile_id == profile.id).delete(synchronize_session=False)
    db.delete(profile)
    db.commit()
    return {"message": "deleted"}


@app.put("/api/test-account-bindings")
def update_test_account_binding(
    payload: TestAccountBindingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload)
    target_type = str(data["target_type"])
    target_id = int(data["target_id"])
    project_id = account_target_project_id(db, target_type, target_id)
    profile_id = data.get("account_profile_id")
    if profile_id is not None:
        account_profile_variables(db, int(profile_id), project_id)
    save_test_account_binding(db, target_type, target_id, profile_id)
    db.commit()
    profile = db.get(TestAccountProfile, profile_id) if profile_id else None
    return {"profile": serialize_account_profile(profile) if profile else None}


# ─── 操作模板库 ──────────────────────────────────────────


def _serialize_template(template: ActionTemplate) -> Dict[str, Any]:
    return {
        "id": template.id,
        "project_id": template.project_id,
        "name": template.name,
        "description": template.description or "",
        "trigger_keywords": parse_json_value(template.trigger_keywords, []),
        "steps": parse_json_value(template.steps, []),
        "variables": parse_json_value(template.variables, {}),
        "locator_fallbacks": parse_json_value(template.locator_fallbacks, {}),
        "create_time": template.create_time.isoformat(),
    }


@app.get("/api/action-templates")
def list_action_templates(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(ActionTemplate)
    if project_id is not None:
        query = query.filter(ActionTemplate.project_id == project_id)
    return [_serialize_template(t) for t in query.order_by(ActionTemplate.id.desc()).all()]


@app.post("/api/action-templates")
def create_action_template(
    payload: ActionTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload)
    ensure_project_exists(db, data["project_id"])
    require_non_blank_text(data, "name", "模板名称")
    template = ActionTemplate(
        project_id=data["project_id"],
        name=data["name"],
        description=data.get("description", ""),
        trigger_keywords=to_json_text(data.get("trigger_keywords", []), []),
        steps=to_json_text(data.get("steps", []), []),
        variables=to_json_text(data.get("variables", {}), {}),
        locator_fallbacks=to_json_text(data.get("locator_fallbacks", {}), {}),
        create_time=datetime.now(),
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _serialize_template(template)


@app.put("/api/action-templates/{template_id}")
def update_action_template(
    template_id: int,
    payload: ActionTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    template = get_or_404(db, ActionTemplate, template_id)
    data = schema_data(payload, exclude_unset=True)
    if "name" in data:
        require_non_blank_text(data, "name", "模板名称")
    for field in ["name", "description"]:
        if field in data:
            setattr(template, field, data[field])
    for json_field in ["trigger_keywords", "steps", "variables", "locator_fallbacks"]:
        if json_field in data:
            setattr(template, json_field, to_json_text(data[json_field], ACTION_TEMPLATE_JSON_DEFAULTS[json_field]))
    db.commit()
    db.refresh(template)
    return _serialize_template(template)


@app.delete("/api/action-templates/{template_id}")
def delete_action_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    template = get_or_404(db, ActionTemplate, template_id)
    db.delete(template)
    db.commit()
    return {"message": "deleted"}


@app.get("/api/action-templates/{template_id}/test-run")
def test_run_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    template = get_or_404(db, ActionTemplate, template_id)
    steps = parse_json_value(template.steps, [])
    if not steps:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="模板没有步骤")
    try:
        from .executors import execute_ui_case
        ui_case = UiCase(
            id=0,
            project_id=template.project_id,
            case_name=f"[模板测试] {template.name}",
            page_url="",
            steps=to_json_text(steps, []),
            timeout=30,
            status="active",
            create_time=datetime.now(),
        )
        passed, log_text, screenshot_path, report_path = execute_ui_case(ui_case, {})
        return {"passed": passed, "log": log_text, "screenshot": screenshot_path}
    except Exception as exc:
        return {"passed": False, "log": str(exc), "screenshot": ""}


# ─── Locator 自愈记录 ─────────────────────────────────────


@app.get("/api/locator-heal-logs")
def list_heal_logs(
    case_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(LocatorHealLog)
    if case_id is not None:
        query = query.filter(LocatorHealLog.case_id == case_id)
    return [
        {
            "id": log.id,
            "case_id": log.case_id,
            "old_locator": log.old_locator,
            "new_locator": log.new_locator,
            "page_url": log.page_url or "",
            "screenshot_path": log.screenshot_path or "",
            "confirmed": log.confirmed,
            "create_time": log.create_time.isoformat(),
        }
        for log in query.order_by(LocatorHealLog.id.desc()).limit(100).all()
    ]


@app.put("/api/locator-heal-logs/{log_id}")
def confirm_heal_log(
    log_id: int,
    payload: LocatorHealLogConfirm,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    log = get_or_404(db, LocatorHealLog, log_id)
    log.confirmed = payload.confirmed
    db.commit()
    return {"message": "updated"}


# ─── 执行前预检 ──────────────────────────────────────────


@app.post("/api/functional-cases/{case_id}/preflight")
def preflight_check_case(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PreflightResult:
    functional_case = get_or_404(db, FunctionalCase, case_id)
    if not functional_case.ui_case_id:
        return PreflightResult(passed=False, errors=["该用例未关联 UI 步骤，无法执行"])
    ui_case = db.get(UiCase, functional_case.ui_case_id)
    if not ui_case:
        return PreflightResult(passed=False, errors=["关联的 UI 用例不存在"])
    try:
        from .executors import preflight_check
        errors, warnings = preflight_check(ui_case)
        return PreflightResult(passed=len(errors) == 0, errors=errors, warnings=warnings)
    except Exception as exc:
        return PreflightResult(passed=False, errors=[str(exc)])


@app.post("/api/functional-tasks/{task_id}/seed-test-data")
def seed_functional_task_test_data(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    result = seed_functional_package_data(db, task)
    return {
        "task_id": task.id,
        "variables": result.get("variables") or {},
        "sources": result.get("sources") or [],
        "source_text_available": bool(result.get("source_text_available")),
        "message": "已抽取真实测试数据样本" if result.get("variables") else "未从页面快照或历史记录中抽到可用业务数据",
    }


@app.post("/api/functional-tasks/{task_id}/preflight-package")
def preflight_functional_task_package(
    task_id: int,
    payload: FunctionalExecuteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    selected_case_ids: list[int] = []
    if payload:
        if payload.case_id:
            selected_case_ids = [payload.case_id]
        elif payload.case_ids:
            selected_case_ids = list(dict.fromkeys(int(item) for item in payload.case_ids if int(item) > 0))
    return preflight_functional_package(db, task, payload, selected_case_ids or None, persist=True)


@app.get("/api/envs")
def list_envs(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(Env)
    if project_id is not None:
        query = query.filter(Env.project_id == project_id)
    return serialize_many(query.order_by(Env.id.asc()).all())


@app.post("/api/envs")
def create_env(payload: EnvCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, Any]:
    data = normalize_env_payload(normalize_json_fields(schema_data(payload)), require_required_fields=True)
    ensure_project_exists(db, data["project_id"])
    env = Env(**data)
    db.add(env)
    db.commit()
    db.refresh(env)
    return serialize(env)


@app.put("/api/envs/{env_id}")
def update_env(
    env_id: int,
    payload: EnvUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    env = get_or_404(db, Env, env_id)
    data = normalize_env_payload(normalize_json_fields(schema_data(payload, exclude_unset=True)))
    if "project_id" in data:
        ensure_project_exists(db, data["project_id"])
    for field, value in data.items():
        setattr(env, field, value)
    db.commit()
    db.refresh(env)
    return serialize(env)


@app.delete("/api/envs/{env_id}")
def delete_env(env_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, str]:
    env = get_or_404(db, Env, env_id)
    linked_api_count = db.query(ApiCase).filter(ApiCase.env_id == env.id).count()
    if linked_api_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"环境已被 {linked_api_count} 个接口用例引用，不能删除",
        )
    db.delete(env)
    db.commit()
    return {"message": "deleted"}


@app.get("/api/api-cases")
def list_api_cases(
    project_id: int | None = Query(default=None),
    env_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(ApiCase)
    if project_id is not None:
        query = query.filter(ApiCase.project_id == project_id)
    if env_id is not None:
        query = query.filter(ApiCase.env_id == env_id)
    return serialize_many(query.order_by(ApiCase.id.desc()).all())


@app.post("/api/api-cases")
def create_api_case(
    payload: ApiCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = normalize_api_case_payload(normalize_json_fields(schema_data(payload)), require_required_fields=True)
    data["case_name"] = strip_case_name_prefix(data["case_name"])
    if not data["case_name"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u7528\u4f8b\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a")
    ensure_project_exists(db, data["project_id"])
    env = ensure_env_exists(db, data["env_id"])
    ensure_env_belongs_to_project(env, data["project_id"])
    case = ApiCase(**data, create_time=datetime.now())
    db.add(case)
    db.commit()
    db.refresh(case)
    return serialize(case)


@app.put("/api/api-cases/{case_id}")
def update_api_case(
    case_id: int,
    payload: ApiCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    case = get_or_404(db, ApiCase, case_id)
    data = normalize_api_case_payload(normalize_json_fields(schema_data(payload, exclude_unset=True)))
    if "case_name" in data:
        data["case_name"] = strip_case_name_prefix(data["case_name"])
        if not data["case_name"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u7528\u4f8b\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a")
    if "project_id" in data:
        ensure_project_exists(db, data["project_id"])
    final_project_id = data.get("project_id", case.project_id)
    final_env_id = data.get("env_id", case.env_id)
    env = ensure_env_exists(db, final_env_id)
    ensure_env_belongs_to_project(env, final_project_id)
    for field, value in data.items():
        setattr(case, field, value)
    db.commit()
    db.refresh(case)
    return serialize(case)


@app.delete("/api/api-cases/{case_id}")
def delete_api_case(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, str]:
    case = get_or_404(db, ApiCase, case_id)
    db.delete(case)
    db.commit()
    return {"message": "deleted"}


@app.post("/api/api-cases/{case_id}/execute")
def run_api_case(
    case_id: int,
    payload: ApiExecuteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    case = get_or_404(db, ApiCase, case_id)
    env_id = payload.env_id if payload and payload.env_id else case.env_id
    env = get_or_404(db, Env, env_id)
    if env.project_id != case.project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="环境不属于该用例项目")
    runtime_vars = payload.variables if payload else {}
    passed, log_text, report_path, extracted_vars = execute_api_case(case, env, runtime_vars)
    record = TestRecord(
        case_type="api",
        case_id=case.id,
        project_id=case.project_id,
        result="passed" if passed else "failed",
        log=log_text,
        screenshot="",
        report_path=report_path,
        execute_time=datetime.now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    data = serialize(record)
    data["extracted_vars"] = extracted_vars
    return data


def save_record(
    db: Session,
    case_type: str,
    case_id: int,
    passed: bool,
    log_text: str,
    report_path: str,
    screenshot: str = "",
    project_id: int | None = None,
) -> TestRecord:
    record = TestRecord(
        case_type=case_type,
        case_id=case_id,
        project_id=project_id,
        result="passed" if passed else "failed",
        log=log_text,
        screenshot=screenshot,
        report_path=report_path,
        execute_time=datetime.now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def split_customer_ids(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    raw_items = value if isinstance(value, list) else [value]
    customer_ids: list[str] = []
    for raw_item in raw_items:
        if raw_item in (None, ""):
            continue
        for item in re.split(r"[\s,，;；]+", str(raw_item).strip()):
            customer_id = item.strip()
            if not customer_id:
                continue
            if not re.fullmatch(r"\d+", customer_id):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"客户ID只能是数字：{customer_id}")
            customer_ids.append(customer_id)
    return customer_ids


def apply_frontend_customer_login_variables(variables: Dict[str, Any]) -> Dict[str, Any]:
    customer_ids = split_customer_ids(variables.get("customer_id"))
    if not customer_ids:
        customer_ids = split_customer_ids(variables.get("customer_ids"))
    if not customer_ids:
        return variables
    customer_id = customer_ids[0]
    variables["customer_id"] = customer_id
    variables["customer_ids"] = customer_ids
    variables["account"] = f"userID/{customer_id}In"
    variables["password"] = FRONTEND_UNIVERSAL_ACCOUNT_PASSWORD
    return variables


@app.post("/api/api-cases/batch-execute")
def batch_run_api_cases(
    payload: ApiBatchExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    if not payload.case_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要执行的接口用例")
    runtime_vars = apply_frontend_customer_login_variables(dict(payload.variables or {}))
    records = []
    for case_id in payload.case_ids:
        case = get_or_404(db, ApiCase, case_id)
        env_id = payload.env_id or case.env_id
        env = get_or_404(db, Env, env_id)
        if env.project_id != case.project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"用例 {case.id} 与所选环境不属于同一项目")
        passed, log_text, report_path, extracted_vars = execute_api_case(case, env, runtime_vars)
        runtime_vars.update(extracted_vars)
        record = save_record(db, "api", case.id, passed, log_text, report_path, project_id=case.project_id)
        record_data = serialize(record)
        record_data["case_name"] = case.case_name
        record_data["extracted_vars"] = extracted_vars
        records.append(record_data)
    return {
        "passed": all(item["result"] == "passed" for item in records),
        "records": records,
        "variables": runtime_vars,
    }


def resolve_data_script_context(db: Session, payload: DataScriptExecuteRequest) -> tuple[Env, int]:
    project_id = int(payload.project_id) if payload.project_id is not None else None
    if project_id is not None:
        ensure_project_exists(db, project_id)
    if payload.env_id:
        env = get_or_404(db, Env, payload.env_id)
        if project_id is not None and env.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="环境不属于所选项目")
        return env, env.project_id
    query = db.query(Env)
    if project_id is not None:
        query = query.filter(Env.project_id == project_id)
    else:
        data_script_project = find_data_script_project(db)
        if data_script_project:
            query = query.filter(Env.project_id == data_script_project.id)
    env = query.order_by(Env.id.asc()).first()
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先配置环境")
    return env, env.project_id


def data_script_variables(db: Session, variables: Dict[str, Any] | None, project_id: int | None = None) -> Dict[str, Any]:
    merged = dict(variables or {})
    configured_paths = {}

    # 批量查询：一次性查出所有相关 ApiCase，避免 ~40 次循环 x 4 种匹配的 N+1 查询
    all_search_names = set()
    all_urls = set()
    for item in DATA_SCRIPT_API_CASES:
        all_search_names.add(item["case_name"])
        all_search_names.add(strip_case_name_prefix(item["case_name"]))
        all_urls.add(item["url"])
    batch_query = db.query(ApiCase).filter(
        or_(ApiCase.case_name.in_(all_search_names), ApiCase.url.in_(all_urls))
    )
    if project_id is not None:
        batch_query = batch_query.filter(ApiCase.project_id == project_id)
    all_cases = batch_query.order_by(ApiCase.id.asc()).all()

    # 构建内存索引，沿用原有 4 级匹配优先级
    case_by_name: Dict[str, ApiCase] = {}
    case_by_name_url: Dict[tuple[str, str], ApiCase] = {}
    case_by_url_first: Dict[str, ApiCase] = {}
    for c in all_cases:
        if c.case_name not in case_by_name:
            case_by_name[c.case_name] = c
        key_nu = (c.case_name, c.url)
        if key_nu not in case_by_name_url:
            case_by_name_url[key_nu] = c
        if c.url not in case_by_url_first:
            case_by_url_first[c.url] = c

    for item in DATA_SCRIPT_API_CASES:
        legacy_name = item["case_name"]
        case_name = strip_case_name_prefix(legacy_name)
        url = item["url"]
        case = (
            case_by_name.get(legacy_name)
            or case_by_name_url.get((case_name, url))
            or case_by_url_first.get(url)
            or case_by_name.get(case_name)
        )
        configured_paths[item["key"]] = case.url if case else item["url"]
    custom_paths = merged.get("api_paths") if isinstance(merged.get("api_paths"), dict) else {}
    merged["api_paths"] = {**configured_paths, **custom_paths}
    login_case_query = db.query(ApiCase).filter(ApiCase.case_name == LOGIN_CASE_NAME)
    if project_id is not None:
        login_case_query = login_case_query.filter(ApiCase.project_id == project_id)
    login_case = login_case_query.order_by(ApiCase.id.asc()).first()
    login_body = parse_json_value(login_case.body, {}) if login_case else {}
    if isinstance(login_body, dict):
        for key in ["account", "password", "client_tool"]:
            default_value = login_body.get(key)
            if default_value in (None, ""):
                continue
            current_value = merged.get(key)
            is_old_seed = (key == "account" and current_value == "abner") or (key == "password" and current_value == "12345")
            if current_value in (None, "") or is_old_seed:
                merged[key] = default_value
    return apply_frontend_customer_login_variables(merged)


@app.post("/api/data-scripts/shopping-cart")
def run_shopping_cart_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = run_shopping_cart_script(env, variables)
    cart_case = db.query(ApiCase).filter(ApiCase.case_name == CART_CASE_NAME, ApiCase.project_id == project_id).order_by(ApiCase.id.asc()).first()
    record = save_record(db, "api", cart_case.id if cart_case else 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/order-quote")
def run_order_quote_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = run_order_quote_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/order-quote/options-preview")
def preview_order_quote_options_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    return preview_order_quote_options(env, variables)


@app.post("/api/data-scripts/balance-payment")
def run_balance_payment_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = run_balance_payment_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/bank-payment")
def run_bank_payment_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = run_bank_payment_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/purchase-to-shelf")
def run_purchase_to_shelf_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    def enabled(value: Any, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in {"0", "false", "no", "off"}

    has_target_order = bool(
        str(variables.get("order_sn") or variables.get("last_order_sn") or "").strip()
        or variables.get("purchase_ids")
    )
    if not has_target_order and enabled(variables.get("link_quote_balance_before_shelf"), True) and enabled(variables.get("auto_quote_and_pay"), True):
        passed, log_text, report_path, summary = run_purchase_to_shelf_chain(env, variables)
    else:
        passed, log_text, report_path, summary = run_purchase_to_shelf_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/purchase-to-shelf-chain")
def run_purchase_to_shelf_chain_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = run_purchase_to_shelf_chain(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/direct-box-to-shelf")
def run_direct_box_to_shelf_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = run_direct_box_to_shelf_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/warehouse-delivery")
def run_warehouse_delivery_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = run_warehouse_delivery_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/porder-balance-payment")
def run_porder_balance_payment_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = run_porder_balance_payment_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/porder-bank-payment")
def run_porder_bank_payment_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = run_porder_bank_payment_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/full-flow")
def run_full_flow_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = run_full_flow_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.get("/api/data-scripts/latest-order-sn")
def get_latest_order_sn(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    query = db.query(TestRecord).filter(TestRecord.case_type == "api")
    if project_id is not None:
        query = query.filter(TestRecord.project_id == project_id)
    records = query.order_by(TestRecord.id.desc()).limit(100).all()
    for record in records:
        try:
            log_data = json.loads(record.log or "{}")
        except ValueError:
            continue
        summary = log_data.get("summary") if isinstance(log_data, dict) else {}
        if not isinstance(summary, dict):
            continue
        order_sn = summary.get("order_sn")
        if order_sn:
            return {
                "order_sn": str(order_sn),
                "record_id": record.id,
                "result": record.result,
                "execute_time": record.execute_time.strftime("%Y-%m-%d %H:%M:%S"),
            }
    return {"order_sn": "", "record_id": None}


@app.get("/api/ui-cases")
def list_ui_cases(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(UiCase)
    if project_id is not None:
        query = query.filter(UiCase.project_id == project_id)
    rows = []
    for case in query.order_by(UiCase.id.desc()).all():
        item = serialize(case)
        item.update(account_profile_summary(default_account_profile_for_target(db, "ui_case", case.id, case.project_id)))
        rows.append(item)
    return rows


@app.post("/api/ui-cases")
def create_ui_case(
    payload: UiCaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = normalize_json_fields(schema_data(payload))
    ensure_project_exists(db, data["project_id"])
    case = UiCase(**data, create_time=datetime.now())
    db.add(case)
    db.commit()
    db.refresh(case)
    return serialize(case)


@app.put("/api/ui-cases/{case_id}")
def update_ui_case(
    case_id: int,
    payload: UiCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    case = get_or_404(db, UiCase, case_id)
    data = normalize_json_fields(schema_data(payload, exclude_unset=True))
    if "project_id" in data:
        ensure_project_exists(db, data["project_id"])
    for field, value in data.items():
        setattr(case, field, value)
    db.commit()
    db.refresh(case)
    return serialize(case)


@app.delete("/api/ui-cases/{case_id}")
def delete_ui_case(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, str]:
    case = get_or_404(db, UiCase, case_id)
    db.delete(case)
    db.commit()
    return {"message": "deleted"}


@app.post("/api/ui-cases/{case_id}/heal-steps")
def heal_ui_case_steps(
    case_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """接受执行日志中的 healing 建议，更新用例的 locator"""
    case = get_or_404(db, UiCase, case_id)
    heal_map = payload.get("heal_map")
    if not isinstance(heal_map, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="heal_map 必须是对象")
    current_steps = parse_json_value(case.steps, [])
    if not isinstance(current_steps, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用例步骤格式不正确")
    updated_count = 0
    for step in current_steps:
        if not isinstance(step, dict):
            continue
        step_locator = step.get("locator", "")
        for old_locator, new_locator in heal_map.items():
            if step_locator == old_locator:
                step["locator"] = new_locator
                step["healed_at"] = datetime.now().isoformat()
                updated_count += 1
    if updated_count:
        case.steps = to_json_text(current_steps, [])
        db.commit()
        db.refresh(case)
    return {"updated_count": updated_count, "case": serialize(case)}


@app.post("/api/ui-cases/{case_id}/execute")
def run_ui_case(
    case_id: int,
    payload: FunctionalExecuteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    case = get_or_404(db, UiCase, case_id)
    variables, execution_context = resolve_execution_account(db, payload, "ui_case", case.id, case.project_id, case.page_url)
    passed, log_text, screenshot_path, report_path = execute_ui_case(case, variables, execution_context)
    record = save_ui_record(db, case, passed, log_text, report_path, screenshot_path)
    return serialize(record)


@app.get("/api/ai-config")
def get_ai_config(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return serialize_ai_config(latest_ai_config(db))


@app.put("/api/ai-config")
def update_ai_config(
    payload: AiConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload)
    config = latest_ai_config(db)
    if not config:
        config = AiConfig(
            provider=data.get("provider") or "openai_compatible",
            base_url=data.get("base_url") or "",
            model=data.get("model") or "",
            api_key=data.get("api_key") or "",
            create_time=datetime.now(),
        )
        db.add(config)
    else:
        config.provider = data.get("provider") or "openai_compatible"
        config.base_url = data.get("base_url") or ""
        config.model = data.get("model") or ""
        config.api_key = data.get("api_key") or ""
    db.commit()
    db.refresh(config)
    return serialize_ai_config(config)


@app.get("/api/functional-tasks")
def list_functional_tasks(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(FunctionalTask)
    if project_id is not None:
        query = query.filter(FunctionalTask.project_id == project_id)
    return [functional_task_detail(db, item) for item in query.order_by(FunctionalTask.id.desc()).all()]


@app.post("/api/functional-tasks")
def create_functional_task(
    payload: FunctionalTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload)
    ensure_project_exists(db, data["project_id"])
    task = FunctionalTask(
        project_id=data["project_id"],
        iteration_name=data["iteration_name"].strip(),
        requirement_text=data.get("requirement_text") or "",
        context=data.get("context") or "",
        axure_path="",
        target_url=data["target_url"].strip(),
        status=data.get("status") or "draft",
        create_time=datetime.now(),
    )
    if not task.iteration_name or not task.target_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="迭代名称和目标页面不能为空")
    db.add(task)
    db.commit()
    db.refresh(task)
    return functional_task_detail(db, task)


@app.get("/api/functional-tasks/{task_id}")
def get_functional_task(task_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return functional_task_detail(db, get_or_404(db, FunctionalTask, task_id))


@app.put("/api/functional-tasks/{task_id}/context")
def update_functional_task_context(
    task_id: int,
    payload: FunctionalTaskContextUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    data = schema_data(payload)
    task.context = (data.get("context") or "").strip()
    db.commit()
    db.refresh(task)
    return functional_task_detail(db, task)


@app.delete("/api/functional-tasks/{task_id}")
def delete_functional_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    task = get_or_404(db, FunctionalTask, task_id)
    for case in db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id).all():
        if case.ui_case_id:
            db.query(UiCase).filter(UiCase.id == case.ui_case_id).delete(synchronize_session=False)
    db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id).delete(synchronize_session=False)
    db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).delete(synchronize_session=False)
    db.query(FunctionalScreenshot).filter(FunctionalScreenshot.task_id == task.id).delete(synchronize_session=False)
    db.query(FunctionalRequirementNote).filter(FunctionalRequirementNote.task_id == task.id).delete(synchronize_session=False)
    db.query(FunctionalRun).filter(FunctionalRun.task_id == task.id).delete(synchronize_session=False)
    db.query(FunctionalImpactItem).filter(FunctionalImpactItem.task_id == task.id).delete(synchronize_session=False)
    db.query(FunctionalDataCheckResult).filter(FunctionalDataCheckResult.task_id == task.id).delete(synchronize_session=False)
    db.query(FunctionalDataCheckRule).filter(FunctionalDataCheckRule.task_id == task.id).delete(synchronize_session=False)
    db.delete(task)
    db.commit()
    return {"message": "deleted"}


@app.post("/api/functional-tasks/{task_id}/impact-items/analyze")
def analyze_functional_impact_items(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    existing_keys = {
        impact_item_key(item.item_type, item.ref_id, item.title, item.target)
        for item in db.query(FunctionalImpactItem).filter(FunctionalImpactItem.task_id == task.id).all()
    }
    created = []
    for item in suggest_functional_impact_items(db, task):
        key = impact_item_key(item.get("item_type") or "", item.get("ref_id"), item.get("title") or "", item.get("target") or "")
        if key in existing_keys:
            continue
        impact = FunctionalImpactItem(
            task_id=task.id,
            item_type=item.get("item_type") or "manual",
            ref_id=item.get("ref_id"),
            title=(item.get("title") or "关联影响项")[:200],
            target=item.get("target") or "",
            risk_level=item.get("risk_level") or "P1",
            test_result="untested",
            source=item.get("source") or "rule",
            reason=item.get("reason") or "",
            remark="",
            create_time=datetime.now(),
            update_time=None,
        )
        db.add(impact)
        db.flush()
        created.append(impact)
        existing_keys.add(key)
    db.commit()
    return {"created": len(created), "items": serialize_many(created), "task": functional_task_detail(db, task)}


@app.post("/api/functional-tasks/{task_id}/impact-items")
def create_functional_impact_item(
    task_id: int,
    payload: FunctionalImpactItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    data = schema_data(payload)
    require_non_blank_text(data, "title", "影响项标题")
    item = FunctionalImpactItem(
        task_id=task.id,
        item_type=data.get("item_type") or "manual",
        ref_id=data.get("ref_id"),
        title=data["title"][:200],
        target=data.get("target") or "",
        risk_level=data.get("risk_level") or "P1",
        test_result=normalize_functional_result(data.get("test_result")),
        source=data.get("source") or "manual",
        reason=data.get("reason") or "",
        remark=data.get("remark") or "",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"item": serialize(item), "task": functional_task_detail(db, task)}


@app.put("/api/functional-impact-items/{item_id}")
def update_functional_impact_item(
    item_id: int,
    payload: FunctionalImpactItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    item = get_or_404(db, FunctionalImpactItem, item_id)
    data = schema_data(payload, exclude_unset=True)
    if "title" in data and data["title"] is not None:
        require_non_blank_text(data, "title", "影响项标题")
    if "test_result" in data and data["test_result"] is not None:
        data["test_result"] = normalize_functional_result(data["test_result"])
    for field in ["item_type", "ref_id", "title", "target", "risk_level", "test_result", "source", "reason", "remark"]:
        if field in data and data[field] is not None:
            setattr(item, field, data[field])
    item.update_time = datetime.now()
    db.commit()
    db.refresh(item)
    return {"item": serialize(item), "task": functional_task_detail(db, get_or_404(db, FunctionalTask, item.task_id))}


@app.delete("/api/functional-impact-items/{item_id}")
def delete_functional_impact_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    item = get_or_404(db, FunctionalImpactItem, item_id)
    task = get_or_404(db, FunctionalTask, item.task_id)
    db.delete(item)
    db.commit()
    return {"message": "deleted", "task": functional_task_detail(db, task)}


@app.post("/api/functional-tasks/{task_id}/data-check-rules")
def create_functional_data_check_rule(
    task_id: int,
    payload: FunctionalDataCheckRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    data = normalize_data_check_payload(schema_data(payload), require_name=True)
    rule = FunctionalDataCheckRule(
        task_id=task.id,
        rule_name=data["rule_name"],
        check_type=data.get("check_type") or "page_api_consistency",
        page_value=data.get("page_value") or "",
        api_method=data.get("api_method") or "GET",
        api_url=data.get("api_url") or "",
        api_headers=data.get("api_headers") or "{}",
        api_body=data.get("api_body") or "{}",
        api_value_path=data.get("api_value_path") or "json",
        compare_rule=data.get("compare_rule") or "{}",
        expected_value=data.get("expected_value") or "",
        status=data.get("status") or "active",
        create_time=datetime.now(),
        update_time=None,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"rule": serialize(rule), "task": functional_task_detail(db, task)}


@app.put("/api/functional-data-check-rules/{rule_id}")
def update_functional_data_check_rule(
    rule_id: int,
    payload: FunctionalDataCheckRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    rule = get_or_404(db, FunctionalDataCheckRule, rule_id)
    data = normalize_data_check_payload(schema_data(payload, exclude_unset=True))
    for field in [
        "rule_name",
        "check_type",
        "page_value",
        "api_method",
        "api_url",
        "api_headers",
        "api_body",
        "api_value_path",
        "compare_rule",
        "expected_value",
        "status",
    ]:
        if field in data and data[field] is not None:
            setattr(rule, field, data[field])
    rule.update_time = datetime.now()
    db.commit()
    db.refresh(rule)
    return {"rule": serialize(rule), "task": functional_task_detail(db, get_or_404(db, FunctionalTask, rule.task_id))}


@app.delete("/api/functional-data-check-rules/{rule_id}")
def delete_functional_data_check_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    rule = get_or_404(db, FunctionalDataCheckRule, rule_id)
    task = get_or_404(db, FunctionalTask, rule.task_id)
    db.query(FunctionalDataCheckResult).filter(FunctionalDataCheckResult.rule_id == rule.id).delete(synchronize_session=False)
    db.delete(rule)
    db.commit()
    return {"message": "deleted", "task": functional_task_detail(db, task)}


@app.post("/api/functional-data-check-rules/{rule_id}/execute")
def execute_functional_data_check(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    rule = get_or_404(db, FunctionalDataCheckRule, rule_id)
    task = get_or_404(db, FunctionalTask, rule.task_id)
    record = execute_functional_data_check_rule(db, task, rule)
    return {"result": serialize(record), "task": functional_task_detail(db, task)}


@app.post("/api/functional-tasks/{task_id}/data-check-runs")
def execute_functional_data_checks(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    rules = (
        db.query(FunctionalDataCheckRule)
        .filter(FunctionalDataCheckRule.task_id == task.id, FunctionalDataCheckRule.status != "inactive")
        .order_by(FunctionalDataCheckRule.id.asc())
        .all()
    )
    results = [execute_functional_data_check_rule(db, task, rule) for rule in rules]
    return {"results": serialize_many(results), "task": functional_task_detail(db, task)}


@app.get("/api/functional-tasks/{task_id}/conclusion")
def get_functional_task_conclusion(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    return {"task_id": task.id, "conclusion": functional_task_conclusion_summary(db, task)}



@app.post("/api/functional-tasks/{task_id}/upload-axure")
async def upload_functional_axure(
    task_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件不能为空")
    task.axure_path = store_axure_file(file.filename or "prototype.rp", content)
    task.status = "uploaded"
    db.commit()
    db.refresh(task)
    axure_text = read_axure_text(task.axure_path)
    data = functional_task_detail(db, task)
    data["axure_text_preview"] = axure_text[:2000]
    return data


@app.post("/api/functional-tasks/{task_id}/upload-screenshot")
async def upload_functional_screenshot(
    task_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传截图不能为空")
    try:
        image_path = store_functional_screenshot_file(file.filename or "screenshot.png", content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    screenshot = FunctionalScreenshot(
        task_id=task.id,
        image_path=image_path,
        analysis_result="",
        create_time=datetime.now(),
    )
    task.status = "screenshot_uploaded"
    db.add(screenshot)
    db.commit()
    db.refresh(screenshot)
    return {"screenshot": serialize(screenshot), "task": functional_task_detail(db, task)}


@app.post("/api/functional-tasks/{task_id}/upload-screenshots")
async def upload_functional_screenshots_batch(
    task_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    uploaded: list[Dict[str, Any]] = []
    errors: list[str] = []
    for file in files:
        content = await file.read()
        if not content:
            errors.append(f"{file.filename}: 文件为空")
            continue
        try:
            image_path = store_functional_screenshot_file(file.filename or "screenshot.png", content)
        except ValueError as exc:
            errors.append(f"{file.filename}: {exc}")
            continue
        screenshot = FunctionalScreenshot(
            task_id=task.id,
            image_path=image_path,
            analysis_result="",
            create_time=datetime.now(),
        )
        task.status = "screenshot_uploaded"
        db.add(screenshot)
        db.commit()
        db.refresh(screenshot)
        uploaded.append(serialize(screenshot))
    if not uploaded and errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="；".join(errors[:5]))
    return {"uploaded": uploaded, "errors": errors, "task": functional_task_detail(db, task)}


@app.get("/api/functional-screenshots/{screenshot_id}/file")
def get_functional_screenshot_file(
    screenshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    screenshot = get_or_404(db, FunctionalScreenshot, screenshot_id)
    return safe_file_response(screenshot.image_path)


@app.post("/api/functional-screenshots/{screenshot_id}/analyze")
def analyze_uploaded_functional_screenshot(
    screenshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    screenshot = get_or_404(db, FunctionalScreenshot, screenshot_id)
    task = get_or_404(db, FunctionalTask, screenshot.task_id)
    try:
        screenshot.analysis_result = analyze_functional_screenshot(task, screenshot, latest_ai_config(db))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    task.status = "screenshot_analyzed"
    db.commit()
    db.refresh(screenshot)
    return {"screenshot": serialize(screenshot), "task": functional_task_detail(db, task)}


@app.post("/api/functional-tasks/{task_id}/requirement-notes")
def create_functional_requirement_note(
    task_id: int,
    payload: FunctionalRequirementNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    data = schema_data(payload)
    note_text = (data.get("note_text") or "").strip()
    if not note_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="补充需求不能为空")
    note = FunctionalRequirementNote(
        task_id=task.id,
        note_text=note_text,
        create_time=datetime.now(),
        update_time=None,
    )
    task.status = "requirements_updated"
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"note": serialize(note), "task": functional_task_detail(db, task)}


@app.put("/api/functional-requirement-notes/{note_id}")
def update_functional_requirement_note(
    note_id: int,
    payload: FunctionalRequirementNoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    note = get_or_404(db, FunctionalRequirementNote, note_id)
    data = schema_data(payload)
    note_text = (data.get("note_text") or "").strip()
    if not note_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="补充需求不能为空")
    note.note_text = note_text
    note.update_time = datetime.now()
    db.commit()
    db.refresh(note)
    return serialize(note)


@app.delete("/api/functional-requirement-notes/{note_id}")
def delete_functional_requirement_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, str]:
    note = get_or_404(db, FunctionalRequirementNote, note_id)
    db.delete(note)
    db.commit()
    return {"message": "deleted"}


@app.post("/api/functional-tasks/{task_id}/scan-page")
def scan_functional_page(
    task_id: int,
    payload: FunctionalScanRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    scanned: Dict[str, Any] = {}
    try:
        auth_config = schema_data(payload.auth, exclude_unset=True) if payload and payload.auth else None
        scanned = scan_page_dom(task.target_url, auth=auth_config)
    except FunctionalScanError as exc:
        trace = getattr(exc, "trace", None) or scanned.get("scan_trace", [])
        detail = str(exc)
        if trace:
            detail = f"{detail}\n\n扫描过程：\n" + "\n".join(f"- {item}" for item in trace)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
    except Exception as exc:
        trace = scanned.get("scan_trace", [])
        detail = f"扫描异常中断：{exc}"
        if trace:
            detail += "\n\n扫描过程：\n" + "\n".join(f"- {item}" for item in trace)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

    snapshot = PageSnapshot(
        task_id=task.id,
        page_url=task.target_url,
        dom_summary=scanned["dom_summary"],
        screenshot_path=scanned["screenshot_path"],
        scan_time=datetime.now(),
    )
    # 即使部分失败也保存已获取的数据
    task.status = "scanned"
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    data = serialize(snapshot)
    data["scan_trace"] = scanned.get("scan_trace", [])
    # 传递错误步骤信息以便前端展示
    dom_data = json.loads(scanned.get("dom_summary", "{}"))
    if dom_data.get("error_step"):
        data["scan_error_step"] = dom_data["error_step"]
        data["scan_error"] = dom_data.get("error", "")
    return data


# ─── 简单内存限速器 ────────────────────────────────
_LOGIN_RATE_LIMIT: dict[str, list[float]] = {}  # "ip:user" → [timestamp, ...]
_LOGIN_RATE_WINDOW = 60  # 秒
_LOGIN_RATE_MAX_ATTEMPTS = int(os.getenv("LOGIN_RATE_LIMIT", "200"))  # 每窗口最多尝试次数，可通过环境变量覆盖


def _check_login_rate_limit(client_ip: str, username: str = "") -> None:
    """检查登录频率，超过阈值则拒绝。key = IP:username 避免不同用户相互干扰。"""
    now = time.time()
    key = f"{client_ip}:{username}"
    records = _LOGIN_RATE_LIMIT.get(key, [])
    # 清理过期记录
    records = [t for t in records if now - t < _LOGIN_RATE_WINDOW]
    if len(records) >= _LOGIN_RATE_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录尝试过于频繁，请稍后再试（{_LOGIN_RATE_WINDOW}秒内最多{_LOGIN_RATE_MAX_ATTEMPTS}次）",
        )
    records.append(now)
    _LOGIN_RATE_LIMIT[key] = records


def ui_steps_have_strong_assertion(steps: Any) -> bool:
    parsed = parse_json_value(steps, steps)
    if isinstance(parsed, str):
        parsed = parse_json_value(parsed, [])
    if not isinstance(parsed, list):
        return False
    strong_actions = {"assert_url", "assert_visible", "assert_value", "text_assert"}
    for step in parsed:
        if not isinstance(step, dict):
            continue
        if step.get("action") in strong_actions:
            return True
        if step.get("success_condition") or step.get("assertions"):
            return True
    return False


@app.post("/api/functional-tasks/{task_id}/quick-start")
def quick_start_functional_task(
    task_id: int,
    payload: FunctionalScanRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """
    一键快速开始：扫描页面 → 生成测试用例 → 生成UI步骤 → 自动确认
    
    将原本需要 5-8 步的操作合并为一步。
    返回完整任务详情 + 每个步骤的执行状态。
    """
    task = get_or_404(db, FunctionalTask, task_id)
    steps_status = {}

    # ─── 步骤 1：扫描页面（带超时保护）─────────────────
    try:
        auth_config = schema_data(payload.auth, exclude_unset=True) if payload and payload.auth else None
        # 如果目标 URL 明显不可达（如 example.com），跳过扫描减少等待
        skip_scan = any(domain in task.target_url.lower() for domain in ["example.com", "test.com", "localhost", "127.0.0.1"])
        if skip_scan:
            steps_status["scan"] = {"ok": False, "error": "目标URL不可达，跳过扫描", "skipped": True}
        else:
            # 带超时的扫描
            scanned_holder = {}
            def do_scan():
                scanned_holder["result"] = scan_page_dom(task.target_url, timeout=15, auth=auth_config)
            t = threading.Thread(target=do_scan, daemon=True)
            t.start()
            t.join(timeout=25)
            if t.is_alive():
                steps_status["scan"] = {"ok": False, "error": "扫描超时（25s），已跳过"}
            else:
                scanned = scanned_holder.get("result")
                if scanned:
                    snapshot = PageSnapshot(
                        task_id=task.id,
                        page_url=task.target_url,
                        dom_summary=scanned["dom_summary"],
                        screenshot_path=scanned["screenshot_path"],
                        scan_time=datetime.now(),
                    )
                    db.add(snapshot)
                    db.flush()
                    steps_status["scan"] = {"ok": True, "snapshot_id": snapshot.id}
                    task.status = "scanned"
                    safe_commit(db)
    except Exception as exc:
        db.rollback()
        steps_status["scan"] = {"ok": False, "error": str(exc)[:300]}
        # 即使扫描失败也继续生成

    # ─── 步骤 2：生成测试用例 ─────────────────────────
    try:
        task = get_or_404(db, FunctionalTask, task_id)
        axure_text = read_axure_text(task.axure_path)
        latest_snapshot = db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).first()
        screenshots = db.query(FunctionalScreenshot).filter(FunctionalScreenshot.task_id == task.id).order_by(FunctionalScreenshot.id.asc()).all()
        notes = db.query(FunctionalRequirementNote).filter(FunctionalRequirementNote.task_id == task.id).order_by(FunctionalRequirementNote.id.asc()).all()
        generated = generate_functional_cases(task, axure_text, latest_snapshot, latest_ai_config(db), screenshots, notes)

        # 删除旧的未确认用例
        for old_case in db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id, FunctionalCase.automation_status != "approved").all():
            db.delete(old_case)
        db.flush()

        for item in generated.items:
            db.add(FunctionalCase(
                task_id=task.id,
                title=item["title"],
                precondition=item.get("precondition", ""),
                steps=item.get("steps", ""),
                expected=item.get("expected", ""),
                category=item.get("category", "主流程"),
                priority=item.get("priority", "P1"),
                automation_status="draft",
                ui_case_id=None,
                create_time=datetime.now(),
            ))
        db.flush()
        steps_status["generate_cases"] = {"ok": True, "count": len(generated.items), "source": generated.source}
        task.status = "cases_generated"
        db.commit()
    except Exception as exc:
        db.rollback()
        steps_status["generate_cases"] = {"ok": False, "error": str(exc)[:300]}

    # ─── 步骤 3：生成 UI 步骤 + 自动确认 ──────────────
    task = get_or_404(db, FunctionalTask, task_id)
    cases = db.query(FunctionalCase).filter(
        FunctionalCase.task_id == task.id,
        FunctionalCase.automation_status.in_(["draft", "ui_steps_generated"]),
    ).order_by(FunctionalCase.id.asc()).all()

    ui_generated_count = 0
    ui_failed_count = 0
    latest_snapshot = db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).first()

    for fc in cases:
        try:
            generated_ui = generate_ui_steps(fc, task, latest_snapshot, latest_ai_config(db))
            steps_text = to_json_text(generated_ui.items, [])
            if fc.ui_case_id:
                ui_case = db.get(UiCase, fc.ui_case_id)
                if ui_case:
                    ui_case.case_name = fc.title
                    ui_case.page_url = task.target_url
                    ui_case.steps = steps_text
                else:
                    fc.ui_case_id = None
            if not fc.ui_case_id:
                ui_case = UiCase(
                    project_id=task.project_id,
                    case_name=fc.title,
                    page_url=task.target_url,
                    steps=steps_text,
                    timeout=30,
                    status="active",
                    create_time=datetime.now(),
                )
                db.add(ui_case)
                db.flush()
                fc.ui_case_id = ui_case.id
            # 只有具备业务断言的步骤才自动确认；否则保留待人工确认，避免假阳性。
            fc.automation_status = "approved" if ui_steps_have_strong_assertion(generated_ui.items) else "ui_steps_generated"
            ui_generated_count += 1
        except Exception as exc:
            fc.automation_status = "draft"
            ui_failed_count += 1

    approved_count = sum(1 for item in cases if item.automation_status == "approved")
    if approved_count > 0:
        task.status = "approved"
    elif ui_generated_count > 0:
        task.status = "ui_steps_generated"
    db.commit()

    steps_status["generate_ui"] = {
        "ok": ui_failed_count == 0,
        "total": len(cases),
        "generated": ui_generated_count,
        "approved": approved_count,
        "needs_review": max(ui_generated_count - approved_count, 0),
        "failed": ui_failed_count,
    }

    return {
        "task": functional_task_detail(db, task),
        "steps": steps_status,
        "summary": f"扫描{'✅' if steps_status.get('scan',{}).get('ok') else '❌'} → "
                   f"生成用例{'✅' if steps_status.get('generate_cases',{}).get('ok') else '❌'} → "
                   f"生成步骤{'✅' if steps_status.get('generate_ui',{}).get('ok') else '❌'}",
    }


@app.post("/api/functional-tasks/{task_id}/generate-cases")
def generate_functional_task_cases(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    axure_text = read_axure_text(task.axure_path)
    snapshot = db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).first()
    screenshots = db.query(FunctionalScreenshot).filter(FunctionalScreenshot.task_id == task.id).order_by(FunctionalScreenshot.id.asc()).all()
    notes = (
        db.query(FunctionalRequirementNote)
        .filter(FunctionalRequirementNote.task_id == task.id)
        .order_by(FunctionalRequirementNote.id.asc())
        .all()
    )
    generated = generate_functional_cases(task, axure_text, snapshot, latest_ai_config(db), screenshots, notes)

    for old_case in db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id, FunctionalCase.automation_status != "approved").all():
        db.delete(old_case)
    db.flush()

    for item in generated.items:
        db.add(
            FunctionalCase(
                task_id=task.id,
                title=item["title"],
                precondition=item.get("precondition", ""),
                steps=item.get("steps", ""),
                expected=item.get("expected", ""),
                category=item.get("category", "主流程"),
                priority=item.get("priority", "P1"),
                automation_status=item.get("automation_status", "draft"),
                ui_case_id=None,
                create_time=datetime.now(),
            )
        )
    task.status = "cases_generated"
    db.commit()
    result = {"source": generated.source, "warning": generated.warning, "task": functional_task_detail(db, task)}
    return result


@app.put("/api/functional-cases/{case_id}")
def update_functional_case(
    case_id: int,
    payload: FunctionalCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    case = get_or_404(db, FunctionalCase, case_id)
    data = schema_data(payload, exclude_unset=True)
    for field in ["title", "precondition", "steps", "expected", "category", "priority", "automation_status"]:
        if field in data and data[field] is not None:
            setattr(case, field, data[field])
    db.commit()
    db.refresh(case)
    return serialize(case)


@app.put("/api/functional-cases/{case_id}/status")
def update_functional_case_status(
    case_id: int,
    payload: FunctionalCaseStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """更新单个用例的测试执行状态"""
    case = get_or_404(db, FunctionalCase, case_id)
    valid_statuses = {"untested", "passed", "failed", "blocked", "skipped"}
    if payload.test_result not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"无效的状态值，可选: {', '.join(sorted(valid_statuses))}")
    case.test_result = payload.test_result
    db.commit()
    db.refresh(case)
    return serialize(case)


@app.post("/api/functional-tasks/{task_id}/cases/batch-status")
def batch_update_functional_case_status(
    task_id: int,
    payload: FunctionalCaseBatchStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """批量更新用例的测试执行状态"""
    get_or_404(db, FunctionalTask, task_id)
    valid_statuses = {"untested", "passed", "failed", "blocked", "skipped"}
    if payload.test_result not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"无效的状态值，可选: {', '.join(sorted(valid_statuses))}")
    updated = (
        db.query(FunctionalCase)
        .filter(FunctionalCase.task_id == task_id, FunctionalCase.id.in_(payload.case_ids))
        .update({"test_result": payload.test_result}, synchronize_session="fetch")
    )
    db.commit()
    return {"updated": updated, "test_result": payload.test_result}


@app.get("/api/functional-tasks/{task_id}/cases/stats")
def get_functional_case_stats(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FunctionalCaseStats:
    """获取任务的用例状态统计"""
    get_or_404(db, FunctionalTask, task_id)
    total = db.query(FunctionalCase).filter(FunctionalCase.task_id == task_id).count()
    counts = {row[0]: row[1] for row in
              db.query(FunctionalCase.test_result, func.count(FunctionalCase.id))
              .filter(FunctionalCase.task_id == task_id)
              .group_by(FunctionalCase.test_result)
              .all()}
    return FunctionalCaseStats(
        total=total,
        untested=counts.get("untested", 0),
        passed=counts.get("passed", 0),
        failed=counts.get("failed", 0),
        blocked=counts.get("blocked", 0),
        skipped=counts.get("skipped", 0),
    )


def save_generated_functional_ui_steps(
    db: Session,
    task: FunctionalTask,
    case: FunctionalCase,
    snapshot: PageSnapshot | None = None,
) -> Dict[str, Any]:
    generated = generate_ui_steps(case, task, snapshot, latest_ai_config(db))
    steps_text = to_json_text(generated.items, [])
    if case.ui_case_id:
        ui_case = db.get(UiCase, case.ui_case_id)
        if ui_case:
            ui_case.case_name = case.title
            ui_case.page_url = task.target_url
            ui_case.steps = steps_text
            ui_case.status = "draft"
        else:
            case.ui_case_id = None
    if not case.ui_case_id:
        ui_case = UiCase(
            project_id=task.project_id,
            case_name=case.title,
            page_url=task.target_url,
            steps=steps_text,
            timeout=30,
            status="draft",
            create_time=datetime.now(),
        )
        db.add(ui_case)
        db.flush()
        case.ui_case_id = ui_case.id
    case.automation_status = "draft"
    task.status = "ui_steps_generated"
    return {"source": generated.source, "warning": generated.warning, "case": serialize(case), "steps": generated.items}


@app.post("/api/functional-cases/{case_id}/generate-ui-steps")
def generate_functional_case_ui_steps(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    case = get_or_404(db, FunctionalCase, case_id)
    task = get_or_404(db, FunctionalTask, case.task_id)
    snapshot = db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).first()
    result = save_generated_functional_ui_steps(db, task, case, snapshot)
    db.commit()
    db.refresh(case)
    result["case"] = serialize(case)
    return result


@app.post("/api/functional-tasks/{task_id}/cases/batch-generate-ui-steps")
def batch_generate_functional_case_ui_steps(
    task_id: int,
    payload: FunctionalCaseBatchIds,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    query = db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id)
    requested_ids = list(dict.fromkeys(int(item) for item in (payload.case_ids or []) if int(item) > 0))
    if requested_ids:
        query = query.filter(FunctionalCase.id.in_(requested_ids))
    cases = query.order_by(FunctionalCase.id.asc()).all()
    if not cases:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可生成步骤的用例")
    snapshot = db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).first()
    results: list[Dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    for case in cases:
        try:
            result = save_generated_functional_ui_steps(db, task, case, snapshot)
            results.append(
                {
                    "case_id": case.id,
                    "title": case.title,
                    "status": "success",
                    "source": result.get("source"),
                    "warning": result.get("warning"),
                }
            )
            success_count += 1
        except Exception as exc:
            results.append({"case_id": case.id, "title": case.title, "status": "failed", "error": str(exc)})
            failed_count += 1
    db.commit()
    return {"total": len(cases), "success_count": success_count, "failed_count": failed_count, "results": results}


@app.post("/api/functional-tasks/{task_id}/cases/batch-automation-status")
def batch_update_functional_case_automation_status(
    task_id: int,
    payload: FunctionalCaseBatchAutomationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    get_or_404(db, FunctionalTask, task_id)
    valid_statuses = {"draft", "ui_steps_generated", "approved", "needs_review"}
    if payload.automation_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"无效的自动化状态，可选: {', '.join(sorted(valid_statuses))}")
    requested_ids = list(dict.fromkeys(int(item) for item in (payload.case_ids or []) if int(item) > 0))
    query = db.query(FunctionalCase).filter(FunctionalCase.task_id == task_id)
    if requested_ids:
        query = query.filter(FunctionalCase.id.in_(requested_ids))
    if payload.automation_status == "approved":
        query = query.filter(FunctionalCase.ui_case_id.isnot(None))
    updated = query.update({"automation_status": payload.automation_status}, synchronize_session="fetch")
    db.commit()
    return {"updated": updated, "automation_status": payload.automation_status}


def execute_functional_case_for_run(
    db: Session,
    functional_case: FunctionalCase,
    variables: Dict[str, Any],
    payload: FunctionalExecuteRequest | None = None,
) -> tuple[Dict[str, Any], int, int]:
    ui_case = db.get(UiCase, functional_case.ui_case_id) if functional_case.ui_case_id else None
    if not ui_case:
        return (
            {
                "functional_case_id": functional_case.id,
                "title": functional_case.title,
                "result": "failed",
                "error": "关联UI用例不存在",
            },
            0,
            1,
        )
    case_variables, execution_context = resolve_execution_account(
        db,
        payload,
        "functional_case",
        functional_case.id,
        ui_case.project_id,
        ui_case.page_url,
    )
    case_variables = {**variables, **case_variables}
    try:
        passed, log_text, screenshot_path, report_path = execute_ui_case(ui_case, case_variables, execution_context)
    except Exception as exc:
        passed = False
        screenshot_path = ""
        report_path = ""
        log_text = json.dumps(
            {
                "case_name": ui_case.case_name,
                "page_url": ui_case.page_url,
                "error": str(exc),
                "finished_at": datetime.now(),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    record = save_ui_record(db, ui_case, passed, log_text, report_path, screenshot_path)
    return (
        {
            "functional_case_id": functional_case.id,
            "ui_case_id": ui_case.id,
            "record_id": record.id,
            "title": functional_case.title,
            "result": record.result,
            "screenshot": screenshot_path,
            "log": log_text,
        },
        1 if passed else 0,
        0 if passed else 1,
    )


def execute_functional_case_for_run_isolated(
    functional_case_id: int,
    variables: Dict[str, Any],
    payload_data: Dict[str, Any] | None = None,
) -> tuple[Dict[str, Any], int, int]:
    from .database import SessionLocal

    db = SessionLocal()
    try:
        functional_case = db.get(FunctionalCase, functional_case_id)
        if not functional_case:
            return (
                {
                    "functional_case_id": functional_case_id,
                    "title": f"#{functional_case_id}",
                    "result": "failed",
                    "error": "功能用例不存在",
                },
                0,
                1,
            )
        payload = FunctionalExecuteRequest(**payload_data) if payload_data else None
        return execute_functional_case_for_run(db, functional_case, variables, payload)
    finally:
        db.close()


def save_functional_run(
    db: Session,
    task: FunctionalTask,
    variables: Dict[str, Any],
    records: list[Dict[str, Any]],
    passed_count: int,
    failed_count: int,
) -> FunctionalRun:
    result = "passed" if failed_count == 0 else "failed"
    log_payload = {
        "task_id": task.id,
        "task": task.iteration_name,
        "variables": {key: ("***" if "password" in str(key).lower() else value) for key, value in variables.items()},
        "records": records,
        "passed_count": passed_count,
        "failed_count": failed_count,
    }
    run = FunctionalRun(
        task_id=task.id,
        result=result,
        log=json.dumps(log_payload, ensure_ascii=False, indent=2, default=str),
        passed_count=passed_count,
        failed_count=failed_count,
        execute_time=datetime.now(),
    )
    task.status = result
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@app.post("/api/functional-tasks/{task_id}/execute-async")
def execute_functional_task_async(
    task_id: int,
    payload: FunctionalExecuteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    force_execute = bool(payload.force) if payload else False
    selected_case_ids: list[int] = []
    if payload:
        if payload.case_id:
            selected_case_ids = [payload.case_id]
        elif payload.case_ids:
            selected_case_ids = list(dict.fromkeys(int(item) for item in payload.case_ids if int(item) > 0))
    preflight_result = preflight_functional_package(db, task, payload, selected_case_ids or None, persist=True)
    seed_variables = dict((preflight_result.get("seed") or {}).get("variables") or {})
    variables = {**seed_variables, **(payload.variables if payload else {})}
    cases_query = db.query(FunctionalCase).filter(
        FunctionalCase.task_id == task.id,
        FunctionalCase.automation_status == "approved",
        FunctionalCase.ui_case_id.isnot(None),
    )
    if selected_case_ids:
        cases_query = cases_query.filter(FunctionalCase.id.in_(selected_case_ids))
    if not force_execute:
        cases_query = cases_query.filter(FunctionalCase.quality_status == QUALITY_EXECUTABLE)
    cases = cases_query.order_by(FunctionalCase.id.asc()).all()
    if not cases:
        manual_count = (preflight_result.get("counts") or {}).get("manual_check", 0)
        detail = "预检后没有高可信可自动执行用例"
        if manual_count:
            detail += f"，有 {manual_count} 条已转为人工核对/需补数据/需修定位"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    # 1) 先创建 run 记录，标记为 running
    initial_log = {
        "task_id": task.id,
        "task": task.iteration_name,
        "variables": {key: ("***" if "password" in str(key).lower() else value) for key, value in variables.items()},
        "records": [],
        "passed_count": 0,
        "failed_count": 0,
        "total": len(cases),
        "preflight": preflight_result,
        "completed": 0,
        "current_case_title": "初始化执行器...",
    }
    run = FunctionalRun(
        task_id=task.id,
        result="running",
        log=json.dumps(initial_log, ensure_ascii=False, indent=2, default=str),
        passed_count=0,
        failed_count=0,
        execute_time=datetime.now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # 2) 后台线程执行
    run_id = run.id
    payload_data = schema_data(payload) if payload else {}
    payload_data["variables"] = variables
    payload_data["force"] = force_execute
    payload_case_id = payload_data.get("case_id") if payload_data else None
    payload_case_ids = payload_data.get("case_ids") if payload_data else []
    selected_bg_case_ids: list[int] = []
    if payload_case_id:
        selected_bg_case_ids = [int(payload_case_id)]
    elif payload_case_ids:
        selected_bg_case_ids = list(dict.fromkeys(int(item) for item in payload_case_ids if int(item) > 0))

    def _background_execute():
        from .database import SessionLocal

        bg_db = None
        try:
            bg_db = SessionLocal()
            bg_task = bg_db.query(FunctionalTask).filter(FunctionalTask.id == task_id).first()
            bg_run = bg_db.query(FunctionalRun).filter(FunctionalRun.id == run_id).first()
            if not bg_task or not bg_run:
                return

            bg_cases_query = bg_db.query(FunctionalCase).filter(
                FunctionalCase.task_id == task_id,
                FunctionalCase.automation_status == "approved",
                FunctionalCase.ui_case_id.isnot(None),
            )
            if selected_bg_case_ids:
                bg_cases_query = bg_cases_query.filter(FunctionalCase.id.in_(selected_bg_case_ids))
            if not payload_data.get("force"):
                bg_cases_query = bg_cases_query.filter(FunctionalCase.quality_status == QUALITY_EXECUTABLE)
            bg_cases = bg_cases_query.order_by(FunctionalCase.id.asc()).all()

            gathered_records: list[Dict[str, Any]] = []
            total_passed = 0
            total_failed = 0
            total_blocked = 0
            _cached_vars = dict(variables)
            processed_case_ids: set[int] = set()
            batch_items: list[Dict[str, Any]] = []
            payload_obj = FunctionalExecuteRequest(**payload_data) if payload_data else None

            for fc in bg_cases:
                ui_case = bg_db.get(UiCase, fc.ui_case_id) if fc.ui_case_id else None
                if not ui_case:
                    continue
                case_variables, execution_context = resolve_execution_account(
                    bg_db,
                    payload_obj,
                    "functional_case",
                    fc.id,
                    ui_case.project_id,
                    ui_case.page_url,
                )
                case_variables = {**_cached_vars, **case_variables}
                if execution_context.get("login_required"):
                    profile_key = execution_context.get("account_profile_id") or "default"
                    execution_context["session_key"] = f"functional-task:{task_id}:profile:{profile_key}"
                    execution_context["target_url"] = execution_context.get("target_url") or bg_task.target_url or ui_case.page_url
                batch_items.append(
                    {
                        "case": ui_case,
                        "functional_case": fc,
                        "functional_case_id": fc.id,
                        "variables": case_variables,
                        "execution_context": execution_context,
                    }
                )

            def _write_run_progress(current_title: str, completed: int) -> None:
                bg_run.log = json.dumps({
                    **json.loads(bg_run.log or "{}"),
                    "records": gathered_records,
                    "passed_count": total_passed,
                    "failed_count": total_failed,
                    "blocked_count": total_blocked,
                    "completed": completed,
                    "current_case_title": current_title,
                }, ensure_ascii=False, default=str)
                bg_run.passed_count = total_passed
                bg_run.failed_count = total_failed
                bg_db.commit()

            def _on_case_start(item: Dict[str, Any]) -> None:
                fc = item.get("functional_case")
                title = getattr(fc, "title", "正在执行用例")
                _write_run_progress(title, len(processed_case_ids))

            def _on_case_finish(item: Dict[str, Any], result_tuple: tuple[bool, str, str, str]) -> None:
                nonlocal total_passed, total_failed, total_blocked
                fc = bg_db.get(FunctionalCase, int(item.get("functional_case_id")))
                ui_case = item.get("case")
                passed, log_text, screenshot_path, report_path = result_tuple
                record = save_ui_record(bg_db, ui_case, passed, log_text, report_path, screenshot_path)
                record_payload: Dict[str, Any] = {
                    "functional_case_id": fc.id if fc else item.get("functional_case_id"),
                    "ui_case_id": getattr(ui_case, "id", None),
                    "record_id": record.id,
                    "title": fc.title if fc else getattr(ui_case, "case_name", "未知用例"),
                    "result": record.result,
                    "quality_status": getattr(fc, "quality_status", QUALITY_UNCHECKED) if fc else QUALITY_UNCHECKED,
                    "screenshot": screenshot_path,
                    "log": log_text,
                }
                record_text = json.dumps(record_payload, ensure_ascii=False, default=str)
                auth_blocked = (not passed) and ("登录前置失败" in record_text or ("login_required" in record_text and "#/login" in record_text))
                if fc:
                    if passed:
                        fc.test_result = "passed"
                        total_passed += 1
                    elif auth_blocked:
                        fc.test_result = "blocked"
                        fc.quality_status = QUALITY_AUTH_RISK
                        fc.quality_report = json.dumps(
                            quality_report_payload(QUALITY_AUTH_RISK, "登录前置失败，未继续判定业务功能"),
                            ensure_ascii=False,
                            default=str,
                        )
                        record_payload["result"] = "blocked"
                        record_payload["status"] = "auth_blocked"
                        total_blocked += 1
                    else:
                        fc.test_result = "failed"
                        fc.failure_count = (fc.failure_count or 0) + 1
                        total_failed += 1
                    processed_case_ids.add(fc.id)
                gathered_records.append(record_payload)
                _write_run_progress(
                    "登录前置失败，后续用例已阻断" if auth_blocked else record_payload["title"],
                    len(processed_case_ids),
                )

            try:
                execute_ui_cases_batch(batch_items, on_case_start=_on_case_start, on_case_finish=_on_case_finish)
            except Exception as exc:
                if "登录前置失败" not in str(exc):
                    raise
                for blocked_case in bg_cases:
                    if blocked_case.id in processed_case_ids:
                        continue
                    blocked_case.test_result = "blocked"
                    blocked_case.quality_status = QUALITY_AUTH_RISK
                    blocked_case.quality_report = json.dumps(
                        quality_report_payload(QUALITY_AUTH_RISK, str(exc)[:500]),
                        ensure_ascii=False,
                        default=str,
                    )
                    gathered_records.append(
                        {
                            "functional_case_id": blocked_case.id,
                            "title": blocked_case.title,
                            "result": "blocked",
                            "status": "auth_blocked",
                            "error": str(exc),
                        }
                    )
                    processed_case_ids.add(blocked_case.id)
                    total_blocked += 1
                _write_run_progress("登录前置失败，已停止后续用例", len(processed_case_ids))

            final_result = "failed" if total_failed else ("blocked" if total_blocked else "passed")
            bg_run.result = final_result
            bg_run.log = json.dumps({
                **json.loads(bg_run.log or "{}"),
                "current_case_title": "执行完毕",
                "status": final_result,
                "blocked_count": total_blocked,
            }, ensure_ascii=False, default=str)
            bg_task.status = final_result
            bg_db.commit()
        except Exception:
            import traceback
            if bg_db is not None:
                try:
                    error_run = bg_db.query(FunctionalRun).filter(FunctionalRun.id == run_id).first()
                    if error_run:
                        error_run.result = "error"
                        error_run.log = json.dumps({
                            **json.loads(error_run.log or "{}"),
                            "current_case_title": "执行异常",
                            "status": "error",
                            "error": traceback.format_exc(),
                        }, ensure_ascii=False, default=str)
                        bg_db.commit()
                except Exception:
                    pass
        finally:
            if bg_db is not None:
                bg_db.close()

    thread = threading.Thread(target=_background_execute, daemon=True)
    thread.start()

    return {
        "job_id": run.id,
        "status": "running",
        "total": len(cases),
        "completed": 0,
        "passed_count": 0,
        "failed_count": 0,
        "current_case_title": "启动中...",
        "records": [],
        "task_name": task.iteration_name,
    }


@app.get("/api/functional-executions/{job_id}")
def get_functional_execution(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    run = get_or_404(db, FunctionalRun, job_id)
    log_data = parse_json_value(run.log, {})
    return {
        "job_id": run.id,
        "status": run.result,
        "total": log_data.get("total", 0),
        "completed": log_data.get("completed", 0),
        "passed_count": run.passed_count,
        "failed_count": run.failed_count,
        "blocked_count": log_data.get("blocked_count", 0),
        "preflight": log_data.get("preflight", None),
        "current_case_title": log_data.get("current_case_title", ""),
        "records": log_data.get("records", []),
        "task_name": log_data.get("task", ""),
        "error": log_data.get("error", None),
    }


@app.post("/api/functional-runs/{run_id}/diagnose")
def diagnose_functional_run(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    run = get_or_404(db, FunctionalRun, run_id)
    diagnosis = diagnose_failure(run, latest_ai_config(db))
    try:
        payload = json.loads(run.log or "{}")
    except json.JSONDecodeError:
        payload = {"log": run.log or ""}
    payload["diagnosis"] = diagnosis
    run.log = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    db.commit()
    db.refresh(run)
    return {"run": serialize(run), "diagnosis": diagnosis}


@app.post("/api/functional-runs/{run_id}/heal")
def heal_functional_run_steps(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """从执行日志提取 healed locator，批量更新关联 UI 用例"""
    run = get_or_404(db, FunctionalRun, run_id)
    run_log = parse_json_value(run.log, {})
    records = run_log.get("records") if isinstance(run_log.get("records"), list) else []
    heal_map: Dict[str, str] = {}
    updated_cases: list[int] = []

    for record in records:
        if not isinstance(record, dict):
            continue
        ui_log = parse_json_value(record.get("log"), {})
        step_logs = ui_log.get("step_logs") if isinstance(ui_log.get("step_logs"), list) else []
        for step in step_logs:
            if isinstance(step, dict) and step.get("healed") and step.get("original_locator") and step.get("suggested_locator"):
                old_loc = step.get("original_locator")
                new_loc = step.get("suggested_locator")
                if old_loc and new_loc and old_loc != new_loc:
                    heal_map[old_loc] = new_loc
        case_id = record.get("case_id") or ui_log.get("case_id")
        if case_id and heal_map:
            try:
                case = db.get(UiCase, case_id)
                if case:
                    current_steps = parse_json_value(case.steps, [])
                    updated = 0
                    for step in current_steps:
                        if isinstance(step, dict):
                            step_locator = step.get("locator", "")
                            for old_loc, new_loc in heal_map.items():
                                if step_locator == old_loc:
                                    step["locator"] = new_loc
                                    step["healed_at"] = datetime.now().isoformat()
                                    updated += 1
                    if updated:
                        case.steps = to_json_text(current_steps, [])
                        updated_cases.append(case.id)
            except Exception:
                continue

    if updated_cases:
        db.commit()

    return {
        "heal_map": heal_map,
        "updated_cases": updated_cases,
        "updated_count": len(heal_map),
    }


PROXY_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
PROXY_ALLOW_PRIVATE_URLS = os.getenv("ALLOW_PROXY_PRIVATE_URLS", "").strip().lower() in {"1", "true", "yes", "on"}
PROXY_MAX_REDIRECTS = 5


def proxy_ip_is_blocked(ip_value: str) -> bool:
    ip = ipaddress.ip_address(ip_value)
    return any(
        (
            ip.is_loopback,
            ip.is_private,
            ip.is_link_local,
            ip.is_reserved,
            ip.is_multicast,
            ip.is_unspecified,
        )
    )


def _resolve_and_check_hostname(hostname: str, port: int) -> None:
    """解析 hostname 并检查所有解析到的 IP 是否为内网地址。"""
    try:
        resolved = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return
    for item in resolved:
        address = item[4][0]
        try:
            if proxy_ip_is_blocked(address):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"代理请求禁止访问本机或内网地址 (解析到 {address})",
                )
        except ValueError:
            continue


def validate_proxy_target(method: str, url: str) -> None:
    if method not in PROXY_ALLOWED_METHODS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的请求方法")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 HTTP/HTTPS URL")
    if not parsed.hostname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL host 不能为空")
    if PROXY_ALLOW_PRIVATE_URLS:
        return

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理请求禁止访问本机或内网地址")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # 如果 hostname 本身就是 IP，直接检查
    try:
        if proxy_ip_is_blocked(hostname):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理请求禁止访问本机或内网地址")
        return
    except ValueError:
        pass

    # 解析 DNS 并检查所有解析到的 IP
    _resolve_and_check_hostname(hostname, port)


def _origin(url: str) -> str:
    """提取 URL 的 origin（scheme + host），用于跨域判断。"""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.hostname.lower()}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"


def guarded_proxy_request(method: str, url: str, headers: Dict[str, Any], body: str, timeout: int) -> requests.Response:
    current_method = method
    current_url = url
    current_body = body
    original_origin = _origin(current_url)
    request_headers = dict(headers or {})
    for _ in range(PROXY_MAX_REDIRECTS + 1):
        validate_proxy_target(current_method, current_url)
        # 跨域重定向时剥离 Authorization 头（防泄露给第三方）
        redirect_headers = dict(request_headers)
        if _origin(current_url) != original_origin:
            for sensitive_header in {"authorization", "proxy-authorization", "cookie", "x-api-key"}:
                redirect_headers.pop(sensitive_header, None)
                redirect_headers.pop(sensitive_header.title(), None)
        response = requests.request(
            current_method,
            current_url,
            headers=redirect_headers,
            data=current_body,
            timeout=timeout,
            allow_redirects=False,
        )
        if not response.is_redirect:
            return response
        location = response.headers.get("Location")
        if not location:
            return response
        current_url = urljoin(current_url, location)
        if response.status_code in {301, 302, 303}:
            current_method = "GET"
            current_body = ""
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="重定向次数过多")


@app.post("/api/proxy/request")
def proxy_http_request(
    payload: QuickRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    method = payload.method.upper().strip()
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL不能为空")
    headers = dict(payload.headers or {})
    body = payload.body or ""
    client_ip = request.client.host if request.client else "unknown"
    logger.info("代理请求 [%s] %s %s (来源: %s)", method, url, current_user.username, client_ip)
    start = time.time()
    try:
        resp = guarded_proxy_request(method, url, headers, body, timeout=30)
    except HTTPException:
        raise
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="请求超时（30s）")
    except requests.exceptions.ConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"连接失败: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    elapsed = int((time.time() - start) * 1000)
    content_type = resp.headers.get("Content-Type", "")
    body_text = resp.text
    preview = body_text[:5000]
    return {
        "status_code": resp.status_code,
        "headers": dict(resp.headers),
        "body_preview": preview,
        "body_truncated": len(body_text) > 5000,
        "elapsed_ms": elapsed,
    }


@app.get("/api/test-records")
def list_records(
    case_type: str | None = Query(default=None),
    project_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    query = db.query(TestRecord)
    if case_type is not None:
        query = query.filter(TestRecord.case_type == case_type)
    if project_id is not None:
        api_ids = [item.id for item in db.query(ApiCase.id).filter(ApiCase.project_id == project_id).all()]
        ui_ids = [item.id for item in db.query(UiCase.id).filter(UiCase.project_id == project_id).all()]
        query = query.filter(
            or_(
                TestRecord.project_id == project_id,
                (TestRecord.case_type == "api") & TestRecord.case_id.in_(api_ids or [-1]),
                (TestRecord.case_type == "ui") & TestRecord.case_id.in_(ui_ids or [-1]),
            )
        )
    total = query.count()
    items = serialize_many(query.order_by(TestRecord.id.desc()).offset((page - 1) * page_size).limit(page_size).all())
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@app.get("/api/test-records/{record_id}")
def get_record(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    return serialize(get_or_404(db, TestRecord, record_id))


@app.get("/api/test-records/{record_id}/report")
def get_record_report(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> FileResponse:
    record = get_or_404(db, TestRecord, record_id)
    return safe_file_response(record.report_path)


@app.get("/api/test-records/{record_id}/screenshot")
def get_record_screenshot(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> FileResponse:
    record = get_or_404(db, TestRecord, record_id)
    return safe_file_response(record.screenshot)
