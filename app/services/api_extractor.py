"""静态接口提取服务。

扫描 app/data_scripts/ 下所有脚本,用正则提取接口调用(method/path/来源/上下文),
组装成接口清单供 AI 生成测试用例。不执行脚本,只做静态文本分析。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from ..data_scripts.registry import SCRIPT_REGISTRY

# data_scripts 目录
_DATA_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "data_scripts"

# 接口路径正则:以 / 开头,后跟 字母/数字/下划线/点/连字符,至少含一个点(如 /bill.adjustApplication.list)
# 或 / 开头的多段路径(如 /api/admin/login)
_PATH_PATTERN = re.compile(r"""
    (?:_api_path\([^,]+,\s*["'][^"']+["']\s*,\s*|   # _api_path(variables, "key", "/path")
     urljoin\([^,]+,\s*|                              # urljoin(base_url, "/path")
     session\.(?:post|get)\(\s*)                      # session.post("/path"
    ["']                                               # 引号开始
    (/[A-Za-z0-9_./\-]+)                               # 捕获路径
    ["']
""", re.VERBOSE)

# 直接出现的接口路径字符串(兜底:路径含点且以 / 开头)
_BARE_PATH_PATTERN = re.compile(r"['\"](/[A-Za-z0-9_\-]+\.[A-Za-z0-9_.\-]+)['\"]")

# method 上下文:只认明确的 session.get 为 GET,排除 dict.get 等干扰
_SESSION_GET_PATTERN = re.compile(r"session\s*\.\s*get\s*\(")

# 脚本 key → 中文名映射
_SCRIPT_NAMES = {key: meta.get("name", key) for key, meta in SCRIPT_REGISTRY.items()}


def extract_all() -> Dict[str, Any]:
    """扫描所有 data_scripts,返回接口清单。

    返回结构:
    {
      "scripts": [
        {"script_key": "balance_adjustment", "script_name": "余额调整",
         "file": "balance_adjustment.py",
         "endpoints": [{"method":"POST","path":"/...","context":"..."}]}
      ],
      "unique_endpoints": [{"method":"POST","path":"/...","used_in":["balance_adjustment"]}]
    }
    """
    scripts: List[Dict[str, Any]] = []
    endpoint_usage: Dict[str, List[str]] = {}

    py_files = sorted(_DATA_SCRIPTS_DIR.glob("*.py"))
    # oem 子目录
    oem_dir = _DATA_SCRIPTS_DIR / "oem"
    if oem_dir.is_dir():
        py_files.extend(sorted(oem_dir.glob("*.py")))

    for py_file in py_files:
        if py_file.name in ("__init__.py", "registry.py", "capabilities.py"):
            continue
        script_key = _infer_script_key(py_file)
        endpoints = _extract_from_file(py_file)
        if not endpoints:
            continue
        # 去重(同文件内同 path+method 只保留一次)
        seen = set()
        unique_endpoints = []
        for ep in endpoints:
            key = f"{ep['method']}:{ep['path']}"
            if key in seen:
                continue
            seen.add(key)
            unique_endpoints.append(ep)
            usage_key = f"{ep['method']}:{ep['path']}"
            endpoint_usage.setdefault(usage_key, [])
            if script_key and script_key not in endpoint_usage[usage_key]:
                endpoint_usage[usage_key].append(script_key)

        scripts.append({
            "script_key": script_key or py_file.stem,
            "script_name": _SCRIPT_NAMES.get(script_key, py_file.stem),
            "file": py_file.name,
            "endpoints": unique_endpoints,
        })

    # 构建去重接口列表
    unique_endpoints: List[Dict[str, Any]] = []
    seen_paths = set()
    for ep_key, used_in in sorted(endpoint_usage.items()):
        method, path = ep_key.split(":", 1)
        if path in seen_paths:
            continue
        seen_paths.add(path)
        unique_endpoints.append({"method": method, "path": path, "used_in": used_in})

    return {
        "scripts": scripts,
        "unique_endpoints": unique_endpoints,
        "stats": {
            "script_count": len(scripts),
            "endpoint_count": len(unique_endpoints),
        },
    }


def _infer_script_key(py_file: Path) -> str | None:
    """从文件名推断 script_key。oem 子目录加 oem_ 前缀。"""
    stem = py_file.stem
    if py_file.parent.name == "oem":
        return f"oem_{stem}"
    return stem


def _extract_from_file(py_file: Path) -> List[Dict[str, Any]]:
    """从单个文件提取接口调用。"""
    try:
        text = py_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    lines = text.splitlines()
    results: List[Dict[str, Any]] = []

    # 1. 匹配带上下文的接口调用(_api_path/urljoin/session.post+path)
    for match in _PATH_PATTERN.finditer(text):
        path = match.group(1)
        if not _is_api_path(path):
            continue
        # 找行号和上下文
        pos = match.start()
        line_no = text.count("\n", 0, pos) + 1
        context_line = lines[line_no - 1].strip() if line_no - 1 < len(lines) else ""
        method = _infer_method(text, pos)
        results.append({
            "method": method,
            "path": path,
            "line": line_no,
            "context": context_line[:200],
        })

    # 2. 兜底:裸接口路径字符串(含点的路径,如 /bill.adjustApplication.list)
    for match in _BARE_PATH_PATTERN.finditer(text):
        path = match.group(1)
        if not _is_api_path(path):
            continue
        pos = match.start()
        line_no = text.count("\n", 0, pos) + 1
        context_line = lines[line_no - 1].strip() if line_no - 1 < len(lines) else ""
        method = _infer_method(text, pos)
        ep_key = f"{method}:{path}"
        if any(f"{r['method']}:{r['path']}" == ep_key for r in results):
            continue
        results.append({
            "method": method,
            "path": path,
            "line": line_no,
            "context": context_line[:200],
        })

    return results


def _is_api_path(path: str) -> bool:
    """判断是否为有效接口路径:以 / 开头,长度合理,非纯静态资源。"""
    if not path or not path.startswith("/"):
        return False
    if len(path) < 2 or len(path) > 100:
        return False
    # 过滤掉静态资源
    lower = path.lower()
    if any(lower.endswith(ext) for ext in (".js", ".css", ".png", ".jpg", ".html", ".ico")):
        return False
    return True


def _infer_method(text: str, pos: int) -> str:
    """根据调用位置上下文推断 HTTP method。

    项目以 POST 表单为主,只有明确看到 session.get 才标 GET,否则默认 POST。
    """
    # 向前取 500 字符窗口,找最近的 session.get(
    window_start = max(0, pos - 500)
    window = text[window_start:pos]
    if _SESSION_GET_PATTERN.search(window):
        return "GET"
    return "POST"


__all__ = ["extract_all"]
