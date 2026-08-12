<template>
  <Teleport v-if="open && portalTarget" :to="portalTarget">
    <div
      ref="modalRoot"
      v-bind="$attrs"
      class="v2-base-modal"
      :style="modalLayerStyle"
      data-v2-portal="frontend-v2-portal"
      @pointerdown="handleBackdropPointerdown"
    >
      <section
        ref="panelElement"
        class="v2-base-modal__panel"
        role="dialog"
        aria-modal="true"
        :aria-label="hasTitle ? undefined : normalizedAriaLabel"
        :aria-labelledby="hasTitle ? titleId : undefined"
        :aria-describedby="hasDescription ? descriptionId : undefined"
        tabindex="-1"
      >
        <header v-if="hasTitle || hasDescription" class="v2-base-modal__header">
          <div class="v2-base-modal__heading">
            <h2 v-if="hasTitle" :id="titleId" class="v2-base-modal__title">
              {{ title }}
            </h2>
            <p v-if="hasDescription" :id="descriptionId" class="v2-base-modal__description">
              {{ description }}
            </p>
          </div>
          <button
            v-if="hasTitle"
            type="button"
            class="v2-base-modal__close"
            aria-label="关闭弹窗"
            @click="requestUserClose('close-button')"
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>

        <div class="v2-base-modal__body">
          <slot />
        </div>

        <footer v-if="$slots.footer" class="v2-base-modal__footer">
          <slot name="footer" />
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  ref,
  useId,
  watch,
} from 'vue'
import {
  activateOverlay,
  deactivateOverlay,
  getTopOverlay,
  refreshOverlayStack,
} from '../overlay/overlayStack.js'
import {
  createFocusTrap,
  focusDocumentFallback,
  focusInitialElement,
  isRestorableFocusTarget,
} from '../overlay/focusTrap.js'
import { acquireV2Portal, releaseV2Portal } from '../overlay/portal.js'
import { lockBodyScroll, unlockBodyScroll } from '../overlay/scrollLock.js'

defineOptions({ inheritAttrs: false })

const MODAL_STACK_STEP = 2

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  description: { type: String, default: '' },
  ariaLabel: { type: String, default: '' },
  closeOnEscape: { type: Boolean, default: true },
  closeOnBackdrop: { type: Boolean, default: false },
})

const emit = defineEmits(['update:open', 'close'])
const generatedId = useId().replace(/[^a-zA-Z0-9_-]/g, '')
const overlayId = `v2-modal-overlay-${generatedId}`
const titleId = `v2-modal-title-${generatedId}`
const descriptionId = `v2-modal-description-${generatedId}`
const portalTarget = ref(null)
const modalRoot = ref(null)
const panelElement = ref(null)
const isTop = ref(false)
const stackIndex = ref(0)
const modalCount = ref(0)
const normalizedAriaLabel = computed(() => props.ariaLabel.trim())
const hasTitle = computed(() => Boolean(props.title.trim()))
const hasDescription = computed(() => Boolean(props.description.trim()))
const modalLayerStyle = computed(() => ({
  '--v2-modal-layer-offset': String(stackIndex.value * MODAL_STACK_STEP),
}))

let openerElement = null
let focusFrame = null
let lifecycleToken = 0
let lifecycleActive = false
let portalOwned = false
let scrollOwned = false
let closePending = false

const focusTrap = createFocusTrap({
  container: () => panelElement.value,
  isActive: () => lifecycleActive && isTop.value,
})

function validateAccessibleName() {
  if (hasTitle.value || normalizedAriaLabel.value) return
  if (import.meta.env.DEV) {
    console.error('BaseModal requires either a non-empty title or ariaLabel.')
  }
}

function handleStackChange(state) {
  isTop.value = state.isTop
  stackIndex.value = Math.max(0, state.modalIndex)
  modalCount.value = state.modalCount
}

function canStackClose(reason) {
  return reason !== 'escape' || props.closeOnEscape
}

function requestUserClose(reason) {
  if (!props.open || !isTop.value || closePending) return
  if (reason === 'escape' && !props.closeOnEscape) return
  if (reason === 'backdrop' && !props.closeOnBackdrop) return

  closePending = true
  emit('update:open', false)
  emit('close', reason)
  nextTick(() => {
    if (props.open) closePending = false
  })
}

function handleStackClose(reason) {
  requestUserClose(reason)
}

function handleBackdropPointerdown(event) {
  if (event.target !== event.currentTarget) return
  requestUserClose('backdrop')
}

function scheduleInitialFocus(token) {
  if (focusFrame !== null) cancelAnimationFrame(focusFrame)
  focusFrame = requestAnimationFrame(() => {
    focusFrame = null
    if (token !== lifecycleToken || !props.open || !isTop.value) return
    focusTrap.focusInitial()
  })
}

function restoreFocus() {
  if (isRestorableFocusTarget(openerElement)) {
    openerElement.focus({ preventScroll: true })
    return
  }
  const nextTopPanel = getTopOverlay()?.element?.()?.querySelector?.('[role="dialog"]')
    ?? getTopOverlay()?.element?.()
  if (nextTopPanel) {
    focusInitialElement(nextTopPanel)
    return
  }
  focusDocumentFallback(modalRoot.value)
}

async function startOpenLifecycle() {
  const token = ++lifecycleToken
  closePending = false
  validateAccessibleName()
  openerElement = document.activeElement instanceof HTMLElement ? document.activeElement : null
  portalTarget.value = acquireV2Portal(overlayId)
  portalOwned = Boolean(portalTarget.value)
  if (!portalOwned) return
  lockBodyScroll(overlayId)
  scrollOwned = true

  await nextTick()
  if (token !== lifecycleToken || !props.open || !modalRoot.value) return

  lifecycleActive = true
  activateOverlay({
    id: overlayId,
    group: 'modal',
    element: () => modalRoot.value,
    canClose: canStackClose,
    requestClose: handleStackClose,
    onStackChange: handleStackChange,
  })
  refreshOverlayStack()
  focusTrap.activate()
  scheduleInitialFocus(token)
}

function stopOpenLifecycle({ restore = true, immediatePortalRelease = false } = {}) {
  const hadOpenLifecycle = lifecycleActive || portalOwned || scrollOwned
  if (!hadOpenLifecycle) return
  ++lifecycleToken
  closePending = false
  if (focusFrame !== null) {
    cancelAnimationFrame(focusFrame)
    focusFrame = null
  }
  focusTrap.deactivate()
  if (lifecycleActive) deactivateOverlay(overlayId)
  lifecycleActive = false
  isTop.value = false
  modalCount.value = 0
  if (scrollOwned) unlockBodyScroll(overlayId)
  scrollOwned = false

  const releasePortal = () => {
    if (portalOwned) releaseV2Portal(overlayId)
    portalOwned = false
    portalTarget.value = null
  }
  if (immediatePortalRelease) releasePortal()
  else nextTick(releasePortal)
  if (restore) nextTick(restoreFocus)
}

watch(
  () => props.open,
  (open) => {
    if (open) startOpenLifecycle()
    else stopOpenLifecycle()
  },
  { immediate: true, flush: 'post' },
)

watch(
  () => [props.title, props.ariaLabel],
  () => {
    if (props.open) validateAccessibleName()
  },
)

onBeforeUnmount(() => {
  stopOpenLifecycle({ restore: true, immediatePortalRelease: true })
})
</script>

<style scoped>
@layer v2-components {
  .v2-base-modal {
    position: fixed;
    inset: 0;
    z-index: calc(var(--v2-modal-overlay-z-index) + var(--v2-modal-layer-offset));
    display: grid;
    place-items: center;
    padding: var(--v2-space-4);
    background: var(--v2-modal-overlay);
  }

  .v2-base-modal__panel {
    position: relative;
    z-index: var(--v2-modal-z-index);
    width: min(680px, calc(100vw - 40px));
    max-height: calc(100vh - 48px);
    display: flex;
    flex-direction: column;
    color: var(--v2-text-primary);
    background: var(--v2-modal-surface);
    border: var(--v2-border-width) solid var(--v2-modal-border);
    border-radius: var(--v2-modal-radius);
    box-shadow: var(--v2-modal-shadow);
    outline: none;
  }

  .v2-base-modal__panel:focus-visible {
    box-shadow: var(--v2-modal-shadow), var(--v2-state-focus-ring);
  }

  .v2-base-modal__header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--v2-space-2);
    min-height: 56px;
    padding: 14px 20px;
    border-bottom: var(--v2-border-width) solid var(--v2-modal-border);
    background: var(--v2-modal-surface);
  }

  .v2-base-modal__heading {
    min-width: 0;
  }

  .v2-base-modal__title,
  .v2-base-modal__description {
    margin: 0;
  }

  .v2-base-modal__title {
    overflow-wrap: anywhere;
    font-size: 16px;
    font-weight: var(--v2-font-weight-semibold);
    color: var(--v2-color-text-heading);
    line-height: var(--v2-line-height-tight);
  }

  .v2-base-modal__description {
    margin-top: var(--v2-space-1);
    color: var(--v2-text-muted);
    font-size: var(--v2-font-size-caption);
    line-height: var(--v2-line-height-caption);
  }

  .v2-base-modal__close {
    width: var(--v2-control-height-compact);
    height: var(--v2-control-height-compact);
    display: grid;
    flex: 0 0 auto;
    place-items: center;
    padding: 0;
    color: var(--v2-text-muted);
    background: transparent;
    border: 0;
    border-radius: var(--v2-radius-sm);
    font-size: 18px;
    line-height: 1;
    cursor: pointer;
    transition:
      color var(--v2-motion-duration) var(--v2-motion-easing),
      background-color var(--v2-motion-duration) var(--v2-motion-easing);
  }

  .v2-base-modal__close:hover {
    color: var(--v2-text-primary);
    background: var(--v2-surface-hover);
  }

  .v2-base-modal__close:focus-visible {
    outline: none;
    box-shadow: var(--v2-state-focus-ring);
  }

  .v2-base-modal__body {
    min-height: 0;
    padding: 18px 20px;
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  .v2-base-modal__footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: var(--v2-space-2);
    min-height: 60px;
    padding: 12px 20px;
    border-top: var(--v2-border-width) solid var(--v2-modal-border);
    background: var(--v2-modal-surface);
  }

  @media (max-width: 480px) {
    .v2-base-modal__footer > :deep(*) {
      flex: 1 1 auto;
    }
  }
}
</style>
