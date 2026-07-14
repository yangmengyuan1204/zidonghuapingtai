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
  const FULL_FLOW_COPY_NAME = "全流程完全体_副本";
  const FULL_FLOW_COPY_ALIASES = new Set([
    FULL_FLOW_COPY_NAME,
    "全流程脚本可根据订单和配送单输入后继续执行",
  ]);
  const FULL_FLOW_PAYMENT_MODE_OPTIONS = [
    { value: "balance_first", label: "余额支付（余额不足自动银行支付）" },
    { value: "bank", label: "银行支付" },
  ];
  const FULL_FLOW_SHELF_TYPE_OPTIONS = [
    { value: "1,3", label: "默认上架类型（1,3）" },
  ];
  const FULL_FLOW_DELIVERY_QUOTE_LOGISTICS_OPTIONS = [
    { value: "14", label: "お任せ(お勧め)（ID 14）" },
    { value: "24", label: "KS-JP航空経済便（ID 24）" },
    { value: "20", label: "RW船便（ID 20）" },
    { value: "30", label: "Rロジ専用船便（ID 30）" },
    { value: "29", label: "海源電子特殊航空便（ID 29）" },
    { value: "25", label: "KS-JP電子特殊便（ID 25）" },
    { value: "23", label: "Raku-DQ（ID 23）" },
    { value: "18", label: "KS-JP航空便（ID 18）" },
    { value: "1", label: "EMS（ID 1）" },
    { value: "3", label: "EMS船便（ID 3）" },
    { value: "2", label: "OCS（ID 2）" },
    { value: "4", label: "電子特殊便（ID 4）" },
    { value: "12", label: "TW船便（ID 12）" },
    { value: "15", label: "海源DQ船便（ID 15）" },
    { value: "22", label: "海源TK船便（ID 22）" },
    { value: "21", label: "DHL（ID 21）" },
    { value: "6", label: "FBA新幹線（ID 6）" },
    { value: "8", label: "コンテナ（ID 8）" },
    { value: "13", label: "その他（ID 13）" },
    { value: "19", label: "海源 LCLコンテナ混載便（ID 19）" },
  ];

  SCRIPT_PARAM_SCHEMAS.full_flow = [
    CUSTOMER_ID_FIELD,
    { name: "order_sn", label: "订单号（继续执行）" },
    { name: "porder_sn", label: "配送单号（继续执行，优先）" },
    { name: "keyword", label: "关键词", default: "衣服" },
    { name: "shop_type", label: "商品来源", type: "select", options: SHOP_TYPE_OPTIONS, default: "1688" },
    { name: "target_shops", label: "补货目标店铺数", type: "number", default: 1 },
    { name: "per_shop", label: "补货每店商品数", type: "number", default: 2 },
    { name: "quantities", label: "补货商品数量", default: "2,3,5" },
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
    { name: "warehouse_sku_count", label: "仓库提出番数", type: "number", default: 1 },
    { name: "send_num", label: "每番配送数量", type: "number", default: 1 },
    { name: "stop_after_node", label: "暂停节点", type: "select", options: RESUME_ORDER_STOP_NODE_OPTIONS, default: "porder_offered" },
  ];

  SCRIPT_PARAM_SCHEMAS.resume_porder_flow = [
    CUSTOMER_ID_FIELD,
    { name: "porder_sn", label: "配送单号", required: true },
    { name: "stop_after_node", label: "暂停节点", type: "select", options: RESUME_PORDER_STOP_NODE_OPTIONS, default: "porder_offered" },
  ];

  const FULL_FLOW_COPY_FIELD_GROUPS = [
    {
      title: "继续执行",
      open: true,
      fields: [
        { name: "order_sn", label: "订单号（继续执行）" },
        { name: "porder_sn", label: "配送单号（继续执行，优先）" },
      ],
    },
    {
      title: "订单提单",
      fields: [
        { name: "order_shop_count", label: "订单店铺数", type: "number", default: 1 },
        { name: "order_per_shop", label: "订单每店商品数", type: "number", default: 2 },
        { name: "order_item_num", label: "每个商品数量", type: "number", default: 10 },
        { name: "client_remark", label: "提单备注", default: "自动化提出订单" },
      ],
    },
    {
      title: "订单翻译",
      fields: [{ name: "translate_remark", label: "翻译备注", default: "自动化订单翻译" }],
    },
    {
      title: "订单确认",
      open: true,
      fields: [
        { name: "confirm_price", label: "实际采购价", type: "number", default: 10 },
        { name: "confirm_freight", label: "确认国内运费", type: "number", default: 5 },
        { name: "confirm_volume", label: "单个商品尺寸", type: "dimension", default: "1x2x3" },
        { name: "confirm_weight", label: "重量（g）", type: "number", default: 200 },
        { name: "confirm_remark", label: "采购调查备注", default: "自动化采购调查" },
      ],
    },
    {
      title: "订单报价",
      fields: [
        { name: "offer_num", label: "报价在库数", type: "number", placeholder: "留空沿用确认数量" },
        { name: "offer_price", label: "报价单价", type: "number", default: 10 },
        { name: "offer_freight", label: "报价国内运费", type: "number", default: 5 },
        { name: "other_price", label: "其他费用", type: "number", default: 0 },
        { name: "other_price_remark", label: "其他费用备注", default: "自动化其他费用备注" },
        { name: "offer_remark", label: "业务报价备注", default: "自动化业务报价" },
      ],
    },
    {
      title: "订单支付",
      fields: [
        { name: "discounts_id", label: "余额优惠ID" },
        { name: "order_payment_mode", label: "支付方式", type: "select", options: FULL_FLOW_PAYMENT_MODE_OPTIONS, default: "balance_first" },
        { name: "pay_name", label: "付款人", default: "自动化测试" },
        { name: "pay_remark", label: "付款备注", default: "自动化银行付款" },
      ],
    },
    {
      title: "待拍下采购",
      fields: [
        { name: "purchase_no", label: "交易号" },
        { name: "purchase_unit_price", label: "实际采购价", type: "number", default: 10 },
        { name: "purchase_freight", label: "国内运费", type: "number", default: 0 },
        { name: "express_no", label: "快递单号" },
      ],
    },
    {
      title: "核查上架",
      fields: [
        { name: "grid_id", label: "指定库位ID（留空自动选择）" },
        { name: "warehouse_index", label: "自动库位分组", default: "2", placeholder: "默认第2组" },
        { name: "shelf_type_set", label: "上架类型", type: "select", options: FULL_FLOW_SHELF_TYPE_OPTIONS, default: "1,3" },
        { name: "warehouse_user_id", label: "仓库操作人ID（留空自动识别）" },
      ],
    },
    {
      title: "仓库提出配送单",
      fields: [
        { name: "warehouse_sku_count", label: "仓库提出番数", type: "number", default: 1 },
        { name: "send_num", label: "每番配送数量", type: "number", default: 1 },
        { name: "porder_detail_remark", label: "配送单明细备注", default: "自动化配送单明细备注" },
      ],
    },
    {
      title: "配送单翻译/装箱",
      fields: [
        { name: "client_remark_translate", label: "客户翻译备注", default: "自动化配送单翻译" },
        { name: "porder_y_remark", label: "后台配货备注", default: "自动化装箱" },
        { name: "box_count", label: "箱子数量", type: "number", default: 1 },
        { name: "box_length", label: "箱长", type: "number", default: 58 },
        { name: "box_width", label: "箱宽", type: "number", default: 51 },
        { name: "box_height", label: "箱高", type: "number", default: 50 },
        { name: "box_weight", label: "箱重（KG）", type: "number", default: 10 },
      ],
    },
    {
      title: "配送单报价",
      fields: [
        { name: "delivery_quote_logistics_id", label: "国际物流方式", type: "select", options: FULL_FLOW_DELIVERY_QUOTE_LOGISTICS_OPTIONS, default: "25" },
        { name: "logistics_price_artificial", label: "人工物流费", type: "number", default: 775 },
        { name: "porder_offer_remark", label: "报价备注", default: "自动化配送单报价" },
        { name: "fba_complete_num", label: "FBA完成数量", type: "number", default: 0 },
      ],
    },
    {
      title: "配送单支付",
      fields: [
        { name: "porder_payment_mode", label: "支付方式", type: "select", options: FULL_FLOW_PAYMENT_MODE_OPTIONS, default: "balance_first" },
        { name: "merge_pay", label: "合并支付", default: "0" },
      ],
    },
    {
      title: "执行控制",
      fields: [{ name: "stop_after_node", label: "暂停节点", type: "select", options: FULL_FLOW_STOP_NODE_OPTIONS, default: "full_complete" }],
    },
  ];

  const FULL_FLOW_COPY_FIELDS = FULL_FLOW_COPY_FIELD_GROUPS.flatMap((group) => group.fields);
  const FULL_FLOW_COPY_REMARK_DEFAULTS = Object.fromEntries(
    FULL_FLOW_COPY_FIELDS
      .filter((field) => String(field.label || "").includes("备注") && field.default !== undefined)
      .map((field) => [field.name, field.default]),
  );
  const FULL_FLOW_SAVE_DEFAULTS_FIELD = { name: "__save_defaults", label: "保存为默认值", type: "checkbox", default: false };
  const FULL_FLOW_PART_PAY_SCRIPT_ID = "full_flow_part_pay_builtin";
  const FULL_FLOW_PART_PAY_SCRIPT_NAME = "全流程加入分批付款";
  const FULL_FLOW_PART_PAY_PERCENT_OPTIONS = Array.from({ length: 21 }, (_, index) => index * 5);
  const FULL_FLOW_PART_PAY_TAIL_NODE_OPTIONS = [
    { value: "before_shelf", label: "上架仓库前" },
    { value: "before_porder_create", label: "提出配送单前" },
  ];
  const FULL_FLOW_PART_PAY_FEE_FIELDS = [
    { key: "domestic_freight", label: "国内运费", amountKeys: ["offer_freight", "confirm_freight"] },
    { key: "service_fee", label: "手续费", amountKeys: ["service_fee", "handling_fee"] },
    { key: "additional_service_fee", label: "附加服务费", amountKeys: ["additional_service_fee", "added_service_fee"] },
    { key: "other_fee", label: "其他费用", amountKeys: ["other_price"] },
  ];

  function isFullFlowCopy(flow) {
    if (flow?.scriptType !== "full_flow") return false;
    const name = String(flow?.name || "").trim();
    if (FULL_FLOW_COPY_ALIASES.has(name)) return true;
    const builtin = BUILTIN_FLOW_DEFINITIONS.full_flow;
    return flow?.id !== builtin?.id && name !== builtin?.name;
  }

  function isFullFlowPartPayScript(flow) {
    return flow?.scriptType === "full_flow" && (flow?.id === FULL_FLOW_PART_PAY_SCRIPT_ID || String(flow?.name || "").trim() === FULL_FLOW_PART_PAY_SCRIPT_NAME);
  }

  function fullFlowPartPayPercent(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return 10;
    const normalized = Math.round(Math.max(0, Math.min(100, number)) / 5) * 5;
    return Math.max(0, Math.min(100, normalized));
  }

  function fullFlowPartPayFeeTiming(value) {
    const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    return Object.fromEntries(
      FULL_FLOW_PART_PAY_FEE_FIELDS.map((field) => {
        const timing = String(source[field.key] || "first").trim();
        return [field.key, timing === "tail" || timing === "尾款支付" ? "tail" : "first"];
      }),
    );
  }

  function fullFlowPartPaySelectionText(value) {
    return splitParamList(value).join(",");
  }

  function normalizeFullFlowPartPayVariables(variables, flow) {
    const next = { ...(variables || {}) };
    if (!isFullFlowPartPayScript(flow)) {
      next._full_flow_part_pay_script = false;
      delete next._full_flow_report_name;
      return next;
    }
    next._full_flow_part_pay_script = true;
    next._full_flow_report_name = FULL_FLOW_PART_PAY_SCRIPT_NAME;
    next.order_part_pay = boolValue(next.order_part_pay, true) ? 1 : 0;
    next.order_part_pay_percent = fullFlowPartPayPercent(next.order_part_pay_percent);
    const tailNode = String(next.order_part_pay_tail_node || "").trim();
    next.order_part_pay_tail_node = FULL_FLOW_PART_PAY_TAIL_NODE_OPTIONS.some((option) => option.value === tailNode) ? tailNode : "before_shelf";
    next.order_part_pay_fee_timing = fullFlowPartPayFeeTiming(next.order_part_pay_fee_timing);
    next.order_part_pay_tail_partial_enabled = boolValue(next.order_part_pay_tail_partial_enabled, false) ? 1 : 0;
    next.order_part_pay_tail_select_by = "sorting";
    next.order_part_pay_tail_sortings = fullFlowPartPaySelectionText(next.order_part_pay_tail_sortings);
    next.order_part_pay_tail_detail_ids = "";
    return next;
  }

  function validateFullFlowPartPayVariables(variables, flow) {
    if (!isFullFlowPartPayScript(flow)) return;
    if (!boolValue(variables?.order_part_pay, true)) return;
    if (!boolValue(variables?.order_part_pay_tail_partial_enabled, false)) return;
    if (!fullFlowPartPaySelectionText(variables?.order_part_pay_tail_sortings)) {
      throw new Error("按番尾款已启用，但未填写番序号");
    }
  }

  function fullFlowPartPayDisplayValues(variables) {
    const normalized = normalizeFullFlowPartPayVariables(variables, { id: FULL_FLOW_PART_PAY_SCRIPT_ID, scriptType: "full_flow", name: FULL_FLOW_PART_PAY_SCRIPT_NAME });
    const timing = fullFlowPartPayFeeTiming(normalized.order_part_pay_fee_timing);
    return {
      order_part_pay: boolValue(normalized.order_part_pay, true),
      order_part_pay_percent: fullFlowPartPayPercent(normalized.order_part_pay_percent),
      order_part_pay_tail_node: normalized.order_part_pay_tail_node || "before_shelf",
      order_part_pay_tail_partial_enabled: boolValue(normalized.order_part_pay_tail_partial_enabled, false),
      order_part_pay_tail_select_by: "sorting",
      order_part_pay_tail_sortings: fullFlowPartPaySelectionText(normalized.order_part_pay_tail_sortings),
      order_part_pay_tail_detail_ids: "",
      ...Object.fromEntries(FULL_FLOW_PART_PAY_FEE_FIELDS.map((field) => [`order_part_pay_fee_timing_${field.key}`, timing[field.key] || "first"])),
    };
  }

  function applyFullFlowPartPayFormValues(variables, data, flow) {
    const next = { ...(variables || {}) };
    if (!isFullFlowPartPayScript(flow)) {
      next._full_flow_part_pay_script = false;
      delete next._full_flow_report_name;
      return next;
    }
    next._full_flow_part_pay_script = true;
    next._full_flow_report_name = FULL_FLOW_PART_PAY_SCRIPT_NAME;
    next.order_part_pay = data.order_part_pay ? 1 : 0;
    next.order_part_pay_percent = fullFlowPartPayPercent(data.order_part_pay_percent);
    next.order_part_pay_tail_node = FULL_FLOW_PART_PAY_TAIL_NODE_OPTIONS.some((option) => option.value === data.order_part_pay_tail_node)
      ? data.order_part_pay_tail_node
      : "before_shelf";
    next.order_part_pay_fee_timing = Object.fromEntries(
      FULL_FLOW_PART_PAY_FEE_FIELDS.map((field) => {
        const timing = data[`order_part_pay_fee_timing_${field.key}`] === "tail" ? "tail" : "first";
        return [field.key, timing];
      }),
    );
    next.order_part_pay_tail_partial_enabled = boolValue(data.order_part_pay_tail_partial_enabled, false) ? 1 : 0;
    next.order_part_pay_tail_select_by = "sorting";
    next.order_part_pay_tail_sortings = fullFlowPartPaySelectionText(data.order_part_pay_tail_sortings);
    next.order_part_pay_tail_detail_ids = "";
    return next;
  }

  function fullFlowPartPayMoney(value) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number : 0;
  }

  function fullFlowPartPayAmountFromKeys(data, keys) {
    for (const key of keys) {
      const amount = fullFlowPartPayMoney(data[key]);
      if (amount > 0) return amount;
    }
    return 0;
  }

  function fullFlowPartPayFormatMoney(value) {
    const fixed = Number(value || 0).toFixed(2);
    return fixed.replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
  }

  function fullFlowPartPayOptionKey(option) {
    return String(option?.key || option?.id || option?.name || "").trim();
  }

  function fullFlowPartPaySelectedOptionAmount(options, counts, productAmount) {
    const selectedCounts = counts && typeof counts === "object" && !Array.isArray(counts) ? counts : {};
    return (Array.isArray(options) ? options : []).reduce((total, option) => {
      const key = fullFlowPartPayOptionKey(option);
      const count = normalizePositiveInt(selectedCounts[key], 0);
      if (!key || count <= 0) return total;
      const price = fullFlowPartPayMoney(option?.price);
      const priceType = String(option?.price_type ?? "").trim();
      const unit = String(option?.unit || "").trim();
      const amount = priceType === "1" || unit.includes("%") ? productAmount * price / 100 : price * count;
      return total + amount;
    }, 0);
  }

  function fullFlowPartPayPreview(data, orderOptions = []) {
    const shopCount = normalizePositiveInt(data.order_shop_count, 1);
    const perShop = normalizePositiveInt(data.order_per_shop || data.order_item_count, 2);
    const detailCount = Math.max(1, shopCount * perShop);
    const quantity = normalizePositiveInt(data.order_item_num, 10);
    const price = fullFlowPartPayMoney(data.offer_price || data.quote_unit_price || 10);
    const productAmount = detailCount * quantity * price;
    const percent = fullFlowPartPayPercent(data.order_part_pay_percent);
    const firstProduct = productAmount * percent / 100;
    const tailProduct = productAmount - firstProduct;
    let firstFee = 0;
    let tailFee = 0;
    const optionAmount = fullFlowPartPaySelectedOptionAmount(orderOptions, data.order_option_counts, productAmount);
    const feeRows = FULL_FLOW_PART_PAY_FEE_FIELDS.map((field) => {
      const rawAmount = fullFlowPartPayAmountFromKeys(data, field.amountKeys);
      const amount = field.key === "domestic_freight" ? rawAmount * detailCount : rawAmount;
      const timing = data[`order_part_pay_fee_timing_${field.key}`] === "tail" ? "tail" : "first";
      if (timing === "tail") tailFee += amount;
      else firstFee += amount;
      return { label: field.label, amount, timing };
    });
    if (optionAmount > 0) {
      const timing = data.order_part_pay_fee_timing_additional_service_fee === "tail" ? "tail" : "first";
      if (timing === "tail") tailFee += optionAmount;
      else firstFee += optionAmount;
      feeRows.push({ label: "已选 option 费用", amount: optionAmount, timing });
    }
    return {
      percent,
      productAmount,
      firstProduct,
      tailProduct,
      firstFee,
      tailFee,
      firstTotal: firstProduct + firstFee,
      tailTotal: tailProduct + tailFee,
      optionAmount,
      feeRows,
    };
  }

  function renderFullFlowPartPayPreview(data, orderOptions = []) {
    const preview = fullFlowPartPayPreview(data || {}, orderOptions);
    const feeRows = preview.feeRows
      .map((row) => `<tr><td>${escapeHtml(row.label)}</td><td>${fullFlowPartPayFormatMoney(row.amount)}</td><td>${row.timing === "tail" ? "尾款" : "首款"}</td></tr>`)
      .join("");
    const partialEnabled = boolValue(data?.order_part_pay_tail_partial_enabled, false);
    const selection = fullFlowPartPaySelectionText(data?.order_part_pay_tail_sortings);
    const partialText = partialEnabled
      ? `按番尾款：番序号 ${selection || "未填写，执行时会阻断"}`
      : "整单剩余尾款：尾款节点按整单待付尾款执行";
    return `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:12px">
        <div style="padding:12px;border:1px solid var(--line);border-radius:8px;background:#f8fafc"><span style="display:block;color:#64748b;font-size:12px">商品金额</span><strong>${fullFlowPartPayFormatMoney(preview.productAmount)}</strong></div>
        <div style="padding:12px;border:1px solid var(--line);border-radius:8px;background:#fff7ed"><span style="display:block;color:#64748b;font-size:12px">首款预估</span><strong>${fullFlowPartPayFormatMoney(preview.firstTotal)}</strong></div>
        <div style="padding:12px;border:1px solid var(--line);border-radius:8px;background:#eff6ff"><span style="display:block;color:#64748b;font-size:12px">尾款预估</span><strong>${fullFlowPartPayFormatMoney(preview.tailTotal)}</strong></div>
      </div>
      <div class="empty" style="margin-top:10px;text-align:left">${escapeHtml(partialText)}</div>
      <div class="table-wrap" style="margin-top:12px">
        <table><thead><tr><th>费用项</th><th>预估金额</th><th>支付节点</th></tr></thead><tbody>${feeRows}</tbody></table>
      </div>
    `;
  }

  function renderFullFlowPartPayPanel(values) {
    const percentOptions = FULL_FLOW_PART_PAY_PERCENT_OPTIONS
      .map((value) => `<option value="${value}" ${Number(values.order_part_pay_percent) === value ? "selected" : ""}>${value}%</option>`)
      .join("");
    const nodeOptions = FULL_FLOW_PART_PAY_TAIL_NODE_OPTIONS
      .map((option) => `<option value="${escapeHtml(option.value)}" ${option.value === values.order_part_pay_tail_node ? "selected" : ""}>${escapeHtml(option.label)}</option>`)
      .join("");
    const feeFields = FULL_FLOW_PART_PAY_FEE_FIELDS.map((field) => {
      const value = values[`order_part_pay_fee_timing_${field.key}`] || "first";
      return `
        <div class="field">
          <label>${escapeHtml(field.label)}</label>
          <select name="order_part_pay_fee_timing_${escapeHtml(field.key)}" data-part-pay-input>
            <option value="first" ${value === "first" ? "selected" : ""}>首款支付</option>
            <option value="tail" ${value === "tail" ? "selected" : ""}>尾款支付</option>
          </select>
        </div>
      `;
    }).join("");
    return `
      <details class="functional-requirement" open id="fullFlowPartPayPanel">
        <summary>分批付款</summary>
        <div class="form-grid" style="margin-top:12px">
          <label class="check-field">
            <input name="order_part_pay" id="fullFlowPartPayEnabled" type="checkbox" ${values.order_part_pay ? "checked" : ""} data-part-pay-input />
            <span>启用分批付款</span>
          </label>
          <div class="field">
            <label>首款比例</label>
            <select name="order_part_pay_percent" data-part-pay-input>${percentOptions}</select>
          </div>
          <div class="field">
            <label>尾款支付节点</label>
            <select name="order_part_pay_tail_node" data-part-pay-input>${nodeOptions}</select>
          </div>
          <div class="field">
            <label>尾款支付范围</label>
            <select name="order_part_pay_tail_partial_enabled" data-part-pay-input>
              <option value="0" ${values.order_part_pay_tail_partial_enabled ? "" : "selected"}>整单剩余尾款</option>
              <option value="1" ${values.order_part_pay_tail_partial_enabled ? "selected" : ""}>按番尾款</option>
            </select>
          </div>
          <div class="field">
            <label>尾款支付番序号</label>
            <input name="order_part_pay_tail_sortings" value="${escapeHtml(values.order_part_pay_tail_sortings || "")}" placeholder="如 1,2,3" data-part-pay-input />
          </div>
          ${feeFields}
        </div>
        <div id="fullFlowPartPayPreview">${renderFullFlowPartPayPreview(values)}</div>
      </details>
    `;
  }

  function bindFullFlowPartPayPanel(form, orderOptionsProvider = () => []) {
    const panel = form.querySelector("#fullFlowPartPayPanel");
    const previewEl = form.querySelector("#fullFlowPartPayPreview");
    if (!panel || !previewEl) return null;
    const sync = () => {
      const data = readForm(form);
      data.order_option_counts = readOrderOptionCounts(form);
      previewEl.innerHTML = renderFullFlowPartPayPreview(data, orderOptionsProvider());
    };
    ["order_shop_count", "order_per_shop", "order_item_count", "order_item_num", "offer_num", "offer_price", "quote_unit_price", "offer_freight", "confirm_freight", "service_fee", "handling_fee", "additional_service_fee", "added_service_fee", "other_price"].forEach((name) => {
      form.querySelectorAll(`[name="${name}"]`).forEach((input) => input.addEventListener(input.type === "number" ? "input" : "change", sync));
    });
    form.querySelectorAll("[data-part-pay-input]").forEach((input) => {
      input.addEventListener(input.type === "checkbox" || input.tagName === "SELECT" ? "change" : "input", sync);
    });
    form.addEventListener("input", (event) => {
      if (event.target?.matches?.("[data-order-option-key]")) sync();
    });
    form.addEventListener("change", (event) => {
      if (event.target?.matches?.("[data-order-option-key]")) sync();
    });
    sync();
    return sync;
  }

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
    next.warehouse_sku_count = normalizePositiveInt(next.warehouse_sku_count || next.porder_sku_count || next.sku_count, 1);
    next.order_shop_count = normalizePositiveInt(next.order_shop_count, 1);
    next.order_per_shop = normalizePositiveInt(next.order_per_shop || next.order_item_count, 2);
    if (next.order_shop_count * next.order_per_shop < next.warehouse_sku_count) {
      next.order_per_shop = Math.ceil(next.warehouse_sku_count / next.order_shop_count);
    }
    next.order_item_count = next.order_per_shop;
    next.target_shops = normalizePositiveInt(next.target_shops || next.shop_count, next.order_shop_count);
    next.per_shop = normalizePositiveInt(next.per_shop, next.order_per_shop);
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
    next.order_payment_mode = next.order_payment_mode || "balance_first";
    next.porder_payment_mode = next.porder_payment_mode || "balance_first";
    next.pay_bank_method = next.pay_bank_method || "1";
    if (isFullFlowCopy(flow)) {
      Object.entries(FULL_FLOW_COPY_REMARK_DEFAULTS).forEach(([key, value]) => {
        next[key] = next[key] || value;
      });
    } else {
      next.client_remark_translate = next.client_remark_translate || "自动化配送单翻译";
      next.porder_y_remark = next.porder_y_remark || "自动化装箱";
      next.porder_offer_remark = next.porder_offer_remark || "自动化配送单报价";
    }
    next.finance_confirm = true;
    next.discounts_id = next.discounts_id || "";
    next.predict_logistics_price_is_pay = "0";
    next.include_balance_pay_amount = false;
    Object.assign(next, normalizeFullFlowPartPayVariables(next, flow));
    if (next.shelf_type_set) {
      next.shelf_type_set = splitParamList(next.shelf_type_set).map((item) => {
        const number = Number(item);
        return Number.isFinite(number) ? number : item;
      });
    }
    next.order_sn = String(next.order_sn || next.last_order_sn || "").trim();
    next.porder_sn = String(next.porder_sn || "").trim();
    if (!next.order_sn) delete next.order_sn;
    if (!next.porder_sn) delete next.porder_sn;
    delete next.last_order_sn;
    delete next.order_sns;
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
      target_shops: 1,
      per_shop: 2,
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
    const migratedExistingVariables = { ...existingVariables };
    if (
      existingFlow?.id === "full_flow_builtin" &&
      String(migratedExistingVariables.target_shops ?? "") === "4" &&
      String(migratedExistingVariables.per_shop ?? "") === "5" &&
      normalizePositiveInt(migratedExistingVariables.order_shop_count, 1) === 1 &&
      normalizePositiveInt(migratedExistingVariables.order_per_shop || migratedExistingVariables.order_item_count, 2) === 2
    ) {
      migratedExistingVariables.target_shops = 1;
      migratedExistingVariables.per_shop = 2;
    }
    const mergedVariables = sanitizeScriptVariables("full_flow", { ...defaultVariables, ...migratedExistingVariables }, existingFlow);
    mergedVariables.keywords = uniqueList([...listValue(migratedExistingVariables.keywords), ...defaultVariables.keywords]);
    mergedVariables.preferred_keywords = uniqueList([...listValue(migratedExistingVariables.preferred_keywords), ...defaultVariables.preferred_keywords]);
    mergedVariables.boost_keywords = uniqueList([...listValue(migratedExistingVariables.boost_keywords), ...defaultVariables.boost_keywords]);
    if (migratedExistingVariables.order_option_counts) mergedVariables.order_option_counts = migratedExistingVariables.order_option_counts;
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

  function isFullFlowPartPayScriptDeleted() {
    if (isBuiltinDeleted(FULL_FLOW_PART_PAY_SCRIPT_ID)) return true;
    return readDeletedFlows().some((entry) => {
      const source = entry?.flow || {};
      return (
        deletedEntryKey(entry) === FULL_FLOW_PART_PAY_SCRIPT_ID ||
        entry?.builtinId === FULL_FLOW_PART_PAY_SCRIPT_ID ||
        source.id === FULL_FLOW_PART_PAY_SCRIPT_ID ||
        String(source.name || entry?.name || "").trim() === FULL_FLOW_PART_PAY_SCRIPT_NAME
      );
    });
  }

  function ensureFullFlowPartPayScript(flows, projects, envs, cases) {
    if (isFullFlowPartPayScriptDeleted()) return flows;
    const env = dataScriptDefaultEnv(projects, envs);
    const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";
    if (!env) return flows;

    const baseFlow = flows.find((flow) => flow.id === "full_flow_builtin") || flows.find((flow) => flow.name === "全流程完全体") || {};
    let baseVariables = {};
    try {
      baseVariables = parseJsonText(baseFlow.variables || "{}", {});
    } catch {
      baseVariables = {};
    }

    const existingIndex =
      flows.findIndex((flow) => flow.id === FULL_FLOW_PART_PAY_SCRIPT_ID) >= 0
        ? flows.findIndex((flow) => flow.id === FULL_FLOW_PART_PAY_SCRIPT_ID)
        : flows.findIndex((flow) => String(flow.name || "").trim() === FULL_FLOW_PART_PAY_SCRIPT_NAME && flow.scriptType === "full_flow");
    const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};
    let existingVariables = {};
    try {
      existingVariables = parseJsonText(existingFlow.variables || "{}", {});
    } catch {
      existingVariables = {};
    }

    const mergedVariables = sanitizeScriptVariables(
      "full_flow",
      {
        ...baseVariables,
        ...existingVariables,
        _full_flow_part_pay_script: true,
        _full_flow_report_name: FULL_FLOW_PART_PAY_SCRIPT_NAME,
        order_part_pay: existingVariables.order_part_pay ?? baseVariables.order_part_pay ?? 1,
        order_part_pay_percent: existingVariables.order_part_pay_percent ?? baseVariables.order_part_pay_percent ?? 10,
        order_part_pay_tail_node: existingVariables.order_part_pay_tail_node ?? baseVariables.order_part_pay_tail_node ?? "before_shelf",
        order_part_pay_fee_timing: existingVariables.order_part_pay_fee_timing ?? baseVariables.order_part_pay_fee_timing ?? {},
      },
      { id: FULL_FLOW_PART_PAY_SCRIPT_ID, name: FULL_FLOW_PART_PAY_SCRIPT_NAME, scriptType: "full_flow" },
    );
    const nextFlow = {
      ...existingFlow,
      id: FULL_FLOW_PART_PAY_SCRIPT_ID,
      name: FULL_FLOW_PART_PAY_SCRIPT_NAME,
      scriptType: "full_flow",
      projectId: String(existingFlow.projectId || baseFlow.projectId || projectId),
      envId: String(existingFlow.envId || baseFlow.envId || env.id),
      caseIds: (existingFlow.caseIds && existingFlow.caseIds.length ? existingFlow.caseIds : baseFlow.caseIds) || [],
      variables: JSON.stringify(mergedVariables, null, 2),
    };
    const next =
      existingIndex >= 0
        ? flows
            .map((flow, index) => (index === existingIndex ? nextFlow : flow))
            .filter((flow, index) => index === existingIndex || (flow.id !== FULL_FLOW_PART_PAY_SCRIPT_ID && String(flow.name || "").trim() !== FULL_FLOW_PART_PAY_SCRIPT_NAME))
        : [...flows.filter((flow) => flow.id !== FULL_FLOW_PART_PAY_SCRIPT_ID && String(flow.name || "").trim() !== FULL_FLOW_PART_PAY_SCRIPT_NAME), nextFlow];
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
          ensureFullFlowPartPayScript(
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

  function renderFullFlowCopyFieldGroups(values, flow) {
    return FULL_FLOW_COPY_FIELD_GROUPS.map((group) => {
      const groupBody = group.fields
        .map((field) => renderFullFlowCopyFormField(field, values?.[field.name] ?? field.default ?? ""))
        .join("");
      const saveDefaults = group.title === "执行控制" ? renderFormField(FULL_FLOW_SAVE_DEFAULTS_FIELD, values?.__save_defaults ?? false) : "";
      const partPayPanel = isFullFlowPartPayScript(flow) && group.title === "订单报价" ? renderFullFlowPartPayPanel(values) : "";
      return `
        <details class="functional-requirement" ${group.open ? "open" : ""}>
          <summary>${escapeHtml(group.title)}</summary>
          <div class="form-grid" style="margin-top:12px">${groupBody}${saveDefaults}</div>
        </details>
        ${partPayPanel}
      `;
    }).join("");
  }

  function fullFlowDimensionParts(value) {
    const parts = String(value || "")
      .trim()
      .split(/[xX×*＊]/)
      .map((item) => item.trim());
    return {
      length: parts[0] || "",
      width: parts[1] || "",
      height: parts[2] || "",
    };
  }

  function renderFullFlowCopyFormField(field, value) {
    if (field.name === "confirm_weight" || field.name === "box_weight") {
      const unit = field.name === "box_weight" ? "KG" : "g";
      return `
        <div class="field">
          <label>${escapeHtml(field.label)}</label>
          <div style="display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center">
            <input name="${escapeHtml(field.name)}" type="number" value="${escapeHtml(value ?? field.default ?? "")}" />
            <span style="color:#64748b;font-weight:600">（${escapeHtml(unit)}）</span>
          </div>
        </div>
      `;
    }
    if (field.name !== "confirm_volume") return renderFormField(field, value);
    const parts = fullFlowDimensionParts(value || field.default || "");
    return `
      <div class="field">
        <label>${escapeHtml(field.label)}</label>
        <div style="display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr) auto minmax(0,1fr);gap:10px;align-items:center">
          <input name="confirm_volume_length" type="text" inputmode="decimal" value="${escapeHtml(parts.length)}" placeholder="长" />
          <span style="font-weight:700;text-align:center;color:#ef4444">x</span>
          <input name="confirm_volume_width" type="text" inputmode="decimal" value="${escapeHtml(parts.width)}" placeholder="宽" />
          <span style="font-weight:700;text-align:center;color:#ef4444">x</span>
          <input name="confirm_volume_height" type="text" inputmode="decimal" value="${escapeHtml(parts.height)}" placeholder="高" />
        </div>
      </div>
    `;
  }

  function fullFlowDimensionValue(data, fallback = "") {
    const length = String(data.confirm_volume_length ?? "").trim();
    const width = String(data.confirm_volume_width ?? "").trim();
    const height = String(data.confirm_volume_height ?? "").trim();
    if (length || width || height) return `${length}x${width}x${height}`;
    return String(data.confirm_volume || fallback || "").trim();
  }

  function fullFlowDefaultVariables(variables) {
    const next = { ...(variables || {}) };
    delete next.order_sn;
    delete next.last_order_sn;
    delete next.order_sns;
    delete next.porder_sn;
    delete next.porder_sns;
    return next;
  }

  function fullFlowCopyDefaultVariables(variables) {
    const next = fullFlowDefaultVariables(variables);
    Object.entries(FULL_FLOW_COPY_REMARK_DEFAULTS).forEach(([key, value]) => {
      next[key] = value;
    });
    return next;
  }

  function fullFlowCopyDisplayValues(values) {
    return { ...(values || {}), ...FULL_FLOW_COPY_REMARK_DEFAULTS };
  }

  function openFullFlowCopyRunForm(flow) {
    let variables = {};
    try {
      variables = parseJsonText(flow.variables || "{}", {});
    } catch {
      showToast("脚本变量不是合法 JSON");
      return;
    }
    const fields = FULL_FLOW_COPY_FIELDS;
    variables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables("full_flow", variables, flow)));
    const values = {
      ...fullFlowCopyDisplayValues(paramFormValues(fields, variables)),
      ...fullFlowPartPayDisplayValues(variables),
      __save_defaults: false,
    };
    const initialCounts = orderOptionCountsFromVariables(variables.order_option_counts);
    modalEl.innerHTML = `
      <form id="fullFlowRunForm">
        <div class="modal-head">
          <h3>${escapeHtml(`执行 ${flow.name || FULL_FLOW_COPY_NAME}`)}</h3>
          <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>
        </div>
        <div class="modal-body">
          ${renderFullFlowCopyFieldGroups(values, flow)}
          <details class="functional-requirement">
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
    let currentOrderOptions = [];
    function runtimeVariables(includeCurrentCounts = true) {
      const data = readForm(form);
      data.confirm_volume = fullFlowDimensionValue(data, variables.confirm_volume);
      const next = applyFullFlowPartPayFormValues(sanitizeScriptVariables("full_flow", mergeParamValues(variables, fields, data), flow), data, flow);
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
        currentOrderOptions = result.options || [];
        previewEl.innerHTML = renderOrderOptionPreview(result.options || [], { ...initialCounts, ...counts });
        if (syncPartPayPreview) syncPartPayPreview();
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
    const syncPartPayPreview = bindFullFlowPartPayPanel(form, () => currentOrderOptions);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = readForm(form);
        const next = runtimeVariables(true);
        validateFullFlowPartPayVariables(next, flow);
        if (data.__save_defaults) saveFlowVariables(flow, fullFlowCopyDefaultVariables(next));
        await runSavedFlow(flow, next);
      } catch (error) {
        showToast(error.message);
      }
    });
    refreshOptions();
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
        if (data.__save_defaults) saveFlowVariables(flow, fullFlowDefaultVariables(next));
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
      if (isFullFlowCopy(flow)) {
        openFullFlowCopyRunForm(flow);
        return;
      }
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
    const flowTitle = isFullFlowPartPayScript(flow) ? FULL_FLOW_PART_PAY_SCRIPT_NAME : "全流程完全体";
    const progress = options.progress || openScriptProgress(`${flowTitle}执行进度`, "预计执行 20 个业务节点");
    try {
      showToast(`${flowTitle}脚本执行中，请稍候`);
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
      progress.success(summary.paused ? `已按暂停节点停止：${summary.node_label || summary.current_node || ""}` : `${flowTitle}执行完成，正在展示结果...`);
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
