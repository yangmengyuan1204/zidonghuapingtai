import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const repoDir = resolve(frontendDir, '..')
const baseDir = join(frontendDir, 'src', 'components', 'v2', 'base')
const labPath = join(frontendDir, 'src', 'dev', 'V2BaseComponentsLab.vue')
const indexPath = join(baseDir, 'index.js')
const tokenPath = join(frontendDir, 'src', 'styles', 'v2', 'tokens.component.css')
const resourceNames = ['BaseSelect', 'BaseTextarea', 'BaseTable']
const approvedProductionUsage = new Map([
  ['BaseSelect', new Set([
    'src/components/AppFormDialog.vue', 'src/components/AppShell.vue',
    'src/views/ApiCasesView.vue', 'src/views/ApiHarvesterView.vue', 'src/views/DataScriptsView.vue',
    'src/views/RequirementVerificationView.vue', 'src/views/SystemRegressionView.vue',
  ])],
  ['BaseTable', new Set(['src/views/ApiCasesView.vue', 'src/views/SystemRegressionView.vue'])],
  ['BaseTextarea', new Set([
    'src/components/AppFormDialog.vue', 'src/components/data-scripts/DataAgentWorkspace.vue',
    'src/components/data-scripts/DataScriptRunner.vue', 'src/views/RequirementVerificationView.vue',
    'src/views/SystemRegressionView.vue',
  ])],
])
const failures = []

function fail(message) {
  failures.push(message)
}

function read(path) {
  return readFileSync(path, 'utf8')
}

function walkFiles(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? walkFiles(path) : [path]
  })
}

export function isApprovedResourceProductionUsage(componentName, normalizedPath) {
  return approvedProductionUsage.get(componentName)?.has(normalizedPath) ?? false
}

function styleBlocks(source) {
  return [...source.matchAll(/<style\b([^>]*)>([\s\S]*?)<\/style>/gi)]
    .map(([, attributes, css]) => ({ attributes, css }))
}

function staticClassTokens(source) {
  return [...source.matchAll(/\bclass\s*=\s*["']([^"']+)["']/g)]
    .flatMap(([, value]) => value.split(/\s+/))
    .filter(Boolean)
}

export function validateResourceSource(name, source) {
  const issues = []
  const add = (message) => issues.push(`${name}: ${message}`)
  const styles = styleBlocks(source)
  const forbiddenLegacyClasses = new Set([
    'btn', 'badge', 'field', 'panel', 'pagination', 'table-wrap', 'empty', 'loading',
  ])

  if ((source.match(/^\s*<template>\s*$/gm) || []).length !== 1) add('must contain exactly one root template block')
  if (!/<script\s+setup\b/.test(source)) add('must use script setup')
  if (styles.length !== 1 || !/\bscoped\b/.test(styles[0]?.attributes || '')) {
    add('must contain exactly one scoped style block')
  }
  if (/\bv-html\b/.test(source)) add('must not use v-html')
  if (/(?:vue-router|pinia|axios|stores\/|api\/|\bfetch\s*\(|\bXMLHttpRequest\b|localStorage|sessionStorage)/i.test(source)) {
    add('must not depend on Router, Store, API, network, or browser storage')
  }
  if (staticClassTokens(source).some((token) => forbiddenLegacyClasses.has(token))) {
    add('must not use legacy classes')
  }

  for (const { css } of styles) {
    if (/(?:#[0-9a-f]{3,8}\b|rgba?\(|hsla?\()/i.test(css)) add('must not use raw colors')
    if (/var\(\s*--(?!v2-)[a-z0-9-]+/i.test(css)) add('must only consume --v2-* custom properties')
    if (/(^|[},]\s*)(?::root|html|body)(?=$|[\s,{.:#[>+~])/im.test(css)) add('must not style global selectors')
    if (/\.(?:btn|badge|field|panel|pagination|table-wrap|empty|loading)(?=$|[\s,{.:#[>+~])/im.test(css)) {
      add('must not style legacy selectors')
    }
  }

  return issues
}

const invalidSample = `
<template><div class="field" v-html="unsafe"></div></template>
<script setup>import axios from 'axios'; axios('/api/demo')</script>
<style scoped>.field { color: #fff; background: var(--legacy-surface); }</style>
`
const selfCheckIssues = validateResourceSource('SelfCheck', invalidSample).join('\n')
for (const expectation of ['v-html', 'Router, Store, API', 'legacy classes', 'raw colors', '--v2-', 'legacy selectors']) {
  if (!selfCheckIssues.includes(expectation)) fail(`validator self-check did not detect ${expectation}`)
}

const sources = new Map()
for (const name of resourceNames) {
  const path = join(baseDir, `${name}.vue`)
  if (!existsSync(path)) {
    fail(`${relative(repoDir, path)} is missing`)
    continue
  }
  const source = read(path)
  sources.set(name, source)
  failures.push(...validateResourceSource(name, source))
}

if (!existsSync(indexPath)) {
  fail('base/index.js is missing')
} else {
  const indexSource = read(indexPath)
  for (const name of resourceNames) {
    const imported = new RegExp(`import\\s+${name}\\s+from\\s+['"]\\./${name}\\.vue['"]`).test(indexSource)
    const exported = new RegExp(`export\\s*\\{[^}]*\\b${name}\\b[^}]*\\}`, 's').test(indexSource)
    if (!imported || !exported) fail(`base/index.js must import and export ${name}`)
  }
}

if (!existsSync(tokenPath)) {
  fail('tokens.component.css is missing')
} else {
  const tokenSource = read(tokenPath)
  const requiredTokens = [
    '--v2-select-height', '--v2-select-surface', '--v2-select-border', '--v2-select-focus-ring',
    '--v2-textarea-min-height', '--v2-textarea-surface', '--v2-textarea-border', '--v2-textarea-focus-ring',
    '--v2-table-cell-padding-x', '--v2-table-cell-padding-y', '--v2-table-header-text',
    '--v2-table-radius', '--v2-table-focus-ring',
  ]
  for (const token of requiredTokens) {
    if (!new RegExp(`${token.replaceAll('-', '\\-')}\\s*:`).test(tokenSource)) fail(`missing component token ${token}`)
  }
}

if (!existsSync(labPath)) {
  fail('Component Lab is missing')
} else {
  const labSource = read(labPath)
  for (const name of resourceNames) {
    if (!new RegExp(`\\b${name}\\b`).test(labSource)) fail(`Component Lab must import and render ${name}`)
  }
  const requiredScenarios = [
    'select-default', 'select-label', 'select-placeholder', 'select-selected', 'select-hover',
    'select-focus', 'select-disabled', 'select-required', 'select-error', 'select-long', 'select-narrow',
    'textarea-default', 'textarea-label', 'textarea-placeholder', 'textarea-focus', 'textarea-disabled',
    'textarea-readonly', 'textarea-error', 'textarea-maxlength', 'textarea-long', 'textarea-narrow',
    'table-normal', 'table-dense', 'table-long', 'table-method-status', 'table-actions',
    'table-empty', 'table-loading', 'table-overflow',
  ]
  for (const scenario of requiredScenarios) {
    if (!labSource.includes(`data-testid="${scenario}"`)) fail(`Component Lab is missing ${scenario}`)
  }
}

if (sources.has('BaseSelect')) {
  const source = sources.get('BaseSelect')
  const requirements = [
    [/<select\b/, 'native select'],
    [/defineProps\([\s\S]*\bmodelValue\b/, 'modelValue prop'],
    [/\boptions\b/, 'options contract'],
    [/\boptionValue\b/, 'optionValue contract'],
    [/\boptionLabel\b/, 'optionLabel contract'],
    [/:disabled="disabled"/, 'disabled binding'],
    [/:required="required"/, 'required binding'],
    [/:aria-invalid=/, 'aria-invalid'],
    [/:aria-describedby=/, 'aria-describedby'],
    [/@focus=/, 'focus event'],
    [/emit\(['"]update:modelValue['"]/, 'v-model emit'],
    [/selectedOption\?\._value\s*\?\?\s*event\.target\.value/, 'typed option value preservation'],
  ]
  for (const [pattern, label] of requirements) if (!pattern.test(source)) fail(`BaseSelect must implement ${label}`)
  if (/(?:multiple|virtual|remote|async|tree|search)/i.test(source)) fail('BaseSelect contains a prohibited advanced feature')
}

if (sources.has('BaseTextarea')) {
  const source = sources.get('BaseTextarea')
  const requirements = [
    [/<textarea\b/, 'native textarea'],
    [/:rows="rows"/, 'rows binding'],
    [/:maxlength="maxlength"/, 'maxlength binding'],
    [/:disabled="disabled"/, 'disabled binding'],
    [/:readonly="readonly"/, 'readonly binding'],
    [/:aria-invalid=/, 'aria-invalid'],
    [/v-if="hasMaxlength"/, 'conditional maxlength counter'],
    [/String\(props\.modelValue \?\? ''\)\.length/, 'real string length counter'],
    [/emit\(['"]update:modelValue['"]/, 'v-model emit'],
  ]
  for (const [pattern, label] of requirements) if (!pattern.test(source)) fail(`BaseTextarea must implement ${label}`)
  if (/(?:markdown|codeEditor|autoResize)/i.test(source)) fail('BaseTextarea contains a prohibited advanced feature')
}

if (sources.has('BaseTable')) {
  const source = sources.get('BaseTable')
  const requirements = [
    [/<table\b/, 'semantic table'], [/<thead\b/, 'semantic thead'], [/<tbody\b/, 'semantic tbody'],
    [/\bcolumns\b/, 'columns prop'], [/\brows\b/, 'rows prop'], [/\browKey\b/, 'rowKey prop'],
    [/\bariaLabel\b/, 'ariaLabel prop'], [/\bloading\b/, 'loading prop'], [/\bminContentWidth\b/, 'min content width'],
    [/:name="column\.key"/, 'named cell slots'], [/:name="`header-\$\{column\.key\}`"/, 'named header slots'],
    [/name="empty"/, 'empty slot'], [/name="loading"/, 'loading slot'],
    [/overflow-x:\s*auto/, 'responsive horizontal overflow'],
  ]
  for (const [pattern, label] of requirements) if (!pattern.test(source)) fail(`BaseTable must implement ${label}`)
  if (/(?:v-html|sortBy|filterBy|pagination|selectedRows|inlineEdit|virtualScroll|resizeColumn|dragSort)/i.test(source)) {
    fail('BaseTable contains a prohibited feature')
  }
}

const productionFiles = walkFiles(join(frontendDir, 'src'))
  .filter((path) => /\.(?:vue|js)$/i.test(path))
  .filter((path) => {
    const normalized = relative(frontendDir, path).replaceAll('\\', '/')
    return !normalized.startsWith('src/dev/') && !normalized.startsWith('src/components/v2/base/')
  })
for (const path of productionFiles) {
  const source = read(path)
  const normalized = relative(frontendDir, path).replaceAll('\\', '/')
  for (const name of resourceNames) {
    if (new RegExp(`\\b${name}\\b`).test(source) && !isApprovedResourceProductionUsage(name, normalized)) {
      fail(`${relative(repoDir, path)} references ${name} outside Approved Production Usage`)
    }
  }
}

if (isApprovedResourceProductionUsage('BaseTextarea', 'src/views/ProjectsView.vue')) {
  fail('validator self-check allows BaseTextarea outside its approved shared component')
}

if (failures.length > 0) {
  console.error('V2 resource foundation validation failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('V2 resource foundation validation passed (BaseSelect, BaseTextarea, BaseTable, Lab, tokens, production isolation).')
