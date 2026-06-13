(function () {
  "use strict";

  const STATUS_OPTIONS = [
    { value: "untested", label: "未测试" },
    { value: "passed", label: "通过" },
    { value: "failed", label: "失败" },
    { value: "blocked", label: "阻塞" },
    { value: "skipped", label: "跳过" },
  ];

  function initCaseGenerationState() {
    if (typeof state === "undefined") return;
    state.caseGenerationProjectId =
      state.caseGenerationProjectId ||
      localStorage.getItem("caseGenerationProjectId") ||
      state.filters.projectId ||
      localStorage.getItem("projectId") ||
      "";
  }

  function parseJson(value, fallback) {
    try {
      const parsed = JSON.parse(value || "");
      return parsed ?? fallback;
    } catch {
      return fallback;
    }
  }

  function resultBadge(value) {
    const item = STATUS_OPTIONS.find((option) => option.value === value) || STATUS_OPTIONS[0];
    const cls = value === "passed" ? "ok" : value === "failed" ? "fail" : value === "blocked" ? "warn" : "";
    return `<span class="badge ${cls}">${escapeHtml(item.label)}</span>`;
  }

  function statusOptions(selected) {
    return STATUS_OPTIONS.map(
      (item) => `<option value="${item.value}" ${item.value === (selected || "untested") ? "selected" : ""}>${item.label}</option>`,
    ).join("");
  }

  function sourceLabel(row) {
    const refs = parseJson(row.source_refs, {});
    const parts = [];
    if ((refs.screenshots || []).length) parts.push(`截图${refs.screenshots.length}张`);
    if ((refs.notes || []).length) parts.push(`补充需求${refs.notes.length}条`);
    const text = parts.length ? parts.join(" / ") : "手工";
    return row.source_missing ? `${text}（来源已删除）` : text;
  }

  function confidenceText(value) {
    const score = Number(value || 0);
    return score > 0 ? `${Math.round(score * 100)}%` : "未识别";
  }

  function activeProjectId(projects) {
    if (!projects.length) return "";
    if (!state.caseGenerationProjectId || !projects.some((item) => String(item.id) === String(state.caseGenerationProjectId))) {
      state.caseGenerationProjectId = String(projects[0].id);
      localStorage.setItem("caseGenerationProjectId", state.caseGenerationProjectId);
    }
    return state.caseGenerationProjectId;
  }

  function injectCaseGenerationStyles() {
    if (document.getElementById("case-generation-style")) return;
    const style = document.createElement("style");
    style.id = "case-generation-style";
    style.textContent = `
.case-generation-page{display:grid;gap:16px}
.case-generation-top{display:flex;align-items:end;justify-content:space-between;gap:14px;flex-wrap:wrap}
.case-generation-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(320px,.72fr);gap:16px;align-items:start}
.case-generation-stack{display:grid;gap:16px;min-width:0}
.case-generation-card{display:grid;gap:10px;padding:12px;border:1px solid var(--line);border-radius:var(--radius-sm);background:rgba(255,255,255,.62)}
.case-generation-card-head,.case-generation-batch{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.case-generation-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;color:var(--muted);font-size:12px}
.case-generation-ocr{display:grid;gap:8px}
.case-generation-ocr textarea{width:100%;min-height:110px;padding:10px 12px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--surface-solid);line-height:1.6;resize:vertical}
.case-generation-low{margin:0;color:#92400e;font-size:12px;line-height:1.5}
.case-generation-upload-zone{display:grid;gap:8px;place-items:center;min-height:150px;padding:22px;border:1px dashed var(--accent);border-radius:var(--radius-sm);background:rgba(37,99,235,.06);text-align:center;cursor:pointer}
.case-generation-upload-zone.drag-over{background:rgba(37,99,235,.12);box-shadow:0 0 0 3px var(--accent-glow)}
.case-generation-upload-list{display:grid;gap:8px;max-height:210px;margin-top:12px;overflow:auto}
.case-generation-upload-list div{display:flex;gap:10px;align-items:center;justify-content:space-between;padding:10px;border:1px solid var(--line);border-radius:var(--radius-sm);background:rgba(255,255,255,.62)}
.case-generation-select{min-height:34px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--surface-solid);padding:6px 8px}
.case-generation-source-missing{color:#92400e;font-size:12px;font-weight:700}
.case-generation-page td{white-space:normal}
.case-generation-page th,.case-generation-page td{max-width:460px}
@media (max-width:980px){.case-generation-grid{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  async function renderCaseGeneration() {
    initCaseGenerationState();
    injectCaseGenerationStyles();
    const projects = await getProjects();
    const projectId = activeProjectId(projects);
    const workspace = projectId ? await api(`/api/case-generation/workspace${queryString({ project_id: projectId })}`) : null;
    contentEl().innerHTML = `
      <div class="case-generation-page">
        <div class="case-generation-top">
          <div class="field compact">
            <label>项目</label>
            <select id="cgProjectSelect">${optionList(projects, "id", "name", projectId, "请选择项目")}</select>
          </div>
          <div class="actions">
            ${workspace && isAdmin() ? `<button class="btn secondary" id="uploadCgScreenshots">上传截图</button><button class="btn secondary" id="addCgNote">补充需求</button><button class="btn" id="generateCgCases">生成用例</button>` : ""}
          </div>
        </div>
        ${
          workspace
            ? `<div class="case-generation-grid">
                <div class="case-generation-stack">
                  ${renderScreenshots(workspace)}
                  ${renderCases(workspace)}
                </div>
                <div class="case-generation-stack">
                  ${renderNotes(workspace)}
                  ${renderStats(workspace)}
                </div>
              </div>`
            : `<div class="panel"><div class="empty">请先创建项目</div></div>`
        }
      </div>
    `;
    document.querySelector("#cgProjectSelect")?.addEventListener("change", async (event) => {
      state.caseGenerationProjectId = event.target.value;
      state.filters.projectId = event.target.value;
      localStorage.setItem("caseGenerationProjectId", event.target.value);
      localStorage.setItem("projectId", event.target.value);
      await renderCaseGeneration();
    });
    bindCaseGenerationActions(workspace, projectId);
  }

  function renderScreenshots(workspace) {
    const rows = workspace.screenshots || [];
    return `
      <section class="panel">
        <div class="panel-title">
          <h3>截图材料</h3>
          <span class="muted-text">${rows.length} 张</span>
        </div>
        <div class="panel-body">
          ${
            rows.length
              ? rows.map((item, index) => renderScreenshotCard(item, rows.length - index)).join("")
              : `<div class="empty">上传截图后，可识别文字并生成执行用例</div>`
          }
        </div>
      </section>
    `;
  }

  function renderScreenshotCard(item, index) {
    const lowItems = parseJson(item.low_confidence_items, []);
    const corrected = item.corrected_text || item.ocr_text || "";
    const lowText = lowItems
      .slice(0, 8)
      .map((row) => row.text)
      .filter(Boolean)
      .join("、");
    return `
      <div class="case-generation-card">
        <div class="case-generation-card-head">
          <strong>截图 ${index} · #${item.id}</strong>
          <div class="actions">
            <button class="btn secondary" data-cg-shot-view="${item.id}">查看</button>
            ${isAdmin() ? `<button class="btn secondary" data-cg-shot-analyze="${item.id}">识别</button><button class="btn danger" data-cg-shot-delete="${item.id}">删除</button>` : ""}
          </div>
        </div>
        <div class="case-generation-meta">
          <span>置信度：${escapeHtml(confidenceText(item.ocr_confidence))}</span>
          <span>${item.needs_manual_confirm ? "建议校对" : "已校对/可用"}</span>
          ${item.ocr_error ? `<span>OCR提示：${escapeHtml(short(item.ocr_error, 80))}</span>` : ""}
        </div>
        <div class="case-generation-ocr">
          <label class="muted-text">识别结果校对</label>
          <textarea data-cg-ocr-text="${item.id}" ${isAdmin() ? "" : "disabled"} placeholder="识别后会展示 OCR 文本，也可以直接手工补充截图文字">${escapeHtml(corrected)}</textarea>
          ${lowText ? `<p class="case-generation-low">低置信度：${escapeHtml(lowText)}</p>` : ""}
          ${isAdmin() ? `<div class="actions"><button class="btn secondary" data-cg-ocr-save="${item.id}">保存校对</button></div>` : ""}
        </div>
      </div>
    `;
  }

  function renderNotes(workspace) {
    const rows = workspace.requirement_notes || [];
    return `
      <section class="panel">
        <div class="panel-title">
          <h3>补充需求</h3>
          <span class="muted-text">${rows.length} 条</span>
        </div>
        <div class="panel-body">
          ${
            rows.length
              ? rows.map((item) => `
                  <div class="case-generation-card">
                    <div class="case-generation-card-head">
                      <strong>#${item.id}</strong>
                      ${isAdmin() ? `<div class="actions"><button class="btn secondary" data-cg-note-edit="${item.id}">编辑</button><button class="btn danger" data-cg-note-delete="${item.id}">删除</button></div>` : ""}
                    </div>
                    <pre class="mini-log">${escapeHtml(item.note_text || "")}</pre>
                  </div>
                `).join("")
              : `<div class="empty">可手工补充截图里看不出来的规则</div>`
          }
        </div>
      </section>
    `;
  }

  function renderStats(workspace) {
    const stats = workspace.stats || {};
    return `
      <section class="panel">
        <div class="panel-title"><h3>执行状态</h3></div>
        <div class="panel-body">
          <div class="case-generation-meta">
            <span>总数 ${stats.total || 0}</span>
            <span>未测试 ${stats.untested || 0}</span>
            <span>通过 ${stats.passed || 0}</span>
            <span>失败 ${stats.failed || 0}</span>
            <span>阻塞 ${stats.blocked || 0}</span>
            <span>跳过 ${stats.skipped || 0}</span>
          </div>
        </div>
      </section>
    `;
  }

  function renderCases(workspace) {
    const rows = workspace.cases || [];
    return `
      <section class="panel">
        <div class="panel-title"><h3>生成用例</h3></div>
        <div class="panel-body">
          <div class="case-generation-batch" style="margin-bottom:12px">
            <div class="actions">
              <label class="check-field"><input type="checkbox" id="cgSelectAll" /> <span>全选</span></label>
              <select class="case-generation-select" id="cgBatchStatus">${statusOptions("untested")}</select>
              <button class="btn secondary" id="cgBatchApply" type="button">批量标记</button>
            </div>
          </div>
          ${renderTable(
            [
              { key: "select", label: "", render: (row) => `<input class="case-cb cg-case-check" type="checkbox" value="${row.id}" />` },
              { key: "title", label: "标题", render: (row) => `${escapeHtml(row.title)}${row.source_missing ? `<div class="case-generation-source-missing">来源已删除</div>` : ""}` },
              { key: "steps", label: "步骤", render: (row) => escapeHtml(short(row.steps || "-", 160)) },
              { key: "expected", label: "预期", render: (row) => escapeHtml(short(row.expected || "-", 120)) },
              { key: "priority", label: "优先级", render: (row) => escapeHtml(row.priority || "P1") },
              { key: "source", label: "来源", render: (row) => escapeHtml(sourceLabel(row)) },
              { key: "test_result", label: "执行状态", render: (row) => `<select class="case-generation-select" data-cg-case-status="${row.id}">${statusOptions(row.test_result)}</select>` },
              { key: "remark", label: "备注", render: (row) => escapeHtml(short(row.remark || "-", 80)) },
              {
                key: "actions",
                label: "操作",
                render: (row) => `<div class="actions"><button class="btn secondary" data-cg-case-detail="${row.id}">详情</button>${isAdmin() ? `<button class="btn secondary" data-cg-case-edit="${row.id}">编辑</button><button class="btn danger" data-cg-case-delete="${row.id}">删除</button>` : ""}</div>`,
              },
            ],
            rows,
            false,
          )}
        </div>
      </section>
    `;
  }

  function bindCaseGenerationActions(workspace, projectId) {
    document.querySelector("#uploadCgScreenshots")?.addEventListener("click", () => openScreenshotUpload(projectId));
    document.querySelector("#addCgNote")?.addEventListener("click", () => openNoteForm(projectId));
    document.querySelector("#generateCgCases")?.addEventListener("click", () => generateCases(projectId));
    if (!workspace) return;

    document.querySelector("#cgSelectAll")?.addEventListener("change", (event) => {
      document.querySelectorAll(".cg-case-check").forEach((input) => {
        input.checked = event.target.checked;
      });
    });
    document.querySelector("#cgBatchApply")?.addEventListener("click", () => batchStatus(projectId));
    document.querySelectorAll("[data-cg-case-status]").forEach((select) => {
      select.addEventListener("change", () => updateCaseStatus(select.dataset.cgCaseStatus, select.value));
    });
    document.querySelectorAll("[data-cg-shot-view]").forEach((button) => {
      button.addEventListener("click", () => openProtectedFile(`/api/case-generation/screenshots/${button.dataset.cgShotView}/file`));
    });
    document.querySelectorAll("[data-cg-shot-analyze]").forEach((button) => {
      button.addEventListener("click", () => analyzeScreenshot(button.dataset.cgShotAnalyze));
    });
    document.querySelectorAll("[data-cg-shot-delete]").forEach((button) => {
      button.addEventListener("click", () => openDeleteScreenshot(button.dataset.cgShotDelete));
    });
    document.querySelectorAll("[data-cg-ocr-save]").forEach((button) => {
      button.addEventListener("click", () => saveOcrText(button.dataset.cgOcrSave));
    });
    document.querySelectorAll("[data-cg-note-edit]").forEach((button) => {
      const item = (workspace.requirement_notes || []).find((row) => row.id === Number(button.dataset.cgNoteEdit));
      button.addEventListener("click", () => openNoteForm(projectId, item));
    });
    document.querySelectorAll("[data-cg-note-delete]").forEach((button) => {
      button.addEventListener("click", () => deleteItem(`/api/case-generation/requirement-notes/${button.dataset.cgNoteDelete}`, renderCaseGeneration));
    });
    document.querySelectorAll("[data-cg-case-detail]").forEach((button) => {
      const item = (workspace.cases || []).find((row) => row.id === Number(button.dataset.cgCaseDetail));
      button.addEventListener("click", () => showCaseDetail(item));
    });
    document.querySelectorAll("[data-cg-case-edit]").forEach((button) => {
      const item = (workspace.cases || []).find((row) => row.id === Number(button.dataset.cgCaseEdit));
      button.addEventListener("click", () => openCaseForm(item));
    });
    document.querySelectorAll("[data-cg-case-delete]").forEach((button) => {
      button.addEventListener("click", () => deleteItem(`/api/case-generation/cases/${button.dataset.cgCaseDelete}`, renderCaseGeneration));
    });
  }

  function openScreenshotUpload(projectId) {
    let pending = [];
    const renderPending = () => {
      const list = document.querySelector("#cgUploadList");
      if (!list) return;
      list.innerHTML = pending.length
        ? pending.map((file, index) => `<div><span>${escapeHtml(file.name)}</span><strong>${Math.ceil(file.size / 1024)} KB</strong><button class="btn secondary" type="button" data-remove-upload="${index}">移除</button></div>`).join("")
        : `<div><span>还没有选择截图</span></div>`;
      list.querySelectorAll("[data-remove-upload]").forEach((button) => {
        button.addEventListener("click", () => {
          pending.splice(Number(button.dataset.removeUpload), 1);
          renderPending();
        });
      });
    };
    const addFiles = (files) => {
      Array.from(files || []).forEach((file) => {
        if (file.type && !file.type.startsWith("image/")) return;
        pending.push(file);
      });
      renderPending();
    };

    modalEl.innerHTML = `
      <form id="cgUploadForm">
        <div class="modal-head"><h3>上传截图</h3><button class="btn secondary" type="button" id="closeModal">关闭</button></div>
        <div class="modal-body">
          <div class="case-generation-upload-zone" id="cgUploadZone" tabindex="0">
            <strong>选择、拖拽或 Ctrl+V 粘贴截图</strong>
            <span>可一次上传多张，上传前可移除</span>
            <input id="cgUploadInput" type="file" accept="image/*" multiple hidden />
          </div>
          <div class="case-generation-upload-list" id="cgUploadList"></div>
        </div>
        <div class="modal-foot"><span></span><button class="btn" type="submit">上传</button></div>
      </form>
    `;
    modalEl.showModal();
    renderPending();

    const zone = document.querySelector("#cgUploadZone");
    const input = document.querySelector("#cgUploadInput");
    const close = () => {
      modalEl.removeEventListener("paste", pasteHandler);
      modalEl.close();
    };
    const pasteHandler = (event) => addFiles(Array.from(event.clipboardData?.files || []));
    document.querySelector("#closeModal").addEventListener("click", close);
    modalEl.addEventListener("paste", pasteHandler);
    zone.addEventListener("click", () => input.click());
    input.addEventListener("change", (event) => addFiles(event.target.files));
    zone.addEventListener("dragover", (event) => {
      event.preventDefault();
      zone.classList.add("drag-over");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      zone.classList.remove("drag-over");
      addFiles(event.dataTransfer.files);
    });
    document.querySelector("#cgUploadForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!pending.length) {
        showToast("请先选择截图");
        return;
      }
      const form = new FormData();
      pending.forEach((file) => form.append("files", file));
      try {
        const response = await fetch(`/api/case-generation/workspace/upload-screenshots${queryString({ project_id: projectId })}`, {
          method: "POST",
          headers: { Authorization: `Bearer ${state.token}` },
          body: form,
        });
        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          throw new Error(err.detail || "上传失败");
        }
        showToast("截图已上传");
        modalEl.removeEventListener("paste", pasteHandler);
        modalEl.close();
        await renderCaseGeneration();
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  function openNoteForm(projectId, item = null) {
    openForm(
      item ? "编辑补充需求" : "补充需求",
      [{ name: "note_text", label: "需求内容", type: "textarea", rows: 8, required: true }],
      item || {},
      async (data) => {
        const path = item
          ? `/api/case-generation/requirement-notes/${item.id}`
          : `/api/case-generation/workspace/requirement-notes${queryString({ project_id: projectId })}`;
        await api(path, { method: item ? "PUT" : "POST", body: data });
        showToast("补充需求已保存");
        await renderCaseGeneration();
      },
    );
  }

  async function generateCases(projectId) {
    try {
      showToast("正在生成用例");
      const result = await api(`/api/case-generation/workspace/generate-cases${queryString({ project_id: projectId })}`, { method: "POST" });
      showToast(result.warning || `已生成 ${result.created || 0} 条用例`);
      await renderCaseGeneration();
    } catch (error) {
      showToast(error.message);
    }
  }

  async function analyzeScreenshot(screenshotId) {
    try {
      showToast("正在识别截图，首次加载 OCR 可能较慢");
      await api(`/api/case-generation/screenshots/${screenshotId}/analyze`, { method: "POST" });
      showToast("截图识别完成，请检查校对区");
      await renderCaseGeneration();
    } catch (error) {
      showToast(error.message);
    }
  }

  async function saveOcrText(screenshotId) {
    const text = document.querySelector(`[data-cg-ocr-text="${screenshotId}"]`)?.value || "";
    try {
      await api(`/api/case-generation/screenshots/${screenshotId}/ocr-text`, { method: "PUT", body: { corrected_text: text } });
      showToast("OCR 校对已保存");
      await renderCaseGeneration();
    } catch (error) {
      showToast(error.message);
    }
  }

  async function openDeleteScreenshot(screenshotId) {
    try {
      const impact = await api(`/api/case-generation/screenshots/${screenshotId}/impact`);
      modalEl.innerHTML = `
        <div class="modal-head"><h3>删除截图 #${escapeHtml(screenshotId)}</h3><button class="btn secondary" id="closeModal" type="button">关闭</button></div>
        <div class="modal-body">
          <p>这张截图关联 ${escapeHtml(impact.total || 0)} 条用例，其中可联动删除 ${escapeHtml(impact.deletable || 0)} 条，已测试或手工编辑保留 ${escapeHtml(impact.protected || 0)} 条。</p>
          <p class="muted-text">不联动删除时，只删除截图，并把关联用例标记为来源缺失。</p>
        </div>
        <div class="modal-foot">
          <button class="btn secondary" id="deleteShotOnly" type="button">仅删除截图</button>
          <button class="btn danger" id="deleteShotAndCases" type="button">联动删除用例</button>
        </div>
      `;
      modalEl.showModal();
      document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
      document.querySelector("#deleteShotOnly").addEventListener("click", () => deleteScreenshot(screenshotId, false));
      document.querySelector("#deleteShotAndCases").addEventListener("click", () => deleteScreenshot(screenshotId, true));
    } catch (error) {
      showToast(error.message);
    }
  }

  async function deleteScreenshot(screenshotId, deleteCases) {
    try {
      await api(`/api/case-generation/screenshots/${screenshotId}${queryString({ delete_cases: deleteCases })}`, { method: "DELETE" });
      showToast(deleteCases ? "截图和关联未保护用例已删除" : "截图已删除，关联用例已标记来源缺失");
      modalEl.close();
      await renderCaseGeneration();
    } catch (error) {
      showToast(error.message);
    }
  }

  function openCaseForm(item) {
    openForm(
      "编辑执行用例",
      [
        { name: "title", label: "标题", required: true },
        { name: "precondition", label: "前置条件", type: "textarea", rows: 3 },
        { name: "steps", label: "测试步骤", type: "textarea", rows: 6 },
        { name: "expected", label: "预期结果", type: "textarea", rows: 4 },
        { name: "priority", label: "优先级", type: "select", options: ["P0", "P1", "P2"].map((value) => ({ value, label: value })) },
        { name: "remark", label: "备注", type: "textarea", rows: 3 },
      ],
      item,
      async (data) => {
        await api(`/api/case-generation/cases/${item.id}`, { method: "PUT", body: data });
        showToast("用例已保存");
        await renderCaseGeneration();
      },
    );
  }

  function showCaseDetail(item) {
    if (!item) return;
    modalEl.innerHTML = `
      <div class="modal-head"><h3>${escapeHtml(item.title)}</h3><button class="btn secondary" id="closeModal" type="button">关闭</button></div>
      <div class="modal-body">
        <div class="case-generation-meta">
          <span>优先级：${escapeHtml(item.priority || "P1")}</span>
          <span>来源：${escapeHtml(sourceLabel(item))}</span>
          <span>状态：${resultBadge(item.test_result)}</span>
        </div>
        <h4>前置条件</h4><pre class="mini-log">${escapeHtml(item.precondition || "-")}</pre>
        <h4>测试步骤</h4><pre class="mini-log">${escapeHtml(item.steps || "-")}</pre>
        <h4>预期结果</h4><pre class="mini-log">${escapeHtml(item.expected || "-")}</pre>
        <h4>备注</h4><pre class="mini-log">${escapeHtml(item.remark || "-")}</pre>
      </div>
    `;
    modalEl.showModal();
    document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
  }

  async function updateCaseStatus(caseId, value) {
    try {
      await api(`/api/case-generation/cases/${caseId}/status`, { method: "PUT", body: { test_result: value } });
      showToast("执行状态已保存");
      await renderCaseGeneration();
    } catch (error) {
      showToast(error.message);
    }
  }

  async function batchStatus(projectId) {
    const caseIds = Array.from(document.querySelectorAll(".cg-case-check:checked")).map((input) => Number(input.value));
    if (!caseIds.length) {
      showToast("请先选择用例");
      return;
    }
    try {
      await api(`/api/case-generation/workspace/cases/batch-status${queryString({ project_id: projectId })}`, {
        method: "POST",
        body: { case_ids: caseIds, test_result: document.querySelector("#cgBatchStatus").value },
      });
      showToast("批量状态已保存");
      await renderCaseGeneration();
    } catch (error) {
      showToast(error.message);
    }
  }

  initCaseGenerationState();
  window.renderCaseGeneration = renderCaseGeneration;
  if (typeof state !== "undefined" && state.view === "caseGeneration" && typeof renderShell === "function") {
    renderShell();
  }
})();
