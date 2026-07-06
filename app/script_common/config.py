import os
from typing import Any, Dict


# 全局默认配置
DEFAULT_CONFIG: Dict[str, Any] = {
    "oem": {
        "base_url": "https://oem-test.example.com",
        "timeout": 25,
        "retry_count": 2,
        "write_retry": False,
        "log_level": "INFO"
    },
    "security": {
        "token_desensitize": True,
        "log_truncate_length": 300
    }
}


class ConfigLoader:
    _instance = None
    _config: Dict[str, Any] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def init(self) -> None:
        """初始化配置，后续可扩展加载yaml配置文件"""
        self._config = DEFAULT_CONFIG.copy()

    def get(self, key_path: str, default: Any = None) -> Any:
        """通过点分隔的key获取配置，比如get('oem.base_url')，环境变量优先级最高"""
        if self._config is None:
            self.init()
        
        # 优先读取环境变量
        env_key = key_path.replace(".", "_").upper()
        env_value = os.getenv(env_key)
        if env_value is not None:
            if env_value.isdigit():
                return int(env_value)
            if env_value.lower() in ("true", "false"):
                return env_value.lower() == "true"
            return env_value
        
        # 读取本地配置
        keys = key_path.split(".")
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value if value is not None else default


def get_config() -> ConfigLoader:
    """全局获取配置单例"""
    return ConfigLoader()
