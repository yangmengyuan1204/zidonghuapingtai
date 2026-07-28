<template>
  <div v-if="!rows.length" :class="framed ? 'panel' : ''">
    <div class="empty">暂无数据</div>
  </div>
  <div v-else :class="['table-wrap', framed ? 'panel' : '']">
    <table>
      <thead>
        <tr>
          <th v-for="col in columns" :key="col.key">{{ col.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="row.id || index" v-bind="rowAttrs ? rowAttrs(row) : {}">
          <td v-for="col in columns" :key="col.key">
            <slot v-if="col.slot" :name="col.slot" :row="row" :index="index" />
            <template v-else-if="col.render && col.html === true" v-html="col.render(row)"></template>
            <template v-else-if="col.render">{{ col.render(row) }}</template>
            <template v-else>{{ short(row[col.key]) }}</template>
          </td>
        </tr>
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
/* 使用旧应用 .table-wrap / .panel / .empty 样式（来自 legacy.css） */
</style>
