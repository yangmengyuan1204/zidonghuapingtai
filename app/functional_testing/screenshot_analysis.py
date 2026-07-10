from __future__ import annotations

import sys


_COMPAT_NAMES = (
    'AiConfig',
    'FunctionalScreenshot',
    'FunctionalTask',
    'call_local_model_json',
    'extract_screenshot_material',
    'fallback_screenshot_analysis',
    'json',
)


def _sync_compat_globals() -> None:
    package = sys.modules["app.functional_testing"]
    sync_legacy = getattr(package, "_sync_legacy_overrides", None)
    if callable(sync_legacy):
        sync_legacy()
    for name in _COMPAT_NAMES:
        globals()[name] = getattr(package, name)


def _impl_analyze_functional_screenshot(task: FunctionalTask, screenshot: FunctionalScreenshot, config: AiConfig | None) -> str:
    material = extract_screenshot_material(screenshot.image_path)
    prompt = f"""
你是资深软件测试工程师。请只根据下面的 OCR/图像结构化材料分析产品截图，不要编造材料中没有的信息。
输出合法 JSON，字段固定为：
{{
  "analysis_source": "ocr_deepseek",
  "page_summary": "页面功能概述",
  "visible_controls": ["可见按钮、输入框、表格、弹窗、状态文案等"],
  "inferred_rules": ["只能从 OCR/区域信息合理推断出的业务规则"],
  "questions_for_product": ["需要产品确认的问题"],
  "suggested_test_points": ["建议测试点"],
  "needs_manual_confirm": true,
  "ocr_confidence": 0.0,
  "low_confidence_items": []
}}

迭代：{task.iteration_name}
目标页面：{task.target_url}
初始需求说明：{task.requirement_text or ""}

OCR/图像材料：
{json.dumps(material, ensure_ascii=False, indent=2)[:30000]}
"""
    try:
        payload = call_local_model_json(config, prompt, timeout=120)
    except Exception as exc:
        return fallback_screenshot_analysis(task, screenshot, str(exc))
    if not isinstance(payload, dict):
        return fallback_screenshot_analysis(task, screenshot, "DeepSeek 未返回合法 JSON")

    normalized = {
        "analysis_source": "ocr_deepseek",
        "page_summary": payload.get("page_summary") or payload.get("summary") or "",
        "visible_controls": payload.get("visible_controls") or payload.get("controls") or [],
        "inferred_rules": payload.get("inferred_rules") or payload.get("rules") or [],
        "questions_for_product": payload.get("questions_for_product") or payload.get("questions") or [],
        "suggested_test_points": payload.get("suggested_test_points") or payload.get("test_points") or [],
        "needs_manual_confirm": bool(payload.get("needs_manual_confirm", material.get("needs_manual_confirm", True))),
        "ocr_confidence": material.get("ocr_confidence", 0),
        "low_confidence_items": material.get("low_confidence_items", []),
        "ocr_material": material,
    }
    return json.dumps(normalized, ensure_ascii=False, indent=2)


def analyze_functional_screenshot(task: FunctionalTask, screenshot: FunctionalScreenshot, config: AiConfig | None) -> str:
    _sync_compat_globals()
    return _impl_analyze_functional_screenshot(task, screenshot, config)
