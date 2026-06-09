import base64
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Type

from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .data_scripts import (
    run_balance_payment_script,
    run_bank_payment_script,
    run_order_quote_script,
    run_purchase_to_shelf_script,
    run_purchase_to_shelf_chain,
    run_porder_balance_payment_script,
    run_porder_bank_payment_script,
    run_shopping_cart_script,
    run_warehouse_delivery_script,
)
from .executors import ensure_report_dirs, execute_api_case, execute_ui_case, parse_json_value, to_json_text
from .functional_testing import (
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
    Env,
    FunctionalCase,
    FunctionalRequirementNote,
    FunctionalRun,
    FunctionalScreenshot,
    FunctionalTask,
    PageSnapshot,
    Project,
    TestRecord,
    UiCase,
    User,
    TestAccountBinding,
    TestAccountProfile,
)
from .schemas import (
    AiConfigUpdate,
    ApiCaseCreate,
    ApiBatchExecuteRequest,
    ApiCaseUpdate,
    ApiExecuteRequest,
    DataScriptExecuteRequest,
    EnvCreate,
    EnvUpdate,
    FunctionalCaseUpdate,
    FunctionalExecuteRequest,
    FunctionalRequirementNoteCreate,
    FunctionalRequirementNoteUpdate,
    FunctionalScanRequest,
    FunctionalTaskCreate,
    LoginRequest,
    ProjectCreate,
    ProjectUpdate,
    UiCaseCreate,
    UiCaseUpdate,
    UserCreate,
    UserUpdate,
    TestAccountBindingUpdate,
    TestAccountProfileCreate,
    TestAccountProfileUpdate,
)
from .security import SECRET_KEY, create_access_token, get_current_user, hash_password, require_admin, verify_password


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
    TestRecord: ["id", "case_type", "case_id", "result", "log", "screenshot", "report_path", "execute_time"],
    FunctionalTask: ["id", "project_id", "iteration_name", "requirement_text", "axure_path", "target_url", "status", "create_time"],
    FunctionalCase: ["id", "task_id", "title", "precondition", "steps", "expected", "priority", "automation_status", "ui_case_id", "create_time"],
    PageSnapshot: ["id", "task_id", "page_url", "dom_summary", "screenshot_path", "scan_time"],
    FunctionalScreenshot: ["id", "task_id", "image_path", "analysis_result", "create_time"],
    FunctionalRequirementNote: ["id", "task_id", "note_text", "create_time", "update_time"],
    FunctionalRun: ["id", "task_id", "result", "log", "passed_count", "failed_count", "execute_time"],
    AiConfig: ["id", "provider", "base_url", "model", "api_key", "create_time"],
    TestAccountProfile: [
        "id", "project_id", "profile_name", "variables",
        "sensitive_variables", "status", "create_time", "update_time",
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
}

CASE_NAME_PREFIXES = ("\u6570\u636e\u811a\u672c-", "test-")


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


def find_data_script_api_case(db: Session, item: Dict[str, Any]) -> ApiCase | None:
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
        case = query.order_by(ApiCase.id.asc()).first()
        if case:
            return case
    return None


LOGIN_CASE_NAME = "\u767b\u5f55"
CART_CASE_NAME = "\u52a0\u5165\u8d2d\u7269\u8f66"

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
]


def ensure_data_script_api_cases(db: Session) -> None:
    env = db.query(Env).order_by(Env.id.asc()).first()
    if not env:
        project = db.query(Project).order_by(Project.id.asc()).first()
        if not project:
            project = Project(name="\u6570\u636e\u811a\u672c\u9879\u76ee", desc="\u7cfb\u7edf\u81ea\u52a8\u521b\u5efa", create_time=datetime.now())
            db.add(project)
            db.commit()
            db.refresh(project)
        env = Env(
            project_id=project.id,
            env_name="test-\u6570\u636e\u811a\u672c",
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
        exists = find_data_script_api_case(db, item)
        if exists:
            exists.case_name = case_name
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
    ensure_report_dirs()
    db = next(get_db())
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            db.add(
                User(
                    username="admin",
                    password=hash_password("admin123"),
                    role="admin",
                    create_time=datetime.now(),
                )
            )
            db.commit()
        normalize_api_case_names(db)
        ensure_data_script_api_cases(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_app()
    yield


app = FastAPI(title="接口 + UI 自动化测试平台", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    return response


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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


def functional_task_detail(db: Session, task: FunctionalTask) -> Dict[str, Any]:
    data = serialize(task)
    project = db.get(Project, task.project_id)
    data["project_name"] = project.name if project else task.project_id
    data["cases"] = serialize_many(db.query(FunctionalCase).filter(FunctionalCase.task_id == task.id).order_by(FunctionalCase.id.asc()).all())
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
    return data


def save_ui_record(db: Session, case: UiCase, passed: bool, log_text: str, report_path: str, screenshot_path: str = "") -> TestRecord:
    record = TestRecord(
        case_type="ui",
        case_id=case.id,
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
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
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
    return serialize_many(db.query(Project).order_by(Project.id.desc()).all())


@app.post("/api/projects")
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    data = schema_data(payload)
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
    data = schema_data(payload, exclude_unset=True)
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
    db.delete(project)
    db.commit()
    return {"message": "deleted"}

import re

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
    return variables, {"id": profile.id, "profile_name": profile.profile_name}


def account_target_project_id(db: Session, target_type: str, target_id: int) -> int:
    if target_type == "project":
        return target_id
    elif target_type == "functional_task":
        item = get_or_404(db, FunctionalTask, target_id)
        return item.project_id
    elif target_type == "functional_case":
        item = get_or_404(db, FunctionalCase, target_id)
        return item.project_id
    return target_id


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
        query = query.filter(TestAccountProfile.project_id == project_id)
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
    save_test_account_binding(db, target_type, target_id, profile_id)
    db.commit()
    profile = db.get(TestAccountProfile, profile_id) if profile_id else None
    return {"profile": serialize_account_profile(profile) if profile else None}


@app.get("/api/envs")
def list_envs(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(Env)
    if project_id is not None:
        query = query.filter(Env.project_id == project_id)
    return serialize_many(query.order_by(Env.id.desc()).all())


@app.post("/api/envs")
def create_env(payload: EnvCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)) -> Dict[str, Any]:
    data = normalize_json_fields(schema_data(payload))
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
    data = normalize_json_fields(schema_data(payload, exclude_unset=True))
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
    data = normalize_json_fields(schema_data(payload))
    data["case_name"] = strip_case_name_prefix(data["case_name"])
    if not data["case_name"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u7528\u4f8b\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a")
    ensure_project_exists(db, data["project_id"])
    ensure_env_exists(db, data["env_id"])
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
    data = normalize_json_fields(schema_data(payload, exclude_unset=True))
    if "case_name" in data:
        data["case_name"] = strip_case_name_prefix(data["case_name"])
        if not data["case_name"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u7528\u4f8b\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a")
    if "project_id" in data:
        ensure_project_exists(db, data["project_id"])
    if "env_id" in data:
        ensure_env_exists(db, data["env_id"])
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


def save_record(db: Session, case_type: str, case_id: int, passed: bool, log_text: str, report_path: str, screenshot: str = "") -> TestRecord:
    record = TestRecord(
        case_type=case_type,
        case_id=case_id,
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


@app.post("/api/api-cases/batch-execute")
def batch_run_api_cases(
    payload: ApiBatchExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    if not payload.case_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择要执行的接口用例")
    runtime_vars = dict(payload.variables or {})
    records = []
    for case_id in payload.case_ids:
        case = get_or_404(db, ApiCase, case_id)
        env_id = payload.env_id or case.env_id
        env = get_or_404(db, Env, env_id)
        if env.project_id != case.project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"用例 {case.id} 与所选环境不属于同一项目")
        passed, log_text, report_path, extracted_vars = execute_api_case(case, env, runtime_vars)
        runtime_vars.update(extracted_vars)
        record = save_record(db, "api", case.id, passed, log_text, report_path)
        record_data = serialize(record)
        record_data["case_name"] = case.case_name
        record_data["extracted_vars"] = extracted_vars
        records.append(record_data)
    return {
        "passed": all(item["result"] == "passed" for item in records),
        "records": records,
        "variables": runtime_vars,
    }


def data_script_variables(db: Session, variables: Dict[str, Any] | None) -> Dict[str, Any]:
    merged = dict(variables or {})
    configured_paths = {}
    for item in DATA_SCRIPT_API_CASES:
        case = find_data_script_api_case(db, item)
        configured_paths[item["key"]] = case.url if case else item["url"]
    custom_paths = merged.get("api_paths") if isinstance(merged.get("api_paths"), dict) else {}
    merged["api_paths"] = {**configured_paths, **custom_paths}
    login_case = db.query(ApiCase).filter(ApiCase.case_name == LOGIN_CASE_NAME).first()
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
    return merged


@app.post("/api/data-scripts/shopping-cart")
def run_shopping_cart_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env = get_or_404(db, Env, payload.env_id) if payload.env_id else db.query(Env).order_by(Env.id.asc()).first()
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先配置环境")
    variables = data_script_variables(db, payload.variables)
    passed, log_text, report_path, summary = run_shopping_cart_script(env, variables)
    cart_case = db.query(ApiCase).filter(ApiCase.case_name == CART_CASE_NAME).first()
    record = save_record(db, "api", cart_case.id if cart_case else 0, passed, log_text, report_path)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/order-quote")
def run_order_quote_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env = get_or_404(db, Env, payload.env_id) if payload.env_id else db.query(Env).order_by(Env.id.asc()).first()
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="璇峰厛閰嶇疆鐜")
    variables = data_script_variables(db, payload.variables)
    passed, log_text, report_path, summary = run_order_quote_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/balance-payment")
def run_balance_payment_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env = get_or_404(db, Env, payload.env_id) if payload.env_id else db.query(Env).order_by(Env.id.asc()).first()
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u8bf7\u5148\u914d\u7f6e\u73af\u5883")
    variables = data_script_variables(db, payload.variables)
    passed, log_text, report_path, summary = run_balance_payment_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/bank-payment")
def run_bank_payment_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env = get_or_404(db, Env, payload.env_id) if payload.env_id else db.query(Env).order_by(Env.id.asc()).first()
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u8bf7\u5148\u914d\u7f6e\u73af\u5883")
    variables = data_script_variables(db, payload.variables)
    passed, log_text, report_path, summary = run_bank_payment_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/purchase-to-shelf")
def run_purchase_to_shelf_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env = get_or_404(db, Env, payload.env_id) if payload.env_id else db.query(Env).order_by(Env.id.asc()).first()
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u8bf7\u5148\u914d\u7f6e\u73af\u5883")
    variables = data_script_variables(db, payload.variables)
    def enabled(value: Any, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in {"0", "false", "no", "off"}

    if enabled(variables.get("link_quote_balance_before_shelf"), True) and enabled(variables.get("auto_quote_and_pay"), True):
        passed, log_text, report_path, summary = run_purchase_to_shelf_chain(env, variables)
    else:
        passed, log_text, report_path, summary = run_purchase_to_shelf_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/purchase-to-shelf-chain")
def run_purchase_to_shelf_chain_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env = get_or_404(db, Env, payload.env_id) if payload.env_id else db.query(Env).order_by(Env.id.asc()).first()
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u8bf7\u5148\u914d\u7f6e\u73af\u5883")
    variables = data_script_variables(db, payload.variables)
    passed, log_text, report_path, summary = run_purchase_to_shelf_chain(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/warehouse-delivery")
def run_warehouse_delivery_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env = get_or_404(db, Env, payload.env_id) if payload.env_id else db.query(Env).order_by(Env.id.asc()).first()
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="\u8bf7\u5148\u914d\u7f6e\u73af\u5883")
    variables = data_script_variables(db, payload.variables)
    passed, log_text, report_path, summary = run_warehouse_delivery_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/porder-balance-payment")
def run_porder_balance_payment_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env = get_or_404(db, Env, payload.env_id) if payload.env_id else db.query(Env).order_by(Env.id.asc()).first()
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先配置环境")
    variables = data_script_variables(db, payload.variables)
    passed, log_text, report_path, summary = run_porder_balance_payment_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.post("/api/data-scripts/porder-bank-payment")
def run_porder_bank_payment_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env = get_or_404(db, Env, payload.env_id) if payload.env_id else db.query(Env).order_by(Env.id.asc()).first()
    if not env:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先配置环境")
    variables = data_script_variables(db, payload.variables)
    passed, log_text, report_path, summary = run_porder_bank_payment_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path)
    data = serialize(record)
    data["summary"] = summary
    return data


@app.get("/api/data-scripts/latest-order-sn")
def get_latest_order_sn(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    records = db.query(TestRecord).filter(TestRecord.case_type == "api").order_by(TestRecord.id.desc()).limit(100).all()
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
    return serialize_many(query.order_by(UiCase.id.desc()).all())


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


@app.post("/api/ui-cases/{case_id}/execute")
def run_ui_case(
    case_id: int,
    payload: FunctionalExecuteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    case = get_or_404(db, UiCase, case_id)
    passed, log_text, screenshot_path, report_path = execute_ui_case(case, payload.variables if payload else {})
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
    db.delete(task)
    db.commit()
    return {"message": "deleted"}



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
    try:
        auth_config = schema_data(payload.auth, exclude_unset=True) if payload and payload.auth else None
        scanned = scan_page_dom(task.target_url, auth=auth_config)
    except Exception as exc:
        trace = getattr(exc, "trace", None)
        detail = str(exc)
        if trace:
            detail = f"{detail}\n\n扫描过程：\n" + "\n".join(f"- {item}" for item in trace)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
    snapshot = PageSnapshot(
        task_id=task.id,
        page_url=task.target_url,
        dom_summary=scanned["dom_summary"],
        screenshot_path=scanned["screenshot_path"],
        scan_time=datetime.now(),
    )
    task.status = "scanned"
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    data = serialize(snapshot)
    data["scan_trace"] = scanned.get("scan_trace", [])
    return data


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
                priority=item.get("priority", "P1"),
                automation_status=item.get("automation_status", "draft"),
                ui_case_id=None,
                create_time=datetime.now(),
            )
        )
    task.status = "cases_generated"
    db.commit()
    return {"source": generated.source, "warning": generated.warning, "task": functional_task_detail(db, task)}


@app.put("/api/functional-cases/{case_id}")
def update_functional_case(
    case_id: int,
    payload: FunctionalCaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    case = get_or_404(db, FunctionalCase, case_id)
    data = schema_data(payload, exclude_unset=True)
    for field in ["title", "precondition", "steps", "expected", "priority", "automation_status"]:
        if field in data and data[field] is not None:
            setattr(case, field, data[field])
    db.commit()
    db.refresh(case)
    return serialize(case)


@app.post("/api/functional-cases/{case_id}/generate-ui-steps")
def generate_functional_case_ui_steps(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    case = get_or_404(db, FunctionalCase, case_id)
    task = get_or_404(db, FunctionalTask, case.task_id)
    snapshot = db.query(PageSnapshot).filter(PageSnapshot.task_id == task.id).order_by(PageSnapshot.id.desc()).first()
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
    db.commit()
    db.refresh(case)
    return {"source": generated.source, "warning": generated.warning, "case": serialize(case), "steps": generated.items}


def execute_functional_case_for_run(db: Session, functional_case: FunctionalCase, variables: Dict[str, Any]) -> tuple[Dict[str, Any], int, int]:
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
    try:
        passed, log_text, screenshot_path, report_path = execute_ui_case(ui_case, variables)
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


@app.post("/api/functional-cases/{case_id}/execute")
def execute_functional_case(
    case_id: int,
    payload: FunctionalExecuteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    functional_case = get_or_404(db, FunctionalCase, case_id)
    task = get_or_404(db, FunctionalTask, functional_case.task_id)
    if functional_case.automation_status != "approved" or not functional_case.ui_case_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该用例未确认或还没有生成UI步骤")
    variables = payload.variables if payload else {}
    record, passed_count, failed_count = execute_functional_case_for_run(db, functional_case, variables)
    run = save_functional_run(db, task, variables, [record], passed_count, failed_count)
    return serialize(run)


@app.post("/api/functional-tasks/{task_id}/execute")
def execute_functional_task(
    task_id: int,
    payload: FunctionalExecuteRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    task = get_or_404(db, FunctionalTask, task_id)
    variables = payload.variables if payload else {}
    cases = (
        db.query(FunctionalCase)
        .filter(FunctionalCase.task_id == task.id, FunctionalCase.automation_status == "approved", FunctionalCase.ui_case_id.isnot(None))
        .order_by(FunctionalCase.id.asc())
        .all()
    )
    if not cases:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有已确认且可执行的UI步骤")

    records = []
    passed_count = 0
    failed_count = 0
    for functional_case in cases:
        record, case_passed_count, case_failed_count = execute_functional_case_for_run(db, functional_case, variables)
        records.append(record)
        passed_count += case_passed_count
        failed_count += case_failed_count

    run = save_functional_run(db, task, variables, records, passed_count, failed_count)
    return serialize(run)


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


@app.get("/api/test-records")
def list_records(
    case_type: str | None = Query(default=None),
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    query = db.query(TestRecord)
    if case_type is not None:
        query = query.filter(TestRecord.case_type == case_type)
    if project_id is not None:
        api_ids = [item.id for item in db.query(ApiCase.id).filter(ApiCase.project_id == project_id).all()]
        ui_ids = [item.id for item in db.query(UiCase.id).filter(UiCase.project_id == project_id).all()]
        query = query.filter(
            or_(
                (TestRecord.case_type == "api") & TestRecord.case_id.in_(api_ids or [-1]),
                (TestRecord.case_type == "ui") & TestRecord.case_id.in_(ui_ids or [-1]),
            )
        )
    return serialize_many(query.order_by(TestRecord.id.desc()).all())


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
