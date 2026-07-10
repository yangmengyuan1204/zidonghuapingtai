import sys as _sys
import types as _types

from . import _legacy as _legacy_module


_LEGACY_EXPORT_NAMES = tuple(name for name in vars(_legacy_module) if not name.startswith("__"))
_DOMAIN_FUNCTION_NAMES = (
    '_business_variables_from_text',
    '_capture_evidence_screenshot',
    '_case_has_business_assertion',
    '_check_success_condition',
    '_classify_ui_error',
    '_expected_origin',
    '_extract_variables_from_text',
    '_final_business_verification',
    '_first_business_match',
    '_first_runtime_value',
    '_guess_login_url',
    '_heal_locator',
    '_is_generated_sample_value',
    '_is_login_related_step',
    '_locator_candidates',
    '_login_loading_visible',
    '_looks_like_login_page',
    '_looks_like_login_url',
    '_mask_variables',
    '_merge_inferred_business_variables',
    '_merge_locator_values',
    '_normalize_text',
    '_page_text_excerpt',
    '_perform_ui_action',
    '_prepare_authenticated_page',
    '_quick_screenshot_check',
    '_quote_locator_text',
    '_replace_sample_tokens',
    '_resolve_locator',
    '_run_ui_step',
    '_sample_replacement_for_step',
    '_split_locator_values',
    '_stabilize_runtime_steps',
    '_step_has_business_assertion',
    '_step_text',
    '_step_timeout_ms',
    '_strip_leading_login_steps',
    '_template_match_keywords',
    '_text_locator_value',
    '_url_looks_reasonable',
    '_validate_ui_steps_for_execution',
    '_visible_login_error',
    '_wait_after_action',
    '_wait_for_url_contains',
    '_wait_login_submit_settled',
    '_wait_page_stable',
    '_wait_text_contains',
    'execute_ui_case',
    'execute_ui_case_in_page',
    'execute_ui_case_with_deadline',
    'execute_ui_cases_batch',
    'match_action_template',
    'preflight_check',
    'preflight_ui_case',
)
for _name in _LEGACY_EXPORT_NAMES:
    globals()[_name] = getattr(_legacy_module, _name)


def _sync_legacy_overrides() -> None:
    for name in _LEGACY_EXPORT_NAMES:
        if name in globals():
            setattr(_legacy_module, name, globals()[name])


class _ExecutorsModule(_types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name in _LEGACY_EXPORT_NAMES or name in _DOMAIN_FUNCTION_NAMES:
            setattr(_legacy_module, name, value)


_sys.modules[__name__].__class__ = _ExecutorsModule


from .actions import _perform_ui_action, _run_ui_step, _validate_ui_steps_for_execution
from .auth import (
    _business_variables_from_text, _first_business_match, _first_runtime_value,
    _guess_login_url, _is_generated_sample_value, _is_login_related_step,
    _login_loading_visible, _looks_like_login_page, _looks_like_login_url,
    _merge_inferred_business_variables, _prepare_authenticated_page,
    _replace_sample_tokens, _sample_replacement_for_step, _stabilize_runtime_steps,
    _step_text, _strip_leading_login_steps, _visible_login_error,
    _wait_login_submit_settled,
)
from .batch import execute_ui_cases_batch, preflight_ui_case
from .locators import (
    _classify_ui_error, _heal_locator, _locator_candidates, _merge_locator_values,
    _resolve_locator, _split_locator_values, _step_timeout_ms, _text_locator_value,
    _wait_for_url_contains, _wait_page_stable, _wait_text_contains,
)
from .preflight import _extract_variables_from_text, _template_match_keywords, match_action_template, preflight_check
from .runtime import execute_ui_case, execute_ui_case_in_page, execute_ui_case_with_deadline
from .screenshots import _mask_variables, _normalize_text, _quick_screenshot_check, _quote_locator_text, _url_looks_reasonable
from .verification import (
    _capture_evidence_screenshot, _case_has_business_assertion,
    _check_success_condition, _expected_origin, _final_business_verification,
    _page_text_excerpt, _step_has_business_assertion, _wait_after_action,
)

for _name in _DOMAIN_FUNCTION_NAMES:
    setattr(_legacy_module, _name, globals()[_name])


del _name
