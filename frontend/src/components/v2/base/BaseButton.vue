<template>
  <button
    v-bind="$attrs"
    class="v2-base-button"
    :class="[
      `v2-base-button--${variant}`,
      `v2-base-button--${size}`,
      { 'v2-base-button--block': block, 'v2-base-button--loading': loading },
    ]"
    :type="type"
    :disabled="loading || disabled"
    :aria-busy="loading || undefined"
    @click="handleClick"
  >
    <span
      class="v2-base-button__content"
      :class="{ 'v2-base-button__content--hidden': loading }"
    >
      <span v-if="$slots.icon" class="v2-base-button__icon" aria-hidden="true">
        <slot name="icon" />
      </span>
      <span class="v2-base-button__label"><slot /></span>
    </span>
    <span v-if="loading" class="v2-base-button__loading" role="status">
      <span class="v2-base-button__loading-indicator" aria-hidden="true"></span>
      <span class="v2-visually-hidden">加载中</span>
    </span>
  </button>
</template>

<script setup>
defineOptions({ inheritAttrs: false })

const props = defineProps({
  type: {
    type: String,
    default: 'button',
    validator: (value) => ['button', 'submit', 'reset'].includes(value),
  },
  variant: {
    type: String,
    default: 'primary',
    validator: (value) => ['primary', 'secondary', 'ghost', 'danger'].includes(value),
  },
  size: {
    type: String,
    default: 'default',
    validator: (value) => ['default', 'compact'].includes(value),
  },
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  block: { type: Boolean, default: false },
})

const emit = defineEmits(['click'])

function handleClick(event) {
  if (props.disabled || props.loading) return
  emit('click', event)
}
</script>

<style scoped>
@layer v2-components {
  .v2-base-button {
    position: relative;
    height: var(--v2-button-height);
    min-height: var(--v2-button-height);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0 var(--v2-button-padding);
    color: var(--v2-button-text);
    background: var(--v2-button-bg);
    border: var(--v2-button-border-width) solid var(--v2-button-bg);
    border-radius: var(--v2-button-radius);
    font-size: var(--v2-button-font-size);
    font-weight: var(--v2-button-font-weight);
    line-height: var(--v2-line-height-tight);
    white-space: nowrap;
    cursor: pointer;
    box-shadow: none;
    transition:
      color var(--v2-motion-duration) var(--v2-motion-easing),
      background-color var(--v2-motion-duration) var(--v2-motion-easing),
      border-color var(--v2-motion-duration) var(--v2-motion-easing),
      opacity var(--v2-motion-duration) var(--v2-motion-easing);
  }

  .v2-base-button:hover:not(:disabled) {
    background: var(--v2-button-bg-hover);
    border-color: var(--v2-button-bg-hover);
  }

  .v2-base-button:active:not(:disabled) {
    background: var(--v2-button-bg-pressed);
    border-color: var(--v2-button-bg-pressed);
  }

  .v2-base-button:focus-visible {
    outline: none;
    box-shadow: var(--v2-button-focus-ring);
  }

  .v2-base-button:disabled {
    cursor: not-allowed;
    opacity: var(--v2-button-disabled-opacity);
  }

  .v2-base-button--compact {
    height: var(--v2-button-height-compact);
    min-height: var(--v2-button-height-compact);
    padding: 0 var(--v2-button-padding-compact);
    font-size: var(--v2-font-size-caption);
  }

  .v2-base-button--block {
    width: 100%;
  }

  .v2-base-button--secondary {
    color: var(--v2-button-secondary-text);
    background: var(--v2-button-secondary-bg);
    border-color: var(--v2-button-secondary-border);
  }

  .v2-base-button--secondary:hover:not(:disabled) {
    color: var(--v2-action-primary);
    background: var(--v2-button-secondary-bg-hover);
    border-color: var(--v2-action-primary);
  }

  .v2-base-button--secondary:active:not(:disabled) {
    background: var(--v2-button-secondary-bg-pressed);
  }

  .v2-base-button--ghost {
    color: var(--v2-button-ghost-text);
    background: var(--v2-button-ghost-bg);
    border-color: var(--v2-button-ghost-border);
  }

  .v2-base-button--ghost:hover:not(:disabled) {
    color: var(--v2-button-ghost-text-hover);
    background: var(--v2-button-ghost-bg-hover);
  }

  .v2-base-button--ghost:active:not(:disabled) {
    background: var(--v2-button-ghost-bg-pressed);
  }

  .v2-base-button--danger {
    color: var(--v2-button-danger-text);
    background: var(--v2-button-danger-bg);
    border-color: var(--v2-button-danger-border);
  }

  .v2-base-button--danger:hover:not(:disabled) {
    background: var(--v2-button-danger-bg-hover);
    border-color: var(--v2-button-danger-bg-hover);
  }

  .v2-base-button--danger:active:not(:disabled) {
    background: var(--v2-button-danger-bg-pressed);
    border-color: var(--v2-button-danger-bg-pressed);
  }

  .v2-base-button__content {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--v2-button-gap);
  }

  .v2-base-button__content--hidden {
    visibility: hidden;
  }

  .v2-base-button__icon {
    width: var(--v2-icon-size-sm);
    height: var(--v2-icon-size-sm);
    display: inline-grid;
    place-items: center;
  }

  .v2-base-button__icon :deep(svg) {
    width: 100%;
    height: 100%;
  }

  .v2-base-button__loading {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
  }

  .v2-base-button__loading-indicator {
    width: var(--v2-button-loading-indicator-size);
    height: var(--v2-button-loading-indicator-size);
    border: var(--v2-button-border-width) solid currentColor;
    border-radius: var(--v2-radius-round);
    opacity: var(--v2-opacity-pressed);
  }
}
</style>
