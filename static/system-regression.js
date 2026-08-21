(function () {
  const existing = views.findIndex((item) => item.key === "systemRegression");
  if (existing < 0) {
    const recordsIndex = views.findIndex((item) => item.key === "records");
    views.splice(recordsIndex < 0 ? views.length : recordsIndex, 0, { key: "systemRegression", label: "系统回归" });
  }

  const originalRenderCurrentView = renderCurrentView;
  renderCurrentView = function () {
    if (state.view === "systemRegression") return window.renderSystemRegression();
    return originalRenderCurrentView();
  };

  const srState = {
    suiteKey: "japan",
    cases: [],
    categories: [],
    category: "all",
    selected: new Set(),
    activeId: 0,
    projectId: localStorage.getItem("systemRegressionProjectId") || localStorage.getItem("projectId") || "",
    envId: localStorage.getItem("systemRegressionEnvId") || "",
    customerId: localStorage.getItem("systemRegressionCustomerId") || "",
    ledgerWait: localStorage.getItem("systemRegressionLedgerWait") || "30",
    tickets: { coupons: [], vouchers: [], reason: "" },
    membership: { kind: "", level_name: "", service_rate: "", preview_cny_to_jpy: "", reason: "" },
    options: { rows: [], reason: "" },
    drawerTab: "process",
    newKind: "order",
    projects: [],
    envs: [],
    problemTypes: [],
    batch: null,
    batchStartedAt: 0,
    pollId: 0,
    pollTimer: 0,
    clockTimer: 0,
    recentBatches: [],
    resultFilter: "all",
    resultQuery: "",
    resultTab: "events",
    expandedRunId: 0,
    eventLog: [],
    resumeUsername: "",
    resumePassword: "",
    runConsoleScrollBusy: false,
    pendingRunConsolePatch: false,
    runConsoleScrollGuardBound: false,
    casePaneHeightBound: false,
  };

  const BATCH_STORAGE_KEY = "systemRegressionActiveBatch";
  const LIVE_STATUSES = ["pending", "running", "waiting_account"];
  const STATUS_LABELS = {
    pending: "排队",
    running: "执行中",
    waiting_account: "等待账号",
    passed: "通过",
    failed: "失败",
    blocked: "缺前置",
    stopped: "已停止",
  };

  const categoryLabels = {
    payment: "支付金额",
    problem_amount: "问题产品-基础金额",
    problem_service_fee: "问题产品-手续费",
    problem_option_manual: "问题产品-OPTION手动",
    problem_option_auto: "问题产品-OPTION自动",
    problem_mixed: "问题产品-混合调整",
    problem_flow: "问题产品-完整流程",
    problem_guard: "问题产品-预期拦截",
    porder: "配送单",
  };
  const LOGISTICS = [
    ["25", "KS-JP电子特殊便"], ["24", "KS-JP航空経済便"], ["18", "KS-JP航空便"],
    ["29", "海源電子特殊航空便"], ["4", "電子特殊便"], ["23", "Raku-DQ"], ["1", "EMS"], ["2", "OCS"],
    ["14", "お任せ(お勧め)"], ["20", "RW船便"], ["30", "Rロジ専用船便"], ["12", "TW船便"],
    ["15", "海源DQ船便"], ["22", "海源TK船便"], ["3", "EMS船便"]
  ];
  const AIR_LOGISTICS = new Set(["1", "2", "4", "18", "23", "24", "25", "29"]);
  const FEE_FIELDS = [
    ["domestic_freight", "国内运费"],
    ["service_fee", "手续费"],
    ["additional_service_fee", "附加服务费（OPTION 跟这项走）"],
    ["other_fee", "其他费用"]
  ];
  const OPTION_PLACEHOLDERS = new Set(["加固包装", "检品", "加急出货"]);
  const CLIENT_DEALS = [["accept", "接受"], ["exchange", "换货"], ["cancel", "取消/退货"], ["discard", "已收不退"], ["other", "其他"]];
  const PURCHASE_DEALS = ["仅退款", "退货退款", "换货", "丢货重拍", "少货补买", "其他"];
  const SERVICE_COUPON_ID = "__service_discount__";
  const ACCOUNT_COUPON_ID = "__account_coupon__";
  const ACCOUNT_VOUCHER_ID = "__account_voucher__";
  const TICKETS_API = "/api/system-regression/tickets";
  const OPTIONS_API = "/api/system-regression/options";
  const TICKET_LIST_PATH = "/client/user.usableDiscount";
  const OPTION_LIST_PATH = "/client/order.optionList";
  let ticketsRequest = 0;
  let optionsRequest = 0;

  function isOnRegressionPage() {
    return state.view === "systemRegression";
  }

  function isLiveStatus(status) {
    return LIVE_STATUSES.includes(status);
  }

  function fmtClock(ms) {
    const total = Math.max(0, Math.floor((ms || 0) / 1000));
    return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
  }

  function nowStamp() {
    const d = new Date();
    return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, "0")).join(":");
  }

  function caseName(run) {
    const item = srState.cases.find((row) => row.id === run.case_id);
    return item?.name || run.case_key || String(run.case_id || "");
  }

  function tally(batch) {
    const runs = batch?.runs || [];
    return {
      total: Number(batch?.total_count || runs.length || 0),
      passed: Number(batch?.passed_count || 0),
      failed: Number(batch?.failed_count || 0),
      waiting: runs.filter((run) => run.status === "waiting_account").length,
      queued: runs.filter((run) => run.status === "pending" || run.status === "running").length,
      done: runs.filter((run) => !isLiveStatus(run.status)).length,
    };
  }

  function persistActiveBatch(batch) {
    if (!batch?.id) return;
    const counts = tally(batch);
    const snapshot = {
      id: batch.id,
      batch_no: batch.batch_no,
      status: batch.status,
      passed_count: counts.passed,
      failed_count: counts.failed,
      blocked_count: Number(batch.blocked_count || 0),
      total_count: counts.total,
      done_count: counts.done,
      started_at: srState.batchStartedAt || Date.now(),
      updated_at: Date.now(),
    };
    srState.batchStartedAt = snapshot.started_at;
    localStorage.setItem(BATCH_STORAGE_KEY, JSON.stringify(snapshot));
  }

  function readActiveBatch() {
    try {
      return JSON.parse(localStorage.getItem(BATCH_STORAGE_KEY) || "null");
    } catch {
      return null;
    }
  }

  function pushEvent(key, text) {
    srState.eventLog.push({ time: nowStamp(), key: key || "BATCH", text });
    if (srState.eventLog.length > 80) srState.eventLog.splice(0, srState.eventLog.length - 80);
  }

  function appendRunEvents(previous, next) {
    const prevMap = Object.fromEntries((previous?.runs || []).map((run) => [run.id, run.status]));
    (next?.runs || []).forEach((run) => {
      if (prevMap[run.id] === run.status) return;
      if (run.status === "running") pushEvent(run.case_key, `开始执行 ${caseName(run)}`);
      else if (run.status === "passed") pushEvent(run.case_key, "通过");
      else if (run.status === "failed") pushEvent(run.case_key, `失败${run.reason_code ? ` · ${run.reason_code}` : ""}`);
      else if (run.status === "blocked") pushEvent(run.case_key, `缺前置${run.reason_code ? ` · ${run.reason_code}` : ""}`);
      else if (run.status === "waiting_account") pushEvent(run.case_key, "退款达到 500 元，需要部长账号");
      else if (run.status === "stopped") pushEvent(run.case_key, "已停止");
    });
    if (previous?.status !== next?.status && next?.status && !isLiveStatus(next.status)) {
      const counts = tally(next);
      pushEvent("", `批次结束：通过 ${counts.passed} · 失败 ${counts.failed}`);
    }
  }

  function startClock() {
    if (srState.clockTimer) return;
    srState.clockTimer = window.setInterval(() => {
      if (!srState.batch || !isLiveStatus(srState.batch.status)) return;
      const elapsed = Date.now() - (srState.batchStartedAt || Date.now());
      document.querySelectorAll("[data-sr-clock]").forEach((el) => { el.textContent = fmtClock(elapsed); });
    }, 250);
  }

  function captureRunConsoleScroll() {
    const seq = document.querySelector(".system-regression-seq");
    const pane = document.querySelector(".system-regression-pane");
    return {
      seqLeft: seq ? seq.scrollLeft : 0,
      paneTop: pane ? pane.scrollTop : 0,
      paneHeight: pane ? pane.scrollHeight : 0,
    };
  }

  function capturePageScroll() {
    const scroll = document.querySelector(".system-regression-scroll");
    const cases = document.querySelector(".system-regression-cases");
    const drawer = document.querySelector(".system-regression-drawer");
    const cats = document.querySelector(".system-regression-categories");
    const host = document.querySelector("#srRunConsoleHost");
    return {
      scrollTop: scroll ? scroll.scrollTop : 0,
      casesTop: cases ? cases.scrollTop : 0,
      drawerTop: drawer ? drawer.scrollTop : 0,
      catsTop: cats ? cats.scrollTop : 0,
      hostTop: host ? host.scrollTop : 0,
      run: captureRunConsoleScroll(),
    };
  }

  function restorePageScroll(saved, options = {}) {
    const scroll = document.querySelector(".system-regression-scroll");
    const cases = document.querySelector(".system-regression-cases");
    const drawer = document.querySelector(".system-regression-drawer");
    const cats = document.querySelector(".system-regression-categories");
    const host = document.querySelector("#srRunConsoleHost");
    if (scroll) scroll.scrollTop = saved.scrollTop;
    if (cases) cases.scrollTop = saved.casesTop;
    if (cats) cats.scrollTop = saved.catsTop;
    if (host) host.scrollTop = saved.hostTop;
    if (drawer) drawer.scrollTop = options.resetDrawer ? 0 : saved.drawerTop;
    restoreRunConsoleScroll(saved.run);
  }

  function syncCasePaneHeights() {
    const drawer = document.querySelector(".system-regression-drawer");
    const cases = document.querySelector(".system-regression-cases");
    const cats = document.querySelector(".system-regression-categories");
    if (!drawer || !cases) return;
    [cases, cats].forEach((el) => {
      if (!el) return;
      el.style.height = "auto";
    });
    const height = Math.ceil(drawer.getBoundingClientRect().height);
    if (height <= 0) return;
    cases.style.height = `${height}px`;
    if (cats) cats.style.height = `${height}px`;
  }

  function bindCasePaneHeightSync() {
    if (srState.casePaneHeightBound) return;
    srState.casePaneHeightBound = true;
    window.addEventListener("resize", () => {
      if (!isOnRegressionPage()) return;
      syncCasePaneHeights();
    });
  }

  function restoreRunConsoleScroll(saved) {
    const seq = document.querySelector(".system-regression-seq");
    const pane = document.querySelector(".system-regression-pane");
    if (seq) seq.scrollLeft = saved.seqLeft;
    if (!pane) return;
    if (saved.paneTop <= 8) {
      pane.scrollTop = 0;
      return;
    }
    pane.scrollTop = saved.paneTop + Math.max(0, pane.scrollHeight - saved.paneHeight);
  }

  function bindRunConsoleScrollGuard() {
    if (srState.runConsoleScrollGuardBound) return;
    srState.runConsoleScrollGuardBound = true;
    document.addEventListener("pointerdown", (event) => {
      if (event.target?.closest?.(".system-regression-seq, .system-regression-pane")) {
        srState.runConsoleScrollBusy = true;
      }
    });
    const release = () => {
      if (!srState.runConsoleScrollBusy) return;
      srState.runConsoleScrollBusy = false;
      if (!srState.pendingRunConsolePatch) return;
      srState.pendingRunConsolePatch = false;
      patchRunConsole();
    };
    document.addEventListener("pointerup", release);
    document.addEventListener("pointercancel", release);
  }

  function currentCase() {
    return srState.cases.find((item) => item.id === srState.activeId) || srState.cases[0] || null;
  }

  function visibleCases() {
    return srState.category === "all"
      ? srState.cases
      : srState.cases.filter((item) => item.category === srState.category);
  }

  function problemTypeOptions(selectedValue) {
    return srState.problemTypes.map((problemType) => `
      <option value="${escapeHtml(problemType.value)}" ${Number(selectedValue) === Number(problemType.value) ? "selected" : ""}>${escapeHtml(problemType.label)}</option>`).join("");
  }

  function money(n) { return Math.round((Number(n) || 0) * 100) / 100; }
  function yen(n) { return money(n).toFixed(2); }
  function emptyMembership() {
    return { kind: "", level_name: "", service_rate: "", preview_cny_to_jpy: "", reason: "" };
  }
  function cnyToJpyRate() {
    const n = Number(srState.membership && srState.membership.preview_cny_to_jpy);
    return n > 0 ? n : 21.2;
  }
  function membershipServiceRate() {
    const raw = srState.membership && srState.membership.service_rate;
    if (raw === 0 || raw === "0") return 0;
    const n = Number(raw);
    return Number.isFinite(n) ? n : 0.05;
  }
  function membershipCustomerAttr() {
    const m = srState.membership || emptyMembership();
    const name = String(m.level_name || "").trim().toUpperCase();
    if (!name && !m.kind) return m.reason || "未拉取";
    if (name.includes("SVIP")) return "SVIP";
    if (name.includes("VIP") || m.kind === "fixed") return "VIP";
    return "普通用户";
  }
  function membershipFeeNoteHtml() {
    const percent = money(membershipServiceRate() * 100);
    return `<div class="system-regression-bill-member" id="srBillMembership"><span>客户属性：${escapeHtml(membershipCustomerAttr())}</span><strong>手续费比例 ${escapeHtml(String(percent))}%</strong></div>`;
  }
  function jpyFromCny(n) { return Math.round(money(n) * cnyToJpyRate()); }
  function dualCnyJpy(n, minus) {
    const sign = minus ? "−" : "";
    return `<strong class="system-regression-money-dual"><b><em>人民币</em><i>${sign}${yen(n)}</i></b><b><em>日元</em><i>${sign}${jpyFromCny(n)}</i></b></strong>`;
  }
  function moneyValue(value) {
    if (value && typeof value === "object") return money(value.value);
    return money(value);
  }
  function isPorderCase(item) { return item?.runner_kind === "porder_payment"; }
  function isProblemCase(item) { return String(item?.runner_kind || "").startsWith("problem_"); }
  function optionListPairs(rows, selected) {
    return rows.map(([value, label]) => `<option value="${escapeHtml(value)}" ${String(value) === String(selected) ? "selected" : ""}>${escapeHtml(label)}</option>`).join("");
  }

  function optionKey(row) {
    return String(row?.key || row?.id || row?.name || "").trim();
  }

  function assignedLiveOptions(saved, catalog) {
    const assigned = new Map();
    const usedLive = new Set();
    const rows = (saved || []).filter((row) => row && row.checked !== false);
    function take(match) {
      rows.forEach((row) => {
        if ([...assigned.values()].includes(row)) return;
        const live = catalog.find((item) => !usedLive.has(optionKey(item)) && match(row, item));
        if (!live) return;
        usedLive.add(optionKey(live));
        assigned.set(optionKey(live), row);
      });
    }
    take((row, live) => {
      const key = optionKey(row);
      return Boolean(key) && [optionKey(live), String(live.id || ""), String(live.name || ""), String(live.label || "")].includes(key);
    });
    take((row, live) => {
      const name = String(row.name || "").trim();
      return Boolean(name) && (name === String(live.name || "").trim() || name === String(live.label || "").trim());
    });
    take((row, live) => OPTION_PLACEHOLDERS.has(String(row.name || "").trim()) && Number(row.price_type) === Number(live.price_type));
    return assigned;
  }

  function optionPickerHtml(itemIndex, selectedOptions) {
    const catalog = srState.options.rows || [];
    if (!catalog.length) {
      const reason = srState.options.reason || `先选业务项目、执行环境和客户 ID，点「重新拉券和 OPTION」。会调 ${OPTION_LIST_PATH}。`;
      const saved = (selectedOptions || []).filter((row) => row && row.checked !== false && String(row.name || row.id || "").trim());
      return `<p class="system-regression-hint">${escapeHtml(reason)}${saved.length ? ` 当前用例先记着 ${saved.map((row) => row.name || row.id).join("、")}，拉到列表后按名称或计价类型对上。` : ""}</p>`;
    }
    const assigned = assignedLiveOptions(selectedOptions, catalog);
    const rows = catalog.map((row) => {
      const key = optionKey(row);
      const saved = assigned.get(key);
      const checked = Boolean(saved);
      const num = saved?.num ?? 1;
      const priceKind = Number(row.price_type) === 1 ? "百分比" : "固定金额";
      const priceText = Number(row.price_type) === 1 ? `${row.price}%` : `${row.price}${row.unit ? ` ${row.unit}` : ""}`;
      return `<label class="system-regression-check wide">
        <input type="checkbox" data-live-option="${itemIndex}:${escapeHtml(key)}" ${checked ? "checked" : ""} />
        <span>${escapeHtml(row.name || row.label || key)} · ${priceKind} ${escapeHtml(priceText)}</span>
        <input type="number" min="1" data-live-option-num="${itemIndex}:${escapeHtml(key)}" value="${escapeHtml(num)}" ${checked ? "" : "disabled"} />
      </label>`;
    }).join("");
    return `<div class="system-regression-option-live" data-item-options="${itemIndex}"><p class="system-regression-hint">下面是当前环境 ${escapeHtml(OPTION_LIST_PATH)} 拉到的 OPTION，勾选用哪几项、买几个。</p>${rows}</div>`;
  }

  function itemTags(items) {
    return items.map((row, itemIndex) => `
      <div class="system-regression-repeat" data-item-row="${itemIndex}">
        <div class="system-regression-grid">
          <div class="field"><label>单番序号</label><input type="number" min="1" data-item-sorting value="${escapeHtml(row.sorting ?? itemIndex + 1)}" /></div>
          <div class="field"><label>买几个</label><input type="number" min="1" data-item-quantity value="${escapeHtml(row.quantity ?? 1)}" /></div>
          <div class="field"><label>报给客户的单价(CNY)</label><input type="number" step="0.01" data-item-price value="${escapeHtml(row.offer_price?.value ?? 10)}" /></div>
          <div class="field"><label>中国国内运费(CNY)</label><input type="number" step="0.01" data-item-freight value="${escapeHtml(row.offer_freight?.value ?? 0)}" /></div>
        </div>
        <div class="system-regression-actions"><button class="btn danger" type="button" data-remove-item="${itemIndex}">删除单番</button></div>
        ${optionPickerHtml(itemIndex, row.options || [])}
      </div>`).join("");
  }

  function emptyPartPay(enabled) {
    return {
      enabled: !!enabled,
      percent: 50,
      tail_node: "before_shelf",
      tail_partial: false,
      tail_sortings: "",
      fee_timing: { domestic_freight: "first", service_fee: "first", additional_service_fee: "first", other_fee: "first" }
    };
  }
  function emptyPorder() {
    return {
      sku_count: 1, send_num: 1, box_count: 1, box_length: 58, box_width: 51, box_height: 50, box_weight: 10,
      logistics: "25", price_manual: false, logistics_price: { value: 0, currency: "CNY" },
      extra_name: "", extra_fee: { value: 0, currency: "CNY" }, payment_mode: "balance",
      voucher: { selectedId: "" }
    };
  }

  function normalizedParameters(item) {
    const source = structuredClone(item?.parameters || {});
    source.order = source.order || {};
    source.order.item_count = source.order.item_count || source.item_count || 1;
    source.order.default_quantity = source.order.default_quantity || 1;
    source.order.other_fee_name = source.order.other_fee_name || source.other_fee_name || "";
    source.order.other_fee_amount = source.order.other_fee_amount || { value: source.other_fee_amount || 0, currency: "CNY" };
    source.order.default_offer_price = source.order.default_offer_price || { value: 10, currency: "CNY" };
    source.order.default_freight = source.order.default_freight || { value: 3, currency: "CNY" };
    source.items = source.items || [];
    source.problem_goods = source.problem_goods || {};
    source.part_pay = { ...emptyPartPay(source.payment_plan === "part" || item?.runner_kind === "order_part_payment"), ...(source.part_pay || {}) };
    if (source.payment_plan === "part") source.part_pay.enabled = true;
    if (source.first_payment_rate && source.part_pay.percent == null) source.part_pay.percent = Math.round(Number(source.first_payment_rate) * 100);
    source.coupon = source.coupon || { selectedId: "" };
    if (source.service_discount && !source.coupon.selectedId) source.coupon.selectedId = SERVICE_COUPON_ID;
    source.porder = { ...emptyPorder(), ...(source.porder || {}) };
    source.porder.voucher = source.porder.voucher || { selectedId: "" };
    source.ledger_wait_seconds = source.ledger_wait_seconds ?? srState.ledgerWait ?? 30;
    if (!source.items.length && item?.runner_kind !== "porder_payment") {
      const count = Math.max(1, Number(source.order.item_count || 1));
      const qty = Number(source.order.default_quantity || 1);
      const price = source.order.default_offer_price || { value: 10, currency: "CNY" };
      const freight = source.order.default_freight || { value: 3, currency: "CNY" };
      source.items = Array.from({ length: count }, (_, index) => ({
        sorting: index + 1,
        quantity: qty,
        offer_price: { value: price.value ?? 10, currency: "CNY" },
        offer_freight: { value: source.per_item_freight ? String(3 + index) : (freight.value ?? 3), currency: "CNY" },
        options: [],
      }));
    }
    return source;
  }

  function predictFreight(p) {
    const length = money(p.box_length);
    const width = money(p.box_width);
    const height = money(p.box_height);
    const weight = money(p.box_weight);
    const count = Math.max(1, Number(p.box_count) || 1);
    const volume = money(length * width * height);
    const air = AIR_LOGISTICS.has(String(p.logistics || "25"));
    const volDiv = air ? 5000 : 6000;
    const rate = air ? 26.2 : 8.5;
    const volW = money(volume / volDiv);
    const chargeKg = money(Math.max(weight, volW));
    const perBox = money(chargeKg * rate);
    const name = (LOGISTICS.find((row) => String(row[0]) === String(p.logistics)) || ["", "未选物流"])[1];
    return { length, width, height, weight, count, volume, volW, chargeKg, name, perBox, total: money(perBox * count) };
  }

  function orderTotals(c) {
    let goods = 0, freight = 0, options = 0;
    (c.items || []).forEach((it) => {
      const unit = moneyValue(it.offer_price);
      goods += money(money(it.quantity) * unit);
      freight += moneyValue(it.offer_freight);
      (it.options || []).forEach((o) => {
        if (o.checked === false) return;
        const qty = money(o.num);
        const price = money(o.price);
        options += Number(o.price_type) === 1 ? money((price / 100) * unit * qty) : money(price * qty);
      });
    });
    const other = moneyValue(c.order?.other_fee_amount);
    const couponOn = Boolean(c.coupon?.selectedId || c.service_discount);
    const serviceRate = membershipServiceRate();
    const serviceBase = money(goods * serviceRate);
    const service = couponOn ? 0 : serviceBase;
    return { goods, freight, options, other, service, serviceBase, couponOn, serviceRate, payable: money(goods + freight + options + other + service) };
  }

  function porderTotals(c) {
    const p = c.porder || emptyPorder();
    const quote = predictFreight(p);
    const logistics = p.price_manual ? moneyValue(p.logistics_price) : quote.total;
    const extra = moneyValue(p.extra_fee);
    const ticket = (srState.tickets.vouchers || []).find((row) => row.id === (p.voucher && p.voucher.selectedId));
    let voucher = 0;
    let voucherHint = "未使用代金券";
    if (ticket && ticket.kind === "all") {
      voucher = money(logistics + extra);
      voucherHint = "这张券全部抵扣，配送应付变成 0";
    } else if (ticket) {
      voucher = 0;
      voucherHint = ticket.amount
        ? `这张券按物流抵 ${ticket.amount} 日元，预览不和人民币运费混减`
        : "这张券按物流抵扣，预览不和人民币运费混减";
    }
    return { logistics, extra, voucher, voucherHint, payable: money(Math.max(0, logistics + extra - voucher)), quote, manual: !!p.price_manual };
  }

  function billHtml(item, parameters) {
    if (isPorderCase(item)) {
      const p = porderTotals(parameters);
      return `<div class="system-regression-bill" id="srBill">
        <div><span>${p.manual ? "国际运费（人工钉死）" : "国际运费（执行时按箱子+物流算）"}</span>${dualCnyJpy(p.logistics)}</div>
        <div><span>${escapeHtml(p.voucher ? p.voucherHint : "代金券抵扣")}</span>${dualCnyJpy(p.voucher, true)}</div>
        <div class="first"><span>配送单应付</span>${dualCnyJpy(p.payable)}</div>
      </div>`;
    }
    const t = orderTotals(parameters);
    return `<div class="system-regression-bill" id="srBill">
      <div><span>报给客户的商品金额</span>${dualCnyJpy(t.goods)}</div>
      <div><span>${t.couponOn ? "手续费（优惠券免）" : "手续费"}</span>${dualCnyJpy(t.service)}</div>
      ${membershipFeeNoteHtml()}
      <div class="first"><span>订单应付</span>${dualCnyJpy(t.payable)}</div>
    </div>`;
  }

  function couponOptions(selectedId) {
    const real = srState.tickets.coupons || [];
    const rows = [
      ["", "不使用优惠券"],
      [ACCOUNT_COUPON_ID, "使用账号当前优惠券（执行时自动选第一张）"],
    ];
    if (!real.length) rows.push([SERVICE_COUPON_ID, "手续费减免券（账号没有真券时用）"]);
    real.forEach((row) => rows.push([row.id, `${row.title}${row.left != null ? `（剩 ${row.left} 张）` : ""}`]));
    let selected = selectedId || "";
    if (selected === SERVICE_COUPON_ID && real[0]?.id) selected = real[0].id;
    if (selected && !rows.some((row) => row[0] === selected)) rows.push([selected, "已选券（当前列表里没有）"]);
    return optionListPairs(rows, selected);
  }

  function voucherOptions(selectedId) {
    const rows = [
      ["", "不使用代金券"],
      [ACCOUNT_VOUCHER_ID, "使用账号当前代金券（执行时自动选第一张）"],
    ];
    (srState.tickets.vouchers || []).forEach((row) => {
      const extra = row.kind === "all" ? "（全部抵扣）" : (row.amount != null && row.amount !== "" ? `（按物流抵 ${row.amount} 日元）` : "（按物流抵）");
      rows.push([row.id, `${row.title}${extra}`]);
    });
    if (selectedId && !rows.some((row) => row[0] === selectedId)) rows.push([selectedId, "已选券（当前列表里没有）"]);
    return optionListPairs(rows, selectedId || "");
  }

  function partPayHtml(parameters) {
    const pp = parameters.part_pay;
    if (!pp.enabled) return "";
    const feeSel = FEE_FIELDS.map(([key, label]) => `
      <div class="field"><label>${escapeHtml(label)}</label>
        <select data-part-timing="${key}">
          <option value="first" ${(pp.fee_timing?.[key] || "first") !== "tail" ? "selected" : ""}>首款支付</option>
          <option value="tail" ${pp.fee_timing?.[key] === "tail" ? "selected" : ""}>尾款支付</option>
        </select>
      </div>`).join("");
    const percents = Array.from({ length: 21 }, (_, i) => i * 5).map((n) => `<option value="${n}" ${Number(pp.percent) === n ? "selected" : ""}>${n}%</option>`).join("");
    return `<details class="system-regression-block" open>
      <summary>分批付款 <em>和数据工厂「全流程加入分批付款」同一套</em></summary>
      <div class="inner">
        <div class="system-regression-grid">
          <div class="field"><label>首款比例</label><select id="srPartPercent">${percents}</select></div>
          <div class="field"><label>尾款什么时候付</label>
            <select id="srPartTailNode">
              <option value="before_shelf" ${pp.tail_node !== "before_porder_create" ? "selected" : ""}>上架仓库前</option>
              <option value="before_porder_create" ${pp.tail_node === "before_porder_create" ? "selected" : ""}>提出配送单前</option>
            </select>
          </div>
          <div class="field"><label>尾款付哪些番</label>
            <select id="srPartTailPartial">
              <option value="0" ${pp.tail_partial ? "" : "selected"}>整单剩余尾款</option>
              <option value="1" ${pp.tail_partial ? "selected" : ""}>按番尾款</option>
            </select>
          </div>
          <div class="field"><label>尾款支付番序号</label><input id="srPartSortings" value="${escapeHtml(pp.tail_sortings || "")}" /><small class="system-regression-hint">选「按番尾款」时填，例如 1,2。</small></div>
          ${feeSel}
        </div>
      </div>
    </details>`;
  }

  function couponHtml(parameters) {
    const t = orderTotals(parameters);
    const selected = parameters.coupon?.selectedId || "";
    return `<details class="system-regression-block" open>
      <summary>订单优惠券 <em>选一张就把手续费变成 0</em></summary>
      <div class="inner">
        <div class="field wide"><label>优惠券</label><select id="srCouponId">${couponOptions(selected)}</select></div>
        <p class="system-regression-hint">${selected ? `已选券。手续费从 ${yen(t.serviceBase)} 变成 0。优惠券只免手续费，不减商品货款。` : `没选券。手续费按会员费率 ${money(t.serviceRate * 100)}% 预估，现在是 ${yen(t.service)}。${srState.membership && srState.membership.level_name ? escapeHtml("当前账号：" + srState.membership.level_name + "。") : ""}${srState.tickets.reason ? escapeHtml(srState.tickets.reason) : ""}`}</p>
      </div>
    </details>`;
  }

  function porderPaneHtml(item, parameters) {
    const p = parameters.porder || emptyPorder();
    const t = porderTotals(parameters);
    return `
      <p class="system-regression-how">配送单金额跟订单货款无关。国际运费按物流方式 + 箱子长宽高重量，执行时调 porder.predictLogisticsPrice。</p>
      <details class="system-regression-block" open>
        <summary>怎么付钱</summary>
        <div class="inner system-regression-grid">
          <div class="field"><label>支付渠道</label><select id="srPaymentMode"><option value="balance" ${parameters.payment_mode !== "bank" ? "selected" : ""}>余额</option><option value="bank" ${parameters.payment_mode === "bank" ? "selected" : ""}>银行</option></select></div>
        </div>
      </details>
      <details class="system-regression-block" open>
        <summary>提出哪些货 <em>不计入金额</em></summary>
        <div class="inner system-regression-grid">
          <div class="field"><label>提出几番</label><input id="srPorderSkuCount" type="number" min="1" value="${escapeHtml(p.sku_count)}" /></div>
          <div class="field"><label>每番发几个</label><input id="srPorderSendNum" type="number" min="1" value="${escapeHtml(p.send_num)}" /></div>
        </div>
      </details>
      <details class="system-regression-block" open>
        <summary>怎么装箱 <em>这些尺寸会拿去算运费</em></summary>
        <div class="inner system-regression-grid">
          <div class="field"><label>箱子数量</label><input id="srBoxCount" type="number" min="1" value="${escapeHtml(p.box_count)}" /></div>
          <div class="field"><label>箱长</label><input id="srBoxLength" type="number" step="any" value="${escapeHtml(p.box_length)}" /></div>
          <div class="field"><label>箱宽</label><input id="srBoxWidth" type="number" step="any" value="${escapeHtml(p.box_width)}" /></div>
          <div class="field"><label>箱高</label><input id="srBoxHeight" type="number" step="any" value="${escapeHtml(p.box_height)}" /></div>
          <div class="field"><label>箱重（KG）</label><input id="srBoxWeight" type="number" step="any" value="${escapeHtml(p.box_weight)}" /></div>
          <div class="field"><label>单箱体积</label><input id="srBoxVolume" readonly value="${escapeHtml(t.quote.volume)}" /><small class="system-regression-hint">长×宽×高，接口入参 volume。</small></div>
        </div>
      </details>
      <details class="system-regression-block" open>
        <summary>配送单怎么算钱</summary>
        <div class="inner">
          <div class="system-regression-grid">
            <div class="field wide"><label>国际物流方式</label><select id="srLogistics">${optionListPairs(LOGISTICS, p.logistics)}</select></div>
            <div class="field"><label>计费重（KG）</label><input id="srChargeKg" readonly value="${escapeHtml(yen(t.quote.chargeKg))}" /><small class="system-regression-hint">实重和体积重取大的。</small></div>
            <div class="field"><label>国际运费</label>
              ${p.price_manual ? `<input id="srLogisticsPrice" type="number" step="0.01" value="${escapeHtml(p.logistics_price?.value ?? 0)}" />` : `<input id="srPredictedFreight" readonly value="${yen(t.logistics)}" />`}
              <small class="system-regression-hint">${p.price_manual ? "已改成人工钉死。" : "执行时调 porder.predictLogisticsPrice。上面预估仅供参考。"}</small>
            </div>
            <div class="field"><label>其他配送费用叫什么</label><input id="srPorderExtraName" value="${escapeHtml(p.extra_name || "")}" /></div>
            <div class="field"><label>其他配送费用</label><input id="srPorderExtraFee" type="number" step="0.01" value="${escapeHtml(p.extra_fee?.value ?? 0)}" /></div>
            <label class="system-regression-check wide"><input id="srPriceManual" type="checkbox" ${p.price_manual ? "checked" : ""} />少数情况要钉死金额，不用接口价</label>
          </div>
        </div>
      </details>
      <details class="system-regression-block" open>
        <summary>配送单代金券 <em>从账号拉列表，按券自己的规则抵</em></summary>
        <div class="inner">
          <div class="field wide"><label>代金券</label><select id="srVoucherId">${voucherOptions(p.voucher?.selectedId || "")}</select></div>
          <p class="system-regression-hint">${escapeHtml(t.voucherHint)}。${srState.tickets.reason ? escapeHtml(srState.tickets.reason) : "不用填名称、ID、怎么减、减免多少钱。用当前客户 ID 调 " + TICKET_LIST_PATH + " 拉列表。"}</p>
        </div>
      </details>`;
  }

  function problemProcessHtml(item, parameters) {
    const problem = parameters.problem_goods || {};
    const it = parameters.items[0] || { quantity: 1, offer_price: { value: 10 }, offer_freight: { value: 3 } };
    return `
      <p class="system-regression-how">执行时会先按「造订单」下好单，再按下面 6 步做问题产品处理。</p>
      <div class="system-regression-step">
        <header><b>1</b><strong>提出什么问题</strong></header>
        <div class="system-regression-grid">
          <div class="field"><label>问题类型</label><select id="srProblemType">${problemTypeOptions(problem.problem_type || parameters.problem_type)}</select></div>
          <div class="field"><label>这次提出几个</label><input id="srProblemNum" type="number" min="0" value="${escapeHtml(problem.problem_num ?? 1)}" /></div>
          <div class="field wide"><label>问题描述</label><input id="srProblemDescription" value="${escapeHtml(problem.problem_description || "系统回归问题产品")}" /></div>
          <div class="field wide"><label>客户译文</label><input id="srTranslationContent" value="${escapeHtml(problem.translation_content || "システム回帰テスト")}" /></div>
        </div>
      </div>
      <div class="system-regression-step">
        <header><b>2</b><strong>把数量 / 单价 / 运费改成什么样</strong></header>
        <table class="system-regression-case-table system-regression-compare">
          <thead><tr><th></th><th>下单时</th><th>改成</th></tr></thead>
          <tbody>
            <tr><td>数量</td><td>${escapeHtml(it.quantity ?? 1)}</td><td><input id="srPreNum" type="number" min="0" value="${escapeHtml(problem.pre_num ?? 2)}" /></td></tr>
            <tr><td>报给客户的单价</td><td>${yen(it.offer_price?.value ?? 10)} CNY</td><td><input id="srPrePrice" type="number" step="0.01" value="${escapeHtml(problem.pre_price?.value ?? 9)}" /></td></tr>
            <tr><td>国内运费</td><td>${yen(it.offer_freight?.value ?? 3)} CNY</td><td><input id="srPreFreight" type="number" step="0.01" value="${escapeHtml(problem.pre_freight?.value ?? 1)}" /></td></tr>
          </tbody>
        </table>
        <div class="field" style="margin-top:8px;max-width:220px">
          <label>每次加减多少元</label>
          <input id="srAmountStep" type="number" step="0.01" min="0" value="${escapeHtml(parameters.amount_step || 1)}" />
          <small class="system-regression-hint">自动改单价或运费时用。填 1：原价 10 元，降价变成 9，涨价变成 11。</small>
        </div>
      </div>
      <div class="system-regression-step">
        <header><b>3</b><strong>OPTION 怎么处理</strong></header>
        <div class="field"><label>OPTION计算</label><select id="srOptionSuggest"><option value="2" ${Number(problem.option_deal_suggest || 2) !== 1 ? "selected" : ""}>系统自动计算</option><option value="1" ${Number(problem.option_deal_suggest) === 1 ? "selected" : ""}>按输入值计算</option></select></div>
      </div>
      <div class="system-regression-step">
        <header><b>4</b><strong>客户怎么选</strong></header>
        <div class="system-regression-grid">
          <div class="field"><label>客户处理</label><select id="srClientDeal">${optionListPairs(CLIENT_DEALS, problem.client_deal_choice || "accept")}</select></div>
          <div class="field" ${problem.client_deal_choice === "other" ? "" : 'style="display:none"'}><label>其他回复</label><input id="srClientOther" value="${escapeHtml(problem.client_deal_other || "")}" /></div>
        </div>
      </div>
      <div class="system-regression-step">
        <header><b>5</b><strong>业务怎么定手续费</strong></header>
        ${parameters.coupon?.selectedId || parameters.service_discount ? `<p class="system-regression-hint">这条订单选了手续费减免券，手续费按 0。</p>` : ""}
        <div class="system-regression-grid">
          <div class="field"><label>手续费</label><select id="srServiceSuggest"><option value="2" ${Number(problem.service_deal_suggest || 2) !== 1 ? "selected" : ""}>多退少补</option><option value="1" ${Number(problem.service_deal_suggest) === 1 ? "selected" : ""}>已收不退</option></select></div>
          <div class="field"><label>客户属性</label><input id="srMembershipLevel" readonly value="${escapeHtml(membershipCustomerAttr())}" /></div>
          <div class="field wide"><label>业务处理意见</label><input id="srBusinessDecision" value="${escapeHtml(problem.business_decision || "系统回归自动处理")}" /></div>
        </div>
      </div>
      <div class="system-regression-step">
        <header><b>6</b><strong>采购怎么处理</strong></header>
        <div class="system-regression-grid">
          <div class="field"><label>采购处理类型</label><select id="srPurchaseDeal">${PURCHASE_DEALS.map((name) => `<option value="${escapeHtml(name)}" ${ (problem.g_deal_type || "仅退款") === name ? "selected" : ""}>${escapeHtml(name)}</option>`).join("")}</select></div>
          <div class="field"><label>采购备注</label><input id="srPurchaseRemark" value="${escapeHtml(problem.purchase_remark || "系统回归")}" /></div>
          <label class="system-regression-check wide"><input id="srConfirmDistribution" type="checkbox" ${problem.confirm_distribution !== false ? "checked" : ""} />采购完成后自动配货确认</label>
        </div>
      </div>`;
  }

  function orderPaneHtml(item, parameters) {
    const isPart = parameters.part_pay.enabled || item.runner_kind === "order_part_payment";
    return `
      <details class="system-regression-block" open>
        <summary>怎么付钱</summary>
        <div class="inner system-regression-grid">
          <div class="field"><label>支付渠道</label><select id="srPaymentMode"><option value="balance" ${parameters.payment_mode !== "bank" ? "selected" : ""}>余额</option><option value="bank" ${parameters.payment_mode === "bank" ? "selected" : ""}>银行</option></select></div>
          <div class="field"><label>一次付清还是分批</label><select id="srPartEnabled"><option value="0" ${isPart ? "" : "selected"}>一次付清</option><option value="1" ${isPart ? "selected" : ""}>分批付款</option></select></div>
        </div>
      </details>
      ${partPayHtml(parameters)}
      <details class="system-regression-block" open>
        <summary>订单怎么算</summary>
        <div class="inner system-regression-grid">
          <div class="field"><label>单番数量</label><input id="srItemCount" type="number" min="1" value="${escapeHtml(parameters.order.item_count)}" /></div>
          <div class="field"><label>默认商品数量</label><input id="srDefaultQuantity" type="number" min="1" value="${escapeHtml(parameters.order.default_quantity)}" /></div>
          <div class="field"><label>报给客户的单价(CNY)</label><input id="srDefaultPrice" type="number" step="0.01" value="${escapeHtml(parameters.order.default_offer_price?.value ?? 10)}" /></div>
          <div class="field"><label>默认国内运费(CNY)</label><input id="srDefaultFreight" type="number" step="0.01" value="${escapeHtml(parameters.order.default_freight?.value ?? 3)}" /></div>
          <div class="field"><label>其他费用名义</label><input id="srOtherFeeName" value="${escapeHtml(parameters.order.other_fee_name)}" /></div>
          <div class="field"><label>其他费用金额(CNY)</label><input id="srOtherFeeAmount" type="number" step="0.01" value="${escapeHtml(parameters.order.other_fee_amount?.value ?? 0)}" /></div>
        </div>
      </details>
      <section class="system-regression-section">
        <div class="system-regression-actions"><h4>单番与OPTION</h4><button class="btn secondary" id="srAddItem" type="button">新增单番</button></div>
        <div id="srItemRows">${itemTags(parameters.items)}</div>
      </section>
      ${couponHtml(parameters)}`;
  }

  function drawerTags(item) {
    if (!item) return '<div class="system-regression-drawer"><p>请选择用例。</p></div>';
    const parameters = normalizedParameters(item);
    const showProblem = isProblemCase(item);
    const tab = showProblem ? srState.drawerTab : "order";
    const body = isPorderCase(item)
      ? porderPaneHtml(item, parameters)
      : (showProblem && tab === "process" ? problemProcessHtml(item, parameters) : orderPaneHtml(item, parameters));
    return `<aside class="system-regression-drawer">
      <div class="panel-title"><h3>参数设置</h3><span>${escapeHtml(item.case_key)}</span><button class="btn danger" type="button" data-sr-delete="${item.id}">删除用例</button></div>
      <div class="field wide"><label>用例名称</label><input id="srCaseName" value="${escapeHtml(item.name)}" /></div>
      ${billHtml(item, parameters)}
      ${showProblem ? `<div class="system-regression-drawer-tabs">
        <button type="button" class="${tab === "process" ? "active" : ""}" data-sr-drawer-tab="process">处理问题</button>
        <button type="button" class="${tab === "order" ? "active" : ""}" data-sr-drawer-tab="order">造订单</button>
      </div>` : ""}
      ${body}
      <div class="system-regression-actions system-regression-section">
        <button class="btn" id="srSaveCase" type="button">保存参数</button>
        <button class="btn secondary" id="srCopyCase" type="button">复制用例</button>
        ${item.is_system ? `<button class="btn secondary" id="srResetCase" type="button">恢复默认</button>` : ""}
        <button class="btn" id="srRunOne" type="button">单条执行</button>
      </div>
    </aside>`;
  }

  function categoryTags() {
    const counts = Object.fromEntries(srState.categories.map((key) => [key, srState.cases.filter((item) => item.category === key).length]));
    return `<button class="${srState.category === "all" ? "active" : ""}" data-sr-category="all"><span>全部用例</span><b>${srState.cases.length}</b></button>${srState.categories.map((key) => `<button class="${srState.category === key ? "active" : ""}" data-sr-category="${key}"><span>${escapeHtml(categoryLabels[key] || key)}</span><b>${counts[key]}</b></button>`).join("")}`;
  }

  function caseTableTags() {
    const rows = visibleCases();
    return `<div class="system-regression-case-tools"><div class="panel-title"><h3>用例</h3></div><div class="system-regression-actions"><button class="btn secondary" id="srNewCase" type="button">新建用例</button><button class="btn danger" id="srDeleteVisible" type="button">删除用例</button></div></div><table class="system-regression-case-table"><thead><tr><th><input id="srSelectAll" type="checkbox" /></th><th>编号</th><th>用例名称</th><th>状态</th><th>操作</th></tr></thead><tbody>${rows.map((item) => {
      const run = (srState.batch?.runs || []).find((row) => row.case_id === item.id);
      const statusText = run ? (STATUS_LABELS[run.status] || run.status) : `${item.enabled ? "启用" : "停用"}${item.user_modified ? " · 已修改" : ""}`;
      return `<tr class="${item.id === srState.activeId ? "active" : ""}"><td><input type="checkbox" data-sr-select="${item.id}" ${srState.selected.has(item.id) ? "checked" : ""} /></td><td>${escapeHtml(item.case_key)}</td><td><button class="link-button" data-sr-open="${item.id}" type="button">${escapeHtml(item.name)}</button></td><td data-sr-run-status="${item.id}">${escapeHtml(statusText)}</td><td class="system-regression-row-ops"><button class="link-button" data-sr-open="${item.id}" type="button">编辑</button> <button class="link-button system-regression-delete" data-sr-delete="${item.id}" type="button">删除</button></td></tr>`;
    }).join("")}</tbody></table>`;
  }

  function batchResultTags(batch) {
    if (!batch?.runs?.length) return "";
    const rows = batch.runs.map((run) => {
      const evidence = run.structured_evidence || {};
      const details = {
        execution_id: run.execution_id || "",
        reason_code: run.reason_code || "",
        before_evidence: evidence.before_evidence || {},
        after_evidence: evidence.after_evidence || {},
        response_evidence: evidence.response_evidence || {},
        business_diffs: evidence.business_diffs || [],
        required_effects: evidence.required_effects || [],
        forbidden_effects: evidence.forbidden_effects || [],
        allowed_effects: evidence.allowed_effects || [],
        unclassified_effects: evidence.unclassified_effects || [],
      };
      return `<details><summary>${escapeHtml(run.case_key || run.case_id)} · ${escapeHtml(run.status)}${run.reason_code ? ` · ${escapeHtml(run.reason_code)}` : ""}</summary><pre>${escapeHtml(JSON.stringify(details, null, 2))}</pre></details>`;
    }).join("");
    return `<section class="system-regression-section"><h4>执行结果证据</h4>${rows}</section>`;
  }

  function summarizeEvidence(value) {
    if (value == null || value === "") return "—";
    if (typeof value !== "object") return String(value);
    const keys = Object.keys(value);
    if (!keys.length) return "—";
    return keys.slice(0, 6).map((key) => `${key} ${typeof value[key] === "object" ? JSON.stringify(value[key]) : value[key]}`).join(" · ");
  }

  function readableEvidence(run) {
    const evidence = run.structured_evidence || {};
    const diffs = evidence.business_diffs || [];
    return {
      execution_id: run.execution_id || "",
      reason_code: run.reason_code || "",
      before: summarizeEvidence(evidence.before_evidence || {}),
      after: summarizeEvidence(evidence.after_evidence || {}),
      diffs: diffs.length ? diffs.map((item) => `${item.entity || ""} ${item.field || ""}：${item.before ?? "—"} → ${item.after ?? "—"}`).join("；") : "无",
      note: evidence.failure_reason || run.error_message || "",
    };
  }

  function batchStartedAt(batch) {
    const raw = batch?.start_time || batch?.create_time || "";
    const parsed = raw ? Date.parse(raw) : NaN;
    return Number.isNaN(parsed) ? Date.now() : parsed;
  }

  function batchElapsed(batch) {
    const start = (srState.batch?.id === batch?.id && srState.batchStartedAt) || batchStartedAt(batch);
    const live = isLiveStatus(batch?.status);
    const endParsed = batch?.end_time ? Date.parse(batch.end_time) : NaN;
    const end = live || Number.isNaN(endParsed) ? Date.now() : endParsed;
    return Math.max(0, end - start);
  }

  function batchWhen(batch) {
    const raw = batch?.start_time || batch?.create_time || "";
    const date = raw ? new Date(raw) : null;
    if (!date || Number.isNaN(date.getTime())) return "";
    const pad = (value) => String(value).padStart(2, "0");
    return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  function batchPickLabel(batch) {
    const status = STATUS_LABELS[batch.status] || batch.status || "";
    const passed = Number(batch.passed_count || 0);
    const total = Number(batch.total_count || (batch.runs || []).length || 0);
    return [batchWhen(batch), batch.batch_no || "", `${status} ${passed}/${total}`].filter(Boolean).join("  ");
  }

  function batchOptions() {
    const rows = [...(srState.recentBatches || [])];
    if (srState.batch && !rows.some((item) => item.id === srState.batch.id)) rows.unshift(srState.batch);
    return rows;
  }

  function batchOptionTags(batch) {
    const rows = batchOptions();
    const head = batch ? "" : `<option value="">请选择一批查看结果</option>`;
    return head + rows.map((item) => `<option value="${item.id}" ${item.id === batch?.id ? "selected" : ""}>${escapeHtml(batchPickLabel(item))}</option>`).join("");
  }

  function upsertRecentBatch(batch) {
    if (!batch?.id) return;
    const rest = (srState.recentBatches || []).filter((item) => item.id !== batch.id);
    srState.recentBatches = [batch, ...rest].slice(0, 20);
  }

  function hasLiveBatch() {
    if (srState.batch && isLiveStatus(srState.batch.status)) return true;
    return (srState.recentBatches || []).some((item) => isLiveStatus(item.status));
  }

  function visibleRuns(batch) {
    const query = String(srState.resultQuery || "").trim().toLowerCase();
    const filter = srState.resultFilter || "all";
    return (batch?.runs || []).filter((run) => {
      if (filter === "passed" && run.status !== "passed") return false;
      if (filter === "failed" && !["failed", "stopped"].includes(run.status)) return false;
      if (!query) return true;
      return `${run.case_key || ""} ${caseName(run)}`.toLowerCase().includes(query);
    });
  }

  function runResultText(run) {
    const note = String(run.error_message || run.structured_evidence?.failure_reason || "").trim();
    const orderSn = String(run.order_sn || "").trim();
    const porderSn = String(run.porder_sn || "").trim();
    const ledger = String(
      run.result?.customer_balance_jpy
      || run.structured_evidence?.customer_balance_jpy
      || run.structured_evidence?.after_evidence?.customer_balance_jpy
      || ""
    ).trim();
    const ledgerText = ledger ? `客户出入金 ${ledger} 日元。` : "";
    if (run.status === "passed") {
      if (porderSn) return `通过。配送单 ${porderSn} 已付款。${ledgerText}`;
      if (orderSn) return `通过。订单 ${orderSn} 已付款。${ledgerText}`;
      return ledgerText ? `通过。${ledgerText}` : "通过。";
    }
    if (run.status === "waiting_account") return "等部长账号。";
    if (run.status === "running") return "正在执行。";
    if (run.status === "pending") return "还没开始。";
    if (run.status === "stopped") return note ? `已停止。${note}` : "已停止。";
    if (run.status === "blocked") return note ? `缺前置。${note}` : "缺前置。";
    return note ? `失败。${note}` : "失败。";
  }

  function resultListHtml(batch) {
    const rows = visibleRuns(batch);
    if (!rows.length) return `<p class="system-regression-empty">没有符合条件的结果。</p>`;
    return rows.map((run) => {
      const open = srState.expandedRunId === run.id;
      return `<div class="system-regression-result ${open ? "is-open" : ""}">
        <button class="system-regression-result-head" data-sr-expand="${run.id}" type="button">
          <kbd>${escapeHtml(run.case_key || "")}</kbd>
          <span>${escapeHtml(caseName(run))}</span>
          <em>${escapeHtml(STATUS_LABELS[run.status] || run.status)}</em>
        </button>
        ${open ? `<p class="system-regression-result-copy">${escapeHtml(runResultText(run))}</p>` : ""}
      </div>`;
    }).join("");
  }

  function runConsoleTags(batch) {
    if (!batch) {
      return `<section class="system-regression-run" id="srRunConsole">
      <div class="system-regression-run-head">
        <div class="system-regression-run-id"><label class="system-regression-run-pick"><span>近期批次</span><select id="srRecentBatch">${batchOptionTags(null)}</select></label></div>
      </div>
      <p class="system-regression-empty">跑一批之后，这里用白话显示每条通过或失败。也可以从上面下拉切回今天跑过的批次。</p>
    </section>`;
    }
    const counts = tally(batch);
    const live = isLiveStatus(batch.status);
    const waiting = (batch.runs || []).find((run) => run.status === "waiting_account");
    const current = (batch.runs || []).find((run) => run.status === "running") || waiting;
    const elapsed = batchElapsed(batch);
    const tone = batch.status === "waiting_account" ? "is-waiting" : batch.status === "failed" ? "is-failed" : batch.status === "passed" ? "is-passed" : "";
    const events = [...srState.eventLog].reverse();
    const eventPane = events.map((item) => `<div class="system-regression-event"><time>${escapeHtml(item.time)}</time><kbd>${escapeHtml(item.key)}</kbd><p>${escapeHtml(item.text)}</p></div>`).join("") || `<p class="system-regression-empty">执行开始后会在这里显示进度。</p>`;
    const resultPane = `<div class="system-regression-result-tools">
        <div class="system-regression-result-filters">
          <button type="button" class="${srState.resultFilter === "all" ? "active" : ""}" data-sr-result-filter="all">全部</button>
          <button type="button" class="${srState.resultFilter === "passed" ? "active" : ""}" data-sr-result-filter="passed">通过</button>
          <button type="button" class="${srState.resultFilter === "failed" ? "active" : ""}" data-sr-result-filter="failed">失败</button>
        </div>
        <input id="srResultQuery" value="${escapeHtml(srState.resultQuery)}" placeholder="搜编号或名称" />
      </div>
      <div id="srResultList">${resultListHtml(batch)}</div>`;
    return `<section class="system-regression-run ${tone}" id="srRunConsole">
      <div class="system-regression-run-head">
        <div class="system-regression-run-id"><label class="system-regression-run-pick"><span>近期批次</span><select id="srRecentBatch">${batchOptionTags(batch)}</select></label><span class="system-regression-pill">${escapeHtml(STATUS_LABELS[batch.status] || batch.status)}</span></div>
        <div class="system-regression-run-meta">
          <span><b>${counts.done}</b>/${counts.total}</span>
          <span class="system-regression-clock" data-sr-clock>${fmtClock(elapsed)}</span>
          ${live ? `<button class="btn danger" id="srStopBatch" type="button">停止</button>` : `<button class="btn secondary" id="srRerunFailed" type="button">失败重跑</button>`}
        </div>
      </div>
      ${waiting ? `<div class="system-regression-hold" id="srAccountResume"><strong>退款达到500元，需要部长账号</strong><div class="system-regression-actions"><input id="srResumeUsername" placeholder="账号" value="${escapeHtml(srState.resumeUsername)}" /><input id="srResumePassword" type="password" placeholder="密码" value="${escapeHtml(srState.resumePassword)}" /><button class="btn" id="srResumeSubmit" type="button">继续执行</button></div></div>` : ""}
      <div class="system-regression-run-body">
        <div class="system-regression-meters">
          <div><span>通过</span><b>${counts.passed}</b></div>
          <div><span>失败</span><b>${counts.failed}</b></div>
          <div><span>等待账号</span><b>${counts.waiting}</b></div>
          <div><span>排队</span><b>${counts.queued}</b></div>
        </div>
        <div class="system-regression-seq">${(batch.runs || []).map((run) => `<div class="system-regression-seq-cell is-${escapeHtml(run.status)} ${current && current.id === run.id ? "is-current" : ""}"><kbd>${escapeHtml(run.case_key || "")}</kbd><em>${escapeHtml(caseName(run))}</em><small>${escapeHtml(STATUS_LABELS[run.status] || run.status)}</small></div>`).join("")}</div>
        <div class="system-regression-now">${current ? `当前 <strong>${escapeHtml(current.case_key || "")}</strong> ${escapeHtml(caseName(current))}` : (live ? "等待下一条" : "批次已结束")}</div>
      </div>
      <div class="system-regression-tabs">
        <button class="${srState.resultTab === "events" ? "active" : ""}" data-sr-tab="events" type="button">实时事件 ${srState.eventLog.length}</button>
        <button class="${srState.resultTab === "results" ? "active" : ""}" data-sr-tab="results" type="button">逐条结果 ${counts.done}</button>
      </div>
      <div class="system-regression-pane">${srState.resultTab === "events" ? eventPane : resultPane}</div>
    </section>`;
  }

  function renderPage(options = {}) {
    const active = currentCase();
    const live = hasLiveBatch();
    const saved = capturePageScroll();
    contentEl().innerHTML = `<section class="system-regression-page">
      <div class="system-regression-toolbar">
        <div class="filters"><div class="field compact"><label>回归项目</label><select id="srSuite"><option value="japan">日本站</option></select></div><div class="field compact"><label>业务项目</label><select id="srProject">${optionList(srState.projects, "id", "name", srState.projectId)}</select></div><div class="field compact"><label>执行环境</label><select id="srEnv">${optionList(srState.envs, "id", "env_name", srState.envId)}</select></div><div class="field compact"><label>客户 ID</label><input id="srCustomerId" inputmode="numeric" value="${escapeHtml(srState.customerId)}" placeholder="例如 300001" /></div><div class="field compact"><label>付钱后等多久再对数</label><input id="srLedgerWait" type="number" min="0" value="${escapeHtml(srState.ledgerWait)}" /></div></div>
        <div class="system-regression-actions"><button class="btn secondary" id="srRefreshTickets" type="button">重新拉券和 OPTION</button><button class="btn secondary" id="srSelectVisible" type="button">选择当前分类</button><button class="btn" id="srRunBatch" type="button" ${live ? "disabled" : ""}>${live ? "执行中…" : "批量执行"}</button></div>
      </div>
      <div class="system-regression-scroll">
      <div id="srRunConsoleHost">${runConsoleTags(srState.batch)}</div>
      <div class="system-regression-layout"><nav class="system-regression-categories"><div class="panel-title"><h3>用例分类</h3></div>${categoryTags()}</nav><main class="system-regression-cases">${caseTableTags()}</main>${drawerTags(active)}</div>
      ${newCaseModalTags()}
      </div>
    </section>`;
    bindPage();
    startClock();
    bindCasePaneHeightSync();
    syncCasePaneHeights();
    restorePageScroll(saved, options);
    requestAnimationFrame(() => {
      syncCasePaneHeights();
      restorePageScroll(saved, options);
    });
  }

  function newCaseModalTags() {
    const kind = srState.newKind === "porder" ? "porder" : "order";
    return `<div class="system-regression-modal" id="srNewCaseModal">
      <div class="system-regression-dialog">
        <h3>新建用例</h3>
        <p class="system-regression-how">先选这是<strong>订单</strong>还是<strong>配送单</strong>。两边的钱和券不是一套，选错后面参数全对不上。</p>
        <div class="system-regression-kind-pick">
          <button type="button" class="${kind === "order" ? "active" : ""}" data-sr-new-kind="order"><strong>订单</strong><span>商品货款、国内运费、手续费。优惠券只把手续费变成 0。</span></button>
          <button type="button" class="${kind === "porder" ? "active" : ""}" data-sr-new-kind="porder"><strong>配送单</strong><span>国际运费。代金券按券规则抵扣，跟订单货款无关。</span></button>
        </div>
        <div class="system-regression-grid">
          <div class="field wide" id="srOrderKindExtra" ${kind === "order" ? "" : "hidden"}><label>这条订单要测什么</label>
            <select id="srNewType">
              <option value="payment">一次付清</option>
              <option value="part">分批付款</option>
              <option value="problem">问题产品（先造订单，再处理问题）</option>
            </select>
          </div>
          <p class="system-regression-hint wide" id="srPorderKindExtra" ${kind === "porder" ? "" : "hidden"}>配送单没有商品货款，也没有优惠券。建完只填国际运费和代金券。</p>
          <div class="field wide"><label>用例名称</label><input id="srNewName" placeholder="例如 两番分批付款" /></div>
          <div class="field wide"><label>将得到的编号</label><input id="srNewKeyPreview" readonly /><small class="system-regression-hint">编号按类型自动生成：支付 / 配送 / 流程，后面跟 001、002…</small></div>
        </div>
        <p class="system-regression-hint">编号只增不挤。删掉 002 后，003 还是 003，新建用下一个最大号，不会填回 002。</p>
        <div class="system-regression-actions"><button class="btn secondary" id="srCancelNew" type="button">取消</button><button class="btn" id="srConfirmNew" type="button">新建</button></div>
      </div>
    </div>`;
  }

  async function deleteRegressionCases(items) {
    const rows = [...new Map((items || []).filter(Boolean).map((item) => [item.id, item])).values()];
    if (!rows.length) {
      showToast("先勾选或点开要删的用例");
      return;
    }
    const label = rows.length === 1
      ? `${rows[0].case_key || ""} ${rows[0].name || ""}`.trim()
      : `${rows.length} 条：${rows.map((item) => item.case_key).filter(Boolean).slice(0, 8).join("、")}${rows.length > 8 ? ` 等` : ""}`;
    if (!window.confirm(`确定删除用例 ${label}？`)) return;
    for (const item of rows) {
      await api(`/api/system-regression/cases/${item.id}`, { method: "DELETE" });
      srState.cases = srState.cases.filter((row) => row.id !== item.id);
      srState.selected.delete(item.id);
    }
    srState.categories = [...new Set(srState.cases.map((row) => row.category))];
    if (!srState.cases.some((row) => row.id === srState.activeId)) {
      srState.activeId = visibleCases()[0]?.id || srState.cases[0]?.id || 0;
      srState.drawerTab = isProblemCase(currentCase()) ? "process" : "order";
    }
    showToast("已删除");
    renderPage();
  }

  async function deleteRegressionCase(item) {
    return deleteRegressionCases(item ? [item] : []);
  }

  function nextCustomKey(prefix) {
    const token = `${prefix}-`;
    let max = 0;
    srState.cases.forEach((item) => {
      const key = String(item.case_key || "");
      if (!key.startsWith(token)) return;
      const tail = key.slice(token.length);
      if (/^\d+$/.test(tail)) max = Math.max(max, Number(tail));
    });
    return `${prefix}-${String(max + 1).padStart(3, "0")}`;
  }

  const CREATE_KIND_PREFIX = {
    payment: "支付",
    part: "支付",
    problem: "流程",
    porder: "配送",
  };

  function selectedNewType() {
    if ((document.querySelector("#srNewCaseModal [data-sr-new-kind].active")?.dataset.srNewKind || srState.newKind) === "porder") return "porder";
    return document.querySelector("#srNewType")?.value || "payment";
  }

  function previewNewKey() {
    const type = selectedNewType();
    const prefix = CREATE_KIND_PREFIX[type] || "支付";
    const el = document.querySelector("#srNewKeyPreview");
    if (el) el.value = nextCustomKey(prefix);
  }

  function setNewKind(kind) {
    srState.newKind = kind === "porder" ? "porder" : "order";
    document.querySelectorAll("[data-sr-new-kind]").forEach((button) => button.classList.toggle("active", button.dataset.srNewKind === srState.newKind));
    const orderExtra = document.querySelector("#srOrderKindExtra");
    const porderExtra = document.querySelector("#srPorderKindExtra");
    if (orderExtra) orderExtra.hidden = srState.newKind !== "order";
    if (porderExtra) porderExtra.hidden = srState.newKind !== "porder";
    const name = document.querySelector("#srNewName");
    if (name && !name.value) name.placeholder = srState.newKind === "porder" ? "例如 海运加代金券" : "例如 两番分批付款";
    previewNewKey();
  }

  async function refreshTickets(options = {}) {
    const silent = Boolean(options.silent);
    srState.customerId = String(document.querySelector("#srCustomerId")?.value || srState.customerId || "").trim();
    if (!srState.projectId || !srState.envId) {
      srState.tickets = { coupons: [], vouchers: [], reason: "先选业务项目和执行环境。" };
      srState.membership = emptyMembership();
      srState.options = { rows: [], reason: "先选业务项目和执行环境。" };
      if (!silent) showToast(srState.tickets.reason);
      return srState.tickets;
    }
    if (!/^\d+$/.test(srState.customerId)) {
      srState.tickets = { coupons: [], vouchers: [], reason: "填客户 ID 后才能拉这个账号的券。" };
      srState.membership = emptyMembership();
      srState.options = { rows: [], reason: "填客户 ID 后才能拉 OPTION。" };
      if (!silent) showToast(srState.tickets.reason);
      return srState.tickets;
    }
    const ticketSeq = ++ticketsRequest;
    const optionSeq = ++optionsRequest;
    const body = {
      project_id: Number(srState.projectId),
      env_id: Number(srState.envId),
      customer_id: srState.customerId,
    };
    const ticketTask = api(TICKETS_API, { method: "POST", body }).then((data) => {
      if (ticketSeq !== ticketsRequest) return srState.tickets;
      srState.tickets = {
        coupons: Array.isArray(data.coupons) ? data.coupons : [],
        vouchers: Array.isArray(data.vouchers) ? data.vouchers : [],
        reason: data.reason || "",
      };
      srState.membership = data.membership && typeof data.membership === "object" ? data.membership : emptyMembership();
      preferRealServiceCoupon();
      return srState.tickets;
    }).catch((error) => {
      if (ticketSeq !== ticketsRequest) return srState.tickets;
      srState.tickets = { coupons: [], vouchers: [], reason: error.message || "优惠券列表拉取失败" };
      srState.membership = emptyMembership();
      return srState.tickets;
    });
    const optionTask = api(OPTIONS_API, { method: "POST", body }).then((data) => {
      if (optionSeq !== optionsRequest) return srState.options;
      srState.options = {
        rows: Array.isArray(data.options) ? data.options : [],
        reason: data.reason || "",
      };
      return srState.options;
    }).catch((error) => {
      if (optionSeq !== optionsRequest) return srState.options;
      srState.options = { rows: [], reason: error.message || "OPTION 列表拉取失败" };
      return srState.options;
    });
    await Promise.all([ticketTask, optionTask]);
    if (!silent) {
      const ticketText = srState.tickets.reason || `拉到 ${srState.tickets.coupons.length} 张优惠券、${srState.tickets.vouchers.length} 张代金券`;
      const optionText = srState.options.reason || `拉到 ${srState.options.rows.length} 项 OPTION`;
      showToast(`${ticketText}；${optionText}`);
    }
    return srState.tickets;
  }

  function preferRealServiceCoupon() {
    const realId = srState.tickets.coupons?.[0]?.id;
    if (!realId) return;
    const item = currentCase();
    if (!item) return;
    const parameters = normalizedParameters(item);
    if (parameters.coupon?.selectedId !== SERVICE_COUPON_ID) return;
    parameters.coupon.selectedId = realId;
    parameters.discounts_id = realId;
    parameters.service_discount = true;
    item.parameters = parameters;
  }

  function fieldEl(id) {
    return document.querySelector(id);
  }

  function persistDrawer() {
    const item = currentCase();
    if (!item) return item;
    item.parameters = collectParameters(item);
    const name = fieldEl("#srCaseName");
    if (name) item.name = name.value;
    return item;
  }

  function nextRunnerKind(item, parameters) {
    if (isPorderCase(item) || isProblemCase(item)) return item.runner_kind;
    return parameters.part_pay?.enabled ? "order_part_payment" : "order_payment";
  }

  function refreshMoneyPreview() {
    const item = persistDrawer();
    if (!item) return;
    const parameters = normalizedParameters(item);
    const bill = document.querySelector("#srBill");
    if (bill) bill.outerHTML = billHtml(item, parameters);
    if (!isPorderCase(item)) return;
    const quote = predictFreight(parameters.porder || emptyPorder());
    const volume = fieldEl("#srBoxVolume");
    const charge = fieldEl("#srChargeKg");
    const predicted = fieldEl("#srPredictedFreight");
    if (volume) volume.value = quote.volume;
    if (charge) charge.value = yen(quote.chargeKg);
    if (predicted && !parameters.porder.price_manual) predicted.value = yen(porderTotals(parameters).logistics);
  }

  function collectLiveOptions(row, itemIndex) {
    const catalog = srState.options.rows || [];
    if (!catalog.length) return null;
    return catalog.flatMap((live) => {
      const key = optionKey(live);
      const box = row.querySelector(`[data-live-option="${itemIndex}:${key}"]`);
      if (!box?.checked) return [];
      const num = Number(row.querySelector(`[data-live-option-num="${itemIndex}:${key}"]`)?.value || 1);
      return [{
        id: live.id || key,
        key,
        name: live.name || live.label || key,
        price_type: Number(live.price_type) === 1 ? 1 : 0,
        price: live.price || "0",
        num: Number.isFinite(num) && num > 0 ? num : 1,
        checked: true,
      }];
    });
  }

  function collectItems() {
    const current = currentCase();
    const fallbackItems = current ? (normalizedParameters(current).items || []) : [];
    return [...document.querySelectorAll("[data-item-row]")].map((row, index) => {
      const liveOptions = collectLiveOptions(row, Number(row.dataset.itemRow ?? index));
      return {
        sorting: Number(row.querySelector("[data-item-sorting]").value || 1),
        quantity: Number(row.querySelector("[data-item-quantity]").value || 1),
        offer_price: { value: row.querySelector("[data-item-price]").value || "0", currency: "CNY" },
        offer_freight: { value: row.querySelector("[data-item-freight]").value || "0", currency: "CNY" },
        options: liveOptions || fallbackItems[index]?.options || [],
      };
    });
  }

  function collectParameters(item) {
    const parameters = normalizedParameters(item);
    const wait = fieldEl("#srLedgerWait")?.value;
    if (wait != null && wait !== "") parameters.ledger_wait_seconds = Number(wait);
    if (fieldEl("#srPaymentMode")) parameters.payment_mode = fieldEl("#srPaymentMode").value || "balance";
    if (fieldEl("#srAmountStep")) parameters.amount_step = fieldEl("#srAmountStep").value || parameters.amount_step || "1";
    if (fieldEl("#srItemCount")) {
      parameters.order = {
        item_count: Number(fieldEl("#srItemCount").value || 1),
        default_quantity: Number(fieldEl("#srDefaultQuantity")?.value || 1),
        default_offer_price: { value: fieldEl("#srDefaultPrice")?.value || "10", currency: "CNY" },
        default_freight: { value: fieldEl("#srDefaultFreight")?.value || "3", currency: "CNY" },
        other_fee_name: fieldEl("#srOtherFeeName")?.value || "",
        other_fee_amount: { value: fieldEl("#srOtherFeeAmount")?.value || "0", currency: "CNY" },
      };
      if (document.querySelector("[data-item-row]")) parameters.items = collectItems();
    }
    if (fieldEl("#srPartEnabled")) {
      const enabled = fieldEl("#srPartEnabled").value === "1";
      const timing = { ...(parameters.part_pay.fee_timing || {}) };
      FEE_FIELDS.forEach(([key]) => {
        const el = document.querySelector(`[data-part-timing="${key}"]`);
        if (el) timing[key] = el.value || "first";
      });
      parameters.part_pay = {
        enabled,
        percent: Number(fieldEl("#srPartPercent")?.value ?? parameters.part_pay.percent ?? 50),
        tail_node: fieldEl("#srPartTailNode")?.value || parameters.part_pay.tail_node || "before_shelf",
        tail_partial: (fieldEl("#srPartTailPartial")?.value || "0") === "1",
        tail_sortings: fieldEl("#srPartSortings")?.value || parameters.part_pay.tail_sortings || "",
        fee_timing: timing,
      };
      parameters.payment_plan = enabled ? "part" : "full";
    }
    if (fieldEl("#srCouponId")) {
      const selectedId = fieldEl("#srCouponId").value || "";
      parameters.coupon = { selectedId };
      parameters.service_discount = Boolean(selectedId);
      parameters.discounts_id = selectedId && selectedId !== SERVICE_COUPON_ID ? selectedId : "";
    }
    if (fieldEl("#srBoxCount")) {
      const p = parameters.porder || emptyPorder();
      parameters.porder = {
        ...p,
        sku_count: Number(fieldEl("#srPorderSkuCount")?.value || 1),
        send_num: Number(fieldEl("#srPorderSendNum")?.value || 1),
        box_count: Number(fieldEl("#srBoxCount").value || 1),
        box_length: Number(fieldEl("#srBoxLength")?.value || 58),
        box_width: Number(fieldEl("#srBoxWidth")?.value || 51),
        box_height: Number(fieldEl("#srBoxHeight")?.value || 50),
        box_weight: Number(fieldEl("#srBoxWeight")?.value || 10),
        logistics: fieldEl("#srLogistics")?.value || "25",
        price_manual: Boolean(fieldEl("#srPriceManual")?.checked),
        logistics_price: { value: fieldEl("#srLogisticsPrice")?.value || p.logistics_price?.value || "0", currency: "CNY" },
        extra_name: fieldEl("#srPorderExtraName")?.value || "",
        extra_fee: { value: fieldEl("#srPorderExtraFee")?.value || "0", currency: "CNY" },
        voucher: { selectedId: fieldEl("#srVoucherId")?.value || "" },
      };
    }
    if (fieldEl("#srProblemType")) {
      const problem = parameters.problem_goods || {};
      parameters.problem_goods = {
        ...problem,
        problem_type: Number(fieldEl("#srProblemType").value),
        problem_num: Number(fieldEl("#srProblemNum").value),
        problem_description: fieldEl("#srProblemDescription").value || "系统回归问题产品",
        translation_content: fieldEl("#srTranslationContent").value || "システム回帰テスト",
        pre_num: Number(fieldEl("#srPreNum").value),
        pre_price: { value: fieldEl("#srPrePrice").value || "0", currency: "CNY" },
        pre_freight: { value: fieldEl("#srPreFreight").value || "0", currency: "CNY" },
        client_deal_choice: fieldEl("#srClientDeal").value,
        client_deal_other: fieldEl("#srClientOther")?.value || "",
        service_deal_suggest: Number(fieldEl("#srServiceSuggest").value),
        option_deal_suggest: Number(fieldEl("#srOptionSuggest").value),
        option_new: problem.option_new || [],
        g_deal_type: fieldEl("#srPurchaseDeal")?.value || problem.g_deal_type || "仅退款",
        business_decision: fieldEl("#srBusinessDecision").value || "系统回归自动处理",
        purchase_remark: fieldEl("#srPurchaseRemark")?.value || problem.purchase_remark || "系统回归",
        confirm_distribution: fieldEl("#srConfirmDistribution") ? fieldEl("#srConfirmDistribution").checked : problem.confirm_distribution !== false,
      };
    }
    return parameters;
  }

  function freezeCaseParameters(caseIds) {
    persistDrawer();
    const wait = Number(fieldEl("#srLedgerWait")?.value || srState.ledgerWait || 30);
    return Object.fromEntries(caseIds.map((caseId) => {
      const item = srState.cases.find((candidate) => candidate.id === caseId);
      const params = item ? structuredClone(item.parameters || {}) : {};
      params.ledger_wait_seconds = wait;
      return [String(caseId), params];
    }));
  }

  async function execute(caseIds) {
    if (!caseIds.length) return showToast("请至少选择一条用例");
    if (!srState.projectId || !srState.envId) return showToast("请选择业务项目和执行环境");
    srState.customerId = String(document.querySelector("#srCustomerId")?.value || srState.customerId || "").trim();
    if (!/^\d+$/.test(srState.customerId)) return showToast("客户 ID 只能填写数字");
    srState.ledgerWait = String(document.querySelector("#srLedgerWait")?.value || srState.ledgerWait || "30");
    localStorage.setItem("systemRegressionCustomerId", srState.customerId);
    localStorage.setItem("systemRegressionLedgerWait", srState.ledgerWait);
    if (hasLiveBatch()) return showToast("当前批次还在执行");
    srState.batch = await api("/api/system-regression/batches", { method: "POST", body: { suite_key: "japan", case_ids: caseIds, project_id: Number(srState.projectId), env_id: Number(srState.envId), context: { variables: { customer_id: srState.customerId, ledger_wait_seconds: Number(srState.ledgerWait || 30) }, case_parameters: freezeCaseParameters(caseIds) } } });
    srState.batchStartedAt = Date.now();
    srState.resultTab = "events";
    srState.expandedRunId = 0;
    srState.resultFilter = "all";
    srState.resultQuery = "";
    srState.eventLog = [];
    pushEvent("", `批次 ${srState.batch.batch_no} 已创建，共 ${caseIds.length} 条`);
    upsertRecentBatch(srState.batch);
    persistActiveBatch(srState.batch);
    renderPage();
    pollBatch(srState.batch.id);
  }

  function patchRunConsole() {
    if (!isOnRegressionPage()) return;
    const host = document.querySelector("#srRunConsoleHost");
    if (!host) {
      if (srState.batch) renderPage();
      return;
    }
    if (srState.runConsoleScrollBusy) {
      srState.pendingRunConsolePatch = true;
      return;
    }
    const saved = captureRunConsoleScroll();
    host.innerHTML = runConsoleTags(srState.batch);
    bindRunConsole();
    restoreRunConsoleScroll(saved);
    document.querySelectorAll("[data-sr-run-status]").forEach((cell) => {
      const id = Number(cell.dataset.srRunStatus);
      const item = srState.cases.find((row) => row.id === id);
      const run = (srState.batch?.runs || []).find((row) => row.case_id === id);
      cell.textContent = run ? (STATUS_LABELS[run.status] || run.status) : `${item?.enabled ? "启用" : "停用"}${item?.user_modified ? " · 已修改" : ""}`;
    });
    const batchBtn = document.querySelector("#srRunBatch");
    if (batchBtn) {
      const live = hasLiveBatch();
      batchBtn.disabled = Boolean(live);
      batchBtn.textContent = live ? "执行中…" : "批量执行";
    }
  }

  async function pollBatch(batchId) {
    window.clearTimeout(srState.pollTimer);
    srState.pollId = batchId;
    if (!batchId) return;
    try {
      const previous = srState.batch;
      const batch = await api(`/api/system-regression/batches/${batchId}`);
      if (srState.pollId !== batchId) return;
      upsertRecentBatch(batch);
      if (srState.batch?.id === batchId) {
        appendRunEvents(previous, batch);
        srState.batch = batch;
        persistActiveBatch(batch);
        if (isOnRegressionPage()) {
          patchRunConsole();
          const waiting = (batch.runs || []).find((run) => run.status === "waiting_account");
          if (waiting) openAccountResume(waiting);
        }
      }
      if (isLiveStatus(batch.status)) {
        srState.pollTimer = window.setTimeout(() => pollBatch(batchId), 2000);
      }
    } catch (error) {
      if (srState.pollId !== batchId) return;
      if (String(error?.message || "").includes("不存在")) return;
      srState.pollTimer = window.setTimeout(() => pollBatch(batchId), 4000);
    }
  }

  async function stopActiveBatch() {
    if (!srState.batch?.id || !isLiveStatus(srState.batch.status)) return;
    srState.batch = await api(`/api/system-regression/batches/${srState.batch.id}/stop`, { method: "POST" });
    persistActiveBatch(srState.batch);
    pushEvent("", "已停止批次");
    showToast("已停止批次");
    pollBatch(srState.batch.id);
  }

  async function rerunFailedRuns() {
    const failed = (srState.batch?.runs || []).filter((run) => ["failed", "stopped"].includes(run.status));
    if (!failed.length) return showToast("没有可重跑的失败/停止用例");
    await Promise.all(failed.map((run) => api(`/api/system-regression/runs/${run.id}/rerun`, { method: "POST" })));
    srState.resultTab = "events";
    pushEvent("", `重跑 ${failed.length} 条失败/停止用例`);
    showToast("开始重跑");
    pollBatch(srState.batch.id);
  }

  function openAccountResume(run) {
    if (!isOnRegressionPage()) return;
    if (document.querySelector("#srAccountResume")) return;
    const wrapper = document.createElement("div");
    wrapper.id = "srAccountResume";
    wrapper.className = "system-regression-status";
    wrapper.innerHTML = `<strong>退款达到500元，需要部长账号</strong><div class="system-regression-actions"><input id="srResumeUsername" placeholder="账号" /><input id="srResumePassword" type="password" placeholder="密码" /><button class="btn" id="srResumeSubmit" type="button">继续执行</button></div>`;
    document.querySelector(".system-regression-page")?.prepend(wrapper);
    bindAccountResume(run);
  }

  function bindAccountResume(run) {
    const username = document.querySelector("#srResumeUsername");
    const password = document.querySelector("#srResumePassword");
    username?.addEventListener("input", (event) => { srState.resumeUsername = event.target.value; });
    password?.addEventListener("input", (event) => { srState.resumePassword = event.target.value; });
    document.querySelector("#srResumeSubmit")?.addEventListener("click", async () => {
      const name = document.querySelector("#srResumeUsername")?.value || "";
      const pass = document.querySelector("#srResumePassword")?.value || "";
      if (!name.trim() || !pass.trim()) return showToast("请填写账号和密码");
      await api(`/api/system-regression/runs/${run.id}/resume-account`, { method: "POST", body: { username: name, password: pass } });
      document.querySelector("#srAccountResume")?.remove();
      showToast("已继续执行");
      pollBatch(srState.batch.id);
    });
  }

  function bindResultExpand() {
    document.querySelectorAll("[data-sr-expand]").forEach((button) => button.addEventListener("click", () => {
      const id = Number(button.dataset.srExpand);
      srState.expandedRunId = srState.expandedRunId === id ? 0 : id;
      srState.resultTab = "results";
      const list = document.querySelector("#srResultList");
      if (list) {
        list.innerHTML = resultListHtml(srState.batch);
        bindResultExpand();
        return;
      }
      patchRunConsole();
    }));
  }

  async function refreshRecentBatches() {
    try {
      const data = await api(`/api/system-regression/batches?suite_key=${encodeURIComponent(srState.suiteKey || "japan")}&limit=20`);
      srState.recentBatches = Array.isArray(data.items) ? data.items : [];
    } catch {
      srState.recentBatches = srState.recentBatches || [];
    }
    if (srState.batch) upsertRecentBatch(srState.batch);
  }

  async function openBatch(batchId) {
    const id = Number(batchId);
    if (!id) return;
    if (srState.batch?.id === id && Array.isArray(srState.batch.runs)) return;
    try {
      const batch = await api(`/api/system-regression/batches/${id}`);
      srState.batch = batch;
      srState.batchStartedAt = batchStartedAt(batch);
      srState.expandedRunId = 0;
      srState.resultFilter = "all";
      srState.resultQuery = "";
      upsertRecentBatch(batch);
      persistActiveBatch(batch);
      if (isOnRegressionPage()) patchRunConsole();
      if (isLiveStatus(batch.status) && srState.pollId !== batch.id) pollBatch(batch.id);
    } catch (error) {
      showToast(error.message || "批次加载失败");
    }
  }

  function bindRunConsole() {
    bindRunConsoleScrollGuard();
    document.querySelector("#srStopBatch")?.addEventListener("click", stopActiveBatch);
    document.querySelector("#srRerunFailed")?.addEventListener("click", rerunFailedRuns);
    document.querySelector("#srRecentBatch")?.addEventListener("change", (event) => {
      openBatch(event.target.value);
    });
    document.querySelectorAll("[data-sr-tab]").forEach((button) => button.addEventListener("click", () => {
      srState.resultTab = button.dataset.srTab;
      patchRunConsole();
    }));
    document.querySelectorAll("[data-sr-result-filter]").forEach((button) => button.addEventListener("click", () => {
      srState.resultFilter = button.dataset.srResultFilter;
      patchRunConsole();
    }));
    document.querySelector("#srResultQuery")?.addEventListener("input", (event) => {
      srState.resultQuery = event.target.value;
      const list = document.querySelector("#srResultList");
      if (!list) return;
      list.innerHTML = resultListHtml(srState.batch);
      bindResultExpand();
    });
    bindResultExpand();
    const waiting = (srState.batch?.runs || []).find((run) => run.status === "waiting_account");
    if (waiting) bindAccountResume(waiting);
  }

  function bindPage() {
    document.querySelector("#srProject")?.addEventListener("change", async (event) => {
      persistDrawer();
      srState.projectId = event.target.value;
      localStorage.setItem("systemRegressionProjectId", srState.projectId);
      srState.envs = await api(`/api/envs?project_id=${encodeURIComponent(srState.projectId)}`);
      srState.envId = String(srState.envs[0]?.id || "");
      await refreshTickets({ silent: true });
      renderPage();
    });
    document.querySelector("#srEnv")?.addEventListener("change", async (event) => {
      srState.envId = event.target.value;
      localStorage.setItem("systemRegressionEnvId", srState.envId);
      persistDrawer();
      await refreshTickets({ silent: true });
      renderPage();
    });
    document.querySelector("#srCustomerId")?.addEventListener("input", (event) => { srState.customerId = event.target.value.trim(); });
    document.querySelector("#srCustomerId")?.addEventListener("change", async (event) => {
      srState.customerId = event.target.value.trim();
      localStorage.setItem("systemRegressionCustomerId", srState.customerId);
      persistDrawer();
      await refreshTickets({ silent: true });
      renderPage();
    });
    document.querySelector("#srLedgerWait")?.addEventListener("input", (event) => {
      srState.ledgerWait = event.target.value;
      localStorage.setItem("systemRegressionLedgerWait", srState.ledgerWait);
    });
    document.querySelector("#srRefreshTickets")?.addEventListener("click", async () => {
      persistDrawer();
      await refreshTickets();
      renderPage();
    });
    document.querySelectorAll("[data-sr-category]").forEach((button) => button.addEventListener("click", () => {
      persistDrawer();
      srState.category = button.dataset.srCategory;
      const visible = visibleCases();
      if (!visible.some((item) => item.id === srState.activeId)) {
        srState.activeId = visible[0]?.id || srState.activeId;
        srState.drawerTab = isProblemCase(currentCase()) ? "process" : "order";
      }
      renderPage();
    }));
    document.querySelectorAll("[data-sr-open]").forEach((button) => button.addEventListener("click", () => {
      persistDrawer();
      srState.activeId = Number(button.dataset.srOpen);
      srState.drawerTab = isProblemCase(currentCase()) ? "process" : "order";
      renderPage({ resetDrawer: true });
    }));
    document.querySelectorAll("[data-sr-delete]").forEach((button) => button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      persistDrawer();
      deleteRegressionCase(srState.cases.find((row) => row.id === Number(button.dataset.srDelete)));
    }));
    document.querySelectorAll("[data-sr-drawer-tab]").forEach((button) => button.addEventListener("click", () => {
      persistDrawer();
      srState.drawerTab = button.dataset.srDrawerTab;
      renderPage();
    }));
    const selectAll = document.querySelector("#srSelectAll");
    const rows = visibleCases();
    const selectedCount = rows.filter((item) => srState.selected.has(item.id)).length;
    if (selectAll) {
      selectAll.checked = rows.length > 0 && selectedCount === rows.length;
      selectAll.indeterminate = selectedCount > 0 && selectedCount < rows.length;
    }
    document.querySelectorAll("[data-sr-select]").forEach((box) => box.addEventListener("change", () => {
      const id = Number(box.dataset.srSelect);
      box.checked ? srState.selected.add(id) : srState.selected.delete(id);
      persistDrawer();
      renderPage();
    }));
    document.querySelector("#srSelectAll")?.addEventListener("change", (event) => {
      rows.forEach((item) => event.target.checked ? srState.selected.add(item.id) : srState.selected.delete(item.id));
      persistDrawer();
      renderPage();
    });
    document.querySelector("#srSelectVisible")?.addEventListener("click", () => { rows.forEach((item) => srState.selected.add(item.id)); persistDrawer(); renderPage(); });
    document.querySelector("#srRunBatch")?.addEventListener("click", () => execute([...srState.selected]));
    document.querySelector("#srRunOne")?.addEventListener("click", () => execute([currentCase().id]));
    document.querySelector("#srAddItem")?.addEventListener("click", () => {
      const item = persistDrawer();
      if (!item) return;
      const parameters = normalizedParameters(item);
      parameters.items.push({
        sorting: parameters.items.length + 1,
        quantity: parameters.order.default_quantity || 1,
        offer_price: parameters.order.default_offer_price || { value: 10, currency: "CNY" },
        offer_freight: parameters.order.default_freight || { value: 0, currency: "CNY" },
        options: [],
      });
      item.parameters = parameters;
      renderPage();
    });
    document.querySelectorAll("[data-remove-item]").forEach((button) => button.addEventListener("click", () => {
      const item = persistDrawer();
      if (!item) return;
      const parameters = normalizedParameters(item);
      parameters.items.splice(Number(button.dataset.removeItem), 1);
      item.parameters = parameters;
      renderPage();
    }));
    document.querySelector("#srSaveCase")?.addEventListener("click", async () => {
      const item = persistDrawer();
      if (!item) return;
      const parameters = collectParameters(item);
      const updated = await api(`/api/system-regression/cases/${item.id}`, { method: "PATCH", body: { name: fieldEl("#srCaseName").value, parameters, runner_kind: nextRunnerKind(item, parameters) } });
      Object.assign(item, updated);
      showToast("参数已保存");
      renderPage();
    });
    document.querySelector("#srCopyCase")?.addEventListener("click", async () => {
      persistDrawer();
      const copied = await api(`/api/system-regression/cases/${currentCase().id}/copy`, { method: "POST" });
      srState.cases.push(copied);
      srState.activeId = copied.id;
      renderPage();
    });
    document.querySelector("#srResetCase")?.addEventListener("click", async () => {
      const reset = await api(`/api/system-regression/cases/${currentCase().id}/reset`, { method: "POST" });
      Object.assign(currentCase(), reset);
      renderPage();
    });
    document.querySelector("#srDeleteVisible")?.addEventListener("click", () => {
      persistDrawer();
      const selected = visibleCases().filter((item) => srState.selected.has(item.id));
      deleteRegressionCases(selected.length ? selected : [currentCase()]);
    });
    document.querySelector("#srNewCase")?.addEventListener("click", () => {
      persistDrawer();
      const type = document.querySelector("#srNewType");
      const name = document.querySelector("#srNewName");
      if (name) name.value = "";
      if (type) type.value = String(srState.category).startsWith("problem") ? "problem" : "payment";
      setNewKind(srState.category === "porder" ? "porder" : "order");
      document.querySelector("#srNewCaseModal")?.classList.add("show");
    });
    document.querySelector("#srCancelNew")?.addEventListener("click", () => document.querySelector("#srNewCaseModal")?.classList.remove("show"));
    document.querySelector("#srNewCaseModal")?.addEventListener("click", (event) => {
      if (event.target.id === "srNewCaseModal") event.target.classList.remove("show");
    });
    document.querySelectorAll("[data-sr-new-kind]").forEach((button) => button.addEventListener("click", () => setNewKind(button.dataset.srNewKind)));
    document.querySelector("#srNewType")?.addEventListener("change", previewNewKey);
    document.querySelector("#srConfirmNew")?.addEventListener("click", async () => {
      const created = await api("/api/system-regression/cases", { method: "POST", body: { kind: selectedNewType(), name: document.querySelector("#srNewName")?.value || "" } });
      srState.cases.push(created);
      srState.categories = [...new Set(srState.cases.map((row) => row.category))];
      srState.activeId = created.id;
      srState.category = created.category;
      srState.drawerTab = isProblemCase(created) ? "process" : "order";
      document.querySelector("#srNewCaseModal")?.classList.remove("show");
      showToast(`已新建 ${created.case_key}`);
      renderPage();
    });
    const drawer = document.querySelector(".system-regression-drawer");
    drawer?.addEventListener("change", (event) => {
      const id = event.target.id;
      if (event.target.matches("[data-live-option]")) {
        const num = document.querySelector(`[data-live-option-num="${event.target.getAttribute("data-live-option")}"]`);
        if (num) num.disabled = !event.target.checked;
      }
      if (id === "srPartEnabled" || id === "srPriceManual" || id === "srClientDeal" || id === "srCouponId" || id === "srVoucherId") {
        persistDrawer();
        renderPage();
        return;
      }
      refreshMoneyPreview();
    });
    drawer?.addEventListener("input", (event) => {
      if (event.target.id === "srCaseName") return;
      if (["srPartEnabled", "srPriceManual", "srClientDeal", "srCouponId", "srVoucherId"].includes(event.target.id)) return;
      refreshMoneyPreview();
    });
    previewNewKey();
    bindRunConsole();
  }

  async function renderSystemRegression() {
    const [catalog, projects, recent] = await Promise.all([
      api("/api/system-regression/suites/japan/cases"),
      getProjects(),
      api(`/api/system-regression/batches?suite_key=${encodeURIComponent(srState.suiteKey || "japan")}&limit=20`).catch(() => ({ items: [] })),
    ]);
    srState.cases = catalog.cases;
    srState.problemTypes = Array.isArray(catalog.problem_types) ? catalog.problem_types : [];
    srState.categories = [...new Set(srState.cases.map((item) => item.category))];
    srState.projects = projects;
    srState.projectId = srState.projectId || String(projects[0]?.id || "");
    srState.envs = srState.projectId ? await api(`/api/envs?project_id=${encodeURIComponent(srState.projectId)}`) : [];
    srState.envId = srState.envId || String(srState.envs[0]?.id || "");
    srState.activeId = srState.activeId || srState.cases[0]?.id || 0;
    srState.recentBatches = Array.isArray(recent.items) ? recent.items : [];
    const stored = readActiveBatch();
    if (stored?.id && !srState.batch) {
      try {
        srState.batch = await api(`/api/system-regression/batches/${stored.id}`);
        srState.batchStartedAt = stored.started_at || batchStartedAt(srState.batch);
        upsertRecentBatch(srState.batch);
        persistActiveBatch(srState.batch);
        if (isLiveStatus(srState.batch.status)) pollBatch(srState.batch.id);
      } catch {
        srState.batch = null;
      }
    } else if (srState.batch?.id && isLiveStatus(srState.batch.status) && srState.pollId !== srState.batch.id) {
      upsertRecentBatch(srState.batch);
      pollBatch(srState.batch.id);
    } else if (srState.batch) {
      upsertRecentBatch(srState.batch);
    }
    if (!srState.batch && srState.recentBatches[0]?.id) {
      try {
        srState.batch = await api(`/api/system-regression/batches/${srState.recentBatches[0].id}`);
        srState.batchStartedAt = batchStartedAt(srState.batch);
        upsertRecentBatch(srState.batch);
        persistActiveBatch(srState.batch);
        if (isLiveStatus(srState.batch.status)) pollBatch(srState.batch.id);
      } catch {
        srState.batch = null;
      }
    }
    if (srState.batch && !srState.eventLog.length && !isLiveStatus(srState.batch.status)) {
      srState.resultTab = "results";
    }
    renderPage();
    await refreshTickets({ silent: true });
    if (isOnRegressionPage()) renderPage();
  }

  window.renderSystemRegression = renderSystemRegression;
})();
