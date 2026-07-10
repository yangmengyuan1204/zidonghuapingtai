from __future__ import annotations

import sys
from functools import wraps


_COMPAT_NAMES = (
    "HTTPException",
    "PROXY_ALLOWED_METHODS",
    "PROXY_ALLOW_PRIVATE_URLS",
    "PROXY_MAX_REDIRECTS",
    "_origin",
    "_resolve_and_check_hostname",
    "ipaddress",
    "proxy_ip_is_blocked",
    "requests",
    "socket",
    "status",
    "urljoin",
    "urlparse",
    "validate_proxy_target",
)


def _sync_compat_globals() -> None:
    module = sys.modules["app.core.utils"]
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(module, name)


def _compat_wrapper(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        _sync_compat_globals()
        return func(*args, **kwargs)

    return wrapped


def _impl_proxy_ip_is_blocked(ip_value: str) -> bool:
    ip = ipaddress.ip_address(ip_value)
    return any(
        (
            ip.is_loopback,
            ip.is_private,
            ip.is_link_local,
            ip.is_reserved,
            ip.is_multicast,
            ip.is_unspecified,
        )
    )


def _impl__resolve_and_check_hostname(hostname: str, port: int) -> None:
    """解析 hostname 并检查所有解析到的 IP 是否为内网地址。"""
    try:
        resolved = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return
    for item in resolved:
        address = item[4][0]
        try:
            if proxy_ip_is_blocked(address):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"代理请求禁止访问本机或内网地址 (解析到 {address})",
                )
        except ValueError:
            continue


def _impl_validate_proxy_target(method: str, url: str) -> None:
    if method not in PROXY_ALLOWED_METHODS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的请求方法")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 HTTP/HTTPS URL")
    if not parsed.hostname:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL host 不能为空")
    if PROXY_ALLOW_PRIVATE_URLS:
        return

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".localhost") or hostname.endswith(".local"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理请求禁止访问本机或内网地址")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # 如果 hostname 本身就是 IP，直接检查
    try:
        if proxy_ip_is_blocked(hostname):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="代理请求禁止访问本机或内网地址")
        return
    except ValueError:
        pass

    # 解析 DNS 并检查所有解析到的 IP
    _resolve_and_check_hostname(hostname, port)


def _impl__origin(url: str) -> str:
    """提取 URL 的 origin（scheme + host），用于跨域判断。"""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.hostname.lower()}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"


def _impl_guarded_proxy_request(method: str, url: str, headers: Dict[str, Any], body: str, timeout: int) -> requests.Response:
    current_method = method
    current_url = url
    current_body = body
    original_origin = _origin(current_url)
    request_headers = dict(headers or {})
    for _ in range(PROXY_MAX_REDIRECTS + 1):
        validate_proxy_target(current_method, current_url)
        # 跨域重定向时剥离 Authorization 头（防泄露给第三方）
        redirect_headers = dict(request_headers)
        if _origin(current_url) != original_origin:
            for sensitive_header in {"authorization", "proxy-authorization", "cookie", "x-api-key"}:
                redirect_headers.pop(sensitive_header, None)
                redirect_headers.pop(sensitive_header.title(), None)
        response = requests.request(
            current_method,
            current_url,
            headers=redirect_headers,
            data=current_body,
            timeout=timeout,
            allow_redirects=False,
        )
        if not response.is_redirect:
            return response
        location = response.headers.get("Location")
        if not location:
            return response
        current_url = urljoin(current_url, location)
        if response.status_code in {301, 302, 303}:
            current_method = "GET"
            current_body = ""
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="重定向次数过多")


proxy_ip_is_blocked = _compat_wrapper(_impl_proxy_ip_is_blocked)
_resolve_and_check_hostname = _compat_wrapper(_impl__resolve_and_check_hostname)
validate_proxy_target = _compat_wrapper(_impl_validate_proxy_target)
_origin = _compat_wrapper(_impl__origin)
guarded_proxy_request = _compat_wrapper(_impl_guarded_proxy_request)
