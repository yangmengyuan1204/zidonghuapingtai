from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    'OrderedDict',
    '_address_fields',
    '_api_path',
    '_api_paths',
    '_api_success',
    '_apply_extra_fields',
    '_as_bool',
    '_as_int',
    '_as_list',
    '_box_need_num',
    '_default_importer_address',
    '_default_receiver_address',
    '_extract_stock_item',
    '_field_value',
    '_first_deep_value',
    '_freight_box_brief',
    '_merge_address',
    '_nested_rows',
    '_payload_brief',
    '_porder_create_fields_for_items',
    '_porder_detail_id',
    '_porder_detail_rows',
    '_porder_wait_box_num',
    '_post_admin_form',
    '_select_warehouse_items',
    '_stock_item_from_row',
    '_unique_list',
    '_walk_dicts',
    '_warehouse_item_id',
    '_warehouse_requested_order_detail_ids',
    '_warehouse_row_matches_current_order',
    '_warehouse_row_order_sn',
    '_warehouse_sendable_num',
    '_warehouse_sku_id',
    'datetime',
    'random',
    'time',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _compat_wrapper(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        _sync_compat_globals()
        return func(*args, **kwargs)

    return wrapped


def _impl__porder_sn(variables: Dict[str, Any]) -> str:
    configured = str(variables.get("porder_sn") or "").strip()
    if configured:
        return configured
    suffix = str(variables.get("porder_suffix") or variables.get("operation_id") or "300001").strip() or "300001"
    return f"P{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(0, 99):02d}-{suffix}"


def _impl__warehouse_list_fields(variables: Dict[str, Any]) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    for key in ["children_id", "for_sn_set", "tag_set", "client_remark", "sort_type", "hasLabel"]:
        value = variables.get(key)
        if value not in (None, ""):
            fields[key] = value
    keywords = str(variables.get("warehouse_keywords") or "").strip()
    tag = str(variables.get("warehouse_search_tag") or "").strip()
    if keywords:
        if tag in {"\u7ba1\u7406\u756a\u53f7", "for_sn", "for_sn_set"}:
            fields["for_sn_set"] = keywords
        elif tag in {"\u30e9\u30d9\u30eb\u60c5\u5831", "tag", "tag_set"}:
            fields["tag_set"] = keywords
        elif tag in {"\u5099\u8003\u6b04", "client_remark"}:
            fields["client_remark"] = keywords
    _apply_extra_fields(fields, variables.get("warehouse_list_fields"))
    return fields


def _impl__warehouse_candidate_paths(variables: Dict[str, Any]) -> list[str]:
    configured = variables.get("client_warehouse_list") or variables.get("warehouse_list_path")
    paths = []
    if configured:
        paths.append(str(configured))
    api_path = _api_paths(variables).get("client_warehouse_list")
    if api_path:
        paths.append(str(api_path))
    paths.extend(
        [
            "/client/wms.stockAutoList",
            "/client/warehouse.warehouseList",
            "/client/warehouse.goodsList",
            "/client/warehouse.goodsWarehouseList",
            "/client/warehouse.orderDetailList",
            "/client/porder.warehouseList",
            "/client/porder.porderWarehouseList",
            "/client/porder.porderDetailList",
            "/client/order.warehouseList",
        ]
    )
    result = []
    for path in paths:
        if path and path not in result:
            result.append(path)
    return result


def _impl__nested_rows(value: Any, depth: int = 0) -> list[Dict[str, Any]]:
    if depth > 5:
        return []
    rows: list[Dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            rows.extend(_nested_rows(item, depth + 1))
        return rows
    if not isinstance(value, dict):
        return rows
    if any(key in value for key in ["order_detail_id", "order_detailId", "detail_id", "porder_detail_id", "id"]):
        rows.append(value)
    for key in ["data", "list", "rows", "result", "items", "order_detail", "orderDetail", "detail", "details", "goods", "goods_list"]:
        child = value.get(key)
        if isinstance(child, (dict, list)):
            rows.extend(_nested_rows(child, depth + 1))
    return rows


def _impl__field_value(row: Dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _impl__warehouse_item_id(row: Dict[str, Any]) -> str:
    return str(_field_value(row, ["order_detail_id", "order_detailId", "detail_id", "porder_detail_id", "id"]) or "").strip()


def _impl__warehouse_sku_id(row: Dict[str, Any]) -> str:
    return str(
        _field_value(
            row,
            [
                "sku_id",
                "skuId",
                "skuID",
                "spec_id",
                "specId",
                "specID",
                "goods_id",
                "goodsId",
                "goodsID",
            ],
        )
        or _warehouse_item_id(row)
        or ""
    ).strip()


def _impl__warehouse_sendable_num(row: Dict[str, Any]) -> int:
    value = _field_value(
        row,
        [
            "send_num",
            "send_await_num",
            "can_send_num",
            "canSendNum",
            "sendable_num",
            "surplus_num",
            "surplus",
            "stock_num",
            "stock",
            "num",
            "available_num",
            "in_stock_num",
        ],
    )
    return _as_int(value, 0)


def _impl__warehouse_item_brief(row: Dict[str, Any], send_num: int | None = None) -> Dict[str, Any]:
    brief = {
        "order_detail_id": _warehouse_item_id(row),
        "sku_id": _warehouse_sku_id(row),
        "goods_id": _field_value(row, ["goods_id", "goodsId", "goodsID"]),
        "goods_title": _field_value(row, ["goods_title", "goodsTitle", "title", "name"]),
        "sendable_num": _warehouse_sendable_num(row),
    }
    order_sn = _field_value(row, ["order_sn", "orderSn", "orderSN"])
    if order_sn not in (None, ""):
        brief["order_sn"] = order_sn
    if row.get("_warehouse_source"):
        brief["source"] = row.get("_warehouse_source")
    if send_num is not None:
        brief["send_num"] = send_num
    return brief


def _impl__warehouse_requested_order_detail_ids(variables: Dict[str, Any]) -> list[str]:
    ids = _as_list(variables.get("order_detail_ids"), [])
    for key in ["order_detail_id", "porder_detail_id"]:
        value = variables.get(key)
        if value not in (None, ""):
            ids.append(str(value).strip())
    return _unique_list(ids)


def _impl__warehouse_row_order_sn(row: Dict[str, Any]) -> str:
    direct = _field_value(row, ["order_sn", "orderSn", "orderSN"])
    if direct not in (None, ""):
        return str(direct).strip()
    return str(_first_deep_value(row, ["order_sn", "orderSn", "orderSN"]) or "").strip()


def _impl__warehouse_row_matches_current_order(row: Dict[str, Any], order_sn: str, order_detail_ids: set[str]) -> bool:
    item_id = _warehouse_item_id(row)
    if order_detail_ids and item_id in order_detail_ids:
        return True
    return bool(order_sn and _warehouse_row_order_sn(row) == order_sn)


def _impl__select_warehouse_items(rows: list[Dict[str, Any]], variables: Dict[str, Any], limit: int = 1) -> list[Dict[str, Any]]:
    requested_id = str(variables.get("order_detail_id") or variables.get("porder_detail_id") or "").strip()
    requested_ids = _warehouse_requested_order_detail_ids(variables)
    requested_id_set = set(requested_ids)
    order_sn = str(variables.get("warehouse_order_sn") or variables.get("order_sn") or "").strip()
    fill_scope = str(variables.get("warehouse_fill_scope") or "").strip().lower()
    require_full_count = _as_bool(variables.get("require_warehouse_sku_count"), False)
    current_first = fill_scope in {"current_order", "current_order_then_history"} or bool(requested_id_set and limit > 1) or bool(order_sn)
    allow_history = fill_scope != "current_order"
    target_count = max(1, limit)
    selected: list[Dict[str, Any]] = []
    seen_skus: set[str] = set()
    seen_item_ids: set[str] = set()

    def add(row: Dict[str, Any], *, force: bool = False, source: str = "history") -> bool:
        item_id = _warehouse_item_id(row)
        if not item_id:
            return False
        if not force and _warehouse_sendable_num(row) <= 0:
            return False
        if item_id in seen_item_ids:
            return False
        sku_id = _warehouse_sku_id(row) or item_id
        if sku_id in seen_skus:
            return False
        selected_row = dict(row)
        selected_row["_warehouse_source"] = source
        selected.append(selected_row)
        seen_skus.add(sku_id)
        seen_item_ids.add(item_id)
        return len(selected) >= target_count

    if current_first:
        for row in rows:
            if _warehouse_row_matches_current_order(row, order_sn, requested_id_set) and add(row, source="current_order"):
                return selected
        if len(selected) >= target_count or not allow_history:
            return selected

    if requested_id:
        for row in rows:
            if _warehouse_item_id(row) == requested_id:
                add(row, force=not require_full_count, source="current_order")
                break
        if not selected and not require_full_count:
            add({"order_detail_id": requested_id, "send_num": _as_int(variables.get("send_num"), 1)}, force=True, source="current_order")
        if len(selected) >= target_count:
            return selected

    if not allow_history:
        return selected
    for row in rows:
        if add(row, source="history"):
            break
    return selected


def _impl__select_warehouse_item(rows: list[Dict[str, Any]], variables: Dict[str, Any]) -> Dict[str, Any] | None:
    selected = _select_warehouse_items(rows, variables, 1)
    return selected[0] if selected else None


def _impl__address_fields(prefix: str, values: Dict[str, Any]) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    for key in [
        "name",
        "company",
        "address",
        "zip",
        "mobile",
        "tel",
        "name_rome",
        "address_rome",
        "corporate_name",
        "account",
        "standard_code",
        "title",
    ]:
        fields[f"{prefix}[{key}]"] = values.get(key, "")
    return fields


def _impl__default_receiver_address() -> Dict[str, Any]:
    return {
        "name": "\u6d4b\u8bd5",
        "company": "\u6d4b\u8bd5\u516c\u53f8\u540d",
        "address": "\u4f4f\u6240",
        "zip": "12345678",
        "mobile": "1353214567",
        "tel": "0321-55786",
        "name_rome": "\u30ed\u30fc\u30de\u5b57(\u6c0f\u540d)",
        "address_rome": "\u30ed\u30fc\u30de\u5b57(\u4f4f\u6240)",
        "corporate_name": "1234567891234",
        "account": "1234567889789",
        "standard_code": "1234567891235",
        "title": "\u9648\u54e5\u6700\u7231\u5199bug",
    }


def _impl__default_importer_address() -> Dict[str, Any]:
    return {
        "name": "13123",
        "company": "",
        "address": "123123",
        "zip": "1232132",
        "mobile": "123123",
        "tel": "",
        "name_rome": "12312313",
        "address_rome": "123123123",
        "corporate_name": "",
        "account": "\u30ea\u30a2\u30eb\u30bf\u30a4\u30e0\u53e3\u5ea7\u5c0f\u6768",
        "standard_code": "\u6a19\u6e96\u30b3\u30fc\u30c9\u5c0f\u6768",
        "title": "\u6c0f\u540d",
    }


def _impl__merge_address(defaults: Dict[str, Any], configured: Any) -> Dict[str, Any]:
    result = dict(defaults)
    if isinstance(configured, dict):
        for key, value in configured.items():
            result[str(key)] = value
    return result


def _impl__porder_create_fields_for_items(items: list[Dict[str, Any]], porder_sn: str, variables: Dict[str, Any]) -> OrderedDict[str, Any]:
    fields: OrderedDict[str, Any] = OrderedDict()
    fields["create_type"] = str(variables.get("create_type") or "send")
    fields["porder_sn"] = porder_sn
    fields["logistics_id"] = str(variables.get("porder_logistics_id") or variables.get("logistics_id") or "14")
    fields["client_remark"] = str(variables.get("client_remark") or "")
    for index, item in enumerate(items):
        prefix = f"porder_detail[{index}]"
        fields[f"{prefix}[order_detail_id]"] = str(item.get("order_detail_id") or "")
        fields[f"{prefix}[send_num]"] = _as_int(item.get("send_num"), 1)
        fields[f"{prefix}[client_remark]"] = str(item.get("client_remark") or variables.get("porder_detail_remark") or "自动化配送单明细备注")
    receiver = _merge_address(_default_receiver_address(), variables.get("receiver_address"))
    importer = _merge_address(_default_importer_address(), variables.get("importer_address"))
    fields.update(_address_fields("receiver_address", receiver))
    fields.update(_address_fields("importer_address", importer))
    fields["is_amazon"] = str(variables.get("is_amazon") or "0")
    _apply_extra_fields(fields, variables.get("porder_create_fields"))
    return fields


def _impl__porder_create_fields(order_detail_id: str, porder_sn: str, send_num: int, variables: Dict[str, Any]) -> OrderedDict[str, Any]:
    return _porder_create_fields_for_items(
        [{"order_detail_id": order_detail_id, "send_num": send_num, "client_remark": variables.get("porder_detail_remark") or "自动化配送单明细备注"}],
        porder_sn,
        variables,
    )


def _impl__extract_porder_sn(payload: Dict[str, Any], fallback: str) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ["porder_sn", "porderSn", "sn", "order_sn"]:
            value = data.get(key)
            if value:
                return str(value)
    if isinstance(data, str) and data.strip().startswith("P"):
        return data.strip()
    for key in ["porder_sn", "porderSn", "sn"]:
        value = payload.get(key)
        if value:
            return str(value)
    return fallback


def _impl__walk_dicts(value: Any, depth: int = 0) -> list[Dict[str, Any]]:
    if depth > 8:
        return []
    if isinstance(value, list):
        rows: list[Dict[str, Any]] = []
        for item in value:
            rows.extend(_walk_dicts(item, depth + 1))
        return rows
    if not isinstance(value, dict):
        return []
    rows = [value]
    for item in value.values():
        if isinstance(item, (dict, list)):
            rows.extend(_walk_dicts(item, depth + 1))
    return rows


def _impl__first_deep_value(value: Any, keys: list[str]) -> Any:
    for row in _walk_dicts(value):
        for key in keys:
            item = row.get(key)
            if item not in (None, "", [], {}):
                return item
    return ""


def _impl__porder_detail_rows(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    data = payload.get("data")
    roots = [data, payload]
    rows: list[Dict[str, Any]] = []
    detail_keys = [
        "porder_detail",
        "porderDetail",
        "porder_detail_list",
        "porderDetailList",
        "detail",
        "details",
        "list",
    ]
    for root in roots:
        if isinstance(root, dict):
            for key in detail_keys:
                child = root.get(key)
                if isinstance(child, (dict, list)):
                    rows.extend(_nested_rows(child))
        elif isinstance(root, list):
            rows.extend(_nested_rows(root))
    filtered: list[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _field_value(row, ["porder_detail_id", "porderDetailId", "detail_id", "id"]) in (None, ""):
            continue
        if any(key in row for key in ["porder_sn", "goods_id", "goods_name", "send_num", "wait_box_num", "received_num", "order_detail_id"]):
            filtered.append(row)
    return filtered or [row for row in rows if isinstance(row, dict)]


def _impl__porder_detail_id(row: Dict[str, Any]) -> str:
    return str(_field_value(row, ["porder_detail_id", "porderDetailId", "detail_id", "id"]) or "").strip()


def _impl__porder_wait_box_num(row: Dict[str, Any], fallback: int = 1) -> int:
    value = _field_value(
        row,
        [
            "wait_box_num",
            "waitBoxNum",
            "not_box_num",
            "notBoxNum",
            "packing_num",
            "received_num",
            "send_num",
            "num",
        ],
    )
    number = _as_int(value, fallback)
    return number if number > 0 else fallback


def _impl__box_need_num(value: Any, fallback_num: int) -> int:
    fallback = max(1, _as_int(fallback_num, 1))
    number = _as_int(value, fallback)
    if number <= 0:
        return fallback
    return min(number, fallback)


def _impl__extract_freight_id(*payloads: Dict[str, Any], variables: Dict[str, Any] | None = None) -> str:
    variables = variables or {}
    configured = str(variables.get("freight_id") or variables.get("porder_freight_id") or "").strip()
    if configured:
        return configured
    freight_shape_keys = {
        "freight_id",
        "freightId",
        "freightID",
        "logistics_id",
        "logisticsId",
        "length",
        "width",
        "height",
        "weight",
        "box_no",
        "boxNo",
        "box_num",
        "boxNum",
        "porder_sn",
    }
    for payload in payloads:
        direct = _first_deep_value(payload, ["freight_id", "freightId", "freightID"])
        if direct not in (None, ""):
            return str(direct).strip()
        freight_set = _first_deep_value(payload, ["freight_id_set", "freightIdSet", "freight_ids"])
        if isinstance(freight_set, list) and freight_set:
            return str(freight_set[0]).strip()
        for row in _walk_dicts(payload):
            row_id = row.get("id")
            if row_id in (None, ""):
                continue
            if any(key in row and row.get(key) not in (None, "") for key in freight_shape_keys):
                return str(row_id).strip()
    return ""


def _impl__payload_structure_sample(payload: Dict[str, Any], limit: int = 8) -> list[Dict[str, Any]]:
    samples: list[Dict[str, Any]] = []
    for row in _walk_dicts(payload):
        if not row:
            continue
        keys = list(row.keys())[:20]
        interesting = {
            key: row.get(key)
            for key in [
                "id",
                "porder_detail_id",
                "porderDetailId",
                "stock_id",
                "stockId",
                "wms_stock_id",
                "num",
                "num_need",
                "need_num",
                "stock_num",
                "storage_num",
                "send_num",
                "wait_box_num",
            ]
            if key in row
        }
        samples.append({"keys": keys, "interesting": interesting})
        if len(samples) >= limit:
            break
    return samples


def _impl__freight_box_brief(payload: Dict[str, Any], limit: int = 10) -> list[Dict[str, Any]]:
    boxes: list[Dict[str, Any]] = []
    freight_keys = {
        "number",
        "status",
        "length",
        "width",
        "height",
        "weight",
        "logistics_id",
        "box_id",
        "volume",
        "charge_weight",
        "freight_id",
    }
    for row in _walk_dicts(payload):
        if row.get("id") in (None, ""):
            continue
        if not any(key in row for key in freight_keys):
            continue
        boxes.append(
            {
                "id": row.get("id"),
                "porder_sn": row.get("porder_sn"),
                "number": row.get("number"),
                "status": row.get("status"),
                "statusName": row.get("statusName") or row.get("status_name"),
                "length": row.get("length"),
                "width": row.get("width"),
                "height": row.get("height"),
                "weight": row.get("weight"),
                "logistics_id": row.get("logistics_id"),
                "box_id": row.get("box_id"),
                "freight_id": row.get("freight_id"),
            }
        )
        if len(boxes) >= limit:
            break
    return boxes


def _impl__has_incomplete_freight_box(payload: Dict[str, Any]) -> bool:
    boxes = _freight_box_brief(payload)
    for box in boxes:
        status = box.get("status")
        status_name = str(box.get("statusName") or "")
        if status in (None, "", 0, "0", False) or "未完成" in status_name or "空箱" in status_name:
            return True
    return False


def _impl__porder_complete_box_paths(variables: Dict[str, Any]) -> list[str]:
    paths: list[str] = []
    api_paths = _api_paths(variables)
    configured = api_paths.get("admin_porder_complete_box") or variables.get("admin_porder_complete_box_path")
    if configured:
        paths.append(str(configured))
    paths.extend(_as_list(variables.get("porder_complete_box_paths"), []))
    paths.append("/porder.completeBox")
    normalized = []
    for path in _unique_list(paths):
        normalized.append(path if path.startswith("/") else f"/{path}")
    return normalized


def _impl__extract_stock_item(payload: Dict[str, Any], fallback_num: int, porder_detail_id: str = "") -> Dict[str, Any]:
    configured_stock_id = str(payload.get("stock_id") or "").strip()
    if configured_stock_id:
        return {"stock_id": configured_stock_id, "num_need": _box_need_num(fallback_num, fallback_num)}
    stock_shape_keys = {
        "stock_id",
        "stockId",
        "wms_stock_id",
        "wmsStockId",
        "stock_num",
        "stockNum",
        "storage_num",
        "storageNum",
        "num_need",
        "need_num",
        "grid_id",
        "warehouse_id",
        "order_purchase_id",
        "putaway_at",
    }
    for row in _walk_dicts(payload):
        stock_id = _field_value(row, ["stock_id", "stockId", "wms_stock_id", "wmsStockId", "stockDetailId", "stock_detail_id"])
        if stock_id not in (None, ""):
            return {
                "stock_id": str(stock_id).strip(),
                "num_need": _box_need_num(
                    _field_value(row, ["num_need", "need_num", "send_num", "wait_box_num", "stock_num", "storage_num", "num"]),
                    fallback_num,
                ),
            }
    for row in _walk_dicts(payload):
        for stock_key in ["stock", "stocks", "stock_list", "stockList", "wms_stock", "wmsStock", "storage", "storage_list", "storageList"]:
            stock = row.get(stock_key)
            if not isinstance(stock, list):
                continue
            for item in stock:
                if isinstance(item, dict) and item.get("id") not in (None, ""):
                    return {
                        "stock_id": str(item.get("id")).strip(),
                        "num_need": _box_need_num(
                            _field_value(item, ["num_need", "need_num", "send_num", "wait_box_num", "stock_num", "storage_num", "num"]),
                            fallback_num,
                        ),
                    }
    candidate_ids: list[tuple[str, int]] = []
    for row in _walk_dicts(payload):
        row_id = row.get("id")
        if row_id in (None, "") or str(row_id) == str(porder_detail_id):
            continue
        if any(key in row and row.get(key) not in (None, "") for key in stock_shape_keys):
            candidate_ids.append(
                (
                    str(row_id).strip(),
                    _box_need_num(
                        _field_value(row, ["num_need", "need_num", "send_num", "wait_box_num", "stock_num", "storage_num", "num"]),
                        fallback_num,
                    ),
                )
            )
    if len(candidate_ids) == 1:
        stock_id, num_need = candidate_ids[0]
        return {"stock_id": stock_id, "num_need": num_need}
    return {"stock_id": "", "num_need": _box_need_num(fallback_num, fallback_num)}


def _impl__stock_item_from_row(row: Dict[str, Any], fallback_num: int) -> Dict[str, Any]:
    stock_id = _field_value(row, ["stock_id", "stockId", "wms_stock_id", "wmsStockId", "stockDetailId", "stock_detail_id"])
    if stock_id not in (None, ""):
        return {
            "stock_id": str(stock_id).strip(),
            "num_need": _box_need_num(
                _field_value(row, ["num_need", "need_num", "send_num", "wait_box_num", "stock_num", "storage_num", "num"]),
                fallback_num,
            ),
        }
    for stock_key in ["stock", "stocks", "stock_list", "stockList", "wms_stock", "wmsStock", "storage", "storage_list", "storageList"]:
        stock = row.get(stock_key)
        stock_rows = stock if isinstance(stock, list) else [stock] if isinstance(stock, dict) else []
        for item in stock_rows:
            if not isinstance(item, dict):
                continue
            item_id = _field_value(item, ["stock_id", "stockId", "wms_stock_id", "wmsStockId", "stockDetailId", "stock_detail_id", "id"])
            if item_id not in (None, ""):
                return {
                    "stock_id": str(item_id).strip(),
                    "num_need": _box_need_num(
                        _field_value(item, ["num_need", "need_num", "send_num", "wait_box_num", "stock_num", "storage_num", "num"]),
                        fallback_num,
                    ),
                }
    return {"stock_id": "", "num_need": _box_need_num(fallback_num, fallback_num)}


def _impl__extract_stock_item_for_detail(
    payload: Dict[str, Any],
    porder_detail_id: str,
    fallback_num: int,
    *,
    allow_global_fallback: bool = False,
) -> Dict[str, Any]:
    detail_id = str(porder_detail_id or "").strip()
    for row in _walk_dicts(payload):
        row_detail_id = str(_field_value(row, ["porder_detail_id", "porderDetailId", "detail_id", "detailId"]) or "").strip()
        row_id = str(row.get("id") or "").strip()
        if detail_id and detail_id not in {row_detail_id, row_id}:
            continue
        stock_item = _stock_item_from_row(row, fallback_num)
        if stock_item.get("stock_id"):
            return stock_item
    if allow_global_fallback:
        return _extract_stock_item(payload, fallback_num, detail_id)
    return {"stock_id": "", "num_need": _box_need_num(fallback_num, fallback_num)}


def _impl__porder_flow_detail_items(rows: list[Dict[str, Any]], fallback_num: int = 1) -> list[Dict[str, Any]]:
    items: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        porder_detail_id = _porder_detail_id(row)
        if not porder_detail_id or porder_detail_id in seen:
            continue
        seen.add(porder_detail_id)
        items.append(
            {
                "porder_detail_id": porder_detail_id,
                "wait_box_num": _porder_wait_box_num(row, fallback_num),
            }
        )
    return items


def _impl__porder_detail_payload(
    session: requests.Session,
    base_url: str,
    variables: Dict[str, Any],
    porder_sn: str,
    timeout: int,
    retries: int = 4,
) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    payload: Dict[str, Any] = {}
    rows: list[Dict[str, Any]] = []
    for attempt in range(retries + 1):
        payload = _post_admin_form(
            session,
            base_url,
            _api_path(variables, "admin_porder_detail", "/porder.detail"),
            {"porder_sn": porder_sn},
            timeout,
        )
        rows = _porder_detail_rows(payload)
        if _api_success(payload) and rows:
            return payload, rows
        if attempt < retries:
            time.sleep(0.8 * (attempt + 1))
    return payload, rows


def _impl__porder_detail_brief(payload: Dict[str, Any], rows: list[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        **_payload_brief(payload),
        "detail_count": len(rows),
        "details": [
            {
                "id": _porder_detail_id(row),
                "goods_id": row.get("goods_id"),
                "num": row.get("num"),
                "send_num": row.get("send_num"),
                "wait_box_num": row.get("wait_box_num"),
                "received_num": row.get("received_num"),
                "freight_id": row.get("freight_id"),
                "status": row.get("status"),
                "statusName": row.get("statusName") or row.get("status_name"),
            }
            for row in rows[:10]
        ],
    }


_porder_sn = _compat_wrapper(_impl__porder_sn)
_warehouse_list_fields = _compat_wrapper(_impl__warehouse_list_fields)
_warehouse_candidate_paths = _compat_wrapper(_impl__warehouse_candidate_paths)
_nested_rows = _compat_wrapper(_impl__nested_rows)
_field_value = _compat_wrapper(_impl__field_value)
_warehouse_item_id = _compat_wrapper(_impl__warehouse_item_id)
_warehouse_sku_id = _compat_wrapper(_impl__warehouse_sku_id)
_warehouse_sendable_num = _compat_wrapper(_impl__warehouse_sendable_num)
_warehouse_item_brief = _compat_wrapper(_impl__warehouse_item_brief)
_warehouse_requested_order_detail_ids = _compat_wrapper(_impl__warehouse_requested_order_detail_ids)
_warehouse_row_order_sn = _compat_wrapper(_impl__warehouse_row_order_sn)
_warehouse_row_matches_current_order = _compat_wrapper(_impl__warehouse_row_matches_current_order)
_select_warehouse_items = _compat_wrapper(_impl__select_warehouse_items)
_select_warehouse_item = _compat_wrapper(_impl__select_warehouse_item)
_address_fields = _compat_wrapper(_impl__address_fields)
_default_receiver_address = _compat_wrapper(_impl__default_receiver_address)
_default_importer_address = _compat_wrapper(_impl__default_importer_address)
_merge_address = _compat_wrapper(_impl__merge_address)
_porder_create_fields_for_items = _compat_wrapper(_impl__porder_create_fields_for_items)
_porder_create_fields = _compat_wrapper(_impl__porder_create_fields)
_extract_porder_sn = _compat_wrapper(_impl__extract_porder_sn)
_walk_dicts = _compat_wrapper(_impl__walk_dicts)
_first_deep_value = _compat_wrapper(_impl__first_deep_value)
_porder_detail_rows = _compat_wrapper(_impl__porder_detail_rows)
_porder_detail_id = _compat_wrapper(_impl__porder_detail_id)
_porder_wait_box_num = _compat_wrapper(_impl__porder_wait_box_num)
_box_need_num = _compat_wrapper(_impl__box_need_num)
_extract_freight_id = _compat_wrapper(_impl__extract_freight_id)
_payload_structure_sample = _compat_wrapper(_impl__payload_structure_sample)
_freight_box_brief = _compat_wrapper(_impl__freight_box_brief)
_has_incomplete_freight_box = _compat_wrapper(_impl__has_incomplete_freight_box)
_porder_complete_box_paths = _compat_wrapper(_impl__porder_complete_box_paths)
_extract_stock_item = _compat_wrapper(_impl__extract_stock_item)
_stock_item_from_row = _compat_wrapper(_impl__stock_item_from_row)
_extract_stock_item_for_detail = _compat_wrapper(_impl__extract_stock_item_for_detail)
_porder_flow_detail_items = _compat_wrapper(_impl__porder_flow_detail_items)
_porder_detail_payload = _compat_wrapper(_impl__porder_detail_payload)
_porder_detail_brief = _compat_wrapper(_impl__porder_detail_brief)
