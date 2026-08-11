<template>
  <ul v-if="items.length" class="v2-workbench-attention-list">
    <li v-for="item in items" :key="item.id" class="v2-workbench-attention-list__item">
      <WorkbenchStatus
        class="v2-workbench-attention-list__status"
        :tone="item.tone"
        :label="item.title"
        :detail="item.detail"
      />
      <button
        v-if="item.actionLabel"
        class="v2-workbench-attention-list__action"
        type="button"
        @click="emit('action', item.id)"
      >
        {{ item.actionLabel }}
      </button>
    </li>
  </ul>
  <p v-else class="v2-workbench-attention-list__empty">当前没有需要处理的事项</p>
</template>

<script setup>
import WorkbenchStatus from './WorkbenchStatus.vue'

defineProps({
  items: { type: Array, default: () => [] },
})

const emit = defineEmits(['action'])
</script>

<style scoped>
.v2-workbench-attention-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.v2-workbench-attention-list__item {
  display: flex;
  min-height: var(--v2-size-table-row);
  align-items: center;
  justify-content: space-between;
  gap: var(--v2-space-3);
  padding: var(--v2-space-2) var(--v2-space-3);
}

.v2-workbench-attention-list__item + .v2-workbench-attention-list__item {
  border-top: var(--v2-border-width) solid var(--v2-border-panel);
}

.v2-workbench-attention-list__status {
  min-width: 0;
}

.v2-workbench-attention-list__action {
  min-height: var(--v2-control-height-compact);
  flex: 0 0 auto;
  padding: 0 var(--v2-space-2);
  border: var(--v2-border-width) solid var(--v2-border-default);
  border-radius: var(--v2-radius-sm);
  background: var(--v2-surface-default);
  color: var(--v2-action-primary);
  cursor: pointer;
  font: inherit;
  font-size: var(--v2-font-size-caption);
  font-weight: var(--v2-font-weight-semibold);
}

.v2-workbench-attention-list__action:hover {
  border-color: var(--v2-border-focus);
  background: var(--v2-action-primary-soft);
}

.v2-workbench-attention-list__action:focus-visible {
  outline: 0;
  box-shadow: var(--v2-state-focus-ring);
}

.v2-workbench-attention-list__empty {
  margin: 0;
  padding: var(--v2-space-5) var(--v2-space-3);
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-body);
  text-align: center;
}
</style>
