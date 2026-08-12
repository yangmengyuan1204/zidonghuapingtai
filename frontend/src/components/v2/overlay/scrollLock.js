const owners = new Set()

let originalOverflow = null
let originalOverflowPriority = ''

export function lockBodyScroll(ownerId) {
  if (!ownerId || typeof document === 'undefined') return
  if (owners.has(ownerId)) return

  if (owners.size === 0) {
    originalOverflow = document.body.style.getPropertyValue('overflow')
    originalOverflowPriority = document.body.style.getPropertyPriority('overflow')
    document.body.style.setProperty('overflow', 'hidden')
  }
  owners.add(ownerId)
}

export function unlockBodyScroll(ownerId) {
  if (!ownerId || typeof document === 'undefined' || !owners.delete(ownerId)) return
  if (owners.size > 0) return

  if (originalOverflow) {
    document.body.style.setProperty('overflow', originalOverflow, originalOverflowPriority)
  } else {
    document.body.style.removeProperty('overflow')
  }
  originalOverflow = null
  originalOverflowPriority = ''
}

export function getBodyScrollLockCount() {
  return owners.size
}

/** Clear orphaned body scroll locks (e.g. modal unmounted mid-lifecycle). */
export function forceUnlockAllBodyScroll() {
  if (typeof document === 'undefined') return
  owners.clear()
  if (originalOverflow) {
    document.body.style.setProperty('overflow', originalOverflow, originalOverflowPriority)
  } else {
    document.body.style.removeProperty('overflow')
  }
  originalOverflow = null
  originalOverflowPriority = ''
}
