<template>
  <button
    v-bind="$attrs"
    class="v2-base-dropdown-item"
    :class="{ 'v2-base-dropdown-item--danger': danger }"
    type="button"
    role="menuitem"
    tabindex="-1"
    :aria-disabled="disabled ? 'true' : undefined"
    :disabled="disabled"
    data-v2-dropdown-item
    @click="handleClick"
  >
    <span v-if="$slots.icon" class="v2-base-dropdown-item__icon" aria-hidden="true">
      <slot name="icon" />
    </span>
    <span
      v-else-if="danger && !$slots.icon"
      class="v2-base-dropdown-item__danger-cue"
      aria-hidden="true"
    >!</span>
    <span class="v2-base-dropdown-item__label"><slot /></span>
    <span v-if="$slots.suffix" class="v2-base-dropdown-item__suffix">
      <slot name="suffix" />
    </span>
  </button>
</template>

<script setup>
import { inject } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  value: { type: null, default: null },
  disabled: { type: Boolean, default: false },
  danger: { type: Boolean, default: false },
})

const emit = defineEmits(['select'])
const dropdown = inject('v2-base-dropdown', null)

function handleClick(event) {
  if (props.disabled) return
  emit('select', props.value, event)
  dropdown?.selectItem(props.value, event)
}
</script>

<style scoped>
@layer v2-components {
  .v2-base-dropdown-item {
    width: 100%;
    min-height: var(--v2-dropdown-item-height);
    display: flex;
    align-items: center;
    gap: var(--v2-dropdown-item-gap);
    padding: 0 var(--v2-dropdown-item-padding);
    color: var(--v2-dropdown-item-text);
    background: var(--v2-dropdown-item-surface);
    border: 0;
    border-radius: var(--v2-dropdown-item-radius);
    font-size: var(--v2-dropdown-item-font-size);
    line-height: var(--v2-line-height-body);
    text-align: left;
    cursor: pointer;
  }

  .v2-base-dropdown-item:hover:not(:disabled),
  .v2-base-dropdown-item:focus-visible:not(:disabled) {
    color: var(--v2-dropdown-item-text-hover);
    background: var(--v2-dropdown-item-surface-hover);
    outline: none;
  }

  .v2-base-dropdown-item:focus-visible {
    box-shadow: var(--v2-dropdown-item-focus-ring);
  }

  .v2-base-dropdown-item:disabled {
    color: var(--v2-dropdown-item-text-disabled);
    cursor: not-allowed;
    opacity: var(--v2-dropdown-item-disabled-opacity);
  }

  .v2-base-dropdown-item--danger:not(:disabled) {
    color: var(--v2-dropdown-item-danger-text);
  }

  .v2-base-dropdown-item--danger:hover:not(:disabled),
  .v2-base-dropdown-item--danger:focus-visible:not(:disabled) {
    background: var(--v2-dropdown-item-danger-surface-hover);
  }

  .v2-base-dropdown-item__icon,
  .v2-base-dropdown-item__danger-cue,
  .v2-base-dropdown-item__suffix {
    flex: 0 0 auto;
    color: currentColor;
  }

  .v2-base-dropdown-item__icon {
    width: var(--v2-dropdown-item-icon-size);
    height: var(--v2-dropdown-item-icon-size);
    display: grid;
    place-items: center;
  }

  .v2-base-dropdown-item__danger-cue {
    width: var(--v2-dropdown-item-icon-size);
    text-align: center;
    font-weight: var(--v2-dropdown-item-danger-cue-font-weight);
  }

  .v2-base-dropdown-item__icon :deep(svg) {
    width: 100%;
    height: 100%;
  }

  .v2-base-dropdown-item__label {
    min-width: 0;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .v2-base-dropdown-item__suffix {
    color: var(--v2-dropdown-item-suffix-text);
    font-size: var(--v2-dropdown-item-suffix-size);
  }
}
</style>
