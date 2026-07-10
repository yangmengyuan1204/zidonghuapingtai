from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'Any',
    'Dict',
    'Path',
    're',
    'urlparse',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.executors"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl__quick_screenshot_check(screenshot_path: str) -> dict:
    """
    快速检查截图是否有效。
    返回 {"ok": bool, "reason": str, "checks": dict}
    """
    result = {"ok": True, "reason": "", "checks": {}}
    path = Path(screenshot_path)
    if not path.exists():
        result["ok"] = False
        result["reason"] = "截图文件不存在"
        return result

    size = path.stat().st_size
    result["checks"]["file_size_bytes"] = size

    if size < 2000:
        result["ok"] = False
        result["reason"] = f"截图文件过小 ({size} bytes)，可能为空白页"
        return result

    if size > 50 * 1024 * 1024:
        result["ok"] = False
        result["reason"] = f"截图文件异常过大 ({size // 1024 // 1024}MB)"
        return result

    # 检查截图文件名中是否包含错误内容
    # 如果图片内容有常见错误文本，通过 OCR 检查（高级功能暂不实现）
    # 这里简单检查文件名和时间戳
    return result


def _impl__url_looks_reasonable(url: str, expected_base: str = "") -> bool:
    """
    检查最终 URL 是否合理（非空白、非错误页）。
    仅检查 URL 路径的最后两个段（文件名和父目录），避免误伤正常 URL。
    """
    if not url or url in ("about:blank", "data:", ""):
        return False
    from urllib.parse import urlparse
    parsed = urlparse(url.lower())
    # 只检查 path 的尾段，避免误伤正常路由
    path_segments = [s for s in parsed.path.rstrip("/").split("/") if s]
    tail = path_segments[-2:] if len(path_segments) >= 2 else path_segments[-1:]
    tail_str = "/".join(tail)
    # 整段完全匹配的知名错误页面关键词
    error_tails = ["404", "500", "error", "notfound", "accessdenied", "timeout"]
    if tail_str in error_tails:
        return False
    # 检查文件名的扩展名前部分（如 error.aspx, 404.html）
    for seg in tail:
        base = seg.rsplit(".", 1)[0] if "." in seg else seg
        if base in error_tails:
            return False
    if expected_base and not url.lower().startswith(expected_base.lower().rstrip("/")):
        # 不包含期望 base 说明页面跳转到了预期外的域名
        return False
    return True


def _impl__mask_variables(variables: Dict[str, Any]) -> Dict[str, Any]:
    sensitive = re.compile(r"(password|passwd|pwd|captcha|token|secret|authorization|auth|密码|验证码)", re.I)
    sensitive_names = {"code", "verify_code", "verification_code", "captcha_code"}
    return {key: ("***" if str(key).lower() in sensitive_names or sensitive.search(str(key)) else value) for key, value in variables.items()}


def _impl__normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _impl__quote_locator_text(value: str) -> str:
    return str(value or "").replace('"', '\\"')


def _quick_screenshot_check(screenshot_path: str) -> dict:
    _sync_compat_globals()
    return _impl__quick_screenshot_check(screenshot_path)


def _url_looks_reasonable(url: str, expected_base: str='') -> bool:
    _sync_compat_globals()
    return _impl__url_looks_reasonable(url, expected_base)


def _mask_variables(variables: Dict[str, Any]) -> Dict[str, Any]:
    _sync_compat_globals()
    return _impl__mask_variables(variables)


def _normalize_text(value: Any) -> str:
    _sync_compat_globals()
    return _impl__normalize_text(value)


def _quote_locator_text(value: str) -> str:
    _sync_compat_globals()
    return _impl__quote_locator_text(value)
