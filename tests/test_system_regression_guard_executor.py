from __future__ import annotations

from app.system_regression.projects.japan.guard_executor import (
    GuardActionUnavailable,
    GuardExecutor,
    GuardPreconditionMissing,
    GuardWriteTimeout,
    LiveGuardDriver,
    match_guard_error,
    select_execution_rows,
)
from app.system_regression.projects.japan.guard_runner import GuardRunner


def _case(guard_kind="part_tail_unpaid"):
    return {
        "id": 7,
        "case_key": "JP-PG-GUARD-001",
        "name": "guard",
        "runner_kind": "problem_guard",
        "parameters": {"guard_kind": guard_kind},
        "expectation": {"outcome": "guard", "direction": "none"},
    }


def _prepared():
    return {
        "order_sn": "O-1",
        "problem_goods_id": "P-1",
        "purchase_record_ids": ["R-1"],
        "precondition_evidence": {"tail_paid": False},
        "before_evidence": {"problem_status": 3},
        "action_fields": {"problem_goods_id": "P-1"},
        "actor": {"role": "normal"},
    }


def test_match_guard_error_prefers_business_code_over_other_signals():
    matched = match_guard_error(
        {
            "business_code": "PART_TAIL_UNPAID",
            "http_status": 500,
            "error_message": "无关文案",
        },
        business_codes=("PART_TAIL_UNPAID",),
        http_statuses=(422,),
        message_patterns=(r"尾款",),
    )

    assert matched == "business_code"


def test_match_guard_error_uses_http_before_message_regex():
    matched = match_guard_error(
        {"http_status": 422, "error_message": "包含尾款文案"},
        business_codes=(),
        http_statuses=(422,),
        message_patterns=(r"尾款",),
    )

    assert matched == "http_status"


def test_same_error_at_wrong_stage_cannot_pass():
    executor = GuardExecutor(
        precondition_provider=lambda _spec, _case, _context: _prepared(),
        action_gateway=lambda _action, _prepared, _case, _context: {
            "actual_stage": "problem_create",
            "business_code": "PART_TAIL_UNPAID",
            "error_message": "尾款未完成",
        },
    )

    result = GuardRunner(executor.execute).execute(_case(), {"execution_id": "E-1", "batch_id": 2})

    assert result.status == "failed"
    assert result.reason_code == "unexpected_guard_stage"


def test_successful_target_call_without_guard_is_backend_defect():
    executor = GuardExecutor(
        precondition_provider=lambda _spec, _case, _context: _prepared(),
        action_gateway=lambda _action, _prepared, _case, _context: {
            "actual_stage": "business_deal",
            "success": True,
            "http_status": 200,
            "business_diffs": [],
        },
    )

    result = GuardRunner(executor.execute).execute(_case(), {})

    assert result.status == "failed"
    assert result.reason_code == "backend_guard_missing"


def test_missing_precondition_capability_is_blocked():
    def missing(_spec, _case, _context):
        raise GuardPreconditionMissing("缺少转寄订单构造接口")

    result = GuardRunner(GuardExecutor(missing, lambda *_args: {}).execute).execute(_case(), {})

    assert result.status == "blocked"
    assert result.reason_code == "precondition_capability_missing"


def test_missing_target_action_is_blocked():
    def unavailable(_action, _prepared, _case, _context):
        raise GuardActionUnavailable("目标提交接口不可调用")

    result = GuardRunner(GuardExecutor(lambda *_args: _prepared(), unavailable).execute).execute(_case(), {})

    assert result.status == "blocked"
    assert result.reason_code == "target_action_unavailable"


def test_timeout_confirmed_written_continues_verification_without_replay():
    calls = []

    def timed_out(_action, _prepared, _case, _context):
        calls.append("submit")
        raise GuardWriteTimeout(
            "请求超时",
            probe=lambda: {
                "write_state": "confirmed_written",
                "actual_stage": "business_deal",
                "business_code": "PART_TAIL_UNPAID",
                "error_message": "尾款未完成",
                "business_diffs": [],
            },
        )

    result = GuardRunner(GuardExecutor(lambda *_args: _prepared(), timed_out).execute).execute(_case(), {})

    assert calls == ["submit"]
    assert result.status == "passed"
    assert result.result["response_evidence"][0]["write_state"] == "confirmed_written"


def test_timeout_indeterminate_is_blocked_and_not_replayed():
    calls = []

    def timed_out(_action, _prepared, _case, _context):
        calls.append("submit")
        raise GuardWriteTimeout("请求超时", probe=lambda: {"write_state": "indeterminate"})

    result = GuardRunner(GuardExecutor(lambda *_args: _prepared(), timed_out).execute).execute(_case(), {})

    assert calls == ["submit"]
    assert result.status == "blocked"
    assert result.reason_code == "unknown_write_state"


def test_execution_row_selection_cannot_match_historical_problem():
    rows = [
        {"id": 1, "batch_no": "OLD", "problem_goods_id": "P-1"},
        {"id": 2, "batch_no": "NEW", "problem_goods_id": "P-2"},
        {"id": 3, "batch_no": "NEW", "problem_goods_id": "P-1"},
    ]

    assert select_execution_rows(rows, batch_no="NEW", problem_goods_id="P-2") == [rows[1]]


def test_live_guard_for_over_unstored_quantity_calls_real_create_with_n_plus_one():
    captured = []

    class FakeProblemRunner:
        def candidate_loader(self, _case, context):
            return {
                **context,
                "order_sn": "O-1",
                "candidate": {
                    "order_purchase_id": 11,
                    "order_detail_id": 12,
                    "possible_num": 2,
                    "storage_num": 0,
                    "confirm_num": 2,
                    "confirm_price": "10",
                    "confirm_freight": "3",
                },
            }

    class FakeApiError(RuntimeError):
        def __init__(self):
            self.payload = {"code": "PROBLEM_NUM_OVER_UNSTORED", "msg": "问题产品提出数超过未上架数"}

    class FakeGateway:
        def __init__(self, _env, _variables, _log):
            pass

        def list_problems(self, _order_sn, _status=0):
            return []

        def create_problem(self, fields):
            captured.append(dict(fields))
            raise FakeApiError()

    driver = LiveGuardDriver(object(), FakeProblemRunner(), gateway_factory=FakeGateway)
    executor = GuardExecutor(driver.prepare, driver.perform)
    case = _case("problem_num_over_unstored")

    result = GuardRunner(executor.execute).execute(case, {"execution_id": "E-1", "variables": {}})

    assert result.status == "passed"
    assert captured[0]["data[0][num]"] == 3
    assert result.result["actual_stage"] == "problem_create"


def test_live_guard_reports_missing_builder_capability_instead_of_using_normal_flow():
    driver = LiveGuardDriver(object(), object(), gateway_factory=lambda *_args: object())

    result = GuardRunner(GuardExecutor(driver.prepare, driver.perform).execute).execute(_case("resend_order"), {})

    assert result.status == "blocked"
    assert result.reason_code == "precondition_capability_missing"


def test_live_duplicate_guard_creates_one_problem_then_submits_the_same_purchase_again():
    calls = []

    class FakeProblemRunner:
        def candidate_loader(self, _case, context):
            return {
                **context,
                "order_sn": "O-2",
                "candidate": {
                    "order_purchase_id": 21,
                    "order_detail_id": 22,
                    "possible_num": 3,
                    "storage_num": 0,
                    "confirm_num": 3,
                    "confirm_price": "10",
                    "confirm_freight": "3",
                },
            }

    class FakeGateway:
        def __init__(self, _env, _variables, _log):
            self.created = False

        def list_problems(self, _order_sn, _status=0):
            return [{"problem_goods_id": 31, "status": 1}] if self.created else []

        def create_problem(self, fields):
            calls.append(dict(fields))
            if not self.created:
                self.created = True
                return {"success": True, "code": 0}
            raise RuntimeError("有进行中的问题产品, 不可以重复提出")

    driver = LiveGuardDriver(object(), FakeProblemRunner(), gateway_factory=FakeGateway)
    result = GuardRunner(GuardExecutor(driver.prepare, driver.perform).execute).execute(
        _case("duplicate_open_problem"),
        {"variables": {}},
    )

    assert result.status == "passed"
    assert len(calls) == 2
    assert calls[0]["data[0][order_purchase_id]"] == calls[1]["data[0][order_purchase_id]"] == 21


def test_guard_matches_rejection_message_nested_in_success_envelope():
    prepared = {**_prepared(), "target_callback": lambda *_args: {
        "actual_stage": "business_deal",
        "success": True,
        "data": {"msg": "订单尾款未分批付款完成, 不可决策"},
    }}
    driver = LiveGuardDriver(object(), object())

    result = GuardRunner(GuardExecutor(lambda *_args: prepared, driver.perform).execute).execute(_case(), {})

    assert result.status == "passed"
    assert result.result["response_evidence"][0]["matched_by"] == "message_regex"


def test_live_purchase_guard_builds_real_problem_stage_then_calls_purchase_endpoint():
    calls = []

    class FakeProblemRunner:
        account_resolver = None

        @staticmethod
        def candidate_loader(_case, context):
            return {
                **context,
                "order_sn": "O-300001",
                "variables": {"customer_id": 300001},
                "candidate": {
                    "order_purchase_id": 41,
                    "order_detail_id": 42,
                    "possible_num": 2,
                    "storage_num": 0,
                    "confirm_num": 2,
                    "confirm_price": "10",
                    "confirm_freight": "3",
                },
            }

    class FakeApiError(RuntimeError):
        def __init__(self):
            self.payload = {"code": "QUANTITY_OVER_POSSIBLE", "msg": "修改后数量应该小于可入库数"}

    class FakeGateway:
        def __init__(self, _env, _variables, _log):
            self.status = 0

        def balance_changes(self, _order_sn):
            return []

        def create_problem(self, fields):
            calls.append(("create_problem", dict(fields)))
            self.status = 1
            return {"success": True}

        def find_problem(self, _order_sn, _problem_id=0, _purchase_id=0):
            return {"problem_goods_id": 51, "order_purchase_id": 41, "status": self.status}

        def wait_for_status(self, order_sn, problem_id, status):
            return self.find_problem(order_sn, problem_id)

        def translate(self, problem_id, content):
            calls.append(("translate", {"problem_id": problem_id, "content": content}))
            self.status = 2
            return {"success": True}

        def client_reply(self, problem_id, content):
            calls.append(("client_reply", {"problem_id": problem_id, "content": content}))
            self.status = 3
            return {"success": True}

        def business_deal(self, fields, preview=False):
            calls.append(("business_deal", dict(fields)))
            self.status = 4
            return {"success": True}

        def purchase_deal(self, fields):
            calls.append(("purchase_deal", dict(fields)))
            raise FakeApiError()

        def list_problems(self, _order_sn, _status=0):
            return [self.find_problem(_order_sn)]

    case = _case("quantity_over_possible")
    driver = LiveGuardDriver(object(), FakeProblemRunner(), gateway_factory=FakeGateway)
    result = GuardRunner(GuardExecutor(driver.prepare, driver.perform).execute).execute(case, {"variables": {}})

    assert result.status == "passed"
    assert [name for name, _fields in calls] == [
        "create_problem", "translate", "client_reply", "business_deal", "purchase_deal"
    ]
    assert calls[-1][1]["data[0][pre_num]"] == 3


def test_live_option_price_type_change_success_is_reported_as_backend_guard_missing():
    prepared = {
        **_prepared(),
        "gateway": type(
            "Gateway",
            (),
            {
                "update_options": lambda self, problem_id, options: {"success": True, "code": 0},
                "list_problems": lambda self, order_sn, status=0: [],
            },
        )(),
        "action_fields": {"problem_goods_id": 9, "options": [{"option_id": 7, "price_type": 1}]},
    }
    driver = LiveGuardDriver(object(), object())

    result = GuardRunner(GuardExecutor(lambda *_args: prepared, driver.perform).execute).execute(
        _case("option_price_type_change"), {}
    )

    assert result.status == "failed"
    assert result.reason_code == "backend_guard_missing"


def test_result_verification_resume_uses_checkpoint_response_without_replaying_write():
    calls = []
    response = {
        "actual_stage": "business_deal",
        "business_code": "PART_TAIL_UNPAID",
        "error_message": "尾款未完成",
        "business_diffs": [],
        "write_state": "confirmed_not_written",
    }
    executor = GuardExecutor(
        lambda *_args: calls.append("prepare") or _prepared(),
        lambda *_args: calls.append("write") or response,
    )

    result = executor.execute(
        _case(),
        {
            "resume_stage": "result_verification",
            "execution_state": {
                "resume_payload": {
                    "confirmed_response": response,
                    "prepared": _prepared(),
                }
            },
        },
    )

    assert result["status"] == "passed"
    assert calls == []
