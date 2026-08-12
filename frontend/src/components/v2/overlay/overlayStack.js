const overlayStack = []
const backgroundInertState = new Map()
const lowerModalInertState = new Map()

let listening = false

function saveAndSetInert(state, element) {
  if (!element || state.has(element)) return
  state.set(element, {
    hadAttribute: element.hasAttribute('inert'),
    attributeValue: element.getAttribute('inert'),
    propertyValue: element.inert,
  })
  element.inert = true
}

function restoreInert(state, element) {
  const original = state.get(element)
  if (!original) return
  if (original.hadAttribute) element.setAttribute('inert', original.attributeValue ?? '')
  else element.removeAttribute('inert')
  element.inert = original.propertyValue
  state.delete(element)
}

function syncManagedInert(state, desiredElements) {
  for (const element of [...state.keys()]) {
    if (!desiredElements.has(element)) restoreInert(state, element)
  }
  for (const element of desiredElements) saveAndSetInert(state, element)
}

function modalEntries() {
  return overlayStack.filter(({ group }) => group === 'modal')
}

function syncModalInteractionBlocking() {
  if (typeof document === 'undefined') return
  const modals = modalEntries()
  const background = new Set()
  const lowerModals = new Set()

  if (modals.length > 0) {
    for (const child of document.body.children) {
      if (!child.classList.contains('frontend-v2-portal')) background.add(child)
    }
    for (const entry of modals.slice(0, -1)) {
      const element = entry.element?.()
      if (element) lowerModals.add(element)
    }
  }

  syncManagedInert(backgroundInertState, background)
  syncManagedInert(lowerModalInertState, lowerModals)
}

function notifyStackChange() {
  const topOverlay = overlayStack.at(-1) ?? null
  const modals = modalEntries()
  for (const [index, entry] of overlayStack.entries()) {
    entry.onStackChange?.({
      index,
      isTop: entry === topOverlay,
      modalIndex: entry.group === 'modal' ? modals.indexOf(entry) : -1,
      modalCount: modals.length,
    })
  }
  syncModalInteractionBlocking()
}

function handleDocumentKeydown(event) {
  if (event.key !== 'Escape' || event.defaultPrevented) return
  const topOverlay = overlayStack.at(-1)
  if (!topOverlay || topOverlay.canClose?.('escape') === false) return

  event.preventDefault()
  event.stopPropagation()
  topOverlay.requestClose('escape', true)
}

function syncKeydownListener() {
  if (typeof document === 'undefined') return
  if (overlayStack.length > 0 && !listening) {
    document.addEventListener('keydown', handleDocumentKeydown, true)
    listening = true
  } else if (overlayStack.length === 0 && listening) {
    document.removeEventListener('keydown', handleDocumentKeydown, true)
    listening = false
  }
}

export function activateOverlay(entry) {
  if (entry.group === 'dropdown') {
    for (const activeEntry of [...overlayStack]) {
      if (activeEntry.id !== entry.id && activeEntry.group === 'dropdown') {
        activeEntry.requestClose('mutual', false)
      }
    }
  }

  const existingIndex = overlayStack.findIndex(({ id }) => id === entry.id)
  if (existingIndex !== -1) overlayStack.splice(existingIndex, 1)
  overlayStack.push(entry)
  syncKeydownListener()
  notifyStackChange()
  return overlayStack.length
}

export function deactivateOverlay(id) {
  const index = overlayStack.findIndex((entry) => entry.id === id)
  if (index !== -1) overlayStack.splice(index, 1)
  syncKeydownListener()
  notifyStackChange()
}

export function refreshOverlayStack() {
  notifyStackChange()
}

export function getTopOverlay() {
  return overlayStack.at(-1) ?? null
}

export function getOverlayCount(group = '') {
  return group ? overlayStack.filter((entry) => entry.group === group).length : overlayStack.length
}

/**
 * Drop all overlay entries and restore body inert state.
 * Used when DOM modals are gone but stack/inert leaked (blocks sidebar clicks).
 */
export function hardResetOverlayStack() {
  overlayStack.length = 0
  syncKeydownListener()
  notifyStackChange()
}
