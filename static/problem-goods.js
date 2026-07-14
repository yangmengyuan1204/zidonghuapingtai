(function () {
  const PROBLEM_TYPES = [
    [1, "单价变动"], [2, "运费变动"], [3, "少货"], [4, "不良"], [5, "不良且少货"],
    [6, "option变动"], [7, "数量多了"], [8, "其他"], [9, "客户原因"], [10, "不良直接上架"],
  ];
  const PURCHASE_TYPES = ["退货退款", "换货", "丢货重拍", "少货补买", "其他", "仅退款"];
  const STATUS_NAMES = { "-1": "问题商品取消", 1: "待翻译", 2: "待客户处理", 3: "待业务决策", 4: "待采购处理", 5: "待配货确认", 6: "已完成" };
  const OPTION_CATALOG_CACHE = new Map();

  function parseJson(value, fallback = []) {
    if (Array.isArray(value)) return value;
    if (!value) return fallback;
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : fallback;
    } catch {
      return fallback;
    }
  }

  function suffixCustomerId(orderSn) {
    return String(orderSn || "").trim().match(/-(\d+)$/)?.[1] || "";
  }

  function numeric(value, fallback = "0") {
    return value === null || value === undefined || value === "" ? fallback : String(value);
  }

  function optionRows(value) {
    return parseJson(value, []).map((item) => ({ ...item, checked: item.checked !== false }));
  }

  function accountOptions(accounts, selected, escape) {
    return [
      `<option value="">使用环境默认后台账号</option>`,
      ...accounts.map((item) => `<option value="${escape(item.id)}" ${String(item.id) === String(selected || "") ? "selected" : ""}>${escape(item.profile_name)}</option>`),
    ].join("");
  }

  function stageVisible(status, stage) {
    if (status <= 0) return true;
    return status <= stage;
  }

  function problemGoodsUi() {
    const state = {
      flow: null,
      deps: null,
      accounts: [],
      inspection: null,
      selected: null,
      selectedKind: "",
      options: [],
      optionCatalog: [],
      optionCatalogLoading: false,
      optionCatalogError: "",
      optionCatalogContext: "",
      optionCatalogRequestId: 0,
      optionFilter: "",
      optionFilterTimer: null,
      resumeVariables: null,
      search: {},
      lastAccountId: "",
      searchController: null,
      searchRequestId: 0,
    };

    const d = () => state.deps;
    const escape = (value) => d().escapeHtml(value);
    const modal = () => d().modalEl;

    function baseRequest(variables) {
      return {
        project_id: state.flow.projectId ? Number(state.flow.projectId) : null,
        env_id: state.flow.envId ? Number(state.flow.envId) : null,
        variables,
      };
    }

    function closeButton() {
      document.querySelector("#closeProblemGoods")?.addEventListener("click", () => {
        state.searchController?.abort();
        window.clearTimeout(state.optionFilterTimer);
        modal().close();
      });
    }

    function renderSearch() {
      let defaults = {};
      try { defaults = JSON.parse(state.flow.variables || "{}"); } catch { defaults = {}; }
      const search = state.search || {};
      modal().innerHTML = `
        <div class="modal-head">
          <h3>执行 ${escape(state.flow.name || "日本站问题产品处理")}</h3>
          <button class="btn secondary" id="closeProblemGoods" type="button">关闭</button>
        </div>
        <div class="modal-body">
          <div class="form-grid">
            <div class="field"><label>订单号</label><input id="pgOrderSn" value="${escape(search.order_sn || defaults.order_sn || "")}" placeholder="例如 2026071311333811-300001" /></div>
            <div class="field"><label>客户ID</label><input id="pgCustomerId" value="${escape(search.customer_id || defaults.customer_id || "")}" placeholder="可由订单号自动带出" /></div>
            <div class="field"><label>后台执行账号</label><select id="pgAdminAccount">${accountOptions(state.accounts, search.backend_account_profile_id || defaults.backend_account_profile_id, escape)}</select></div>
          </div>
          <p class="progress-note">查询只读取订单和问题产品数据，不会修改金额或状态。</p>
          <div id="pgSearchResult"></div>
        </div>
        <div class="modal-foot"><span></span><button class="btn" id="pgSearch" type="button">查询订单</button></div>
      `;
      if (!modal().open) modal().showModal();
      closeButton();
      const orderInput = document.querySelector("#pgOrderSn");
      const customerInput = document.querySelector("#pgCustomerId");
      const syncCustomer = () => {
        const parsed = suffixCustomerId(orderInput.value);
        if (parsed && !customerInput.value.trim()) customerInput.value = parsed;
      };
      orderInput.addEventListener("blur", syncCustomer);
      document.querySelector("#pgSearch").addEventListener("click", queryOrder);
    }

    async function queryOrder() {
      const orderSn = document.querySelector("#pgOrderSn")?.value.trim() || "";
      const parsedCustomerId = suffixCustomerId(orderSn);
      const customerEl = document.querySelector("#pgCustomerId");
      const customerId = customerEl?.value.trim() || parsedCustomerId;
      if (!orderSn) return d().showToast("请输入订单号");
      if (!parsedCustomerId) return d().showToast("订单号格式有误，无法解析客户ID");
      if (customerId !== parsedCustomerId) return d().showToast("客户ID与订单号后缀不一致");
      if (customerEl) customerEl.value = customerId;
      state.search = {
        order_sn: orderSn,
        customer_id: customerId,
        backend_account_profile_id: document.querySelector("#pgAdminAccount")?.value || "",
      };
      state.lastAccountId = state.search.backend_account_profile_id;
      const target = document.querySelector("#pgSearchResult");
      const queryButton = document.querySelector("#pgSearch");
      state.searchController?.abort();
      const controller = new AbortController();
      const requestId = ++state.searchRequestId;
      state.searchController = controller;
      target.innerHTML = `<div class="empty">正在查询订单和问题产品...</div>`;
      if (queryButton) queryButton.disabled = true;
      try {
        const result = await d().api("/api/data-scripts/problem-goods/inspect", {
          method: "POST",
          signal: controller.signal,
          body: baseRequest({
            order_sn: orderSn,
            customer_id: customerId,
            backend_account_profile_id: document.querySelector("#pgAdminAccount")?.value || "",
          }),
        });
        if (requestId !== state.searchRequestId) return;
        state.inspection = result;
        state.selected = null;
        state.selectedKind = "";
        renderInspection();
      } catch (error) {
        if (error?.name === "AbortError" || requestId !== state.searchRequestId) return;
        target.innerHTML = `<div class="empty">${escape(error.message)}</div>`;
      } finally {
        if (requestId === state.searchRequestId && queryButton) queryButton.disabled = false;
      }
    }

    function renderInspection() {
      const target = document.querySelector("#pgSearchResult");
      const items = state.inspection?.items || [];
      const candidates = state.inspection?.order_candidates || [];
      const activePurchases = new Set(items.filter((item) => Number(item.status) > 0 && Number(item.status) < 5).map((item) => String(item.order_purchase_id)));
      const itemRows = items.length ? items.map((item) => `
        <tr>
          <td><input type="radio" name="pgSelection" data-kind="problem" value="${escape(item.problem_goods_id)}" /></td>
          <td>#${escape(item.problem_goods_id)}</td><td>${escape(item.sorting || "-")}</td>
          <td>${escape(item.type_name || PROBLEM_TYPES.find(([id]) => Number(id) === Number(item.type))?.[1] || item.type || "-")}</td>
          <td>${escape(item.status_name || STATUS_NAMES[item.status] || item.status)}</td>
          <td>${escape(item.possible_num ?? item.pre_num ?? "-")}</td>
        </tr>`).join("") : `<tr><td colspan="6">没有问题产品记录</td></tr>`;
      const candidateRows = candidates.length ? candidates.map((item) => {
        const activeBlocked = activePurchases.has(String(item.order_purchase_id));
        const blocked = activeBlocked || item.can_submit === false;
        return `<tr>
          <td><input type="radio" name="pgSelection" data-kind="candidate" value="${escape(item.order_purchase_id)}" ${blocked ? "disabled" : ""} /></td>
          <td>${escape(item.sorting || "-")}</td><td>${escape(item.purchase_no || "-")}</td>
          <td>${escape(item.max_submit_num ?? "-")}</td><td>${escape(item.storage_num ?? "-")}</td>
          <td>${activeBlocked ? "已有处理中问题产品" : blocked ? "没有未上架数量" : "可提出"}</td>
        </tr>`;
      }).join("") : `<tr><td colspan="6">没有可用采购记录</td></tr>`;
      target.innerHTML = `
        <details class="functional-requirement" open><summary>已有问题产品</summary>
          <div class="table-wrap"><table><thead><tr><th>选择</th><th>ID</th><th>番号</th><th>类型</th><th>状态</th><th>当前数量</th></tr></thead><tbody>${itemRows}</tbody></table></div>
        </details>
        <details class="functional-requirement"><summary>创建新问题产品</summary>
          <div class="table-wrap"><table><thead><tr><th>选择</th><th>番号</th><th>交易号</th><th>可提出数</th><th>已上架数</th><th>状态</th></tr></thead><tbody>${candidateRows}</tbody></table></div>
        </details>
        <div class="actions" style="margin-top:12px"><button class="btn" id="pgConfigure" type="button" disabled>填写处理内容</button></div>
      `;
      document.querySelectorAll("input[name='pgSelection']").forEach((radio) => {
        radio.addEventListener("change", () => {
          state.selectedKind = radio.dataset.kind;
          state.selected = state.selectedKind === "problem"
            ? items.find((item) => String(item.problem_goods_id) === radio.value)
            : candidates.find((item) => String(item.order_purchase_id) === radio.value);
          document.querySelector("#pgConfigure").disabled = !state.selected;
        });
      });
      document.querySelector("#pgConfigure")?.addEventListener("click", renderProcessForm);
    }

    function typeOptions(selected) {
      return PROBLEM_TYPES.map(([value, label]) => `<option value="${value}" ${Number(value) === Number(selected) ? "selected" : ""}>${escape(label)}</option>`).join("");
    }

    function purchaseOptions(selected) {
      return PURCHASE_TYPES.map((value) => `<option value="${escape(value)}" ${value === selected ? "selected" : ""}>${escape(value)}</option>`).join("");
    }

    function optionNameKey(item) {
      return String(item?.name || item?.name_translate || "").trim().toLocaleLowerCase();
    }

    function optionCatalogKey(item) {
      return String(item?.id || item?.option_id || optionNameKey(item) || "").trim();
    }

    function optionLabel(item) {
      return item?.name_translate || item?.name || "-";
    }

    function optionPriceTypeLabel(item) {
      return Number(item?.price_type) === 1 ? "百分比" : "固定单价";
    }

    function optionCatalogCacheKey() {
      return `${state.inspection?.customer_id || ""}:${state.lastAccountId || "default"}`;
    }

    function syncOptionEditorValues() {
      const container = document.querySelector("#pgOptionEditor");
      if (!container || container.hidden) return;
      state.options = state.options.map((item, index) => ({
        ...item,
        checked: Boolean(container.querySelector(`[data-option-checked='${index}']`)?.checked),
        num: container.querySelector(`[data-option-num='${index}']`)?.value ?? item.num ?? 0,
        price: container.querySelector(`[data-option-price='${index}']`)?.value ?? item.price ?? 0,
      }));
    }

    function renderManualOptionRows() {
      const target = document.querySelector("#pgManualOptionRows");
      if (!target) return;
      target.innerHTML = state.options.length ? state.options.map((item, index) => `
        <tr>
          <td><input type="checkbox" data-option-checked="${index}" ${item.checked !== false ? "checked" : ""} /></td>
          <td>${escape(optionLabel(item))}</td>
          <td>${escape(item.__source === "added" ? "手动新增" : "原订单")}</td>
          <td>${escape(optionPriceTypeLabel(item))}</td>
          <td>${escape(item.__old_num ?? item.num ?? 0)}</td>
          <td><input type="number" min="0" step="1" data-option-num="${index}" value="${escape(item.num ?? 0)}" /></td>
          <td><input type="number" min="0" step="0.01" data-option-price="${index}" value="${escape(item.price ?? 0)}" /></td>
          <td>${item.__source === "added" ? `<button class="btn secondary" type="button" data-remove-option="${index}">移除</button>` : "-"}</td>
        </tr>`).join("") : `<tr><td colspan="8">当前未选择 OPTION，可从下方全量 OPTION 清单添加。</td></tr>`;
    }

    function renderAvailableOptionRows() {
      const target = document.querySelector("#pgAvailableOptionRows");
      const stateTarget = document.querySelector("#pgOptionCatalogState");
      if (!target || !stateTarget) return;
      if (state.optionCatalogLoading) {
        stateTarget.textContent = "正在加载可添加 OPTION...";
        target.innerHTML = "";
        return;
      }
      if (state.optionCatalogError) {
        stateTarget.textContent = state.optionCatalogError;
        target.innerHTML = "";
        return;
      }
      if (!state.optionCatalog.length) {
        stateTarget.textContent = "暂无可添加 OPTION";
        target.innerHTML = "";
        return;
      }
      const filter = state.optionFilter.trim().toLocaleLowerCase();
      const selectedNames = new Set(state.options.map(optionNameKey).filter(Boolean));
      const rows = state.optionCatalog
        .map((item, index) => ({ item, index }))
        .filter(({ item }) => !filter || `${item.name || ""} ${item.name_translate || ""}`.toLocaleLowerCase().includes(filter));
      stateTarget.textContent = `共 ${rows.length} 条可选 OPTION`;
      target.innerHTML = rows.length ? rows.map(({ item, index }) => {
        const nameKey = optionNameKey(item);
        const duplicate = !nameKey || selectedNames.has(nameKey);
        return `<tr>
          <td>${escape(optionLabel(item))}</td><td>${escape(optionPriceTypeLabel(item))}</td>
          <td>${escape(item.price ?? 0)}</td><td>${escape(item.unit || "-")}</td>
          <td><button class="btn secondary" type="button" data-add-option="${index}" ${duplicate ? "disabled" : ""}>${duplicate ? "已添加" : "添加"}</button></td>
        </tr>`;
      }).join("") : `<tr><td colspan="5">没有匹配的 OPTION</td></tr>`;
    }

    function bindOptionEditor(container) {
      if (container.dataset.bound === "1") return;
      container.dataset.bound = "1";
      container.addEventListener("click", (event) => {
        const addButton = event.target.closest("[data-add-option]");
        const removeButton = event.target.closest("[data-remove-option]");
        if (addButton) {
          syncOptionEditorValues();
          const item = state.optionCatalog[Number(addButton.dataset.addOption)];
          const nameKey = optionNameKey(item);
          if (!item || !nameKey) return d().showToast("该 OPTION 缺少名称，不能添加");
          if (state.options.some((option) => optionNameKey(option) === nameKey)) return d().showToast("该 OPTION 已添加");
          const currentNum = document.querySelector("[name='pre_num']")?.value || item.num || 0;
          state.options.push({
            ...item,
            checked: true,
            num: currentNum,
            price: item.price ?? 0,
            __old_num: "-",
            __source: "added",
            __catalog_key: optionCatalogKey(item),
          });
          renderManualOptionRows();
          renderAvailableOptionRows();
          return;
        }
        if (removeButton) {
          syncOptionEditorValues();
          const index = Number(removeButton.dataset.removeOption);
          if (state.options[index]?.__source !== "added") return;
          state.options.splice(index, 1);
          renderManualOptionRows();
          renderAvailableOptionRows();
        }
      });
      container.addEventListener("input", (event) => {
        if (event.target.id !== "pgOptionFilter") return;
        window.clearTimeout(state.optionFilterTimer);
        state.optionFilterTimer = window.setTimeout(() => {
          state.optionFilter = event.target.value || "";
          renderAvailableOptionRows();
        }, 150);
      });
    }

    async function ensureOptionCatalog() {
      const cacheKey = optionCatalogCacheKey();
      const cached = OPTION_CATALOG_CACHE.get(cacheKey);
      if (cached) {
        state.optionCatalog = cached;
        state.optionCatalogError = "";
        state.optionCatalogContext = cacheKey;
        renderAvailableOptionRows();
        return;
      }
      if (state.optionCatalogLoading && state.optionCatalogContext === cacheKey) return;
      const requestId = ++state.optionCatalogRequestId;
      state.optionCatalogLoading = true;
      state.optionCatalogError = "";
      state.optionCatalogContext = cacheKey;
      state.optionCatalog = [];
      renderAvailableOptionRows();
      try {
        const result = await d().api("/api/data-scripts/problem-goods/options", {
          method: "POST",
          body: baseRequest({
            order_sn: state.inspection.order_sn,
            customer_id: state.inspection.customer_id,
            backend_account_profile_id: state.lastAccountId || "",
          }),
        });
        const options = Array.isArray(result.options) ? result.options : [];
        OPTION_CATALOG_CACHE.set(cacheKey, options);
        if (requestId !== state.optionCatalogRequestId) return;
        state.optionCatalog = options;
      } catch (error) {
        if (requestId !== state.optionCatalogRequestId) return;
        state.optionCatalog = [];
        state.optionCatalogError = error.message || "加载可添加 OPTION 失败";
      } finally {
        if (requestId !== state.optionCatalogRequestId) return;
        state.optionCatalogLoading = false;
        renderAvailableOptionRows();
      }
    }

    function renderOptionEditor() {
      syncOptionEditorValues();
      const container = document.querySelector("#pgOptionEditor");
      if (!container) return;
      const manual = document.querySelector("#pgOptionDeal")?.value === "1";
      container.hidden = !manual;
      if (!manual) return;
      if (container.dataset.ready !== "1") {
        container.dataset.ready = "1";
        container.innerHTML = `
          <div class="table-wrap"><table><thead><tr><th>使用</th><th>OPTION</th><th>来源</th><th>计价</th><th>原数量</th><th>修改后数量</th><th>修改后价格/%</th><th>操作</th></tr></thead><tbody id="pgManualOptionRows"></tbody></table></div>
          <details class="functional-requirement" open>
            <summary>添加 OPTION</summary>
            <div class="field"><label>搜索全量 OPTION</label><input id="pgOptionFilter" placeholder="按中文名或日文名搜索" /></div>
            <p class="progress-note" id="pgOptionCatalogState"></p>
            <div class="table-wrap"><table><thead><tr><th>OPTION</th><th>计价</th><th>默认价格/%</th><th>单位</th><th>操作</th></tr></thead><tbody id="pgAvailableOptionRows"></tbody></table></div>
          </details>`;
        bindOptionEditor(container);
      }
      renderManualOptionRows();
      renderAvailableOptionRows();
    }

    function selectedSnapshot() {
      const item = state.selected || {};
      const isNew = state.selectedKind === "candidate";
      const originalNum = numeric(item.confirm_num ?? item.possible_num, "0");
      const originalPrice = numeric(item.confirm_price ?? item.price, "0");
      const originalFreight = numeric(item.confirm_freight ?? item.freight, "0");
      return {
        status: isNew ? 0 : Number(item.status || 0),
        possibleNum: numeric(item.possible_num ?? originalNum, "0"),
        originalNum,
        originalPrice,
        originalFreight,
        modifiedNum: numeric(item.pre_num, originalNum),
        modifiedPrice: numeric(item.pre_price, originalPrice),
        modifiedFreight: numeric(item.pre_freight, originalFreight),
        maxSubmitNum: Number(item.max_submit_num ?? Math.max(0, Number(item.possible_num || 0) - Number(item.storage_num || 0))),
        type: Number(item.type || 8),
        options: optionRows(item.option_new || item.option || []),
      };
    }

    function renderProcessForm() {
      const snapshot = selectedSnapshot();
      const status = snapshot.status;
      state.options = snapshot.options.map((item) => ({ ...item, __old_num: item.num, __source: "original" }));
      state.optionFilter = "";
      state.optionCatalog = [];
      state.optionCatalogError = "";
      state.optionCatalogLoading = false;
      state.optionCatalogContext = "";
      state.optionCatalogRequestId += 1;
      const autoUnsafe = state.options.some((item) => item.checked !== false && Number(item.num || 0) > Number(snapshot.possibleNum || 0));
      const optionDealDefault = Number(state.selected?.option_deal_suggest || (autoUnsafe ? 1 : 2));
      state.lastAccountId = document.querySelector("#pgAdminAccount")?.value || state.lastAccountId || "";
      modal().innerHTML = `
        <form id="pgProcessForm">
          <div class="modal-head"><h3>问题产品处理 · ${escape(state.inspection.order_sn)}</h3><button class="btn secondary" id="closeProblemGoods" type="button">关闭</button></div>
          <div class="modal-body">
            <div class="functional-summary">
              <div><span>问题产品</span><strong>${state.selectedKind === "candidate" ? "新建" : `#${escape(state.selected.problem_goods_id)}`}</strong></div>
              <div><span>番号</span><strong>${escape(state.selected.sorting || "-")}</strong></div>
              <div><span>当前状态</span><strong>${escape(STATUS_NAMES[status] || "待提出")}</strong></div>
              <div><span>后台账号</span><strong>${escape(state.accounts.find((item) => String(item.id) === String(state.lastAccountId))?.profile_name || "环境默认")}</strong></div>
            </div>
            <details class="functional-requirement" open><summary>原始数据与修改后数据</summary>
              <div class="table-wrap"><table><thead><tr><th>字段</th><th>当前值</th><th>修改后</th></tr></thead><tbody>
                <tr><td>数量</td><td>${escape(snapshot.originalNum)}</td><td><input name="pre_num" type="number" min="0" step="1" value="${escape(snapshot.modifiedNum)}" /></td></tr>
                <tr><td>单价</td><td>${escape(snapshot.originalPrice)}</td><td><input name="pre_price" type="number" min="0" step="0.01" value="${escape(snapshot.modifiedPrice)}" /></td></tr>
                <tr><td>运费</td><td>${escape(snapshot.originalFreight)}</td><td><input name="pre_freight" type="number" min="0" step="0.01" value="${escape(snapshot.modifiedFreight)}" /></td></tr>
              </tbody></table></div>
            </details>
            ${stageVisible(status, 0) ? `<details class="functional-requirement" open><summary>提出问题产品</summary><div class="form-grid">
              <div class="field"><label>问题类型</label><select name="problem_type">${typeOptions(snapshot.type)}</select></div>
              <div class="field"><label>问题产品数量（最多 ${escape(snapshot.maxSubmitNum)}）</label><input name="problem_num" type="number" min="1" max="${escape(snapshot.maxSubmitNum)}" step="1" value="1" /></div>
              <div class="field"><label>问题描述</label><textarea name="problem_description" rows="3">自动化问题产品</textarea></div>
            </div></details>` : `<input name="problem_type" type="hidden" value="${escape(snapshot.type)}" />`}
            ${stageVisible(status, 1) ? `<details class="functional-requirement" open><summary>业务翻译</summary><div class="field"><label>客户译文</label><textarea name="translation_content" rows="3">自動化問題商品</textarea></div></details>` : ""}
            ${stageVisible(status, 2) ? `<details class="functional-requirement" open><summary>客户处理</summary><div class="form-grid">
              <div class="field"><label>客户选择</label><select name="client_deal_choice" id="pgClientChoice"><option value="accept">接受</option><option value="exchange">不良品换货</option><option value="cancel">退货/取消购买</option><option value="discard">废弃</option><option value="other">其他</option></select></div>
              <div class="field" id="pgClientOther" hidden><label>其他回复</label><textarea name="client_deal_other" rows="3"></textarea></div>
            </div></details>` : ""}
            ${stageVisible(status, 3) ? `<details class="functional-requirement" open><summary>业务决策与费用</summary><div class="form-grid">
              <div class="field"><label>业务决策</label><textarea name="business_decision" rows="3">自动化业务决策</textarea></div>
              <div class="field"><label>手续费</label><select name="service_deal_suggest"><option value="1">已收不退</option><option value="2" selected>多退少补</option></select></div>
              <div class="field"><label>附加服务费</label><select name="option_deal_suggest" id="pgOptionDeal"><option value="1" ${optionDealDefault === 1 ? "selected" : ""}>按照业务修改值计算</option><option value="2" ${optionDealDefault === 2 ? "selected" : ""}>系统自动计算</option></select></div>
            </div><div id="pgOptionEditor"></div><p class="progress-note">点击执行后才会写入 OPTION，并立即进行官方账单预览；达到 500 元会暂停并提示切换部长账号。</p></details>` : ""}
            ${stageVisible(status, 4) ? `<details class="functional-requirement" open><summary>采购处理</summary><div class="form-grid">
              <div class="field"><label>采购处理类型</label><select name="g_deal_type">${purchaseOptions("其他")}</select></div>
              <div class="field"><label>采购处理备注</label><textarea name="purchase_remark" rows="3">自动化采购处理</textarea></div>
            </div></details>` : ""}
            ${status <= 5 ? `<label class="check-field"><input name="confirm_distribution" type="checkbox" checked /><span>采购完成后自动进行配货确认</span></label>` : `<div class="empty">该问题产品已经完成，无需再次执行。</div>`}
            ${status < 6 ? `<label class="check-field"><input name="confirmed" type="checkbox" required /><span>我已核对原始数据、修改后数据和处理选项</span></label>` : ""}
          </div>
          <div class="modal-foot"><button class="btn secondary" id="pgBack" type="button">返回查询</button>${status < 6 ? `<button class="btn" type="submit">预览并执行</button>` : ""}</div>
        </form>`;
      closeButton();
      document.querySelector("#pgBack").addEventListener("click", renderSearch);
      document.querySelector("#pgClientChoice")?.addEventListener("change", (event) => {
        document.querySelector("#pgClientOther").hidden = event.target.value !== "other";
      });
      const syncOptionMode = () => {
        renderOptionEditor();
        if (document.querySelector("#pgOptionDeal")?.value === "1") void ensureOptionCatalog();
      };
      document.querySelector("#pgOptionDeal")?.addEventListener("change", syncOptionMode);
      syncOptionMode();
      document.querySelector("#pgProcessForm").addEventListener("submit", executeFlow);
    }

    function collectOptions() {
      syncOptionEditorValues();
      return state.options.map(({ __catalog_key, __old_num, __source, ...item }) => item);
    }

    function collectVariables(form) {
      const data = Object.fromEntries(new FormData(form));
      const selected = state.selected || {};
      const variables = {
        order_sn: state.inspection.order_sn,
        customer_id: state.inspection.customer_id,
        backend_account_profile_id: state.lastAccountId || "",
        problem_goods_id: state.selectedKind === "problem" ? selected.problem_goods_id : "",
        create_if_missing: state.selectedKind === "candidate",
        order_purchase_id: selected.order_purchase_id,
        order_detail_id: selected.order_detail_id,
        problem_type: data.problem_type || selected.type || 8,
        problem_num: data.problem_num || 1,
        problem_description: data.problem_description || "",
        translation_content: data.translation_content || "",
        client_deal_choice: data.client_deal_choice || "accept",
        client_deal_other: data.client_deal_other || "",
        business_decision: data.business_decision || "",
        service_deal_suggest: data.service_deal_suggest || selected.service_deal_suggest || 2,
        option_deal_suggest: data.option_deal_suggest || selected.option_deal_suggest || 2,
        pre_num: data.pre_num,
        pre_price: data.pre_price,
        pre_freight: data.pre_freight,
        g_deal_type: data.g_deal_type || "其他",
        purchase_remark: data.purchase_remark || "",
        confirm_distribution: true,
      };
      if (Number(variables.option_deal_suggest) === 1) variables.option_new = collectOptions();
      return variables;
    }

    async function executeFlow(event) {
      event.preventDefault();
      const form = event.currentTarget;
      if (!form.querySelector("[name='confirmed']")?.checked) return d().showToast("请先确认已核对数据");
      const variables = collectVariables(form);
      state.resumeVariables = variables;
      renderRunning("正在执行官方账单预览和问题产品流程...");
      await submitExecution(variables);
    }

    function renderRunning(message) {
      modal().innerHTML = `
        <div class="modal-head"><h3>问题产品处理中</h3><button class="btn secondary" id="closeProblemGoods" type="button">关闭</button></div>
        <div class="modal-body"><div class="empty">${escape(message)}</div><p class="progress-note">请勿重复点击执行；网络异常时脚本会先查询状态，不会盲目重试写接口。</p></div>`;
      closeButton();
    }

    async function submitExecution(variables) {
      try {
        const result = await d().api("/api/data-scripts/problem-goods", { method: "POST", body: baseRequest(variables) });
        const summary = result.summary || {};
        if (summary.permission_required || (/部长|500/.test(summary.reason || "") && !summary.completed)) {
          state.resumeVariables = variables;
          renderPermissionPrompt(summary);
          return;
        }
        if (result.result !== "passed" || (!summary.completed && !summary.already_completed)) {
          renderFailure(result);
          return;
        }
        renderCompleted(result);
      } catch (error) {
        if (/部长|500/.test(error.message || "")) {
          renderPermissionPrompt({ reason: error.message, resume_stage: "purchase_deal" });
        } else {
          renderFailure({ summary: { reason: error.message } });
        }
      }
    }

    function renderPermissionPrompt(summary) {
      modal().innerHTML = `
        <div class="modal-head"><h3>需要部长账号</h3><button class="btn secondary" id="closeProblemGoods" type="button">关闭</button></div>
        <div class="modal-body">
          <div class="diagnosis-warning">${escape(summary.reason || "退款金额达到权限阈值，请切换部长后台账号。")}</div>
          <div class="functional-summary"><div><span>问题产品ID</span><strong>${escape(summary.problem_goods_id || state.resumeVariables?.problem_goods_id || "-")}</strong></div><div><span>继续步骤</span><strong>${escape(summary.resume_stage || "purchase_deal")}</strong></div></div>
          <div class="field"><label>选择部长后台账号</label><select id="pgLeaderAccount">${accountOptions(state.accounts, "", escape)}</select></div>
          <p class="progress-note">继续执行会先按问题产品当前状态恢复，不会重复业务决策或重复入账。</p>
        </div>
        <div class="modal-foot"><span></span><button class="btn" id="pgContinueLeader" type="button">切换账号并继续</button></div>`;
      closeButton();
      document.querySelector("#pgContinueLeader").addEventListener("click", async () => {
        const profileId = document.querySelector("#pgLeaderAccount").value;
        if (!profileId) return d().showToast("请选择已维护的部长后台账号");
        const variables = { ...state.resumeVariables, backend_account_profile_id: profileId, allow_large_refund: true };
        state.resumeVariables = variables;
        renderRunning("已切换后台账号，正在从安全检查点继续...");
        await submitExecution(variables);
      });
    }

    function previewBills(summary) {
      const bills = summary.preview_bills || [];
      if (!bills.length) return `<div class="empty">本次没有客户出入金账单</div>`;
      return `<div class="table-wrap"><table><thead><tr><th>订单号</th><th>客户入/出金(JPY)</th><th>汇率</th><th>类型</th></tr></thead><tbody>${bills.map((bill) => `
        <tr><td>${escape(bill.order_sn || summary.order_sn || "-")}</td><td>${escape(bill.amount ?? 0)}</td><td>${escape(bill.exchange_rate ?? "-")}</td><td>${Number(bill.amount || 0) >= 0 ? "客户入金" : "客户出金"}</td></tr>`).join("")}</tbody></table></div>`;
    }

    function renderCompleted(result) {
      const summary = result.summary || {};
      modal().innerHTML = `
        <div class="modal-head"><h3>问题产品处理完成</h3><button class="btn secondary" id="closeProblemGoods" type="button">关闭</button></div>
        <div class="modal-body">
          <div class="functional-summary"><div><span>订单号</span><strong>${escape(summary.order_sn || "-")}</strong></div><div><span>问题产品ID</span><strong>${escape(summary.problem_goods_id || "-")}</strong></div><div><span>状态</span><strong>${escape(summary.status_name || STATUS_NAMES[summary.status] || summary.status)}</strong></div><div><span>记录ID</span><strong>${escape(result.id || "-")}</strong></div></div>
          <details class="functional-requirement" open><summary>客户账单预览</summary>${previewBills(summary)}</details>
        </div>`;
      closeButton();
      d().showToast("问题产品流程执行完成");
    }

    function renderFailure(result) {
      const summary = result.summary || {};
      modal().innerHTML = `
        <div class="modal-head"><h3>问题产品处理未完成</h3><button class="btn secondary" id="closeProblemGoods" type="button">关闭</button></div>
        <div class="modal-body"><div class="diagnosis-warning">${escape(summary.reason || "执行失败，请查看执行记录。")}</div><p class="progress-note">重新执行前请先按同一订单号查询状态，脚本会从当前步骤恢复。</p></div>
        <div class="modal-foot"><button class="btn secondary" id="pgQueryAgain" type="button">重新查询</button><span></span></div>`;
      closeButton();
      document.querySelector("#pgQueryAgain").addEventListener("click", renderSearch);
    }

    async function open(flow, deps) {
      state.searchController?.abort();
      state.searchRequestId += 1;
      state.optionCatalogRequestId += 1;
      window.clearTimeout(state.optionFilterTimer);
      state.flow = flow;
      state.deps = deps;
      state.inspection = null;
      state.selected = null;
      state.selectedKind = "";
      state.options = [];
      state.optionCatalog = [];
      state.optionCatalogLoading = false;
      state.optionCatalogError = "";
      state.optionCatalogContext = "";
      state.optionFilter = "";
      state.resumeVariables = null;
      state.search = {};
      state.lastAccountId = "";
      try {
        const query = flow.projectId ? `?project_id=${encodeURIComponent(flow.projectId)}` : "";
        state.accounts = await deps.api(`/api/test-accounts${query}`);
      } catch {
        state.accounts = [];
      }
      renderSearch();
    }

    return { open };
  }

  window.ProblemGoodsUI = problemGoodsUi();
})();
