import uuid
import requests
from typing import Any, Dict, Tuple
from .config import get_config
from .http_client import HttpClient
from .exceptions import BusinessException, SystemException


class BaseScript:
    """所有OEM脚本的公共基类，封装通用逻辑"""
    def __init__(self, env: Any, variables: Dict[str, Any]):
        self.env = env
        self.variables = variables or {}
        self.config = get_config()
        self.trace_id = str(uuid.uuid4())
        self.default_timeout = getattr(env, "timeout", None) or self.config.get("oem.timeout", 25)
        self.http_client = HttpClient(trace_id=self.trace_id, default_timeout=self.default_timeout)
        self.session = requests.Session()
        self.base_url = self.config.get("oem.base_url")

    def validate_params(self) -> None:
        """参数校验模板，各脚本重写"""
        pass

    def query(self, path: str, params: Dict[str, Any] = None, method: str = "GET", token: str = None) -> Dict[str, Any]:
        """查询接口请求（自动重试）"""
        return self.http_client.request(path, params, method, is_write=False, token=token)

    def write(self, path: str, data: Dict[str, Any], idempotent_key: str = None, token: str = None) -> Dict[str, Any]:
        """写接口请求（默认不重试，需传幂等键才能重试）"""
        return self.http_client.request(path, data, "POST", is_write=True, token=token, idempotent_key=idempotent_key)

    def success(self, summary: Dict[str, Any]) -> Tuple[bool, str, str, Dict[str, Any]]:
        """统一返回成功结果，和原来的返回结构兼容"""
        return (True, "执行成功", self.trace_id, {"trace_id": self.trace_id, **summary})

    def fail(self, exception: Exception) -> Tuple[bool, str, str, Dict[str, Any]]:
        """统一返回失败结果，和原来的返回结构兼容"""
        if isinstance(exception, BusinessException):
            return (False, exception.msg, self.trace_id, {
                "trace_id": self.trace_id,
                "code": exception.code,
                "msg": exception.detail,
                "error_type": "business"
            })
        elif isinstance(exception, SystemException):
            return (False, exception.msg, self.trace_id, {
                "trace_id": self.trace_id,
                "code": exception.code,
                "msg": exception.msg,
                "trace": exception.trace,
                "error_type": "system"
            })
        else:
            # 兼容原有未封装的异常
            return (False, str(exception), self.trace_id, {
                "trace_id": self.trace_id,
                "msg": str(exception),
                "error_type": "unknown"
            })

    def run(self) -> Tuple[bool, str, str, Dict[str, Any]]:
        """脚本执行入口，子类重写"""
        raise NotImplementedError
