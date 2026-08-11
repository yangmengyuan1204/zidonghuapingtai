import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const repoDir = resolve(frontendDir, '..')
const viewPath = join(frontendDir, 'src', 'views', 'ApiCasesView.vue')

const protectedFiles = new Map([
  ['src/api/modules/apiCases.js', '1931c30fea806f12a9d01dc99bdc3f7dee768c493fb95c3101f041b4c4603ea8'],
  ['src/router/index.js', '3e4f2b838d35836ea3a0e35ec53676f417d6fa72a9185a75e9d51b538b3edbe8'],
  ['src/stores/auth.js', '0c1401d4fe0b66e0dce15cb190a1b266b8d6a96ada4191634e6791892e17aa8d'],
  ['src/stores/app.js', '7ed84fa1928bc86bd17ac001dc63e3f3d623dca7426d103859248c60793ab93b'],
  ['src/stores/toast.js', '1ae4737ce5d593bc60ba9a3af02e33c1c6cfb0c8c06fa9377a5d66f3f81d5def'],
  ['src/components/AppTable.vue', 'aacdcf92d0dbe8ba72b4daf8ef9345ed5dfdf165fd9abc8e6274567df4123788'],
  ['src/components/AppModal.vue', '6feeebd08839bed4576b33c57f9e2c146e607af023f77f313c24dde744e5d7a0'],
  ['src/components/AppToast.vue', 'e656febea1d08e28e4cd7d33fb53d4316d3e97adff509fb9ce83658b22f44991'],
])

const protectedFunctions = new Map([
  ['loadApiCases', '38a6cf2153b5c08db80649c330d1f88149d0e355e978037ab532341e435094cc'],
  ['onProjectChange', '2bb84d08f8293b9538af1ebac33f8f7bd12b3bb706a0c90609e87b603fd6ab7f'],
  ['onEnvChange', '93cdb47b38e3f6b9b9948c2a7045d2106afe6b7a4cffc6ce43592b767928d56a'],
  ['goPage', '8bea66c930efea33fdaeda4f3d72a80933dc946b36cf97a98641dabbfa677702'],
  ['toggleSelect', 'f8386050aae03aa2f6af257208155a6075986540253e5ab5d9a9acfab56d4695'],
  ['submitForm', '37022223c96822139c00342c190aea40158849a38b9f33100bc390681d0f2a9f'],
  ['onDelete', 'dd5caa6f9fbaf7ce957577d935ea03497fd7717d8e7e15d16ea80b1280d249f4'],
  ['onRun', 'b3108b486d4c4b4808d9e1f582de507a12edf1fad87d1097b4f1c514121a8fd1'],
  ['submitBatch', '600e4f13e97103071ce1320d027ef3fd4403a938c983a79ea44a3cbb41e887aa'],
  ['parseJsonText', 'e33809f03061ba7910df485348bbf773e4771a63abb755262938064a59211214'],
])

const protectedTemplateFragments = new Map([
  ['CRUD dialog', 'a4043d2ebe01af380e1a036aa69782739ef4d20f3418ebeb0416cbcaf0731414'],
  ['batch dialog', '2996d586a2fa166edbc1ac6befe7a4a94cc81f4997e0d7c59ed7e267a85fca63'],
])

const failures = []

function fail(message) {
  failures.push(message)
}

function read(path) {
  return readFileSync(path, 'utf8')
}

function digest(value) {
  return createHash('sha256').update(value).digest('hex')
}

function templateBlock(source) {
  const start = source.indexOf('<template>')
  const end = source.indexOf('<script setup>')
  return start === -1 || end === -1 ? '' : source.slice(start + '<template>'.length, end)
}

function scriptBlock(source) {
  return source.match(/<script\s+setup>([\s\S]*?)<\/script>/)?.[1] ?? ''
}

function styleBlocks(source) {
  return [...source.matchAll(/<style\b([^>]*)>([\s\S]*?)<\/style>/gi)]
    .map(([, attributes, css]) => ({ attributes, css }))
}

function componentBlocks(template, name) {
  return [...template.matchAll(new RegExp(`<${name}\\b[\\s\\S]*?<\\/${name}>`, 'g'))]
    .map(([block]) => block)
}

function openingTags(template, name) {
  return [...template.matchAll(new RegExp(`<${name}\\b[^>]*>`, 'g'))]
    .map(([tag]) => tag)
}

function staticClassTokens(source) {
  return [...source.matchAll(/(?<!:)class=["']([^"']+)["']/g)]
    .flatMap(([, value]) => value.split(/\s+/))
    .filter(Boolean)
}

function dynamicClassTokens(source) {
  return [...source.matchAll(/:class\s*=\s*"([^"]*)"|:class\s*=\s*'([^']*)'/g)]
    .flatMap((match) => [...(match[1] ?? match[2] ?? '').matchAll(/['"]([^'"]+)['"]/g)])
    .flatMap(([, value]) => value.split(/\s+/))
    .filter(Boolean)
}

function extractFunction(source, name) {
  const signature = `function ${name}`
  const start = source.indexOf(signature)
  if (start === -1) return ''
  const openingBrace = source.indexOf('{', start)
  let depth = 0
  for (let index = openingBrace; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1
    if (source[index] === '}') depth -= 1
    if (depth === 0) return source.slice(start, index + 1)
  }
  return ''
}

function baseImports(script) {
  const match = script.match(/import\s*\{([^}]*)\}\s*from\s*['"]\.\.\/components\/v2\/base\/index\.js['"]/) 
  return new Set(
    (match?.[1] ?? '')
      .split(',')
      .map((name) => name.trim())
      .filter(Boolean),
  )
}

function validateMigratedRegionIsolation(source) {
  const issues = []
  const forbidden = new Set(['btn', 'badge', 'pagination'])
  const usedLegacyClasses = [...staticClassTokens(source), ...dynamicClassTokens(source)]
    .filter((className) => forbidden.has(className))
  if (usedLegacyClasses.length > 0) {
    issues.push(`migrated regions use legacy classes ${[...new Set(usedLegacyClasses)].join(', ')}`)
  }

  for (const block of styleBlocks(source)) {
    if (!/\bscoped\b/i.test(block.attributes)) issues.push('page style must remain scoped')
    if (/\.(?:btn|badge|pagination)(?=$|[\s,{.:#[>+~])/im.test(block.css)) {
      issues.push('page CSS styles a migrated legacy selector')
    }
    if (/(?:#[0-9a-f]{3,8}\b|rgba?\(|hsla?\()/i.test(block.css)) {
      issues.push('page CSS contains a raw color')
    }
    if (/:root\b|(^|[},]\s*)(?:html|body|table)(?=$|[\s,{.:#[>+~])/im.test(block.css)) {
      issues.push('page CSS contains a forbidden shared selector')
    }
    if (/var\(\s*--(?!v2-)[a-z0-9-]+/i.test(block.css)) {
      issues.push('page CSS references a non-V2 custom property')
    }
    const selectors = [...block.css.matchAll(/([^{}]+)\{/g)]
      .map(([, selector]) => selector.trim())
      .filter((selector) => !selector.startsWith('@'))
    if (selectors.some((selector) => selector.split(',').some((part) => {
      const normalized = part.trim()
      return normalized !== '.v2-api-cases' && !normalized.startsWith('.v2-api-cases-')
    }))) {
      issues.push('page CSS contains a selector outside v2-api-cases-*')
    }
  }

  return issues
}

function requireBlock(blocks, eventExpression, label, requirements = []) {
  const block = blocks.find((candidate) => candidate.includes(`@click="${eventExpression}"`))
  if (!block) {
    fail(`${label} is not mapped to BaseButton`)
    return
  }
  for (const [pattern, message] of requirements) {
    if (!pattern.test(block)) fail(`${label} ${message}`)
  }
}

if (!existsSync(viewPath)) {
  fail(`missing ${relative(repoDir, viewPath)}`)
}

for (const [path, expectedDigest] of protectedFiles) {
  const absolutePath = join(frontendDir, path)
  if (!existsSync(absolutePath)) {
    fail(`missing protected file frontend/${path}`)
  } else if (digest(read(absolutePath)) !== expectedDigest) {
    fail(`protected contract changed in frontend/${path}`)
  }
}

const source = existsSync(viewPath) ? read(viewPath) : ''
const template = templateBlock(source)
const script = scriptBlock(source)
const imports = baseImports(script)

for (const name of ['BaseButton', 'BaseBadge', 'BaseCheckbox', 'BasePagination']) {
  if (!imports.has(name)) fail(`ApiCasesView must import ${name} from the V2 base index`)
}
for (const name of [
  'BaseDropdown',
  'BaseDropdownItem',
  'BaseSkeleton',
  'BaseEmptyState',
  'BaseErrorState',
  'BaseTooltip',
]) {
  if (new RegExp(`\\b${name}\\b`).test(source)) fail(`ApiCasesView must not introduce ${name}`)
}

const buttonBlocks = componentBlocks(template, 'BaseButton')
if (buttonBlocks.length !== 6) fail('ApiCasesView must contain exactly six mapped BaseButton declarations')
requireBlock(buttonBlocks, 'openBatchRun', 'Batch Execute', [
  [/type="button"/, 'must use type=button'],
  [/variant="secondary"/, 'must remain secondary'],
  [/:disabled="selectedIds\.size === 0"/, 'must preserve its disabled condition'],
  [/批量执行/, 'must preserve its label'],
])
requireBlock(buttonBlocks, 'openForm(null)', 'Create', [
  [/type="button"/, 'must use type=button'],
  [/variant="primary"/, 'must remain primary'],
  [/v-if="auth\.isAdmin"/, 'must preserve admin visibility'],
  [/新增接口用例/, 'must preserve its label'],
])
requireBlock(buttonBlocks, 'onRun(row)', 'Execute', [
  [/type="button"/, 'must use type=button'],
  [/variant="primary"/, 'must remain primary'],
  [/size="compact"/, 'must use the compact row-action size'],
])
requireBlock(buttonBlocks, 'onCopy(row)', 'Copy', [
  [/type="button"/, 'must use type=button'],
  [/variant="secondary"/, 'must remain secondary'],
  [/size="compact"/, 'must use the compact row-action size'],
])
requireBlock(buttonBlocks, 'openForm(row)', 'Edit', [
  [/type="button"/, 'must use type=button'],
  [/variant="secondary"/, 'must remain secondary'],
  [/size="compact"/, 'must use the compact row-action size'],
])
requireBlock(buttonBlocks, 'onDelete(row)', 'Delete', [
  [/type="button"/, 'must use type=button'],
  [/variant="danger"/, 'must use the danger variant'],
  [/size="compact"/, 'must use the compact row-action size'],
])
if (/<button\b/i.test(template)) fail('ApiCasesView still contains a native page-level button')

const badgeBlocks = componentBlocks(template, 'BaseBadge')
if (badgeBlocks.length !== 2) fail('ApiCasesView must contain exactly two mapped BaseBadge declarations')
if (!badgeBlocks.some((block) => /tone="neutral"/.test(block) && /badgeText\(row\.method\)/.test(block))) {
  fail('HTTP Method must use BaseBadge without changing its text mapping')
}
if (!badgeBlocks.some((block) => /:tone="apiCaseStatusTone\(row\.status\)"/.test(block) && /apiCaseStatusText\(row\.status\)/.test(block))) {
  fail('Case Status must use BaseBadge with the existing status text mapping')
}
if (!/function\s+apiCaseStatusTone\([^)]*\)[\s\S]*apiCaseStatusClass\(/.test(script)) {
  fail('Case Status tone must derive from the existing apiCaseStatusClass mapping')
}

const checkboxTags = openingTags(template, 'BaseCheckbox')
if (checkboxTags.length !== 1) fail('ApiCasesView must contain exactly one row BaseCheckbox declaration')
const checkboxTag = checkboxTags[0] ?? ''
if (!/:model-value="selectedIds\.has\(row\.id\)"/.test(checkboxTag)) {
  fail('row BaseCheckbox must remain controlled by selectedIds')
}
if (!/@change="toggleSelect\(row\.id, \$event\)"/.test(checkboxTag)) {
  fail('row BaseCheckbox must preserve the existing toggleSelect event contract')
}
if (!/:aria-label="`[^`]*(?:row\.case_name|row\.id)[^`]*`"/.test(checkboxTag)) {
  fail('row BaseCheckbox must have a case-specific accessible name')
}
if (/<input\b[^>]*type=["']checkbox["']/i.test(template)) {
  fail('ApiCasesView still contains the legacy native row checkbox')
}
if (/\b(?:selectAll|indeterminate)\b/.test(source)) fail('ApiCasesView must not add select-all behavior')

const paginationTags = openingTags(template, 'BasePagination')
if (paginationTags.length !== 1) fail('ApiCasesView must contain exactly one BasePagination declaration')
const paginationTag = paginationTags[0] ?? ''
for (const [pattern, message] of [
  [/:page="page"/, 'must receive page'],
  [/:total="total"/, 'must receive total'],
  [/:page-size="pageSize"/, 'must receive pageSize'],
  [/:sibling-count="2"/, 'must use siblingCount=2'],
  [/@change="goPage"/, 'must reuse goPage'],
  [/aria-label=/, 'must expose an aria-label'],
]) {
  if (!pattern.test(paginationTag)) fail(`BasePagination ${message}`)
}
if (!/class="v2-api-cases-+[^"']*pagination/.test(template)) {
  fail('pagination layout must use a v2-api-cases-* class')
}
if (!/\{\{\s*total\s*\}\}[\s\S]*\{\{\s*page\s*\}\}[\s\S]*\{\{\s*totalPages\s*\}\}/.test(template)) {
  fail('pagination must preserve total and current-page summary text')
}

if (!/const\s+pageSize\s*=\s*20\b/.test(script)) fail('pageSize must remain 20')
if (!/const\s+selectedIds\s*=\s*ref\(new Set\(\)\)/.test(script)) fail('selectedIds must remain a Set')
if ((script.match(/selectedIds\.value\s*=\s*new Set\(\)/g) ?? []).length !== 3) {
  fail('selectedIds reset points changed')
}

for (const [name, expectedDigest] of protectedFunctions) {
  const functionSource = extractFunction(script, name)
  if (!functionSource) fail(`missing protected function ${name}`)
  else if (digest(functionSource) !== expectedDigest) fail(`protected function ${name} changed`)
}
const mountedStart = script.indexOf('onMounted(async () => {')
const mountedBlock = mountedStart === -1 ? '' : script.slice(mountedStart).trim()
if (digest(mountedBlock) !== 'd28609dcc5a4502a5dc0491001c906b8360befc04c991c1cc845c73b743c83ff') {
  fail('ApiCasesView mounted lifecycle changed')
}

if (openingTags(template, 'BaseSelect').length !== 2 || /<select\b/i.test(template)) {
  fail('Project and Environment filter boundary regressed after approved foundation integration')
}
const dialogTags = [...template.matchAll(/<AppFormDialog\b[\s\S]*?\/>/g)].map(([block]) => block)
if (dialogTags.length !== 2) fail('CRUD and Batch AppFormDialog declarations must remain unchanged')
for (const [index, block] of dialogTags.entries()) {
  const expected = [...protectedTemplateFragments.values()][index]
  if (digest(block) !== expected) fail(`${index === 0 ? 'CRUD' : 'Batch'} AppFormDialog changed`)
}
if (openingTags(template, 'BaseTable').length !== 1 || /\bAppTable\b/.test(source)) {
  fail('approved BaseTable integration regressed')
}

if (/\bv-html\b/.test(source)) fail('ApiCasesView must not add v-html')
if (/<input\b[^>]*type=["']search["']|\bBaseDropdown\b|\bselectAll\b/i.test(template)) {
  fail('ApiCasesView adds Search, Dropdown, or select-all behavior')
}
if (/v-if="loading"|<BaseSkeleton\b|<BaseEmptyState\b|<BaseErrorState\b/.test(template)) {
  fail('ApiCasesView adds Loading, Empty, or Error UI')
}

failures.push(...validateMigratedRegionIsolation(source))

const selfCheckSource = `
<template><BaseButton class="btn">Unsafe</BaseButton></template>
<script setup></script>
<style scoped>.pagination { color: #fff; }</style>
`
const selfCheckIssues = validateMigratedRegionIsolation(selfCheckSource)
for (const expected of ['legacy classes', 'legacy selector', 'raw color', 'outside v2-api-cases-*']) {
  if (!selfCheckIssues.some((issue) => issue.includes(expected))) {
    fail(`validator self-check did not detect ${expected}`)
  }
}

if (failures.length > 0) {
  console.error('V2 API Cases direct mapping validation failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('V2 API Cases direct mapping validation passed (Button, Badge, Checkbox, Pagination, partial migration boundary).')
