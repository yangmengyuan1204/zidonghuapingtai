(function () {
  const existing = views.findIndex((item) => item.key === "systemRegression");
  if (existing < 0) {
    const recordsIndex = views.findIndex((item) => item.key === "records");
    views.splice(recordsIndex < 0 ? views.length : recordsIndex, 0, { key: "systemRegression", label: "系统回归" });
  }

  const originalRenderCurrentView = renderCurrentView;
  renderCurrentView = function () {
    if (state.view === "systemRegression") return window.renderSystemRegression();
    return originalRenderCurrentView();
  };

  const srState = {
    suiteKey: "japan",
    cases: [],
    categories: [],
    category: "all",
    selected: new Set(),
    activeId: 0,
    projectId: localStorage.getItem("systemRegressionProjectId") || localStorage.getItem("projectId") || "",
    envId: localStorage.getItem("systemRegressionEnvId") || "",
    customerId: localStorage.getItem("systemRegressionCustomerId") || "",
    projects: [],
    envs: [],
    problemTypes: [],
    batch: null,
  };

  const categoryLabels = {
    payment: "支付金额",
    problem_amount: "问题产品-基础金额",
    problem_service_fee: "问题产品-手续费",
    problem_option_manual: "问题产品-OPTION手动",
    problem_option_auto: "问题产品-OPTION自动",
    problem_mixed: "问题产品-混合调整",
    problem_flow: "问题产品-完整流程",
    problem_guard: "问题产品-预期拦截",
  };

  function currentCase() {
    return srState.cases.find((item) => item.id === srState.activeId) || srState.cases[0] || null;
  }

  function visibleCases() {
    return srState.category === "all"
      ? srState.cases
      : srState.cases.filter((item) => item.category === srState.category);
  }

  function problemTypeOptions(selectedValue) {
    return srState.problemTypes.map((problemType) => `
      <option value="${escapeHtml(problemType.value)}" ${Number(selectedValue) === Number(problemType.value) ? "selected" : ""}>${escapeHtml(problemType.label)}</option>`).join("");
  }

  function optionTags(options, itemIndex) {
    const rows = options.length ? options : [];
    return rows.map((row, optionIndex) => `
      <div class="system-regression-repeat" data-option-row="${itemIndex}:${optionIndex}">
        <div class="system-regression-grid">
          <div class="field"><label>OPTION名称</label><input data-option-name value="${escapeHtml(row.name || "")}" /></div>
          <div class="field"><label>计价方式</label><select data-option-price-type><option value="0" ${Number(row.price_type) === 0 ? "selected" : ""}>固定金额</option><option value="1" ${Number(row.price_type) === 1 ? "selected" : ""}>百分比</option></select></div>
          <div class="field"><label>价格/比例</label><input type="number" step="0.01" data-option-price value="${escapeHtml(row.price ?? 0)}" /></div>
          <div class="field"><label>数量</label><input type="number" min="0" data-option-num value="${escapeHtml(row.num ?? 1)}" /></div>
        </div>
        <button class="btn danger" type="button" data-remove-option="${itemIndex}:${optionIndex}">删除OPTION</button>
      </div>`).join("");
  }

  function itemTags(items) {
    return items.map((row, itemIndex) => `
      <div class="system-regression-repeat" data-item-row="${itemIndex}">
        <div class="system-regression-grid">
          <div class="field"><label>单番序号</label><input type="number" min="1" data-item-sorting value="${escapeHtml(row.sorting ?? itemIndex + 1)}" /></div>
          <div class="field"><label>数量</label><input type="number" min="1" data-item-quantity value="${escapeHtml(row.quantity ?? 1)}" /></div>
          <div class="field"><label>报价单价(CNY)</label><input type="number" step="0.01" data-item-price value="${escapeHtml(row.offer_price?.value ?? 10)}" /></div>
          <div class="field"><label>中国国内运费(CNY)</label><input type="number" step="0.01" data-item-freight value="${escapeHtml(row.offer_freight?.value ?? 0)}" /></div>
        </div>
        <div class="system-regression-actions"><button class="btn secondary" type="button" data-add-option="${itemIndex}">添加OPTION</button><button class="btn danger" type="button" data-remove-item="${itemIndex}">删除单番</button></div>
        ${optionTags(row.options || [], itemIndex)}
      </div>`).join("");
  }

  function normalizedParameters(item) {
    const source = structuredClone(item?.parameters || {});
    source.order = source.order || {};
    source.order.item_count = source.order.item_count || source.item_count || 1;
    source.order.default_quantity = source.order.default_quantity || 1;
    source.order.other_fee_name = source.order.other_fee_name || source.other_fee_name || "";
    source.order.other_fee_amount = source.order.other_fee_amount || { value: source.other_fee_amount || 0, currency: "CNY" };
    source.items = source.items || [];
    source.problem_goods = source.problem_goods || {};
    return source;
  }

  function drawerTags(item) {
    if (!item) return '<div class="system-regression-drawer"><p>请选择用例。</p></div>';
    const parameters = normalizedParameters(item);
    const problem = parameters.problem_goods;
    const showProblem = item.runner_kind.startsWith("problem_");
    return `<aside class="system-regression-drawer">
      <div class="panel-title"><h3>参数设置</h3><span>${escapeHtml(item.case_key)}</span></div>
      <div class="system-regression-grid">
        <div class="field wide"><label>用例名称</label><input id="srCaseName" value="${escapeHtml(item.name)}" /></div>
        <div class="field"><label>支付渠道</label><select id="srPaymentMode"><option value="balance" ${parameters.payment_mode !== "bank" ? "selected" : ""}>余额</option><option value="bank" ${parameters.payment_mode === "bank" ? "selected" : ""}>银行</option></select></div>
        <div class="field"><label>金额步长(CNY)</label><input id="srAmountStep" type="number" step="0.01" value="${escapeHtml(parameters.amount_step || 1)}" /></div>
      </div>
      <section class="system-regression-section">
        <h4>订单费用</h4>
        <div class="system-regression-grid">
          <div class="field"><label>单番数量</label><input id="srItemCount" type="number" min="1" value="${escapeHtml(parameters.order.item_count)}" /></div>
          <div class="field"><label>默认商品数量</label><input id="srDefaultQuantity" type="number" min="1" value="${escapeHtml(parameters.order.default_quantity)}" /></div>
          <div class="field"><label>其他费用名义</label><input id="srOtherFeeName" value="${escapeHtml(parameters.order.other_fee_name)}" /></div>
          <div class="field"><label>其他费用金额(CNY)</label><input id="srOtherFeeAmount" type="number" step="0.01" value="${escapeHtml(parameters.order.other_fee_amount?.value ?? 0)}" /></div>
        </div>
      </section>
      <section class="system-regression-section">
        <div class="system-regression-actions"><h4>单番与OPTION</h4><button class="btn secondary" id="srAddItem" type="button">新增单番</button></div>
        <div id="srItemRows">${itemTags(parameters.items)}</div>
      </section>
      ${showProblem ? `<section class="system-regression-section">
        <h4>问题产品处理</h4>
        <div class="system-regression-grid">
          <div class="field"><label>问题类型</label><select id="srProblemType">${problemTypeOptions(problem.problem_type || parameters.problem_type)}</select></div>
          <div class="field"><label>问题数量</label><input id="srProblemNum" type="number" min="0" value="${escapeHtml(problem.problem_num ?? 1)}" /></div>
          <div class="field wide"><label>问题描述</label><input id="srProblemDescription" value="${escapeHtml(problem.problem_description || "系统回归问题产品")}" /></div>
          <div class="field wide"><label>客户译文</label><input id="srTranslationContent" value="${escapeHtml(problem.translation_content || "システム回帰テスト")}" /></div>
          <div class="field"><label>调整后数量</label><input id="srPreNum" type="number" min="0" value="${escapeHtml(problem.pre_num ?? 2)}" /></div>
          <div class="field"><label>调整后单价(CNY)</label><input id="srPrePrice" type="number" step="0.01" value="${escapeHtml(problem.pre_price?.value ?? 9)}" /></div>
          <div class="field"><label>调整后运费(CNY)</label><input id="srPreFreight" type="number" step="0.01" value="${escapeHtml(problem.pre_freight?.value ?? 1)}" /></div>
          <div class="field"><label>客户处理</label><select id="srClientDeal"><option value="accept">接受</option><option value="exchange">换货</option><option value="cancel">取消/退货</option><option value="discard">已收不退</option><option value="other">其他</option></select></div>
          <div class="field"><label>手续费</label><select id="srServiceSuggest"><option value="2">多退少补</option><option value="1">已收不退</option></select></div>
          <div class="field"><label>OPTION计算</label><select id="srOptionSuggest"><option value="2">系统自动计算</option><option value="1">按输入值计算</option></select></div>
          <div class="field wide"><label>业务处理意见</label><input id="srBusinessDecision" value="${escapeHtml(problem.business_decision || "系统回归自动处理")}" /></div>
        </div>
      </section>` : ""}
      <div class="system-regression-actions system-regression-section"><button class="btn" id="srSaveCase" type="button">保存参数</button><button class="btn secondary" id="srCopyCase" type="button">复制用例</button><button class="btn secondary" id="srResetCase" type="button">恢复默认</button><button class="btn" id="srRunOne" type="button">单条执行</button></div>
    </aside>`;
  }

  function categoryTags() {
    const counts = Object.fromEntries(srState.categories.map((key) => [key, srState.cases.filter((item) => item.category === key).length]));
    return `<button class="${srState.category === "all" ? "active" : ""}" data-sr-category="all"><span>全部用例</span><b>${srState.cases.length}</b></button>${srState.categories.map((key) => `<button class="${srState.category === key ? "active" : ""}" data-sr-category="${key}"><span>${escapeHtml(categoryLabels[key] || key)}</span><b>${counts[key]}</b></button>`).join("")}`;
  }

  function caseTableTags() {
    const rows = visibleCases();
    return `<table class="system-regression-case-table"><thead><tr><th><input id="srSelectAll" type="checkbox" /></th><th>编号</th><th>用例名称</th><th>状态</th><th>操作</th></tr></thead><tbody>${rows.map((item) => `<tr class="${item.id === srState.activeId ? "active" : ""}"><td><input type="checkbox" data-sr-select="${item.id}" ${srState.selected.has(item.id) ? "checked" : ""} /></td><td>${escapeHtml(item.case_key)}</td><td><button class="link-button" data-sr-open="${item.id}" type="button">${escapeHtml(item.name)}</button></td><td>${item.enabled ? "启用" : "停用"}${item.user_modified ? " · 已修改" : ""}</td><td><button class="btn secondary" data-sr-open="${item.id}" type="button">编辑</button></td></tr>`).join("")}</tbody></table>`;
  }

  function batchResultTags(batch) {
    if (!batch?.runs?.length) return "";
    const rows = batch.runs.map((run) => {
      const evidence = run.structured_evidence || {};
      const details = {
        execution_id: run.execution_id || "",
        reason_code: run.reason_code || "",
        before_evidence: evidence.before_evidence || {},
        after_evidence: evidence.after_evidence || {},
        response_evidence: evidence.response_evidence || {},
        business_diffs: evidence.business_diffs || [],
        required_effects: evidence.required_effects || [],
        forbidden_effects: evidence.forbidden_effects || [],
        allowed_effects: evidence.allowed_effects || [],
        unclassified_effects: evidence.unclassified_effects || [],
      };
      return `<details><summary>${escapeHtml(run.case_key || run.case_id)} · ${escapeHtml(run.status)}${run.reason_code ? ` · ${escapeHtml(run.reason_code)}` : ""}</summary><pre>${escapeHtml(JSON.stringify(details, null, 2))}</pre></details>`;
    }).join("");
    return `<section class="system-regression-section"><h4>执行结果证据</h4>${rows}</section>`;
  }

  function renderPage() {
    const active = currentCase();
    contentEl().innerHTML = `<section class="system-regression-page">
      <div class="system-regression-toolbar">
        <div class="filters"><div class="field compact"><label>回归项目</label><select id="srSuite"><option value="japan">日本站</option></select></div><div class="field compact"><label>业务项目</label><select id="srProject">${optionList(srState.projects, "id", "name", srState.projectId)}</select></div><div class="field compact"><label>执行环境</label><select id="srEnv">${optionList(srState.envs, "id", "env_name", srState.envId)}</select></div><div class="field compact"><label>客户 ID</label><input id="srCustomerId" inputmode="numeric" value="${escapeHtml(srState.customerId)}" placeholder="例如 300001" /></div></div>
        <div class="system-regression-actions"><button class="btn secondary" id="srSelectVisible" type="button">选择当前分类</button><button class="btn" id="srRunBatch" type="button">批量执行</button></div>
      </div>
      ${srState.batch ? `<div class="system-regression-status">批次 ${escapeHtml(srState.batch.batch_no)}：${escapeHtml(srState.batch.status)}，通过 ${srState.batch.passed_count}/${srState.batch.total_count}</div>${batchResultTags(srState.batch)}` : ""}
      <div class="system-regression-layout"><nav class="system-regression-categories"><div class="panel-title"><h3>用例分类</h3></div>${categoryTags()}</nav><main class="system-regression-cases">${caseTableTags()}</main>${drawerTags(active)}</div>
    </section>`;
    bindPage();
  }

  function collectItems() {
    return [...document.querySelectorAll("[data-item-row]")].map((row) => ({
      sorting: Number(row.querySelector("[data-item-sorting]").value || 1),
      quantity: Number(row.querySelector("[data-item-quantity]").value || 1),
      offer_price: { value: row.querySelector("[data-item-price]").value || "0", currency: "CNY" },
      offer_freight: { value: row.querySelector("[data-item-freight]").value || "0", currency: "CNY" },
      options: [...row.querySelectorAll("[data-option-row]")].map((option) => ({
        name: option.querySelector("[data-option-name]").value,
        price_type: Number(option.querySelector("[data-option-price-type]").value),
        price: option.querySelector("[data-option-price]").value || "0",
        num: Number(option.querySelector("[data-option-num]").value || 0),
        checked: true,
      })),
    }));
  }

  function collectParameters(item) {
    const parameters = normalizedParameters(item);
    parameters.payment_mode = document.querySelector("#srPaymentMode")?.value || parameters.payment_mode || "balance";
    parameters.amount_step = document.querySelector("#srAmountStep")?.value || "1";
    parameters.order = {
      item_count: Number(document.querySelector("#srItemCount")?.value || 1),
      default_quantity: Number(document.querySelector("#srDefaultQuantity")?.value || 1),
      other_fee_name: document.querySelector("#srOtherFeeName")?.value || "",
      other_fee_amount: { value: document.querySelector("#srOtherFeeAmount")?.value || "0", currency: "CNY" },
    };
    parameters.items = collectItems();
    if (document.querySelector("#srProblemType")) {
      parameters.problem_goods = {
        problem_type: Number(document.querySelector("#srProblemType").value),
        problem_num: Number(document.querySelector("#srProblemNum").value),
        problem_description: document.querySelector("#srProblemDescription").value || "系统回归问题产品",
        translation_content: document.querySelector("#srTranslationContent").value || "システム回帰テスト",
        pre_num: Number(document.querySelector("#srPreNum").value),
        pre_price: { value: document.querySelector("#srPrePrice").value || "0", currency: "CNY" },
        pre_freight: { value: document.querySelector("#srPreFreight").value || "0", currency: "CNY" },
        client_deal_choice: document.querySelector("#srClientDeal").value,
        service_deal_suggest: Number(document.querySelector("#srServiceSuggest").value),
        option_deal_suggest: Number(document.querySelector("#srOptionSuggest").value),
        option_new: parameters.problem_goods?.option_new || [],
        g_deal_type: parameters.problem_goods?.g_deal_type || "仅退款",
        business_decision: document.querySelector("#srBusinessDecision").value || "系统回归自动处理",
      };
    }
    return parameters;
  }

  function freezeCaseParameters(caseIds) {
    const active = currentCase();
    if (active && caseIds.includes(active.id)) active.parameters = collectParameters(active);
    return Object.fromEntries(caseIds.map((caseId) => {
      const item = srState.cases.find((candidate) => candidate.id === caseId);
      return [String(caseId), item ? structuredClone(item.parameters || {}) : {}];
    }));
  }

  async function execute(caseIds) {
    if (!caseIds.length) return showToast("请至少选择一条用例");
    if (!srState.projectId || !srState.envId) return showToast("请选择业务项目和执行环境");
    srState.customerId = String(document.querySelector("#srCustomerId")?.value || srState.customerId || "").trim();
    if (!/^\d+$/.test(srState.customerId)) return showToast("客户 ID 只能填写数字");
    localStorage.setItem("systemRegressionCustomerId", srState.customerId);
    srState.batch = await api("/api/system-regression/batches", { method: "POST", body: { suite_key: "japan", case_ids: caseIds, project_id: Number(srState.projectId), env_id: Number(srState.envId), context: { variables: { customer_id: srState.customerId }, case_parameters: freezeCaseParameters(caseIds) } } });
    renderPage();
    pollBatch(srState.batch.id);
  }

  async function pollBatch(batchId) {
    const batch = await api(`/api/system-regression/batches/${batchId}`);
    srState.batch = batch;
    renderPage();
    if (["pending", "running", "waiting_account"].includes(batch.status)) {
      const waiting = (batch.runs || []).find((run) => run.status === "waiting_account");
      if (waiting) openAccountResume(waiting);
      window.setTimeout(() => pollBatch(batchId), 2000);
    }
  }

  function openAccountResume(run) {
    if (document.querySelector("#srAccountResume")) return;
    const wrapper = document.createElement("div");
    wrapper.id = "srAccountResume";
    wrapper.className = "system-regression-status";
    wrapper.innerHTML = `<strong>退款达到500元，需要部长账号</strong><div class="system-regression-actions"><input id="srResumeUsername" placeholder="账号" /><input id="srResumePassword" type="password" placeholder="密码" /><button class="btn" id="srResumeSubmit" type="button">继续执行</button></div>`;
    document.querySelector(".system-regression-page")?.prepend(wrapper);
    wrapper.querySelector("#srResumeSubmit").addEventListener("click", async () => {
      await api(`/api/system-regression/runs/${run.id}/resume-account`, { method: "POST", body: { username: wrapper.querySelector("#srResumeUsername").value, password: wrapper.querySelector("#srResumePassword").value } });
      wrapper.remove();
    });
  }

  function bindPage() {
    document.querySelector("#srProject")?.addEventListener("change", async (event) => {
      srState.projectId = event.target.value;
      localStorage.setItem("systemRegressionProjectId", srState.projectId);
      srState.envs = await api(`/api/envs?project_id=${encodeURIComponent(srState.projectId)}`);
      srState.envId = String(srState.envs[0]?.id || "");
      renderPage();
    });
    document.querySelector("#srEnv")?.addEventListener("change", (event) => { srState.envId = event.target.value; localStorage.setItem("systemRegressionEnvId", srState.envId); });
    document.querySelector("#srCustomerId")?.addEventListener("input", (event) => { srState.customerId = event.target.value.trim(); });
    document.querySelectorAll("[data-sr-category]").forEach((button) => button.addEventListener("click", () => { srState.category = button.dataset.srCategory; renderPage(); }));
    document.querySelectorAll("[data-sr-open]").forEach((button) => button.addEventListener("click", () => { srState.activeId = Number(button.dataset.srOpen); renderPage(); }));
    const selectAll = document.querySelector("#srSelectAll");
    const rows = visibleCases();
    const selectedCount = rows.filter((item) => srState.selected.has(item.id)).length;
    if (selectAll) {
      selectAll.checked = rows.length > 0 && selectedCount === rows.length;
      selectAll.indeterminate = selectedCount > 0 && selectedCount < rows.length;
    }
    document.querySelectorAll("[data-sr-select]").forEach((box) => box.addEventListener("change", () => {
      const id = Number(box.dataset.srSelect);
      box.checked ? srState.selected.add(id) : srState.selected.delete(id);
      renderPage();
    }));
    document.querySelector("#srSelectAll")?.addEventListener("change", (event) => {
      rows.forEach((item) => event.target.checked ? srState.selected.add(item.id) : srState.selected.delete(item.id));
      renderPage();
    });
    document.querySelector("#srSelectVisible")?.addEventListener("click", () => { rows.forEach((item) => srState.selected.add(item.id)); renderPage(); });
    document.querySelector("#srRunBatch")?.addEventListener("click", () => execute([...srState.selected]));
    document.querySelector("#srRunOne")?.addEventListener("click", () => execute([currentCase().id]));
    document.querySelector("#srAddItem")?.addEventListener("click", () => { const item = currentCase(); const parameters = normalizedParameters(item); parameters.items.push({ sorting: parameters.items.length + 1, quantity: 1, offer_price: { value: 10, currency: "CNY" }, offer_freight: { value: 0, currency: "CNY" }, options: [] }); item.parameters = parameters; renderPage(); });
    document.querySelectorAll("[data-add-option]").forEach((button) => button.addEventListener("click", () => { const item = currentCase(); const parameters = normalizedParameters(item); const index = Number(button.dataset.addOption); parameters.items[index].options = parameters.items[index].options || []; parameters.items[index].options.push({ name: "", price_type: 0, price: 0, num: 1 }); item.parameters = parameters; renderPage(); }));
    document.querySelectorAll("[data-remove-item]").forEach((button) => button.addEventListener("click", () => { const item = currentCase(); const parameters = normalizedParameters(item); parameters.items.splice(Number(button.dataset.removeItem), 1); item.parameters = parameters; renderPage(); }));
    document.querySelectorAll("[data-remove-option]").forEach((button) => button.addEventListener("click", () => { const item = currentCase(); const parameters = normalizedParameters(item); const [itemIndex, optionIndex] = button.dataset.removeOption.split(":").map(Number); parameters.items[itemIndex].options.splice(optionIndex, 1); item.parameters = parameters; renderPage(); }));
    document.querySelector("#srSaveCase")?.addEventListener("click", async () => { const item = currentCase(); const updated = await api(`/api/system-regression/cases/${item.id}`, { method: "PATCH", body: { name: document.querySelector("#srCaseName").value, parameters: collectParameters(item) } }); Object.assign(item, updated); showToast("参数已保存"); renderPage(); });
    document.querySelector("#srCopyCase")?.addEventListener("click", async () => { const copied = await api(`/api/system-regression/cases/${currentCase().id}/copy`, { method: "POST" }); srState.cases.push(copied); srState.activeId = copied.id; renderPage(); });
    document.querySelector("#srResetCase")?.addEventListener("click", async () => { const reset = await api(`/api/system-regression/cases/${currentCase().id}/reset`, { method: "POST" }); Object.assign(currentCase(), reset); renderPage(); });
  }

  async function renderSystemRegression() {
    const [catalog, projects] = await Promise.all([api("/api/system-regression/suites/japan/cases"), getProjects()]);
    srState.cases = catalog.cases;
    srState.problemTypes = Array.isArray(catalog.problem_types) ? catalog.problem_types : [];
    srState.categories = [...new Set(srState.cases.map((item) => item.category))];
    srState.projects = projects;
    srState.projectId = srState.projectId || String(projects[0]?.id || "");
    srState.envs = srState.projectId ? await api(`/api/envs?project_id=${encodeURIComponent(srState.projectId)}`) : [];
    srState.envId = srState.envId || String(srState.envs[0]?.id || "");
    srState.activeId = srState.activeId || srState.cases[0]?.id || 0;
    renderPage();
  }

  window.renderSystemRegression = renderSystemRegression;
})();
