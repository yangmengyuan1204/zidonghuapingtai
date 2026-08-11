<template>
  <span
    class="v2-workbench-status"
    :class="[`v2-workbench-status--${normalizedTone}`, { 'v2-workbench-status--compact': compact }]"
  >
    <span class="v2-workbench-status__mark" aria-hidden="true">{{ mark }}</span>
    <span class="v2-workbench-status__copy">
      <strong class="v2-workbench-status__label">{{ label }}</strong>
      <span v-if="detail && !compact" class="v2-workbench-status__detail">{{ detail }}</span>
    </span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  tone: { type: String, default: 'neutral' },
  label: { type: String, required: true },
  detail: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})

const allowedTones = new Set(['neutral', 'success', 'warning', 'danger', 'info'])
const normalizedTone = computed(() => allowedTones.has(props.tone) ? props.tone : 'neutral')
const marks = { neutral: '–', success: '✓', warning: '!', danger: '×', info: 'i' }
const mark = computed(() => marks[normalizedTone.value])
</script>

<style scoped>
.v2-workbench-status {
  display: inline-flex;
  align-items: center;
  gap: var(--v2-space-1);
  color: var(--v2-text-secondary);
}

.v2-workbench-status__mark {
  display: inline-grid;
  width: var(--v2-icon-size-md);
  height: var(--v2-icon-size-md);
  flex: 0 0 auto;
  place-items: center;
  border-radius: var(--v2-radius-round);
  background: var(--v2-surface-soft);
  color: var(--v2-text-secondary);
  font-size: var(--v2-font-size-caption);
  font-weight: var(--v2-font-weight-bold);
}

.v2-workbench-status__copy {
  display: grid;
  gap: var(--v2-space-micro);
  min-width: 0;
}

.v2-workbench-status__label {
  color: inherit;
  font-size: var(--v2-font-size-caption);
  font-weight: var(--v2-font-weight-semibold);
}

.v2-workbench-status__detail {
  overflow: hidden;
  color: var(--v2-text-muted);
  font-size: var(--v2-font-size-tiny);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.v2-workbench-status--success {
  color: var(--v2-feedback-success);
}

.v2-workbench-status--success .v2-workbench-status__mark {
  background: var(--v2-feedback-success-soft);
  color: var(--v2-feedback-success);
}

.v2-workbench-status--warning {
  color: var(--v2-feedback-warning);
}

.v2-workbench-status--warning .v2-workbench-status__mark {
  background: var(--v2-feedback-warning-soft);
  color: var(--v2-feedback-warning);
}

.v2-workbench-status--danger {
  color: var(--v2-feedback-danger);
}

.v2-workbench-status--danger .v2-workbench-status__mark {
  background: var(--v2-feedback-danger-soft);
  color: var(--v2-feedback-danger);
}

.v2-workbench-status--info {
  color: var(--v2-feedback-info);
}

.v2-workbench-status--info .v2-workbench-status__mark {
  background: var(--v2-feedback-info-soft);
  color: var(--v2-feedback-info);
}

.v2-workbench-status--compact {
  gap: var(--v2-space-micro);
}

.v2-workbench-status--compact .v2-workbench-status__mark {
  width: var(--v2-icon-size-sm);
  height: var(--v2-icon-size-sm);
  font-size: var(--v2-font-size-tiny);
}
</style>
