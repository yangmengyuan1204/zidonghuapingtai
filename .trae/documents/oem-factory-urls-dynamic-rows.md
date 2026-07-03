# OEM 询价单全流程 - 工厂链接动态行 + factory_type 文字化

## 背景

当前 OEM 询价单全流程执行弹窗存在三个问题：

1. **工厂链接联动体验差**：`factory_urls` 是单个 textarea（4 行），用户填几行链接就展开几组报价。但 textarea 体验不好，用户希望改成「+/- 按钮」的动态行输入。
2. **删除不按索引联动**：当前 `refreshQuoteGroups` 按 textarea 行数重渲染，删除某行时是"截断"（保留前 N 个），不是按索引删除。用户期望：删除第 2 条链接时，下方「工厂2报价」组也对应删除，工厂3变成工厂2。
3. **factory_type 是数字看不懂**：schema 里 `factory_type` 是 `type: "number", default: 3`，用户不知道 1/2/3 代表什么工厂类型。

## 用户确认的方案

1. **factory_type 选项来源**：用 Playwright 登录 OEM 后台，打开创建询价单页面，抓取 factory_type 下拉框的所有选项文字，再把 schema 字段改成 select。抓不到则保留 number。
2. **factory_urls 存储格式**：保持字符串（`url1\nurl2\nurl3`），前端把多个 input 的 value 用 `\n` 拼接。后端 `_oem_parse_factory_urls` 不改。

## 当前实现分析

### `static/app.js` schema（第 22-24 行）

```js
{ name: "goods_type", label: "商品类型", type: "number", default: 1 },
{ name: "factory_type", label: "工厂类型", type: "number", default: 3 },
{ name: "factory_urls", label: "工厂链接（每行一个）", type: "textarea", rows: 4 },
```

### `openOemFullInquiryFlowRunForm`（第 1230-1383 行）

- 第 1290 行：`factory_urls` 走 `renderFormField` 的 textarea 分支，渲染成单个 `<textarea name="factory_urls" rows="4">`
- 第 1311-1337 行 `refreshQuoteGroups`：读 `factory_urls.value` → `splitParamList` 切分行数 → 重渲染报价分组。删除时是"截断"（`fqCache` 的 key 超过 factoryCount 就 delete），不是按索引删除。
- 第 1342-1345 行：监听 textarea 的 `input` 事件触发 `refreshQuoteGroups`

### `renderFormField`（第 101 行单行函数）

支持的类型：select / textarea / checkbox / upload / 默认 text/number。**不支持动态重复行组**。

### factory_type 数字含义（无任何代码注释）

- 创建询价单 `/api/newInquiry`：`factory_type = 3`（默认）
- 工厂报价 `/admin/factoryQuote`：`factory_type = 1`（从 d_item 取或 fallback 1）
- HAR 文件未捕获相关接口，无法从抓包反推

## 提议改动

### 步骤0：Playwright 抓取 factory_type 选项（执行阶段第一步）

**目的**：获取 factory_type 下拉框的选项文字（1/2/3 对应什么工厂类型）

**方法**：
- 用 Playwright 登录 OEM 后台 `https://oemadmin.rakumart.cn`
- 找到创建询价单的页面（可能在前台 `https://oem.rakumart.cn` 用户端提交询价单，或后台某入口）
- 定位 `factory_type` 相关的 select / radio / 下拉组件
- dump 所有选项的 value 和 label
- 把抓取结果写入本计划文件的「抓取结果」小节

**备用方案**：如果抓取失败（登录受阻/页面结构变化/字段不暴露），fallback 到「保留 number + label 加括号说明」方案，并在计划里记录失败原因。

**抓取结果**：（执行后填充）
```
factory_type 选项：
- value=1 label=___
- value=2 label=___
- value=3 label=___
```

### 改动1：前端 schema `factory_type` 改 select（第 23 行）

**位置**：`static/app.js` `SCRIPT_PARAM_SCHEMAS.oem_full_inquiry_flow` 第 23 行

**改动**：根据步骤0抓取结果，把 `factory_type` 从 number 改成 select：

```js
// 改前
{ name: "factory_type", label: "工厂类型", type: "number", default: 3 },
// 改后（选项根据抓取结果填充）
{ name: "factory_type", label: "工厂类型", type: "select", default: "3",
  options: [
    { value: "1", label: "工厂类型A（抓取后填实际文字）" },
    { value: "2", label: "工厂类型B（抓取后填实际文字）" },
    { value: "3", label: "工厂类型C（抓取后填实际文字）" },
  ] },
```

**注意**：default 改成字符串 `"3"`（select 的 value 都是字符串），保持与后端 `int(variables.get("factory_type") or 3)` 兼容。

### 改动2：前端 `factory_urls` 改成动态行输入（+/- 按钮）

**位置**：`static/app.js` `openOemFullInquiryFlowRunForm`（第 1230-1383 行）

**改动**：

1. **schema 调整**（第 24 行）：把 `factory_urls` 从 textarea 改成一个标记字段 `type: "factory-urls-dynamic"`（仅用于 `openOemFullInquiryFlowRunForm` 识别，`renderFormField` 不识别此类型时返回空字符串，避免在普通流程被渲染）：

```js
// 改前
{ name: "factory_urls", label: "工厂链接（每行一个）", type: "textarea", rows: 4 },
// 改后
{ name: "factory_urls", label: "工厂链接", type: "factory-urls-dynamic" },
```

2. **新增 `renderFactoryUrlsDynamic` 函数**：渲染工厂链接动态行容器

```js
function renderFactoryUrlsDynamic(values) {
  // values.factory_urls 是字符串 "url1\nurl2\nurl3"
  const urls = splitParamList(values.factory_urls || "");
  const rows = urls.length ? urls : [""]; // 至少 1 行
  let html = `<div class="field"><label>工厂链接</label><div id="factoryUrlsContainer">`;
  for (let i = 0; i < rows.length; i++) {
    html += renderFactoryUrlRow(i, rows[i], i > 0);
  }
  html += `</div><button class="btn secondary" type="button" id="addFactoryUrlBtn">+ 添加工厂链接</button></div>`;
  return html;
}

function renderFactoryUrlRow(idx, value, canDelete) {
  return `<div class="factory-url-row" data-idx="${idx}">
    <input name="factory_url_${idx}" type="text" value="${escapeHtml(value)}" placeholder="https://..." />
    ${canDelete ? `<button class="btn secondary delete-factory-url" type="button" data-idx="${idx}">-</button>` : ""}
  </div>`;
}
```

3. **`openOemFullInquiryFlowRunForm` 分组渲染时**：当遇到 `factory_urls` 字段且 `type === "factory-urls-dynamic"` 时，调用 `renderFactoryUrlsDynamic` 而非 `renderFormField`：

```js
// 在分组循环里
for (const f of g.fields) {
  if (f.name === "factory_urls" && f.type === "factory-urls-dynamic") {
    bodyHtml += renderFactoryUrlsDynamic(values);
  } else {
    bodyHtml += renderFormField(f, values[f.name]);
  }
}
```

4. **绑定 +/- 按钮事件**：

```js
// 添加按钮
const addBtn = form.querySelector("#addFactoryUrlBtn");
if (addBtn) {
  addBtn.addEventListener("click", () => {
    const container = form.querySelector("#factoryUrlsContainer");
    const rows = container.querySelectorAll(".factory-url-row");
    const newIdx = rows.length;
    container.insertAdjacentHTML("beforeend", renderFactoryUrlRow(newIdx, "", true));
    syncFactoryUrlsToHidden(); // 同步到隐藏的 factory_urls
    refreshQuoteGroups();       // 联动报价分组
    bindDeleteButtons();       // 重新绑定删除按钮
  });
}

// 删除按钮（事件委托）
function bindDeleteButtons() {
  form.querySelectorAll(".delete-factory-url").forEach((btn) => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.idx);
      // 删除指定行
      const row = btn.closest(".factory-url-row");
      if (row) row.remove();
      // 重新编号所有行的 name 和 data-idx
      renumberFactoryUrlRows();
      syncFactoryUrlsToHidden();
      refreshQuoteGroups(); // 联动：删除对应索引的报价组，后续前移
    });
  });
}

function renumberFactoryUrlRows() {
  const rows = form.querySelectorAll("#factoryUrlsContainer .factory-url-row");
  rows.forEach((row, i) => {
    row.dataset.idx = i;
    const input = row.querySelector("input");
    if (input) input.name = `factory_url_${i}`;
    const delBtn = row.querySelector(".delete-factory-url");
    if (delBtn) delBtn.dataset.idx = i;
    // 第 1 行（i=0）不显示删除按钮
    if (i === 0 && delBtn) delBtn.style.display = "none";
    else if (delBtn) delBtn.style.display = "";
  });
}
```

5. **同步到隐藏的 factory_urls**（保持 variables 字符串格式）：

```js
function syncFactoryUrlsToHidden() {
  const inputs = form.querySelectorAll("#factoryUrlsContainer input[name^='factory_url_']");
  const urls = [];
  inputs.forEach((inp) => {
    const v = String(inp.value || "").trim();
    if (v) urls.push(v);
  });
  // 存到一个隐藏 input，提交时读取
  let hidden = form.querySelector('[name="factory_urls"]');
  if (!hidden) {
    hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = "factory_urls";
    form.appendChild(hidden);
  }
  hidden.value = urls.join("\n");
}

// 每个 factory_url_* input 的 input 事件都同步
form.addEventListener("input", (e) => {
  if (e.target.name && e.target.name.startsWith("factory_url_")) {
    syncFactoryUrlsToHidden();
    refreshQuoteGroups();
  }
});
```

6. **`refreshQuoteGroups` 改造**：从隐藏的 `factory_urls` 读值（而非 textarea），逻辑不变。删除时的联动行为变化：

```js
function refreshQuoteGroups() {
  const hidden = form.querySelector('[name="factory_urls"]');
  const urls = hidden ? hidden.value : "";
  const factoryCount = splitParamList(urls).length;
  // 读取当前 form 已填的 __fq_* 值（按当前索引）
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
  // 关键：按索引覆盖缓存（删除第2行时，原第3行的值变成新第2行，但用户没填过所以用默认）
  // 这里保持原逻辑：已填 > 旧缓存 > 存储的 factory_quotes
  for (let i = 0; i < factoryCount; i++) {
    fqCache[i] = { ...(factoryQuotesStored[i] || {}), ...(fqCache[i] || {}), ...newCache[i] };
  }
  // 清理超出范围的缓存
  Object.keys(fqCache).forEach((k) => {
    if (Number(k) >= factoryCount) delete fqCache[k];
  });
  const container = document.querySelector("#factoryQuoteContainer");
  if (container) container.innerHTML = renderQuoteGroups(factoryCount);
}
```

**关键**：删除第 2 行链接后，`renumberFactoryUrlRows` 把第 3 行重命名为 `factory_url_1`，`syncFactoryUrlsToHidden` 把剩余链接拼接，`refreshQuoteGroups` 按新行数重渲染报价分组。原「工厂3报价」变成「工厂2报价」（因为索引前移），但其值如果是用户填过的会丢失（因为 fqCache[2] 被清理，fqCache[1] 是用户原填的工厂2值）。

**这里有个体验权衡**：删除第2行后，原工厂3的报价数据应该「前移」到工厂2，还是工厂2用默认值？

- 方案A（前移）：原 fqCache[2] 的值赋给 fqCache[1]，原 fqCache[1] 丢弃。符合「删除第2条，第3条变成第2条」的直觉。
- 方案B（用默认）：fqCache[1] 保留用户原填的工厂2值（但该工厂链接已被删），fqCache[2] 清理。

**选方案A**（前移），因为用户删除的是「第2个工厂链接」，期望第3个工厂变成第2个，其报价数据也跟着前移。

实现方案A：
```js
// 删除按钮 click 时：
function onDeleteFactoryUrl(idx) {
  // 先把 fqCache[idx] 之后的所有缓存前移一位
  const maxIdx = Object.keys(fqCache).reduce((m, k) => Math.max(m, Number(k)), -1);
  for (let i = idx; i < maxIdx; i++) {
    fqCache[i] = fqCache[i + 1] ? { ...fqCache[i + 1] } : {};
  }
  delete fqCache[maxIdx];
  // 然后删除 DOM 行 + renumber + sync + refresh
}
```

### 改动3：CSS 样式（可选，最小化）

**位置**：`static/` 下的 CSS 文件（或内联 style）

**改动**：为 `.factory-url-row` 加简单布局（input + 按钮横排）：

```css
.factory-url-row { display: flex; gap: 8px; margin-bottom: 8px; }
.factory-url-row input { flex: 1; }
.factory-quote-group { margin: 8px 0; border-left: 3px solid var(--accent); padding-left: 12px; }
```

若现有样式已够用则不加。

## 不改动

- `app/data_scripts.py`（后端逻辑不变，factory_urls 仍是字符串）
- `app/core/utils.py`（用例模板不变）
- `app/routers/data_scripts.py`（路由不变）
- 后端 `_oem_parse_factory_urls`（保持字符串解析）

## 假设与决策

1. **factory_type select 选项**：依赖步骤0 Playwright 抓取结果。若抓取失败，fallback 到「保留 number + label 改成 `工厂类型(3=默认，具体含义见OEM后台)`」。
2. **factory_urls 存储格式**：保持字符串 `\n` 分隔，后端无感知。
3. **删除联动**：删除第 idx 行链接时，fqCache 从 idx 开始前移一位（方案A），原 idx+1 的报价数据变成新 idx。
4. **隐藏 input**：用一个 `<input type="hidden" name="factory_urls">` 存聚合后的字符串，提交时 readForm 能读到。`factory_url_*` 这些中间字段在提交时被忽略（不在 formFields 里，mergeParamValues 不会写入）。
5. **第 1 行不可删除**：保证至少有 1 个工厂链接输入框。
6. **默认行数**：打开弹窗时，若 variables.factory_urls 为空，默认 1 行空输入框；有值则按行数展开。

## 验证步骤

1. **factory_type 抓取**：Playwright 脚本能登录 OEM 后台/前台，定位到 factory_type 下拉框，dump 出选项文字。
2. **factory_type select 渲染**：打开执行弹窗，「询价单提出」section 的「工厂类型」显示为下拉框，选项文字清晰。
3. **工厂链接动态行**：打开弹窗默认 1 行；点 + 加一行（第 2 行带 - 按钮）；点 - 删第 2 行，回到 1 行。
4. **删除中间行联动**：填 3 行链接，下方展开 3 个报价组；填不同报价值；删第 2 行链接，确认下方变成 2 个报价组，且原「工厂3报价」的数据前移到「工厂2报价」。
5. **提交执行**：填 2 行链接 + 2 组不同报价，执行全流程，确认后端收到正确的 factory_urls（字符串）和 factory_quotes（数组）。
6. **向后兼容**：旧 variables（factory_urls 是字符串）打开弹窗，能正确解析成多行输入框。
7. **git commit**：自测通过后提交。

## 文件清单

- `static/app.js`（schema factory_type 改 select + factory_urls 改动态行 + openOemFullInquiryFlowRunForm 重构）
- 可能新增 `_tmp_probe_factory_type.py`（Playwright 抓取脚本，抓完删除）

## 执行顺序

1. 先写并运行 Playwright 抓取脚本，获取 factory_type 选项文字
2. 根据抓取结果修改 schema 的 factory_type 为 select
3. 修改 factory_urls 为动态行 + 联动逻辑
4. 前端 UI 自测（打开弹窗、增删行、联动、提交）
5. 后端全流程自测（2 工厂差异化报价）
6. 清理临时脚本 + git commit
