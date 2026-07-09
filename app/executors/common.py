import json
import logging
import random
import re
import shutil
import string
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from ..models import Env


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
REPORT_DIR = BASE_DIR / "reports"
ALLURE_DIR = REPORT_DIR / "allure-results"
SCREENSHOT_DIR = REPORT_DIR / "screenshots"

VAR_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.$-]+)\s*\}\}")


def ensure_report_dirs() -> None:
    ALLURE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def parse_json_value(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        if isinstance(value, str) and len(value) > 0:
            logger.debug("parse_json_value 解析失败，使用 fallback: %s...", value[:200])
        return fallback


def to_json_text(value: Any, fallback: Any) -> str:
    if value is None:
        value = fallback
    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return json.dumps(fallback, ensure_ascii=False)
        try:
            parsed = json.loads(raw)
            return json.dumps(parsed, ensure_ascii=False)
        except json.JSONDecodeError:
            return value
    return json.dumps(value, ensure_ascii=False)


def _epoch_ms(value: Any, fallback: int) -> int:
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    return fallback


def write_allure_result(
    name: str,
    case_type: str,
    passed: bool,
    log_text: str,
    screenshot_path: str = "",
    started_at: Any = None,
    finished_at: Any = None,
) -> str:
    ensure_report_dirs()
    now_ms = int(time.time() * 1000)
    start_ms = _epoch_ms(started_at, now_ms)
    stop_ms = _epoch_ms(finished_at, now_ms)
    result_uuid = str(uuid4())
    status = "passed" if passed else "failed"
    log_source = f"{result_uuid}-log.txt"
    (ALLURE_DIR / log_source).write_text(log_text or "", encoding="utf-8")

    attachments = [{"name": "log", "source": log_source, "type": "text/plain"}]
    if screenshot_path:
        src = Path(screenshot_path)
        if src.exists():
            screenshot_source = f"{result_uuid}-screenshot.png"
            shutil.copyfile(src, ALLURE_DIR / screenshot_source)
            attachments.append({"name": "screenshot", "source": screenshot_source, "type": "image/png"})
        else:
            logger.warning("Allure 报告截图文件不存在: %s", screenshot_path)

    payload = {
        "uuid": result_uuid,
        "name": name,
        "fullName": f"{case_type}.{name}",
        "status": status,
        "stage": "finished",
        "start": start_ms,
        "stop": stop_ms,
        "labels": [{"name": "suite", "value": case_type}],
        "attachments": attachments,
    }
    result_path = ALLURE_DIR / f"{result_uuid}-result.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(result_path)


def json_dump_log(parts: Dict[str, Any]) -> str:
    return json.dumps(parts, ensure_ascii=False, indent=2, default=str)


def builtin_variables() -> Dict[str, Any]:
    now = datetime.now()
    rand = random.randint(100000, 999999)
    uid = str(uuid4())
    generated = {
        "timestamp": int(time.time()),
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "uuid": uid,
        "random_int": rand,
        "random_str": "".join(random.choices(string.ascii_lowercase + string.digits, k=8)),
        "random_phone": f"13{random.randint(100000000, 999999999)}",
        "random_email": f"test_{rand}@example.com",
    }
    generated.update({f"${key}": value for key, value in generated.items()})
    return generated


def render_template(value: Any, variables: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in variables and variables[key] is not None:
                return str(variables[key])
            return ""

        return VAR_PATTERN.sub(replace, value)
    if isinstance(value, list):
        return [render_template(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: render_template(item, variables) for key, item in value.items()}
    return value


def merge_variables(env: Env, runtime_vars: Dict[str, Any] | None = None) -> Dict[str, Any]:
    variables = builtin_variables()
    env_vars = parse_json_value(env.global_vars, {})
    if isinstance(env_vars, dict):
        variables.update(env_vars)
    if runtime_vars:
        variables.update(runtime_vars)
    return variables
