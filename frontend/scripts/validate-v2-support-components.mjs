import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
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
const dropdownNames = ['BaseDropdown', 'BaseDropdownItem']
const resourceNames = ['BaseSelect', 'BaseTextarea', 'BaseTable']
const modalNames = ['BaseModal']
const expectedExportNames = [...allNames, ...dropdownNames, ...resourceNames, ...modalNames]
const productionUsageNames = [...supportNames, ...dropdownNames, ...resourceNames, ...modalNames]
const approvedProductionUsage = new Map([
  ['BaseBadge', new Set(['src/components/AppShell.vue'])],
  ['BasePagination', new Set(['src/views/ApiCasesView.vue', 'src/components/AppPagination.vue'])],
  ['BaseDropdown', new Set(['src/views/DashboardView.vue'])],
  ['BaseDropdownItem', new Set(['src/views/DashboardView.vue'])],
  ['BaseSkeleton', new Set(['src/views/DashboardView.vue'])],
  ['BaseEmptyState', new Set([
    'src/views/DashboardView.vue', 'src/views/ApiHarvesterView.vue', 'src/views/RequirementVerificationView.vue',
    'src/views/SystemRegressionView.vue', 'src/components/data-scripts/DataAgentWorkspace.vue',
    'src/components/data-scripts/DataScriptCatalog.vue',
  ])],
  ['BaseErrorState', new Set(['src/views/DashboardView.vue', 'src/views/DataScriptsView.vue', 'src/views/RequirementVerificationView.vue'])],
  ['BaseSelect', new Set([
    'src/components/AppFormDialog.vue', 'src/components/AppShell.vue', 'src/views/ApiCasesView.vue',
    'src/views/ApiHarvesterView.vue', 'src/views/DataScriptsView.vue', 'src/views/RequirementVerificationView.vue',
    'src/views/SystemRegressionView.vue',
  ])],
  ['BaseTable', new Set(['src/views/ApiCasesView.vue', 'src/views/SystemRegressionView.vue'])],
  ['BaseTextarea', new Set([
    'src/components/AppFormDialog.vue', 'src/components/data-scripts/DataAgentWorkspace.vue',
    'src/components/data-scripts/DataScriptRunner.vue', 'src/views/RequirementVerificationView.vue',
    'src/views/SystemRegressionView.vue',
  ])],
  ['BaseModal', new Set([
    'src/components/AppFormDialog.vue', 'src/views/ApiHarvesterView.vue', 'src/views/DashboardView.vue',
    'src/views/RecordsView.vue', 'src/views/RequirementVerificationView.vue', 'src/views/SystemRegressionView.vue',
  ])],
])
const fullyMigratedProductionPages = new Set([
  'src/views/DashboardView.vue',
  'src/views/ApiHarvesterView.vue',
  'src/views/DataScriptsView.vue',
  'src/views/RequirementVerificationView.vue',
  'src/views/SystemRegressionView.vue',
])
const partialMigrationRules = new Map([
  ['src/views/ApiCasesView.vue', {
    approvedComponents: new Set([
      'BaseButton',
      'BaseBadge',
      'BaseCheckbox',
      'BasePagination',
      'BaseSelect',
      'BaseTable',
    ]),
    forbiddenLegacyInMigratedRegions: new Set([
      'btn',
      'badge',
      'pagination',
      'field',
      'compact',
      'table-wrap',
    ]),
    allowedLegacyOutsideMigratedRegions: new Set([
      'toolbar',
      'filters',
      'actions',
    ]),
  }],
  ['src/views/RecordsView.vue', {
    approvedComponents: new Set(['BaseModal']),
    forbiddenLegacyInMigratedRegions: new Set(),
    allowedLegacyOutsideMigratedRegions: new Set(['toolbar', 'filters', 'field', 'compact', 'badge', 'actions', 'btn', 'secondary', 'empty']),
  }],
])
const sharedComponentMigrationRules = new Map([
  ['src/components/AppFormDialog.vue', {
    approvedComponents: new Set(['BaseButton', 'BaseInput', 'BaseModal', 'BaseSelect', 'BaseTextarea']),
  }],
  ['src/components/AppPagination.vue', { approvedComponents: new Set(['BasePagination']) }],
  ['src/components/AppShell.vue', { approvedComponents: new Set(['BaseBadge', 'BaseButton', 'BaseSelect']) }],
  ['src/components/data-scripts/DataAgentWorkspace.vue', { approvedComponents: new Set(['BaseButton', 'BaseEmptyState', 'BaseTextarea']) }],
  ['src/components/data-scripts/DataScriptCatalog.vue', { approvedComponents: new Set(['BaseEmptyState']) }],
  ['src/components/data-scripts/DataScriptRunner.vue', { approvedComponents: new Set(['BaseButton', 'BaseTextarea']) }],
])
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

function walkFiles(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? walkFiles(path) : [path]
  })
}

export function isApprovedProductionUsage(componentName, normalizedPath) {
  return approvedProductionUsage.get(componentName)?.has(normalizedPath) ?? false
}

const forbiddenDependency = /(?:from\s+['"][^'"]*(?:vue-router|pinia|axios|stores\/|api\/|services\/)|import\s+['"][^'"]*(?:vue-router|pinia|axios|stores\/|api\/|services\/)|require\s*\(\s*['"][^'"]*(?:vue-router|pinia|axios|stores\/|api\/|services\/)|localStorage|sessionStorage|\bfetch\s*\(|\bXMLHttpRequest\b|\baxios\s*(?:\.|\())/i
const forbiddenLegacyClasses = new Set(['btn', 'field', 'panel', 'badge', 'modal', 'toast', 'pagination', 'page-btn', 'empty', 'alert'])
const forbiddenApprovedUsageLegacyClasses = new Set([
  'actions',
  'badge',
  'btn',
  'compact',
  'dropdown',
  'dropdown-item',
  'dropdown-menu',
  'empty',
  'empty-state',
  'field',
  'filters',
  'panel',
  'panel-title',
  'secondary',
  'skeleton',
  'stat',
  'stats',
  'toolbar',
])
const forbiddenRawColor = /(?:#[0-9a-f]{3,8}\b|rgba?\(|hsla?\()/i
const forbiddenGlobalSelector = /(^|[},]\s*)(?::root|html|body|table)(?=$|[\s,{.:#[>+~])/im
const forbiddenLegacySelector = /\.(?:btn|field|panel|badge|modal|toast|pagination|page-btn|empty|alert)(?=$|[\s,{.:#[>+~])/im
const forbiddenPortal = /(?:<(?:Teleport|teleport)\b|\bh\s*\(\s*(?:Teleport|Portal)\b|:is\s*=\s*["'][^"']*(?:Teleport|Portal)|\bcreatePortal\s*\(|from\s+['"][^'"]*portal)/i

function validateGenericSource(name, source) {
  const issues = []
  const add = (message) => issues.push(`${name}: ${message}`)

  if (forbiddenDependency.test(source)) add('references Router, Pinia, API, service, or browser storage')
  if (/\bv-html\b/.test(source)) add('uses forbidden v-html')
  if (forbiddenRawColor.test(source)) add('contains an inline color value')
  if (/:root\b/.test(source)) add('contains shared :root')
  const dynamicClassValues = [...source.matchAll(/:class\s*=\s*"([^"]*)"|:class\s*=\s*'([^']*)'/g)]
    .map((match) => match[1] ?? match[2] ?? '')
  if (dynamicClassValues.some((value) => {
    const quotedTokens = [...value.matchAll(/['"]([^'"]+)['"]/g)]
      .flatMap(([, classNames]) => classNames.split(/\s+/))
    const unquotedObjectKey = /(?:^|[,{]\s*)(?:btn|field|panel|badge|modal|toast|pagination|page-btn|empty|alert)\s*:/.test(value)
    return quotedTokens.some((token) => forbiddenLegacyClasses.has(token)) || unquotedObjectKey
  })) {
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

export function validateApprovedProductionLegacyUsage(normalizedPath, source) {
  const issues = []
  const staticLegacyClasses = staticClassTokens(source)
    .filter((className) => forbiddenApprovedUsageLegacyClasses.has(className))
  if (staticLegacyClasses.length > 0) {
    issues.push(`${normalizedPath} uses approved-production legacy classes ${[...new Set(staticLegacyClasses)].join(', ')}`)
  }

  const dynamicClassValues = [...source.matchAll(/:class\s*=\s*"([^"]*)"|:class\s*=\s*'([^']*)'/g)]
    .map((match) => match[1] ?? match[2] ?? '')
  for (const value of dynamicClassValues) {
    const tokens = [...value.matchAll(/['"]([^'"]+)['"]/g)]
      .flatMap(([, classNames]) => classNames.split(/\s+/))
    if (tokens.some((token) => forbiddenApprovedUsageLegacyClasses.has(token))) {
      issues.push(`${normalizedPath} dynamically binds an approved-production legacy class`)
      break
    }
  }

  const legacySelector = new RegExp(
    `\\.(?:${[...forbiddenApprovedUsageLegacyClasses].join('|')})(?=$|[\\s,{.:#[>+~])`,
    'im',
  )
  for (const { css } of styleBlocks(source)) {
    if (legacySelector.test(css)) {
      issues.push(`${normalizedPath} styles an approved-production legacy selector`)
    }
    if (/var\(\s*--(?!v2-)[a-z0-9-]+/i.test(css)) {
      issues.push(`${normalizedPath} references a non-V2 custom property in approved production usage`)
    }
  }

  return issues
}

export function validateProductionBoundaryConfiguration() {
  const issues = []

  for (const path of fullyMigratedProductionPages) {
    if (partialMigrationRules.has(path)) {
      issues.push(`${path} cannot be both fully and partially migrated`)
    }
  }

  for (const [path, rule] of partialMigrationRules) {
    if (!path.startsWith('src/views/') || !path.endsWith('.vue')) {
      issues.push(`${path} is not a production view path`)
    }
    if (!(rule.approvedComponents instanceof Set) || rule.approvedComponents.size === 0) {
      issues.push(`${path} must declare approved components`)
    }
    for (const name of rule.approvedComponents ?? []) {
      if (!expectedExportNames.includes(name)) {
        issues.push(`${path} approves unknown component ${name}`)
      }
      if (productionUsageNames.includes(name) && !isApprovedProductionUsage(name, path)) {
        issues.push(`${path} must be allow-listed for ${name}`)
      }
    }
    for (const className of rule.forbiddenLegacyInMigratedRegions ?? []) {
      if (rule.allowedLegacyOutsideMigratedRegions?.has(className)) {
        issues.push(`${path} cannot both allow and forbid legacy class ${className}`)
      }
    }
  }

  for (const [path, rule] of sharedComponentMigrationRules) {
    if (!path.startsWith('src/components/') || !path.endsWith('.vue')) {
      issues.push(`${path} is not a shared production component path`)
    }
    if (!(rule.approvedComponents instanceof Set) || rule.approvedComponents.size === 0) {
      issues.push(`${path} must declare approved shared components`)
    }
    for (const name of rule.approvedComponents ?? []) {
      if (!expectedExportNames.includes(name)) {
        issues.push(`${path} approves unknown component ${name}`)
      }
      if (productionUsageNames.includes(name) && !isApprovedProductionUsage(name, path)) {
        issues.push(`${path} must be allow-listed for ${name}`)
      }
    }
  }

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
if (!forbiddenPortal.test(`h(Teleport, null, 'forbidden')`)) {
  fail('validator self-check did not detect render-function Portal usage')
}
failures.push(...validateProductionBoundaryConfiguration())

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
  if (exports.size !== expectedExportNames.length) {
    fail(`index.js must export exactly ${expectedExportNames.length} completed base components`)
  }
  for (const name of expectedExportNames) {
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
  ...walkFiles(join(frontendDir, 'src'))
    .filter((path) => /\.(?:vue|js)$/i.test(path))
    .filter((path) => {
      const normalized = relative(frontendDir, path).replaceAll('\\', '/')
      return !normalized.startsWith('src/dev/')
        && !normalized.startsWith('src/components/v2/base/')
    }),
  join(frontendDir, 'vite.config.js'),
]
for (const path of productionFiles) {
  if (!existsSync(path)) continue
  const source = read(path)
  const normalized = relative(frontendDir, path).replaceAll('\\', '/')

  if (/(?:V2BaseComponentsLab|v2-base-components)/.test(source)) {
    fail(`${relative(repoDir, path)} references the development-only Component Lab`)
  }

  for (const name of productionUsageNames) {
    if (new RegExp(`\\b${name}\\b`).test(source) && !isApprovedProductionUsage(name, normalized)) {
      fail(`${relative(repoDir, path)} references ${name} outside Approved Production Usage`)
    }
  }

  const hasApprovedUsage = productionUsageNames.some((name) =>
    isApprovedProductionUsage(name, normalized) && new RegExp(`\\b${name}\\b`).test(source)
  )
  if (hasApprovedUsage) {
    if (fullyMigratedProductionPages.has(normalized)) {
      failures.push(...validateApprovedProductionLegacyUsage(normalized, source))
    } else if (partialMigrationRules.has(normalized)) {
      const rule = partialMigrationRules.get(normalized)
      for (const name of expectedExportNames) {
        if (new RegExp(`\\b${name}\\b`).test(source) && !rule.approvedComponents.has(name)) {
          fail(`${relative(repoDir, path)} references ${name} outside its partial migration boundary`)
        }
      }
    } else if (sharedComponentMigrationRules.has(normalized)) {
      const rule = sharedComponentMigrationRules.get(normalized)
      for (const name of expectedExportNames) {
        if (new RegExp(`\\b${name}\\b`).test(source) && !rule.approvedComponents.has(name)) {
          fail(`${relative(repoDir, path)} references ${name} outside its shared component migration boundary`)
        }
      }
    } else {
      fail(`${relative(repoDir, path)} uses an approved production component without a page migration boundary`)
    }
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
  if (name === 'BaseTooltip' && forbiddenPortal.test(source)) {
    fail('BaseTooltip must not use any Portal or Teleport form')
  }
}

if (failures.length > 0) {
  console.error('V2 support components validation failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log(`V2 support components validation passed (${supportNames.length} support components, ${expectedExportNames.length} total exports).`)
