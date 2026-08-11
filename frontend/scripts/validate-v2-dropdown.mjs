import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const repoDir = resolve(frontendDir, '..')
const baseDir = join(frontendDir, 'src', 'components', 'v2', 'base')
const overlayDir = join(frontendDir, 'src', 'components', 'v2', 'overlay')

const paths = {
  dropdown: join(baseDir, 'BaseDropdown.vue'),
  item: join(baseDir, 'BaseDropdownItem.vue'),
  portal: join(overlayDir, 'portal.js'),
  stack: join(overlayDir, 'overlayStack.js'),
  index: join(baseDir, 'index.js'),
  tokens: join(frontendDir, 'src', 'styles', 'v2', 'tokens.component.css'),
  lab: join(frontendDir, 'src', 'dev', 'V2BaseComponentsLab.vue'),
  main: join(frontendDir, 'src', 'main.js'),
  app: join(frontendDir, 'src', 'App.vue'),
  router: join(frontendDir, 'src', 'router', 'index.js'),
  vite: join(frontendDir, 'vite.config.js'),
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

function validateComponent(label, source) {
  const forbiddenDependency = /(?:vue-router|pinia|axios|stores\/|api\/|services\/|localStorage|sessionStorage|\bfetch\s*\(|\bXMLHttpRequest\b)/i
  const forbiddenLegacyClasses = new Set(['btn', 'field', 'panel', 'modal', 'toast', 'dropdown', 'menu'])
  const forbiddenLegacySelector = /\.(?:btn|field|panel|modal|toast|dropdown|menu)(?=$|[\s,{.:#[>+~])/im
  const forbiddenRawColor = /(?:#[0-9a-f]{3,8}\b|rgba?\(|hsla?\()/i

  if (forbiddenDependency.test(source)) fail(`${label} references Router, Pinia, API, service, or storage`)
  if (/\bv-html\b/.test(source)) fail(`${label} uses v-html`)
  if (/:root\b/.test(source)) fail(`${label} contains shared :root`)
  if (forbiddenLegacySelector.test(source)) fail(`${label} uses a legacy selector`)
  if (forbiddenRawColor.test(source)) fail(`${label} contains a raw color`)

  const classes = [...source.matchAll(/(?<!:)class=["']([^"']+)["']/g)]
    .flatMap(([, value]) => value.split(/\s+/))
    .filter(Boolean)
  for (const className of classes) {
    if (forbiddenLegacyClasses.has(className)) fail(`${label} uses legacy class ${className}`)
    if (!className.startsWith('v2-')) fail(`${label} uses non-V2 class ${className}`)
  }

  const styles = [...source.matchAll(/<style\b([^>]*)>([\s\S]*?)<\/style>/gi)]
  if (styles.length !== 1 || !/\bscoped\b/i.test(styles[0]?.[1] ?? '')) {
    fail(`${label} must contain exactly one scoped style block`)
  }
  if (!/var\(\s*--v2-[a-z0-9-]+/i.test(styles[0]?.[2] ?? '')) {
    fail(`${label} styles do not consume V2 tokens`)
  }
}

const selfCheck = '<template><div class="dropdown" v-html="x" /></template><style scoped>.dropdown{color:#fff}</style>'
const selfCheckBefore = failures.length
validateComponent('self-check', selfCheck)
if (failures.length === selfCheckBefore) fail('validator self-check did not reject a known violation')
failures.splice(selfCheckBefore)

for (const [name, path] of Object.entries(paths)) {
  if (!existsSync(path)) fail(`missing ${relative(repoDir, path)}`)
}

const dropdown = existsSync(paths.dropdown) ? read(paths.dropdown) : ''
const item = existsSync(paths.item) ? read(paths.item) : ''
const portal = existsSync(paths.portal) ? read(paths.portal) : ''
const stack = existsSync(paths.stack) ? read(paths.stack) : ''
const index = existsSync(paths.index) ? read(paths.index) : ''
const tokens = existsSync(paths.tokens) ? read(paths.tokens) : ''
const lab = existsSync(paths.lab) ? read(paths.lab) : ''

if (dropdown) validateComponent('BaseDropdown.vue', dropdown)
if (item) validateComponent('BaseDropdownItem.vue', item)

const dropdownContracts = [
  [/open:\s*\{\s*type:\s*Boolean/, 'BaseDropdown must define controlled open prop'],
  [/const renderedOpen = computed\(\(\) => props\.open && !props\.disabled\)/, 'BaseDropdown visibility must be derived from controlled open prop'],
  [/defineEmits\(\[['"]update:open['"],\s*['"]select['"]\]\)/, 'BaseDropdown must emit update:open and select'],
  [/bottom-start[\s\S]*bottom-end[\s\S]*top-start[\s\S]*top-end/, 'BaseDropdown must support four placements'],
  [/<Teleport\b/, 'BaseDropdown must use real Teleport'],
  [/frontend-v2-portal/, 'BaseDropdown must target the V2 portal'],
  [/aria-haspopup[\s\S]*menu/, 'BaseDropdown trigger must expose aria-haspopup=menu'],
  [/aria-expanded/, 'BaseDropdown trigger must expose aria-expanded'],
  [/aria-controls/, 'BaseDropdown trigger must expose aria-controls'],
  [/role=["']menu["']/, 'BaseDropdown menu must use role=menu'],
  [/ArrowDown[\s\S]*ArrowUp[\s\S]*Home[\s\S]*End/, 'BaseDropdown must implement Arrow/Home/End navigation'],
  [/Enter[\s\S]*Space|['"] ['"]/, 'BaseDropdown must implement Enter and Space'],
  [/Escape/, 'BaseDropdown must implement Escape'],
  [/Tab/, 'BaseDropdown must close on Tab without a focus trap'],
  [/requestAnimationFrame/, 'BaseDropdown must schedule positioning with requestAnimationFrame'],
  [/cancelAnimationFrame/, 'BaseDropdown must cancel pending animation frames'],
  [/addEventListener\(["']resize/, 'BaseDropdown must reposition on resize'],
  [/addEventListener\(["']scroll/, 'BaseDropdown must reposition on scroll'],
  [/removeEventListener\(["']resize/, 'BaseDropdown must clean resize listeners'],
  [/removeEventListener\(["']scroll/, 'BaseDropdown must clean scroll listeners'],
  [/removeEventListener\(["']pointerdown/, 'BaseDropdown must clean outside-click listener'],
  [/aria-disabled["']\) !== ["']true["'][\s\S]*!item\.disabled/, 'BaseDropdown must skip disabled menu items'],
  [/restoreFocus[\s\S]*\.focus\(\)/, 'BaseDropdown must restore trigger focus when requested'],
  [/group:\s*['"]dropdown['"]/, 'BaseDropdown must register in the mutual-exclusion Dropdown group'],
  [/closeOnSelect/, 'BaseDropdown must support closeOnSelect=false'],
  [/closeOnOutside/, 'BaseDropdown must support closeOnOutside=false'],
  [/matchTriggerWidth/, 'BaseDropdown must support matchTriggerWidth'],
  [/Math\.min[\s\S]*Math\.max|Math\.max[\s\S]*Math\.min/, 'BaseDropdown must clamp horizontal position'],
  [/onBeforeUnmount/, 'BaseDropdown must clean up on unmount'],
]
for (const [pattern, message] of dropdownContracts) requirePattern(dropdown, pattern, message)
if (/renderedOpen\.value\s*=/.test(dropdown)) {
  fail('BaseDropdown must not mutate its controlled visible state internally')
}
if ((dropdown.match(/emit\(['"]select['"]/g) ?? []).length !== 1) {
  fail('BaseDropdown must contain exactly one parent select emission path')
}

const itemContracts = [
  [/role=["']menuitem["']/, 'BaseDropdownItem must use role=menuitem'],
  [/aria-disabled/, 'BaseDropdownItem must expose aria-disabled'],
  [/disabled/, 'BaseDropdownItem must support disabled'],
  [/danger/, 'BaseDropdownItem must support danger'],
  [/<slot\s+name=["']icon["']/, 'BaseDropdownItem must provide icon slot'],
  [/<slot\s+name=["']suffix["']/, 'BaseDropdownItem must provide suffix slot'],
  [/danger && !\$slots\.icon/, 'BaseDropdownItem danger state must provide a non-color cue'],
  [/defineEmits\(\[['"]select['"]\]\)/, 'BaseDropdownItem must emit select'],
]
for (const [pattern, message] of itemContracts) requirePattern(item, pattern, message)
if ((item.match(/emit\(['"]select['"]/g) ?? []).length !== 1) {
  fail('BaseDropdownItem must contain exactly one item select emission path')
}

const portalContracts = [
  [/frontend-v2-portal/, 'Portal module must use frontend-v2-portal'],
  [/querySelectorAll/, 'Portal module must enforce uniqueness'],
  [/v2PortalManaged/, 'Portal module must mark and own its runtime container'],
  [/filter\([\s\S]*v2PortalManaged/, 'Portal module must only reuse owned runtime containers'],
  [/createElement/, 'Portal module must create the runtime container'],
  [/remove\(\)/, 'Portal module must remove an unused container'],
]
for (const [pattern, message] of portalContracts) requirePattern(portal, pattern, message)

const stackContracts = [
  [/keydown/, 'Overlay stack must manage Escape'],
  [/Escape/, 'Overlay stack must close the top overlay on Escape'],
  [/removeEventListener/, 'Overlay stack must clean its global listener'],
  [/requestClose/, 'Overlay stack must close prior Dropdown instances'],
]
for (const [pattern, message] of stackContracts) requirePattern(stack, pattern, message)

for (const name of ['BaseDropdown', 'BaseDropdownItem']) {
  requirePattern(index, new RegExp(`Base${name.replace(/^Base/, '')}`), `index.js must export ${name}`)
}
for (const token of [
  '--v2-dropdown-item-height',
  '--v2-dropdown-padding',
  '--v2-dropdown-viewport-gap',
  '--v2-dropdown-item-danger-text',
]) {
  requirePattern(tokens, new RegExp(`${token}\\s*:`), `missing component token ${token}`)
}

const labCases = [
  'bottom-start', 'bottom-end', 'top-start', 'top-end',
  'dropdown-disabled-trigger', 'dropdown-disabled-item', 'dropdown-danger-item',
  'dropdown-icon-item', 'dropdown-suffix-item', 'dropdown-keep-open',
  'dropdown-ignore-outside', 'dropdown-match-width', 'dropdown-no-items',
  'dropdown-long-text', 'dropdown-viewport-edge', 'dropdown-mutual-a',
  'dropdown-mutual-b', 'dropdown-unmount', 'dropdown-controlled',
]
for (const marker of labCases) {
  requirePattern(lab, new RegExp(marker), `Component Lab missing ${marker}`)
}

for (const path of [paths.main, paths.app, paths.router, paths.vite]) {
  if (!existsSync(path)) continue
  const source = read(path)
  if (/BaseDropdown|BaseDropdownItem|V2BaseComponentsLab|v2-base-components/.test(source)) {
    fail(`${relative(repoDir, path)} references Dropdown or the development-only Lab`)
  }
  if (/frontend-v2-portal/.test(source)) {
    fail(`${relative(repoDir, path)} creates a production Portal outside the Dropdown lifecycle`)
  }
}

if (failures.length > 0) {
  console.error('V2 Dropdown validation failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('V2 Dropdown validation passed (Portal, Overlay Stack, BaseDropdown, BaseDropdownItem, Lab coverage).')
