<template>
  <div class="v2-data-script-catalog">
    <button
      v-for="item in items"
      :key="item.script_type"
      class="v2-data-script-catalog__item"
      :class="{ 'v2-data-script-catalog__item--active': item.script_type === selected }"
      type="button"
      @click="emit('select', item.script_type)"
    >
      <span class="v2-data-script-catalog__copy">
        <strong>{{ item.name }}</strong>
        <small>{{ item.script_type }}</small>
      </span>
      <WorkbenchStatus :tone="item.risk_level === 'high' ? 'warning' : 'neutral'" :label="item.risk_level === 'high' ? '高风险' : '标准'" compact />
    </button>
    <BaseEmptyState v-if="!items.length" title="没有可用脚本" compact icon-hidden />
  </div>
</template>

<script setup>
import { BaseEmptyState } from '../v2/base/index.js'
import { WorkbenchStatus } from '../v2/workbench/index.js'

defineProps({ items: { type: Array, default: () => [] }, selected: { type: String, default: '' } })
const emit = defineEmits(['select'])
</script>

<style scoped>
.v2-data-script-catalog {
  display: grid;
}

.v2-data-script-catalog__item {
  display: flex;
  min-height: var(--v2-size-table-row);
  align-items: center;
  justify-content: space-between;
  gap: var(--v2-space-2);
  padding: var(--v2-space-2) var(--v2-space-3);
  border: 0;
  border-bottom: var(--v2-border-width) solid var(--v2-border-panel);
  background: var(--v2-surface-default);
  color: var(--v2-text-secondary);
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.v2-data-script-catalog__item:hover,
.v2-data-script-catalog__item--active {
  background: var(--v2-action-primary-soft);
}

.v2-data-script-catalog__item--active {
  box-shadow: inset calc(var(--v2-border-width) * 3) 0 var(--v2-action-primary);
}

.v2-data-script-catalog__item:focus-visible {
  outline: 0;
  box-shadow: var(--v2-state-focus-ring);
}

.v2-data-script-catalog__copy {
  display: grid;
  gap: var(--v2-space-micro);
  min-width: 0;
}

.v2-data-script-catalog__copy strong {
  overflow: hidden;
  color: var(--v2-text-primary);
  font-size: var(--v2-font-size-caption);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.v2-data-script-catalog__copy small {
  color: var(--v2-text-muted);
  font-family: var(--v2-font-family-mono);
  font-size: var(--v2-font-size-tiny);
}
</style>
