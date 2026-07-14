(function () {
  if (window.__testRecordReportLoaded) return;
  window.__testRecordReportLoaded = true;

  function withScriptIdentity(flow, variables) {
    return {
      ...(variables || {}),
      _data_script_flow_id: flow?.id || "",
      _data_script_name: flow?.name || "",
    };
  }

  const originalRunSavedFlow = window.runSavedFlow;
  if (typeof originalRunSavedFlow === "function") {
    window.runSavedFlow = function (flow, runtimeVariables = null, options = {}) {
      const variables = runtimeVariables && typeof runtimeVariables === "object"
        ? runtimeVariables
        : window.safeVariables?.(flow?.variables || "{}") || {};
      return originalRunSavedFlow(flow, withScriptIdentity(flow, variables), options);
    };
  }

  function interfaceText(row) {
    const values = Array.isArray(row?.interface_names) ? row.interface_names : [];
    return values.length ? values.join("、") : "-";
  }

  const originalRecordColumns = window.recordColumns;
  if (typeof originalRecordColumns === "function") {
    window.recordColumns = function (options = {}) {
      const columns = originalRecordColumns(options).filter((column) => column.key !== "case_id");
      const actionIndex = columns.findIndex((column) => column.key === "actions");
      const insertAt = actionIndex >= 0 ? actionIndex : columns.length;
      columns.splice(insertAt, 0,
        {
          key: "script_name",
          label: "脚本名称",
          render: (row) => escapeHtml(row.script_name || "-"),
        },
        {
          key: "interface_names",
          label: "接口名称",
          render: (row) => escapeHtml(interfaceText(row)),
        },
      );
      return columns;
    };
  }

  function parseSummary(rawText) {
    let parsed = null;
    try {
      const candidate = JSON.parse(rawText || "");
      if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) parsed = candidate;
    } catch {
      return { parsed: null, summary: null };
    }
    let summary = null;
    if (parsed?.summary && typeof parsed.summary === "object" && Object.keys(parsed.summary).length) {
      summary = parsed.summary;
    } else if (parsed?.variables && typeof parsed.variables === "object" && Object.keys(parsed.variables).length) {
      summary = parsed.variables;
    } else if (parsed && typeof parsed === "object" && Object.keys(parsed).length) {
      const metaKeys = ["script", "mode", "started_at", "finished_at", "duration_ms", "steps", "batches", "shops", "login", "backend", "backend_porder", "_runtime"];
      if (!metaKeys.some((key) => key in parsed)) summary = parsed;
    }
    return { parsed, summary };
  }

  window.showLog = function (item) {
    const rawText = item?.log || "";
    const { parsed, summary } = parseSummary(rawText);
    const modal = document.querySelector("#modal");
    if (!modal) return;
    const scriptName = item?.script_name || parsed?.script || "-";
    const interfaceNames = Array.isArray(item?.interface_names) ? item.interface_names : [];
    const interfacesHtml = interfaceNames.length
      ? `<ul>${interfaceNames.map((name) => `<li>${escapeHtml(name)}</li>`).join("")}</ul>`
      : "<span>-</span>";
    const summaryHtml = summary && typeof window.renderChineseSummary === "function"
      ? `<div class="summary-wrap">${window.renderChineseSummary(summary)}</div>`
      : "";
    modal.innerHTML = `
      <div class="modal-head">
        <h3>脚本执行结果 #${escapeHtml(item?.id || "")}</h3>
        <button class="btn secondary" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body">
        <div class="record-report-meta">
          <div><strong>脚本名称：</strong>${escapeHtml(scriptName)}</div>
          <div><strong>接口名称：</strong>${interfacesHtml}</div>
        </div>
        ${summaryHtml}
        <details class="summary-detail"><summary>查看原始日志</summary><pre class="log-view">${escapeHtml(rawText)}</pre></details>
      </div>
    `;
    modal.showModal();
    document.querySelector("#closeModal")?.addEventListener("click", () => modal.close());
  };
})();
