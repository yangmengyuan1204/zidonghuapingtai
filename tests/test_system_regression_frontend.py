from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_index_loads_independent_system_regression_assets():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

    assert "/static/system-regression.css" in html
    assert "/static/system-regression.css?v=20260819-attr-simple" in html
    assert "/static/system-regression.js?v=20260819-attr-simple" in html


def test_system_regression_menu_and_execution_controls_are_present():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")

    assert 'key: "systemRegression", label: "系统回归"' in script
    assert "window.renderSystemRegression" in script
    assert "单条执行" in script
    assert "批量执行" in script
    assert 'type="checkbox"' in script
    assert "/api/system-regression/batches" in script


def test_parameters_use_ordinary_fields_and_repeatable_item_option_rows():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")

    assert "其他费用名义" in script
    assert "其他费用金额" in script
    assert "中国国内运费" in script
    assert "新增单番" in script
    assert "optionPickerHtml" in script
    assert "/api/system-regression/options" in script
    assert "client/order.optionList" in script
    assert "重新拉券和 OPTION" in script
    assert "添加OPTION" not in script
    assert "业务处理意见" in script
    assert 'id="srBusinessDecision"' in script
    assert "business_decision:" in script
    assert "fieldEl(\"#srBusinessDecision\")" in script
    assert "问题描述" in script
    assert 'id="srProblemDescription"' in script
    assert "problem_description:" in script
    assert "fieldEl(\"#srProblemDescription\")" in script
    assert "客户译文" in script
    assert 'id="srTranslationContent"' in script
    assert "translation_content:" in script
    assert "fieldEl(\"#srTranslationContent\")" in script
    assert 'type="number"' in script
    assert 'type="password"' in script
    assert "<select" in script
    assert "textarea" not in script.lower()
    assert "parameters_json" not in script


def test_layout_has_project_category_case_table_and_parameter_drawer():
    stylesheet = (ROOT / "static" / "system-regression.css").read_text(encoding="utf-8")
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")

    assert "system-regression-layout" in stylesheet
    assert "system-regression-drawer" in stylesheet
    assert "日本站" in script
    assert "用例分类" in script
    assert "参数设置" in script


def test_regression_toolbar_stays_at_top_when_scrolling():
    stylesheet = (ROOT / "static" / "system-regression.css").read_text(encoding="utf-8")
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")
    start = stylesheet.find("html.v3-embed .system-regression-scroll {")
    if start < 0:
        start = stylesheet.find("html.v3-embed .system-regression-scroll {\r\n")
    assert start >= 0
    block = stylesheet[start:start + 220]
    body_start = stylesheet.find("html.v3-embed:has(.system-regression-page) body {")
    if body_start < 0:
        body_start = stylesheet.find("html.v3-embed:has(.system-regression-page) body {\r\n")
    assert body_start >= 0
    body_block = stylesheet[body_start:body_start + 160]
    app_start = stylesheet.find("html.v3-embed:has(.system-regression-page) #app {")
    if app_start < 0:
        app_start = stylesheet.find("html.v3-embed:has(.system-regression-page) #app {\r\n")
    assert app_start >= 0
    app_block = stylesheet[app_start:app_start + 220]

    assert 'class="system-regression-scroll"' in script
    assert "<div class=\"system-regression-toolbar\">" in script
    toolbar_at = script.find("<div class=\"system-regression-toolbar\">")
    scroll_at = script.find('class="system-regression-scroll"')
    layout_at = script.find('class="system-regression-layout"')
    assert 0 <= toolbar_at < scroll_at < layout_at
    assert "overflow: auto" in block
    assert "height: 0" in block
    assert "flex-shrink: 0" in stylesheet
    assert "overflow: hidden" in body_block
    assert "overflow-y: auto" not in body_block
    assert "overflow: hidden" in app_block
    assert "height: 100%" in app_block
    assert "align-items: stretch" in stylesheet
    cases_start = stylesheet.find("html.v3-embed .system-regression-categories,\nhtml.v3-embed .system-regression-cases {")
    if cases_start < 0:
        cases_start = stylesheet.find("html.v3-embed .system-regression-categories,\r\nhtml.v3-embed .system-regression-cases {")
    assert cases_start >= 0
    cases_block = stylesheet[cases_start:cases_start + 180]
    assert "overflow: auto" in cases_block
    assert "min-height: 0" in cases_block


def test_parameter_drawer_overrides_v3_embed_overflow_hidden():
    stylesheet = (ROOT / "static" / "system-regression.css").read_text(encoding="utf-8")
    start = stylesheet.find("html.v3-embed .system-regression-drawer {\n  position: static")
    if start < 0:
        start = stylesheet.find("html.v3-embed .system-regression-drawer {\r\n  position: static")
    assert start >= 0
    block = stylesheet[start:start + 220]

    assert "overflow: visible" in block
    assert "height: auto" in block
    assert "max-height: none" in block
    assert "min-height: 0" in block
    assert "flex: 1 1 auto" in stylesheet


def test_table_select_all_checkbox_selects_and_clears_visible_cases():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")

    assert 'querySelector("#srSelectAll")?.addEventListener("change"' in script
    assert "srState.selected.add(item.id)" in script
    assert "srState.selected.delete(item.id)" in script
    assert "selectAll.indeterminate" in script


def test_problem_type_options_use_catalog_labels_instead_of_numeric_labels():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")

    assert "catalog.problem_types" in script
    assert "problemType.label" in script
    assert ">${index + 1}</option>" not in script


def test_customer_id_uses_an_ordinary_input_and_batch_runtime_context():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")

    assert "客户 ID" in script
    assert 'id="srCustomerId"' in script
    assert 'inputmode="numeric"' in script
    assert "customer_id: srState.customerId" in script
    assert "ledger_wait_seconds: Number(srState.ledgerWait || 30)" in script
    assert "systemRegressionCustomerId" in script


def test_money_panel_exposes_order_porder_coupon_and_new_case_controls():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "static" / "system-regression.css").read_text(encoding="utf-8")

    assert "手续费减免券" in script
    assert "账号没有真券时用" in script
    assert "preferRealServiceCoupon" in script
    assert 'id="srCouponId"' in script
    assert 'id="srVoucherId"' in script
    assert "porder.predictLogisticsPrice" in script
    assert "付钱后等多久再对数" in script
    assert "新建用例" in script
    assert "CUSTOM-PAY" in script
    assert "CUSTOM-PORDER" in script
    assert "/api/system-regression/cases" in script
    assert "/api/system-regression/tickets" in script
    assert "/api/system-regression/options" in script
    assert "client/user.usableDiscount" in script
    assert "client/order.optionList" in script
    assert 'method: "DELETE"' in script
    assert "system-regression-bill" in stylesheet
    assert "system-regression-modal" in stylesheet
    assert "textarea" not in script.lower()
    assert "parameters_json" not in script


def test_batch_execution_freezes_selected_case_parameters():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")

    assert "function freezeCaseParameters(caseIds)" in script
    assert "case_parameters: freezeCaseParameters(caseIds)" in script
    assert "persistDrawer()" in script
    assert "structuredClone(item.parameters || {})" in script


def test_batch_result_exposes_structured_execution_evidence():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")

    assert "function batchResultTags(batch)" in script
    assert "execution_id" in script
    assert "reason_code" in script
    assert "structured_evidence" in script
    assert "before_evidence" in script
    assert "after_evidence" in script
    assert "客户 ID 只能填写数字" in script


def test_run_console_persists_batch_and_does_not_rerender_other_pages():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "static" / "system-regression.css").read_text(encoding="utf-8")

    assert "systemRegressionActiveBatch" in script
    assert "function isOnRegressionPage()" in script
    assert "if (isOnRegressionPage())" in script
    assert "function patchRunConsole()" in script
    assert "function captureRunConsoleScroll()" in script
    assert "function restoreRunConsoleScroll(saved)" in script
    assert "runConsoleScrollBusy" in script
    assert "overflow-anchor: none" in stylesheet
    assert "实时事件" in script
    assert "逐条结果" in script
    assert "失败重跑" in script
    assert 'id="srStopBatch"' in script
    assert "/batches/${srState.batch.id}/stop" in script
    assert "system-regression-seq" in stylesheet
    assert "system-regression-run" in stylesheet


def test_porder_bill_shows_cny_and_jpy_together():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "static" / "system-regression.css").read_text(encoding="utf-8")

    assert "function dualCnyJpy" in script
    assert "function cnyToJpyRate" in script
    assert "preview_cny_to_jpy" in script
    assert "<em>人民币</em>" in script
    assert "<em>日元</em>" in script
    assert "system-regression-money-dual" in stylesheet
    assert "${dualCnyJpy(p.logistics)}" in script
    assert "${dualCnyJpy(p.voucher, true)}" in script
    assert "${dualCnyJpy(p.payable)}" in script
    assert "${dualCnyJpy(t.goods)}" in script
    assert "${dualCnyJpy(t.service)}" in script
    assert "${dualCnyJpy(t.payable)}" in script


def test_result_console_uses_plain_language_and_recent_batches():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "static" / "system-regression.css").read_text(encoding="utf-8")

    assert "function runResultText(run)" in script
    assert "通过。订单" in script
    assert "通过。配送单" in script
    assert "近期批次" in script
    assert 'id="srRecentBatch"' in script
    assert "搜编号或名称" in script
    assert "data-sr-result-filter" in script
    assert "/api/system-regression/batches?suite_key=" in script
    assert "function openBatch(batchId)" in script
    assert "请选择一批查看结果" in script
    assert "system-regression-result-copy" in stylesheet
    assert "system-regression-result-tools" in stylesheet
    assert "source.items = Array.from({ length: count }" in (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")


def test_edit_keeps_scroll_and_shows_membership_beside_service_fee():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")

    assert "function capturePageScroll()" in script
    assert "function restorePageScroll(saved, options = {})" in script
    assert "renderPage({ resetDrawer: true })" in script
    assert "function membershipCustomerAttr()" in script
    assert 'id="srMembershipLevel"' in script
    assert "客户属性：" in script
    assert "普通用户" in script
    assert "function membershipFeeNoteHtml()" in script
    assert 'id="srBillMembership"' in script
    assert "手续费比例" in script
    assert "定额会员（VIP/SVIP）" not in script
    bill_fee_at = script.find('<span>${t.couponOn ? "手续费（优惠券免）" : "手续费"}</span>')
    bill_member_at = script.find("${membershipFeeNoteHtml()}")
    assert 0 <= bill_fee_at < bill_member_at
