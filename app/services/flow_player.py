"""录制流程回放执行服务。

按 step_index 升序执行录制流程的步骤，支持变量替换与跨步骤取值，
自动维护登录态（token），失败即停止。
"""

import json
import re
from typing import Any, Dict, Optional

import requests
from sqlalchemy.orm import Session

from ..models import Env, RecordedFlow, RecordedFlowStep
from .har_recorder import parameterize_headers

# 占位符 {{var}} / {{step_N.data.field}}
_PLACEHOLDER_RE = re.compile(r"\{\{([^}]+)\}\}")
# 跨步骤取值 step_N.data.field
_STEP_REF_RE = re.compile(r"^step_(\d+)\.(.+)$")

# 业务成功码白名单
_BUSINESS_SUCCESS_CODES = {"0", "200", "success", "1"}


def play_flow(flow_id: int, variables: Dict[str, Any], db: Session, skip_on_failure: bool = False) -> Dict[str, Any]:
    """回放指定流程：取流程与步骤 -> 顺序执行 -> 维护登录态 -> 失败即停或跳过。"""
    flow = db.query(RecordedFlow).filter(RecordedFlow.id == flow_id).first()
    if not flow:
        return {"success": False, "completed_steps": [], "failed_step": None, "error": "流程不存在"}
    steps = sorted(flow.steps or [], key=lambda s: s.step_index)
    base_url = _resolve_base_url(variables, db, flow)
    if not base_url:
        return {"success": False, "completed_steps": [], "failed_step": None, "error": "未配置 base_url"}

    session = requests.Session()
    token = ""
    step_results = []
    skipped_steps = []
    for step in steps:
        body_str = _replace_placeholders(step.body_template or "", variables, step_results)
        headers = {
            key: _replace_placeholders(value, variables, step_results)
            for key, value in parameterize_headers(_parse_headers(step.headers_json)).items()
        }
        if token and not _has_auth_header(headers):
            headers["Authorization"] = f"Bearer {token}"
        # 优先用录制时记录的完整 URL，支持多域名回放
        full_url = _replace_placeholders(step.full_url or "", variables, step_results) if step.full_url else ""
        if full_url:
            url = full_url
        else:
            url = base_url.rstrip("/") + "/" + (step.path or "").lstrip("/")
        method = (step.method or "GET").upper()

        try:
            response = _send_request(session, method, url, headers, body_str)
        except Exception as exc:
            if skip_on_failure:
                skipped_steps.append({"step_index": step.step_index, "method": method, "path": step.path, "error": f"请求异常: {exc}"})
                continue
            return {
                "success": False,
                "completed_steps": step_results,
                "failed_step": _step_summary(step),
                "error": f"请求异常: {exc}",
            }
        status_code = response.status_code
        response_body = _try_parse_json(response.text)
        if response_body is None:
            response_body = response.text[:500]

        step_summary = {
            "step_index": step.step_index,
            "method": method,
            "path": step.path,
            "status_code": status_code,
            "response": response_body,
        }

        # 登录态提取
        if _is_login_path(step.path or ""):
            token = _extract_token(response_body)
            if token:
                session.headers.update({"Authorization": f"Bearer {token}"})
        step_results.append(step_summary)

        # 失败判定
        failed = None
        if status_code >= 400:
            failed = f"HTTP 状态码 {status_code}"
        else:
            failed = _check_business_failure(response_body)
        if failed:
            if skip_on_failure:
                skipped_steps.append({"step_index": step.step_index, "method": method, "path": step.path, "error": failed})
                continue
            return {
                "success": False,
                "completed_steps": step_results,
                "failed_step": step_summary,
                "error": failed,
            }
    return {"success": True, "completed_steps": step_results, "skipped_steps": skipped_steps, "failed_step": None, "error": ""}


def _resolve_base_url(variables: Dict[str, Any], db: Session, flow: Optional[RecordedFlow] = None) -> str:
    """优先用 variables.base_url，其次 flow.base_url，最后取最早的 Env。"""
    base = str(variables.get("base_url") or "").strip()
    if base:
        return base
    if flow is not None and flow.base_url:
        return flow.base_url.strip()
    env = db.query(Env).order_by(Env.id.asc()).first()
    return (env.base_url if env else "").strip()


def _parse_headers(headers_json: Optional[str]) -> Dict[str, str]:
    if not headers_json:
        return {}
    try:
        parsed = json.loads(headers_json)
    except (ValueError, TypeError):
        return {}
    return {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}


def _has_auth_header(headers: Dict[str, str]) -> bool:
    return any(key.lower() == "authorization" for key in headers)


def _replace_placeholders(template: str, variables: Dict[str, Any], step_results: list) -> str:
    """替换 body_template 中的 {{var}} 与 {{step_N.data.field}}。"""
    if not template:
        return ""

    def _sub(match: "re.Match[str]") -> str:
        expr = match.group(1).strip()
        step_match = _STEP_REF_RE.match(expr)
        if step_match:
            idx = int(step_match.group(1))
            path = step_match.group(2)
            if 1 <= idx <= len(step_results):
                value = _extract_path(step_results[idx - 1].get("response"), path)
                return "" if value is None else str(value)
            return ""
        if expr in variables:
            value = variables[expr]
            return "" if value is None else str(value)
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_sub, template)


def _extract_path(obj: Any, path: str) -> Any:
    """按点号路径从嵌套对象取值。"""
    cur = obj
    for key in path.split("."):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


def _try_parse_json(text: Any):
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _is_login_path(path: str) -> bool:
    lower = path.lower()
    return "login" in lower


def _extract_token(response_body: Any) -> str:
    """从登录响应中提取 token，参考 data_scripts._extract_token。"""
    if not isinstance(response_body, dict):
        return ""
    data = response_body.get("data")
    if isinstance(data, dict):
        for key in ("userToken", "token", "access_token"):
            value = data.get(key)
            if value:
                return str(value)
    for key in ("userToken", "token", "access_token"):
        value = response_body.get(key)
        if value:
            return str(value)
    return ""


def _check_business_failure(response_body: Any) -> str:
    """业务码失败判定：code 非 0/200/success/1 或 success=false。"""
    if not isinstance(response_body, dict):
        return ""
    code = response_body.get("code")
    if code is not None and str(code) not in _BUSINESS_SUCCESS_CODES:
        return f"业务码失败: code={code}"
    success = response_body.get("success")
    if success is False:
        return "业务返回 success=false"
    return ""


def _step_summary(step: RecordedFlowStep) -> Dict[str, Any]:
    return {
        "step_index": step.step_index,
        "method": step.method,
        "path": step.path,
    }


def _send_request(session: requests.Session, method: str, url: str, headers: Dict[str, str], body_str: str) -> requests.Response:
    """按 body 类型分发请求：dict/list 用 json，纯文本用 data，空 body 不带。"""
    if not body_str:
        return session.request(method, url, headers=headers, timeout=30)
    body = _try_parse_json(body_str)
    if isinstance(body, (dict, list)):
        return session.request(method, url, headers=headers, json=body, timeout=30)
    return session.request(method, url, headers=headers, data=body_str, timeout=30)
