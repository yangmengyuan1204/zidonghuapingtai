import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const repoDir = resolve(frontendDir, '..')
const baseDir = join(frontendDir, 'src', 'components', 'v2', 'base')
const overlayDir = join(frontendDir, 'src', 'components', 'v2', 'overlay')
const paths = {
  modal: join(baseDir, 'BaseModal.vue'),
  focusTrap: join(overlayDir, 'focusTrap.js'),
  scrollLock: join(overlayDir, 'scrollLock.js'),
  stack: join(overlayDir, 'overlayStack.js'),
  portal: join(overlayDir, 'portal.js'),
  index: join(baseDir, 'index.js'),
  tokens: join(frontendDir, 'src', 'styles', 'v2', 'tokens.component.css'),
  lab: join(frontendDir, 'src', 'dev', 'V2BaseComponentsLab.vue'),
  dropdown: join(baseDir, 'BaseDropdown.vue'),
}
const failures = []

function fail(message) {
  failures.push(message)
}

function read(path) {
  return readFileSync(path, 'utf8')
}

function requirePattern(source, pattern, message) {
  if (!pattern.test(source)) fail(message)
}

function walkFiles(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? walkFiles(path) : [path]
  })
}

export function validateModalSource(source) {
  const issues = []
  const add = (message) => issues.push(message)
  const classes = [...source.matchAll(/(?<!:)class=["']([^"']+)["']/g)]
    .flatMap(([, value]) => value.split(/\s+/))
    .filter(Boolean)

  if (/<dialog\b/i.test(source)) add('native dialog is forbidden')
  if (/\bv-html\b/.test(source)) add('v-html is forbidden')
  if (/(?:vue-router|pinia|axios|stores\/|api\/|services\/|\bfetch\s*\(|XMLHttpRequest|localStorage|sessionStorage)/i.test(source)) {
    add('Router, Store, API, service, and storage dependencies are forbidden')
  }
  if (classes.some((name) => ['modal', 'modal-head', 'modal-body', 'modal-foot', 'btn', 'form-grid'].includes(name))) {
    add('legacy modal classes are forbidden')
  }
  if (classes.some((name) => !name.startsWith('v2-'))) add('all static classes must use the v2- prefix')
  if (/(?:#[0-9a-f]{3,8}\b|rgba?\(|hsla?\()/i.test(source)) add('raw colors are forbidden')
  if (/var\(\s*--(?!v2-)[a-z0-9-]+/i.test(source)) add('non-V2 custom properties are forbidden')
  if (/:root\b|(^|[},]\s*)(?:html|body)(?=$|[\s,{.:#[>+~])/im.test(source)) add('global selectors are forbidden')
  return issues
}

export function validateModalProductionIsolation(source, normalizedPath) {
  const approved = new Set([
    'src/components/AppFormDialog.vue',
    'src/views/ApiHarvesterView.vue',
    'src/views/DashboardView.vue',
    'src/views/RecordsView.vue',
    'src/views/RequirementVerificationView.vue',
    'src/views/SystemRegressionView.vue',
  ])
  if (/\bBaseModal\b/.test(source) && !approved.has(normalizedPath)) {
    return [`${normalizedPath} references BaseModal outside Approved Production Usage`]
  }
  return []
}

const invalidSource = `
<template><dialog class="modal btn" v-html="unsafe" /></template>
<script setup>import axios from 'axios'; axios('/api/demo')</script>
<style scoped>.modal { color: #fff; background: var(--legacy-surface); }</style>
`
const selfCheckIssues = validateModalSource(invalidSource).join('\n')
for (const expected of ['native dialog', 'v-html', 'Router, Store, API', 'legacy modal', 'raw colors', 'non-V2']) {
  if (!selfCheckIssues.includes(expected)) fail(`validator self-check did not detect ${expected}`)
}
if (validateModalProductionIsolation('import { BaseModal } from "./v2/base/index.js"', 'src/App.vue').length !== 1) {
  fail('validator self-check did not reject production BaseModal usage')
}
if (validateModalProductionIsolation('const safe = true', 'src/App.vue').length !== 0) {
  fail('validator self-check rejected a clean production source')
}

for (const [name, path] of Object.entries(paths)) {
  if (!existsSync(path)) fail(`missing ${relative(repoDir, path)} (${name})`)
}

const modal = existsSync(paths.modal) ? read(paths.modal) : ''
const focusTrap = existsSync(paths.focusTrap) ? read(paths.focusTrap) : ''
const scrollLock = existsSync(paths.scrollLock) ? read(paths.scrollLock) : ''
const stack = existsSync(paths.stack) ? read(paths.stack) : ''
const portal = existsSync(paths.portal) ? read(paths.portal) : ''
const index = existsSync(paths.index) ? read(paths.index) : ''
const tokens = existsSync(paths.tokens) ? read(paths.tokens) : ''
const lab = existsSync(paths.lab) ? read(paths.lab) : ''
const dropdown = existsSync(paths.dropdown) ? read(paths.dropdown) : ''

if (modal) failures.push(...validateModalSource(modal).map((issue) => `BaseModal.vue: ${issue}`))

const modalContracts = [
  [/<Teleport\b/, 'BaseModal must use real Teleport'],
  [/frontend-v2-portal/, 'BaseModal must use the shared V2 Portal'],
  [/open:\s*\{\s*type:\s*Boolean/, 'BaseModal must define controlled open'],
  [/closeOnEscape:\s*\{[^}]*default:\s*true/s, 'BaseModal must default closeOnEscape to true'],
  [/closeOnBackdrop:\s*\{[^}]*default:\s*false/s, 'BaseModal must default closeOnBackdrop to false'],
  [/defineEmits\(\[['"]update:open['"],\s*['"]close['"]\]\)/, 'BaseModal must emit update:open and close'],
  [/role=["']dialog["']/, 'BaseModal must use role=dialog'],
  [/aria-modal=["']true["']/, 'BaseModal must expose aria-modal=true'],
  [/aria-labelledby/, 'BaseModal must bind aria-labelledby'],
  [/aria-describedby/, 'BaseModal must bind aria-describedby'],
  [/aria-label/, 'BaseModal must provide ariaLabel fallback'],
  [/useId\s*\(/, 'BaseModal must generate stable unique IDs'],
  [/console\.error/, 'BaseModal must report a missing accessible name in development'],
  [/reason\s*===\s*['"]escape['"]|['"]escape['"]\s*:\s*/, 'BaseModal must support escape close reason'],
  [/['"]backdrop['"]/, 'BaseModal must support backdrop close reason'],
  [/['"]close-button['"]/, 'BaseModal must support close-button reason'],
  [/event\.target\s*!==\s*event\.currentTarget/, 'Backdrop close must require direct backdrop targeting'],
  [/onBeforeUnmount/, 'BaseModal must clean up on unmount'],
  [/cancelAnimationFrame/, 'BaseModal must cancel pending focus work'],
  [/lockBodyScroll/, 'BaseModal must acquire scroll lock'],
  [/unlockBodyScroll/, 'BaseModal must release scroll lock'],
  [/createFocusTrap/, 'BaseModal must use the shared focus trap'],
  [/group:\s*['"]modal['"]/, 'BaseModal must register as a modal overlay'],
  [/isTop/, 'BaseModal must enforce top-only interaction'],
]
for (const [pattern, message] of modalContracts) requirePattern(modal, pattern, message)
if (/props\.open\s*=|open\.value\s*=/.test(modal)) fail('BaseModal must not mutate controlled open state')

const focusContracts = [
  [/\[autofocus\]/, 'Focus trap must prefer autofocus'],
  [/querySelectorAll/, 'Focus trap must discover focusable descendants'],
  [/Tab/, 'Focus trap must handle Tab'],
  [/shiftKey/, 'Focus trap must handle Shift+Tab'],
  [/focusin/, 'Focus trap must contain programmatic focus'],
  [/removeEventListener/, 'Focus trap must remove listeners'],
  [/tabindex/, 'Focus trap must support panel fallback'],
  [/disabled|aria-disabled|inert/, 'Focus trap must skip disabled or inert targets'],
  [/getClientRects|offsetParent/, 'Focus trap must skip hidden targets'],
]
for (const [pattern, message] of focusContracts) requirePattern(focusTrap, pattern, message)

const scrollContracts = [
  [/new Set\s*\(/, 'Scroll lock must track owners'],
  [/owners\.size/, 'Scroll lock must be reference counted'],
  [/document\.body\.style\.(?:overflow|setProperty\(['"]overflow['"])/, 'Scroll lock must manage body overflow'],
  [/originalOverflow|snapshot/, 'Scroll lock must preserve the original style'],
  [/typeof document === ['"]undefined['"]/, 'Scroll lock must be SSR safe'],
  [/getBodyScrollLockCount/, 'Scroll lock must expose a safe count for Lab proof'],
]
for (const [pattern, message] of scrollContracts) requirePattern(scrollLock, pattern, message)

const stackContracts = [
  [/group\s*===\s*['"]dropdown['"]|entry\.mutual/, 'Overlay stack must preserve Dropdown mutual exclusion'],
  [/group\s*===\s*['"]modal['"]|modalEntries/, 'Overlay stack must support modal entries'],
  [/overlayStack\.at\(-1\)/, 'Overlay stack must resolve the top overlay'],
  [/canClose/, 'Overlay stack must respect top overlay Escape policy'],
  [/onStackChange/, 'Overlay stack must notify modal top/index state'],
  [/\binert\b/, 'Overlay stack must block background interaction'],
  [/frontend-v2-portal/, 'Overlay stack must not inert the shared Portal'],
  [/removeEventListener/, 'Overlay stack must remove the global Escape listener'],
]
for (const [pattern, message] of stackContracts) requirePattern(stack, pattern, message)

for (const [pattern, message] of [
  [/frontend-v2-portal/, 'Portal must retain the shared class contract'],
  [/owners\s*=\s*new Set/, 'Portal must retain owner tracking'],
  [/v2PortalManaged/, 'Portal must only remove managed DOM'],
  [/getV2PortalOwnerCount/, 'Portal must expose a safe owner count for Lab proof'],
]) requirePattern(portal, pattern, message)

requirePattern(index, /import\s+BaseModal\s+from\s+['"]\.\/BaseModal\.vue['"]/, 'index.js must import BaseModal')
requirePattern(index, /export\s*\{[^}]*\bBaseModal\b[^}]*\}/s, 'index.js must export BaseModal')

for (const token of [
  '--v2-modal-surface', '--v2-modal-overlay', '--v2-modal-border', '--v2-modal-radius',
  '--v2-modal-shadow', '--v2-modal-overlay-z-index', '--v2-modal-z-index',
]) requirePattern(tokens, new RegExp(`${token}\\s*:`), `missing component token ${token}`)

const labCases = [
  'modal-default', 'modal-long-content', 'modal-footer', 'modal-no-footer',
  'modal-title-description', 'modal-aria-label', 'modal-backdrop-default',
  'modal-backdrop-close', 'modal-escape-disabled', 'modal-autofocus',
  'modal-no-focusable', 'modal-nested-parent', 'modal-nested-child',
  'modal-dropdown-inside', 'modal-dropdown-before', 'modal-controlled',
  'modal-unmount-open', 'modal-opener-removed', 'modal-scroll-lock',
  'modal-background-block',
]
for (const marker of labCases) requirePattern(lab, new RegExp(`data-testid=["']${marker}["']`), `Component Lab missing ${marker}`)
requirePattern(lab, />18 base components ready</, 'Component Lab component count must include BaseModal')
requirePattern(
  lab,
  /v-model:open=["']dropdownBeforeModalMenuOpen["'][^>]*:close-on-outside=["']false["']/,
  'Dropdown-before-Modal Lab scenario must remain open while the Modal trigger is clicked',
)
requirePattern(
  lab,
  /v-model:open=["']dropdownBeforeModalMenuOpen["'][^>]*placement=["']top-start["']/,
  'Dropdown-before-Modal Lab menu must not cover its Modal trigger',
)
for (const stateLabel of ['modal count', 'scroll lock count', 'focus element', 'portal owner count', 'last close reason']) {
  requirePattern(lab.toLowerCase(), new RegExp(stateLabel), `Component Lab missing ${stateLabel} proof`)
}

const productionFiles = walkFiles(join(frontendDir, 'src'))
  .filter((path) => /\.(?:vue|js)$/i.test(path))
  .filter((path) => {
    const normalized = relative(frontendDir, path).replaceAll('\\', '/')
    return !normalized.startsWith('src/dev/') && !normalized.startsWith('src/components/v2/base/')
  })
for (const path of productionFiles) {
  const normalized = relative(frontendDir, path).replaceAll('\\', '/')
  failures.push(...validateModalProductionIsolation(read(path), normalized))
}

for (const frozenPattern of [
  /group:\s*['"]dropdown['"]/, /ArrowDown[\s\S]*ArrowUp[\s\S]*Home[\s\S]*End/,
  /closeOnOutside/, /requestAnimationFrame/, /removeEventListener\(["']scroll/,
]) requirePattern(dropdown, frozenPattern, 'BaseDropdown frozen contract regressed')

if (failures.length > 0) {
  console.error('V2 Modal foundation validation failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('V2 Modal foundation validation passed (BaseModal, nested overlay, focus, scroll, isolation, Lab-only usage).')
