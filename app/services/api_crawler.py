"""纯 JS 静态分析爬取服务。

不依赖 Playwright UI 爬取,不依赖接口登录,直接:
1. GET 首页 HTML(不会被 nginx 405)
2. 提取所有 JS 文件 URL(含 prefetch chunk)
3. 逐个下载 JS,加 sleep 间隔避免压垮服务器
4. 正则提取所有 API 路径(E("post",j+"/path") 及裸路径)
5. 去重返回

比 UI 爬取快 10 倍以上,服务器压力极小(只读静态 JS)。
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Set
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

# 每个 JS 文件下载间隔(秒),避免压垮服务器
_JS_INTERVAL = 2.0

# 匹配 E("post",j+"/path") / E("get",j+"/path") 等 axios 封装调用
_E_CALL_PATTERN = re.compile(
    r'E\(["\'](?:post|get|put|delete|POST|GET|PUT|DELETE)["\'],\s*\w+\+["\']([^"\']+)["\']'
)

# 匹配 E("post","/path") 直接路径
_E_DIRECT_PATTERN = re.compile(
    r'E\(["\'](?:post|get|put|delete|POST|GET|PUT|DELETE)["\'],\s*["\']([^"\']+)["\']'
)

# 裸 API 路径:以 / 开头,含点号(如 /config.feedback.list)或多段路径
_API_PATH_PATTERN = re.compile(
    r"""['"`](/(?:api|admin|user|order|product|goods|cart|payment|login|auth|upload|export|report|dashboard|stat|config|system|common|chatManage|aftersale|manage|bill|wms|data|cash|worldFirst|purchaseAdd|problemFinanceCheck|box|urgent|claim|palPal|jpanfirm|client|cost-analysis)[^'"`\s,;)]*)['""]""",
    re.IGNORECASE,
)

# 更宽松:以 / 开头,后跟字母,至少含一个点或多段
_LOOSE_PATH_PATTERN = re.compile(
    r"""['"`](/[a-zA-Z][a-zA-Z0-9_\-]+\.[a-zA-Z0-9_.\-]+)['""]""",
)

# 前台裸路径:无 / 前缀,如 "user.orderList", "order.orderDetail", "cart.goodsCartList"
# 前台 JS 中 API 路径不带 / 前缀,用已知模块名匹配
_FRONT_MODULES = {
    "user", "order", "cart", "address", "balance", "payment", "goods",
    "product", "client", "coupon", "aftersale", "config", "common",
    "logistics", "warehouse", "porder", "spot", "chat", "consult",
    "alibaba", "taobao", "problem", "receive", "box", "inspect",
    "bill", "wms", "data", "purchase", "record", "follow",
    "optionService", "inSale", "jpanfirm", "chatWork", "cash",
    "worldFirst", "purchaseAdd", "claim", "palPal", "urgent",
    "manage", "admin", "api", "system", "stat", "report",
    "dashboard", "upload", "export", "auth", "login",
}
_BARE_PATH_PATTERN = re.compile(
    r"""['"`]([a-zA-Z][a-zA-Z0-9_\-]+\.[a-zA-Z0-9_.\-]+)['""]""",
)

# 静态资源后缀过滤
_STATIC_EXTENSIONS = {
    ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".eot", ".map", ".html", ".htm", ".json",
    ".xml", ".txt", ".pdf", ".zip", ".rar", ".mp4", ".mp3", ".avi",
}

# 无意义路径过滤
_IGNORE_PREFIXES = {
    "/assets/", "/static/", "/public/", "/node_modules/",
}


def _is_api_path(path: str) -> bool:
    """判断是否为有效 API 路径。"""
    if not path or not path.startswith("/"):
        return False
    if len(path) < 3 or len(path) > 150:
        return False
    lower = path.lower()
    if any(lower.endswith(ext) for ext in _STATIC_EXTENSIONS):
        return False
    if any(lower.startswith(p) for p in _IGNORE_PREFIXES):
        return False
    parts = [p for p in path.split("/") if p]
    if parts and all(p.isdigit() for p in parts):
        return False
    return True


def _is_bare_api_path(path: str) -> bool:
    """判断无 / 前缀的裸路径是否为 API 路径(前台专用)。

    前台 JS 中 API 路径如 "user.orderList" 不带 / 前缀,
    需满足:模块名在已知列表中 + 含点号 + 非静态资源。
    """
    if not path or len(path) < 3 or len(path) > 150:
        return False
    if "." not in path:
        return False
    lower = path.lower()
    if any(lower.endswith(ext) for ext in _STATIC_EXTENSIONS):
        return False
    mod = path.split(".")[0]
    return mod in _FRONT_MODULES


def _extract_api_paths(js_content: str) -> Set[str]:
    """从 JS 内容中提取 API 路径。"""
    paths: Set[str] = set()
    # 1. E("post",j+"/path") 模式(最可靠,后台 axios 封装)
    for match in _E_CALL_PATTERN.finditer(js_content):
        path = match.group(1)
        if _is_api_path(path):
            paths.add(path)
    # 2. E("post","/path") 直接路径
    for match in _E_DIRECT_PATTERN.finditer(js_content):
        path = match.group(1)
        if _is_api_path(path):
            paths.add(path)
    # 3. 裸 API 路径(含已知模块前缀,带 / 开头)
    for match in _API_PATH_PATTERN.finditer(js_content):
        path = match.group(1)
        if _is_api_path(path):
            paths.add(path)
    # 4. 宽松兜底:含点号的路径(如 /config.feedback.list)
    for match in _LOOSE_PATH_PATTERN.finditer(js_content):
        path = match.group(1)
        if _is_api_path(path):
            paths.add(path)
    # 5. 前台裸路径:无 / 前缀(如 "user.orderList"),补 / 前缀
    for match in _BARE_PATH_PATTERN.finditer(js_content):
        bare = match.group(1)
        if _is_bare_api_path(bare):
            paths.add("/" + bare)
    return paths


def _find_js_urls(html: str, base_url: str) -> List[str]:
    """从 HTML 中提取所有 JS 文件 URL。

    匹配:
    - <script src="..."> 和 <script data-src="...">
    - <link rel="prefetch" href="xxx.js">
    - <link rel="preload" href="xxx.js">
    """
    js_urls: List[str] = []
    seen: Set[str] = set()

    # script 标签
    for match in re.finditer(r'<script[^>]+(?:src|data-src)=["\']([^"\']+)["\']', html, re.IGNORECASE):
        src = match.group(1)
        full_url = _resolve_js_url(src, base_url)
        if full_url and full_url not in seen:
            seen.add(full_url)
            js_urls.append(full_url)

    # link prefetch/preload JS
    for match in re.finditer(r'<link[^>]+(?:prefetch|preload)[^>]*href=["\']([^"\']+\.js)["\']', html, re.IGNORECASE):
        src = match.group(1)
        full_url = _resolve_js_url(src, base_url)
        if full_url and full_url not in seen:
            seen.add(full_url)
            js_urls.append(full_url)

    # link href 含 .js(prefetch 可能属性顺序不同)
    for match in re.finditer(r'<link[^>]+href=["\']([^"\']+\.js)["\'][^>]*(?:prefetch|preload)', html, re.IGNORECASE):
        src = match.group(1)
        full_url = _resolve_js_url(src, base_url)
        if full_url and full_url not in seen:
            seen.add(full_url)
            js_urls.append(full_url)

    return js_urls


def _resolve_js_url(src: str, base_url: str) -> str:
    """解析 JS URL,过滤外部 CDN。"""
    if src.startswith(("http://", "https://")):
        parsed = urlparse(src)
        base_parsed = urlparse(base_url)
        if parsed.netloc and parsed.netloc != base_parsed.netloc:
            return ""  # 跳过外部 CDN
        return src
    if src.startswith("//"):
        return "https:" + src
    return urljoin(base_url, src)


def _find_chunk_js_urls(js_content: str, base_url: str) -> List[str]:
    """从 JS 内容中找到动态加载的 chunk JS URL。"""
    chunk_pattern = re.compile(r'["\']([^"\']*\.js)["\']', re.IGNORECASE)
    urls: List[str] = []
    seen: Set[str] = set()
    for match in chunk_pattern.finditer(js_content):
        path = match.group(1)
        if path in seen:
            continue
        seen.add(path)
        full_url = _resolve_js_url(path, base_url)
        if full_url:
            urls.append(full_url)
    return urls


def _fetch_url(session: requests.Session, url: str, timeout: int = 20) -> str:
    """下载 URL 内容,失败返回空字符串。"""
    try:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.warning("下载失败 %s: %s", url, exc)
        return ""


def _crawl_one_site(
    site_url: str,
    site_name: str,
    timeout: int = 20,
    max_chunk_depth: int = 1,
) -> Dict[str, Any]:
    """爬取单个站点的 JS,提取接口路径。

    Args:
        site_url: 站点首页 URL
        site_name: "front" 或 "back"
        timeout: 请求超时秒数
        max_chunk_depth: chunk JS 递归深度(0=不递归,1=只下载首页 JS 引用的 chunk)

    Returns:
        {"paths": Set[str], "js_count": int, "js_urls": list, "error": str}
    """
    result: Dict[str, Any] = {"paths": set(), "js_count": 0, "js_urls": [], "error": ""}
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })

    try:
        # 1. 下载首页 HTML
        logger.info("[%s] 下载首页: %s", site_name, site_url)
        html = _fetch_url(session, site_url, timeout=timeout)
        if not html:
            result["error"] = "首页下载失败"
            return result

        # 2. 提取所有 JS URL
        js_urls = _find_js_urls(html, site_url)
        logger.info("[%s] 找到 %d 个 JS 文件", site_name, len(js_urls))
        result["js_urls"] = js_urls

        if not js_urls:
            result["error"] = "HTML 中未找到 JS 文件"
            return result

        # 3. 逐个下载 JS,提取接口路径
        all_chunk_urls: List[str] = []
        for i, js_url in enumerate(js_urls):
            logger.info("[%s] 下载 JS %d/%d: %s", site_name, i + 1, len(js_urls), js_url)
            js_content = _fetch_url(session, js_url, timeout=timeout)
            if js_content:
                result["js_count"] += 1
                paths = _extract_api_paths(js_content)
                result["paths"].update(paths)
                # 收集 chunk JS URL(深度 1)
                if max_chunk_depth > 0:
                    chunk_urls = _find_chunk_js_urls(js_content, site_url)
                    for cu in chunk_urls:
                        if cu not in all_chunk_urls and cu not in js_urls:
                            all_chunk_urls.append(cu)
            # 间隔,避免压垮服务器
            if i < len(js_urls) - 1:
                time.sleep(_JS_INTERVAL)

        # 4. 下载 chunk JS(深度 1)
        if all_chunk_urls:
            logger.info("[%s] 发现 %d 个 chunk JS,开始下载", site_name, len(all_chunk_urls))
            for i, chunk_url in enumerate(all_chunk_urls[:50]):  # 限制最多 50 个 chunk
                logger.info("[%s] 下载 chunk %d/%d: %s", site_name, i + 1, min(len(all_chunk_urls), 50), chunk_url)
                chunk_content = _fetch_url(session, chunk_url, timeout=timeout)
                if chunk_content:
                    result["js_count"] += 1
                    chunk_paths = _extract_api_paths(chunk_content)
                    result["paths"].update(chunk_paths)
                # 间隔
                if i < min(len(all_chunk_urls), 50) - 1:
                    time.sleep(_JS_INTERVAL)

        logger.info("[%s] 共扫描 %d 个 JS,提取 %d 个接口", site_name, result["js_count"], len(result["paths"]))

    except Exception as exc:
        logger.error("[%s] 爬取失败: %s", site_name, exc)
        result["error"] = str(exc)

    return result


def crawl_by_api(
    front_url: str = "",
    front_account: str = "",
    front_password: str = "",
    back_url: str = "",
    back_account: str = "",
    back_password: str = "",
    timeout: int = 20,
) -> Dict[str, Any]:
    """纯 JS 静态分析爬取接口。

    不需要登录,直接下载前端 JS 文件分析。
    账号密码参数保留兼容但不使用。

    Returns:
    {
        "front_endpoints": [...],
        "back_endpoints": [...],
        "all_endpoints": [...],
        "stats": {"front_count", "back_count", "total_count", "js_files_scanned"}
    }
    """
    result: Dict[str, Any] = {
        "front_endpoints": [],
        "back_endpoints": [],
        "all_endpoints": [],
        "stats": {"front_count": 0, "back_count": 0, "total_count": 0, "js_files_scanned": 0},
    }

    # 前台
    front_result: Dict[str, Any] = {"paths": set(), "js_count": 0, "error": ""}
    if front_url:
        front_result = _crawl_one_site(front_url, "front", timeout=timeout)
        if front_result["error"]:
            result["front_error"] = front_result["error"]

    # 后台
    back_result: Dict[str, Any] = {"paths": set(), "js_count": 0, "error": ""}
    if back_url:
        back_result = _crawl_one_site(back_url, "back", timeout=timeout)
        if back_result["error"]:
            result["back_error"] = back_result["error"]

    # 组装结果
    front_paths: Set[str] = front_result["paths"]
    back_paths: Set[str] = back_result["paths"]

    result["front_endpoints"] = sorted(
        [{"method": "POST", "path": p, "source": "front"} for p in front_paths],
        key=lambda x: x["path"],
    )
    result["back_endpoints"] = sorted(
        [{"method": "POST", "path": p, "source": "back"} for p in back_paths],
        key=lambda x: x["path"],
    )
    all_paths = front_paths | back_paths
    result["all_endpoints"] = sorted(
        [{"method": "POST", "path": p, "source": "front" if p in front_paths else "back"} for p in all_paths],
        key=lambda x: x["path"],
    )
    result["stats"] = {
        "front_count": len(front_paths),
        "back_count": len(back_paths),
        "total_count": len(all_paths),
        "js_files_scanned": front_result["js_count"] + back_result["js_count"],
    }

    return result


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    result = crawl_by_api(
        front_url="https://jpweb.rakumart.cn/",
        back_url="https://jpmanage.rakumart.cn",
    )
    print(json.dumps(result["stats"], ensure_ascii=False, indent=2))
    print(f"\n前台接口数: {result['stats']['front_count']}")
    print(f"后台接口数: {result['stats']['back_count']}")
    print(f"总接口数: {result['stats']['total_count']}")
    print(f"扫描 JS 文件数: {result['stats']['js_files_scanned']}")
    print("\n前台接口示例:")
    for ep in result["front_endpoints"][:10]:
        print(f"  {ep['method']} {ep['path']}")
    print("\n后台接口示例:")
    for ep in result["back_endpoints"][:10]:
        print(f"  {ep['method']} {ep['path']}")
