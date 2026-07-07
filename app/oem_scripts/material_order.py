"""OEM 辅料单脚本 - 前台客户提交辅料单。

流程：客户登录 -> 查商品列表/辅料类型 -> 参考库 -> 上传凭证 -> 创建辅料单
"""
import sys
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin

import requests

sys.path.append(r"D:\A_zidonghuapingtai")

# Helpers imported lazily in run_material_order_script to avoid circular import
from app.vendor import piliangtianjiagouwuche as bulk_cart

MATERIAL_ORDER_SCRIPT_NAME = "辅料单"


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_goods_id(raw) -> List[int]:
    """解析 goods_id 输入：支持 int / list / 逗号分隔字符串"""
    if isinstance(raw, int):
        return [raw]
    if isinstance(raw, list):
        return [_as_int(x) for x in raw if _as_int(x) > 0]
    if isinstance(raw, str):
        if raw.strip().startswith("["):
            try:
                parsed = json.loads(raw)
                return [_as_int(x) for x in parsed if _as_int(x) > 0]
            except (json.JSONDecodeError, TypeError):
                pass
        return [_as_int(x) for x in raw.split(",") if _as_int(x.strip()) > 0]
    return []


def _configure_client_api_paths(client, variables):
    """按 data_scripts 中已有的配置方式同步 API 路径"""
    base = (getattr(client, "base_url", "") or "").rstrip("/")
    if base:
        client.login_path = base + "/api/login"
        client.goods_list_path = base + "/api/getGoodsList"


def run_material_order_script(
    env, variables: Dict[str, Any] | None = None
) -> Tuple[bool, str, str, Dict[str, Any]]:
    """OEM 辅料单脚本

    必填变量：account, password, accessory_name, goods_id
    可选变量：accessory_type(default=14), num(default=100), expend_number(default=1),
              master_image, config_id, client_tool
    """
    ensure_report_dirs()
    variables = dict(variables or {})
    started_at = datetime.now()

    account, password, client_tool = _client_login_inputs(variables)
    timeout = _as_int(variables.get("timeout"), getattr(env, "timeout", 25) or 25)
    base_url = getattr(env, "base_url", None) or bulk_cart.BASE_URL
    base_url = base_url.rstrip("/")

    log: Dict[str, Any] = {
        "script": MATERIAL_ORDER_SCRIPT_NAME,
        "base_url": base_url,
        "started_at": started_at,
    }

    accessory_name = str(variables.get("accessory_name") or "").strip()
    goods_id = _parse_goods_id(variables.get("goods_id"))
    accessory_type = _as_int(variables.get("accessory_type"), 14)
    num = _as_int(variables.get("num"), 100)
    expend_number = _as_int(variables.get("expend_number"), 1)
    master_image = str(variables.get("master_image") or "")
    config_id = variables.get("config_id")

    log["accessory_name"] = accessory_name
    log["goods_id"] = goods_id
    log["accessory_type"] = accessory_type
    log["num"] = num

    if not accessory_name:
        return _finish_named(MATERIAL_ORDER_SCRIPT_NAME, log, False, {"reason": "缺少必填参数：accessory_name 不能为空"})
    if not goods_id:
        return _finish_named(MATERIAL_ORDER_SCRIPT_NAME, log, False, {"reason": "缺少必填参数：goods_id 无效"})

    try:
        client = bulk_cart.RakumartClient(base_url, timeout)
        _configure_client_api_paths(client, variables)

        # 1. 登录
        token = _call_with_retry("client login", lambda: client.login(account, password, client_tool))
        log["login"] = {"success": True, "account": account, "token_extracted": bool(token)}

        # 2. 获取上传凭证（如果没传 master_image 则需要）
        if not master_image:
            try:
                token_resp = client.session.post(
                    base_url + "/common/common/getUploadToken",
                    json={},
                    timeout=timeout,
                )
                if token_resp.ok:
                    token_data = token_resp.json()
                    log["upload_token"] = {"fetched": True, "status": token_resp.status_code}
            except Exception as te:
                log["upload_token_error"] = str(te)

        # 3. 创建辅料单（核心接口）
        create_url = base_url + "/api/accessoryCreate"
        create_body = {
            "accessory_name": accessory_name,
            "goods_id": goods_id,
            "accessory_type": accessory_type,
            "num": str(num),
            "expend_number": expend_number,
            "master_image": master_image,
        }

        last_error = None
        create_data = {}
        for attempt in range(3):
            try:
                resp = client.session.post(create_url, json=create_body, timeout=timeout)
                create_data = resp.json()
                log["create_response"] = {
                    "status": resp.status_code,
                    "attempt": attempt + 1,
                    "body_preview": json.dumps(create_data, ensure_ascii=False)[:500],
                }
                if resp.ok and create_data.get("success"):
                    break
                last_error = create_data.get("msg") or f"HTTP {resp.status_code}"
            except Exception as e:
                last_error = str(e)
                if attempt < 2:
                    time.sleep(0.8 * (attempt + 1))

        if not create_data.get("success"):
            reason = last_error or "创建辅料单失败"
            return _finish_named(MATERIAL_ORDER_SCRIPT_NAME, log, False, {"reason": reason})

        # 4. 查询辅料列表确认
        try:
            list_resp = client.session.post(base_url + "/api/accessoryList", json={}, timeout=timeout)
            if list_resp.ok:
                list_data = list_resp.json()
                items = []
                raw_items = list_data.get("data") or []
                if isinstance(raw_items, dict):
                    items = raw_items.get("data") or raw_items.get("list") or []
                elif isinstance(raw_items, list):
                    items = raw_items
                log["list_count"] = len(items)
                log["latest_accessory"] = items[0] if items else None
        except Exception as le:
            log["list_error"] = str(le)

        summary: Dict[str, Any] = {
            "accessory_name": accessory_name,
            "goods_id": goods_id,
            "accessory_type": accessory_type,
            "num": num,
            "create_result": create_data.get("data"),
            "completed": True,
        }
        return _finish_named(MATERIAL_ORDER_SCRIPT_NAME, log, True, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(MATERIAL_ORDER_SCRIPT_NAME, log, False, {"reason": str(exc)})


def run_oem_material_order_script(env, variables=None):
    return run_material_order_script(env, variables)

