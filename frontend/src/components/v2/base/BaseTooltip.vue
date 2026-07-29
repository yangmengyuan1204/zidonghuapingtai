<template>
  <span
    v-bind="$attrs"
    class="v2-base-tooltip"
    @mouseenter="handleMouseenter"
    @mouseleave="handleMouseleave"
    @focusin="handleFocusin"
    @focusout="handleFocusout"
    @keydown.esc="hideTooltip"
  >
    <TooltipTrigger :described-by="describedBy">
      <slot />
    </TooltipTrigger>
    <span
      v-if="visible"
      :id="tooltipId"
      class="v2-base-tooltip__content"
      :class="`v2-base-tooltip__content--${placement}`"
      role="tooltip"
    >
      {{ content }}
      <span class="v2-base-tooltip__arrow" aria-hidden="true"></span>
    </span>
  </span>
</template>

<script setup>
import {
  Comment,
  Fragment,
  cloneVNode,
  computed,
  defineComponent,
  h,
  onBeforeUnmount,
  ref,
  useId,
  watch,
} from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  content: { type: String, default: '' },
  placement: {
    type: String,
    default: 'top',
    validator: (value) => ['top', 'right', 'bottom', 'left'].includes(value),
  },
  disabled: { type: Boolean, default: false },
  delay: { type: Number, default: 120 },
  id: { type: String, default: '' },
})

const generatedId = useId()
const visible = ref(false)
const hovered = ref(false)
const focused = ref(false)
let showTimer = null

const tooltipId = computed(() => props.id || `v2-tooltip-${generatedId}`)
const canShow = computed(() => !props.disabled && props.content.trim().length > 0)
const describedBy = computed(() => visible.value ? tooltipId.value : undefined)

const TooltipTrigger = defineComponent({
  name: 'V2TooltipTrigger',
  inheritAttrs: false,
  props: {
    describedBy: { type: String, default: undefined },
  },
  setup(triggerProps, { slots }) {
    return () => {
      const nodes = flattenTriggerNodes(slots.default?.() ?? [])
      const first = nodes[0]
      if (!first) return null

      const existing = first.props?.['aria-describedby']
      const merged = [existing, triggerProps.describedBy].filter(Boolean).join(' ') || undefined
      if (nodes.length === 1) {
        return cloneVNode(first, { 'aria-describedby': merged }, true)
      }
      return h('span', { 'aria-describedby': merged }, nodes)
    }
  },
})

function flattenTriggerNodes(nodes) {
  return nodes.flatMap((node) => {
    if (node.type === Comment) return []
    if (node.type === Fragment && Array.isArray(node.children)) {
      return flattenTriggerNodes(node.children)
    }
    return [node]
  })
}

function clearShowTimer() {
  if (showTimer !== null) {
    clearTimeout(showTimer)
    showTimer = null
  }
}

function scheduleShow() {
  clearShowTimer()
  if (!canShow.value) return
  const delay = Number.isFinite(props.delay) ? Math.max(0, props.delay) : 0
  showTimer = window.setTimeout(() => {
    showTimer = null
    if (canShow.value && (hovered.value || focused.value)) visible.value = true
  }, delay)
}

function hideTooltip() {
  clearShowTimer()
  visible.value = false
}

function handleMouseenter() {
  hovered.value = true
  scheduleShow()
}

function handleMouseleave() {
  hovered.value = false
  if (!focused.value) hideTooltip()
}

function handleFocusin() {
  focused.value = true
  scheduleShow()
}

function handleFocusout(event) {
  if (event.currentTarget.contains(event.relatedTarget)) return
  focused.value = false
  if (!hovered.value) hideTooltip()
}

watch(canShow, (allowed) => {
  if (!allowed) hideTooltip()
})

onBeforeUnmount(clearShowTimer)
</script>

<style scoped>
@layer v2-components {
  .v2-base-tooltip {
    position: relative;
    display: inline-flex;
    max-width: 100%;
  }

  .v2-base-tooltip__content {
    position: absolute;
    z-index: var(--v2-tooltip-z-index);
    width: max-content;
    max-width: var(--v2-tooltip-max-width);
    padding:
      var(--v2-tooltip-padding-block)
      var(--v2-tooltip-padding-inline);
    color: var(--v2-tooltip-text);
    background: var(--v2-tooltip-surface);
    border-radius: var(--v2-tooltip-radius);
    box-shadow: var(--v2-tooltip-shadow);
    font-size: var(--v2-tooltip-font-size);
    line-height: var(--v2-tooltip-line-height);
    pointer-events: none;
  }

  .v2-base-tooltip__content--top {
    left: 50%;
    bottom: calc(100% + var(--v2-tooltip-offset));
    transform: translateX(-50%);
  }

  .v2-base-tooltip__content--right {
    top: 50%;
    left: calc(100% + var(--v2-tooltip-offset));
    transform: translateY(-50%);
  }

  .v2-base-tooltip__content--bottom {
    top: calc(100% + var(--v2-tooltip-offset));
    left: 50%;
    transform: translateX(-50%);
  }

  .v2-base-tooltip__content--left {
    top: 50%;
    right: calc(100% + var(--v2-tooltip-offset));
    transform: translateY(-50%);
  }

  .v2-base-tooltip__arrow {
    position: absolute;
    width: var(--v2-tooltip-arrow-size);
    height: var(--v2-tooltip-arrow-size);
    background: var(--v2-tooltip-surface);
    transform: rotate(45deg);
  }

  .v2-base-tooltip__content--top .v2-base-tooltip__arrow {
    bottom: calc(var(--v2-tooltip-arrow-size) / -2);
    left: calc(50% - var(--v2-tooltip-arrow-size) / 2);
  }

  .v2-base-tooltip__content--right .v2-base-tooltip__arrow {
    top: calc(50% - var(--v2-tooltip-arrow-size) / 2);
    left: calc(var(--v2-tooltip-arrow-size) / -2);
  }

  .v2-base-tooltip__content--bottom .v2-base-tooltip__arrow {
    top: calc(var(--v2-tooltip-arrow-size) / -2);
    left: calc(50% - var(--v2-tooltip-arrow-size) / 2);
  }

  .v2-base-tooltip__content--left .v2-base-tooltip__arrow {
    top: calc(50% - var(--v2-tooltip-arrow-size) / 2);
    right: calc(var(--v2-tooltip-arrow-size) / -2);
  }
}
</style>
