(function () {
  const LEGACY_VIEWS = new Set(["caseGeneration", "functionalTests"]);
  const firstLegacyIndex = views.findIndex((item) => LEGACY_VIEWS.has(item.key));
  for (let index = views.length - 1; index >= 0; index -= 1) {
    if (LEGACY_VIEWS.has(views[index].key)) views.splice(index, 1);
  }
  const insertAt = firstLegacyIndex >= 0 ? firstLegacyIndex : Math.max(0, views.findIndex((item) => item.key === "uiCases"));
  views.splice(insertAt, 0, { key: "requirementVerification", label: "需求验证中心" });

  /**
   * Phase 3.1 nav fix:
   * Vue AppShell still emits /#/functionalTests|/caseGeneration, but this script
   * removes those keys from the visible menu. migration-bridge activateInitialHash
   * then cannot find [data-view=functionalTests] and leaves default dashboard.
   * Keep hidden alias targets + normalize legacy view keys. No menu order/key change.
   */
  function ensureLegacyHashTargets() {
    const nav = document.querySelector("#mainNav");
    if (!nav) return false;
    let added = false;
    LEGACY_VIEWS.forEach((key) => {
      if (nav.querySelector(`[data-view="${key}"]`)) return;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("data-view", key);
      btn.setAttribute("aria-hidden", "true");
      btn.tabIndex = -1;
      btn.textContent = key;
      btn.style.cssText =
        "position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0;";
      nav.appendChild(btn);
      added = true;
    });
    return true;
  }

  // Install as soon as #mainNav appears (before renderCurrentView awaits),
  // so migration-bridge hash activation can find legacy data-view targets.
  (function watchLegacyHashTargets() {
    let tries = 0;
    const timer = window.setInterval(() => {
      const ready = ensureLegacyHashTargets();
      tries += 1;
      if ((ready && document.querySelector('#mainNav [data-view="functionalTests"]')) || tries > 60) {
        window.clearInterval(timer);
      }
    }, 50);
  })();

  const originalRenderShell = renderShell;
  renderShell = async function renderShellWithLegacyHashTargets(...args) {
    if (LEGACY_VIEWS.has(state.view)) {
      state.view = "requirementVerification";
    }
    const result = await originalRenderShell.apply(this, args);
    ensureLegacyHashTargets();
    return result;
  };

  const originalRenderCurrentView = renderCurrentView;
  renderCurrentView = function () {
    if (LEGACY_VIEWS.has(state.view)) {
      state.view = "requirementVerification";
    }
    if (state.view === "requirementVerification") return window.renderRequirementVerification();
    return originalRenderCurrentView();
  };

  const rvState = {
    projectId: localStorage.getItem("verificationProjectId") || localStorage.getItem("projectId") || "",
    taskId: localStorage.getItem("verificationTaskId") || "",
    keyword: "",
    status: "",
    archived: localStorage.getItem("verificationArchivedFilter") || "active",
    sort: localStorage.getItem("verificationSort") || "updated_desc",
  };

  const typeLabels = {
    page: "页面",
    data: "数据",
    state: "状态",
    amount: "金额",
    permission: "权限",
    exception: "异常",
    manual: "人工",
  };
  const levelLabels = { auto: "自动", supervised: "监督", manual: "人工" };
  const formulaRoundingLabels = {
    HALF_UP: "四舍五入（推荐）",
    HALF_EVEN: "银行家舍入（五成双）",
    DOWN: "直接截断",
    UP: "远离零方向进位",
    FLOOR: "向下取整",
    CEILING: "向上取整",
  };
  const formulaStageLabels = {
    final: "最终合计后舍入",
    per_item: "每个明细先舍入再合计",
  };
  const formulaCurrencyLabels = {
    CNY: "人民币",
    JPY: "日元",
    USD: "美元",
    EUR: "欧元",
    GBP: "英镑",
    HKD: "港币",
    KRW: "韩元",
    AUD: "澳元",
    CAD: "加拿大元",
    SGD: "新加坡元",
  };
  let pollTimer = null;

  function escapeRegex(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function formulaVariables(formula) {
    return Object.entries(formula?.variables || {}).map(([key, label]) => ({ key, label: String(label || key) }));
  }

  function formulaExpressionToReadable(expression, variables = {}) {
    let readable = String(expression || "");
    Object.entries(variables)
      .sort(([left], [right]) => right.length - left.length)
      .forEach(([key, label]) => {
        readable = readable.replace(new RegExp(`\\b${escapeRegex(key)}\\b`, "g"), `[${String(label || key)}]`);
      });
    readable = readable
      .replace(/\bmin\s*\(/g, "最小值(")
      .replace(/\bmax\s*\(/g, "最大值(")
      .replace(/\babs\s*\(/g, "绝对值(")
      .replace(/\bround\s*\(/g, "四舍五入(")
      .replaceAll("*", "×")
      .replaceAll("/", "÷");
    return readable;
  }

  function formulaReadableToExpression(readable, variables) {
    let expression = String(readable || "").trim();
    [...variables]
      .sort((left, right) => right.label.length - left.label.length)
      .forEach((item) => {
        expression = expression.split(`[${item.label}]`).join(item.key);
      });
    const unresolved = expression.match(/\[[^\]]+\]/);
    if (unresolved) throw new Error(`计算公式中的变量“${unresolved[0]}”不存在，请从变量按钮重新插入`);
    return expression
      .replace(/最小值\s*\(/g, "min(")
      .replace(/最大值\s*\(/g, "max(")
      .replace(/绝对值\s*\(/g, "abs(")
      .replace(/四舍五入\s*\(/g, "round(")
      .replaceAll("×", "*")
      .replaceAll("÷", "/")
      .replaceAll("＋", "+")
      .replaceAll("－", "-")
      .trim();
  }

  function formulaCurrencyText(currency) {
    const code = String(currency || "").toUpperCase();
    return formulaCurrencyLabels[code] ? `${formulaCurrencyLabels[code]}（${code}）` : code || "未指定";
  }

  function formulaRoundingText(formula) {
    const scale = Number(formula?.scale ?? 2);
    const scaleText = scale === 0 ? "不保留小数" : `保留${scale}位小数`;
    return `${formulaRoundingLabels[formula?.rounding_mode] || formula?.rounding_mode || "未指定"}；${scaleText}；${formulaStageLabels[formula?.rounding_stage] || formula?.rounding_stage || "未指定"}`;
  }

  function jsonPretty(value) {
    return JSON.stringify(value ?? {}, null, 2);
  }

  function parseJson(value, fallback) {
    try {
      return JSON.parse(value || "");
    } catch {
      return fallback;
    }
  }

  function optionHtml(items, selected, emptyLabel = "请选择") {
    return [
      `<option value="">${escapeHtml(emptyLabel)}</option>`,
      ...items.map((item) => `<option value="${escapeHtml(item.id)}" ${String(item.id) === String(selected) ? "selected" : ""}>${escapeHtml(item.name || item.env_name || item.profile_name || item.id)}</option>`),
    ].join("");
  }

  function verificationBadge(value) {
    const labels = {
      plan_generated: "计划已生成",
      materials_ready: "材料已就绪",
      ready: "待执行",
      waiting_confirmation: "等待人工",
      waiting_user: "需要我处理",
      paused: "已暂停",
      cancelling: "正在取消",
      cancelled: "已取消",
      preflighting: "运行前检查",
      data_preparing: "准备数据",
      data_validating: "检查数据",
      browser_preparing: "准备浏览器",
      needs_review: "待人工验证",
      supervised: "监督执行",
      auto: "自动执行",
      manual: "人工验证",
      assisted: "人工辅助",
      blocked: "暂不执行",
      confirmed: "已确认",
      open: "待答复",
      pending_confirmation: "待确认理解",
      answered: "理解已确认",
      deferred: "暂不确定",
    };
    return badge(labels[value] || value);
  }

  function sortVerificationTasks(tasks) {
    const rows = [...tasks];
    const timestamp = (item) => Date.parse(String(item.update_time || item.create_time || "").replace(" ", "T")) || 0;
    if (rvState.sort === "updated_asc") rows.sort((left, right) => timestamp(left) - timestamp(right));
    else if (rvState.sort === "name_asc") rows.sort((left, right) => String(left.name || "").localeCompare(String(right.name || ""), "zh-CN"));
    else rows.sort((left, right) => timestamp(right) - timestamp(left));
    return rows;
  }

  function renderFeatureCard(item) {
    const counts = item.result_counts || {};
    const selected = String(item.id) === String(rvState.taskId) ? "active" : "";
    return `
      <div class="verification-task-card ${selected}">
        <button class="verification-task-open" data-open-verification="${item.id}">
          <strong>${escapeHtml(item.name)}</strong>
          <span>${verificationBadge(item.status)} ${escapeHtml(item.update_time || item.create_time)}</span>
          <span class="verification-task-counts">
            <b>验证项 ${item.item_count || 0}</b><b>通过 ${counts.passed || 0}</b><b>失败 ${counts.failed || 0}</b><b>阻塞 ${counts.blocked || 0}</b>
          </span>
          <span>造数 ${item.data_setup_step_count || 0} 步 · 执行 ${item.run_count || 0} 次 · 最近结果 ${item.latest_result ? verificationBadge(item.latest_result) : "未执行"}</span>
        </button>
        ${isAdmin() ? `<div class="verification-task-actions"><button class="btn secondary" data-archive-verification="${item.id}" data-archive-value="${item.is_archived ? "false" : "true"}">${item.is_archived ? "恢复" : "归档"}</button>${actionMenu("更多", `<button class="btn danger" data-delete-verification="${item.id}">删除</button>`)}</div>` : ""}
      </div>`;
  }

  function taskTargetPages(task) {
    return Array.isArray(task?.target_pages) && task.target_pages.length
      ? task.target_pages
      : (task?.target_url ? [{ name: "主要页面", role: "", url: task.target_url }] : []);
  }

  function renderTargetPageEditorRow(page = {}) {
    return `
      <div class="verification-target-page-row">
        <input type="text" data-page-field="name" value="${escapeHtml(page.name || "")}" placeholder="例如：订单详情" aria-label="页面名称" />
        <input type="text" data-page-field="role" value="${escapeHtml(page.role || "")}" placeholder="例如：买家" aria-label="适用角色" />
        <input type="text" data-page-field="url" value="${escapeHtml(page.url || "")}" placeholder="https://example.com/orders/{{order_id}}" aria-label="页面URL" />
        <button class="btn danger" type="button" data-remove-target-page>删除</button>
      </div>`;
  }

  function renderTargetPages(task) {
    const pages = Array.isArray(task.target_pages) ? task.target_pages : [];
    if (!pages.length) return '<div class="verification-warning">尚未填写涉及页面，可以先分析需求，明确后再补充。</div>';
    return `<div class="verification-target-pages">${pages.map((page) => `
      <div><strong>${escapeHtml(page.name || "未命名页面")}</strong><span>角色：${escapeHtml(page.role || "未指定")}</span><span>${escapeHtml(page.url || "URL暂未提供")}</span></div>
    `).join("")}</div>`;
  }

  function taskDataSetupSteps(task) {
    return Array.isArray(task?.data_setup?.steps) ? task.data_setup.steps.map((step) => ({
      script_type: step.script_type || "",
      env_id: Number(step.env_id || 0),
      variables: { ...(step.variables || {}) },
      enabled: step.enabled !== false,
    })) : [];
  }

  function dataScriptMeta(catalog, scriptType) {
    return (catalog || []).find((item) => item.script_type === scriptType) || { script_type: scriptType, name: scriptType, risk_level: "normal" };
  }

  function setupEnvName(envs, envId) {
    return (envs || []).find((item) => String(item.id) === String(envId))?.env_name || `环境#${envId || "未选"}`;
  }

  function renderDataSetup(task, catalog, envs) {
    const steps = taskDataSetupSteps(task);
    return `
      <section class="verification-section">
        <div class="panel-title"><h3>0. 数据准备</h3>${isAdmin() ? '<button class="btn secondary" id="editVerificationDataSetup">配置数据工厂</button>' : ""}</div>
        ${steps.length ? `<div class="verification-setup-summary">${steps.map((step, index) => {
          const meta = dataScriptMeta(catalog, step.script_type);
          return `<div class="verification-setup-summary-item ${step.enabled ? "" : "disabled"}"><strong>${index + 1}. ${escapeHtml(meta.name)}</strong><span>${escapeHtml(setupEnvName(envs, step.env_id))}</span><span>${meta.risk_level === "high" ? verificationBadge("high") : "普通操作"} · ${step.enabled ? "启用" : "停用"}</span><pre class="mini-log">${escapeHtml(jsonPretty(step.variables || {}))}</pre></div>`;
        }).join("")}</div>` : '<div class="empty">未配置数据准备，执行时不会自动造测试数据</div>'}
      </section>`;
  }

  function renderSetupResult(setupResult) {
    const steps = setupResult?.steps || [];
    if (!steps.length) return setupResult?.status === "skipped" ? '<div class="verification-setting">本次未配置数据准备</div>' : "";
    return `
      <details class="verification-setup-result">
        <summary>数据准备结果 ${verificationBadge(setupResult.status || "unknown")}</summary>
        ${steps.map((step) => `<div class="verification-setup-result-step"><div><strong>${step.index}. ${escapeHtml(step.name || step.script_type)}</strong>${verificationBadge(step.status)}</div><span>${escapeHtml(step.message || "")}</span><pre class="mini-log">输出：${escapeHtml(jsonPretty(step.outputs || {}))}\n日志：${escapeHtml(step.log || "-")}</pre></div>`).join("")}
        <pre class="mini-log">合并输出：${escapeHtml(jsonPretty(setupResult.outputs || {}))}</pre>
      </details>`;
  }

  function setupParamSchema(scriptType) {
    return typeof scriptParamFields === "function" ? (scriptParamFields(scriptType) || []) : [];
  }

  function isSensitiveSetupKey(name) {
    return /(password|passwd|pwd|token|secret|authorization|cookie)/i.test(String(name || ""));
  }

  function setupSupportsFields(fields) {
    const supported = new Set([undefined, "text", "number", "select", "textarea", "checkbox", "section", "hidden"]);
    return fields.length > 0 && fields.every((field) => supported.has(field.type)) && !fields.some((field) => isSensitiveSetupKey(field.name));
  }

  function defaultSetupVariables(scriptType) {
    const variables = {};
    setupParamSchema(scriptType).forEach((field) => {
      if (!field.name || field.name.startsWith("__") || field.type === "section" || field.type === "hidden" || isSensitiveSetupKey(field.name)) return;
      if (field.default !== undefined && field.default !== "") variables[field.name] = field.default;
    });
    return variables;
  }

  function setupFieldValue(field, variables) {
    return typeof fieldDisplayValue === "function" ? fieldDisplayValue(field, variables || {}) : (variables?.[field.name] ?? field.default ?? "");
  }

  function renderSetupVariableField(field, variables) {
    if (field.type === "section") return `<div class="verification-setup-param-section">${escapeHtml(field.label || "参数")}</div>`;
    if (field.type === "hidden") return "";
    const value = setupFieldValue(field, variables);
    const common = `data-setup-variable="${escapeHtml(field.name)}"`;
    if (field.type === "select") {
      return `<div class="field"><label>${escapeHtml(field.label || field.name)}</label><select ${common}>${(field.options || []).map((option) => `<option value="${escapeHtml(option.value)}" ${String(option.value) === String(value) ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}</select></div>`;
    }
    if (field.type === "textarea") return `<div class="field"><label>${escapeHtml(field.label || field.name)}</label><textarea rows="${field.rows || 3}" ${common}>${escapeHtml(value)}</textarea></div>`;
    if (field.type === "checkbox") return `<label class="check-field"><input type="checkbox" ${common} ${value === true || value === "true" || value === 1 || value === "1" ? "checked" : ""}/><span>${escapeHtml(field.label || field.name)}</span></label>`;
    return `<div class="field"><label>${escapeHtml(field.label || field.name)}</label><input type="${field.type === "number" ? "number" : "text"}" value="${escapeHtml(value)}" ${common} placeholder="${escapeHtml(field.placeholder || "")}" /></div>`;
  }

  function setupExtraVariables(fields, variables) {
    const visibleKeys = new Set(fields.filter((field) => field.name && field.type !== "section" && field.type !== "hidden").map((field) => field.name));
    return Object.fromEntries(Object.entries(variables || {}).filter(([key]) => !visibleKeys.has(key)));
  }

  function quickSetupFields(scriptType, fields) {
    const preferred = {
      full_flow: ["customer_ids", "keyword", "shop_type", "stop_after_node"],
      direct_box_to_shelf: ["customer_ids", "order_sn", "keyword"],
      resume_order_flow: ["customer_ids", "order_sn", "stop_after_node"],
      resume_porder_flow: ["customer_ids", "porder_sn", "stop_after_node"],
      problem_goods: ["order_sn", "num", "is_fee"],
      balance_adjustment: ["customer_ids", "amount", "type"],
    }[scriptType] || [];
    const selected = fields.filter((field) => field.required || preferred.includes(field.name));
    return selected.length ? selected : fields.filter((field) => field.type !== "section" && field.type !== "hidden").slice(0, 4);
  }

  function renderSetupStepEditor(step, index, catalog, envs) {
    const meta = dataScriptMeta(catalog, step.script_type);
    const fields = setupParamSchema(step.script_type);
    const structured = setupSupportsFields(fields);
    const scriptOptions = (catalog || []).map((item) => `<option value="${escapeHtml(item.script_type)}" ${item.script_type === step.script_type ? "selected" : ""}>${escapeHtml(item.name)}${item.risk_level === "high" ? "（高风险）" : ""}</option>`).join("");
    const envOptions = (envs || []).map((env) => `<option value="${env.id}" ${String(env.id) === String(step.env_id) ? "selected" : ""}>${escapeHtml(env.env_name)}</option>`).join("");
    const quickFields = quickSetupFields(step.script_type, fields);
    const quickNames = new Set(quickFields.map((field) => field.name));
    const advancedFields = fields.filter((field) => !quickNames.has(field.name));
    const params = structured
      ? `<div class="verification-setup-param-grid">${quickFields.map((field) => renderSetupVariableField(field, step.variables)).join("")}</div><details class="verification-setup-advanced"><summary>高级参数（通常不用修改）</summary><div class="verification-setup-param-grid">${advancedFields.map((field) => renderSetupVariableField(field, step.variables)).join("")}</div><div class="field"><label>其它参数</label><textarea rows="3" data-setup-extra-json>${escapeHtml(jsonPretty(setupExtraVariables(fields, step.variables)))}</textarea></div></details>`
      : `<div class="field"><label>脚本参数 JSON</label><textarea rows="7" data-setup-variables-json>${escapeHtml(jsonPretty(step.variables || {}))}</textarea><small>该脚本包含复合参数，请按数据工厂变量格式填写；密码和令牌不能保存。</small></div>`;
    return `
      <section class="verification-setup-editor-step" data-setup-step-index="${index}" data-script-type="${escapeHtml(step.script_type)}" data-param-mode="${structured ? "fields" : "json"}">
        <div class="verification-setup-editor-head"><strong>步骤 ${index + 1}：${escapeHtml(meta.name)}</strong><div class="actions"><button class="btn secondary" type="button" data-setup-move="up" ${index === 0 ? "disabled" : ""}>上移</button><button class="btn secondary" type="button" data-setup-move="down">下移</button><button class="btn danger" type="button" data-setup-remove>删除</button></div></div>
        <div class="verification-setup-base-grid">
          <div class="field"><label>数据工厂脚本</label><select data-setup-script>${scriptOptions}</select></div>
          <div class="field"><label>执行环境</label><select data-setup-env><option value="">选择环境</option>${envOptions}</select></div>
          <label class="check-field"><input type="checkbox" data-setup-enabled ${step.enabled !== false ? "checked" : ""}/><span>启用此步骤</span></label>
          <div>${meta.risk_level === "high" ? '<span class="badge warn">高风险</span>' : '<span class="badge">普通</span>'}</div>
        </div>
        ${params}
      </section>`;
  }

  function mountDataSetupEditor(initialSteps, catalog, envs) {
    const container = document.querySelector("#verificationSetupStepList");
    let steps = (initialSteps || []).map((step) => ({ ...step, variables: { ...(step.variables || {}) } }));
    const collectStep = (card) => {
      const scriptType = card.dataset.scriptType;
      let variables = {};
      if (card.dataset.paramMode === "json") {
        variables = parseJson(card.querySelector("[data-setup-variables-json]")?.value || "{}", null);
        if (!variables || Array.isArray(variables)) throw new Error(`步骤${Number(card.dataset.setupStepIndex) + 1}参数JSON格式错误`);
      } else {
        const fields = setupParamSchema(scriptType);
        const extras = parseJson(card.querySelector("[data-setup-extra-json]")?.value || "{}", null);
        if (!extras || Array.isArray(extras)) throw new Error(`步骤${Number(card.dataset.setupStepIndex) + 1}其它参数JSON格式错误`);
        variables = { ...extras };
        card.querySelectorAll("[data-setup-variable]").forEach((input) => {
          const field = fields.find((item) => item.name === input.dataset.setupVariable) || { name: input.dataset.setupVariable };
          const raw = input.type === "checkbox" ? input.checked : input.value;
          const value = typeof normalizeParamValue === "function" ? normalizeParamValue(field, raw) : raw;
          if (value !== "" && value !== null && value !== undefined && (!Array.isArray(value) || value.length)) variables[field.name] = value;
          else delete variables[field.name];
        });
      }
      if (typeof sanitizeScriptVariables === "function") variables = sanitizeScriptVariables(scriptType, variables, { scriptType });
      return {
        script_type: scriptType,
        env_id: Number(card.querySelector("[data-setup-env]")?.value || 0),
        variables,
        enabled: Boolean(card.querySelector("[data-setup-enabled]")?.checked),
      };
    };
    const collect = () => [...container.querySelectorAll(".verification-setup-editor-step")].map(collectStep);
    const updateRisk = () => {
      const notice = document.querySelector("#verificationSetupRiskNotice");
      if (!notice) return;
      const hasRisk = steps.some((step) => step.enabled !== false && dataScriptMeta(catalog, step.script_type).risk_level === "high");
      notice.hidden = !hasRisk;
    };
    const render = () => {
      container.innerHTML = steps.length ? steps.map((step, index) => renderSetupStepEditor(step, index, catalog, envs)).join("") : '<div class="empty">还没有数据准备步骤</div>';
      container.querySelectorAll('[data-setup-move="down"]').forEach((button, index) => { button.disabled = index === steps.length - 1; });
      updateRisk();
    };
    document.querySelector("#addVerificationSetupStep").addEventListener("click", () => {
      try { steps = collect(); } catch (error) { showToast(error.message); return; }
      if (steps.length >= 10) { showToast("最多添加10个数据准备步骤"); return; }
      const scriptType = catalog[0]?.script_type || "";
      steps.push({ script_type: scriptType, env_id: Number(envs[0]?.id || 0), variables: defaultSetupVariables(scriptType), enabled: true });
      render();
    });
    container.addEventListener("change", (event) => {
      if (!event.target.matches("[data-setup-script]")) {
        try { steps = collect(); updateRisk(); } catch {}
        return;
      }
      const card = event.target.closest(".verification-setup-editor-step");
      const index = Number(card.dataset.setupStepIndex);
      try { steps = collect(); } catch (error) { showToast(error.message); return; }
      steps[index].script_type = event.target.value;
      steps[index].variables = defaultSetupVariables(event.target.value);
      render();
    });
    container.addEventListener("click", (event) => {
      const remove = event.target.closest("[data-setup-remove]");
      const move = event.target.closest("[data-setup-move]");
      if (!remove && !move) return;
      const card = event.target.closest(".verification-setup-editor-step");
      const index = Number(card.dataset.setupStepIndex);
      try { steps = collect(); } catch (error) { showToast(error.message); return; }
      if (remove) steps.splice(index, 1);
      else {
        const target = move.dataset.setupMove === "up" ? index - 1 : index + 1;
        if (target >= 0 && target < steps.length) [steps[index], steps[target]] = [steps[target], steps[index]];
      }
      render();
    });
    render();
    return {
      collect,
      hasHighRisk: () => collect().some((step) => step.enabled && dataScriptMeta(catalog, step.script_type).risk_level === "high"),
    };
  }

  function setupEditorShell(title, submitLabel, extraHtml = "") {
    return `
      <form id="verificationSetupForm">
        <div class="modal-head"><h3>${escapeHtml(title)}</h3><button class="btn secondary" type="button" id="closeModal">关闭</button></div>
        <div class="modal-body">${extraHtml}<div class="verification-setup-toolbar"><strong>数据准备步骤</strong><button class="btn secondary" type="button" id="addVerificationSetupStep">添加脚本</button></div><div id="verificationSetupStepList"></div><div class="verification-warning" id="verificationSetupRiskNotice" hidden>包含支付、充值或资金类高风险脚本，执行前必须明确确认。</div></div>
        <div class="modal-foot"><span>步骤输出会自动传给后续脚本和全部验证项</span><button class="btn" type="submit">${escapeHtml(submitLabel)}</button></div>
      </form>`;
  }

  function openDataSetupForm(task, catalog, envs) {
    modalEl.innerHTML = setupEditorShell("配置数据准备", "保存默认配置");
    modalEl.showModal();
    document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
    const editor = mountDataSetupEditor(taskDataSetupSteps(task), catalog, envs);
    document.querySelector("#verificationSetupForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const steps = editor.collect();
        await api(`/api/requirement-verifications/${task.id}`, { method: "PUT", body: { data_setup: { steps } } });
        modalEl.close();
        showToast("数据准备默认配置已保存");
        await window.renderRequirementVerification();
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  async function openVerificationRunForm(task, itemIds) {
    try {
      showToast("正在执行运行前检查，不会创建测试数据");
      const preflight = await api(`/api/requirement-verifications/${task.id}/preflight`, { method: "POST", body: { item_ids: itemIds, variables: {} } });
      const summary = preflight.summary || {};
      const setupSteps = preflight.data_setup?.steps || [];
      const itemHtml = (preflight.items || []).map((item) => `
        <div class="verification-preflight-item ${item.execution_mode}">
          <div><strong>${escapeHtml(item.title)}</strong>${verificationBadge(item.execution_mode)}</div>
          ${(item.issues || []).length ? `<ul>${item.issues.map((issue) => `<li><span>${escapeHtml(issue.message)}</span>${issue.suggestion ? `<small>${escapeHtml(issue.suggestion)}</small>` : ""}</li>`).join("")}</ul>` : '<p>检查通过，可自动执行</p>'}
        </div>`).join("");
      modalEl.innerHTML = `
        <form id="verificationQuickRunForm">
          <div class="modal-head"><h3>一键准备数据并验证</h3><button class="btn secondary" type="button" id="closeModal">关闭</button></div>
          <div class="modal-body">
            <div class="verification-readiness"><div><span>自动验证</span><strong>${summary.auto || 0}</strong></div><div><span>人工辅助</span><strong>${summary.assisted || 0}</strong></div><div><span>暂不执行</span><strong>${summary.blocked || 0}</strong></div></div>
            <div class="verification-quick-setup"><strong>本次数据准备</strong>${setupSteps.length ? setupSteps.map((step) => `<div><span>${escapeHtml(step.name)}</span><small>${escapeHtml(step.environment)}${step.output_keys?.length ? ` · 将生成 ${escapeHtml(step.output_keys.join("、"))}` : ""}</small></div>`).join("") : '<p>无需额外造数</p>'}</div>
            <div class="verification-preflight-list">${itemHtml || '<div class="empty">没有已确认的验证项</div>'}</div>
            ${preflight.data_setup?.high_risk ? '<label class="check-field verification-risk-confirm"><input id="verificationRiskConfirmed" type="checkbox"/><span>我已确认执行包含支付、退款或资金操作的数据准备</span></label>' : ""}
          </div>
          <div class="modal-foot"><span>暂不执行项会自动跳过，不会产生无效测试数据</span><button class="btn" type="submit" ${preflight.runnable_item_ids?.length ? "" : "disabled"}>开始验证 ${preflight.runnable_item_ids?.length || 0} 项</button></div>
        </form>`;
      modalEl.showModal();
      document.querySelector("#closeModal").onclick = () => modalEl.close();
      document.querySelector("#verificationQuickRunForm").onsubmit = async (event) => {
        event.preventDefault();
        try {
          const riskConfirmed = Boolean(document.querySelector("#verificationRiskConfirmed")?.checked);
          if (preflight.data_setup?.high_risk && !riskConfirmed) throw new Error("请先确认高风险数据准备");
          await api(`/api/requirement-verifications/${task.id}/runs`, { method: "POST", body: { item_ids: preflight.runnable_item_ids, variables: {}, risk_confirmed: riskConfirmed, visible_browser: true } });
          modalEl.close();
          await window.renderRequirementVerification();
        } catch (error) {
          showToast(error.message);
        }
      };
    } catch (error) {
      showToast(error.message);
    }
  }

  function renderStats(task) {
    const byType = task.stats?.by_type || {};
    const cards = Object.entries(typeLabels).map(([key, label]) => `<div><span>${label}</span><strong>${byType[key] || 0}</strong></div>`).join("");
    return `<div class="verification-stats">${cards}</div>`;
  }

  function renderMaterials(task) {
    const rows = task.materials || [];
    return `
      <section class="verification-section">
        <div class="panel-title"><h3>1. 需求材料</h3><div class="actions">${isAdmin() ? '<button class="btn secondary" id="addVerificationMaterial">粘贴材料</button><button class="btn secondary" id="uploadVerificationMaterial">上传原型截图</button>' : ""}</div></div>
        ${rows.length ? rows.map((item) => `
          <div class="verification-material">
            <div><strong>${escapeHtml(item.name || item.material_type)}</strong><span>${escapeHtml(item.create_time)}</span></div>
            <pre class="mini-log">${escapeHtml(short(item.content_text || item.ocr_text || "截图已保存，暂无OCR文字", 1200))}</pre>
            ${item.has_image ? `<button class="btn secondary" data-material-file="${item.id}">查看截图</button>` : ""}
          </div>`).join("") : '<div class="empty">除初始需求外，还没有补充群聊或原型材料</div>'}
      </section>`;
  }

  function renderAnalysis(task) {
    const analysis = task.analysis || {};
    const clarifications = task.clarifications || [];
    const active = clarifications.filter((item) => ["open", "pending_confirmation"].includes(item.status)).slice(0, 3);
    const deferred = clarifications.filter((item) => item.status === "deferred");
    const confirmed = task.confirmed_clarifications || [];
    const analyzeLabel = task.analysis_version ? "按已确认理解更新矩阵" : "分析并生成验证矩阵";
    const warningText = [analysis.warning, ...(analysis.warnings || [])].filter(Boolean);
    const confirmedHtml = confirmed.map((item) => {
      const interpretation = item.review?.interpretation || {};
      const rules = interpretation.understood_rules || [];
      return `<div class="verification-confirmed-rule">
        <strong>${escapeHtml(interpretation.summary || item.question)}</strong>
        <p>原回答：${escapeHtml(item.answer || "历史已确认答复")}</p>
        ${rules.length ? `<ul>${rules.map((rule) => `<li>${escapeHtml(rule)}</li>`).join("")}</ul>` : ""}
      </div>`;
    }).join("");
    return `
      <section class="verification-section">
        <div class="panel-title"><h3>2. AI分析与澄清</h3><div class="actions">${isAdmin() ? `${task.analysis_version ? '<button class="btn secondary" id="continueVerificationAnalysis">按当前理解继续</button>' : ""}<button class="btn" id="analyzeVerification">${analyzeLabel}</button>` : ""}</div></div>
        ${warningText.length ? `<div class="verification-warning">${warningText.map((item) => escapeHtml(item)).join("<br>")}</div>` : ""}
        <div class="verification-analysis-grid">
          <div><span>需求摘要</span><p>${escapeHtml(analysis.summary || "尚未分析")}</p></div>
          <div><span>业务流程</span><p>${escapeHtml((analysis.flows || []).join("；") || "-")}</p></div>
          <div><span>涉及页面</span><p>${escapeHtml((analysis.impacted_pages || []).join("；") || "-")}</p></div>
          <div><span>前置数据</span><p>${escapeHtml((analysis.prerequisites || []).join("；") || "-")}</p></div>
        </div>
        ${task.has_unapplied_confirmed_answers ? '<div class="verification-confirmation-notice">业务理解已确认。确认完这一批后，再统一点击“按已确认理解更新矩阵”，不会立即反复分析。</div>' : ""}
        <div class="verification-clarification-note">一次最多处理 3 个关键问题，只阻塞关联验证项，不会影响其他已明确测试项。</div>
        <div class="verification-questions">
          ${active.length ? active.map((item) => {
            const review = item.review || {};
            const interpretation = review.interpretation || {};
            const affected = review.affected_item_titles || interpretation.affected_item_titles || [];
            const suggestions = review.suggested_answers || [];
            return `
            <div class="verification-question">
              <div><strong>${escapeHtml(item.question)}</strong>${verificationBadge(item.status)}</div>
              <p><b>为什么要问：</b>${escapeHtml(review.why_needed || "该信息会影响相关验证项的预期结论。")}</p>
              <p><b>影响：</b>${escapeHtml(affected.join("、") || "待生成矩阵后自动关联")}</p>
              ${suggestions.length && item.status === "open" ? `<div class="verification-answer-options">${suggestions.map((option, index) => `<button class="btn secondary" data-clarification-option="${item.id}" data-option-index="${index}">${escapeHtml(option)}</button>`).join("")}</div>` : ""}
              ${item.answer ? `<div class="verification-answer-draft"><b>你的回答草稿：</b>${escapeHtml(item.answer)}</div>` : ""}
              ${item.status === "pending_confirmation" ? `<div class="verification-review-preview">${interpretation.model_warning ? escapeHtml(interpretation.model_warning) : `<b>AI复述：</b>${escapeHtml(interpretation.summary || "等待重新理解")}`}</div>` : ""}
              ${isAdmin() ? `<div class="actions">${item.status === "open" ? `<button class="btn" data-answer-question="${item.id}">用普通话回答</button>` : `<button class="btn" data-view-clarification="${item.id}">查看并确认复述</button><button class="btn secondary" data-supplement-clarification="${item.id}">补充一句再理解</button>`}<button class="btn secondary" data-defer-clarification="${item.id}">我也不确定</button></div>` : ""}
            </div>`;
          }).join("") : '<div class="empty">没有需要你回答的关键问题，可以直接确认矩阵或继续执行明确范围。</div>'}
        </div>
        ${deferred.length ? `<details class="verification-confirmed-rules"><summary>暂不确定（${deferred.length}）</summary>${deferred.map((item) => `<div class="verification-deferred-rule">${escapeHtml(item.question)} <span>仅阻塞关联验证项</span></div>`).join("")}</details>` : ""}
        ${confirmed.length ? `<details class="verification-confirmed-rules"><summary>已确认业务规则（${confirmed.length}）</summary>${confirmedHtml}</details>` : ""}
      </section>`;
  }

  function renderFormulas(task) {
    const rows = task.formulas || [];
    return `
      <section class="verification-section">
        <details class="verification-advanced-section"><summary>3. 金额公式（高级，通常不用修改）</summary>
        <div class="panel-title"><span></span><div class="actions">${isAdmin() ? '<button class="btn secondary" id="newVerificationFormula">新增公式</button>' : ""}</div></div>
        ${rows.length ? renderTable([
          { key: "name", label: "公式" },
          { key: "expression", label: "计算规则", render: (row) => `<span class="verification-formula-readable">${escapeHtml(formulaExpressionToReadable(row.expression, row.variables))}</span>` },
          { key: "currency", label: "币种", render: (row) => escapeHtml(formulaCurrencyText(row.currency)) },
          { key: "rounding", label: "金额处理", render: (row) => escapeHtml(formulaRoundingText(row)) },
          { key: "status", label: "状态", render: (row) => verificationBadge(row.status) },
          { key: "actions", label: "操作", render: (row) => `<div class="actions"><button class="btn secondary" data-edit-formula="${row.id}">编辑</button>${row.status !== "confirmed" ? `<button class="btn" data-confirm-formula="${row.id}">确认启用</button>` : ""}</div>` },
        ], rows, false) : '<div class="empty">需求中没有可确认的金额公式</div>'}</details>
      </section>`;
  }

  function renderMatrix(task) {
    const rows = task.items || [];
    const clarificationBlocked = rows.filter((item) => item.status === "blocked" && (item.config?.blocking_topic_keys || []).length).length;
    const executable = rows.filter((item) => item.status !== "blocked" && ["auto", "supervised"].includes(item.automation_level)).length;
    const manual = rows.filter((item) => item.automation_level === "manual").length;
    return `
      <section class="verification-section">
        <div class="panel-title"><h3>4. 业务测试点</h3><div class="actions">${isAdmin() ? '<button class="btn secondary" id="confirmSelectedItems">确认选中测试点</button><button class="btn" id="runSelectedItems">一键准备数据并验证</button>' : ""}</div></div>
        <div class="verification-readiness"><div><span>可执行</span><strong>${executable}</strong></div><div><span>因澄清阻塞</span><strong>${clarificationBlocked}</strong></div><div><span>人工验证</span><strong>${manual}</strong></div></div>
        ${renderStats(task)}
        ${rows.length ? renderTable([
          { key: "select", label: "选择", render: (row) => `<input class="verification-matrix-check" type="checkbox" data-verification-check="${row.id}" ${row.confirmed ? "checked" : ""} title="${row.status === "blocked" ? "可以确认此测试点，但处理澄清问题前不能执行" : "选择此验证项"}" />` },
          { key: "item_type", label: "类型", render: (row) => escapeHtml(typeLabels[row.item_type] || row.item_type) },
          { key: "title", label: "验证项" },
          { key: "expected", label: "预期", render: (row) => escapeHtml(short(row.expected, 160)) },
          { key: "automation_level", label: "执行方式", render: (row) => verificationBadge(levelLabels[row.automation_level] || row.automation_level) },
          { key: "status", label: "状态", render: (row) => verificationBadge(row.status) },
          { key: "source_refs", label: "需求依据", render: (row) => escapeHtml((row.source_refs || []).join("；") || "缺失") },
        ], rows, false) : '<div class="empty">完成需求分析后生成验证矩阵</div>'}
        ${rows.length && isAdmin() ? `<details class="verification-advanced-section"><summary>高级配置（仅排查时使用）</summary><div class="verification-advanced-item-actions">${rows.map((row) => `<button class="btn secondary" data-edit-verification-item="${row.id}">${escapeHtml(row.title)}</button>`).join("")}</div></details>` : ""}
      </section>`;
  }

  function runItemActions(item) {
    if (!["waiting_confirmation", "waiting_user"].includes(item.result) || !isAdmin()) return "";
    const takeover = item.resume?.pending || item.evidence?.manual_takeover || item.evidence || {};
    const type = takeover.type || "";
    if (type === "observation_value") {
      return `<div class="verification-observation-takeover"><label>${escapeHtml(takeover.observation_goal || takeover.message || "页面实际值")}</label><input type="text" data-observed-value="${item.id}" placeholder="填写你在页面看到的值"/><div class="actions"><button class="btn" data-submit-observation="${item.id}">提交实际值</button><button class="btn secondary" data-run-confirm="${item.id}" data-decision="retry">重新识别</button><button class="btn secondary" data-run-confirm="${item.id}" data-decision="skip">跳过此项</button></div></div>`;
    }
    if (type === "manual_check") {
      return `<div class="verification-manual-check"><p>${escapeHtml(takeover.expected || takeover.message || "请按业务预期检查")}</p><div class="actions"><button class="btn" data-run-confirm="${item.id}" data-decision="pass">符合预期</button><button class="btn danger" data-run-confirm="${item.id}" data-decision="fail">不符合预期</button><button class="btn secondary" data-run-confirm="${item.id}" data-decision="defer">暂不确定</button></div></div>`;
    }
    return `<div class="actions"><button class="btn secondary" data-run-confirm="${item.id}" data-decision="user_completed">我已接管完成</button><button class="btn" data-run-confirm="${item.id}" data-decision="continue">允许AI继续</button><button class="btn secondary" data-run-confirm="${item.id}" data-decision="skip">跳过此项</button></div>`;
  }

  function runProgress(task, run) {
    const setupSteps = (run.data_setup?.steps || []).filter((item) => item.enabled !== false);
    const setupResults = run.setup_result?.steps || [];
    const runItems = run.items || [];
    const completedSetup = setupResults.filter((item) => ["passed", "failed"].includes(item.status)).length;
    const completedItems = runItems.filter((item) => !["pending", "running", "waiting_confirmation", "waiting_user"].includes(item.result)).length;
    const runningSetup = setupResults.find((item) => item.status === "running");
    const runningItem = runItems.find((item) => item.result === "running");
    const waitingItem = runItems.find((item) => ["waiting_confirmation", "waiting_user"].includes(item.result));
    const terminal = ["passed", "failed", "blocked", "needs_review", "cancelled"].includes(run.status);
    const totalUnits = setupSteps.length + runItems.length;
    const partialUnit = runningSetup || runningItem || waitingItem ? 0.5 : 0;
    const phaseProgress = run.progress || {};
    const percent = terminal ? 100 : run.status === "queued" ? 3 : Math.max(5, Math.min(98, phaseProgress.total ? Math.round((Number(phaseProgress.current || 0) / Number(phaseProgress.total)) * 100) : Math.round(((completedSetup + completedItems + partialUnit) / Math.max(totalUnits, 1)) * 100)));
    const itemTitle = (runItem) => (task.items || []).find((item) => item.id === runItem?.item_id)?.title || `验证项 #${runItem?.item_id || ""}`;
    let message = "等待执行任务启动";
    if (terminal) message = run.status === "passed" ? "全部验证处理完成" : run.status === "failed" ? "执行结束，存在失败项" : run.status === "blocked" ? "数据准备失败，执行已阻塞" : "执行结束，存在待人工处理项";
    else if (waitingItem) message = `等待人工处理：${itemTitle(waitingItem)}`;
    else if (runningSetup) message = `正在准备测试数据：第 ${runningSetup.index || run.setup_result?.current_step || 1}/${setupSteps.length} 步 ${runningSetup.name || runningSetup.script_type || ""}`;
    else if (setupSteps.length && !["passed", "skipped"].includes(run.setup_result?.status)) message = "正在启动数据准备";
    else if (runningItem) message = `正在验证：${itemTitle(runningItem)}`;
    else if (run.status === "running") message = "数据准备完成，正在启动验证";
    if (!terminal && phaseProgress.message) message = phaseProgress.message;
    const meta = [
      setupSteps.length ? `数据准备 ${completedSetup}/${setupSteps.length}` : "无需数据准备",
      `验证项 ${completedItems}/${runItems.length}`,
    ].join(" · ");
    return `
      <div class="verification-live-progress ${terminal ? "complete" : "running"}">
        <div class="verification-live-progress-head"><strong>${escapeHtml(message)}</strong><span>${percent}%</span></div>
        <div class="verification-live-progress-track" role="progressbar" aria-label="验证执行进度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}"><div class="verification-live-progress-fill" style="width:${percent}%"></div></div>
        <small>${escapeHtml(meta)}${!terminal ? " · 页面约每1.2秒自动刷新" : ""}</small>
      </div>`;
  }

  function renderRuns(task) {
    const runs = task.runs || [];
    const latest = runs[0];
    return `
      <section class="verification-section">
        <div class="panel-title"><h3>5. 执行与结论</h3>${latest ? `<button class="btn secondary" id="refreshVerificationRun">刷新</button>` : ""}</div>
        ${latest ? `
          <div class="verification-run-summary"><span>执行 #${latest.id}</span>${verificationBadge(latest.status)}<span>${escapeHtml(jsonPretty(latest.summary))}</span></div>
          ${runProgress(task, latest)}
          ${renderSetupResult(latest.setup_result)}
          ${window.RequirementVerificationV2?.renderRunWorkspace(task, latest) || ""}
          ${renderTable([
            { key: "item_id", label: "验证项ID" },
            { key: "result", label: "结果", render: (row) => verificationBadge(row.result) },
            { key: "message", label: "说明" },
            { key: "actual", label: "实际与计算", render: (row) => `<pre class="mini-log">${escapeHtml(short(jsonPretty(row.actual), 1600))}</pre>` },
            { key: "actions", label: "人工处理", render: runItemActions },
          ], latest.items || [], false)}
        ` : '<div class="empty">尚未执行验证计划</div>'}
      </section>`;
  }

  function renderTaskDetail(task, catalog, envs) {
    return `
      <div class="panel-title verification-task-head">
        <div><h3>${escapeHtml(task.name)}</h3><p>涉及 ${(task.target_pages || []).length} 个页面</p></div>
        <div class="actions">${verificationBadge(task.status)}${isAdmin() ? '<button class="btn secondary" id="editVerificationTask">编辑功能分类</button><button class="btn secondary" id="verificationSettings">项目规则</button>' : ""}</div>
      </div>
      ${renderTargetPages(task)}
      <details class="functional-requirement" open><summary>初始需求说明</summary><pre>${escapeHtml(task.requirement_text || "暂无")}</pre></details>
      ${renderDataSetup(task, catalog, envs)}
      ${renderMaterials(task)}
      ${renderAnalysis(task)}
      ${renderFormulas(task)}
      ${renderMatrix(task)}
      ${window.RequirementVerificationV2?.renderSections(task) || ""}
      ${renderRuns(task)}
    `;
  }

  function selectedIds(selector) {
    return [...document.querySelectorAll(`${selector}:checked`)].map((input) => Number(input.dataset.verificationCheck));
  }

  function openTaskForm(projects, task = null) {
    const pages = taskTargetPages(task);
    if (!pages.length) pages.push({ name: "", role: "", url: "" });
    modalEl.innerHTML = `
      <form id="verificationTaskForm">
        <div class="modal-head"><h3>${task ? "编辑功能分类" : "新建功能分类"}</h3><button class="btn secondary" type="button" id="closeModal">关闭</button></div>
        <div class="modal-body"><div class="form-grid">
          <div class="field"><label>项目</label><select name="project_id" required ${task ? "disabled" : ""}>${optionHtml(projects, task?.project_id || rvState.projectId, "选择项目")}</select></div>
          <div class="field"><label>功能分类名称</label><input name="name" value="${escapeHtml(task?.name || "")}" placeholder="例如：订单支付新增XX功能" required /></div>
          <div class="field verification-target-page-editor">
            <div class="verification-target-page-head"><label>涉及页面</label><button class="btn secondary" type="button" id="addVerificationTargetPage">添加页面</button></div>
            <div class="verification-target-page-columns"><span>页面名称</span><span>适用角色</span><span>页面URL</span><span></span></div>
            <div id="verificationTargetPageRows">${pages.map(renderTargetPageEditorRow).join("")}</div>
            <small>页面或URL暂时不明确时可以留空，后续再编辑补充。</small>
          </div>
          <div class="field"><label>需求说明</label><textarea name="requirement_text" rows="10" required>${escapeHtml(task?.requirement_text || "")}</textarea></div>
          <div class="field"><label>业务背景与限制</label><textarea name="context" rows="5">${escapeHtml(task?.context || "")}</textarea></div>
        </div></div>
        <div class="modal-foot"><span>${task ? "所属项目创建后不可移动" : "默认创建一个页面输入行"}</span><button class="btn" type="submit">保存</button></div>
      </form>`;
    modalEl.showModal();
    document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
    const pageRows = document.querySelector("#verificationTargetPageRows");
    document.querySelector("#addVerificationTargetPage").addEventListener("click", () => {
      pageRows.insertAdjacentHTML("beforeend", renderTargetPageEditorRow());
      pageRows.lastElementChild?.querySelector('[data-page-field="name"]')?.focus();
    });
    pageRows.addEventListener("click", (event) => {
      const removeButton = event.target.closest("[data-remove-target-page]");
      if (!removeButton) return;
      const row = removeButton.closest(".verification-target-page-row");
      if (pageRows.children.length > 1) row.remove();
      else row.querySelectorAll("input").forEach((input) => { input.value = ""; });
    });
    document.querySelector("#verificationTaskForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const targetPages = [...pageRows.querySelectorAll(".verification-target-page-row")].map((row) => ({
        name: row.querySelector('[data-page-field="name"]').value.trim(),
        role: row.querySelector('[data-page-field="role"]').value.trim(),
        url: row.querySelector('[data-page-field="url"]').value.trim(),
      })).filter((page) => page.name || page.url);
      const data = {
        project_id: Number(form.querySelector('[name="project_id"]').value),
        name: form.querySelector('[name="name"]').value.trim(),
        target_pages: targetPages,
        target_url: targetPages.find((page) => page.url)?.url || "",
        requirement_text: form.querySelector('[name="requirement_text"]').value,
        context: form.querySelector('[name="context"]').value,
      };
      try {
        const result = await api(task ? `/api/requirement-verifications/${task.id}` : "/api/requirement-verifications", { method: task ? "PUT" : "POST", body: data });
        rvState.projectId = String(result.project_id);
        rvState.taskId = String(result.id);
        localStorage.setItem("verificationProjectId", rvState.projectId);
        localStorage.setItem("verificationTaskId", rvState.taskId);
        modalEl.close();
        await window.renderRequirementVerification();
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  function openMaterialForm(task) {
    openForm("补充需求材料", [
      { name: "material_type", label: "材料类型", type: "select", options: [
        { value: "chat", label: "群聊记录" }, { value: "requirement", label: "需求补充" }, { value: "note", label: "测试理解" },
      ], required: true },
      { name: "name", label: "材料名称" },
      { name: "content_text", label: "材料内容", type: "textarea", rows: 12, required: true },
    ], { material_type: "chat" }, async (data) => {
      await api(`/api/requirement-verifications/${task.id}/materials`, { method: "POST", body: data });
      await window.renderRequirementVerification();
    });
  }

  function openUploadForm(task) {
    modalEl.innerHTML = `
      <form id="verificationUploadForm">
        <div class="modal-head"><h3>上传原型截图</h3><button class="btn secondary" type="button" id="closeModal">关闭</button></div>
        <div class="modal-body"><div class="field"><label>PNG/JPG/WebP，最大20MB</label><input type="file" name="file" accept="image/png,image/jpeg,image/webp" required /></div></div>
        <div class="modal-foot"><span>上传后在本地执行OCR，截图不发送给DeepSeek</span><button class="btn" type="submit">上传</button></div>
      </form>`;
    modalEl.showModal();
    document.querySelector("#closeModal").onclick = () => modalEl.close();
    document.querySelector("#verificationUploadForm").onsubmit = async (event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const response = await fetch(`/api/requirement-verifications/${task.id}/materials/upload`, { method: "POST", headers: { Authorization: `Bearer ${state.token}` }, body: form });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "上传失败");
      }
      modalEl.close();
      await window.renderRequirementVerification();
    };
  }

  function openAnswerForm(item, preset = "") {
    openForm("用普通话回答即可", [
      { name: "question", label: "关键问题" },
      { name: "answer", label: "你的回答（先作为草稿）", type: "textarea", rows: 8, required: true },
    ], { question: item.question, answer: preset || item.answer || "" }, async (data) => {
      const result = await api(`/api/requirement-verifications/clarifications/${item.id}`, { method: "PUT", body: { answer: data.answer } });
      modalEl.close();
      openClarificationReview(result);
      return false;
    }, "让AI复述我的意思");
    document.querySelector('[name="question"]')?.setAttribute("disabled", "disabled");
  }

  function openSupplementForm(item) {
    openForm("补充一句再理解", [
      { name: "original_answer", label: "原回答" },
      { name: "supplement", label: "补充说明", type: "textarea", rows: 6, required: true },
    ], { original_answer: item.answer || "" }, async (data) => {
      const result = await api(`/api/requirement-verifications/clarifications/${item.id}`, { method: "PUT", body: { supplement: data.supplement } });
      modalEl.close();
      openClarificationReview(result);
      return false;
    }, "重新复述");
    document.querySelector('[name="original_answer"]')?.setAttribute("disabled", "disabled");
  }

  function clarificationReviewList(label, values) {
    const rows = Array.isArray(values) ? values.filter(Boolean) : [];
    return rows.length ? `<div class="verification-review-group"><strong>${escapeHtml(label)}</strong><ul>${rows.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul></div>` : "";
  }

  function openClarificationReview(item) {
    const interpretation = item.review?.interpretation || {};
    const canConfirm = Boolean(interpretation.can_confirm);
    const confidence = Math.round(Number(interpretation.confidence || 0) * 100);
    modalEl.innerHTML = `
      <div class="modal-head"><h3>确认AI是否理解正确</h3><button class="btn secondary" type="button" id="closeModal">关闭</button></div>
      <div class="modal-body verification-review-modal">
        <div class="verification-review-question"><span>原问题</span><strong>${escapeHtml(item.question)}</strong></div>
        <div class="verification-review-answer"><span>你的原回答</span><p>${escapeHtml(item.answer || "-")}</p></div>
        ${interpretation.model_warning ? `<div class="verification-warning">${escapeHtml(interpretation.model_warning)}</div>` : `
          <div class="verification-review-summary"><span>AI理解的业务规则</span><strong>${escapeHtml(interpretation.summary || "尚未生成可靠复述")}</strong></div>
          ${clarificationReviewList("具体规则", interpretation.understood_rules)}
          ${clarificationReviewList("适用条件", interpretation.conditions)}
          ${clarificationReviewList("例外情况", interpretation.exceptions)}
          ${clarificationReviewList("影响的验证项", interpretation.affected_item_titles)}
          ${clarificationReviewList("仍有歧义", interpretation.ambiguities)}
          ${clarificationReviewList("与历史规则冲突", interpretation.conflicts)}
          <div class="verification-review-confidence">理解置信度：${confidence}%${canConfirm ? "" : "（建议补充一句）"}</div>`}
      </div>
      <div class="modal-foot verification-review-actions">
        <button class="btn secondary" type="button" id="deferClarificationReview">我也不确定</button>
        <button class="btn secondary" type="button" id="supplementClarificationReview">补充一句再理解</button>
        ${canConfirm ? '<button class="btn" type="button" id="confirmClarificationReview">理解正确</button>' : '<button class="btn" type="button" id="retryClarificationReview">重新生成复述</button>'}
      </div>`;
    modalEl.showModal();
    document.querySelector("#closeModal").onclick = () => modalEl.close();
    document.querySelector("#supplementClarificationReview").onclick = () => {
      modalEl.close();
      openSupplementForm(item);
    };
    document.querySelector("#deferClarificationReview").onclick = async () => {
      await api(`/api/requirement-verifications/clarifications/${item.id}/defer`, { method: "POST" });
      modalEl.close();
      await window.renderRequirementVerification();
    };
    document.querySelector("#confirmClarificationReview")?.addEventListener("click", async () => {
      await api(`/api/requirement-verifications/clarifications/${item.id}/confirm`, { method: "POST" });
      modalEl.close();
      showToast("业务理解已确认，完成这一批后再统一更新矩阵");
      await window.renderRequirementVerification();
    });
    document.querySelector("#retryClarificationReview")?.addEventListener("click", async () => {
      const result = await api(`/api/requirement-verifications/clarifications/${item.id}`, { method: "PUT", body: { answer: item.answer } });
      modalEl.close();
      openClarificationReview(result);
    });
  }

  function openItemForm(item) {
    openForm("编辑验证项", [
      { name: "title", label: "验证项", required: true },
      { name: "priority", label: "优先级", type: "select", options: ["P0", "P1", "P2", "P3"].map((value) => ({ value, label: value })) },
      { name: "role_name", label: "业务角色" },
      { name: "precondition", label: "前置条件", type: "textarea", rows: 3 },
      { name: "action_goal", label: "业务操作目标", type: "textarea", rows: 4 },
      { name: "expected", label: "预期结果", type: "textarea", rows: 4 },
      { name: "automation_level", label: "执行方式", type: "select", options: [
        { value: "auto", label: "自动" }, { value: "supervised", label: "监督" }, { value: "manual", label: "人工" },
      ] },
      { name: "risk_level", label: "风险", type: "select", options: [
        { value: "low", label: "低" }, { value: "medium", label: "中" }, { value: "high", label: "高" },
      ] },
      { name: "source_refs_json", label: "需求依据 JSON", type: "textarea", rows: 3 },
      { name: "config_json", label: "执行配置 JSON", type: "textarea", rows: 14 },
    ], { ...item, source_refs_json: jsonPretty(item.source_refs), config_json: jsonPretty(item.config) }, async (data) => {
      const config = parseJson(data.config_json, null);
      const sourceRefs = parseJson(data.source_refs_json, null);
      if (!config || !Array.isArray(sourceRefs)) throw new Error("需求依据或执行配置JSON格式错误");
      delete data.config_json;
      delete data.source_refs_json;
      data.config = config;
      data.source_refs = sourceRefs;
      await api(`/api/requirement-verifications/items/${item.id}`, { method: "PUT", body: data });
      await window.renderRequirementVerification();
    });
  }

  function openFormulaForm(task, formula = null) {
    let variableRows = formulaVariables(formula);
    if (!variableRows.length) variableRows = [{ key: "v1", label: "" }];
    let conditionRows = Object.entries(formula?.conditions || {}).map(([key, value]) => ({ key, value: String(value ?? "") }));
    const expression = formulaExpressionToReadable(formula?.expression || "", formula?.variables || {});
    const selectedCurrency = String(formula?.currency || "CNY").toUpperCase();
    const currencyCodes = Object.keys(formulaCurrencyLabels);
    if (selectedCurrency && !currencyCodes.includes(selectedCurrency)) currencyCodes.push(selectedCurrency);
    const selectedScale = Number(formula?.scale ?? 2);
    const scales = [0, 1, 2, 3, 4, 5, 6];
    if (!scales.includes(selectedScale)) scales.push(selectedScale);

    modalEl.innerHTML = `
      <div class="modal-head"><h3>${formula ? "编辑金额公式" : "新增金额公式"}</h3><button class="btn secondary" id="closeModal" type="button">关闭</button></div>
      <form class="modal-body verification-formula-form" id="verificationFormulaForm">
        <div class="field"><label>公式名称</label><input name="name" value="${escapeHtml(formula?.name || "")}" placeholder="例如：订单应付金额" required /></div>

        <section class="verification-formula-block">
          <div class="verification-formula-block-head"><div><strong>计算变量</strong><span>填写你看得懂的中文名称，系统会在后台自动处理变量标识。</span></div><button class="btn secondary" id="addFormulaVariable" type="button">添加变量</button></div>
          <div class="verification-formula-columns"><span>变量名称</span><span>操作</span></div>
          <div id="formulaVariableRows"></div>
        </section>

        <section class="verification-formula-block">
          <div class="verification-formula-block-head"><div><strong>计算公式</strong><span>点击变量和符号即可拼接，也可以直接输入中文公式。</span></div></div>
          <div class="verification-formula-toolbar">
            <div id="formulaVariableTokens" class="verification-formula-token-group"></div>
            <div class="verification-formula-token-group">
              ${["+", "-", "×", "÷", "(", ")", "最小值(", "最大值(", "绝对值(", "四舍五入("].map((token) => `<button class="btn secondary formula-token" type="button" data-insert-formula="${escapeHtml(token)}">${escapeHtml(token)}</button>`).join("")}
            </div>
          </div>
          <textarea id="formulaReadableExpression" rows="4" placeholder="例如：[商品单价] × [数量] + [运费] - [优惠金额]" required>${escapeHtml(expression)}</textarea>
          <small>支持加、减、乘、除、括号、最小值、最大值、绝对值和四舍五入。保存时系统会自动转换为安全计算规则。</small>
        </section>

        <section class="verification-formula-block">
          <div class="verification-formula-block-head"><div><strong>适用条件</strong><span>没有限制条件可以不填写。</span></div><button class="btn secondary" id="addFormulaCondition" type="button">添加条件</button></div>
          <div id="formulaConditionRows"></div>
        </section>

        <div class="verification-formula-settings">
          <div class="field"><label>币种</label><select name="currency" required>${currencyCodes.map((code) => `<option value="${escapeHtml(code)}" ${code === selectedCurrency ? "selected" : ""}>${escapeHtml(formulaCurrencyText(code))}</option>`).join("")}</select></div>
          <div class="field"><label>保留小数位</label><select name="scale">${scales.sort((left, right) => left - right).map((scale) => `<option value="${scale}" ${scale === selectedScale ? "selected" : ""}>${scale === 0 ? "不保留小数（整数）" : `保留 ${scale} 位小数${scale === 2 ? "（常用）" : ""}`}</option>`).join("")}</select></div>
          <div class="field"><label>舍入方式</label><select name="rounding_mode">${Object.entries(formulaRoundingLabels).map(([value, label]) => `<option value="${value}" ${value === (formula?.rounding_mode || "HALF_UP") ? "selected" : ""}>${escapeHtml(label)}</option>`).join("")}</select></div>
          <div class="field"><label>舍入阶段</label><select name="rounding_stage">${Object.entries(formulaStageLabels).map(([value, label]) => `<option value="${value}" ${value === (formula?.rounding_stage || "final") ? "selected" : ""}>${escapeHtml(label)}</option>`).join("")}</select></div>
        </div>

        <div class="field"><label>需求依据（每行一条）</label><textarea name="source_refs_text" rows="3" placeholder="例如：原型第3页订单金额说明">${escapeHtml((formula?.source_refs || []).join("\n"))}</textarea></div>
        <div class="verification-formula-preview"><span>当前规则预览</span><strong id="formulaRulePreview"></strong></div>
        <div class="form-actions"><button class="btn secondary" id="cancelFormulaForm" type="button">取消</button><button class="btn" type="submit">保存公式</button></div>
      </form>`;
    modalEl.showModal();

    const formEl = document.querySelector("#verificationFormulaForm");
    const expressionEl = document.querySelector("#formulaReadableExpression");
    const nextVariableKey = () => {
      const used = new Set(variableRows.map((item) => item.key));
      let index = 1;
      while (used.has(`v${index}`)) index += 1;
      return `v${index}`;
    };
    const conditionOptions = (selected = "") => {
      const known = variableRows.some((item) => item.key === selected);
      return [
        '<option value="">请选择条件字段</option>',
        ...variableRows.filter((item) => item.label.trim()).map((item) => `<option value="${escapeHtml(item.key)}" ${item.key === selected ? "selected" : ""}>${escapeHtml(item.label)}</option>`),
        ...(!known && selected ? [`<option value="${escapeHtml(selected)}" selected>${escapeHtml(selected)}（历史条件字段）</option>`] : []),
      ].join("");
    };
    const insertFormulaText = (text) => {
      const start = expressionEl.selectionStart ?? expressionEl.value.length;
      const end = expressionEl.selectionEnd ?? start;
      expressionEl.value = `${expressionEl.value.slice(0, start)}${text}${expressionEl.value.slice(end)}`;
      expressionEl.focus();
      expressionEl.setSelectionRange(start + text.length, start + text.length);
      expressionEl.dispatchEvent(new Event("input"));
    };
    const syncFormulaTokens = () => {
      document.querySelector("#formulaVariableTokens").innerHTML = variableRows
        .filter((item) => item.label.trim())
        .map((item) => `<button class="btn secondary formula-token variable" type="button" data-insert-formula="${escapeHtml(`[${item.label.trim()}]`)}">${escapeHtml(item.label.trim())}</button>`)
        .join("") || '<span class="muted">填写变量名称后，可点击变量插入公式</span>';
    };
    const syncPreview = () => {
      const mode = formEl.elements.rounding_mode.value;
      const stage = formEl.elements.rounding_stage.value;
      const scale = Number(formEl.elements.scale.value);
      const scaleText = scale === 0 ? "不保留小数" : `保留${scale}位小数`;
      document.querySelector("#formulaRulePreview").textContent = `${expressionEl.value.trim() || "请填写计算公式"}；${formulaCurrencyText(formEl.elements.currency.value)}；${formulaRoundingLabels[mode]}；${scaleText}；${formulaStageLabels[stage]}`;
    };
    const renderConditionRows = () => {
      const container = document.querySelector("#formulaConditionRows");
      container.innerHTML = conditionRows.length ? conditionRows.map((item, index) => `
        <div class="verification-formula-condition-row">
          <span>当</span>
          <select data-formula-condition-key="${index}">${conditionOptions(item.key)}</select>
          <span>等于</span>
          <input data-formula-condition-value="${index}" value="${escapeHtml(item.value)}" placeholder="条件值" />
          <button class="btn danger" type="button" data-remove-formula-condition="${index}">删除</button>
        </div>`).join("") : '<div class="empty">所有情况都适用</div>';
      container.querySelectorAll("[data-formula-condition-key]").forEach((select) => select.addEventListener("change", () => {
        conditionRows[Number(select.dataset.formulaConditionKey)].key = select.value;
      }));
      container.querySelectorAll("[data-formula-condition-value]").forEach((input) => input.addEventListener("input", () => {
        conditionRows[Number(input.dataset.formulaConditionValue)].value = input.value;
      }));
      container.querySelectorAll("[data-remove-formula-condition]").forEach((button) => button.addEventListener("click", () => {
        conditionRows.splice(Number(button.dataset.removeFormulaCondition), 1);
        renderConditionRows();
      }));
    };
    const renderVariableRows = () => {
      const container = document.querySelector("#formulaVariableRows");
      container.innerHTML = variableRows.map((item, index) => `
        <div class="verification-formula-variable-row">
          <input data-formula-variable-label="${index}" value="${escapeHtml(item.label)}" placeholder="例如：商品单价、数量、国际运费" />
          <button class="btn danger" type="button" data-remove-formula-variable="${index}" ${variableRows.length === 1 ? "disabled" : ""}>删除</button>
        </div>`).join("");
      container.querySelectorAll("[data-formula-variable-label]").forEach((input) => input.addEventListener("input", () => {
        const index = Number(input.dataset.formulaVariableLabel);
        const previous = variableRows[index].label.trim();
        const next = input.value.trim();
        variableRows[index].label = input.value;
        if (previous && next && previous !== next) expressionEl.value = expressionEl.value.split(`[${previous}]`).join(`[${next}]`);
        syncFormulaTokens();
        renderConditionRows();
        syncPreview();
      }));
      container.querySelectorAll("[data-remove-formula-variable]").forEach((button) => button.addEventListener("click", () => {
        const removed = variableRows.splice(Number(button.dataset.removeFormulaVariable), 1)[0];
        conditionRows = conditionRows.filter((item) => item.key !== removed.key);
        renderVariableRows();
        renderConditionRows();
        syncFormulaTokens();
        syncPreview();
      }));
    };

    renderVariableRows();
    renderConditionRows();
    syncFormulaTokens();
    syncPreview();
    document.querySelector("#closeModal").onclick = () => modalEl.close();
    document.querySelector("#cancelFormulaForm").onclick = () => modalEl.close();
    document.querySelector("#addFormulaVariable").onclick = () => {
      variableRows.push({ key: nextVariableKey(), label: "" });
      renderVariableRows();
      document.querySelector("#formulaVariableRows .verification-formula-variable-row:last-child input")?.focus();
    };
    document.querySelector("#addFormulaCondition").onclick = () => {
      conditionRows.push({ key: "", value: "" });
      renderConditionRows();
    };
    formEl.addEventListener("click", (event) => {
      const button = event.target.closest("[data-insert-formula]");
      if (button) insertFormulaText(button.dataset.insertFormula);
    });
    expressionEl.addEventListener("input", syncPreview);
    ["currency", "scale", "rounding_mode", "rounding_stage"].forEach((name) => formEl.elements[name].addEventListener("change", syncPreview));
    formEl.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = formEl.querySelector('[type="submit"]');
      try {
        const variables = variableRows
          .map((item) => ({ key: item.key, label: item.label.trim() }))
          .filter((item) => item.label);
        if (!variables.length) throw new Error("请至少填写一个计算变量");
        if (variables.some((item) => /[\[\]]/.test(item.label))) throw new Error("变量名称不能包含方括号");
        if (new Set(variables.map((item) => item.label)).size !== variables.length) throw new Error("变量名称不能重复");
        const internalExpression = formulaReadableToExpression(expressionEl.value, variables);
        if (!internalExpression) throw new Error("请填写计算公式");
        const conditions = {};
        conditionRows.filter((item) => item.key).forEach((item) => { conditions[item.key] = item.value; });
        const data = new FormData(formEl);
        const body = {
          task_id: task.id,
          name: String(data.get("name") || "").trim(),
          expression: internalExpression,
          variables: Object.fromEntries(variables.map((item) => [item.key, item.label])),
          conditions,
          currency: String(data.get("currency") || "CNY"),
          scale: Number(data.get("scale")),
          rounding_mode: String(data.get("rounding_mode") || "HALF_UP"),
          rounding_stage: String(data.get("rounding_stage") || "final"),
          source_refs: String(data.get("source_refs_text") || "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
        };
        if (!body.name) throw new Error("请填写公式名称");
        submitButton.disabled = true;
        await api(formula ? `/api/requirement-verifications/formulas/${formula.id}` : `/api/requirement-verifications/projects/${task.project_id}/formulas`, { method: formula ? "PUT" : "POST", body });
        modalEl.close();
        await window.renderRequirementVerification();
      } catch (error) {
        showToast(error.message);
        submitButton.disabled = false;
      }
    });
  }

  async function openSettings(task) {
    const [envs, sources, memories] = await Promise.all([
      api(`/api/envs?project_id=${task.project_id}`),
      api(`/api/requirement-verifications/projects/${task.project_id}/data-sources`),
      api(`/api/requirement-verifications/projects/${task.project_id}/memories`),
    ]);
    modalEl.innerHTML = `
      <div class="modal-head"><h3>项目规则与只读数据源</h3><button class="btn secondary" id="closeModal">关闭</button></div>
      <div class="modal-body">
        <div class="panel-title"><h3>只读接口白名单</h3><button class="btn" id="addDataSource">新增</button></div>
        ${sources.length ? sources.map((item) => `<div class="verification-setting"><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.allowed_paths.join("；"))}</span></div>`).join("") : '<div class="empty">尚未配置，只能执行不依赖接口的验证项</div>'}
        <div class="panel-title"><h3>已确认业务记忆</h3><button class="btn" id="addMemory">新增</button></div>
        ${memories.length ? memories.map((item) => `<div class="verification-setting"><strong>${escapeHtml(item.name)}</strong>${verificationBadge(item.status)}${item.status !== "confirmed" ? `<button class="btn secondary" data-confirm-memory="${item.id}">确认规则</button>` : ""}<pre class="mini-log">${escapeHtml(short(jsonPretty(item.content), 900))}</pre></div>`).join("") : '<div class="empty">尚未沉淀项目规则</div>'}
      </div>`;
    modalEl.showModal();
    document.querySelector("#closeModal").onclick = () => modalEl.close();
    document.querySelectorAll("[data-confirm-memory]").forEach((button) => button.onclick = async () => {
      await api(`/api/requirement-verifications/memories/${button.dataset.confirmMemory}/confirm`, { method: "POST" });
      modalEl.close();
      await window.renderRequirementVerification();
    });
    document.querySelector("#addDataSource").onclick = () => {
      modalEl.close();
      openForm("新增只读接口白名单", [
        { name: "env_id", label: "项目环境", type: "select", options: envs.map((item) => ({ value: item.id, label: item.env_name })), required: true },
        { name: "name", label: "数据源名称", required: true },
        { name: "allowed_paths_text", label: "允许的GET/HEAD路径前缀（每行一条）", type: "textarea", rows: 8, required: true },
      ], {}, async (data) => {
        await api(`/api/requirement-verifications/projects/${task.project_id}/data-sources`, { method: "POST", body: { env_id: Number(data.env_id), name: data.name, allowed_paths: data.allowed_paths_text.split(/\r?\n/).map((value) => value.trim()).filter(Boolean) } });
        await window.renderRequirementVerification();
      });
    };
    document.querySelector("#addMemory").onclick = () => {
      modalEl.close();
      openForm("新增项目业务记忆", [
        { name: "memory_type", label: "类型", type: "select", options: [
          { value: "business_rule", label: "业务规则" }, { value: "state_mapping", label: "状态映射" }, { value: "field_definition", label: "字段定义" }, { value: "page_knowledge", label: "页面知识" },
        ] },
        { name: "name", label: "名称", required: true },
        { name: "content_json", label: "规则 JSON", type: "textarea", rows: 10, required: true },
      ], { memory_type: "business_rule", content_json: "{}" }, async (data) => {
        const content = parseJson(data.content_json, null);
        if (!content) throw new Error("规则JSON格式错误");
        await api(`/api/requirement-verifications/projects/${task.project_id}/memories`, { method: "POST", body: { memory_type: data.memory_type, name: data.name, content, source_task_id: task.id } });
        await window.renderRequirementVerification();
      });
    };
  }

  function bindActions(task, projects, catalog, envs) {
    document.querySelector("#editVerificationTask")?.addEventListener("click", () => openTaskForm(projects, task));
    document.querySelector("#editVerificationDataSetup")?.addEventListener("click", () => openDataSetupForm(task, catalog, envs));
    document.querySelector("#addVerificationMaterial")?.addEventListener("click", () => openMaterialForm(task));
    document.querySelector("#uploadVerificationMaterial")?.addEventListener("click", () => openUploadForm(task));
    document.querySelector("#verificationSettings")?.addEventListener("click", () => openSettings(task));
    document.querySelectorAll("[data-material-file]").forEach((button) => button.addEventListener("click", () => openProtectedFile(`/api/requirement-verifications/materials/${button.dataset.materialFile}/file`)));
    document.querySelector("#analyzeVerification")?.addEventListener("click", async () => {
      showToast("正在分析需求并生成验证矩阵");
      await api(`/api/requirement-verifications/${task.id}/analyze`, { method: "POST", body: { mode: "standard" } });
      await window.renderRequirementVerification();
    });
    document.querySelector("#continueVerificationAnalysis")?.addEventListener("click", async () => {
      showToast("正在按当前明确范围更新矩阵，不会新增问题");
      await api(`/api/requirement-verifications/${task.id}/analyze`, { method: "POST", body: { mode: "continue_without_questions" } });
      await window.renderRequirementVerification();
    });
    const clarificationById = (id) => (task.clarifications || []).find((item) => item.id === Number(id));
    document.querySelectorAll("[data-answer-question]").forEach((button) => button.addEventListener("click", () => openAnswerForm(clarificationById(button.dataset.answerQuestion))));
    document.querySelectorAll("[data-clarification-option]").forEach((button) => button.addEventListener("click", () => {
      const item = clarificationById(button.dataset.clarificationOption);
      const option = item?.review?.suggested_answers?.[Number(button.dataset.optionIndex)] || "";
      openAnswerForm(item, option);
    }));
    document.querySelectorAll("[data-view-clarification]").forEach((button) => button.addEventListener("click", () => openClarificationReview(clarificationById(button.dataset.viewClarification))));
    document.querySelectorAll("[data-supplement-clarification]").forEach((button) => button.addEventListener("click", () => openSupplementForm(clarificationById(button.dataset.supplementClarification))));
    document.querySelectorAll("[data-defer-clarification]").forEach((button) => button.addEventListener("click", async () => {
      await api(`/api/requirement-verifications/clarifications/${button.dataset.deferClarification}/defer`, { method: "POST" });
      await window.renderRequirementVerification();
    }));
    document.querySelector("#newVerificationFormula")?.addEventListener("click", () => openFormulaForm(task));
    document.querySelectorAll("[data-edit-formula]").forEach((button) => button.addEventListener("click", () => openFormulaForm(task, task.formulas.find((item) => item.id === Number(button.dataset.editFormula)))));
    document.querySelectorAll("[data-confirm-formula]").forEach((button) => button.addEventListener("click", async () => {
      await api(`/api/requirement-verifications/formulas/${button.dataset.confirmFormula}/confirm`, { method: "POST" });
      await window.renderRequirementVerification();
    }));
    document.querySelectorAll("[data-edit-verification-item]").forEach((button) => button.addEventListener("click", () => openItemForm(task.items.find((item) => item.id === Number(button.dataset.editVerificationItem)))));
    document.querySelector("#confirmSelectedItems")?.addEventListener("click", async () => {
      const ids = selectedIds("[data-verification-check]");
      if (!ids.length) throw new Error("请先选择验证项");
      const result = await api(`/api/requirement-verifications/${task.id}/items/batch-confirm`, { method: "POST", body: { item_ids: ids, confirmed: true } });
      showToast(`已确认 ${result.confirmed} 条${result.blocked?.length ? `，其中${result.blocked.length}条需完成澄清后才能执行` : ""}`);
      await window.renderRequirementVerification();
    });
    document.querySelector("#runSelectedItems")?.addEventListener("click", async () => {
      const selected = selectedIds("[data-verification-check]");
      const confirmed = (task.items || []).filter((item) => item.confirmed && item.status !== "blocked" && (!selected.length || selected.includes(item.id))).map((item) => item.id);
      if (!confirmed.length) throw new Error("选中的验证项尚未确认，或仍处于阻塞状态");
      openVerificationRunForm(task, confirmed);
    });
    document.querySelector("#refreshVerificationRun")?.addEventListener("click", () => window.renderRequirementVerification());
    document.querySelectorAll("[data-run-confirm]").forEach((button) => button.addEventListener("click", async () => {
      await api(`/api/requirement-verifications/run-items/${button.dataset.runConfirm}/confirm`, { method: "POST", body: { decision: button.dataset.decision } });
      showToast("已发送人工确认");
      window.setTimeout(() => window.renderRequirementVerification(), 500);
    }));
    document.querySelectorAll("[data-submit-observation]").forEach((button) => button.addEventListener("click", async () => {
      const input = document.querySelector(`[data-observed-value="${button.dataset.submitObservation}"]`);
      if (!String(input?.value || "").trim()) { showToast("请填写你在页面看到的实际值"); return; }
      await api(`/api/requirement-verifications/run-items/${button.dataset.submitObservation}/confirm`, { method: "POST", body: { decision: "provide_value", observed_value: input.value } });
      showToast("实际值已提交，继续验证");
      window.setTimeout(() => window.renderRequirementVerification(), 500);
    }));
    window.RequirementVerificationV2?.bind(task);
  }

  window.renderRequirementVerification = async function () {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    const projects = await getProjects();
    if (!rvState.projectId && projects[0]) rvState.projectId = String(projects[0].id);
    const taskParams = new URLSearchParams();
    if (rvState.projectId) taskParams.set("project_id", rvState.projectId);
    if (rvState.keyword) taskParams.set("keyword", rvState.keyword);
    if (rvState.status) taskParams.set("status", rvState.status);
    if (rvState.archived === "active") taskParams.set("archived", "false");
    if (rvState.archived === "archived") taskParams.set("archived", "true");
    const tasks = sortVerificationTasks(await api(`/api/requirement-verifications?${taskParams.toString()}`));
    if (rvState.taskId && !tasks.some((item) => String(item.id) === String(rvState.taskId))) rvState.taskId = "";
    if (!rvState.taskId && tasks[0]) rvState.taskId = String(tasks[0].id);
    const [task, catalog, envs] = rvState.taskId
      ? await Promise.all([
          api(`/api/requirement-verifications/${rvState.taskId}`),
          api(`/api/requirement-verifications/data-script-catalog?project_id=${encodeURIComponent(rvState.projectId)}`),
          api(`/api/envs?project_id=${encodeURIComponent(rvState.projectId)}`),
        ])
      : [null, [], []];
    contentEl().innerHTML = `
      <div class="toolbar">
        <div class="filters"><div class="field compact"><label>项目</label><select id="verificationProjectFilter">${optionHtml(projects, rvState.projectId, "选择项目")}</select></div></div>
        ${isAdmin() ? '<div class="actions"><button class="btn" id="newVerificationTask">新建功能分类</button></div>' : ""}
      </div>
      <div class="verification-list-filters">
        <div class="field compact"><label>名称搜索</label><input id="verificationKeyword" value="${escapeHtml(rvState.keyword)}" placeholder="订单支付、配送单……" /></div>
        <button class="btn secondary" id="searchVerificationTask">搜索</button>
        <div class="field compact"><label>执行状态</label><select id="verificationStatusFilter">
          <option value="" ${rvState.status ? "" : "selected"}>全部状态</option>
          ${[["draft", "草稿"], ["materials_ready", "材料已就绪"], ["plan_generated", "计划已生成"], ["ready", "待执行"], ["queued", "排队中"], ["running", "执行中"], ["passed", "通过"], ["failed", "失败"], ["blocked", "数据准备阻塞"], ["needs_review", "待人工处理"]].map(([value, label]) => `<option value="${value}" ${rvState.status === value ? "selected" : ""}>${label}</option>`).join("")}
        </select></div>
        <div class="field compact"><label>归档</label><select id="verificationArchivedFilter">
          <option value="active" ${rvState.archived === "active" ? "selected" : ""}>进行中</option>
          <option value="archived" ${rvState.archived === "archived" ? "selected" : ""}>已归档</option>
          <option value="all" ${rvState.archived === "all" ? "selected" : ""}>全部</option>
        </select></div>
        <div class="field compact"><label>排序</label><select id="verificationSort">
          <option value="updated_desc" ${rvState.sort === "updated_desc" ? "selected" : ""}>最近更新</option>
          <option value="updated_asc" ${rvState.sort === "updated_asc" ? "selected" : ""}>最早更新</option>
          <option value="name_asc" ${rvState.sort === "name_asc" ? "selected" : ""}>名称排序</option>
        </select></div>
      </div>
      <div class="verification-layout">
        <section class="panel verification-task-list">
          <div class="panel-title"><h3>功能分类（本期需求包）</h3></div>
          ${tasks.length ? tasks.map(renderFeatureCard).join("") : '<div class="empty">当前筛选条件下没有功能分类</div>'}
        </section>
        <section class="panel verification-detail">${task ? renderTaskDetail(task, catalog, envs) : '<div class="empty">新建一个功能分类，存放本期需求材料和验证结果</div>'}</section>
      </div>`;
    document.querySelector("#verificationProjectFilter").addEventListener("change", async (event) => {
      rvState.projectId = event.target.value;
      rvState.taskId = "";
      localStorage.setItem("verificationProjectId", rvState.projectId);
      localStorage.removeItem("verificationTaskId");
      await window.renderRequirementVerification();
    });
    document.querySelector("#newVerificationTask")?.addEventListener("click", () => openTaskForm(projects));
    const applyFilters = async () => {
      rvState.keyword = document.querySelector("#verificationKeyword")?.value.trim() || "";
      rvState.status = document.querySelector("#verificationStatusFilter")?.value || "";
      rvState.archived = document.querySelector("#verificationArchivedFilter")?.value || "active";
      rvState.sort = document.querySelector("#verificationSort")?.value || "updated_desc";
      localStorage.setItem("verificationArchivedFilter", rvState.archived);
      localStorage.setItem("verificationSort", rvState.sort);
      await window.renderRequirementVerification();
    };
    document.querySelector("#searchVerificationTask")?.addEventListener("click", applyFilters);
    document.querySelector("#verificationKeyword")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") applyFilters();
    });
    ["#verificationStatusFilter", "#verificationArchivedFilter", "#verificationSort"].forEach((selector) => document.querySelector(selector)?.addEventListener("change", applyFilters));
    document.querySelectorAll("[data-open-verification]").forEach((button) => button.addEventListener("click", async () => {
      rvState.taskId = button.dataset.openVerification;
      localStorage.setItem("verificationTaskId", rvState.taskId);
      await window.renderRequirementVerification();
    }));
    document.querySelectorAll("[data-archive-verification]").forEach((button) => button.addEventListener("click", async () => {
      await api(`/api/requirement-verifications/${button.dataset.archiveVerification}`, { method: "PUT", body: { is_archived: button.dataset.archiveValue === "true" } });
      if (String(rvState.taskId) === String(button.dataset.archiveVerification)) {
        rvState.taskId = "";
        localStorage.removeItem("verificationTaskId");
      }
      showToast(button.dataset.archiveValue === "true" ? "功能分类已归档" : "功能分类已恢复");
      await window.renderRequirementVerification();
    }));
    document.querySelectorAll("[data-delete-verification]").forEach((button) => button.addEventListener("click", () => {
      const deletingId = button.dataset.deleteVerification;
      deleteItem(`/api/requirement-verifications/${deletingId}`, async () => {
        if (String(rvState.taskId) === String(deletingId)) {
          rvState.taskId = "";
          localStorage.removeItem("verificationTaskId");
        }
        await window.renderRequirementVerification();
      });
    }));
    if (task) bindActions(task, projects, catalog, envs);
    const running = task?.runs?.[0] && ["queued", "running", "waiting_confirmation", "waiting_user", "paused", "cancelling"].includes(task.runs[0].status);
    if (running && state.view === "requirementVerification") pollTimer = window.setTimeout(() => window.renderRequirementVerification(), 1200);
  };

  const style = document.createElement("style");
  style.textContent = `
    .verification-layout{display:grid;grid-template-columns:minmax(230px,300px) minmax(0,1fr);gap:16px;align-items:start}
    .verification-task-list{position:sticky;top:12px;max-height:calc(100vh - 120px);overflow:auto}
    .verification-list-filters{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin:0 0 14px}.verification-list-filters .field{min-width:140px}.verification-list-filters .field:first-child{min-width:220px}
    .verification-task-card{display:flex;width:100%;flex-direction:column;gap:7px;padding:10px;border:1px solid var(--border);background:transparent;color:inherit;text-align:left;border-radius:10px;margin-bottom:8px}
    .verification-task-card.active{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 10%,transparent)}
    .verification-task-open{display:flex;flex-direction:column;gap:7px;width:100%;padding:2px;border:0;background:transparent;color:inherit;text-align:left;cursor:pointer}.verification-task-open span{font-size:12px;color:var(--muted)}
    .verification-task-counts{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 10px}.verification-task-counts b{font-weight:500;color:var(--text)}.verification-task-actions{display:flex;justify-content:flex-end;gap:6px;border-top:1px solid var(--border);padding-top:8px}
    .verification-target-pages{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px;margin:0 0 14px}.verification-target-pages>div{display:flex;flex-direction:column;gap:5px;padding:10px;border:1px solid var(--border);border-radius:8px}.verification-target-pages span{font-size:12px;color:var(--muted);overflow-wrap:anywhere}
    .verification-formula-readable{font-weight:600;line-height:1.7;overflow-wrap:anywhere}dialog:has(#verificationFormulaForm){width:min(980px,calc(100vw - 32px))}.verification-formula-form{display:grid;gap:14px}.verification-formula-block{display:grid;gap:10px;padding:14px;border:1px solid var(--border);border-radius:10px}.verification-formula-block-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.verification-formula-block-head>div{display:flex;flex-direction:column;gap:4px}.verification-formula-block-head span,.verification-formula-block small{font-size:12px;color:var(--muted);line-height:1.5}.verification-formula-columns,.verification-formula-variable-row{display:grid;grid-template-columns:minmax(220px,1fr) auto;gap:10px;align-items:center}.verification-formula-columns{padding:0 3px;color:var(--muted);font-size:12px;font-weight:600}.verification-formula-variable-row{padding:9px;border:1px solid var(--border);border-radius:8px;margin-top:8px}.verification-formula-toolbar{display:grid;gap:8px}.verification-formula-token-group{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.verification-formula-token{padding:6px 10px}.verification-formula-token.variable{border-color:var(--accent);font-weight:600}.verification-formula-condition-row{display:grid;grid-template-columns:auto minmax(150px,1fr) auto minmax(150px,1fr) auto;gap:8px;align-items:center;margin-top:8px}.verification-formula-settings{display:grid;grid-template-columns:repeat(2,minmax(180px,1fr));gap:12px}.verification-formula-preview{display:flex;flex-direction:column;gap:7px;padding:13px;border-radius:9px;background:color-mix(in srgb,var(--accent) 10%,transparent);border:1px solid color-mix(in srgb,var(--accent) 35%,var(--border))}.verification-formula-preview span{font-size:12px;color:var(--muted)}.verification-formula-preview strong{line-height:1.7;overflow-wrap:anywhere}
    .verification-setup-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;padding:12px 0}.verification-setup-summary-item{display:flex;flex-direction:column;gap:7px;padding:12px;border:1px solid var(--border);border-radius:9px}.verification-setup-summary-item.disabled{opacity:.55}.verification-setup-summary-item>span{font-size:12px;color:var(--muted)}.verification-setup-summary-item pre{margin:0}
    .verification-setup-advanced,.verification-advanced-section{margin-top:10px;padding:10px 12px;border:1px solid var(--border);border-radius:9px}.verification-setup-advanced summary,.verification-advanced-section summary{cursor:pointer;color:var(--muted);font-weight:700}.verification-advanced-item-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
    dialog:has(#verificationSetupForm){width:min(1040px,calc(100vw - 32px))}.verification-setup-toolbar,.verification-setup-editor-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.verification-setup-toolbar{margin:0 0 12px}.verification-setup-editor-step{display:grid;gap:12px;padding:14px;border:1px solid var(--border);border-radius:10px;margin-bottom:12px}.verification-setup-base-grid{display:grid;grid-template-columns:minmax(180px,1.2fr) minmax(160px,1fr) auto auto;gap:10px;align-items:end}.verification-setup-param-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.verification-setup-param-section{grid-column:1/-1;padding:8px 0 5px;border-bottom:1px solid var(--border);font-weight:700}.verification-run-options{margin-bottom:18px;padding:12px;border:1px solid var(--border);border-radius:9px}.verification-setup-result{margin:10px 0;padding:12px;border:1px solid var(--border);border-radius:9px}.verification-setup-result summary{cursor:pointer;font-weight:700}.verification-setup-result-step{display:grid;gap:7px;padding:10px 0;border-bottom:1px solid var(--border)}.verification-setup-result-step>div{display:flex;align-items:center;justify-content:space-between;gap:10px}.verification-setup-result-step>span{font-size:12px;color:var(--muted)}
    .verification-target-page-editor{gap:10px}.verification-target-page-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.verification-target-page-head label{margin:0}.verification-target-page-columns,.verification-target-page-row{display:grid;grid-template-columns:minmax(120px,.8fr) minmax(100px,.6fr) minmax(230px,1.6fr) auto;gap:8px;align-items:center}.verification-target-page-columns{padding:0 2px;color:var(--muted);font-size:12px;font-weight:600}.verification-target-page-row{padding:10px;border:1px solid var(--border);border-radius:8px;background:color-mix(in srgb,var(--surface) 86%,transparent)}#verificationTargetPageRows{display:grid;gap:8px}.verification-target-page-editor small{color:var(--muted);line-height:1.5}
    .verification-detail{min-width:0}.verification-task-head{align-items:flex-start}.verification-task-head p{margin:5px 0 0;color:var(--muted)}
    .verification-section{padding:16px 0;border-top:1px solid var(--border)}.verification-section:first-of-type{border-top:0}
    .verification-matrix-check{width:18px;height:18px;min-height:0;cursor:pointer;accent-color:var(--accent)}
    .verification-stats{display:grid;grid-template-columns:repeat(7,minmax(70px,1fr));gap:8px;margin:10px 0}.verification-stats>div{padding:9px;border:1px solid var(--border);border-radius:8px;text-align:center}.verification-stats span{display:block;color:var(--muted);font-size:12px}.verification-stats strong{font-size:20px}
    .verification-analysis-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.verification-analysis-grid>div,.verification-question,.verification-material,.verification-setting{padding:12px;border:1px solid var(--border);border-radius:9px;margin-bottom:8px}.verification-analysis-grid span{color:var(--muted);font-size:12px}.verification-analysis-grid p{margin:6px 0 0}
    .verification-question>div,.verification-material>div,.verification-run-summary{display:flex;gap:10px;align-items:center;justify-content:space-between}.verification-question p{margin:8px 0;color:var(--muted)}
    .verification-clarification-note,.verification-confirmation-notice{padding:10px 12px;border-radius:8px;margin:10px 0}.verification-clarification-note{background:color-mix(in srgb,var(--accent) 8%,transparent);color:var(--muted)}.verification-confirmation-notice{background:#e9f8ef;color:#21613b}.verification-answer-options,.verification-question .actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.verification-answer-draft,.verification-review-preview{padding:10px;border-radius:8px;margin-top:10px;white-space:pre-wrap}.verification-answer-draft{background:color-mix(in srgb,var(--border) 32%,transparent)}.verification-review-preview{background:color-mix(in srgb,var(--accent) 9%,transparent)}.verification-confirmed-rules{margin-top:10px;padding:10px 12px;border:1px solid var(--border);border-radius:9px}.verification-confirmed-rules summary{cursor:pointer;font-weight:700}.verification-confirmed-rule,.verification-deferred-rule{padding:10px 0;border-bottom:1px solid var(--border)}.verification-confirmed-rule:last-child,.verification-deferred-rule:last-child{border-bottom:0}.verification-confirmed-rule p{color:var(--muted);white-space:pre-wrap}.verification-deferred-rule{display:flex;justify-content:space-between;gap:12px}.verification-deferred-rule span{color:var(--muted);font-size:12px}.verification-readiness{display:grid;grid-template-columns:repeat(3,minmax(100px,1fr));gap:8px;margin:10px 0}.verification-readiness>div{padding:12px;border:1px solid var(--border);border-radius:9px;text-align:center}.verification-readiness span{display:block;color:var(--muted);font-size:12px}.verification-readiness strong{font-size:23px}.verification-review-modal{display:grid;gap:12px}.verification-review-question,.verification-review-answer,.verification-review-summary,.verification-review-group{display:grid;gap:7px;padding:12px;border:1px solid var(--border);border-radius:9px}.verification-review-question span,.verification-review-answer span,.verification-review-summary span{color:var(--muted);font-size:12px}.verification-review-answer p{margin:0;white-space:pre-wrap}.verification-review-group ul{margin:0;padding-left:22px}.verification-review-confidence{color:var(--muted);font-size:12px}.verification-review-actions{gap:8px;flex-wrap:wrap}
    .verification-quick-setup{display:grid;gap:8px;padding:12px;border:1px solid var(--border);border-radius:9px;margin-bottom:12px}.verification-quick-setup>div{display:flex;justify-content:space-between;gap:12px}.verification-quick-setup small{color:var(--muted)}.verification-preflight-list{display:grid;gap:8px}.verification-preflight-item{padding:12px;border:1px solid var(--border);border-radius:9px}.verification-preflight-item>div{display:flex;justify-content:space-between;gap:10px}.verification-preflight-item ul{margin:8px 0 0;padding-left:20px}.verification-preflight-item li{margin-top:6px}.verification-preflight-item li small{display:block;color:var(--muted)}.verification-preflight-item.blocked{border-color:#d99;background:#fff5f5}.verification-preflight-item.assisted{border-color:#d8b45b;background:#fffaf0}.verification-risk-confirm{margin-top:14px}.verification-observation-takeover,.verification-manual-check{display:grid;gap:8px;min-width:260px}.verification-observation-takeover input{min-width:240px}
    .verification-warning{padding:10px 12px;border-radius:8px;background:#fff7dc;color:#7a5200;margin-bottom:10px}.verification-run-summary{padding:10px 0}.verification-run-summary>span:last-child{font-size:12px;color:var(--muted);white-space:pre-wrap}
    .verification-live-progress{display:grid;gap:9px;margin:8px 0 14px;padding:14px;border:1px solid var(--border);border-radius:10px;background:color-mix(in srgb,var(--accent) 7%,var(--surface))}.verification-live-progress-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.verification-live-progress-head strong{line-height:1.5}.verification-live-progress-head span{color:var(--accent);font-size:18px;font-weight:800}.verification-live-progress-track{height:12px;overflow:hidden;border-radius:999px;background:color-mix(in srgb,var(--border) 65%,transparent)}.verification-live-progress-fill{height:100%;border-radius:inherit;background:var(--accent-gradient);transition:width .45s ease}.verification-live-progress.running .verification-live-progress-fill{animation:verification-progress-pulse 1s ease-in-out infinite}.verification-live-progress small{color:var(--muted)}@keyframes verification-progress-pulse{0%,100%{filter:brightness(1)}50%{filter:brightness(1.2)}}
    @media(max-width:1000px){.verification-layout{grid-template-columns:1fr}.verification-task-list{position:static;max-height:none}.verification-stats{grid-template-columns:repeat(4,1fr)}}
    @media(max-width:700px){.verification-target-page-columns,.verification-formula-columns{display:none}.verification-target-page-row,.verification-formula-variable-row,.verification-formula-settings,.verification-formula-condition-row,.verification-readiness{grid-template-columns:1fr}.verification-target-page-row .btn,.verification-formula-variable-row .btn,.verification-formula-condition-row .btn{justify-self:end}.verification-target-page-head,.verification-formula-block-head{align-items:flex-start}.verification-setup-base-grid{grid-template-columns:1fr}.verification-setup-editor-head{align-items:flex-start;flex-direction:column}}
  `;
  document.head.appendChild(style);
})();
