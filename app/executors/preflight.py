from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'ActionTemplate',
    'UiCase',
    '_extract_variables_from_text',
    '_template_match_keywords',
    'json',
    'parse_json_value',
    're',
    'requests',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.executors"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl__template_match_keywords(text: str, keywords: list[str]) -> int:
    """计算文本与关键词列表的匹配分"""
    text_lower = text.lower()
    score = 0
    for kw in keywords:
        kw_lower = kw.lower().strip()
        if not kw_lower:
            continue
        if kw_lower in text_lower:
            score += 10
            if text_lower.startswith(kw_lower) or text_lower.endswith(kw_lower):
                score += 5
    return score


def _impl_match_action_template(
    case_title: str,
    case_steps: str,
    templates: list[ActionTemplate],
) -> ActionTemplate | None:
    """根据用例标题和步骤文本匹配最佳操作模板"""
    if not templates:
        return None
    best_score = 0
    best_template = None
    for template in templates:
        try:
            keywords = json.loads(template.trigger_keywords) if isinstance(template.trigger_keywords, str) else (template.trigger_keywords or [])
        except (json.JSONDecodeError, TypeError):
            keywords = []
        if not keywords:
            continue
        title_score = _template_match_keywords(case_title, keywords) * 2
        steps_score = _template_match_keywords(case_steps or "", keywords)
        total = title_score + steps_score
        if total > best_score:
            best_score = total
            best_template = template
    return best_template if best_score > 0 else None


def _impl__extract_variables_from_text(text: str) -> set[str]:
    if not text:
        return set()
    return set(re.findall(r"\{\{(\w+)\}\}", text))


def _impl_preflight_check(case: UiCase) -> tuple[list[str], list[str]]:
    """执行前预检，返回 (errors, warnings)"""
    errors: list[str] = []
    warnings: list[str] = []

    if not case.steps:
        errors.append("用例没有步骤")
        return errors, warnings

    steps = parse_json_value(case.steps, [])
    if not isinstance(steps, list) or len(steps) == 0:
        errors.append("步骤格式无效或为空")
        return errors, warnings

    page_url = case.page_url or ""
    if page_url:
        try:
            resp = requests.head(page_url, timeout=5, allow_redirects=True)
            if resp.status_code == 405:
                # 部分服务器不支持 HEAD，回退到 GET
                try:
                    resp = requests.get(page_url, timeout=5, allow_redirects=True)
                except Exception:
                    pass
            if resp.status_code >= 500:
                errors.append(f"目标页面返回服务端错误 HTTP {resp.status_code}")
            elif resp.status_code >= 400:
                warnings.append(f"目标页面返回 HTTP {resp.status_code}，可能存在访问问题")
        except requests.ConnectionError:
            errors.append(f"目标页面不可达: {page_url}")
        except Exception as exc:
            warnings.append(f"URL 检查失败: {exc}")

    needed_vars: set[str] = set()
    for step in steps:
        if isinstance(step, dict):
            for field in ("locator", "value", "name"):
                needed_vars |= _extract_variables_from_text(str(step.get(field, "")))

    builtin = {"timestamp", "datetime", "date", "uuid", "random_int", "random_str", "random_phone", "random_email"}
    external_needed = needed_vars - builtin
    if external_needed:
        warnings.append(f"步骤中使用的外部变量（需确保运行时提供）: {', '.join(sorted(external_needed))}")

    try:
        import playwright  # noqa: F401
    except ImportError:
        errors.append("Playwright 未安装，请执行: pip install playwright && python -m playwright install")

    return errors, warnings


def _template_match_keywords(text: str, keywords: list[str]) -> int:
    _sync_compat_globals()
    return _impl__template_match_keywords(text, keywords)


def match_action_template(case_title: str, case_steps: str, templates: list[ActionTemplate]) -> ActionTemplate | None:
    _sync_compat_globals()
    return _impl_match_action_template(case_title, case_steps, templates)


def _extract_variables_from_text(text: str) -> set[str]:
    _sync_compat_globals()
    return _impl__extract_variables_from_text(text)


def preflight_check(case: UiCase) -> tuple[list[str], list[str]]:
    _sync_compat_globals()
    return _impl_preflight_check(case)
