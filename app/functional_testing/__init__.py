import sys as _sys
import types as _types

from . import _legacy as _legacy_module

_LEGACY_EXPORT_NAMES = tuple(name for name in vars(_legacy_module) if not name.startswith("__"))
_DOMAIN_FUNCTION_NAMES = (
    '_attach_login_network_trace',
    '_auth_storage_snapshot',
    '_basic_generate_ui_steps',
    '_check_keep_login',
    '_clean_text_locator_value',
    '_click_first_available',
    '_click_login_submit',
    '_click_text_locator',
    '_element_text',
    '_extract_json_list_field',
    '_failure_reason_and_actions',
    '_fill_auto_input',
    '_fill_first_available',
    '_has_visible_locator',
    '_infer_failed_step',
    '_input_meta',
    '_is_login_response',
    '_load_action_templates',
    '_load_json_object',
    '_locator_candidates',
    '_locator_from_error',
    '_login_before_scan',
    '_looks_like_login_page',
    '_match_template_for_case',
    '_normalize_generated_cases',
    '_page_available_for_screenshot',
    '_redacted_response_summary',
    '_request_failure_text',
    '_safe_page_evaluate',
    '_safe_url_label',
    '_scan_error',
    '_scan_extract_dom',
    '_scan_launch',
    '_scan_locator_quality',
    '_scan_navigate',
    '_scan_page_state',
    '_scan_screenshot',
    '_scan_trace',
    '_score_input',
    '_step_text',
    '_step_timeout',
    '_wait_after_login_submit',
    'analyze_functional_screenshot',
    'diagnose_failure',
    'generate_functional_cases',
    'generate_ui_steps',
    'normalize_case_category',
    'rule_diagnose_failure',
    'rule_generate_cases',
    'rule_generate_ui_steps',
    'scan_page_dom',
    'validate_ui_steps',
)
for _name in _LEGACY_EXPORT_NAMES:
    globals()[_name] = getattr(_legacy_module, _name)

def _sync_legacy_overrides() -> None:
    for name in _LEGACY_EXPORT_NAMES:
        if name in globals():
            setattr(_legacy_module, name, globals()[name])

class _FunctionalTestingModule(_types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name in _LEGACY_EXPORT_NAMES or name in _DOMAIN_FUNCTION_NAMES:
            setattr(_legacy_module, name, value)

_sys.modules[__name__].__class__ = _FunctionalTestingModule

from .case_generation import (_extract_json_list_field, _normalize_generated_cases, generate_functional_cases, normalize_case_category, rule_generate_cases)
from .diagnosis import (_failure_reason_and_actions, _infer_failed_step, _load_json_object, _locator_from_error, _step_text, diagnose_failure, rule_diagnose_failure)
from .scanner import (
    _attach_login_network_trace, _auth_storage_snapshot, _check_keep_login, _clean_text_locator_value,
    _click_first_available, _click_login_submit, _click_text_locator, _element_text, _fill_auto_input,
    _fill_first_available, _has_visible_locator, _input_meta, _is_login_response, _locator_candidates,
    _login_before_scan, _looks_like_login_page, _page_available_for_screenshot, _redacted_response_summary,
    _request_failure_text, _safe_page_evaluate, _safe_url_label, _scan_error, _scan_extract_dom,
    _scan_launch, _scan_locator_quality, _scan_navigate, _scan_page_state, _scan_screenshot, _scan_trace,
    _score_input, _step_timeout, _wait_after_login_submit, scan_page_dom,
)
from .screenshot_analysis import analyze_functional_screenshot
from .ui_generation import (_basic_generate_ui_steps, _load_action_templates, _match_template_for_case, generate_ui_steps, rule_generate_ui_steps, validate_ui_steps)

for _name in _DOMAIN_FUNCTION_NAMES:
    setattr(_legacy_module, _name, globals()[_name])

del _name
