if (!window.__fullFlowDataScriptLoaded) {
  window.__fullFlowDataScriptLoaded = true;

  BUILTIN_FLOW_DEFINITIONS.full_flow = { id: "full_flow_builtin", name: "全流程完全体" };
  if (!BUILTIN_DATA_SCRIPT_TYPES.includes("full_flow")) BUILTIN_DATA_SCRIPT_TYPES.push("full_flow");
  BUILTIN_FLOW_DEFINITIONS.direct_box_to_shelf = { id: "direct_box_to_shelf_builtin", name: "直接装箱上架" };
  if (!BUILTIN_DATA_SCRIPT_TYPES.includes("direct_box_to_shelf")) BUILTIN_DATA_SCRIPT_TYPES.push("direct_box_to_shelf");
  BUILTIN_FLOW_DEFINITIONS.resume_order_flow = { id: "resume_order_flow_builtin", name: "输入订单号继续执行操作" };
  if (!BUILTIN_DATA_SCRIPT_TYPES.includes("resume_order_flow")) BUILTIN_DATA_SCRIPT_TYPES.push("resume_order_flow");
  BUILTIN_FLOW_DEFINITIONS.resume_porder_flow = { id: "resume_porder_flow_builtin", name: "输入配送单号继续执行操作" };
  if (!BUILTIN_DATA_SCRIPT_TYPES.includes("resume_porder_flow")) BUILTIN_DATA_SCRIPT_TYPES.push("resume_porder_flow");

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
  const RESUME_ORDER_STOP_NODE_OPTIONS = FULL_FLOW_STOP_NODE_OPTIONS.filter(
    (option) => !["full_complete", "shopping_cart", "order_created", "porder_paid"].includes(option.value),
  );
  const RESUME_PORDER_STOP_NODE_OPTIONS = FULL_FLOW_STOP_NODE_OPTIONS.filter(
    (option) => ["warehouse_delivery_created", "porder_translated", "porder_confirmed", "porder_wait_offer", "porder_offered", "porder_paid"].includes(option.value),
  ).map((option) => option.value === "porder_paid" ? { ...option, label: "不暂停（配送单全流程结束）" } : option);

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

  SCRIPT_PARAM_SCHEMAS.direct_box_to_shelf = [
    CUSTOMER_ID_FIELD,
    { name: "order_sn", label: "订单号（可选）" },
    { name: "purchase_no", label: "交易号（可选）" },
    { name: "keyword", label: "关键词", default: "衣服" },
    { name: "shop_type", label: "商品来源", type: "select", options: SHOP_TYPE_OPTIONS, default: "1688" },
    { name: "order_shop_count", label: "订单店铺数", type: "number", default: 1 },
    { name: "order_per_shop", label: "订单每店商品数", type: "number", default: 2 },
    { name: "order_item_num", label: "订单商品数量", type: "number", default: 10 },
    { name: "box_count", label: "箱子数", type: "number", default: 1 },
  ];

  SCRIPT_PARAM_SCHEMAS.resume_order_flow = [
    CUSTOMER_ID_FIELD,
    { name: "order_sn", label: "订单号", required: true },
    { name: "purchase_no", label: "交易号（可选）" },
    { name: "order_item_num", label: "订单商品数量", type: "number", default: 10 },
    { name: "warehouse_sku_count", label: "仓库提出番数", type: "number", default: 1 },
    { name: "send_num", label: "每番配送数量", type: "number", default: 1 },
    { name: "stop_after_node", label: "暂停节点", type: "select", options: RESUME_ORDER_STOP_NODE_OPTIONS, default: "porder_offered" },
  ];

  SCRIPT_PARAM_SCHEMAS.resume_porder_flow = [
    CUSTOMER_ID_FIELD,
    { name: "porder_sn", label: "配送单号", required: true },
    { name: "stop_after_node", label: "暂停节点", type: "select", options: RESUME_PORDER_STOP_NODE_OPTIONS, default: "porder_offered" },
  ];

  const originalSanitizeScriptVariablesForFullFlow = sanitizeScriptVariables;
  sanitizeScriptVariables = function (scriptType, variables, flow = null) {
    if (scriptType === "direct_box_to_shelf") {
      const next = { ...(variables || {}) };
      const shopType = String(next.shop_type || splitParamList(next.shop_types)[0] || "1688").trim() || "1688";
      next.shop_type = shopType;
      next.shop_types = [shopType];
      next.order_shop_count = normalizePositiveInt(next.order_shop_count, 1);
      next.order_per_shop = normalizePositiveInt(next.order_per_shop || next.order_item_count, 2);
      next.order_item_count = next.order_per_shop;
      next.order_item_num = normalizePositiveInt(next.order_item_num, 10);
      next.box_count = normalizePositiveInt(next.box_count || next.direct_box_count, 1);
      next.strict_shop_count = false;
      next.submit_order = true;
      next.run_backend_flow = true;
      next.auto_fill_cart_on_shortage = true;
      next.link_quote_balance_before_shelf = false;
      next.auto_quote_and_pay = false;
      next.logistics_id = next.logistics_id || "1";
      next.purchase_unit_price = next.purchase_unit_price || "10";
      next.purchase_freight = next.purchase_freight || "0";
      next.warehouse_index = next.warehouse_index || "2";
      next.finance_confirm = true;
      next.discounts_id = "";
      next.predict_logistics_price_is_pay = "0";
      next.include_balance_pay_amount = false;
      next.boxes = normalizeDirectBoxes(next.boxes, next.box_count);
      return next;
    }
    if (scriptType === "resume_order_flow") {
      const next = { ...(variables || {}) };
      next.order_sn = String(next.order_sn || next.last_order_sn || "").trim();
      next.purchase_no = String(next.purchase_no || "").trim();
      next.order_item_num = normalizePositiveInt(next.order_item_num, 10);
      next.warehouse_sku_count = normalizePositiveInt(next.warehouse_sku_count || next.porder_sku_count || next.sku_count, 1);
      next.send_num = normalizePositiveInt(next.send_num || next.porder_send_num, 1);
      next.stop_after_node = String(next.stop_after_node || "porder_offered").trim() || "porder_offered";
      next.run_backend_flow = true;
      next.run_backend_delivery_flow = true;
      next.run_backend_porder_flow = false;
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
      delete next.order_sns;
      delete next.porder_sn;
      delete next.porder_sns;
      delete next.shop_count;
      return next;
    }
    if (scriptType === "resume_porder_flow") {
      const next = { ...(variables || {}) };
      next.porder_sn = String(next.porder_sn || "").trim();
      next.stop_after_node = String(next.stop_after_node || "porder_offered").trim() || "porder_offered";
      next.run_backend_porder_flow = false;
      next.run_backend_flow = false;
      next.run_backend_delivery_flow = false;
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
      return next;
    }
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
    const env = dataScriptDefaultEnv(projects, envs);
    const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";
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

  function directBoxNumber(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? Math.floor(number) : fallback;
  }

  function normalizeDirectBoxes(rawBoxes, count = 1) {
    let source = rawBoxes;
    if (typeof source === "string") {
      try {
        source = JSON.parse(source);
      } catch {
        source = [];
      }
    }
    source = Array.isArray(source) ? source : [];
    const targetCount = directBoxNumber(count || source.length, 1);
    const fallback = source[0] || {};
    const result = [];
    for (let index = 0; index < targetCount; index += 1) {
      const item = source[index] || fallback || {};
      result.push({
        length: String(item.length || item.c || item.box_length || "10"),
        width: String(item.width || item.k || item.box_width || "20"),
        height: String(item.height || item.g || item.box_height || "30"),
        weight: String(item.weight || item.box_weight || "10"),
        item_count: item.item_count || item.num || "",
      });
    }
    return result;
  }

  function ensureDirectBoxToShelfScript(flows, projects, envs, cases) {
    if (isBuiltinDeleted("direct_box_to_shelf_builtin")) return flows;
    const scriptName = "直接装箱上架";
    const login = findCaseByName(cases, "登录");
    const search = findCaseByName(cases, "搜索商品");
    const detail = findCaseByName(cases, "商品详情");
    const cart = findCaseByName(cases, "加入购物车");
    const env = dataScriptDefaultEnv(projects, envs);
    const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";
    if (!env) return flows;
    const loginBody = parseJsonText(login?.body || "{}", {});
    const existingIndex =
      flows.findIndex((flow) => flow.id === "direct_box_to_shelf_builtin") >= 0
        ? flows.findIndex((flow) => flow.id === "direct_box_to_shelf_builtin")
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
      shop_type: "1688",
      shop_types: ["1688"],
      order_shop_count: 1,
      order_per_shop: 2,
      order_item_count: 2,
      order_item_num: 10,
      logistics_id: "1",
      submit_order: true,
      run_backend_flow: true,
      auto_fill_cart_on_shortage: true,
      purchase_unit_price: "10",
      purchase_freight: "0",
      warehouse_index: "2",
      box_count: 1,
      boxes: [{ length: "10", width: "20", height: "30", weight: "10", item_count: "" }],
      account: loginBody.account || "12345678990",
      password: loginBody.password || "123456",
      client_tool: "1",
      backend_account: "Y001",
      backend_password: "raku@123456``",
      backend_system: "1",
      backend_code: "wnm666",
    };
    const mergedVariables = sanitizeScriptVariables("direct_box_to_shelf", { ...defaultVariables, ...existingVariables }, existingFlow);
    const caseIds = [login, search, detail, cart].filter(Boolean).map((item) => item.id);
    const nextFlow = {
      ...existingFlow,
      id: "direct_box_to_shelf_builtin",
      name: existingFlow.name || scriptName,
      scriptType: "direct_box_to_shelf",
      projectId: String(projectId),
      envId: String(env.id),
      caseIds,
      variables: JSON.stringify(mergedVariables, null, 2),
    };
    const next =
      existingIndex >= 0
        ? flows.map((flow, index) => (index === existingIndex ? nextFlow : flow)).filter((flow, index) => index === existingIndex || flow.id !== "direct_box_to_shelf_builtin")
        : [...flows, nextFlow];
    writeFlows(next);
    return next;
  }

  function ensureResumeOrderFlowScript(flows, projects, envs, cases) {
    if (isBuiltinDeleted("resume_order_flow_builtin")) return flows;
    const scriptName = "输入订单号继续执行操作";
    const login = findCaseByName(cases, "登录");
    const env = dataScriptDefaultEnv(projects, envs);
    const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";
    if (!env) return flows;
    const loginBody = parseJsonText(login?.body || "{}", {});
    const existingIndex =
      flows.findIndex((flow) => flow.id === "resume_order_flow_builtin") >= 0
        ? flows.findIndex((flow) => flow.id === "resume_order_flow_builtin")
        : flows.findIndex((flow) => flow.name === scriptName);
    const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};
    let existingVariables = {};
    try {
      existingVariables = parseJsonText(existingFlow.variables || "{}", {});
    } catch {
      existingVariables = {};
    }
    const defaultVariables = {
      order_sn: "",
      purchase_no: "",
      order_item_num: 10,
      logistics_id: "1",
      run_backend_flow: true,
      run_backend_delivery_flow: true,
      run_backend_porder_flow: false,
      stop_after_node: "porder_offered",
      warehouse_sku_count: 1,
      send_num: 1,
      porder_logistics_id: "14",
      client_warehouse_list: "/client/wms.stockAutoList",
      porder_suffix: "300001",
      purchase_unit_price: "10",
      purchase_freight: "0",
      warehouse_index: "2",
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
    const mergedVariables = sanitizeScriptVariables("resume_order_flow", { ...defaultVariables, ...existingVariables }, existingFlow);
    const caseIds = [login].filter(Boolean).map((item) => item.id);
    const nextFlow = {
      ...existingFlow,
      id: "resume_order_flow_builtin",
      name: existingFlow.name || scriptName,
      scriptType: "resume_order_flow",
      projectId: String(projectId),
      envId: String(env.id),
      caseIds,
      variables: JSON.stringify(mergedVariables, null, 2),
    };
    const next =
      existingIndex >= 0
        ? flows.map((flow, index) => (index === existingIndex ? nextFlow : flow)).filter((flow, index) => index === existingIndex || flow.id !== "resume_order_flow_builtin")
        : [...flows, nextFlow];
    writeFlows(next);
    return next;
  }

  function ensureResumePorderFlowScript(flows, projects, envs, cases) {
    if (isBuiltinDeleted("resume_porder_flow_builtin")) return flows;
    const scriptName = "输入配送单号继续执行操作";
    const login = findCaseByName(cases, "登录");
    const env = dataScriptDefaultEnv(projects, envs);
    const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";
    if (!env) return flows;
    const loginBody = parseJsonText(login?.body || "{}", {});
    const existingIndex =
      flows.findIndex((flow) => flow.id === "resume_porder_flow_builtin") >= 0
        ? flows.findIndex((flow) => flow.id === "resume_porder_flow_builtin")
        : flows.findIndex((flow) => flow.name === scriptName);
    const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};
    let existingVariables = {};
    try {
      existingVariables = parseJsonText(existingFlow.variables || "{}", {});
    } catch {
      existingVariables = {};
    }
    const defaultVariables = {
      porder_sn: "",
      stop_after_node: "porder_offered",
      delivery_quote_logistics_id: "25",
      logistics_price_artificial: "775",
      logistics_id: "1",
      porder_logistics_id: "14",
      purchase_unit_price: "10",
      purchase_freight: "0",
      warehouse_index: "2",
      box_count: 1,
      box_length: "58",
      box_width: "51",
      box_height: "50",
      box_weight: "10",
      finance_confirm: true,
      account: loginBody.account || "12345678990",
      password: loginBody.password || "123456",
      client_tool: "1",
      backend_account: "Y001",
      backend_password: "raku@123456``",
      backend_system: "1",
      backend_code: "wnm666",
    };
    const mergedVariables = sanitizeScriptVariables("resume_porder_flow", { ...defaultVariables, ...existingVariables }, existingFlow);
    const caseIds = [login].filter(Boolean).map((item) => item.id);
    const nextFlow = {
      ...existingFlow,
      id: "resume_porder_flow_builtin",
      name: existingFlow.name || scriptName,
      scriptType: "resume_porder_flow",
      projectId: String(projectId),
      envId: String(env.id),
      caseIds,
      variables: JSON.stringify(mergedVariables, null, 2),
    };
    const next =
      existingIndex >= 0
        ? flows.map((flow, index) => (index === existingIndex ? nextFlow : flow)).filter((flow, index) => index === existingIndex || flow.id !== "resume_porder_flow_builtin")
        : [...flows, nextFlow];
    writeFlows(next);
    return next;
  }

  const originalEnsureWarehouseDeliveryScriptForFullFlow = ensureWarehouseDeliveryScript;
  ensureWarehouseDeliveryScript = function (flows, projects, envs, cases) {
    return ensureResumePorderFlowScript(
      ensureResumeOrderFlowScript(
        ensureDirectBoxToShelfScript(
          ensureFullFlowScript(originalEnsureWarehouseDeliveryScriptForFullFlow(flows, projects, envs, cases), projects, envs, cases),
          projects,
          envs,
          cases,
        ),
        projects,
        envs,
        cases,
      ),
      projects,
      envs,
      cases,
    );
  };

  function directBoxRowsHtml(boxes) {
    return boxes
      .map(
        (box, index) => `
          <tr class="direct-box-row" data-index="${index}">
            <td>${index + 1}</td>
            <td><input name="direct_length_${index}" type="number" min="1" value="${escapeHtml(box.length || "10")}" /></td>
            <td><input name="direct_width_${index}" type="number" min="1" value="${escapeHtml(box.width || "20")}" /></td>
            <td><input name="direct_height_${index}" type="number" min="1" value="${escapeHtml(box.height || "30")}" /></td>
            <td><input name="direct_weight_${index}" type="number" min="0.01" step="0.01" value="${escapeHtml(box.weight || "10")}" /></td>
            <td><input name="direct_item_count_${index}" type="number" min="1" value="${escapeHtml(box.item_count || "")}" placeholder="自动" /></td>
          </tr>
        `,
      )
      .join("");
  }

  function readDirectBoxes(form) {
    return Array.from(form.querySelectorAll(".direct-box-row")).map((row, index) => ({
      length: String(row.querySelector(`[name="direct_length_${index}"]`)?.value || "10").trim() || "10",
      width: String(row.querySelector(`[name="direct_width_${index}"]`)?.value || "20").trim() || "20",
      height: String(row.querySelector(`[name="direct_height_${index}"]`)?.value || "30").trim() || "30",
      weight: String(row.querySelector(`[name="direct_weight_${index}"]`)?.value || "10").trim() || "10",
      item_count: String(row.querySelector(`[name="direct_item_count_${index}"]`)?.value || "").trim(),
    }));
  }

  function openDirectBoxRunForm(flow, fields) {
    let variables = {};
    try {
      variables = parseJsonText(flow.variables || "{}", {});
    } catch {
      showToast("脚本变量不是合法 JSON");
      return;
    }
    variables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables("direct_box_to_shelf", variables, flow)));
    const values = {
      ...paramFormValues(fields, variables),
      __save_defaults: false,
    };
    const baseFields = fields.filter((field) => field.name !== "box_count");
    const boxCountField = fields.find((field) => field.name === "box_count");
    const boxes = normalizeDirectBoxes(variables.boxes, values.box_count || variables.box_count || 1);
    modalEl.innerHTML = `
      <form id="directBoxRunForm">
        <div class="modal-head">
          <h3>${escapeHtml(`执行 ${flow.name || "直接装箱上架"}`)}</h3>
          <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>
        </div>
        <div class="modal-body">
          <div class="form-grid">
            ${baseFields.map((field) => renderFormField(field, values?.[field.name] ?? field.default ?? "")).join("")}
            ${boxCountField ? renderFormField(boxCountField, values.box_count || 1) : ""}
            <label class="check-field">
              <input name="__save_defaults" type="checkbox" />
              <span>保存为默认值</span>
            </label>
          </div>
          <details class="functional-requirement" open>
            <summary>箱子配置</summary>
            <div class="actions" style="margin:10px 0">
              <button class="btn secondary" id="applyFirstDirectBox" type="button">套用第一箱</button>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>箱号</th>
                    <th>长</th>
                    <th>宽</th>
                    <th>高</th>
                    <th>重量(kg)</th>
                    <th>装商品数</th>
                  </tr>
                </thead>
                <tbody id="directBoxRows">${directBoxRowsHtml(boxes)}</tbody>
              </table>
            </div>
          </details>
        </div>
        <div class="modal-foot"><span></span><button class="btn" type="submit">执行</button></div>
      </form>
    `;
    modalEl.showModal();
    const form = document.querySelector("#directBoxRunForm");
    const rowsEl = document.querySelector("#directBoxRows");
    const boxCountEl = form.querySelector('[name="box_count"]');
    function syncRows() {
      const current = readDirectBoxes(form);
      const count = normalizePositiveInt(boxCountEl?.value || current.length, 1);
      rowsEl.innerHTML = directBoxRowsHtml(normalizeDirectBoxes(current, count));
    }
    document.querySelector("#closeModal").addEventListener("click", async () => {
      modalEl.close();
      if (state.view === "dataScripts" && !state.factory.editing) {
        await renderDataScripts();
      }
    });
    boxCountEl?.addEventListener("change", syncRows);
    boxCountEl?.addEventListener("input", syncRows);
    document.querySelector("#applyFirstDirectBox").addEventListener("click", () => {
      const current = readDirectBoxes(form);
      if (!current.length) return;
      rowsEl.innerHTML = directBoxRowsHtml(current.map((box, index) => (index === 0 ? box : { ...current[0], item_count: box.item_count })));
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = readForm(form);
        let next = sanitizeScriptVariables("direct_box_to_shelf", mergeParamValues(variables, fields, data), flow);
        next.boxes = readDirectBoxes(form);
        next.box_count = next.boxes.length;
        next = withCustomerLoginInputs(mergeStoredCustomerIds(next));
        if (data.__save_defaults) saveFlowVariables(flow, next);
        await runSavedFlow(flow, next);
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  function openFullFlowRunForm(flow, fields) {
    let variables = {};
    try {
      variables = parseJsonText(flow.variables || "{}", {});
    } catch {
      showToast("脚本变量不是合法 JSON");
      return;
    }
    variables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables("full_flow", variables, flow)));
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
      return withCustomerLoginInputs(mergeStoredCustomerIds(next));
    }
    async function refreshOptions() {
      const counts = readOrderOptionCounts(form);
      previewEl.innerHTML = `<div class="empty">正在读取订单 option...</div>`;
      try {
        const result = await api("/api/data-scripts/order-quote/options-preview", {
          method: "POST",
          body: {
            project_id: flow.projectId ? Number(flow.projectId) : null,
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

  function openResumeOrderRunForm(flow, fields) {
    let variables = {};
    try {
      variables = parseJsonText(flow.variables || "{}", {});
    } catch {
      showToast("脚本变量不是合法 JSON");
      return;
    }
    variables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables("resume_order_flow", variables, flow)));
    const values = {
      ...paramFormValues(fields, variables),
      __save_defaults: false,
    };
    const body = [...fields, { name: "__save_defaults", label: "保存为默认值", type: "checkbox", default: false }]
      .map((field) => renderFormField(field, values?.[field.name] ?? field.default ?? ""))
      .join("");
    modalEl.innerHTML = `
      <form id="resumeOrderRunForm">
        <div class="modal-head">
          <h3>${escapeHtml(`执行 ${flow.name || "输入订单号继续执行操作"}`)}</h3>
          <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>
        </div>
        <div class="modal-body">
          <div class="form-grid">${body}</div>
        </div>
        <div class="modal-foot"><span></span><button class="btn" type="submit">执行</button></div>
      </form>
    `;
    modalEl.showModal();
    const form = document.querySelector("#resumeOrderRunForm");
    document.querySelector("#closeModal").addEventListener("click", async () => {
      modalEl.close();
      if (state.view === "dataScripts" && !state.factory.editing) {
        await renderDataScripts();
      }
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = readForm(form);
        const next = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables("resume_order_flow", mergeParamValues(variables, fields, data), flow)));
        if (!String(next.order_sn || "").trim()) throw new Error("请输入订单号");
        if (data.__save_defaults) saveFlowVariables(flow, next);
        await runSavedFlow(flow, next);
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  function openResumePorderRunForm(flow, fields) {
    let variables = {};
    try {
      variables = parseJsonText(flow.variables || "{}", {});
    } catch {
      showToast("脚本变量不是合法 JSON");
      return;
    }
    variables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables("resume_porder_flow", variables, flow)));
    const values = {
      ...paramFormValues(fields, variables),
      __save_defaults: false,
    };
    const body = [...fields, { name: "__save_defaults", label: "保存为默认值", type: "checkbox", default: false }]
      .map((field) => renderFormField(field, values?.[field.name] ?? field.default ?? ""))
      .join("");
    modalEl.innerHTML = `
      <form id="resumePorderRunForm">
        <div class="modal-head">
          <h3>${escapeHtml(`执行 ${flow.name || "输入配送单号继续执行操作"}`)}</h3>
          <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>
        </div>
        <div class="modal-body">
          <div class="form-grid">${body}</div>
        </div>
        <div class="modal-foot"><span></span><button class="btn" type="submit">执行</button></div>
      </form>
    `;
    modalEl.showModal();
    const form = document.querySelector("#resumePorderRunForm");
    document.querySelector("#closeModal").addEventListener("click", async () => {
      modalEl.close();
      if (state.view === "dataScripts" && !state.factory.editing) {
        await renderDataScripts();
      }
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = readForm(form);
        const next = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables("resume_porder_flow", mergeParamValues(variables, fields, data), flow)));
        if (!String(next.porder_sn || "").trim()) throw new Error("请输入配送单号");
        if (data.__save_defaults) saveFlowVariables(flow, next);
        await runSavedFlow(flow, next);
      } catch (error) {
        showToast(error.message);
      }
    });
  }

  const originalOpenRunScriptFormForFullFlow = openRunScriptForm;
  openRunScriptForm = function (flow) {
    if (flow?.scriptType === "direct_box_to_shelf") {
      openDirectBoxRunForm(flow, scriptParamFields("direct_box_to_shelf", flow));
      return;
    }
    if (flow?.scriptType === "full_flow") {
      openFullFlowRunForm(flow, scriptParamFields("full_flow", flow));
      return;
    }
    if (flow?.scriptType === "resume_order_flow") {
      openResumeOrderRunForm(flow, scriptParamFields("resume_order_flow", flow));
      return;
    }
    if (flow?.scriptType === "resume_porder_flow") {
      openResumePorderRunForm(flow, scriptParamFields("resume_porder_flow", flow));
      return;
    }
    return originalOpenRunScriptFormForFullFlow(flow);
  };

  const originalRunSavedFlowForFullFlow = runSavedFlow;
  runSavedFlow = async function (flow, runtimeVariables = null, options = {}) {
    if (flow?.scriptType !== "full_flow" && flow?.scriptType !== "direct_box_to_shelf" && flow?.scriptType !== "resume_order_flow" && flow?.scriptType !== "resume_porder_flow") {
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
    if (flow?.scriptType === "direct_box_to_shelf") {
      variables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables("direct_box_to_shelf", variables, flow)));
      const customerIds = customerIdsFromVariables(variables);
      if (customerIds.length > 1 && !options.singleCustomerRun) {
        await runMultiCustomerFlow(flow, variables, customerIds);
        return;
      }
      if (customerIds.length === 1) variables = variablesForCustomerId(variables, customerIds[0]);
      const progress = options.progress || openScriptProgress("直接装箱上架执行进度", "正在准备订单、核查、装箱和上架...");
      try {
        showToast("直接装箱上架脚本执行中，请稍候");
        progress.update(10, "正在执行前置流程并进入开始核查...");
        const result = await api("/api/data-scripts/direct-box-to-shelf", {
          method: "POST",
          body: {
            project_id: flow.projectId ? Number(flow.projectId) : null,
            env_id: flow.envId ? Number(flow.envId) : null,
            variables,
          },
        });
        const summary = result.summary || {};
        const orderSn = summary.order_sn || "";
        const purchaseNo = summary.purchase_no || "";
        const flows = readFlows().map((item) =>
          item.id === flow.id
            ? {
                ...item,
                lastOrderSn: orderSn || item.lastOrderSn || "",
                lastPurchaseNo: purchaseNo || item.lastPurchaseNo || "",
                lastRecordId: result.id,
              }
            : item,
        );
        writeFlows(flows);
        flow.lastOrderSn = orderSn || flow.lastOrderSn || "";
        flow.lastPurchaseNo = purchaseNo || flow.lastPurchaseNo || "";
        flow.lastRecordId = result.id;
        progress.success("直接装箱上架脚本执行完成，正在展示结果...");
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
      return;
    }
    if (flow?.scriptType === "resume_order_flow") {
      variables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables("resume_order_flow", variables, flow)));
      const customerIds = customerIdsFromVariables(variables);
      if (customerIds.length > 1 && !options.singleCustomerRun) {
        await runMultiCustomerFlow(flow, variables, customerIds);
        return;
      }
      if (customerIds.length === 1) variables = variablesForCustomerId(variables, customerIds[0]);
      if (!String(variables.order_sn || "").trim()) {
        showToast("请输入订单号");
        return;
      }
      const progress = options.progress || openScriptProgress("输入订单号继续执行操作进度", "正在判断订单状态并继续执行到配送单报价完成...");
      try {
        showToast("继续执行订单流程中，请稍等");
        progress.update(10, "正在识别订单所在节点...");
        const result = await api("/api/data-scripts/resume-order-flow", {
          method: "POST",
          body: {
            project_id: flow.projectId ? Number(flow.projectId) : null,
            env_id: flow.envId ? Number(flow.envId) : null,
            variables,
          },
        });
        const summary = result.summary || {};
        const orderSn = summary.order_sn || variables.order_sn || "";
        const purchaseNo = summary.purchase_no || "";
        const porderSn = summary.porder_sn || "";
        const flows = readFlows().map((item) =>
          item.id === flow.id
            ? {
                ...item,
                lastOrderSn: orderSn || item.lastOrderSn || "",
                lastPurchaseNo: purchaseNo || item.lastPurchaseNo || "",
                lastPorderSn: porderSn || item.lastPorderSn || "",
                lastRecordId: result.id,
              }
            : item,
        );
        writeFlows(flows);
        flow.lastOrderSn = orderSn || flow.lastOrderSn || "";
        flow.lastPurchaseNo = purchaseNo || flow.lastPurchaseNo || "";
        flow.lastPorderSn = porderSn || flow.lastPorderSn || "";
        flow.lastRecordId = result.id;
        progress.success(summary.paused ? `已按暂停节点停止：${summary.node_label || summary.current_node || ""}` : "订单继续执行完成，正在展示结果...");
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
      return;
    }
    if (flow?.scriptType === "resume_porder_flow") {
      variables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables("resume_porder_flow", variables, flow)));
      const customerIds = customerIdsFromVariables(variables);
      if (customerIds.length > 1 && !options.singleCustomerRun) {
        await runMultiCustomerFlow(flow, variables, customerIds);
        return;
      }
      if (customerIds.length === 1) variables = variablesForCustomerId(variables, customerIds[0]);
      if (!String(variables.porder_sn || "").trim()) {
        showToast("请输入配送单号");
        return;
      }
      const progress = options.progress || openScriptProgress("输入配送单号继续执行操作进度", "正在判断配送单状态并继续执行到配送单支付完成...");
      try {
        showToast("继续执行配送单流程中，请稍等");
        progress.update(10, "正在识别配送单所在节点...");
        const result = await api("/api/data-scripts/resume-porder-flow", {
          method: "POST",
          body: {
            project_id: flow.projectId ? Number(flow.projectId) : null,
            env_id: flow.envId ? Number(flow.envId) : null,
            variables,
          },
        });
        const summary = result.summary || {};
        const porderSn = summary.porder_sn || variables.porder_sn || "";
        const flows = readFlows().map((item) =>
          item.id === flow.id
            ? {
                ...item,
                lastPorderSn: porderSn || item.lastPorderSn || "",
                lastRecordId: result.id,
              }
            : item,
        );
        writeFlows(flows);
        flow.lastPorderSn = porderSn || flow.lastPorderSn || "";
        flow.lastRecordId = result.id;
        progress.success(summary.paused ? `已按暂停节点停止：${summary.node_label || summary.current_node || ""}` : "配送单继续执行完成，正在展示结果...");
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
      return;
    }
    variables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables("full_flow", variables, flow)));
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
          project_id: flow.projectId ? Number(flow.projectId) : null,
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

// 确保配送单继续执行脚本存在于 localStorage
(function ensureResumePorderFlowOnLoad() {
  try {
    const flows = readFlows();
    if (flows.some(function (f) { return f.id === "resume_porder_flow_builtin" || f.name === "输入配送单号继续执行操作"; })) return;
    flows.push({
      id: "resume_porder_flow_builtin",
      name: "输入配送单号继续执行操作",
      scriptType: "resume_porder_flow",
      projectId: "",
      envId: "",
      caseIds: [],
      variables: JSON.stringify({ porder_sn: "", stop_after_node: "porder_offered" }),
    });
    writeFlows(flows);
  } catch (e) {
    console.warn("ensureResumePorderFlowOnLoad error:", e);
  }
})();
