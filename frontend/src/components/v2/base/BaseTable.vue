<template>
  <div
    class="v2-base-table"
    role="region"
    :aria-label="`${ariaLabel}可滚动区域`"
    :aria-busy="loading ? 'true' : undefined"
    tabindex="0"
  >
    <table
      class="v2-base-table__table"
      :style="tableStyle"
      :aria-label="ariaLabel"
    >
      <thead class="v2-base-table__head">
        <tr>
          <th
            v-for="column in columns"
            :key="column.key"
            class="v2-base-table__header"
            scope="col"
          >
            <slot :name="`header-${column.key}`" :column="column">
              {{ column.label }}
            </slot>
          </th>
        </tr>
      </thead>
      <tbody class="v2-base-table__body">
        <tr v-if="loading" class="v2-base-table__state-row">
          <td class="v2-base-table__state-cell" :colspan="columnCount">
            <slot name="loading">
              <span role="status">正在加载</span>
            </slot>
          </td>
        </tr>
        <tr v-else-if="rows.length === 0" class="v2-base-table__state-row">
          <td class="v2-base-table__state-cell" :colspan="columnCount">
            <slot name="empty">暂无数据</slot>
          </td>
        </tr>
        <template v-else>
          <tr
            v-for="(row, rowIndex) in rows"
            :key="resolveRowKey(row, rowIndex)"
            class="v2-base-table__row"
          >
            <td
              v-for="column in columns"
              :key="column.key"
              class="v2-base-table__cell"
            >
              <slot
                :name="column.key"
                :row="row"
                :column="column"
                :row-index="rowIndex"
                :value="row[column.key]"
              >
                {{ row[column.key] }}
              </slot>
            </td>
          </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  columns: { type: Array, required: true },
  rows: { type: Array, default: () => [] },
  rowKey: { type: [String, Function], default: 'id' },
  ariaLabel: { type: String, default: '数据表格' },
  loading: { type: Boolean, default: false },
  minContentWidth: { type: [String, Number], default: '100%' },
})

const columnCount = computed(() => Math.max(1, props.columns.length))
const tableStyle = computed(() => ({
  '--v2-base-table-min-content-width': typeof props.minContentWidth === 'number'
    ? `${props.minContentWidth}px`
    : props.minContentWidth,
}))

function resolveRowKey(row, index) {
  if (typeof props.rowKey === 'function') return props.rowKey(row, index)
  return row?.[props.rowKey] ?? index
}
</script>

<style scoped>
@layer v2-components {
  .v2-base-table {
    width: 100%;
    max-width: 100%;
    overflow-x: auto;
    color: var(--v2-table-text);
    background: var(--v2-table-surface);
    border: var(--v2-border-width) solid var(--v2-color-panel-border);
    border-radius: var(--v2-table-radius);
  }

  .v2-base-table:focus-visible {
    outline: none;
    box-shadow: var(--v2-table-focus-ring);
  }

  .v2-base-table__table {
    width: 100%;
    min-width: var(--v2-base-table-min-content-width);
    border-spacing: 0;
    border-collapse: separate;
    font-size: var(--v2-table-font-size);
    line-height: var(--v2-line-height-body);
    text-align: left;
  }

  .v2-base-table__head {
    background: var(--v2-table-header-surface);
  }

  .v2-base-table__header,
  .v2-base-table__cell {
    padding: var(--v2-table-cell-padding-y) var(--v2-table-cell-padding-x);
    border-top: 0;
    border-right: 0;
    border-left: 0;
    border-bottom: var(--v2-border-width) solid var(--v2-table-border);
    vertical-align: middle;
  }

  .v2-base-table__header {
    height: var(--v2-table-header-height);
    color: var(--v2-table-header-text);
    background: var(--v2-table-header-surface);
    font-size: var(--v2-table-header-font-size);
    font-weight: var(--v2-table-header-font-weight);
    letter-spacing: 0.01em;
    white-space: nowrap;
  }

  .v2-base-table__row {
    min-height: var(--v2-table-row-height);
    transition: background-color var(--v2-motion-duration) var(--v2-motion-easing);
  }

  .v2-base-table__cell {
    height: var(--v2-table-row-height);
    color: var(--v2-color-text-body);
  }

  .v2-base-table__row:hover {
    background: var(--v2-table-row-hover);
  }

  .v2-base-table__body .v2-base-table__row:last-child .v2-base-table__cell,
  .v2-base-table__state-row:last-child .v2-base-table__state-cell {
    border-bottom: 0;
  }

  .v2-base-table__state-cell {
    min-height: var(--v2-table-row-height);
    padding: var(--v2-table-state-padding);
    color: var(--v2-table-text-muted);
    border-bottom: var(--v2-border-width) solid var(--v2-table-border);
    text-align: center;
  }
}

/* Legacy global th styles are unlayered, so keep the visual override unlayered too. */
.v2-base-table__header {
  background: var(--v2-table-header-surface);
  border-right: 0;
  border-left: 0;
}
</style>
