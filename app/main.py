from contextlib import asynccontextmanager
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Type

from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .data_scripts import (
    run_balance_payment_script,
    run_bank_payment_script,
    run_order_quote_script,
    run_purchase_to_shelf_script,
    run_purchase_to_shelf_chain,
    run_shopping_cart_script,
    run_warehouse_delivery_script,
)
from .executors import ensure_report_dirs, execute_api_case, execute_ui_case, parse_json_value, to_json_text
from .models import ApiCase, Env, Project, TestRecord, UiCase, User
from .schemas import (
    ApiCaseCreate,
    ApiBatchExecuteRequest,
    ApiCaseUpdate,
    ApiExecuteRequest,
    DataScriptExecuteRequest,
    EnvCreate,
    EnvUpdate,
    LoginRequest,
    ProjectCreate,
    ProjectUpdate,
    UiCaseCreate,
    UiCaseUpdate,
    UserCreate,
    UserUpdate,
)
from .security import create_access_token, get_current_user, hash_password, require_admin, verify_password


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
}

JSON_FIELD_DEFAULTS = {
    "global_headers": {},
    "global_vars": {},
    "headers": {},
    "params": {},
    "assert_rule": {},
    "steps": [],
}

LOGIN_CASE_NAME = "test-\u767b\u5f55"
CART_CASE_NAME = "test-\u52a0\u5165\u8d2d\u7269\u8f66"

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
        exists = db.query(ApiCase).filter(ApiCase.case_name == item["case_name"]).first()
        if exists:
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
                case_name=item["case_name"],
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
        case = db.query(ApiCase).filter(ApiCase.case_name == item["case_name"]).first()
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
def run_ui_case(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    case = get_or_404(db, UiCase, case_id)
    passed, log_text, screenshot_path, report_path = execute_ui_case(case)
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
    return serialize(record)


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
