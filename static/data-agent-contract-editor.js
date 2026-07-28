(function () {
  "use strict";

  const drafts = new Map();
  const inferredValues = new Map();
  let activeSessionKey = "";

  function valueText(value) {
    if (Array.isArray(value)) return value.join(",");
    if (value && typeof value === "object") return JSON.stringify(value);
    return value ?? "";
  }

  function renderRestore(field, escapeHtml) {
    if (!field.restore_inferred || field.readonly) return "";
    return `<button class="btn secondary" type="button" data-restore-field="${escapeHtml(field.name)}">恢复推断值</button>`;
  }

  function renderField(field, escapeHtml) {
    const value = drafts.has(field.name) ? drafts.get(field.name) : field.value;
    const inferred = field.inferred ? '<span class="tag warning">推断项</span>' : "";
    const source = field.source ? `<small>来源：${escapeHtml(field.source)}</small>` : "";
    const attrs = `data-contract-field="${escapeHtml(field.name)}" ${field.readonly ? "disabled" : ""} ${field.required ? "required" : ""}`;
    const restore = renderRestore(field, escapeHtml);
    if (field.editor === "select") {
      const choices = (field.choices || []).map((item) => `<option value="${escapeHtml(item.value)}" ${String(item.value) === String(value) ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("");
      return `<div class="field"><label>${escapeHtml(field.label)}${inferred}<select ${attrs}>${choices}</select>${source}${restore}<span class="danger-text" data-field-error="${escapeHtml(field.name)}"></span></label></div>`;
    }
    if (field.editor === "checkbox") {
      return `<div class="field"><label>${escapeHtml(field.label)}${inferred}<input type="checkbox" ${attrs} ${value === true ? "checked" : ""} />${source}${restore}<span class="danger-text" data-field-error="${escapeHtml(field.name)}"></span></label></div>`;
    }
    const type = field.editor === "number" || field.editor === "decimal" ? "number" : "text";
    const step = field.editor === "decimal" ? 'step="any"' : "";
    return `<div class="field"><label>${escapeHtml(field.label)}${inferred}<input type="${type}" ${step} ${attrs} value="${escapeHtml(valueText(value))}" />${source}${restore}<span class="danger-text" data-field-error="${escapeHtml(field.name)}"></span></label></div>`;
  }

  function render(session, options) {
    const escapeHtml = options.escapeHtml;
    const sessionKey = `${session.id || ""}:${session.plan_version || ""}`;
    if (activeSessionKey && activeSessionKey !== sessionKey) drafts.clear();
    activeSessionKey = sessionKey;
    inferredValues.clear();
    const fields = session.contract_editor.fields || [];
    fields.forEach((field) => {
      if (field.restore_inferred) inferredValues.set(field.name, field.restore_value);
    });
    const groups = (session.contract_editor.groups || []).map((group) => {
      const controls = fields.filter((field) => field.group === group.key).map((field) => renderField(field, escapeHtml)).join("");
      if (!controls) return "";
      return `<details open data-contract-group="${escapeHtml(group.key)}"><summary>${escapeHtml(group.label)}</summary><div class="form-grid">${controls}</div></details>`;
    }).join("");
    const canEdit = ["awaiting_confirmation", "clarifying"].includes(session.status);
    return `<section class="panel" data-contract-editor>
      <div class="panel-title"><h3>目标合同</h3><span>版本 v${escapeHtml(session.plan_version || 1)}</span></div>
      <div class="panel-body">
        <form data-contract-save-form>${groups}<div class="actions"><button class="btn" type="submit" ${canEdit ? "" : "disabled"}>保存修改</button></div></form>
        <form data-contract-correction-form style="margin-top:12px"><div class="field"><label>自然语言修正<textarea name="message" rows="2" required placeholder="说明需要修改的合同字段"></textarea></label></div><div class="actions"><button class="btn secondary" type="submit" ${canEdit ? "" : "disabled"}>重新生成合同</button></div></form>
        <div data-contract-preview></div>
        <div class="actions" style="margin-top:12px"><button class="btn secondary" type="button" data-contract-correct ${canEdit ? "" : "disabled"}>合同正确</button><button class="btn" type="button" data-contract-confirm ${session.can_confirm ? "" : "disabled"}>确认并执行</button></div>
      </div>
    </section>`;
  }

  function readControl(control, field) {
    if (control.type === "checkbox") return control.checked;
    const raw = control.value;
    if (raw === "") return "";
    if (field.value_type === "list[str]") return raw.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean);
    return raw;
  }

  function normalizedNumericText(value, allowDecimal) {
    const text = String(value).trim();
    if (!text) return text;
    const pattern = allowDecimal
      ? /^([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))$/
      : /^([+-]?)(\d+)$/;
    const match = text.match(pattern);
    if (!match) return text;
    const sign = match[1] === "-" ? "-" : "";
    let integer = match[2] ?? "0";
    let fraction = allowDecimal ? (match[3] ?? match[4] ?? "") : "";
    integer = integer.replace(/^0+(?=\d)/, "");
    fraction = fraction.replace(/0+$/, "");
    const unsigned = fraction ? `${integer}.${fraction}` : integer;
    return unsigned === "0" ? "0" : `${sign}${unsigned}`;
  }

  function comparableValue(value, field) {
    if (value === null || value === undefined) return null;
    if (value === "") return "";
    if (field.value_type === "int") return normalizedNumericText(value, false);
    if (field.value_type === "decimal") return normalizedNumericText(value, true);
    if (field.value_type === "list[str]") {
      const items = Array.isArray(value) ? value : String(value).split(/[，,\n]/);
      return items.map((item) => String(item).trim()).filter(Boolean);
    }
    if (["str", "string", "node"].includes(field.value_type)) return String(value).trim();
    return value;
  }

  function fieldChanged(value, field) {
    const before = comparableValue(field.value, field);
    const after = comparableValue(value, field);
    if (before === null && after === "") return false;
    return JSON.stringify(before) !== JSON.stringify(after);
  }

  function collectFields(container, session) {
    const schema = new Map((session.contract_editor.fields || []).map((field) => [field.name, field]));
    const values = {};
    const changes = {};
    container.querySelectorAll("[data-contract-field]").forEach((control) => {
      const field = schema.get(control.dataset.contractField);
      if (!field || field.readonly) return;
      values[field.name] = readControl(control, field);
      if (fieldChanged(values[field.name], field)) changes[field.name] = values[field.name];
    });
    return { values, changes };
  }

  function replaceDrafts(values) {
    drafts.clear();
    Object.entries(values).forEach(([name, value]) => drafts.set(name, value));
  }

  function errorDetail(error) {
    let detail = error?.detail || error?.data?.detail || error?.response?.detail;
    if (!detail && error?.message) {
      try { detail = JSON.parse(error.message); } catch { detail = null; }
    }
    return detail && typeof detail === "object" ? detail : {};
  }

  function applyFieldErrors(container, error) {
    container.querySelectorAll("[data-field-error]").forEach((element) => { element.textContent = ""; });
    const fields = errorDetail(error).fields || {};
    Object.entries(fields).forEach(([name, message]) => {
      const target = [...container.querySelectorAll("[data-field-error]")].find((element) => element.dataset.fieldError === name);
      if (target) target.textContent = String(message || "");
    });
  }

  function setEditorBusy(container, busy) {
    container.querySelectorAll("[data-contract-field], button").forEach((element) => {
      if (busy) {
        element._contractWasDisabled = Boolean(element.disabled);
        element.disabled = true;
      } else if (Object.prototype.hasOwnProperty.call(element, "_contractWasDisabled")) {
        element.disabled = element._contractWasDisabled;
        delete element._contractWasDisabled;
      }
    });
  }

  function displayValue(value) {
    if (value === null || value === undefined || value === "") return "空";
    return typeof value === "object" ? JSON.stringify(value) : String(value);
  }

  function renderPreview(container, preview, session, options) {
    const escapeHtml = options.escapeHtml;
    const labels = new Map((session.contract_editor.fields || []).map((field) => [field.name, field.label]));
    const rows = (preview.diff || []).map((item) => `<tr><td>${escapeHtml(labels.get(item.field) || item.field)}</td><td>${escapeHtml(displayValue(item.before))}</td><td>${escapeHtml(displayValue(item.after))}</td><td>${escapeHtml(item.source || "natural_language_correction")}</td></tr>`).join("");
    container.innerHTML = `<div class="panel" style="margin-top:12px"><div class="panel-title"><h3>合同修正预览</h3></div><div class="panel-body"><div class="table-wrap"><table><thead><tr><th>执行字段</th><th>修改前</th><th>修改后</th><th>来源</th></tr></thead><tbody>${rows}</tbody></table></div><div class="actions" style="margin-top:12px"><button class="btn" type="button" data-apply-contract-preview="${escapeHtml(preview.preview_hash)}">应用修正</button></div></div></div>`;
    container.querySelector("[data-apply-contract-preview]")?.addEventListener("click", async (event) => {
      const savedDrafts = Object.fromEntries(drafts);
      const button = event.currentTarget;
      button.disabled = true;
      try {
        await options.applyPreview(preview.preview_hash, session.plan_version);
      } catch (error) {
        replaceDrafts(savedDrafts);
        button.disabled = false;
      }
    });
  }

  function bind(container, session, options) {
    if (!container || !session?.contract_editor) return;
    const editor = container.querySelector("[data-contract-editor]");
    const bindKey = `${session.id || ""}:${session.plan_version || ""}`;
    if (!editor || editor.dataset.contractBindKey === bindKey) return;
    editor.dataset.contractBindKey = bindKey;
    const saveForm = container.querySelector("[data-contract-save-form]");
    let saveFlight = null;

    function saveDirtyFields() {
      if (saveFlight) return saveFlight;
      const { values, changes } = collectFields(container, session);
      replaceDrafts(values);
      const savedDrafts = { ...values };
      if (!Object.keys(changes).length) {
        Object.keys(values).forEach((name) => drafts.delete(name));
        return Promise.resolve({ plan_version: session.plan_version });
      }
      setEditorBusy(container, true);
      const request = Promise.resolve().then(() => options.save(changes, session.plan_version));
      saveFlight = request.then((savedSession) => {
        Object.keys(values).forEach((name) => drafts.delete(name));
        return savedSession;
      }).catch((error) => {
        replaceDrafts(savedDrafts);
        applyFieldErrors(container, error);
        throw error;
      }).finally(() => {
        setEditorBusy(container, false);
        saveFlight = null;
      });
      return saveFlight;
    }

    saveForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await saveDirtyFields();
      } catch {}
    });

    container.querySelectorAll("[data-restore-field]").forEach((button) => {
      button.addEventListener("click", () => {
        const name = button.dataset.restoreField;
        const control = [...container.querySelectorAll("[data-contract-field]")].find((item) => item.dataset.contractField === name);
        const value = inferredValues.get(name);
        if (!control) return;
        if (control.type === "checkbox") control.checked = value === true;
        else control.value = valueText(value);
        drafts.set(name, value);
        const error = [...container.querySelectorAll("[data-field-error]")].find((item) => item.dataset.fieldError === name);
        if (error) error.textContent = "";
      });
    });

    const correctionForm = container.querySelector("[data-contract-correction-form]");
    correctionForm?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = new FormData(correctionForm).get("message");
      const previewContainer = container.querySelector("[data-contract-preview]");
      const button = correctionForm.querySelector('button[type="submit"]');
      button.disabled = true;
      try {
        const preview = await options.previewCorrection(message, session.plan_version);
        renderPreview(previewContainer, preview, session, options);
      } catch {
        previewContainer.innerHTML = "";
      } finally {
        button.disabled = false;
      }
    });

    container.querySelector("[data-contract-correct]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const savedSession = await saveDirtyFields();
        await options.markCorrect(savedSession?.plan_version ?? session.plan_version);
      } catch {
        button.disabled = false;
      }
    });
    container.querySelector("[data-contract-confirm]")?.addEventListener("click", async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const savedSession = await saveDirtyFields();
        await options.confirm(savedSession?.plan_version ?? session.plan_version);
      } catch {
        button.disabled = false;
      }
    });
  }

  window.DataAgentContractEditor = { render, bind };
})();
