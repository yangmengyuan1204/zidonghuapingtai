import { createHash } from 'node:crypto'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const repoDir = resolve(frontendDir, '..')
const apiCasesPath = join(frontendDir, 'src', 'views', 'ApiCasesView.vue')
const formDialogPath = join(frontendDir, 'src', 'components', 'AppFormDialog.vue')
const supportValidatorPath = join(scriptDir, 'validate-v2-support-components.mjs')
const resourceValidatorPath = join(scriptDir, 'validate-v2-resource-foundation.mjs')
const failures = []

const protectedFiles = new Map([
  ['src/api/modules/apiCases.js', '1931c30fea806f12a9d01dc99bdc3f7dee768c493fb95c3101f041b4c4603ea8'],
  ['src/router/index.js', '3e4f2b838d35836ea3a0e35ec53676f417d6fa72a9185a75e9d51b538b3edbe8'],
  ['src/stores/auth.js', '0c1401d4fe0b66e0dce15cb190a1b266b8d6a96ada4191634e6791892e17aa8d'],
  ['src/stores/app.js', '7ed84fa1928bc86bd17ac001dc63e3f3d623dca7426d103859248c60793ab93b'],
  ['src/stores/toast.js', '1ae4737ce5d593bc60ba9a3af02e33c1c6cfb0c8c06fa9377a5d66f3f81d5def'],
  ['src/components/AppTable.vue', 'aacdcf92d0dbe8ba72b4daf8ef9345ed5dfdf165fd9abc8e6274567df4123788'],
  ['src/components/AppModal.vue', '6feeebd08839bed4576b33c57f9e2c146e607af023f77f313c24dde744e5d7a0'],
  ['src/components/AppToast.vue', 'e656febea1d08e28e4cd7d33fb53d4316d3e97adff509fb9ce83658b22f44991'],
  ['src/views/ProjectsView.vue', '45f15545ddbbc374e66a44a980c1929dc0f61a5ab74bd6ca4e3b0ef510132ff8'],
  ['src/views/UsersView.vue', 'ede8095981cc8afb2e51da2df0957b8fdad26e75d223eb0413f3d604b1d31b03'],
  ['src/views/UiCasesView.vue', 'a26656ad0d44c4f6dda57e66b350ee292efb7af391462ea4b78eb8572daf6b16'],
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

const approvedProductionUsage = new Map([
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
])

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

function openingTags(template, name) {
  return [...template.matchAll(new RegExp(`<${name}\\b[^>]*>`, 'g'))].map(([tag]) => tag)
}

function walkFiles(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry)
    return statSync(path).isDirectory() ? walkFiles(path) : [path]
  })
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

export function validateProductionUsage(componentName, normalizedPath) {
  return approvedProductionUsage.get(componentName)?.has(normalizedPath) ?? false
}

export function validateSharedDialog(source) {
  const issues = []
  const template = templateBlock(source)
  const script = scriptBlock(source)
  const textareaTags = openingTags(template, 'BaseTextarea')

  if (/<textarea\b/i.test(template)) issues.push('AppFormDialog still renders a native textarea')
  if (textareaTags.length !== 1) issues.push('AppFormDialog must contain exactly one BaseTextarea branch')
  if (!/import\s*\{[^}]*\bBaseTextarea\b[^}]*\}\s*from\s*['"]\.\/v2\/base\/index\.js['"]/s.test(script)) {
    issues.push('AppFormDialog must import BaseTextarea from the V2 base index')
  }

  const tag = textareaTags[0] ?? ''
  const requiredBindings = [
    [/v-else-if="field\.type === 'textarea'"/, 'textarea type branch'],
    [/:id="field\.name"/, 'id mapping'],
    [/v-model="form\[field\.name\]"/, 'model mapping'],
    [/:name="field\.name"/, 'name mapping'],
    [/:rows="field\.rows \|\| 3"/, 'rows mapping'],
    [/:maxlength="field\.maxlength"/, 'maxlength mapping'],
    [/:required="Boolean\(field\.required\)"/, 'required mapping'],
    [/:disabled="Boolean\(field\.disabled\)"/, 'disabled mapping'],
    [/:readonly="Boolean\(field\.readonly\)"/, 'readonly mapping'],
    [/:placeholder="field\.placeholder \|\| ''"/, 'placeholder mapping'],
    [/:error="field\.error \|\| ''"/, 'validation error mapping'],
    [/:help="field\.help \|\| ''"/, 'help text mapping'],
  ]
  for (const [pattern, label] of requiredBindings) {
    if (!pattern.test(tag)) issues.push(`AppFormDialog must preserve ${label}`)
  }

  const propNames = [...script.matchAll(/^\s{2}([A-Za-z][A-Za-z0-9]*):\s*\{/gm)].map(([, name]) => name)
  const expectedProps = ['visible', 'title', 'fields', 'values', 'submitLabel']
  if (propNames.join(',') !== expectedProps.join(',')) issues.push('AppFormDialog public props changed')
  if (!/defineEmits\(\[['"]close['"],\s*['"]submit['"]\]\)/.test(script)) {
    issues.push('AppFormDialog emits changed')
  }
  if (!/obj\[field\.name\]\s*=\s*props\.values\?\.\[field\.name\]\s*\?\?\s*field\.default\s*\?\?\s*''/.test(script)) {
    issues.push('AppFormDialog form reset mapping changed')
  }
  if (!/function\s+handleSubmit\(\)\s*\{\s*emit\(['"]submit['"],\s*\{\s*\.\.\.form\.value\s*\}\)\s*\}/s.test(script)) {
    issues.push('AppFormDialog submit contract changed')
  }
  if (/(?:ApiCasesView|ProjectsView|UsersView|UiCasesView|route\.|routeName|consumer|window\.location)/.test(script)) {
    issues.push('AppFormDialog adds a consumer-specific branch')
  }
  return issues
}

for (const [path, expectedDigest] of protectedFiles) {
  const absolutePath = join(frontendDir, path)
  if (!existsSync(absolutePath)) fail(`missing protected file frontend/${path}`)
  else if (digest(read(absolutePath)) !== expectedDigest) fail(`protected contract changed in frontend/${path}`)
}

if (!existsSync(apiCasesPath)) fail('missing frontend/src/views/ApiCasesView.vue')
if (!existsSync(formDialogPath)) fail('missing frontend/src/components/AppFormDialog.vue')

const apiCasesSource = existsSync(apiCasesPath) ? read(apiCasesPath) : ''
const apiCasesTemplate = templateBlock(apiCasesSource)
const apiCasesScript = scriptBlock(apiCasesSource)
const formDialogSource = existsSync(formDialogPath) ? read(formDialogPath) : ''

for (const name of ['BaseSelect', 'BaseTable']) {
  if (!new RegExp(`\\b${name}\\b`).test(apiCasesScript)) fail(`ApiCasesView must import ${name}`)
}
if (/\bAppTable\b/.test(apiCasesSource)) fail('ApiCasesView still references AppTable')
if (/<select\b/i.test(apiCasesTemplate)) fail('ApiCasesView still renders a native select')

const selectTags = openingTags(apiCasesTemplate, 'BaseSelect')
if (selectTags.length !== 2) fail('ApiCasesView must contain exactly two BaseSelect declarations')
const projectSelect = selectTags.find((tag) => /@change="onProjectChange"/.test(tag)) ?? ''
const environmentSelect = selectTags.find((tag) => /@change="onEnvChange"/.test(tag)) ?? ''
for (const [tag, label, requirements] of [
  [projectSelect, 'Project Select', [/:model-value="filterProjectId"/, /:options="projects"/, /option-value="id"/, /option-label="name"/, /placeholder="全部"/]],
  [environmentSelect, 'Environment Select', [/:model-value="filterEnvId"/, /:options="envs"/, /option-value="id"/, /option-label="env_name"/, /placeholder="全部"/]],
]) {
  if (!tag) fail(`${label} is not mapped to BaseSelect`)
  for (const requirement of requirements) if (!requirement.test(tag)) fail(`${label} contract changed`)
}

const tableTags = openingTags(apiCasesTemplate, 'BaseTable')
if (tableTags.length !== 1) fail('ApiCasesView must contain exactly one BaseTable declaration')
const tableTag = tableTags[0] ?? ''
for (const [pattern, label] of [
  [/:columns="columns"/, 'columns'],
  [/:rows="rows"/, 'rows'],
  [/row-key="id"/, 'rowKey'],
  [/:loading="loading"/, 'loading'],
  [/:min-content-width=/, 'responsive minimum content width'],
  [/aria-label=/, 'accessible name'],
]) {
  if (!pattern.test(tableTag)) fail(`BaseTable must preserve ${label}`)
}
for (const slotName of ['select', 'id', 'project_id', 'env_id', 'case_name', 'method', 'url', 'status', 'actions']) {
  if (!new RegExp(`<template\\s+#${slotName}=`).test(apiCasesTemplate)) fail(`BaseTable is missing named slot ${slotName}`)
}
if (!/function\s+shortText\(value,\s*length\s*=\s*140\)\s*\{[\s\S]*?String\(value\s*\?\?\s*''\)[\s\S]*?s\.length\s*>\s*length\s*\?\s*s\.slice\(0,\s*length\)\s*\+\s*'\.\.\.'\s*:\s*s[\s\S]*?\}/.test(apiCasesScript)) {
  fail('BaseTable plain-text cells must preserve AppTable short(value, 140) rendering')
}
for (const name of ['BaseBadge', 'BaseButton', 'BaseCheckbox', 'BasePagination']) {
  if (!new RegExp(`<${name}\\b`).test(apiCasesTemplate)) fail(`Phase 5.5B mapping regressed for ${name}`)
}

for (const [name, expectedDigest] of protectedFunctions) {
  const functionSource = extractFunction(apiCasesScript, name)
  if (!functionSource) fail(`missing protected function ${name}`)
  else if (digest(functionSource) !== expectedDigest) fail(`protected function ${name} changed`)
}
const mountedStart = apiCasesScript.indexOf('onMounted(async () => {')
const mountedBlock = mountedStart === -1 ? '' : apiCasesScript.slice(mountedStart).trim()
if (digest(mountedBlock) !== 'd28609dcc5a4502a5dc0491001c906b8360befc04c991c1cc845c73b743c83ff') {
  fail('ApiCasesView mounted lifecycle changed')
}
if (!/const\s+pageSize\s*=\s*20\b/.test(apiCasesScript)) fail('pageSize must remain 20')
if (!/const\s+selectedIds\s*=\s*ref\(new Set\(\)\)/.test(apiCasesScript)) fail('selectedIds must remain a Set')
if ((apiCasesScript.match(/type:\s*['"]textarea['"]/g) ?? []).length !== 5) fail('ApiCases textarea field schema changed')
for (const [fieldName, pattern] of [
  ['headers', /\{\s*name:\s*['"]headers['"],\s*label:\s*['"][^'"]*['"],\s*type:\s*['"]textarea['"],\s*default:\s*['"]\{\}['"]\s*\}/],
  ['params', /\{\s*name:\s*['"]params['"],\s*label:\s*['"][^'"]*['"],\s*type:\s*['"]textarea['"],\s*default:\s*['"]\{\}['"]\s*\}/],
  ['body', /\{\s*name:\s*['"]body['"],\s*label:\s*['"][^'"]*['"],\s*type:\s*['"]textarea['"]\s*\}/],
  ['assert_rule', /\{\s*name:\s*['"]assert_rule['"],\s*label:\s*['"][^'"]*['"],\s*type:\s*['"]textarea['"],\s*default:\s*['"]\{\"status_code\":200,\"extract\":\{\"id\":\"json\.data\.id\"\}\}['"]\s*\}/],
  ['variables', /\{\s*name:\s*['"]variables['"],\s*label:\s*['"][^'"]*['"],\s*type:\s*['"]textarea['"],\s*rows:\s*8,\s*default:\s*'\{\\n  "username": "test_\{\{\$random_int\}\}",\\n  "phone": "\{\{\$random_phone\}\}"\\n\}',?\s*\}/],
]) {
  if (!pattern.test(apiCasesScript)) fail(`ApiCases textarea field contract changed for ${fieldName}`)
}

for (const issue of validateSharedDialog(formDialogSource)) fail(issue)

const consumerExpectations = new Map([
  ['src/views/ApiCasesView.vue', 5],
  ['src/views/ProjectsView.vue', 6],
  ['src/views/UsersView.vue', 0],
  ['src/views/UiCasesView.vue', 1],
])
for (const [path, expectedCount] of consumerExpectations) {
  const source = path === 'src/views/ApiCasesView.vue' ? apiCasesSource : read(join(frontendDir, path))
  const count = (source.match(/type:\s*['"]textarea['"]/g) ?? []).length
  if (count !== expectedCount) fail(`${path} textarea field schema changed`)
  if (/querySelector(?:All)?\([^)]*textarea|getElementById\([^)]*textarea|closest\([^)]*textarea/i.test(source)) {
    fail(`${path} depends on native textarea DOM access`)
  }
  if (/\bBaseTextarea\b/.test(source)) fail(`${path} must not directly import BaseTextarea`)
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
  for (const componentName of approvedProductionUsage.keys()) {
    if (new RegExp(`\\b${componentName}\\b`).test(source) && !validateProductionUsage(componentName, normalized)) {
      fail(`${normalized} references ${componentName} outside Phase 5.5D approval`)
    }
  }
}

for (const [validatorPath, label] of [
  [supportValidatorPath, 'Supporting Validator'],
  [resourceValidatorPath, 'Resource Foundation Validator'],
]) {
  const source = existsSync(validatorPath) ? read(validatorPath) : ''
  for (const [componentName, paths] of approvedProductionUsage) {
    for (const path of paths) {
      if (!source.includes(componentName) || !source.includes(path)) {
        fail(`${label} does not approve ${componentName} at ${path}`)
      }
    }
  }
}

const selfCheckSource = `
<template><textarea v-if="route.name === 'ApiCases'" /></template>
<script setup>
import { BaseTextarea } from './v2/base/index.js'
const props = defineProps({ visible: Boolean, extraMode: Boolean })
const route = { name: 'ApiCasesView' }
</script>
`
const selfCheckIssues = validateSharedDialog(selfCheckSource)
for (const expected of ['native textarea', 'public props changed', 'consumer-specific branch']) {
  if (!selfCheckIssues.some((issue) => issue.includes(expected))) {
    fail(`validator self-check did not detect ${expected}`)
  }
}
if (validateProductionUsage('BaseTextarea', 'src/views/ProjectsView.vue')) {
  fail('validator self-check allows unapproved direct BaseTextarea usage')
}

if (failures.length > 0) {
  console.error('V2 API Cases foundation integration validation failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('V2 API Cases foundation integration validation passed (BaseSelect, BaseTable, shared AppFormDialog BaseTextarea, protected business contracts).')
