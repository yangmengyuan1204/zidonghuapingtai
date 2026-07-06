import time
import requests
import traceback
import uuid
from typing import Any, Dict, Optional
from .config import get_config
from .exceptions import SystemException


class HttpClient:
    def __init__(self, trace_id: str = None, default_timeout: int = None, retry_count: int = None):
        self.trace_id = trace_id or str(uuid4())
        self.config = get_config()
        self.default_timeout = default_timeout or self.config.get("oem.timeout", 25)
        self.retry_count = retry_count or self.config.get("oem.retry_count", 2)
        self.session = requests.Session()

    def _should_retry(self, exception: Exception, is_write: bool, retry_count: int) -> bool:
        """判断是否重试"""
        if is_write:
            # 写接口仅允许网络超时重试，最多重试1次
            return isinstance(exception, (requests.Timeout, ConnectionError)) and retry_count < 1
        # 查询接口允许超时/5xx错误，重试指定次数
        if isinstance(exception, requests.Timeout):
            return retry_count < self.retry_count
        if isinstance(exception, requests.HTTPError) and getattr(exception, 'response', None) and exception.response.status_code >= 500:
            return retry_count < self.retry_count
        return False

    def request(self, path: str, data: Dict[str, Any] = None, method: str = "GET", 
                is_write: bool = False, token: str = None, idempotent_key: str = None) -> Dict[str, Any]:
        """统一请求方法"""
        base_url = self.config.get("oem.base_url").rstrip("/")
        url = f"{base_url}{path}"
        headers = {"X-Trace-Id": self.trace_id}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if is_write and idempotent_key:
            # 写接口增加幂等键
            headers["Idempotent-Key"] = idempotent_key

        retry_count = 0
        while True:
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    params=data if method == "GET" else None,
                    json=data if method != "GET" else None,
                    headers=headers,
                    timeout=self.default_timeout
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                if self._should_retry(e, is_write, retry_count):
                    retry_count += 1
                    time.sleep(0.8)
                    continue
                # 抛系统异常，带完整堆栈
                raise SystemException(3001, f"请求{url}失败: {str(e)}", trace=traceback.format_exc())
