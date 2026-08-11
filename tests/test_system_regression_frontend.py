from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_index_loads_independent_system_regression_assets():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

    assert "/static/system-regression.css" in html
    assert "/static/system-regression.js?v=20260729-system-regression-customer-id" in html


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
    assert "添加OPTION" in script
    assert "业务处理意见" in script
    assert 'id="srBusinessDecision"' in script
    assert "business_decision: document.querySelector" in script
    assert "问题描述" in script
    assert 'id="srProblemDescription"' in script
    assert "problem_description: document.querySelector" in script
    assert "客户译文" in script
    assert 'id="srTranslationContent"' in script
    assert "translation_content: document.querySelector" in script
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
    assert "systemRegressionCustomerId" in script


def test_batch_execution_freezes_selected_case_parameters():
    script = (ROOT / "static" / "system-regression.js").read_text(encoding="utf-8")

    assert "function freezeCaseParameters(caseIds)" in script
    assert "case_parameters: freezeCaseParameters(caseIds)" in script
    assert "collectParameters(active)" in script
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
