(function () {
  "use strict";

  let options = null;

  function formPayload(form) {
    const data = new FormData(form);
    return {
      provider: String(data.get("provider") || "openai_compatible").trim(),
      base_url: String(data.get("base_url") || "").trim(),
      model: String(data.get("model") || "").trim(),
      api_key: String(data.get("api_key") || "").trim(),
    };
  }

  async function withBusyButton(button, text, action) {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = text;
    try {
      return await action();
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  async function openGlobalAiConfig() {
    if (!options?.isAdmin) return;
    const config = await options.api("/api/ai-config");
    const { modalEl, escapeHtml } = options;
    modalEl.removeAttribute("data-data-agent-session-id");
    modalEl.innerHTML = `
      <form id="globalAiConfigForm">
        <div class="modal-head">
          <h3>全局 AI 配置</h3>
          <button class="btn secondary" id="closeGlobalAiConfig" type="button">关闭</button>
        </div>
        <div class="modal-body">
          <div class="notice warn">修改后会影响全平台后续 AI 任务；正在运行的任务继续使用启动时的配置。</div>
          <div class="form-grid">
            <div class="field"><label>服务类型</label><select name="provider">
              <option value="openai_compatible" ${config.provider === "openai_compatible" ? "selected" : ""}>OpenAI 兼容</option>
              <option value="ollama" ${config.provider === "ollama" ? "selected" : ""}>Ollama</option>
            </select></div>
            <div class="field"><label>API 地址</label><input name="base_url" value="${escapeHtml(config.base_url || "")}" required /></div>
            <div class="field"><label>模型名称</label><input name="model" value="${escapeHtml(config.model || "")}" required /></div>
            <div class="field"><label>API Key</label><input name="api_key" type="password" autocomplete="new-password" placeholder="留空则保留现有密钥" /></div>
          </div>
          <p class="muted">当前模型：<strong id="globalAiCurrentModel">${escapeHtml(config.model || "未配置")}</strong></p>
          <p id="globalAiConnectionResult" class="muted" aria-live="polite"></p>
        </div>
        <div class="modal-foot">
          <button class="btn secondary" id="testGlobalAiConfig" type="button">测试连接</button>
          <button class="btn" type="submit">保存配置</button>
        </div>
      </form>`;
    if (!modalEl.open) modalEl.showModal();

    const form = modalEl.querySelector("#globalAiConfigForm");
    const result = modalEl.querySelector("#globalAiConnectionResult");
    modalEl.querySelector("#closeGlobalAiConfig").onclick = () => modalEl.close();
    modalEl.querySelector("#testGlobalAiConfig").onclick = async (event) => {
      result.textContent = "";
      try {
        await withBusyButton(event.currentTarget, "正在测试...", async () => {
          const response = await options.api("/api/ai-config/test", {
            method: "POST",
            body: formPayload(form),
          });
          result.textContent = `${response.message}，模型：${response.model}`;
        });
      } catch (error) {
        result.textContent = error.message || "连接测试失败";
      }
    };
    form.onsubmit = async (event) => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      await withBusyButton(button, "正在保存...", async () => {
        const saved = await options.api("/api/ai-config", {
          method: "PUT",
          body: formPayload(form),
        });
        options.showToast("全局 AI 配置已保存");
        updateButtonModel(saved.model);
        modalEl.close();
      });
    };
  }

  function updateButtonModel(model) {
    const button = document.querySelector("#globalAiConfigBtn");
    if (!button) return;
    button.textContent = model ? `全局 AI 配置 · ${model}` : "全局 AI 配置";
    button.title = "修改后影响全平台后续 AI 任务";
  }

  function mount(config) {
    options = config;
    const button = document.querySelector("#globalAiConfigBtn");
    if (!button || !config?.isAdmin) return;
    button.onclick = openGlobalAiConfig;
    config.api("/api/ai-config")
      .then((current) => updateButtonModel(current?.model || ""))
      .catch(() => updateButtonModel(""));
  }

  window.GlobalAiConfig = { mount, open: openGlobalAiConfig };
})();
