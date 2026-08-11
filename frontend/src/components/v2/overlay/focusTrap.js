const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'button',
  'input',
  'select',
  'textarea',
  'iframe',
  '[contenteditable="true"]',
  '[tabindex]',
].join(',')

function isVisible(element) {
  if (element.hidden) return false
  const style = getComputedStyle(element)
  return style.display !== 'none'
    && style.visibility !== 'hidden'
    && element.getClientRects().length > 0
}

export function isFocusableElement(element) {
  if (!(element instanceof HTMLElement)) return false
  if (element.matches(':disabled') || element.getAttribute('aria-disabled') === 'true') return false
  if (element.inert || element.closest('[inert]')) return false
  if (element.getAttribute('tabindex') === '-1') return false
  return isVisible(element)
}

export function getFocusableElements(container) {
  if (!container) return []
  return [...container.querySelectorAll(FOCUSABLE_SELECTOR)].filter(isFocusableElement)
}

function isOwnedPortalTarget(target, container) {
  const menu = target.closest?.('.frontend-v2-portal [role="menu"]')
  if (!menu?.id) return false
  const trigger = document.querySelector(`[aria-controls="${CSS.escape(menu.id)}"]`)
  return Boolean(trigger && container.contains(trigger))
}

export function focusInitialElement(container) {
  if (!container) return null
  const autofocusTarget = container.querySelector('[autofocus]')
  const target = isFocusableElement(autofocusTarget)
    ? autofocusTarget
    : getFocusableElements(container)[0] ?? container
  target.focus({ preventScroll: true })
  return target
}

export function isRestorableFocusTarget(element) {
  return Boolean(element?.isConnected && isFocusableElement(element))
}

export function focusDocumentFallback(excludedContainer = null) {
  const candidates = [...document.body.querySelectorAll(FOCUSABLE_SELECTOR)]
    .filter((element) => !excludedContainer?.contains(element))
    .filter(isFocusableElement)
  const target = candidates[0] ?? null
  target?.focus({ preventScroll: true })
  return target
}

export function createFocusTrap({ container, isActive }) {
  let active = false

  function resolveContainer() {
    return typeof container === 'function' ? container() : container
  }

  function trapEnabled() {
    return active && (typeof isActive !== 'function' || isActive())
  }

  function handleKeydown(event) {
    if (event.key !== 'Tab' || event.defaultPrevented || !trapEnabled()) return
    const root = resolveContainer()
    if (!root) return
    const focusable = getFocusableElements(root)
    if (focusable.length === 0) {
      event.preventDefault()
      root.focus({ preventScroll: true })
      return
    }

    const activeElement = document.activeElement
    const currentIndex = focusable.indexOf(activeElement)
    if (event.shiftKey && currentIndex <= 0) {
      event.preventDefault()
      focusable.at(-1).focus({ preventScroll: true })
    } else if (!event.shiftKey && (currentIndex === -1 || currentIndex === focusable.length - 1)) {
      event.preventDefault()
      focusable[0].focus({ preventScroll: true })
    }
  }

  function handleFocusin(event) {
    if (!trapEnabled()) return
    const root = resolveContainer()
    if (!root || root.contains(event.target) || isOwnedPortalTarget(event.target, root)) return
    focusInitialElement(root)
  }

  function activate() {
    if (active || typeof document === 'undefined') return
    active = true
    document.addEventListener('keydown', handleKeydown, true)
    document.addEventListener('focusin', handleFocusin, true)
  }

  function deactivate() {
    if (!active || typeof document === 'undefined') return
    active = false
    document.removeEventListener('keydown', handleKeydown, true)
    document.removeEventListener('focusin', handleFocusin, true)
  }

  return { activate, deactivate, focusInitial: () => focusInitialElement(resolveContainer()) }
}
