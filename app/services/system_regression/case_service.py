from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.database import safe_commit
from app.system_regression.common.catalog import CaseExpectation
from app.system_regression.models import SystemRegressionCase, SystemRegressionCaseRun, SystemRegressionSuite
from app.system_regression.projects.japan.catalog import japan_case_definitions
from app.system_regression.projects.japan.case_keys import (
    LEGACY_CUSTOM_PREFIX,
    REMOVED_DEFAULT_CASE_KEYS,
    case_key_prefix,
)


class CaseServiceError(ValueError):
    pass


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _removed_case_keys(suite: SystemRegressionSuite) -> set[str]:
    config = suite.config if isinstance(suite.config, dict) else {}
    return {str(item).strip() for item in (config.get("removed_case_keys") or []) if str(item).strip()}


def _remember_removed_case_key(suite: SystemRegressionSuite, case_key: str) -> None:
    key = str(case_key or "").strip()
    if not key:
        return
    config = dict(suite.config or {})
    removed = [str(item).strip() for item in (config.get("removed_case_keys") or []) if str(item).strip()]
    if key not in removed:
        removed.append(key)
    config["removed_case_keys"] = removed
    suite.config_json = _dump_json(config)


def _definition_snapshot(case: SystemRegressionCase) -> dict[str, Any]:
    return {
        "name": case.name,
        "category": case.category,
        "runner_kind": case.runner_kind,
        "parameters": case.parameters,
        "expectation": case.expectation,
        "tags": case.tags,
        "enabled": bool(case.enabled),
        "sort_order": case.sort_order,
    }


def _rename_case_key(db: Session, case: SystemRegressionCase, new_key: str) -> None:
    old_key = str(case.case_key or "")
    new_key = str(new_key or "").strip()
    if not new_key or old_key == new_key:
        return
    conflict = (
        db.query(SystemRegressionCase)
        .filter(
            SystemRegressionCase.suite_id == case.suite_id,
            SystemRegressionCase.case_key == new_key,
            SystemRegressionCase.id != case.id,
        )
        .first()
    )
    if conflict is not None:
        raise CaseServiceError(f"编号 {new_key} 已被用例 {conflict.id} 占用，无法从 {old_key} 迁移")
    db.query(SystemRegressionCaseRun).filter(SystemRegressionCaseRun.case_key == old_key).update(
        {"case_key": new_key},
        synchronize_session=False,
    )
    case.case_key = new_key


def _migrate_system_case_keys(db: Session, suite: SystemRegressionSuite) -> None:
    definitions = list(japan_case_definitions())
    system_cases = (
        db.query(SystemRegressionCase)
        .filter(SystemRegressionCase.suite_id == suite.id, SystemRegressionCase.is_system.is_(True))
        .order_by(SystemRegressionCase.sort_order, SystemRegressionCase.id)
        .all()
    )
    if len(system_cases) != len(definitions):
        return
    for case, definition in zip(system_cases, definitions):
        if case.case_key != definition.key:
            _rename_case_key(db, case, definition.key)


def _custom_case_target_prefix(case: SystemRegressionCase) -> str | None:
    key = str(case.case_key or "")
    for legacy_prefix, prefix in LEGACY_CUSTOM_PREFIX.items():
        if key.startswith(f"{legacy_prefix}-"):
            return prefix
    if key.startswith("CUSTOM-"):
        try:
            return case_key_prefix(str(case.category or ""))
        except KeyError:
            return None
    return None


def _migrate_custom_case_keys(db: Session, suite: SystemRegressionSuite) -> None:
    custom_cases = (
        db.query(SystemRegressionCase)
        .filter(SystemRegressionCase.suite_id == suite.id, SystemRegressionCase.is_system.is_(False))
        .order_by(SystemRegressionCase.id)
        .all()
    )
    for case in custom_cases:
        prefix = _custom_case_target_prefix(case)
        if prefix is None:
            continue
        current_prefix = f"{prefix}-"
        key = str(case.case_key or "")
        if key.startswith(current_prefix):
            continue
        _rename_case_key(db, case, _next_custom_key(db, suite.id, prefix))


def _retire_removed_default_cases(db: Session, suite: SystemRegressionSuite) -> None:
    for case in (
        db.query(SystemRegressionCase)
        .filter(
            SystemRegressionCase.suite_id == suite.id,
            SystemRegressionCase.is_system.is_(True),
            SystemRegressionCase.case_key.in_(REMOVED_DEFAULT_CASE_KEYS),
        )
        .all()
    ):
        if case.enabled:
            case.enabled = False
        _remember_removed_case_key(suite, str(case.case_key or ""))


def ensure_japan_suite(
    db: Session,
    *,
    defaults: Mapping[str, Any] | None = None,
) -> SystemRegressionSuite:
    suite = db.query(SystemRegressionSuite).filter(SystemRegressionSuite.suite_key == "japan").first()
    if suite is None:
        values = dict(defaults or {})
        suite = SystemRegressionSuite(
            suite_key="japan",
            name="日本站",
            **{key: value for key, value in values.items() if hasattr(SystemRegressionSuite, key)},
        )
        db.add(suite)
        db.flush()

    _migrate_system_case_keys(db, suite)
    _migrate_custom_case_keys(db, suite)
    _retire_removed_default_cases(db, suite)
    db.flush()

    removed_keys = _removed_case_keys(suite)
    existing_keys = {
        row[0]
        for row in db.query(SystemRegressionCase.case_key)
        .filter(SystemRegressionCase.suite_id == suite.id)
        .all()
    }
    for definition in japan_case_definitions():
        if definition.key in removed_keys:
            continue
        if definition.key in existing_keys:
            existing = (
                db.query(SystemRegressionCase)
                .filter(
                    SystemRegressionCase.suite_id == suite.id,
                    SystemRegressionCase.case_key == definition.key,
                )
                .first()
            )
            if existing is not None and existing.is_system:
                snapshot = {
                    "name": definition.name,
                    "category": definition.category,
                    "runner_kind": definition.runner_kind,
                    "parameters": dict(definition.parameters),
                    "expectation": asdict(definition.expectation),
                    "tags": list(definition.tags),
                    "enabled": True,
                    "sort_order": definition.sort_order,
                }
                existing.default_definition_json = _dump_json(snapshot)
                if not existing.user_modified:
                    existing.name = definition.name
                    existing.category = definition.category
                    existing.runner_kind = definition.runner_kind
                    existing.parameters_json = _dump_json(dict(definition.parameters))
                    existing.expectation_json = _dump_json(asdict(definition.expectation))
                    existing.tags_json = _dump_json(list(definition.tags))
                    existing.sort_order = definition.sort_order
                    existing.enabled = True
                else:
                    expectation = existing.expectation
                    expectation_changed = False
                    if "required_identities" not in expectation:
                        expectation["required_identities"] = list(definition.expectation.required_identities)
                        expectation_changed = True
                    if definition.expectation.expected_stage and "expected_stage" not in expectation:
                        expectation["expected_stage"] = definition.expectation.expected_stage
                        expectation_changed = True
                    if expectation_changed:
                        existing.expectation_json = _dump_json(expectation)
            continue
        expectation = asdict(definition.expectation)
        case = SystemRegressionCase(
            suite_id=suite.id,
            case_key=definition.key,
            name=definition.name,
            category=definition.category,
            runner_kind=definition.runner_kind,
            parameters_json=_dump_json(dict(definition.parameters)),
            expectation_json=_dump_json(expectation),
            tags_json=_dump_json(list(definition.tags)),
            is_system=True,
            enabled=True,
            sort_order=definition.sort_order,
        )
        case.default_definition_json = _dump_json(_definition_snapshot(case))
        db.add(case)
    safe_commit(db)
    db.refresh(suite)
    return suite


def list_cases(
    db: Session,
    *,
    suite_key: str,
    category: str | None = None,
    enabled: bool | None = None,
) -> list[SystemRegressionCase]:
    query = (
        db.query(SystemRegressionCase)
        .join(SystemRegressionSuite, SystemRegressionSuite.id == SystemRegressionCase.suite_id)
        .filter(SystemRegressionSuite.suite_key == suite_key)
    )
    if category is not None:
        query = query.filter(SystemRegressionCase.category == category)
    if enabled is not None:
        query = query.filter(SystemRegressionCase.enabled == enabled)
    return query.order_by(SystemRegressionCase.sort_order, SystemRegressionCase.id).all()


def _get_case(db: Session, case_id: int) -> SystemRegressionCase:
    case = db.query(SystemRegressionCase).filter(SystemRegressionCase.id == case_id).first()
    if case is None:
        raise CaseServiceError("回归用例不存在")
    return case


def update_case(
    db: Session,
    case_id: int,
    changes: Mapping[str, Any],
    *,
    actor_id: int | None,
) -> SystemRegressionCase:
    case = _get_case(db, case_id)
    json_fields = {
        "parameters": "parameters_json",
        "expectation": "expectation_json",
        "tags": "tags_json",
    }
    scalar_fields = {"name", "category", "runner_kind", "enabled", "sort_order"}
    unknown = set(changes) - set(json_fields) - scalar_fields
    if unknown:
        raise CaseServiceError(f"不支持修改字段：{', '.join(sorted(unknown))}")
    for key, value in changes.items():
        if key in json_fields:
            setattr(case, json_fields[key], _dump_json(value))
        else:
            setattr(case, key, value)
    case.version += 1
    case.user_modified = bool(case.is_system)
    case.updated_by = actor_id
    case.update_time = datetime.now()
    safe_commit(db)
    db.refresh(case)
    return case


def _next_custom_key(db: Session, suite_id: int, prefix: str) -> str:
    token = f"{prefix}-"
    nums = []
    for (key,) in db.query(SystemRegressionCase.case_key).filter(SystemRegressionCase.suite_id == suite_id).all():
        text = str(key or "")
        if not text.startswith(token):
            continue
        tail = text[len(token) :]
        if tail.isdigit():
            nums.append(int(tail))
    return f"{prefix}-{max(nums, default=0) + 1:03d}"


def _default_item() -> dict[str, Any]:
    return {
        "sorting": 1,
        "quantity": 1,
        "offer_price": {"value": "10", "currency": "CNY"},
        "offer_freight": {"value": "3", "currency": "CNY"},
        "options": [],
    }


def _default_parameters(kind: str) -> dict[str, Any]:
    part = kind == "part"
    payload = {
        "payment_mode": "balance",
        "payment_plan": "part" if part else "full",
        "order": {
            "item_count": 1,
            "default_quantity": 1,
            "other_fee_name": "",
            "other_fee_amount": {"value": "0", "currency": "CNY"},
        },
        "items": [] if kind == "porder" else [_default_item()],
        "part_pay": {
            "enabled": part,
            "percent": 50,
            "tail_node": "before_shelf",
            "tail_partial": False,
            "tail_sortings": "",
            "fee_timing": {
                "domestic_freight": "first",
                "service_fee": "first",
                "additional_service_fee": "first",
                "other_fee": "first",
            },
        },
        "coupon": {"selectedId": ""},
        "porder": {
            "sku_count": 1,
            "send_num": 1,
            "box_count": 1,
            "box_length": 58,
            "box_width": 51,
            "box_height": 50,
            "box_weight": 10,
            "logistics": "25",
            "price_manual": False,
            "logistics_price": {"value": "0", "currency": "CNY"},
            "extra_name": "",
            "extra_fee": {"value": "0", "currency": "CNY"},
            "payment_mode": "balance",
            "voucher": {"selectedId": ""},
        },
        "ledger_wait_seconds": 30,
    }
    if kind == "problem":
        payload["problem_goods"] = {
            "problem_type": 1,
            "problem_num": 1,
            "problem_description": "系统回归问题产品",
            "translation_content": "システム回帰テスト",
            "pre_num": 2,
            "pre_price": {"value": "9", "currency": "CNY"},
            "pre_freight": {"value": "3", "currency": "CNY"},
            "client_deal_choice": "accept",
            "service_deal_suggest": 2,
            "option_deal_suggest": 2,
            "option_new": [],
            "g_deal_type": "仅退款",
            "business_decision": "系统回归自动处理",
            "purchase_remark": "系统回归",
            "confirm_distribution": True,
        }
    return payload


def create_case(
    db: Session,
    *,
    kind: str,
    name: str,
    actor_id: int | None,
) -> SystemRegressionCase:
    kind = str(kind or "").strip()
    specs = {
        "payment": ("支付", "payment", "order_payment", "新建支付用例", ("支付", "自定义"), "debit", ""),
        "part": ("支付", "payment", "order_part_payment", "新建分批付款", ("支付", "分批", "自定义"), "debit", ""),
        "problem": ("流程", "problem_flow", "problem_flow", "新建问题产品", ("问题产品", "自定义"), "credit", "problem_goods_completed"),
        "porder": ("配送", "porder", "porder_payment", "新建配送单", ("配送单", "自定义"), "debit", ""),
    }
    if kind not in specs:
        raise CaseServiceError("不支持的用例类型")
    suite = ensure_japan_suite(db)
    prefix, category, runner_kind, default_name, tags, direction, expected_stage = specs[kind]
    case_key = _next_custom_key(db, suite.id, prefix)
    expectation = asdict(
        CaseExpectation(
            outcome="success",
            direction=direction,  # type: ignore[arg-type]
            required_identities=("admin", "client"),
            expected_stage=expected_stage,
        )
    )
    case = SystemRegressionCase(
        suite_id=suite.id,
        case_key=case_key,
        name=(name or "").strip() or default_name,
        category=category,
        runner_kind=runner_kind,
        parameters_json=_dump_json(_default_parameters(kind)),
        expectation_json=_dump_json(expectation),
        tags_json=_dump_json(list(tags)),
        is_system=False,
        version=1,
        user_modified=False,
        enabled=True,
        sort_order=10000,
        created_by=actor_id,
        updated_by=actor_id,
    )
    case.default_definition_json = _dump_json(_definition_snapshot(case))
    db.add(case)
    safe_commit(db)
    db.refresh(case)
    return case


def delete_case(db: Session, case_id: int) -> None:
    case = _get_case(db, case_id)
    suite = db.query(SystemRegressionSuite).filter(SystemRegressionSuite.id == case.suite_id).first()
    if suite is None:
        raise CaseServiceError("回归项目不存在")
    if case.is_system:
        _remember_removed_case_key(suite, str(case.case_key or ""))
    db.delete(case)
    safe_commit(db)


def copy_case(db: Session, case_id: int, *, actor_id: int | None) -> SystemRegressionCase:
    source = _get_case(db, case_id)
    prefix = case_key_prefix(str(source.category or ""))
    copied = SystemRegressionCase(
        suite_id=source.suite_id,
        case_key=_next_custom_key(db, source.suite_id, prefix),
        name=f"{source.name}（副本）",
        category=source.category,
        runner_kind=source.runner_kind,
        parameters_json=source.parameters_json,
        expectation_json=source.expectation_json,
        tags_json=source.tags_json,
        is_system=False,
        version=1,
        user_modified=False,
        enabled=source.enabled,
        sort_order=source.sort_order,
        created_by=actor_id,
        updated_by=actor_id,
    )
    copied.default_definition_json = _dump_json(_definition_snapshot(copied))
    db.add(copied)
    safe_commit(db)
    db.refresh(copied)
    return copied


def reset_case(db: Session, case_id: int, *, actor_id: int | None) -> SystemRegressionCase:
    case = _get_case(db, case_id)
    if not case.is_system:
        raise CaseServiceError("自定义用例不支持重置")
    snapshot = case.default_definition
    case.name = snapshot["name"]
    case.category = snapshot["category"]
    case.runner_kind = snapshot["runner_kind"]
    case.parameters_json = _dump_json(snapshot["parameters"])
    case.expectation_json = _dump_json(snapshot["expectation"])
    case.tags_json = _dump_json(snapshot["tags"])
    case.enabled = snapshot["enabled"]
    case.sort_order = snapshot["sort_order"]
    case.version += 1
    case.user_modified = False
    case.updated_by = actor_id
    case.update_time = datetime.now()
    safe_commit(db)
    db.refresh(case)
    return case


__all__ = [
    "CaseServiceError",
    "copy_case",
    "create_case",
    "delete_case",
    "ensure_japan_suite",
    "list_cases",
    "reset_case",
    "update_case",
]
