from datetime import datetime
import re
import sys
from typing import Any, Dict, Tuple

from ..executors import ensure_report_dirs
from ..models import Env
from ..oem_scripts.material_order import run_material_order_script
from ..vendor import piliangtianjiagouwuche as bulk_cart


_COMPAT_NAMES = (
    "MATERIAL_GENERATION_SCRIPT_NAME",
    "_as_int",
    "_call_with_retry",
    "_client_login_inputs",
    "_configure_client_api_paths",
    "_finish_named",
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.data_scripts"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _run_material_generation_script(env: Env, variables: Dict[str, Any] | None = None) -> Tuple[bool, str, str, Dict[str, Any]]:
    """辅料生成脚本 - 通过后端代理调用 jpapi 接口，避免 CORS 问题"""
    ensure_report_dirs()
    variables = dict(variables or {})
    started_at = datetime.now()

    account, password, client_tool = _client_login_inputs(variables)
    timeout = _as_int(variables.get("timeout"), env.timeout or 25)
    base_url = (env.base_url or bulk_cart.BASE_URL).rstrip("/")

    base_name = str(variables.get("name") or "").strip()
    count = max(1, _as_int(variables.get("count"), 1))

    log: Dict[str, Any] = {
        "script": MATERIAL_GENERATION_SCRIPT_NAME,
        "base_url": base_url,
        "name": base_name,
        "count": count,
        "started_at": started_at,
    }

    if not base_name:
        return _finish_named(
            MATERIAL_GENERATION_SCRIPT_NAME, log, False,
            {"reason": "缺少必要参数：辅料名称不能为空"},
        )

    try:
        # 登录客户端
        client = bulk_cart.RakumartClient(base_url, timeout)
        _configure_client_api_paths(client, variables)
        token = _call_with_retry("client login", lambda: client.login(account, password, client_tool))
        log["login"] = {"success": True, "account": account, "token_extracted": bool(token)}

        # 查询已有辅料名称，并解析最大编号
        list_url = base_url + "/client/material/material/list"
        existing_names: set = set()
        max_existing_idx = 0
        _name_pattern = re.compile(r"^" + re.escape(base_name) + r"-(\d+)$")

        def _parse_list_items(list_data: Any) -> list:
            """从列表接口响应中提取 items，兼容多种返回格式"""
            if not isinstance(list_data, dict):
                return []
            data = list_data.get("data")
            if isinstance(data, dict):
                return data.get("data") or data.get("list") or data.get("items") or []
            if isinstance(data, list):
                return data
            return []

        # 先不带 name 过滤拉取全量列表（某些接口 name 是精确匹配，模糊搜索需空 name）
        _query_variants = [
            {"page": "1", "pageSize": "500"},
            {"name": "", "page": "1", "pageSize": "500"},
            {"name": base_name, "page": "1", "pageSize": "500"},
        ]
        for query_params in _query_variants:
            try:
                list_resp = client.session.get(list_url, params=query_params, timeout=timeout)
                log.setdefault("list_responses", []).append({
                    "params": dict(query_params),
                    "method": "GET",
                    "status": list_resp.status_code,
                    "body_preview": list_resp.text[:800] if list_resp.ok else list_resp.text[:300],
                })
                if list_resp.ok:
                    list_data = list_resp.json()
                    if list_data.get("success") or list_data.get("code") == 200 or list_data.get("code") == 0:
                        items = _parse_list_items(list_data)
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict) and item.get("name"):
                                    name_text = item["name"]
                                    existing_names.add(name_text)
                                    _m = _name_pattern.match(name_text)
                                    if _m:
                                        max_existing_idx = max(max_existing_idx, int(_m.group(1)))
            except Exception as list_err:
                log.setdefault("list_errors", []).append(f"GET {query_params}: {list_err}")

        # 如果 GET 方式没查到数据，尝试 POST form-data（部分接口只接受 POST）
        if not existing_names:
            _post_variants = [
                {"page": "1", "pageSize": "500"},
                {"name": "", "page": "1", "pageSize": "500"},
                {"name": base_name, "name_trans": "", "type_id": "", "page": "1", "pageSize": "500"},
            ]
            for post_fields in _post_variants:
                try:
                    files = [(k, (None, str(v))) for k, v in post_fields.items()]
                    list_resp = client.session.post(list_url, files=files, timeout=timeout)
                    log.setdefault("list_responses", []).append({
                        "params": dict(post_fields),
                        "method": "POST",
                        "status": list_resp.status_code,
                        "body_preview": list_resp.text[:800] if list_resp.ok else list_resp.text[:300],
                    })
                    if list_resp.ok:
                        list_data = list_resp.json()
                        if list_data.get("success") or list_data.get("code") == 200 or list_data.get("code") == 0:
                            items = _parse_list_items(list_data)
                            if isinstance(items, list):
                                for item in items:
                                    if isinstance(item, dict) and item.get("name"):
                                        name_text = item["name"]
                                        existing_names.add(name_text)
                                        _m = _name_pattern.match(name_text)
                                        if _m:
                                            max_existing_idx = max(max_existing_idx, int(_m.group(1)))
                except Exception as list_err:
                    log.setdefault("list_errors", []).append(f"POST {post_fields}: {list_err}")

        # 从已有最大编号 +1 开始创建
        start_idx = max_existing_idx + 1
        log["existing_count"] = len(existing_names)
        log["max_existing_idx"] = max_existing_idx
        log["start_idx"] = start_idx

        # 循环创建辅料
        created: list = []
        skipped: list = []
        idx = start_idx
        max_iterations = start_idx + count + 200
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 10

        while len(created) < count and idx <= max_iterations and consecutive_failures < MAX_CONSECUTIVE_FAILURES:
            candidate = f"{base_name}-{idx}"
            if candidate in existing_names:
                skipped.append(candidate)
                idx += 1
                continue

            body_obj = {
                "name": candidate,
                "name_trans": candidate,
                "type_id": 1,
                "consume": 1,
                "main_image": "https://rakumart-ps20.oss-ap-northeast-1.aliyuncs.com/dest/202606/265055113/O1CN01nklPMm2KqWS7HYtvi_!!2248919608.jpg",
                "notice": "",
            }
            try:
                create_resp = client.session.post(
                    base_url + "/client/material/material/store",
                    json=body_obj,
                    timeout=timeout,
                )
                if create_resp.ok:
                    create_data = create_resp.json()
                    if create_data.get("success"):
                        created.append({"name": candidate, "id": create_data.get("data", {}).get("id", "")})
                        consecutive_failures = 0
                    else:
                        skipped.append(f"{candidate}({create_data.get('msg', '创建失败')})")
                        consecutive_failures += 1
                else:
                    skipped.append(f"{candidate}(HTTP {create_resp.status_code})")
                    consecutive_failures += 1
            except Exception as fetch_err:
                skipped.append(f"{candidate}(网络错误: {fetch_err})")
                consecutive_failures += 1

            existing_names.add(candidate)
            idx += 1

        passed = len(created) > 0
        reason = ""
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES and len(created) < count:
            reason = f"连续 {MAX_CONSECUTIVE_FAILURES} 次创建失败，已中止。已创建 {len(created)}/{count}"
        elif len(created) < count:
            reason = f"达到最大尝试次数，已创建 {len(created)}/{count}"

        summary: Dict[str, Any] = {
            "material_generation_name": base_name,
            "material_generation_count": count,
            "created_count": len(created),
            "skipped_count": len(skipped),
            "created_list": [c["name"] for c in created],
            "skipped_list": skipped,
            "completed": passed,
        }
        if reason:
            summary["reason"] = reason

        return _finish_named(MATERIAL_GENERATION_SCRIPT_NAME, log, passed, summary)

    except Exception as exc:
        log["error"] = str(exc)
        return _finish_named(
            MATERIAL_GENERATION_SCRIPT_NAME, log, False,
            {"reason": str(exc), "error": str(exc)},
        )


def run_material_generation_script(
    env: Env,
    variables: Dict[str, Any] | None = None,
) -> Tuple[bool, str, str, Dict[str, Any]]:
    _sync_compat_globals()
    return _run_material_generation_script(env, variables)
