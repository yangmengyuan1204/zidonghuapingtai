<template>
  <span
    class="v2-base-badge"
    :class="[`v2-base-badge--${tone}`, `v2-base-badge--${size}`]"
  >
    <span v-if="dot" class="v2-base-badge__dot" aria-hidden="true"></span>
    <span class="v2-base-badge__text"><slot /></span>
  </span>
</template>

<script setup>
defineProps({
  tone: {
    type: String,
    default: 'neutral',
    validator: (value) => ['neutral', 'success', 'warning', 'danger', 'info'].includes(value),
  },
  size: {
    type: String,
    default: 'default',
    validator: (value) => ['default', 'compact'].includes(value),
  },
  dot: { type: Boolean, default: false },
})
</script>

<style scoped>
@layer v2-components {
  .v2-base-badge {
    height: var(--v2-badge-height);
    min-height: var(--v2-badge-height);
    display: inline-flex;
    align-items: center;
    gap: var(--v2-badge-gap);
    padding: 0 var(--v2-badge-padding);
    color: var(--v2-badge-text);
    background: var(--v2-badge-surface);
    border: var(--v2-border-width) solid transparent;
    border-radius: var(--v2-badge-radius);
    font-size: var(--v2-badge-font-size);
    font-weight: var(--v2-badge-font-weight);
    line-height: 1;
    white-space: nowrap;
  }

  .v2-base-badge--compact {
    height: var(--v2-badge-height-compact);
    min-height: var(--v2-badge-height-compact);
    padding: 0 var(--v2-badge-padding-compact);
    font-size: var(--v2-badge-font-size-compact);
  }

  .v2-base-badge--success {
    color: var(--v2-badge-success-text);
    background: var(--v2-badge-success-surface);
  }

  .v2-base-badge--warning {
    color: var(--v2-badge-warning-text);
    background: var(--v2-badge-warning-surface);
  }

  .v2-base-badge--danger {
    color: var(--v2-badge-danger-text);
    background: var(--v2-badge-danger-surface);
  }

  .v2-base-badge--info {
    color: var(--v2-badge-info-text);
    background: var(--v2-badge-info-surface);
  }

  .v2-base-badge__dot {
    width: var(--v2-badge-dot-size);
    height: var(--v2-badge-dot-size);
    flex: 0 0 auto;
    background: currentColor;
    border-radius: var(--v2-radius-round);
  }
}
</style>
