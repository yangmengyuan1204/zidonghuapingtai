const state = {
  token: localStorage.getItem("token") || "",
  user: null,
  view: "dashboard",
  filters: {
    projectId: localStorage.getItem("projectId") || "",
    envId: "",
    recordType: "",
  },
  selectedApiIds: new Set(),
  factory: {
    flowId: localStorage.getItem("factoryFlowId") || "",
    projectId: localStorage.getItem("factoryProjectId") || localStorage.getItem("projectId") || "",
    envId: localStorage.getItem("factoryEnvId") || "",
    caseIds: JSON.parse(localStorage.getItem("factoryCaseIds") || "[]"),
    variables: localStorage.getItem("factoryVariables") || '{\n  "keyword": "test",\n  "account": "abner"\n}',
    editing: false,
  },
};

const views = [
  { key: "dashboard", label: "首页" },
  { key: "projects", label: "项目管理" },
  { key: "apiCases", label: "接口管理" },
  { key: "dataScripts", label: "数据脚本" },
  { key: "uiCases", label: "UI测试" },
  { key: "records", label: "报告中心" },
  { key: "users", label: "用户管理", adminOnly: true },
];

const FLOW_STORAGE_KEY = "dataFactoryFlows";
const DELETED_BUILTIN_KEY = "dataFactoryDeletedBuiltins";
const BUILTIN_FLOW_DEFINITIONS = {
  shopping_cart: { id: "shopping_cart_builtin", name: "\u5546\u54c1\u8d2d\u7269\u8f66" },
  order_quote: { id: "order_quote_builtin", name: "\u8ba2\u5355\u62a5\u4ef7" },
  balance_payment: { id: "balance_payment_builtin", name: "\u4f59\u989d\u652f\u4ed8" },
  bank_payment: { id: "bank_payment_builtin", name: "\u94f6\u884c\u652f\u4ed8" },
  purchase_to_shelf: { id: "purchase_to_shelf_builtin", name: "\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6" },
  purchase_to_shelf_chain: {
    id: "purchase_to_shelf_chain_builtin",
    name: "\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6(\u7ec4\u5408\u811a\u672c)",
  },
  warehouse_delivery: { id: "warehouse_delivery_builtin", name: "\u4ed3\u5e93\u63d0\u51fa\u914d\u9001\u5355" },
};

const appEl = document.querySelector("#app");
const toastEl = document.querySelector("#toast");
const modalEl = document.querySelector("#modal");

function isAdmin() {
  return state.user && state.user.role === "admin";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function short(value, length = 140) {
  const text = String(value ?? "");
  return text.length > length ? `${text.slice(0, length)}...` : text;
}

function showToast(message) {
  toastEl.textContent = message;
  toastEl.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toastEl.hidden = true;
  }, 2600);
}

async function copyText(text, label = "\u5185\u5bb9") {
  const value = String(text || "").trim();
  if (!value) {
    showToast("\u6ca1\u6709\u53ef\u590d\u5236\u7684\u5185\u5bb9");
    return;
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.setAttribute("readonly", "readonly");
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    showToast(`${label}\u5df2\u590d\u5236`);
  } catch {
    showToast("\u590d\u5236\u5931\u8d25\uff0c\u8bf7\u624b\u52a8\u590d\u5236");
  }
}

function queryString(params) {
  const query = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) query.set(key, value);
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

function parseJsonText(text, fallback = {}) {
  const raw = String(text || "").trim();
  if (!raw) return fallback;
  return JSON.parse(raw);
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const requestOptions = { ...options };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (requestOptions.body && typeof requestOptions.body !== "string") {
    headers["Content-Type"] = "application/json";
    requestOptions.body = JSON.stringify(requestOptions.body);
  }
  const response = await fetch(path, { ...requestOptions, headers });
  if (response.status === 401) {
    localStorage.removeItem("token");
    state.token = "";
    state.user = null;
    renderLogin();
    throw new Error("登录已失效");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail || detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

async function openProtectedFile(path) {
  const response = await fetch(path, {
    headers: { Authorization: `Bearer ${state.token}` },
  });
  if (!response.ok) {
    showToast("文件不存在或无权访问");
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener,noreferrer");
}

function renderLogin() {
  appEl.innerHTML = `
    <section class="login-wrap">
      <form class="login-panel" id="loginForm">
        <h1>自动化测试平台</h1>
        <p>默认管理员：admin / admin123</p>
        <div class="form-grid">
          <div class="field">
            <label for="username">账号</label>
            <input id="username" name="username" autocomplete="username" required value="admin" />
          </div>
          <div class="field">
            <label for="password">密码</label>
            <input id="password" name="password" type="password" autocomplete="current-password" required value="admin123" />
          </div>
          <button class="btn" type="submit">登录</button>
        </div>
      </form>
    </section>
  `;
  document.querySelector("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const result = await api("/api/auth/login", {
        method: "POST",
        body: {
          username: form.get("username"),
          password: form.get("password"),
        },
      });
      state.token = result.access_token;
      state.user = result.user;
      localStorage.setItem("token", state.token);
      await renderShell();
    } catch (error) {
      showToast(error.message);
    }
  });
}

async function renderShell() {
  if (!state.user) state.user = await api("/api/auth/me");
  const nav = views
    .filter((item) => !item.adminOnly || isAdmin())
    .map((item) => `<button class="${state.view === item.key ? "active" : ""}" data-view="${item.key}">${escapeHtml(item.label)}</button>`)
    .join("");

  appEl.innerHTML = `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand">
          <strong>测试平台</strong>
          <span>${escapeHtml(state.user.username)}</span>
        </div>
        <nav class="nav">${nav}</nav>
        <div class="sidebar-foot"><span class="role-pill">${escapeHtml(state.user.role)}</span></div>
      </aside>
      <main class="main">
        <header class="topbar">
          <h2>${escapeHtml((views.find((v) => v.key === state.view) || views[0]).label)}</h2>
          <button class="btn secondary" id="logoutBtn" type="button">退出</button>
        </header>
        <section class="content" id="content"></section>
      </main>
    </div>
  `;

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.view = button.dataset.view;
      await renderShell();
    });
  });
  document.querySelector("#logoutBtn").addEventListener("click", () => {
    localStorage.removeItem("token");
    state.token = "";
    state.user = null;
    renderLogin();
  });
  await renderCurrentView();
}

function contentEl() {
  return document.querySelector("#content");
}

function badge(value) {
  const labels = {
    passed: "\u6210\u529f",
    failed: "\u5931\u8d25",
    active: "\u542f\u7528",
    inactive: "\u505c\u7528",
    admin: "\u4e3b\u8d26\u53f7",
    normal: "\u5b50\u8d26\u53f7",
    api: "\u63a5\u53e3",
    ui: "UI",
  };
  const statusClassMap = {
    passed: "ok",
    failed: "fail",
    active: "ok",
    inactive: "warn",
  };
  const text = escapeHtml(labels[value] || value || "-");
  const cls = statusClassMap[value] || "";
  return `<span class="badge ${cls}">${text}</span>`;
}

function renderTable(columns, rows, framed = true) {
  if (!rows.length) return framed ? `<div class="panel"><div class="empty">暂无数据</div></div>` : `<div class="empty">暂无数据</div>`;
  const head = columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("");
  const body = rows
    .map(
      (row) => `
        <tr>
          ${columns
            .map((column) => {
              const raw = column.render ? column.render(row) : escapeHtml(short(row[column.key]));
              return `<td>${raw}</td>`;
            })
            .join("")}
        </tr>
      `,
    )
    .join("");
  return `<div class="${framed ? "panel " : ""}table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function optionList(items, valueKey = "id", labelKey = "name", selected = "", allLabel = "全部") {
  return [
    `<option value="">${escapeHtml(allLabel)}</option>`,
    ...items.map((item) => `<option value="${escapeHtml(item[valueKey])}" ${String(item[valueKey]) === String(selected) ? "selected" : ""}>${escapeHtml(item[labelKey])}</option>`),
  ].join("");
}

function readFlows() {
  try {
    const flows = JSON.parse(localStorage.getItem(FLOW_STORAGE_KEY) || "[]");
    return Array.isArray(flows) ? flows : [];
  } catch {
    return [];
  }
}

function writeFlows(flows) {
  localStorage.setItem(FLOW_STORAGE_KEY, JSON.stringify(flows));
}

function readDeletedBuiltins() {
  try {
    const ids = JSON.parse(localStorage.getItem(DELETED_BUILTIN_KEY) || "[]");
    return Array.isArray(ids) ? ids : [];
  } catch {
    return [];
  }
}

function writeDeletedBuiltins(ids) {
  localStorage.setItem(DELETED_BUILTIN_KEY, JSON.stringify(ids));
}

function isBuiltinDeleted(id) {
  return readDeletedBuiltins().includes(id);
}

function markBuiltinDeleted(id) {
  const ids = readDeletedBuiltins();
  if (!ids.includes(id)) {
    ids.push(id);
    writeDeletedBuiltins(ids);
  }
}

function builtinDefinitionForFlow(flow) {
  if (!flow) return null;
  const directMatch = Object.values(BUILTIN_FLOW_DEFINITIONS).find((item) => item.id === flow.id);
  if (directMatch) return directMatch;
  const typeMatch = BUILTIN_FLOW_DEFINITIONS[flow.scriptType];
  if (typeMatch && flow.name === typeMatch.name) return typeMatch;
  return null;
}

function isDeletedBuiltinFlow(flow) {
  const definition = builtinDefinitionForFlow(flow);
  return Boolean(definition && isBuiltinDeleted(definition.id));
}

function newFlowId() {
  return `flow_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
}

function uniqueList(items) {
  const seen = new Set();
  const result = [];
  (items || []).forEach((item) => {
    const text = String(item || "").trim();
    const key = text.toLowerCase();
    if (text && !seen.has(key)) {
      seen.add(key);
      result.push(text);
    }
  });
  return result;
}

function listValue(value) {
  if (Array.isArray(value)) return value;
  if (typeof value === "string") {
    return value.split(",").map((item) => item.trim()).filter(Boolean);
  }
  return [];
}

function ensureShoppingCartScript(flows, projects, envs, cases) {
  if (isBuiltinDeleted("shopping_cart_builtin")) return flows;
  const scriptName = "\u5546\u54c1\u8d2d\u7269\u8f66";
  const login = cases.find((item) => item.case_name === "test-\u767b\u5f55");
  const search = cases.find((item) => item.case_name === "test-\u641c\u7d22\u5546\u54c1");
  const detail = cases.find((item) => item.case_name === "test-\u5546\u54c1\u8be6\u60c5");
  const cart = cases.find((item) => item.case_name === "test-\u52a0\u5165\u8d2d\u7269\u8f66");
  const env = envs.find((item) => item.env_name === "test-\u767b\u5f55") || envs[0];
  const projectId = env?.project_id || projects[0]?.id || "";
  const caseIds = [login, search, detail, cart].filter(Boolean).map((item) => item.id);
  if (!env || caseIds.length < 4) return flows;
  const loginBody = parseJsonText(login?.body || "{}", {});
  const existingIndex = flows.findIndex((flow) => flow.id === "shopping_cart_builtin") >= 0
    ? flows.findIndex((flow) => flow.id === "shopping_cart_builtin")
    : flows.findIndex((flow) => flow.name === scriptName);
  const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};
  let existingVariables = {};
  try {
    existingVariables = parseJsonText(existingFlow.variables || "{}", {});
  } catch {
    existingVariables = {};
  }
  const defaultVariables = {
    keywords: ["\u8863\u670d", "\u978b\u5b50", "\u978b", "usp", "USP", "\u5305", "\u5e3d\u5b50", "\u88d9\u5b50", "\u8033\u73af", "\u889c\u5b50", "\u624b\u673a\u58f3", "\u624b\u8868", "\u9879\u94fe", "\u6c34\u676f", "\u6587\u5177", "\u6536\u7eb3"],
    preferred_keywords: ["\u8863\u670d", "\u978b\u5b50", "\u978b", "\u5305"],
    boost_keywords: ["\u8863\u670d", "\u978b\u5b50", "\u5305"],
    random_keyword: true,
    shop_type: "1688",
    shop_types: ["1688"],
    target_shops: 4,
    per_shop: 5,
    page_size: 50,
    max_pages: 10,
    batch_size: 30,
    detail_workers: 4,
    quantities: "2,3,5",
    sleep: 0.2,
    no_fallback_sku: false,
    strict_shop_count: false,
    account: loginBody.account || "12345678990",
    password: loginBody.password || "123456",
    client_tool: "1",
  };
  const mergedVariables = { ...defaultVariables, ...existingVariables };
  mergedVariables.keywords = uniqueList([...listValue(existingVariables.keywords), ...defaultVariables.keywords]);
  mergedVariables.preferred_keywords = uniqueList([...listValue(existingVariables.preferred_keywords), ...defaultVariables.preferred_keywords]);
  mergedVariables.boost_keywords = uniqueList([...listValue(existingVariables.boost_keywords), ...defaultVariables.boost_keywords]);
  if (!mergedVariables.shop_type) mergedVariables.shop_type = defaultVariables.shop_type;
  if (!mergedVariables.target_shops) mergedVariables.target_shops = defaultVariables.target_shops;
  if (!mergedVariables.page_size) mergedVariables.page_size = defaultVariables.page_size;
  if (!mergedVariables.max_pages) mergedVariables.max_pages = defaultVariables.max_pages;
  if (!mergedVariables.batch_size) mergedVariables.batch_size = defaultVariables.batch_size;
  if (!mergedVariables.detail_workers) mergedVariables.detail_workers = defaultVariables.detail_workers;
  if (!mergedVariables.quantities) mergedVariables.quantities = defaultVariables.quantities;
  if (mergedVariables.sleep === undefined || mergedVariables.sleep === null) mergedVariables.sleep = defaultVariables.sleep;
  if (mergedVariables.client_tool === "2" || !mergedVariables.client_tool) mergedVariables.client_tool = defaultVariables.client_tool;
  if (existingVariables.account === "abner" && loginBody.account) mergedVariables.account = loginBody.account;
  if (existingVariables.password === "12345" && loginBody.password) mergedVariables.password = loginBody.password;
  if (!mergedVariables.client_tool && loginBody.client_tool) mergedVariables.client_tool = loginBody.client_tool;
  const nextFlow = {
    ...existingFlow,
    id: "shopping_cart_builtin",
    name: existingFlow.name || scriptName,
    scriptType: "shopping_cart",
    projectId: String(projectId),
    envId: String(env.id),
    caseIds,
    variables: JSON.stringify(mergedVariables, null, 2),
  };
  const next = existingIndex >= 0
    ? flows
        .map((flow, index) => (index === existingIndex ? nextFlow : flow))
        .filter((flow, index) => index === existingIndex || flow.id !== "shopping_cart_builtin")
    : [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensureOrderQuoteScript(flows, projects, envs, cases) {
  if (isBuiltinDeleted("order_quote_builtin")) return flows;
  const scriptName = "\u8ba2\u5355\u62a5\u4ef7";
  const login = cases.find((item) => item.case_name === "test-\u767b\u5f55");
  const env = envs.find((item) => item.env_name === "test-\u767b\u5f55") || envs[0];
  const projectId = env?.project_id || projects[0]?.id || "";
  if (!env) return flows;
  const loginBody = parseJsonText(login?.body || "{}", {});
  const existingIndex = flows.findIndex((flow) => flow.id === "order_quote_builtin") >= 0
    ? flows.findIndex((flow) => flow.id === "order_quote_builtin")
    : flows.findIndex((flow) => flow.name === scriptName);
  const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};
  let existingVariables = {};
  try {
    existingVariables = parseJsonText(existingFlow.variables || "{}", {});
  } catch {
    existingVariables = {};
  }
  const defaultVariables = {
    order_item_count: 2,
    order_item_num: 10,
    price_cut: 0,
    logistics_id: "1",
    create_type: "send",
    submit_order: true,
    run_backend_flow: true,
    skip_create_order: false,
    client_remark: "\u81ea\u52a8\u5316\u63d0\u51fa\u8ba2\u5355",
    quote_unit_price: "10",
    confirm_freight: "5",
    confirm_volume: "1x2x3",
    confirm_weight: 200,
    translate_is_temp: "0",
    confirm_is_temp: "0",
    offer_is_temp: "0",
    account: loginBody.account || "12345678990",
    password: loginBody.password || "123456",
    client_tool: "1",
    backend_account: "Y001",
    backend_password: "raku@123456``",
    backend_system: "1",
    backend_code: "wnm666",
  };
  const mergedVariables = { ...defaultVariables, ...existingVariables };
  if (!mergedVariables.order_item_count) mergedVariables.order_item_count = defaultVariables.order_item_count;
  if (!mergedVariables.order_item_num) mergedVariables.order_item_num = defaultVariables.order_item_num;
  if (!mergedVariables.logistics_id) mergedVariables.logistics_id = defaultVariables.logistics_id;
  if (!mergedVariables.create_type) mergedVariables.create_type = defaultVariables.create_type;
  if (mergedVariables.submit_order === undefined || mergedVariables.submit_order === null) {
    mergedVariables.submit_order = defaultVariables.submit_order;
  }
  if (mergedVariables.run_backend_flow === undefined || mergedVariables.run_backend_flow === null) {
    mergedVariables.run_backend_flow = defaultVariables.run_backend_flow;
  }
  if (!mergedVariables.quote_unit_price) mergedVariables.quote_unit_price = defaultVariables.quote_unit_price;
  if (!mergedVariables.confirm_freight) mergedVariables.confirm_freight = defaultVariables.confirm_freight;
  if (!mergedVariables.confirm_volume) mergedVariables.confirm_volume = defaultVariables.confirm_volume;
  if (!mergedVariables.confirm_weight) mergedVariables.confirm_weight = defaultVariables.confirm_weight;
  if (!mergedVariables.backend_system) mergedVariables.backend_system = defaultVariables.backend_system;
  if (!mergedVariables.backend_code) mergedVariables.backend_code = defaultVariables.backend_code;
  if (mergedVariables.client_tool === "2" || !mergedVariables.client_tool) mergedVariables.client_tool = defaultVariables.client_tool;
  if (existingVariables.account === "abner" && loginBody.account) mergedVariables.account = loginBody.account;
  if (existingVariables.password === "12345" && loginBody.password) mergedVariables.password = loginBody.password;
  const nextFlow = {
    ...existingFlow,
    id: "order_quote_builtin",
    name: existingFlow.name || scriptName,
    scriptType: "order_quote",
    projectId: String(projectId),
    envId: String(env.id),
    caseIds: existingFlow.caseIds || [],
    variables: JSON.stringify(mergedVariables, null, 2),
  };
  const next = existingIndex >= 0
    ? flows
        .map((flow, index) => (index === existingIndex ? nextFlow : flow))
        .filter((flow, index) => index === existingIndex || flow.id !== "order_quote_builtin")
    : [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensurePaymentScript(flows, projects, envs, cases, config) {
  if (isBuiltinDeleted(config.id)) return flows;
  const login = cases.find((item) => item.case_name === "test-\u767b\u5f55");
  const orderList = cases.find((item) => item.case_name === "\u6570\u636e\u811a\u672c-\u524d\u53f0\u8ba2\u5355\u5217\u8868");
  const payCase = cases.find((item) => item.case_name === config.caseName);
  const financeCase = cases.find((item) => item.case_name === "\u6570\u636e\u811a\u672c-\u8d22\u52a1\u786e\u8ba4\u5165\u91d1");
  const env = envs.find((item) => item.env_name === "test-\u767b\u5f55") || envs[0];
  const projectId = env?.project_id || projects[0]?.id || "";
  if (!env) return flows;
  const caseIds = [orderList, payCase, config.scriptType === "bank_payment" ? financeCase : null].filter(Boolean).map((item) => item.id);
  const loginBody = parseJsonText(login?.body || "{}", {});
  const existingIndex = flows.findIndex((flow) => flow.id === config.id) >= 0
    ? flows.findIndex((flow) => flow.id === config.id)
    : flows.findIndex((flow) => flow.name === config.name);
  const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};
  let existingVariables = {};
  try {
    existingVariables = parseJsonText(existingFlow.variables || "{}", {});
  } catch {
    existingVariables = {};
  }
  const commonVariables = {
    order_status_name: "\u7b49\u5f85\u4ed8\u6b3e",
    page: 1,
    page_size: 10,
    order_by: "desc",
    discounts_id: "",
    predict_logistics_price_is_pay: "0",
    account: loginBody.account || "12345678990",
    password: loginBody.password || "123456",
    client_tool: "1",
  };
  const typeVariables = config.scriptType === "bank_payment"
    ? {
        pay_bank_method: "1",
        pay_reach_after_days: 0,
        pay_name: "\u81ea\u52a8\u5316\u6d4b\u8bd5",
        pay_remark: "\u81ea\u52a8\u5316\u94f6\u884c\u4ed8\u6b3e",
        finance_confirm: true,
        finance_confirm_initial_delay: 2,
        finance_confirm_retries: 6,
        finance_confirm_delay: 2,
        backend_account: "Y001",
        backend_password: "raku@123456``",
        backend_system: "1",
        backend_code: "wnm666",
      }
    : {
        include_balance_pay_amount: false,
        balance_pay_fields: {},
      };
  const mergedVariables = { ...commonVariables, ...typeVariables, ...existingVariables };
  if (mergedVariables.client_tool === "2" || !mergedVariables.client_tool) mergedVariables.client_tool = commonVariables.client_tool;
  if (existingVariables.account === "abner" && loginBody.account) mergedVariables.account = loginBody.account;
  if (existingVariables.password === "12345" && loginBody.password) mergedVariables.password = loginBody.password;
  const nextFlow = {
    ...existingFlow,
    id: config.id,
    name: existingFlow.name || config.name,
    scriptType: config.scriptType,
    projectId: String(projectId),
    envId: String(env.id),
    caseIds: existingFlow.caseIds || caseIds,
    variables: JSON.stringify(mergedVariables, null, 2),
  };
  const next = existingIndex >= 0
    ? flows
        .map((flow, index) => (index === existingIndex ? nextFlow : flow))
        .filter((flow, index) => index === existingIndex || flow.id !== config.id)
    : [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensurePaymentScripts(flows, projects, envs, cases) {
  let next = ensurePaymentScript(flows, projects, envs, cases, {
    id: "balance_payment_builtin",
    name: "\u4f59\u989d\u652f\u4ed8",
    scriptType: "balance_payment",
    caseName: "\u6570\u636e\u811a\u672c-\u4f59\u989d\u652f\u4ed8\u8ba2\u5355",
  });
  next = ensurePaymentScript(next, projects, envs, cases, {
    id: "bank_payment_builtin",
    name: "\u94f6\u884c\u652f\u4ed8",
    scriptType: "bank_payment",
    caseName: "\u6570\u636e\u811a\u672c-\u94f6\u884c\u652f\u4ed8\u8ba2\u5355",
  });
  return next;
}

function ensurePurchaseToShelfScript(flows, projects, envs, cases) {
  if (isBuiltinDeleted("purchase_to_shelf_builtin")) return flows;
  const scriptName = "\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6";
  const login = cases.find((item) => item.case_name === "test-\u767b\u5f55");
  const env = envs.find((item) => item.env_name === "test-\u767b\u5f55") || envs[0];
  const projectId = env?.project_id || projects[0]?.id || "";
  if (!env) return flows;
  const caseNames = [
    "\u6570\u636e\u811a\u672c-\u5f85\u62cd\u4e0b\u5546\u54c1\u5217\u8868",
    "\u6570\u636e\u811a\u672c-\u4fdd\u5b58\u91c7\u8d2d\u4ea4\u6613\u53f7",
    "\u6570\u636e\u811a\u672c-\u6807\u8bb0\u5f85\u6539\u4ef7",
    "\u6570\u636e\u811a\u672c-\u63d0\u4ea4\u5f85\u8d22\u52a1\u4ed8\u6b3e",
    "\u6570\u636e\u811a\u672c-\u4ea4\u6613\u53f7\u5f85\u4ed8\u6b3e\u5217\u8868",
    "\u6570\u636e\u811a\u672c-\u4ea4\u6613\u53f7\u4ed8\u6b3e\u786e\u8ba4",
    "\u6570\u636e\u811a\u672c-\u6838\u67e5\u5546\u54c1\u5217\u8868",
    "\u6570\u636e\u811a\u672c-\u6838\u67e5\u5546\u54c1\u9884\u89c8",
    "\u6570\u636e\u811a\u672c-\u5f00\u59cb\u6838\u67e5",
    "\u6570\u636e\u811a\u672c-\u5e93\u4f4d\u9884\u89c8",
    "\u6570\u636e\u811a\u672c-\u4e0a\u67b6\u5165\u5e93",
  ];
  const caseIds = caseNames
    .map((name) => cases.find((item) => item.case_name === name))
    .filter(Boolean)
    .map((item) => item.id);
  const loginBody = parseJsonText(login?.body || "{}", {});
  const existingIndex = flows.findIndex((flow) => flow.id === "purchase_to_shelf_builtin") >= 0
    ? flows.findIndex((flow) => flow.id === "purchase_to_shelf_builtin")
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
    link_quote_balance_before_shelf: true,
    purchase_status: "\u5168\u90e8",
    purchase_item_limit: 0,
    purchase_unit_price: "10",
    purchase_freight: "0",
    purchase_transition_delay: 1,
    finance_wait_pay_status: "2",
    finance_confirm_retries: 8,
    finance_confirm_delay: 2,
    finance_days: 30,
    follow_status: "3",
    follow_retries: 8,
    follow_delay: 2,
    warehouse_index: "2",
    shelf_type_set: [1, 3],
    prefer_empty_grid: true,
    inspection_transition_delay: 1,
    account: loginBody.account || "12345678990",
    password: loginBody.password || "123456",
    client_tool: "1",
    backend_account: "Y001",
    backend_password: "raku@123456``",
    backend_system: "1",
    backend_code: "wnm666",
  };
  const mergedVariables = { ...defaultVariables, ...existingVariables };
  if (mergedVariables.link_quote_balance_before_shelf === undefined || mergedVariables.link_quote_balance_before_shelf === null) {
    mergedVariables.link_quote_balance_before_shelf = true;
  }
  if (!mergedVariables.purchase_status) mergedVariables.purchase_status = defaultVariables.purchase_status;
  if (!mergedVariables.finance_wait_pay_status) mergedVariables.finance_wait_pay_status = defaultVariables.finance_wait_pay_status;
  if (!mergedVariables.follow_status) mergedVariables.follow_status = defaultVariables.follow_status;
  if (!mergedVariables.warehouse_index) mergedVariables.warehouse_index = defaultVariables.warehouse_index;
  if (!Array.isArray(mergedVariables.shelf_type_set)) mergedVariables.shelf_type_set = defaultVariables.shelf_type_set;
  if (mergedVariables.prefer_empty_grid === false) mergedVariables.prefer_empty_grid = true;
  if (!mergedVariables.backend_system) mergedVariables.backend_system = defaultVariables.backend_system;
  if (!mergedVariables.backend_code) mergedVariables.backend_code = defaultVariables.backend_code;
  if (existingVariables.account === "abner" && loginBody.account) mergedVariables.account = loginBody.account;
  if (existingVariables.password === "12345" && loginBody.password) mergedVariables.password = loginBody.password;
  const nextFlow = {
    ...existingFlow,
    id: "purchase_to_shelf_builtin",
    name: existingFlow.name || scriptName,
    scriptType: "purchase_to_shelf",
    projectId: String(projectId),
    envId: String(env.id),
    caseIds: existingFlow.caseIds?.length ? existingFlow.caseIds : caseIds,
    variables: JSON.stringify(mergedVariables, null, 2),
  };
  const next = existingIndex >= 0
    ? flows
        .map((flow, index) => (index === existingIndex ? nextFlow : flow))
        .filter((flow, index) => index === existingIndex || flow.id !== "purchase_to_shelf_builtin")
    : [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensurePurchaseToShelfChainScript(flows, projects, envs, cases) {
  if (isBuiltinDeleted("purchase_to_shelf_chain_builtin")) return flows;
  const scriptName = "\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6(\u7ec4\u5408\u811a\u672c)";
  const login = cases.find((item) => item.case_name === "test-\u767b\u5f55");
  const env = envs.find((item) => item.env_name === "test-\u767b\u5f55") || envs[0];
  const projectId = env?.project_id || projects[0]?.id || "";
  if (!env) return flows;
  const loginBody = parseJsonText(login?.body || "{}", {});
  const existingIndex = flows.findIndex((flow) => flow.id === "purchase_to_shelf_chain_builtin") >= 0
    ? flows.findIndex((flow) => flow.id === "purchase_to_shelf_chain_builtin")
    : flows.findIndex((flow) => flow.name === scriptName);
  const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};
  let existingVariables = {};
  try {
    existingVariables = parseJsonText(existingFlow.variables || "{}", {});
  } catch {
    existingVariables = {};
  }
  const defaultVariables = {
    order_item_count: 2,
    order_item_num: 10,
    price_cut: "0",
    logistics_id: "1",
    client_remark: "\u81ea\u52a8\u5316\u63d0\u51fa\u8ba2\u5355",
    submit_order: true,
    run_backend_flow: true,
    purchase_status: "\u5168\u90e8",
    purchase_item_limit: 0,
    purchase_unit_price: "10",
    purchase_freight: "0",
    purchase_transition_delay: 1,
    finance_wait_pay_status: "2",
    finance_confirm_retries: 8,
    finance_confirm_delay: 2,
    finance_days: 30,
    follow_status: "3",
    follow_retries: 8,
    follow_delay: 2,
    warehouse_index: "2",
    shelf_type_set: [1, 3],
    prefer_empty_grid: true,
    inspection_transition_delay: 1,
    account: loginBody.account || "12345678990",
    password: loginBody.password || "123456",
    client_tool: "1",
    backend_account: "Y001",
    backend_password: "raku@123456``",
    backend_system: "1",
    backend_code: "wnm666",
  };
  const mergedVariables = { ...defaultVariables, ...existingVariables };
  if (!Array.isArray(mergedVariables.shelf_type_set)) mergedVariables.shelf_type_set = defaultVariables.shelf_type_set;
  if (mergedVariables.prefer_empty_grid === false) mergedVariables.prefer_empty_grid = true;
  if (existingVariables.account === "abner" && loginBody.account) mergedVariables.account = loginBody.account;
  if (existingVariables.password === "12345" && loginBody.password) mergedVariables.password = loginBody.password;
  const nextFlow = {
    ...existingFlow,
    id: "purchase_to_shelf_chain_builtin",
    name: existingFlow.name || scriptName,
    scriptType: "purchase_to_shelf_chain",
    projectId: String(projectId),
    envId: String(env.id),
    caseIds: [],
    variables: JSON.stringify(mergedVariables, null, 2),
  };
  const next = existingIndex >= 0
    ? flows
        .map((flow, index) => (index === existingIndex ? nextFlow : flow))
        .filter((flow, index) => index === existingIndex || (flow.id !== "purchase_to_shelf_chain_builtin" && flow.name !== scriptName))
    : [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function ensureWarehouseDeliveryScript(flows, projects, envs, cases) {
  if (isBuiltinDeleted("warehouse_delivery_builtin")) return flows;
  const scriptName = "\u4ed3\u5e93\u63d0\u51fa\u914d\u9001\u5355";
  const login = cases.find((item) => item.case_name === "test-\u767b\u5f55");
  const env = envs.find((item) => item.env_name === "test-\u767b\u5f55") || envs[0];
  const projectId = env?.project_id || projects[0]?.id || "";
  if (!env) return flows;
  const loginBody = parseJsonText(login?.body || "{}", {});
  const existingIndex = flows.findIndex((flow) => flow.id === "warehouse_delivery_builtin") >= 0
    ? flows.findIndex((flow) => flow.id === "warehouse_delivery_builtin")
    : flows.findIndex((flow) => flow.name === scriptName);
  const existingFlow = existingIndex >= 0 ? flows[existingIndex] : {};
  let existingVariables = {};
  try {
    existingVariables = parseJsonText(existingFlow.variables || "{}", {});
  } catch {
    existingVariables = {};
  }
  const defaultVariables = {
    order_detail_id: "",
    send_num: 1,
    porder_logistics_id: "14",
    client_warehouse_list: "/client/wms.stockAutoList",
    warehouse_keywords: "",
    warehouse_search_tag: "",
    children_id: "",
    for_sn_set: "",
    tag_set: "",
    sort_type: "",
    hasLabel: "",
    create_type: "send",
    client_remark: "",
    porder_suffix: "300001",
    run_backend_delivery_flow: true,
    backend_account: "Y001",
    backend_password: "raku@123456``",
    backend_system: "1",
    backend_code: "wnm666",
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
    receiver_address: {
      name: "\u6d4b\u8bd5",
      company: "\u6d4b\u8bd5\u516c\u53f8\u540d",
      address: "\u4f4f\u6240",
      zip: "12345678",
      mobile: "1353214567",
      tel: "0321-55786",
      name_rome: "\u30ed\u30fc\u30de\u5b57(\u6c0f\u540d)",
      address_rome: "\u30ed\u30fc\u30de\u5b57(\u4f4f\u6240)",
      corporate_name: "1234567891234",
      account: "1234567889789",
      standard_code: "1234567891235",
      title: "\u9648\u54e5\u6700\u7231\u5199bug",
    },
    importer_address: {
      name: "13123",
      company: "",
      address: "123123",
      zip: "1232132",
      mobile: "123123",
      tel: "",
      name_rome: "12312313",
      address_rome: "123123123",
      corporate_name: "",
      account: "\u30ea\u30a2\u30eb\u30bf\u30a4\u30e0\u53e3\u5ea7\u5c0f\u6768",
      standard_code: "\u6a19\u6e96\u30b3\u30fc\u30c9\u5c0f\u6768",
      title: "\u6c0f\u540d",
    },
  };
  const mergedVariables = { ...defaultVariables, ...existingVariables };
  if (!mergedVariables.receiver_address || typeof mergedVariables.receiver_address !== "object") {
    mergedVariables.receiver_address = defaultVariables.receiver_address;
  }
  if (!mergedVariables.importer_address || typeof mergedVariables.importer_address !== "object") {
    mergedVariables.importer_address = defaultVariables.importer_address;
  }
  if (!mergedVariables.send_num) mergedVariables.send_num = defaultVariables.send_num;
  if (!mergedVariables.porder_logistics_id) mergedVariables.porder_logistics_id = defaultVariables.porder_logistics_id;
  if (mergedVariables.run_backend_delivery_flow === undefined) mergedVariables.run_backend_delivery_flow = true;
  if (!mergedVariables.backend_account) mergedVariables.backend_account = defaultVariables.backend_account;
  if (!mergedVariables.backend_password) mergedVariables.backend_password = defaultVariables.backend_password;
  if (!mergedVariables.box_count) mergedVariables.box_count = defaultVariables.box_count;
  if (!mergedVariables.box_length) mergedVariables.box_length = defaultVariables.box_length;
  if (!mergedVariables.box_width) mergedVariables.box_width = defaultVariables.box_width;
  if (!mergedVariables.box_height) mergedVariables.box_height = defaultVariables.box_height;
  if (!mergedVariables.box_weight) mergedVariables.box_weight = defaultVariables.box_weight;
  if (!mergedVariables.delivery_quote_logistics_id) mergedVariables.delivery_quote_logistics_id = defaultVariables.delivery_quote_logistics_id;
  if (!mergedVariables.logistics_price_artificial) mergedVariables.logistics_price_artificial = defaultVariables.logistics_price_artificial;
  if (existingVariables.account === "abner" && loginBody.account) mergedVariables.account = loginBody.account;
  if (existingVariables.password === "12345" && loginBody.password) mergedVariables.password = loginBody.password;
  const nextFlow = {
    ...existingFlow,
    id: "warehouse_delivery_builtin",
    name: existingFlow.name || scriptName,
    scriptType: "warehouse_delivery",
    projectId: String(projectId),
    envId: String(env.id),
    caseIds: [],
    variables: JSON.stringify(mergedVariables, null, 2),
  };
  const next = existingIndex >= 0
    ? flows
        .map((flow, index) => (index === existingIndex ? nextFlow : flow))
        .filter((flow, index) => index === existingIndex || (flow.id !== "warehouse_delivery_builtin" && flow.name !== scriptName))
    : [...flows, nextFlow];
  writeFlows(next);
  return next;
}

function persistFactoryDraft() {
  localStorage.setItem("factoryFlowId", state.factory.flowId || "");
  localStorage.setItem("factoryProjectId", state.factory.projectId || "");
  localStorage.setItem("factoryEnvId", state.factory.envId || "");
  localStorage.setItem("factoryCaseIds", JSON.stringify(state.factory.caseIds || []));
  localStorage.setItem("factoryVariables", state.factory.variables || "");
}

function loadFlowToDraft(flow) {
  state.factory.flowId = flow?.id || "";
  state.factory.projectId = flow?.projectId || "";
  state.factory.envId = flow?.envId || "";
  state.factory.caseIds = [...(flow?.caseIds || [])];
  state.factory.variables = flow?.variables || '{\n  "keyword": "test",\n  "account": "abner"\n}';
  persistFactoryDraft();
}

function readForm(form) {
  const data = {};
  new FormData(form).forEach((value, key) => {
    const input = form.elements[key];
    data[key] = input && input.type === "number" ? (value === "" ? null : Number(value)) : value;
  });
  return data;
}

function openForm(title, fields, values, onSubmit, submitLabel = "保存") {
  const body = fields
    .map((field) => {
      const value = values?.[field.name] ?? field.default ?? "";
      if (field.type === "select") {
        const options = (field.options || [])
          .map((option) => `<option value="${escapeHtml(option.value)}" ${String(option.value) === String(value) ? "selected" : ""}>${escapeHtml(option.label)}</option>`)
          .join("");
        return `<div class="field"><label>${escapeHtml(field.label)}</label><select name="${escapeHtml(field.name)}" ${field.required ? "required" : ""}>${options}</select></div>`;
      }
      if (field.type === "textarea") {
        return `<div class="field"><label>${escapeHtml(field.label)}</label><textarea name="${escapeHtml(field.name)}" rows="${field.rows || 5}" ${field.required ? "required" : ""}>${escapeHtml(value)}</textarea></div>`;
      }
      return `<div class="field"><label>${escapeHtml(field.label)}</label><input name="${escapeHtml(field.name)}" type="${field.type || "text"}" value="${escapeHtml(value)}" ${field.required ? "required" : ""} /></div>`;
    })
    .join("");

  modalEl.innerHTML = `
    <form id="modalForm">
      <div class="modal-head">
        <h3>${escapeHtml(title)}</h3>
        <button class="btn secondary" value="cancel" formmethod="dialog" type="button" id="closeModal">关闭</button>
      </div>
      <div class="modal-body"><div class="form-grid">${body}</div></div>
      <div class="modal-foot"><span></span><button class="btn" type="submit">${escapeHtml(submitLabel)}</button></div>
    </form>
  `;
  modalEl.showModal();
  document.querySelector("#closeModal").addEventListener("click", async () => {
    modalEl.close();
    if (state.view === "dataScripts" && !state.factory.editing) {
      await renderDataScripts();
    }
  });
  document.querySelector("#modalForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await onSubmit(readForm(event.currentTarget));
      modalEl.close();
    } catch (error) {
      showToast(error.message);
    }
  });
}

async function deleteItem(path, afterDelete) {
  if (!window.confirm("确认删除这条数据？")) return;
  try {
    await api(path, { method: "DELETE" });
    showToast("已删除");
    await afterDelete();
  } catch (error) {
    showToast(error.message);
  }
}

async function renderCurrentView() {
  if (state.view === "dashboard") return renderDashboard();
  if (state.view === "projects") return renderProjects();
  if (state.view === "envs") return renderEnvs();
  if (state.view === "apiCases") return renderApiCases();
  if (state.view === "dataScripts") return state.factory.editing ? renderDataScriptEditor() : renderDataScripts();
  if (state.view === "uiCases") return renderUiCases();
  if (state.view === "records") return renderRecords();
  if (state.view === "users") return renderUsers();
}

async function renderDashboard() {
  const projects = await api("/api/projects");
  const data = await api(`/api/dashboard${queryString({ project_id: state.filters.projectId })}`);
  contentEl().innerHTML = `
    <div class="toolbar">
      <div class="filters">
        <div class="field compact">
          <label>项目</label>
          <select id="dashboardProject">${optionList(projects, "id", "name", state.filters.projectId)}</select>
        </div>
      </div>
    </div>
    <div class="stats">
      <div class="stat"><span>项目</span><strong>${data.project_count}</strong></div>
      <div class="stat"><span>环境</span><strong>${data.env_count}</strong></div>
      <div class="stat"><span>接口用例</span><strong>${data.api_case_count}</strong></div>
      <div class="stat"><span>UI用例</span><strong>${data.ui_case_count}</strong></div>
      <div class="stat"><span>执行记录</span><strong>${data.record_count}</strong></div>
    </div>
    <div class="panel-title"><h3>最近执行</h3></div>
    ${renderTable(recordColumns(), data.latest_records)}
  `;
  bindRecordActions(data.latest_records);
  document.querySelector("#dashboardProject").addEventListener("change", async (event) => {
    state.filters.projectId = event.target.value;
    localStorage.setItem("projectId", state.filters.projectId);
    await renderDashboard();
  });
}

async function renderProjects() {
  const [rows, allEnvs] = await Promise.all([api("/api/projects"), api("/api/envs")]);
  const projectName = (id) => (rows.find((item) => item.id === id) || {}).name || id;
  const envRows = state.filters.projectId ? allEnvs.filter((item) => String(item.project_id) === String(state.filters.projectId)) : allEnvs;
  contentEl().innerHTML = `
    <div class="toolbar"><p>${isAdmin() ? "项目配置" : "当前账号只读"}</p>${isAdmin() ? `<button class="btn" id="newProject">新增项目</button>` : ""}</div>
    ${renderTable(
      [
        { key: "id", label: "ID" },
        { key: "name", label: "项目名称" },
        { key: "desc", label: "描述" },
        { key: "create_time", label: "创建时间" },
        {
          key: "actions",
          label: "操作",
          render: (row) => (isAdmin() ? `<div class="actions"><button class="btn secondary" data-edit-project="${row.id}">编辑</button><button class="btn danger" data-del-project="${row.id}">删除</button></div>` : "-"),
        },
      ],
      rows,
    )}
    <section class="project-env-section">
      <div class="toolbar">
        <div class="filters">
          <div class="field compact"><label>项目环境配置</label><select id="projectEnvFilter">${optionList(rows, "id", "name", state.filters.projectId)}</select></div>
        </div>
        ${isAdmin() ? `<button class="btn" id="newProjectEnv">新增环境</button>` : ""}
      </div>
      ${renderTable(
        [
          { key: "id", label: "ID" },
          { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },
          { key: "env_name", label: "环境名称" },
          { key: "base_url", label: "Base URL" },
          { key: "timeout", label: "超时" },
          { key: "global_headers", label: "全局请求头", render: (row) => escapeHtml(short(row.global_headers)) },
          { key: "global_vars", label: "全局变量", render: (row) => escapeHtml(short(row.global_vars)) },
          {
            key: "actions",
            label: "操作",
            render: (row) => (isAdmin() ? `<div class="actions"><button class="btn secondary" data-edit-project-env="${row.id}">编辑</button><button class="btn danger" data-del-project-env="${row.id}">删除</button></div>` : "-"),
          },
        ],
        envRows,
      )}
    </section>
  `;
  document.querySelector("#projectEnvFilter").addEventListener("change", async (event) => {
    state.filters.projectId = event.target.value;
    localStorage.setItem("projectId", state.filters.projectId);
    await renderProjects();
  });
  if (!isAdmin()) return;
  document.querySelector("#newProject").addEventListener("click", () => projectForm());
  document.querySelectorAll("[data-edit-project]").forEach((button) => {
    const item = rows.find((row) => row.id === Number(button.dataset.editProject));
    button.addEventListener("click", () => projectForm(item));
  });
  document.querySelectorAll("[data-del-project]").forEach((button) => {
    button.addEventListener("click", () => deleteItem(`/api/projects/${button.dataset.delProject}`, renderProjects));
  });
  const envProjectOptions = rows.map((item) => ({ value: item.id, label: item.name }));
  document.querySelector("#newProjectEnv").addEventListener("click", () => envForm(null, envProjectOptions, renderProjects, state.filters.projectId || rows[0]?.id || ""));
  document.querySelectorAll("[data-edit-project-env]").forEach((button) => {
    const item = allEnvs.find((row) => row.id === Number(button.dataset.editProjectEnv));
    button.addEventListener("click", () => envForm(item, envProjectOptions, renderProjects));
  });
  document.querySelectorAll("[data-del-project-env]").forEach((button) => {
    button.addEventListener("click", () => deleteItem(`/api/envs/${button.dataset.delProjectEnv}`, renderProjects));
  });
}

function projectForm(item) {
  openForm(
    item ? "编辑项目" : "新增项目",
    [
      { name: "name", label: "项目名称", required: true },
      { name: "desc", label: "描述", type: "textarea" },
    ],
    item,
    async (data) => {
      await api(item ? `/api/projects/${item.id}` : "/api/projects", { method: item ? "PUT" : "POST", body: data });
      showToast("已保存");
      await renderProjects();
    },
  );
}

async function renderEnvs() {
  const projects = await api("/api/projects");
  const rows = await api(`/api/envs${queryString({ project_id: state.filters.projectId })}`);
  const projectName = (id) => (projects.find((item) => item.id === id) || {}).name || id;
  contentEl().innerHTML = `
    <div class="toolbar">
      <div class="filters">
        <div class="field compact"><label>项目</label><select id="envProjectFilter">${optionList(projects, "id", "name", state.filters.projectId)}</select></div>
      </div>
      ${isAdmin() ? `<button class="btn" id="newEnv">新增环境</button>` : ""}
    </div>
    ${renderTable(
      [
        { key: "id", label: "ID" },
        { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },
        { key: "env_name", label: "环境名称" },
        { key: "base_url", label: "Base URL" },
        { key: "timeout", label: "超时" },
        { key: "global_headers", label: "全局请求头", render: (row) => escapeHtml(short(row.global_headers)) },
        { key: "global_vars", label: "全局变量", render: (row) => escapeHtml(short(row.global_vars)) },
        {
          key: "actions",
          label: "操作",
          render: (row) => (isAdmin() ? `<div class="actions"><button class="btn secondary" data-edit-env="${row.id}">编辑</button><button class="btn danger" data-del-env="${row.id}">删除</button></div>` : "-"),
        },
      ],
      rows,
    )}
  `;
  document.querySelector("#envProjectFilter").addEventListener("change", async (event) => {
    state.filters.projectId = event.target.value;
    localStorage.setItem("projectId", state.filters.projectId);
    await renderEnvs();
  });
  if (!isAdmin()) return;
  const options = projects.map((item) => ({ value: item.id, label: item.name }));
  document.querySelector("#newEnv").addEventListener("click", () => envForm(null, options));
  document.querySelectorAll("[data-edit-env]").forEach((button) => {
    const item = rows.find((row) => row.id === Number(button.dataset.editEnv));
    button.addEventListener("click", () => envForm(item, options));
  });
  document.querySelectorAll("[data-del-env]").forEach((button) => {
    button.addEventListener("click", () => deleteItem(`/api/envs/${button.dataset.delEnv}`, renderEnvs));
  });
}

function envForm(item, projectOptions, afterSave = renderEnvs, defaultProjectId = "") {
  const values = item || { project_id: defaultProjectId };
  const isUpdate = item && item.id;
  openForm(
    isUpdate ? "编辑环境" : "新增环境",
    [
      { name: "project_id", label: "项目", type: "select", options: projectOptions, required: true },
      { name: "env_name", label: "环境名称", required: true },
      { name: "base_url", label: "Base URL", required: true },
      { name: "global_headers", label: "全局请求头 JSON", type: "textarea", default: "{}" },
      { name: "global_vars", label: "全局变量 JSON", type: "textarea", default: "{}" },
      { name: "timeout", label: "超时秒数", type: "number", default: 30 },
    ],
    values,
    async (data) => {
      await api(isUpdate ? `/api/envs/${item.id}` : "/api/envs", { method: isUpdate ? "PUT" : "POST", body: data });
      showToast("已保存");
      await afterSave();
    },
  );
}

async function renderApiCases() {
  const [projects, allEnvs] = await Promise.all([api("/api/projects"), api("/api/envs")]);
  const envs = state.filters.projectId ? allEnvs.filter((item) => String(item.project_id) === String(state.filters.projectId)) : allEnvs;
  if (state.filters.envId && !envs.some((item) => String(item.id) === String(state.filters.envId))) state.filters.envId = "";
  const rows = await api(`/api/api-cases${queryString({ project_id: state.filters.projectId, env_id: state.filters.envId })}`);
  const projectName = (id) => (projects.find((item) => item.id === id) || {}).name || id;
  const envName = (id) => (allEnvs.find((item) => item.id === id) || {}).env_name || id;
  const selectedCount = [...state.selectedApiIds].filter((id) => rows.some((row) => row.id === id)).length;
  contentEl().innerHTML = `
    <div class="toolbar">
      <div class="filters">
        <div class="field compact"><label>项目</label><select id="apiProjectFilter">${optionList(projects, "id", "name", state.filters.projectId)}</select></div>
        <div class="field compact"><label>环境</label><select id="apiEnvFilter">${optionList(envs, "id", "env_name", state.filters.envId)}</select></div>
      </div>
      <div class="actions">
        <button class="btn secondary" id="batchApiRun" ${selectedCount ? "" : "disabled"}>批量执行 ${selectedCount || ""}</button>
        ${isAdmin() ? `<button class="btn" id="newApiCase">新增接口用例</button>` : ""}
      </div>
    </div>
    ${renderTable(
      [
        {
          key: "select",
          label: "",
          render: (row) => `<input type="checkbox" data-api-select="${row.id}" ${state.selectedApiIds.has(row.id) ? "checked" : ""} />`,
        },
        { key: "id", label: "ID" },
        { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },
        { key: "env_id", label: "环境", render: (row) => escapeHtml(envName(row.env_id)) },
        { key: "case_name", label: "用例名称" },
        { key: "method", label: "方法", render: (row) => badge(row.method) },
        { key: "url", label: "URL" },
        { key: "status", label: "状态", render: (row) => badge(row.status) },
        {
          key: "actions",
          label: "操作",
          render: (row) => `
            <div class="actions">
              <button class="btn" data-run-api="${row.id}">执行</button>
              ${isAdmin() ? `<button class="btn secondary" data-copy-api="${row.id}">复制</button><button class="btn secondary" data-edit-api="${row.id}">编辑</button><button class="btn danger" data-del-api="${row.id}">删除</button>` : ""}
            </div>
          `,
        },
      ],
      rows,
    )}
  `;

  document.querySelector("#apiProjectFilter").addEventListener("change", async (event) => {
    state.filters.projectId = event.target.value;
    state.filters.envId = "";
    localStorage.setItem("projectId", state.filters.projectId);
    state.selectedApiIds.clear();
    await renderApiCases();
  });
  document.querySelector("#apiEnvFilter").addEventListener("change", async (event) => {
    state.filters.envId = event.target.value;
    state.selectedApiIds.clear();
    await renderApiCases();
  });
  document.querySelector("#batchApiRun").addEventListener("click", () => openBatchApiRun());
  document.querySelectorAll("[data-api-select]").forEach((checkbox) => {
    checkbox.addEventListener("change", async (event) => {
      const id = Number(event.target.dataset.apiSelect);
      if (event.target.checked) state.selectedApiIds.add(id);
      else state.selectedApiIds.delete(id);
      await renderApiCases();
    });
  });
  document.querySelectorAll("[data-run-api]").forEach((button) => {
    button.addEventListener("click", () => runApiCase(Number(button.dataset.runApi)));
  });
  if (!isAdmin()) return;
  const projectOptions = projects.map((item) => ({ value: item.id, label: item.name }));
  const envOptions = allEnvs.map((item) => ({ value: item.id, label: `${item.env_name} (${projectName(item.project_id)})` }));
  document.querySelector("#newApiCase").addEventListener("click", () => apiCaseForm(null, projectOptions, envOptions));
  document.querySelectorAll("[data-copy-api]").forEach((button) => {
    const item = rows.find((row) => row.id === Number(button.dataset.copyApi));
    button.addEventListener("click", () => apiCaseForm({ ...item, id: undefined, case_name: `${item.case_name}_copy` }, projectOptions, envOptions, true));
  });
  document.querySelectorAll("[data-edit-api]").forEach((button) => {
    const item = rows.find((row) => row.id === Number(button.dataset.editApi));
    button.addEventListener("click", () => apiCaseForm(item, projectOptions, envOptions));
  });
  document.querySelectorAll("[data-del-api]").forEach((button) => {
    button.addEventListener("click", () => deleteItem(`/api/api-cases/${button.dataset.delApi}`, renderApiCases));
  });
}

function apiCaseForm(item, projectOptions, envOptions, forceCreate = false) {
  openForm(
    item && !forceCreate ? "编辑接口用例" : "新增接口用例",
    [
      { name: "project_id", label: "项目", type: "select", options: projectOptions, required: true },
      { name: "env_id", label: "环境", type: "select", options: envOptions, required: true },
      { name: "case_name", label: "用例名称", required: true },
      { name: "method", label: "请求方法", type: "select", options: ["GET", "POST", "PUT", "PATCH", "DELETE"].map((item) => ({ value: item, label: item })), required: true },
      { name: "url", label: "URL", required: true },
      { name: "headers", label: "请求头 JSON", type: "textarea", default: "{}" },
      { name: "params", label: "参数 JSON", type: "textarea", default: "{}" },
      { name: "body", label: "请求体", type: "textarea" },
      { name: "assert_rule", label: "断言/提取 JSON", type: "textarea", default: '{"status_code":200,"extract":{"id":"json.data.id"}}' },
      {
        name: "status",
        label: "状态",
        type: "select",
        options: [
          { value: "active", label: "启用" },
          { value: "inactive", label: "停用" },
        ],
        default: "active",
      },
    ],
    item,
    async (data) => {
      const isUpdate = item && item.id && !forceCreate;
      await api(isUpdate ? `/api/api-cases/${item.id}` : "/api/api-cases", { method: isUpdate ? "PUT" : "POST", body: data });
      showToast("已保存");
      await renderApiCases();
    },
  );
}

async function runApiCase(caseId) {
  try {
    showToast("正在执行，请稍候");
    const body = {};
    if (state.filters.envId) body.env_id = Number(state.filters.envId);
    const record = await api(`/api/api-cases/${caseId}/execute`, { method: "POST", body });
    showToast(`执行完成：${record.result === "passed" ? "成功" : "失败"}`);
    state.view = "records";
    await renderShell();
  } catch (error) {
    showToast(error.message);
  }
}

function openBatchApiRun() {
  const caseIds = [...state.selectedApiIds];
  if (!caseIds.length) {
    showToast("请选择接口用例");
    return;
  }
  openForm(
    `批量执行 ${caseIds.length} 条接口用例`,
    [
      {
        name: "variables",
        label: "运行时变量 JSON",
        type: "textarea",
        rows: 8,
        default: '{\n  "username": "test_{{$random_int}}",\n  "phone": "{{$random_phone}}"\n}',
      },
    ],
    {},
    async (data) => {
      const payload = {
        case_ids: caseIds,
        variables: parseJsonText(data.variables, {}),
      };
      if (state.filters.envId) payload.env_id = Number(state.filters.envId);
      const result = await api("/api/api-cases/batch-execute", { method: "POST", body: payload });
      state.selectedApiIds.clear();
      showToast(`批量执行完成：${result.records.length} 条`);
      state.view = "records";
      await renderShell();
    },
    "执行",
  );
}

async function renderDataScripts() {
  const [projects, allEnvs, allCases, latestOrder] = await Promise.all([
    api("/api/projects"),
    api("/api/envs"),
    api("/api/api-cases"),
    api("/api/data-scripts/latest-order-sn"),
  ]);
  const storedFlows = readFlows();
  const baseFlows = storedFlows.filter((flow) => !isDeletedBuiltinFlow(flow));
  if (baseFlows.length !== storedFlows.length) {
    writeFlows(baseFlows);
  }
  let flows = ensureWarehouseDeliveryScript(
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
    if (row.scriptType === "shopping_cart") {
      return (row.caseIds || []).map(caseName).join(" -> ") || "\u767b\u5f55 -> \u641c\u7d22 -> \u8be6\u60c5 -> \u52a0\u8d2d";
    }
    if (row.scriptType === "order_quote") {
      return "\u524d\u53f0\u63d0\u5355 -> \u540e\u53f0\u767b\u5f55 -> \u8ba2\u5355\u7ffb\u8bd1 -> \u91c7\u8d2d\u8c03\u67e5 -> \u4e1a\u52a1\u62a5\u4ef7";
    }
    if (row.scriptType === "balance_payment") {
      return "\u8ba2\u5355\u5217\u8868(\u7b49\u5f85\u4ed8\u6b3e) -> \u4f59\u989d\u652f\u4ed8";
    }
    if (row.scriptType === "bank_payment") {
      return "\u8ba2\u5355\u5217\u8868(\u7b49\u5f85\u4ed8\u6b3e) -> \u94f6\u884c\u8f6c\u8d26 -> \u8d22\u52a1\u786e\u8ba4\u5165\u91d1";
    }
    if (row.scriptType === "purchase_to_shelf") {
      const variables = parseJsonText(row.variables || "{}", {});
      if (variables.link_quote_balance_before_shelf !== false && variables.auto_quote_and_pay !== false) {
        return "\u8ba2\u5355\u62a5\u4ef7 -> \u4f59\u989d\u652f\u4ed8 -> \u5f85\u62cd\u4e0b\u5546\u54c1 -> \u4ea4\u6613\u53f7\u4ed8\u6b3e -> \u5f00\u59cb\u6838\u67e5 -> \u4e0a\u67b6\u5165\u5e93";
      }
      return "\u5f85\u62cd\u4e0b\u5546\u54c1 -> \u6807\u8bb0\u5f85\u6539\u4ef7 -> \u5f85\u8d22\u52a1\u4ed8\u6b3e -> \u4ea4\u6613\u53f7\u4ed8\u6b3e -> \u5f00\u59cb\u6838\u67e5 -> \u4e0a\u67b6\u5165\u5e93";
    }
    if (row.scriptType === "warehouse_delivery") {
      return "\u4ed3\u5e93\u5546\u54c1\u5217\u8868 -> \u9009\u62e91\u756a -> \u63d0\u51fa\u914d\u9001\u5355 -> \u540e\u53f0\u914d\u8d27 -> \u88c5\u7bb1 -> \u63d0\u4ea4\u4e1a\u52a1 -> \u914d\u9001\u5355\u62a5\u4ef7";
    }
    return (row.caseIds || []).map(caseName).join(" -> ") || "-";
  };

  contentEl().innerHTML = `
    <div class="toolbar">
      <p>已保存的数据脚本可直接执行，维护时再进入编辑。</p>
      <button class="btn" id="newDataScript">新建脚本</button>
    </div>
    ${renderTable(
      [
        { key: "name", label: "脚本名称" },
        { key: "projectId", label: "项目", render: (row) => escapeHtml(projectName(row.projectId)) },
        { key: "envId", label: "环境", render: (row) => escapeHtml(envName(row.envId)) },
        {
          key: "caseIds",
          label: "步骤",
          render: (row) => escapeHtml(flowSteps(row)),
        },
        {
          key: "actions",
          label: "操作",
          render: (row) => `
            <div class="actions">
              <button class="btn" data-run-script="${row.id}">执行</button>
              <button class="btn secondary" data-edit-script="${row.id}">编辑</button>
              ${["order_quote", "balance_payment", "bank_payment", "purchase_to_shelf"].includes(row.scriptType) || row.lastOrderSn ? `<button class="btn secondary" data-copy-order-sn="${row.id}" ${row.lastOrderSn ? "" : "disabled"}>\u590d\u5236\u8ba2\u5355\u53f7</button>` : ""}
              ${row.scriptType === "purchase_to_shelf" ? `<button class="btn secondary" data-copy-purchase-no="${row.id}" ${row.lastPurchaseNo ? "" : "disabled"}>\u590d\u5236\u4ea4\u6613\u53f7</button>` : ""}
              ${row.scriptType === "warehouse_delivery" ? `<button class="btn secondary" data-copy-porder-sn="${row.id}" ${row.lastPorderSn ? "" : "disabled"}>\u590d\u5236\u914d\u9001\u5355\u53f7</button>` : ""}
              <button class="btn secondary" data-copy-script="${row.id}">复制</button>
              <button class="btn danger" data-delete-script="${row.id}">删除</button>
            </div>
          `,
        },
      ],
      flows,
    )}
  `;

  document.querySelector("#newDataScript").addEventListener("click", async () => {
    loadFlowToDraft(null);
    state.factory.editing = true;
    await renderShell();
  });
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
      await runSavedFlow(flow);
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
      const copied = {
        ...flow,
        id: newFlowId(),
        name: `${flow.name || "数据脚本"}_副本`,
        caseIds: [...(flow.caseIds || [])],
        lastOrderSn: "",
        lastPurchaseNo: "",
        lastPorderSn: "",
        lastRecordId: "",
      };
      writeFlows([...flows, copied]);
      showToast("脚本已复制");
      await renderDataScripts();
    });
  });
  document.querySelectorAll("[data-copy-order-sn]").forEach((button) => {
    button.addEventListener("click", async () => {
      const flow = readFlows().find((item) => item.id === button.dataset.copyOrderSn);
      await copyText(flow?.lastOrderSn, "\u8ba2\u5355\u53f7");
    });
  });
  document.querySelectorAll("[data-copy-purchase-no]").forEach((button) => {
    button.addEventListener("click", async () => {
      const flow = readFlows().find((item) => item.id === button.dataset.copyPurchaseNo);
      await copyText(flow?.lastPurchaseNo, "\u4ea4\u6613\u53f7");
    });
  });
  document.querySelectorAll("[data-copy-porder-sn]").forEach((button) => {
    button.addEventListener("click", async () => {
      const flow = readFlows().find((item) => item.id === button.dataset.copyPorderSn);
      await copyText(flow?.lastPorderSn, "\u914d\u9001\u5355\u53f7");
    });
  });
  document.querySelectorAll("[data-delete-script]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("确认删除这个数据脚本？")) return;
      const deleteId = button.dataset.deleteScript;
      const flows = readFlows();
      const targetFlow = flows.find((flow) => flow.id === deleteId);
      const builtinDefinition = builtinDefinitionForFlow(targetFlow);
      if (builtinDefinition) {
        markBuiltinDeleted(builtinDefinition.id);
      }
      writeFlows(
        flows.filter((flow) => {
          if (flow.id === deleteId) return false;
          if (!builtinDefinition) return true;
          return flow.id !== builtinDefinition.id && flow.name !== builtinDefinition.name;
        }),
      );
      showToast("已删除");
      await renderDataScripts();
    });
  });
}

async function renderDataScriptEditor() {
  const [projects, allEnvs, allCases] = await Promise.all([api("/api/projects"), api("/api/envs"), api("/api/api-cases")]);
  const flows = readFlows();
  const selectedProjectId = state.factory.projectId;
  const envs = selectedProjectId ? allEnvs.filter((item) => String(item.project_id) === String(selectedProjectId)) : allEnvs;
  if (state.factory.envId && !envs.some((item) => String(item.id) === String(state.factory.envId))) {
    state.factory.envId = "";
    persistFactoryDraft();
  }
  const availableCases = allCases.filter((item) => {
    const projectOk = !state.factory.projectId || String(item.project_id) === String(state.factory.projectId);
    const envOk = !state.factory.envId || String(item.env_id) === String(state.factory.envId);
    return projectOk && envOk;
  });
  const projectName = (id) => (projects.find((item) => item.id === id) || {}).name || id;
  const envName = (id) => (allEnvs.find((item) => item.id === id) || {}).env_name || id;
  const selectedCases = state.factory.caseIds
    .map((id) => allCases.find((item) => item.id === id))
    .filter(Boolean);
  const selectedFlow = flows.find((flow) => flow.id === state.factory.flowId);

  contentEl().innerHTML = `
    <div class="toolbar">
      <div class="filters">
        <div class="field compact"><label>项目</label><select id="factoryProject">${optionList(projects, "id", "name", state.factory.projectId)}</select></div>
        <div class="field compact"><label>环境</label><select id="factoryEnv">${optionList(envs, "id", "env_name", state.factory.envId)}</select></div>
      </div>
      <div class="actions">
        <button class="btn secondary" id="backScripts">返回列表</button>
        <button class="btn" id="saveFlow">保存脚本</button>
      </div>
    </div>
    <div class="factory-grid">
      <section class="panel">
        <div class="panel-title"><h3>接口用例</h3></div>
        ${renderTable(
          [
            { key: "id", label: "ID" },
            { key: "case_name", label: "用例名称" },
            { key: "method", label: "方法", render: (row) => badge(row.method) },
            { key: "env_id", label: "环境", render: (row) => escapeHtml(envName(row.env_id)) },
            { key: "actions", label: "操作", render: (row) => `<button class="btn secondary" data-add-flow-case="${row.id}">加入</button>` },
          ],
          availableCases,
          false,
        )}
      </section>
      <section class="panel">
        <div class="panel-title"><h3>脚本步骤</h3></div>
        ${renderTable(
          [
            { key: "index", label: "顺序", render: (row) => row.index + 1 },
            { key: "case_name", label: "用例名称" },
            { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },
            { key: "env_id", label: "环境", render: (row) => escapeHtml(state.factory.envId ? envName(Number(state.factory.envId)) : envName(row.env_id)) },
            {
              key: "actions",
              label: "操作",
              render: (row) => `
                <div class="actions">
                  <button class="btn secondary" data-move-flow-case="${row.index}:up">上移</button>
                  <button class="btn secondary" data-move-flow-case="${row.index}:down">下移</button>
                  <button class="btn danger" data-remove-flow-case="${row.index}">移除</button>
                </div>
              `,
            },
          ],
          selectedCases.map((item, index) => ({ ...item, index })),
          false,
        )}
      </section>
    </div>
    <section class="panel factory-vars">
      <div class="panel-title"><h3>运行时变量</h3></div>
      <div class="panel-body">
        <textarea id="factoryVariables" spellcheck="false">${escapeHtml(state.factory.variables)}</textarea>
      </div>
    </section>
  `;

  document.querySelector("#backScripts").addEventListener("click", async () => {
    state.factory.editing = false;
    await renderShell();
  });
  document.querySelector("#factoryProject").addEventListener("change", async (event) => {
    state.factory.projectId = event.target.value;
    state.factory.envId = "";
    persistFactoryDraft();
    await renderDataScriptEditor();
  });
  document.querySelector("#factoryEnv").addEventListener("change", async (event) => {
    state.factory.envId = event.target.value;
    persistFactoryDraft();
    await renderDataScriptEditor();
  });
  document.querySelector("#factoryVariables").addEventListener("input", (event) => {
    state.factory.variables = event.target.value;
    persistFactoryDraft();
  });
  document.querySelector("#saveFlow").addEventListener("click", () => openSaveFlowForm());
  document.querySelectorAll("[data-add-flow-case]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.factory.caseIds.push(Number(button.dataset.addFlowCase));
      persistFactoryDraft();
      await renderDataScriptEditor();
    });
  });
  document.querySelectorAll("[data-remove-flow-case]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.factory.caseIds.splice(Number(button.dataset.removeFlowCase), 1);
      persistFactoryDraft();
      await renderDataScriptEditor();
    });
  });
  document.querySelectorAll("[data-move-flow-case]").forEach((button) => {
    button.addEventListener("click", async () => {
      const [rawIndex, direction] = button.dataset.moveFlowCase.split(":");
      const index = Number(rawIndex);
      const next = direction === "up" ? index - 1 : index + 1;
      if (next < 0 || next >= state.factory.caseIds.length) return;
      const ids = state.factory.caseIds;
      [ids[index], ids[next]] = [ids[next], ids[index]];
      persistFactoryDraft();
      await renderDataScriptEditor();
    });
  });
}

function openSaveFlowForm() {
  const flow = readFlows().find((item) => item.id === state.factory.flowId);
  openForm(
    "保存脚本",
    [{ name: "name", label: "脚本名称", required: true, default: flow?.name || "购物车造数脚本" }],
    flow || {},
    async (data) => {
      const flows = readFlows();
      const isEditing = Boolean(state.factory.flowId);
      const id = isEditing ? state.factory.flowId : newFlowId();
      const index = flows.findIndex((item) => item.id === id);
      if (isEditing && index < 0) {
        throw new Error("当前脚本不存在，无法保存为新增脚本，请返回列表后重新编辑");
      }
      const nextFlow = {
        id,
        name: data.name,
        scriptType: (index >= 0 ? flows[index]?.scriptType : flow?.scriptType) || "",
        projectId: state.factory.projectId,
        envId: state.factory.envId,
        caseIds: [...state.factory.caseIds],
        variables: state.factory.variables,
        lastOrderSn: (index >= 0 ? flows[index]?.lastOrderSn : flow?.lastOrderSn) || "",
        lastPurchaseNo: (index >= 0 ? flows[index]?.lastPurchaseNo : flow?.lastPurchaseNo) || "",
        lastPorderSn: (index >= 0 ? flows[index]?.lastPorderSn : flow?.lastPorderSn) || "",
        lastRecordId: (index >= 0 ? flows[index]?.lastRecordId : flow?.lastRecordId) || "",
      };
      if (index >= 0) flows[index] = nextFlow;
      else flows.push(nextFlow);
      writeFlows(flows);
      state.factory.flowId = id;
      persistFactoryDraft();
      state.factory.editing = false;
      showToast("脚本已保存");
      await renderShell();
    },
  );
}

async function runFactoryFlow() {
  if (!state.factory.caseIds.length) {
    showToast("请先加入接口用例");
    return;
  }
  let variables = {};
  try {
    variables = parseJsonText(state.factory.variables, {});
  } catch {
    showToast("运行时变量不是合法 JSON");
    return;
  }
  try {
    showToast("脚本执行中，请稍候");
    const payload = {
      case_ids: state.factory.caseIds,
      variables,
    };
    if (state.factory.envId) payload.env_id = Number(state.factory.envId);
    const result = await api("/api/api-cases/batch-execute", { method: "POST", body: payload });
    showFactoryResult(result);
  } catch (error) {
    showToast(error.message);
  }
}

function scriptStepEstimate(flow, variables) {
  if (!flow) return 1;
  if (flow.scriptType === "order_quote") return variables?.run_backend_flow === false ? 5 : 9;
  if (flow.scriptType === "balance_payment") return 3;
  if (flow.scriptType === "bank_payment") return variables?.finance_confirm === false ? 3 : 5;
  if (flow.scriptType === "purchase_to_shelf") {
    return variables?.link_quote_balance_before_shelf === false || variables?.auto_quote_and_pay === false ? 9 : 21;
  }
  if (flow.scriptType === "purchase_to_shelf_chain") return 21;
  if (flow.scriptType === "warehouse_delivery") return variables?.run_backend_delivery_flow === false ? 3 : 11;
  if (flow.scriptType !== "shopping_cart") return Math.max((flow.caseIds || []).length, 1);
  const perShopRaw = Number(variables?.per_shop);
  const perShop = Number.isFinite(perShopRaw) && perShopRaw > 0 ? Math.floor(perShopRaw) : 5;
  const rawShopTypes = variables?.shop_types;
  const shopTypes = Array.isArray(rawShopTypes)
    ? rawShopTypes
    : String(rawShopTypes || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
  const shopCount = Math.max(shopTypes.length || 4, 1);
  return 1 + shopCount * perShop;
}

function openScriptProgress(title, initialMessage) {
  modalEl.innerHTML = `
    <div class="modal-head">
      <h3>${escapeHtml(title || "\u811a\u672c\u6267\u884c\u8fdb\u5ea6")}</h3>
      <button class="btn secondary" type="button" id="closeProgress">\u5173\u95ed</button>
    </div>
    <div class="modal-body">
      <div class="progress-meta">
        <strong id="progressMessage">${escapeHtml(initialMessage || "\u6b63\u5728\u51c6\u5907\u811a\u672c...")}</strong>
        <span id="progressPercent">8%</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill" id="progressFill" style="width:8%"></div>
      </div>
      <p class="progress-note">\u811a\u672c\u8fd0\u884c\u4e2d\uff0c\u7ed3\u675f\u540e\u4f1a\u81ea\u52a8\u5c55\u793a\u7ed3\u679c\u3002</p>
    </div>
  `;
  if (!modalEl.open) modalEl.showModal();

  const fillEl = document.querySelector("#progressFill");
  const percentEl = document.querySelector("#progressPercent");
  const messageEl = document.querySelector("#progressMessage");
  const closeBtn = document.querySelector("#closeProgress");

  let percent = 8;
  let failed = false;
  let closed = false;
  const tick = () => {
    if (percent >= 92) return;
    const delta = percent < 40 ? 6 : percent < 70 ? 3 : 1;
    percent = Math.min(92, percent + delta);
    render();
  };
  const timer = window.setInterval(tick, 700);
  closeBtn.addEventListener("click", () => {
    closed = true;
    window.clearInterval(timer);
    if (modalEl.open) modalEl.close();
  });

  function render() {
    fillEl.style.width = `${percent}%`;
    fillEl.classList.toggle("failed", failed);
    percentEl.textContent = `${Math.round(percent)}%`;
  }

  render();

  function done(message, isFailed) {
    window.clearInterval(timer);
    failed = Boolean(isFailed);
    if (!failed) percent = 100;
    if (message) messageEl.textContent = message;
    if (!closed) render();
  }

  return {
    update(nextPercent, message) {
      if (typeof nextPercent === "number" && Number.isFinite(nextPercent)) {
        percent = Math.max(percent, Math.min(95, Math.round(nextPercent)));
      }
      if (message) messageEl.textContent = message;
      render();
    },
    success(message) {
      done(message || "\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u8f93\u51fa\u7ed3\u679c...", false);
    },
    fail(message) {
      done(message || "\u811a\u672c\u6267\u884c\u5931\u8d25", true);
    },
  };
}

async function runSavedFlow(flow) {
  const builtInTypes = ["shopping_cart", "order_quote", "balance_payment", "bank_payment", "purchase_to_shelf", "purchase_to_shelf_chain", "warehouse_delivery"];
  if (!flow || (!builtInTypes.includes(flow.scriptType) && !(flow.caseIds || []).length)) {
    showToast("脚本没有配置步骤");
    return;
  }
  let variables = {};
  try {
    variables = parseJsonText(flow.variables, {});
  } catch {
    showToast("脚本变量不是合法 JSON");
    return;
  }
  const progress = openScriptProgress("\u6570\u636e\u811a\u672c\u6267\u884c\u8fdb\u5ea6", `\u9884\u8ba1\u6267\u884c ${scriptStepEstimate(flow, variables)} \u4e2a\u6b65\u9aa4`);
  try {
    showToast("脚本执行中，请稍候");
    if (flow.scriptType === "shopping_cart") {
      progress.update(24, "\u6b63\u5728\u6267\u884c\u767b\u5f55\u3001\u641c\u7d22\u3001\u52a0\u8d2d\u6b65\u9aa4...");
      const result = await api("/api/data-scripts/shopping-cart", {
        method: "POST",
        body: {
          env_id: flow.envId ? Number(flow.envId) : null,
          variables,
        },
      });
      progress.success("\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");
      await new Promise((resolve) => window.setTimeout(resolve, 180));
      showFactoryResult({
        records: [{ id: result.id, case_name: flow.name, result: result.result }],
        variables: result.summary || {},
      });
      return;
    }
    if (flow.scriptType === "order_quote") {
      progress.update(24, "\u6b63\u5728\u6267\u884c\u524d\u53f0\u63d0\u5355\u4e0e\u540e\u53f0\u7ffb\u8bd1\u3001\u91c7\u8d2d\u8c03\u67e5\u3001\u4e1a\u52a1\u62a5\u4ef7...");
      const result = await api("/api/data-scripts/order-quote", {
        method: "POST",
        body: {
          env_id: flow.envId ? Number(flow.envId) : null,
          variables,
        },
      });
      const orderSn = result.summary?.order_sn || "";
      if (orderSn) {
        const flows = readFlows().map((item) =>
          item.id === flow.id ? { ...item, lastOrderSn: orderSn, lastRecordId: result.id } : item,
        );
        writeFlows(flows);
        flow.lastOrderSn = orderSn;
        flow.lastRecordId = result.id;
      }
      progress.success("\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");
      await new Promise((resolve) => window.setTimeout(resolve, 180));
      showFactoryResult({
        records: [{ id: result.id, case_name: flow.name, result: result.result }],
        variables: result.summary || {},
      });
      return;
    }
    if (flow.scriptType === "balance_payment" || flow.scriptType === "bank_payment") {
      const isBank = flow.scriptType === "bank_payment";
      progress.update(
        24,
        isBank
          ? "\u6b63\u5728\u67e5\u627e\u7b49\u5f85\u4ed8\u6b3e\u8ba2\u5355\uff0c\u6267\u884c\u94f6\u884c\u8f6c\u8d26\u4e0e\u8d22\u52a1\u786e\u8ba4..."
          : "\u6b63\u5728\u67e5\u627e\u7b49\u5f85\u4ed8\u6b3e\u8ba2\u5355\uff0c\u6267\u884c\u4f59\u989d\u652f\u4ed8...",
      );
      const result = await api(isBank ? "/api/data-scripts/bank-payment" : "/api/data-scripts/balance-payment", {
        method: "POST",
        body: {
          env_id: flow.envId ? Number(flow.envId) : null,
          variables,
        },
      });
      const orderSn = result.summary?.order_sn || "";
      if (orderSn) {
        const flows = readFlows().map((item) =>
          item.id === flow.id ? { ...item, lastOrderSn: orderSn, lastRecordId: result.id } : item,
        );
        writeFlows(flows);
        flow.lastOrderSn = orderSn;
        flow.lastRecordId = result.id;
      }
      progress.success("\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");
      await new Promise((resolve) => window.setTimeout(resolve, 180));
      showFactoryResult({
        records: [{ id: result.id, case_name: flow.name, result: result.result }],
        variables: result.summary || {},
      });
      return;
    }
    if (flow.scriptType === "purchase_to_shelf") {
      const requestVariables = { ...variables };
      const linkBeforeShelf = requestVariables.link_quote_balance_before_shelf !== false && requestVariables.auto_quote_and_pay !== false;
      if (linkBeforeShelf) {
        delete requestVariables.order_sn;
        delete requestVariables.last_order_sn;
        progress.update(8, "\u6b63\u5728\u8054\u52a8\u6267\u884c\uff1a\u8ba2\u5355\u62a5\u4ef7\u2192\u4f59\u989d\u652f\u4ed8\u2192\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6...");
        const result = await api("/api/data-scripts/purchase-to-shelf-chain", {
          method: "POST",
          body: {
            env_id: flow.envId ? Number(flow.envId) : null,
            variables: requestVariables,
          },
        });
        const orderSn = result.summary?.order_sn || "";
        const purchaseNo = result.summary?.purchase_no || "";
        const flows = readFlows().map((item) =>
          item.id === flow.id
            ? { ...item, lastOrderSn: orderSn, lastPurchaseNo: purchaseNo, lastRecordId: result.id }
            : item,
        );
        writeFlows(flows);
        flow.lastOrderSn = orderSn;
        flow.lastPurchaseNo = purchaseNo;
        flow.lastRecordId = result.id;
        progress.success("\u8054\u52a8\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");
        await new Promise((resolve) => window.setTimeout(resolve, 180));
        showFactoryResult({
          records: [{ id: result.id, case_name: flow.name, result: result.result }],
          variables: result.summary || {},
        });
        return;
      }
      progress.update(24, "\u6b63\u5728\u63a8\u8fdb\u5f85\u62cd\u4e0b\u5546\u54c1\uff1a\u4ea4\u6613\u53f7\u3001\u5f85\u6539\u4ef7\u3001\u4ed8\u6b3e\u3001\u6838\u67e5\u3001\u4e0a\u67b6\u5165\u5e93...");
      if (!requestVariables.order_sn && flow.lastOrderSn) requestVariables.order_sn = flow.lastOrderSn;
      const result = await api("/api/data-scripts/purchase-to-shelf", {
        method: "POST",
        body: {
          env_id: flow.envId ? Number(flow.envId) : null,
          variables: requestVariables,
        },
      });
      const orderSn = result.summary?.order_sn || requestVariables.order_sn || "";
      const purchaseNo = result.summary?.purchase_no || requestVariables.purchase_no || "";
      const flows = readFlows().map((item) =>
        item.id === flow.id
          ? { ...item, lastOrderSn: orderSn, lastPurchaseNo: purchaseNo, lastRecordId: result.id }
          : item,
      );
      writeFlows(flows);
      flow.lastOrderSn = orderSn;
      flow.lastPurchaseNo = purchaseNo;
      flow.lastRecordId = result.id;
      progress.success("\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");
      await new Promise((resolve) => window.setTimeout(resolve, 180));
      showFactoryResult({
        records: [{ id: result.id, case_name: flow.name, result: result.result }],
        variables: result.summary || {},
      });
      return;
    }
    if (flow.scriptType === "purchase_to_shelf_chain") {
      progress.update(8, "\u6b63\u5728\u6267\u884c\u7ec4\u5408\u811a\u672c\uff1a\u8ba2\u5355\u62a5\u4ef7\u2192\u4f59\u989d\u652f\u4ed8\u2192\u5f85\u62cd\u4e0b\u5230\u5546\u54c1\u4e0a\u67b6...");
      const result = await api("/api/data-scripts/purchase-to-shelf-chain", {
        method: "POST",
        body: {
          env_id: flow.envId ? Number(flow.envId) : null,
          variables,
        },
      });
      const orderSn = result.summary?.order_sn || "";
      const purchaseNo = result.summary?.purchase_no || "";
      const flows = readFlows().map((item) =>
        item.id === flow.id
          ? { ...item, lastOrderSn: orderSn, lastPurchaseNo: purchaseNo, lastRecordId: result.id }
          : item,
      );
      writeFlows(flows);
      flow.lastOrderSn = orderSn;
      flow.lastPurchaseNo = purchaseNo;
      flow.lastRecordId = result.id;
      progress.success("\u7ec4\u5408\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");
      await new Promise((resolve) => window.setTimeout(resolve, 180));
      showFactoryResult({
        records: [{ id: result.id, case_name: flow.name, result: result.result }],
        variables: result.summary || {},
      });
      return;
    }
    if (flow.scriptType === "warehouse_delivery") {
      progress.update(12, "\u6b63\u5728\u6267\u884c\uff1a\u4ed3\u5e93\u9009\u62e91\u756a -> \u63d0\u51fa\u914d\u9001\u5355 -> \u540e\u53f0\u914d\u8d27\u88c5\u7bb1 -> \u63d0\u4ea4\u4e1a\u52a1\u62a5\u4ef7...");
      const result = await api("/api/data-scripts/warehouse-delivery", {
        method: "POST",
        body: {
          env_id: flow.envId ? Number(flow.envId) : null,
          variables,
        },
      });
      const porderSn = result.summary?.porder_sn || "";
      const flows = readFlows().map((item) =>
        item.id === flow.id
          ? { ...item, lastPorderSn: porderSn, lastRecordId: result.id }
          : item,
      );
      writeFlows(flows);
      flow.lastPorderSn = porderSn;
      flow.lastRecordId = result.id;
      progress.success("\u914d\u9001\u5355\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");
      await new Promise((resolve) => window.setTimeout(resolve, 180));
      showFactoryResult({
        records: [{ id: result.id, case_name: flow.name, result: result.result }],
        variables: result.summary || {},
      });
      return;
    }
    progress.update(24, `\u6b63\u5728\u987a\u5e8f\u6267\u884c ${Math.max((flow.caseIds || []).length, 1)} \u4e2a\u63a5\u53e3\u7528\u4f8b...`);
    const payload = {
      case_ids: flow.caseIds,
      variables,
    };
    if (flow.envId) payload.env_id = Number(flow.envId);
    const result = await api("/api/api-cases/batch-execute", { method: "POST", body: payload });
    progress.success("\u811a\u672c\u6267\u884c\u5b8c\u6210\uff0c\u6b63\u5728\u5c55\u793a\u7ed3\u679c...");
    await new Promise((resolve) => window.setTimeout(resolve, 180));
    showFactoryResult(result);
  } catch (error) {
    progress.fail(`\u6267\u884c\u5931\u8d25\uff1a${error.message}`);
    showToast(error.message);
  }
}

function showFactoryResult(result) {
  const rows = result.records || [];
  modalEl.innerHTML = `
    <div class="modal-head">
      <h3>脚本执行结果</h3>
      <button class="btn secondary" type="button" id="closeModal">关闭</button>
    </div>
    <div class="modal-body">
      ${renderTable(
        [
          { key: "case_name", label: "用例" },
          { key: "result", label: "结果", render: (row) => badge(row.result) },
          { key: "id", label: "记录ID" },
        ],
        rows,
        false,
      )}
      <pre class="log-view">${escapeHtml(JSON.stringify(result.variables || {}, null, 2))}</pre>
    </div>
    <div class="modal-foot">
      <span></span>
      <button class="btn" type="button" id="goRecords">查看记录</button>
    </div>
  `;
  if (!modalEl.open) modalEl.showModal();
  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
  document.querySelector("#goRecords").addEventListener("click", async () => {
    modalEl.close();
    state.view = "records";
    await renderShell();
  });
}

async function renderUiCases() {
  const projects = await api("/api/projects");
  const rows = await api(`/api/ui-cases${queryString({ project_id: state.filters.projectId })}`);
  const projectName = (id) => (projects.find((item) => item.id === id) || {}).name || id;
  contentEl().innerHTML = `
    <div class="toolbar">
      <div class="filters">
        <div class="field compact"><label>项目</label><select id="uiProjectFilter">${optionList(projects, "id", "name", state.filters.projectId)}</select></div>
      </div>
      ${isAdmin() ? `<button class="btn" id="newUiCase">新增UI用例</button>` : ""}
    </div>
    ${renderTable(
      [
        { key: "id", label: "ID" },
        { key: "project_id", label: "项目", render: (row) => escapeHtml(projectName(row.project_id)) },
        { key: "case_name", label: "用例名称" },
        { key: "page_url", label: "页面地址" },
        { key: "timeout", label: "超时" },
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
  document.querySelectorAll("[data-run-ui]").forEach((button) => button.addEventListener("click", () => runCase(`/api/ui-cases/${button.dataset.runUi}/execute`)));
  if (!isAdmin()) return;
  const projectOptions = projects.map((item) => ({ value: item.id, label: item.name }));
  document.querySelector("#newUiCase").addEventListener("click", () => uiCaseForm(null, projectOptions));
  document.querySelectorAll("[data-edit-ui]").forEach((button) => {
    const item = rows.find((row) => row.id === Number(button.dataset.editUi));
    button.addEventListener("click", () => uiCaseForm(item, projectOptions));
  });
  document.querySelectorAll("[data-del-ui]").forEach((button) => {
    button.addEventListener("click", () => deleteItem(`/api/ui-cases/${button.dataset.delUi}`, renderUiCases));
  });
}

function uiCaseForm(item, projectOptions) {
  openForm(
    item ? "编辑UI用例" : "新增UI用例",
    [
      { name: "project_id", label: "项目", type: "select", options: projectOptions, required: true },
      { name: "case_name", label: "用例名称", required: true },
      { name: "page_url", label: "页面地址", required: true },
      { name: "steps", label: "步骤 JSON", type: "textarea", rows: 8, default: '[{"action":"goto","value":"https://example.com"},{"action":"text_assert","locator":"body","value":"Example"}]' },
      { name: "timeout", label: "超时秒数", type: "number", default: 30 },
      {
        name: "status",
        label: "状态",
        type: "select",
        options: [
          { value: "active", label: "启用" },
          { value: "inactive", label: "停用" },
        ],
        default: "active",
      },
    ],
    item,
    async (data) => {
      await api(item ? `/api/ui-cases/${item.id}` : "/api/ui-cases", { method: item ? "PUT" : "POST", body: data });
      showToast("已保存");
      await renderUiCases();
    },
  );
}

async function runCase(path) {
  try {
    showToast("正在执行，请稍候");
    const record = await api(path, { method: "POST" });
    showToast(`执行完成：${record.result === "passed" ? "成功" : "失败"}`);
    state.view = "records";
    await renderShell();
  } catch (error) {
    showToast(error.message);
  }
}

function recordColumns() {
  return [
    { key: "id", label: "ID" },
    { key: "case_type", label: "类型", render: (row) => badge(row.case_type) },
    { key: "case_id", label: "用例ID" },
    { key: "result", label: "结果", render: (row) => badge(row.result) },
    { key: "execute_time", label: "执行时间" },
    {
      key: "actions",
      label: "操作",
      render: (row) => `
        <div class="actions">
          <button class="btn secondary" data-log="${row.id}">日志</button>
          ${row.report_path ? `<button class="btn secondary" data-report="${row.id}">报告</button>` : ""}
          ${row.screenshot ? `<button class="btn secondary" data-shot="${row.id}">截图</button>` : ""}
        </div>
      `,
    },
  ];
}

async function renderRecords() {
  const projects = await api("/api/projects");
  const rows = await api(`/api/test-records${queryString({ project_id: state.filters.projectId, case_type: state.filters.recordType })}`);
  contentEl().innerHTML = `
    <div class="toolbar">
      <div class="filters">
        <div class="field compact"><label>项目</label><select id="recordProjectFilter">${optionList(projects, "id", "name", state.filters.projectId)}</select></div>
        <div class="field compact"><label>类型</label><select id="recordTypeFilter">
          <option value="">全部</option>
          <option value="api" ${state.filters.recordType === "api" ? "selected" : ""}>api</option>
          <option value="ui" ${state.filters.recordType === "ui" ? "selected" : ""}>ui</option>
        </select></div>
      </div>
    </div>
    ${renderTable(recordColumns(), rows)}
  `;
  bindRecordActions(rows);
  document.querySelector("#recordProjectFilter").addEventListener("change", async (event) => {
    state.filters.projectId = event.target.value;
    localStorage.setItem("projectId", state.filters.projectId);
    await renderRecords();
  });
  document.querySelector("#recordTypeFilter").addEventListener("change", async (event) => {
    state.filters.recordType = event.target.value;
    await renderRecords();
  });
}

function bindRecordActions(rows) {
  document.querySelectorAll("[data-log]").forEach((button) => {
    const item = rows.find((row) => row.id === Number(button.dataset.log));
    button.addEventListener("click", () => showLog(item));
  });
  document.querySelectorAll("[data-report]").forEach((button) => {
    button.addEventListener("click", () => openProtectedFile(`/api/test-records/${button.dataset.report}/report`));
  });
  document.querySelectorAll("[data-shot]").forEach((button) => {
    button.addEventListener("click", () => openProtectedFile(`/api/test-records/${button.dataset.shot}/screenshot`));
  });
}

function showLog(item) {
  modalEl.innerHTML = `
    <div class="modal-head">
      <h3>执行日志 #${item.id}</h3>
      <button class="btn secondary" type="button" id="closeModal">关闭</button>
    </div>
    <div class="modal-body"><pre class="log-view">${escapeHtml(item.log || "")}</pre></div>
  `;
  modalEl.showModal();
  document.querySelector("#closeModal").addEventListener("click", () => modalEl.close());
}

async function renderUsers() {
  if (!isAdmin()) {
    state.view = "dashboard";
    return renderShell();
  }
  const rows = await api("/api/users");
  contentEl().innerHTML = `
    <div class="toolbar"><p>仅 admin 可管理账号</p><button class="btn" id="newUser">新增用户</button></div>
    ${renderTable(
      [
        { key: "id", label: "ID" },
        { key: "username", label: "账号" },
        { key: "role", label: "角色", render: (row) => badge(row.role) },
        { key: "create_time", label: "创建时间" },
        {
          key: "actions",
          label: "操作",
          render: (row) => `<div class="actions"><button class="btn secondary" data-edit-user="${row.id}">编辑</button><button class="btn danger" data-del-user="${row.id}">删除</button></div>`,
        },
      ],
      rows,
    )}
  `;
  document.querySelector("#newUser").addEventListener("click", () => userForm());
  document.querySelectorAll("[data-edit-user]").forEach((button) => {
    const item = rows.find((row) => row.id === Number(button.dataset.editUser));
    button.addEventListener("click", () => userForm(item));
  });
  document.querySelectorAll("[data-del-user]").forEach((button) => {
    button.addEventListener("click", () => deleteItem(`/api/users/${button.dataset.delUser}`, renderUsers));
  });
}

function userForm(item) {
  openForm(
    item ? "编辑用户" : "新增用户",
    [
      { name: "username", label: "账号", required: true },
      { name: "password", label: item ? "新密码（可留空）" : "密码", type: "password", required: !item },
      {
        name: "role",
        label: "角色",
        type: "select",
        options: [
          { value: "admin", label: "admin" },
          { value: "normal", label: "normal" },
        ],
        default: "normal",
        required: true,
      },
    ],
    item,
    async (data) => {
      if (item && !data.password) delete data.password;
      await api(item ? `/api/users/${item.id}` : "/api/users", { method: item ? "PUT" : "POST", body: data });
      showToast("已保存");
      await renderUsers();
    },
  );
}

async function bootstrap() {
  if (!state.token) {
    renderLogin();
    return;
  }
  try {
    await renderShell();
  } catch {
    renderLogin();
  }
}

bootstrap();
