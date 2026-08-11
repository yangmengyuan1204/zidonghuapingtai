import json
import sys
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.utils import (
    CART_CASE_NAME,
    OEM_DATA_SCRIPT_PROJECT_NAME,
    apply_frontend_customer_login_variables,
    account_profile_variables,
    data_script_variables,
    find_oem_data_script_project,
    get_or_404,
    resolve_data_script_context,
    save_record,
    schema_data,
    serialize,
    split_customer_ids,
)
from ..data_scripts import (
    run_material_order_script,
    fetch_oem_goods_class_list,
    fetch_oem_option_list,
    preview_order_quote_options,
    run_balance_adjustment_script,
    run_balance_payment_script,
    run_balance_recharge_script,
    run_bank_payment_script,
    run_direct_box_to_shelf_script,
    run_full_flow_script,
    run_material_generation_script,
    run_oem_full_inquiry_flow_script,
    run_oem_new_inquiry_script,
    run_oem_sample_admin_flow_script,
    run_oem_sample_balance_pay_script,
    run_oem_bulk_order_script,
    run_oem_sample_full_flow_script,
    run_oem_sample_order_script,
    fetch_oem_full_quote,
    run_order_quote_script,
    run_payment_amount_regression_script,
    run_problem_goods_script,
    run_porder_balance_payment_script,
    run_porder_bank_payment_script,
    run_porder_shipment_script,
    run_purchase_to_shelf_chain,
    run_purchase_to_shelf_script,
    run_resume_order_flow_script,
    run_resume_porder_flow_script,
    run_shopping_cart_script,
    run_warehouse_delivery_script,
    upload_oem_image,
)
from ..data_scripts.problem_goods import ProblemGoodsError, fetch_problem_goods_options, inspect_problem_goods
from ..database import get_db
from ..models import ApiCase, Env, TestAccountProfile, TestRecord, User
from ..schemas import DataScriptExecuteRequest
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api", tags=["data-scripts"])


def _runtime_func(name: str, fallback: Any) -> Any:
    fallback_module = getattr(fallback, "__module__", "")
    if fallback_module and not fallback_module.startswith("app."):
        return fallback
    main_module = sys.modules.get("app.main")
    return getattr(main_module, name, fallback) if main_module else fallback


def _oem_data_script_variables(
    db: Session,
    env: Env,
    variables: Dict[str, Any] | None,
    project_id: int,
) -> Dict[str, Any]:
    env_variables: Dict[str, Any] = {}
    if env.global_vars:
        try:
            configured = json.loads(env.global_vars)
            if isinstance(configured, dict):
                env_variables.update(configured)
        except (json.JSONDecodeError, TypeError):
            pass
    return data_script_variables(db, {**env_variables, **dict(variables or {})}, project_id)


def _backend_profile_id_for_account(
    db: Session,
    project_id: int,
    account: str,
) -> int | None:
    matches: list[int] = []
    profiles = (
        db.query(TestAccountProfile)
        .filter(
            TestAccountProfile.status == "active",
            or_(
                TestAccountProfile.project_id == project_id,
                TestAccountProfile.project_id.is_(None),
            ),
        )
        .order_by(TestAccountProfile.id.asc())
        .all()
    )
    for profile in profiles:
        account_vars, _ = account_profile_variables(db, int(profile.id), project_id)
        profile_account = (
            account_vars.get("backend_account")
            or account_vars.get("username")
            or account_vars.get("account")
        )
        if str(profile_account or "").strip() == account:
            matches.append(int(profile.id))
    return matches[0] if len(matches) == 1 else None


def _resolve_backend_account_variables(
    db: Session,
    variables: Dict[str, Any],
    project_id: int,
) -> Dict[str, Any]:
    resolved = dict(variables)
    profile_id = resolved.get("backend_account_profile_id") or resolved.get("admin_account_profile_id")
    if not profile_id:
        profile_id = _backend_profile_id_for_account(db, project_id, "Y001")
    if profile_id:
        account_vars, meta = account_profile_variables(db, int(profile_id), project_id)
        backend_account = account_vars.get("backend_account") or account_vars.get("username") or account_vars.get("account")
        backend_password = account_vars.get("backend_password") or account_vars.get("password")
        if not backend_account or not backend_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="所选后台账号档案缺少账号或密码")
        resolved.update(account_vars)
        resolved.update(
            {
                "backend_account": str(backend_account),
                "backend_password": str(backend_password),
                "backend_code": str(account_vars.get("backend_code") or account_vars.get("code") or ""),
                "backend_account_profile_id": int(profile_id),
                "backend_account_profile_name": meta.get("profile_name") or "",
            }
        )
        return resolved
    backend_account = resolved.get("backend_account") or resolved.get("backend_username")
    backend_password = resolved.get("backend_password")
    is_legacy_builtin = str(backend_account or "").strip() == "Y001" and str(
        backend_password or ""
    ) in {"raku@123456``", "xiaolin666@@"}
    if backend_account and backend_password and not is_legacy_builtin:
        return resolved
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="未配置后台账号档案，请先为当前项目绑定可查看该订单的后台账号",
    )


def _problem_goods_variables(
    db: Session,
    payload: DataScriptExecuteRequest,
    project_id: int,
) -> Dict[str, Any]:
    variables = data_script_variables(db, payload.variables, project_id)
    profile_id = variables.get("backend_account_profile_id") or variables.get("admin_account_profile_id")
    if not profile_id:
        return variables
    account_vars, meta = account_profile_variables(db, int(profile_id), project_id)
    backend_account = account_vars.get("backend_account") or account_vars.get("username") or account_vars.get("account")
    backend_password = account_vars.get("backend_password") or account_vars.get("password")
    backend_code = account_vars.get("backend_code") or account_vars.get("code") or ""
    if not backend_account or not backend_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="所选后台账号档案缺少账号或密码")
    variables.update(
        {
            "backend_account": str(backend_account),
            "backend_password": str(backend_password),
            "backend_code": str(backend_code),
            "backend_account_profile_id": int(profile_id),
            "backend_account_profile_name": meta.get("profile_name") or "",
        }
    )
    return variables


@router.post("/data-scripts/shopping-cart")
def run_shopping_cart_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_shopping_cart_script", run_shopping_cart_script)(env, variables)
    cart_case = db.query(ApiCase).filter(ApiCase.case_name == CART_CASE_NAME, ApiCase.project_id == project_id).order_by(ApiCase.id.asc()).first()
    record = save_record(db, "api", cart_case.id if cart_case else 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="shopping_cart", env_id=env.id, variables=payload.variables)
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
    passed, log_text, report_path, summary = _runtime_func("run_order_quote_script", run_order_quote_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="order_quote", env_id=env.id, variables=payload.variables)
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
    try:
        return _runtime_func("preview_order_quote_options", preview_order_quote_options)(env, variables)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"读取订单选项失败：{exc}") from exc


@router.post("/data-scripts/balance-payment")
def run_balance_payment_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_balance_payment_script", run_balance_payment_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="balance_payment", env_id=env.id, variables=payload.variables)
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
    passed, log_text, report_path, summary = _runtime_func("run_bank_payment_script", run_bank_payment_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="bank_payment", env_id=env.id, variables=payload.variables)
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
        passed, log_text, report_path, summary = _runtime_func("run_purchase_to_shelf_chain", run_purchase_to_shelf_chain)(env, variables)
    else:
        passed, log_text, report_path, summary = _runtime_func("run_purchase_to_shelf_script", run_purchase_to_shelf_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="purchase_to_shelf", env_id=env.id, variables=payload.variables)
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
    passed, log_text, report_path, summary = _runtime_func("run_purchase_to_shelf_chain", run_purchase_to_shelf_chain)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="purchase_to_shelf_chain", env_id=env.id, variables=payload.variables)
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
    passed, log_text, report_path, summary = _runtime_func("run_direct_box_to_shelf_script", run_direct_box_to_shelf_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="direct_box_to_shelf", env_id=env.id, variables=payload.variables)
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
    passed, log_text, report_path, summary = _runtime_func("run_warehouse_delivery_script", run_warehouse_delivery_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="warehouse_delivery", env_id=env.id, variables=payload.variables)
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
    passed, log_text, report_path, summary = _runtime_func("run_porder_balance_payment_script", run_porder_balance_payment_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="porder_balance_payment", env_id=env.id, variables=payload.variables)
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
    passed, log_text, report_path, summary = _runtime_func("run_porder_bank_payment_script", run_porder_bank_payment_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="porder_bank_payment", env_id=env.id, variables=payload.variables)
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
    variables = _resolve_backend_account_variables(
        db,
        data_script_variables(db, payload.variables, project_id),
        project_id,
    )
    passed, log_text, report_path, summary = _runtime_func("run_full_flow_script", run_full_flow_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="full_flow", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.post("/data-scripts/payment-amount-regression")
def run_payment_amount_regression_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = _resolve_backend_account_variables(
        db,
        data_script_variables(db, payload.variables, project_id),
        project_id,
    )
    passed, log_text, report_path, summary = _runtime_func(
        "run_payment_amount_regression_script",
        run_payment_amount_regression_script,
    )(env, variables)
    record = save_record(
        db,
        "api",
        0,
        passed,
        log_text,
        report_path,
        project_id=project_id,
        kind="data_script",
        script_key="payment_amount_regression",
        env_id=env.id,
        variables=payload.variables,
    )
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
    variables = _resolve_backend_account_variables(
        db,
        data_script_variables(db, payload.variables, project_id),
        project_id,
    )
    passed, log_text, report_path, summary = _runtime_func("run_resume_order_flow_script", run_resume_order_flow_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="resume_order_flow", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.post("/data-scripts/porder-shipment")
def run_porder_shipment_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = _resolve_backend_account_variables(
        db,
        data_script_variables(db, payload.variables, project_id),
        project_id,
    )
    passed, log_text, report_path, summary = _runtime_func("run_porder_shipment_script", run_porder_shipment_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="porder_shipment", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data

@router.post("/data-scripts/resume-porder-flow")
def run_resume_porder_flow_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_resume_porder_flow_script", run_resume_porder_flow_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="resume_porder_flow", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.post("/data-scripts/material-generation")
def run_material_generation_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_material_generation_script", run_material_generation_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="material_generation", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data



@router.post("/data-scripts/material-order")
def run_material_order_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_material_order_script", run_material_order_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="material_order", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data






@router.post("/data-scripts/balance-recharge")
def run_balance_recharge_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_balance_recharge_script", run_balance_recharge_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="balance_recharge", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.post("/data-scripts/balance-adjustment")
def run_balance_adjustment_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = data_script_variables(db, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func(
        "run_balance_adjustment_script",
        run_balance_adjustment_script,
    )(env, variables)
    record = save_record(
        db,
        "api",
        0,
        passed,
        log_text,
        report_path,
        project_id=project_id,
        kind="data_script",
        script_key="balance_adjustment",
        env_id=env.id,
        variables=payload.variables,
    )
    data = serialize(record)
    data["summary"] = summary
    return data


@router.post("/data-scripts/problem-goods/inspect")
def inspect_problem_goods_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = _problem_goods_variables(db, payload, project_id)
    try:
        return inspect_problem_goods(env, variables)
    except ProblemGoodsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/data-scripts/problem-goods/options")
def get_problem_goods_options_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = _problem_goods_variables(db, payload, project_id)
    try:
        return fetch_problem_goods_options(env, variables)
    except ProblemGoodsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/data-scripts/problem-goods")
def run_problem_goods_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = _problem_goods_variables(db, payload, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_problem_goods_script", run_problem_goods_script)(env, variables)
    record = save_record(
        db,
        "api",
        0,
        passed,
        log_text,
        report_path,
        project_id=project_id,
        kind="data_script",
        script_key="problem_goods",
        env_id=env.id,
        variables=payload.variables,
    )
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


# ─── OEM 数据脚本路由（独立项目 oem-测试，不影响日本站）──────────────


@router.post("/data-scripts/oem-new-inquiry")
def run_oem_new_inquiry_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = _oem_data_script_variables(db, env, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_oem_new_inquiry_script", run_oem_new_inquiry_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="oem_new_inquiry", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.post("/data-scripts/oem-sample-order")
def run_oem_sample_order_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = _oem_data_script_variables(db, env, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_oem_sample_order_script", run_oem_sample_order_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="oem_sample_order", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.post("/data-scripts/oem-sample-admin-flow")
def run_oem_sample_admin_flow_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = _oem_data_script_variables(db, env, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_oem_sample_admin_flow_script", run_oem_sample_admin_flow_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="oem_sample_admin_flow", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.post("/data-scripts/oem-full-inquiry-flow")
def run_oem_full_inquiry_flow_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = _oem_data_script_variables(db, env, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_oem_full_inquiry_flow_script", run_oem_full_inquiry_flow_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="oem_full_inquiry_flow", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.post("/data-scripts/oem-sample-full-flow")
def run_oem_sample_full_flow_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = _oem_data_script_variables(db, env, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_oem_sample_full_flow_script", run_oem_sample_full_flow_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="oem_sample_full_flow", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.post("/data-scripts/oem-bulk-order")
def run_oem_bulk_order_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = _oem_data_script_variables(db, env, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_oem_bulk_order_script", run_oem_bulk_order_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="oem_bulk_order", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.post("/data-scripts/oem-sample-balance-pay")
def run_oem_sample_balance_pay_data_script(
    payload: DataScriptExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    env, project_id = resolve_data_script_context(db, payload)
    variables = _oem_data_script_variables(db, env, payload.variables, project_id)
    passed, log_text, report_path, summary = _runtime_func("run_oem_sample_balance_pay_script", run_oem_sample_balance_pay_script)(env, variables)
    record = save_record(db, "api", 0, passed, log_text, report_path, project_id=project_id, kind="data_script", script_key="oem_balance_pay", env_id=env.id, variables=payload.variables)
    data = serialize(record)
    data["summary"] = summary
    return data


@router.get("/oem/inquiry-full")
def get_oem_full_quote(
    order_sn: str = Query(..., description="询价单号，如 X20260615132111-15-OEM"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """根据询价单号查询完整报价详情（两步：inquiryDetail → quoteDetail）。"""
    project = find_oem_data_script_project(db)
    if not project:
        return {"success": False, "data": {}, "message": "未找到 OEM 项目"}
    env = db.query(Env).filter(Env.project_id == project.id).order_by(Env.id.asc()).first()
    if not env:
        return {"success": False, "data": {}, "message": "未找到 OEM 环境"}
    variables: Dict[str, Any] = {"base_url": env.base_url}
    if env.global_vars:
        try:
            global_vars = json.loads(env.global_vars)
            if isinstance(global_vars, dict):
                variables.update(global_vars)
        except (json.JSONDecodeError, TypeError):
            pass
    data = fetch_oem_full_quote(order_sn, variables)
    return {"success": True, "data": data}


@router.get("/oem/goods-class-list")
def get_oem_goods_class_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """获取 OEM 商品分类列表，供前端下拉选择。"""
    project = find_oem_data_script_project(db)
    if not project:
        return {"success": False, "data": [], "message": "未找到 OEM 项目"}
    env = db.query(Env).filter(Env.project_id == project.id).order_by(Env.id.asc()).first()
    if not env:
        return {"success": False, "data": [], "message": "未找到 OEM 环境"}
    variables: Dict[str, Any] = {"base_url": env.base_url}
    if env.global_vars:
        try:
            global_vars = json.loads(env.global_vars)
            if isinstance(global_vars, dict):
                variables.update(global_vars)
        except (json.JSONDecodeError, TypeError):
            pass
    try:
        data = fetch_oem_goods_class_list(variables)
        return {"success": True, "data": data}
    except Exception as exc:
        return {
            "success": False,
            "data": [],
            "message": f"获取商品分类列表失败: {exc}",
        }


@router.get("/oem/option-list")
def get_oem_option_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """获取 OEM 大货单可选 option 列表（/common/common/optionList）。"""
    project = find_oem_data_script_project(db)
    if not project:
        return {"success": False, "data": [], "message": "未找到 OEM 项目"}
    env = db.query(Env).filter(Env.project_id == project.id).order_by(Env.id.asc()).first()
    if not env:
        return {"success": False, "data": [], "message": "未找到 OEM 环境"}
    variables: Dict[str, Any] = {"base_url": env.base_url}
    if env.global_vars:
        try:
            global_vars = json.loads(env.global_vars)
            if isinstance(global_vars, dict):
                variables.update(global_vars)
        except (json.JSONDecodeError, TypeError):
            pass
    data = fetch_oem_option_list(variables)
    return {"success": True, "data": data}


@router.post("/oem/upload-image")
async def upload_oem_image_route(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """OEM 商品图片上传：前端选文件 -> 后端登录OEM -> 拿STS -> PUT到OSS -> 返回URL。"""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件不能为空")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件过大，最大 20MB")
    content_type = file.content_type or "application/octet-stream"
    try:
        url = upload_oem_image(file.filename or "upload.png", content, content_type)
        return {"url": url}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"OEM 图片上传失败: {exc}") from exc





