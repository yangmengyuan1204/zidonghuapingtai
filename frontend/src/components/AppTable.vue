<template>
  <div class="v2-app-table" :class="{ 'v2-app-table--framed': framed }" role="region" aria-label="数据表格可滚动区域" tabindex="0">
    <table class="v2-app-table__table">
      <thead class="v2-app-table__head">
        <tr>
          <th v-for="col in columns" :key="col.key" class="v2-app-table__header" scope="col">{{ col.label }}</th>
        </tr>
      </thead>
      <tbody class="v2-app-table__body">
        <tr v-if="!rows.length" class="v2-app-table__state-row">
          <td class="v2-app-table__state-cell" :colspan="Math.max(1, columns.length)">暂无数据</td>
        </tr>
        <template v-else>
          <tr v-for="(row, index) in rows" :key="row.id || index" class="v2-app-table__row" v-bind="rowAttrs ? rowAttrs(row) : {}">
            <td v-for="col in columns" :key="col.key" class="v2-app-table__cell">
              <slot v-if="col.slot" :name="col.slot" :row="row" :index="index" />
              <template v-else-if="col.render && col.html === true" v-html="col.render(row)"></template>
              <template v-else-if="col.render">{{ col.render(row) }}</template>
              <template v-else>{{ short(row[col.key]) }}</template>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>

<script setup>
/**
 * 通用表格组件
 * 对齐旧应用 app.js renderTable(columns, rows, framed, rowAttrs)
 *
 * columns: [{ key, label, render?, html?, slot? }]
 *   - slot: 优先级最高，使用具名插槽渲染（推荐用法，Vue 风格）
 *   - render: 自定义渲染函数，返回字符串
 *             默认按普通文本输出（Vue 插值，自动转义）
 *             仅当 col.html === true 时，才通过 v-html 渲染（解析 HTML 标签）
 *   - 都没有: 普通文本列，调用 short() 截断
 *
 * rows: array
 * framed: 是否带 panel 外框
 * rowAttrs: function(row) => object（返回 v-bind 属性）
 *
 * 渲染优先级（从高到低）：
 * 1. col.slot 存在            → 使用 slot
 * 2. col.render + col.html    → v-html 渲染（显式声明 HTML 输出）
 * 3. col.render（无 html）     → 普通文本输出（Vue 插值，自动转义）
 * 4. 都没有                    → short() 普通文本
 *
 * 安全策略（重要）：
 * - v-html 必须显式声明 col.html === true 才会启用
 * - 避免"新增 render() 却忘记 HTML 安全约束"的隐患
 * - 旧应用迁移时，只有返回 HTML 字符串的 render 才需要加 html: true
 * - 返回纯文本的 render 无需加 html: true，默认安全
 */
defineProps({
  columns: { type: Array, required: true },
  rows: { type: Array, default: () => [] },
  framed: { type: Boolean, default: true },
  rowAttrs: { type: Function, default: null },
})

function short(value, length = 140) {
  // 对齐旧应用 app.js short(value, length = 140)：截断长度 140，后缀 "..."
  const s = String(value ?? '')
  return s.length > length ? s.slice(0, length) + '...' : s
}
</script>

<style scoped>
.v2-app-table {
  width: 100%;
  max-width: 100%;
  overflow-x: auto;
  border-radius: var(--v2-radius-panel);
  background: var(--v2-surface-default);
}

.v2-app-table--framed {
  border: var(--v2-border-width) solid var(--v2-border-panel);
  box-shadow: var(--v2-shadow-panel);
}

.v2-app-table:focus-visible {
  outline: 0;
  box-shadow: var(--v2-state-focus-ring);
}

.v2-app-table__table {
  width: 100%;
  min-width: 760px;
  border-spacing: 0;
  border-collapse: separate;
  color: var(--v2-text-secondary);
  font-size: var(--v2-table-font-size);
  text-align: left;
}

.v2-app-table__head {
  background: var(--v2-surface-soft);
}

.v2-app-table__header,
.v2-app-table__cell {
  padding: var(--v2-table-cell-padding-y) var(--v2-table-cell-padding-x);
  border-bottom: var(--v2-border-width) solid var(--v2-border-panel);
  vertical-align: middle;
}

.v2-app-table__header {
  height: var(--v2-table-header-height);
  color: var(--v2-table-header-text);
  background: var(--v2-table-header-surface);
  font-size: var(--v2-table-header-font-size);
  font-weight: var(--v2-table-header-font-weight);
  letter-spacing: 0;
  text-transform: none;
}

.v2-app-table__row {
  min-height: var(--v2-table-row-height);
  transition: background-color var(--v2-motion-duration) var(--v2-motion-easing);
}

.v2-app-table__cell {
  height: var(--v2-table-row-height);
}

.v2-app-table__row:hover {
  background: var(--v2-surface-hover);
}

.v2-app-table__body .v2-app-table__row:last-child .v2-app-table__cell {
  border-bottom: 0;
}

.v2-app-table__state-cell {
  padding: var(--v2-space-6) var(--v2-space-3);
  color: var(--v2-text-muted);
  text-align: center;
}
</style>
