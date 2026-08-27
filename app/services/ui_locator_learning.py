from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..models import UiCase, UiCaseRevision, UiLocatorMemory


def _steps(case: UiCase) -> list[dict[str, Any]]:
    try:
        value = json.loads(case.steps or "[]")
    except (TypeError, ValueError):
        value = []
    return value if isinstance(value, list) else []


def _profile_identity(case: UiCase, step: dict[str, Any]) -> tuple[str, str]:
    profile = step.get("locator_profile") if isinstance(step, dict) else None
    profile = profile if isinstance(profile, dict) else {}
    fingerprint = profile.get("fingerprint") if isinstance(profile.get("fingerprint"), dict) else {}
    page_key = str(profile.get("page_key") or case.page_url or "")[:500]
    fingerprint_hash = str(fingerprint.get("hash") or "")
    if not fingerprint_hash:
        fingerprint_hash = hashlib.sha256(
            json.dumps(
                {
                    "page_key": page_key,
                    "name": step.get("name"),
                    "action": step.get("action"),
                    "old_locator": step.get("locator"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
    return page_key, fingerprint_hash


def memory_locator_candidates(
    db: Session,
    project_id: int,
    page_key: str,
    fingerprint_hash: str,
) -> list[str]:
    rows = (
        db.query(UiLocatorMemory)
        .filter(
            UiLocatorMemory.project_id == project_id,
            UiLocatorMemory.page_key == page_key,
            UiLocatorMemory.fingerprint_hash == fingerprint_hash,
            UiLocatorMemory.success_count > 0,
        )
        .order_by(UiLocatorMemory.success_count.desc(), UiLocatorMemory.failure_count.asc())
        .all()
    )
    return [row.locator for row in rows if row.locator]


def memory_candidates_for_step(db: Session, case_id: int, step: dict[str, Any]) -> list[str]:
    case = db.get(UiCase, case_id)
    if not case:
        return []
    page_key, fingerprint_hash = _profile_identity(case, step)
    return memory_locator_candidates(db, case.project_id, page_key, fingerprint_hash)


def remember_locator_success(
    db: Session,
    project_id: int,
    page_key: str,
    fingerprint_hash: str,
    locator: str,
    strategy: str,
) -> None:
    now = datetime.now()
    statement = sqlite_insert(UiLocatorMemory).values(
        project_id=project_id,
        page_key=page_key,
        fingerprint_hash=fingerprint_hash,
        locator=locator,
        strategy=strategy,
        success_count=1,
        failure_count=0,
        last_verified_at=now,
        create_time=now,
        update_time=now,
    )
    statement = statement.on_conflict_do_update(
        index_elements=["project_id", "page_key", "fingerprint_hash", "locator"],
        set_={
            "success_count": UiLocatorMemory.success_count + 1,
            "strategy": strategy,
            "last_verified_at": now,
            "update_time": now,
        },
    )
    db.execute(statement)


def confirm_locator_updates(
    db: Session,
    case_id: int,
    updates: list[dict[str, Any]],
    *,
    run_id: str = "",
) -> UiCaseRevision | None:
    case = db.get(UiCase, case_id)
    if not case or not updates:
        return None
    steps = _steps(case)
    original_steps = json.loads(json.dumps(steps, ensure_ascii=False))
    changed: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for update in updates:
        old_locator = str(update.get("old_locator") or "").strip()
        new_locator = str(update.get("new_locator") or "").strip()
        if not old_locator or not new_locator or old_locator == new_locator:
            continue
        raw_index = update.get("step_index")
        indexes = []
        if isinstance(raw_index, int) and 1 <= raw_index <= len(steps):
            indexes = [raw_index - 1]
        else:
            indexes = list(range(len(steps)))
        for index in indexes:
            step = steps[index]
            if not isinstance(step, dict) or step.get("locator") != old_locator:
                continue
            fallback = [
                str(item)
                for item in (step.get("fallback_locators") or [])
                if str(item).strip() and str(item) != new_locator
            ]
            if old_locator not in fallback:
                fallback.insert(0, old_locator)
            step["locator"] = new_locator
            step["fallback_locators"] = fallback
            step["healed_at"] = datetime.now().isoformat()
            changed.append((step, update))
            break
    if not changed:
        return None
    revision = UiCaseRevision(
        case_id=case.id,
        source="auto_heal",
        run_id=run_id or None,
        steps_json=json.dumps(original_steps, ensure_ascii=False),
        create_time=datetime.now(),
    )
    db.add(revision)
    case.steps = json.dumps(steps, ensure_ascii=False)
    for step, update in changed:
        page_key, fingerprint_hash = _profile_identity(case, step)
        new_locator = str(update.get("new_locator") or "")
        remember_locator_success(
            db,
            case.project_id,
            page_key,
            fingerprint_hash,
            new_locator,
            str(update.get("strategy") or "runtime"),
        )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(revision)
    return revision


def rollback_case_revision(db: Session, case_id: int, revision_id: int) -> UiCaseRevision:
    case = db.get(UiCase, case_id)
    revision = db.get(UiCaseRevision, revision_id)
    if not case or not revision or revision.case_id != case_id:
        raise ValueError("用例版本不存在")
    audit = UiCaseRevision(
        case_id=case.id,
        source="rollback",
        run_id=str(revision.id),
        steps_json=json.dumps(_steps(case), ensure_ascii=False),
        create_time=datetime.now(),
    )
    db.add(audit)
    case.steps = revision.steps_json
    db.commit()
    db.refresh(audit)
    return audit
