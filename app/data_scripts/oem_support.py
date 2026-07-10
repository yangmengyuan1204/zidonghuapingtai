from __future__ import annotations

import sys
from functools import wraps


OEM_DEFAULT_BASE_URL = "https://oemapi.rakumart.cn"


_COMPAT_NAMES = (
    'OEM_DEFAULT_ADMIN_ORIGIN',
    'OEM_DEFAULT_BASE_URL',
    'OEM_DEFAULT_FRONTEND_ORIGIN',
    'OEM_OSS_BUCKET',
    'OEM_OSS_ENDPOINT',
    '_OEM_MSG_TRANSLATIONS',
    '_OEM_ORDER_TYPE_LABELS',
    '_as_int',
    '_oem_admin_login',
    '_oem_admin_post',
    '_oem_client_login',
    '_oem_get_upload_token',
    '_oem_normalize_goods_class',
    '_oem_order_type_label',
    '_oem_post_json',
    '_oem_query_option_list',
    '_oss_put_object',
    '_step',
    'datetime',
    'json',
    're',
    'requests',
    'time',
    'urljoin',
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


def _impl__oem_post_json(
    session: requests.Session,
    base_url: str,
    path: str,
    body: Dict[str, Any],
    timeout: int,
    token: str | None = None,
    is_admin: bool = False,
    variables: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """OEM 通用 JSON POST 请求，自带 3 次重试。与日本站 multipart form 完全独立。"""
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    origin = (variables or {}).get(
        "backend_manage_origin" if is_admin else "frontend_origin",
        OEM_DEFAULT_ADMIN_ORIGIN if is_admin else OEM_DEFAULT_FRONTEND_ORIGIN,
    )
    headers["Origin"] = origin
    headers["Referer"] = (variables or {}).get(
        "frontend_origin", OEM_DEFAULT_FRONTEND_ORIGIN
    ).rstrip("/") + "/"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = session.post(url, json=body, headers=headers, timeout=timeout)
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except (requests.ConnectionError, requests.Timeout, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"oem request {path} failed after retries: {last_error}")


def _impl__oem_admin_login(session: requests.Session, base_url: str, variables: Dict[str, Any], timeout: int) -> str:
    """OEM 后台登录，返回 access_token。"""
    fields = {
        "username": variables.get("backend_account") or "admin",
        "password": variables.get("backend_password") or "123456",
    }
    payload = _oem_post_json(session, base_url, "/admin/login", fields, timeout, is_admin=True, variables=variables)
    if not payload.get("success") or payload.get("code") not in (0, "0", None):
        raise RuntimeError(f"OEM 后台登录失败: code={payload.get('code')} msg={payload.get('msg')}")
    token = (payload.get("data") or {}).get("access_token")
    if not token:
        raise RuntimeError(f"OEM 后台登录成功但未返回 access_token: {payload}")
    return str(token)


def _impl__oem_client_login(session: requests.Session, base_url: str, variables: Dict[str, Any], timeout: int) -> tuple[str, str, str]:
    """OEM 前台登录，返回 (access_token, user_id, user_info_error)。

    站点接口为 POST /api/login，请求体 {"account","password"}，
    返回 {"code":0,"msg":"操作成功","data":{"access_token":"..."}}，无 success 字段。
    user_id 需调 /api/userInfo 获取（登录响应不含 id）。
    user_info_error 为获取 user_id 时的错误信息（空字符串表示无错误）。
    """
    fields = {
        "account": variables.get("account") or "12345678990",
        "password": variables.get("password") or "123456",
    }
    payload = _oem_post_json(session, base_url, "/api/login", fields, timeout, is_admin=False, variables=variables)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    token = data.get("access_token") or data.get("userToken") or data.get("token")
    if not token:
        raise RuntimeError(f"OEM 前台登录失败: code={payload.get('code')} msg={payload.get('msg')}")

    # 调 /api/userInfo 获取账号 id（样品单号需要，必须带 token）
    user_id = ""
    user_info_error = ""
    try:
        info_payload = _oem_post_json(
            session, base_url, "/api/userInfo", {}, timeout,
            token=token, is_admin=False, variables=variables,
        )
        info_data = info_payload.get("data") if isinstance(info_payload.get("data"), dict) else {}
        user_id = str(info_data.get("id") or info_data.get("user_id") or info_data.get("uid") or "")
        if not user_id:
            # 记录完整响应便于排查字段名差异
            user_info_error = f"userInfo 响应无 id 字段, payload={json.dumps(info_payload, ensure_ascii=False)[:300]}"
    except Exception as exc:
        user_info_error = f"调用 /api/userInfo 失败: {exc}"
    return str(token), user_id, user_info_error


def _impl__oem_get_upload_token(session: requests.Session, base_url: str, client_token: str, timeout: int) -> Dict[str, Any]:
    """调 OEM /common/common/getUploadToken 获取阿里云 OSS STS 临时凭证（需 clienttoken 头）。"""
    url = urljoin(base_url.rstrip("/") + "/", "/common/common/getUploadToken")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "clienttoken": client_token,
        "Origin": OEM_DEFAULT_FRONTEND_ORIGIN,
        "Referer": OEM_DEFAULT_FRONTEND_ORIGIN.rstrip("/") + "/",
    }
    response = session.post(url, json={}, headers=headers, timeout=timeout)
    data = response.json() if response.ok else {}
    if not isinstance(data, dict) or not data.get("success"):
        raise RuntimeError(f"获取 OSS STS 失败: {data}")
    sts = data.get("data") or {}
    if not sts.get("AccessKeyId") or not sts.get("SecurityToken"):
        raise RuntimeError(f"OSS STS 数据不完整: {sts}")
    return sts


def _impl__oss_put_object(sts: Dict[str, Any], bucket: str, endpoint: str, object_key: str, content: bytes, content_type: str) -> str:
    """用 STS 临时凭证签名 PUT 到阿里云 OSS，返回可访问 URL。"""
    import hmac, hashlib, base64
    from email.utils import formatdate
    date = formatdate(usegmt=True)
    # OSS v1 签名 StringToSign: VERB\nContent-MD5\nContent-Type\nDate\nCanonicalizedOSSHeaders\nCanonicalizedResource
    string_to_sign = f"PUT\n\n{content_type}\n{date}\nx-oss-security-token:{sts['SecurityToken']}\n/{bucket}/{object_key}"
    signature = base64.b64encode(
        hmac.new(sts["AccessKeySecret"].encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    url = f"https://{bucket}.{endpoint}/{object_key}"
    headers = {
        "Authorization": f"OSS {sts['AccessKeyId']}:{signature}",
        "Content-Type": content_type,
        "Date": date,
        "x-oss-security-token": sts["SecurityToken"],
    }
    response = requests.put(url, data=content, headers=headers, timeout=30)
    if response.status_code not in (200, 204):
        raise RuntimeError(f"OSS PUT 失败: {response.status_code} {response.text[:200]}")
    return url


def _impl_upload_oem_image(file_name: str, content: bytes, content_type: str, base_url: str = OEM_DEFAULT_BASE_URL) -> str:
    """OEM 图片上传：获取 STS -> PUT 到 OSS -> 返回 OSS URL（getUploadToken 无需登录鉴权）。"""
    session = requests.Session()
    sts = _oem_get_upload_token(session, base_url, "", 30)
    # 构造 object_key: dest/202607/6位随机/文件名
    now = datetime.now()
    month_dir = now.strftime("%Y%m")
    import random, string
    rand_suffix = "".join(random.choices(string.digits, k=6))
    safe_name = (file_name or "upload.png").replace("\\", "/").split("/")[-1]
    object_key = f"dest/{month_dir}/{rand_suffix}/{safe_name}"
    return _oss_put_object(sts, OEM_OSS_BUCKET, OEM_OSS_ENDPOINT, object_key, content, content_type)


def _impl__oem_parse_factory_urls(variables: Dict[str, Any]) -> list:
    """从前端多行文本解析工厂链接列表，兼容旧 factory_url 单值字段。"""
    raw = variables.get("factory_urls")
    if raw and isinstance(raw, list):
        return raw
    if raw and isinstance(raw, str):
        urls = [line.strip() for line in raw.splitlines() if line.strip()]
        if urls:
            return urls
    old = variables.get("factory_url")
    return [old] if old else []


def _impl__oem_extract_factory_iid(factory_url: str) -> str:
    """从 1688 工厂链接解析 memberId 作为 factory_iid。

    支持格式：
    - https://sale.1688.com/factory/card.html?...&memberId=b2b-2216921663537497f8&...
    - https://detail.1688.com/offer/xxx.html?memberId=b2b-xxx
    - 兼容 HTML 编码 &amp; （从页面复制时可能带上）
    - 兼容小写 memberid (1688 不同页面参数写法不同)

    若 URL 不含 memberId 参数，返回空字符串。
    """
    if not factory_url:
        return ""
    # 处理 HTML 编码（&amp; → &），从页面复制可能带上
    url = factory_url.replace('&amp;', '&').replace('&AMP;', '&')
    # 不区分大小写：兼容 memberId / memberid / MEMBERID 等写法
    m = re.search(r'[?&]memberid=([^&#\s]+)', url, re.IGNORECASE)
    return m.group(1) if m else ""


def _impl__translate_oem_msg(msg: Any) -> str:
    """翻译 OEM 后端日文 msg 为中文，未命中则原样返回。"""
    text = str(msg or "").strip()
    if not text:
        return ""
    for jp, cn in _OEM_MSG_TRANSLATIONS.items():
        if jp in text:
            return text.replace(jp, cn)
    return text


def _impl__oem_order_type_label(order_type, variables=None) -> str:
    """根据 body.type 返回单子属性标签（OEM/ODM/FL）。"""
    if variables and str(variables.get("order_type_label") or "").strip():
        return str(variables["order_type_label"]).strip()
    try:
        t = int(order_type or 1)
    except (TypeError, ValueError):
        t = 1
    label = _OEM_ORDER_TYPE_LABELS.get(t)
    if not label:
        label = "OEM"
    return label


def _impl__oem_generate_sample_order_sn(variables=None, user_id="", order_type=1) -> str:
    """生成 OEM 样品单号：Y + 14位时间戳 + - + 账号id + - + 单子属性。

    规则：Y{YYYYMMDDHHMMSS}-{user_id}-{OEM|ODM|FL}
    - user_id: 账号 id（从 /api/userInfo 获取）
    - order_type: 1=OEM, 2=ODM, 3=FL
    允许通过 variables["sample_order_sn"] 自定义覆盖。
    """
    if variables and str(variables.get("sample_order_sn") or "").strip():
        return str(variables["sample_order_sn"]).strip()
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    uid = str(user_id or (variables.get("user_id") if variables else "") or "").strip()
    label = _oem_order_type_label(order_type, variables)
    return f"Y{ts}-{uid}-{label}"


def _impl_fetch_oem_goods_class_list(variables: Dict[str, Any] | None = None) -> list:
    """获取 OEM 商品分类列表（POST /admin/goodsClassList）。

    返回展平后的列表 [{id, class_name, parent_name}, ...]，便于前端下拉渲染。
    """
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), 30)
    base_url = (variables.get("base_url") or OEM_DEFAULT_BASE_URL).rstrip("/")
    session = requests.Session()
    admin_token = _oem_admin_login(session, base_url, variables, timeout)
    payload = _oem_post_json(session, base_url, "/admin/goodsClassList", {}, timeout,
                             token=admin_token, is_admin=True, variables=variables)
    if not payload.get("success"):
        return []
    tree = payload.get("data")
    if not isinstance(tree, list):
        return []
    flat: list = []

    def _flatten(items, parent_name=""):
        for item in items:
            name = item.get("class_name") or ""
            flat.append({"id": item.get("id"), "class_name": name, "parent_name": parent_name})
            childs = item.get("childs") or []
            if childs:
                _flatten(childs, name)

    _flatten(tree)
    return flat


def _impl_fetch_oem_option_list(variables: Dict[str, Any] | None = None) -> list:
    """获取 OEM 大货单可选 option 列表（POST /common/common/optionList，空 body）。"""
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), 30)
    base_url = (variables.get("base_url") or OEM_DEFAULT_BASE_URL).rstrip("/")
    session = requests.Session()
    client_token, user_id, _ = _oem_client_login(session, base_url, variables, timeout)
    return _oem_query_option_list(session, base_url, client_token, timeout, variables)


def _impl_fetch_oem_full_quote(order_sn: str, variables: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """根据询价单号查询 OEM 完整报价详情。

    两步调用：
      1. POST /api/inquiryDetail  → 获取 detail_id 及工厂信息
      2. POST /api/quoteDetail   → 获取完整报价明细
    返回合并后的 data 对象，查询失败时返回空 dict。
    """
    variables = dict(variables or {})
    timeout = _as_int(variables.get("timeout"), 30)
    base_url = (variables.get("base_url") or OEM_DEFAULT_BASE_URL).rstrip("/")

    try:
        session = requests.Session()
        client_token, user_id, _ = _oem_client_login(session, base_url, variables, timeout)

        # 1. 查询询价单基本信息，获取 detail_id
        inquiry_payload = _oem_post_json(
            session, base_url, "/api/inquiryDetail",
            {"order_sn": order_sn}, timeout,
            token=client_token, is_admin=False, variables=variables,
        )
        if not inquiry_payload.get("success") or inquiry_payload.get("code") not in (0, "0", None):
            return {}
        inquiry_data = inquiry_payload.get("data")
        if not isinstance(inquiry_data, dict):
            return {}

        # 提取第一条记录的 id 作为 detail_id
        records = inquiry_data.get("list") or []
        if not isinstance(records, list) or not records:
            return {}
        first = records[0] if isinstance(records[0], dict) else {}
        detail_id = first.get("id") or ""
        inquiry_data["detail_id"] = detail_id

        # 2. 查询完整报价详情
        if detail_id:
            try:
                quote_payload = _oem_post_json(
                    session, base_url, "/api/quoteDetail",
                    {"detail_id": str(detail_id)}, timeout,
                    token=client_token, is_admin=False, variables=variables,
                )
                if quote_payload.get("success") and quote_payload.get("code") in (0, "0", None):
                    quote_data = quote_payload.get("data")
                    if isinstance(quote_data, dict):
                        inquiry_data["quote_detail"] = quote_data
            except Exception:
                pass

        return inquiry_data

    except Exception:
        return {}


def _impl__oem_normalize_goods_class(detail: Dict[str, Any]) -> Any:
    """详情接口返回的 goods_class 是对象 {"id":110,"class_name":"..."}，
    提交给后台的 body 需要 goods_class 为数字 id。原地修改并返回。"""
    gc = detail.get("goods_class")
    if isinstance(gc, dict):
        detail["goods_class"] = gc.get("id")
    return detail


def _impl__oem_query_inquiry_detail(
    session: requests.Session, base_url: str, admin_token: str, order_sn: str, timeout: int, variables: Dict[str, Any]
) -> Dict[str, Any]:
    """查询询价单完整详情（POST /admin/inquiryDetail 不带 point_name）。"""
    payload = _oem_post_json(
        session, base_url, "/admin/inquiryDetail",
        {"order_sn": order_sn}, timeout,
        token=admin_token, is_admin=True, variables=variables,
    )
    if not payload.get("success") and payload.get("code") not in (0, "0", None):
        raise RuntimeError(f"查询询价单详情失败: code={payload.get('code')} msg={payload.get('msg')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"询价单详情数据异常: {payload}")
    _oem_normalize_goods_class(data)
    return data


def _impl__oem_submit_node(
    session: requests.Session, base_url: str, admin_token: str, order_sn: str,
    point_name: str, is_quote: bool, timeout: int, variables: Dict[str, Any],
) -> Dict[str, Any]:
    """节点提交（POST /admin/inquiryDetail 带 point_name）。"""
    body = {"order_sn": order_sn, "is_quote": is_quote, "point_name": point_name}
    return _oem_post_json(session, base_url, "/admin/inquiryDetail", body, timeout,
                          token=admin_token, is_admin=True, variables=variables)


def _impl__oem_admin_post(
    session: requests.Session,
    base_url: str,
    path: str,
    body: Dict[str, Any],
    timeout: int,
    token: str,
    variables: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """OEM 后台 JSON POST，带 Bearer token + admin Origin。"""
    return _oem_post_json(session, base_url, path, body, timeout, token=token, is_admin=True, variables=variables)


def _impl__call_admin_api(
    session: requests.Session,
    base_url: str,
    path: str,
    body: Dict[str, Any],
    timeout: int,
    token: str,
    variables: Dict[str, Any] | None,
    log: Dict[str, Any],
    step_name: str,
) -> Dict[str, Any]:
    """调用后台 API 并记录日志，失败时抛 RuntimeError。"""
    payload = _oem_admin_post(session, base_url, path, body, timeout, token, variables)
    if not payload.get("success") or payload.get("code") not in (0, "0", None):
        _step(log, step_name, payload, {"url": path, "method": "POST"})
        raise RuntimeError(f"{step_name} 失败: {payload.get('msg')}")
    _step(log, step_name, payload, {"url": path, "method": "POST"})
    return payload


def _impl__oem_build_sku_info_from_quote(order_sn: str, session: requests.Session, base_url: str, timeout: int, token: str, variables: Dict[str, Any]) -> list[Dict[str, Any]]:
    """从 samplesDetail 获取当前 SKU 数据，用于 samplesConfirmed 的 quote_info.sku_info。"""
    try:
        detail_payload = _oem_admin_post(session, base_url, "/admin/samplesDetail", {"order_sn": order_sn}, timeout, token, variables)
        data = detail_payload.get("data") or {}
        if isinstance(data, dict):
            skus = data.get("sku_detail") or data.get("skuInfo") or data.get("sku_list") or []
            if not skus and isinstance(data.get("list"), list) and len(data["list"]) > 0:
                skus = data["list"][0].get("sku_detail") or []
        elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            skus = data[0].get("sku_detail") or data
        else:
            skus = []
    except Exception:
        skus = []
    # 从 variables 中读取用户提供的 sku_info 覆盖，否则用查到的数据构造
    user_sku_info = variables.get("quote_sku_info")
    if isinstance(user_sku_info, list) and user_sku_info:
        return user_sku_info
    result = []
    for sku in (skus if isinstance(skus, list) else []):
        if not isinstance(sku, dict):
            continue
        result.append({
            "id": sku.get("id") or sku.get("goods_sku_id") or 0,
            "sku": sku.get("sku") or "",
            "sku_tr": sku.get("sku_tr") or sku.get("sku") or "",
            "sku_image": sku.get("sku_image") or "",
            "num": sku.get("num") or 1,
            "inquiry_samples_price": str(sku.get("inquiry_samples_price") or variables.get("inquiry_samples_price", "0")),
            "inquiry_samples_price_return": str(sku.get("inquiry_samples_price_return") or variables.get("inquiry_samples_price_return", "0")),
            "quote_samples_price": str(sku.get("quote_samples_price") or variables.get("quote_samples_price", "1")),
            "quote_samples_price_return": str(sku.get("quote_samples_price_return") or variables.get("quote_samples_price_return", "0")),
            "real_samples_price": str(sku.get("real_samples_price") or variables.get("real_samples_price", "1")),
            "real_samples_price_return": str(sku.get("real_samples_price_return") or variables.get("real_samples_price_return", "0")),
            "keep_sample_sku_num": int(sku.get("keep_sample_sku_num") or 0),
        })
    if not result:
        # 完全构造默认数据
        num_skus = int(variables.get("sku_count") or 3)
        for i in range(1, num_skus + 1):
            sid = variables.get(f"sku_id_{i}")
            if sid:
                result.append({
                    "id": int(sid),
                    "sku": variables.get(f"sku_{i}", f"SKU{i}"),
                    "sku_tr": variables.get(f"sku_tr_{i}", f"SKU{i}"),
                    "sku_image": "",
                    "num": int(variables.get(f"sku_num_{i}", 1)),
                    "inquiry_samples_price": variables.get(f"inquiry_samples_price_{i}", "0"),
                    "inquiry_samples_price_return": variables.get(f"inquiry_samples_price_return_{i}", "0"),
                    "quote_samples_price": variables.get(f"quote_samples_price_{i}", "1"),
                    "quote_samples_price_return": variables.get(f"quote_samples_price_return_{i}", "0"),
                    "real_samples_price": variables.get(f"real_samples_price_{i}", "1"),
                    "real_samples_price_return": variables.get(f"real_samples_price_return_{i}", "0"),
                    "keep_sample_sku_num": 0,
                })
    return result


def _impl__oem_query_option_list(
    session: requests.Session, base_url: str, token: str, timeout: int, variables: Dict[str, Any]
) -> list:
    """查询 OEM 大货单可选 option 列表（POST /common/common/optionList，空 body）。"""
    payload = _oem_post_json(
        session, base_url, "/common/common/optionList", {}, timeout,
        token=token, is_admin=False, variables=variables,
    )
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # 兼容 {list: [...]} 结构
        inner = data.get("list") or data.get("option_list") or []
        if isinstance(inner, list):
            return inner
    return []


def _impl__oem_generate_large_order_sn(order_sn: str, user_id: str) -> str:
    """按 OEM 前端规则生成大货单号：D{timestamp}-{user_id}-{type}
    其中 type 从询价单号后缀提取（如 OEM、ODM），无法提取时默认为 OEM。
    """
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    type_suffix = "OEM"
    parts = str(order_sn).strip().rsplit("-", 1)
    if len(parts) == 2 and parts[1]:
        type_suffix = parts[1].upper()
    uid = str(user_id) if user_id else "0"
    return f"D{ts}-{uid}-{type_suffix}"


def _impl__oem_order_preview(
    session: requests.Session, base_url: str, token: str,
    detail_id: str, timeout: int, variables: Dict[str, Any], large_order_sn: str = "",
) -> Dict[str, Any]:
    """大货单订单预览（POST /api/orderPreviews，type=2）。"""
    body = {"detail_id": str(detail_id), "type": 2, "large_order_sn": large_order_sn or ""}
    payload = _oem_post_json(
        session, base_url, "/api/orderPreviews", body, timeout,
        token=token, is_admin=False, variables=variables,
    )
    return payload.get("data") if isinstance(payload.get("data"), dict) else {}


def _impl__oem_edit_sku_image(
    session: requests.Session, base_url: str, token: str,
    goods_sku_id: int, sku_image: str, timeout: int, variables: Dict[str, Any],
) -> Dict[str, Any]:
    """编辑 SKU 图片（POST /api/editSkuImage）。"""
    body = {"goods_sku_id": int(goods_sku_id), "sku_image": sku_image}
    payload = _oem_post_json(
        session, base_url, "/api/editSkuImage", body, timeout,
        token=token, is_admin=False, variables=variables,
    )
    return payload


def _impl__oem_create_new_order(
    session: requests.Session, base_url: str, token: str,
    body: Dict[str, Any], timeout: int, variables: Dict[str, Any],
) -> Dict[str, Any]:
    """创建大货单（POST /api/newOrder，type=2）。返回响应 data。"""
    payload = _oem_post_json(
        session, base_url, "/api/newOrder", body, timeout,
        token=token, is_admin=False, variables=variables,
    )
    if not isinstance(payload, dict):
        raise RuntimeError(f"创建大货单失败: 接口返回非 JSON 响应")
    # 兼容两种成功判定：有 success=true，或 code=0/"0"
    is_success = payload.get("success") is True or payload.get("code") in (0, "0")
    if not is_success:
        raise RuntimeError(
            f"创建大货单失败: code={payload.get('code')} msg={payload.get('msg')} "
            f"data={json.dumps(payload.get('data'), ensure_ascii=False)[:500] if payload.get('data') else 'null'}"
        )
    return payload.get("data") if isinstance(payload.get("data"), dict) else (payload or {})


def _impl__oem_build_option_for_sku(
    option_template: list, num: int, large_price: str = "",
) -> list:
    """根据 option 模板和购买数量，生成该 SKU 的 option 数组。
    全部 option 默认 checked=true；num 跟随 SKU 数量（拍照类 price_type=0 固定 1）。
    large_price 为 SKU 级别大货单价（来自 inquiryDetail.sku_detail.large_price），
    OEM 后端要求 option.large_price 必须为该 SKU 的大货单价，而非 option 自身的 price。
    """
    result = []
    for opt in option_template:
        if not isinstance(opt, dict):
            continue
        item = dict(opt)
        # 拍照类 option（id=9 或 name 含"拍照"）固定数量为 1
        opt_id = item.get("id")
        opt_name = str(item.get("name") or "")
        opt_num = 1 if (opt_id == 9 or "拍照" in opt_name) else num
        item["num"] = opt_num
        item["checked"] = True
        # large_price 优先用传入的 SKU 级别大货单价，否则回退到 option 自身 price
        if large_price:
            item["large_price"] = large_price
        elif "large_price" not in item:
            item["large_price"] = item.get("price") or "0.00"
        # price_range 默认空数组
        if "price_range" not in item:
            item["price_range"] = []
        result.append(item)
    return result


def _impl__oem_build_warehouse_for_sku(
    sku_index: int, variables: Dict[str, Any], bulk_images: list,
) -> list:
    """根据变量和图片列表构造 warehouse 数组。
    默认 warehouse_type=1（FBA），FNSKU/ASIN 从变量取，image 取 bulk_images 对应索引。
    """
    warehouse_city = _as_int(variables.get("warehouse_city"), 1)
    # 仓库类型默认 1=FBA，可通过 warehouse_type_N 指定每个 SKU
    warehouse_type = _as_int(variables.get(f"warehouse_type_{sku_index}"), 1)
    fnsku = str(variables.get(f"fnsku_{sku_index}") or variables.get("fnsku") or "").strip()
    asin = str(variables.get(f"asin_{sku_index}") or variables.get("asin") or "").strip()
    image = ""
    if sku_index < len(bulk_images):
        image = bulk_images[sku_index]
    return [{
        "warehouse_type": warehouse_type,
        "FNSKU": fnsku,
        "ASIN": asin,
        "image": image,
    }]


_oem_post_json = _compat_wrapper(_impl__oem_post_json)
_oem_admin_login = _compat_wrapper(_impl__oem_admin_login)
_oem_client_login = _compat_wrapper(_impl__oem_client_login)
_oem_get_upload_token = _compat_wrapper(_impl__oem_get_upload_token)
_oss_put_object = _compat_wrapper(_impl__oss_put_object)
upload_oem_image = _compat_wrapper(_impl_upload_oem_image)
_oem_parse_factory_urls = _compat_wrapper(_impl__oem_parse_factory_urls)
_oem_extract_factory_iid = _compat_wrapper(_impl__oem_extract_factory_iid)
_translate_oem_msg = _compat_wrapper(_impl__translate_oem_msg)
_oem_order_type_label = _compat_wrapper(_impl__oem_order_type_label)
_oem_generate_sample_order_sn = _compat_wrapper(_impl__oem_generate_sample_order_sn)
fetch_oem_goods_class_list = _compat_wrapper(_impl_fetch_oem_goods_class_list)
fetch_oem_option_list = _compat_wrapper(_impl_fetch_oem_option_list)
fetch_oem_full_quote = _compat_wrapper(_impl_fetch_oem_full_quote)
_oem_normalize_goods_class = _compat_wrapper(_impl__oem_normalize_goods_class)
_oem_query_inquiry_detail = _compat_wrapper(_impl__oem_query_inquiry_detail)
_oem_submit_node = _compat_wrapper(_impl__oem_submit_node)
_oem_admin_post = _compat_wrapper(_impl__oem_admin_post)
_call_admin_api = _compat_wrapper(_impl__call_admin_api)
_oem_build_sku_info_from_quote = _compat_wrapper(_impl__oem_build_sku_info_from_quote)
_oem_query_option_list = _compat_wrapper(_impl__oem_query_option_list)
_oem_generate_large_order_sn = _compat_wrapper(_impl__oem_generate_large_order_sn)
_oem_order_preview = _compat_wrapper(_impl__oem_order_preview)
_oem_edit_sku_image = _compat_wrapper(_impl__oem_edit_sku_image)
_oem_create_new_order = _compat_wrapper(_impl__oem_create_new_order)
_oem_build_option_for_sku = _compat_wrapper(_impl__oem_build_option_for_sku)
_oem_build_warehouse_for_sku = _compat_wrapper(_impl__oem_build_warehouse_for_sku)
