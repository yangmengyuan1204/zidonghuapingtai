let _projectsCache = null;async function getProjects() {  if (!_projectsCache) _projectsCache = await api("/api/projects");  return _projectsCache;}function invalidateProjectsCache() { _projectsCache = null; }const state = {  token: localStorage.getItem("token") || "",  user: null,  view: "dashboard",  filters: {    projectId: localStorage.getItem("projectId") || "",    envId: "",    recordType: "",  },  selectedApiIds: new Set(),  factory: {    flowId: localStorage.getItem("factoryFlowId") || "",    projectId: localStorage.getItem("factoryProjectId") || localStorage.getItem("projectId") || "",    envId: localStorage.getItem("factoryEnvId") || "",    caseIds: JSON.parse(localStorage.getItem("factoryCaseIds") || "[]"),    variables: localStorage.getItem("factoryVariables") || '{\n  "keyword": "test",\n  "account": "abner"\n}',    editing: false,  },  dataScriptTab: localStorage.getItem("dataScriptTab") || "active",  functionalTaskId: localStorage.getItem("functionalTaskId") || "",};const views = [  { key: "dashboard", label: "工作台总览" },  { key: "projects", label: "项目空间" },  { key: "apiCases", label: "接口用例库" },  { key: "dataScripts", label: "数据工厂" },  { key: "caseGeneration", label: "AI用例生成" },  { key: "functionalTests", label: "功能验证中心" },  { key: "uiCases", label: "UI自动化" },  { key: "records", label: "执行报告" },  { key: "users", label: "权限中心", adminOnly: true },];const FLOW_STORAGE_KEY = "dataFactoryFlows";const DELETED_BUILTIN_KEY = "dataFactoryDeletedBuiltins";const DELETED_FLOW_STORAGE_KEY = "dataFactoryDeletedFlows";const HIDDEN_FLOW_STORAGE_KEY = "dataFactoryHiddenFlows";const HIDDEN_BUILTIN_KEY = "dataFactoryHiddenBuiltins";const DATA_SCRIPT_CUSTOMER_IDS_KEY = "dataScriptCustomerIds";const FUNCTIONAL_SCAN_AUTH_PREFIX = "functionalScanAuth:";const CASE_NAME_PREFIXES = ["\u6570\u636e\u811a\u672c-", "test-"];const BUILTIN_FLOW_DEFINITIONS = {  shopping_cart: { id: "shopping_cart_builtin", name: "\u5546\u54c1\u8d2d\u7269\u8f66" },  order_quote: { id: "order_quote_builtin", name: "\u8ba2\u5355\u62a5\u4ef7" },  balance_payment: { id: "balance_payment_builtin", name: "\u4f59\u989d\u652f\u4ed8" },  bank_payment: { id: "bank_payment_builtin", name: "\u94f6\u884c\u652f\u4ed8" },  purchase_to_shelf: { id: "purchase_to_shelf_builtin", name: "\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6" },  purchase_to_shelf_chain: {    id: "purchase_to_shelf_chain_builtin",    name: "\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6(\u7ec4\u5408\u811a\u672c)",  },  warehouse_delivery: { id: "warehouse_delivery_builtin", name: "\u4ed3\u5e93\u63d0\u51fa\u914d\u9001\u5355" },  porder_balance_payment: { id: "porder_balance_payment_builtin", name: "\u914d\u9001\u5355\u4f59\u989d\u4ed8\u6b3e" },  porder_bank_payment: { id: "porder_bank_payment_builtin", name: "\u914d\u9001\u5355\u94f6\u884c\u4ed8\u6b3e" },
  material_generation: { id: "material_generation_builtin", name: "\u8f85\u6599\u751f\u6210" },
  balance_recharge: { id: "balance_recharge_builtin", name: "\u4f59\u989d\u5145\u503c" },
  oem_new_inquiry: { id: "oem_new_inquiry_builtin", name: "OEM\u63d0\u51fa\u8be2\u4ef7\u5355" },
  oem_sample_order: { id: "oem_sample_order_builtin", name: "OEM\u63d0\u51fa\u6837\u54c1\u5355" },
  oem_full_inquiry_flow: { id: "oem_full_inquiry_flow_builtin", name: "OEM询价单全流程" },
  oem_sample_admin_flow: { id: "oem_sample_admin_flow_builtin", name: "OEM样品单后台流程" },
  oem_sample_full_flow: { id: "oem_sample_full_flow_builtin", name: "OEM样品单全流程" },
  oem_bulk_order: { id: "oem_bulk_order_builtin", name: "OEM大货单下单" },
  oem_balance_pay: { id: "oem_balance_pay_builtin", name: "OEM余额支付" },
};const BUILTIN_DATA_SCRIPT_TYPES = Object.keys(BUILTIN_FLOW_DEFINITIONS);const CUSTOMER_ID_FIELD = { name: "customer_ids", label: "客户ID(多个换行或逗号)", type: "textarea", rows: 3, kind: "list", placeholder: "多个客户ID可用逗号或换行分隔" };const SHOP_TYPE_OPTIONS = [  { value: "1688", label: "1688" },  { value: "taobao", label: "taobao" },  { value: "tmall", label: "tmall" },  { value: "rakumart", label: "rakumart" },];const SCRIPT_PARAM_SCHEMAS = {  shopping_cart: [    { name: "keyword", label: "关键词" },    { name: "shop_type", label: "商品来源", type: "select", options: SHOP_TYPE_OPTIONS, default: "1688" },    { name: "target_shops", label: "目标店铺数", type: "number", default: 4 },    { name: "per_shop", label: "每店商品数", type: "number", default: 5 },  ],  order_quote: [    { name: "order_shop_count", label: "目标店铺数", type: "number", default: 1 },    { name: "order_per_shop", label: "每店商品数", type: "number", default: 2 },    { name: "order_item_num", label: "每个商品数量", type: "number", default: 10 },  ],  balance_payment: [    { name: "order_sns", label: "订单号(多个换行或逗号)", type: "textarea", rows: 4, kind: "list" },    { name: "order_sn", label: "单个订单号" },  ],  bank_payment: [    { name: "order_sns", label: "订单号(多个换行或逗号)", type: "textarea", rows: 4, kind: "list" },    { name: "order_sn", label: "单个订单号" },  ],  purchase_to_shelf: [    { name: "order_sn", label: "订单号" },    { name: "purchase_no", label: "交易号" },  ],  purchase_to_shelf_chain: [    { name: "purchase_no", label: "交易号" },  ],  warehouse_delivery: [    { name: "warehouse_sku_count", label: "仓库提出番数", type: "number", default: 1 },    { name: "send_num", label: "每番提出数量", type: "number", default: 1 },  ],  porder_balance_payment: [    { name: "porder_sns", label: "\u914d\u9001\u5355\u53f7(\u591a\u4e2a\u6362\u884c\u6216\u9017\u53f7)", type: "textarea", rows: 4, kind: "list" },    { name: "porder_sn", label: "\u5355\u4e2a\u914d\u9001\u5355\u53f7" },  ],  porder_bank_payment: [    { name: "porder_sns", label: "\u914d\u9001\u5355\u53f7(\u591a\u4e2a\u6362\u884c\u6216\u9017\u53f7)", type: "textarea", rows: 4, kind: "list" },    { name: "porder_sn", label: "\u5355\u4e2a\u914d\u9001\u5355\u53f7" },  ],  porder_shipment: [    { name: "porder_sns", label: "\u914d\u9001\u5355\u53f7(\u591a\u4e2a\u6362\u884c\u6216\u9017\u53f7)", type: "textarea", rows: 4, kind: "list" },    { name: "porder_sn", label: "\u5355\u4e2a\u914d\u9001\u5355\u53f7" },  ],
  oem_sample_order: [
    { name: "order_sn", label: "\u8be2\u4ef7\u5355\u53f7", required: true },
    { name: "sku_list", label: "SKU \u5217\u8868", type: "textarea", rows: 6, placeholder: "[{\"sku_id\": 1993, \"num\": 1}, {\"sku_id\": 1994, \"num\": 2}]" },
  ],
  oem_full_inquiry_flow: [
    { name: "__section_create", type: "section", label: "询价单提出" },
    { name: "goods_name", label: "商品名称", default: "测试商品" },
    { name: "hope_min_price", label: "期望最低价", default: "1" },
    { name: "hope_max_price", label: "期望最高价", default: "100" },
    { name: "hope_futures", label: "期望交期", default: "10" },
    { name: "goods_class", label: "商品类型", type: "goods-class-select", default: 110 },
    { name: "factory_type", label: "工厂类型", type: "select", default: "3",
      options: [
        { value: "1", label: "严选工厂" },
        { value: "2", label: "普通工厂" },
        { value: "3", label: "交易工厂" },
      ] },
    { name: "factory_urls", label: "工厂链接", type: "factory-urls-dynamic" },
    { name: "goods_img", label: "商品主图", type: "upload" },
    { name: "sku_info", label: "SKU列表", type: "sku-dynamic" },
    { name: "__section_translate", type: "section", label: "翻译阶段" },
    { name: "goods_name_tr", label: "商品名称翻译(留空用原名)" },
    { name: "material_tr", label: "材质翻译" },
    { name: "customize_detail_tr", label: "定制详情翻译" },
    { name: "goods_detail_tr", label: "商品详情翻译" },
    { name: "__section_inquiry", type: "section", label: "询价阶段" },
    { name: "factory_img", label: "工厂图片URL(留空则不设置)" },
    { name: "salesman", label: "业务员名称", default: "测试业务员" },
    { name: "salesman_phone", label: "业务员电话", default: "13800000000" },
    { name: "__section_quote", type: "section", label: "报价阶段" },
    { name: "samples_price", label: "样品单价", default: "12.00" },
    { name: "large_price", label: "大货单价", default: "11.00" },
    { name: "large_other_fee", label: "大货其他费用", default: "12.00" },
    { name: "large_freight", label: "大货运费", default: "11.00" },
    { name: "large_delivery_time", label: "大货交期(天)", type: "number", default: 15 },
    { name: "large_deposit_rate", label: "大货定金比例", default: "100" },
    { name: "real_samples_price", label: "实际样品单价", default: "10.00" },
    { name: "real_large_price", label: "实际大货单价", default: "10.00" },
  ],
  oem_sample_admin_flow: [
    { name: "order_sn", label: "\u6837\u54c1\u5355\u53f7", required: true },
    { name: "warehouse_city", label: "\u4ed3\u5e93\u57ce\u5e02", type: "number", default: 2 },
  ],
  oem_sample_full_flow: [
    { name: "__section_confirm", type: "section", label: "\u786e\u8ba4\u9636\u6bb5\uff08\u91c7\u8d2d\u786e\u8ba4\uff09" },
    { name: "inquiry_other_fee", label: "\u8be2\u4ef7\u5176\u4ed6\u8d39\u7528", default: "0.00" },
    { name: "inquiry_freight", label: "\u8be2\u4ef7\u8fd0\u8d39", default: "0.00" },
    { name: "inquiry_delivery_time", label: "\u8be2\u4ef7\u4ea4\u671f(\u5929)", type: "number", default: 0 },
    { name: "quote_other_fee", label: "\u62a5\u4ef7\u5176\u4ed6\u8d39\u7528", default: "7" },
    { name: "quote_freight", label: "\u62a5\u4ef7\u8fd0\u8d39", default: "8" },
    { name: "quote_delivery_time", label: "\u62a5\u4ef7\u4ea4\u671f(\u5929)", default: "9" },
    { name: "real_other_fee", label: "\u5b9e\u9645\u5176\u4ed6\u8d39\u7528", default: "7" },
    { name: "real_freight", label: "\u5b9e\u9645\u8fd0\u8d39", default: "8" },
    { name: "__section_check", type: "section", label: "\u9a8c\u8d27\u9636\u6bb5" },
    { name: "check_report_images", label: "\u9a8c\u8d27\u56fe\u7247URL(\u6bcf\u884c\u4e00\u4e2a)", type: "textarea", rows: 4 },
    { name: "check_report_remark", label: "\u9a8c\u8d27\u5907\u6ce8" },
    { name: "keep_sample_num", label: "\u7559\u6837\u6570\u91cf", type: "number", default: 0 },
    { name: "keep_sample_possible_num", label: "\u53ef\u7559\u6837\u6570\u91cf", type: "number", default: 0 },
    { name: "__section_shelve", type: "section", label: "\u4e0a\u67b6\u9636\u6bb5" },
    { name: "warehouse_city", label: "\u4ed3\u5e93\u57ce\u5e02", type: "select",
      options: [{ value: "2", label: "\u5e7f\u5dde\u4ed3" }, { value: "1", label: "\u4e49\u4e4c\u4ed3" }], default: "2" },
  ],
  oem_bulk_order: [
    { name: "__section_account", type: "section", label: "登录信息" },
    { name: "account", label: "前台账号", default: "12345678990" },
    { name: "password", label: "前台密码", default: "123456" },
    { name: "__section_query", type: "section", label: "查询参数" },
    { name: "order_sn", label: "询价单号", required: true },
    { name: "sku_list", type: "hidden" },
    { name: "warehouse_city", type: "hidden" },
    { name: "remark", type: "hidden" },
    { name: "inquiry_detail_id", type: "hidden" },
  ],
  oem_balance_pay: [
    { name: "order_sn", label: "\u6837\u54c1\u5355\u53f7", required: true },
    { name: "coupon_id", label: "\u4f18\u60e0\u5238ID\uff08\u53ef\u7559\u7a7a\uff09" },
  ],
  material_generation: [
    CUSTOMER_ID_FIELD,
    { name: "count", label: "\u8f85\u6599\u751f\u6210\u4e2a\u6570", type: "number", default: 1 },
    { name: "name", label: "\u8f85\u6599\u540d\u79f0", required: true },
  ],
  balance_recharge: [
    CUSTOMER_ID_FIELD,
    { name: "amount", label: "充值金额", required: true },
  ],
  oem_new_inquiry: [
    { name: "goods_name", label: "商品名称", default: "测试商品" },
    { name: "hope_min_price", label: "期望最低价", default: "1" },
    { name: "hope_max_price", label: "期望最高价", default: "100" },
    { name: "hope_futures", label: "期望交期", default: "10" },
    { name: "goods_type", label: "商品类型", type: "number", default: 1 },
    { name: "factory_urls", label: "工厂链接（每行一个）", type: "textarea", rows: 4 },
    { name: "goods_img", label: "商品主图", type: "upload" },
  ],};// 主题初始化
(function initTheme() {
  const saved = localStorage.getItem('theme') || 'shuimo';
  document.documentElement.dataset.theme = saved;
})();

const appEl = document.querySelector("#app");const toastEl = document.querySelector("#toast");const modalEl = document.querySelector("#modal");function isAdmin() {  return state.user && state.user.role === "admin";}function escapeHtml(value) {  return String(value ?? "")    .replaceAll("&", "&amp;")    .replaceAll("<", "&lt;")    .replaceAll(">", "&gt;")    .replaceAll('"', "&quot;")    .replaceAll("'", "&#039;");}function short(value, length = 140) {  const text = String(value ?? "");  return text.length > length ? `${text.slice(0, length)}...` : text;}function showToast(message) {  toastEl.textContent = message;  toastEl.hidden = false;  window.clearTimeout(showToast.timer);  showToast.timer = window.setTimeout(() => {    toastEl.hidden = true;  }, 2600);}async function copyText(text, label = "\u5185\u5bb9") {  const value = String(text || "").trim();  if (!value) {    showToast("\u6ca1\u6709\u53ef\u590d\u5236\u7684\u5185\u5bb9");    return;  }  try {    if (navigator.clipboard?.writeText) {      await navigator.clipboard.writeText(value);    } else {      const textarea = document.createElement("textarea");      textarea.value = value;      textarea.setAttribute("readonly", "readonly");      textarea.style.position = "fixed";      textarea.style.left = "-9999px";      document.body.appendChild(textarea);      textarea.select();      document.execCommand("copy");      textarea.remove();    }    showToast(`${label}\u5df2\u590d\u5236`);  } catch {    showToast("\u590d\u5236\u5931\u8d25\uff0c\u8bf7\u624b\u52a8\u590d\u5236");  }}function queryString(params) {  const query = new URLSearchParams();  Object.entries(params || {}).forEach(([key, value]) => {    if (value !== "" && value !== null && value !== undefined) query.set(key, value);  });  const text = query.toString();  return text ? `?${text}` : "";}function parseJsonText(text, fallback = {}) {  const raw = String(text || "").trim();  if (!raw) return fallback;  return JSON.parse(raw);}function boolValue(value, fallback = false) {  if (value === undefined || value === null || value === "") return fallback;  if (typeof value === "boolean") return value;  if (typeof value === "number") return value !== 0;  return !["0", "false", "no", "off", "否"].includes(String(value).trim().toLowerCase());}function splitParamList(value) {  if (Array.isArray(value)) {    return value.map((item) => String(item || "").trim()).filter(Boolean);  }  return String(value || "")    .split(/[\n,，;；]+/)    .map((item) => item.trim())    .filter(Boolean);}function customerIdsFromVariables(variables) {  const ids = splitParamList(variables?.customer_ids);  return ids.length ? ids : splitParamList(variables?.customer_id);}function storedDataScriptCustomerIds() {  return localStorage.getItem(DATA_SCRIPT_CUSTOMER_IDS_KEY) || "";}function mergeStoredCustomerIds(variables) {  const ids = splitParamList(storedDataScriptCustomerIds());  if (!ids.length || customerIdsFromVariables(variables).length) return variables;  return { ...(variables || {}), customer_ids: ids };}function withCustomerLoginInputs(variables) {  const ids = customerIdsFromVariables(variables);  if (!ids.length) return variables;  const next = { ...(variables || {}), customer_ids: ids };  if (ids.length === 1) {    next.customer_id = ids[0];  } else {    delete next.customer_id;  }  delete next.account;  delete next.password;  return next;}function variablesForCustomerId(variables, customerId) {  return withCustomerLoginInputs({ ...(variables || {}), customer_id: customerId, customer_ids: [customerId] });}function customerIdFromSnSuffix(value) {  const match = String(value || "").trim().match(/-(\d+)$/);  return match ? match[1] : "";}const SILENT_PROGRESS = { update() {}, success() {}, fail() {} };function isPorderShipmentFlow(flow) {  const name = String(flow?.name || "");  return name.includes("配送单") && name.includes("出货");}function scriptParamFields(scriptType, flow = null) {  if (SCRIPT_PARAM_SCHEMAS[scriptType]) return SCRIPT_PARAM_SCHEMAS[scriptType];  if (isPorderShipmentFlow(flow)) return SCRIPT_PARAM_SCHEMAS.porder_shipment;  return [];}function customerScriptFields(scriptType, flow = null) {  const fields = scriptParamFields(scriptType, flow);  return [CUSTOMER_ID_FIELD, ...fields.filter((field) => field.name !== CUSTOMER_ID_FIELD.name)];}function safeVariables(text) {  try {    return parseJsonText(text || "{}", {});  } catch {    return {};  }}function fieldDisplayValue(field, variables) {  const value = variables?.[field.name] ?? field.default ?? "";  if (field.type === "checkbox") return boolValue(value, boolValue(field.default, false));  if (field.kind === "list") return splitParamList(value).join("\n");  return value ?? "";}function renderFormField(field, value) {  const required = field.required ? "required" : "";  const placeholder = field.placeholder ? `placeholder="${escapeHtml(field.placeholder)}"` : "";  if (field.type === "select") {    const options = (field.options || [])      .map((option) => `<option value="${escapeHtml(option.value)}" ${String(option.value) === String(value) ? "selected" : ""}>${escapeHtml(option.label)}</option>`)      .join("");    return `<div class="field"><label>${escapeHtml(field.label)}</label><select name="${escapeHtml(field.name)}" ${required}>${options}</select></div>`;  }  if (field.type === "textarea") {    return `<div class="field"><label>${escapeHtml(field.label)}</label><textarea name="${escapeHtml(field.name)}" rows="${field.rows || 5}" ${required} ${placeholder}>${escapeHtml(value)}</textarea></div>`;  }  if (field.type === "checkbox") {
    return `      <label class="check-field">        <input name="${escapeHtml(field.name)}" type="checkbox" ${value ? "checked" : ""} />        <span>${escapeHtml(field.label)}</span>      </label>    `;  }
  if (field.type === "upload") {
    return `<div class="field"><label>${escapeHtml(field.label)}</label><div class="upload-field"><input name="${escapeHtml(field.name)}" type="text" value="${escapeHtml(value)}" ${placeholder} ${required} data-upload-input /><button class="btn secondary" type="button" data-upload-btn data-upload-url="/api/oem/upload-image">选择文件</button></div></div>`;
  }  return `<div class="field"><label>${escapeHtml(field.label)}</label><input name="${escapeHtml(field.name)}" type="${field.type || "text"}" value="${escapeHtml(value)}" ${placeholder} ${required} /></div>`;}function paramFormValues(fields, variables) {  return Object.fromEntries(fields.map((field) => [field.name, fieldDisplayValue(field, variables)]));}function normalizeParamValue(field, rawValue) {  if (field.type === "checkbox") {    const checked = boolValue(rawValue, false);    return field.kind === "flag" ? (checked ? "1" : "0") : checked;  }  if (field.kind === "list") return splitParamList(rawValue);  if (field.type === "number") {    if (rawValue === "" || rawValue === null || rawValue === undefined) return "";    const number = Number(rawValue);    return Number.isFinite(number) ? number : "";  }  return String(rawValue ?? "").trim();}function mergeParamValues(variables, fields, formData) {  const next = { ...(variables || {}) };  fields.forEach((field) => {    const value = normalizeParamValue(field, formData[field.name]);    const isEmptyList = Array.isArray(value) && value.length === 0;    if (value === "" || value === null || value === undefined || isEmptyList) {      delete next[field.name];    } else {      next[field.name] = value;    }  });  return next;}function orderSnListFromVariables(variables) {  const fromMany = splitParamList(variables?.order_sns);  if (fromMany.length) return fromMany;  const single = String(variables?.order_sn || "").trim();  return single ? [single] : [];}function porderSnListFromVariables(variables) {  const fromMany = splitParamList(variables?.porder_sns);  if (fromMany.length) return fromMany;  const single = String(variables?.porder_sn || "").trim();  return single ? [single] : [];}function isOrderPaymentFlow(flow) {  return flow?.scriptType === "balance_payment" || flow?.scriptType === "bank_payment";}function isPorderSnFlow(flow) {  return flow?.scriptType === "porder_balance_payment" || flow?.scriptType === "porder_bank_payment" || isPorderShipmentFlow(flow);}function customerScopedSnConfig(flow) {  if (isOrderPaymentFlow(flow)) return { list: orderSnListFromVariables, singleKey: "order_sn", manyKey: "order_sns", label: "\u8ba2\u5355\u53f7" };  if (isPorderSnFlow(flow)) return { list: porderSnListFromVariables, singleKey: "porder_sn", manyKey: "porder_sns", label: "\u914d\u9001\u5355\u53f7" };  return null;}function routedVariablesForCustomerSn(variables, config, sns) {  const next = { ...(variables || {}) };  if (sns.length > 1) {    next[config.manyKey] = sns;    delete next[config.singleKey];  } else {    next[config.singleKey] = sns[0];    delete next[config.manyKey];  }  return next;}function lastWarehousePorderSn(flow) {  if (flow?.lastPorderSn) return flow.lastPorderSn;  const warehouseFlow = readFlows().find((item) => item.id === BUILTIN_FLOW_DEFINITIONS.warehouse_delivery.id);  return warehouseFlow?.lastPorderSn || "";}function normalizePositiveInt(value, fallback) {  const number = Number(value);  return Number.isFinite(number) && number > 0 ? Math.floor(number) : fallback;}function sanitizePaymentVariables(next, { bank = false } = {}) {  next.discounts_id = "";  next.predict_logistics_price_is_pay = "0";  delete next.pay_amount;  delete next.balance_pay_fields;  if (bank) {    next.pay_bank_method = "1";    next.pay_name = "自动化测试";    next.pay_remark = "自动化银行付款";    next.finance_confirm = true;    delete next.pay_date;    delete next.pay_reach_date;    delete next.bank_pay_fields;  } else {    next.include_balance_pay_amount = false;  }}function sanitizeScriptVariables(scriptType, variables, flow = null) {  const next = { ...(variables || {}) };  if (scriptType === "shopping_cart") {    const shopType = String(next.shop_type || splitParamList(next.shop_types)[0] || "1688").trim() || "1688";    next.shop_type = shopType;    next.shop_types = [shopType];    next.target_shops = normalizePositiveInt(next.target_shops || next.shop_count, 4);    next.per_shop = normalizePositiveInt(next.per_shop, 5);    next.strict_shop_count = false;    delete next.shop_count;    return next;  }  if (scriptType === "order_quote") {    next.order_shop_count = normalizePositiveInt(next.order_shop_count || next.target_shops || next.shop_count, 1);    next.order_per_shop = normalizePositiveInt(next.order_per_shop || next.order_item_count, 2);    next.order_item_count = next.order_per_shop;    next.order_item_num = normalizePositiveInt(next.order_item_num, 10);    next.logistics_id = next.logistics_id || "1";    next.shop_type = "1688";    next.submit_order = true;    next.run_backend_flow = true;    next.auto_fill_cart_on_shortage = true;    delete next.keyword;    delete next.target_shops;    delete next.shop_count;    return next;  }  if (scriptType === "balance_payment") {    sanitizePaymentVariables(next);    return next;  }  if (scriptType === "bank_payment") {    sanitizePaymentVariables(next, { bank: true });    return next;  }  if (scriptType === "purchase_to_shelf") {    next.link_quote_balance_before_shelf = true;    next.auto_quote_and_pay = true;    next.order_shop_count = normalizePositiveInt(next.order_shop_count, 1);    next.order_per_shop = normalizePositiveInt(next.order_per_shop, 2);    next.order_item_num = normalizePositiveInt(next.order_item_num, 10);    next.purchase_unit_price = "10";    next.purchase_freight = "0";    next.warehouse_index = next.warehouse_index || "2";    return next;  }  if (scriptType === "purchase_to_shelf_chain") {    next.order_shop_count = normalizePositiveInt(next.order_shop_count, 1);    next.order_per_shop = normalizePositiveInt(next.order_per_shop, 2);    next.order_item_num = normalizePositiveInt(next.order_item_num, 10);    next.purchase_unit_price = "10";    next.purchase_freight = "0";    next.warehouse_index = next.warehouse_index || "2";    return next;  }  if (scriptType === "warehouse_delivery") {    next.warehouse_sku_count = normalizePositiveInt(next.warehouse_sku_count || next.porder_sku_count || next.sku_count, 1);    next.send_num = normalizePositiveInt(next.send_num, 1);    next.porder_logistics_id = "14";    next.warehouse_keywords = "";    next.run_backend_delivery_flow = true;    delete next.order_detail_id;    delete next.porder_sn;    return next;  }  if (scriptType === "porder_balance_payment") {    if (!splitParamList(next.porder_sns).length) next.porder_sn = String(next.porder_sn || lastWarehousePorderSn(flow) || "").trim();    next.run_backend_porder_flow = false;    sanitizePaymentVariables(next);    return next;  }  if (scriptType === "porder_bank_payment") {    if (!splitParamList(next.porder_sns).length) next.porder_sn = String(next.porder_sn || lastWarehousePorderSn(flow) || "").trim();    next.run_backend_porder_flow = false;    sanitizePaymentVariables(next, { bank: true });    return next;  }  if (isPorderShipmentFlow(flow)) {    if (!splitParamList(next.porder_sns).length) next.porder_sn = String(next.porder_sn || lastWarehousePorderSn(flow) || "").trim();    return next;  }  if (scriptType === "material_generation") {
    next.count = normalizePositiveInt(next.count, 1);
    next.name = String(next.name || "").trim();
    return next;
  }
  return next;}async function api(path, options = {}) {  const headers = { ...(options.headers || {}) };  const requestOptions = { ...options };  if (state.token) headers.Authorization = `Bearer ${state.token}`;  if (requestOptions.body && typeof requestOptions.body !== "string") {    headers["Content-Type"] = "application/json";    requestOptions.body = JSON.stringify(requestOptions.body);  }  const response = await fetch(path, { ...requestOptions, headers });  if (response.status === 401) {    let detail = "登录已失效，请重新登录";    try {      const text = await response.text();      try { detail = JSON.parse(text).detail || detail; } catch { if (text) detail = text; }    } catch { /* body 读取失败保持默认提示 */ }    localStorage.removeItem("token");    state.token = "";    state.user = null;    showToast(detail);    if (path !== "/api/auth/login") {      await sleep(600);      renderLogin();    }    throw new Error(detail);  }  if (!response.ok) {    let detail = response.statusText;    try {      const text = await response.text();      try { detail = JSON.parse(text).detail || text || detail; } catch { detail = text || detail; }    } catch { /* body 读取失败保持 statusText */ }    showToast(detail);    throw new Error(detail);  }  if (response.status === 204) return null;  return response.json();}function sleep(ms) {  return new Promise((resolve) => window.setTimeout(resolve, ms));}async function openProtectedFile(path) {  const response = await fetch(path, {    headers: { Authorization: `Bearer ${state.token}` },  });  if (!response.ok) {    showToast("文件不存在或无权访问");    return;  }  const blob = await response.blob();  const url = URL.createObjectURL(blob);  window.open(url, "_blank", "noopener,noreferrer");}function renderLogin() {  // 读取记住的账号（不存储密码到 localStorage）
  const savedUsername = localStorage.getItem("savedUsername") || "";  const savedPassword = (() => {    try { return atob(localStorage.getItem("savedPassword") || ""); } catch { return ""; }  })();  const remember = !!(savedUsername && savedPassword);  appEl.innerHTML = `    <section class="login-wrap">      <form class="login-panel" id="loginForm">        <h1>AI 功能测试工作台</h1>        <p>请输入管理员账号登录</p>        <div class="form-grid">          <div class="field">            <label for="username">账号</label>            <input id="username" name="username" autocomplete="username" value="${escapeHtml(savedUsername)}" required />          </div>          <div class="field">            <label for="password">密码</label>            <input id="password" name="password" type="password" autocomplete="current-password" value="${escapeHtml(savedPassword)}" required />          </div>          <label class="check-field remember-check">            <input id="rememberPwd" name="rememberPwd" type="checkbox" ${remember ? "checked" : ""} />            <span>记住密码</span>          </label>          <button class="btn" type="submit">登录</button>        </div>      </form>    </section>  `;  document.querySelector("#loginForm").addEventListener("submit", async (event) => {    event.preventDefault();    const form = new FormData(event.currentTarget);    const rememberPwd = form.get("rememberPwd") === "on";    try {      const result = await api("/api/auth/login", {        method: "POST",        body: {          username: form.get("username"),          password: form.get("password"),        },      });      state.token = result.access_token;      state.user = result.user;      localStorage.setItem("token", state.token);      if (rememberPwd) {        localStorage.setItem("savedUsername", form.get("username"));        localStorage.setItem("savedPassword", btoa(form.get("password")));      } else {        localStorage.removeItem("savedUsername");        localStorage.removeItem("savedPassword");      }      await renderShell();    } catch (error) {      showToast(error.message);    }  });}async function renderShell() {  if (!state.user) state.user = await api("/api/auth/me");  if (!document.querySelector(".shell")) {    const nav = views      .filter((item) => !item.adminOnly || isAdmin())      .map((item) => `<button class="${state.view === item.key ? "active" : ""}" data-view="${item.key}">${escapeHtml(item.label)}</button>`)      .join("");    appEl.innerHTML = `    <div class="shell">      <aside class="sidebar">        <div class="brand">          <strong>AI 功能测试工作台</strong>          <span>${escapeHtml(state.user.username)}</span>        </div>        <nav class="nav" id="mainNav">${nav}</nav>        <div class="sidebar-foot">
  <span class="role-pill">${escapeHtml(state.user.role)}</span>
  ${isAdmin() ? '<a href="/static/admin/templates.html" target="_blank" style="display:block;font-size:12px;margin-top:6px;color:var(--accent)">模板管理</a><a href="/static/admin/heal-logs.html" target="_blank" style="display:block;font-size:12px;color:var(--accent)">自愈记录</a>' : ''}
</div>      </aside>      <main class="main">        <header class="topbar">          <h2 id="viewTitle">${escapeHtml((views.find((v) => v.key === state.view) || views[0]).label)}</h2>          <div class="theme-picker">            <button class="theme-dot${(localStorage.getItem('theme')||'shuimo')==='shuimo'?' active':''}" data-theme="shuimo" style="background:#2f4f46" title="\u6c34\u58a8"></button>            <button class="theme-dot${localStorage.getItem('theme')==='zhuanye'?' active':''}" data-theme="zhuanye" style="background:#6366f1" title="\u4e13\u4e1a\u84dd\u7070"></button>            <button class="theme-dot${localStorage.getItem('theme')==='qingxuan'?' active':''}" data-theme="qingxuan" style="background:#3b82f6" title="\u6e05\u723d\u6d45\u8272"></button>            <button class="theme-dot${localStorage.getItem('theme')==='xiaolan'?' active':''}" data-theme="xiaolan" style="background:#ff6b9d" title="\u5c0f\u5170"></button>          </div>          <button class="btn secondary" id="logoutBtn" type="button">退出</button>        </header>        <section class="content" id="content"></section>      </main>    </div>  `;    document.querySelector("#mainNav").addEventListener("click", (event) => {      const button = event.target.closest("[data-view]");      if (!button) return;      state.view = button.dataset.view;      renderShell().catch((error) => showToast(error.message || '页面加载失败'));    });    // 主题切换
    document.querySelectorAll(".theme-dot").forEach((dot) => {
      dot.addEventListener("click", () => {
        const name = dot.dataset.theme;
        document.documentElement.dataset.theme = name;
        localStorage.setItem("theme", name);
        document.querySelectorAll(".theme-dot").forEach((d) => d.classList.toggle("active", d.dataset.theme === name));
      });
    });
    document.querySelector("#logoutBtn").addEventListener("click", () => {      localStorage.removeItem("token");      state.token = "";      state.user = null;      renderLogin();    });  } else {    const titleEl = document.querySelector("#viewTitle");    const label = (views.find((v) => v.key === state.view) || views[0]).label;    if (titleEl) titleEl.textContent = label;    document.querySelectorAll("#mainNav [data-view]").forEach((btn) => {      btn.classList.toggle("active", btn.dataset.view === state.view);    });  }  await renderCurrentView();}function contentEl() {  return document.querySelector("#content");}function badge(value) {  const labels = {    passed: "\u901a\u8fc7",    failed: "\u5931\u8d25",    active: "\u542f\u7528",    inactive: "\u505c\u7528",    admin: "\u4e3b\u8d26\u53f7",    normal: "\u5b50\u8d26\u53f7",    api: "\u63a5\u53e3",    ui: "UI",    draft: "\u8349\u7a3f",    uploaded: "Axure\u5df2\u4e0a\u4f20",    screenshot_uploaded: "\u622a\u56fe\u5df2\u4e0a\u4f20",    screenshot_analyzed: "\u622a\u56fe\u5df2\u8bc6\u522b",    requirements_updated: "\u9700\u6c42\u5df2\u8865\u5145",    scanned: "\u9875\u9762\u5df2\u626b\u63cf",    cases_generated: "\u6d4b\u8bd5\u70b9\u5df2\u751f\u6210",    ui_steps_generated: "\u6b65\u9aa4\u5df2\u751f\u6210",    approved: "\u5df2\u786e\u8ba4",    queued: "\u6392\u961f\u4e2d",    pending: "\u7b49\u5f85\u4e2d",    running: "\u6267\u884c\u4e2d",    error: "\u5f02\u5e38",    skipped: "\u5df2\u8df3\u8fc7",    ok: "\u901a\u8fc7",    success: "\u6210\u529f",    done: "\u5b8c\u6210",    warning: "\u9884\u8b66",    blocked: "\u963b\u585e",    untested: "\u672a\u6d4b\u8bd5",    unknown: "\u672a\u77e5",    partial: "\u90e8\u5206\u5b8c\u6210",    auth_blocked: "\u767b\u5f55\u53d7\u963b",    failed_verification: "\u9a8c\u8bc1\u5931\u8d25",    axure_bound: "\u5df2\u7ed1\u5b9a\u9875\u9762",    executable: "\u53ef\u6267\u884c",    missing_variables: "\u7f3a\u5c11\u53d8\u91cf",    locator_risk: "\u5b9a\u4f4d\u5668\u98ce\u9669",    auth_risk: "\u767b\u5f55\u6001\u98ce\u9669",    not_recommended: "\u4e0d\u5efa\u8bae\u81ea\u52a8\u5316",    needs_review: "\u9700\u4eba\u5de5\u786e\u8ba4",    unchecked: "\u672a\u68c0\u67e5",    flaky: "\u4e0d\u7a33\u5b9a",    high: "\u9ad8",    medium: "\u4e2d",    low: "\u4f4e",    critical: "\u7d27\u6025",    P0: "P0 \u7d27\u6025",    P1: "P1 \u9ad8",    P2: "P2 \u4e2d",    P3: "P3 \u4f4e",    "\u5145\u5206": "\u5145\u5206",    "\u4e0d\u8db3": "\u4e0d\u8db3",    "\u7f3a\u5931": "\u7f3a\u5931",    "\u9700\u4eba\u5de5\u786e\u8ba4": "\u9700\u4eba\u5de5\u786e\u8ba4",  };  const statusClassMap = {    passed: "ok",    success: "ok",    done: "ok",    ok: "ok",    active: "ok",    approved: "ok",    executable: "ok",    scanned: "ok",    cases_generated: "ok",    ui_steps_generated: "ok",    screenshot_analyzed: "ok",    "\u5145\u5206": "ok",    failed: "fail",    error: "fail",    blocked: "fail",    auth_blocked: "fail",    failed_verification: "fail",    missing_variables: "fail",    not_recommended: "fail",    flaky: "fail",    critical: "fail",    P0: "fail",    "\u7f3a\u5931": "fail",    skipped: "warn",    pending: "warn",    queued: "warn",    running: "warn",    inactive: "warn",    uploaded: "warn",    screenshot_uploaded: "warn",    requirements_updated: "warn",    draft: "warn",    needs_review: "warn",    unchecked: "warn",    untested: "warn",    unknown: "warn",    partial: "warn",    warning: "warn",    locator_risk: "warn",    auth_risk: "warn",    high: "warn",    medium: "warn",    low: "",    P1: "warn",    P2: "warn",    P3: "",    "\u4e0d\u8db3": "warn",    "\u9700\u4eba\u5de5\u786e\u8ba4": "warn",  };  const text = escapeHtml(labels[value] || value || "-");  const cls = statusClassMap[value] || "";  return `<span class="badge ${cls}">${text}</span>`;}function actionMenu(label, content) {  if (!content) return "";  return `<details class="action-menu"><summary>${escapeHtml(label)}</summary><div class="action-menu-list">${content}</div></details>`;}function renderTable(columns, rows, framed = true, rowAttrs = null) {  if (!rows.length) return framed ? `<div class="panel"><div class="empty">暂无数据</div></div>` : `<div class="empty">暂无数据</div>`;  const head = columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("");  const body = rows    .map(      (row) => `        <tr${rowAttrs ? ` ${rowAttrs(row)}` : ""}>          ${columns            .map((column) => {              const raw = column.render ? column.render(row) : escapeHtml(short(row[column.key]));              return `<td>${raw}</td>`;            })            .join("")}        </tr>      `,    )    .join("");  return `<div class="${framed ? "panel " : ""}table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;}function optionList(items, valueKey = "id", labelKey = "name", selected = "", allLabel = "全部") {  return [    `<option value="">${escapeHtml(allLabel)}</option>`,    ...items.map((item) => `<option value="${escapeHtml(item[valueKey])}" ${String(item[valueKey]) === String(selected) ? "selected" : ""}>${escapeHtml(item[labelKey])}</option>`),  ].join("");}const ACCOUNT_RUNTIME_KEYS = new Set(["username", "password", "code", "captcha", "captcha_code", "verify_code", "verification_code"]);function accountLabel(account, projects = []) {  if (!account) return "";  const project = account.project_id ? projects.find((item) => String(item.id) === String(account.project_id)) : null;  const scope = account.project_id ? project?.name || `项目#${account.project_id}` : "全局";  return `${account.profile_name}（${scope}）`;}function accountOptions(accounts, selected = "", projects = [], emptyLabel = "跟随默认账号") {  return [    `<option value="" ${selected ? "" : "selected"}>${escapeHtml(emptyLabel)}</option>`,    ...(accounts || []).map((account) => {      const value = String(account.id);      return `<option value="${escapeHtml(value)}" ${value === String(selected || "") ? "selected" : ""}>${escapeHtml(accountLabel(account, projects))}</option>`;    }),  ].join("");}function accountNameById(accounts, id) {  const account = (accounts || []).find((item) => String(item.id) === String(id));  return account?.profile_name || "";}async function saveTestAccountBinding(targetType, targetId, accountProfileId) {  await api("/api/test-account-bindings", {    method: "PUT",    body: {      target_type: targetType,      target_id: Number(targetId),      account_profile_id: accountProfileId ? Number(accountProfileId) : null,    },  });}function openAccountBindingForm({ title, targetType, targetId, currentId, accounts, projects, emptyLabel = "不绑定/跟随上级", afterSave }) {  openForm(    title,    [{ name: "account_profile_id", label: "测试账号", type: "select", options: [{ value: "", label: emptyLabel }, ...(accounts || []).map((item) => ({ value: item.id, label: accountLabel(item, projects) }))] }],    { account_profile_id: currentId || "" },    async (data) => {      await saveTestAccountBinding(targetType, targetId, data.account_profile_id);      showToast("测试账号已保存");      if (afterSave) await afterSave();    },  );}function accountMaskedText(account) {  const values = account?.masked_variables || {};  const labels = {    username: "登录账号",    account: "登录账号",    password: "登录密码",    code: "验证码",    captcha: "验证码",    captcha_code: "验证码",    verify_code: "验证码",    verification_code: "验证码",  };  const text = Object.entries(values)    .map(([key, value]) => `${labels[key] || key}: ${value === "***" ? "已配置" : value}`)    .join("\n");  return text || "-";}function openTestAccountForm(item, projects, afterSave = renderProjects) {  const currentVariables = item?.variables || {};  const values = {    project_id: item?.project_id || "",    profile_name: item?.profile_name || "",    username: currentVariables.username || currentVariables.account || "",    password: "",    code: "",    login_url: item?.login_url || "",    username_locator: item?.username_locator || 'input[placeholder="邮箱/手机号"]\ninput[name="username"]\ninput[name="account"]\ninput[name="mobile"]\ninput[name="email"]\ninput[type="text"]',    password_locator: item?.password_locator || 'input[placeholder="请输入密码"]\ninput[type="password"]\ninput[name="password"]',    submit_locator: item?.submit_locator || 'button[type="submit"]\nbutton:has-text("登录")\n[role="button"]:has-text("登录")\ntext=登录',    success_url_contains: item?.success_url_contains || "",    success_selector: item?.success_selector || "",    status: item?.status || "active",  };  openForm(    item ? "编辑测试账号" : "新增测试账号",    [      { name: "project_id", label: "所属项目", type: "select", options: [{ value: "", label: "全局账号" }, ...(projects || []).map((project) => ({ value: project.id, label: project.name }))] },      { name: "profile_name", label: "账号档案名称", required: true },      { name: "username", label: "登录账号", required: true },      { name: "password", label: item ? "登录密码（留空不修改）" : "登录密码", type: "password" },      { name: "code", label: item ? "验证码（留空不修改）" : "验证码" },      { name: "login_url", label: "登录页 URL", placeholder: "留空时默认按目标站点自动拼接 /login" },      { name: "username_locator", label: "账号输入框定位器", type: "textarea", rows: 4, placeholder: "支持一行一个，按顺序兜底匹配" },      { name: "password_locator", label: "密码输入框定位器", type: "textarea", rows: 3, placeholder: "支持一行一个，按顺序兜底匹配" },      { name: "submit_locator", label: "登录按钮定位器", type: "textarea", rows: 4, placeholder: "支持一行一个，按顺序兜底匹配" },      { name: "success_url_contains", label: "登录成功 URL 关键字", placeholder: "例如 /customerHasBeenInvited，选填" },      { name: "success_selector", label: "登录成功元素定位器", placeholder: "例如 text=已邀请客户，选填" },      {        name: "status",        label: "状态",        type: "select",        options: [          { value: "active", label: "启用" },          { value: "inactive", label: "停用" },        ],      },    ],    values,    async (data) => {      const body = {        project_id: data.project_id ? Number(data.project_id) : null,        profile_name: data.profile_name,        variables: {          username: String(data.username || "").trim(),        },        login_url: String(data.login_url || "").trim(),        username_locator: String(data.username_locator || "").trim(),        password_locator: String(data.password_locator || "").trim(),        submit_locator: String(data.submit_locator || "").trim(),        success_url_contains: String(data.success_url_contains || "").trim(),        success_selector: String(data.success_selector || "").trim(),        status: data.status || "active",      };      const sensitive = {};      if (String(data.password || "").trim()) sensitive.password = data.password;      if (String(data.code || "").trim()) sensitive.code = data.code;      if (!item || Object.keys(sensitive).length) {        body.sensitive_variables = sensitive;      }      await api(item ? `/api/test-accounts/${item.id}` : "/api/test-accounts", { method: item ? "PUT" : "POST", body });      showToast("测试账号已保存");      await afterSave();    },  );}function readFlows() {  try {    const flows = JSON.parse(localStorage.getItem(FLOW_STORAGE_KEY) || "[]");    return Array.isArray(flows) ? flows : [];  } catch {    return [];  }}function writeFlows(flows) {  localStorage.setItem(FLOW_STORAGE_KEY, JSON.stringify(flows));}function readDeletedBuiltins() {  try {    const ids = JSON.parse(localStorage.getItem(DELETED_BUILTIN_KEY) || "[]");    return Array.isArray(ids) ? ids : [];  } catch {    return [];  }}function writeDeletedBuiltins(ids) {  localStorage.setItem(DELETED_BUILTIN_KEY, JSON.stringify(ids));}function isBuiltinDeleted(id) {  return readDeletedBuiltins().includes(id) || readHiddenBuiltins().includes(id);}function markBuiltinDeleted(id) {  const ids = readDeletedBuiltins();  if (!ids.includes(id)) {    ids.push(id);    writeDeletedBuiltins(ids);  }}function builtinDefinitionForFlow(flow) {  if (!flow) return null;  const directMatch = Object.values(BUILTIN_FLOW_DEFINITIONS).find((item) => item.id === flow.id);  if (directMatch) return directMatch;  const typeMatch = BUILTIN_FLOW_DEFINITIONS[flow.scriptType];  if (typeMatch && flow.name === typeMatch.name) return typeMatch;  return null;}function isDeletedBuiltinFlow(flow) {  const definition = builtinDefinitionForFlow(flow);  return Boolean(definition && readDeletedBuiltins().includes(definition.id));}function removeBuiltinDeleted(id) {  writeDeletedBuiltins(readDeletedBuiltins().filter((item) => item !== id));}function readDeletedFlows() {  try {    const rows = JSON.parse(localStorage.getItem(DELETED_FLOW_STORAGE_KEY) || "[]");    return Array.isArray(rows) ? rows : [];  } catch {    return [];  }}function writeDeletedFlows(rows) {  localStorage.setItem(DELETED_FLOW_STORAGE_KEY, JSON.stringify(rows || []));}function dataScriptDefaultProject(projects = []) {  return (projects || []).find((item) => item.name === "日本站测试") || (projects || [])[0] || null;}function dataScriptDefaultEnv(projects = [], envs = []) {  const project = dataScriptDefaultProject(projects);  return (envs || []).find((item) => project && String(item.project_id) === String(project.id)) || (envs || [])[0] || null;}function normalizeDataScriptFlows(flows = [], projects = [], envs = []) {  const project = dataScriptDefaultProject(projects);  const projectId = project?.id ? String(project.id) : "";  const defaultEnv = dataScriptDefaultEnv(projects, envs);  let changed = false;  const next = (flows || []).map((flow, index) => {    if (!flow) return flow;    let patched = flow;    if (flow.order === undefined || flow.order === null) { patched = { ...patched, order: index }; changed = true; }    if (!patched.projectId) { changed = true; const env = (envs || []).find((item) => patched.envId && String(item.id) === String(patched.envId) && String(item.project_id) === String(projectId)); patched = { ...patched, projectId, envId: String(env?.id || defaultEnv?.id || patched.envId || "") }; }    return patched;  });  if (changed) writeFlows(next);  return next;}function activeDataScriptProjectId(projects = []) {  if (!projects.length) return "";  const current = state.filters.projectId || localStorage.getItem("projectId") || "";  if (current && projects.some((item) => String(item.id) === String(current))) return String(current);  const project = dataScriptDefaultProject(projects);  const projectId = project?.id ? String(project.id) : "";  state.filters.projectId = projectId;  if (projectId) localStorage.setItem("projectId", projectId);  return projectId;}function dataScriptProjectMatches(item, projectId) {  return !projectId || String(item?.projectId || "") === String(projectId);}function deletedEntryKey(entry) {  return String(entry?.id || entry?.builtinId || entry?.flow?.id || "");}function saveDeletedFlow(flow, builtinDefinition = null) {  if (!flow) return;  const key = builtinDefinition?.id || flow.id || newFlowId();  const entry = {    id: key,    name: flow.name || builtinDefinition?.name || "数据脚本",    projectId: String(flow.projectId || ""),    envId: String(flow.envId || ""),    isBuiltin: Boolean(builtinDefinition),    builtinId: builtinDefinition?.id || "",    deletedAt: new Date().toISOString(),    flow: { ...flow },  };  const rows = readDeletedFlows().filter((item) => deletedEntryKey(item) !== key && item.builtinId !== key);  writeDeletedFlows([entry, ...rows]);}function deletedDataScriptRows(projects = [], envs = []) {  const defaultProject = dataScriptDefaultProject(projects);  const defaultEnv = dataScriptDefaultEnv(projects, envs);  const rows = readDeletedFlows().map((entry) => ({ ...entry, id: deletedEntryKey(entry), name: entry.name || entry.flow?.name || "????", projectId: String(entry.projectId || entry.flow?.projectId || defaultProject?.id || ""), envId: String(entry.envId || entry.flow?.envId || defaultEnv?.id || "") }));  const known = new Set(rows.map((entry) => entry.builtinId || entry.id));  const env = dataScriptDefaultEnv(projects, envs);  readDeletedBuiltins().forEach((id) => {    if (known.has(id)) return;    const definition = Object.values(BUILTIN_FLOW_DEFINITIONS).find((item) => item.id === id);    rows.push({      id,      name: definition?.name || id,      projectId: String(env?.project_id || dataScriptDefaultProject(projects)?.id || ""),      envId: String(env?.id || ""),      isBuiltin: true,      builtinId: id,      legacyBuiltin: true,      deletedAt: "",      flow: null,    });  });  return rows;}function restoreDeletedFlow(entry) {  if (!entry) return;  const key = deletedEntryKey(entry);  if (entry.builtinId) removeBuiltinDeleted(entry.builtinId);  const sourceFlow = entry.flow ? { ...entry.flow } : null;  if (sourceFlow) {    let restored = { ...sourceFlow, projectId: String(sourceFlow.projectId || entry.projectId || ""), envId: String(sourceFlow.envId || entry.envId || "") };    let flows = readFlows();    if (entry.builtinId) {      const definition = Object.values(BUILTIN_FLOW_DEFINITIONS).find((item) => item.id === entry.builtinId);      flows = flows.filter((flow) => flow.id !== entry.builtinId && (!definition || flow.name !== definition.name));      restored.id = entry.builtinId;      restored.name = restored.name || definition?.name || entry.name;    } else if (flows.some((flow) => flow.id === restored.id)) {      restored = { ...restored, id: newFlowId(), name: `${restored.name || entry.name || "数据脚本"}_恢复` };    }    writeFlows([...flows, restored]);  }  writeDeletedFlows(readDeletedFlows().filter((item) => deletedEntryKey(item) !== key));}function readHiddenFlows() {  try {    const rows = JSON.parse(localStorage.getItem(HIDDEN_FLOW_STORAGE_KEY) || "[]");    return Array.isArray(rows) ? rows : [];  } catch {    return [];  }}function writeHiddenFlows(rows) {  localStorage.setItem(HIDDEN_FLOW_STORAGE_KEY, JSON.stringify(rows || []));}function readHiddenBuiltins() {  try {    const ids = JSON.parse(localStorage.getItem(HIDDEN_BUILTIN_KEY) || "[]");    return Array.isArray(ids) ? ids : [];  } catch {    return [];  }}function writeHiddenBuiltins(ids) {  localStorage.setItem(HIDDEN_BUILTIN_KEY, JSON.stringify(ids));}function removeBuiltinHidden(id) {  writeHiddenBuiltins(readHiddenBuiltins().filter((item) => item !== id));}function hiddenEntryKey(entry) {  return String(entry?.id || entry?.builtinId || entry?.flow?.id || "");}function markBuiltinHidden(id) {  const ids = readHiddenBuiltins();  if (!ids.includes(id)) {    ids.push(id);    writeHiddenBuiltins(ids);  }}function saveHiddenFlow(flow, builtinDefinition = null) {  if (!flow) return;  const key = builtinDefinition?.id || flow.id || newFlowId();  const entry = {    id: key,    name: flow.name || builtinDefinition?.name || "数据脚本",    projectId: String(flow.projectId || ""),    envId: String(flow.envId || ""),    isBuiltin: Boolean(builtinDefinition),    builtinId: builtinDefinition?.id || "",    hiddenAt: new Date().toISOString(),    flow: { ...flow },  };  const rows = readHiddenFlows().filter((item) => hiddenEntryKey(item) !== key && item.builtinId !== key);  writeHiddenFlows([entry, ...rows]);}function restoreHiddenFlow(entry) {  if (!entry) return;  const key = hiddenEntryKey(entry);  if (entry.builtinId) removeBuiltinHidden(entry.builtinId);  const sourceFlow = entry.flow ? { ...entry.flow } : null;  if (sourceFlow) {    let restored = { ...sourceFlow, projectId: String(sourceFlow.projectId || entry.projectId || ""), envId: String(sourceFlow.envId || entry.envId || "") };    let flows = readFlows();    if (entry.builtinId) {      const definition = Object.values(BUILTIN_FLOW_DEFINITIONS).find((item) => item.id === entry.builtinId);      flows = flows.filter((flow) => flow.id !== entry.builtinId && (!definition || flow.name !== definition.name));      restored.id = entry.builtinId;      restored.name = restored.name || definition?.name || entry.name;    } else if (flows.some((flow) => flow.id === restored.id)) {      restored = { ...restored, id: newFlowId(), name: `${restored.name || entry.name || "数据脚本"}_恢复` };    }    writeFlows([...flows, restored]);  }  writeHiddenFlows(readHiddenFlows().filter((item) => hiddenEntryKey(item) !== key));}function hiddenDataScriptRows(projects = [], envs = []) {  const defaultProject = dataScriptDefaultProject(projects);  const defaultEnv = dataScriptDefaultEnv(projects, envs);  const rows = readHiddenFlows().map((entry) => ({ ...entry, id: hiddenEntryKey(entry), name: entry.name || entry.flow?.name || "数据脚本", projectId: String(entry.projectId || entry.flow?.projectId || defaultProject?.id || ""), envId: String(entry.envId || entry.flow?.envId || defaultEnv?.id || "") }));  return rows;}function newFlowId() {  return `flow_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;}function uniqueList(items) {  const seen = new Set();  const result = [];  (items || []).forEach((item) => {    const text = String(item || "").trim();    const key = text.toLowerCase();    if (text && !seen.has(key)) {      seen.add(key);      result.push(text);    }  });  return result;}function listValue(value) {  if (Array.isArray(value)) return value;  if (typeof value === "string") {    return value.split(",").map((item) => item.trim()).filter(Boolean);  }  return [];}function stripCaseNamePrefix(value) {  let text = String(value || "").trim();  let changed = true;  while (changed) {    changed = false;    CASE_NAME_PREFIXES.forEach((prefix) => {      if (text.startsWith(prefix)) {        text = text.slice(prefix.length).trim();        changed = true;      }    });  }  return text;}function findCaseByName(cases, name) {  const target = stripCaseNamePrefix(name);  return (cases || []).find((item) => stripCaseNamePrefix(item.case_name) === target);}function ensureShoppingCartScript(flows, projects, envs, cases) {  if (isBuiltinDeleted("shopping_cart_builtin")) return flows;  const scriptName = "\u5546\u54c1\u8d2d\u7269\u8f66";  const login = findCaseByName(cases, "\u767b\u5f55");  const search = findCaseByName(cases, "\u641c\u7d22\u5546\u54c1");  const detail = findCaseByName(cases, "\u5546\u54c1\u8be6\u60c5");  const cart = findCaseByName(cases, "\u52a0\u5165\u8d2d\u7269\u8f66");  const env = dataScriptDefaultEnv(projects, envs);  const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";  const caseIds = [login, search, detail, cart].filter(Boolean).map((item) => item.id);  if (!env || caseIds.length < 4) return flows;  const loginBody = parseJsonText(login?.body || "{}", {});  const existingIndex = flows.findIndex((flow) => flow.id === "shopping_cart_builtin") >= 0    ? flows.findIndex((flow) => flow.id === "shopping_cart_builtin")    : flows.findIndex((flow) => flow.name === scriptName);  const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};  let existingVariables = {};  try {    existingVariables = parseJsonText(existingFlow.variables || "{}", {});  } catch {    existingVariables = {};  }  const defaultVariables = {    keywords: ["\u8863\u670d", "\u978b\u5b50", "\u978b", "usp", "USP", "\u5305", "\u5e3d\u5b50", "\u88d9\u5b50", "\u8033\u73af", "\u889c\u5b50", "\u624b\u673a\u58f3", "\u624b\u8868", "\u9879\u94fe", "\u6c34\u676f", "\u6587\u5177", "\u6536\u7eb3"],    preferred_keywords: ["\u8863\u670d", "\u978b\u5b50", "\u978b", "\u5305"],    boost_keywords: ["\u8863\u670d", "\u978b\u5b50", "\u5305"],    random_keyword: true,    shop_type: "1688",    shop_types: ["1688"],    target_shops: 4,    per_shop: 5,    page_size: 50,    max_pages: 10,    batch_size: 30,    detail_workers: 4,    quantities: "2,3,5",    sleep: 0.2,    no_fallback_sku: false,    strict_shop_count: false,    account: loginBody.account || "12345678990",    password: loginBody.password || "123456",    client_tool: "1",  };  const mergedVariables = { ...defaultVariables, ...existingVariables };  mergedVariables.keywords = uniqueList([...listValue(existingVariables.keywords), ...defaultVariables.keywords]);  mergedVariables.preferred_keywords = uniqueList([...listValue(existingVariables.preferred_keywords), ...defaultVariables.preferred_keywords]);  mergedVariables.boost_keywords = uniqueList([...listValue(existingVariables.boost_keywords), ...defaultVariables.boost_keywords]);  if (!mergedVariables.shop_type) mergedVariables.shop_type = defaultVariables.shop_type;  if (!mergedVariables.target_shops) mergedVariables.target_shops = defaultVariables.target_shops;  if (!mergedVariables.page_size) mergedVariables.page_size = defaultVariables.page_size;  if (!mergedVariables.max_pages) mergedVariables.max_pages = defaultVariables.max_pages;  if (!mergedVariables.batch_size) mergedVariables.batch_size = defaultVariables.batch_size;  if (!mergedVariables.detail_workers) mergedVariables.detail_workers = defaultVariables.detail_workers;  if (!mergedVariables.quantities) mergedVariables.quantities = defaultVariables.quantities;  if (mergedVariables.sleep === undefined || mergedVariables.sleep === null) mergedVariables.sleep = defaultVariables.sleep;  if (mergedVariables.client_tool === "2" || !mergedVariables.client_tool) mergedVariables.client_tool = defaultVariables.client_tool;  if (existingVariables.account === "abner" && loginBody.account) mergedVariables.account = loginBody.account;  if (existingVariables.password === "12345" && loginBody.password) mergedVariables.password = loginBody.password;  if (!mergedVariables.client_tool && loginBody.client_tool) mergedVariables.client_tool = loginBody.client_tool;  const nextFlow = {    ...existingFlow,    id: "shopping_cart_builtin",    name: existingFlow.name || scriptName,    scriptType: "shopping_cart",    projectId: String(projectId),    envId: String(env.id),    caseIds,    variables: JSON.stringify(mergedVariables, null, 2),  };  const next = existingIndex >= 0    ? flows        .map((flow, index) => (index === existingIndex ? nextFlow : flow))        .filter((flow, index) => index === existingIndex || flow.id !== "shopping_cart_builtin")    : [...flows, nextFlow];  writeFlows(next);  return next;}function ensureOrderQuoteScript(flows, projects, envs, cases) {  if (isBuiltinDeleted("order_quote_builtin")) return flows;  const scriptName = "\u8ba2\u5355\u62a5\u4ef7";  const login = findCaseByName(cases, "\u767b\u5f55");  const env = dataScriptDefaultEnv(projects, envs);  const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";  if (!env) return flows;  const loginBody = parseJsonText(login?.body || "{}", {});  const existingIndex = flows.findIndex((flow) => flow.id === "order_quote_builtin") >= 0    ? flows.findIndex((flow) => flow.id === "order_quote_builtin")    : flows.findIndex((flow) => flow.name === scriptName);  const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};  let existingVariables = {};  try {    existingVariables = parseJsonText(existingFlow.variables || "{}", {});  } catch {    existingVariables = {};  }  const defaultVariables = {    order_item_count: 2,    order_item_num: 10,    price_cut: 0,    logistics_id: "1",    create_type: "send",    submit_order: true,    run_backend_flow: true,    skip_create_order: false,    client_remark: "\u81ea\u52a8\u5316\u63d0\u51fa\u8ba2\u5355",    quote_unit_price: "10",    confirm_freight: "5",    confirm_volume: "1x2x3",    confirm_weight: 200,    translate_is_temp: "0",    confirm_is_temp: "0",    offer_is_temp: "0",    account: loginBody.account || "12345678990",    password: loginBody.password || "123456",    client_tool: "1",    backend_account: "Y001",    backend_password: "raku@123456``",    backend_system: "1",    backend_code: "wnm666",  };  const mergedVariables = { ...defaultVariables, ...existingVariables };  if (!mergedVariables.order_item_count) mergedVariables.order_item_count = defaultVariables.order_item_count;  if (!mergedVariables.order_item_num) mergedVariables.order_item_num = defaultVariables.order_item_num;  if (!mergedVariables.logistics_id) mergedVariables.logistics_id = defaultVariables.logistics_id;  if (!mergedVariables.create_type) mergedVariables.create_type = defaultVariables.create_type;  if (mergedVariables.submit_order === undefined || mergedVariables.submit_order === null) {    mergedVariables.submit_order = defaultVariables.submit_order;  }  if (mergedVariables.run_backend_flow === undefined || mergedVariables.run_backend_flow === null) {    mergedVariables.run_backend_flow = defaultVariables.run_backend_flow;  }  if (!mergedVariables.quote_unit_price) mergedVariables.quote_unit_price = defaultVariables.quote_unit_price;  if (!mergedVariables.confirm_freight) mergedVariables.confirm_freight = defaultVariables.confirm_freight;  if (!mergedVariables.confirm_volume) mergedVariables.confirm_volume = defaultVariables.confirm_volume;  if (!mergedVariables.confirm_weight) mergedVariables.confirm_weight = defaultVariables.confirm_weight;  if (!mergedVariables.backend_system) mergedVariables.backend_system = defaultVariables.backend_system;  if (!mergedVariables.backend_code) mergedVariables.backend_code = defaultVariables.backend_code;  if (mergedVariables.client_tool === "2" || !mergedVariables.client_tool) mergedVariables.client_tool = defaultVariables.client_tool;  if (existingVariables.account === "abner" && loginBody.account) mergedVariables.account = loginBody.account;  if (existingVariables.password === "12345" && loginBody.password) mergedVariables.password = loginBody.password;  const nextFlow = {    ...existingFlow,    id: "order_quote_builtin",    name: existingFlow.name || scriptName,    scriptType: "order_quote",    projectId: String(projectId),    envId: String(env.id),    caseIds: existingFlow.caseIds || [],    variables: JSON.stringify(mergedVariables, null, 2),  };  const next = existingIndex >= 0    ? flows        .map((flow, index) => (index === existingIndex ? nextFlow : flow))        .filter((flow, index) => index === existingIndex || flow.id !== "order_quote_builtin")    : [...flows, nextFlow];  writeFlows(next);  return next;}function ensurePaymentScript(flows, projects, envs, cases, config) {  if (isBuiltinDeleted(config.id)) return flows;  const login = findCaseByName(cases, "\u767b\u5f55");  const orderList = findCaseByName(cases, "\u524d\u53f0\u8ba2\u5355\u5217\u8868");  const payCase = findCaseByName(cases, config.caseName);  const financeCase = findCaseByName(cases, "\u8d22\u52a1\u786e\u8ba4\u5165\u91d1");  const env = dataScriptDefaultEnv(projects, envs);  const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";  if (!env) return flows;  const caseIds = [orderList, payCase, config.scriptType === "bank_payment" ? financeCase : null].filter(Boolean).map((item) => item.id);  const loginBody = parseJsonText(login?.body || "{}", {});  const existingIndex = flows.findIndex((flow) => flow.id === config.id) >= 0    ? flows.findIndex((flow) => flow.id === config.id)    : flows.findIndex((flow) => flow.name === config.name);  const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};  let existingVariables = {};  try {    existingVariables = parseJsonText(existingFlow.variables || "{}", {});  } catch {    existingVariables = {};  }  const commonVariables = {    order_status_name: "\u7b49\u5f85\u4ed8\u6b3e",    page: 1,    page_size: 10,    order_by: "desc",    discounts_id: "",    predict_logistics_price_is_pay: "0",    account: loginBody.account || "12345678990",    password: loginBody.password || "123456",    client_tool: "1",  };  const typeVariables = config.scriptType === "bank_payment"    ? {        pay_bank_method: "1",        pay_reach_after_days: 0,        pay_name: "\u81ea\u52a8\u5316\u6d4b\u8bd5",        pay_remark: "\u81ea\u52a8\u5316\u94f6\u884c\u4ed8\u6b3e",        finance_confirm: true,        finance_confirm_initial_delay: 2,        finance_confirm_retries: 6,        finance_confirm_delay: 2,        backend_account: "Y001",        backend_password: "raku@123456``",        backend_system: "1",        backend_code: "wnm666",      }    : {        include_balance_pay_amount: false,        balance_pay_fields: {},      };  const mergedVariables = { ...commonVariables, ...typeVariables, ...existingVariables };  if (mergedVariables.client_tool === "2" || !mergedVariables.client_tool) mergedVariables.client_tool = commonVariables.client_tool;  if (existingVariables.account === "abner" && loginBody.account) mergedVariables.account = loginBody.account;  if (existingVariables.password === "12345" && loginBody.password) mergedVariables.password = loginBody.password;  const nextFlow = {    ...existingFlow,    id: config.id,    name: existingFlow.name || config.name,    scriptType: config.scriptType,    projectId: String(projectId),    envId: String(env.id),    caseIds: existingFlow.caseIds || caseIds,    variables: JSON.stringify(mergedVariables, null, 2),  };  const next = existingIndex >= 0    ? flows        .map((flow, index) => (index === existingIndex ? nextFlow : flow))        .filter((flow, index) => index === existingIndex || flow.id !== config.id)    : [...flows, nextFlow];  writeFlows(next);  return next;}function ensurePaymentScripts(flows, projects, envs, cases) {  let next = ensurePaymentScript(flows, projects, envs, cases, {    id: "balance_payment_builtin",    name: "\u4f59\u989d\u652f\u4ed8",    scriptType: "balance_payment",    caseName: "\u6570\u636e\u811a\u672c-\u4f59\u989d\u652f\u4ed8\u8ba2\u5355",  });  next = ensurePaymentScript(next, projects, envs, cases, {    id: "bank_payment_builtin",    name: "\u94f6\u884c\u652f\u4ed8",    scriptType: "bank_payment",    caseName: "\u6570\u636e\u811a\u672c-\u94f6\u884c\u652f\u4ed8\u8ba2\u5355",  });  return next;}function ensurePurchaseToShelfScript(flows, projects, envs, cases) {  if (isBuiltinDeleted("purchase_to_shelf_builtin")) return flows;  const scriptName = "\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6";  const login = findCaseByName(cases, "\u767b\u5f55");  const env = dataScriptDefaultEnv(projects, envs);  const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";  if (!env) return flows;  const caseNames = [    "\u6570\u636e\u811a\u672c-\u5f85\u62cd\u4e0b\u5546\u54c1\u5217\u8868",    "\u6570\u636e\u811a\u672c-\u4fdd\u5b58\u91c7\u8d2d\u4ea4\u6613\u53f7",    "\u6570\u636e\u811a\u672c-\u6807\u8bb0\u5f85\u6539\u4ef7",    "\u6570\u636e\u811a\u672c-\u63d0\u4ea4\u5f85\u8d22\u52a1\u4ed8\u6b3e",    "\u6570\u636e\u811a\u672c-\u4ea4\u6613\u53f7\u5f85\u4ed8\u6b3e\u5217\u8868",    "\u6570\u636e\u811a\u672c-\u4ea4\u6613\u53f7\u4ed8\u6b3e\u786e\u8ba4",    "\u6570\u636e\u811a\u672c-\u6838\u67e5\u5546\u54c1\u5217\u8868",    "\u6570\u636e\u811a\u672c-\u6838\u67e5\u5546\u54c1\u9884\u89c8",    "\u6570\u636e\u811a\u672c-\u5f00\u59cb\u6838\u67e5",    "\u6570\u636e\u811a\u672c-\u5e93\u4f4d\u9884\u89c8",    "\u6570\u636e\u811a\u672c-\u4e0a\u67b6\u5165\u5e93",  ];  const caseIds = caseNames    .map((name) => findCaseByName(cases, name))    .filter(Boolean)    .map((item) => item.id);  const loginBody = parseJsonText(login?.body || "{}", {});  const existingIndex = flows.findIndex((flow) => flow.id === "purchase_to_shelf_builtin") >= 0    ? flows.findIndex((flow) => flow.id === "purchase_to_shelf_builtin")    : flows.findIndex((flow) => flow.name === scriptName);  const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};  let existingVariables = {};  try {    existingVariables = parseJsonText(existingFlow.variables || "{}", {});  } catch {    existingVariables = {};  }  const defaultVariables = {    order_sn: "",    purchase_no: "",    link_quote_balance_before_shelf: true,    purchase_status: "\u5168\u90e8",    purchase_item_limit: 0,    purchase_unit_price: "10",    purchase_freight: "0",    purchase_transition_delay: 1,    finance_wait_pay_status: "2",    finance_confirm_retries: 8,    finance_confirm_delay: 2,    finance_days: 30,    follow_status: "3",    follow_retries: 8,    follow_delay: 2,    warehouse_index: "2",    shelf_type_set: [1, 3],    prefer_empty_grid: true,    inspection_transition_delay: 1,    account: loginBody.account || "12345678990",    password: loginBody.password || "123456",    client_tool: "1",    backend_account: "Y001",    backend_password: "raku@123456``",    backend_system: "1",    backend_code: "wnm666",  };  const mergedVariables = { ...defaultVariables, ...existingVariables };  if (mergedVariables.link_quote_balance_before_shelf === undefined || mergedVariables.link_quote_balance_before_shelf === null) {    mergedVariables.link_quote_balance_before_shelf = true;  }  if (!mergedVariables.purchase_status) mergedVariables.purchase_status = defaultVariables.purchase_status;  if (!mergedVariables.finance_wait_pay_status) mergedVariables.finance_wait_pay_status = defaultVariables.finance_wait_pay_status;  if (!mergedVariables.follow_status) mergedVariables.follow_status = defaultVariables.follow_status;  if (!mergedVariables.warehouse_index) mergedVariables.warehouse_index = defaultVariables.warehouse_index;  if (!Array.isArray(mergedVariables.shelf_type_set)) mergedVariables.shelf_type_set = defaultVariables.shelf_type_set;  if (mergedVariables.prefer_empty_grid === false) mergedVariables.prefer_empty_grid = true;  if (!mergedVariables.backend_system) mergedVariables.backend_system = defaultVariables.backend_system;  if (!mergedVariables.backend_code) mergedVariables.backend_code = defaultVariables.backend_code;  if (existingVariables.account === "abner" && loginBody.account) mergedVariables.account = loginBody.account;  if (existingVariables.password === "12345" && loginBody.password) mergedVariables.password = loginBody.password;  const nextFlow = {    ...existingFlow,    id: "purchase_to_shelf_builtin",    name: existingFlow.name || scriptName,    scriptType: "purchase_to_shelf",    projectId: String(projectId),    envId: String(env.id),    caseIds: existingFlow.caseIds?.length ? existingFlow.caseIds : caseIds,    variables: JSON.stringify(mergedVariables, null, 2),  };  const next = existingIndex >= 0    ? flows        .map((flow, index) => (index === existingIndex ? nextFlow : flow))        .filter((flow, index) => index === existingIndex || flow.id !== "purchase_to_shelf_builtin")    : [...flows, nextFlow];  writeFlows(next);  return next;}function ensurePurchaseToShelfChainScript(flows, projects, envs, cases) {  if (isBuiltinDeleted("purchase_to_shelf_chain_builtin")) return flows;  const scriptName = "\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6(\u7ec4\u5408\u811a\u672c)";  const login = findCaseByName(cases, "\u767b\u5f55");  const env = dataScriptDefaultEnv(projects, envs);  const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";  if (!env) return flows;  const loginBody = parseJsonText(login?.body || "{}", {});  const existingIndex = flows.findIndex((flow) => flow.id === "purchase_to_shelf_chain_builtin") >= 0    ? flows.findIndex((flow) => flow.id === "purchase_to_shelf_chain_builtin")    : flows.findIndex((flow) => flow.name === scriptName);  const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};  let existingVariables = {};  try {    existingVariables = parseJsonText(existingFlow.variables || "{}", {});  } catch {    existingVariables = {};  }  const defaultVariables = {    order_item_count: 2,    order_item_num: 10,    price_cut: "0",    logistics_id: "1",    client_remark: "\u81ea\u52a8\u5316\u63d0\u51fa\u8ba2\u5355",    submit_order: true,    run_backend_flow: true,    purchase_status: "\u5168\u90e8",    purchase_item_limit: 0,    purchase_unit_price: "10",    purchase_freight: "0",    purchase_transition_delay: 1,    finance_wait_pay_status: "2",    finance_confirm_retries: 8,    finance_confirm_delay: 2,    finance_days: 30,    follow_status: "3",    follow_retries: 8,    follow_delay: 2,    warehouse_index: "2",    shelf_type_set: [1, 3],    prefer_empty_grid: true,    inspection_transition_delay: 1,    account: loginBody.account || "12345678990",    password: loginBody.password || "123456",    client_tool: "1",    backend_account: "Y001",    backend_password: "raku@123456``",    backend_system: "1",    backend_code: "wnm666",  };  const mergedVariables = { ...defaultVariables, ...existingVariables };  if (!Array.isArray(mergedVariables.shelf_type_set)) mergedVariables.shelf_type_set = defaultVariables.shelf_type_set;  if (mergedVariables.prefer_empty_grid === false) mergedVariables.prefer_empty_grid = true;  if (existingVariables.account === "abner" && loginBody.account) mergedVariables.account = loginBody.account;  if (existingVariables.password === "12345" && loginBody.password) mergedVariables.password = loginBody.password;  const nextFlow = {    ...existingFlow,    id: "purchase_to_shelf_chain_builtin",    name: existingFlow.name || scriptName,    scriptType: "purchase_to_shelf_chain",    projectId: String(projectId),    envId: String(env.id),    caseIds: [],    variables: JSON.stringify(mergedVariables, null, 2),  };  const next = existingIndex >= 0    ? flows        .map((flow, index) => (index === existingIndex ? nextFlow : flow))        .filter((flow, index) => index === existingIndex || (flow.id !== "purchase_to_shelf_chain_builtin" && flow.name !== scriptName))    : [...flows, nextFlow];  writeFlows(next);  return next;}function ensureWarehouseDeliveryScript(flows, projects, envs, cases) {  if (isBuiltinDeleted("warehouse_delivery_builtin")) return flows;  const scriptName = "\u4ed3\u5e93\u63d0\u51fa\u914d\u9001\u5355";  const login = findCaseByName(cases, "\u767b\u5f55");  const env = dataScriptDefaultEnv(projects, envs);  const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";  if (!env) return flows;  const loginBody = parseJsonText(login?.body || "{}", {});  const existingIndex = flows.findIndex((flow) => flow.id === "warehouse_delivery_builtin") >= 0    ? flows.findIndex((flow) => flow.id === "warehouse_delivery_builtin")    : flows.findIndex((flow) => flow.name === scriptName);  const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};  let existingVariables = {};  try {    existingVariables = parseJsonText(existingFlow.variables || "{}", {});  } catch {    existingVariables = {};  }  const defaultVariables = {    order_detail_id: "",    send_num: 1,    porder_logistics_id: "14",    client_warehouse_list: "/client/wms.stockAutoList",    warehouse_keywords: "",    warehouse_search_tag: "",    children_id: "",    for_sn_set: "",    tag_set: "",    sort_type: "",    hasLabel: "",    create_type: "send",    client_remark: "",    porder_suffix: "300001",    run_backend_delivery_flow: true,    backend_account: "Y001",    backend_password: "raku@123456``",    backend_system: "1",    backend_code: "wnm666",    box_count: "1",    box_length: "58",    box_width: "51",    box_height: "50",    box_weight: "10",    delivery_quote_logistics_id: "25",    logistics_price_artificial: "775",    account: loginBody.account || "12345678990",    password: loginBody.password || "123456",    client_tool: "1",    receiver_address: {      name: "\u6d4b\u8bd5",      company: "\u6d4b\u8bd5\u516c\u53f8\u540d",      address: "\u4f4f\u6240",      zip: "12345678",      mobile: "1353214567",      tel: "0321-55786",      name_rome: "\u30ed\u30fc\u30de\u5b57(\u6c0f\u540d)",      address_rome: "\u30ed\u30fc\u30de\u5b57(\u4f4f\u6240)",      corporate_name: "1234567891234",      account: "1234567889789",      standard_code: "1234567891235",      title: "\u9648\u54e5\u6700\u7231\u5199bug",    },    importer_address: {      name: "13123",      company: "",      address: "123123",      zip: "1232132",      mobile: "123123",      tel: "",      name_rome: "12312313",      address_rome: "123123123",      corporate_name: "",      account: "\u30ea\u30a2\u30eb\u30bf\u30a4\u30e0\u53e3\u5ea7\u5c0f\u6768",      standard_code: "\u6a19\u6e96\u30b3\u30fc\u30c9\u5c0f\u6768",      title: "\u6c0f\u540d",    },  };  const mergedVariables = { ...defaultVariables, ...existingVariables };  if (!mergedVariables.receiver_address || typeof mergedVariables.receiver_address !== "object") {    mergedVariables.receiver_address = defaultVariables.receiver_address;  }  if (!mergedVariables.importer_address || typeof mergedVariables.importer_address !== "object") {    mergedVariables.importer_address = defaultVariables.importer_address;  }  if (!mergedVariables.send_num) mergedVariables.send_num = defaultVariables.send_num;  if (!mergedVariables.porder_logistics_id) mergedVariables.porder_logistics_id = defaultVariables.porder_logistics_id;  if (mergedVariables.run_backend_delivery_flow === undefined) mergedVariables.run_backend_delivery_flow = true;  if (!mergedVariables.backend_account) mergedVariables.backend_account = defaultVariables.backend_account;  if (!mergedVariables.backend_password) mergedVariables.backend_password = defaultVariables.backend_password;  if (!mergedVariables.box_count) mergedVariables.box_count = defaultVariables.box_count;  if (!mergedVariables.box_length) mergedVariables.box_length = defaultVariables.box_length;  if (!mergedVariables.box_width) mergedVariables.box_width = defaultVariables.box_width;  if (!mergedVariables.box_height) mergedVariables.box_height = defaultVariables.box_height;  if (!mergedVariables.box_weight) mergedVariables.box_weight = defaultVariables.box_weight;  if (!mergedVariables.delivery_quote_logistics_id) mergedVariables.delivery_quote_logistics_id = defaultVariables.delivery_quote_logistics_id;  if (!mergedVariables.logistics_price_artificial) mergedVariables.logistics_price_artificial = defaultVariables.logistics_price_artificial;  if (existingVariables.account === "abner" && loginBody.account) mergedVariables.account = loginBody.account;  if (existingVariables.password === "12345" && loginBody.password) mergedVariables.password = loginBody.password;  const nextFlow = {    ...existingFlow,    id: "warehouse_delivery_builtin",    name: existingFlow.name || scriptName,    scriptType: "warehouse_delivery",    projectId: String(projectId),    envId: String(env.id),    caseIds: [],    variables: JSON.stringify(mergedVariables, null, 2),  };  const next = existingIndex >= 0    ? flows        .map((flow, index) => (index === existingIndex ? nextFlow : flow))        .filter((flow, index) => index === existingIndex || (flow.id !== "warehouse_delivery_builtin" && flow.name !== scriptName))    : [...flows, nextFlow];  writeFlows(next);  return next;}function persistFactoryDraft() {  localStorage.setItem("factoryFlowId", state.factory.flowId || "");  localStorage.setItem("factoryProjectId", state.factory.projectId || "");  localStorage.setItem("factoryEnvId", state.factory.envId || "");  localStorage.setItem("factoryCaseIds", JSON.stringify(state.factory.caseIds || []));  localStorage.setItem("factoryVariables", state.factory.variables || "");}function loadFlowToDraft(flow) {  state.factory.flowId = flow?.id || "";  state.factory.projectId = flow?.projectId || state.filters.projectId || "";  state.factory.envId = flow?.envId || "";  state.factory.caseIds = [...(flow?.caseIds || [])];  state.factory.variables = flow?.variables || '{\n  "keyword": "test",\n  "account": "abner"\n}';  persistFactoryDraft();}function readForm(form) {  const data = {};  Array.from(form.elements).forEach((input) => {    if (!input.name || input.disabled || ["submit", "button"].includes(input.type)) return;    if (input.type === "checkbox") {      data[input.name] = input.checked;      return;    }    data[input.name] = input.type === "number" ? (input.value === "" ? null : Number(input.value)) : input.value;  });  return data;}function bindUploadButtons() {
  document.querySelectorAll("[data-upload-btn]").forEach((btn) => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async () => {
      const input = btn.parentElement.querySelector("[data-upload-input]");
      const url = btn.dataset.uploadUrl;
      const fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.accept = "image/*";
      fileInput.onchange = async () => {
        const file = fileInput.files[0];
        if (!file) return;
        btn.disabled = true;
        btn.textContent = "上传中...";
        try {
          const formData = new FormData();
          formData.append("file", file);
          const token = localStorage.getItem("token");
          const resp = await fetch(url, { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: formData });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.detail || "上传失败");
          if (input) input.value = data.url || "";
          showToast("上传成功");
        } catch (error) {
          showToast(error.message);
        } finally {
          btn.disabled = false;
          btn.textContent = "选择文件";
        }
      };
      fileInput.click();
    });
  });
}
function openForm(title, fields, values, onSubmit, submitLabel = "保存") {  const body = fields    .map((field) => renderFormField(field, values?.[field.name] ?? field.default ?? ""))    .join("");  modalEl.innerHTML = `    <form id="modalForm">      <div class="modal-head">        <h3>${escapeHtml(title)}</h3>        <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>      </div>      <div class="modal-body"><div class="form-grid">${body}</div></div>      <div class="modal-foot"><span></span><button class="btn" type="submit">${escapeHtml(submitLabel)}</button></div>    </form>  `;  modalEl.showModal();  bindUploadButtons();  document.querySelector("#closeModal").addEventListener("click", async () => {    modalEl.close();    if (state.view === "dataScripts" && !state.factory.editing) {      await renderDataScripts();    }  });  document.querySelector("#modalForm").addEventListener("submit", async (event) => {    event.preventDefault();    try {      const shouldClose = await onSubmit(readForm(event.currentTarget));      if (shouldClose !== false) modalEl.close();    } catch (error) {      showToast(error.message);    }  });}async function deleteItem(path, afterDelete) {  if (!window.confirm("确认删除这条数据？")) return;  try {    await api(path, { method: "DELETE" });    showToast("已删除");    await afterDelete();  } catch (error) {    showToast(error.message);  }}async function renderCurrentView() {  if (state.view === "dashboard") return renderDashboard();  if (state.view === "projects") return renderProjects();  if (state.view === "envs") return renderEnvs();  if (state.view === "apiCases") return renderApiCases();  if (state.view === "dataScripts") return state.factory.editing ? renderDataScriptEditor() : renderDataScripts();  if (state.view === "caseGeneration") return window.renderCaseGeneration ? window.renderCaseGeneration() : null;  if (state.view === "functionalTests") return renderFunctionalTests();  if (state.view === "uiCases") return renderUiCases();  if (state.view === "records") return renderRecords();  if (state.view === "users") return renderUsers();}async function renderDashboard() {  const projects = await getProjects();  const data = await api(`/api/dashboard${queryString({ project_id: state.filters.projectId })}`);  contentEl().innerHTML = `    <div class="toolbar">      <div class="filters">        <div class="field compact">          <label>项目</label>          <select id="dashboardProject">${optionList(projects, "id", "name", state.filters.projectId)}</select>        </div>      </div>    </div>    <div class="stats">      <div class="stat"><span>项目</span><strong>${data.project_count}</strong></div>      <div class="stat"><span>环境</span><strong>${data.env_count}</strong></div>      <div class="stat"><span>接口用例</span><strong>${data.api_case_count}</strong></div>      <div class="stat"><span>UI用例</span><strong>${data.ui_case_count}</strong></div>      <div class="stat"><span>执行记录</span><strong>${data.record_count}</strong></div>    </div>    <div class="panel-title"><h3>最近执行</h3></div>    ${renderTable(recordColumns(), data.latest_records)}  `;  bindRecordActions(data.latest_records);  document.querySelector("#dashboardProject").addEventListener("change", async (event) => {    state.filters.projectId = event.target.value;    localStorage.setItem("projectId", state.filters.projectId);    await renderDashboard();  });}async function renderProjects() {  const [rows, allEnvs, accounts] = await Promise.all([getProjects(), api("/api/envs"), api(`/api/test-accounts${queryString({ project_id: state.filters.projectId })}`)]);  const projectName = (id) => (rows.find((item) => item.id === id) || {}).name || id;  const envRows = state.filters.projectId ? allEnvs.filter((item) => String(item.project_id) === String(state.filters.projectId)) : allEnvs;  contentEl().innerHTML = `    <div class="toolbar"><p>${isAdmin() ? "项目配置" : "当前账号只读"}</p>${isAdmin() ? `<button class="btn" id="newProject">新增项目</button>` : ""}</div>    ${renderTable(      [        { key: "id", label: "ID" },        { key: "name", label: "项目名称" },        { key: "desc", label: "描述" },        { key: "account_profile_name", label: "默认测试账号", render: (row) => escapeHtml(row.account_profile_name || "-") },        { key: "create_time", label: "创建时间" },        {          key: "actions",          label: "操作",          render: (row) => (isAdmin() ? `<div class="actions"><button class="btn secondary" data-bind-project-account="${row.id}">账号</button><button class="btn secondary" data-edit-project="${row.id}">编辑</button><button class="btn danger" data-del-project="${row.id}">删除</button></div>` : "-"),        },      ],      rows,    )}    <section class="project-env-section">      <div class="toolbar">        <div class="filters">          <div class="field compact"><label>项目环境配置</label><select id="projectEnvFilter">${optionList(rows, "id", "name", state.filters.projectId)}</select></div>        </div>        ${isAdmin() ? `<button class="btn" id="newProjectEnv">新增环境</button>` : ""}      </div>      ${renderTable(        [          { key: "id", label: "ID" },          { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },          { key: "env_name", label: "环境名称" },          { key: "base_url", label: "Base URL" },          { key: "timeout", label: "超时" },          { key: "global_headers", label: "全局请求头", render: (row) => escapeHtml(short(row.global_headers)) },          { key: "global_vars", label: "全局变量", render: (row) => escapeHtml(short(row.global_vars)) },          {            key: "actions",            label: "操作",            render: (row) => (isAdmin() ? `<div class="actions"><button class="btn secondary" data-edit-project-env="${row.id}">编辑</button><button class="btn danger" data-del-project-env="${row.id}">删除</button></div>` : "-"),          },        ],        envRows,      )}    </section>    <section class="project-env-section">      <div class="toolbar">        <div class="filters"><strong>测试账号档案</strong></div>        ${isAdmin() ? `<button class="btn" id="newTestAccount">新增测试账号</button>` : ""}      </div>      ${renderTable(        [          { key: "id", label: "ID" },          { key: "profile_name", label: "账号档案" },          { key: "project_id", label: "范围", render: (row) => escapeHtml(row.project_id ? projectName(row.project_id) : "全局") },          { key: "masked_variables", label: "变量", render: (row) => `<pre class="mini-log">${escapeHtml(accountMaskedText(row))}</pre>` },          { key: "status", label: "状态", render: (row) => badge(row.status) },          {            key: "actions",            label: "操作",            render: (row) => (isAdmin() ? `<div class="actions"><button class="btn secondary" data-edit-test-account="${row.id}">编辑</button><button class="btn danger" data-del-test-account="${row.id}">删除</button></div>` : "-"),          },        ],        accounts,      )}    </section>  `;  document.querySelector("#projectEnvFilter").addEventListener("change", async (event) => {    state.filters.projectId = event.target.value;    localStorage.setItem("projectId", state.filters.projectId);    await renderProjects();  });  if (!isAdmin()) return;  document.querySelector("#newProject").addEventListener("click", () => projectForm());  document.querySelectorAll("[data-edit-project]").forEach((button) => {    const item = rows.find((row) => row.id === Number(button.dataset.editProject));    button.addEventListener("click", () => projectForm(item));  });  document.querySelectorAll("[data-del-project]").forEach((button) => {    button.addEventListener("click", () => deleteItem(`/api/projects/${button.dataset.delProject}`, renderProjects));  });  document.querySelectorAll("[data-bind-project-account]").forEach((button) => {    const item = rows.find((row) => row.id === Number(button.dataset.bindProjectAccount));    button.addEventListener("click", () =>      openAccountBindingForm({        title: `设置项目默认账号：${item?.name || ""}`,        targetType: "project",        targetId: item.id,        currentId: item.account_profile_id,        accounts,        projects: rows,        emptyLabel: "不设置默认账号",        afterSave: renderProjects,      }),    );  });  const envProjectOptions = rows.map((item) => ({ value: item.id, label: item.name }));  document.querySelector("#newProjectEnv").addEventListener("click", () => envForm(null, envProjectOptions, renderProjects, state.filters.projectId || rows[0]?.id || ""));  document.querySelectorAll("[data-edit-project-env]").forEach((button) => {    const item = allEnvs.find((row) => row.id === Number(button.dataset.editProjectEnv));    button.addEventListener("click", () => envForm(item, envProjectOptions, renderProjects));  });  document.querySelectorAll("[data-del-project-env]").forEach((button) => {    button.addEventListener("click", () => deleteItem(`/api/envs/${button.dataset.delProjectEnv}`, renderProjects));  });  document.querySelector("#newTestAccount")?.addEventListener("click", () => openTestAccountForm(null, rows));  document.querySelectorAll("[data-edit-test-account]").forEach((button) => {    const item = accounts.find((row) => row.id === Number(button.dataset.editTestAccount));    button.addEventListener("click", () => openTestAccountForm(item, rows));  });  document.querySelectorAll("[data-del-test-account]").forEach((button) => {    button.addEventListener("click", () => deleteItem(`/api/test-accounts/${button.dataset.delTestAccount}`, renderProjects));  });}function projectForm(item) {  openForm(    item ? "编辑项目" : "新增项目",    [      { name: "name", label: "项目名称", required: true },      { name: "desc", label: "描述", type: "textarea" },    ],    item,    async (data) => {      await api(item ? `/api/projects/${item.id}` : "/api/projects", { method: item ? "PUT" : "POST", body: data });      invalidateProjectsCache();      showToast("已保存");      await renderProjects();    },  );}async function renderEnvs() {  const projects = await getProjects();  const rows = await api(`/api/envs${queryString({ project_id: state.filters.projectId })}`);  const projectName = (id) => (projects.find((item) => item.id === id) || {}).name || id;  contentEl().innerHTML = `    <div class="toolbar">      <div class="filters">        <div class="field compact"><label>项目</label><select id="envProjectFilter">${optionList(projects, "id", "name", state.filters.projectId)}</select></div>      </div>      ${isAdmin() ? `<button class="btn" id="newEnv">新增环境</button>` : ""}    </div>    ${renderTable(      [        { key: "id", label: "ID" },        { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },        { key: "env_name", label: "环境名称" },        { key: "base_url", label: "Base URL" },        { key: "timeout", label: "超时" },        { key: "global_headers", label: "全局请求头", render: (row) => escapeHtml(short(row.global_headers)) },        { key: "global_vars", label: "全局变量", render: (row) => escapeHtml(short(row.global_vars)) },        {          key: "actions",          label: "操作",          render: (row) => (isAdmin() ? `<div class="actions"><button class="btn secondary" data-edit-env="${row.id}">编辑</button><button class="btn danger" data-del-env="${row.id}">删除</button></div>` : "-"),        },      ],      rows,    )}  `;  document.querySelector("#envProjectFilter").addEventListener("change", async (event) => {    state.filters.projectId = event.target.value;    localStorage.setItem("projectId", state.filters.projectId);    await renderEnvs();  });  if (!isAdmin()) return;  const options = projects.map((item) => ({ value: item.id, label: item.name }));  document.querySelector("#newEnv").addEventListener("click", () => envForm(null, options));  document.querySelectorAll("[data-edit-env]").forEach((button) => {    const item = rows.find((row) => row.id === Number(button.dataset.editEnv));    button.addEventListener("click", () => envForm(item, options));  });  document.querySelectorAll("[data-del-env]").forEach((button) => {    button.addEventListener("click", () => deleteItem(`/api/envs/${button.dataset.delEnv}`, renderEnvs));  });}function envForm(item, projectOptions, afterSave = renderEnvs, defaultProjectId = "") {  const values = item || { project_id: defaultProjectId };  const isUpdate = item && item.id;  openForm(    isUpdate ? "编辑环境" : "新增环境",    [      { name: "project_id", label: "项目", type: "select", options: projectOptions, required: true },      { name: "env_name", label: "环境名称", required: true },      { name: "base_url", label: "Base URL", required: true },      { name: "global_headers", label: "全局请求头 JSON", type: "textarea", default: "{}" },      { name: "global_vars", label: "全局变量 JSON", type: "textarea", default: "{}" },      { name: "timeout", label: "超时秒数", type: "number", default: 30 },    ],    values,    async (data) => {      await api(isUpdate ? `/api/envs/${item.id}` : "/api/envs", { method: isUpdate ? "PUT" : "POST", body: data });      showToast("已保存");      await afterSave();    },  );}async function renderApiCases() {  const [projects, allEnvs] = await Promise.all([getProjects(), api("/api/envs")]);  const envs = state.filters.projectId ? allEnvs.filter((item) => String(item.project_id) === String(state.filters.projectId)) : allEnvs;  if (state.filters.envId && !envs.some((item) => String(item.id) === String(state.filters.envId))) state.filters.envId = "";  const rows = await api(`/api/api-cases${queryString({ project_id: state.filters.projectId, env_id: state.filters.envId })}`);  const projectName = (id) => (projects.find((item) => item.id === id) || {}).name || id;  const envName = (id) => (allEnvs.find((item) => item.id === id) || {}).env_name || id;  const selectedCount = [...state.selectedApiIds].filter((id) => rows.some((row) => row.id === id)).length;  contentEl().innerHTML = `    <div class="toolbar">      <div class="filters">        <div class="field compact"><label>项目</label><select id="apiProjectFilter">${optionList(projects, "id", "name", state.filters.projectId)}</select></div>        <div class="field compact"><label>环境</label><select id="apiEnvFilter">${optionList(envs, "id", "env_name", state.filters.envId)}</select></div>      </div>      <div class="actions">        <button class="btn secondary" id="batchApiRun" ${selectedCount ? "" : "disabled"}>批量执行 ${selectedCount || ""}</button>        ${isAdmin() ? `<button class="btn" id="newApiCase">新增接口用例</button>` : ""}      </div>    </div>    ${renderTable(      [        {          key: "select",          label: "",          render: (row) => `<input type="checkbox" data-api-select="${row.id}" ${state.selectedApiIds.has(row.id) ? "checked" : ""} />`,        },        { key: "id", label: "ID" },        { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },        { key: "env_id", label: "环境", render: (row) => escapeHtml(envName(row.env_id)) },        { key: "case_name", label: "用例名称" },        { key: "method", label: "方法", render: (row) => badge(row.method) },        { key: "url", label: "URL" },        { key: "status", label: "状态", render: (row) => badge(row.status) },        {          key: "actions",          label: "操作",          render: (row) => `            <div class="actions">              <button class="btn" data-run-api="${row.id}">执行</button>              ${isAdmin() ? `<button class="btn secondary" data-copy-api="${row.id}">复制</button><button class="btn secondary" data-edit-api="${row.id}">编辑</button><button class="btn danger" data-del-api="${row.id}">删除</button>` : ""}            </div>          `,        },      ],      rows,    )}  `;  document.querySelector("#apiProjectFilter").addEventListener("change", async (event) => {    state.filters.projectId = event.target.value;    state.filters.envId = "";    localStorage.setItem("projectId", state.filters.projectId);    state.selectedApiIds.clear();    await renderApiCases();  });  document.querySelector("#apiEnvFilter").addEventListener("change", async (event) => {    state.filters.envId = event.target.value;    state.selectedApiIds.clear();    await renderApiCases();  });  document.querySelector("#batchApiRun").addEventListener("click", () => openBatchApiRun());  document.querySelectorAll("[data-api-select]").forEach((checkbox) => {    checkbox.addEventListener("change", async (event) => {      const id = Number(event.target.dataset.apiSelect);      if (event.target.checked) state.selectedApiIds.add(id);      else state.selectedApiIds.delete(id);      await renderApiCases();    });  });  document.querySelectorAll("[data-run-api]").forEach((button) => {    button.addEventListener("click", () => runApiCase(Number(button.dataset.runApi)));  });  if (!isAdmin()) return;  const projectOptions = projects.map((item) => ({ value: item.id, label: item.name }));  const envOptions = allEnvs.map((item) => ({ value: item.id, label: `${item.env_name} (${projectName(item.project_id)})` }));  document.querySelector("#newApiCase").addEventListener("click", () => apiCaseForm(null, projectOptions, envOptions));  document.querySelectorAll("[data-copy-api]").forEach((button) => {    const item = rows.find((row) => row.id === Number(button.dataset.copyApi));    button.addEventListener("click", () => apiCaseForm({ ...item, id: undefined, case_name: `${item.case_name}_copy` }, projectOptions, envOptions, true));  });  document.querySelectorAll("[data-edit-api]").forEach((button) => {    const item = rows.find((row) => row.id === Number(button.dataset.editApi));    button.addEventListener("click", () => apiCaseForm(item, projectOptions, envOptions));  });  document.querySelectorAll("[data-del-api]").forEach((button) => {    button.addEventListener("click", () => deleteItem(`/api/api-cases/${button.dataset.delApi}`, renderApiCases));  });}function apiCaseForm(item, projectOptions, envOptions, forceCreate = false) {  openForm(    item && !forceCreate ? "编辑接口用例" : "新增接口用例",    [      { name: "project_id", label: "项目", type: "select", options: projectOptions, required: true },      { name: "env_id", label: "环境", type: "select", options: envOptions, required: true },      { name: "case_name", label: "用例名称", required: true },      { name: "method", label: "请求方法", type: "select", options: ["GET", "POST", "PUT", "PATCH", "DELETE"].map((item) => ({ value: item, label: item })), required: true },      { name: "url", label: "URL", required: true },      { name: "headers", label: "请求头 JSON", type: "textarea", default: "{}" },      { name: "params", label: "参数 JSON", type: "textarea", default: "{}" },      { name: "body", label: "请求体", type: "textarea" },      { name: "assert_rule", label: "断言/提取 JSON", type: "textarea", default: '{"status_code":200,"extract":{"id":"json.data.id"}}' },      {        name: "status",        label: "状态",        type: "select",        options: [          { value: "active", label: "启用" },          { value: "inactive", label: "停用" },        ],        default: "active",      },    ],    item,    async (data) => {      const isUpdate = item && item.id && !forceCreate;      await api(isUpdate ? `/api/api-cases/${item.id}` : "/api/api-cases", { method: isUpdate ? "PUT" : "POST", body: data });      showToast("已保存");      await renderApiCases();    },  );}async function runApiCase(caseId) {  try {    showToast("正在执行，请稍候");    const body = {};    if (state.filters.envId) body.env_id = Number(state.filters.envId);    const record = await api(`/api/api-cases/${caseId}/execute`, { method: "POST", body });    showToast(`执行完成：${record.result === "passed" ? "成功" : "失败"}`);    state.view = "records";    await renderShell();  } catch (error) {    showToast(error.message);  }}function openBatchApiRun() {  const caseIds = [...state.selectedApiIds];  if (!caseIds.length) {    showToast("请选择接口用例");    return;  }  openForm(    `批量执行 ${caseIds.length} 条接口用例`,    [      {        name: "variables",        label: "运行时变量 JSON",        type: "textarea",        rows: 8,        default: '{\n  "username": "test_{{$random_int}}",\n  "phone": "{{$random_phone}}"\n}',      },    ],    {},    async (data) => {      const payload = {        case_ids: caseIds,        variables: parseJsonText(data.variables, {}),      };      if (state.filters.envId) payload.env_id = Number(state.filters.envId);      const result = await api("/api/api-cases/batch-execute", { method: "POST", body: payload });      state.selectedApiIds.clear();      showToast(`批量执行完成：${result.records.length} 条`);      state.view = "records";      await renderShell();    },    "执行",  );}async function renderDataScripts() {
  const [projects, allEnvs, allCases, recorderFlows] = await Promise.all([getProjects(), api("/api/envs"), api("/api/api-cases"), flowRecorderList()]);
  const selectedProjectId = activeDataScriptProjectId(projects);
  const latestOrder = selectedProjectId ? await api(`/api/data-scripts/latest-order-sn${queryString({ project_id: selectedProjectId })}`) : {};
  const storedFlows = normalizeDataScriptFlows(readFlows(), projects, allEnvs);
  const baseFlows = storedFlows.filter((flow) => !isDeletedBuiltinFlow(flow));
  if (baseFlows.length !== storedFlows.length) {
    writeFlows(baseFlows);
  }
  let flows = ensureOemBalancePayScript(
    ensureOemBulkOrderFlowScript(
    ensureOemSampleFullFlowScript(
    ensureOemSampleAdminFlowScript(
    ensureOemFullInquiryFlowScript(
    ensureOemSampleOrderScript(
    ensureOemNewInquiryScript(
    ensureBalanceRechargeScript(
    ensureMaterialGenerationScript(
    ensureWarehouseDeliveryScript(
    ensurePurchaseToShelfChainScript(
      ensurePurchaseToShelfScript(
        ensurePaymentScripts(
          ensureOrderQuoteScript(ensureShoppingCartScript(baseFlows, projects, allEnvs, allCases), projects, allEnvs, allCases),
          projects,
          allEnvs,
          allCases,
        ),
        projects,
        allEnvs,
        allCases,
      ),
      projects,
      allEnvs,
      allCases,
    ),
    projects,
    allEnvs,
    allCases,
  ),
    projects,
    allEnvs,
    allCases,
  ),
    projects,
    allEnvs,
    allCases,
  ),
    projects,
    allEnvs,
    allCases,
  ),
    projects,
    allEnvs,
    allCases,
  ),
    projects,
    allEnvs,
  ),
    projects,
    allEnvs,
  ),
    projects,
    allEnvs,
    allCases,
  ),
    projects,
    allEnvs,
    allCases,
  ),
    projects,
    allEnvs,
  );
  if (latestOrder?.order_sn) {
    flows = flows.map((flow) =>
      ["order_quote", "purchase_to_shelf", "purchase_to_shelf_chain"].includes(flow.scriptType)
        ? { ...flow, lastOrderSn: latestOrder.order_sn, lastRecordId: latestOrder.record_id || flow.lastRecordId || "" }
        : flow,
    );
    writeFlows(flows);
  }
  const projectName = (id) => (projects.find((item) => String(item.id) === String(id)) || {}).name || "-";
  const envName = (id) => (allEnvs.find((item) => String(item.id) === String(id)) || {}).env_name || "-";
  const caseName = (id) => (allCases.find((item) => String(item.id) === String(id)) || {}).case_name || `#${id}`;
  const flowSteps = (row) => {
    if (row.isFlowRecorder) return `录制流程 · ${row.step_count || 0} 步`;
    if (row.scriptType === "shopping_cart") return (row.caseIds || []).map(caseName).join(" -> ") || "登录 -> 搜索 -> 详情 -> 加购";
    if (row.scriptType === "order_quote") return "前台提单 -> 后台登录 -> 订单翻译 -> 采购调查 -> 业务报价";
    if (row.scriptType === "balance_payment") return "订单列表(等待付款) -> 余额支付";
    if (row.scriptType === "bank_payment") return "订单列表(等待付款) -> 银行转账 -> 财务确认入金";
    if (row.scriptType === "purchase_to_shelf") {
      const variables = parseJsonText(row.variables || "{}", {});
      return variables.link_quote_balance_before_shelf !== false && variables.auto_quote_and_pay !== false
        ? "订单报价 -> 余额支付 -> 待拍下商品 -> 交易号付款 -> 开始核查 -> 上架入库"
        : "待拍下商品 -> 标记待改价 -> 待财务付款 -> 交易号付款 -> 开始核查 -> 上架入库";
    }
    if (row.scriptType === "warehouse_delivery") return "仓库商品列表 -> 选择1番 -> 提出配送单 -> 后台配货 -> 装箱 -> 提交业务 -> 配送单报价";
    if (row.scriptType === "full_flow") return "购物车 -> 订单报价 -> 订单付款 -> 待拍下上架 -> 配送单 -> 配送单付款";
    if (row.scriptType === "direct_box_to_shelf") return "订单报价 -> 待拍下上架 -> 直接装箱 -> 上架完成";
    if (row.scriptType === "material_generation") return "查询现有辅料 -> 循环创建不重复辅料";
    if (row.scriptType === "balance_recharge") return "前台提交充值 -> 后台登录 -> 财务确认入金 -> 余额到账";
    return (row.caseIds || []).map(caseName).join(" -> ") || "-";
  };
  const visibleFlows = flows.filter((flow) => dataScriptProjectMatches(flow, selectedProjectId)).sort((a, b) => (a.order ?? Infinity) - (b.order ?? Infinity));
  const deletedRows = deletedDataScriptRows(projects, allEnvs).filter((row) => dataScriptProjectMatches(row, selectedProjectId));
  const hiddenRows = hiddenDataScriptRows(projects, allEnvs).filter((row) => dataScriptProjectMatches(row, selectedProjectId));
  const isDeletedTab = state.dataScriptTab === "deleted";
  const isHiddenTab = state.dataScriptTab === "hidden";
  const tabButton = (key, label, count) => `<button class="btn ${state.dataScriptTab === key ? "" : "secondary"}" data-data-script-tab="${key}" type="button">${label}${count ? ` (${count})` : ""}</button>`;
  const projectOptions = optionList(projects, "id", "name", selectedProjectId, "请选择项目");
  // 录制流程作为脚本卡片插入列表（不受项目过滤影响，始终展示）
  const recorderRows = (recorderFlows || []).map(flowRecorderRow);
  const tableFlows = [...visibleFlows, ...recorderRows];
  const activeTable = renderTable(
    [
      { key: "_drag", label: "", render: (row) => row.isFlowRecorder ? "" : `<span class="drag-handle" draggable="true" data-drag-handle="${escapeHtml(row.id)}" title="拖动排序">≡</span>` },
      { key: "name", label: "脚本名称" },
      { key: "projectId", label: "项目", render: (row) => escapeHtml(row.isFlowRecorder ? "通用" : projectName(row.projectId)) },
      { key: "envId", label: "环境", render: (row) => escapeHtml(envName(row.envId)) },
      { key: "caseIds", label: "步骤", render: (row) => escapeHtml(flowSteps(row)) },
      {
        key: "actions",
        label: "操作",
        render: (row) => row.isFlowRecorder ? `
          <div class="actions">
            <button class="btn" data-flow-recorder-run="${escapeHtml(row.flowRecorderId)}">执行</button>
            <button class="btn secondary" data-flow-recorder-view="${escapeHtml(row.flowRecorderId)}">查看</button>
            <button class="btn danger" data-flow-recorder-delete="${escapeHtml(row.flowRecorderId)}">删除</button>
          </div>
        ` : `
          <div class="actions">
            <button class="btn" data-run-script="${row.id}">执行</button>
            <button class="btn secondary" data-edit-script="${row.id}">编辑</button>
            ${["order_quote", "balance_payment", "bank_payment", "purchase_to_shelf", "direct_box_to_shelf"].includes(row.scriptType) || row.lastOrderSn ? `<button class="btn secondary" data-copy-order-sn="${row.id}" ${row.lastOrderSn ? "" : "disabled"}>复制订单号</button>` : ""}
            ${["purchase_to_shelf", "direct_box_to_shelf"].includes(row.scriptType) ? `<button class="btn secondary" data-copy-purchase-no="${row.id}" ${row.lastPurchaseNo ? "" : "disabled"}>复制交易号</button>` : ""}
            ${row.scriptType === "warehouse_delivery" ? `<button class="btn secondary" data-copy-porder-sn="${row.id}" ${row.lastPorderSn ? "" : "disabled"}>复制配送单号</button>` : ""}
            <button class="btn secondary" data-copy-script="${row.id}">复制</button>
            <button class="btn secondary" data-hide-script="${row.id}">隐藏</button>
            <button class="btn danger" data-delete-script="${row.id}">删除</button>
          </div>
        `,
      },
    ],
    tableFlows,
    true,
    (row) => `data-row-id="${escapeHtml(row.id)}"`,
  );
  const deletedTable = renderTable(
    [
      { key: "name", label: "脚本名称" },
      { key: "projectId", label: "项目", render: (row) => escapeHtml(projectName(row.projectId)) },
      { key: "envId", label: "环境", render: (row) => escapeHtml(envName(row.envId)) },
      { key: "isBuiltin", label: "类型", render: (row) => badge(row.isBuiltin ? "内置" : "自定义") },
      { key: "deletedAt", label: "删除时间", render: (row) => escapeHtml(row.deletedAt ? new Date(row.deletedAt).toLocaleString() : "旧删除记录") },
      { key: "actions", label: "操作", render: (row) => `<button class="btn" data-restore-script="${escapeHtml(row.id)}">恢复</button>` },
    ],
    deletedRows,
  );
  const hiddenTable = renderTable(
    [
      { key: "name", label: "脚本名称" },
      { key: "projectId", label: "项目", render: (row) => escapeHtml(projectName(row.projectId)) },
      { key: "envId", label: "环境", render: (row) => escapeHtml(envName(row.envId)) },
      { key: "isBuiltin", label: "类型", render: (row) => badge(row.isBuiltin ? "内置" : "自定义") },
      { key: "hiddenAt", label: "隐藏时间", render: (row) => escapeHtml(row.hiddenAt ? new Date(row.hiddenAt).toLocaleString() : "-") },
      { key: "actions", label: "操作", render: (row) => `<button class="btn" data-restore-hidden-script="${escapeHtml(row.id)}">恢复显示</button>` },
    ],
    hiddenRows,
  );
  contentEl().innerHTML = `
    <div class="toolbar">
      <div class="filters">
        <div class="field compact"><label>项目</label><select id="dataScriptProjectFilter">${projectOptions}</select></div>
        <div class="actions">${tabButton("active", "脚本列表", visibleFlows.length)}${tabButton("hidden", "已隐藏", hiddenRows.length)}${tabButton("deleted", "已删除", deletedRows.length)}</div>
        ${!isDeletedTab && !isHiddenTab ? `<div class="field compact"><label>客户ID</label><textarea id="dataScriptCustomerIds" rows="2" placeholder="多个客户ID可用逗号或换行分隔">${escapeHtml(storedDataScriptCustomerIds())}</textarea></div>` : ""}
      </div>
      <div class="actions">${!isDeletedTab && !isHiddenTab ? `<button class="btn" id="newDataScript">新建脚本</button><button class="btn secondary" id="recordNewFlow">录制新流程</button><button class="btn secondary" id="recordLiveFlow">实时录制</button>` : ""}</div>
    </div>
    ${isHiddenTab ? hiddenTable : isDeletedTab ? deletedTable : activeTable}
  `;
  document.querySelector("#dataScriptProjectFilter")?.addEventListener("change", async (event) => {
    state.filters.projectId = event.target.value;
    localStorage.setItem("projectId", state.filters.projectId);
    await renderDataScripts();
  });
  document.querySelectorAll("[data-data-script-tab]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.dataScriptTab = button.dataset.dataScriptTab;
      localStorage.setItem("dataScriptTab", state.dataScriptTab);
      await renderDataScripts();
    });
  });
  document.querySelector("#dataScriptCustomerIds")?.addEventListener("input", (event) => {
    localStorage.setItem(DATA_SCRIPT_CUSTOMER_IDS_KEY, event.target.value);
  });
  document.querySelector("#newDataScript")?.addEventListener("click", async () => {
    loadFlowToDraft(null);
    state.factory.projectId = selectedProjectId || "";
    const defaultEnv = allEnvs.find((item) => String(item.project_id) === String(selectedProjectId));
    state.factory.envId = defaultEnv?.id ? String(defaultEnv.id) : "";
    persistFactoryDraft();
    state.factory.editing = true;
    await renderShell();
  });
  // 录制新流程：触发隐藏文件选择
  document.querySelector("#recordNewFlow")?.addEventListener("click", () => flowRecorderPickFile());
  // 实时录制：打开起始 URL 对话框
  document.querySelector("#recordLiveFlow")?.addEventListener("click", () => liveRecorderOpenStartDialog());
  document.querySelectorAll("[data-restore-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      const entry = deletedRows.find((item) => item.id === button.dataset.restoreScript);
      restoreDeletedFlow(entry);
      state.dataScriptTab = "active";
      localStorage.setItem("dataScriptTab", state.dataScriptTab);
      showToast("脚本已恢复");
      await renderDataScripts();
    });
  });
  document.querySelectorAll("[data-restore-hidden-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      const entry = hiddenRows.find((item) => item.id === button.dataset.restoreHiddenScript);
      restoreHiddenFlow(entry);
      state.dataScriptTab = "active";
      localStorage.setItem("dataScriptTab", state.dataScriptTab);
      showToast("脚本已恢复显示");
      await renderDataScripts();
    });
  });
  if (isDeletedTab || isHiddenTab) return;
  // 拖拽排序：仅 active tab
  const dragSourceId = { current: null };
  document.querySelectorAll("[data-drag-handle]").forEach((handle) => {
    handle.addEventListener("dragstart", (event) => {
      const tr = handle.closest("tr");
      if (!tr) return;
      dragSourceId.current = tr.dataset.rowId;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", tr.dataset.rowId);
      if (event.dataTransfer.setDragImage && tr) event.dataTransfer.setDragImage(tr, 0, 0);
      tr.classList.add("dragging");
    });
  });
  const activeTbody = document.querySelector("#content tbody");
  if (activeTbody) {
    activeTbody.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      const targetTr = event.target.closest("tr");
      if (!targetTr || !targetTr.dataset.rowId) return;
      if (targetTr.dataset.rowId === dragSourceId.current) return;
      activeTbody.querySelectorAll("tr.drag-over").forEach((tr) => tr.classList.remove("drag-over"));
      targetTr.classList.add("drag-over");
    });
    activeTbody.addEventListener("drop", async (event) => {
      event.preventDefault();
      const targetTr = event.target.closest("tr");
      if (!targetTr || !targetTr.dataset.rowId) return;
      const sourceId = dragSourceId.current;
      const targetId = targetTr.dataset.rowId;
      if (!sourceId || sourceId === targetId) return;
      const flows = readFlows();
      const visibleFlows = flows
        .filter((flow) => dataScriptProjectMatches(flow, state.filters.projectId || ""))
        .sort((a, b) => (a.order ?? Infinity) - (b.order ?? Infinity));
      const sourceIdx = visibleFlows.findIndex((flow) => flow.id === sourceId);
      const targetIdx = visibleFlows.findIndex((flow) => flow.id === targetId);
      if (sourceIdx < 0 || targetIdx < 0) return;
      const [moved] = visibleFlows.splice(sourceIdx, 1);
      visibleFlows.splice(targetIdx, 0, moved);
      visibleFlows.forEach((flow, index) => { flow.order = index; });
      const visibleById = new Map(visibleFlows.map((flow) => [flow.id, flow]));
      const nextFlows = flows.map((flow) => visibleById.get(flow.id) || flow);
      writeFlows(nextFlows);
      showToast("排序已更新");
      await renderDataScripts();
    });
    activeTbody.addEventListener("dragend", () => {
      dragSourceId.current = null;
      activeTbody.querySelectorAll("tr.dragging, tr.drag-over").forEach((tr) => tr.classList.remove("dragging", "drag-over"));
    });
  }
  document.querySelectorAll("[data-edit-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      const flow = readFlows().find((item) => item.id === button.dataset.editScript);
      loadFlowToDraft(flow);
      state.factory.editing = true;
      await renderShell();
    });
  });
  document.querySelectorAll("[data-run-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      const flow = readFlows().find((item) => item.id === button.dataset.runScript);
      openRunScriptForm(flow);
    });
  });
  document.querySelectorAll("[data-copy-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      const flows = readFlows();
      const flow = flows.find((item) => item.id === button.dataset.copyScript);
      if (!flow) {
        showToast("脚本不存在，刷新后再试");
        return;
      }
      const copied = { ...flow, id: newFlowId(), name: `${flow.name || "数据脚本"}_副本`, caseIds: [...(flow.caseIds || [])], lastOrderSn: "", lastPurchaseNo: "", lastPorderSn: "", lastRecordId: "" };
      writeFlows([...flows, copied]);
      showToast("脚本已复制");
      await renderDataScripts();
    });
  });
  document.querySelectorAll("[data-copy-order-sn]").forEach((button) => {
    button.addEventListener("click", async () => {
      const flow = readFlows().find((item) => item.id === button.dataset.copyOrderSn);
      await copyText(flow?.lastOrderSn, "订单号");
    });
  });
  document.querySelectorAll("[data-copy-purchase-no]").forEach((button) => {
    button.addEventListener("click", async () => {
      const flow = readFlows().find((item) => item.id === button.dataset.copyPurchaseNo);
      await copyText(flow?.lastPurchaseNo, "交易号");
    });
  });
  document.querySelectorAll("[data-copy-porder-sn]").forEach((button) => {
    button.addEventListener("click", async () => {
      const flow = readFlows().find((item) => item.id === button.dataset.copyPorderSn);
      await copyText(flow?.lastPorderSn, "配送单号");
    });
  });
  document.querySelectorAll("[data-delete-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("确认删除这个数据脚本？删除后可在已删除中恢复。")) return;
      const deleteId = button.dataset.deleteScript;
      const flows = readFlows();
      const targetFlow = flows.find((flow) => flow.id === deleteId);
      if (!targetFlow) {
        showToast("脚本不存在，刷新后再试");
        return;
      }
      const builtinDefinition = builtinDefinitionForFlow(targetFlow);
      saveDeletedFlow(targetFlow, builtinDefinition);
      if (builtinDefinition) markBuiltinDeleted(builtinDefinition.id);
      writeFlows(
        flows.filter((flow) => {
          if (flow.id === deleteId) return false;
          if (!builtinDefinition) return true;
          return flow.id !== builtinDefinition.id && flow.name !== builtinDefinition.name;
        }),
      );
      showToast("已删除，可在已删除中恢复");
      await renderDataScripts();
    });
  });
  document.querySelectorAll("[data-hide-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      const hideId = button.dataset.hideScript;
      const flows = readFlows();
      const targetFlow = flows.find((flow) => flow.id === hideId);
      if (!targetFlow) {
        showToast("脚本不存在，刷新后再试");
        return;
      }
      const builtinDefinition = builtinDefinitionForFlow(targetFlow);
      saveHiddenFlow(targetFlow, builtinDefinition);
      if (builtinDefinition) markBuiltinHidden(builtinDefinition.id);
      writeFlows(
        flows.filter((flow) => {
          if (flow.id === hideId) return false;
          if (!builtinDefinition) return true;
          return flow.id !== builtinDefinition.id && flow.name !== builtinDefinition.name;
        }),
      );
      showToast("已隐藏，可在已隐藏中恢复显示");
      await renderDataScripts();
    });
  });
  // 录制流程：执行 / 查看 / 删除
  document.querySelectorAll("[data-flow-recorder-run]").forEach((button) => {
    button.addEventListener("click", () => {
      flowRecorderOpenExecDialog({ flowRecorderId: button.dataset.flowRecorderRun });
    });
  });
  document.querySelectorAll("[data-flow-recorder-view]").forEach((button) => {
    button.addEventListener("click", () => flowRecorderOpenDetailDialog(button.dataset.flowRecorderView));
  });
  document.querySelectorAll("[data-flow-recorder-delete]").forEach((button) => {
    button.addEventListener("click", () => flowRecorderDelete(button.dataset.flowRecorderDelete));
  });
}async function renderDataScriptEditor() {  const [projects, allEnvs, allCases] = await Promise.all([getProjects(), api("/api/envs"), api("/api/api-cases")]);  const flows = readFlows();  const selectedProjectId = state.factory.projectId;  const envs = selectedProjectId ? allEnvs.filter((item) => String(item.project_id) === String(selectedProjectId)) : allEnvs;  if (state.factory.envId && !envs.some((item) => String(item.id) === String(state.factory.envId))) {    state.factory.envId = "";    persistFactoryDraft();  }  const availableCases = allCases.filter((item) => {    const projectOk = !state.factory.projectId || String(item.project_id) === String(state.factory.projectId);    const envOk = !state.factory.envId || String(item.env_id) === String(state.factory.envId);    return projectOk && envOk;  });  const projectName = (id) => (projects.find((item) => item.id === id) || {}).name || id;  const envName = (id) => (allEnvs.find((item) => item.id === id) || {}).env_name || id;  const selectedCases = state.factory.caseIds    .map((id) => allCases.find((item) => item.id === id))    .filter(Boolean);  const selectedFlow = flows.find((flow) => flow.id === state.factory.flowId);  const paramFields = scriptParamFields(selectedFlow?.scriptType || "", selectedFlow);  const draftVariables = sanitizeScriptVariables(selectedFlow?.scriptType || "", safeVariables(state.factory.variables), selectedFlow);  const paramValues = paramFormValues(paramFields, draftVariables);  contentEl().innerHTML = `    <div class="toolbar">      <div class="filters">        <div class="field compact"><label>项目</label><select id="factoryProject">${optionList(projects, "id", "name", state.factory.projectId)}</select></div>        <div class="field compact"><label>环境</label><select id="factoryEnv">${optionList(envs, "id", "env_name", state.factory.envId)}</select></div>      </div>      <div class="actions">        <button class="btn secondary" id="backScripts">返回列表</button>        <button class="btn" id="saveFlow">保存脚本</button>      </div>    </div>    <div class="factory-grid">      <section class="panel">        <div class="panel-title"><h3>接口用例</h3></div>        ${renderTable(          [            { key: "id", label: "ID" },            { key: "case_name", label: "用例名称" },            { key: "method", label: "方法", render: (row) => badge(row.method) },            { key: "env_id", label: "环境", render: (row) => escapeHtml(envName(row.env_id)) },            { key: "actions", label: "操作", render: (row) => `<button class="btn secondary" data-add-flow-case="${row.id}">加入</button>` },          ],          availableCases,          false,        )}      </section>      <section class="panel">        <div class="panel-title"><h3>脚本步骤</h3></div>        ${renderTable(          [            { key: "index", label: "顺序", render: (row) => row.index + 1 },            { key: "case_name", label: "用例名称" },            { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },            { key: "env_id", label: "环境", render: (row) => escapeHtml(state.factory.envId ? envName(Number(state.factory.envId)) : envName(row.env_id)) },            {              key: "actions",              label: "操作",              render: (row) => `                <div class="actions">                  <button class="btn secondary" data-move-flow-case="${row.index}:up">上移</button>                  <button class="btn secondary" data-move-flow-case="${row.index}:down">下移</button>                  <button class="btn danger" data-remove-flow-case="${row.index}">移除</button>                </div>              `,            },          ],          selectedCases.map((item, index) => ({ ...item, index })),          false,        )}      </section>    </div>    ${      paramFields.length        ? `          <section class="panel factory-vars">            <div class="panel-title"><h3>常用参数</h3></div>            <div class="panel-body">              <form id="factoryParamForm" class="param-grid">                ${paramFields.map((field) => renderFormField(field, paramValues[field.name])).join("")}              </form>            </div>          </section>        `        : ""    }    <details class="panel factory-vars advanced-vars">      <summary>高级参数</summary>      <div class="panel-body">        <textarea id="factoryVariables" spellcheck="false">${escapeHtml(state.factory.variables)}</textarea>      </div>    </details>  `;  document.querySelector("#backScripts").addEventListener("click", async () => {    state.factory.editing = false;    await renderShell();  });  document.querySelector("#factoryProject").addEventListener("change", async (event) => {    state.factory.projectId = event.target.value;    state.factory.envId = "";    persistFactoryDraft();    await renderDataScriptEditor();  });  document.querySelector("#factoryEnv").addEventListener("change", async (event) => {    state.factory.envId = event.target.value;    persistFactoryDraft();    await renderDataScriptEditor();  });  document.querySelector("#factoryVariables").addEventListener("input", (event) => {    state.factory.variables = event.target.value;    persistFactoryDraft();  });  const paramForm = document.querySelector("#factoryParamForm");  if (paramForm) {    const syncParamForm = () => {      const textarea = document.querySelector("#factoryVariables");      let variables = {};      try {        variables = parseJsonText(textarea.value || "{}", {});      } catch {        showToast("运行时变量不是合法 JSON，先修正 JSON 后再改常用参数");        return;      }      const merged = withCustomerLoginInputs(sanitizeScriptVariables(selectedFlow?.scriptType || "", mergeParamValues(variables, paramFields, readForm(paramForm)), selectedFlow));      state.factory.variables = JSON.stringify(merged, null, 2);      textarea.value = state.factory.variables;      persistFactoryDraft();    };    paramForm.querySelectorAll("input, select, textarea").forEach((input) => {      input.addEventListener(input.type === "checkbox" || input.tagName === "SELECT" ? "change" : "input", syncParamForm);    });  }  document.querySelector("#saveFlow").addEventListener("click", () => openSaveFlowForm());  document.querySelectorAll("[data-add-flow-case]").forEach((button) => {    button.addEventListener("click", async () => {      state.factory.caseIds.push(Number(button.dataset.addFlowCase));      persistFactoryDraft();      await renderDataScriptEditor();    });  });  document.querySelectorAll("[data-remove-flow-case]").forEach((button) => {    button.addEventListener("click", async () => {      state.factory.caseIds.splice(Number(button.dataset.removeFlowCase), 1);      persistFactoryDraft();      await renderDataScriptEditor();    });  });  document.querySelectorAll("[data-move-flow-case]").forEach((button) => {    button.addEventListener("click", async () => {      const [rawIndex, direction] = button.dataset.moveFlowCase.split(":");      const index = Number(rawIndex);      const next = direction === "up" ? index - 1 : index + 1;      if (next < 0 || next >= state.factory.caseIds.length) return;      const ids = state.factory.caseIds;      [ids[index], ids[next]] = [ids[next], ids[index]];      persistFactoryDraft();      await renderDataScriptEditor();    });  });}function openSaveFlowForm() {  const flow = readFlows().find((item) => item.id === state.factory.flowId);  openForm(    "保存脚本",    [{ name: "name", label: "脚本名称", required: true, default: flow?.name || "购物车造数脚本" }],    flow || {},    async (data) => {      const flows = readFlows();      const isEditing = Boolean(state.factory.flowId);      const id = isEditing ? state.factory.flowId : newFlowId();      const index = flows.findIndex((item) => item.id === id);      if (isEditing && index < 0) {        throw new Error("当前脚本不存在，无法保存为新增脚本，请返回列表后重新编辑");      }      const nextFlow = {        id,        name: data.name,        scriptType: (index >= 0 ? flows[index]?.scriptType : flow?.scriptType) || "",        projectId: state.factory.projectId,        envId: state.factory.envId,        caseIds: [...state.factory.caseIds],        variables: state.factory.variables,        lastOrderSn: (index >= 0 ? flows[index]?.lastOrderSn : flow?.lastOrderSn) || "",        lastPurchaseNo: (index >= 0 ? flows[index]?.lastPurchaseNo : flow?.lastPurchaseNo) || "",        lastPorderSn: (index >= 0 ? flows[index]?.lastPorderSn : flow?.lastPorderSn) || "",        lastRecordId: (index >= 0 ? flows[index]?.lastRecordId : flow?.lastRecordId) || "",      };      if (index >= 0) flows[index] = nextFlow;      else flows.push(nextFlow);      writeFlows(flows);      state.factory.flowId = id;      persistFactoryDraft();      state.factory.editing = false;      showToast("脚本已保存");      await renderShell();    },  );}async function runFactoryFlow() {  if (!state.factory.caseIds.length) {    showToast("请先加入接口用例");    return;  }  let variables = {};  try {    variables = parseJsonText(state.factory.variables, {});  } catch {    showToast("运行时变量不是合法 JSON");    return;  }  try {    showToast("脚本执行中，请稍候");    const payload = {      case_ids: state.factory.caseIds,      variables,    };    if (state.factory.envId) payload.env_id = Number(state.factory.envId);    const result = await api("/api/api-cases/batch-execute", { method: "POST", body: payload });    showFactoryResult(result);  } catch (error) {    showToast(error.message);  }}function saveFlowVariables(flow, variables) {  const text = JSON.stringify(variables || {}, null, 2);  const flows = readFlows();  const next = flows.map((item) => (item.id === flow.id ? { ...item, variables: text } : item));  writeFlows(next);  flow.variables = text;}function openRunScriptForm(flow) {  const builtInTypes = BUILTIN_DATA_SCRIPT_TYPES;  if (!flow || (!builtInTypes.includes(flow.scriptType) && !(flow.caseIds || []).length)) {    showToast("脚本没有配置步骤");    return;  }  const fields = scriptParamFields(flow.scriptType, flow);  if (!fields.length) {    runSavedFlow(flow);    return;  }  let variables = {};  try {    variables = parseJsonText(flow.variables || "{}", {});  } catch {    showToast("脚本变量不是合法 JSON");    return;  }  variables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables(flow.scriptType, variables, flow)));  const values = {    ...paramFormValues(fields, variables),    __save_defaults: false,  };  openForm(    `执行 ${flow.name || "数据脚本"}`,    [...fields, { name: "__save_defaults", label: "保存为默认值", type: "checkbox", default: false }],    values,    async (data) => {      const runtimeVariables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables(flow.scriptType, mergeParamValues(variables, fields, data), flow)));      if (data.__save_defaults) saveFlowVariables(flow, runtimeVariables);      await runSavedFlow(flow, runtimeVariables);      return false;    },    "执行",  );}function scriptStepEstimate(flow, variables) {  if (!flow) return 1;  if (flow.scriptType === "order_quote") return variables?.run_backend_flow === false ? 5 : 9;  if (flow.scriptType === "balance_payment") return 3;  if (flow.scriptType === "bank_payment") return variables?.finance_confirm === false ? 3 : 5;  if (flow.scriptType === "purchase_to_shelf") {    return variables?.link_quote_balance_before_shelf === false || variables?.auto_quote_and_pay === false ? 9 : 21;  }  if (flow.scriptType === "purchase_to_shelf_chain") return 21;  if (flow.scriptType === "warehouse_delivery") return variables?.run_backend_delivery_flow === false ? 3 : 11;  if (flow.scriptType === "porder_balance_payment") return 14;  if (flow.scriptType === "porder_bank_payment") return variables?.finance_confirm === false ? 14 : 16;
  if (flow.scriptType === "balance_recharge") return variables?.finance_confirm === false ? 3 : 5;  if (flow.scriptType !== "shopping_cart") return Math.max((flow.caseIds || []).length, 1);  const perShopRaw = Number(variables?.per_shop);  const perShop = Number.isFinite(perShopRaw) && perShopRaw > 0 ? Math.floor(perShopRaw) : 5;  const targetShopsRaw = Number(variables?.target_shops || variables?.shop_count);  const rawShopTypes = variables?.shop_types;  const shopTypes = Array.isArray(rawShopTypes)    ? rawShopTypes    : String(rawShopTypes || "")        .split(",")        .map((item) => item.trim())        .filter(Boolean);  const shopCount = Number.isFinite(targetShopsRaw) && targetShopsRaw > 0 ? Math.floor(targetShopsRaw) : Math.max(shopTypes.length || 1, 1);  return 1 + shopCount * perShop;}function openScriptProgress(title, initialMessage) {  modalEl.innerHTML = `    <div class="modal-head">      <h3>${escapeHtml(title || "\u811a\u672c\u6267\u884c\u8fdb\u5ea6")}</h3>      <button class="btn secondary" type="button" id="closeProgress">\u5173\u95ed</button>    </div>    <div class="modal-body">      <div class="progress-meta">        <strong id="progressMessage">${escapeHtml(initialMessage || "\u6b63\u5728\u51c6\u5907\u811a\u672c...")}</strong>        <span id="progressPercent">8%</span>      </div>      <div class="progress-track">        <div class="progress-fill" id="progressFill" style="width:8%"></div>      </div>      <p class="progress-note">\u811a\u672c\u8fd0\u884c\u4e2d\uff0c\u7ed3\u675f\u540e\u4f1a\u81ea\u52a8\u5c55\u793a\u7ed3\u679c\u3002</p>    </div>  `;  if (!modalEl.open) modalEl.showModal();  const fillEl = document.querySelector("#progressFill");  const percentEl = document.querySelector("#progressPercent");  const messageEl = document.querySelector("#progressMessage");  const closeBtn = document.querySelector("#closeProgress");  let percent = 8;  let failed = false;  let closed = false;  const tick = () => {    if (percent >= 92) return;    const delta = percent < 40 ? 6 : percent < 70 ? 3 : 1;    percent = Math.min(92, percent + delta);    render();  };  const timer = window.setInterval(tick, 700);  closeBtn.addEventListener("click", () => {    closed = true;    window.clearInterval(timer);    if (modalEl.open) modalEl.close();  });  function render() {    fillEl.style.width = `${percent}%`;    fillEl.classList.toggle("failed", failed);    percentEl.textContent = `${Math.round(percent)}%`;  }  render();  function done(message, isFailed) {    window.clearInterval(timer);    failed = Boolean(isFailed);    if (!failed) percent = 100;    if (message) messageEl.textContent = message;    if (!closed) render();  }  return {    update(nextPercent, message) {      if (typeof nextPercent === "number" && Number.isFinite(nextPercent)) {        percent = Math.max(percent, Math.min(95, Math.round(nextPercent)));      }      if (message) messageEl.textContent = message;      render();    },    success(message) {      done(message || "\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u8f93\u51fa\u7ed3\u679c...", false);    },    fail(message) {      done(message || "\u811a\u672c\u6267\u884c\u5931\u8d25", true);    },  };}function scriptResultRecord(result, caseName) {  return { id: result?.id || "", case_name: caseName || "数据脚本", result: result?.result || "failed" };}function updateFlowLastOrder(flow, orderSn, recordId) {  if (!orderSn) return;  const flows = readFlows().map((item) =>    item.id === flow.id ? { ...item, lastOrderSn: orderSn, lastRecordId: recordId || item.lastRecordId || "" } : item,  );  writeFlows(flows);  flow.lastOrderSn = orderSn;  flow.lastRecordId = recordId || flow.lastRecordId || "";}function buildCartAutofillVariables(variables, shortageSummary) {  const targetShops = Number(shortageSummary?.expected_shop_count || variables.order_shop_count || variables.target_shops || variables.shop_count || 1);  const perShop = Number(shortageSummary?.expected_per_shop || variables.order_per_shop || variables.per_shop || variables.order_item_count || 1);  const next = {    ...variables,    target_shops: Number.isFinite(targetShops) && targetShops > 0 ? targetShops : 1,    per_shop: Number.isFinite(perShop) && perShop > 0 ? perShop : 1,  };  if (!next.shop_type) {    const shopTypes = splitParamList(next.shop_types);    next.shop_type = shopTypes[0] || "1688";  }  return sanitizeScriptVariables("shopping_cart", next);}async function runMultiPaymentFlow(flow, variables, progress, options = {}) {  const orderSns = orderSnListFromVariables(variables);  const isBank = flow.scriptType === "bank_payment";  const endpoint = isBank ? "/api/data-scripts/bank-payment" : "/api/data-scripts/balance-payment";  const records = [];  const orders = [];  for (const [index, orderSn] of orderSns.entries()) {    progress.update(18 + Math.round((index / orderSns.length) * 70), `正在执行第 ${index + 1}/${orderSns.length} 个订单：${orderSn}`);    const requestVariables = { ...variables, order_sn: orderSn };    delete requestVariables.order_sns;    if (orderSns.length > 1) delete requestVariables.serial_number;    try {      const result = await api(endpoint, {        method: "POST",        body: {          project_id: flow.projectId ? Number(flow.projectId) : null,          env_id: flow.envId ? Number(flow.envId) : null,          variables: requestVariables,        },      });      const summary = result.summary || {};      const finalOrderSn = summary.order_sn || orderSn;      records.push(scriptResultRecord(result, `${flow.name || "支付脚本"}-${finalOrderSn}`));      orders.push({ order_sn: finalOrderSn, result: result.result, summary });      updateFlowLastOrder(flow, finalOrderSn, result.id);    } catch (error) {      records.push({ id: "", case_name: `${flow.name || "支付脚本"}-${orderSn}`, result: "failed" });      orders.push({ order_sn: orderSn, result: "failed", error: error.message });    }  }  const failed = orders.filter((item) => item.result !== "passed");  if (failed.length) {    progress.fail("多订单支付执行完成，存在失败订单");  } else {    progress.success("多订单支付执行完成，正在展示汇总...");  }  return presentScriptResult({    records,    variables: {      total: orders.length,      passed: orders.length - failed.length,      failed: failed.length,      orders,    },  }, options);}async function runMultiPorderFlow(flow, variables, progress, options = {}) {  const porderSns = porderSnListFromVariables(variables);  const records = [];  const porders = [];  for (const [index, porderSn] of porderSns.entries()) {    progress.update(18 + Math.round((index / porderSns.length) * 70), `\u6b63\u5728\u6267\u884c\u7b2c ${index + 1}/${porderSns.length} \u4e2a\u914d\u9001\u5355\uff1a${porderSn}`);    const requestVariables = { ...variables, porder_sn: porderSn };    delete requestVariables.porder_sns;    if (porderSns.length > 1) delete requestVariables.serial_number;    try {      const result = await runSavedFlow(flow, requestVariables, { singleCustomerRun: true, collectOnly: true, progress: SILENT_PROGRESS });      const resultRecords = result?.records?.length ? result.records : [{ id: "", case_name: flow.name || "\u914d\u9001\u5355\u811a\u672c", result: "failed" }];      resultRecords.forEach((row) => records.push({ ...row, case_name: `${row.case_name || flow.name || "\u914d\u9001\u5355\u811a\u672c"}-${porderSn}` }));      const porderFailed = resultRecords.some((row) => row.result !== "passed");      porders.push({ porder_sn: porderSn, result: porderFailed ? "failed" : "passed", summary: result?.variables || {} });    } catch (error) {      records.push({ id: "", case_name: `${flow.name || "\u914d\u9001\u5355\u811a\u672c"}-${porderSn}`, result: "failed" });      porders.push({ porder_sn: porderSn, result: "failed", error: error.message });    }  }  const failed = porders.filter((item) => item.result !== "passed");  if (failed.length) {    progress.fail("\u591a\u914d\u9001\u5355\u6267\u884c\u5b8c\u6210\uff0c\u5b58\u5728\u5931\u8d25\u914d\u9001\u5355");  } else {    progress.success("\u591a\u914d\u9001\u5355\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u6c47\u603b...");  }  return presentScriptResult({    records,    variables: {      total: porders.length,      passed: porders.length - failed.length,      failed: failed.length,      porders,    },  }, options);}async function runOrderQuoteWithAutofill(flow, variables, progress, options = {}) {  const records = [];  const executeQuote = async (label) => {    const result = await api("/api/data-scripts/order-quote", {      method: "POST",      body: {        project_id: flow.projectId ? Number(flow.projectId) : null,        env_id: flow.envId ? Number(flow.envId) : null,        variables,      },    });    records.push(scriptResultRecord(result, label || flow.name));    updateFlowLastOrder(flow, result.summary?.order_sn || "", result.id);    return result;  };  progress.update(24, "正在执行前台提单与后台报价...");  let result = await executeQuote(flow.name);  let summary = result.summary || {};  if (summary.reason_code === "cart_items_shortage" && boolValue(variables.auto_fill_cart_on_shortage, true)) {    const targetShops = summary.expected_shop_count || variables.order_shop_count || 1;    const perShop = summary.expected_per_shop || variables.order_per_shop || variables.order_item_count || 1;    const shortage = summary.shortage_count || Math.max(0, (Number(targetShops) || 1) * (Number(perShop) || 1) - (Number(summary.selected_count) || 0));    progress.update(42, "购物车可提单商品不足，等待确认是否补货...");    const confirmed = window.confirm(`购物车商品不足，还差 ${shortage} 个。是否自动执行加购物车脚本补到 ${targetShops} 个店铺、每店 ${perShop} 个商品后重新提单？`);    if (confirmed) {      progress.update(48, "正在自动补充购物车商品...");      const cartVariables = buildCartAutofillVariables(variables, summary);      const cartResult = await api("/api/data-scripts/shopping-cart", {        method: "POST",        body: {          project_id: flow.projectId ? Number(flow.projectId) : null,          env_id: flow.envId ? Number(flow.envId) : null,          variables: cartVariables,        },      });      records.push(scriptResultRecord(cartResult, "自动补充购物车"));      if (cartResult.result === "passed") {        progress.update(70, "补货完成，正在重新执行订单报价...");        result = await executeQuote(`${flow.name || "订单报价"}-重试`);        summary = result.summary || {};      } else {        summary = {          order_quote: summary,          autofill: cartResult.summary || {},          reason: "自动补充购物车失败",        };      }    }  }  if (records[records.length - 1]?.result !== "passed") {    progress.fail("脚本执行完成，存在失败步骤");  } else {    progress.success("脚本执行完成，正在展示结果...");  }  return presentScriptResult({ records, variables: summary }, options);}async function presentScriptResult(result, options = {}) {  if (options.collectOnly) return result;  await sleep(180);  showFactoryResult(result);  return result;}async function runMultiCustomerFlow(flow, variables, customerIds) {  const progress = openScriptProgress("\u6570\u636e\u811a\u672c\u6267\u884c\u8fdb\u5ea6", `\u51c6\u5907\u6309 ${customerIds.length} \u4e2a\u5ba2\u6237\u6267\u884c`);  const records = [];  const customers = [];  const routeConfig = customerScopedSnConfig(flow);  const routedSns = routeConfig ? routeConfig.list(variables) : [];  showToast(`\u811a\u672c\u5c06\u6309 ${customerIds.length} \u4e2a\u5ba2\u6237\u987a\u5e8f\u6267\u884c`);  if (routeConfig && routedSns.length) {    const customerSet = new Set(customerIds.map((item) => String(item)));    const snsByCustomer = new Map(customerIds.map((item) => [String(item), []]));    const skippedCustomers = [];    const unmatchedSns = [];    routedSns.forEach((sn) => {      const ownerCustomerId = customerIdFromSnSuffix(sn);      if (ownerCustomerId && customerSet.has(ownerCustomerId)) {        snsByCustomer.get(ownerCustomerId).push(sn);      } else {        unmatchedSns.push({          [routeConfig.singleKey]: sn,          customer_id: ownerCustomerId || "",          result: "failed",          reason: ownerCustomerId ? "\u5355\u53f7\u5ba2\u6237ID\u672a\u5728\u672c\u6b21\u6267\u884c\u8303\u56f4" : "\u5355\u53f7\u672a\u5305\u542b\u5ba2\u6237ID\u540e\u7f00",        });      }    });    unmatchedSns.forEach((item) => {      const sn = item[routeConfig.singleKey];      records.push({ id: "", case_name: `${flow.name || "\u6570\u636e\u811a\u672c"}-${sn}`, result: "failed" });      customers.push({ customer_id: item.customer_id || "-", result: "failed", summary: item });    });    const runnableCustomerIds = customerIds.filter((customerId) => (snsByCustomer.get(String(customerId)) || []).length);    customerIds.forEach((customerId) => {      if (!(snsByCustomer.get(String(customerId)) || []).length) skippedCustomers.push(String(customerId));    });    for (const [index, customerId] of runnableCustomerIds.entries()) {      const scopedSns = snsByCustomer.get(String(customerId)) || [];      progress.update(12 + Math.round((index / Math.max(runnableCustomerIds.length, 1)) * 78), `\u6b63\u5728\u6267\u884c\u5ba2\u6237 ${customerId}\uff08${index + 1}/${runnableCustomerIds.length}\uff09\uff1a${scopedSns.join("\uFF0C")}`);      try {        const routedVariables = routedVariablesForCustomerSn(variables, routeConfig, scopedSns);        const result = await runSavedFlow(flow, variablesForCustomerId(routedVariables, customerId), { singleCustomerRun: true, collectOnly: true, progress: SILENT_PROGRESS });        const resultRecords = result?.records?.length ? result.records : [{ id: "", case_name: flow.name || "\u6570\u636e\u811a\u672c", result: "failed" }];        resultRecords.forEach((row) => records.push({ ...row, case_name: `${row.case_name || flow.name || "\u6570\u636e\u811a\u672c"}-\u5ba2\u6237${customerId}` }));        const customerFailed = resultRecords.some((row) => row.result !== "passed");        customers.push({ customer_id: customerId, result: customerFailed ? "failed" : "passed", sns: scopedSns, summary: result?.variables || {} });      } catch (error) {        records.push({ id: "", case_name: `${flow.name || "\u6570\u636e\u811a\u672c"}-\u5ba2\u6237${customerId}`, result: "failed" });        customers.push({ customer_id: customerId, result: "failed", sns: scopedSns, error: error.message });      }    }    const failed = customers.filter((item) => item.result === "failed");    if (failed.length) {      progress.fail("\u591a\u5ba2\u6237\u6309\u5355\u53f7\u6267\u884c\u5b8c\u6210\uff0c\u5b58\u5728\u5931\u8d25\u5355\u53f7\u6216\u5ba2\u6237");    } else {      progress.success("\u591a\u5ba2\u6237\u6309\u5355\u53f7\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u6c47\u603b...");    }    await sleep(180);    showFactoryResult({      records,      variables: {        customer_count: customerIds.length,        executed_customers: runnableCustomerIds.length,        skipped_customers: skippedCustomers,        sn_count: routedSns.length,        passed: customers.filter((item) => item.result === "passed").length,        failed: failed.length,        customers,      },    });    return;  }  for (const [index, customerId] of customerIds.entries()) {    progress.update(12 + Math.round((index / customerIds.length) * 78), `\u6b63\u5728\u6267\u884c\u5ba2\u6237 ${customerId}\uff08${index + 1}/${customerIds.length}\uff09`);    try {      const result = await runSavedFlow(flow, variablesForCustomerId(variables, customerId), { singleCustomerRun: true, collectOnly: true, progress: SILENT_PROGRESS });      const resultRecords = result?.records?.length ? result.records : [{ id: "", case_name: flow.name || "\u6570\u636e\u811a\u672c", result: "failed" }];      resultRecords.forEach((row) => records.push({ ...row, case_name: `${row.case_name || flow.name || "\u6570\u636e\u811a\u672c"}-\u5ba2\u6237${customerId}` }));      const customerFailed = resultRecords.some((row) => row.result !== "passed");      customers.push({ customer_id: customerId, result: customerFailed ? "failed" : "passed", summary: result?.variables || {} });    } catch (error) {      records.push({ id: "", case_name: `${flow.name || "\u6570\u636e\u811a\u672c"}-\u5ba2\u6237${customerId}`, result: "failed" });      customers.push({ customer_id: customerId, result: "failed", error: error.message });    }  }  const failed = customers.filter((item) => item.result !== "passed");  if (failed.length) {    progress.fail("\u591a\u5ba2\u6237\u6267\u884c\u5b8c\u6210\uff0c\u5b58\u5728\u5931\u8d25\u5ba2\u6237");  } else {    progress.success("\u591a\u5ba2\u6237\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u6c47\u603b...");  }  await sleep(180);  showFactoryResult({    records,    variables: {      customer_count: customers.length,      passed: customers.length - failed.length,      failed: failed.length,      customers,    },  });}async function runSavedFlow(flow, runtimeVariables = null, options = {}) {  const builtInTypes = BUILTIN_DATA_SCRIPT_TYPES;  if (!flow || (!builtInTypes.includes(flow.scriptType) && !(flow.caseIds || []).length)) {    showToast("脚本没有配置步骤");    return;  }  let variables = {};  if (runtimeVariables) {    variables = { ...runtimeVariables };  } else {    try {      variables = parseJsonText(flow.variables, {});    } catch {      showToast("脚本变量不是合法 JSON");      return;    }  }  variables = withCustomerLoginInputs(mergeStoredCustomerIds(sanitizeScriptVariables(flow.scriptType, variables, flow)));  const customerIds = customerIdsFromVariables(variables);  if (customerIds.length > 1 && !options.singleCustomerRun) {    await runMultiCustomerFlow(flow, variables, customerIds);    return;  }  if (customerIds.length === 1) variables = variablesForCustomerId(variables, customerIds[0]);  const progress = options.progress || openScriptProgress("\u6570\u636e\u811a\u672c\u6267\u884c\u8fdb\u5ea6", `\u9884\u8ba1\u6267\u884c ${scriptStepEstimate(flow, variables)} \u4e2a\u6b65\u9aa4`);  try {    showToast("脚本执行中，请稍候");    if (flow.scriptType === "shopping_cart") {      progress.update(24, "\u6b63\u5728\u6267\u884c\u767b\u5f55\u3001\u641c\u7d22\u3001\u52a0\u8d2d\u6b65\u9aa4...");      const result = await api("/api/data-scripts/shopping-cart", {        method: "POST",        body: {          project_id: flow.projectId ? Number(flow.projectId) : null,          env_id: flow.envId ? Number(flow.envId) : null,          variables,        },      });      progress.success("\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");      return presentScriptResult({        records: [{ id: result.id, case_name: flow.name, result: result.result }],        variables: result.summary || {},      }, options);    }    if (flow.scriptType === "order_quote") {      return await runOrderQuoteWithAutofill(flow, variables, progress, options);    }    if (flow.scriptType === "balance_payment" || flow.scriptType === "bank_payment") {      const isBank = flow.scriptType === "bank_payment";      const orderSns = orderSnListFromVariables(variables);      if (orderSns.length > 1) {        return await runMultiPaymentFlow(flow, variables, progress, options);      }      if (orderSns.length === 1 && variables.order_sns) {        variables = { ...variables, order_sn: orderSns[0] };        delete variables.order_sns;      }      progress.update(        24,        isBank          ? "\u6b63\u5728\u67e5\u627e\u7b49\u5f85\u4ed8\u6b3e\u8ba2\u5355\uff0c\u6267\u884c\u94f6\u884c\u8f6c\u8d26\u4e0e\u8d22\u52a1\u786e\u8ba4..."          : "\u6b63\u5728\u67e5\u627e\u7b49\u5f85\u4ed8\u6b3e\u8ba2\u5355\uff0c\u6267\u884c\u4f59\u989d\u652f\u4ed8...",      );      const result = await api(isBank ? "/api/data-scripts/bank-payment" : "/api/data-scripts/balance-payment", {        method: "POST",        body: {          project_id: flow.projectId ? Number(flow.projectId) : null,          env_id: flow.envId ? Number(flow.envId) : null,          variables,        },      });      const orderSn = result.summary?.order_sn || "";      if (orderSn) {        const flows = readFlows().map((item) =>          item.id === flow.id ? { ...item, lastOrderSn: orderSn, lastRecordId: result.id } : item,        );        writeFlows(flows);        flow.lastOrderSn = orderSn;        flow.lastRecordId = result.id;      }      progress.success("\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");      return presentScriptResult({        records: [{ id: result.id, case_name: flow.name, result: result.result }],        variables: result.summary || {},      }, options);    }    if (flow.scriptType === "purchase_to_shelf") {      const requestVariables = { ...variables };      const linkBeforeShelf = !String(requestVariables.order_sn || "").trim()        && requestVariables.link_quote_balance_before_shelf !== false        && requestVariables.auto_quote_and_pay !== false;      if (linkBeforeShelf) {        delete requestVariables.order_sn;        delete requestVariables.last_order_sn;        progress.update(8, "\u6b63\u5728\u8054\u52a8\u6267\u884c\uff1a\u8ba2\u5355\u62a5\u4ef7\u2192\u4f59\u989d\u652f\u4ed8\u2192\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6...");        const result = await api("/api/data-scripts/purchase-to-shelf-chain", {          method: "POST",          body: {            project_id: flow.projectId ? Number(flow.projectId) : null,            env_id: flow.envId ? Number(flow.envId) : null,            variables: requestVariables,          },        });        const orderSn = result.summary?.order_sn || "";        const purchaseNo = result.summary?.purchase_no || "";        const flows = readFlows().map((item) =>          item.id === flow.id            ? { ...item, lastOrderSn: orderSn, lastPurchaseNo: purchaseNo, lastRecordId: result.id }            : item,        );        writeFlows(flows);        flow.lastOrderSn = orderSn;        flow.lastPurchaseNo = purchaseNo;        flow.lastRecordId = result.id;        progress.success("\u8054\u52a8\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");        return presentScriptResult({        records: [{ id: result.id, case_name: flow.name, result: result.result }],        variables: result.summary || {},      }, options);      }      progress.update(24, "\u6b63\u5728\u63a8\u8fdb\u5f85\u62cd\u4e0b\u5546\u54c1\uff1a\u4ea4\u6613\u53f7\u3001\u5f85\u6539\u4ef7\u3001\u4ed8\u6b3e\u3001\u6838\u67e5\u3001\u4e0a\u67b6\u5165\u5e93...");      if (!requestVariables.order_sn && flow.lastOrderSn) requestVariables.order_sn = flow.lastOrderSn;      const result = await api("/api/data-scripts/purchase-to-shelf", {        method: "POST",        body: {          project_id: flow.projectId ? Number(flow.projectId) : null,          env_id: flow.envId ? Number(flow.envId) : null,          variables: requestVariables,        },      });      const orderSn = result.summary?.order_sn || requestVariables.order_sn || "";      const purchaseNo = result.summary?.purchase_no || requestVariables.purchase_no || "";      const flows = readFlows().map((item) =>        item.id === flow.id          ? { ...item, lastOrderSn: orderSn, lastPurchaseNo: purchaseNo, lastRecordId: result.id }          : item,      );      writeFlows(flows);      flow.lastOrderSn = orderSn;      flow.lastPurchaseNo = purchaseNo;      flow.lastRecordId = result.id;      progress.success("\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");      return presentScriptResult({        records: [{ id: result.id, case_name: flow.name, result: result.result }],        variables: result.summary || {},      }, options);    }    if (flow.scriptType === "purchase_to_shelf_chain") {      progress.update(8, "\u6b63\u5728\u6267\u884c\u7ec4\u5408\u811a\u672c\uff1a\u8ba2\u5355\u62a5\u4ef7\u2192\u4f59\u989d\u652f\u4ed8\u2192\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6...");      const result = await api("/api/data-scripts/purchase-to-shelf-chain", {        method: "POST",        body: {          project_id: flow.projectId ? Number(flow.projectId) : null,          env_id: flow.envId ? Number(flow.envId) : null,          variables,        },      });      const orderSn = result.summary?.order_sn || "";      const purchaseNo = result.summary?.purchase_no || "";      const flows = readFlows().map((item) =>        item.id === flow.id          ? { ...item, lastOrderSn: orderSn, lastPurchaseNo: purchaseNo, lastRecordId: result.id }          : item,      );      writeFlows(flows);      flow.lastOrderSn = orderSn;      flow.lastPurchaseNo = purchaseNo;      flow.lastRecordId = result.id;      progress.success("\u7ec4\u5408\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");      return presentScriptResult({        records: [{ id: result.id, case_name: flow.name, result: result.result }],        variables: result.summary || {},      }, options);    }    if (flow.scriptType === "warehouse_delivery") {      progress.update(12, "\u6b63\u5728\u6267\u884c\uff1a\u4ed3\u5e93\u9009\u62e91\u756a -> \u63d0\u51fa\u914d\u9001\u5355 -> \u540e\u53f0\u914d\u8d27\u88c5\u7bb1 -> \u63d0\u4ea4\u4e1a\u52a1\u62a5\u4ef7...");      const result = await api("/api/data-scripts/warehouse-delivery", {        method: "POST",        body: {          project_id: flow.projectId ? Number(flow.projectId) : null,          env_id: flow.envId ? Number(flow.envId) : null,          variables,        },      });      const porderSn = result.summary?.porder_sn || "";      const flows = readFlows().map((item) =>        item.id === flow.id          ? { ...item, lastPorderSn: porderSn, lastRecordId: result.id }          : item,      );      writeFlows(flows);      flow.lastPorderSn = porderSn;      flow.lastRecordId = result.id;      progress.success("\u914d\u9001\u5355\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");      return presentScriptResult({        records: [{ id: result.id, case_name: flow.name, result: result.result }],        variables: result.summary || {},      }, options);    }    if (flow.scriptType === "porder_balance_payment" || flow.scriptType === "porder_bank_payment" || isPorderShipmentFlow(flow)) {      const porderSns = porderSnListFromVariables(variables);      if (porderSns.length > 1) {        return await runMultiPorderFlow(flow, variables, progress, options);      }      if (porderSns.length === 1 && variables.porder_sns) {        variables = { ...variables, porder_sn: porderSns[0] };        delete variables.porder_sns;      }    }    if (flow.scriptType === "porder_balance_payment") {      progress.update(12, "正在执行：配送单后台流程 -> 余额支付...");      const result = await api("/api/data-scripts/porder-balance-payment", {        method: "POST",        body: {          project_id: flow.projectId ? Number(flow.projectId) : null,          env_id: flow.envId ? Number(flow.envId) : null,          variables,        },      });      progress.success("配送单余额付款脚本执行完成，正在展示结果...");      return presentScriptResult({        records: [{ id: result.id, case_name: flow.name, result: result.result }],        variables: result.summary || {},      }, options);    }    if (flow.scriptType === "porder_bank_payment") {      progress.update(12, "正在执行：配送单后台流程 -> 银行支付 -> 财务确认...");      const result = await api("/api/data-scripts/porder-bank-payment", {        method: "POST",        body: {          project_id: flow.projectId ? Number(flow.projectId) : null,          env_id: flow.envId ? Number(flow.envId) : null,          variables,        },      });      progress.success("配送单银行付款脚本执行完成，正在展示结果...");      return presentScriptResult({        records: [{ id: result.id, case_name: flow.name, result: result.result }],        variables: result.summary || {},      }, options);
    }
    if (flow.scriptType === "material_generation") {
      progress.update(24, "正在创建辅料，请稍候...");
      const result = await api("/api/data-scripts/material-generation", {
        method: "POST",
        body: {
          project_id: flow.projectId ? Number(flow.projectId) : null,
          env_id: flow.envId ? Number(flow.envId) : null,
          variables,
        },
      });
      const summary = result.summary || {};
      if (result.result === "passed") {
        progress.success("辅料生成完成");
      } else {
        progress.fail(summary.reason || "辅料生成失败");
      }
      return presentScriptResult({
        records: [{ id: result.id, case_name: flow.name, result: result.result }],
        variables: summary,
      }, options);
    }
    if (flow.scriptType === "balance_recharge") {
      progress.update(24, "正在执行余额充值，请稍候...");
      const result = await api("/api/data-scripts/balance-recharge", {
        method: "POST",
        body: {
          project_id: flow.projectId ? Number(flow.projectId) : null,
          env_id: flow.envId ? Number(flow.envId) : null,
          variables,
        },
      });
      const summary = result.summary || {};
      if (result.result === "passed") {
        progress.success(`余额充值成功：客户 ${summary.customer_id || "-"} 到账 ${summary.amount || "-"}`);
      } else {
        progress.fail(summary.reason || "余额充值失败");
      }
      return presentScriptResult({
        records: [{ id: result.id, case_name: flow.name, result: result.result }],
        variables: summary,
      }, options);
    }
    if (flow.scriptType === "oem_new_inquiry") {
      progress.update(24, "正在执行提出oem询价单，请稍候...");
      const result = await api("/api/data-scripts/oem-new-inquiry", {
        method: "POST",
        body: {
          project_id: flow.projectId ? Number(flow.projectId) : null,
          env_id: flow.envId ? Number(flow.envId) : null,
          variables,
        },
      });
      const summary = result.summary || {};
      if (result.result === "passed") {
        progress.success(`OEM询价单创建成功：${summary.inquiry_sn || "-"}`);
      } else {
        progress.fail(summary.reason || "OEM询价单创建失败");
      }
      return presentScriptResult({
        records: [{ id: result.id, case_name: flow.name, result: result.result }],
        variables: summary,
      }, options);
    }
    if (flow.scriptType === "oem_sample_order") {
      progress.update(24, "正在执行OEM提出样品单，请稍候...");
      const result = await api("/api/data-scripts/oem-sample-order", {
        method: "POST",
        body: {
          project_id: flow.projectId ? Number(flow.projectId) : null,
          env_id: flow.envId ? Number(flow.envId) : null,
          variables,
        },
      });
      const summary = result.summary || {};
      if (result.result === "passed") {
        progress.success(`OEM样品单创建成功：${summary.order_sn || "-"}`);
      } else {
        progress.fail(summary.reason || "OEM样品单创建失败");
      }
      return presentScriptResult({
        records: [{ id: result.id, case_name: flow.name, result: result.result }],
        variables: summary,
      }, options);
    }
    if (flow.scriptType === "oem_full_inquiry_flow") {
      progress.update(24, "正在执行OEM询价单全流程，请稍候...");
      const result = await api("/api/data-scripts/oem-full-inquiry-flow", {
        method: "POST",
        body: {
          project_id: flow.projectId ? Number(flow.projectId) : null,
          env_id: flow.envId ? Number(flow.envId) : null,
          variables,
        },
      });
      const summary = result.summary || {};
      if (result.result === "passed") {
        progress.success(`OEM询价单全流程执行成功：${summary.order_sn || summary.inquiry_sn || "-"}`);
      } else {
        progress.fail(summary.reason || "OEM询价单全流程执行失败");
      }
      return presentScriptResult({
        records: [{ id: result.id, case_name: flow.name, result: result.result }],
        variables: summary,
      }, options);
    }
    if (flow.scriptType === "oem_sample_admin_flow") {
      progress.update(24, "正在执行OEM样品单后台流程...");
      const result = await api("/api/data-scripts/oem-sample-admin-flow", {
        method: "POST",
        body: { project_id: flow.projectId ? Number(flow.projectId) : null, env_id: flow.envId ? Number(flow.envId) : null, variables },
      });
      const summary = result.summary || {};
      if (result.result === "passed") {
        progress.success(`OEM样品单后台流程执行成功：${summary.order_sn || "-"}`);
      } else {
        progress.fail(summary.reason || "OEM样品单后台流程执行失败");
      }
      return presentScriptResult({ records: [{ id: result.id, case_name: flow.name, result: result.result }], variables: summary }, options);
    }
    if (flow.scriptType === "oem_sample_full_flow") {
      progress.update(24, "正在执行OEM样品单全流程...");
      const result = await api("/api/data-scripts/oem-sample-full-flow", {
        method: "POST", body: { project_id: flow.projectId ? Number(flow.projectId) : null, env_id: flow.envId ? Number(flow.envId) : null, variables },
      });
      const summary = result.summary || {};
      if (result.result === "passed") { progress.success(`OEM样品单全流程执行成功：${summary.order_sn || "-"}`); }
      else { progress.fail(summary.reason || "OEM样品单全流程执行失败"); }
      return presentScriptResult({ records: [{ id: result.id, case_name: flow.name, result: result.result }], variables: summary }, options);
    }
    if (flow.scriptType === "oem_bulk_order") {
      progress.update(24, "正在执行OEM大货单下单...");
      const result = await api("/api/data-scripts/oem-bulk-order", {
        method: "POST", body: { project_id: flow.projectId ? Number(flow.projectId) : null, env_id: flow.envId ? Number(flow.envId) : null, variables },
      });
      const summary = result.summary || {};
      if (result.result === "passed") { progress.success(`OEM大货单下单成功：${summary.order_sn || "-"}`); }
      else { progress.fail(summary.reason || "OEM大货单下单失败"); }
      return presentScriptResult({ records: [{ id: result.id, case_name: flow.name, result: result.result }], variables: summary }, options);
    }
    if (flow.scriptType === "oem_balance_pay") {
      progress.update(24, "正在执行OEM余额支付...");
      const result = await api("/api/data-scripts/oem-sample-balance-pay", {
        method: "POST", body: { project_id: flow.projectId ? Number(flow.projectId) : null, env_id: flow.envId ? Number(flow.envId) : null, variables },
      });
      const summary = result.summary || {};
      if (result.result === "passed") { progress.success(`余额支付成功：${summary.serial_number || "-"}`); }
      else { progress.fail(summary.reason || "余额支付失败"); }
      return presentScriptResult({ records: [{ id: result.id, case_name: flow.name, result: result.result }], variables: summary }, options);
    }
    progress.update(24, `\u6b63\u5728\u987a\u5e8f\u6267\u884c ${Math.max((flow.caseIds || []).length, 1)} \u4e2a\u63a5\u53e3\u7528\u4f8b...`);    const payload = {      case_ids: flow.caseIds,      variables,    };    if (flow.envId) payload.env_id = Number(flow.envId);    const result = await api("/api/api-cases/batch-execute", { method: "POST", body: payload });    progress.success("\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");    return presentScriptResult(result, options);  } catch (error) {    progress.fail(`\u6267\u884c\u5931\u8d25\uff1a${error.message}`);    showToast(error.message);    if (options.collectOnly) throw error;  }}function renderChineseSummary(summary) {  if (!summary || typeof summary !== 'object' || !Object.keys(summary).length) {    return `<div class="empty">暂无执行汇总数据</div>`;  }  const LABEL_MAP = {    keyword: "搜索关键词",    expected_total: "期望添加商品数",    available_expected_total: "可用期望商品数",    added_total: "实际添加商品数",    shop_types: "商品来源",    skipped_shop_types: "跳过的来源",    failed_shop_types: "失败的来源",    strict_shop_count: "严格店铺数",    reason: "失败原因",    ready_shops: "已就绪店铺数",    target_shops: "目标店铺数",    per_shop: "每店商品数",    api_added_total: "API添加数",    verified_added_total: "验证通过数",    cart_selection: "购物车选择",    payment_type: "付款类型",    order_sn: "订单号", samples_price_return: "样品费退还(元)", samples_other_fee: "样品其他费用", samples_freight: "样品运费(元)", samples_delivery_time: "打样货期(天)", factory_img: "工厂图片",
    inquiry_sn: "询价单号",
    porder_sn: "配送单号",    pay_amount: "付款金额",    payment_passed: "付款是否成功",    serial_number: "流水号",    porder_matched: "配送单匹配",    purchase_no: "交易号",    selected_count: "选中商品数",    purchase_ids: "采购ID列表",    grid_id: "货位ID",    grid_number: "货位编号",    storage_count: "入库数量",    storage_passed: "入库是否成功",    customer_count: "客户总数",    executed_customers: "已执行客户数",    skipped_customers: "跳过的客户",    sn_count: "单号数量",    customers: "客户明细",    passed: "成功数",    failed: "失败数",    total: "总计",    material_generation_name: "辅料名称",    material_generation_count: "请求生成数",    created_count: "已创建数",    skipped_count: "已跳过数",    created_list: "已创建列表",    skipped_list: "已跳过列表",    completed: "已完成",    shop_type: "商品来源",    order_item_count: "每店商品数",    order_item_num: "每个商品数量",    logistics_id: "物流方式",    submit_order: "是否提交订单",    run_backend_flow: "是否执行后台流程",    send_num: "每番提出数量",    warehouse_sku_count: "请求番数",    actual_warehouse_sku_count: "实际番数",    total_send_num: "总提出数量",    selected_sku_ids: "选中SKU",    selected_warehouse_items: "选中仓库明细",    order_detail_ids: "仓库明细ID",    porder_detail_ids: "配送单明细ID",    porder_logistics_id: "配送物流ID",    warning: "提示",    error: "错误信息",    customer_id: "客户ID",    duration_ms: "耗时(ms)",    screenshot: "截图",    current_url: "当前URL",    total_box_item_num: "装箱商品总数",    requested_box_count: "请求箱数",    kept_box_count: "实际保留箱数",    box_ids: "箱ID列表",    box_item_counts: "每箱商品数",    box_allocations: "箱分配明细",    direct_box_passed: "直接装箱是否成功",    deleted_box_ids: "已删除箱ID",    unfinished_box_ids: "未完成箱ID",  };  const BOOL_TRUE_TEXT = { true: "是", false: "否", "true": "是", "false": "否" };  const entries = Object.entries(summary).filter(([key]) => key !== 'customers' && !Array.isArray(summary[key]) && typeof summary[key] !== 'object');  const arrayEntries = Object.entries(summary).filter(([key, val]) => key !== 'customers' && Array.isArray(val) && val.length);  const objectEntries = Object.entries(summary).filter(([key, val]) => key === 'customers' && Array.isArray(val) && val.length);  const html = [];  if (entries.length) {    html.push(`<table class="summary-table"><tbody>${entries.map(([key, val]) => {      const label = LABEL_MAP[key] || key;      const display = typeof val === 'boolean' || val === true || val === false ? (BOOL_TRUE_TEXT[String(val)] || String(val)) : String(val ?? '');      const cellHtml = key === 'factory_img' && val ? `<img src="${escapeHtml(String(val))}" style="max-width:200px;max-height:200px" />` : escapeHtml(display);      return `<tr><td class="summary-label">${escapeHtml(label)}</td><td class="summary-value">${cellHtml}</td></tr>`;    }).join('')}</tbody></table>`);  }  if (arrayEntries.length) {    arrayEntries.forEach(([key, val]) => {      const label = LABEL_MAP[key] || key;      const display = val.map((item) => typeof item === "object" && item !== null ? JSON.stringify(item, null, 2) : String(item)).join('\n');      html.push(`<details class="summary-detail"><summary>${escapeHtml(label)}（${val.length}项）</summary><pre class="log-view">${escapeHtml(display)}</pre></details>`);    });  }  if (objectEntries.length) {    objectEntries.forEach(([key, val]) => {      html.push(`<details class="summary-detail" open><summary>${escapeHtml(LABEL_MAP[key] || key)}（${val.length}条）</summary><table class="summary-table"><tbody>${val.map((item) => {        const itemEntries = Object.entries(item || {});        return itemEntries.map(([k, v]) => {          const label = LABEL_MAP[k] || k;          const display = typeof v === 'boolean' || v === true || v === false ? (BOOL_TRUE_TEXT[String(v)] || String(v)) : String(v ?? '');          return `<tr><td class="summary-label">${escapeHtml(label)}</td><td class="summary-value">${escapeHtml(display)}</td></tr>`;        }).join('');      }).join('<tr><td colspan="2" style="border-bottom:2px solid var(--border)"></td></tr>')}</tbody></table></details>`);    });  }  const unknownKeys = Object.keys(summary).filter((key) => !LABEL_MAP[key]);  if (unknownKeys.length) {    html.push(`<details class="summary-detail"><summary>其他原始数据</summary><pre class="log-view">${escapeHtml(JSON.stringify(summary, null, 2))}</pre></details>`);  }  return html.join('');}

function ensureMaterialGenerationScript(flows, projects, envs, cases) {
  if (isBuiltinDeleted("material_generation_builtin")) return flows;
  const env = dataScriptDefaultEnv(projects, envs);
  const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";
  if (!env) return flows;
  const existingIndex = flows.findIndex((flow) => flow.id === "material_generation_builtin");
  if (existingIndex >= 0) return flows;
  const nextFlow = {
    id: "material_generation_builtin",
    name: "\u8f85\u6599\u751f\u6210",
    scriptType: "material_generation",
    projectId: String(projectId),
    envId: String(env.id),
    caseIds: [],
    variables: JSON.stringify({ count: 1 }, null, 2),
  };
  const next = [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensureBalanceRechargeScript(flows, projects, envs, cases) {
  if (isBuiltinDeleted("balance_recharge_builtin")) return flows;
  const env = dataScriptDefaultEnv(projects, envs);
  const projectId = env?.project_id || dataScriptDefaultProject(projects)?.id || projects[0]?.id || "";
  if (!env) return flows;
  const existingIndex = flows.findIndex((flow) => flow.id === "balance_recharge_builtin");
  if (existingIndex >= 0) return flows;
  const nextFlow = {
    id: "balance_recharge_builtin",
    name: "余额充值",
    scriptType: "balance_recharge",
    projectId: String(projectId),
    envId: String(env.id),
    caseIds: [],
    variables: JSON.stringify({ customer_ids: "", amount: "" }, null, 2),
  };
  const next = [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensureOemNewInquiryScript(flows, projects, envs, cases) {
  if (isBuiltinDeleted("oem_new_inquiry_builtin")) return flows;
  // OEM 独立项目：优先匹配名为 "oem-测试" 的项目
  const oemProject = projects.find((p) => p.name === "oem-测试");
  if (!oemProject) return flows;
  // 直接用 OEM 项目的第一个 env，不依赖 dataScriptDefaultEnv（它只认日本站）
  const env = (envs || []).find((e) => String(e.project_id) === String(oemProject.id));
  if (!env) return flows;
  const projectId = oemProject.id;
  const envId = env.id;
  const existingIndex = flows.findIndex((flow) => flow.id === "oem_new_inquiry_builtin");
  if (existingIndex >= 0) {
    // 已存在则更新 projectId/envId（防止 OEM 项目后建导致绑定到错误项目）
    const next = flows.map((flow) =>
      flow.id === "oem_new_inquiry_builtin"
        ? { ...flow, projectId: String(projectId), envId: String(envId), name: "提出oem询价单" }
        : flow,
    );
    writeFlows(next);
    return next;
  }
  const nextFlow = {
    id: "oem_new_inquiry_builtin",
    name: "提出oem询价单",
    scriptType: "oem_new_inquiry",
    projectId: String(projectId),
    envId: String(envId),
    caseIds: [],
    variables: JSON.stringify(
      { goods_name: "测试商品", hope_min_price: "1", hope_max_price: "100", hope_futures: "10", goods_type: 1, factory_urls: "", goods_img: "" },
      null,
      2,
    ),
  };
  const next = [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensureOemSampleOrderScript(flows, projects, envs, cases) {
  if (isBuiltinDeleted("oem_sample_order_builtin")) return flows;
  // OEM 独立项目：优先匹配名为 "oem-测试" 的项目
  const oemProject = projects.find((p) => p.name === "oem-测试");
  if (!oemProject) return flows;
  // 直接用 OEM 项目的第一个 env，不依赖 dataScriptDefaultEnv（它只认日本站）
  const env = (envs || []).find((e) => String(e.project_id) === String(oemProject.id));
  if (!env) return flows;
  const projectId = oemProject.id;
  const envId = env.id;
  const existingIndex = flows.findIndex((flow) => flow.id === "oem_sample_order_builtin");
  if (existingIndex >= 0) {
    // 已存在则更新 projectId/envId
    const next = flows.map((flow) =>
      flow.id === "oem_sample_order_builtin"
        ? { ...flow, projectId: String(projectId), envId: String(envId), name: "提出oem样品单" }
        : flow,
    );
    writeFlows(next);
    return next;
  }
  const nextFlow = {
    id: "oem_sample_order_builtin",
    name: "提出oem样品单",
    scriptType: "oem_sample_order",
    projectId: String(projectId),
    envId: String(envId),
    caseIds: [],
    variables: JSON.stringify(
      { order_sn: "", sku_list: "" },
      null,
      2,
    ),
  };
  const next = [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensureOemFullInquiryFlowScript(flows, projects, envs) {
  if (isBuiltinDeleted("oem_full_inquiry_flow_builtin")) return flows;
  const oemProject = projects.find((p) => p.name === "oem-测试");
  if (!oemProject) return flows;
  const env = (envs || []).find((e) => String(e.project_id) === String(oemProject.id));
  if (!env) return flows;
  const projectId = oemProject.id;
  const envId = env.id;
  const existingIndex = flows.findIndex((flow) => flow.id === "oem_full_inquiry_flow_builtin");
  if (existingIndex >= 0) {
    const next = flows.map((flow) =>
      flow.id === "oem_full_inquiry_flow_builtin"
        ? { ...flow, projectId: String(projectId), envId: String(envId), name: "OEM询价单全流程" }
        : flow,
    );
    writeFlows(next);
    return next;
  }
  const nextFlow = {
    id: "oem_full_inquiry_flow_builtin",
    name: "OEM询价单全流程",
    scriptType: "oem_full_inquiry_flow",
    projectId: String(projectId),
    envId: String(envId),
    caseIds: [],
    variables: JSON.stringify({
      goods_name: "测试商品", hope_min_price: "1", hope_max_price: "100", hope_futures: "10",
      goods_class: 110, factory_type: 3, factory_urls: "", goods_img: "",
      sku_info: [{ sku: "sku1", num: 1 }],
      factory_img: "", salesman: "测试业务员", salesman_phone: "13800000000",
      samples_price: "12.00", large_price: "11.00", large_other_fee: "12.00",
      large_freight: "11.00", large_delivery_time: 15, large_deposit_rate: "100",
      real_samples_price: "10.00", real_large_price: "10.00",
    }, null, 2),
  };
  const next = [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensureOemSampleAdminFlowScript(flows, projects, envs) {
  if (isBuiltinDeleted("oem_sample_admin_flow_builtin")) return flows;
  const oemProject = projects.find((p) => p.name === "oem-测试");
  if (!oemProject) return flows;
  const env = (envs || []).find((e) => String(e.project_id) === String(oemProject.id));
  if (!env) return flows;
  const projectId = oemProject.id;
  const envId = env.id;
  const existingIndex = flows.findIndex((flow) => flow.id === "oem_sample_admin_flow_builtin");
  if (existingIndex >= 0) {
    const next = flows.map((flow) =>
      flow.id === "oem_sample_admin_flow_builtin" ? { ...flow, projectId: String(projectId), envId: String(envId), name: "OEM样品单后台流程" } : flow,
    );
    writeFlows(next);
    return next;
  }
  const nextFlow = {
    id: "oem_sample_admin_flow_builtin",
    name: "OEM样品单后台流程",
    scriptType: "oem_sample_admin_flow",
    projectId: String(projectId),
    envId: String(envId),
    caseIds: [],
    variables: JSON.stringify({ order_sn: "", warehouse_city: 2 }, null, 2),
  };
  const next = [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensureOemSampleFullFlowScript(flows, projects, envs) {
  if (isBuiltinDeleted("oem_sample_full_flow_builtin")) return flows;
  const oemProject = projects.find((p) => p.name === "oem-测试");
  if (!oemProject) return flows;
  const env = (envs || []).find((e) => String(e.project_id) === String(oemProject.id));
  if (!env) return flows;
  const projectId = oemProject.id;
  const envId = env.id;
  const existingIndex = flows.findIndex((flow) => flow.id === "oem_sample_full_flow_builtin");
  if (existingIndex >= 0) {
    const next = flows.map((flow) =>
      flow.id === "oem_sample_full_flow_builtin" ? { ...flow, projectId: String(projectId), envId: String(envId), name: "OEM样品单全流程" } : flow,
    );
    writeFlows(next);
    return next;
  }
  const nextFlow = {
    id: "oem_sample_full_flow_builtin",
    name: "OEM样品单全流程",
    scriptType: "oem_sample_full_flow",
    projectId: String(projectId),
    envId: String(envId),
    caseIds: [],
    variables: JSON.stringify({ order_sn: "", sku_list: "", warehouse_city: 2, inquiry_other_fee: "0.00", inquiry_freight: "0.00", inquiry_delivery_time: 0, quote_other_fee: "7", quote_freight: "8", quote_delivery_time: "9", real_other_fee: "7", real_freight: "8" }, null, 2),
  };
  const next = [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensureOemBulkOrderFlowScript(flows, projects, envs) {
  if (isBuiltinDeleted("oem_bulk_order_builtin")) return flows;
  const oemProject = projects.find((p) => p.name === "oem-测试");
  if (!oemProject) return flows;
  const env = (envs || []).find((e) => String(e.project_id) === String(oemProject.id));
  if (!env) return flows;
  const existingIndex = flows.findIndex((flow) => flow.id === "oem_bulk_order_builtin");
  if (existingIndex >= 0) return flows;
  const nextFlow = {
    id: "oem_bulk_order_builtin",
    name: "OEM大货单下单",
    scriptType: "oem_bulk_order",
    projectId: String(oemProject.id),
    envId: String(env.id),
    caseIds: [],
    variables: JSON.stringify({ order_sn: "" }, null, 2),
  };
  const next = [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensureOemBalancePayScript(flows, projects, envs) {
  if (isBuiltinDeleted("oem_balance_pay_builtin")) return flows;
  const oemProject = projects.find((p) => p.name === "oem-测试");
  if (!oemProject) return flows;
  const env = (envs || []).find((e) => String(e.project_id) === String(oemProject.id));
  if (!env) return flows;
  const existingIndex = flows.findIndex((flow) => flow.id === "oem_balance_pay_builtin");
  if (existingIndex >= 0) return flows;
  const nextFlow = {
    id: "oem_balance_pay_builtin",
    name: "OEM余额支付",
    scriptType: "oem_balance_pay",
    projectId: String(oemProject.id),
    envId: String(env.id),
    caseIds: [],
    variables: JSON.stringify({ order_sn: "", coupon_id: "" }, null, 2),
  };
  const next = [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function showFactoryResult(result) {  const rows = result.records || [];  const allPassed = rows.length > 0 && rows.every((r) => r.result === "passed");  const summaryVars = { ...(result.variables || {}) };  if (allPassed) delete summaryVars.reason;  modalEl.innerHTML = `    <div class="modal-head">      <h3>脚本执行结果</h3>      <button class="btn secondary" type="button" id="closeModal">关闭</button>    </div>    <div class="modal-body">      ${renderTable(        [          { key: "case_name", label: "用例" },          { key: "result", label: "结果", render: (row) => badge(row.result) },          { key: "id", label: "记录ID" },        ],        rows,        false,      )}      <div class="summary-wrap">${renderChineseSummary(summaryVars)}</div>    </div>    <div class="modal-foot">      <span></span>      <button class="btn" type="button" id="goRecords">查看记录</button>    </div>  `;  if (!modalEl.open) modalEl.showModal();  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());  document.querySelector("#goRecords").addEventListener("click", async () => {    modalEl.close();    state.view = "records";    await renderShell();  });}async function renderFunctionalTests() {  const projects = await getProjects();  const tasks = await api(`/api/functional-tasks${queryString({ project_id: state.filters.projectId })}`);  if (state.functionalTaskId && !tasks.some((item) => String(item.id) === String(state.functionalTaskId))) {    state.functionalTaskId = "";    localStorage.removeItem("functionalTaskId");  }  const selectedId = state.functionalTaskId || (tasks[0]?.id ? String(tasks[0].id) : "");  const selected = selectedId ? await api(`/api/functional-tasks/${selectedId}`) : null;  const accounts = await api(`/api/test-accounts${queryString({ project_id: selected?.project_id || state.filters.projectId })}`);  const projectName = (id) => (projects.find((item) => String(item.id) === String(id)) || {}).name || id;  contentEl().innerHTML = `    <div class="toolbar">      <div class="filters">        <div class="field compact"><label>项目</label><select id="functionalProjectFilter">${optionList(projects, "id", "name", state.filters.projectId)}</select></div>      </div>      <div class="actions">        ${isAdmin() ? `<button class="btn secondary" id="aiConfigBtn">AI配置</button><button class="btn" id="newFunctionalTask">新增迭代任务</button>` : ""}      </div>    </div>    <div class="functional-layout">      <section class="panel functional-list">        <div class="panel-title"><h3>迭代/需求任务</h3></div>        ${renderTable(          [            { key: "iteration_name", label: "迭代" },            { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },            { key: "status", label: "状态", render: (row) => badge(row.status) },            { key: "actions", label: "操作", render: (row) => `<div class="actions"><button class="btn secondary" data-open-functional="${row.id}">查看</button>${isAdmin() ? `<button class="btn danger" data-del-functional="${row.id}">删除</button>` : ""}</div>` },          ],          tasks,          false,        )}      </section>      <section class="panel functional-detail">        ${selected ? renderFunctionalTaskDetail(selected, accounts, projects) : `<div class="empty">暂无功能测试任务</div>`}      </section>    </div>  `;  document.querySelector("#functionalProjectFilter").addEventListener("change", async (event) => {    state.filters.projectId = event.target.value;    localStorage.setItem("projectId", state.filters.projectId);    state.functionalTaskId = "";    localStorage.removeItem("functionalTaskId");    await renderFunctionalTests();  });  document.querySelectorAll("[data-open-functional]").forEach((button) => {    button.addEventListener("click", async () => {      state.functionalTaskId = button.dataset.openFunctional;      localStorage.setItem("functionalTaskId", state.functionalTaskId);      await renderFunctionalTests();    });  });  document.querySelectorAll("[data-del-functional]").forEach((button) => {    button.addEventListener("click", () => {      deleteItem("/api/functional-tasks/" + button.dataset.delFunctional, renderFunctionalTests);    });  });  if (isAdmin()) {    document.querySelector("#newFunctionalTask")?.addEventListener("click", () => openFunctionalTaskForm(projects));    document.querySelector("#aiConfigBtn")?.addEventListener("click", openAiConfigForm);  }  bindFunctionalActions(selected, accounts, projects);}function renderFunctionalTaskDetail(task, accounts = [], projects = []) {  const latestSnapshot = task.snapshots?.[0];  const cases = task.cases || [];  const runs = task.runs || [];  const executable = cases.some((item) => item.automation_status === "approved" && item.ui_case_id);  return `    <div class="quick-start-bar" id="quickStartBar"><strong>⚡ 快捷开始</strong><span class="status-label" id="quickStartStatus">就绪</span></div>    <div class="panel-title functional-task-head">      <h3>${escapeHtml(task.iteration_name)}</h3>      <div class="actions functional-header-actions">        <button class="btn" id="executeFunctionalBtn" ${executable ? "" : "disabled"}>\u6267\u884c\u5df2\u786e\u8ba4\u7528\u4f8b</button>        ${isAdmin() ? actionMenu("\u66f4\u591a\u64cd\u4f5c", `<button class="btn secondary" id="bindFunctionalTaskAccount">\u9ed8\u8ba4\u8d26\u53f7</button><button class="btn secondary" id="uploadAxureBtn">\u4e0a\u4f20Axure</button><button class="btn secondary" id="uploadScreenshotBtn">\u4e0a\u4f20\u622a\u56fe</button><button class="btn secondary" id="addRequirementNoteBtn">\u8865\u5145\u9700\u6c42</button><button class="btn secondary" id="scanPageBtn">\u626b\u63cf\u9875\u9762</button><button class="btn secondary" id="generateCasesBtn">\u751f\u6210\u6d4b\u8bd5\u70b9</button>`) : ""}      </div>    </div>    <div class="functional-summary">      <div><span>项目</span><strong>${escapeHtml(task.project_name || task.project_id)}</strong></div>      <div><span>状态</span><strong>${badge(task.status)}</strong></div>      <div><span>默认测试账号</span><strong>${escapeHtml(task.account_profile_name || "跟随项目默认账号")}</strong></div>      <div><span>目标页面</span><strong>${escapeHtml(task.target_url)}</strong></div>      <div><span>Axure</span><strong>${task.axure_path ? "已上传" : "未上传"}</strong></div>    </div>    <details class="functional-requirement" open>      <summary>初始需求说明</summary>      <pre>${escapeHtml(task.requirement_text || "暂无需求说明")}</pre>    </details>    <details class="functional-requirement" open>      <summary>项目上下文（业务背景/本次迭代范围）</summary>      <div class="field">        <textarea id="functionalContext" rows="4" placeholder="例如：这是一个跨境电商订单管理系统，本次迭代涉及订单列表批量审核功能...">${escapeHtml(task.context || "")}</textarea>        <div class="actions" style="margin-top:8px">          <button class="btn secondary" id="saveContextBtn" type="button">保存上下文</button>        </div>      </div>    </details>    ${renderFunctionalMaterials(task)}    <div class="panel-title"><h3>测试点草稿</h3></div>    ${renderTable(      [        { key: "title", label: "测试点" },        { key: "priority", label: "优先级", render: (row) => badge(row.priority) },        { key: "automation_status", label: "自动化状态", render: (row) => badge(row.automation_status) },        { key: "quality_status", label: "执行检查", render: (row) => badge(row.quality_status || "unchecked") },        { key: "failure_count", label: "失败次数", render: (row) => escapeHtml(row.failure_count || 0) },        { key: "account_profile_name", label: "测试账号", render: (row) => escapeHtml(row.account_profile_name || "跟随任务") },        { key: "ui_case_id", label: "UI用例", render: (row) => (row.ui_case_id ? `#${row.ui_case_id}` : "-") },        {          key: "actions",          label: "操作",          render: (row) => `            <div class="actions functional-row-actions">              <button class="btn secondary" data-functional-case-detail="${row.id}">\u8be6\u60c5</button>              <button class="btn" data-execute-functional-case="${row.id}" ${row.automation_status === "approved" && row.ui_case_id ? "" : "disabled"}>\u6267\u884c</button>              ${isAdmin() ? actionMenu("\u66f4\u591a", `<button class="btn secondary" data-edit-functional-case="${row.id}">\u7f16\u8f91</button><button class="btn secondary" data-generate-ui="${row.id}">\u751f\u6210\u6b65\u9aa4</button><button class="btn secondary" data-preflight-functional="${row.id}" ${row.ui_case_id ? "" : "disabled"}>\u8bd5\u8dd1\u68c0\u67e5</button><button class="btn" data-approve-functional="${row.id}" ${row.ui_case_id ? "" : "disabled"}>\u786e\u8ba4</button>`) : ""}            </div>          `,        },      ],      cases,      false,    )}    <div class="functional-two-col">      <section>        <div class="panel-title"><h3>页面快照</h3></div>        ${latestSnapshot ? `<pre class="mini-log">${escapeHtml(short(latestSnapshot.dom_summary || "", 1600))}</pre>` : `<div class="empty">还没有扫描真实页面 DOM</div>`}      </section>      <section>        <div class="panel-title"><h3>执行记录</h3></div>        ${renderTable(          [            { key: "id", label: "ID" },            { key: "result", label: "结果", render: (row) => badge(row.result) },            { key: "passed_count", label: "通过" },            { key: "failed_count", label: "失败" },            { key: "execute_time", label: "执行时间" },            {              key: "actions",              label: "操作",              render: (row) => `<div class="actions functional-row-actions"><button class="btn secondary" data-functional-run-log="${row.id}">\u65e5\u5fd7</button>${actionMenu("\u66f4\u591a", `<button class="btn secondary" data-functional-run-shots="${row.id}">\u622a\u56fe</button><button class="btn secondary" data-functional-diagnose="${row.id}" ${row.result === "failed" ? "" : "disabled"}>\u8bca\u65ad</button>`)}</div>`,            },          ],          runs,          false,        )}      </section>    </div>  `;}function renderFunctionalMaterials(task) {  const screenshots = task.screenshots || [];  const notes = task.requirement_notes || [];  return `    <section class="functional-materials">      <div class="panel-title"><h3>需求材料</h3></div>      <div class="functional-two-col">        <section>          <div class="panel-title"><h3>产品截图</h3></div>          ${            screenshots.length              ? screenshots                  .map(                    (item, index) => `                      <div class="material-item">                        <div class="material-head">                          <strong>流程截图 ${index + 1} · #${item.id}</strong>                          <div class="actions">                            <button class="btn secondary" data-functional-shot="${item.id}">查看截图</button>                            ${isAdmin() ? `<button class="btn secondary" data-analyze-functional-shot="${item.id}">识别截图</button>` : ""}                            ${isAdmin() ? `<button class="btn secondary" data-move-shot="${item.id}" data-move-dir="-1" ${index === 0 ? "disabled" : ""}>上移</button><button class="btn secondary" data-move-shot="${item.id}" data-move-dir="1" ${index === screenshots.length - 1 ? "disabled" : ""}>下移</button>` : ""}                          </div>                        </div>                        <pre class="mini-log">${escapeHtml(item.analysis_result ? short(item.analysis_result, 1600) : "未识别")}</pre>                      </div>                    `,                  )                  .join("")              : `<div class="empty">还没有上传产品截图</div>`          }        </section>        <section>          <div class="panel-title"><h3>补充需求</h3></div>          ${            notes.length              ? notes                  .map(                    (item) => `                      <div class="material-item">                        <div class="material-head">                          <strong>#${item.id} ${escapeHtml(item.create_time || "")}</strong>                          ${                            isAdmin()                              ? `<div class="actions"><button class="btn secondary" data-edit-requirement-note="${item.id}">编辑</button><button class="btn danger" data-delete-requirement-note="${item.id}">删除</button></div>`                              : ""                          }                        </div>                        <pre class="mini-log">${escapeHtml(item.note_text || "")}</pre>                      </div>                    `,                  )                  .join("")              : `<div class="empty">还没有补充需求</div>`          }        </section>      </div>    </section>  `;}function bindFunctionalActions(task, accounts = [], projects = []) {  if (!task) return;  document.querySelector("#executeFunctionalBtn")?.addEventListener("click", () => openFunctionalExecuteForm(task, null, accounts, projects));  document.querySelectorAll("[data-functional-case-detail]").forEach((button) => {    const item = (task.cases || []).find((row) => row.id === Number(button.dataset.functionalCaseDetail));    button.addEventListener("click", () => showFunctionalCaseDetail(item));  });  document.querySelectorAll("[data-execute-functional-case]").forEach((button) => {    const item = (task.cases || []).find((row) => row.id === Number(button.dataset.executeFunctionalCase));    button.addEventListener("click", () => openFunctionalExecuteForm(task, item, accounts, projects));  });  document.querySelectorAll("[data-functional-run-log]").forEach((button) => {    const item = (task.runs || []).find((row) => row.id === Number(button.dataset.functionalRunLog));    button.addEventListener("click", () => showFunctionalRunLog(item));  });  document.querySelectorAll("[data-functional-run-shots]").forEach((button) => {    const item = (task.runs || []).find((row) => row.id === Number(button.dataset.functionalRunShots));    button.addEventListener("click", () => showFunctionalRunScreenshots(item));  });  document.querySelectorAll("[data-functional-diagnose]").forEach((button) => {    button.addEventListener("click", () => diagnoseFunctionalRun(Number(button.dataset.functionalDiagnose)));  });  document.querySelectorAll("[data-functional-shot]").forEach((button) => {    button.addEventListener("click", () => openProtectedFile(`/api/functional-screenshots/${button.dataset.functionalShot}/file`));  });  if (!isAdmin()) return;  document.querySelector("#bindFunctionalTaskAccount")?.addEventListener("click", () =>    openAccountBindingForm({      title: `设置任务默认账号：${task.iteration_name}`,      targetType: "functional_task",      targetId: task.id,      currentId: task.account_profile_id,      accounts,      projects,      emptyLabel: "跟随项目默认账号",      afterSave: renderFunctionalTests,    }),  );  document.querySelector("#uploadAxureBtn")?.addEventListener("click", () => openAxureUpload(task.id));    document.querySelector("#uploadScreenshotBtn")?.addEventListener("click", () => openFunctionalScreenshotUpload(task.id));  document.querySelector("#addRequirementNoteBtn")?.addEventListener("click", () => openRequirementNoteForm(task.id));  document.querySelector("#scanPageBtn")?.addEventListener("click", () => openFunctionalScanForm(task));  document.querySelector("#generateCasesBtn")?.addEventListener("click", () => generateFunctionalCases(task.id));  document.querySelectorAll("[data-analyze-functional-shot]").forEach((button) => {    button.addEventListener("click", () => analyzeFunctionalScreenshot(Number(button.dataset.analyzeFunctionalShot)));  });  document.querySelectorAll("[data-edit-requirement-note]").forEach((button) => {    const item = (task.requirement_notes || []).find((row) => row.id === Number(button.dataset.editRequirementNote));    button.addEventListener("click", () => openRequirementNoteForm(task.id, item));  });  document.querySelectorAll("[data-delete-requirement-note]").forEach((button) => {    button.addEventListener("click", () => deleteItem(`/api/functional-requirement-notes/${button.dataset.deleteRequirementNote}`, renderFunctionalTests));  });  document.querySelectorAll("[data-edit-functional-case]").forEach((button) => {    const item = (task.cases || []).find((row) => row.id === Number(button.dataset.editFunctionalCase));    button.addEventListener("click", () => openFunctionalCaseForm(item, accounts, projects));  });  document.querySelectorAll("[data-generate-ui]").forEach((button) => {    button.addEventListener("click", () => generateFunctionalUiSteps(Number(button.dataset.generateUi)));  });  document.querySelectorAll("[data-preflight-functional]").forEach((button) => {    const item = (task.cases || []).find((row) => row.id === Number(button.dataset.preflightFunctional));    button.addEventListener("click", () => preflightFunctionalCase(task, item, accounts, projects));  });  document.querySelectorAll("[data-approve-functional]").forEach((button) => {    button.addEventListener("click", () => approveFunctionalCase(Number(button.dataset.approveFunctional)));  });}
  document.querySelector("#saveContextBtn")?.addEventListener("click", async () => {
    const el = document.querySelector("#functionalContext");
    if (!el) return;
    const value = el.value.trim();
    const taskId = state.functionalTaskId;
    if (!taskId) { showToast("请先选择功能测试任务"); return; }
    try {
      const btn = document.querySelector("#saveContextBtn");
      btn.disabled = true; btn.textContent = "保存中...";
      await api("/api/functional-tasks/" + taskId + "/context", { method: "PUT", body: { context: value } });
      showToast("项目上下文已保存");
      state.functionalTaskId = taskId;
      await renderFunctionalTests();
    } catch (e) {
      showToast(e.message || "保存失败");
      document.querySelector("#saveContextBtn").disabled = false;
      document.querySelector("#saveContextBtn").textContent = "保存上下文";
    }
  });

function orderOptionCountsFromVariables(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, count]) => [String(key || "").trim(), Number(count)])
      .filter(([key, count]) => key && Number.isFinite(count) && count > 0)
      .map(([key, count]) => [key, Math.floor(count)]),
  );
}

function readOrderOptionCounts(container = document) {
  const counts = {};
  container.querySelectorAll("[data-order-option-key]").forEach((input) => {
    const key = String(input.dataset.orderOptionKey || "").trim();
    const count = Number(input.value);
    if (key && Number.isFinite(count) && count > 0) counts[key] = Math.floor(count);
  });
  return counts;
}

function renderOrderOptionPreview(options, selectedCounts = {}) {
  if (!options.length) {
    return `<div class="empty">未读取到可用订单 option，请刷新重试</div>`;
  }
  return `
    <div class="table-wrap">
      <table>
        <thead><tr><th>Option</th><th>价格</th><th>数量</th></tr></thead>
        <tbody>
          ${options
            .map((option) => {
              const key = String(option.key || option.id || option.name || "");
              const priceText = [option.price, option.unit].filter((item) => item !== undefined && item !== null && item !== "").join(" ");
              return `
                <tr>
                  <td>${escapeHtml(option.label || option.name || key)}</td>
                  <td>${escapeHtml(priceText || "-")}</td>
                  <td><input type="number" min="1" step="1" data-order-option-key="${escapeHtml(key)}" value="${escapeHtml(selectedCounts[key] || "")}" /></td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function openOrderQuoteRunForm(flow, fields) {
  let variables = {};
  try {
    variables = parseJsonText(flow.variables || "{}", {});
  } catch {
    showToast("脚本变量不是合法 JSON");
    return;
  }
  variables = sanitizeScriptVariables(flow.scriptType, variables, flow);
  const values = {
    ...paramFormValues(fields, variables),
    __save_defaults: false,
  };
  const body = [...fields, { name: "__save_defaults", label: "保存为默认值", type: "checkbox", default: false }]
    .map((field) => renderFormField(field, values?.[field.name] ?? field.default ?? ""))
    .join("");
  const initialCounts = orderOptionCountsFromVariables(variables.order_option_counts);
  modalEl.innerHTML = `
    <form id="orderQuoteRunForm">
      <div class="modal-head">
        <h3>${escapeHtml(`执行 ${flow.name || "数据脚本"}`)}</h3>
        <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">${body}</div>
        <details class="functional-requirement" open>
          <summary>订单 option（可选）</summary>
          <div id="orderOptionPreview"><div class="empty">正在读取订单 option...</div></div>
          <div class="actions" style="margin-top:10px">
            <button class="btn secondary" id="refreshOrderOptions" type="button">刷新选项</button>
          </div>
        </details>
      </div>
      <div class="modal-foot"><span></span><button class="btn" type="submit">执行</button></div>
    </form>
  `;
  modalEl.showModal();
  const form = document.querySelector("#orderQuoteRunForm");
  const previewEl = document.querySelector("#orderOptionPreview");
  function runtimeVariables(includeCurrentCounts = true) {
    const data = readForm(form);
    const next = sanitizeScriptVariables(flow.scriptType, mergeParamValues(variables, fields, data), flow);
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
  document.querySelector("#refreshOrderOptions").addEventListener("click", refreshOptions);
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

function openOemSampleOrderRunForm(flow) {
  modalEl.innerHTML = `
    <form id="oemSampleOrderForm">
      <div class="modal-head">
        <h3>${escapeHtml(`执行 ${flow.name || "数据脚本"}`)}</h3>
        <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field">
            <label>询价单号</label>
            <div style="display:flex;gap:8px">
              <input name="order_sn" id="oemOrderSn" placeholder="如 X20260615132111-15-OEM" required style="flex:1" />
              <button class="btn secondary" type="button" id="fetchQuoteBtn">查询</button>
            </div>
          </div>
        </div>
        <div id="quoteResultArea" style="margin-top:12px">
          <div class="empty">输入询价单号后点击「查询」</div>
        </div>
      </div>
      <div class="modal-foot">
        <span></span>
        <button class="btn" type="submit" id="submitOemSampleOrder" disabled>执行样品单</button>
      </div>
    </form>
  `;
  modalEl.showModal();

  const form = document.querySelector("#oemSampleOrderForm");
  const detailInput = document.querySelector("#oemOrderSn");
  const fetchBtn = document.querySelector("#fetchQuoteBtn");
  const submitBtn = document.querySelector("#submitOemSampleOrder");
  const resultArea = document.querySelector("#quoteResultArea");

  let skuItems = [];

  document.querySelector("#closeModal").addEventListener("click", async () => {
    modalEl.close();
    if (state.view === "dataScripts" && !state.factory.editing) {
      await renderDataScripts();
    }
  });

  fetchBtn.addEventListener("click", async () => {
    const orderSn = detailInput.value.trim();
    if (!orderSn) { showToast("请输入询价单号"); return; }
    fetchBtn.disabled = true; fetchBtn.textContent = "查询中...";
    resultArea.innerHTML = `<div class="empty">正在查询报价详情...</div>`;
    try {
      const resp = await api(`/api/oem/inquiry-full?order_sn=${encodeURIComponent(orderSn)}`);
      const data = resp.data || {};
      if (!data || Object.keys(data).length === 0) {
        resultArea.innerHTML = `<div class="alert warn">未查到该询价单的信息，请检查单号是否正确</div>`;
        submitBtn.disabled = true; return;
      }
      // 从 list 中提取第一条记录的 sku_detail
      const records = data.list || [];
      const first = records[0] || {};
      const rawList = first.sku_detail || first.sku_list || first.skuInfo || first.details || first.items || [];
      if (!rawList.length) {
        resultArea.innerHTML = `<div class="alert warn">该询价单暂无 SKU 明细数据</div>`;
        submitBtn.disabled = true; return;
      }
      const detailId = first.id || data.detail_id || "";
      // 从 quoteDetail 提取样品/大货明细
      const quoteDetail = first.quote_detail || data.quote_detail || {};
      const samplesInfo = quoteDetail.samples_info || {};
      const largeInfo = quoteDetail.large_info || {};
      // 建立 sku 名称 → 样品字段映射
      const sampleSkuMap = {};
      for (const s of (samplesInfo.skus || [])) {
        if (s.sku) sampleSkuMap[s.sku] = s;
      }
      // 建立 sku 名称 → 大货字段映射
      const largeSkuMap = {};
      for (const s of (largeInfo.skus || [])) {
        if (s.sku) largeSkuMap[s.sku] = s;
      }
      skuItems = rawList.map((item, index) => {
        const skuId = item.goods_sku_id || item.sku_id || item.skuId || item.id || `SKU-${index + 1}`;
        const skuName = item.sku || item.sku_name || item.skuName || item.goods_name || item.name || "";
        // 按 sku 名称匹配样品/大货数据
        const sSku = sampleSkuMap[skuName] || {};
        const lSku = largeSkuMap[skuName] || {};
        return {
          _index: index, _checked: true, _raw: item, _detail_id: detailId,
          sku_id: skuId, sku_name: skuName,
          num: item.num || item.quantity || item.count || 1,
          /** 样品信息 */
          sample_can: sSku.can_proofing ?? (item.can_sample || item.can_make_sample || item.is_sample || ""),
          sample_fee: sSku.samples_price || item.samples_price || item.sample_fee || item.samplePrice || item.sample_price || "",
          sample_refund: sSku.samples_price_return || item.sample_refund || item.sampleReturn || item.sample_return || "",
          sample_other_fee: samplesInfo.samples_other_fee || item.sample_other_fee || item.otherSampleFee || item.other_sample_fee || "",
          sample_shipping: samplesInfo.samples_freight || item.sample_shipping || item.sampleShipping || item.sample_freight || "",
          sample_lead_time: samplesInfo.samples_delivery_time || item.sample_lead_time || item.sampleLeadTime || item.sample_delivery || "",
          /** 大货信息 */
          bulk_moq: lSku.large_min_quantity || item.large_min_quantity || item.moq || item.bulk_moq || item.min_order_qty || item.minOrderQty || "",
          bulk_price: lSku.large_price || item.large_price || item.bulk_price || item.bulkPrice || item.unit_price || item.unitPrice || item.price || "",
          bulk_other_fee: largeInfo.large_other_fee || item.bulk_other_fee || item.bulkOtherFee || item.other_fee || item.otherFee || "",
          bulk_deposit_ratio: largeInfo.large_deposit_rate || item.deposit_ratio || item.depositRatio || item.deposit || "",
          bulk_shipping: largeInfo.large_freight || item.bulk_shipping || item.bulkShipping || item.bulk_freight || item.freight || "",
          bulk_lead_time: largeInfo.large_delivery_time || item.bulk_lead_time || item.bulkLeadTime || item.delivery_time || item.deliveryTime || "",
        };
      });
      detailInput.readOnly = true; submitBtn.disabled = false;
      renderQuoteResult(data);
      showToast(`已获取 ${skuItems.length} 个 SKU`);
    } catch (error) {
      resultArea.innerHTML = `<div class="alert error">查询失败：${escapeHtml(error.message)}</div>`;
      submitBtn.disabled = true;
    } finally {
      fetchBtn.textContent = "重新查询"; fetchBtn.disabled = false;
    }
  });

  function renderQuoteResult(data) {
    let infoHtml = "";
    const first = (data.list || [])[0] || {};
    const qd = first.quote_detail || data.quote_detail || {};
    const hope = qd.hope_info || {};
    // 基本信息字段：优先从 hope_info / quote_detail / first / data 取
    const infoFields = {
      order_sn: "询价单号", goods_name: "商品名称", goods_no: "商品编号",
      status: "状态", status_name: "状态", factory_name: "工厂名称",
      factory_city: "工厂城市", factory_province: "工厂省份",
      factory_url: "工厂链接", samples_price: "样品总价",
      hope_min_price: "期望最低价", hope_max_price: "期望最高价", hope_futures: "期望交期",
      samples_other_fee: "样品其他费用", samples_freight: "样品运费",
      samples_delivery_time: "打样货期(天)",
      large_other_fee: "大货其他费用", large_freight: "大货运费(元)",
      large_delivery_time: "大货货期(天)", large_deposit_rate: "定金比例(%)",
      remark: "备注", quote_at: "报价时间",
    };
    const infoParts = [];
    for (const [key, label] of Object.entries(infoFields)) {
      const val = hope[key] ?? qd.samples_info?.[key] ?? qd.large_info?.[key] ?? first[key] ?? data[key] ?? "";
      if (val !== "" && val !== null && val !== undefined) {
        infoParts.push(`<div><span>${label}</span><strong>${escapeHtml(String(val))}</strong></div>`);
      }
    }
    if (infoParts.length) infoHtml = `<div class="functional-summary" style="margin-bottom:14px">${infoParts.join("")}</div>`;

    const sh = `<th style="padding:6px 8px;text-align:left;white-space:nowrap">能否打样</th><th style="padding:6px 8px;text-align:left;white-space:nowrap">打样费用</th><th style="padding:6px 8px;text-align:left;white-space:nowrap">样品费退还</th><th style="padding:6px 8px;text-align:left;white-space:nowrap">其他费用</th><th style="padding:6px 8px;text-align:left;white-space:nowrap">样品运费</th><th style="padding:6px 8px;text-align:left;white-space:nowrap">打样货期</th>`;
    const bh = `<th style="padding:6px 8px;text-align:left;white-space:nowrap">起订量</th><th style="padding:6px 8px;text-align:left;white-space:nowrap">大货单价(元)</th><th style="padding:6px 8px;text-align:left;white-space:nowrap">其他费用(元)</th><th style="padding:6px 8px;text-align:left;white-space:nowrap">定金比例</th><th style="padding:6px 8px;text-align:left;white-space:nowrap">大货运费(元)</th><th style="padding:6px 8px;text-align:left;white-space:nowrap">大货货期</th>`;

    const tbody = skuItems.map((it) => `<tr><td style="padding:6px 8px"><input type="checkbox" data-sku-check="${it._index}" ${it._checked?"checked":""} /></td><td style="padding:6px 8px;font-weight:600">${escapeHtml(String(it.sku_id))}</td><td style="padding:6px 8px">${it.sku_name?escapeHtml(it.sku_name):"-"}</td><td style="padding:6px 8px"><input name="sku_num_${it._index}" type="number" min="1" value="${escapeHtml(it.num)}" style="width:70px;padding:4px 6px;border:1px solid var(--border);border-radius:4px" /></td><td style="padding:6px 8px;text-align:center">${it.sample_can?escapeHtml(String(it.sample_can)):"-"}</td><td style="padding:6px 8px;text-align:right">${it.sample_fee?escapeHtml(String(it.sample_fee)):"-"}</td><td style="padding:6px 8px;text-align:center">${it.sample_refund?escapeHtml(String(it.sample_refund)):"-"}</td><td style="padding:6px 8px;text-align:right">${it.sample_other_fee?escapeHtml(String(it.sample_other_fee)):"-"}</td><td style="padding:6px 8px;text-align:right">${it.sample_shipping?escapeHtml(String(it.sample_shipping)):"-"}</td><td style="padding:6px 8px;text-align:center">${it.sample_lead_time?escapeHtml(String(it.sample_lead_time)):"-"}</td><td style="padding:6px 8px;text-align:center">${it.bulk_moq?escapeHtml(String(it.bulk_moq)):"-"}</td><td style="padding:6px 8px;text-align:right">${it.bulk_price?escapeHtml(String(it.bulk_price)):"-"}</td><td style="padding:6px 8px;text-align:right">${it.bulk_other_fee?escapeHtml(String(it.bulk_other_fee)):"-"}</td><td style="padding:6px 8px;text-align:center">${it.bulk_deposit_ratio?escapeHtml(String(it.bulk_deposit_ratio)):"-"}</td><td style="padding:6px 8px;text-align:right">${it.bulk_shipping?escapeHtml(String(it.bulk_shipping)):"-"}</td><td style="padding:6px 8px;text-align:center">${it.bulk_lead_time?escapeHtml(String(it.bulk_lead_time)):"-"}</td></tr>`).join("");

    resultArea.innerHTML = `${infoHtml}<div class="panel-title" style="margin-bottom:8px"><h4>SKU 明细</h4></div><div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px"><thead><tr style="background:var(--bg-muted)"><th style="padding:6px 8px;text-align:left">选择</th><th style="padding:6px 8px;text-align:left">SKU ID</th><th style="padding:6px 8px;text-align:left">名称</th><th style="padding:6px 8px;text-align:left">数量</th>${sh}${bh}</tr></thead><tbody>${tbody}</tbody></table></div><div style="margin-top:8px;color:var(--muted);font-size:12px">☑ 勾选的 SKU 将提交为样品单，取消勾选则跳过</div>`;

    document.querySelectorAll("[data-sku-check]").forEach((cb) => {
      cb.addEventListener("change", () => { const idx = parseInt(cb.dataset.skuCheck,10); const item = skuItems.find((i)=>i._index===idx); if (item) item._checked = cb.checked; });
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const orderSn = detailInput.value.trim();
    const checked = skuItems.filter((item) => item._checked);
    if (!orderSn || !checked.length) { showToast("请至少勾选一个 SKU"); return; }
    const skuList = checked.map((item) => {
      const numInput = form.querySelector(`[name="sku_num_${item._index}"]`);
      const num = numInput ? parseInt(numInput.value, 10) || 1 : item.num;
      const skuId = parseInt(String(item.sku_id), 10);
      return { sku_id: isNaN(skuId) ? item.sku_id : skuId, num };
    });
    const detailId = skuItems[0]?._detail_id || "";
    const variables = { order_sn: orderSn, inquiry_detail_id: detailId, sku_list: JSON.stringify(skuList) };
    let flowVariables = {};
    try { flowVariables = parseJsonText(flow.variables || "{}", {}); } catch {}
    const merged = { ...flowVariables, ...variables };
    try { showToast("正在执行样品单..."); await runSavedFlow(flow, merged); } catch (error) { showToast(error.message); }
  });
}

function openOemFullInquiryFlowRunForm(flow) {
  let variables = {};
  try { variables = parseJsonText(flow.variables || "{}", {}); } catch { showToast("脚本变量不是合法 JSON"); return; }
  const fields = (SCRIPT_PARAM_SCHEMAS.oem_full_inquiry_flow || []);
  const formFields = fields.filter((f) => f.type !== "section" && f.type !== "factory-urls-dynamic" && f.type !== "sku-dynamic" && f.type !== "goods-class-select");
  variables = sanitizeScriptVariables(flow.scriptType, variables, flow);
  const values = { ...paramFormValues(formFields, variables), factory_urls: variables.factory_urls || "", __save_defaults: false };

  // 报价阶段按 factory_urls 行数动态展开多组（每工厂独立 8 个金额字段）
  const QUOTE_SECTION_LABEL = "报价阶段";
  const QUOTE_FIELD_NAMES = ["samples_price","large_price","large_other_fee","large_freight",
    "large_delivery_time","large_deposit_rate","real_samples_price","real_large_price"];
  const quoteFieldDefs = fields.filter((f) => QUOTE_FIELD_NAMES.includes(f.name));
  const factoryQuotesStored = Array.isArray(variables.factory_quotes) ? variables.factory_quotes : [];

  // 分组：报价阶段标记 isQuote，其下 8 个金额字段不直接渲染（改为按工厂展开）
  const groups = [];
  let current = { label: "基础参数", fields: [], isQuote: false };
  for (const f of fields) {
    if (f.type === "section") {
      if (current.fields.length || current.isQuote) groups.push(current);
      current = { label: f.label, fields: [], isQuote: f.label === QUOTE_SECTION_LABEL };
    } else {
      if (current.isQuote && QUOTE_FIELD_NAMES.includes(f.name)) continue;
      current.fields.push(f);
    }
  }
  if (current.fields.length || current.isQuote) groups.push(current);

  // 缓存每工厂已填值（重渲染时保留）
  let fqCache = {};
  for (let i = 0; i < factoryQuotesStored.length; i++) {
    if (factoryQuotesStored[i] && typeof factoryQuotesStored[i] === "object") {
      fqCache[i] = { ...factoryQuotesStored[i] };
    }
  }

  function renderQuoteGroups(factoryCount) {
    if (!factoryCount) return `<div class="empty">请先添加工厂链接</div>`;
    let html = "";
    for (let i = 0; i < factoryCount; i++) {
      const cached = fqCache[i] || {};
      html += `<details open class="factory-quote-group"><summary>工厂${i + 1}报价</summary><div class="form-grid">`;
      for (const fdef of quoteFieldDefs) {
        const fieldDef = { ...fdef, name: `__fq_${i}__${fdef.name}` };
        const val = cached[fdef.name] ?? values[fdef.name] ?? fdef.default ?? "";
        html += renderFormField(fieldDef, val);
      }
      html += `</div></details>`;
    }
    return html;
  }

  // 工厂链接动态行渲染
  function renderFactoryUrlRow(idx, value, canDelete) {
    return `<div class="factory-url-row" data-idx="${idx}">
      <input name="factory_url_${idx}" type="text" value="${escapeHtml(value)}" placeholder="https://..." />
      ${canDelete ? `<button class="btn secondary delete-factory-url" type="button" data-idx="${idx}">-</button>` : ""}
    </div>`;
  }

  function renderFactoryUrlsDynamic() {
    const urls = (values.factory_urls || "").split("\n").map(s => s.trim()).filter(Boolean);
    const rows = urls.length ? urls : [""];
    let html = `<div class="field"><label>工厂链接</label><div id="factoryUrlsContainer">`;
    for (let i = 0; i < rows.length; i++) {
      html += renderFactoryUrlRow(i, rows[i], i > 0);
    }
    html += `</div><button class="btn secondary" type="button" id="addFactoryUrlBtn">+ 添加工厂链接</button></div>`;
    return html;
  }

  // SKU 动态行渲染
  function renderSkuRow(idx, skuName, skuNum, canDelete) {
    return `<div class="factory-url-row sku-row" data-idx="${idx}">
      <input name="sku_name_${idx}" type="text" value="${escapeHtml(skuName)}" placeholder="SKU名称" />
      <input name="sku_num_${idx}" type="number" value="${escapeHtml(String(skuNum ?? ""))}" placeholder="数量" style="width:80px" />
      ${canDelete ? `<button class="btn secondary delete-sku-row" type="button" data-idx="${idx}">-</button>` : ""}
    </div>`;
  }

  function renderSkuDynamic() {
    let skuList = [];
    const raw = values.sku_info;
    if (Array.isArray(raw)) {
      skuList = raw;
    } else if (typeof raw === "string" && raw.trim()) {
      try { skuList = JSON.parse(raw); } catch { skuList = []; }
    }
    if (!skuList.length) skuList = [{ sku: "sku1", num: 1 }];
    let html = `<div class="field"><label>SKU列表</label><div id="skuContainer">`;
    for (let i = 0; i < skuList.length; i++) {
      const item = skuList[i] || {};
      html += renderSkuRow(i, item.sku || "", item.num ?? "", i > 0);
    }
    html += `</div><button class="btn secondary" type="button" id="addSkuBtn">+ 添加SKU</button></div>`;
    return html;
  }

  // 商品类型下拉（从后端 /api/oem/goods-class-list 拉取选项）
  let goodsClassCache = null;
  async function loadGoodsClassList() {
    if (goodsClassCache) return goodsClassCache;
    try {
      const res = await api("/api/oem/goods-class-list");
      if (res && res.success && Array.isArray(res.data)) {
        goodsClassCache = res.data;
        return goodsClassCache;
      }
    } catch (e) { /* ignore */ }
    goodsClassCache = [];
    return goodsClassCache;
  }

  function renderGoodsClassSelect(field, value) {
    const v = String(value ?? field.default ?? "");
    return `<div class="field"><label>${escapeHtml(field.label)}</label><select name="${escapeHtml(field.name)}" data-goods-class-select><option value="${escapeHtml(v)}" selected>加载中...</option></select></div>`;
  }

  async function fillGoodsClassSelects() {
    const list = await loadGoodsClassList();
    form.querySelectorAll("[data-goods-class-select]").forEach((sel) => {
      const currentVal = String(sel.value || "");
      const optHtml = list.map((item) => {
        const label = item.parent_name ? `${item.parent_name} / ${item.class_name}` : item.class_name;
        const val = String(item.id);
        const selected = val === currentVal ? "selected" : "";
        return `<option value="${escapeHtml(val)}" ${selected}>${escapeHtml(label)}</option>`;
      }).join("");
      sel.innerHTML = optHtml || `<option value="">无分类数据</option>`;
    });
  }

  let bodyHtml = "";
  for (const g of groups) {
    bodyHtml += `<details class="functional-requirement" ${g.isQuote ? "open" : ""}><summary>${escapeHtml(g.label)}</summary>`;
    if (g.isQuote) {
      bodyHtml += `<div class="factory-quote-container" id="factoryQuoteContainer">__FACTORY_QUOTE_PLACEHOLDER__</div>`;
    } else {
      bodyHtml += `<div class="form-grid">`;
      for (const f of g.fields) {
        if (f.type === "factory-urls-dynamic") {
          bodyHtml += renderFactoryUrlsDynamic();
        } else if (f.type === "sku-dynamic") {
          bodyHtml += renderSkuDynamic();
        } else if (f.type === "goods-class-select") {
          bodyHtml += renderGoodsClassSelect(f, values[f.name] ?? f.default ?? "");
        } else {
          bodyHtml += renderFormField(f, values[f.name]);
        }
      }
      bodyHtml += `</div>`;
    }
    bodyHtml += `</details>`;
  }
  bodyHtml += renderFormField({ name: "__save_defaults", label: "保存为默认值", type: "checkbox", default: false }, false);
  modalEl.innerHTML = `
    <form id="oemFullInquiryFlowForm">
      <div class="modal-head">
        <h3>${escapeHtml(`执行 ${flow.name || "OEM询价单全流程"}`)}</h3>
        <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body">${bodyHtml}</div>
      <div class="modal-foot"><span></span><button class="btn" type="submit">执行</button></div>
    </form>
  `;
  modalEl.showModal();
  bindUploadButtons();
  fillGoodsClassSelects();
  const form = document.querySelector("#oemFullInquiryFlowForm");

  // 同步 SKU 动态行到隐藏的 sku_info 字段（JSON 字符串）
  function syncSkuToHidden() {
    const inputs = form.querySelectorAll("#skuContainer .sku-row");
    const skuList = [];
    inputs.forEach((row) => {
      const nameInput = row.querySelector('input[name^="sku_name_"]');
      const numInput = row.querySelector('input[name^="sku_num_"]');
      const sku = String(nameInput?.value || "").trim();
      const num = Number(numInput?.value || 0);
      if (sku) skuList.push({ sku, num });
    });
    let hidden = form.querySelector('[name="sku_info"]');
    if (!hidden) {
      hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "sku_info";
      form.appendChild(hidden);
    }
    hidden.value = JSON.stringify(skuList);
  }

  function renumberSkuRows() {
    const rows = form.querySelectorAll("#skuContainer .sku-row");
    rows.forEach((row, i) => {
      row.dataset.idx = i;
      const nameInput = row.querySelector('input[name^="sku_name_"]');
      const numInput = row.querySelector('input[name^="sku_num_"]');
      if (nameInput) nameInput.name = `sku_name_${i}`;
      if (numInput) numInput.name = `sku_num_${i}`;
      const delBtn = row.querySelector(".delete-sku-row");
      if (delBtn) {
        delBtn.dataset.idx = i;
        delBtn.style.display = i === 0 ? "none" : "";
      } else if (i > 0) {
        const btn = document.createElement("button");
        btn.className = "btn secondary delete-sku-row";
        btn.type = "button";
        btn.dataset.idx = i;
        btn.textContent = "-";
        btn.addEventListener("click", () => onDeleteSku(i));
        row.appendChild(btn);
      }
    });
  }

  function onDeleteSku(idx) {
    const row = form.querySelector(`#skuContainer .sku-row[data-idx="${idx}"]`);
    if (row) row.remove();
    renumberSkuRows();
    syncSkuToHidden();
  }

  // 同步动态行输入到隐藏的 factory_urls 字段（保持字符串格式）
  function syncFactoryUrlsToHidden() {
    const inputs = form.querySelectorAll("#factoryUrlsContainer input[name^='factory_url_']");
    const urls = [];
    inputs.forEach((inp) => {
      const v = String(inp.value || "").trim();
      if (v) urls.push(v);
    });
    let hidden = form.querySelector('[name="factory_urls"]');
    if (!hidden) {
      hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "factory_urls";
      form.appendChild(hidden);
    }
    hidden.value = urls.join("\n");
  }

  // 重新编号所有工厂链接行（删除后索引前移）
  function renumberFactoryUrlRows() {
    const rows = form.querySelectorAll("#factoryUrlsContainer .factory-url-row");
    rows.forEach((row, i) => {
      row.dataset.idx = i;
      const input = row.querySelector("input");
      if (input) input.name = `factory_url_${i}`;
      const delBtn = row.querySelector(".delete-factory-url");
      if (delBtn) {
        delBtn.dataset.idx = i;
        delBtn.style.display = i === 0 ? "none" : "";
      } else if (i > 0) {
        // 第 0 行原本无删除按钮，重编号后若 i>0 需补按钮
        const btn = document.createElement("button");
        btn.className = "btn secondary delete-factory-url";
        btn.type = "button";
        btn.dataset.idx = i;
        btn.textContent = "-";
        btn.addEventListener("click", () => onDeleteFactoryUrl(i));
        row.appendChild(btn);
      }
    });
  }

  // 删除指定索引的工厂链接行：fqCache 前移一位
  function onDeleteFactoryUrl(idx) {
    const maxIdx = Object.keys(fqCache).reduce((m, k) => Math.max(m, Number(k)), -1);
    for (let i = idx; i < maxIdx; i++) {
      fqCache[i] = fqCache[i + 1] ? { ...fqCache[i + 1] } : {};
    }
    delete fqCache[maxIdx];
    const row = form.querySelector(`#factoryUrlsContainer .factory-url-row[data-idx="${idx}"]`);
    if (row) row.remove();
    renumberFactoryUrlRows();
    syncFactoryUrlsToHidden();
    refreshQuoteGroups();
  }

  // 刷新报价阶段子块：读隐藏 factory_urls + 保留已填值
  function refreshQuoteGroups() {
    const hidden = form.querySelector('[name="factory_urls"]');
    const urls = hidden ? hidden.value : "";
    const factoryCount = urls.split("\n").map(s => s.trim()).filter(Boolean).length;
    const newCache = {};
    for (let i = 0; i < factoryCount; i++) {
      const entry = {};
      for (const fn of QUOTE_FIELD_NAMES) {
        const input = form.querySelector(`[name="__fq_${i}__${fn}"]`);
        if (input && input.value !== "" && input.value !== null && input.value !== undefined) {
          entry[fn] = input.value;
        }
      }
      newCache[i] = entry;
    }
    for (let i = 0; i < factoryCount; i++) {
      fqCache[i] = { ...(factoryQuotesStored[i] || {}), ...(fqCache[i] || {}), ...newCache[i] };
    }
    Object.keys(fqCache).forEach((k) => {
      if (Number(k) >= factoryCount) delete fqCache[k];
    });
    const container = document.querySelector("#factoryQuoteContainer");
    if (container) container.innerHTML = renderQuoteGroups(factoryCount);
  }

  // 初始化：同步隐藏字段 + 刷新报价组
  syncFactoryUrlsToHidden();
  refreshQuoteGroups();

  // 添加工厂链接按钮
  const addBtn = form.querySelector("#addFactoryUrlBtn");
  if (addBtn) {
    addBtn.addEventListener("click", () => {
      const container = form.querySelector("#factoryUrlsContainer");
      const rows = container.querySelectorAll(".factory-url-row");
      const newIdx = rows.length;
      container.insertAdjacentHTML("beforeend", renderFactoryUrlRow(newIdx, "", true));
      syncFactoryUrlsToHidden();
      refreshQuoteGroups();
      const newDelBtn = container.querySelector(`.factory-url-row[data-idx="${newIdx}"] .delete-factory-url`);
      if (newDelBtn) newDelBtn.addEventListener("click", () => onDeleteFactoryUrl(newIdx));
    });
  }

  // 绑定已有删除按钮
  form.querySelectorAll(".delete-factory-url").forEach((btn) => {
    btn.addEventListener("click", () => onDeleteFactoryUrl(Number(btn.dataset.idx)));
  });

  // 监听工厂链接输入变化：同步隐藏字段 + 刷新报价组
  form.addEventListener("input", (e) => {
    if (e.target.name && e.target.name.startsWith("factory_url_")) {
      syncFactoryUrlsToHidden();
      refreshQuoteGroups();
    }
    if (e.target.name && (e.target.name.startsWith("sku_name_") || e.target.name.startsWith("sku_num_"))) {
      syncSkuToHidden();
    }
  });

  // 添加 SKU 按钮
  const addSkuBtn = form.querySelector("#addSkuBtn");
  if (addSkuBtn) {
    addSkuBtn.addEventListener("click", () => {
      const container = form.querySelector("#skuContainer");
      const rows = container.querySelectorAll(".sku-row");
      const newIdx = rows.length;
      container.insertAdjacentHTML("beforeend", renderSkuRow(newIdx, "", 1, true));
      syncSkuToHidden();
      const newDelBtn = container.querySelector(`.sku-row[data-idx="${newIdx}"] .delete-sku-row`);
      if (newDelBtn) newDelBtn.addEventListener("click", () => onDeleteSku(newIdx));
    });
  }

  // 绑定已有 SKU 删除按钮
  form.querySelectorAll(".delete-sku-row").forEach((btn) => {
    btn.addEventListener("click", () => onDeleteSku(Number(btn.dataset.idx)));
  });

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
      const urls = data.factory_urls || "";
      const factoryCount = urls.split("\n").map(s => s.trim()).filter(Boolean).length;
      const fqList = [];
      for (let i = 0; i < factoryCount; i++) {
        const entry = {};
        for (const fn of QUOTE_FIELD_NAMES) {
          const k = `__fq_${i}__${fn}`;
          const v = data[k];
          if (v !== undefined && v !== null && v !== "") {
            entry[fn] = fn === "large_delivery_time" ? Number(v) : String(v);
          }
        }
        fqList.push(entry);
      }
      syncSkuToHidden();
      const merged = mergeParamValues(variables, formFields, data);
      merged.factory_urls = urls;
      // sku_info: 从隐藏字段 JSON 解析为数组
      if (data.sku_info) {
        try {
          const skuArr = JSON.parse(data.sku_info);
          if (Array.isArray(skuArr) && skuArr.length) merged.sku_info = skuArr;
        } catch { /* ignore */ }
      }
      // 清理旧 SKU 字段残留
      delete merged.sku1; delete merged.sku2; delete merged.sku3;
      delete merged.sku1_num; delete merged.sku2_num; delete merged.sku3_num;
      if (fqList.length) merged.factory_quotes = fqList;
      else delete merged.factory_quotes;
      const runtimeVariables = sanitizeScriptVariables(flow.scriptType, merged, flow);
      if (data.__save_defaults) saveFlowVariables(flow, runtimeVariables);
      showToast("正在执行OEM询价单全流程...");
      await runSavedFlow(flow, runtimeVariables);
    } catch (error) {
      showToast(error.message);
    }
  });
}

function openOemSampleFullFlowRunForm(flow) {
  let variables = {};
  try { variables = parseJsonText(flow.variables || "{}", {}); } catch { showToast("脚本变量不是合法 JSON"); return; }
  const fields = (SCRIPT_PARAM_SCHEMAS.oem_sample_full_flow || []);
  const formFields = fields.filter((f) => f.type !== "section" && f.name !== "check_report_images");
  variables = sanitizeScriptVariables(flow.scriptType, variables, flow);
  const values = { ...paramFormValues(formFields, variables), __save_defaults: false };
  // 按 section 分组
  const groups = [];
  let current = null;
  for (const f of fields) {
    if (f.type === "section") {
      if (current) groups.push(current);
      current = { label: f.label, fields: [] };
    } else if (current && f.name !== "check_report_images") {
      current.fields.push(f);
    }
  }
  if (current) groups.push(current);

  let adminHtml = "";
  for (const g of groups) {
    if (!g.fields.length) continue;
    // 确认和报价阶段默认展开，验货和上架阶段默认折叠
    const isQuoteOrConfirm = g.label.includes("确认") || g.label.includes("报价");
    adminHtml += `<details class="functional-requirement" ${isQuoteOrConfirm ? "open" : ""}><summary>${escapeHtml(g.label)}</summary><div class="form-grid">`;
    for (const f of g.fields) adminHtml += renderFormField(f, values[f.name]);
    adminHtml += `</div></details>`;
  }

  modalEl.innerHTML = `
    <form id="oemSampleFullFlowForm">
      <div class="modal-head">
        <h3>${escapeHtml(`执行 ${flow.name || "OEM样品单全流程"}`)}</h3>
        <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field">
            <label>询价单ID(或样品单号)</label>
            <div style="display:flex;gap:8px">
              <input name="order_sn" id="ffOrderSn" placeholder="输入询价单明细ID 或 Y开头的样品单号" required style="flex:1" />
              <button class="btn secondary" type="button" id="ffFetchBtn">查询 SKU</button>
            </div>
          </div>
        </div>
        <div id="ffSkuArea" style="margin-top:12px">
          <div class="empty">输入询价单ID后点击「查询 SKU」获取商品列表</div>
        </div>
        <div id="ffAdminArea" style="margin-top:16px;display:none">
          <div class="panel-title" style="margin-bottom:8px"><h4>后台流程参数</h4></div>
          ${adminHtml}
          <details class="functional-requirement" id="checkImagesSection">
            <summary>验货图片上传</summary>
            <div class="form-grid">
              <div class="field">
                <label>验货图片</label>
                <div class="upload-field">
                  <input type="file" id="checkImageFileInput" accept="image/*" multiple style="display:none" />
                  <input type="hidden" name="check_report_images" id="checkReportImages" value="" />
                  <button class="btn secondary" type="button" id="checkImageSelectBtn">选择图片(可多选)</button>
                </div>
                <div id="checkImagePreview" style="margin-top:6px;display:flex;flex-wrap:wrap;gap:8px"></div>
                <div style="color:var(--muted);font-size:12px;margin-top:4px">支持多张图片，选择后自动上传</div>
              </div>
              <div class="field">
                <label>验货备注</label>
                <input name="check_report_remark" value="${escapeHtml(values.check_report_remark || '')}" placeholder="选填" />
              </div>
            </div>
          </details>
          ${renderFormField({ name: "__save_defaults", label: "保存为默认值", type: "checkbox", default: false }, false)}
        </div>
      </div>
      <div class="modal-foot">
        <span></span>
        <button class="btn" type="submit" id="ffSubmitBtn" disabled>执行全流程</button>
      </div>
    </form>
  `;
  modalEl.showModal();

  const form = document.querySelector("#oemSampleFullFlowForm");
  const orderSnInput = document.querySelector("#ffOrderSn");
  const fetchBtn = document.querySelector("#ffFetchBtn");
  const skuArea = document.querySelector("#ffSkuArea");
  const adminArea = document.querySelector("#ffAdminArea");
  const submitBtn = document.querySelector("#ffSubmitBtn");
  let skuItems = [];
  let fetchedDetailId = "";

  document.querySelector("#closeModal").addEventListener("click", async () => {
    modalEl.close();
    if (state.view === "dataScripts" && !state.factory.editing) { await renderDataScripts(); }
  });

  // 多图片上传
  document.querySelector("#checkImageSelectBtn").addEventListener("click", () => {
    document.querySelector("#checkImageFileInput").click();
  });
  document.querySelector("#checkImageFileInput").addEventListener("change", async (event) => {
    const files = event.target.files;
    if (!files.length) return;
    const progressEl = document.querySelector("#checkImagePreview");
    const existing = (document.querySelector("#checkReportImages").value || "").split(",").filter(Boolean);
    const btn = document.querySelector("#checkImageSelectBtn");
    btn.disabled = true;
    btn.textContent = "上传中...";
    const token = localStorage.getItem("token");
    for (const file of files) {
      const fd = new FormData();
      fd.append("file", file);
      try {
        const resp = await fetch("/api/oem/upload-image", { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || "上传失败");
        const url = data.url || "";
        if (url) {
          existing.push(url);
          progressEl.innerHTML += `<img src="${escapeHtml(url)}" style="width:80px;height:80px;object-fit:cover;border-radius:4px;border:1px solid var(--border)" />`;
        }
      } catch (e) { showToast(`上传失败: ${e.message}`); }
    }
    document.querySelector("#checkReportImages").value = existing.join(",");
    btn.disabled = false;
    btn.textContent = "选择图片(可多选)";
    showToast(`已上传 ${files.length} 张图片`);
  });

  fetchBtn.addEventListener("click", async () => {
    const orderSn = orderSnInput.value.trim();
    if (!orderSn) { showToast("请输入询价单ID或样品单号"); return; }
    fetchBtn.disabled = true; fetchBtn.textContent = "查询中...";
    skuArea.innerHTML = `<div class="empty">正在查询报价详情...</div>`;
    try {
      const resp = await api(`/api/oem/inquiry-full?order_sn=${encodeURIComponent(orderSn)}`);
      const data = resp.data || {};
      if (!data || Object.keys(data).length === 0) {
        skuArea.innerHTML = `<div class="alert warn">未查到该询价单的信息</div>`; submitBtn.disabled = true; return;
      }
      const records = data.list || [];
      const first = records[0] || {};
      const rawList = first.sku_detail || first.sku_list || first.skuInfo || first.details || first.items || [];
      if (!rawList.length) {
        skuArea.innerHTML = `<div class="alert warn">该询价单暂无 SKU 明细数据</div>`;
        // 如果没 SKU 但已存在样品单号（Y开头），仍允许执行后台流程
        if (orderSn.startsWith("Y")) {
          adminArea.style.display = "";
          submitBtn.disabled = false;
          skuArea.innerHTML = `<div class="alert info">已识别样品单号 ${escapeHtml(orderSn)}，直接执行后台流程</div>`;
        }
        return;
      }
      fetchedDetailId = first.id || data.detail_id || "";
      const qd = first.quote_detail || data.quote_detail || {};
      const sm = {}, lm = {};
      for (const s of (qd.samples_info?.skus || [])) { if (s.sku) sm[s.sku] = s; }
      for (const s of (qd.large_info?.skus || [])) { if (s.sku) lm[s.sku] = s; }
      skuItems = rawList.map((item, idx) => {
        const sn = item.sku || "";
        const ss = sm[sn] || {}, ls = lm[sn] || {};
        return {
          _index: idx, _checked: true,
          sku_id: item.goods_sku_id || item.sku_id || item.skuId || item.id || `SKU-${idx+1}`,
          sku_name: sn,
          num: item.num || item.quantity || 1,
          sample_can: item.can_sample || item.can_make_sample || item.is_sample || "",
          sample_fee: ss.samples_price || item.samples_price || item.sample_fee || "-",
          sample_refund: item.sample_refund || item.sampleReturn || item.sample_return || "",
          sample_shipping: item.sample_shipping || item.sampleShipping || item.sample_freight || "",
          sample_lead_time: item.sample_lead_time || item.sampleLeadTime || item.sample_delivery || "",
          bulk_moq: ls.large_min_quantity || item.large_min_quantity || item.moq || "-",
          bulk_price: ls.large_price || item.large_price || item.bulk_price || "-",
          bulk_other_fee: item.bulk_other_fee || item.bulkOtherFee || item.other_fee || "",
          bulk_deposit_ratio: item.deposit_ratio || item.depositRatio || item.deposit || "",
          bulk_shipping: item.bulk_shipping || item.bulkShipping || item.bulk_freight || "",
          bulk_lead_time: item.bulk_lead_time || item.bulkLeadTime || item.delivery_time || "",
        };
      });
      renderSkuTable(first, data);
      orderSnInput.readOnly = true;
      adminArea.style.display = "";
      submitBtn.disabled = false;
      showToast(`已获取 ${skuItems.length} 个 SKU`);
    } catch (error) {
      skuArea.innerHTML = `<div class="alert error">查询失败：${escapeHtml(error.message)}</div>`;
    } finally {
      fetchBtn.textContent = "重新查询";
      fetchBtn.disabled = false;
    }
  });

  function renderSkuTable(first, data) {
    const rows = skuItems.map((it) => `<tr>
      <td style="padding:4px 6px"><input type="checkbox" data-ff-sku="${it._index}" ${it._checked?"checked":""} /></td>
      <td style="padding:4px 6px;font-weight:600">${escapeHtml(String(it.sku_id))}</td>
      <td style="padding:4px 6px">${escapeHtml(it.sku_name)}</td>
      <td style="padding:4px 6px"><input name="ff_num_${it._index}" type="number" min="1" value="${it.num}" style="width:60px;padding:2px 4px;border:1px solid var(--border);border-radius:4px" /></td>
      <td style="padding:4px 6px;text-align:center">${it.sample_can || "-"}</td>
      <td style="padding:4px 6px;text-align:right">${it.sample_fee || "-"}</td>
      <td style="padding:4px 6px;text-align:center">${it.sample_refund || "-"}</td>
      <td style="padding:4px 6px;text-align:right">${it.sample_shipping || "-"}</td>
      <td style="padding:4px 6px;text-align:center">${it.sample_lead_time || "-"}</td>
      <td style="padding:4px 6px;text-align:center">${it.bulk_moq || "-"}</td>
      <td style="padding:4px 6px;text-align:right">${it.bulk_price || "-"}</td>
      <td style="padding:4px 6px;text-align:right">${it.bulk_other_fee || "-"}</td>
      <td style="padding:4px 6px;text-align:center">${it.bulk_deposit_ratio || "-"}</td>
      <td style="padding:4px 6px;text-align:right">${it.bulk_shipping || "-"}</td>
      <td style="padding:4px 6px;text-align:center">${it.bulk_lead_time || "-"}</td>
    </tr>`).join("");

    let infoHtml = "";
    const infoFields = { goods_name: "商品名称", goodsName: "商品名称", status: "状态", create_time: "创建时间", createdAt: "创建时间", factory_url: "工厂链接", factoryUrl: "工厂链接" };
    const parts = [];
    for (const [key, label] of Object.entries(infoFields)) {
      const v = first[key] || data[key];
      if (v) parts.push(`<span>${label}: <strong>${escapeHtml(String(v))}</strong></span>`);
    }
    if (parts.length) infoHtml = `<div style="margin-bottom:8px;font-size:13px;display:flex;flex-wrap:wrap;gap:4px 16px">${parts.join("")}</div>`;

    skuArea.innerHTML = `${infoHtml}<details class="functional-requirement" open><summary>SKU 明细（勾选=提出样品单）</summary><div style="overflow-x:auto;margin-top:8px"><table style="width:100%;border-collapse:collapse;font-size:12px"><thead><tr style="background:var(--bg-muted)"><th style="padding:4px 6px">选择</th><th style="padding:4px 6px">SKU ID</th><th style="padding:4px 6px">SKU</th><th style="padding:4px 6px">数量</th><th style="padding:4px 6px">能否打样</th><th style="padding:4px 6px">打样费</th><th style="padding:4px 6px">样费退还</th><th style="padding:4px 6px">样运费</th><th style="padding:4px 6px">打样货期</th><th style="padding:4px 6px">起订量</th><th style="padding:4px 6px">大货单价</th><th style="padding:4px 6px">大货其他费</th><th style="padding:4px 6px">定金比例</th><th style="padding:4px 6px">大货运费</th><th style="padding:4px 6px">大货货期</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
    document.querySelectorAll("[data-ff-sku]").forEach((cb) => {
      cb.addEventListener("change", () => { const idx = parseInt(cb.dataset.ffSku, 10); const item = skuItems.find((i) => i._index === idx); if (item) item._checked = cb.checked; });
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const orderSn = orderSnInput.value.trim();
    if (!orderSn) { showToast("请先查询询价单"); return; }
    const checked = skuItems.filter((i) => i._checked);
    // 如果没有勾选 SKU 但直接给了 Y 开头的样品单号，则直接走后台流程
    let skuList = [];
    if (checked.length) {
      skuList = checked.map((it) => {
        const numEl = form.querySelector(`[name="ff_num_${it._index}"]`);
        return { sku_id: parseInt(String(it.sku_id), 10) || it.sku_id, num: numEl ? parseInt(numEl.value, 10) || 1 : it.num };
      });
    }
    const data = readForm(form);
    const merged = mergeParamValues(variables, formFields, { ...data, sku_list: skuList.length ? JSON.stringify(skuList) : undefined });
    merged.order_sn = orderSn;
    if (fetchedDetailId) merged.inquiry_detail_id = fetchedDetailId;
    // 收集图片 URL
    const imageUrls = (document.querySelector("#checkReportImages").value || "").split(",").filter(Boolean);
    if (imageUrls.length) merged.check_report_images = imageUrls.join("\n");
    const runtimeVariables = sanitizeScriptVariables(flow.scriptType, merged, flow);
    if (data.__save_defaults) saveFlowVariables(flow, runtimeVariables);
    showToast("正在执行OEM样品单全流程...");
    await runSavedFlow(flow, runtimeVariables);
  });
}

function openOemBulkOrderRunForm(flow) {
  let variables = {};
  try { variables = parseJsonText(flow.variables || "{}", {}); } catch { showToast("脚本变量不是合法 JSON"); return; }
  const fields = (SCRIPT_PARAM_SCHEMAS.oem_bulk_order || []);
  const formFields = fields.filter((f) => f.type !== "section");
  variables = sanitizeScriptVariables(flow.scriptType, variables, flow);
  const values = { ...paramFormValues(formFields, variables), __save_defaults: false };

  modalEl.innerHTML = `
    <form id="oemBulkOrderForm">
      <div class="modal-head">
        <h3>${escapeHtml(`执行 ${flow.name || "OEM大货单下单"}`)}</h3>
        <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field">
            <label>询价单号</label>
            <div style="display:flex;gap:8px">
              <input name="order_sn" id="ffOrderSn" placeholder="输入询价单号" required style="flex:1" />
              <button class="btn secondary" type="button" id="ffFetchBtn">查询报价</button>
            </div>
          </div>
        </div>
        <div id="ffInfoArea" style="margin-top:12px;display:none"></div>
        <div id="ffOptionArea" style="margin-top:12px;display:none">
          <div class="panel-title" style="margin-bottom:8px"><h4>全局附加服务（默认全选，可单 SKU 自定义覆盖）</h4></div>
          <div id="ffOptionList" style="display:flex;flex-direction:column;gap:4px"></div>
        </div>
        <div id="ffSkuArea" style="margin-top:12px">
          <div class="empty">输入询价单号后点击「查询报价」获取商品列表</div>
        </div>
        <div id="ffParamArea" style="margin-top:16px;display:none">
          <div class="panel-title" style="margin-bottom:8px"><h4>大货单参数</h4></div>
          <div class="form-grid">
            <div class="field">
              <label>仓库城市</label>
              <select name="warehouse_city">
                <option value="2" ${values.warehouse_city === "2" ? "selected" : ""}>广州仓</option>
                <option value="1" ${values.warehouse_city === "1" ? "selected" : ""}>义乌仓</option>
              </select>
            </div>
            <div class="field">
              <label>备注</label>
              <input name="remark" value="${escapeHtml(values.remark || '')}" placeholder="选填" />
            </div>
          </div>
          ${renderFormField({ name: "__save_defaults", label: "保存为默认值", type: "checkbox", default: false }, false)}
        </div>
      </div>
      <div class="modal-foot">
        <span></span>
        <button class="btn" type="submit" id="ffSubmitBtn" disabled>提交大货单</button>
      </div>
    </form>
  `;
  modalEl.showModal();

  const form = document.querySelector("#oemBulkOrderForm");
  const orderSnInput = document.querySelector("#ffOrderSn");
  const fetchBtn = document.querySelector("#ffFetchBtn");
  const infoArea = document.querySelector("#ffInfoArea");
  const optionArea = document.querySelector("#ffOptionArea");
  const optionListEl = document.querySelector("#ffOptionList");
  const skuArea = document.querySelector("#ffSkuArea");
  const paramArea = document.querySelector("#ffParamArea");
  const submitBtn = document.querySelector("#ffSubmitBtn");
  let skuItems = [];
  let fetchedDetailId = "";
  let globalOptionTemplate = []; // 从 API 拉取的 option 模板
  const skuCustomOptions = {};   // { skuIndex: [option, option, ...] } 单 SKU 覆盖

  document.querySelector("#closeModal").addEventListener("click", async () => {
    modalEl.close();
    if (state.view === "dataScripts" && !state.factory.editing) { await renderDataScripts(); }
  });

  fetchBtn.addEventListener("click", async () => {
    const orderSn = orderSnInput.value.trim();
    if (!orderSn) { showToast("请输入询价单号"); return; }
    fetchBtn.disabled = true; fetchBtn.textContent = "查询中...";
    skuArea.innerHTML = `<div class="empty">正在查询报价详情...</div>`;
    try {
      const resp = await api(`/api/oem/inquiry-full?order_sn=${encodeURIComponent(orderSn)}`);
      const data = resp.data || {};
      if (!data || Object.keys(data).length === 0) {
        skuArea.innerHTML = `<div class="alert warn">未查到该询价单的信息</div>`; submitBtn.disabled = true; return;
      }
      const records = data.list || [];
      const first = records[0] || {};
      const rawList = first.sku_detail || first.sku_list || first.skuInfo || first.details || first.items || [];
      if (!rawList.length) {
        skuArea.innerHTML = `<div class="alert warn">该询价单暂无 SKU 数据</div>`;
        return;
      }
      fetchedDetailId = first.id || data.detail_id || "";
      const qd = first.quote_detail || data.quote_detail || {};
      const lm = {};
      for (const s of (qd.large_info?.skus || [])) { if (s.sku) lm[s.sku] = s; }
      const OEM_INQUIRY_STATUS_MAP = { 0: "待翻译", 1: "待审核", 2: "待询价", 3: "询价中", 4: "待报价", 5: "报价中", 6: "已完成", 7: "已取消" };
      const statusLabel = (v) => { const n = Number(v); return (!isNaN(n) && OEM_INQUIRY_STATUS_MAP[n]) ? `${OEM_INQUIRY_STATUS_MAP[n]}(${n})` : (v != null ? String(v) : "-"); };
      const infoFields = { goods_name: "商品名称", status: "状态", create_time: "创建时间", factory_url: "工厂链接" };
      const parts = [];
      for (const [key, label] of Object.entries(infoFields)) {
        const v = first[key] || data[key];
        if (v != null && v !== "") {
          const display = key === "status" ? statusLabel(v) : escapeHtml(String(v));
          parts.push(`<span style="word-break:break-all;overflow-wrap:anywhere">${label}: <strong>${display}</strong></span>`);
        }
      }
      infoArea.innerHTML = parts.length ? `<div style="margin-bottom:8px;font-size:13px;display:flex;flex-wrap:wrap;gap:4px 16px;word-break:break-all;overflow-wrap:anywhere">${parts.join("")}</div>` : "";
      infoArea.style.display = "";

      skuItems = rawList.map((item, idx) => {
        const sn = item.sku || "";
        const ls = lm[sn] || {};
        const num = ls.large_min_quantity || item.large_min_quantity || item.moq || 1;
        return {
          _index: idx, _checked: true,
          sku_id: item.goods_sku_id || item.sku_id || item.skuId || item.id || `SKU-${idx+1}`,
          sku_name: sn,
          num: num,
          _customOption: false,
          warehouse_type: 1,
          fnsku: "",
          asin: "",
          image: "",
        };
      });

      // 拉取全局 option 模板
      try {
        const optResp = await api(`/api/oem/option-list`);
        globalOptionTemplate = Array.isArray(optResp.data) ? optResp.data : [];
      } catch (e) {
        globalOptionTemplate = [];
      }
      renderGlobalOptions();

      orderSnInput.readOnly = true;
      renderSkuTable(first, data);
      paramArea.style.display = "";
      submitBtn.disabled = false;
      showToast(`已获取 ${skuItems.length} 个 SKU + ${globalOptionTemplate.length} 个附加服务`);
    } catch (error) {
      skuArea.innerHTML = `<div class="alert error">查询失败：${escapeHtml(error.message)}</div>`;
    } finally {
      fetchBtn.textContent = "重新查询";
      fetchBtn.disabled = false;
    }
  });

  function renderGlobalOptions() {
    if (!globalOptionTemplate.length) {
      optionArea.style.display = "none";
      return;
    }
    optionArea.style.display = "";
    optionListEl.innerHTML = `<div class="oem-opt-grid">` + globalOptionTemplate.map((opt, i) => {
      if (!typeof opt === "object" || opt === null) return "";
      const name = opt.name || opt.label || "";
      const price = opt.large_price || opt.price || "0.00";
      const remark = opt.remark ? ` (${opt.remark})` : "";
      const isPhoto = opt.id === 9 || String(opt.name || "").includes("拍照");
      const defaultNum = isPhoto ? 1 : "";
      const numDisabled = isPhoto ? "disabled" : 'disabled title="勾选后可输入数量"';
      return `<label class="oem-opt-item">
        <input type="checkbox" class="global-opt" data-opt-idx="${i}" />
        <span class="oem-opt-name">${escapeHtml(name)}${escapeHtml(remark)} — <strong>${escapeHtml(String(price))}</strong> 元</span>
        <input type="number" class="oem-opt-num global-opt-num" data-opt-idx="${i}"
               min="0" value="${defaultNum}" placeholder="跟随SKU" ${numDisabled} />
      </label>`;
    }).join("") + `</div>`;

    // 勾选时启用对应的数量输入框；拍照类保持禁用（固定 1）
    optionListEl.querySelectorAll(".global-opt").forEach((cb) => {
      cb.addEventListener("change", () => {
        const idx = cb.dataset.optIdx;
        const opt = globalOptionTemplate[idx];
        const isPhoto = opt && (opt.id === 9 || String(opt.name || "").includes("拍照"));
        const numInput = optionListEl.querySelector(`.global-opt-num[data-opt-idx="${idx}"]`);
        if (numInput && !isPhoto) numInput.disabled = !cb.checked;
      });
    });
  }

  function getSelectedGlobalOptions() {
    const result = [];
    optionListEl.querySelectorAll(".global-opt:checked").forEach((cb) => {
      const idx = parseInt(cb.dataset.optIdx, 10);
      const opt = globalOptionTemplate[idx];
      if (!opt) return;
      const numInput = optionListEl.querySelector(`.global-opt-num[data-opt-idx="${idx}"]`);
      const numVal = numInput ? parseInt(numInput.value, 10) : NaN;
      const isPhoto = opt.id === 9 || String(opt.name || "").includes("拍照");
      result.push({
        ...opt,
        _num: isPhoto ? 1 : (isNaN(numVal) || numVal < 0 ? null : numVal),
      });
    });
    return result;
  }

  function renderSkuTable(first, data) {
    const OEM_INQUIRY_STATUS_MAP = { 0: "待翻译", 1: "待审核", 2: "待询价", 3: "询价中", 4: "待报价", 5: "报价中", 6: "已完成", 7: "已取消" };
    const statusLabel = (v) => { const n = Number(v); return (!isNaN(n) && OEM_INQUIRY_STATUS_MAP[n]) ? `${OEM_INQUIRY_STATUS_MAP[n]}(${n})` : (v != null ? String(v) : "-"); };
    const rows = skuItems.map((it) => {
      const qd = (first.quote_detail || data.quote_detail || {});
      const ls = (qd.large_info?.skus || []).find((s) => s.sku === it.sku_name) || {};
      const bulkPrice = ls.large_price || "-";
      const bulkOtherFee = ls.large_other_fee || "-";
      const bulkDeposit = ls.deposit_ratio || "-";
      const bulkShipping = ls.large_shipping || "-";
      const bulkLeadTime = ls.large_lead_time || "-";
      const trClass = it._customOption ? ' style="background:hsl(45 80% 95%)"' : '';
      return `<tr data-sku-idx="${it._index}"${trClass}>
        <td style="padding:4px 6px"><input type="checkbox" data-ff-sku="${it._index}" ${it._checked?"checked":""} /></td>
        <td style="padding:4px 6px;font-weight:600">${escapeHtml(String(it.sku_id))}</td>
        <td style="padding:4px 6px;font-size:12px;word-break:break-all">${escapeHtml(it.sku_name)}</td>
        <td style="padding:4px 6px"><input name="ff_num_${it._index}" type="number" min="1" value="${it.num}" style="width:60px" class="sku-num-input" /></td>
        <td style="padding:4px 6px;text-align:center">${escapeHtml(String(ls.large_min_quantity || it.num))}</td>
        <td style="padding:4px 6px;text-align:right">${escapeHtml(String(bulkPrice))}</td>
        <td style="padding:4px 6px;text-align:right">${escapeHtml(String(bulkOtherFee))}</td>
        <td style="padding:4px 6px;text-align:center">${escapeHtml(String(bulkDeposit))}</td>
        <td style="padding:4px 6px;text-align:right">${escapeHtml(String(bulkShipping))}</td>
        <td style="padding:4px 6px;text-align:center">${escapeHtml(String(bulkLeadTime))}</td>
        <td style="padding:4px 6px">
          <select class="sku-wh-type" data-sku-idx="${it._index}" style="width:70px">
            <option value="1" ${it.warehouse_type === 1 ? "selected" : ""}>FBA</option>
            <option value="4" ${it.warehouse_type === 4 ? "selected" : ""}>其他</option>
          </select>
        </td>
        <td style="padding:4px 6px"><input class="sku-fnsku" data-sku-idx="${it._index}" value="${escapeHtml(it.fnsku)}" placeholder="FNSKU" style="width:90px" /></td>
        <td style="padding:4px 6px"><input class="sku-asin" data-sku-idx="${it._index}" value="${escapeHtml(it.asin)}" placeholder="ASIN" style="width:90px" /></td>
        <td style="padding:4px 6px">
          <input type="file" class="sku-img-file" data-sku-idx="${it._index}" accept="image/*" style="display:none" />
          <button type="button" class="btn secondary sku-img-btn" data-sku-idx="${it._index}" style="font-size:11px;padding:2px 6px">上传图片</button>
          <div class="sku-img-preview" data-sku-idx="${it._index}" style="margin-top:2px;min-height:20px"></div>
        </td>
        <td style="padding:4px 6px">
          <a href="#" class="sku-custom-opt" data-sku-idx="${it._index}" style="font-size:12px;color:var(--primary)">自定义 option</a>
        </td>
        <td class="sku-custom-area" data-sku-idx="${it._index}" style="padding:6px;display:none" colspan="15"></td>
      </tr>`;
    }).join("");

    skuArea.innerHTML = `<details class="functional-requirement" open><summary>SKU 明细（勾选=下大货单）</summary>
      <div style="overflow-x:auto;margin-top:8px">
        <table style="width:100%;border-collapse:collapse;font-size:12px">
          <thead><tr style="background:var(--bg-muted)">
            <th style="padding:4px 6px">选择</th><th style="padding:4px 6px">SKU ID</th><th style="padding:4px 6px">SKU</th>
            <th style="padding:4px 6px">购买数量</th><th style="padding:4px 6px">起订量</th><th style="padding:4px 6px">大货单价</th>
            <th style="padding:4px 6px">其他费</th><th style="padding:4px 6px">定金比例</th><th style="padding:4px 6px">运费</th>
            <th style="padding:4px 6px">货期</th><th style="padding:4px 6px">仓库类型</th><th style="padding:4px 6px">FNSKU</th>
            <th style="padding:4px 6px">ASIN</th><th style="padding:4px 6px">标签图片</th><th style="padding:4px 6px">操作</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </details>`;

    // Bind events
    skuArea.querySelectorAll("[data-ff-sku]").forEach((cb) => {
      cb.addEventListener("change", () => { const idx = parseInt(cb.dataset.ffSku, 10); const item = skuItems.find((i) => i._index === idx); if (item) item._checked = cb.checked; });
    });
    skuArea.querySelectorAll(".sku-wh-type").forEach((sel) => {
      sel.addEventListener("change", () => { const idx = parseInt(sel.dataset.skuIdx, 10); const item = skuItems.find((i) => i._index === idx); if (item) item.warehouse_type = parseInt(sel.value, 10); });
    });
    skuArea.querySelectorAll(".sku-fnsku").forEach((inp) => {
      inp.addEventListener("input", () => { const idx = parseInt(inp.dataset.skuIdx, 10); const item = skuItems.find((i) => i._index === idx); if (item) item.fnsku = inp.value.trim(); });
    });
    skuArea.querySelectorAll(".sku-asin").forEach((inp) => {
      inp.addEventListener("input", () => { const idx = parseInt(inp.dataset.skuIdx, 10); const item = skuItems.find((i) => i._index === idx); if (item) item.asin = inp.value.trim(); });
    });
    skuArea.querySelectorAll(".sku-img-btn").forEach((btn) => {
      btn.addEventListener("click", () => { skuArea.querySelector(`.sku-img-file[data-sku-idx="${btn.dataset.skuIdx}"]`).click(); });
    });
    skuArea.querySelectorAll(".sku-img-file").forEach((fileInput) => {
      fileInput.addEventListener("change", async (e) => {
        const file = e.target.files[0]; if (!file) return;
        const idx = parseInt(fileInput.dataset.skuIdx, 10);
        const btn = skuArea.querySelector(`.sku-img-btn[data-sku-idx="${idx}"]`);
        const preview = skuArea.querySelector(`.sku-img-preview[data-sku-idx="${idx}"]`);
        btn.disabled = true; btn.textContent = "上传中...";
        const token = localStorage.getItem("token");
        const fd = new FormData(); fd.append("file", file);
        try {
          const resp = await fetch("/api/oem/upload-image", { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.detail || "上传失败");
          const item = skuItems.find((i) => i._index === idx);
          if (item) item.image = data.url || "";
          preview.innerHTML = `<img src="${escapeHtml(item.image)}" style="width:60px;height:60px;object-fit:cover;border-radius:4px" />`;
          showToast("图片上传成功");
        } catch (err) { showToast(`上传失败: ${err.message}`); }
        btn.disabled = false; btn.textContent = "上传图片";
      });
    });
    skuArea.querySelectorAll(".sku-custom-opt").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const idx = parseInt(link.dataset.skuIdx, 10);
        const area = skuArea.querySelector(`.sku-custom-area[data-sku-idx="${idx}"]`);
        const isVisible = area.style.display !== "none";
        area.style.display = isVisible ? "none" : "";
        if (!isVisible) {
          // Render per-SKU option customization
          const tr = skuArea.querySelector(`tr[data-sku-idx="${idx}"]`);
          tr.style.background = "hsl(45 80% 95%)";
          const skuItem = skuItems.find((i) => i._index === idx);
          if (skuItem) skuItem._customOption = true;
          const skuNum = skuItem ? skuItem.num : 1;
          // 初始化自定义 option 状态（首次展开时默认不勾选）
          if (!skuCustomOptions[idx]) {
            skuCustomOptions[idx] = globalOptionTemplate.map((o) => ({
              ...o, checked: false, _num: null,
            }));
          }
          area.innerHTML = `<div class="oem-sku-custom-panel">
            <div class="oem-sku-custom-title">自定义 option（覆盖全局，默认不勾选）</div>
            <div class="oem-opt-grid oem-opt-grid-compact">${globalOptionTemplate.map((opt, oi) => {
              if (!opt || typeof opt !== "object") return "";
              const name = opt.name || opt.label || "";
              const price = opt.large_price || opt.price || "0.00";
              const isPhoto = opt.id === 9 || String(opt.name || "").includes("拍照");
              const defaultNum = isPhoto ? 1 : skuNum;
              const existingOpt = skuCustomOptions[idx].find((o) => o.id === opt.id);
              const isChecked = existingOpt && existingOpt.checked === true;
              const savedNum = existingOpt && existingOpt._num != null ? existingOpt._num : defaultNum;
              const numDisabled = isPhoto ? "disabled" : (isChecked ? "" : "disabled");
              return `<label class="oem-opt-item">
                <input type="checkbox" class="custom-opt-cb" data-sku-idx="${idx}" data-opt-idx="${oi}" ${isChecked ? "checked" : ""} />
                <span class="oem-opt-name">${escapeHtml(name)} — <strong>${escapeHtml(String(price))}</strong> 元</span>
                <input type="number" class="oem-opt-num custom-opt-num" data-sku-idx="${idx}" data-opt-idx="${oi}"
                       min="0" value="${savedNum}" ${numDisabled} />
              </label>`;
            }).join("")}</div>
          </div>`;
          area.querySelectorAll(".custom-opt-cb").forEach((cb) => {
            cb.addEventListener("change", () => {
              const skuIdx = parseInt(cb.dataset.skuIdx, 10);
              const optIdx = parseInt(cb.dataset.optIdx, 10);
              const opt = globalOptionTemplate[optIdx];
              if (!opt) return;
              const isPhoto = opt.id === 9 || String(opt.name || "").includes("拍照");
              const existing = skuCustomOptions[skuIdx].find((o) => o.id === opt.id);
              if (existing) existing.checked = cb.checked;
              const numInput = area.querySelector(`.custom-opt-num[data-sku-idx="${skuIdx}"][data-opt-idx="${optIdx}"]`);
              if (numInput && !isPhoto) numInput.disabled = !cb.checked;
            });
          });
          area.querySelectorAll(".custom-opt-num").forEach((input) => {
            input.addEventListener("change", () => {
              const skuIdx = parseInt(input.dataset.skuIdx, 10);
              const optIdx = parseInt(input.dataset.optIdx, 10);
              const opt = globalOptionTemplate[optIdx];
              if (!opt) return;
              const existing = skuCustomOptions[skuIdx].find((o) => o.id === opt.id);
              if (existing) existing._num = parseInt(input.value, 10) || 0;
            });
          });
        } else {
          const tr = skuArea.querySelector(`tr[data-sku-idx="${idx}"]`);
          tr.style.background = "";
          const item = skuItems.find((i) => i._index === idx);
          if (item) item._customOption = false;
        }
      });
    });
  }

  function buildSkuListBody() {
    const checked = skuItems.filter((i) => i._checked);
    const globalSelected = getSelectedGlobalOptions();
    return checked.map((it) => {
      const numInput = skuArea.querySelector(`[name="ff_num_${it._index}"]`);
      const skuNum = numInput ? (parseInt(numInput.value, 10) || 1) : it.num;
      let skuOpts;
      if (skuCustomOptions[it._index]) {
        // 单 SKU 自定义：只取勾选的 option
        skuOpts = skuCustomOptions[it._index].filter((o) => o.checked === true);
      } else {
        // 全局勾选的 option
        skuOpts = globalSelected;
      }
      const options = skuOpts.map((opt) => {
        if (!opt || typeof opt !== "object") return null;
        const isPhoto = opt.id === 9 || String(opt.name || "").includes("拍照");
        // num 优先级：option 独立输入 > SKU num（拍照类固定 1）
        let optNum;
        if (isPhoto) {
          optNum = 1;
        } else if (opt._num != null) {
          optNum = opt._num;
        } else {
          optNum = skuNum;
        }
        return {
          id: opt.id,
          name: opt.name || "",
          name_translate: opt.name_translate || "",
          price: String(opt.price || "0.00"),
          price_type: opt.price_type != null ? opt.price_type : 0,
          remark: opt.remark || "",
          unit: opt.unit || "元",
          sort: opt.sort != null ? opt.sort : 0,
          price_range: Array.isArray(opt.price_range) ? opt.price_range : [],
          num: optNum,
          checked: true,
          large_price: String(opt.large_price || opt.price || "0.00"),
        };
      }).filter(Boolean);
      return {
        sku_id: parseInt(String(it.sku_id), 10) || it.sku_id,
        num: skuNum,
        option: options,
        warehouse: [{
          warehouse_type: it.warehouse_type || 1,
          FNSKU: it.fnsku || "",
          ASIN: it.asin || "",
          image: it.image || "",
        }],
      };
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const orderSn = orderSnInput.value.trim();
    if (!orderSn) { showToast("请先查询询价单"); return; }
    const skuList = buildSkuListBody();
    if (!skuList.length) { showToast("请至少勾选一个 SKU"); return; }
    const formData = Object.fromEntries(new FormData(form));
    const merged = mergeParamValues(variables, formFields, {
      ...formData,
      sku_list: JSON.stringify(skuList),
    });
    merged.order_sn = orderSn;
    if (fetchedDetailId) merged.inquiry_detail_id = fetchedDetailId;
    const runtimeVariables = sanitizeScriptVariables(flow.scriptType, merged, flow);
    if (formData.__save_defaults === "on") saveFlowVariables(flow, runtimeVariables);
    showToast("正在执行OEM大货单下单...");
    await runSavedFlow(flow, runtimeVariables);
  });
}

function openRunScriptForm(flow) {
  const builtInTypes = ["shopping_cart", "order_quote", "balance_payment", "bank_payment", "purchase_to_shelf", "purchase_to_shelf_chain", "warehouse_delivery", "porder_balance_payment", "porder_bank_payment", "material_generation", "balance_recharge", "oem_new_inquiry", "oem_sample_order", "oem_full_inquiry_flow", "oem_sample_admin_flow", "oem_sample_full_flow", "oem_bulk_order"];
  if (!flow || (!builtInTypes.includes(flow.scriptType) && !(flow.caseIds || []).length)) {
    showToast("脚本没有配置步骤");
    return;
  }
  const fields = scriptParamFields(flow.scriptType, flow);
  if (!fields.length) {
    runSavedFlow(flow);
    return;
  }
  if (flow.scriptType === "order_quote") {
    openOrderQuoteRunForm(flow, fields);
    return;
  }
  if (flow.scriptType === "oem_sample_order") {
    openOemSampleOrderRunForm(flow);
    return;
  }
  if (flow.scriptType === "oem_full_inquiry_flow") { openOemFullInquiryFlowRunForm(flow); return; }
  if (flow.scriptType === "oem_sample_full_flow") { openOemSampleFullFlowRunForm(flow); return; }
  if (flow.scriptType === "oem_bulk_order") { openOemBulkOrderRunForm(flow); return; }
  let variables = {};
  try {
    variables = parseJsonText(flow.variables || "{}", {});
  } catch {
    showToast("脚本变量不是合法 JSON");
    return;
  }
  variables = sanitizeScriptVariables(flow.scriptType, variables, flow);
  const values = {
    ...paramFormValues(fields, variables),
    __save_defaults: false,
  };
  openForm(
    `执行 ${flow.name || "数据脚本"}`,
    [...fields, { name: "__save_defaults", label: "保存为默认值", type: "checkbox", default: false }],
    values,
    async (data) => {
      const runtimeVariables = sanitizeScriptVariables(flow.scriptType, mergeParamValues(variables, fields, data), flow);
      if (data.__save_defaults) saveFlowVariables(flow, runtimeVariables);
      await runSavedFlow(flow, runtimeVariables);
      return false;
    },
    "执行",
  );
}
// ====== 样品单后续流程 HAR 录制 ======
// 拉取已录制流程列表，失败时静默返回空数组，避免阻塞数据工厂渲染
async function flowRecorderList() {
  try { return await api("/api/flow-recorder/list"); }
  catch { return []; }
}
// 把后端流程对象转换为数据工厂表格行
function flowRecorderRow(flow) {
  return {
    id: `flow_recorder_${flow.id}`,
    flowRecorderId: String(flow.id),
    name: flow.name || "未命名流程",
    description: flow.description || "",
    step_count: flow.step_count || 0,
    isFlowRecorder: true,
    projectId: "",
    envId: "",
  };
}
// 上传 HAR 文件，使用 FormData 直连 fetch（api() 会把非字符串 body 当 JSON 处理）
async function flowRecorderUploadHar(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/api/flow-recorder/upload", {
    method: "POST",
    headers: state.token ? { Authorization: `Bearer ${state.token}` } : {},
    body: formData,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch { detail = await response.text(); }
    throw new Error(detail);
  }
  return response.json();
}
// 触发隐藏 file input 选择 HAR 文件
function flowRecorderPickFile() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".har,application/json";
  input.style.display = "none";
  document.body.appendChild(input);
  input.addEventListener("change", async () => {
    const file = input.files && input.files[0];
    document.body.removeChild(input);
    if (!file) return;
    try {
      showToast("正在解析 HAR 文件...");
      const result = await flowRecorderUploadHar(file);
      flowRecorderOpenPreviewDialog(result);
    } catch (error) {
      showToast(error.message || "HAR 上传失败");
    }
  });
  input.click();
}
// 上传成功后的预览弹窗：步骤预览 + 名称/描述 + 保存
function flowRecorderOpenPreviewDialog(uploadResult) {
  const preview = uploadResult.preview || [];
  const flowDefinition = uploadResult.flow_definition || {};
  const fields = uploadResult.fields || [];
  const previewRows = preview.map((item) => ({
    step_index: item.step_index,
    method: item.method,
    path: item.path,
    response_status: item.response_status,
    body_preview: short(item.body_preview || "", 200),
  }));
  modalEl.innerHTML = `
    <form id="flowRecorderPreviewForm">
      <div class="modal-head">
        <h3>录制流程预览</h3>
        <button class="btn secondary" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field"><label>名称</label><input name="name" required placeholder="例如：样品单后续流程" /></div>
          <div class="field"><label>描述</label><textarea name="description" rows="3" placeholder="流程用途说明（可选）"></textarea></div>
        </div>
        <div class="panel-title"><h3>步骤预览（${previewRows.length} 步）</h3></div>
        ${renderTable(
          [
            { key: "step_index", label: "序号" },
            { key: "method", label: "方法", render: (row) => badge(row.method) },
            { key: "path", label: "路径" },
            { key: "response_status", label: "状态码" },
            { key: "body_preview", label: "响应预览" },
          ],
          previewRows,
          false,
        )}
        ${fields.length ? `<details class="advanced-vars"><summary>字段定义（${fields.length}）</summary><pre class="mini-log">${escapeHtml(JSON.stringify(fields, null, 2))}</pre></details>` : ""}
      </div>
      <div class="modal-foot"><span></span><button class="btn" type="submit">保存</button></div>
    </form>
  `;
  if (!modalEl.open) modalEl.showModal();
  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
  document.querySelector("#flowRecorderPreviewForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = readForm(event.currentTarget);
    if (!data.name) { showToast("请填写流程名称"); return; }
    const submitBtn = event.currentTarget.querySelector('button[type="submit"]');
    try {
      if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "保存中..."; }
      await api("/api/flow-recorder/save", {
        method: "POST",
        body: { name: data.name, description: data.description || "", flow_definition: flowDefinition },
      });
      modalEl.close();
      showToast("流程已保存");
      await renderDataScripts();
    } catch (error) {
      showToast(error.message);
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "保存"; }
    }
  });
}
// 查看流程详情：展示 steps 列表
async function flowRecorderOpenDetailDialog(flowRecorderId) {
  try {
    showToast("正在加载流程详情...");
    const flow = await api(`/api/flow-recorder/${flowRecorderId}`);
    const steps = flow.steps || [];
    modalEl.innerHTML = `
      <div class="modal-head">
        <h3>流程详情：${escapeHtml(flow.name || "未命名流程")}</h3>
        <button class="btn secondary" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body">
        <div class="field"><label>描述</label><p>${escapeHtml(flow.description || "无")}</p></div>
        <div class="panel-title"><h3>步骤列表（${steps.length} 步）</h3></div>
        ${renderTable(
          [
            { key: "step_index", label: "序号" },
            { key: "method", label: "方法", render: (row) => badge(row.method) },
            { key: "path", label: "路径" },
          ],
          steps.map((item) => ({ step_index: item.step_index, method: item.method, path: item.path })),
          false,
        )}
      </div>
      <div class="modal-foot"><span></span><button class="btn secondary" type="button" id="closeModal2">关闭</button></div>
    `;
    if (!modalEl.open) modalEl.showModal();
    document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
    document.querySelector("#closeModal2").addEventListener("click", () => modalEl.close());
  } catch (error) {
    showToast(error.message);
  }
}
// 执行弹窗：先拉详情，再用 renderFormField 渲染字段
async function flowRecorderOpenExecDialog(flowSummary) {
  showToast("正在加载流程详情...");
  try {
    const detail = await api(`/api/flow-recorder/${flowSummary.flowRecorderId}`);
    flowRecorderRenderExecForm(detail);
  } catch (error) {
    showToast(error.message);
  }
}
function flowRecorderRenderExecForm(detail) {
  const fields = detail.fields || [];
  const body = fields.length
    ? `<div class="form-grid">${fields.map((field) => renderFormField(field, field.default ?? "")).join("")}</div>`
    : `<div class="empty">该流程没有需要填写的变量</div>`;
  modalEl.innerHTML = `
    <form id="flowRecorderExecForm">
      <div class="modal-head">
        <h3>执行 ${escapeHtml(detail.name || "录制流程")}</h3>
        <button class="btn secondary" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body">${body}</div>
      <div class="modal-foot"><span></span><button class="btn" type="submit">执行</button></div>
    </form>
  `;
  if (!modalEl.open) modalEl.showModal();
  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
  document.querySelector("#flowRecorderExecForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = readForm(event.currentTarget);
    const variables = {};
    fields.forEach((field) => {
      const raw = formData[field.name];
      if (raw === null || raw === undefined || String(raw).trim() === "") return;
      variables[field.name] = field.type === "number" ? Number(raw) : raw;
    });
    const submitBtn = event.currentTarget.querySelector('button[type="submit"]');
    try {
      if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "执行中..."; }
      showToast("正在执行录制流程...");
      const result = await api(`/api/flow-recorder/${detail.id}/execute`, { method: "POST", body: { variables } });
      flowRecorderShowResult(result, detail);
    } catch (error) {
      showToast(error.message);
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "执行"; }
    }
  });
}
// 展示执行结果：成功步骤绿色、失败步骤红色、后续未执行灰色
function flowRecorderShowResult(result, detail) {
  const completed = result.completed_steps || [];
  const failed = result.failed_step || null;
  const allSteps = detail?.steps || [];
  const failedIndex = failed?.step_index;
  const rows = allSteps.length
    ? allSteps.map((step) => {
        const completedStep = completed.find((item) => item.step_index === step.step_index);
        const isFailed = failedIndex === step.step_index;
        const isAfterFailed = failedIndex != null && step.step_index > failedIndex;
        let status = "skipped";
        let detailText = "";
        if (completedStep) { status = "passed"; detailText = completedStep.response_preview || completedStep.body_preview || ""; }
        else if (isFailed) { status = "failed"; detailText = failed?.error || result.error || ""; }
        else if (isAfterFailed) { status = "skipped"; detailText = "前序步骤失败，未执行"; }
        return { step_index: step.step_index, method: step.method, path: step.path, status, detail: detailText };
      })
    : [
        ...completed.map((item) => ({ step_index: item.step_index, method: item.method, path: item.path, status: "passed", detail: item.response_preview || item.body_preview || "" })),
        ...(failed ? [{ step_index: failed.step_index, method: failed.method, path: failed.path, status: "failed", detail: failed.error || result.error || "" }] : []),
      ];
  modalEl.innerHTML = `
    <div class="modal-head">
      <h3>执行结果：${escapeHtml(detail?.name || "录制流程")}</h3>
      <button class="btn secondary" type="button" id="closeModal">关闭</button>
    </div>
    <div class="modal-body">
      <div class="alert ${result.success ? "info" : "error"}">${result.success ? "执行成功" : (result.error || "执行失败")}</div>
      ${renderTable(
        [
          { key: "step_index", label: "序号" },
          { key: "method", label: "方法", render: (row) => badge(row.method) },
          { key: "path", label: "路径" },
          { key: "status", label: "状态", render: (row) => badge(row.status === "passed" ? "passed" : row.status === "failed" ? "failed" : "skipped") },
          { key: "detail", label: "响应/错误" },
        ],
        rows,
        false,
      )}
    </div>
    <div class="modal-foot"><span></span><button class="btn secondary" type="button" id="closeModal2">关闭</button></div>
  `;
  if (!modalEl.open) modalEl.showModal();
  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
  document.querySelector("#closeModal2").addEventListener("click", () => modalEl.close());
}
// 删除录制流程
async function flowRecorderDelete(flowRecorderId) {
  if (!window.confirm("确认删除这个录制流程？删除后无法恢复。")) return;
  try {
    await api(`/api/flow-recorder/${flowRecorderId}`, { method: "DELETE" });
    showToast("已删除");
    await renderDataScripts();
  } catch (error) {
    showToast(error.message);
  }
}
function openFunctionalTaskForm(projects) {  const projectOptions = projects.map((item) => ({ value: item.id, label: item.name }));  openForm(    "新增功能测试任务",    [      { name: "project_id", label: "项目", type: "select", options: projectOptions, required: true },      { name: "iteration_name", label: "迭代/需求名称", required: true },      { name: "target_url", label: "真实测试页面URL", required: true },      { name: "requirement_text", label: "需求说明", type: "textarea", rows: 8 },    ],    { project_id: state.filters.projectId || projects[0]?.id || "" },    async (data) => {      const task = await api("/api/functional-tasks", { method: "POST", body: data });      state.functionalTaskId = String(task.id);      localStorage.setItem("functionalTaskId", state.functionalTaskId);      showToast("功能测试任务已创建");      await renderFunctionalTests();    },  );}async function openAiConfigForm() {  const config = await api("/api/ai-config");  openForm(    "本地模型配置",    [      {        name: "provider",        label: "服务类型",        type: "select",        options: [          { value: "openai_compatible", label: "OpenAI兼容" },          { value: "ollama", label: "Ollama" },        ],      },      { name: "base_url", label: "Base URL", default: "http://127.0.0.1:11434" },      { name: "model", label: "模型名称" },      { name: "api_key", label: "API Key(可选)", type: "password" },    ],    config,    async (data) => {      await api("/api/ai-config", { method: "PUT", body: data });      showToast("AI配置已保存");    },  );}function openAxureUpload(taskId) {  modalEl.innerHTML = `    <form id="axureUploadForm">      <div class="modal-head">        <h3>上传 Axure .rp 文件</h3>        <button class="btn secondary" type="button" id="closeModal">关闭</button>      </div>      <div class="modal-body">        <div class="field"><label>Axure文件</label><input type="file" id="axureFile" accept=".rp,.zip,.html,.htm,.txt" required /></div>      </div>      <div class="modal-foot"><span></span><button class="btn" type="submit">上传</button></div>    </form>  `;  modalEl.showModal();  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());  document.querySelector("#axureUploadForm").addEventListener("submit", async (event) => {    event.preventDefault();    const file = document.querySelector("#axureFile").files[0];    if (!file) return;    const formData = new FormData();    formData.append("file", file);    try {      const response = await fetch(`/api/functional-tasks/${taskId}/upload-axure`, {        method: "POST",        headers: state.token ? { Authorization: `Bearer ${state.token}` } : {},        body: formData,      });      if (!response.ok) throw new Error((await response.json()).detail || response.statusText);      modalEl.close();      showToast("Axure上传完成");      await renderFunctionalTests();    } catch (error) {      showToast(error.message);    }  });}function functionalScreenshotFilesFromList(fileList) {  return Array.from(fileList || []).filter((file) => {    const name = file.name || "";    return file.type?.startsWith("image/") || /\.(png|jpe?g|webp)$/i.test(name);  });}async function uploadFunctionalScreenshotFiles(taskId, files) {  for (const file of files) {    const formData = new FormData();    formData.append("file", file);    const response = await fetch(`/api/functional-tasks/${taskId}/upload-screenshot`, {      method: "POST",      headers: state.token ? { Authorization: `Bearer ${state.token}` } : {},      body: formData,    });    if (!response.ok) {      const error = await response.json().catch(() => ({}));      throw new Error(error.detail || response.statusText);    }  }}function openFunctionalScreenshotUpload(taskId) {  let selectedFiles = [];  modalEl.innerHTML = `    <form id="functionalScreenshotUploadForm">      <div class="modal-head">        <h3>上传产品截图</h3>        <button class="btn secondary" type="button" id="closeModal">关闭</button>      </div>      <div class="modal-body">        <div class="screenshot-upload-zone" id="functionalScreenshotDropZone" tabindex="0">          <strong>拖拽图片到这里，或点击选择图片</strong>          <span>支持 PNG/JPG/WebP，可一次选择多张，也可以复制图片后按 Ctrl+V 粘贴</span>          <input type="file" id="functionalScreenshotFile" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" multiple hidden />        </div>        <div class="screenshot-upload-list" id="functionalScreenshotList">暂未选择图片</div>      </div>      <div class="modal-foot"><span></span><button class="btn" type="submit">上传</button></div>    </form>  `;  modalEl.showModal();  const input = document.querySelector("#functionalScreenshotFile");  const dropZone = document.querySelector("#functionalScreenshotDropZone");  const listEl = document.querySelector("#functionalScreenshotList");  function renderSelectedFiles() {    if (!selectedFiles.length) {      listEl.textContent = "暂未选择图片";      return;    }    listEl.innerHTML = selectedFiles      .map((file, index) => `<div><span>${index + 1}. ${escapeHtml(file.name || "clipboard-image.png")}</span><strong>${Math.ceil(file.size / 1024)} KB</strong></div>`)      .join("");  }  function addFiles(files) {    const imageFiles = functionalScreenshotFilesFromList(files);    if (!imageFiles.length) {      showToast("没有找到可上传的图片");      return;    }    const existing = new Set(selectedFiles.map((file) => `${file.name}-${file.size}-${file.lastModified}`));    imageFiles.forEach((file) => {      const key = `${file.name}-${file.size}-${file.lastModified}`;      if (!existing.has(key)) {        existing.add(key);        selectedFiles.push(file);      }    });    renderSelectedFiles();    showToast(`已选择 ${selectedFiles.length} 张截图`);  }  function extractImageFromItems(items) {    if (!items) return [];    const files = [];    Array.from(items).forEach((item) => {      if (item.kind === "file" && item.type?.startsWith("image/")) {        const file = item.getAsFile();        if (file) files.push(file);      }    });    return files;  }  function pasteHandler(event) {    const fromFiles = functionalScreenshotFilesFromList(event.clipboardData?.files);    if (fromFiles.length) {      event.preventDefault();      addFiles(fromFiles);      return;    }    const fromItems = functionalScreenshotFilesFromList(extractImageFromItems(event.clipboardData?.items));    if (fromItems.length) {      event.preventDefault();      addFiles(fromItems);      return;    }    if (navigator.clipboard?.read) {      event.preventDefault();      navigator.clipboard.read().then((items) => {        const files = [];        const promises = [];        items.forEach((item) => {          item.types.forEach((type) => {            if (type.startsWith("image/")) {              promises.push(                item.getType(type).then((blob) => {                  const f = new File([blob], "clipboard-image.png", { type });                  if (f) files.push(f);                }).catch(() => {})              );            }          });        });        return Promise.all(promises).then(() => {          if (files.length) addFiles(files);        });      }).catch(() => {});    }  }  document.addEventListener("paste", pasteHandler);  modalEl.addEventListener("close", () => {    document.removeEventListener("paste", pasteHandler);  }, { once: true });  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());  dropZone.addEventListener("click", () => input.click());  dropZone.addEventListener("keydown", (event) => {    if (event.key === "Enter" || event.key === " ") {      event.preventDefault();      input.click();    }  });  input.addEventListener("change", () => addFiles(input.files));  dropZone.addEventListener("dragenter", (event) => {    event.preventDefault();    dropZone.classList.add("drag-over");  });  dropZone.addEventListener("dragover", (event) => {    event.preventDefault();    event.dataTransfer.dropEffect = "copy";    dropZone.classList.add("drag-over");  });  dropZone.addEventListener("dragleave", () => {    dropZone.classList.remove("drag-over");  });  dropZone.addEventListener("drop", (event) => {    event.preventDefault();    dropZone.classList.remove("drag-over");    const files = Array.from(event.dataTransfer?.files || []);    if (files.length) {      addFiles(files);    } else {      const itemsFiles = functionalScreenshotFilesFromList(extractImageFromItems(event.dataTransfer?.items));      if (itemsFiles.length) addFiles(itemsFiles);    }  });  document.querySelector("#functionalScreenshotUploadForm").addEventListener("submit", async (event) => {    event.preventDefault();    if (!selectedFiles.length) {      showToast("请先选择、拖入或粘贴图片");      return;    }    try {      showToast(`正在上传 ${selectedFiles.length} 张截图`);      await uploadFunctionalScreenshotFiles(taskId, selectedFiles);      modalEl.close();      showToast(`已上传 ${selectedFiles.length} 张截图`);      await renderFunctionalTests();    } catch (error) {      showToast(error.message);    }  });}async function analyzeFunctionalScreenshot(screenshotId) {  try {    showToast("正在识别截图，请稍候");    await api(`/api/functional-screenshots/${screenshotId}/analyze`, { method: "POST" });    showToast("截图识别完成");    await renderFunctionalTests();  } catch (error) {    showToast(error.message);  }}function openRequirementNoteForm(taskId, item = null) {  openForm(    item ? "编辑补充需求" : "补充需求",    [{ name: "note_text", label: "补充需求内容", type: "textarea", rows: 8, required: true }],    item || {},    async (data) => {      const path = item ? `/api/functional-requirement-notes/${item.id}` : `/api/functional-tasks/${taskId}/requirement-notes`;      await api(path, { method: item ? "PUT" : "POST", body: data });      showToast("补充需求已保存");      await renderFunctionalTests();    },  );}function functionalScanAuthKey(task) {  try {    return `${FUNCTIONAL_SCAN_AUTH_PREFIX}${new URL(task.target_url).origin}`;  } catch {    return `${FUNCTIONAL_SCAN_AUTH_PREFIX}${task.id}`;  }}function inferLoginUrl(targetUrl) {  try {    const url = new URL(targetUrl);    if (url.hash && url.hash.includes("/")) {      const base = url.origin + url.pathname;      const hashPrefix = url.hash.startsWith("#!") ? "#!" : "#";      return base + hashPrefix + "/login";    }    if (url.pathname.toLowerCase().includes("login")) return url.toString();    return url.origin + "/login";  } catch {    return "";  }}function loadFunctionalScanAuth(task) {  let saved = {};  try {    saved = JSON.parse(localStorage.getItem(functionalScanAuthKey(task)) || "{}");  } catch {    saved = {};  }  return {    enabled: saved.enabled ?? true,    login_url: saved.login_url || inferLoginUrl(task.target_url),    username: saved.username || "",    password: saved.remember_password ? saved.password || "" : "",    remember_password: Boolean(saved.remember_password),    username_locator:      saved.username_locator ||      'input[name="username"]\ninput[name="account"]\ninput[placeholder*="账号"]\ninput[placeholder*="用户名"]\ninput[type="text"]',    password_locator:      saved.password_locator ||      'input[type="password"]\ninput[name="password"]\ninput[placeholder*="密码"]',    submit_locator:      saved.submit_locator ||      'button[type="submit"]\ntext=登录\ntext=Login\ntext=ログイン',    success_url_contains: saved.success_url_contains || "",    success_selector: saved.success_selector || "",  };}function saveFunctionalScanAuth(task, data) {  const value = {    enabled: data.enabled,    login_url: data.login_url,    username: data.username,    remember_password: data.remember_password,    username_locator: data.username_locator,    password_locator: data.password_locator,    submit_locator: data.submit_locator,    success_url_contains: data.success_url_contains,    success_selector: data.success_selector,    password: data.remember_password ? data.password : "",  };  localStorage.setItem(functionalScanAuthKey(task), JSON.stringify(value));}function openFunctionalScanForm(task) {  const values = loadFunctionalScanAuth(task);  const basicFields = [    { name: "enabled", label: "启用登录后扫描", type: "checkbox", default: true },    { name: "login_url", label: "登录页 URL" },    { name: "username", label: "登录账号" },    { name: "password", label: "登录密码", type: "password" },    { name: "remember_password", label: "记住到本机浏览器", type: "checkbox" },  ];  const advancedFields = [    { name: "username_locator", label: "账号输入框 locator(多个换行)", type: "textarea", rows: 4 },    { name: "password_locator", label: "密码输入框 locator(多个换行)", type: "textarea", rows: 3 },    { name: "submit_locator", label: "登录按钮 locator(多个换行)", type: "textarea", rows: 4 },    { name: "success_url_contains", label: "登录成功 URL 包含(可选)" },    { name: "success_selector", label: "登录成功页面元素 locator(可选)" },  ];  modalEl.innerHTML = `    <form id="functionalScanForm">      <div class="modal-head">        <h3>扫描页面登录配置</h3>        <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>      </div>      <div class="modal-body">        <div class="form-grid">          <div class="field">            <label>目标页面</label>            <input value="${escapeHtml(task.target_url)}" disabled />          </div>          ${basicFields.map((field) => renderFormField(field, values[field.name])).join("")}          <details class="advanced-vars">            <summary>高级配置</summary>            <div class="form-grid">              ${advancedFields.map((field) => renderFormField(field, values[field.name])).join("")}            </div>          </details>          <section class="scan-progress" id="functionalScanProgress" hidden>            <div class="progress-meta">              <strong id="functionalScanStage">准备扫描</strong>              <span id="functionalScanPercent">0%</span>            </div>            <div class="progress-track"><div class="progress-fill" id="functionalScanFill" style="width: 0%"></div></div>            <pre class="scan-progress-log" id="functionalScanLog"></pre>          </section>        </div>      </div>      <div class="modal-foot"><span></span><button class="btn" type="submit">开始扫描</button></div>    </form>  `;  modalEl.showModal();  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());  document.querySelector("#functionalScanForm").addEventListener("submit", async (event) => {    event.preventDefault();    const data = readForm(event.currentTarget);    if (data.enabled && (!data.login_url || !data.username || !data.password)) {      showToast("请填写登录页URL、登录账号和登录密码");      return;    }    saveFunctionalScanAuth(task, data);    const submitButton = event.currentTarget.querySelector('button[type="submit"]');    const progressEl = document.querySelector("#functionalScanProgress");    const stageEl = document.querySelector("#functionalScanStage");    const percentEl = document.querySelector("#functionalScanPercent");    const fillEl = document.querySelector("#functionalScanFill");    const logEl = document.querySelector("#functionalScanLog");    const logs = [];    const setProgress = (percent, stage, logLine = "", failed = false) => {      progressEl.hidden = false;      const safePercent = Math.max(0, Math.min(100, percent));      stageEl.textContent = stage;      percentEl.textContent = `${safePercent}%`;      fillEl.style.width = `${safePercent}%`;      fillEl.classList.toggle("failed", failed);      if (logLine) logs.push(logLine);      logEl.textContent = logs.join("\n");      logEl.scrollTop = logEl.scrollHeight;    };    const stages = [      [8, "准备扫描", "准备登录配置"],      [18, "打开登录页", "正在打开登录页"],      [34, "填写账号密码", "正在定位账号框、密码框"],      [48, "提交登录", "正在点击登录按钮"],      [64, "进入目标页面", "正在带登录态进入目标页面"],      [78, "提取DOM", "正在提取页面按钮、输入框、文本结构"],      [88, "保存截图", "正在保存页面快照"],    ];    let stageIndex = 0;    setProgress(5, "准备扫描", "扫描任务已提交");    const timer = window.setInterval(() => {      if (stageIndex >= stages.length) return;      const [percent, stage, line] = stages[stageIndex];      setProgress(percent, stage, line);      stageIndex += 1;    }, 1200);    submitButton.disabled = true;    submitButton.textContent = "扫描中";    try {      showToast("正在登录并扫描页面");      const result = await api(`/api/functional-tasks/${task.id}/scan-page`, {        method: "POST",        body: {          auth: {            enabled: data.enabled,            login_url: data.login_url,            username: data.username,            password: data.password,            username_locator: data.username_locator,            password_locator: data.password_locator,            submit_locator: data.submit_locator,            success_url_contains: data.success_url_contains,            success_selector: data.success_selector,          },        },      });      window.clearInterval(timer);      (result.scan_trace || []).forEach((line) => logs.push(line));      setProgress(100, "扫描完成", "页面扫描完成");      showToast("页面扫描完成");      await renderFunctionalTests();    } catch (error) {      window.clearInterval(timer);      setProgress(100, "扫描失败", error.message, true);      showToast(error.message);    } finally {      submitButton.disabled = false;      submitButton.textContent = "重新扫描";    }  });}async function runFunctionalAction(path, message) {  try {    showToast("处理中，请稍候");    await api(path, { method: "POST" });    showToast(message);    await renderFunctionalTests();  } catch (error) {    showToast(error.message);  }}async function generateFunctionalCases(taskId) {  try {    showToast("正在生成测试点");    const result = await api(`/api/functional-tasks/${taskId}/generate-cases`, { method: "POST" });    showToast(result.warning || "测试点已生成");    await renderFunctionalTests();  } catch (error) {    showToast(error.message);  }}async function generateFunctionalUiSteps(caseId) {  try {    showToast("正在生成UI步骤");    const result = await api(`/api/functional-cases/${caseId}/generate-ui-steps`, { method: "POST" });    showToast(result.warning || "UI步骤已生成，确认后可执行");    await renderFunctionalTests();  } catch (error) {    showToast(error.message);  }}function renderPreflightReport(report) {  const issues = report?.issues || [];  const locators = report?.locator_checks || [];  return `    <div class="preflight-report">      <section class="diagnosis-summary">        <strong>${badge(report?.status || "unchecked")} ${escapeHtml(report?.summary || "检查完成")}</strong>        ${report?.missing_variables?.length ? `<div><span>缺少变量：${escapeHtml(report.missing_variables.join("、"))}</span></div>` : ""}      </section>      <section class="diagnosis-card">        <div class="diagnosis-card-head"><span>风险项</span></div>        ${          issues.length            ? `<ul>${issues.map((item) => `<li>${escapeHtml(item.step ? `第${item.step}步：${item.message}` : item.message)}</li>`).join("")}</ul>`            : `<div class="empty">没有发现明显风险</div>`        }      </section>      <section class="diagnosis-card">        <div class="diagnosis-card-head"><span>定位器检查</span></div>        ${          locators.length            ? `<div class="step-log-list">${locators                .map(                  (item) => `                    <div class="step-log-item ${item.status === "ok" ? "ok" : "fail"}">                      <div><strong>第${escapeHtml(item.step)}步：${escapeHtml(item.name || "")}</strong>${badge(item.status === "ok" ? "executable" : "locator_risk")}</div>                      <p>定位器：${escapeHtml(item.used_locator || item.locator || "-")}</p>                      <small>匹配数量：${escapeHtml(item.matched_count || 0)}，可见：${item.visible ? "是" : "否"}</small>                    </div>                  `,                )                .join("")}</div>`            : `<div class="empty">没有需要检查的定位器</div>`        }      </section>    </div>  `;}async function preflightFunctionalCase(task, item, accounts = [], projects = []) {  if (!item) return;  openFunctionalExecutionModal({    title: `试跑检查 ${item.title}`,    task,    singleCase: item,    accounts,    projects,    submitLabel: "开始检查",    onSubmit: async (payload) => {      const result = await api(`/api/functional-cases/${item.id}/preflight`, { method: "POST", body: payload });      modalEl.innerHTML = `        <div class="modal-head">          <h3>试跑检查结果</h3>          <button class="btn secondary" type="button" id="closeModal">关闭</button>        </div>        <div class="modal-body">${renderPreflightReport(result.report || {})}</div>      `;      if (!modalEl.open) modalEl.showModal();      document.querySelector("#closeModal").addEventListener("click", async () => {        modalEl.close();        await renderFunctionalTests();      });    },  });}async function approveFunctionalCase(caseId) {  try {    await api(`/api/functional-cases/${caseId}`, { method: "PUT", body: { automation_status: "approved" } });    showToast("已确认可执行");    await renderFunctionalTests();  } catch (error) {    showToast(error.message);  }}function openFunctionalCaseForm(item, accounts = [], projects = []) {  openForm(    "编辑测试点",    [      { name: "title", label: "测试点", required: true },      { name: "precondition", label: "前置条件", type: "textarea", rows: 3 },      { name: "steps", label: "测试步骤", type: "textarea", rows: 6 },      { name: "expected", label: "预期结果", type: "textarea", rows: 4 },      { name: "priority", label: "优先级", type: "select", options: ["P0", "P1", "P2"].map((value) => ({ value, label: value })) },      {        name: "automation_status",        label: "自动化状态",        type: "select",        options: [          { value: "draft", label: "草稿" },          { value: "approved", label: "已确认" },        ],      },      {        name: "__account_profile_id",        label: "用例账号",        type: "select",        options: [{ value: "", label: "跟随任务默认账号" }, ...(accounts || []).map((account) => ({ value: account.id, label: accountLabel(account, projects) }))],      },    ],    { ...item, __account_profile_id: item?.account_profile_id || "" },    async (data) => {      const accountProfileId = data.__account_profile_id;      delete data.__account_profile_id;      await api(`/api/functional-cases/${item.id}`, { method: "PUT", body: data });      await saveTestAccountBinding("functional_case", item.id, accountProfileId);      showToast("测试点已保存");      await renderFunctionalTests();    },  );}const FUNCTIONAL_RUNTIME_FIELD_META = {  username: { label: "登录账号", placeholder: "请输入登录账号" },  password: { label: "登录密码", type: "password", placeholder: "请输入登录密码" },  code: { label: "验证码", placeholder: "请输入验证码" },  phone: { label: "手机号", placeholder: "请输入手机号" },  email: { label: "邮箱", placeholder: "请输入邮箱" },  account: { label: "账号", placeholder: "请输入账号" },};function collectFunctionalRuntimeVariableNames(task, singleCase = null, { includeDefaultAccountFields = true } = {}) {  const textParts = [];  const cases = singleCase ? [singleCase] : task?.cases || [];  cases.forEach((item) => {    if (item.automation_status !== "approved") return;    ["steps", "expected", "precondition"].forEach((key) => {      if (item[key]) textParts.push(String(item[key]));    });    if (item.ui_case_id) {      const uiText = JSON.stringify(item);      textParts.push(uiText);    }  });  const text = textParts.join("\n");  const names = new Set();  text.replace(/\{\{\s*([A-Za-z_][A-Za-z0-9_$]*)\s*\}\}/g, (_, name) => {    names.add(name.replace(/^\$/, ""));    return "";  });  if (includeDefaultAccountFields) ["username", "password", "code"].forEach((name) => names.add(name));  return [...names].filter((name) => !["timestamp", "datetime", "date", "uuid", "random_int", "random_str", "random_phone", "random_email"].includes(name));}function functionalRuntimeFields(task, singleCase = null, options = {}) {  return collectFunctionalRuntimeVariableNames(task, singleCase, options).map((name) => {    const meta = FUNCTIONAL_RUNTIME_FIELD_META[name] || {};    return {      name,      label: meta.label || name,      type: meta.type || "text",      placeholder: meta.placeholder || "",    };  });}function renderExecutionVariableFields(fields, values = {}) {  if (!fields.length) return `<div class="empty">没有需要手填的运行变量</div>`;  return fields.map((field) => renderFormField(field, values[field.name] ?? "")).join("");}function readFunctionalExecutionForm(form, variableFields, accountFields) {  const data = readForm(form);  const variables = {};  [...variableFields, ...accountFields].forEach((field) => {    const value = data[field.name];    if (String(value ?? "").trim() !== "") variables[field.name] = value;  });  return {    account_mode: data.account_mode || "default",    account_profile_id: data.account_mode === "override" && data.account_profile_id ? Number(data.account_profile_id) : null,    variables,  };}function openFunctionalExecutionModal({ title, task, singleCase = null, accounts = [], projects = [], submitLabel = "执行", onSubmit }) {  const variableFields = functionalRuntimeFields(task, singleCase, { includeDefaultAccountFields: false }).filter((field) => !ACCOUNT_RUNTIME_KEYS.has(field.name));  const accountFields = functionalRuntimeFields(task, singleCase, { includeDefaultAccountFields: true }).filter((field) => ACCOUNT_RUNTIME_KEYS.has(field.name));  modalEl.innerHTML = `    <form id="functionalExecuteForm">      <div class="modal-head">        <h3>${escapeHtml(title)}</h3>        <button class="btn secondary" type="button" id="closeModal">关闭</button>      </div>      <div class="modal-body">        <div class="form-grid">          <div class="field">            <label>账号来源</label>            <select name="account_mode" id="functionalAccountMode">              <option value="default">使用默认账号（用例 > 任务 > 项目）</option>              <option value="override">本次统一使用指定账号</option>              <option value="none">不使用账号档案</option>            </select>          </div>          <div class="field" id="functionalAccountPicker" hidden>            <label>本次统一账号</label>            <select name="account_profile_id">${accountOptions(accounts, "", projects, "请选择测试账号")}</select>          </div>          <div class="field">            <label>当前默认</label>            <input type="text" value="${escapeHtml(singleCase?.account_profile_name || task.account_profile_name || "按项目默认账号解析")}" disabled />          </div>        </div>        <details class="functional-requirement">          <summary>运行时变量</summary>          <div class="form-grid">${renderExecutionVariableFields(variableFields)}</div>        </details>        <details class="functional-requirement">          <summary>临时覆盖账号/验证码</summary>          <div class="form-grid">${renderExecutionVariableFields(accountFields)}</div>        </details>      </div>      <div class="modal-foot"><span></span><button class="btn" type="submit">${escapeHtml(submitLabel)}</button></div>    </form>  `;  modalEl.showModal();  const modeEl = document.querySelector("#functionalAccountMode");  const pickerEl = document.querySelector("#functionalAccountPicker");  const syncPicker = () => {    pickerEl.hidden = modeEl.value !== "override";  };  modeEl.addEventListener("change", syncPicker);  syncPicker();  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());  document.querySelector("#functionalExecuteForm").addEventListener("submit", async (event) => {    event.preventDefault();    const submitButton = event.currentTarget.querySelector('button[type="submit"]');    try {      if (submitButton) {        submitButton.disabled = true;        submitButton.textContent = "执行中...";      }      const payload = readFunctionalExecutionForm(event.currentTarget, variableFields, accountFields);      await onSubmit(payload);    } catch (error) {      showToast(error.message);      if (submitButton && document.body.contains(submitButton)) {        submitButton.disabled = false;        submitButton.textContent = submitLabel;      }    }  });}function isFunctionalExecutionDone(job) {  return ["passed", "failed", "error"].includes(String(job?.status || ""));}function renderFunctionalExecutionProgress(job) {  const total = Number(job?.total || 0);  const completed = Number(job?.completed || 0);  const passedCount = Number(job?.passed_count || 0);  const failedCount = Number(job?.failed_count || 0);  const pendingCount = Math.max(total - completed, 0);  const percent = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;  const isDone = isFunctionalExecutionDone(job);  const isFailed = ["failed", "error"].includes(String(job?.status || ""));  const currentText = job?.current_case_title ? `正在执行：${job.current_case_title}` : isDone ? "执行已结束" : "等待执行器启动...";  const rows = Array.isArray(job?.records) ? job.records : [];  modalEl.innerHTML = `    <div class="modal-head">      <h3>${escapeHtml(job?.task_name || "已确认用例执行进度")}</h3>      <button class="btn secondary" type="button" id="closeModal">关闭</button>    </div>    <div class="modal-body">      <div class="progress-meta">        <strong>${escapeHtml(currentText)}</strong>        <span>${escapeHtml(completed)} / ${escapeHtml(total)}，${escapeHtml(percent)}%</span>      </div>      <div class="progress-track">        <div class="progress-fill ${isFailed ? "failed" : ""}" style="width:${escapeHtml(percent)}%"></div>      </div>      <div class="functional-execution-summary">        <div><span>状态</span><strong>${badge(job?.status || "queued")}</strong></div>        <div><span>成功</span><strong class="success-text">${escapeHtml(passedCount)}</strong></div>        <div><span>失败</span><strong class="danger-text">${escapeHtml(failedCount)}</strong></div>        <div><span>等待</span><strong>${escapeHtml(pendingCount)}</strong></div>      </div>      ${job?.error ? `<div class="alert error">${escapeHtml(job.error)}</div>` : ""}      <div class="functional-progress-list">        ${rows          .map((row, index) => {            const statusValue = row.status || row.result || "pending";            const failure = row.error_category || row.failure_reason || row.error || "";            return `              <div class="functional-progress-item ${escapeHtml(statusValue)}">                <div>                  <span>用例 ${escapeHtml(index + 1)}</span>                  <strong>${escapeHtml(row.title || "-")}</strong>                  ${badge(statusValue)}                </div>                <p>${failure ? escapeHtml(failure) : row.duration_ms ? `耗时：${escapeHtml(row.duration_ms)} ms` : "等待执行"}</p>                <div class="functional-progress-actions">                  ${row.record_id && row.screenshot ? `<button class="btn secondary" type="button" data-progress-shot="${row.record_id}">查看截图</button>` : ""}                  ${row.current_url ? `<small>URL：${escapeHtml(row.current_url)}</small>` : ""}                </div>              </div>            `;          })          .join("")}      </div>      <p class="progress-note">${isDone ? "执行已完成，可以关闭弹窗查看执行记录。" : "执行中可关闭弹窗，后台会继续执行；保留弹窗可实时查看进度。"}</p>    </div>  `;  if (!modalEl.open) modalEl.showModal();  document.querySelector("#closeModal")?.addEventListener("click", () => modalEl.close());  document.querySelectorAll("[data-progress-shot]").forEach((button) => {    button.addEventListener("click", () => openProtectedFile(`/api/test-records/${button.dataset.progressShot}/screenshot`));  });}async function watchFunctionalExecutionProgress(initialJob) {  let job = initialJob;  let closed = false;  const onClose = () => {    closed = true;  };  modalEl.addEventListener("close", onClose, { once: true });  while (true) {    renderFunctionalExecutionProgress(job);    if (isFunctionalExecutionDone(job)) break;    await sleep(1000);    if (closed) return;    job = await api(`/api/functional-executions/${job.job_id}`);  }  showToast(`执行完成：成功 ${job.passed_count || 0} 条，失败 ${job.failed_count || 0} 条`);  await renderFunctionalTests();}function openFunctionalExecuteForm(task, singleCase = null, accounts = [], projects = []) {  openFunctionalExecutionModal({    title: singleCase ? `执行 ${singleCase.title}` : `执行 ${task.iteration_name}`,    task,    singleCase,    accounts,    projects,    submitLabel: "执行",    onSubmit: async (payload) => {      if (singleCase) payload.case_id = singleCase.id;      const job = await api(`/api/functional-tasks/${task.id}/execute-async`, {        method: "POST",        body: payload,      });      await watchFunctionalExecutionProgress(job);    },  });}function showFunctionalCaseDetail(item) {  modalEl.innerHTML = `    <div class="modal-head">      <h3>${escapeHtml(item?.title || "测试点详情")}</h3>      <button class="btn secondary" type="button" id="closeModal">关闭</button>    </div>    <div class="modal-body"><pre class="log-view">${escapeHtml(JSON.stringify(item || {}, null, 2))}</pre></div>  `;  modalEl.showModal();  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());}function showFunctionalRunLog(item) {  const readable = renderFunctionalRunReadableLog(item);  modalEl.innerHTML = `    <div class="modal-head">      <h3>功能测试执行日志 #${item?.id || ""}</h3>      <button class="btn secondary" type="button" id="closeModal">关闭</button>    </div>    <div class="modal-body">${readable}</div>  `;  modalEl.showModal();  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());}function parseFunctionalRunLog(item) {  if (!item?.log) return {};  if (typeof item.log === "object") return item.log;  try {    return JSON.parse(item.log);  } catch {    return {};  }}function functionalRunScreenshotRows(item) {  const payload = parseFunctionalRunLog(item);  const records = Array.isArray(payload.records) ? payload.records : [];  return records.map((record, index) => ({    title: record.title || record.case_name || `用例 ${index + 1}`,    result: record.result || "unknown",    recordId: record.record_id,    screenshot: record.screenshot || "",  }));}function parseUiLog(log) {  if (!log) return {};  if (typeof log === "object") return log;  try {    return JSON.parse(log);  } catch {    return { raw: log };  }}function renderFunctionalRunReadableLog(item) {  const payload = parseFunctionalRunLog(item);  const records = Array.isArray(payload.records) ? payload.records : [];  if (!records.length) {    return `<pre class="log-view">${escapeHtml(item?.log || "")}</pre>`;  }  const categoryStats = {};  records.forEach((record) => {    const uiLog = parseUiLog(record.log);    const category = uiLog.error_category || uiLog.failed_step_detail?.category || (record.result === "passed" ? "通过" : "未知失败");    categoryStats[category] = (categoryStats[category] || 0) + 1;  });  return `    <div class="run-readable-log">      <section class="diagnosis-summary">        <strong>通过 ${escapeHtml(payload.passed_count ?? item?.passed_count ?? 0)} 条，失败 ${escapeHtml(payload.failed_count ?? item?.failed_count ?? 0)} 条</strong>        <div>${Object.entries(categoryStats).map(([key, count]) => `<span>${escapeHtml(key)}：${escapeHtml(count)}</span>`).join("")}</div>      </section>      ${records        .map((record, index) => {          const uiLog = parseUiLog(record.log);          const stepLogs = Array.isArray(uiLog.step_logs) ? uiLog.step_logs : [];          return `            <section class="diagnosis-card">              <div class="diagnosis-card-head">                <span>用例 ${index + 1}</span>                <strong>${escapeHtml(record.title || uiLog.case_name || "-")}</strong>                ${badge(record.result)}              </div>              ${                record.result !== "passed"                  ? `<div class="diagnosis-block"><span>失败原因</span><p>${escapeHtml(uiLog.error_category || uiLog.failed_step_detail?.category || uiLog.error || "未记录")}</p></div>                     <div class="diagnosis-block"><span>建议</span><p>${escapeHtml(uiLog.suggestion || uiLog.failed_step_detail?.suggestion || "查看截图和失败步骤继续排查")}</p></div>`                  : ""              }              ${                stepLogs.length                  ? `<div class="step-log-list">${stepLogs                      .map(                        (step) => `                          <div class="step-log-item ${step.status === "passed" ? "ok" : step.status === "skipped" ? "warn" : "fail"}">                            <div><strong>第${escapeHtml(step.index || "-")}步：${escapeHtml(step.name || step.action || "")}</strong>${badge(step.status || "-")}</div>                            <p>${escapeHtml(step.category || step.reason || step.error || step.used_locator || step.locator || "")}</p>                            <small>耗时：${escapeHtml(step.duration_ms ?? "-")} ms；URL：${escapeHtml(step.current_url || "-")}</small>                          </div>                        `,                      )                      .join("")}</div>`                  : `<pre class="mini-log">${escapeHtml(record.log || "")}</pre>`              }              <details class="diagnosis-detail"><summary>查看原始日志</summary><pre>${escapeHtml(record.log || "")}</pre></details>            </section>          `;        })        .join("")}    </div>  `;}function showFunctionalRunScreenshots(item) {  const rows = functionalRunScreenshotRows(item);  const body = rows.length    ? `      <div class="run-screenshot-list">        ${rows          .map(            (row) => `              <div class="run-screenshot-item">                <div>                  <strong>${escapeHtml(row.title)}</strong>                  <span>${badge(row.result)}</span>                </div>                ${                  row.recordId && row.screenshot                    ? `<button class="btn secondary" data-run-shot-record="${row.recordId}">查看截图</button>`                    : `<span class="muted-text">暂无截图</span>`                }              </div>            `,          )          .join("")}      </div>    `    : `<div class="empty">暂无截图</div>`;  modalEl.innerHTML = `    <div class="modal-head">      <h3>执行截图 #${item?.id || ""}</h3>      <button class="btn secondary" type="button" id="closeModal">关闭</button>    </div>    <div class="modal-body">${body}</div>  `;  modalEl.showModal();  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());  document.querySelectorAll("[data-run-shot-record]").forEach((button) => {    button.addEventListener("click", () => openProtectedFile(`/api/test-records/${button.dataset.runShotRecord}/screenshot`));  });}function parseFunctionalDiagnosis(raw) {  if (!raw) return null;  if (typeof raw === "object") return raw;  try {    return JSON.parse(raw);  } catch {    return null;  }}function renderFunctionalDiagnosis(raw) {  const data = parseFunctionalDiagnosis(raw);  if (!data || !Array.isArray(data.failed_cases)) {    return `<pre class="log-view">${escapeHtml(raw || "")}</pre>`;  }  const failedCases = data.failed_cases.length    ? data.failed_cases        .map(          (item, index) => `            <section class="diagnosis-card">              <div class="diagnosis-card-head">                <span>失败用例 ${index + 1}</span>                <strong>${escapeHtml(item.case_title || "未知用例")}</strong>              </div>              <div class="diagnosis-grid">                <div><span>失败步骤</span><strong>${escapeHtml(item.failed_step_no ? `第 ${item.failed_step_no} 步` : "未定位到具体步骤")}</strong></div>                <div><span>失败现象</span><strong>${escapeHtml(item.failure || "-")}</strong></div>              </div>              <div class="diagnosis-block">                <span>步骤内容</span>                <p>${escapeHtml(item.failed_step || "-")}</p>              </div>              <div class="diagnosis-block">                <span>可能原因</span>                <p>${escapeHtml(item.likely_reason || "-")}</p>              </div>              ${                item.suggested_actions?.length                  ? `<div class="diagnosis-block"><span>建议排查</span><ul>${item.suggested_actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("")}</ul></div>`                  : ""              }              ${                item.record_id && item.screenshot                  ? `<div class="diagnosis-actions"><button class="btn secondary" data-diagnosis-shot="${item.record_id}">查看失败截图</button></div>`                  : `<div class="diagnosis-actions"><span class="muted-text">暂无失败截图</span></div>`              }              ${item.error_detail ? `<details class="diagnosis-detail"><summary>查看原始错误</summary><pre>${escapeHtml(item.error_detail)}</pre></details>` : ""}            </section>          `,        )        .join("")    : `<div class="empty">没有失败用例</div>`;  return `    <div class="diagnosis-view">      <section class="diagnosis-summary">        <strong>${escapeHtml(data.summary || "诊断完成")}</strong>        <div><span>通过：${escapeHtml(data.passed_count ?? 0)}</span><span>失败：${escapeHtml(data.failed_count ?? 0)}</span></div>      </section>      ${failedCases}      ${        data.overall_suggestions?.length          ? `<section class="diagnosis-card"><div class="diagnosis-card-head"><span>整体建议</span></div><ul>${data.overall_suggestions              .map((item) => `<li>${escapeHtml(item)}</li>`)              .join("")}</ul></section>`          : ""      }      ${data.model_warning ? `<p class="diagnosis-warning">${escapeHtml(data.model_warning)}</p>` : ""}    </div>  `;}async function diagnoseFunctionalRun(runId) {  try {    showToast("正在生成失败诊断");    const result = await api(`/api/functional-runs/${runId}/diagnose`, { method: "POST" });    modalEl.innerHTML = `      <div class="modal-head">        <h3>失败诊断 #${runId}</h3>        <button class="btn secondary" type="button" id="closeModal">关闭</button>      </div>      <div class="modal-body">${renderFunctionalDiagnosis(result.diagnosis || "")}</div>      <div class="modal-actions" style="padding:12px;text-align:right;border-top:1px solid #eee">        <button class="btn" id="healRunBtn" type="button" style="display:${result.run?.status === "failed" ? "inline-block" : "none"}">一键修复定位器</button>      </div>    `;    modalEl.showModal();    document.querySelector("#closeModal").addEventListener("click", async () => {      modalEl.close();      await renderFunctionalTests();    });    document.querySelector("#healRunBtn")?.addEventListener("click", async () => {      const btn = document.querySelector("#healRunBtn");      btn.disabled = true;      btn.textContent = "修复中...";      try {        const healResult = await api(`/api/functional-runs/${runId}/heal`, { method: "POST" });        const count = healResult.updated_count || 0;        if (count > 0) {          showToast(`已修复 ${count} 个定位器，涉及 ${(healResult.updated_cases || []).length} 个用例`);        } else {          showToast("未发现需要修复的定位器");        }        btn.textContent = "已修复";        modalEl.close();        await renderFunctionalTests();      } catch (e) {        showToast(e.message || "修复失败");        btn.disabled = false;        btn.textContent = "一键修复定位器";      }    });    document.querySelectorAll("[data-diagnosis-shot]").forEach((button) => {      button.addEventListener("click", () => openProtectedFile(`/api/test-records/${button.dataset.diagnosisShot}/screenshot`));    });  } catch (error) {    showToast(error.message);  }}async function renderUiCases() {  const projects = await getProjects();  const accounts = await api(`/api/test-accounts${queryString({ project_id: state.filters.projectId })}`);  const rows = await api(`/api/ui-cases${queryString({ project_id: state.filters.projectId })}`);  const projectName = (id) => (projects.find((item) => item.id === id) || {}).name || id;  contentEl().innerHTML = `    <div class="toolbar">      <div class="filters">        <div class="field compact"><label>项目</label><select id="uiProjectFilter">${optionList(projects, "id", "name", state.filters.projectId)}</select></div>      </div>      ${isAdmin() ? `<button class="btn" id="newUiCase">新增UI用例</button>` : ""}    </div>    ${renderTable(      [        { key: "id", label: "ID" },        { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },        { key: "case_name", label: "用例名称" },        { key: "page_url", label: "页面地址" },        { key: "timeout", label: "超时" },        { key: "account_profile_name", label: "测试账号", render: (row) => escapeHtml(row.account_profile_name || "跟随项目") },        { key: "status", label: "状态", render: (row) => badge(row.status) },        {          key: "actions",          label: "操作",          render: (row) => `            <div class="actions">              <button class="btn" data-run-ui="${row.id}">执行</button>              ${isAdmin() ? `<button class="btn secondary" data-edit-ui="${row.id}">编辑</button><button class="btn danger" data-del-ui="${row.id}">删除</button>` : ""}            </div>          `,        },      ],      rows,    )}  `;  document.querySelector("#uiProjectFilter").addEventListener("change", async (event) => {    state.filters.projectId = event.target.value;    localStorage.setItem("projectId", state.filters.projectId);    await renderUiCases();  });  document.querySelectorAll("[data-run-ui]").forEach((button) => {    const item = rows.find((row) => row.id === Number(button.dataset.runUi));    button.addEventListener("click", () => openUiExecuteForm(item, accounts, projects));  });  if (!isAdmin()) return;  const projectOptions = projects.map((item) => ({ value: item.id, label: item.name }));  document.querySelector("#newUiCase").addEventListener("click", () => uiCaseForm(null, projectOptions, accounts, projects));  document.querySelectorAll("[data-edit-ui]").forEach((button) => {    const item = rows.find((row) => row.id === Number(button.dataset.editUi));    button.addEventListener("click", () => uiCaseForm(item, projectOptions, accounts, projects));  });  document.querySelectorAll("[data-del-ui]").forEach((button) => {    button.addEventListener("click", () => deleteItem(`/api/ui-cases/${button.dataset.delUi}`, renderUiCases));  });}function uiCaseForm(item, projectOptions, accounts = [], projects = []) {  openForm(    item ? "编辑UI用例" : "新增UI用例",    [      { name: "project_id", label: "项目", type: "select", options: projectOptions, required: true },      { name: "case_name", label: "用例名称", required: true },      { name: "page_url", label: "页面地址", required: true },      { name: "steps", label: "步骤 JSON", type: "textarea", rows: 8, default: '[{"action":"goto","value":"https://example.com"},{"action":"text_assert","locator":"body","value":"Example"}]' },      { name: "timeout", label: "超时秒数", type: "number", default: 30 },      {        name: "__account_profile_id",        label: "用例账号",        type: "select",        options: [{ value: "", label: "跟随项目默认账号" }, ...(accounts || []).map((account) => ({ value: account.id, label: accountLabel(account, projects) }))],      },      {        name: "status",        label: "状态",        type: "select",        options: [          { value: "active", label: "启用" },          { value: "inactive", label: "停用" },        ],        default: "active",      },    ],    { ...item, __account_profile_id: item?.account_profile_id || "" },    async (data) => {      const accountProfileId = data.__account_profile_id;      delete data.__account_profile_id;      const saved = await api(item ? `/api/ui-cases/${item.id}` : "/api/ui-cases", { method: item ? "PUT" : "POST", body: data });      await saveTestAccountBinding("ui_case", saved.id, accountProfileId);      showToast("已保存");      await renderUiCases();    },  );}function openUiExecuteForm(item, accounts = [], projects = []) {  if (!item) return;  let steps = [];  try {    steps = JSON.parse(item.steps || "[]");  } catch {    steps = [];  }  const text = JSON.stringify(steps);  const names = new Set();  text.replace(/\{\{\s*([A-Za-z_][A-Za-z0-9_$]*)\s*\}\}/g, (_, name) => {    names.add(name.replace(/^\$/, ""));    return "";  });  ["username", "password", "code"].forEach((name) => names.add(name));  const runtimeFields = [...names]    .filter((name) => !["timestamp", "datetime", "date", "uuid", "random_int", "random_str", "random_phone", "random_email"].includes(name))    .map((name) => {      const meta = FUNCTIONAL_RUNTIME_FIELD_META[name] || {};      return { name, label: meta.label || name, type: meta.type || "text", placeholder: meta.placeholder || "" };    });  const variableFields = runtimeFields.filter((field) => !ACCOUNT_RUNTIME_KEYS.has(field.name));  const accountFields = runtimeFields.filter((field) => ACCOUNT_RUNTIME_KEYS.has(field.name));  modalEl.innerHTML = `    <form id="uiExecuteForm">      <div class="modal-head">        <h3>执行 ${escapeHtml(item.case_name)}</h3>        <button class="btn secondary" type="button" id="closeModal">关闭</button>      </div>      <div class="modal-body">        <div class="form-grid">          <div class="field">            <label>账号来源</label>            <select name="account_mode" id="uiAccountMode">              <option value="default">使用默认账号（用例 > 项目）</option>              <option value="override">本次统一使用指定账号</option>              <option value="none">不使用账号档案</option>            </select>          </div>          <div class="field" id="uiAccountPicker" hidden>            <label>本次统一账号</label>            <select name="account_profile_id">${accountOptions(accounts, "", projects, "请选择测试账号")}</select>          </div>          <div class="field">            <label>当前默认</label>            <input type="text" value="${escapeHtml(item.account_profile_name || "按项目默认账号解析")}" disabled />          </div>        </div>        <details class="functional-requirement">          <summary>运行时变量</summary>          <div class="form-grid">${renderExecutionVariableFields(variableFields)}</div>        </details>        <details class="functional-requirement">          <summary>临时覆盖账号/验证码</summary>          <div class="form-grid">${renderExecutionVariableFields(accountFields)}</div>        </details>      </div>      <div class="modal-foot"><span></span><button class="btn" type="submit">执行</button></div>    </form>  `;  modalEl.showModal();  const modeEl = document.querySelector("#uiAccountMode");  const pickerEl = document.querySelector("#uiAccountPicker");  const syncPicker = () => {    pickerEl.hidden = modeEl.value !== "override";  };  modeEl.addEventListener("change", syncPicker);  syncPicker();  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());  document.querySelector("#uiExecuteForm").addEventListener("submit", async (event) => {    event.preventDefault();    try {      const payload = readFunctionalExecutionForm(event.currentTarget, variableFields, accountFields);      showToast("正在执行，请稍候");      const record = await api(`/api/ui-cases/${item.id}/execute`, { method: "POST", body: payload });      showToast(`执行完成：${record.result === "passed" ? "成功" : "失败"}`);      modalEl.close();      state.view = "records";      await renderShell();    } catch (error) {      showToast(error.message);    }  });}async function runCase(path) {  try {    showToast("正在执行，请稍候");    const record = await api(path, { method: "POST" });    showToast(`执行完成：${record.result === "passed" ? "成功" : "失败"}`);    state.view = "records";    await renderShell();  } catch (error) {    showToast(error.message);  }}function recordColumns() {  return [    { key: "id", label: "ID" },    { key: "case_type", label: "类型", render: (row) => badge(row.case_type) },    { key: "case_id", label: "用例ID" },    { key: "result", label: "结果", render: (row) => badge(row.result) },    { key: "execute_time", label: "执行时间" },    {      key: "actions",      label: "操作",      render: (row) => `        <div class="actions">          <button class="btn secondary" data-log="${row.id}">日志</button>          ${row.report_path ? `<button class="btn secondary" data-report="${row.id}">报告</button>` : ""}          ${row.screenshot ? `<button class="btn secondary" data-shot="${row.id}">截图</button>` : ""}        </div>      `,    },  ];}async function renderRecords() {  const projects = await getProjects();  const pid = state.filters.recordProjectId ?? "";  const page = state.filters.recordPage || 1;  const pageSize = 20;  const resp = await api(`/api/test-records${queryString({ project_id: pid, case_type: state.filters.recordType, page, page_size: pageSize })}`);  const rows = resp.items || resp;  const total = resp.total ?? rows.length;  const totalPages = Math.max(1, Math.ceil(total / pageSize));  contentEl().innerHTML = `    <div class="toolbar">      <div class="filters">        <div class="field compact"><label>项目</label><select id="recordProjectFilter">${optionList(projects, "id", "name", pid)}</select></div>        <div class="field compact"><label>类型</label><select id="recordTypeFilter">          <option value="">全部</option>          <option value="api" ${state.filters.recordType === "api" ? "selected" : ""}>api</option>          <option value="ui" ${state.filters.recordType === "ui" ? "selected" : ""}>ui</option>        </select></div>      </div>    </div>    ${renderTable(recordColumns(), rows)}    <div class="pagination">      <span class="page-info">共 ${total} 条，第 ${page}/${totalPages} 页</span>      <div class="page-buttons">        <button class="btn secondary page-btn" data-page="prev" ${page <= 1 ? "disabled" : ""}>上一页</button>        ${(() => {          const btns = [];          const start = Math.max(1, page - 2);          const end = Math.min(totalPages, page + 2);          if (start > 1) btns.push(`<button class="btn secondary page-btn" data-page="1">1</button><span class="page-ellipsis">...</span>`);          for (let i = start; i <= end; i++) btns.push(`<button class="btn page-btn ${i === page ? "active" : "secondary"}" data-page="${i}">${i}</button>`);          if (end < totalPages) btns.push(`<span class="page-ellipsis">...</span><button class="btn secondary page-btn" data-page="${totalPages}">${totalPages}</button>`);          return btns.join("");        })()}        <button class="btn secondary page-btn" data-page="next" ${page >= totalPages ? "disabled" : ""}>下一页</button>      </div>    </div>  `;  bindRecordActions(rows);  document.querySelector("#recordProjectFilter").addEventListener("change", async (event) => {    state.filters.recordProjectId = event.target.value;    state.filters.recordPage = 1;    await renderRecords();  });  document.querySelector("#recordTypeFilter").addEventListener("change", async (event) => {    state.filters.recordType = event.target.value;    state.filters.recordPage = 1;    await renderRecords();  });  document.querySelectorAll(".page-btn").forEach((btn) => {    btn.addEventListener("click", async () => {      const target = btn.dataset.page;      if (target === "prev") state.filters.recordPage = Math.max(1, page - 1);      else if (target === "next") state.filters.recordPage = Math.min(totalPages, page + 1);      else state.filters.recordPage = Number(target);      await renderRecords();    });  });}function bindRecordActions(rows) {  document.querySelectorAll("[data-log]").forEach((button) => {    const item = rows.find((row) => row.id === Number(button.dataset.log));    button.addEventListener("click", () => showLog(item));  });  document.querySelectorAll("[data-report]").forEach((button) => {    button.addEventListener("click", () => openProtectedFile(`/api/test-records/${button.dataset.report}/report`));  });  document.querySelectorAll("[data-shot]").forEach((button) => {    button.addEventListener("click", () => openProtectedFile(`/api/test-records/${button.dataset.shot}/screenshot`));  });}function showLog(item) {  const rawText = item.log || "";  let parsed = null;  try {    const candidate = JSON.parse(rawText);    if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) parsed = candidate;  } catch {}  // 从日志 JSON 中提取结构化汇总数据：优先取 summary 字段，其次取 variables 字段，或直接使用整个 parsed 对象
  let summary = null;  if (parsed?.summary && typeof parsed.summary === "object" && Object.keys(parsed.summary).length > 0) {    summary = parsed.summary;  } else if (parsed?.variables && typeof parsed.variables === "object" && Object.keys(parsed.variables).length > 0) {    summary = parsed.variables;  } else if (parsed && typeof parsed === "object" && Object.keys(parsed).length > 0) {    // 如果 parsed 本身看起来就像一个汇总（排除纯元数据字段），尝试直接使用
    const metaKeys = ["script", "mode", "started_at", "finished_at", "duration_ms", "steps", "batches", "shops", "login", "backend", "backend_porder", "_runtime"];    const hasMeta = metaKeys.some((k) => k in parsed);    if (!hasMeta) summary = parsed;  }  const isStructured = summary && typeof summary === "object" && Object.keys(summary).length > 0;  if (isStructured) {    const recordsHtml = item.case_id ? renderTable(      [        { key: "case_name", label: "用例" },        { key: "result", label: "结果", render: (row) => badge(row.result) },        { key: "id", label: "记录ID" },      ],      [{ id: item.id, case_name: "#" + item.case_id, result: item.result }],      false,    ) : "";    modalEl.innerHTML = `      <div class="modal-head">        <h3>脚本执行结果 #${item.id}</h3>        <button class="btn secondary" type="button" id="closeModal">关闭</button>      </div>      <div class="modal-body">        ${recordsHtml}        <div class="summary-wrap">${renderChineseSummary(summary)}</div>        <details class="summary-detail"><summary>查看原始日志</summary><pre class="log-view">${escapeHtml(rawText)}</pre></details>      </div>    `;  } else {    modalEl.innerHTML = `      <div class="modal-head">        <h3>执行日志 #${item.id}</h3>        <button class="btn secondary" type="button" id="closeModal">关闭</button>      </div>      <div class="modal-body"><pre class="log-view">${escapeHtml(rawText)}</pre></div>    `;  }  modalEl.showModal();  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());}async function renderUsers() {  if (!isAdmin()) {    state.view = "dashboard";    return renderShell();  }  const rows = await api("/api/users");  contentEl().innerHTML = `    <div class="toolbar"><p>仅 admin 可管理账号</p><button class="btn" id="newUser">新增用户</button></div>    ${renderTable(      [        { key: "id", label: "ID" },        { key: "username", label: "账号" },        { key: "role", label: "角色", render: (row) => badge(row.role) },        { key: "create_time", label: "创建时间" },        {          key: "actions",          label: "操作",          render: (row) => `<div class="actions"><button class="btn secondary" data-edit-user="${row.id}">编辑</button><button class="btn danger" data-del-user="${row.id}">删除</button></div>`,        },      ],      rows,    )}  `;  document.querySelector("#newUser").addEventListener("click", () => userForm());  document.querySelectorAll("[data-edit-user]").forEach((button) => {    const item = rows.find((row) => row.id === Number(button.dataset.editUser));    button.addEventListener("click", () => userForm(item));  });  document.querySelectorAll("[data-del-user]").forEach((button) => {    button.addEventListener("click", () => deleteItem(`/api/users/${button.dataset.delUser}`, renderUsers));  });}function userForm(item) {  openForm(    item ? "编辑用户" : "新增用户",    [      { name: "username", label: "账号", required: true },      { name: "password", label: item ? "新密码（可留空）" : "密码", type: "password", required: !item },      {        name: "role",        label: "角色",        type: "select",        options: [          { value: "admin", label: "admin" },          { value: "normal", label: "normal" },        ],        default: "normal",        required: true,      },    ],    item,    async (data) => {      if (item && !data.password) delete data.password;      await api(item ? `/api/users/${item.id}` : "/api/users", { method: item ? "PUT" : "POST", body: data });      showToast("已保存");      await renderUsers();    },  );}// ====== 实时浏览器录制（liveRecorder） ======
// 实时录制会话状态：保存 session_id、轮询定时器
const liveRecorderState = { sessionId: "", pollTimer: null };

// 取默认起始 URL：优先当前选中环境的 base_url，其次当前项目首个环境
async function liveRecorderDefaultStartUrl() {
  try {
    const envs = await api("/api/envs");
    const envId = state.factory.envId || state.filters.envId || "";
    const matched = envId ? envs.find((item) => String(item.id) === String(envId)) : null;
    if (matched?.base_url) return matched.base_url;
    const projectId = state.filters.projectId || "";
    const projectEnv = (projectId ? envs.find((item) => String(item.project_id) === String(projectId)) : null) || envs[0];
    return projectEnv?.base_url || "";
  } catch {
    return "";
  }
}

// 开始录制对话框：填写起始 URL，提交后创建会话
async function liveRecorderOpenStartDialog() {
  const defaultUrl = await liveRecorderDefaultStartUrl();
  modalEl.innerHTML = `
    <form id="liveRecorderStartForm">
      <div class="modal-head">
        <h3>实时录制</h3>
        <button class="btn secondary" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field">
            <label>起始 URL</label>
            <input name="start_url" required value="${escapeHtml(defaultUrl)}" placeholder="例如 https://example.com" />
          </div>
        </div>
        <p class="progress-note">点击开始录制后会启动一个可见浏览器，请在其中操作；操作完成后再回到本页面停止并保存。</p>
      </div>
      <div class="modal-foot"><span></span><button class="btn" type="submit">开始录制</button></div>
    </form>
  `;
  if (!modalEl.open) modalEl.showModal();
  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
  document.querySelector("#liveRecorderStartForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = readForm(event.currentTarget);
    const startUrl = String(data.start_url || "").trim();
    if (!startUrl) { showToast("请填写起始 URL"); return; }
    const submitBtn = event.currentTarget.querySelector('button[type="submit"]');
    try {
      if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "启动中..."; }
      const result = await api("/api/browser-record/sessions", { method: "POST", body: { start_url: startUrl } });
      liveRecorderState.sessionId = String(result.session_id || "");
      if (!liveRecorderState.sessionId) throw new Error("未拿到 session_id");
      // 注册关闭兜底：对话框关闭时若有 session_id，DELETE 清理
      modalEl.removeEventListener("close", liveRecorderHandleClose);
      modalEl.addEventListener("close", liveRecorderHandleClose, { once: true });
      liveRecorderOpenRecordingDialog();
    } catch (error) {
      showToast(error.message || "启动录制失败");
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "开始录制"; }
    }
  });
}

// 对话框关闭兜底：停止轮询并清理会话（避免浏览器进程泄漏）
function liveRecorderHandleClose() {
  liveRecorderStopPolling();
  const sessionId = liveRecorderState.sessionId;
  liveRecorderState.sessionId = "";
  if (sessionId) {
    api(`/api/browser-record/sessions/${sessionId}`, { method: "DELETE" }).catch(() => {});
  }
}

// 录制中对话框：实时事件列表 + 停止保存/取消
function liveRecorderOpenRecordingDialog() {
  modalEl.innerHTML = `
    <div class="modal-head">
      <h3>录制中...</h3>
      <button class="btn secondary" type="button" id="closeModal">关闭</button>
    </div>
    <div class="modal-body">
      <p class="progress-note">请在弹出的浏览器窗口中操作，事件将实时同步到这里。</p>
      <div class="panel-title"><h3>已捕获请求（<span id="liveRecorderCount">0</span>）</h3></div>
      <div id="liveRecorderEvents"><div class="empty">等待捕获请求...</div></div>
    </div>
    <div class="modal-foot">
      <button class="btn danger" type="button" id="liveRecorderCancel">取消录制</button>
      <button class="btn" type="button" id="liveRecorderSave">停止并保存</button>
    </div>
  `;
  if (!modalEl.open) modalEl.showModal();
  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
  document.querySelector("#liveRecorderSave").addEventListener("click", liveRecorderStopAndSave);
  document.querySelector("#liveRecorderCancel").addEventListener("click", liveRecorderCancel);
  liveRecorderStartPolling();
}

// 启动 1 秒轮询
function liveRecorderStartPolling() {
  liveRecorderStopPolling();
  liveRecorderState.pollTimer = window.setInterval(liveRecorderPollEvents, 1000);
  liveRecorderPollEvents();
}

function liveRecorderStopPolling() {
  if (liveRecorderState.pollTimer) {
    window.clearInterval(liveRecorderState.pollTimer);
    liveRecorderState.pollTimer = null;
  }
}

// 拉取事件并刷新列表
async function liveRecorderPollEvents() {
  if (!liveRecorderState.sessionId) return;
  try {
    const resp = await api(`/api/browser-record/sessions/${liveRecorderState.sessionId}/events`);
    const items = (resp.items || []).slice().sort((a, b) => String(a.started_at || "").localeCompare(String(b.started_at || "")));
    liveRecorderRenderEvents(items);
  } catch {
    // 轮询失败静默，避免刷屏
  }
}

function liveRecorderRenderEvents(items) {
  const countEl = document.querySelector("#liveRecorderCount");
  const listEl = document.querySelector("#liveRecorderEvents");
  if (countEl) countEl.textContent = String(items.length);
  if (!listEl) return;
  if (!items.length) { listEl.innerHTML = `<div class="empty">等待捕获请求...</div>`; return; }
  const rows = items.map((item, index) => ({
    index: index + 1,
    method: item.method || "-",
    path: item.path || item.url || "-",
    response_status: item.response_status || "-",
    body_preview: short(String(item.response_body || item.body || ""), 80),
  }));
  listEl.innerHTML = renderTable(
    [
      { key: "index", label: "序号" },
      { key: "method", label: "方法", render: (row) => badge(row.method) },
      { key: "path", label: "路径" },
      { key: "response_status", label: "状态码" },
      { key: "body_preview", label: "响应预览" },
    ],
    rows,
    false,
  );
}

// 停止轮询并弹出命名子对话框
function liveRecorderStopAndSave() {
  liveRecorderStopPolling();
  liveRecorderOpenSaveDialog();
}

// 命名子对话框：保存为 RecordedFlow
function liveRecorderOpenSaveDialog() {
  modalEl.innerHTML = `
    <form id="liveRecorderSaveForm">
      <div class="modal-head">
        <h3>保存录制流程</h3>
        <button class="btn secondary" type="button" id="liveRecorderBack">返回</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field"><label>名称</label><input name="name" required placeholder="例如：实时录制样品单流程" /></div>
          <div class="field"><label>描述</label><textarea name="description" rows="3" placeholder="流程用途说明（可选）"></textarea></div>
        </div>
      </div>
      <div class="modal-foot"><span></span><button class="btn" type="submit">保存</button></div>
    </form>
  `;
  if (!modalEl.open) modalEl.showModal();
  document.querySelector("#liveRecorderBack").addEventListener("click", () => liveRecorderOpenRecordingDialog());
  document.querySelector("#liveRecorderSaveForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = readForm(event.currentTarget);
    const name = String(data.name || "").trim();
    if (!name) { showToast("请填写流程名称"); return; }
    const submitBtn = event.currentTarget.querySelector('button[type="submit"]');
    try {
      if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = "保存中..."; }
      await api(`/api/browser-record/sessions/${liveRecorderState.sessionId}/save`, {
        method: "POST",
        body: { name, description: String(data.description || "").trim() },
      });
      // 保存成功：清空 sessionId 避免 close 兜底再 DELETE（后端已关闭会话）
      liveRecorderState.sessionId = "";
      modalEl.close();
      showToast("流程已保存");
      await renderDataScripts();
    } catch (error) {
      showToast(error.message || "保存失败");
      if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = "保存"; }
    }
  });
}

// 取消录制：确认后 DELETE 会话
async function liveRecorderCancel() {
  if (!window.confirm("确认取消录制？已捕获的请求将丢失")) return;
  liveRecorderStopPolling();
  const sessionId = liveRecorderState.sessionId;
  liveRecorderState.sessionId = "";
  if (sessionId) {
    try { await api(`/api/browser-record/sessions/${sessionId}`, { method: "DELETE" }); }
    catch { /* 静默：会话可能已关闭 */ }
  }
  modalEl.close();
}

const uiVisualExecutionState = { pollTimer: null, runId: "" };
function stopUiVisualPolling() {
  if (uiVisualExecutionState.pollTimer) {
    window.clearInterval(uiVisualExecutionState.pollTimer);
    uiVisualExecutionState.pollTimer = null;
  }
}
function uiVisualShort(value, max = 140) {
  const text = String(value ?? "");
  return text.length > max ? `${text.slice(0, max)}...` : text;
}
function uiVisualStatusText(status) {
  return ({ queued: "排队中", running: "执行中", passed: "成功", failed: "失败", error: "失败" }[status] || status || "-");
}
function uiVisualProgressPercent(run) {
  const steps = run.steps || [];
  if (run.status === "passed" || run.status === "failed") return 100;
  if (!steps.length) return run.status === "running" ? 20 : 5;
  const done = steps.filter((item) => ["passed", "failed", "skipped"].includes(item.status)).length;
  return Math.max(8, Math.min(95, Math.round((done / steps.length) * 100)));
}
function uiVisualExtractedHtml(run) {
  const extracted = run.extracted_vars || {};
  if (!extracted || !Object.keys(extracted).length) return `<div class="empty">暂无提取数据</div>`;
  if (typeof renderChineseSummary === "function") return `<div class="summary-wrap">${renderChineseSummary(extracted)}</div>`;
  return `<pre class="mini-log">${escapeHtml(JSON.stringify(extracted, null, 2))}</pre>`;
}
function renderUiVisualExecution(run, item) {
  const steps = run.steps || [];
  const percent = uiVisualProgressPercent(run);
  const stepRows = steps.map((step) => ({
    index: step.index,
    name: step.name || step.action || "-",
    action: step.action || "-",
    locator: uiVisualShort(step.used_locator || step.locator || "-"),
    status: uiVisualStatusText(step.status),
    duration_ms: step.duration_ms ? `${step.duration_ms} ms` : "-",
    result: step.error || step.reason || (step.extracted && Object.keys(step.extracted).length ? JSON.stringify(step.extracted) : ""),
  }));
  const screenshotHtml = run.latest_screenshot_url
    ? `<details class="functional-requirement" open><summary>最新截图</summary><img src="${escapeHtml(run.latest_screenshot_url)}" alt="执行截图" style="width:100%;max-height:420px;object-fit:contain;border:1px solid var(--line);border-radius:var(--radius-sm);background:#fff" /></details>`
    : `<div class="empty">等待截图生成...</div>`;
  const finalBlocks = run.status === "passed" || run.status === "failed"
    ? `
      <div class="functional-execution-summary">
        <div><span>执行结果</span><strong>${escapeHtml(uiVisualStatusText(run.status))}</strong></div>
        <div><span>记录ID</span><strong>${escapeHtml(run.record_id || "-")}</strong></div>
        <div><span>当前步骤</span><strong>${escapeHtml(run.current_step_index || 0)} / ${escapeHtml(steps.length || 0)}</strong></div>
        <div><span>可见浏览器</span><strong>${run.headed ? "已开启" : "未开启"}</strong></div>
      </div>
      ${run.error ? `<div class="alert error">${escapeHtml(run.error)}</div>` : ""}
      <details class="functional-requirement" open>
        <summary>最终数据</summary>
        ${uiVisualExtractedHtml(run)}
      </details>
    `
    : "";
  modalEl.innerHTML = `
    <div class="modal-head">
      <h3>可视化执行 ${escapeHtml(item?.case_name || run.case_name || "")}</h3>
      <button class="btn secondary" type="button" id="closeModal">关闭</button>
    </div>
    <div class="modal-body">
      <div class="progress-meta"><strong>${escapeHtml(uiVisualStatusText(run.status))}</strong><span>${percent}%</span></div>
      <div class="progress-track"><div class="progress-fill ${run.status === "failed" ? "failed" : ""}" style="width:${percent}%"></div></div>
      ${finalBlocks}
      <div class="functional-two-col">
        <div>
          <div class="panel-title"><h3>步骤执行</h3></div>
          ${renderTable(
            [
              { key: "index", label: "#" },
              { key: "name", label: "步骤" },
              { key: "action", label: "动作", render: (row) => badge(row.action) },
              { key: "locator", label: "定位器" },
              { key: "status", label: "状态", render: (row) => badge(row.status) },
              { key: "duration_ms", label: "耗时" },
              { key: "result", label: "结果" },
            ],
            stepRows,
            false,
          )}
        </div>
        <div>${screenshotHtml}</div>
      </div>
      <details class="summary-detail">
        <summary>查看执行事件</summary>
        <pre class="log-view">${escapeHtml(JSON.stringify(run.events || [], null, 2))}</pre>
      </details>
    </div>
    <div class="modal-foot">
      <span>${run.updated_at ? `更新时间：${escapeHtml(run.updated_at)}` : ""}</span>
      <div class="actions">
        ${run.record_id ? `<button class="btn secondary" type="button" id="uiVisualRecord">查看记录</button>` : ""}
        <button class="btn secondary" type="button" id="uiVisualClose">关闭</button>
      </div>
    </div>
  `;
  if (!modalEl.open) modalEl.showModal();
  document.querySelector("#closeModal")?.addEventListener("click", () => modalEl.close());
  document.querySelector("#uiVisualClose")?.addEventListener("click", () => modalEl.close());
  document.querySelector("#uiVisualRecord")?.addEventListener("click", async () => {
    stopUiVisualPolling();
    modalEl.close();
    state.view = "records";
    await renderShell();
  });
}
async function pollUiVisualExecution(item) {
  if (!uiVisualExecutionState.runId) return;
  try {
    const run = await api(`/api/ui-executions/${uiVisualExecutionState.runId}`);
    renderUiVisualExecution(run, item);
    if (run.status === "passed" || run.status === "failed") {
      stopUiVisualPolling();
      showToast(`执行完成：${run.status === "passed" ? "成功" : "失败"}`);
    }
  } catch (error) {
    stopUiVisualPolling();
    showToast(error.message || "执行状态查询失败");
  }
}
function startUiVisualPolling(run, item) {
  stopUiVisualPolling();
  uiVisualExecutionState.runId = run.run_id || "";
  renderUiVisualExecution(run, item);
  modalEl.addEventListener("close", stopUiVisualPolling, { once: true });
  uiVisualExecutionState.pollTimer = window.setInterval(() => pollUiVisualExecution(item), 1000);
  pollUiVisualExecution(item);
}
openUiExecuteForm = function (item, accounts = [], projects = []) {
  if (!item) return;
  let steps = [];
  try { steps = JSON.parse(item.steps || "[]"); } catch { steps = []; }
  const text = JSON.stringify(steps);
  const names = new Set();
  text.replace(/\{\{\s*([A-Za-z_][A-Za-z0-9_$]*)\s*\}\}/g, (_, name) => {
    names.add(name.replace(/^\$/, ""));
    return "";
  });
  ["username", "password", "code"].forEach((name) => names.add(name));
  const runtimeFields = [...names]
    .filter((name) => !["timestamp", "datetime", "date", "uuid", "random_int", "random_str", "random_phone", "random_email"].includes(name))
    .map((name) => {
      const meta = FUNCTIONAL_RUNTIME_FIELD_META[name] || {};
      return { name, label: meta.label || name, type: meta.type || "text", placeholder: meta.placeholder || "" };
    });
  const variableFields = runtimeFields.filter((field) => !ACCOUNT_RUNTIME_KEYS.has(field.name));
  const accountFields = runtimeFields.filter((field) => ACCOUNT_RUNTIME_KEYS.has(field.name));
  modalEl.innerHTML = `
    <form id="uiExecuteForm">
      <div class="modal-head">
        <h3>执行 ${escapeHtml(item.case_name)}</h3>
        <button class="btn secondary" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field">
            <label>账号来源</label>
            <select name="account_mode" id="uiAccountMode">
              <option value="default">使用默认账号（用例 > 项目）</option>
              <option value="override">本次统一使用指定账号</option>
              <option value="none">不使用账号档案</option>
            </select>
          </div>
          <div class="field" id="uiAccountPicker" hidden>
            <label>本次统一账号</label>
            <select name="account_profile_id">${accountOptions(accounts, "", projects, "请选择测试账号")}</select>
          </div>
          <div class="field">
            <label>当前默认</label>
            <input type="text" value="${escapeHtml(item.account_profile_name || "按项目默认账号解析")}" disabled />
          </div>
          <label class="check-field"><input type="checkbox" name="headed" checked /> 弹出可见浏览器执行</label>
        </div>
        <details class="functional-requirement">
          <summary>运行时变量</summary>
          <div class="form-grid">${renderExecutionVariableFields(variableFields)}</div>
        </details>
        <details class="functional-requirement">
          <summary>临时覆盖账号/验证码</summary>
          <div class="form-grid">${renderExecutionVariableFields(accountFields)}</div>
        </details>
      </div>
      <div class="modal-foot"><span></span><button class="btn" type="submit">可视化执行</button></div>
    </form>
  `;
  if (!modalEl.open) modalEl.showModal();
  const modeEl = document.querySelector("#uiAccountMode");
  const pickerEl = document.querySelector("#uiAccountPicker");
  const syncPicker = () => { pickerEl.hidden = modeEl.value !== "override"; };
  modeEl.addEventListener("change", syncPicker);
  syncPicker();
  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
  document.querySelector("#uiExecuteForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submitButton = form.querySelector('button[type="submit"]');
    try {
      const payload = readFunctionalExecutionForm(form, variableFields, accountFields);
      payload.headed = Boolean(form.querySelector('input[name="headed"]')?.checked);
      if (submitButton) { submitButton.disabled = true; submitButton.textContent = "启动中..."; }
      showToast("正在启动可视化执行");
      const run = await api(`/api/ui-cases/${item.id}/visual-execute`, { method: "POST", body: payload });
      startUiVisualPolling(run, item);
    } catch (error) {
      showToast(error.message);
      if (submitButton) { submitButton.disabled = false; submitButton.textContent = "可视化执行"; }
    }
  });
};
const uiRecordState = { pollTimer: null, sessionId: "", latest: null };
function stopUiRecordPolling() {
  if (uiRecordState.pollTimer) {
    window.clearInterval(uiRecordState.pollTimer);
    uiRecordState.pollTimer = null;
  }
}
function uiRecordShort(value, max = 120) {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? "");
  return text.length > max ? `${text.slice(0, max)}...` : text;
}
function uiRecordStepPreviewRows(steps) {
  return (steps || []).map((step, index) => ({
    index: index + 1,
    name: step.name || step.action || "-",
    action: step.action || "-",
    locator: step.locator || "-",
    value: step.value ?? "",
  }));
}
function renderUiRecordPreview(data) {
  const countEl = document.querySelector("#uiRecordCount");
  const urlEl = document.querySelector("#uiRecordCurrentUrl");
  const stepsEl = document.querySelector("#uiRecordSteps");
  if (countEl) countEl.textContent = String(data?.count || 0);
  if (urlEl) urlEl.textContent = data?.current_url || data?.start_url || "-";
  if (stepsEl) {
    const rows = uiRecordStepPreviewRows(data?.preview_steps || []);
    stepsEl.innerHTML = renderTable(
      [
        { key: "index", label: "#" },
        { key: "name", label: "步骤" },
        { key: "action", label: "动作", render: (row) => badge(row.action) },
        { key: "locator", label: "定位器", render: (row) => escapeHtml(uiRecordShort(row.locator)) },
        { key: "value", label: "值", render: (row) => escapeHtml(uiRecordShort(row.value)) },
      ],
      rows,
      false,
    );
  }
}
async function pollUiRecordSession() {
  if (!uiRecordState.sessionId) return;
  try {
    const data = await api(`/api/ui-record/sessions/${uiRecordState.sessionId}/events`);
    uiRecordState.latest = data;
    renderUiRecordPreview(data);
  } catch (error) {
    stopUiRecordPolling();
    showToast(error.message || "录制状态查询失败");
  }
}
function startUiRecordPolling(session) {
  stopUiRecordPolling();
  uiRecordState.sessionId = session.session_id || "";
  uiRecordState.latest = session;
  renderUiRecordSessionDialog(session);
  uiRecordState.pollTimer = window.setInterval(pollUiRecordSession, 1000);
  pollUiRecordSession();
}
async function cancelUiRecordSession() {
  const sessionId = uiRecordState.sessionId;
  stopUiRecordPolling();
  uiRecordState.sessionId = "";
  uiRecordState.latest = null;
  if (sessionId) {
    try {
      await api(`/api/ui-record/sessions/${sessionId}`, { method: "DELETE" });
    } catch (error) {
      showToast(error.message || "取消录制失败");
    }
  }
  modalEl.close();
}
function openUiRecordSaveDialog() {
  stopUiRecordPolling();
  const latest = uiRecordState.latest || {};
  modalEl.innerHTML = `
    <form id="uiRecordSaveForm">
      <div class="modal-head">
        <h3>保存录制用例</h3>
        <button class="btn secondary" type="button" id="uiRecordBack">返回录制</button>
      </div>
      <div class="modal-body">
        <div class="form-grid">
          <div class="field"><label>用例名称</label><input value="${escapeHtml(latest.case_name || "")}" disabled /></div>
          <div class="field"><label>已捕获事件</label><input value="${escapeHtml(latest.count || 0)}" disabled /></div>
          <div class="field"><label>最终URL</label><input value="${escapeHtml(latest.current_url || latest.start_url || "")}" disabled /></div>
          <div class="field"><label>页面文案断言（可选）</label><input name="assertion_text" placeholder="例如：保存成功、登录成功" /></div>
        </div>
        <div id="uiRecordSteps">${renderTable(
          [
            { key: "index", label: "#" },
            { key: "name", label: "步骤" },
            { key: "action", label: "动作", render: (row) => badge(row.action) },
            { key: "locator", label: "定位器", render: (row) => escapeHtml(uiRecordShort(row.locator)) },
            { key: "value", label: "值", render: (row) => escapeHtml(uiRecordShort(row.value)) },
          ],
          uiRecordStepPreviewRows(latest.preview_steps || []),
          false,
        )}</div>
      </div>
      <div class="modal-foot">
        <span>保存后会生成草稿 UI 用例，可直接点执行复跑</span>
        <button class="btn" type="submit">保存用例</button>
      </div>
    </form>
  `;
  if (!modalEl.open) modalEl.showModal();
  document.querySelector("#uiRecordBack")?.addEventListener("click", () => {
    if (uiRecordState.sessionId) startUiRecordPolling(latest);
  });
  document.querySelector("#uiRecordSaveForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton) { submitButton.disabled = true; submitButton.textContent = "保存中..."; }
    try {
      const data = readForm(form);
      const result = await api(`/api/ui-record/sessions/${uiRecordState.sessionId}/save`, { method: "POST", body: data });
      uiRecordState.sessionId = "";
      uiRecordState.latest = null;
      showToast(`已保存UI用例 #${result.case?.id || ""}`);
      modalEl.close();
      await renderUiCases();
    } catch (error) {
      showToast(error.message);
      if (submitButton) { submitButton.disabled = false; submitButton.textContent = "保存用例"; }
    }
  });
}
function renderUiRecordSessionDialog(session) {
  modalEl.innerHTML = `
    <div class="modal-head">
      <h3>录制UI用例：${escapeHtml(session.case_name || "")}</h3>
      <button class="btn secondary" type="button" id="uiRecordCancelTop">取消</button>
    </div>
    <div class="modal-body">
      <section class="diagnosis-summary">
        <strong>${badge("running")} 请在弹出的浏览器中完成操作</strong>
        <div><span>事件数：<b id="uiRecordCount">${escapeHtml(session.count || 0)}</b></span><span>当前URL：<b id="uiRecordCurrentUrl">${escapeHtml(session.current_url || session.start_url || "-")}</b></span></div>
      </section>
      <div class="panel-title"><h3>步骤预览</h3></div>
      <div id="uiRecordSteps"><div class="empty">等待操作事件...</div></div>
    </div>
    <div class="modal-foot">
      <span>第一版支持当前标签页内的点击、输入、选择、勾选和最终URL断言</span>
      <div class="actions">
        <button class="btn secondary" type="button" id="uiRecordCancel">取消录制</button>
        <button class="btn" type="button" id="uiRecordSave">停止并保存</button>
      </div>
    </div>
  `;
  if (!modalEl.open) modalEl.showModal();
  modalEl.addEventListener("close", stopUiRecordPolling, { once: true });
  document.querySelector("#uiRecordCancelTop")?.addEventListener("click", cancelUiRecordSession);
  document.querySelector("#uiRecordCancel")?.addEventListener("click", cancelUiRecordSession);
  document.querySelector("#uiRecordSave")?.addEventListener("click", openUiRecordSaveDialog);
  renderUiRecordPreview(session);
}
function openUiRecordStartDialog(projects) {
  if (!projects.length) {
    showToast("请先创建项目");
    return;
  }
  const projectOptions = projects.map((item) => ({ value: item.id, label: item.name }));
  openForm(
    "录制UI用例",
    [
      { name: "project_id", label: "项目", type: "select", options: projectOptions, required: true },
      { name: "case_name", label: "用例名称", required: true },
      { name: "start_url", label: "起始URL", required: true },
    ],
    { project_id: state.filters.projectId || projects[0]?.id || "" },
    async (data) => {
      showToast("正在启动可视化浏览器");
      const session = await api("/api/ui-record/sessions", { method: "POST", body: data });
      showToast("录制已开始");
      startUiRecordPolling(session);
    },
    "开始录制",
  );
}
renderUiCases = async function () {
  const projects = await getProjects();
  const accounts = await api(`/api/test-accounts${queryString({ project_id: state.filters.projectId })}`);
  const rows = await api(`/api/ui-cases${queryString({ project_id: state.filters.projectId })}`);
  const projectName = (id) => (projects.find((item) => item.id === id) || {}).name || id;
  contentEl().innerHTML = `
    <div class="toolbar">
      <div class="filters">
        <div class="field compact"><label>项目</label><select id="uiProjectFilter">${optionList(projects, "id", "name", state.filters.projectId)}</select></div>
      </div>
      ${isAdmin() ? `<div class="actions"><button class="btn" id="recordUiCase">录制UI用例</button><button class="btn secondary" id="newUiCase">新增UI用例</button></div>` : ""}
    </div>
    ${renderTable(
      [
        { key: "id", label: "ID" },
        { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },
        { key: "case_name", label: "用例名称" },
        { key: "page_url", label: "页面地址" },
        { key: "timeout", label: "超时" },
        { key: "account_profile_name", label: "测试账号", render: (row) => escapeHtml(row.account_profile_name || "跟随项目") },
        { key: "status", label: "状态", render: (row) => badge(row.status) },
        {
          key: "actions",
          label: "操作",
          render: (row) => `
            <div class="actions">
              <button class="btn" data-run-ui="${row.id}">执行</button>
              ${isAdmin() ? `<button class="btn secondary" data-edit-ui="${row.id}">编辑</button><button class="btn danger" data-del-ui="${row.id}">删除</button>` : ""}
            </div>
          `,
        },
      ],
      rows,
    )}
  `;
  document.querySelector("#uiProjectFilter").addEventListener("change", async (event) => {
    state.filters.projectId = event.target.value;
    localStorage.setItem("projectId", state.filters.projectId);
    await renderUiCases();
  });
  document.querySelectorAll("[data-run-ui]").forEach((button) => {
    const item = rows.find((row) => row.id === Number(button.dataset.runUi));
    button.addEventListener("click", () => openUiExecuteForm(item, accounts, projects));
  });
  if (!isAdmin()) return;
  const projectOptions = projects.map((item) => ({ value: item.id, label: item.name }));
  document.querySelector("#recordUiCase")?.addEventListener("click", () => openUiRecordStartDialog(projects));
  document.querySelector("#newUiCase")?.addEventListener("click", () => uiCaseForm(null, projectOptions, accounts, projects));
  document.querySelectorAll("[data-edit-ui]").forEach((button) => {
    const item = rows.find((row) => row.id === Number(button.dataset.editUi));
    button.addEventListener("click", () => uiCaseForm(item, projectOptions, accounts, projects));
  });
  document.querySelectorAll("[data-del-ui]").forEach((button) => {
    button.addEventListener("click", () => deleteItem(`/api/ui-cases/${button.dataset.delUi}`, renderUiCases));
  });
};
async function bootstrap() {  if (!state.token) {    renderLogin();    return;  }  try {    await renderShell();  } catch {    renderLogin();  }}bootstrap();
Promise.resolve().then(() => {
  if (typeof saveTestAccountBinding === "function") {
    const originalSaveTestAccountBinding = saveTestAccountBinding;
    saveTestAccountBinding = async function (...args) {
      const result = await originalSaveTestAccountBinding.apply(this, args);
      invalidateProjectsCache();
      return result;
    };
  }

  if (typeof openTestAccountForm === "function") {
    const originalOpenTestAccountForm = openTestAccountForm;
    openTestAccountForm = function (item, projects, afterSave = renderProjects) {
      const refreshAfterCacheClear = async (...args) => {
        invalidateProjectsCache();
        if (afterSave) return afterSave(...args);
      };
      return originalOpenTestAccountForm.call(this, item, projects, refreshAfterCacheClear);
    };
  }
});
