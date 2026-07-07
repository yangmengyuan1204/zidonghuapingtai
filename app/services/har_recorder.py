"""HAR 录制解析服务。

将浏览器录制的 HAR 文件解析为接口序列，自动识别动态字段（order_sn/sku 等）
标记为变量，沉淀为可复用流程，后续可在执行弹窗填值回放。
"""

import json
from urllib.parse import urlsplit

# 动态字段名规则集：匹配则标记为变量
DYNAMIC_FIELD_NAMES = {
    "order_sn",
    "sku_list",
    "sku",
    "amount",
    "price",
    "total",
    "serial_number",
    "token",
    "coupon_id",
    "warehouse_city",
    "inquiry_order_sn",
    "large_order_sn",
    "qt_code",
}

# 字段中文 label 映射
FIELD_LABEL_CN = {
    "order_sn": "订单号",
    "sku_list": "SKU列表",
    "sku": "SKU",
    "amount": "金额",
    "price": "价格",
    "total": "总计",
    "serial_number": "序列号",
    "token": "Token",
    "coupon_id": "优惠券ID",
    "warehouse_city": "仓库城市",
    "inquiry_order_sn": "询价单号",
    "large_order_sn": "大订单号",
    "qt_code": "QT编码",
}


def parse_har(har_content: dict) -> list[dict]:
    """解析标准 HAR（spec 1.2/1.3）内容，返回按 startedDateTime 升序排序的步骤列表。"""
    entries = (har_content.get("log") or {}).get("entries") or []
    parsed: list[dict] = []
    for entry in entries:
        request = entry.get("request") or {}
        response = entry.get("response") or {}
        method = request.get("method", "GET")
        url = request.get("url", "")
        query = _pairs_to_dict(request.get("queryString") or [])
        headers = _pairs_to_dict(request.get("headers") or [])
        body = ""
        if method.upper() == "POST":
            post_data = request.get("postData") or {}
            body = post_data.get("text") or ""
        response_status = response.get("status", 0)
        response_body = ""
        content = response.get("content") or {}
        raw_text = content.get("text")
        if raw_text:
            parsed_json = _try_parse_json(raw_text)
            response_body = parsed_json if parsed_json is not None else raw_text
        parsed.append({
            "method": method,
            "url": url,
            "path": _url_to_path(url),
            "query": query,
            "headers": headers,
            "body": body,
            "response_status": response_status,
            "response_body": response_body,
            "started_at": entry.get("startedDateTime", ""),
        })
    parsed.sort(key=lambda x: x["started_at"])
    return parsed


def identify_dynamic_fields(steps: list[dict]) -> dict:
    """识别每个步骤 body 和 query 中的动态字段，生成全局字段 schema 与 body 模板。

    返回: {"fields": [字段 schema 列表], "steps": [每个步骤的 body 模板（含 {{var}} 占位）]}
    """
    fields: dict = {}
    body_templates: list = []

    for step in steps:
        body_raw = step.get("body") or ""
        body_value = _try_parse_json(body_raw)
        if body_value is None:
            body_templates.append(None)
        else:
            body_templates.append(_replace_dynamic(body_value, fields))

        query = step.get("query") or {}
        for key, value in query.items():
            if key in DYNAMIC_FIELD_NAMES and _value_not_empty(value):
                _ensure_field(fields, key)

    return {"fields": list(fields.values()), "steps": body_templates}


def build_flow_definition(parsed_steps: list[dict], dynamic_schema: dict) -> dict:
    """把 parse_har 结果与 identify_dynamic_fields 结果组装成可持久化的流程定义。"""
    field_schema_json = json.dumps(dynamic_schema.get("fields") or [], ensure_ascii=False)
    body_templates = dynamic_schema.get("steps") or []
    steps_def: list[dict] = []
    for idx, step in enumerate(parsed_steps, start=1):
        body_template = body_templates[idx - 1] if idx - 1 < len(body_templates) else None
        body_str = ""
        if body_template is not None:
            body_str = json.dumps(body_template, ensure_ascii=False)
        steps_def.append({
            "step_index": idx,
            "method": step.get("method", "GET"),
            "path": step.get("path", ""),
            "full_url": step.get("url", ""),
            "headers_json": json.dumps(step.get("headers") or {}, ensure_ascii=False),
            "body_template": body_str,
            "field_schema_json": field_schema_json,
        })
    base_url = _infer_base_url(parsed_steps)
    return {"name": "", "description": "", "base_url": base_url, "steps": steps_def}


def _infer_base_url(parsed_steps: list[dict]) -> str:
    """从步骤的完整 url 或 headers 的 referer/origin 推断 API 基地址。"""
    for step in parsed_steps:
        url = step.get("url") or ""
        if url:
            parsed = urlsplit(url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
        headers = step.get("headers") or {}
        for key in ("origin", "referer"):
            val = headers.get(key) or ""
            if val:
                parsed = urlsplit(val)
                if parsed.scheme and parsed.netloc:
                    return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def _url_to_path(url: str) -> str:
    """从完整 URL 中提取 path（去掉 query）。"""
    try:
        return urlsplit(url).path or ""
    except Exception:
        return url


def _pairs_to_dict(pairs: list) -> dict:
    """HAR 中的 headers/queryString 是 [{name, value}] 列表，转 dict。"""
    result: dict = {}
    for item in pairs or []:
        name = item.get("name")
        if not name:
            continue
        result[name] = item.get("value", "")
    return result


def _try_parse_json(text: str):
    """尝试 JSON 解析，失败返回 None。"""
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _value_not_empty(value) -> bool:
    """值非空（None 或空字符串视为空）。"""
    return value is not None and value != ""


def _ensure_field(fields: dict, name: str, original_value=None) -> None:
    """确保字段在 schema 中（已存在则跳过）。sku_list 用 textarea。placeholder 用原值作提示。"""
    if name in fields:
        return
    field_type = "textarea" if name == "sku_list" else "input"
    label = FIELD_LABEL_CN.get(name, name)
    placeholder = f"请输入{label}（原值：{original_value}）" if original_value not in (None, "") else f"请输入{label}"
    fields[name] = {
        "name": name,
        "label": label,
        "type": field_type,
        "required": True,
        "default": "",
        "placeholder": placeholder,
    }


def _replace_dynamic(value, fields: dict):
    """递归处理 body：把动态字段值替换为 {{field_name}}，非动态字段保留原值。"""
    if isinstance(value, dict):
        result = {}
        for key, val in value.items():
            if key in DYNAMIC_FIELD_NAMES and _value_not_empty(val):
                _ensure_field(fields, key, val)
                result[key] = "{{" + key + "}}"
            else:
                result[key] = _replace_dynamic(val, fields)
        return result
    if isinstance(value, list):
        return [_replace_dynamic(item, fields) for item in value]
    return value
