from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Dict, Mapping

from .registry import SCRIPT_REGISTRY


ResultValidator = Callable[[Dict[str, Any]], tuple[bool, str]]
Runner = Callable[[Any, Dict[str, Any]], Any]
ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}
ALLOWED_PARAMETER_SOURCES = {
    "natural_language",
    "page_context",
    "environment",
    "default",
}


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    label: str
    value_type: str
    required: bool = False
    default: Any = None
    sources: tuple[str, ...] = (
        "natural_language",
        "page_context",
        "environment",
        "default",
    )

    def validate(self) -> "ParameterSpec":
        if not self.name.strip() or not self.label.strip() or not self.value_type.strip():
            raise ValueError("parameter name, label, and value_type are required")
        if not self.sources or set(self.sources) - ALLOWED_PARAMETER_SOURCES:
            raise ValueError("parameter contains invalid sources")
        return self


@dataclass(frozen=True)
class RiskSpec:
    level: str
    mutating: bool
    second_confirmation: bool

    def validate(self) -> "RiskSpec":
        if self.level not in ALLOWED_RISK_LEVELS:
            raise ValueError("invalid risk level")
        if not self.mutating and self.second_confirmation:
            raise ValueError("read-only capability cannot require second confirmation")
        return self


@dataclass(frozen=True)
class DataScriptCapability:
    key: str
    name: str
    module: str
    projects: tuple[str, ...]
    intents: tuple[str, ...]
    examples: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]
    risk: RiskSpec
    runner: Runner
    result_validator: ResultValidator | None
    account_role: str = ""
    preconditions: tuple[str, ...] = ()
    result_state: str = ""
    resume_key: str = ""
    idempotency_key: str = ""
    agent_enabled: bool = False

    def validate(self) -> "DataScriptCapability":
        if not self.key.strip() or not self.name.strip() or not self.module.strip():
            raise ValueError("capability key, name, and module are required")
        if not callable(self.runner):
            raise ValueError("capability runner is required")
        self.risk.validate()
        if self.risk.mutating and not callable(self.result_validator):
            raise ValueError("mutating capability requires result_validator")
        if not self.projects or not all(str(item).strip() for item in self.projects):
            raise ValueError("capability projects are required")
        if not self.intents or not self.examples:
            raise ValueError("capability intents and examples are required")
        names = [parameter.validate().name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("capability parameter names must be unique")
        return self


CAPABILITIES: Dict[str, DataScriptCapability] = {}


def register_capability(spec: DataScriptCapability) -> None:
    validated = spec.validate()
    CAPABILITIES[validated.key] = validated
    legacy = SCRIPT_REGISTRY.setdefault(validated.key, {})
    legacy.update(
        {
            "name": validated.name,
            "func": validated.runner,
            "capability": validated,
        }
    )


def capability_catalog() -> Mapping[str, DataScriptCapability]:
    return MappingProxyType(dict(CAPABILITIES))


def register_builtin_capabilities() -> None:
    """Registration hook populated incrementally by verified capability groups."""
    return None

