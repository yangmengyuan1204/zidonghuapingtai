import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const repoDir = resolve(frontendDir, '..')
const componentsDir = join(frontendDir, 'src', 'components', 'v2', 'base')

const primitiveNames = [
  'BaseButton',
  'BaseIconButton',
  'BaseInput',
  'BaseCheckbox',
  'BaseBadge',
  'BaseChip',
  'BaseCard',
]
const supportNames = [
  'BasePagination',
  'BaseTooltip',
  'BaseSkeleton',
  'BaseEmptyState',
  'BaseErrorState',
]
const allNames = [...primitiveNames, ...supportNames]
const failures = []

function fail(message) {
  failures.push(message)
}

function read(path) {
  return readFileSync(path, 'utf8')
}

function styleBlocks(source) {
  return [...source.matchAll(/<style\b([^>]*)>([\s\S]*?)<\/style>/gi)]
    .map(([, attributes, css]) => ({ attributes, css }))
}

function templateBlock(source) {
  return source.match(/<template\b[^>]*>([\s\S]*?)<\/template>/i)?.[1] ?? ''
}

function staticClassTokens(source) {
  return [...source.matchAll(/(?<!:)class=["']([^"']+)["']/g)]
    .flatMap(([, value]) => value.split(/\s+/))
    .filter(Boolean)
}

const forbiddenDependency = /(?:from\s+['"][^'"]*(?:vue-router|pinia|axios|stores\/|api\/|services\/)|import\s+['"][^'"]*(?:vue-router|pinia|axios|stores\/|api\/|services\/)|require\s*\(\s*['"][^'"]*(?:vue-router|pinia|axios|stores\/|api\/|services\/)|localStorage|sessionStorage|\bfetch\s*\(|\bXMLHttpRequest\b|\baxios\s*(?:\.|\())/i
const forbiddenLegacyClasses = new Set(['btn', 'field', 'panel', 'badge', 'modal', 'toast', 'pagination', 'page-btn', 'empty', 'alert'])
const forbiddenRawColor = /(?:#[0-9a-f]{3,8}\b|rgba?\(|hsla?\()/i
const forbiddenGlobalSelector = /(^|[},]\s*)(?::root|html|body|table)(?=$|[\s,{.:#[>+~])/im
const forbiddenLegacySelector = /\.(?:btn|field|panel|badge|modal|toast|pagination|page-btn|empty|alert)(?=$|[\s,{.:#[>+~])/im

function validateGenericSource(name, source) {
  const issues = []
  const add = (message) => issues.push(`${name}: ${message}`)

  if (forbiddenDependency.test(source)) add('references Router, Pinia, API, service, or browser storage')
  if (/\bv-html\b/.test(source)) add('uses forbidden v-html')
  if (forbiddenRawColor.test(source)) add('contains an inline color value')
  if (/:root\b/.test(source)) add('contains shared :root')
  const dynamicClassValues = [...source.matchAll(/:class\s*=\s*"([^"]*)"|:class\s*=\s*'([^']*)'/g)]
    .map((match) => match[1] ?? match[2] ?? '')
  if (dynamicClassValues.some((value) =>
    /['"](?:btn|field|panel|badge|modal|toast|pagination|page-btn|empty|alert)['"]/.test(value)
  )) {
    add('contains a dynamically bound legacy class')
  }

  for (const className of staticClassTokens(source)) {
    if (forbiddenLegacyClasses.has(className)) add(`uses forbidden legacy class ${className}`)
    if (!className.startsWith('v2-')) add(`uses non-V2 class ${className}`)
  }

  const styles = styleBlocks(source)
  if (styles.length !== 1 || !/\bscoped\b/i.test(styles[0]?.attributes ?? '')) {
    add('must contain exactly one scoped style block')
  }
  for (const { css } of styles) {
    if (!/var\(\s*--v2-[a-z0-9-]+/i.test(css)) add('styles do not consume V2 tokens')
    if (/var\(\s*--(?!v2-)[a-z0-9-]+/i.test(css)) add('references a non-V2 custom property')
    if (forbiddenGlobalSelector.test(css)) add('contains an unscoped shared element selector')
    if (forbiddenLegacySelector.test(css)) add('styles contain a legacy selector')
  }

  if (!/v-bind=["']\$attrs["']/.test(source)) add('does not forward $attrs')
  return issues
}

const selfCheckSample = `
<template><div class="btn" v-html="unsafe"></div></template>
<script setup>import axios from 'axios'; axios('/api/demo')</script>
<style>:root { color: #fff; }</style>
`
const selfCheckIssues = validateGenericSource('self-check', selfCheckSample)
for (const expected of ['Router, Pinia, API', 'v-html', 'legacy class', 'inline color', 'shared :root']) {
  if (!selfCheckIssues.some((issue) => issue.includes(expected))) {
    fail(`validator self-check did not detect ${expected}`)
  }
}

const sources = new Map()
for (const name of supportNames) {
  const path = join(componentsDir, `${name}.vue`)
  if (!existsSync(path)) {
    fail(`missing ${relative(repoDir, path)}`)
    continue
  }
  const source = read(path)
  sources.set(name, source)
  failures.push(...validateGenericSource(relative(repoDir, path), source))
}

const indexPath = join(componentsDir, 'index.js')
if (!existsSync(indexPath)) {
  fail(`missing ${relative(repoDir, indexPath)}`)
} else {
  const indexSource = read(indexPath)
  const directExports = [...indexSource.matchAll(
    /export\s*\{\s*default\s+as\s+(Base[A-Za-z]+)\s*\}\s*from\s*['"]\.\/(Base[A-Za-z]+)\.vue['"]/g,
  )].map(([, exported, file]) => ({ exported, file }))
  const imports = new Map(
    [...indexSource.matchAll(/import\s+(Base[A-Za-z]+)\s+from\s+['"]\.\/(Base[A-Za-z]+)\.vue['"]/g)]
      .map(([, imported, file]) => [imported, file]),
  )
  const namedExports = new Set(
    [...indexSource.matchAll(/export\s*\{([^}]+)\}/g)]
      .flatMap(([, names]) => names.split(',').map((name) => name.trim()))
      .filter((name) => /^Base[A-Za-z]+$/.test(name)),
  )
  const exports = new Set(directExports.map(({ exported }) => exported))
  for (const name of namedExports) {
    if (imports.get(name) === name) exports.add(name)
  }
  if (exports.size !== allNames.length) {
    fail(`index.js must export exactly ${allNames.length} base components`)
  }
  for (const name of allNames) {
    const direct = directExports.some(({ exported, file }) => exported === name && file === name)
    const importedAndExported = imports.get(name) === name && namedExports.has(name)
    if (!direct && !importedAndExported) {
      fail(`index.js does not correctly export ${name}`)
    }
  }
}

const contracts = {
  BasePagination: [
    [/<nav\b/, 'must render a nav root'],
    [/:aria-label=["']ariaLabel["']/, 'must bind the navigation aria-label'],
    [/Math\.ceil\s*\(/, 'must calculate total pages with Math.ceil'],
    [/:aria-current=["'][^>]*\bpage\b/, 'must expose the current page'],
    [/<span\b[^>]*v-else[^>]*v2-base-pagination__ellipsis/s, 'must render ellipsis as non-interactive text'],
    [/defineEmits\(\[['"]change['"]\]\)/, 'must declare change event'],
    [/if\s*\([^)]*props\.disabled[^)]*\)\s*return/s, 'must guard disabled changes'],
    [/targetPage\s*===\s*currentPage\.value/, 'must not emit the current page'],
    [/:disabled=["']previousDisabled["']/, 'must disable Previous at the boundary'],
    [/:disabled=["']nextDisabled["']/, 'must disable Next at the boundary'],
  ],
  BaseTooltip: [
    [/role=["']tooltip["']/, 'must use role=tooltip'],
    [/aria-describedby/, 'must associate the trigger with the tooltip'],
    [/\bcloneVNode\s*\(/, 'must place aria-describedby on the slotted trigger'],
    [/@mouseenter=|onMouseenter/, 'must support mouseenter'],
    [/@mouseleave=|onMouseleave/, 'must support mouseleave'],
    [/@focusin=|onFocusin/, 'must support focusin'],
    [/@focusout=|onFocusout/, 'must support focusout'],
    [/@keydown\.esc=|onKeydown/, 'must support Escape'],
    [/\bclearTimeout\s*\(/, 'must clear pending timers'],
    [/\bonBeforeUnmount\s*\(/, 'must clear timers on unmount'],
    [/\bdisabled\b[\s\S]*\bcontent\b|\bcontent\b[\s\S]*\bdisabled\b/, 'must guard disabled or empty content'],
  ],
  BaseSkeleton: [
    [/aria-hidden=["']true["']/, 'must be hidden from assistive technology'],
    [/prefers-reduced-motion:\s*reduce/, 'must stop animation for reduced motion'],
    [/animated/, 'must support disabling animation'],
    [/\bvariant\b/, 'must support text, circle, and rectangle variants'],
    [/\blines\b/, 'must support multiple text lines'],
    [/\bpx\b/, 'must convert numeric dimensions to px'],
  ],
  BaseEmptyState: [
    [/title:\s*\{[^}]*required:\s*true/s, 'must require a title'],
    [/<h[2-6]\b/, 'must render a non-page-level heading'],
    [/v-if=["']\$slots\.action["']/, 'must omit an empty action container'],
    [/<slot\s+name=["']icon["']/, 'must provide an icon slot'],
    [/<slot\s+name=["']action["']/, 'must provide an action slot'],
  ],
  BaseErrorState: [
    [/title:\s*\{[^}]*required:\s*true/s, 'must require a title'],
    [/:role=["']stateRole["']/, 'must switch alert/status role'],
    [/retryable\s*&&\s*!\$slots\.action/, 'must conditionally render the default retry action'],
    [/<BaseButton\b/, 'must reuse BaseButton'],
    [/:loading=["']busy["']/, 'must expose busy retry state'],
    [/defineEmits\(\[['"]retry['"]\]\)/, 'must declare retry event'],
    [/if\s*\(\s*props\.busy\s*\)\s*return/, 'must guard retry while busy'],
    [/<slot\s+name=["']details["']/, 'must provide a details slot'],
  ],
}

for (const [name, requirements] of Object.entries(contracts)) {
  const source = sources.get(name)
  if (!source) continue
  for (const [pattern, description] of requirements) {
    if (!pattern.test(source)) fail(`${name} ${description}`)
  }
}

const tokenFiles = [
  join(frontendDir, 'src', 'styles', 'v2', 'tokens.foundation.css'),
  join(frontendDir, 'src', 'styles', 'v2', 'tokens.semantic.css'),
  join(frontendDir, 'src', 'styles', 'v2', 'tokens.component.css'),
]
const declaredTokens = new Set(
  tokenFiles
    .filter(existsSync)
    .flatMap((path) => [...read(path).matchAll(/(--v2-[a-z0-9-]+)\s*:/gi)].map(([, name]) => name)),
)
for (const [name, source] of sources) {
  for (const [, token] of source.matchAll(/var\(\s*(--v2-[a-z0-9-]+)/gi)) {
    if (!declaredTokens.has(token)) fail(`${name} references undefined token ${token}`)
  }
}

if (sources.size === supportNames.length) {
  const labPath = join(frontendDir, 'src', 'dev', 'V2BaseComponentsLab.vue')
  if (!existsSync(labPath)) {
    fail(`missing ${relative(repoDir, labPath)}`)
  } else {
    const labSource = read(labPath)
    if (forbiddenDependency.test(labSource)) fail('Component Lab references a forbidden dependency')
    for (const name of supportNames) {
      if (!new RegExp(`<${name}\\b`).test(labSource)) fail(`Component Lab does not render ${name}`)
    }
  }
}

const productionFiles = [
  join(frontendDir, 'src', 'main.js'),
  join(frontendDir, 'src', 'App.vue'),
  join(frontendDir, 'src', 'router', 'index.js'),
  join(frontendDir, 'vite.config.js'),
]
for (const path of productionFiles) {
  if (existsSync(path) && /(?:BasePagination|BaseTooltip|BaseSkeleton|BaseEmptyState|BaseErrorState|V2BaseComponentsLab|v2-base-components)/.test(read(path))) {
    fail(`${relative(repoDir, path)} references Phase 5.2B1 or the development-only Lab`)
  }
}

for (const [name, source] of sources) {
  const template = templateBlock(source)
  if (name === 'BasePagination') {
    const buttonBlocks = [...template.matchAll(/<button\b[\s\S]*?<\/button>/gi)].map(([block]) => block)
    if (buttonBlocks.some((block) => /(?:ellipsis|…)/i.test(block))) {
      fail('BasePagination renders a clickable ellipsis')
    }
  }
  if (name === 'BaseTooltip' && /<(?:Teleport|teleport)\b/.test(template)) {
    fail('BaseTooltip must not use a Portal or Teleport')
  }
}

if (failures.length > 0) {
  console.error('V2 support components validation failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log(`V2 support components validation passed (${supportNames.length} support components, ${allNames.length} total exports).`)
