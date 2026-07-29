<template>
  <component
    :is="as"
    v-bind="$attrs"
    class="v2-base-card"
    :class="[
      `v2-base-card--${variant}`,
      `v2-base-card--padding-${padding}`,
      { 'v2-base-card--interactive': interactive },
    ]"
    :type="nativeButtonType"
    :role="interactiveRole"
    :tabindex="interactiveTabindex"
    @click="handleClick"
    @keydown.enter="handleKeyActivate"
    @keydown.space="handleKeyActivate"
  >
    <div v-if="$slots.header" class="v2-base-card__header">
      <slot name="header" />
    </div>
    <div class="v2-base-card__body">
      <slot />
    </div>
    <div v-if="$slots.footer" class="v2-base-card__footer">
      <slot name="footer" />
    </div>
  </component>
</template>

<script setup>
import { computed, useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  as: { type: String, default: 'section' },
  variant: {
    type: String,
    default: 'surface',
    validator: (value) => ['surface', 'soft'].includes(value),
  },
  padding: {
    type: String,
    default: 'default',
    validator: (value) => ['none', 'compact', 'default', 'spacious'].includes(value),
  },
  interactive: { type: Boolean, default: false },
})

const emit = defineEmits(['activate'])
const attrs = useAttrs()
const nativeInteractiveTags = new Set(['button', 'a'])
const isNativeInteractive = computed(() => nativeInteractiveTags.has(props.as))
const interactiveRole = computed(() =>
  props.interactive && !isNativeInteractive.value ? 'button' : attrs.role
)
const interactiveTabindex = computed(() =>
  props.interactive && !isNativeInteractive.value ? 0 : attrs.tabindex
)
const nativeButtonType = computed(() =>
  props.as === 'button' ? (attrs.type || 'button') : undefined
)

function handleClick(event) {
  if (!props.interactive || isNestedInteractiveEvent(event)) return
  emit('activate', event)
}

function handleKeyActivate(event) {
  if (
    !props.interactive
    || isNativeInteractive.value
    || event.repeat
    || event.target !== event.currentTarget
  ) return
  event.preventDefault()
  emit('activate', event)
}

function isNestedInteractiveEvent(event) {
  if (event.target === event.currentTarget || typeof event.target.closest !== 'function') return false
  const nested = event.target.closest('button, a, input, select, textarea, [role="button"], [tabindex]')
  return Boolean(nested && nested !== event.currentTarget)
}
</script>

<style scoped>
@layer v2-components {
  .v2-base-card {
    display: grid;
    gap: var(--v2-card-section-gap);
    min-width: 0;
    margin: 0;
    color: var(--v2-text-primary);
    background: var(--v2-card-surface);
    border: var(--v2-border-width) solid var(--v2-card-border);
    border-radius: var(--v2-card-radius);
    text-align: left;
    transition:
      background-color var(--v2-motion-duration) var(--v2-motion-easing),
      border-color var(--v2-motion-duration) var(--v2-motion-easing),
      opacity var(--v2-motion-duration) var(--v2-motion-easing);
  }

  .v2-base-card--soft {
    background: var(--v2-card-surface-soft);
  }

  .v2-base-card--padding-none {
    padding: 0;
  }

  .v2-base-card--padding-compact {
    padding: var(--v2-card-padding-compact);
  }

  .v2-base-card--padding-default {
    padding: var(--v2-card-padding-default);
  }

  .v2-base-card--padding-spacious {
    padding: var(--v2-card-padding-spacious);
  }

  .v2-base-card--interactive {
    cursor: pointer;
  }

  .v2-base-card--interactive:hover {
    background: var(--v2-card-surface-hover);
    border-color: var(--v2-card-border-hover);
  }

  .v2-base-card--interactive:active {
    background: var(--v2-card-surface-pressed);
  }

  .v2-base-card--interactive:focus-visible {
    outline: none;
    box-shadow: var(--v2-card-focus-ring);
  }

  .v2-base-card__header,
  .v2-base-card__footer,
  .v2-base-card__body {
    min-width: 0;
  }
}
</style>
