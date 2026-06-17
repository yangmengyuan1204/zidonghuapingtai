"""
Execution service module.

Provides execution-related business logic consolidated from main.py:
- Quality status constants
- Execution gate check and run helpers
- Account resolution during execution
"""

from ..core.utils import (
    QUALITY_AUTH_RISK,
    QUALITY_EXECUTABLE,
    QUALITY_NOT_RECOMMENDED,
    QUALITY_UNCHECKED,
    execute_functional_case_for_run,
    execute_functional_case_for_run_isolated,
    resolve_execution_account,
    save_functional_run,
    save_ui_record,
    can_execute_functional_case,
)

__all__ = [
    "QUALITY_AUTH_RISK",
    "QUALITY_EXECUTABLE",
    "QUALITY_NOT_RECOMMENDED",
    "QUALITY_UNCHECKED",
    "execute_functional_case_for_run",
    "execute_functional_case_for_run_isolated",
    "resolve_execution_account",
    "save_functional_run",
    "save_ui_record",
    "can_execute_functional_case",
]
