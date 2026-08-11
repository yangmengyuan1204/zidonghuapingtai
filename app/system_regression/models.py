from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint

from app.database import Base


def _load_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


class SystemRegressionSuite(Base):
    __tablename__ = "system_regression_suite"

    id = Column(Integer, primary_key=True, autoincrement=True)
    suite_key = Column(String(80), nullable=False, unique=True, index=True)
    name = Column(String(120), nullable=False)
    default_project_id = Column(Integer, nullable=True)
    default_env_id = Column(Integer, nullable=True)
    default_customer_profile_id = Column(Integer, nullable=True)
    default_business_account_id = Column(Integer, nullable=True)
    default_purchase_account_id = Column(Integer, nullable=True)
    default_finance_account_id = Column(Integer, nullable=True)
    minister_account_profile_id = Column(Integer, nullable=True)
    tolerance_jpy = Column(Integer, nullable=False, default=1)
    ledger_wait_seconds = Column(Integer, nullable=False, default=30)
    timeout_seconds = Column(Integer, nullable=False, default=3600)
    enabled = Column(Boolean, nullable=False, default=True)
    config_json = Column(Text, nullable=False, default="{}")
    create_time = Column(DateTime, nullable=False, default=datetime.now)
    update_time = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    @property
    def config(self) -> dict[str, Any]:
        return _load_json(self.config_json, {})


class SystemRegressionCase(Base):
    __tablename__ = "system_regression_case"
    __table_args__ = (
        UniqueConstraint("suite_id", "case_key", name="uq_system_regression_case_suite_key"),
        Index("ix_system_regression_case_suite_category", "suite_id", "category"),
        Index("ix_system_regression_case_suite_enabled", "suite_id", "enabled"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    suite_id = Column(Integer, ForeignKey("system_regression_suite.id", ondelete="CASCADE"), nullable=False)
    case_key = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)
    category = Column(String(80), nullable=False)
    runner_kind = Column(String(80), nullable=False)
    parameters_json = Column(Text, nullable=False, default="{}")
    expectation_json = Column(Text, nullable=False, default="{}")
    tags_json = Column(Text, nullable=False, default="[]")
    is_system = Column(Boolean, nullable=False, default=True)
    default_definition_json = Column(Text, nullable=False, default="{}")
    version = Column(Integer, nullable=False, default=1)
    user_modified = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, nullable=True)
    updated_by = Column(Integer, nullable=True)
    create_time = Column(DateTime, nullable=False, default=datetime.now)
    update_time = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    @property
    def parameters(self) -> dict[str, Any]:
        return _load_json(self.parameters_json, {})

    @property
    def expectation(self) -> dict[str, Any]:
        return _load_json(self.expectation_json, {})

    @property
    def tags(self) -> list[str]:
        return _load_json(self.tags_json, [])

    @property
    def default_definition(self) -> dict[str, Any]:
        return _load_json(self.default_definition_json, {})


class SystemRegressionBatch(Base):
    __tablename__ = "system_regression_batch"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_no = Column(String(80), nullable=False, unique=True, index=True)
    suite_id = Column(Integer, ForeignKey("system_regression_suite.id"), nullable=False)
    project_id = Column(Integer, nullable=True)
    env_id = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    total_count = Column(Integer, nullable=False, default=0)
    passed_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    blocked_count = Column(Integer, nullable=False, default=0)
    context_json = Column(Text, nullable=False, default="{}")
    stop_requested = Column(Boolean, nullable=False, default=False)
    created_by = Column(Integer, nullable=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    create_time = Column(DateTime, nullable=False, default=datetime.now)
    update_time = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class SystemRegressionCaseRun(Base):
    __tablename__ = "system_regression_case_run"
    __table_args__ = (Index("ix_system_regression_case_run_batch_status", "batch_id", "status"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("system_regression_batch.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(Integer, ForeignKey("system_regression_case.id"), nullable=False)
    case_key = Column(String(100), nullable=False)
    case_version = Column(Integer, nullable=False)
    source_run_id = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    snapshot_json = Column(Text, nullable=False, default="{}")
    resume_stage = Column(String(80), nullable=True)
    order_sn = Column(String(100), nullable=True)
    sorting = Column(String(100), nullable=True)
    porder_sn = Column(String(100), nullable=True)
    problem_goods_id = Column(String(100), nullable=True)
    expected_json = Column(Text, nullable=False, default="{}")
    preview_json = Column(Text, nullable=False, default="{}")
    actual_json = Column(Text, nullable=False, default="{}")
    result_json = Column(Text, nullable=False, default="{}")
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    compat_record_id = Column(Integer, nullable=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    create_time = Column(DateTime, nullable=False, default=datetime.now)
    update_time = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


__all__ = [
    "SystemRegressionBatch",
    "SystemRegressionCase",
    "SystemRegressionCaseRun",
    "SystemRegressionSuite",
]
