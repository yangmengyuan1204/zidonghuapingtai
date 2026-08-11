if (!window.__paymentAmountRegressionLoaded) {
  window.__paymentAmountRegressionLoaded = true;

  const PAYMENT_AMOUNT_REGRESSION_ID = "payment_amount_regression_builtin";
  const PAYMENT_AMOUNT_REGRESSION_NAME = "支付金额自动回归";

  BUILTIN_FLOW_DEFINITIONS.payment_amount_regression = {
    id: PAYMENT_AMOUNT_REGRESSION_ID,
    name: PAYMENT_AMOUNT_REGRESSION_NAME,
  };
  if (!BUILTIN_DATA_SCRIPT_TYPES.includes("payment_amount_regression")) {
    BUILTIN_DATA_SCRIPT_TYPES.push("payment_amount_regression");
  }

  SCRIPT_PARAM_SCHEMAS.payment_amount_regression = [
    CUSTOMER_ID_FIELD,
    { name: "payment_regression_scenario_order_balance", label: "普通订单：余额支付", type: "checkbox", default: true },
    { name: "payment_regression_scenario_order_bank", label: "普通订单：银行支付", type: "checkbox", default: true },
    { name: "payment_regression_scenario_order_part_balance", label: "分批付款：余额首尾款", type: "checkbox", default: true },
    { name: "payment_regression_scenario_order_part_bank", label: "分批付款：银行首尾款", type: "checkbox", default: true },
    { name: "payment_regression_scenario_porder_balance", label: "配送单：余额支付", type: "checkbox", default: true },
    { name: "payment_regression_scenario_porder_bank", label: "配送单：银行支付", type: "checkbox", default: true },
    { name: "payment_regression_scenario_problem_quantity_refund", label: "问题产品：数量减少退款", type: "checkbox", default: true },
    { name: "payment_regression_scenario_problem_price_refund", label: "问题产品：单价下调退款", type: "checkbox", default: true },
    { name: "payment_regression_scenario_problem_freight_refund", label: "问题产品：运费下调退款", type: "checkbox", default: true },
    { name: "payment_regression_scenario_problem_option_topup", label: "问题产品：OPTION 费用增加补款", type: "checkbox", default: true },
    { name: "payment_regression_scenario_problem_mixed_refund", label: "问题产品：混合调整退款", type: "checkbox", default: true },
    { name: "payment_regression_scenario_problem_zero_control", label: "问题产品：零金额对照", type: "checkbox", default: true },
    { name: "keyword", label: "造单关键词", default: "衣服" },
    { name: "payment_regression_offer_price", label: "单件报价（人民币）", type: "number", default: 10 },
    { name: "payment_regression_item_num", label: "单商品数量", type: "number", default: 3 },
    { name: "payment_regression_part_pay_percent", label: "首款比例（%）", type: "number", default: 50 },
    { name: "payment_regression_evidence_retries", label: "流水轮询次数", type: "number", default: 6 },
    { name: "payment_regression_evidence_delay", label: "轮询间隔（秒）", type: "number", default: 2 },
  ];

  function ensurePaymentAmountRegressionScript(flows, projects, envs, cases) {
    if (isBuiltinDeleted(PAYMENT_AMOUNT_REGRESSION_ID)) return flows;
    const env = dataScriptDefaultEnv(projects, envs);
    if (!env) return flows;
    const projectId = env.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";
    const login = findCaseByName(cases, "登录");
    const search = findCaseByName(cases, "搜索商品");
    const detail = findCaseByName(cases, "商品详情");
    const cart = findCaseByName(cases, "加入购物车");
    const loginBody = parseJsonText(login?.body || "{}", {});
    const existingIndex = flows.findIndex(
      (flow) => flow.id === PAYMENT_AMOUNT_REGRESSION_ID || flow.name === PAYMENT_AMOUNT_REGRESSION_NAME,
    );
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
      target_shops: 1,
      per_shop: 2,
      quantities: "3,5,8",
      order_shop_count: 1,
      order_per_shop: 2,
      order_item_count: 2,
      order_item_num: 3,
      logistics_id: "1",
      create_type: "send",
      submit_order: true,
      run_backend_flow: true,
      run_backend_delivery_flow: true,
      purchase_unit_price: "10",
      purchase_freight: "3",
      warehouse_index: "2",
      warehouse_sku_count: 1,
      send_num: 1,
      porder_logistics_id: "14",
      box_count: "1",
      box_length: "58",
      box_width: "51",
      box_height: "50",
      box_weight: "10",
      delivery_quote_logistics_id: "25",
      logistics_price_artificial: "775",
      payment_regression_offer_price: 10,
      payment_regression_item_num: 3,
      payment_regression_part_pay_percent: 50,
      payment_regression_evidence_retries: 6,
      payment_regression_evidence_delay: 2,
      account: loginBody.account || "12345678990",
      password: loginBody.password || "123456",
      client_tool: "1",
    };
    const nextFlow = {
      ...existingFlow,
      id: PAYMENT_AMOUNT_REGRESSION_ID,
      name: existingFlow.name || PAYMENT_AMOUNT_REGRESSION_NAME,
      scriptType: "payment_amount_regression",
      projectId: String(projectId),
      envId: String(env.id),
      caseIds: [login, search, detail, cart].filter(Boolean).map((item) => item.id),
      variables: JSON.stringify({ ...defaultVariables, ...existingVariables }, null, 2),
    };
    const next = existingIndex >= 0
      ? flows.map((flow, index) => (index === existingIndex ? nextFlow : flow))
      : [...flows, nextFlow];
    writeFlows(next);
    return next;
  }

  const originalEnsureWarehouseDeliveryScriptForPaymentRegression = ensureWarehouseDeliveryScript;
  ensureWarehouseDeliveryScript = function (flows, projects, envs, cases) {
    return ensurePaymentAmountRegressionScript(
      originalEnsureWarehouseDeliveryScriptForPaymentRegression(flows, projects, envs, cases),
      projects,
      envs,
      cases,
    );
  };

  const originalRunSavedFlowForPaymentRegression = runSavedFlow;
  runSavedFlow = async function (flow, runtimeVariables = null, options = {}) {
    if (flow?.scriptType !== "payment_amount_regression") {
      return originalRunSavedFlowForPaymentRegression(flow, runtimeVariables, options);
    }
    let variables = {};
    try {
      variables = runtimeVariables ? { ...runtimeVariables } : parseJsonText(flow.variables || "{}", {});
    } catch {
      showToast("脚本变量不是合法 JSON");
      return;
    }
    variables = withCustomerLoginInputs(mergeStoredCustomerIds(variables));
    const customerIds = customerIdsFromVariables(variables);
    if (customerIds.length > 1) {
      showToast("支付金额回归每批次只支持一个客户，请保留一个客户ID");
      return;
    }
    if (customerIds.length === 1) variables = variablesForCustomerId(variables, customerIds[0]);
    const scenarioFields = SCRIPT_PARAM_SCHEMAS.payment_amount_regression.filter(
      (field) => field.name.startsWith("payment_regression_scenario_"),
    );
    const selectedScenarioCount = scenarioFields.filter(
      (field) => boolValue(variables[field.name], boolValue(field.default, true)),
    ).length;
    if (!selectedScenarioCount) {
      showToast("请至少勾选一个支付金额回归场景");
      return;
    }
    const confirmMessage = selectedScenarioCount === 12
      ? "本次将创建并保留 12 张业务订单，并顺序执行全部金额场景。确认继续吗？"
      : `本次将创建并保留 ${selectedScenarioCount} 张业务订单。确认继续吗？`;
    if (!window.confirm(confirmMessage)) return;

    const progress = options.progress || openScriptProgress(
      "支付金额自动回归",
      `将顺序执行 ${selectedScenarioCount} 个独立订单场景，单场景失败后继续`,
    );
    try {
      showToast("支付金额回归执行中，请稍候");
      progress.update(5, "正在创建独立订单并采集报价、预期金额和实际流水证据...");
      const result = await api("/api/data-scripts/payment-amount-regression", {
        method: "POST",
        body: {
          project_id: flow.projectId ? Number(flow.projectId) : null,
          env_id: flow.envId ? Number(flow.envId) : null,
          variables,
        },
      });
      const summary = result.summary || {};
      const nextFlows = readFlows().map((item) =>
        item.id === flow.id ? { ...item, lastRecordId: result.id } : item,
      );
      writeFlows(nextFlows);
      flow.lastRecordId = result.id;
      if (Number(summary.failed_count || 0) || Number(summary.blocked_count || 0)) {
        progress.fail(`执行完成：通过 ${summary.passed_count || 0}，失败 ${summary.failed_count || 0}，阻塞 ${summary.blocked_count || 0}`);
      } else {
        progress.success(`${summary.scenario_count || selectedScenarioCount} 个场景全部通过，正在展示汇总...`);
      }
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
