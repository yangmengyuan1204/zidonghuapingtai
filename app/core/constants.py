import os


API_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
ACTION_TEMPLATE_JSON_DEFAULTS = {
    "trigger_keywords": [],
    "steps": [],
    "variables": {},
    "locator_fallbacks": {},
}

QUALITY_EXECUTABLE = "executable"
QUALITY_UNCHECKED = "unchecked"
QUALITY_AUTH_RISK = "auth_risk"
QUALITY_MISSING_VARIABLES = "missing_variables"
QUALITY_LOCATOR_RISK = "locator_risk"
QUALITY_NEEDS_REVIEW = "needs_review"
QUALITY_NOT_RECOMMENDED = "not_recommended"

ASSERTION_ACTIONS = {"assert_url", "assert_visible", "assert_value", "text_assert"}
LOCATOR_REQUIRED_ACTIONS = {
    "input",
    "click",
    "wait_for_selector",
    "text_assert",
    "select",
    "check",
    "uncheck",
    "assert_visible",
    "assert_value",
}
VALUE_REQUIRED_ACTIONS = {"goto", "input", "select", "wait", "assert_url", "assert_value", "text_assert"}

FUNCTIONAL_CASE_KIND_BUSINESS_AUTH = "business_authenticated"
FUNCTIONAL_CASE_KIND_AUTH_NEGATIVE = "auth_negative"
FUNCTIONAL_CASE_KIND_MANUAL_ONLY = "manual_only"

BUILTIN_RUNTIME_VARS = {
    "timestamp",
    "datetime",
    "date",
    "uuid",
    "random_int",
    "random_str",
    "random_phone",
    "random_email",
}
ACCOUNT_RUNTIME_VARS = {
    "username",
    "account",
    "email",
    "mobile",
    "phone",
    "password",
    "code",
    "captcha",
    "captcha_code",
    "verify_code",
    "verification_code",
}
SEARCH_SEED_KEYS = {
    "customer_id": ["customer_id", "customerId", "client_id", "clientId"],
    "customer_name": ["customer_name", "customerName", "client_name", "clientName"],
    "orderNumber": ["orderNumber", "order_no", "orderNo", "order_sn", "orderSn"],
    "box_no": ["box_no", "boxNo", "box_number", "boxNumber"],
    "location_code": ["location_code", "locationCode", "warehouse_location", "storage_location"],
    "startDate": ["startDate", "start_date"],
    "endDate": ["endDate", "end_date"],
}

PROXY_ALLOWED_METHODS = API_ALLOWED_METHODS
PROXY_ALLOW_PRIVATE_URLS = os.getenv("ALLOW_PROXY_PRIVATE_URLS", "").strip().lower() in {"1", "true", "yes", "on"}
PROXY_MAX_REDIRECTS = 5
