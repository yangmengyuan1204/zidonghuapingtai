from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


MoneyDirection = Literal["credit", "debit", "none"]
ExpectedOutcome = Literal["success", "guard"]
IdentityType = Literal["admin", "client"]


@dataclass(frozen=True)
class CaseExpectation:
    outcome: ExpectedOutcome
    direction: MoneyDirection = "none"
    error_codes: tuple[str, ...] = ()
    error_keywords: tuple[str, ...] = ()
    required_identities: tuple[IdentityType, ...] = ()
    expected_stage: str = ""


@dataclass(frozen=True)
class RegressionCaseDefinition:
    key: str
    name: str
    category: str
    runner_kind: str
    parameters: Mapping[str, Any]
    expectation: CaseExpectation
    tags: tuple[str, ...]
    sort_order: int
