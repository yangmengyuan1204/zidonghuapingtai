<template>
  <button
    v-bind="$attrs"
    class="v2-base-chip"
    :class="{ 'v2-base-chip--selected': selected }"
    type="button"
    :aria-pressed="selected"
    :disabled="disabled"
    @click="handleSelect"
  >
    <span v-if="$slots.icon" class="v2-base-chip__icon" aria-hidden="true">
      <slot name="icon" />
    </span>
    <span class="v2-base-chip__label"><slot /></span>
    <span
      v-if="count !== undefined && count !== null"
      class="v2-base-chip__count"
    >
      {{ count }}
    </span>
  </button>
</template>

<script setup>
defineOptions({ inheritAttrs: false })

const props = defineProps({
  selected: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  count: { type: [String, Number], default: undefined },
})

const emit = defineEmits(['select'])

function handleSelect(event) {
  if (props.disabled) return
  emit('select', event)
}
</script>

<style scoped>
@layer v2-components {
  .v2-base-chip {
    min-height: var(--v2-chip-height);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--v2-chip-gap);
    padding: 0 var(--v2-chip-padding);
    color: var(--v2-chip-text);
    background: var(--v2-chip-surface);
    border: var(--v2-border-width) solid var(--v2-chip-border);
    border-radius: var(--v2-chip-radius);
    font-size: var(--v2-chip-font-size);
    font-weight: var(--v2-chip-font-weight);
    line-height: var(--v2-line-height-tight);
    white-space: nowrap;
    cursor: pointer;
    transition:
      color var(--v2-motion-duration) var(--v2-motion-easing),
      background-color var(--v2-motion-duration) var(--v2-motion-easing),
      border-color var(--v2-motion-duration) var(--v2-motion-easing),
      opacity var(--v2-motion-duration) var(--v2-motion-easing);
  }

  .v2-base-chip:hover:not(:disabled) {
    background: var(--v2-chip-surface-hover);
    border-color: var(--v2-chip-border-hover);
  }

  .v2-base-chip:active:not(:disabled) {
    background: var(--v2-chip-surface-pressed);
  }

  .v2-base-chip:focus-visible {
    outline: none;
    box-shadow: var(--v2-chip-focus-ring);
  }

  .v2-base-chip:disabled {
    cursor: not-allowed;
    opacity: var(--v2-chip-disabled-opacity);
  }

  .v2-base-chip--selected {
    color: var(--v2-chip-text-selected);
    background: var(--v2-chip-surface-selected);
    border-color: var(--v2-chip-border-selected);
  }

  .v2-base-chip__icon {
    width: var(--v2-icon-size-xs);
    height: var(--v2-icon-size-xs);
    display: inline-grid;
    place-items: center;
  }

  .v2-base-chip__icon :deep(svg) {
    width: 100%;
    height: 100%;
  }

  .v2-base-chip__count {
    min-width: var(--v2-icon-size-sm);
    min-height: var(--v2-icon-size-sm);
    display: inline-grid;
    place-items: center;
    padding: 0 var(--v2-space-micro);
    color: var(--v2-chip-count-text);
    background: var(--v2-chip-count-surface);
    border-radius: var(--v2-radius-round);
    font-size: var(--v2-font-size-tiny);
  }

  .v2-base-chip--selected .v2-base-chip__count {
    color: var(--v2-chip-count-text-selected);
    background: var(--v2-chip-count-surface-selected);
  }
}
</style>
