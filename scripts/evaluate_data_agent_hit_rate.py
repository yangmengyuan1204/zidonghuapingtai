from __future__ import annotations

import argparse
import copy
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import TestRecord  # noqa: E402
from app.services import data_factory_agent as agent_service  # noqa: E402
from app.services.data_factory_agent_intent import reduce_intent_fields  # noqa: E402


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "data_agent_intent_cases.json"


def load_cases() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def expand_explicit_cases(fixture: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    fixture = fixture or load_cases()
    matrix = fixture["explicit_matrix"]
    cases: list[dict[str, Any]] = []
    for target, shape, price in itertools.product(
        matrix["targets"], matrix["shapes"], matrix["prices"]
    ):
        cases.append(
            {
                "id": f"{target['id']}__{shape['id']}__{price['id']}",
                "instruction": matrix["instruction_template"].format(
                    target=target["text"], shape=shape["text"], price=price["text"]
                ),
                "expected": {
                    "target_node": target["target_node"],
                    **copy.deepcopy(shape["expected"]),
                    "pricing": copy.deepcopy(price["expected"]),
                },
            }
        )
    return cases


def explicit_case_matches(result: dict[str, Any], case: dict[str, Any]) -> bool:
    expected = case["expected"]
    goal = result.get("goal") or {}
    variables = goal.get("variables") or {}
    pricing = (goal.get("intent") or {}).get("pricing") or {}
    if result.get("status") != "awaiting_confirmation":
        return False
    if goal.get("target_node") != expected["target_node"]:
        return False
    if variables.get("order_shop_count") != expected["shop_count"]:
        return False
    if variables.get("order_per_shop") != expected["per_shop"]:
        return False
    if variables.get("order_item_num") != expected["quantity"]:
        return False
    expected_pricing = expected["pricing"]
    if pricing.get("mode") != expected_pricing["mode"]:
        return False
    if expected_pricing["mode"] == "goods_total":
        return pricing.get("requested_goods_total") == expected_pricing["amount"]
    effective = pricing.get("effective_unit_prices") or []
    return bool(effective) and set(effective) == {expected_pricing["amount"]}


def expand_fixture_cases(fixture: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    fixture = fixture or load_cases()
    explicit = [{"kind": "explicit", **case} for case in expand_explicit_cases(fixture)]
    fixed = [{"kind": "fixed", **copy.deepcopy(case)} for case in fixture["fixed_cases"]]
    return explicit + fixed


def analyze_without_execution(
    instruction: str,
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    messages = [{"role": "user", "content": str(instruction or "")}]
    intent_state = reduce_intent_fields({}, str(instruction or ""))
    capability_gap = agent_service._unsupported_capability(messages)
    if capability_gap:
        return {
            "status": "blocked",
            "goal": {},
            "question": "",
            "reason": capability_gap["reason"],
            "intent_state": intent_state,
        }
    payload = copy.deepcopy(candidate) if candidate is not None else {
        "status": "ready",
        "goal": {"mode": "new", "target_node": "", "variables": {}},
    }
    status, goal, question = agent_service._normalize_goal(payload, messages)
    return {
        "status": status,
        "goal": goal,
        "question": question,
        "reason": "",
        "intent_state": intent_state,
    }


def fixture_case_matches(result: dict[str, Any], case: dict[str, Any]) -> bool:
    if case.get("kind") == "explicit":
        return explicit_case_matches(result, case)
    if case.get("kind") != "fixed":
        return False
    explanation = f"{result.get('question', '')} {result.get('reason', '')}"
    return (
        result.get("status") == case.get("expected_status")
        and str(case.get("question_contains") or "") in explanation
    )


def tool_record_snapshot_from_rows(rows: Iterable[Any]) -> dict[str, int | None]:
    ids: list[int] = []
    for row in rows:
        try:
            record_id, log_text = row[0], row[1]
            payload = json.loads(log_text) if log_text else {}
        except (IndexError, TypeError, ValueError, json.JSONDecodeError):
            continue
        metadata = payload.get("_exec_meta") if isinstance(payload, dict) else None
        if isinstance(metadata, dict) and metadata.get("kind") == "data_agent_tool":
            ids.append(int(record_id))
    return {"count": len(ids), "max_id": max(ids) if ids else None}


def tool_record_snapshot(db) -> dict[str, int | None]:
    rows = (
        db.query(TestRecord.id, TestRecord.log)
        .filter(TestRecord.log.isnot(None), TestRecord.log.like("%data_agent_tool%"))
        .all()
    )
    return tool_record_snapshot_from_rows(rows)


def _safe_error(exc: Exception) -> str:
    detail = str(getattr(exc, "detail", None) or exc)
    detail = re.sub(r"https?://\S+", "<url>", detail)
    detail = re.sub(r"(?i)(?:bearer\s+|api[_ -]?key[=:]\s*)\S+", "<redacted>", detail)
    return detail[:500]


def _tool_records_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    before_max = int(before.get("max_id") or 0)
    after_max = int(after.get("max_id") or 0)
    return int(after.get("count") or 0) > int(before.get("count") or 0) or after_max > before_max


def evaluate(rounds: int = 3) -> tuple[dict[str, Any], int]:
    if rounds <= 0:
        raise ValueError("rounds 必须是正整数")
    cases = expand_explicit_cases()
    db = SessionLocal()
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    round_results: list[dict[str, Any]] = []
    environment_error = ""
    try:
        before = tool_record_snapshot(db)
        print(json.dumps({"event": "start", "rounds": rounds, "cases_per_round": len(cases), "tool_records_before": before}, ensure_ascii=False), flush=True)
        for round_index in range(1, rounds + 1):
            correct = 0
            failed_case_ids: list[str] = []
            print(json.dumps({"event": "round_start", "round": round_index, "total": len(cases)}, ensure_ascii=False), flush=True)
            for case_index, case in enumerate(cases, start=1):
                instruction = case["instruction"]
                messages = [{"role": "user", "content": instruction}]
                intent_state = agent_service._reduce_intent_state({}, instruction)
                try:
                    status, goal, question, _ = agent_service._analyze_turn(
                        db,
                        messages,
                        intent_state,
                        compile_context={},
                    )
                except Exception as exc:
                    environment_error = _safe_error(exc)
                    raise
                result = {"status": status, "goal": goal, "question": question}
                if explicit_case_matches(result, case):
                    correct += 1
                else:
                    failed_case_ids.append(case["id"])
                if case_index % 10 == 0 or case_index == len(cases):
                    print(
                        json.dumps(
                            {
                                "event": "round_progress",
                                "round": round_index,
                                "completed": case_index,
                                "total": len(cases),
                                "correct_so_far": correct,
                                "failed_case_ids": failed_case_ids,
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
            result = {
                "round": round_index,
                "total": len(cases),
                "correct": correct,
                "rate": correct / len(cases),
                "failed_case_ids": failed_case_ids,
            }
            round_results.append(result)
            print(json.dumps({"event": "round_complete", **result}, ensure_ascii=False), flush=True)
    except Exception:
        pass
    finally:
        try:
            db.rollback()
            after = tool_record_snapshot(db)
        except Exception as exc:
            environment_error = environment_error or _safe_error(exc)
        finally:
            db.close()

    tool_delta = {
        "count": int(after.get("count") or 0) - int(before.get("count") or 0),
        "max_id_before": before.get("max_id"),
        "max_id_after": after.get("max_id"),
    }
    summary = {
        "status": "passed",
        "rounds_requested": rounds,
        "rounds_completed": len(round_results),
        "results": round_results,
        "tool_records_before": before,
        "tool_records_after": after,
        "tool_record_delta": tool_delta,
    }
    if _tool_records_changed(before, after):
        summary["status"] = "tool_record_changed"
        return summary, 3
    if environment_error or len(round_results) != rounds:
        summary["status"] = "environment_unavailable"
        summary["error"] = environment_error or "真实 DeepSeek 评测未完成全部轮次"
        return summary, 2
    if any(float(item["rate"]) < 0.95 for item in round_results):
        summary["status"] = "rate_below_threshold"
        return summary, 1
    return summary, 0


def main() -> int:
    parser = argparse.ArgumentParser(description="真实 DeepSeek 数据智能体首次命中率评测（只分析，不执行工具）")
    parser.add_argument("--rounds", type=int, default=3, help="完整评测轮数，默认 3")
    args = parser.parse_args()
    try:
        summary, exit_code = evaluate(args.rounds)
    except ValueError as exc:
        summary, exit_code = {"status": "invalid_arguments", "error": str(exc)}, 2
    print(json.dumps({"event": "summary", **summary}, ensure_ascii=False), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
