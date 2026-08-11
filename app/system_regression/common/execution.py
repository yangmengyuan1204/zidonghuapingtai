from __future__ import annotations

import json
from typing import Any, Mapping


FINAL_RUN_STATUSES = {"passed", "failed", "blocked", "stopped"}
ACTIVE_RUN_STATUSES = {"pending", "running", "waiting_account"}


def sanitize_secrets(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_secrets(item)
            for key, item in value.items()
            if "password" not in str(key).lower() and "secret" not in str(key).lower()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_secrets(item) for item in value]
    return value


def dump_runtime_json(value: Any) -> str:
    return json.dumps(sanitize_secrets(value), ensure_ascii=False, sort_keys=True, default=str)


__all__ = ["ACTIVE_RUN_STATUSES", "FINAL_RUN_STATUSES", "dump_runtime_json", "sanitize_secrets"]
