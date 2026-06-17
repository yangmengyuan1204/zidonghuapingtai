"""轻量内存 TTL 缓存 — 减少重复数据库查询。

使用场景：项目列表、环境列表、当前用户信息等低频变更、高频读取的数据。
缓存过期后自动失效，写操作（增/删/改）主动清除对应缓存条目。
"""

import time
from typing import Any


_cache: dict[str, tuple[float, Any, float]] = {}


# ─── 公开 API ─────────────────────────────────────────────


def get(key: str) -> Any:
    """获取缓存值，过期或不存在返回 None。"""
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, value, ttl = entry
    if time.time() - ts > ttl:
        _cache.pop(key, None)
        return None
    return value


def set(key: str, value: Any, ttl: float = 30) -> None:
    """写入缓存，ttl 单位为秒。"""
    _cache[key] = (time.time(), value, ttl)


def invalidate(key: str) -> None:
    """精确清除一个缓存键。"""
    _cache.pop(key, None)


def invalidate_prefix(prefix: str) -> None:
    """清除所有指定前缀的缓存键。"""
    for key in list(_cache.keys()):
        if key.startswith(prefix):
            _cache.pop(key, None)
