const PORTAL_CLASS = 'frontend-v2-portal'
const PORTAL_SELECTOR = `.${PORTAL_CLASS}`
const owners = new Set()

let managedPortal = null

function resolvePortal() {
  if (typeof document === 'undefined') return null

  const portals = [...document.querySelectorAll(PORTAL_SELECTOR)]
  const ownedPortals = portals.filter((portal) => portal.dataset.v2PortalManaged === 'true')
  managedPortal = managedPortal?.isConnected && managedPortal.dataset.v2PortalManaged === 'true'
    ? managedPortal
    : ownedPortals[0] ?? null

  if (!managedPortal) {
    managedPortal = document.createElement('div')
    managedPortal.className = PORTAL_CLASS
    managedPortal.dataset.v2PortalManaged = 'true'
    document.body.appendChild(managedPortal)
  }

  for (const portal of portals) {
    if (portal === managedPortal) continue
    if (portal.dataset.v2PortalManaged === 'true') {
      while (portal.firstChild) managedPortal.appendChild(portal.firstChild)
      portal.remove()
    } else {
      portal.classList.remove(PORTAL_CLASS)
    }
  }

  return managedPortal
}

export function acquireV2Portal(ownerId) {
  if (ownerId) owners.add(ownerId)
  return resolvePortal()
}

export function releaseV2Portal(ownerId) {
  if (ownerId) owners.delete(ownerId)
  if (owners.size > 0 || !managedPortal) return

  if (managedPortal.dataset.v2PortalManaged === 'true') {
    managedPortal.replaceChildren()
    managedPortal.remove()
  }
  managedPortal = null
}

export function getV2PortalCount() {
  if (typeof document === 'undefined') return 0
  return document.querySelectorAll(PORTAL_SELECTOR).length
}

export function getV2PortalOwnerCount() {
  return owners.size
}

/** Drop portal owners and remove managed portal host if present. */
export function forceReleaseAllV2Portals() {
  owners.clear()
  if (!managedPortal) return
  if (managedPortal.dataset.v2PortalManaged === 'true') {
    managedPortal.replaceChildren()
    managedPortal.remove()
  }
  managedPortal = null
}
