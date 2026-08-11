from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from sqlalchemy.orm import Session

from ..models import TestRecord


DEFAULT_ALLURE_RESULTS_DIR = Path(__file__).resolve().parents[1] / "reports" / "allure-results"


def _allure_execute_time(payload: Dict[str, Any]) -> datetime:
    raw = payload.get("start") or payload.get("stop")
    try:
        return datetime.fromtimestamp(float(raw) / 1000)
    except (TypeError, ValueError, OSError):
        return datetime.now()


def recover_orphan_test_records(
    db: Session,
    report_dir: str | Path = DEFAULT_ALLURE_RESULTS_DIR,
    project_id: int | None = None,
) -> Dict[str, int]:
    root = Path(report_dir).resolve()
    files = sorted(root.glob("*-result.json")) if root.is_dir() else []
    known_paths = {
        str(Path(value).resolve())
        for (value,) in db.query(TestRecord.report_path).filter(TestRecord.report_path.isnot(None)).all()
        if value
    }
    result = {"scanned": len(files), "created": 0, "existing": 0, "skipped": 0}
    for path in files:
        resolved_path = str(path.resolve())
        if resolved_path in known_paths:
            result["existing"] += 1
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            result["skipped"] += 1
            continue
        if not isinstance(payload, dict) or not str(payload.get("name") or "").strip():
            result["skipped"] += 1
            continue
        allure_status = str(payload.get("status") or "unknown").strip().lower()
        log = {
            "script": str(payload.get("name") or "历史执行报告"),
            "mode": "recovered_allure_report",
            "recovered_from_allure": True,
            "allure": {
                "uuid": str(payload.get("uuid") or path.stem.removesuffix("-result")),
                "status": allure_status,
                "full_name": str(payload.get("fullName") or ""),
                "start": payload.get("start"),
                "stop": payload.get("stop"),
                "labels": payload.get("labels") if isinstance(payload.get("labels"), list) else [],
            },
        }
        db.add(
            TestRecord(
                case_type="api",
                case_id=0,
                project_id=project_id,
                result="passed" if allure_status == "passed" else "failed",
                log=json.dumps(log, ensure_ascii=False, default=str),
                screenshot="",
                report_path=resolved_path,
                execute_time=_allure_execute_time(payload),
            )
        )
        known_paths.add(resolved_path)
        result["created"] += 1
    db.commit()
    return result
