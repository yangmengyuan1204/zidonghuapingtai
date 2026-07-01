# 数据工厂新增「已隐藏」tab 与「隐藏」按钮

## 现状说明

经探索 `static/app.js`，**hidden 功能代码已完整实现**（来自上一会话），与现有 deleted 范式完全对称。本计划的实际工作仅为：**语法检查 + git 提交**，无需再写任何业务代码。

## 已完成改动清单（验证参考）

所有改动均在 `d:\A_zidonghuapingtai\static\app.js` 单文件内：

### 1. 新增 storage key 常量（第 1 行长行内）
- `HIDDEN_FLOW_STORAGE_KEY = "dataFactoryHiddenFlows"`
- `HIDDEN_BUILTIN_KEY = "dataFactoryHiddenBuiltins"`

### 2. 修改 `isBuiltinDeleted`（第 36 行长行内）
合并 hidden 检查，使所有 `ensureXxxScript` 函数自动跳过隐藏的内置脚本：
```js
function isBuiltinDeleted(id) {
  return readDeletedBuiltins().includes(id) || readHiddenBuiltins().includes(id);
}
```

### 3. 修改 `isDeletedBuiltinFlow`（第 36 行长行内）
只检查 deleted 列表，不再调用 `isBuiltinDeleted`，避免误把 hidden 内置 flow 从 `dataFactoryFlows` 中删除：
```js
function isDeletedBuiltinFlow(flow) {
  const definition = builtinDefinitionForFlow(flow);
  return Boolean(definition && readDeletedBuiltins().includes(definition.id));
}
```

### 4. 新增 hidden 辅助函数组（第 36 行长行内）
与 deleted 函数一一对应：`readHiddenFlows` / `writeHiddenFlows` / `readHiddenBuiltins` / `writeHiddenBuiltins` / `removeBuiltinHidden` / `hiddenEntryKey` / `markBuiltinHidden` / `saveHiddenFlow` / `restoreHiddenFlow` / `hiddenDataScriptRows`。

### 5. 修改 `renderDataScripts`（第 37–307 行）
- **第 107 行**：新增 `hiddenRows` 计算
- **第 109 行**：新增 `isHiddenTab = state.dataScriptTab === "hidden"`
- **第 129 行**：active 表格 actions 列新增「隐藏」按钮 `<button class="btn secondary" data-hide-script="${row.id}">隐藏</button>`
- **第 148–158 行**：新增 `hiddenTable`（列：脚本名称/项目/环境/类型/隐藏时间/操作「恢复显示」）
- **第 163 行**：tab 按钮新增 `tabButton("hidden", "已隐藏", hiddenRows.length)`，顺序 active → hidden → deleted
- **第 164、166 行**：客户ID框和新建脚本按钮显隐条件改为 `!isDeletedTab && !isHiddenTab`
- **第 168 行**：表格切换逻辑改为 `isHiddenTab ? hiddenTable : isDeletedTab ? deletedTable : activeTable`
- **第 204–213 行**：新增 `data-restore-hidden-script` 事件绑定，恢复后回 active tab
- **第 214 行**：提前返回条件改为 `if (isDeletedTab || isHiddenTab) return;`
- **第 285–307 行**：新增 `data-hide-script` 事件绑定（保存快照 → 标记 builtin hidden → 从 flows 移除 → 刷新）

## 待执行步骤

### 步骤 1：JS 语法检查
```
node --check d:\A_zidonghuapingtai\static\app.js
```
通过则进入步骤 2；失败则定位语法错误并最小修复。

### 步骤 2：git 提交
```
git add static/app.js
git commit -m "数据工厂新增已隐藏tab与隐藏按钮"
```
按 AGENTS.md 规则，不主动 push。

## 验证步骤（用户在浏览器自测）

1. 打开数据工厂页面，确认 tab 栏出现「脚本列表 / 已隐藏 / 已删除」三个 tab
2. 在「脚本列表」中点击任一脚本的「隐藏」按钮 → 该脚本从列表消失，「已隐藏」tab 计数 +1
3. 切换到「已隐藏」tab → 看到刚隐藏的脚本，含「隐藏时间」列和「恢复显示」按钮
4. 点击「恢复显示」→ 脚本回到「脚本列表」，「已隐藏」tab 计数 -1
5. 刷新页面 → 隐藏状态保持（localStorage 持久化生效）
6. 隐藏一个内置脚本 → 不应被 `ensure` 函数重新注入（验证 `isBuiltinDeleted` 已合并 hidden 检查）
7. 隐藏与删除互不干扰：删除的脚本不出现在已隐藏 tab，反之亦然

## 假设与决策

- **纯前端 localStorage 方案**：无后端变更，与现有 deleted 范式一致。
- **复用 `isBuiltinDeleted` 桥接**：避免改动 8 处 `ensureXxxScript` 调用点，最小改动。
- **`isDeletedBuiltinFlow` 不再调用 `isBuiltinDeleted`**：避免 hidden 的内置 flow 在 `storedFlows.filter((flow) => !isDeletedBuiltinFlow(flow))` 中被误删。
- **不主动 push**：遵循 AGENTS.md 默认规则。
