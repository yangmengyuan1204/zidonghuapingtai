(function () {
  const RESULT_OPTIONS = [
    { value: "untested", label: "未测试" },
    { value: "passed", label: "通过" },
    { value: "failed", label: "失败" },
    { value: "blocked", label: "阻塞" },
    { value: "needs_review", label: "需确认" },
    { value: "skipped", label: "跳过" },
  ];

  const CATEGORY_OPTIONS = [
    "主流程",
    "等价类",
    "边界值",
    "异常流程",
    "权限状态",
    "数据结果",
    "页面展示",
    "输入校验",
    "主流程",
    "异常流程",
    "权限/状态",
    "数据结果",
  ];

  function resultOptions(selected) {
    return RESULT_OPTIONS
      .map((item) => `<option value="${item.value}" ${item.value === selected ? "selected" : ""}>${item.label}</option>`)
      .join("");
  }

  const FUNCTIONAL_TERMINAL_STATUSES = new Set(["passed", "failed", "error", "blocked", "needs_review"]);

  function isTerminalFunctionalJob(job) {
    return FUNCTIONAL_TERMINAL_STATUSES.has(String(job?.status || ""));
  }

  function functionalExecutionToast(job) {
    return `执行完成：成功 ${job?.passed_count || 0} 条，失败 ${job?.failed_count || 0} 条，阻断 ${job?.blocked_count || 0} 条，需确认 ${job?.review_count || 0} 条`;
  }

  function augmentFunctionalExecutionSummary(job) {
    const summaryEl = document.querySelector(".functional-execution-summary");
    if (!summaryEl) return;
    if (!summaryEl.querySelector("[data-functional-blocked-count]")) {
      summaryEl.insertAdjacentHTML(
        "beforeend",
        '<div><span>阻断</span><strong class="danger-text" data-functional-blocked-count>0</strong></div>' +
          '<div><span>需确认</span><strong data-functional-review-count>0</strong></div>',
      );
    }
    const blockedEl = summaryEl.querySelector("[data-functional-blocked-count]");
    const reviewEl = summaryEl.querySelector("[data-functional-review-count]");
    if (blockedEl) blockedEl.textContent = String(job?.blocked_count || 0);
    if (reviewEl) reviewEl.textContent = String(job?.review_count || 0);
  }

  async function streamFunctionalExecutionProgress(initialJob) {
    if (!initialJob?.job_id || !window.fetch || !window.ReadableStream) throw new Error("stream unsupported");
    let lastJob = initialJob;
    let buffer = "";
    const response = await fetch(`/api/functional-executions/${initialJob.job_id}/events`, {
      headers: state.token ? { Authorization: `Bearer ${state.token}` } : {},
    });
    if (!response.ok || !response.body) throw new Error("stream unavailable");
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const line = part.split("\n").find((item) => item.startsWith("data: "));
        if (!line) continue;
        const payload = JSON.parse(line.slice(6));
        if (payload && payload.job_id) {
          lastJob = payload;
          window.renderFunctionalExecutionProgress(lastJob);
          augmentFunctionalExecutionSummary(lastJob);
        }
      }
    }
    return lastJob;
  }

  function patchFunctionalExecutionProgress() {
    if (typeof window === "undefined" || window.__requirementExecutionProgressPatched) return;
    window.__requirementExecutionProgressPatched = true;
    const originalDone = typeof window.isFunctionalExecutionDone === "function" ? window.isFunctionalExecutionDone : null;
    if (originalDone) {
      window.isFunctionalExecutionDone = (job) => isTerminalFunctionalJob(job) || originalDone(job);
    }
    const originalRender = typeof window.renderFunctionalExecutionProgress === "function" ? window.renderFunctionalExecutionProgress : null;
    if (originalRender) {
      window.renderFunctionalExecutionProgress = (job) => {
        originalRender(job);
        augmentFunctionalExecutionSummary(job);
      };
    }
    if (typeof window.watchFunctionalExecutionProgress === "function") {
      window.watchFunctionalExecutionProgress = async (initialJob) => {
        let job = initialJob;
        let closed = false;
        const onClose = () => {
          closed = true;
        };
        modalEl.addEventListener("close", onClose, { once: true });
        try {
          window.renderFunctionalExecutionProgress(job);
          job = await streamFunctionalExecutionProgress(job);
          if (!closed) {
            showToast(functionalExecutionToast(job));
            await renderFunctionalTests();
          }
          return;
        } catch (error) {
          // SSE 失败时回退到原有轮询。
        }
        while (true) {
          window.renderFunctionalExecutionProgress(job);
          if (isTerminalFunctionalJob(job)) break;
          await new Promise((resolve) => setTimeout(resolve, 1000));
          if (closed) return;
          job = await api(`/api/functional-executions/${job.job_id}`);
        }
        showToast(functionalExecutionToast(job));
        await renderFunctionalTests();
      };
    }
  }

  patchFunctionalExecutionProgress();

  function conclusionClass(decision) {
    if (decision === "ready") return "ok";
    if (decision === "risky") return "warn";
    return "fail";
  }

  // ── 工作流步骤导航 ──────────────────────────────
  const WORKFLOW_STEP_ICONS = {
    materials: "📋", cases: "🤖", review: "✅",
    ui_steps: "🧩", preflight: "🔍", execution: "▶️",
    diagnosis: "🩺", conclusion: "📊",
  };

  function renderWorkflowStepper(workflow) {
    if (!workflow || !workflow.steps) return "";
    const steps = workflow.steps || [];
    const current = workflow.current_stage || "";
    return `
      <div class="workflow-stepper">
        ${steps.map(function(s) {
          var cls = "workflow-step";
          if (s.key === current) cls += " current";
          else if (s.status === "done") cls += " done";
          else if (s.status === "warning") cls += " warning";
          else if (s.status === "blocked") cls += " blocked";
          else cls += " pending";
          var icon = WORKFLOW_STEP_ICONS[s.key] || "○";
          var iconEl = '<span class="step-icon">' + icon + '</span>';
          return '<div class="' + cls + '" title="' + escapeHtml(s.summary || s.label) + '">' + iconEl + escapeHtml(s.label) + '</div>';
        }).join("")}
      </div>
    `;
  }

  function renderReadinessBar(score) {
    if (score === undefined || score === null) return "";
    var cls = "high";
    if (score < 40) cls = "low";
    else if (score < 70) cls = "medium";
    return '<div class="readiness-score"><strong>' + score + '</strong>/100<div class="readiness-bar"><div class="readiness-fill ' + cls + '" style="width:' + score + '%"></div></div></div>';
  }

  function renderNextActionsBar(workflow) {
    if (!workflow || !workflow.next_actions || !workflow.next_actions.length) return "";
    var actions = workflow.next_actions.filter(function(a) { return a.key !== "check_diagnosis"; });
    if (!actions.length) return "";
    return '<div class="next-actions-bar"><strong>下一步建议：</strong>' +
      actions.map(function(a) {
        return '<button class="next-action-btn" data-next-action="' + escapeHtml(a.key) + '" data-case-ids="' + escapeHtml(JSON.stringify(a.target_case_ids || [])) + '">' + escapeHtml(a.label) + '</button>';
      }).join("") + '</div>';
  }

  function renderWorkflowPanel(key, label, status, summary, contentHtml, defaultOpen) {
    var cls = "workflow-panel";
    var statusCls = status || "pending";
    var statusLabels = { done: "✅ 已完成", warning: "⚠️ 待处理", blocked: "❌ 阻塞", pending: "⏳ 待进行" };
    var open = (status !== "done" && defaultOpen !== false) ? "" : " hidden";
    return '<div class="' + cls + '" data-workflow-panel="' + key + '">' +
      '<div class="workflow-panel-head" data-toggle-panel>' +
        '<strong>' + escapeHtml(label) + '</strong>' +
        '<span class="panel-status ' + statusCls + '">' + (statusLabels[status] || status) + '</span>' +
      '</div>' +
      (summary ? '<div style="padding:4px 16px;font-size:12px;color:var(--muted);border-bottom:1px solid var(--line)">' + escapeHtml(summary) + '</div>' : '') +
      '<div class="workflow-panel-body' + open + '">' + contentHtml + '</div>' +
    '</div>';
  }

  function loadWorkflow(taskId) {
    return api("/api/functional-tasks/" + taskId + "/workflow").catch(function() {
      return null;
    });
  }

  function renderConclusion(conclusion) {
    const data = conclusion || {};
    const feature = data.new_feature?.counts || {};
    const impact = data.impact?.counts || {};
    const check = data.data || {};
    return `
      <section class="requirement-section conclusion-${conclusionClass(data.decision)}">
        <div class="panel-title">
          <h3>测试结论</h3>
          <div class="actions"><button class="btn secondary" id="refreshConclusionBtn" type="button">刷新结论</button></div>
        </div>
        <div class="requirement-conclusion">
          <strong>${escapeHtml(data.decision_text || "待生成")}</strong>
          <p>${escapeHtml(data.summary || "暂无结论")}</p>
          <div class="functional-summary">
            <div><span>新功能</span><strong>${feature.passed || 0}/${feature.total || 0} 通过</strong></div>
            <div><span>P0 阻断</span><strong>${data.new_feature?.p0_blockers?.length || 0}</strong></div>
            <div><span>关联异常</span><strong>${data.impact?.failures?.length || 0}</strong></div>
            <div><span>数据核对</span><strong>${check.passed || 0}/${check.total || 0} 通过</strong></div>
          </div>
        </div>
      </section>
    `;
  }

  function renderImpactItems(task) {
    const rows = task.impact_items || [];
    return `
      <section class="requirement-section">
        <div class="panel-title">
          <h3>关联影响回归</h3>
          <div class="actions">
            ${isAdmin() ? `<button class="btn secondary" id="analyzeImpactBtn" type="button">生成关联影响清单</button><button class="btn" id="addImpactBtn" type="button">新增影响项</button>` : ""}
          </div>
        </div>
        ${renderTable(
          [
            { key: "title", label: "影响项" },
            { key: "item_type", label: "类型", render: (row) => badge(row.item_type) },
            { key: "target", label: "关联对象", render: (row) => escapeHtml(row.target || "-") },
            { key: "risk_level", label: "风险", render: (row) => badge(row.risk_level || "P1") },
            { key: "reason", label: "原因", render: (row) => escapeHtml(row.reason || "-") },
            {
              key: "test_result",
              label: "测试状态",
              render: (row) =>
                isAdmin()
                  ? `<select class="requirement-select" data-impact-status="${row.id}">${resultOptions(row.test_result || "untested")}</select>`
                  : badge(row.test_result || "untested"),
            },
            {
              key: "actions",
              label: "操作",
              render: (row) =>
                isAdmin()
                  ? `<div class="actions"><button class="btn secondary" data-edit-impact="${row.id}">编辑</button><button class="btn danger" data-delete-impact="${row.id}">删除</button></div>`
                  : "-",
            },
          ],
          rows,
          false,
        )}
      </section>
    `;
  }

  function renderDataChecks(task) {
    const rows = task.data_check_rules || [];
    return `
      <section class="requirement-section">
        <div class="panel-title">
          <h3>数据与流程核对</h3>
          <div class="actions">
            ${isAdmin() ? `<button class="btn secondary" id="runAllDataChecksBtn" type="button">执行全部核对</button><button class="btn" id="addDataCheckRuleBtn" type="button">新增核对规则</button>` : ""}
          </div>
        </div>
        ${renderTable(
          [
            { key: "rule_name", label: "核对项" },
            { key: "check_type", label: "类型", render: (row) => badge(row.check_type) },
            { key: "page_value", label: "页面值", render: (row) => escapeHtml(row.page_value || "-") },
            { key: "api_value_path", label: "接口取值", render: (row) => escapeHtml(row.api_value_path || "-") },
            { key: "latest_result", label: "结果", render: (row) => badge(row.latest_result?.result || "untested") },
            { key: "message", label: "说明", render: (row) => escapeHtml(row.latest_result?.message || "-") },
            {
              key: "actions",
              label: "操作",
              render: (row) =>
                `<div class="actions">
                  <button class="btn secondary" data-run-data-check="${row.id}">执行</button>
                  ${isAdmin() ? `<button class="btn secondary" data-edit-data-check="${row.id}">编辑</button><button class="btn danger" data-delete-data-check="${row.id}">删除</button>` : ""}
                </div>`,
            },
          ],
          rows,
          false,
        )}
      </section>
    `;
  }

  function requirementCaseGroupOptions(cases) {
    const groups = Array.from(new Set((cases || []).map((item) => item.category || "主流程").filter(Boolean)));
    return ['<option value="">全部分组</option>'].concat(groups.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)).join("");
  }

  function requirementWorkstationMetrics(task, cases) {
    const rows = cases || [];
    const summary = task?.preflight_summary || {};
    const trustedRows = rows.filter((item) => {
      return item.automation_status === "approved" && item.ui_case_id && item.quality_status === "executable";
    });
    const trialStatuses = new Set(["executable", "unchecked", "needs_review", "locator_risk"]);
    const trialRows = rows.filter((item) => {
      return item.automation_status === "approved" && item.ui_case_id && trialStatuses.has(item.quality_status || "unchecked");
    });
    const manualRows = rows.filter((item) => {
      const status = item.quality_status || "unchecked";
      return ["auth_risk", "missing_variables", "needs_review", "locator_risk", "not_recommended"].includes(status);
    });
    return {
      design: rows.length || summary.total || 0,
      trusted: Math.min(trustedRows.length || summary.executable || 0, 12),
      trial: trialRows.length || summary.trial_runnable || 0,
      manual: manualRows.length || summary.manual_check || 0,
      passed: rows.filter((item) => item.test_result === "passed").length,
      failed: rows.filter((item) => item.test_result === "failed").length,
      blocked: rows.filter((item) => item.test_result === "blocked").length,
    };
  }

  function renderRequirementCommandCenter(task, cases, executable) {
    const metrics = requirementWorkstationMetrics(task, cases);
    const hasCases = metrics.design > 0;
    return `
      <section class="requirement-command-center">
        <div class="requirement-command-head">
          <div>
            <strong>精简重构版 · 三步工作台</strong>
            <p>测试设计生成 20-30 条；可信执行池只保留 5-12 条适合自动化的用例；人工/高级场景不拖累自动执行。</p>
          </div>
          <span class="badge ok">默认串行执行</span>
        </div>
        <div class="requirement-command-metrics">
          <div><span>测试设计</span><strong>${escapeHtml(metrics.design)}</strong><small>目标 20-30 条</small></div>
          <div><span>可信执行池</span><strong>${escapeHtml(metrics.trusted)}</strong><small>默认执行 5-12 条</small></div>
          <div><span>可试跑</span><strong>${escapeHtml(metrics.trial)}</strong><small>不含缺账号/缺数据</small></div>
          <div><span>人工/高级</span><strong>${escapeHtml(metrics.manual)}</strong><small>权限/异常/复杂状态</small></div>
        </div>
        <div class="requirement-command-steps">
          <button class="btn" id="generateCasesBtn" type="button">1. 生成测试设计</button>
          <button class="btn secondary" id="preflightPackageBtn" type="button" ${hasCases ? "" : "disabled"}>2. 准备并预检</button>
          <button class="btn" id="executeFunctionalBtn" type="button" ${executable ? "" : "disabled"}>3. 执行可信用例</button>
          <button class="btn secondary" id="requirementRepairEntryBtn" type="button">诊断修复复跑</button>
        </div>
      </section>
    `;
  }

  function renderRequirementCaseBatchBar(cases) {
    if (!cases.length) return "";
    return `
      <div class="requirement-case-batchbar">
        <div class="requirement-case-batchbar-main">
          <label class="requirement-check-label">
            <input type="checkbox" id="requirementCaseSelectAll" />
            <span id="requirementCaseSelectedText">已选 0/${cases.length}</span>
          </label>
          <select class="requirement-select" id="requirementCaseBatchScope">
            <option value="selected">选中用例</option>
            <option value="all" selected>全部用例</option>
          </select>
          <select class="requirement-select" id="requirementCaseGroupScope">
            ${requirementCaseGroupOptions(cases)}
          </select>
        </div>
        <div class="actions">
          <button class="btn secondary" id="batchExecuteCasesBtn" type="button">执行当前选择</button>
          <details class="advanced-actions">
            <summary>高级操作</summary>
            <div class="actions">
              <select class="requirement-select" id="requirementCaseBatchStatus">
                ${resultOptions("passed")}
              </select>
              ${isAdmin() ? `<button class="btn secondary" id="batchUpdateCaseStatusBtn" type="button">批量标记</button><button class="btn secondary" id="batchGenerateStepsBtn" type="button">生成 UI 步骤</button><button class="btn secondary" id="batchApproveCasesBtn" type="button">批量确认</button><button class="btn secondary" id="seedTestDataBtn" type="button">抽样测试数据</button>` : ""}
            </div>
          </details>
        </div>
      </div>
    `;
  }

  function parseRequirementQualityReport(row) {
    if (!row?.quality_report) return {};
    if (typeof row.quality_report === "object") return row.quality_report;
    try {
      return JSON.parse(row.quality_report);
    } catch {
      return {};
    }
  }

  function renderRequirementPreflightOverview(summary = {}, cases = []) {
    const unchecked = summary.unchecked ?? cases.filter((item) => !item.quality_status || item.quality_status === "unchecked").length;
    const metrics = requirementWorkstationMetrics({ preflight_summary: summary }, cases);
    const trialRunnable = summary.trial_runnable ?? 0;
    const sampleReasons = cases
      .filter((item) => item.quality_status && item.quality_status !== "executable")
      .slice(0, 5)
      .map((item) => {
        const report = parseRequirementQualityReport(item);
        return `<li><strong>${escapeHtml(item.title || `#${item.id}`)}</strong><span>${escapeHtml(report.reason || item.quality_status || "")}</span></li>`;
      })
      .join("");
    return `
      <div class="requirement-preflight-overview">
        <div><span>测试设计</span><strong>${escapeHtml(metrics.design)}</strong></div>
        <div><span>可信执行池</span><strong>${escapeHtml(metrics.trusted)}</strong></div>
        <div><span>可试跑</span><strong>${escapeHtml(trialRunnable)}</strong></div>
        <div><span>人工/高级</span><strong>${escapeHtml(metrics.manual)}</strong></div>
        <div><span>登录阻断</span><strong>${escapeHtml(summary.auth_blocked ?? 0)}</strong></div>
        <div><span>缺真实数据</span><strong>${escapeHtml(summary.data_missing ?? 0)}</strong></div>
        <div><span>定位风险</span><strong>${escapeHtml(summary.locator_risk ?? 0)}</strong></div>
        <div><span>缺业务断言</span><strong>${escapeHtml(summary.missing_assertion ?? 0)}</strong></div>
        <div><span>未预检</span><strong>${escapeHtml(unchecked)}</strong></div>
        ${sampleReasons ? `<ul>${sampleReasons}</ul>` : ""}
      </div>
    `;
  }

  function computeCaseNextAction(row) {
    // 返回 { label, cls } 用于 "下一步" 列
    if (row.automation_status === "draft") return { label: "待确认", cls: "warn" };
    if (row.automation_status === "needs_review") return { label: "待确认", cls: "warn" };
    if (row.automation_status === "ui_steps_generated") return { label: "待确认", cls: "warn" };
    if (row.automation_status === "approved" && !row.ui_case_id) return { label: "生成UI步骤", cls: "info" };
    var qs = row.quality_status || "unchecked";
    if (qs === "unchecked") return { label: "待预检", cls: "info" };
    if (qs === "executable") return { label: "可执行", cls: "ok" };
    if (qs === "locator_risk") return { label: "修复定位器", cls: "warn" };
    if (qs === "missing_variables") return { label: "补测试数据", cls: "warn" };
    if (qs === "needs_review" || qs === "missing_assertion") return { label: "补充断言", cls: "warn" };
    if (qs === "auth_risk") return { label: "检查账号", cls: "fail" };
    if (qs === "not_recommended") return { label: "不可执行", cls: "fail" };
    if (row.test_result === "failed") return { label: "查看诊断", cls: "fail" };
    return { label: "-", cls: "info" };
  }

  function renderFunctionalMaterials(task) {
    var notes = task.requirement_notes || [];
    var html = '<div class="functional-materials">';
    html += '<div class="actions" style="margin-bottom:8px">';
    if (isAdmin()) {
      html += '<button class="btn secondary" id="uploadAxureBtn">上传Axure</button>';
      html += '<button class="btn secondary" id="uploadScreenshotBtn">上传截图</button>';
      html += '<button class="btn secondary" id="addRequirementNoteBtn">补充需求</button>';
      html += '<button class="btn secondary" id="scanPageBtn">扫描页面</button>';
    }
    html += '</div>';
    if (task.axure_path) {
      html += '<div class="material-item"><div class="material-head"><strong>Axure 文件</strong><span class="badge ok">已上传</span></div></div>';
    }
    if (task.screenshots && task.screenshots.length) {
      html += '<div class="material-item"><div class="material-head"><strong>截图</strong><span class="badge ok">' + task.screenshots.length + '张</span></div></div>';
    }
    if (notes.length) {
      notes.forEach(function(n) {
        html += '<div class="material-item"><div class="material-head"><strong>需求备注</strong></div><pre class="mini-log">' + escapeHtml(n.note_text) + '</pre></div>';
      });
    }
    html += '</div>';
    return html;
  }

  function renderNewFeatureCases(task, accounts, projects) {
    const latestSnapshot = task.snapshots?.[0];
    const cases = task.cases || [];
    const runs = task.runs || [];
    const executable = cases.some((item) => item.automation_status === "approved" && item.ui_case_id);
    return `
      <section class="requirement-section">
        <div class="panel-title">
          <h3>新功能验证</h3>
        </div>
        ${renderRequirementCommandCenter(task, cases, executable)}
        ${renderRequirementPreflightOverview(task.preflight_summary || {}, cases)}
        ${renderFunctionalMaterials(task)}
        ${renderRequirementCaseBatchBar(cases)}
        <div class="requirement-case-table">
        ${renderTable(
          [
            {
              key: "select",
              label: "选择",
              render: (row) => `<input class="requirement-case-check" type="checkbox" data-requirement-case-check="${row.id}" />`,
            },
            { key: "category", label: "分类", render: (row) => badge(row.category || "主流程") },
            { key: "title", label: "测试点" },
            { key: "priority", label: "优先级", render: (row) => badge(row.priority) },
            {
              key: "test_result",
              label: "测试状态",
              render: (row) =>
                isAdmin()
                  ? `<select class="requirement-select" data-functional-case-status="${row.id}">${resultOptions(row.test_result || "untested")}</select>`
                  : badge(row.test_result || "untested"),
            },
            { key: "automation_status", label: "自动化", render: (row) => badge(row.automation_status) },
            { key: "quality_status", label: "执行检查", render: (row) => badge(row.quality_status || "unchecked") },
            { key: "account_profile_name", label: "账号", render: (row) => escapeHtml(row.account_profile_name || "跟随任务") },
            {
              key: "next_action",
              label: "下一步",
              render: (row) => {
                var action = computeCaseNextAction(row);
                return '<span class="next-action-tag ' + action.cls + '">' + escapeHtml(action.label) + '</span>';
              },
            },
            {
              key: "actions",
              label: "操作",
              render: (row) => `
                <div class="actions">
                  <button class="btn secondary" data-functional-case-detail="${row.id}">详情</button>
                  <button class="btn" data-execute-functional-case="${row.id}" ${row.automation_status === "approved" && row.ui_case_id ? "" : "disabled"}>执行</button>
                  ${isAdmin() ? `<button class="btn secondary" data-edit-functional-case-pack="${row.id}">编辑</button><button class="btn secondary" data-generate-ui="${row.id}">生成步骤</button><button class="btn secondary" data-preflight-functional="${row.id}" ${row.ui_case_id ? "" : "disabled"}>试跑检查</button><button class="btn" data-approve-functional="${row.id}" ${row.ui_case_id ? "" : "disabled"}>确认</button>` : ""}
                </div>
              `,
            },
          ],
          cases,
          false,
        )}
        </div>
        <div class="functional-two-col">
          <section>
            <div class="panel-title"><h3>页面快照</h3></div>
            ${latestSnapshot ? `<pre class="mini-log">${escapeHtml(short(latestSnapshot.dom_summary || "", 1600))}</pre>` : `<div class="empty">还没有扫描真实页面 DOM</div>`}
          </section>
          <section>
            <div class="panel-title"><h3>执行记录</h3></div>
            ${renderTable(
              [
                { key: "id", label: "ID" },
                { key: "result", label: "结果", render: (row) => badge(row.result) },
                { key: "passed_count", label: "通过" },
                { key: "failed_count", label: "失败" },
                { key: "execute_time", label: "执行时间" },
                {
                  key: "actions",
                  label: "操作",
                  render: (row) => `<div class="actions"><button class="btn secondary" data-functional-run-timeline="${row.id}">📋 时间线</button></div>`,
                },
              ],
              runs,
              false,
            )}
          </section>
        </div>
      </section>
    `;
  }

  function renderNewFeatureCasesCompact(task, accounts, projects) {
    // 和 renderNewFeatureCases 一样，但去掉 execution records（已在专属面板中）
    var cases = task.cases || [];
    var latestSnapshot = task.snapshots?.[0];
    var executable = cases.some((item) => item.automation_status === "approved" && item.ui_case_id);
    return `
      <section class="requirement-section" style="margin:0;border-top:0">
        <div class="panel-title">
          <h3>新功能验证</h3>
        </div>
        ${renderRequirementCommandCenter(task, cases, executable)}
        ${renderRequirementPreflightOverview(task.preflight_summary || {}, cases)}
        ${renderRequirementCaseBatchBar(cases)}
        <div class="requirement-case-table">
        ${renderTable(
          [
            {
              key: "select",
              label: "选择",
              render: (row) => `<input class="requirement-case-check" type="checkbox" data-requirement-case-check="${row.id}" />`,
            },
            { key: "category", label: "分类", render: (row) => badge(row.category || "主流程") },
            { key: "title", label: "测试点" },
            { key: "priority", label: "优先级", render: (row) => badge(row.priority) },
            {
              key: "test_result",
              label: "测试状态",
              render: (row) =>
                isAdmin()
                  ? `<select class="requirement-select" data-functional-case-status="${row.id}">${resultOptions(row.test_result || "untested")}</select>`
                  : badge(row.test_result || "untested"),
            },
            { key: "automation_status", label: "自动化", render: (row) => badge(row.automation_status) },
            { key: "quality_status", label: "执行检查", render: (row) => badge(row.quality_status || "unchecked") },
            { key: "account_profile_name", label: "账号", render: (row) => escapeHtml(row.account_profile_name || "跟随任务") },
            {
              key: "next_action",
              label: "下一步",
              render: (row) => {
                var action = computeCaseNextAction(row);
                return '<span class="next-action-tag ' + action.cls + '">' + escapeHtml(action.label) + '</span>';
              },
            },
            {
              key: "actions",
              label: "操作",
              render: (row) => `
                <div class="actions">
                  <button class="btn secondary" data-functional-case-detail="${row.id}">详情</button>
                  <button class="btn" data-execute-functional-case="${row.id}" ${row.automation_status === "approved" && row.ui_case_id ? "" : "disabled"}>执行</button>
                  ${isAdmin() ? `<button class="btn secondary" data-edit-functional-case-pack="${row.id}">编辑</button><button class="btn secondary" data-generate-ui="${row.id}">生成步骤</button><button class="btn secondary" data-preflight-functional="${row.id}" ${row.ui_case_id ? "" : "disabled"}>试跑检查</button><button class="btn" data-approve-functional="${row.id}" ${row.ui_case_id ? "" : "disabled"}>确认</button>` : ""}
                </div>
              `,
            },
          ],
          cases,
          false,
        )}
        </div>
        ${latestSnapshot ? `<div class="panel-title" style="margin-top:12px"><h3>页面快照</h3></div><pre class="mini-log">${escapeHtml(short(latestSnapshot.dom_summary || "", 1600))}</pre>` : `<div class="empty" style="margin-top:12px">还没有扫描真实页面 DOM</div>`}
      </section>
    `;
  }

  function renderRequirementPackDetail(task, accounts = [], projects = [], workflow = null) {
    var hasWorkflow = workflow && workflow.steps;
    var summaryCtx = hasWorkflow ? (workflow.summary || {}) : {};
    return `
      <div class="panel-title">
        <h3>${escapeHtml(task.iteration_name)}</h3>
        <span>${badge(task.status)}</span>
      </div>
      <div class="functional-summary">
        <div><span>项目</span><strong>${escapeHtml(task.project_name || task.project_id)}</strong></div>
        <div><span>默认测试账号</span><strong>${escapeHtml(task.account_profile_name || "跟随项目默认账号")}</strong></div>
        <div><span>入口页面</span><strong>${escapeHtml(task.target_url)}</strong></div>
        <div><span>Axure</span><strong>${task.axure_path ? "已上传" : "未上传"}</strong></div>
      </div>
      ${hasWorkflow ? renderWorkflowStepper(workflow) : ""}
      ${hasWorkflow ? renderReadinessBar(workflow.readiness_score) : ""}
      ${hasWorkflow ? renderNextActionsBar(workflow) : ""}
      ${renderRequirementWorkflowContent(task, accounts, projects, workflow)}
    `;
  }

  function renderRequirementWorkflowContent(task, accounts, projects, workflow) {
    var stepsData = {};
    if (workflow && workflow.steps) {
      workflow.steps.forEach(function(s) { stepsData[s.key] = s; });
    }
    var s = function(key) { return stepsData[key] || { status: "pending", summary: "" }; };

    // Step 1: 需求材料 — requirement text + context + Axure/screenshot upload buttons
    var materialsHtml =
      '<details class="functional-requirement" open><summary>初始需求说明</summary><pre>' + escapeHtml(task.requirement_text || "暂无需求说明") + '</pre></details>' +
      renderContextEditor(task) +
      renderAxureScreenshotArea(task);

    // Step 2: 用例（含确认、UI步骤） — Compact 版本（去掉预检和执行的重复）
    var casesCombinedHtml = renderNewFeatureCasesCompact(task, accounts, projects);

    // Step 5: 预检 — preflight overview
    var preflightHtml = renderPreflightStandalone(task);

    // Step 6: 执行 — execution records
    var execHtml = renderExecutionRecords(task);

    // Step 7: 诊断 — diagnosis
    var diagHtml = '<div class="empty">执行失败后可点击「诊断」分析失败原因</div>';

    // Step 8: 结论 + 影响回归 + 数据核对
    var concHtml = renderConclusion(task.conclusion) + renderImpactItems(task) + renderDataChecks(task);

    return [
      renderWorkflowPanel("materials", "📋 需求材料", s("materials").status, s("materials").summary, materialsHtml),
      renderWorkflowPanel("cases", "🤖 测试用例（生成 → 确认 → UI步骤）", s("cases").status, s("cases").summary, casesCombinedHtml),
      renderWorkflowPanel("preflight", "🔍 执行前预检", s("preflight").status, s("preflight").summary, preflightHtml),
      renderWorkflowPanel("execution", "▶️ 执行记录", s("execution").status, s("execution").summary, execHtml),
      renderWorkflowPanel("diagnosis", "🩺 失败诊断", s("diagnosis").status, s("diagnosis").summary, diagHtml),
      renderWorkflowPanel("conclusion", "📊 测试结论", s("conclusion").status, s("conclusion").summary, concHtml),
    ].join("\n");
  }

  function renderContextEditor(task) {
    return '<details class="functional-requirement" open><summary>项目上下文</summary><div class="field"><textarea id="functionalContext" rows="4">' + escapeHtml(task.context || "") + '</textarea><div class="actions" style="margin-top:8px"><button class="btn secondary" id="saveContextBtn" type="button">保存上下文</button></div></div></details>';
  }

  function renderAxureScreenshotArea(task) {
    var hasAxure = !!task.axure_path;
    var hasNotes = task.requirement_notes && task.requirement_notes.length;
    return '<details class="functional-requirement"><summary>测试材料（Axure / 截图 / 扫描）</summary>' +
      '<div class="actions" style="margin:8px 0">' +
      (isAdmin() ? '<button class="btn secondary" id="uploadAxureBtn">上传Axure</button><button class="btn secondary" id="uploadScreenshotBtn">上传截图</button><button class="btn secondary" id="addRequirementNoteBtn">补充需求</button><button class="btn secondary" id="scanPageBtn">扫描页面</button><button class="btn secondary" id="bindFunctionalTaskAccount">默认账号</button>' : '') +
      '</div>' +
      (hasAxure ? '<div class="material-item"><div class="material-head"><strong>Axure 文件</strong><span class="badge ok">已上传</span></div></div>' : '<div class="empty">尚未上传 Axure 文件</div>') +
      (hasNotes ? '<div class="material-item"><div class="material-head"><strong>需求备注</strong></div>' + (task.requirement_notes || []).map(function(n) { return '<pre class="mini-log">' + escapeHtml(n.note_text) + '</pre>'; }).join("") + '</div>' : '') +
      '</details>';
  }

  function renderPreflightStandalone(task) {
    var summary = task.preflight_summary || {};
    if (!summary.total) return '<div class="empty">尚未执行预检，请在用例面板中点击「预检测试包」</div>';
    return renderRequirementPreflightOverview(summary, task.cases || []);
  }

  function renderExecutionRecords(task) {
    var runs = task.runs || [];
    if (!runs.length) return '<div class="empty">暂无执行记录</div>';
    var columns = [
      { key: "id", label: "ID" },
      { key: "result", label: "结果", render: function(row) { return badge(row.result); } },
      { key: "passed_count", label: "通过" },
      { key: "failed_count", label: "失败" },
      { key: "execute_time", label: "执行时间" },
      { key: "actions", label: "操作", render: function(row) {
        return '<div class="actions"><button class="btn secondary" data-functional-run-timeline="' + row.id + '">📋 时间线</button></div>';
      } },
    ];
    return renderTable(columns, runs, false);
  }

  async function renderRequirementPacks() {
    try {
      const projects = await getProjects();
      const tasks = await api(`/api/functional-tasks${queryString({ project_id: state.filters.projectId })}`);
      if (state.functionalTaskId && !tasks.some((item) => String(item.id) === String(state.functionalTaskId))) {
        state.functionalTaskId = "";
        localStorage.removeItem("functionalTaskId");
      }
      const selectedId = state.functionalTaskId || (tasks[0]?.id ? String(tasks[0].id) : "");
      const [selected, workflow] = await Promise.all([
        selectedId ? api(`/api/functional-tasks/${selectedId}`) : Promise.resolve(null),
        selectedId ? loadWorkflow(selectedId) : Promise.resolve(null),
      ]);
      const accounts = await api(`/api/test-accounts${queryString({ project_id: selected?.project_id || state.filters.projectId })}`);
      const projectName = (id) => (projects.find((item) => String(item.id) === String(id)) || {}).name || id;
      contentEl().innerHTML = `
      <div class="toolbar">
        <div class="filters">
          <div class="field compact"><label>项目</label><select id="functionalProjectFilter">${optionList(projects, "id", "name", state.filters.projectId)}</select></div>
        </div>
        <div class="actions">
          ${isAdmin() ? `<button class="btn secondary" id="aiConfigBtn">AI配置</button><button class="btn" id="newFunctionalTask">新增需求测试包</button>` : ""}
        </div>
      </div>
      <div class="functional-layout">
        <section class="panel functional-list">
          <div class="panel-title"><h3>需求测试包</h3></div>
          ${renderTable(
            [
              { key: "iteration_name", label: "需求/迭代" },
              { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },
              { key: "status", label: "状态", render: (row) => badge(row.status) },
              { key: "actions", label: "操作", render: (row) => `<div class="actions"><button class="btn secondary" data-open-functional="${row.id}">查看</button>${isAdmin() ? `<button class="btn danger" data-del-functional="${row.id}">删除</button>` : ""}</div>` },
            ],
            tasks,
            false,
          )}
        </section>
        <section class="panel functional-detail">
          ${selected ? renderRequirementPackDetail(selected, accounts, projects, workflow) : `<div class="empty">暂无需求测试包</div>`}
        </section>
      </div>
    `;
      bindRequirementPackPage(selected, accounts, projects);
    } catch (error) {
      console.error("renderRequirementPacks 渲染失败:", error);
      contentEl().innerHTML = `<div class="error-panel">页面加载失败: ${escapeHtml(error.message)}</div>`;
    }
  }

  function bindRequirementPackPage(task, accounts = [], projects = []) {
    document.querySelector("#functionalProjectFilter")?.addEventListener("change", async (event) => {
      state.filters.projectId = event.target.value;
      localStorage.setItem("projectId", state.filters.projectId);
      state.functionalTaskId = "";
      localStorage.removeItem("functionalTaskId");
      await renderFunctionalTests();
    });
    document.querySelectorAll("[data-open-functional]").forEach((button) => {
      button.addEventListener("click", async () => {
        state.functionalTaskId = button.dataset.openFunctional;
        localStorage.setItem("functionalTaskId", state.functionalTaskId);
        await renderFunctionalTests();
      });
    });
    document.querySelectorAll("[data-del-functional]").forEach((button) => {
      button.addEventListener("click", () => deleteItem("/api/functional-tasks/" + button.dataset.delFunctional, renderFunctionalTests));
    });
    if (isAdmin()) {
      document.querySelector("#newFunctionalTask")?.addEventListener("click", () => openFunctionalTaskForm(projects));
      document.querySelector("#aiConfigBtn")?.addEventListener("click", openAiConfigForm);
    }
    if (!task) return;
    bindFunctionalActions(task, accounts, projects);
    bindRequirementPackActions(task, accounts, projects);
    bindWorkflowPanelEvents(task, accounts, projects);
  }

  function bindWorkflowPanelEvents(task, accounts, projects) {
    // 面板折叠/展开
    document.querySelectorAll("[data-toggle-panel]").forEach(function(head) {
      var panel = head.closest("[data-workflow-panel]");
      if (!panel) return;
      head.addEventListener("click", function() {
        var body = panel.querySelector(".workflow-panel-body");
        if (body) body.classList.toggle("hidden");
      });
    });
    // 下一步建议按钮
    document.querySelectorAll("[data-next-action]").forEach(function(btn) {
      btn.addEventListener("click", function() {
        var action = btn.dataset.nextAction;
        var caseIds = [];
        try { caseIds = JSON.parse(btn.dataset.caseIds || "[]"); } catch(e) {}
        if (action === "generate_cases") {
          var genBtn = document.querySelector("#generateCasesBtn");
          if (genBtn) genBtn.click();
        } else if (action === "review_cases") {
          // 滚动到用例面板
          var panel = document.querySelector('[data-workflow-panel="cases"]');
          if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
        } else if (action === "generate_ui_steps") {
          if (caseIds.length) {
            // 勾选对应用例并点击批量生成
            caseIds.forEach(function(id) {
              var cb = document.querySelector('[data-requirement-case-check="' + id + '"]');
              if (cb) cb.checked = true;
            });
            var btn = document.querySelector("#batchGenerateStepsBtn");
            if (btn) btn.click();
          }
        } else if (action === "preflight") {
          var preflightBtn = document.querySelector("#preflightPackageBtn");
          if (preflightBtn) preflightBtn.click();
        } else if (action === "execute") {
          var execBtn = document.querySelector("#batchExecuteCasesBtn");
          if (execBtn) execBtn.click();
        } else if (action === "check_diagnosis") {
          var timelineBtn = document.querySelector('[data-functional-run-timeline]');
          if (timelineBtn) timelineBtn.click();
        }
      });
    });
  }

  function bindRequirementPackActions(task, accounts = [], projects = []) {
    const executeBtn = document.querySelector("#executeFunctionalBtn");
    if (executeBtn) {
      const cleanBtn = executeBtn.cloneNode(true);
      executeBtn.replaceWith(cleanBtn);
      cleanBtn.addEventListener("click", () => {
        const caseIds = (task.cases || [])
          .filter((item) => item.automation_status === "approved" && item.ui_case_id)
          .map((item) => item.id);
        if (!caseIds.length) return showToast("当前测试包没有已确认且已生成步骤的用例");
        openRequirementBatchExecuteForm(task, caseIds, accounts, projects);
      });
    }
    document.querySelector("#saveContextBtn")?.addEventListener("click", async () => {
      const value = document.querySelector("#functionalContext")?.value?.trim() || "";
      await api(`/api/functional-tasks/${task.id}/context`, { method: "PUT", body: { context: value } });
      showToast("上下文已保存");
      await renderFunctionalTests();
    });
    document.querySelector("#analyzeImpactBtn")?.addEventListener("click", async () => {
      const result = await api(`/api/functional-tasks/${task.id}/impact-items/analyze`, { method: "POST" });
      showToast(`已生成 ${result.created || 0} 个关联影响项`);
      await renderFunctionalTests();
    });
    document.querySelector("#addImpactBtn")?.addEventListener("click", () => openImpactItemForm(task));
    document.querySelectorAll("[data-edit-impact]").forEach((button) => {
      const item = (task.impact_items || []).find((row) => row.id === Number(button.dataset.editImpact));
      button.addEventListener("click", () => openImpactItemForm(task, item));
    });
    document.querySelectorAll("[data-delete-impact]").forEach((button) => {
      button.addEventListener("click", () => deleteItem(`/api/functional-impact-items/${button.dataset.deleteImpact}`, renderFunctionalTests));
    });
    document.querySelectorAll("[data-impact-status]").forEach((select) => {
      select.addEventListener("change", async () => {
        await api(`/api/functional-impact-items/${select.dataset.impactStatus}`, { method: "PUT", body: { test_result: select.value } });
        await renderFunctionalTests();
      });
    });
    document.querySelectorAll("[data-functional-case-status]").forEach((select) => {
      select.addEventListener("change", async () => {
        await api(`/api/functional-cases/${select.dataset.functionalCaseStatus}/status`, { method: "PUT", body: { test_result: select.value } });
        await renderFunctionalTests();
      });
    });
    document.querySelectorAll("[data-edit-functional-case-pack]").forEach((button) => {
      const item = (task.cases || []).find((row) => row.id === Number(button.dataset.editFunctionalCasePack));
      button.addEventListener("click", () => openRequirementCaseForm(item));
    });
    document.querySelector("#addDataCheckRuleBtn")?.addEventListener("click", () => openDataCheckRuleForm(task));
    document.querySelector("#runAllDataChecksBtn")?.addEventListener("click", async () => {
      const result = await api(`/api/functional-tasks/${task.id}/data-check-runs`, { method: "POST" });
      showToast(`已执行 ${result.results?.length || 0} 条数据核对`);
      await renderFunctionalTests();
    });
    document.querySelectorAll("[data-run-data-check]").forEach((button) => {
      button.addEventListener("click", async () => {
        await api(`/api/functional-data-check-rules/${button.dataset.runDataCheck}/execute`, { method: "POST" });
        showToast("数据核对已执行");
        await renderFunctionalTests();
      });
    });
    document.querySelectorAll("[data-edit-data-check]").forEach((button) => {
      const item = (task.data_check_rules || []).find((row) => row.id === Number(button.dataset.editDataCheck));
      button.addEventListener("click", () => openDataCheckRuleForm(task, item));
    });
    document.querySelectorAll("[data-delete-data-check]").forEach((button) => {
      button.addEventListener("click", () => deleteItem(`/api/functional-data-check-rules/${button.dataset.deleteDataCheck}`, renderFunctionalTests));
    });
    document.querySelector("#refreshConclusionBtn")?.addEventListener("click", async () => {
      await api(`/api/functional-tasks/${task.id}/conclusion`);
      showToast("结论已刷新");
      await renderFunctionalTests();
    });
    bindRequirementCaseBatchActions(task, accounts, projects);

    // 时间线按钮
    document.querySelectorAll("[data-functional-run-timeline]").forEach(function(button) {
      button.addEventListener("click", function() {
        openExecutionTimeline(Number(this.dataset.functionalRunTimeline));
      });
    });
  }

  function requirementCheckedCaseIds() {
    return Array.from(document.querySelectorAll("[data-requirement-case-check]:checked"))
      .map((item) => Number(item.dataset.requirementCaseCheck))
      .filter(Boolean);
  }

  function requirementCaseScopeIds(task) {
    const scope = document.querySelector("#requirementCaseBatchScope")?.value || "selected";
    const group = document.querySelector("#requirementCaseGroupScope")?.value || "";
    let rows = scope === "all" ? (task.cases || []) : (task.cases || []).filter((item) => requirementCheckedCaseIds().includes(item.id));
    if (group) rows = rows.filter((item) => String(item.category || "主流程") === group);
    return rows.map((item) => item.id);
  }

  function updateRequirementCaseBatchState(task) {
    const cases = task.cases || [];
    const checkedIds = new Set(requirementCheckedCaseIds());
    const scope = document.querySelector("#requirementCaseBatchScope")?.value || "selected";
    const group = document.querySelector("#requirementCaseGroupScope")?.value || "";
    const selectedText = document.querySelector("#requirementCaseSelectedText");
    const scopedCount = requirementCaseScopeIds(task).length;
    if (selectedText) selectedText.textContent = `${group || (scope === "all" ? "全部" : "已选")} ${scopedCount}/${cases.length}`;
    const selectAll = document.querySelector("#requirementCaseSelectAll");
    if (selectAll) {
      selectAll.checked = cases.length > 0 && checkedIds.size === cases.length;
      selectAll.indeterminate = checkedIds.size > 0 && checkedIds.size < cases.length;
    }
  }

  function selectedExecutableRequirementCases(task, ids) {
    const selected = new Set(ids || []);
    return (task.cases || []).filter((item) => {
      const inScope = selected.size ? selected.has(item.id) : false;
      return inScope && item.automation_status === "approved" && item.ui_case_id;
    });
  }

  function requirementExecutionModeCounts(task, caseIds) {
    const selected = new Set(caseIds || []);
    const trialStatuses = new Set(["executable", "unchecked", "needs_review", "locator_risk"]);
    const rows = (task.cases || []).filter((item) => {
      return selected.has(item.id) && item.automation_status === "approved" && item.ui_case_id;
    });
    const trusted = rows.filter((item) => item.quality_status === "executable").length;
    const trial = rows.filter((item) => trialStatuses.has(item.quality_status || "unchecked")).length;
    return { trusted, trial };
  }

  function renderRequirementExecutionModeLegacy(task, caseIds) {
    const counts = requirementExecutionModeCounts(task, caseIds);
    const trialChecked = counts.trusted <= 0 && counts.trial > 0;
    return `
      <details class="functional-requirement" id="requirementExecutionMode" open>
        <summary>执行模式</summary>
        <div class="form-grid">
          <label class="check-field">
            <input type="radio" name="__execution_mode" value="trusted" ${trialChecked ? "" : "checked"} />
            可信执行（${escapeHtml(counts.trusted)}）
          </label>
          <label class="check-field">
            <input type="radio" name="__execution_mode" value="trial" ${trialChecked ? "checked" : ""} ${counts.trial ? "" : "disabled"} />
            试跑风险用例（${escapeHtml(counts.trial)}）
          </label>
        </div>
        ${
          counts.trusted <= 0 && counts.trial > 0
            ? `<p class="muted-text">当前没有高可信用例，已默认切换为试跑模式。</p>`
            : `<p class="muted-text">试跑模式会执行定位风险、缺数据和需确认用例，结果仍按真实通过、失败、阻断或需确认分类。</p>`
        }
      </details>
    `;
  }

  function renderRequirementExecutionMode(task, caseIds) {
    const counts = requirementExecutionModeCounts(task, caseIds);
    const trialChecked = counts.trusted <= 0 && counts.trial > 0;
    return `
      <details class="functional-requirement" id="requirementExecutionMode" open>
        <summary>执行模式</summary>
        <div class="form-grid">
          <label class="check-field">
            <input type="radio" name="__execution_mode" value="trusted" ${trialChecked ? "" : "checked"} />
            可信执行（${escapeHtml(counts.trusted)}）
          </label>
          <label class="check-field">
            <input type="radio" name="__execution_mode" value="trial" ${trialChecked ? "checked" : ""} ${counts.trial ? "" : "disabled"} />
            试跑风险用例（${escapeHtml(counts.trial)}）
          </label>
        </div>
        <p class="muted-text">试跑模式只执行定位风险、需确认用例；缺数据和登录缺失仍会阻断，不会误绿。</p>
        <div class="form-grid">
          <label>并发数
            <select class="requirement-select" id="requirementParallelism">
              <option value="1" selected>1</option>
              <option value="2">2</option>
              <option value="3">3</option>
            </select>
          </label>
          <label class="check-field">
            <input type="checkbox" id="requirementSaveVariables" />
            保存本次非敏感运行变量
          </label>
        </div>
      </details>
    `;
  }

  function injectRequirementExecutionMode(task, caseIds) {
    const bodyEl = document.querySelector("#functionalExecuteForm .modal-body");
    if (!bodyEl || bodyEl.querySelector("#requirementExecutionMode")) return;
    bodyEl.insertAdjacentHTML("afterbegin", renderRequirementExecutionMode(task, caseIds));
  }

  function readRequirementExecutionForce() {
    return document.querySelector('#functionalExecuteForm input[name="__execution_mode"]:checked')?.value === "trial";
  }

  function readRequirementExecutionParallelism() {
    const raw = Number(document.querySelector("#requirementParallelism")?.value || 1);
    return Math.max(1, Math.min(raw || 1, 3));
  }

  function openRequirementBatchExecuteForm(task, caseIds, accounts = [], projects = []) {
    const filteredTask = { ...task, cases: (task.cases || []).filter((item) => caseIds.includes(item.id)) };
    openFunctionalExecutionModal({
      title: `预检并执行 ${caseIds.length} 条用例`,
      task: filteredTask,
      accounts,
      projects,
      submitLabel: "预检并执行",
      onSubmit: async (payload) => {
        payload.case_ids = caseIds;
        const trialMode = readRequirementExecutionForce();
        payload.force = trialMode;
        payload.execution_mode = trialMode ? "trial" : "trusted";
        payload.execution_policy = "isolated_per_case";
        payload.parallelism = readRequirementExecutionParallelism();
        payload.save_variables = Boolean(document.querySelector("#requirementSaveVariables")?.checked);
        const job = await api(`/api/functional-tasks/${task.id}/execute-async`, {
          method: "POST",
          body: payload,
        });
        await watchFunctionalExecutionProgress(job);
      },
    });
    injectRequirementExecutionMode(task, caseIds);
  }

  function isNotFoundError(error) {
    return String(error?.message || error || "").toLowerCase().includes("not found") || String(error?.status || "") === "404";
  }

  async function batchGenerateRequirementSteps(task, caseIds) {
    try {
      return await api(`/api/functional-tasks/${task.id}/cases/batch-generate-ui-steps`, {
        method: "POST",
        body: { case_ids: caseIds },
      });
    } catch (error) {
      if (!isNotFoundError(error)) throw error;
      let successCount = 0;
      let failedCount = 0;
      for (const caseId of caseIds) {
        try {
          await api(`/api/functional-cases/${caseId}/generate-ui-steps`, { method: "POST" });
          successCount += 1;
        } catch {
          failedCount += 1;
        }
      }
      return { success_count: successCount, failed_count: failedCount };
    }
  }

  async function batchApproveRequirementCases(task, caseIds) {
    try {
      return await api(`/api/functional-tasks/${task.id}/cases/batch-automation-status`, {
        method: "POST",
        body: { case_ids: caseIds, automation_status: "approved" },
      });
    } catch (error) {
      if (!isNotFoundError(error)) throw error;
      let updated = 0;
      const casesById = new Map((task.cases || []).map((item) => [item.id, item]));
      for (const caseId of caseIds) {
        const item = casesById.get(caseId);
        if (!item?.ui_case_id) continue;
        await api(`/api/functional-cases/${caseId}`, { method: "PUT", body: { automation_status: "approved" } });
        updated += 1;
      }
      return { updated, automation_status: "approved" };
    }
  }

  function renderRequirementPreflightResultLegacy(result) {
    const counts = result?.counts || {};
    const seed = result?.seed?.variables || {};
    const manualItems = result?.manual_check_items || [];
    return `
      <div class="preflight-report">
        <section class="diagnosis-summary">
          <strong>测试包预检完成</strong>
          <div>
            <span>测试设计：${escapeHtml(result?.design_case_count ?? counts.total ?? 0)}</span>
            <span>可信自动化：${escapeHtml(result?.trusted_case_count ?? result?.executable_count ?? 0)}</span>
            <span>可试跑：${escapeHtml(result?.trial_count ?? counts.trial_runnable ?? 0)}</span>
            <span>人工/高级：${escapeHtml(result?.manual_case_count ?? counts.manual_check ?? 0)}</span>
            <span>登录阻断：${escapeHtml(counts.auth_blocked ?? 0)}</span>
            <span>缺真实数据：${escapeHtml(counts.data_missing ?? 0)}</span>
          </div>
        </section>
        <section class="diagnosis-card">
          <div class="diagnosis-card-head"><span>登录与页面</span></div>
          <p>${escapeHtml(result?.login?.message || "-")}</p>
          <p>${escapeHtml(result?.page?.message || "-")}</p>
        </section>
        <section class="diagnosis-card">
          <div class="diagnosis-card-head"><span>抽样数据</span></div>
          ${
            Object.keys(seed).length
              ? `<pre class="mini-log">${escapeHtml(JSON.stringify(seed, null, 2))}</pre>`
              : `<div class="empty">暂未抽到可复用的真实搜索数据</div>`
          }
        </section>
        <section class="diagnosis-card">
          <div class="diagnosis-card-head"><span>人工核对/阻断项</span></div>
          ${
            manualItems.length
              ? `<ul>${manualItems
                  .slice(0, 30)
                  .map((item) => `<li><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.reason || item.quality_status)}</span></li>`)
                  .join("")}</ul>`
              : `<div class="empty">没有人工核对项</div>`
          }
        </section>
      </div>
    `;
  }

  function renderRequirementPreflightResult(result) {
    const counts = result?.counts || {};
    const seed = result?.seed?.variables || {};
    const manualItems = result?.manual_check_items || [];
    const groups = result?.case_groups || [];
    const missingVars = result?.missing_variables_detail || [];
    return `
      <div class="preflight-report">
        <section class="diagnosis-summary">
          <strong>测试包预检完成</strong>
          <div>
            <span>测试设计：${escapeHtml(result?.design_case_count ?? counts.total ?? 0)}</span>
            <span>可信自动化：${escapeHtml(result?.trusted_case_count ?? result?.executable_count ?? 0)}</span>
            <span>可试跑：${escapeHtml(result?.trial_count ?? counts.trial_runnable ?? 0)}</span>
            <span>人工/高级：${escapeHtml(result?.manual_case_count ?? counts.manual_check ?? 0)}</span>
            <span>登录阻断：${escapeHtml(counts.auth_blocked ?? 0)}</span>
            <span>缺数据：${escapeHtml(counts.data_missing ?? 0)}</span>
            <span>建议动作：${escapeHtml(result?.primary_action || "-")}</span>
          </div>
        </section>
        <section class="diagnosis-card">
          <div class="diagnosis-card-head"><span>用例分组</span></div>
          ${
            groups.length
              ? `<ul>${groups
                  .map(
                    (item) =>
                      `<li><strong>${escapeHtml(item.category || "-")}</strong><span>共 ${escapeHtml(item.total || 0)}，可执行 ${escapeHtml(item.executable || 0)}，阻断 ${escapeHtml(item.blocked || 0)}，需确认 ${escapeHtml(item.needs_review || 0)}</span></li>`,
                  )
                  .join("")}</ul>`
              : `<div class="empty">暂无分组数据</div>`
          }
        </section>
        <section class="diagnosis-card">
          <div class="diagnosis-card-head"><span>缺失变量填写</span></div>
          ${
            missingVars.length
              ? `<div class="form-grid">${missingVars
                  .map((item) => {
                    const value = item.suggested_value ?? seed[item.name] ?? "";
                    return `<label>${escapeHtml(item.name)}<input data-preflight-variable="${escapeHtml(item.name)}" value="${escapeHtml(value)}" placeholder="影响 ${escapeHtml((item.affected_case_ids || []).length)} 条用例" /></label>`;
                  })
                  .join("")}</div>
                <div class="actions" style="margin-top:8px">
                  <button class="btn secondary" type="button" id="requirementPreflightRerunBtn">使用变量重新预检</button>
                  <button class="btn primary" type="button" id="requirementPreflightSaveRerunBtn">保存变量并重新预检</button>
                </div>`
              : `<div class="empty">没有缺失变量</div>`
          }
        </section>
        <section class="diagnosis-card">
          <div class="diagnosis-card-head"><span>登录与页面</span></div>
          <p>${escapeHtml(result?.login?.message || "-")}</p>
          <p>${escapeHtml(result?.page?.message || "-")}</p>
        </section>
        <section class="diagnosis-card">
          <div class="diagnosis-card-head"><span>抽样数据</span></div>
          ${
            Object.keys(seed).length
              ? `<pre class="mini-log">${escapeHtml(JSON.stringify(seed, null, 2))}</pre>`
              : `<div class="empty">暂未抽到可复用的真实搜索数据</div>`
          }
        </section>
        <section class="diagnosis-card">
          <div class="diagnosis-card-head"><span>人工确认/阻断项</span></div>
          ${
            manualItems.length
              ? `<ul>${manualItems
                  .slice(0, 30)
                  .map((item) => `<li><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.reason || item.quality_status)}</span></li>`)
                  .join("")}</ul>`
              : `<div class="empty">没有人工确认项</div>`
          }
        </section>
      </div>
    `;
  }

  function readRequirementPreflightVariables() {
    const variables = {};
    document.querySelectorAll("[data-preflight-variable]").forEach((input) => {
      const name = input.getAttribute("data-preflight-variable");
      if (name && input.value.trim()) variables[name] = input.value.trim();
    });
    return variables;
  }

  function showRequirementPreflightResult(result, task, caseIds = []) {
    modalEl.innerHTML = `
      <div class="modal-head">
        <h3>测试包预检</h3>
        <button class="btn secondary" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body">${renderRequirementPreflightResult(result)}</div>
    `;
    modalEl.showModal();
    document.querySelector("#closeModal")?.addEventListener("click", async () => {
      modalEl.close();
      await renderFunctionalTests();
    });
    document.querySelector("#requirementPreflightRerunBtn")?.addEventListener("click", async () => {
      const variables = readRequirementPreflightVariables();
      modalEl.close();
      await runRequirementPackagePreflight(task, caseIds, variables, false);
    });
    document.querySelector("#requirementPreflightSaveRerunBtn")?.addEventListener("click", async () => {
      const variables = readRequirementPreflightVariables();
      modalEl.close();
      await runRequirementPackagePreflight(task, caseIds, variables, true);
    });
  }

  async function runRequirementPackagePreflight(task, caseIds = [], variables = {}, saveVariables = false) {
    try {
      showToast("正在预检测试包");
      const result = await api(`/api/functional-tasks/${task.id}/preflight-package`, {
        method: "POST",
        body: { case_ids: caseIds, variables, save_variables: saveVariables },
      });
      showToast(`预检完成：可信自动化 ${result.trusted_case_count ?? result.executable_count ?? 0} 条`);
      showRequirementPreflightResult(result, task, caseIds);
    } catch (error) {
      showToast(error.message || "预检失败");
    }
  }

  async function seedRequirementTestData(task) {
    try {
      showToast("正在抽样真实测试数据");
      const result = await api(`/api/functional-tasks/${task.id}/seed-test-data`, { method: "POST" });
      modalEl.innerHTML = `
        <div class="modal-head">
          <h3>测试数据抽样</h3>
          <button class="btn secondary" type="button" id="closeModal">关闭</button>
        </div>
        <div class="modal-body">
          <section class="diagnosis-summary"><strong>${escapeHtml(result.message || "抽样完成")}</strong></section>
          ${
            Object.keys(result.variables || {}).length
              ? `<pre class="mini-log">${escapeHtml(JSON.stringify(result.variables, null, 2))}</pre>`
              : `<div class="empty">建议先扫描目标页面，或执行一次能进入列表页的高可信用例，再重新抽样</div>`
          }
        </div>
      `;
      modalEl.showModal();
      document.querySelector("#closeModal")?.addEventListener("click", () => modalEl.close());
    } catch (error) {
      showToast(error.message || "抽样失败");
    }
  }

  function bindRequirementCaseBatchActions(task, accounts = [], projects = []) {
    const cases = task.cases || [];
    document.querySelector("#requirementCaseSelectAll")?.addEventListener("change", (event) => {
      document.querySelectorAll("[data-requirement-case-check]").forEach((checkbox) => {
        checkbox.checked = event.target.checked;
      });
      updateRequirementCaseBatchState(task);
    });
    document.querySelectorAll("[data-requirement-case-check]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => updateRequirementCaseBatchState(task));
    });
    document.querySelector("#requirementCaseBatchScope")?.addEventListener("change", () => updateRequirementCaseBatchState(task));
    document.querySelector("#requirementCaseGroupScope")?.addEventListener("change", () => updateRequirementCaseBatchState(task));
    updateRequirementCaseBatchState(task);

    document.querySelector("#batchUpdateCaseStatusBtn")?.addEventListener("click", async () => {
      const caseIds = requirementCaseScopeIds(task);
      if (!caseIds.length) return showToast("请选择要标记的用例");
      const testResult = document.querySelector("#requirementCaseBatchStatus")?.value || "untested";
      const result = await api(`/api/functional-tasks/${task.id}/cases/batch-status`, {
        method: "POST",
        body: { case_ids: caseIds, test_result: testResult },
      });
      showToast(`已更新 ${result.updated || 0} 条用例状态`);
      await renderFunctionalTests();
    });

    document.querySelector("#batchGenerateStepsBtn")?.addEventListener("click", async () => {
      const caseIds = requirementCaseScopeIds(task);
      if (!caseIds.length) return showToast("请选择要生成步骤的用例");
      showToast("正在批量生成 UI 步骤");
      const result = await batchGenerateRequirementSteps(task, caseIds);
      showToast(`生成完成：成功 ${result.success_count || 0} 条，失败 ${result.failed_count || 0} 条`);
      await renderFunctionalTests();
    });

    document.querySelector("#batchApproveCasesBtn")?.addEventListener("click", async () => {
      const caseIds = requirementCaseScopeIds(task);
      if (!caseIds.length) return showToast("请选择要确认的用例");
      const result = await batchApproveRequirementCases(task, caseIds);
      showToast(`已确认 ${result.updated || 0} 条可执行用例`);
      await renderFunctionalTests();
    });

    document.querySelector("#seedTestDataBtn")?.addEventListener("click", () => seedRequirementTestData(task));

    document.querySelector("#preflightPackageBtn")?.addEventListener("click", () => {
      const caseIds = requirementCaseScopeIds(task);
      runRequirementPackagePreflight(task, caseIds);
    });

    document.querySelector("#batchExecuteCasesBtn")?.addEventListener("click", () => {
      const caseIds = requirementCaseScopeIds(task);
      if (!caseIds.length) return showToast("请选择要执行的用例");
      const executableCases = selectedExecutableRequirementCases(task, caseIds);
      if (!executableCases.length) return showToast("所选范围内没有已确认且可执行的用例");
      openRequirementBatchExecuteForm(task, executableCases.map((item) => item.id), accounts, projects);
    });
    document.querySelector("#requirementRepairEntryBtn")?.addEventListener("click", async () => {
      const runs = task.runs || [];
      const target = runs.find((item) => ["failed", "blocked", "needs_review", "error"].includes(item.result)) || runs[0];
      if (!target) return showToast("暂无可诊断的执行记录");
      await openExecutionTimeline(target.id);
    });
  }

  function openImpactItemForm(task, item = null) {
    openForm(
      item ? "编辑关联影响项" : "新增关联影响项",
      [
        { name: "title", label: "影响项标题", required: true },
        { name: "item_type", label: "类型", type: "select", options: ["manual", "page", "api_case", "ui_case", "functional_case"].map((value) => ({ value, label: value })) },
        { name: "target", label: "关联对象" },
        { name: "risk_level", label: "风险等级", type: "select", options: ["P0", "P1", "P2"].map((value) => ({ value, label: value })) },
        { name: "test_result", label: "测试状态", type: "select", options: RESULT_OPTIONS },
        { name: "reason", label: "原因", type: "textarea", rows: 3 },
        { name: "remark", label: "备注", type: "textarea", rows: 3 },
      ],
      item || { item_type: "manual", risk_level: "P1", test_result: "untested" },
      async (data) => {
        await api(item ? `/api/functional-impact-items/${item.id}` : `/api/functional-tasks/${task.id}/impact-items`, { method: item ? "PUT" : "POST", body: data });
        showToast("关联影响项已保存");
        await renderFunctionalTests();
      },
    );
  }

  function openDataCheckRuleForm(task, item = null) {
    openForm(
      item ? "编辑数据核对规则" : "新增数据核对规则",
      [
        { name: "rule_name", label: "核对项名称", required: true },
        {
          name: "check_type",
          label: "核对类型",
          type: "select",
          options: [
            { value: "status_flow", label: "状态流转" },
            { value: "amount_quantity", label: "金额/数量" },
            { value: "page_api_consistency", label: "页面/API一致" },
          ],
        },
        { name: "page_value", label: "页面值" },
        { name: "api_method", label: "接口方法", type: "select", options: ["GET", "POST", "PUT", "PATCH"].map((value) => ({ value, label: value })) },
        { name: "api_url", label: "接口 URL" },
        { name: "api_headers", label: "接口请求头 JSON", type: "textarea", rows: 4, default: "{}" },
        { name: "api_body", label: "接口请求体 JSON", type: "textarea", rows: 5, default: "{}" },
        { name: "api_value_path", label: "接口取值路径", default: "json.data" },
        { name: "expected_value", label: "预期值" },
        { name: "compare_rule", label: "比较规则 JSON", type: "textarea", rows: 4, default: "{}" },
      ],
      item || { check_type: "page_api_consistency", api_method: "GET", api_headers: "{}", api_body: "{}", api_value_path: "json.data", compare_rule: "{}" },
      async (data) => {
        await api(item ? `/api/functional-data-check-rules/${item.id}` : `/api/functional-tasks/${task.id}/data-check-rules`, { method: item ? "PUT" : "POST", body: data });
        showToast("数据核对规则已保存");
        await renderFunctionalTests();
      },
    );
  }

  function openRequirementCaseForm(item) {
    if (!item) return;
    openForm(
      "编辑新功能测试点",
      [
        { name: "title", label: "测试点", required: true },
        { name: "category", label: "分类", type: "select", options: CATEGORY_OPTIONS.map((value) => ({ value, label: value })) },
        { name: "priority", label: "优先级", type: "select", options: ["P0", "P1", "P2"].map((value) => ({ value, label: value })) },
        { name: "precondition", label: "前置条件", type: "textarea", rows: 3 },
        { name: "steps", label: "测试步骤", type: "textarea", rows: 6 },
        { name: "expected", label: "预期结果", type: "textarea", rows: 4 },
        { name: "automation_status", label: "自动化状态", type: "select", options: ["draft", "ui_steps_generated", "approved", "needs_review"].map((value) => ({ value, label: value })) },
      ],
      item,
      async (data) => {
        await api(`/api/functional-cases/${item.id}`, { method: "PUT", body: data });
        showToast("测试点已保存");
        await renderFunctionalTests();
      },
    );
  }

  const originalOpenFunctionalTaskForm = typeof openFunctionalTaskForm === "function" ? openFunctionalTaskForm : null;
  openFunctionalTaskForm = function (projects) {
    const projectOptions = projects.map((item) => ({ value: item.id, label: item.name }));
    openForm(
      "新增需求测试包",
      [
        { name: "project_id", label: "项目", type: "select", options: projectOptions, required: true },
        { name: "iteration_name", label: "需求/迭代名称", required: true },
        { name: "target_url", label: "主要测试入口 URL", required: true },
        { name: "requirement_text", label: "需求说明", type: "textarea", rows: 8 },
      ],
      { project_id: state.filters.projectId || projects[0]?.id || "" },
      async (data) => {
        const task = await api("/api/functional-tasks", { method: "POST", body: data });
        state.functionalTaskId = String(task.id);
        localStorage.setItem("functionalTaskId", state.functionalTaskId);
        showToast("需求测试包已创建");
        await renderFunctionalTests();
      },
    );
  };

  const originalRenderFunctionalTests = typeof renderFunctionalTests === "function" ? renderFunctionalTests : null;
  renderFunctionalTests = renderRequirementPacks;
  window.renderFunctionalTests = renderRequirementPacks;

  // ── 执行时间线视图 ──────────────────────────────
  function renderExecutionTimelineHtml(data) {
    if (!data || !data.cases || !data.cases.length) {
      return '<div class="empty">暂无执行数据</div>';
    }
    var statusIcon = data.status === "passed" ? "✅" : (data.status === "failed" ? "❌" : "⏳");
    var casesHtml = data.cases.map(function(c) {
      var caseIcon = c.result === "passed" ? "✅" : (c.result === "failed" ? "❌" : (c.result === "blocked" ? "⛔" : "❓"));
      var stepsHtml = "";
      if (c.steps && c.steps.length) {
        stepsHtml = '<div class="timeline-steps">' + c.steps.map(function(s) {
          var stepIcon = s.status === "passed" ? "✅" : (s.status === "failed" ? "❌" : (s.status === "skipped" ? "⏭️" : "⏳"));
          var cls = "timeline-step" + (s.status === "failed" ? " step-failed" : "");
          var screenshotsHtml = "";
          if (s.screenshot_before) {
            screenshotsHtml += '<span class="timeline-shot-link" data-shot="' + escapeHtml(s.screenshot_before) + '">📷操作前</span>';
          }
          if (s.screenshot_after) {
            screenshotsHtml += '<span class="timeline-shot-link" data-shot="' + escapeHtml(s.screenshot_after) + '">📷操作后</span>';
          }
          if (s.screenshot_failure) {
            screenshotsHtml += '<span class="timeline-shot-link failure-shot" data-shot="' + escapeHtml(s.screenshot_failure) + '">📷失败截图</span>';
          }
          var detailHtml = "";
          if (s.locator) {
            detailHtml += '<div class="timeline-step-meta"><span class="meta-label">定位器</span><code>' + escapeHtml(s.locator) + '</code></div>';
          }
          if (s.value && s.action !== "password") {
            detailHtml += '<div class="timeline-step-meta"><span class="meta-label">输入值</span><code>' + escapeHtml(s.value) + '</code></div>';
          }
          if (s.url_before) {
            detailHtml += '<div class="timeline-step-meta"><span class="meta-label">执行前 URL</span><code class="url-text">' + escapeHtml(s.url_before) + '</code></div>';
          }
          if (s.url_after) {
            detailHtml += '<div class="timeline-step-meta"><span class="meta-label">执行后 URL</span><code class="url-text">' + escapeHtml(s.url_after) + '</code></div>';
          }
          if (s.duration_ms) {
            detailHtml += '<div class="timeline-step-meta"><span class="meta-label">耗时</span>' + s.duration_ms + 'ms</div>';
          }
          var errorHtml = "";
          if (s.status === "failed" && s.error) {
            errorHtml = '<div class="timeline-error"><strong>错误：</strong>' + escapeHtml(s.error) + '</div>';
            if (s.category) errorHtml += '<div class="timeline-error"><strong>分类：</strong>' + escapeHtml(s.category) + '</div>';
            if (s.reason) errorHtml += '<div class="timeline-error"><strong>原因：</strong>' + escapeHtml(s.reason) + '</div>';
            if (s.suggestion) errorHtml += '<div class="timeline-error"><strong>建议：</strong>' + escapeHtml(s.suggestion) + '</div>';
          }
          if (s.healed) {
            errorHtml += '<div class="timeline-healed"><strong>🔧 定位器自愈：</strong>' + escapeHtml(s.original_locator) + ' → ' + escapeHtml(s.suggested_locator) + '</div>';
          }
          return '<div class="' + cls + '">' +
            '<div class="timeline-step-head">' +
              '<span class="step-indicator">' + stepIcon + '</span>' +
              '<span class="step-name"><strong>Step ' + s.index + '</strong> ' + escapeHtml(s.name || s.action || "") + '</span>' +
              screenshotsHtml +
            '</div>' +
            (detailHtml ? '<div class="timeline-step-detail">' + detailHtml + '</div>' : "") +
            errorHtml +
          '</div>';
        }).join("") + '</div>';
      } else {
        stepsHtml = '<div class="timeline-empty">该用例无步骤日志</div>';
      }
      return '<div class="timeline-case ' + (c.result === "failed" ? "case-failed" : "") + '">' +
        '<div class="timeline-case-head" data-toggle-case-steps>' +
          '<span class="case-indicator">' + caseIcon + '</span>' +
          '<span class="case-title">' + escapeHtml(c.title) + '</span>' +
          '<span class="case-result badge badge-' + c.result + '">' + c.result + '</span>' +
        '</div>' +
        stepsHtml +
      '</div>';
    }).join("");

    // 诊断信息
    var diagHtml = "";
    if (data.diagnosis) {
      var diagData = (typeof data.diagnosis === "string") ? tryParseJson(data.diagnosis, null) : data.diagnosis;
      if (diagData && diagData.failed_cases && diagData.failed_cases.length) {
        diagHtml = '<div class="timeline-diagnosis">' +
          '<div class="diagnosis-card-head"><span>🩺 AI 诊断</span></div>' +
          (diagData.summary ? '<p class="diagnosis-summary-text">' + escapeHtml(diagData.summary) + '</p>' : "") +
          diagData.failed_cases.map(function(fc) {
            return '<div class="diagnosis-item">' +
              '<strong>' + escapeHtml(fc.case_title) + '</strong>' +
              '<div class="diagnosis-detail-line"><span class="meta-label">实际结果</span>' + escapeHtml(fc.failure || "") + '</div>' +
              '<div class="diagnosis-detail-line"><span class="meta-label">可能原因</span>' + escapeHtml(fc.likely_reason || "") + '</div>' +
              (fc.suggested_actions && fc.suggested_actions.length ?
                '<div class="diagnosis-detail-line"><span class="meta-label">建议</span><ul>' + fc.suggested_actions.map(function(a) { return '<li>' + escapeHtml(a) + '</li>'; }).join("") + '</ul></div>'
                : "") +
            '</div>';
          }).join("") +
          (diagData.overall_suggestions && diagData.overall_suggestions.length ?
            '<div class="diagnosis-overall"><strong>整体建议：</strong><ul>' + diagData.overall_suggestions.map(function(s) { return '<li>' + escapeHtml(s) + '</li>'; }).join("") + '</ul></div>'
            : "") +
        '</div>';
      }
    }

    return '<div class="timeline-view">' +
      '<div class="timeline-summary">' +
        '<strong>' + statusIcon + ' 执行 #' + data.run_id + '</strong>' +
        '<span>通过：' + (data.passed_count || 0) + '</span>' +
        '<span>失败：' + (data.failed_count || 0) + '</span>' +
        '<span>阻断：' + (data.blocked_count || 0) + '</span>' +
        '<span>需确认：' + (data.review_count || 0) + '</span>' +
        '<span>' + escapeHtml(data.summary || "") + '</span>' +
      '</div>' +
      casesHtml +
      diagHtml +
    '</div>';
  }

  function tryParseJson(text, fallback) {
    if (!text) return fallback;
    if (typeof text === "object") return text;
    try { return JSON.parse(text); } catch(e) { return fallback; }
  }

  async function openExecutionTimeline(runId) {
    try {
      showToast("正在加载执行时间线...");
      var data = await api("/api/functional-runs/" + runId + "/timeline");
      var canRepair = (data.failed_count || 0) > 0 || (data.blocked_count || 0) > 0 || (data.review_count || 0) > 0 || data.status !== "passed";
      var canApplyRepair = canRepair && isAdmin();
      modalEl.innerHTML = '' +
        '<div class="modal-head">' +
          '<h3>📋 执行时间线 #' + runId + '</h3>' +
          '<button class="btn secondary" type="button" id="closeModal">关闭</button>' +
        '</div>' +
        '<div class="modal-body timeline-modal-body">' +
          renderExecutionTimelineHtml(data) +
        '</div>' +
        '<div class="modal-foot"><span></span>' +
          '<button class="btn secondary" id="diagnoseFromTimelineBtn" type="button" ' + (data.failed_count > 0 ? "" : "disabled") + '>🩺 生成/刷新诊断</button>' +
        '</div>';
      modalEl.showModal();
      modalEl.querySelector(".modal-foot")?.insertAdjacentHTML(
        "beforeend",
        '<button class="btn secondary" id="repairPlanFromTimelineBtn" type="button" ' + (canRepair ? "" : "disabled") + '>生成修复计划</button>' +
          '<button class="btn" id="applyRepairFromTimelineBtn" type="button" ' + (canRepair ? "" : "disabled") + '>应用安全修复</button>',
      );
      if (!canApplyRepair) document.querySelector("#applyRepairFromTimelineBtn")?.setAttribute("disabled", "disabled");
      document.querySelector("#closeModal")?.addEventListener("click", function() { modalEl.close(); });
      // 诊断按钮
      document.querySelector("#diagnoseFromTimelineBtn")?.addEventListener("click", async function() {
        var btn = this;
        btn.disabled = true;
        btn.textContent = "诊断中...";
        try {
          await api("/api/functional-runs/" + runId + "/diagnose", { method: "POST" });
          showToast("诊断完成，刷新时间线");
          modalEl.close();
          await openExecutionTimeline(runId);
        } catch(e) {
          showToast(e.message || "诊断失败");
          btn.disabled = false;
          btn.textContent = "🩺 生成/刷新诊断";
        }
      });
      // 截图点击放大
      document.querySelector("#repairPlanFromTimelineBtn")?.addEventListener("click", async function() {
        var btn = this;
        btn.disabled = true;
        btn.textContent = "生成中...";
        try {
          var plan = await api("/api/functional-runs/" + runId + "/repair-plan", { method: "POST" });
          showToast("修复计划已生成：可自动修复 " + (plan.auto_fixable_count || 0) + " 项");
        } catch(e) {
          showToast(e.message || "生成修复计划失败");
        } finally {
          btn.disabled = false;
          btn.textContent = "生成修复计划";
        }
      });
      document.querySelector("#applyRepairFromTimelineBtn")?.addEventListener("click", async function() {
        var btn = this;
        btn.disabled = true;
        btn.textContent = "应用中...";
        try {
          var result = await api("/api/functional-runs/" + runId + "/apply-repair", { method: "POST", body: {} });
          showToast("安全修复已应用：" + (result.applied_count || 0) + " 处");
          modalEl.close();
          await openExecutionTimeline(runId);
        } catch(e) {
          showToast(e.message || "应用修复失败");
          btn.disabled = false;
          btn.textContent = "应用安全修复";
        }
      });
      modalEl.querySelectorAll("[data-shot]").forEach(function(el) {
        el.addEventListener("click", function() {
          var shotPath = this.dataset.shot;
          if (shotPath) openProtectedFile("/api/files/screenshot?path=" + encodeURIComponent(shotPath));
        });
      });
      // 用例步骤折叠
      modalEl.querySelectorAll("[data-toggle-case-steps]").forEach(function(el) {
        el.addEventListener("click", function() {
          var stepsEl = this.nextElementSibling;
          if (stepsEl) stepsEl.classList.toggle("hidden");
        });
      });
    } catch (error) {
      showToast(error.message || "加载时间线失败");
    }
  }

  if (typeof state !== "undefined" && state.view === "functionalTests" && typeof renderShell === "function") {
    renderShell().catch((error) => showToast(error.message || "页面加载失败"));
  }
})();
