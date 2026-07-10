import copy
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import random
import threading
import time
from typing import Any, Dict, Tuple
from urllib.parse import urljoin

import requests

from ..executors import ensure_report_dirs, write_allure_result
from ..models import Env
from ..vendor import piliangtianjiagouwuche as bulk_cart
from .registry import SCRIPT_REGISTRY, register_script



SCRIPT_NAME = "\u5546\u54c1\u8d2d\u7269\u8f66"
ORDER_SCRIPT_NAME = "\u8ba2\u5355\u62a5\u4ef7"
BALANCE_PAYMENT_SCRIPT_NAME = "\u4f59\u989d\u652f\u4ed8"
BANK_PAYMENT_SCRIPT_NAME = "\u94f6\u884c\u652f\u4ed8"
PURCHASE_TO_SHELF_SCRIPT_NAME = "\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6"
WAREHOUSE_DELIVERY_SCRIPT_NAME = "\u4ed3\u5e93\u63d0\u51fa\u914d\u9001\u5355"
POORDER_BALANCE_PAYMENT_SCRIPT_NAME = "\u914d\u9001\u5355\u4f59\u989d\u4ed8\u6b3e"
POORDER_BANK_PAYMENT_SCRIPT_NAME = "\u914d\u9001\u5355\u94f6\u884c\u4ed8\u6b3e"
BALANCE_RECHARGE_SCRIPT_NAME = "\u4f59\u989d\u5145\u503c"
FULL_FLOW_SCRIPT_NAME = "\u5168\u6d41\u7a0b\u5b8c\u5168\u4f53"
FULL_FLOW_PART_PAY_SCRIPT_NAME = "全流程加入分批付款"
DIRECT_BOX_TO_SHELF_SCRIPT_NAME = "\u76f4\u63a5\u88c5\u7bb1\u4e0a\u67b6"
RESUME_ORDER_FLOW_SCRIPT_NAME = "输入订单号继续执行操作"
RESUME_PORDER_FLOW_SCRIPT_NAME = "输入配送单号继续执行操作"
FULL_FLOW_COMPLETE_NODE = "full_complete"
FULL_FLOW_NODE_LABELS = {
    "shopping_cart": "\u5546\u54c1\u52a0\u8d2d\u5b8c\u6210",
    "order_created": "\u524d\u53f0\u63d0\u4ea4\u8ba2\u5355\u5b8c\u6210",
    "order_translated": "\u540e\u53f0\u8ba2\u5355\u7ffb\u8bd1\u5b8c\u6210",
    "order_confirmed": "\u540e\u53f0\u8ba2\u5355\u786e\u8ba4\u5b8c\u6210",
    "order_offered": "\u540e\u53f0\u8ba2\u5355\u62a5\u4ef7\u5b8c\u6210",
    "order_paid": "\u8ba2\u5355\u652f\u4ed8\u5b8c\u6210",
    "pending_purchase": "\u8ba2\u5355\u8fdb\u5165\u5f85\u62cd\u4e0b",
    "purchase_no_saved": "\u4fdd\u5b58\u4ea4\u6613\u53f7\u5b8c\u6210",
    "purchase_wait_modify_price": "\u6807\u8bb0\u5f85\u6539\u4ef7\u5b8c\u6210",
    "purchase_wait_pay": "\u63d0\u4ea4\u5f85\u8d22\u52a1\u4ed8\u6b3e\u5b8c\u6210",
    "purchase_paid": "\u4ea4\u6613\u53f7\u4ed8\u6b3e\u5b8c\u6210",
    "checking_started": "\u5f00\u59cb\u6838\u67e5\u5b8c\u6210",
    "shelf_stored": "\u6838\u67e5\u4e0a\u67b6\u5165\u5e93\u5b8c\u6210",
    "warehouse_delivery_created": "\u4ed3\u5e93\u63d0\u51fa\u914d\u9001\u5355\u5b8c\u6210",
    "porder_translated": "\u914d\u9001\u5355\u5f85\u7ffb\u8bd1\u5b8c\u6210",
    "porder_confirmed": "\u914d\u9001\u5355\u786e\u8ba4\u6d41\u8f6c\u5b8c\u6210",
    "porder_wait_offer": "\u914d\u9001\u5355\u8fdb\u5165\u5f85\u62a5\u4ef7\u5b8c\u6210",
    "porder_offered": "\u914d\u9001\u5355\u62a5\u4ef7\u5b8c\u6210",
    "porder_paid": "\u914d\u9001\u5355\u652f\u4ed8\u5b8c\u6210",
    FULL_FLOW_COMPLETE_NODE: "\u5168\u6d41\u7a0b\u7ed3\u675f",
}
FULL_FLOW_NODE_SEQUENCE = [
    "shopping_cart",
    "order_created",
    "order_translated",
    "order_confirmed",
    "order_offered",
    "order_paid",
    "pending_purchase",
    "purchase_no_saved",
    "purchase_wait_modify_price",
    "purchase_wait_pay",
    "purchase_paid",
    "checking_started",
    "shelf_stored",
    "warehouse_delivery_created",
    "porder_translated",
    "porder_confirmed",
    "porder_wait_offer",
    "porder_offered",
    "porder_paid",
    FULL_FLOW_COMPLETE_NODE,
]
KEYWORDS = [
    "\u8863\u670d",
    "\u978b\u5b50",
    "\u978b",
    "usp",
    "USP",
    "\u5305",
    "\u5e3d\u5b50",
    "\u88d9\u5b50",
    "\u8033\u73af",
    "\u889c\u5b50",
    "\u624b\u673a\u58f3",
    "\u624b\u8868",
    "\u9879\u94fe",
    "\u6c34\u676f",
    "\u6587\u5177",
    "\u6536\u7eb3",
]
PREFERRED_KEYWORDS = ["衣服", "鞋子", "鞋", "包"]
SHOP_TYPES = ["1688", "taobao", "tmall", "rakumart"]
SHOP_TYPE_ALIASES = {}
MAX_LOG_BODY = 1200
REQUEST_RETRIES = 2
REQUEST_RETRY_DELAY = 0.8
ORDER_OPTION_NAME_FALLBACKS = {
    "1": "FBA贴标",
    "3": "更换OPP袋子",
    "4": "取布标",
    "5": "缝布标",
    "fba_label": "FBA贴标",
    "detail_inspection": "详细检品(单价)",
    "opp_bag": "更换OPP袋子",
    "remove_cloth_label": "取布标",
    "sew_cloth_label": "缝布标",
    "FBA贴标": "FBA贴标",
    "详细检品(单价)": "详细检品(单价)",
    "更换OPP袋子": "更换OPP袋子",
    "取布标": "取布标",
    "缝布标": "缝布标",
}


class DataScriptRuntime:
    def __init__(self) -> None:
        self._client_cache: Dict[tuple[Any, ...], tuple[Any, str]] = {}
        self._admin_token_cache: Dict[tuple[Any, ...], tuple[Dict[str, Any], str]] = {}
        self._admin_session: requests.Session | None = None

    def admin_session(self) -> requests.Session:
        """返回可复用的 admin requests.Session，在链式调用中保持 TCP 连接复用"""
        if self._admin_session is None:
            self._admin_session = requests.Session()
        return self._admin_session

    def client(
        self,
        env: Env,
        variables: Dict[str, Any],
        *,
        log: Dict[str, Any] | None = None,
        retry_login: bool = True,
    ) -> tuple[Any, str, int, str, bool]:
        account, password, client_tool = _client_login_inputs(variables)
        timeout = _as_int(variables.get("timeout"), env.timeout or 25)
        base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")
        key = (base_url, timeout, account, password, client_tool)
        cached = key in self._client_cache
        if cached:
            client, token = self._client_cache[key]
            _configure_client_api_paths(client, variables)
        else:
            client = bulk_cart.RakumartClient(base_url, timeout)
            _configure_client_api_paths(client, variables)
            login = lambda: client.login(account, password, client_tool)
            token = _call_with_retry("client login", login) if retry_login else login()
            self._client_cache[key] = (client, str(token))
        if log is not None:
            log["login"] = {
                "success": True,
                "account": account,
                "client_tool": client_tool,
                "token_extracted": bool(token),
                "cached": cached,
            }
        return client, base_url, timeout, str(token), cached

    def admin_login(
        self,
        session: requests.Session,
        base_url: str,
        variables: Dict[str, Any],
        timeout: int,
    ) -> tuple[Dict[str, Any], str, bool]:
        key = (
            base_url.rstrip("/"),
            timeout,
            str(variables.get("backend_account") or variables.get("backend_username") or "Y001"),
            str(variables.get("backend_password") or "raku@123456``"),
            str(variables.get("backend_system") or "1"),
            str(variables.get("backend_compute_token") or ""),
            str(variables.get("backend_code") or "wnm666"),
        )
        cached = key in self._admin_token_cache
        if cached:
            payload, token = self._admin_token_cache[key]
        else:
            payload, token = _admin_login_without_runtime(session, base_url, variables, timeout)
            if token:
                self._admin_token_cache[key] = (payload, token)
        if token:
            session.headers.update(_admin_headers(token))
        return payload, token, cached































































































































# 后端日文错误提示 → 中文映射（命中即替换，未命中保留原文+数字）
_ORDER_MSG_TRANSLATIONS = {
    "注文提出商品数が最大制限に達しました": "订单提交商品数已达最大限制",
    "操作が成功しました": "操作成功",
    "ログインに失敗しました": "登录失败",
    "パラメータエラー": "参数错误",
    "システムエラー": "系统错误",
    "注文情報が存在しません": "订单信息不存在",
    "カート情報が存在しません": "购物车信息不存在",
    "在庫が不足しています": "库存不足",
}




































ORDER_PART_PAY_FEE_KEYS = ["domestic_freight", "service_fee", "additional_service_fee", "other_fee"]
ORDER_PART_PAY_TAIL_NODES = {"before_shelf", "before_porder_create"}
































































PORDER_AMOUNT_KEYS = [
    "pay_amount",
    "total_amount",
    "need_pay_amount",
    "wait_pay_amount",
    "payment_amount",
    "porder_amount",
    "porder_price",
    "delivery_amount",
    "delivery_price",
    "logistics_price",
    "logistics_amount",
    "international_freight",
    "freight_price",
    "freight_amount",
    "amount",
    "total",
]
















































































































































































































































MATERIAL_GENERATION_SCRIPT_NAME = "辅料生成"
MATERIAL_ORDER_SCRIPT_NAME = "辅料单"










# 注册脚本函数






BALANCE_INSUFFICIENT_MARKERS = [
    "\u4f59\u989d\u4e0d\u8db3",
    "\u8d26\u6237\u91d1\u989d",
    "\u53ef\u7528\u4f59\u989d",
    "\u4f59\u989d\u4e0d\u591f",
    "insufficient",
    "not enough",
]
FULL_FLOW_SHARED_KEYS = [
    "order_sn",
    "purchase_no",
    "purchase_ids",
    "grid_id",
    "grid_number",
    "order_detail_id",
    "order_detail_ids",
    "porder_sn",
    "porder_detail_id",
    "porder_detail_ids",
    "freight_id",
    "warehouse_sku_count",
    "actual_warehouse_sku_count",
    "selected_sku_ids",
    "total_send_num",
    "serial_number",
    "payment_type",
    "pay_amount",
]


























































# ─── OEM 独立数据脚本（与日本站完全隔离，不影响日本站脚本）──────────────

OEM_SCRIPT_NAME = "OEM创建询价单"
OEM_DEFAULT_FRONTEND_ORIGIN = "https://oem.rakumart.cn"
OEM_DEFAULT_ADMIN_ORIGIN = "https://oemadmin.rakumart.cn"












OEM_OSS_BUCKET = "rakumart-oem"
OEM_OSS_ENDPOINT = "oss-ap-northeast-1.aliyuncs.com"










# ─── OEM 样品单提出脚本 ───────────────────────────────────────────────

OEM_SAMPLE_ORDER_SCRIPT_NAME = "OEM提出样品单"


# OEM 后端常见日文错误信息 → 中文翻译
_OEM_MSG_TRANSLATIONS = {
    "操作に失敗しました": "操作失败",
    "操作成功": "操作成功",
    "SKU形式が正しくありません": "SKU 格式不正确",
    "パラメータエラー": "参数错误",
    "システムエラー": "系统错误",
    "ログインに失敗しました": "登录失败",
    "権限がありません": "无权限",
    "データが存在しません": "数据不存在",
    "注文情報が存在しません": "订单信息不存在",
    "在庫が不足しています": "库存不足",
}




# OEM 单子属性映射：body.type 值 → 单号后缀
_OEM_ORDER_TYPE_LABELS = {
    1: "OEM",
    2: "ODM",
    3: "FL",
}














# ─── OEM 询价单全流程脚本（提出→翻译→询价→报价） ──────────────────────

OEM_FULL_INQUIRY_SCRIPT_NAME = "OEM询价单全流程"










# ─── OEM 样品单后台管理流程 ─────────────────────────────────────────

OEM_SAMPLE_ADMIN_SCRIPT_NAME = "OEM样品单后台流程"










# ─── OEM 样品单全流程（提出 + 后台管理）─────────────────────────────

OEM_SAMPLE_FULL_FLOW_NAME = "OEM样品单全流程"




# ─── OEM 大货单下单 ────────────────────────────────────────────

OEM_BULK_ORDER_NAME = "OEM大货单下单"


















# ─── OEM 样品单余额支付 ────────────────────────────────────────────

OEM_BALANCE_PAY_NAME = "OEM样品单余额支付"


from .data_script_shared import (
    _runtime_from_variables,
    _admin_session_from,
    _client_login_inputs,
    _as_list,
    _unique_list,
    _as_int,
    _clean_multipart_headers,
    _post_form,
    _response_json,
    _response_brief,
    _extract_token,
    _data_object,
    _goods_items,
    _first_stock,
    _detail_specs,
    _cart_payload,
    _auth_headers,
    _auth_form_fields,
    _duration_ms,
    _finish_named,
    _finish,
    _stop_after_node,
    _checkpoint_requested,
    _paused_summary,
    _is_paused,
    _finish_paused,
)
from .cart_support import (
    _legacy_run_shopping_cart_script,
    _as_float,
    _as_bool,
    _quantity_cycle,
    _item_brief,
    _cart_text,
    _cart_item_matches,
    _verify_cart_contains_items,
    _api_success,
    _api_paths,
    _api_path,
    _client_login_with_path,
    _configure_client_api_paths,
    _payload_brief,
    _order_text,
    _first_price,
    _json_list,
    _order_option_items,
    _order_option_key,
    _order_option_label,
    _normalize_order_option_counts,
    _add_order_option_to_catalog,
    _order_option_catalog_from_options,
    _collect_order_option_catalog,
    _public_order_options,
    _order_option_list_path,
    _fetch_order_option_catalog,
    _apply_order_options_to_items,
    _flatten_cart_goods,
    _cart_item_ready,
    _select_cart_items,
    _cart_shop_key,
    _select_cart_items_by_shop,
    _order_item_brief,
    _edit_cart_fields,
    _cart_item_quantity,
    _authed_client_with_token,
    _edit_cart_items_for_order,
)
from .order_support import (
    _translate_order_msg,
    _parse_order_max_limit,
    _order_fields,
    _extract_order_sn,
    _decimal_text,
    _money_total,
    _admin_headers,
    _call_with_retry,
    _post_admin_form,
    _flatten_urlencoded_fields,
    _post_admin_urlencoded,
    _admin_login_without_runtime,
    _admin_login,
    _order_detail_data,
    _admin_detail_brief,
    _prepare_translate_data,
    _build_confirm_data,
    _order_part_pay_enabled,
    _full_flow_part_pay_script_enabled,
    _order_part_pay_requested,
    _order_part_pay_percent,
    _order_part_pay_tail_node,
    _order_part_pay_fee_timing,
    _apply_order_part_pay_payload,
    _order_part_pay_api_node,
    _order_part_pay_api_fee_flag,
    _order_part_pay_goods_total,
    _order_part_pay_first_goods_amount,
    _order_part_pay_plan_fields,
    _save_order_part_pay_plan_if_needed,
    _prepare_offer_data,
    _run_backend_order_flow,
    _order_status_code,
    _resume_node_for_order_status,
    _order_detail_ids,
    _order_ready_for_warehouse_delivery,
    _purchase_is_pending_start,
    _detect_resume_order_state,
    _run_backend_order_flow_resume,
    preview_order_quote_options,
)


from .payment_support import (
    _positive_decimal,
    _first_positive_decimal,
    _order_rows_from_payload,
    _order_payment_amount,
    _payment_order_list_fields,
    _select_payment_order,
    _login_client_for_payment,
    _load_payment_order,
    _common_payment_summary,
    _first_recursive_positive_decimal,
    _porder_payload_matches,
    _porder_payment_summary,
    _porder_payment_amount_from_payload,
    _load_porder_payment_amount,
    _apply_extra_fields,
    _order_tail_payment_order_sn,
    _order_tail_payment_mode,
    _order_tail_payment_path,
    _order_tail_pay_amount_from_variables,
    _order_tail_value_list,
    _order_tail_partial_enabled,
    _order_tail_partial_select_by,
    _order_tail_partial_selected_values,
    _order_tail_detail_id,
    _order_tail_detail_sorting,
    _order_tail_detail_status,
    _order_tail_detail_is_paid,
    _order_tail_detail_is_unpaid,
    _order_tail_order_detail_rows,
    _order_tail_unpaid_ids_from_detail,
    _order_tail_detail_fields,
    _order_tail_pay_data_fields,
    _order_tail_apply_payment_detail_fields,
    _order_tail_pay_data_brief,
    _order_tail_pay_amount_from_pay_data,
    _order_tail_pay_data_unpayable_ids,
    _resolve_order_tail_partial_context,
    _public_order_tail_context,
    _order_tail_bank_pay_amount,
    _run_order_tail_payment_if_needed,
    _bank_pay_reach_date,
    _finance_rows_from_payload,
    _finance_bill_brief,
    _row_contains_text,
    _select_finance_bill,
    _finance_unconfirm_fields,
    _admin_rows_from_payload,
    _field_text,
)
from .purchase_support import (
    _purchase_timestamp_no,
    _purchase_list_fields,
    _flatten_purchase_items,
    _purchase_item_id,
    _select_purchase_items,
    _positive_text,
    _purchase_item_values,
    _purchase_status_name,
    _purchase_save_rows,
    _purchase_wait_pay_rows,
    _purchase_item_brief,
    _purchase_order_detail_id,
    _purchase_wait_pay_fields,
    _select_purchase_wait_pay,
    _finance_purchase_brief,
    _follow_list_fields,
    _flatten_follow_items,
    _preview_rows_from_payload,
    _preview_items,
    _order_purchase_id,
    _item_up_num,
    _items_already_checking,
    _first_preview_user_id,
    _unique_values,
    _purchase_status_code,
    _purchase_still_pending,
    _verify_purchase_to_shelf_completed,
    _walk_grid_candidates,
    _grid_candidates,
    _select_grid_from_payload,
    _step,
)


from .warehouse_support import (
    _porder_sn,
    _warehouse_list_fields,
    _warehouse_candidate_paths,
    _nested_rows,
    _field_value,
    _warehouse_item_id,
    _warehouse_sku_id,
    _warehouse_sendable_num,
    _warehouse_item_brief,
    _warehouse_requested_order_detail_ids,
    _warehouse_row_order_sn,
    _warehouse_row_matches_current_order,
    _select_warehouse_items,
    _select_warehouse_item,
    _address_fields,
    _default_receiver_address,
    _default_importer_address,
    _merge_address,
    _porder_create_fields_for_items,
    _porder_create_fields,
    _extract_porder_sn,
    _walk_dicts,
    _first_deep_value,
    _porder_detail_rows,
    _porder_detail_id,
    _porder_wait_box_num,
    _box_need_num,
    _extract_freight_id,
    _payload_structure_sample,
    _freight_box_brief,
    _has_incomplete_freight_box,
    _porder_complete_box_paths,
    _extract_stock_item,
    _stock_item_from_row,
    _extract_stock_item_for_detail,
    _porder_flow_detail_items,
    _porder_detail_payload,
    _porder_detail_brief,
)
from .porder_flow_support import (
    _run_backend_porder_flow,
)
from .porder_resume_support import (
    _run_backend_porder_flow_resume,
    _porder_detail_status_texts,
    _porder_node_from_status_texts,
    _detect_resume_porder_state,
)


from .full_flow_support import (
    _summary_text,
    _looks_like_balance_insufficient,
    _payment_with_bank_fallback,
    _direct_box_int,
    _direct_box_text,
    _direct_box_configs,
    _direct_box_rows,
    _direct_box_id,
    _direct_box_sort_key,
    _direct_box_order_sn,
    _direct_box_units,
    _direct_box_counts,
    _direct_box_allocations,
    _direct_box_prepare_to_checking,
    _full_flow_update_shared,
    _full_flow_record_step,
    _full_flow_node_results,
    _full_flow_finish,
    _resume_record_skipped,
    _resume_flow_finish,
    _full_flow_stop_reached,
    _full_flow_prepare_warehouse_counts,
)
from .oem_support import (
    OEM_DEFAULT_BASE_URL,
    _oem_post_json,
    _oem_admin_login,
    _oem_client_login,
    _oem_get_upload_token,
    _oss_put_object,
    upload_oem_image,
    _oem_parse_factory_urls,
    _oem_extract_factory_iid,
    _translate_oem_msg,
    _oem_order_type_label,
    _oem_generate_sample_order_sn,
    fetch_oem_goods_class_list,
    fetch_oem_option_list,
    fetch_oem_full_quote,
    _oem_normalize_goods_class,
    _oem_query_inquiry_detail,
    _oem_submit_node,
    _oem_admin_post,
    _call_admin_api,
    _oem_build_sku_info_from_quote,
    _oem_query_option_list,
    _oem_generate_large_order_sn,
    _oem_order_preview,
    _oem_edit_sku_image,
    _oem_create_new_order,
    _oem_build_option_for_sku,
    _oem_build_warehouse_for_sku,
)
