<template>
  <button
    v-bind="$attrs"
    class="v2-base-icon-button"
    :class="[
      `v2-base-icon-button--${variant}`,
      `v2-base-icon-button--${size}`,
      { 'v2-base-icon-button--pressed': pressed === true },
    ]"
    type="button"
    :aria-label="label"
    :aria-pressed="pressedValue"
    :disabled="disabled"
    @click="handleClick"
  >
    <span class="v2-base-icon-button__icon" aria-hidden="true">
      <slot />
    </span>
  </button>
</template>

<script setup>
import { computed } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  label: { type: String, required: true },
  size: {
    type: String,
    default: 'default',
    validator: (value) => ['default', 'compact'].includes(value),
  },
  variant: {
    type: String,
    default: 'ghost',
    validator: (value) => ['ghost', 'secondary'].includes(value),
  },
  disabled: { type: Boolean, default: false },
  pressed: { type: Boolean, default: undefined },
})

const emit = defineEmits(['click'])
const pressedValue = computed(() =>
  typeof props.pressed === 'boolean' ? props.pressed : undefined
)

function handleClick(event) {
  if (props.disabled) return
  emit('click', event)
}
</script>

<style scoped>
@layer v2-components {
  .v2-base-icon-button {
    width: var(--v2-icon-button-size);
    height: var(--v2-icon-button-size);
    display: inline-grid;
    place-items: center;
    flex: 0 0 auto;
    padding: 0;
    color: var(--v2-icon-button-text);
    background: var(--v2-icon-button-surface);
    border: var(--v2-border-width) solid var(--v2-color-overlay-transparent);
    border-radius: var(--v2-icon-button-radius);
    cursor: pointer;
    transition:
      color var(--v2-motion-duration) var(--v2-motion-easing),
      background-color var(--v2-motion-duration) var(--v2-motion-easing),
      border-color var(--v2-motion-duration) var(--v2-motion-easing),
      opacity var(--v2-motion-duration) var(--v2-motion-easing);
  }

  .v2-base-icon-button:hover:not(:disabled) {
    background: var(--v2-icon-button-surface-hover);
  }

  .v2-base-icon-button:active:not(:disabled) {
    background: var(--v2-icon-button-surface-pressed);
  }

  .v2-base-icon-button:focus-visible {
    outline: none;
    box-shadow: var(--v2-icon-button-focus-ring);
  }

  .v2-base-icon-button:disabled {
    cursor: not-allowed;
    opacity: var(--v2-icon-button-disabled-opacity);
  }

  .v2-base-icon-button--compact {
    width: var(--v2-icon-button-size-compact);
    height: var(--v2-icon-button-size-compact);
  }

  .v2-base-icon-button--secondary {
    background: var(--v2-icon-button-secondary-surface);
    border-color: var(--v2-icon-button-secondary-border);
  }

  .v2-base-icon-button--pressed {
    color: var(--v2-icon-button-pressed-text);
    background: var(--v2-icon-button-pressed-surface);
  }

  .v2-base-icon-button__icon {
    width: var(--v2-icon-button-icon-size);
    height: var(--v2-icon-button-icon-size);
    display: grid;
    place-items: center;
  }

  .v2-base-icon-button__icon :deep(svg) {
    width: 100%;
    height: 100%;
  }
}
</style>
