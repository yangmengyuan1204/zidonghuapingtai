(function () {
  "use strict";

  const SESSION_KEY = "dataFactoryAgentSessionId";
  const TERMINAL = new Set(["succeeded", "failed", "blocked", "cancelled"]);
  const STATUS_LABELS = {
    clarifying: "待补充",
    awaiting_confirmation: "待确认",
    awaiting_risk_confirmation: "待风险确认",
    awaiting_permission: "待权限",
    running: "执行中",
    succeeded: "已完成",
    failed: "失败",
    blocked: "已阻塞",
    cancelled: "已取消",
  };
  const NODE_LABELS = {
    shopping_cart: "购物车已备货",
    order_created: "订单已创建",
    order_translated: "订单已翻译",
    order_confirmed: "采购已确认",
    order_offered: "订单待付款",
    order_paid: "订单已付款",
    pending_purchase: "订单待拍下",
    purchase_no_saved: "采购交易号已保存",
    purchase_wait_modify_price: "采购待改价",
    purchase_wait_pay: "采购待财务付款",
    purchase_paid: "采购已付款",
    checking_started: "商品开始核查",
    shelf_stored: "商品已上架",
    warehouse_delivery_created: "配送单已创建",
    porder_translated: "配送单已翻译",
    porder_confirmed: "配送单采购已确认",
    porder_wait_offer: "配送单待报价",
    porder_offered: "配送单待付款",
    porder_paid: "配送单已付款",
    porder_shipped: "配送单已出货",
    full_complete: "全部流程已完成",
    problem_goods: "问题产品处理",
    order_wait_offer: "订单待报价",
    order_purchase: "订单采购",
    order_translate: "订单翻译",
    porder_wait_box: "配送单待装箱",
    porder_wait_translate: "配送单待翻译",
    shelf_checking: "商品核查中",
  };
  const TOOL_LABELS = {
    run_full_flow: "新建订单并推进",
    resume_order_flow: "续跑订单",
    resume_porder_flow: "续跑配送单",
    fill_shopping_cart: "补充购物车",
    quote_order: "订单报价",
    pay_order: "订单付款",
    confirm_order_bank_deposit: "确认银行入金",
    advance_purchase_to_shelf: "推进采购到上架",
    create_and_quote_porder: "创建并报价配送单",
    pay_porder: "配送单付款",
    inspect_order_state: "查询订单真实状态",
    inspect_porder_state: "查询配送单真实状态",
    inspect_problem_goods: "查询问题产品",
    inspect_order_options: "查询商品附加服务",
    process_problem_goods: "提出并处理问题产品",
    rollback_business_state: "逐级回退业务状态",
  };
  const FIELD_LABELS = {
    order_item_num: "每种购买数量",
    order_shop_count: "店铺数",
    order_per_shop: "每店商品种类数",
    keyword: "商品关键词",
    confirm_freight: "采购确认运费",
    offer_freight: "订单报价运费",
    offer_price: "统一执行单价",
    offer_unit_prices: "逐商品执行单价",
    target_node: "目标状态",
    options: "商品附加服务",
    quantity: "购买数量",
    item_count: "商品种类数",
    shop_count: "店铺数",
    items_per_shop: "每店商品种类数",
    customer_id: "客户编号",
  };
  const NODE_STATUS_LABELS = {
    running: "执行中",
    completed: "已完成",
    failed: "失败",
    awaiting_permission: "等待授权",
  };

  let currentSession = null;
  let pollTimer = null;
  let pollInFlight = false;
  let options = null;
  let permissionAccounts = null;
  let permissionAccountsLoading = false;
  let pendingContractPreview = null;

  function knownLabel(mapping, value, emptyText = "未提供") {
    if (value === null || value === undefined || value === "") return emptyText;
    return mapping[String(value)] || "未识别";
  }

  function nodeLabel(value) {
    return knownLabel(NODE_LABELS, value, "尚未开始");
  }

  function stopPolling() {
    if (pollTimer) window.clearTimeout(pollTimer);
    pollTimer = null;
  }

  async function withBusyButton(button, busyText, action) {
    if (!button || button.disabled) return;
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = busyText;
    try {
      return await action();
    } finally {
      button.disabled = false;
      button.textContent = originalText;
    }
  }

  function statusBadge(status, escapeHtml) {
    const kind = status === "succeeded" ? "ok" : ["failed", "blocked"].includes(status) ? "fail" : "warn";
    return `<span class="badge ${kind}">${escapeHtml(knownLabel(STATUS_LABELS, status, "未知状态"))}</span>`;
  }

  function goalHtml(goal, escapeHtml) {
    if (!goal || !Object.keys(goal).length) return "";
    const variables = goal.variables || {};
    const intent = goal.intent || {};
    const pricing = intent.pricing || {};
    const prices = Array.isArray(pricing.effective_unit_prices) && pricing.effective_unit_prices.length
      ? pricing.effective_unit_prices.join(" / ")
      : Array.isArray(variables.offer_unit_prices)
        ? variables.offer_unit_prices.join(" / ")
        : variables.offer_price || "保持原值";
    const defaults = (goal.defaults_used || [])
      .filter((item) => ["order_item_num", "keyword", "confirm_freight", "offer_freight"].includes(item.field))
      .map((item) => `${knownLabel(FIELD_LABELS, item.field, "默认项")}=${item.value}`)
      .join("，");
    const steps = (goal.steps || []).map((step, index) => `<li>${index + 1}. ${escapeHtml(step)}</li>`).join("");
    const operations = (goal.operations || []).map((operation, index) => {
      const labels = { advance_order: "订单推进", advance_porder: "配送单推进", problem_goods: "问题产品", rollback: "业务状态回退" };
      const detail = operation.type === "problem_goods"
        ? `${operation.quantity_refund_mode === "all" ? "退全部商品数量和商品金额" : operation.quantity_refund_mode === "half" ? "退一半商品数量和对应金额" : "按指定数量处理商品金额"}；${operation.freight_refund_mode === "all" ? "退全部国内运费" : "国内运费保持不变"}；${operation.option_refund_mode === "all" ? "退全部附加服务金额" : "附加服务保持不变"}`
        : operation.target_label || nodeLabel(operation.target_node);
      return `<li>${index + 1}. ${escapeHtml(labels[operation.type] || "未知操作")}：${escapeHtml(detail)}</li>`;
    }).join("");
    const corrections = (intent.corrections || []).map((item) => `${knownLabel(FIELD_LABELS, item.field, "识别项")}：${item.reason}`).join("；");
    const shapeText = variables.order_shop_count && variables.order_per_shop
      ? `${variables.order_shop_count}店 × 每店${variables.order_per_shop}种（共${Number(variables.order_shop_count) * Number(variables.order_per_shop)}种）`
      : "保持原订单数据";
    const quantityText = variables.order_item_num || "保持原值";
    const feeText = `国内运费 ${variables.offer_freight ?? "保持原值"}；其他费用 ${variables.other_price ?? "保持原值"}`;
    const optionGoal = goal.options || {};
    const optionText = optionGoal.enabled
      ? optionGoal.mode === "random" ? `每个商品随机添加${optionGoal.count || 0}项` : "按已确认名称添加"
      : "不添加或保持原值";
    return `
      <section class="panel">
        <div class="panel-title"><h3>目标合同</h3>${statusBadge(currentSession?.status, escapeHtml)}</div>
        <div class="panel-body">
          <p>${escapeHtml(goal.summary || "-")}</p>
          <div class="form-grid">
            <div class="field"><label>店铺 / 商品种类</label><input data-goal-editable="true" disabled value="${escapeHtml(shapeText)}" /></div>
            <div class="field"><label>每种购买数量</label><input data-goal-editable="true" disabled value="${escapeHtml(quantityText)}" /></div>
            <div class="field"><label>价格口径</label><input disabled value="${escapeHtml(pricing.mode_label || "保持原订单价格")}" /></div>
            <div class="field"><label>商品金额合计</label><input disabled value="${escapeHtml(pricing.requested_goods_total || pricing.effective_goods_total || "保持原值")}" /></div>
            <div class="field"><label>实际执行单价</label><input data-goal-editable="true" disabled value="${escapeHtml(prices)}" /></div>
            <div class="field"><label>运费 / 其他费用</label><input disabled value="${escapeHtml(feeText)}" /></div>
            <div class="field"><label>商品附加服务</label><input disabled value="${escapeHtml(optionText)}" /></div>
            <div class="field"><label>客户范围</label><input disabled value="${escapeHtml(goal.customer_scope_label || "项目默认测试账号")}" /></div>
            <div class="field"><label>支付方式</label><input disabled value="${variables.order_payment_mode === "bank" ? "银行付款并财务入金" : variables.order_payment_mode ? "余额优先" : "保持原值"}" /></div>
            <div class="field"><label>目标状态</label><input data-goal-editable="true" disabled value="${escapeHtml(goal.target_label || (goal.target_node ? nodeLabel(goal.target_node) : "仅执行后置操作"))}" /></div>
            <div class="field"><label>合同版本</label><input disabled value="v${escapeHtml(currentSession?.plan_version || 1)} · ${escapeHtml(goal.contract_hash || "-")}" /></div>
          </div>
          ${operations ? `<details open><summary>有序操作合同</summary><ol>${operations}</ol></details>` : ""}
          ${corrections ? `<p class="muted">自动纠偏：${escapeHtml(corrections)}</p>` : ""}
          ${defaults ? `<p class="muted">自动补全：${escapeHtml(defaults)}</p>` : ""}
          ${steps ? `<details><summary>预计执行步骤</summary><ol>${steps}</ol></details>` : ""}
        </div>
      </section>`;
  }

  function contractGoalHtml(session, escapeHtml) {
    if (window.DataAgentContractEditor && session.contract_editor?.fields?.length) {
      return window.DataAgentContractEditor.render(session, { escapeHtml });
    }
    return goalHtml(session.goal, escapeHtml);
  }

  function permissionHtml(session, escapeHtml) {
    if (session.status !== "awaiting_permission") return "";
    const accounts = permissionAccounts || [];
    const accountOptions = accounts
      .filter((item) => item.status === "active")
      .map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.profile_name || `账号#${item.id}`)}</option>`)
      .join("");
    return `<form id="dataAgentPermissionForm" class="panel">
      <div class="panel-title"><h3>需要部长后台账号</h3></div>
      <div class="panel-body"><p>${escapeHtml(session.question || session.result?.reason || "退款达到权限阈值，请选择账号后继续")}</p>
        <div class="field"><label><input type="radio" name="permission_source" value="profile" checked /> 使用系统账号</label> <label><input type="radio" name="permission_source" value="temporary" /> 临时输入账号</label></div>
        <div data-permission-source="profile" class="field"><label>后台账号档案</label><select name="backend_account_profile_id">${accountOptions || '<option value="">正在加载账号...</option>'}</select></div>
        <div data-permission-source="temporary" hidden>
          <div class="field"><label>后台账号</label><input name="backend_account" autocomplete="username" maxlength="160" /></div>
          <div class="field"><label>后台密码</label><input name="backend_password" type="password" autocomplete="current-password" maxlength="500" /></div>
        </div>
      </div><div class="modal-foot"><span>不会重复提出已经生成的问题产品</span><button class="btn" type="submit">继续执行</button></div>
    </form>`;
  }

  function riskConfirmationHtml(session, escapeHtml) {
    if (session.status !== "awaiting_risk_confirmation") return "";
    const risk = session.goal?.risk || {};
    return `<form id="dataAgentRiskConfirmForm" class="panel">
      <div class="panel-title"><h3>高风险操作二次确认</h3></div>
      <div class="panel-body">
        <p>操作：${escapeHtml(risk.operation || session.goal?.summary || "-")}</p>
        <p>客户范围：${escapeHtml(risk.customer_scope || session.goal?.customer_scope_label || "-")}</p>
        <p>金额与方向：${escapeHtml(risk.amount_direction || "-")}</p>
        <p>执行账号：${escapeHtml(risk.account_role || "按当前项目绑定账号")}</p>
        <p class="danger-text">该操作会修改真实测试业务数据，请核对后确认。</p>
        <label><input type="checkbox" name="acknowledged" required /> 我已核对上述范围、金额、方向和执行账号</label>
      </div>
      <div class="modal-foot"><span>合同 ${escapeHtml(session.goal?.contract_hash || "-")}</span><button class="btn danger" type="submit">确认执行高风险操作</button></div>
    </form>`;
  }

  function eventsHtml(events, escapeHtml) {
    if (!events?.length) return '<div class="empty">等待智能体决策</div>';
    return events
      .map((event) => `
        <div class="panel" style="margin-bottom:8px">
          <div class="panel-title"><strong>${escapeHtml(event.message || event.kind)}</strong><span>${escapeHtml(event.time || "")}</span></div>
          ${event.tool ? `<div class="panel-body"><span class="badge">${escapeHtml(knownLabel(TOOL_LABELS, event.tool, "未知工具"))}</span>${event.expected ? ` <span>${escapeHtml(event.expected)}</span>` : ""}</div>` : ""}
        </div>`)
      .join("");
  }

  function progressHtml(progress, escapeHtml) {
    if (!progress || !Object.keys(progress).length) {
      return '<section class="panel data-agent-progress"><div class="panel-title"><h3>当前执行进度</h3></div><div class="panel-body"><p>等待开始执行</p></div></section>';
    }
    const operationIndex = Number(progress.operation_index || 0);
    const operationTotal = Number(progress.operation_total || 0);
    const itemText = progress.item_total
      ? `；当前商品 ${Number(progress.item_index || 0)} / ${Number(progress.item_total)}`
      : "";
    const problemText = progress.problem_goods_id ? `；问题产品编号 ${escapeHtml(progress.problem_goods_id)}` : "";
    const nextText = progress.next_node ? `；下一节点 ${escapeHtml(nodeLabel(progress.next_node))}` : "";
    const percent = operationTotal ? Math.min(100, Math.max(0, Math.round((operationIndex - (progress.node_status === "completed" ? 0 : 1)) / operationTotal * 100))) : 0;
    return `<section class="panel data-agent-progress">
      <div class="panel-title"><h3>当前执行进度</h3><span class="badge warn">${escapeHtml(knownLabel(NODE_STATUS_LABELS, progress.node_status, "等待执行"))}</span></div>
      <div class="panel-body">
        <p>第 ${operationIndex || 1} / ${operationTotal || 1} 项操作；当前节点 ${escapeHtml(nodeLabel(progress.current_node))}${nextText}${itemText}${problemText}</p>
        <div style="height:8px;border-radius:999px;background:var(--border);overflow:hidden"><span style="display:block;height:100%;width:${percent}%;background:var(--primary)"></span></div>
        <p class="muted">开始时间 ${escapeHtml(progress.started_at || "-")}；最后更新 ${escapeHtml(progress.updated_at || "-")}${progress.reason ? `；说明 ${escapeHtml(progress.reason)}` : ""}</p>
      </div>
    </section>`;
  }

  function questionHtml(session, escapeHtml) {
    if (session.status !== "clarifying") return "";
    const pending = Object.values(session.pending_fields || {});
    const pendingHtml = pending.length
      ? `<p>请一次补充或纠正以下信息：</p><ul>${pending.map((item) => `<li><strong>${escapeHtml(item.label || "待确认信息")}：</strong>${escapeHtml(item.question || "请补充")}</li>`).join("")}</ul>`
      : `<p>${escapeHtml(session.question || "请补充关键目标")}</p>`;
    return `<form id="dataAgentMessageForm" class="panel">
      <div class="panel-title"><h3>需要补充</h3></div>
      <div class="panel-body">${pendingHtml}<textarea id="dataAgentMessage" name="message" rows="3" required placeholder="直接说明你最终要的数据和状态"></textarea></div>
      <div class="modal-foot"><span>请直接补充或纠正，已确认内容会保留</span><button class="btn" type="submit">发送给 DeepSeek</button></div>
    </form>`;
  }

  function resultHtml(session, escapeHtml) {
    if (!session.result || !Object.keys(session.result).length) return "";
    const state = session.current_state || {};
    const result = session.result || {};
    const actualNode = result.current_node || state.current_node || state.detected_start_node || "";
    return `<section class="panel"><div class="panel-title"><h3>最终结果</h3>${statusBadge(session.status, escapeHtml)}</div><div class="panel-body">
      <p>${escapeHtml(result.reason || "执行结果已生成")}</p>
      ${result.suggested_tool ? `<p>建议补充能力：${escapeHtml(knownLabel(TOOL_LABELS, result.suggested_tool, "新的业务工具"))}</p>` : ""}
      <p>订单号：${escapeHtml(result.order_sn || state.order_sn || "-")}　配送单号：${escapeHtml(result.porder_sn || state.porder_sn || "-")}　实际节点：${escapeHtml(nodeLabel(actualNode))}</p>
      ${state.problem_goods_ids?.length ? `<p>问题产品编号：${state.problem_goods_ids.map((item) => escapeHtml(item)).join("、")}</p>` : ""}
      ${session.record_id ? `<p>聚合测试记录：#${escapeHtml(session.record_id)}</p>` : ""}
    </div></section>`;
  }

  function renderRecordSummary(log, escapeHtml) {
    const summary = log?.summary || {};
    const goal = log?.goal || {};
    const state = summary.state || summary;
    const status = summary.status || (summary.reason?.includes("完成") ? "succeeded" : "");
    const operations = (goal.operations || []).map((operation, index) => {
      const label = operation.type === "problem_goods" ? "问题产品处理" : operation.type === "rollback" ? "业务状态回退" : operation.type === "advance_porder" ? "配送单推进" : operation.type === "advance_order" ? "订单推进" : "未知操作";
      const target = operation.type === "problem_goods" ? "按退款合同处理" : nodeLabel(operation.target_node);
      return `<li>${index + 1}. ${escapeHtml(label)}：${escapeHtml(target)}</li>`;
    }).join("");
    return `<section class="panel"><div class="panel-title"><h3>DeepSeek 数据智能体执行结果</h3>${status ? statusBadge(status, escapeHtml) : ""}</div><div class="panel-body">
      <p>${escapeHtml(summary.reason || "执行记录已生成")}</p>
      <p>订单号：${escapeHtml(state.order_sn || "-")}　配送单号：${escapeHtml(state.porder_sn || "-")}　实际节点：${escapeHtml(nodeLabel(state.current_node || state.detected_start_node))}</p>
      ${state.problem_goods_ids?.length ? `<p>问题产品编号：${state.problem_goods_ids.map((item) => escapeHtml(item)).join("、")}</p>` : ""}
      ${operations ? `<details open><summary>已确认操作</summary><ol>${operations}</ol></details>` : ""}
      ${log?.events?.length ? `<details><summary>执行步骤</summary>${eventsHtml(log.events, escapeHtml)}</details>` : ""}
    </div></section>`;
  }

  function minimizeModal() {
    if (!options?.modalEl?.open) return;
    options.modalEl.close();
    options.showToast("任务仍在后台执行，可随时继续查看");
  }

  function captureModalViewState(modalEl) {
    const body = modalEl.querySelector(".modal-body");
    const active = document.activeElement;
    return {
      scrollTop: body?.scrollTop || 0,
      details: [...modalEl.querySelectorAll("details")].map((item) => item.open),
      activeId: active?.id || "",
      value: active && "value" in active ? active.value : "",
      selectionStart: active?.selectionStart,
      selectionEnd: active?.selectionEnd,
    };
  }

  function restoreModalViewState(modalEl, viewState) {
    const body = modalEl.querySelector(".modal-body");
    if (body) body.scrollTop = viewState.scrollTop;
    [...modalEl.querySelectorAll("details")].forEach((item, index) => {
      if (viewState.details[index] !== undefined) item.open = viewState.details[index];
    });
    const active = viewState.activeId ? modalEl.querySelector(`#${viewState.activeId}`) : null;
    if (active) {
      if ("value" in active) active.value = viewState.value;
      active.focus();
      if (typeof active.setSelectionRange === "function" && viewState.selectionStart !== undefined) {
        active.setSelectionRange(viewState.selectionStart, viewState.selectionEnd);
      }
    }
  }

  function updateRegion(modalEl, selector, html) {
    const element = modalEl.querySelector(selector);
    if (element && element.innerHTML !== html) element.innerHTML = html;
  }

  function bindModalActions(modalEl) {
    const messageForm = modalEl.querySelector("#dataAgentMessageForm");
    if (messageForm) messageForm.onsubmit = sendMessage;
    const permissionForm = modalEl.querySelector("#dataAgentPermissionForm");
    if (permissionForm) {
      permissionForm.onsubmit = resumePermission;
      permissionForm.querySelectorAll('[name="permission_source"]').forEach((input) => {
        input.onchange = () => {
          const source = new FormData(permissionForm).get("permission_source");
          permissionForm.querySelectorAll("[data-permission-source]").forEach((section) => {
            section.hidden = section.dataset.permissionSource !== source;
          });
        };
      });
    }
    const riskForm = modalEl.querySelector("#dataAgentRiskConfirmForm");
    if (riskForm) riskForm.onsubmit = confirmRisk;
    if (window.DataAgentContractEditor && currentSession?.contract_editor?.fields?.length) {
      window.DataAgentContractEditor.bind(
        modalEl.querySelector("#data-agent-goal"),
        currentSession,
        {
          escapeHtml: options.escapeHtml,
          save: saveContractFields,
          previewCorrection: previewContractCorrection,
          applyPreview: applyContractPreview,
          markCorrect: markContractCorrect,
          confirm: confirmContract,
        },
      );
    }
    const confirmButton = modalEl.querySelector("#dataAgentConfirm");
    if (confirmButton) confirmButton.onclick = confirmGoal;
    const editButton = modalEl.querySelector("#dataAgentEditGoal");
    if (editButton) editButton.onclick = toggleGoalEdit;
    const cancelButton = modalEl.querySelector("#dataAgentCancel");
    if (cancelButton) cancelButton.onclick = cancelSession;
  }

  function updatePanelButton() {
    const button = document.querySelector("#dataAgentResume");
    if (!button) return;
    const status = currentSession?.status;
    button.hidden = !currentSession?.id && !sessionStorage.getItem(SESSION_KEY);
    button.textContent = currentSession?.id
      ? `${knownLabel(STATUS_LABELS, status, "查看任务")} · 继续查看`
      : "继续查看任务";
  }

  function updateModal(session = currentSession) {
    if (!options || !session) return;
    const { escapeHtml, modalEl } = options;
    if (modalEl.dataset.dataAgentSessionId !== String(session.id) || !modalEl.querySelector("#data-agent-status")) return;
    const viewState = captureModalViewState(modalEl);
    const hasContractEditor = Boolean(window.DataAgentContractEditor && session.contract_editor?.fields?.length);
    const confirmButton = session.can_confirm && !hasContractEditor ? '<button class="btn" id="dataAgentConfirm" type="button">确认目标并执行</button>' : "";
    const cancelButton = session.can_cancel ? '<button class="btn danger" id="dataAgentCancel" type="button">停止后续步骤</button>' : "";
    updateRegion(modalEl, "#data-agent-status", statusBadge(session.status, escapeHtml));
    updateRegion(modalEl, "#data-agent-progress", progressHtml(session.current_state?.progress, escapeHtml));
    updateRegion(modalEl, "#data-agent-goal", contractGoalHtml(session, escapeHtml));
    updateRegion(modalEl, "#data-agent-question", `${questionHtml(session, escapeHtml)}${permissionHtml(session, escapeHtml)}${riskConfirmationHtml(session, escapeHtml)}`);
    updateRegion(modalEl, "#data-agent-events", `<section><div class="panel-title"><h3>实时步骤与自动纠错</h3></div>${eventsHtml(session.events, escapeHtml)}</section>`);
    updateRegion(modalEl, "#data-agent-result", resultHtml(session, escapeHtml));
    updateRegion(modalEl, "#data-agent-task", `任务 ${escapeHtml(session.id)}`);
    updateRegion(modalEl, "#data-agent-actions", `${cancelButton}${confirmButton}`);
    bindModalActions(modalEl);
    restoreModalViewState(modalEl, viewState);
    updatePanelButton();
    if (session.status === "awaiting_permission" && !permissionAccounts && !permissionAccountsLoading) void loadPermissionAccounts();
  }

  function renderModal() {
    if (!options || !currentSession) return;
    const { modalEl } = options;
    const ownsModal = modalEl.dataset.dataAgentSessionId === String(currentSession.id) && modalEl.querySelector("#data-agent-status");
    if (!ownsModal) {
      modalEl.id = "dataFactoryAgentModal";
      modalEl.dataset.dataAgentSessionId = String(currentSession.id);
      modalEl.innerHTML = `
        <div class="modal-head"><h3>DeepSeek 数据智能体 <span id="data-agent-status"></span></h3><div class="actions"><button class="btn secondary" id="dataAgentMinimize" type="button">最小化</button><button class="btn secondary" id="dataAgentClose" type="button">关闭</button></div></div>
        <div class="modal-body"><div id="data-agent-progress"></div><div id="data-agent-goal"></div><div id="data-agent-question"></div><div id="data-agent-events"></div><div id="data-agent-result"></div></div>
        <div class="modal-foot"><span id="data-agent-task"></span><div class="actions" id="data-agent-actions"></div></div>`;
      modalEl.querySelector("#dataAgentMinimize").onclick = minimizeModal;
      modalEl.querySelector("#dataAgentClose").onclick = () => modalEl.close();
    }
    updateModal(currentSession);
    if (!modalEl.open) modalEl.showModal();
  }

  async function refreshSession() {
    if (!options || !currentSession?.id) return;
    if (pollInFlight) return;
    pollInFlight = true;
    try {
      currentSession = await options.api(`/api/data-scripts/agent/sessions/${currentSession.id}`);
      updateModal(currentSession);
      if (!TERMINAL.has(currentSession.status) && !["clarifying", "awaiting_confirmation", "awaiting_risk_confirmation", "awaiting_permission"].includes(currentSession.status)) {
        pollTimer = window.setTimeout(refreshSession, 1000);
      } else {
        stopPolling();
      }
    } catch (error) {
      stopPolling();
      options.showToast(error.message || "智能体状态查询失败");
    } finally {
      pollInFlight = false;
    }
  }

  async function sendMessage(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const message = new FormData(form).get("message");
    await withBusyButton(form.querySelector('button[type="submit"]'), "正在理解补充内容...", async () => {
      currentSession = await options.api(`/api/data-scripts/agent/sessions/${currentSession.id}/messages`, {
        method: "POST",
        body: { message },
      });
      renderModal();
    });
  }

  function toggleGoalEdit() {
    const fields = document.querySelectorAll('#dataFactoryAgentModal [data-goal-editable="true"]');
    const btn = document.getElementById("dataAgentEditGoal");
    if (!fields.length) return;
    const editing = !fields[0].disabled;
    fields.forEach(function (f) { f.disabled = editing; });
    if (btn) btn.textContent = editing ? "编辑目标数据" : "保存修改";
    if (!editing) return;
    // Collect and send edited values
    const goal = currentSession.goal || {};
    const vars = goal.variables || {};
    const updates = {};
    fields.forEach(function (f) {
      const label = (f.closest(".field")?.querySelector("label")?.textContent || "").trim();
      const value = f.value.trim();
      if (!value) return;
      if (label.includes("店铺")) {
        var m = value.match(/(\d+)\D+(\d+)/);
        if (m) { updates.order_shop_count = parseInt(m[1]); updates.order_per_shop = parseInt(m[2]); }
      } else if (label.includes("购买数量")) {
        updates.order_item_num = parseInt(value) || vars.order_item_num;
      } else if (label.includes("执行单价")) {
        if (value.includes("/")) {
          updates.offer_unit_prices = value.split("/").map(function(s) { return s.trim(); });
        } else {
          updates.offer_price = value;
        }
      } else if (label.includes("目标")) {
        updates.target_node = value;
      }
    });
    if (!Object.keys(updates).length) return;
    saveGoalEdits(updates);
  }

  async function loadPermissionAccounts() {
    permissionAccountsLoading = true;
    try {
      permissionAccounts = await options.api(`/api/test-accounts?project_id=${encodeURIComponent(options.projectId)}`);
    } catch (error) {
      permissionAccounts = [];
      options.showToast(error.message || "后台账号加载失败");
    } finally {
      permissionAccountsLoading = false;
      updateModal(currentSession);
    }
  }

  async function resumePermission(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const source = formData.get("permission_source");
    const profileId = Number(formData.get("backend_account_profile_id"));
    const temporaryAccount = String(formData.get("backend_account") || "").trim();
    const temporaryPassword = String(formData.get("backend_password") || "");
    const passwordInput = form.querySelector('[name="backend_password"]');
    try {
      if (source === "profile" && !profileId) return options.showToast("请选择后台账号档案");
      if (source === "temporary" && (!temporaryAccount || !temporaryPassword.trim())) {
        return options.showToast("请同时输入后台账号和密码");
      }
      const body = source === "profile"
        ? { plan_version: currentSession.plan_version, backend_account_profile_id: profileId }
        : {
            plan_version: currentSession.plan_version,
            backend_account: temporaryAccount,
            backend_password: temporaryPassword,
          };
      currentSession = await options.api(`/api/data-scripts/agent/sessions/${currentSession.id}/permission`, {
        method: "POST",
        body,
      });
      options.showToast("已提供账号，继续执行");
      renderModal();
      stopPolling();
      pollTimer = window.setTimeout(refreshSession, 600);
    } finally {
      if (passwordInput) passwordInput.value = "";
    }
  }

  async function saveContractFields(fields, planVersion) {
    currentSession = await options.api(
      `/api/data-scripts/agent/sessions/${currentSession.id}/goal`,
      { method: "PATCH", body: { fields, plan_version: planVersion } },
    );
    pendingContractPreview = null;
    options.showToast("合同修改已保存");
    renderModal();
    return currentSession;
  }

  async function previewContractCorrection(message, planVersion) {
    pendingContractPreview = await options.api(
      `/api/data-scripts/agent/sessions/${currentSession.id}/contract-preview`,
      { method: "POST", body: { message, plan_version: planVersion } },
    );
    options.showToast("合同修正预览已生成，请核对后应用");
    return pendingContractPreview;
  }

  async function applyContractPreview(previewHash, planVersion) {
    if (!pendingContractPreview || pendingContractPreview.preview_hash !== previewHash) {
      options.showToast("合同修正预览已失效，请重新生成");
      throw new Error("合同修正预览已失效");
    }
    currentSession = await options.api(
      `/api/data-scripts/agent/sessions/${currentSession.id}/contract-preview/apply`,
      {
        method: "POST",
        body: {
          plan_version: planVersion,
          base_contract_hash: pendingContractPreview.base_contract_hash,
          preview_hash: previewHash,
        },
      },
    );
    pendingContractPreview = null;
    options.showToast("合同修正已应用");
    renderModal();
    return currentSession;
  }

  async function markContractCorrect(planVersion) {
    currentSession = await options.api(
      `/api/data-scripts/agent/sessions/${currentSession.id}/contract-feedback`,
      { method: "POST", body: { plan_version: planVersion, verdict: "correct" } },
    );
    options.showToast("合同正确，已保存为待验证样本");
    return currentSession;
  }

  async function saveGoalEdits(updates) {
    try {
      currentSession = await options.api(
        "/api/data-scripts/agent/sessions/" + currentSession.id + "/goal",
        { method: "PATCH", body: { ...updates, plan_version: currentSession.plan_version } }
      );
      options.showToast("目标已更新");
      renderModal();
    } catch (err) {
      options.showToast("更新失败: " + (err.message || "unknown"));
    }
  }

  async function confirmRisk(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const acknowledged = new FormData(form).get("acknowledged") === "on";
    await withBusyButton(form.querySelector('button[type="submit"]'), "正在启动高风险操作...", async () => {
      currentSession = await options.api(`/api/data-scripts/agent/sessions/${currentSession.id}/risk-confirm`, {
        method: "POST",
        body: {
          plan_version: currentSession.plan_version,
          contract_hash: currentSession.goal?.contract_hash || "",
          acknowledged,
        },
      });
      options.showToast("高风险范围已确认，智能体开始执行");
      renderModal();
      stopPolling();
      pollTimer = window.setTimeout(refreshSession, 600);
    });
  }

  async function confirmContract(planVersion) {
    currentSession = await options.api(`/api/data-scripts/agent/sessions/${currentSession.id}/confirm`, {
      method: "POST",
      body: { plan_version: planVersion },
    });
    options.showToast(currentSession.status === "awaiting_risk_confirmation" ? "目标已确认，请继续核对高风险范围" : "目标已确认，智能体开始执行");
    renderModal();
    stopPolling();
    pollTimer = window.setTimeout(refreshSession, 600);
    return currentSession;
  }

  async function confirmGoal() {
    const button = document.querySelector("#dataAgentConfirm");
    await withBusyButton(button, "正在启动执行...", () => confirmContract(currentSession.plan_version));
  }

  async function cancelSession() {
    currentSession = await options.api(`/api/data-scripts/agent/sessions/${currentSession.id}/cancel`, { method: "POST" });
    options.showToast("已请求停止后续步骤");
    renderModal();
  }

  async function createSession(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const envId = Number(form.get("env_id"));
    if (!envId) {
      options.showToast("请选择执行环境");
      return;
    }
    const topbarCustomerIds = String(localStorage.getItem("dataScriptCustomerIds") || "")
      .split(/[\n,，;；]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    await withBusyButton(formElement.querySelector('button[type="submit"]'), "正在理解目标...", async () => {
      currentSession = await options.api("/api/data-scripts/agent/sessions", {
        method: "POST",
        body: {
          project_id: Number(options.projectId),
          env_id: envId,
          instruction: form.get("instruction"),
          topbar_customer_ids: topbarCustomerIds,
        },
      });
      sessionStorage.setItem(SESSION_KEY, currentSession.id);
      renderModal();
    });
  }

  async function openStoredSession() {
    const sessionId = sessionStorage.getItem(SESSION_KEY);
    if (!sessionId) return;
    currentSession = { id: sessionId };
    await refreshSession();
    renderModal();
  }

  async function openLearningCenter() {
    // learning/candidates 及 approveLearningRule、promoteLearningRule、rollbackLearningRule
    // 的回归结果、来源样本、运行回归、提升全局、停用展示和操作统一由独立模块负责。
    let dialog = document.querySelector("#dataAgentLearningCenter");
    if (!dialog) {
      dialog = document.createElement("dialog");
      dialog.id = "dataAgentLearningCenter";
      dialog.className = "modal";
      document.body.appendChild(dialog);
    }
    await window.DataAgentLearningCenter.open({ ...options, dialog });
  }

  function reportLearningCenterOpenError(error) {
    if (error?.detail) return;
    options.showToast(`学习中心打开失败：${error?.message || "未知错误"}`);
  }

  function mount(config) {
    options = config;
    permissionAccounts = null;
    stopPolling();
    if (!config?.root || !config.isAdmin || config.projectName !== "日本站测试") return;
    const envs = (config.envs || []).filter((env) => String(env.project_id) === String(config.projectId));
    const stored = sessionStorage.getItem(SESSION_KEY);
    const section = document.createElement("section");
    section.id = "dataFactoryAgentPanel";
    section.className = "panel";
    section.style.marginBottom = "16px";
    section.innerHTML = `
      <div class="panel-title"><div><h3>DeepSeek 数据智能体</h3><p>用自然语言描述目标，智能体会在受控工具范围内造数并校验实际状态。</p></div><div class="actions"><button class="btn secondary" id="dataAgentLearning" type="button">学习中心</button><button class="btn secondary" id="dataAgentResume" type="button" ${stored ? "" : "hidden"}>继续查看任务</button></div></div>
      <div class="panel-body">
        <form id="dataAgentCreateForm">
          <div class="form-grid">
            <div class="field"><label>执行环境</label><select name="env_id" required>${envs.map((env) => `<option value="${config.escapeHtml(env.id)}">${config.escapeHtml(env.env_name)}</option>`).join("")}</select></div>
            <div class="field"><label>告诉智能体你要什么数据</label><textarea name="instruction" rows="3" required placeholder="例如：造一个两店各一件商品的订单，两条报价分别1元和2元，银行付款并财务入金，最终到待拍下"></textarea></div>
          </div>
          <div class="actions"><button class="btn" type="submit">让 DeepSeek 理解目标</button></div>
        </form>
      </div>`;
    config.root.prepend(section);
    section.querySelector("#dataAgentCreateForm")?.addEventListener("submit", createSession);
    section.querySelector("#dataAgentLearning")?.addEventListener("click", () => openLearningCenter().catch(reportLearningCenterOpenError));
    section.querySelector("#dataAgentResume")?.addEventListener("click", openStoredSession);
  }

  window.DataFactoryAgent = { mount, progressHtml, renderRecordSummary };
})();
