import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = resolve(scriptDir, '..')
const repoDir = resolve(frontendDir, '..')
const componentsDir = join(frontendDir, 'src', 'components', 'v2', 'base')

const componentNames = [
  'BaseButton',
  'BaseIconButton',
  'BaseInput',
  'BaseCheckbox',
  'BaseBadge',
  'BaseChip',
  'BaseCard',
]

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

function styleBlocks(source) {
  return [...source.matchAll(/<style\b([^>]*)>([\s\S]*?)<\/style>/gi)]
    .map(([, attributes, css]) => ({ attributes, css }))
}

function staticClassTokens(source) {
  return [...source.matchAll(/(?<!:)class=["']([^"']+)["']/g)]
    .flatMap(([, value]) => value.split(/\s+/))
    .filter(Boolean)
}

const sources = new Map()
for (const name of componentNames) {
  const path = join(componentsDir, `${name}.vue`)
  if (!existsSync(path)) {
    fail(`missing ${relative(repoDir, path)}`)
    continue
  }
  sources.set(name, read(path))
}

const indexPath = join(componentsDir, 'index.js')
if (!existsSync(indexPath)) {
  fail(`missing ${relative(repoDir, indexPath)}`)
} else {
  const indexSource = read(indexPath)
  const exports = [...indexSource.matchAll(
    /export\s*\{\s*default\s+as\s+(Base[A-Za-z]+)\s*\}\s*from\s*['"]\.\/(Base[A-Za-z]+)\.vue['"]/g,
  )].map(([, exported, file]) => ({ exported, file }))
  if (exports.length !== componentNames.length) {
    fail(`index.js must export exactly ${componentNames.length} base components`)
  }
  for (const name of componentNames) {
    if (!exports.some(({ exported, file }) => exported === name && file === name)) {
      fail(`index.js does not correctly export ${name}`)
    }
  }
}

const forbiddenDependency = /(?:from\s+['"][^'"]*(?:vue-router|pinia|axios|stores\/|api\/|services\/)|import\s+['"][^'"]*(?:vue-router|pinia|axios|stores\/|api\/|services\/)|require\s*\(\s*['"][^'"]*(?:vue-router|pinia|axios|stores\/|api\/|services\/)|localStorage|sessionStorage|\bfetch\s*\(|\bXMLHttpRequest\b|\baxios\s*(?:\.|\())/i
const forbiddenLegacyClasses = new Set(['btn', 'field', 'panel', 'badge', 'modal', 'toast'])
const forbiddenRawColor = /(?:#[0-9a-f]{3,8}\b|rgba?\(|hsla?\()/i
const forbiddenGlobalSelector = /(^|[},]\s*)(?::root|html|body|table)(?=$|[\s,{.:#[>+~])/im
const forbiddenLegacySelector = /\.(?:btn|field|panel|badge|modal|toast)(?=$|[\s,{.:#[>+~])/im
const dependencySentinels = [
  "import axios from 'axios'; axios('/api/users')",
  "fetch('/api/users')",
  'new XMLHttpRequest()',
]
for (const sentinel of dependencySentinels) {
  if (!forbiddenDependency.test(sentinel)) {
    fail(`dependency validator does not reject ${sentinel}`)
  }
}

for (const [name, source] of sources) {
  const label = `frontend/src/components/v2/base/${name}.vue`

  if (forbiddenDependency.test(source)) {
    fail(`${label} references a forbidden Router, Store, API, or browser-storage dependency`)
  }
  if (forbiddenRawColor.test(source)) {
    fail(`${label} contains an inline color value`)
  }
  if (/:root\b/.test(source)) {
    fail(`${label} contains shared :root`)
  }
  if (/['"](?:btn|field|panel|badge|modal|toast)['"]/.test(source)) {
    fail(`${label} contains a dynamically bound legacy class`)
  }

  const classes = staticClassTokens(source)
  for (const className of classes) {
    if (forbiddenLegacyClasses.has(className)) {
      fail(`${label} uses forbidden legacy class ${className}`)
    }
    if (!className.startsWith('v2-')) {
      fail(`${label} uses non-V2 class ${className}`)
    }
  }

  const styles = styleBlocks(source)
  if (styles.length !== 1 || !/\bscoped\b/i.test(styles[0]?.attributes ?? '')) {
    fail(`${label} must contain exactly one scoped style block`)
  }
  for (const { css } of styles) {
    if (!/var\(\s*--v2-[a-z0-9-]+/i.test(css)) {
      fail(`${label} styles do not consume V2 tokens`)
    }
    if (/var\(\s*--(?!v2-)[a-z0-9-]+/i.test(css)) {
      fail(`${label} styles reference a non-V2 custom property`)
    }
    if (forbiddenGlobalSelector.test(css)) {
      fail(`${label} contains an unscoped shared element selector`)
    }
    if (forbiddenLegacySelector.test(css)) {
      fail(`${label} styles contain a legacy selector`)
    }
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

const labPaths = [
  join(frontendDir, 'dev', 'v2-base-components.html'),
  join(frontendDir, 'src', 'dev', 'V2BaseComponentsLab.vue'),
  join(frontendDir, 'src', 'dev', 'v2-base-components-main.js'),
]
for (const path of labPaths) {
  if (!existsSync(path)) fail(`missing ${relative(repoDir, path)}`)
}
const existingLabSources = labPaths.filter(existsSync).map((path) => ({
  path,
  source: read(path),
}))
for (const { path, source } of existingLabSources) {
  if (forbiddenDependency.test(source)) {
    fail(`${relative(repoDir, path)} references Router, Pinia, Store, API, service, or browser storage`)
  }
}
const labHtml = existingLabSources.find(({ path }) => path.endsWith('.html'))?.source ?? ''
if (!/<div\b[^>]*\bid=["']app["'][^>]*\bclass=["'][^"']*\bfrontend-v2\b/i.test(labHtml)) {
  fail('Component Lab root does not use frontend-v2')
}
const productionFiles = [
  join(frontendDir, 'src', 'main.js'),
  join(frontendDir, 'src', 'App.vue'),
  join(frontendDir, 'src', 'router', 'index.js'),
  join(frontendDir, 'vite.config.js'),
]
for (const path of productionFiles) {
  if (existsSync(path) && /(?:V2BaseComponentsLab|v2-base-components)/i.test(read(path))) {
    fail(`${relative(repoDir, path)} references the development-only Component Lab`)
  }
}

const contracts = {
  BaseButton: [
    [/<button\b/, 'must render a native button'],
    [/type:\s*\{\s*type:\s*String,\s*default:\s*['"]button['"]/, 'must default type to button'],
    [/:disabled=["']loading\s*\|\|\s*disabled["']/, 'must disable the native button while loading or disabled'],
    [/:aria-busy=["']loading\s*\|\|\s*undefined["']/, 'must expose loading through aria-busy'],
    [/if\s*\(\s*props\.disabled\s*\|\|\s*props\.loading\s*\)\s*return/, 'must guard click emission'],
    [/v-bind=["']\$attrs["']/, 'must forward native attributes'],
  ],
  BaseIconButton: [
    [/<button\b/, 'must render a native button'],
    [/label:\s*\{[^}]*required:\s*true/s, 'must require an accessible label'],
    [/:aria-label=["']label["']/, 'must bind aria-label'],
    [/:aria-pressed=/, 'must conditionally bind aria-pressed'],
    [/v-bind=["']\$attrs["']/, 'must forward native attributes'],
  ],
  BaseInput: [
    [/<input\b/, 'must render a native input'],
    [/<label\b[^>]*:for=["']inputId["']/, 'must associate label and input'],
    [/\buseId\s*\(/, 'must generate a stable fallback id'],
    [/:aria-invalid=["']error\s*\?\s*['"]true['"]\s*:\s*undefined["']/, 'must expose error state through aria-invalid'],
    [/:aria-describedby=["']describedBy["']/, 'must associate help or error text'],
    [/defineEmits\(\[['"]update:modelValue['"],\s*['"]focus['"],\s*['"]blur['"],\s*['"]change['"]\]\)/, 'must declare the required events'],
    [/v-bind=["']\$attrs["']/, 'must forward native attributes'],
  ],
  BaseCheckbox: [
    [/<input\b[^>]*type=["']checkbox["']/s, 'must use a native checkbox'],
    [/id:\s*\{\s*type:\s*String,\s*default:\s*['"]{2}\s*\}/, 'must support an explicit id'],
    [/props\.id\s*\|\|\s*`v2-checkbox-/, 'must preserve an explicit id before generating one'],
    [/\.indeterminate\s*=\s*Boolean\(/, 'must synchronize the native indeterminate property'],
    [/:aria-describedby=["']describedBy["']/, 'must associate description text'],
    [/defineEmits\(\[['"]update:modelValue['"],\s*['"]change['"]\]\)/, 'must declare model and change events'],
    [/v-bind=["']\$attrs["']/, 'must forward aria-label and native attributes'],
  ],
  BaseBadge: [
    [/<span\b/, 'must render a non-interactive element'],
    [/aria-hidden=["']true["']/, 'must hide the decorative status dot from assistive technology'],
  ],
  BaseChip: [
    [/<button\b/, 'must render a native button'],
    [/:aria-pressed=["']selected["']/, 'must bind aria-pressed'],
    [/defineEmits\(\[['"]select['"]\]\)/, 'must declare select event'],
    [/if\s*\(\s*props\.disabled\s*\)\s*return/, 'must guard disabled selection'],
    [/v-bind=["']\$attrs["']/, 'must forward native attributes'],
  ],
  BaseCard: [
    [/<component\b[^>]*:is=["']as["']/, 'must support the as prop'],
    [/defineEmits\(\[['"]activate['"]\]\)/, 'must declare activate event'],
    [/:role=["']interactiveRole["']/, 'must add conditional interactive role'],
    [/:tabindex=["']interactiveTabindex["']/, 'must add conditional tabindex'],
    [/@keydown\.enter=/, 'must handle Enter activation'],
    [/@keydown\.space=/, 'must handle Space activation'],
    [/event\.repeat/, 'must ignore repeated keyboard activation'],
    [/event\.target\s*!==\s*event\.currentTarget/, 'must guard nested interactive keyboard events'],
    [/attrs\.role/, 'must preserve caller role when no interactive role is added'],
    [/attrs\.tabindex/, 'must preserve caller tabindex when no interactive tabindex is added'],
    [/v-bind=["']\$attrs["']/, 'must forward native attributes'],
  ],
}

for (const [name, requirements] of Object.entries(contracts)) {
  const source = sources.get(name)
  if (!source) continue
  for (const [pattern, description] of requirements) {
    requirePattern(source, pattern, `${name} ${description}`)
  }
}

if (failures.length > 0) {
  console.error('V2 base components validation failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log(`V2 base components validation passed (${componentNames.length} components).`)
