import json
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..core.utils import (
    CART_CASE_NAME,
    apply_frontend_customer_login_variables,
    data_script_variables,
    get_or_404,
    resolve_data_script_context,
    save_record,
    schema_data,
    serialize,
    split_customer_ids,
)
from ..data_scripts import (
    preview_order_quote_options,
    run_balance_payment_script,
    run_bank_payment_script,
    run_direct_box_to_shelf_script,
    run_full_flow_script,
    run_order_quote_script,
    run_porder_balance_payment_script,
    run_porder_bank_payment_script,
    run_purchase_to_shelf_chain,
    run_purchase_to_shelf_script,
    run_resume_order_flow_script,
    run_shopping_cart_script,
    run_warehouse_delivery_script,
)
from ..database import get_db
from ..models import ApiCase, Env, TestRecord, User
from ..schemas import DataScriptExecuteRequest
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api", tags=["data-scripts"])


@router.post("/data-scripts/shopping-cart")
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


@router.post("/data-scripts/order-quote")
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


@router.post("/data-scripts/order-quote/options-preview")
def preview_order_quote_options_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    return preview_order_quote_options(env, variables)


@router.post("/data-scripts/balance-payment")
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


@router.post("/data-scripts/bank-payment")
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


@router.post("/data-scripts/purchase-to-shelf")
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
    if not has_target_order and enabled(variables.get("link_quote_balance_before_shelf"), False) and enabled(variables.get("auto_quote_and_pay"), False):
        passed, log_text, report_path, summary = run_purchase_to_shelf_chain(env, variables)
    else:
        passed, log_text, report_path, summary = run_purchase_to_shelf_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.post("/data-scripts/purchase-to-shelf-chain")
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


@router.post("/data-scripts/direct-box-to-shelf")
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


@router.post("/data-scripts/warehouse-delivery")
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


@router.post("/data-scripts/porder-balance-payment")
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


@router.post("/data-scripts/porder-bank-payment")
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


@router.post("/data-scripts/full-flow")
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


@router.post("/data-scripts/resume-order-flow")
def run_resume_order_flow_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = run_resume_order_flow_script(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.get("/data-scripts/latest-order-sn")
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
