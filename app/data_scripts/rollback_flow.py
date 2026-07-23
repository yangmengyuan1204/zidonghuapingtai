from __future__ import annotations

import json
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Tuple
from urllib.parse import urljoin

import requests

from ..models import Env
from ..vendor import piliangtianjiagouwuche as bulk_cart
from .data_script_shared import _admin_session_from, _finish_named
from .order_support import (
    _admin_login,
    _flatten_urlencoded_fields,
    _order_detail_data,
    _order_status_code,
    _post_admin_form,
    _post_admin_urlencoded,
)
from .payment_support import _admin_rows_from_payload
from .porder_resume_support import _detect_resume_porder_state
from .purchase_support import (
    _first_preview_user_id,
    _flatten_follow_items,
    _follow_list_fields,
    _grid_candidates,
    _order_purchase_id,
    _preview_items,
    _preview_rows_from_payload,
)


ROLLBACK_FLOW_SCRIPT_NAME = "日本站业务状态回退"

ROLLBACK_TARGET_LABELS = {
    "order_wait_offer": "订单待报价",
    "order_purchase": "订单采购",
    "order_translate": "订单翻译",
    "porder_wait_offer": "配送单待报价",
    "porder_wait_box": "配送单待装箱",
    "porder_wait_translate": "配送单待翻译",
    "shelf_checking": "商品核查中",
}

ORDER_STAGE_SEQUENCE = ["order_translate", "order_purchase", "order_wait_offer", "order_quoted"]
PORDER_STAGE_SEQUENCE = ["porder_wait_translate", "porder_wait_box", "porder_wait_offer", "porder_quoted"]

ORDER_STATUS_STAGES = {20: "order_translate", 21: "order_purchase", 22: "order_wait_offer", 30: "order_quoted"}
PORDER_DETECTED_STAGES = {
    "warehouse_delivery_created": "porder_wait_translate",
    "porder_translated": "porder_wait_box",
    "porder_wait_offer": "porder_wait_offer",
    "porder_offered": "porder_quoted",
}

ORDER_EDGES = {
    "order_quoted": ("order_wait_offer", "admin_order_back_to_wait_offer", "/order.backToWaitOffer"),
    "order_wait_offer": ("order_purchase", "admin_order_back_to_wait_confirm", "/order.backToWaitConfirm"),
    "order_purchase": ("order_translate", "admin_order_back_to_wait_translate", "/order.backToWaitTranslate"),
}
PORDER_EDGES = {
    "porder_quoted": ("porder_wait_offer", "admin_porder_back_to_offer", "/porder.backToOffer"),
    "porder_wait_offer": ("porder_wait_box", "admin_porder_back_to_confirm", "/porder.backToConfirm"),
    "porder_wait_box": ("porder_wait_translate", "admin_porder_to_wait_translate", "/porder.toWaitTranslate"),
}


class RollbackFlowError(RuntimeError):
    pass


def _api_success(payload: Dict[str, Any]) -> bool:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return False
    try:
        return int(payload.get("code") or 0) == 0
    except (TypeError, ValueError):
        return False


def _api_path(variables: Dict[str, Any], key: str, default: str) -> str:
    paths = variables.get("api_paths") if isinstance(variables.get("api_paths"), dict) else {}
    return str(paths.get(key) or variables.get(f"{key}_path") or default)


def _payload_brief(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {key: payload.get(key) for key in ("success", "code", "msg") if key in payload}


def _number(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _item_status_text(item: Dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "").strip()
        for key in ("statusName", "status_name", "statusText", "status_text", "follow_status_name")
        if item.get(key) not in (None, "")
    )


def _item_is_checking(item: Dict[str, Any]) -> bool:
    if "核查" in _item_status_text(item):
        return True
    for key in ("status", "follow_status"):
        status = _number(item.get(key))
        if status is not None and status >= 40:
            return True
    return False


class JapanRollbackGateway:
    def __init__(self, env: Env, variables: Dict[str, Any], log: Dict[str, Any]):
        self.env = env
        self.variables = dict(variables or {})
        self.log = log
        self.base_url = str(self.variables.get("backend_base_url") or env.base_url or bulk_cart.BASE_URL).rstrip("/")
        self.timeout = int(self.variables.get("timeout") or env.timeout or 25)
        self.session = _admin_session_from(self.variables)

        login_payload, token = _admin_login(self.session, self.base_url, self.variables, self.timeout)
        self.admin_token = token
        self.log["login"] = {**_payload_brief(login_payload), "token_extracted": bool(token)}
        if not _api_success(login_payload) or not token:
            raise RollbackFlowError("后台登录失败")

    def _mutation_once(self, path: str, fields: Dict[str, Any]) -> tuple[Dict[str, Any], str]:
        pairs: list[tuple[str, str]] = []
        for key, value in fields.items():
            pairs.extend(_flatten_urlencoded_fields(value, str(key)))
        url = urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))
        try:
            response = self.session.post(
                url,
                data=pairs,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.timeout,
            )
            payload = response.json()
            if not isinstance(payload, dict):
                return {}, "写接口未返回JSON对象"
            return payload, ""
        except (requests.RequestException, ValueError) as exc:
            return {}, f"写接口结果不确定：{type(exc).__name__}"

    def order_snapshot(self, order_sn: str) -> Dict[str, Any]:
        payload, order_data = _order_detail_data(
            self.session,
            self.base_url,
            self.variables,
            order_sn,
            self.timeout,
        )
        if not _api_success(payload) or not order_data:
            raise RollbackFlowError("未查询到订单详情")
        status = _order_status_code(order_data)
        return {
            "stage": ORDER_STATUS_STAGES.get(status, ""),
            "status": status,
            "status_name": order_data.get("statusName") or order_data.get("status_name"),
            "data": order_data,
        }

    def rollback_order_edge(self, source: str, order_sn: str, order_data: Dict[str, Any]) -> tuple[Dict[str, Any], str, str]:
        target, path_key, default_path = ORDER_EDGES[source]
        if source == "order_wait_offer":
            order_detail = order_data.get("order_detail")
            if not isinstance(order_detail, list) or not order_detail:
                raise RollbackFlowError("最新订单详情缺少订单商品明细，未执行回退")
            rollback_data = {
                "order_sn": order_data.get("order_sn") or order_sn,
                "order_detail": order_detail,
                "other_price": order_data.get("other_price") or "0",
                "other_price_remark": order_data.get("other_price_remark") or "",
                "predict_logistics_price": order_data.get("predict_logistics_price") or "",
                "y_remark": order_data.get("y_remark") or "",
                "y_reply": order_data.get("y_reply") or "",
            }
            fields = {"data": json.dumps(rollback_data, ensure_ascii=False, separators=(",", ":"))}
        else:
            fields = {"order_sn_set": [order_sn]}
        payload, uncertain = self._mutation_once(_api_path(self.variables, path_key, default_path), fields)
        return payload, uncertain, target

    def porder_snapshot(self, porder_sn: str) -> Dict[str, Any]:
        detect_log: Dict[str, Any] = {}
        passed, summary = _detect_resume_porder_state(
            self.env,
            self.variables,
            porder_sn,
            detect_log,
        )
        if not passed:
            raise RollbackFlowError(str(summary.get("reason") or "未查询到配送单详情"))
        detected = str(summary.get("detected_start_node") or "")
        return {
            "stage": PORDER_DETECTED_STAGES.get(detected, ""),
            "detected_start_node": detected,
            "status_texts": summary.get("detail_status_texts") or [],
        }

    def rollback_porder_edge(self, source: str, porder_sn: str) -> tuple[Dict[str, Any], str, str]:
        target, path_key, default_path = PORDER_EDGES[source]
        token = str(getattr(self, "admin_token", "") or "")
        self.session.headers.update(
            {
                "AdminToken": f"Bearer {token}" if token else "",
                "adminToken": f"Bearer {token}" if token else "",
                "Fingerprint": str(self.variables.get("fingerprint") or "35d3d2dc553624bd3e6cc32688f4e43b"),
                "PageUrlTrace": f"https://jpmanage.rakumart.cn/#/porderDetail?porder_sn={porder_sn}",
                "Origin": "https://jpmanage.rakumart.cn",
                "Referer": "https://jpmanage.rakumart.cn/",
            }
        )
        payload, uncertain = self._mutation_once(
            _api_path(self.variables, path_key, default_path),
            {"porder_sn": porder_sn},
        )
        return payload, uncertain, target

    def _follow_candidates(self, order_sn: str, purchase_no: str, purchase_id: str) -> tuple[str, list[Dict[str, Any]]]:
        statuses = []
        for value in (self.variables.get("follow_status"), "4", "3", ""):
            text = "" if value is None else str(value)
            if text not in statuses:
                statuses.append(text)
        for status in statuses:
            fields = _follow_list_fields(self.variables, purchase_no, order_sn, status)
            payload = _post_admin_form(
                self.session,
                self.base_url,
                _api_path(self.variables, "admin_follow_list", "/follow.followList"),
                fields,
                self.timeout,
            )
            rows = _admin_rows_from_payload(payload)
            items = _flatten_follow_items(rows)
            if not _api_success(payload) or not items:
                continue
            if purchase_no:
                resolved_purchase_no = purchase_no
            else:
                selected = items
                if purchase_id:
                    selected = [item for item in items if str(_order_purchase_id(item) or "") == purchase_id]
                    if not selected:
                        raise RollbackFlowError("未找到指定采购记录ID对应的商品")
                purchase_numbers = {
                    str(item.get("_purchase_no") or item.get("purchase_no") or "").strip()
                    for item in selected
                    if item.get("_purchase_no") or item.get("purchase_no")
                }
                if len(purchase_numbers) != 1:
                    raise RollbackFlowError("订单包含多个交易号，请明确提供 purchase_no 或 order_purchase_id")
                resolved_purchase_no = next(iter(purchase_numbers))
            return resolved_purchase_no, items
        return purchase_no, []

    def _preview(self, purchase_no: str) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
        payload = _post_admin_form(
            self.session,
            self.base_url,
            _api_path(self.variables, "admin_follow_up_preview", "/follow.upPreview"),
            {"purchase_no": purchase_no, "express_no": str(self.variables.get("express_no") or "")},
            self.timeout,
        )
        if not _api_success(payload):
            raise RollbackFlowError("核查商品预览查询失败")
        rows = _preview_rows_from_payload(payload)
        return rows, _preview_items(rows)

    @staticmethod
    def _select_item(items: list[Dict[str, Any]], requested_id: str) -> Dict[str, Any]:
        if requested_id:
            matched = [item for item in items if str(_order_purchase_id(item) or "") == requested_id]
            if len(matched) != 1:
                raise RollbackFlowError("未找到指定采购记录ID对应的商品")
            selected = matched[0]
            if not _item_is_checking(selected) and (_number(selected.get("storage_num")) or Decimal("0")) <= 0:
                raise RollbackFlowError("指定商品未上架，未执行下架")
            return selected
        candidates = [
            item
            for item in items
            if _item_is_checking(item) or (_number(item.get("storage_num")) or Decimal("0")) > 0
        ]
        if not candidates:
            raise RollbackFlowError("没有已上架商品可下架")
        if len(candidates) != 1:
            raise RollbackFlowError("订单包含多个可下架商品，请明确提供 order_purchase_id")
        return candidates[0]

    @staticmethod
    def _grid_has_purchase(grid: Dict[str, Any], purchase_id: str) -> bool:
        stack: list[Any] = [grid.get("wms_stock"), grid.get("stock"), grid.get("items")]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                if str(value.get("order_purchase_id") or value.get("purchase_id") or "") == purchase_id:
                    return True
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
        return False

    def _source_grid(self, payload: Dict[str, Any], purchase_id: str) -> Dict[str, Any]:
        grids = _grid_candidates(payload.get("data"), str(self.variables.get("warehouse_index") or "2"))
        configured = str(self.variables.get("grid_id") or "").strip()
        if configured:
            match = next((grid for grid in grids if str(grid.get("id") or "") == configured), None)
            if match:
                return match
            raise RollbackFlowError("指定库位不属于当前商品")
        matched = [grid for grid in grids if self._grid_has_purchase(grid, purchase_id)]
        if len(matched) == 1:
            return matched[0]
        if len(grids) == 1:
            return grids[0]
        raise RollbackFlowError("无法唯一识别商品所在库位，请提供 grid_id")

    def shelf_snapshot(self, order_sn: str, purchase_no: str, purchase_id: str) -> Dict[str, Any]:
        resolved_purchase_no, list_items = self._follow_candidates(order_sn, purchase_no, purchase_id)
        if not resolved_purchase_no:
            raise RollbackFlowError("未查询到商品交易号")
        rows, preview_items = self._preview(resolved_purchase_no)
        candidates = preview_items or list_items
        item = self._select_item(candidates, purchase_id)
        return {
            "purchase_no": resolved_purchase_no,
            "purchase_id": str(_order_purchase_id(item) or ""),
            "item": item,
            "rows": rows,
            "checking": _item_is_checking(item),
        }

    def rollback_shelf(self, snapshot: Dict[str, Any], quantity: int) -> tuple[Dict[str, Any], str]:
        item = snapshot["item"]
        purchase_id = str(snapshot["purchase_id"])
        user_id = str(self.variables.get("warehouse_user_id") or _first_preview_user_id(snapshot["rows"], [item]) or "")
        shelf_types = self.variables.get("shelf_type_set") or [1, 3]
        if isinstance(shelf_types, str):
            shelf_types = [value.strip() for value in shelf_types.split(",") if value.strip()]
        grid_payload = _post_admin_urlencoded(
            self.session,
            self.base_url,
            _api_path(self.variables, "admin_wms_grid_preview", "/wms.wmsGridPreview"),
            {"shelf_type_set": shelf_types, "user_id": user_id, "order_purchase_id": [purchase_id]},
            self.timeout,
        )
        if not _api_success(grid_payload):
            raise RollbackFlowError("商品库位查询失败")
        grid = self._source_grid(grid_payload, purchase_id)
        fields = {
            "grid_id": grid.get("id"),
            "data": [
                {
                    "num": quantity,
                    "order_purchase_id": purchase_id,
                    "uncomplete_problem_num": item.get("uncomplete_problem_num") or 0,
                }
            ],
        }
        return self._mutation_once(
            _api_path(self.variables, "admin_follow_up_storage", "/follow.upStorage"),
            fields,
        )


class RollbackFlow:
    def __init__(self, gateway: JapanRollbackGateway, variables: Dict[str, Any], log: Dict[str, Any]):
        self.gateway = gateway
        self.variables = dict(variables or {})
        self.log = log
        self.verify_retries = max(1, int(self.variables.get("rollback_verify_retries") or 4))
        self.verify_delay = max(0.0, float(self.variables.get("rollback_verify_delay") or 0.6))

    def _wait_stage(self, getter: Any, target: str) -> Dict[str, Any]:
        last: Dict[str, Any] = {}
        for attempt in range(self.verify_retries):
            last = getter()
            if last.get("stage") == target:
                return last
            if attempt < self.verify_retries - 1 and self.verify_delay:
                time.sleep(self.verify_delay)
        return last

    def _run_chain(
        self,
        identifier: str,
        target: str,
        sequence: list[str],
        snapshot_getter: Any,
        edge_runner: Any,
    ) -> Dict[str, Any]:
        snapshot = snapshot_getter(identifier)
        current = str(snapshot.get("stage") or "")
        if current not in sequence:
            raise RollbackFlowError("当前状态无法安全识别，未执行回退")
        if target not in sequence:
            raise RollbackFlowError("目标状态不属于当前回退链")
        current_index = sequence.index(current)
        target_index = sequence.index(target)
        if current_index < target_index:
            raise RollbackFlowError("目标状态在当前状态之后，回退脚本不会执行正向推进")
        if current_index == target_index:
            return {"current_node": target, "target_node": target, "already_at_target": True, "verified": True}

        while current_index > target_index:
            payload, uncertain, adjacent_target = edge_runner(current, identifier, snapshot)
            verified = self._wait_stage(lambda: snapshot_getter(identifier), adjacent_target)
            self.log.setdefault("steps", []).append(
                {
                    "source": current,
                    "target": adjacent_target,
                    "response": _payload_brief(payload),
                    "uncertain": uncertain,
                    "verified_stage": verified.get("stage"),
                }
            )
            if verified.get("stage") != adjacent_target:
                reason = uncertain or str(payload.get("msg") or "回退后状态校验失败")
                raise RollbackFlowError(reason)
            snapshot = verified
            current = adjacent_target
            current_index = sequence.index(current)

        return {
            "current_node": target,
            "target_node": target,
            "verified": True,
            "step_count": len(self.log.get("steps") or []),
        }

    def run(self) -> Dict[str, Any]:
        target = str(self.variables.get("rollback_target") or self.variables.get("target_node") or "").strip()
        if target in ORDER_STAGE_SEQUENCE:
            order_sn = str(self.variables.get("order_sn") or "").strip()
            if not order_sn:
                raise RollbackFlowError("订单回退必须提供 order_sn")

            def order_edge(source: str, identifier: str, snapshot: Dict[str, Any]):
                return self.gateway.rollback_order_edge(source, identifier, snapshot.get("data") or {})

            return {"order_sn": order_sn, **self._run_chain(order_sn, target, ORDER_STAGE_SEQUENCE, self.gateway.order_snapshot, order_edge)}

        if target in PORDER_STAGE_SEQUENCE:
            porder_sn = str(self.variables.get("porder_sn") or "").strip()
            if not porder_sn:
                raise RollbackFlowError("配送单回退必须提供 porder_sn")

            def porder_edge(source: str, identifier: str, _snapshot: Dict[str, Any]):
                return self.gateway.rollback_porder_edge(source, identifier)

            return {"porder_sn": porder_sn, **self._run_chain(porder_sn, target, PORDER_STAGE_SEQUENCE, self.gateway.porder_snapshot, porder_edge)}

        if target == "shelf_checking":
            order_sn = str(self.variables.get("order_sn") or "").strip()
            purchase_no = str(self.variables.get("purchase_no") or "").strip()
            purchase_id = str(self.variables.get("order_purchase_id") or "").strip()
            if not order_sn and not purchase_no:
                raise RollbackFlowError("商品下架必须提供 order_sn 或 purchase_no")
            quantity = int(self.variables.get("rollback_quantity") or -1)
            if quantity >= 0:
                raise RollbackFlowError("商品下架数量必须为负整数")
            before = self.gateway.shelf_snapshot(order_sn, purchase_no, purchase_id)
            if before.get("checking"):
                return {
                    "order_sn": order_sn,
                    "purchase_no": before.get("purchase_no"),
                    "order_purchase_id": before.get("purchase_id"),
                    "current_node": target,
                    "target_node": target,
                    "already_at_target": True,
                    "verified": True,
                }
            before_storage = _number((before.get("item") or {}).get("storage_num"))
            payload, uncertain = self.gateway.rollback_shelf(before, quantity)
            after: Dict[str, Any] = {}
            after_storage: Decimal | None = None
            storage_reduced = False
            verified = False
            for attempt in range(self.verify_retries):
                after = self.gateway.shelf_snapshot(order_sn, str(before.get("purchase_no") or ""), str(before.get("purchase_id") or ""))
                after_storage = _number((after.get("item") or {}).get("storage_num"))
                storage_reduced = before_storage is not None and after_storage is not None and after_storage < before_storage
                if after.get("checking"):
                    verified = True
                    break
                if attempt < self.verify_retries - 1 and self.verify_delay:
                    time.sleep(self.verify_delay)
            self.log.setdefault("steps", []).append(
                {
                    "source": "shelf_stored",
                    "target": target,
                    "quantity": quantity,
                    "response": _payload_brief(payload),
                    "uncertain": uncertain,
                    "verified": verified,
                    "storage_before": str(before_storage) if before_storage is not None else None,
                    "storage_after": str(after_storage) if after_storage is not None else None,
                    "storage_reduced": storage_reduced,
                }
            )
            if not verified:
                raise RollbackFlowError(uncertain or str(payload.get("msg") or "负数下架后未确认商品回到核查中"))
            return {
                "order_sn": order_sn,
                "purchase_no": before.get("purchase_no"),
                "order_purchase_id": before.get("purchase_id"),
                "current_node": target,
                "target_node": target,
                "rollback_quantity": quantity,
                "verified": True,
            }

        raise RollbackFlowError("未指定受支持的回退目标")


def run_rollback_flow_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    values = dict(variables or {})
    log: Dict[str, Any] = {
        "script": ROLLBACK_FLOW_SCRIPT_NAME,
        "target_node": values.get("rollback_target") or values.get("target_node"),
        "started_at": datetime.now(),
        "steps": [],
    }
    try:
        gateway = JapanRollbackGateway(env, values, log)
        summary = RollbackFlow(gateway, values, log).run()
        return _finish_named(ROLLBACK_FLOW_SCRIPT_NAME, log, True, summary)
    except Exception as exc:
        return _finish_named(
            ROLLBACK_FLOW_SCRIPT_NAME,
            log,
            False,
            {
                "order_sn": str(values.get("order_sn") or ""),
                "porder_sn": str(values.get("porder_sn") or ""),
                "target_node": str(values.get("rollback_target") or values.get("target_node") or ""),
                "verified": False,
                "reason": str(exc),
            },
        )
