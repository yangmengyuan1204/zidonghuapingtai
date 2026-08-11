<template>
  <span ref="rootElement" v-bind="$attrs" class="v2-base-dropdown">
    <DropdownTrigger
      :menu-id="menuId"
      :open="renderedOpen"
      :disabled="disabled"
      :aria-label="ariaLabel"
      :on-trigger-click="handleTriggerClick"
      :on-trigger-keydown="handleTriggerKeydown"
    >
      <slot name="trigger" />
    </DropdownTrigger>

    <Teleport v-if="renderedOpen && portalTarget" :to="portalTarget">
      <div
        :id="menuId"
        ref="menuElement"
        class="v2-base-dropdown__menu"
        :class="`v2-base-dropdown__menu--${placement}`"
        :style="menuStyle"
        role="menu"
        aria-orientation="vertical"
        :aria-label="menuLabel || ariaLabel || undefined"
        data-v2-portal="frontend-v2-portal"
        @keydown="handleMenuKeydown"
      >
        <slot />
      </div>
    </Teleport>
  </span>
</template>

<script setup>
import {
  Comment,
  Fragment,
  cloneVNode,
  computed,
  defineComponent,
  nextTick,
  onBeforeUnmount,
  provide,
  ref,
  useId,
  watch,
} from 'vue'
import { activateOverlay, deactivateOverlay } from '../overlay/overlayStack.js'
import { acquireV2Portal, releaseV2Portal } from '../overlay/portal.js'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  open: { type: Boolean, default: false },
  placement: {
    type: String,
    default: 'bottom-start',
    validator: (value) => [
      'bottom-start',
      'bottom-end',
      'top-start',
      'top-end',
    ].includes(value),
  },
  disabled: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '' },
  menuLabel: { type: String, default: '' },
  closeOnSelect: { type: Boolean, default: true },
  closeOnOutside: { type: Boolean, default: true },
  matchTriggerWidth: { type: Boolean, default: false },
})

const emit = defineEmits(['update:open', 'select'])
const generatedId = useId().replace(/[^a-zA-Z0-9_-]/g, '')
const overlayId = `v2-dropdown-overlay-${generatedId}`
const menuId = `v2-dropdown-menu-${generatedId}`
const rootElement = ref(null)
const menuElement = ref(null)
const portalTarget = ref(null)
const renderedOpen = computed(() => props.open && !props.disabled)
const menuStyle = ref({})

let triggerElement = null
let lifecycleActive = false
let listenersAttached = false
let positionFrame = null
let pendingFocus = null
let pendingRestoreFocus = false

const DropdownTrigger = defineComponent({
  name: 'V2DropdownTrigger',
  inheritAttrs: false,
  props: {
    menuId: { type: String, required: true },
    open: { type: Boolean, required: true },
    disabled: { type: Boolean, required: true },
    ariaLabel: { type: String, default: '' },
    onTriggerClick: { type: Function, required: true },
    onTriggerKeydown: { type: Function, required: true },
  },
  setup(triggerProps, { slots }) {
    return () => {
      const trigger = flattenTriggerNodes(slots.default?.() ?? [])[0]
      if (!trigger) return null

      const triggerDisabled = Boolean(trigger.props?.disabled || triggerProps.disabled)
      return cloneVNode(trigger, {
        'aria-haspopup': 'menu',
        'aria-expanded': String(triggerProps.open),
        'aria-controls': triggerProps.menuId,
        'aria-label': triggerProps.ariaLabel || trigger.props?.['aria-label'],
        'aria-disabled': triggerDisabled ? 'true' : trigger.props?.['aria-disabled'],
        disabled: triggerDisabled,
        onClick: triggerProps.onTriggerClick,
        onKeydown: triggerProps.onTriggerKeydown,
      }, true)
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

function resolveTriggerElement(event) {
  if (event?.currentTarget instanceof HTMLElement) triggerElement = event.currentTarget
  if (!triggerElement?.isConnected) {
    triggerElement = rootElement.value?.querySelector(`[aria-controls="${menuId}"]`) ?? null
  }
  return triggerElement
}

function enabledItems() {
  if (!menuElement.value) return []
  return [...menuElement.value.querySelectorAll('[role="menuitem"]')]
    .filter((item) => item.getAttribute('aria-disabled') !== 'true' && !item.disabled)
}

function focusMenuItem(position) {
  const items = enabledItems()
  if (items.length === 0) return
  items[position === 'last' ? items.length - 1 : 0].focus()
}

function readPixelToken(name, fallback) {
  const source = portalTarget.value || rootElement.value
  if (!source) return fallback
  const value = Number.parseFloat(getComputedStyle(source).getPropertyValue(name))
  return Number.isFinite(value) ? value : fallback
}

function updatePosition() {
  positionFrame = null
  const trigger = resolveTriggerElement()
  const menu = menuElement.value
  if (!renderedOpen.value || !trigger || !menu) return

  const viewportGap = readPixelToken('--v2-dropdown-viewport-gap', 12)
  const offset = readPixelToken('--v2-dropdown-position-offset', 8)
  const triggerRect = trigger.getBoundingClientRect()
  const maxWidth = Math.max(0, window.innerWidth - viewportGap * 2)

  menu.style.width = props.matchTriggerWidth
    ? `${Math.min(triggerRect.width, maxWidth)}px`
    : ''
  menu.style.maxWidth = `${maxWidth}px`

  const menuRect = menu.getBoundingClientRect()
  const preferredLeft = props.placement.endsWith('end')
    ? triggerRect.right - menuRect.width
    : triggerRect.left
  const left = Math.min(
    Math.max(preferredLeft, viewportGap),
    Math.max(viewportGap, window.innerWidth - menuRect.width - viewportGap),
  )
  const top = props.placement.startsWith('top')
    ? triggerRect.top - menuRect.height - offset
    : triggerRect.bottom + offset

  menuStyle.value = {
    left: `${Math.round(left)}px`,
    top: `${Math.round(top)}px`,
    width: props.matchTriggerWidth ? `${Math.min(triggerRect.width, maxWidth)}px` : undefined,
    maxWidth: `${maxWidth}px`,
  }
}

function schedulePosition() {
  if (positionFrame !== null) cancelAnimationFrame(positionFrame)
  positionFrame = requestAnimationFrame(updatePosition)
}

function handleDocumentPointerdown(event) {
  if (!props.closeOnOutside || !renderedOpen.value) return
  if (rootElement.value?.contains(event.target) || menuElement.value?.contains(event.target)) return
  closeDropdown({ emitUpdate: true, restoreFocus: false })
}

function addGlobalListeners() {
  if (listenersAttached) return
  document.addEventListener('pointerdown', handleDocumentPointerdown, true)
  window.addEventListener('resize', schedulePosition)
  window.addEventListener('scroll', schedulePosition, true)
  listenersAttached = true
}

function removeGlobalListeners() {
  if (!listenersAttached) return
  document.removeEventListener('pointerdown', handleDocumentPointerdown, true)
  window.removeEventListener('resize', schedulePosition)
  window.removeEventListener('scroll', schedulePosition, true)
  listenersAttached = false
}

function stopOpenLifecycle() {
  if (positionFrame !== null) {
    cancelAnimationFrame(positionFrame)
    positionFrame = null
  }
  removeGlobalListeners()
  deactivateOverlay(overlayId)
  lifecycleActive = false
  nextTick(() => {
    if (renderedOpen.value) return
    releaseV2Portal(overlayId)
    portalTarget.value = null
  })
}

function closeDropdown({ emitUpdate, restoreFocus }) {
  pendingFocus = null
  pendingRestoreFocus = restoreFocus
  if (emitUpdate) emit('update:open', false)
  nextTick(() => {
    if (renderedOpen.value) pendingRestoreFocus = false
  })
}

function handleStackClose(_reason, restoreFocus) {
  closeDropdown({ emitUpdate: true, restoreFocus })
}

function startOpenLifecycle() {
  if (props.disabled) return
  if (!portalTarget.value) portalTarget.value = acquireV2Portal(overlayId)
  if (!portalTarget.value?.classList.contains('frontend-v2-portal')) return

  if (!lifecycleActive) {
    lifecycleActive = true
    activateOverlay({
      id: overlayId,
      group: 'dropdown',
      requestClose: handleStackClose,
    })
    addGlobalListeners()
  }

  nextTick(() => {
    schedulePosition()
    if (pendingFocus) {
      focusMenuItem(pendingFocus)
      pendingFocus = null
    }
  })
}

function openDropdown({ emitUpdate, focus }) {
  if (props.disabled) return
  pendingFocus = focus
  if (emitUpdate) emit('update:open', true)
  nextTick(() => {
    if (!renderedOpen.value) pendingFocus = null
  })
}

function handleTriggerClick(event) {
  resolveTriggerElement(event)
  if (props.disabled) return
  if (renderedOpen.value) closeDropdown({ emitUpdate: true, restoreFocus: false })
  else openDropdown({ emitUpdate: true, focus: null })
}

function handleTriggerKeydown(event) {
  resolveTriggerElement(event)
  if (props.disabled) return

  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (renderedOpen.value) focusMenuItem(event.key === 'ArrowUp' ? 'last' : 'first')
    else openDropdown({ emitUpdate: true, focus: event.key === 'ArrowUp' ? 'last' : 'first' })
    return
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (renderedOpen.value) closeDropdown({ emitUpdate: true, restoreFocus: false })
    else openDropdown({ emitUpdate: true, focus: 'first' })
    return
  }
  if (event.key === 'Escape' && renderedOpen.value) {
    event.preventDefault()
    closeDropdown({ emitUpdate: true, restoreFocus: true })
  } else if (event.key === 'Tab' && renderedOpen.value) {
    closeDropdown({ emitUpdate: true, restoreFocus: false })
  }
}

function handleMenuKeydown(event) {
  const items = enabledItems()
  const currentIndex = items.indexOf(document.activeElement)

  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    closeDropdown({ emitUpdate: true, restoreFocus: true })
    return
  }
  if (event.key === 'Tab') {
    closeDropdown({ emitUpdate: true, restoreFocus: false })
    return
  }
  if (event.key === 'Enter' || event.key === ' ') {
    if (currentIndex === -1) return
    event.preventDefault()
    items[currentIndex].click()
    return
  }
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) || items.length === 0) return

  event.preventDefault()
  const nextIndex = event.key === 'Home'
    ? 0
    : event.key === 'End'
      ? items.length - 1
      : event.key === 'ArrowDown'
        ? (currentIndex + 1 + items.length) % items.length
        : (currentIndex <= 0 ? items.length - 1 : currentIndex - 1)
  items[nextIndex].focus()
}

function selectItem(value, event) {
  emit('select', value, event)
  if (props.closeOnSelect) closeDropdown({ emitUpdate: true, restoreFocus: true })
}

provide('v2-base-dropdown', { selectItem })

watch(
  renderedOpen,
  (open) => {
    if (open) {
      startOpenLifecycle()
    } else if (lifecycleActive || portalTarget.value) {
      const restoreFocus = pendingRestoreFocus
      pendingRestoreFocus = false
      pendingFocus = null
      stopOpenLifecycle()
      if (restoreFocus) nextTick(() => resolveTriggerElement()?.focus())
    }
  },
  { immediate: true, flush: 'post' },
)

watch(
  () => props.disabled,
  (disabled) => {
    if (disabled && props.open) emit('update:open', false)
  },
)

watch(
  () => [props.placement, props.matchTriggerWidth],
  () => {
    if (renderedOpen.value) nextTick(schedulePosition)
  },
)

onBeforeUnmount(() => {
  if (positionFrame !== null) cancelAnimationFrame(positionFrame)
  removeGlobalListeners()
  deactivateOverlay(overlayId)
  releaseV2Portal(overlayId)
})
</script>

<style scoped>
@layer v2-components {
  .v2-base-dropdown {
    display: inline-flex;
    max-width: 100%;
  }

  .v2-base-dropdown__menu {
    position: fixed;
    z-index: var(--v2-dropdown-z-index);
    width: var(--v2-dropdown-width);
    max-height: var(--v2-dropdown-max-height);
    display: grid;
    gap: var(--v2-dropdown-gap);
    padding: var(--v2-dropdown-padding);
    overflow-x: hidden;
    overflow-y: auto;
    color: var(--v2-dropdown-text);
    background: var(--v2-dropdown-surface);
    border: var(--v2-border-width) solid var(--v2-dropdown-border);
    border-radius: var(--v2-dropdown-radius);
    box-shadow: var(--v2-dropdown-shadow);
  }
}
</style>
