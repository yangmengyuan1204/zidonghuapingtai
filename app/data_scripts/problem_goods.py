from __future__ import annotations

import json
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Tuple
from urllib.parse import urljoin

import requests

from ..vendor import piliangtianjiagouwuche as bulk_cart
from .data_script_shared import _admin_session_from, _finish_named, _runtime_from_variables
from .order_support import _admin_login


PROBLEM_GOODS_SCRIPT_NAME = "日本站问题产品处理"

STATUS_CANCELLED = -1
STATUS_TRANSLATE_PENDING = 1
STATUS_CLIENT_PENDING = 2
STATUS_BUSINESS_PENDING = 3
STATUS_PURCHASE_PENDING = 4
STATUS_DISTRIBUTION_PENDING = 5
STATUS_COMPLETED = 6

STATUS_NAMES = {
    STATUS_CANCELLED: "问题商品取消",
    STATUS_TRANSLATE_PENDING: "待翻译",
    STATUS_CLIENT_PENDING: "待客户处理",
    STATUS_BUSINESS_PENDING: "待业务决策",
    STATUS_PURCHASE_PENDING: "待采购处理",
    STATUS_DISTRIBUTION_PENDING: "待配货确认",
    STATUS_COMPLETED: "已完成",
}

PROBLEM_TYPES = {
    1: "单价变动",
    2: "运费变动",
    3: "少货",
    4: "不良",
    5: "不良且少货",
    6: "option变动",
    7: "数量多了",
    8: "其他",
    9: "客户原因",
    10: "不良直接上架",
}

SERVICE_DEAL_TYPES = {1: "已收不退", 2: "多退少补"}
OPTION_DEAL_TYPES = {1: "按照业务修改值计算", 2: "系统自动计算"}
PURCHASE_DEAL_TYPES = {"退货退款", "换货", "丢货重拍", "少货补买", "其他", "仅退款"}

CLIENT_DEAL_VALUES = {
    "accept": "クイック処理受け入れ",
    "exchange": "クイック処理交換",
    "cancel": "クイック処理返品/購入キャンセル",
    "discard": "クイック処理廃棄",
}

PERMISSION_ERROR_PATTERNS = (
    "大于500人民币需要部长",
    "部长账号进行退款",
    "需要部长账号",
    "请联系部长",
)


class ProblemGoodsError(RuntimeError):
    pass


class ProblemGoodsApiError(ProblemGoodsError):
    def __init__(self, action: str, payload: Dict[str, Any] | None = None):
        self.action = action
        self.payload = payload or {}
        message = str(self.payload.get("msg") or self.payload.get("message") or "接口返回失败")
        super().__init__(f"{action}失败：{message}")


class ProblemGoodsMutationUncertain(ProblemGoodsError):
    """写接口网络结果不确定；调用方必须先查状态，禁止直接重试。"""


def _bool_value(value: Any, fallback: bool = False) -> bool:
    if value in (None, ""):
        return fallback
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {"0", "false", "no", "off", "否"}


def _decimal(value: Any, label: str, *, non_negative: bool = True) -> Decimal:
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, ValueError):
        raise ProblemGoodsError(f"{label}必须是数字")
    if not parsed.is_finite():
        raise ProblemGoodsError(f"{label}必须是有限数字")
    if non_negative and parsed < 0:
        raise ProblemGoodsError(f"{label}不能小于0")
    return parsed


def _integer(value: Any, label: str, *, positive: bool = False) -> int:
    parsed = _decimal(value, label)
    if parsed != parsed.to_integral_value():
        raise ProblemGoodsError(f"{label}必须是整数")
    number = int(parsed)
    if positive and number <= 0:
        raise ProblemGoodsError(f"{label}必须大于0")
    return number


def _decimal_text(value: Any, label: str) -> str:
    parsed = _decimal(value, label)
    text = format(parsed, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _status(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def customer_id_from_order_sn(order_sn: str) -> str:
    match = re.fullmatch(r"[^\s-]+-(\d+)", str(order_sn or "").strip())
    if not match:
        raise ProblemGoodsError("订单号格式有误，无法解析客户ID")
    return match.group(1)


def normalize_customer_id(order_sn: str, customer_id: Any = "") -> str:
    suffix_id = customer_id_from_order_sn(order_sn)
    supplied = str(customer_id or "").strip()
    if supplied and not supplied.isdigit():
        raise ProblemGoodsError("客户ID只能是数字")
    if supplied and supplied != suffix_id:
        raise ProblemGoodsError(f"客户ID与订单号后缀不一致：{supplied} != {suffix_id}")
    return supplied or suffix_id


def _json_array(value: Any, label: str) -> list[Dict[str, Any]]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            raise ProblemGoodsError(f"{label}不是有效JSON")
    if not isinstance(value, list):
        raise ProblemGoodsError(f"{label}必须是数组")
    return [dict(item) for item in value if isinstance(item, dict)]


def validate_manual_options(options: Any, original_options: Any = None) -> list[Dict[str, Any]]:
    rows = _json_array(options, "修改后OPTION")
    original_rows = _json_array(original_options, "原始OPTION")
    original_types = {
        str(item.get("name") or "").strip(): str(item.get("price_type"))
        for item in original_rows
        if str(item.get("name") or "").strip()
    }
    names: set[str] = set()
    for item in rows:
        name = str(item.get("name") or "").strip()
        if not name:
            raise ProblemGoodsError("OPTION名称不能为空")
        if name in names:
            raise ProblemGoodsError(f"OPTION名称重复：{name}")
        names.add(name)
        price_type = str(item.get("price_type"))
        if price_type not in {"0", "1"}:
            raise ProblemGoodsError(f"OPTION计价类型有误：{name}")
        if name in original_types and original_types[name] != price_type:
            raise ProblemGoodsError(f"不允许修改OPTION计价类型：{name}")
        _decimal(item.get("num"), f"OPTION数量({name})")
        _decimal(item.get("price"), f"OPTION价格({name})")
    return rows


def validate_auto_option_eligibility(original_options: Any, old_possible_num: Any, new_num: Any) -> None:
    options = [item for item in _json_array(original_options, "原始OPTION") if _bool_value(item.get("checked"), False)]
    rate_options = [item for item in options if str(item.get("price_type")) == "1"]
    if len(rate_options) > 1:
        raise ProblemGoodsError("存在多个百分比OPTION，必须选择“按照业务修改值计算”")
    if old_possible_num in (None, ""):
        return
    old_num = _integer(old_possible_num, "当前可入库数")
    desired_num = _integer(new_num, "修改后数量")
    if desired_num > old_num:
        raise ProblemGoodsError("商品数量增加时必须选择“按照业务修改值计算”OPTION")
    for item in options:
        option_num = _decimal(item.get("num"), f"OPTION数量({item.get('name') or ''})")
        if option_num > old_num:
            raise ProblemGoodsError("OPTION数量大于商品数，必须选择“按照业务修改值计算”")


def client_deal_text(choice: Any, other_text: Any = "") -> str:
    value = str(choice or "accept").strip()
    if value == "other":
        text = str(other_text or "").strip()
        if not text:
            raise ProblemGoodsError("客户选择“其他”时必须填写回复内容")
        return text
    if value in CLIENT_DEAL_VALUES:
        return CLIENT_DEAL_VALUES[value]
    if value in CLIENT_DEAL_VALUES.values():
        return value
    raise ProblemGoodsError("客户处理选项无效")


def _api_success(payload: Dict[str, Any]) -> bool:
    return isinstance(payload, dict) and payload.get("success") is True and int(payload.get("code") or 0) == 0


def _payload_message(payload: Dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("msg") or payload.get("message") or "")


def is_department_permission_error(value: Any) -> bool:
    text = _payload_message(value) if isinstance(value, dict) else str(value or "")
    return any(pattern in text for pattern in PERMISSION_ERROR_PATTERNS)


def parse_preview_bills(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    candidates = [payload.get("data"), payload.get("msg")]
    for candidate in candidates:
        parsed = candidate
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except ValueError:
                continue
        if isinstance(parsed, dict):
            parsed = parsed.get("data") or parsed.get("list") or [parsed]
        if isinstance(parsed, list):
            return [dict(item) for item in parsed if isinstance(item, dict)]
    if _api_success(payload):
        return []
    raise ProblemGoodsApiError("金额预览", payload)


def refund_cny_from_preview(bills: Iterable[Dict[str, Any]]) -> Decimal:
    refund = Decimal("0")
    for bill in bills:
        amount = _decimal(bill.get("amount") or 0, "预览账单金额", non_negative=False)
        rate = _decimal(bill.get("exchange_rate") or 0, "预览汇率")
        if amount > 0 and rate > 0:
            refund += amount / rate
    return refund


def _form_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _request_payload(response: requests.Response, action: str) -> Dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        raise ProblemGoodsError(f"{action}返回非JSON响应：HTTP {response.status_code}")
    if not isinstance(payload, dict):
        raise ProblemGoodsError(f"{action}返回结构有误")
    return payload


def _nested_list(payload: Dict[str, Any]) -> list[Any]:
    data: Any = payload.get("data")
    if isinstance(data, dict):
        for key in ("data", "list", "rows", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return data if isinstance(data, list) else []


def flatten_problem_rows(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for batch in _nested_list(payload):
        if not isinstance(batch, dict):
            continue
        groups = batch.get("groupByPurchaseNo") or batch.get("group_by_purchase_no") or []
        if not isinstance(groups, list):
            groups = []
        if not groups and isinstance(batch.get("list"), list):
            groups = [{"list": batch.get("list")}]
        for group in groups:
            if not isinstance(group, dict):
                continue
            for raw in group.get("list") or []:
                if not isinstance(raw, dict):
                    continue
                item = dict(raw)
                item.setdefault("uniqid", batch.get("uniqid"))
                item.setdefault("order_sn", batch.get("order_sn"))
                item.setdefault("purchase_no", group.get("purchase_no"))
                rows.append(item)
    return rows


def _problem_id(row: Dict[str, Any]) -> int:
    return int(row.get("problem_goods_id") or row.get("id") or 0)


def _order_purchase_id(row: Dict[str, Any]) -> int:
    nested = row.get("order_purchase") if isinstance(row.get("order_purchase"), dict) else {}
    return int(row.get("order_purchase_id") or nested.get("id") or 0)


def _first_value(row: Dict[str, Any], *keys: str) -> Any:
    purchase = row.get("order_purchase") if isinstance(row.get("order_purchase"), dict) else {}
    detail = row.get("order_detail") if isinstance(row.get("order_detail"), dict) else {}
    for key in keys:
        if row.get(key) not in (None, ""):
            return row.get(key)
        if purchase.get(key) not in (None, ""):
            return purchase.get(key)
        if detail.get(key) not in (None, ""):
            return detail.get(key)
    return None


def public_problem_row(row: Dict[str, Any]) -> Dict[str, Any]:
    status = _status(row.get("status"))
    return {
        "problem_goods_id": _problem_id(row),
        "order_sn": row.get("order_sn"),
        "order_purchase_id": _order_purchase_id(row),
        "order_detail_id": row.get("order_detail_id"),
        "sorting": _first_value(row, "sorting"),
        "purchase_no": row.get("purchase_no"),
        "type": row.get("type"),
        "type_name": row.get("type_name"),
        "status": status,
        "status_name": row.get("status_name") or STATUS_NAMES.get(status, str(status)),
        "problem_num": row.get("num"),
        "confirm_num": _first_value(row, "confirm_num"),
        "confirm_price": _first_value(row, "confirm_price"),
        "confirm_freight": _first_value(row, "confirm_freight"),
        "possible_num": _first_value(row, "possible_num", "now_num"),
        "storage_num": _first_value(row, "storage_num"),
        "price": _first_value(row, "price", "confirm_price"),
        "freight": _first_value(row, "freight", "confirm_freight"),
        "pre_num": row.get("pre_num"),
        "pre_price": row.get("pre_price"),
        "pre_freight": row.get("pre_freight"),
        "option": row.get("option") or [],
        "option_new": row.get("option_new") or [],
        "service_deal_suggest": row.get("service_deal_suggest"),
        "option_deal_suggest": row.get("option_deal_suggest"),
        "g_deal_type": row.get("g_deal_type"),
    }


def order_purchase_candidates(order_data: Dict[str, Any]) -> list[Dict[str, Any]]:
    nested_data = order_data.get("data")
    if isinstance(nested_data, dict):
        order_data = nested_data

    pairs: list[tuple[Dict[str, Any], Dict[str, Any]]] = []
    for order in _nested_list(order_data):
        if not isinstance(order, dict):
            continue
        purchases = (
            order.get("order_purchase")
            or order.get("order_purchases")
            or order.get("list")
            or order.get("items")
            or []
        )
        if isinstance(purchases, dict):
            purchases = [purchases]
        for raw_purchase in purchases if isinstance(purchases, list) else []:
            if not isinstance(raw_purchase, dict):
                continue
            purchase = dict(raw_purchase)
            purchase.setdefault("purchase_no", order.get("purchase_no"))
            purchase.setdefault("order_sn", order.get("order_sn"))
            detail = purchase.get("order_detail") if isinstance(purchase.get("order_detail"), dict) else {}
            pairs.append((detail, purchase))

    details = order_data.get("order_detail") or order_data.get("order_details") or []
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        purchases = detail.get("order_purchase") or detail.get("order_purchases") or []
        if isinstance(purchases, dict):
            purchases = [purchases]
        for raw_purchase in purchases if isinstance(purchases, list) else []:
            if not isinstance(raw_purchase, dict):
                continue
            purchase = dict(raw_purchase)
            purchase.setdefault("order_detail_id", detail.get("id"))
            pairs.append((detail, purchase))

    candidates: list[Dict[str, Any]] = []
    seen: set[int] = set()
    for detail, purchase in pairs:
        purchase_id = int(purchase.get("id") or purchase.get("order_purchase_id") or 0)
        detail_id = int(detail.get("id") or purchase.get("order_detail_id") or 0)
        if not purchase_id or not detail_id or purchase_id in seen:
            continue
        seen.add(purchase_id)
        possible_num = int(purchase.get("possible_num") or 0)
        storage_num = int(purchase.get("storage_num") or 0)
        max_submit_num = max(0, possible_num - storage_num)
        price = purchase.get("price") if purchase.get("price") not in (None, "") else detail.get("confirm_price")
        freight = purchase.get("freight") if purchase.get("freight") not in (None, "") else detail.get("confirm_freight")
        confirm_num = detail.get("confirm_num") if detail.get("confirm_num") not in (None, "") else purchase.get("confirm_num")
        confirm_price = detail.get("confirm_price") if detail.get("confirm_price") not in (None, "") else purchase.get("confirm_price")
        confirm_freight = detail.get("confirm_freight") if detail.get("confirm_freight") not in (None, "") else purchase.get("confirm_freight")
        price = price if price not in (None, "") else confirm_price
        freight = freight if freight not in (None, "") else confirm_freight
        candidates.append(
            {
                "order_purchase_id": purchase_id,
                "order_detail_id": detail_id,
                "sorting": detail.get("sorting") if detail.get("sorting") not in (None, "") else purchase.get("sorting"),
                "purchase_no": purchase.get("purchase_no"),
                "goods_name": detail.get("goods_name") or detail.get("goods_title") or detail.get("title") or purchase.get("goods_name"),
                "sku_id": detail.get("sku_id") or purchase.get("sku_id"),
                "purchase_status": purchase.get("status"),
                "possible_num": possible_num,
                "storage_num": storage_num,
                "max_submit_num": max_submit_num,
                "can_submit": max_submit_num > 0,
                "price": price,
                "freight": freight,
                "confirm_num": confirm_num,
                "confirm_price": confirm_price,
                "confirm_freight": confirm_freight,
                "pre_num": confirm_num if confirm_num not in (None, "") else possible_num,
                "pre_price": confirm_price if confirm_price not in (None, "") else price,
                "pre_freight": confirm_freight if confirm_freight not in (None, "") else freight,
                "option": detail.get("option") or purchase.get("option") or [],
            }
        )
    return candidates


def merge_purchase_candidates(*groups: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    merged: Dict[int, Dict[str, Any]] = {}
    for group in groups:
        for candidate in group:
            purchase_id = int(candidate.get("order_purchase_id") or 0)
            if not purchase_id:
                continue
            current = merged.get(purchase_id)
            if current is None:
                merged[purchase_id] = dict(candidate)
                continue
            for key, value in candidate.items():
                if current.get(key) in (None, "", []) and value not in (None, "", []):
                    current[key] = value
    return list(merged.values())


def available_option_catalog(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data: Any = payload.get("data")
    if isinstance(data, dict):
        data = data.get("list") or data.get("data") or data.get("items") or []
    if not isinstance(data, list):
        return []
    rows: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        option = dict(item)
        key = str(option.get("id") or option.get("option_id") or option.get("name") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(option)
    return rows


class ProblemGoodsGateway:
    def __init__(self, env: Any, variables: Dict[str, Any], log: Dict[str, Any]):
        self.env = env
        self.variables = variables
        self.log = log
        self.timeout = max(1, int(variables.get("timeout") or getattr(env, "timeout", 25) or 25))
        self.base_url = str(variables.get("backend_base_url") or getattr(env, "base_url", "") or bulk_cart.BASE_URL).rstrip("/")
        self.admin_session = _admin_session_from(variables)
        self._admin_ready = False
        self._client: Any = None

    def _path(self, key: str, default: str) -> str:
        paths = self.variables.get("api_paths") if isinstance(self.variables.get("api_paths"), dict) else {}
        return str(paths.get(key) or default)

    def admin_login(self) -> None:
        if self._admin_ready:
            return
        payload, token = _admin_login(self.admin_session, self.base_url, self.variables, self.timeout)
        self.log["admin_login"] = {
            "success": _api_success(payload) and bool(token),
            "account_profile_id": self.variables.get("backend_account_profile_id"),
            "token_extracted": bool(token),
        }
        if not _api_success(payload) or not token:
            raise ProblemGoodsApiError("后台登录", payload)
        self._admin_ready = True

    def client_login(self) -> Any:
        if self._client is not None:
            return self._client
        runtime = _runtime_from_variables(self.variables)
        if runtime is not None:
            client, _base_url, _timeout, token, _cached = runtime.client(self.env, self.variables, log=None)
        else:
            client = bulk_cart.RakumartClient(self.base_url, self.timeout)
            account = str(self.variables.get("account") or "").strip()
            password = str(self.variables.get("password") or "").strip()
            client_tool = str(self.variables.get("client_tool") or "1")
            token = client.login(account, password, client_tool)
        if not token:
            raise ProblemGoodsError("客户登录失败")
        self.log["client_login"] = {"success": True, "customer_id": self.variables.get("customer_id")}
        self._client = client
        return client

    def _admin_request(self, path: str, fields: Dict[str, Any], action: str, *, mutation: bool) -> Dict[str, Any]:
        self.admin_login()
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        form_data = {str(key): _form_value(value) for key, value in fields.items()}
        attempts = 1 if mutation else 3
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self.admin_session.post(url, data=form_data, timeout=self.timeout)
                return _request_payload(response, action)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(0.5 * (attempt + 1))
        if mutation:
            raise ProblemGoodsMutationUncertain(f"{action}网络结果不确定，必须先查询状态") from last_error
        raise ProblemGoodsError(f"{action}请求失败：{last_error}")

    def _client_request(self, path: str, fields: Dict[str, Any], action: str, *, mutation: bool) -> Dict[str, Any]:
        client = self.client_login()
        client_base_url = str(getattr(client, "base_url", "") or self.base_url).rstrip("/")
        url = path if path.startswith("http") else client_base_url + path
        form_data = {str(key): _form_value(value) for key, value in fields.items()}
        attempts = 1 if mutation else 3
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = client.session.post(url, data=form_data, timeout=self.timeout)
                return _request_payload(response, action)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(0.5 * (attempt + 1))
        if mutation:
            raise ProblemGoodsMutationUncertain(f"{action}网络结果不确定，必须先查询状态") from last_error
        raise ProblemGoodsError(f"{action}请求失败：{last_error}")

    def list_problems(self, order_sn: str, status: Any = 0) -> list[Dict[str, Any]]:
        fields = {
            "status": status,
            "page": 1,
            "pageSize": 100,
            "dateStart": "",
            "dateEnd": "",
            "express_no": "",
            "purchase_no": "",
            "order_sn": order_sn,
            "user_id": "",
            "org_id": 1,
            "admin_id": "",
            "overdue": "",
            "refund_status": "",
        }
        payload = self._admin_request(self._path("problem_list", "/problem.list"), fields, "查询问题产品", mutation=False)
        if not _api_success(payload):
            raise ProblemGoodsApiError("查询问题产品", payload)
        return flatten_problem_rows(payload)

    def list_purchase_candidates(self, order_sn: str) -> list[Dict[str, Any]]:
        source_log: Dict[str, Dict[str, Any]] = {}
        successful_sources = 0

        def query(source: str, path_key: str, default_path: str, fields: Dict[str, Any]) -> list[Dict[str, Any]]:
            nonlocal successful_sources
            try:
                payload = self._admin_request(
                    self._path(path_key, default_path),
                    fields,
                    f"查询问题产品候选（{source}）",
                    mutation=False,
                )
                if not _api_success(payload):
                    raise ProblemGoodsApiError(f"查询问题产品候选（{source}）", payload)
                successful_sources += 1
                rows = order_purchase_candidates(payload)
                source_log[source] = {"success": True, "count": len(rows)}
                return rows
            except ProblemGoodsError as exc:
                source_log[source] = {"success": False, "error": str(exc)}
                return []

        order_detail_rows = query(
            "order_detail",
            "admin_order_detail",
            "/order.detail",
            {"order_sn": order_sn},
        )
        if order_detail_rows:
            self.log["candidate_sources"] = source_log
            return order_detail_rows

        purchase_rows = query(
            "purchase_list",
            "admin_purchase_list",
            "/purchase.purchaseList",
            {
                "page": 1,
                "pageSize": 100,
                "status": "全部",
                "dateStart": "",
                "dateEnd": "",
                "user_id": "",
                "order_sn": order_sn,
                "g_id": "",
                "is_urgent": "",
                "overdue": "",
            },
        )
        follow_rows = query(
            "follow_list",
            "admin_follow_list",
            "/follow.followList",
            {
                "page": 1,
                "pageSize": 100,
                "status": "0",
                "dateStart": "",
                "dateEnd": "",
                "user_id": "",
                "order_sn": order_sn,
                "express_no": "",
                "purchase_no": "",
                "order_part": "",
                "realname": "",
            },
        )
        self.log["candidate_sources"] = source_log
        if not successful_sources:
            raise ProblemGoodsError("候选采购记录查询失败")
        return merge_purchase_candidates(purchase_rows, follow_rows)

    def list_available_options(self) -> list[Dict[str, Any]]:
        payload = self._client_request(
            self._path("client_order_option_list", "/client/order.optionList"),
            {},
            "查询全量OPTION",
            mutation=False,
        )
        if not _api_success(payload):
            raise ProblemGoodsApiError("查询全量OPTION", payload)
        return available_option_catalog(payload)

    def find_problem(self, order_sn: str, problem_goods_id: int = 0, order_purchase_id: int = 0) -> Dict[str, Any] | None:
        rows = self.list_problems(order_sn, 0)
        candidates = [row for row in rows if not problem_goods_id or _problem_id(row) == problem_goods_id]
        if order_purchase_id:
            candidates = [row for row in candidates if _order_purchase_id(row) == order_purchase_id]
        if problem_goods_id and not candidates:
            completed = self.list_problems(order_sn, STATUS_COMPLETED)
            candidates = [row for row in completed if _problem_id(row) == problem_goods_id]
        if not candidates:
            return None
        if problem_goods_id or order_purchase_id:
            return max(candidates, key=_problem_id)
        active = [row for row in candidates if STATUS_TRANSLATE_PENDING <= _status(row.get("status")) < STATUS_COMPLETED]
        if len(active) == 1:
            return active[0]
        if len(active) > 1:
            raise ProblemGoodsError("订单存在多个处理中问题产品，请选择具体问题产品")
        completed = [row for row in candidates if _status(row.get("status")) == STATUS_COMPLETED]
        if len(completed) == 1:
            return completed[0]
        return None

    def wait_for_status(self, order_sn: str, problem_goods_id: int, minimum_status: int, *, attempts: int = 6) -> Dict[str, Any] | None:
        for attempt in range(attempts):
            row = self.find_problem(order_sn, problem_goods_id)
            if row is not None and _status(row.get("status")) >= minimum_status:
                return row
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
        return self.find_problem(order_sn, problem_goods_id)

    def create_problem(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._admin_request(self._path("problem_store", "/problem.store"), fields, "提出问题产品", mutation=True)
        if not _api_success(payload):
            raise ProblemGoodsApiError("提出问题产品", payload)
        return payload

    def translate(self, problem_goods_id: int, content: str) -> Dict[str, Any]:
        payload = self._admin_request(
            self._path("problem_translate", "/problem.translate"),
            {"data[0][problem_goods_id]": problem_goods_id, "data[0][content]": content},
            "业务翻译",
            mutation=True,
        )
        if not _api_success(payload):
            raise ProblemGoodsApiError("业务翻译", payload)
        return payload

    def client_reply(self, problem_goods_id: int, content: str) -> Dict[str, Any]:
        payload = self._client_request(
            self._path("client_question_over", "/client/question.over"),
            {"problem_goods_id": problem_goods_id, "client_deal": content},
            "客户处理",
            mutation=True,
        )
        if not _api_success(payload):
            raise ProblemGoodsApiError("客户处理", payload)
        return payload

    def update_pre_data(self, problem_goods_id: int, pre_num: int, pre_price: str, pre_freight: str) -> Dict[str, Any]:
        payload = self._admin_request(
            self._path("problem_update_pre_data", "/problem.updatePreData"),
            {
                "problem_goods_id": problem_goods_id,
                "pre_num": pre_num,
                "pre_price": pre_price,
                "pre_freight": pre_freight,
            },
            "修改问题产品数据",
            mutation=True,
        )
        if not _api_success(payload):
            raise ProblemGoodsApiError("修改问题产品数据", payload)
        return payload

    def update_options(self, problem_goods_id: int, options: list[Dict[str, Any]]) -> Dict[str, Any]:
        payload = self._admin_request(
            self._path("problem_update_option", "/problem.updateOption"),
            {
                "data[0][problem_goods_id]": problem_goods_id,
                "data[0][option_new]": json.dumps(options, ensure_ascii=False, separators=(",", ":")),
            },
            "修改问题产品OPTION",
            mutation=True,
        )
        if not _api_success(payload):
            raise ProblemGoodsApiError("修改问题产品OPTION", payload)
        return payload

    def business_deal(self, fields: Dict[str, Any], *, preview: bool) -> Dict[str, Any]:
        request_fields = dict(fields)
        request_fields["preview_bill"] = 1 if preview else 0
        payload = self._admin_request(self._path("problem_y_deal", "/problem.y_deal"), request_fields, "业务决策预览" if preview else "业务决策", mutation=True)
        if preview:
            parse_preview_bills(payload)
        elif not _api_success(payload):
            raise ProblemGoodsApiError("业务决策", payload)
        return payload

    def purchase_deal(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._admin_request(self._path("problem_g_deal", "/problem.g_deal"), fields, "采购处理", mutation=True)
        if not _api_success(payload):
            raise ProblemGoodsApiError("采购处理", payload)
        return payload

    def distribution_deal(self, problem_goods_id: int) -> Dict[str, Any]:
        payload = self._admin_request(
            self._path("problem_p_deal", "/problem.p_deal"),
            {"data[0][problem_goods_id]": problem_goods_id},
            "配货确认",
            mutation=True,
        )
        if not _api_success(payload):
            raise ProblemGoodsApiError("配货确认", payload)
        return payload

    def balance_changes(self, order_sn: str) -> list[Dict[str, Any]]:
        payload = self._client_request(
            self._path("client_balance_change", "/client/user.balanceChange"),
            {
                "start_time": "",
                "end_time": "",
                "keywords": order_sn,
                "bill_type": "",
                "bill_method": "",
                "order_by": "desc",
                "page": 1,
                "pageSize": 20,
            },
            "查询客户账单",
            mutation=False,
        )
        if not _api_success(payload):
            raise ProblemGoodsApiError("查询客户账单", payload)
        return [dict(item) for item in _nested_list(payload) if isinstance(item, dict)]

    def order_detail(self, order_sn: str) -> Dict[str, Any]:
        payload = self._admin_request(
            self._path("admin_order_detail", "/order.detail"),
            {"order_sn": order_sn},
            "查询订单详情",
            mutation=False,
        )
        if not _api_success(payload):
            raise ProblemGoodsApiError("查询订单详情", payload)
        return payload.get("data") if isinstance(payload.get("data"), dict) else {}


def _business_fields(problem_goods_id: int, variables: Dict[str, Any], *, preview: bool) -> Dict[str, Any]:
    return {
        "data[0][problem_goods_id]": problem_goods_id,
        "data[0][content]": str(variables.get("business_decision") or "").strip(),
        "data[0][service_deal_suggest]": int(variables["service_deal_suggest"]),
        "data[0][option_deal_suggest]": int(variables["option_deal_suggest"]),
        "data[0][type]": int(variables["problem_type"]),
        "data[0][is_purchase_add]": 1 if _bool_value(variables.get("is_purchase_add"), False) else 0,
        "data[0][purchase_add_reparation_sn]": str(variables.get("purchase_add_reparation_sn") or ""),
        "jump_g": 1 if preview else 0,
        "jump_p": 0,
    }


def _purchase_fields(problem_goods_id: int, variables: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "data[0][problem_goods_id]": problem_goods_id,
        "data[0][pre_num]": variables["pre_num"],
        "data[0][pre_price]": variables["pre_price"],
        "data[0][pre_freight]": variables["pre_freight"],
        "data[0][content]": str(variables.get("purchase_remark") or "").strip(),
        "data[0][g_deal_type]": str(variables.get("g_deal_type") or "").strip(),
    }


def _create_fields(variables: Dict[str, Any]) -> Dict[str, Any]:
    prefix = "data[0]"
    fields: Dict[str, Any] = {
        f"{prefix}[order_detail_id]": int(variables["order_detail_id"]),
        f"{prefix}[order_purchase_id]": int(variables["order_purchase_id"]),
        f"{prefix}[description]": str(variables.get("problem_description") or "").strip(),
        f"{prefix}[num]": int(variables["problem_num"]),
        f"{prefix}[inspect_bad_id]": str(variables.get("inspect_bad_id") or ""),
        f"{prefix}[type]": int(variables["problem_type"]),
        f"{prefix}[pre_num]": variables["pre_num"],
        f"{prefix}[pre_price]": variables["pre_price"],
        f"{prefix}[pre_freight]": variables["pre_freight"],
    }
    images = variables.get("problem_images") or []
    if isinstance(images, str):
        images = [item.strip() for item in re.split(r"[\n,，;；]+", images) if item.strip()]
    for index, item in enumerate(images if isinstance(images, list) else []):
        image = item if isinstance(item, str) else item.get("image")
        client_show = 0 if isinstance(item, str) else (1 if _bool_value(item.get("client_show"), False) else 0)
        if image:
            fields[f"{prefix}[image][{index}][image]"] = image
            fields[f"{prefix}[image][{index}][client_show]"] = client_show
    return fields


def normalize_flow_variables(variables: Dict[str, Any], row: Dict[str, Any] | None = None) -> Dict[str, Any]:
    values = dict(variables or {})
    order_sn = str(values.get("order_sn") or "").strip()
    if not order_sn:
        raise ProblemGoodsError("订单号不能为空")
    values["order_sn"] = order_sn
    values["customer_id"] = normalize_customer_id(order_sn, values.get("customer_id"))

    row = row or {}
    current_status = _status(row.get("status")) if row else 0
    for key in ("pre_num", "pre_price", "pre_freight", "service_deal_suggest", "option_deal_suggest"):
        if values.get(key) in (None, "") and row.get(key) not in (None, ""):
            values[key] = row.get(key)
    if values.get("problem_type") in (None, "") and row.get("type") not in (None, ""):
        values["problem_type"] = row.get("type")

    if current_status <= STATUS_PURCHASE_PENDING:
        values["pre_num"] = _integer(values.get("pre_num"), "修改后数量")
        values["pre_price"] = _decimal_text(values.get("pre_price"), "修改后单价")
        values["pre_freight"] = _decimal_text(values.get("pre_freight"), "修改后运费")

        problem_type = _integer(values.get("problem_type"), "问题类型", positive=True)
        if problem_type not in PROBLEM_TYPES:
            raise ProblemGoodsError("问题类型无效")
        values["problem_type"] = problem_type

        purchase_type = str(values.get("g_deal_type") or "").strip()
        if purchase_type not in PURCHASE_DEAL_TYPES:
            raise ProblemGoodsError("采购处理类型无效")
        if not str(values.get("purchase_remark") or "").strip():
            raise ProblemGoodsError("采购处理备注不能为空")
        values["g_deal_type"] = purchase_type

    if current_status <= STATUS_BUSINESS_PENDING:
        service_type = _integer(values.get("service_deal_suggest"), "手续费处理类型", positive=True)
        if service_type not in SERVICE_DEAL_TYPES:
            raise ProblemGoodsError("手续费处理类型无效")
        values["service_deal_suggest"] = service_type

        option_type = _integer(values.get("option_deal_suggest"), "附加服务费处理类型", positive=True)
        if option_type not in OPTION_DEAL_TYPES:
            raise ProblemGoodsError("附加服务费处理类型无效")
        values["option_deal_suggest"] = option_type

        if not str(values.get("business_decision") or "").strip():
            raise ProblemGoodsError("业务决策不能为空")

    if current_status <= STATUS_CLIENT_PENDING:
        values["client_deal_text"] = client_deal_text(values.get("client_deal_choice"), values.get("client_deal_other"))
    return values


def pre_data_needs_update(row: Dict[str, Any], variables: Dict[str, Any]) -> bool:
    """避免后台把“值未变更”返回为修改失败。"""
    for key, label in (("pre_num", "修改后数量"), ("pre_price", "修改后单价"), ("pre_freight", "修改后运费")):
        current = row.get(key)
        if current in (None, ""):
            return True
        try:
            if _decimal(current, label) != _decimal(variables[key], label):
                return True
        except ProblemGoodsError:
            return True
    return False


class ProblemGoodsFlow:
    def __init__(self, gateway: Any, variables: Dict[str, Any], log: Dict[str, Any]):
        self.gateway = gateway
        self.variables = dict(variables or {})
        self.log = log

    def _record_step(self, name: str, **extra: Any) -> None:
        self.log.setdefault("steps", []).append({"name": name, **extra})

    def _permission_summary(self, row: Dict[str, Any], bills: list[Dict[str, Any]], reason: str) -> Dict[str, Any]:
        return {
            "order_sn": self.variables["order_sn"],
            "customer_id": self.variables["customer_id"],
            "problem_goods_id": _problem_id(row),
            "status": _status(row.get("status")),
            "status_name": STATUS_NAMES.get(_status(row.get("status"))),
            "paused": True,
            "resumable": True,
            "permission_required": True,
            "required_account_role": "department_leader",
            "resume_stage": "purchase_deal" if _status(row.get("status")) >= STATUS_PURCHASE_PENDING else "business_deal",
            "reason": reason,
            "preview_bills": bills,
        }

    def _create_or_select(self) -> Dict[str, Any]:
        order_sn = self.variables["order_sn"]
        requested_id = int(self.variables.get("problem_goods_id") or 0)
        purchase_id = int(self.variables.get("order_purchase_id") or 0)
        row = self.gateway.find_problem(order_sn, requested_id, purchase_id)
        if row is not None and not requested_id and _bool_value(self.variables.get("create_if_missing"), False):
            if _status(row.get("status")) in {STATUS_CANCELLED, STATUS_COMPLETED}:
                row = None
        if row is not None:
            return row
        if not _bool_value(self.variables.get("create_if_missing"), False):
            raise ProblemGoodsError("没有找到符合条件的问题产品")
        self.variables = normalize_flow_variables(self.variables)
        for key, label in (("order_purchase_id", "采购记录"), ("order_detail_id", "订单详情"), ("problem_num", "问题产品数量")):
            if self.variables.get(key) in (None, ""):
                raise ProblemGoodsError(f"创建问题产品时{label}不能为空")
        self.variables["order_purchase_id"] = _integer(self.variables["order_purchase_id"], "采购记录ID", positive=True)
        self.variables["order_detail_id"] = _integer(self.variables["order_detail_id"], "订单详情ID", positive=True)
        self.variables["problem_num"] = _integer(self.variables["problem_num"], "问题产品数量", positive=True)
        if not str(self.variables.get("problem_description") or "").strip():
            raise ProblemGoodsError("创建问题产品时问题描述不能为空")
        create_error: Exception | None = None
        try:
            self.gateway.create_problem(_create_fields(self.variables))
        except (ProblemGoodsApiError, ProblemGoodsMutationUncertain) as exc:
            create_error = exc
        row = None
        for attempt in range(6):
            row = self.gateway.find_problem(order_sn, 0, self.variables["order_purchase_id"])
            if row is not None and _status(row.get("status")) == STATUS_TRANSLATE_PENDING:
                break
            if attempt < 5:
                time.sleep(0.5 * (attempt + 1))
        if row is None:
            if create_error is not None:
                raise create_error
            raise ProblemGoodsError("提出问题产品后未查询到新记录，已停止以避免重复提出")
        self._record_step("problem_created", problem_goods_id=_problem_id(row))
        return row

    def run(self) -> Dict[str, Any]:
        order_sn = str(self.variables.get("order_sn") or "").strip()
        self.variables["order_sn"] = order_sn
        self.variables["customer_id"] = normalize_customer_id(order_sn, self.variables.get("customer_id"))
        row = self._create_or_select()
        problem_goods_id = _problem_id(row)
        if not problem_goods_id:
            raise ProblemGoodsError("问题产品ID缺失")

        if _status(row.get("status")) == STATUS_CANCELLED:
            raise ProblemGoodsError("问题产品已取消，不能继续处理")
        if _status(row.get("status")) == STATUS_COMPLETED:
            return {
                "order_sn": order_sn,
                "customer_id": self.variables["customer_id"],
                "problem_goods_id": problem_goods_id,
                "status": STATUS_COMPLETED,
                "status_name": STATUS_NAMES[STATUS_COMPLETED],
                "already_completed": True,
            }
        self.variables = normalize_flow_variables(self.variables, row)
        if hasattr(self.gateway, "variables") and isinstance(self.gateway.variables, dict):
            self.gateway.variables.update(self.variables)

        if _status(row.get("status")) == STATUS_TRANSLATE_PENDING:
            content = str(self.variables.get("translation_content") or "").strip()
            if not content:
                raise ProblemGoodsError("待翻译状态必须填写客户译文")
            try:
                self.gateway.translate(problem_goods_id, content)
            except (ProblemGoodsApiError, ProblemGoodsMutationUncertain) as exc:
                refreshed = self.gateway.find_problem(order_sn, problem_goods_id)
                if refreshed is None or _status(refreshed.get("status")) < STATUS_CLIENT_PENDING:
                    raise ProblemGoodsError(f"业务翻译失败且未完成：{exc}")
            row = self.gateway.wait_for_status(order_sn, problem_goods_id, STATUS_CLIENT_PENDING)
            if row is None or _status(row.get("status")) < STATUS_CLIENT_PENDING:
                raise ProblemGoodsError("翻译提交结果无法确认，已停止以避免重复提交")
            self._record_step("translated", status=_status(row.get("status")))

        if _status(row.get("status")) == STATUS_CLIENT_PENDING:
            try:
                self.gateway.client_reply(problem_goods_id, self.variables["client_deal_text"])
            except (ProblemGoodsApiError, ProblemGoodsMutationUncertain) as exc:
                refreshed = self.gateway.find_problem(order_sn, problem_goods_id)
                if refreshed is None or _status(refreshed.get("status")) < STATUS_BUSINESS_PENDING:
                    raise ProblemGoodsError(f"客户处理失败且未完成：{exc}")
            row = self.gateway.wait_for_status(order_sn, problem_goods_id, STATUS_BUSINESS_PENDING)
            if row is None or _status(row.get("status")) < STATUS_BUSINESS_PENDING:
                raise ProblemGoodsError("客户处理结果无法确认，已停止以避免重复提交")
            self._record_step("client_replied", status=_status(row.get("status")))

        preview_bills: list[Dict[str, Any]] = []
        if _status(row.get("status")) == STATUS_BUSINESS_PENDING:
            original_options = row.get("option") or []
            if self.variables["option_deal_suggest"] == 1:
                if "option_new" not in self.variables:
                    raise ProblemGoodsError("按照业务修改值计算时必须明确提交修改后OPTION")
                options = validate_manual_options(self.variables.get("option_new"), original_options)
            else:
                validate_auto_option_eligibility(
                    original_options,
                    _first_value(row, "possible_num", "now_num"),
                    self.variables["pre_num"],
                )
                options = []

            if pre_data_needs_update(row, self.variables):
                self.gateway.update_pre_data(
                    problem_goods_id,
                    self.variables["pre_num"],
                    self.variables["pre_price"],
                    self.variables["pre_freight"],
                )
                self._record_step("pre_data_updated")
            else:
                self._record_step("pre_data_unchanged")
            if self.variables["option_deal_suggest"] == 1:
                self.gateway.update_options(problem_goods_id, options)
                self._record_step("options_updated", option_count=len(options))

            preview_payload = self.gateway.business_deal(_business_fields(problem_goods_id, self.variables, preview=True), preview=True)
            preview_bills = parse_preview_bills(preview_payload)
            refund_cny = refund_cny_from_preview(preview_bills)
            self._record_step("bill_previewed", refund_cny=str(refund_cny), bill_count=len(preview_bills))
            if refund_cny >= Decimal("500") and not _bool_value(self.variables.get("allow_large_refund"), False):
                return self._permission_summary(row, preview_bills, "预计退款达到500元，请切换部长后台账号后继续")

            try:
                self.gateway.business_deal(_business_fields(problem_goods_id, self.variables, preview=False), preview=False)
            except (ProblemGoodsApiError, ProblemGoodsMutationUncertain) as exc:
                refreshed = self.gateway.find_problem(order_sn, problem_goods_id)
                if refreshed is None or _status(refreshed.get("status")) < STATUS_PURCHASE_PENDING:
                    raise ProblemGoodsError(f"业务决策失败且未完成：{exc}")
            row = self.gateway.wait_for_status(order_sn, problem_goods_id, STATUS_PURCHASE_PENDING)
            if row is None or _status(row.get("status")) < STATUS_PURCHASE_PENDING:
                raise ProblemGoodsError("业务决策结果无法确认，已停止以避免重复提交")
            self._record_step("business_dealt", status=_status(row.get("status")))

        if _status(row.get("status")) == STATUS_PURCHASE_PENDING:
            before_bills = self.gateway.balance_changes(order_sn)
            try:
                self.gateway.purchase_deal(_purchase_fields(problem_goods_id, self.variables))
            except (ProblemGoodsApiError, ProblemGoodsMutationUncertain) as exc:
                refreshed = self.gateway.find_problem(order_sn, problem_goods_id)
                if refreshed is not None and _status(refreshed.get("status")) >= STATUS_DISTRIBUTION_PENDING:
                    row = refreshed
                elif is_department_permission_error(exc.payload if isinstance(exc, ProblemGoodsApiError) else str(exc)):
                    return self._permission_summary(refreshed or row, preview_bills, "后台要求部长账号，请切换后从采购处理继续")
                else:
                    raise ProblemGoodsError(f"采购处理失败且未完成：{exc}")
            else:
                row = self.gateway.wait_for_status(order_sn, problem_goods_id, STATUS_DISTRIBUTION_PENDING)
            if row is None or _status(row.get("status")) < STATUS_DISTRIBUTION_PENDING:
                raise ProblemGoodsError("采购处理结果无法确认，禁止重复提交")
            try:
                after_bills = self.gateway.balance_changes(order_sn)
            except ProblemGoodsError as exc:
                after_bills = before_bills
                self.log.setdefault("warnings", []).append(f"采购已完成，但客户账单复核失败：{exc}")
            self._record_step(
                "purchase_dealt",
                status=_status(row.get("status")),
                new_bill_count=max(0, len(after_bills) - len(before_bills)),
            )

        if _status(row.get("status")) == STATUS_DISTRIBUTION_PENDING and _bool_value(self.variables.get("confirm_distribution"), True):
            try:
                self.gateway.distribution_deal(problem_goods_id)
            except (ProblemGoodsApiError, ProblemGoodsMutationUncertain):
                refreshed = self.gateway.find_problem(order_sn, problem_goods_id)
                if refreshed is None or _status(refreshed.get("status")) < STATUS_COMPLETED:
                    raise ProblemGoodsError("配货确认失败；采购结算可能已完成，请勿重新执行采购处理")
                row = refreshed
            else:
                row = self.gateway.wait_for_status(order_sn, problem_goods_id, STATUS_COMPLETED)
            if row is None or _status(row.get("status")) < STATUS_COMPLETED:
                raise ProblemGoodsError("配货确认结果无法确认，请按问题产品ID查询已完成状态")
            self._record_step("distribution_confirmed", status=_status(row.get("status")))

        final_status = _status(row.get("status"))
        order_detail: Dict[str, Any] = {}
        if final_status >= STATUS_DISTRIBUTION_PENDING:
            try:
                order_detail = self.gateway.order_detail(order_sn)
            except ProblemGoodsError as exc:
                self.log.setdefault("warnings", []).append(f"流程已完成，但订单详情复核失败：{exc}")
        return {
            "order_sn": order_sn,
            "customer_id": self.variables["customer_id"],
            "problem_goods_id": problem_goods_id,
            "status": final_status,
            "status_name": STATUS_NAMES.get(final_status, str(final_status)),
            "preview_bills": preview_bills,
            "order_detail": order_detail,
            "completed": final_status == STATUS_COMPLETED,
        }


def inspect_problem_goods(env: Any, variables: Dict[str, Any] | None = None) -> Dict[str, Any]:
    values = dict(variables or {})
    order_sn = str(values.get("order_sn") or "").strip()
    if not order_sn:
        raise ProblemGoodsError("订单号不能为空")
    values["order_sn"] = order_sn
    values["customer_id"] = normalize_customer_id(order_sn, values.get("customer_id"))
    log: Dict[str, Any] = {"script": PROBLEM_GOODS_SCRIPT_NAME, "mode": "inspect", "started_at": datetime.now()}
    gateway = ProblemGoodsGateway(env, values, log)
    rows = gateway.list_problems(order_sn, 0)
    completed = gateway.list_problems(order_sn, STATUS_COMPLETED)
    order_candidates = gateway.list_purchase_candidates(order_sn)
    merged: Dict[int, Dict[str, Any]] = {}
    for row in [*rows, *completed]:
        if _problem_id(row):
            merged[_problem_id(row)] = row
    return {
        "order_sn": order_sn,
        "customer_id": values["customer_id"],
        "items": [public_problem_row(row) for row in merged.values()],
        "order_candidates": order_candidates,
        "problem_types": [{"value": key, "label": value} for key, value in PROBLEM_TYPES.items()],
        "status_map": [{"value": key, "label": value} for key, value in STATUS_NAMES.items()],
    }


def fetch_problem_goods_options(env: Any, variables: Dict[str, Any] | None = None) -> Dict[str, Any]:
    values = dict(variables or {})
    order_sn = str(values.get("order_sn") or "").strip()
    if not order_sn:
        raise ProblemGoodsError("订单号不能为空")
    values["order_sn"] = order_sn
    values["customer_id"] = normalize_customer_id(order_sn, values.get("customer_id"))
    log: Dict[str, Any] = {"script": PROBLEM_GOODS_SCRIPT_NAME, "mode": "option_catalog", "started_at": datetime.now()}
    options = ProblemGoodsGateway(env, values, log).list_available_options()
    return {
        "order_sn": order_sn,
        "customer_id": values["customer_id"],
        "options": options,
    }


def run_problem_goods_script(
    env: Any,
    variables: Dict[str, Any] | None = None,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    values = dict(variables or {})
    log: Dict[str, Any] = {
        "script": PROBLEM_GOODS_SCRIPT_NAME,
        "mode": "problem_goods_full_flow",
        "started_at": datetime.now(),
        "steps": [],
    }
    try:
        gateway = ProblemGoodsGateway(env, values, log)
        summary = ProblemGoodsFlow(gateway, values, log).run()
        passed = bool(summary.get("completed") or summary.get("already_completed") or summary.get("paused"))
        return _finish_named(PROBLEM_GOODS_SCRIPT_NAME, log, passed, summary)
    except Exception as exc:
        summary = {
            "order_sn": str(values.get("order_sn") or ""),
            "problem_goods_id": values.get("problem_goods_id"),
            "completed": False,
            "reason": str(exc),
        }
        log["error"] = str(exc)
        return _finish_named(PROBLEM_GOODS_SCRIPT_NAME, log, False, summary)


__all__ = [
    "CLIENT_DEAL_VALUES",
    "OPTION_DEAL_TYPES",
    "PROBLEM_GOODS_SCRIPT_NAME",
    "PROBLEM_TYPES",
    "PURCHASE_DEAL_TYPES",
    "SERVICE_DEAL_TYPES",
    "STATUS_NAMES",
    "ProblemGoodsError",
    "ProblemGoodsFlow",
    "ProblemGoodsGateway",
    "available_option_catalog",
    "client_deal_text",
    "customer_id_from_order_sn",
    "flatten_problem_rows",
    "fetch_problem_goods_options",
    "inspect_problem_goods",
    "is_department_permission_error",
    "normalize_customer_id",
    "order_purchase_candidates",
    "parse_preview_bills",
    "refund_cny_from_preview",
    "run_problem_goods_script",
    "validate_auto_option_eligibility",
    "validate_manual_options",
]
