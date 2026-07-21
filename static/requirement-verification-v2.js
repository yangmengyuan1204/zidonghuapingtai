(function () {
  const failureLabels = {
    business_mismatch: "业务结果不符合预期",
    auth_error: "登录或权限问题",
    data_invalid: "测试数据不符合前置条件",
    page_not_ready: "页面业务区未准备完成",
    locator_error: "页面字段无法可靠定位",
    ai_error: "AI结果不可靠",
    user_deferred: "暂不判断",
    system_interrupted: "系统或浏览器中断",
    cancelled: "用户取消",
  };
  const phaseLabels = {
    queued: "等待执行",
    preflighting: "真实运行前检查",
    data_preparing: "准备测试数据",
    data_validating: "检查数据前置条件",
    browser_preparing: "恢复浏览器和登录状态",
    running: "执行页面验证",
    waiting_user: "需要我处理",
    paused: "已暂停",
    cancelling: "正在取消",
    cancelled: "已取消",
    passed: "已通过",
    failed: "业务失败",
    blocked: "暂不可执行",
    needs_review: "待人工复核",
  };
  let checkpointPollTimer = null;

  function e(value) {
    return escapeHtml(String(value ?? ""));
  }

  function conditionText(condition) {
    const operators = { eq: "等于", ne: "不等于", lt: "小于", lte: "小于等于", gt: "大于", gte: "大于等于", in: "属于", between: "介于", contains: "包含" };
    const value = Array.isArray(condition.value) ? condition.value.join("、") : condition.value;
    return `${condition.field} ${operators[condition.operator] || condition.operator} ${value ?? ""}${condition.unit ? ` ${condition.unit}` : ""}`;
  }

  function renderSections(task) {
    const memories = (task.memories || []).filter((item) => ["page_checkpoint", "page_readiness", "business_flow", "data_recipe", "state_mapping", "amount_rule"].includes(item.memory_type));
    return `
      <section class="verification-section verification-v2-tools">
        <div class="panel-title"><h3>边测边教与历史复用</h3><div class="actions">
          ${isAdmin() ? '<button class="btn" id="startVerificationLearning">开始边测边教</button><button class="btn secondary" id="inheritVerificationHistory">继承相似功能</button>' : ""}
          <button class="btn secondary" id="verificationEfficiency">效率统计</button>
        </div></div>
        <div class="verification-v2-capabilities">
          <div><strong>${memories.filter((item) => item.status === "confirmed").length}</strong><span>项目已确认规则</span></div>
          <div><strong>${memories.filter((item) => item.status === "verified").length}</strong><span>当前已回放规则</span></div>
          <div><strong>${memories.filter((item) => item.status === "draft").length}</strong><span>待确认草稿</span></div>
        </div>
        <p class="verification-v2-hint">第一次按平时方式测试并点击添加验证点；相似迭代直接继承已确认规则，不再从零配置页面动作。</p>
      </section>`;
  }

  function renderRunWorkspace(task, run) {
    const waiting = run.waiting_user_items || (run.items || []).filter((item) => ["waiting_user", "waiting_confirmation"].includes(item.result));
    const datasets = run.datasets || [];
    const failed = (run.items || []).filter((item) => item.failure_kind);
    const controls = run.available_actions || {};
    return `
      <div class="verification-v2-cockpit">
        <div class="verification-v2-phase"><strong>${e(phaseLabels[run.phase] || run.phase || run.status)}</strong><span>${e(run.progress?.message || "")}</span><small>已用时间按实际记录，系统不承诺不可靠的剩余时间</small></div>
        <div class="actions verification-v2-run-controls">
          ${controls.pause ? `<button class="btn secondary" data-v2-run-action="pause" data-run-id="${run.id}">暂停</button>` : ""}
          ${controls.resume ? `<button class="btn" data-v2-run-action="resume" data-run-id="${run.id}">继续</button>` : ""}
          ${controls.cancel ? `<button class="btn secondary" data-v2-run-action="cancel" data-run-id="${run.id}">取消</button>` : ""}
          ${controls.retry ? `<button class="btn" data-v2-run-retry="current_step" data-run-id="${run.id}">复用原数据复跑</button><button class="btn secondary" data-v2-run-retry="new_data" data-run-id="${run.id}">新数据重新开始</button>` : ""}
        </div>
        ${waiting.length ? `<section class="verification-v2-attention"><div class="panel-title"><h4>需要我处理（${waiting.length}）</h4><button class="btn secondary" data-open-test-browser>打开测试浏览器</button></div>${waiting.map((item) => {
          const pending = item.resume?.pending || item.evidence?.manual_takeover || {};
          const title = (task.items || []).find((row) => row.id === item.item_id)?.title || `验证项 #${item.item_id}`;
          return `<article><strong>${e(title)}</strong><p>${e(pending.message || item.message)}</p><small>系统已完成：数据准备、前置条件检查和当前页面打开</small><span>你只需：${e(pending.type === "login" ? "在测试浏览器完成登录或验证码" : pending.type === "observation_value" ? "点击目标字段或填写页面实际值" : pending.type === "risk" ? "确认风险动作是否允许" : "按业务预期做一次判断")}</span><span>完成后系统会继续：当前验证项及其后续依赖项</span></article>`;
        }).join("")}</section>` : ""}
        ${datasets.length ? `<details class="verification-v2-datasets"><summary>本次测试数据集（${datasets.length}）</summary>${datasets.map((dataset) => `<article><div><strong>${e(dataset.name)}</strong><span>${e(dataset.status)}</span></div><p>${(dataset.conditions || []).length ? dataset.conditions.map(conditionText).map(e).join("；") : "通用数据，无额外业务条件"}</p><small>${dataset.status === "passed" ? (dataset.result?.reused_from_run_id ? `已复用执行 #${dataset.result.reused_from_run_id} 的原订单` : "数据有效性检查通过") : dataset.status === "invalid" ? "数据不符合条件，未执行关联断言" : "等待处理"}</small></article>`).join("")}</details>` : ""}
        ${failed.length ? `<details class="verification-v2-failures" open><summary>执行问题分类（${failed.length}）</summary>${failed.map((item) => `<article><div><strong>${e(failureLabels[item.failure_kind] || item.failure_kind)}</strong><span>${e(item.message)}</span></div>${item.failure_kind === "business_mismatch" ? `<button class="btn secondary" data-v2-defect="${item.id}">生成缺陷草稿</button>` : '<small>这是技术阻塞，不计入功能失败</small>'}</article>`).join("")}</details>` : ""}
      </div>`;
  }

  function pageOptions(task) {
    return (task.target_pages || []).map((page) => `<option value="${e(page.url)}" data-page-name="${e(page.name)}" data-role="${e(page.role)}">${e(page.name || page.url)}${page.role ? `（${e(page.role)}）` : ""}</option>`).join("");
  }

  async function openLearningStart(task) {
    const accounts = await api(`/api/test-accounts?project_id=${encodeURIComponent(task.project_id)}`);
    modalEl.innerHTML = `
      <form id="verificationLearningStartForm">
        <div class="modal-head"><h3>开始边测边教</h3><button class="btn secondary" type="button" id="closeModal">关闭</button></div>
        <div class="modal-body form-grid">
          <div class="field"><label>起始页面</label><select name="start_url" required>${pageOptions(task)}</select></div>
          <div class="field"><label>适用角色</label><input name="role_name" placeholder="买家、运营、审核员" /></div>
          <div class="field"><label>项目账号</label><select name="account_profile_id" required><option value="">请选择</option>${accounts.filter((item) => item.status === "active").map((item) => `<option value="${item.id}">${e(item.profile_name)} · 登录状态 ${e(item.browser_session_status || "未保存")}</option>`).join("")}</select></div>
          <p class="verification-v2-hint">系统会打开可见测试浏览器。你照常测试，密码、验证码、Token、Cookie和手机号不会进入录制事件。</p>
        </div>
        <div class="modal-foot"><span>规则先属于当前功能分类</span><button class="btn" type="submit">打开测试浏览器</button></div>
      </form>`;
    modalEl.showModal();
    document.querySelector("#closeModal").onclick = () => modalEl.close();
    document.querySelector("#verificationLearningStartForm").onsubmit = async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target).entries());
      const selected = event.target.querySelector('[name="start_url"] option:checked');
      data.page_name = selected?.dataset.pageName || "";
      data.role_name = data.role_name || selected?.dataset.role || "";
      data.account_profile_id = Number(data.account_profile_id);
      try {
        const session = await api(`/api/requirement-verifications/${task.id}/learning-sessions`, { method: "POST", body: data });
        localStorage.setItem(`verificationLearningSession:${task.id}`, session.id);
        openLearningWorkspace(task, session);
      } catch (error) {
        showToast(error.message);
      }
    };
  }

  function openLearningWorkspace(task, session) {
    const checkpoints = session.checkpoints || [];
    modalEl.innerHTML = `
      <div id="verificationLearningWorkspace">
        <div class="modal-head"><div><h3>边测边教进行中</h3><small>${e(session.page_name || session.start_url)}</small></div><button class="btn secondary" type="button" id="closeModal">收起</button></div>
        <div class="modal-body">
          <div class="verification-v2-learning-status"><strong>已记录 ${session.event_count || 0} 个业务动作</strong><span>已添加 ${checkpoints.length} 个验证点</span></div>
          <div class="verification-v2-learning-actions"><button class="btn" id="captureVerificationCheckpoint">在浏览器点击目标字段</button><button class="btn secondary" id="refreshVerificationLearning">刷新记录</button></div>
          <div id="verificationLearningInstruction" class="verification-v2-hint">需要验证页面值时，点击上方按钮，再到测试浏览器点击“その他”等目标字段。</div>
          ${checkpoints.length ? checkpoints.map((item) => `<article class="verification-v2-checkpoint"><strong>${e(item.payload?.field_name)}</strong><span>${e(item.payload?.actual_value)}</span><small>${e(item.payload?.relation)}</small></article>`).join("") : '<div class="empty">尚未添加验证点</div>'}
        </div>
        <div class="modal-foot"><button class="btn secondary" id="cancelVerificationLearning">取消本次学习</button><button class="btn" id="saveVerificationLearning">保存规则</button></div>
      </div>`;
    modalEl.showModal();
    document.querySelector("#closeModal").onclick = () => modalEl.close();
    document.querySelector("#refreshVerificationLearning").onclick = async () => openLearningWorkspace(task, await api(`/api/requirement-verifications/learning-sessions/${session.id}`));
    document.querySelector("#captureVerificationCheckpoint").onclick = async () => {
      const beforeId = Math.max(0, ...(session.events || []).map((item) => item.id || 0));
      await api(`/api/requirement-verifications/learning-sessions/${session.id}/capture-checkpoint`, { method: "POST" });
      document.querySelector("#verificationLearningInstruction").textContent = "现在请到测试浏览器，单击你要验证的字段。系统会自动读取字段名、相邻值和定位候选。";
      if (checkpointPollTimer) clearInterval(checkpointPollTimer);
      checkpointPollTimer = setInterval(async () => {
        const latest = await api(`/api/requirement-verifications/learning-sessions/${session.id}`);
        const selected = (latest.events || []).find((item) => item.id > beforeId && item.event_type === "checkpoint_selection");
        if (!selected) return;
        clearInterval(checkpointPollTimer);
        checkpointPollTimer = null;
        openCheckpointConfirm(task, latest, selected.payload || {});
      }, 1000);
    };
    document.querySelector("#cancelVerificationLearning").onclick = async () => {
      await api(`/api/requirement-verifications/learning-sessions/${session.id}/cancel`, { method: "POST" });
      localStorage.removeItem(`verificationLearningSession:${task.id}`);
      modalEl.close();
      showToast("本次学习已取消");
    };
    document.querySelector("#saveVerificationLearning").onclick = () => openLearningSave(task, session);
  }

  function openCheckpointConfirm(task, session, selected) {
    modalEl.innerHTML = `
      <form id="verificationCheckpointForm">
        <div class="modal-head"><h3>确认这个验证点</h3><button class="btn secondary" type="button" id="closeModal">返回</button></div>
        <div class="modal-body form-grid">
          <div class="field"><label>字段名称</label><input name="field_name" value="${e(selected.field_name || selected.text)}" required /></div>
          <div class="field"><label>当前实际值</label><input name="actual_value" value="${e(selected.actual_value || "")}" /></div>
          <div class="field"><label>数据类型</label><select name="value_type"><option value="text">文字</option><option value="money" ${selected.value_type === "money" ? "selected" : ""}>金额</option><option value="status">状态</option></select></div>
          <div class="field"><label>验证方式</label><select name="verification_type"><option value="equals">等于预期</option><option value="contains">包含文案</option><option value="amount_equals">金额相等</option><option value="evidence">只采集证据</option></select></div>
          <div class="field"><label>预期结果</label><input name="expected" value="${e(selected.actual_value || "")}" /></div>
          <p class="verification-v2-hint">系统理解为“${e(selected.field_name || selected.text)}”与其相邻值的关系。你只需改正业务名称或预期，不需要写定位器。</p>
        </div>
        <div class="modal-foot"><span>保存后仍是当前功能分类草稿</span><button class="btn" type="submit">确认添加</button></div>
      </form>`;
    document.querySelector("#closeModal").onclick = () => openLearningWorkspace(task, session);
    document.querySelector("#verificationCheckpointForm").onsubmit = async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(event.target).entries());
      data.page_name = session.page_name;
      data.role_name = session.role_name;
      data.currency = selected.currency || "";
      data.relation = selected.relation || "nearby_value";
      data.locator_candidates = selected.locator_candidates || (selected.locator ? [selected.locator] : []);
      await api(`/api/requirement-verifications/learning-sessions/${session.id}/select-checkpoint`, { method: "POST", body: data });
      openLearningWorkspace(task, await api(`/api/requirement-verifications/learning-sessions/${session.id}`));
    };
  }

  function openLearningSave(task, session) {
    modalEl.innerHTML = `
      <form id="verificationLearningSaveForm">
        <div class="modal-head"><h3>保存学习规则</h3><button class="btn secondary" type="button" id="closeModal">返回</button></div>
        <div class="modal-body">
          <div class="field"><label>规则名称</label><input name="name" value="${e(task.name)}页面规则" /></div>
          <label class="check-field"><input type="checkbox" name="replay_verified"/><span>本次流程已经成功回放</span></label>
          <label class="check-field"><input type="checkbox" name="promote_to_project"/><span>确认写入项目记忆，供后续功能分类复用</span></label>
          <p class="verification-v2-hint">没有成功回放时只能保存为当前分类草稿，避免错误经验污染后续测试。</p>
        </div>
        <div class="modal-foot"><button class="btn" type="submit">保存</button></div>
      </form>`;
    document.querySelector("#closeModal").onclick = () => openLearningWorkspace(task, session);
    document.querySelector("#verificationLearningSaveForm").onsubmit = async (event) => {
      event.preventDefault();
      const form = event.target;
      const body = {
        name: form.querySelector('[name="name"]').value,
        replay_verified: form.querySelector('[name="replay_verified"]').checked,
        promote_to_project: form.querySelector('[name="promote_to_project"]').checked,
      };
      try {
        await api(`/api/requirement-verifications/learning-sessions/${session.id}/save`, { method: "POST", body });
        localStorage.removeItem(`verificationLearningSession:${task.id}`);
        modalEl.close();
        showToast("学习规则已保存");
        await window.renderRequirementVerification();
      } catch (error) {
        showToast(error.message);
      }
    };
  }

  async function openSimilar(task) {
    const result = await api(`/api/requirement-verifications/${task.id}/similar`);
    const rows = result.items || [];
    modalEl.innerHTML = `
      <div><div class="modal-head"><h3>继承相似功能</h3><button class="btn secondary" id="closeModal">关闭</button></div>
      <div class="modal-body">${rows.length ? rows.map((item) => `<article class="verification-v2-similar"><div><strong>${e(item.name)}</strong><span>相似度 ${Math.round(item.score * 100)}%</span></div><p>可继承 ${item.confirmed_items} 个验证点、${item.confirmed_memories} 条项目规则</p><button class="btn" data-inherit-task="${item.task_id}">继承已确认内容</button></article>`).join("") : '<div class="empty">当前项目还没有可复用的相似功能</div>'}</div></div>`;
    modalEl.showModal();
    document.querySelector("#closeModal").onclick = () => modalEl.close();
    document.querySelectorAll("[data-inherit-task]").forEach((button) => button.onclick = async () => {
      const result = await api(`/api/requirement-verifications/${task.id}/inherit`, { method: "POST", body: { source_task_id: Number(button.dataset.inheritTask), item_ids: [], memory_ids: [] } });
      modalEl.close();
      showToast(`已继承 ${result.copied_item_ids.length} 个验证点`);
      await window.renderRequirementVerification();
    });
  }

  async function openEfficiency(task) {
    const stats = await api(`/api/requirement-verifications/stats/efficiency?task_id=${task.id}`);
    modalEl.innerHTML = `<div><div class="modal-head"><h3>功能测试效率统计</h3><button class="btn secondary" id="closeModal">关闭</button></div><div class="modal-body"><div class="verification-v2-stats"><div><span>执行次数</span><strong>${stats.runs}</strong></div><div><span>自动完成</span><strong>${stats.automatic_completed}</strong></div><div><span>业务失败</span><strong>${stats.business_failures}</strong></div><div><span>技术阻塞</span><strong>${stats.technical_blocks}</strong></div><div><span>无效数据</span><strong>${stats.data_invalid}</strong></div><div><span>已确认规则</span><strong>${stats.reused_rules}</strong></div></div><p class="verification-v2-hint">技术阻塞、跳过和待人工项不会被计算为通过，也不会降低业务通过率。</p></div></div>`;
    modalEl.showModal();
    document.querySelector("#closeModal").onclick = () => modalEl.close();
  }

  async function openDefect(itemId) {
    const draft = await api(`/api/requirement-verifications/run-items/${itemId}/defect-draft`);
    modalEl.innerHTML = `<div><div class="modal-head"><h3>缺陷草稿</h3><button class="btn secondary" id="closeModal">关闭</button></div><div class="modal-body"><pre class="mini-log verification-v2-defect-text">${e(draft.copy_text)}</pre><button class="btn" id="copyVerificationDefect">复制中文缺陷草稿</button></div></div>`;
    modalEl.showModal();
    document.querySelector("#closeModal").onclick = () => modalEl.close();
    document.querySelector("#copyVerificationDefect").onclick = async () => {
      await navigator.clipboard.writeText(draft.copy_text || "");
      showToast("缺陷草稿已复制");
    };
  }

  function bind(task) {
    document.querySelector("#startVerificationLearning")?.addEventListener("click", () => openLearningStart(task));
    document.querySelector("#inheritVerificationHistory")?.addEventListener("click", () => openSimilar(task));
    document.querySelector("#verificationEfficiency")?.addEventListener("click", () => openEfficiency(task));
    document.querySelectorAll("[data-v2-run-action]").forEach((button) => button.addEventListener("click", async () => {
      await api(`/api/requirement-verifications/runs/${button.dataset.runId}/${button.dataset.v2RunAction}`, { method: "POST" });
      await window.renderRequirementVerification();
    }));
    document.querySelectorAll("[data-v2-run-retry]").forEach((button) => button.addEventListener("click", async () => {
      const path = `/api/requirement-verifications/runs/${button.dataset.runId}/retry`;
      const body = { strategy: button.dataset.v2RunRetry, item_ids: [], risk_confirmed: false };
      try {
        await api(path, { method: "POST", body });
      } catch (error) {
        if (!String(error.message || "").includes("高风险脚本")) throw error;
        if (!window.confirm("本次数据准备包含支付、充值或资金类操作，确认重新执行吗？")) return;
        await api(path, { method: "POST", body: { ...body, risk_confirmed: true } });
      }
      await window.renderRequirementVerification();
    }));
    document.querySelector("[data-open-test-browser]")?.addEventListener("click", async () => {
      const latest = task.runs?.[0];
      if (!latest) return;
      try {
        const result = await api(`/api/requirement-verifications/runs/${latest.id}/open-browser`, { method: "POST" });
        showToast(result.status === "already_open" ? "测试浏览器已经打开，请切换到浏览器窗口" : "已重新打开原页面并恢复项目登录状态");
      } catch (error) {
        showToast(error.message);
      }
    });
    document.querySelectorAll("[data-v2-defect]").forEach((button) => button.addEventListener("click", () => openDefect(button.dataset.v2Defect)));
    const latest = task.runs?.[0];
    const waiting = latest?.waiting_user_items?.length || 0;
    if (waiting) {
      document.title = `(${waiting}) 需要我处理 - AI 功能测试工作台`;
      const noticeKey = `verificationWaitingNotice:${latest.id}:${waiting}`;
      if ("Notification" in window && Notification.permission === "granted" && !sessionStorage.getItem(noticeKey)) {
        new Notification("需求验证中心需要你处理", { body: `${task.name} 有 ${waiting} 个等待项` });
        sessionStorage.setItem(noticeKey, "sent");
      }
    } else if (document.title.includes("需要我处理")) {
      document.title = "AI 功能测试工作台";
    }
  }

  const style = document.createElement("style");
  style.textContent = `
    .verification-v2-capabilities,.verification-v2-stats{display:grid;grid-template-columns:repeat(3,minmax(100px,1fr));gap:10px}.verification-v2-capabilities>div,.verification-v2-stats>div{display:grid;gap:4px;padding:12px;border:1px solid var(--border);border-radius:9px;text-align:center}.verification-v2-capabilities strong,.verification-v2-stats strong{font-size:22px}.verification-v2-capabilities span,.verification-v2-stats span,.verification-v2-hint{color:var(--muted);font-size:12px}.verification-v2-cockpit{display:grid;gap:12px;margin:10px 0}.verification-v2-phase{display:grid;gap:5px;padding:12px;border:1px solid var(--border);border-radius:9px}.verification-v2-phase span,.verification-v2-phase small{color:var(--muted)}.verification-v2-run-controls{justify-content:flex-end}.verification-v2-attention{padding:14px;border:2px solid #d8a63c;border-radius:10px;background:#fffaf0}.verification-v2-attention article{display:grid;gap:6px;padding:10px 0;border-top:1px solid #ead9ae}.verification-v2-attention article span,.verification-v2-attention article small{font-size:12px;color:#70551f}.verification-v2-datasets,.verification-v2-failures{padding:10px 12px;border:1px solid var(--border);border-radius:9px}.verification-v2-datasets summary,.verification-v2-failures summary{cursor:pointer;font-weight:700}.verification-v2-datasets article,.verification-v2-failures article,.verification-v2-similar,.verification-v2-checkpoint{display:grid;gap:7px;padding:10px 0;border-bottom:1px solid var(--border)}.verification-v2-datasets article>div,.verification-v2-failures article>div,.verification-v2-similar>div{display:flex;justify-content:space-between;gap:10px}.verification-v2-datasets p,.verification-v2-similar p{margin:0;color:var(--muted)}.verification-v2-learning-status,.verification-v2-learning-actions{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}.verification-v2-defect-text{white-space:pre-wrap;min-height:240px}.verification-v2-stats{grid-template-columns:repeat(3,1fr)}@media(max-width:700px){.verification-v2-capabilities,.verification-v2-stats{grid-template-columns:1fr}.verification-v2-learning-status,.verification-v2-learning-actions{align-items:stretch;flex-direction:column}}
  `;
  document.head.appendChild(style);

  window.RequirementVerificationV2 = { renderSections, renderRunWorkspace, bind };
})();
