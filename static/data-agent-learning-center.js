(function () {
  "use strict";

  const VIEW_LABELS = {
    samples: "学习样本",
    candidates: "规则候选",
    rules: "生效规则",
    metrics: "命中率",
  };
  const STATUS_LABELS = {
    pending: "待验证",
    verified: "已验证",
    invalid: "无效",
    collecting: "收集中",
    pending_regression: "待回归",
    regression_failed: "回归失败",
    pending_review: "待审批",
    approved: "已批准",
    rejected: "已拒绝",
    active: "生效中",
    superseded: "已替代",
    disabled: "已停用",
  };

  let state = null;
  let nextGeneration = 0;

  function beginRequest(targetState, tokenKey) {
    if (!targetState || state !== targetState) return null;
    targetState[tokenKey] += 1;
    return targetState[tokenKey];
  }

  function requestIsCurrent(targetState, tokenKey, requestToken) {
    return state === targetState
      && state.generation === targetState.generation
      && targetState[tokenKey] === requestToken;
  }

  function escapeHtml(value) {
    return state.options.escapeHtml(value);
  }

  function statusLabel(value) {
    return STATUS_LABELS[String(value)] || String(value || "-");
  }

  function statusBadge(value) {
    const tone = value === "verified" || value === "active" || value === "approved"
      ? "ok"
      : value === "invalid" || value === "regression_failed" || value === "rejected"
        ? "fail"
        : "warn";
    return `<span class="badge ${tone}">${escapeHtml(statusLabel(value))}</span>`;
  }

  function jsonText(value) {
    return escapeHtml(JSON.stringify(value ?? {}, null, 2));
  }

  function compactJson(value) {
    if (value === undefined) return "（无）";
    const text = JSON.stringify(value);
    return text === undefined ? String(value) : text;
  }

  function sameValue(left, right) {
    if (left === right) return true;
    if (Array.isArray(left) || Array.isArray(right)) {
      if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) return false;
      return left.every((item, index) => sameValue(item, right[index]));
    }
    if (left && right && typeof left === "object" && typeof right === "object") {
      const keys = [...new Set([...Object.keys(left), ...Object.keys(right)])].sort();
      return keys.every((key) => Object.hasOwn(left, key) === Object.hasOwn(right, key) && sameValue(left[key], right[key]));
    }
    return false;
  }

  function contractDiff(initialContract, finalContract, path = "") {
    if (sameValue(initialContract, finalContract)) return [];
    const initialObject = initialContract && typeof initialContract === "object" && !Array.isArray(initialContract);
    const finalObject = finalContract && typeof finalContract === "object" && !Array.isArray(finalContract);
    if (initialObject && finalObject) {
      return [...new Set([...Object.keys(initialContract), ...Object.keys(finalContract)])]
        .sort()
        .flatMap((key) => contractDiff(initialContract[key], finalContract[key], path ? `${path}.${key}` : key));
    }
    return [{ field: path || "合同", before: initialContract, after: finalContract }];
  }

  function renderContractDiff(sample) {
    const differences = contractDiff(sample.initial_contract || {}, sample.final_contract || {});
    if (!differences.length) return '<span class="muted-text">无变更</span>';
    const rows = differences.map((item) => `<li><strong>${escapeHtml(item.field)}</strong>：${escapeHtml(compactJson(item.before))} → ${escapeHtml(compactJson(item.after))}</li>`).join("");
    return `<details><summary>${differences.length} 项差异</summary><ol>${rows}</ol></details>`;
  }

  function renderCorrectionSources(corrections) {
    const rows = (corrections || []).map((item) => `<li><strong>${escapeHtml(item.field || "-")}</strong> · ${escapeHtml(item.source || "未标注")}</li>`).join("");
    return rows ? `<ul>${rows}</ul>` : '<span class="muted-text">无修订</span>';
  }

  function sampleStatus(sample) {
    return sample.data_quality === "invalid" ? "invalid" : sample.status;
  }

  function learningReason(actionLabel) {
    const reason = window.prompt(`请输入${actionLabel}原因（将写入审核记录）`, "");
    return reason === null ? null : String(reason).trim();
  }

  function learningReviews(reviews) {
    const rows = (reviews || []).map((item) => `<li>${escapeHtml(item.action || "审核")} · ${escapeHtml(item.reason || "-")} · ${escapeHtml(item.create_time || "")}</li>`).join("");
    return rows ? `<ol>${rows}</ol>` : '<div class="empty">暂无审核记录</div>';
  }

  function learningTable(title, rows, columns) {
    const head = columns.map((item) => `<th>${escapeHtml(item.label)}</th>`).join("");
    const body = rows.length
      ? rows.map((row) => `<tr>${columns.map((item) => `<td>${item.render(row)}</td>`).join("")}</tr>`).join("")
      : `<tr><td colspan="${columns.length}"><div class="empty">暂无数据</div></td></tr>`;
    return `<section class="panel"><div class="panel-title"><h3>${escapeHtml(title)}</h3></div><div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div></section>`;
  }

  function learningCandidateActions(item) {
    const itemId = escapeHtml(item.id);
    const actions = [`<button class="btn secondary" type="button" data-learning-candidate="${itemId}">查看</button>`];
    if (item.status === "pending_regression") {
      actions.push(`<button class="btn secondary" type="button" data-learning-regression="${itemId}">运行回归</button>`);
    }
    if (item.status === "pending_review") {
      actions.push(`<button class="btn" type="button" data-learning-approve="${itemId}">批准</button>`);
      actions.push(`<button class="btn secondary" type="button" data-learning-reject="${itemId}">拒绝</button>`);
    }
    return actions.join(" ");
  }

  function learningRuleActions(item) {
    const itemId = escapeHtml(item.id);
    const actions = [`<button class="btn secondary" type="button" data-learning-rule="${itemId}">查看版本</button>`];
    if (item.status === "active" && item.scope === "project") {
      actions.push(`<button class="btn secondary" type="button" data-learning-promote="${itemId}">提升全局</button>`);
    }
    if (item.status === "active") {
      actions.push(`<button class="btn secondary" type="button" data-learning-disable="${itemId}">停用</button>`);
    }
    actions.push(`<button class="btn secondary" type="button" data-learning-rollback="${itemId}">回滚</button>`);
    return actions.join(" ");
  }

  function renderSamples() {
    return learningTable("学习样本", state.overview.samples || [], [
      { label: "指令", render: (item) => escapeHtml(item.instruction || "-") },
      { label: "规范合同差异", render: renderContractDiff },
      { label: "修订来源", render: (item) => renderCorrectionSources(item.corrections) },
      { label: "状态", render: (item) => statusBadge(sampleStatus(item)) },
      { label: "来源会话", render: (item) => escapeHtml(item.session_id || "-") },
      { label: "脚本", render: (item) => escapeHtml(item.script_key || "-") },
      { label: "时间", render: (item) => escapeHtml(item.create_time || "-") },
    ]);
  }

  function renderCandidates() {
    const table = learningTable("规则候选", state.overview.candidates || [], [
      { label: "模块", render: (item) => escapeHtml(item.module_key || "-") },
      { label: "规则", render: (item) => escapeHtml(item.rule_key || "-") },
      { label: "出现次数", render: (item) => escapeHtml(item.occurrence_count || 0) },
      { label: "状态", render: (item) => statusBadge(item.status) },
      { label: "操作", render: learningCandidateActions },
    ]);
    return `${table}<div id="dataAgentLearningDetail">${state.detailHtml}</div>`;
  }

  function renderRules() {
    const columns = [
      { label: "范围", render: (item) => escapeHtml(item.scope === "project" ? "当前项目" : "全局") },
      { label: "规则", render: (item) => escapeHtml(item.rule_key || "-") },
      { label: "版本", render: (item) => `v${escapeHtml(item.version || 0)}` },
      { label: "状态", render: (item) => statusBadge(item.status) },
      { label: "操作", render: learningRuleActions },
    ];
    const activeRules = learningTable("生效规则", state.overview.active_rules || [], columns);
    const versions = learningTable("最近版本", state.overview.recent_versions || [], columns);
    return `${activeRules}${versions}<div id="dataAgentLearningDetail">${state.detailHtml}</div>`;
  }

  function rateText(metric) {
    const pendingCount = Number(metric.pending_count || 0);
    if (metric.first_hit_rate == null) return `暂无已验证样本（待验证 ${pendingCount}）`;
    return `${(Number(metric.first_hit_rate) * 100).toFixed(1)}%（${Number(metric.first_hit_count || 0)}/${Number(metric.verified_count || 0)}，待验证 ${pendingCount}）`;
  }

  function scriptRateText(metric) {
    if (metric.first_hit_rate == null) return "暂无已验证样本";
    return `${(Number(metric.first_hit_rate) * 100).toFixed(1)}%（${Number(metric.first_hit_count || 0)}/${Number(metric.verified_count || 0)}）`;
  }

  function renderMetricPeriod(title, metric) {
    const totals = `
      <div class="stats" style="grid-template-columns:repeat(5,minmax(110px,1fr));">
        <div class="stat"><span>样本总数</span><strong>${escapeHtml(metric.sample_count || 0)}</strong></div>
        <div class="stat"><span>已验证</span><strong>${escapeHtml(metric.verified_count || 0)}</strong></div>
        <div class="stat"><span>待验证</span><strong>${escapeHtml(metric.pending_count || 0)}</strong></div>
        <div class="stat"><span>无效</span><strong>${escapeHtml(metric.invalid_count || 0)}</strong></div>
        <div class="stat"><span>首次命中率</span><strong style="font-size:16px;">${escapeHtml(rateText(metric))}</strong></div>
      </div>`;
    const scripts = learningTable("按脚本命中率", metric.by_script || [], [
      { label: "脚本", render: (item) => escapeHtml(item.script_key || "-") },
      { label: "首次命中率（命中/已验证）", render: (item) => escapeHtml(scriptRateText(item)) },
    ]);
    const fields = learningTable("按字段修订次数", metric.by_correction_field || [], [
      { label: "字段", render: (item) => escapeHtml(item.field || "-") },
      { label: "修订次数", render: (item) => escapeHtml(item.count || 0) },
    ]);
    return `<section class="panel" style="margin-bottom:16px;"><div class="panel-title"><h3>${escapeHtml(title)}</h3></div><div class="panel-body">${totals}${scripts}${fields}</div></section>`;
  }

  function renderMetrics() {
    const metrics = state.overview.metrics || {};
    return `${renderMetricPeriod("近 7 天", metrics.days_7 || {})}${renderMetricPeriod("近 30 天", metrics.days_30 || {})}`;
  }

  function renderCurrentView() {
    if (state.activeView === "candidates") return renderCandidates();
    if (state.activeView === "rules") return renderRules();
    if (state.activeView === "metrics") return renderMetrics();
    return renderSamples();
  }

  function renderShell() {
    const dialog = state.options.dialog;
    dialog.innerHTML = `
      <div class="modal-head"><div><h3>数据智能体学习中心</h3><p>规则至少由3次已验证修订生成，回归通过并由管理员批准后才会生效。</p></div><div class="actions"><button class="btn secondary" id="refreshLearningCenter" type="button">刷新</button><button class="btn secondary" id="closeLearningCenter" type="button">关闭</button></div></div>
      <div class="modal-body">
        <div class="actions" style="margin-bottom:16px;">
          <button class="btn ${state.activeView === "samples" ? "" : "secondary"}" type="button" data-learning-view="samples">${VIEW_LABELS.samples}</button>
          <button class="btn ${state.activeView === "candidates" ? "" : "secondary"}" type="button" data-learning-view="candidates">${VIEW_LABELS.candidates}</button>
          <button class="btn ${state.activeView === "rules" ? "" : "secondary"}" type="button" data-learning-view="rules">${VIEW_LABELS.rules}</button>
          <button class="btn ${state.activeView === "metrics" ? "" : "secondary"}" type="button" data-learning-view="metrics">${VIEW_LABELS.metrics}</button>
        </div>
        ${renderCurrentView()}
      </div>`;
    bindViews(dialog);
    bindExistingRuleActions(dialog);
  }

  async function refreshLearningCenter(targetState = state) {
    const requestToken = beginRequest(targetState, "overviewToken");
    if (requestToken === null) return false;
    targetState.detailToken += 1;
    targetState.detailHtml = "";
    if (targetState.hasRendered) renderShell();
    const overview = await targetState.options.api(`/api/data-scripts/agent/learning/overview?project_id=${encodeURIComponent(targetState.options.projectId)}`);
    if (!requestIsCurrent(targetState, "overviewToken", requestToken)) return false;
    targetState.detailToken += 1;
    targetState.overview = overview;
    targetState.detailHtml = "";
    targetState.hasRendered = true;
    renderShell();
    return true;
  }

  async function showLearningCandidate(candidateId, targetState) {
    const requestToken = beginRequest(targetState, "detailToken");
    if (requestToken === null) return;
    const detail = await targetState.options.api(`/api/data-scripts/agent/learning/candidates/${encodeURIComponent(candidateId)}`);
    if (!requestIsCurrent(targetState, "detailToken", requestToken)) return;
    const candidate = detail.candidate || {};
    const samples = (detail.source_samples || []).map((item) => `
      <div class="panel-body"><strong>#${escapeHtml(item.id)}</strong> ${escapeHtml(item.instruction || "-")}<pre>${jsonText(item.corrections)}</pre></div>`).join("");
    targetState.detailHtml = `<section class="panel"><div class="panel-title"><h3>候选详情</h3><span>${statusBadge(candidate.status)}</span></div><div class="panel-body"><h4>回归结果</h4><pre>${jsonText(candidate.regression)}</pre><h4>来源样本</h4>${samples || '<div class="empty">暂无来源样本</div>'}<h4>候选规则</h4><pre>${jsonText(candidate.proposal)}</pre><h4>审核记录</h4>${learningReviews(detail.reviews)}</div></section>`;
    renderShell();
  }

  async function showLearningRule(ruleId, targetState) {
    const requestToken = beginRequest(targetState, "detailToken");
    if (requestToken === null) return null;
    const detail = await targetState.options.api(`/api/data-scripts/agent/learning/rules/${encodeURIComponent(ruleId)}`);
    if (!requestIsCurrent(targetState, "detailToken", requestToken)) return null;
    const history = (detail.history || []).map((item) => `<li>v${escapeHtml(item.version)} · ${escapeHtml(statusLabel(item.status))} · ID ${escapeHtml(item.id)}</li>`).join("");
    targetState.detailHtml = `<section class="panel"><div class="panel-title"><h3>规则版本详情</h3></div><div class="panel-body"><pre>${jsonText(detail.rule?.rule || {})}</pre><h4>版本历史</h4><ol>${history || "<li>暂无版本</li>"}</ol><h4>审核记录</h4>${learningReviews(detail.reviews)}</div></section>`;
    renderShell();
    return detail;
  }

  async function approveLearningRule(candidateId, targetState) {
    const reason = learningReason("批准");
    if (!reason) return;
    const requestToken = beginRequest(targetState, "actionToken");
    if (requestToken === null) return;
    await targetState.options.api(`/api/data-scripts/agent/learning/candidates/${encodeURIComponent(candidateId)}/approve`, { method: "POST", body: { reason } });
    if (!requestIsCurrent(targetState, "actionToken", requestToken)) return;
    targetState.options.showToast("学习规则已批准并在当前项目生效");
    await refreshLearningCenter(targetState);
  }

  async function promoteLearningRule(ruleId, targetState) {
    const reason = learningReason("提升为全局规则");
    if (!reason) return;
    const requestToken = beginRequest(targetState, "actionToken");
    if (requestToken === null) return;
    await targetState.options.api(`/api/data-scripts/agent/learning/rules/${encodeURIComponent(ruleId)}/promote`, { method: "POST", body: { reason } });
    if (!requestIsCurrent(targetState, "actionToken", requestToken)) return;
    targetState.options.showToast("学习规则已提升为全局规则");
    await refreshLearningCenter(targetState);
  }

  async function rollbackLearningRule(ruleId, targetState) {
    const requestToken = beginRequest(targetState, "actionToken");
    if (requestToken === null) return;
    const detail = await targetState.options.api(`/api/data-scripts/agent/learning/rules/${encodeURIComponent(ruleId)}`);
    if (!requestIsCurrent(targetState, "actionToken", requestToken)) return;
    const choices = (detail.history || []).filter((item) => Number(item.id) !== Number(ruleId));
    const hint = choices.map((item) => `ID ${item.id}: v${item.version}（${statusLabel(item.status)}）`).join("\n");
    const target = window.prompt(`请输入回滚目标版本ID：\n${hint}`, choices[0]?.id || "");
    if (target === null || !/^\d+$/.test(String(target).trim())) return;
    const reason = learningReason("回滚");
    if (!reason) return;
    await targetState.options.api(`/api/data-scripts/agent/learning/rules/${encodeURIComponent(ruleId)}/rollback`, { method: "POST", body: { target_version_id: Number(target), reason } });
    if (!requestIsCurrent(targetState, "actionToken", requestToken)) return;
    targetState.options.showToast("已创建新的回滚版本并生效");
    await refreshLearningCenter(targetState);
  }

  async function runLearningAction(url, actionLabel, targetState) {
    const requestToken = beginRequest(targetState, "actionToken");
    if (requestToken === null) return;
    await targetState.options.api(url, { method: "POST" });
    if (!requestIsCurrent(targetState, "actionToken", requestToken)) return;
    targetState.options.showToast(actionLabel);
    await refreshLearningCenter(targetState);
  }

  async function runReasonedLearningAction(url, actionLabel, targetState) {
    const reason = learningReason(actionLabel);
    if (!reason) return;
    const requestToken = beginRequest(targetState, "actionToken");
    if (requestToken === null) return;
    await targetState.options.api(url, { method: "POST", body: { reason } });
    if (!requestIsCurrent(targetState, "actionToken", requestToken)) return;
    targetState.options.showToast(`${actionLabel}完成`);
    await refreshLearningCenter(targetState);
  }

  function reportActionError(error, targetState) {
    if (state === targetState && !error?.detail) targetState.options.showToast(error?.message || "学习中心操作失败");
  }

  function bindAsync(dialog, selector, action) {
    const boundState = state;
    dialog.querySelectorAll(selector).forEach((button) => {
      button.addEventListener("click", () => {
        if (state !== boundState) return;
        Promise.resolve(action(button, boundState)).catch((error) => reportActionError(error, boundState));
      });
    });
  }

  function bindViews(dialog) {
    const boundState = state;
    dialog.querySelector("#closeLearningCenter")?.addEventListener("click", () => dialog.close());
    bindAsync(dialog, "#refreshLearningCenter", (_button, targetState) => refreshLearningCenter(targetState));
    dialog.querySelectorAll("[data-learning-view]").forEach((button) => {
      button.addEventListener("click", () => {
        if (state !== boundState) return;
        boundState.detailToken += 1;
        boundState.activeView = button.dataset.learningView;
        boundState.detailHtml = "";
        renderShell();
      });
    });
  }

  function bindExistingRuleActions(dialog) {
    bindAsync(dialog, "[data-learning-candidate]", (button, targetState) => showLearningCandidate(button.dataset.learningCandidate, targetState));
    bindAsync(dialog, "[data-learning-rule]", (button, targetState) => showLearningRule(button.dataset.learningRule, targetState));
    bindAsync(dialog, "[data-learning-regression]", (button, targetState) => runLearningAction(`/api/data-scripts/agent/learning/candidates/${encodeURIComponent(button.dataset.learningRegression)}/regression`, "回归完成", targetState));
    bindAsync(dialog, "[data-learning-approve]", (button, targetState) => approveLearningRule(button.dataset.learningApprove, targetState));
    bindAsync(dialog, "[data-learning-reject]", (button, targetState) => runReasonedLearningAction(`/api/data-scripts/agent/learning/candidates/${encodeURIComponent(button.dataset.learningReject)}/reject`, "拒绝", targetState));
    bindAsync(dialog, "[data-learning-promote]", (button, targetState) => promoteLearningRule(button.dataset.learningPromote, targetState));
    bindAsync(dialog, "[data-learning-disable]", (button, targetState) => runReasonedLearningAction(`/api/data-scripts/agent/learning/rules/${encodeURIComponent(button.dataset.learningDisable)}/disable`, "停用", targetState));
    bindAsync(dialog, "[data-learning-rollback]", (button, targetState) => rollbackLearningRule(button.dataset.learningRollback, targetState));
  }

  async function open(options) {
    if (!options?.isAdmin) return;
    if (!options.dialog || typeof options.api !== "function" || typeof options.escapeHtml !== "function") {
      throw new Error("学习中心初始化参数不完整");
    }
    const openState = {
      options,
      overview: {},
      activeView: "samples",
      detailHtml: "",
      generation: ++nextGeneration,
      overviewToken: 0,
      detailToken: 0,
      actionToken: 0,
      hasRendered: false,
    };
    state = openState;
    options.dialog.style.width = "min(1100px, calc(100vw - 32px))";
    options.dialog.innerHTML = '<div class="empty">正在加载学习中心...</div>';
    const rendered = await refreshLearningCenter(openState);
    if (rendered && state === openState && !options.dialog.open) options.dialog.showModal();
  }

  window.DataAgentLearningCenter = { open };
})();
