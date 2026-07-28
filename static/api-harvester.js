/**
 * 接口抓取页面:真跑网站抓接口 + AI 分析 + 入库用例库。
 * 独立 JS,不堆进 app.js。依赖 app.js 提供的 api/contentEl/showToast/badge/renderTable/isAdmin。
 */
(function () {
  "use strict";

  let currentTaskId = null;
  let pollTimer = null;
  let lastCrawlResult = null;

  async function render() {
    const el = contentEl();
    const adminNote = isAdmin()
      ? ""
      : "<p style='color:var(--danger)'>抓取和分析需管理员权限,当前账号无权限</p>";
    el.innerHTML = `
      <div class="toolbar"><p>启动浏览器自动登录前后台,遍历页面抓取所有接口,AI 分析接口用途并给出造数脚本建议,同时把接口补到接口用例库。</p></div>
      ${adminNote}
      <div class="panel">
        <div class="panel-title"><h3>抓取配置</h3></div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
          <div>
            <h4>前台(用户端)</h4>
            <label>网址</label>
            <input id="crawlFrontUrl" class="input" value="https://jpweb.rakumart.cn/" placeholder="https://...">
            <label>账号</label>
            <input id="crawlFrontAccount" class="input" value="12345678990" placeholder="前台账号">
            <label>密码</label>
            <input id="crawlFrontPassword" class="input" type="password" value="123456" placeholder="前台密码">
          </div>
          <div>
            <h4>后台(管理端)</h4>
            <label>网址</label>
            <input id="crawlBackUrl" class="input" value="https://jpmanage.rakumart.cn" placeholder="https://...">
            <label>账号</label>
            <input id="crawlBackAccount" class="input" value="Y001" placeholder="后台账号">
            <label>密码</label>
            <input id="crawlBackPassword" class="input" type="password" value="xiaolin666@" placeholder="后台密码">
          </div>
        </div>
        <div class="actions" style="margin-top:16px;gap:8px;display:flex">
          <button class="btn" id="crawlBtn" type="button" ${isAdmin() ? "" : "disabled"}>1. 启动浏览器抓取接口</button>
          <button class="btn" id="analyzeBtn" type="button" disabled>2. AI 分析 + 入库</button>
          <span id="crawlStatus" style="color:var(--text-muted);align-self:center"></span>
        </div>
      </div>
      <div id="crawlProgress"></div>
      <div id="crawlEndpoints"></div>
      <div id="analyzeResult"></div>
    `;

    document.querySelector("#crawlBtn").addEventListener("click", startCrawl);
    document.querySelector("#analyzeBtn").addEventListener("click", startAnalyze);
  }

  async function startCrawl() {
    if (!isAdmin()) return;
    const btn = document.querySelector("#crawlBtn");
    btn.disabled = true;
    btn.textContent = "抓取中...";
    document.querySelector("#crawlStatus").textContent = "正在启动浏览器...";
    document.querySelector("#crawlProgress").innerHTML = "";
    document.querySelector("#crawlEndpoints").innerHTML = "";
    document.querySelector("#analyzeResult").innerHTML = "";
    document.querySelector("#analyzeBtn").disabled = true;

    const payload = {
      front_url: val("#crawlFrontUrl"),
      front_account: val("#crawlFrontAccount"),
      front_password: val("#crawlFrontPassword"),
      back_url: val("#crawlBackUrl"),
      back_account: val("#crawlBackAccount"),
      back_password: val("#crawlBackPassword"),
    };

    try {
      const res = await api("/api/api-harvester/crawl", { method: "POST", body: payload });
      currentTaskId = res.task_id;
      document.querySelector("#crawlStatus").textContent = "浏览器已启动,正在遍历页面...";
      pollTaskStatus();
    } catch (error) {
      showToast(error.message);
      btn.disabled = false;
      btn.textContent = "1. 启动浏览器抓取接口";
    }
  }

  function pollTaskStatus() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      if (!currentTaskId) return;
      try {
        const task = await api(`/api/api-harvester/task/${currentTaskId}`);
        if (task.status === "running") {
          document.querySelector("#crawlStatus").textContent = "浏览器运行中,正在遍历页面抓接口...";
        } else if (task.status === "done") {
          clearInterval(pollTimer);
          pollTimer = null;
          lastCrawlResult = task.result;
          document.querySelector("#crawlStatus").textContent = "抓取完成";
          document.querySelector("#crawlBtn").disabled = false;
          document.querySelector("#crawlBtn").textContent = "1. 启动浏览器抓取接口";
          renderCrawlResult(task.result);
          document.querySelector("#analyzeBtn").disabled = false;
          showToast(`抓取完成:${task.result.stats.endpoint_count} 个接口`);
        } else if (task.status === "failed") {
          clearInterval(pollTimer);
          pollTimer = null;
          document.querySelector("#crawlStatus").textContent = "抓取失败";
          document.querySelector("#crawlBtn").disabled = false;
          document.querySelector("#crawlBtn").textContent = "1. 启动浏览器抓取接口";
          showToast(`抓取失败:${task.error}`);
        }
      } catch (error) {
        clearInterval(pollTimer);
        pollTimer = null;
        showToast(error.message);
      }
    }, 3000);
  }

  function renderCrawlResult(result) {
    const { front_pages, back_pages, endpoints, stats } = result;
    const pagesHtml = `
      <div class="panel-title"><h3>遍历页面 (${stats.page_count})</h3></div>
      <details>
        <summary>前台页面 (${front_pages.length})</summary>
        ${renderPagesTable(front_pages)}
      </details>
      <details>
        <summary>后台页面 (${back_pages.length})</summary>
        ${renderPagesTable(back_pages)}
      </details>
    `;
    const endpointsHtml = `
      <div class="panel-title"><h3>抓取到的接口 (${stats.endpoint_count})</h3></div>
      ${renderTable(
        [
          { key: "source", label: "来源", render: (r) => badge(r.source === "front" ? "前台" : "后台") },
          { key: "method", label: "方法", render: (r) => badge(r.method) },
          { key: "path", label: "路径" },
          { key: "response_status", label: "状态码", render: (r) => r.response_status || "-" },
        ],
        endpoints,
      )}
    `;
    document.querySelector("#crawlProgress").innerHTML = pagesHtml;
    document.querySelector("#crawlEndpoints").innerHTML = endpointsHtml;
  }

  function renderPagesTable(pages) {
    if (!pages || !pages.length) return "<p>无</p>";
    return renderTable(
      [
        { key: "url", label: "URL" },
        { key: "title", label: "标题" },
        { key: "error", label: "错误", render: (r) => (r.error ? `<span style="color:var(--danger)">${escapeHtml(r.error)}</span>` : "-") },
      ],
      pages,
    );
  }

  async function startAnalyze() {
    if (!isAdmin() || !lastCrawlResult) return;
    const btn = document.querySelector("#analyzeBtn");
    btn.disabled = true;
    btn.textContent = "AI 分析中(约 30-90 秒)...";
    document.querySelector("#analyzeResult").innerHTML = "";
    try {
      const result = await api("/api/api-harvester/analyze", {
        method: "POST",
        body: { endpoints: lastCrawlResult.endpoints },
      });
      renderAnalyzeResult(result);
      if (result.error) {
        showToast(result.error);
      } else {
        showToast(`分析完成,已导入 ${result.imported_count} 条用例到接口用例库`);
      }
    } catch (error) {
      showToast(error.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "2. AI 分析 + 入库";
    }
  }

  function renderAnalyzeResult(result) {
    const analysis = result.analysis || {};
    const epAnalysis = analysis.endpoints || [];
    const suggestions = analysis.script_suggestions || [];
    const importedCount = result.imported_count || 0;

    const epHtml = epAnalysis.length
      ? renderTable(
          [
            { key: "method", label: "方法", render: (r) => badge(r.method) },
            { key: "path", label: "路径" },
            { key: "purpose", label: "用途" },
            { key: "category", label: "分类", render: (r) => badge(r.category) },
            { key: "can_use_for_script", label: "可造数", render: (r) => (r.can_use_for_script ? '<span style="color:var(--success)">是</span>' : "否") },
            { key: "script_role", label: "脚本角色" },
          ],
          epAnalysis,
        )
      : "<p>AI 未返回接口分析</p>";

    const sugHtml = suggestions.length
      ? suggestions.map((s, i) => `
          <div class="panel" style="margin-bottom:12px">
            <h4>${i + 1}. ${escapeHtml(s.name || "")}</h4>
            <p style="color:var(--text-muted)">${escapeHtml(s.description || "")}</p>
            <p><strong>关键产出:</strong> ${escapeHtml(s.key_outputs || "无")}</p>
            <h5>流程步骤</h5>
            ${renderTable(
              [
                { key: "step", label: "#", render: (r, idx) => idx + 1 },
                { key: "method", label: "方法", render: (r) => badge(r.method) },
                { key: "path", label: "路径" },
                { key: "purpose", label: "说明" },
              ],
              s.steps || [],
            )}
          </div>
        `).join("")
      : "<p>AI 未给出造数脚本建议</p>";

    document.querySelector("#analyzeResult").innerHTML = `
      <div class="panel-title"><h3>AI 分析结果</h3></div>
      <div class="panel">
        <div class="stats">
          <div class="stat"><span>已导入用例</span><strong>${importedCount}</strong></div>
          <div class="stat"><span>分析接口数</span><strong>${epAnalysis.length}</strong></div>
          <div class="stat"><span>建议脚本数</span><strong>${suggestions.length}</strong></div>
        </div>
        <p style="margin-top:12px">接口已导入到「接口用例库」(状态默认关闭,带 [抓取] 前缀),到用例库查看并启用。</p>
      </div>
      <div class="panel-title"><h3>接口用途分析</h3></div>
      <div class="panel">${epHtml}</div>
      <div class="panel-title"><h3>造数脚本建议计划</h3></div>
      <div>${sugHtml}</div>
    `;
  }

  function val(selector) {
    const el = document.querySelector(selector);
    return el ? el.value.trim() : "";
  }

  window.renderApiHarvester = render;
})();
