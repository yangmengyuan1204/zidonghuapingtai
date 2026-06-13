if (!window.__fullFlowDataScriptLoaded) {
  window.__fullFlowDataScriptLoaded = true;

  BUILTIN_FLOW_DEFINITIONS.full_flow = { id: "full_flow_builtin", name: "全流程完全体" };
  if (!BUILTIN_DATA_SCRIPT_TYPES.includes("full_flow")) BUILTIN_DATA_SCRIPT_TYPES.push("full_flow");

  const FULL_FLOW_STOP_NODE_OPTIONS = [
    { value: "full_complete", label: "不暂停（全流程结束）" },
    { value: "shopping_cart", label: "商品加购完成" },
    { value: "order_created", label: "前台提交订单完成" },
    { value: "order_translated", label: "后台订单翻译完成" },
    { value: "order_confirmed", label: "后台订单确认完成" },
    { value: "order_offered", label: "后台订单报价完成" },
    { value: "order_paid", label: "订单支付完成" },
    { value: "pending_purchase", label: "待拍下" },
    { value: "purchase_no_saved", label: "保存交易号完成" },
    { value: "purchase_wait_modify_price", label: "标记待改价完成" },
    { value: "purchase_wait_pay", label: "提交待财务付款完成" },
    { value: "purchase_paid", label: "交易号付款完成" },
    { value: "checking_started", label: "开始核查完成" },
    { value: "shelf_stored", label: "核查上架/入库完成" },
    { value: "warehouse_delivery_created", label: "仓库提出配送单完成" },
    { value: "porder_translated", label: "配送单待翻译/提交配货完成" },
    { value: "porder_confirmed", label: "配送单确认流转完成" },
    { value: "porder_wait_offer", label: "配送单进入待报价完成" },
    { value: "porder_offered", label: "配送单报价完成" },
    { value: "porder_paid", label: "配送单支付完成" },
  ];

  SCRIPT_PARAM_SCHEMAS.full_flow = [
    CUSTOMER_ID_FIELD,
    { name: "keyword", label: "关键词", default: "衣服" },
    { name: "shop_type", label: "商品来源", type: "select", options: SHOP_TYPE_OPTIONS, default: "1688" },
    { name: "target_shops", label: "加购目标店铺数", type: "number", default: 4 },
    { name: "per_shop", label: "加购每店商品数", type: "number", default: 5 },
    { name: "quantities", label: "加购商品数量", default: "2,3,5" },
    { name: "order_shop_count", label: "订单店铺数", type: "number", default: 1 },
    { name: "order_per_shop", label: "订单每店商品数", type: "number", default: 2 },
    { name: "order_item_num", label: "订单商品数量", type: "number", default: 10 },
    { name: "warehouse_sku_count", label: "仓库提出番数", type: "number", default: 1 },
    { name: "send_num", label: "每番配送数量", type: "number", default: 1 },
    { name: "stop_after_node", label: "暂停节点", type: "select", options: FULL_FLOW_STOP_NODE_OPTIONS, default: "full_complete" },
  ];

  const originalSanitizeScriptVariablesForFullFlow = sanitizeScriptVariables;
  sanitizeScriptVariables = function (scriptType, variables, flow = null) {
    if (scriptType !== "full_flow") return originalSanitizeScriptVariablesForFullFlow(scriptType, variables, flow);
    const next = { ...(variables || {}) };
    const shopType = String(next.shop_type || splitParamList(next.shop_types)[0] || "1688").trim() || "1688";
    next.shop_type = shopType;
    next.shop_types = [shopType];
    next.target_shops = normalizePositiveInt(next.target_shops || next.shop_count, 4);
    next.per_shop = normalizePositiveInt(next.per_shop, 5);
    next.warehouse_sku_count = normalizePositiveInt(next.warehouse_sku_count || next.porder_sku_count || next.sku_count, 1);
    next.order_shop_count = normalizePositiveInt(next.order_shop_count, 1);
    next.order_per_shop = normalizePositiveInt(next.order_per_shop || next.order_item_count, 2);
    if (next.order_shop_count * next.order_per_shop < next.warehouse_sku_count) {
      next.order_per_shop = Math.ceil(next.warehouse_sku_count / next.order_shop_count);
    }
    next.order_item_count = next.order_per_shop;
    next.target_shops = Math.max(next.target_shops, next.order_shop_count);
    next.per_shop = Math.max(next.per_shop, next.order_per_shop);
    next.order_item_num = normalizePositiveInt(next.order_item_num, 10);
    next.send_num = normalizePositiveInt(next.send_num || next.porder_send_num, 1);
    next.stop_after_node = String(next.stop_after_node || "full_complete").trim() || "full_complete";
    next.strict_shop_count = false;
    next.submit_order = true;
    next.run_backend_flow = true;
    next.run_backend_delivery_flow = true;
    next.run_backend_porder_flow = false;
    next.auto_fill_cart_on_shortage = true;
    next.link_quote_balance_before_shelf = false;
    next.auto_quote_and_pay = false;
    next.logistics_id = next.logistics_id || "1";
    next.porder_logistics_id = next.porder_logistics_id || "14";
    next.delivery_quote_logistics_id = next.delivery_quote_logistics_id || "25";
    next.logistics_price_artificial = next.logistics_price_artificial || "775";
    next.purchase_unit_price = next.purchase_unit_price || "10";
    next.purchase_freight = next.purchase_freight || "0";
    next.warehouse_index = next.warehouse_index || "2";
    next.finance_confirm = true;
    next.discounts_id = "";
    next.predict_logistics_price_is_pay = "0";
    next.include_balance_pay_amount = false;
    delete next.order_sn;
    delete next.last_order_sn;
    delete next.order_sns;
    delete next.porder_sn;
    delete next.porder_sns;
    delete next.shop_count;
    return next;
  };

  function ensureFullFlowScript(flows, projects, envs, cases) {
    if (isBuiltinDeleted("full_flow_builtin")) return flows;
    const scriptName = "全流程完全体";
    const login = findCaseByName(cases, "登录");
    const search = findCaseByName(cases, "搜索商品");
    const detail = findCaseByName(cases, "商品详情");
    const cart = findCaseByName(cases, "加入购物车");
    const env = envs.find((item) => item.env_name === "test-登录") || envs[0];
    const projectId = env?.project_id || projects[0]?.id || "";
    if (!env) return flows;
    const loginBody = parseJsonText(login?.body || "{}", {});
    const existingIndex =
      flows.findIndex((flow) => flow.id === "full_flow_builtin") >= 0
        ? flows.findIndex((flow) => flow.id === "full_flow_builtin")
        : flows.findIndex((flow) => flow.name === scriptName);
    const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};
    let existingVariables = {};
    try {
      existingVariables = parseJsonText(existingFlow.variables || "{}", {});
    } catch {
      existingVariables = {};
    }
    const defaultVariables = {
      keyword: "衣服",
      keywords: ["衣服", "鞋子", "包"],
      preferred_keywords: ["衣服", "鞋子", "包"],
      boost_keywords: ["衣服", "鞋子", "包"],
      random_keyword: true,
      shop_type: "1688",
      shop_types: ["1688"],
      target_shops: 4,
      per_shop: 5,
      quantities: "2,3,5",
      order_shop_count: 1,
      order_per_shop: 2,
      order_item_count: 2,
      order_item_num: 10,
      price_cut: 0,
      logistics_id: "1",
      create_type: "send",
      submit_order: true,
      run_backend_flow: true,
      run_backend_delivery_flow: true,
      run_backend_porder_flow: false,
      stop_after_node: "full_complete",
      warehouse_sku_count: 1,
      send_num: 1,
      porder_logistics_id: "14",
      client_warehouse_list: "/client/wms.stockAutoList",
      porder_suffix: "300001",
      purchase_unit_price: "10",
      purchase_freight: "0",
      warehouse_index: "2",
      box_count: "1",
      box_length: "58",
      box_width: "51",
      box_height: "50",
      box_weight: "10",
      delivery_quote_logistics_id: "25",
      logistics_price_artificial: "775",
      account: loginBody.account || "12345678990",
      password: loginBody.password || "123456",
      client_tool: "1",
      backend_account: "Y001",
      backend_password: "raku@123456``",
      backend_system: "1",
      backend_code: "wnm666",
    };
    const mergedVariables = sanitizeScriptVariables("full_flow", { ...defaultVariables, ...existingVariables }, existingFlow);
    mergedVariables.keywords = uniqueList([...listValue(existingVariables.keywords), ...defaultVariables.keywords]);
    mergedVariables.preferred_keywords = uniqueList([...listValue(existingVariables.preferred_keywords), ...defaultVariables.preferred_keywords]);
    mergedVariables.boost_keywords = uniqueList([...listValue(existingVariables.boost_keywords), ...defaultVariables.boost_keywords]);
    if (existingVariables.order_option_counts) mergedVariables.order_option_counts = existingVariables.order_option_counts;
    const caseIds = [login, search, detail, cart].filter(Boolean).map((item) => item.id);
    const nextFlow = {
      ...existingFlow,
      id: "full_flow_builtin",
      name: existingFlow.name || scriptName,
      scriptType: "full_flow",
      projectId: String(projectId),
      envId: String(env.id),
      caseIds,
      variables: JSON.stringify(mergedVariables, null, 2),
    };
    const next =
      existingIndex >= 0
        ? flows.map((flow, index) => (index === existingIndex ? nextFlow : flow)).filter((flow, index) => index === existingIndex || flow.id !== "full_flow_builtin")
        : [...flows, nextFlow];
    writeFlows(next);
    return next;
  }

  const originalEnsureWarehouseDeliveryScriptForFullFlow = ensureWarehouseDeliveryScript;
  ensureWarehouseDeliveryScript = function (flows, projects, envs, cases) {
    return ensureFullFlowScript(originalEnsureWarehouseDeliveryScriptForFullFlow(flows, projects, envs, cases), projects, envs, cases);
  };

  function openFullFlowRunForm(flow, fields) {
    let variables = {};
    try {
      variables = parseJsonText(flow.variables || "{}", {});
    } catch {
      showToast("脚本变量不是合法 JSON");
      return;
    }
    variables = sanitizeScriptVariables("full_flow", variables, flow);
    const values = {
      ...paramFormValues(fields, variables),
      __save_defaults: false,
    };
    const body = [...fields, { name: "__save_defaults", label: "保存为默认值", type: "checkbox", default: false }]
      .map((field) => renderFormField(field, values?.[field.name] ?? field.default ?? ""))
      .join("");
    const initialCounts = orderOptionCountsFromVariables(variables.order_option_counts);
    modalEl.innerHTML = `
      <form id="fullFlowRunForm">
        <div class="modal-head">
          <h3>${escapeHtml(`执行 ${flow.name || "全流程完全体"}`)}</h3>
          <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>
        </div>
        <div class="modal-body">
          <div class="form-grid">${body}</div>
          <details class="functional-requirement" open>
            <summary>订单 option（可选）</summary>
            <div id="fullFlowOrderOptionPreview"><div class="empty">正在读取订单 option...</div></div>
            <div class="actions" style="margin-top:10px">
              <button class="btn secondary" id="refreshFullFlowOrderOptions" type="button">刷新选项</button>
            </div>
          </details>
        </div>
        <div class="modal-foot"><span></span><button class="btn" type="submit">执行</button></div>
      </form>
    `;
    modalEl.showModal();
    const form = document.querySelector("#fullFlowRunForm");
    const previewEl = document.querySelector("#fullFlowOrderOptionPreview");
    function runtimeVariables(includeCurrentCounts = true) {
      const data = readForm(form);
      const next = sanitizeScriptVariables("full_flow", mergeParamValues(variables, fields, data), flow);
      const counts = includeCurrentCounts ? readOrderOptionCounts(form) : initialCounts;
      if (Object.keys(counts).length) next.order_option_counts = counts;
      else delete next.order_option_counts;
      return next;
    }
    async function refreshOptions() {
      const counts = readOrderOptionCounts(form);
      previewEl.innerHTML = `<div class="empty">正在读取订单 option...</div>`;
      try {
        const result = await api("/api/data-scripts/order-quote/options-preview", {
          method: "POST",
          body: {
            env_id: flow.envId ? Number(flow.envId) : null,
            variables: runtimeVariables(false),
          },
        });
        previewEl.innerHTML = renderOrderOptionPreview(result.options || [], { ...initialCounts, ...counts });
      } catch (error) {
        previewEl.innerHTML = `<div class="alert error">读取 option 失败：${escapeHtml(error.message)}</div>`;
      }
    }
    document.querySelector("#closeModal").addEventListener("click", async () => {
      modalEl.close();
      if (state.view === "dataScripts" && !state.factory.editing) {
        await renderDataScripts();
      }
    });
    document.querySelector("#refreshFullFlowOrderOptions").addEventListener("click", refreshOptions);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = readForm(form);
        const next = runtimeVariables(true);
        if (data.__save_defaults) saveFlowVariables(flow, next);
        await runSavedFlow(flow, next);
      } catch (error) {
        showToast(error.message);
      }
    });
    refreshOptions();
  }

  const originalOpenRunScriptFormForFullFlow = openRunScriptForm;
  openRunScriptForm = function (flow) {
    if (flow?.scriptType === "full_flow") {
      openFullFlowRunForm(flow, scriptParamFields("full_flow", flow));
      return;
    }
    return originalOpenRunScriptFormForFullFlow(flow);
  };

  const originalRunSavedFlowForFullFlow = runSavedFlow;
  runSavedFlow = async function (flow, runtimeVariables = null, options = {}) {
    if (flow?.scriptType !== "full_flow") {
      return originalRunSavedFlowForFullFlow(flow, runtimeVariables, options);
    }
    let variables = {};
    if (runtimeVariables) {
      variables = { ...runtimeVariables };
    } else {
      try {
        variables = parseJsonText(flow.variables, {});
      } catch {
        showToast("脚本变量不是合法 JSON");
        return;
      }
    }
    variables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables("full_flow", variables, flow), !options.singleCustomerRun));
    const customerIds = customerIdsFromVariables(variables);
    if (customerIds.length > 1 && !options.singleCustomerRun) {
      await runMultiCustomerFlow(flow, variables, customerIds);
      return;
    }
    if (customerIds.length === 1) variables = variablesForCustomerId(variables, customerIds[0]);
    const progress = options.progress || openScriptProgress("全流程完全体执行进度", "预计执行 20 个业务节点");
    try {
      showToast("全流程脚本执行中，请稍候");
      progress.update(10, "正在执行商品加购、订单报价、支付、采购、上架、配送单流转...");
      const result = await api("/api/data-scripts/full-flow", {
        method: "POST",
        body: {
          env_id: flow.envId ? Number(flow.envId) : null,
          variables,
        },
      });
      const summary = result.summary || {};
      const orderSn = summary.order_sn || "";
      const porderSn = summary.porder_sn || "";
      const flows = readFlows().map((item) =>
        item.id === flow.id
          ? {
              ...item,
              lastOrderSn: orderSn || item.lastOrderSn || "",
              lastPorderSn: porderSn || item.lastPorderSn || "",
              lastRecordId: result.id,
            }
          : item,
      );
      writeFlows(flows);
      flow.lastOrderSn = orderSn || flow.lastOrderSn || "";
      flow.lastPorderSn = porderSn || flow.lastPorderSn || "";
      flow.lastRecordId = result.id;
      progress.success(summary.paused ? `已按暂停节点停止：${summary.node_label || summary.current_node || ""}` : "全流程完全体执行完成，正在展示结果...");
      return presentScriptResult(
        {
          records: [{ id: result.id, case_name: flow.name, result: result.result }],
          variables: summary,
        },
        options,
      );
    } catch (error) {
      progress.fail(`执行失败：${error.message}`);
      showToast(error.message);
      if (options.collectOnly) throw error;
    }
  };
}
