from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..core.utils import data_script_variables
from ..data_scripts.registry import SCRIPT_REGISTRY
from ..models import Env, UiRecordProjectConfig
from .requirement_verification import mask_sensitive_data, redact_sensitive_text


RESET_PATTERN = re.compile(r"\$\{reset\.([A-Za-z0-9_.-]+)\}")


@dataclass
class ResetExecutionResult:
    passed: bool
    raw_outputs: dict[str, Any]
    runtime_variables: dict[str, Any]
    public_report: dict[str, Any]
    error: str = ""


def _flatten_outputs(value: Any, prefix: str, result: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            _flatten_outputs(nested, f"{prefix}.{key}", result)
        return
    result[prefix] = value


def _reset_variable(outputs: dict[str, Any], path: str) -> Any:
    if path in outputs:
        return outputs[path]
    current: Any = outputs
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ValueError(f"缺少数据重置变量：reset.{path}")
    return current


def resolve_reset_templates(value: Any, outputs: dict[str, Any]) -> Any:
    """Resolve strict ``${reset.xxx}`` templates against nested reset outputs."""

    if isinstance(value, dict):
        return {key: resolve_reset_templates(nested, outputs) for key, nested in value.items()}
    if isinstance(value, list):
        return [resolve_reset_templates(item, outputs) for item in value]
    if not isinstance(value, str):
        return value

    matches = list(RESET_PATTERN.finditer(value))
    if not matches:
        return value
    if len(matches) == 1 and matches[0].span() == (0, len(value)):
        return _reset_variable(outputs, matches[0].group(1))

    return RESET_PATTERN.sub(
        lambda match: str(_reset_variable(outputs, match.group(1))),
        value,
    )


def _failure(error: str, *, log_text: Any = "", outputs: Any = None) -> ResetExecutionResult:
    raw_outputs = outputs if isinstance(outputs, dict) else {}
    return ResetExecutionResult(
        passed=False,
        raw_outputs=raw_outputs,
        runtime_variables={},
        public_report={
            "log": redact_sensitive_text(log_text),
            "outputs": mask_sensitive_data(raw_outputs),
        },
        error=redact_sensitive_text(error),
    )


def execute_recording_reset(db: Session, config: UiRecordProjectConfig) -> ResetExecutionResult:
    definition = SCRIPT_REGISTRY.get(str(config.reset_script_key or "").strip())
    runner: Callable[..., Any] | None = definition.get("func") if isinstance(definition, dict) else None
    if not callable(runner):
        return _failure(f"数据重置脚本不存在或未注册：{config.reset_script_key}")

    env = db.get(Env, config.reset_env_id)
    if not env or env.project_id != config.project_id:
        return _failure("数据重置环境不存在或不属于当前项目")

    try:
        reset_variables = json.loads(config.reset_variables_json or "{}")
    except (TypeError, ValueError) as exc:
        return _failure(f"数据重置参数格式错误：{exc}")
    if not isinstance(reset_variables, dict):
        return _failure("数据重置参数必须是对象")

    try:
        prepared = data_script_variables(db, reset_variables, config.project_id)
        passed, log_text, _evidence_path, outputs = runner(env, prepared)
    except Exception as exc:
        return _failure(f"数据重置脚本执行异常：{exc}")

    raw_outputs = outputs if isinstance(outputs, dict) else {}
    runtime_variables: dict[str, Any] = {}
    for key, value in raw_outputs.items():
        _flatten_outputs(value, f"reset.{key}", runtime_variables)
    public_report = {
        "log": redact_sensitive_text(log_text),
        "outputs": mask_sensitive_data(raw_outputs),
    }
    error = "" if passed else redact_sensitive_text(log_text) or "数据重置脚本执行失败"
    return ResetExecutionResult(
        passed=bool(passed),
        raw_outputs=raw_outputs,
        runtime_variables=runtime_variables,
        public_report=public_report,
        error=error,
    )
